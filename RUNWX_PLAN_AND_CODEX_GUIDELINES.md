# runwx: delivery plan and Codex working agreement

**Version 2 · 7 September 2026 · Prepared for Miha**  
**Purpose:** one active implementation plan, combining the research outcome with faster, learning-focused AI-assisted development.

> Keep the useful race report. Build the missing cloud and warehouse evidence. Agree on behaviour once, complete a bounded implementation, then learn from the actual code and tests.

## 1. Direction and status

Continue `runwx`; do not start a replacement project. The product remains **trustworthy, reproducible race comparisons with weather context**. The next investment is the engineering around that output: traceable ingestion, useful warehouse SQL, tested models, real cloud execution and safe recovery.

Miha has approximately three years of commercial Python/data-engineering experience at Infosys/BT, including Python migration, pandas/NumPy, SQL/MySQL, Kafka, Druid, testing, GitLab CI/CD and Docker. Kubernetes exposure was assisted; independent production cloud or Databricks ownership is not established. Target UK Python/data-engineering, data-platform and suitable analytics-engineering roles. Do not treat him as a beginner or inflate his experience.

**Adopted decisions:** GCP; Cloud Storage; Cloud Run Jobs; BigQuery; dbt Core; minimal Terraform; Workflows after the first working cloud path. Airflow is a later, bounded learning extension, not a prerequisite for release. No second cloud or replacement project during this milestone.

This updates the earlier plan, rather than appending another roadmap. It replaces the conditional AWS default, SQL-as-a-late-addition sequence, simultaneous dual-orchestrator scope and repeated per-edit approvals. Retain the earlier correctness, provenance, permission and publication safeguards. The research supports these priorities; the scope and working method below are our synthesis, not measured hiring guarantees. [R1, pp. 1, 5–11; R2, pp. 3–8]

**Repository status is not reverified in this document.** Both reports describe `master` at commit `f28db7a` (4 September 2026). The coding agent must inspect its actual checkout once, preserve newer work and skip completed tasks. Historical test counts are not current test evidence. [R1, p. 5; R2, p. 3]

## 2. Working agreement: faster delivery, deliberate learning

You are Miha's repository-aware coding and learning partner. Own routine implementation; make consequential choices understandable. A task is one coherent, testable change, potentially spanning several files. It is not necessarily one helper function, and it is not an entire milestone.

### The normal loop

**Explain the problem.** Inspect relevant code and tests. Briefly show the current behaviour, why it matters and one main learning objective. Do not re-audit the repository or repeat familiar Python lessons for every task.

**Decide and sketch.** Recommend one design and give two or three acceptance examples. Debate an alternative only when it changes correctness, cost, public behaviour or substantial complexity. Use a short data-flow sketch when useful. A clear implementation request already authorises its routine local work; do not ask for the same approval again.

**Implement and test.** Complete the bounded change autonomously. For a known bug, prefer a failing regression first. Derive expected results from the agreed input/behaviour, not from the generated implementation. Run focused tests, fix your own implementation mistakes, then run appropriate broader checks. Do not pause between ordinary edits, fixtures and test runs.

**Review and explain.** Review the actual diff for correctness and scope. Show the essential snippet, its relevant test and a brief explanation of why the behaviour holds. Use a diagram for relationships or failure flow, not for decoration. Report test commands and actual outcomes; separate verified results, skipped checks and assumptions.

**Apply the idea.** Give Miha one small exercise: predict an edge case, alter a query, write a related test or explain a failure. Offer a hint or a direct explanation when needed. Do not turn every function into a quiz or automatically block delivery while waiting for an exercise answer. Record “implemented” separately from “practised independently”.

These are phases, **not five approval gates**. The agent may carry out a clear task in one implementation pass followed by one focused review. If an agreed behaviour proves impossible or unsafe, explain the new evidence and ask one targeted question.

### Approval boundaries

Proceed within the task with local inspection, relevant edits, conventional helpers, deterministic tests and small supporting documentation. Preserve existing architecture unless the task requires otherwise.

