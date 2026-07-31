# Personal Deployment Retirement — Checklist (APPROVAL GATE, nothing executed)

**Created:** 2026-07-31 · **Status:** checklist only. **No disable, delete, unlink, logout, account
switch, or ownership transfer has been performed, and none may be performed without Krish's explicit
per-action approval.** Every fact below came from a read-only probe.

## Why this exists

ISAAC's canonical deployment is now SLAC-owned: `ISAAC-DOE/isaac-metadata-assistant` → GHCR → Flux →
`https://isaac.slac.stanford.edu/krish`, behind Authentik. The two personal deployments that preceded
it are still running and still serving traffic. They are developer-owned infrastructure pending an
explicit ownership decision (CLAUDE.md §17).

## Observed state (read-only, 2026-07-31)

| Item | Vercel | Railway |
|---|---|---|
| Account / scope | `kvlx`, team `krish2808` (personal) | Krish's personal Railway account (identified in the dashboard; email deliberately omitted here — see note) |
| Project / service | `isaac-demo-web` | `isaac-metadata-assistant` |
| URL | `https://isaac-demo-web.vercel.app` | `https://isaac-metadata-assistant-production.up.railway.app` |
| Status | live — `HTTP 200` | live, `● Online` — `HTTP 200` in 0.20 s |
| Last updated | 8 days ago | deployment `8d18b32d-…`, service `14618664-…` |
| Auth | **none** — public | **none** — public |
| Data attached | none observed | **volume `isaac-metadata-assistant-volume`** (persistent) |
| Serving commit | not probed (static SPA) | **`b3b76cd`** (2026-07-23) — **77 commits behind `origin/main`** |
| Runtime mode | n/a | `synthetic-only` |

Probe commands: `vercel whoami`, `vercel project ls`, `railway whoami`, `railway status`,
`curl …/api/health`, `git rev-list --count b3b76cd..origin/main` (→ 77; note `..HEAD` gives a
different number on a feature branch, so the ref matters).

**Why the email is omitted.** The accounts are unambiguously identified without it, and this file
will enter the memory plane's served content the next time the graph is regenerated (see the graph
doc §1.3) — at which point Project Memory and search could surface anything written here. Account
identifiers are operationally necessary for a retirement checklist; a personal email address is not.

### Three findings worth Krish's attention before deciding

1. **Both are publicly reachable with no authentication.** The SLAC deployment is Authentik-gated;
   these are not. What they serve is synthetic-only, so this is not a data-exposure incident — but it
   is an unauthenticated public instance carrying the ISAAC name.
2. **Railway is 77 commits stale.** Its `/api/health` returns no `database` block, confirming it
   predates Slice 2A. Anyone who finds it sees a materially older product than `/krish`.
3. **Railway has a persistent volume.** It is not an `emptyDir` like the k8s deployment. Whatever
   synthetic workspace state accumulated there survives restarts, so **deletion destroys data that
   disabling would preserve.** This is the single strongest argument for disable-before-delete.

## Rollback consequence

| Action | Reversible? | Consequence |
|---|---|---|
| Vercel: disable/pause | yes | URL stops serving; project, settings, and history retained |
| Vercel: delete project | **no** | URL, deployment history, and env config gone |
| Railway: remove domain / pause service | yes | URL stops serving; volume and config retained |
| Railway: delete service | **no** | **volume contents destroyed** |
| Railway: delete project | **no** | everything gone |
| Delete `personal` git remote (`Krish-Verma/isaac-metadata-assistant`) | n/a here | out of scope — it is a preserved historical mirror, keep it |

## Recommended order (each step is a separate approval)

1. **Confirm `/krish` is verified working** — gate G1 in the Baseline Completion Matrix. Do not retire
   a fallback before the replacement is runtime-verified. *This is currently open.*
2. **Announce** to anyone holding the old URLs (Krish's call who that is).
3. **Railway first, non-destructively:** remove the public domain **or** pause the service. Keep the
   volume. Observe for a chosen interval.
4. **Vercel:** pause/disable the `isaac-demo-web` project. Keep it.
5. **Observation window** — a week is typical; Krish decides.
6. **Only then**, if desired, consider deletion — as a separate decision, with the volume consequence
   in §Rollback consequence understood.

## What must not happen

- No account switch, logout, re-login, or `vercel link`.
- No ownership or billing transfer.
- No deletion of the `personal` git remote or the mirror repository.
- No step executed by an agent. Every operation above is Krish's, performed in the respective
  dashboard or CLI by Krish.

**Status: awaiting Krish. Recommended: do nothing until gate G1 closes.**
