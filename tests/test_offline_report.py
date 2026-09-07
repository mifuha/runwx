import hashlib
import json
import socket
from pathlib import Path

import httpx
import pytest

from runwx.main import main


WEATHER_HEADER = "observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct\n"
WEATHER_ROW = "2022-03-06T10:30:00+00:00,8.0,3.5,0.0,70.0\n"
HTML = """<!doctype html>
<link rel="canonical" href="https://example.invalid/results/123">
<script type="application/ld+json">
{"location": {"geo": {"latitude": 50.95, "longitude": 0.90}}}
</script>
<div class="box-header"><h3 class="box-title">Synthetic Half Results</h3>
<small>06/03/2022, 10:00</small></div>
<table id="results">
<thead><tr><th>Position</th><th>Gender</th><th>Time</th></tr></thead>
<tbody>
<tr><td>1</td><td>Male</td><td>01:00:00</td></tr>
<tr><td>2</td><td>Female</td><td>02:00:00</td></tr>
<tr><td>3</td><td>Male</td><td></td></tr>
<tr><td>4</td><td>Female</td><td>bad-time</td></tr>
</tbody></table>
"""


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline report attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)


@pytest.fixture
def inputs(tmp_path):
    race = tmp_path / "race.html"
    weather = tmp_path / "weather.csv"
    race.write_text(HTML, encoding="utf-8")
    weather.write_text(WEATHER_HEADER + WEATHER_ROW, encoding="utf-8")
    return race, weather


def arguments(race, weather):
    return [
        "report", "--race-html", str(race), "--weather-csv", str(weather),
        "--course-id", "synthetic-half", "--distance-m", "21097",
        "--timezone", "Europe/London", "--max-gap-min", "15",
        "--top-n", "1", "--weather-kind", "synthetic",
    ]


def test_offline_cli_repeats_identically_and_keeps_quality_and_coverage_separate(inputs, capsys):
    race, weather = inputs
    args = arguments(race, weather)
    main(args)
    first = capsys.readouterr().out
    main(args)
    second = capsys.readouterr().out

    assert first == second
    report = json.loads(first)
    assert report["race"]["event_id"] == "eventrac:123"
    assert report["race"]["started_at_utc"] == "2022-03-06T10:00:00+00:00"
    assert report["race_summary"] == {
        "finisher_count": 2, "best_duration_s": 3600,
        "mean_duration_s": 5400, "median_duration_s": 5400,
        "top_n_median_duration_s": 3600,
    }
    assert report["result_quality"]["candidate_count"] == 4
    assert report["result_quality"]["accepted_count"] == 2
    assert report["result_quality"]["skipped_count"] == 1
    assert report["result_quality"]["invalid_count"] == 1
    assert report["result_quality"]["skipped"] == [
        {"row_number": 3, "reason": "missing finish time"},
    ]
    assert report["result_quality"]["invalid"][0]["row_number"] == 4
    assert report["weather_coverage"] == {
        "accepted_result_count": 2, "matched_count": 1, "unmatched_count": 1,
        "matched_fraction": 0.5, "status": "partial",
        "unmatched_reasons": {"No weather within 0:15:00": 1},
    }
    assert report["weather_summary"]["median_temp_c"] == 8.0
    assert report["weather_summary"]["enriched_count"] == 1
    assert report["sources"]["race"]["sha256"] == hashlib.sha256(race.read_bytes()).hexdigest()
    assert report["sources"]["weather"]["sha256"] == hashlib.sha256(weather.read_bytes()).hexdigest()
    assert report["sources"]["weather"]["kind"] == "synthetic"
    assert report["settings"]["max_gap_seconds"] == 900
    assert report["settings"]["top_n"] == 1
    assert report["settings"]["timezone_name"] == "Europe/London"
    assert report["settings"]["timing_basis"] is None
    assert any("synthetic" in text.lower() for text in report["limitations"])


@pytest.mark.parametrize("saved_weather", [WEATHER_HEADER, WEATHER_HEADER + WEATHER_ROW.replace("10:30", "16:30")])
def test_no_eligible_weather_retains_race_summary_and_reports_unavailable(inputs, capsys, saved_weather):
    race, weather = inputs
    weather.write_text(saved_weather, encoding="utf-8")
    main(arguments(race, weather))
    report = json.loads(capsys.readouterr().out)

    assert report["race_summary"]["finisher_count"] == 2
    assert report["weather_summary"] is None
    assert report["weather_coverage"]["matched_count"] == 0
    assert report["weather_coverage"]["unmatched_count"] == 2
    assert report["weather_coverage"]["matched_fraction"] == 0.0
    assert report["weather_coverage"]["status"] == "unavailable"


def test_all_rejected_rows_have_no_invented_summary_or_coverage(inputs, capsys):
    race, weather = inputs
    race.write_text(HTML.replace("01:00:00", "").replace("02:00:00", ""), encoding="utf-8")
    main(arguments(race, weather))
    report = json.loads(capsys.readouterr().out)

    assert report["result_quality"]["candidate_count"] == 4
    assert report["result_quality"]["accepted_count"] == 0
    assert report["race_summary"] is None
    assert report["weather_summary"] is None
    assert report["weather_coverage"]["matched_fraction"] is None
    assert report["weather_coverage"]["status"] == "not_applicable"


