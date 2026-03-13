from __future__ import annotations

"""
Backward-compatible re-exports for CSV input schemas.

Tests and IO adapters expect ``runwx.schemas.RunIn`` / ``WeatherObsIn``.
The concrete models live in ``runwx.adapters.csv.schemas``.
"""

from runwx.adapters.csv.schemas import RunIn, WeatherObsIn

__all__ = ["RunIn", "WeatherObsIn"]

