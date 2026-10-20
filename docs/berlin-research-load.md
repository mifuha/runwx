# Preview a Berlin research snapshot load

Berlin uses its own [typed row schema](../src/runwx/adapters/bigquery/berlin_research_rows.schema.json).
The capture has no official places or individual starts, and its weather describes
a fixed edition window. It must not be loaded as the existing full-field or GNR
Top 1,000 format.

Start with the files produced by [offline preparation](berlin-preparation.md).
Preview one edition without credentials or network access:

```bash
python -m runwx.bigquery_load \
  --input-format berlin-research \
  --input saved/2018-09-16.ndjson \
  --preparation-report saved/2018-09-16.report.json \
  --expected-sha256 CAPTURE_SHA256 \
  --expected-report-sha256 REPORT_SHA256 \
  --table PROJECT.runwx_staging.berlin_2018_research_SNAPSHOT
```

Replace the paths, destination and hashes with the exact reviewed values. The
capture hash comes from preparation evidence; separately hash the saved report
and review its settings. Supplying a newly calculated hash is not approval for
an unexplained changed input.

## What the preview checks

Both files must match their expected hashes. The report must match the pinned
Kaggle version, reviewed edition/date/counts and declared population. Every capture
row is checked for its typed fields, original source-record identity and order,
raw time conversion and accepted/held outcome. Identical anonymous rows remain
distinct. Official place, exact age and timing basis must stay null.

The report's saved request and weather contract must describe ERA5, the Berlin
proxy, correct units and the fixed 09:00–15:00 Europe/Berlin window. Values must be
finite and physically valid. The preparation report's approved hash binds the
weather values and source hashes. This preflight does not fetch the provider or
independently recalculate the report from the original weather response; the
preparation and retained reconciliation evidence establish that separate check.

One warehouse row contains one capture, with explicit research-population and
course-era labels, source/report/weather hashes and shared typed weather context.
The context is also present on held rows: it belongs to the edition, not an
individual runner match. Future pace models must exclude held durations.
Published-count differences remain visible; the ambiguous 2013 total stays null.

The warehouse payload differs from the original capture. Preview prints both
hashes, its schema hash, candidate counts, size and deterministic load job ID.
Keeping context in the same table lets one load and full row comparison verify
the snapshot together. There is no second metadata publication step.

The current bounds are 16 MiB for the original capture, 64 KiB for its report and
64 MiB for the expanded warehouse payload. Offline preflight checked all 16
prepared editions and 541,730 rows. The largest capture was 14,776,638 bytes;
its expanded warehouse payload was 65,984,298 bytes. Full-field and GNR limits
stay unchanged. The preflight and independent row-checking process peaked at
253,272 KiB; this does not measure a real BigQuery upload. Preflight materialises
the typed rows and expanded payload. Process one edition at a time.

## Explicit execution, after review

Only after its exact destination and settings are approved and the table has
been created with this schema, adding `--execute` calls the existing shared
BigQuery loader. It requires `europe-west1`, `CREATE_NEVER` and `WRITE_EMPTY`.
It reads back every typed row after loading. An identical rerun verifies existing
rows without another upload; conflicting, missing, extra or duplicated rows fail
without overwrite or deletion. Paths do not enter job identity. Changing the
report, payload, destination or schema changes the planned job identity.

Existing request/job timeouts, deterministic job recovery and the 100 MiB query
billing cap remain in the shared loader. These are serialized snapshot operations,
not a concurrent publication protocol or automatic edition selection.

Tests use the real SDK interfaces and a stateful fake with network and credentials
blocked. They verify load/rerun/conflict and failure behaviour, not native SQL or
cloud execution. This change creates no tables, changes no IAM and does not run
dbt or update the API. A real pilot load remains a separately reviewed step.
