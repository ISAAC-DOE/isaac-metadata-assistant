# SLAC Account & Toolchain Reconciliation — Plan (ACCEPTED)

**Status: ACCEPTED 2026-07-20 — decisions ratified by the user; R1–R6 authorized for execution.
P25.4 remains BLOCKED until this reconciliation gate is complete and reviewed.**

> **Execution checkpoint 2026-07-20 — R1–R6 COMPLETE.** All six slices are on `origin/main`
> (R1 `3ac9b31` · R2 `a6709d7` · R3 `936c654` · R4 `6a06df3` · R6 `230ada4`; R5 was verification-only,
> no commit). Every exact-HEAD CI run is green. Hosted production E2E QA verified GREEN (R5). Two
> independent Opus reviews passed (plan + final R1–R6, both APPROVED-WITH-MINORS). **P25.4 remains
> BLOCKED pending the user's review of the reconciliation report.** Non-blocking follow-ups (all gated):
> optional removal of the residual global `context-mode-cache-heal.mjs` hook (a `~/.claude` edit); any
> account migration/relink (handoff gate); an optional `graphify update` + snapshot regen so the new
> governance docs/skills (`infrastructure-ownership.md`, `toolchain-reconnection-runbook.md`,
> `isaac-checkpoint`, `isaac-resume`) enter the served manifest.

Date: 2026-07-20
Orchestrator: **Opus 4.8** (ratified standing fallback; Fable 5 availability under the SLAC org is a
model-picker UI fact not verifiable from the CLI — use Fable 5 as orchestrator only when it is
actually available in the account, otherwise Opus 4.8). The orchestrator plans/reviews/verifies and
**does not implement production code**.
Baseline commit (verified): `9ff4c54` (`main`, synchronized with `origin/main`; CI run `29772306721`
green; working tree clean aside from this plan file).

All findings below came from read-only, non-destructive probes. This plan is now an **execution**
plan: it authorizes the documentation, project-scoped configuration, continuity-skill, and
verification work in R1–R6. It authorizes **no** migration, ownership transfer, interactive login,
secret change, global `~/.claude` edit, or product implementation. Every such action stays behind an
explicit approval gate (see §Approval gates).

---

## 0. Verified state (evidence, not assumption)

| Claim in accepted checkpoint | Verdict | Evidence |
|---|---|---|
| HEAD = `9ff4c54` | ✅ confirmed | `git rev-parse HEAD` |
| `main` clean & synced with remote | ✅ confirmed | `git status -sb` clean; `git ls-remote origin main` = HEAD |
| P25.1 / P25.2 released | ✅ confirmed | commits `ee60367`,`83aa5b8`,`7e5a86c`; `8eab6ba`,`5a0c049` |
| P25.3 tombstone | ✅ confirmed | phase-25 plan §status |
| P25.4 not started | ✅ confirmed | no P25.4 commits in history |
| CI run `29772306721` green | ✅ confirmed | `gh run view` — both jobs success on `9ff4c54` |
| No `/checkpoint` / `/resume` / `/phase` / `/verify-ui` command | ✅ confirmed | absent in repo, user, and all plugin `commands/` dirs — they were prose workflow names, never installed commands |
| Frontend *fallback* API base is localhost | ✅ confirmed (source only) | `apps/web/src/lib/api.ts:40-41` |
| **Hosted build points at localhost (mixed content)** | ❌ **REFUTED** | live bundle targets Railway HTTPS `/api`; zero localhost request-base matches — see §5 / DECISION 6 |
| Hosted Vercel→Railway wiring | ⚠️ base URL + CORS verified; **authenticated hosted E2E still to be proven** | bundle→Railway correct; `/api/health` 200 at HEAD; CORS echoes prod origin; unauth data call = 401 — see §5 / R5 |

---

## 1. What persisted vs. what changed (account-transition analysis)

**Repository-persistent (unaffected by the account switch):** all tracked source, `CLAUDE.md`,
`AGENTS.md`, `schema/`, full `docs/` tree, plan docs + specs, git history. Nothing was lost.

**Machine-persistent (unaffected):** global CLI installs (`gh` 2.93, `railway` 5.26, `vercel` 54.20,
`graphify` 0.9.4), `graphify-out/` graph (built 2026-07-18), local `dist/` build (stale),
user-global `~/.claude` skills/hooks/plugins.

