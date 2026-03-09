from __future__ import annotations

import csv
from pathlib import Path

from pydantic import ValidationError

from runwx.adapters.races.schemas import RaceResultIn
from runwx.domain.race import RaceResult


def load_results_csv(path: str | Path, *, event_id: str) -> list[RaceResult]:
    path = Path(path)
    results: list[RaceResult] = []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        required = {"duration_s"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing results CSV columns: {sorted(missing)}")

        for row_num, row in enumerate(reader, start=2):
            try:
                result = RaceResultIn.model_validate(row).to_domain(event_id=event_id)
                results.append(result)
            except ValidationError as e:
                raise ValueError(f"Invalid results CSV row {row_num}: {e}") from e

    return results