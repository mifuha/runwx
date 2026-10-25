# Read-only comparison API

The [live comparison](https://runwx-api-f6n35ol7sa-ew.a.run.app/) reads the existing
dbt comparison marts through this API. It does not parse race data, align weather
or calculate new statistics.

The service root (`/`) serves the small comparison page. The live
[How it works page](https://runwx-api-f6n35ol7sa-ew.a.run.app/how-it-works)
explains the path from fixed inputs to the chart, using Folkestone 2019 as one
example.
The pages link to each other. The comparison page uses the endpoint below to
populate course, pace and weather selectors, two aligned accessible SVG trend
plots, a temperature–pace scatter and a compact edition table. Pace stays visible beside the selected weather
measure. The HTML, CSS and JavaScript are packaged with the API; the page has no
external frontend or chart dependency.

```text
GET /api/courses/{course_slug}/comparison
```

The reviewed course slugs in this code are `lydd-half`, `folkestone-half`,
`great-north-run`, `battersea-park-10k` and `berlin-marathon`. All five are live,
covering 61 editions. Each slug maps
to one explicit BigQuery mart. The URL cannot select a table or submit SQL.
Existing course queries select fixed public columns, bind the expected course ID
and read at most 50 editions. Berlin reads at most 17 rows from its materialized
summary and requires the complete reviewed 16-edition cohort.
Lydd, Folkestone, GNR and Berlin keep the 64 MiB query cap. Battersea uses
the existing 200 MiB cap, although its final comparison now reads an 18-row stored
table. The cap is unchanged; it is not measured usage. During the original
13-edition deployment, a 64 MiB query failed because BigQuery required at least
130 MiB.

The [Battersea serving update](battersea-serving.md) preserves every public value
and the same API read access. Its edition models remain views.

Battersea has 18 full-field editions from 2019 and 2022–2024. The page shows
their dates so races in the same year remain distinct. Its published times are manually timed
without a chip/gun distinction, so baseline pace changes are left blank. The pace
and ERA5 weather statistics are descriptive. The live page shows all 18 editions
and their 2,725 finishers.

The 7 October 2026 deployment added the five 2019 editions. The live response
matched all 18 reconciled warehouse rows; the other three courses were unchanged.
Health and page checks passed, and Terraform reported no remaining changes.
The [2019 source note](battersea-2019-local-pilot.md) records the start-time
evidence and the June race that remains excluded.

The full-field response contains the course and baseline identity, followed by
editions in date order. Each edition includes finishers; median, mean, p25–p75 and fastest-N
pace; matched-weather coverage and medians; its compatibility status; and its
pace/speed change from the stated baseline. Pace values are seconds per kilometre.

Great North Run has a separate sampled response. Its 19 editions use the fastest
1,000 available running results per year, not the full race field. The response
uses `sample_size` rather than `finishers`, keeps chip/gun/unknown timing counts,
and gives one fixed 10:00–14:00 local start-area ERA5 weather context per edition.
That weather is not matched to individual runners. The page labels this clearly
and plots the years with the gaps for 2020 and the different-route 2021 edition.
The differences from the 2019 baseline are descriptive, not weather effects.
The GNR image and read grants for its summary table and comparison view are deployed.
All 19 public editions matched the hash-verified local exports; Lydd and Folkestone
responses were unchanged. The [GNR deployment record](evidence/gnr-public-api-validation.json)
retains the image, checks and limitations.

Berlin has a separate `research_capture` response for 2003–2018: 541,730 accepted
records from a published anonymised research dataset. It returns captured, accepted,
held and published counts, retaining count differences and the unknown 2013 total.
These are not verified complete official fields. Timing basis and individual starts
are unknown; the course-era grouping does not prove identical routes.

Pace values come directly from `mart_berlin_edition_summary`. Weather is a fixed
09:00–15:00 Europe/Berlin finish-area ERA5 context with seven observations, not
runner-matched exposure. Precipitation is the window total. The response has no
baseline change, official places, inferred starts or matched-runner coverage.
The page labels these differences and keeps the existing courses' responses intact.
See [Berlin statistics and verification](berlin-statistics.md).

The comparison page has a temperature-versus-pace scatter plot for each course.
Each dot is one edition; hover, keyboard focus or tap shows its values. Battersea
uses full dates to distinguish races in the same year. Pace follows the existing
selector; higher seconds per kilometre means slower pace. Captions distinguish
Berlin and GNR's fixed weather windows from the other courses' runner-midpoint
weather summaries, which depend on finishing durations. GNR remains a top-1,000
sample. Small cohorts carry a caution. Courses are kept separate, with no fitted
curve or correlation score. The plot reuses the existing API response.
All five scatter plots are deployed. On 21 October 2026, the image-only update
passed live page, asset, health and cache checks. All five course responses kept
their verified values. Desktop/mobile checks covered all 61 dots, keyboard focus
and pace switching; the final Terraform plan reported no changes. See the
[deployment summary](../infra/gcp/api/README.md#current-deployment).

An unknown course returns `404`. A full-field course with no rows returns an empty
`editions` list. A missing GNR sample or Berlin edition, warehouse timeout or
invalid mart row returns `503` without exposing internal details.

Install and run locally with Application Default Credentials that can query the
selected mart (table or view) and any view dependencies:

```bash
python -m pip install -e '.[bigquery,api]'
uvicorn runwx.api.app:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/api/courses/lydd-half/comparison
```

Open `http://127.0.0.1:8000/` to use the local page. The
[separate Terraform root](../infra/gcp/api/README.md) owns the public Cloud Run
service, its immutable image reference and its dedicated runtime identity. The
corrected image and `/health` probes were deployed on 22 September 2026. Health,
page, assets and both course endpoints returned `200`; an unknown course returned
`404`. All returned values matched the saved results: five Lydd editions with
1,197 finishers and three Folkestone editions with 1,215 finishers. The
[deployment record](evidence/public-api-validation.json) includes the image digest
and checks. Terraform reported no remaining changes after the update.

The [monitoring configuration](../infra/gcp/monitoring/README.md) manages a small
API dashboard and a `/health` uptime alert, deployed on 14 October 2026. It checks
service availability without recurring BigQuery queries; analytical correctness
still comes from the existing reconciliation checks. A controlled test verified
incident opening, recovery and cleanup on 14 October; the recipient confirmed both
emails on 15 October. See the [test and troubleshooting guide](../infra/gcp/monitoring/README.md#verified-alert-test).

## API container

`Dockerfile.api` packages the same FastAPI application and page as a dedicated
non-root image. It does not reuse or change the validation/export job image.

```bash
docker build -f Dockerfile.api --build-arg VCS_REF="$(git rev-parse HEAD)" \
  -t runwx-api:local .

docker run --rm --name runwx-api-local --read-only -p 8080:8080 \
  runwx-api:local
```

Open `http://127.0.0.1:8080/`. `/health` checks only that the HTTP process is ready;
it deliberately does not query BigQuery. A successful comparison response is
publicly cacheable for five minutes, the packaged assets for one hour, and the page
itself is revalidated. The page uses content-hashed asset URLs, so a new deployment
does not pair its HTML with an older cached script. Query submission uses a
10-second RPC timeout and result
waiting uses a 30-second timeout; client retries can extend the total request time.

The image defaults to one Uvicorn worker on port 8080, runs as numeric user 10001 and
supports a read-only root filesystem. Each revision is configured for zero minimum
instances, one maximum instance, concurrency 8, a 60-second request timeout and HTTP
startup/liveness probes against `/health`.

The dedicated runtime identity can create BigQuery query jobs and read only the
named tables and views in the deployed comparison dependency chains, including
the GNR summary table and comparison view. The identity has no
dataset-wide data role, storage role or service-account key. The service uses an
immutable `runwx-api@sha256:...` image.

`requirements/api-container.lock` and `requirements/api-build.lock` are separate
from the report and dbt locks because the serving image additionally needs FastAPI,
Uvicorn and BigQuery. Refresh them only in a disposable Python 3.12 Linux environment,
then rebuild the image, run `pip check` and repeat the offline container smoke check.
Exact version pins improve repeatability, while the immutable registry digest remains
the deployment identity.

The offline smoke check starts the real Uvicorn entrypoint and verifies `/health`,
both pages and the packaged assets with container networking disabled. It cannot call
a configured comparison mart because the offline container deliberately has neither
Application Default Credentials nor BigQuery access. Repository tests cover those
success and failure cases. The GNR deployment check called its three then-public
course endpoints and reconciled them with saved results. The later Battersea
deployment added the fourth course; the chart-date correction is also live.

On 23 September 2026, the existing Cloud Run service received an immutable image
with `/how-it-works`. The saved Terraform plan changed only the image. The live page,
health route, stylesheet and all four comparison endpoints returned `200`; the
edition and result counts matched their saved expectations. A fresh Terraform plan
was no-op. See the [deployment check](evidence/pipeline-explainer-api-validation.json).
