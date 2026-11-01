"""Static case study: data agreement, accessibility and no warehouse access."""
import asyncio
import csv
from hashlib import sha256
import json
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
from runwx.api.app import app, get_repository

ROOT = Path(__file__).resolve().parents[1]


def request(path):
    async def get():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.get(path)
    return asyncio.run(get())


def test_static_page_does_not_construct_a_warehouse_client():
    def forbidden():
        raise AssertionError('case study must not request a warehouse dependency')
    app.dependency_overrides[get_repository] = forbidden
    try:
        response = request('/case-studies/berlin')
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-cache'
    soup = BeautifulSoup(response.text, 'html.parser')
    css = request('/assets/styles.css')
    assert soup.find('link',rel='stylesheet')['href'] == '/assets/styles.css?v='+sha256(css.content).hexdigest()
    assert len(soup.select('figure svg[role="img"]')) == 9
    assert all('2006' in s.get_text() for s in soup.select('figure svg'))
    assert soup.find('a',href='#main')
    assert soup.find('main',id='main')
    assert len(soup.find_all(id=True)) == len({tag['id'] for tag in soup.find_all(id=True)})
    assert not soup.find('script')
    assert 'Pace scales differ by panel' in soup.get_text()
    assert '16 edition-level weather observations' in soup.get_text()
    assert 'became negative when 2006 was omitted' in soup.get_text()
    summaries = list(csv.DictReader((ROOT/'docs/evidence/berlin-case-study/summaries.csv').open()))
    performance = soup.select_one('[aria-label="Performance group data"] tbody').find_all('tr')
    assert len(performance) == len(summaries) == 128
    for row, expected in zip(performance, summaries):
        cells = [c.get_text() for c in row.find_all(['td','th'])]
        assert cells[:5] == [expected[k] for k in ('year','recorded_gender','n','subset','count')]
        assert float(cells[5]) == float(expected['median_temp_c'])
        minutes, seconds = cells[6].split(':')
        assert abs(int(minutes)*60+float(seconds)-float(expected['median_pace_s_per_km'])) <= .051
    # GitHub evidence links resolve to tracked candidates, without external requests.
    prefix='https://github.com/mifuha/runwx/blob/master/'
    for link in soup.find_all('a',href=True):
        if link['href'].startswith(prefix):
            assert (ROOT/link['href'][len(prefix):]).exists(), link['href']


def test_navigation_and_published_hashes():
    for url in ('/','/how-it-works'):
        assert 'href="/case-studies/berlin"' in request(url).text
    folder=ROOT/'docs/evidence/berlin-case-study'
    manifest=json.loads((folder/'manifest.json').read_text())
    for filename, expected in manifest['files'].items():
        assert sha256((folder/filename).read_bytes()).hexdigest() == expected
    for filename, expected in manifest['analysis_code'].items():
        assert sha256((ROOT/'analysis/berlin'/filename).read_bytes()).hexdigest() == expected
    assert '/home/' not in json.dumps(manifest)
    assert '/mnt/' not in json.dumps(manifest)


def test_participant_mix_section_matches_checked_aggregates():
    response=request('/case-studies/berlin')
    soup=BeautifulSoup(response.text,'html.parser')
    section=soup.select_one('#fixed-mix')
    assert section is not None
    assert '541,659' in section.get_text()
    assert '16 edition-level weather observations' in section.get_text()
    assert 'does not establish a causal heat effect' in section.get_text()
    folder=ROOT/'docs/evidence/berlin-fixed-mix'
    associations=json.loads((folder/'associations.json').read_bytes())
    before_after=section.select('.study-overview tbody td')
    assert [cell.get_text() for cell in before_after]==[
        f"{associations['series'][view+':median']['pearson_r']['value']:+.3f}"
        for view in ('eligible_unweighted','fixed_mix')]
    source=list(csv.DictReader((folder/'summaries.csv').open()))
    expected=[r for r in source if r['view']!='whole_capture']
    displayed=section.select('[aria-label="Participant-mix chart values"] tbody tr')
    assert len(displayed)==len(expected)==32
    for row,value in zip(displayed,expected):
        cells=[cell.get_text() for cell in row.find_all(['th','td'])]
        assert cells[0]==value['year']
        assert cells[1]==('Recorded' if value['view']=='eligible_unweighted' else 'Fixed mix')
        assert float(cells[2])==float(value['median_temp_c'])
        for index,metric in enumerate(('p25','median','p75'),3):
            minutes,seconds=cells[index].split(':')
            assert abs(int(minutes)*60+float(seconds)-float(value[metric+'_pace_s_per_km']))<=.051
        assert abs(float(cells[6])-float(value['iqr_pace_s_per_km']))<=.051
    assert all(tag.find_parent('details') for tag in section.select('figure, [aria-label="Participant-mix chart values"]'))
    assert section.select_one('svg[role="img"]')
    assert not section.find('script')
