"""Independent NDJSON reader and CDF checker; does not import fixed_mix.py."""
from bisect import bisect_right
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
from itertools import accumulate


def independent_band(raw):
    if raw in ('','M','M<'):
        return None
    if raw not in {'18','20','30','35','40','45','50','55','60','65','70','75','80'}:
        raise ValueError('independent reader found unreviewed age category')
    code = int(raw)
    return 'under40' if code < 40 else '40-49' if code < 50 else '50-59' if code < 60 else '60+'


def read(path, digest):
    all_values, cells, ages = Counter(),{},Counter()
    actual = sha256()
    with Path(path).open('rb') as handle:
        for raw in handle:
            actual.update(raw)
            r = json.loads(raw)
            if r['validation_status'] != 'accepted' or r['gender_raw'] not in {'female','male'}:
                raise ValueError('independent export outcome/gender differs')
            parts = r['time_raw'].split(':')
            if len(parts) != 3 or not all(p.isascii() and p.isdigit() for p in parts):
                raise ValueError('independent export time is malformed')
            hours,minutes,seconds = map(int,parts)
            duration = hours*3600 + minutes*60 + seconds
            if (minutes >= 60 or seconds >= 60 or duration <= 0
                    or type(r['duration_s']) is not int or duration != r['duration_s']):
                raise ValueError('independently parsed duration differs')
            g,age = r['gender_raw'],r['age_category_raw']
            ages[g,age] += 1
            all_values[duration] += 1
            b = independent_band(age)
            if b is not None:
                cells.setdefault((g,b),Counter())[duration] += 1
    if actual.hexdigest() != digest:
        raise ValueError('independent prepared export hash changed')
    return cells,all_values,ages


def prefix(hist):
    ordered = sorted(hist)
    return ordered,list(accumulate(hist[t] for t in ordered))


def cdf(distribution, duration):
    xs,cs = distribution
    i = bisect_right(xs,duration)
    return Fraction(cs[i-1],cs[-1]) if i else Fraction()


def inverted_quantile(candidates, cumulative, target):
    # Binary-search a CDF evaluated from independent stratum prefix counts.
    lo,hi = 0,len(candidates)-1
    while lo < hi:
        mid = (lo+hi)//2
        if cumulative(candidates[mid]) >= target: hi = mid
        else: lo = mid+1
    value = candidates[lo]
    return Fraction(value+candidates[lo+1],2) if cumulative(value) == target and lo+1<len(candidates) else Fraction(value)


def covariance_r(xs,ys):
    if len(xs) != len(ys) or len(xs)<3:
        return None
    mx,my = math.fsum(xs)/len(xs),math.fsum(ys)/len(ys)
    dx,dy = [x-mx for x in xs],[y-my for y in ys]
    denom = math.sqrt(math.fsum(x*x for x in dx)*math.fsum(y*y for y in dy))
    return math.fsum(x*y for x,y in zip(dx,dy))/denom if denom else None


def partial_r(years,xs,ys):
    a,b,c = covariance_r(xs,ys),covariance_r(xs,years),covariance_r(ys,years)
    if any(v is None for v in (a,b,c)):
        return None
    denom2 = (1-b*b)*(1-c*c)
    if denom2 <= 1e-24 or abs(1-abs(b)) < 1e-12 or abs(1-abs(c)) < 1e-12:
        return None
    return (a-b*c)/math.sqrt(denom2)


def same(actual,expected,label,tolerance=1e-12):
    if (actual is None)!=(expected is None) or (actual is not None and
            not math.isclose(actual,expected,abs_tol=tolerance,rel_tol=0)):
        raise ValueError(f'independent numerical check differs: {label}: {actual} != {expected}')


