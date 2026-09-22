"""Parse a frozen bundle of original Sporthive race and participant responses."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from pydantic import ValidationError

from runwx.adapters.races.outcomes import InvalidRaceRow, RaceParseResult, SkippedRaceRow
from runwx.adapters.races.schemas import RaceEventIn, RaceResultIn


def _duration_seconds(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError("duration must be a string")
    match = re.fullmatch(r"([0-9]+):([0-9]{2}):([0-9]{2}(?:\.[0-9]+)?)", value.strip())
    if match is None:
        raise ValueError(f"unsupported duration format: {value!r}")
    hours, minutes = int(match[1]), int(match[2])
    try:
        seconds = Decimal(match[3])
    except InvalidOperation as exc:  # defensive: the regular expression is stricter
        raise ValueError(f"unsupported duration format: {value!r}") from exc
    if minutes >= 60 or seconds >= 60:
        raise ValueError("minutes and seconds must be between 0 and 59")
    total = Decimal(hours * 3600 + minutes * 60) + seconds
    return int(total.to_integral_value(rounding=ROUND_CEILING))


def _object(value: object, *, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _positive_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def parse_sporthive_snapshot_json(
    text: str,
    *,
    course_id: str,
    distance_m: int,
    timing_basis: str | None,
) -> RaceParseResult:
    """Validate one complete snapshot before returning row outcomes.

    Event time and location are explicit evidenced metadata in the frozen bundle;
    Sporthive's race `date` is retained but is not treated as a start time.
    """
    if timing_basis not in {"chip", "gun"}:
        raise ValueError("Sporthive timing_basis must be chip or gun")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid Sporthive snapshot JSON") from exc
    payload = _object(payload, name="Sporthive snapshot")
    expected_keys = {"snapshot_schema_version", "event", "race", "pages", "source_responses"}
    if set(payload) != expected_keys:
        raise ValueError(f"Sporthive snapshot keys must be {sorted(expected_keys)}")
    if payload["snapshot_schema_version"] != 1:
        raise ValueError("unsupported Sporthive snapshot schema version")

    event = _object(payload["event"], name="event")
    expected_event_keys = {"source_event_id", "name", "started_at", "latitude", "longitude"}
    if set(event) != expected_event_keys:
        raise ValueError(f"Sporthive event keys must be {sorted(expected_event_keys)}")
    event_in = RaceEventIn.model_validate({
        "source": "sporthive",
        **event,
        "course_id": course_id,
        "distance_m": distance_m,
    })

    race = _object(payload["race"], name="race")
    for key in ("id", "activeEventId", "activeRaceId", "classificationsCount", "distanceInMeter"):
        if key not in race:
            raise ValueError(f"Sporthive race is missing {key}")
    if not isinstance(race["id"], str) or not race["id"]:
        raise ValueError("Sporthive race ID must be non-empty")
    source_event_id = str(race["activeEventId"])
    active_race_id = str(race["activeRaceId"])
    if event_in.source_event_id != source_event_id:
        raise ValueError("Sporthive event identity does not match race metadata")
    expected_rows = _positive_int(race["classificationsCount"], name="classificationsCount")
    provider_distance = _positive_int(race["distanceInMeter"], name="distanceInMeter")

    pages = payload["pages"]
    if not isinstance(pages, list) or not pages:
        raise ValueError("Sporthive pages must be a non-empty list")
    source_responses = payload["source_responses"]
    if not isinstance(source_responses, list) or len(source_responses) != len(pages) + 1:
        raise ValueError("Sporthive source responses must cover the race and every page")
    response_files = set()
    for response in source_responses:
        response = _object(response, name="source response")
        if set(response) != {"file", "requested_url", "sha256"}:
            raise ValueError("Sporthive source response must contain file, requested_url and sha256")
        if not isinstance(response["file"], str) or not response["file"]:
            raise ValueError("Sporthive source response file must be non-empty")
        if response["file"] in response_files:
            raise ValueError("duplicate Sporthive source response file")
        response_files.add(response["file"])
        if (
            not isinstance(response["requested_url"], str)
            or not response["requested_url"].startswith("https://")
        ):
            raise ValueError("Sporthive source response URL must use HTTPS")
        if (
            not isinstance(response["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", response["sha256"]) is None
        ):
            raise ValueError("Sporthive source response SHA-256 must be lowercase hexadecimal")

    accepted: list[RaceResultIn] = []
    accepted_row_numbers: list[int] = []
    skipped: list[SkippedRaceRow] = []
    errors: list[InvalidRaceRow] = []
    participant_ids: set[str] = set()
    row_number = 0
    total_pages = len(pages)
    for page_number, raw_page in enumerate(pages):
        page = _object(raw_page, name=f"page {page_number}")
        if page.get("number") != page_number or page.get("totalPages") != total_pages:
            raise ValueError("Sporthive pages must be complete and ordered from zero")
        if page.get("totalElements") != expected_rows or page.get("first") != (page_number == 0):
            raise ValueError("Sporthive page metadata does not match the complete snapshot")
        if page.get("last") != (page_number == total_pages - 1):
            raise ValueError("Sporthive final-page metadata does not match the complete snapshot")
        content = page.get("content")
        if not isinstance(content, list) or page.get("numberOfElements") != len(content):
            raise ValueError("Sporthive page row count does not match its metadata")
        page_size = _positive_int(page.get("size"), name="page size")
        if len(content) > page_size:
            raise ValueError("Sporthive page contains more rows than its page size")

        for raw_row in content:
            row_number += 1
            row = _object(raw_row, name=f"participant row {row_number}")
            participant_id = row.get("id")
            if not isinstance(participant_id, str) or not participant_id:
                raise ValueError(f"Sporthive row {row_number} has no participant result ID")
            if participant_id in participant_ids:
                raise ValueError("duplicate Sporthive participant result ID")
            participant_ids.add(participant_id)
            if (
                str(row.get("activeEventId")) != source_event_id
                or str(row.get("activeRaceId")) != active_race_id
            ):
                raise ValueError(f"Sporthive row {row_number} belongs to a different event or race")
            if row.get("distanceInMeter") != provider_distance:
                raise ValueError(f"Sporthive row {row_number} has a different provider distance")
            if type(row.get("dns")) is not bool or type(row.get("dsq")) is not bool:
                raise ValueError(f"Sporthive row {row_number} has invalid DNS/DSQ flags")

            if row.get("dns") is True:
                skipped.append(SkippedRaceRow(row_number, "did not start"))
                continue
            if row.get("dsq") is True:
                skipped.append(SkippedRaceRow(row_number, "disqualified"))
                continue

            place_value = row.get("overallPosition")
            duration_value = row.get(
                "chipTimeOfParticipant" if timing_basis == "chip" else "gunTimeOfParticipant"
            )
            safe_values = (str(place_value), str(duration_value))
            try:
                place = _positive_int(place_value, name="finishing place")
                duration_s = _duration_seconds(duration_value)
                result = RaceResultIn(
                    duration_s=duration_s,
                    place=place,
                    gender=row.get("gender"),
                )
            except (ValueError, ValidationError) as exc:
                errors.append(InvalidRaceRow(row_number, f"invalid Sporthive result: {exc}", safe_values))
                continue
            accepted.append(result)
            accepted_row_numbers.append(row_number)

    if row_number != expected_rows:
        raise ValueError(
            f"Sporthive snapshot expected {expected_rows} participant rows, found {row_number}"
        )
    outcome = RaceParseResult(
        event=event_in,
        accepted=tuple(accepted),
        skipped=tuple(skipped),
        errors=tuple(errors),
        accepted_row_numbers=tuple(accepted_row_numbers),
        duration_precision="whole seconds; provider fractions rounded up",
        timing_basis=timing_basis,
    )
    if outcome.candidate_count != row_number:
        raise RuntimeError("Sporthive row outcome counts do not reconcile")
    return outcome
