# Read-only comparison API

The [live comparison](https://runwx-api-f6n35ol7sa-ew.a.run.app/) reads the existing
dbt comparison marts through this API. It does not parse race data, align weather
or calculate new statistics.

The service root (`/`) serves the small comparison page. It uses the endpoint below
to populate course, pace and weather selectors, two aligned accessible SVG trend
plots and a compact edition table. Pace stays visible beside the selected weather
measure. The HTML, CSS and JavaScript are packaged with the API; the page has no
external frontend or chart dependency.

```text
GET /api/courses/{course_slug}/comparison
```

The reviewed course slugs in this code are `lydd-half`, `folkestone-half` and
`great-north-run`. Each maps to one explicit BigQuery comparison view. The URL
cannot select a table or submit SQL. The query selects fixed public columns, binds
the expected course ID as a parameter, reads at most 50 editions and refuses to
bill more than 64 MiB. The first deployed queries required 50 MiB for Lydd and
30 MiB for Folkestone because
of BigQuery's minimum billing per referenced table. The previous 10 MiB cap rejected
both; 64 MiB leaves a small margin above the current requirement.

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

An unknown course returns `404`. A full-field course with no rows returns an empty
`editions` list. A missing GNR sample, warehouse timeout or invalid mart row returns
`503` without exposing internal details.

Install and run locally with Application Default Credentials that can query the
selected view and its dependencies:

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
the page and both packaged assets with container networking disabled. It cannot call
a configured comparison mart because the offline container deliberately has neither
Application Default Credentials nor BigQuery access. Repository tests cover those
success and failure cases. The latest deployment check called all three public
course endpoints and reconciled the returned analytical values with saved results.
