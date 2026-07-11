# Phase 20 — Deploy the Synthetic UI Prototype for Sharing (Design)

Date: 2026-07-11
Status: approved by user (with volume + access-protection amendments)

## Context

Phases 19A–19F produced a working local-only UI prototype: a Vite/React SPA
(`apps/web`) talking to a FastAPI presentation layer (`apps/api/isaac_api`)
that calls the deterministic truth core (`src/isaac_records`) in-process.
Phase 20 is approved: host this synthetic demo so it can be shared, without
compromising the architecture or any project constraint.

The deployment question was investigated before choosing hosts:

- **The backend cannot run cleanly on Vercel serverless.** It persists
  experiment state to local disk across requests (`workspace.py` writes
  `experiment.json`, exported records, and evidence sidecars under
  `ISAAC_UI_WORKSPACE`, then reads them back on later requests, e.g.
  `GET /api/experiments/{id}/artifacts` after `POST .../export`). Vercel
  functions have ephemeral, per-instance filesystems, so cross-request state
  would vanish or diverge between instances. Making it fit would require
  rewriting the workspace store for blob/DB storage — an awkward serverless
  workaround explicitly ruled out.
- **The frontend is a clean static Vite SPA** and is Vercel-ready with a SPA
  rewrite and one build-time env var (`VITE_API_BASE`).

## Decision: split hosting

| Piece | Host | Form |
|---|---|---|
| React frontend (`apps/web`) | Vercel | Static Vite build (`dist/`), SPA rewrite, deployment protection enabled |
| FastAPI backend (`apps/api`) | Railway | Single always-on container built from a Dockerfile, with a Railway Volume |

## Backend on Railway

- **Dockerfile build** (not Nixpacks auto-detect): deterministic, reviewable,
  and copies *only* what the API needs — `pyproject.toml`, `src/`,
  `apps/api/`, `schema/`, `tests/fixtures/synthetic/`,
  `scripts/check_graphify_freshness.py`. It must **not** copy `examples/`
  (gitignored, potentially sensitive), `drafts/`, `records/`, or
  `graphify-out/`. Data governance holds inside the image.
- **Binding**: uvicorn started by the container CMD with
  `--host 0.0.0.0 --port $PORT`. No code change for binding; the "loopback
  only" note in `app.py`'s docstring is updated to reflect that remote
  binding is a deployment concern.
- **CORS**: origins become env-driven via `ISAAC_UI_CORS_ORIGINS`
  (comma-separated), defaulting to the current hardcoded localhost list so
  local dev behavior is unchanged. Covered by a small test. This is the
  presentation layer (`apps/api/isaac_api/app.py`), not the truth path.
- **Health check**: Railway health check on `GET /api/health`.
- **Railway Volume**: mounted at a fixed path (e.g. `/data/isaac-workspace`)
  with `ISAAC_UI_WORKSPACE` pointing at it (the env var already exists in
  `workspace.py`; no code change). The volume stores only synthetic demo
  workspace artifacts: experiment state, exported demo records, evidence
  sidecars. No real data, no Graphify indexes. Demo state survives
  redeploys/restarts.
- **Reset procedure**: `railway ssh` into the service and remove the
  workspace directory contents; the backend auto-seeds a fresh synthetic
  experiment on next access. Documented in `docs/deployment.md`. No reset
  endpoint is added (keeps API surface unchanged).

## Frontend on Vercel

- Vercel project rooted at `apps/web`, framework Vite, output `dist/`.
- `apps/web/vercel.json` with a SPA rewrite (all routes → `/index.html`) so
  BrowserRouter deep links (e.g. `/record/:id/evidence`) don't 404.
- `VITE_API_BASE` set in Vercel project env to
  `https://<railway-backend-domain>/api` — inlined at build time. No
  deployment URLs hardcoded in the repo.
- **Deployment protection enabled** (Vercel Deployment Protection — Vercel
  Authentication tier, or the closest equivalent available on the account's
  plan) so the demo is not publicly discoverable while iterating. Protection
  is a platform toggle, not code — removable later without code changes.

## Known limitation (stated honestly)

Deployment protection covers the **frontend URL**. The Railway backend API
remains directly reachable (CORS restricts browsers, not curl). All content
it serves is synthetic, uploads are hard-403, and there is no mutation of
anything sensitive — accepted for the iteration phase. If mentors want the
API itself gated later, that is a follow-up decision (e.g. a shared-secret
header), deliberately out of scope now.

## Environment variables

| Variable | Where | Value | Purpose |
|---|---|---|---|
| `ISAAC_UI_WORKSPACE` | Railway | `/data/isaac-workspace` (volume mount) | Persistent synthetic workspace |
| `ISAAC_UI_CORS_ORIGINS` | Railway | `https://<vercel-frontend-domain>` (+ localhost list for convenience) | Browser access from deployed frontend |
| `PORT` | Railway (provided by platform) | injected | Container listen port |
| `VITE_API_BASE` | Vercel | `https://<railway-backend-domain>/api` | Frontend → backend origin (build-time) |

## Deploy sequence

1. Implement code/config changes (subagent), verify locally (pytest, vitest,
   build).
2. Interactive logins (user): `railway login`, `vercel login`.
3. Deploy backend to Railway (project + service + volume + env), get domain.
4. Deploy frontend to Vercel with `VITE_API_BASE`, get domain; enable
   deployment protection.
5. Set `ISAAC_UI_CORS_ORIGINS` on Railway to the Vercel domain; redeploy.
6. End-to-end verification (below). Commit docs/config.

## Verification checklist (deployed)

- Frontend loads (through protection) and all screens render.
- `GET /api/health` returns healthy on the Railway domain.
- Run Synthetic Demo works end-to-end (draft-only and full).
- Pending → answers → export works; artifacts (record + sidecar) readable.
- Validation and audit return the same verdicts as the local demo.
- Evidence Trail renders.
- `POST /api/uploads` still returns 403 (no real-data path enabled).
- Deployment protection actually blocks an unauthenticated visitor.
- Volume persistence: demo state survives a service restart.
- Local dev flow unchanged (default CORS/workspace behavior identical).

## Constraints preserved

Synthetic-only (bundled fixtures only); no real-data upload (403 seam
untouched); no portal parity; no Graphify validation (`/api/graph/status`
simply reports unavailable in the container — memory plane only); assistant
subordinate; deterministic validation/audit unchanged; **no changes to the
truth plane** (`src/isaac_records/*`, `schema/`).

## Out of scope

Backend API authentication, custom domains, CI/CD auto-deploy pipelines,
performance work, portal validator integration, real/sanitized data.

## Workflow

Fable 5 orchestrates only; implementation is delegated to Opus 4.8 / Sonnet 5
subagents in small reviewable slices; Graphify may inform discovery but every
change is verified against actual files and tests.
