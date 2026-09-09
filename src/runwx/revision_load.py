"""Preview a synthetic revision candidate; loading requires explicit --execute."""

import argparse
from datetime import timedelta
import json
from pathlib import Path

from runwx.adapters.bigquery.revision_load import load_revision_candidate, prepare_revision_load
from runwx.services.revisions import prepare_revision


def main(argv=None, *, client=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--race-html", type=Path, required=True)
    parser.add_argument("--weather-csv", type=Path, required=True)
    for name in ("dataset", "event-id", "weather-source-id", "course-id", "timezone"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--distance-m", type=int, required=True)
    parser.add_argument("--race-kind", choices=["synthetic"], required=True)
    parser.add_argument("--weather-kind", choices=["synthetic"], required=True)
    parser.add_argument("--snapshot-scope", choices=["complete"], required=True)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--max-gap-min", type=float, default=30)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    revision = prepare_revision(
        args.race_html, args.weather_csv, event_id=args.event_id,
        weather_source_id=args.weather_source_id, course_id=args.course_id,
        distance_m=args.distance_m, timezone_name=args.timezone, race_kind=args.race_kind,
        weather_kind=args.weather_kind, snapshot_scope=args.snapshot_scope,
        top_n=args.top_n, max_gap=timedelta(minutes=args.max_gap_min),
    )
    prepared = prepare_revision_load(revision, args.race_html, args.weather_csv, dataset=args.dataset)
    if args.execute:
        if client is None:
            from google.cloud import bigquery
            with bigquery.Client(project=args.dataset.split(".")[0], location="europe-west1") as owned_client:
                result = load_revision_candidate(owned_client, prepared)
        else:
            result = load_revision_candidate(client, prepared)
    else:
        result = {**prepared.summary(), "status": "prepared_locally"}
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    main()
