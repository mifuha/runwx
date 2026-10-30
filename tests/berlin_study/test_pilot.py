"""Hand-calculated controls for this local study; no real inputs required."""
from collections import Counter
from hashlib import sha256
import json
from math import isclose, sqrt
from pathlib import Path
import socket

import pytest

from check_prepared import histogram_median, read_capture
from offline_guard import install
from pilot import (GROUPS, add_row, associations, checked_bytes, group_stats,
                   pearson, run, validate_configuration)


def sample_rows(ys=(2, 4, 6, 8), xs=(1, 2, 3, 4)):
    return [{"year": 2000 + i, "group": group, "median_temp_c": x,
             "median_pace_s_per_km": y + offset}
            for i, (x, y) in enumerate(zip(xs, ys))
            for group, offset in zip(GROUPS, (0, 10, -10))]


@pytest.mark.parametrize("values,expected", [([120, 60, 180], 120),
    ([60, 120, 180, 240], 150), ([60, 60, 180], 60)])
def test_hand_calculated_medians(values, expected):
    actual = group_stats(values)
    assert actual["median_duration_s"] == expected
    assert actual["median_pace_s_per_km"] == expected / 42.195
    assert actual["count"] == len(values)
    assert histogram_median(Counter(values)) == expected


def test_groups_duplicates_and_held():
    groups = {"female": [], "male": []}
    for gender, duration, status in [("female", 60, "accepted"), ("female", 60, "accepted"),
                                     ("female", 180, "accepted"), ("male", 240, "accepted"),
                                     ("male", None, "held")]:
        add_row(groups, {"gender_raw": gender, "duration_s": duration, "validation_status": status})
    assert groups == {"female": [60, 60, 180], "male": [240]}
    assert group_stats(groups["female"])["median_duration_s"] == 60
    assert group_stats(groups["male"])["median_duration_s"] == 240


@pytest.mark.parametrize("gender,duration,status", [("unknown", 60, "accepted"),
    ("male", True, "accepted"), ("female", 0, "accepted"), ("male", 30, "held"),
    ("male", 30, "skipped")])
def test_unusable_or_unreviewed_values_rejected(gender, duration, status):
    with pytest.raises(ValueError):
        add_row({"female": [], "male": []}, {"gender_raw": gender, "duration_s": duration,
                                             "validation_status": status})


@pytest.mark.parametrize("xs,ys", [([1, 1, 1], [2, 3, 4]), ([1, 2, 3], [4, 4, 4])])
def test_constant_is_undefined_not_zero(xs, ys):
    assert pearson(xs, ys) == {"value": None, "reason": "constant series"}
    json.dumps(pearson(xs, ys), allow_nan=False)


def test_hand_calculated_pearson():
    assert isclose(pearson([1, 2, 3], [2, 4, 6])["value"], 1)
    assert isclose(pearson([1, 2, 3], [6, 4, 2])["value"], -1)
    # x=[1,2,3], y=[1,3,2]: sum cross deviations=1, each sum square=2 => r=.5.
    assert isclose(pearson([1, 2, 3], [1, 3, 2])["value"], .5)
    assert pearson([1, 2], [1, 2])["value"] is None


def test_every_omission_removes_whole_edition():
    output = associations(sample_rows())
    assert output["independent_weather_observations"] == 4
    for group in GROUPS:
        series = output["series"][group]
        assert len(series["leave_one_out"]) == 4
        for omission in series["leave_one_out"]:
            assert omission["omitted_year"] not in omission["included_years"]
            assert len(omission["included_years"]) == omission["edition_count"] == 3
            assert isclose(omission["value"], 1)


def test_influential_edition():
    # Removing the final point returns x=[1,2,3], y=[1,2,3], exactly r=1.
    result = associations(sample_rows(ys=(1, 2, 3, -10)))
    for group in GROUPS:
        series = result["series"][group]
        assert series["pearson_r"]["value"] < 0
        assert series["most_influential_omission"]["omitted_year"] == 2003
        assert isclose(series["most_influential_omission"]["value"], 1)
        assert 2003 in series["direction_change_omissions"]
        assert series["edition_count"] == 4


@pytest.mark.parametrize("mode", ["missing", "duplicate", "different_weather"])
def test_incomplete_or_inconsistent_series_rejected(mode):
    rows = sample_rows()
    if mode == "missing":
        rows.pop()
    elif mode == "duplicate":
        rows.append(dict(rows[0]))
    else:
        rows[1]["median_temp_c"] += 1
    with pytest.raises(ValueError):
        associations(rows)


def test_altered_hash_and_missing_input(tmp_path):
    path = tmp_path / "weather.json"
    path.write_bytes(b'{}')
    digest = sha256(path.read_bytes()).hexdigest()
    assert checked_bytes(path, digest, "weather") == b'{}'
    path.write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError, match="weather: hash changed"):
        checked_bytes(path, digest, "weather")
    with pytest.raises(FileNotFoundError):
        checked_bytes(tmp_path / "missing.json", digest, "weather")


def test_output_directory_preserved(tmp_path):
    out = tmp_path / "already-here"
    out.mkdir()
    marker = out / "keep.txt"
    marker.write_text("retain")
    with pytest.raises(FileExistsError):
        run(tmp_path / "nonexistent.json", out)
    assert marker.read_text() == "retain"


def test_invalid_config_leaves_no_output(tmp_path):
    config = tmp_path / "bad.json"
    config.write_text('{"schema":"wrong"}')
    out = tmp_path / "no-completed-output"
    with pytest.raises((KeyError, ValueError)):
        run(config, out)
    assert not out.exists()


def test_independent_reader_keeps_duplicates_excludes_held(tmp_path):
    rows = [{"gender_raw": "female", "time_raw": "00:01:00", "duration_s": 60,
             "validation_status": "accepted"}] * 2 + [
        {"gender_raw": "male", "time_raw": "not a time", "duration_s": None,
         "validation_status": "held"}]
    raw = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    path = tmp_path / "capture.ndjson"
    path.write_bytes(raw)
    groups, outcomes = read_capture(path, sha256(raw).hexdigest())
    assert groups == {"female": Counter({60: 2}), "male": Counter()}
    assert outcomes == Counter(accepted=2, held=1)
    assert histogram_median(groups["female"]) == 60


def test_network_is_blocked():
    import subprocess, sys
    code = "from offline_guard import install; install(); import socket; socket.socket()"
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[2] / 'analysis/berlin', capture_output=True, text=True)
    assert result.returncode != 0
    assert 'offline pilot blocks socket' in result.stderr
