# Phase 20 — Deploy the Synthetic UI Prototype for Sharing (Design)

Date: 2026-07-11
Status: approved by user (amendments: Railway volume, frontend access
protection, shared-secret API auth in Phase 20, GitHub-connected auto-deploys)

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
- **Shared-secret API authentication** (moved into Phase 20 because the
  persistent volume makes unauthenticated write endpoints worth closing):
  a small middleware in the presentation layer (`apps/api/isaac_api`)
  requires `Authorization: Bearer <key>` on every `/api` route except
  `GET /api/health` (kept open for Railway health checks; it exposes only a
  liveness/mode banner). The key comes from env var `ISAAC_UI_API_KEY`.
  **If the var is unset, auth is disabled** — local dev remains
  byte-identical with zero configuration. The middleware must not intercept
  CORS preflight (`OPTIONS`) requests. It adds no validation logic, never
  touches the truth plane, and does not change validation/audit/export
  semantics — an unauthenticated request is rejected before reaching any
  route. Covered by tests (401 without key, success with key, health open,
  disabled when unset).

## Frontend on Vercel

- Vercel project rooted at `apps/web`, framework Vite, output `dist/`.
- `apps/web/vercel.json` with a SPA rewrite (all routes → `/index.html`) so
  BrowserRouter deep links (e.g. `/record/:id/evidence`) don't 404.
- `VITE_API_BASE` set in Vercel project env to
  `https://<railway-backend-domain>/api` — inlined at build time. No
  deployment URLs hardcoded in the repo.
- `VITE_API_KEY` set in Vercel project env; the frontend API client
  (`apps/web/src/lib/api.ts`) attaches it as `Authorization: Bearer` on
  every request **when present**. Unset locally → no header → matches the
  auth-disabled local backend. Honest caveat: a build-time key is visible in
  the served JS bundle, so it is exactly as secret as frontend access —
  which is the sharing boundary anyway (deployment protection gates the
  bundle). This is nuisance-abuse prevention for a synthetic demo, not
  cryptographic access control.
- **Deployment protection enabled** (Vercel Deployment Protection — Vercel
  Authentication tier, or the closest equivalent available on the account's
  plan) so the demo is not publicly discoverable while iterating. Protection
  is a platform toggle, not code — removable later without code changes.

## Known limitations (stated honestly)

- The Railway backend domain is directly reachable, but every route except
  `GET /api/health` requires the bearer key. Residual exposure: the health
  banner (liveness + mode string) is public, and the key itself lives in the
  frontend JS bundle, so anyone who can view the (protection-gated) frontend
  can extract it. Both are accepted for a synthetic demo; rotating the key
  is an env-var change + frontend rebuild.
- No rate limiting on write endpoints — key holders could still spam demo
  runs. Deferred to Phase 21 alongside volume-size monitoring.

## Environment variables

| Variable | Where | Value | Purpose |
|---|---|---|---|
| `ISAAC_UI_WORKSPACE` | Railway | `/data/isaac-workspace` (volume mount) | Persistent synthetic workspace |
| `ISAAC_UI_CORS_ORIGINS` | Railway | `https://<vercel-frontend-domain>` (+ localhost list for convenience) | Browser access from deployed frontend |
| `ISAAC_UI_API_KEY` | Railway | generated random token (unset locally → auth disabled) | Shared-secret bearer auth |
| `PORT` | Railway (provided by platform) | injected | Container listen port |
| `VITE_API_BASE` | Vercel | `https://<railway-backend-domain>/api` | Frontend → backend origin (build-time) |
| `VITE_API_KEY` | Vercel | same token as `ISAAC_UI_API_KEY` | Frontend attaches bearer header (build-time) |

## Deploy model: GitHub-connected auto-deploys

Both platforms track the GitHub repository
(`Krish-Verma/isaac-metadata-assistant`, branch `main`) rather than relying
on CLI pushes. Manual CLI deploys remain available during development, but
the deployed environments follow the repo automatically:

- **Railway**: service created from the GitHub repo, building with the
  repo-root Dockerfile; auto-deploy on push to `main`. Requires the user to
  authorize the Railway GitHub App on the repo (one-time browser step).
- **Vercel**: project created from the GitHub repo with root directory
  `apps/web`; production deploys track `main`, PR branches get preview
  deploys. Requires the user to authorize the Vercel GitHub App (one-time
  browser step).

### Sequence

1. Implement code/config changes (subagent), verify locally (pytest, vitest,
   build). Commit to `main` and push (push is the deploy trigger from then
   on).
2. Interactive logins (user): `railway login`, `vercel login`, plus GitHub
   App authorizations for both platforms when prompted.
3. Create Railway project/service from the GitHub repo; attach volume; set
   `ISAAC_UI_WORKSPACE`, `ISAAC_UI_API_KEY`; first deploy; get backend
   domain.
4. Create Vercel project from the GitHub repo (root `apps/web`); set
   `VITE_API_BASE`, `VITE_API_KEY`; deploy; get frontend domain; enable
   deployment protection.
5. Set `ISAAC_UI_CORS_ORIGINS` on Railway to the Vercel domain; redeploy
   backend.
6. End-to-end verification (below). Final docs commit → push → confirm both
   platforms auto-deploy it.

## Verification checklist (deployed)

- Frontend loads (through protection) and all screens render.
- `GET /api/health` returns healthy on the Railway domain.
- Run Synthetic Demo works end-to-end (draft-only and full).
- Pending → answers → export works; artifacts (record + sidecar) readable.
- Validation and audit return the same verdicts as the local demo.
- Evidence Trail renders.
- `POST /api/uploads` still returns 403 (no real-data path enabled).
- API auth: request without bearer key → 401; with key → succeeds;
  `GET /api/health` open; local backend with var unset requires no key.
- Deployment protection actually blocks an unauthenticated visitor.
- Volume persistence: demo state survives a service restart.
- Auto-deploy: a push to `main` triggers deploys on both platforms.
- Local dev flow unchanged (default CORS/workspace/auth behavior identical).

## Constraints preserved

Synthetic-only (bundled fixtures only); no real-data upload (403 seam
untouched); no portal parity; no Graphify validation (`/api/graph/status`
simply reports unavailable in the container — memory plane only); assistant
subordinate; deterministic validation/audit unchanged; **no changes to the
truth plane** (`src/isaac_records/*`, `schema/`).

## Out of scope

Rate limiting and volume-size monitoring (Phase 21), custom domains,
performance work, portal validator integration, real/sanitized data.

## Workflow

Fable 5 orchestrates only; implementation is delegated to Opus 4.8 / Sonnet 5
subagents in small reviewable slices; Graphify may inform discovery but every
change is verified against actual files and tests.
