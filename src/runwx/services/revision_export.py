"""Prepare candidate rows for a revision; no warehouse writes or promotion."""

from datetime import timedelta
from pathlib import Path

from runwx.domain.revisions import RevisionIdentity
from runwx.services.result_export import build_result_rows
from runwx.services.revisions import processing_code_sha256


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
