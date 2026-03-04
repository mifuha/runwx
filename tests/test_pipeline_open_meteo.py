from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from runwx.models import Run, WeatherObs
from runwx.pipeline_open_meteo import enrich_runs_with_open_meteo


class DummyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float, date, date]] = []

    def fetch_weather_obs(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> list[WeatherObs]:
        self.calls.append((latitude, longitude, start_date, end_date))
        return [
            WeatherObs(
                observed_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
                temp_c=7.2,
                wind_mps=3.1,
                precipitation_mm=0.0,
                humidity_pct=80.0,
            ),
            WeatherObs(
                observed_at=datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc),
                temp_c=7.6,
                wind_mps=3.4,
                precipitation_mm=0.2,
                humidity_pct=78.0,
            ),
        ]


def test_enrich_runs_with_open_meteo_fetches_weather_and_delegates_to_pipeline():
    runs = [
        Run(
            started_at=datetime(2026, 2, 1, 10, 12, tzinfo=timezone.utc),
            duration_s=1800,
            distance_m=5000,
        ),
        Run(
            started_at=datetime(2026, 2, 1, 11, 5, tzinfo=timezone.utc),
            duration_s=2100,
            distance_m=6000,
        ),
    ]
    client = DummyClient()

    result = enrich_runs_with_open_meteo(
        runs,
        latitude=51.5,
        longitude=-0.1,
        client=client,
        max_gap=timedelta(minutes=30),
    )

    assert client.calls == [
        (51.5, -0.1, date(2026, 2, 1), date(2026, 2, 1))
    ]

    assert len(result.enriched) == 2
    assert len(result.skipped) == 0

    assert result.enriched[0].run == runs[0]
    assert result.enriched[0].weather.observed_at == datetime(
        2026, 2, 1, 10, 0, tzinfo=timezone.utc
    )
    assert result.enriched[0].weather.humidity_pct == 80.0

    assert result.enriched[1].run == runs[1]
    assert result.enriched[1].weather.observed_at == datetime(
        2026, 2, 1, 11, 0, tzinfo=timezone.utc
    )
    assert result.enriched[1].weather.humidity_pct == 78.0


def test_enrich_runs_with_open_meteo_returns_empty_result_for_no_runs():
    client = DummyClient()

    result = enrich_runs_with_open_meteo(
        [],
        latitude=51.5,
        longitude=-0.1,
        client=client,
    )

    assert result.enriched == ()
    assert result.skipped == ()
    assert client.calls == []