from __future__ import annotations

"""
Compatibility alias for weather alignment utilities.

Canonical module: ``runwx.domain.align``.
"""

from runwx.domain.align import (
    WeatherIndex,
    build_weather_index,
    nearest_weather,
    run_anchor_time,
)

__all__ = [
    "WeatherIndex",
    "build_weather_index",
    "nearest_weather",
    "run_anchor_time",
]

