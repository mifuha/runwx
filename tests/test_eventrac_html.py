from datetime import datetime, timezone
from pathlib import Path

from runwx.adapters.races.eventrac_html import parse_eventrac_results_html

from pathlib import Path

from runwx.adapters.races.eventrac_html import parse_eventrac_results_html


def test_eventrac_html_parsed_objects_convert_to_domain():
    html = Path("data/raw/eventrac/lydd_half_2022.html").read_text(encoding="utf-8")

    event_in, results_in = parse_eventrac_results_html(
        html,
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )

    event = event_in.to_domain()
    results = [row.to_domain(event_id=event.source_event_id) for row in results_in]

    assert event.course_id == "lydd-half-marathon"
    assert len(results) > 0
    assert results[0].event_id == event.source_event_id
    assert results[0].duration_s > 0

def test_parse_eventrac_results_html_lydd_half_2022():
    html = Path("data/raw/eventrac/lydd_half_2022.html").read_text(encoding="utf-8")

    event_in, results_in = parse_eventrac_results_html(
        html,
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )

    assert event_in.source == "eventrac"
    assert event_in.source_event_id == "21723"
    assert event_in.name == "Lydd Half Marathon 2022"
    assert event_in.course_id == "lydd-half-marathon"
    assert event_in.distance_m == 21097
    assert event_in.latitude == 50.954438
    assert event_in.longitude == 0.902385
    assert event_in.started_at == datetime(2022, 3, 6, 10, 0, tzinfo=timezone.utc)

    assert len(results_in) > 0
    assert results_in[0].place == 1
    assert results_in[0].gender == "Male"
    assert results_in[0].duration_s == 4267


def test_parse_eventrac_results_html_converts_british_summer_time_to_utc():
    html = Path("data/raw/eventrac/lydd_half_2022.html").read_text(encoding="utf-8")
    html = html.replace(
        "<small>06/03/2022, 10:00</small>",
        "<small>06/07/2022, 10:00</small>",
    )

    event_in, _ = parse_eventrac_results_html(
        html,
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )

    assert event_in.started_at == datetime(2022, 7, 6, 9, 0, tzinfo=timezone.utc)
