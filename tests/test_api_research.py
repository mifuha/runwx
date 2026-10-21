"""Synthetic mart rows exercise the public research contract without credentials."""

import asyncio
from datetime import date, datetime, time, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import httpx
import pytest
from google.cloud.bigquery import Row

from runwx.api.app import ComparisonService, app, get_repository
from runwx.api.repository import BERLIN_CATALOG, COURSES, BigQueryComparisonRepository, ComparisonUnavailableError


def research_rows():
    rows = []
    for year, edition in BERLIN_CATALOG["editions"].items():
        day = date.fromisoformat(edition["date"])
        count, published = edition["captured_count"], edition["published_count"]
        rows.append({
            "snapshot_table": f"runwx-learning-mifuha.runwx_staging.berlin_{year}_research_aaaaaaaaaaaa",
            "race_date": day, "export_schema": "berlin_research_v1", "dataset_version": 2,
            "population_basis": "published_research_capture",
            "course_basis": "post_2003_course_era_not_identical_routes", "distance_m": 42195,
            "race_sha256": BERLIN_CATALOG["results_sha256"], "preparation_report_sha256": "a" * 64,
            "captured_count": count, "declared_captured_count": count,
            "accepted_count": count, "held_count": 0, "finisher_count": count,
            "published_count": published,
            "count_difference_from_published": count - published if published is not None else None,
            "distinct_source_rows": count, "distinct_source_locators": count,
            "unknown_timing_count": count, "distinct_contexts": 1,
            "top_n_requested": 20, "top_n_effective": 20,
            "comparison_status": "descriptive_research_capture",
            # Deliberately synthetic statistics, not retained real-data outputs.
            "median_pace_s_per_km": 300.0, "mean_pace_s_per_km": 310.0,
            "pace_p25_s_per_km": 280.0, "pace_p75_s_per_km": 350.0,
            "top_n_median_pace_s_per_km": 200.0,
            "weather_context": {
                "basis": "fixed_edition_window", "timezone": "Europe/Berlin",
                "start_local": "09:00", "end_local": "15:00",
                "start_utc": datetime.combine(day, time(9), ZoneInfo("Europe/Berlin")).astimezone(timezone.utc),
                "end_utc": datetime.combine(day, time(15), ZoneInfo("Europe/Berlin")).astimezone(timezone.utc),
                "observation_count": 7,
                "units": {"temperature": "°C", "wind": "m/s", "humidity": "%", "precipitation": "mm"},
                "precipitation_basis": "preceding-hour amounts ending after start through end",
                "median_temp_c": 18.0, "median_wind_mps": 2.0,
                "median_humidity_pct": 60.0, "precipitation_mm": 0.5,
                "note": "Synthetic fixed-window finish-area weather; not personal exposure.",
            },
        })
    return rows


def repository(rows):
    job = Mock()
    job.result.return_value = rows
    client = Mock()
    client.query.return_value = job
    return BigQueryComparisonRepository(client), client, job


def test_research_reads_only_materialized_mart_and_preserves_scope():
    repo, client, job = repository(research_rows())
    result = repo.get_course_comparison("berlin-marathon")
    query = client.query.call_args.args[0]
    config = client.query.call_args.kwargs["job_config"]
    assert f"FROM `{COURSES['berlin-marathon'].table_id}`" in query
    assert "runwx_staging" not in query
    assert "LIMIT 17" in query and "ORDER BY race_date, snapshot_table" in query
    assert all(sql not in query.upper() for sql in ["AVG(", "PERCENTILE_CONT(", "ROW_NUMBER("])
    assert config.maximum_bytes_billed == 64 * 1024 * 1024
    assert config.use_legacy_sql is False
    assert client.query.call_args.kwargs["location"] == "europe-west1"
    assert client.query.call_args.kwargs["timeout"] == 10
    job.result.assert_called_once_with(timeout=30)
    assert result.scope == "research_capture" and len(result.editions) == 16
    assert result.editions[-1].pace.median_s_per_km == 300.0
    assert result.editions[-1].pace.mean_s_per_km == 310.0
    assert result.editions[-1].weather.start_utc.hour == 7
    assert result.editions[-1].weather.end_utc.hour == 13
    assert result.editions[-1].weather.precipitation_mm == 0.5
    body = result.model_dump(mode="json")
    assert "baseline_event_id" not in body
    assert "finishers" not in body["editions"][0]
    assert "started_at_utc" not in body["editions"][0]
    assert "matched_finishers" not in body["editions"][0]["weather"]
    assert all(edition["timing_basis"] is None for edition in body["editions"])
    assert result.editions[5].count_difference_from_published == 79
    assert result.editions[10].published_count is None
    assert result.editions[10].count_difference_from_published is None


