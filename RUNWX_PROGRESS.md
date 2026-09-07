# runwx progress

Updated: 7 September 2026. Active plan: `RUNWX_PLAN_AND_CODEX_GUIDELINES.md`.

- Checkout: `/home/mihaf/code/runwx`; branch `codex/weather-midnight-coverage`,
  based on the committed and pushed course-ID fix `7cfc54e`. The weather task is
  implemented and authorised for commit/push. Earlier Eventrac row outcomes are in
  `b98ec22`. These feature branches have not been merged by this session.
- Completed Slice A input boundaries: Eventrac row outcomes, empty normalized
  explicit course IDs, and weather-request coverage across midnight. The offline
  report/snapshot contract is still pending, so Slice A is not yet complete.
- Decision: reuse `run_anchor_time`, convert each midpoint to UTC, and request
  dates covering earliest midpoint minus `max_gap` through latest midpoint plus
  `max_gap`. This supports previous/next-day observations and batches with
  different durations. Matching still determines eligibility and records missing
  or too-distant observations as skips. A negative gap fails before any fetch.
- Evidence: `.venv/bin/python -m pytest -q tests/test_weather_date_coverage.py
  --tb=short` initially produced 10 failures and 1 pass.
  Focused command: `.venv/bin/python -m pytest -q tests/test_weather_date_coverage.py
  tests/test_pipeline_open_meteo.py tests/test_align.py tests/test_race_pipeline.py
  tests/test_eventrac_race_analysis.py`: 21 passed in 0.54s.
  Full `.venv/bin/python -m pytest -q`: 120 passed in 1.07s.
  Whitespace review preserves the existing CRLF files and treats CR at end of
  line as a line ending. Tests use a date-filtered fake and no live requests.
- Checks not run: separate lint/type/build checks, standalone demos, GitHub CI,
  live provider calls, container execution, dbt, or GCP integration. No new DST
  transition semantics were introduced; the existing midpoint helper is reused.
- Learning objective: the fetch window must cover the observations allowed by
  the downstream matching rule. Miha explained that both dates cover the whole
  window before choosing the nearest eligible observation. Independent code
  practice is pending. Prior practice: Miha correctly predicted that
  `---Lydd---` survives course-ID normalization.
- Next task: produce a minimal reproducible offline race/quality report from
  saved race and weather inputs, with source hashes and quality/coverage totals.
- Cloud milestones: Slices B-E pending and unexecuted. The course-ID task was
  committed and pushed as authorised; Miha authorised committing and pushing only
  this weather fix, with the offline report kept as a separate change. Git history
  records delivery; no merge or cloud/destructive operation is authorised.
