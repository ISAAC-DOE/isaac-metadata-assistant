---
name: isaac-profile
description: Report the active Claude toolset/account posture for ISAAC — launcher marker, effective config root, account context, model, orchestrator, context-mode state, tools/MCP/services, and refreshed durable project context — then name the one safe next action. Read-only and advisory; mutates nothing. Use when the user runs /isaac-profile or asks which profile/account/toolset is active.
---

# /isaac-profile

Read-only and advisory. It reports the current Claude toolset/account posture and refreshes durable
project context. It mutates NOTHING — no login/logout, no account switch, no settings edit, no plugin
install, no relink, no deploy, no commit/push, no record mutation, no private-data indexing.

CRITICAL HONESTY RULE: the launcher marker (`$ISAAC_CLAUDE_PROFILE`) and effective config root prove the
claimed TOOLSET only — they do NOT prove the Claude ACCOUNT. Auth lives in a shared macOS Keychain item.
NEVER equate the marker with the account. Establish account context from non-secret signals or report it
`UNKNOWN`.

## Default behavior

Every invocation does BOTH `check` (detect posture) and `refresh` (re-read durable context). A
natural-language request for detail (e.g. "explain why", "walk me through it") triggers an expanded
explanation of each detected signal. This is intent, not a flag parser — do not build a brittle argument
parser.

## Steps

1. **Detect the launcher/toolset (proves toolset, not account).** The pinned launcher contract:
   - `claude-personal` sets `ISAAC_CLAUDE_PROFILE=personal` and does NOT set `CLAUDE_CONFIG_DIR` ⇒
     default root `~/.claude`, which HAS context-mode.
   - `claude-slac` sets `ISAAC_CLAUDE_PROFILE=slac` and `CLAUDE_CONFIG_DIR=$HOME/.claude-slac` ⇒ minimal
     root, NO context-mode.
   - Effective config root = `$CLAUDE_CONFIG_DIR` if set, else default `~/.claude`.

2. **Detect each posture signal read-only; report the value where SAFELY detectable, else `UNKNOWN` —
   never guess.** Signals: launcher marker (`$ISAAC_CLAUDE_PROFILE`); effective config root; Claude
   account/organization context (from NON-SECRET signals only — e.g. `CLAUDE_CODE_ACCOUNT_TAGGED_ID`/UUID
   env if present, or the running session's own reported org; NEVER read the Keychain credential); active
   model; orchestrator selection (Fable 5 if available in the account, else Opus 4.8 ratified fallback —
   `CLAUDE.md` §10/§17); context-mode installed state; context-mode enabled state (project
   `.claude/settings.json` `enabledPlugins`); context-mode `SessionStart` injection state;
   `$NODE_OPTIONS` effect; relevant plugin inventory; relevant MCP inventory; browser connection;
   external CLI identities (GitHub `gh auth status`, Railway `railway whoami`, Vercel `vercel whoami` —
   report identity/scope BY NAME, never print secrets); repository state; the current authorization gate.

3. **Refresh durable context — read the ACTUAL committed docs, not chat memory.** Read in this order
   (where a same-purpose newer doc exists, the newest wins). This is the SAME doc set `/isaac-resume`
   uses, so the two skills cannot drift:
   1. `AGENTS.md`
   2. `CLAUDE.md`
   3. decision lock: `docs/superpowers/plans/2026-07-20-remaining-work-decision-lock.md`
   4. master roadmap: `docs/superpowers/plans/2026-07-19-remaining-product-roadmap.md`
   5. active phase plan: `docs/superpowers/plans/2026-07-19-phase-25-grounded-assistant-plan.md`
   6. active phase spec: `docs/superpowers/specs/2026-07-20-phase-25-grounded-assistant-design.md`
   7. latest committed checkpoint — the "Session checkpoint" block of the active phase plan, and the
      active reconciliation plan `docs/superpowers/plans/2026-07-20-slac-account-toolchain-reconciliation.md`
   8. `git status -sb` + `git rev-parse HEAD`
   9. local/remote sync: `git ls-remote origin main`
   10. recent commits: `git log --oneline -8`
   11. CI state when accessible
   12. deployment/toolchain status
   Precedence when sources conflict: (1) authoritative decision lock (2) latest approved specification
   (3) latest committed checkpoint (4) active phase plan (5) master roadmap (6) historical docs.
   State explicitly in the report: do NOT rely on conversation memory; do NOT treat a proposed plan as
   authorization. For DEEP authorized-state reconstruction, defer to `/isaac-resume` — do not duplicate
   its logic here.

4. **Resolve consistency, using these verbatim tokens.**
   - If the launcher marker, config root, and detectable account disagree ⇒ report
     `PROFILE CONFIGURATION MISMATCH` and DO NOT auto-fix.
   - If account context cannot be safely established ⇒ report
     `UNKNOWN — Claude account context could not be established safely.` and DO NOT guess.
   - Consistent example: marker `slac` + root `~/.claude-slac` + SLAC org account + context-mode absent.
   - Mismatch example: marker `personal` + default root + SLAC org account.

5. **Emit EXACTLY this template** (fill each field; use `UNKNOWN` where a value is not safely
   detectable):

```
# ISAAC PROFILE

## ACTIVE PROFILE
- Launcher marker:
- Config root:
- Claude account context:
- Model:
- Orchestrator:
- Confidence:

## CONTEXT-MODE
- Expected:
- Installed:
- Enabled:
- SessionStart injection:
- Node environment effect:
- Result:

## REPOSITORY
- Repo:
- Branch:
- HEAD:
- Working tree:
- Remote synchronization:
- CI:

## SERVICES
- GitHub:
- Railway:
- Vercel:
- Graphify:
- Browser:

## TOOLS
- Repo-local skills:
- User/global plugins:
- Organization-provided tools:
- MCP:
- Missing tools:

## CONTEXT REFRESHED
- Project purpose:
- Completed:
- Active phase:
- Authorized now:
- Not authorized:
- Architectural invariants:
- Governance restrictions:
- Deployment state:
- Latest checkpoint:
- Context sources:

## POLICY MATCH
- Overall:

## MISMATCHES
- None or exact mismatches

## APPROVALS REQUIRED
- None or exact human actions

## SAFE NEXT ACTION
- One explicit action
```

## Refuses (this skill is read-only; it MUST NOT)

- log in; log out; switch accounts
- copy or read credentials/Keychain, or print any secret/token
- edit settings; install/enable/disable plugins
- change cloud config; relink; deploy
- commit; push
- authorize a phase
- mutate records; index private data

Report presence/scope BY NAME only (`CLAUDE.md` §17 and the runbook's no-secret reporting rule). Login,
relink, and ownership actions are approval-gated — name them under APPROVALS REQUIRED; never run them.

## Notes

- Account/continuity policy, the snapshot preflight, and orchestrator selection live in `CLAUDE.md` §17;
  the reconnection/recovery procedure and read-only service checks live in
  `docs/toolchain-reconnection-runbook.md`. Link to them; do not duplicate them here.
- context-mode is disabled for ISAAC at project scope; a residual user-scope SessionStart cache hook may
  remain (benign) — see the runbook's "context-mode status" section.
- This SKILL.md is a snapshot-manifest file (`CLAUDE.md` §17). Editing it is predictable drift —
  regenerate the committed snapshot in the same commit before pushing.
