# Read-only comparison API

The first MVP endpoint reads the existing dbt comparison marts. It does not parse
race data, align weather or calculate new statistics.

The service root (`/`) serves the small comparison page. It uses the endpoint below
to populate course, pace and weather selectors, two aligned accessible SVG trend
plots and a compact edition table. Pace stays visible beside the selected weather
measure. The HTML, CSS and JavaScript are packaged with the API; the page has no
external frontend or chart dependency.

```text
GET /api/courses/{course_slug}/comparison
```

The current reviewed course slugs are `lydd-half` and `folkestone-half`. Each maps
to one explicit BigQuery comparison view. The URL cannot select a table or submit
SQL. The query selects the fixed public columns, binds the expected course ID as a
parameter, reads at most 50 editions and refuses to bill more than 10 MiB.

The response contains the course and baseline identity, followed by editions in
date order. Each edition includes finishers; median, mean, p25–p75 and fastest-N
pace; matched-weather coverage and medians; its compatibility status; and its
pace/speed change from the stated baseline. Pace values are seconds per kilometre.

An unknown course returns `404`. A configured course with no rows returns an empty
`editions` list. A warehouse timeout or invalid mart row returns `503` without
exposing internal details.

Install and run locally with Application Default Credentials that can query the two
views:

```bash
python -m pip install -e '.[bigquery,api]'
uvicorn runwx.api.app:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/api/courses/lydd-half/comparison
```

Open `http://127.0.0.1:8000/` to use the local page. The page and API are local only
at this stage. The dedicated container below is also local; runtime identity,
Terraform and public deployment remain separate work.

## API container

`Dockerfile.api` packages the same FastAPI application and page as a dedicated
non-root image. It does not reuse or change the validation/export job image.

```bash
docker build -f Dockerfile.api --build-arg VCS_REF="$(git rev-parse HEAD)" \
  -t runwx-api:local .

docker run --rm --name runwx-api-local --read-only -p 8080:8080 \
  runwx-api:local
```

Open `http://127.0.0.1:8080/`. `/healthz` checks only that the HTTP process is ready;
it deliberately does not query BigQuery. A successful comparison response is
publicly cacheable for five minutes, the packaged assets for one hour, and the page
itself is revalidated. Query submission and result waits remain bounded at 10 and 30
seconds respectively.

The image defaults to one Uvicorn worker on port 8080, runs as numeric user 10001 and
supports a read-only root filesystem. The next infrastructure review should start
with zero minimum instances, one maximum instance, concurrency 8 and a 60-second
request timeout. These are proposed demo limits, not deployed settings. The runtime
identity and exact BigQuery permissions still need a reviewed Terraform plan; no
service-account key belongs in this image.

`requirements/api-container.lock` is separate from the report and dbt locks because
the serving image additionally needs FastAPI, Uvicorn and BigQuery. Refresh it only
in a disposable Python 3.12 Linux environment, then rebuild the image, run `pip
check` and repeat the offline container smoke check. Exact version pins improve
repeatability, while the immutable registry digest remains the deployment identity.

The offline smoke check starts the real Uvicorn entrypoint and verifies `/healthz`,
the page and both packaged assets with container networking disabled. It cannot call
a configured comparison mart because the offline container deliberately has neither
Application Default Credentials nor BigQuery access. Repository tests cover those
success and failure contracts; the first deployed validation must still request both
configured courses through the service identity and reconcile their returned values.
