# runwx progress

Updated: 8 September 2026. Active plan: `RUNWX_PLAN_AND_CODEX_GUIDELINES.md`.

- Checkout: `/home/mihaf/code/runwx`; branch `codex/local-container-report`, based
  on `d31a61a` (reviewed README/reference docs, committed and pushed as authorised).
  Earlier work: `0d3e76f` offline report, `0f04828` midnight weather, `7cfc54e`
  course ID and `b98ec22` row outcomes. No branches were merged here.
- Git checkpoint: `8a67383` packages the local container; `bd46134` adds the
  completed cloud input/output path. Documentation diagrams are kept in a separate
  commit. Miha authorised commit and push on 8 September; no merge authorised.
- Host setup: Miha explicitly chose Docker Engine in Ubuntu. Installed Engine/CLI
  29.8.0, containerd 2.3.4 and Buildx 0.37.0 from Docker's official Ubuntu repository.
  Docker/containerd system services are installed and running. No user group or
  sudo policy changes; Docker commands use administrator access. Images/cache remain
  local. No image publication, cloud resources or destructive cleanup.
- Design: pinned official Python 3.12 slim/bookworm base; install the existing
  package with its current dependency ranges. Run as uid 10001. Include only package
  code/build metadata; mount saved inputs read-only at runtime. The CLI is unchanged.
- Actual build: `docker build --build-arg VCS_REF=<HEAD> -t runwx:offline .` passed.
  Python 3.12.14; image ID:
  `sha256:b341a758fd9b25286130853c742b5a15e64bdeede30e56cef626ac0e247df22b`.
  Revision label: `d31a61acbd43afb2e0c12edec7b0152db1d9b237`.
- Integration checks: local report plus two `docker run --rm --network none
  --read-only --mount <read-only data>` report runs were byte-identical.
  Results: 189 accepted, 0 skipped/invalid, 188 weather matches, 1 unmatched.
  Output SHA-256:
  `632493bcd0b6c6f9f5848865a9f3cb61b61693d66da7b90afaaa5013c9d74913`.
- Image audit passed: uid 10001; only loopback networking; installed package in
  site-packages; all 48 Python files hash-match the checkout. No saved data, .git,
  .venv, .codex, .env, AGENTS.md or src/test.py in the image. The first permission
  review timed out; the permitted retry succeeded. Nothing remains blocked.
- Evidence: `/tmp/runwx-container-check-20260907/` contains local/container/repeat
  JSON, image-inspect.json, and environment.json with package versions/source hashes.
- Limits: the base is pinned, but Python dependencies are resolved from existing
  ranges during each build. This image used some newer dependencies than the local
  environment. Saved-demo agreement is verified; full-suite compatibility inside
  the image is not. Image ID/revision are recorded separately from the report.
  Synthetic-weather, timing and source-uncertainty limitations remain unchanged.
- Checks not run: Python suite (application code unchanged; prior 133 passed),
  full tests inside the image, separate lint checks, GitHub CI, macOS/Windows
  containers, dbt or GCP. Docker build/runtime were checked on Ubuntu 24.04/WSL.
- Learning: an image contains installed code/dependencies; saved data is supplied
  at runtime. Predict whether changing only a mounted CSV requires rebuilding.
  Independent practice for this task is pending; prior top-N test was demonstrated.
- Completed task: first cloud input/output path within Slice B. Added a small GCS
  adapter and entrypoint around the existing report, one SDK dependency, comparison
  command and minimal Terraform. Existing Dockerfile/.dockerignore/container docs
  and README edits remain untouched and separate from this cloud integration diff.
  Git publication was authorised after the deployment and documentation review.
- Local cloud checks: full Python suite **148 passed in 1.79s** on 8 September;
  network-blocked boundary tests use saved synthetic data. The same container was
  tested with fake storage and real SDK signatures, then verified against all 51
  application source files before publication. Details: [first cloud run](docs/first-cloud-run.md).
- Deployment approved on 8 September 2026. Miha confirmed the selected billing
  account is Free Trial, expiring **7 December 2026**. No paid upgrade authorised
  or performed; the $300 credit does not expand this deployment's scope.
