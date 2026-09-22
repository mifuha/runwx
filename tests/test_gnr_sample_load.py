"""The sample loader must keep full-field tables and reruns safe."""

from copy import deepcopy
from hashlib import sha256
import json
import socket
from unittest.mock import create_autospec

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import bigquery
import pytest

from runwx.adapters.bigquery.gnr_sample_load import SCHEMA, prepare_sample_load
from runwx.adapters.bigquery.result_load import load_prepared, prepare_load
from runwx.adapters.races.greatrun_json import SAMPLE_LABEL, SAMPLE_NOTE
from runwx.bigquery_load import main
from runwx.services.result_export import encode_result_rows

TABLE = "runwx-learning-mifuha.runwx_staging.gnr_2019_sample"
HASH = "a" * 64


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("sample loader test attempted network access")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def rows():
    sample = {
        "label": SAMPLE_LABEL, "note": SAMPLE_NOTE, "size": 1000,
        "selection": "published finish seconds then provider result ID",
        "source_count": 2000, "excluded_count": 2, "unselected_count": 998,
        "cutoff_s": 4999, "cutoff_ties_available": 1, "cutoff_ties_selected": 1,
        "timing_note": "Published chip/gun/unknown basis retained per row; no timing correction.",
    }
    weather = {
        "basis": "fixed_event_window",
        "note": "Start-area ERA5 context; not individual runner exposure or whole-course weather.",
        "timezone": "Europe/London", "start_local": "10:00", "end_local": "14:00",
        "start_utc": "2019-09-08T09:00:00+00:00",
        "end_utc": "2019-09-08T13:00:00+00:00", "hourly_observation_count": 5,
        "requested_latitude": 54.984, "requested_longitude": -1.62,
        "grid_latitude": 55.0, "grid_longitude": -1.5,
        "median_temp_c": 13.9, "median_wind_mps": 3.0,
        "median_humidity_pct": 73.0, "precipitation_mm": 0.1,
        "precipitation_basis": "sum of preceding-hour amounts ending after start through end",
    }
    common = {
        "export_schema": "gnr_sample_v1", "event_id": "greatrun:881", "race_date": "2019-09-08",
        "course_id": "great-north-run-traditional", "distance_m": 21100,
        "distance_basis": "provider distanceInKm", "race_kind": "historical",
        "weather_kind": "historical_reanalysis",
        "race_sha256": HASH, "categories_sha256": "b" * 64,
        "weather_sha256": "c" * 64, "weather_request_sha256": "d" * 64,
        "sample": sample, "weather_context": weather,
    }
    return [{**common, "source_row_id": f"greatrun:881:{HASH}:{n+100}",
             "source_row_number": n+100, "sample_rank": n, "duration_s": 3999+n,
             "timing_basis": "unknown" if n == 1 else ("gun" if n == 2 else "chip")}
            for n in range(1, 1001)]


def prepared(rows):
    payload = encode_result_rows(rows)
    return prepare_sample_load(payload, table_id=TABLE, expected_sha256=sha256(payload).hexdigest())


class Warehouse:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))
        self.api = create_autospec(bigquery.Client, instance=True)
        self.api.project = TABLE.split(".")[0]
        self.api.get_table.return_value = bigquery.Table.from_api_repr({
            "tableReference": {"projectId": self.api.project, "datasetId": "runwx_staging", "tableId": "gnr_2019_sample"},
            "location": "europe-west1", "type": "TABLE", "schema": {"fields": SCHEMA},
        })
        self.api.query.side_effect = self.query
        self.api.load_table_from_file.side_effect = self.load

    def query(self, sql, **kwargs):
        assert "ORDER BY sample_rank" in sql
        count = kwargs["job_config"].query_parameters[0].value
        snapshot = sorted(deepcopy(self.rows), key=lambda row: row["sample_rank"])[:count]
        job = create_autospec(bigquery.QueryJob, instance=True)
        job.job_id = f"query_{self.api.query.call_count}"
        job.total_bytes_processed = 50000
        job.total_bytes_billed = 10485760
        job.result.return_value = [{"row_json": json.dumps(row).replace("+00:00", "Z")}
                                   for row in snapshot]
        return job

    def load(self, source, destination, **kwargs):
        data = source.read()
        job = create_autospec(bigquery.LoadJob, instance=True)
        job.job_id = kwargs["job_id"]

        def complete(**options):
            if self.rows:
                raise Conflict("table is not empty")
            self.rows = [json.loads(line) for line in data.splitlines()]
            return job
        job.result.side_effect = complete
        return job


def test_preflight_is_offline_and_full_field_loader_rejects_sample(rows, tmp_path, capsys, monkeypatch):
    export = tmp_path / "sample.ndjson"
    export.write_bytes(encode_result_rows(rows))
    monkeypatch.setattr(bigquery, "Client", lambda **kwargs: pytest.fail("preview requested credentials"))
    main(["--input-format", "gnr-sample", "--input", str(export), "--table", TABLE,
          "--expected-sha256", sha256(export.read_bytes()).hexdigest()])
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "prepared_locally"
    assert summary["sample_count"] == 1000
    assert summary["timing_counts"] == {"unknown": 1, "gun": 1, "chip": 998}
    assert summary["input_bytes"] > 1024 * 1024
    with pytest.raises(ValueError):
        prepare_load(export.read_bytes(), table_id=TABLE,
                     expected_sha256=sha256(export.read_bytes()).hexdigest())