Ask before an unresolved identity/correction policy, an incompatible interface change, a major dependency/architecture change, destructive migration, private-data upload or expansion beyond the agreed task. Include your recommendation with the question.

Do not commit, push, merge, rewrite history, delete branches or change paid/cloud resources without explicit authorisation. Cloud authorisation may cover a bounded deployment/test window; do not reconfirm each operation already inside it. Stop before exceeding its account, resource, data or spending scope. Never change agent permission settings to bypass a restriction.

Preserve unrelated tracked changes and untracked files. Do not clean up personal notes or `.codex` configuration. A dirty checkout is not a reason to reset it. Follow the environment's branch/worktree rules; resolve overlapping edits before touching them.

### Eliminate duplicate work

Use the coding agent's checkout, diff and test outputs as the source of truth for implementation. No mandatory ChatGPT → Codex → ChatGPT approval round-trip. Reserve additional independent review for high-risk publication/IAM changes or a release, not routine helpers.

Record consequential decisions once, briefly. Reopen them only for changed requirements, contradictory implementation evidence, security/cost risk or sustained interview feedback. A different model suggesting another reasonable tool is not new evidence.

Keep one active task and one short progress record. Check the current diff for each task, but do not repeat a whole-repository audit or unchanged test run without a reason. Consult official documentation for the immediate API/version question; do not restart broad market research.

## 3. The system to build

The first release uses **one race-results provider, saved snapshots and weather inputs**. Multiple editions do not require multiple providers. A second provider is optional, not a release gate.

```text
Saved, permitted race + weather snapshots
                  |
            Cloud Storage
                  |
     Python ingestion on Cloud Run Jobs
                  |
       BigQuery source/staging tables
                  |
     dbt Core models + reconciliation tests
                  |
      Validated, selected report revision
                  |
       Small race/quality report
```

Start with explicit manual invocation. Later, Workflows coordinates ingestion, modelling/validation and publication. Workflows can execute Cloud Run Jobs; that does not require adopting every service in Google's example tutorial. Scheduler is unnecessary until a real recurring input or monitoring requirement exists. [T1]

Keep business rules in the existing Python domain/services/adapters. Use Python for parsing, validation and weather alignment; SQL/dbt for warehouse relationships, reconciliation and analytical aggregation. Do not maintain two independent implementations of every calculation. Test a few shared metrics against independently specified expected results.

Run dbt in a containerised execution step, not only on the laptop. One repository and initially one image with separate entrypoints are acceptable if dependencies remain manageable. These are execution stages, not a reason to create microservices.

Use BigQuery native tables and a few readable models. Preserve the existing SQLite activity workflow, but do not build a parallel SQLite race-revision platform first. Add no new local database merely to imitate the warehouse. BigQuery-specific SQL needs actual BigQuery validation; a local substitute does not prove dialect compatibility.

**Output:** one compact report with accepted/skipped/invalid counts, finish-time summaries, weather coverage and explicit limitations. Compare two editions only when route, distance, timing basis and source suitability are established. Weather context is not a causal weather-adjusted performance score.

## 4. Minimum data contracts

These are implementation defaults to validate against the source, not a request for a generic framework. Settle the relevant contract when its task starts; do not redesign everything in advance.

**Row outcomes.** Define a candidate result row, then give each one exactly one terminal outcome: accepted, expected skip or invalid/error, with a reason and source locator where needed. For completed parsing, reconcile the total to those outcomes. Keep page-level/schema failure distinct from row-level rejection. Do not turn programmer exceptions into ordinary skipped records.

**Identity.** Keep course identity separate from a particular event edition. Snapshot identity includes source identity and a content hash. Within a snapshot, use a stable row locator or verified source key: equal finish times, places or names must not collapse different finishers. Store original local-time text, declared timezone, UTC interpretation, source reference and parser version where applicable.

**Corrections.** Default to whole-event snapshot revisions for inputs verified to represent a complete result set. Select an explicit successful revision; do not invent cross-revision athlete identity from names, row numbers or finishing places. A stable upstream result identifier can support row-level change explanations when its semantics are verified. Without one, demonstrate snapshot replacement and aggregate differences honestly. Partial/delta inputs require a separate policy before acceptance.

