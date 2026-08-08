# Toolchain Reconnection Runbook

How to reconcile ISAAC's toolchain after a Claude account switch or an interrupted/reset
session — **without** migrating ownership or logging into anything uninvited.

**Status:** living doc.

Cross-links:
- `docs/infrastructure-ownership.md` — the ownership decision, the future handoff gate, and
  the human login gates (do not duplicate; link to it).
- `CLAUDE.md` §16 (Resume Protocol) and §17 (Account, Continuity & Snapshot Preflight).

---

## Account scope vs machine scope

What persists where, so a Claude account switch is not mistaken for a service-account switch:

- **Repository-persistent** — all tracked source, `CLAUDE.md`/`AGENTS.md`, schema, docs, git
  history. Follows the repo regardless of which Claude account is active.
- **Machine-persistent** — global CLI installs (`gh`, `railway`, `vercel`, `graphify`),
  `graphify-out/` (gitignored, local-only), `~/.claude` skills/hooks/plugins. Tied to the
  local machine, not the repo or the Claude account.
- **Account-scoped** — which Claude account/org is active, and any org-provisioned MCP
  connectors. This is what actually changes on a Claude account switch.
- **External-service state** — GitHub/Railway/Vercel accounts. These do **not** switch when
  the Claude account switches; they stay on whatever identity was last logged in locally.

---

## Default-account policy

Preserve the currently connected, developer-owned service identities (GitHub, Railway,
Vercel) unless the user explicitly authorizes a different account. Claude Code running
under the SLAC org account is **not** a reason to migrate the other services.

The full policy and do-not list lives in `docs/infrastructure-ownership.md` and
`CLAUDE.md` §17 — link, do not duplicate here.

---

## Read-only reconnection checks (run these FIRST; none change state)

| Service | Read-only check | Expected |
|---|---|---|
| Claude Code | note the active account/org | SLAC org "ISAAC" |
| GitHub | `gh auth status` | logged in to the existing personal account, scopes `repo`/`workflow`/`read:org`/`gist`; `git remote -v` unchanged |
| Railway | `railway whoami`; `railway status` | the existing personal account; project linked and Online; do **not** re-login unless a read-only probe proves the session expired |
| Vercel | `vercel whoami` | the existing personal account; repo not CLI-linked (by design); do **not** run `vercel link` unless an approved op needs it |
| Graphify | `graphify --version` | machine-local, no auth |
| Browser (Claude-in-Chrome) | tab context | connected |
| Deployment | `curl -s <railway>/api/health`; public bundle/CORS checks | health 200 with commit; CORS echoes the Vercel origin; unauth data call 401 |

---

## Shared Repository Synchronization Contract

**Authoritative.** This is the single source for how the two Claude toolsets, the local
repo, GitHub, CI, Railway, and Vercel stay consistent. `CLAUDE.md` §17, `isaac-profile`,
`isaac-resume`, and `isaac-checkpoint` cross-reference this section; they do not restate it.

### One repository, two intentionally different tool environments

Both toolsets operate on the **same** checkout: `~/Documents/ISAAC` — one working tree, one
`.git`, one `origin`, one `main`, one history, one set of tracked plans/specs, one set of
repo-local ISAAC skills, one GitHub repo, one Railway project, one Vercel project, one
production path. Never create separate clones, routine implementation branches, copied repo
directories, duplicate cloud projects, duplicate roadmaps, or profile-specific project files.

The Claude **configuration roots stay different on purpose**: personal `~/.claude`
(context-mode + personal plugins/hooks/MCP) vs. SLAC `~/.claude-slac` (minimal, no
context-mode, Chrome via the `claude-slac` launcher). **Never** copy between the two roots:
credentials, OAuth/Keychain state, cookies, plugin/hook directories, MCP config, caches,
personal skills, context-mode state, or account settings. The requirement is: **same project
state, intentionally different tool environments.**

### Only one editor at a time

Only one Claude session may modify `~/Documents/ISAAC` at a time. The other toolset may be
used for unrelated discussion but must not edit ISAAC files, commit, pull, push, run
migrations, deploy, or start another slice while the first session owns active work. This is
enforced by convention plus a warning, not a lock: `isaac-profile` warns when the shared tree
already shows dirty or interrupted work (which may belong to another session). It cannot
detect another OS process — it reports the shared-tree evidence honestly and does not claim
process-level detection.

### Four repository states

1. **`CLEAN_AND_SYNCHRONIZED`** — the stable boundary expected before switching profiles,
   ending a session, declaring a slice released, or handing off. Repo path correct; branch
   `main`; tree clean; no untracked files needing review; local HEAD == `origin/main`; 0
   ahead; 0 behind; latest checkpoint committed and pushed; exact-HEAD CI status known;
   deployment status explicitly classified; next slice recorded.
