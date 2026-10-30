"""Build the static case study from verified aggregates. Plotting is analysis-only."""
import csv
from html import escape
import json
import math
from pathlib import Path
import re
from verify import check_directory

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/berlin-case-study'
PUBLIC = 'https://github.com/mifuha/runwx/blob/master/'


def pace(value):
    tenths = round(float(value) * 10)
    return f'{tenths // 600}:{tenths % 600 / 10:04.1f}'


def chart(rows, key, title):
    # Installed only in the analysis environment; the service serves generated HTML.
    from reportlab.graphics import renderSVG
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.widgets.markers import makeMarker
    from reportlab.lib import colors
    selected = [r for r in rows if r['series'] == key]
    values = [(float(r['median_temp_c']), float(r['median_pace_s_per_km'])) for r in selected]
    lo = math.floor((min(y for x,y in values)-3)/10)*10
    hi = math.ceil((max(y for x,y in values)+3)/10)*10
    d = Drawing(520,340)
    p = LinePlot(); p.x=58; p.y=47; p.width=440; p.height=260
    p.data=[values]; p.joinedLines=0
    p.lines[0].strokeColor=colors.HexColor('#214f3e')
    p.lines[0].symbol=makeMarker('FilledCircle'); p.lines[0].symbol.size=7
    p.xValueAxis.valueMin=9; p.xValueAxis.valueMax=25
    p.xValueAxis.valueSteps=[10,15,20,25]
    p.yValueAxis.valueMin=lo; p.yValueAxis.valueMax=hi
    p.yValueAxis.valueSteps=list(range(lo,hi+1,10))
    p.yValueAxis.labelTextFormat=lambda y: f'{int(y)//60}:{int(y)%60:02}'
    for axis in (p.xValueAxis,p.yValueAxis):
        axis.labels.fontName='Helvetica'; axis.labels.fontSize=14
        axis.labels.fillColor=colors.HexColor('#53675d'); axis.strokeColor=colors.HexColor('#cad8cf')
    p.yValueAxis.visibleGrid=True; p.yValueAxis.gridStrokeColor=colors.HexColor('#e8eee8')
    d.add(p)
    d.add(String(58,325,'Median pace (min/km) · higher means slower',fontName='Helvetica',fontSize=14))
    d.add(String(278,10,'Temperature (°C)',textAnchor='middle',fontName='Helvetica',fontSize=14))
    hot=next(r for r in selected if r['year']=='2006')
    x=58+(float(hot['median_temp_c'])-9)/16*440
    y=47+(float(hot['median_pace_s_per_km'])-lo)/(hi-lo)*260
    d.add(String(x-8,y+11,'2006',textAnchor='end',fontName='Helvetica',fontSize=14))
    svg=renderSVG.drawToString(d)
    svg=svg[svg.index('<svg '):]
    svg=re.sub(r'width="520" height="340"', 'class="study-plot" role="img" aria-label="'+escape(title)+'"', svg, count=1)
    svg=svg.replace('<title>...</title>', '<title>'+escape(title)+'</title>').replace('<desc>...</desc>', '<desc>Sixteen editions. Each dot is one year; 2006 is labelled. Complete values follow in the data table.</desc>')
    for identifier in re.findall(r'id="([^"]+)"', svg):
        svg = svg.replace(f'id="{identifier}"', f'id="{key}-{identifier}"').replace(f'url(#{identifier})', f'url(#{key}-{identifier})')
    return svg


