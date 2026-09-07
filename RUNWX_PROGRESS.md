# runwx progress

Updated: 7 September 2026. Active plan: `RUNWX_PLAN_AND_CODEX_GUIDELINES.md`.

- Checkout: `/home/mihaf/code/runwx`; branch `codex/eventrac-row-outcomes`;
  base commit `f28db7a`. Implementation complete; Miha authorised committing and
  pushing this task on 7 September. Git history records the delivery state.
- Completed: Slice A's Eventrac row-outcome boundary. Short/reordered rows,
  invalid values, and former silent skips receive explicit outcomes; valid
  neighbours survive. Required-header failures remain page failures. Outcome
  totals reconcile with candidate rows counted from the input.
- Decision: candidates are source-table rows with direct data cells, excluding
  headers, footers, and nested-table rows. Validate the full row width first;
  blank time is an expected skip, while bad place/time values are invalid.
  All-rejected pages return a quality report; zero-candidate pages fail clearly.
  Keep distinct equal-time/equal-place finishers. DNF/DNS semantics are deferred.
- Evidence: baseline `.venv/bin/python -m pytest -q`: 83 passed in 2.03s.
  New regressions before implementation: 13 failed, 2 passed.
  Final focused command: `.venv/bin/python -m pytest -q
  tests/test_eventrac_row_outcomes.py tests/test_eventrac_html.py
  tests/test_eventrac_race_analysis.py`: 23 passed in 0.83s.
  Final full `.venv/bin/python -m pytest -q`: 100 passed in 1.10s.
  `.venv/bin/python scripts/demo_eventrac_parse.py`: 189 candidates,
  189 accepted, 0 skipped, 0 invalid. Tests and demo use local inputs.
- Checks not run: standalone lint/type/build checks, GitHub CI, live provider
  calls, container execution, dbt, or GCP integration. No cloud resources changed.
- Learning objective: distinguish source-row rejection from page-schema failure
  and programming errors; derive reconciliation expectations from the input.
  Miha identified separate source rows as the reason to preserve equal-valued
  results. Clarified that equal time/place does not prove duplicate identity.
  Independent implementation practice has not yet been demonstrated.
- Count prediction pending: accepted/skipped/invalid counts for four rows with
  valid time, blank time, `00:61:00`, and the same valid time/place as row 1.
- Next task: fix the explicit-course-ID boundary where a nonblank ID such as
  `---` normalizes to an empty string. Midnight weather coverage and the minimal
  offline report/snapshot contract remain unfinished Slice A tasks.
- Cloud milestones: Slices B-E pending and unexecuted. No merge, cloud deployment,
  or resource cleanup is included in this task's delivery scope.
