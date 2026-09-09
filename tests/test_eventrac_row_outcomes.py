from html import escape

import pytest

from runwx.adapters.races import eventrac_html


def make_html(rows, headers=("Position", "Gender", "Time"), *, jsonld=None):
    if jsonld is None:
        jsonld = '{"location": {"geo": {"latitude": 50.954438, "longitude": 0.902385}}}'
    header_cells = "".join(f"<th>{escape(value)}</th>" for value in headers)
    data_rows = "".join(
        "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"""
    <link rel="canonical" href="https://www.eventrac.co.uk/results/21723">
    <script type="application/ld+json">
        {jsonld}
    </script>
    <div class="box-header">
        <h3 class="box-title">Synthetic Half Marathon Results</h3>
        <small>06/03/2022, 10:00</small>
    </div>
    <table id="results">
        <thead><tr>{header_cells}</tr></thead>
        <tbody>{data_rows}</tbody>
    </table>
    """


def parse(html):
    return eventrac_html.parse_eventrac_results_html(
        html,
        course_id="synthetic-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )


@pytest.mark.parametrize(
    "jsonld",
    [
        "null",
        "[]",
        '{"location": null}',
        '{"location": []}',
        '{"location": {"geo": null}}',
        '{"location": {"geo": []}}',
    ],
)
def test_unsupported_jsonld_shape_does_not_hide_later_valid_location(jsonld):
    unrelated_script = f'<script type="application/ld+json">{jsonld}</script>'
    outcome = parse(unrelated_script + make_html([("1", "Male", "01:00:00")]))

    assert outcome.event.latitude == 50.954438
    assert outcome.event.longitude == 0.902385
    assert len(outcome.accepted) == 1


@pytest.mark.parametrize(
    "jsonld",
    [
        "null",
        "[]",
        '{"location": null}',
        '{"location": []}',
        '{"location": {"geo": null}}',
        '{"location": {"geo": []}}',
    ],
)
def test_unsupported_jsonld_without_valid_location_is_a_clear_page_failure(jsonld):
    with pytest.raises(ValueError, match="could not extract latitude/longitude from JSON-LD"):
        parse(make_html([("1", "Male", "01:00:00")], jsonld=jsonld))


@pytest.mark.parametrize(
    ("headers", "rows"),
    [
        (
            ("Position", "Gender", "Time"),
            [("1", "Male", "01:11:07.00"), ("2",), ("3", "Female", "01:14:48")],
        ),
        (
            ("Time", "Place", "Gender"),
            [("01:11:07.00", "1", "Male"), ("01:12:00",), ("01:14:48", "3", "Female")],
        ),
    ],
)
def test_short_row_is_invalid_and_valid_neighbours_survive(headers, rows):
    outcome = parse(make_html(rows, headers))

    assert [row.duration_s for row in outcome.accepted] == [4267, 4488]
    assert [row.place for row in outcome.accepted] == [1, 3]
    assert outcome.skipped == ()
    assert len(outcome.errors) == 1
    assert outcome.errors[0].row_number == 2
    assert outcome.errors[0].values == rows[1]
    assert outcome.errors[0].reason == "expected 3 cells, found 1"
    assert outcome.candidate_count == 3


def test_every_candidate_has_one_outcome_without_deduplicating_finishers():
    outcome = parse(make_html([
        ("1", "Male", "01:00:00"),
        ("2", "Female", " "),
        ("", "Male", "01:03:00"),
        ("oops", "Female", "01:04:00"),
        ("0", "Male", "01:05:00"),
        ("3", "Male", "bad-time"),
        ("4", "Male", "00:00:00"),
        ("1", "Female", "01:00:00"),
    ]))

    assert outcome.candidate_count == 8
    assert len(outcome.accepted) == 2
    assert [row.duration_s for row in outcome.accepted] == [3600, 3600]
    assert [row.gender for row in outcome.accepted] == ["Male", "Female"]
    assert len(outcome.skipped) == 1
    assert outcome.skipped[0].row_number == 2
    assert outcome.skipped[0].reason == "missing finish time"
    assert [row.row_number for row in outcome.errors] == [3, 4, 5, 6, 7]
    assert outcome.errors[0].reason == "missing finishing place"
    assert "oops" in outcome.errors[1].reason
    assert "positive" in outcome.errors[2].reason
    assert "bad-time" in outcome.errors[3].reason
    assert "duration_s" in outcome.errors[4].reason
    assert outcome.candidate_count == (
        len(outcome.accepted) + len(outcome.skipped) + len(outcome.errors)
    )


def test_page_with_only_rejected_rows_still_returns_its_quality_report():
    outcome = parse(make_html([("1", "Male", ""), ("2", "Female", "bad-time")]))

    assert outcome.accepted == ()
    assert outcome.candidate_count == 2
    assert [row.row_number for row in outcome.skipped] == [1]
    assert [row.row_number for row in outcome.errors] == [2]


@pytest.mark.parametrize(
    "bad_time",
    ["00:61:00", "00:00:60", "01:-01:00", "01:00:00.junk"],
)
def test_malformed_time_is_reported_before_normalization_hides_the_error(bad_time):
    outcome = parse(make_html([("1", "Male", bad_time)]))

    assert outcome.accepted == ()
    assert outcome.skipped == ()
    assert outcome.candidate_count == 1
    assert len(outcome.errors) == 1
    assert outcome.errors[0].row_number == 1
    assert outcome.errors[0].values[-1] == bad_time
    assert "invalid finish time" in outcome.errors[0].reason


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        (("Position", "Gender", "Gun Time"), "missing required columns"),
        (("Position", "Place", "Gender", "Time"), "ambiguous required column"),
        (("Position", "Gender", "Time", "Time"), "ambiguous required column"),
    ],
)
def test_missing_or_ambiguous_required_header_fails_the_page(headers, message):
    with pytest.raises(ValueError, match=message):
        parse(make_html([], headers))


def test_empty_result_table_is_a_page_failure():
    with pytest.raises(ValueError, match="no Eventrac candidate result rows"):
        parse(make_html([]))


def test_header_footer_and_empty_rows_do_not_count_as_candidates():
    html = make_html([(), ("1", "Male", "01:00:00")])
    html = html.replace("</thead>", "<tr><td colspan='3'>Heading</td></tr></thead>")
    html = html.replace("</tbody>", "</tbody><tfoot><tr><td>Total: 1</td></tr></tfoot>")

    outcome = parse(html)

    assert outcome.candidate_count == 1
    assert len(outcome.accepted) == 1
    assert outcome.skipped == ()
    assert outcome.errors == ()


def test_spanning_data_cells_are_invalid_instead_of_shifting_values():
    html = make_html([("1", "Male", "01:00:00")])
    html = html.replace("<td>Male</td>", "<td colspan='2'>Male</td>")

    outcome = parse(html)

    assert outcome.accepted == ()
    assert outcome.candidate_count == 1
    assert outcome.errors[0].reason == "spanning data cells are not supported"


def test_spanning_header_is_a_page_failure():
    html = make_html([("1", "Male", "01:00:00")])
    html = html.replace("<th>Time</th>", "<th colspan='2'>Time</th>")

    with pytest.raises(ValueError, match="spanning Eventrac header cells"):
        parse(html)


def test_nested_table_rows_are_not_additional_candidates():
    html = make_html(
        [("1", "Male", "01:00:00", "DETAILS")],
        headers=("Position", "Gender", "Time", "Details"),
    )
    html = html.replace("DETAILS", "<table><tr><td>Award details</td></tr></table>")

    outcome = parse(html)

    assert outcome.candidate_count == 1
    assert len(outcome.accepted) == 1
    assert outcome.skipped == ()
    assert outcome.errors == ()


def test_programming_error_propagates_instead_of_becoming_a_row_rejection(monkeypatch):
    def broken_parser(value):
        raise RuntimeError("unexpected parser bug")

    monkeypatch.setattr(eventrac_html, "_parse_duration_to_seconds", broken_parser)

    with pytest.raises(RuntimeError, match="unexpected parser bug"):
        parse(make_html([("1", "Male", "01:00:00")]))
