"""Provider-neutral outcomes from one saved race-result snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from runwx.adapters.races.schemas import RaceEventIn, RaceResultIn


@dataclass(frozen=True)
class SkippedRaceRow:
    """An expected skip, numbered from 1 among candidate result rows."""

    row_number: int
    reason: str


@dataclass(frozen=True)
class InvalidRaceRow:
    """A rejected source row and any safe provider values retained for diagnosis."""

    row_number: int
    reason: str
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class RaceParseResult:
    """Reconciled outcomes for one structurally valid saved result snapshot."""

    event: RaceEventIn
    accepted: tuple[RaceResultIn, ...]
    skipped: tuple[SkippedRaceRow, ...]
    errors: tuple[InvalidRaceRow, ...] = ()
    accepted_row_numbers: tuple[int, ...] = ()
    duration_precision: str = "whole seconds; fractions truncated"
    timing_basis: str | None = None

    @property
    def candidate_count(self) -> int:
        return len(self.accepted) + len(self.skipped) + len(self.errors)
