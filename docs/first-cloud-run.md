# First cloud input/output run

Status: **deployed and verified on 8 September 2026** (Europe/London).
Two successful cloud executions matched the synthetic local baseline.
This is the next part of Slice B, not a new roadmap. Its purpose is to prove the
execution path before adding useful historical race analysis in BigQuery/dbt.

```text
Private input bucket (fully synthetic HTML + synthetic weather CSV)
    → download exact object generations; check approved SHA-256 hashes
    → temporary files → existing build_offline_report()
    → private report bucket: reports/<execution>/task-0-attempt-0.json
```

The container's temporary files disappear after the job. The uploaded JSON stays
in Cloud Storage until explicitly deleted. The job needs network access to Google
Storage and authentication, but never fetches race or weather provider data.

## What was deployed

| Resource | Actual identifier |
| --- | --- |
| Dedicated project | `runwx-learning-mifuha`, number `840088506058` |
| Billing | `01B1B2-1644DE-88DA97` — My Billing Account, GBP; Free Trial confirmed by Miha, expires 7 December 2026 |
| Region | `europe-west1` for storage, registry and job |
| Private input bucket | `runwx-learning-mifuha-runwx-inputs` |
| Private report bucket | `runwx-learning-mifuha-runwx-reports` |
| Artifact Registry repository | `runwx` |
| Runtime service account | `runwx-report@runwx-learning-mifuha.iam.gserviceaccount.com` |
| Cloud Run Job | `runwx-report` |
| £3 monthly budget | `runwx-first-run`, ID `0e13b36f-2013-40e5-8256-3a16bf4cc872` |

Deployed image, verified against both execution descriptions and saved reports:

```text
europe-west1-docker.pkg.dev/runwx-learning-mifuha/runwx/runwx@sha256:f90bc8ea97497ca377dec4cbc2e4bfb43cfe4484658e602561039782392475d5
```

This is the Linux/amd64 manifest inside the published `first-run` image index
`sha256:2c8257f6f0f1d79b69ac94ce429736fbf74fa977811a430968fe773ef1e1445c`.
These are two levels of the same image, not two application builds. All 51 Python
source files in the tested image matched the checkout before publication. The Git
label points to the base commit: the image was built before the cloud changes
were committed. Use the verified image digest to identify the deployed code.

| Execution | Result | Start-to-completion time | Output generation |
| --- | --- | ---: | --- |
| `runwx-report-tdjvt` | 1 task succeeded, no retries | 27.510 s | `1788823251294987` |
| `runwx-report-btttr` | 1 task succeeded, no retries | 41.499 s | `1788823418694525` |

Both reports were downloaded successfully. Their private locations are:

```text
gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-tdjvt/task-0-attempt-0.json
gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-btttr/task-0-attempt-0.json
```

Both matched every local report field except the two source file paths. Input
hashes, analysis settings, quality counts, coverage and limitations all matched.
The two cloud `report` objects were identical; execution names and output URIs
legitimately differed in the surrounding metadata. Input generations matched the
uploaded objects. The first output's generation and checksums stayed unchanged
after the repeat. This used **2 of the approved maximum 5 executions**; five is an
operating limit for this deployment, not a Cloud Run lifetime quota.

**Entirely synthetic demonstration:** 5 candidate rows, 3 accepted, 1 skipped,
1 invalid; weather matched 2 of 3 finishers. Best/median/mean finish durations were
3600/7200/8400 seconds. No historical performance conclusion follows from this.

Measured storage: 1231 input bytes and two 3893-byte reports, **9017 bytes total**.
Artifact Registry reported **61.579 MB**. Cloud Monitoring exposed 60 seconds of
`billable_instance_time` at the 00:25 BST check; this early metric snapshot did not
account for both one-minute billing minima, so it is not treated as a complete
billed total. The two minima imply about **$0.00228 compute** before allowances at
the rates below, an estimate rather than an actual charge. Actual billed cost was
not accessible: the desktop browser bridge failed on the WSL workspace path, and
the billing-account/budget APIs do not supply incurred charges. Check Billing
Reports after usage has appeared; do not read missing cost data as £0.

No trial restriction blocked deployment. No paid upgrade or destructive cleanup
was performed. Git publication was authorised separately after deployment.
The project, billing link, setup APIs and
budget were created with `gcloud`; the job, buckets, registry, runtime identity,
bucket grants and four workload APIs are recorded in local Terraform state.

