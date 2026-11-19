import csv
from statistics import covariance, median, variance

import pytest

from finish_time import EVIDENCE, HOURLY_FILE, estimate


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_estimates_and_omissions_match_covariance_calculation():
    summaries = read_rows(EVIDENCE / "summaries.csv")
    durations = {
        row["race_date"]: float(row["median_duration_s"])
        for row in summaries if row["view"] == "fixed_mix"
    }
    weather = read_rows(EVIDENCE / HOURLY_FILE)
    result = estimate(EVIDENCE, summaries)

    def expected(last_hour, omitted=None):
        rows = [row for row in weather if row["race_date"][:4] != omitted]
        temperatures = [
            median(float(row[f"{hour:02}:00"]) for hour in range(9, last_hour + 1))
            for row in rows
        ]
        times = [durations[row["race_date"]] / 60 for row in rows]
        return 5 * covariance(temperatures, times) / variance(temperatures)

    assert result["09:00–15:00"] == pytest.approx(expected(15), abs=1e-12)
    assert result["09:00–12:00"] == pytest.approx(expected(12), abs=1e-12)
    omitted = result["omit_one_edition_09:00–15:00"]
    assert set(omitted) == {date[:4] for date in durations}
    for year, value in omitted.items():
        assert value == pytest.approx(expected(15, year), abs=1e-12)


def test_changed_hourly_weather_is_rejected(tmp_path):
    (tmp_path / "manifest.json").write_bytes((EVIDENCE / "manifest.json").read_bytes())
    weather = (EVIDENCE / HOURLY_FILE).read_bytes()
    (tmp_path / HOURLY_FILE).write_bytes(weather + b"\n")
    with pytest.raises(ValueError, match="hourly temperature evidence hash changed"):
        estimate(tmp_path, read_rows(EVIDENCE / "summaries.csv"))
