"""Local publisher contract tests. The API fake does not execute BigQuery SQL."""

from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
from unittest.mock import create_autospec

from google.cloud import bigquery
import pytest

from runwx.adapters.bigquery.selection import (
    SelectionOutcomeUnknown, prepare_selection, publish_selection,
)
from runwx.domain.revisions import Selection, canonical_json
from runwx.services.revisions import prepare_revision


DATASET = "runwx-learning-mifuha.runwx_revision_demo"
WEATHER = Path("data/sample_lydd_weather_synthetic.csv")
OLD = Selection("eventrac:900001", "a" * 64, "old-warehouse-attempt")


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("local publisher test attempted network access")
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, forbidden)


@pytest.fixture
def prepared():
    race = Path("data/sample_race_synthetic_corrected.html")
    revision = prepare_revision(
        race, WEATHER, event_id=OLD.event_id,
        weather_source_id="runwx:synthetic-hourly-weather-demo",
        snapshot_scope="complete", race_kind="synthetic", weather_kind="synthetic",
        course_id="runwx-synthetic-half", distance_m=21097, timezone_name="Europe/London",
    )
    return prepare_selection(
        revision, race, WEATHER, dataset=DATASET, expected=OLD,
        successful_attempt_id="correction-warehouse-attempt",
        validation_code_sha256="b" * 64, validation_invocation_id="test-invocation",
    )


class Warehouse:
    """Independent state transition oracle plus a real SDK signature check.

    It tests orchestration/parameters, not transaction semantics or SQL validity.
    Native BigQuery validation is a separate approval-bound check.
    """

    def __init__(self, prepared):
        self.metadata = [json.loads(prepared.metadata_json)]
        self.rows = json.loads(prepared.rows_json)
        self.receipts = [json.loads(prepared.receipt_json)]
        self.selections = [asdict(OLD)]
        self.before_write = lambda: None
        self.lose_response = False
        self.writes = 0
        self.api = create_autospec(bigquery.Client, instance=True)
        self.api.project = DATASET.split(".")[0]
        self.api.query.side_effect = self.query

    def snapshot(self):
        return {
            "metadata_json": [canonical_json(r) for r in self.metadata],
            "rows_json": [canonical_json(r) for r in self.rows],
            "receipt_json": [canonical_json(r) for r in self.receipts],
        }

    def query(self, sql, **kwargs):
        params = {p.name: p.to_api_repr()["parameterValue"] for p in kwargs["job_config"].query_parameters}
        values = {name: p.get("value", [x["value"] for x in p.get("arrayValues", [])])
                  for name, p in params.items()}
        job = create_autospec(bigquery.QueryJob, instance=True)
        job.job_id = kwargs["job_id"]
        job.total_bytes_processed, job.total_bytes_billed = 512, 10485760

        def complete(**options):
            if "BEGIN TRANSACTION" not in sql:
                return [deepcopy(self.snapshot())]
            self.before_write()
            if self.snapshot() != {name: values[name] for name in self.snapshot()}:
                raise ValueError("candidate changed")
            desired = {"event_id": values["event_id"], "revision_id": values["revision_id"],
                       "successful_attempt_id": values["attempt_id"]}
            expected = ([] if values["expected_revision_id"] is None else [{
                "event_id": values["event_id"], "revision_id": values["expected_revision_id"],
                "successful_attempt_id": values["expected_attempt_id"],
            }])
            if len(self.selections) > 1:
                raise ValueError("ambiguous selection")
            if self.selections == [desired]:
                status = "already_selected"
            elif self.selections == expected:
                self.selections = [desired]
                self.writes += 1
                status = "selected"
            else:
                raise ValueError("selection changed")
            if self.lose_response:
                raise TimeoutError("response lost after commit")
            return [{"status": status, **desired}]

        job.result.side_effect = complete
        return job


