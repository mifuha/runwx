"""Explicit, guarded event selection over the existing four warehouse tables.

One controlled, serialized publisher; no loading, dbt execution or automatic retry.
Native transaction behaviour still needs a separately authorised BigQuery check.
"""

from dataclasses import asdict, dataclass
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid4

from runwx.adapters.bigquery.result_load import MAXIMUM_BYTES_BILLED, _normalise_fields
from runwx.domain.revisions import RevisionIdentity, Selection, canonical_json
from runwx.services.offline_report import build_offline_report
from runwx.services.revision_export import build_revision_rows
from runwx.services.revisions import _analytical_json, _check_report


@dataclass(frozen=True)
class PreparedSelection:
    dataset: str
    selection: Selection
    expected: Selection | None
    metadata_json: str
    rows_json: str
    receipt_json: str

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]\.[A-Za-z_][A-Za-z0-9_]*", self.dataset):
            raise ValueError("expected project.dataset using simple identifiers")
        for pointer in (self.selection, self.expected):
            if pointer is None:
                continue
            if pointer.event_id != self.selection.event_id:
                raise ValueError("expected selection must belong to the same event")
            if (not pointer.event_id.strip() or not pointer.successful_attempt_id.strip()
                    or not re.fullmatch(r"[0-9a-f]{64}", pointer.revision_id)):
                raise ValueError("selection needs an event, revision hash and attempt")


def prepare_selection(
    revision: RevisionIdentity, race_html: Path, weather_csv: Path, *,
    dataset: str, successful_attempt_id: str, validation_code_sha256: str,
    validation_invocation_id: str, expected: Selection | None,
) -> PreparedSelection:
    """Rebuild the local baseline without credentials; require an exact receipt.

    The identifiers name a receipt that must ALREADY exist after warehouse
    validation. This function neither performs that validation nor creates it.
    `expected=None` means the event must have no current selection.
    """
    if (not re.fullmatch(r"[0-9a-f]{64}", validation_code_sha256)
            or not validation_invocation_id.strip()):
        raise ValueError("warehouse validation hash and invocation are required")
    if revision.race_kind != "synthetic" or revision.settings["weather_kind"] != "synthetic":
        raise ValueError("this bounded publisher requires explicitly synthetic inputs")
    rows = build_revision_rows(revision, race_html, weather_csv)
    settings = revision.settings
    settings["max_gap"] = timedelta(seconds=settings.pop("max_gap_seconds"))
    report = build_offline_report(race_html, weather_csv, **settings)
    _check_report(revision, report)
    rows_json = canonical_json(rows)
    metadata = {
        **asdict(revision), "revision_id": revision.revision_id,
        "result_rows_sha256": sha256(rows_json.encode()).hexdigest(),
        "report_json": canonical_json(report),
        **{key: report["result_quality"][key] for key in (
            "candidate_count", "accepted_count", "skipped_count", "invalid_count")},
        "weather_matched_count": report["weather_coverage"]["matched_count"],
    }
    # Bound the read-back and query-parameter payload for this small demonstration.
    if len(rows_json.encode()) + len(canonical_json(metadata).encode()) > 1024 * 1024:
        raise ValueError("selection baseline exceeds the 1 MiB demonstration limit")
    receipt = {
        "attempt_id": successful_attempt_id, "revision_id": revision.revision_id,
        "status": "succeeded", "validation_scope": "warehouse",
        "validation_code_sha256": validation_code_sha256,
        "validation_invocation_id": validation_invocation_id,
    }
    return PreparedSelection(
        dataset, Selection(revision.event_id, revision.revision_id, successful_attempt_id),
        expected, canonical_json(metadata), rows_json, canonical_json(receipt),
    )


