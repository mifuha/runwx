"""Build a reproducible Composer DAG ZIP from committed, allowlisted files."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import zipfile


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def build_bundle(root, revision="HEAD"):
    revision = git(root, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
    paths = git(root, "ls-tree", "-r", "--name-only", revision).decode().splitlines()
    payloads = {}
    for path in paths:
        if path == "orchestration/dags/runwx_historical.py":
            destination = "dags/runwx_historical.py"
        elif path.startswith("orchestration/runwx_airflow/") and path.endswith(".py"):
            destination = "dags/" + path.removeprefix("orchestration/")
        elif path.startswith("src/runwx/") and path.endswith(
                (".py", "result_rows.schema.json", "gnr_sample_rows.schema.json", "gnr_editions.json")):
            destination = "dags/" + path.removeprefix("src/")
        elif path == "dbt/stage_runner.py":
            destination = "dags/stage_runner.py"
        elif path == "orchestration/folkestone-2019.json":
            destination = "folkestone-2019.json"
        else:
            continue
        payloads[destination] = git(root, "show", f"{revision}:{path}")
    required = {"dags/runwx_historical.py", "dags/stage_runner.py",
                "dags/runwx_airflow/tasks.py", "dags/runwx_airflow/config.py",
                "dags/runwx/adapters/bigquery/result_rows.schema.json", "folkestone-2019.json"}
    if not required <= payloads.keys():
        raise ValueError("revision is missing required orchestration files")
    # Composer config explicitly selects regexp syntax. Imports are still allowed.
    payloads["dags/.airflowignore"] = b"runwx/\nrunwx_airflow/\nstage_runner\\.py\n"
    manifest = {"source_revision": revision, "files": {
        name: sha256(payload).hexdigest() for name, payload in sorted(payloads.items())}}
    payloads["bundle-manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(payloads.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, payload)
    return stream.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_bundle(Path(__file__).resolve().parents[1], args.revision)
    with args.output.open("xb") as output:
        output.write(payload)
    print(f"{sha256(payload).hexdigest()}  {args.output}")
