"""Validate one synthetic export and load it into an empty staging table."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib.resources import files
from io import BytesIO
import json
import math
import re


MAXIMUM_BYTES_BILLED = 100 * 1024 * 1024
SCHEMA_BYTES = files(__package__).joinpath("result_rows.schema.json").read_bytes()
SCHEMA = json.loads(SCHEMA_BYTES)


def _normalise_fields(row, schema=SCHEMA):
    """Check the export's field types and normalise equivalent UTC timestamps.

    This supports only the scalar/record types used by this one staging schema.
    BigQuery's own load validation remains necessary; this is not a SQL emulator.
    """
    if not isinstance(row, dict) or set(row) != {field["name"] for field in schema}:
        raise ValueError("row fields do not match the staging schema")
    result = {}
    for field in schema:
        name, kind = field["name"], field["type"]
        value = row[name]
        if value is None:
            if field["mode"] == "REQUIRED":
                raise ValueError(f"{name} is required")
        elif kind == "RECORD":
            value = _normalise_fields(value, field["fields"])
        elif kind == "TIMESTAMP":
            if not isinstance(value, str):
                raise ValueError(f"{name} must be an ISO timestamp")
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                raise ValueError(f"{name} must include a timezone")
            value = timestamp.astimezone(timezone.utc).isoformat()
        elif kind == "STRING" and not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        elif kind == "INTEGER" and (type(value) is not int or abs(value) >= 2**53):
            raise ValueError(f"{name} must be a JSON-safe integer")
        elif kind == "FLOAT" and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f"{name} must be a finite number")
        result[name] = value
    return result


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON field")
    return result


@dataclass(frozen=True)
class PreparedLoad:
    payload: bytes
    rows: list[dict]
    table_id: str
    location: str

    def summary(self):
        outcomes = Counter(row["validation_status"] for row in self.rows)
        return {
            "table_id": self.table_id,
            "location": self.location,
            "export_sha256": sha256(self.payload).hexdigest(),
            "schema_sha256": sha256(SCHEMA_BYTES).hexdigest(),
            "input_bytes": len(self.payload),
            "candidate_count": len(self.rows),
            **{f"{status}_count": outcomes[status] for status in ("accepted", "skipped", "invalid")},
            "matched_count": sum(row["weather_match_status"] == "matched" for row in self.rows),
            "race_sha256": self.rows[0]["race_sha256"],
            "weather_sha256": self.rows[0]["weather_sha256"],
            "race_kind": "synthetic", "weather_kind": "synthetic",
        }

    @property
    def job_id(self):
        identity = f"{self.table_id}:{self.location}:{sha256(self.payload).hexdigest()}:{sha256(SCHEMA_BYTES).hexdigest()}"
        return f"runwx_load_{sha256(identity.encode()).hexdigest()}"


def prepare_load(payload: bytes, *, table_id: str, expected_sha256: str,
                 location: str = "europe-west1") -> PreparedLoad:
    """Prepare without credentials or network access; bind loading to exact bytes."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", table_id):
        raise ValueError("expected project.dataset.table using simple identifiers")
    if location != "europe-west1":
        raise ValueError("this first staging load uses europe-west1")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("export SHA-256 mismatch")
    if not payload or len(payload) > 1024 * 1024:
        raise ValueError("expected a nonempty export of at most 1 MiB")
    rows = [_normalise_fields(json.loads(line, object_pairs_hook=_unique_object))
            for line in payload.decode("utf-8").splitlines()]
    common = ("event_id", "source", "source_event_id", "course_id", "started_at_utc",
              "distance_m", "race_sha256", "weather_sha256", "settings")
    for number, row in enumerate(rows, 1):
        if row["export_schema_version"] != 1 or row["race_kind"] != "synthetic" or row["weather_kind"] != "synthetic":
            raise ValueError("first staging load requires version 1 and explicitly synthetic inputs")
        if any(row[key] != rows[0][key] for key in common):
            raise ValueError("one export must contain one snapshot and settings")
        if any(not re.fullmatch(r"[0-9a-f]{64}", row[key]) for key in ("race_sha256", "weather_sha256")):
            raise ValueError("invalid source hash")
        expected_id = f"{row['event_id']}:{row['race_sha256']}:{number}"
        if row["source_row_number"] != number or row["source_row_id"] != expected_id:
            raise ValueError("source row identities must be distinct and in candidate order")
        if row["distance_m"] <= 0 or row["settings"]["max_gap_seconds"] < 0:
            raise ValueError("invalid distance or weather gap")
        status, match = row["validation_status"], row["weather_match_status"]
        if status == "accepted":
            if not row["duration_s"] or row["duration_s"] < 0 or not row["place"] or row["place"] < 0 or row["validation_reason"] is not None:
                raise ValueError("accepted rows require positive duration/place and no rejection reason")
            if match not in {"matched", "unmatched"} or (row["weather"] is not None) != (match == "matched"):
                raise ValueError("accepted weather outcome does not reconcile")
            if (match == "matched" and row["weather_match_reason"] is not None) or (match == "unmatched" and not row["weather_match_reason"]):
                raise ValueError("weather match reason does not reconcile")
        elif status in {"skipped", "invalid"}:
            if not row["validation_reason"] or row["duration_s"] is not None or row["place"] is not None:
                raise ValueError("rejected rows require a reason and no validated result")
            if match != "not_applicable" or row["weather"] is not None or row["weather_match_reason"] is not None:
                raise ValueError("weather must be inapplicable for rejected rows")
        else:
            raise ValueError("unknown validation outcome")
    return PreparedLoad(payload, rows, table_id, location)


