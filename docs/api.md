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
at this stage. A container, runtime identity, Terraform and public deployment are
separate work.
