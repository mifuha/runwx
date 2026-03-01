from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runwx.io_runs import load_runs_csv
from runwx.io_weather import load_weather_csv
from runwx.models import Run, WeatherObs
from runwx.pipeline import enrich_runs
from runwx.query_sqlite import fetch_latest_enriched
from runwx.storage_sqlite import connect, write_pipeline_result


def demo_data() -> tuple[list[Run], list[WeatherObs]]:
    runs = [
        Run(
            started_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
            duration_s=3600,
            distance_m=10_000,
        ),
        Run(
            started_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
            duration_s=1800,
            distance_m=5_000,
        ),
    ]

    weather = [
        WeatherObs(
            observed_at=datetime(2026, 2, 1, 10, 20, tzinfo=timezone.utc),
            temp_c=6.5,
            wind_mps=4.2,
            precipitation_mm=0.0,
        ),
        WeatherObs(
            observed_at=datetime(2026, 2, 1, 11, 50, tzinfo=timezone.utc),
            temp_c=7.1,
            wind_mps=3.8,
            precipitation_mm=0.2,
        ),
    ]
    return runs, weather


def csv_data(data_dir: Path = Path("data")) -> tuple[list[Run], list[WeatherObs]]:
    runs = load_runs_csv(data_dir / "sample_runs.csv")
    weather = load_weather_csv(data_dir / "sample_weather.csv")
    return runs, weather


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="runwx",
        description="Align runs with weather and optionally persist/query SQLite.",
    )
    sub = p.add_subparsers(dest="cmd")

    # run command
    run_p = sub.add_parser("run", help="Run pipeline (default).")
    run_p.add_argument("--csv", action="store_true", help="Load runs/weather from CSV sample files.")
    run_p.add_argument("--data-dir", type=Path, default=Path("data"), help="Directory containing CSV files (default: data/).")
    run_p.add_argument("--db", type=Path, default=None, help="Path to SQLite db file to write results.")
    run_p.add_argument("--max-gap-min", type=int, default=30, help="Maximum allowed gap in minutes (default: 30).")
    run_p.add_argument("--log-level", type=str, default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR). Default: INFO.")

    # query command
    q_p = sub.add_parser("query", help="Query latest enriched rows from SQLite.")
    q_p.add_argument("--db", type=Path, default=Path("runwx.db"), help="SQLite db path (default: runwx.db).")
    q_p.add_argument("--limit", type=int, default=20, help="Max rows to print (default: 20).")
    q_p.add_argument("--log-level", type=str, default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR). Default: INFO.")

    args = p.parse_args(argv)

    # default: if no subcommand, behave like "run"
    if args.cmd is None:
        args.cmd = "run"
        args.csv = False
        args.data_dir = Path("data")
        args.db = None
        args.max_gap_min = 30
        args.log_level = "INFO"

    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging(args.log_level)
    logger = logging.getLogger("runwx")

    # --- QUERY MODE ---
    if args.cmd == "query":
        logger.info("Querying latest enriched rows from %s (limit=%s)", args.db, args.limit)

        conn = connect(args.db)
        rows = fetch_latest_enriched(conn, limit=args.limit)
        conn.close()

        print(f"Latest enriched runs (limit={args.limit}) from {args.db}:")
        if not rows:
            print("- (no rows found)")
            return

        for r in rows:
            print(
                f"- run {r.started_at} ({r.distance_m}m, {r.duration_s}s)"
                f" -> weather {r.observed_at} ({r.temp_c}C, wind {r.wind_mps}m/s, rain {r.precipitation_mm}mm)"
            )
        return

    # --- RUN MODE ---
    if args.csv:
        runs, weather = csv_data(args.data_dir)
        logger.info(
            "Source: CSV files (%s, %s)",
            args.data_dir / "sample_runs.csv",
            args.data_dir / "sample_weather.csv",
        )
    else:
        runs, weather = demo_data()
        logger.info("Source: demo data")

    result = enrich_runs(runs, weather, max_gap=timedelta(minutes=args.max_gap_min))
    logger.info("Pipeline completed: enriched=%s skipped=%s", len(result.enriched), len(result.skipped))

    # keep prints as the user-facing report
    print(f"\nEnriched: {len(result.enriched)}")
    for item in result.enriched:
        r = item.run
        w = item.weather
        print(
            f"- run @ {r.started_at.isoformat()} ({r.distance_m}m, {r.duration_s}s)"
            f" -> weather @ {w.observed_at.isoformat()} ({w.temp_c}C, wind {w.wind_mps}m/s, rain {w.precipitation_mm}mm)"
        )

    print(f"\nSkipped: {len(result.skipped)}")
    for s in result.skipped:
        print(f"- run @ {s.run.started_at.isoformat()} -> {s.reason}")

    if args.db is not None:
        conn = connect(args.db)
        enriched_created, skipped_created = write_pipeline_result(conn, result)
        conn.close()
        logger.info(
            "Saved to SQLite: enriched_created=%s skipped_created=%s db=%s",
            enriched_created,
            skipped_created,
            args.db,
        )


if __name__ == "__main__":
    main()