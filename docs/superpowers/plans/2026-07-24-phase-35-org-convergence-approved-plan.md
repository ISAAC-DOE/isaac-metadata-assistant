# ISAAC — Org-Repo Convergence + Capability Integration (APPROVED PLAN)

**Status:** APPROVED 2026-07-24. **Program A COMPLETE** — P35.0–P35.6 executed to the PR boundary, then
**P35.7 (main-merge/deploy) and P35.8 (canonical cutover) were executed under a separate explicit Krish
authorization** (Dean-approved); org canonical HEAD `8a10ed5`, deployed `v0.0.3`, hosted running commit
verified `8a10ed5`. See the closure doc
`docs/superpowers/plans/2026-07-24-phase-35-org-convergence-closure.md` for the executed outcome. The
**Program B native enhancements are now authorized as Phase 36** (repository-local, synthetic-only);
**portal integrations and Phase 37 remain hard-gated and NOT authorized.** The P35.5–P35.8 subsections
below are the original plan; the closure doc is authoritative for what actually shipped.
**Date:** 2026-07-23 (drafted) / 2026-07-24 (approved)
**Vessel:** `Krish-Verma/isaac-metadata-assistant` (local/personal, remote `origin`) →
`ISAAC-DOE/isaac-metadata-assistant` (canonical, remote `org`).

This document supersedes the pre-approval draft spec
(`docs/superpowers/specs/2026-07-23-org-migration-portal-parity-design.md`, personal checkout only,
uncommitted) as the tracked, approved plan of record for Phase 35 (Program A) and the scoped-but-gated
Phase 36 (Program B).

---

## Execution status (2026-07-24)

Recorded as verified fact at the time this plan was committed:

- **Merge base:** `6593759` (P26.0a, Jul 21). Personal side: 105 commits (P26→34), HEAD `b3b76cd`.
  Org side: 6 commits, all deployment-layer (`Dockerfile`, `build-push.yaml`, `spa.py`/`config.py`,
  base-path plumbing, `test_base_path.py`, doc updates) — **zero truth-path changes** (nothing under
  `schema/` or `src/isaac_records/`).
- **P35.0 (read-only recontextualization)** and **P35.1 (two-repo forensic audit)** are complete. The
  audit reproduced the merge base, commit graphs, and file-ownership matrix from a fresh trial merge
  (not the draft's `compare` output) and found no hard-stop condition (no rewritten published history,
  no unexpected product/truth-path change on the org side, no unknown production-data handling).
- **P35.2 (local history-preserving integration)** is complete: the merge is committed locally on
  `integration/current-app-s3df` at `e83a0ce`, a genuine two-parent merge commit
  (`010f3c7` org/main + `b3b76cd` personal main) — both histories preserved, no squash, no rebase of
  published org history, no force-push, nothing dropped. Verification at merge time: backend
  **975 passed / 1 skipped**, frontend **672 passed**, Vite production build clean, snapshot `--check`
  reported no drift. Independent Opus review verdict: **SHIP**.
- **P35.3 (single-image + `/krish` verification)** passed via a functional uvicorn simulation of the
  base-path contract (router `basename`, `API_BASE`-only fetches, deep-link/SPA-fallback behavior,
  asset base-path honoring) — green. **Docker image build + smoke is DEFERRED**: Docker is unavailable
  in this development environment and the org repo's CI does not build/smoke the image on branch push
  or PR — `build-push.yaml` only builds and pushes an image on push to `main` or a `v*` tag. The image
  build path will be exercised for the first time at the P35.7 main-merge gate, which remains
  unauthorized until Krish approves it explicitly.
- **This document, the CLAUDE.md §10/§17 policy update, and the snapshot regeneration are P35.4**
  (documentation + policy, no product/code changes).
- Truth core (`schema/`, `src/isaac_records/official.py`, `draft_validator.py`, `export.py`,
  `audit.py`, `cli.py`) is unchanged by the org-repo integration — the org side contributed deployment
  plumbing only.

## Exact next approved action

1. **P35.4** — this plan document, the CLAUDE.md §10/§17 policy update, and deterministic snapshot
   regeneration (in progress / this commit).
2. **P35.5** — full release verification battery: full backend + frontend suites, TypeScript, Vite
   production build, base-path tests, synthetic demo, truth validation, evidence audit, snapshot
   `--check` + the committed-snapshot gate test, secret/path/raw-content/hardcoded-route/hardcoded-API/
   disabled-test scans. Fix every Critical + Important finding. (Docker build + smoke stays deferred
   per the P35.3 note above — it is not part of PR-time CI.)
