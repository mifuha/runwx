from __future__ import annotations

"""
Backward-compatible re-exports for weather alignment utilities.

Tests and older code import from ``runwx.align``; the implementations now live
in ``runwx.domain.align``.
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

