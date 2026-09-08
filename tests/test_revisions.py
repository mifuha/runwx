from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import socket

import httpx
import pytest

from runwx.services import revisions
from runwx.services.revisions import RevisionSession, prepare_revision


RACE = Path("data/sample_race_synthetic.html")
CORRECTED = Path("data/sample_race_synthetic_corrected.html")
WEATHER = Path("data/sample_lydd_weather_synthetic.csv")
EVENT = "eventrac:900001"
OPTIONS = {
    "event_id": EVENT,
    "weather_source_id": "runwx:synthetic-hourly-weather-demo",
    "snapshot_scope": "complete",
    "race_kind": "synthetic",
    "course_id": "runwx-synthetic-half",
    "distance_m": 21097,
    "timezone_name": "Europe/London",
    "weather_kind": "synthetic",
}


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("revision processing attempted network access")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)


def prepare(race=RACE, weather=WEATHER, **changes):
    return prepare_revision(race, weather, **(OPTIONS | changes))


def test_correction_requires_selection_and_old_replay_cannot_roll_it_back():
    session = RevisionSession()
    original, corrected = prepare(), prepare(CORRECTED)

    first = session.run(original, RACE, WEATHER)
    assert session.selection(EVENT) is None  # Success does not select itself.
    session.select(EVENT, first.revision_id)
    baseline = session.selected_report(EVENT)
    assert baseline["race_summary"]["median_duration_s"] == 7200

    repeat = session.run(original, RACE, WEATHER)
    assert repeat.attempt_id != first.attempt_id
    assert repeat.revision_id == first.revision_id
    assert session.successful_revision_ids == (first.revision_id,)
    assert session.selected_report(EVENT) == baseline

    correction = session.run(corrected, CORRECTED, WEATHER)
    assert correction.revision_id != first.revision_id
    assert session.selected_report(EVENT) == baseline
    chosen = session.select(EVENT, correction.revision_id)
    assert chosen.successful_attempt_id == correction.attempt_id
    report = session.selected_report(EVENT)
    assert report["race_summary"]["median_duration_s"] == 6600
    assert report["race_summary"]["top_n_median_duration_s"] == 6600
    assert report["race_summary"]["finisher_count"] == 3
    assert report["result_quality"] == baseline["result_quality"]
    assert report["weather_coverage"] == baseline["weather_coverage"]
    assert report["weather_coverage"]["matched_count"] == 2

    session.run(original, RACE, WEATHER)  # Finishes later, remains an old revision.
    assert session.selection(EVENT) == chosen
    assert session.selected_report(EVENT) == report
    assert session.report(first.revision_id) == baseline
    assert len(session.attempts) == 4
    assert len(session.successful_revision_ids) == 2


def test_invalid_candidate_records_failed_attempt_and_preserves_selection(tmp_path):
    session = RevisionSession()
    original = prepare()
    session.run(original, RACE, WEATHER)
    selected = session.select(EVENT, original.revision_id)
    baseline = session.selected_report(EVENT)
    bad_weather = tmp_path / "invalid.csv"
    bad_weather.write_text("observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct\n"
                           "not-a-date,8,3,0,70\n")
    invalid = prepare(weather=bad_weather)

    with pytest.raises(ValueError, match="Invalid weather CSV"):
        session.run(invalid, RACE, bad_weather)
    failure = session.attempts[-1]
    assert failure.status == "failed"
    assert failure.revision_id == invalid.revision_id
    assert session.revision(failure.revision_id) == invalid
    assert "ValueError" in failure.error
    with pytest.raises(ValueError, match="successful revision"):
        session.select(EVENT, invalid.revision_id)
    assert session.selection(EVENT) == selected
    assert session.selected_report(EVENT) == baseline


def test_failed_attempt_can_be_retried_without_changing_logical_identity(monkeypatch):
    session, revision = RevisionSession(), prepare()
    real_builder = revisions.build_offline_report

    def interrupted(*args, **kwargs):
        raise RuntimeError("injected processing failure")

    monkeypatch.setattr(revisions, "build_offline_report", interrupted)
    with pytest.raises(RuntimeError, match="injected"):
        session.run(revision, RACE, WEATHER)
    assert not session.successful_revision_ids
    monkeypatch.setattr(revisions, "build_offline_report", real_builder)
    success = session.run(revision, RACE, WEATHER)
    failure = session.attempts[0]
    assert failure.revision_id == success.revision_id
    assert failure.attempt_id != success.attempt_id
    assert [a.status for a in session.attempts] == ["failed", "succeeded"]
    assert session.selection(EVENT) is None


