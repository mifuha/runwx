from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class EnrichedRow:
    started_at: str
    duration_s: int
    distance_m: int
    observed_at: str
    temp_c: float
    wind_mps: float
    precipitation_mm: float


def fetch_latest_enriched(conn: sqlite3.Connection, *, limit: int = 20) -> list[EnrichedRow]:
    """
    Return latest enriched runs, ordered by run start time descending.
    """
    cur = conn.execute(
        """
        SELECT
            r.started_at,
            r.duration_s,
            r.distance_m,
            w.observed_at,
            w.temp_c,
            w.wind_mps,
            w.precipitation_mm
        FROM run_with_weather rw
        JOIN runs r ON r.id = rw.run_id
        JOIN weather_obs w ON w.id = rw.weather_id
        ORDER BY r.started_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    out: list[EnrichedRow] = []
    for row in cur.fetchall():
        out.append(
            EnrichedRow(
                started_at=row[0],
                duration_s=int(row[1]),
                distance_m=int(row[2]),
                observed_at=row[3],
                temp_c=float(row[4]),
                wind_mps=float(row[5]),
                precipitation_mm=float(row[6]),
            )
        )
    return out