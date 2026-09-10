# tests/adapters/races/test_course_normalization.py
import pytest

from runwx.adapters.races.course_normalization import normalize_course_id
from runwx.adapters.races.schemas import RaceEventIn


@pytest.mark.parametrize(
    ("raw_course_id", "expected"),
    [
        ("Sample Park 10K", "sample-park-10k"),
        ("Lydd Half Marathon", "lydd-half-marathon"),
        ("  Café 10K  ", "cafe-10k"),
    ],
)
def test_normalize_course_id_normalizes_explicit_raw_course_id(raw_course_id, expected):
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Whatever Event",
        raw_course_id=raw_course_id,
        distance_m=10_000,
    ) == expected


@pytest.mark.parametrize("raw_course_id", ["---", " !@#$ ", "東京"])
@pytest.mark.parametrize("name", ["Lydd Half Marathon 2022", "Unknown Event"])
def test_normalize_course_id_rejects_explicit_id_that_normalizes_to_empty(raw_course_id, name):
    with pytest.raises(ValueError, match="explicit course_id normalizes to an empty ID"):
        normalize_course_id(
            source="eventrac",
            source_event_id="21723",
            name=name,
            raw_course_id=raw_course_id,
            distance_m=21_097,
        )


def test_event_conversion_rejects_empty_normalized_id_instead_of_inferring_alias():
    event_in = RaceEventIn(
        source="eventrac",
        source_event_id="21723",
        name="Lydd Half Marathon 2022",
        started_at="2022-03-06T10:00:00+00:00",
        distance_m=21_097,
        latitude=50.954438,
        longitude=0.902385,
        course_id="---",
    )

    with pytest.raises(ValueError, match="explicit course_id normalizes to an empty ID"):
        event_in.to_domain()


def test_normalize_course_id_falls_back_to_event_name_alias_when_raw_missing():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="2025 Sample Park 10 km",
        raw_course_id=None,
        distance_m=10_000,
    ) == "sample-park-10k"


def test_normalize_course_id_keeps_unknown_raw_course_id_as_normalized_slug():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Whatever Event",
        raw_course_id="Provider Specific Course 01",
        distance_m=10_000,
    ) == "provider-specific-course-01"


def test_normalize_course_id_returns_none_when_no_raw_or_known_name():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Completely Unknown Event",
        raw_course_id=None,
        distance_m=10_000,
    ) is None


def test_normalize_course_id_whitespace_only_raw_falls_back_to_known_event_name():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="2025 Sample Park 10 km",
        raw_course_id="   \t",
        distance_m=10_000,
    ) == "sample-park-10k"


def test_normalize_course_id_whitespace_only_raw_unknown_event_name_returns_none():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Completely Unknown Event",
        raw_course_id="   ",
        distance_m=10_000,
    ) is None


@pytest.mark.parametrize(
    "name",
    [
        "Lydd Half Marathon",
        "Lydd Half Marathon 2022",
        "2022 Lydd Half Marathon",
        "Brett Lydd Half Marathon",
        "Brett Lydd Half Marathon 2022",
    ],
)
def test_normalize_course_id_maps_lydd_half_aliases_to_canonical(name):
    assert normalize_course_id(
        source="eventrac",
        source_event_id="21723",
        name=name,
        raw_course_id=None,
        distance_m=21_097,
    ) == "lydd-half-marathon"


def test_normalize_course_id_does_not_map_known_name_at_different_distance():
    assert normalize_course_id(
        source="eventrac",
        source_event_id="21723",
        name="Lydd Half Marathon 2022",
        raw_course_id=None,
        distance_m=20_000,
    ) is None


def test_normalize_course_id_preserves_versioned_manual_route_override():
    assert normalize_course_id(
        source="eventrac",
        source_event_id="21723",
        name="Lydd Half Marathon 2022",
        raw_course_id="lydd-half-marathon-2024-route",
        distance_m=21_097,
    ) == "lydd-half-marathon-2024-route"
