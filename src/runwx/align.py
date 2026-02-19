from __future__ import annotations

from datetime import datetime, timedelta

from runwx.models import Run, WeatherObs


def run_anchor_time(run: Run) -> datetime:
    """Midpoint time of the run (usually better than start time)."""
    return run.started_at + timedelta(seconds=run.duration_s / 2.0)


def nearest_weather(
    run: Run,
    observations: list[WeatherObs],
    *,
    max_gap: timedelta = timedelta(minutes=30),
) -> WeatherObs | None:
    """
    Return the WeatherObs closest in time to the run's anchor time.
    If closest is farther than max_gap away, return None.
    """
    if not observations:
        return None

    anchor = run_anchor_time(run)

    best: WeatherObs | None = None
    best_delta: timedelta | None = None

    for obs in observations:
        delta = obs.observed_at - anchor
        if delta < timedelta(0):
            delta = -delta  # abs(delta) but faster / clearer for timedelta

        if best is None or delta < best_delta:  # type: ignore[operator]
            best = obs
            best_delta = delta
        elif delta == best_delta:
            # tie-break: pick the earlier observation for deterministic results
            if obs.observed_at < best.observed_at:
                best = obs

    if best_delta is None or best_delta > max_gap:
        return None

    return best


