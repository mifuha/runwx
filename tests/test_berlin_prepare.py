"""Berlin captures must remain research populations with no invented metadata."""

from copy import deepcopy
from hashlib import sha256
import json
import socket
from urllib.parse import urlencode

import google.auth
import pytest

from runwx.adapters.races.berlin_csv import CATALOG
from runwx.main import main
from runwx.services.berlin_prepare import prepare_berlin


def weather(day):
    return {
        "latitude": 52.5, "longitude": 13.5, "timezone": "Europe/Berlin",
        "utc_offset_seconds": 7200,
        "hourly_units": dict(time="iso8601", temperature_2m="°C", wind_speed_10m="m/s",
                             precipitation="mm", relative_humidity_2m="%"),
        "hourly": {"time": [f"{day}T{h:02}:00" for h in range(24)],
                   "temperature_2m": list(range(24)), "wind_speed_10m": [2.0] * 24,
                   "precipitation": list(range(24)), "relative_humidity_2m": [70.0] * 24},
    }


def request_url(day, **changes):
    params = dict(latitude="52.5163", longitude="13.3777", start_date=day, end_date=day,
                  models="era5", timezone="Europe/Berlin", wind_speed_unit="ms",
                  temperature_unit="celsius", precipitation_unit="mm",
                  hourly="temperature_2m,wind_speed_10m,precipitation,relative_humidity_2m")
    params.update(changes)
    return "https://archive-api.open-meteo.com/v1/archive?" + urlencode(params)


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Berlin preparation attempted network access or credentials")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(google.auth, "default", forbidden)


@pytest.fixture
def batch(tmp_path, monkeypatch):
    # Includes an unselected year, two distinct identical captures, a category that
    # looks numeric, a nonnumeric category and a held time. These are synthetic.
    raw = ("YEAR,COUNTRY,GENDER,AGE,TIME\n"
           "2019,GER,male,35,03:01:00\n"
           "2012,,male,35,03:00:00\n"
           "2015,,female,L1,04:00:00\n"
           "2012,,male,35,03:00:00\n"
           "2012,,female,,no time\n").encode()
    (tmp_path / "race.csv").write_bytes(raw)
    monkeypatch.setitem(CATALOG, "results_sha256", sha256(raw).hexdigest())
    for year, count, genders in [(2012, 3, {"male": 2, "female": 1}),
                                 (2015, 1, {"female": 1})]:
        item = {**CATALOG['editions'][str(year)], "captured_count": count,
                "gender_counts": genders}
        monkeypatch.setitem(CATALOG["editions"], str(year), item)
    editions = []
    for year, day in [(2015, "2015-09-27"), (2012, "2012-09-30")]:
        payload = json.dumps(weather(day)).encode()
        (tmp_path / f"{year}.json").write_bytes(payload)
        editions.append(dict(year=year, weather_json=f"{year}.json",
                             weather_sha256=sha256(payload).hexdigest(),
                             weather_request_url=request_url(day)))
    config = tmp_path / "config.json"
    config.write_text(json.dumps(dict(version=1, race_csv="race.csv", editions=editions)))
    return config, tmp_path / "prepared"


def change_config(config, mutate):
    content = json.loads(config.read_bytes())
    mutate(content)
    config.write_text(json.dumps(content))


def change_weather(config, mutate):
    path = config.parent / "2015.json"
    payload = json.loads(path.read_bytes())
    mutate(payload)
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    change_config(config, lambda c: c["editions"][0].update(weather_sha256=sha256(raw).hexdigest()))


