# Phase 20 — Synthetic UI Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host the synthetic UI prototype for sharing — React frontend on Vercel (protection-gated), FastAPI backend on Railway (Dockerfile container + persistent volume + bearer auth), both tracking GitHub `main` via auto-deploys.

**Architecture:** The backend gains two env-driven seams in the presentation layer only (CORS allowlist, shared-secret bearer auth) plus a Dockerfile/railway.json; the frontend gains one optional bearer header and a vercel.json SPA rewrite. The truth plane (`src/isaac_records/*`, `schema/`) is not touched. Deployment state lives on a Railway volume via the existing `ISAAC_UI_WORKSPACE` env var.

**Tech Stack:** FastAPI/Starlette middleware, pytest + TestClient, Vite/React/TypeScript, Vitest, Docker (Railway cloud build — no local Docker), Railway CLI, Vercel CLI.

**Spec:** `docs/superpowers/specs/2026-07-11-phase-20-deployment-design.md`

## Global Constraints

- Truth plane untouched: no changes under `src/isaac_records/`, `schema/`, or to validation/audit/export semantics.
- Synthetic-only: the Docker image must never contain `examples/`, `drafts/`, `records/`, or `graphify-out/`.
- No new dependencies: backend uses only the existing `[api]` extra (`fastapi>=0.110`, `uvicorn>=0.29`, `httpx>=0.27`); frontend adds no npm packages.
- No deployment URLs hardcoded in the repo — all URLs flow through env vars (`ISAAC_UI_CORS_ORIGINS`, `VITE_API_BASE`).
- Local dev behavior byte-identical with zero env vars set: CORS defaults to `http://localhost:5173` + `http://127.0.0.1:5173`; auth disabled when `ISAAC_UI_API_KEY` unset; workspace defaults to `/tmp/isaac-ui-workspace`.
- `POST /api/uploads` stays hard-403; `GET /api/health` stays unauthenticated (Railway health checks).
- Env var names (exact): `ISAAC_UI_CORS_ORIGINS`, `ISAAC_UI_API_KEY`, `ISAAC_UI_WORKSPACE` (Railway); `VITE_API_BASE`, `VITE_API_KEY` (Vercel); `PORT` (injected by Railway).
- Verification commands: `.venv/bin/pytest` (backend), `cd apps/web && npm test` and `npm run build` (frontend).
- Commits per task; do not push until Task 7 says to (push triggers auto-deploys once platforms are connected).
- Tasks 7–9 contain **STOP points** requiring the user's browser/login. Stop exactly there, tell the user what to click, continue after they confirm.

---

### Task 1: Env-driven CORS origins (backend)

**Files:**
- Modify: `apps/api/isaac_api/app.py`
- Test: `apps/api/tests/test_deploy_config.py` (create)

**Interfaces:**
- Consumes: existing `create_app()` factory (`apps/api/isaac_api/app.py:27`); test-client pattern from `apps/api/tests/test_api.py` (tmp `ISAAC_UI_WORKSPACE` + `TestClient(create_app())`).
- Produces: `_cors_origins() -> list[str]` in `app.py` reading `ISAAC_UI_CORS_ORIGINS` (comma-separated, falls back to `DEFAULT_CORS_ORIGINS`). Task 2 modifies the same `create_app()`; Task 2's tests share `test_deploy_config.py` and its `_make_client` helper.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_deploy_config.py`:

```python
"""Deployment-config tests: env-driven CORS + shared-secret bearer auth.

Presentation-layer seams for the hosted synthetic demo (Phase 20). Both seams
default OFF so local dev needs zero configuration and stays byte-identical.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- CORS allowlist -----------------------------------------------------------


def test_cors_default_allows_vite_dev_origin(tmp_path, monkeypatch):
    monkeypatch.delenv("ISAAC_UI_CORS_ORIGINS", raising=False)
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_env_override_replaces_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_CORS_ORIGINS", "https://isaac-demo.vercel.app")
    client = _make_client(tmp_path, monkeypatch)

    allowed = client.get("/api/health", headers={"Origin": "https://isaac-demo.vercel.app"})
    assert allowed.headers["access-control-allow-origin"] == "https://isaac-demo.vercel.app"

    # The default dev origin is NOT silently appended — env fully replaces it.
    blocked = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in blocked.headers


def test_cors_env_supports_comma_separated_list(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "ISAAC_UI_CORS_ORIGINS",
        "https://isaac-demo.vercel.app, http://localhost:5173",
    )
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/test_deploy_config.py -v`
Expected: `test_cors_env_override_replaces_allowlist` and `test_cors_env_supports_comma_separated_list` FAIL (env var ignored; only the hardcoded tuple is honored). `test_cors_default_allows_vite_dev_origin` may already pass — that is fine; it pins the default.

