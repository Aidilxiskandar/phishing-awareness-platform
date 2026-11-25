# syntax=docker/dockerfile:1
# Multi-stage build. Python pinned to a 3.12 patch release on Debian bookworm-slim
# (mature wheel coverage for the whole dependency tree, incl. pydantic-core) rather
# than inheriting the dev box's interpreter. Bump PYTHON_IMAGE deliberately; for
# fully reproducible builds, append an @sha256 digest.
ARG PYTHON_IMAGE=python:3.12.12-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install -r requirements.txt

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL="sqlite:////data/phishing.db"
# Non-root runtime user. /data is pre-created and owned by it so a fresh named
# volume mounted there inherits the right ownership.
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY --from=builder /venv /venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
USER app
EXPOSE 8000
# Probe the health endpoint with stdlib (no curl in slim image).
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)"
# Migrate the schema (fresh, legacy or managed DB) before serving.
CMD ["sh", "-c", "python -m app.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
