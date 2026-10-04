"""Battersea's saved PDF must not silently change the result population."""

from __future__ import annotations

from hashlib import sha256

import pytest

from runwx.adapters.races import battersea_pdf
from runwx.adapters.races.saved_results import parse_saved_race_results
from runwx.services.offline_report import build_offline_report
from runwx.services.result_export import build_result_rows


ROWS = (
    "Sri Chinmoy 10K Race\nBattersea Park, London\n21st May 2022\n"
    "WINNERS\n1 Winner 00:31:00\n"
    "ALL RESULTS BELOW\nRESULTS\nRANK NAME TIME\n"
    "1Runner One Male00:31:00\n"
    "2 Runner Two Female 00:31:00\n"
    "3Runner Three Male00:32:01\n"
)
SETTINGS = dict(
    race_format="battersea_pdf", course_id="battersea-park-10k",
    distance_m=10_000, timezone_name="Europe/London", timing_basis=None,
)
LEGACY_NOTICE = (
    "“Congratulations on completing the race.\n"
    "A notice about handicap scores.\n"
    "http://www.runbritainrankings.com/user/claimhandicap.aspx“\n"
)


def _fake_reader(monkeypatch, text=ROWS, *, date="2022-05-21"):
    data = b"%PDF-frozen-test"
    monkeypatch.setattr(battersea_pdf, "QUALIFIED_EDITIONS", {
        date: {"name": "May 10K", "result_sha256": sha256(data).hexdigest(),
               "result_count": 3, "pdf_pages": 1}
    })

    class Page:
        def extract_text(self):
            return text

    class Reader:
        def __init__(self, source):
            assert source.read().startswith(data)
            self.pages = [Page()]

    monkeypatch.setattr(battersea_pdf, "PdfReader", Reader)
    return data


def test_qualified_catalog_excludes_held_race():
    assert len(battersea_pdf.QUALIFIED_EDITIONS) == 18
    assert sum(e["result_count"] for e in battersea_pdf.QUALIFIED_EDITIONS.values()) == 2_725
    assert "2023-08-05" not in battersea_pdf.QUALIFIED_EDITIONS
    assert "2019-06-01" not in battersea_pdf.QUALIFIED_EDITIONS
    assert {date: e["result_count"] for date, e in battersea_pdf.QUALIFIED_EDITIONS.items()
            if date.startswith("2019")} == {
        "2019-03-16": 137, "2019-04-06": 126, "2019-08-03": 112,
        "2019-10-19": 171, "2019-11-30": 193,
    }


def test_parser_ignores_winners_and_preserves_rank_ties_and_london_start(monkeypatch):
    data = _fake_reader(monkeypatch)
    parsed = parse_saved_race_results(data, **SETTINGS)
    assert parsed.candidate_count == 3
    assert [r.duration_s for r in parsed.accepted] == [1860, 1860, 1921]
    assert [r.place for r in parsed.accepted] == [1, 2, 3]
    assert parsed.accepted_row_numbers == (1, 2, 3)
    assert parsed.event.started_at.isoformat() == "2022-05-21T08:30:00+01:00"
    assert parsed.event.source_event_id == "battersea-10k-2022-05-21"
    assert parsed.timing_basis is None


def test_2019_notice_before_results_and_winter_start(monkeypatch):
    text = ROWS.replace("21st May 2022", "30th November 2019").replace(
        "ALL RESULTS BELOW\n", "ALL RESULTS BELOW\n" + LEGACY_NOTICE
    )
    data = _fake_reader(monkeypatch, text, date="2019-11-30")
    parsed = parse_saved_race_results(data, **SETTINGS)
    assert [r.duration_s for r in parsed.accepted] == [1860, 1860, 1921]
    assert parsed.event.started_at.isoformat() == "2019-11-30T08:30:00+00:00"


@pytest.mark.parametrize("notice", [
    "Unrecognised results section\n",
    LEGACY_NOTICE.replace("A notice about handicap scores.", "1 Runner 00:30:00"),
    LEGACY_NOTICE + "RESULTS\nRANK NAME TIME\n",
])
def test_parser_does_not_skip_unknown_or_result_like_preamble(monkeypatch, notice):
    data = _fake_reader(monkeypatch, ROWS.replace(
        "ALL RESULTS BELOW\n", "ALL RESULTS BELOW\n" + notice
    ))
    with pytest.raises(ValueError, match="heading|preamble"):
        parse_saved_race_results(data, **SETTINGS)


@pytest.mark.parametrize("changed, error", [
    (ROWS.replace("2 Runner", "4 Runner"), "out-of-order"),
    (ROWS.replace("00:32:01", "00:30:01"), "unordered"),
    (ROWS.replace("3Runner Three Male00:32:01", "3Runner Three Male"), "ambiguous"),
    (ROWS.replace("3Runner Three Male00:32:01\n", ""), "expected 3"),
    (ROWS.replace("ALL RESULTS BELOW", "WINNERS AGAIN"), "full-results marker"),
    (ROWS.replace("00:32:01", "00;32:01"), "ambiguous"),
])
def test_parser_rejects_incomplete_or_ambiguous_full_results(monkeypatch, changed, error):
    data = _fake_reader(monkeypatch, changed)
    with pytest.raises(ValueError, match=error):
        parse_saved_race_results(data, **SETTINGS)


def test_parser_rejects_changed_bytes_and_unqualified_date(monkeypatch):
    data = _fake_reader(monkeypatch)
    with pytest.raises(ValueError, match="source hash scope"):
        parse_saved_race_results(data + b"changed", **SETTINGS)
    _fake_reader(monkeypatch, ROWS.replace("21st May 2022", "5th August 2023"))
    with pytest.raises(ValueError, match="header date"):
        parse_saved_race_results(data, **SETTINGS)


@pytest.mark.parametrize("change", [
    {"course_id": "some-other-course"}, {"distance_m": 5_000},
    {"timezone_name": "UTC"}, {"timing_basis": "chip"},
])
def test_parser_rejects_unsupported_settings(monkeypatch, change):
    data = _fake_reader(monkeypatch)
    with pytest.raises(ValueError, match="qualified course"):
        parse_saved_race_results(data, **(SETTINGS | change))


def test_shared_report_and_export_reconcile_on_pdf(monkeypatch, tmp_path):
    race = tmp_path / "race.pdf"
    weather = tmp_path / "weather.csv"
    race.write_bytes(_fake_reader(monkeypatch))
    weather.write_text(
        "observed_at,temp_c,wind_mps,precipitation_mm,humidity_pct\n"
        "2022-05-21T08:00:00+00:00,13.5,4.2,0,80\n"
    )
    report = build_offline_report(race, weather, weather_kind="historical_reanalysis", **SETTINGS)
    rows = build_result_rows(race, weather, race_kind="historical",
                             weather_kind="historical_reanalysis", **SETTINGS)
    assert report["result_quality"]["candidate_count"] == 3
    assert report["result_quality"]["accepted_count"] == 3
    assert report["weather_coverage"]["matched_count"] == 3
    assert [row["source_row_number"] for row in rows] == [1, 2, 3]
    assert {row["validation_status"] for row in rows} == {"accepted"}
    assert {row["weather_match_status"] for row in rows} == {"matched"}
    assert len({row["source_row_id"] for row in rows}) == 3