def test_paths_and_attempts_do_not_change_revision_identity(tmp_path):
    race, weather = tmp_path / "moved.html", tmp_path / "moved.csv"
    race.write_bytes(RACE.read_bytes())
    weather.write_bytes(WEATHER.read_bytes())
    original, moved = prepare(), prepare(race, weather)
    assert original == moved
    session = RevisionSession()
    first = session.run(original, RACE, WEATHER)
    second = session.run(moved, race, weather)
    assert first.revision_id == second.revision_id
    assert first.race_file != second.race_file
    assert len(session.successful_revision_ids) == 1


def test_bytes_settings_source_and_code_all_contribute_to_identity(tmp_path):
    original = prepare()
    weather = tmp_path / "changed.csv"
    weather.write_bytes(WEATHER.read_bytes() + b"\n")
    variants = [
        prepare(CORRECTED), prepare(weather=weather), prepare(top_n=1),
        prepare(max_gap=timedelta(0)), prepare(distance_m=21098),
        prepare(timezone_name="UTC"), prepare(course_id="different-course"),
        prepare(weather_source_id="runwx:another-weather-source"),
        prepare(event_id="eventrac:900002"), prepare(weather_kind="unknown"),
        prepare(race_kind="unknown"), replace(original, code_sha256="0" * 64),
    ]
    assert len({original.revision_id, *(r.revision_id for r in variants)}) == 13
    assert original.settings["top_n"] == 20


@pytest.mark.parametrize("scope", ["partial", "unknown"])
def test_partial_or_unverified_snapshot_needs_a_policy(scope):
    with pytest.raises(ValueError, match="complete snapshot"):
        prepare(snapshot_scope=scope)


def test_changed_bytes_or_code_cannot_run_under_old_identity():
    session, original = RevisionSession(), prepare()
    with pytest.raises(ValueError, match="source hashes"):
        session.run(original, CORRECTED, WEATHER)
    with pytest.raises(ValueError, match="processing code"):
        session.run(replace(original, code_sha256="0" * 64), RACE, WEATHER)
    assert all(a.status == "failed" for a in session.attempts)
    assert not session.successful_revision_ids


def test_report_from_another_event_cannot_succeed():
    session = RevisionSession()
    with pytest.raises(ValueError, match="event differs"):
        session.run(prepare(event_id="eventrac:900002"), RACE, WEATHER)
    assert session.attempts[-1].status == "failed"
    assert not session.successful_revision_ids


@pytest.mark.parametrize(("section", "field", "value"), [
    ("result_quality", "accepted_count", 4),
    ("weather_coverage", "matched_count", 3),
    ("weather_coverage", "matched_fraction", 1.0),
])
def test_report_contract_failure_does_not_replace_selected_output(monkeypatch, section, field, value):
    session, original = RevisionSession(), prepare()
    session.run(original, RACE, WEATHER)
    selected = session.select(EVENT, original.revision_id)
    baseline = session.selected_report(EVENT)
    real_builder = revisions.build_offline_report

    def broken_counts(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        report[section][field] = value
        return report

    monkeypatch.setattr(revisions, "build_offline_report", broken_counts)
    with pytest.raises(ValueError, match="counts"):
        session.run(prepare(CORRECTED), CORRECTED, WEATHER)
    assert session.selection(EVENT) == selected
    assert session.selected_report(EVENT) == baseline


def test_conflicting_repeat_fails_without_mutating_success(monkeypatch):
    session, original = RevisionSession(), prepare()
    session.run(original, RACE, WEATHER)
    session.select(EVENT, original.revision_id)
    baseline = session.selected_report(EVENT)
    real_builder = revisions.build_offline_report

    def changed_result(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        report["race_summary"]["median_duration_s"] += 1
        return report

    monkeypatch.setattr(revisions, "build_offline_report", changed_result)
    with pytest.raises(ValueError, match="different analytical output"):
        session.run(original, RACE, WEATHER)
    assert session.attempts[-1].status == "failed"
    assert session.selected_report(EVENT) == baseline
    assert len(session.successful_revision_ids) == 1
    chosen = session.select(EVENT, original.revision_id)
    assert chosen.successful_attempt_id == session.attempts[0].attempt_id


def test_selection_checks_event_and_returned_reports_cannot_mutate_stored_output():
    session, original = RevisionSession(), prepare()
    session.run(original, RACE, WEATHER)
    with pytest.raises(ValueError, match="event"):
        session.select("eventrac:900002", original.revision_id)
    chosen = session.select(EVENT, original.revision_id)
    report = session.selected_report(EVENT)
    report["race_summary"]["finisher_count"] = 999
    original.settings["top_n"] = 999
    assert session.selected_report(EVENT)["race_summary"]["finisher_count"] == 3
    assert original.settings["top_n"] == 20
    assert session.select(EVENT, original.revision_id) == chosen