- Google Cloud CLI 583.0.0 and Terraform 1.13.5 are installed under `~/.local/bin`.
  Manual browser login and ADC refresh succeeded; no service-account keys created.
- Created `runwx-learning-mifuha` (project number `840088506058`) in the existing
  personal organisation and linked the confirmed GBP billing account. Created the
  approved £3 project-only monthly budget, before credits, at 50/90/100% thresholds.
  Actual identifiers and evidence: `/tmp/runwx-gcp-20260908/`.
- New deployment baseline: `data/sample_race_synthetic.html` plus existing
  `data/sample_lydd_weather_synthetic.csv`; course `runwx-synthetic-half`, 21097 m,
  Europe/London, top-N 20, gap 30 minutes. Completely fabricated race, no names.
  Race SHA-256 `70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182`.
  Counts 5/3/1/1 candidate/accepted/skipped/invalid; weather 2 matched, 1 unmatched.
  Two native reports identical; two fake-storage container reports agree with the
  native baseline. Evidence: `/tmp/runwx-cloud-prep/synthetic/`. Focused tests:
  15 passed in 1.24s; Terraform validate/fmt passed. Full suite not rerun for this
  fixture/config change; previous 148 passed, processing code unchanged.
- First cloud input/output task completed: two private buckets, registry, runtime
  account and job in europe-west1. Uploaded only synthetic race/weather fixtures.
  Executions `runwx-report-tdjvt` and `runwx-report-btttr` both succeeded: **2 of 5**
  permitted executions used. Retrieved both reports; every analytical field,
  input hash and setting matched the local baseline. Only source paths and the
  surrounding execution/storage metadata differ. First output remained unchanged.
- Deployed Linux image digest:
  `sha256:f90bc8ea97497ca377dec4cbc2e4bfb43cfe4484658e602561039782392475d5`.
  Actual execution descriptions match both report envelopes. Job limits verified:
  1 task, parallelism 1, 1 CPU, 512 MiB, 300 seconds, no retries. Runtime has only
  conditional input-read and report-create bucket grants, no project-wide role.
- Actual usage: two successful tasks (27.510/41.499 s start to completion), 9017
  bytes in GCS, registry reported 61.579 MB. Early Monitoring data exposed 60 s;
  do not treat it as a complete billed total. Actual charges remain unverified:
  the desktop browser bridge failed on this WSL workspace path. Use the linked
  Billing Reports page with this project selected. Budget/estimate are not caps.
- Both Terraform applies succeeded (10 + 1 resources, no changes or destruction);
  final read-only plan reported no changes. Bucket privacy and runtime grants
  inspected. No paid upgrade or trial restriction encountered. No destructive
  cleanup performed; cleanup still needs separate approval.
  Existing container files and README edits remain untouched by this cloud work.
- Following milestone, not implemented: expose useful result rows in BigQuery and
  tested dbt models. Question: how did recorded finish times and average paces
  differ across suitable editions of the same course, and what weather context
  accompanied them? Start with median and top-N average pace for the existing
  edition, explicit units/settings/result counts/weather coverage. Reuse existing
  analysis/comparison code. A second snapshot needs course, distance, timing and
  source comparability checks before historical comparison. Synthetic demos stay
  separate from real evidence; no prediction, weather-adjusted claims or splits.
- Learning for cloud I/O: runtime identity controls access; temporary compute
  produces persistent objects. Predict the duplicate-output test's result when
  only its second execution name changes, then adapt it locally. Independent
  practice pending. Slice A and the first Slice B cloud I/O path are delivered;
  BigQuery/dbt and later slices remain unimplemented.
- Documentation: one compact Mermaid flow in README and a neutral planned
  warehouse flow in `docs/architecture.md`. README milestone now reflects the
  completed cloud proof. Both five-node diagrams parsed and rendered locally with
  Mermaid 11.12.0 in headless Chrome; visually checked at README width. GitHub's
  live preview was not tested. Thirteen relative links and whitespace checks
  passed. No Python tests rerun for this documentation-only task. Commit and push
  were authorised afterwards; next session starts with the BigQuery/dbt task above.
