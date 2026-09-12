"""Compare a downloaded cloud envelope with a local report (standard library only)."""

import argparse
from copy import deepcopy
import json
from pathlib import Path


def compare_reports(local: dict, cloud: dict) -> None:
    if cloud["cloud_report_schema_version"] not in {1, 2}:
        raise ValueError("unsupported cloud report schema")
    expected, actual = deepcopy(local), deepcopy(cloud["report"])
    # File locations legitimately differ. Every other report field must match,
    # including hashes, settings, quality counts, coverage and limitations.
    for report in (expected, actual):
        for kind in ("race", "weather"):
            del report["sources"][kind]["file"]
    if expected != actual:
        raise ValueError("report differs from local baseline beyond source file paths")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("local", type=Path)
    parser.add_argument("cloud", type=Path)
    args = parser.parse_args()
    compare_reports(json.loads(args.local.read_text()), json.loads(args.cloud.read_text()))
    print("MATCH: report fields, input hashes and settings; source file paths excluded.")


if __name__ == "__main__":
    main()
