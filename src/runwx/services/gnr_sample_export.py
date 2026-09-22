"""Offline GNR sample export with shared event-window weather, not runner matches."""

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from statistics import median
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from runwx.adapters.races.greatrun_json import (
    SAMPLE_LABEL, SAMPLE_NOTE, SAMPLE_SIZE, parse_greatrun_sample,
)
from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse
from runwx.adapters.weather.translate import to_weather_obs

LOCATION = {"latitude": 54.984, "longitude": -1.620}
LONDON = ZoneInfo("Europe/London")


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON field")
    return result


def _nonfinite(value):
    raise ValueError("non-finite JSON number")


def _json(raw: bytes):
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite)


def _verified_bytes(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(raw).hexdigest() != expected:
        raise ValueError(f"SHA-256 mismatch: {path.name}")
    return raw


def _weather_context(raw: bytes, request_raw: bytes, day: date) -> dict:
    params = {
        **LOCATION, "start_date": day.isoformat(), "end_date": day.isoformat(),
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "models": "era5", "timezone": "UTC", "temperature_unit": "celsius",
        "wind_speed_unit": "ms", "precipitation_unit": "mm",
    }
    request = _json(request_raw)
    if not isinstance(request, dict):
        raise ValueError("weather request must be an object")
    if (request.get("params") != params or request.get("provider") != "Open-Meteo"
            or request.get("dataset") != "ERA5" or request.get("status") != 200
            or request.get("sha256") != sha256(raw).hexdigest()
            or request.get("bytes") != len(raw)):
        raise ValueError("weather request does not match ERA5 settings and captured bytes")
    url = urlsplit(request.get("url", ""))
    if (url.scheme != "https" or url.netloc != "archive-api.open-meteo.com"
            or url.path != "/v1/archive" or url.fragment
            or parse_qs(url.query) != {key: [str(value)] for key, value in params.items()}):
        raise ValueError("weather request URL does not match its settings")
    payload = _json(raw)
    if not isinstance(payload, dict):
        raise ValueError("weather response must be an object")
    units = {"time": "iso8601", "temperature_2m": "°C", "relative_humidity_2m": "%",
             "wind_speed_10m": "m/s", "precipitation": "mm"}
    if (payload.get("utc_offset_seconds") != 0 or payload.get("timezone") not in {"GMT", "UTC"}
            or payload.get("hourly_units") != units):
        raise ValueError("weather must use UTC and the expected units")
    for key, limit in (("latitude", 90), ("longitude", 180)):
        value = payload.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit:
            raise ValueError("invalid weather grid location")
        if abs(value - LOCATION[key]) > 0.5:
            raise ValueError("weather grid is not near the requested Newcastle start area")
    observations = to_weather_obs(OpenMeteoArchiveResponse.model_validate(payload))
    midnight = datetime.combine(day, time(), tzinfo=timezone.utc)
    if [o.observed_at for o in observations] != [midnight + timedelta(hours=h) for h in range(24)]:
        raise ValueError("weather must contain exactly the requested 24-hour UTC day")
    start = datetime.combine(day, time(10), tzinfo=LONDON).astimezone(timezone.utc)
    end = datetime.combine(day, time(14), tzinfo=LONDON).astimezone(timezone.utc)
    window = [o for o in observations if start <= o.observed_at <= end]
    rain = [o for o in window if o.observed_at > start]
    if len(window) != 5 or len(rain) != 4:
        raise ValueError("incomplete local weather window")
    return {
        "basis": "fixed_event_window",
        "note": "Start-area ERA5 context; not individual runner exposure or whole-course weather.",
        "timezone": "Europe/London", "start_local": "10:00", "end_local": "14:00",
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "hourly_observation_count": len(window),
        "requested_latitude": LOCATION["latitude"], "requested_longitude": LOCATION["longitude"],
        "grid_latitude": payload["latitude"], "grid_longitude": payload["longitude"],
        "median_temp_c": median(o.temp_c for o in window),
        "median_wind_mps": median(o.wind_mps for o in window),
        "median_humidity_pct": median(o.humidity_pct for o in window),
        "precipitation_mm": round(sum(o.precipitation_mm for o in rain), 6),
        "precipitation_basis": "sum of preceding-hour amounts ending after start through end",
    }


def build_gnr_sample_rows(
    race_json: Path, categories_json: Path, weather_json: Path, weather_request: Path,
    *, race_id: int, race_date: date, race_sha256: str, categories_sha256: str,
    weather_sha256: str,
) -> list[dict]:
    """Validate all inputs before returning any rows. Paths never enter the export.

    This contract deliberately differs from the full-field/midpoint export. Its
    sample ranks are not race places and its weather is shared edition context.
    """
    race_raw = _verified_bytes(race_json, race_sha256)
    categories_raw = _verified_bytes(categories_json, categories_sha256)
    weather_raw = _verified_bytes(weather_json, weather_sha256)
    request_raw = weather_request.read_bytes()
    sample = parse_greatrun_sample(
        _json(race_raw), _json(categories_raw), race_id=race_id, race_date=race_date,
        race_sha256=race_sha256,
    )
    context = _weather_context(weather_raw, request_raw, race_date)
    common = {
        "export_schema": "gnr_sample_v1",
        "event_id": f"greatrun:{race_id}", "race_date": race_date.isoformat(),
        "course_id": "great-north-run-traditional", "distance_m": 21100,
        "distance_basis": "provider distanceInKm",
        "race_kind": "historical", "weather_kind": "historical_reanalysis",
        "race_sha256": race_sha256, "categories_sha256": categories_sha256,
        "weather_sha256": weather_sha256, "weather_request_sha256": sha256(request_raw).hexdigest(),
        "sample": {
            "label": SAMPLE_LABEL, "note": SAMPLE_NOTE, "size": SAMPLE_SIZE,
            "selection": "published finish seconds then provider result ID",
            "source_count": sample.source_count, "excluded_count": sample.excluded_count,
            "unselected_count": sample.source_count - sample.excluded_count - SAMPLE_SIZE,
            "cutoff_s": sample.cutoff_s, "cutoff_ties_available": sample.cutoff_ties_available,
            "cutoff_ties_selected": sample.cutoff_ties_selected,
            "timing_note": "Published chip/gun/unknown basis retained per row; no timing correction.",
        },
        "weather_context": context,
    }
    return [{**common, **row} for row in sample.rows]
