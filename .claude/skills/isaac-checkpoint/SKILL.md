---
name: isaac-checkpoint
description: Snapshot verified ISAAC session state — branch, working tree, ahead/behind, changed-file classification, verification status — and optionally commit/push only explicitly-safe scoped documentation. Refuses destructive git and deployment. Use when the user runs /isaac-checkpoint or asks to checkpoint or save session state.
---

# /isaac-checkpoint

Read-only by default. It reports verified repo state and the exact next human action. It NEVER runs
destructive git (no `reset --hard`, `rebase`, force-push, branch delete, `clean -fd`), NEVER deploys,
and commits/pushes ONLY explicitly-safe scoped documentation when the user has authorized it.

The authoritative rules — repository states, remote-advanced/diverged handling, the four synchronization
axes, and the decision table — live in `docs/toolchain-reconnection-runbook.md` → "Shared Repository
Synchronization Contract". This skill applies them; it does not restate the decision table.

## Steps

1. Repo state: run a `git fetch --prune origin` **before** committing, then `git status -sb` (branch,
   ahead/behind, dirty/clean); `git log --oneline -8`; `git rev-parse HEAD` compared against
   `git ls-remote origin <branch>` for push sync. Detect whether the remote advanced and whether local
   and remote diverged. **If the remote advanced while local has commits or the tree is dirty, do NOT
   push** — stop and report (`DIVERGED` / `REMOTE_ADVANCED_DURING_WIP`).
2. Classify changed files: **truth-path** (`schema/`, `src/isaac_records/official.py`,
   `draft_validator.py`, `export.py`, `audit.py`, `cli.py` + their tests) · **docs** · **frontend**
   (`apps/web`) · **served snapshot** (`apps/api/isaac_api/data/memory-snapshot.json`) · **config**
   (`.claude/`). Flag any truth-path change loudly.
3. Snapshot drift preflight IF any manifest/served file changed (`CLAUDE.md`, `AGENTS.md`, `docs/*.md`,
   `.claude/skills/*/SKILL.md`, or any snapshot-manifest path):
   ```bash
   .venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
     --out apps/api/isaac_api/data/memory-snapshot.json --check
   ```
   If it reports drift, regenerate (drop `--check`) and re-run the gate
   `.venv/bin/pytest apps/api/tests/test_committed_snapshot.py -q`.
4. Update the active phase/status section when appropriate — the "Session checkpoint" block of the active
   phase plan under `docs/superpowers/plans/` (or the reconciliation plan while R1–R6 are active). Only
   status wording that reflects verified facts; never invent progress.
5. Commit/push ONLY if the user authorized it AND the change is scoped, safe documentation (or a
   deterministically-regenerated snapshot). Otherwise leave the tree untouched and report. Never deploy,
   relink, log in, change secrets, or change env vars (all approval-gated). **After a push, re-fetch and
   verify** HEAD == `origin/main`, 0 ahead, 0 behind, clean tree — a checkpoint must NEVER claim
   synchronization without a post-push re-fetch + verification.
   **Interruption-safe:** never create a commit merely to make the tree clean. Leave incomplete or
   insufficiently-verified work dirty and classify it (`INTERRUPTED_SCOPED_WIP` /
   `INTERRUPTED_UNKNOWN_WIP`); preserve it for the next session.
6. Emit the report with EXACTLY these labels. Report the four synchronization axes **separately** —
   never a global "synchronized" when only Git is:
   - **REPO:** branch · local HEAD · origin HEAD · clean/dirty · ahead · behind · divergence
   - **SYNC AXES:** Local↔GitHub · GitHub↔CI · GitHub↔Vercel · GitHub↔Railway
   - **COMMITTED:** commit hashes made this checkpoint, or `none`
   - **VERIFIED:** checks that passed, with the commands run
   - **NOT VERIFIED:** what was not checked and why
   - **BLOCKED:** anything blocked and its gate
   - **NEXT HUMAN ACTION:** the single next safe step, or `none`

## Refuses

- destructive git (`reset --hard`, `rebase`, force-push, branch delete, `clean -fd`)
- deployment / relink / login / secret change / env-var change (approval-gated)
- committing truth-path, generated, or private artifacts without explicit approval
