"""Logical analysis identity, execution receipts and an explicit selection."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from typing import Literal


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class RevisionIdentity:
    event_id: str
    race_sha256: str
    weather_source_id: str
    weather_sha256: str
    code_sha256: str
    settings_json: str
    race_kind: str
    snapshot_scope: str

    def __post_init__(self):
        for value in (self.event_id, self.weather_source_id):
            if not value or value != value.strip():
                raise ValueError("source identities must be nonempty and trimmed")
        for value in (self.race_sha256, self.weather_sha256, self.code_sha256):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("expected a lowercase SHA-256")
        if self.snapshot_scope != "complete":
            raise ValueError("revision selection requires a verified complete snapshot; partial inputs need a policy")
        if self.race_kind not in {"synthetic", "unknown"}:
            raise ValueError("race_kind must be synthetic or unknown")
        object.__setattr__(self, "settings_json", canonical_json(json.loads(self.settings_json)))

    @property
    def settings(self) -> dict:
        return json.loads(self.settings_json)  # A copy, not mutable identity state.

    @property
    def revision_id(self) -> str:
        identity = asdict(self)
        del identity["settings_json"]
        identity["settings"] = self.settings
        identity["revision_schema_version"] = 1
        return sha256(canonical_json(identity).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    revision_id: str
    status: Literal["running", "succeeded", "failed"]
    race_file: str
    weather_file: str
    error: str | None = None


@dataclass(frozen=True)
class Selection:
    event_id: str
    revision_id: str
    successful_attempt_id: str
