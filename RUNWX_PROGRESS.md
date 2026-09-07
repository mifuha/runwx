# runwx progress

Updated: 7 September 2026. Active plan: `RUNWX_PLAN_AND_CODEX_GUIDELINES.md`.

- Checkout: `/home/mihaf/code/runwx`; branch `codex/course-id-validation`, based
  on `b98ec22` (the committed and pushed Eventrac row-outcome work). Implementation
  is complete; Miha authorised committing and pushing the course-ID task on
  7 September. Git history records the delivery state.
- Completed Slice A tasks: reconciled Eventrac row outcomes in `b98ec22`, followed
  by the explicit-course-ID normalization guard in this working tree. Existing
  row-outcome, alias, and route-override behaviour is preserved.
- Decision: a supplied nonblank course ID must produce a nonempty ASCII slug.
  Reject an empty normalized ID with `ValueError`; do not infer an event-name
  alias to replace an invalid explicit override. Missing or whitespace-only IDs
  retain the existing curated name/distance lookup. This applies at normalization
  and input-to-domain conversion, using the same public function signatures.
- Evidence: new rejection regressions initially failed: 7 failed, 15 deselected
  using `.venv/bin/python -m pytest -q tests/test_course_normalization.py
  -k 'normalizes_to_empty or event_conversion_rejects' --tb=short`.
  Final focused command: `.venv/bin/python -m pytest -q
  tests/test_course_normalization.py tests/test_race_ingestion.py
  tests/test_eventrac_html.py tests/test_race_compare.py`: 31 passed in 1.77s.
  Final full `.venv/bin/python -m pytest -q`: 109 passed in 1.23s.
  `git diff --check` passed. Tests use local inputs and no credentials.
- Checks not run for this task: separate lint/type/build checks, the standalone
  demo, GitHub CI, live provider calls, containers, dbt, or GCP integration.
- Learning objective: validate after normalization can remove information, and
  distinguish absent input from an invalid explicit override. Miha correctly
  predicted that `---Lydd---` survives normalization; clarified that both leading
  and trailing hyphens are stripped and letters are lowercased. Independent code
  practice remains pending.
- Next task: fix the requested weather date range when a run's midpoint or
  permitted weather-matching window crosses midnight. The minimal offline
  report/snapshot contract remains the following unfinished Slice A task.
- Cloud milestones: Slices B-E pending and unexecuted. No merge, cloud-resource
  change, or destructive operation is included in this task's delivery scope.
