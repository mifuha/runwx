# src/runwx/adapters/races/course_normalization.py
from __future__ import annotations

import re
import unicodedata


# Keep curated course aliases small and explicit.
COURSE_ALIASES: dict[tuple[str, int], tuple[str, ...]] = {
    ("sample-park-10k", 10_000): (
        "sample-park-10k",
        "Sample Park 10K",
        "Sample Park 10 km",
        "2025 Sample Park 10K",
    ),
    ("lydd-half-marathon", 21_097): (
        "Lydd Half Marathon",
        "Lydd Half Marathon 2022",
        "2022 Lydd Half Marathon",
        "Brett Lydd Half Marathon",
        "Brett Lydd Half Marathon 2022",
    ),
}


def _slug_course_id(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def _normalize_event_name(value: str) -> str:
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", value)
    text = re.sub(r"\bkm\b", "k", text, flags=re.IGNORECASE)
    return _slug_course_id(text)


_ALIAS_TO_CANONICAL: dict[tuple[str, int], str] = {
    (_normalize_event_name(alias), distance_m): canonical
    for (canonical, distance_m), aliases in COURSE_ALIASES.items()
    for alias in aliases
}


def normalize_course_id(
    *,
    source: str,
    source_event_id: str,
    name: str,
    raw_course_id: str | None,
    distance_m: int,
) -> str | None:
    """Normalize an explicit course ID, or infer a known alias by name and distance.

    A non-empty raw_course_id wins and is slug-normalized. Otherwise, the event
    name and distance_m are used to infer a canonical ID from known aliases.
    """
    # source and source_event_id are included because they will likely matter later,
    # even if version 1 does not use them yet.
    _ = source
    _ = source_event_id

    if raw_course_id is not None:
        raw_stripped = raw_course_id.strip()
        if raw_stripped:
            return _slug_course_id(raw_stripped)

    name_key = _normalize_event_name(name)
    return _ALIAS_TO_CANONICAL.get((name_key, distance_m))
