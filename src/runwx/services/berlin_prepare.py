"""Prepare saved Berlin research captures and fixed-window weather offline."""

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import math
from pathlib import Path
import shutil
from statistics import median
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from runwx.adapters.races.berlin_csv import CATALOG, iter_research_rows
from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse
from runwx.adapters.weather.translate import to_weather_obs

BERLIN = ZoneInfo("Europe/Berlin")
LOCATION = {"latitude": 52.5163, "longitude": 13.3777}
FIELDS = ("temperature_2m", "wind_speed_10m", "precipitation", "relative_humidity_2m")
UNITS = dict(time="iso8601", temperature_2m="°C", wind_speed_10m="m/s",
             precipitation="mm", relative_humidity_2m="%")


class EditionInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    year: int
    weather_json: str = Field(min_length=1)
    weather_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    weather_request_url: str = Field(min_length=1)


class PreparationConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    version: int = Field(ge=1, le=1)
    race_csv: str = Field(min_length=1)
    editions: list[EditionInput] = Field(min_length=1, max_length=16)


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON field")
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique_object)


def validate_weather_request(request_url: str, day: str) -> None:
    """Check the recorded request without network access or provider authentication."""
    url = urlsplit(request_url)
    if (url.scheme != "https" or url.netloc != "archive-api.open-meteo.com"
            or url.path != "/v1/archive" or url.fragment):
        raise ValueError("expected saved Open-Meteo archive request URL")
    query = parse_qs(url.query, keep_blank_values=True)
    expected = {**{key: str(value) for key, value in LOCATION.items()},
                "start_date": day, "end_date": day, "models": "era5",
                "timezone": "Europe/Berlin", "wind_speed_unit": "ms"}
    optional = {"temperature_unit": "celsius", "precipitation_unit": "mm"}
    if (set(query) - set(optional) != set(expected) | {"hourly"}
            or any(query.get(key) != [value] for key, value in expected.items())
            or any(key in query and query[key] != [value] for key, value in optional.items())
            or len(query.get("hourly", [])) != 1
            or sorted(query["hourly"][0].split(",")) != sorted(FIELDS)):
        raise ValueError("weather request date/location/model/timezone/units differ")


def _weather(raw: bytes, request_url: str, day: str):
    """Validate local-day ERA5, then reuse the shared UTC/domain translation."""
    validate_weather_request(request_url, day)
    payload = _json(raw)
    if not isinstance(payload, dict):
        raise ValueError("weather response must be an object")
    offset = datetime.fromisoformat(day).replace(tzinfo=BERLIN).utcoffset()
    if (payload.get("timezone") != "Europe/Berlin"
            or payload.get("utc_offset_seconds") != offset.total_seconds()
            or payload.get("hourly_units") != UNITS):
        raise ValueError("weather timezone or units differ")
    for key, limit in (("latitude", 90), ("longitude", 180)):
        value = payload.get(key)
        if (type(value) not in (int, float) or not math.isfinite(value)
                or abs(value) > limit or abs(value - LOCATION[key]) > 0.5):
            raise ValueError("weather grid is not near the Berlin proxy")
    hourly = payload.get("hourly")
    if (not isinstance(hourly, dict)
            or hourly.get("time") != [f"{day}T{hour:02}:00" for hour in range(24)]
            or any(not isinstance(hourly.get(key), list) or len(hourly[key]) != 24
                   or any(type(v) not in (int, float) for v in hourly[key]) for key in FIELDS)):
        raise ValueError("weather must contain all 24 local hours with numeric values")
    utc_times = [datetime.fromisoformat(stamp).replace(tzinfo=BERLIN)
                 .astimezone(timezone.utc).isoformat() for stamp in hourly["time"]]
    translated = {**payload, "hourly": {**hourly, "time": utc_times}}
    observations = to_weather_obs(OpenMeteoArchiveResponse.model_validate(translated))
    text = StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(("observed_at", "temp_c", "wind_mps", "precipitation_mm", "humidity_pct"))
    for obs in observations:
        writer.writerow((obs.observed_at.isoformat(), obs.temp_c, obs.wind_mps,
                         obs.precipitation_mm, obs.humidity_pct))
    start = datetime.fromisoformat(day + "T09:00").replace(tzinfo=BERLIN).astimezone(timezone.utc)
    end = start + timedelta(hours=6)
    window = [obs for obs in observations if start <= obs.observed_at <= end]
    if len(window) != 7:
        raise ValueError("incomplete fixed edition weather window")
    context = {
        "basis": "fixed_edition_window", "timezone": "Europe/Berlin",
        "start_local": "09:00", "end_local": "15:00",
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "observation_count": 7, "requested_point": LOCATION,
        "returned_point": {key: payload[key] for key in LOCATION},
        "units": {"temperature": "°C", "wind": "m/s", "precipitation": "mm", "humidity": "%"},
        "median_temp_c": median(obs.temp_c for obs in window),
        "median_wind_mps": median(obs.wind_mps for obs in window),
        "median_humidity_pct": median(obs.humidity_pct for obs in window),
        "precipitation_mm": round(sum(obs.precipitation_mm for obs in window if obs.observed_at > start), 6),
        "precipitation_basis": "preceding-hour amounts ending after start through end",
        "note": "Finish-area ERA5 context; not personal exposure, a race start or whole-course weather.",
    }
    return text.getvalue().encode(), context


