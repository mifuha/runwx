from __future__ import annotations

from datetime import datetime, timezone

from runwx.domain.models import WeatherObs
from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse


def _parse_utc(ts: str) -> datetime:
    """
    Open-Meteo returns times like '2026-02-01T10:00' when timezone=UTC.
    Interpret naive timestamps as UTC and ensure timezone awareness.
    """
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def to_weather_obs(resp: OpenMeteoArchiveResponse) -> list[WeatherObs]:
    hourly = resp.hourly

    observations: list[WeatherObs] = []
    for t, temp_c, wind_mps, pr_mm, humidity_pct in zip(
        hourly.time,
        hourly.temperature_2m,
        hourly.wind_speed_10m,
        hourly.precipitation,
        hourly.relative_humidity_2m,
        strict=True,
    ):
        observations.append(
            WeatherObs(
                observed_at=_parse_utc(t),
                temp_c=float(temp_c),
                wind_mps=float(wind_mps),
                precipitation_mm=float(pr_mm),
                humidity_pct=float(humidity_pct),
            )
        )

    return observations
