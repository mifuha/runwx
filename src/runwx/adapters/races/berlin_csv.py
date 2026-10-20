"""Read the pinned anonymous Berlin CSV without inventing places or identities."""

import csv
from importlib.resources import files
import json
from pathlib import Path
import re

from runwx.domain.race import RaceResult

CATALOG = json.loads(files(__package__).joinpath("berlin_editions.json").read_bytes())


def validate_reported_result(time_raw: str, gender_raw: str):
    """Return the duration or held reason used by preparation and load preflight."""
    match = re.fullmatch(r"([0-9]{1,3}):([0-5][0-9]):([0-5][0-9])", time_raw)
    duration = sum(int(v) * k for v, k in zip(match.groups(), (3600, 60, 1))) if match else None
    if not duration:
        return None, "invalid or nonpositive reported duration"
    if gender_raw not in {"male", "female"}:
        return None, "unsupported recorded gender"
    RaceResult(event_id="berlin-research", duration_s=duration, gender=gender_raw)
    return duration, None


def iter_research_rows(path: Path, years: set[int], source_hash: str):
    """Yield every capture row; an unselected year yields no result payload.

    Record numbers count CSV data records, not athletes, official places or
    physical lines. Identical anonymous rows must keep distinct locators.
    """
    try:
        yield from _read_rows(path, years, source_hash)
    except csv.Error as exc:
        raise ValueError(f"malformed Berlin CSV: {exc}") from exc


def _read_rows(path: Path, years: set[int], source_hash: str):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        if next(reader, None) != CATALOG["columns"]:
            raise ValueError("Berlin CSV columns differ from the reviewed source")
        for number, raw in enumerate(reader, 1):
            if len(raw) != 5 or re.fullmatch(r"[0-9]{4}", raw[0]) is None:
                raise ValueError(f"CSV record {number}: malformed columns or year")
            year = int(raw[0])
            if year not in years:
                yield year, None
                continue
            duration, reason = validate_reported_result(raw[4], raw[2])
            yield year, {
                "source_row_number": number,
                "source_row_id": f"berlin-kaggle-v2:{source_hash}:{number}",
                "race_date": CATALOG["editions"][str(year)]["date"],
                "country_raw": raw[1], "gender_raw": raw[2],
                "age_category_raw": raw[3], "time_raw": raw[4],
                "duration_s": duration if reason is None else None,
                "place": None, "age": None, "timing_basis": None,
                "validation_status": "accepted" if reason is None else "held",
                "validation_reason": reason,
            }
