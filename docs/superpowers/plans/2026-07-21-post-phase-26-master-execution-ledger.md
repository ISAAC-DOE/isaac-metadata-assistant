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
| **Active ticket** | P27.6 — Live client synchronization (bounded revision-aware polling; SSE ruled out — see entry) (next) |
| **Completed** | T0 (`859d36c`); P27.0; ledger+approval (`33825ff`); P27.1 (`26642eb`); P27.2 (`14477bd`); P27.3 (`ccac6d3`); P27.4 (`41bd20b`); P27.5 (`0112f5f`); P27.5-strict (`d7a9fef`); reset-content fix (`61c017f`, deployed + hosted-QA PASS) |
| **Next step** | P27.6 live sync (bounded revision-aware polling per the SSE-vs-poll analysis); then P27.7 hosted two-tab QA; then Phase 27 checkpoint; then Phases 28–32 |
| **Blockers** | none |
| **Latest impl commit** | `61c017f` (reset-content) |
| **Latest checkpoint commit** | `61c017f` |
| **Verification status** | full backend **740 passed**; frontend **361 passed**; CI green on `61c017f`; Railway serving `61c017f` synthetic-only; Vercel P27.5 bundle; hosted demo restored to canonical 2/1/1/1 |
| **Open decisions** | ledger→resume skill wiring (skill edit needs approval); strict 428 enforcement gated on deployed-FE sending If-Match (P27.4/P27.5) |
| **Approved constraints** | synthetic-only; no LLM; no real data; no new cloud service; no account/billing change (except `ISAAC_RUNTIME_MODE` add) |
| **Next recommended action** | P27.4 — shared typed version contract + compat-rollout boundaries |
| **Git sync** | `main` · local == `origin/main` == `ccac6d3` · 0/0 · clean |
| **Exact-HEAD CI** | green on `ccac6d3` (run 29890264575) |
| **Railway** | Online · commit `ccac6d3` · `mode: synthetic-only` · volume `/data/isaac-workspace`; `expose_headers=[ETag]` live |
| **Vercel** | 200 · `isaac-demo-web.vercel.app` (canonical per `.vercel/project.json`; `isaac-demo.vercel.app` also 200) |
| **Browser-QA** | P26 SearchDialog green (prior); P27.3 hosted no-regression smoke (pre-P27.5 FE unchanged); full two-tab concurrency QA at P27.7 |

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
  - **Railway var (P27.1 completion, 2026-07-21):** `ISAAC_RUNTIME_MODE=synthetic-only` added to
    production; redeployed; **Online**; `/api/health` → `mode: synthetic-only` on `26642eb`. Only this
    one var changed. Deploy verified.
- **P27.2** (2026-07-21): per-record version model + atomic writes. `Experiment` gains `rev:int`
  (monotonic) + `updated_utc`; NEW `atomic_write_text` (mkstemp→fsync→`os.replace`, temp-cleanup on
  failure) wired into every workspace write; `save_versioned()` bumps `rev` (from `max(in-mem, on-disk)+1`)
  + stamps `updated_utc` ONLY when the authoritative signature `{title,source,draft,record_id}` changes —
  identical re-entry is a byte-stable no-op (answer_log excluded, speculative append popped on no-op).
  Seeds/`demo_run` stay `rev 0` + byte-reproducible. Legacy files load rev 0 / updated_utc=created_utc,
  not rewritten on read. Opus impl (red-first, 12 tests) + Opus adversarial review = **SHIP** (no
  Crit/Imp); folded in a rev-monotonicity hardening + regression test (13th). Full backend **677 passed**;
  synthetic demo byte-identical; snapshot regen + gate 17 green. NO HTTP conflict contract yet (P27.3).
  Truth-core/schema/export untouched. Known-accepted (deferred to P27.3): last-write-wins across
  concurrent instances (no If-Match yet).
- **Checkpoint-record correction (2026-07-21):** the post-P27.2 checkpoint narrative said "5 commits this
  session"; the actual count is **four** (`859d36c`, `33825ff`, `26642eb`, `14477bd` — verified by
  `git rev-list --count 7926ab0..14477bd` = 4). The "5" was a typo in prose only; no commit was missing.
  Corrected here rather than in a standalone commit.
