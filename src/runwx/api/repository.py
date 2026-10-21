"""Read the small public comparison contract from explicit BigQuery marts."""

from dataclasses import dataclass
import logging
import re
from typing import Literal, Mapping
from zoneinfo import ZoneInfo

from google.api_core.exceptions import GoogleAPICallError, RetryError
from google.cloud import bigquery
from pydantic import ValidationError

from runwx.api.models import (
    BaselineChange,
    CourseComparison,
    EditionComparison,
    PaceSummary,
    ResearchCourseComparison,
    ResearchEditionComparison,
    ResearchWeatherSummary,
    SampledCourseComparison,
    SampledEditionComparison,
    SampledWeatherSummary,
    TimingCounts,
    WeatherSummary,
)
from runwx.adapters.races.berlin_csv import CATALOG as BERLIN_CATALOG


LOCATION = "europe-west1"
# BigQuery bills at least 10 MiB per referenced table; Lydd currently reaches five.
MAXIMUM_BYTES_BILLED = 64 * 1024 * 1024
MAX_EDITIONS = 50
LOGGER = logging.getLogger(__name__)
TABLE_ID = re.compile(
    r"[a-z][a-z0-9-]{4,61}[a-z0-9]\."
    r"[A-Za-z_][A-Za-z0-9_]*\."
    r"[A-Za-z_][A-Za-z0-9_]*"
)


class UnknownCourseError(KeyError):
    """The requested course slug is not in the reviewed API catalog."""


class ComparisonUnavailableError(RuntimeError):
    """The configured mart could not provide a valid response."""


@dataclass(frozen=True)
class CourseSource:
    slug: str
    name: str
    course_id: str
    table_id: str
    distance_m: int
    baseline_event_id: str | None = None
    scope: Literal["full_field", "top_1000", "research_capture"] = "full_field"
    maximum_bytes_billed: int = MAXIMUM_BYTES_BILLED

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.slug):
            raise ValueError("course slug must contain lowercase words and hyphens")
        if (
            not self.name.strip()
            or not self.course_id.strip()
            or (self.scope != "research_capture" and (
                not self.baseline_event_id or not self.baseline_event_id.strip()
            ))
        ):
            raise ValueError("course name, course ID and baseline event ID are required")
        if self.scope == "research_capture" and self.baseline_event_id is not None:
            raise ValueError("research summaries do not have a comparison baseline")
        if self.distance_m <= 0:
            raise ValueError("course distance must be positive")
        if not TABLE_ID.fullmatch(self.table_id):
            raise ValueError("comparison table must be a fully qualified simple table ID")
        if not 0 < self.maximum_bytes_billed <= 200 * 1024 * 1024:
            raise ValueError("comparison query cap must be positive and at most 200 MiB")


COURSES: dict[str, CourseSource] = {
    "lydd-half": CourseSource(
        slug="lydd-half",
        name="Lydd Half Marathon",
        course_id="lydd-half",
        table_id=(
            "runwx-learning-mifuha."
            "runwx_dbt_lydd_2022_99783aaa85b8."
            "mart_course_comparison"
        ),
        distance_m=21097,
        baseline_event_id="eventrac:21723",
    ),
    "folkestone-half": CourseSource(
        slug="folkestone-half",
        name="Folkestone Half Marathon",
        course_id="folkestone-half-marathon-2014-route",
        table_id=(
            "runwx-learning-mifuha."
            "runwx_dbt_folkestone_2019_f95b3ae312e3."
            "mart_course_comparison"
        ),
        distance_m=21097,
        baseline_event_id="eventrac:36835",
    ),
    "battersea-park-10k": CourseSource(
        slug="battersea-park-10k",
        name="Battersea Park 10K",
        course_id="battersea-park-10k",
        table_id=(
            "runwx-learning-mifuha."
            "runwx_dbt_battersea_2019_03_16_301b6c15b5f8."
            "mart_course_comparison"
        ),
        distance_m=10000,
        baseline_event_id="sri_chinmoy:battersea-10k-2022-03-26",
        maximum_bytes_billed=200 * 1024 * 1024,
    ),
    "great-north-run": CourseSource(
        slug="great-north-run",
        name="Great North Run",
        course_id="great-north-run-traditional",
        table_id=(
            "runwx-learning-mifuha."
            "runwx_dbt_gnr_top1000_v1."
            "mart_gnr_sample_comparison"
        ),
        distance_m=21100,
        baseline_event_id="greatrun:881",
        scope="top_1000",
    ),
    "berlin-marathon": CourseSource(
        slug="berlin-marathon",
        name="Berlin Marathon",
        course_id="berlin-post-2003-course-era",
        table_id="runwx-learning-mifuha.runwx_dbt_berlin_research_v1.mart_berlin_edition_summary",
        distance_m=42195,
        scope="research_capture",
    ),
}


