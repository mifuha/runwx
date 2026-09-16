"""Manually orchestrate one explicitly configured historical snapshot."""

from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG, Param, task


with DAG(
    dag_id="runwx_historical",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    dagrun_timeout=timedelta(hours=1),
    default_args={"retries": 0, "execution_timeout": timedelta(minutes=35)},
    params={"snapshot": Param({}, type="object", description="Reviewed fixed-snapshot configuration")},
    tags=["runwx", "historical"],
) as dag:

    @task
    def validate_configuration(params=None):
        from runwx_airflow.config import validate_config
        return validate_config(params["snapshot"])

    @task(multiple_outputs=False)
    def execute_export(config):
        from runwx_airflow.tasks import execute_job
        return execute_job(config, "report")

    @task(multiple_outputs=False)
    def verify_artifacts(config, execution):
        from runwx_airflow.tasks import verify_export
        return verify_export(config, execution)

    @task(multiple_outputs=False)
    def load_or_verify_snapshot(config, references):
        from runwx_airflow.tasks import load_snapshot
        return load_snapshot(config, references)

    @task(multiple_outputs=False)
    def execute_dbt_stage(config):
        from runwx_airflow.tasks import execute_job
        return execute_job(config, "dbt")

    @task(multiple_outputs=False)
    def verify_execution_evidence(config, execution):
        from runwx_airflow.tasks import verify_dbt_evidence
        return verify_dbt_evidence(config, execution)

    config = validate_configuration()
    exported = execute_export(config)
    artifacts = verify_artifacts(config, exported)
    loaded = load_or_verify_snapshot(config, artifacts)
    built = execute_dbt_stage(config)
    loaded >> built
    verify_execution_evidence(config, built)