def test_correction_then_repeat_changes_one_pointer_and_keeps_candidate_counts(prepared):
    warehouse = Warehouse(prepared)
    before = deepcopy(warehouse.rows)
    first = publish_selection(warehouse.api, prepared)
    repeat = publish_selection(warehouse.api, prepared)
    assert first["status"] == "selected"
    assert repeat["status"] == "already_selected"
    assert warehouse.writes == 1
    assert warehouse.selections == [asdict(prepared.selection)]
    assert warehouse.rows == before
    report = json.loads(prepared.metadata_json)["report_json"]
    report = json.loads(report)
    assert report["race_summary"]["median_duration_s"] == 6600
    assert report["race_summary"]["top_n_median_duration_s"] == 6600
    assert report["result_quality"]["candidate_count"] == 5
    assert report["weather_coverage"]["matched_count"] == 2
    assert len(first["jobs"]) == 2
    assert first["jobs"][1]["job_id"] != repeat["jobs"][1]["job_id"]


@pytest.mark.parametrize("problem", [
    "missing_receipt", "local_receipt", "failed_receipt", "other_attempt",
    "other_validation", "duplicate_receipt", "duplicate_metadata", "partial_rows",
    "duplicate_rows", "changed_duration", "changed_report", "changed_digest",
])
def test_invalid_candidate_never_submits_a_write(prepared, problem):
    warehouse = Warehouse(prepared)
    if problem == "missing_receipt":
        warehouse.receipts.clear()
    elif problem in {"local_receipt", "failed_receipt", "other_attempt", "other_validation"}:
        field, value = {
            "local_receipt": ("validation_scope", "local_report"),
            "failed_receipt": ("status", "failed"),
            "other_attempt": ("attempt_id", "some-other-success"),
            "other_validation": ("validation_invocation_id", "different-validation"),
        }[problem]
        warehouse.receipts[0][field] = value
    elif problem == "duplicate_receipt":
        warehouse.receipts *= 2
    elif problem == "duplicate_metadata":
        warehouse.metadata *= 2
    elif problem == "partial_rows":
        warehouse.rows.pop()
    elif problem == "duplicate_rows":
        warehouse.rows.append(deepcopy(warehouse.rows[0]))
    elif problem == "changed_duration":
        warehouse.rows[0]["duration_s"] += 1
    elif problem == "changed_report":
        report = json.loads(warehouse.metadata[0]["report_json"])
        report["race_summary"]["top_n_median_duration_s"] = 8000
        warehouse.metadata[0]["report_json"] = canonical_json(report)
    else:
        warehouse.metadata[0]["result_rows_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        publish_selection(warehouse.api, prepared)
    assert warehouse.api.query.call_count == 1
    assert warehouse.selections == [asdict(OLD)]
    assert warehouse.writes == 0


@pytest.mark.parametrize("problem", ["revision", "attempt", "duplicate", "rows", "receipt", "metadata"])
def test_changes_between_validation_and_write_preserve_current_selection(prepared, problem):
    warehouse = Warehouse(prepared)
    expected_selections = {
        "revision": [asdict(replace(OLD, revision_id="c" * 64))],
        "attempt": [asdict(replace(OLD, successful_attempt_id="newer-success"))],
        "duplicate": [asdict(OLD), asdict(OLD)],
    }.get(problem, [asdict(OLD)])

    def change():
        if problem == "revision":
            warehouse.selections[0]["revision_id"] = "c" * 64
        elif problem == "attempt":
            warehouse.selections[0]["successful_attempt_id"] = "newer-success"
        elif problem == "duplicate":
            warehouse.selections *= 2
        elif problem == "rows":
            warehouse.rows[0]["duration_s"] += 1
        elif problem == "receipt":
            warehouse.receipts[0]["status"] = "failed"
        else:
            warehouse.metadata[0]["candidate_count"] += 1

    warehouse.before_write = change
    with pytest.raises(SelectionOutcomeUnknown) as error:
        publish_selection(warehouse.api, prepared)
    assert error.value.job_id.startswith("runwx_select_")
    assert warehouse.writes == 0
    assert warehouse.selections != [asdict(prepared.selection)]
    assert warehouse.selections == expected_selections


def test_initial_selection_requires_explicit_absence(prepared):
    warehouse = Warehouse(prepared)
    warehouse.selections.clear()
    with pytest.raises(SelectionOutcomeUnknown):
        publish_selection(warehouse.api, prepared)
    assert warehouse.selections == []
    assert publish_selection(warehouse.api, replace(prepared, expected=None))["status"] == "selected"


def test_lost_response_does_not_retry_and_recheck_does_not_rewrite(prepared):
    warehouse = Warehouse(prepared)
    warehouse.lose_response = True
    with pytest.raises(SelectionOutcomeUnknown) as error:
        publish_selection(warehouse.api, prepared)
    assert warehouse.api.query.call_count == 2
    assert warehouse.writes == 1  # A timeout is not evidence of a rollback.
    assert error.value.job_id == warehouse.api.query.call_args.kwargs["job_id"]
    warehouse.lose_response = False
    assert publish_selection(warehouse.api, prepared)["status"] == "already_selected"
    assert warehouse.writes == 1


def test_job_limits_and_guard_sql_are_sent_with_parameters(prepared):
    warehouse = Warehouse(prepared)
    publish_selection(warehouse.api, prepared)
    for call in warehouse.api.query.call_args_list:
        assert call.kwargs["location"] == "europe-west1"
        assert call.kwargs["retry"] is None and call.kwargs["job_retry"] is None
        config = call.kwargs["job_config"]
        assert config.maximum_bytes_billed == 100 * 1024 * 1024
        assert not config.use_query_cache and not config.use_legacy_sql
        assert config.create_session is False and config.connection_properties == []
        assert int(config.job_timeout_ms) == 300000
    sql = warehouse.api.query.call_args.args[0]
    assert sql.index("BEGIN TRANSACTION") < sql.index("AS 'candidate changed'")
    assert sql.index("AS 'candidate changed'") < sql.index("UPDATE") < sql.index("COMMIT TRANSACTION")
    assert "@expected_attempt_id" in sql and "@expected_revision_id" in sql
    assert "@@row_count = 1" in sql
    assert "selected_revision_results" not in sql  # Validation cannot depend on publication.
    assert OLD.successful_attempt_id not in sql


def test_other_project_or_event_is_rejected_before_query(prepared):
    warehouse = Warehouse(prepared)
    warehouse.api.project = "different-project"
    with pytest.raises(ValueError, match="project"):
        publish_selection(warehouse.api, prepared)
    warehouse.api.query.assert_not_called()
    with pytest.raises(ValueError, match="event"):
        replace(prepared, expected=replace(OLD, event_id="other:event"))


def test_equivalent_timestamps_numbers_and_relocated_report_paths_are_allowed(prepared):
    warehouse = Warehouse(prepared)
    warehouse.rows = json.loads(canonical_json(warehouse.rows).replace("+00:00", "Z"))
    assert warehouse.rows[0]["weather"]["precipitation_mm"] == 0.0
    warehouse.rows[0]["weather"]["precipitation_mm"] = 0
    report = json.loads(warehouse.metadata[0]["report_json"])
    report["sources"]["race"]["file"] = "/another/mount/race.html"
    report["sources"]["weather"]["file"] = "/another/mount/weather.csv"
    warehouse.metadata[0]["report_json"] = canonical_json(report)
    assert publish_selection(warehouse.api, prepared)["status"] == "selected"


def test_repeating_current_selection_still_requires_valid_candidate(prepared):
    warehouse = Warehouse(prepared)
    warehouse.selections = [asdict(prepared.selection)]
    warehouse.receipts.clear()
    with pytest.raises(ValueError):
        publish_selection(warehouse.api, prepared)
    assert warehouse.api.query.call_count == 1
    assert warehouse.writes == 0


def test_prepared_metadata_matches_existing_warehouse_schema(prepared):
    from runwx.adapters.bigquery.result_load import _normalise_fields

    root = Path("dbt/contracts/revisions")
    for filename, rows in (
        ("analysis_revisions", [json.loads(prepared.metadata_json)]),
        ("revision_result_rows", json.loads(prepared.rows_json)),
        ("revision_attempts", [json.loads(prepared.receipt_json)]),
        ("event_selections", [asdict(prepared.selection)]),
    ):
        schema = json.loads((root / f"{filename}.schema.json").read_text())
        assert [_normalise_fields(row, schema) for row in rows] == rows


@pytest.mark.parametrize("dataset", ["one.part.extra", "project.dataset`;DROP TABLE x", "only_one"])
def test_dataset_identifiers_cannot_inject_sql(prepared, dataset):
    with pytest.raises(ValueError, match="project.dataset"):
        replace(prepared, dataset=dataset)