**Analysis and attempt.** A logical analysis identifies the exact race/weather snapshots, interpretation/configuration and code version. Each execution attempt has a separate ID and status. A retry may create another attempt, but must not duplicate logical results in published queries. Record image/code identity, not only an unversioned image tag.

**Replay versus promotion.** Replaying an old revision must not silently replace the selected current revision because it finished later. Make promotion explicit. Keep the old source and prior successful output traceable. “Reproducible” refers to stable domain/analytical output; timestamps and attempt IDs may legitimately differ.

**Publication.** Build candidate outputs away from the selected report. Advance the publication reference only after required jobs, data checks and report outputs succeed. A failed candidate must leave the previous successful report intact. Choose and document one small BigQuery-compatible publication mechanism; test the boundary rather than assuming a manifest hides partial tables.

`dbt build` executes resources and tests, and a failing test can skip downstream work. It is not our cross-service publication protocol. Build/test candidates before exposing them. BigQuery primary/foreign keys are not enforced; explicit uniqueness, relationship and cardinality checks remain necessary. [T2, T3]

**Concurrency limit.** Start with one controlled submission/publication path and serialized operation. Demonstrate sequential duplicate-safe retries; do not claim concurrent exactly-once delivery or distributed locking. Add overlapping-run guarantees only as a separately tested requirement.

## 5. Delivery sequence and stop points

Use approximately 10–15 hours/week and six to eight weeks as planning assumptions, not commitments. Learn from actual effort after the first two slices. Cut optional scope or extend the calendar rather than calling untested work finished. The reports' estimates are not promises.

### Slice A — Protect inputs and produce the offline contract

Inspect only the known boundaries: Eventrac short/reordered rows and silent skips; explicit course IDs normalising to empty; weather date coverage across midnight. Fix only still-present blockers with deterministic regressions. Then connect one saved event/weather input to a minimal report plus source metadata and quality totals. Reuse existing tests and schemas.

**Done:** valid records survive malformed neighbouring rows; candidate counts reconcile; uncertain weather coverage is visible; the offline report is reproducible. **Learning:** validation boundaries and output contracts. Do not let exhaustive parser hardening postpone Slice B.

### Slice B — First deployed end-to-end path

Containerise the existing path. Add minimal Terraform for authorised GCP resources: storage, registry, runtime identity, Cloud Run Job and warehouse datasets. Load one controlled snapshot into BigQuery and produce the first dbt staging/canonical model with tests. Manual invocation is sufficient here; no orchestrator or second source yet.

**Done:** saved input → actual cloud execution → warehouse model → small report, with job/image identifiers and local/cloud agreement. At least the first warehouse model executes against BigQuery, not just compiles. **Learning:** container execution, runtime permissions and warehouse grain. This is already useful portfolio evidence.

### Slice C — Make modelling and reliability substantial

Add a small model set, shaped by the queries rather than a target model count: source-row staging, event/course relationships, accepted result revisions, selected successful results and one event-quality/comparison mart. Explain what one row means in each. Avoid a giant star schema or elaborate incremental logic for tiny inputs.

Implement explicit revision selection and tested publication. Demonstrate repeat ingestion, a clearly labelled corrected snapshot and replay of an older revision. Test row counts, uniqueness, join cardinality, accepted/skipped reconciliation and weather denominators. Choose a few real SQL questions: “What was excluded?”, “What changed between selected revisions?” and “Which comparable editions have adequate coverage?”

**Done:** repeated input leaves published totals unchanged; a validated correction changes the intended output; replay does not roll back the current selection; failed validation publishes nothing new. **Learning:** keys, joins, revisions and useful warehouse SQL.

### Slice D — Orchestrate recovery once

Wrap the working execution stages in one Workflows definition. Pass immutable URIs/IDs and configuration, not large records. Wait for actual completion; distinguish successful submission from successful processing and publication. Bound retries across application/runtime/orchestrator layers so failures do not cause multiplied retry storms. Deterministic bad input should not be retried indefinitely.

