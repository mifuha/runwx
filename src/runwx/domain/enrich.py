from __future__ import annotations

from dataclasses import dataclass

from runwx.models import Run, WeatherObs


@dataclass(frozen=True)
class RunWithWeather:
    run: Run
    weather: WeatherObs


def attach_weather(run: Run, weather: WeatherObs) -> RunWithWeather:
    """Combine a Run and WeatherObs into a single record for downstream analysis."""
    return RunWithWeather(run=run, weather=weather)
