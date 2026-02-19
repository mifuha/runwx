from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from runwx.models import Run, WeatherObs


def run_anchor_time(run: Run) -> datetime:
    """
    Use midpoint of run as anchor time.
    """
    return run.started_at + timedelta(seconds=run.duration_s / 2)


def nearest_weather(
    run: Run,
    observations: list[WeatherObs],
    *,
    max_gap: timedelta = timedelta(minutes=30),
) -> Optional[WeatherObs]:
    """
    Return the WeatherObs closest in time to the run's anchor time.
    If the closest observation is farther than max_gap away, return None.
    """
    if not observations:
        return None

    anchor = run_anchor_time(run)

    closest = min(
        observations,
        key=lambda obs: abs(obs.observed_at - anchor),
    )

    if abs(closest.observed_at - anchor) > max_gap:
        return None

    return closest

