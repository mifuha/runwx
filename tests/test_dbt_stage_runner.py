"""Runner contracts with no warehouse or dbt dependency."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SPEC = importlib.util.spec_from_file_location('stage_runner', Path(__file__).resolve().parents[1] / 'dbt/stage_runner.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture
def config():
    return dict(project='runwx-example', location='europe-west1',
                source_dataset='staging', source_table='snapshot_a',
                edition_dataset='edition_a', comparison_dataset='edition_a',
                comparison_datasets=['edition_a', 'edition_b'], comparison_baseline='edition_a', top_n=20)


@pytest.fixture
def expectations():
    return {
        'edition': {'mart': {'event_id': 'example:a'}, 'weather': {'enriched_count': 1}},
        'comparison': [
            {'snapshot_dataset': 'edition_a', 'median_duration_s': 10.0},
            {'snapshot_dataset': 'edition_b', 'median_duration_s': 12.0},
        ],
    }


def artifacts(folder, stage):
    """Independent simulated dbt contract: 3/1 models and 21/7 tests."""
    model_names = ['stg_race_results', 'fct_race_results', 'mart_event_summary'] if stage == 'edition' else ['mart_course_comparison']
    models = ['model.runwx.' + name for name in model_names]
    nodes = {uid: dict(resource_type='model', config={'materialized': 'view'},
                       tags=['comparison'] if stage == 'comparison' else []) for uid in models}
    for kind, count in [('test', 14 if stage == 'edition' else 5), ('unit_test', 7 if stage == 'edition' else 2)]:
        for i in range(count):
            nodes[f'{kind}.runwx.example_{i}'] = dict(resource_type=kind, depends_on={'nodes': [models[-1]]})
    nodes['model.runwx.intermediate'] = dict(resource_type='model', config={'materialized': 'ephemeral'}, tags=['comparison'])
    results = [dict(unique_id=uid, status='success' if uid.startswith('model.') else 'pass')
               for uid in nodes if uid != 'model.runwx.intermediate']
    folder.mkdir(parents=True)
    manifest = dict(metadata={'invocation_id': stage}, nodes={k:v for k,v in nodes.items() if not k.startswith('unit_test.')},
                    unit_tests={k:v for k,v in nodes.items() if k.startswith('unit_test.')})
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    (folder / 'run_results.json').write_text(json.dumps(dict(metadata={'invocation_id': stage}, results=results)))


def fake_build(monkeypatch, calls, mutate=None):
    def run(command, **kwargs):
        target = Path(command[command.index('--target-path') + 1])
        stage = target.parent.name
        calls.append(stage)
        assert kwargs['env']['RUNWX_DBT_PROJECT'] == 'runwx-example'
        assert 'DBT_SELECT' not in kwargs['env']
        kwargs['stdout'].write('build diagnostics\n')
        artifacts(target, stage)
        if mutate:
            mutate(target, stage)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(runner.subprocess, 'run', run)


class FakeJob:
    def __init__(self, stage, rows):
        self.job_id = f'{stage}-job'
        self.rows = rows
        self.total_bytes_processed = 123
        self.total_bytes_billed = 10485760
        self.cache_hit = False
        self.errors = None

    def result(self, **kwargs):
        assert kwargs == {'timeout': 300, 'retry': None, 'job_retry': None,
                          'max_results': len(self.rows) + 1}
        return [{'row_json': json.dumps(row)} for row in self.rows]


class FakeClient:
    def __init__(self, expectations):
        copied = json.loads(json.dumps(expectations))
        self.results = [[copied['edition']], copied['comparison']]
        self.queries = []
        self.closed = False

    def query(self, sql, **kwargs):
        stage = ('edition' if 'mart_event_summary' in sql else 'comparison')
        assert kwargs['location'] == 'europe-west1'
        assert kwargs['retry'] is None and kwargs['job_retry'] is None
        assert kwargs['timeout'] == 30
        self.queries.append((stage, sql, kwargs['job_config']))
        return FakeJob(stage, self.results.pop(0))

    def close(self):
        self.closed = True


def fake_reconciliation(expectations):
    client = FakeClient(expectations)
    job_config = object()
    return client, lambda config: (client, job_config)


def test_preview_has_no_execution_or_files(config, expectations, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: pytest.fail('preview invoked dbt'))
    file = tmp_path / 'config.json'
    file.write_text(json.dumps(config))
    expected_file = tmp_path / 'expectations.json'
    expected_file.write_text(json.dumps(expectations))
    out = tmp_path / 'out'
    assert runner.main(['--config', str(file), '--expectations', str(expected_file),
                        '--output-dir', str(out)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['status'] == 'preview'
    assert [s['stage'] for s in plan['stages']] == ['edition', 'comparison']
    assert [s['stage'] for s in plan['reconciliation']] == ['edition', 'comparison']
    assert not out.exists()
    for stage in plan['stages']:
        cmd = stage['command']
        assert cmd[:3] == [sys.executable, '-m', 'dbt.cli.main']
        variables = json.loads(cmd[cmd.index('--vars') + 1])
        assert variables['source_table'] == 'snapshot_a'
        assert variables['top_n'] == 20
    assert plan['stages'][1]['command'][-2:] == ['--select', 'tag:comparison']


@pytest.mark.parametrize('change', [
    {'project': None}, {'project': 'bad;command'}, {'location': 'bad/location'},
    {'top_n': True}, {'top_n': 0},
    {'comparison_datasets': 'edition_a'}, {'comparison_datasets': ['edition_a', 'edition_a']},
    {'comparison_baseline': 'missing'}, {'edition_dataset': 'missing'},
    {'source_table': 'x;drop'}, {'edition_dataset': 'staging'},
    {'comparison_dataset': 'edition_b'}, {'surprise': 1},
])
def test_invalid_config_stops_before_execution(config, expectations, change, tmp_path, monkeypatch):
    config.update(change)
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: pytest.fail('invalid config invoked dbt'))
    with pytest.raises(ValueError):
        runner.execute(config, expectations, tmp_path / 'out', tmp_path)
    assert not (tmp_path / 'out').exists()


def test_success_retains_both_artifacts(config, expectations, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv('DBT_SELECT', 'nothing')
    fake_build(monkeypatch, calls)
    out = tmp_path / 'out'
    client, client_setup = fake_reconciliation(expectations)
    record = runner.execute(
        config, expectations, out, tmp_path, client_setup=client_setup)
    assert calls == ['edition', 'comparison']
    assert record['status'] == 'reconciled'
    assert record['analytical_reconciliation'] == 'passed'
    assert record['reconciliation_evidence'] == 'reconciliation/reconciliation.json'
    assert 'actual_rows' not in record['reconciliation']['queries'][0]
    assert [s['unit_tests'] + s['data_tests'] for s in record['stages']] == [21, 7]
    assert [s['invocation_id'] for s in record['stages']] == ['edition', 'comparison']
    for stage in calls:
        assert (out / stage / 'target/manifest.json').exists()
        assert (out / stage / 'console.log').read_text() == 'build diagnostics\n'
    assert len(client.queries) == 2
    assert json.loads((out / 'reconciliation/reconciliation.json').read_text())['status'] == 'reconciled'
    assert json.loads((out / 'expectations.json').read_text()) == expectations
    with pytest.raises(FileExistsError):
        runner.execute(config, expectations, out, tmp_path)
    assert calls == ['edition', 'comparison']


@pytest.mark.parametrize('problem', ['fail', 'skip', 'warn', 'missing', 'duplicate', 'invocation', 'no_artifact', 'manifest'])
def test_bad_edition_evidence_blocks_comparison(config, expectations, tmp_path, monkeypatch, problem):
    calls = []
    def mutate(target, stage):
        file = target / 'run_results.json'
        doc = json.loads(file.read_text())
        if problem in ('fail', 'skip', 'warn'):
            doc['results'][-1]['status'] = problem
        elif problem == 'missing':
            doc['results'].pop()
        elif problem == 'duplicate':
            doc['results'][-1] = doc['results'][0]
        elif problem == 'invocation':
            doc['metadata']['invocation_id'] = 'stale'
        elif problem == 'no_artifact':
            file.unlink()
            return
        elif problem == 'manifest':
            manifest = target / 'manifest.json'
            m = json.loads(manifest.read_text())
            m['unit_tests'] = {}
            manifest.write_text(json.dumps(m))
        file.write_text(json.dumps(doc))
    fake_build(monkeypatch, calls, mutate)
    out = tmp_path / 'out'
    with pytest.raises((ValueError, OSError)):
        runner.execute(config, expectations, out, tmp_path)
    assert calls == ['edition']
    assert json.loads((out / 'execution.json').read_text())['status'] == 'failed'
    assert (out / 'edition/console.log').exists()
    assert not (out / 'comparison').exists()


@pytest.mark.parametrize('timeout', [False, True])
def test_process_failure_blocks_comparison(config, expectations, tmp_path, monkeypatch, timeout):
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        kwargs['stdout'].write('failure details')
        if timeout:
            raise subprocess.TimeoutExpired(cmd, 1800)
        return subprocess.CompletedProcess(cmd, 1)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        runner.execute(config, expectations, tmp_path / 'out', tmp_path)
    assert len(calls) == 1
    assert json.loads((tmp_path / 'out/execution.json').read_text())['status'] == 'failed'
    assert json.loads((tmp_path / 'out/expectations.json').read_text()) == expectations


def test_comparison_failure_preserves_edition_success(config, expectations, tmp_path, monkeypatch):
    calls = []
    def mutate(target, stage):
        if stage == 'comparison':
            path = target / 'run_results.json'
            doc = json.loads(path.read_text())
            doc['results'][-1]['status'] = 'fail'
            path.write_text(json.dumps(doc))
    fake_build(monkeypatch, calls, mutate)
    out = tmp_path / 'out'
    with pytest.raises(ValueError):
        runner.execute(config, expectations, out, tmp_path)
    record = json.loads((out / 'execution.json').read_text())
    assert calls == ['edition', 'comparison']
    assert [stage['status'] for stage in record['stages']] == ['passed', 'failed']
    assert record['status'] == 'failed'
    assert (out / 'edition/target/run_results.json').exists()


def test_missing_configuration_field(config, expectations, tmp_path, monkeypatch):
    del config['source_table']
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: pytest.fail('missing source invoked dbt'))
    with pytest.raises(ValueError, match='exactly'):
        runner.execute(config, expectations, tmp_path / 'out', tmp_path)


@pytest.mark.parametrize('bad', [
    {},
    {'edition': {}, 'comparison': []},
    {'edition': {'mart': {}, 'weather': {'enriched_count': 1}},
     'comparison': [{'snapshot_dataset': 'edition_a'}, {'snapshot_dataset': 'edition_b'}]},
    {'edition': {'mart': {'event_id': 'a'}, 'weather': {'enriched_count': 1}},
     'comparison': [{'snapshot_dataset': 'edition_a'}, {'snapshot_dataset': 'edition_a'}]},
    {'edition': {'mart': {'event_id': 'a'}, 'weather': {'enriched_count': 1}},
     'comparison': [{'snapshot_dataset': 'edition_a'}]},
    {'edition': {'mart': {'event_id': 'a', 'pace': float('nan')},
                 'weather': {'enriched_count': 1}},
     'comparison': [{'snapshot_dataset': 'edition_a'}, {'snapshot_dataset': 'edition_b'}]},
    {'edition': {'mart': {'event_id': 'a', 'started_at_utc': '2019-09-29T09:00:00'},
                 'weather': {'enriched_count': 1}},
     'comparison': [{'snapshot_dataset': 'edition_a'}, {'snapshot_dataset': 'edition_b'}]},
])
def test_invalid_expectations_stop_before_build(config, bad, tmp_path, monkeypatch):
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: pytest.fail('bad expectations invoked dbt'))
    with pytest.raises(ValueError):
        runner.execute(config, bad, tmp_path / 'out', tmp_path)
    assert not (tmp_path / 'out').exists()


def test_reconciliation_plan_names_only_explicit_outputs(config, expectations):
    expectations['comparison'].reverse()
    plans = runner.build_reconciliation_plan(config, expectations)
    assert '`runwx-example.edition_a.mart_event_summary`' in plans[0]['sql']
    assert '`runwx-example.edition_a.fct_race_results`' in plans[0]['sql']
    assert plans[0]['sql'].rstrip().endswith('limit 2')
    assert '`runwx-example.edition_a.mart_course_comparison`' in plans[1]['sql']
    assert plans[1]['sql'].rstrip().endswith('limit 3')
    assert plans[0]['expected'] == [expectations['edition']]
    assert [row['snapshot_dataset'] for row in plans[1]['expected']] == [
        'edition_a', 'edition_b']


def test_value_comparison_is_structural_timezone_aware_and_float_tolerant():
    expected = {'started_at_utc': '2019-09-29T09:00:00+00:00',
                'pace': 356.21178366592403, 'count': 459, 'valid': True}
    runner.assert_same(
        {'started_at_utc': '2019-09-29T09:00:00Z',
         'pace': 356.2117836659241, 'count': 459, 'valid': True},
        expected)
    for actual in (
        {**expected, 'pace': float('nan')},
        {**expected, 'count': 459.0},
        {**expected, 'valid': 1},
        {**expected, 'extra': 'field'},
        {**expected, 'started_at_utc': '2019-09-29T09:00:01Z'},
        {**expected, 'started_at_utc': 'not-a-timestamp'},
    ):
        with pytest.raises(ValueError, match='Reconciliation'):
            runner.assert_same(actual, expected)


def test_reconciliation_mismatch_preserves_actual_and_dbt_success(
        config, expectations, tmp_path, monkeypatch):
    calls = []
    fake_build(monkeypatch, calls)
    client, client_setup = fake_reconciliation(expectations)
    client.results[0][0]['mart']['event_id'] = 'wrong:event'
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match=r'edition\[0\]\.mart\.event_id'):
        runner.execute(config, expectations, out, tmp_path, client_setup=client_setup)
    execution = json.loads((out / 'execution.json').read_text())
    evidence = json.loads((out / 'reconciliation/reconciliation.json').read_text())
    assert calls == ['edition', 'comparison']
    assert [stage['status'] for stage in execution['stages']] == ['passed', 'passed']
    assert execution['status'] == 'failed'
    assert execution['analytical_reconciliation'] == 'failed'
    assert evidence['status'] == 'failed'
    assert evidence['queries'][0]['actual_rows'][0]['mart']['event_id'] == 'wrong:event'
    assert len(client.queries) == 1
    assert client.closed


def test_query_failure_preserves_job_identity(config, expectations, tmp_path, monkeypatch):
    calls = []
    fake_build(monkeypatch, calls)
    client, client_setup = fake_reconciliation(expectations)

    class FailedJob(FakeJob):
        def result(self, **kwargs):
            raise TimeoutError('bounded query timeout')

    def failed_query(sql, **kwargs):
        client.queries.append(('edition', sql, kwargs['job_config']))
        return FailedJob('edition', [])

    client.query = failed_query
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='bounded query timeout'):
        runner.execute(config, expectations, out, tmp_path, client_setup=client_setup)
    evidence = json.loads((out / 'reconciliation/reconciliation.json').read_text())
    assert evidence['queries'][0]['job_id'] == 'edition-job'
    assert evidence['queries'][0]['status'] == 'failed'
    assert evidence['queries'][0]['bytes_billed'] == 10485760
    assert evidence['queries'][0]['errors'] is None
    assert client.closed
