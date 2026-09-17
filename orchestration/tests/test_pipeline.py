from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest

from conftest import ROOT, Storage
import cloud_stage
import stage_runner
from runwx.services.snapshot_artifacts import build_snapshot_artifacts
from runwx_airflow.config import validate_config
from runwx_airflow import tasks


def execution(config, stage):
    return {"name": f"projects/{config['project']}/locations/{config['region']}/jobs/"
                    f"{config[stage]['job']}/executions/{config[stage]['job']}-abc12",
            "operation": "projects/example/locations/europe-west1/operations/123"}


def test_frozen_configuration_reuses_existing_dbt_case(config):
    assert validate_config(config) == config
    existing = json.loads((ROOT / "infra/gcp/examples/folkestone-2019-dbt-stage.json").read_text())
    assert config["dbt"]["config"] == existing["dbt_stage_config"]
    assert config["dbt"]["expectations"] == existing["dbt_stage_expectations"]


@pytest.mark.parametrize("change", [
    lambda c: c.update(table_id="example.wrong.table"),
    lambda c: c.update(export_sha256="not-a-hash"),
    lambda c: c["report"].update(image="registry/runwx:latest"),
    lambda c: c["report"]["settings"].update(top_n=100),
    lambda c: c["report"]["settings"].update(distance_m=20000),
    lambda c: c["report"].update(race_sha256="0" * 64),
    lambda c: c["dbt"].update(job=c["report"]["job"]),
    lambda c: c["dbt"]["config"].update(comparison_datasets=[]),
])
def test_invalid_configuration_fails_without_cloud(config, change):
    change(config)
    with pytest.raises(ValueError):
        validate_config(config)


def cloud_client(config, stage):
    template = SimpleNamespace(max_retries=0, containers=[SimpleNamespace(image=config[stage]["image"])])
    job = SimpleNamespace(template=SimpleNamespace(task_count=1, parallelism=1, template=template))
    client = Mock()
    client.get_job.return_value = job
    op = client.run_job.return_value
    op.operation.name = "operations/submitted-once"
    name = execution(config, stage)["name"]
    op.result.return_value = SimpleNamespace(
        name=name, job=config[stage]["job"], task_count=1, succeeded_count=1,
        failed_count=0, cancelled_count=0, retried_count=0,
    )
    return client


@pytest.mark.parametrize("stage", ["report", "dbt"])
def test_submit_once_and_return_this_execution(config, stage):
    client = cloud_client(config, stage)
    result = tasks.execute_job(config, stage, client=client)
    assert result["name"] == execution(config, stage)["name"]
    assert result["operation"] == "operations/submitted-once"
    client.run_job.assert_called_once()
    assert client.run_job.call_args.kwargs["retry"] is None
    request = client.run_job.call_args.kwargs["request"]
    # Validate the real SDK request shape without credentials or an RPC.
    from google.cloud.run_v2 import RunJobRequest
    assert RunJobRequest(request).overrides.task_count == 1
    env = {v["name"]: v["value"] for v in request["overrides"]["container_overrides"][0]["env"]}
    if stage == "report":
        assert json.loads(env["RUNWX_REPORT_SETTINGS"]) == config["report"]["settings"]
    else:
        assert json.loads(env["RUNWX_DBT_CONFIG"]) == config["dbt"]["config"]


def test_wrong_deployed_image_blocks_submission(config):
    client = cloud_client(config, "report")
    client.get_job.return_value.template.template.containers[0].image = "wrong@sha256:" + "0" * 64
    with pytest.raises(ValueError, match="pinned image"):
        tasks.execute_job(config, "report", client=client)
    client.run_job.assert_not_called()


def test_execution_parent_job_must_match(config):
    client = cloud_client(config, "report")
    client.run_job.return_value.result.return_value.job = "another-job"
    with pytest.raises(ValueError, match="successfully"):
        tasks.execute_job(config, "report", client=client)


def test_wait_failure_does_not_resubmit_and_logs_operation(config, caplog):
    client = cloud_client(config, "report")
    client.run_job.return_value.result.side_effect = TimeoutError("lost response")
    with caplog.at_level("INFO"), pytest.raises(TimeoutError):
        tasks.execute_job(config, "report", client=client)
    client.run_job.assert_called_once()
    assert "operations/submitted-once" in caplog.text