2. **`ACTIVE_SCOPED_WIP`** — allowed while exactly one session owns the repo. Tree may be
   dirty; local may be ahead; GitHub may be temporarily behind; CI may not have run; deploy
   may lag. Requires: active slice identifiable; changed files classified; no second session
   editing; no claim that local and GitHub are synchronized; unfinished work preserved.
3. **Interrupted** (usage limit / crash / forced stop / tool or browser outage / subagent
   failure / context exhaustion) — `INTERRUPTED_SCOPED_WIP` when every changed/untracked file
   classifies cleanly to the active slice; `INTERRUPTED_UNKNOWN_WIP` when any does not. A
   dirty tree is acceptable here; **losing or overwriting it is not.** Record completed vs.
   missing verification, unpushed commits, and the exact next action.
4. **Unsafe / ambiguous** — stop automatic synchronization and require human review:
   `WRONG_REPOSITORY`, `WRONG_REMOTE`, `WRONG_BRANCH`, `DIRTY_UNKNOWN_WIP`, `DIVERGED`,
   `REMOTE_ADVANCED_DURING_WIP`, `REMOTE_UNAVAILABLE`, `SERVICE_IDENTITY_MISMATCH`, and the
   catch-all `REQUIRES_HUMAN_REVIEW`.

### The one automatic reconciliation (fast-forward only)

`isaac-resume` may run `git pull --ff-only origin main` **only** when ALL hold: expected repo;
expected `origin`; branch `main`; **working tree clean**; no untracked files needing review;
0 ahead; ≥1 behind; not diverged; fetch succeeded. Afterward verify tree still clean, HEAD ==
`origin/main`, 0 ahead, 0 behind, and report old→new HEAD. **No other automatic pull, merge,
reset, rebase, cherry-pick, stash, or reconciliation is ever allowed.**

**Verified git behavior (disposable-repo simulation, git 2.50.1) — why the clean-tree
precondition is mandatory:** `git pull --ff-only` into a *dirty* tree does **not** reliably
refuse. It aborts only when the dirty change collides with an incoming file
(`your local changes would be overwritten`); when the dirty change is unrelated it
**succeeds and moves HEAD while the dirty change remains** (observed rc=0). Git therefore does
not protect a dirty tree — the skill must gate on a clean tree *itself*, before ever invoking
the pull. Divergence aborts deterministically (`fatal: Not possible to fast-forward,
aborting`); a non-fast-forward push is rejected (`[rejected] non-fast-forward`) and is never
followed by a force.

### Clean but ahead

Clean tree with local commits not on `origin/main` and not behind: `isaac-resume` does **not**
push. It reports the ahead count, the local-only commits, the latest verification state, and
whether they look like completed scoped work, then routes to `isaac-checkpoint`, which may push
only after confirming the work is scoped, required verification passed, the remote has not
advanced, the push is a normal fast-forward, and no hard gate is present.

### Dirty working tree

Never pull, reset, clean, auto-stash, switch branches, overwrite files, or start unrelated
work. Classify every changed/untracked file as: active-slice implementation · active-slice
tests · active-slice docs · status/checkpoint docs · deterministic generated artifact ·
local-only generated file · secret-like/sensitive · migration/config · unrelated · unknown.
Then identify the active slice, what was implemented, tests already run, tests still required,
whether any commit exists, and the exact next safe action — and resume that work rather than
restarting.

### Remote advanced during the session

Re-fetch at checkpoint time. **Clean, no local commits:** a safe `git pull --ff-only` may be
used. **Clean with local commits:** this is divergence — stop; do not push/merge/rebase/reset/
cherry-pick/force; report both ranges. **Dirty:** stop and preserve the tree; do not pull;
classify `REMOTE_ADVANCED_DURING_WIP`; report local HEAD, remote HEAD, changed files, active
slice, and the exact human decision required.

### Divergence

When local and remote each hold unique commits: stop; never auto-resolve, force-push, merge,
rebase, reset, amend, or discard. Report merge base, local-only commits, remote-only commits,
working-tree state, active slice, and whether either side deployed. Require explicit human
approval for the recovery strategy.

### Usage-limit / forced-stop recovery

