# ISAAC — Post-Phase-26 Master Execution Ledger (Phases 27–32)

> **This is the single canonical end-to-end execution ledger for the remaining ISAAC program.**
> It is the source `/isaac-resume` and `/isaac-checkpoint` should use to recover program state across
> sessions. Where a companion plan conflicts on *post-Phase-26 execution*, this ledger governs; the
> dated historical plans (Phase 20–26, the 2026-07-19/20 lock) remain authoritative for their own
> eras and are **not** rewritten. Created 2026-07-21 · baseline HEAD `859d36c` · orchestrator: Opus 4.8
> (Fable 5 unavailable this account, ratified fallback).

---

## STATUS BLOCK (update every slice)

| Field | Value |
|---|---|
| **Current phase** | Phase 27 — Runtime Safety Foundation |
| **Active ticket** | P27.2 — Atomic writes + record version model (next to implement) |
| **Completed** | T0 docs-truth (`859d36c`); P27.0 storage ground-truth; ledger+approval (`33825ff`); P27.1 runtime mode |
| **Next step** | Add authorized `ISAAC_RUNTIME_MODE=synthetic-only` Railway var + verify health; then P27.2 |
| **Blockers** | none |
| **Latest impl commit** | P27.1 (this commit) |
| **Latest checkpoint commit** | `859d36c` |
| **Verification status** | baseline verified; CI green on `859d36c`; Railway+Vercel healthy |
| **Open decisions** | ledger→resume skill wiring (skill edit needs approval); `If-Match` strictness handled by P27.4 two-step |
| **Approved constraints** | synthetic-only; no LLM; no real data; no new cloud service; no account/billing change (except `ISAAC_RUNTIME_MODE` add) |
| **Next recommended action** | governance commit (this ledger + lock/roadmap/storage-doc reconcile), then P27.1 |
| **Git sync** | `main` · local == `origin/main` == `859d36c` · 0/0 · clean |
| **Exact-HEAD CI** | green on `859d36c` |
| **Railway** | Online · commit `859d36c` · `mode: synthetic-only` · volume `/data/isaac-workspace` 34/500 MB |
| **Vercel** | 200 · `isaac-demo.vercel.app` |
| **Browser-QA** | P26 SearchDialog green (prior); Phase 27+ pending |

---

## 1. Overall objective

Finish the ISAAC product from the post-Phase-26 foundation through a final clean, synchronized,
CI-green, deployed, browser-verified release, delivering: one authoritative synthetic-only runtime
mode; durable+atomic persistence; per-record versions + stale-write protection; live cross-tab/
assistant sync; one fixed workflow order; dependency-aware invalidation; deterministic evidence
classifications; a conversation-style assistant that always reads live state; a bounded deterministic
workflow agent; ephemeral session context; subordinate live runtime record retrieval; sandboxed
synthetic/public file ingestion; and full UI/a11y refinement + stabilization + docs + audit.

Hard invariants: **no external LLM · no real/private SLAC data · no guessed/silently-substituted
scientific values · deterministic Python truth plane stays authoritative.**

## 2. Approved phases & slices

Roadmap approved 2026-07-21 (extends the locked terminal arc; promotes runtime-record retrieval and
sandboxed synthetic/public ingestion into synthetic-only scope — see §Decision Lock Addendum).

| Phase | Name | Slices |
|---|---|---|
| **27** | Runtime Safety Foundation | P27.0 storage ground-truth ✅ · P27.1 runtime mode · P27.2 atomic writes + rev model · P27.3 backend version contract · P27.4 safe compat rollout (compat→strict) · P27.5 FE version propagation · P27.6 live client sync · P27.7 hosted concurrency QA |
| **28** | Workflow & Evidence Contracts | P28.0 audit · P28.1 fixed order · P28.2 dependency invalidation · P28.3 revisit/view/edit · P28.4 evidence classification · P28.5 evidence API+UI · P28.6 hosted QA |
| **29** | Assistant Experience | P29.0 live context builder · P29.1 ephemeral session context · P29.2 conversation UI · P29.3 deterministic workflow agent · P29.4 one shared state · P29.5 hosted agent QA |
| **30** | Live Runtime Record Retrieval | P30.0 proof+contract · P30.1 projection · P30.2 update/invalidation · P30.3 search+agent integration · P30.4 degradation+QA |
| **31** | Synthetic/Public File Ingestion | P31.0 format selection · P31.1 upload boundary · P31.2 deterministic parser · P31.3 assistant/manual review · P31.4 QA |
| **32** | UI Refinement, Stabilization, Docs, Release | P32.0 UI inventory · P32.1 UI+a11y refinement · P32.2 CQ/minor closure · P32.3 whole-codebase audit · P32.4 docs · P32.5 memory refresh · P32.6 final release gate |

## 3. Dependency graph

```
T0(done) → P27.0(done) → P27.1 → P27.2 → P27.3 → P27.4(compat→strict) → P27.5 → P27.6 → P27.7
                                    │(rev token is prerequisite for live-context "verified current")
Phase 28: P28.0 → P28.1 → P28.2 → P28.3 ; P28.4 → P28.5 (evidence track parallel) → P28.6
Phase 29: P29.0(needs 27 rev + 28 classifications) → P29.2 ; P29.1 ; P29.3(needs 28 workflow) → P29.4 → P29.5
Phase 30: P30.0 proof-gate → (index only if justified) P30.1 → P30.2 → P30.3 → P30.4
Phase 31: P31.0 → P31.1 → P31.2 → P31.3 → P31.4   (needs 27 runtime-mode gate, 28 evidence, 29 context)
Phase 32: P32.0 → P32.1 ; P32.2 ; P32.3 → P32.4 → P32.5 → P32.6
```

