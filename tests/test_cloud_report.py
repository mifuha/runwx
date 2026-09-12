"""Exercise the storage boundary with saved bytes and no credentials/network."""

import copy
import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import Mock
import runpy

import pytest

import runwx.services.snapshot_artifacts as snapshot_artifacts
from runwx.adapters.gcs.report_io import run_stored_report
from runwx.cloud_report import main
from runwx.services.offline_report import build_offline_report
from runwx.services.result_export import build_result_rows, encode_result_rows


ROOT = Path(__file__).resolve().parents[1]
RACE = ROOT / "data/sample_race_synthetic.html"
WEATHER = ROOT / "data/sample_lydd_weather_synthetic.csv"
SETTINGS = dict(course_id="runwx-synthetic-half", distance_m=21097,
                timezone_name="Europe/London", weather_kind="synthetic")
compare_reports = runpy.run_path(ROOT / "scripts/compare_cloud_report.py")["compare_reports"]


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("local cloud-boundary test attempted network access")
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def storage():
    blobs = {}
    saved = {}

    def blob(bucket, name):
        key = (bucket, name)
        if key not in blobs:
            obj = Mock(generation=17)

            def upload(data, *, content_type, if_generation_match, timeout):
                expected_type = (
                    "application/x-ndjson" if name.endswith(".ndjson")
                    else "application/json"
                )
                assert content_type == expected_type
                assert if_generation_match == 0
                if key in saved:
                    raise FileExistsError("object already exists")
                saved[key] = data
            obj.upload_from_string.side_effect = upload
            blobs[key] = obj
        return blobs[key]

    client = Mock()
    client.bucket.side_effect = lambda bucket: Mock(blob=lambda name: blob(bucket, name))
    blob("inputs", "race.html").download_as_bytes.return_value = RACE.read_bytes()
    blob("inputs", "weather.csv").download_as_bytes.return_value = WEATHER.read_bytes()
    return client, blobs, saved


def arguments(execution="report-abc"):
    return dict(
        race_uri="gs://inputs/race.html",
        race_sha256=hashlib.sha256(RACE.read_bytes()).hexdigest(),
        weather_uri="gs://inputs/weather.csv",
        weather_sha256=hashlib.sha256(WEATHER.read_bytes()).hexdigest(),
        output_prefix="gs://outputs/reports",
        execution={"job": "report", "name": execution, "task_index": 0,
                   "task_attempt": 0, "image": "registry/image@sha256:" + "a" * 64,
                   "source_revision": "b" * 40},
        settings=SETTINGS,
    )


def comparable(report):
    report = copy.deepcopy(report)
    for source in report["sources"].values():
        source.pop("file")
    return report


