from datetime import datetime, timezone

import pytest

from runwx.domain.race import RaceEvent
from runwx.services.event_weather_summary import EventWeatherSummary
from runwx.services.pipeline import PipelineResult
from runwx.services.race_analysis import RaceAnalysis
from runwx.services.race_compare import RaceComparisonRow, compare_race_analyses
from runwx.services.race_summary import EventSummary


def make_analysis(
    *,
    source_event_id: str,
    started_at: datetime,
    course_id: str | None,
    median_duration_s: float,
    top_n_median_duration_s: float,
    median_temp_c: float,
    median_wind_mps: float,
    median_humidity_pct: float = 75.0,
    median_precipitation_mm: float = 0.0,
) -> RaceAnalysis:
    event = RaceEvent(
        source="demo",
        source_event_id=source_event_id,
        name="Demo 5K",
        started_at=started_at,
        distance_m=5000,
        latitude=51.5,
        longitude=-0.1,
        course_id=course_id,
    )

    summary = EventSummary(
        finisher_count=100,
        mean_duration_s=median_duration_s,
        median_duration_s=median_duration_s,
        best_duration_s=1200,
        top_n_median_duration_s=top_n_median_duration_s,
    )

    weather_summary = EventWeatherSummary(
        enriched_count=100,
        median_temp_c=median_temp_c,
        median_wind_mps=median_wind_mps,
        median_humidity_pct=median_humidity_pct,
        median_precipitation_mm=median_precipitation_mm,
    )

    return RaceAnalysis(
        event=event,
        summary=summary,
        weather_summary=weather_summary,
        pipeline_result=PipelineResult(enriched=(), skipped=()),
    )


def test_compare_race_analyses_returns_sorted_rows_for_same_course():
    analysis_2024 = make_analysis(
        source_event_id="event-2024",
        started_at=datetime(2024, 10, 6, 9, 0, tzinfo=timezone.utc),
        course_id="brockwell-park-5k",
        median_duration_s=1505.0,
        top_n_median_duration_s=1360.0,
        median_temp_c=11.0,
        median_wind_mps=3.0,
    )
    analysis_2023 = make_analysis(
        source_event_id="event-2023",
        started_at=datetime(2023, 10, 1, 9, 0, tzinfo=timezone.utc),
        course_id="brockwell-park-5k",
        median_duration_s=1540.0,
        top_n_median_duration_s=1390.0,
        median_temp_c=17.0,
        median_wind_mps=5.0,
    )

    rows = compare_race_analyses([analysis_2024, analysis_2023])

    assert rows == [
        RaceComparisonRow(
            event_id="demo:event-2023",
            started_at=datetime(2023, 10, 1, 9, 0, tzinfo=timezone.utc),
            course_id="brockwell-park-5k",
            distance_m=5000,
            finisher_count=100,
            median_duration_s=1540.0,
            top_n_median_duration_s=1390.0,
            median_temp_c=17.0,
            median_wind_mps=5.0,
            median_humidity_pct=75.0,
            median_precipitation_mm=0.0,
        ),
        RaceComparisonRow(
            event_id="demo:event-2024",
            started_at=datetime(2024, 10, 6, 9, 0, tzinfo=timezone.utc),
            course_id="brockwell-park-5k",
            distance_m=5000,
            finisher_count=100,
            median_duration_s=1505.0,
            top_n_median_duration_s=1360.0,
            median_temp_c=11.0,
            median_wind_mps=3.0,
            median_humidity_pct=75.0,
            median_precipitation_mm=0.0,
        ),
    ]


def test_compare_race_analyses_rejects_mixed_course_ids():
    analysis_a = make_analysis(
        source_event_id="event-a",
        started_at=datetime(2023, 10, 1, 9, 0, tzinfo=timezone.utc),
        course_id="brockwell-park-5k",
        median_duration_s=1540.0,
        top_n_median_duration_s=1390.0,
        median_temp_c=17.0,
        median_wind_mps=5.0,
    )
    analysis_b = make_analysis(
        source_event_id="event-b",
        started_at=datetime(2024, 10, 6, 9, 0, tzinfo=timezone.utc),
        course_id="clapham-common-5k",
        median_duration_s=1505.0,
        top_n_median_duration_s=1360.0,
        median_temp_c=11.0,
        median_wind_mps=3.0,
    )

    with pytest.raises(ValueError, match="same course_id"):
        compare_race_analyses([analysis_a, analysis_b])