def test_one_load_then_identical_rerun_verifies_every_row(rows):
    load = prepared(rows)
    warehouse = Warehouse()
    first = load_prepared(warehouse.api, load)
    second = load_prepared(warehouse.api, load)
    assert first["status"] == "loaded_verified"
    assert second["status"] == "already_present_verified"
    assert warehouse.api.load_table_from_file.call_count == 1
    assert len(warehouse.rows) == 1000
    config = warehouse.api.load_table_from_file.call_args.kwargs["job_config"]
    assert config.write_disposition == "WRITE_EMPTY"
    assert config.create_disposition == "CREATE_NEVER"
    assert config.max_bad_records == 0
    assert config.autodetect is False
    assert [field.to_api_repr() for field in config.schema] == SCHEMA
    assert len(first["verification_jobs"]) == 2
    assert len(second["verification_jobs"]) == 1


def test_explicit_sample_cli_executes_only_after_complete_preflight(rows, tmp_path, capsys):
    export = tmp_path / "sample.ndjson"
    export.write_bytes(encode_result_rows(rows))
    warehouse = Warehouse()
    args = ["--input-format", "gnr-sample", "--input", str(export),
            "--table", TABLE, "--expected-sha256", sha256(export.read_bytes()).hexdigest(),
            "--execute"]
    main(args, client=warehouse.api)
    assert json.loads(capsys.readouterr().out)["status"] == "loaded_verified"
    main(args, client=warehouse.api)
    assert json.loads(capsys.readouterr().out)["status"] == "already_present_verified"
    assert warehouse.api.load_table_from_file.call_count == 1


@pytest.mark.parametrize("change", ["duration", "timing", "weather", "extra", "missing"])
def test_conflicting_existing_rows_are_never_overwritten(rows, change):
    stored = deepcopy(rows)
    if change == "duration": stored[0]["duration_s"] += 1
    if change == "timing": stored[1]["timing_basis"] = "chip"
    if change == "weather": stored[0]["weather_context"]["median_temp_c"] += 1
    if change == "extra": stored.append(deepcopy(stored[-1]))
    if change == "missing": stored.pop()
    warehouse = Warehouse(stored)
    with pytest.raises(ValueError, match="stored rows differ"):
        load_prepared(warehouse.api, prepared(rows))
    warehouse.api.load_table_from_file.assert_not_called()


@pytest.mark.parametrize("change", [
    "missing_row", "extra_row", "mixed_hash", "wrong_rank", "duplicate_locator",
    "wrong_id", "bad_timing", "unordered", "wrong_day", "false_place",
    "wrong_window", "bad_counts", "bad_cutoff", "mixed_weather", "bad_date",
])
def test_bad_samples_fail_before_cloud_calls(rows, change):
    if change == "missing_row": rows.pop()
    if change == "extra_row": rows.append(deepcopy(rows[-1]))
    if change == "mixed_hash": rows[3]["race_sha256"] = "e" * 64
    if change == "wrong_rank": rows[3]["sample_rank"] = 9
    if change == "duplicate_locator": rows[3]["source_row_number"] = rows[2]["source_row_number"]
    if change == "wrong_id": rows[3]["source_row_id"] = "athlete-id"
    if change == "bad_timing": rows[3]["timing_basis"] = "inferred"
    if change == "unordered": rows[3]["duration_s"] = 100
    if change == "wrong_day": rows[3]["race_date"] = "2019-09-09"
    if change == "false_place": rows[3]["place"] = 4
    if change == "wrong_window": rows[3]["weather_context"] = {**rows[3]["weather_context"], "basis": "runner_midpoint"}
    if change == "bad_counts":
        for row in rows: row["sample"] = {**row["sample"], "excluded_count": 3}
    if change == "bad_cutoff":
        for row in rows: row["sample"] = {**row["sample"], "cutoff_s": 6000}
    if change == "mixed_weather": rows[3]["weather_sha256"] = "e" * 64
    if change == "bad_date":
        for row in rows: row["race_date"] = "2019-02-29"
    with pytest.raises(ValueError):
        prepared(rows)


def test_wrong_hash_and_destination_are_rejected(rows):
    payload = encode_result_rows(rows)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        prepare_sample_load(payload, table_id=TABLE, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="project.dataset.table"):
        prepare_sample_load(payload, table_id="runwx-learning-mifuha.x;DROP.results",
                            expected_sha256=sha256(payload).hexdigest())


@pytest.mark.parametrize("problem", ["missing", "schema", "location"])
def test_target_requires_existing_table_in_right_region_with_exact_schema(rows, problem):
    warehouse = Warehouse()
    if problem == "missing": warehouse.api.get_table.side_effect = NotFound("missing")
    if problem == "schema": warehouse.api.get_table.return_value.schema = []
    if problem == "location": warehouse.api.get_table.return_value._properties["location"] = "US"
    with pytest.raises((ValueError, NotFound)):
        load_prepared(warehouse.api, prepared(rows))
    warehouse.api.query.assert_not_called()
    warehouse.api.load_table_from_file.assert_not_called()