3. **P35.6** — independent Opus release review of the full integration diff, then push the
   `integration/current-app-s3df` branch to `org` and open a PR into org `main`. **Do not merge.**
   Request Dean's review (Docker, FastAPI SPA hosting, `/krish`, Actions, GHCR tags, Flux, resources,
   health, infra ownership). Branch push and PR do not trigger a deploy (verified in P35.1/P35.6 —
   `build-push.yaml` fires only on push to `main` or `v*` tags).
4. **Stop at the pull-request-ready boundary.** P35.7 (main-merge — a hard gate, since merge to `main`
   auto-deploys via GHCR + Flux) and P35.8 (canonical cutover — a hard gate on changing `origin`) each
   require a separate, explicit Krish approval before any further action. Program B (Phase 36) and any
   Phase 37 remain unauthorized and out of scope until Program A reaches a stable, hosted-verified state
   and Krish opens them explicitly.

---

## 1. Verified repository facts (shared ground truth)

- **Histories diverged; the org repo is not a pure clone.** Merge base `6593759` (P26.0a, Jul 21),
  reproduced and re-verified in P35.1. Our side: **105 commits** (P26→34), HEAD `b3b76cd`. Dean's side:
  **6 commits / 19 files, all deployment**, **zero truth-path changes** (nothing under `schema/` or
  `src/isaac_records/`).
- **Dean's deploy layer:** multi-stage `Dockerfile`; `build-push.yaml`; `spa.py`+`config.py` (FastAPI
  serves SPA under base path); `app.py`/`auth.py` edits (API layer, not truth core); `App.tsx`
  `basename` + `vite.config.ts` `base`; `package.json`(+lock); **deleted `vercel.json`+`railway.json`**;
  `test_base_path.py`; doc edits + `developer-guide-k8s.md`.
- **Deploy triggers (verified):** `build-push.yaml` fires **only** `on push to main` and on `v*` tags.
  **Branch push + PR do not deploy. Merge-to-main and `v*` tags do.**
- **Auth at the edge** (guide §4): Authentik/SLAC SSO, `admin`/`researcher` groups; `ISAAC_UI_API_KEY`
  unset in prod. **No app-level ORCID phase now.**
- **State ephemeral** (guide §5): emptyDir, self-seeds synthetic data; **no SLAC DB wired**.
- **Base-path discipline** (guide §3): served at `/krish`; nav via `ROUTES`, API via `lib/api.ts`,
  assets via Vite.
- **Blue portal = separate, inaccessible repo.** Screenshots = product inventory, navigation
  candidates, visual problems, high-level intent. Screenshots are **not** data contracts, authority
  boundaries, write/persistence/role/API/error semantics, active-usage, or deprecation status.
- **Snapshot drift gate live** (guide §6, CLAUDE.md §17).

## 2. Canonical design system

The canonical product design is the current **Phase 33/34 light application**, verified in
`tokens.css`: light neutral workspace (`--app-canvas #e7ebf0`, `--screen-base #f4f6f9`,
`--surface #ffffff`), **blue** primary accents, restrained semantic colors (teal verified / tan
confirmed / slate inferred / amber needs-you), the **lavender Assistant rail**
(`--assist-panel-bg #f8f8fd`), existing sidebar, typography, cards, spacing, badges, responsive + a11y
patterns. **The dark blue portal is a capability reference only** — do not adopt its dark shell, menu
styling, dense forms, raw error presentation, analytics-table styling, or page composition. Every
integrated capability is rebuilt inside this light system. No colored global rail.

## 3. Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Direction | Our light app is the vessel; capabilities absorbed into it. |
| D2 | Scope | Two programs, phased, gated. |
| D3 | LLM/Claude | Truth core permanently LLM-free; optional isolated read-only assist-layer later; **never a personal key in production**. |
| D4 (revised) | Discovery / nano ISAAC | **Gated on portal access + protocol audit**, not on our LLM; LLM-need decided *after* that audit. Out of MVP. |
| D5 | New capabilities on our data | Native enhancements built on our schema/contracts; genuine portal modules need access. |
| D6 | Migration | History-preserving merge; no force-push; PR into org `main`. |
| D7 | Cutover | Explicit Krish approval before changing `origin`. |
| D8 | Auth | Edge SSO now; app-level roles/ORCID later. |

## 4. Non-negotiable invariants