- [ ] **Step 3: Implement env-driven origins in `app.py`**

Replace the constant block (`apps/api/isaac_api/app.py:20-24`) and the `allow_origins` argument (`app.py:35`), and add `import os` after `from __future__ import annotations`:

```python
import os
```

```python
# Default: the Vite dev server origins. Deployed environments override via
# ISAAC_UI_CORS_ORIGINS (comma-separated full origins, e.g. the Vercel domain).
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins() -> list[str]:
    raw = os.environ.get("ISAAC_UI_CORS_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)
```

In `create_app()`, change `allow_origins=list(CORS_ORIGINS)` to `allow_origins=_cors_origins()`.

Update the module docstring (lines 1-10): replace the sentence "It binds 127.0.0.1 by design (no remote listener in v1) and only permits CORS from the Vite dev server (localhost:5173 / 127.0.0.1:5173)." with:

```
By default it permits CORS only from the Vite dev server (localhost:5173 /
127.0.0.1:5173); deployed environments override the allowlist with the
ISAAC_UI_CORS_ORIGINS env var (comma-separated origins). Remote binding is a
deployment concern (the container CMD passes --host 0.0.0.0); local runs keep
127.0.0.1.
```

Note: `CORS_ORIGINS` is referenced nowhere else in the codebase (verified by grep) — renaming to `DEFAULT_CORS_ORIGINS` is safe.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/test_deploy_config.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `.venv/bin/pytest`
Expected: all tests pass (existing `apps/api/tests/test_api.py` exercises the same factory).

- [ ] **Step 6: Commit**

```bash
git add apps/api/isaac_api/app.py apps/api/tests/test_deploy_config.py
git commit -m "Phase 20: env-driven CORS allowlist (ISAAC_UI_CORS_ORIGINS)"
```

---

### Task 2: Shared-secret bearer auth middleware (backend)

**Files:**
- Create: `apps/api/isaac_api/auth.py`
- Modify: `apps/api/isaac_api/app.py` (add middleware in `create_app()`)
- Test: `apps/api/tests/test_deploy_config.py` (append)

**Interfaces:**
- Consumes: `_make_client` helper from Task 1's test file; `create_app()` from Task 1's `app.py`.
- Produces: `ApiKeyAuthMiddleware` (Starlette `BaseHTTPMiddleware` subclass) in `apps/api/isaac_api/auth.py`, reading `ISAAC_UI_API_KEY` at construction. Task 3's frontend header (`Authorization: Bearer <key>`) must match this check exactly.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_deploy_config.py`:

```python
# --- shared-secret bearer auth --------------------------------------------------


def test_auth_disabled_when_key_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/experiments").status_code == 200


def test_auth_rejects_missing_and_wrong_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)

    missing = client.get("/api/experiments")
    assert missing.status_code == 401
    assert missing.json()["error"] == "unauthorized"

    wrong = client.get(
        "/api/experiments", headers={"Authorization": "Bearer not-the-key"}
    )
    assert wrong.status_code == 401


def test_auth_accepts_correct_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    res = client.get(
        "/api/experiments", headers={"Authorization": "Bearer demo-secret"}
    )
    assert res.status_code == 200


def test_health_stays_open_with_auth_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    assert client.get("/api/health").status_code == 200


def test_cors_preflight_passes_with_auth_enabled(tmp_path, monkeypatch):
    """Preflight OPTIONS carries no credentials by spec — auth must not eat it."""
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    res = client.options(
        "/api/experiments",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200


def test_401_carries_cors_headers(tmp_path, monkeypatch):
    """Browsers must see a readable 401, not an opaque CORS failure."""
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/api/experiments", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 401
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/test_deploy_config.py -v`
Expected: `test_auth_rejects_missing_and_wrong_key` and `test_401_carries_cors_headers` FAIL (endpoints return 200 — no auth exists yet). The other new tests pass trivially against the current app; they pin the open paths (health, preflight, correct key, disabled default) so regressions surface later.

