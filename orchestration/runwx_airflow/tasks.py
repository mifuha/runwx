"""Cloud I/O only. Parsing, loading and dbt remain in their existing modules."""

from hashlib import sha256
from io import BytesIO
import json
import logging
from pathlib import PurePosixPath
import zipfile

import stage_runner
from runwx.adapters.bigquery.result_load import load_prepared
from runwx.adapters.gcs.report_io import object_path
from runwx.adapters.gcs.warehouse_input import prepare_stored_load


LOG = logging.getLogger(__name__)


def execute_job(config, stage, *, client=None):
    """Submit once, retain the operation ID, and return this execution, not latest."""
    if client is None:
        from google.cloud import run_v2
        client = run_v2.JobsClient()
    spec = config[stage]
    name = f"projects/{config['project']}/locations/{config['region']}/jobs/{spec['job']}"
    job = client.get_job(request={"name": name}, retry=None, timeout=30)
    template = job.template.template
    if (job.template.task_count != 1 or job.template.parallelism != 1
            or template.max_retries != 0 or len(template.containers) != 1
            or template.containers[0].image != spec["image"]):
        raise ValueError("deployed job must match the pinned image and single-task/no-retry contract")
    if stage == "report":
        values = {
            "RUNWX_RACE_URI": spec["race_uri"], "RUNWX_RACE_SHA256": spec["race_sha256"],
            "RUNWX_WEATHER_URI": spec["weather_uri"],
            "RUNWX_WEATHER_SHA256": spec["weather_sha256"],
            "RUNWX_OUTPUT_PREFIX": spec["output_prefix"],
            "RUNWX_REPORT_SETTINGS": json.dumps(spec["settings"], sort_keys=True),
        }
        timeout = 900
    else:
        values = {
            "RUNWX_DBT_CONFIG": stage_runner.canonical_json(spec["config"]),
            "RUNWX_DBT_EXPECTATIONS": stage_runner.canonical_json(spec["expectations"]),
            "RUNWX_DBT_OUTPUT_PREFIX": spec["output_prefix"],
        }
        timeout = 1800
    operation = client.run_job(
        request={"name": name, "overrides": {
            "task_count": 1, "timeout": f"{timeout}s",
            "container_overrides": [{"env": [
                {"name": key, "value": value} for key, value in values.items()
            ]}],
        }}, retry=None, timeout=30,
    )
    LOG.info("Submitted %s; operation=%s", name, operation.operation.name)
    # An acknowledgement/wait failure must be investigated, never blindly retried.
    result = operation.result(timeout=timeout + 120)
    if (result.job != name or not result.name.startswith(name + "/executions/")
            or result.task_count != 1 or result.succeeded_count != 1
            or result.failed_count or result.cancelled_count or result.retried_count):
        raise ValueError("Cloud Run execution did not complete its one task successfully")
    LOG.info("Completed execution=%s", result.name)
    return {"name": result.name, "operation": operation.operation.name}


def execution_identity(config, stage, execution):
    spec = config[stage]
    prefix = f"projects/{config['project']}/locations/{config['region']}/jobs/{spec['job']}/executions/"
    if not execution["name"].startswith(prefix):
        raise ValueError("execution belongs to another job")
    name = execution["name"][len(prefix):]
    if not name or "/" in name:
        raise ValueError("invalid execution name")
    return {
        "name": name, "job": spec["job"], "image": spec["image"],
        "source_revision": spec["source_revision"], "task_index": 0, "task_attempt": 0,
    }


def storage_client(config):
    from google.cloud import storage
    return storage.Client(project=config["project"])


def pinned_blob(client, uri, *, limit):
    bucket, name = object_path(uri)
    blob = client.bucket(bucket).blob(name)
    blob.reload(timeout=30)
    if blob.size is None or blob.size > limit:
        raise ValueError("artifact exceeds the bounded download size")
    generation = int(blob.generation)
    return client.bucket(bucket).blob(name, generation=generation), generation


def download(blob, generation):
    return blob.download_as_bytes(if_generation_match=generation, checksum="auto", timeout=30)


def verify_export(config, execution, *, client=None):
    client = storage_client(config) if client is None else client
    identity = execution_identity(config, "report", execution)
    stem = f"{config['report']['output_prefix']}/{identity['name']}/task-0-attempt-0"
    report_uri, export_uri = stem + ".json", stem + ".ndjson"
    report_blob, report_generation = pinned_blob(client, report_uri, limit=1024 * 1024)
    _, export_generation = pinned_blob(client, export_uri, limit=1024 * 1024)
    envelope = json.loads(download(report_blob, report_generation))
    if envelope["execution"] != identity:
        raise ValueError("report execution/image/source identity mismatch")
    for kind in ("race", "weather"):
        if envelope["storage"]["inputs"][kind]["uri"] != config["report"][f"{kind}_uri"]:
            raise ValueError("report source URI mismatch")
    refs = {
        "report_uri": report_uri, "report_generation": report_generation,
        "result_export_uri": export_uri, "result_export_generation": export_generation,
        "expected_sha256": config["export_sha256"],
        "table_id": config["table_id"], "location": config["region"],
    }
    stored = prepare_stored_load(client, **refs)
    first = stored.prepared.rows[0]
    if any(first[f"{kind}_sha256"] != config["report"][f"{kind}_sha256"]
           for kind in ("race", "weather")):
        raise ValueError("export source hashes disagree with configured inputs")
    LOG.info("Validated snapshot %s", json.dumps(stored.summary(), sort_keys=True))
    return refs


