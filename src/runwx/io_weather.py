from __future__ import annotations

"""
Backward-compatible re-export for CSV weather loading.

Older code uses ``runwx.io_weather.load_weather_csv``; the implementation now
lives in ``runwx.adapters.csv.io_weather``.
"""

from runwx.adapters.csv.io_weather import load_weather_csv

__all__ = ["load_weather_csv"]

