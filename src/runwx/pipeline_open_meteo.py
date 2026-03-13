from __future__ import annotations

"""
Backward-compatible re-export for the Open-Meteo pipeline helper.

Tests import ``runwx.pipeline_open_meteo.enrich_runs_with_open_meteo``.
The implementation now lives in ``runwx.services.pipeline_open_meteo``.
"""

from runwx.services.pipeline_open_meteo import enrich_runs_with_open_meteo

__all__ = ["enrich_runs_with_open_meteo"]

