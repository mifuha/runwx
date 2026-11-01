"""Build the compact follow-up section from checked public aggregates."""
import csv
from html import escape
import json
from pathlib import Path
from check_fixed_mix import check_public

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'docs/evidence/berlin-fixed-mix'
PUBLIC='https://github.com/mifuha/runwx/blob/master/'


def pace(value):
    tenths=round(float(value)*10)
    return f'{tenths//600}:{tenths%600/10:04.1f}'


def build_section():
    checked=check_public(EVIDENCE)
    associations=json.loads((EVIDENCE/'associations.json').read_bytes())
    with (EVIDENCE/'summaries.csv').open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    raw=associations['series']['eligible_unweighted:median']['pearson_r']['value']
    fixed=associations['series']['fixed_mix:median']['pearson_r']['value']
    omitted=next(r['value'] for r in associations['series']['fixed_mix:median']['leave_one_out'] if r['omitted_year']==2006)
    year=associations['median_linear_year_sensitivity']['fixed_mix']['value']
    svg=(EVIDENCE/'scatter.svg').read_text(encoding='utf-8')
    svg=svg[svg.index('<svg '):].replace('<svg ', '<svg class="fixed-mix-plot" role="img" aria-label="Four panels comparing recorded and fixed age and gender mix across 16 Berlin editions" ',1)
    table=''.join('<tr><th scope="row">'+r['year']+'</th>'+''.join(
        '<td>'+escape(str(v))+'</td>' for v in [
            'Recorded' if r['view']=='eligible_unweighted' else 'Fixed mix',
            r['median_temp_c'],pace(r['p25_pace_s_per_km']),pace(r['median_pace_s_per_km']),
            pace(r['p75_pace_s_per_km']),f"{float(r['iqr_pace_s_per_km']):.1f}"]
        )+'</tr>' for r in rows if r['view']!='whole_capture')
    evidence=' · '.join(f'<a href="{PUBLIC}docs/evidence/berlin-fixed-mix/{name}">{label}</a>'
        for name,label in [('summaries.csv','Edition values'),('groups.csv','Group proportions'),
            ('age-audit.csv','Age-category counts'),('associations.json','Correlations and omitted years'),
            ('reference-mix.json','Fixed reference mix'),('manifest.json','Hashes and provenance')])
    return f'''<section id="fixed-mix" aria-labelledby="fixed-mix-title">
<p class="eyebrow">One further check / participant mix</p>
<h2 id="fixed-mix-title">Does who enters explain the pattern?</h2>
<p>Different people enter each year. We gave every edition the same mix of recorded age and gender groups, then checked the pattern again.</p>
<p><strong>Warmer editions still tended to have slower median pace.</strong> The median correlation barely changed.</p>
<div class="study-table study-overview"><table><caption>Median pace and temperature across the same 16 editions.</caption><thead><tr><th scope="col">Comparison</th><th scope="col">Correlation (r)</th></tr></thead><tbody><tr><th scope="row">As recorded, with interpretable age categories</th><td>{raw:+.3f}</td></tr><tr><th scope="row">With the same age/gender mix</th><td>{fixed:+.3f}</td></tr></tbody></table></div>
<p class="study-note">Both comparisons use the same {checked['age_eligible']:,} captured results. There are <strong>16 edition-level weather observations</strong>. The four age bands are under 40, 40–49, 50–59 and 60+, within each recorded gender.</p>
<p>This adjustment holds broad recorded categories constant. Training, ability, variation within age bands and incomplete captures remain unresolved. It does not establish a causal heat effect.</p>
<details class="study-disclosure"><summary>How we checked the participant mix</summary>
<p>We averaged the group proportions across the 16 editions, giving each edition equal influence. That fixed mix was applied to the full duration distributions. We did not average group medians. The reference mix stayed fixed for every omitted-year check.</p>
<p>The {checked['unmapped_age']} records with unclear ages remain in the original whole-capture results. They are excluded from both comparisons above, so that exclusion is not mistaken for an adjustment effect.</p>
<p>Leaving out 2006 kept the adjusted median correlation positive ({omitted:+.3f}). After separately removing a linear calendar-year trend from temperature and median pace, their residual correlation was {year:+.3f}. This addresses only a straight-line trend.</p>
<p>The calculation reused saved inputs, the existing parser and fixed 09:00–15:00 Europe/Berlin ERA5 context. Independent export reading and weighted-quantile checks agreed. A separate calculation verified {checked['independent_correlations']} correlation values and {checked['independent_year_sensitivities']} year-sensitivity values. Offline replays reproduced the frozen analytical outputs.</p>
<p>The public checker reproduces counts, reference proportions and coefficients from aggregates. Reproducing weighted quantiles from source records requires the retained private inputs. The two readers share a research source; agreement does not authenticate that source.</p>
<p>{evidence}</p><p><a href="{PUBLIC}analysis/berlin/FIXED_MIX.md">Method and reproduction instructions</a> · <a href="{PUBLIC}analysis/berlin/fixed_mix.py">Analysis code</a> · <a href="{PUBLIC}analysis/berlin/check_fixed_mix.py">Independent checker</a></p>
</details>
<details class="study-disclosure"><summary>Explore the other parts of the distribution</summary>
<p>P25 describes the faster quarter, the median the middle, and P75 the slower quarter. P75 minus P25 measures the width of the middle half. These positions describe each year's captured field; they are not fixed ability groups.</p>
<figure class="fixed-mix-figure">{svg}<figcaption>Grey outlines show recorded results with interpretable ages; green dots show the same records with a fixed mix. Different correlations do not measure different individual heat effects. Pace scales differ between panels.</figcaption></figure>
<p>The same cumulative-weight quantile rule is used before and after adjustment: at an exact boundary, average that duration and the next distinct duration. These pilot quartiles differ from the warehouse's linear interpolation.</p>
<div class="study-table" tabindex="0" role="region" aria-label="Participant-mix chart values"><table><caption>All 32 plotted edition/comparison summaries. Pace is min/km; spread is seconds/km.</caption><thead><tr><th scope="col">Year</th><th scope="col">Comparison</th><th scope="col">Temperature °C</th><th scope="col">P25</th><th scope="col">Median</th><th scope="col">P75</th><th scope="col">Spread</th></tr></thead><tbody>{table}</tbody></table></div>
</details></section>'''