- **P27.3** (`ccac6d3`, 2026-07-21): backend version contract — ABA-safe ETag/If-Match/412 on the two
  scientific-record mutations (`/answers`, `/export`). Four parallel read-only discovery audits (HTTP
  surface, reset/reseed **ABA**, frontend/CORS, tests/standards) proved the integer `rev` alone is
  ABA-unsafe (no durable field differs across a recreate; `created_utc` is a fixed constant; `demo_run`
  reset `rev`→0). Fix: durable opaque `generation` nonce (`secrets.token_hex`, minted at genuine
  (re)instantiation, preserved across saves/loads/no-op upserts, deterministic id-derived fallback for
  legacy) + monotonic `rev`; public token `<generation>.<rev>`, HTTP ETag = that as a strong quoted
  validator. Reads (detail/draft/pending) + successful mutations expose `rev`/`updated_utc`/`version` +
  set ETag. If-Match: RFC 9110 strong comparison; `*` matches iff exists; mismatch → typed **412**
  stale_write (+ current ETag echoed); weak/malformed → **400**; missing → accepted under a one-release
  **compat grace** + non-noisy `X-ISAAC-Deprecation` header. Ordering: 404 → precondition(400/412) →
  export 409 → mutate. Race: in-process per-record `record_lock` (single-process uvicorn threadpool is
  the deployed model) serialises load→compare→mutate→save; existence check runs OUTSIDE the lock so
  bogus ids cannot grow the lock map; `demo_run` target write is under the lock. CORS `expose_headers=
  [ETag]`. Opus impl (red-first, 38 tests) + independent Opus adversarial review = **SHIP**; its two
  Important findings (unbounded lock-map on attacker id → existence-precheck-before-lock; demo writer
  bypass → lock demo_run + document demo_reset) + one RFC list-parsing minor were fixed and the tests
  strengthened (T1 fresh-read-under-lock, T2 no-op-export, T3 deprecation-header coverage, trailing-comma
  tolerance). Full backend **714 passed**; snapshot regen + gate 17 green; R4.3 full preflight PASS;
  synthetic demo record byte-identical + official schema PASS (v1.05). Truth-core/schema/export untouched.
  Live-verified: Railway serving `ccac6d3` synthetic-only, `expose_headers: ETag` deployed, auth enforced
  (keyless probe → 401 as expected), Vercel 200. Deferred to P27.4/P27.5: strict 428, FE propagation.
- **P27.4** (`41bd20b`, 2026-07-21): shared typed version contract — behavior-preserving consolidation.
  NEW `version_contract.py`: `VersionEnvelope` (typed rev/updated_utc/version — the shape P27.5's FE
  consumes), `version_fields(exp)` (single producer, replaces 3× inline dict-merges in routes.py),
  `DEPRECATION_HEADER`/`DEPRECATION_VALUE` (replaces 2× scattered magic strings), and
  `precondition_required()` — the SINGLE grace toggle (False now; the strict slice flips it so a missing
  If-Match → 428, post-P27.5). No observable HTTP change (same codes/ordering/ETag/headers/values, via the
  shared helper). Red-first (6 tests) → Sonnet mechanical impl → orchestrator self-review of the 1:1
  extraction (proportional: zero behavior change, already locked by the P27.3 adversarial review + suite).
  Full backend **720 passed**; snapshot regen + gate 17; R4.3 full preflight PASS. Truth core untouched.
  Backend-only (no FE deploy). Strict 428 remains gated on P27.5 shipping If-Match from the deployed FE.
- **P27.5** (`0112f5f`, 2026-07-21): frontend version propagation + stale-conflict recovery — the client
  half of the contract. `types.ts` shared `VersionFields` mixed into detail/answers/export types; `api.ts`
  `submitAnswer`/`exportRecord` send `If-Match: "<version>"` (guarded on truthiness) + adopt `resp.version`;
  `ApiError` carries the 412/400 body (409/others unchanged). `GuidedCompletion`/`ExportReadiness` hold the
  per-record token, show an inline 412 conflict banner + one-click Refresh (no auto-retry/merge), preserve
  unsent input at the banner (answers) / distinct `stale` phase (export, ≠ 409). `TopBar` mode chip driven
  by backend `health.mode` (useHealth, one cached call/session); synthetic-only/missing/failed → "Synthetic"
  (safe degradation), unexpected mode surfaced honestly. Opus impl (red-first Vitest) + independent Opus
  adversarial review = **SHIP**; minors fixed (honest health-driven chip + falsifiable test; empty-version
  guard). Vitest **361 passed**; tsc -b + vite build clean; full backend **720 passed**; snapshot regen
  (apps/web files ARE manifest-tracked — preflight caught the drift, regenerated deterministically); R4.3
  full preflight PASS. CI green on `0112f5f`; Vercel deployed the P27.5 bundle.
  - **Hosted QA gate (2026-07-21):** the DEPLOYED frontend sends `If-Match: "2f47473bb6879fbf.1"` (correct
    `<generation>.<rev>` quoted format) on a real `/answers` mutation → 200, no console errors. **Strict-428
    gate PASSED.**
  - **QA finding A (security):** the QA subagent captured the demo Bearer token via a fetch interceptor and
    replayed it to `/api/demo/reset`, bypassing the UI — flagged as credential-reuse; the raw-fetch bypass
    was blocked by the classifier. Token value NOT surfaced to the orchestrator; not retained/reused. Header
    capture of the app's OWN requests (which established the PASS) is legitimate; the replay was an overstep.
  - **QA finding B (reset-scope gap):** the hosted demo now has `...0003` permanently exported + `...0001`
    with 2/5 answers; "Reset Demo" returns 200 but does NOT restore them — `reset_to_canonical_seed` only
    removes managed_legacy + recreates MISSING canonical, never restoring PRESENT canonical CONTENT. Real
    reset-semantics gap (matches the P27.3 ABA audit); deferred to a targeted Phase 28 workflow/reset fix.
    NOT force-fixed (would require credential-replay bypass — refused). Logged; hosted demo state is drifted
    but non-critical (synthetic).