def load_prepared(client, prepared: PreparedLoad) -> dict:
    """Write only to an empty, pre-created table; verify equal rows on each rerun.

    Intended for one controlled, sequential submission path. Failed or uncertain
    jobs do not trigger truncation, deletion or automatic new load attempts.
    """
    from google.api_core.exceptions import Conflict
    from google.cloud import bigquery

    project = prepared.table_id.split(".")[0]
    if client.project != project:
        raise ValueError("client project must match destination project")
    table = client.get_table(prepared.table_id, retry=None, timeout=30)
    expected_schema = [bigquery.SchemaField.from_api_repr(field) for field in SCHEMA]
    if table.location != prepared.location or table.table_type != "TABLE" or table.schema != expected_schema:
        raise ValueError("destination location, type or schema differs from the prepared load")

    verification_jobs = []

    def read_rows():
        query = f"SELECT TO_JSON_STRING(t) AS row_json FROM `{prepared.table_id}` AS t ORDER BY source_row_number LIMIT @row_limit"
        config = bigquery.QueryJobConfig(
            use_legacy_sql=False, use_query_cache=False,
            maximum_bytes_billed=MAXIMUM_BYTES_BILLED,
            query_parameters=[bigquery.ScalarQueryParameter("row_limit", "INT64", len(prepared.rows) + 1)],
        )
        job = client.query(query, location=prepared.location, job_config=config,
                           retry=None, job_retry=None, timeout=30)
        rows = [_normalise_fields(json.loads(row["row_json"])) for row in
                job.result(timeout=300, retry=None, job_retry=None, max_results=len(prepared.rows) + 1)]
        verification_jobs.append({
            "job_id": job.job_id, "bytes_processed": job.total_bytes_processed,
            "bytes_billed": job.total_bytes_billed,
        })
        return rows

    existing = read_rows()
    load_job_id = None
    if existing:
        actual = existing
        status = "already_present_verified"
    else:
        config = bigquery.LoadJobConfig(
            schema=expected_schema, source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            autodetect=False, create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
            write_disposition=bigquery.WriteDisposition.WRITE_EMPTY,
            max_bad_records=0, ignore_unknown_values=False,
        )
        try:
            job = client.load_table_from_file(
                BytesIO(prepared.payload), prepared.table_id, size=len(prepared.payload),
                location=prepared.location, job_id=prepared.job_id, job_config=config,
                num_retries=0, timeout=30,
            )
        except Conflict:
            job = client.get_job(prepared.job_id, project=project, location=prepared.location,
                                 retry=None, timeout=30)
        job.result(timeout=300, retry=None)
        load_job_id = job.job_id
        actual = read_rows()
        status = "loaded_verified"
    if actual != prepared.rows:
        raise ValueError("stored rows differ from the local export; nothing overwritten or published")
    return {**prepared.summary(), "status": status, "load_job_id": load_job_id,
            "verification_jobs": verification_jobs}
