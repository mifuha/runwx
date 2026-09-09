"""Prepare candidate rows for a revision; no warehouse writes or promotion."""

from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from runwx.domain.revisions import RevisionIdentity, canonical_json
from runwx.services.result_export import build_result_rows
from runwx.services.offline_report import build_offline_report
from runwx.services.revisions import _check_report, processing_code_sha256


def build_revision_rows(
    revision: RevisionIdentity, race_html: Path, weather_csv: Path,
) -> list[dict]:
    """Keep the existing export fields and add the logical revision key.

    A successful export is only a candidate. Warehouse validation and explicit
    selection are separate steps; no attempt ID is part of a result-row key.
    """
    if revision.code_sha256 != processing_code_sha256():
        raise ValueError("processing code differs from prepared revision")
    settings = revision.settings
    settings.pop("top_n")  # Changes revision identity, not individual result rows.
    settings["max_gap"] = timedelta(seconds=settings.pop("max_gap_seconds"))
    rows = build_result_rows(race_html, weather_csv, race_kind=revision.race_kind, **settings)
    for row in rows:
        if (row["event_id"] != revision.event_id
                or row["race_sha256"] != revision.race_sha256
                or row["weather_sha256"] != revision.weather_sha256):
            raise ValueError("export sources differ from prepared revision")
    return [{"revision_id": revision.revision_id, **row} for row in rows]


def build_revision_candidate(
    revision: RevisionIdentity, race_html: Path, weather_csv: Path,
) -> tuple[dict, list[dict]]:
    """Share the exact bounded baseline between candidate loading and selection."""
    if revision.race_kind != "synthetic" or revision.settings["weather_kind"] != "synthetic":
        raise ValueError("this bounded publisher requires explicitly synthetic inputs")
    rows = build_revision_rows(revision, race_html, weather_csv)
    settings = revision.settings
    settings["max_gap"] = timedelta(seconds=settings.pop("max_gap_seconds"))
    report = build_offline_report(race_html, weather_csv, **settings)
    _check_report(revision, report)
    rows_json = canonical_json(rows)
    metadata = {
        **asdict(revision), "revision_id": revision.revision_id,
        "result_rows_sha256": sha256(rows_json.encode()).hexdigest(),
        "report_json": canonical_json(report),
        **{key: report["result_quality"][key] for key in (
            "candidate_count", "accepted_count", "skipped_count", "invalid_count")},
        "weather_matched_count": report["weather_coverage"]["matched_count"],
    }
    # Bound the read-back and query-parameter payload for this small demonstration.
    if len(rows_json.encode()) + len(canonical_json(metadata).encode()) > 1024 * 1024:
        raise ValueError("selection baseline exceeds the 1 MiB demonstration limit")
    return metadata, rows