- [ ] **Step 3: Create `apps/api/isaac_api/auth.py`**

```python
"""Shared-secret bearer auth for the hosted synthetic demo (Phase 20).

Presentation-layer only: unauthenticated requests are rejected before reaching
any route. Adds no validation logic and never touches the truth plane
(``isaac_records``). Auth is DISABLED when ``ISAAC_UI_API_KEY`` is unset or
empty, so local dev needs zero configuration.

Kept open on purpose:
- ``GET /api/health`` — platform health checks; exposes a liveness banner only.
- ``OPTIONS`` — CORS preflight carries no credentials by spec.
"""

from __future__ import annotations

import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_OPEN_PATHS = frozenset({"/api/health"})


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Require ``Authorization: Bearer <ISAAC_UI_API_KEY>`` on every /api route."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._expected = ""
        key = os.environ.get("ISAAC_UI_API_KEY", "").strip()
        if key:
            self._expected = f"Bearer {key}"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._expected:
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in _OPEN_PATHS:
            return await call_next(request)
        supplied = request.headers.get("authorization", "")
        if supplied and secrets.compare_digest(supplied, self._expected):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "detail": "Missing or invalid API key."},
        )
```

- [ ] **Step 4: Wire the middleware into `create_app()`**

In `apps/api/isaac_api/app.py`, add the import:

```python
from .auth import ApiKeyAuthMiddleware
```

In `create_app()`, add **before** the existing `app.add_middleware(CORSMiddleware, ...)` call:

```python
    # Order matters: Starlette treats the LAST-added middleware as outermost.
    # Auth is added first so CORSMiddleware wraps it — preflight short-circuits
    # in CORS, and auth 401s still get CORS headers the browser can read.
    app.add_middleware(ApiKeyAuthMiddleware)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/test_deploy_config.py -v`
Expected: 9 PASS (3 CORS + 6 auth).

- [ ] **Step 6: Run the full backend suite**

Run: `.venv/bin/pytest`
Expected: all pass — existing `test_api.py` tests run with no `ISAAC_UI_API_KEY` set, so auth stays disabled for them.

- [ ] **Step 7: Commit**

```bash
git add apps/api/isaac_api/auth.py apps/api/isaac_api/app.py apps/api/tests/test_deploy_config.py
git commit -m "Phase 20: shared-secret bearer auth middleware (ISAAC_UI_API_KEY)"
```

---

### Task 3: Frontend bearer header (api.ts)

**Files:**
- Modify: `apps/web/src/lib/api.ts` (the `request()` helper, `api.ts:58-72`)
- Test: `apps/web/src/__tests__/api.test.ts` (append a describe block)

