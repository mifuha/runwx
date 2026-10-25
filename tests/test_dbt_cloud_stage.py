"""Cloud dbt boundary tests without credentials, dbt, BigQuery or network."""

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import socket
import sys
from unittest.mock import Mock
import zipfile
from io import BytesIO

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location("stage_runner", ROOT / "dbt/stage_runner.py")
stage_runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(stage_runner)
sys.modules["stage_runner"] = stage_runner
SPEC = importlib.util.spec_from_file_location("cloud_stage", ROOT / "dbt/cloud_stage.py")
cloud_stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cloud_stage)


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("cloud-stage test attempted network access")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def config():
    return {
        "project": "runwx-example", "location": "europe-west1",
        "source_dataset": "staging", "source_table": "snapshot_a",
        "edition_dataset": "edition_a", "comparison_dataset": "edition_a",
        "comparison_datasets": ["edition_a", "edition_b"],
        "comparison_baseline": "edition_a", "top_n": 20,
    }


@pytest.fixture
def expectations():
    return {
        "edition": {"mart": {"event_id": "example:a"},
                    "weather": {"enriched_count": 1}},
        "comparison": [
            {"snapshot_dataset": "edition_a"},
            {"snapshot_dataset": "edition_b"},
        ],
    }


@pytest.fixture
def execution():
    return {
        "job": "runwx-dbt", "name": "runwx-dbt-abc12",
        "task_index": 0, "task_attempt": 0,
        "image": "europe-west1-docker.pkg.dev/example/runwx/runwx-dbt@sha256:" + "a" * 64,
        "source_revision": "b" * 40,
    }


@pytest.fixture
def storage():
    saved = {}
    blobs = {}

    def blob(name):
        if name not in blobs:
            item = Mock()

            def upload(payload, *, content_type, if_generation_match, timeout):
                assert if_generation_match == 0
                if name in saved:
                    raise FileExistsError("object already exists")
                saved[name] = (payload, content_type, timeout)
            item.upload_from_string.side_effect = upload
            blobs[name] = item
        return blobs[name]

    client = Mock()
    client.bucket.side_effect = lambda name: Mock(blob=blob)
    return client, saved, blobs


def successful_runner(config, expectations, output_dir, project_dir):
    output_dir.mkdir()
    (output_dir / "expectations.json").write_text(json.dumps(expectations))
    (output_dir / "execution.json").write_text('{"status":"reconciled"}\n')
    target = output_dir / "edition/target"
    target.mkdir(parents=True)
    (target / "manifest.json").write_text("{}")
    return {"status": "reconciled", "analytical_reconciliation": "passed"}


def invoke(storage, config, expectations, execution, runner=successful_runner):
    return cloud_stage.run_cloud_stage(
        storage,
        config=config,
        expectations=expectations,
        output_prefix="gs://evidence/dbt-runs",
        execution=execution,
        project_dir=ROOT / "dbt",
        runner=runner,
    )


def test_success_uploads_complete_create_only_archive_and_manifest(
        storage, config, expectations, execution):
    client, saved, _ = storage
    manifest = invoke(client, config, expectations, execution)
    stem = "dbt-runs/runwx-dbt-abc12/task-0-attempt-0"
    archive, archive_type, archive_timeout = saved[stem + ".zip"]
    encoded, manifest_type, manifest_timeout = saved[stem + ".json"]
    names = zipfile.ZipFile(BytesIO(archive)).namelist()

    assert names == [
        "cloud-execution.json",
        "execution/edition/target/manifest.json",
        "execution/execution.json",
        "execution/expectations.json",
    ]
    assert archive_type == "application/zip" and archive_timeout == 60
    assert manifest_type == "application/json" and manifest_timeout == 30
    assert json.loads(encoded) == manifest
    assert manifest["status"] == "reconciled"
    assert manifest["analytical_reconciliation"] == "passed"
    assert manifest["storage"]["archive_sha256"] == sha256(archive).hexdigest()
    assert manifest["storage"]["file_count"] == 4
    assert manifest["storage"]["archive_uri"] == f"gs://evidence/{stem}.zip"
    assert manifest["execution"] == execution


def test_runner_failure_uploads_failure_evidence_then_fails_task(
        storage, config, expectations, execution):
    client, saved, _ = storage

    def fail(config, expectations, output_dir, project_dir):
        output_dir.mkdir()
        (output_dir / "execution.json").write_text(
            '{"status":"failed","analytical_reconciliation":"not_performed"}\n'
        )
        raise ValueError("edition test failed")

    with pytest.raises(ValueError, match="edition test failed"):
        invoke(client, config, expectations, execution, runner=fail)

    manifest = json.loads(saved[
        "dbt-runs/runwx-dbt-abc12/task-0-attempt-0.json"
    ][0])
    assert manifest["status"] == "failed"
    assert manifest["runner_status"] == "failed"
    assert manifest["analytical_reconciliation"] == "not_performed"
    assert manifest["error"] == {
        "type": "ValueError", "message": "edition test failed",
    }
    assert manifest["storage"]["file_count"] == 2


