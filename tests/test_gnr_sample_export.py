"""Synthetic provider-shaped inputs: no personal result data or network access."""

from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
import socket
from urllib.parse import urlencode

import pytest

from runwx.main import main
from runwx.services.gnr_sample_export import build_gnr_sample_rows
from runwx.services.result_export import encode_result_rows


def duration(seconds):
    return f"{seconds // 3600:02}:{seconds % 3600 // 60:02}:{seconds % 60:02}"


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline GNR export attempted network access")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    race = {
        "success": True,
        "raceDetail": {"idRace": 881, "raceDate": "2019-09-08T00:00:00", "distanceInKm": 21.1},
        "resultMen": [], "resultWomen": [],
    }
    for group, offset in (("resultMen", 0), ("resultWomen", 1000)):
        race[group] = [{
            "idResult": offset + i + 1, "idRace": 881, "idRaceCategory": 1,
            "wheelchair": 0, "eventRace": "Mass", "gunChip": "C",
            "timeFinish": duration(4000 + offset // 2 + i),
            "name": "PERSONAL DATA MUST NOT BE EXPORTED", "dateOfBirth": "1970-01-01",
        } for i in range(1000)]
    race["resultMen"][0]["wheelchair"] = 1
    race["resultMen"][1]["idRaceCategory"] = 2
    race["resultMen"][2]["gunChip"] = None
    race["resultMen"][3]["gunChip"] = "G"
    categories = [{"value": "1", "text": "Orange B"}, {"value": "2", "text": "Hand Cycle"}]
    weather = {
        "timezone": "GMT", "utc_offset_seconds": 0, "latitude": 55.0, "longitude": -1.5,
        "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "wind_speed_10m": "m/s",
                         "precipitation": "mm", "relative_humidity_2m": "%"},
        "hourly": {
            "time": [f"2019-09-08T{h:02}:00" for h in range(24)],
            "temperature_2m": [h - 10 for h in range(24)],
            "wind_speed_10m": [h / 10 for h in range(24)],
            "relative_humidity_2m": [50 + h for h in range(24)],
            "precipitation": list(range(24)),
        },
    }
    params = {
        "latitude": 54.984, "longitude": -1.62,
        "start_date": "2019-09-08", "end_date": "2019-09-08",
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "models": "era5", "timezone": "UTC", "temperature_unit": "celsius",
        "wind_speed_unit": "ms", "precipitation_unit": "mm",
    }
    request = {"params": params, "provider": "Open-Meteo", "dataset": "ERA5", "status": 200,
               "url": "https://archive-api.open-meteo.com/v1/archive?" + urlencode(params)}

    def write(race=race, categories=categories, weather=weather, request=request):
        options = {"race_id": 881, "race_date": date(2019, 9, 8)}
        for name, payload in (("race", race), ("categories", categories), ("weather", weather)):
            raw = json.dumps(payload).encode()
            path = tmp_path / f"{name}.json"
            path.write_bytes(raw)
            options[f"{name}_json"] = path
            options[f"{name}_sha256"] = sha256(raw).hexdigest()
        request = {**request, "sha256": options["weather_sha256"],
                   "bytes": options["weather_json"].stat().st_size}
        path = tmp_path / "request.json"
        path.write_text(json.dumps(request))
        options["weather_request"] = path
        return options
    return race, categories, weather, request, write


def cli(options):
    args = ["export-gnr-sample"]
    for name, value in options.items():
        args.extend(["--" + name.replace("_", "-"), str(value)])
    return args


def test_selection_preserves_unknown_timing_and_excludes_explicit_categories(inputs, capsys):
    *_, write = inputs
    options = write()
    rows = build_gnr_sample_rows(**options)
    assert len(rows) == 1000
    assert rows[0]["duration_s"] == 4002
    assert rows[0]["source_row_number"] == 3
    assert rows[0]["timing_basis"] == "unknown"
    assert rows[1]["timing_basis"] == "gun"
    assert rows[-1]["duration_s"] == 4750
    assert rows[-2]["source_row_number"] == 751  # Result ID breaks a time tie.
    assert rows[-1]["source_row_number"] == 1251
    assert rows[0]["sample"]["excluded_count"] == 2
    assert rows[0]["sample"]["unselected_count"] == 998
    assert rows[0]["sample"]["cutoff_ties_available"] == 2
    assert rows[0]["sample"]["size"] == 1000
    assert [r["sample_rank"] for r in rows] == list(range(1, 1001))
    assert len({r["source_row_id"] for r in rows}) == 1000
    payload = encode_result_rows(rows)
    assert b"PERSONAL DATA" not in payload and b"dateOfBirth" not in payload
    assert "started_at_utc" not in rows[0] and "place" not in rows[0]
    assert "weather_match_status" not in rows[0]
    main(cli(options))
    assert capsys.readouterr().out.encode() == payload
    main(cli(options))
    assert capsys.readouterr().out.encode() == payload


def test_weather_is_bst_window_with_correct_precipitation_intervals(inputs):
    *_, write = inputs
    rows = build_gnr_sample_rows(**write())
    context = rows[0]["weather_context"]
    assert context["start_utc"] == "2019-09-08T09:00:00+00:00"
    assert context["end_utc"] == "2019-09-08T13:00:00+00:00"
    assert context["median_temp_c"] == 1
    assert context["median_wind_mps"] == 1.1
    assert context["median_humidity_pct"] == 61
    assert context["precipitation_mm"] == 46  # UTC 10+11+12+13, not 9+10+11+12+13.
    assert context["basis"] == "fixed_event_window"
    assert rows[-1]["weather_context"] == context


