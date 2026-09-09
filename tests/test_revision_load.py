"""Candidate loading contract with real SDK signatures; no native SQL execution."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
from unittest.mock import create_autospec

from google.api_core.exceptions import Conflict
from google.cloud import bigquery
import pytest

from runwx.adapters.bigquery.revision_load import (
    SCHEMAS, CandidateLoadUnknown, load_revision_candidate, prepare_revision_load,
)
from runwx.adapters.bigquery.selection import prepare_selection
from runwx.revision_load import main
from runwx.services.revisions import prepare_revision

DATASET = "runwx-learning-mifuha.runwx_revision_demo"
RACE = Path("data/sample_race_synthetic.html")
WEATHER = Path("data/sample_lydd_weather_synthetic.csv")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("candidate loader attempted network access")
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, forbidden)


@pytest.fixture
def revision():
    return prepare_revision(
        RACE, WEATHER, event_id="eventrac:900001", weather_source_id="runwx:synthetic",
        snapshot_scope="complete", race_kind="synthetic", weather_kind="synthetic",
        course_id="runwx-synthetic-half", distance_m=21097, timezone_name="Europe/London",
    )


@pytest.fixture
def prepared(revision):
    return prepare_revision_load(revision, RACE, WEATHER, dataset=DATASET)


class Warehouse:
    def __init__(self):
        self.rows = {name: [] for name in SCHEMAS}
        self.jobs = {}
        self.fail_table = None
        self.lose_response = False
        self.corrupt_load = False
        self.api = create_autospec(bigquery.Client, instance=True)
        self.api.project = DATASET.split(".")[0]
        self.api.get_table.side_effect = self.table
        self.api.query.side_effect = self.query
        self.api.load_table_from_file.side_effect = self.load
        self.api.get_job.side_effect = lambda job_id, **kwargs: self.jobs[job_id]

    def table(self, table_id, **kwargs):
        name = table_id.split(".")[-1]
        return bigquery.Table.from_api_repr({
            "tableReference": {"projectId": self.api.project, "datasetId": DATASET.split(".")[1], "tableId": name},
            "location": "europe-west1", "type": "TABLE", "schema": {"fields": SCHEMAS[name]},
        })

    def query(self, sql, **kwargs):
        name = next(name for name in SCHEMAS if f"`{DATASET}.{name}`" in sql)
        params = {p.name: p.value for p in kwargs["job_config"].query_parameters}
        rows = [row for row in self.rows[name] if row["revision_id"] == params["revision_id"]]
        rows = sorted(rows, key=lambda row: row.get("source_row_number", 0))[:params["row_limit"]]
        job = create_autospec(bigquery.QueryJob, instance=True)
        job.job_id = kwargs["job_id"]
        job.total_bytes_processed, job.total_bytes_billed = 100, 10485760
        def warehouse_json(row):
            # BigQuery formats TIMESTAMP fields, not timestamps embedded in STRING JSON.
            row = deepcopy(row)
            if name == "revision_result_rows":
                row["started_at_utc"] = row["started_at_utc"].replace("+00:00", "Z")
                if row["weather"]:
                    row["weather"]["observed_at_utc"] = row["weather"]["observed_at_utc"].replace("+00:00", "Z")
            return json.dumps(row)
        job.result.return_value = [{"row_json": warehouse_json(row)} for row in rows]
        return job

    def load(self, stream, table_id, **kwargs):
        job_id = kwargs["job_id"]
        if job_id in self.jobs:
            raise Conflict("existing job")
        name = table_id.split(".")[-1]
        payload = [json.loads(line) for line in stream.read().splitlines()]
        job = create_autospec(bigquery.LoadJob, instance=True)
        job.job_id = job_id
        job.project, job.location = self.api.project, "europe-west1"
        job.destination = bigquery.TableReference.from_string(table_id)
        for attr in ("schema", "source_format", "create_disposition", "write_disposition"):
            setattr(job, attr, getattr(kwargs["job_config"], attr))
        completed = False

        def finish(**options):
            nonlocal completed
            if self.fail_table == name:
                raise TimeoutError("paused before candidate load completed")
            if not completed:
                self.rows[name].extend(deepcopy(payload))
                completed = True
                if self.corrupt_load and name == "revision_result_rows":
                    self.rows[name][0]["duration_s"] += 1
            if self.lose_response:
                raise TimeoutError("response lost after load")
            return job

        job.result.side_effect = finish
        self.jobs[job_id] = job
        return job


def test_candidate_matches_writer_without_inventing_a_receipt(prepared, revision):
    selected = prepare_selection(
        revision, RACE, WEATHER, dataset=DATASET, expected=None,
        successful_attempt_id="fixture-only", validation_code_sha256="a" * 64,
        validation_invocation_id="fixture-only",
    )
    assert prepared.metadata_json == selected.metadata_json
    assert prepared.rows_json == selected.rows_json
    assert set(SCHEMAS) == {"analysis_revisions", "revision_result_rows"}
    for name, schema in SCHEMAS.items():
        assert schema == json.loads(Path(f"dbt/contracts/revisions/{name}.schema.json").read_text())


def test_load_repeat_and_second_revision_preserve_existing_candidates(prepared, revision):
    warehouse = Warehouse()
    first = load_revision_candidate(warehouse.api, prepared)
    before = deepcopy(warehouse.rows)
    repeated = load_revision_candidate(warehouse.api, prepared)
    assert first["status"] == "candidate_loaded_verified"
    assert repeated["status"] == "candidate_already_present_verified"
    assert warehouse.rows == before
    assert warehouse.api.load_table_from_file.call_count == 2
    changed = prepare_revision(
        RACE, WEATHER, event_id=revision.event_id, weather_source_id=revision.weather_source_id,
        snapshot_scope="complete", race_kind="synthetic", weather_kind="synthetic",
        course_id="runwx-synthetic-half", distance_m=21097, timezone_name="Europe/London", top_n=1,
    )
    load_revision_candidate(warehouse.api, prepare_revision_load(changed, RACE, WEATHER, dataset=DATASET))
    assert len(warehouse.rows["analysis_revisions"]) == 2
    assert len(warehouse.rows["revision_result_rows"]) == 10
    assert warehouse.rows["revision_result_rows"][:5] == before["revision_result_rows"]
    assert "receipt" not in first and "selection" not in first


def test_resume_after_rows_load_and_metadata_submission_timeout(prepared):
    warehouse = Warehouse()
    warehouse.fail_table = "analysis_revisions"
    with pytest.raises(CandidateLoadUnknown) as error:
        load_revision_candidate(warehouse.api, prepared)
    assert error.value.table_id == DATASET + ".analysis_revisions"
    assert isinstance(error.value.__cause__, TimeoutError)
    assert len(warehouse.rows["revision_result_rows"]) == 5
    assert warehouse.rows["analysis_revisions"] == []
    original_job = error.value.job_id
    warehouse.fail_table = None
    result = load_revision_candidate(warehouse.api, prepared)
    assert result["status"] == "candidate_loaded_verified"
    assert len(warehouse.rows["revision_result_rows"]) == 5
    assert len(warehouse.rows["analysis_revisions"]) == 1
    assert warehouse.api.get_job.call_args.args[0] == original_job


def test_response_loss_recheck_does_not_duplicate_rows(prepared):
    warehouse = Warehouse()
    warehouse.lose_response = True
    with pytest.raises(CandidateLoadUnknown) as error:
        load_revision_candidate(warehouse.api, prepared)
    assert error.value.job_id in warehouse.jobs
    assert warehouse.api.load_table_from_file.call_count == 1
    warehouse.lose_response = False
    load_revision_candidate(warehouse.api, prepared)
    assert warehouse.api.load_table_from_file.call_count == 2
    assert len(warehouse.rows["revision_result_rows"]) == 5


def test_relocated_sources_recover_the_same_metadata_job(prepared, revision, tmp_path):
    warehouse = Warehouse()
    warehouse.fail_table = "analysis_revisions"
    with pytest.raises(CandidateLoadUnknown) as error:
        load_revision_candidate(warehouse.api, prepared)
    race, weather = tmp_path / "race.html", tmp_path / "weather.csv"
    race.write_bytes(RACE.read_bytes())
    weather.write_bytes(WEATHER.read_bytes())
    relocated = prepare_revision_load(revision, race, weather, dataset=DATASET)
    assert relocated.metadata_json != prepared.metadata_json
    assert relocated.job_id("analysis_revisions") == error.value.job_id
    warehouse.fail_table = None
    load_revision_candidate(warehouse.api, relocated)
    assert warehouse.api.get_job.call_args.args[0] == error.value.job_id
    assert warehouse.rows["analysis_revisions"] == [json.loads(prepared.metadata_json)]
    assert len(warehouse.rows["revision_result_rows"]) == 5


def test_wrong_existing_job_is_not_awaited_or_reported_as_success(prepared):
    warehouse = Warehouse()
    warehouse.fail_table = "revision_result_rows"
    with pytest.raises(CandidateLoadUnknown) as error:
        load_revision_candidate(warehouse.api, prepared)
    job = warehouse.jobs[error.value.job_id]
    job.destination = bigquery.TableReference.from_string(DATASET + ".different_table")
    job.result.reset_mock()
    with pytest.raises(CandidateLoadUnknown) as error:
        load_revision_candidate(warehouse.api, prepared)
    assert isinstance(error.value.__cause__, ValueError)
    job.result.assert_not_called()
    assert all(not rows for rows in warehouse.rows.values())


def test_submission_failure_retains_deterministic_job_id(prepared):
    warehouse = Warehouse()
    warehouse.api.load_table_from_file.side_effect = TimeoutError("submission response lost")
    with pytest.raises(CandidateLoadUnknown) as error:
        load_revision_candidate(warehouse.api, prepared)
    assert error.value.job_id == prepared.job_id("revision_result_rows")
    assert isinstance(error.value.__cause__, TimeoutError)
    warehouse.api.load_table_from_file.assert_called_once()


@pytest.mark.parametrize("change", ["dataset", "race_kind", "weather_kind", "source", "code"])
def test_invalid_candidate_is_rejected_locally(revision, change, tmp_path):
    dataset, race = DATASET, RACE
    if change == "dataset":
        dataset += "`; DROP TABLE other"
    elif change == "race_kind":
        revision = replace(revision, race_kind="unknown")
    elif change == "weather_kind":
        settings = revision.settings
        settings["weather_kind"] = "unknown"
        revision = replace(revision, settings_json=json.dumps(settings))
    elif change == "source":
        race = tmp_path / "race.html"
        race.write_bytes(RACE.read_bytes() + b"\n")
    else:
        revision = replace(revision, code_sha256="a" * 64)
    with pytest.raises(ValueError):
        prepare_revision_load(revision, race, WEATHER, dataset=dataset)


@pytest.mark.parametrize("problem", ["partial", "duplicate", "duration", "metadata"])
def test_conflicting_existing_revision_fails_before_any_upload(prepared, problem):
    warehouse = Warehouse()
    warehouse.rows["revision_result_rows"] = json.loads(prepared.rows_json)
    if problem == "partial":
        warehouse.rows["revision_result_rows"].pop()
    elif problem == "duplicate":
        warehouse.rows["revision_result_rows"].append(deepcopy(warehouse.rows["revision_result_rows"][0]))
    elif problem == "duration":
        warehouse.rows["revision_result_rows"][0]["duration_s"] += 1
    else:
        warehouse.rows["analysis_revisions"] = [json.loads(prepared.metadata_json)]
        warehouse.rows["analysis_revisions"][0]["candidate_count"] += 1
    before = deepcopy(warehouse.rows)
    with pytest.raises(ValueError, match="stored candidate"):
        load_revision_candidate(warehouse.api, prepared)
    warehouse.api.load_table_from_file.assert_not_called()
    assert warehouse.rows == before


def test_load_drift_does_not_report_success_or_load_metadata(prepared):
    warehouse = Warehouse()
    warehouse.corrupt_load = True
    with pytest.raises(ValueError, match="stored candidate"):
        load_revision_candidate(warehouse.api, prepared)
    assert len(warehouse.rows["revision_result_rows"]) == 5
    assert warehouse.rows["analysis_revisions"] == []
    warehouse.api.delete_table.assert_not_called()


@pytest.mark.parametrize("problem", ["project", "location", "schema"])
def test_preflight_checks_both_table_contracts_before_queries_or_uploads(prepared, problem):
    warehouse = Warehouse()
    if problem == "project":
        warehouse.api.project = "different-project"
    else:
        def table(table_id, **kwargs):
            result = warehouse.table(table_id)
            if table_id.endswith("analysis_revisions"):
                if problem == "schema": result.schema = []
                else: result._properties["location"] = "US"
            return result
        warehouse.api.get_table.side_effect = table
    with pytest.raises(ValueError):
        load_revision_candidate(warehouse.api, prepared)
    warehouse.api.query.assert_not_called()
    warehouse.api.load_table_from_file.assert_not_called()


def test_job_limits_and_schema_are_explicit(prepared):
    warehouse = Warehouse()
    load_revision_candidate(warehouse.api, prepared)
    for call in warehouse.api.load_table_from_file.call_args_list:
        kwargs, config = call.kwargs, call.kwargs["job_config"]
        assert kwargs["num_retries"] == 0 and kwargs["location"] == "europe-west1"
        assert config.write_disposition == "WRITE_APPEND" and config.create_disposition == "CREATE_NEVER"
        assert not config.autodetect and not config.ignore_unknown_values and config.max_bad_records == 0
        assert int(config.job_timeout_ms) == 300000
    for call in warehouse.api.query.call_args_list:
        assert call.kwargs["retry"] is None and call.kwargs["job_retry"] is None
        config = call.kwargs["job_config"]
        assert config.maximum_bytes_billed == 104857600 and int(config.job_timeout_ms) == 300000
    assert len(warehouse.api.query.call_args_list) == 4
    for job in warehouse.jobs.values():
        job.result.assert_called_once_with(timeout=300, retry=None)


@pytest.mark.parametrize("execute", [False, True])
def test_cli_loads_only_with_execute_and_preview_never_creates_a_client(monkeypatch, capsys, execute):
    warehouse = Warehouse()
    def forbidden(*args, **kwargs): pytest.fail("preview created a BigQuery client")
    monkeypatch.setattr(bigquery, "Client", forbidden)
    main([
        "--race-html", str(RACE), "--weather-csv", str(WEATHER), "--dataset", DATASET,
        "--event-id", "eventrac:900001", "--weather-source-id", "runwx:synthetic",
        "--course-id", "runwx-synthetic-half", "--distance-m", "21097", "--timezone", "Europe/London",
        "--race-kind", "synthetic", "--weather-kind", "synthetic", "--snapshot-scope", "complete",
    ] + (["--execute"] if execute else []), client=warehouse.api if execute else None)
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == ("candidate_loaded_verified" if execute else "prepared_locally")
    assert result["candidate_count"] == 5 and result["accepted_count"] == 3
    assert len(result["planned_load_job_ids"]) == 2
    assert warehouse.api.load_table_from_file.call_count == (2 if execute else 0)
