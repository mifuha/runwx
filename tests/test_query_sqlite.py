from datetime import datetime, timezone

from runwx.enrich import attach_weather
from runwx.models import Run, WeatherObs
from runwx.storage_sqlite import connect, write_enriched
from runwx.query_sqlite import fetch_latest_enriched


def test_fetch_latest_enriched(tmp_path):
    db = tmp_path / "runwx.db"
    conn = connect(db)

    run = Run(started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc), duration_s=3600, distance_m=10000)
    obs = WeatherObs(observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc), temp_c=6.5, wind_mps=4.2, precipitation_mm=0.0)

    write_enriched(conn, [attach_weather(run, obs)])

    rows = fetch_latest_enriched(conn, limit=10)
    conn.close()

    assert len(rows) == 1
    assert rows[0].distance_m == 10000
    assert rows[0].temp_c == 6.5