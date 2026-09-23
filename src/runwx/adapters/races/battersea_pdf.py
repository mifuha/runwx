"""Parse only the qualified Sri Chinmoy Battersea Park 10K result PDFs."""

from __future__ import annotations

from datetime import datetime, time
from hashlib import sha256
from importlib.resources import files
from io import BytesIO
import json
import re
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from runwx.adapters.races.outcomes import RaceParseResult
from runwx.adapters.races.schemas import RaceEventIn, RaceResultIn


QUALIFIED_EDITIONS = json.loads(
    files(__package__).joinpath("battersea_editions.json").read_text(encoding="utf-8")
)
HEADER_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r",?\s+(20\d{2})\b", re.IGNORECASE,
)
MARKER = re.compile(r"ALL\s+RESULTS\s+BELOW", re.IGNORECASE)
RANK = re.compile(r"^\s*(\d+)(?=\D)")
TIME = re.compile(r"(?<!\d)\d{2}:[0-5]\d:[0-5]\d")
COURSE_ID = "battersea-park-10k"
VENUE_LATITUDE = 51.4791075
VENUE_LONGITUDE = -0.1564981


def _result_rows(text: str, *, expected_count: int) -> tuple[RaceResultIn, ...]:
    markers = list(MARKER.finditer(text))
    if len(markers) != 1:
        raise ValueError("Battersea PDF needs exactly one full-results marker")
    body = text[markers[0].end():]
    if not re.match(r"\s*RESULTS\s+RANK", body, re.IGNORECASE):
        raise ValueError("Battersea PDF full-results heading is missing")
    results = []
    previous_duration = 0
    for line in body.splitlines():
        rank_match = RANK.match(line)
        times = TIME.findall(line)
        if rank_match is None and not times:
            continue
        rank = len(results) + 1
        if rank_match is None or int(rank_match[1]) != rank or len(times) != 1:
            raise ValueError(f"Battersea PDF ambiguous or out-of-order result at row {rank}")
        hours, minutes, seconds = map(int, times[0].split(":"))
        duration = hours * 3600 + minutes * 60 + seconds
        if duration <= 0 or duration < previous_duration:
            raise ValueError(f"Battersea PDF invalid or unordered finish time at row {rank}")
        results.append(RaceResultIn(place=rank, duration_s=duration))
        previous_duration = duration
    if len(results) != expected_count:
        raise ValueError(
            f"Battersea PDF expected {expected_count} full results, found {len(results)}"
        )
    return tuple(results)


def parse_battersea_pdf(
    data: bytes, *, course_id: str, distance_m: int,
    timezone_name: str, timing_basis: str | None,
) -> RaceParseResult:
    """Use pinned PDF bytes and the evidenced 08:30 London series start.

    The PDF names/club cells are not reliable text fields. Only published rank
    and whole-second finish time are exported; the winners section is excluded.
    The source calls these manually timed results, without a chip/gun flag.
    """
    if (course_id != COURSE_ID or distance_m != 10_000
            or timezone_name != "Europe/London" or timing_basis is not None):
        raise ValueError("Battersea PDF requires its qualified course, distance, timezone and unknown chip/gun basis")
    if not data.startswith(b"%PDF-"):
        raise ValueError("Battersea result input is not a PDF")
    digest = sha256(data).hexdigest()
    qualified = [(race_date, item) for race_date, item in QUALIFIED_EDITIONS.items()
                 if item["result_sha256"] == digest]
    if len(qualified) != 1:
        raise ValueError("Battersea PDF is outside the qualified source hash scope")
    qualified_date, edition = qualified[0]
    try:
        reader = PdfReader(BytesIO(data))
        if not reader.pages:
            raise ValueError("Battersea PDF has no pages")
        first = reader.pages[0].extract_text() or ""
        header = first[:250]
        date_match = HEADER_DATE.search(header)
        if ("Sri Chinmoy 10K Race" not in header
                or "Battersea Park" not in header or date_match is None):
            raise ValueError("Battersea PDF event/date/venue header is missing")
        day, month, year = date_match.groups()
        race_date = datetime.strptime(f"{int(day)} {month} {year}", "%d %B %Y").date()
        if race_date.isoformat() != qualified_date:
            raise ValueError("Battersea PDF header date differs from the qualified source")
        if len(reader.pages) != edition["pdf_pages"]:
            raise ValueError("Battersea PDF page count differs from the qualified source")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as exc:
        raise ValueError("Battersea PDF cannot be read") from exc
    results = _result_rows(text, expected_count=edition["result_count"])
    started_at = datetime.combine(race_date, time(8, 30), ZoneInfo("Europe/London"))
    event = RaceEventIn(
        source="sri_chinmoy", source_event_id=f"battersea-10k-{race_date.isoformat()}",
        name=edition["name"], started_at=started_at,
        distance_m=distance_m, latitude=VENUE_LATITUDE, longitude=VENUE_LONGITUDE,
        course_id=course_id,
    )
    return RaceParseResult(
        event=event, accepted=results, skipped=(),
        accepted_row_numbers=tuple(range(1, len(results) + 1)),
        duration_precision="published whole seconds; manually timed",
        timing_basis=None,
    )
