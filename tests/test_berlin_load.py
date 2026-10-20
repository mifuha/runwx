"""Research capture preflight must retain unknowns and the existing load protections."""

from copy import deepcopy
from hashlib import sha256
import json

from google.cloud import bigquery
import pytest

from runwx.adapters.bigquery.result_load import load_prepared, prepare_load
from runwx.adapters.races.berlin_csv import CATALOG
from runwx.bigquery_load import main
from runwx.services import berlin_load
from runwx.services.berlin_load import SCHEMA, prepare_berlin_load
from runwx.services.berlin_prepare import prepare_berlin

from test_berlin_prepare import batch, offline_only  # Existing synthetic source and credential/network tripwires.
from test_bigquery_load import Warehouse

TABLE = "runwx-learning-mifuha.runwx_staging.berlin_2012_research"


def encode(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()


@pytest.fixture
def artifacts(batch):
    config, output = batch
    prepare_berlin(config, output)
    return (output / "2012-09-30.ndjson").read_bytes(), (output / "2012-09-30.report.json").read_bytes()


def prepared(artifacts, **changes):
    capture, report = artifacts
    options = dict(table_id=TABLE, expected_sha256=sha256(capture).hexdigest(),
                   expected_report_sha256=sha256(report).hexdigest())
    options.update(changes)
    return prepare_berlin_load(capture, report, **options)


def warehouse(rows=()):
    result = Warehouse(rows)
    result.api.get_table.return_value.schema = [bigquery.SchemaField.from_api_repr(f) for f in SCHEMA]
    return result


def test_reuses_preparation_and_preserves_source_identity_population_and_weather(artifacts):
    load = prepared(artifacts)
    assert len(load.rows) == 3
    assert [r["source_row_number"] for r in load.rows] == [2, 4, 5]
    assert [r["duration_s"] for r in load.rows] == [10800, 10800, None]
    assert load.rows[0]["time_raw"] == load.rows[1]["time_raw"] == "03:00:00"
    assert load.rows[0]["source_row_id"] != load.rows[1]["source_row_id"]
    assert load.rows[2]["validation_status"] == "held"
    assert all(r["age"] is r["place"] is r["timing_basis"] is None for r in load.rows)
    assert load.rows[0]["age_category_raw"] == "35"
    assert load.rows[0]["weather_context"]["start_utc"] == "2012-09-30T07:00:00+00:00"
    assert load.rows[0]["weather_context"]["precipitation_mm"] == 75
    assert load.rows[0]["population_basis"] == "published_research_capture"
    assert load.rows[0]["course_basis"] == "post_2003_course_era_not_identical_routes"
    assert prepared(artifacts).job_id == load.job_id
    assert prepared(artifacts, table_id=TABLE + "_other").job_id != load.job_id
    assert load.summary()["accepted_count"] == 2 and load.summary()["held_count"] == 1
    with pytest.raises(ValueError):
        prepare_load(artifacts[0], table_id=TABLE, expected_sha256=sha256(artifacts[0]).hexdigest())


def test_shared_loader_writes_once_then_reads_and_verifies_all_typed_rows(artifacts):
    load = prepared(artifacts)
    store = warehouse()
    first = load_prepared(store.api, load)
    second = load_prepared(store.api, load)
    assert first["status"] == "loaded_verified"
    assert second["status"] == "already_present_verified"
    assert store.api.load_table_from_file.call_count == 1
    assert store.rows == load.rows
    options = store.api.load_table_from_file.call_args.kwargs
    assert options["job_config"].write_disposition == "WRITE_EMPTY"
    assert options["job_config"].create_disposition == "CREATE_NEVER"
    assert options["job_config"].max_bad_records == 0
    assert options["num_retries"] == 0 and options["timeout"] == 30
    assert [f.to_api_repr() for f in options["job_config"].schema] == SCHEMA
    assert len(first["verification_jobs"]) == 2 and len(second["verification_jobs"]) == 1
    for call in store.api.query.call_args_list:
        assert "ORDER BY source_row_number" in call.args[0]
        assert call.kwargs["job_config"].query_parameters[0].value == 4
        assert call.kwargs["job_config"].maximum_bytes_billed == 100 * 1024 * 1024
    store.api.delete_table.assert_not_called()


@pytest.mark.parametrize("mutation", ["duration", "weather", "population", "missing", "duplicate"])
def test_existing_conflicts_are_not_overwritten(artifacts, mutation):
    load = prepared(artifacts)
    changed = deepcopy(load.rows)
    if mutation == "duration": changed[0]["duration_s"] += 1
    if mutation == "weather": changed[0]["weather_context"]["median_temp_c"] += 1
    if mutation == "population": changed[0]["population_basis"] = "official_full_field"
    if mutation == "missing": changed.pop()
    if mutation == "duplicate": changed.append(deepcopy(changed[-1]))
    store = warehouse(changed)
    with pytest.raises(ValueError, match="stored rows differ"):
        load_prepared(store.api, load)
    store.api.load_table_from_file.assert_not_called()
    store.api.delete_table.assert_not_called()


def test_response_loss_and_corrupted_readback_preserve_existing_guarantees(artifacts):
    load = prepared(artifacts)
    store = warehouse()
    store.lose_response = True
    with pytest.raises(TimeoutError):
        load_prepared(store.api, load)
    assert load_prepared(store.api, load)["status"] == "already_present_verified"
    assert store.api.load_table_from_file.call_count == 1
    broken = warehouse()
    broken.corrupt_load = True
    with pytest.raises(ValueError, match="stored rows differ"):
        load_prepared(broken.api, load)
    broken.api.delete_table.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("race_date", "2012-09-29"), ("source_row_number", 1), ("source_row_id", "athlete"),
    ("age", 35), ("place", 1), ("timing_basis", "chip"), ("age_category_raw", 35),
    ("duration_s", 200), ("time_raw", "00:00:00"), ("validation_status", "skipped"),
    ("validation_reason", "not actually accepted"), ("gender_raw", "unknown"),
])
def test_bad_capture_outcomes_fail_even_with_updated_artifact_hashes(artifacts, field, value):
    capture, raw_report = artifacts
    rows = [json.loads(line) for line in capture.splitlines()]
    rows[1][field] = value
    capture = b"".join(encode(row) for row in rows)
    report = json.loads(raw_report)
    report.update(export_sha256=sha256(capture).hexdigest(), export_bytes=len(capture))
    with pytest.raises(ValueError):
        prepared((capture, encode(report)))