SELECT_COLUMNS = """
    event_id,
    course_id,
    started_at_utc,
    distance_m,
    finisher_count,
    mean_pace_s_per_km,
    median_pace_s_per_km,
    pace_p25_s_per_km,
    pace_p75_s_per_km,
    top_n_effective,
    top_n_median_pace_s_per_km,
    weather_matched_count,
    weather_coverage_fraction,
    weather_coverage_status,
    median_temp_c,
    median_wind_mps,
    median_precipitation_mm,
    median_humidity_pct,
    baseline_event_id,
    comparison_status,
    median_pace_change_pct,
    speed_at_median_duration_change_pct
""".strip()

SAMPLED_SELECT_COLUMNS = """
    event_id,
    course_id,
    race_date,
    distance_m,
    sample_size,
    sample_label,
    sample_note,
    timing_note,
    chip_count,
    gun_count,
    unknown_count,
    mean_pace_s_per_km,
    median_pace_s_per_km,
    pace_p25_s_per_km,
    pace_p75_s_per_km,
    top_n_effective,
    top_n_median_pace_s_per_km,
    weather_context_basis,
    weather_context_note,
    weather_start_local,
    weather_end_local,
    median_temp_c,
    median_wind_mps,
    median_humidity_pct,
    precipitation_mm,
    baseline_event_id,
    comparison_status,
    median_pace_change_pct
""".strip()

RESEARCH_SELECT_COLUMNS = """
    snapshot_table, race_date, export_schema, dataset_version, population_basis,
    course_basis, distance_m, race_sha256, preparation_report_sha256,
    captured_count, declared_captured_count, accepted_count, held_count,
    published_count, count_difference_from_published, finisher_count,
    distinct_source_rows, distinct_source_locators, unknown_timing_count,
    distinct_contexts, top_n_requested, top_n_effective, comparison_status,
    mean_pace_s_per_km, median_pace_s_per_km, pace_p25_s_per_km,
    pace_p75_s_per_km, top_n_median_pace_s_per_km, weather_context
""".strip()


