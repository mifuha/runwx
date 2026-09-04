from datetime import datetime, time, timezone
from pathlib import Path

from runwx.adapters.races import load_event_json, load_results_csv
from runwx.domain.models import WeatherObs
from runwx.services.race_analysis import analyze_race_event
from runwx.services.race_compare import compare_race_analyses


class FakeOpenMeteoClient:
    def fetch_weather_obs(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date,
        end_date,
    ):
        return [
            WeatherObs(
                observed_at=datetime.combine(
                    start_date,
                    time(hour=hour),
                    tzinfo=timezone.utc,
                ),
                temp_c=12.0 + hour - 9,
                wind_mps=3.0,
                precipitation_mm=0.0,
                humidity_pct=75.0,
            )
            for hour in (9, 10)
        ]


def test_compare_race_analyses_end_to_end_from_sample_files():
    base = Path("data")

    event_2024 = load_event_json(base / "sample_event.json")
    results_2024 = load_results_csv(
        base / "sample_results.csv",
        event_id=event_2024.event_id,
    )

    event_2023 = load_event_json(base / "sample_event_2023.json")
    results_2023 = load_results_csv(
        base / "sample_results_2023.csv",
        event_id=event_2023.event_id,
    )

    assert event_2023.event_id == "sample:course-a-5k-2023-10-01"
    assert event_2024.event_id == "sample:course-a-5k-2024-06-15"
    assert (event_2023.latitude, event_2023.longitude) == (
        event_2024.latitude,
        event_2024.longitude,
    )

    client = FakeOpenMeteoClient()
    analysis_2024 = analyze_race_event(event_2024, results_2024, client=client)
    analysis_2023 = analyze_race_event(event_2023, results_2023, client=client)

    rows = compare_race_analyses([analysis_2024, analysis_2023])

    assert len(rows) == 2

    # sorted by started_at ascending
    assert rows[0].event_id == event_2023.event_id
    assert rows[1].event_id == event_2024.event_id

    # same course comparison
    assert rows[0].course_id == "course-a-5k"
    assert rows[1].course_id == "course-a-5k"

    # same distance, different event dates
    assert rows[0].distance_m == 5000
    assert rows[1].distance_m == 5000
    assert rows[0].started_at < rows[1].started_at

    # performance comparison is exposed in standardized rows
    assert rows[0].median_duration_s == 1560
    assert rows[1].median_duration_s == 1505

    # weather summary is present
    assert rows[0].median_temp_c is not None
    assert rows[1].median_temp_c is not None
