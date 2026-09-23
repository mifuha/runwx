"""Manually coordinate a complete GNR comparison from shared, saved inputs."""

from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG, Param, task


with DAG(
    dag_id="runwx_gnr_batch",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    dagrun_timeout=timedelta(hours=2),
    default_args={"retries": 0, "execution_timeout": timedelta(minutes=35)},
    params={"batch": Param({}, type="object", description="Saved config and shared worker paths")},
    tags=["runwx", "historical", "gnr"],
) as dag:

    @task(multiple_outputs=False)
    def prepare_batch(params=None):
        from runwx_airflow.batch import prepare
        return prepare(params["batch"])

    @task(multiple_outputs=False)
    def load_or_verify_snapshots(references):
        from runwx_airflow.batch import load
        return load(references)

    @task(multiple_outputs=False)
    def build_edition_summary(references):
        from runwx_airflow.batch import run_stage
        return run_stage(references, "gnr_edition")

    @task(multiple_outputs=False)
    def build_comparison(references):
        from runwx_airflow.batch import run_stage
        return run_stage(references, "gnr_comparison")

    @task(multiple_outputs=False)
    def reconcile_results(references):
        from runwx_airflow.batch import run_stage
        return run_stage(references, "reconciliation")

    prepared = prepare_batch()
    loaded = load_or_verify_snapshots(prepared)
    editions = build_edition_summary(loaded)
    compared = build_comparison(editions)
    reconcile_results(compared)
