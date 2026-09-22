from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import BadRequest

from runwx.api.repository import (
    BigQueryComparisonRepository,
    COURSES,
    ComparisonUnavailableError,
    CourseSource,
    UnknownCourseError,
)


SOURCE = CourseSource(
    slug="example-half",
    name="Example Half Marathon",
    course_id="example-half-route",
    table_id="runwx-example.edition_2022.mart_course_comparison",
    distance_m=21097,
    baseline_event_id="eventrac:123",
)


def comparison_row(**changes):
    row = {
        "event_id": "eventrac:123",
        "course_id": SOURCE.course_id,
        "started_at_utc": datetime(2022, 3, 6, 10, tzinfo=timezone.utc),
        "distance_m": 21097,
        "finisher_count": 189,
        "mean_pace_s_per_km": 330.8,
        "median_pace_s_per_km": 329.6,
        "pace_p25_s_per_km": 283.3,
        "pace_p75_s_per_km": 375.9,
        "top_n_effective": 20,
        "top_n_median_pace_s_per_km": 234.8,
        "weather_matched_count": 189,
        "weather_coverage_fraction": 1.0,
        "weather_coverage_status": "complete",
        "median_temp_c": 5.8,
        "median_wind_mps": 7.34,
        "median_precipitation_mm": 0.0,
        "median_humidity_pct": 61.0,
        "baseline_event_id": "eventrac:123",
        "comparison_status": "comparable",
        "median_pace_change_pct": 0.0,
        "speed_at_median_duration_change_pct": 0.0,
    }
    row.update(changes)
    return row


def repository(rows):
    job = Mock()
    job.result.return_value = rows
    client = Mock()
    client.query.return_value = job
    return BigQueryComparisonRepository(client, courses={SOURCE.slug: SOURCE}), client, job


def sampled_row(**changes):
    row = {
        "event_id": "greatrun:881",
        "course_id": "great-north-run-traditional",
        "race_date": date(2019, 9, 8),
        "distance_m": 21100,
        "sample_size": 1000,
        "sample_label": "Top 1,000 only*",
        "sample_note": "Fastest 1,000 running results; not all finishers.",
        "timing_note": "Published timing flags retained.",
        "chip_count": 994,
        "gun_count": 6,
        "unknown_count": 0,
        "mean_pace_s_per_km": 243.4,
        "median_pace_s_per_km": 246.9,
        "pace_p25_s_per_km": 235.0,
        "pace_p75_s_per_km": 259.0,
        "top_n_effective": 20,
        "top_n_median_pace_s_per_km": 206.6,
        "weather_context_basis": "fixed_event_window",
        "weather_context_note": "Fixed 10:00–14:00 local start-area ERA5 window.",
        "weather_start_local": "10:00",
        "weather_end_local": "14:00",
        "median_temp_c": 13.9,
        "median_wind_mps": 1.04,
        "median_humidity_pct": 69.0,
        "precipitation_mm": 0.0,
        "baseline_event_id": "greatrun:881",
        "comparison_status": "descriptive_sample",
        "median_pace_change_pct": 0.0,
    }
    row.update(changes)
    return row


def sampled_repository(rows):
    job = Mock()
    job.result.return_value = rows
    client = Mock()
    client.query.return_value = job
    source = COURSES["great-north-run"]
    return BigQueryComparisonRepository(client, courses={source.slug: source}), client


def test_query_uses_only_catalog_table_and_parameterized_course():
    repo, client, job = repository([comparison_row()])

    result = repo.get_course_comparison(SOURCE.slug)

    query = client.query.call_args.args[0]
    kwargs = client.query.call_args.kwargs
    config = kwargs["job_config"]
    assert f"FROM `{SOURCE.table_id}`" in query
    assert "WHERE course_id = @course_id" in query
    assert "LIMIT 50" in query
    assert SOURCE.course_id not in query
    assert config.use_legacy_sql is False
    assert config.maximum_bytes_billed == 64 * 1024 * 1024
    assert [(parameter.name, parameter.type_, parameter.value)
            for parameter in config.query_parameters] == [
        ("course_id", "STRING", SOURCE.course_id)
    ]
    assert kwargs["location"] == "europe-west1"
    assert kwargs["timeout"] == 10
    job.result.assert_called_once_with(timeout=30)
    assert result.course_slug == SOURCE.slug
    assert result.distance_m == 21097
    assert result.editions[0].year == 2022
    assert result.editions[0].pace.fastest_n == 20
    assert result.editions[0].weather.median_temperature_c == 5.8


