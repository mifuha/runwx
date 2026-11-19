"""Describe the Berlin temperature association in minutes per 5°C."""

import argparse
import csv
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import linear_regression, median

from check_fixed_mix import check_public

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/berlin-fixed-mix"
HOURLY_FILE = "temperature-hours.csv"
HOURS = tuple(f"{hour:02}:00" for hour in range(9, 16))
EARLY_HOURS = HOURS[:4]


def estimate(evidence, summaries):
    """Hold the edition medians fixed and vary only the weather window."""
    raw = (evidence / HOURLY_FILE).read_bytes()
    manifest = json.loads((evidence / "manifest.json").read_bytes())
    if sha256(raw).hexdigest() != manifest["finish_time_weather_sha256"]:
        raise ValueError("Berlin hourly temperature evidence hash changed")
    hourly = list(csv.DictReader(raw.decode().splitlines()))
    fixed = sorted(
        (row for row in summaries if row["view"] == "fixed_mix"),
        key=lambda row: row["race_date"],
    )
    dates = [row["race_date"] for row in fixed]
    if len(dates) != 16 or len(set(dates)) != 16 or dates != [row["race_date"] for row in hourly]:
        raise ValueError("Berlin hourly temperatures must cover the same 16 edition dates")
    temperatures = [[float(row[hour]) for hour in HOURS] for row in hourly]
    if not all(isfinite(value) for day in temperatures for value in day):
        raise ValueError("Berlin hourly temperatures must be finite")
    primary = [median(day) for day in temperatures]
    if primary != [float(row["median_temp_c"]) for row in fixed]:
        raise ValueError("09:00–15:00 temperatures differ from the checked Berlin summaries")
    early = [median(day[:len(EARLY_HOURS)]) for day in temperatures]
    durations = [float(row["median_duration_s"]) for row in fixed]

    def minutes_per_five_degrees(temperature, seconds):
        return linear_regression(temperature, seconds).slope * 5 / 60

    return {
        "09:00–15:00": minutes_per_five_degrees(primary, durations),
        "09:00–12:00": minutes_per_five_degrees(early, durations),
        "omit_one_edition_09:00–15:00": {
            date[:4]: minutes_per_five_degrees(
                primary[:i] + primary[i + 1:], durations[:i] + durations[i + 1:]
            )
            for i, date in enumerate(dates)
        },
    }


def saved_weather_rows(config_path):
    """Recover the public hourly values from the retained, validated snapshots."""
    from pilot import checked_bytes, load_configuration
    from runwx.services.berlin_prepare import _weather

    source = json.loads((ROOT / "docs/evidence/berlin-case-study/manifest.json").read_bytes())
    reviewed = {entry["year"]: entry for entry in source["inputs"]}
    inputs = load_configuration(config_path)["edition_inputs"]
    if sorted(entry["year"] for entry in inputs) != sorted(reviewed):
        raise ValueError("Berlin weather replay requires each reviewed edition once")
    rows = []
    for entry in sorted(inputs, key=lambda entry: entry["year"]):
        original = reviewed[entry["year"]]
        request = original["weather_request_url"]
        if entry["weather_request_url"] != request or entry["weather_sha256"] != original["weather_sha256"]:
            raise ValueError(f'{entry["year"]}: weather source differs from the published study')
        raw = checked_bytes(entry["weather_json"], original["weather_sha256"], str(entry["year"]))
        hourly = json.loads(raw)["hourly"]
        race_date = hourly["time"][0][:10]
        _weather(raw, request, race_date)
        rows.append({"race_date": race_date, **{
            hour: str(hourly["temperature_2m"][int(hour[:2])]) for hour in HOURS
        }})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved-weather", type=Path, metavar="INPUTS_JSON")
    args = parser.parse_args()
    check_public(EVIDENCE)
    with (EVIDENCE / "summaries.csv").open(newline="", encoding="utf-8") as handle:
        result = estimate(EVIDENCE, list(csv.DictReader(handle)))
    if args.saved_weather:
        with (EVIDENCE / HOURLY_FILE).open(newline="", encoding="utf-8") as handle:
            if saved_weather_rows(args.saved_weather) != list(csv.DictReader(handle)):
                raise ValueError("Berlin public hourly values differ from the saved weather")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