def build():
    checked=check_directory(EVIDENCE)
    with (EVIDENCE/'summaries.csv').open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
    with (EVIDENCE/'whole-summaries.csv').open(newline='',encoding='utf-8') as f: whole=list(csv.DictReader(f))
    stats=json.loads((EVIDENCE/'associations.json').read_text())['series']
    baseline=json.loads((EVIDENCE/'whole-associations.json').read_text())['series']
    def panels(n):
        cards=[]
        for gender in ('female','male'):
            for subset in ('fastest','remaining'):
                key=f'{gender}_{subset}_{n}'
                title=f'Fastest {n}' if subset=='fastest' else 'Rest of the group'
                description=(f'{n} fastest captured results per edition.' if subset=='fastest'
                             else f'All other captured {gender} results.')
                finding=('The pattern is weaker here.' if subset=='fastest'
                         else 'Warmer editions tend to be slower.')
                cards.append(f'<figure class="study-card"><p class="study-group-label">Recorded {gender}</p><h3>{title}</h3><p class="study-population">{description}</p>{chart(rows,key,f"Recorded {gender}: {title}")}<figcaption>{finding}</figcaption></figure>')
        return '<div class="study-grid">'+''.join(cards)+'</div>'
    performance_stats=''.join(
        f'<tr><th scope="row">{gender.capitalize()} · {"fastest" if subset == "fastest" else "rest after fastest"} {n}</th>'
        f'<td>{stats[f"{gender}_{subset}_{n}"]["pearson_r"]["value"]:+.3f}</td>'
        f'<td>{stats[f"{gender}_{subset}_{n}"]["leave_one_out_min"]:+.3f} to {stats[f"{gender}_{subset}_{n}"]["leave_one_out_max"]:+.3f}</td></tr>'
        for n in (20,50) for gender in ('female','male') for subset in ('fastest','remaining'))
    grouped=''.join(f'<tr><th scope="row">{label}</th><td>{baseline[key]["pearson_r"]["value"]:+.3f}</td><td>{baseline[key]["leave_one_out_min"]:+.3f} to {baseline[key]["leave_one_out_max"]:+.3f}</td></tr>' for key,label in [('all','Whole capture'),('female','Recorded female'),('male','Recorded male')])
    cells=''.join('<tr>'+f'<th scope="row">{r["year"]}</th>'+''.join(f'<td>{escape(str(v))}</td>' for v in [r['recorded_gender'],r['n'],r['subset'],r['count'],f'{float(r["median_temp_c"]):g}',pace(r['median_pace_s_per_km'])])+'</tr>' for r in rows)
    context=''.join('<tr>'+f'<th scope="row">{r["year"]}</th>'+''.join(f'<td>{escape(str(v))}</td>' for v in [r['group'],r['count'],f'{float(r["group_share_of_accepted"])*100:.1f}%',pace(r['median_pace_s_per_km']),r['difference_from_published'] or 'Unknown'])+'</tr>' for r in whole)
    downloads=' · '.join(f'<a href="{PUBLIC}docs/evidence/berlin-case-study/{name}">{label}</a>' for name,label in [('summaries.csv','Group CSV'),('whole-summaries.csv','Whole-capture CSV'),('associations.json','All group correlations and omissions'),('whole-associations.json','Whole-capture correlations and omissions'),('manifest.json','Hashes and provenance')])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>runwx · Does the pattern hold for everyone?</title>
