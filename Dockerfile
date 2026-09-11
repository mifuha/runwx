# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements/ requirements/
RUN python -m pip install --no-cache-dir --no-deps --only-binary=:all: \
    -r requirements/container.lock -r requirements/build.lock

COPY pyproject.toml setup.cfg ./
COPY src/runwx/ ./src/runwx/
# A package build must use the installed tools and cannot resolve new dependencies.
RUN --network=none python -m pip install --no-cache-dir --no-deps --no-build-isolation . \
    && python -m pip check

ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/mifuha/runwx" \
      org.opencontainers.image.revision="${VCS_REF}"

USER 10001:10001
ENTRYPOINT ["python", "-m", "runwx"]
CMD ["--help"]
