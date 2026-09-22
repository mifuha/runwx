"""Public response models for the historical comparison API."""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PaceSummary(ApiModel):
    median_s_per_km: float | None
    mean_s_per_km: float | None
    p25_s_per_km: float | None
    p75_s_per_km: float | None
    fastest_n: int = Field(ge=0)
    fastest_n_median_s_per_km: float | None


class WeatherSummary(ApiModel):
    matched_finishers: int = Field(ge=0)
    coverage_fraction: float | None = Field(default=None, ge=0, le=1)
    coverage_status: Literal["not_applicable", "unavailable", "partial", "complete"]
    median_temperature_c: float | None
    median_wind_mps: float | None = Field(default=None, ge=0)
    median_precipitation_mm: float | None = Field(default=None, ge=0)
    median_humidity_pct: float | None = Field(default=None, ge=0, le=100)


class BaselineChange(ApiModel):
    median_pace_pct: float | None
    speed_at_median_duration_pct: float | None


class EditionComparison(ApiModel):
    event_id: str
    year: int = Field(ge=1900, le=2200)
    started_at_utc: AwareDatetime
    comparison_status: Literal[
        "comparable",
        "different_course_or_distance",
        "unknown_timing_basis",
        "different_interpretation",
        "no_finishers",
    ]
    finishers: int = Field(ge=0)
    pace: PaceSummary
    weather: WeatherSummary
    change_from_baseline: BaselineChange


class CourseComparison(ApiModel):
    course_slug: str
    course_name: str
    course_id: str
    distance_m: int = Field(gt=0)
    baseline_event_id: str
    pace_unit: Literal["seconds_per_kilometre"] = "seconds_per_kilometre"
    editions: list[EditionComparison]


class SampledWeatherSummary(ApiModel):
    median_temperature_c: float | None
    median_wind_mps: float | None = Field(default=None, ge=0)
    median_humidity_pct: float | None = Field(default=None, ge=0, le=100)
    precipitation_mm: float | None = Field(default=None, ge=0)
    context_note: str


class TimingCounts(ApiModel):
    chip: int = Field(ge=0)
    gun: int = Field(ge=0)
    unknown: int = Field(ge=0)
    note: str


class SampledEditionComparison(ApiModel):
    event_id: str
    year: int = Field(ge=1900, le=2200)
    race_date: date
    comparison_status: Literal["descriptive_sample", "different_course_or_scope"]
    sample_size: int = Field(gt=0)
    pace: PaceSummary
    weather: SampledWeatherSummary
    timing: TimingCounts
    median_pace_change_pct: float | None


class SampledCourseComparison(ApiModel):
    course_slug: str
    course_name: str
    course_id: str
    distance_m: int = Field(gt=0)
    baseline_event_id: str
    scope: Literal["top_1000"] = "top_1000"
    sample_label: str
    sample_note: str
    pace_unit: Literal["seconds_per_kilometre"] = "seconds_per_kilometre"
    editions: list[SampledEditionComparison]
