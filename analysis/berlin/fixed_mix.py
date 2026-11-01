"""Offline four-band Berlin study. The application serves checked aggregates only."""
import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
import resource
from statistics import correlation, linear_regression
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
import pilot as shared
from runwx.adapters.races.berlin_csv import iter_research_rows
import check_fixed_mix

YEARS = tuple(range(2003, 2019))
BANDS = {'under40': ('18','20','30','35'), '40-49': ('40','45'),
         '50-59': ('50','55'), '60+': ('60','65','70','75','80')}
CELLS = tuple((g,b) for g in ('female','male') for b in BANDS)
METRICS = ('p25','median','p75','iqr')
VIEWS = ('whole_capture','eligible_unweighted','fixed_mix')


def band(code):
    for label, values in BANDS.items():
        if code in values:
            return label
    if code in ('','M','M<'):
        return None
    raise ValueError(f'unreviewed age-category code: {code!r}')


def reference_mix(groups):
    if not groups:
        raise ValueError('no editions')
    for year, cells in groups.items():
        if set(cells) != set(CELLS) or any(not c or sum(c.values()) <= 0 for c in cells.values()):
            raise ValueError(f'{year}: missing required age/gender group')
    totals = {y: sum(sum(c.values()) for c in cells.values()) for y,cells in groups.items()}
    weights = {cell: sum((Fraction(sum(cells[cell].values()), totals[y])
                         for y,cells in groups.items()), Fraction()) / len(groups)
               for cell in CELLS}
    if sum(weights.values()) != 1:
        raise ValueError('reference weights do not sum to one')
    return weights


def combine(cells):
    result = Counter()
    for values in cells.values():
        result.update(values)
    return result


def reweight(cells, weights):
    if set(cells) != set(CELLS) or set(weights) != set(CELLS):
        raise ValueError('required cells differ')
    result = Counter()
    for cell in CELLS:
        n = sum(cells[cell].values())
        if n <= 0 or weights[cell] <= 0:
            raise ValueError('empty group or nonpositive reference weight')
        for duration,count in cells[cell].items():
            result[duration] += weights[cell] * count / n
    if sum(result.values()) != 1:
        raise ValueError('reweighted distribution does not sum to one')
    return result


def quantiles(masses):
    if not masses or any(not isinstance(k,int) or isinstance(k,bool) or k <= 0
                         or v <= 0 for k,v in masses.items()):
        raise ValueError('empty or invalid duration distribution')
    ordered = sorted(masses)
    total = sum(masses.values())
    targets = {key: total * q for key,q in
               [('p25',Fraction(1,4)),('median',Fraction(1,2)),('p75',Fraction(3,4))]}
    result = {}
    cumulative = Fraction()
    for i,duration in enumerate(ordered):
        cumulative += masses[duration]
        for key,target in targets.items():
            if key not in result and cumulative >= target:
                result[key] = (Fraction(duration + ordered[i+1],2)
                               if cumulative == target and i+1 < len(ordered)
                               else Fraction(duration))
    result['iqr'] = result['p75'] - result['p25']
    return result


def pearson(xs, ys):
    return shared.pearson(xs,ys)


def year_adjusted(years, xs, ys):
    if len(years) != len(xs) or len(xs) != len(ys) or len(set(years)) < 2:
        raise ValueError('year sensitivity inputs differ or years are constant')
    centered = [y - sum(years)/len(years) for y in years]
    residuals = []
    for values in (xs,ys):
        fit = linear_regression(centered,values)
        errors = [v - fit.intercept - fit.slope*x for x,v in zip(centered,values)]
        # A perfectly linear series has no remaining variation. Avoid numerical noise r.
        if max(map(abs,errors)) <= 1e-12 * max(1,max(map(abs,values))):
            return {'value':None,'reason':'no residual variation after linear year fit'}
        residuals.append(errors)
    return pearson(*residuals)


