import pytest
from datetime import datetime, timezone

from runwx.domain.models import Run, WeatherObs
from runwx.domain.enrich import RunWithWeather
from runwx.services.event_weather_summary import (
    EventWeatherSummary,
    summarize_event_weather,
)


def make_run_with_weather(duration_s: int, temp_c: float, wind_mps: float, humidity_pct: float, precipitation_mm: float):
    run = Run(
        started_at=datetime(2024, 10, 6, 9, 0, tzinfo=timezone.utc),
        duration_s=duration_s,
        distance_m=5000,
    )
    weather = WeatherObs(
        observed_at=datetime(2024, 10, 6, 9, 0, tzinfo=timezone.utc),
        temp_c=temp_c,
        wind_mps=wind_mps,
        precipitation_mm=precipitation_mm,
        humidity_pct=humidity_pct,
    )
    return RunWithWeather(run=run, weather=weather)


def test_summarize_event_weather_computes_medians():
    enriched = [
        make_run_with_weather(1320, 10.0, 2.0, 70.0, 0.0),
        make_run_with_weather(1450, 12.0, 3.0, 75.0, 0.1),
        make_run_with_weather(1505, 11.0, 4.0, 80.0, 0.0),
    ]

    summary = summarize_event_weather(enriched)

    assert summary == EventWeatherSummary(
        enriched_count=3,
        median_temp_c=11.0,
        median_wind_mps=3.0,
        median_humidity_pct=75.0,
        median_precipitation_mm=0.0,
    )


def test_summarize_event_weather_rejects_empty_input():
    with pytest.raises(ValueError, match="enriched must not be empty"):
        summarize_event_weather([])