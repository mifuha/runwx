# First cloud input/output run

Status: **deployed with paired real-input validation on 12 September 2026**
(Europe/London). Two earlier synthetic executions and the first Folkestone report
remain retained. A new exact Folkestone 2019 execution matched both frozen local
artifacts. This proves the private storage, deployed parsing, reporting and warehouse-
export path.
The [historical BigQuery/dbt flow](architecture.md) remains a separately verified
path; this job does not load BigQuery or invoke dbt.

```text
Private input bucket (approved synthetic or fixed historical inputs)
    → download exact object generations; check SHA-256 hashes
    → temporary files → existing build_offline_report() + build_result_rows()
    → private report bucket: reports/<execution>/task-0-attempt-0.json
                            reports/<execution>/task-0-attempt-0.ndjson
```

The container's temporary files disappear after the job. The uploaded pair stays in
Cloud Storage until deleted. The job needs network access to Google Storage
and authentication, but never fetches race or weather provider data.

## Deployed resources and results

| Resource | Identifier |
| --- | --- |
| Project | `runwx-learning-mifuha` |
| Region | `europe-west1` for storage, registry and job |
| Private input bucket | `runwx-learning-mifuha-runwx-inputs` |
| Private report bucket | `runwx-learning-mifuha-runwx-reports` |
| Artifact Registry repository | `runwx` |
| Image builder service account | `runwx-image-builder@runwx-learning-mifuha.iam.gserviceaccount.com` |
| Runtime service account | `runwx-report@runwx-learning-mifuha.iam.gserviceaccount.com` |
| Cloud Run Job | `runwx-report` |

Deployed image, verified against the paired execution description and report:

```text
europe-west1-docker.pkg.dev/runwx-learning-mifuha/runwx/runwx@sha256:4a090fe42e24320b1eb169ff4bcd40be8641802e87528ffd90f89c307c333dbd
```

Cloud Build `414ee1ca-a217-4cbb-8a26-78383a49ddc4` produced this Linux image with
application revision `6378f4c236aa82bc40bc51443c200549714ae26f`
using the pinned base image and dependency locks. The local package installation
completed with network disabled. The immutable registry digest identifies the
deployed bytes.

| Execution | Result | Duration | Report generation | Export generation |
| --- | --- | ---: | --- | --- |
| `runwx-report-tdjvt` | 1 task succeeded, no retries | 27.510 s | `1788823251294987` | — |
| `runwx-report-btttr` | 1 task succeeded, no retries | 41.499 s | `1788823418694525` | — |
| `runwx-report-rpc8z` | 1 task succeeded, no retries | 71.630 s | `1789164918076677` | — |
| `runwx-report-6ccdt` | 1 task succeeded, no retries | 30.540 s | `1789226380183224` | `1789226379967796` |

The new paired output is stored at:

```text
gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-6ccdt/task-0-attempt-0.json
gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-6ccdt/task-0-attempt-0.ndjson
```

Every synthetic local report field matched except the two source file paths: hashes,
settings, quality counts, coverage and limitations all agreed. The two synthetic
cloud `report` objects were identical. Execution names and output URIs differed in
the surrounding metadata, as expected. Input generations matched the uploaded
objects; the first output's generation and checksums stayed unchanged after the repeat.

**Entirely synthetic demonstration:** 5 candidate rows, 3 accepted, 1 skipped,
1 invalid; weather matched 2 of 3 finishers. Best/median/mean finish durations were
3600/7200/8400 seconds. These are pipeline checks, not historical race findings.

**Fixed historical validation:** execution `runwx-report-rpc8z` read the exact
Folkestone 2019 HTML and weather CSV generations. It accepted all 459 candidate
results, matched weather for all 459 finishers and returned a 7515-second median.
Every report field matched the frozen local report except the expected local/GCS
source paths. The two earlier synthetic report generations remained unchanged.
Report v1 labels this weather `unknown`; the separate qualification evidence records
its ERA5 origin. See the [validation record](evidence/folkestone-cloud-run-validation.json).

**Paired historical validation:** execution `runwx-report-6ccdt` read those same
input generations with their expected SHA-256 hashes. Its report again accepted and
weather-matched all 459 candidates with a 7515-second median. Its 551,872-byte NDJSON
is byte-for-byte identical to the frozen warehouse input, including historical race,
ERA5 reanalysis and chip-time labels; SHA-256 is
`f95b3ae312e3131279a8a5ebbe77f58d3967d70bc7007b6c268f0bd4492eef47`.
The report records the image digest, full source revision, both input generations and
the export URI/hash/count. See the
[paired validation record](evidence/cloud-run-result-export-validation.json).