**Account-scoped (this is what changed):** Claude Code is now on the SLAC org **"ISAAC"**
(`claude_team`, role `user`), the SLAC org account. `mcp__claude_ai_*` connectors are
provisioned org-side.

> **Managed-policy scope (corrected wording).** No local managed-settings file or local hard-policy
> configuration was discovered on the machine (`~/.claude/policy-limits.json` sets only
> `allow_quick_web_setup:false`). **Server-side organization policy was not independently verifiable
> from the local filesystem.** Do not assert "the SLAC org pushes no hard managed policy" — only that
> none was locally observable.

**External-service state (did NOT switch with Claude):** GitHub, Railway, and Vercel remain on
**personal** Krish-owned accounts (§3, DECISION 1). The SLAC Claude login did not touch them.

---

## 2. Persistent-instruction ownership (DECISION 4 — ratified)

No file is missing; `CLAUDE.md` and `AGENTS.md` both exist and are current. Ownership is **ratified**,
not rewritten. No rule is duplicated across files without one authoritative owner — link, don't copy.

| Category | Authoritative owner | Action |
|---|---|---|
| Tool-independent repo rules: purpose, truth-core authority, truth/memory separation, no-guessing, synthetic-only governance, no real/private SLAC data without approval, protected files, verification & reporting expectations, security/deployment safeguards, **"preserve existing project ownership & service identities unless an authorized migration plan changes them"** | `AGENTS.md` | ratify; add only the one-line ownership-preservation principle |
| Claude-specific workflow: Fable 5 / Opus 4.8 orchestrator selection, orchestrator-does-not-implement, Opus/Sonnet assignment, Graphify discovery, Chrome/browser model rule, repo skill inventory, snapshot preflight, slice reports, commit/push/deploy gates, **account-transition + default-account policy**, continuity workflow | `CLAUDE.md` | ratify; add orchestrator-fallback line, the "`/checkpoint` `/resume` `/phase` `/verify-ui` were prose names, not installed commands" clarification, the default-account policy, and the snapshot-preflight sequence |
| Account-switch reconnection / recovery runbook | **NEW** `docs/toolchain-reconnection-runbook.md` | create in R6; other files link to it |

---

## 3. External CLI / account status (DECISION 1 + default-account policy)

| Service | Identity (read-only) | Linkage | Ownership | Login/relink required? |
|---|---|---|---|---|
| GitHub (`gh` 2.93) | `Krish-Verma`, ADMIN on `Krish-Verma/isaac-metadata-assistant` | repo remote OK | **Personal** | No |
| Railway (5.26) | personal Krish account (gmail) | **LINKED, Online** → `isaac-metadata-assistant-production.up.railway.app` | **Personal** | No (do not re-login unless a fresh read-only probe proves the session expired) |
| Vercel (54.20) | personal account, team `krish2808` | project `isaac-demo-web` exists & GitHub-deploys; repo **not** CLI-linked | **Personal** | `vercel link` only if an approved op needs CLI project operations (DECISION 2) |
| Claude Code | SLAC org account, org "ISAAC" | on SLAC | **SLAC** | No |
| Graphify (0.9.4) | machine-local, no auth | `graphify-out/` present | machine-local | No |
| Browser (Claude-in-Chrome) | local, connected | connected | n/a | No |

**DECISION 1 — infrastructure ownership: UNCHANGED for now.** GitHub personal `Krish-Verma`; Railway
personal account linked to production; Vercel personal team `krish2808`; Claude Code SLAC org. **Do not
migrate, transfer, relink, log out, or change ownership.** Rationale: no SLAC infra team, destination
org, project owner, billing/secrets/deployment owner, or migration requirements have been supplied; an
uncoordinated migration could break deployment or access; current infrastructure functions.

Document externally-facing as: **"Temporary developer-owned personal infrastructure pending an explicit
SLAC ownership and handoff decision."** Do not put personal emails, tokens, or private account
identifiers in public-facing docs — the generic statement suffices.

**Future handoff gate (must be satisfied before any migration):** named SLAC owner · destination
GitHub org · destination Railway/Vercel team or approved replacement · billing owner · secrets owner ·
deployment owner · rollback plan · verified transfer procedure. Personal ownership is **not** the
intended final institutional architecture.

**Default-account policy (persisted in `CLAUDE.md` + runbook):** preserve the currently connected,
Krish-owned service identities for ISAAC unless the user explicitly authorizes a different account. Do
not switch identity, log out a working account, relink, create duplicate projects, change teams/orgs,
alter billing, rotate credentials, or change git remotes without explicit per-action approval.

