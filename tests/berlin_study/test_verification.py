import copy
from pathlib import Path
import pytest
from pilot import load_configuration
from verify import check_directory, coefficient, verify_correlations
from performance import describe


def test_retained_public_results_independently_reconcile():
    result = check_directory(Path(__file__).resolve().parents[2] / 'docs/evidence/berlin-case-study')
    assert result['performance']['correlations_checked'] == 136
    assert result['whole']['correlations_checked'] == 51


def test_independent_control_and_constant():
    assert coefficient([(1,1),(2,3),(3,2)]) == pytest.approx(.5)
    assert coefficient([(1,2),(1,3),(1,4)]) is None


def test_changed_coefficient_and_duplicate_omission_rejected():
    rows = [{'year':2003+i,'series':'fixture','median_temp_c':i,'median_pace_s_per_km':2*i+3} for i in range(16)]
    result = describe(rows)
    altered = copy.deepcopy(result)
    altered['series']['fixture']['pearson_r']['value'] = .9
    with pytest.raises(ValueError, match='correlation differs'):
        verify_correlations(rows, altered)
    altered = copy.deepcopy(result)
    altered['series']['fixture']['leave_one_out'][1] = altered['series']['fixture']['leave_one_out'][0]
    with pytest.raises(ValueError, match='every edition'):
        verify_correlations(rows, altered)


def test_paths_resolve_relative_to_config_even_from_another_cwd(tmp_path, monkeypatch):
    import json
    folder = tmp_path / 'config'; folder.mkdir()
    config = {k:'inputs/file' for k in ('race_csv','catalog','baseline','retained_check_manifest','retained_native_results')}
    config['edition_inputs'] = [{k:'inputs/edition' for k in ('weather_json','capture','report','weather_csv')}]
    path = folder / 'study.json'; path.write_text(json.dumps(config))
    monkeypatch.chdir(tmp_path)
    loaded = load_configuration(path)
    assert loaded['race_csv'] == str(folder / 'inputs/file')
    assert loaded['edition_inputs'][0]['capture'] == str(folder / 'inputs/edition')