def verify(entries,primary_groups,primary_all,primary_ages,rows,associations):
    inputs = {}
    categories = 0
    for entry in entries:
        y = entry['year']
        cells,all_values,ages = read(entry['capture'],entry['capture_sha256'])
        if cells != primary_groups[y] or all_values != primary_all[y] or ages != primary_ages[y]:
            raise ValueError(f'{y}: independent raw-code/cell/whole duration histograms differ')
        categories += len(ages)
        known = Counter()
        for values in cells.values(): known.update(values)
        inputs[y] = {'cells':{cell:prefix(hist) for cell,hist in cells.items()},
                     'all':prefix(all_values),'known':prefix(known),
                     'n':sum(known.values()),'counts':{cell:sum(hist.values()) for cell,hist in cells.items()}}
    years = sorted(inputs)
    keys = set(inputs[years[0]]['cells'])
    ref = {c:sum((Fraction(inputs[y]['counts'][c],inputs[y]['n']) for y in years),Fraction())/len(years) for c in keys}
    indexed = {(r['year'],r['view']):r for r in rows}
    quantile_checks = 0
    for y in years:
        for view in ('whole_capture','eligible_unweighted','fixed_mix'):
            source = inputs[y]['all' if view=='whole_capture' else 'known']
            def cumulative(t):
                if view=='fixed_mix':
                    return sum((ref[c]*cdf(inputs[y]['cells'][c],t) for c in keys),Fraction())
                return cdf(source,t)
            quantiles = {k:inverted_quantile(source[0],cumulative,q) for k,q in
                         [('p25',Fraction(1,4)),('median',Fraction(1,2)),('p75',Fraction(3,4))]}
            quantiles['iqr'] = quantiles['p75']-quantiles['p25']
            for k,v in quantiles.items():
                row = indexed[y,view]
                same(float(v),row[k+'_duration_s'],f'{y}/{view}/{k} duration')
                same(float(v)/42.195,row[k+'_pace_s_per_km'],f'{y}/{view}/{k} pace')
                quantile_checks += 1
    checked = verify_coefficients(rows,associations)
    return {'status':'matched','edition_exports':len(inputs),'raw_category_cells_checked':categories,
            'full_duration_histograms':'identical for whole capture and every age/gender group',
            'independent_distribution_measure_checks':quantile_checks,
            **checked,
            'basis':'Independent NDJSON/time/category reader; prefix-count CDF queries and binary-search quantiles; covariance correlation and partial-correlation formula. No fixed_mix.py calculation helpers.'}


def verify_coefficients(rows, associations):
    years = sorted({int(r["year"]) for r in rows})
    indexed = {(int(r["year"]), r["view"]): r for r in rows}
    correlations = 0
    for key,result in associations['series'].items():
        view,metric = key.split(':')
        checks = [(None,result['pearson_r']['value']),
                  *[(r['omitted_year'],r['value']) for r in result['leave_one_out']]]
        if sorted(r['omitted_year'] for r in result['leave_one_out'])!=years:
            raise ValueError('omitted-edition coverage differs')
        for omitted,expected in checks:
            included = [y for y in years if y!=omitted]
            x = [indexed[y,view]['median_temp_c'] for y in included]
            z = [indexed[y,view][metric+'_pace_s_per_km'] for y in included]
            same(covariance_r(x,z),expected,key+f'/omit {omitted}')
            correlations += 1
    for view,result in associations['median_linear_year_sensitivity'].items():
        same(partial_r(years,[indexed[y,view]['median_temp_c'] for y in years],
                       [indexed[y,view]['median_pace_s_per_km'] for y in years]),result['value'],view+'/year')
    return {'independent_correlations':correlations,'independent_year_sensitivities':len(associations['median_linear_year_sensitivity'])}


