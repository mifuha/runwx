from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Run:
    """A single running activity."""
    started_at: datetime
    duration_s: int
    distance_m: int

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC recommended)")
        if self.duration_s <= 0:
            raise ValueError("duration_s must be positive")
        if self.distance_m <= 0:
            raise ValueError("distance_m must be positive")


@dataclass(frozen=True)
class WeatherObs:
    """A weather observation at a specific point in time."""
    observed_at: datetime
    temp_c: float
    wind_mps: float
    precipitation_mm: float

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware (UTC recommended)")
