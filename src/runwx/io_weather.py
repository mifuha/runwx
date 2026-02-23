from __future__ import annotations

import csv
from pathlib import Path

from runwx.io_common import parse_datetime_iso, parse_float
from runwx.models import WeatherObs


def load_weather_csv(path: str | Path) -> list[WeatherObs]:
    """
    Load weather observations from a CSV file with columns:
      observed_at,temp_c,wind_mps,precipitation_mm
    """
    path = Path(path)
    observations: list[WeatherObs] = []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        required = {"observed_at", "temp_c", "wind_mps", "precipitation_mm"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing weather CSV columns: {sorted(missing)}")

        for row_num, row in enumerate(reader, start=2):
            try:
                obs = WeatherObs(
                    observed_at=parse_datetime_iso(row["observed_at"]),
                    temp_c=parse_float(row["temp_c"]),
                    wind_mps=parse_float(row["wind_mps"]),
                    precipitation_mm=parse_float(row["precipitation_mm"]),
                )
                observations.append(obs)
            except Exception as e:
                raise ValueError(f"Invalid weather CSV row {row_num}: {e}") from e

    return observations