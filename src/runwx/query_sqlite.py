from __future__ import annotations

"""
Backward-compatible re-exports for SQLite query helpers.

Tests import from ``runwx.query_sqlite``; the implementations now live in
``runwx.adapters.sqlite.query_sqlite``.
"""

from runwx.adapters.sqlite.query_sqlite import EnrichedRow, fetch_latest_enriched

__all__ = ["EnrichedRow", "fetch_latest_enriched"]

