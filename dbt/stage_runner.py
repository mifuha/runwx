"""Run the existing edition and comparison builds with explicit configuration.

Preview uses only the standard library. Execution uses the locked dbt and BigQuery
client dependencies with the process's existing credentials.
"""
import argparse
from datetime import datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys


FIELDS = {
    'project', 'location', 'source_dataset', 'source_table', 'edition_dataset',
    'comparison_dataset', 'comparison_datasets', 'comparison_baseline', 'top_n',
}
MODELS = {
    'edition': {'model.runwx.stg_race_results', 'model.runwx.fct_race_results',
                'model.runwx.mart_event_summary'},
    'comparison': {'model.runwx.mart_course_comparison'},
    'gnr_edition': {'model.runwx.mart_gnr_edition_summary'},
    'gnr_comparison': {'model.runwx.mart_gnr_sample_comparison'},
}


def validate_config(config):
    if not isinstance(config, dict) or set(config) != FIELDS:
        raise ValueError('Configuration must contain exactly: ' + ', '.join(sorted(FIELDS)))
    project = config['project']
    if not isinstance(project, str) or not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project):
        raise ValueError('Invalid project ID')
    if not isinstance(config['location'], str) or not re.fullmatch(
            r'[A-Za-z][A-Za-z0-9-]{0,63}', config['location']):
        raise ValueError('Invalid BigQuery location')
    datasets = config['comparison_datasets']
    if not isinstance(datasets, list) or len(datasets) < 2:
        raise ValueError('comparison_datasets must list at least two explicit editions')
    identifier_keys = {
        'source_dataset', 'source_table', 'edition_dataset',
        'comparison_dataset', 'comparison_baseline',
    }
    identifiers = [config[k] for k in identifier_keys] + datasets
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


def validate_expectations(expectations, config):
    if not isinstance(expectations, dict) or set(expectations) != {'edition', 'comparison'}:
        raise ValueError('Expectations must contain exactly edition and comparison')
    edition = expectations['edition']
    if (not isinstance(edition, dict) or set(edition) != {'mart', 'weather'}
            or not all(isinstance(value, dict) and value for value in edition.values())):
        raise ValueError('Edition expectation must contain non-empty mart and weather objects')
    comparison = expectations['comparison']
    if (not isinstance(comparison, list) or len(comparison) != len(config['comparison_datasets'])
            or any(not isinstance(row, dict) or not row for row in comparison)):
        raise ValueError('Comparison expectations must contain one object per dataset')
    validate_expected_value(expectations)
    expected_datasets = [row.get('snapshot_dataset') for row in comparison]
    if (not all(isinstance(dataset, str) for dataset in expected_datasets)
            or len(set(expected_datasets)) != len(expected_datasets)
            or set(expected_datasets) != set(config['comparison_datasets'])):
        raise ValueError('Comparison expectations must identify every configured dataset once')
    return expectations


def validate_expected_value(value, path='$'):
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f'Expectation contains a non-string key at {path}')
        for key, child in value.items():
            validate_expected_value(child, f'{path}.{key}')
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            validate_expected_value(child, f'{path}[{index}]')
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'Expectation contains a non-finite number at {path}')
    if path.endswith('.started_at_utc'):
        if not isinstance(value, str):
            raise ValueError(f'Expectation contains a non-string timestamp at {path}')
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError(f'Expectation contains an invalid timestamp at {path}') from exc
        if parsed.tzinfo is None:
            raise ValueError(f'Expectation contains a naive timestamp at {path}')
    if value is not None and type(value) not in {bool, int, float, str}:
        raise ValueError(f'Expectation contains an unsupported value at {path}')


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def assert_same(actual, expected, path='$'):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(f'Reconciliation structure mismatch at {path}')
        for key, value in expected.items():
            assert_same(actual[key], value, f'{path}.{key}')
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f'Reconciliation list mismatch at {path}')
        for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
            assert_same(left, right, f'{path}[{index}]')
        return
    if path.endswith('.started_at_utc') and isinstance(actual, str) and isinstance(expected, str):
        try:
            left = datetime.fromisoformat(actual.replace('Z', '+00:00'))
            right = datetime.fromisoformat(expected.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError(f'Reconciliation value mismatch at {path}') from exc
        if left.tzinfo is None or right.tzinfo is None or left != right:
            raise ValueError(f'Reconciliation value mismatch at {path}')
        return
    if isinstance(expected, float):
        if (isinstance(actual, bool) or not isinstance(actual, (int, float))
                or not math.isfinite(actual)
                or not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9)):
            raise ValueError(f'Reconciliation value mismatch at {path}')
        return
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError(f'Reconciliation value mismatch at {path}')


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
        command = [sys.executable, '-m', 'dbt.cli.main',
                   '--no-partial-parse', '--write-json', 'build',
                   '--project-dir', str(project_dir), '--profiles-dir', str(project_dir),
                   '--target', 'cloud', '--target-path', str(folder / 'target'),
                   '--log-path', str(folder / 'logs'), '--vars', json.dumps(variables, sort_keys=True)]
        command += ['--select', 'tag:comparison'] if stage == 'comparison' else ['--exclude', 'tag:comparison']
        plans.append({'stage': stage, 'command': command, 'directory': str(folder),
                      'environment': {'RUNWX_DBT_PROJECT': config['project'],
                                      'RUNWX_DBT_DATASET': config[stage + '_dataset']}})
    return plans


