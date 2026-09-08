FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml setup.cfg ./
COPY src/runwx/ ./src/runwx/
RUN python -m pip install --no-cache-dir .

ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/mifuha/runwx" \
      org.opencontainers.image.revision="${VCS_REF}"

USER 10001:10001
ENTRYPOINT ["python", "-m", "runwx"]
CMD ["--help"]