### Inspect it in the console

- [Job executions](https://console.cloud.google.com/run/jobs/details/europe-west1/runwx-report/executions?project=runwx-learning-mifuha): open an execution for status, configuration and logs.
- [First execution](https://console.cloud.google.com/run/jobs/executions/details/europe-west1/runwx-report-tdjvt?project=840088506058) and [second execution](https://console.cloud.google.com/run/jobs/executions/details/europe-west1/runwx-report-btttr?project=840088506058).
- [Saved reports](https://console.cloud.google.com/storage/browser/runwx-learning-mifuha-runwx-reports/reports?project=runwx-learning-mifuha): open either execution folder, then `task-0-attempt-0.json` to view/download it while signed in.
- [Private inputs](https://console.cloud.google.com/storage/browser/runwx-learning-mifuha-runwx-inputs/approved?project=runwx-learning-mifuha).
- [Registry](https://console.cloud.google.com/artifacts/docker/runwx-learning-mifuha/europe-west1/runwx?project=runwx-learning-mifuha): inspect the `runwx` image and its digest.
- [Billing Reports](https://console.cloud.google.com/billing/01B1B2-1644DE-88DA97/reports): filter Projects to `runwx-learning-mifuha`, select the current month, and distinguish usage cost from credits.
- [Budget alerts](https://console.cloud.google.com/billing/01B1B2-1644DE-88DA97/budgets) and [trial overview](https://console.cloud.google.com/billing/01B1B2-1644DE-88DA97/overview). Do not activate paid billing.

Local evidence is in `/tmp/runwx-gcp-20260908/`: `local.json`, `cloud-1.json`,
`cloud-2.json`, execution/object metadata, `verification.json`, plans and usage
snapshot. Temporary local files can disappear; the private reports survive in GCS.

## Small storage boundary

[report_io.py](../src/runwx/adapters/gcs/report_io.py) uses the official
`google-cloud-storage` client. It downloads two objects and calls the existing
report function. There is no mount, storage framework or new analytical logic.
[cloud_report.py](../src/runwx/cloud_report.py) reads the job configuration from
environment variables and uses the runtime service account through Application
Default Credentials. No service-account key is needed.

Each input download is pinned to the generation returned by its metadata lookup.
The downloaded bytes must also match the configured local SHA-256. A missing,
changed or invalid input fails the execution before any report upload.

The output name includes execution, task and attempt identifiers. Upload uses
`if_generation_match=0`: an existing object causes failure instead of replacement.
The runtime also lacks delete/overwrite permission. There is no `latest.json` or
automatic selection of a current report. A failed attempt leaves earlier reports
alone. If an upload succeeds but its acknowledgement is lost, inspect that exact
object before rerunning; failure alone does not prove that no object was saved.
These rules follow Google's [generation preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions).

The saved JSON contains:

- `report`: the existing race summary, row counts, weather coverage, hashes,
  settings and limitations. Only `sources.race.file` and `sources.weather.file`
  change from local paths to `gs://` source locations.
- `execution`: job name, execution name, task index, attempt and configured image
  digest. Terraform sets this digest to the same immutable reference it deploys.
- `storage`: source object URIs/generations and the output URI.

The envelope is version 1. Image identity is recorded around the report; the
original report's code/dependency-version limitation remains. The configured
digest must also be checked against the actual deployed execution, not trusted
as independent proof on its own. Runtime identifiers come from
[Cloud Run's documented environment](https://docs.cloud.google.com/run/docs/container-contract).

## Approved setup

Use one dedicated learning project, display name `runwx-learning`, with Miha's
confirmed project ID and **Free Trial** billing account. Signup is complete; Miha
reports $300 credit and console expiry **7 December 2026**. Expiry is user-reported,
not API-verified. Never activate or upgrade to paid billing. Credit does not expand
the agreed resource or spending scope. Use `europe-west1` (Belgium) for the job,
buckets and registry, and the future BigQuery dataset. This fits the agreed GCP
plan; it is not a claim that GCP is always cheaper than AWS.

[Terraform](../infra/gcp/main.tf) contains:

- Four API enablements: Cloud Run, Cloud Storage, Artifact Registry and IAM.
  Bootstrap Service Usage and Cloud Resource Manager first.
- Two private Standard buckets with uniform bucket-level access and public access
  prevention. No public members or object ACLs. Seven-day soft delete is explicit.
- One private Docker registry and one dedicated `runwx-report` service account.
- Input Object Viewer limited by an IAM condition to the two named objects;
  output Object Creator limited to the `reports/` prefix on the report bucket.
- One manual Cloud Run Job: one task, parallelism 1, 1 vCPU, 512 MiB memory,
  five-minute task timeout and zero task retries. Submit executions sequentially.

The runtime has no project-wide data role, report-read permission, upload access
to inputs, or credentials file. [Object Creator](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)
cannot read, overwrite or delete objects. The human who retrieves evidence needs
Object Viewer on the report bucket and permission to view the job/execution;
manual execution can use Cloud Run Invoker on this job.

Keep deployment identity separate. Setup needs permissions to enable services,
manage these buckets and their IAM, create the registry/service account/job, and
act as this runtime account. The corresponding predefined administrator roles
are Service Usage Admin, Storage Admin, Artifact Registry Admin, Service Account
Admin and Cloud Run Admin; scope them to this dedicated project only when needed.
Service Account User can be scoped to the runtime account. Do not give these roles
to the runtime or add Owner as a shortcut. Check the chosen identity's existing
access before granting anything. Billing linkage is a separate approved action.

Approved data scope: only these two files, uploaded privately:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| [Synthetic race HTML](../data/sample_race_synthetic.html) | 1044 | `70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182` |
| [Synthetic weather CSV](../data/sample_lydd_weather_synthetic.csv) | 187 | `835e03b360af5403540aa1f06a99f164ce30140cc958ea9fdbaef301165ca25f` |

The HTML was written as a fully fabricated fixture: no runner names, an invalid
example source URL, placeholder coordinates and invented times. Its name says
Synthetic. The parser still labels the format/provider `eventrac`; that is not
evidence of a real Eventrac event. The existing weather CSV is also invented,
despite its Lydd filename. Neither input is historical race evidence. The earlier
proposal to upload the real Lydd snapshot is withdrawn.

## Cost and cleanup

Checked official pricing on 7 September 2026, in USD before tax or currency
conversion. These are estimates, not a promise of free-tier eligibility.

| Item | Estimate for this bounded run |
| --- | --- |
| Cloud Run, Belgium | At $0.000018/vCPU-second and $0.000002/GiB-second, one billed minute at 1 CPU/0.5 GiB is about $0.00114; five minutes about $0.0057, before free allowance. Jobs have a one-minute minimum. |
| Standard storage, Belgium | $0.02/GiB-month. The two inputs total 1231 bytes; their storage is less than $0.000001/month. |
| Storage operations | Standard regional Class A $0.005/1,000; Class B $0.0004/1,000. A few downloads/uploads are fractions of a cent. |
| Artifact Registry | About $0.10/GiB-month above the shared 0.5 GiB free allowance. Allow $0.10/month for up to 1 GiB, without relying on that allowance. |

Sources: [Cloud Run pricing](https://cloud.google.com/run/pricing),
[Storage pricing](https://cloud.google.com/storage/pricing),
[Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing).
Same-region storage/image transfers to the job are free under those pricing rules.
Report retrieval to the laptop can incur small internet transfer charges. Keep
logs small; do not enable paid image scanning, Cloud Build or other services for
this task. This estimate assumes the dedicated project has no unrelated usage.

Recommend at most five manual executions, one image under 1 GiB and these tiny
inputs/reports, retained for one month. Expect well below $1 for that scope; use a
project budget alert as a precaution. Discovery found GBP billing, so the final
proposal is **£3/month**, replacing the earlier $5 placeholder, with 50/90/100%
alerts on this project and credit treatment `EXCLUDE_ALL_CREDITS`. This makes
usage visible before trial credits reduce the bill. The £3 alert was approved
and created; the workload and below-$1 estimate remain.
A [budget alert is not a spending cap](https://docs.cloud.google.com/billing/docs/how-to/budgets).
The job has no idle compute charge, but saved objects/images and any billable logs
remain after execution finishes. Soft-deleted objects remain chargeable during
their seven-day retention period.

After recording evidence, review the exact job, registry images and two buckets
for cleanup. Ask before deletion. Terraform blocks bucket/registry destruction
and job deletion by default; buckets also refuse deletion while non-empty.
Remove protections only for a separately approved cleanup. Do not delete the whole
project as a shortcut, silently expire successful reports, or disable shared APIs.

## Local authentication and account discovery

Installed locally under `~/.local`: Google Cloud CLI 583.0.0 and Terraform 1.13.5.
The CLI archive matched Google's published SHA-256. No credential files belong in
this repository and no service-account keys are needed.

In an Ubuntu terminal as `mihaf` (not root), run:

```bash
export PATH="$HOME/.local/bin:$PATH"
gcloud auth login --update-adc --no-launch-browser
```

Open the printed Google URL in your own browser and choose the same Google account
as the Free Trial console. Enter any returned code only in your Ubuntu terminal.
Tell Codex only that login finished. Do not paste codes, tokens or credential files
into chat. `--update-adc` also prepares the user credentials Terraform will use,
so a second browser login is unnecessary for this fresh setup. See the official
[login flags](https://docs.cloud.google.com/sdk/gcloud/reference/auth/login).

Login is complete. Account/project/billing discovery and an ADC refresh check
passed with token output discarded. Miha approved the deployment on 8 September
2026 after confirming the trial account and expiry in the console. The new project
`runwx-learning-mifuha` (number `840088506058`) was created in the existing personal
organisation `224555148161` and linked to the confirmed billing account
`01B1B2-1644DE-88DA97` (My Billing Account, GBP). No paid-account upgrade was made.

An open
billing account or `billingEnabled: true` does not establish paid/trial status;
confirm the trial account in the console. The billing-account API does not expose
the trial expiry date. Do not use `gcloud init` to create/select a project blindly,
accept API-enablement prompts, or link billing during discovery.

Discovery commands will set `CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API=false`
and `CLOUDSDK_CORE_DISABLE_PROMPTS=true` for those calls only, so a disabled API
produces an error rather than an enablement prompt.

The approved scope and deployment evidence are saved locally in
`/tmp/runwx-gcp-20260908/`. Terraform state and actual tfvars remain git-ignored.

## Deployment sequence after approval

This is the sequence used for the approved deployment. Read-only discovery came
before approval; project creation, billing linkage, API enablement, resources and
uploads followed it. Repeating these steps is a new operation, not a test command.
If the Free Trial blocks a step, record the actual error and recommend the smallest
alternative. Do not upgrade the account.

1. Confirm project ID, billing account, region, permitted inputs and the bounded
   run/cost scope above. Create/link the dedicated project only if authorised.
   Enable the setup APIs needed for this path: Service Usage, Cloud Resource
   Manager, Cloud Billing and Billing Budgets. Set the project-only budget alert.
2. Copy [terraform.tfvars.example](../infra/gcp/terraform.tfvars.example) to local
   `infra/gcp/terraform.tfvars`, with the approved project. Keep `image_uri = null`.
   Run `terraform init`, save/review a plan and apply it to create storage, registry
   and identity. No job exists yet. State, plans and actual tfvars are git-ignored;
   keep them private and retain state for controlled cleanup.
3. Build from the reviewed source using the existing [container instructions](container.md),
   with a separate tag, `runwx:cloud-local`. It now installs the one additional
   direct dependency, `google-cloud-storage`. Authenticate Docker to the private
   registry, push this image and record its actual registry digest. When Docker
   uses sudo/root, its registry credentials must be configured for that same user.
   A Git revision label alone does not identify uncommitted source edits.
4. Upload only the approved inputs to the configured names, with
   `gcloud storage cp --if-generation-match=0`. Capture object metadata/generations.
   Do not overwrite existing inputs on a repeat.
5. Set `image_uri` to the pushed `...@sha256:...` reference, save/review the next
   Terraform plan and apply it. This creates the job without executing it.
6. Execute twice sequentially and retrieve both reports. Reserve the remaining
   three executions for necessary fixes/rechecks within the same approved scope.

Example execution/retrieval commands, from the activated environment at repo root.
Set `PROJECT` to the approved project ID first:

```bash
REGION=europe-west1
EVIDENCE=$(mktemp -d /tmp/runwx-gcp-evidence.XXXXXX)

python -m runwx report \
  --race-html data/sample_race_synthetic.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id runwx-synthetic-half --distance-m 21097 \
  --timezone Europe/London --weather-kind synthetic > "$EVIDENCE/local.json"

gcloud run jobs execute runwx-report --project "$PROJECT" --region "$REGION" \
  --wait --format=json > "$EVIDENCE/execution.json"
```

Continue only after execution succeeds. Read its actual `metadata.name` from
`execution.json` into `EXECUTION`; do not substitute the job name. Then:

```bash
REPORT_URI="gs://${PROJECT}-runwx-reports/reports/${EXECUTION}/task-0-attempt-0.json"
gcloud storage cp "$REPORT_URI" "$EVIDENCE/cloud.json"
gcloud storage objects describe "$REPORT_URI" --format=json > "$EVIDENCE/output-object.json"
gcloud run jobs describe runwx-report --project "$PROJECT" --region "$REGION" \
  --format=json > "$EVIDENCE/job.json"
python scripts/compare_cloud_report.py "$EVIDENCE/local.json" "$EVIDENCE/cloud.json"
```

Use a fresh evidence directory for the second run. Verify the deployed image
reference in each execution against both the registry digest and report envelope.
Keep both output URIs/generations, downloaded JSON files, execution descriptions,
image reference and comparison output. Do not call the cloud task complete until
the actual report is retrievable and all these checks pass.

## Checks and learning

Checked on Ubuntu/WSL, 8 September 2026:

- Full Python suite: `python -m pytest -q` — **148 passed in 1.79s**.
  The cloud boundary tests block socket connections and use saved synthetic inputs.
- Earlier container checks used the real Storage SDK's method signatures with fake
  storage, network disabled and read-only inputs. Both calls matched the local
  baseline; `pip check` passed. Live transport and the real runtime identity were
  then exercised by the two successful cloud executions above.
- Terraform 1.13.5 / Google provider 7.46.1: reviewed bootstrap plan added 10
  resources; job plan added 1. Neither changed or destroyed existing resources.
  Final read-only plan exited 0: no changes. Format and validation passed.
- Compared both downloaded reports with the regenerated local baseline; separately
  checked actual image references, execution IDs, input generations, output
  metadata and all runtime limits. Both report contents agreed, and the first
  output remained unchanged. Bucket privacy/IAM policies were inspected.
- The local baseline's SHA-256 is
  `fd3872c315cae21fab8b0c0377906a59d01685a359e59c77e1d95b090c461fe5`.
  Regeneration was byte-identical to the previous synthetic baseline.
- Final documentation checks: 13 relative links resolved, bash command blocks
  parsed, Terraform format check and `git diff --check` passed. Checksums confirmed
  the existing Dockerfile, dockerignore, container documentation and README were
  unchanged by this cloud deployment. Terraform state/tfvars/plans are ignored.
- Not run: full Python suite inside the image, deliberate live IAM-denial or
  duplicate-upload probes, other operating systems, GitHub CI, BigQuery or dbt.
  The no-overwrite/failure cases are covered locally; successful real cloud I/O
  does not by itself prove every denied operation. Actual billed cost is unverified.

Start with [main](../src/runwx/cloud_report.py): it reads settings, records the
Cloud Run execution identity, obtains the keyless Storage client, then calls
[run_stored_report](../src/runwx/adapters/gcs/report_io.py). That function downloads
and hashes the two inputs, calls the existing report, and publishes once:

```python
report = build_offline_report(paths["race"], paths["weather"], **settings)
# The surrounding code records source locations and execution metadata.
client.bucket(output_bucket).blob(output_name).upload_from_string(
    encoded, content_type="application/json", if_generation_match=0, timeout=30,
)
```

The [main test](../tests/test_cloud_report.py),
`test_saved_report_matches_local_and_repeat_keeps_both_outputs`, supplies saved
synthetic bytes through fake storage and runs two execution names. It checks the
expected row counts and durations, compares the report with the local baseline,
and confirms both outputs survive. Network access is blocked throughout the test.

Exercise: in `test_existing_success_is_not_overwritten`, predict what changing
only the second call's execution name would do. Try that change locally, adapt
its expected result, and run `python -m pytest -q tests/test_cloud_report.py`.
It needs no cloud execution.

Next: expose useful race-result rows in BigQuery and build the first tested dbt
model for median and top-N average pace, with explicit units, settings, counts and
weather coverage. Keep this synthetic cloud proof separate from real historical
evidence. The intended comparison is recorded in [progress](../RUNWX_PROGRESS.md);
the [active plan](../RUNWX_PLAN_AND_CODEX_GUIDELINES.md) is unchanged.
