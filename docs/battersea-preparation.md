# Prepare a Battersea batch offline

`prepare-battersea` turns qualified saved PDFs and ERA5 responses into the same
reports and result exports used by the existing pipeline. It uses the shared
parser, validation, weather matching and artifact coordinator. It does not fetch
sources, load BigQuery, run dbt or change the live page.

Start with [the example configuration](../batches/battersea.example.json). Its
paths are placeholders; the weather hash and request describe the retained
16 March 2019 response. Raw inputs are private and are not included in the repo.
Use your reviewed saved files and their retained request/hash evidence; do not
replace a hash just to make an unexplained changed input pass.

```bash
python -m runwx prepare-battersea batches/battersea.example.json \
  --output data/local/prepared/battersea-01
```

Each entry has a date, PDF path, weather JSON path, expected weather SHA-256 and
saved weather request URL. Paths are relative to the configuration file. Entries
are processed in date order. PDF identity and expected result counts come from the
[qualified catalog](../src/runwx/adapters/races/battersea_editions.json).
New dates still need source qualification and a reviewed catalog change.

The command rejects duplicate or unqualified dates, changed hashes, wrong request
settings and malformed weather. The saved request must name the Battersea venue,
that race date, ERA5, UTC, wind in m/s and the four established hourly variables.
The response must contain that day's 24 hours with the expected units and valid
numbers. Its returned grid coordinates must be finite, within geographic bounds
and within 0.5 degrees of the venue on each axis. ERA5 returns a grid cell rather
than the exact requested point; this coarse check rejects unrelated locations
without claiming precise venue exposure. Checking a saved URL and hash preserves
the reviewed input contract; it does not independently authenticate the provider response.

Settings stay fixed: 10 km, 08:30 Europe/London using the evidenced series
convention, top-20, a 30-minute weather gap and unknown chip/gun timing basis.
The parser handles winter/summer UTC conversion. The start-time convention and
course evidence have the same limitations as the [existing qualification](battersea-2019-local-pilot.md).

## Outputs and failures

Each date produces `DATE.weather.csv`, `DATE.report.json` and `DATE.ndjson`.
`preparation.json` records source and artifact hashes, settings, counts and saved
weather requests. It is preparation evidence, not an executable warehouse plan.
Unmatched weather remains visible in the counts; it is not silently discarded.

All editions are validated in temporary storage before final files are written.
A validation failure returns a nonzero exit status with the edition and reason,
and creates no final batch. Existing output directories are never reused.
The summary is written last: an interrupted or failed final filesystem write may
leave an incomplete directory without it. Use a new output directory after
investigating; this is a sequential local command, not a concurrent publisher.

NDJSON and weather CSV are deterministic for the same inputs. Reports retain
source paths, so their bytes can differ between output directories; compare their
analytical content separately. Keep generated inputs/exports and summaries private.

## A short hands-on demonstration

Copy the example into an ignored local directory and set the paths to your
reviewed files. Run it, then add one more already-qualified date with its retained
weather hash/request and prepare into a new directory. Inspect the edition count,
accepted results and weather matches in `preparation.json`.

In another copy of the config, change one character of a weather hash and run
against a third new directory. Explain why the command stops and why no completed
batch appears. This demonstrates an input mismatch, not a cloud outage or a safe
warehouse rerun. The [failure guide](failure-and-recovery.md) covers those separate
boundaries.

## Local verification

The command was replayed against all 18 retained editions: 2,725 accepted results
and 2,725 weather matches. Every NDJSON and weather CSV matched its frozen file
byte for byte. Reports matched after excluding only the two source-file paths;
winter/summer UTC starts also matched. This was a local replay, not a new
BigQuery load, Cloud Run execution or demonstration of independent practice.
Offline tests use synthetic PDFs through the existing parser test seams and
block network connections and credential discovery.
