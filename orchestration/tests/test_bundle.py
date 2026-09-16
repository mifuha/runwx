"""Deployment checks: no private files, reproducible bytes, independent imports."""

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from build_bundle import build_bundle


ROOT = Path(__file__).resolve().parents[2]


def test_bundle_is_reproducible_and_excludes_local_files():
    payload = build_bundle(ROOT)
    assert build_bundle(ROOT) == payload
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
        assert "dags/runwx/adapters/bigquery/result_rows.schema.json" in names
        assert all(name.startswith("dags/") or name in {"bundle-manifest.json", "folkestone-2019.json"}
                   for name in names)
        assert not any(part in name for name in names for part in
                       (".git/", "data/", "AGENTS", "RUNWX_", "tfstate", "__pycache__", "tests/"))
        manifest = json.loads(archive.read("bundle-manifest.json"))
        assert manifest["files"] == {name: sha256(archive.read(name)).hexdigest()
                                     for name in names if name != "bundle-manifest.json"}


def test_bundle_imports_away_from_checkout_and_rejects_corruption(tmp_path):
    bundle = tmp_path / "bundle"
    with zipfile.ZipFile(BytesIO(build_bundle(ROOT))) as archive:
        archive.extractall(bundle)
    env = {**os.environ, "AIRFLOW_HOME": str(tmp_path / "airflow-home"),
           "AIRFLOW__CORE__LOAD_EXAMPLES": "False", "AIRFLOW__CORE__DAG_IGNORE_FILE_SYNTAX": "regexp",
           "AIRFLOW__CORE__HOSTNAME_CALLABLE": "socket.gethostname"}
    env.pop("PYTHONPATH", None)
    command = [sys.executable, "-I", str(ROOT / "orchestration/smoke_bundle.py"), str(bundle)]
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "imported_offline"' in result.stdout
    (bundle / "dags/runwx/adapters/bigquery/result_rows.schema.json").write_text("{}")
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert "bundle files differ" in result.stderr
