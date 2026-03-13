from __future__ import annotations

from datetime import date, datetime, timezone

from runwx.adapters.weather.open_meteo import OpenMeteoClient
from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse


def test_fetch_weather_obs_returns_translated_weather_obs(monkeypatch):
    payload = {
        "latitude": 51.5,
        "longitude": -0.1,
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "hourly": {
            "time": ["2026-02-01T10:00", "2026-02-01T11:00"],
            "temperature_2m": [7.2, 7.6],
            "relative_humidity_2m": [80.0, 78.0],
            "precipitation": [0.0, 0.2],
            "wind_speed_10m": [3.1, 3.4],
        },
    }
    response = OpenMeteoArchiveResponse.model_validate(payload)

    called = {}

    def fake_fetch_hourly(self, *, latitude, longitude, start_date, end_date):
        called["args"] = (latitude, longitude, start_date, end_date)
        return response

    monkeypatch.setattr(OpenMeteoClient, "fetch_hourly", fake_fetch_hourly)

    client = OpenMeteoClient(timeout_s=5.0)
    obs = client.fetch_weather_obs(
        latitude=51.5,
        longitude=-0.1,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )

    assert called["args"] == (
        51.5,
        -0.1,
        date(2026, 2, 1),
        date(2026, 2, 1),
    )

    assert len(obs) == 2

    assert obs[0].observed_at == datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    assert obs[0].temp_c == 7.2
    assert obs[0].wind_mps == 3.1
    assert obs[0].precipitation_mm == 0.0
    assert obs[0].humidity_pct == 80.0

    assert obs[1].observed_at == datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc)
    assert obs[1].temp_c == 7.6
    assert obs[1].wind_mps == 3.4
    assert obs[1].precipitation_mm == 0.2
    assert obs[1].humidity_pct == 78.0