"""Check an extracted DAG bundle offline, without repository Python paths."""

import argparse
from hashlib import sha256
import importlib
import json
from pathlib import Path
import socket
import sys


def smoke(root):
    root = root.resolve()
    manifest = json.loads((root / "bundle-manifest.json").read_text())
    actual = {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
              for p in root.rglob("*") if p.is_file() and p != root / "bundle-manifest.json"}
    if actual != manifest["files"]:
        raise ValueError("bundle files differ from the committed manifest")

    def forbidden(*args, **kwargs):
        raise AssertionError("bundle smoke check attempted credentials or network access")

    socket.create_connection = socket.getaddrinfo = forbidden
    import google.auth
    google.auth.default = forbidden
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root / "dags"))
    from airflow.models import DagBag
    from runwx_airflow.config import validate_config
    from runwx_airflow import tasks
    from importlib.resources import files

    dagbag = DagBag(dag_folder=str(root / "dags"), include_examples=False)
    if dagbag.import_errors or set(dagbag.dags) != {"runwx_historical"}:
        raise AssertionError(f"unexpected DAG imports: {dagbag.import_errors}")
    dag = dagbag.dags["runwx_historical"]
    order = ["validate_configuration", "execute_export", "verify_artifacts",
             "load_or_verify_snapshot", "execute_dbt_stage", "verify_execution_evidence"]
    assert set(dag.task_ids) == set(order)
    for upstream, downstream in zip(order, order[1:]):
        assert downstream in dag.get_task(upstream).downstream_task_ids
    assert dag.max_active_runs == dag.max_active_tasks == 1
    assert all(task.retries == 0 for task in dag.tasks)
    validate_config(json.loads((root / "folkestone-2019.json").read_text())["snapshot"])
    json.loads(files("runwx.adapters.bigquery").joinpath("result_rows.schema.json").read_text())
    for name in ("google.cloud.run_v2", "google.cloud.storage", "google.cloud.bigquery"):
        importlib.import_module(name)
    for name, module in list(sys.modules.items()):
        if name == "stage_runner" or name.startswith(("runwx.", "runwx_airflow.")):
            if getattr(module, "__file__", None):
                assert Path(module.__file__).resolve().is_relative_to(root / "dags"), name
    print(json.dumps({"status": "imported_offline", "source_revision": manifest["source_revision"],
                      "python": sys.version.split()[0], "airflow": importlib.import_module("airflow").__version__,
                      "tasks": order}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    smoke(parser.parse_args().directory)
