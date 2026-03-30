from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from runwx.adapters.weather.open_meteo import OpenMeteoClient
from runwx.domain.race import RaceEvent, RaceResult
from runwx.services.pipeline import PipelineResult
from runwx.services.pipeline_open_meteo import enrich_runs_with_open_meteo
from runwx.services.race_convert import results_to_runs


def enrich_race_results_with_open_meteo(
    event: RaceEvent,
    results: Sequence[RaceResult],
    *,
    client: OpenMeteoClient | None = None,
    max_gap: timedelta = timedelta(minutes=30),
) -> PipelineResult:
    runs = results_to_runs(event, results)
    return enrich_runs_with_open_meteo(
        runs,
        latitude=event.latitude,
        longitude=event.longitude,
        client=client,
        max_gap=max_gap,
    )