"""One local, offline Berlin study. Not an application CLI or warehouse stage."""
import argparse
from array import array
from collections import Counter
import csv
from hashlib import sha256
from io import StringIO
import json
import math
from pathlib import Path
import resource
from statistics import correlation, mean, median
from tempfile import TemporaryDirectory
from time import perf_counter

from offline_guard import install
from check_prepared import verify as verify_prepared
from runwx.adapters.races.berlin_csv import CATALOG, iter_research_rows
from runwx.services.berlin_prepare import _weather

GROUPS = ("all", "female", "male")
YEARS = tuple(range(2003, 2019))
REFERENCE = "abcf027c9c91b60a0cb3afdc0306a3f47d119848"
DISTANCE_KM = 42.195


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       indent=2) + "\n").encode()


def fingerprint(path):
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def checked_bytes(path, expected, label):
    raw = Path(path).read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"{label}: hash changed")
    return raw


def add_row(groups, row):
    gender = row["gender_raw"]
    if gender not in {"female", "male"}:
        raise ValueError("unreviewed recorded gender")
    status = row["validation_status"]
    if status == "held":
        if row["duration_s"] is not None:
            raise ValueError("held result has a duration")
        return False
    if status != "accepted" or type(row["duration_s"]) is not int or row["duration_s"] <= 0:
        raise ValueError("accepted result has an unusable duration or outcome")
    groups[gender].append(row["duration_s"])
    return True


def group_stats(values):
    if not values:
        return {"count": 0, "median_duration_s": None, "median_pace_s_per_km": None}
    middle = median(values)
    return {"count": len(values), "median_duration_s": middle,
            "median_pace_s_per_km": middle / DISTANCE_KM}


def pearson(xs, ys):
    if len(xs) != len(ys) or len(xs) < 3:
        return {"value": None, "reason": "fewer than three paired editions"}
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (*xs, *ys)):
        raise ValueError("association inputs must be finite numbers")
    if len(set(xs)) == 1 or len(set(ys)) == 1:
        return {"value": None, "reason": "constant series"}
    return {"value": correlation(xs, ys), "reason": None}


def direction(value):
    return None if value is None else "positive" if value > 0 else "negative" if value < 0 else "zero"


def associations(rows):
    years = sorted({row["year"] for row in rows})
    by_key = {(row["year"], row["group"]): row for row in rows}
    if len(by_key) != len(rows) or set(by_key) != {(y, g) for y in years for g in GROUPS}:
        raise ValueError("each edition must have exactly all/female/male summaries")
    for year in years:
        if len({by_key[year, g]["median_temp_c"] for g in GROUPS}) != 1:
            raise ValueError("groups within an edition must share the same weather")
    output = {}
    for group in GROUPS:
        def calculate(included):
            return pearson([by_key[y, group]["median_temp_c"] for y in included],
                           [by_key[y, group]["median_pace_s_per_km"] for y in included])
        full = calculate(years)
        omissions = [{"omitted_year": omitted, "included_years": [y for y in years if y != omitted],
                      "edition_count": len(years) - 1, **calculate([y for y in years if y != omitted])}
                     for omitted in years]
        defined = [row for row in omissions if row["value"] is not None]
        for row in omissions:
            row["delta_from_full"] = (row["value"] - full["value"]
                if row["value"] is not None and full["value"] is not None else None)
        influential = max(defined, key=lambda row: abs(row["delta_from_full"] or 0)) if defined else None
        output[group] = {"edition_count": len(years), "years": years, "pearson_r": full,
                         "direction": direction(full["value"]),
                         "leave_one_out": omissions,
                         "leave_one_out_min": min((r["value"] for r in defined), default=None),
                         "leave_one_out_max": max((r["value"] for r in defined), default=None),
                         "direction_change_omissions": [r["omitted_year"] for r in defined
                              if full["value"] is not None and direction(r["value"]) != direction(full["value"])],
                         "most_influential_omission": influential}
    return {"measure": "Pearson r between edition temperature and group median pace",
            "weighting": "equal edition weights", "unit": "edition, not runner",
            "independent_weather_observations": len(years), "series": output,
            "interpretation": "Descriptive linear association, without p-values, confidence intervals, age/year adjustment, prediction or causal interpretation. The groups share the same 16 weather contexts."}


def load_configuration(path):
    """Resolve retained input paths relative to the configuration, never cwd."""
    path = Path(path).resolve()
    config = json.loads(path.read_bytes())
    for key in ("race_csv", "catalog", "baseline", "retained_check_manifest", "retained_native_results"):
        config[key] = str((path.parent / config[key]).resolve())
    for entry in config["edition_inputs"]:
        for key in ("weather_json", "capture", "report", "weather_csv"):
            entry[key] = str((path.parent / entry[key]).resolve())
    return config


