from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from runwx.enrich import RunWithWeather
from runwx.models import Run, WeatherObs
from runwx.pipeline import PipelineResult


def _iso(dt) -> str:
    return dt.isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            duration_s INTEGER NOT NULL,
            distance_m INTEGER NOT NULL,
            UNIQUE(started_at, duration_s, distance_m)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_obs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            temp_c REAL NOT NULL,
            wind_mps REAL NOT NULL,
            precipitation_mm REAL NOT NULL,
            UNIQUE(observed_at, temp_c, wind_mps, precipitation_mm)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_with_weather (
            run_id INTEGER NOT NULL,
            weather_id INTEGER NOT NULL,
            PRIMARY KEY(run_id),
            FOREIGN KEY(run_id) REFERENCES runs(id),
            FOREIGN KEY(weather_id) REFERENCES weather_obs(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skipped_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            duration_s INTEGER NOT NULL,
            distance_m INTEGER NOT NULL,
            reason TEXT NOT NULL,
            UNIQUE(started_at, duration_s, distance_m, reason)
        )
        """
    )

    conn.commit()


def _get_or_create_run_id(conn: sqlite3.Connection, run: Run) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO runs (started_at, duration_s, distance_m)
        VALUES (?, ?, ?)
        """,
        (_iso(run.started_at), run.duration_s, run.distance_m),
    )
    row = conn.execute(
        """
        SELECT id FROM runs
        WHERE started_at = ? AND duration_s = ? AND distance_m = ?
        """,
        (_iso(run.started_at), run.duration_s, run.distance_m),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to read back run id after insert")
    return int(row[0])


def _get_or_create_weather_id(conn: sqlite3.Connection, obs: WeatherObs) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO weather_obs (observed_at, temp_c, wind_mps, precipitation_mm)
        VALUES (?, ?, ?, ?)
        """,
        (_iso(obs.observed_at), obs.temp_c, obs.wind_mps, obs.precipitation_mm),
    )
    row = conn.execute(
        """
        SELECT id FROM weather_obs
        WHERE observed_at = ? AND temp_c = ? AND wind_mps = ? AND precipitation_mm = ?
        """,
        (_iso(obs.observed_at), obs.temp_c, obs.wind_mps, obs.precipitation_mm),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to read back weather id after insert")
    return int(row[0])


def write_enriched(conn: sqlite3.Connection, rows: Iterable[RunWithWeather]) -> int:
    """
    Persist enriched rows to SQLite.
    Returns number of run_with_weather links created.
    Assumes init_db(conn) has already been called.
    """
    init_db(conn)
    created = 0

    for item in rows:
        run_id = _get_or_create_run_id(conn, item.run)
        weather_id = _get_or_create_weather_id(conn, item.weather)

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO run_with_weather (run_id, weather_id)
            VALUES (?, ?)
            """,
            (run_id, weather_id),
        )
        created += int(cur.rowcount)

    conn.commit()
    return created


def write_pipeline_result(conn: sqlite3.Connection, result: PipelineResult) -> tuple[int, int]:
    """
    Persist both enriched and skipped rows to SQLite.
    Returns (enriched_links_created, skipped_rows_created).
    """
    

    enriched_created = write_enriched(conn, result.enriched)

    skipped_created = 0
    for s in result.skipped:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO skipped_runs (started_at, duration_s, distance_m, reason)
            VALUES (?, ?, ?, ?)
            """,
            (_iso(s.run.started_at), s.run.duration_s, s.run.distance_m, s.reason),
        )
        skipped_created += int(cur.rowcount)

    conn.commit()
    return enriched_created, skipped_created