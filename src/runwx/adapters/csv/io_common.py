from __future__ import annotations

from datetime import datetime


def parse_datetime_iso(value: str) -> datetime:
    """
    Parse an ISO-8601 datetime string.
    Accepts trailing 'Z' by converting to '+00:00'.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    dt = datetime.fromisoformat(text)

    if dt.tzinfo is None:
        raise ValueError(f"datetime must be timezone-aware: {value!r}")

    return dt


def parse_int(value: str) -> int:
    return int(value.strip())


def parse_float(value: str) -> float:
    return float(value.strip())