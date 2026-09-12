import hashlib
import json
import socket
from collections import Counter
from pathlib import Path

import httpx
import pytest

from runwx.main import main
from runwx.services.offline_report import build_offline_report
from runwx.services.result_export import build_result_rows, encode_result_rows


RACE = Path("data/sample_race_synthetic.html")
WEATHER = Path("data/sample_lydd_weather_synthetic.csv")
SETTINGS = {
    "course_id": "runwx-synthetic-half",
    "distance_m": 21097,
    "timezone_name": "Europe/London",
    "weather_kind": "synthetic",
}


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("local result export attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)


def export(capsys, race=RACE, weather=WEATHER, gap=30):
    main([
        "export-results", "--race-html", str(race), "--weather-csv", str(weather),
        "--course-id", SETTINGS["course_id"], "--distance-m", "21097",
        "--timezone", "Europe/London", "--max-gap-min", str(gap),
        "--race-kind", "synthetic", "--weather-kind", "synthetic",
    ])
    output = capsys.readouterr().out
    return output, [json.loads(line) for line in output.splitlines()]


def test_synthetic_export_reconciles_with_report_and_repeats_offline(capsys):
    first, rows = export(capsys)
    second, _ = export(capsys)
    report = build_offline_report(RACE, WEATHER, **SETTINGS)
    assert first.encode("utf-8") == encode_result_rows(rows)

    assert first == second
    assert len(rows) == report["result_quality"]["candidate_count"] == 5
    assert Counter(row["validation_status"] for row in rows) == {
        "accepted": 3, "skipped": 1, "invalid": 1,
    }
    for status in ("accepted", "skipped", "invalid"):
        assert sum(row["validation_status"] == status for row in rows) == report[
            "result_quality"
        ][f"{status}_count"]
    assert [row["source_row_number"] for row in rows] == [1, 2, 3, 4, 5]
    assert len({row["source_row_id"] for row in rows}) == 5
    assert [row["duration_s"] for row in rows] == [3600, 7200, 14400, None, None]
    assert [row["weather_match_status"] for row in rows] == [
        "matched", "matched", "unmatched", "not_applicable", "not_applicable",
    ]
    assert sum(row["weather_match_status"] == "matched" for row in rows) == report[
        "weather_coverage"
    ]["matched_count"] == 2
    assert rows[0]["weather"]["observed_at_utc"] == "2022-03-06T10:00:00+00:00"
    assert rows[0]["weather"]["temp_c"] == 8.5  # Midpoint tie chooses earlier hour.
    assert rows[1]["weather"]["observed_at_utc"] == "2022-03-06T11:00:00+00:00"
    assert rows[2]["weather_match_reason"] == "No weather within 0:30:00"
    assert rows[3]["validation_reason"] == "missing finish time"
    assert "invalid finish time" in rows[4]["validation_reason"]
    for row in rows[2:]:
        assert row["weather"] is None
    for row in rows:
        assert row["export_schema_version"] == 1
        assert row["event_id"] == "eventrac:900001"
        assert row["course_id"] == SETTINGS["course_id"]
        assert row["distance_m"] == 21097
        assert row["race_kind"] == row["weather_kind"] == "synthetic"
        assert row["race_sha256"] == report["sources"]["race"]["sha256"]
        assert row["weather_sha256"] == report["sources"]["weather"]["sha256"]
        assert row["settings"]["timing_basis"] is None
        assert row["settings"]["max_gap_seconds"] == 1800


def test_source_row_ids_keep_identical_finishers_distinct_after_rejected_rows(tmp_path, capsys):
    # The accepted rows now occur at 1, 3 and 5; all three have identical values.
    html = RACE.read_text(encoding="utf-8")
    html = html.replace("<td>2</td><td>Female</td><td>02:00:00", "<td>2</td><td>Female</td><td>")
    html = html.replace("<td>3</td><td>Male</td><td>04:00:00", "<td>1</td><td>Male</td><td>01:00:00")
    html = html.replace("<td>4</td><td>Female</td><td>", "<td>4</td><td>Female</td><td>bad-time")
    html = html.replace("<td>5</td><td>Male</td><td>bad-time", "<td>1</td><td>Male</td><td>01:00:00")
    race = tmp_path / "duplicates.html"
    race.write_text(html, encoding="utf-8")

    _, rows = export(capsys, race=race)
    accepted = [row for row in rows if row["validation_status"] == "accepted"]

    assert [row["source_row_number"] for row in accepted] == [1, 3, 5]
    assert [row["place"] for row in accepted] == [1, 1, 1]
    assert [row["duration_s"] for row in accepted] == [3600, 3600, 3600]
    assert len({row["source_row_id"] for row in accepted}) == 3
    assert all(row["weather_match_status"] == "matched" for row in accepted)


def test_settings_change_coverage_but_not_source_row_identity(capsys):
    _, broad = export(capsys)
    _, narrow = export(capsys, gap=0)

    assert [row["source_row_id"] for row in broad] == [row["source_row_id"] for row in narrow]
    assert narrow[0]["weather_match_status"] == "unmatched"
    assert narrow[1]["weather_match_status"] == "matched"
    assert narrow[0]["duration_s"] == broad[0]["duration_s"]
    assert narrow[0]["settings"]["max_gap_seconds"] == 0
    assert narrow[0]["race_sha256"] == broad[0]["race_sha256"]
    assert narrow[0]["weather_sha256"] == broad[0]["weather_sha256"]


def test_moved_inputs_repeat_identically_but_changed_bytes_change_provenance(tmp_path, capsys):
    original, before = export(capsys)
    race = tmp_path / "moved.html"
    weather = tmp_path / "moved.csv"
    race.write_bytes(RACE.read_bytes())
    weather.write_bytes(WEATHER.read_bytes())
    moved, _ = export(capsys, race, weather)
    assert moved == original

    weather.write_bytes(weather.read_bytes().replace(b",8.5,", b",7.5,"))
    _, changed_weather = export(capsys, race, weather)
    assert changed_weather[0]["weather"]["temp_c"] == 7.5
    assert changed_weather[0]["weather_sha256"] != before[0]["weather_sha256"]
    assert [row["source_row_id"] for row in changed_weather] == [row["source_row_id"] for row in before]

    race.write_bytes(race.read_bytes() + b"\n")
    _, changed_race = export(capsys, race, weather)
    assert changed_race[0]["race_sha256"] == hashlib.sha256(race.read_bytes()).hexdigest()
    assert not {row["source_row_id"] for row in before} & {row["source_row_id"] for row in changed_race}
    assert [row["duration_s"] for row in changed_race] == [row["duration_s"] for row in before]


def test_empty_weather_keeps_accepted_results(tmp_path, capsys):
    weather = tmp_path / "empty.csv"
    weather.write_bytes(WEATHER.read_bytes().splitlines(keepends=True)[0])
    _, rows = export(capsys, weather=weather)

    assert [row["duration_s"] for row in rows[:3]] == [3600, 7200, 14400]
    assert all(row["weather_match_status"] == "unmatched" for row in rows[:3])
    assert all(row["weather"] is None for row in rows)


def test_all_rejected_rows_have_no_invented_results_or_weather(tmp_path, capsys):
    race = tmp_path / "rejected.html"
    html = RACE.read_text(encoding="utf-8")
    for duration in ("01:00:00", "02:00:00", "04:00:00"):
        html = html.replace(duration, "")
    race.write_text(html, encoding="utf-8")
    _, rows = export(capsys, race=race)

    assert len(rows) == 5
    assert Counter(row["validation_status"] for row in rows) == {"skipped": 4, "invalid": 1}
    assert all(row["duration_s"] is None and row["place"] is None for row in rows)
    assert all(row["weather_match_status"] == "not_applicable" for row in rows)


def test_unlabelled_sources_remain_unknown():
    settings = {key: value for key, value in SETTINGS.items() if key != "weather_kind"}
    rows = build_result_rows(RACE, WEATHER, **settings)

    assert all(row["race_kind"] == row["weather_kind"] == "unknown" for row in rows)


def test_historical_export_records_supplied_interpretation_without_changing_results(capsys):
    # Synthetic bytes exercise the flags; this fixture is not historical evidence.
    baseline = build_result_rows(RACE, WEATHER, **SETTINGS)
    arguments = [
        "export-results", "--race-html", str(RACE), "--weather-csv", str(WEATHER),
        "--course-id", SETTINGS["course_id"], "--distance-m", "21097",
        "--timezone", "Europe/London", "--race-kind", "historical",
        "--weather-kind", "historical_reanalysis", "--timing-basis", "chip",
    ]
    main(arguments)
    first = capsys.readouterr().out
    main(arguments)
    assert capsys.readouterr().out == first
    rows = [json.loads(line) for line in first.splitlines()]
    for actual, expected in zip(rows, baseline, strict=True):
        assert actual.pop("race_kind") == "historical"
        assert actual.pop("weather_kind") == "historical_reanalysis"
        assert actual["settings"]["timing_basis"] == "chip"
        actual["settings"]["timing_basis"] = None
        expected.pop("race_kind")
        expected.pop("weather_kind")
        assert actual == expected


def test_export_rejects_unsupported_timing_interpretation():
    with pytest.raises(ValueError, match="timing_basis"):
        build_result_rows(RACE, WEATHER, **SETTINGS, timing_basis="inferred")


def test_unexpected_matching_failure_does_not_become_a_skipped_row(monkeypatch, capsys):
    def broken_matcher(*args, **kwargs):
        raise RuntimeError("unexpected matcher failure")

    monkeypatch.setattr("runwx.services.result_export.nearest_weather", broken_matcher)
    with pytest.raises(RuntimeError, match="unexpected matcher failure"):
        export(capsys)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("input_kind", ["race", "weather", "settings"])
def test_invalid_input_fails_without_partial_stdout(tmp_path, capsys, input_kind):
    race, weather, gap = RACE, WEATHER, 30
    if input_kind == "race":
        race = tmp_path / "bad.html"
        race.write_text("<html></html>", encoding="utf-8")
    elif input_kind == "weather":
        weather = tmp_path / "bad.csv"
        weather.write_bytes(WEATHER.read_bytes().replace(b"2022-03-06", b"not-a-date"))
    else:
        gap = -1

    with pytest.raises(ValueError):
        export(capsys, race, weather, gap)
    assert capsys.readouterr().out == ""
