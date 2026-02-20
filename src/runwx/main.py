from __future__ import annotations

from datetime import datetime, timedelta, timezone

from runwx.models import Run, WeatherObs
from runwx.pipeline import enrich_runs


def demo_data():
    runs = [
        Run(
            started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
            duration_s=3600,
            distance_m=10_000,
        ),
        Run(
            started_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            duration_s=1800,
            distance_m=5_000,
        ),
    ]

    weather = [
        WeatherObs(
            observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc),
            temp_c=6.5,
            wind_mps=4.2,
            precipitation_mm=0.0,
        ),
        WeatherObs(
            observed_at=datetime(2026, 2, 1, 11, 50, tzinfo=timezone.utc),
            temp_c=7.1,
            wind_mps=3.8,
            precipitation_mm=0.2,
        ),
    ]
    return runs, weather


def main() -> None:
    runs, weather = demo_data()
    result = enrich_runs(runs, weather, max_gap=timedelta(minutes=30))

    print(f"Enriched: {len(result.enriched)}")
    for item in result.enriched:
        r = item.run
        w = item.weather
        print(
            f"- run @ {r.started_at.isoformat()} ({r.distance_m}m, {r.duration_s}s)"
            f" -> weather @ {w.observed_at.isoformat()} ({w.temp_c}C, wind {w.wind_mps}m/s, rain {w.precipitation_mm}mm)"
        )

    print(f"\nSkipped: {len(result.skipped)}")
    for s in result.skipped:
        print(f"- run @ {s.run.started_at.isoformat()} -> {s.reason}")


if __name__ == "__main__":
    main()