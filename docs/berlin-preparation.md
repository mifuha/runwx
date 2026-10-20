# Prepare Berlin research results offline

`prepare-berlin` prepares saved results from the
[version 2 Kaggle research dataset](https://www.kaggle.com/datasets/aiaiaidavid/berlin-marathons-data/versions/2)
and saved ERA5 responses. It supports **16 editions, 2003–2018**, containing
541,730 usable reported times in the reviewed capture. It does not download data,
load BigQuery, run dbt or add Berlin to the live page.

These are available anonymised research results, **not verified complete official
fields**. The publisher declares CC0. The
[catalog](../src/runwx/adapters/races/berlin_editions.json) records the pinned CSV
hash, dates, captured counts, primary evidence and published-count differences.
The organiser describes major course changes and a course era beginning in 2003;
identical street-by-street routes and smaller changes have not been verified.

2019 is excluded because that capture has only men. Earlier course eras are out
of scope. Missing country or age-category values do not invalidate a duration.
AGE is retained as a raw category string; it is never converted into exact age.
No official place, athlete identity or individual start is invented. Identical
anonymous rows remain separate captures.

## Run it

Copy [the example configuration](../batches/berlin.example.json), then supply the
reviewed saved CSV and one saved weather response/request/hash per selected year:

```bash
python -m runwx prepare-berlin batches/berlin.example.json \
  --output data/local/prepared/berlin-01
```

Paths are relative to the configuration file. Choose any reviewed years, up to
all 16, by listing their weather inputs. The example has two entries to keep it
short; its paths and all-zero weather hashes are placeholders. Keep actual inputs,
configs and runner-level exports in ignored local storage.

The command checks the source against the pinned dataset hash. Duplicate or
unreviewed years, changed bytes, malformed CSV structure and unexpected captured
counts fail the batch. Each selected row is accepted or held with a reason;
unselected records are counted separately. Blank or unusable reported times are
held, not silently dropped or repaired. A dataset update needs a reviewed catalog
change; changing the config cannot approve a new source hash.

## Weather means edition context

The saved request must specify ERA5, that race date, the Berlin finish-area proxy
at **52.5163, 13.3777**, Europe/Berlin and wind in m/s. Celsius and mm may be stated
explicitly or use provider defaults; response units are checked either way.
Temperature, wind, precipitation and humidity must cover all 24 local hours.
The response offset must agree with Europe/Berlin on that date; returned grid
coordinates must be near the requested point. A URL/hash check records the
reviewed request; it does not independently authenticate the provider response.

The fixed **09:00–15:00 Europe/Berlin** window was chosen before inspecting any
pace–weather association. It is descriptive context, independent of finishing
durations. Seven observations supply median temperature, wind and humidity.
Rainfall sums the six preceding-hour amounts ending at 10:00 through 15:00, as
defined by the [provider](https://open-meteo.com/en/docs/historical-weather-api#hourly-parameter-definition).
It is not individual exposure or whole-course weather. Timing basis stays unknown.
The supplied daily research-weather CSV is separate evidence and is not an input.

## Outputs and guarantees

Each edition produces `DATE.ndjson`, `DATE.weather.csv` and `DATE.report.json`.
`preparation.json` records the source/catalog hashes, captured/accepted/held counts,
unselected count, weather settings/provenance and export hashes/sizes. Reports are
also embedded in that summary. Paths and execution timestamps are excluded from
artifacts, so the same inputs produce identical output bytes in a new directory.

Rows retain original CSV data-record numbers and source-hash-based IDs. Those
numbers identify captures, not race places. The export has no inferred start or
runner weather match. Its preparation contract is separate from both the current
full-field warehouse export and GNR's Top 1,000 sample. It is not a load plan.

The full source is hashed into a temporary copy, then parsed once. Selected rows
stream to files rather than accumulating the full field in memory. All editions
must validate before final output is written. Existing output directories and
symlinks are rejected. The summary is written last: an interrupted final file copy
may leave an incomplete directory without it. Investigate and use a new directory.
This is a local sequential command, not a concurrent artifact publisher.

Count differences remain explicit. The 2008 capture has 79 more rows than the
published table; its cause is unresolved. The table's 2013 total is malformed, so
`published_count` remains null rather than being guessed. Neither matching nor
near-matching totals proves that the population is complete or unbiased.

The next integration must retain these population/weather labels, measure the
appropriate load bound, and preserve typed-row verification and duplicate/conflict
protection. No loader, warehouse schema, API or cloud change is part of this work.
