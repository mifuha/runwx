# runwx

runwx is a Python project for looking at race results alongside weather data.
It checks the result rows, matches finishers to weather by time and produces a
small report.

I'm building it to practise data engineering using something I care about: running.

## What works today

- Read race results from saved Eventrac HTML.
- Count accepted, skipped and invalid rows, with reasons for rejected rows.
- Summarise finish times and show how many results have matching weather.
- Record the input file hashes and settings so the analysis can be repeated.
- Run the report from saved files without internet access.
- Load running activities from CSV and save their weather matches in SQLite.

The Lydd example has 189 accepted results and 188 weather matches. Its weather
values are made up for the demo, so the report does not describe the actual
conditions on race day. Everything runs locally for now; cloud deployment is planned.

---

## Core concepts

### Domain models (validated + immutable)

- `Run(started_at, duration_s, distance_m)`
- `WeatherObs(observed_at, temp_c, wind_mps, precipitation_mm, humidity_pct)`
- `RunWithWeather(run, weather)`

Validation rules:

- timestamps must be timezone-aware  
- `duration_s > 0`  
- `distance_m > 0`  
- `wind_mps >= 0`  
- `precipitation_mm >= 0`  

Dataclasses are `frozen=True` to keep core data immutable.

---

### Alignment (time-based)

For each run:

- compute the run anchor time as the **midpoint**  
- find the nearest weather observation in time  
- reject if the closest observation is farther than `max_gap` (default: 30 minutes)  

Open-Meteo requests cover UTC dates from the earliest run midpoint minus
`max_gap` to the latest midpoint plus `max_gap`. Adjacent dates are included
when this matching window crosses midnight. The same midpoint helper is used
for fetching and matching. A run with no observation within the permitted gap
is recorded as skipped with a reason. A negative `max_gap` raises `ValueError`
before any weather request.

---

### Pipeline orchestration

The pipeline:

- loops through runs  
- aligns weather  
- enriches valid matches  
- records skipped runs (with a reason)  

---

### CSV ingestion

The project can load:

- runs from `runs.csv`  
- weather observations from `weather.csv`  

CSV rows are parsed and converted into typed domain objects before entering the pipeline.

---

## Package structure

Canonical architecture is layered, and these modules are the source of truth:

- `runwx.domain`  
  Core domain types and pure logic.
- `runwx.services`  
  Orchestration/use-case flows built on domain logic.
- `runwx.adapters`  
  External I/O boundaries (CSV, SQLite, APIs, format translation).
- `runwx.main` / `runwx.__main__`  
  CLI entrypoints (`python -m runwx`).

---

## API stability

- Stable entrypoint
  - `python -m runwx`
- Canonical code API (for contributors/internal code)
  - Prefer imports from `runwx.domain.*`, `runwx.services.*`, and `runwx.adapters.*`.
- Backward-compatibility aliases (top-level modules)
  - Top-level `runwx.*` alias modules are kept to avoid breaking older imports.
  - They are compatibility paths, not the primary architecture surface.

---

## Contributor guidance

When adding or changing code:

- add business rules/entities in `runwx.domain`
- add orchestration in `runwx.services`
- add persistence/integration code in `runwx.adapters`
- keep `runwx.main` focused on CLI wiring

Internal code should import canonical layered modules directly.  
Compatibility aliases remain for external users and older integrations.

---

## Requirements

- Python 3.10+ (tested locally on Python 3.13)  
- Git  

---

## Setup (Git Bash on Windows)

From the project root:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -U pip
pip install -e .
pip install pytest
```

## Usage

```bash
python -m runwx run
python -m runwx run --csv
python -m runwx run --csv --db runwx.db
python -m runwx query --db runwx.db --limit 10
```

### Offline race report

Run this from the repository root:

```bash
.venv/bin/python -m runwx report \
  --race-html data/raw/eventrac/lydd_half_2022.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id lydd-half-marathon --distance-m 21097 \
  --timezone Europe/London --weather-kind synthetic
