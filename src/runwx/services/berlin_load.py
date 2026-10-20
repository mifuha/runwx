"""Bind one prepared Berlin capture and reviewed report to a typed warehouse load."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from hashlib import sha256
from importlib.resources import files
import json
import re

from runwx.adapters.bigquery.result_load import _normalise_fields, _unique_object
from runwx.adapters.races.berlin_csv import CATALOG, validate_reported_result
from runwx.domain.models import WeatherObs
from runwx.services.berlin_prepare import BERLIN, LOCATION, validate_weather_request

SCHEMA_BYTES = files("runwx.adapters.bigquery").joinpath("berlin_research_rows.schema.json").read_bytes()
SCHEMA = json.loads(SCHEMA_BYTES)
RAW_SCHEMA, CONTEXT_SCHEMA = SCHEMA[:13], SCHEMA[13:]
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 64 * 1024
MAX_EXPORT_BYTES = 64 * 1024 * 1024
REPORT_FIELDS = {
    "accepted_count", "captured_count", "count_difference_from_published", "count_note",
    "course_era", "date_evidence_url", "distance_m", "export_bytes", "export_sha256",
    "gender_counts", "held_count", "individual_starts_available", "population", "published_count",
    "race_date", "results_sha256", "timing_basis", "weather_context", "weather_csv_sha256",
    "weather_request_url", "weather_response_sha256", "year",
}


@dataclass(frozen=True)
class PreparedBerlinLoad:
    payload: bytes
    rows: list[dict]
    table_id: str
    location: str
    capture_sha256: str

    @property
    def schema(self):
        return SCHEMA

    @property
    def order_column(self):
        return "source_row_number"

    @property
    def job_id(self):
        identity = f"{self.table_id}:{self.location}:{sha256(self.payload).hexdigest()}:{sha256(SCHEMA_BYTES).hexdigest()}"
        return f"runwx_load_{sha256(identity.encode()).hexdigest()}"

    def summary(self):
        first = self.rows[0]
        return {
            "table_id": self.table_id, "location": self.location,
            "export_schema": first["export_schema"], "race_date": first["race_date"],
            "population_basis": first["population_basis"], "course_basis": first["course_basis"],
            "captured_count": len(self.rows), "published_count": first["published_count"],
            "accepted_count": sum(row["validation_status"] == "accepted" for row in self.rows),
            "held_count": sum(row["validation_status"] == "held" for row in self.rows),
            "capture_sha256": self.capture_sha256,
            "preparation_report_sha256": first["preparation_report_sha256"],
            "export_sha256": sha256(self.payload).hexdigest(),
            "schema_sha256": sha256(SCHEMA_BYTES).hexdigest(), "input_bytes": len(self.payload),
            "race_sha256": first["race_sha256"], "weather_sha256": first["weather_sha256"],
        }


def _verified(raw: bytes, expected: str, limit: int, label: str):
    if not raw or len(raw) > limit:
        raise ValueError(f"{label} must be nonempty and at most {limit} bytes")
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(raw).hexdigest() != expected:
        raise ValueError(f"{label} SHA-256 mismatch")


def _report_context(report: dict, report_hash: str, capture_hash: str, capture_bytes: int):
    if not isinstance(report, dict) or set(report) != REPORT_FIELDS:
        raise ValueError("Berlin preparation report fields differ")
    if type(report["year"]) is not int or str(report["year"]) not in CATALOG["editions"]:
        raise ValueError("unreviewed Berlin year")
    catalog = CATALOG["editions"][str(report["year"])]
    day = catalog["date"]
    expected = {
        "race_date": day, "results_sha256": CATALOG["results_sha256"],
        "population": CATALOG["population"], "course_era": CATALOG["course_era"],
        "captured_count": catalog["captured_count"], "gender_counts": catalog["gender_counts"],
        "published_count": catalog["published_count"], "count_note": catalog["count_note"],
        "date_evidence_url": catalog["date_evidence_url"], "distance_m": 42195,
        "export_sha256": capture_hash, "export_bytes": capture_bytes, "timing_basis": None,
        "individual_starts_available": False,
        "count_difference_from_published": (catalog["captured_count"] - catalog["published_count"]
                                             if catalog["published_count"] is not None else None),
    }
    if any(report[key] != value for key, value in expected.items()):
        raise ValueError("Berlin report identity/population/export differs from reviewed inputs")
    for key in ("captured_count", "accepted_count", "held_count", "distance_m", "export_bytes"):
        if type(report[key]) is not int or report[key] < 0:
            raise ValueError("invalid Berlin report counts")
    if report["accepted_count"] + report["held_count"] != report["captured_count"]:
        raise ValueError("Berlin report counts do not reconcile")
    if (not isinstance(report["gender_counts"], dict)
            or any(type(value) is not int or value < 0 for value in report["gender_counts"].values())
            or (report["count_difference_from_published"] is not None
                and type(report["count_difference_from_published"]) is not int)):
        raise ValueError("invalid Berlin population counts")
    if report["individual_starts_available"] is not False:
        raise ValueError("individual starts must remain unavailable")
    for key in ("weather_response_sha256", "weather_csv_sha256"):
        if not isinstance(report[key], str) or not re.fullmatch(r"[0-9a-f]{64}", report[key]):
            raise ValueError("invalid Berlin weather hash")
    if not isinstance(report["weather_request_url"], str):
        raise ValueError("invalid Berlin weather request URL")
    validate_weather_request(report["weather_request_url"], day)
    metadata = _normalise_fields({
        "export_schema": "berlin_research_v1", "dataset_version": 2,
        "race_sha256": report["results_sha256"], "preparation_report_sha256": report_hash,
        "weather_sha256": report["weather_response_sha256"],
        "weather_csv_sha256": report["weather_csv_sha256"],
        "population_basis": "published_research_capture",
        "course_basis": "post_2003_course_era_not_identical_routes", "distance_m": 42195,
        "captured_count": report["captured_count"], "published_count": report["published_count"],
        "weather_context": report["weather_context"],
    }, CONTEXT_SCHEMA)
    context = metadata["weather_context"]
    start = datetime.combine(date.fromisoformat(day), time(9), tzinfo=BERLIN).astimezone(timezone.utc)
    end = datetime.combine(date.fromisoformat(day), time(15), tzinfo=BERLIN).astimezone(timezone.utc)
    weather_expected = {
        "basis": "fixed_edition_window", "timezone": "Europe/Berlin",
        "start_local": "09:00", "end_local": "15:00", "start_utc": start.isoformat(),
        "end_utc": end.isoformat(), "observation_count": 7, "requested_point": LOCATION,
        "units": {"temperature": "°C", "wind": "m/s", "precipitation": "mm", "humidity": "%"},
        "precipitation_basis": "preceding-hour amounts ending after start through end",
        "note": "Finish-area ERA5 context; not personal exposure, a race start or whole-course weather.",
    }
    if any(context[key] != value for key, value in weather_expected.items()):
        raise ValueError("Berlin fixed-window weather context differs")
    if any(abs(context["returned_point"][key] - value) > 0.5 for key, value in LOCATION.items()):
        raise ValueError("weather grid differs from Berlin proxy")
    WeatherObs(observed_at=start, temp_c=context["median_temp_c"], wind_mps=context["median_wind_mps"],
               precipitation_mm=context["precipitation_mm"], humidity_pct=context["median_humidity_pct"])
    return metadata


def prepare_berlin_load(
    capture: bytes, report_bytes: bytes, *, table_id: str, expected_sha256: str,
    expected_report_sha256: str, location: str = "europe-west1",
) -> PreparedBerlinLoad:
    """Validate the full edition before any client/credentials or load submission.

    Caller-approved hashes bind both original artifacts. No values are calculated
    from race durations except validating the source's reported time conversion.
    """
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", table_id):
        raise ValueError("expected project.dataset.table using simple identifiers")
    if location != "europe-west1":
        raise ValueError("Berlin snapshot load uses europe-west1")
    _verified(capture, expected_sha256, MAX_CAPTURE_BYTES, "Berlin capture")
    _verified(report_bytes, expected_report_sha256, MAX_REPORT_BYTES, "Berlin report")
    report = json.loads(report_bytes, object_pairs_hook=_unique_object)
    metadata = _report_context(report, expected_report_sha256, expected_sha256, len(capture))
    rows = []
    outcomes, genders = Counter(), Counter()
    previous = 0
    for line in capture.decode("utf-8").splitlines():
        row = _normalise_fields(json.loads(line, object_pairs_hook=_unique_object), RAW_SCHEMA)
        locator = row["source_row_number"]
        if (not previous < locator <= 884944
                or row["source_row_id"] != f"berlin-kaggle-v2:{CATALOG['results_sha256']}:{locator}"
                or row["race_date"] != report["race_date"]):
            raise ValueError("Berlin source identity/order/date differs")
        previous = locator
        if any(row[key] is not None for key in ("place", "age", "timing_basis")):
            raise ValueError("Berlin place, exact age and timing basis must remain unknown")
        duration, reason = validate_reported_result(row["time_raw"], row["gender_raw"])
        expected_status = "held" if reason else "accepted"
        if (row["duration_s"] != duration or row["validation_reason"] != reason
                or row["validation_status"] != expected_status):
            raise ValueError("Berlin row outcome differs from reported source fields")
        outcomes[row["validation_status"]] += 1
        genders[row["gender_raw"]] += 1
        rows.append({**row, **metadata})
    if (len(rows) != report["captured_count"] or dict(genders) != report["gender_counts"]
            or outcomes["accepted"] != report["accepted_count"] or outcomes["held"] != report["held_count"]):
        raise ValueError("Berlin capture/report counts do not reconcile")
    payload = b"".join((json.dumps(row, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()
                       for row in rows)
    if len(payload) > MAX_EXPORT_BYTES:
        raise ValueError("Berlin warehouse export exceeds 64 MiB")
    return PreparedBerlinLoad(payload, rows, table_id, location, expected_sha256)
