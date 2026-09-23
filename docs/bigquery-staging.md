# First BigQuery staging load

For several qualified Great North Run editions, use the
[batch preparation/loading command](batch-ingestion.md). It reuses the same safe
snapshot loader and records one batch summary.

Status: **first cloud load passed on 8 September; exact Cloud Run artifact-to-table
verification passed on 14 September 2026**.
This step puts the [synthetic result export](result-export.md) into one table.
This load step does not add dbt models or change the existing Cloud Run report job;
the subsequent [dbt validation](dbt-models.md#verified-cloud-run) is recorded separately.

## Dataset, table and schema

A BigQuery dataset groups tables and sets their location and access. This first
dataset is `runwx_staging` in `europe-west1`. Its `synthetic_results` table holds
one complete synthetic export, including skipped and invalid candidates.

The [explicit schema](../src/runwx/adapters/bigquery/result_rows.schema.json) gives
each column a type: seconds and metres are integers, hashes and outcomes are
strings, and observation times are timestamps. `settings` and `weather` are nested
records. Rejected durations and absent weather remain null; schema inference is off.

The source-row grain and identity are unchanged. Each table accepts one export.
The loader also supports explicitly labelled historical results and reanalysis
weather; see [local historical preparation](historical-inputs.md). The verified
cloud run below remains evidence for the original synthetic inputs.

## Verified cloud run

Terraform created two resources in project `runwx-learning-mifuha`: the private
`runwx_staging` dataset and `synthetic_results` table, both in `europe-west1`.
It changed or deleted no existing resources. A post-deployment plan found no drift.

The first load returned `loaded_verified`. The repeat returned
`already_present_verified`, submitted no second upload and left the table's
modification timestamp unchanged. Both checked every field against the local export,
including source hashes, settings, nulls and weather observations. The BigQuery
timestamp spelling was normalised before comparison.

| Check | Actual result |
| --- | --- |
| Uploaded export | 5,521 bytes; five candidate rows |
| Accepted / skipped / invalid | 3 / 1 / 1 |
| Weather matched / accepted | 2 / 3 |
| Table after repeat | Five rows; 2,688 logical bytes |
| Verification queries | Three, each with a 100 MiB billed-byte limit |
| Total query bytes processed / billed | 5,376 / 20,971,520 |

The billed-byte statistic includes BigQuery's query minimum; it is not a confirmed
currency charge after free allowances or credits. No currency charge was measured.
The existing Cloud Run job, runtime permissions and billing configuration were unchanged.

Load job:

```text
runwx_load_304fe491e6b933fd3196f22810e67f5c58a5cee14cbca9c56a07163effb5c418
```

The [verification record](evidence/bigquery-first-load.json) contains all four job
IDs, timestamps, usage, hashes, settings and the loader commit/client version.
The rows read back from BigQuery also reproduced the existing Python summary:
best 3,600 s, median 7,200 s, mean 8,400 s and top-N median 7,200 s (N requested 20,
effective 3). Those load-verification calculations ran in Python; the later
[dbt validation](dbt-models.md#verified-cloud-run) reproduced them in BigQuery.
**These inputs are entirely synthetic, not historical race evidence.**

Inspect the [table in BigQuery](https://console.cloud.google.com/bigquery?project=runwx-learning-mifuha&p=runwx-learning-mifuha&d=runwx_staging&t=synthetic_results&page=table),
including its schema and preview. In the same console, use Job history to find the
recorded load and query IDs. [Billing reports](https://console.cloud.google.com/billing?project=runwx-learning-mifuha)
show monetary charges when available; job byte statistics are available sooner.

## Local preview

From the repository root with the virtual environment activated:

```bash
python -m pip install -e '.[bigquery]'
```

The optional extra supplies Google's BigQuery client. The report and SQLite commands
do not require this extra. CI installs it to include the loader tests.

Generate the same five synthetic rows in a fresh temporary directory, then preview
the load. Both commands below work without network access or cloud credentials:

```bash
runwx_demo_dir=$(mktemp -d)
python -m runwx export-results \
  --race-html data/sample_race_synthetic.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id runwx-synthetic-half --distance-m 21097 \
  --timezone Europe/London --max-gap-min 30 \
  --race-kind synthetic --weather-kind synthetic \
  > "$runwx_demo_dir/results.ndjson"
python -m runwx.bigquery_load \
  --input "$runwx_demo_dir/results.ndjson" \
  --table runwx-learning-mifuha.runwx_staging.synthetic_results \
  --expected-sha256 91fcecdb956ea324d27aa8247c05a7eea357151ffe431752624f2ca95bb7b570
```

Expected preview: `prepared_locally`, 5,521 bytes, five candidate rows, three
accepted, one skipped, one invalid and two weather matches. It also prints the
input hashes, schema hash and planned load-job ID. **Both inputs are synthetic;
these counts are pipeline evidence, not historical race findings.**

The expected hash binds execution to the file reviewed in the preview. Changed
bytes require inspecting a new preview and supplying its actual hash. The first
loader rejects exports over 1 MiB, unknown source labels, inconsistent snapshots,
duplicate row identities and fields that differ from the schema.

## Cloud execution

Provisioning is separate from loading. [warehouse.tf](../infra/gcp/warehouse.tf)
adds only the private dataset and an empty table when `enable_bigquery_staging`
is true; the default is false. BigQuery's API must already be enabled. Terraform
owns the table schema, and the loader requires an existing table in the expected
region with that exact schema. No resources are created by the Python command.

The first manual load uses the signed-in developer's Application Default
Credentials. Existing project owners have access; this configuration gives dataset
access to `projectOwners` and adds no public access or runtime service-account role.
Project-level inherited permissions still apply. A separate restricted loader would
need job creation on the project and table data read/write permissions. See Google's
[batch-load permissions](https://docs.cloud.google.com/bigquery/docs/batch-loading-data#required_permissions).
No service-account key is needed. If local ADC is missing, use
`gcloud auth application-default login` and complete authentication in the browser.

Adding `--execute` to the preview command uploads the local file directly to
BigQuery and runs verification queries. This first step does not stage another
Cloud Storage object. The existing saved-input Cloud Run path stays as described
in [first-cloud-run.md](first-cloud-run.md).

For a Cloud Run artifact pair, use the separate Storage adapter. It downloads the
exact report and result-export generations, checks that the version 2 report names
and hashes the export, and reconciles source identity, settings and counts before it
calls the same `prepare_load` function. This preview reads Cloud Storage but does
not create a BigQuery client or submit a job:

```bash
python -m runwx.gcs_bigquery_load \
  --report-uri gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-6ccdt/task-0-attempt-0.json \
  --report-generation 1789226380183224 \
  --result-export-uri gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-6ccdt/task-0-attempt-0.ndjson \
  --result-export-generation 1789226379967796 \
  --expected-sha256 f95b3ae312e3131279a8a5ebbe77f58d3967d70bc7007b6c268f0bd4492eef47 \
  --table runwx-learning-mifuha.runwx_staging.folkestone_2019_f95b3ae312e3
```

The report object is the completeness marker because the Cloud Run job writes it
after the NDJSON. Both generations are still required: the marker does not turn two
Cloud Storage writes into one atomic transaction. A missing generation, changed or
truncated export, mismatched URI/hash/byte/row metadata, or disagreement in report
counts, settings or source hashes fails before any BigQuery operation. Adding
`--execute` then delegates the already prepared bytes to the existing safe loader;
it does not use a direct BigQuery URI load or introduce another loading algorithm.
The Folkestone pair passed this preparation path and was then verified twice against
the existing protected table. Both executions returned `already_present_verified`,
submitted no load job and left all 459 rows and the table modification time unchanged.
This was the correct duplicate-safe result because the Cloud Run export is byte-
identical to the export used for the table's earlier `WRITE_EMPTY` load.

The native check downloaded the two exact object generations twice and ran two
uncached verification queries. Each query processed 270,243 bytes and billed BigQuery's
10 MiB minimum, with the existing 100 MiB cap. The approved developer identity ran
both successful jobs. No upload, retry, Terraform/IAM change, dbt invocation or live
conflict mutation occurred. See the
[Cloud export-to-BigQuery validation record](evidence/cloud-export-bigquery-validation.json).

The loader follows this sequence:

1. Check the destination, then read up to the expected row count plus one.
2. If rows already exist, compare every field with the local export. Equal data
   returns `already_present_verified`; different data fails without writing.
3. If empty, load the exact bytes with `WRITE_EMPTY`, `CREATE_NEVER`, zero tolerated
   bad records and no ignored fields. Wait for the load job to finish.
4. Read back and compare every row, including hashes, settings, nulls and weather.
   Equivalent UTC timestamp spellings are normalised. Only an exact comparison
   returns `loaded_verified`.

See [result_load.py](../src/runwx/adapters/bigquery/result_load.py). Successful
execution prints the load/verification job IDs and query bytes processed/billed,
alongside the local counts and hashes that were verified.

## Reruns, failure and cost controls

BigQuery's [WRITE_EMPTY option](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/Job#JobConfigurationLoad)
rejects a nonempty table. There is no append, truncate, delete or promotion step.
A query failure stops the load. A failed comparison leaves the candidate table
available for inspection and does not report success.

The load-job ID is deterministic from destination, region, export hash and schema
hash. Reusing that ID is a **first-load simplification**: it binds one logical load
to one BigQuery job. An existing job with that ID is awaited instead of submitting
a new attempt.
If a successful upload's response was lost, rerunning can verify the saved rows
without uploading again. A terminally failed job still needs inspection; the loader
does not invent a fresh attempt ID or promise recovery from every failure.
This is a sequential first-load contract, not a concurrent revision system.

The fixed-snapshot release retains this bounded rerun behaviour. Deliberate
corrections have distinct content hashes and must be supplied explicitly to an
analysis; they do not require an automatic current-revision pointer or attempt ledger.

Verification queries use GoogleSQL, disable cached results and set a 100 MiB
maximum billed-byte limit per query. The initial load uses two queries; an equal
rerun uses one. The row limit bounds returned data, not bytes scanned.

Normal batch loads are free; stored data and on-demand queries have separate
pricing and free allowances. This tiny test is estimated below $0.01 in additional
cost, not a guaranteed account spending cap. See [BigQuery pricing](https://cloud.google.com/bigquery/pricing).
The resources have deletion protection and no automatic expiry. Cleanup is a
separate operation: preserve wanted evidence before removing this table/dataset.

## Tests and next use

```bash
python -m pytest -q tests/test_bigquery_load.py
python -m pytest -q tests/test_gcs_bigquery_load.py
```

The tests use real SDK configuration objects and API signatures with a small fake
warehouse. They block network access and check first load, equal rerun, changed
data, lost acknowledgement, post-load mismatch and invalid inputs. They do not
execute SQL or prove that BigQuery accepts the schema. The separate
[verified cloud run](#verified-cloud-run) now supplies that evidence for this fixture.
The Storage-adapter tests additionally check exact-generation reads, pair
reconciliation, early rejection and delegation to the same loader.

The [staging → accepted-results fact → event-summary mart](dbt-models.md) SQL
and tests have now executed in BigQuery and matched the Python baseline.
Multiple Lydd and Folkestone editions are now loaded and compared. Course, distance
and timing compatibility remain explicit, and weather remains context rather than a
performance adjustment.

## Metric contract

The existing [Python summary](../src/runwx/services/race_summary.py) sorts accepted
finish durations ascending, selects `min(top_n, finisher_count)` (default N is 20),
and calculates their **median**, stored as `top_n_median_duration_s`. With an even
number of values, median averages the two central values. `mean_duration_s` is a
separate whole-field statistic; it does not define top-N.

The mart preserves this selection and median when expressing pace as
`duration_s / (distance_m / 1000.0)` in seconds per kilometre. Missing weather must
not remove accepted results. Use the [existing summary tests](../tests/test_race_summary.py)
as reference cases: the fastest three durations `[3600, 3720, 3900]` have a median
of 3720 seconds, not their mean of 3740 seconds.
