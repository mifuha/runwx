from __future__ import annotations

from typing import Sequence

from runwx.domain.models import Run
from runwx.domain.race import RaceEvent, RaceResult


def results_to_runs(event: RaceEvent, results: Sequence[RaceResult]) -> list[Run]:
    return [r.to_run(event) for r in results]