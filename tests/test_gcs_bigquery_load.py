from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket

import pytest

from runwx.adapters.gcs.warehouse_input import prepare_stored_load
from runwx.gcs_bigquery_load import main
from runwx.services.snapshot_artifacts import build_snapshot_artifacts


REPORT_URI = "gs://outputs/reports/execution-1/task-0-attempt-0.json"
EXPORT_URI = "gs://outputs/reports/execution-1/task-0-attempt-0.ndjson"
REPORT_GENERATION = 123
EXPORT_GENERATION = 122
TABLE = "runwx-learning-mifuha.runwx_staging.cloud_results"


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("local Storage/BigQuery tests attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


class Blob:
    def __init__(self, storage, bucket, name, generation):
        self.storage = storage
        self.key = (bucket, name, generation)

    def download_as_bytes(self, **kwargs):
        self.storage.downloads.append((self.key, kwargs))
        if kwargs["if_generation_match"] != self.key[2]:
            raise ValueError("generation precondition mismatch")
        try:
            return self.storage.objects[self.key]
        except KeyError as error:
            raise FileNotFoundError("exact object generation not found") from error


class Bucket:
    def __init__(self, storage, name):
        self.storage = storage
        self.name = name

    def blob(self, name, generation=None):
        return Blob(self.storage, self.name, name, generation)


class Storage:
    def __init__(self, objects):
        self.objects = objects
        self.downloads = []

    def bucket(self, name):
        return Bucket(self, name)


@pytest.fixture
def artifact_pair():
    artifacts = build_snapshot_artifacts(
        Path("data/sample_race_synthetic.html"),
        Path("data/sample_lydd_weather_synthetic.csv"),
        course_id="runwx-synthetic-half",
        distance_m=21097,
        timezone_name="Europe/London",
        weather_kind="synthetic",
        race_kind="synthetic",
        export_weather_kind="synthetic",
    )
    envelope = {
        "cloud_report_schema_version": 2,
        "report": artifacts.report,
        "execution": {
            "job": "runwx-report",
            "name": "execution-1",
            "task_index": 0,
            "task_attempt": 0,
            "image": "registry/runwx@sha256:" + "1" * 64,
            "source_revision": "2" * 40,
        },
        "storage": {
            "inputs": {
                "race": {"uri": "gs://inputs/race.html", "generation": "10"},
                "weather": {"uri": "gs://inputs/weather.csv", "generation": "11"},
            },
            "output_uri": REPORT_URI,
            "outputs": {
                "report": {"uri": REPORT_URI},
                "result_export": {
                    "uri": EXPORT_URI,
                    "sha256": artifacts.result_sha256,
                    "bytes": len(artifacts.result_payload),
                    "row_count": len(artifacts.result_rows),
                    "schema_version": 1,
                },
            },
        },
    }
    return artifacts, envelope


def storage_for(artifacts, envelope):
    report = json.dumps(envelope, sort_keys=True, allow_nan=False).encode()
    return Storage({
        ("outputs", "reports/execution-1/task-0-attempt-0.json", REPORT_GENERATION): report,
        ("outputs", "reports/execution-1/task-0-attempt-0.ndjson", EXPORT_GENERATION): artifacts.result_payload,
    })


def prepare(storage, expected_hash):
    return prepare_stored_load(
        storage,
        report_uri=REPORT_URI,
        report_generation=str(REPORT_GENERATION),
        result_export_uri=EXPORT_URI,
        result_export_generation=str(EXPORT_GENERATION),
        expected_sha256=expected_hash,
        table_id=TABLE,
    )


def cli_args(expected_hash, *, execute=False):
    args = [
        "--report-uri", REPORT_URI,
        "--report-generation", str(REPORT_GENERATION),
        "--result-export-uri", EXPORT_URI,
        "--result-export-generation", str(EXPORT_GENERATION),
        "--expected-sha256", expected_hash,
        "--table", TABLE,
    ]
    return [*args, "--execute"] if execute else args


def test_exact_pair_prepares_existing_loader_input_and_records_generations(artifact_pair):
    artifacts, envelope = artifact_pair
    storage = storage_for(artifacts, envelope)
    stored = prepare(storage, artifacts.result_sha256)

    assert stored.prepared.payload == artifacts.result_payload
    assert stored.prepared.rows == artifacts.result_rows
    assert stored.summary()["report_generation"] == str(REPORT_GENERATION)
    assert stored.summary()["result_export_generation"] == str(EXPORT_GENERATION)
    assert stored.summary()["source_execution"] == envelope["execution"]
    assert [download[0][2] for download in storage.downloads] == [REPORT_GENERATION, EXPORT_GENERATION]
    assert all(download[1] == {
        "if_generation_match": download[0][2], "checksum": "auto", "timeout": 30
    } for download in storage.downloads)


def test_storage_preview_never_creates_a_bigquery_client(
    artifact_pair, monkeypatch, capsys
):
    artifacts, envelope = artifact_pair
    storage = storage_for(artifacts, envelope)

    def forbidden_client(*args, **kwargs):
        pytest.fail("preview created a BigQuery client")

    monkeypatch.setattr("google.cloud.bigquery.Client", forbidden_client)
    main(cli_args(artifacts.result_sha256), storage_client=storage)
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "prepared_from_storage"
    assert result["candidate_count"] == 5
    assert result["planned_load_job_id"].startswith("runwx_load_")
    assert result["export_sha256"] == artifacts.result_sha256


def test_execute_calls_the_existing_safe_loader_only_after_pair_validation(
    artifact_pair, monkeypatch, capsys
):
    artifacts, envelope = artifact_pair
    storage = storage_for(artifacts, envelope)
    bigquery_client = object()
    calls = []

    def fake_load(client, prepared):
        calls.append((client, prepared))
        return {**prepared.summary(), "status": "loaded_verified", "load_job_id": prepared.job_id}

    monkeypatch.setattr("runwx.gcs_bigquery_load.load_prepared", fake_load)
    main(
        cli_args(artifacts.result_sha256, execute=True),
        storage_client=storage,
        bigquery_client=bigquery_client,
    )
    result = json.loads(capsys.readouterr().out)

    assert len(calls) == 1
    assert calls[0][0] is bigquery_client
    assert calls[0][1].payload == artifacts.result_payload
    assert result["status"] == "loaded_verified"
    assert result["result_export_generation"] == str(EXPORT_GENERATION)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("cloud_report_schema_version",), 1),
        (("storage", "output_uri"), "gs://outputs/wrong.json"),
        (("storage", "outputs", "result_export", "uri"), "gs://outputs/wrong.ndjson"),
        (("storage", "outputs", "result_export", "sha256"), "0" * 64),
        (("storage", "outputs", "result_export", "bytes"), 1),
        (("storage", "outputs", "result_export", "row_count"), 4),
        (("report", "result_quality", "accepted_count"), 2),
        (("report", "settings", "timezone_name"), "UTC"),
        (("report", "race", "started_at_utc"), "2022-03-06T11:00:00+00:00"),
        (("report", "sources", "race", "provider"), "other"),
        (("report", "sources", "race", "source_event_id"), "other"),
        (("report", "sources", "race", "sha256"), "3" * 64),
    ],
)
def test_report_mismatch_fails_before_safe_loader_can_be_called(artifact_pair, path, value):
    artifacts, envelope = artifact_pair
    changed = deepcopy(envelope)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    storage = storage_for(artifacts, changed)

    with pytest.raises(ValueError, match="identify|reconcile"):
        prepare(storage, artifacts.result_sha256)


