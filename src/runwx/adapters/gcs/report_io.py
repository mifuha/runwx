"""Download two known objects and create one reconciled artifact pair."""

from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from runwx.services.snapshot_artifacts import build_snapshot_artifacts


def _object_path(uri: str) -> tuple[str, str]:
    parts = urlsplit(uri)
    if (parts.scheme != "gs" or not parts.netloc or not parts.path.strip("/")
            or parts.query or parts.fragment or parts.username or parts.port):
        raise ValueError("expected gs://bucket/object without query or generation suffix")
    return parts.netloc, parts.path.lstrip("/")


def run_stored_report(
    client, *, race_uri: str, race_sha256: str,
    weather_uri: str, weather_sha256: str, output_prefix: str,
    execution: dict, settings: dict,
) -> dict:
    """Publish only after both approved hashes and both artifacts are valid.

    The caller supplies a Storage client so local tests need neither credentials
    nor a server. Object generations prevent a change between metadata lookup and
    download; SHA-256 checks bind the bytes to the approved local baseline.
    """
    inputs = {"race": (race_uri, race_sha256), "weather": (weather_uri, weather_sha256)}
    for uri, expected_hash in inputs.values():
        _object_path(uri)
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError("expected a lowercase SHA-256 input hash")
    output_bucket, prefix = _object_path(output_prefix)
    if not re.fullmatch(r"[a-z0-9-]+", execution["name"]):
        raise ValueError("invalid Cloud Run execution name")
    if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", execution["image"]):
        raise ValueError("image must be an immutable registry digest reference")
    if not re.fullmatch(r"[0-9a-f]{40}", execution["source_revision"]):
        raise ValueError("source_revision must be a full lowercase Git commit")
    for key in ("task_index", "task_attempt"):
        if not isinstance(execution[key], int) or execution[key] < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    object_stem = (
        f"{prefix.rstrip('/')}/{execution['name']}/"
        f"task-{execution['task_index']}-attempt-{execution['task_attempt']}"
    )
    report_name = f"{object_stem}.json"
    result_name = f"{object_stem}.ndjson"
    report_uri = f"gs://{output_bucket}/{report_name}"
    result_uri = f"gs://{output_bucket}/{result_name}"

    with TemporaryDirectory(prefix="runwx-") as directory:
        paths = {}
        provenance = {}
        for kind, (uri, expected_hash) in inputs.items():
            bucket, name = _object_path(uri)
            blob = client.bucket(bucket).blob(name)
            blob.reload(timeout=30)
            generation = blob.generation
            data = blob.download_as_bytes(
                if_generation_match=generation, checksum="auto", timeout=30,
            )
            if sha256(data).hexdigest() != expected_hash:
                raise ValueError(f"{kind} SHA-256 mismatch; no artifacts uploaded")
            paths[kind] = Path(directory) / kind
            paths[kind].write_bytes(data)
            provenance[kind] = {"uri": uri, "generation": str(generation)}

        artifacts = build_snapshot_artifacts(paths["race"], paths["weather"], **settings)
        report = artifacts.report
        # Temporary paths disappear at exit. Keep the retrievable source location.
        for kind, (uri, _) in inputs.items():
            report["sources"][kind]["file"] = uri
        payload = {
            "cloud_report_schema_version": 2,
            "report": report,
            "execution": execution,
            "storage": {
                "inputs": provenance,
                # Retain output_uri for consumers of the version 1 envelope.
                "output_uri": report_uri,
                "outputs": {
                    "report": {"uri": report_uri},
                    "result_export": {
                        "uri": result_uri,
                        "sha256": artifacts.result_sha256,
                        "bytes": len(artifacts.result_payload),
                        "row_count": len(artifacts.result_rows),
                        "schema_version": 1,
                    },
                },
            },
        }
        encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
        # Publish the data first and the report envelope last. The report is the
        # completeness marker; downstream work must require both named objects.
        client.bucket(output_bucket).blob(result_name).upload_from_string(
            artifacts.result_payload,
            content_type="application/x-ndjson",
            if_generation_match=0,
            timeout=30,
        )
        client.bucket(output_bucket).blob(report_name).upload_from_string(
            encoded, content_type="application/json", if_generation_match=0, timeout=30,
        )
    return {
        "output_uri": report_uri,
        "report_uri": report_uri,
        "result_export_uri": result_uri,
        "result_export_sha256": artifacts.result_sha256,
        "result_export_rows": len(artifacts.result_rows),
    }
