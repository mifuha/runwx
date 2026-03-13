from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from runwx.domain.models import Run


@dataclass(frozen=True)
class RaceEvent:
    """
    A specific race event on a specific date/course.

    We keep this separate from Run so we can control for "same course over time"
    and use location/time for weather enrichment.
    """
    source: str                # e.g. "runsignup", "parkrun"
    source_event_id: str       # provider-specific id / slug
    name: str
    started_at: datetime       # timezone-aware (UTC recommended)
    distance_m: int
    latitude: float
    longitude: float
    course_id: str | None = None  # optional stable course key if you have it

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source must be non-empty")
        if not self.source_event_id.strip():
            raise ValueError("source_event_id must be non-empty")
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC recommended)")
        if self.distance_m <= 0:
            raise ValueError("distance_m must be positive")
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError("longitude must be between -180 and 180")

    @property
    def event_id(self) -> str:
        # stable internal identifier
        return f"{self.source}:{self.source_event_id}"

    @property
    def started_at_utc(self) -> datetime:
        return self.started_at.astimezone(timezone.utc)


@dataclass(frozen=True)
class RaceResult:
    """
    One finisher’s result for a RaceEvent.

    Keep athlete_id optional and anonymized (hash) if available.
    """
    event_id: str
    duration_s: int
    athlete_id: str | None = None
    place: int | None = None
    age: int | None = None
    gender: str | None = None  # keep loose for now

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if self.duration_s <= 0:
            raise ValueError("duration_s must be positive")
        if self.place is not None and self.place <= 0:
            raise ValueError("place must be positive if provided")
        if self.age is not None and not (0 < self.age < 130):
            raise ValueError("age must be between 1 and 129 if provided")

    def to_run(self, event: RaceEvent) -> Run:
        """
        Normalize race result into a Run record for existing pipeline reuse.
        """
        if event.event_id != self.event_id:
            raise ValueError(f"event mismatch: result={self.event_id} event={event.event_id}")

        return Run(
            started_at=event.started_at_utc,
            duration_s=self.duration_s,
            distance_m=event.distance_m,
        )