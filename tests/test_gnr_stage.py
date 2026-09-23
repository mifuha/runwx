"""Sample analytical expectations and the shared dbt artifact contract."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'dbt'))
import gnr_stage
import stage_runner
from runwx.services.gnr_batch import prepare_batch, _read_prepared
from test_gnr_batch import batch, Warehouse
from gnr_batch_support import dbt_artifacts, uniform_inputs, warehouse_summaries


def test_independent_expectations_match_known_distributions(batch, tmp_path):
    uniform_inputs(batch)
    prepare_batch(batch, tmp_path/'prepared')
    plan, loads, _ = _read_prepared(tmp_path/'prepared/plan.json')
    expected = warehouse_summaries({load.table_id: load.rows for load in loads})
    stage_runner.assert_same(gnr_stage.expected_editions(loads), expected)
    build = gnr_stage.build_plan(plan, tmp_path/'run', Path(__file__).resolve().parents[1]/'dbt',
                                 'gnr_comparison', sys.executable)
    variables = json.loads(build['command'][build['command'].index('--vars')+1])
    assert len(variables['gnr_sample_tables']) == 2
    assert variables['gnr_baseline_event_id'] == 'greatrun:881'
    assert build['environment']['RUNWX_DBT_MAXIMUM_BYTES_BILLED'] == '104857600'


@pytest.mark.parametrize('stage', ['gnr_edition', 'gnr_comparison'])
@pytest.mark.parametrize('mutation', [None, 'omitted_test', 'failed_test', 'foreign_invocation', 'missing_model'])
def test_gnr_artifact_contract(tmp_path, stage, mutation):
    dbt_artifacts(tmp_path/'target', stage)
    result_path = tmp_path/'target/run_results.json'
    result = json.loads(result_path.read_text())
    if mutation == 'omitted_test': result['results'].pop()
    if mutation == 'failed_test': result['results'][-1]['status'] = 'fail'
    if mutation == 'foreign_invocation': result['metadata']['invocation_id'] = 'different'
    if mutation == 'missing_model':
        path = tmp_path/'target/manifest.json'
        manifest = json.loads(path.read_text())
        del manifest['nodes'][result['results'][0]['unique_id']]
        path.write_text(json.dumps(manifest))
    result_path.write_text(json.dumps(result))
    if mutation:
        with pytest.raises(ValueError):
            stage_runner.verify_artifacts(tmp_path, stage)
    else:
        value = stage_runner.verify_artifacts(tmp_path, stage)
        assert value['models'] == 1
        assert value['data_tests'] + value['unit_tests'] == 5


def test_no_model_build_before_all_loads_succeed(batch, tmp_path, monkeypatch):
    from runwx.services.gnr_batch import execute_batch, BatchError

    uniform_inputs(batch)
    prepare_batch(batch, tmp_path/'prepared')
    path = tmp_path/'prepared/plan.json'
    plan = json.loads(path.read_text())
    warehouse = Warehouse()
    warehouse.fail_table = plan['editions'][1]['table_id']
    with pytest.raises(BatchError):
        execute_batch(path, tmp_path/'run', client=warehouse.api)
    monkeypatch.setattr(stage_runner, 'execute_build', lambda *a: pytest.fail('built after failed load'))
    with pytest.raises(ValueError, match='every required snapshot'):
        gnr_stage.run_stage(path, tmp_path/'run', 'dbt', 'gnr_edition')


def test_local_batch_cli_runs_the_shared_analytical_steps(batch, tmp_path, monkeypatch, capsys):
    import subprocess
    from unittest.mock import Mock
    from google.cloud import bigquery
    from runwx.main import main

    uniform_inputs(batch)
    prepare_batch(batch, tmp_path/'prepared')
    warehouse = Warehouse()
    original_query = warehouse.query
    calls = []

    def query(sql, **kwargs):
        if 'mart_gnr_' not in sql:
            return original_query(sql, **kwargs)
        rows = warehouse_summaries(warehouse.rows, 'mart_gnr_sample_comparison' in sql)
        return Mock(job_id='reconciliation-test', total_bytes_processed=100,
                    total_bytes_billed=10485760, cache_hit=False, errors=None,
                    result=Mock(return_value=[{'row_json': json.dumps(row)} for row in rows]))

    warehouse.api.query.side_effect = query
    monkeypatch.setattr(bigquery, 'Client', lambda **kw: warehouse.api)

    def process(command, **kwargs):
        if '--plan' in command:
            gnr_stage.execute(command[command.index('--plan')+1],
                              command[command.index('--execution-dir')+1],
                              Path(command[1]).parent, dbt_python=command[-1])
        else:
            folder = Path(command[command.index('--target-path')+1])
            calls.append(folder.parent.name)
            dbt_artifacts(folder, folder.parent.name)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, 'run', process)
    main(['batch', 'execute', str(tmp_path/'prepared/plan.json'),
          '--output', str(tmp_path/'execution'), '--dbt-project', str(Path(gnr_stage.__file__).parent)])
    record = json.loads(capsys.readouterr().out)
    assert record['status'] == 'reconciled'
    assert calls == ['gnr_edition', 'gnr_comparison']
