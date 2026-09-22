import copy
import hashlib
import json
from datetime import timedelta

import pytest

from runwx.adapters.races.sporthive_json import parse_sporthive_snapshot_json
from runwx.main import main
from runwx.services.snapshot_artifacts import build_snapshot_artifacts


def participant(result_id, place, chip, *, dns=False, dsq=False):
    return {
        "id": result_id,
        "name": f"Runner {result_id}",
        "activeEventId": "event-123",
        "activeRaceId": "1",
        "distanceInMeter": 21082,
        "overallPosition": place,
        "chipTimeOfParticipant": chip,
        "gunTimeOfParticipant": chip,
        "gender": "F" if place == 2 else "M",
        "dns": dns,
        "dsq": dsq,
    }


def snapshot():
    rows = [
        participant("result-1", 1, "01:00:00.0010000"),
        participant("result-2", 2, "01:30:00.0000000"),
        participant("result-3", 3, None, dns=True),
    ]
    return {
        "snapshot_schema_version": 1,
        "event": {
            "source_event_id": "event-123",
            "name": "Saved Half 2018",
            "started_at": "2018-09-30T10:00:00+01:00",
            "latitude": 51.074381,
            "longitude": 1.162709,
        },
        "race": {
            "id": "race-456",
            "activeEventId": "event-123",
            "activeRaceId": "1",
            "classificationsCount": 3,
            "distanceInMeter": 21082,
        },
        "pages": [
            {"content": rows[:2], "number": 0, "size": 2, "totalElements": 3,
             "totalPages": 2, "first": True, "last": False, "numberOfElements": 2},
            {"content": rows[2:], "number": 1, "size": 2, "totalElements": 3,
             "totalPages": 2, "first": False, "last": True, "numberOfElements": 1},
        ],
        "source_responses": [
            {"file": "races.json", "requested_url": "https://example.invalid/races", "sha256": "a" * 64},
            {"file": "page-0.json", "requested_url": "https://example.invalid/page/0", "sha256": "b" * 64},
            {"file": "page-1.json", "requested_url": "https://example.invalid/page/1", "sha256": "c" * 64},
        ],
    }


def encoded(value=None):
    return json.dumps(snapshot() if value is None else value, sort_keys=True).encode()


def test_sporthive_snapshot_validates_complete_pages_and_uses_selected_chip_time():
    parsed = parse_sporthive_snapshot_json(
        encoded().decode(), course_id="folkestone-route", distance_m=21097,
        timing_basis="chip",
    )

    assert parsed.event.source == "sporthive"
    assert parsed.event.source_event_id == "event-123"
    assert parsed.event.started_at.isoformat() == "2018-09-30T10:00:00+01:00"
    assert parsed.candidate_count == 3
    assert parsed.accepted_row_numbers == (1, 2)
    assert [row.duration_s for row in parsed.accepted] == [3601, 5400]
    assert [row.place for row in parsed.accepted] == [1, 2]
    assert [(row.row_number, row.reason) for row in parsed.skipped] == [(3, "did not start")]
    assert parsed.errors == ()
    assert parsed.duration_precision == "whole seconds; provider fractions rounded up"
    assert parsed.timing_basis == "chip"


@pytest.mark.parametrize("mutation", ["missing_page", "wrong_total", "duplicate_id"])
def test_sporthive_snapshot_rejects_incomplete_or_conflicting_structure(mutation):
    value = snapshot()
    if mutation == "missing_page":
        value["pages"].pop()
        value["source_responses"].pop()
    elif mutation == "wrong_total":
        value["pages"][1]["totalElements"] = 4
    else:
        value["pages"][1]["content"][0]["id"] = "result-1"

    with pytest.raises(ValueError):
        parse_sporthive_snapshot_json(
            encoded(value).decode(), course_id="folkestone-route", distance_m=21097,
            timing_basis="chip",
        )


def test_sporthive_requires_explicit_timing_basis():
    with pytest.raises(ValueError, match="timing_basis must be chip or gun"):
        parse_sporthive_snapshot_json(
            encoded().decode(), course_id="folkestone-route", distance_m=21097,
            timing_basis=None,
        )


def test_shared_report_and_export_reconcile_for_sporthive(tmp_path, capsys):
    race = tmp_path / "race.json"
    weather = tmp_path / "weather.csv"
    race.write_bytes(encoded())
    weather.write_text(
        "observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct\n"
        "2018-09-30T09:30:00+00:00,12.0,3.0,0.0,75.0\n"
        "2018-09-30T10:00:00+00:00,13.0,4.0,0.1,70.0\n"
    )
    settings = dict(
        course_id="folkestone-route", distance_m=21097,
        timezone_name="Europe/London", race_format="sporthive_json",
        timing_basis="chip", weather_kind="historical_reanalysis", race_kind="historical",
        export_weather_kind="historical_reanalysis", max_gap=timedelta(minutes=30),
    )

    first = build_snapshot_artifacts(race, weather, **settings)
    second = build_snapshot_artifacts(race, weather, **settings)

    assert first == second
    assert first.report["race"]["event_id"] == "sporthive:event-123"
    assert first.report["sources"]["race"] == {
        "file": str(race),
        "sha256": hashlib.sha256(race.read_bytes()).hexdigest(),
        "provider": "sporthive",
        "source_event_id": "event-123",
    }
    assert first.report["result_quality"]["candidate_count"] == 3
    assert first.report["result_quality"]["accepted_count"] == 2
    assert first.report["result_quality"]["skipped_count"] == 1
    assert first.report["settings"]["timing_basis"] == "chip"
    assert first.report["settings"]["duration_precision"].endswith("rounded up")
    assert [row["validation_status"] for row in first.result_rows] == [
        "accepted", "accepted", "skipped",
    ]
    assert all("name" not in row and "athlete_id" not in row for row in first.result_rows)
    assert first.result_rows[0]["weather"]["temp_c"] == 12.0
    # A 09:45 midpoint is tied; the established matcher deliberately uses the earlier hour.
    assert first.result_rows[1]["weather"]["temp_c"] == 12.0
    assert first.result_rows[2]["weather"] is None

    args = [
        "report", "--race-input", str(race), "--race-format", "sporthive_json",
        "--weather-csv", str(weather), "--course-id", "folkestone-route",
        "--distance-m", "21097", "--timezone", "Europe/London",
        "--timing-basis", "chip", "--weather-kind", "historical_reanalysis",
    ]
    main(args)
    cli_report = json.loads(capsys.readouterr().out)
    assert cli_report["race"]["event_id"] == "sporthive:event-123"
    assert cli_report["sources"]["weather"]["kind"] == "historical_reanalysis"


def test_sporthive_gun_selection_is_deliberate_and_changes_duration():
    value = copy.deepcopy(snapshot())
    value["pages"][0]["content"][0]["gunTimeOfParticipant"] = "01:00:09.0010000"
    parsed = parse_sporthive_snapshot_json(
        encoded(value).decode(), course_id="folkestone-route", distance_m=21097,
        timing_basis="gun",
    )
    assert parsed.accepted[0].duration_s == 3610
    assert parsed.timing_basis == "gun"
