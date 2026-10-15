"""Prepare qualified Battersea snapshots offline using the shared artifact builders."""

import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from runwx.adapters.csv.io_weather import parse_weather_csv
from runwx.adapters.races import battersea_pdf
from runwx.services.snapshot_artifacts import build_snapshot_artifacts

SETTINGS = dict(
    course_id="battersea-park-10k", distance_m=10_000,
    timezone_name="Europe/London", race_format="battersea_pdf",
    timing_basis=None, weather_kind="historical_reanalysis", race_kind="historical",
)
FIELDS = ("temperature_2m", "wind_speed_10m", "precipitation", "relative_humidity_2m")
EXPECTED_UNITS = {
    "time": "iso8601", "temperature_2m": "°C", "wind_speed_10m": "m/s",
    "precipitation": "mm", "relative_humidity_2m": "%",
}


class EditionInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    race_pdf: str = Field(min_length=1)
    weather_json: str = Field(min_length=1)
    weather_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    weather_request_url: str = Field(min_length=1)


class PreparationConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    version: int = Field(ge=1, le=1)
    editions: list[EditionInput] = Field(min_length=1)


def _validate_request(url: str, race_date: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "archive-api.open-meteo.com"
            or parsed.path != "/v1/archive" or parsed.fragment):
        raise ValueError("weather request must be the saved Open-Meteo archive URL")
    query = parse_qs(parsed.query, keep_blank_values=True)
    expected = {
        "latitude": str(battersea_pdf.VENUE_LATITUDE),
        "longitude": str(battersea_pdf.VENUE_LONGITUDE),
        "start_date": race_date, "end_date": race_date,
        "models": "era5", "timezone": "UTC", "wind_speed_unit": "ms",
    }
    if set(query) != set(expected) | {"hourly"}:
        raise ValueError("weather request settings differ from the qualified request")
    if any(query[key] != [value] for key, value in expected.items()):
        raise ValueError("weather request date, venue, model, timezone or units differ")
    hourly = query["hourly"]
    if len(hourly) != 1 or sorted(hourly[0].split(",")) != sorted(FIELDS):
        raise ValueError("weather request hourly fields differ")


def weather_csv(raw: bytes, race_date: str) -> bytes:
    """Preserve the CSV bytes used in the qualified 13- and five-edition batches."""
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("weather response must be a JSON object")
    if payload.get("utc_offset_seconds") != 0 or payload.get("hourly_units") != EXPECTED_UNITS:
        raise ValueError("weather timezone/units changed")
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("weather hourly data missing")
    expected_hours = [f"{race_date}T{hour:02d}:00" for hour in range(24)]
    if hourly.get("time") != expected_hours or any(
        not isinstance(hourly.get(key), list) or len(hourly[key]) != 24 for key in FIELDS
    ):
        raise ValueError("incomplete weather hours or wrong weather date")
    text = StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(("observed_at", "temp_c", "wind_mps", "precipitation_mm", "humidity_pct"))
    for hour in range(24):
        values = [hourly[key][hour] for key in FIELDS]
        if any(type(value) not in (int, float) for value in values):
            raise ValueError(f"invalid weather observation at hour {hour}")
        writer.writerow((datetime.fromisoformat(hourly["time"][hour]).replace(
            tzinfo=timezone.utc).isoformat(), *values))
    # Reuse the existing finite-number and physical-range validation for all hours.
    parse_weather_csv(text.getvalue())
    return text.getvalue().encode("utf-8")


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def prepare_battersea(config_path: Path, output: Path) -> dict:
    """Validate the complete batch before writing any final output artifacts."""
    config_path = config_path.resolve()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output directory already exists: {output}")
    config = PreparationConfig.model_validate_json(config_path.read_bytes())
    dates = [edition.date for edition in config.editions]
    if len(set(dates)) != len(dates):
        raise ValueError("duplicate edition dates")
    for day in dates:
        if day not in battersea_pdf.QUALIFIED_EDITIONS:
            raise ValueError(f"{day}: edition is not qualified")

    summaries = []
    with TemporaryDirectory(prefix="runwx-battersea-") as tmp:
        staging = Path(tmp)
        for edition in sorted(config.editions, key=lambda item: item.date):
            day = edition.date
            try:
                catalog = battersea_pdf.QUALIFIED_EDITIONS[day]
                _validate_request(edition.weather_request_url, day)
                race = (config_path.parent / edition.race_pdf).resolve()
                weather = (config_path.parent / edition.weather_json).resolve()
                race_bytes, weather_bytes = race.read_bytes(), weather.read_bytes()
                if sha256(race_bytes).hexdigest() != catalog["result_sha256"]:
                    raise ValueError("PDF hash changed")
                if sha256(weather_bytes).hexdigest() != edition.weather_sha256:
                    raise ValueError("weather response hash changed")
                csv_path = staging / f"{day}.weather.csv"
                csv_path.write_bytes(weather_csv(weather_bytes, day))
                # The builders read the same verified bytes even if source files change later.
                race_copy = staging / f"{day}.pdf"
                race_copy.write_bytes(race_bytes)
                artifacts = build_snapshot_artifacts(race_copy, csv_path, **SETTINGS)
                race_copy.unlink()
                report = artifacts.report
                quality, coverage = report["result_quality"], report["weather_coverage"]
                if not (quality["candidate_count"] == quality["accepted_count"] == catalog["result_count"]
                        and quality["skipped_count"] == quality["invalid_count"] == 0):
                    raise ValueError("result counts differ from the qualified catalog")
                if datetime.fromisoformat(report["race"]["started_at_utc"]).date().isoformat() != day:
                    raise ValueError("parsed race date differs from configuration")
                report["sources"]["race"]["file"] = str(race)
                report["sources"]["weather"]["file"] = str(output / csv_path.name)
                report_bytes = _json_bytes(report)
                (staging / f"{day}.report.json").write_bytes(report_bytes)
                (staging / f"{day}.ndjson").write_bytes(artifacts.result_payload)
                summaries.append({
                    "date": day, "race_pdf": str(race), "weather_json": str(weather),
                    "pdf_sha256": catalog["result_sha256"],
                    "weather_request_url": edition.weather_request_url,
                    "era5_response_sha256": edition.weather_sha256,
                    "weather_csv_sha256": report["sources"]["weather"]["sha256"],
                    "report_sha256": sha256(report_bytes).hexdigest(),
                    "export_sha256": artifacts.result_sha256,
                    **quality,
                    "weather_matched_count": coverage["matched_count"],
                    "weather_unmatched_count": coverage["unmatched_count"],
                    "start_utc": report["race"]["started_at_utc"],
                })
            except (OSError, ValueError, RuntimeError) as exc:
                raise ValueError(f"{day}: {exc}") from exc
        summary = {
            "version": 1, "status": "prepared_locally", "edition_count": len(summaries),
            "settings": {**SETTINGS, "top_n": 20, "max_gap_seconds": 1800},
            "editions": summaries,
            **{key: sum(item[key] for item in summaries) for key in (
                "candidate_count", "accepted_count", "skipped_count", "invalid_count",
                "weather_matched_count", "weather_unmatched_count",
            )},
        }
        # No final directory exists until every edition has passed. Write the summary last.
        output.mkdir(parents=True, exist_ok=False)
        for artifact in sorted(staging.iterdir()):
            (output / artifact.name).write_bytes(artifact.read_bytes())
        (output / "preparation.json").write_bytes(_json_bytes(summary))
    return summary
