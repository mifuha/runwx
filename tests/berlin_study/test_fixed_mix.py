from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import json
import math
import pytest
import fixed_mix as study
import check_fixed_mix as independent


@pytest.mark.parametrize('values,expected',[
    ([60,120,180],{'p25':60,'median':120,'p75':180,'iqr':120}),
    ([60,120,180,240],{'p25':90,'median':150,'p75':210,'iqr':120}),
    ([60,60,180],{'p25':60,'median':60,'p75':180,'iqr':120}),
    ([60],{'p25':60,'median':60,'p75':60,'iqr':0}),
])
def test_hand_order_statistics(values,expected):
    assert study.quantiles(Counter(values)) == expected


def test_unequal_masses_boundary_and_duplicates():
    # 25% at 60, 50% at 120, 25% at 240: quartiles at exact boundaries average neighbours.
    assert study.quantiles({60:F(1,4),120:F(1,2),240:F(1,4)}) == {'p25':90,'median':120,'p75':180,'iqr':90}
    assert study.quantiles({60:F(3,4),240:F(1,4)})['median'] == 60
    dist=independent.prefix(Counter({60:1,120:2,240:1}))
    assert independent.inverted_quantile(dist[0],lambda t:independent.cdf(dist,t),F(3,4)) == 180


def test_weight_distribution_not_group_medians():
    # Cell A: median 100, cell B: median 1000; mixture median 100, not mean-of-medians 550.
    cells={c:Counter({100:1}) for c in study.CELLS}
    a,b=study.CELLS[:2]
    cells[a]=Counter({10:1,100:1,1000:1}); cells[b]=Counter({1000:1})
    # Remaining cells carry tiny valid positive weights and durations 100.
    weights={c:F(1,100) for c in study.CELLS}
    weights[a]=F(7,10); weights[b]=F(24,100)
    assert sum(weights.values())==1
    result=study.reweight(cells,weights)
    assert sum(result.values())==1
    assert study.quantiles(result)['median']==100


def test_equal_editions_reference_and_identity_weights():
    a={c:Counter({60:1}) for c in study.CELLS}
    b={c:Counter({120:10}) for c in study.CELLS}
    b[study.CELLS[0]]=Counter({120:20})
    w=study.reference_mix({2003:a,2004:b})
    assert w[study.CELLS[0]]==(F(1,8)+F(2,9))/2
    identity={c:F(sum(v.values()),sum(sum(h.values()) for h in b.values())) for c,v in b.items()}
    assert study.quantiles(study.reweight(b,identity))==study.quantiles(study.combine(b))


@pytest.mark.parametrize('missing',[True,False])
def test_missing_or_empty_group_fails(missing):
    c={k:Counter({100:1}) for k in study.CELLS}
    if missing: del c[study.CELLS[0]]
    else: c[study.CELLS[0]]=Counter()
    with pytest.raises(ValueError,match='missing required'): study.reference_mix({2003:c})


@pytest.mark.parametrize('code,expected',[('18','under40'),('35','under40'),('40','40-49'),
    ('45','40-49'),('50','50-59'),('55','50-59'),('60','60+'),('80','60+'),('',None),('M',None),('M<',None)])
def test_age_map(code,expected):
    assert study.band(code)==expected
    assert independent.independent_band(code)==expected


def test_new_category_rejected():
    with pytest.raises(ValueError,match='unreviewed'):study.band('42')


@pytest.mark.parametrize('bad',[{}, {60:0},{60:-1},{True:1}])
def test_invalid_distribution(bad):
    with pytest.raises(ValueError):study.quantiles(bad)


def test_constant_and_year_perfect_fit_are_undefined():
    assert study.pearson([1,1,1],[2,3,4])['value'] is None
    assert study.pearson([1,2,3],[4,4,4])['value'] is None
    assert study.year_adjusted([2003,2004,2005],[1,2,3],[3,5,4])['value'] is None
    assert independent.partial_r([2003,2004,2005],[1,2,3],[3,5,4]) is None


def test_year_adjustment_hand_orthogonal_residuals():
    # Centered years [-1.5,-.5,.5,1.5]. e1=[1,-1,-1,1], e2=[1,-3,3,-1]
    # Both residual vectors are orthogonal to year and each other; raw r is nonzero.
    years=[0,1,2,3]; x=[1,0,1,4]; y=[1,-1,7,5]
    assert study.pearson(x,y)['value'] != 0
    assert study.year_adjusted(years,x,y)['value']==pytest.approx(0,abs=1e-12)
    assert independent.partial_r(years,x,y)==pytest.approx(0,abs=1e-12)


def sample_rows():
    return [{'year':y,'view':v,'median_temp_c':i+1,
        **{k+'_pace_s_per_km':2*(i+1) for k in study.METRICS}}
        for i,y in enumerate(study.YEARS) for v in study.VIEWS]


def test_omission_excludes_entire_edition():
    rows=sample_rows(); rows[-3]['median_pace_s_per_km']=-50
    result=study.associations(rows)
    s=result['series']['whole_capture:median']
    assert s['pearson_r']['value'] != 1
    last=next(r for r in s['leave_one_out'] if r['omitted_year']==2018)
    assert last['edition_count']==15
    assert last['value']==pytest.approx(1)
    assert len(s['leave_one_out'])==16
    assert result['reference_mix_frozen_for_omissions'] is True


def test_population_context_validation():
    rows=sample_rows();rows.pop()
    with pytest.raises(ValueError,match='exactly once'):study.associations(rows)
    rows=sample_rows(); rows[0]['median_temp_c']+=1
    with pytest.raises(ValueError,match='different weather'):study.associations(rows)


def test_existing_output_and_bad_config_preserved(tmp_path):
    out=tmp_path/'old';out.mkdir();marker=out/'keep';marker.write_text('retain')
    with pytest.raises(FileExistsError):study.run(tmp_path/'missing.json',out)
    assert marker.read_text()=='retain'
    cfg=tmp_path/'bad.json';cfg.write_text('{"schema":"wrong"}')
    fresh=tmp_path/'new'
    with pytest.raises((ValueError,KeyError)):study.run(cfg,fresh)
    assert not fresh.exists()


def test_altered_hash_stops_before_output(tmp_path):
    config=json.loads((Path(__file__).resolve().parents[2]/'analysis/berlin/fixed-mix.json').read_text())
    parent=tmp_path/'parent.json';parent.write_text('{}')
    config['parent_configuration']='parent.json';config['parent_configuration_sha256']='0'*64
    method=tmp_path/'method.json';method.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='hash changed'):study.run(method,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_export_altered_bytes_rejected(tmp_path):
    r={'validation_status':'accepted','gender_raw':'female','time_raw':'01:00:00',
       'duration_s':3600,'age_category_raw':'40'}
    p=tmp_path/'one.ndjson';p.write_text(json.dumps(r)+'\n')
    with pytest.raises(ValueError,match='export hash changed'):independent.read(p,'0'*64)