Do not rush an incomplete implementation into a commit and do not fabricate a "finished"
checkpoint. Preserve all local files. Record: active slice, modified files, tests done, tests
not done, independent-review status, unpushed local commits, current local/remote HEADs, and
the exact next command. If work is fully implemented, verified, reviewed, and safely
committable, `isaac-checkpoint` may commit and push it (within its docs/snapshot commit
boundary; implementation code still needs explicit per-commit authorization); otherwise leave it uncommitted and
dirty, classify it as interrupted scoped WIP, and do not pull or overwrite it next session.
**Never create a commit merely to make the tree clean.**

> **Interruption-state persistence — `DEFERRED — approved fallback, not currently necessary`.**
> Git working-tree state, untracked-file inspection, local/remote commits, the latest committed
> checkpoint, the active plan/status block, and `isaac-profile`/`isaac-resume`/`isaac-checkpoint`
> are currently sufficient to preserve recovery context. If repeated real interruptions prove
> they cannot, a single secret-free, machine-local `.git/isaac-session-state.json` (ignored by
> Git by location, readable by both toolsets, limited to repo-state + next-action metadata) may
> be introduced through a separately reviewed continuity slice. Do not build it now — no file,
> schema, reader, writer, cleanup logic, hook, daemon, watcher, or lock.

### Four independent synchronization axes — never collapse them

Report these separately; "everything is synchronized" is forbidden when only Git is.

1. **Local ↔ GitHub:** synchronized · local ahead · local behind · dirty · diverged · remote unavailable.
2. **GitHub ↔ CI:** exact-HEAD green · running · queued · failed · no run found · unavailable.
3. **GitHub ↔ Vercel:** intended commit deployed · pending · failed · ready-but-mapping-uncertain · not relevant.
4. **GitHub ↔ Railway:** intended commit deployed & healthy · pending · healthy-but-mapping-uncertain · failed · not relevant.

`main` is the deployment branch; pushes trigger the existing CI/deploy flows; deployment can
lag Git; a successful push does not prove production is current; a local build does not prove
hosted behavior. Do not deploy manually or relink cloud projects when auto-deploy is healthy.

### Service identities stay unchanged

Both toolsets keep the existing Krish-owned identities: GitHub `Krish-Verma`, the Krish-owned
Railway ISAAC project, the Krish-owned Vercel ISAAC project; Graphify is machine-local. Startup
checks are read-only (`gh auth status`, `railway whoami`, `vercel whoami`, `git remote -v`); see
"Read-only reconnection checks" above. Never print secrets; never auto login/logout/switch/
relink/duplicate/transfer/rotate/change-remote. An unexpected identity is
`SERVICE_IDENTITY_MISMATCH` — a blocker requiring human review.

### Decision table (observed state → classification → allowed vs. forbidden → next action)

