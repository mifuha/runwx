from __future__ import annotations

"""
Backward-compatible re-exports for the enrichment pipeline.

Tests and callers import ``runwx.pipeline.enrich_runs`` and related types.
The implementations now live in ``runwx.services.pipeline``.
"""

from runwx.services.pipeline import PipelineResult, SkippedRun, enrich_runs

__all__ = ["PipelineResult", "SkippedRun", "enrich_runs"]

