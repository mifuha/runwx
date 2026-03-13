from __future__ import annotations

import csv
from pathlib import Path

from pydantic import ValidationError

from runwx.models import Run
from runwx.schemas import RunIn


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

        for row_num, row in enumerate(reader, start=2):
            try:
                run = RunIn.model_validate(row).to_domain()
                runs.append(run)
            except ValidationError as e:
                raise ValueError(f"Invalid runs CSV row {row_num}: {e}") from e

    return runs