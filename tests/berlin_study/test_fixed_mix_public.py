from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
import check_fixed_mix
import fixed_mix

ROOT=Path(__file__).resolve().parents[2]
PUBLIC=ROOT/'docs/evidence/berlin-fixed-mix'


def test_published_aggregate_check_without_private_inputs():
    actual=check_fixed_mix.check_public(PUBLIC)
    assert actual['accepted']==541730
    assert actual['age_eligible']==541659
    assert actual['independent_correlations']==204
    assert actual['independent_year_sensitivities']==3


def mutate(tmp_path,name,change):
    copied=tmp_path/'evidence'
    shutil.copytree(PUBLIC,copied)
    path=copied/name
    data=json.loads(path.read_bytes());change(data)
    path.write_text(json.dumps(data))
    # Refresh the file digest so the independent semantic check has to find it.
    manifest=json.loads((copied/'manifest.json').read_bytes())
    manifest['files'][name]=sha256(path.read_bytes()).hexdigest()
    (copied/'manifest.json').write_text(json.dumps(manifest))
    return copied


def test_altered_coefficient_rejected_even_with_updated_digest(tmp_path):
    copied=mutate(tmp_path,'associations.json',lambda d:d['series']['fixed_mix:median']['pearson_r'].update(value=.5))
    with pytest.raises(ValueError,match='independent numerical'):
        check_fixed_mix.check_public(copied)


def test_duplicate_omitted_year_rejected(tmp_path):
    def change(d):
        rows=d['series']['fixed_mix:median']['leave_one_out']
        rows[1]=rows[0]
    copied=mutate(tmp_path,'associations.json',change)
    with pytest.raises(ValueError,match='omitted-edition coverage'):
        check_fixed_mix.check_public(copied)


def test_changed_reference_weight_rejected(tmp_path):
    copied=mutate(tmp_path,'reference-mix.json',lambda d:d['groups'][0].update(numerator=1))
    with pytest.raises(ValueError,match='reference proportions'):
        check_fixed_mix.check_public(copied)


def test_missing_public_file_or_private_path_rejected(tmp_path):
    copied=tmp_path/'evidence';shutil.copytree(PUBLIC,copied)
    (copied/'summaries.csv').write_text('changed')
    with pytest.raises(ValueError,match='hash changed'):
        check_fixed_mix.check_public(copied)
    data=json.loads((copied/'manifest.json').read_text());data['private']='/home/example/data'
    (copied/'manifest.json').write_text(json.dumps(data))
    with pytest.raises(ValueError,match='private path'):
        check_fixed_mix.check_public(copied)


def test_fixed_mix_configuration_relative_to_its_file(tmp_path,monkeypatch):
    folder=tmp_path/'config';folder.mkdir()
    parent=folder/'parent.json';parent.write_text('{}')
    method=json.loads((ROOT/'analysis/berlin/fixed-mix.json').read_bytes())
    method.update(parent_configuration='parent.json',parent_configuration_sha256=sha256(parent.read_bytes()).hexdigest())
    path=folder/'fixed-mix.json';path.write_text(json.dumps(method))
    monkeypatch.chdir(tmp_path)
    _,resolved=fixed_mix.load_method(path)
    assert resolved==parent


def test_cli_audit_guard_without_affecting_other_tests():
    code="import sys,socket;sys.path.insert(0,sys.argv[1]);from offline_guard import install;install();socket.socket()"
    result=subprocess.run([sys.executable,'-B','-c',code,str(ROOT/'analysis/berlin')],capture_output=True,text=True)
    assert result.returncode!=0
    assert 'offline pilot blocks socket.__new__' in result.stderr
