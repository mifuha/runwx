# Race report reference

See the [README quickstart](../README.md#quickstart) for setup and the report command.
Run commands from the repository root with the virtual environment activated.

## Report contents

`python -m runwx report` reads saved Eventrac HTML and weather CSV, then prints JSON.
It uses the existing parsers, race summaries, result-to-run conversion, weather
matching and weather summaries. It does not request live data or write a database.

- `race`: event and course identity, supplied distance, location, interpreted
  local start and UTC start.
- `race_summary`: finisher count and best, mean, median and top-N median finish
  times in seconds. These use all accepted results.
- `result_quality`: candidate, accepted, skipped and invalid counts, plus reasons
  and candidate row numbers for rejected rows.
- `weather_coverage`: matched and unmatched counts, unmatched reasons and the
  matched fraction. The denominator is accepted results, not all source rows.
- `weather_summary`: medians across matched runners. One observation can match
  several runners, so these are not medians across unique weather timestamps.
- `sources`: filenames and full SHA-256 hashes, the race provider/event ID, and
  the declared weather kind and observation count.
- `settings`: course ID input, distance, timezone, top-N requested/effective count,
  matching gap, midpoint/tie rules and whole-second duration precision. The
  unknown chip/gun timing basis is `null`.
- `limitations`: the source and interpretation limits described below.

`--top-n` defaults to 20; when fewer finishers are accepted, it uses all of them.
`--max-gap-min` defaults to 30. `--weather-kind` accepts `synthetic` or `unknown`
and defaults to `unknown`. This label is a declaration, not verified provenance.

With no eligible weather, race statistics remain available, weather statistics
are `null` and coverage is zero. With no accepted results, both summaries and
the coverage fraction are `null`, with coverage status `not_applicable`.
Invalid pages, malformed weather and invalid settings fail before a report is printed.

Each file is read once; the same bytes are parsed and hashed. Repeating a command
with the same files, paths, settings, code and dependencies produces identical JSON.
There are no execution timestamps or random IDs. Moving an input changes its
recorded path. Changing only line endings changes its hash but can leave the
statistics unchanged. Hashes identify content, not authenticity or completeness.
Code/dependency versions are not captured yet; replay assumes the same environment.

The included weather is synthetic, not historical Lydd data. Weather location,
provider and capture metadata are unverified. Individual runner starts, chip/gun
timing and full-event completeness are unknown. Every runner uses the event start.
Time matching does not establish spatial suitability or conditions over the whole race.

## Parser rules

For a parser-only demonstration, using the same saved Lydd HTML:

```bash
python -m scripts.demo_eventrac_parse
```

The demo converts the Europe/London start to UTC and prints the normalized event,
some accepted results, and candidate/accepted/skipped/invalid counts and reasons.

Both `load_eventrac_results_html` and `parse_eventrac_results_html` return an
`EventracParseResult` with `event`, `accepted`, `skipped` and `errors` fields.
`candidate_count` is checked against the source row count before returning.

Location extraction accepts JSON-LD objects containing a `location.geo` object.
Unsupported shapes, such as lists or nulls, are skipped so a later valid script
can supply coordinates. If none supplies coordinates, parsing raises a page-level
`ValueError`.

A candidate is a row with direct data cells belonging to the results table,
excluding header/footer and nested-table rows. Candidate row numbers start at 1
in source order, independently of finishing place. Equal times or places do not
cause deduplication.

Each candidate gets one outcome, in this order:

1. Misaligned cell counts or spanning cells: invalid, with row number, reason and
   stripped cell values. Rows must match the full header width so values cannot
   silently shift. Reordered columns are supported.
2. Blank `Time`: skipped with the reason `missing finish time`.
3. Missing, non-integer or non-positive finishing place: invalid.
4. Malformed or non-positive finish time: invalid. Times use `hours:minutes:seconds`
   with an optional numeric fraction; minutes and seconds must be 0–59. Valid
   fractional seconds are truncated to the existing whole-second domain unit.
5. Otherwise: accepted as a validated `RaceResultIn`.

The parser returns row outcomes even when every candidate is rejected. The
summary functions require non-empty inputs; the report handles this with `null`
summaries. A missing results table, missing or ambiguous required headers, spanning
headers, or no candidate rows fails the page with `ValueError`. Unexpected parser
programming exceptions propagate.

DNF/DNS codes have no special interpretation yet: a blank time is skipped and
other unparseable values are invalid. The parser retains raw cells for invalid
rows; the JSON report includes their reasons and row numbers without copying the cells.

## Course identity

Explicit course IDs take precedence and are normalized to ASCII slugs. A nonblank
ID that normalizes to an empty string, such as `---`, raises `ValueError` during
normalization or input-to-domain conversion. It does not fall back to an inferred
course. Missing or whitespace-only IDs use curated event-name aliases plus distance;
an unknown combination returns `None`. Valid explicit route overrides remain supported.

## Time matching

For each run, the pipeline computes its midpoint, selects the nearest observation
and attaches it if the gap is within `max_gap` (default: 30 minutes). Equal-distance
ties go to the earlier observation. A missing or too-distant observation produces
a skipped run with a reason.

The optional live Open-Meteo path requests UTC dates from the earliest midpoint
minus `max_gap` to the latest midpoint plus `max_gap`. It includes adjacent dates
when that window crosses midnight, using the same midpoint helper as matching.
A negative gap raises `ValueError` before any weather request. The offline report
also rejects a negative gap and reads only its saved weather CSV.

Implementation: [Eventrac parser](../src/runwx/adapters/races/eventrac_html.py),
[offline report](../src/runwx/services/offline_report.py),
[weather matching](../src/runwx/domain/align.py).
