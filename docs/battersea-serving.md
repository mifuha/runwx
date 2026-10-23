# Battersea stored-summary pilot

Battersea compares 18 editions with 2,725 finishers. Its historical inputs rarely
change. A stored summary can avoid recalculating the comparison on each uncached
read, but it must be rebuilt and checked after a data refresh.

The pilot passed on 23 October 2026. **The live API still uses the comparison
view.** Other courses and API permissions are unchanged.

## What we measured

| Uncached API read | Existing view | Stored summary |
|---|---:|---:|
| Bytes processed | 1,354,325 | 4,464 |
| Bytes billed | 188,743,680 (180 MiB) | 10,485,760 (10 MiB) |
| Median local response time | 2.561 s | 0.294 s |
| Local response range | 2.377–2.967 s | 0.292–0.321 s |

There were three uncached reads per path, alternating paths. Each path also had
two cache-enabled reads: one miss and one hit. Both hits processed and billed
zero bytes. These are local API requests with real BigQuery, not public Cloud Run
latency measurements or a load test. They do not establish monthly savings.

The isolated table used the same analytical SQL as commit
`3943f4124ed56f1cd1f3ddf57f6fd0cfb03871e7`. One model, five data tests and two unit
tests passed. Both complete comparison readbacks matched frozen independent
expectations. All ten API responses matched the saved public values for all
18 editions. The candidate contained 18 rows and was set to expire after 24 hours.

Building and testing billed 390 MiB. Two reconciliation reads billed 190 MiB;
ten measured API reads billed 760 MiB. The whole window billed 1,340 MiB across
23 successful jobs, including three zero-billed adapter jobs. Every query had a
200 MiB billing ceiling; that was not a total budget. Billed bytes do not imply
money charged. Source files and detailed local execution evidence remain private.

Representative BigQuery job IDs, retained for audit:

- Table build: `4de0d36d-e383-4d6c-a250-17f4643c86ee`.
- Current full reconciliation: `b0014bc0-3528-4807-99c9-b12397515242`.
- Candidate full reconciliation: `6c8856f9-3e76-4cde-8cb0-80f666704e90`.
- First uncached view/table reads: `ad0ca973-6895-4412-ac4e-708f3d3e5d5f`
  and `3f2fa5f5-df96-446f-8331-5adb467c480d`.

A local measurement-directory error stopped the first attempt before queries.
An offline regression test reproduced it; the corrected harness then ran the
planned reads once. The successful dbt build was not repeated.

## Explicit refresh and rollback

The stage runner accepts optional `"comparison_materialization": "table"` in its
existing JSON configuration. Omission preserves `view`. Only the comparison stage
receives this setting; edition models and analytical SQL are unchanged. Direct
dbt use accepts the same variable through `--vars`.

For the proposed Battersea promotion, use the reviewed 18-edition configuration
and its independent expectations. Keep the existing `mart_course_comparison`
relation name, so no API mapping or response change is needed. Do not enable the
option for other courses as part of this change.

After each approved snapshot refresh, run the existing stage runner with a new
evidence directory: edition build, comparison build/tests, then independent
reconciliation. A table will not update itself when its inputs change. A failed
check must be investigated; it does not automatically undo a built table.

Promotion must first review the saved live view definition and warehouse target.
Changing a view to a table requires dbt to drop the view before creating the
table; this is not an atomic switch and can briefly interrupt reads. Schedule the
approved change accordingly. If it fails, restore the saved view definition or
rebuild the same comparison with `"comparison_materialization": "view"`, then
reconcile again. Rollback is an explicit cloud operation, not an automatic retry.

The pilot does not prove reduced runtime access. Existing grants remain in place.
Any narrower access proposal needs its own permission checks and rollback review.
No deployment, IAM change or live refresh is authorised by this documentation.
