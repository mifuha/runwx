"""Validate GNR sample exports before using the shared empty-table BigQuery loader."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from hashlib import sha256
from importlib.resources import files
import json
import re
from zoneinfo import ZoneInfo

from runwx.adapters.bigquery.result_load import _normalise_fields, _unique_object
from runwx.adapters.races.greatrun_json import EDITION_IDS, SAMPLE_LABEL, SAMPLE_NOTE, SAMPLE_SIZE

SCHEMA_BYTES = files(__package__).joinpath("gnr_sample_rows.schema.json").read_bytes()
SCHEMA = json.loads(SCHEMA_BYTES)
LONDON = ZoneInfo("Europe/London")
MAX_EXPORT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class PreparedSampleLoad:
    payload: bytes
    rows: list[dict]
    table_id: str
    location: str

    @property
    def schema(self):
        return SCHEMA

    @property
    def order_column(self):
        return "sample_rank"

    @property
    def job_id(self):
        identity = f"{self.table_id}:{self.location}:{sha256(self.payload).hexdigest()}:{sha256(SCHEMA_BYTES).hexdigest()}"
        return f"runwx_load_{sha256(identity.encode()).hexdigest()}"

    def summary(self):
        first = self.rows[0]
        return {
            "table_id": self.table_id, "location": self.location,
            "export_sha256": sha256(self.payload).hexdigest(),
            "schema_sha256": sha256(SCHEMA_BYTES).hexdigest(),
            "input_bytes": len(self.payload), "sample_count": len(self.rows),
            "event_id": first["event_id"], "race_date": first["race_date"],
            "sample_label": first["sample"]["label"],
            "timing_counts": dict(Counter(row["timing_basis"] for row in self.rows)),
            "race_sha256": first["race_sha256"],
            "categories_sha256": first["categories_sha256"],
            "weather_sha256": first["weather_sha256"],
        }


def prepare_sample_load(
    payload: bytes, *, table_id: str, expected_sha256: str, location: str = "europe-west1",
) -> PreparedSampleLoad:
    """Check all 1,000 rows locally; a bad export must not reach BigQuery."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", table_id):
        raise ValueError("expected project.dataset.table using simple identifiers")
    if location != "europe-west1":
        raise ValueError("GNR staging load uses europe-west1")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("export SHA-256 mismatch")
    if not payload or len(payload) > MAX_EXPORT_BYTES:
        raise ValueError("expected a nonempty GNR sample export of at most 4 MiB")
    rows = [_normalise_fields(json.loads(line, object_pairs_hook=_unique_object), SCHEMA)
            for line in payload.decode("utf-8").splitlines()]
    if len(rows) != SAMPLE_SIZE:
        raise ValueError("GNR sample must have exactly 1,000 rows")
    first = rows[0]
    day = date.fromisoformat(first["race_date"])
    race_id = EDITION_IDS.get(day.year)
    if race_id is None or first["event_id"] != f"greatrun:{race_id}":
        raise ValueError("unqualified GNR edition identity")
    if (first["export_schema"] != "gnr_sample_v1"
            or first["course_id"] != "great-north-run-traditional"
            or first["distance_m"] != 21100 or first["distance_basis"] != "provider distanceInKm"
            or first["race_kind"] != "historical"
            or first["weather_kind"] != "historical_reanalysis"):
        raise ValueError("GNR sample identity or interpretation differs")
    hashes = ("race_sha256", "categories_sha256", "weather_sha256", "weather_request_sha256")
    if any(not re.fullmatch(r"[0-9a-f]{64}", first[key]) for key in hashes):
        raise ValueError("invalid source hash")
    sample = first["sample"]
    if (sample["label"] != SAMPLE_LABEL or sample["note"] != SAMPLE_NOTE
            or sample["size"] != SAMPLE_SIZE or sample["source_count"] != 2000
            or not 0 <= sample["excluded_count"] <= 1000
            or sample["unselected_count"] != 1000 - sample["excluded_count"]
            or sample["selection"] != "published finish seconds then provider result ID"
            or sample["timing_note"] != "Published chip/gun/unknown basis retained per row; no timing correction."):
        raise ValueError("sample scope/counts differ from the qualified export")
    context = first["weather_context"]
    expected_start = datetime.combine(day, time(10), tzinfo=LONDON).astimezone(timezone.utc).isoformat()
    expected_end = datetime.combine(day, time(14), tzinfo=LONDON).astimezone(timezone.utc).isoformat()
    if (context["basis"] != "fixed_event_window"
            or context["note"] != "Start-area ERA5 context; not individual runner exposure or whole-course weather."
            or context["timezone"] != "Europe/London"
            or context["start_local"] != "10:00" or context["end_local"] != "14:00"
            or context["start_utc"] != expected_start or context["end_utc"] != expected_end
            or context["hourly_observation_count"] != 5
            or context["requested_latitude"] != 54.984 or context["requested_longitude"] != -1.620
            or abs(context["grid_latitude"] - 54.984) > 0.5
            or abs(context["grid_longitude"] + 1.620) > 0.5
            or context["median_wind_mps"] < 0
            or not 0 <= context["median_humidity_pct"] <= 100
            or context["precipitation_mm"] < 0
            or context["precipitation_basis"] != "sum of preceding-hour amounts ending after start through end"):
        raise ValueError("event-window weather context differs")
    common = tuple(key for key in first if key not in {
        "source_row_id", "source_row_number", "sample_rank", "duration_s", "timing_basis"
    })
    locators = set()
    previous_duration = 0
    for rank, row in enumerate(rows, 1):
        if any(row[key] != first[key] for key in common):
            raise ValueError("mixed GNR snapshots or settings")
        locator = row["source_row_number"]
        if (row["sample_rank"] != rank or locator not in range(1, 2001)
                or locator in locators
                or row["source_row_id"] != f"{first['event_id']}:{first['race_sha256']}:{locator}"
                or row["duration_s"] <= 0 or row["duration_s"] < previous_duration
                or row["timing_basis"] not in {"chip", "gun", "unknown"}):
            raise ValueError("invalid GNR sample rank, source identity, timing or duration")
        locators.add(locator)
        previous_duration = row["duration_s"]
    if (sample["cutoff_s"] != previous_duration
            or not 1 <= sample["cutoff_ties_selected"] <= sample["cutoff_ties_available"]
            or sample["cutoff_ties_selected"] != sum(row["duration_s"] == previous_duration for row in rows)
            or sample["cutoff_ties_available"] > sample["source_count"] - sample["excluded_count"]):
        raise ValueError("sample cutoff or tie counts do not reconcile")
    return PreparedSampleLoad(payload, rows, table_id, location)
