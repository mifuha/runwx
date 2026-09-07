from datetime import datetime, timezone
from pathlib import Path

import pytest

from runwx.adapters.races.eventrac_html import (
    load_eventrac_results_html,
    parse_eventrac_results_html,
)


def test_eventrac_html_parsed_objects_convert_to_domain():
    outcome = load_eventrac_results_html(
        "data/raw/eventrac/lydd_half_2022.html",
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )

    event = outcome.event.to_domain()
    results = [row.to_domain(event_id=event.event_id) for row in outcome.accepted]

    assert event.course_id == "lydd-half-marathon"
    assert len(results) > 0
    assert results[0].event_id == event.event_id
    assert results[0].duration_s > 0


def test_parse_eventrac_results_html_lydd_half_2022():
    html = Path("data/raw/eventrac/lydd_half_2022.html").read_text(encoding="utf-8")

    outcome = parse_eventrac_results_html(
        html,
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )
    event_in = outcome.event
    results_in = outcome.accepted

    assert event_in.source == "eventrac"
    assert event_in.source_event_id == "21723"
    assert event_in.name == "Lydd Half Marathon 2022"
    assert event_in.course_id == "lydd-half-marathon"
    assert event_in.distance_m == 21097
    assert event_in.latitude == 50.954438
    assert event_in.longitude == 0.902385
    assert event_in.started_at == datetime(2022, 3, 6, 10, 0, tzinfo=timezone.utc)

    assert len(results_in) == 189
    assert results_in[0].place == 1
    assert results_in[0].gender == "Male"
    assert results_in[0].duration_s == 4267
    assert outcome.skipped == ()
    assert outcome.errors == ()
    assert outcome.candidate_count == 189


def test_parse_eventrac_results_html_converts_british_summer_time_to_utc():
    html = Path("data/raw/eventrac/lydd_half_2022.html").read_text(encoding="utf-8")
    html = html.replace(
        "<small>06/03/2022, 10:00</small>",
        "<small>06/07/2022, 10:00</small>",
    )

    outcome = parse_eventrac_results_html(
        html,
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )

    assert outcome.event.started_at == datetime(2022, 7, 6, 9, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("blank_time", ["", " \t\n "])
def test_eventrac_html_reports_missing_time_and_keeps_valid_result(blank_time):
    html = """
    <link rel="canonical" href="https://www.eventrac.co.uk/results/21723">
    <script type="application/ld+json">
        {"location": {"geo": {"latitude": 50.954438, "longitude": 0.902385}}}
    </script>
    <div class="box-header">
        <h3 class="box-title">Lydd Half Marathon 2022 Results</h3>
        <small>06/03/2022, 10:00</small>
    </div>
    <table id="results">
        <thead><tr><th>Position</th><th>Gender</th><th>Time</th></tr></thead>
        <tbody>
            <tr><td>42</td><td>Female</td><td>BLANK_TIME</td></tr>
            <tr><td>7</td><td>Male</td><td>01:11:07.00</td></tr>
        </tbody>
    </table>
    """.replace("BLANK_TIME", blank_time)

    outcome = parse_eventrac_results_html(
        html,
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )

    assert len(outcome.accepted) == 1
    assert outcome.accepted[0].place == 7
    assert outcome.accepted[0].duration_s == 4267
    assert len(outcome.skipped) == 1
    assert outcome.skipped[0].row_number == 1
    assert outcome.skipped[0].reason == "missing finish time"
