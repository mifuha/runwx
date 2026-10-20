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
same mart. Choose one snapshot per year. For example, after a separately approved
load and with an approved output dataset:

```bash
RUNWX_DBT_PROJECT=runwx-learning-mifuha \
RUNWX_DBT_DATASET=APPROVED_OUTPUT_DATASET \
  dbt build --project-dir dbt --profiles-dir dbt --target cloud \
  --select tag:berlin \
  --vars '{"berlin_research_tables": ["runwx-learning-mifuha.runwx_staging.berlin_2018_research_bfd49c5c5d9c"], "top_n": 20}'
```

The models are disabled by default, so existing builds keep their current scope.
The mart is `mart_berlin_edition_summary`. This change adds no runner, API endpoint,
or website feature. The existing reconciliation reader can compare its rows with
independently calculated expected values before any publication.

dbt unit fixtures cover ties, held rows, an empty accepted population, clamping N
and inconsistent context. CI checks table/N configuration, parses the unit fixtures
and compiles models and data-test SQL with network blocked and a dummy identity. Executing the SQL tests
and checking real warehouse output require BigQuery. Offline compilation is not a
successful native build.

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