def test_existing_execution_evidence_is_never_overwritten(
        storage, config, expectations, execution):
    client, saved, _ = storage
    invoke(client, config, expectations, execution)
    previous = dict(saved)
    with pytest.raises(FileExistsError, match="already exists"):
        invoke(client, config, expectations, execution)
    assert saved == previous


def test_manifest_upload_failure_leaves_traceable_archive(
        storage, config, expectations, execution):
    client, saved, blobs = storage
    manifest_name = "dbt-runs/runwx-dbt-abc12/task-0-attempt-0.json"
    client.bucket("evidence").blob(manifest_name)
    blobs[manifest_name].upload_from_string.side_effect = RuntimeError("manifest upload failed")

    with pytest.raises(RuntimeError, match="manifest upload failed"):
        invoke(client, config, expectations, execution)

    assert "dbt-runs/runwx-dbt-abc12/task-0-attempt-0.zip" in saved
    assert manifest_name not in saved


@pytest.mark.parametrize("change", [
    {"name": "Bad/name"},
    {"task_attempt": -1},
    {"image": "registry/image:latest"},
    {"source_revision": "short"},
])
def test_invalid_execution_fails_before_runner_or_storage(
        storage, config, expectations, execution, change):
    client, saved, _ = storage
    execution.update(change)
    with pytest.raises(ValueError):
        invoke(
            client, config, expectations, execution,
            runner=lambda *args: pytest.fail("invalid execution invoked runner"),
        )
    client.bucket.assert_not_called()
    assert not saved


def test_entrypoint_uses_runtime_identity_and_embedded_revision(
        storage, config, expectations, execution, monkeypatch, capsys):
    client, saved, _ = storage
    environment = {
        "RUNWX_DBT_CONFIG": json.dumps(config),
        "RUNWX_DBT_EXPECTATIONS": json.dumps(expectations),
        "RUNWX_DBT_OUTPUT_PREFIX": "gs://evidence/dbt-runs",
        "RUNWX_IMAGE": execution["image"],
        "RUNWX_SOURCE_REVISION": execution["source_revision"],
        "CLOUD_RUN_JOB": execution["job"],
        "CLOUD_RUN_EXECUTION": execution["name"],
        "CLOUD_RUN_TASK_INDEX": "0",
        "CLOUD_RUN_TASK_ATTEMPT": "0",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cloud_stage.stage_runner, "execute", successful_runner)

    result = cloud_stage.main(client=client)

    assert result["status"] == "reconciled"
    assert json.loads(capsys.readouterr().out)["execution"] == execution
    assert len(saved) == 2


def test_invalid_entrypoint_configuration_creates_no_client(
        config, expectations, execution, monkeypatch):
    config["top_n"] = 0
    environment = {
        "RUNWX_DBT_CONFIG": json.dumps(config),
        "RUNWX_DBT_EXPECTATIONS": json.dumps(expectations),
        "RUNWX_DBT_OUTPUT_PREFIX": "gs://evidence/dbt-runs",
        "RUNWX_IMAGE": execution["image"],
        "RUNWX_SOURCE_REVISION": execution["source_revision"],
        "CLOUD_RUN_JOB": execution["job"],
        "CLOUD_RUN_EXECUTION": execution["name"],
        "CLOUD_RUN_TASK_INDEX": "0",
        "CLOUD_RUN_TASK_ATTEMPT": "0",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="top_n"):
        cloud_stage.main(client=None)


def test_folkestone_validation_case_matches_runner_contract():
    case = json.loads((
        ROOT / "infra/gcp/examples/folkestone-2019-dbt-stage.json"
    ).read_text())
    config = stage_runner.validate_config(case["dbt_stage_config"])
    expectations = stage_runner.validate_expectations(
        case["dbt_stage_expectations"], config
    )

    assert config["source_table"] == "folkestone_2019_f95b3ae312e3"
    assert config["edition_dataset"] == config["comparison_dataset"]
    assert len(config["comparison_datasets"]) == len(expectations["comparison"]) == 3
    assert expectations["edition"]["mart"]["finisher_count"] == 459
    assert expectations["edition"]["weather"]["enriched_count"] == 459
    assert len(stage_runner.canonical_json(expectations).encode()) < 32768


