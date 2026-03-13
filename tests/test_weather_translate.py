from __future__ import annotations

from datetime import datetime, timezone

from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse
from runwx.adapters.weather.translate import to_weather_obs


def test_to_weather_obs_maps_openmeteo_hourly_response():
    payload = {
        "latitude": 51.5,
        "longitude": -0.1,
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "hourly": {
            "time": ["2026-02-01T10:00", "2026-02-01T11:00"],
            "temperature_2m": [7.2, 7.6],
            "wind_speed_10m": [3.1, 3.4],
            "precipitation": [0.0, 0.2],
            "relative_humidity_2m": [80.0, 78.0],
        },
    }

    resp = OpenMeteoArchiveResponse.model_validate(payload)
    obs = to_weather_obs(resp)

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