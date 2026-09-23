"""Read the small public comparison contract from explicit BigQuery marts."""

from dataclasses import dataclass
import logging
import re
from typing import Literal, Mapping

from google.api_core.exceptions import GoogleAPICallError, RetryError
from google.cloud import bigquery
from pydantic import ValidationError

from runwx.api.models import (
    BaselineChange,
    CourseComparison,
    EditionComparison,
    PaceSummary,
    SampledCourseComparison,
    SampledEditionComparison,
    SampledWeatherSummary,
    TimingCounts,
    WeatherSummary,
)


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
    baseline_event_id: str
    scope: Literal["full_field", "top_1000"] = "full_field"
    maximum_bytes_billed: int = MAXIMUM_BYTES_BILLED

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.slug):
            raise ValueError("course slug must contain lowercase words and hyphens")
        if (
            not self.name.strip()
            or not self.course_id.strip()
            or not self.baseline_event_id.strip()
        ):
            raise ValueError("course name, course ID and baseline event ID are required")
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
            "runwx_dbt_battersea_2022_03_26_18f9f3ba0578."
            "mart_course_comparison"
        ),
        distance_m=10000,
        baseline_event_id="sri_chinmoy:battersea-10k-2022-03-26",
        maximum_bytes_billed=160 * 1024 * 1024,
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
    ) -> CourseComparison | SampledCourseComparison:
        try:
            source = self._courses[course_slug]
        except KeyError as error:
            raise UnknownCourseError(course_slug) from error

        if source.scope == "top_1000":
            return self._get_sampled_comparison(source)

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
