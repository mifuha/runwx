"""Build and reconcile the two deterministic artifacts for one snapshot."""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from runwx.services.offline_report import build_offline_report
from runwx.services.result_export import build_result_rows, encode_result_rows


@dataclass(frozen=True)
class SnapshotArtifacts:
    report: dict
    result_rows: list[dict]
    result_payload: bytes
    result_sha256: str


def build_snapshot_artifacts(
    race_input: Path,
    weather_csv: Path,
    *,
    course_id: str,
    distance_m: int,
    timezone_name: str,
    top_n: int = 20,
    max_gap: timedelta = timedelta(minutes=30),
    weather_kind: str = "unknown",
    race_kind: str | None = None,
    export_weather_kind: str | None = None,
    timing_basis: str | None = None,
    race_format: str = "eventrac_html",
) -> SnapshotArtifacts:
    """Reuse the local builders, then reject any disagreement between them."""
    if race_kind is None:
        race_kind = "synthetic" if weather_kind == "synthetic" else "unknown"
    if export_weather_kind is None:
        export_weather_kind = weather_kind

    report = build_offline_report(
        race_input,
        weather_csv,
        course_id=course_id,
        distance_m=distance_m,
        timezone_name=timezone_name,
        top_n=top_n,
        max_gap=max_gap,
        weather_kind=weather_kind,
        race_format=race_format,
        timing_basis=timing_basis,
    )
    rows = build_result_rows(
        race_input,
        weather_csv,
        course_id=course_id,
        distance_m=distance_m,
        timezone_name=timezone_name,
        max_gap=max_gap,
        race_kind=race_kind,
        weather_kind=export_weather_kind,
        timing_basis=timing_basis,
        race_format=race_format,
    )
    if not rows:
        raise ValueError("result export has no candidate rows")

    quality = report["result_quality"]
    statuses = Counter(row["validation_status"] for row in rows)
    expected_statuses = {
        "accepted": quality["accepted_count"],
        "skipped": quality["skipped_count"],
        "invalid": quality["invalid_count"],
    }
    actual_statuses = {status: statuses[status] for status in expected_statuses}
    if len(rows) != quality["candidate_count"] or actual_statuses != expected_statuses:
        raise RuntimeError("report and result export row counts do not reconcile")

    coverage = report["weather_coverage"]
    matched = sum(row["weather_match_status"] == "matched" for row in rows)
    unmatched = sum(row["weather_match_status"] == "unmatched" for row in rows)
    if (matched, unmatched) != (coverage["matched_count"], coverage["unmatched_count"]):
        raise RuntimeError("report and result export weather counts do not reconcile")

    common_settings = {
        "course_id_input": course_id,
        "timezone_name": timezone_name,
        "max_gap_seconds": max_gap.total_seconds(),
    }
    if any(report["settings"][key] != value for key, value in common_settings.items()):
        raise RuntimeError("report settings do not match requested snapshot settings")
    if any(
        row["settings"][key] != value
        for row in rows
        for key, value in common_settings.items()
    ):
        raise RuntimeError("result export settings do not match requested snapshot settings")
    if any(row["distance_m"] != distance_m for row in rows):
        raise RuntimeError("result export distance does not match requested snapshot settings")
    if any(
        row["race_sha256"] != report["sources"]["race"]["sha256"]
        or row["weather_sha256"] != report["sources"]["weather"]["sha256"]
        for row in rows
    ):
        raise RuntimeError("report and result export source hashes do not reconcile")

    payload = encode_result_rows(rows)
    return SnapshotArtifacts(report, rows, payload, sha256(payload).hexdigest())
