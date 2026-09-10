"""Reject unusable observations at ingestion, before aggregation/serialization."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from runwx.adapters.csv.io_weather import parse_weather_csv
from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse
from runwx.domain.models import WeatherObs


FIELDS = [
    ("temp_c", "temperature_2m"),
    ("wind_mps", "wind_speed_10m"),
    ("precipitation_mm", "precipitation"),
    ("humidity_pct", "relative_humidity_2m"),
]
VALID = {"temp_c": -2.5, "wind_mps": 0.0, "precipitation_mm": 0.0, "humidity_pct": 100.0}


@pytest.mark.parametrize("field", [field for field, _ in FIELDS])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_csv_rejects_nonfinite_weather_with_row_and_field(field, value):
    row = {key: str(number) for key, number in VALID.items()}
    row[field] = value
    csv_text = (
        "observed_at," + ",".join(row) + "\n"
        "2026-02-01T10:00:00Z," + ",".join(row.values()) + "\n"
    )

    with pytest.raises(ValueError, match="Invalid weather CSV row 2") as error:
        parse_weather_csv(csv_text)

    assert isinstance(error.value.__cause__, ValidationError)
    detail = error.value.__cause__.errors()[0]
    assert detail["loc"] == (field,)
    assert detail["type"] == "finite_number"


@pytest.mark.parametrize("field", [field for _, field in FIELDS])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_api_rejects_nonfinite_hourly_measurement_at_its_index(field, value):
    hourly = {api_field: [VALID[domain_field]] for domain_field, api_field in FIELDS}
    hourly["time"] = ["2026-02-01T10:00"]
    hourly[field] = [value]
    payload = {
        "latitude": 51.5, "longitude": -0.1, "timezone": "UTC",
        "utc_offset_seconds": 0, "hourly": hourly,
    }

    with pytest.raises(ValidationError) as error:
        OpenMeteoArchiveResponse.model_validate(payload)

    detail = error.value.errors()[0]
    assert detail["loc"] == ("hourly", field, 0)
    assert detail["type"] == "finite_number"


@pytest.mark.parametrize("field", [field for field, _ in FIELDS])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_domain_cannot_bypass_finite_weather_requirement(field, value):
    values = {**VALID, field: value}
    with pytest.raises(ValueError, match=f"{field} must be finite"):
        WeatherObs(observed_at=datetime(2026, 2, 1, 10, tzinfo=timezone.utc), **values)


def test_csv_keeps_finite_negative_temperature_and_range_boundaries():
    observations = parse_weather_csv(
        "observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct\n"
        "2026-02-01T10:00:00Z,-2.5,0,0,100\n"
    )
    assert observations == [WeatherObs(
        observed_at=datetime(2026, 2, 1, 10, tzinfo=timezone.utc), **VALID,
    )]