## 4. Decision Lock Addendum (approved 2026-07-21 — ADDITIVE)

Extends `2026-07-20-remaining-work-decision-lock.md`. Historical decisions there are preserved; this
addendum records the new approvals without rewriting the past.

- **Roadmap extended** beyond the terminal "UI Refinement → Stabilization → Docs" arc with Phases 27–32.
- **Promoted into synthetic-only scope** (previously §11 back-burner): live runtime record retrieval;
  sandboxed synthetic/public deterministic file ingestion.
- **Still deferred (NOT promoted):** real-data ingestion · institutional users/SSO/orgs · per-user
  authorization · experiment permissions · real/private SLAC data · production institutional storage ·
  vector search · embeddings · semantic search · external LLM orchestration · unrestricted uploads ·
  second scientific domain · related-record similarity · dark mode · institutional infrastructure.
- **Storage correction (P27.0):** the hosted workspace **is persistent** — Railway volume
  `isaac-metadata-assistant-volume` mounted at `/data/isaac-workspace`, used via
  `ISAAC_UI_WORKSPACE=/data/isaac-workspace`. The 2026-07-19/20 "ephemeral /tmp · no volume"
  characterization was **inaccurate at the time** (Phase 20 had already provisioned the volume) and is
  corrected forward here. `docs/deployment.md` was correct.
- **Runtime-mode signal:** approved mechanism `ISAAC_RUNTIME_MODE=synthetic-only` (fail-closed
  default). Adding/updating exactly this one Railway production var is authorized after code+tests+preflight.

## 5. Current phase / active slice / completed slices

- **Current phase:** 27. **Active slice:** P27.1 (next). **Completed:** T0, P27.0.

## 6. Verification evidence (as of `859d36c`)

- Backend suite green in CI (`tests and synthetic demo` job); frontend green (`frontend tests and build`).
- Truth validation + advisory-warning validation + evidence audit run in CI on synthetic demo record.
- Snapshot `--check` clean; committed-snapshot gate 17 passed; R4.3 docs preflight passed.
- Railway `/api/health` = `{status:ok, mode:synthetic-only, commit:859d36c}`; volume 34/500 MB. Vercel 200.

## 7. Not-yet-verified

Everything in Phases 27–32 below P27.0. No Phase 27 code exists yet.

## 8. Current blockers

None. (P27.0 volume confirmed → no infra hard gate.)

## 9. Human gates (this program) — stop ONLY for these

1. Railway persistent storage missing AND fixing it changes billing/infra → **N/A, volume confirmed.**
2. Account/ownership/billing/service migration required.
3. A secret/credential must be created, rotated, or exposed.
4. Real/private SLAC data or institutional approval required.
5. A supported scientific file format cannot be chosen from repo evidence (P31.0).
6. Two committed specs irreconcilably conflict.
7. A Critical/Important defect cannot be safely resolved within the approved architecture.
8. A destructive action exceeds the approved synthetic-only reset/cleanup contract.
9. A new external cloud service or LLM provider would be required.
10. Project fully complete → final human acceptance.

## 10. Deferred beyond this program

See §4 "Still deferred." Document as future institutional work in P32.4.

## 11. Next safe action

Governance commit (this ledger + lock/roadmap/storage-doc additive reconcile), then P27.1.

## 12. Final completion checklist

Mirrors the mandate's Final Completion Standard — tracked at P32.6. Key axes: storage doc accurate ·
one runtime-mode source · atomic persistence · every mutable record has a rev · stale writes rejected ·
missing precondition rejected post-rollout · safe two-tab · live resync · fixed workflow order ·
revisitable completed steps · dependency-aware invalidation · deterministic evidence classes distinct ·
no silent inferred writes · natural conversation UI · assistant verifies live state · ephemeral session
context · one shared state · confirm-gated mutations · retrieval subordinate to Workspace · memory
separate · memory failure non-blocking · safe synthetic ingestion · candidates stay candidates · no real
data · all user-visible behavior browser-tested · all Critical/Important resolved · docs match reality ·
tests/validation/audit/demo/snapshot/preflight/CI/deploy pass · git clean+synced · release checkpointed.

---

## Per-slice log (append-only)

- **T0** (`859d36c`, 2026-07-21): corrected stale "no search" claims in `docs/ui-local-dev.md`; snapshot
  regenerated. CI green, Railway+Vercel healthy. `technical-architecture.md` left untouched (no search claim).
- **P27.0** (2026-07-21, read-only inspection): Railway volume `isaac-metadata-assistant-volume` @
  `/data/isaac-workspace` (34/500 MB) confirmed; `ISAAC_UI_WORKSPACE=/data/isaac-workspace`;
  `ISAAC_RUNTIME_MODE` absent. Classification: **Persistent Volume Confirmed.** No infra change. Storage
  docs reconciled additively in the governance commit.
- **P27.1** (2026-07-21): authoritative synthetic-only runtime mode. NEW `runtime_mode.py` (single
  fail-closed source), `is_synthetic_only()` delegates, `/api/health` mode + reset/upload guards read
  it, `create_app()` validates at boot (invalid/`real` → refuse to boot). Opus impl (red-first, 18
  tests) + independent Opus adversarial review = **SHIP**; folded in the upload `synthetic_only` test.
  Full backend **664 passed**; snapshot regen (edited manifest files: app.py/routes.py/workspace.py/
  test_api.py) + gate 17 green; R4.3 backend preflight passed. Follow-ups: (a) authorized Railway
  `ISAAC_RUNTIME_MODE=synthetic-only` var add + health verify; (b) `runtime_mode.py` not yet
  graph-indexed → P32.5 memory refresh. Truth-core untouched.
