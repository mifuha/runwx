from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from runwx.adapters.csv.schemas import RunIn, WeatherObsIn
from runwx.adapters.races.schemas import RaceEventIn

def test_run_in_parses_string_fields_and_converts_to_domain():
    row = {
        "started_at": "2026-02-01T10:00:00+00:00",
        "duration_s": "3600",
        "distance_m": "10000",
    }

    model = RunIn.model_validate(row)
    run = model.to_domain()

    assert run.duration_s == 3600
    assert run.distance_m == 10000
    assert run.started_at == datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)


def test_weather_obs_in_rejects_naive_datetime():
    row = {
        "observed_at": "2026-02-01T10:20:00",
        "temp_c": "6.5",
        "wind_mps": "4.2",
        "precipitation_mm": "0.0",
        "humidity_pct": "50.0",
    }

    with pytest.raises(ValidationError):
        WeatherObsIn.model_validate(row)


def test_weather_obs_in_rejects_negative_wind():
    row = {
        "observed_at": "2026-02-01T10:20:00+00:00",
        "temp_c": "6.5",
        "wind_mps": "-1.0",
        "precipitation_mm": "0.0",
        "humidity_pct": "50.0",
    }

    with pytest.raises(ValidationError):
        WeatherObsIn.model_validate(row)
def test_race_event_in_to_domain_normalizes_course_id_from_name():
    event_in = RaceEventIn(
        source="demo",
        source_event_id="event-1",
        name="2025 Sample Park 10K",
        started_at="2025-05-01T10:00:00Z",
        distance_m=10000,
        latitude=46.0,
        longitude=14.0,
        course_id=None,
    )

    event = event_in.to_domain()

    assert event.course_id == "sample-park-10k"