def test_changed_settings_change_coverage_without_changing_source_identity(inputs, capsys):
    race, weather = inputs
    args = arguments(race, weather)
    main(args)
    first = json.loads(capsys.readouterr().out)
    args[args.index("--max-gap-min") + 1] = "30"
    main(args)
    second = json.loads(capsys.readouterr().out)

    assert first["sources"] == second["sources"]
    assert first["race_summary"] == second["race_summary"]
    assert second["settings"]["max_gap_seconds"] == 1800
    assert second["weather_coverage"]["matched_count"] == 2
    assert second["weather_coverage"]["status"] == "complete"


def test_changed_top_n_changes_summary_without_changing_sources_or_coverage(inputs, capsys):
    race, weather = inputs
    args = arguments(race, weather)
    main(args)
    first = json.loads(capsys.readouterr().out)

    args[args.index("--top-n") + 1] = "2"
    main(args)
    second = json.loads(capsys.readouterr().out)

    assert first["settings"]["top_n"] == 1
    assert second["settings"]["top_n"] == 2
    assert first["race_summary"]["top_n_median_duration_s"] == 3600
    assert second["race_summary"]["top_n_median_duration_s"] == 5400
    assert first["sources"] == second["sources"]
    assert first["weather_coverage"] == second["weather_coverage"]


def test_changed_weather_bytes_change_hash_and_weather_summary_only(inputs, capsys):
    race, weather = inputs
    main(arguments(race, weather))
    first = json.loads(capsys.readouterr().out)
    weather.write_text(WEATHER_HEADER + WEATHER_ROW.replace(",8.0,", ",9.0,"), encoding="utf-8")
    main(arguments(race, weather))
    second = json.loads(capsys.readouterr().out)

    assert first["sources"]["race"] == second["sources"]["race"]
    assert first["sources"]["weather"]["sha256"] != second["sources"]["weather"]["sha256"]
    assert first["race_summary"] == second["race_summary"]
    assert second["weather_summary"]["median_temp_c"] == 9.0


@pytest.mark.parametrize(("flag", "value", "message"), [
    ("--max-gap-min", "-1", "max_gap must be non-negative"),
    ("--top-n", "0", "top_n must be positive"),
])
def test_invalid_settings_fail_before_printing_a_report(inputs, capsys, flag, value, message):
    args = arguments(*inputs)
    args[args.index(flag) + 1] = value
    with pytest.raises(ValueError, match=message):
        main(args)
    assert capsys.readouterr().out == ""


def test_invalid_weather_fails_without_a_report(inputs, capsys):
    race, weather = inputs
    weather.write_text(WEATHER_HEADER + "not-a-date,8,3,0,70\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid weather CSV row 2"):
        main(arguments(race, weather))
    assert capsys.readouterr().out == ""


def test_saved_lydd_report_runs_twice_without_network(capsys):
    args = arguments(
        Path("data/raw/eventrac/lydd_half_2022.html"),
        Path("data/sample_lydd_weather_synthetic.csv"),
    )
    args[args.index("--max-gap-min") + 1] = "30"
    main(args)
    first = capsys.readouterr().out
    main(args)
    assert first == capsys.readouterr().out
    report = json.loads(first)

    assert report["race"]["name"] == "Lydd Half Marathon 2022"
    assert report["race_summary"]["finisher_count"] == 189
    assert report["result_quality"]["candidate_count"] == 189
    assert report["result_quality"]["skipped_count"] == 0
    assert report["result_quality"]["invalid_count"] == 0
    coverage = report["weather_coverage"]
    assert coverage["matched_count"] + coverage["unmatched_count"] == 189
    assert coverage["matched_count"] > 0


def test_unlabelled_weather_origin_stays_unknown(inputs, capsys):
    args = arguments(*inputs)
    del args[-2:]  # Omit the explicit synthetic label.
    main(args)
    report = json.loads(capsys.readouterr().out)

    assert report["sources"]["weather"]["kind"] == "unknown"
    assert "Weather origin is unknown" in report["limitations"][0]


def test_byte_only_source_change_updates_hash_without_changing_analytics(inputs, capsys):
    race, weather = inputs
    main(arguments(race, weather))
    first = json.loads(capsys.readouterr().out)
    race.write_bytes(race.read_bytes().replace(b"\n", b"\r\n"))
    weather.write_bytes(weather.read_bytes().replace(b"\n", b"\r\n"))
    main(arguments(race, weather))
    second = json.loads(capsys.readouterr().out)

    for key in ("race_summary", "result_quality", "weather_coverage", "weather_summary", "settings"):
        assert first[key] == second[key]
    for key, path in (("race", race), ("weather", weather)):
        assert second["sources"][key]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert first["sources"][key]["sha256"] != second["sources"][key]["sha256"]
