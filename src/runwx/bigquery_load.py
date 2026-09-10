"""Preview one fixed-snapshot staging load locally; --execute sends it to BigQuery."""

import argparse
import json
from pathlib import Path

from runwx.adapters.bigquery.result_load import load_prepared, prepare_load


def main(argv=None, *, client=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--table", required=True, help="project.dataset.table")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--location", default="europe-west1")
    parser.add_argument("--execute", action="store_true", help="Upload data and run verification queries.")
    args = parser.parse_args(argv)
    prepared = prepare_load(args.input.read_bytes(), table_id=args.table,
                            expected_sha256=args.expected_sha256, location=args.location)
    if args.execute:
        if client is None:
            from google.cloud import bigquery

            client = bigquery.Client(project=args.table.split(".")[0], location=args.location)
        result = load_prepared(client, prepared)
    else:
        result = {**prepared.summary(), "status": "prepared_locally", "planned_load_job_id": prepared.job_id}
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
