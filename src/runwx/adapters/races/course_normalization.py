# src/runwx/adapters/races/course_normalization.py
from __future__ import annotations

import re
import unicodedata


# Keep this tiny at first. Start with sample/demo aliases only.
COURSE_ALIASES: dict[str, tuple[str, ...]] = {
    "sample-park-10k": (
        "sample-park-10k",
        "Sample Park 10K",
        "Sample Park 10 km",
        "2025 Sample Park 10K",
    ),
}


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()

    # remove standalone years
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", text)

    # normalize km wording a bit
    text = re.sub(r"\bkm\b", "k", text)

    # collapse punctuation/whitespace into dashes
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


_ALIAS_TO_CANONICAL: dict[str, str] = {
    _slug(alias): canonical
    for canonical, aliases in COURSE_ALIASES.items()
    for alias in aliases
}


def normalize_course_id(
    *,
    source: str,
    source_event_id: str,
    name: str,
    raw_course_id: str | None,
) -> str | None:
    # source and source_event_id are included because they will likely matter later,
    # even if version 1 does not use them yet.
    _ = source
    _ = source_event_id

    if raw_course_id:
        raw_key = _slug(raw_course_id)
        return _ALIAS_TO_CANONICAL.get(raw_key, raw_key)

    name_key = _slug(name)
    return _ALIAS_TO_CANONICAL.get(name_key)