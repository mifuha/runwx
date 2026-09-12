"""Prepare an exact Cloud Run export for BigQuery; --execute runs the safe loader."""

import argparse
import json

from runwx.adapters.bigquery.result_load import load_prepared
from runwx.adapters.gcs.warehouse_input import prepare_stored_load


def main(argv=None, *, storage_client=None, bigquery_client=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-uri", required=True)
    parser.add_argument("--report-generation", required=True)
    parser.add_argument("--result-export-uri", required=True)
    parser.add_argument("--result-export-generation", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--table", required=True, help="project.dataset.table")
    parser.add_argument("--location", default="europe-west1")
    parser.add_argument("--execute", action="store_true", help="Load and verify the prepared rows.")
    args = parser.parse_args(argv)

    if storage_client is None:
        from google.cloud import storage

        storage_client = storage.Client()
    stored = prepare_stored_load(
        storage_client,
        report_uri=args.report_uri,
        report_generation=args.report_generation,
        result_export_uri=args.result_export_uri,
        result_export_generation=args.result_export_generation,
        expected_sha256=args.expected_sha256,
        table_id=args.table,
        location=args.location,
    )
    if args.execute:
        if bigquery_client is None:
            from google.cloud import bigquery

            bigquery_client = bigquery.Client(
                project=args.table.split(".")[0], location=args.location
            )
        result = {**stored.summary(), **load_prepared(bigquery_client, stored.prepared)}
    else:
        result = {
            **stored.summary(),
            "status": "prepared_from_storage",
            "planned_load_job_id": stored.prepared.job_id,
        }
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