def validate_configuration(config):
    method = config["method"]
    if (config["schema"] != "berlin_group_pilot_v1"
            or config["reference_commit"] != REFERENCE
            or method["years"] != list(YEARS) or method["groups"] != list(GROUPS)
            or method["distance_m"] != 42195
            or method["weather_window"] != ["09:00", "15:00"]
            or method["timezone"] != "Europe/Berlin"
            or any(method[k] is not False for k in ("age_adjustment", "year_adjustment", "p_values",
                                                   "confidence_intervals", "predictions", "deduplicate"))):
        raise ValueError("configuration differs from the fixed pilot method")
    if (sorted(e["year"] for e in config["edition_inputs"]) != list(YEARS)
            or config["race_sha256"] != CATALOG["results_sha256"]):
        raise ValueError("pilot must contain each reviewed edition once and the pinned source")


def validate_inputs(config):
    validate_configuration(config)
    manifest = []
    def retain(path, digest, label):
        raw = checked_bytes(path, digest, label)
        manifest.append({"path": str(Path(path).resolve()), "sha256": digest, "bytes": len(raw),
                         "role": label})
        return raw
    catalog = json.loads(retain(config["catalog"], config["catalog_sha256"], "qualified catalog"))
    if catalog != CATALOG:
        raise ValueError("loaded parser catalog differs from recorded catalog")
    checks = json.loads(Path(config["retained_check_manifest"]).read_bytes())
    if checks["file_sha256"][Path(config["baseline"]).name] != config["baseline_sha256"]:
        raise ValueError("baseline hash differs from retained pre-execution check")
    expected = json.loads(retain(config["baseline"], config["baseline_sha256"], "frozen independent baseline"))
    by_year = {int(e["race_date"][:4]): e for e in expected["editions"]}
    if sorted(by_year) != list(YEARS):
        raise ValueError("frozen baseline cohort differs")
    retain(config["retained_native_results"], config["retained_native_results_sha256"], "saved native results (no query)")
    reports, weather = {}, {}
    for entry in sorted(config["edition_inputs"], key=lambda e: e["year"]):
        year = entry["year"]
        approved = CATALOG["editions"][str(year)]
        baseline = by_year[year]
        if (entry["report_sha256"] != baseline["preparation_report_sha256"]
                or entry["capture_sha256"] != baseline["capture_sha256"]
                or entry["weather_sha256"] != baseline["weather_sha256"]):
            raise ValueError(f"{year}: input hashes differ from frozen baseline")
        report = json.loads(retain(entry["report"], entry["report_sha256"], f"{year} preparation report"))
        if (report["year"] != year or report["race_date"] != approved["date"]
                or report["results_sha256"] != config["race_sha256"]
                or report["distance_m"] != 42195 or report["timing_basis"] is not None
                or report["individual_starts_available"] is not False
                or report["gender_counts"] != approved["gender_counts"]
                or report["captured_count"] != approved["captured_count"]
                or report["published_count"] != approved["published_count"]
                or report["export_sha256"] != entry["capture_sha256"]
                or report["weather_response_sha256"] != entry["weather_sha256"]
                or report["weather_request_url"] != entry["weather_request_url"]):
            raise ValueError(f"{year}: preparation report context differs")
        raw = retain(entry["weather_json"], entry["weather_sha256"], f"{year} saved ERA5 response")
        csv_bytes, context = _weather(raw, entry["weather_request_url"], approved["date"])
        if context != report["weather_context"]:
            raise ValueError(f"{year}: shared weather validation differs from frozen report")
        saved_csv = retain(entry["weather_csv"], report["weather_csv_sha256"], f"{year} saved weather CSV")
        if csv_bytes != saved_csv or context["median_temp_c"] != baseline["median_temp_c"]:
            raise ValueError(f"{year}: weather bytes/statistic differ")
        reports[year], weather[year] = report, context
    return manifest, by_year, reports, weather