def test_saved_report_matches_local_and_repeat_keeps_both_outputs(storage):
    client, blobs, saved = storage
    outputs = run_stored_report(client, **arguments())
    run_stored_report(client, **arguments("report-def"))
    report_uri = "gs://outputs/reports/report-abc/task-0-attempt-0.json"
    result_uri = "gs://outputs/reports/report-abc/task-0-attempt-0.ndjson"
    assert outputs["report_uri"] == outputs["output_uri"] == report_uri
    assert outputs["result_export_uri"] == result_uri
    assert len(saved) == 4
    first = json.loads(saved[("outputs", "reports/report-abc/task-0-attempt-0.json")])
    second = json.loads(saved[("outputs", "reports/report-def/task-0-attempt-0.json")])
    result_payload = saved[("outputs", "reports/report-abc/task-0-attempt-0.ndjson")]
    baseline = build_offline_report(RACE, WEATHER, **SETTINGS)
    expected_rows = build_result_rows(RACE, WEATHER, **SETTINGS, race_kind="synthetic")
    expected_payload = encode_result_rows(expected_rows)
    assert baseline["race"]["name"] == "Runwx Synthetic Half"
    assert baseline["race_summary"] == {
        "finisher_count": 3, "best_duration_s": 3600,
        "mean_duration_s": 8400, "median_duration_s": 7200,
        "top_n_median_duration_s": 7200,
    }
    assert [baseline["result_quality"][key] for key in
            ("candidate_count", "accepted_count", "skipped_count", "invalid_count")] == [5, 3, 1, 1]
    assert baseline["weather_coverage"]["matched_count"] == 2
    assert baseline["weather_coverage"]["unmatched_count"] == 1
    assert baseline["weather_coverage"]["matched_fraction"] == 2 / 3
    assert comparable(first["report"]) == comparable(baseline)
    compare_reports(baseline, first)
    assert first["cloud_report_schema_version"] == 2
    assert first["report"] == second["report"]
    assert first["execution"]["name"] != second["execution"]["name"]
    assert first["execution"]["image"] == arguments()["execution"]["image"]
    assert first["execution"]["source_revision"] == "b" * 40
    assert first["report"]["sources"]["weather"]["kind"] == "synthetic"
    assert first["storage"]["inputs"]["race"]["generation"] == "17"
    assert first["storage"]["output_uri"] == report_uri
    assert first["storage"]["outputs"]["result_export"] == {
        "uri": result_uri,
        "sha256": hashlib.sha256(expected_payload).hexdigest(),
        "bytes": len(expected_payload),
        "row_count": 5,
        "schema_version": 1,
    }
    assert result_payload == expected_payload
    assert saved[("outputs", "reports/report-def/task-0-attempt-0.ndjson")] == expected_payload
    blobs[("inputs", "race.html")].download_as_bytes.assert_called_with(
        if_generation_match=17, checksum="auto", timeout=30,
    )


def test_existing_success_is_not_overwritten(storage):
    client, _, saved = storage
    run_stored_report(client, **arguments())
    previous = dict(saved)
    with pytest.raises(FileExistsError):
        run_stored_report(client, **arguments())
    assert saved == previous


@pytest.mark.parametrize("source", ["race", "weather"])
def test_changed_input_hash_stops_before_upload(storage, source):
    client, blobs, saved = storage
    name = "race.html" if source == "race" else "weather.csv"
    blobs[("inputs", name)].download_as_bytes.return_value += b"\n"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_stored_report(client, **arguments())
    assert not saved


def test_parse_failure_leaves_previous_success_intact(storage):
    client, blobs, saved = storage
    run_stored_report(client, **arguments())
    previous = dict(saved)
    bad_weather = b"wrong,columns\n"
    blobs[("inputs", "weather.csv")].download_as_bytes.return_value = bad_weather
    args = arguments("report-failed")
    args["weather_sha256"] = hashlib.sha256(bad_weather).hexdigest()
    with pytest.raises(ValueError):
        run_stored_report(client, **args)
    assert saved == previous


def test_download_failure_publishes_nothing(storage):
    client, blobs, saved = storage
    blobs[("inputs", "race.html")].download_as_bytes.side_effect = RuntimeError("changed generation")
    with pytest.raises(RuntimeError, match="changed generation"):
        run_stored_report(client, **arguments())
    assert not saved


