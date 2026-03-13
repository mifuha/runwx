from datetime import datetime, timedelta, timezone

from runwx.domain.align import build_weather_index, nearest_weather
from runwx.domain.models import Run, WeatherObs


def test_nearest_weather_empty_list_returns_none():
    run = Run(
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,
        distance_m=10_000,
    )
    assert nearest_weather(run, []) is None


def test_nearest_weather_picks_closest_observation():
    run = Run(
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,
        distance_m=10_000,
    )
    # midpoint is 10:30
    obs1 = WeatherObs(
        observed_at=datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc),
        temp_c=10.0,
        wind_mps=1.0,
        precipitation_mm=0.0,
        humidity_pct=70.0,
    )
    obs2 = WeatherObs(
        observed_at=datetime(2026, 1, 1, 10, 35, tzinfo=timezone.utc),
        temp_c=11.0,
        wind_mps=1.0,
        precipitation_mm=0.0,
        humidity_pct=75.0,
    )
    assert nearest_weather(run, [obs1, obs2]) == obs2


def test_nearest_weather_respects_max_gap():
    run = Run(
        started_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,
        distance_m=10_000,
    )
    obs = WeatherObs(
        observed_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        temp_c=10.0,
        wind_mps=1.0,
        precipitation_mm=0.0,
        humidity_pct=60.0,
    )
    assert nearest_weather(run, [obs], max_gap=timedelta(minutes=30)) is None


def test_nearest_weather_with_prebuilt_index():
    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,  # midpoint 10:30
        distance_m=10_000,
    )

    observations = [
        WeatherObs(
            observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc),
            temp_c=6.5,
            wind_mps=4.2,
            precipitation_mm=0.0,
            humidity_pct=80.0,
        ),
        WeatherObs(
            observed_at=datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc),
            temp_c=7.0,
            wind_mps=3.5,
            precipitation_mm=0.1,
            humidity_pct=75.0,
        ),
    ]

    index = build_weather_index(observations)
    result = nearest_weather(run, index, max_gap=timedelta(minutes=30))

    assert result is not None
    assert result.observed_at == datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc)


def test_nearest_weather_tie_breaks_to_earlier_observation():
    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,  # midpoint 10:30
        distance_m=10_000,
    )

    earlier = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc),
        temp_c=6.5,
        wind_mps=4.2,
        precipitation_mm=0.0,
        humidity_pct=80.0,
    )
    later = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 40, tzinfo=timezone.utc),
        temp_c=7.1,
        wind_mps=3.8,
        precipitation_mm=0.2,
        humidity_pct=75.0,
    )

    result = nearest_weather(run, [later, earlier], max_gap=timedelta(minutes=30))

    assert result == earlier


def test_nearest_weather_with_prebuilt_index_respects_max_gap():
    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,  # midpoint 10:30
        distance_m=10_000,
    )

    observations = [
        WeatherObs(
            observed_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            temp_c=8.0,
            wind_mps=2.0,
            precipitation_mm=0.0,
            humidity_pct=60.0,
        ),
    ]

    index = build_weather_index(observations)
    result = nearest_weather(run, index, max_gap=timedelta(minutes=30))

    assert result is None