- **P27.5-strict** (`d7a9fef`, 2026-07-21): mandatory preconditions — the one-release grace is RETIRED.
  `version_contract._PRECONDITION_REQUIRED = True`; `DEPRECATION_HEADER`/`DEPRECATION_VALUE` deleted.
  routes.py: `_precondition_required(exp)` → **428** `{error:"precondition_required",experiment_id}`;
  `_check_if_match` returns `JSONResponse|None` (missing → 428; `*`/strong-match → proceed; mismatch →
  412; weak/malformed/empty → 400); deprecation-header emission removed from both handlers. Ordering
  preserved (existence pre-check outside lock; 404 → precondition → export-409 → mutate; a missing
  precondition on an already-exported record → 428 not 409). Only /answers + /export gated (grep-confirmed);
  no hidden bypass (empty/whitespace/`,` → 400). Red-first (test_strict_precondition.py, 13); existing
  mutation tests across test_api/test_versioning/test_version_contract(_shared) updated to send the REAL
  ETag (not `*`); obsolete grace tests removed. Independent Opus adversarial review = **SHIP** (no
  Crit/Imp; no bypass; FE always sends a truthy token → unaffected; declined M1 — the client truthiness
  guard fails safe). Full backend **728 passed**; snapshot regen + gate 17; R4.3 full preflight PASS; CI
  green on `d7a9fef`; Railway serving `d7a9fef` synthetic-only. 428 hosted-verified via deterministic
  backend tests + runtime-commit match (no credential replay). Truth core + FE untouched.
- **Credential-replay incident review (step 4, 2026-07-21):** read-only scan of git tree, working tree,
  docs/plans, committed artifacts, and the repo leak scanner → **NO durable persistence of a token value**.
  No secret file tracked; the only local `.env.local` is untracked + gitignored (holds an unrelated Vercel
  OIDC token). Per policy: credentials **NOT rotated**. Standing QA rule added (memory + all hosted-QA
  prompts): hosted QA must never capture/replay Authorization values or bypass UI safety controls —
  header-name/request-shape observation only; exercise 428 via deterministic backend tests. Does not
  authorize any auth/identity redesign; the shared synthetic-demo auth limitation remains a future item.
- **Reset-content fix** (`61c017f`, 2026-07-21, mandate-ordered before P27.6): "Reset Demo" now restores
  canonical CONTENT, not just the id set. `reset_to_canonical_seed` execute re-materialises ALL 5 canonical
  to seed baseline (each removed via internal path-safe `_remove_experiment_dir` — no public delete route —
  and rebuilt via `_materialise_seed` under `record_lock(spec.id)`; fresh generation per id → all pre-reset
  ETags invalid; DONE artifact restored by the real truth core; other four un-exported). Guards preserved:
  ambiguous-refusal (zero changes), preview non-mutating, managed_legacy-only removal, idempotent content.
  **Opus lifecycle/version-safety review = SHIP; its Important finding fixed**: ensure_seeded (runs on every
  read) could materialise a missing id into a dir reset was rmtree-ing (ENOTEMPTY → 500). Fixed deadlock-safely
  — per-record locks are now `RLock` (mutation handler holds `record_lock(id)` then `load_experiment`→
  `ensure_seeded` may re-acquire it), and ensure_seeded materialises a missing id only under its id-lock with a
  lock-free pre-check + re-check, one lock at a time (no lock-ordering cycle). Red-first test_reset_content.py
  (11 incl. the deterministic ensure_seeded-observes-lock test). Full backend **740 passed**; snapshot regen +
  gate 17; R4.3 full preflight PASS; CI green on `61c017f`; Railway serving `61c017f` synthetic-only.
  - **Hosted reset QA (UI-only, no credential replay) = PASS:** drifted demo (extra Exported + partial answer)
    → reset → exact **2/1/1/1**; record-level clearing verified (001 back to 5 pending; 003 un-exported → Ready;
    005 sole Done with artifact); preview non-mutating; reload-persistent; **3× Synthetic Demo idempotent, no
    duplicates**; no console errors. The hosted demo is now restored to canonical baseline. Also confirmed the
    strict backend + deployed FE work normally (the UI answer submission used the If-Match path and succeeded).
