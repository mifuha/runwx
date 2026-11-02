# Does who enters explain the pattern?

Across the same 16 Berlin research captures, the temperature–median-pace
correlation barely changed after holding broad recorded age/gender composition
constant: **+0.882 before, +0.884 after**. Removing 2006 leaves the adjusted
coefficient at +0.831. After removing separate linear year trends from temperature
and median pace, the residual correlation is +0.912.

These checks describe 16 edition contexts. They do not establish a causal heat
effect or remove training, ability, within-band age differences and capture gaps.
The original [recorded-group study](README.md) remains unchanged.

## Fixed method

Use all 16 reviewed editions, 2003–2018. Preserve duplicate anonymous records.
Of 541,730 accepted captures, 541,659 have interpretable age-category codes.
The other 71 comprise 31 blanks, 39 `M` and one `M<`. Keep them in whole-capture
context; exclude them from both directly compared distributions.

Use under 40, 40–49, 50–59 and 60+ within each recorded gender: eight cells.
Numeric code meanings follow the related [Berlin age-group study](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2021.654544/full).
These are categories, not exact ages. The explicit mapping and frozen choices are
in [fixed-mix.json](fixed-mix.json).

For each cell, average its eligible within-edition proportion across the 16
editions. This gives each edition equal influence on the reference mix. Reweight
each edition's full duration distribution to those proportions; do not average
cell medians. All eight cells are present in every edition. Freeze the reference
mix for all omitted-year checks. Those checks assess the association against a
fixed reference; they are not held-out prediction tests.

Take P25, median and P75 from cumulative probability mass. At an exact boundary,
average the current and next distinct duration; otherwise use the first duration
crossing the target. Use this same rule for both populations. It reproduces ordinary
medians with uniform weights; these quartiles differ from the warehouse's linear
interpolation. P75−P25 measures the middle-half width. Divide durations by 42.195
km. Exact rational weights avoid floating-point ambiguity at boundaries.

Retain the existing median of seven hourly ERA5 observations, 09:00–15:00
Europe/Berlin at 52.5163, 13.3777. This is shared finish-area context, not individual
exposure. Compute Pearson r for all four outcomes and every whole-edition omission.
For median pace, separately fit temperature and pace against centered calendar
year and correlate their residuals. Constant or perfectly fitted series are
explicitly undefined. No p-values or predictions.

## Inspect and reproduce

[Public aggregates](../../docs/evidence/berlin-fixed-mix/) contain 48 summaries,
128 cell counts/proportions, raw age-category counts, reference weights, all
coefficients, source provenance and the checked figure. No runner-level records
or private manifests are published.

Run the public checks with standard-library Python 3.11+:

```bash
python3 analysis/berlin/check_fixed_mix.py docs/evidence/berlin-fixed-mix
```

This independently recomputes counts, reference proportions, 204 correlations and
three year sensitivities from aggregates. It checks unit identities and evidence/
code hashes. It cannot reconstruct weighted quantiles without the source records.

For a full replay, install the existing project and pytest; retained private inputs
at the parent configuration's relative paths must already exist:

```bash
unshare -Urn .venv/bin/python -B analysis/berlin/fixed_mix.py \
  analysis/berlin/fixed-mix.json --output data/local/MY_FRESH_FIXED_MIX
.venv/bin/python -m pytest -q tests/berlin_study
```

Output must be new. Paths resolve against configuration files. Another local
layout needs local configuration copies with adjusted paths and parent-config
hash, preserving all reviewed input hashes. The CLI blocks sockets/subprocesses.
The independent export reader parses times/categories and compares full duration
histograms; its prefix-count CDF queries check weighted quantiles separately.
Covariance calculations check coefficients; the partial-correlation identity
checks the residual year calculation. Expectations in fixtures are hand-derived.

The portable replay preserves the frozen pilot's five analytical CSV/JSON files
byte for byte. The SVG matches after normalising its Windows line endings to LF. Reconciliation values also match; only the checker module
name in its description changed. Runtime manifests contain local paths and current code hashes and
stay private. The original ignored pilot and its independent checks are retained.
Agreement between two readers does not authenticate their common research source.

For the static figure, use an analysis-only environment with the existing
`requirements-plot.txt`, then run `python analysis/berlin/plot_fixed_mix.py RUN_DIR`.
It writes SVG/PDF after the completion marker and refuses existing figure outputs.
Optional `--png` additionally requires PDFium in that isolated environment.
The [page generator](render_fixed_mix_page.py) combines the unchanged original
study with the follow-up, verifies the aggregates and embeds the checked SVG:

```bash
python analysis/berlin/render_fixed_mix_page.py
```

The application serves that generated static HTML and performs no study
calculations or warehouse queries at request time. The follow-up is
[live on the existing service](https://runwx-api-f6n35ol7sa-ew.a.run.app/case-studies/berlin#fixed-mix).
The 1 November 2026 image-only deployment passed page, asset, comparison-response
and browser checks; the full Terraform plan then reported no remaining changes.
See the [deployment record](../../docs/evidence/berlin-fixed-mix-api-validation.json).
