# P26.0 — Workspace & Memory Search Design — pointer

Status: **DECISIONS APPLIED (2026-07-20 decision-lock), RELEASED (P26.1–P26.6 shipped 2026-07-21).**

This is a short pointer, not a duplicate spec. The authoritative Phase 26 mini-spec **is**
the phase plan itself:

[`docs/superpowers/plans/2026-07-19-phase-26-workspace-memory-search-plan.md`](../plans/2026-07-19-phase-26-workspace-memory-search-plan.md)

That document's §12 (API/contracts), §13 (UI behavior), and §20 (bite-sized slices, with a
RELEASED note per shipped slice P26.0a–P26.6) are the design of record. This pointer exists only
so `docs/superpowers/specs/` has an entry for Phase 26, matching the convention set by prior
phases (P20, P24, P24.9, P24.10, P25).

For a reader-facing summary of what actually shipped, see
[`docs/search-architecture.md`](../../search-architecture.md).

## Decisions (D1–D6), resolved 2026-07-20 decision-lock, plan §25

- **D1** — Single grouped `GET /api/search` route with two internally-separate providers
  (workspace + memory), not two routes.
- **D2** — Affordance is **⌘K / Ctrl-K** plus a visible TopBar "Search ⌘K" trigger button
  (not keyboard-only); `/` stays unbound.
- **D3** — The retirement of the P22-era "no fake search" tests is a **dedicated, reviewed
  slice** (P26.6), shipped strictly green-per-commit atomically with the feature slice (P26.5)
  in commit `1365b7f` — no transient-red push.
- **D4** — Vector / semantic embedding search stays **back-burner**; not built in Phase 26.
- **D5** — Scoped to the single shared workspace + single memory provider; the UI must not
  imply per-user or per-owner results.
- **D6** — No new environment variables, no new dependencies (backend or frontend).
