from runwx.adapters.races.eventrac_html import load_eventrac_results_html


def main() -> None:
    event_in, results_in = load_eventrac_results_html(
        "data/raw/eventrac/lydd_half_2022.html",
        course_id="lydd-half-marathon",
        distance_m=21097,
    )

    print(event_in)
    print(f"parsed results: {len(results_in)}")
    print(results_in[:3])


if __name__ == "__main__":
    main()