def test_cross_artifact_count_mismatch_publishes_nothing(storage, monkeypatch):
    client, _, saved = storage
    original = snapshot_artifacts.build_result_rows

    def inconsistent_rows(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows[-1]["validation_status"] = "skipped"
        return rows

    monkeypatch.setattr(snapshot_artifacts, "build_result_rows", inconsistent_rows)
    with pytest.raises(RuntimeError, match="row counts do not reconcile"):
        run_stored_report(client, **arguments())
    assert not saved


def test_entrypoint_uses_runtime_identity_and_explicit_settings(storage, monkeypatch, capsys):
    client, _, saved = storage
    args = arguments()
    env = {
        "RUNWX_RACE_URI": args["race_uri"], "RUNWX_RACE_SHA256": args["race_sha256"],
        "RUNWX_WEATHER_URI": args["weather_uri"], "RUNWX_WEATHER_SHA256": args["weather_sha256"],
        "RUNWX_OUTPUT_PREFIX": args["output_prefix"],
        "RUNWX_IMAGE": args["execution"]["image"],
        "RUNWX_SOURCE_REVISION": args["execution"]["source_revision"],
        "RUNWX_REPORT_SETTINGS": json.dumps(dict(SETTINGS, top_n=2, max_gap_minutes=15)),
        "CLOUD_RUN_JOB": "report", "CLOUD_RUN_EXECUTION": "report-abc",
        "CLOUD_RUN_TASK_INDEX": "0", "CLOUD_RUN_TASK_ATTEMPT": "0",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    main(client=client)
    report = json.loads(saved[("outputs", "reports/report-abc/task-0-attempt-0.json")])["report"]
    assert report["settings"]["top_n"] == 2
    assert report["settings"]["max_gap_seconds"] == 900
    assert json.loads(capsys.readouterr().out)["output_uri"].startswith("gs://outputs/")


def test_historical_labels_apply_to_export_without_changing_report_v1(storage):
    client, _, saved = storage
    args = arguments()
    # Synthetic fixture bytes exercise the explicit mapping; they are not evidence.
    args["settings"] = dict(
        SETTINGS,
        weather_kind="unknown",
        race_kind="historical",
        export_weather_kind="historical_reanalysis",
        timing_basis="chip",
    )
    run_stored_report(client, **args)

    report = json.loads(saved[("outputs", "reports/report-abc/task-0-attempt-0.json")])
    rows = [
        json.loads(line)
        for line in saved[("outputs", "reports/report-abc/task-0-attempt-0.ndjson")]
        .decode("utf-8")
        .splitlines()
    ]
    assert report["report"]["sources"]["weather"]["kind"] == "unknown"
    assert all(row["race_kind"] == "historical" for row in rows)
    assert all(row["weather_kind"] == "historical_reanalysis" for row in rows)
    assert all(row["settings"]["timing_basis"] == "chip" for row in rows)


def test_report_upload_failure_is_reported_and_leaves_traceable_export(storage):
    client, blobs, saved = storage
    report_key = ("outputs", "reports/report-abc/task-0-attempt-0.json")
    client.bucket("outputs").blob(report_key[1])
    blobs[report_key].upload_from_string.side_effect = RuntimeError("report upload failed")

    with pytest.raises(RuntimeError, match="report upload failed"):
        run_stored_report(client, **arguments())

    assert ("outputs", "reports/report-abc/task-0-attempt-0.ndjson") in saved
    assert report_key not in saved


@pytest.mark.parametrize("field,value", [
    ("race_uri", "https://example.invalid/race.html"),
    ("weather_uri", "gs://inputs/weather.csv#17"),
    ("output_prefix", "gs://outputs"),
    ("race_sha256", "not-a-hash"),
])
def test_invalid_configuration_fails_before_storage(storage, field, value):
    client, _, saved = storage
    args = arguments()
    args[field] = value
    with pytest.raises(ValueError):
        run_stored_report(client, **args)
    client.bucket.assert_not_called()
    assert not saved


def test_invalid_source_revision_fails_before_storage(storage):
    client, _, saved = storage
    args = arguments()
    args["execution"]["source_revision"] = "short"
    with pytest.raises(ValueError, match="source_revision"):
        run_stored_report(client, **args)
    client.bucket.assert_not_called()
    assert not saved


@pytest.mark.parametrize("section,key,value", [
    ("settings", "top_n", 10),
    ("race_summary", "median_duration_s", 0),
    ("weather_coverage", "matched_count", 0),
    ("sources", "race", {"file": "gs://different/file", "sha256": "b" * 64}),
])
def test_comparison_does_not_hide_analytical_or_input_changes(storage, section, key, value):
    client, _, saved = storage
    run_stored_report(client, **arguments())
    cloud = json.loads(saved[("outputs", "reports/report-abc/task-0-attempt-0.json")])
    cloud["report"][section][key] = value
    with pytest.raises(ValueError, match="differs from local baseline"):
        compare_reports(build_offline_report(RACE, WEATHER, **SETTINGS), cloud)
