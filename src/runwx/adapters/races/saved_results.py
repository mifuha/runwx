"""Select the parser for an explicitly identified saved race-result format."""

from __future__ import annotations

from dataclasses import replace

from runwx.adapters.races.eventrac_html import parse_eventrac_results_html
from runwx.adapters.races.outcomes import RaceParseResult
from runwx.adapters.races.sporthive_json import parse_sporthive_snapshot_json


RACE_FORMATS = ("eventrac_html", "sporthive_json")


def parse_saved_race_results(
    data: bytes,
    *,
    race_format: str,
    course_id: str,
    distance_m: int,
    timezone_name: str,
    timing_basis: str | None,
) -> RaceParseResult:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("saved race input must be UTF-8") from exc
    if race_format == "eventrac_html":
        outcome = parse_eventrac_results_html(
            text,
            course_id=course_id,
            distance_m=distance_m,
            timezone_name=timezone_name,
        )
        return replace(outcome, timing_basis=timing_basis)
    if race_format == "sporthive_json":
        return parse_sporthive_snapshot_json(
            text,
            course_id=course_id,
            distance_m=distance_m,
            timing_basis=timing_basis,
        )
    raise ValueError(f"race_format must be one of {', '.join(RACE_FORMATS)}")
