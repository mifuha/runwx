from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import List, Sequence, Tuple

from runwx.domain.align import build_weather_index, nearest_weather
from runwx.domain.enrich import RunWithWeather, attach_weather
from runwx.domain.models import Run, WeatherObs


@dataclass(frozen=True)
class SkippedRun:
    run: Run
    reason: str


@dataclass(frozen=True)
class PipelineResult:
    enriched: Tuple[RunWithWeather, ...]
    skipped: Tuple[SkippedRun, ...]


def enrich_runs(
    runs: Sequence[Run],
    weather: Sequence[WeatherObs],
    *,
    max_gap: timedelta = timedelta(minutes=30),
) -> PipelineResult:
    """
    Orchestrate: align (nearest_weather) + enrich (attach_weather).
    """
    enriched: List[RunWithWeather] = []
    skipped: List[SkippedRun] = []

    weather_index = build_weather_index(weather)

    for run in runs:
        try:
            w = nearest_weather(run, weather_index, max_gap=max_gap)
            if w is None:
                skipped.append(
                    SkippedRun(run=run, reason=f"No weather within {max_gap}")
                )
                continue

            enriched.append(attach_weather(run, w))

        except Exception as e:
            skipped.append(
                SkippedRun(run=run, reason=f"{type(e).__name__}: {e}")
            )

    return PipelineResult(enriched=tuple(enriched), skipped=tuple(skipped))