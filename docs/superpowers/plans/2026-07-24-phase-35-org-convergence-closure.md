# Phase 35 — Org-Repo Convergence + S3DF Deployment · Closure

**Status:** CLOSED 2026-07-24 — org canonical HEAD `8a10ed5` (merge commit #1), deployed image
`v0.0.3`, hosted `/krish` running commit verified `8a10ed5`.
**Owner:** orchestrator (Opus 4.8, ratified fallback for Fable 5).
**Created:** 2026-07-24.
**Plan of record:** `docs/superpowers/plans/2026-07-24-phase-35-org-convergence-approved-plan.md`
(this closure records the executed outcome of that plan's P35.5–P35.8).

Goal (Program A): move the exact Phase 31–34 light application into the canonical org repo
`ISAAC-DOE/isaac-metadata-assistant`, preserving both histories and Dean's single-image `/krish`
deploy layer; verify under `/krish`; deploy synthetic-only; make the org repo canonical. No portal
dependency, no real data, no LLM, no truth-path change.

---

## 1. Accuracy boundary (binding documentation language)

- The integration added **no** truth-path change: `schema/` and `src/isaac_records/` are byte-identical
  to personal `main`; the org side contributed **deployment plumbing only**.
- The app remains **synthetic-only**, ephemeral (`emptyDir`), LLM-free, Graphify-free in the truth
  core. No Postgres, no portal API key, no personal API key, no real SLAC data.
- "Deployed and verified" means: the merge, the versioned image build, the immutable semver tag, and
  the **hosted running commit** are confirmed. The **human responsive / 200%-zoom visual gate is NOT
  claimed** — it remains Krish's to give.
- History preservation is literal: the org canonical HEAD is a genuine **two-parent merge commit**;
  both Dean's deploy lineage and the full personal P26–34 history are reachable from it. No squash, no
  rebase of published history, no force-push.

---

## 2. What happened (P35.5 → P35.8)

### P35.5 — Full release verification (complete)
On the integration HEAD `f5c519e`: backend `pytest` **975 passed / 1 skipped** (pre-existing real-graph
skip), frontend `vitest` **672 passed**, `tsc` + Vite build clean, base-path tests **12 passed**,
synthetic demo → schema-valid export, `isaac validate --official` (+`--warnings`) PASS, `isaac audit`
**33/33**, committed-snapshot gate **17 passed**, snapshot `--check` no drift; secret/path/raw-content/
hardcoded-route/hardcoded-API/`.only`/disabled-test scans clean. Independent Opus reviews (merge, docs,
release, + addendum) → **SHIP**.

### P35.6 + pre-merge hardening addendum (complete)
Pushed `integration/current-app-s3df` to `org` and opened **PR #1** as a review-only, no-merge proposal
(branch push does not deploy — `build-push.yaml` fires only on push to `main` / `v*` tags). Addendum:
corrected the `ISAAC_UI_API_KEY` contract (unset in prod; Authentik at the edge is the auth boundary —
setting the server key alone with `VITE_API_KEY` unset would 401 the SPA); added a **non-publishing**
`pull_request`-only `pr-docker-smoke.yml` that builds the exact production image and smoke-tests it on
the runner (health `commit` echoes head SHA, `/krish` routing, SPA fallback, API-404 non-fallthrough,
root-leak) — **GREEN**, no push/tag/secret; specified the **Create a merge commit** method; included 9
Dean review questions. All PR checks green.

### P35.7 — Main-merge + deployment (complete; hosted running SHA verified)
Under explicit Krish authorization (Dean-approved), PR #1 was merged with **Create a merge commit**:

- **Merge commit `8a10ed5ee58e051888dd7f867234c3a198546ffb`** — parents **`[010f3c7, f5c519e]`**, by
  `Krish-Verma`, 2026-07-24T17:51:58Z. Org `main` advanced to `8a10ed5`. Both histories preserved and
  reachable (`f5c519e → 8265629 → e83a0ce → {010f3c7, b3b76cd}`).
- **Build:** workflow run `30114677296` (`push`/`main`/`8a10ed5`) **success**; image
  `ghcr.io/isaac-doe/isaac-metadata-assistant` manifest digest
  `sha256:643716b5d6fc17b0caebfe7fc3be1afb5485dc5b69698f78e8217938604783b3`, built with
  `ISAAC_BUILD_COMMIT=8a10ed5`.
- **Versioning:** annotated tag **`v0.0.3`** → `8a10ed5` (monotonic; org tags = `v0.0.1/2/3`;
  immutable, not reused/moved). **No manual tag; no manual workflow dispatch.**
- **Independent Opus review:** **SHIP** — 0 Critical / 1 Important (`:latest` published, non-blocking —
  see §4) / 3 Minor.
- **Hosted verification (Krish, authenticated through Authentik):** `/krish/api/health` →
  `status: ok`, `mode: synthetic-only`, `core: isaac_records`, `version: 0.1.0`,
  **`commit: 8a10ed5` — exact match to the merge commit**. Light neutral shell + workflow rail +
  record-completion surface + lavender Assistant rail visibly serving under `/krish`; **no dark portal
  shell** introduced.

**P35.7 classification:** `COMPLETE — DEPLOYED AND RUNNING SHA VERIFIED; HUMAN RESPONSIVE GATE
PARTIALLY OPEN`. Desktop hosted verification PASSED; the narrow-width (1280/1024/768/375) + 200%-zoom
**human visual sign-off remains OPEN** (not performed — Krish's gate).

### P35.8 — Canonical cutover (git-local complete; personal-deploy retirement pending manual)
Executed 2026-07-24 in the primary checkout, all reversible git-local operations only:

- **Remotes remapped:** `origin` → `ISAAC-DOE/isaac-metadata-assistant` (canonical); `personal` →
  `Krish-Verma/isaac-metadata-assistant` (preserved historical mirror, never pushed/rewritten).
- **Local `main` fast-forwarded** `b3b76cd` → `8a10ed5`, tracking `origin/main`; **0 ahead / 0 behind**,
  tree clean. Three-way alignment: local `main` == `origin/main` == hosted `commit` == `8a10ed5`.
- **Cleanup:** integration worktree removed; local + remote merged integration branch deleted
  (`f5c519e` preserved as parent-2 of `8a10ed5` — nothing lost); the stale pre-approval draft
  (`specs/2026-07-23-org-migration-portal-parity-design.md`, uncommitted) removed after proving it is
  fully superseded by the committed approved plan (archived to session scratchpad).
- **Safety:** no force-push, no history rewrite, no push to `main`, no personal-repo push, no unique
  commit lost.

**Personal-deploy retirement — PENDING (manual, disable-not-delete).** The remap already prevents this
repo's pushes from reaching personal `main`; the residual path is a human push to personal `main`
re-triggering the still-armed integrations (`vercel[bot]` project `isaac-demo-web`;
`railway-app[bot]` service `isaac-metadata-assistant / production`; both last deployed `b3b76cd`). This
requires a Vercel/Railway dashboard action Claude cannot safely perform (Vercel MCP is read-only; no
Railway API access; GitHub-App changes need app-auth; a config-removal push is a forbidden and
self-triggering personal push). Krish action: Vercel → project `isaac-demo-web` → Settings → Git →
**Disconnect** (or Pause Project); Railway → service → Settings → **disconnect the GitHub repo** (or
disable Auto-Deploy). **Do NOT delete** either project. The `/krish` preview (`8a10ed5`) is unaffected.

---

## 3. Phase 35 Completion Gate (CLOSED 2026-07-24 @ org HEAD `8a10ed5`)

| Criterion | Status | Evidence |
|---|---|---|
| History-preserving 2-parent merge, both histories reachable | ✅ | `8a10ed5` parents `[010f3c7, f5c519e]`; `b3b76cd`/`010f3c7` ancestors of HEAD; no squash/rebase/force |
| Truth path untouched by integration | ✅ | `schema/`, `src/isaac_records/` byte-identical to personal `main`; org side = deploy plumbing only |
| Full release battery (P35.5) | ✅ | backend 975/1-skip; frontend 672; tsc+build; base-path 12; official validate + audit 33/33; snapshot gate 17 + `--check` clean; scans clean |
| Independent Opus review (P35.5/P35.6/P35.7) | ✅ | SHIP at each gate; P35.7 reviewer SHIP (0C/1I/3M) |
| Merge via Create-a-merge-commit (P35.7) | ✅ | merge commit `8a10ed5`, by Krish-Verma, 2026-07-24T17:51:58Z |
| Versioned image built + immutable semver tag | ✅ | run `30114677296` success; digest `sha256:643716b5…`; tag `v0.0.3`→`8a10ed5`; no tag reuse |
| Hosted running commit verified | ✅ | Krish-authenticated `/krish/api/health` `commit: 8a10ed5`, `mode: synthetic-only` |
| Light UI deployed; no dark portal shell | ✅ | Krish visual confirmation of light shell + Assistant rail under `/krish` |
| Canonical cutover git-local (P35.8) | ✅ | `origin`→org, `personal`→Krish; `main`==`origin/main`==hosted==`8a10ed5`; clean; branches/worktree cleaned; no force-push |
| Deploy-safety boundaries held | ✅ | no direct `main` push, no squash/rebase, no manual `v*` tag, no manual dispatch, no `isaac-k8` change, no secret |

**Phase 35 = COMPLETE at `8a10ed5`.** Open items honestly carried, not overstated as done:

- **Human responsive / 200%-zoom visual sign-off** (narrow 1280/1024/768/375 + zoom) — Krish's gate,
  still OPEN. Desktop hosted verification passed.
- **Personal-deploy retirement** (Vercel `isaac-demo-web` + Railway service) — PENDING Krish's
  dashboard disable-not-delete action; checklist above.
- **`:latest` publication** by `build-push.yaml` — tracked hardening item (§4).

---

## 4. Known issues carried into Phase 36 hardening

- **`build-push.yaml` publishes a mutable `:latest` alias** alongside the immutable semver tag. This is
  Dean's unmodified workflow (authored 2026-07-21, pre-dates the integration) — **not** an integration
  regression. Flux follows the immutable semver pin, so the preview is unaffected; but nothing should
  depend on `:latest`. Tracked as a focused, reviewed hardening item (remove `:latest`, preserve
  immutable semver + auto-tag + Flux compatibility; deployment-sensitive Opus review). Do not modify
  `isaac-k8`.
- **GitHub Actions are pinned to floating tags** (not commit SHAs) — supply-chain hardening item.
- **`ApiKeyAuthMiddleware`** remains present (fail-open when the key is unset) — Authentik at the edge
  is the production auth boundary; a focused architecture decision (retain-for-dev / remove / defer) is
  a Phase 36 hardening item. No personal/SPA key may be introduced in production.
- **Residual, non-blocking:** single-layer (edge-only) auth for a synthetic preview; GHCR digest not
  API-verifiable with the current token scope (corroborated via build logs).

No new phase began without approval; Phase 36 (repository-local native enhancements) is authorized and
opened under the 2026-07-24 execution authorization (see the Phase 36 plan doc).
