"""Adversarial checks of the installed-image verifier, without Docker."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


SPEC = importlib.util.spec_from_file_location(
    "report_container_check",
    Path(__file__).resolve().parents[1] / "scripts/check_report_container.py",
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
HASHES = {"race": "a" * 64, "weather": "b" * 64}


@pytest.fixture
def report():
    return {
        "report_schema_version": 1,
        "race": {"course_id": "lydd-half-marathon", "distance_m": 21097,
                 "started_at_utc": "2022-03-06T10:00:00+00:00"},
        "race_summary": {"finisher_count": 189, "median_duration_s": 6954,
                         "top_n_median_duration_s": 4953.5},
        "result_quality": {"candidate_count": 189, "accepted_count": 189,
                           "skipped_count": 0, "invalid_count": 0},
        "weather_coverage": {"accepted_result_count": 189, "matched_count": 188,
                             "unmatched_count": 1, "status": "partial"},
        "sources": {
            "race": {"sha256": HASHES["race"], "file": str(checker.RACE)},
            "weather": {"sha256": HASHES["weather"], "file": str(checker.WEATHER),
                        "kind": "synthetic"},
        },
        "settings": {"course_id_input": "lydd-half-marathon", "distance_m": 21097,
                     "timezone_name": "Europe/London", "top_n": 20,
                     "top_n_effective": 20, "max_gap_seconds": 1800,
                     "alignment": "nearest observation to run midpoint",
                     "tie_break": "earlier observation"},
    }


def result(code=0, output=b"", error=b""):
    return subprocess.CompletedProcess([], code, output, error)


def test_successful_pair_and_deliberate_failure(report):
    good = result(output=json.dumps(report).encode())
    checker.validate_runs(good, good, result(1, error=b"Invalid weather CSV row 2"), HASHES)


@pytest.mark.parametrize("section,key,value", [
    ("result_quality", "accepted_count", 188),
    ("weather_coverage", "matched_count", 189),
    ("weather_coverage", "unmatched_count", True),
    ("race_summary", "median_duration_s", 6900),
    ("race_summary", "top_n_median_duration_s", 4953),
    ("settings", "timezone_name", "UTC"),
    ("settings", "max_gap_seconds", 900),
])
def test_wrong_values_rejected(report, section, key, value):
    report[section][key] = value
    with pytest.raises(ValueError, match=f"{section}.{key}"):
        checker.validate_report(json.dumps(report).encode(), HASHES)


def test_missing_statistic_rejected(report):
    del report["race_summary"]["median_duration_s"]
    with pytest.raises(ValueError, match="missing race_summary.median_duration_s"):
        checker.validate_report(json.dumps(report).encode(), HASHES)


@pytest.mark.parametrize("key,value", [("sha256", "c" * 64), ("kind", "unknown")])
def test_wrong_weather_provenance_rejected(report, key, value):
    report["sources"]["weather"][key] = value
    with pytest.raises(ValueError, match=f"sources.weather.{key}"):
        checker.validate_report(json.dumps(report).encode(), HASHES)


def test_byte_differences_rejected_even_when_values_match(report):
    good = result(output=json.dumps(report).encode())
    other = result(output=good.stdout + b"\n")
    with pytest.raises(ValueError, match="reports differ"):
        checker.validate_runs(good, other, result(1), HASHES)


@pytest.mark.parametrize("failure", [
    result(), result(125), result(126), result(127),
    result(1, output=b"{}", error=b"Invalid weather CSV row 2"),
    result(1, error=b"unrelated failure"),
])
def test_false_failure_evidence_rejected(report, failure):
    good = result(output=json.dumps(report).encode())
    with pytest.raises(ValueError):
        checker.validate_runs(good, good, failure, HASHES)


def test_valid_run_must_succeed(report):
    bad = result(1, json.dumps(report).encode())
    with pytest.raises(ValueError, match="Valid report failed"):
        checker.validate_runs(bad, bad, result(1), HASHES)


def test_container_isolation(monkeypatch, tmp_path):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 120
        return result()
    monkeypatch.setattr(checker.subprocess, "run", run)
    checker.run_report("sha256:example", tmp_path, checker.WEATHER)
    command = calls[0]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--mount") + 1] == (
        f"type=bind,source={tmp_path},target=/app/data,readonly"
    )
    assert command[command.index("--pull") + 1] == "never"
    assert "--user" not in command
    assert "--env" not in command


def test_root_image_rejected_before_execution(monkeypatch):
    def inspect(command, **kwargs):
        assert command[:3] == ["docker", "image", "inspect"]
        return result(output=b'[{"Config": {"User": "0"}, "Id": "example"}]')
    monkeypatch.setattr(checker.subprocess, "run", inspect)
    with pytest.raises(ValueError, match="non-root"):
        checker.check_image("example")


def test_timeout_removes_only_its_own_container(monkeypatch, tmp_path):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 120)
        return result()
    monkeypatch.setattr(checker.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        checker.run_report("example", tmp_path, checker.WEATHER)
    name = calls[0][calls[0].index("--name") + 1]
    assert calls[1] == ["docker", "rm", "--force", name]
