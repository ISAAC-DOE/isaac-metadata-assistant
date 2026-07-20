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
  `records/`, or `graphify-out/`). The image does ship one committed,
  sanitized `apps/api/isaac_api/data/memory-snapshot.json` (P24.9,
  metadata/provenance only, no file contents), which powers hosted Project
  Memory. Health check: `GET /api/health`.
- **State** — a Railway Volume mounted at `/data/isaac-workspace`, pointed at
  by `ISAAC_UI_WORKSPACE`. Contents are synthetic-only: experiment state,
  exported demo records, evidence sidecars.
- **Auto-deploys** — both platforms track GitHub
  `Krish-Verma/isaac-metadata-assistant`, branch `main`. Pushing to `main`
  deploys backend (Railway) and frontend (Vercel).

## Project Memory snapshot (P24.9)

Hosted Project Memory is served from a committed, sanitized snapshot rather than
a live graph (`graphify-out/` is gitignored and never shipped).

- **Delivery** — `apps/api/isaac_api/data/memory-snapshot.json` ships inside the
  existing `COPY apps/api/` layer; no extra Dockerfile COPY is needed. The reader
  auto-selects it by on-disk presence (`SanitizedSnapshotSource`), so no env var
  is required for the packaged path. `ISAAC_MEMORY_SNAPSHOT` can point at an
  alternate file (e.g. a Railway volume) if delivery changes later.
- **Content** — metadata/provenance only: counts, served-file allowlist, curated
  concepts, and length-capped rationales. Never file contents; every `on_disk` is
  forced `false`; secret/path-excluded strings are scanned out at generation.
- **Freshness (redesigned P24.10)** — `GET /api/graph/status` no longer compares
  the deploy's build commit to the snapshot; `deployed_app_commit` is surfaced as
  version metadata only, never a freshness input. Freshness is two separated,
  provable axes instead: `memory_policy` (current/stale/unknown — the shipped
  sanitization/exclusion policy recomputed at runtime against the snapshot's
  embedded fingerprint) and `indexed_sources` (current/stale/unknown — a
  CI-only content-drift gate over the files already embedded in the snapshot;
  the hosted runtime never recomputes it, since the served files aren't
  shipped). A missing/unreadable snapshot still degrades to the honest
  unavailable panel regardless. See
  [`2026-07-19-phase-24-10-memory-freshness-semantics.md`](superpowers/specs/2026-07-19-phase-24-10-memory-freshness-semantics.md).
- **Refresh / rollback** — regenerate with
  `python scripts/build_memory_snapshot.py` from a fresh local graph, review the
  diff (including every `rationales[]` string), and recommit; `test_committed_snapshot.py`
  gates shape, provenance, and leaks in CI. Rollback is atomic with code via
  `git revert`. See the P24.9 spec §16 (update) and §15 (rollback).
- **Verification scope (two independent guarantees).** The committed snapshot's
  **shape + leak scan** (`test_committed_snapshot.py`) runs unconditionally in every
  backend test run — it reads only the committed artifact and needs no graph, so a
  malformed or leaking snapshot is always caught, including in CI. **Byte-drift
  detection** (`python scripts/build_memory_snapshot.py --check`, which regenerates
  from the source graph and compares) is different: it requires the local Graphify
  artifacts (`graphify-out/`). Where those artifacts are present the check is
  deterministic and catches any drift between the committed snapshot and the graph;
  where they are absent — e.g. CI, which does not ship `graphify-out/` — drift cannot
  be recomputed, and CI does **not** and **cannot** regenerate the graph, because the
  Graphify inputs are not available there. Keeping the committed snapshot current is
  therefore a local, human-run step (§16), not something CI can do on its own.

## Environment variables

