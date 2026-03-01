from datetime import datetime, timedelta, timezone

from runwx.models import Run, WeatherObs
from runwx.pipeline import enrich_runs
from runwx.storage_sqlite import connect, write_pipeline_result


def test_write_pipeline_result_persists_skipped(tmp_path):
    db = tmp_path / "runwx.db"
    conn = connect(db)

    runs = [
        Run(started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc), duration_s=3600, distance_m=10000),
        Run(started_at=datetime(2026, 2, 1, 15, 0, tzinfo=timezone.utc), duration_s=2400, distance_m=7000),
    ]

    weather = [
        WeatherObs(observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc), temp_c=6.5, wind_mps=4.2, precipitation_mm=0.0),
        WeatherObs(observed_at=datetime(2026, 2, 1, 16, 30, tzinfo=timezone.utc), temp_c=5.9, wind_mps=5.1, precipitation_mm=0.0),
    ]

    result = enrich_runs(runs, weather, max_gap=timedelta(minutes=30))

    enriched_created, skipped_created = write_pipeline_result(conn, result)

    assert enriched_created == 1
    assert skipped_created == 1

    skipped_count = conn.execute("SELECT COUNT(*) FROM skipped_runs").fetchone()[0]
    assert skipped_count == 1

    row = conn.execute("SELECT reason FROM skipped_runs").fetchone()[0]
    assert "No weather within" in row

    conn.close()


def test_write_pipeline_result_idempotent(tmp_path):
    db = tmp_path / "runwx.db"
    conn = connect(db)

    runs = [Run(started_at=datetime(2026, 2, 1, 15, 0, tzinfo=timezone.utc), duration_s=2400, distance_m=7000)]
    weather = [WeatherObs(observed_at=datetime(2026, 2, 1, 16, 30, tzinfo=timezone.utc), temp_c=5.9, wind_mps=5.1, precipitation_mm=0.0)]

    result = enrich_runs(runs, weather, max_gap=timedelta(minutes=30))

    c1 = write_pipeline_result(conn, result)
    c2 = write_pipeline_result(conn, result)

    # First run creates the skipped row, second run should create nothing new
    assert c1[1] == 1
    assert c2[1] == 0

    conn.close()