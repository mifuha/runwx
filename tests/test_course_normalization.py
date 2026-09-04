# tests/adapters/races/test_course_normalization.py
import pytest

from runwx.adapters.races.course_normalization import normalize_course_id


def test_normalize_course_id_normalizes_explicit_raw_course_id():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Whatever Event",
        raw_course_id="Sample Park 10K",
        distance_m=10_000,
    ) == "sample-park-10k"


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
