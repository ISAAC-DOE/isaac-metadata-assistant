# Developer guide: your app now runs on SLAC Kubernetes

As of 2026-07-21 the metadata assistant is hosted at
**https://isaac.slac.stanford.edu/krish/** on the ISAAC cluster. Vercel and
Railway are retired. Here is what changes for you day to day.

## 1. Push to the org repo, not your personal repo

The canonical repo is now **`ISAAC-DOE/isaac-metadata-assistant`** (public since 2026-08-06).
Point your checkout at it:

```bash
git remote set-url origin git@github.com:ISAAC-DOE/isaac-metadata-assistant.git
git pull --rebase
```

Do NOT push to `Krish-Verma/isaac-metadata-assistant` anymore — until the old
platform projects are deleted, pushes there still trigger Vercel/Railway
deploys of stale code.

## 2. How deploys work now

Push to `main` and you are done:

1. `.github/workflows/ci.yml` runs the test suites (unchanged).
2. `.github/workflows/build-push.yaml` builds ONE Docker image containing both
   the FastAPI backend and the compiled SPA, pushes it to
   `ghcr.io/isaac-doe/isaac-metadata-assistant` with an auto-incremented
   version (v0.0.1, v0.0.2, ...), and tags the repo.
3. Flux (the cluster's GitOps operator) notices the new version and rolls it
   out automatically. No dashboard, no CLI, no manual step.

Expect a push-to-live time of roughly 5-10 minutes. To verify a deploy landed,
open https://isaac.slac.stanford.edu/krish/api/health in a logged-in browser —
the `commit` field is the SHA that is actually running.

Because frontend and backend ship in one image, there is no more Vercel/Railway
split-brain: every deploy is a single tested commit. **Rollback = `git revert`
+ push.**

## 3. The app lives under /krish — path rules

The site is served at a subpath, not a domain root. The plumbing is already
done (Vite `base`, router `basename`, same-origin API base — all baked in at
Docker build time). To keep it working:

- Use React Router navigation (`<Link>`, `navigate`, `ROUTES`) — never
  hardcode absolute paths like `href="/experiments"` or `fetch("/api/...")`.
- All API calls go through `apps/web/src/lib/api.ts` (`API_BASE`), as they do
  today. Keep it that way.
- Reference static assets through Vite imports so the base path is applied.

Nothing about local dev changes: `npm run dev` still serves at `/`, uvicorn
still serves `/api/*`. The `/krish` prefix exists only in the deployed image.

## 4. Auth is at the edge now

Every request to `/krish/*` goes through **Authentik** and requires
membership in the `admin` or `researcher` group — same policy as the ISAAC
portal. Consequences:

> **Corrected 2026-08-01.** This line previously read "Authentik (SLAC SSO)". That parenthetical is not
> supported by anything observed. An **unauthenticated** observation on 2026-08-01 of
> `https://isaac.slac.stanford.edu/if/flow/default-authentication-flow/` found the
> identification stage presenting **only** an "Email or Username" field, an **ORCID** federated-login
> button, and "Sign up with ORCID" — **no SLAC SSO button is offered at that stage**. Whether a SLAC
> IdP appears later in the flow, or is reachable by another path, is **UNOBSERVED** — this is not a
> claim that SLAC SSO is absent, only that it is not what the login page presents. Authentik is the
> identity provider at the edge; which upstream sources it federates is Dean's configuration in
> `isaac-k8`, which this repository cannot see (Q1). Note also that ORCID being an **authentication**
> method here confers no authorization: `attribution.contributors[].orcid` is scientific-credit
> metadata and must never be used as an authorization principal.

- `ISAAC_UI_API_KEY` is unset in this deployment and the bearer-key seam still
  exists in the BACKEND for other environments, though it is redundant behind
  SSO. **`VITE_API_KEY` no longer exists in the frontend at all** (removed
  2026-08-08): a `VITE_*` value is compiled into the bundle served to every
  visitor, so it could never have been a secret. Consequence worth knowing
  before you set the server key: the browser client sends no credential, so a
  deployment that sets `ISAAC_UI_API_KEY` will 401 the UI. It is now a control
  for non-browser callers.
- You need an account in the researcher group to see the deployed app — ask
  the ISAAC team if you don't have one.
- Scripted access (curl) to the deployed URL won't work without a browser
  session; test against a local run or `docker run` instead.

## 5. State is ephemeral

The workspace (`ISAAC_UI_WORKSPACE`) is an emptyDir volume: it resets whenever
the pod restarts, then self-seeds the synthetic experiments on first read.
There is no Railway volume anymore — do not build anything that assumes
exported records survive a restart.

## 6. Gotchas to remember

- **Never use `:latest`** in anything k8s-related; the cluster pins semver
  tags (the workflow handles this for you).
- The committed `memory-snapshot.json` drift gate still applies: if you edit a
  file indexed in its manifest, regenerate/refresh the snapshot or CI fails
  (see `docs/deployment.md`, "Project Memory snapshot").
- Docker builds now include `apps/web` (multi-stage). If you add frontend
  build-time env vars, they must be threaded through the Dockerfile's node
  stage to take effect in production.
- k8s manifests live in a separate repo (`ISAAC-DOE/isaac-k8`,
  `metadata-assistant/`). App code changes never require touching it; only
  infra changes (env vars, resources, ingress) do.