---

## 4. Tooling inventory

- **Repo `.claude/`:** `settings.local.json` (**untracked** local file; single allow
  `...ctx_batch_execute`) + 5 tracked `isaac-*` skills (`.claude/skills/<name>/SKILL.md`). No
  `commands/`, `agents/`, `hooks/`, `.mcp.json`.
- **User `~/.claude/`:** skills `deploy-to-vercel`, `vercel-cli-with-tokens`, `graphify`; SessionStart
  hook `context-mode-cache-heal.mjs`; `model: opus[1m]`, `effortLevel: xhigh`.
- **Plugins enabled (global):** `superpowers`, `vercel`, `frontend-design`; `claude-mem`,
  `playwright-skill`, **`context-mode` (3rd-party git)**.
- **`/checkpoint` `/resume` `/phase` `/verify-ui`: ABSENT** everywhere — prose workflow names, not
  installed commands (DECISION 4 clarification). DECISION 5 replaces the two continuity ones with
  tracked, repo-local, collision-free skills `isaac-checkpoint` / `isaac-resume`; `/phase` and
  `/verify-ui` are **not** created; a manual procedure is documented as fallback.

---

## 5. Deployment-wiring findings (DECISION 6 correction)

**Mechanism:** `apps/web/src/lib/api.ts:40-41` — `VITE_API_BASE ?? 'http://127.0.0.1:8000/api'`. If
`VITE_API_BASE` is unset at build time (as in a bare local `vite build`), localhost is baked in. Split
hosting is by design (`Dockerfile`/`.dockerignore` exclude `apps/web`: Railway = backend, Vercel =
frontend); backend CORS is overridden live by `ISAAC_UI_CORS_ORIGINS`.

**Live production verdict (public read-only fetch — DEFINITIVE):** the accepted-state "hosted build
points at localhost" claim is **REFUTED**. `https://isaac-demo-web.vercel.app` returns 200; its bundle
targets `https://isaac-metadata-assistant-production.up.railway.app/api` with **zero** localhost
request-base matches. Railway `/api/health` returns 200 with `commit` = HEAD. CORS is **correct** — the
backend echoes `access-control-allow-origin: https://isaac-demo-web.vercel.app` on GET and the OPTIONS
preflight and allows `Authorization`. Unauthenticated `GET /api/experiments` correctly returns **401**
(`ISAAC_UI_API_KEY` gating is enabled; health stays public). Localhost existed only in the *local*
`dist/` built with the env var unset.

> **DECISION 6 correction (to be applied to living status/checkpoint docs, not to historical commits):**
> "A local production build created without Vercel environment variables targeted localhost. The hosted
> Vercel deployment targets the Railway HTTPS API correctly. Previous checkpoint wording conflated the
> local preview bundle with the hosted production bundle."

**Corrected "everything functions" wording:** repository access, CLIs, the deployment base URL, Railway
health, and CORS are functional; **authenticated hosted E2E remains to be verified** (R5).

**Three terms kept distinct in all future reports:** *Hosted shell QA* (page loads past Vercel access
protection) · *Local production-build E2E QA* (`vite preview` of a local build + local backend) ·
*Hosted production E2E QA* (real `isaac-demo-web.vercel.app` frontend → live Railway API,
authenticated).

---

## Model & delegation rule (ratified)

- Orchestrator (Fable 5 when available, else Opus 4.8): plan, review, verify — **no production code.**
- Instruction-architecture & security-sensitive implementation → **Opus 4.8** subagent.
- Mechanical documentation & inventory changes → **Sonnet 5** subagent.
- Browser QA → Opus 4.8 or Sonnet 5 (orchestrator may run it directly as verifier if the
  browser/extension context is more reliable in-loop).
- Final independent review → a **separate Opus 4.8** subagent.
- Each slice: own scoped commit · independent review · relevant verification · snapshot preflight
  before push · push only after local verification · confirm exact-HEAD CI · report separately.

---

## Snapshot preflight (persisted in `CLAUDE.md` + `isaac-checkpoint`)

