"""Run the existing edition and comparison builds with explicit configuration.

Standard-library only: usable locally and in the locked dbt image. Preview is
credential-free; --execute invokes dbt using the process's existing credentials.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


FIELDS = {
    'project', 'source_dataset', 'source_table', 'edition_dataset',
    'comparison_dataset', 'comparison_datasets', 'comparison_baseline', 'top_n',
}
MODELS = {
    'edition': {'model.runwx.stg_race_results', 'model.runwx.fct_race_results',
                'model.runwx.mart_event_summary'},
    'comparison': {'model.runwx.mart_course_comparison'},
}


def validate_config(config):
    if not isinstance(config, dict) or set(config) != FIELDS:
        raise ValueError('Configuration must contain exactly: ' + ', '.join(sorted(FIELDS)))
    project = config['project']
    if not isinstance(project, str) or not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project):
        raise ValueError('Invalid project ID')
    datasets = config['comparison_datasets']
    if not isinstance(datasets, list) or len(datasets) < 2:
        raise ValueError('comparison_datasets must list at least two explicit editions')
    identifiers = [config[k] for k in FIELDS - {'project', 'comparison_datasets', 'top_n'}] + datasets
    if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,1023}', v) for v in identifiers):
        raise ValueError('Invalid dataset or table identifier')
    if len(set(datasets)) != len(datasets):
        raise ValueError('Duplicate comparison dataset')
    if config['edition_dataset'] not in datasets or config['comparison_baseline'] not in datasets:
        raise ValueError('Comparison must include the built edition and the baseline')
    if config['source_dataset'] in {config['edition_dataset'], config['comparison_dataset']}:
        raise ValueError('Output datasets must differ from the source dataset')
    if config['comparison_dataset'] in datasets and config['comparison_dataset'] != config['edition_dataset']:
        raise ValueError('Comparison output cannot write into another edition dataset')
    if type(config['top_n']) is not int or config['top_n'] < 1:
        raise ValueError('top_n must be a positive integer')
    return config


def build_plan(config, output_dir, project_dir):
    validate_config(config)
    output_dir, project_dir = Path(output_dir).resolve(), Path(project_dir).resolve()
    plans = []
    for stage in ('edition', 'comparison'):
        variables = {'source_dataset': config['source_dataset'],
                     'source_table': config['source_table'], 'top_n': config['top_n']}
        if stage == 'comparison':
            variables.update({key: config[key] for key in ('comparison_datasets', 'comparison_baseline')})
        folder = output_dir / stage
        command = ['dbt', '--no-partial-parse', '--write-json', 'build',
                   '--project-dir', str(project_dir), '--profiles-dir', str(project_dir),
                   '--target', 'cloud', '--target-path', str(folder / 'target'),
                   '--log-path', str(folder / 'logs'), '--vars', json.dumps(variables, sort_keys=True)]
        command += ['--select', 'tag:comparison'] if stage == 'comparison' else ['--exclude', 'tag:comparison']
        plans.append({'stage': stage, 'command': command, 'directory': str(folder),
                      'environment': {'RUNWX_DBT_PROJECT': config['project'],
                                      'RUNWX_DBT_DATASET': config[stage + '_dataset']}})
    return plans


def verify_artifacts(folder, stage):
    target = Path(folder) / 'target'
    manifest = json.loads((target / 'manifest.json').read_text())
    results = json.loads((target / 'run_results.json').read_text())
    invocation = results['metadata']['invocation_id']
    if not invocation or invocation != manifest['metadata']['invocation_id']:
        raise ValueError('Artifact invocation IDs disagree')
    nodes = {**manifest['nodes'], **manifest.get('unit_tests', {})}

    def comparison_node(uid, seen=None):
        seen = set() if seen is None else seen
        if uid in seen or uid not in nodes:
            return False
        seen.add(uid)
        node = nodes[uid]
        return 'comparison' in (node.get('tags') or []) or any(
            comparison_node(parent, seen) for parent in node.get('depends_on', {}).get('nodes', []))

    expected = {
        uid for uid, node in nodes.items()
        if node['resource_type'] in {'model', 'test', 'unit_test'}
        and node.get('config', {}).get('materialized') != 'ephemeral'
        and comparison_node(uid) == (stage == 'comparison')
    }
    expected_models = {uid for uid in expected if uid.startswith('model.')}
    # These counts describe this locked project's existing test contract, not
    # arbitrary dbt projects. Missing tests must not look like successful builds.
    expected_counts = (3, 14, 7) if stage == 'edition' else (1, 5, 2)
    counts = tuple(sum(uid.startswith(prefix) for uid in expected)
                   for prefix in ('model.', 'test.', 'unit_test.'))
    if expected_models != MODELS[stage] or counts != expected_counts:
        raise ValueError('Manifest does not contain the established model/test contract')
    rows = results['results']
    if len(rows) != len(expected) or {r['unique_id'] for r in rows} != expected:
        raise ValueError('Build results omit or repeat expected nodes')
    for row in rows:
        wanted = 'success' if row['unique_id'].startswith('model.') else 'pass'
        if row['status'] != wanted:
            raise ValueError('Unsuccessful dbt result: ' + row['unique_id'])
    return {'invocation_id': invocation, 'models': counts[0],
            'data_tests': counts[1], 'unit_tests': counts[2]}


def execute(config, output_dir, project_dir):
    plans = build_plan(config, output_dir, project_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    record = {'status': 'running', 'config': config, 'stages': [],
              'analytical_reconciliation': 'not_performed'}
    record_path = output_dir / 'execution.json'
    try:
        for plan in plans:
            folder = Path(plan['directory'])
            folder.mkdir()
            stage = {'stage': plan['stage'], 'status': 'running', 'command': plan['command']}
            record['stages'].append(stage)
            record_path.write_text(json.dumps(record, indent=2) + '\n')
            env = os.environ.copy()
            # Prevent inherited dbt flags from suppressing tests/artifacts or
            # substituting a different selection/profile. Auth env stays intact.
            env = {k: v for k, v in env.items() if not k.startswith('DBT_')}
            env.update(plan['environment'])
            env['DBT_SEND_ANONYMOUS_USAGE_STATS'] = 'false'
            with (folder / 'console.log').open('w') as log:
                result = subprocess.run(plan['command'], env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=1800, check=False)
            stage['returncode'] = result.returncode
            if result.returncode:
                raise ValueError(f"{plan['stage']} dbt build exited {result.returncode}")
            stage.update(verify_artifacts(folder, plan['stage']))
            stage['status'] = 'passed'
        record['status'] = 'builds_passed'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        record['status'] = 'failed'
        if record['stages']:
            record['stages'][-1]['status'] = 'failed'
        record['error'] = str(exc)
        raise
    finally:
        record_path.write_text(json.dumps(record, indent=2) + '\n')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New execution directory; never reused')
    parser.add_argument('--project-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text())
        result = execute(config, args.output_dir, args.project_dir) if args.execute else {
            'status': 'preview', 'stages': build_plan(config, args.output_dir, args.project_dir)}
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f'dbt stage failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
