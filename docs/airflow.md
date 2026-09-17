# Historical pipeline orchestration

The first Airflow DAG connects the existing stages for one explicitly configured
historical snapshot. It is tested offline and completed a bounded Cloud Composer
experiment against the frozen Folkestone 2019 snapshot. The temporary environment
and its runtime permissions were removed after validation.

```text
validate_configuration
        ↓
execute_export                 existing runwx-report Cloud Run job
        ↓
verify_artifacts               exact report/NDJSON generations and hashes
        ↓
load_or_verify_snapshot        existing Python BigQuery loader
        ↓
execute_dbt_stage              existing runwx-dbt Cloud Run job
                              edition → comparison → reconciliation
        ↓
verify_execution_evidence      exact manifest/ZIP and recorded query results
```

The DAG is manual, with one active run, one active task and no automatic retries.
Every downstream task requires upstream success. The final evidence task is the
only leaf, so a failed earlier task cannot turn into a successful pipeline run.
dbt failures can leave already-created views; there is no rollback claim.

Airflow handles configuration, invocation and artifact references. The existing
report job still owns parsing, validation, weather alignment and export. The
existing dbt runner still owns build ordering, tests and warehouse reconciliation.
The loader reuses `prepare_stored_load` and `load_prepared`; it downloads and
validates pinned bytes again in its own task instead of passing rows through XCom.
The final verifier checks recorded reconciliation results without issuing new SQL.

## Inputs and execution identity

[The Folkestone 2019 configuration](../orchestration/folkestone-2019.json) contains
the fixed input URIs/hashes, expected export hash, explicit destination, pinned
images/source revisions and existing frozen dbt expectations. It names existing
resources; it does not create tables or datasets. Its report override preserves
the report API's `weather_kind: unknown` label and the export's more specific
`export_weather_kind: historical_reanalysis` label, and explicitly preserves chip
timing as the warehouse export's timing basis.

Configuration validation checks that report settings and hashes agree with the
edition expectations, and the loader destination is the dbt source table.
There is no default historical snapshot or automatic edition selection.

A small Cloud Run SDK wrapper submits an existing job once, logs its operation ID,
waits for completion and returns that exact execution ID. It checks the deployed
image and single-task/no-retry settings before submission. This avoids reading a
job's mutable `latest` execution to locate artifacts. Outputs use the existing
execution-specific `task-0-attempt-0` names. Metadata lookups pin generations before
download, and artifact identities must match the submitted execution.

If submission acknowledgement or waiting fails, inspect Cloud Run and the logged
operation before clearing the task. A failed wait does not prove that the remote
job stopped. Do not blindly rerun submissions. SDK reads may use their bounded
transport retries; Airflow submission retries are disabled.

An identical pipeline rerun gets fresh execution artifacts. The loader verifies
the existing snapshot without another load; dbt may rebuild the same derived views.
The DAG does not overwrite immutable inputs or evidence.

## Offline checks

Use a separate Python 3.12 environment. The orchestration lock records the tested
Airflow 3.1.6 / Cloud Run SDK 0.15.0 environment, including the application's
existing httpx 0.27 requirement. It does not change either Cloud Run image lock.

From the repository root:

```bash
python3.12 -m venv /tmp/runwx-airflow-venv
/tmp/runwx-airflow-venv/bin/pip install -r orchestration/requirements.lock -e '.[bigquery]'
/tmp/runwx-airflow-venv/bin/pip check
export AIRFLOW_HOME=/tmp/runwx-airflow-test
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/orchestration/dags"
export PYTHONPATH="$PWD/orchestration:$PWD/dbt"
/tmp/runwx-airflow-venv/bin/pytest -q orchestration/tests
```

These tests use Airflow's real DAG import and in-process execution with an isolated
SQLite metadata database. GCP boundaries are replaced with test doubles; network
resolution and credential discovery are blocked. They test success and failure at
each boundary, plus the real artifact parsers/loader preparation and cloud wrapper
formats. They do not prove live permissions, managed deployment or a native load.
Ordinary application tests remain `pytest -q tests`.

The new CI job runs the same offline checks. Keep the repository's `orchestration`
and `dbt` directories on the worker Python path; neither dbt nor SQL is executed
in the Airflow worker. The managed experiment separately pinned Composer
3 / Airflow 3.1.7 and its provider set rather than installing this local lock.

## Managed validation

The temporary Composer worker used the deleted `runwx-orchestrator` service account:

| Operation | Execution location and identity |
|---|---|
| Invoke/wait and read evidence | Airflow worker credentials; temporary `runwx-orchestrator` |
| Validate/export | Existing `runwx-report` service account in Cloud Run |
| Load/verify snapshot | Existing Python loader using the worker's attached credentials; query jobs and read access to the exact table only |
| dbt and independent queries | Existing `runwx-dbt` service account in Cloud Run |

Run `runwx-invalid-20260917T1229Z` failed configuration validation and all five
downstream tasks were blocked without a Cloud Run submission. Two subsequent runs
exposed integration assumptions at real boundaries: Cloud Run returned a short job
name, and the report override initially omitted chip timing. The exact checks stopped
both runs before unsafe downstream work; PRs #28 and #29 fixed the assumptions before
a fresh execution.

Run `runwx-success3-20260917T1734Z` and identical rerun
`runwx-rerun-20260917T1740Z` each passed all six tasks. They created distinct
execution-specific artifacts, but both exports contained 459 rows, 551872 bytes and
SHA-256 `f95b3ae312e3131279a8a5ebbe77f58d3967d70bc7007b6c268f0bd4492eef47`.
Both loader tasks returned `already_present_verified` with a null load job ID, and
both dbt runs passed edition/comparison reconciliation and immutable evidence checks.

The experiment proves managed sequencing, failure propagation and duplicate-safe
verification of an existing snapshot. It does not prove the first write to an empty
table, automatic retries or a multi-edition backfill. dbt views can still be changed
before a later test fails; the DAG does not provide rollback.

Teardown removed the Composer environment, its bucket, custom network/subnet, runtime
identity and every runtime grant. Terraform state is empty and a destroy plan is
no-op. The orchestration project, billing link, enabled APIs and unmanaged default
network remain; the existing Cloud Run jobs, immutable evidence and 459-row table are
retained, and the table data remains the 459 rows verified by both runs. See the
[sanitized execution evidence](evidence/composer-airflow-validation.json)
and the original [managed run plan](airflow-live-plan.md). No continuously running
Airflow environment remains.

API references: [Airflow 3.1.6 best practices](https://airflow.apache.org/docs/apache-airflow/3.1.6/best-practices.html),
[Cloud Run Jobs SDK](https://cloud.google.com/python/docs/reference/run/latest/google.cloud.run_v2.services.jobs.JobsClient).