```

The command prints a JSON report using only the saved files. The weather is
**synthetic demo data**, not historical Lydd observations. If you omit
`--weather-kind`, the report labels its origin as unknown.

The report shows:

- Race details and finish-time statistics in seconds, using all accepted results.
- Accepted, skipped and invalid row counts, with reasons and row numbers.
- Weather matches and missing matches, with accepted results as the denominator.
- Weather medians across matched runners; one observation can match several runners.
- Full SHA-256 input hashes and the analysis settings, including timezone,
  `--top-n` (default 20) and `--max-gap-min` (default 30).

For Lydd, the defaults give 189 accepted results, 0 skipped and 0 invalid.
Weather matches 188 results and misses 1. The best finish is 4267 seconds,
the median is 6954, and the top-20 median is 4953.5.

The report reuses the existing parsers, summaries and weather matching code.
Each file is read once; those same bytes are parsed and hashed. Missing weather
leaves the race statistics intact and gives a `null` weather summary. With no
accepted results, both summaries and the coverage fraction are `null`.
Invalid pages, malformed weather or invalid settings fail before a report is printed.

The same files, paths, settings, code and dependencies produce identical JSON.
Moving a file changes its recorded path. Changing only line endings changes its
hash but can leave the statistics unchanged. Code and dependency versions are not
yet recorded, so use the same checkout and environment when repeating a run.

The report flags what we don't know: whether the saved results are complete,
individual start times, chip/gun timing, and the weather's location and source.
A time match alone doesn't establish whether the weather represents race conditions.

Tests block network access and check repeated output:

```bash
.venv/bin/python -m pytest -q tests/test_offline_report.py
```

### Race ingestion demo

Parse the saved Eventrac fixture deterministically, without requesting the live race page:
```bash
python scripts/demo_eventrac_parse.py
```

The demo reads `data/raw/eventrac/lydd_half_2022.html`, converts its
Europe/London start time to UTC, and prints the normalized event plus the
candidate, accepted, skipped, and invalid row counts.

Both Eventrac parsing entrypoints return an `EventracParseResult` with
`event`, `accepted`, `skipped`, and `errors` fields. `candidate_count` is checked
against the source row count before returning. Each candidate is a row with
direct data cells belonging to the results table, excluding header/footer and
nested-table rows. Row numbers start at 1 in candidate source order, independently
of finishing places. Equal times or places do not cause deduplication.

Each candidate gets one outcome, in this order:

- Misaligned cell counts or spanning cells: invalid, with row number, reason,
  and stripped cell values. Rows must match the full header width so positional
  values cannot silently shift; reordered columns are supported.
- Blank `Time` cell: skipped with the reason `missing finish time`.
- Missing, non-integer, or non-positive finishing place: invalid.
- Malformed or non-positive finish time: invalid. Times use `hours:minutes:seconds`
  with an optional numeric fraction; minutes and seconds must be 0–59. Valid
  fractional seconds are truncated to the existing whole-second domain unit.
- Otherwise: accepted as a validated `RaceResultIn`.

The parser returns a quality report even when every candidate is rejected;
analysis still requires accepted results. A missing results table, missing or
ambiguous required headers, spanning headers, or no candidate rows fails the page
with `ValueError`. Unexpected programming exceptions propagate. Provider status
codes such as DNF/DNS have no special interpretation yet: a blank time is skipped,
and other unparseable values are invalid.

### Course identity

Explicit course IDs take precedence and are normalized to ASCII slugs. A nonblank
ID that normalizes to an empty string, such as `---`, raises `ValueError` during
normalization or input-to-domain conversion. It does not fall back to an inferred
course. Missing or whitespace-only IDs still use curated event-name aliases plus
distance; an unknown combination returns `None`. Valid explicit route overrides
remain supported.

### Active delivery plan

See [RUNWX_PLAN_AND_CODEX_GUIDELINES.md](RUNWX_PLAN_AND_CODEX_GUIDELINES.md) for
the current implementation and learning agreement, and
[RUNWX_PROGRESS.md](RUNWX_PROGRESS.md) for the latest verified progress. The plan
supersedes conflicting strategy in older planning notes.