| # | Observed state | Classification | Automatic action ALLOWED | Forbidden | Next action / human approval |
|---|---|---|---|---|---|
| 1 | Expected repo, `main`, clean, HEAD==origin, 0/0 | `CLEAN_AND_SYNCHRONIZED` | none needed | — | Proceed to authorized slice. No approval. |
| 2 | Clean, 1 behind, not diverged | behind | `git pull --ff-only` | merge/rebase/reset | ff, verify 0/0. No approval. |
| 3 | Clean, several behind, not diverged | behind | `git pull --ff-only` | merge/rebase/reset | ff, verify 0/0. No approval. |
| 4 | Clean, local ahead, 0 behind | clean-ahead (`ACTIVE_SCOPED_WIP`) | none (report) | auto-push from resume | Route to `isaac-checkpoint`; it pushes only after gates. |
| 5 | Clean, remote ahead AND local ahead | `DIVERGED` | none | merge/rebase/reset/force/cherry-pick | Report ranges + merge-base. **Human approval.** |
| 6 | Dirty active-slice implementation | `ACTIVE_SCOPED_WIP` / `INTERRUPTED_SCOPED_WIP` | none | pull/reset/clean/stash/switch | Classify, resume the slice. No approval to continue. |
| 7 | Dirty active-slice tests | `ACTIVE_SCOPED_WIP` / `INTERRUPTED_SCOPED_WIP` | none | pull/reset/clean/stash | Classify, resume the slice. No approval. |
| 8 | Dirty unknown/unrelated file | `DIRTY_UNKNOWN_WIP` | none | pull/reset/clean/commit-it | Stop; classify. **Human review of the unknown file.** |
| 9 | Untracked deterministic/generated file | `ACTIVE_SCOPED_WIP` (generated) | none | commit it (unless policy tracks) | Report path; leave/ignore. No approval. |
| 10 | Untracked secret-like file (`.env`, `*.pem`, `id_rsa`, `*credential*`) | `DIRTY_UNKNOWN_WIP` / sensitive | none | stage/commit/push/print | **Stop; never stage. Human review.** |
| 11 | Not the expected ISAAC repo | `WRONG_REPOSITORY` | none | any git write | **Stop. Human.** |
| 12 | `origin` != expected URL | `WRONG_REMOTE` | none | push/pull/change-remote | **Stop. Human.** |
| 13 | Branch != `main` | `WRONG_BRANCH` | none | auto-checkout/commit | **Stop. Human** (explicit switch approval). |
| 14 | Local & remote both have unique commits | `DIVERGED` | none | merge/rebase/reset/force | Report merge-base + ranges. **Human.** |
| 15 | `git fetch` fails / offline | `REMOTE_UNAVAILABLE` | local read-only work | claim "synchronized" | Report offline; no sync claim. No approval. |
| 16 | Remote advanced, clean, no local commits | behind | `git pull --ff-only` | merge/rebase/reset | ff, verify 0/0. No approval. |
| 17 | Remote advanced, clean, local commits exist | `DIVERGED` | none | push/merge/rebase/force | **Stop. Human.** |
| 18 | Remote advanced while tree dirty | `REMOTE_ADVANCED_DURING_WIP` | none | pull/merge/reset/stash | Preserve tree; report HEADs+files. **Human.** |
| 19 | Usage-limit, incomplete dirty work | `INTERRUPTED_SCOPED_WIP` / `INTERRUPTED_UNKNOWN_WIP` | none | commit-to-clean/pull/reset | Leave dirty; record next action. No commit. |
| 20 | Usage-limit, fully verified & committable | ready | checkpoint commit + normal ff push (docs/snapshot only; user-gated) | force; auto-push implementation code | `isaac-checkpoint`; implementation code needs explicit per-commit authorization. |
| 21 | Commit fails | unchanged | none | force anything | Report error; fix. No approval. |
| 22 | Push rejected (non-ff) | `DIVERGED` / `REMOTE_ADVANCED_DURING_WIP` | none | force push | Re-fetch; classify. **Human if diverged.** |
| 23 | Checkpoint push succeeded | `CLEAN_AND_SYNCHRONIZED` | post-push fetch + verify 0/0 | — | Record. No approval. |
| 24 | Post-push verification | (of 23) | fetch; confirm HEAD==origin, 0/0, clean | claim sync w/o re-fetch | Record. No approval. |
| 25 | CI queued for HEAD | axis-2 queued | wait/report | claim green | Report "CI queued". No approval. |
| 26 | CI failed for HEAD | axis-2 failed | report | claim green / deploy-verified | **Stop; investigate. Human decides fix.** |
| 27 | CI green at exact HEAD | axis-2 green | proceed | — | Proceed. No approval. |
| 28 | Vercel deployment pending | axis-3 pending | report | claim prod verified | Re-check later. No approval. |
| 29 | Vercel Ready | axis-3 ready | report; verify served bundle/commit | assume mapping unchecked | Verify bundle maps to HEAD. No approval. |
| 30 | Railway deployment pending | axis-4 pending | report | claim healthy | Re-check later. No approval. |
| 31 | Railway healthy | axis-4 healthy | report; verify `/health` commit | assume mapping unchecked | Verify commit mapping. No approval. |
| 32 | Personal→SLAC switch at clean boundary | `CLEAN_AND_SYNCHRONIZED` precondition | checkpoint → switch → profile → resume | switch mid-dirty | Checkpoint first. No approval. |
| 33 | SLAC→personal switch at clean boundary | `CLEAN_AND_SYNCHRONIZED` precondition | checkpoint → switch → profile → resume | switch mid-dirty | Checkpoint first. No approval. |
| 34 | Second session opens while tree dirty | single-editor warning | `isaac-profile` warns (advisory) | second session edits/commits/pushes | Second session must not edit. No approval. |
| 35 | GitHub identity != `Krish-Verma` | `SERVICE_IDENTITY_MISMATCH` | report by name | login/switch/relink | **Stop. Human.** |
| 36 | Railway identity != expected | `SERVICE_IDENTITY_MISMATCH` | report by name | login/switch/relink | **Stop. Human.** |
| 37 | Vercel identity != expected | `SERVICE_IDENTITY_MISMATCH` | report by name | login/switch/relink | **Stop. Human.** |
| 38 | Interrupted; resumed with no chat history | `INTERRUPTED_*` (reconstruct) | read-only reconstruct from git + checkpoint | trust chat memory | `isaac-resume`. No approval. |
| 39 | Clean, behind, not diverged, fetch ok | the ONE allowed auto-reconcile | `git pull --ff-only` | any other pull/merge/reset | Verify 0/0. No approval. |
| 40 | Dirty tree, any behind/ahead | `ACTIVE_/INTERRUPTED_*_WIP` | none (gate on clean tree FIRST) | any `git pull` | Resume slice. No approval. |