**Interfaces:**
- Consumes: `api.health()` (`api.ts:92`), the `request()` helper (`api.ts:58`).
- Produces: every request carries `Authorization: Bearer <VITE_API_KEY>` **iff** `VITE_API_KEY` is set (build-time env). Must match Task 2's expected header format exactly. The key is read lazily per request (a function, not a module constant) so Vitest's `vi.stubEnv` works with static imports.

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/src/__tests__/api.test.ts` (its imports of `api` and `vi` already exist; note the file already has `afterEach(() => vi.unstubAllGlobals())` — the new block adds env unstubbing locally):

```typescript
describe('bearer auth header', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  function captureFetch(): RequestInit[] {
    const seen: RequestInit[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        seen.push(init ?? {});
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }),
    );
    return seen;
  }

  it('attaches Authorization: Bearer when VITE_API_KEY is set', async () => {
    vi.stubEnv('VITE_API_KEY', 'demo-secret');
    const seen = captureFetch();
    await api.health();
    const headers = seen[0].headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer demo-secret');
  });

  it('sends no Authorization header when VITE_API_KEY is unset', async () => {
    const seen = captureFetch();
    await api.health();
    const headers = seen[0].headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && npx vitest run src/__tests__/api.test.ts`
Expected: `attaches Authorization` FAILS (`headers.Authorization` is `undefined`); the unset-case test passes (pins current behavior).

- [ ] **Step 3: Implement the lazy key read in `api.ts`**

Below the `API_BASE` export (`api.ts:39`), add:

```typescript
/**
 * Optional shared-secret for the deployed demo backend. Read lazily per request
 * (not a module constant) so tests can stub the env. Unset locally → no header,
 * matching the auth-disabled local backend.
 */
function apiKey(): string | undefined {
  const key = (import.meta.env.VITE_API_KEY as string | undefined)?.trim();
  return key ? key : undefined;
}
```

In `request()` (`api.ts:58-72`), extend the headers object — insert the Authorization spread between `Accept` and the `Content-Type` spread:

```typescript
async function request(path: string, init?: RequestInit): Promise<Response> {
  const key = apiKey();
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(key !== undefined ? { Authorization: `Bearer ${key}` } : {}),
        ...(init?.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    });
  } catch {
    // Network-level failure (server not started, connection refused, CORS reject).
    throw new ApiError('The local backend is not reachable.', { unreachable: true });
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run src/__tests__/api.test.ts`
Expected: all pass, including both new tests.

- [ ] **Step 5: Run the full frontend suite and build**

Run: `cd apps/web && npm test && npm run build`
Expected: all suites pass; `tsc -b && vite build` completes with `dist/` output.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/__tests__/api.test.ts
git commit -m "Phase 20: optional bearer header from VITE_API_KEY in API client"
```

---

### Task 4: Dockerfile, .dockerignore, railway.json

**Files:**
- Create: `Dockerfile` (repo root)
- Create: `.dockerignore` (repo root)
- Create: `railway.json` (repo root)

**Interfaces:**
- Consumes: `_find_repo_root()` (`apps/api/isaac_api/workspace.py:35-42`) walks up from the module file until it finds `schema/isaac_record_v1.json` — with `WORKDIR /app` and COPY paths mirroring the repo layout, `REPO_ROOT` resolves to `/app` and fixtures/schema/scripts resolve without code changes.
- Produces: an image Railway builds from GitHub (Task 7). `railway.json` pins the Dockerfile builder and `/api/health` health check.

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
# ISAAC synthetic demo backend (Phase 20). Built by Railway from GitHub.
#
# Data governance: COPY is an explicit allowlist. examples/, drafts/, records/,
# and graphify-out/ must NEVER be added — the image contains only the vendored
# public schema, committed synthetic fixtures, and code.

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
```

- [ ] **Step 2: Create `.dockerignore`**

Defense-in-depth (COPY is already an allowlist; this also keeps caches out of copied trees):

```
**/__pycache__
**/*.pyc
.venv
.git
node_modules
examples
drafts
records
graphify-out
apps/web
```

- [ ] **Step 3: Create `railway.json`**

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 120,
    "restartPolicyType": "ON_FAILURE"
  }
}
```

- [ ] **Step 4: Verify every COPY source exists and no forbidden path is copied**

Run:
```bash
ls pyproject.toml src apps/api schema/isaac_record_v1.json \
   tests/fixtures/synthetic/mock_campaign.csv \
   tests/fixtures/synthetic/raw_scan_listing.txt \
   tests/fixtures/synthetic/xanes_completion_answers.json \
   scripts/check_graphify_freshness.py
grep -E "^COPY" Dockerfile | grep -E "examples|drafts|records|graphify-out" \
  && echo "FORBIDDEN PATH IN DOCKERFILE" || echo "COPY allowlist clean"
```
Expected: every `ls` target exists; the check prints "COPY allowlist clean". (Only COPY lines are checked — the governance comment mentions the forbidden names on purpose. Note `tests/fixtures/synthetic` is allowed; the forbidden `records` is the repo-root directory.)

- [ ] **Step 5: Sanity-run the app the way the container will**

No local Docker exists; simulate the container invocation (env-port + 0.0.0.0) briefly:

```bash
ISAAC_UI_WORKSPACE=/tmp/isaac-deploy-smoke PORT=8123 sh -c \
  '.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 0.0.0.0 --port ${PORT} & sleep 3; curl -s http://127.0.0.1:8123/api/health; kill %1'
rm -rf /tmp/isaac-deploy-smoke
```
Expected: JSON health payload printed. Real image build is verified on Railway in Task 7.

- [ ] **Step 6: Run the full backend suite (nothing regressed)**

Run: `.venv/bin/pytest`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore railway.json
git commit -m "Phase 20: Railway container build (Dockerfile allowlist, health check)"
```

---

### Task 5: Vercel SPA config

**Files:**
- Create: `apps/web/vercel.json`

**Interfaces:**
- Consumes: BrowserRouter routes (`apps/web/src/App.tsx:12`, `src/lib/routes.ts`) — deep links like `/record/:id/evidence` need the rewrite.
- Produces: the config Vercel reads when the project root is `apps/web` (Task 8).

- [ ] **Step 1: Create `apps/web/vercel.json`**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

(Vercel serves real files in `dist/` before applying rewrites, so assets are unaffected; only unknown paths fall through to the SPA shell.)

- [ ] **Step 2: Verify a production build with deploy-style env vars**

Run:
```bash
cd apps/web && VITE_API_BASE=https://backend.example.invalid/api VITE_API_KEY=smoke-key npm run build
grep -rl "backend.example.invalid" dist/assets | head -1
grep -rl "smoke-key" dist/assets | head -1
npm run build
```
Expected: first build succeeds and both greps find a bundle file (env vars are inlined); the final plain `npm run build` restores a local-default `dist/` so no smoke values linger.

- [ ] **Step 3: Run the frontend suite**

Run: `cd apps/web && npm test`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add apps/web/vercel.json
git commit -m "Phase 20: Vercel SPA rewrite config"
```

---

### Task 6: Deployment docs

**Files:**
- Create: `docs/deployment.md`
- Modify: `docs/ui-local-dev.md` (the "What this is not" bullet, lines 19-20, and the inaccurate proxy claim near line 21 of the intro if present)
- Modify: `README.md:37-38` and `README.md:220-221` (stale "not deployed anywhere" claims)

**Interfaces:**
- Consumes: env var names and architecture from the spec (`docs/superpowers/specs/2026-07-11-phase-20-deployment-design.md`).
- Produces: the operator doc Tasks 7–9 follow; the doc where deployed URLs/project names get recorded after Task 9.

- [ ] **Step 1: Create `docs/deployment.md`**

```markdown
# Deployment — Synthetic Demo Hosting (Phase 20)

The synthetic UI prototype is hosted for sharing. Nothing about validation,
audit, or export changed — the deployed backend runs the same deterministic
core in a container.

## Architecture

- **Frontend** — Vite/React SPA on Vercel (root `apps/web`, static `dist/`,
  SPA rewrite via `apps/web/vercel.json`). Deployment Protection is enabled
  while iterating.
- **Backend** — FastAPI on Railway, built from the repo-root `Dockerfile`
  (explicit COPY allowlist; never contains `examples/`, `drafts/`,
  `records/`, or `graphify-out/`). Health check: `GET /api/health`.
- **State** — a Railway Volume mounted at `/data/isaac-workspace`, pointed at
  by `ISAAC_UI_WORKSPACE`. Contents are synthetic-only: experiment state,
  exported demo records, evidence sidecars.
- **Auto-deploys** — both platforms track GitHub
  `Krish-Verma/isaac-metadata-assistant`, branch `main`. Pushing to `main`
  deploys backend (Railway) and frontend (Vercel).

## Environment variables

| Variable | Platform | Purpose |
|---|---|---|
| `ISAAC_UI_WORKSPACE` | Railway | Workspace dir; set to the volume mount path |
| `ISAAC_UI_CORS_ORIGINS` | Railway | Comma-separated browser origins (the Vercel domain) |
| `ISAAC_UI_API_KEY` | Railway | Shared-secret bearer key; unset → auth disabled (local dev) |
| `PORT` | Railway (injected) | Container listen port |
| `VITE_API_BASE` | Vercel (build-time) | Backend origin + `/api` |
| `VITE_API_KEY` | Vercel (build-time) | Same value as `ISAAC_UI_API_KEY` |

Local dev needs none of these — defaults reproduce the pre-Phase-20 behavior
exactly (localhost CORS, `/tmp/isaac-ui-workspace`, auth off, no header).

## Auth model (honest scope)

Every `/api` route except `GET /api/health` requires
`Authorization: Bearer <ISAAC_UI_API_KEY>`. The key is baked into the frontend
bundle at build time, so it is exactly as secret as frontend access — which is
gated by Vercel Deployment Protection. This is nuisance-abuse prevention for a
synthetic demo, not cryptographic access control. Rotate by changing the env
var on both platforms and redeploying. Rate limiting is deferred to Phase 21.

## Resetting the synthetic workspace

```bash
railway ssh -- rm -rf /data/isaac-workspace
```

The backend auto-seeds a fresh synthetic demo experiment on the next request.
Nuclear option: delete and re-create the volume in the Railway dashboard.

## Rollback and failure recovery

Both platforms deploy from the same `main` commit, so the primary recovery
path is deterministic: **`git revert` the offending commit and push** — both
auto-deploys converge on the same known-good code. Platform rollbacks are the
fast stopgap while a revert is prepared:

- **Vercel**: Instant Rollback (dashboard) or `vercel rollback` repoints
  production at the previous immutable deployment. The frontend is stateless;
  rollback is always safe.
- **Railway**: redeploy a previous deployment from the dashboard's deploy
  history. A failed deploy (build or `GET /api/health` health-check failure)
  never replaces the running healthy one — a broken push degrades to "old
  backend keeps serving", not downtime.

**If one platform deploys a push and the other fails** (split-brain), the old
side keeps serving against the new side — an API-contract version mismatch.
The UI's explicit error states make this degraded, not corrupting. Recover by
revert-and-push so both converge; do not fix-forward one platform by hand.

**Outside git rollbacks:** the volume is untouched by any rollback — if a
newer backend wrote workspace state an older one cannot parse, reset the
workspace (above) and it re-seeds. Env vars (key, CORS origins) do not roll
back with code; after any rollback confirm both platforms' env vars still
match the running code.

## Deployed URLs and project names

Recorded after deployment (kept here, not hardcoded in code):

- Railway project: _TBD at deploy time_
- Backend URL: _TBD at deploy time_
- Vercel project: _TBD at deploy time_
- Frontend URL: _TBD at deploy time_
```

(The four "TBD at deploy time" placeholders are intentionally filled by Task 9 Step 5 — they are deploy outputs, not plan gaps.)

- [ ] **Step 2: Update `docs/ui-local-dev.md`**

Replace the first "What this is not" bullet (lines 19-20):

```markdown
- **Not production.** No auth by default; binds `127.0.0.1` when run locally.
  A protection-gated synthetic demo deployment exists — see
  [`docs/deployment.md`](deployment.md). Local runs remain the primary flow.
```

Also, if the intro (around line 21) claims the Vite dev server "proxies" to the backend, correct it: the frontend makes direct cross-origin fetches to `http://127.0.0.1:8000` allowed by the backend's CORS allowlist — there is no proxy (`apps/web/vite.config.ts` has no `server.proxy`).

- [ ] **Step 3: Update `README.md` stale claims**

At `README.md:37-38`, replace:

```markdown
- No production web app — the Phase 19 UI (`apps/api` + `apps/web`) is a local, synthetic-only
  prototype, not deployed anywhere (see [`docs/ui-local-dev.md`](docs/ui-local-dev.md)). No MCP server.
```

with:

```markdown
- No production web app — the Phase 19 UI (`apps/api` + `apps/web`) is a synthetic-only
  prototype. A protection-gated demo deployment exists (Phase 20, see
  [`docs/deployment.md`](docs/deployment.md)); local dev per
  [`docs/ui-local-dev.md`](docs/ui-local-dev.md). No MCP server.
```

At `README.md:220-222`, replace:

```markdown
- web UI iteration beyond the Phase 19 local synthetic-only prototype
  ([`docs/ui-local-dev.md`](docs/ui-local-dev.md)) — production hardening and any deployment are
  not planned;
```

with:

```markdown
- web UI iteration beyond the Phase 19 synthetic-only prototype
  ([`docs/ui-local-dev.md`](docs/ui-local-dev.md)) — a protection-gated synthetic demo deployment
  exists (Phase 20, [`docs/deployment.md`](docs/deployment.md)); production hardening is still
  not planned;
```

- [ ] **Step 4: Verify docs-only diff**

Run: `git diff --stat`
Expected: only `docs/deployment.md`, `docs/ui-local-dev.md`, `README.md` changed. Run `.venv/bin/pytest tests/test_query_safety_docs.py -v` (docs-sensitive tests) and expect PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/deployment.md docs/ui-local-dev.md README.md
git commit -m "Phase 20: deployment docs + refresh local-only claims"
```

---

### Task 7: Railway backend deployment (interactive gates)

**Files:** none (operational; `docs/deployment.md` updated later in Task 9)

**Interfaces:**
- Consumes: `Dockerfile`/`railway.json` from Task 4; auth + CORS env seams from Tasks 1–2.
- Produces: a live backend domain (`https://<service>.up.railway.app`) consumed by Task 8's `VITE_API_BASE`; the generated API key value shared with Task 8's `VITE_API_KEY`.

- [ ] **Step 1: Push `main` to GitHub**

```bash
git log origin/main..main --oneline   # review exactly what will be pushed
git push origin main
```
Expected: push succeeds; this is the commit the GitHub-connected services will build.

- [ ] **Step 2: Install the Railway CLI**

```bash
npm install -g @railway/cli && railway --version
```

- [ ] **Step 3: STOP — user login**

Tell the user: run `! railway login` (browser opens; click **Verify**). Wait for confirmation, then check `railway whoami`.

- [ ] **Step 4: STOP — user creates the GitHub-connected project**

CLI cannot install the GitHub App. Tell the user exactly:
1. Open https://railway.app/new → **Deploy from GitHub repo**.
2. If prompted, click **Configure GitHub App** and grant access to `Krish-Verma/isaac-metadata-assistant`.
3. Select the repo; when the service appears, click **Add variables later / Deploy**.
4. Report back the project name Railway assigned.

(The first build may fail health checks until env vars exist — that is expected and fixed in Step 5.)

- [ ] **Step 5: Link the CLI, attach the volume, set env vars**

```bash
cd /Users/krishverma/Documents/ISAAC
railway link          # pick the project the user just created
railway volume add --mount-path /data/isaac-workspace
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # generate the key; do NOT commit it
railway variables --set "ISAAC_UI_WORKSPACE=/data/isaac-workspace" --set "ISAAC_UI_API_KEY=<generated-key>"
railway redeploy
```
Expected: deploy goes green with the health check passing. If any CLI subcommand syntax differs (Railway CLI evolves), run `railway <cmd> --help` and adapt — the intent per step is fixed.

- [ ] **Step 6: Create the public domain and verify the API contract**

```bash
railway domain        # generates https://<service>.up.railway.app
BACKEND=https://<printed-domain>
curl -s $BACKEND/api/health                                   # expect 200 JSON banner
curl -s -o /dev/null -w "%{http_code}\n" $BACKEND/api/experiments                    # expect 401
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <generated-key>" \
  $BACKEND/api/experiments                                    # expect 200
curl -s -o /dev/null -w "%{http_code}\n" -X POST $BACKEND/api/uploads \
  -H "Authorization: Bearer <generated-key>"                  # expect 403 (governance seam)
```
Expected codes: 200, 401, 200, 403.

- [ ] **Step 7: Record state (no commit yet)**

Note project name, service name, backend domain, and volume mount for Task 9's doc update and final report.

---

### Task 8: Vercel frontend deployment (interactive gates)

**Files:** none (operational)

**Interfaces:**
- Consumes: backend domain + API key from Task 7; `apps/web/vercel.json` from Task 5.
- Produces: the frontend production domain, fed back into Railway's `ISAAC_UI_CORS_ORIGINS`.

- [ ] **Step 1: STOP — user login**

Tell the user: run `! vercel login` and complete the browser/email confirmation. Verify with `vercel whoami`.

- [ ] **Step 2: Create and link the Vercel project**

```bash
cd /Users/krishverma/Documents/ISAAC/apps/web
vercel link           # create new project (suggest name: isaac-demo-web), scope = user's account
```

- [ ] **Step 3: Connect the GitHub repo for auto-deploys**

```bash
vercel git connect
```
If it reports the Vercel GitHub App is not installed: STOP and tell the user to click **Install** on the GitHub authorization page it opens (grant `Krish-Verma/isaac-metadata-assistant`), then rerun.

- [ ] **Step 4: STOP if needed — Root Directory**

Auto-deploys must build from `apps/web`. Check project settings (`vercel project inspect isaac-demo-web` or the dashboard). If Root Directory is not settable via CLI, tell the user: Vercel dashboard → project **isaac-demo-web** → **Settings → General → Root Directory** → set to `apps/web` → Save.

- [ ] **Step 5: Set env vars and deploy**

```bash
printf 'https://<railway-domain>/api' | vercel env add VITE_API_BASE production
printf '<generated-key>' | vercel env add VITE_API_KEY production
vercel deploy --prod
```
Expected: build succeeds; note the production URL (`https://isaac-demo-web.vercel.app` or similar).

- [ ] **Step 6: Verify/enable Deployment Protection**

New Vercel projects default to **Vercel Authentication** on. Verify: fetch the production URL from this machine's shell (unauthenticated) — expect an auth challenge (401/302 to SSO), NOT the app. If it serves the app publicly: STOP and tell the user: dashboard → **Settings → Deployment Protection** → enable **Vercel Authentication** for Standard Protection.

- [ ] **Step 7: Wire the frontend origin into backend CORS**

```bash
cd /Users/krishverma/Documents/ISAAC
railway variables --set "ISAAC_UI_CORS_ORIGINS=https://<vercel-production-domain>"
railway redeploy
```
Expected: backend redeploys green.

---

### Task 9: End-to-end deployed verification + final report

**Files:**
- Modify: `docs/deployment.md` (fill in URLs/project names recorded in Tasks 7–8)

**Interfaces:**
- Consumes: live backend + frontend from Tasks 7–8; verification checklist from the spec.
- Produces: the Phase 20 completion report (URLs, env table, reset procedure, local-vs-deployed differences).

- [ ] **Step 1: Scripted API verification against the deployed backend**

With `BACKEND` and `KEY` from Task 7 (`AUTH="Authorization: Bearer $KEY"`):

```bash
curl -s $BACKEND/api/health | python3 -m json.tool                    # banner
curl -s -X POST $BACKEND/api/demo/run -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"mode": "full"}' | python3 -m json.tool                        # full pipeline (incl. export)
curl -s -X POST $BACKEND/api/demo/run -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"mode": "draft_only"}' | python3 -m json.tool                  # draft-only pipeline
curl -s $BACKEND/api/experiments -H "$AUTH" | python3 -m json.tool    # list incl. demo results
```
Then walk the manual completion path on the **draft_only** experiment id, mirroring `apps/api/tests/test_api.py`'s `_complete_seed` flow: GET `/pending` → POST `/answers` with each blocker's `demo_answer` value → POST `/export` → GET `/artifacts` (record + sidecar present) → POST `/validate` → POST `/audit` → GET `/draft` and `/evidence` (all with `$AUTH`). Compare every verdict against the same sequence run on the local backend (fresh `ISAAC_UI_WORKSPACE` tmp dir). Expected: identical verdict payloads (timestamps/ids differ).

- [ ] **Step 2: Volume persistence check**

```bash
railway redeploy   # or restart the service
curl -s $BACKEND/api/experiments -H "$AUTH" | python3 -m json.tool
```
Expected: the experiments created in Step 1 are still listed after the restart (volume survived).

- [ ] **Step 3: Browser verification of the deployed frontend**

Using Chrome automation (user's browser is logged into Vercel, so protection passes): load the production URL, walk S1 → run synthetic demo → S3 workbench → S4 completion → S5 evidence → S6 export readiness. Confirm no console errors, no requests to `127.0.0.1`, and the same screens/behavior as the local demo. Also confirm an unauthenticated client (curl) still gets the auth challenge, not the app.

- [ ] **Step 4: Auto-deploy check**

After Step 5's docs commit is pushed, confirm both platforms picked it up automatically (Railway deployment list + `vercel ls`), i.e. push-to-`main` is the deploy trigger.

- [ ] **Step 5: Fill in `docs/deployment.md`, commit, push**

Replace the four "TBD at deploy time" lines with the real Railway project name, backend URL, Vercel project name, and frontend URL.

```bash
git add docs/deployment.md
git commit -m "Phase 20: record deployed URLs and project names"
git push origin main
```

- [ ] **Step 6: Final report to the user**

Deliver: frontend URL, backend URL, protected demo URL note (Vercel Authentication — only authorized Vercel users see it), full env-var table (names + where each value lives, no secret values), Railway/Vercel project names, workspace reset command, local-vs-deployed differences (auth on, CORS restricted to the Vercel origin, workspace on volume vs `/tmp` — everything else byte-identical), and any remaining manual steps.
