from datetime import datetime, timezone

from runwx.domain.models import WeatherObs
from runwx.domain.race import RaceEvent, RaceResult
from runwx.services.race_pipeline import enrich_race_results_with_open_meteo


class FakeOpenMeteoClient:
    def __init__(self):
        self.calls = []

    def fetch_weather_obs(self, *, latitude, longitude, start_date, end_date):
        self.calls.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        return [
            WeatherObs(
                observed_at=datetime(2024, 10, 6, 9, 0, tzinfo=timezone.utc),
                temp_c=12.0,
                wind_mps=3.0,
                precipitation_mm=0.0,
                humidity_pct=80.0,
            ),
            WeatherObs(
                observed_at=datetime(2024, 10, 6, 10, 0, tzinfo=timezone.utc),
                temp_c=13.0,
                wind_mps=4.0,
                precipitation_mm=0.0,
                humidity_pct=78.0,
            ),
        ]


def test_enrich_race_results_with_open_meteo_uses_event_location():
    event = RaceEvent(
        source="demo",
        source_event_id="event-001",
        name="Demo 10K",
        started_at=datetime(2024, 10, 6, 9, 0, tzinfo=timezone.utc),
        distance_m=10000,
        latitude=51.5074,
        longitude=-0.1278,
        course_id="demo-10k-course",
    )
    results = [
        RaceResult(event_id=event.event_id, duration_s=3600, athlete_id="a1"),
        RaceResult(event_id=event.event_id, duration_s=3720, athlete_id="a2"),
    ]

    client = FakeOpenMeteoClient()

    pipeline_result = enrich_race_results_with_open_meteo(
        event,
        results,
        client=client,
    )

    assert len(pipeline_result.enriched) == 2
    assert len(pipeline_result.skipped) == 0

    assert len(client.calls) == 1
    assert client.calls[0]["latitude"] == event.latitude
    assert client.calls[0]["longitude"] == event.longitude