def _snapshot_sql(dataset: str) -> str:
    # Read the unselected candidate directly. Two metadata/receipt rows reveal
    # ambiguous keys; N+1 candidates reveals an overfull load as well as a short one.
    return f"""SELECT
    ARRAY(SELECT TO_JSON_STRING(r) FROM `{dataset}.analysis_revisions` r
          WHERE revision_id = @revision_id ORDER BY TO_JSON_STRING(r) LIMIT 2) AS metadata_json,
    ARRAY(SELECT TO_JSON_STRING(c) FROM `{dataset}.revision_result_rows` c
          WHERE revision_id = @revision_id
          ORDER BY source_row_number, TO_JSON_STRING(c) LIMIT @row_limit) AS rows_json,
    ARRAY(SELECT TO_JSON_STRING(a) FROM `{dataset}.revision_attempts` a
          WHERE attempt_id = @attempt_id ORDER BY TO_JSON_STRING(a) LIMIT 2) AS receipt_json"""


def _guarded_sql(dataset: str) -> str:
    snapshot = _snapshot_sql(dataset).replace("SELECT\n", "SELECT AS STRUCT\n", 1)
    return f"""DECLARE candidate STRUCT<metadata_json ARRAY<STRING>, rows_json ARRAY<STRING>, receipt_json ARRAY<STRING>>;
DECLARE current_selection ARRAY<STRUCT<event_id STRING, revision_id STRING, successful_attempt_id STRING>>;
DECLARE outcome STRING DEFAULT 'selected';
BEGIN TRANSACTION;
SET candidate = ({snapshot});
ASSERT TO_JSON_STRING(candidate.metadata_json) = TO_JSON_STRING(@metadata_json)
   AND TO_JSON_STRING(candidate.rows_json) = TO_JSON_STRING(@rows_json)
   AND TO_JSON_STRING(candidate.receipt_json) = TO_JSON_STRING(@receipt_json)
   AS 'candidate changed';
SET current_selection = ARRAY(
    SELECT AS STRUCT event_id, revision_id, successful_attempt_id
    FROM `{dataset}.event_selections` WHERE event_id = @event_id LIMIT 2
);
ASSERT ARRAY_LENGTH(current_selection) <= 1 AS 'ambiguous selection';
IF ARRAY_LENGTH(current_selection) = 1
   AND current_selection[SAFE_OFFSET(0)].revision_id = @revision_id
   AND current_selection[SAFE_OFFSET(0)].successful_attempt_id = @attempt_id THEN
    SET outcome = 'already_selected';
ELSE
    ASSERT (@expected_revision_id IS NULL AND ARRAY_LENGTH(current_selection) = 0)
        OR (ARRAY_LENGTH(current_selection) = 1
            AND current_selection[SAFE_OFFSET(0)].revision_id = @expected_revision_id
            AND current_selection[SAFE_OFFSET(0)].successful_attempt_id = @expected_attempt_id)
        AS 'selection changed';
    IF @expected_revision_id IS NULL THEN
        INSERT INTO `{dataset}.event_selections` (event_id, revision_id, successful_attempt_id)
        VALUES (@event_id, @revision_id, @attempt_id);
        ASSERT @@row_count = 1 AS 'expected one inserted selection';
    ELSE
        UPDATE `{dataset}.event_selections`
        SET revision_id = @revision_id, successful_attempt_id = @attempt_id
        WHERE event_id = @event_id AND revision_id = @expected_revision_id
            AND successful_attempt_id = @expected_attempt_id;
        ASSERT @@row_count = 1 AS 'expected one updated selection';
    END IF;
END IF;
COMMIT TRANSACTION;
SELECT outcome AS status, @event_id AS event_id, @revision_id AS revision_id,
       @attempt_id AS successful_attempt_id;
"""


