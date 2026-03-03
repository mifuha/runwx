from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from runwx.models import Run, WeatherObs


def _normalize_z_suffix(value):
    if isinstance(value, str) and value.endswith("Z"):
        return value[:-1] + "+00:00"
    return value


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    duration_s: int = Field(gt=0)
    distance_m: int = Field(gt=0)

    @field_validator("started_at", mode="before")
    @classmethod
    def normalize_started_at(cls, value):
        return _normalize_z_suffix(value)

    @field_validator("started_at")
    @classmethod
    def require_timezone_aware_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    def to_domain(self) -> Run:
        return Run(
            started_at=self.started_at,
            duration_s=self.duration_s,
            distance_m=self.distance_m,
        )


class WeatherObsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    temp_c: float
    wind_mps: float = Field(ge=0)
    precipitation_mm: float = Field(ge=0)
    humidity_pct: float = Field(ge=0, le=100)

    @field_validator("observed_at", mode="before")
    @classmethod
    def normalize_observed_at(cls, value):
        return _normalize_z_suffix(value)

    @field_validator("observed_at")
    @classmethod
    def require_timezone_aware_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return value

    def to_domain(self) -> WeatherObs:
        return WeatherObs(
            observed_at=self.observed_at,
            temp_c=self.temp_c,
            wind_mps=self.wind_mps,
            precipitation_mm=self.precipitation_mm,
            humidity_pct=self.humidity_pct,
        )