"""Prepare one generation-pinned Cloud Run artifact pair for BigQuery loading."""

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from runwx.adapters.bigquery.result_load import PreparedLoad, prepare_load
from runwx.adapters.gcs.report_io import object_path


def _generation(value: int | str, *, name: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError(f"{name} must be a positive Cloud Storage generation")
    return int(value)


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON field in cloud report")
    return result


def _download_generation(client, uri: str, generation: int) -> bytes:
    bucket, name = object_path(uri)
    blob = client.bucket(bucket).blob(name, generation=generation)
    return blob.download_as_bytes(
        if_generation_match=generation,
        checksum="auto",
        timeout=30,
    )


@dataclass(frozen=True)
class StoredPreparedLoad:
    """A fully reconciled local load plus its immutable Storage references."""

    prepared: PreparedLoad
    report_uri: str
    report_generation: int
    result_export_uri: str
    result_export_generation: int
    execution: dict

    def summary(self) -> dict:
        return {
            **self.prepared.summary(),
            "report_uri": self.report_uri,
            "report_generation": str(self.report_generation),
            "result_export_uri": self.result_export_uri,
            "result_export_generation": str(self.result_export_generation),
            "source_execution": self.execution,
        }


def prepare_stored_load(
    client,
    *,
    report_uri: str,
    report_generation: int | str,
    result_export_uri: str,
    result_export_generation: int | str,
    expected_sha256: str,
    table_id: str,
    location: str = "europe-west1",
) -> StoredPreparedLoad:
    """Download and reconcile an exact completed pair without contacting BigQuery."""
    report_generation = _generation(report_generation, name="report_generation")
    result_export_generation = _generation(
        result_export_generation, name="result_export_generation"
    )
    object_path(report_uri)
    object_path(result_export_uri)
    if report_uri == result_export_uri:
        raise ValueError("report and result export must be different objects")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected a lowercase result-export SHA-256")

    report_bytes = _download_generation(client, report_uri, report_generation)
    try:
        envelope = json.loads(report_bytes.decode("utf-8"), object_pairs_hook=_unique_object)
        storage = envelope["storage"]
        outputs = storage["outputs"]
        export_metadata = outputs["result_export"]
        report = envelope["report"]
        execution = envelope["execution"]
        if (
            envelope["cloud_report_schema_version"] != 2
            or report["report_schema_version"] != 1
            or storage["output_uri"] != report_uri
            or outputs["report"]["uri"] != report_uri
            or export_metadata["uri"] != result_export_uri
            or export_metadata["sha256"] != expected_sha256
            or export_metadata["schema_version"] != 1
        ):
            raise ValueError("cloud report does not identify the requested artifact pair")
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Cloud Run report envelope") from error

    payload = _download_generation(client, result_export_uri, result_export_generation)
    prepared = prepare_load(
        payload,
        table_id=table_id,
        expected_sha256=expected_sha256,
        location=location,
    )
    summary = prepared.summary()
    rows = prepared.rows
    first = rows[0]
    common_settings = (
        "course_id_input",
        "timezone_name",
        "max_gap_seconds",
        "alignment",
        "tie_break",
        "duration_precision",
    )
    try:
        quality = report["result_quality"]
        coverage = report["weather_coverage"]
        reconciles = (
            export_metadata["bytes"] == len(payload)
            and export_metadata["row_count"] == len(rows)
            and quality["candidate_count"] == len(rows)
            and quality["accepted_count"] == summary["accepted_count"]
            and quality["skipped_count"] == summary["skipped_count"]
            and quality["invalid_count"] == summary["invalid_count"]
            and coverage["accepted_result_count"] == summary["accepted_count"]
            and coverage["matched_count"] == summary["matched_count"]
            and coverage["unmatched_count"]
            == sum(row["weather_match_status"] == "unmatched" for row in rows)
            and report["race"]["event_id"] == first["event_id"]
            and report["race"]["course_id"] == first["course_id"]
            and report["race"]["distance_m"] == first["distance_m"]
            and report["race"]["started_at_utc"] == first["started_at_utc"]
            and report["sources"]["race"]["provider"] == first["source"]
            and report["sources"]["race"]["source_event_id"] == first["source_event_id"]
            and report["sources"]["race"]["sha256"] == first["race_sha256"]
            and report["sources"]["weather"]["sha256"] == first["weather_sha256"]
            and all(report["settings"][key] == first["settings"][key] for key in common_settings)
        )
    except (KeyError, TypeError) as error:
        raise ValueError("cloud report is missing reconciliation fields") from error
    if not reconciles or sha256(payload).hexdigest() != export_metadata["sha256"]:
        raise ValueError("cloud report and result export do not reconcile")

    return StoredPreparedLoad(
        prepared=prepared,
        report_uri=report_uri,
        report_generation=report_generation,
        result_export_uri=result_export_uri,
        result_export_generation=result_export_generation,
        execution=execution,
    )
