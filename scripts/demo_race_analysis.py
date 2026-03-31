from pathlib import Path

from runwx.adapters.races import load_event_json, load_results_csv
from runwx.services.race_analysis import analyze_race_event


def format_weather(label, run_with_weather):
    run = run_with_weather.run
    weather = run_with_weather.weather

    print(f"{label}:")
    print(f"  Duration (s): {run.duration_s}")
    print(f"  Distance (m): {run.distance_m}")
    print(f"  Temp (C): {weather.temp_c}")
    print(f"  Wind (m/s): {weather.wind_mps}")
    print(f"  Precipitation (mm): {weather.precipitation_mm}")
    print(f"  Humidity (%): {weather.humidity_pct}")


def main():
    base = Path(__file__).resolve().parent.parent / "data"

    event = load_event_json(base / "sample_event.json")
    results = load_results_csv(base / "sample_results.csv", event_id=event.event_id)

    analysis = analyze_race_event(event, results)

    print(f"Event: {event.name}")
    print(f"Finishers: {analysis.summary.finisher_count}")
    print(f"Best time (s): {analysis.summary.best_duration_s}")
    print(f"Mean time (s): {analysis.summary.mean_duration_s:.1f}")
    print(f"Median time (s): {analysis.summary.median_duration_s}")
    print(f"Top-20 median (s): {analysis.summary.top_n_median_duration_s}")

    print()
    print(f"Enriched runs: {len(analysis.pipeline_result.enriched)}")
    print(f"Skipped runs: {len(analysis.pipeline_result.skipped)}")

    enriched = sorted(analysis.pipeline_result.enriched, key=lambda x: x.run.duration_s)

    if enriched:
        print()
        fastest = enriched[0]
        median = enriched[len(enriched) // 2]

        format_weather("Fastest enriched runner", fastest)
        print()
        format_weather("Median enriched runner", median)


if __name__ == "__main__":
    main()