Truth/validation/evidence/export/no-guessing/reconciliation contracts unchanged · truth plane LLM-free
& Graphify-free · snapshot drift gate · base-path cleanliness · account/continuity policy (no
force-push, no remote/identity change without approval) · data governance (`examples/` unstaged,
synthetic-only) · light design system, no portal-shell leakage · **no dead/placeholder nav in
production** · every new surface ships tests + independent review · PR-only org workflow (no direct
push to org `main` during convergence) · no personal production credentials.

---

## PROGRAM A — Org Repository & S3DF Convergence *(underway; no portal dependency)*

Move the exact current Phase 34 app into the org repo, preserve both histories, retain Dean's deploy
layer, verify under `/krish`, deploy synthetic-only, make the org repo canonical.

### Conflict policy (semantic, not whole-file)

For **every** overlapping file: inspect base + ours + theirs → identify each side's intent → reconcile
both → add/update tests proving both survive. Do **not** predeclare "take Dean's" or "take ours."
Reproduce the real conflict set from a fresh trial-merge. Likely-overlapping: `app.py`, `auth.py`,
`spa.py`/hosting, `vite.config.ts`, `App.tsx` basename, API-base handling, `Dockerfile`,
`package.json`(+lock), health endpoint, CI, `memory-snapshot.json`, deploy docs, `.gitignore`. Rules
that must hold: our P31–34 behavior survives; Dean's single-image SPA hosting + `/krish` survives;
Vercel/Railway stay retired; snapshot **regenerated, never hand-merged**.

### P35.0 — Recontextualization + read-only baseline ✅ COMPLETE

Verify local path, legitimate Phase 34 HEAD `b3b76cd`, clean/dirty state, the uncommitted planning
file, git identity, personal remote, org remote access, org branches/tags, branch protection, workflow
triggers, current deployed commit, no secrets, no account switch, not using stale SLAC Claude config.
Read `CLAUDE.md`, master ledger, P31–34 plans, `developer-guide-k8s.md`; run `/isaac-resume`,
`/isaac-checkpoint`. **Edit nothing.** 🔴 Security: revoke the portal API key exposed in the
screenshot; do not hand Claude a new portal key during convergence; **no personal Claude key in k8s**;
do not capture auth cookies. Deliverable: read-only environment report.

### P35.1 — Two-repo forensic audit *(reproduce, don't trust)* ✅ COMPLETE

Add remotes for the two repos (kept `origin` = personal, added `org`); fetch all branches/tags.
Reproduce: merge base, unique-commit counts + graphs, only-us / only-Dean / both / deleted files,
deploy vs product vs truth-path classification, workflow-trigger analysis, semver/tag-collision
analysis. **Run a trial merge to get the true conflict set.** Deliverable: merge base, commit graph,
file-ownership matrix, conflict forecast, recommended direction, hard blockers. **Hard-stop** on: no
common ancestry, rewritten published history, unexpected product/truth-path change, unknown
production-data handling, diverged protected history. None of these hard-stops fired.

### P35.2 — Local history-preserving integration ✅ COMPLETE

From a clean worktree: `git switch -c integration/current-app-s3df org/main`; `git merge origin/main`;
preserve both histories; **no squash, no rebase of published org history, no force-push**; reconcile
overlaps semantically (§ conflict policy); ensure Vercel/Railway stay removed; regenerate the snapshot.
**Do not push.** Committed locally at `e83a0ce`.
Acceptance (met): all P31–34 commits visible; Dean's infra commits visible; no force-push; nothing
dropped; no truth-path regression; one frontend + one backend, no duplicated tree.

### P35.3 — Single-image + `/krish` verification ✅ COMPLETE (functional simulation)

Frontend compiles into the image; FastAPI serves the SPA; deep-link refresh + SPA fallback; router
`basename`; all API via `API_BASE`; **no hardcoded root-relative nav or `fetch("/api…")`**; assets
honor base path; health reports exact commit; local dev still works at root; prod simulation works
under `/krish`; matching FE/BE in one image; no Railway/Vercel runtime dependency. Verified via a
functional uvicorn simulation (green); the actual Docker image build + smoke is deferred to the P35.7
CI run, since Docker is unavailable locally and org CI does not build the image on branch/PR.

### P35.4 — Documentation, policy, ephemeral-contract confirmation *(this document)*

Author this approved plan as a tracked file; update `CLAUDE.md` §10/§17 to the risk-tiered
orchestration policy; reconcile deployment docs with the verified S3DF architecture; regenerate the
committed snapshot deterministically. Also confirms the ephemeral synthetic deployment contract already
documented in `docs/deployment.md`/`docs/developer-guide-k8s.md`: emptyDir behavior, synthetic
reseeding, restart behavior, export non-durability, no duplicate/corrupt records after restart,
Assistant/Project-Memory ephemerality + snapshot determinism, no false durability claims, no real/
private data, no DB.

