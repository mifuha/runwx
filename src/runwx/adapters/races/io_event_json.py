from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from runwx.adapters.races.schemas import RaceEventIn
from runwx.domain.race import RaceEvent


def load_event_json(path: str | Path) -> RaceEvent:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    try:
        return RaceEventIn.model_validate(raw).to_domain()
    except ValidationError as e:
        raise ValueError(f"Invalid event JSON {path}: {e}") from e