"""Independent dbt artifacts and warehouse summaries for batch boundary tests."""

import json
from pathlib import Path


def dbt_artifacts(folder, stage):
    models = ['mart_gnr_edition_summary', 'mart_gnr_sample_comparison']
    nodes = {f'model.runwx.{name}': {'resource_type': 'model',
                                   'config': {'materialized': 'table' if i == 0 else 'view'}}
             for i, name in enumerate(models)}
    for model, columns in [(models[0], ['snapshot_table', 'event_id']), (models[1], ['snapshot_table'])]:
        for column in columns:
            for check in ['not_null', 'unique']:
                uid = f'test.runwx.{check}_{model}_{column}'
                nodes[uid] = {'resource_type': 'test', 'depends_on': {'nodes': [f'model.runwx.{model}']}}
    nodes['test.runwx.accepted_status'] = {'resource_type': 'test',
                                         'depends_on': {'nodes': ['model.runwx.'+models[1]]}}
    nodes['test.runwx.gnr_edition_reconcile'] = {'resource_type': 'test',
                                              'depends_on': {'nodes': ['model.runwx.'+models[0]]}}
    nodes['test.runwx.gnr_comparison_reconcile'] = {'resource_type': 'test',
                                                 'depends_on': {'nodes': ['model.runwx.'+m for m in models]}}
    units = {'unit_test.runwx.mart_gnr_sample_comparison.incompatible': {
        'resource_type': 'unit_test', 'depends_on': {'nodes': ['model.runwx.'+models[1]]}}}
    selected = ('model.runwx.'+models[0] if stage == 'gnr_edition' else 'model.runwx.'+models[1])
    results = [{'unique_id': selected, 'status': 'success'}]
    for uid, node in {**nodes, **units}.items():
        if selected in node.get('depends_on', {}).get('nodes', []):
            if stage == 'gnr_edition' and uid == 'test.runwx.gnr_comparison_reconcile':
                continue
            results.append({'unique_id': uid, 'status': 'pass'})
    folder = Path(folder)
    folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps({'metadata': {'invocation_id': stage},
                                                   'nodes': nodes, 'unit_tests': units}))
    (folder/'run_results.json').write_text(json.dumps({'metadata': {'invocation_id': stage},
                                                      'results': results}))


def uniform_inputs(config_path):
    """Known distributions: 2019 has 1,000 x 70min, 2022 has 1,000 x 80min."""
    from hashlib import sha256

    config = json.loads(config_path.read_text())
    config['analytics'] = {'dataset': 'runwx_dbt_gnr_test', 'baseline_year': 2019}
    config_path.write_text(json.dumps(config))
    for year, minutes in [(2019, 10), (2022, 20)]:
        path = config_path.parent / str(year) / 'race.json'
        data = json.loads(path.read_text())
        # Both source pages must extend beyond the selected cutoff.
        for group in ('resultMen', 'resultWomen'):
            for index, row in enumerate(data[group]):
                row['timeFinish'] = f'{1 if index < 500 else 2:02}:{minutes}:00'
        path.write_text(json.dumps(data))
        capture_path = Path(str(path)+'.capture.json')
        capture = json.loads(capture_path.read_text())
        capture.update(sha256=sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
        capture_path.write_text(json.dumps(capture))


def warehouse_summaries(tables, comparison=False):
    """Hand-known fixture results, independent of the production expectation builder."""
    result = []
    for table, rows in sorted(tables.items()):
        first = rows[0]
        duration = 4200.0 if first['race_date'].startswith('2019') else 4800.0
        row = {key: first[key] for key in ('export_schema', 'event_id', 'race_date', 'course_id',
               'distance_m', 'distance_basis', 'race_kind', 'weather_kind', 'race_sha256',
               'categories_sha256', 'weather_sha256', 'weather_request_sha256')}
        row.update(snapshot_table=table, sample_label=first['sample']['label'],
                   sample_note=first['sample']['note'], sample_selection=first['sample']['selection'],
                   declared_sample_size=1000, source_count=2000, excluded_count=0,
                   timing_note=first['sample']['timing_note'],
                   weather_context_basis='fixed_event_window', weather_context_note=first['weather_context']['note'],
                   weather_start_local='10:00', weather_end_local='14:00', median_temp_c=12.0,
                   median_wind_mps=2.0, median_humidity_pct=60.0, precipitation_mm=0.0,
                   sample_size=1000, distinct_source_rows=1000, distinct_sample_ranks=1000,
                   min_sample_rank=1, max_sample_rank=1000, distinct_contexts=1,
                   chip_count=1000, gun_count=0, unknown_count=0, best_duration_s=int(duration),
                   mean_duration_s=duration, duration_p25_s=duration, median_duration_s=duration,
                   duration_p75_s=duration, top_n_median_duration_s=duration,
                   mean_pace_s_per_km=duration/21.1, median_pace_s_per_km=duration/21.1,
                   pace_p25_s_per_km=duration/21.1, pace_p75_s_per_km=duration/21.1,
                   top_n_median_pace_s_per_km=duration/21.1, top_n_requested=20, top_n_effective=20)
        if comparison:
            row.update(baseline_event_id='greatrun:881', baseline_median_pace_s_per_km=4200/21.1,
                       comparison_status='descriptive_sample',
                       median_pace_difference_s_per_km=(duration-4200)/21.1,
                       median_pace_change_pct=(0.0 if duration == 4200 else 100/7))
        result.append(row)
    return result
