"""Select a running sample from saved Great Run leaderboard/category responses."""

from dataclasses import dataclass
from datetime import date, datetime, time
import re

from pydantic import BaseModel, ConfigDict, Field

SAMPLE_SIZE = 1000
# Editions with retained traditional-course evidence. Extend after source qualification.
EDITION_IDS = {
    2006: 32, 2007: 62, 2008: 106, 2009: 137, 2010: 173, 2011: 222,
    2012: 272, 2013: 374, 2014: 437, 2015: 488, 2016: 582, 2017: 680,
    2018: 785, 2019: 881, 2022: 1149, 2023: 1191, 2024: 1252,
    2025: 1324, 2026: 1371,
}
EXCLUDED_CATEGORIES = {"Hand Cycle", "Wheelchair", "Elite Men", "Elite Women"}
SAMPLE_LABEL = "Top 1,000 only*"
SAMPLE_NOTE = (
    "Fastest 1,000 running results from the available mass-participation leaderboard, "
    "ranked by published finish time. Statistics describe this group, not all finishers."
)


class _SourceModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)


class _Result(_SourceModel):
    idResult: int = Field(gt=0)
    idRace: int = Field(gt=0)
    idRaceCategory: int = Field(gt=0)
    wheelchair: int = Field(ge=0, le=1)
    eventRace: str
    timeFinish: str
    gunChip: str | None  # Required even when the provider explicitly supplies null.


class _Race(_SourceModel):
    idRace: int = Field(gt=0)
    raceDate: str
    distanceInKm: float = Field(gt=0, allow_inf_nan=False)


class _Leaderboard(_SourceModel):
    success: bool
    raceDetail: _Race
    resultMen: list[_Result] = Field(min_length=SAMPLE_SIZE, max_length=SAMPLE_SIZE)
    resultWomen: list[_Result] = Field(min_length=SAMPLE_SIZE, max_length=SAMPLE_SIZE)


class _Category(_SourceModel):
    value: str = Field(pattern=r"^[1-9][0-9]*$")
    text: str = Field(min_length=1)


@dataclass(frozen=True)
class GreatRunSample:
    rows: tuple[dict, ...]
    source_count: int
    excluded_count: int
    cutoff_s: int
    cutoff_ties_available: int
    cutoff_ties_selected: int


def parse_greatrun_sample(
    payload: dict, categories: list, *, race_id: int, race_date: date, race_sha256: str,
) -> GreatRunSample:
    """Fail the entire sample on ambiguous input; retain no athlete identity fields."""
    source = _Leaderboard.model_validate(payload)
    event = source.raceDetail
    supplied_date = datetime.fromisoformat(event.raceDate)
    if (not source.success or event.idRace != race_id or supplied_date.date() != race_date
            or supplied_date.tzinfo is not None or supplied_date.time() != time()):
        raise ValueError("Great Run identity/date does not match the requested edition")
    if EDITION_IDS.get(race_date.year) != race_id:
        raise ValueError("edition is outside the qualified traditional-course scope")
    if event.distanceInKm != 21.1:
        raise ValueError("expected the Great North Run half-marathon distance")
    if not isinstance(categories, list):
        raise ValueError("Great Run categories must be a list")
    labels = [_Category.model_validate(item) for item in categories]
    mapping = {int(item.value): item.text.strip() for item in labels}
    if len(mapping) != len(labels) or any(not label for label in mapping.values()):
        raise ValueError("duplicate or empty Great Run category")

    seen = set()
    candidates = []
    tails = []
    excluded = 0
    locator = 0
    for group in (source.resultMen, source.resultWomen):
        previous = 0
        for row in group:
            locator += 1
            if row.idResult in seen:
                raise ValueError("duplicate Great Run result ID")
            seen.add(row.idResult)
            if row.idRace != race_id or row.eventRace != "Mass":
                raise ValueError("result belongs to a different race or event category")
            if row.idRaceCategory not in mapping:
                raise ValueError("unmapped Great Run category")
            if row.gunChip not in {None, "G", "C"}:
                raise ValueError("unknown Great Run timing flag")
            if re.fullmatch(r"[0-9]+:[0-5][0-9]:[0-5][0-9]", row.timeFinish) is None:
                raise ValueError("invalid published finish time")
            h, m, s = map(int, row.timeFinish.split(":"))
            duration = h * 3600 + m * 60 + s
            if duration <= 0 or duration < previous:
                raise ValueError("finish times must be positive and each source list ordered")
            previous = duration
            if row.wheelchair or mapping[row.idRaceCategory] in EXCLUDED_CATEGORIES:
                excluded += 1
                continue
            candidates.append((duration, row.idResult, locator, row.gunChip))
        tails.append(previous)
    chosen = sorted(candidates)[:SAMPLE_SIZE]
    if len(chosen) != SAMPLE_SIZE or any(chosen[-1][0] >= tail for tail in tails):
        raise ValueError("source truncation or a cutoff tie could change the sample")
    rows = tuple({
        "source_row_id": f"greatrun:{race_id}:{race_sha256}:{locator}",
        "source_row_number": locator,
        "sample_rank": rank,
        "duration_s": duration,
        "timing_basis": {None: "unknown", "G": "gun", "C": "chip"}[flag],
    } for rank, (duration, _, locator, flag) in enumerate(chosen, 1))
    cutoff = chosen[-1][0]
    return GreatRunSample(
        rows, locator, excluded, cutoff,
        sum(item[0] == cutoff for item in candidates),
        sum(item[0] == cutoff for item in chosen),
    )
