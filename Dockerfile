# ISAAC metadata assistant: single image serving the API and the built SPA.
# Deployed to k8s at https://isaac.slac.stanford.edu${BASE_PATH}/ (Flux GitOps).
#
# Data governance: COPY is an explicit allowlist. examples/, drafts/, records/,
# and graphify-out/ must NEVER be added — the image contains only the vendored
# public schema, committed synthetic fixtures, code, one committed sanitized
# Project Memory snapshot (apps/api/isaac_api/data/memory-snapshot.json, P24.9 —
# metadata/provenance only, no file contents; ships inside `COPY apps/api/`),
# and the compiled frontend bundle (built from apps/web/ sources only).

# --- Stage 1: frontend build ---------------------------------------------------
FROM node:24-slim AS web

ARG BASE_PATH=/krish

WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
# Bake the deploy prefix into asset URLs, the router basename, and the
# same-origin API base. Runtime ISAAC_BASE_PATH below must match.
RUN VITE_BASE_PATH="${BASE_PATH}/" VITE_API_BASE="${BASE_PATH}/api" npm run build

# --- Stage 2: backend + static bundle -------------------------------------------
FROM python:3.11-slim

ARG BASE_PATH=/krish
ARG ISAAC_BUILD_COMMIT=""

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
COPY apps/api/ apps/api/
COPY schema/ schema/
COPY tests/fixtures/synthetic/ tests/fixtures/synthetic/
# The Record Verification corpus. These ten records are copied verbatim from the
# PUBLIC upstream ISAAC `examples/` directory (`schema/PROVENANCE.md`) and are
# already published on GitHub, so shipping them in the image discloses nothing.
# Without this line the deployed pod finds no corpus and reports `unavailable`.
COPY tests/fixtures/official/ tests/fixtures/official/
COPY scripts/check_graphify_freshness.py scripts/check_graphify_freshness.py

RUN pip install --no-cache-dir ".[api]"

COPY --from=web /web/dist /app/apps/web/dist

ENV PYTHONUNBUFFERED=1 \
    ISAAC_BASE_PATH=${BASE_PATH} \
    ISAAC_STATIC_DIR=/app/apps/web/dist \
    ISAAC_BUILD_COMMIT=${ISAAC_BUILD_COMMIT}

EXPOSE 8000

CMD ["sh", "-c", "uvicorn isaac_api.app:app --app-dir apps/api --host 0.0.0.0 --port ${PORT:-8000}"]
