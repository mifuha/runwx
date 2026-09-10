# runwx

runwx compares historical race pace and weather across editions of the same course.
Saved Eventrac results and hourly ERA5 reanalysis pass through Python validation,
BigQuery and dbt into a comparison view with explicit snapshot provenance.

I'm building it to practise data engineering using something I care about: running.

## Real historical comparison

The **Lydd Half Marathon 2022, 2023, 2024 and 2026** snapshots are verified in
BigQuery: **936 finishers**, all with a time-matched weather observation.
These are real historical results and reanalysis weather, captured as fixed inputs.

| Metric | 2022 | 2023 | 2024 | 2026 |
| --- | ---: | ---: | ---: | ---: |
| Finishers | 189 | 226 | 229 | 292 |
| Median pace | 5:29.6/km | 5:46.5/km | 5:36.8/km | 5:36.3/km |
| Mean pace | 5:30.8/km | 5:52.3/km | 5:45.4/km | 5:39.0/km |
| Fastest-20 median pace | 3:54.8/km | 4:09.6/km | 4:02.8/km | 3:54.5/km |
| Median pace change versus 2022 | 0% | +5.13% | +2.19% | +2.03% |
| Speed at median duration change | 0% | −4.88% | −2.14% | −1.99% |
| Matched temperature median | 5.8 °C | 11.0 °C | 8.8 °C | 7.4 °C |
| Matched wind median | 7.34 m/s | 7.47 m/s | 2.08 m/s | 3.05 m/s |
| Matched precipitation median | 0 mm | 0.1 mm | 0.5 mm | 0 mm |
| Matched humidity median | 61% | 81% | 90% | 74% |
| Weather coverage | 189/189 | 226/226 | 229/229 | 292/292 |

Positive pace change means slower. Speed at median duration is the reciprocal
measure, so its percentage change differs. Fastest-20 means the **median of the
fastest 20 finishers**. The view also exposes exact pace quartiles and unrounded
values; see [statistics, inputs and validation](docs/historical-comparison.md).

All editions use a common 21,097 m pace convention. Shared venue and certificate
evidence supports an **unchanged-course assumption**, not proof of identical routes.
Weather is hourly reanalysis at a venue proxy, matched to estimated run midpoints;
coverage does not establish whole-race conditions. Different runner populations
mean these results **do not isolate weather's causal effect**.

## Implemented flow

```mermaid
flowchart LR
    inputs["Saved race HTML + ERA5 weather"] --> python["Python validation,<br/>UTC alignment and row export"]
    python --> warehouse[("BigQuery snapshot tables")]
    warehouse --> staging["dbt staging"]
    staging --> fact["Accepted-results fact"]
    fact --> mart["Edition summary mart"]
    fact --> comparison["Historical comparison view"]
    mart --> comparison
```

This path has run using locally launched Python and containerized dbt against
BigQuery. Each edition has a dedicated source table and output dataset; the
comparison reads an explicit list of edition datasets and a named baseline.
Exact export reruns verify existing rows without another upload. A deliberately
corrected snapshot uses a separate destination and retains its own provenance.

The latest expansion passed **49 native dbt tests**: 21 for each new edition and
seven for the four-edition comparison. Its full result readbacks matched the saved
expectations. [Execution evidence](docs/evidence/historical-edition-expansion-validation.json)
distinguishes cached fixture tests from uncached real-data checks; the
[initial historical run](docs/evidence/historical-warehouse-validation.json)
records the earlier 2022/2024 validation. New raw captures and runner-level exports
are kept outside Git; these tables and aggregate evidence can be inspected without
a cloud account, but rerunning the historical warehouse needs the source snapshots
and configured BigQuery access.

A separate [deployed Cloud Run Job](docs/first-cloud-run.md) reads **fully synthetic
inputs** from private Cloud Storage and writes a JSON report back. Connecting real
snapshot export/loading and dbt execution to Cloud Run remains to be implemented.
There is no scheduled historical pipeline or hosted comparison UI yet. See the
[architecture](docs/architecture.md) for the implemented boundaries and remaining work.

