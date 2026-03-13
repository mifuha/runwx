from __future__ import annotations

"""
Compatibility alias for SQLite storage helpers.

Canonical module: ``runwx.adapters.sqlite.storage_sqlite``.
"""

from runwx.adapters.sqlite.storage_sqlite import (
    connect,
    init_db,
    write_enriched,
    write_pipeline_result,
)

__all__ = ["connect", "init_db", "write_enriched", "write_pipeline_result"]

