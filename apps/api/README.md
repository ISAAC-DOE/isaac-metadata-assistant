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

## Memory plane (read-only)

Four `GET /api/memory/*` endpoints (`/memory/concepts`, `/memory/concepts/{id}`, `/memory/files`,
`/memory/file`) wrap the read-only project-memory graph (`memory.py`) — metadata/provenance only,
no file contents ever served, no search. `GET /api/graph/status` additionally carries seven
additive fields (`built_at_commit`, `node_count`, `edge_count`, `community_count`, `file_count`,
`concept_count`, `graph_mtime`) sourced from the same reader as the memory endpoints, so status and
counts always describe the same graph. This is a **memory plane**: it never validates a record and
never authorizes export. See [`../../docs/project-memory-map.md`](../../docs/project-memory-map.md).