The committed Project Memory snapshot `apps/api/isaac_api/data/memory-snapshot.json` embeds a
`served_content_manifest` (202 files) whose sha256s are re-checked in CI by
`apps/api/tests/test_committed_snapshot.py` (Branch B). The manifest **includes** `CLAUDE.md`,
`AGENTS.md`, all `docs/*.md`, and each `.claude/skills/*/SKILL.md`. **Editing any manifest-listed file
is predictable drift** and must be reconciled in the same commit. New/untracked files (this plan, new
skills, the new runbook, post-2026-07-18 docs) are not in the manifest and do not drift the gate.

Pre-push sequence — do not wait for CI to discover drift:
1. implementation → 2. focused tests → 3. full relevant tests → 4. typecheck / Vite build →
5. **snapshot drift check** → 6. deterministic regeneration if required → 7. path/secret/leak checks →
8. independent review → 9. commit → 10. push → 11. exact-HEAD CI → 12. deployment/browser QA.

Existing commands (documented exactly):
```bash
# drift check (exit 0 = no drift)
.venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json --check
# deterministic regeneration (drop --check), then re-run the check + the gate test
.venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json
.venv/bin/pytest apps/api/tests/test_committed_snapshot.py -q
```

---

## Approved slices (execution order R1 → R6; each independently reviewed & reported)

### R1 — Instruction ownership & status correction *(docs)*
Ratify the §2 ownership model. `CLAUDE.md`: orchestrator-fallback line, "prose-not-commands"
clarification, default-account policy, snapshot-preflight sequence. `AGENTS.md`: the one-line
ownership-preservation principle only. Apply the DECISION 6 correction to the phase-25 living-status
doc (superseding note; no commit rewrite). **Snapshot regen required** (`CLAUDE.md`, `AGENTS.md` are in
the manifest). Own commit → review → verify → preflight → push → CI.

### R2 — Project-scoped context-mode disablement *(config; likely approval gate)*
Do **not** describe context-mode as malicious — it is installed third-party tooling with unacceptable
project-local reliability & governance risk for ISAAC (SessionStart instruction block; relies on /
mutates `NODE_OPTIONS`; produced a stale shim that broke Node CLIs; runs under the SLAC org account).
Approved sequence: (1) determine the narrowest repo/project-level way to prevent activation for ISAAC;
(2) remove the ISAAC-local allow in `.claude/settings.local.json`; (3) verify normal Claude Code
operation without it; (4) verify `node`, `npm`, frontend tests, TypeScript, Vite build, relevant CLIs;
(5) confirm no stale `NODE_OPTIONS`/shim affects the ISAAC shell.

> **Finding (evidence-based, R2):** `.claude/settings.local.json` is **untracked** and holds only a
> permission *pre-approval*, not an activation switch. context-mode's activation (SessionStart
> injection, PreToolUse nudges, `context-mode-cache-heal.mjs`, `NODE_OPTIONS`) comes from the plugin
> being **enabled globally in `~/.claude`**. Removing the local allow is correct but does **not** stop
> activation. If a true per-project disable is unavailable and only a **global `~/.claude` change**
> works, that is an approval-gated global edit: do not make it automatically — report the exact change,
> its effect on other projects, and stop.

### R3 — External ownership decision recorded; no migration/relink *(docs)*
Record DECISION 1 (ownership unchanged; developer-owned pending handoff), the future handoff gate, and
the default-account policy. **No** migration, relink, logout, or duplicate-project creation. Enumerate
exact human login gates (below). Own commit → review → report.

### R4 — Continuity skills `isaac-checkpoint` + `isaac-resume` *(repo-local skills)*
Create two tracked, repo-local, secret-free skills in the existing `.claude/skills/<name>/SKILL.md`
format (collision-free names; not `/checkpoint`/`/resume`). `isaac-checkpoint`: inspect branch / tree /
ahead-behind / recent commits; classify changed files; update the active phase/status section when
appropriate; run snapshot drift preflight when served files changed; refuse destructive Git; refuse
deployment unless separately authorized; commit/push only explicitly-safe scoped docs when allowed;
output REPO / COMMITTED / VERIFIED / NOT VERIFIED / BLOCKED / NEXT HUMAN ACTION. `isaac-resume`:
inspect real repo/remote state; read decision lock, roadmap, active phase plan/spec, latest checkpoint;
identify the authorized slice and what is not authorized; detect uncommitted/unpushed work; state the
next safe action; implement nothing automatically. Add dry-run/verification where the format permits. A
manual procedure stays documented (in the runbook) for accounts that can't load repo-local skills. `/phase`
and `/verify-ui` are **not** created. `CLAUDE.md` skill inventory updated (**snapshot regen required**).
Own commit → review → verify → preflight → push → CI.

