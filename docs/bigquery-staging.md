# First BigQuery staging load

Status: local loader and tests implemented; **cloud load and SQL validation pending**.
This step puts the [synthetic result export](result-export.md) into one table.
It does not yet add dbt models or change the existing Cloud Run report job.

## Dataset, table and schema

A BigQuery dataset groups tables and sets their location and access. This first
dataset is `runwx_staging` in `europe-west1`. Its `synthetic_results` table holds
one complete synthetic export, including skipped and invalid candidates.

The [explicit schema](../src/runwx/adapters/bigquery/result_rows.schema.json) gives
each column a type: seconds and metres are integers, hashes and outcomes are
strings, and observation times are timestamps. `settings` and `weather` are nested
records. Rejected durations and absent weather remain null; schema inference is off.

The source-row grain and identity are unchanged. This table accepts one export;
appending multiple analyses or selecting historical revisions is later work.

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
hash. An existing job with that ID is awaited instead of submitting a new attempt.
If a successful upload's response was lost, rerunning can verify the saved rows
without uploading again. A terminally failed job still needs inspection; the loader
does not invent a fresh attempt ID or promise recovery from every failure.
This is a sequential first-load contract, not a concurrent revision system.

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
```

The tests use real SDK configuration objects and API signatures with a small fake
warehouse. They block network access and check first load, equal rerun, changed
data, lost acknowledgement, post-load mismatch and invalid inputs. They do not
execute SQL or prove that BigQuery accepts the schema; the first real load must
supply that evidence.

After cloud verification, the next model will select accepted finishers, calculate
pace in seconds per kilometre and support median/top-N mean pace with coverage
kept separate. Those dbt models are not implemented here. The eventual historical
comparison still requires a suitable second edition and checked course, distance
and timing comparability; weather remains context rather than a performance adjustment.