@pytest.mark.parametrize("field,value", [
    ("year", 2019), ("population", "Official complete field"), ("course_era", "Identical routes"),
    ("results_sha256", "0" * 64), ("captured_count", 1), ("accepted_count", 0),
    ("held_count", True), ("individual_starts_available", 0), ("timing_basis", "gun"),
    ("distance_m", 42000), ("weather_response_sha256", "wrong"),
    ("weather_request_url", "https://archive-api.open-meteo.com/v1/archive?timezone=UTC"),
])
def test_bad_report_is_rejected_before_credentials(artifacts, field, value):
    capture, raw_report = artifacts
    report = json.loads(raw_report)
    report[field] = value
    with pytest.raises(ValueError):
        prepared((capture, encode(report)))


@pytest.mark.parametrize("field,value", [
    ("basis", "runner_midpoint"), ("timezone", "UTC"), ("start_local", "10:00"),
    ("start_utc", "2012-09-30T09:00:00Z"), ("observation_count", 6),
    ("units", {"temperature": "F", "wind": "m/s", "precipitation": "mm", "humidity": "%"}),
    ("median_wind_mps", -1), ("median_humidity_pct", 101),
    ("precipitation_mm", -1), ("returned_point", {"latitude": 0, "longitude": 0}),
])
def test_changed_weather_contract_is_rejected(artifacts, field, value):
    capture, raw_report = artifacts
    report = json.loads(raw_report)
    report["weather_context"][field] = value
    with pytest.raises(ValueError):
        prepared((capture, encode(report)))