<meta name="description" content="A checked Berlin Marathon case study: temperature, median pace, recorded groups and sensitivity to individual editions.">
<link rel="stylesheet" href="/assets/styles.css"></head><body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><a class="brand" href="/" aria-label="runwx home">runwx</a><nav class="site-nav" aria-label="Main navigation"><a href="/">Compare</a><a href="/how-it-works">How it works</a></nav></header>
<main id="main" class="berlin-study"><section class="intro"><p class="eyebrow">Berlin Marathon / 16 editions · 2003–2018</p>
<h1>Does the pattern hold for everyone?</h1>
<p class="lede">Warmer editions tended to be slower. But the pattern was weaker among the fastest recorded results.</p>
<p class="study-note">One dot = one edition from a research dataset. These patterns do not prove a weather effect.</p>
<a class="text-link" href="/?course=berlin-marathon&amp;pace=median-pace&amp;weather=temperature">← Back to the Berlin comparison</a></section>
<section class="study-question" aria-labelledby="challenged"><h2 id="challenged">We checked the pattern three ways.</h2>
<ol class="study-steps"><li><span class="eyebrow">01 / All results</span><strong>Split the recorded groups.</strong><p>The pattern remains within both recorded female and male groups.</p></li><li><span class="eyebrow">02 / Fastest results</span><strong>Compare the fastest 20.</strong><p>The pattern is weaker among the fastest 20 captured results in each group.</p></li><li><span class="eyebrow">03 / One year at a time</span><strong>Leave out one year.</strong><p>Leaving out any one year keeps the broad-field pattern positive. The fastest groups are less stable.</p></li></ol></section>
<section aria-labelledby="survived"><h2 id="survived">Fastest 20 versus the rest.</h2>
<p>Each dot shows a year's median pace and temperature. <strong>Right = warmer. Up = slower.</strong></p>
<p class="study-note">16 edition-level weather observations, shared across the panels. <strong>Pace scales differ by panel</strong>, so visual slopes cannot tell us which group is more affected by heat.</p>
{panels(20)}
<div class="study-sensitivity"><h3>Does choosing 50 instead of 20 change the story?</h3><p>The fastest-50 female results showed little linear pattern. The correlation became negative when 2006 was omitted. The male pattern is also weaker than in the rest of its group.</p><p class="study-note">All 16 editions stay in the main results. Both selection sizes were chosen before these calculations.</p></div>
<details class="study-disclosure"><summary>Show the fastest-50 charts</summary>{panels(50)}</details>
<details class="study-disclosure"><summary>See the correlation numbers</summary><p>Correlation, called <strong>r</strong>, measures a straight-line pattern: near +1 means warmer editions consistently pair with slower pace; near 0 means little linear pattern; negative means the pattern runs the other way. It does not tell us how much heat slows a runner.</p>
<div class="study-table study-overview"><table><caption>All results and recorded groups.</caption><thead><tr><th scope="col">Population</th><th scope="col">r</th><th scope="col">Range with one year left out</th></tr></thead><tbody>{grouped}</tbody></table></div>
<div class="study-table study-overview"><table><caption>Fastest results and the rest of each recorded group.</caption><thead><tr><th scope="col">Population</th><th scope="col">r</th><th scope="col">Range with one year left out</th></tr></thead><tbody>{performance_stats}</tbody></table></div></details>
<div class="study-limits"><h3>A useful pattern. Still an incomplete explanation.</h3><ul><li>Different runners enter each year. Age, training and field strength can change.</li><li>“Fastest” describes results in this dataset, not verified elite status. The rest are not necessarily amateurs. These groups are chosen using finishing times.</li><li>Every group shares the same six-hour weather estimate. It is not each runner's actual exposure.</li></ul><p>We can describe the association. We cannot say temperature caused the pace differences.</p></div></section>
<section aria-labelledby="checked"><h2 id="checked">How do we know the numbers hold up?</h2>
<p>We checked 541,730 captured results, compared two calculation paths and reproduced the saved outputs. The analysis still has only <strong>16 edition-level weather observations</strong>.</p>
<details class="study-disclosure"><summary>How we checked</summary>
<p>This grouping study ran offline against saved inputs, checked against the original research file and prepared exports. The page serves the checked summaries. It does not recalculate them.</p>
<p>Median reported duration divided by 42.195 km. Temperature is the median of seven hourly ERA5 observations from 09:00 to 15:00 Europe/Berlin at the reviewed finish-area proxy. The window is independent of finishing durations. The primary fastest-20 split and fastest-50 sensitivity were fixed before these subgroup calculations.</p>
<p>Identical anonymous records remain separate. Independent export parsing checks counts and duration distributions. A separate covariance calculation verifies {checked['performance']['correlations_checked']} group correlations and {checked['whole']['correlations_checked']} whole/recorded-group correlations. Replays matched the retained analytical outputs.</p>
<p>These are anonymised research captures from the CC0-declared Kaggle version 2 dataset, not verified complete official fields. Timing basis and individual starts are unknown. Count gaps remain: 2008 has 79 more captured records than the published total; the 2013 published total is unknown. Course-era evidence does not prove identical routes.</p>
<p>{downloads}</p><p><a href="{PUBLIC}analysis/berlin/README.md">Method and reproduction instructions</a> · <a href="{PUBLIC}analysis/berlin/performance.py">Analysis code</a> · <a href="{PUBLIC}analysis/berlin/verify.py">Independent checker</a> · <a href="{PUBLIC}docs/berlin-statistics.md">Source qualification and warehouse checks</a></p>
<p>The two readers share a research source: agreement checks implementation, not authenticity of the original results. No age/year adjustment, p-values or causal claims.</p></details>
<details class="study-disclosure"><summary>Read the chart values as a table</summary><div class="study-table" tabindex="0" role="region" aria-label="Performance group data"><table><caption>All 128 performance-group summaries; pace is min/km.</caption><thead><tr><th scope="col">Year</th><th scope="col">Recorded group</th><th scope="col">N</th><th scope="col">Subset</th><th scope="col">Count</th><th scope="col">Temperature °C</th><th scope="col">Median pace</th></tr></thead><tbody>{cells}</tbody></table></div></details>
<details class="study-disclosure"><summary>Counts and population context by year</summary><div class="study-table" tabindex="0" role="region" aria-label="Edition population data"><table><caption>48 whole/recorded-group summaries. Published count gaps refer to the whole edition.</caption><thead><tr><th scope="col">Year</th><th scope="col">Group</th><th scope="col">Count</th><th scope="col">Share</th><th scope="col">Median pace</th><th scope="col">Published-count gap</th></tr></thead><tbody>{context}</tbody></table></div></details>
<p class="study-note">Explore the plots as associations, following <a href="https://www.itl.nist.gov/div898/handbook/eda/section3/scatterp.htm">NIST's scatter-plot guidance</a>.</p></section></main></body></html>'''


if __name__ == '__main__':
    output = ROOT / 'src/runwx/api/static/berlin-case-study.html'
    output.write_text(build(), encoding='utf-8')
    print('Generated the case study from independently verified aggregates.')