The [job execution page](https://console.cloud.google.com/run/jobs/details/europe-west1/runwx-report/executions?project=runwx-learning-mifuha)
shows status, configuration and logs. The
[report bucket](https://console.cloud.google.com/storage/browser/runwx-learning-mifuha-runwx-reports/reports?project=runwx-learning-mifuha)
and [registry](https://console.cloud.google.com/artifacts/docker/runwx-learning-mifuha/europe-west1/runwx?project=runwx-learning-mifuha)
require access to this private project; they are not public downloads.

## Artifact contract and failure behaviour

[report_io.py](../src/runwx/adapters/gcs/report_io.py) uses the official
`google-cloud-storage` client to download two objects and call the existing report
and export functions through the shared coordinator.
[cloud_report.py](../src/runwx/cloud_report.py) reads configuration from environment
variables and uses the runtime service account through Application Default
Credentials. No service-account key is needed.

Each download is pinned to the generation returned by its metadata lookup. The
bytes must also match the configured local SHA-256. A missing, changed or invalid
input fails the execution before either artifact upload.

Output names include execution, task and attempt identifiers. Both uploads use
`if_generation_match=0`, so an existing object causes failure instead of replacement.
The runtime also lacks delete/overwrite permission. There is no `latest.json` or
automatic selection of a current report. The result export uploads first; the report
envelope uploads last and marks a complete pair. A failure can therefore leave an
export without its report, which downstream processing must reject. Failed attempts
leave earlier objects alone. If an upload succeeds but its acknowledgement is lost,
inspect that exact object before rerunning: a failed execution does not prove that no
object was saved.
See Google's [generation preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions).

The version 2 cloud envelope retains the inner deterministic report at schema v1 and
adds the paired export metadata:

- `report`: the existing summaries, row counts, weather coverage, hashes, settings
  and limitations. Only `sources.race.file` and `sources.weather.file` change from
  local paths to `gs://` source locations.
- `execution`: job, execution, task index, attempt, configured image digest and full
  source commit embedded in the image.
  Check the digest against the actual execution description as well.
- `storage`: input URIs/generations, both output URIs and the export SHA-256, byte
  count, row count and schema version. The legacy report `output_uri` remains.

Cloud Run supplies the execution identifiers through its
[documented environment](https://docs.cloud.google.com/run/docs/container-contract).
Image identity is recorded around the report; the original report's limitation
about code/dependency versions remains. The cloud wrapper adds no analytical logic.

## Runtime permissions and configuration

[Terraform](../infra/gcp/main.tf) defines:

- Cloud Run, Cloud Storage, Artifact Registry, Cloud Build and IAM API enablements.
- Two private Standard buckets, uniform bucket-level access, enforced public
  access prevention and seven-day soft delete.
- One private Docker registry, one dedicated image builder and one runtime identity.
- The builder can read only the Cloud Build source prefix, write this image repository
  and write build logs. It has no runtime data permissions.
- Input Object Viewer restricted by an IAM condition to four named objects;
  output Object Creator restricted to the report bucket's `reports/` prefix.
- One manual job: one task, parallelism 1, 1 vCPU, 512 MiB memory, a five-minute
  timeout and zero task retries. No scheduler is configured.

The runtime has no project-wide data role, report-read permission or input-write
permission. [Object Creator](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)
cannot read, overwrite or delete objects. Retrieving reports requires separate
Object Viewer access; manual execution can use Cloud Run Invoker on this job.
Deployment permissions are separate from runtime permissions: resource/IAM
administration and permission to act as the runtime service account are needed
for setup, not for processing data.

## Saved inputs

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| [Synthetic race HTML](../data/sample_race_synthetic.html) | 1044 | `70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182` |
| [Synthetic weather CSV](../data/sample_lydd_weather_synthetic.csv) | 187 | `835e03b360af5403540aa1f06a99f164ce30140cc958ea9fdbaef301165ca25f` |

The HTML is fabricated: no runner names, an invalid example source URL, placeholder
coordinates and invented times. The parser labels its format/provider `eventrac`;
that does not establish a real event. The weather CSV is also invented despite
its Lydd filename. Neither input is historical evidence.

## Deployment and comparison

The initial run used Google Cloud CLI 583.0.0, Terraform 1.13.5 and Google provider
7.46.1. Local CLI credentials and Application Default Credentials are needed for
setup. Keep credentials, actual tfvars and Terraform state outside Git.

1. Use a dedicated project with billing configured. Enable Service Usage, Cloud
   Resource Manager, Cloud Billing and Billing Budgets for setup. Project creation,
   billing linkage, these setup APIs and the budget are separate from Terraform.
2. Copy [terraform.tfvars.example](../infra/gcp/terraform.tfvars.example) to local
   `infra/gcp/terraform.tfvars`. Set the project and keep `image_uri = null`.
   Initialise Terraform and review/apply a saved plan for storage, registry and
   identity. This stage does not create or execute a job.
3. Build and publish with [cloudbuild.image.yaml](../infra/gcp/cloudbuild.image.yaml),
   supplying a unique `_IMAGE_TAG` and the source commit as `_VCS_REF`. Record the
   resulting immutable registry digest. A standard Docker build remains available
   through the [container instructions](container.md).
4. Upload only the two synthetic inputs, using `gcloud storage cp
   --if-generation-match=0`. Record their metadata/generations; this precondition
   prevents overwriting existing objects.
5. Set `image_uri` to the pushed digest reference. Review/apply the job plan;
   creating the job does not execute it.
6. Execute with defaults for the synthetic demonstration, or use execution-only
   environment overrides for explicitly allowed historical objects and their hashes.
   Download both artifacts and compare them with their local baselines.

These commands execute an existing cloud job. From the repository root and an
activated Python environment, set `PROJECT` to that job's project ID first:

```bash
REGION=europe-west1
EVIDENCE=$(mktemp -d /tmp/runwx-gcp-evidence.XXXXXX)

python -m runwx report \
  --race-html data/sample_race_synthetic.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id runwx-synthetic-half --distance-m 21097 \
  --timezone Europe/London --weather-kind synthetic > "$EVIDENCE/local.json"

python -m runwx export-results \
  --race-html data/sample_race_synthetic.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id runwx-synthetic-half --distance-m 21097 \
  --timezone Europe/London --race-kind synthetic --weather-kind synthetic \
  > "$EVIDENCE/local.ndjson"

gcloud run jobs execute runwx-report --project "$PROJECT" --region "$REGION" \
  --wait --format=json > "$EVIDENCE/execution.json"
```

After a successful execution, read its actual `metadata.name` from `execution.json`
into `EXECUTION`, then retrieve and compare:

```bash
REPORT_URI="gs://${PROJECT}-runwx-reports/reports/${EXECUTION}/task-0-attempt-0.json"
EXPORT_URI="gs://${PROJECT}-runwx-reports/reports/${EXECUTION}/task-0-attempt-0.ndjson"
gcloud storage cp "$REPORT_URI" "$EVIDENCE/cloud.json"
gcloud storage cp "$EXPORT_URI" "$EVIDENCE/cloud.ndjson"
gcloud storage objects describe "$REPORT_URI" --format=json > "$EVIDENCE/output-object.json"
gcloud run jobs describe runwx-report --project "$PROJECT" --region "$REGION" \
  --format=json > "$EVIDENCE/job.json"
python scripts/compare_cloud_report.py "$EVIDENCE/local.json" "$EVIDENCE/cloud.json"
cmp "$EVIDENCE/local.ndjson" "$EVIDENCE/cloud.ndjson"
```

Retain a separate evidence directory for each run. The comparator excludes only
the two source file paths. Check execution IDs, input generations and actual image
references separately. Compare the first output's metadata again after the repeat
so unchanged analytical results do not conceal an overwritten object.

## Costs and retained resources

The retained output objects use less than 0.6 MiB; the approved synthetic and
Folkestone inputs use less than 0.5 MiB. Artifact Registry retains the published
image layers, and Cloud Build retains build records and staged source archives.
Actual billed charges were not independently verified; missing cost data does not
mean zero cost.

Pricing checked on 7 September 2026, in USD before tax, currency conversion or
free allowances:

| Item | Estimate |
| --- | --- |
| Cloud Run, Belgium | $0.000018/vCPU-second plus $0.000002/GiB-second. At 1 CPU/0.5 GiB, one billed minute is about $0.00114; two minima total about $0.00228 compute. |
| Standard storage, Belgium | $0.02/GiB-month. Current inputs and reports remain below 0.5 MiB. |
| Storage operations | Regional Class A $0.005/1,000; Class B $0.0004/1,000. |
| Artifact Registry | About $0.10/GiB-month above the shared 0.5 GiB free allowance. |

Sources: [Cloud Run pricing](https://cloud.google.com/run/pricing),
[Storage pricing](https://cloud.google.com/storage/pricing) and
[Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing).
Same-region input/image transfers are free under those pricing rules; report
retrieval to a laptop can incur internet transfer charges. Paid image scanning was
not enabled. Cloud Build recorded three short parser failures and one successful
build before the Dockerfile frontend compatibility fix was verified.

The below-$1 estimate assumes at most five manual executions, one image under
1 GiB, tiny inputs/reports and one month's retention. A project-only £3 monthly
budget alert tracks cost before credits, at 50/90/100% thresholds. Neither the
estimate nor the [budget alert](https://docs.cloud.google.com/billing/docs/how-to/budgets)
is a spending cap.

The job has no idle compute charge, but saved objects/images and any billable logs
remain after it finishes. Soft-deleted objects remain chargeable for seven days.
Terraform prevents bucket/registry destruction and job deletion by default;
buckets also refuse deletion while non-empty. Cleanup must account for those
protections, retained reports, and the separately managed project and budget.

## Verification

Follow-up checked on Ubuntu/WSL, 12 September 2026:

- Local and CI Python suites passed **255 tests**; CI also built/smoke-tested the
  locked report image and passed Terraform and dbt checks.
- Cloud Build used the dedicated builder, explicit logging mode, tracked source
  archive and full commit. The resulting digest is the deployed digest shown above.
- The reviewed targeted plan and apply were **0 additions, 1 in-place change and
  0 deletions**: only the existing job image and matching `RUNWX_IMAGE` value changed.
  A final targeted plan reported no changes.
- Execution `runwx-report-6ccdt` succeeded once. The report and exact NDJSON both
  reconcile with the frozen local artifacts; input/output generations, hashes,
  counts, image and source revision are recorded in the paired validation record.
- No BigQuery load, dbt run, scheduler, new IAM grant, bucket or parallel job was
  created. The three older report objects and stored synthetic job defaults remain.

Follow-up checked on Ubuntu/WSL, 11 September 2026:

- The dedicated builder plan applied **5 additions, 0 changes and 0 deletions**.
  The final image build succeeded after three short parser failures exposed the
  missing Dockerfile frontend declaration.
- The input/job plan applied **1 addition, 1 in-place change and 1 deletion** because
  Terraform replaces a conditional IAM member when its expression changes. A targeted
  read-only plan across all seven affected resources then reported no changes.
- Execution `runwx-report-rpc8z` succeeded once with one task and zero retries. Its
  downloaded report matched the 459-result local baseline except source file paths;
  both previous synthetic report generations and the job's synthetic defaults remained
  unchanged.
- Full Python suite: **251 passed in 4.26s**. Terraform formatting, validation, JSON,
  links and whitespace checks passed. The successful Cloud Build exercised the
  container build and its network-disabled package-install step.

Checked on Ubuntu/WSL, 8 September 2026:

- Full Python suite: **148 passed in 1.79s**. Cloud-boundary tests block socket
  connections and use saved synthetic inputs.
- Two local container calls used fake storage with real SDK method signatures,
  network disabled and read-only inputs. They matched the local baseline, and
  `pip check` passed. The two cloud runs then exercised real transport and identity.
- Terraform bootstrap added 10 resources; the job plan added 1. Neither changed
  or destroyed existing resources. Final read-only plan: no changes. Format and
  validation passed; bucket privacy and runtime grants were inspected.
- Both downloaded reports matched the local baseline and actual execution/input
  metadata. The first output remained unchanged after the second execution.
- Baseline SHA-256:
  `fd3872c315cae21fab8b0c0377906a59d01685a359e59c77e1d95b090c461fe5`.
- Not run: full suite inside the image, deliberate live IAM-denial or duplicate
  upload probes, other operating systems, BigQuery or dbt. The denied-operation
  and failed-upload cases are covered locally. Actual billed cost is unverified.

The [main boundary test](../tests/test_cloud_report.py),
`test_saved_report_matches_local_and_repeat_keeps_both_outputs`, supplies saved
bytes through fake storage and runs two execution names. It checks expected row
counts and durations, agreement with the local report and preservation of both
outputs. Separate tests cover changed hashes, failed downloads/parsing and
attempts to overwrite an earlier success.

See [architecture](architecture.md) for the separate result-row and dbt path, and
the [report reference](race-report.md) for analytical limitations.
