from datetime import datetime, timedelta, timezone

from runwx.align import nearest_weather
from runwx.models import Run, WeatherObs


def test_nearest_weather_empty_list_returns_none():
    run = Run(started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), duration_s=3600, distance_m=10_000)
    assert nearest_weather(run, []) is None


def test_nearest_weather_picks_closest_observation():
    run = Run(started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), duration_s=3600, distance_m=10_000)
    # midpoint is 10:30
    obs1 = WeatherObs(observed_at=datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc), temp_c=10.0, wind_mps=1.0, precipitation_mm=0.0)
    obs2 = WeatherObs(observed_at=datetime(2026, 1, 1, 10, 35, tzinfo=timezone.utc), temp_c=11.0, wind_mps=1.0, precipitation_mm=0.0)
    assert nearest_weather(run, [obs1, obs2]) == obs2


def test_nearest_weather_respects_max_gap():
    run = Run(started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), duration_s=3600, distance_m=10_000)
    obs = WeatherObs(observed_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc), temp_c=10.0, wind_mps=1.0, precipitation_mm=0.0)
    assert nearest_weather(run, [obs], max_gap=timedelta(minutes=30)) is None