### P35.5 — Full release verification *(next)*

Full backend + frontend suites · TypeScript · Vite prod build · base-path tests · synthetic demo ·
truth validation · evidence audit · snapshot `--check` + committed-snapshot gate · secret/path/
raw-content/hardcoded-route/hardcoded-API/`.only`-and-disabled-test scans · **independent Opus
review**. Fix every Critical + Important finding. (Docker build + smoke remains deferred to P35.7's
CI run — not part of this local/PR-time battery.)

### P35.6 — Org branch + PR gate *(safe: branch push does not deploy)*

Report branch, exact diff, commit graph, files changed, test results, and confirm (verified) that
branch push does **not** build/tag/deploy. **Checkpoint for Krish approval before the first org
push.** After approval: push the integration branch, open a PR, **do not merge**, request Dean review
(Docker, FastAPI SPA hosting, `/krish`, Actions, GHCR tags, Flux, resources, health, infra ownership).

### P35.7 — Main-merge + deployment gate *(EXECUTED 2026-07-24 — see closure doc §2)*

> **Executed:** merged via Create-a-merge-commit → `8a10ed5` (parents `[010f3c7, f5c519e]`); build run
> `30114677296` success; image digest `sha256:643716b5…`, tag `v0.0.3`; Opus review SHIP; hosted
> `/krish/api/health` `commit: 8a10ed5`, `synthetic-only` (Krish-verified). Status: `COMPLETE —
> DEPLOYED AND RUNNING SHA VERIFIED; HUMAN RESPONSIVE GATE PARTIALLY OPEN`. Original plan text follows.

Report exact approved head, CI status, Dean review status, expected image/tag, rollback commit,
expected deployment impact. **Stop for explicit Krish approval — merge to `main` triggers GHCR build +
Flux rollout.** After approval: merge normally; confirm CI, image build, semver tag (no collision,
never `:latest`), Flux rollout, `/krish/api/health` = merged commit; run authenticated hosted QA (My
Experiments, record editor, Guided Completion, Evidence, Project Memory, Search, Governance & Safety,
Settings, deterministic Assistant, deep-link refresh, assets, same-origin API, console/network,
synthetic mode); confirm exact running commit.

### P35.8 — Canonical cutover gate *(EXECUTED 2026-07-24 — git-local complete; retirement pending — see closure doc §2)*

> **Executed:** remotes remapped (`origin`→org, `personal`→Krish); local `main` ff to `8a10ed5`
> tracking `origin/main`; integration worktree + local/remote merged branch removed; stale draft
> removed. No force-push, no personal-repo push. **Personal-deploy retirement (Vercel `isaac-demo-web`
> + Railway service) is PENDING Krish's dashboard disable-not-delete action.** Original plan follows.

After hosted verification, **stop again before** changing local `origin`, archiving/freezing the
personal repo, or disabling Vercel/Railway/ownership. Present exact cutover actions for approval. Final
state: org repo canonical; local `origin` → org; personal repo = read-only historical mirror; personal
deploy hooks disabled **only after S3DF is stable**; no parallel production work.

---

## PROGRAM B — Capability Integration *(native enhancements AUTHORIZED as Phase 36 on 2026-07-24; portal integrations + real-data + Phase 37 still hard-gated / NOT AUTHORIZED)*

> **Phase 36 (native enhancements) is authorized and sequenced in a dedicated plan** —
> `docs/superpowers/plans/2026-07-24-phase-36-native-enhancements-plan.md` (capability matrix + slice
> order). The **portal integrations** below (Discovery, Ontology Editor, System Overview, API Keys,
> record consolidation, roles, persistence) remain **blocked on portal access and NOT authorized**.

### Native enhancements (buildable from our own contracts — NOT "portal parity")

After Program A reaches a stable, hosted-verified state and is explicitly opened, these need no portal
access and add minimally to the light shell:
- **Record Validator** inside **Governance & Safety** — JSON upload → official schema + vocabulary
  validation, structured errors, no mutation, no raw-file persistence. Integrated workflow validator
  stays authoritative.
- **API Documentation** under **Developer** — generated from our canonical FastAPI/OpenAPI contract;
  don't expose privileged endpoints to unauthorized users.