def test_captures_keep_duplicates_unknowns_and_original_locators(batch, monkeypatch, tmp_path):
    config, output = batch
    monkeypatch.chdir(tmp_path.parent)  # Paths must resolve relative to config.
    summary = prepare_berlin(config, output)
    assert (summary["input_record_count"], summary["unselected_record_count"]) == (5, 1)
    assert (summary["captured_count"], summary["accepted_count"], summary["held_count"]) == (4, 3, 1)
    assert [edition["year"] for edition in summary["editions"]] == [2012, 2015]
    rows = [json.loads(line) for line in (output / "2012-09-30.ndjson").read_text().splitlines()]
    assert [row["source_row_number"] for row in rows] == [2, 4, 5]
    assert len({row["source_row_id"] for row in rows}) == 3
    assert [row["duration_s"] for row in rows] == [10800, 10800, None]
    assert rows[-1]["validation_status"] == "held" and rows[-1]["validation_reason"]
    assert rows[0]["age_category_raw"] == "35" and rows[0]["age"] is None
    assert all(row["place"] is None and row["timing_basis"] is None for row in rows)
    assert all("started_at" not in key for row in rows for key in row)
    other = json.loads((output / "2015-09-27.ndjson").read_text())
    assert other["age_category_raw"] == "L1" and other["source_row_number"] == 3
    context = summary["editions"][0]["weather_context"]
    assert context["start_utc"] == "2012-09-30T07:00:00+00:00"
    assert context["end_utc"] == "2012-09-30T13:00:00+00:00"
    assert context["median_temp_c"] == 12 and context["observation_count"] == 7
    assert context["precipitation_mm"] == 75  # 10+11+12+13+14+15, excluding hour ending09:00.
    assert "2012-09-29T22:00:00+00:00" in (output / "2012-09-30.weather.csv").read_text()
    assert json.loads((output / "preparation.json").read_bytes()) == summary


def test_deterministic_artifacts_and_recorded_hashes(batch, tmp_path):
    config, output = batch
    summary = prepare_berlin(config, output)
    other = tmp_path / "repeat"
    assert prepare_berlin(config, other) == summary
    assert {p.name for p in output.iterdir()} == {p.name for p in other.iterdir()}
    assert all(p.read_bytes() == (other / p.name).read_bytes() for p in output.iterdir())
    for edition in summary["editions"]:
        day = edition["race_date"]
        assert sha256((output / f"{day}.ndjson").read_bytes()).hexdigest() == edition["export_sha256"]
        assert sha256((output / f"{day}.weather.csv").read_bytes()).hexdigest() == edition["weather_csv_sha256"]


@pytest.mark.parametrize("mutation,reason", [
    (lambda c: c["editions"].append(deepcopy(c["editions"][0])), "duplicate"),
    (lambda c: c["editions"][0].update(year=2019), "outside"),
    (lambda c: c["editions"][0].update(year=2002), "outside"),
    (lambda c: c["editions"][0].update(year=True), "integer"),
    (lambda c: c.update(unknown=True), "Extra inputs"),
    (lambda c: c["editions"][0].update(weather_sha256="0" * 64), "hash"),
    (lambda c: c["editions"][0].update(weather_request_url=request_url("2015-09-28")), "request"),
    (lambda c: c["editions"][0].update(weather_request_url=request_url("2015-09-27", models="era5_land")), "request"),
    (lambda c: c["editions"][0].update(weather_request_url=request_url("2015-09-27", latitude="0")), "request"),
    (lambda c: c["editions"][0].update(weather_request_url=request_url("2015-09-27", timezone="UTC")), "request"),
    (lambda c: c["editions"][0].update(weather_request_url=request_url("2015-09-27", wind_speed_unit="kmh")), "request"),
])
def test_bad_config_rejected_without_completed_batch(batch, mutation, reason):
    config, output = batch
    change_config(config, mutation)
    with pytest.raises(ValueError, match=reason):
        prepare_berlin(config, output)
    assert not output.exists()


@pytest.mark.parametrize("mutation,reason", [
    (lambda p: p.update(timezone="UTC"), "timezone"),
    (lambda p: p.update(utc_offset_seconds=0), "timezone"),
    (lambda p: p["hourly_units"].update(wind_speed_10m="km/h"), "units"),
    (lambda p: p["hourly"]["time"].__setitem__(0, "2015-09-28T00:00"), "24 local hours"),
    (lambda p: p["hourly"]["temperature_2m"].pop(), "24 local hours"),
    (lambda p: p["hourly"]["temperature_2m"].__setitem__(0, None), "numeric"),
    (lambda p: p["hourly"]["temperature_2m"].__setitem__(0, float("nan")), "finite"),
    (lambda p: p["hourly"]["wind_speed_10m"].__setitem__(0, -1), "non-negative"),
    (lambda p: p["hourly"]["relative_humidity_2m"].__setitem__(0, 101), "between"),
    (lambda p: p.update(longitude=0), "grid"),
])
def test_later_edition_weather_failure_publishes_nothing(batch, mutation, reason):
    config, output = batch
    change_weather(config, mutation)
    with pytest.raises(ValueError, match=reason) as error:
        prepare_berlin(config, output)
    assert "2015" in str(error.value)
    assert not output.exists()


