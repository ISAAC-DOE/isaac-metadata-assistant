# Infrastructure Ownership & Account Policy

This document records the accepted infrastructure-ownership decision from the 2026-07-20 SLAC account/toolchain reconciliation. **Status: SUPERSEDED (2026-07-21) — see "SLAC handoff executed" below.**

---

## SLAC handoff executed (2026-07-21)

The handoff this document gated on was explicitly authorized and executed by
the SLAC project owner (kskoien@slac.stanford.edu):

- **Code** — canonical repo is now `ISAAC-DOE/isaac-metadata-assistant`
  (private, full history pushed). The personal repo
  `Krish-Verma/isaac-metadata-assistant` should be archived by its owner with
  a pointer to the org repo.
- **Hosting** — SLAC Kubernetes (ISAAC vCluster) at
  `https://isaac.slac.stanford.edu/krish/`, deployed via GitHub Actions ->
  ghcr.io -> Flux GitOps (see `docs/deployment.md`). Vercel and Railway are
  retired; their projects run on the personal account and must be deleted by
  that account holder (teardown checklist in `docs/deployment.md`).
- **Ownership** — infrastructure, secrets, and deployment are owned by the
  ISAAC/SLAC team through the `isaac-k8` GitOps repo and cluster; no personal
  cloud accounts remain in the serving path once teardown completes.

The sections below are retained as the historical record of the pre-handoff
state and the policy that governed it.

Cross-links:
- Reconciliation plan (decision record): `docs/superpowers/plans/2026-07-20-slac-account-toolchain-reconciliation.md`
- Operational recovery runbook (created alongside this document): `docs/toolchain-reconnection-runbook.md`

---

## Current ownership (unchanged for now)

ISAAC's GitHub repository, Railway backend service, and Vercel frontend project each run on a **personal, developer-owned account**. Claude Code runs under the **SLAC organization account**.

The Claude account switch to the SLAC org does **not** migrate the other services — GitHub, Railway, and Vercel remain on the personal developer account.

Characterization of the current state:

> **Temporary developer-owned infrastructure pending an explicit SLAC ownership and handoff decision.**

This personal ownership is **not** the intended final institutional architecture.

---

## Why unchanged

- No SLAC infrastructure team has been identified.
- No destination organization has been supplied.
- No project owner has been designated.
- No billing owner has been designated.
- No secrets owner has been designated.
- No deployment owner has been designated.
- No migration requirements have been supplied.
- An uncoordinated migration could break deployment or access.
- The current infrastructure is functioning as-is.

---

## Default-account policy

Preserve the currently connected, developer-owned service identities unless the user explicitly authorizes a different account.

Do **not** (without explicit per-action approval):

- Log out a working account.
- Switch identity on any connected service.
- Link or relink a cloud project.
- Create a new or duplicate cloud project.
- Move to a different team/org.
- Transfer ownership or billing.
- Rotate credentials.
- Change git remotes.

Claude Code using the SLAC org account is **not** a reason to migrate the other services (GitHub, Railway, Vercel).

---

## Future handoff gate (must ALL be satisfied before any migration)

- [ ] Named SLAC owner
- [ ] Destination GitHub organization
- [ ] Destination Railway/Vercel team (or approved replacement)
- [ ] Billing owner
- [ ] Secrets owner
- [ ] Deployment owner
- [ ] Rollback plan
- [ ] Verified transfer procedure

---

## Human login gates (exact commands; all optional, none run automatically)

Each of the following is interactive and gated on a human ownership decision. None of these commands run automatically as part of routine work.

| Command | Purpose | Gate |
|---|---|---|
| `vercel link` | Only to CLI-deploy this repo; offers the existing personal scope | Stop for approval first |
| `vercel logout` then `vercel login` | Optional account switch | Human decision required |
| `railway logout` then `railway login`, then `railway status` | Optional account switch (only if moving off the personal account) | Human decision required |
| `gh repo transfer` | Optional GitHub org migration | Human decision required |

---

## No-migration confirmation (2026-07-20 reconciliation)

As of the reconciliation, verified by read-only checks:

- The git remote is unchanged.
- No cloud project was relinked.
- No duplicate project was created.
- No account was logged out or switched.
- All service identities remain the existing personal developer accounts.
- The only new project-scoped config change was disabling the context-mode plugin for ISAAC.