def prepare_berlin(config_path: Path, output: Path) -> dict:
    """Stage all selected editions before publishing a new completed directory.

    The CSV is copied and hashed once before parsing. Rows stream to disk; the
    source hash and original data-record number identify captures, not athletes.
    """
    config_path = config_path.resolve()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output directory already exists: {output}")
    config = PreparationConfig.model_validate(_json(config_path.read_bytes()))
    years = [edition.year for edition in config.editions]
    if len(set(years)) != len(years):
        raise ValueError("duplicate edition years")
    for year in years:
        if str(year) not in CATALOG["editions"]:
            raise ValueError(f"{year}: outside the reviewed Berlin research cohort")
    with TemporaryDirectory(prefix="runwx-berlin-") as tmp:
        staging = Path(tmp)
        source = staging / "source.csv"
        digest = sha256()
        with (config_path.parent / config.race_csv).open("rb") as src, source.open("wb") as dest:
            while chunk := src.read(1024 * 1024):
                digest.update(chunk)
                dest.write(chunk)
        source_hash = digest.hexdigest()
        if source_hash != CATALOG["results_sha256"]:
            raise ValueError("Berlin research CSV hash differs from pinned Kaggle v2")
        reports = {}
        for edition in sorted(config.editions, key=lambda item: item.year):
            year = edition.year
            catalog = CATALOG["editions"][str(year)]
            day = catalog["date"]
            try:
                raw = (config_path.parent / edition.weather_json).read_bytes()
                if sha256(raw).hexdigest() != edition.weather_sha256:
                    raise ValueError("weather response hash changed")
                weather_csv, context = _weather(raw, edition.weather_request_url, day)
                (staging / f"{day}.weather.csv").write_bytes(weather_csv)
                reports[year] = {
                    "year": year, "race_date": day, "distance_m": 42195,
                    "population": CATALOG["population"], "course_era": CATALOG["course_era"],
                    "timing_basis": None, "individual_starts_available": False,
                    "captured_count": 0, "accepted_count": 0, "held_count": 0,
                    "gender_counts": {}, "published_count": catalog["published_count"],
                    "count_note": catalog["count_note"],
                    "date_evidence_url": catalog["date_evidence_url"],
                    "weather_response_sha256": edition.weather_sha256,
                    "weather_request_url": edition.weather_request_url,
                    "weather_csv_sha256": sha256(weather_csv).hexdigest(),
                    "weather_context": context,
                }
            except (OSError, ValueError) as exc:
                raise ValueError(f"{year} ({day}): {exc}") from exc
        hashes = {year: sha256() for year in years}
        genders = {year: Counter() for year in years}
        input_count = unselected_count = 0
        with ExitStack() as stack:
            streams = {year: stack.enter_context((staging / f"{report['race_date']}.ndjson").open("wb"))
                       for year, report in reports.items()}
            for year, row in iter_research_rows(source, set(years), source_hash):
                input_count += 1
                if row is None:
                    unselected_count += 1
                    continue
                report = reports[year]
                report["captured_count"] += 1
                report["accepted_count" if row["validation_status"] == "accepted" else "held_count"] += 1
                genders[year][row["gender_raw"]] += 1
                encoded = _json_bytes(row)
                streams[year].write(encoded)
                hashes[year].update(encoded)
        source.unlink()
        for year, report in reports.items():
            catalog = CATALOG["editions"][str(year)]
            report["gender_counts"] = dict(genders[year])
            if report["captured_count"] != catalog["captured_count"] or report["gender_counts"] != catalog["gender_counts"]:
                raise ValueError(f"{year}: captured population differs from reviewed catalog")
            report["count_difference_from_published"] = (
                report["captured_count"] - report["published_count"] if report["published_count"] is not None else None)
            report["export_sha256"] = hashes[year].hexdigest()
            report["export_bytes"] = (staging / f"{report['race_date']}.ndjson").stat().st_size
            report["results_sha256"] = source_hash
            (staging / f"{report['race_date']}.report.json").write_bytes(_json_bytes(report))
        summary = {
            "preparation_schema": "berlin_research_preparation_v1", "status": "prepared_locally",
            "dataset_url": CATALOG["dataset_url"], "dataset_version": 2, "license": CATALOG["license"],
            "results_sha256": source_hash, "catalog_sha256": sha256(_json_bytes(CATALOG)).hexdigest(),
            "population": CATALOG["population"], "course_era": CATALOG["course_era"],
            "course_evidence_url": CATALOG["course_evidence_url"],
            "published_counts_url": CATALOG["published_counts_url"],
            "published_counts_note": CATALOG["published_counts_note"],
            "input_record_count": input_count, "unselected_record_count": unselected_count,
            "edition_count": len(reports), "editions": list(reports.values()),
            **{key: sum(report[key] for report in reports.values()) for key in
               ("captured_count", "accepted_count", "held_count")},
        }
        if (summary["captured_count"] != summary["accepted_count"] + summary["held_count"]
                or input_count != summary["captured_count"] + unselected_count):
            raise RuntimeError("Berlin preparation counts do not reconcile")
        # A filesystem interruption may leave an incomplete directory. Summary is last.
        output.mkdir(parents=True, exist_ok=False)
        for artifact in sorted(staging.iterdir()):
            shutil.copyfile(artifact, output / artifact.name)
        (output / "preparation.json").write_bytes(_json_bytes(summary))
    return summary
