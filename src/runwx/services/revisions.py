"""Local, sequential revision/selection contract; no database or cloud writes."""

from dataclasses import dataclass, replace
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from runwx.domain.revisions import Attempt, RevisionIdentity, Selection, canonical_json
from runwx.services.offline_report import build_offline_report


def processing_code_sha256() -> str:
    """Identify saved package source, including uncommitted Python changes.

    Run in a fresh process after editing. This records source bytes, not installed
    dependency versions or a container image. Paths are relative to the package.
    """
    root = Path(__file__).resolve().parents[1]
    hashes = {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
              for path in sorted(root.rglob("*.py"))}
    return sha256(canonical_json(hashes).encode("utf-8")).hexdigest()


def prepare_revision(
    race_html: Path, weather_csv: Path, *, event_id: str,
    weather_source_id: str, snapshot_scope: str, course_id: str,
    distance_m: int, timezone_name: str, race_kind: str = "unknown",
    weather_kind: str = "unknown", top_n: int = 20,
    max_gap: timedelta = timedelta(minutes=30),
) -> RevisionIdentity:
    """Bind one complete snapshot analysis to sources, settings and current code.

    Completeness and weather source identity are caller assertions. The synthetic
    fixture is a known complete set of five candidates, including rejected rows.
    Moving a file does not change identity; changing its bytes does.
    """
    if type(top_n) is not int or top_n <= 0:
        raise ValueError("top_n must be a positive integer")
    if type(distance_m) is not int or distance_m <= 0:
        raise ValueError("distance_m must be a positive integer")
    if max_gap < timedelta(0):
        raise ValueError("max_gap must be non-negative")
    if weather_kind not in {"synthetic", "unknown"}:
        raise ValueError("weather_kind must be synthetic or unknown")
    settings = {
        "course_id": course_id, "distance_m": distance_m,
        "timezone_name": timezone_name, "weather_kind": weather_kind,
        "top_n": top_n, "max_gap_seconds": max_gap.total_seconds(),
    }
    return RevisionIdentity(
        event_id=event_id, race_sha256=sha256(race_html.read_bytes()).hexdigest(),
        weather_source_id=weather_source_id,
        weather_sha256=sha256(weather_csv.read_bytes()).hexdigest(),
        code_sha256=processing_code_sha256(), settings_json=canonical_json(settings),
        race_kind=race_kind, snapshot_scope=snapshot_scope,
    )


def _check_report(revision: RevisionIdentity, report: dict) -> None:
    """Gate success on identity and accounting; retain normal row rejections."""
    if report["race"]["event_id"] != revision.event_id:
        raise ValueError("report event differs from revision source identity")
    if (report["sources"]["race"]["sha256"] != revision.race_sha256
            or report["sources"]["weather"]["sha256"] != revision.weather_sha256):
        raise ValueError("report source hashes differ from prepared revision")
    expected = revision.settings
    for name in ("distance_m", "timezone_name", "top_n", "max_gap_seconds"):
        if report["settings"][name] != expected[name]:
            raise ValueError("report settings differ from prepared revision")
    if (report["settings"]["course_id_input"] != expected["course_id"]
            or report["sources"]["weather"]["kind"] != expected["weather_kind"]):
        raise ValueError("report interpretation differs from prepared revision")
    quality, coverage, summary = (
        report["result_quality"], report["weather_coverage"], report["race_summary"]
    )
    accepted = quality["accepted_count"]
    counts = [quality[f"{name}_count"] for name in ("candidate", "accepted", "skipped", "invalid")]
    weather_counts = [coverage["matched_count"], coverage["unmatched_count"]]
    if (any(type(n) is not int or n < 0 for n in counts + weather_counts)
            or counts[0] != sum(counts[1:])
            or quality["skipped_count"] != len(quality["skipped"])
            or quality["invalid_count"] != len(quality["invalid"])
            or coverage["accepted_result_count"] != accepted
            or sum(weather_counts) != accepted
            or coverage["matched_fraction"] != (weather_counts[0] / accepted if accepted else None)
            or (summary["finisher_count"] if summary else 0) != accepted):
        raise ValueError("report counts do not reconcile")


def _analytical_json(report: dict) -> str:
    comparison = json.loads(canonical_json(report))
    for source in ("race", "weather"):
        comparison["sources"][source].pop("file")
    return canonical_json(comparison)


@dataclass(frozen=True)
class _SuccessfulRevision:
    identity: RevisionIdentity
    report_json: str
    attempt_id: str


class RevisionSession:
    """Keep candidates and selection separate within one local process.

    No automatic promotion, persistence, concurrent publication or retry loop.
    Reports are stored as JSON so callers cannot mutate a successful candidate.
    """

    def __init__(self):
        self._revisions: dict[str, RevisionIdentity] = {}
        self._attempts: dict[str, Attempt] = {}
        self._successful: dict[str, _SuccessfulRevision] = {}
        self._selected: dict[str, Selection] = {}

    @property
    def attempts(self) -> tuple[Attempt, ...]:
        return tuple(self._attempts.values())

    @property
    def successful_revision_ids(self) -> tuple[str, ...]:
        return tuple(self._successful)

    def run(self, revision: RevisionIdentity, race_html: Path, weather_csv: Path) -> Attempt:
        attempt = Attempt(str(uuid4()), revision.revision_id, "running",
                          str(race_html), str(weather_csv))
        self._revisions.setdefault(revision.revision_id, revision)
        self._attempts[attempt.attempt_id] = attempt
        try:
            if revision.code_sha256 != processing_code_sha256():
                raise ValueError("processing code differs from prepared revision")
            settings = revision.settings
            settings["max_gap"] = timedelta(seconds=settings.pop("max_gap_seconds"))
            report = build_offline_report(race_html, weather_csv, **settings)
            _check_report(revision, report)
            existing = self._successful.get(revision.revision_id)
            if existing and _analytical_json(json.loads(existing.report_json)) != _analytical_json(report):
                raise ValueError("same revision produced different analytical output")
            # Preserve the first successful report, including its original paths.
            candidate = _SuccessfulRevision(revision, canonical_json(report), attempt.attempt_id)
            self._successful.setdefault(revision.revision_id, candidate)
        except Exception as error:
            self._attempts[attempt.attempt_id] = replace(
                attempt, status="failed", error=f"{type(error).__name__}: {error}"
            )
            raise  # Unexpected errors remain errors, never skipped race rows.
        completed = replace(attempt, status="succeeded")
        self._attempts[attempt.attempt_id] = completed
        return completed

    def select(self, event_id: str, revision_id: str) -> Selection:
        candidate = self._successful.get(revision_id)
        if candidate is None:
            raise ValueError("selection requires a successful revision")
        if candidate.identity.event_id != event_id:
            raise ValueError("cannot select a revision from another event")
        selection = Selection(event_id, revision_id, candidate.attempt_id)
        self._selected[event_id] = selection
        return selection

    def selection(self, event_id: str) -> Selection | None:
        return self._selected.get(event_id)

    def revision(self, revision_id: str) -> RevisionIdentity:
        return self._revisions[revision_id]

    def report(self, revision_id: str) -> dict:
        return json.loads(self._successful[revision_id].report_json)

    def selected_report(self, event_id: str) -> dict | None:
        selected = self.selection(event_id)
        return self.report(selected.revision_id) if selected else None
