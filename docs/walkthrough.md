# runwx in two minutes

## Berlin · Does the pattern hold?

Warmer Berlin Marathons tended to have slower median paces. Could a change in who
entered explain it? I gave each edition the same mix of four age bands within
each recorded gender. The correlation barely moved, from +0.882 to +0.884.
The fastest groups showed a less consistent pattern.

There are 541,730 captured results across 16 editions. The age comparison uses
the 541,659 with a usable age category. Each dot is one race day, so this tells
us about editions rather than how an individual runner responds to heat.
[Explore the Berlin study and its checks](https://runwx-api-f6n35ol7sa-ew.a.run.app/case-studies/berlin#fixed-mix).

## Battersea · Why store 18 rows?

The results rarely change. Instead of asking BigQuery to calculate the comparison
each time the API needed an uncached result, I used dbt to store one summary row
per edition. All 18 editions returned the same values.

In three uncached reads per version, billed data fell from 180 to 10 MiB per
read. The median local API response time against BigQuery fell from 2.56 to
0.29 seconds. The trade-off is simple: when the inputs change, I have to rebuild
and check the summary. [See the serving experiment](battersea-serving.md).

## Folkestone · What if the input is wrong?

In a Cloud Composer run, a missing timing setting changed the exported results.
The file’s hash differed from the expected one, and Airflow stopped the run
before the BigQuery load. After I corrected the setting, the pipeline passed.
An identical rerun checked the 459 rows already in BigQuery and skipped the upload.
[Follow the failure and recovery](failure-and-recovery.md).

**Try the chart.** In [Lydd 2022](https://runwx-api-f6n35ol7sa-ew.a.run.app/?course=lydd-half&pace=median-pace&weather=temperature),
the dot shows the median pace (5:30/km). The line shows the middle half of
finishers (4:43–6:16/km).
