"""Build the existing GNR marts once per batch, locally or from Airflow tasks."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean
import sys
from time import monotonic

import stage_runner
from runwx.services.gnr_batch import _read_prepared, _write_json


def expected_editions(loads):
    """Independent Python calculations from validated exports, never warehouse output."""
    expected = []
    for load in loads:
        rows = load.rows
        first, sample, weather = rows[0], rows[0]['sample'], rows[0]['weather_context']
        durations = sorted(row['duration_s'] for row in rows)
        timing = Counter(row['timing_basis'] for row in rows)

        def percentile(values, p):
            index = (len(values) - 1) * p
            lower, upper = math.floor(index), math.ceil(index)
            return float(values[lower] + (values[upper] - values[lower]) * (index - lower))

        item = {key: first[key] for key in (
            'export_schema', 'event_id', 'race_date', 'course_id', 'distance_m',
            'distance_basis', 'race_kind', 'weather_kind', 'race_sha256',
            'categories_sha256', 'weather_sha256', 'weather_request_sha256')}
        item.update({
            'snapshot_table': load.table_id, 'sample_label': sample['label'],
            'sample_note': sample['note'], 'sample_selection': sample['selection'],
            'declared_sample_size': sample['size'], 'source_count': sample['source_count'],
            'excluded_count': sample['excluded_count'], 'timing_note': sample['timing_note'],
            'weather_context_basis': weather['basis'], 'weather_context_note': weather['note'],
            'weather_start_local': weather['start_local'], 'weather_end_local': weather['end_local'],
            **{key: weather[key] for key in ('median_temp_c', 'median_wind_mps',
                                             'median_humidity_pct', 'precipitation_mm')},
            'sample_size': len(rows),
            'distinct_source_rows': len({row['source_row_id'] for row in rows}),
            'distinct_sample_ranks': len({row['sample_rank'] for row in rows}),
            'min_sample_rank': min(row['sample_rank'] for row in rows),
            'max_sample_rank': max(row['sample_rank'] for row in rows),
            'distinct_contexts': 1,  # Complete preflight already requires one context.
            'chip_count': timing['chip'], 'gun_count': timing['gun'], 'unknown_count': timing['unknown'],
            'best_duration_s': durations[0], 'mean_duration_s': float(mean(durations)),
            'duration_p25_s': percentile(durations, .25),
            'median_duration_s': percentile(durations, .5),
            'duration_p75_s': percentile(durations, .75),
            'top_n_median_duration_s': percentile(durations[:20], .5),
            'top_n_requested': 20, 'top_n_effective': min(20, len(rows)),
        })
        for pace, duration in (
                ('mean_pace_s_per_km', 'mean_duration_s'),
                ('median_pace_s_per_km', 'median_duration_s'),
                ('pace_p25_s_per_km', 'duration_p25_s'),
                ('pace_p75_s_per_km', 'duration_p75_s'),
                ('top_n_median_pace_s_per_km', 'top_n_median_duration_s')):
            item[pace] = item[duration] / (first['distance_m'] / 1000)
        expected.append(item)
    return sorted(expected, key=lambda row: row['snapshot_table'])


def _validated(plan_path, output_dir):
    plan, loads, digest = _read_prepared(Path(plan_path).resolve())
    if (plan.analytics is None or len(plan.editions) < 2
            or plan.analytics.baseline_year not in {e.year for e in plan.editions}):
        raise ValueError('GNR analysis needs a configured dataset and baseline in the complete batch')
    record = json.loads((Path(output_dir) / 'execution.json').read_text())
    if (record.get('snapshot_status', record['status']) != 'loaded_verified'
            or record['plan_sha256'] != digest
            or [(e['year'], e['table_id']) for e in record['editions']]
            != [(e.year, e.table_id) for e in plan.editions]
            or any(e['status'] not in {'loaded_verified', 'already_present_verified'}
                   for e in record['editions'])):
        raise ValueError('every required snapshot must be loaded and verified for this exact plan')
    return plan, loads, record


def build_plan(plan, output_dir, project_dir, stage, dbt_python):
    if stage not in {'gnr_edition', 'gnr_comparison'}:
        raise ValueError('unknown GNR build stage')
    folder, project_dir = Path(output_dir).resolve() / stage, Path(project_dir).resolve()
    baseline = next(e for e in plan.editions if e.year == plan.analytics.baseline_year)
    variables = {'gnr_sample_tables': [e.table_id for e in plan.editions],
                 'gnr_baseline_event_id': baseline.summary['event_id'], 'top_n': 20}
    selection = (['mart_gnr_edition_summary'] if stage == 'gnr_edition'
                 else ['mart_gnr_sample_comparison', 'gnr_comparison_reconcile'])
    command = [str(Path(dbt_python).absolute()), '-m', 'dbt.cli.main',
               '--no-partial-parse', '--write-json', 'build',
               '--project-dir', str(project_dir), '--profiles-dir', str(project_dir),
               '--target', 'cloud', '--target-path', str(folder / 'target'),
               '--log-path', str(folder / 'logs'), '--vars', json.dumps(variables, sort_keys=True),
               '--indirect-selection', 'cautious', '--select', *selection]
    return {'stage': stage, 'command': command, 'directory': str(folder),
            'environment': {'RUNWX_DBT_PROJECT': plan.project,
                            'RUNWX_DBT_DATASET': plan.analytics.dataset,
                            'RUNWX_DBT_MAXIMUM_BYTES_BILLED': str(plan.analytics.maximum_bytes_billed)}}


def run_stage(plan_path, output_dir, project_dir, stage, *, dbt_python=sys.executable,
              client_setup=stage_runner.create_bigquery_client):
    """One reusable task boundary. Failure retains evidence and prevents the next stage."""
    output_dir = Path(output_dir)
    record_path = output_dir / 'execution.json'
    record = json.loads(record_path.read_text())
    started = monotonic()
    current = {'stage': stage, 'status': 'running'}
    try:
        plan, loads, record = _validated(plan_path, output_dir)
        preceding = {'gnr_edition': [], 'gnr_comparison': ['gnr_edition'],
                     'reconciliation': ['gnr_edition', 'gnr_comparison']}[stage]
        if [(s['stage'], s['status']) for s in record.get('analytical_stages', [])] != [
                (name, 'passed') for name in preceding]:
            raise ValueError('earlier analytical stages must pass once, in order')
        record['snapshot_status'] = 'loaded_verified'
        record['status'] = 'running'
        record['stage'] = stage
        record['analytical_status'] = 'running'
        record.setdefault('analytical_stages', []).append(current)
        _write_json(record_path, record)
        if stage != 'reconciliation':
            build = build_plan(plan, output_dir, project_dir, stage, dbt_python)
            current['command'] = build['command']
            stage_runner.execute_build(build, current)
        else:
            edition = expected_editions(loads)
            baseline_id = next(e.summary['event_id'] for e in plan.editions
                               if e.year == plan.analytics.baseline_year)
            baseline = next(row['median_pace_s_per_km'] for row in edition
                            if row['event_id'] == baseline_id)
            comparison = [{**row, 'baseline_event_id': baseline_id,
                           'baseline_median_pace_s_per_km': baseline,
                           'comparison_status': 'descriptive_sample',
                           'median_pace_difference_s_per_km': row['median_pace_s_per_km'] - baseline,
                           'median_pace_change_pct': 100 * (row['median_pace_s_per_km'] - baseline) / baseline}
                          for row in edition]
            expected = {'edition': edition, 'comparison': comparison}
            _write_json(output_dir / 'expectations.json', expected)
            queries = []
            for name, model in [('edition', 'mart_gnr_edition_summary'),
                                ('comparison', 'mart_gnr_sample_comparison')]:
                table = f'{plan.project}.{plan.analytics.dataset}.{model}'
                queries.append({'stage': name, 'sql': f'SELECT TO_JSON_STRING(t) AS row_json FROM `{table}` AS t ORDER BY snapshot_table LIMIT {len(edition)+1}',
                                'expected': expected[name]})
            result = stage_runner.execute_reconciliation(
                queries, expected, {'project': plan.project, 'location': plan.location},
                output_dir, client_setup=client_setup)
            current['status'] = 'passed'
            current['queries'] = [{k: q[k] for k in ('stage', 'status', 'job_id', 'sql_sha256')}
                                 for q in result['queries']]
            record.update(status='reconciled', stage='complete', analytical_status='passed')
        return {'stage': stage, 'status': 'passed', 'execution': str(record_path)}
    except Exception as exc:
        current.update(status='failed', error=str(exc))
        record.update(status='failed', analytical_status='failed', error=str(exc))
        if current not in record.get('analytical_stages', []):
            record.setdefault('analytical_stages', []).append(current)
        raise
    finally:
        current['elapsed_seconds'] = round(monotonic() - started, 3)
        finished = datetime.now(timezone.utc)
        record['finished_at_utc'] = finished.isoformat()
        record['elapsed_seconds'] = round(
            (finished - datetime.fromisoformat(record['started_at_utc'])).total_seconds(), 3)
        _write_json(record_path, record)


def execute(plan_path, output_dir, project_dir, *, dbt_python=sys.executable):
    for stage in ('gnr_edition', 'gnr_comparison', 'reconciliation'):
        run_stage(plan_path, output_dir, project_dir, stage, dbt_python=dbt_python)
    return json.loads((Path(output_dir) / 'execution.json').read_text())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--execution-dir', type=Path, required=True)
    parser.add_argument('--dbt-python', default=sys.executable)
    args = parser.parse_args()
    print(json.dumps(execute(args.plan, args.execution_dir, Path(__file__).parent,
                             dbt_python=args.dbt_python), indent=2))