def percentile(sorted_values, fraction):
    position = (len(sorted_values) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (position - lo)


def analyse(config, source, expected, reports, weather):
    groups = {year: {gender: array("I") for gender in ("female", "male")} for year in YEARS}
    outcomes = {year: Counter() for year in YEARS}
    genders = {year: Counter() for year in YEARS}
    source_count = unselected = 0
    for year, row in iter_research_rows(source, set(YEARS), config["race_sha256"]):
        source_count += 1
        if row is None:
            unselected += 1
            continue
        outcomes[year][row["validation_status"]] += 1
        genders[year][row["gender_raw"]] += 1
        add_row(groups[year], row)
    if source_count != 884944 or unselected != 343214:
        raise ValueError("source inventory differs from retained preparation")
    rows, checked_editions = [], []
    for year in YEARS:
        report = reports[year]
        if (dict(genders[year]) != report["gender_counts"]
                or outcomes[year]["accepted"] != report["accepted_count"]
                or outcomes[year]["held"] != report["held_count"]):
            raise ValueError(f"{year}: population/outcomes do not reconcile")
        combined = sorted([*groups[year]["female"], *groups[year]["male"]])
        checks = {"median_duration_s": median(combined), "mean_duration_s": mean(combined),
                  "duration_p25_s": percentile(combined, .25),
                  "duration_p75_s": percentile(combined, .75)}
        for key, actual in checks.items():
            if not math.isclose(actual, expected[year][key], rel_tol=1e-12, abs_tol=1e-9):
                raise ValueError(f"{year}: {key} differs from frozen independent expectation")
        for group in GROUPS:
            stats = group_stats(combined if group == "all" else groups[year][group])
            rows.append({"year": year, "race_date": report["race_date"], "group": group,
                         "captured_count": report["captured_count"],
                         "accepted_count": report["accepted_count"], "held_count": report["held_count"],
                         **stats, "group_share_of_accepted": stats["count"] / report["accepted_count"],
                         "median_temp_c": weather[year]["median_temp_c"],
                         "weather_window": "09:00–15:00 Europe/Berlin; 7 hourly observations",
                         "published_count": report["published_count"],
                         "difference_from_published": report["count_difference_from_published"],
                         "count_note": report["count_note"], "population": report["population"],
                         "course_era": report["course_era"], "timing_basis": "unknown",
                         "race_sha256": config["race_sha256"],
                         "weather_sha256": report["weather_response_sha256"],
                         "capture_sha256": report["export_sha256"]})
        checked_editions.append({"year": year, "accepted_count": report["accepted_count"],
                                 "held_count": report["held_count"], "frozen_statistics_matched": checks})
    if len(rows) != 48 or sum(len(values) for genders_ in groups.values() for values in genders_.values()) != 541730:
        raise ValueError("cohort totals differ from fixed pilot")
    independent = verify_prepared(config["edition_inputs"], groups, reports)
    for edition in independent["editions"]:
        for group, checked in edition["groups"].items():
            row = next(r for r in rows if r["year"] == edition["year"] and r["group"] == group)
            if checked["count"] != row["count"] or checked["median_duration_s"] != row["median_duration_s"]:
                raise ValueError("independent subgroup median/count differs")
    return rows, {"source_records": source_count, "unselected_records": unselected,
                  "accepted_records": 541730, "held_records": sum(r["held_count"] for r in reports.values()),
                  "whole_capture_checks": checked_editions, "separate_export_check": independent}


def csv_bytes(rows):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def run(config_path, output):
    start = perf_counter()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output directory already exists: {output}")
    config_path = Path(config_path).resolve()
    raw_config = config_path.read_bytes()
    config = load_configuration(config_path)
    manifest, expected, reports, weather = validate_inputs(config)
    # Read the original file once into a hash-verified temporary copy, then parse that copy once.
    with TemporaryDirectory(prefix="runwx-berlin-group-") as folder:
        source = Path(folder) / "source.csv"
        digest = sha256()
        source_size = 0
        with Path(config["race_csv"]).open("rb") as handle, source.open("wb") as dest:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                source_size += len(chunk)
                dest.write(chunk)
        if digest.hexdigest() != config["race_sha256"]:
            raise ValueError("Berlin source: hash changed from reviewed Kaggle v2")
        manifest.append({"path": config["race_csv"], "sha256": digest.hexdigest(),
                         "bytes": source_size, "role": "original research CSV"})
        rows, checks = analyse(config, source, expected, reports, weather)
    for entry in config["edition_inputs"]:
        capture = Path(entry["capture"])
        manifest.append({"path": str(capture.resolve()), "sha256": entry["capture_sha256"],
                         "bytes": capture.stat().st_size, "role": f"{entry['year']} independently read prepared capture"})
    result = associations(rows)
    output.mkdir(parents=True, exist_ok=False)
    (output / "summaries.csv").write_bytes(csv_bytes(rows))
    (output / "associations.json").write_bytes(json_bytes(result))
    (output / "reconciliation.json").write_bytes(json_bytes(checks))
    (output / "input-manifest.json").write_bytes(json_bytes({"reference_commit": REFERENCE,
        "configuration_sha256": sha256(raw_config).hexdigest(), "inputs": manifest}))
    (output / "run.json").write_bytes(json_bytes({"status": "analysed_offline_not_published",
        "network": "socket/subprocess audit guard and external network namespace",
        "editions": 16, "summary_rows": len(rows), "accepted_records": checks["accepted_records"],
        "independent_user_practice": False}))
    # Operational timing intentionally stays outside deterministic analytical artifacts.
    (output / "measurement.json").write_bytes(json_bytes({"elapsed_seconds": round(perf_counter() - start, 6),
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scope": "One Python pilot process: validation, verified source copy, parsing, aggregation, separate export check and analytical output; excludes plotting and tests."}))
    return {"output": str(output), "status": "analysed_offline", "editions": 16, "summary_rows": 48,
            "accepted_records": checks["accepted_records"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        install()
        print(json.dumps(run(args.configuration, args.output), sort_keys=True))
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.exit(1, f"Berlin offline pilot: {error}\n")