### R5 — Hosted authenticated E2E verification *(verification)*
Label all output **"Hosted production E2E QA."** First verify presence/configuration metadata only
(Vercel prod has the required `VITE_API_*` variable configured; preview/dev scope identified; Railway
API auth enabled) **without printing/comparing raw secret values** — lead with observable network
evidence, not secret listing. Then open the real hosted frontend and inspect live traffic: (1) requests
go to the Railway HTTPS host; (2) none to localhost; (3) include the expected auth mechanism;
(4) authenticated calls succeed; (5) no 401s from valid requests; (6) no CORS errors; (7) no
mixed-content; (8) no console errors; (9) `/api/health` matches deployed HEAD; (10) real hosted
synthetic data loads on My Experiments, Record Workbench, Ready to Export, Project Memory, Source Index,
Concept Lookup; (11) P25.1 live composer behavior; (12) P25.2 Guided Prompts Only behavior. If auth
fails, diagnose (missing Vercel var · wrong env scope · stale build · credential mismatch · frontend not
attaching token · Railway auth config) — **do not weaken or disable auth; do not redesign auth here.**
Report → gate.

### R6 — Reconnection runbook & final documentation corrections *(docs)*
Author `docs/toolchain-reconnection-runbook.md` (Claude account switches; GitHub/Railway/Vercel/Graphify
/browser auth checks; account vs machine scope; no-secret reporting; login gates; ownership-transfer
gates; recovery; default-account policy). Fix "hosted E2E" vs "local-preview" vs "hosted-shell"
terminology across status docs; refresh `docs/deployment.md`. Docs editing manifest-listed files
(`deployment.md`, `README.md`) → **snapshot regen required**. Own commit → review → verify → preflight →
push → CI.

**Then final gate:** run `isaac-checkpoint`; verify clean/in-sync branch; confirm all CI runs; report
hosted production E2E status, remaining account/tool limitations, whether human login is still required,
context-mode status, installed continuity skills, exact roadmap position. **Stop before P25.4.**

---

## Browser-visible credential limitation (security clarification — persisted)

Any `VITE_`-prefixed variable is **compiled into client-side JavaScript**. Therefore `VITE_API_KEY` is
**not a private secret** — it is a **browser-visible shared demo credential**. Vercel access protection
limits who can reach the app; the key is acceptable **only** for the current synthetic-demo boundary and
is **not** institutional user authentication. Institutional SSO and per-user authorization remain
deferred and institution-owned. Do not expose the value in reports/logs even though it is technically
retrievable from a client bundle. Do not redesign authentication during this reconciliation.

---

## CLI installation authorization (persisted)

Authorized to install CLIs genuinely necessary to inspect/verify/build/test/deploy/maintain ISAAC,
after: checking whether already installed; recording version; confirming it is not merely off `PATH`;
preferring the official channel and the machine's existing package manager; user-scoped/Homebrew-style
(no `sudo`); avoiding duplicate installs; confirming relevance. Report name / source / version / path /
auth-required / global-files-changed / cross-project effect. Do not reinstall or upgrade a functioning
CLI merely to make it newer.

---

## Approval gates (stop and ask before any of these; report exact command · why · account · team ·
reversibility · resources changed · safest alternative · what stays blocked if denied)

Interactive/device login · logout · account switch · link/relink a cloud project · create a new
cloud project · move to a different team/org · ownership/billing transfer · add/change/rotate/reveal
secrets · change prod/preview env vars · modify global Claude config · modify global shell profiles
(`.zshrc`) · `sudo` installs · system/browser extensions or privileged agents · new paid plans ·
org-wide settings · disable a plugin **globally** when a project-local disable is possible · delete/
overwrite an existing project linkage · anything affecting projects outside ISAAC.

**Human login gates (exact commands; none run here):** `vercel link` (CLI-deploy this repo — offers
personal `krish2808`); `vercel logout`/`login`; `railway logout`/`login` then `railway status`;
`gh repo transfer` (GitHub org migration). All optional and gated on a human ownership decision.

---

## After R1–R6: resume product roadmap (unchanged accepted order)
**P25.4** Ground Export context → **P25.5** Ground Evidence → **P25.6** Ground Complete → **P25.7**
Ground Project Memory → **P25.8** retain excluded non-record screens → **P25.9** retire remaining static
assistant samples → **P25.10** full Phase 25 verification & release → **Phase 26** Workspace + Project
Memory Search → UI Refinement & Visual QA → Final Stabilization → Documentation & Deliverables →
optional post-core Convex evaluation → deferred back-burner. **P25.4 stays BLOCKED until this
reconciliation gate is complete and the report reviewed.**