@pytest.mark.parametrize("problem", ["wrong_report_generation", "wrong_export_generation", "truncated_export"])
def test_missing_or_truncated_exact_object_fails_during_preparation(artifact_pair, problem):
    artifacts, envelope = artifact_pair
    storage = storage_for(artifacts, envelope)
    report_generation = REPORT_GENERATION
    export_generation = EXPORT_GENERATION
    if problem == "wrong_report_generation":
        report_generation += 1
    elif problem == "wrong_export_generation":
        export_generation += 1
    else:
        key = ("outputs", "reports/execution-1/task-0-attempt-0.ndjson", EXPORT_GENERATION)
        storage.objects[key] = storage.objects[key][:-20]

    with pytest.raises((FileNotFoundError, ValueError)):
        prepare_stored_load(
            storage,
            report_uri=REPORT_URI,
            report_generation=report_generation,
            result_export_uri=EXPORT_URI,
            result_export_generation=export_generation,
            expected_sha256=artifacts.result_sha256,
            table_id=TABLE,
        )


@pytest.mark.parametrize("generation", ["0", "01", "-1", "abc", True])
def test_invalid_generation_is_rejected_before_download(artifact_pair, generation):
    artifacts, envelope = artifact_pair
    storage = storage_for(artifacts, envelope)
    with pytest.raises(ValueError, match="positive Cloud Storage generation"):
        prepare_stored_load(
            storage,
            report_uri=REPORT_URI,
            report_generation=generation,
            result_export_uri=EXPORT_URI,
            result_export_generation=EXPORT_GENERATION,
            expected_sha256=artifacts.result_sha256,
            table_id=TABLE,
        )
    assert storage.downloads == []
