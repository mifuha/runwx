# Berlin pace and weather summaries

The Berlin mart calculates statistics from accepted results in explicitly chosen
research snapshots. It keeps identical anonymous results as separate records and
excludes held records from pace calculations.

For each edition it returns:

- Captured, accepted and held counts, plus the published count where known.
- Fastest recorded duration, mean, median and 25th/75th percentiles.
- Mean and median of the lowest `top_n` durations (20 by default).
- The corresponding paces in seconds per kilometre, using 42.195 km.
- Saved fixed-window temperature, wind, humidity and precipitation.
- Source/report/weather hashes and the research-population/course-era labels.

The top group uses recorded durations, not official places. Ties keep separate
source rows; a source locator only breaks ties when choosing exactly N records.
Changing N does not change the overall distribution or weather window. An edition
with no accepted results has null pace statistics. Mixed edition settings produce
no summary and fail the completeness test.

## Build after the snapshots are loaded

Pass only reviewed, loaded Berlin tables from the target project. One table is
enough for a first edition summary; multiple editions produce one row each in the
same mart. Choose one snapshot per year.

The [historical Terraform root](../infra/gcp/historical/README.md) can prepare that
dataset with `berlin_analysis_dataset_id`, for example
`runwx_dbt_berlin_research_v1`. It stays separate from the source snapshot tables;
review and approve the saved plan before applying it. The option defaults to off
and adds no runtime access.

After a separately approved load and with an approved output dataset:

```bash
RUNWX_DBT_PROJECT=runwx-learning-mifuha \
RUNWX_DBT_DATASET=APPROVED_OUTPUT_DATASET \
  dbt build --project-dir dbt --profiles-dir dbt --target cloud \
  --select tag:berlin \
  --vars '{"berlin_research_tables": ["runwx-learning-mifuha.runwx_staging.berlin_2018_research_bfd49c5c5d9c"], "top_n": 20}'
```

The models are disabled by default, so existing builds keep their current scope.
The mart is `mart_berlin_edition_summary`. The existing reconciliation reader
compares its rows with independently calculated expected values before publication.

dbt unit fixtures cover ties, held rows, an empty accepted population, clamping N
and inconsistent context. CI checks table/N configuration, parses the unit fixtures
and compiles models and data-test SQL with network blocked and a dummy identity. Executing the SQL tests
and checking real warehouse output require BigQuery. Offline compilation is not a
successful native build.

## Berlin 2018 validation — 21 October 2026

The private 2018 summary was built in BigQuery: one table, seven data tests and
two unit tests passed. All 44 checked fields, including pace statistics, counts,
source hashes and the full saved weather context, reconciled with the independent
calculations and hash-verified preparation report using the existing floating-point
tolerance. The source snapshot stayed unchanged.

The first attempts stopped on two unit-fixture problems: a reserved SQL name and
different expected columns between rows. Correcting the fixtures let the existing
statistics SQL run unchanged. An offline regression now checks the expected columns.

This covers 40,641 captured accepted results, compared with 40,651 published
finishers. The ten-record gap remains explicit. Berlin is not on the public
comparison page yet; this validates one research edition, not a weather effect.

## Full cohort validation — 21 October 2026

All 16 reviewed editions (2003–2018) are loaded: 541,730 accepted records and no
held records. The native build passed one materialized summary model, seven data
tests and two unit tests. Independent reconciliation checked 44 fields and the
full weather context for every edition against frozen original-CSV calculations.
The existing 2018 snapshot and all raw tables stayed unchanged during analytics.
An identical 2003 rerun made no second upload; the final Terraform plan was no-op.

Fixed-window median temperatures range from 10.5 to 24 °C. Published-count gaps,
including the extra 79 captured records in 2008 and unknown 2013 total, remain
explicit. This verifies the research summaries, not a weather effect.

The API and chart can now present this mart through a distinct research response.
That integration is prepared locally; the live four-course site is unchanged.
It needs one read grant on the materialized summary, with no raw-table access.

## Interpretation

These summaries describe a published research capture, not confirmed complete
official fields. Count gaps remain visible, including 2018's ten missing records;
2013's ambiguous published count stays null. The post-2003 course era does not
establish identical routes. Timing basis and individual starts are unavailable.

Weather is the saved 09:00–15:00 Europe/Berlin finish-area ERA5 context. It does not
depend on finishing durations and is not each runner's exposure. Precipitation is
the saved sum of hourly amounts for that window, not a median. Comparing these
edition summaries does not establish a weather effect.

The [loader](berlin-research-load.md) and the optional
`berlin_research_tables` map in the [historical Terraform root](../infra/gcp/historical/README.md)
prepare the inputs. A reviewed saved plan and approval are needed before table
creation or upload. No Berlin data has been added to the live comparison by this
implementation alone.
