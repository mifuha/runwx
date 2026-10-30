# Berlin: does the pattern hold for everyone?

Across the 16 reviewed 2003–2018 research captures, warmer editions tended to have
slower median pace. That pattern remains within recorded female and male groups.
Among the fastest captured results it is weaker and less consistent.

| Recorded group | Fastest 20 r | Remaining after 20 r | Fastest 50 r | Remaining after 50 r |
| --- | ---: | ---: | ---: | ---: |
| Female | +0.203 | +0.837 | +0.074 | +0.837 |
| Male | +0.472 | +0.911 | +0.503 | +0.911 |

Each series has **16 edition observations**, sharing the same weather contexts.
The 541,730 accepted records are the input population, not independent weather
observations. Positive r means warmer editions tend to have slower median pace.
It does not measure seconds lost per degree or establish causation.

The whole-capture r is +0.882; recorded female +0.837 and male +0.912.
All remain positive after any one edition is omitted. The female fastest-50
coefficient changes from +0.074 to −0.186 when 2006 is omitted. All editions
remain in the main results. We report both predefined selection sizes.

## Fixed method

Use all 16 research captures, preserving identical anonymous records. Median
reported duration / 42.195 km is the outcome. Exposure is the median of seven
hourly ERA5 temperatures, 09:00–15:00 Europe/Berlin, at the reviewed finish-area
proxy (52.5163, 13.3777). Each edition has equal weight. The weather window does
not depend on finish durations.

First summarise the whole capture and recorded female/male groups (48 rows).
Then sort durations within edition and recorded gender, split exactly fastest
20 versus remaining; repeat with fastest 50 (128 rows). Tied durations retain
source order. Calculate Pearson r using `statistics.correlation` and repeat
omitting each entire edition. Constant series have an explicitly undefined r.
The whole pattern was already seen: this is exploratory, not confirmatory.

Fastest captured does not establish elite status; remaining does not mean amateur.
Outcome-based selection, changing field strength, age mix, equipment and year
trends remain unresolved. The fixed weather window can poorly represent faster
runners' actual conditions. Different coefficients do not establish different
heat sensitivity. No age/year adjustment, p-values, predictions or causal claims.
Research captures have completeness gaps, unknown timing and individual starts;
2008 has 79 extra records against the published count, and 2013 has no confirmed
published total. See [source and warehouse checks](../../docs/berlin-statistics.md).

## Reproduce the public aggregate checks

From the repository root, with Python 3.11+ (no cloud or plotting dependencies):

```bash
python3 analysis/berlin/verify.py docs/evidence/berlin-case-study
```

This independently checks 136 performance-group and 51 whole/recorded-group
coefficients, including every omission, using the covariance formula.
[CSV, correlations and input hashes](../../docs/evidence/berlin-case-study/) are
public aggregates; runner-level inputs and machine paths are not published.

## Replay retained inputs offline

Install the existing project and pytest in a virtual environment. The pinned
race source, saved weather, prepared exports and frozen independent baseline
must already be available. `inputs.json` documents their relative locations and
reviewed hashes; paths resolve against that file, not the current directory.
For another local layout, use a local copy of the input config, adjust paths,
and update its hash in a local copy of `study.json`. Preserve reviewed input
hashes. The relative catalog path points to the tracked source catalog.

```bash
unshare -Urn .venv/bin/python -B analysis/berlin/performance.py \
  analysis/berlin/study.json --output data/local/berlin-my-fresh-replay
.venv/bin/python -m pytest -q tests/berlin_study
```

A fresh output directory is required. The CLI blocks sockets and subprocesses.
Shared runwx parsing and weather validation check the original inputs. A separate
NDJSON reader parses reported times independently and checks complete duration
histograms and group medians. Explicit validation failures precede output.
Two implementations sharing a source do not independently authenticate that source.

The tracked replay matched all four published CSV/association files byte for byte.
Original local evidence is preserved. Input manifests and execution timings from
new runs remain local. Independent user practice has not yet been recorded.

## Build the static page

Plotting is isolated from the application: install `requirements-plot.txt` in an
analysis-only environment, then run `python analysis/berlin/render_page.py`.
ReportLab generates the scientific scatter plots; the service serves packaged
HTML with inline SVGs and makes no query for this study. The generator first
checks the aggregate correlations. The generated HTML is committed with the page.

For a two-minute walkthrough: calculate the 2006 whole median (15,211 seconds /
42.195 = 6:00.5/km), explain r across 16 paired editions, then show what changes
when 2006 is omitted. Record independent practice only after performing it.