---

## R4.1 follow-up (2026-07-20) — toolset-profile separation + `isaac-profile`

> **Separately authorized after R1–R6.** R1–R6 remain **COMPLETE** and unchanged (see the execution
> checkpoint at the top of this plan). This section is **append-only**; it revises nothing above.

**Selected architecture: A1 — supported toolset-only separation.** Claude Code `2.1.211` isolates
*tooling* per config root via `CLAUDE_CONFIG_DIR` (plugins, MCP, hooks, skills, settings, caches).
Authentication is **NOT** isolated: it is a **shared macOS Keychain item** (`"Claude Code-credentials"`)
that lives outside any config root. A2 and every unsupported mechanism —
`CLAUDE_CODE_HOST_CREDS_FILE`, plaintext OAuth files, credential copying, Keychain manipulation,
automated account switching — are **rejected and out of scope**.

**Consequence (stated honestly):** the two launchers select different Claude **tool environments**, not
guaranteed Claude **accounts**. The launcher marker is a *claimed toolset mode*, never proof of the
signed-in account; the normal Claude login (shared Keychain) still determines the account.

**Delivered:**
- `~/.claude-slac/` — minimal SLAC toolset root; context-mode absent (fresh root) and explicitly
  disabled; no copied credentials, no personal MCP/plugins.
- `~/.local/bin/claude-personal` — default root `~/.claude` (personal tooling incl. context-mode),
  marker `personal`; does not set `CLAUDE_CONFIG_DIR`.
- `~/.local/bin/claude-slac` — `CLAUDE_CONFIG_DIR=$HOME/.claude-slac`, marker `slac`.
- `.claude/skills/isaac-profile/SKILL.md` — the **runtime guardrail**: read-only; reports launcher
  marker, effective config root, best-effort (non-secret) account context, model, orchestrator,
  context-mode state, tools/MCP/services, and refreshed durable context; emits
  `PROFILE CONFIGURATION MISMATCH` when marker/root/account disagree and
  `UNKNOWN — Claude account context could not be established safely.` when the account cannot be
  established safely; mutates nothing (no login/logout/switch, no credential read, no settings edit, no
  plugin install, no commit/push/deploy).

**Not done (by design):** no shell startup file edited; no plugin installed into either root; no
credential/Keychain/login action; external service identities (GitHub/Railway/Vercel) untouched.

**Empirical finding:** the R2 project-scope context-mode disable does **not** suppress context-mode's
user-scope `SessionStart`/`PreToolUse` hooks inside an ISAAC session — which validates *root separation*
(a root that simply never installs context-mode) as the sound control, rather than relying on a
project-scope disable.

**Snapshot:** the new `isaac-profile` SKILL.md is not in the committed 2026-07-18 served manifest, so it
does **not** drift the gate (`build_memory_snapshot.py --check` = no drift; `test_committed_snapshot.py`
green). It enters the manifest only at the single authorized **final** Graphify/snapshot refresh,
together with `isaac-checkpoint`/`isaac-resume`.

**One manual verification (safe, ~30s, human-run in a real terminal):** a live "fresh process" check was
not run from inside a Claude session, because launching a new `CLAUDE_CONFIG_DIR` risks a first-run trust
prompt and nested auth against the shared Keychain. To confirm the SLAC toolset live, a human runs
`claude-slac` in a terminal and confirms context-mode's tools / SessionStart injection are absent. Static
config-root inspection already confirms context-mode is not installed in `~/.claude-slac`.

**Fresh-process verification COMPLETED (2026-07-21):** this session was launched via `claude-slac` and
re-verified the SLAC toolset live from inside the process: `$ISAAC_CLAUDE_PROFILE=slac`; effective config
root `~/.claude-slac`; context-mode **absent** (not installed — `plugins:{}` in the SLAC root — and
disabled in settings) with **no** context-mode `SessionStart`/`PreToolUse` injection and no context-mode
MCP tools/skills loaded; `$NODE_OPTIONS` unset (no shim); `node --version`/`npm --version` succeed;
repo-local skills (`isaac-profile`, `isaac-resume`, `isaac-checkpoint`, …) load. The Claude **account**
is reported `UNKNOWN` — expected and acceptable, because auth is a shared macOS Keychain item outside
`CLAUDE_CONFIG_DIR`; GitHub/Railway/Vercel remain the existing Krish-owned identities. **R4.1 is NOT
reopened.** Architecture statement (unchanged, honest): *R4.1 isolates Claude tooling through separate
configuration roots; Claude authentication remains shared through the macOS Keychain and is verified
separately when detectable.*

