from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from runwx.adapters.weather.open_meteo import OpenMeteoClient
from runwx.domain.race import RaceEvent, RaceResult
from runwx.services.event_weather_summary import (
    EventWeatherSummary,
    summarize_event_weather,
)
from runwx.services.pipeline import PipelineResult
from runwx.services.race_pipeline import enrich_race_results_with_open_meteo
from runwx.services.race_summary import EventSummary, summarize_results


@dataclass(frozen=True)
class RaceAnalysis:
    event: RaceEvent
    summary: EventSummary
    weather_summary: EventWeatherSummary
    pipeline_result: PipelineResult


def analyze_race_event(
    event: RaceEvent,
    results: Sequence[RaceResult],
    *,
    client: OpenMeteoClient | None = None,
    top_n: int = 20,
    max_gap: timedelta = timedelta(minutes=30),
) -> RaceAnalysis:
    summary = summarize_results(results, top_n=top_n)
    pipeline_result = enrich_race_results_with_open_meteo(
        event,
        results,
        client=client,
        max_gap=max_gap,
    )
    weather_summary = summarize_event_weather(pipeline_result.enriched)

    return RaceAnalysis(
        event=event,
        summary=summary,
        weather_summary=weather_summary,
        pipeline_result=pipeline_result,
    )