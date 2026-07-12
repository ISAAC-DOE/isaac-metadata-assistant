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
platforms and redeploying. Rate limiting is deferred to Phase 21.

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
