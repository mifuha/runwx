from datetime import datetime, timedelta, timezone

from runwx.models import Run, WeatherObs
from runwx.pipeline import enrich_runs


def test_enrich_runs_enriches_when_weather_within_gap():
    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,   # midpoint 10:30
        distance_m=10_000,
    )
    obs = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc),
        temp_c=6.5,
        wind_mps=4.2,
        precipitation_mm=0.0,
    )

    result = enrich_runs([run], [obs], max_gap=timedelta(minutes=30))

    assert len(result.enriched) == 1
    assert len(result.skipped) == 0
    assert result.enriched[0].run == run
    assert result.enriched[0].weather == obs


def test_enrich_runs_skips_when_no_weather_within_gap():
    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,   # midpoint 10:30
        distance_m=10_000,
    )
    far_obs = WeatherObs(
        observed_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
        temp_c=6.5,
        wind_mps=4.2,
        precipitation_mm=0.0,
    )

    result = enrich_runs([run], [far_obs], max_gap=timedelta(minutes=30))

    assert len(result.enriched) == 0
    assert len(result.skipped) == 1
    assert result.skipped[0].run == run
    assert "No weather within" in result.skipped[0].reason


def test_enrich_runs_mixed_results():
    run_ok = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,   # midpoint 10:30
        distance_m=10_000,
    )
    run_bad = Run(
        started_at=datetime(2026, 2, 1, 13, 0, tzinfo=timezone.utc),
        duration_s=3600,   # midpoint 13:30 (far)
        distance_m=5_000,
    )

    obs_ok = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 25, tzinfo=timezone.utc),
        temp_c=7.0,
        wind_mps=3.0,
        precipitation_mm=0.0,
    )
    obs_far = WeatherObs(
        observed_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
        temp_c=9.0,
        wind_mps=2.0,
        precipitation_mm=0.0,
    )

    result = enrich_runs([run_ok, run_bad], [obs_ok, obs_far], max_gap=timedelta(minutes=20))

    assert len(result.enriched) == 1
    assert len(result.skipped) == 1
    assert result.enriched[0].run == run_ok
    assert result.skipped[0].run == run_bad