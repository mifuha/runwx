"""Prepare saved GNR snapshots offline, then load them through the existing loader."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from time import monotonic
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from runwx.adapters.bigquery.gnr_sample_load import SCHEMA_BYTES, prepare_sample_load
from runwx.adapters.bigquery.result_load import load_prepared
from runwx.adapters.races.greatrun_json import CATALOG_BYTES, EDITION_DATES, EDITION_IDS
from runwx.services.gnr_sample_export import _json, build_gnr_sample_rows
from runwx.services.result_export import encode_result_rows


class BatchError(ValueError):
    """A batch failed; any available details are retained in its summary file."""


class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


class EditionInput(_Model):
    year: int = Field(ge=2000, le=9999)
    race_json: str = Field(min_length=1)
    categories_json: str = Field(min_length=1)
    weather_json: str = Field(min_length=1)
    weather_request: str = Field(min_length=1)
    race_capture: str | None = None
    categories_capture: str | None = None
    table_id: str | None = None


class AnalyticsSettings(_Model):
    dataset: str = Field(pattern=r"^runwx_dbt_gnr_[A-Za-z0-9_]+$")
    baseline_year: int
    maximum_bytes_billed: int = Field(default=104857600, gt=0)


class BatchConfig(_Model):
    version: int = Field(ge=1, le=1)
    project: str = Field(pattern=r"^[a-z][a-z0-9-]{4,61}[a-z0-9]$")
    location: Literal["europe-west1"] = "europe-west1"
    staging_dataset: Literal["runwx_staging"] = "runwx_staging"
    editions: list[EditionInput] = Field(min_length=1)
    analytics: AnalyticsSettings | None = None


class InputReference(_Model):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PreparedEdition(_Model):
    year: int
    export_file: str
    table_id: str
    export_sha256: str
    planned_load_job_id: str
    inputs: dict[str, InputReference]
    summary: dict


class BatchPlan(_Model):
    version: int = Field(ge=1, le=1)
    status: Literal["prepared_locally"]
    project: str
    location: Literal["europe-west1"]
    staging_dataset: Literal["runwx_staging"]
    configuration: InputReference
    catalog_sha256: str
    schema_sha256: str
    destination_existence: Literal["not_checked"]
    editions: list[PreparedEdition] = Field(min_length=1)
    analytics: AnalyticsSettings | None = None


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}


def _check_reference(reference):
    if sha256(Path(reference.path).read_bytes()).hexdigest() != reference.sha256:
        raise BatchError(f"prepared input changed: {reference.path}")


def _capture(path, source, race_id, *, categories=False):
    record = _json(path.read_bytes())
    raw = source.read_bytes()
    if (not isinstance(record, dict) or record.get("sha256") != sha256(raw).hexdigest()
            or record.get("bytes") != len(raw) or record.get("status", 200) != 200):
        raise BatchError(f"capture record does not match source bytes: {path.name}")
    keys = ("url",) if categories else ("requested_url", "returned_url")
    for key in keys:
        raw_url = record.get(key)
        if not isinstance(raw_url, str):
            raise BatchError(f"capture URL must be a string: {path.name}")
        url = urlsplit(raw_url)
        query = parse_qs(url.query)
        endpoint = "/utility/getracecategory" if categories else "/leaderboard/getleaderboardraceresults"
        id_key = "selectedIdRace" if categories else "raceId"
        if (url.scheme != "https" or url.netloc != "results.greatrun.org"
                or url.path != endpoint or url.fragment or query.get(id_key) != [str(race_id)]
                or (not categories and query.get("eventCategory") != ["Mass"])):
            raise BatchError(f"capture URL differs from qualified edition: {path.name}")
    return record["sha256"]


def _prepare_edition(config, edition, base):
    year = edition.year
    if year not in EDITION_IDS:
        raise BatchError("edition is outside the reviewed GNR catalog")
    paths = {key: (base / getattr(edition, key)).resolve() for key in
             ("race_json", "categories_json", "weather_json", "weather_request")}
    for kind in ("race", "categories"):
        supplied = getattr(edition, f"{kind}_capture")
        paths[f"{kind}_capture"] = ((base / supplied).resolve() if supplied else
                                    Path(str(paths[f"{kind}_json"]) + ".capture.json"))
    references = {key: _reference(path) for key, path in paths.items()}
    race_hash = _capture(paths["race_capture"], paths["race_json"], EDITION_IDS[year])
    categories_hash = _capture(paths["categories_capture"], paths["categories_json"],
                               EDITION_IDS[year], categories=True)
    rows = build_gnr_sample_rows(
        *(paths[key] for key in ("race_json", "categories_json", "weather_json", "weather_request")),
        race_id=EDITION_IDS[year], race_date=EDITION_DATES[year], race_sha256=race_hash,
        categories_sha256=categories_hash, weather_sha256=references["weather_json"]["sha256"],
    )
    for reference in references.values():
        _check_reference(InputReference.model_validate(reference))
    payload = encode_result_rows(rows)
    table = edition.table_id or f"gnr_{year}_{race_hash[:12]}"
    if not re.fullmatch(rf"gnr_{year}_[0-9a-f]{{12}}", table):
        raise BatchError("table_id must use gnr_<year>_<12 lowercase hex digits>")
    prepared = prepare_sample_load(
        payload, table_id=f"{config.project}.{config.staging_dataset}.{table}",
        expected_sha256=sha256(payload).hexdigest(), location=config.location,
    )
    return {
        "year": year, "export_file": f"{year}.ndjson", "table_id": prepared.table_id,
        "export_sha256": sha256(payload).hexdigest(), "planned_load_job_id": prepared.job_id,
        "inputs": references, "summary": prepared.summary(),
    }, payload


def prepare_batch(config_path: Path, output_dir: Path) -> dict:
    """Collect all edition errors offline; write no executable plan unless all pass."""
    config_path, output_dir = Path(config_path).resolve(), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "errors": [], "editions": [],
              "destination_existence": "not_checked"}
    try:
        config_ref = _reference(config_path)
        config = BatchConfig.model_validate(_json(config_path.read_bytes()))
        years = [item.year for item in config.editions]
        if len(set(years)) != len(years):
            raise BatchError("configuration repeats an edition year")
        if config.analytics and (len(years) < 2 or config.analytics.baseline_year not in years):
            raise BatchError("analytics requires at least two editions including the baseline year")
        prepared = []
        for edition in sorted(config.editions, key=lambda item: item.year):
            try:
                entry, payload = _prepare_edition(config, edition, config_path.parent)
                prepared.append((entry, payload))
                report["editions"].append({"year": edition.year, "status": "valid",
                                           "table_id": entry["table_id"]})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                report["errors"].append({"year": edition.year, "error": str(exc)})
        if report["errors"]:
            raise BatchError(f"{len(report['errors'])} edition(s) failed preparation")
        plan = BatchPlan(
            version=1, status="prepared_locally", project=config.project,
            location=config.location, staging_dataset=config.staging_dataset,
            configuration=InputReference.model_validate(config_ref),
            catalog_sha256=sha256(CATALOG_BYTES).hexdigest(),
            schema_sha256=sha256(SCHEMA_BYTES).hexdigest(), destination_existence="not_checked",
            editions=[PreparedEdition.model_validate(entry) for entry, _ in prepared],
            analytics=config.analytics,
        ).model_dump(mode="json")
        for entry, payload in prepared:
            (output_dir / entry["export_file"]).write_bytes(payload)
        _write_json(output_dir / "plan.json", plan)
        digest = sha256((output_dir / "plan.json").read_bytes()).hexdigest()
        (output_dir / "plan.sha256").write_text(digest + "\n")
        report.update(status="prepared_locally", plan_sha256=digest,
                      edition_count=len(prepared), sample_count=1000 * len(prepared))
        return report
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if not report["errors"]:
            report["errors"].append({"error": str(exc)})
        raise BatchError(str(exc)) from exc
    finally:
        _write_json(output_dir / "preparation.json", report)


def _read_prepared(plan_path):
    raw = plan_path.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != plan_path.with_suffix(".sha256").read_text().strip():
        raise BatchError("prepared plan changed; prepare again")
    plan = BatchPlan.model_validate(_json(raw))
    if (plan.catalog_sha256 != sha256(CATALOG_BYTES).hexdigest()
            or plan.schema_sha256 != sha256(SCHEMA_BYTES).hexdigest()):
        raise BatchError("catalog or export schema changed; prepare again")
    _check_reference(plan.configuration)
    if len({e.year for e in plan.editions}) != len(plan.editions):
        raise BatchError("prepared plan repeats an edition")
    loads, errors = [], []
    for entry in plan.editions:
        try:
            for reference in entry.inputs.values():
                _check_reference(reference)
            if entry.export_file != f"{entry.year}.ndjson":
                raise BatchError("unexpected export path")
            if not re.fullmatch(
                    rf"{re.escape(plan.project)}\.{plan.staging_dataset}\.gnr_{entry.year}_[0-9a-f]{{12}}",
                    entry.table_id):
                raise BatchError("destination differs from batch project/dataset/year")
            prepared = prepare_sample_load(
                (plan_path.parent / entry.export_file).read_bytes(), table_id=entry.table_id,
                expected_sha256=entry.export_sha256, location=plan.location,
            )
            if prepared.summary() != entry.summary or prepared.job_id != entry.planned_load_job_id:
                raise BatchError("export summary or load job identity changed")
            loads.append(prepared)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{entry.year}: {exc}")
    if errors:
        raise BatchError("Batch preflight failed: " + "; ".join(errors))
    return plan, loads, digest


def execute_batch(plan_path: Path, output_dir: Path, *, client=None) -> dict:
    """Revalidate all local inputs before credentials or loads; never skip from a log."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    record = {"status": "running", "stage": "preflight", "editions": [],
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    record_path = output_dir / "execution.json"
    started, owned_client = monotonic(), False
    try:
        plan, loads, digest = _read_prepared(Path(plan_path).resolve())
        record.update(plan_sha256=digest, project=plan.project, location=plan.location)
        record["editions"] = [
            {"year": e.year, "table_id": e.table_id, "status": "not_run",
             "planned_load_job_id": e.planned_load_job_id} for e in plan.editions]
        _write_json(record_path, record)
        if client is None:
            from google.cloud import bigquery

            client = bigquery.Client(project=plan.project, location=plan.location)
            owned_client = True
        record["stage"] = "load"
        for entry, prepared in zip(record["editions"], loads):
            entry["status"] = "running"
            _write_json(record_path, record)
            edition_start = monotonic()
            try:
                entry["result"] = load_prepared(client, prepared)
                entry["status"] = entry["result"]["status"]
            except Exception as exc:
                entry.update(status="failed", error_type=type(exc).__name__, error=str(exc))
                raise
            finally:
                entry["elapsed_seconds"] = round(monotonic() - edition_start, 3)
                _write_json(record_path, record)
        record.update(status="loaded_verified", stage="complete",
                      analytical_status="not_run")
        return record
    except Exception as exc:
        record.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise BatchError(f"Batch failed during {record['stage']}; see {record_path}: {exc}") from exc
    finally:
        record["elapsed_seconds"] = round(monotonic() - started, 3)
        record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_json(record_path, record)
        if owned_client:
            client.close()
