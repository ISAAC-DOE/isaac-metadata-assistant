---
name: isaac-resume
description: Reconstruct verified ISAAC state after a reset or interruption — repo + remote state, decision lock, roadmap, active phase plan/spec, latest checkpoint — and state the next authorized action without implementing anything. Use when the user runs /isaac-resume or asks to resume or pick up where we left off.
---

# /isaac-resume

Read-only. It reconstructs verified state and names the next authorized action. It implements NOTHING
automatically — no edit, commit, push, deploy, or config change.

## Steps

1. Repo + remote state: `git status -sb`; `git log --oneline -8`; `git rev-parse HEAD`;
   `git ls-remote origin <branch>` — detect uncommitted or unpushed work.
2. Read the authoritative planning docs (if a newer same-purpose file exists, the newest wins):
   - decision lock: `docs/superpowers/plans/2026-07-20-remaining-work-decision-lock.md`
   - roadmap: `docs/superpowers/plans/2026-07-19-remaining-product-roadmap.md`
   - active phase plan: `docs/superpowers/plans/2026-07-19-phase-25-grounded-assistant-plan.md`
     (+ spec `docs/superpowers/specs/2026-07-20-phase-25-grounded-assistant-design.md`)
   - active reconciliation plan (while in progress):
     `docs/superpowers/plans/2026-07-20-slac-account-toolchain-reconciliation.md`
   - latest checkpoint: the "Session checkpoint" block of the active phase plan.
3. Reconcile claimed progress with actual git state — never trust prose over git.
4. Identify: the currently AUTHORIZED slice; what is explicitly NOT authorized (the gates); any
   uncommitted/unpushed work; and the single next safe action.
5. Report (read-only), with these labels:
   - **VERIFIED STATE:** branch · HEAD · clean/dirty · ahead/behind
   - **AUTHORIZED NOW:** the slice that may proceed
   - **NOT AUTHORIZED:** gated items (e.g. next phase, logins, migrations)
   - **UNCOMMITTED / UNPUSHED:** any such work, or `none`
   - **NEXT SAFE ACTION:** the single next step
   Do not edit, commit, push, deploy, or implement.

## Notes

- If a future account cannot load this skill, the manual procedure is `CLAUDE.md` §16 (Resume Protocol),
  §17 (snapshot preflight), and `docs/toolchain-reconnection-runbook.md`.