Inject a transient failure and a failure after candidate output exists but before publication. Recover using the same input/configuration identity. Provide explicit snapshot-based historical reprocessing, not an invented daily race-arrival schedule.

**Done:** cloud coordination works without the laptop controlling stages; recovery preserves correct selected output; failed attempts have useful logs and status. **Learning:** dependency state, retry safety and process boundaries.

### Slice E — Release the evidence

Finish package/image smoke checks, scoped CI, cloud test instructions, deployment/cleanup notes, short decision records and a two-to-three-minute demo. Produce one small report, not a separate frontend application. Put measured results and limitations near the top of the README.

**Done:** a reviewer can run the offline demo, inspect evidence of the real cloud path, see correction/recovery behaviour and understand the design. Record actual input sizes, timings and cost observations with their measurement conditions. Do not invent uptime, scale or business impact.

**Scope pressure:** remove a second provider, decorative UI, incremental optimisation or extra orchestration first. Preserve the first real cloud run, meaningful SQL, failure evidence and Miha's understanding. Continue applications and interview practice throughout; the project must not become a waiting room for job searching. [R2, pp. 6–8]

## 6. Verification without repeated checking

Run the existing baseline once when entering an unfamiliar checkout, or after material unrelated changes. Use its actual environment and configured commands. Run focused checks during implementation; run the full Python suite once at completion of Python-changing tasks while it remains practical. For documentation-only changes, use appropriate checks rather than mechanically rerunning everything.

Keep ordinary Python CI deterministic and credential-free. Separate optional live/provider tests and authenticated cloud integration jobs. For warehouse work, distinguish parsing/compilation from executed dbt tests. Use a disposable, authorised test dataset; report any integration checks not run.

Minimum release evidence:

| Scenario | Required visible outcome |
|---|---|
| Missing/malformed row; changed required schema | Explicit outcome or clear run failure; valid records and counts handled by policy. |
| Identical snapshot processed twice | No duplicate logical rows or changed published totals. |
| Corrected snapshot and old-snapshot replay | Correction traceable; old replay does not become current accidentally. |
| Equal-time finishers; one-to-many join risk | Distinct results preserved; joins do not inflate aggregates. |
| Missing weather; midnight boundary | Correct requested interval and honest coverage/status, not fabricated observations. |
| Stage fails after writing candidate data | Previous selected output remains valid; retry recovers safely. |

Review assertions as well as implementation. Do not weaken a test or change expected data merely to get green results. Compare the complete relevant diff, but teach from the smallest snippet that exposes the important idea. Tests support confidence; they do not establish untested production guarantees.

## 7. Security, costs and source data

Before cloud changes, establish the authorised project, region, permitted data, spending envelope and cleanup boundaries. Batch these into one necessary setup decision, not a questionnaire during local work. Verify current region-specific pricing and API/provider versions at implementation time. No monthly cost or free-tier eligibility is guaranteed by this plan.

Use narrowly scoped runtime permissions and separate deployment identity. Prefer keyless supported authentication; never commit credentials, raw private records or secret-bearing Terraform state. Do not publish cloud datasets or raw race pages simply to provide a demo. Use synthetic public examples unless reuse/publication rights are established.

Keep compute, retries, query scans, logging and retained artefacts bounded. Budget alerts are notifications, not hard spending caps. Document all resources that can remain billable after execution stops. Destructive cleanup needs explicit scope and approval, not a blanket project-delete command. [T4]

## 8. Learning and interview ownership

Concentrate attention on concepts Miha needs to own: grain and identifiers; SQL joins/windowing; correction versus replay; tests derived from invariants; orchestration state; cloud permissions and costs. Let the agent carry more familiar scaffolding.

At the end of a meaningful task, use this compact response structure:

```text
Delivered: the behaviour now implemented.
Evidence: commands and outcomes; checks not run.
Understand: one key snippet + test or small diagram.
Practise: one brief prediction/change for Miha.
Next: one concrete task or one genuine blocker.
```

Once a week, revisit one earlier idea with a small unaided change or explanation. Keep this brief and adapt to energy and interview deadlines. Record mistakes as useful learning evidence, not as a reason to slow every future edit. The agent should not claim Miha has mastered something merely because code passed tests.

