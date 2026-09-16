# Historical pipeline orchestration

The first Airflow DAG connects the existing stages for one explicitly configured
historical snapshot. It is implemented and tested offline; it has not yet run
against GCP. No managed Airflow environment or new IAM has been deployed.

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
`export_weather_kind: historical_reanalysis` label.

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
in the Airflow worker. Pin the eventual managed image/provider combination during
deployment review rather than assuming this local lock installs into Composer.

## Live validation remains a separate step

Before a real trigger, review the configuration and narrow runtime permissions:

| Operation | Execution location and identity |
|---|---|
| Invoke/wait and read evidence | Airflow worker credentials; coordinator identity and grants still to prepare |
| Validate/export | Existing `runwx-report` service account in Cloud Run |
| Load/verify snapshot | Existing Python loader in the Airflow worker, using that worker's ADC in this first adapter |
| dbt and independent queries | Existing `runwx-dbt` service account in Cloud Run |

This first adapter uses Application Default Credentials; it does not yet establish
a separately impersonated loader identity. A native run must identify the actual
actor. Do not grant the report job BigQuery access or claim least-privilege
orchestration validation from these offline tests. No Terraform resources change
in this slice.

The next live milestone should demonstrate one success, invalid-input failure and
an identical rerun against the existing Folkestone snapshot. The first load from
this GCS path is still unproven; the snapshot already exists, so verification is
the expected result. A later explicit second configuration can demonstrate a
historical multi-edition run. Qualification/capture, destination approval, image
publication and starting the workflow remain manual.

A short managed Airflow experiment can follow offline verification. Its proposed
identity, permissions, cost limit, evidence and teardown boundary are recorded in
the [first managed Airflow run plan](airflow-live-plan.md). Keep its Terraform
state separate from retained race data and jobs. No continuously running
environment is part of this local change.

API references: [Airflow 3.1.6 best practices](https://airflow.apache.org/docs/apache-airflow/3.1.6/best-practices.html),
[Cloud Run Jobs SDK](https://cloud.google.com/python/docs/reference/run/latest/google.cloud.run_v2.services.jobs.JobsClient).
