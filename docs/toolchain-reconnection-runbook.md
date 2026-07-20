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

## No-secret reporting

Never print or compare raw tokens, API keys, or secret values. Report presence/scope by
name only (e.g. "`ISAAC_UI_API_KEY` is set on Railway" — not its value).

`VITE_`-prefixed vars are compiled into the client bundle (browser-visible), so
`VITE_API_KEY` is a shared demo credential, not a private secret — but still do not paste
its value.

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
