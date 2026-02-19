import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from runwx.enrich import RunWithWeather, attach_weather
from runwx.models import Run, WeatherObs


def test_attach_weather_returns_run_with_weather():
    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,
        distance_m=10_000,
    )
    weather = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 30, tzinfo=timezone.utc),
        temp_c=10.0,
        wind_mps=2.0,
        precipitation_mm=0.0,
    )

    enriched = attach_weather(run, weather)

    assert isinstance(enriched, RunWithWeather)
    assert enriched.run == run
    assert enriched.weather == weather


def test_run_with_weather_is_frozen():
    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,
        distance_m=10_000,
    )
    weather = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 30, tzinfo=timezone.utc),
        temp_c=10.0,
        wind_mps=2.0,
        precipitation_mm=0.0,
    )

    enriched = RunWithWeather(run=run, weather=weather)

    with pytest.raises(FrozenInstanceError):
        enriched.run = run
