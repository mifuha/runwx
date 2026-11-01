"""Static four-panel research figure, using the existing isolated plotting runtime."""
import argparse
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import platform
import sys
platform.uname()

# Load the previously tested audit guard without importing analysis or production dependencies.
from offline_guard import install
install()
import reportlab
import reportlab.rl_config
reportlab.rl_config.invariant=1
from reportlab.graphics import renderPDF,renderSVG
from reportlab.graphics.shapes import Drawing,String,Line,Circle,Rect
from reportlab.lib import colors


def render(folder, png=False):
    folder=Path(folder)
    if not (folder/'COMPLETE.json').is_file():
        raise ValueError('validated analysis completion marker required')
    if any((folder/f'scatter.{suffix}').exists() for suffix in ('svg','pdf') + (('png',) if png else ())):
        raise FileExistsError('figure output already exists')
    with (folder/'summaries.csv').open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
    stats=json.loads((folder/'associations.json').read_text())['series']
    green=colors.HexColor('#245940'); grey=colors.HexColor('#7e8992')
    ink=colors.HexColor('#243a31'); faint=colors.HexColor('#e1e7df')
    d=Drawing(1100,920)
    d.add(Rect(0,0,1100,920,fillColor=colors.HexColor('#faf9f3'),strokeColor=None))
    d.add(String(50,883,'Berlin: does the pattern survive the same participant mix?',fontName='Helvetica-Bold',fontSize=21,fillColor=ink))
    d.add(String(50,854,'16 editions, 2003-2018 | Four age bands within each recorded gender',fontSize=13,fillColor=ink))
    for cx,color,filled,label in [(57,grey,False,'As recorded, interpretable ages'),(510,green,True,'Same age/gender mix')]:
        d.add(Circle(cx,826,4,strokeColor=color,fillColor=color if filled else colors.HexColor('#faf9f3')))
        d.add(String(cx+14,822,label,fontSize=13,fillColor=ink))
    for i,(metric,title) in enumerate([('p25','Faster quarter (P25)'),('median','Middle of the field (median)'),('p75','Slower quarter (P75)'),('iqr','Gap between quarters (P75 - P25)')]):
        left=52+(i%2)*540; bottom=468-(i//2)*372; w=458; h=245
        chosen={v:[r for r in rows if r['view']==v] for v in ('eligible_unweighted','fixed_mix')}
        vals=[float(r[metric+'_pace_s_per_km']) for rs in chosen.values() for r in rs]
        low=math.floor((min(vals)-5)/10)*10; high=math.ceil((max(vals)+5)/10)*10
        def xy(r):
            return left+(float(r['median_temp_c'])-9)/16*w,bottom+(float(r[metric+'_pace_s_per_km'])-low)/(high-low)*h
        d.add(String(left,bottom+h+66,title,fontName='Helvetica-Bold',fontSize=16,fillColor=ink))
        a=stats['eligible_unweighted:'+metric]['pearson_r']['value'];b=stats['fixed_mix:'+metric]['pearson_r']['value']
        d.add(String(left,bottom+h+43,f'Correlation r: recorded {a:+.3f}  /  fixed mix {b:+.3f}',fontSize=12,fillColor=ink))
        d.add(String(left,bottom+h+23,'Spread (seconds/km); higher = wider' if metric=='iqr' else 'Pace (min/km); higher = slower',fontSize=12,fillColor=ink))
        ticks=5
        for n in range(ticks+1):
            value=low+(high-low)*n/ticks; py=bottom+h*n/ticks
            d.add(Line(left,py,left+w,py,strokeColor=faint,strokeWidth=.7))
            label=f'{value:.0f}' if metric=='iqr' else f'{round(value)//60}:{round(value)%60:02}'
            d.add(String(left-9,py-4,label,textAnchor='end',fontSize=11,fillColor=ink))
        for temp in (10,15,20,25):
            px=left+(temp-9)/16*w
            d.add(String(px,bottom-20,str(temp),textAnchor='middle',fontSize=11,fillColor=ink))
        d.add(String(left+w/2,bottom-40,'Fixed-window median temperature (C)',textAnchor='middle',fontSize=12,fillColor=ink))
        for view,color,filled in [('eligible_unweighted',grey,False),('fixed_mix',green,True)]:
            for r in chosen[view]:
                x,y=xy(r)
                d.add(Circle(x,y,3.8,strokeColor=color,strokeWidth=1.1,fillColor=color if filled else colors.HexColor('#faf9f3')))
                if r['year']=='2006':
                    d.add(String(x-9,y+(10 if filled else -17),'2006 fixed' if filled else '2006 recorded',textAnchor='end',fontSize=10,fillColor=color))
    d.add(String(52,45,'541,659 age-eligible records; 71 unclear ages excluded from both comparison series.',fontSize=12,fillColor=ink))
    d.add(String(52,24,'Each dot is one edition. Adjustment describes measured composition; it does not isolate a heat effect.',fontSize=12,fillColor=ink))
    svg=renderSVG.drawToString(d).replace('<title>...</title>','<title>Berlin fixed participant mix pilot</title>').replace('<desc>...</desc>','<desc>Four scatter panels compare unweighted and fixed age/gender mix pace distributions. All edition values are in summaries.csv.</desc>')
    (folder/'scatter.svg').write_bytes(svg.replace('\r\n','\n').encode('utf-8'))
    renderPDF.drawToFile(d,str(folder/'scatter.pdf'))
    if png:
        import pypdfium2 as pdfium
        pdf=pdfium.PdfDocument(str(folder/'scatter.pdf'))
        page=pdf[0]; bitmap=page.render(scale=1.6); image=bitmap.to_pil();image.save(folder/'scatter.png');image.close();bitmap.close();page.close();pdf.close()
    (folder/'plotting.json').write_text(json.dumps({'runtime':'Preinstalled isolated desktop Python; socket/subprocess audit guard',
       'reportlab':reportlab.Version,'source_summaries_sha256':sha256((folder/'summaries.csv').read_bytes()).hexdigest(),
       'figure':{'panels':4,'series_per_panel':2,'edition_dots_per_series':16},
       'files':{f'scatter.{ext}':sha256((folder/f'scatter.{ext}').read_bytes()).hexdigest() for ext in ('svg','pdf') + (('png',) if png else ())}},indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder');p.add_argument('--png',action='store_true');args=p.parse_args();render(args.folder,png=args.png)