@pytest.mark.parametrize("field,value", [("succeeded_count", 0), ("failed_count", 1),
                                       ("retried_count", 1), ("cancelled_count", 1)])
def test_unsuccessful_cloud_task_cannot_advance(config, field, value):
    client = cloud_client(config, "dbt")
    setattr(client.run_job.return_value.result.return_value, field, value)
    with pytest.raises(ValueError, match="successfully"):
        tasks.execute_job(config, "dbt", client=client)


@pytest.fixture
def export_pair(config):
    # Public synthetic fixture bytes exercise the real parser and export contract.
    artifacts = build_snapshot_artifacts(
        ROOT / "data/sample_race_synthetic.html", ROOT / "data/sample_lydd_weather_synthetic.csv",
        course_id="test-course", distance_m=21097, timezone_name="Europe/London",
        weather_kind="synthetic", race_kind="synthetic", export_weather_kind="synthetic",
    )
    config["export_sha256"] = artifacts.result_sha256
    for kind in ("race", "weather"):
        config["report"][f"{kind}_sha256"] = artifacts.report["sources"][kind]["sha256"]
    identity = tasks.execution_identity(config, "report", execution(config, "report"))
    stem = f"{config['report']['output_prefix']}/{identity['name']}/task-0-attempt-0"
    envelope = {
        "cloud_report_schema_version": 2, "report": artifacts.report, "execution": identity,
        "storage": {"output_uri": stem + ".json", "inputs": {
            kind: {"uri": config["report"][f"{kind}_uri"], "generation": "1"}
            for kind in ("race", "weather")}, "outputs": {
                "report": {"uri": stem + ".json"},
                "result_export": {"uri": stem + ".ndjson", "sha256": artifacts.result_sha256,
                                  "bytes": len(artifacts.result_payload),
                                  "row_count": len(artifacts.result_rows), "schema_version": 1},
            }},
    }
    storage = Storage({stem + ".json": (12, json.dumps(envelope).encode()),
                       stem + ".ndjson": (11, artifacts.result_payload)})
    return storage, stem


def test_exact_export_handoff_and_existing_loader_reused(config, export_pair, monkeypatch):
    storage, _ = export_pair
    refs = tasks.verify_export(config, execution(config, "report"), client=storage)
    assert refs["report_generation"] == 12 and refs["result_export_generation"] == 11
    loader = Mock(return_value={"status": "already_present_verified"})
    monkeypatch.setattr(tasks, "load_prepared", loader)
    warehouse = Mock()
    result = tasks.load_snapshot(config, refs, storage=storage, warehouse=warehouse)
    assert result["status"] == "already_present_verified"
    assert loader.call_args.args[0] is warehouse
    assert loader.call_args.args[1].payload == storage.objects[refs["result_export_uri"]][1]
    assert "rows" not in refs and "rows" not in result


@pytest.mark.parametrize("mutation", ["hash", "execution", "missing_export"])
def test_incomplete_or_wrong_export_fails(config, export_pair, mutation):
    storage, stem = export_pair
    if mutation == "hash":
        config["export_sha256"] = "0" * 64
    elif mutation == "execution":
        envelope = json.loads(storage.objects[stem + ".json"][1])
        envelope["execution"]["name"] = "some-other-execution"
        storage.objects[stem + ".json"] = (12, json.dumps(envelope).encode())
    else:
        del storage.objects[stem + ".ndjson"]
    with pytest.raises((ValueError, KeyError)):
        tasks.verify_export(config, execution(config, "report"), client=storage)


def test_replaced_export_fails_before_loader(config, export_pair, monkeypatch):
    storage, stem = export_pair
    refs = tasks.verify_export(config, execution(config, "report"), client=storage)
    storage.objects[stem + ".ndjson"] = (11, b"corrupted")
    loader = Mock()
    monkeypatch.setattr(tasks, "load_prepared", loader)
    with pytest.raises(ValueError, match="SHA-256"):
        tasks.load_snapshot(config, refs, storage=storage, warehouse=Mock())
    loader.assert_not_called()