Prepare a few honest interview explanations tied to completed work: why this key, why a retry is safe, why a failed candidate cannot become public, why this SQL join preserves counts, and why this workload does not need Spark. Project cloud experience is not years of commercial operations experience.

## 9. Deferred work and decision triggers

After the working release, a bounded local Airflow DAG can invoke the same entrypoints and teach dependencies, retries and parameterised historical reprocessing. Do not copy transformation logic or describe this as Cloud Composer experience. Keep it off the release critical path.

Add a separate Spark/Databricks exercise only when priority interviews repeatedly expose that gap: reuse the schema, label synthetic scale, compare a result against the simpler baseline and inspect an actual execution plan. A notebook port alone does not establish distributed-systems depth.

Do not build Kubernetes, a Kafka cluster, ML/LLM features, CDC infrastructure, multiple clouds, a substantial API/frontend, a generic ingestion framework or a full SQLite revision system for this release. Reconsider accommodation reconciliation only after a specific recurring user problem, authorised exports and someone willing to test it are established. [R1, pp. 5, 10; R2, pp. 4–8]

## 10. Adoption and the first Codex session

Store this file as `RUNWX_PLAN_AND_CODEX_GUIDELINES.md` in the project. Read it explicitly in the launch prompt. For persistent guidance, a short reference in the applicable `AGENTS.md` can point to it; do not duplicate the whole plan across several files. Inspect existing instructions and preserve unrelated rules. Codex supports project guidance through `AGENTS.md`. [T5]

Within user-controlled planning documents, this version supersedes older conflicting strategy and per-edit approval instructions. It does not override higher-priority instructions, security boundaries or a newer explicit user request. Updating a reference is not permission to rewrite agent configuration or silently delete old records.

**First session:** inspect applicable instructions, Git status/HEAD, relevant implementation and the current test setup. Summarise only differences that affect the next action. Do not assume the previously described WSL path or virtual environment exists.

If Slice A blockers remain, complete one coherent input-boundary task. If already fixed, start the minimal report/snapshot contract; if that is complete, take the first unfinished local containerisation task. Explain the scope and acceptance examples briefly, then implement and test without a redundant approval request. Stop for genuinely unresolved semantics or protected operations.

Finish with the compact response from Section 8. Do not implement the entire roadmap in one run. Maintain one short progress record with checkout/branch, completed slice, test evidence, key decision, concept practised and next task. Label unexecuted cloud milestones as pending.

## Basis and technical references

**R1.** *runwx: cloud and career reassessment*, 5 September 2026, supplied PDF. Retained: useful report, narrow input fixes, traceability, safe publication, cloud/SQL learning and operational limits. Replaced: conditional AWS default and old delivery sequence.

**R2.** *Best next portfolio investment for your UK Python/data-engineering job search*, supplied nine-page research report, September 2026 context. Adopted: GCP/dbt, stronger warehouse modelling and correction/replay evidence. Narrowed: second provider, dual orchestration and optimistic release scope. Its vacancy/practitioner findings are prior research, not newly verified hiring availability.

**Working agreement.** Miha's discussion immediately preceding this update: explain why, debate meaningful choices, sketch, implement, test, review and practise; avoid repeated approvals and model-to-model handoffs. Detailed defaults in this document are recommendations implementing that agreement.

**Technical checks accessed 7 September 2026:**

- **T1:** Google Cloud, [Execute a Cloud Run job using Workflows](https://docs.cloud.google.com/workflows/docs/tutorials/execute-cloud-run-jobs). Integration capability only; the tutorial's complete architecture/IAM is not prescribed here.
- **T2:** dbt, [About dbt build](https://docs.getdbt.com/reference/commands/build). Resource execution, tests and downstream skipping.
- **T3:** Google Cloud, [Use primary and foreign keys](https://docs.cloud.google.com/bigquery/docs/primary-foreign-keys). BigQuery key constraints are not enforced.
- **T4:** Google Cloud, [Budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets). Budget monitoring is not an automatic spending cap.
- **T5:** OpenAI, [Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md/). Project guidance discovery.
