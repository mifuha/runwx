import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from runwx.models import Run, WeatherObs


def test_run_valid():
    started_at = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    run = Run(started_at=started_at, duration_s=3600, distance_m=10_000)
    assert run.started_at == started_at
    assert run.duration_s == 3600
    assert run.distance_m == 10_000


def test_run_requires_timezone_aware_datetime():
    started_at = datetime(2026, 1, 15, 10, 30)  # naive
    with pytest.raises(ValueError, match="started_at must be timezone-aware"):
        Run(started_at=started_at, duration_s=3600, distance_m=10_000)


def test_run_duration_must_be_positive():
    started_at = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="duration_s must be positive"):
        Run(started_at=started_at, duration_s=0, distance_m=10_000)

    with pytest.raises(ValueError, match="duration_s must be positive"):
        Run(started_at=started_at, duration_s=-1, distance_m=10_000)


def test_run_distance_must_be_positive():
    started_at = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="distance_m must be positive"):
        Run(started_at=started_at, duration_s=3600, distance_m=0)

    with pytest.raises(ValueError, match="distance_m must be positive"):
        Run(started_at=started_at, duration_s=3600, distance_m=-5)


def test_run_is_frozen():
    started_at = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    run = Run(started_at=started_at, duration_s=3600, distance_m=10_000)

    with pytest.raises(FrozenInstanceError):
        run.duration_s = 7200


def test_weather_obs_valid():
    observed_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    obs = WeatherObs(observed_at=observed_at, temp_c=15.5, wind_mps=5.2, precipitation_mm=0.0)
    assert obs.observed_at == observed_at
    assert obs.temp_c == 15.5
    assert obs.wind_mps == 5.2
    assert obs.precipitation_mm == 0.0


def test_weather_obs_requires_timezone_aware_datetime():
    observed_at = datetime(2026, 1, 15, 12, 0)  # naive
    with pytest.raises(ValueError, match="observed_at must be timezone-aware"):
        WeatherObs(observed_at=observed_at, temp_c=15.5, wind_mps=5.2, precipitation_mm=0.0)


def test_weather_obs_negative_temp_allowed():
    observed_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    obs = WeatherObs(observed_at=observed_at, temp_c=-10.0, wind_mps=0.0, precipitation_mm=0.0)
    assert obs.temp_c == -10.0


def test_weather_obs_wind_must_be_non_negative():
    observed_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="wind_mps must be non-negative"):
        WeatherObs(observed_at=observed_at, temp_c=10.0, wind_mps=-0.1, precipitation_mm=0.0)


def test_weather_obs_precipitation_must_be_non_negative():
    observed_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="precipitation_mm must be non-negative"):
        WeatherObs(observed_at=observed_at, temp_c=10.0, wind_mps=0.0, precipitation_mm=-0.1)


def test_weather_obs_is_frozen():
    observed_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    obs = WeatherObs(observed_at=observed_at, temp_c=15.5, wind_mps=5.2, precipitation_mm=0.0)

    with pytest.raises(FrozenInstanceError):
        obs.temp_c = 20.0