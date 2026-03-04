from __future__ import annotations

from datetime import timedelta, timezone
from typing import Sequence

from runwx.adapters.weather.open_meteo import OpenMeteoClient
from runwx.domain.models import Run
from runwx.services.pipeline import PipelineResult, enrich_runs


def enrich_runs_with_open_meteo(
    runs: Sequence[Run],
    *,
    latitude: float,
    longitude: float,
    client: OpenMeteoClient | None = None,
    max_gap: timedelta = timedelta(minutes=30),
) -> PipelineResult:
    """
    Fetch weather from Open-Meteo for the overall run date range, then
    delegate alignment/enrichment to the generic pipeline.
    """
    if not runs:
        return PipelineResult(enriched=(), skipped=())

    client = client or OpenMeteoClient()

    started_ats_utc = [run.started_at.astimezone(timezone.utc) for run in runs]
    start_date = min(started_ats_utc).date()
    end_date = max(started_ats_utc).date()

    weather = client.fetch_weather_obs(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
    )

    return enrich_runs(runs, weather, max_gap=max_gap)