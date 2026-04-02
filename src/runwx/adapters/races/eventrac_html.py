from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from runwx.adapters.races.schemas import RaceEventIn, RaceResultIn

from pathlib import Path

def load_eventrac_results_html(
    path: str | Path,
    *,
    course_id: str,
    distance_m: int,
) -> tuple[RaceEventIn, list[RaceResultIn]]:
    html = Path(path).read_text(encoding="utf-8")
    return parse_eventrac_results_html(
        html,
        course_id=course_id,
        distance_m=distance_m,
    )

def _parse_duration_to_seconds(value: str) -> int:
    text = value.strip()
    if not text:
        raise ValueError("empty duration")

    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError(f"unsupported duration format: {value!r}")

    hours = int(parts[0])
    minutes = int(parts[1])

    seconds_part = parts[2]
    if "." in seconds_part:
        seconds_part = seconds_part.split(".", 1)[0]
    seconds = int(seconds_part)

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

        location = payload.get("location", {})
        geo = location.get("geo", {})
        latitude = geo.get("latitude")
        longitude = geo.get("longitude")

        if latitude is not None and longitude is not None:
            return float(latitude), float(longitude)

    raise ValueError("could not extract latitude/longitude from JSON-LD")


def parse_eventrac_results_html(
    html: str,
    *,
    course_id: str,
    distance_m: int,
) -> tuple[RaceEventIn, list[RaceResultIn]]:
    soup = BeautifulSoup(html, "html.parser")

    title_node = soup.select_one("div.box-header h3.box-title")
    if title_node is None:
        raise ValueError("could not find Eventrac results title")

    date_node = soup.select_one("div.box-header small")
    if date_node is None:
        raise ValueError("could not find Eventrac results date/time")

    results_title = title_node.get_text(" ", strip=True)
    date_text = date_node.get_text(" ", strip=True)

    started_at = datetime.strptime(date_text, "%d/%m/%Y, %H:%M").replace(tzinfo=timezone.utc)

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

    headers = [
        th.get_text(" ", strip=True)
        for th in header_row.find_all("th")
    ]
    header_map = {name.lower(): idx for idx, name in enumerate(headers)}

    def idx(*names: str) -> int | None:
        for name in names:
            if name.lower() in header_map:
                return header_map[name.lower()]
        return None

    place_idx = idx("Position", "Place")
    gender_idx = idx("Gender")
    time_idx = idx("Time")

    if place_idx is None or gender_idx is None or time_idx is None:
        raise ValueError(f"missing required columns in Eventrac table headers: {headers}")

    results: list[RaceResultIn] = []

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        values = [cell.get_text(" ", strip=True) for cell in cells]

        # Skip malformed / non-result rows
        if len(values) <= time_idx:
            continue

        raw_place = values[place_idx].strip()
        raw_gender = values[gender_idx].strip()
        raw_time = values[time_idx].strip()

        if not raw_place or not raw_time:
            continue

        try:
            place = int(raw_place)
        except ValueError:
            continue

        results.append(
            RaceResultIn(
                duration_s=_parse_duration_to_seconds(raw_time),
                place=place,
                gender=raw_gender or None,
            )
        )

    if not results:
        raise ValueError("no Eventrac result rows parsed")

    return event_in, results