<a id="quickstart"></a>
<a id="example-result"></a>
## Runnable offline demo — synthetic weather

The demo uses saved **Lydd 2022 race results with synthetic weather**, separate from
the real-weather comparison above. It runs without cloud credentials or network
access after installation, and is also available in a [local container](docs/container.md).

Start with Python 3.10 or newer and activate a virtual environment.

**WSL, Linux or macOS (bash/zsh):**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows Git Bash, using Windows Python:**

```bash
python -m venv .venv
source .venv/Scripts/activate
```

Then, in either activated environment:

```bash
python -m pip install -e .
python -m runwx report \
  --race-html data/raw/eventrac/lydd_half_2022.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id lydd-half-marathon --distance-m 21097 \
  --timezone Europe/London --weather-kind synthetic
```

Installation may need internet access. The command reads saved files and prints
JSON with **189 accepted results, 188 weather matches and one unmatched result**.
Median finish time is **6954 seconds**; fastest-20 median is **4953.5 seconds**.
Input hashes, settings, quality counts and limitations accompany the statistics.
The [report reference](docs/race-report.md) describes the schema. Report v1 labels
weather as synthetic or unknown; the historical warehouse uses the separate
[`export-results` command](docs/result-export.md) and its provenance records.

The command was checked in WSL/Ubuntu with Python 3.12.3 using an existing virtual
environment. Fresh installation and macOS/Windows execution were not checked in
this documentation update. The secondary
[CSV/SQLite activity workflow](docs/development.md#csv-and-sqlite-workflow) remains available.

## Validation and scope

- Every candidate result row is accepted, skipped or invalid, with counts and
  rejection reasons. Invalid page structure or unusable weather fails the output.
- Missing weather stays visible. All accepted finishers contribute to race
  statistics; weather coverage uses that same denominator.
- Exact source hashes and interpretation settings identify each input context.
  The loader supports one fixed export per table and duplicate-safe sequential
  reruns. A hash identifies contents, not their accuracy.
- Source qualification remains necessary: 2025 is held out because the organiser
  page repeats finishing positions. Three name discrepancies in 2023/2026 do not
  affect the reconciled durations; athlete matching and demographics are unqualified.
- Guarded selection, concurrent publication and elaborate receipt machinery are
  deferred. The current release uses explicitly chosen fixed historical snapshots.

## Tests

After activation, install pytest and the BigQuery extra, then run the suite.
Warehouse tests use a fake API; no cloud account is needed:

```bash
python -m pip install -e '.[bigquery]' pytest
python -m pytest -q
```

For the offline report checks alone:

```bash
python -m pytest -q tests/test_offline_report.py
```

CI runs Python tests, builds both containers, checks the report command, validates
both Terraform roots and parses default/comparison dbt configurations offline.
It does not deploy infrastructure or execute BigQuery SQL. Native warehouse
validation is recorded separately in the linked execution evidence.

## Development approach

I develop `runwx` with AI assistance alongside hands-on design, testing and review.
I remain responsible for the engineering decisions and for understanding the code.
Expected behaviour and trade-offs are made explicit before consequential changes,
and generated code is checked through focused tests, regression tests and diff review.
The project is also a learning exercise: unfamiliar concepts are worked through,
with small manual changes or tests to reinforce understanding.

## Developer documentation

- [Architecture and remaining Cloud Run integration](docs/architecture.md)
- [Historical source qualification and warehouse inputs](docs/historical-inputs.md)
- [Comparison statistics, explicit datasets and validation](docs/historical-comparison.md)
- [dbt staging, fact and mart models](docs/dbt-models.md)
- [Report fields, parser rules, course identity and time matching](docs/race-report.md)
- [Result-row export](docs/result-export.md) and [BigQuery loader](docs/bigquery-staging.md)
- [Cloud report contract, runtime permissions and verification](docs/first-cloud-run.md)
- [Code structure, API, contributing and CSV/SQLite usage](docs/development.md)