def build_reconciliation_plan(config, expectations):
    validate_config(config)
    validate_expectations(expectations, config)
    project = config['project']
    edition = f"`{project}.{config['edition_dataset']}"
    comparison = f"`{project}.{config['comparison_dataset']}"
    edition_sql = f"""with matched_weather as (
    select
        percentile_cont(weather_temp_c, 0.5) over () as median_temp_c,
        percentile_cont(weather_wind_mps, 0.5) over () as median_wind_mps,
        percentile_cont(weather_precipitation_mm, 0.5) over () as median_precipitation_mm,
        percentile_cont(weather_humidity_pct, 0.5) over () as median_humidity_pct
    from {edition}.fct_race_results`
    where weather_match_status = 'matched'
), weather_summary as (
    select count(*) as enriched_count,
        max(median_temp_c) as median_temp_c,
        max(median_wind_mps) as median_wind_mps,
        max(median_precipitation_mm) as median_precipitation_mm,
        max(median_humidity_pct) as median_humidity_pct
    from matched_weather
)
select to_json_string(struct(m as mart, w as weather)) as row_json
from {edition}.mart_event_summary` as m
cross join weather_summary as w
limit 2
"""
    comparison_limit = len(expectations['comparison']) + 1
    comparison_sql = f"""select to_json_string(t) as row_json
from {comparison}.mart_course_comparison` as t
order by snapshot_dataset
limit {comparison_limit}
"""
    return [
        {'stage': 'edition', 'sql': edition_sql, 'expected': [expectations['edition']]},
        {'stage': 'comparison', 'sql': comparison_sql,
         'expected': sorted(expectations['comparison'], key=lambda row: row['snapshot_dataset'])},
    ]


def create_bigquery_client(config):
    from google.cloud import bigquery

    client = bigquery.Client(project=config['project'], location=config['location'])
    job_config = bigquery.QueryJobConfig(
        use_legacy_sql=False,
        use_query_cache=False,
        maximum_bytes_billed=104857600,
        job_timeout_ms=300000,
    )
    return client, job_config


def query_metadata(job):
    return {
        'bytes_processed': job.total_bytes_processed,
        'bytes_billed': job.total_bytes_billed,
        'cache_hit': job.cache_hit,
        'errors': job.errors,
    }


def reconcile(config, expectations, output_dir, client_setup=create_bigquery_client):
    plans = build_reconciliation_plan(config, expectations)
    return execute_reconciliation(plans, expectations, config, output_dir, client_setup)


def execute_reconciliation(plans, expectations, config, output_dir,
                           client_setup=create_bigquery_client):
    """Run bounded readbacks against independently prepared expected values."""
    folder = Path(output_dir) / 'reconciliation'
    folder.mkdir()
    expected_text = canonical_json(expectations)
    record = {
        'status': 'running',
        'expectations_sha256': sha256(expected_text.encode()).hexdigest(),
        'queries': [],
    }
    record_path = folder / 'reconciliation.json'
    client = None
    try:
        client, job_config = client_setup(config)
        for plan in plans:
            (folder / f"{plan['stage']}.sql").write_text(plan['sql'])
            query = {
                'stage': plan['stage'],
                'status': 'running',
                'sql_sha256': sha256(plan['sql'].encode()).hexdigest(),
            }
            record['queries'].append(query)
            record_path.write_text(json.dumps(record, indent=2) + '\n')
            job = client.query(
                plan['sql'],
                job_config=job_config,
                location=config['location'],
                retry=None,
                job_retry=None,
                timeout=30,
            )
            query['job_id'] = job.job_id
            try:
                rows = [
                    json.loads(row['row_json'])
                    for row in job.result(
                        timeout=300,
                        retry=None,
                        job_retry=None,
                        max_results=len(plan['expected']) + 1,
                    )
                ]
            except Exception:
                query.update(query_metadata(job))
                record_path.write_text(json.dumps(record, indent=2) + '\n')
                raise
            query.update({
                'actual_rows': rows,
                **query_metadata(job),
            })
            record_path.write_text(json.dumps(record, indent=2) + '\n')
            assert_same(rows, plan['expected'], f"$.{plan['stage']}")
            query['status'] = 'passed'
        record['status'] = 'reconciled'
        return record
    except Exception as exc:
        record['status'] = 'failed'
        if record['queries']:
            record['queries'][-1]['status'] = 'failed'
        record['error'] = str(exc)
        raise ValueError(f'Reconciliation failed: {exc}') from exc
    finally:
        record_path.write_text(json.dumps(record, indent=2) + '\n')
        if client is not None:
            client.close()


