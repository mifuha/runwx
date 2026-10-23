"""The offline preparation boundary must preserve verified snapshot content."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import socket
from urllib.parse import urlencode

import google.auth
import pytest

from runwx.adapters.races import battersea_pdf
from runwx.main import main
from runwx.services import battersea_prepare
from runwx.services.battersea_prepare import prepare_battersea, weather_csv
from runwx.services.snapshot_artifacts import build_snapshot_artifacts


DATES = {"2022-05-21": "21st May 2022", "2019-11-30": "30th November 2019"}
FIELDS = ("temperature_2m", "wind_speed_10m", "precipitation", "relative_humidity_2m")
UNITS = dict(time="iso8601", temperature_2m="°C", wind_speed_10m="m/s",
             precipitation="mm", relative_humidity_2m="%")


def _weather(date):
    return {
        "latitude": 51.5, "longitude": -0.25, "timezone": "GMT",
        "utc_offset_seconds": 0,
        "hourly_units": UNITS.copy(),
        "hourly": {
            "time": [f"{date}T{hour:02d}:00" for hour in range(24)],
            "temperature_2m": [13.5] * 24, "wind_speed_10m": [4.2] * 24,
            "precipitation": [0] * 24, "relative_humidity_2m": [80] * 24,
        },
    }


def _url(date, **changes):
    parameters = dict(latitude="51.4791075", longitude="-0.1564981",
                      start_date=date, end_date=date, models="era5", timezone="UTC",
                      wind_speed_unit="ms", hourly=",".join(FIELDS))
    parameters.update(changes)
    return "https://archive-api.open-meteo.com/v1/archive?" + urlencode(parameters)


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline preparation attempted network access or cloud authentication")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(google.auth, "default", forbidden)


@pytest.fixture
def batch(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    text_by_bytes = {}
    editions = []
    for date, heading in DATES.items():
        pdf = f"%PDF-frozen-test-{date}".encode()
        text_by_bytes[pdf] = (
            f"Sri Chinmoy 10K Race\nBattersea Park, London\n{heading}\n"
            "WINNERS\n1 Winner 00:31:00\nALL RESULTS BELOW\nRESULTS\nRANK NAME TIME\n"
            "1 Runner One Male 00:31:00\n2 Runner Two Female 00:31:00\n"
            "3 Runner Three Male 00:32:01\n"
        )
        monkeypatch.setitem(battersea_pdf.QUALIFIED_EDITIONS, date, {
            "name": "Synthetic test edition", "result_sha256": sha256(pdf).hexdigest(),
            "result_count": 3, "pdf_pages": 1,
        })
        (inputs / f"{date}.pdf").write_bytes(pdf)
        raw = json.dumps(_weather(date)).encode()
        (inputs / f"{date}.json").write_bytes(raw)
        editions.append(dict(date=date, race_pdf=f"inputs/{date}.pdf",
                             weather_json=f"inputs/{date}.json",
                             weather_sha256=sha256(raw).hexdigest(),
                             weather_request_url=_url(date)))

    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self, source):
            self.pages = [Page(text_by_bytes[source.read()])]

    monkeypatch.setattr(battersea_pdf, "PdfReader", Reader)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(dict(version=1, editions=editions)))
    return config, tmp_path / "prepared"


def _change_config(config, change):
    content = json.loads(config.read_text())
    change(content)
    config.write_text(json.dumps(content))


def _change_weather(config, date, change):
    path = config.parent / "inputs" / f"{date}.json"
    payload = json.loads(path.read_bytes())
    change(payload)
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    _change_config(config, lambda content: next(
        item for item in content["editions"] if item["date"] == date
    ).update(weather_sha256=sha256(raw).hexdigest()))


def _without_source_paths(report):
    report = deepcopy(report)
    for source in report["sources"].values():
        source.pop("file", None)
    return report


def test_prepare_reuses_shared_artifacts_and_preserves_winter_summer_starts(batch, monkeypatch, tmp_path):
    config, output = batch
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # Inputs are relative to the config, not cwd.
    summary = prepare_battersea(config, output)
    assert summary["edition_count"] == 2
    assert summary["accepted_count"] == summary["weather_matched_count"] == 6
    assert json.loads((output / "preparation.json").read_text()) == summary
    assert {path.name for path in output.iterdir()} == {"preparation.json"} | {
        f"{date}.{suffix}" for date in DATES
        for suffix in ("weather.csv", "report.json", "ndjson")
    }
    for date in DATES:
        csv = output / f"{date}.weather.csv"
        recorded = next(item for item in summary["editions"] if item["date"] == date)
        for suffix, field in (("weather.csv", "weather_csv_sha256"),
                              ("report.json", "report_sha256"),
                              ("ndjson", "export_sha256")):
            assert recorded[field] == sha256((output / f"{date}.{suffix}").read_bytes()).hexdigest()
        assert recorded["era5_response_sha256"] == sha256(
            (config.parent / "inputs" / f"{date}.json").read_bytes()
        ).hexdigest()
        reference = build_snapshot_artifacts(
            config.parent / "inputs" / f"{date}.pdf", csv,
            course_id="battersea-park-10k", distance_m=10_000,
            timezone_name="Europe/London", race_format="battersea_pdf",
            timing_basis=None, weather_kind="historical_reanalysis", race_kind="historical",
        )
        assert (output / f"{date}.ndjson").read_bytes() == reference.result_payload
        report = json.loads((output / f"{date}.report.json").read_text())
        assert _without_source_paths(report) == _without_source_paths(reference.report)
        hour = "07:30:00" if date.startswith("2022") else "08:30:00"
        assert report["race"]["started_at_utc"] == f"{date}T{hour}+00:00"
        assert report["result_quality"]["candidate_count"] == 3
        assert report["weather_coverage"]["unmatched_count"] == 0
        assert report["settings"]["timing_basis"] is None
        assert report["settings"]["top_n"] == 20
        assert report["settings"]["max_gap_seconds"] == 1800
    again = output.with_name("second-preparation")
    prepare_battersea(config, again)
    for date in DATES:
        assert (output / f"{date}.ndjson").read_bytes() == (again / f"{date}.ndjson").read_bytes()


def test_weather_csv_preserves_retained_converter_bytes():
    date = "2022-05-21"
    expected = "observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct\n" + "".join(
        f"{date}T{hour:02d}:00:00+00:00,13.5,4.2,0,80\n" for hour in range(24)
    )
    assert weather_csv(json.dumps(_weather(date)).encode(), date) == expected.encode()


@pytest.mark.parametrize("key,limit", [("latitude", 90), ("longitude", 180)])
@pytest.mark.parametrize("value", [None, "51.5", True, False, float("nan"),
                                   float("inf"), -float("inf"), 10, 10**400, "out_of_range",
                                   "below_range"])
def test_weather_csv_rejects_invalid_or_distant_grid(key, limit, value):
    date = "2022-05-21"
    payload = _weather(date)
    payload[key] = (limit + 1 if value == "out_of_range" else
                    -limit - 1 if value == "below_range" else value)
    with pytest.raises(ValueError, match="weather grid"):
        weather_csv(json.dumps(payload).encode(), date)


@pytest.mark.parametrize("key", ["latitude", "longitude"])
def test_weather_csv_requires_returned_grid_coordinates(key):
    date = "2022-05-21"
    payload = _weather(date)
    payload.pop(key)
    with pytest.raises(ValueError, match="weather grid"):
        weather_csv(json.dumps(payload).encode(), date)


@pytest.mark.parametrize("key,venue", [
    ("latitude", battersea_pdf.VENUE_LATITUDE),
    ("longitude", battersea_pdf.VENUE_LONGITUDE),
])
@pytest.mark.parametrize("offset", [-0.500001, -0.5, 0.5, 0.500001])
def test_weather_grid_proximity_boundary_preserves_csv_bytes(key, venue, offset):
    date = "2022-05-21"
    payload = _weather(date)
    payload[key] = venue + offset
    raw = json.dumps(payload).encode()
    if abs(offset) > 0.5:
        with pytest.raises(ValueError, match="weather grid"):
            weather_csv(raw, date)
    else:
        assert weather_csv(raw, date) == weather_csv(json.dumps(_weather(date)).encode(), date)


@pytest.mark.parametrize("case", ["duplicate", "held", "pdf_hash", "weather_hash"])
def test_unqualified_or_changed_inputs_fail_without_publishing(batch, case):
    config, output = batch
    if case == "duplicate":
        _change_config(config, lambda c: c["editions"].append(c["editions"][0]))
    elif case == "held":
        _change_config(config, lambda c: c["editions"][0].update(date="2023-08-05"))
    else:
        suffix = "pdf" if case == "pdf_hash" else "json"
        path = config.parent / "inputs" / f"2022-05-21.{suffix}"
        path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        prepare_battersea(config, output)
    assert not output.exists()


@pytest.mark.parametrize("changes", [
    {"start_date": "2022-05-22"}, {"end_date": "2022-05-22"},
    {"latitude": "50.0"}, {"longitude": "0"}, {"models": "era5_land"},
    {"timezone": "Europe/London"}, {"wind_speed_unit": "kmh"},
    {"hourly": "temperature_2m"}, {"temperature_unit": "fahrenheit"},
])
def test_unreviewed_weather_request_settings_are_rejected(batch, changes):
    config, output = batch
    _change_config(config, lambda c: c["editions"][0].update(
        weather_request_url=_url("2022-05-21", **changes)))
    with pytest.raises(ValueError):
        prepare_battersea(config, output)
    assert not output.exists()


@pytest.mark.parametrize("rewrite", [
    lambda url: url.replace("https:", "http:"),
    lambda url: url.replace("archive-api.open-meteo.com", "unreviewed.example"),
    lambda url: url.replace("/v1/archive?", "/v1/forecast?"),
    lambda url: url + "&models=era5_land",
    lambda url: url + "#unreviewed",
])
def test_unreviewed_weather_url_or_repeated_parameters_are_rejected(batch, rewrite):
    config, output = batch
    _change_config(config, lambda c: c["editions"][0].update(
        weather_request_url=rewrite(_url("2022-05-21"))))
    with pytest.raises(ValueError):
        prepare_battersea(config, output)
    assert not output.exists()


@pytest.mark.parametrize("change", [
    lambda p: p.update(latitude=0.0, longitude=0.0),
    lambda p: p.pop("latitude"),
    lambda p: p["hourly_units"].update(wind_speed_10m="km/h"),
    lambda p: p.update(utc_offset_seconds=3600),
    lambda p: p["hourly"]["time"].__setitem__(0, "2019-11-29T00:00"),
    lambda p: p["hourly"]["time"].pop(),
    lambda p: p["hourly"]["temperature_2m"].pop(),
    lambda p: p["hourly"]["temperature_2m"].__setitem__(8, None),
    lambda p: p["hourly"]["temperature_2m"].__setitem__(23, float("nan")),
    lambda p: p["hourly"]["relative_humidity_2m"].__setitem__(23, 101),
])
def test_later_invalid_weather_leaves_no_completed_batch(batch, change, monkeypatch):
    config, output = batch
    built = []

    def observe_build(*args, **kwargs):
        artifacts = build_snapshot_artifacts(*args, **kwargs)
        built.append(artifacts.report["race"]["started_at_utc"][:10])
        return artifacts

    monkeypatch.setattr(battersea_prepare, "build_snapshot_artifacts", observe_build)
    _change_weather(config, "2022-05-21", change)
    with pytest.raises(ValueError, match="2022-05-21"):
        prepare_battersea(config, output)
    assert built == ["2019-11-30"]
    assert not output.exists()


def test_existing_directory_and_files_are_preserved(batch):
    config, output = batch
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"previous work")
    with pytest.raises((FileExistsError, ValueError)):
        prepare_battersea(config, output)
    assert list(output.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"previous work"


def test_cli_failure_identifies_edition_and_hash_reason(batch, capsys):
    config, output = batch
    _change_config(config, lambda c: c["editions"][0].update(weather_sha256="0" * 64))
    with pytest.raises(SystemExit) as failure:
        main(["prepare-battersea", str(config), "--output", str(output)])
    assert failure.value.code != 0
    error = capsys.readouterr().err
    assert "2022-05-21" in error
    assert "hash" in error.lower() or "sha256" in error.lower()
    assert not output.exists()
