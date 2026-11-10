"""Check the installed report image using public fixtures and fixed expectations."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
RACE = Path("data/raw/eventrac/lydd_half_2022.html")
WEATHER = Path("data/sample_lydd_weather_synthetic.csv")


def validate_report(output: bytes, hashes: dict[str, str]) -> None:
    """Use recorded expectations, without importing application calculations."""
    report = json.loads(output)
    expected = {
        "report_schema_version": 1,
        "race.course_id": "lydd-half-marathon",
        "race.distance_m": 21097,
        "race.started_at_utc": "2022-03-06T10:00:00+00:00",
        "race_summary.finisher_count": 189,
        "race_summary.median_duration_s": 6954,
        "race_summary.top_n_median_duration_s": 4953.5,
        "result_quality.candidate_count": 189,
        "result_quality.accepted_count": 189,
        "result_quality.skipped_count": 0,
        "result_quality.invalid_count": 0,
        "weather_coverage.accepted_result_count": 189,
        "weather_coverage.matched_count": 188,
        "weather_coverage.unmatched_count": 1,
        "weather_coverage.status": "partial",
        "sources.race.sha256": hashes["race"],
        "sources.weather.sha256": hashes["weather"],
        "sources.race.file": str(RACE),
        "sources.weather.file": str(WEATHER),
        "sources.weather.kind": "synthetic",
        "settings.course_id_input": "lydd-half-marathon",
        "settings.distance_m": 21097,
        "settings.timezone_name": "Europe/London",
        "settings.top_n": 20,
        "settings.top_n_effective": 20,
        "settings.max_gap_seconds": 1800,
        "settings.alignment": "nearest observation to run midpoint",
        "settings.tie_break": "earlier observation",
    }
    for key, value in expected.items():
        actual = report
        for part in key.split("."):
            if not isinstance(actual, dict) or part not in actual:
                raise ValueError(f"Report missing {key}")
            actual = actual[part]
        if isinstance(actual, bool) or actual != value:
            raise ValueError(f"Report {key}: expected {value!r}, got {actual!r}")


def validate_runs(first, second, failed, hashes):
    for result in (first, second):
        if result.returncode != 0:
            raise ValueError(f"Valid report failed (exit {result.returncode}): "
                             f"{result.stderr.decode(errors='replace')[-2000:]}")
        validate_report(result.stdout, hashes)
    if first.stdout != second.stdout:
        raise ValueError("Repeated reports differ")
    if failed.returncode == 0 or failed.returncode in (125, 126, 127):
        raise ValueError("Malformed weather did not produce an application failure")
    if failed.stdout.strip():
        raise ValueError("Malformed weather produced report output")
    if b"Invalid weather CSV row 2" not in failed.stderr:
        raise ValueError("Failure did not identify weather row 2")


def run_report(image: str, data: Path, weather: Path):
    name = f"runwx-report-check-{uuid4().hex}"
    command = [
        "docker", "run", "--rm", "--pull", "never", "--name", name,
        "--network", "none", "--read-only",
        "--mount", f"type=bind,source={data},target=/app/data,readonly",
        image, "report", "--race-html", str(RACE), "--weather-csv", str(weather),
        "--course-id", "lydd-half-marathon", "--distance-m", "21097",
        "--timezone", "Europe/London", "--top-n", "20", "--max-gap-min", "30",
        "--weather-kind", "synthetic",
    ]
    try:
        return subprocess.run(command, capture_output=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True,
                       timeout=30, check=False)
        raise


def check_image(image: str) -> None:
    inspection = subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True, timeout=30,
        check=True,
    )
    metadata = json.loads(inspection.stdout)[0]
    if metadata["Config"]["User"] not in ("10001", "10001:10001"):
        raise ValueError("Image must retain its non-root user 10001")
    image_id = metadata["Id"]  # All three runs use the same locally built image.
    hashes = {"race": sha256((ROOT / RACE).read_bytes()).hexdigest(),
              "weather": sha256((ROOT / WEATHER).read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix="runwx-report-check-") as temporary:
        data = Path(temporary) / "data"
        for relative in (RACE, WEATHER):
            target = Path(temporary) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
            target.chmod(0o644)
        bad_weather = data / "invalid-weather.csv"
        bad_weather.write_text(
            "observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct\n"
            "not-a-date,8,3,0,70\n", encoding="utf-8",
        )
        # A restrictive caller umask must not prevent the image user reading fixtures.
        for directory in (data, data / "raw", data / "raw/eventrac"):
            directory.chmod(0o755)
        bad_weather.chmod(0o644)
        first = run_report(image_id, data, WEATHER)
        second = run_report(image_id, data, WEATHER)
        failed = run_report(image_id, data, Path("data/invalid-weather.csv"))
        validate_runs(first, second, failed, hashes)
    print("PASS: installed report: 189 accepted, 188 matched, 1 unmatched; "
          "fixed statistics, settings and hashes verified.")
    print("PASS: identical rerun; malformed weather rejected at row 2 without output.")
    print(f"Image: {image_id}; user 10001; no network; read-only inputs/filesystem.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Already-built local report image")
    args = parser.parse_args()
    try:
        check_image(args.image)
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f"Container check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