@pytest.fixture
def failure_environment(config, expectations, execution, monkeypatch):
    for key, value in {
        'RUNWX_DBT_CONFIG': json.dumps(config),
        'RUNWX_DBT_EXPECTATIONS': json.dumps(expectations),
        'RUNWX_DBT_OUTPUT_PREFIX': 'gs://evidence/dbt-runs',
        'RUNWX_IMAGE': execution['image'],
        'RUNWX_SOURCE_REVISION': execution['source_revision'],
        'CLOUD_RUN_JOB': execution['job'],
        'CLOUD_RUN_EXECUTION': execution['name'],
        'CLOUD_RUN_TASK_INDEX': '0', 'CLOUD_RUN_TASK_ATTEMPT': '0',
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('RUNWX_EXECUTION_PURPOSE', raising=False)


@pytest.mark.parametrize('exercise', [False, True])
def test_entrypoint_logs_one_safe_failure_and_preserves_evidence(
        storage, failure_environment, monkeypatch, capsys, exercise):
    client, saved, _ = storage
    error = ValueError('private source detail must not appear in the alert')
    runner = Mock(side_effect=error)
    monkeypatch.setattr(cloud_stage.stage_runner, 'execute', runner)
    if exercise:
        monkeypatch.setenv('RUNWX_EXECUTION_PURPOSE', 'exercise')
    with pytest.raises(ValueError) as caught:
        cloud_stage.main(client=client)
    assert caught.value is error
    runner.assert_called_once()
    event = json.loads(capsys.readouterr().out)
    assert event == {
        'severity': 'ERROR',
        'message': 'runwx dbt job failed; inspect execution logs and retained evidence',
        'event': 'runwx_dbt_failure', 'event_version': 1,
        'stage': 'dbt_execution', 'edition': 'edition_a',
        'reason': 'ValueError', 'execution': 'runwx-dbt-abc12',
        'purpose': 'exercise' if exercise else 'operational',
    }
    assert len(saved) == 2
    manifest = json.loads(saved['dbt-runs/runwx-dbt-abc12/task-0-attempt-0.json'][0])
    assert manifest['status'] == 'failed'


def test_malformed_config_signals_without_running_or_uploading(
        storage, failure_environment, monkeypatch, capsys):
    client, saved, _ = storage
    monkeypatch.setenv('RUNWX_DBT_CONFIG', '{')
    runner = Mock()
    monkeypatch.setattr(cloud_stage.stage_runner, 'execute', runner)
    with pytest.raises(json.JSONDecodeError):
        cloud_stage.main(client=client)
    event = json.loads(capsys.readouterr().out)
    assert event['stage'] == 'configuration'
    assert event['edition'] == 'unknown'
    assert event['reason'] == 'JSONDecodeError'
    runner.assert_not_called()
    assert not saved


def test_evidence_upload_failure_also_signals_failure(
        storage, failure_environment, monkeypatch, capsys):
    client, _, _ = storage
    client.bucket.side_effect = OSError('private bucket detail')
    monkeypatch.setattr(cloud_stage.stage_runner, 'execute', successful_runner)
    with pytest.raises(OSError):
        cloud_stage.main(client=client)
    event = json.loads(capsys.readouterr().out)
    assert event['reason'] == 'OSError'
    assert 'private bucket' not in json.dumps(event)


def test_logging_error_does_not_mask_original_failure(
        failure_environment, monkeypatch):
    error = ValueError('original failure')
    monkeypatch.setattr(cloud_stage, '_main', Mock(side_effect=error))
    monkeypatch.setattr(cloud_stage, 'print', Mock(side_effect=OSError('closed')), raising=False)
    with pytest.raises(ValueError) as caught:
        cloud_stage.main(client=Mock())
    assert caught.value is error


def test_real_runner_failure_stops_comparison_and_emits_event(
        storage, failure_environment, monkeypatch, capsys):
    client, saved, _ = storage
    calls = []

    def fail_edition(plan, stage):
        calls.append(plan['stage'])
        raise ValueError('deliberate edition failure')

    monkeypatch.setattr(cloud_stage.stage_runner, 'execute_build', fail_edition)
    reconcile = Mock()
    monkeypatch.setattr(cloud_stage.stage_runner, 'reconcile', reconcile)
    with pytest.raises(ValueError, match='deliberate edition failure'):
        cloud_stage.main(client=client)
    assert calls == ['edition']
    reconcile.assert_not_called()
    assert json.loads(capsys.readouterr().out)['event'] == 'runwx_dbt_failure'
    archive = saved['dbt-runs/runwx-dbt-abc12/task-0-attempt-0.zip'][0]
    with zipfile.ZipFile(BytesIO(archive)) as evidence:
        record = json.loads(evidence.read('execution/execution.json'))
    assert record['status'] == 'failed'
    assert record['analytical_reconciliation'] == 'not_performed'
    assert [stage['stage'] for stage in record['stages']] == ['edition']
