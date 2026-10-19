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
# THE VENDORED SCHEMA, FOR TYPE-CHECKING ONLY, AND ONLY BECAUSE `npm run build` IS
# `tsc -b && vite build`. `src/__tests__/record-description.test.tsx` imports
# `../../../../schema/isaac_record_v1.json` — deliberately the real document rather
# than a hand-built double, so the test cannot drift from the schema — and from
# `/web/src/__tests__/` that path resolves to `/schema/isaac_record_v1.json`.
# `tsc -b` type-checks `src`, tests included, so WITHOUT this line the image build
# fails `TS2307: Cannot find module` and NO image can be produced. It is invisible to
# every other check: `npm run build` passes in a full checkout, so both the local
# command and CI's `frontend` job are green while the Docker build is impossible.
#
# It does NOT reach the bundle. `vite build` walks the entry graph, which no test file
# is in, and stage 2 below takes only `/web/dist`. The file is the public official
# schema that stage 2 already ships via `COPY schema/`, so this adds no content the
# image did not have and widens no data-governance boundary — but the header's
# "built from apps/web/ sources only" is now one file short of true, which is why this
# says so here rather than leaving it to be discovered.
COPY schema/isaac_record_v1.json /schema/isaac_record_v1.json
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
# What Historical Import reads. Measured 2026-10-12: without these lines the deployed
# pod's `GET /api/imports` answers `available_fixtures: []` and `available_archives: []`
# — both lists are filtered by existence, so an image that left them out offers a
# scientist nothing to read, and nothing reports why. Two directories:
#   * historical_import/ — `historical_import.FIXTURE_DIR`, the two example sources;
#     each file's first line reads "SYNTHETIC FIXTURE";
#   * bl15/semantics/multi_operator_corpus/ — the multi-operator archive. Its readme,
#     notes file and both macros say "SYNTHETIC" in their first line, each SPEC
#     acquisition in a `#C SYNTHETIC FIXTURE` header line, and its per-scan `.dat`
#     exports carry no marker of their own — they are covered by that corpus's row in
#     tests/fixtures/bl15/README.md, which also records the independent review that no
#     sentence of the real archive is reproduced in it.
# NOT COPIED, deliberately: bl15/notes/ (a governance flag on it is pending the owner),
# and bl15/gold/mini_corpus/ — its notes file shares a sentence with bl15/notes/, so it
# waits on the same decision. The mini corpus stays registered and readable locally;
# the image simply does not offer it, because `archive_names()` filters by existence.
# `test_hosted_image_imports.py` parses these lines, fails if the image lacks a
# directory it should carry or carries one it must not, and checks each file's marker.
COPY tests/fixtures/historical_import/ tests/fixtures/historical_import/
COPY tests/fixtures/bl15/semantics/multi_operator_corpus/ tests/fixtures/bl15/semantics/multi_operator_corpus/
COPY scripts/check_graphify_freshness.py scripts/check_graphify_freshness.py

RUN pip install --no-cache-dir ".[api]"

COPY --from=web /web/dist /app/apps/web/dist

ENV PYTHONUNBUFFERED=1 \
    ISAAC_BASE_PATH=${BASE_PATH} \
    ISAAC_STATIC_DIR=/app/apps/web/dist \
    ISAAC_BUILD_COMMIT=${ISAAC_BUILD_COMMIT}

EXPOSE 8000

CMD ["sh", "-c", "uvicorn isaac_api.app:app --app-dir apps/api --host 0.0.0.0 --port ${PORT:-8000}"]
