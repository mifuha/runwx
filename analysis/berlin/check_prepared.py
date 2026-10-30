"""Separate export-reader check; deliberately does not import the pilot/parser."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


def histogram_median(counts):
    total = sum(counts.values())
    if not total:
        return None
    positions = ((total - 1) // 2, total // 2)
    found, running = [], 0
    for value, count in sorted(counts.items()):
        for position in positions:
            if running <= position < running + count:
                found.append(value)
        running += count
    if len(found) != 2:
        raise ValueError("independent median positions do not reconcile")
    return sum(found) / 2


def read_capture(path, expected_hash):
    digest = sha256()
    groups = {key: Counter() for key in ("female", "male")}
    outcomes = Counter()
    with Path(path).open("rb") as source:
        for number, raw in enumerate(source, 1):
            digest.update(raw)
            row = json.loads(raw)
            gender = row["gender_raw"]
            if gender not in groups:
                raise ValueError(f"capture line {number}: unreviewed recorded gender")
            outcome = row["validation_status"]
            if outcome not in {"accepted", "held"}:
                raise ValueError(f"capture line {number}: unknown outcome")
            outcomes[outcome] += 1
            if outcome == "held":
                if row["duration_s"] is not None:
                    raise ValueError("held capture has a usable duration")
                continue
            # Parse the saved time independently of runwx's shared race parser.
            parts = row["time_raw"].split(":")
            if len(parts) != 3 or not all(part.isascii() and part.isdigit() for part in parts):
                raise ValueError("accepted capture has an unusable reported time")
            hours, minutes, seconds = map(int, parts)
            duration = hours * 3600 + minutes * 60 + seconds
            if not (duration > 0 and minutes < 60 and seconds < 60
                    and type(row["duration_s"]) is int and duration == row["duration_s"]):
                raise ValueError("capture duration differs from its reported time")
            groups[gender][duration] += 1
    if digest.hexdigest() != expected_hash:
        raise ValueError(f"{Path(path).name}: prepared capture hash changed")
    return groups, outcomes


def verify(entries, primary_groups, reports):
    result = []
    for entry in entries:
        year = entry["year"]
        groups, outcomes = read_capture(entry["capture"], entry["capture_sha256"])
        report = reports[year]
        if (outcomes["accepted"] != report["accepted_count"]
                or outcomes["held"] != report["held_count"]):
            raise ValueError(f"{year}: independent capture outcomes differ")
        for gender in ("female", "male"):
            if groups[gender] != Counter(primary_groups[year][gender]):
                raise ValueError(f"{year} {gender}: raw CSV/export distributions differ")
        combined = groups["female"] + groups["male"]
        result.append({"year": year, "accepted_count": outcomes["accepted"],
                       "held_count": outcomes["held"],
                       "groups": {key: {"count": sum(counts.values()),
                                        "median_duration_s": histogram_median(counts)}
                                  for key, counts in {"all": combined, **groups}.items()}})
    return {"status": "matched", "basis": "Separate reader of hash-verified prepared NDJSON; direct time parsing and histogram order statistics; no pilot aggregation calls.",
            "edition_count": len(result), "editions": result}