def verify_artifacts(folder, stage):
    target = Path(folder) / 'target'
    manifest = json.loads((target / 'manifest.json').read_text())
    results = json.loads((target / 'run_results.json').read_text())
    invocation = results['metadata']['invocation_id']
    if not invocation or invocation != manifest['metadata']['invocation_id']:
        raise ValueError('Artifact invocation IDs disagree')
    nodes = {**manifest['nodes'], **manifest.get('unit_tests', {})}
    # dbt can retain generic tests for disabled models in manifest nodes.
    nodes = {uid: node for uid, node in nodes.items()
             if node.get('config', {}).get('enabled', True)}

    def comparison_node(uid, seen=None):
        seen = set() if seen is None else seen
        if uid in seen or uid not in nodes:
            return False
        seen.add(uid)
        node = nodes[uid]
        return 'comparison' in (node.get('tags') or []) or any(
            comparison_node(parent, seen) for parent in node.get('depends_on', {}).get('nodes', []))

    if stage.startswith('gnr_'):
        models = MODELS[stage]
        if not models <= nodes.keys():
            raise ValueError('Manifest is missing an expected GNR model')
        expected = models | {
            uid for uid, node in nodes.items()
            if node['resource_type'] in {'test', 'unit_test'}
            and models.intersection(node.get('depends_on', {}).get('nodes', []))
            and (stage != 'gnr_edition' or uid != 'test.runwx.gnr_comparison_reconcile')
        }
    else:
        expected = {
            uid for uid, node in nodes.items()
            if node['resource_type'] in {'model', 'test', 'unit_test'}
            and node.get('config', {}).get('materialized') != 'ephemeral'
            and comparison_node(uid) == (stage == 'comparison')
        }
    expected_models = {uid for uid in expected if uid.startswith('model.')}
    # These counts describe this locked project's existing test contract, not
    # arbitrary dbt projects. Missing tests must not look like successful builds.
    expected_counts = {'edition': (3, 14, 7), 'comparison': (1, 5, 2),
                       'gnr_edition': (1, 5, 0), 'gnr_comparison': (1, 4, 1)}[stage]
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


def execute_build(plan, stage):
    """Run one build and verify its artifacts; shared by local and DAG runners."""
    folder = Path(plan['directory'])
    folder.mkdir()
    # Keep authentication, but discard flags that could change the reviewed build.
    env = {k: v for k, v in os.environ.items() if not k.startswith('DBT_')}
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


def execute(config, expectations, output_dir, project_dir, client_setup=create_bigquery_client):
    plans = build_plan(config, output_dir, project_dir)
    validate_expectations(expectations, config)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    expected_text = canonical_json(expectations)
    (output_dir / 'expectations.json').write_text(expected_text + '\n')
    record = {'status': 'running', 'config': config, 'stages': [],
              'expectations_sha256': sha256(expected_text.encode()).hexdigest(),
              'reconciliation_evidence': 'reconciliation/reconciliation.json',
              'analytical_reconciliation': 'not_performed'}
    record_path = output_dir / 'execution.json'
    phase = 'dbt'
    try:
        for plan in plans:
            stage = {'stage': plan['stage'], 'status': 'running', 'command': plan['command']}
            record['stages'].append(stage)
            record_path.write_text(json.dumps(record, indent=2) + '\n')
            execute_build(plan, stage)
        record['status'] = 'builds_passed'
        record_path.write_text(json.dumps(record, indent=2) + '\n')
        phase = 'reconciliation'
        reconciliation = reconcile(
            config, expectations, output_dir, client_setup=client_setup)
        record['reconciliation'] = {
            'status': reconciliation['status'],
            'expectations_sha256': reconciliation['expectations_sha256'],
            'queries': [
                {key: query[key] for key in (
                    'stage', 'status', 'sql_sha256', 'job_id',
                    'bytes_processed', 'bytes_billed', 'cache_hit', 'errors')}
                for query in reconciliation['queries']
            ],
        }
        record['analytical_reconciliation'] = 'passed'
        record['status'] = 'reconciled'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        record['status'] = 'failed'
        if phase == 'dbt' and record['stages']:
            record['stages'][-1]['status'] = 'failed'
        if phase == 'reconciliation':
            record['analytical_reconciliation'] = 'failed'
        record['error'] = str(exc)
        raise
    finally:
        record_path.write_text(json.dumps(record, indent=2) + '\n')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--expectations', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New execution directory; never reused')
    parser.add_argument('--project-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text())
        expectations = json.loads(args.expectations.read_text())
        validate_expectations(expectations, validate_config(config))
        result = execute(config, expectations, args.output_dir, args.project_dir) if args.execute else {
            'status': 'preview',
            'expectations_sha256': sha256(canonical_json(expectations).encode()).hexdigest(),
            'stages': build_plan(config, args.output_dir, args.project_dir),
            'reconciliation': [
                {'stage': plan['stage'], 'sql': plan['sql']}
                for plan in build_reconciliation_plan(config, expectations)
            ],
        }
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f'dbt stage failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
