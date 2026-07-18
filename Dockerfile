# ISAAC synthetic demo backend (Phase 20). Built by Railway from GitHub.
#
# Data governance: COPY is an explicit allowlist. examples/, drafts/, records/,
# and graphify-out/ must NEVER be added — the image contains only the vendored
# public schema, committed synthetic fixtures, code, and one committed sanitized
# Project Memory snapshot (apps/api/isaac_api/data/memory-snapshot.json, P24.9 —
# metadata/provenance only, no file contents; ships inside `COPY apps/api/`).

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
COPY apps/api/ apps/api/
COPY schema/ schema/
COPY tests/fixtures/synthetic/ tests/fixtures/synthetic/
COPY scripts/check_graphify_freshness.py scripts/check_graphify_freshness.py

RUN pip install --no-cache-dir ".[api]"

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Railway injects PORT. Remote binding is a deployment concern; local dev keeps 127.0.0.1.
CMD ["sh", "-c", "uvicorn isaac_api.app:app --app-dir apps/api --host 0.0.0.0 --port ${PORT:-8000}"]