def associations(rows):
    indexed = {(r['year'],r['view']):r for r in rows}
    if len(indexed) != len(rows) or set(indexed) != {(y,v) for y in YEARS for v in VIEWS}:
        raise ValueError('each edition/view must occur exactly once')
    if any(len({indexed[y,v]['median_temp_c'] for v in VIEWS}) != 1 for y in YEARS):
        raise ValueError('views within an edition have different weather')
    output = {}
    for view in VIEWS:
        for metric in METRICS:
            def calculate(years):
                return pearson([indexed[y,view]['median_temp_c'] for y in years],
                               [indexed[y,view][metric+'_pace_s_per_km'] for y in years])
            full = calculate(YEARS)
            omitted = [{'omitted_year':y,'edition_count':15,
                        **calculate([z for z in YEARS if z != y])} for y in YEARS]
            defined = [r['value'] for r in omitted if r['value'] is not None]
            output[view+':'+metric] = {'pearson_r':full,'leave_one_out':omitted,
                'leave_one_out_min':min(defined,default=None),'leave_one_out_max':max(defined,default=None),
                'direction_change_omissions':[r['omitted_year'] for r in omitted
                    if r['value'] is not None and full['value'] is not None
                    and shared.direction(r['value']) != shared.direction(full['value'])]}
    sensitivities = {v:year_adjusted(list(YEARS),
        [indexed[y,v]['median_temp_c'] for y in YEARS],
        [indexed[y,v]['median_pace_s_per_km'] for y in YEARS]) for v in VIEWS}
    return {'edition_weather_contexts':16,'reference_mix_frozen_for_omissions':True,
            'series':output,'median_linear_year_sensitivity':sensitivities}


def load_method(path):
    method = json.loads(Path(path).read_bytes())
    if (method['schema'] != 'berlin_fixed_mix_pilot_v1' or method['years'] != list(YEARS)
            or method['age_bands'] != {k:list(v) for k,v in BANDS.items()}
            or method['recorded_genders'] != ['female','male']
            or method['unmapped_age_codes'] != ['','M','M<']
            or method['outcomes'] != list(METRICS) or method['distance_km'] != 42.195
            or [method[k] for k in ('expected_accepted','expected_eligible','expected_unmapped')]
                != [541730,541659,71]):
        raise ValueError('configuration differs from fixed four-band method')
    parent = (Path(path).resolve().parent / method['parent_configuration']).resolve()
    shared.checked_bytes(parent,method['parent_configuration_sha256'],'parent configuration')
    return method,parent


