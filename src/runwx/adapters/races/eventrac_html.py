from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pydantic import ValidationError

from runwx.adapters.races.outcomes import InvalidRaceRow, RaceParseResult, SkippedRaceRow
from runwx.adapters.races.schemas import RaceEventIn, RaceResultIn


# Keep the established provider-specific import names compatible.
SkippedEventracRow = SkippedRaceRow
InvalidEventracRow = InvalidRaceRow
EventracParseResult = RaceParseResult


def load_eventrac_results_html(
    path: str | Path,
    *,
    course_id: str,
    distance_m: int,
    timezone_name: str,
) -> EventracParseResult:
    html = Path(path).read_text(encoding="utf-8")
    return parse_eventrac_results_html(
        html,
        course_id=course_id,
        distance_m=distance_m,
        timezone_name=timezone_name,
    )


def _parse_duration_to_seconds(value: str) -> int:
    text = value.strip()
    if not text:
        raise ValueError("empty duration")

    match = re.fullmatch(r"([0-9]+):([0-9]+):([0-9]+)(?:\.[0-9]+)?", text)
    if match is None:
        raise ValueError(f"unsupported duration format: {value!r}")

    hours, minutes, seconds = (int(part) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError("minutes and seconds must be between 0 and 59")

    # Domain durations use whole seconds; preserve truncation of valid fractions.
    return hours * 3600 + minutes * 60 + seconds


def _extract_source_event_id(soup: BeautifulSoup) -> str:
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        href = canonical["href"]
        match = re.search(r"/results/(\d+)", href)
        if match:
            return match.group(1)

    og_url = soup.find("meta", attrs={"property": "og:url"})
    if og_url and og_url.get("content"):
        match = re.search(r"/results/(\d+)", og_url["content"])
        if match:
            return match.group(1)

    raise ValueError("could not extract Eventrac results id")


def _extract_geo_from_jsonld(soup: BeautifulSoup) -> tuple[float, float]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if not isinstance(payload, dict):
            continue
        location = payload.get("location")
        if not isinstance(location, dict):
            continue
        geo = location.get("geo")
        if not isinstance(geo, dict):
            continue
        latitude = geo.get("latitude")
        longitude = geo.get("longitude")

        if latitude is not None and longitude is not None:
            return float(latitude), float(longitude)

    raise ValueError("could not extract latitude/longitude from JSON-LD")


def _extract_results_heading(soup: BeautifulSoup) -> tuple[str, str]:
    table = soup.find("table", id="results")
    card = table.find_parent("div", class_="card") if table is not None else None
    if card is not None:
        header = card.find("div", class_="card-header", recursive=False)
        title_node = header.find("h5", recursive=False) if header is not None else None
        if title_node is None:
            raise ValueError("could not find Eventrac results title")
        # The current h5 also contains a date and action links; neither is title text.
        title = " ".join(
            text.strip() for text in title_node.find_all(string=True, recursive=False)
            if text.strip()
        )
        date_node = title_node.find("small", recursive=False)
    else:
        title_node = soup.select_one("div.box-header h3.box-title")
        if title_node is None:
            raise ValueError("could not find Eventrac results title")
        title = title_node.get_text(" ", strip=True)
        date_node = soup.select_one("div.box-header small")

    if not title:
        raise ValueError("could not find Eventrac results title")
    if date_node is None:
        raise ValueError("could not find Eventrac results date/time")
    return title, date_node.get_text(" ", strip=True)


def parse_eventrac_results_html(
    html: str,
    *,
    course_id: str,
    distance_m: int,
    timezone_name: str,
) -> EventracParseResult:
    """Give each candidate row one accepted, skipped, or invalid outcome.

    Candidates are rows belonging to the results table with direct td cells,
    excluding thead/tfoot. Numbering starts at 1 in source order. Blank times
    are expected skips; malformed rows are errors. Invalid page structure or
    an absence of candidate rows raises ValueError. All-rejected pages return
    their outcomes so callers can still inspect data quality.
    """
    soup = BeautifulSoup(html, "html.parser")

    results_title, date_text = _extract_results_heading(soup)

    started_at = (
        datetime.strptime(date_text, "%d/%m/%Y, %H:%M")
        .replace(tzinfo=ZoneInfo(timezone_name))
        .astimezone(timezone.utc)
    )

    source_event_id = _extract_source_event_id(soup)
    latitude, longitude = _extract_geo_from_jsonld(soup)

    event_in = RaceEventIn(
        source="eventrac",
        source_event_id=source_event_id,
        name=results_title.removesuffix(" Results"),
        started_at=started_at,
        distance_m=distance_m,
        latitude=latitude,
        longitude=longitude,
        course_id=course_id,
    )

    table = soup.find("table", id="results")
    if table is None:
        raise ValueError("could not find Eventrac results table")

    header_row = table.find("thead")
    if header_row is None:
        raise ValueError("could not find Eventrac table header")

    header_cells = header_row.find_all("th")
    if any(
        cell.get("colspan", "1") != "1" or cell.get("rowspan", "1") != "1"
        for cell in header_cells
    ):
        raise ValueError("spanning Eventrac header cells are not supported")

    headers = [
        th.get_text(" ", strip=True)
        for th in header_cells
    ]

    def idx(*names: str) -> int | None:
        aliases = {name.lower() for name in names}
        matches = [i for i, header in enumerate(headers) if header.lower() in aliases]
        if len(matches) > 1:
            raise ValueError(f"ambiguous required column {names[0]!r} in Eventrac headers")
        return matches[0] if matches else None

    place_idx = idx("Position", "Place")
    gender_idx = idx("Gender")
    time_idx = idx("Time")

    if place_idx is None or gender_idx is None or time_idx is None:
        raise ValueError(f"missing required columns in Eventrac table headers: {headers}")

    results: list[RaceResultIn] = []
    accepted_row_numbers: list[int] = []
    skipped: list[SkippedEventracRow] = []
    errors: list[InvalidEventracRow] = []
    row_number = 0

    for row in table.find_all("tr"):
        if row.find_parent("table") is not table or row.find_parent(["thead", "tfoot"]):
            continue
        cells = row.find_all("td", recursive=False)
        if not cells:
            continue
        row_number += 1

        values = tuple(cell.get_text(" ", strip=True) for cell in cells)

        # Positional headers are trustworthy only when the complete row aligns.
        if len(values) != len(headers):
            errors.append(InvalidEventracRow(
                row_number, f"expected {len(headers)} cells, found {len(values)}", values
            ))
            continue
        if any(
            cell.get("colspan", "1") != "1" or cell.get("rowspan", "1") != "1"
            for cell in cells
        ):
            errors.append(InvalidEventracRow(
                row_number, "spanning data cells are not supported", values
            ))
            continue

        raw_place = values[place_idx].strip()
        raw_gender = values[gender_idx].strip()
        raw_time = values[time_idx].strip()

        if not raw_time:
            skipped.append(
                SkippedEventracRow(row_number=row_number, reason="missing finish time")
            )
            continue

        if not raw_place:
            errors.append(InvalidEventracRow(row_number, "missing finishing place", values))
            continue

        try:
            place = int(raw_place)
        except ValueError:
            errors.append(InvalidEventracRow(
                row_number, f"invalid finishing place: {raw_place!r}", values
            ))
            continue
        if place <= 0:
            errors.append(InvalidEventracRow(
                row_number, "finishing place must be positive", values
            ))
            continue

        try:
            duration_s = _parse_duration_to_seconds(raw_time)
        except ValueError as exc:
            errors.append(InvalidEventracRow(
                row_number, f"invalid finish time {raw_time!r}: {exc}", values
            ))
            continue

        try:
            result = RaceResultIn(
                duration_s=duration_s,
                place=place,
                gender=raw_gender or None,
            )
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            errors.append(InvalidEventracRow(row_number, f"invalid result: {details}", values))
            continue
        results.append(result)
        accepted_row_numbers.append(row_number)

    if row_number == 0:
        raise ValueError("no Eventrac candidate result rows found")

    outcome = EventracParseResult(
        event=event_in,
        accepted=tuple(results),
        skipped=tuple(skipped),
        errors=tuple(errors),
        accepted_row_numbers=tuple(accepted_row_numbers),
    )
    if outcome.candidate_count != row_number:
        raise RuntimeError("Eventrac row outcome counts do not reconcile")
    return outcome