def test_research_separates_accepted_and_held_records():
    rows = research_rows()
    rows[0].update(accepted_count=30708, held_count=1, finisher_count=30708)
    repo, _, _ = repository(rows)
    result = repo.get_course_comparison("berlin-marathon")
    assert result.editions[0].captured_count == 30709
    assert result.editions[0].accepted_count == 30708
    assert result.editions[0].held_count == 1


def test_research_accepts_nested_bigquery_row_objects():
    def warehouse_row(values):
        return Row(tuple(values.values()), {name: index for index, name in enumerate(values)})

    rows = research_rows()
    for row in rows:
        context = row["weather_context"]
        context["units"] = warehouse_row(context["units"])
        row["weather_context"] = warehouse_row(context)
    repo, _, _ = repository([warehouse_row(row) for row in rows])
    assert len(repo.get_course_comparison("berlin-marathon").editions) == 16


@pytest.mark.parametrize("change", [
    {"distance_m": 21097}, {"captured_count": 1}, {"accepted_count": 1},
    {"published_count": 1}, {"count_difference_from_published": 1},
    {"unknown_timing_count": 0}, {"top_n_requested": 10}, {"top_n_effective": 19},
    {"population_basis": "official_full_field"}, {"course_basis": "identical_route"},
    {"comparison_status": "comparable"}, {"race_sha256": "b" * 64},
    {"preparation_report_sha256": "b" * 64},
    {"snapshot_table": "other-project.runwx_staging.berlin_2003_research_aaaaaaaaaaaa"},
    {"race_date": date(2003, 9, 29)},
    {"median_pace_s_per_km": float("nan")}, {"mean_pace_s_per_km": None},
])
def test_research_rejects_invalid_identity_counts_and_pace(change):
    rows = research_rows()
    rows[0].update(change)
    repo, _, _ = repository(rows)
    with pytest.raises(ComparisonUnavailableError, match="berlin-marathon"):
        repo.get_course_comparison("berlin-marathon")


@pytest.mark.parametrize("change", [
    {"basis": "runner_midpoint"}, {"timezone": "UTC"}, {"observation_count": 6},
    {"start_local": "10:00"}, {"end_local": "16:00"},
    {"start_utc": datetime(2003, 9, 28, 9, tzinfo=timezone.utc)},
    {"end_utc": datetime(2003, 9, 29, 13, tzinfo=timezone.utc)},
    {"start_utc": datetime(2003, 9, 28, 7)},
    {"units": {"temperature": "F"}}, {"precipitation_basis": "median_hourly_amount"},
    {"median_temp_c": float("inf")}, {"median_temp_c": None}, {"precipitation_mm": -1},
])
def test_research_rejects_wrong_weather_contract(change):
    rows = research_rows()
    rows[0]["weather_context"].update(change)
    repo, _, _ = repository(rows)
    with pytest.raises(ComparisonUnavailableError):
        repo.get_course_comparison("berlin-marathon")


@pytest.mark.parametrize("kind", ["empty", "missing", "duplicate", "extra", "reversed"])
def test_research_requires_the_complete_ordered_cohort(kind):
    rows = research_rows()
    rows = {"empty": [], "missing": rows[:-1], "duplicate": [rows[1], *rows[1:]],
            "extra": [*rows, rows[-1]], "reversed": rows[::-1]}[kind]
    repo, _, _ = repository(rows)
    with pytest.raises(ComparisonUnavailableError):
        repo.get_course_comparison("berlin-marathon")


def test_research_endpoint_serializes_its_distinct_contract():
    repo, _, _ = repository(research_rows())

    async def get():
        app.dependency_overrides[get_repository] = lambda: ComparisonService(repo)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await client.get("/api/courses/berlin-marathon/comparison")
        finally:
            app.dependency_overrides.clear()

    response = asyncio.run(get())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.json()["scope"] == "research_capture"
    assert response.json()["editions"][-1]["year"] == 2018
    assert response.json()["editions"][-1]["weather"]["start_utc"].endswith("Z")