| Variable | Platform | Purpose |
|---|---|---|
| `ISAAC_UI_WORKSPACE` | Railway | Workspace dir; set to the volume mount path |
| `ISAAC_UI_CORS_ORIGINS` | Railway | Comma-separated browser origins (the Vercel domain) |
| `ISAAC_UI_API_KEY` | Railway | Shared-secret bearer key; unset → auth disabled (local dev) |
| `PORT` | Railway (injected) | Container listen port |
| `ISAAC_BUILD_COMMIT` | Railway (optional) | Explicit build/commit identity for `GET /api/health` |
| `RAILWAY_GIT_COMMIT_SHA` | Railway (injected) | Fallback build/commit identity for `GET /api/health` |
| `VITE_API_BASE` | Vercel (build-time) | Backend origin + `/api` |
| `VITE_API_KEY` | Vercel (build-time) | Same value as `ISAAC_UI_API_KEY` |

### Build/commit identity on `/api/health`

`GET /api/health` includes an additive `commit` field so a deployed backend's
running commit can be confirmed without a shell into the container:
`ISAAC_BUILD_COMMIT` wins if set and non-empty; else `RAILWAY_GIT_COMMIT_SHA`
if set and non-empty; else `null`. All other health fields are unchanged.
Both env vars are read per-request, not cached at import time.

Railway provides `RAILWAY_GIT_COMMIT_SHA` automatically for GitHub-connected
deploys. If it turns out not to be exposed at runtime, `commit` is `null` and
that is the honest state — do not change Railway config to force it; set
`ISAAC_BUILD_COMMIT` explicitly instead if a guaranteed value is needed.

`ISAAC_UI_CORS_ORIGINS` values must be exact origins — scheme://host with no
trailing slash and no path (e.g. `https://app.vercel.app`, NOT
`https://app.vercel.app/`) — because browsers match origins exactly and a
trailing slash silently breaks CORS.

Local dev needs none of these — defaults reproduce the pre-Phase-20 behavior
exactly (localhost CORS, `/tmp/isaac-ui-workspace`, auth off, no header).

## Auth model (honest scope)

When `ISAAC_UI_API_KEY` is set, every route requires
`Authorization: Bearer <ISAAC_UI_API_KEY>` except `GET /api/health` (kept open
for Railway health checks) and `OPTIONS` requests (CORS preflight carries no
credentials). That includes FastAPI's auto-generated `/docs` and
`/openapi.json` — intentional, so the deployed demo has no public schema
browsing. The key is baked into the frontend bundle at build time, so it is
exactly as secret as frontend access — which is gated by Vercel Deployment
Protection. This is nuisance-abuse prevention for a synthetic demo, not
cryptographic access control. Rotate by changing the env var on both
platforms and redeploying. Rate limiting is not implemented — it is a
back-burner item with no phase currently scheduled to add it (not a
Phase 21 commitment).

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

### Verifying backend/frontend version compatibility

Both platforms build from the same `main` commit, so compatibility is a
property of the commit, not of runtime coordination: the API client and the
backend are tested together on every push (`.venv/bin/pytest` backend suite +
`npm test` frontend suite in CI). After any deploy or rollback, confirm the
running pair:

1. Both dashboards show the same deployed commit SHA (Railway service →
   latest deployment; Vercel project → production deployment).
2. `GET /api/health` on the Railway domain returns 200 with the
   `synthetic-only` banner.
3. Load the frontend and run one synthetic demo cycle — this exercises the
   live API contract end to end (list, demo run, pending, evidence).

If the two SHAs differ (split-brain), recover by revert-and-push as above —
do not fix forward one platform by hand.

## Deployed URLs and project names

Recorded after deployment (kept here, not hardcoded in code):

- Railway project: `isaac-metadata-assistant` (service `isaac-metadata-assistant`,
  region sfo; volume `isaac-metadata-assistant-volume` at `/data/isaac-workspace`)
- Backend URL: https://isaac-metadata-assistant-production.up.railway.app
- Vercel project: `isaac-demo-web` (root directory `apps/web`)
- Frontend URL: https://isaac-demo-web.vercel.app