def _validate_snapshot(snapshot, prepared):
    if len(snapshot["metadata_json"]) != 1 or len(snapshot["receipt_json"]) != 1:
        raise ValueError("candidate requires unique metadata and its exact warehouse receipt")
    metadata = json.loads(snapshot["metadata_json"][0])
    expected_metadata = json.loads(prepared.metadata_json)
    # Relocated input paths are provenance, not a different analytical result.
    for record in (metadata, expected_metadata):
        record["report_json"] = _analytical_json(json.loads(record["report_json"]))
        record["settings_json"] = canonical_json(json.loads(record["settings_json"]))
    if metadata != expected_metadata:
        raise ValueError("stored revision/report differs from the local baseline")
    if json.loads(snapshot["receipt_json"][0]) != json.loads(prepared.receipt_json):
        raise ValueError("candidate lacks the requested successful warehouse receipt")
    actual = []
    for raw in snapshot["rows_json"]:
        row = json.loads(raw)
        revision_id = row.pop("revision_id")
        actual.append({"revision_id": revision_id, **_normalise_fields(row)})
    if actual != json.loads(prepared.rows_json):
        raise ValueError("stored candidate rows differ from the local baseline")


class SelectionOutcomeUnknown(RuntimeError):
    """A submitted job may have committed; inspect it before another submission."""

    def __init__(self, job_id):
        self.job_id = job_id
        super().__init__(f"selection outcome unconfirmed; inspect BigQuery job {job_id}; no automatic retry")


def publish_selection(client, prepared: PreparedSelection) -> dict:
    """Check complete candidate contents, then compare-and-set the event pointer.

    Does not change candidate rows or create success receipts. The transaction
    rechecks the exact warehouse snapshot validated by Python before writing.
    Fresh query job IDs identify executions, separately from revision identity.
    """
    from google.cloud import bigquery

    if client.project != prepared.dataset.split(".")[0]:
        raise ValueError("client project must match the destination project")
    selection = prepared.selection
    params = [
        bigquery.ScalarQueryParameter("event_id", "STRING", selection.event_id),
        bigquery.ScalarQueryParameter("revision_id", "STRING", selection.revision_id),
        bigquery.ScalarQueryParameter("attempt_id", "STRING", selection.successful_attempt_id),
        bigquery.ScalarQueryParameter("row_limit", "INT64", len(json.loads(prepared.rows_json)) + 1),
    ]
    jobs = []

    def query(sql, parameters, *, writing=False):
        job_id = f"runwx_{'select' if writing else 'candidate'}_{uuid4().hex}"
        config = bigquery.QueryJobConfig(
            use_legacy_sql=False, use_query_cache=False,
            create_session=False, connection_properties=[],
            maximum_bytes_billed=MAXIMUM_BYTES_BILLED, job_timeout_ms=300000,
            query_parameters=parameters,
        )
        try:
            job = client.query(sql, location="europe-west1", job_id=job_id,
                               job_config=config, retry=None, job_retry=None, timeout=30)
            result = list(job.result(timeout=300, retry=None, job_retry=None, max_results=2))
            if len(result) != 1:
                raise ValueError("expected one query result")
        except Exception as error:
            if writing:
                raise SelectionOutcomeUnknown(job_id) from error
            raise
        jobs.append({"job_id": job_id, "bytes_processed": job.total_bytes_processed,
                     "bytes_billed": job.total_bytes_billed})
        return dict(result[0])

    snapshot = query(_snapshot_sql(prepared.dataset), params)
    _validate_snapshot(snapshot, prepared)
    expected = prepared.expected
    write_params = params + [
        bigquery.ScalarQueryParameter("expected_revision_id", "STRING", expected.revision_id if expected else None),
        bigquery.ScalarQueryParameter("expected_attempt_id", "STRING", expected.successful_attempt_id if expected else None),
        *[bigquery.ArrayQueryParameter(name, "STRING", snapshot[name])
          for name in ("metadata_json", "rows_json", "receipt_json")],
    ]
    outcome = query(_guarded_sql(prepared.dataset), write_params, writing=True)
    if (outcome.get("status") not in {"selected", "already_selected"}
            or any(outcome.get(k) != v for k, v in asdict(selection).items())):
        raise SelectionOutcomeUnknown(jobs[-1]["job_id"])
    return {**outcome, "jobs": jobs}
