"""Offline performance-group extension of the preserved Berlin pilot."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import resource
from tempfile import TemporaryDirectory
from time import perf_counter

import pilot
from check_prepared import read_capture, histogram_median


def split(values, n):
    if type(n) is not int or n <= 0 or len(values) <= n:
        raise ValueError('each group needs more than N accepted captures')
    ordered = sorted(values)  # Stable: equal durations retain source order.
    return ordered[:n], ordered[n:]


def histogram_split(counts, n):
    if n <= 0 or sum(counts.values()) <= n:
        raise ValueError('independent histogram needs more than N captures')
    top, rest = Counter(), Counter()
    remaining = n
    for duration, count in sorted(counts.items()):
        take = min(remaining, count)
        if take:
            top[duration] = take
        if count - take:
            rest[duration] = count - take
        remaining -= take
    return top, rest


def describe(rows):
    result = {}
    for key in sorted({r['series'] for r in rows}):
        chosen = sorted([r for r in rows if r['series'] == key], key=lambda r:r['year'])
        if len(chosen) != 16 or [r['year'] for r in chosen] != list(pilot.YEARS):
            raise ValueError('each series must contain all 16 editions exactly once')
        def calc(selected):
            return pilot.pearson([r['median_temp_c'] for r in selected],
                                 [r['median_pace_s_per_km'] for r in selected])
        full = calc(chosen)
        omitted = [{'omitted_year':r['year'], 'edition_count':15,
                    **calc([q for q in chosen if q['year'] != r['year']])} for r in chosen]
        for value in omitted:
            value['delta_from_full'] = value['value']-full['value'] if value['value'] is not None and full['value'] is not None else None
        defined = [r for r in omitted if r['value'] is not None]
        result[key] = {'edition_count':16, 'pearson_r':full, 'leave_one_out':omitted,
            'leave_one_out_min':min((r['value'] for r in defined),default=None),
            'leave_one_out_max':max((r['value'] for r in defined),default=None),
            'direction_change_omissions':[r['omitted_year'] for r in defined if full['value'] is not None and pilot.direction(r['value']) != pilot.direction(full['value'])],
            'most_influential_omission':max(defined,key=lambda r:abs(r['delta_from_full'] or 0)) if defined else None}
    return {'unit':'edition', 'weather_contexts':16, 'series':result}


def run(configuration, output):
    start=perf_counter()
    output=Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('output exists; choose a fresh directory')
    config=json.loads(Path(configuration).read_bytes())
    if config['primary_n'] != 20 or config['sensitivity_n'] != 50 or config['years'] != list(pilot.YEARS) or config['recorded_genders'] != ['female','male']:
        raise ValueError('configuration differs from fixed extension')
    parent_path = Path(configuration).resolve().parent / config['parent_configuration']
    pilot.checked_bytes(parent_path, config['parent_configuration_sha256'], 'retained parent configuration')
    parent = pilot.load_configuration(parent_path)
    manifest, expected, reports, weather=pilot.validate_inputs(parent)
    # Preserve the existing raw-source and complete-export reconciliation.
    with TemporaryDirectory(prefix='runwx-berlin-performance-') as temporary:
        source=Path(temporary)/'source.csv';digest=sha256()
        with Path(parent['race_csv']).open('rb') as src, source.open('wb') as dest:
            while chunk:=src.read(1024*1024):
                digest.update(chunk);dest.write(chunk)
        if digest.hexdigest()!=parent['race_sha256']:
            raise ValueError('source hash changed')
        whole, parent_checks=pilot.analyse(parent,source,expected,reports,weather)
        # The parent routine validates but doesn't return durations. Stream the
        # verified temporary copy for this new analysis; original source read once.
        groups={y:{g:[] for g in ('female','male')} for y in pilot.YEARS}
        for year,row in pilot.iter_research_rows(source,set(pilot.YEARS),parent['race_sha256']):
            if row is not None:
                pilot.add_row(groups[year],row)
    rows=[];boundary_checks=[]
    for entry in parent['edition_inputs']:
        year=entry['year']
        histograms,outcomes=read_capture(entry['capture'],entry['capture_sha256'])
        for gender in ('female','male'):
            values=groups[year][gender]
            if len(values) != reports[year]['gender_counts'][gender]:
                raise ValueError(f'{year} {gender}: recorded count differs')
            for n in (20,50):
                selected=split(values,n)
                checked=histogram_split(histograms[gender],n)
                if len(selected[0]) + len(selected[1]) != len(values):
                    raise ValueError(f'{year} {gender}: partition count differs')
                for kind,part,counter in zip(('fastest','remaining'),selected,checked):
                    if Counter(part) != counter:
                        raise ValueError(f'{year} {gender}: independent distribution differs')
                    stats=pilot.group_stats(part)
                    if stats['median_duration_s'] != histogram_median(counter):
                        raise ValueError(f'{year} {gender}: independent median differs')
                    rows.append({'year':year,'race_date':reports[year]['race_date'], 'recorded_gender':gender,
                        'n':n,'subset':kind,'series':f'{gender}_{kind}_{n}',**stats,
                        'gender_count':len(values),'median_temp_c':weather[year]['median_temp_c'],
                        'population':reports[year]['population'],'timing_basis':'unknown',
                        'weather_basis':'09:00–15:00 Europe/Berlin; descriptive finish-area context',
                        'race_sha256':parent['race_sha256'],'capture_sha256':entry['capture_sha256']})
                boundary=sorted(values)[n-1]
                boundary_checks.append({'year':year,'recorded_gender':gender,'n':n,
                    'boundary_duration_s':boundary,'boundary_count_total':values.count(boundary),
                    'boundary_in_fastest':selected[0].count(boundary),'boundary_in_remaining':selected[1].count(boundary)})
    if len(rows) != 128:
        raise ValueError('expected 128 performance summaries')
    association=describe(rows)
    from verify import verify_correlations
    independent = verify_correlations(rows, association)
    whole_associations = pilot.associations(whole)
    independent_whole = verify_correlations(whole, whole_associations, key='group')
    output.mkdir(parents=True,exist_ok=False)
    (output/'whole-summaries.csv').write_bytes(pilot.csv_bytes(whole))
    (output/'whole-associations.json').write_bytes(pilot.json_bytes(whole_associations))
    (output/'correlation-check.json').write_bytes(pilot.json_bytes({'performance': independent, 'whole': independent_whole}))
    (output/'summaries.csv').write_bytes(pilot.csv_bytes(rows))
    (output/'associations.json').write_bytes(pilot.json_bytes(association))
    (output/'reconciliation.json').write_bytes(pilot.json_bytes({'status':'matched','accepted_records':541730,
        'parent_checks':parent_checks,'independent_subset_checks':128,'boundary_ties':boundary_checks}))
    manifest.append({'path':parent['race_csv'],'sha256':parent['race_sha256'],'role':'original source'})
    manifest += [{'path':e['capture'],'sha256':e['capture_sha256'],'role':'independently checked capture'} for e in parent['edition_inputs']]
    (output/'input-manifest.json').write_bytes(pilot.json_bytes({'inputs':manifest,'configuration_sha256':pilot.fingerprint(configuration)}))
    (output/'measurement.json').write_bytes(pilot.json_bytes({'elapsed_seconds':round(perf_counter()-start,6),
        'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'scope':'Analysis and all original/export/subset checks; no plotting.'}))
    print(json.dumps({'status':'completed_offline','summaries':128,'series':8,'accepted_records':541730}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('configuration',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        pilot.install()
        run(args.configuration,args.output)
    except (OSError,ValueError,KeyError,RuntimeError) as error:parser.exit(1,f'Performance pilot: {error}\n')
