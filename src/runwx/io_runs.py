from __future__ import annotations

"""
Backward-compatible re-export for CSV run loading.

Older code uses ``runwx.io_runs.load_runs_csv``; the implementation now lives
in ``runwx.adapters.csv.io_runs``.
"""

from runwx.adapters.csv.io_runs import load_runs_csv

__all__ = ["load_runs_csv"]

