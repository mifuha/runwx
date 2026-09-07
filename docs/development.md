# Development reference

Start with the [README quickstart](../README.md#quickstart). Commands below assume
the repository root and an activated virtual environment.

## CSV and SQLite workflow

The activity workflow loads runs and weather, matches them by time, and can save
both matches and skipped runs in SQLite. It remains available alongside the race report.

```bash
python -m runwx run
python -m runwx run --csv
python -m runwx run --csv --db runwx.db
python -m runwx query --db runwx.db --limit 10
```

The first command uses built-in demo data. `--csv` uses the sample CSV files under
`data/`; `--data-dir` selects another directory containing `sample_runs.csv` and
`sample_weather.csv`. The `--db` command creates or updates the local SQLite file.

The CSV adapters also accept caller-supplied run and weather filenames. They
validate rows and convert them to domain objects before the pipeline runs.

See [CSV adapters](../src/runwx/adapters/csv) and
[SQLite adapters](../src/runwx/adapters/sqlite) for the implementation.

## Domain models

- `Run(started_at, duration_s, distance_m)` describes a running activity.
- `WeatherObs(observed_at, temp_c, wind_mps, precipitation_mm, humidity_pct)`
  describes a weather observation.
- `RunWithWeather(run, weather)` holds a matched pair.

These domain dataclasses are frozen. Timestamps must be timezone-aware;
duration and distance must be positive; wind speed and precipitation cannot be
negative. Input schemas validate external data before conversion.

The pipeline loops through runs, aligns weather, attaches valid matches and
records skipped runs with reasons. See the [matching rules](race-report.md#time-matching)
and [domain code](../src/runwx/domain).

## Package structure and API

The package uses these layers:

| Module | Responsibility |
| --- | --- |
| `runwx.domain` | Domain types and core logic |
| `runwx.services` | Use-case flows built on domain logic |
| `runwx.adapters` | CSV, SQLite, API and other external I/O |
| `runwx.main` / `runwx.__main__` | CLI wiring for `python -m runwx` |

`python -m runwx` is the stable CLI entrypoint. Internal code should import from
`runwx.domain.*`, `runwx.services.*` and `runwx.adapters.*`.

Top-level `runwx.*` compatibility aliases remain so older imports continue to work.
They are compatibility paths, not the main API for new internal code.

## Contributing

Put business rules and entities in `runwx.domain`, use-case flows in
`runwx.services`, and persistence/integrations in `runwx.adapters`. Keep
`runwx.main` focused on CLI wiring and use the canonical imports above.

The [README tests section](../README.md#tests) gives the test commands. Keep ordinary
tests deterministic and independent of credentials or live providers. The
[report tests](../tests/test_offline_report.py) cover repeated output, source hashes,
changed settings, malformed result rows and missing weather while blocking network access.

## Project guidance

- [Active implementation plan and learning agreement](../RUNWX_PLAN_AND_CODEX_GUIDELINES.md)
- [Progress and recorded checks](../RUNWX_PROGRESS.md)
- [Repository instructions](../AGENTS.md)

The active plan supersedes conflicting strategy in older planning notes.
