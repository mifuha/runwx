from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket
from unittest.mock import create_autospec

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import bigquery
import pytest

from runwx.adapters.bigquery.result_load import SCHEMA, load_prepared, prepare_load
from runwx.bigquery_load import main
from runwx.services.result_export import build_result_rows


TABLE = "runwx-learning-mifuha.runwx_staging.synthetic_results"


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("local BigQuery tests attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def rows():
    return build_result_rows(
        Path("data/sample_race_synthetic.html"), Path("data/sample_lydd_weather_synthetic.csv"),
        course_id="runwx-synthetic-half", distance_m=21097, timezone_name="Europe/London",
        race_kind="synthetic", weather_kind="synthetic",
    )


def encode(rows):
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


def prepare(rows):
    payload = encode(rows)
    return prepare_load(payload, table_id=TABLE, expected_sha256=sha256(payload).hexdigest())


class Warehouse:
    """A tiny stateful API fake; SDK objects/signatures are real, no SQL is executed."""

    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))
        self.lose_response = False
        self.corrupt_load = False
        self.api = create_autospec(bigquery.Client, instance=True)
        self.api.project = TABLE.split(".")[0]
        self.api.get_table.return_value = bigquery.Table.from_api_repr({
            "tableReference": {"projectId": self.api.project, "datasetId": "runwx_staging", "tableId": "synthetic_results"},
            "location": "europe-west1", "type": "TABLE", "schema": {"fields": SCHEMA},
        })
        self.api.query.side_effect = self.query
        self.api.load_table_from_file.side_effect = self.load

    def query(self, sql, **kwargs):
        config = kwargs["job_config"]
        limit = config.query_parameters[0].value
        snapshot = sorted(deepcopy(self.rows), key=lambda row: row["source_row_number"])[:limit]
        job = create_autospec(bigquery.QueryJob, instance=True)
        job.job_id = f"query_{self.api.query.call_count}"
        job.total_bytes_processed = 5000
        job.total_bytes_billed = 10485760
        # BigQuery's timestamp spelling can differ from the local ISO spelling.
        job.result.return_value = [
            {"row_json": json.dumps(row).replace("+00:00", "Z")} for row in snapshot
        ]
        return job

    def load(self, source, destination, **kwargs):
        payload = source.read()
        job = create_autospec(bigquery.LoadJob, instance=True)
        job.job_id = kwargs["job_id"]

        def complete(**options):
            if self.rows:
                raise Conflict("table is not empty")
            self.rows = [json.loads(line) for line in payload.splitlines()]
            if self.corrupt_load:
                self.rows[0]["duration_s"] += 1
            if self.lose_response:
                raise TimeoutError("response lost after upload")
            return job

        job.result.side_effect = complete
        return job


def test_preflight_runs_offline_without_creating_a_client(rows, tmp_path, capsys, monkeypatch):
    payload = encode(rows)
    export = tmp_path / "results.ndjson"
    export.write_bytes(payload)

    def forbidden_client(*args, **kwargs):
        pytest.fail("preview requested cloud credentials")

    monkeypatch.setattr(bigquery, "Client", forbidden_client)
    main(["--input", str(export), "--table", TABLE, "--expected-sha256", sha256(payload).hexdigest()])
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "prepared_locally"
    assert summary["candidate_count"] == 5
    assert (summary["accepted_count"], summary["skipped_count"], summary["invalid_count"]) == (3, 1, 1)
    assert summary["matched_count"] == 2
    assert summary["input_bytes"] == 5521
    assert summary["export_sha256"] == "91fcecdb956ea324d27aa8247c05a7eea357151ffe431752624f2ca95bb7b570"


def test_initial_load_and_repeat_keep_five_rows_and_verify_every_value(rows):
    prepared = prepare(rows)
    warehouse = Warehouse()
    first = load_prepared(warehouse.api, prepared)
    repeated = load_prepared(warehouse.api, prepared)

    assert first["status"] == "loaded_verified"
    assert repeated["status"] == "already_present_verified"
    assert len(warehouse.rows) == 5
    assert warehouse.rows == rows
    assert warehouse.api.load_table_from_file.call_count == 1
    assert first["race_sha256"] == repeated["race_sha256"] == rows[0]["race_sha256"]
    assert first["weather_sha256"] == repeated["weather_sha256"] == rows[0]["weather_sha256"]
    assert first["load_job_id"] == prepared.job_id
    assert repeated["load_job_id"] is None  # No new load job on a verified rerun.
    assert len(first["verification_jobs"]) == 2
    assert len(repeated["verification_jobs"]) == 1
    config = warehouse.api.load_table_from_file.call_args.kwargs["job_config"]
    assert config.write_disposition == "WRITE_EMPTY"
    assert config.create_disposition == "CREATE_NEVER"
    assert config.autodetect is False
    assert config.max_bad_records == 0
    assert config.ignore_unknown_values is False
    assert config.source_format == "NEWLINE_DELIMITED_JSON"
    assert [field.to_api_repr() for field in config.schema] == SCHEMA
    for call in warehouse.api.query.call_args_list:
        assert f"`{TABLE}`" in call.args[0]
        config = call.kwargs["job_config"]
        assert config.maximum_bytes_billed == 100 * 1024 * 1024
        assert config.query_parameters[0].value == 6
        assert config.use_query_cache is False
        assert call.kwargs["location"] == "europe-west1"


