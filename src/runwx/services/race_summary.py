from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Sequence

from runwx.domain.race import RaceResult


@dataclass(frozen=True)
class EventSummary:
    finisher_count: int
    mean_duration_s: float
    median_duration_s: float
    best_duration_s: int
    top_n_median_duration_s: float


def summarize_results(
    results: Sequence[RaceResult],
    *,
    top_n: int = 20,
) -> EventSummary:
    if not results:
        raise ValueError("results must not be empty")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    sorted_results = sorted(results, key=lambda r: r.duration_s)
    durations = [r.duration_s for r in sorted_results]

    # If `top_n` exceeds the number of results, we treat it as "all results"
    # (because slicing naturally clamps; this just makes the intent explicit).
    top_n_effective = min(top_n, len(durations))
    top_slice = durations[:top_n_effective]

    return EventSummary(
        finisher_count=len(durations),
        mean_duration_s=mean(durations),
        median_duration_s=median(durations),
        best_duration_s=durations[0],
        top_n_median_duration_s=median(top_slice),
    )