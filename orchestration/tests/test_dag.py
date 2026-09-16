"""Real Airflow dependency execution, with all GCP boundaries replaced offline."""

from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

pytest.importorskip("airflow")

from airflow.models import DagBag
from airflow.utils import db
from runwx_airflow import tasks


ROOT = Path(__file__).resolve().parents[2]
ORDER = ["validate_configuration", "execute_export", "verify_artifacts",
         "load_or_verify_snapshot", "execute_dbt_stage", "verify_execution_evidence"]


@pytest.fixture(scope="module")
def dag():
    # AIRFLOW_HOME must point to an isolated temporary directory in the test command.
    assert Path(os.environ["AIRFLOW_HOME"]).is_relative_to("/tmp")
    db.initdb()
    bag = DagBag(dag_folder=str(ROOT / "orchestration/dags"), include_examples=False)
    assert bag.import_errors == {}
    return bag.dags["runwx_historical"]


def test_manual_dag_contract(dag):
    assert list(dag.task_dict) == ORDER
    assert dag.schedule is None and not dag.catchup
    assert dag.max_active_runs == dag.max_active_tasks == 1
    assert dag.leaves[0].task_id == "verify_execution_evidence"
    for index, name in enumerate(ORDER):
        task = dag.get_task(name)
        assert task.retries == 0
        assert task.trigger_rule == "all_success"
        if index:
            assert ORDER[index - 1] in task.upstream_task_ids


@pytest.mark.parametrize("failure", [None, "validate", "export", "artifacts", "load", "dbt", "evidence"])
def test_airflow_stops_downstream_after_failure(dag, config, monkeypatch, failure):
    called = []

    def boundary(name, result):
        def call(*args, **kwargs):
            called.append(name)
            if name == failure:
                raise ValueError(f"deliberate {name} failure")
            return result
        return call

    def execute(config, stage):
        name = "export" if stage == "report" else "dbt"
        return boundary(name, {"name": f"execution-{stage}"})()

    monkeypatch.setattr(tasks, "execute_job", execute)
    monkeypatch.setattr(tasks, "verify_export", boundary("artifacts", {"report_generation": 12}))
    monkeypatch.setattr(tasks, "load_snapshot", boundary("load", {"status": "already_present_verified"}))
    monkeypatch.setattr(tasks, "verify_dbt_evidence", boundary("evidence", {"status": "verified"}))
    if failure == "validate":
        config["table_id"] = "wrong.table"
    cases = [None, "validate", "export", "artifacts", "load", "dbt", "evidence"]
    result = dag.test(
        logical_date=datetime.now(timezone.utc),
        run_conf={"snapshot": config},
    )
    states = {ti.task_id: ti.state for ti in result.get_task_instances()}
    if failure is None:
        assert result.state == "success"
        assert all(states[name] == "success" for name in ORDER)
        assert called == ["export", "artifacts", "load", "dbt", "evidence"]
    else:
        failed_index = cases.index(failure) - 1
        assert result.state == "failed"
        assert states[ORDER[failed_index]] == "failed"
        assert all(states[name] == "upstream_failed" for name in ORDER[failed_index + 1:])
        assert called == ["export", "artifacts", "load", "dbt", "evidence"][:failed_index]
