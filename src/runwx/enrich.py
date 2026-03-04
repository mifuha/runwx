from __future__ import annotations

"""
Backward-compatible re-exports for enrichment utilities.

Tests and older code import from ``runwx.enrich``; the implementations now live
in ``runwx.domain.enrich``.
"""

from runwx.domain.enrich import RunWithWeather, attach_weather

__all__ = ["RunWithWeather", "attach_weather"]

