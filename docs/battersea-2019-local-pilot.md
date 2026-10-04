# Battersea 2019 local pilot

Five more Sri Chinmoy Battersea Park 10Ks pass the local parser and weather
export checks. These are prepared locally; they have not been loaded into
BigQuery or added to the public comparison.

| Date | Accepted results | Weather matches |
| --- | ---: | ---: |
| 16 March 2019 | 137 | 137 |
| 6 April 2019 | 126 | 126 |
| 3 August 2019 | 112 | 112 |
| 19 October 2019 | 171 | 171 |
| 30 November 2019 | 193 | 193 |
| Total | 739 | 739 |

The [organiser's archive](https://uk.srichinmoyraces.org/races/london/previous-results/2019)
links the full result PDFs. Their exact hashes, counts and dates are pinned in
the [source catalog](../src/runwx/adapters/races/battersea_editions.json).
The parser excludes the winners summaries and requires continuous ranks and
positive, ordered finish times. The older PDFs include a standard notice before
the results heading; the parser now accepts that layout without skipping unknown
text or result-like rows.

## Course and start evidence

A [participant's dated report](https://www.shaefshifters.co.uk/p/royal-parks-half-battersea-10k-and)
describes the 30 November race as four laps, starting just after 08:30. The
organiser's PDF lists the author and club, with a time one second slower than
his reported watch time. This corroborates the November race and start convention.

The other four dates use the same 08:30 `Europe/London` series convention,
supported by the [2018 organiser archive](https://uk.srichinmoyraces.org/races/london/previous-results/2018)
and the November report. They do not have separate confirmed start times.
March and November convert to 08:30 UTC; April, August and October to 07:30 UTC.
The organiser's course map and 2019 Bandstand start description support the
same advertised course family, not proof of identical geometry on every date.
The published times do not specify chip or gun timing, so that field stays unknown.

## Checks and limits

All 739 exported ranks and times match the separate source audit. Each row's
weather match was checked against the saved hourly ERA5 response using the run
midpoint. The venue point is 51.4791075, -0.1564981; ERA5 returns the grid point
51.5, -0.25. This is reanalysis, not an on-course measurement.
At 09:00 local, the five dates span 2.1–18.3°C and wind speeds of 1.84–9.12 m/s.

Repeated exports are byte-identical. Reports are also byte-identical when using
the same input paths; moving the weather file changes its recorded path only.
The existing 13 Battersea exports remain byte-identical across all 1,986 rows.
The application test suite passed 485 tests, including rejection of unknown
preambles, duplicate headings and malformed times.

1 June 2019 remains held: rank 107 has `00;54:52`, leaving 142 usable times
among 143 listed ranks. We have not repaired that value or silently dropped it.
No warehouse, API, infrastructure or public chart changed in this pilot.
