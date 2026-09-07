from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from pydantic import ValidationError

from runwx.adapters.csv.schemas import WeatherObsIn
from runwx.domain.models import WeatherObs


def load_weather_csv(path: str | Path) -> list[WeatherObs]:
    """
    Load weather observations from a CSV file with columns:
      observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct
    """
    return parse_weather_csv(Path(path).read_text(encoding="utf-8"))


def parse_weather_csv(text: str) -> list[WeatherObs]:
    """Parse saved CSV text with the same validation as the file loader."""
    observations: list[WeatherObs] = []
    reader = csv.DictReader(StringIO(text, newline=""))

    required = {"observed_at", "temp_c", "wind_mps", "precipitation_mm", "humidity_pct"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Missing weather CSV columns: {sorted(missing)}")

    for row_num, row in enumerate(reader, start=2):
        try:
            obs = WeatherObsIn.model_validate(row).to_domain()
            observations.append(obs)
        except ValidationError as e:
            raise ValueError(f"Invalid weather CSV row {row_num}: {e}") from e

    return observations