def run(configuration, output, measure=True):
    started = perf_counter()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'output directory already exists: {output}')
    method,parent = load_method(configuration)
    config = shared.load_configuration(parent)
    manifest, expected, reports, weather = shared.validate_inputs(config)
    groups = {y:{c:Counter() for c in CELLS} for y in YEARS}
    all_values = {y:Counter() for y in YEARS}
    unmapped = {y:Counter() for y in YEARS}
    age_audit = {y:Counter() for y in YEARS}
    genders = {y:Counter() for y in YEARS}
    inventory = Counter()
    with TemporaryDirectory(prefix='runwx-fixed-mix-') as temp:
        verified = Path(temp)/'source.csv'
        digest = sha256()
        with Path(config['race_csv']).open('rb') as src, verified.open('wb') as dst:
            while chunk := src.read(1024*1024):
                digest.update(chunk); dst.write(chunk)
        if digest.hexdigest() != config['race_sha256']:
            raise ValueError('Berlin source: hash changed')
        manifest.append({'path':config['race_csv'],'sha256':digest.hexdigest(),'role':'original research CSV'})
        for year,row in iter_research_rows(verified,set(YEARS),digest.hexdigest()):
            inventory['source'] += 1
            if row is None:
                inventory['unselected'] += 1
                continue
            if row['validation_status'] != 'accepted':
                raise ValueError(f'{year}: outcome differs from reviewed all-accepted cohort')
            duration,g,age = row['duration_s'],row['gender_raw'],row['age_category_raw']
            all_values[year][duration] += 1
            genders[year][g] += 1
            age_audit[year][g,age] += 1
            b = band(age)
            if b is None: unmapped[year][g,age] += 1
            else: groups[year][g,b][duration] += 1
    if dict(inventory) != {'source':884944,'unselected':343214}:
        raise ValueError('full source inventory changed')
    accepted = sum(sum(c.values()) for c in all_values.values())
    unknown = sum(sum(c.values()) for c in unmapped.values())
    if (accepted,accepted-unknown,unknown) != (541730,541659,71):
        raise ValueError('accepted/eligible/unmapped population changed')
    for y in YEARS:
        if (sum(all_values[y].values()) != reports[y]['accepted_count']
                or dict(genders[y]) != reports[y]['gender_counts']):
            raise ValueError(f'{y}: edition/gender counts differ')
        actual = float(quantiles(all_values[y])['median'])
        if actual != expected[y]['median_duration_s']:
            raise ValueError(f'{y}: original median differs from frozen independent baseline')
    weights = reference_mix(groups)
    rows,cell_rows,audit_rows = [],[],[]
    distributions = {}
    for y in YEARS:
        eligible = combine(groups[y])
        distributions[y] = {'whole_capture':all_values[y], 'eligible_unweighted':eligible,
                            'fixed_mix':reweight(groups[y],weights)}
        for view,dist in distributions[y].items():
            q = quantiles(dist)
            rows.append({'year':y,'race_date':reports[y]['race_date'],'view':view,
                'included_records':sum(all_values[y].values()) if view == 'whole_capture' else sum(eligible.values()),
                'unclear_age_records':sum(unmapped[y].values()),'median_temp_c':weather[y]['median_temp_c'],
                **{key+'_duration_s':float(value) for key,value in q.items()},
                **{key+'_pace_s_per_km':float(value)/42.195 for key,value in q.items()}})
        for g,b in CELLS:
            n = sum(groups[y][g,b].values())
            actual = Fraction(n,sum(eligible.values()))
            cell_rows.append({'year':y,'recorded_gender':g,'age_band':b,'count':n,
                'observed_share':float(actual),'reference_share':float(weights[g,b]),
                'relative_runner_weight':float(weights[g,b]/actual)})
        for (g,a),n in sorted(age_audit[y].items()):
            audit_rows.append({'year':y,'recorded_gender':g,'age_category_raw':a,
                              'age_band':band(a) or 'unmapped','count':n})
    assoc = associations(rows)
    # Separate reader, mapping, quantile algorithm and correlation formula.
    checks = check_fixed_mix.verify(config['edition_inputs'],groups,all_values,age_audit,rows,assoc)
    for entry in config['edition_inputs']:
        manifest.append({'path':entry['capture'],'sha256':entry['capture_sha256'],
                         'role':f"{entry['year']} independent prepared export"})
    for p,role in [(parent,'parent configuration'),(Path(configuration),'fixed method'),
                   (Path(config['retained_check_manifest']),'retained independent check manifest')]:
        manifest.append({'path':str(p.resolve()),'sha256':shared.fingerprint(p),'role':role})
    code_paths = [(ROOT/'analysis/berlin'/f) for f in
        ('fixed_mix.py','check_fixed_mix.py','plot_fixed_mix.py','render_fixed_mix_page.py',
         'fixed_mix_page.py','pilot.py','check_prepared.py','verify.py','offline_guard.py')] + [
        ROOT/'src/runwx/adapters/races/berlin_csv.py',ROOT/'src/runwx/services/berlin_prepare.py']
    code_hashes = {str(p.resolve()):shared.fingerprint(p) for p in sorted(code_paths)}
    reference = {'method':method['reference_mix'], 'groups':[
        {'recorded_gender':g,'age_band':b,'numerator':weights[g,b].numerator,
         'denominator':weights[g,b].denominator,'share':float(weights[g,b])} for g,b in CELLS]}
    output.mkdir(parents=True,exist_ok=False)
    for name,data in [('summaries.csv',rows),('groups.csv',cell_rows),('age-audit.csv',audit_rows)]:
        (output/name).write_bytes(shared.csv_bytes(data))
    for name,data in [('associations.json',assoc),('reference-mix.json',reference),
                      ('reconciliation.json',checks),('manifest.json',{'inputs':manifest,'code':code_hashes,
                       'source_reference':method['reference_commit'],'method':method})]:
        (output/name).write_bytes(shared.json_bytes(data))
    # Completion marker is last. Timing stays outside deterministic analytical outputs.
    if measure:
        (output/'measurement.json').write_bytes(shared.json_bytes({'elapsed_seconds':round(perf_counter()-started,6),
            'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'scope':'One Linux Python process: validation, hash copy, shared parsing, exact weighted distributions, independent export/numerical checks and output. Excludes tests and plotting.'}))
    (output/'COMPLETE.json').write_bytes(shared.json_bytes({'status':'validated_offline',
        'accepted':accepted,'eligible':accepted-unknown,'unmapped':unknown,'edition_contexts':16,
        'network':'external unshare network namespace plus socket/subprocess audit guard',
        'summary_rows':len(rows),'independent_user_practice':False}))
    return {'status':'validated_offline','output':str(output),'accepted':accepted,'eligible':accepted-unknown}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('configuration',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--no-measurement',action='store_true')
    args = parser.parse_args()
    try:
        shared.install()
        print(json.dumps(run(args.configuration,args.output,measure=not args.no_measurement),sort_keys=True))
    except (ValueError,OSError,KeyError,RuntimeError) as exc:
        parser.exit(1,f'Berlin fixed-mix pilot: {exc}\n')
