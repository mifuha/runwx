from datetime import datetime, timezone
import sqlite3

from runwx.enrich import attach_weather
from runwx.models import Run, WeatherObs
from runwx.storage_sqlite import connect, write_enriched


def test_write_enriched_creates_tables_and_rows(tmp_path):
    db_path = tmp_path / "runwx.db"
    conn = connect(db_path)

    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,
        distance_m=10_000,
    )
    obs = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc),
        temp_c=6.5,
        wind_mps=4.2,
        precipitation_mm=0.0,
    )

    enriched = [attach_weather(run, obs)]
    created = write_enriched(conn, enriched)

    assert created == 1

    # verify counts
    runs_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    weather_count = conn.execute("SELECT COUNT(*) FROM weather_obs").fetchone()[0]
    link_count = conn.execute("SELECT COUNT(*) FROM run_with_weather").fetchone()[0]

    assert runs_count == 1
    assert weather_count == 1
    assert link_count == 1

    conn.close()


def test_write_enriched_is_idempotent_for_same_row(tmp_path):
    db_path = tmp_path / "runwx.db"
    conn = connect(db_path)

    run = Run(
        started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        duration_s=3600,
        distance_m=10_000,
    )
    obs = WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc),
        temp_c=6.5,
        wind_mps=4.2,
        precipitation_mm=0.0,
    )

    enriched = [attach_weather(run, obs)]

    created1 = write_enriched(conn, enriched)
    created2 = write_enriched(conn, enriched)

    assert created1 == 1
    assert created2 == 0  # second time should not create duplicate link

    link_count = conn.execute("SELECT COUNT(*) FROM run_with_weather").fetchone()[0]
    assert link_count == 1

    conn.close()