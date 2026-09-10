from __future__ import annotations

import hashlib
from datetime import timedelta, timezone
from pathlib import Path

from runwx.adapters.csv.io_weather import parse_weather_csv
from runwx.adapters.races.eventrac_html import parse_eventrac_results_html
from runwx.domain.align import build_weather_index, nearest_weather


def build_result_rows(
    race_html: Path,
    weather_csv: Path,
    *,
    course_id: str,
    distance_m: int,
    timezone_name: str,
    max_gap: timedelta = timedelta(minutes=30),
    race_kind: str = "unknown",
    weather_kind: str = "unknown",
    timing_basis: str | None = None,
) -> list[dict]:
    """Export one row per candidate in a saved Eventrac snapshot, in source order.

    Source row IDs identify snapshot rows, not athletes or analysis revisions.
    Build the complete output before the CLI prints anything. Page, weather and
    unexpected processing errors fail the export rather than hiding bad input.
    """
    if max_gap < timedelta(0):
        raise ValueError("max_gap must be non-negative")
    if race_kind not in {"synthetic", "historical", "unknown"}:
        raise ValueError("race_kind must be synthetic, historical or unknown")
    if weather_kind not in {"synthetic", "historical_reanalysis", "unknown"}:
        raise ValueError("weather_kind must be synthetic, historical_reanalysis or unknown")
    if timing_basis not in {None, "chip", "gun"}:
        raise ValueError("timing_basis must be chip, gun or None")

    race_bytes = race_html.read_bytes()
    weather_bytes = weather_csv.read_bytes()
    race_hash = hashlib.sha256(race_bytes).hexdigest()
    weather_hash = hashlib.sha256(weather_bytes).hexdigest()
    parsed = parse_eventrac_results_html(
        race_bytes.decode("utf-8"), course_id=course_id,
        distance_m=distance_m, timezone_name=timezone_name,
    )
    event = parsed.event.to_domain()
    weather_index = build_weather_index(parse_weather_csv(weather_bytes.decode("utf-8")))

    accepted = dict(zip(parsed.accepted_row_numbers, parsed.accepted, strict=True))
    skipped = {row.row_number: row for row in parsed.skipped}
    invalid = {row.row_number: row for row in parsed.errors}
    locators = [*parsed.accepted_row_numbers, *skipped, *invalid]
    if sorted(locators) != list(range(1, parsed.candidate_count + 1)):
        raise RuntimeError("Eventrac source row locators do not reconcile")

    rows = []
    for row_number in range(1, parsed.candidate_count + 1):
        row = {
            "export_schema_version": 1,
            "source_row_id": f"{event.event_id}:{race_hash}:{row_number}",
            "source_row_number": row_number,
            "event_id": event.event_id,
            "source": event.source,
            "source_event_id": event.source_event_id,
            "course_id": event.course_id,
            "started_at_utc": event.started_at_utc.isoformat(),
            "distance_m": event.distance_m,
            "race_sha256": race_hash,
            "weather_sha256": weather_hash,
            "race_kind": race_kind,
            "weather_kind": weather_kind,
            "settings": {
                "course_id_input": course_id,
                "timezone_name": timezone_name,
                "max_gap_seconds": max_gap.total_seconds(),
                "alignment": "nearest observation to run midpoint",
                "tie_break": "earlier observation",
                "duration_precision": "whole seconds; fractions truncated",
                "timing_basis": timing_basis,
            },
            "validation_status": None,
            "validation_reason": None,
            "place": None,
            "duration_s": None,
            "weather_match_status": "not_applicable",
            "weather_match_reason": None,
            "weather": None,
        }
        if row_number in accepted:
            result = accepted[row_number].to_domain(event_id=event.event_id)
            row["validation_status"] = "accepted"
            row["place"] = result.place
            row["duration_s"] = result.duration_s
            # Use the same domain matcher as the existing report pipeline.
            observation = nearest_weather(result.to_run(event), weather_index, max_gap=max_gap)
            if observation is None:
                row["weather_match_status"] = "unmatched"
                row["weather_match_reason"] = f"No weather within {max_gap}"
            else:
                row["weather_match_status"] = "matched"
                row["weather"] = {
                    "observed_at_utc": observation.observed_at.astimezone(timezone.utc).isoformat(),
                    "temp_c": observation.temp_c,
                    "wind_mps": observation.wind_mps,
                    "precipitation_mm": observation.precipitation_mm,
                    "humidity_pct": observation.humidity_pct,
                }
        elif row_number in skipped:
            row["validation_status"] = "skipped"
            row["validation_reason"] = skipped[row_number].reason
        else:
            row["validation_status"] = "invalid"
            row["validation_reason"] = invalid[row_number].reason
        rows.append(row)
    return rows
