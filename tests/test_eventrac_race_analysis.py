from datetime import datetime, timezone
from pathlib import Path

from runwx.adapters.races.eventrac_html import parse_eventrac_results_html
from runwx.domain.models import WeatherObs
from runwx.services.race_analysis import analyze_race_event


class FakeOpenMeteoClient:
    def fetch_weather_obs(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date,
        end_date,
    ):
        # Return hourly observations around the event time.
        # Keep it simple and deterministic.
        return [
            WeatherObs(
                observed_at=datetime(2022, 3, 6, 9, 0, tzinfo=timezone.utc),
                temp_c=8.0,
                wind_mps=3.5,
                precipitation_mm=0.0,
                humidity_pct=70.0,
            ),
            WeatherObs(
                observed_at=datetime(2022, 3, 6, 10, 0, tzinfo=timezone.utc),
                temp_c=8.5,
                wind_mps=4.0,
                precipitation_mm=0.0,
                humidity_pct=72.0,
            ),
            WeatherObs(
                observed_at=datetime(2022, 3, 6, 11, 0, tzinfo=timezone.utc),
                temp_c=9.0,
                wind_mps=4.2,
                precipitation_mm=0.0,
                humidity_pct=68.0,
            ),
        ]


def test_eventrac_results_can_flow_through_race_analysis():
    html = Path("data/raw/eventrac/lydd_half_2022.html").read_text(encoding="utf-8")

    event_in, results_in = parse_eventrac_results_html(
        html,
        course_id="lydd-half-marathon",
        distance_m=21097,
    )

    event = event_in.to_domain()
    # Domain RaceResult must reference the internal canonical event.event_id,
    # not the raw provider source_event_id.
    results = [row.to_domain(event_id=event.event_id) for row in results_in]

    analysis = analyze_race_event(
        event,
        results,
        client=FakeOpenMeteoClient(),
        top_n=20,
    )

    assert analysis.event.course_id == "lydd-half-marathon"
    assert analysis.summary.finisher_count == len(results)
    assert analysis.summary.best_duration_s > 0
    assert analysis.weather_summary.enriched_count > 0
    assert len(analysis.pipeline_result.enriched) > 0