def test_hashes_size_bounds_and_json_structure_fail_closed(artifacts, monkeypatch):
    with pytest.raises(ValueError, match="capture SHA"):
        prepared(artifacts, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="report SHA"):
        prepared(artifacts, expected_report_sha256="0" * 64)
    with pytest.raises(ValueError, match="europe-west1"):
        prepared(artifacts, location="US")
    with pytest.raises(ValueError, match="project.dataset.table"):
        prepared(artifacts, table_id="table; DROP TABLE")
    monkeypatch.setattr(berlin_load, "MAX_EXPORT_BYTES", 1)
    with pytest.raises(ValueError, match="64 MiB"):
        prepared(artifacts)
    monkeypatch.setattr(berlin_load, "MAX_CAPTURE_BYTES", 1)
    with pytest.raises(ValueError, match="at most 1 bytes"):
        prepared(artifacts)


def test_unknown_published_count_and_changed_report_change_load_identity(artifacts, monkeypatch):
    before = prepared(artifacts)
    capture, report_bytes = artifacts
    report = json.loads(report_bytes)
    monkeypatch.setitem(CATALOG["editions"]["2012"], "published_count", None)
    report.update(published_count=None, count_difference_from_published=None)
    after = prepared((capture, encode(report)))
    assert all(row["published_count"] is None for row in after.rows)
    assert after.job_id != before.job_id


def test_explicit_cli_preview_and_execute_use_same_validated_contract(artifacts, tmp_path, monkeypatch, capsys):
    capture, report = artifacts
    input_path, report_path = tmp_path / "capture.ndjson", tmp_path / "report.json"
    input_path.write_bytes(capture)
    report_path.write_bytes(report)
    args = ["--input-format", "berlin-research", "--input", str(input_path), "--table", TABLE,
            "--expected-sha256", sha256(capture).hexdigest(), "--preparation-report", str(report_path),
            "--expected-report-sha256", sha256(report).hexdigest()]
    store = warehouse()
    monkeypatch.setattr(bigquery, "Client", lambda **kwargs: pytest.fail("preview requested credentials"))
    main(args)
    assert json.loads(capsys.readouterr().out)["status"] == "prepared_locally"
    main([*args, "--execute"], client=store.api)
    assert json.loads(capsys.readouterr().out)["status"] == "loaded_verified"
    main([*args, "--execute"], client=store.api)
    assert json.loads(capsys.readouterr().out)["status"] == "already_present_verified"
    assert store.api.load_table_from_file.call_count == 1
    with pytest.raises(SystemExit):
        main(args[:8])  # No report flags: fail before even reading inputs/creating a client.
    with pytest.raises(SystemExit):
        main([*args[:1], "full-results", *args[2:]])


def test_full_field_schema_is_not_reused_for_research_rows(artifacts):
    store = Warehouse()
    with pytest.raises(ValueError, match="schema differs"):
        load_prepared(store.api, prepared(artifacts))
    store.api.query.assert_not_called()
    store.api.load_table_from_file.assert_not_called()


def test_duplicate_fields_or_rows_and_nonfinite_report_fail_closed(artifacts):
    capture, report = artifacts
    with pytest.raises(ValueError, match="duplicate JSON"):
        prepared((capture, report.replace(b'{', b'{"year":2012,', 1)))
    repeated = capture + capture.splitlines()[0] + b"\n"
    metadata = json.loads(report)
    metadata.update(export_bytes=len(repeated), export_sha256=sha256(repeated).hexdigest())
    with pytest.raises(ValueError, match="identity/order"):
        prepared((repeated, encode(metadata)))
    metadata = json.loads(report)
    metadata["weather_context"]["median_temp_c"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        prepared((capture, json.dumps(metadata).encode()))
