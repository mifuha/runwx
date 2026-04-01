# tests/adapters/races/test_course_normalization.py
from runwx.adapters.races.course_normalization import normalize_course_id


def test_normalize_course_id_maps_known_raw_alias_to_canonical():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Whatever Event",
        raw_course_id="Sample Park 10K",
    ) == "sample-park-10k"


def test_normalize_course_id_falls_back_to_event_name_alias_when_raw_missing():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="2025 Sample Park 10 km",
        raw_course_id=None,
    ) == "sample-park-10k"


def test_normalize_course_id_keeps_unknown_raw_course_id_as_normalized_slug():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Whatever Event",
        raw_course_id="Provider Specific Course 01",
    ) == "provider-specific-course-01"


def test_normalize_course_id_returns_none_when_no_raw_or_known_name():
    assert normalize_course_id(
        source="demo",
        source_event_id="event-1",
        name="Completely Unknown Event",
        raw_course_id=None,
    ) is None