def check_public(folder):
    """Recompute public counts, reference weights and coefficients without private inputs.

    Full quantile reproduction still requires the retained runner-level captures.
    """
    import csv
    import re
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_bytes())
    if any(s in json.dumps(manifest) for s in ('/home/','/mnt/','data/local/','@gmail.com')):
        raise ValueError('private path or account in public manifest')
    names = {'summaries.csv','groups.csv','age-audit.csv','associations.json',
             'reference-mix.json','reconciliation.json','scatter.svg'}
    if set(manifest['files']) != names:
        raise ValueError('public evidence file set differs')
    root = Path(__file__).resolve().parents[2]
    for name,digest in manifest['files'].items():
        if sha256((folder/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'public evidence hash changed: {name}')
    for name,digest in manifest['analysis_code'].items():
        if re.fullmatch(r'[a-z_]+\.py',name) is None:
            raise ValueError('unsafe code reference')
        if sha256((root/'analysis/berlin'/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'analysis code hash changed: {name}')
    if sha256((root/'analysis/berlin/fixed-mix.json').read_bytes()).hexdigest() != manifest['method_sha256']:
        raise ValueError('fixed method hash changed')
    provenance=root/'docs/evidence/berlin-case-study/manifest.json'
    if (manifest['input_provenance']!='../berlin-case-study/manifest.json'
            or sha256(provenance.read_bytes()).hexdigest()!=manifest['input_provenance_sha256']
            or json.loads(provenance.read_bytes())['race_sha256']!=manifest['race_sha256']):
        raise ValueError('original study provenance differs')
    def read_csv(name):
        with (folder/name).open(newline='',encoding='utf-8') as f:
            return list(csv.DictReader(f))
    rows = read_csv('summaries.csv')
    groups = read_csv('groups.csv')
    audit = read_csv('age-audit.csv')
    years = list(range(2003,2019))
    views = ('whole_capture','eligible_unweighted','fixed_mix')
    indexed = {(int(r['year']),r['view']):r for r in rows}
    if len(indexed)!=48 or len(rows)!=48 or set(indexed)!={(y,v) for y in years for v in views}:
        raise ValueError('public edition/view coverage differs')
    cells = {(g,b) for g in ('female','male') for b in ('under40','40-49','50-59','60+')}
    counts = {(int(r['year']),r['recorded_gender'],r['age_band']):int(r['count']) for r in groups}
    if len(groups)!=128 or set(counts)!={(y,g,b) for y in years for g,b in cells} or min(counts.values())<=0:
        raise ValueError('public age/gender coverage differs')
    raw = Counter()
    unknown = Counter()
    total = Counter()
    seen = set()
    for r in audit:
        y,g,a,n = int(r['year']),r['recorded_gender'],r['age_category_raw'],int(r['count'])
        if (y,g,a) in seen or y not in years or g not in {'female','male'} or n<=0:
            raise ValueError('duplicate or invalid public category count')
        seen.add((y,g,a))
        b = independent_band(a)
        if r['age_band'] != (b or 'unmapped'):
            raise ValueError('public age mapping differs')
        total[y] += n
        if b is None: unknown[y] += n
        else: raw[y,g,b] += n
    if dict(raw)!=counts or sum(total.values())!=541730 or sum(unknown.values())!=71:
        raise ValueError('public population counts differ')
    eligible = {y:total[y]-unknown[y] for y in years}
    ref = {(g,b):sum((Fraction(counts[y,g,b],eligible[y]) for y in years),Fraction())/16 for g,b in cells}
    saved = json.loads((folder/'reference-mix.json').read_bytes())['groups']
    if len(saved)!=8 or {(r['recorded_gender'],r['age_band']) for r in saved}!=cells:
        raise ValueError('public reference group set differs')
    for r in saved:
        expected = ref[r['recorded_gender'],r['age_band']]
        if Fraction(r['numerator'],r['denominator'])!=expected:
            raise ValueError('public reference proportions differ')
        same(float(expected),r['share'],'reference share')
    for r in groups:
        y,g,b=int(r['year']),r['recorded_gender'],r['age_band']
        observed=Fraction(counts[y,g,b],eligible[y])
        for name,actual in [('observed_share',observed),('reference_share',ref[g,b]),
                            ('relative_runner_weight',ref[g,b]/observed)]:
            same(float(actual),float(r[name]),name)
    for y in years:
        if len({indexed[y,v]['median_temp_c'] for v in views})!=1:
            raise ValueError('public weather differs across views')
        for v in views:
            row=indexed[y,v]
            if int(row['included_records'])!=(total[y] if v=='whole_capture' else eligible[y]) or int(row['unclear_age_records'])!=unknown[y]:
                raise ValueError('public summary population differs')
            qs=[float(row[k+'_duration_s']) for k in ('p25','median','p75')]
            if not all(math.isfinite(x) and x>0 for x in qs) or qs!=sorted(qs):
                raise ValueError('invalid public quantile order/value')
            same(qs[2]-qs[0],float(row['iqr_duration_s']),'IQR')
            for k in ('p25','median','p75','iqr'):
                same(float(row[k+'_duration_s'])/42.195,float(row[k+'_pace_s_per_km']),k+' units')
    associations=json.loads((folder/'associations.json').read_bytes())
    if (set(associations['series'])!={v+':'+m for v in views for m in ('p25','median','p75','iqr')}
            or set(associations['median_linear_year_sensitivity'])!=set(views)
            or associations['edition_weather_contexts']!=16
            or associations['reference_mix_frozen_for_omissions'] is not True):
        raise ValueError('public association context differs')
    typed=[{**r,'year':int(r['year']),**{k:float(value) for k,value in r.items()
           if k=='median_temp_c' or k.endswith('_pace_s_per_km')}} for r in rows]
    checks=verify_coefficients(typed,associations)
    for key,result in associations['series'].items():
        values=[r['value'] for r in result['leave_one_out'] if r['value'] is not None]
        same(min(values,default=None),result['leave_one_out_min'],key+' minimum')
        same(max(values,default=None),result['leave_one_out_max'],key+' maximum')
        changes=[r['omitted_year'] for r in result['leave_one_out']
                 if r['value'] is not None and result['pearson_r']['value'] is not None
                 and (r['value']>0)-(r['value']<0)!=(result['pearson_r']['value']>0)-(result['pearson_r']['value']<0)]
        if changes!=result['direction_change_omissions'] or any(r['edition_count']!=15 for r in result['leave_one_out']):
            raise ValueError('public omission summary differs')
    return {'status':'matched','summaries':48,'group_rows':128,'accepted':541730,
            'age_eligible':541659,'unmapped_age':71,**checks,
            'limits':'Public checks reproduce counts, reference proportions, unit identities and coefficients. Raw weighted quantiles require retained private inputs.'}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    print(json.dumps(check_public(args.directory),sort_keys=True))