def test_sampled_query_keeps_sample_weather_and_timing_distinct_from_full_field():
    repo, client = sampled_repository([sampled_row()])

    result = repo.get_course_comparison("great-north-run")

    query = client.query.call_args.args[0]
    config = client.query.call_args.kwargs["job_config"]
    assert "FROM `runwx-learning-mifuha.runwx_dbt_gnr_top1000_v1.mart_gnr_sample_comparison`" in query
    assert "WHERE course_id = @course_id" in query
    assert "ORDER BY race_date, event_id" in query
    assert config.maximum_bytes_billed == 64 * 1024 * 1024
    assert config.query_parameters[0].value == "great-north-run-traditional"
    assert result.scope == "top_1000"
    assert result.sample_label == "Top 1,000 only*"
    assert result.editions[0].sample_size == 1000
    assert result.editions[0].timing.chip == 994
    assert result.editions[0].weather.precipitation_mm == 0.0
    assert result.editions[0].median_pace_change_pct == 0.0


@pytest.mark.parametrize("rows", [
    [],
    [sampled_row(sample_size=999)],
    [sampled_row(chip_count=993)],
    [sampled_row(weather_context_basis="runner_midpoint")],
    [sampled_row(weather_end_local="16:00")],
    [sampled_row(median_pace_change_pct=None)],
    [sampled_row(event_id="greatrun:other")],
])
def test_invalid_sampled_mart_is_unavailable(rows):
    repo, _ = sampled_repository(rows)

    with pytest.raises(ComparisonUnavailableError, match="great-north-run"):
        repo.get_course_comparison("great-north-run")


def test_unknown_course_never_queries_bigquery():
    repo, client, _ = repository([])

    with pytest.raises(UnknownCourseError):
        repo.get_course_comparison("not-configured")

    client.query.assert_not_called()


@pytest.mark.parametrize(
    "rows",
    [
        [comparison_row(course_id="other-course")],
        [comparison_row(), comparison_row()],
        [comparison_row(median_pace_s_per_km=float("nan"))],
        [comparison_row(started_at_utc=datetime(2022, 3, 6, 10))],
        [{key: value for key, value in comparison_row().items() if key != "finisher_count"}],
    ],
)
def test_invalid_mart_rows_are_reported_as_unavailable(rows):
    repo, _, _ = repository(rows)

    with pytest.raises(ComparisonUnavailableError, match="example-half"):
        repo.get_course_comparison(SOURCE.slug)


def test_known_course_with_no_rows_has_an_empty_edition_list():
    repo, _, _ = repository([])

    result = repo.get_course_comparison(SOURCE.slug)

    assert result.course_id == SOURCE.course_id
    assert result.distance_m == 21097
    assert result.baseline_event_id == "eventrac:123"
    assert result.editions == []


def test_query_failure_logs_course_and_original_exception(caplog):
    client = Mock()
    failure = BadRequest("Query exceeded limit for bytes billed")
    client.query.side_effect = failure
    repo = BigQueryComparisonRepository(client, courses={SOURCE.slug: SOURCE})

    with caplog.at_level("ERROR", logger="runwx.api.repository"):
        with pytest.raises(ComparisonUnavailableError, match="example-half") as caught:
            repo.get_course_comparison(SOURCE.slug)

    record, = caplog.records
    assert record.getMessage() == "Comparison query failed for course example-half"
    assert record.exc_info is not None
    assert record.exc_info[1] is failure
    assert record.exc_info[2] is not None
    assert caught.value.__cause__ is failure


def test_course_catalog_rejects_a_query_fragment_as_a_table():
    with pytest.raises(ValueError, match="fully qualified"):
        CourseSource(
            slug="unsafe",
            name="Unsafe",
            course_id="unsafe",
            table_id="project.dataset.table` WHERE TRUE; --",
            distance_m=21097,
            baseline_event_id="eventrac:1",
        )


def test_public_catalog_matches_the_verified_comparison_views():
    assert {
        slug: (
            source.course_id,
            source.distance_m,
            source.baseline_event_id,
            source.table_id,
        )
        for slug, source in COURSES.items()
    } == {
        "lydd-half": (
            "lydd-half",
            21097,
            "eventrac:21723",
            "runwx-learning-mifuha.runwx_dbt_lydd_2022_99783aaa85b8.mart_course_comparison",
        ),
        "folkestone-half": (
            "folkestone-half-marathon-2014-route",
            21097,
            "eventrac:36835",
            "runwx-learning-mifuha.runwx_dbt_folkestone_2019_f95b3ae312e3.mart_course_comparison",
        ),
        "great-north-run": (
            "great-north-run-traditional",
            21100,
            "greatrun:881",
            "runwx-learning-mifuha.runwx_dbt_gnr_top1000_v1.mart_gnr_sample_comparison",
        ),
    }
