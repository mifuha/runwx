from pathlib import Path

from runwx.adapters.races import load_event_json, load_results_csv
from runwx.services.race_analysis import analyze_race_event
from runwx.services.race_compare import compare_race_analyses


def load_analysis(event_path: Path, results_path: Path):
    event = load_event_json(event_path)
    results = load_results_csv(results_path, event_id=event.event_id)
    return analyze_race_event(event, results)


def main():
    base = Path(__file__).resolve().parent.parent / "data"

    analysis_2023 = load_analysis(
        base / "sample_event_2023.json",
        base / "sample_results_2023.csv",
    )
    analysis_current = load_analysis(
        base / "sample_event.json",
        base / "sample_results.csv",
    )

    rows = compare_race_analyses([analysis_current, analysis_2023])

    print("Race comparison (same course across years)")
    print()

    for row in rows:
        print(f"Event: {row.event_id}")
        print(f"  Date: {row.started_at.date()}")
        print(f"  Course: {row.course_id}")
        print(f"  Distance (m): {row.distance_m}")
        print(f"  Finishers: {row.finisher_count}")
        print(f"  Median time (s): {row.median_duration_s}")
        print(f"  Top-N median (s): {row.top_n_median_duration_s}")
        print(f"  Median temp (C): {row.median_temp_c}")
        print(f"  Median wind (m/s): {row.median_wind_mps}")
        print(f"  Median humidity (%): {row.median_humidity_pct}")
        print(f"  Median precipitation (mm): {row.median_precipitation_mm}")
        print()


if __name__ == "__main__":
    main()