def load_snapshot(config, refs, *, storage=None, warehouse=None):
    storage = storage_client(config) if storage is None else storage
    if (refs["table_id"] != config["table_id"] or refs["location"] != config["region"]
            or refs["expected_sha256"] != config["export_sha256"]):
        raise ValueError("load references disagree with validated configuration")
    # Revalidate exact bytes in this worker; never pass result rows through XCom.
    stored = prepare_stored_load(storage, **refs)
    if warehouse is None:
        from google.cloud import bigquery
        warehouse = bigquery.Client(project=config["project"], location=config["region"])
    result = load_prepared(warehouse, stored.prepared)
    LOG.info("Snapshot load/verification: %s", json.dumps(result, sort_keys=True))
    return {**refs, **result}


def verify_dbt_evidence(config, execution, *, client=None):
    client = storage_client(config) if client is None else client
    identity = execution_identity(config, "dbt", execution)
    spec = config["dbt"]
    stem = f"{spec['output_prefix']}/{identity['name']}/task-0-attempt-0"
    manifest_uri, archive_uri = stem + ".json", stem + ".zip"
    blob, generation = pinned_blob(client, manifest_uri, limit=1024 * 1024)
    manifest = json.loads(download(blob, generation))
    expected_hash = sha256(stage_runner.canonical_json(spec["expectations"]).encode()).hexdigest()
    if (manifest["cloud_stage_schema_version"] != 1 or manifest["execution"] != identity
            or manifest["status"] != "reconciled" or manifest["runner_status"] != "reconciled"
            or manifest["analytical_reconciliation"] != "passed"
            or manifest["config_sha256"] != sha256(stage_runner.canonical_json(spec["config"]).encode()).hexdigest()
            or manifest["expectations_sha256"] != expected_hash
            or manifest["storage"]["manifest_uri"] != manifest_uri
            or manifest["storage"]["archive_uri"] != archive_uri):
        raise ValueError("dbt evidence does not match this successful execution/configuration")
    blob, archive_generation = pinned_blob(client, archive_uri, limit=10 * 1024 * 1024)
    payload = download(blob, archive_generation)
    if (len(payload) != manifest["storage"]["archive_bytes"]
            or sha256(payload).hexdigest() != manifest["storage"]["archive_sha256"]):
        raise ValueError("dbt evidence archive hash/size mismatch")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
        if (len(names) != len(set(names)) or len(names) != manifest["storage"]["file_count"]
                or any(PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names)
                or sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024):
            raise ValueError("invalid dbt evidence archive members")
        if archive.testzip() is not None:
            raise ValueError("corrupt dbt evidence archive")
        record = json.loads(archive.read("execution/execution.json"))
        cloud_record = json.loads(archive.read("cloud-execution.json"))
        expected_cloud = {**manifest, "storage": {
            "archive_uri": archive_uri, "manifest_uri": manifest_uri}}
        if cloud_record != expected_cloud:
            raise ValueError("archived cloud record disagrees with manifest")
        expected = json.loads(archive.read("execution/expectations.json"))
        reconciliation = json.loads(archive.read("execution/reconciliation/reconciliation.json"))
        if (record["status"] != "reconciled" or record["analytical_reconciliation"] != "passed"
                or record["config"] != spec["config"]
                or record["expectations_sha256"] != expected_hash
                or [(s["stage"], s["status"]) for s in record["stages"]]
                != [("edition", "passed"), ("comparison", "passed")]
                or reconciliation["status"] != "reconciled"):
            raise ValueError("archived runner/reconciliation did not pass")
        stage_runner.assert_same(expected, spec["expectations"])
        plans = stage_runner.build_reconciliation_plan(spec["config"], spec["expectations"])
        queries = reconciliation["queries"]
        if (reconciliation["expectations_sha256"] != expected_hash
                or len(queries) != len(plans)):
            raise ValueError("reconciliation evidence is incomplete")
        for query, plan in zip(queries, plans, strict=True):
            if (query["stage"] != plan["stage"] or query["status"] != "passed"
                    or not query["job_id"] or query["errors"]
                    or query["sql_sha256"] != sha256(plan["sql"].encode()).hexdigest()):
                raise ValueError("reconciliation query evidence did not pass")
            stage_runner.assert_same(query["actual_rows"], plan["expected"])
    result = {"status": "verified", "execution": execution["name"],
              "manifest_uri": manifest_uri, "manifest_generation": generation,
              "archive_uri": archive_uri, "archive_generation": archive_generation,
              "archive_sha256": manifest["storage"]["archive_sha256"]}
    LOG.info("Verified dbt evidence: %s", json.dumps(result, sort_keys=True))
    return result
