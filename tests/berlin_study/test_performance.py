from collections import Counter
import json
from pathlib import Path
import pytest
from performance import split,histogram_split,describe


@pytest.mark.parametrize('values,n,top,rest',[
    ([8,1,5,3],2,[1,3],[5,8]),
    ([1,2,2,2,9],3,[1,2,2],[2,9]),
    ([1,1,1,1],2,[1,1],[1,1])])
def test_exact_n_duplicate_and_boundary_ties(values,n,top,rest):
    actual=split(values,n)
    assert actual==(top,rest)
    a,b=histogram_split(Counter(values),n)
    assert a==Counter(top) and b==Counter(rest)
    assert a+b==Counter(values)


@pytest.mark.parametrize('n',[0,-1,True,4,5])
def test_invalid_or_insufficient_group(n):
    with pytest.raises(ValueError):split([1,2,3,4],n)


def test_holding_precedes_selection():
    import pilot
    groups={'female':[],'male':[]}
    for duration,status in [(1,'accepted'),(None,'held'),(4,'accepted'),(2,'accepted')]:
        pilot.add_row(groups,{'gender_raw':'female','duration_s':duration,'validation_status':status})
    assert split(groups['female'],2)==([1,2],[4])
    assert groups['male']==[]


def test_omissions_are_editions_with_known_linear_result():
    rows=[{'year':2003+i,'series':'fixture','median_temp_c':i,'median_pace_s_per_km':2*i+3} for i in range(16)]
    result=describe(rows)['series']['fixture']
    assert result['pearson_r']['value']==pytest.approx(1)
    assert len(result['leave_one_out'])==16
    assert all(r['edition_count']==15 and r['value']==pytest.approx(1) for r in result['leave_one_out'])
    assert result['direction_change_omissions']==[]


def test_undefined_correlation_is_explicit():
    rows=[{'year':2003+i,'series':'fixture','median_temp_c':1,'median_pace_s_per_km':i} for i in range(16)]
    result=describe(rows)['series']['fixture']
    assert result['pearson_r']=={'value':None,'reason':'constant series'}
    assert result['leave_one_out_min'] is None
    json.dumps(result,allow_nan=False)
