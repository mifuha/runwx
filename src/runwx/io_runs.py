from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

from runwx.io_common import parse_datetime_iso, parse_int
from runwx.models import Run


def load_runs_csv(path: str | Path) -> list[Run]:
    """
    Load runs from a CSV file with columns:
      started_at,duration_s,distance_m
    """
    path = Path(path)
    runs: list[Run] = []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        required = {"started_at", "duration_s", "distance_m"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing run CSV columns: {sorted(missing)}")

        for row_num, row in enumerate(reader, start=2):  # row 1 = header
            try:
                run = Run(
                    started_at=parse_datetime_iso(row["started_at"]),
                    duration_s=parse_int(row["duration_s"]),
                    distance_m=parse_int(row["distance_m"]),
                )
                runs.append(run)
            except Exception as e:
                raise ValueError(f"Invalid runs CSV row {row_num}: {e}") from e

    return runs