from __future__ import annotations

"""
Backward-compatible re-exports for SQLite storage helpers.

Tests import from ``runwx.storage_sqlite``; the implementations now live in
``runwx.adapters.sqlite.storage_sqlite``.
"""

from runwx.adapters.sqlite.storage_sqlite import (
    connect,
    init_db,
    write_enriched,
    write_pipeline_result,
)

__all__ = ["connect", "init_db", "write_enriched", "write_pipeline_result"]