@pytest.mark.parametrize("case", [
    "duplicate_id", "wrong_race", "wrong_day", "changed_route", "unordered", "zero_time",
    "bad_time", "timing_flag", "missing_timing", "unmapped_category", "duplicate_category", "unqualified_race",
    "boolean_id", "short_list", "truncated_tie", "wrong_distance", "wrong_event",
])
def test_invalid_source_fails_before_cli_output(inputs, capsys, case):
    race, categories, _, _, write = inputs
    row = race["resultMen"][10]
    if case == "duplicate_id": row["idResult"] = 1
    if case == "wrong_race": row["idRace"] = 882
    if case == "unqualified_race":
        race["raceDetail"]["idRace"] = 882
        for r in race["resultMen"] + race["resultWomen"]: r["idRace"] = 882
    if case == "wrong_day": race["raceDetail"]["raceDate"] = "2019-09-09T00:00:00"
    if case == "changed_route": race["raceDetail"]["raceDate"] = "2021-09-12T00:00:00"
    if case == "unordered": row["timeFinish"] = "00:50:00"
    if case == "zero_time": row["timeFinish"] = "00:00:00"
    if case == "bad_time": row["timeFinish"] = "01:70:00"
    if case == "timing_flag": row["gunChip"] = "X"
    if case == "missing_timing": del row["gunChip"]
    if case == "unmapped_category": row["idRaceCategory"] = 999
    if case == "duplicate_category": categories.append(deepcopy(categories[0]))
    if case == "boolean_id": row["idResult"] = True
    if case == "short_list": race["resultWomen"].pop()
    if case == "truncated_tie":
        for r in race["resultMen"] + race["resultWomen"]: r["timeFinish"] = "01:30:00"
    if case == "wrong_distance": race["raceDetail"]["distanceInKm"] = 10.0
    if case == "wrong_event": row["eventRace"] = "Elite"
    options = write()
    if case == "changed_route": options["race_date"] = date(2021, 9, 12)
    if case == "unqualified_race": options["race_id"] = 882
    with pytest.raises(ValueError):
        main(cli(options))
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("case", [
    "units", "missing_hour", "duplicate_hour", "wrong_date", "infinity", "humidity",
    "timezone", "grid", "model", "request_date", "request_url", "request_hash",
])
def test_invalid_weather_fails_before_cli_output(inputs, capsys, case):
    _, _, weather, request, write = inputs
    if case == "units": weather["hourly_units"]["wind_speed_10m"] = "km/h"
    if case == "missing_hour":
        for values in weather["hourly"].values(): values.pop()
    if case == "duplicate_hour": weather["hourly"]["time"][10] = weather["hourly"]["time"][9]
    if case == "wrong_date": weather["hourly"]["time"][0] = "2018-09-08T00:00"
    if case == "infinity": weather["hourly"]["temperature_2m"][0] = float("inf")
    if case == "humidity": weather["hourly"]["relative_humidity_2m"][0] = 101
    if case == "timezone": weather["utc_offset_seconds"] = 3600
    if case == "grid": weather["latitude"] = 20.0
    if case == "model": request["params"]["models"] = "best_match"
    if case == "request_date": request["params"]["start_date"] = "2018-09-08"
    if case == "request_url": request["url"] = "https://example.com/"
    options = write()
    if case == "request_hash":
        p = options["weather_request"]
        data = json.loads(p.read_bytes()); data["sha256"] = "0" * 64
        p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        main(cli(options))
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("source", ["race", "categories", "weather"])
def test_hash_mismatch_rejected(inputs, source):
    *_, write = inputs
    options = write(); options[f"{source}_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_gnr_sample_rows(**options)


def test_duplicate_json_fields_are_rejected(inputs):
    *_, write = inputs
    options = write()
    path = options["race_json"]
    raw = path.read_bytes().replace(b'"success": true', b'"success": false, "success": true')
    path.write_bytes(raw); options["race_sha256"] = sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="duplicate JSON field"):
        build_gnr_sample_rows(**options)


def test_corrected_snapshot_has_distinct_source_identity(inputs):
    *_, write = inputs
    options = write()
    original = build_gnr_sample_rows(**options)
    path = options["race_json"]; raw = path.read_bytes() + b"\n"; path.write_bytes(raw)
    options["race_sha256"] = sha256(raw).hexdigest()
    corrected = build_gnr_sample_rows(**options)
    assert corrected[0]["source_row_id"] != original[0]["source_row_id"]
    assert [r["duration_s"] for r in corrected] == [r["duration_s"] for r in original]


def test_sample_cannot_be_loaded_as_full_field(inputs):
    from runwx.adapters.bigquery.result_load import prepare_load
    *_, write = inputs
    # One row is enough to prove schema rejection, without hitting the load size cap.
    payload = encode_result_rows(build_gnr_sample_rows(**write())[:1])
    with pytest.raises(ValueError, match="row fields"):
        prepare_load(payload, table_id="test-project.sample.results", expected_sha256=sha256(payload).hexdigest())
