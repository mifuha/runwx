"""Cloud Run boundary for the existing dbt stage runner and evidence upload."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import zipfile

import stage_runner


def storage_location(uri):
    parts = urlsplit(uri)
    if (parts.scheme != "gs" or not parts.netloc or not parts.path.strip("/")
            or parts.query or parts.fragment or parts.username or parts.port):
        raise ValueError("expected gs://bucket/prefix without query or generation suffix")
    return parts.netloc, parts.path.strip("/")


def validate_execution(execution):
    required = {
        "job", "name", "task_index", "task_attempt", "image", "source_revision",
    }
    if not isinstance(execution, dict) or set(execution) != required:
        raise ValueError("execution metadata has an unexpected shape")
    for key in ("job", "name"):
        if not isinstance(execution[key], str) or not re.fullmatch(r"[a-z0-9-]+", execution[key]):
            raise ValueError(f"invalid Cloud Run {key}")
    for key in ("task_index", "task_attempt"):
        if type(execution[key]) is not int or execution[key] < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    if not isinstance(execution["image"], str) or not re.fullmatch(
            r".+@sha256:[0-9a-f]{64}", execution["image"]):
        raise ValueError("image must be an immutable registry digest reference")
    if not isinstance(execution["source_revision"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", execution["source_revision"]):
        raise ValueError("source_revision must be a full lowercase Git commit")
    return execution


def encode_archive(root):
    payload = BytesIO()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root).as_posix())
    return payload.getvalue(), len(files)


def run_cloud_stage(
    client, *, config, expectations, output_prefix, execution,
    project_dir=Path(__file__).resolve().parent, runner=None,
):
    """Run the local stage contract, then publish one create-only evidence pair."""
    stage_runner.validate_config(config)
    stage_runner.validate_expectations(expectations, config)
    validate_execution(execution)
    runner = stage_runner.execute if runner is None else runner
    bucket_name, prefix = storage_location(output_prefix)
    stem = (
        f"{prefix}/{execution['name']}/"
        f"task-{execution['task_index']}-attempt-{execution['task_attempt']}"
    )
    archive_name = f"{stem}.zip"
    manifest_name = f"{stem}.json"
    archive_uri = f"gs://{bucket_name}/{archive_name}"
    manifest_uri = f"gs://{bucket_name}/{manifest_name}"
    config_text = stage_runner.canonical_json(config)
    expectations_text = stage_runner.canonical_json(expectations)
    error = None

    with TemporaryDirectory(prefix="runwx-dbt-") as directory:
        root = Path(directory)
        output_dir = root / "execution"
        try:
            record = runner(config, expectations, output_dir, project_dir)
            status = "reconciled"
        except Exception as exc:
            status = "failed"
            error = exc
            record_path = output_dir / "execution.json"
            try:
                record = json.loads(record_path.read_text()) if record_path.exists() else None
            except (OSError, json.JSONDecodeError):
                record = None

        cloud_record = {
            "cloud_stage_schema_version": 1,
            "status": status,
            "execution": execution,
            "config_sha256": sha256(config_text.encode()).hexdigest(),
            "expectations_sha256": sha256(expectations_text.encode()).hexdigest(),
            "runner_status": record.get("status") if record else "failed",
            "analytical_reconciliation": (
                record.get("analytical_reconciliation") if record else "not_performed"
            ),
            "storage": {
                "archive_uri": archive_uri,
                "manifest_uri": manifest_uri,
            },
        }
        if error is not None:
            cloud_record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        (root / "cloud-execution.json").write_text(
            json.dumps(cloud_record, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
        archive, file_count = encode_archive(root)
        archive_hash = sha256(archive).hexdigest()
        manifest = {
            **cloud_record,
            "storage": {
                **cloud_record["storage"],
                "archive_sha256": archive_hash,
                "archive_bytes": len(archive),
                "file_count": file_count,
            },
        }
        encoded_manifest = json.dumps(
            manifest, indent=2, sort_keys=True, allow_nan=False
        ) + "\n"
        bucket = client.bucket(bucket_name)
        bucket.blob(archive_name).upload_from_string(
            archive,
            content_type="application/zip",
            if_generation_match=0,
            timeout=60,
        )
        bucket.blob(manifest_name).upload_from_string(
            encoded_manifest,
            content_type="application/json",
            if_generation_match=0,
            timeout=30,
        )

    if error is not None:
        raise error
    return manifest


def main(*, client=None):
    config = json.loads(os.environ["RUNWX_DBT_CONFIG"])
    expectations = json.loads(os.environ["RUNWX_DBT_EXPECTATIONS"])
    execution = {
        "job": os.environ["CLOUD_RUN_JOB"],
        "name": os.environ["CLOUD_RUN_EXECUTION"],
        "task_index": int(os.environ["CLOUD_RUN_TASK_INDEX"]),
        "task_attempt": int(os.environ["CLOUD_RUN_TASK_ATTEMPT"]),
        "image": os.environ["RUNWX_IMAGE"],
        "source_revision": os.environ["RUNWX_SOURCE_REVISION"],
    }
    stage_runner.validate_config(config)
    stage_runner.validate_expectations(expectations, config)
    validate_execution(execution)
    storage_location(os.environ["RUNWX_DBT_OUTPUT_PREFIX"])
    if client is None:
        from google.cloud import storage

        client = storage.Client(project=config["project"])
    result = run_cloud_stage(
        client,
        config=config,
        expectations=expectations,
        output_prefix=os.environ["RUNWX_DBT_OUTPUT_PREFIX"],
        execution=execution,
    )
    print(json.dumps(result, sort_keys=True))
    return result


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    main()


if __name__ == "__main__":
    cli()
