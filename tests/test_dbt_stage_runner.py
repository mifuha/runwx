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
    return dict(project='runwx-example', source_dataset='staging', source_table='snapshot_a',
                edition_dataset='edition_a', comparison_dataset='edition_a',
                comparison_datasets=['edition_a', 'edition_b'], comparison_baseline='edition_a', top_n=20)


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


def test_preview_has_no_execution_or_files(config, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: pytest.fail('preview invoked dbt'))
    file = tmp_path / 'config.json'
    file.write_text(json.dumps(config))
    out = tmp_path / 'out'
    assert runner.main(['--config', str(file), '--output-dir', str(out)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['status'] == 'preview'
    assert [s['stage'] for s in plan['stages']] == ['edition', 'comparison']
    assert not out.exists()
    for stage in plan['stages']:
        cmd = stage['command']
        assert cmd[:3] == [sys.executable, '-m', 'dbt.cli.main']
        variables = json.loads(cmd[cmd.index('--vars') + 1])
        assert variables['source_table'] == 'snapshot_a'
        assert variables['top_n'] == 20
    assert plan['stages'][1]['command'][-2:] == ['--select', 'tag:comparison']


@pytest.mark.parametrize('change', [
    {'project': None}, {'project': 'bad;command'}, {'top_n': True}, {'top_n': 0},
    {'comparison_datasets': 'edition_a'}, {'comparison_datasets': ['edition_a', 'edition_a']},
    {'comparison_baseline': 'missing'}, {'edition_dataset': 'missing'},
    {'source_table': 'x;drop'}, {'edition_dataset': 'staging'},
    {'comparison_dataset': 'edition_b'}, {'surprise': 1},
])
def test_invalid_config_stops_before_execution(config, change, tmp_path, monkeypatch):
    config.update(change)
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: pytest.fail('invalid config invoked dbt'))
    with pytest.raises(ValueError):
        runner.execute(config, tmp_path / 'out', tmp_path)
    assert not (tmp_path / 'out').exists()


def test_success_retains_both_artifacts(config, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv('DBT_SELECT', 'nothing')
    fake_build(monkeypatch, calls)
    out = tmp_path / 'out'
    record = runner.execute(config, out, tmp_path)
    assert calls == ['edition', 'comparison']
    assert record['status'] == 'builds_passed'
    assert record['analytical_reconciliation'] == 'not_performed'
    assert [s['unit_tests'] + s['data_tests'] for s in record['stages']] == [21, 7]
    assert [s['invocation_id'] for s in record['stages']] == ['edition', 'comparison']
    for stage in calls:
        assert (out / stage / 'target/manifest.json').exists()
        assert (out / stage / 'console.log').read_text() == 'build diagnostics\n'
    with pytest.raises(FileExistsError):
        runner.execute(config, out, tmp_path)
    assert calls == ['edition', 'comparison']


@pytest.mark.parametrize('problem', ['fail', 'skip', 'warn', 'missing', 'duplicate', 'invocation', 'no_artifact', 'manifest'])
def test_bad_edition_evidence_blocks_comparison(config, tmp_path, monkeypatch, problem):
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
        runner.execute(config, out, tmp_path)
    assert calls == ['edition']
    assert json.loads((out / 'execution.json').read_text())['status'] == 'failed'
    assert (out / 'edition/console.log').exists()
    assert not (out / 'comparison').exists()


@pytest.mark.parametrize('timeout', [False, True])
def test_process_failure_blocks_comparison(config, tmp_path, monkeypatch, timeout):
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        kwargs['stdout'].write('failure details')
        if timeout:
            raise subprocess.TimeoutExpired(cmd, 1800)
        return subprocess.CompletedProcess(cmd, 1)
    monkeypatch.setattr(runner.subprocess, 'run', run)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        runner.execute(config, tmp_path / 'out', tmp_path)
    assert len(calls) == 1
    assert json.loads((tmp_path / 'out/execution.json').read_text())['status'] == 'failed'


def test_comparison_failure_preserves_edition_success(config, tmp_path, monkeypatch):
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
        runner.execute(config, out, tmp_path)
    record = json.loads((out / 'execution.json').read_text())
    assert calls == ['edition', 'comparison']
    assert [stage['status'] for stage in record['stages']] == ['passed', 'failed']
    assert record['status'] == 'failed'
    assert (out / 'edition/target/run_results.json').exists()


def test_missing_configuration_field(config, tmp_path, monkeypatch):
    del config['source_table']
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: pytest.fail('missing source invoked dbt'))
    with pytest.raises(ValueError, match='exactly'):
        runner.execute(config, tmp_path / 'out', tmp_path)
