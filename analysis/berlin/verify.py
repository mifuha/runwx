"""Independent covariance calculation over aggregate rows; no primary helpers."""
import csv
import json
import math
from pathlib import Path


def coefficient(pairs):
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    if not all(math.isfinite(v) for v in (*xs, *ys)):
        raise ValueError('non-finite verification input')
    mx, my = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    dx, dy = [v - mx for v in xs], [v - my for v in ys]
    denominator = math.sqrt(math.fsum(v*v for v in dx) * math.fsum(v*v for v in dy))
    return math.fsum(a*b for a,b in zip(dx,dy)) / denominator if denominator else None


def verify_correlations(rows, associations, key='series'):
    series_keys = {row[key] for row in rows}
    if series_keys != set(associations['series']):
        raise ValueError('verification series differ')
    count = 0
    for name, result in associations['series'].items():
        selected = [row for row in rows if row[key] == name]
        years = [int(row['year']) for row in selected]
        omissions = result['leave_one_out']
        if sorted(years) != list(range(2003, 2019)) or sorted(r['omitted_year'] for r in omissions) != sorted(years):
            raise ValueError('verification requires every edition and omission exactly once')
        checks = [(None, result['pearson_r']['value']), *[(r['omitted_year'], r['value']) for r in omissions]]
        for omitted, expected in checks:
            pairs = [(float(r['median_temp_c']), float(r['median_pace_s_per_km'])) for r in selected if int(r['year']) != omitted]
            actual = coefficient(pairs)
            if (actual is None) != (expected is None) or (actual is not None and not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12)):
                raise ValueError(f'{name}, omitted {omitted}: independent correlation differs')
            count += 1
    return {'status': 'matched', 'correlations_checked': count, 'absolute_tolerance': 1e-12}


def check_directory(directory):
    directory = Path(directory)
    def check(prefix, key):
        with (directory / f'{prefix}summaries.csv').open(newline='') as source:
            rows = list(csv.DictReader(source))
        return verify_correlations(rows, json.loads((directory / f'{prefix}associations.json').read_text()), key)
    return {'performance': check('', 'series'), 'whole': check('whole-', 'group')}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(check_directory(args.directory), sort_keys=True))