Anything not classifiable above is `REQUIRES_HUMAN_REVIEW`: stop automatic synchronization and
report the exact unresolved facts.

### Profile-switch workflow

Before switching: run `isaac-checkpoint` and reach `CLEAN_AND_SYNCHRONIZED` (branch `main`,
clean, 0/0, exact-HEAD CI known, deployment recorded, next slice recorded). Then
`cd ~/Documents/ISAAC && claude-personal` (personal) or `claude-slac` (SLAC), and in the new
session run `isaac-profile` then `isaac-resume`. `claude-slac` stays the single normal ISAAC
entry point and encapsulates supported Chrome activation. No routine plugin/context-mode
toggling, config renaming/copying, Chrome flags, shell edits, or account-file manipulation.
`/handoff` may add narrative context but never replaces Git status, working-tree inspection,
committed plans/specs, checkpoints, history, or these three skills; a switch normally relies on
checkpoint → shared repo → profile → resume.

---

## No-secret reporting

Never print or compare raw tokens, API keys, or secret values. Report presence/scope by
name only (e.g. "`ISAAC_UI_API_KEY` is set on Railway" — not its value).

`VITE_`-prefixed vars are compiled into the client bundle (browser-visible). **`VITE_API_KEY`
was removed from the application on 2026-08-08** and nothing reads it any more; if you find it
set on a service, it is inert and should be deleted rather than rotated. The general rule stands
for any other `VITE_*` value: browser-visible is not secret, and a credential that has to be
compiled into a page is the wrong shape of credential — do not paste its value regardless.

---

## context-mode status

context-mode is disabled for ISAAC at project scope via `.claude/settings.json`
(`enabledPlugins."context-mode@context-mode": false`), effective at the next ISAAC
session. A residual user-scope `context-mode-cache-heal.mjs` `SessionStart` hook cannot be
disabled from project scope and is left in place (benign cache maintenance); removing it
needs a global `~/.claude` edit that affects other projects and is approval-gated.

---

## Login gates (STOP and ask — never run uninvited)

Each of the following is interactive and approval-gated. Do not run any of them without
explicit user approval:

- `vercel link`
- `vercel logout` / `vercel login`
- `railway logout` / `railway login`, then `railway status`
- `gh repo transfer`

If a login is genuinely required, stop and ask the user to select the **existing personal
developer account** — never a new SLAC-owned project.

---

## Ownership-transfer gates

Any migration requires the full handoff gate from `docs/infrastructure-ownership.md`:
named SLAC owner, destination org, destination team, billing owner, secrets owner,
deployment owner, rollback plan, verified transfer procedure. Do not migrate without all
of them.

---

## Recovery procedure (after a reset or interruption)

1. Read `CLAUDE.md` + `AGENTS.md`.
2. Run `/isaac-resume` (or the manual procedure below if the skill can't load).
3. Reconcile claimed progress against actual git state.
4. Run the read-only reconnection checks above.
5. Do **not** log in, migrate, relink, or change secrets/env vars.
6. State the next authorized action and stop at gates.

---

## Manual checkpoint / resume procedure (fallback if repo-local skills can't load)

### Manual checkpoint

- `git status -sb`
- `git log --oneline -8`
- `git rev-parse HEAD` vs `git ls-remote origin main`
- Classify changed files: truth-path / docs / frontend / served snapshot / config.
- If a manifest file changed (`CLAUDE.md`, `AGENTS.md`, `docs/*.md`,
  `.claude/skills/*/SKILL.md`), run the snapshot preflight:
  ```bash
  .venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
    --out apps/api/isaac_api/data/memory-snapshot.json --check
  ```
  Regenerate if drift, then re-run:
  ```bash
  .venv/bin/pytest apps/api/tests/test_committed_snapshot.py -q
  ```
- Refuse destructive git and deployment operations.
- Commit/push only explicitly-safe scoped docs.
- Report: REPO / COMMITTED / VERIFIED / NOT VERIFIED / BLOCKED / NEXT HUMAN ACTION.

### Manual resume

Do the same read-only inspection, plus read:

- The decision lock: `docs/superpowers/plans/2026-07-20-remaining-work-decision-lock.md`
- The roadmap: `docs/superpowers/plans/2026-07-19-remaining-product-roadmap.md`
- The active phase plan/spec.
- The latest checkpoint.

Identify the authorized slice, the gated items, and the next safe action. Implement
nothing.
