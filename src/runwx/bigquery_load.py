"""Preview one fixed-snapshot staging load locally; --execute sends it to BigQuery."""

import argparse
import json
from pathlib import Path

from runwx.adapters.bigquery.result_load import load_prepared, prepare_load
from runwx.adapters.bigquery.gnr_sample_load import prepare_sample_load
from runwx.services.berlin_load import MAX_CAPTURE_BYTES, MAX_REPORT_BYTES, prepare_berlin_load


def main(argv=None, *, client=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--table", required=True, help="project.dataset.table")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--location", default="europe-west1")
    parser.add_argument("--input-format", choices=("full-results", "gnr-sample", "berlin-research"),
                        default="full-results", help="Explicit export contract (default: full-results).")
    parser.add_argument("--preparation-report", type=Path, help="Berlin edition report from prepare-berlin.")
    parser.add_argument("--expected-report-sha256", help="Reviewed Berlin report SHA-256.")
    parser.add_argument("--execute", action="store_true", help="Upload data and run verification queries.")
    args = parser.parse_args(argv)
    if args.input_format == "berlin-research":
        if args.preparation_report is None or args.expected_report_sha256 is None:
            parser.error("berlin-research requires --preparation-report and --expected-report-sha256")
        if args.input.stat().st_size > MAX_CAPTURE_BYTES or args.preparation_report.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError("Berlin input or report exceeds its preparation size bound")
        prepared = prepare_berlin_load(
            args.input.read_bytes(), args.preparation_report.read_bytes(), table_id=args.table,
            expected_sha256=args.expected_sha256, expected_report_sha256=args.expected_report_sha256,
            location=args.location,
        )
    else:
        if args.preparation_report is not None or args.expected_report_sha256 is not None:
            parser.error("preparation report arguments apply only to berlin-research")
        prepare = prepare_sample_load if args.input_format == "gnr-sample" else prepare_load
        prepared = prepare(args.input.read_bytes(), table_id=args.table,
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
