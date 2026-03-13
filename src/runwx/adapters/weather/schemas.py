from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class OpenMeteoHourly(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time: list[str]
    temperature_2m: list[float]
    relative_humidity_2m: list[float]
    precipitation: list[float]
    wind_speed_10m: list[float]

    @model_validator(mode="after")
    def validate_equal_lengths(self) -> "OpenMeteoHourly":
        lengths = {
            "time": len(self.time),
            "temperature_2m": len(self.temperature_2m),
            "relative_humidity_2m": len(self.relative_humidity_2m),
            "precipitation": len(self.precipitation),
            "wind_speed_10m": len(self.wind_speed_10m),
        }

        if len(set(lengths.values())) != 1:
            raise ValueError(f"Hourly arrays must all be the same length, got: {lengths}")

        return self


class OpenMeteoArchiveResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latitude: float
    longitude: float
    timezone: str
    utc_offset_seconds: int
    hourly: OpenMeteoHourly