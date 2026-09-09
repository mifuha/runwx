# Local container report

This packages the existing `python -m runwx` command. Race and weather files are
mounted when it runs; they are not copied into the image. There is no cloud
deployment or image publishing in this step.

## Build

Use Docker Engine in Ubuntu/WSL. Run from the repository root. Building can
download the Python base image and packages; report execution will have no network.
Docker Engine is installed as a local system service using the
[official Ubuntu repository](https://docs.docker.com/engine/install/ubuntu/).
The commands below use `sudo`; membership of the Docker group is not required.

```bash
sudo docker build --build-arg VCS_REF="$(git rev-parse HEAD)" -t runwx:offline .
```

The image installs locked dependencies, then the package from `setup.cfg`, and
starts the same CLI. It runs
as user `10001:10001`. The build context excludes saved data, `.git`, `.venv`,
local configuration and the unrelated practice script under `src/`.
The Python base image is pinned by digest. Updating that digest should be followed
by another build and output comparison.

## Run and compare

Activate the existing Python environment as in the [quickstart](../README.md#quickstart).
These commands use bash and create a new temporary folder for the outputs.

```bash
runwx_check_dir=$(mktemp -d /tmp/runwx-container-check.XXXXXX)

python -m runwx report \
  --race-html data/raw/eventrac/lydd_half_2022.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id lydd-half-marathon --distance-m 21097 \
  --timezone Europe/London --weather-kind synthetic \
  > "$runwx_check_dir/local.json" &&

sudo docker run --rm --network none --read-only \
  --mount "type=bind,source=$PWD/data,target=/app/data,readonly" \
  runwx:offline report \
  --race-html data/raw/eventrac/lydd_half_2022.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id lydd-half-marathon --distance-m 21097 \
  --timezone Europe/London --weather-kind synthetic \
  > "$runwx_check_dir/container.json" &&

cmp "$runwx_check_dir/local.json" "$runwx_check_dir/container.json"
```

`cmp` exits with code 0 and no output when the files are identical. The `&&`
operators stop the comparison if either report command fails. The same relative
input paths are used in both runs so source metadata can match too.

The saved weather is synthetic, as in the [README example](../README.md#example-result).
The data mount and the container filesystem are read-only. Docker removes the
finished container; the image, build cache and temporary reports remain locally.

## Record the environment

```bash
sudo docker image inspect --format '{{.Id}}' runwx:offline
sudo docker run --rm --network none --read-only --entrypoint python \
  runwx:offline --version
sudo docker run --rm --network none --read-only --entrypoint python \
  runwx:offline -m pip freeze
```

Keep the image ID and installed versions with your check results. The revision
label identifies the Git commit supplied at build time; uncommitted edits are
not described by that label. The image ID identifies the resulting image.

The [report dependency lock](../requirements/container.lock) and
[build-tool lock](../requirements/build.lock) fix the installed package versions.
The package itself builds without network access or dependency resolution.
`pip check` fails the build if the installed dependencies do not satisfy the
package metadata. The report itself still does not record code/dependency versions.

## Dependency updates

The image locks target Python 3.12 on Linux/amd64 and include indirect dependencies.
They were captured from the previously validated report and dbt images; their
source image IDs are in the files. The report also pins setuptools and wheel
instead of allowing an isolated build environment to download newer tools.
The [dbt lock](../dbt/requirements.lock) remains separate because its dependency
versions differ from the report's. `setup.cfg` keeps the supported package ranges.

For an intentional update, resolve the changed requirements in a disposable
Python 3.12 Linux environment, run `python -m pip check`, and capture
`python -m pip freeze --all`. Review the full version diff before replacing the
appropriate lock. Omit the local `runwx @ file:...` entry from the report lock;
the Dockerfile builds runwx from this checkout. Keep the two dbt direct pins in
`dbt/requirements.txt` consistent with its lock. Rebuild both affected images and
rerun the offline report comparison or both dbt parse modes before publication.

One dbt dependency needs special handling: PyPI's
[experimental parser 2.0.0rc2](https://pypi.org/project/dbt-core-experimental-parser/2.0.0rc2/)
source package downloads a wheel from the official dbt GitHub release. The lock
pins that Linux/amd64 wheel URL and its upstream SHA-256 directly, preserving the
validated version without running the downloader's build backend. Preserve this
entry when refreshing the freeze; changing architecture needs the corresponding
upstream wheel and a separate check.

These are complete version pins, following pip's
[repeatable-install guidance](https://pip.pypa.io/en/stable/topics/repeatable-installs/).
`--no-deps` prevents unlisted dependencies being installed; `--only-binary=:all:`
requires published wheels so dependency builds cannot fetch extra tooling.
Except for that direct wheel, the locks pin versions rather than artifact hashes.
They do not promise identical image bytes across platforms. Retain image digests
as execution evidence; downloads still depend on PyPI and the upstream release
being available. Only Linux/amd64 is checked in this task.

## Verification status

Checked on 7 September 2026 with Ubuntu 24.04/WSL, Docker Engine 29.8.0 and
Python 3.12.14 in the container (3.12.3 in the local virtual environment):

- The package built and installed successfully in the image.
- One local run and two container runs produced byte-identical JSON: 189 accepted,
  188 weather matches, 1 unmatched. Container runs used no network and read-only inputs.
- The image audit confirmed user 10001, only a loopback network interface, no
  saved data/local configuration, and all 48 installed Python source files matching
  the checkout.

Image ID: `sha256:b341a758fd9b25286130853c742b5a15e64bdeede30e56cef626ac0e247df22b`.
Revision label: `d31a61acbd43afb2e0c12edec7b0152db1d9b237`.
Report SHA-256: `632493bcd0b6c6f9f5848865a9f3cb61b61693d66da7b90afaaa5013c9d74913`.

This build resolved Pydantic 2.13.5, Beautiful Soup 4.15.0, HTTPX 0.27.2 and tzdata
2026.3. These differ from some local versions; output agreement was checked for
the saved demo, not for every supported input. The full Python suite was not run
inside the image. CI, other container platforms and cloud execution were not tested.

See the [cloud report](first-cloud-run.md) for the storage integration and deployed
verification, and [architecture](architecture.md) for the next warehouse milestone.

References: [Docker build guidance](https://docs.docker.com/build/building/best-practices/),
[runtime options](https://docs.docker.com/reference/cli/docker/container/run/),
[network isolation](https://docs.docker.com/engine/network/drivers/none/).
