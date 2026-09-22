"""A small report over saved inputs; no provider client or persistence needed."""

from collections import Counter
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from runwx.adapters.csv.io_weather import parse_weather_csv
from runwx.adapters.races.saved_results import parse_saved_race_results
from runwx.services.event_weather_summary import summarize_event_weather
from runwx.services.pipeline import enrich_runs
from runwx.services.race_convert import results_to_runs
from runwx.services.race_summary import summarize_results


def build_offline_report(
    race_input: Path,
    weather_csv: Path,
    *,
    course_id: str,
    distance_m: int,
    timezone_name: str,
    top_n: int = 20,
    max_gap: timedelta = timedelta(minutes=30),
    weather_kind: str = "unknown",
    race_format: str = "eventrac_html",
    timing_basis: str | None = None,
) -> dict:
    """Hash and parse the same bytes, then reuse existing analysis functions.

    Race statistics use all accepted results. Weather statistics use matched
    results only; coverage always uses accepted results as its denominator.
    Empty populations have null summaries, not fabricated zero-valued metrics.
    """
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    if max_gap < timedelta(0):
        raise ValueError("max_gap must be non-negative")
    if weather_kind not in {"synthetic", "historical_reanalysis", "unknown"}:
        raise ValueError("weather_kind must be synthetic, historical_reanalysis or unknown")

    race_bytes = race_input.read_bytes()
    weather_bytes = weather_csv.read_bytes()
    parsed = parse_saved_race_results(
        race_bytes,
        race_format=race_format,
        course_id=course_id,
        distance_m=distance_m,
        timezone_name=timezone_name,
        timing_basis=timing_basis,
    )
    weather = parse_weather_csv(weather_bytes.decode("utf-8"))
    event = parsed.event.to_domain()
    results = [row.to_domain(event_id=event.event_id) for row in parsed.accepted]
    pipeline = enrich_runs(results_to_runs(event, results), weather, max_gap=max_gap)
    summary = summarize_results(results, top_n=top_n) if results else None
    weather_summary = summarize_event_weather(pipeline.enriched) if pipeline.enriched else None

    accepted_count = len(results)
    matched_count = len(pipeline.enriched)
    unmatched_count = len(pipeline.skipped)
    if matched_count + unmatched_count != accepted_count:
        raise RuntimeError("weather outcomes do not reconcile with accepted results")

    if not accepted_count:
        coverage_status = "not_applicable"
    elif not matched_count:
        coverage_status = "unavailable"
    elif unmatched_count:
        coverage_status = "partial"
    else:
        coverage_status = "complete"

    timing_note = "Every runner uses the event start; individual starts are unknown."
    if parsed.timing_basis is None:
        timing_note += " The chip/gun timing basis is unknown."
    limitations = [
        "Counts describe the saved result rows; full event completeness is unverified.",
        timing_note,
        "Weather coverage measures time matching, not spatial suitability or whole-race conditions.",
        "Weather medians are across matched runners; the same observation may be reused.",
        "Weather CSV has no verified location, provider or capture metadata.",
        "Replay assumes the same code and dependencies; their versions are not captured here.",
    ]
    if weather_kind == "synthetic":
        limitations.insert(0, "Weather values are synthetic demo data, not historical race conditions.")
    elif weather_kind == "historical_reanalysis":
        limitations.insert(0, "Weather is historical reanalysis, not an on-course measurement.")
    else:
        limitations.insert(0, "Weather origin is unknown; historical accuracy is unverified.")

    return {
        "report_schema_version": 1,
        "race": {
            "event_id": event.event_id,
            "name": event.name,
            "course_id": event.course_id,
            "distance_m": event.distance_m,
            "started_at_utc": event.started_at_utc.isoformat(),
            "started_at_local_interpreted": event.started_at.astimezone(
                ZoneInfo(timezone_name)
            ).isoformat(),
            "latitude": event.latitude,
            "longitude": event.longitude,
        },
        "race_summary": asdict(summary) if summary else None,
        "result_quality": {
            "candidate_count": parsed.candidate_count,
            "accepted_count": accepted_count,
            "skipped_count": len(parsed.skipped),
            "invalid_count": len(parsed.errors),
            "skipped": [asdict(row) for row in parsed.skipped],
            # Keep reasons and locators without copying raw result cells/names.
            "invalid": [
                {"row_number": row.row_number, "reason": row.reason} for row in parsed.errors
            ],
        },
        "weather_coverage": {
            "accepted_result_count": accepted_count,
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
            "matched_fraction": matched_count / accepted_count if accepted_count else None,
            "status": coverage_status,
            "unmatched_reasons": dict(Counter(row.reason for row in pipeline.skipped)),
        },
        "weather_summary": asdict(weather_summary) if weather_summary else None,
        "sources": {
            "race": {
                "file": str(race_input), "sha256": sha256(race_bytes).hexdigest(),
                "provider": event.source, "source_event_id": event.source_event_id,
            },
            "weather": {
                "file": str(weather_csv), "sha256": sha256(weather_bytes).hexdigest(),
                "kind": weather_kind, "observation_count": len(weather),
            },
        },
        "settings": {
            "course_id_input": course_id,
            "distance_m": distance_m,
            "timezone_name": timezone_name,
            "top_n": top_n,
            "top_n_effective": min(top_n, accepted_count),
            "max_gap_seconds": max_gap.total_seconds(),
            "alignment": "nearest observation to run midpoint",
            "tie_break": "earlier observation",
            "duration_precision": parsed.duration_precision,
            "timing_basis": parsed.timing_basis,
        },
        "limitations": limitations,
    }
