from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from runwx.models import Run, WeatherObs


@dataclass(frozen=True)
class WeatherIndex:
    observed_at: tuple[datetime, ...]
    observations: tuple[WeatherObs, ...]


def run_anchor_time(run: Run) -> datetime:
    """Return the midpoint time of the run."""
    return run.started_at + timedelta(seconds=run.duration_s / 2.0)


def build_weather_index(observations: Sequence[WeatherObs]) -> WeatherIndex:
    """
    Sort observations once and keep parallel timestamp data
    for fast nearest-neighbour lookup.
    """
    obs_sorted = tuple(sorted(observations, key=lambda obs: obs.observed_at))
    return WeatherIndex(
        observed_at=tuple(obs.observed_at for obs in obs_sorted),
        observations=obs_sorted,
    )


def nearest_weather(
    run: Run,
    observations: Sequence[WeatherObs] | WeatherIndex,
    *,
    max_gap: timedelta = timedelta(minutes=30),
) -> WeatherObs | None:
    """
    Return the WeatherObs closest in time to the run's anchor time.
    If the closest observation is farther than max_gap away, return None.

    Accepts either:
      - a plain sequence of WeatherObs, or
      - a prebuilt WeatherIndex for repeated fast lookups.
    """
    index = observations if isinstance(observations, WeatherIndex) else build_weather_index(observations)

    if not index.observations:
        return None

    anchor = run_anchor_time(run)
    pos = bisect_left(index.observed_at, anchor)

    candidates: list[WeatherObs] = []

    if pos < len(index.observations):
        candidates.append(index.observations[pos])

    if pos > 0:
        candidates.append(index.observations[pos - 1])

    if not candidates:
        return None

    best = min(
        candidates,
        key=lambda obs: (abs(obs.observed_at - anchor), obs.observed_at),
    )

    if abs(best.observed_at - anchor) > max_gap:
        return None

    return best


