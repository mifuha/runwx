from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Sequence

from runwx.domain.enrich import RunWithWeather


@dataclass(frozen=True)
class EventWeatherSummary:
    enriched_count: int
    median_temp_c: float
    median_wind_mps: float
    median_humidity_pct: float
    median_precipitation_mm: float


def summarize_event_weather(
    enriched: Sequence[RunWithWeather],
) -> EventWeatherSummary:
    if not enriched:
        raise ValueError("enriched must not be empty")

    temps = [item.weather.temp_c for item in enriched]
    winds = [item.weather.wind_mps for item in enriched]
    humidities = [item.weather.humidity_pct for item in enriched]
    precipitations = [item.weather.precipitation_mm for item in enriched]

    return EventWeatherSummary(
        enriched_count=len(enriched),
        median_temp_c=median(temps),
        median_wind_mps=median(winds),
        median_humidity_pct=median(humidities),
        median_precipitation_mm=median(precipitations),
    )