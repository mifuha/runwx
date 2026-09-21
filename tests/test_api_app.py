import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

import httpx

from runwx.api.app import ComparisonService, app, get_repository
from runwx.api.models import (
    BaselineChange,
    CourseComparison,
    EditionComparison,
    PaceSummary,
    WeatherSummary,
)
from runwx.api.repository import ComparisonUnavailableError, UnknownCourseError


class Repository:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    async def get_course_comparison(self, course_slug):
        self.requests.append(course_slug)
        if self.error:
            raise self.error
        return self.result


def response():
    return CourseComparison(
        course_slug="lydd-half",
        course_name="Lydd Half Marathon",
        course_id="lydd-half",
        distance_m=21097,
        baseline_event_id="eventrac:21723",
        editions=[
            EditionComparison(
                event_id="eventrac:21723",
                year=2022,
                started_at_utc=datetime(2022, 3, 6, 10, tzinfo=timezone.utc),
                comparison_status="comparable",
                finishers=189,
                pace=PaceSummary(
                    median_s_per_km=329.6,
                    mean_s_per_km=330.8,
                    p25_s_per_km=283.3,
                    p75_s_per_km=375.9,
                    fastest_n=20,
                    fastest_n_median_s_per_km=234.8,
                ),
                weather=WeatherSummary(
                    matched_finishers=189,
                    coverage_fraction=1.0,
                    coverage_status="complete",
                    median_temperature_c=5.8,
                    median_wind_mps=7.34,
                    median_precipitation_mm=0.0,
                    median_humidity_pct=61.0,
                ),
                change_from_baseline=BaselineChange(
                    median_pace_pct=0.0,
                    speed_at_median_duration_pct=0.0,
                ),
            )
        ],
    )


async def request(repository, path):
    async def override_repository():
        return repository

    app.dependency_overrides[get_repository] = override_repository
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.clear()


def test_comparison_endpoint_returns_the_public_contract():
    repository = Repository(result=response())

    result = asyncio.run(
        request(repository, "/api/courses/lydd-half/comparison")
    )

    assert result.status_code == 200
    assert result.headers["cache-control"] == "public, max-age=300"
    assert repository.requests == ["lydd-half"]
    assert result.json() == {
        "course_slug": "lydd-half",
        "course_name": "Lydd Half Marathon",
        "course_id": "lydd-half",
        "distance_m": 21097,
        "baseline_event_id": "eventrac:21723",
        "pace_unit": "seconds_per_kilometre",
        "editions": [
            {
                "event_id": "eventrac:21723",
                "year": 2022,
                "started_at_utc": "2022-03-06T10:00:00Z",
                "comparison_status": "comparable",
                "finishers": 189,
                "pace": {
                    "median_s_per_km": 329.6,
                    "mean_s_per_km": 330.8,
                    "p25_s_per_km": 283.3,
                    "p75_s_per_km": 375.9,
                    "fastest_n": 20,
                    "fastest_n_median_s_per_km": 234.8,
                },
                "weather": {
                    "matched_finishers": 189,
                    "coverage_fraction": 1.0,
                    "coverage_status": "complete",
                    "median_temperature_c": 5.8,
                    "median_wind_mps": 7.34,
                    "median_precipitation_mm": 0.0,
                    "median_humidity_pct": 61.0,
                },
                "change_from_baseline": {
                    "median_pace_pct": 0.0,
                    "speed_at_median_duration_pct": 0.0,
                },
            }
        ],
    }


def test_health_check_is_process_only_and_not_cached():
    repository = Repository(error=AssertionError("warehouse must not be checked"))

    result = asyncio.run(request(repository, "/health"))

    assert result.status_code == 200
    assert result.json() == {"status": "ok"}
    assert result.headers["cache-control"] == "no-store"
    assert repository.requests == []


def test_unknown_course_is_404_without_internal_detail():
    result = asyncio.run(
        request(
            Repository(error=UnknownCourseError("private")),
            "/api/courses/private/comparison",
        )
    )

    assert result.status_code == 404
    assert result.json() == {"detail": "course not found"}
    assert result.headers["cache-control"] == "no-store"


def test_warehouse_failure_is_503_without_internal_detail():
    result = asyncio.run(
        request(
            Repository(error=ComparisonUnavailableError("credential details")),
            "/api/courses/lydd-half/comparison",
        )
    )

    assert result.status_code == 503
    assert result.json() == {"detail": "comparison data is temporarily unavailable"}
    assert result.headers["cache-control"] == "no-store"


def test_production_service_dispatches_the_bigquery_reader_off_the_event_loop(
    monkeypatch,
):
    calls = []
    repository = Mock()

    async def fake_run_in_threadpool(function, *args):
        calls.append((function, args))
        return response()

    monkeypatch.setattr("runwx.api.app.run_in_threadpool", fake_run_in_threadpool)
    service = ComparisonService(repository)

    result = asyncio.run(service.get_course_comparison("lydd-half"))

    assert result == response()
    assert calls == [(repository.get_course_comparison, ("lydd-half",))]


def test_home_page_serves_the_minimal_comparison_interface():
    result = asyncio.run(request(Repository(), "/"))

    assert result.status_code == 200
    assert result.headers["content-type"].startswith("text/html")
    assert result.headers["cache-control"] == "no-cache"
    assert 'id="course-select"' in result.text
    assert 'id="pace-metric-select"' in result.text
    assert 'id="weather-metric-select"' in result.text
    assert 'id="pace-chart"' in result.text
    assert 'id="weather-chart"' in result.text
    assert 'class="charts-timeline"' in result.text
    assert 'id="comparison-rows"' in result.text
    assert "Simple statistics, fixed historical snapshots, no prediction." in result.text
    assert 'src="http' not in result.text
    assert 'href="http' not in result.text


def test_frontend_assets_are_local_packaged_and_cache_bounded():
    stylesheet = asyncio.run(request(Repository(), "/assets/styles.css"))
    javascript = asyncio.run(request(Repository(), "/assets/app.js"))

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert stylesheet.headers["cache-control"] == "public, max-age=3600"
    assert "--accent: #176b4c" in stylesheet.text
    assert "@media (max-width: 720px)" in stylesheet.text

    assert javascript.status_code == 200
    assert javascript.headers["content-type"].startswith("text/javascript")
    assert javascript.headers["cache-control"] == "public, max-age=3600"
    assert "/api/courses/" in javascript.text
    assert "median-pace" in javascript.text
    assert "precipitation" in javascript.text
    assert "renderCharts" in javascript.text
    assert "textContent" in javascript.text
    assert "innerHTML" not in javascript.text
