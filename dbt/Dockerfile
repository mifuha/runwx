FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DBT_LOG_PATH=/tmp/dbt-logs \
    DBT_TARGET_PATH=/tmp/dbt-target \
    HOME=/tmp

WORKDIR /app/dbt
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY dbt_project.yml profiles.yml ./
COPY models/ models/
COPY macros/ macros/
COPY tests/ tests/
USER 10001:10001
ENTRYPOINT ["dbt"]
CMD ["--no-partial-parse", "parse", "--profiles-dir", ".", "--target", "local"]
