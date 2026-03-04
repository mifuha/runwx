from __future__ import annotations

"""
Backward-compatible re-exports for domain models.

Tests and other code import from ``runwx.models``; the implementations live
in ``runwx.domain.models``.
"""

from runwx.domain.models import Run, WeatherObs

__all__ = ["Run", "WeatherObs"]