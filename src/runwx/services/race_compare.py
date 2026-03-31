from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from runwx.services.race_analysis import RaceAnalysis


@dataclass(frozen=True)
class RaceComparisonRow:
    event_id: str
    started_at: datetime
    course_id: str
    distance_m: int
    finisher_count: int
    median_duration_s: float
    top_n_median_duration_s: float
    median_temp_c: float
    median_wind_mps: float
    median_humidity_pct: float
    median_precipitation_mm: float


def compare_race_analyses(
    analyses: Sequence[RaceAnalysis],
    *,
    course_id: str | None = None,
) -> list[RaceComparisonRow]:
    if not analyses:
        raise ValueError("analyses must not be empty")

    selected = list(analyses)

    if course_id is not None:
        selected = [analysis for analysis in selected if analysis.event.course_id == course_id]
        if not selected:
            raise ValueError(f"no analyses found for course_id={course_id!r}")

    course_ids = {analysis.event.course_id for analysis in selected}

    if len(course_ids) != 1:
        raise ValueError("analyses must all share the same course_id")

    shared_course_id = next(iter(course_ids))
    if shared_course_id is None:
        raise ValueError("course_id is required for multi-event comparison")

    selected.sort(key=lambda analysis: analysis.event.started_at_utc)

    return [
        RaceComparisonRow(
            event_id=analysis.event.event_id,
            started_at=analysis.event.started_at_utc,
            course_id=shared_course_id,
            distance_m=analysis.event.distance_m,
            finisher_count=analysis.summary.finisher_count,
            median_duration_s=analysis.summary.median_duration_s,
            top_n_median_duration_s=analysis.summary.top_n_median_duration_s,
            median_temp_c=analysis.weather_summary.median_temp_c,
            median_wind_mps=analysis.weather_summary.median_wind_mps,
            median_humidity_pct=analysis.weather_summary.median_humidity_pct,
            median_precipitation_mm=analysis.weather_summary.median_precipitation_mm,
        )
        for analysis in selected
    ]