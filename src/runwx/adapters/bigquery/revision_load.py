"""Load one synthetic revision candidate through a controlled, serialized path.

Each table load is atomic; the pair is resumable, not a transaction. Loading does
not create a validation receipt or select a revision for analytical output.
"""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from uuid import uuid4

from runwx.adapters.bigquery.result_load import SCHEMA, MAXIMUM_BYTES_BILLED, _normalise_fields
from runwx.domain.revisions import RevisionIdentity, canonical_json
from runwx.services.revision_export import build_revision_candidate
from runwx.services.revisions import _analytical_json


SCHEMAS = {
    "revision_result_rows": [{"name": "revision_id", "type": "STRING", "mode": "REQUIRED"}, *SCHEMA],
    "analysis_revisions": [
        {"name": name, "type": kind, "mode": "REQUIRED"}
        for kind, names in (
            ("STRING", ("revision_id", "event_id", "race_sha256", "weather_source_id",
                        "weather_sha256", "code_sha256", "settings_json", "race_kind",
                        "snapshot_scope", "result_rows_sha256", "report_json")),
            ("INTEGER", ("candidate_count", "accepted_count", "skipped_count",
                         "invalid_count", "weather_matched_count")),
        ) for name in names
    ],
}
LOCATION = "europe-west1"


def _normalise(row, table):
    row = _normalise_fields(row, SCHEMAS[table])
    if table == "analysis_revisions":
        row["settings_json"] = canonical_json(json.loads(row["settings_json"]))
        row["report_json"] = _analytical_json(json.loads(row["report_json"]))
    return row


@dataclass(frozen=True)
class PreparedRevisionLoad:
    dataset: str
    metadata_json: str
    rows_json: str

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]\.[A-Za-z_][A-Za-z0-9_]*", self.dataset):
            raise ValueError("expected project.dataset using simple identifiers")

    def records(self, table):
        return (json.loads(self.rows_json) if table == "revision_result_rows"
                else [json.loads(self.metadata_json)])

    def job_id(self, table):
        # Input paths are provenance only: moving the same source must recover
        # the same pending job, including when its response was lost.
        identity = {"table": f"{self.dataset}.{table}", "location": LOCATION,
                    "schema": SCHEMAS[table],
                    "rows": [_normalise(row, table) for row in self.records(table)]}
        return "runwx_candidate_load_" + sha256(canonical_json(identity).encode()).hexdigest()

    def summary(self):
        metadata = json.loads(self.metadata_json)
        return {"dataset": self.dataset, "location": LOCATION,
                **{key: metadata[key] for key in (
                    "revision_id", "event_id", "candidate_count", "accepted_count",
                    "skipped_count", "invalid_count", "weather_matched_count")},
                "planned_load_job_ids": {table: self.job_id(table) for table in SCHEMAS}}


def prepare_revision_load(
    revision: RevisionIdentity, race_html: Path, weather_csv: Path, *, dataset: str,
) -> PreparedRevisionLoad:
    """Build the candidate without credentials, uploads or a success receipt."""
    metadata, rows = build_revision_candidate(revision, race_html, weather_csv)
    return PreparedRevisionLoad(dataset, canonical_json(metadata), canonical_json(rows))


class CandidateLoadUnknown(RuntimeError):
    """Submission may have succeeded; retain its identity for inspection/recovery."""

    def __init__(self, table_id, job_id):
        self.table_id, self.job_id = table_id, job_id
        super().__init__(f"candidate load unconfirmed for {table_id}; inspect job {job_id}; no automatic retry")


