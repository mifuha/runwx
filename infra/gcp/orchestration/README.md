# Temporary Airflow environment preparation

This root prepares the [supervised Composer experiment](../../../docs/airflow-live-plan.md).
It has not been applied. It uses its own state and an already bootstrapped, separately
approved orchestration project. It does not create a project or attach billing.
Do not import resources from the parent or historical roots.

`runwx-orchestrator` gets Composer Worker only in that separate project. In the
data project it can invoke the two existing Cloud Run jobs, read their executions
and operations, read the report/dbt evidence prefixes, and query the existing
Folkestone 2019 snapshot. It has no warehouse write role. The report and dbt jobs
keep their own identities and permissions. Operation status reads are project-wide.

The root declares the Composer and Compute APIs, a custom-mode VPC with one
`europe-west1` subnet, runtime identity, environment bucket, small Composer
environment, three custom roles and the required IAM memberships. Composer names
that VPC and subnet explicitly; it does not use the auto-created default network or
its public ingress rules. The custom VPC declares no ingress firewall rules.

The root does not change either existing job or its image. One worker is allowed;
DAG scheduling is manual, with one active run/task and zero retries. These settings
do not enforce a spending cap. The bucket refuses deletion while nonempty; cleanup
stays explicit.

## Offline checks

From this directory:

```bash
terraform init -backend=false -lockfile=readonly -input=false
terraform fmt -check
terraform validate
terraform test
```

The tests use a mocked provider. They check project separation, the explicit custom
network/subnet, exact job/table grants, worker bounds and rejected configuration.
They do not prove live IAM, regional capacity, service-agent readiness or successful
provisioning.

## Committed DAG bundle

From the repository root:

```bash
python3 orchestration/build_bundle.py --revision HEAD --output /tmp/runwx-dags.zip
python3 -m zipfile -e /tmp/runwx-dags.zip /tmp/runwx-dags
```

Use a fresh output path. The ZIP contains only allowlisted files read from that
commit: the DAG, orchestration helpers, shared Python implementation, dbt runner,
result schema and frozen configuration. No working-tree files or private source
data are copied. Its manifest records the source revision and every payload hash.
Upload only `dags/` to the environment's DAG prefix after approval; retain the ZIP,
manifest and configuration with the experiment evidence. There is no upload here.

`orchestration/smoke_bundle.py` checks an extracted bundle without an editable
checkout, credentials or external DNS. It verifies hashes, the six-task dependency
chain, import locations and bundled schema. CI runs it in the existing local
Airflow environment. That is separate from the exact Composer runtime check below.

## Verified Composer runtime

The selected build is `composer-3-airflow-3.1.7-build.10`, which uses Python 3.11.8,
Airflow 3.1.7+composer, Google provider 20.0.0 and httpx 0.28.1 in Google's
[package list](https://docs.cloud.google.com/composer/docs/versions-packages).
Its verified additions are in `orchestration/composer/requirements.txt` and the
example Terraform variables. BeautifulSoup is imported indirectly by the shared
report code. Do not install the local Airflow lock or the full runwx package into
Composer: that package's HTTP capture dependency range differs from Composer's.
The DAG uses the existing Cloud Run jobs for capture/processing, and does not call
the HTTP capture adapter on its worker.

Google's [local Composer tooling](https://docs.cloud.google.com/composer/docs/composer-3/run-local-airflow-environments)
resolves that build to this worker image digest:

```text
sha256:26b5c28576222198433d80b458b2eacd3499439fc4265490e62d220c8f5d1f9d
```

The Dockerfile defaults to that immutable image. To repeat the check from the
repository root:

```bash
docker build -f orchestration/composer/Dockerfile.smoke -t runwx-composer-smoke .
docker run --rm --network none \
  --mount type=bind,src=/tmp/runwx-dags,dst=/bundle,readonly \
  runwx-composer-smoke
```

The check passed offline with Python 3.11.8, Airflow 3.1.7+composer and the expected
six tasks. Its output also reports the exact bundled commit for retained evidence.
`pip check` reported no broken requirements; BeautifulSoup 4.15.0, soupsieve 2.9.2,
httpx 0.28.1 and Pydantic 2.12.5 imported at their expected versions. The first run
also caught a harness error: isolated Python hid Composer's per-user PyPI directory.
The container invocation now uses Composer's normal package path while the smoke
script still proves every `runwx`, `runwx_airflow` and `stage_runner` import comes
from the read-only bundle. This smoke imports code; it does not execute a managed DAG.

The separate project, billing link, regional image and request quotas have been
checked. The first real plan exposed an auto-created default network with public
ingress rules, which led to this explicit network boundary. Regenerate and inspect
the saved real plan after this change. Applying it, uploading the DAG, the three
supervised runs, teardown, and cleanup of the unmanaged default network each remain
inside their explicit review/approval boundaries. No managed execution is claimed
by these offline checks.