def test_changed_source_and_existing_directory_are_preserved(batch):
    config, output = batch
    source = config.parent / "race.csv"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash"):
        prepare_berlin(config, output)
    output.mkdir()
    (output / "keep").write_text("keep")
    with pytest.raises(FileExistsError):
        prepare_berlin(config, output)
    assert (output / "keep").read_text() == "keep"


def test_count_mismatch_and_duplicate_json_fail(batch, monkeypatch):
    config, output = batch
    monkeypatch.setitem(CATALOG["editions"]["2015"], "captured_count", 2)
    with pytest.raises(ValueError, match="2015: captured population"):
        prepare_berlin(config, output)
    assert not output.exists()
    config.write_text('{"version":1,"version":1}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        prepare_berlin(config, output)


def test_cli_success_and_clean_error(batch, capsys, tmp_path):
    config, output = batch
    main(["prepare-berlin", str(config), "--output", str(output)])
    assert json.loads(capsys.readouterr().out)["edition_count"] == 2
    change_config(config, lambda c: c["editions"][0].update(weather_sha256="0" * 64))
    with pytest.raises(SystemExit) as error:
        main(["prepare-berlin", str(config), "--output", str(tmp_path / "failed")])
    assert error.value.code == 1
    assert "2015" in capsys.readouterr().err


@pytest.mark.parametrize("replacement,reason", [
    (b"YEAR,GENDER,TIME\n2012,male,01:00:00\n", "columns"),
    (b"YEAR,COUNTRY,GENDER,AGE,TIME\n2012,male,35,01:00:00\n", "malformed columns"),
    (b'YEAR,COUNTRY,GENDER,AGE,TIME\n2012,,male,35,"unterminated\n', "malformed Berlin CSV"),
    (b"YEAR,COUNTRY,GENDER,AGE,TIME\nunknown,,male,35,01:00:00\n", "malformed columns or year"),
])
def test_malformed_source_aborts_before_publication(batch, monkeypatch, replacement, reason):
    config, output = batch
    (config.parent / "race.csv").write_bytes(replacement)
    monkeypatch.setitem(CATALOG, "results_sha256", sha256(replacement).hexdigest())
    with pytest.raises(ValueError, match=reason):
        prepare_berlin(config, output)
    assert not output.exists()


def test_unusable_published_total_stays_unknown(batch, monkeypatch):
    config, output = batch
    monkeypatch.setitem(CATALOG["editions"]["2015"], "published_count", None)
    report = prepare_berlin(config, output)["editions"][1]
    assert report["published_count"] is None
    assert report["count_difference_from_published"] is None


def test_output_symlink_is_never_reused(batch, tmp_path):
    config, output = batch
    output.symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(FileExistsError):
        prepare_berlin(config, output)
    assert output.is_symlink() and not (tmp_path / "absent").exists()


def test_reviewed_catalog_keeps_course_population_and_date_boundaries():
    assert set(CATALOG["editions"]) == {str(year) for year in range(2003, 2019)}
    assert sum(edition["captured_count"] for edition in CATALOG["editions"].values()) == 541730
    assert CATALOG["editions"]["2011"]["date"] == "2011-09-25"
    assert CATALOG["editions"]["2008"]["captured_count"] == 35732
    assert CATALOG["editions"]["2008"]["published_count"] == 35653
    assert CATALOG["editions"]["2013"]["published_count"] is None
    assert CATALOG["results_sha256"] == "bcc454bb7382cc34acc0d1fd359b55258bf25eea48323fd7fcb6d3053396c7f2"
