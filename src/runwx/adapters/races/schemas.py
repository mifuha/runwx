from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from runwx.domain.race import RaceEvent, RaceResult


def _normalize_z_suffix(value: Any) -> Any:
    if isinstance(value, str) and value.endswith("Z"):
        return value[:-1] + "+00:00"
    return value


def _empty_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class RaceEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    started_at: datetime
    distance_m: int = Field(gt=0)
    latitude: float
    longitude: float
    course_id: str | None = None

    @field_validator("started_at", mode="before")
    @classmethod
    def normalize_started_at(cls, value: Any) -> Any:
        return _normalize_z_suffix(value)

    @field_validator("started_at")
    @classmethod
    def require_tzaware_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    def to_domain(self) -> RaceEvent:
        return RaceEvent(
            source=self.source,
            source_event_id=self.source_event_id,
            name=self.name,
            started_at=self.started_at,
            distance_m=self.distance_m,
            latitude=self.latitude,
            longitude=self.longitude,
            course_id=self.course_id,
        )


class RaceResultIn(BaseModel):
    # allow extra provider columns; we only care about a few in MVP
    model_config = ConfigDict(extra="ignore")

    duration_s: int = Field(gt=0)
    athlete_id: str | None = None
    place: int | None = None
    age: int | None = None
    gender: str | None = None

    @field_validator("athlete_id", "gender", mode="before")
    @classmethod
    def empty_strings_to_none(cls, value: Any) -> Any:
        value = _empty_to_none(value)
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("place", "age", mode="before")
    @classmethod
    def empty_numbers_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)

    def to_domain(self, *, event_id: str) -> RaceResult:
        return RaceResult(
            event_id=event_id,
            duration_s=self.duration_s,
            athlete_id=self.athlete_id,
            place=self.place,
            age=self.age,
            gender=self.gender,
        )