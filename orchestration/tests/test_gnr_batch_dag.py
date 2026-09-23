"""Real Airflow DAG execution; only dbt subprocess and BigQuery I/O are simulated."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

pytest.importorskip('airflow')
from airflow.models import DagBag
from airflow.utils import db
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests'))
from test_gnr_batch import batch, Warehouse  # Reuse only input fixtures, not the tested orchestration.
from gnr_batch_support import dbt_artifacts, uniform_inputs, warehouse_summaries
import stage_runner

ORDER = ['prepare_batch', 'load_or_verify_snapshots', 'build_edition_summary',
         'build_comparison', 'reconcile_results']


@pytest.fixture(scope='module')
def dag():
    assert Path(os.environ['AIRFLOW_HOME']).is_relative_to('/tmp')
    db.initdb()
    bag = DagBag(dag_folder=str(ROOT/'orchestration/dags'), include_examples=False)
    assert bag.import_errors == {}
    return bag.dags['runwx_gnr_batch']


def test_batch_dag_dependencies(dag):
    assert list(dag.task_dict) == ORDER
    assert dag.schedule is None and not dag.catchup
    assert dag.max_active_runs == dag.max_active_tasks == 1
    for i, name in enumerate(ORDER):
        task = dag.get_task(name)
        assert task.retries == 0 and task.trigger_rule == 'all_success'
        assert task.upstream_task_ids == ({ORDER[i-1]} if i else set())


@pytest.mark.parametrize('failure', [None, 'prepare', 'load', 'edition', 'comparison', 'reconciliation'])
def test_offline_batch_end_to_end(dag, batch, tmp_path, monkeypatch, failure):
    uniform_inputs(batch)
    warehouse = Warehouse()
    calls = []
    original_query = warehouse.query

    def query(sql, **kwargs):
        if 'mart_gnr_' not in sql:
            return original_query(sql, **kwargs)
        comparison = 'mart_gnr_sample_comparison' in sql
        rows = warehouse_summaries(warehouse.rows, comparison=comparison)
        if failure == 'reconciliation' and comparison:
            rows[-1]['median_pace_s_per_km'] += 1
        return Mock(job_id=f'check-{comparison}', total_bytes_processed=1000,
                    total_bytes_billed=10485760, cache_hit=False, errors=None,
                    result=Mock(return_value=[{'row_json': json.dumps(row)} for row in rows]))

    warehouse.api.query.side_effect = query
    monkeypatch.setattr(bigquery, 'Client', lambda **kw: warehouse.api)
    original_load = warehouse.load

    def load(source, destination, **kwargs):
        if failure == 'load' and '2022' in destination:
            raise TimeoutError('uncertain load')
        return original_load(source, destination, **kwargs)
    warehouse.api.load_table_from_file.side_effect = load

    def dbt(command, **kwargs):
        folder = Path(command[command.index('--target-path')+1])
        stage = folder.parent.name
        calls.append(stage)
        assert len(warehouse.rows) == 2  # All editions precede either model build.
        assert '--indirect-selection' in command and 'cautious' in command
        variables = json.loads(command[command.index('--vars')+1])
        assert set(variables['gnr_sample_tables']) == set(warehouse.rows)
        assert variables['gnr_baseline_event_id'] == 'greatrun:881'
        dbt_artifacts(folder, stage)
        if failure == stage.removeprefix('gnr_'):
            # A dbt process can exit zero yet have incomplete or failed artifacts.
            file = folder/'run_results.json'
            data = json.loads(file.read_text())
            data['results'][-1]['status'] = 'fail'
            file.write_text(json.dumps(data))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(stage_runner.subprocess, 'run', dbt)
    if failure == 'prepare':
        (tmp_path/'2022/weather.json').write_text('{}')

    def run(name):
        output = tmp_path/name
        result = dag.test(logical_date=datetime.now(timezone.utc), run_conf={'batch': {
            'config': str(batch), 'output': str(output),
            'dbt_project': str(ROOT/'dbt'), 'dbt_python': sys.executable}})
        return result, output

    result, output = run('first')
    states = {ti.task_id: ti.state for ti in result.get_task_instances()}
    if failure:
        failed_index = ['prepare', 'load', 'edition', 'comparison', 'reconciliation'].index(failure)
        assert result.state == 'failed'
        assert states[ORDER[failed_index]] == 'failed'
        assert all(states[name] == 'upstream_failed' for name in ORDER[failed_index+1:])
        assert calls == ['gnr_edition', 'gnr_comparison'][:max(0, failed_index-1)]
        if failure != 'prepare':
            record = json.loads((output/'execution/execution.json').read_text())
            assert record['status'] == 'failed'
        if failure == 'load':
            assert len(warehouse.rows) == 1  # Earlier successful snapshot survives.
            failure = None
            recovered, recovered_output = run('recovered')
            assert recovered.state == 'success'
            assert calls == ['gnr_edition', 'gnr_comparison']
            recovered_record = json.loads((recovered_output/'execution/execution.json').read_text())
            assert [e['status'] for e in recovered_record['editions']] == [
                'already_present_verified', 'loaded_verified']
            assert len(warehouse.loads) == 2
        return
    assert result.state == 'success'
    assert calls == ['gnr_edition', 'gnr_comparison']
    record = json.loads((output/'execution/execution.json').read_text())
    assert record['status'] == 'reconciled' and record['analytical_status'] == 'passed'
    assert [s['status'] for s in record['analytical_stages']] == ['passed']*3
    assert len(warehouse.loads) == 2
    result, output = run('rerun')
    assert result.state == 'success'
    assert calls == ['gnr_edition', 'gnr_comparison']*2  # Once per complete run.
    assert len(warehouse.loads) == 2
    record = json.loads((output/'execution/execution.json').read_text())
    assert all(e['status'] == 'already_present_verified' for e in record['editions'])
