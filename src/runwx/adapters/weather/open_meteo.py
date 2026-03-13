from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

import httpx

from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse
from runwx.adapters.weather.translate import to_weather_obs
from runwx.domain.models import WeatherObs

BASE_URL: Final = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_FIELDS: Final[list[str]] = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
]


@dataclass
class OpenMeteoClient:
    timeout_s: float = 10.0

    def fetch_hourly(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> OpenMeteoArchiveResponse:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(HOURLY_FIELDS),
            "timezone": "UTC",
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            response = client.get(BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        return OpenMeteoArchiveResponse.model_validate(payload)

    def fetch_weather_obs(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> list[WeatherObs]:
        resp = self.fetch_hourly(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
        )
        return to_weather_obs(resp)
