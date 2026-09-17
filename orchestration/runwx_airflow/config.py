"""Explicit historical execution settings; no credentials or cloud calls."""

from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

import stage_runner
from runwx.adapters.gcs.report_io import object_path


Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Stage(StrictModel):
    job: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")]
    image: Annotated[str, Field(pattern=r"^.+@sha256:[0-9a-f]{64}$")]
    source_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    output_prefix: str

    @model_validator(mode="after")
    def storage_prefix(self):
        object_path(self.output_prefix)
        if self.output_prefix.endswith("/"):
            raise ValueError("output_prefix must not end with a slash")
        return self


class ReportSettings(StrictModel):
    course_id: str
    distance_m: Annotated[int, Field(gt=0)]
    timezone_name: str
    race_kind: str
    weather_kind: str
    export_weather_kind: str
    timing_basis: str
    top_n: Annotated[int, Field(gt=0)]
    max_gap_minutes: Annotated[int, Field(ge=0)]


class Report(Stage):
    race_uri: str
    race_sha256: Hash
    weather_uri: str
    weather_sha256: Hash
    settings: ReportSettings


class Dbt(Stage):
    config: dict
    expectations: dict


class Pipeline(StrictModel):
    project: str
    region: Annotated[str, Field(pattern=r"^[a-z]+-[a-z]+[0-9]$")]
    table_id: str
    export_sha256: Hash
    report: Report
    dbt: Dbt

    @model_validator(mode="after")
    def coherent_snapshot(self):
        config = stage_runner.validate_config(self.dbt.config)
        expected = stage_runner.validate_expectations(self.dbt.expectations, config)
        if self.project != config["project"] or self.region != config["location"]:
            raise ValueError("pipeline and dbt project/location must agree")
        if self.region != "europe-west1":
            raise ValueError("the existing snapshot loader requires europe-west1")
        table = f"{self.project}.{config['source_dataset']}.{config['source_table']}"
        if self.table_id != table:
            raise ValueError("loader destination must be the dbt source table")
        if self.report.job == self.dbt.job:
            raise ValueError("report and dbt must be separate jobs")
        object_path(self.report.race_uri)
        object_path(self.report.weather_uri)
        settings = self.report.settings
        ZoneInfo(settings.timezone_name)
        if (settings.race_kind != "historical"
                or settings.weather_kind != "unknown"
                or settings.export_weather_kind != "historical_reanalysis"
                or settings.timing_basis != "chip"):
            raise ValueError("this DAG requires historical race and weather inputs")
        mart = expected["edition"]["mart"]
        wanted = {
            "race_sha256": self.report.race_sha256,
            "weather_sha256": self.report.weather_sha256,
            "course_id_input": settings.course_id,
            "distance_m": settings.distance_m,
            "timezone_name": settings.timezone_name,
            "race_kind": settings.race_kind,
            "weather_kind": settings.export_weather_kind,
            "timing_basis": settings.timing_basis,
            "top_n_requested": settings.top_n,
            "max_gap_seconds": settings.max_gap_minutes * 60,
        }
        if any(mart.get(key) != value for key, value in wanted.items()):
            raise ValueError("report settings/hashes must match frozen dbt expectations")
        if settings.top_n != config["top_n"]:
            raise ValueError("report and dbt top_n must agree")
        return self


def validate_config(value):
    return Pipeline.model_validate(value).model_dump()