@pytest.fixture
def dbt_pair(config):
    saved = {}
    client = Mock()

    def bucket(name):
        def blob(path):
            item = Mock()
            item.upload_from_string.side_effect = lambda data, **kwargs: saved.update({
                f"gs://{name}/{path}": (len(saved) + 1, data.encode() if isinstance(data, str) else data)})
            return item
        return SimpleNamespace(blob=blob)

    client.bucket.side_effect = bucket
    expected_hash = sha256(stage_runner.canonical_json(config["dbt"]["expectations"]).encode()).hexdigest()

    def runner(cfg, expected, output_dir, project_dir):
        output_dir.mkdir()
        record = {"status": "reconciled", "analytical_reconciliation": "passed", "config": cfg,
                  "expectations_sha256": expected_hash,
                  "stages": [{"stage": s, "status": "passed"} for s in ("edition", "comparison")]}
        (output_dir / "execution.json").write_text(json.dumps(record))
        (output_dir / "expectations.json").write_text(json.dumps(expected))
        (output_dir / "reconciliation").mkdir()
        plans = stage_runner.build_reconciliation_plan(cfg, expected)
        reconciliation = {"status": "reconciled", "expectations_sha256": expected_hash,
                          "queries": [{"stage": p["stage"], "status": "passed",
                                       "job_id": f"test-{p['stage']}", "errors": None,
                                       "sql_sha256": sha256(p["sql"].encode()).hexdigest(),
                                       "actual_rows": p["expected"]} for p in plans]}
        (output_dir / "reconciliation/reconciliation.json").write_text(json.dumps(reconciliation))
        return record

    identity = tasks.execution_identity(config, "dbt", execution(config, "dbt"))
    manifest = cloud_stage.run_cloud_stage(
        client, config=config["dbt"]["config"], expectations=config["dbt"]["expectations"],
        output_prefix=config["dbt"]["output_prefix"], execution=identity, runner=runner,
    )
    return Storage(saved), manifest


def test_verify_artifacts_from_existing_cloud_wrapper(config, dbt_pair):
    storage, manifest = dbt_pair
    result = tasks.verify_dbt_evidence(config, execution(config, "dbt"), client=storage)
    assert result["status"] == "verified"
    assert result["archive_sha256"] == manifest["storage"]["archive_sha256"]
    assert result["manifest_generation"] == 2 and result["archive_generation"] == 1


@pytest.mark.parametrize("mutation", ["failed", "config", "archive", "missing_archive"])
def test_bad_dbt_evidence_prevents_pipeline_success(config, dbt_pair, mutation):
    storage, manifest = dbt_pair
    uri = manifest["storage"]["archive_uri"]
    if mutation == "failed":
        manifest["status"] = "failed"
        storage.objects[manifest["storage"]["manifest_uri"]] = (2, json.dumps(manifest).encode())
    elif mutation == "config":
        config["dbt"]["config"]["top_n"] = 100
    elif mutation == "archive":
        storage.objects[uri] = (1, b"corrupt")
    else:
        del storage.objects[uri]
    with pytest.raises((ValueError, KeyError)):
        tasks.verify_dbt_evidence(config, execution(config, "dbt"), client=storage)


@pytest.mark.parametrize("mutation", ["wrong_rows", "missing_query", "failed_stage"])
def test_valid_archive_hash_cannot_hide_failed_reconciliation(config, dbt_pair, mutation):
    storage, manifest = dbt_pair
    uri = manifest["storage"]["archive_uri"]
    with zipfile.ZipFile(BytesIO(storage.objects[uri][1])) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    path = ("execution/execution.json" if mutation == "failed_stage"
            else "execution/reconciliation/reconciliation.json")
    record = json.loads(files[path])
    if mutation == "wrong_rows":
        record["queries"][0]["actual_rows"][0]["mart"]["finisher_count"] = 1
    elif mutation == "missing_query":
        record["queries"].pop()
    else:
        record["stages"][1]["status"] = "failed"
    files[path] = json.dumps(record).encode()
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    payload = out.getvalue()
    storage.objects[uri] = (1, payload)
    manifest["storage"]["archive_bytes"] = len(payload)
    manifest["storage"]["archive_sha256"] = sha256(payload).hexdigest()
    storage.objects[manifest["storage"]["manifest_uri"]] = (2, json.dumps(manifest).encode())
    with pytest.raises(ValueError):
        tasks.verify_dbt_evidence(config, execution(config, "dbt"), client=storage)