def test_lost_response_can_be_rechecked_without_a_second_upload(rows):
    prepared = prepare(rows)
    warehouse = Warehouse()
    warehouse.lose_response = True
    with pytest.raises(TimeoutError):
        load_prepared(warehouse.api, prepared)
    assert len(warehouse.rows) == 5

    result = load_prepared(warehouse.api, prepared)
    assert result["status"] == "already_present_verified"
    assert warehouse.api.load_table_from_file.call_count == 1
    assert len(warehouse.rows) == 5


@pytest.mark.parametrize("change", ["duration", "hash", "extra_row", "missing_row", "settings"])
def test_different_existing_data_is_never_overwritten(rows, change):
    stored = deepcopy(rows)
    if change == "duration":
        stored[0]["duration_s"] += 1
    elif change == "hash":
        stored[0]["weather_sha256"] = "0" * 64
    elif change == "extra_row":
        stored.append(deepcopy(stored[-1]))
    elif change == "missing_row":
        stored.pop()
    else:
        stored[0]["settings"]["max_gap_seconds"] = 900
    warehouse = Warehouse(stored)
    with pytest.raises(ValueError, match="stored rows differ"):
        load_prepared(warehouse.api, prepare(rows))
    warehouse.api.load_table_from_file.assert_not_called()
    assert warehouse.rows == stored


def test_post_load_mismatch_does_not_report_success_or_delete_candidate(rows):
    warehouse = Warehouse()
    warehouse.corrupt_load = True
    with pytest.raises(ValueError, match="stored rows differ"):
        load_prepared(warehouse.api, prepare(rows))
    assert len(warehouse.rows) == 5
    warehouse.api.delete_table.assert_not_called()


@pytest.mark.parametrize("change", ["duplicate_id", "extra_field", "missing_field", "wrong_type", "real_label", "mixed_snapshot", "invalid_outcome", "rejected_weather"])
def test_invalid_export_is_rejected_locally(rows, change):
    if change == "duplicate_id":
        rows[1]["source_row_id"] = rows[0]["source_row_id"]
    elif change == "extra_field":
        rows[0]["athlete_name"] = "fabricated name"
    elif change == "missing_field":
        del rows[0]["settings"]
    elif change == "wrong_type":
        rows[0]["duration_s"] = "3600"
    elif change == "real_label":
        rows[0]["race_kind"] = "unknown"
    elif change == "mixed_snapshot":
        rows[1]["weather_sha256"] = "0" * 64
    elif change == "invalid_outcome":
        rows[0]["validation_status"] = "other"
    else:
        rows[3]["weather"] = rows[0]["weather"]
    with pytest.raises(ValueError):
        prepare(rows)


def test_wrong_hash_fails_before_client_use(rows, tmp_path):
    export = tmp_path / "results.ndjson"
    export.write_bytes(encode(rows))
    warehouse = Warehouse()
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        main(["--input", str(export), "--table", TABLE, "--expected-sha256", "0" * 64, "--execute"], client=warehouse.api)
    warehouse.api.get_table.assert_not_called()


@pytest.mark.parametrize("table", ["project.dataset.table;DROP TABLE x", "project.dataset.table`", "only_two.parts"])
def test_invalid_destination_fails_locally(rows, table):
    payload = encode(rows)
    with pytest.raises(ValueError, match="project.dataset.table"):
        prepare_load(payload, table_id=table, expected_sha256=sha256(payload).hexdigest())


@pytest.mark.parametrize("problem", ["missing", "schema", "location"])
def test_destination_must_already_have_the_right_schema_and_location(rows, problem):
    warehouse = Warehouse()
    if problem == "missing":
        warehouse.api.get_table.side_effect = NotFound("missing table")
    elif problem == "schema":
        warehouse.api.get_table.return_value.schema = []
    else:
        warehouse.api.get_table.return_value._properties["location"] = "US"
    with pytest.raises((ValueError, NotFound)):
        load_prepared(warehouse.api, prepare(rows))
    warehouse.api.query.assert_not_called()
    warehouse.api.load_table_from_file.assert_not_called()


def test_existing_load_job_is_waited_for_then_verified(rows):
    warehouse = Warehouse()
    prepared = prepare(rows)
    warehouse.api.load_table_from_file.side_effect = Conflict("job already exists")

    def complete(**kwargs):
        warehouse.rows = deepcopy(rows)

    previous = create_autospec(bigquery.LoadJob, instance=True)
    previous.job_id = prepared.job_id
    previous.result.side_effect = complete
    warehouse.api.get_job.return_value = previous
    result = load_prepared(warehouse.api, prepared)
    assert result["status"] == "loaded_verified"
    assert result["load_job_id"] == prepared.job_id
    warehouse.api.get_job.assert_called_once_with(prepared.job_id, project=warehouse.api.project,
                                                 location="europe-west1", retry=None, timeout=30)