**Authorization update (supersedes the "P25.4 stays BLOCKED" line above by dated note, not rewrite):**
the 2026-07-20 master authorization lifts the P25.4 block and authorizes **continuous execution** of the
locked core roadmap (R4.1 → P25.4–P25.10 → Phase 26 → UI Refinement → Stabilization → Documentation &
Deliverables → one final Graphify/snapshot refresh). Per-slice report → independent review → commit →
push → exact-HEAD CI → checkpoint is **retained**; the hard-stop gates remain in force; P25.8 stays
excluded; Convex/institutional infrastructure stay off the core path. This changes execution **cadence
only** — it introduces no new architectural decision and stays within the decision lock.

---

## R4.2 follow-up (2026-07-20) — Shared Repository Synchronization Contract

> **Separately authorized continuity follow-up after R4.1.** R1–R6 and R4.1 remain COMPLETE and
> unchanged. This section is **append-only**; it revises nothing above and creates no new product
> phase or replacement roadmap.

**Goal.** Keep personal `claude`, `claude-slac`, the local ISAAC repo, GitHub, CI, Railway, and
Vercel consistent through one clear, safe operating contract — while the two Claude configuration
roots stay intentionally isolated.

**Delivered:**
- **Authoritative contract** — `docs/toolchain-reconnection-runbook.md` →
  "Shared Repository Synchronization Contract": one shared repo / two intentionally different tool
  roots; four repository states (`CLEAN_AND_SYNCHRONIZED`, `ACTIVE_SCOPED_WIP`,
  `INTERRUPTED_SCOPED_WIP`/`INTERRUPTED_UNKNOWN_WIP`, and the unsafe set incl. `WRONG_REPOSITORY`/
  `WRONG_REMOTE`/`WRONG_BRANCH`/`DIRTY_UNKNOWN_WIP`/`DIVERGED`/`REMOTE_ADVANCED_DURING_WIP`/
  `REMOTE_UNAVAILABLE`/`SERVICE_IDENTITY_MISMATCH`/`REQUIRES_HUMAN_REVIEW`); the single
  fast-forward-only auto-reconcile and its clean-tree precondition; dirty/ahead/diverged/
  remote-advanced handling; usage-limit recovery; single-editor rule; profile-switch workflow;
  four synchronization axes; a 40-row decision table.
- **Concise cross-references** — `CLAUDE.md` §17 and this plan point to the contract; the three
  continuity skills reference it rather than restating it (one authoritative home).
- **Skill strengthening** — `isaac-profile` (four-axis summary + single-editor/interrupted-work
  warning + one safe next action), `isaac-resume` (safe fetch; ff-only ONLY for clean-behind;
  never pull into dirty; never push; active/interrupted-WIP recovery), `isaac-checkpoint`
  (re-fetch before commit; remote-advanced detection; post-push re-fetch + 0/0 verification;
  four-axis reporting; interruption-safe output).

**Verification (no product code touched):** disposable-repo git simulations (git 2.50.1)
confirmed ff-only reaches 0/0 from clean-behind; diverged aborts (`Not possible to
fast-forward`); non-ff push is rejected; and — the key finding — **ff-only into a *dirty* tree
with unrelated changes succeeds and moves HEAD**, so the skills gate on a clean tree themselves
rather than relying on git to refuse. Non-git scenarios (CI/Vercel/Railway axes, identity
mismatch, second-session) verified as declarative dry-runs against the decision table.

**Deferred (approved fallback, not built):** a machine-local `.git/isaac-session-state.json` —
`DEFERRED — approved fallback, not currently necessary`. Existing Git state + checkpoint docs
suffice; it may be added later only via a separately reviewed slice.

**Scope:** continuity/workflow only. No truth core, schema, validation, frontend/backend product
behavior, API, env/deploy config, auth, billing, ownership, or Phase 25 product implementation
was modified. Product position unchanged: **P25.6 (Complete Missing Fields context) remains the
active authorized slice**; P25.8 excluded.
