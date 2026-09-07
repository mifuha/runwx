from runwx.adapters.races.eventrac_html import load_eventrac_results_html


def main() -> None:
    outcome = load_eventrac_results_html(
        "data/raw/eventrac/lydd_half_2022.html",
        course_id="lydd-half-marathon",
        distance_m=21097,
        timezone_name="Europe/London",
    )

    print(outcome.event)
    print(f"candidate rows: {outcome.candidate_count}")
    print(f"parsed results: {len(outcome.accepted)}")
    print(outcome.accepted[:3])
    print(f"skipped rows: {len(outcome.skipped)}")
    for row in outcome.skipped:
        print(f"row {row.row_number}: {row.reason}")
    print(f"invalid rows: {len(outcome.errors)}")
    for row in outcome.errors:
        print(f"row {row.row_number}: {row.reason}")


if __name__ == "__main__":
    main()
