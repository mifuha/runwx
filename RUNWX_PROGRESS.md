# runwx progress

Updated: 7 September 2026. Active plan: `RUNWX_PLAN_AND_CODEX_GUIDELINES.md`.

- Checkout: `/home/mihaf/code/runwx`; branch `codex/offline-race-report` based on
  `0f04828`. The midnight-weather fix was reviewed, committed and pushed on
  `codex/weather-midnight-coverage`, including only its code, tests and related
  README/progress notes. No report work was included. Earlier fixes: `7cfc54e`
  (course ID), `b98ec22` (Eventrac row outcomes). No branches were merged here.
- Slice A: the three input boundaries and the minimal offline report are
  implemented. Miha authorised finalising, committing and pushing the report as
  a separate change, including the top-N demonstration and a plainer README.
  Git history records delivery. No merge is included in this authorisation.
- Delivered: `python -m runwx report` reads one saved Eventrac HTML and one weather
  CSV, reuses existing parsing/analysis components, and prints deterministic JSON.
  The saved Lydd demo uses clearly labelled synthetic weather, not historical data.
- Contract: summaries cover accepted finishers; weather coverage uses accepted
  results as its denominator. Empty populations have null summaries; zero accepted
  results have null coverage. Rejected-row and unmatched-weather reasons stay
  separate. Each file's exact bytes are read once for both parsing and SHA-256.
  Settings and limitations are included. No new framework, provider calls or DB.
- Acceptance evidence: the initial report tests failed because the command did
  not exist (10 failed in 2.47s). The report/CSV/CLI checks then passed (17 tests).
  Final demonstration command: `.venv/bin/python -m pytest -q
  tests/test_offline_report.py::test_changed_top_n_changes_summary_without_changing_sources_or_coverage`:
  1 passed in 0.47s. Full `.venv/bin/python -m pytest -q`: 133 passed in 1.28s.
- Offline proof: all report tests fail on HTTP/socket access. The final documented
  Lydd CLI command also succeeded twice under `bwrap --unshare-net`; output was
  byte-identical. Initial nested sandbox setup was restricted; the same read-only
  check succeeded with approval to create the isolated namespace.
- Actual demo: 189 accepted, 0 skipped, 0 invalid; 188 matched and 1 unmatched.
  Best/median/top-20-median finish times: 4267/6954/4953.5 seconds.
  Generated report: `/tmp/runwx-offline-report-0f04828/lydd-report.json`.
- Limits: synthetic weather has no verified location/provider/capture metadata;
  event completeness, individual starts and chip/gun timing are unverified.
  Code/dependency versions are not recorded in the report; replay currently
  assumes the same checkout/environment. Source hashes establish content identity.
- Checks not run: separate lint/type/build checks, Docker, GitHub CI, live
  providers, dbt or GCP integration. Final diff reviewed; whitespace checked with
  existing CRLF line endings recognised. No cloud or destructive operations.
- Learning: Miha explained why date requests cover the entire matching window.
  This task demonstrates separating row quality, race statistics and coverage,
  and distinguishing byte identity from unchanged analytical output.
- Practice: at Miha's request, Codex demonstrated the top-N test. It runs the
  same files with top_n 1 and 2: the median changes from 3600 to 5400 seconds,
  while source hashes and weather coverage stay fixed. This was a demonstration,
  not an independent exercise. README wording now describes the race report
  plainly and keeps the synthetic-weather limitation visible.
- Next bounded task: containerise this same offline command locally and compare
  its output. Cloud Slices B-E remain unexecuted; deployment needs separate scope.
