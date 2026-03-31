from datetime import datetime, timezone

from runwx.domain.models import WeatherObs
from runwx.domain.race import RaceEvent, RaceResult
from runwx.services.race_analysis import analyze_race_event


class FakeOpenMeteoClient:
    def fetch_weather_obs(self, *, latitude, longitude, start_date, end_date):
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


def test_analyze_race_event_combines_summary_and_weather_enrichment():
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
        RaceResult(event_id=event.event_id, duration_s=3900, athlete_id="a3"),
    ]

    analysis = analyze_race_event(
        event,
        results,
        client=FakeOpenMeteoClient(),
        top_n=2,
    )

    assert analysis.event == event

    assert analysis.summary.finisher_count == 3
    assert analysis.summary.best_duration_s == 3600
    assert analysis.summary.median_duration_s == 3720
    assert analysis.summary.top_n_median_duration_s == 3660.0

    assert len(analysis.pipeline_result.enriched) == 3
    assert len(analysis.pipeline_result.skipped) == 0