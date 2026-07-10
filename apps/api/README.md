# ISAAC local UI backend (`apps/api`)

A **synthetic-only, local-first** FastAPI wrapper over the deterministic
`isaac_records` core. It adds no validation logic: every draft/official/audit/warning
verdict comes from the same core functions the `isaac` CLI uses, so the UI inherits
byte-identical results. It never touches real data and writes only inside a workspace
directory outside the repo.

## Run

```bash
.venv/bin/pip install -e '.[dev,api]'
.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000
# smoke: curl -s http://127.0.0.1:8000/api/health
```

The React frontend (Vite) is served from `http://localhost:5173`; only that origin is
allowed via CORS. Workspace root: `ISAAC_UI_WORKSPACE` (default `/tmp/isaac-ui-workspace`).

## Governance

Synthetic fixtures only. `POST /api/uploads` is always `403` (real/private uploads are
approval-gated); source preview serves only the two committed synthetic fixtures.