class BigQueryComparisonRepository:
    def __init__(
        self,
        client,
        *,
        courses: Mapping[str, CourseSource] = COURSES,
        location: str = LOCATION,
    ):
        if location != LOCATION:
            raise ValueError(f"comparison marts must be queried in {LOCATION}")
        if not courses or any(slug != source.slug for slug, source in courses.items()):
            raise ValueError("course catalog keys must match their source slugs")
        self._client = client
        self._courses = dict(courses)
        self._location = location

    def get_course_comparison(
        self, course_slug: str
    ) -> CourseComparison | SampledCourseComparison | ResearchCourseComparison:
        try:
            source = self._courses[course_slug]
        except KeyError as error:
            raise UnknownCourseError(course_slug) from error

        if source.scope == "top_1000":
            return self._get_sampled_comparison(source)
        if source.scope == "research_capture":
            return self._get_research_comparison(source)

        query = f"""
            SELECT {SELECT_COLUMNS}
            FROM `{source.table_id}`
            WHERE course_id = @course_id
            ORDER BY started_at_utc, event_id
            LIMIT {MAX_EDITIONS}
        """
        job_config = bigquery.QueryJobConfig(
            use_legacy_sql=False,
            maximum_bytes_billed=source.maximum_bytes_billed,
            query_parameters=[
                bigquery.ScalarQueryParameter("course_id", "STRING", source.course_id)
            ],
        )
        try:
            job = self._client.query(
                query,
                job_config=job_config,
                location=self._location,
                timeout=10,
            )
            rows = [dict(row) for row in job.result(timeout=30)]
            return self._build_response(source, rows)
        except (
            AttributeError,
            GoogleAPICallError,
            KeyError,
            RetryError,
            TimeoutError,
            TypeError,
            ValidationError,
            ValueError,
        ) as error:
            LOGGER.exception("Comparison query failed for course %s", source.slug)
            raise ComparisonUnavailableError(
                f"comparison mart unavailable for {source.slug}"
            ) from error

    @staticmethod
    def _build_response(source: CourseSource, rows: list[dict]) -> CourseComparison:
        if not rows:
            return CourseComparison(
                course_slug=source.slug,
                course_name=source.name,
                course_id=source.course_id,
                distance_m=source.distance_m,
                baseline_event_id=source.baseline_event_id,
                editions=[],
            )

        course_ids = {row["course_id"] for row in rows}
        distances = {row["distance_m"] for row in rows}
        baselines = {row["baseline_event_id"] for row in rows}
        event_ids = [row["event_id"] for row in rows]
        if course_ids != {source.course_id}:
            raise ValueError("comparison rows contain an unexpected course")
        if distances != {source.distance_m} or baselines != {source.baseline_event_id}:
            raise ValueError("comparison rows disagree on distance or baseline")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("comparison rows repeat an event")

        editions = [
            EditionComparison(
                event_id=row["event_id"],
                year=row["started_at_utc"].year,
                started_at_utc=row["started_at_utc"],
                comparison_status=row["comparison_status"],
                finishers=row["finisher_count"],
                pace=PaceSummary(
                    median_s_per_km=row["median_pace_s_per_km"],
                    mean_s_per_km=row["mean_pace_s_per_km"],
                    p25_s_per_km=row["pace_p25_s_per_km"],
                    p75_s_per_km=row["pace_p75_s_per_km"],
                    fastest_n=row["top_n_effective"],
                    fastest_n_median_s_per_km=row["top_n_median_pace_s_per_km"],
                ),
                weather=WeatherSummary(
                    matched_finishers=row["weather_matched_count"],
                    coverage_fraction=row["weather_coverage_fraction"],
                    coverage_status=row["weather_coverage_status"],
                    median_temperature_c=row["median_temp_c"],
                    median_wind_mps=row["median_wind_mps"],
                    median_precipitation_mm=row["median_precipitation_mm"],
                    median_humidity_pct=row["median_humidity_pct"],
                ),
                change_from_baseline=BaselineChange(
                    median_pace_pct=row["median_pace_change_pct"],
                    speed_at_median_duration_pct=(
                        row["speed_at_median_duration_change_pct"]
                    ),
                ),
            )
            for row in rows
        ]
        return CourseComparison(
            course_slug=source.slug,
            course_name=source.name,
            course_id=source.course_id,
            distance_m=next(iter(distances)),
            baseline_event_id=next(iter(baselines)),
            editions=editions,
        )

    def _get_sampled_comparison(self, source: CourseSource) -> SampledCourseComparison:
        query = f"""
            SELECT {SAMPLED_SELECT_COLUMNS}
            FROM `{source.table_id}`
            WHERE course_id = @course_id
            ORDER BY race_date, event_id
            LIMIT {MAX_EDITIONS}
        """
        job_config = bigquery.QueryJobConfig(
            use_legacy_sql=False,
            maximum_bytes_billed=MAXIMUM_BYTES_BILLED,
            query_parameters=[
                bigquery.ScalarQueryParameter("course_id", "STRING", source.course_id)
            ],
        )
        try:
            job = self._client.query(
                query,
                job_config=job_config,
                location=self._location,
                timeout=10,
            )
            rows = [dict(row) for row in job.result(timeout=30)]
            return self._build_sampled_response(source, rows)
        except (
            AttributeError,
            GoogleAPICallError,
            KeyError,
            RetryError,
            TimeoutError,
            TypeError,
            ValidationError,
            ValueError,
        ) as error:
            LOGGER.exception("Comparison query failed for course %s", source.slug)
            raise ComparisonUnavailableError(
                f"comparison mart unavailable for {source.slug}"
            ) from error

    @staticmethod
    def _build_sampled_response(
        source: CourseSource, rows: list[dict]
    ) -> SampledCourseComparison:
        if not rows:
            raise ValueError("sampled comparison has no editions")
        event_ids = [row["event_id"] for row in rows]
        years = [row["race_date"].year for row in rows]
        labels = {row["sample_label"] for row in rows}
        notes = {row["sample_note"] for row in rows}
        if (
            {row["course_id"] for row in rows} != {source.course_id}
            or {row["distance_m"] for row in rows} != {source.distance_m}
            or {row["baseline_event_id"] for row in rows} != {source.baseline_event_id}
            or len(event_ids) != len(set(event_ids))
            or event_ids.count(source.baseline_event_id) != 1
            or len(years) != len(set(years))
            or labels != {"Top 1,000 only*"}
            or len(notes) != 1
            or {row["weather_context_basis"] for row in rows} != {"fixed_event_window"}
            or {row["weather_start_local"] for row in rows} != {"10:00"}
            or {row["weather_end_local"] for row in rows} != {"14:00"}
        ):
            raise ValueError("sampled comparison scope or identity disagrees")
        for row in rows:
            if (
                row["sample_size"] != 1000
                or row["chip_count"] + row["gun_count"] + row["unknown_count"]
                != row["sample_size"]
                or (row["comparison_status"] == "descriptive_sample")
                != (row["median_pace_change_pct"] is not None)
            ):
                raise ValueError("sampled comparison counts or baseline disagree")

        return SampledCourseComparison(
            course_slug=source.slug,
            course_name=source.name,
            course_id=source.course_id,
            distance_m=source.distance_m,
            baseline_event_id=source.baseline_event_id,
            sample_label=next(iter(labels)),
            sample_note=next(iter(notes)),
            editions=[
                SampledEditionComparison(
                    event_id=row["event_id"],
                    year=row["race_date"].year,
                    race_date=row["race_date"],
                    comparison_status=row["comparison_status"],
                    sample_size=row["sample_size"],
                    pace=PaceSummary(
                        median_s_per_km=row["median_pace_s_per_km"],
                        mean_s_per_km=row["mean_pace_s_per_km"],
                        p25_s_per_km=row["pace_p25_s_per_km"],
                        p75_s_per_km=row["pace_p75_s_per_km"],
                        fastest_n=row["top_n_effective"],
                        fastest_n_median_s_per_km=row["top_n_median_pace_s_per_km"],
                    ),
                    weather=SampledWeatherSummary(
                        median_temperature_c=row["median_temp_c"],
                        median_wind_mps=row["median_wind_mps"],
                        median_humidity_pct=row["median_humidity_pct"],
                        precipitation_mm=row["precipitation_mm"],
                        context_note=row["weather_context_note"],
                    ),
                    timing=TimingCounts(
                        chip=row["chip_count"],
                        gun=row["gun_count"],
                        unknown=row["unknown_count"],
                        note=row["timing_note"],
                    ),
                    median_pace_change_pct=row["median_pace_change_pct"],
                )
                for row in rows
            ],
        )

    def _get_research_comparison(self, source: CourseSource) -> ResearchCourseComparison:
        # The materialized mart needs no access to the underlying raw snapshots.
        query = f"""
            SELECT {RESEARCH_SELECT_COLUMNS}
            FROM `{source.table_id}`
            ORDER BY race_date, snapshot_table
            LIMIT {len(BERLIN_CATALOG['editions']) + 1}
        """
        try:
            job = self._client.query(
                query,
                job_config=bigquery.QueryJobConfig(
                    use_legacy_sql=False,
                    maximum_bytes_billed=source.maximum_bytes_billed,
                ),
                location=self._location,
                timeout=10,
            )
            return self._build_research_response(
                source, [dict(row) for row in job.result(timeout=30)]
            )
        except (
            AttributeError, GoogleAPICallError, KeyError, RetryError, TimeoutError,
            TypeError, ValidationError, ValueError,
        ) as error:
            LOGGER.exception("Comparison query failed for course %s", source.slug)
            raise ComparisonUnavailableError(
                f"comparison mart unavailable for {source.slug}"
            ) from error

    @staticmethod
    def _build_research_response(
        source: CourseSource, rows: list[dict]
    ) -> ResearchCourseComparison:
        if len(rows) != len(BERLIN_CATALOG["editions"]):
            raise ValueError("research mart must contain the reviewed edition cohort")
        dates = [row["race_date"] for row in rows]
        if len(set(dates)) != len(dates) or dates != sorted(dates):
            raise ValueError("research editions repeat or are out of order")
        editions = []
        for row in rows:
            day = row["race_date"]
            qualified = BERLIN_CATALOG["editions"][str(day.year)]
            count = row["captured_count"]
            accepted, held = row["accepted_count"], row["held_count"]
            snapshot = re.fullmatch(
                re.escape(source.table_id.split(".")[0])
                + rf"\.runwx_staging\.berlin_{day.year}_research_([0-9a-f]{{12}})",
                row["snapshot_table"],
            )
            if (
                day.isoformat() != qualified["date"]
                or row["population_basis"] != "published_research_capture"
                or row["course_basis"] != "post_2003_course_era_not_identical_routes"
                or row["export_schema"] != "berlin_research_v1"
                or row["dataset_version"] != 2
                or row["race_sha256"] != BERLIN_CATALOG["results_sha256"]
                or row["distance_m"] != source.distance_m
                or any(type(value) is not int or value < 0 for value in (count, accepted, held))
                or count != qualified["captured_count"]
                or row["declared_captured_count"] != count
                or accepted + held != count or row["finisher_count"] != accepted
                or row["distinct_source_rows"] != count
                or row["distinct_source_locators"] != count
                or row["unknown_timing_count"] != count or row["distinct_contexts"] != 1
                or row["published_count"] != qualified["published_count"]
                or row["count_difference_from_published"] != (
                    count - qualified["published_count"]
                    if qualified["published_count"] is not None else None
                )
                or row["top_n_requested"] != 20
                or row["top_n_effective"] != min(20, accepted)
                or not snapshot
                or not re.fullmatch(r"[0-9a-f]{64}", row["preparation_report_sha256"])
                or snapshot.group(1) != row["preparation_report_sha256"][:12]
            ):
                raise ValueError("research population or provenance disagrees with qualification")
            context = dict(row["weather_context"])
            if dict(context["units"]) != {
                "temperature": "°C", "wind": "m/s", "humidity": "%", "precipitation": "mm",
            } or context["precipitation_basis"] != "preceding-hour amounts ending after start through end":
                raise ValueError("research weather units or precipitation interval disagree")
            weather = ResearchWeatherSummary(
                basis=context["basis"], timezone=context["timezone"],
                start_local=context["start_local"], end_local=context["end_local"],
                start_utc=context["start_utc"], end_utc=context["end_utc"],
                observation_count=context["observation_count"],
                median_temperature_c=context["median_temp_c"],
                median_wind_mps=context["median_wind_mps"],
                median_humidity_pct=context["median_humidity_pct"],
                precipitation_mm=context["precipitation_mm"], context_note=context["note"],
            )
            for observed, hour in [(weather.start_utc, 9), (weather.end_utc, 15)]:
                local = observed.astimezone(ZoneInfo("Europe/Berlin"))
                if local.date() != day or (local.hour, local.minute, local.second, local.microsecond) != (hour, 0, 0, 0):
                    raise ValueError("research weather window differs from the race date")
            pace = PaceSummary(
                median_s_per_km=row["median_pace_s_per_km"],
                mean_s_per_km=row["mean_pace_s_per_km"],
                p25_s_per_km=row["pace_p25_s_per_km"], p75_s_per_km=row["pace_p75_s_per_km"],
                fastest_n=row["top_n_effective"],
                fastest_n_median_s_per_km=row["top_n_median_pace_s_per_km"],
            )
            values = list(pace.model_dump(exclude={"fastest_n"}).values())
            if accepted and any(value is None or value <= 0 for value in values):
                raise ValueError("research pace values disagree with the accepted population")
            if not accepted and any(value is not None for value in values):
                raise ValueError("research pace values disagree with the accepted population")
            editions.append(ResearchEditionComparison(
                year=day.year, race_date=day, comparison_status=row["comparison_status"],
                captured_count=count, accepted_count=accepted, held_count=held,
                published_count=row["published_count"],
                count_difference_from_published=row["count_difference_from_published"],
                timing_basis=None, pace=pace, weather=weather,
            ))
        return ResearchCourseComparison(
            course_slug=source.slug, course_name=source.name, course_id=source.course_id,
            distance_m=source.distance_m,
            population_note="An anonymised research capture, not verified complete official fields. Published totals include walkers from 2009 and may cover a different population; count differences are retained.",
            course_note="Post-2003 course era; smaller route changes are not verified. Timing basis and individual starts are unknown.",
            editions=editions,
        )
