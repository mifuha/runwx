from __future__ import annotations

from datetime import timedelta, timezone
from typing import Sequence

from runwx.adapters.weather.open_meteo import OpenMeteoClient
from runwx.domain.align import run_anchor_time
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
    Fetch UTC dates covering every midpoint +/- max_gap, then delegate
    alignment/enrichment to the generic pipeline. Reject a negative gap
    before requesting weather.
    """
    if max_gap < timedelta(0):
        raise ValueError("max_gap must be non-negative")

    if not runs:
        return PipelineResult(enriched=(), skipped=())

    client = client or OpenMeteoClient()

    anchors_utc = [run_anchor_time(run).astimezone(timezone.utc) for run in runs]
    start_date = (min(anchors_utc) - max_gap).date()
    end_date = (max(anchors_utc) + max_gap).date()

    weather = client.fetch_weather_obs(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
    )

    return enrich_runs(runs, weather, max_gap=max_gap)