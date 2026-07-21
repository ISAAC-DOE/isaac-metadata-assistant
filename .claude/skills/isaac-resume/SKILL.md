---
name: isaac-resume
description: Reconstruct verified ISAAC state after a reset or interruption — repo + remote state, decision lock, roadmap, active phase plan/spec, latest checkpoint — and state the next authorized action, implementing nothing beyond an optional fast-forward-only sync. Use when the user runs /isaac-resume or asks to resume or pick up where we left off.
---

# /isaac-resume

Near read-only. It reconstructs verified state and names the next authorized action. It implements
NOTHING automatically — no edit, commit, deploy, or config change — with exactly ONE exception: it may
perform a single fast-forward-only reconcile (`git pull --ff-only origin main`) under the strict
preconditions below. It does **not** push; does **not** merge, rebase, reset, stash, cherry-pick, or
force; and does **not** pull into a dirty tree.

The authoritative rules — repository states, the single ff-only auto-reconcile, dirty/ahead/diverged/
remote-advanced handling, the four synchronization axes, and the decision table — live in
`docs/toolchain-reconnection-runbook.md` → "Shared Repository Synchronization Contract". This skill
applies them; it does not restate the decision table.

## Steps

1. Repo + remote state: run a safe `git fetch --prune origin`, then `git status -sb`;
   `git log --oneline -8`; `git rev-parse HEAD`; `git ls-remote origin <branch>`. Determine local HEAD,
   `origin/main` HEAD, ahead/behind via `git rev-list --left-right --count HEAD...origin/main`,
   divergence, and a working-tree + untracked-file classification — detect uncommitted or unpushed work.

### Safe fast-forward rule (the ONE allowed reconcile)

`isaac-resume` may run `git pull --ff-only origin main` **only** when ALL of these hold: the expected
ISAAC repo; the expected `origin`; branch `main`; **working tree clean**; no untracked files needing
review; 0 ahead; ≥1 behind; not diverged; the fetch succeeded. It MUST verify the clean tree ITSELF
before invoking the pull — git does **not** reliably refuse a fast-forward into a dirty tree; a
non-conflicting dirty change lets the ff succeed and move HEAD. After a successful ff, verify the tree
is still clean, HEAD == `origin/main`, 0 ahead / 0 behind, and report old→new HEAD.

### State handling (no push; never pull into a dirty tree)

- **Clean but ahead** (local commits not on `origin/main`, not behind): report the ahead count, the
  local-only commits, and the verification state; do **not** push; route to `isaac-checkpoint`.
- **Dirty:** classify every changed/untracked file; identify and resume the active slice; do **not**
  pull. **Interrupted:** reconstruct from git + the latest committed checkpoint
  (`INTERRUPTED_SCOPED_WIP` when every file classifies cleanly to the active slice, else
  `INTERRUPTED_UNKNOWN_WIP`) without trusting chat history.
- **Diverged / remote-advanced-during-WIP:** stop and report; require a human decision. Never
  auto-resolve, merge, rebase, reset, or force.
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