- **About / Help** under **Settings** — provenance, schema version, build SHA.
- **New Record** — extend the existing editor only where a field/enum/nested/validation **coverage
  audit** proves a real gap. One record-entry flow; no second system.
- *(Optional)* a **native schema/vocabulary browser** — explicitly *not* the portal Ontology Editor.

### Portal integrations (require access — no implementation from screenshots)

- **P36.0 Obtain portal access + per-module audit** (purpose, users, backend owner, API contract, DB
  tables, auth claims, write semantics, scientific authority, data sensitivity, tests, perf, migration
  complexity, active/deprecated).
- **P36.1 Capability matrix** — classify every module Keep / Merge / Retire / Link / Defer with
  destination + dependencies.
- **P36.2 Final IA** (destinations appear only when functional):
  - **Research:** My Experiments · Discovery · Project Memory · Ontology
  - **Trust:** Governance & Safety
  - **Developer:** System Overview · API Documentation · API Keys
  - **Personal:** Settings · Help/About
- **P36.3+ module integration**, sequenced by the audit:
  - **Discovery** — reuse its backend/protocol; rebuild the frontend in our light shell; Assistant
    context-aware but **read-only, no silent writes**; determine LLM-need only after the protocol
    audit.
  - **Ontology Editor** — only after confirming what it actually holds (vocabulary beyond the schema,
    proposal/review/approval state, applied-change history, concept graph, attribution, role
    enforcement, persistence). Prefer **Propose→Review→Approve→Apply**.
  - **System Overview** — integrate real analytics only after verifying data source/audience/access/
    privacy; **role-gate to admin, redact raw IPs/usernames**. Do not fabricate parity from synthetic
    local metrics.
  - **API Keys** — defer until identity + role enforcement + key backend contract + create/revoke
    ownership + secret handling are known; show once, never re-display, revocable, never logged. No
    decorative page.
  - **Record consolidation, Developer/Ops tools, roles, persistence** — per audit.

---

## 5. Boundaries

- **Auth & roles:** Authentik edge = current authN boundary. App-level authZ
  (Researcher/Reviewer/Ontology-Editor/Developer/Ops) mapped from Authentik claims — later, no second
  login. ORCID only as later identity enrichment, never replacing working SSO.
- **Persistence & real data:** ephemeral synthetic first. Real DB is a separate high-risk staged phase:
  read-only conn → compat report → synthetic migration rehearsal → staging DB → limited internal
  records → security review → prod cutover. **Never emptyDir→prod-writes directly.** Classify data
  (public/internal/private/export-controlled) before any real records.
- **LLM:** no personal Claude key in Program A or early B; truth core permanently LLM-free. An optional
  read-only assist-layer (explanation/summarization/ontology draft text/Discovery help) only after
  institutional approval + institution-owned credential + billing owner + k8s secret + retention +
  prompt-data policy + rate/cost controls + fallback + read-only guarantees. Discovery's LLM-need
  evaluated independently.

## 6. Testing & independent review

Every phase gate = the P35.5 battery. Independent Opus review before the PR (P35.6) and before the
main-merge (P35.7). New capabilities (Program B native) each ship with tests mirroring existing
patterns + review.

## 7. Rollback

App-level: `git revert` + push to main → new image → Flux rolls forward to the reverted state (our
control). Infra-level: semver pin lives in `ISAAC-DOE/isaac-k8` (Dean/infra). No manual cluster
mutation as the normal path.

## 8. Risks

Merge mis-resolution (→ full battery + review); base-path regressions in newer P27–34 code (→ P35.3
audit + tests); snapshot drift (→ regenerate); **accidental `main` push or `v*` tag auto-deploying**
(→ hard gates P35.7); ephemeral data-loss surprise (→ P35.4 contract + no durability claims); exposed
portal key (→ revoke now); personal-repo stale deploys (→ disable after stable); scope creep into
portal modules without contracts (→ Program B access gate); portal dark-shell/theme leakage (→
canonical light system); Docker build/smoke unverified before P35.7 (→ deferred but tracked, first
real exercise happens under CI at the P35.7 gate, not silently skipped).

## 9. Definition of success

Org repo holds full P31–34 + Dean's infra history; current light UI/behavior runs unchanged at
`/krish`; CI builds one tested image; Flux serves the exact commit; Authentik protects it; no
Railway/Vercel remains; personal repo no longer an active prod source; native enhancements
(Validator/API-Docs/About/New-Record) live on our contracts; portal modules + persistence + roles +
Claude introduced only through approved, staged, credential-governed phases; truth + no-guessing
boundaries intact throughout.