def load_revision_candidate(client, prepared: PreparedRevisionLoad) -> dict:
    """Verify both existing slices before any append; recover missing slices only.

    Requires immutable candidates and one serialized writer. Conflicting/partial
    slices fail closed. No deletion, overwrite, receipt creation or selection.
    """
    from google.api_core.exceptions import Conflict
    from google.cloud import bigquery

    project = prepared.dataset.split(".")[0]
    if client.project != project:
        raise ValueError("client project must match the destination project")
    schemas = {name: [bigquery.SchemaField.from_api_repr(field) for field in fields]
               for name, fields in SCHEMAS.items()}
    expected = {name: [_normalise(row, name) for row in prepared.records(name)] for name in SCHEMAS}
    revision_id = json.loads(prepared.metadata_json)["revision_id"]
    for name in SCHEMAS:
        table = client.get_table(f"{prepared.dataset}.{name}", retry=None, timeout=30)
        if table.location != LOCATION or table.table_type != "TABLE" or table.schema != schemas[name]:
            raise ValueError("destination location, type or schema differs from the prepared candidate")

    verification_jobs, load_job_ids = [], {}

    def read_rows(name):
        row_limit = len(expected[name]) + 1
        ordering = "source_row_number, TO_JSON_STRING(t)" if name == "revision_result_rows" else "TO_JSON_STRING(t)"
        sql = (f"SELECT TO_JSON_STRING(t) AS row_json FROM `{prepared.dataset}.{name}` AS t "
               f"WHERE revision_id = @revision_id ORDER BY {ordering} LIMIT @row_limit")
        config = bigquery.QueryJobConfig(
            use_legacy_sql=False, use_query_cache=False, maximum_bytes_billed=MAXIMUM_BYTES_BILLED,
            create_session=False, connection_properties=[], job_timeout_ms=300000, query_parameters=[
                bigquery.ScalarQueryParameter("revision_id", "STRING", revision_id),
                bigquery.ScalarQueryParameter("row_limit", "INT64", row_limit),
            ],
        )
        job = client.query(sql, location=LOCATION, job_id=f"runwx_candidate_read_{uuid4().hex}",
                           job_config=config, retry=None, job_retry=None, timeout=30)
        records = [_normalise(json.loads(row["row_json"]), name) for row in
                   job.result(timeout=300, retry=None, job_retry=None, max_results=row_limit)]
        verification_jobs.append({"job_id": job.job_id, "bytes_processed": job.total_bytes_processed,
                                  "bytes_billed": job.total_bytes_billed})
        return records

    def check(name, records):
        if records != expected[name]:
            raise ValueError(f"stored candidate in {name} differs from the local baseline; nothing overwritten")

    existing = {name: read_rows(name) for name in SCHEMAS}
    for name, records in existing.items():
        if records:
            check(name, records)

    # Rows first; metadata last. Neither is visible through selection without an
    # independently validated receipt and explicit guarded publication later.
    for name in SCHEMAS:
        if existing[name]:
            continue
        table_id, job_id = f"{prepared.dataset}.{name}", prepared.job_id(name)
        payload = "".join(canonical_json(row) + "\n" for row in prepared.records(name)).encode()
        config = bigquery.LoadJobConfig(
            schema=schemas[name], source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            autodetect=False, create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            max_bad_records=0, ignore_unknown_values=False, job_timeout_ms=300000,
        )
        try:
            try:
                job = client.load_table_from_file(
                    BytesIO(payload), table_id, size=len(payload), location=LOCATION,
                    job_id=job_id, job_config=config, num_retries=0, timeout=30,
                )
            except Conflict:
                job = client.get_job(job_id, project=project, location=LOCATION, retry=None, timeout=30)
            if (not isinstance(job, bigquery.LoadJob) or job.job_id != job_id
                    or job.project != project or job.location != LOCATION
                    or job.destination != bigquery.TableReference.from_string(table_id)
                    or any(getattr(job, key) != getattr(config, key) for key in (
                        "schema", "source_format", "create_disposition", "write_disposition"))):
                raise ValueError("existing load job differs from prepared candidate destination/configuration")
            job.result(timeout=300, retry=None)
        except Exception as error:
            raise CandidateLoadUnknown(table_id, job_id) from error
        load_job_ids[name] = job_id
        check(name, read_rows(name))

    return {**prepared.summary(),
            "status": "candidate_loaded_verified" if load_job_ids else "candidate_already_present_verified",
            "load_job_ids": load_job_ids, "verification_jobs": verification_jobs}
