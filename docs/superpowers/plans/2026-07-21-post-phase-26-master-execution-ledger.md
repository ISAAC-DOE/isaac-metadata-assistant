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
| **Current phase** | **Phase 30 COMPLETE** (2026-07-22): Runtime-retrieval proof gate REJECTED a persistent index (measured); shipped a thin Workspace-derived runtime provider (`/runtime/records`, no index/cache/service) + a cross-record triage consumer (SearchDialog), hosted-QA PASS (correct matching, honest empty states, current-by-construction, clean handoff to authoritative record). → Phase 31. |
| **Active ticket** | **Phase 32 (final: QA + hardening) — next.** Phase 31 CLOSED 2026-07-23 (RECONCILIATION-ONLY): P31.1 ingress (`80042f3`) + P31.2 reconciliation (`3ecda47`) + P31.3 review UI (`7b202b6`) + docs (`265e23f`) + B1 flake fix (`e45db20`) + P31.4/closure. Independent review SHIP; CSV parses/reconciles/reviews evidence only — no official-field mutation, confirmed-write surface NOT extended. Phase 32 issue register seeded at `docs/superpowers/plans/2026-07-23-phase-32-issue-register.md`. |
| **Completed** | **Phase 27 (all slices)**: T0 (`859d36c`); P27.0; approval (`33825ff`); P27.1 (`26642eb`); P27.2 (`14477bd`); P27.3 (`ccac6d3`); P27.4 (`41bd20b`); P27.5 (`0112f5f`); P27.5-strict (`d7a9fef`); reset-content (`61c017f`); P27.6 (`ef31f5b`); P27.7 hosted two-tab QA (conflict-safety hosted-PASS). **Phase 28**: P28.0 audit + plan (`a0e2a09`); P28.1 fixed workflow order (`e434de2`); P28.2 dep invalidation + artifact freshness (`859309f`); P28.3 revisit/summary/edit (`039ac1b`); P28.4 evidence classifier (`b1b9cd0`); P28.5 typed evidence API+UI (`bea0a01`) |
| **Next step** | Phase 31 (Synthetic/Public File Ingestion) — P31.0 format selection (human-gate 5 possible) → P31.1 upload boundary → P31.2 deterministic parser → P31.3 assistant/manual review → P31.4 QA. Strict: synthetic/public only, NO real/private data, sandboxed, deterministic; candidates stay candidates (reuse P28.4/P29.6). |
| **Blockers** | none |
| **Latest impl commit** | `7b202b6` (P31.3 CSV review UI); `e45db20` (B1 flake fix) |
| **Latest checkpoint commit** | this Phase 31 closure docs commit (pending push) |
| **Verification status** | full backend **887 passed**; frontend **542 passed** + build clean + tsc 0; snapshot gate 17/17; 61 CSV tests; truth export PASS (v1.05) + audit 21/21; CI green on `e45db20`; Railway `synthetic-only` @ HEAD; Vercel `isaac-demo-web.vercel.app` P31.3 bundle live; independent review SHIP; hosted QA PASS (2 honest human-only NOT-OBSERVED) |
| **Open QA caveat** | P27.7 scenarios 1 (idle passive-poll banner + ~8s cadence) & 5 (offline degraded indicator) NOT hosted-observed — Claude-in-Chrome drives tabs `visibilityState=hidden` and polling is correctly visibility-gated, so an automated hidden tab doesn't passively poll. Both behaviors are deterministically unit-tested (visibility pause/resume, backoff, degraded, LiveSyncNote) + the conflict path is hosted-verified. Recommend a human TWO-WINDOW (both visible) session to visually confirm. Not a defect; not a blocker. |
| **Open decisions** | ledger→resume skill wiring (skill edit needs approval); strict 428 enforcement gated on deployed-FE sending If-Match (P27.4/P27.5) |
| **Approved constraints** | synthetic-only; no LLM; no real data; no new cloud service; no account/billing change (except `ISAAC_RUNTIME_MODE` add) |
| **Next recommended action** | P31.0 — choose the supported synthetic/public ingestion file format from repo evidence (single XANES/characterization path); STOP for human-gate 5 if none is defensibly derivable. No real/private data. |
| **Git sync** | `main` · local == `origin/main` == `e45db20` · 0/0 · clean (before this Phase 31 closure docs commit) |
| **Exact-HEAD CI** | `e45db20` green (run success); P31.3 `7b202b6` green (29990266606); this closure docs commit pending push-time verify |
| **Railway note** | 2026-07-22: rapid P28.1–P28.5 pushes queued serial Railway builds (each Docker build ~minutes on the metal builder). Builds SUCCEED (image push + healthcheck pass in logs); serving `37713d7`, draining the backlog toward HEAD. Not stalled/failed. Confirm Railway == Phase-28 HEAD (has `/edit` + `/evidence-classification`) before P28.6 hosted QA. |
| **Railway** | Online · commit `92ea16f` · `mode: synthetic-only` · volume `/data/isaac-workspace`; host `isaac-metadata-assistant-production.up.railway.app` |
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

- **Current phase:** 28 (Workflow & Evidence Contracts). **Active slice:** P28.1 (next).
  **Completed:** all of Phase 27 (T0 → P27.7); Phase 28 P28.0 audit + plan.
- (The authoritative live status is the STATUS BLOCK at the top of this file; this section is the
  narrative pointer and was reconciled forward on 2026-07-22 — it had stale-carried "phase 27 / P27.1
  next" wording from ledger creation.)

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
- **P27.6** (`ef31f5b`, 2026-07-22): live client synchronization — bounded revision-aware polling.
  SSE ruled out (EventSource can't send the Bearer header; no cookie auth; sync single-process
  deployment) — validated against the code. Backend (Option A, no new route): `GET /experiments/{id}`
  honours `If-None-Match` → 304 (unchanged, ETag, no body) or 200 + bundle + new ETag; `_if_none_match_hit`
  normalises W/, handles tag-list + `*`, never false-304s a changed record; If-Match mutation path
  untouched; 304 carries CORS ACAO + Expose-Headers:ETag. Frontend: `checkRecordVersion` + `useRecordSync`
  (ONE per-record poller — records are separate routes, one mounted at a time): 8s base, setTimeout-chain +
  in-flight guard (non-overlap), AbortController + version/id stale-guard, visibility pause + immediate
  check on regain, bounded backoff (cap 60s) + ±20% jitter, honest `degraded` after 3 real failures. Poll
  machinery is per-effect-run LOCALS (not shared refs). Wiring: S3/S5 silent refetch; S4 proactive
  "changed elsewhere, input preserved" banner + Refresh (no auto-refetch/merge; submit stays If-Match →
  412 backstop); S6 silent readiness refetch; dashboard visibility-regain silent reload only; `LiveSyncNote`
  (role=status) honest paused indicator. Opus adversarial review = **DO-NOT-SHIP → SHIP after fix**: its
  Important finding (shared-ref scheduler could silently kill polling on an in-place version change → stale
  without signal) fixed via the per-effect-locals refactor with a red-green liveness regression test
  (fails pre-fix); minors fixed (dashboard silent reload; degraded reset on version change). Backend
  live-sync tests 11; full backend **751 passed**; frontend **383 passed**; tsc -b + vite build clean;
  snapshot regen + gate 17; R4.3 full preflight PASS; CI green on `ef31f5b`; Railway `ef31f5b`
  synthetic-only; Vercel P27.6 bundle live. Truth core untouched; no credential in URL/query/log/output.
- **P27.7** (hosted two-tab QA, 2026-07-22, UI-only, no credential capture/replay): the revision-aware
  conflict-safety core **PASSES conclusively on the live deployment** — (2) stale answer → **412** with the
  exact "changed elsewhere / nothing applied / input kept / refresh" banner, input preserved, no auto-merge,
  Tab A data intact, Refresh recovers; (3) stale export → **412**, no stale artifact written, no duplicate,
  recovery to the immutable view; (4) Reset → exact canonical **2/1/1/1**, added answers cleared, ...003
  reverted from Exported to Ready, only ...005 Done, no duplicates; (6) restart recovery (the P27.6 deploy)
  → app/health/polling recover, no error loop. No RED console errors. Demo left at canonical 2/1/1/1.
  - **QA CAVEAT (honest, tooling-bound — NOT a defect):** scenarios (1) idle passive-poll banner + ~8s
    bounded cadence and (5) offline degraded indicator could NOT be exercised, because Claude-in-Chrome
    drives tabs via CDP with `document.visibilityState === "hidden"` and the app's polling is CORRECTLY
    visibility-gated (a hidden tab does not poll — a P27.6 requirement). Both behaviors are deterministically
    unit-verified (record-sync.test.ts: visibility pause/resume + immediate check on regain, bounded backoff,
    degraded threshold; live-sync-screens.test.tsx: LiveSyncNote honesty), and the change-detection path is
    hosted-verified via the 412 conflict tests. Per the mandate's P27.7 fallback, this limitation is stated
    honestly rather than fabricated. **Recommended human follow-up: a two-WINDOW session (two genuinely
    visible OS windows) to visually confirm the idle banner, the ~8s cadence, and the offline indicator.**
  - 428-on-missing-If-Match not produced via UI (the FE always sends If-Match); covered by deterministic
    backend tests (test_strict_precondition.py). No credential value captured/copied/replayed; DevTools not
    used for token access.
- **P28.0** (read-only audit, 2026-07-22): confirmed `92ea16f` exact-HEAD CI (run `29901071582`) **success**;
  Railway `92ea16f` synthetic-only; Vercel 200; clean 0/0. Four parallel read-only tracks (backend workflow,
  evidence/audit/export, frontend nav, tests/docs/snapshot) produced an evidence-anchored current-state map
  → plan `docs/superpowers/plans/2026-07-22-phase-28-workflow-evidence-plan.md`. **Key findings:** no backend
  workflow-step model (single derived `status()`, completion never persisted); the frontend `WorkflowSpine`
  is a hardcoded 5-step array with `active` re-derived per-screen = the forbidden frontend-only completion
  model; evidence has two orthogonal truth axes (field-status + source_type) with a committed Phase-21
  vocabulary; no conflict/insufficient/unknown/general-inferred-candidate class exists; exported artifacts
  can silently drift with **no** staleness representation (same class as the reset-content gap fixed in
  `61c017f`, not generalized); the five concepts (schema validity / evidence support / workflow completion /
  export readiness / advisory) are already cleanly distinct. **No hard gate:** the only potential
  spec-collision (P28.4 `inferred_candidate` vs committed `inferred`-exports) is resolved by scoping P28.4 as
  a display/classification layer that does not change truth-core gating (plan §2.1). Truth plane untouched;
  audit was read-only.
- **P28.1** (`e434de2`, 2026-07-22): fixed canonical workflow order, backend-derived. NEW pure module
  `workflow.py` `derive_workflow(pending_count, draft_ok, ready, exported, rev)` → ordered 5-step sequence
  (`load_record → complete_metadata → review_evidence → review_export_readiness → export`) with per-step state
  `{completed, current, reopened, blocked}` derived from current truth only — never persisted, never reordered,
  never client-recomputed; surfaced in every detail bundle via `_detail`. Frontend `WorkflowSpine` rewritten to
  render `detail.workflow.ordered_steps` verbatim; the hardcoded 5-step array + per-screen `active` re-derivation
  (the forbidden frontend-only model) removed from all three record screens. `reopened` visually + textually
  distinct from `blocked`; a11y preserved. **Test-first:** the orchestrator authored `test_workflow_order.py`
  RED (9 failing) before delegating; Opus impl made it green. Independent Opus review = **SHIP-WITH-FIXES** →
  finding **I1** fixed: `review_export_readiness` now uses NEW `Experiment.export_ready()` (current-draft dry-run,
  independent of the frozen `exported` flag) so a regressed exported record honestly shows *reopened* readiness
  instead of a misleading green step; added a route-reachable reopened integration test. Backend **762** (was 751),
  frontend **390** (was 383), tsc clean, Vite build ok. Truth core (`src/isaac_records`, `schema`) untouched.
  Snapshot deterministically regenerated (routes.py/workspace.py + 7 web files are manifest-listed). Deferred
  non-blocking: M1 (surface reopened context on the current step — folds into P28.2/P28.3 reason enrichment),
  M2 (memoize the double `status()`/`export_ready()` dry-run — micro-opt, negligible at 5-record scale → P32.2).
- **P28.2** (`859309f`, 2026-07-22): dependency-aware downstream invalidation + exported-artifact freshness,
  fully DERIVED (no new persisted field, no second workflow store). NEW `dependencies.py`:
  `artifact_state(exp)` compares `transform(current_draft, now=<on-disk created_utc>)` canonical-JSON against the
  on-disk exported record → `none|current|stale` (never throws; missing/unreadable → stale). `title`/`source`
  are not in the official record, so a presentation-only change stays `current` while a scientific change goes
  `stale`. Both authoritative mutations now return `workflow` + `invalidation {changed, rev, changed_fields,
  reopened_steps, artifact, reason}`, built atomically inside the existing `record_lock` at the single
  post-mutation rev; a byte-stable no-op invalidates nothing and does not bump rev. `_detail` carries `artifact`;
  ExportReadiness shows a minimal honest `role=status` stale advisory. Single-artifact immutable policy: mark
  stale (regeneration-required), never auto-delete/silently-current. Forward API mutations cannot un-complete a
  step (`apply_answers` only fills pending) → `reopened_steps=[]` for forward mutations by design; reopen surfaces
  via the derived GET workflow. **Test-first:** orchestrator pinned the 5 contract tests RED; Opus impl added 5
  behavioral (incl. workspace-level regression + presentation-vs-scientific). Independent Opus review = **SHIP**
  (no Crit/Imp; empirically disproved false-stale — exported records re-derive byte-identically). Backend **772**
  (was 762), frontend **392** (was 390), tsc clean, build ok. Truth core untouched (`transform`/`export_draft`
  read-only). Snapshot regenerated. **Known non-blocking limitations:** (a) sidecar (`.evidence.json`) freshness is
  NOT tracked — `artifact_state` compares the official record only (matches the contract + sidecar-only fields per
  CLAUDE.md §5) → note for P28.5/P32; (b) `changed_fields` lists submitted answer keys and may over-report on a
  partial no-op (advisory only; staleness is content-derived).
- **P28.3** (`039ac1b`, 2026-07-22): revisit, summary-first & explicit edit. Backend NEW
  `complete.apply_corrections` (non-truth authoring module, sibling to `apply_answers`) OVERWRITES an
  already-confirmed field's value even at 0 pending, records a fresh `user_confirmation`, never touches
  `pending`; same no-guessing contract (only supplied values; malformed sha/off-enum qc rejected; identical
  value = byte-stable no-op, equality-guarded per branch → no evidence churn / no rev bump). NEW
  `POST /experiments/{id}/edit` mirrors `post_answers` exactly (404→lock→404→422→If-Match 428/412/400→apply→
  single save_versioned→P28.2 invalidation→workflow+ETag); unrecognized field → 422. Editing an exported
  record stales the artifact (P28.2, derived). FE: summary-first read-only confirmed fields + a real
  keyboard-accessible Edit button; inline GuidedPrompt prefilled with the current value; Save uses If-Match +
  adopts resp.version + surfaces invalidation reason / stale note via role=status; Cancel = no mutation; 412
  reuses the stale-write recovery (no auto-merge); viewing/editing never flips the backend-derived workflow;
  completed styling persists. Tests: `test_edit_field.py` (10, RED-first) + `edit-field.test.tsx` (6). Backend
  **782** (was 772), frontend **398** (was 392), tsc clean, build ok. Frozen truth path untouched;
  `complete.py` extended additively (stdlib-only); `tests/test_complete.py` green. Independent Opus review =
  **SHIP** (no Crit/Imp; no-guessing + no-op empirically clean). Non-blocking: qc-correction branch
  unreachable via `/edit` (mirrors existing `/answers` wiring); descriptor/series no-op shape-sensitive & not
  yet test-covered.
- **P28.4** (`b1b9cd0`, 2026-07-22): deterministic evidence-support classification. NEW `evidence_classify.py`
  `classify_fields(draft)` — a pure display VIEW composing field-status + source_type into a third axis with
  five classes (precedence `conflicting_evidence > supported > inferred_candidate > insufficient_evidence >
  unknown`); emits `{field, classification, value_state, explanation, sources}`, no verdict keys, no truth
  change. Mapping-audit boundary: truth-core `inferred` (rule + present value, exports today) → `supported`
  (NOT `inferred_candidate`; the candidate class is reserved for a rule proposal whose value is unconfirmed —
  the `implicit['edge']` null pattern). Insight: the raw seed's unestablished items live in `draft['pending']`
  (workflow-blocker axis), NOT the evidence-trail surface — so the view honestly shows no fabricated `unknown`
  fields for them (evidence-support is orthogonal to workflow-pending). `sources` leak-safe: only
  `{source_type, locator?}`, filtered against absolute/private paths + token-like hex; raw answer/quote/sha256
  never emitted. Tests: `test_evidence_classify.py` (16, RED-first) incl. a security regression pinning the
  leak-safety property (independent-review must-fix, added by orchestrator). Backend **798** (was 782); truth
  path untouched; NO route/FE change (API+UI = P28.5). Independent Opus review = **SHIP** after the leak test
  (no code bug; correct/pure/truth-safe/leak-safe on every probed dimension).
- **P28.5** (`bea0a01`, 2026-07-22): typed evidence-classification API + Review-Evidence UI. Backend NEW
  `GET /experiments/{id}/evidence-classification` → `{record_rev, field_results, counts}` (read-only, typed
  404, auth-gated, ETag; calls the frozen P28.4 `classify_fields`; no lock/mutation). Axis-clean: only the
  evidence-support axis (no valid/ok/exportable/complete/blocking/warnings); `counts` is a same-axis 5-class
  histogram (chosen over the mandate's sample `audit_summary` to honor the separate-axes rule). FE: NEW
  `EvidenceClassificationPanel` on S5 renders each field's class with icon + text + explanation + safe sources
  + keyboard-operable info affordance; scientific honesty — `inferred_candidate` is unmistakably distinct from
  a supported/confirmed value (dashed chip, distinct label/icon) and the panel NEVER renders a candidate's
  value; `unknown` = plainly absent; `conflicting_evidence` = no auto-winner. Folded into `getEvidenceBundle`
  (refetches coherently on live-sync); honest `role=status` "may be out of date" affordance when view rev !=
  record rev (no auto-flip). Tests: `test_evidence_classification_api.py` (8, RED-first) + `evidence-
  classification.test.tsx` (10). Backend **806** (was 798), frontend **408** (was 398), tsc clean, build ok.
  Truth path + P28.4 classifier untouched. Snapshot regenerated. Independent Opus review = **SHIP** (candidate
  != confirmed invariant holds; leak-safe end-to-end; axis-clean; no regression).
- **Railway deploy queue-stall incident** (2026-07-22): the rapid P28.1–P28.5 pushes (each impl + ledger)
  overwhelmed Railway's serial builder — deployments **built and healthchecked successfully** but the next one
  sat `Queued` ~20–28 min while live stayed behind HEAD. User authorized ONE bounded recovery nudge (`railway
  up`/redeploy of clean HEAD, existing Krish-owned service, no config/identity/volume/secret change). Before
  using it, the queue **self-drained** (status went Queued → Building → Deploying → serving `938c4e4`), so the
  authorized nudge was **NOT used** (avoided a redundant deployment — the least-disruptive outcome). Deploy
  reached HEAD `938c4e4` synthetic-only, volume `/data/isaac-workspace` 36/500 MB intact. Lesson: batch fewer
  rapid pushes, or expect serial-build lag; recovery = wait (self-drains) or one bounded `railway up`.
- **P28.6** (hosted QA, 2026-07-22, UI-only, no credential capture/replay; against Railway `938c4e4` + Vercel):
  full matrix **PASS** (A–H), **no functional defects**. Fixed workflow order verified across needs-attention/
  ready/exported states (order never reorders; completed/current/blocked distinct by icon+text, not
  color-only; deep-links + refresh preserve state). Summary-first + explicit Edit: pre-fill, Cancel=no-op,
  same-value=no-op (`/edit`→200), new-value persists. Evidence panel: `Supported` (27) vs `Inferred Candidate`
  (1) visually + textually distinct, candidate shows NO value as fact; ⓘ keyboard-operable; sources leak-safe
  (only synthetic locators, no token/`/Users/`). Two-tab stale write → **412** exact banner "changed elsewhere
  … nothing applied … input kept", no auto-merge. Exported artifact shows honest **current** (validate --official
  exit 0, audit 33/33). Reset → canonical **2/1/1/1**, no duplicates. No red console errors; all API 200/304
  except the one intentional 412; no request storm. **Two honest NOT-OBSERVED (non-blocking):** (1) passive
  idle-poll ~8s banner — CDP tab `visibilityState=hidden` blocks visibility-gated passive polling (carry the
  human two-window follow-up); (2) artifact **stale transition** — the deployed UI exposes no field-edit path
  on an EXPORTED (immutable) record, so staleness can't be triggered via UI; it is backend + unit-verified
  (`test_editing_exported_record_stales_the_artifact`) and the UI never shows stale-as-current (by-design
  immutability). Minor observations (not defects): a single Reset confirm issued two idempotent `/demo/reset`
  200s (end-state correct); a "Use This Suggestion" input occasionally needed a beat (worked on retry) → note
  for P32 UI audit. Demo left at canonical 2/1/1/1.

---

## Phase 30 — Live Runtime Record Retrieval (in progress)

- **P30.0** (Runtime Retrieval PROOF GATE, read-only, 2026-07-22): 2 parallel tracks (search-capability +
  use-case matrix; performance at 5/50/100/500 synthetic) → plan
  `docs/superpowers/plans/2026-07-22-phase-30-runtime-retrieval-plan.md`. **Findings:** P26 search is a fresh
  index-free live scan (current-by-construction, leak-scrubbed); the status-axis cross-record triage already
  ships (ExperimentsHome); the one real in-scope gap is that the assistant is strictly single-record. **Perf
  (near-worst-case):** full `/search` ~9 ms @5, ~108 ms @100, ~560 ms @500; bottleneck = `status()`'s
  per-record export dry-run (NOT disk/index-absence); memory negligible. **Decision:** **Option D (persistent
  index) REJECTED** (no measured need; fresh scan already exists; durable second store unjustified); **Option
  C (cache) rejected** (direct derivation interactive at ≤100); **Option A insufficient alone** (free-text
  can't do structured derived-state filters); **SELECTED Option B — a thin read-only Workspace-derived
  runtime provider over the SAME scan** (no index/cache/service/secret), emitting safe confirmed-facts +
  record_rev + navigate_to, with ONLY the typed filters a concrete consumer uses — a deterministic
  cross-record assistant triage intent + a SearchDialog filter. Speculative filters (missing-field, full
  evidence-class sweep) SCOPED OUT (no consumer → not built; "no provider ahead of its consumer"). No human
  gate; no infra change → proceed. Truth path untouched; docs-only.

- **P30.1** (`964a7ec`, 2026-07-22): thin read-only runtime record projection + typed filters (Option-B). NEW
  `runtime_records.py` `project_records(experiments, *, filters)` — pure, Graphify-free, over the SAME
  `list_experiments()` scan; NO index/cache/service/secret; current-by-construction. Emits ONLY the safe
  confirmed-facts allow-set (evidence counts-only, workflow current_step+2 booleans, artifact_state string,
  record_rev/updated_utc, navigate_to=`/record/<id>`); reuses status/derive_workflow/classify_fields/
  artifact_state read-only. `GET /runtime/records` → {records,total}, conjunctive typed filters (status/
  workflow_state/artifact/has_conflict), unrecognized value → matches NOTHING, deterministic order, auth via
  middleware. Tests: `test_runtime_records.py` (13, red-first) incl. a CRAFTED-SECRET projection guard +
  unrecognized-filter-empty guard (the two independent-review must-fix test-gaps; impl was already secure per a
  crafted-secret probe). Backend **819** (was 806), truth path frozen, snapshot regenerated. Independent Opus
  review = SHIP-WITH-FIXES → fixed. Non-gating: export_draft dry-runs twice per ready/in_review record (fine at
  demo scale; memoize if scale grows). P30.2 (filters/pagination) folded in here.
- **P30.3** (`8346d7b`, 2026-07-22): cross-record triage consumer (justifies the P30.1 provider). NEW pure
  `crossRecordTriage(records, intent)` (needs_attention/blocked/has_conflict/exportable) over the SAFE
  projection → `{text, matches:[{experiment_id,title,navigate_to,reason}]}`; `navigate_to` reconstructed as
  `/record/<id>` (no foreign target), reasons count/flag only (never a value/winner/verdict), unknown→empty.
  `api.getRuntimeRecords`; a self-labeled SearchDialog "Cross-record triage · Workspace-derived · a lead, not
  the record truth · never a verdict" quick-actions surface (empty-query state; two-plane separation intact);
  opening a match HANDS OFF to the authoritative `/record/<id>` load; fetch failure → honest role=status
  unavailable, search still works. Tests: `cross-record-triage.test.ts` (8, red-first) + `-ui.test.tsx` (7).
  Frontend **524** (was 509), tsc clean; truth path + backend untouched (no new endpoint); snapshot
  regenerated. Independent Opus review = **SHIP** (truth-substitution boundary + no inferred/conflict-as-fact
  clean; no open-redirect — backend ULID ids + same-origin route). Deferred nits → P32: encodeURIComponent id
  guard; error-chip aria-pressed.
- **P30.4** (`47e91ae`, 2026-07-22): refresh/reset/degradation — VERIFICATION-ONLY (no new code). The provider
  is stateless-derived, so freshness holds by construction; added confirming tests (reset re-derives canonical
  2/1/1/1 with no stale retention; `project_records([])` → [] — a record absent from the scan is absent from
  the projection). Degradation covered by P30.3 UI tests. Backend **821**.
- **P30.5** (hosted QA, 2026-07-22, UI-only, no credential capture; Railway `8346d7b` + Vercel): PASS A–G (F
  NOT-OBSERVED). Triage chips return correct records vs workspace (needs-attention 2, blocked 3, ready 1,
  has-conflict honestly EMPTY); labeled Workspace-derived lead, separate from Project Memory, no verdict/value/
  winner; **handoff** verified (Ready-to-Export row → `/record/…003` → authoritative record view, not inline
  summary); **freshness** verified (exporting …003 dropped it from Ready-to-Export, no stale cache); Reset →
  2/1/1/1 no duplicates; single-fetch-per-click, no polling storm, no console errors, no row leak; credential-
  safe. NOT-OBSERVED: triage fetch-failure degradation (not safely UI-inducible — unit-tested in P30.3).
  Pre-existing non-P30 note: the EXPORT detail screen shows the Railway volume path `/data/isaac-workspace/…`
  (an artifact path shown since Phase 20; not a triage-row leak) → flag for the P32 UI audit.

- **P30.6** (`b5cf608`, 2026-07-22): internal artifact-path exposure correction (pulled forward from P32 per
  review — fix the user-facing path leak BEFORE ingestion adds stored-file concepts). The API leaked ABSOLUTE
  server paths (`/data/isaac-workspace/…`) to the browser at THREE sites (`_detail.artifact_refs`,
  `POST /export`, `GET /artifacts`, all `str(exp.record_path())`). Fixed at the serialization boundary (not
  CSS): all three return `record_filename`/`sidecar_filename` = basename only (None when not exported);
  server-side file resolution unchanged (from record id, no traversal); View/Download unchanged (JSON content
  Blob, not path). FE migrated (types/ExportReadiness/assistantComposer/fixtures) — grep confirms zero
  `record_path`/`recordPath` refs left, no `/data/` can render. Tests: `test_artifact_path_safety.py` (5,
  red-first) sweeping all 3 sites + a FE no-path test + a snapshot no-leak guard. Backend **826**, frontend
  **525**, tsc clean; truth path frozen; snapshot regenerated. Independent Opus review = SHIP (leak eliminated
  at the boundary; no residual absolute-path field anywhere; access preserved).

## Phase 31 — Synthetic/Public File Ingestion (in progress)

- **P31.0** (format + threat-model PROOF GATE, read-only, 2026-07-22): targeted `rg`/`Read` audit → plan
  `docs/superpowers/plans/2026-07-22-phase-31-ingestion-plan.md`. **Decisive repo evidence:** a deterministic
  parser ALREADY exists — `extract.structured.parse_structured` reads a campaign metadata sheet (.csv stdlib /
  .xlsx openpyxl) via an explicit `FIELD_MAP` (field→official dotted path + type, no-guessing) with
  `spreadsheet` evidence locators (tested); `POST /uploads` is an existing governance refusal seam; P29.6
  confirm + P28.4 classify + P27 version all reusable. **DECISION: initial format = CSV** (stdlib csv, zero new
  dep, lowest attack surface, existing tested parser + FIELD_MAP + evidence locators); xlsx DEFERRED (parser +
  openpyxl dep exist, but ZIP surface); HDF5/NeXus/CIF/XML/ZIP/Office/PDF/images/binary REJECTED (no repo
  evidence, dangerous). **No human gate** (format grounded in an existing parser; no new dep/service/secret/
  real-data). Architecture: bounded IN-MEMORY read (no temp file → eliminates the filesystem-safety threat
  category); reuse parse_structured + P29.6 candidates/confirm + P28.4 classify. Threat model + limits +
  candidate/evidence contract + 6 leaner slices in the plan. Truth path untouched; docs-only.

- **P31.1** (`80042f3`, 2026-07-22): safe CSV ingress + read-only typed preview. NEW `POST /experiments/{id}/
  ingestion/csv/preview` — RAW `text/csv` body (NOT multipart), BOUNDED stream read (`_read_bounded_body`:
  async-for `request.stream()`, 413 before full allocation; NO python-multipart / UploadFile /
  SpooledTemporaryFile / temp file / new dep — all-in-memory by construction). Order: auth(middleware) →
  runtime-mode 403 → 404 → If-Match 428/412/400 → bounded read → utf-8-sig strict (empty/invalid-utf8/NUL →
  400) → CSV v1 validate → in-memory parse → typed preview. READ-ONLY (no write/rev-bump/export/index/persist).
  CSV v1 = ISAAC campaign sheet (`section,field,value,unit,notes`), comma-only (no Sniffer), FIELD_MAP-only
  (unmapped skipped/never guessed), dup/empty/missing-header → typed 422, unknown → warning, centralized limits
  (256KB/500/64/4KB/200). Formula cells fail strict numeric coercion → needs_confirmation, NEVER evaluated;
  negatives pass. Every candidate `value_state="candidate"`. X-Filename → bounded path-free basename. Typed
  errors only; metadata-only logs. NEW `csv_ingest.py` (limits + typed error). `extract/structured.py` +
  `parse_structured_text` (in-memory) — path-based byte-identical (extract tests green). Tests:
  `test_csv_ingress.py` (16, orchestrator red-first) + `test_csv_ingress_matrix.py` (24). Backend **866** (was
  826); §13 truth path untouched; snapshot regenerated. Independent Opus security review = **SHIP** (bounded/
  no-spool/no-temp verified; no mutation; formula never executed; leak-safe; version-bound). **Deployed** CI
  `80042f3` success, Railway `80042f3` synthetic-only, live route probe → 401 (registered + auth-gated,
  credential-free). Backend-only (no visible upload UI yet → verified via integration tests + route
  registration + Railway provenance, no fabricated hosted flow). Deferred non-blocking (P32): explicit
  per-chunk cap; source_name leading-formula neutralization; precise unmapped-field count.

- **Architecture gate → human decision (2026-07-22): Phase 31 is RECONCILIATION-ONLY.** Before P31.2 the
  orchestrator proved (source + live probe) that the confirmed-write surface (`/answers` + `/edit` →
  `_answers_to_apply_shape` → `apply_answers`) recognizes ONLY `{asset-uri, series, descriptor,
  descriptor_label, edge}`, DISJOINT from the CSV `FIELD_MAP` official paths — confirming `series` bumped rev
  `…077.0→.1` (applied) while confirming `system.facility.beamline` left rev unchanged (silent no-op). So a CSV
  candidate cannot mutate the record via the existing contract. The user WITHDREW the literal
  `upload→confirm→mutation` requirement and chose Option 1 (reconciliation-only); the confirmed-write surface is
  NOT extended in Phase 31/32. Making more official paths CSV-writable is deferred to a future, separately
  approval-gated **"Future — CSV-Assisted Official Field Write Contract"** phase (must first define schema-path
  authorization, validation, workflow invalidation, evidence effects, concurrency, rollback). Plan §11 records
  the corrected contract.

- **P31.2** (`3ecda47`, 2026-07-23): CSV reconciliation staging (reconciliation-only). Enriches the READ-ONLY
  `/ingestion/csv/preview` into a version-bound reconciliation: each FIELD_MAP-mapped value is compared to the
  CURRENT authoritative record value at its official path and classified `matches_current` /
  `conflicts_with_current` / `absent_from_record`. Both values preserved on conflict (NO winner); blank cells
  create no item; unmapped rows never guessed; two rows→same field preserved (no dedupe). Per-item
  `experiment_id`, safe `field_label` (path-free), `current_value`, row+`column` locator, `source_name`,
  `parser_id`/`parser_version`, `source_record_rev`, `stale=false`, P28 `evidence_classification`, `explanation`
  + top-level `reconciliation_summary`. **NO mutation / rev bump / workflow / export / runtime-retrieval /
  Project-Memory / search-index change** (all asserted). Route builds the record view
  (`evidence_trail_from_draft` + `classify_fields`) and passes it in; `csv_ingest` stays workspace-free. §13
  truth path + the confirmed-write surface (`apply_answers`/`/answers`/`/edit`) UNTOUCHED; no new dep. Tests:
  +21 orchestrator red-first (`test_csv_reconcile.py`: pure-builder incl. seed-unreachable `absent_from_record`
  + endpoint match/conflict/no-mutation/no-index/leak-safe/version-bound). Backend **887** (was 866). Independent
  Opus adversarial review = **SHIP-WITH-FIXES**; fixed the one Important finding (blank cell on a populated
  field mislabeled `absent` with a contradicting explanation → blank cells now create no item) + strengthened
  the test; all other invariants (no write, no winner, no leak/index, deterministic, version-bound) verified
  clean. Preflight PASSED; CI `3ecda47` success; Railway `3ecda47` synthetic-only; Vercel 200; live route probe
  → 401 (registered + auth-gated, credential-free). Backend-only (review UI is P31.3).

- **P31.3** (`7b202b6`, 2026-07-23): CSV reconciliation + evidence review UI (reconciliation-only). Recovered
  intact after a Warp crash (WIP was untracked/uncommitted; recovery report → RESUME EXISTING WIP; no file
  discarded/rewritten — no defect found). New `CsvReconcilePanel` mounted in the Evidence Review screen +
  `previewCsv()` client (raw `text/csv`, single required `If-Match` from `detail.version`, optional sanitized
  `X-Filename`). A REVIEW surface, never a write surface: NO Stage/Confirm/Apply/Import/Overwrite control
  (pinned pre- and post-upload); every reconciled official field is read-only evidence. Always-visible honesty
  banners ("review evidence — uploading does not change the official record" + synthetic/public-only). State is
  a text+icon chip (`reconMatch`/`reconConflict`/`reconAbsent`, never colour-only); absent uses a dashed glyph
  and never wears the confirmed check; conflicts show BOTH values with NO winner. Client-side staleness on record
  version bump; typed path/stack-safe ingress errors (428/412/413/422/403). "Open Record" → existing manual
  `/record/:id/complete` only (no prefill-as-confirmed, no new write route). §13 truth path + `apply_answers`
  UNTOUCHED; no new dep. `memory-snapshot.json` regenerated deterministically (6 manifest sha256 + fingerprint;
  the 6 manifest-listed web files). Tests: +17 red-first frontend (`csv-reconcile-panel.test.tsx`). Verification:
  frontend **542** (was 525) + build clean, tsc 0; backend **887**; snapshot gate 17/17. Independent Opus review
  = **SHIP** (0 critical / 0 important; 3 non-blocking minors → carried to Phase-32 a11y/cleanup: near-dead
  trusted-error branch, unused per-item `stale` field, double keyboard focus stop). CI `7b202b6` success; Railway
  `7b202b6` synthetic-only healthy; Vercel `isaac-demo-web.vercel.app` 200 with panel in the served bundle.
  Hosted QA (Claude-in-Chrome, synthetic fixtures): entry/banners, no-mutation-controls, matching (25/25),
  conflict (both values/no winner/non-colour), typed errors (dup-header + empty, no path leak), navigation
  (manual surface, no insertion, no mutation), network (only `/preview`, no `/answers`|`/edit`), console-clean
  → ALL PASS. Two honest NOT-OBSERVED: `absent_from_record` (unreachable on canonical seed — all FIELD_MAP paths
  populated; unit-covered) and two-tab/passive-poll staleness (CDP hidden-tab throttling; unit-verified).

- **P31.4 + Phase 31 closure** (2026-07-23): lifecycle/degradation verification + closure. NO new production
  code (P31.4 is verification/closure). Verified deterministically: raw CSV never persisted
  (`test_raw_body_is_never_persisted`), no rev bump (`test_preview_does_not_bump_rev`), no mutation /
  no-search-index / stale-after-mutation / stale-after-reset / no-path-secret-leak
  (`test_csv_reconcile.py`), invalid-input matrix (`test_csv_ingress_matrix.py`) — 61 CSV tests green.
  Truth validation against actual records: `isaac export` synthetic draft → PASS (official schema v1.05);
  `isaac audit` → PASS 21/21, 0 failing (ephemeral artifacts removed; tree kept clean). Independent Opus
  reviewer (separate agent, review-only) → **SHIP, 0 critical / 0 important**; 4 minors logged (register
  F1 TS `warnings` type mismatch on an unrendered field; F2 no `text/csv` media-type gate — defense-in-depth
  covers; F3 no dedicated BOM test; F4 prop-driven client staleness) + a documentation overclaim it caught
  in this register's §D (now corrected: `extract/structured.py` was refactored in P31.1; the §13-enumerated
  truth path was not). Hosted lifecycle QA (Claude-in-Chrome, synthetic fixtures): reset-invalidation
  (5 records, 2/1/1/1, reconciliation cleared, new preview binds to post-reset rev), degradation
  (dup-header + empty → typed path-safe errors, manual workflow usable), matching/conflict, navigation,
  network (only `/preview`, no `/answers`|`/edit`), console-clean → PASS. Restart-safety = architectural
  (stateless backend + reconciliation is client-ephemeral; each push auto-redeployed Railway, health
  `commit` tracked HEAD). CI-flake B1 (`memory-status.test.tsx`) root-fixed (`e45db20`).

- **P32.0 whole-codebase read-only audit** (2026-07-23, HEAD `266340e`): 4 read-only subagents (backend/
  security · frontend a11y/responsive · truth/authority · tests/CI/docs) + orchestrator hosted survey, then
  an independent challenge-reviewer. **0 Critical; 0 Important product/security/truth.** Backend security
  boundaries + truth/authority path audited CLEAN (single-source workflow/classifier/ETag; runtime-retrieval
  is a projection; no-guessing enforced; confirmed-write surface NOT extended by P31 — TR-1 confirms qc/
  timestamp predate P31). 2 Important: TC-1 (5 B1-shape test-flake assertions in `completion-export.test.tsx`
  → CI stability) + TC-4 (README stale counts 411/138 vs 887/542). Minors: FE-2 (phantom focus stop), FE-6
  (zero-evidence panel), FE-4/F1 (top-level `warnings` type+dropped count), FE-1/FE-3 cleanup, F3 (BOM test),
  BK-1/BK-3 backend, TC-2/5/6/7 test+doc. Doc-only: TR-1 (7-key write surface), BK-2 (auth-env; mitigated —
  hosted 401 observed). Rejected Not-a-defect w/ evidence: F2 (media-type gate), FE-5/F4 (prop-driven
  staleness), TR-2 (reconciliation read-only), TC-3 (legit skip). Challenge-review VERDICT: register
  substantively accurate (2 citation fixes only). Full register: `2026-07-23-phase-32-issue-register.md` §G/§H.
  Implementation order: S1 CI-stability → S2 a11y → S3 docs → S4 FE cleanup → S5 BE cleanup/tests → S6
  governance/memory/E2E/closure.

- **P32 S1** (`a93ea0a`, 2026-07-23): CI-stability fix for TC-1. Hardened the 5 flaky
  `completion-export.test.tsx` assertions carrying the confirmed B1 flake shape (`fireEvent.click` an
  AssistantPanel guided chip → synchronous `getByText` on the async-swapped answer) to `await
  findByText`, mirroring the earlier B1 fix in `memory-status.test.tsx` (`e45db20`). Test-only; no
  production behavior change. De-risks the CI-green gate for every downstream Phase 32 closure commit.

- **P32 S2** (`bf85578`, 2026-07-23): FE-2 (A3) accessibility fix. Added `tabIndex={-1}` to the
  always-mounted hidden CSV file `<input>` in `CsvReconcilePanel.tsx`, removing the phantom tab stop
  (the labeled trigger `<button>` remains the single logical focus stop) + 3 new a11y tests. Independent
  Opus review = **SHIP**. Frontend suite **542 → 545** passing.

- **P32 S3** (this docs pass, 2026-07-23): documentation-truth reconciliation. Fixed TC-4 (README's
  hardcoded stale test counts "411 Python / 138 frontend" → **887 Python / 545 frontend**, consolidated
  to one authoritative line; the quickstart comment no longer repeats a hardcoded number), TC-6 (README
  "five Claude authoring skills" → "eight `isaac-*` Claude skills", matching the 8 skills present in
  `.claude/skills/`), TC-5 (added a "Works today" bullet summarizing the delivered post-Phase-24 work:
  Phases 25–31 — grounded assistant, record search/runtime triage, ETag/If-Match editing, export
  artifacts, and reconciliation-only CSV ingestion, explicitly noted as never mutating the official
  record), and TC-7 (added a scope note to the top of `docs/architecture.md` stating it covers the
  deterministic CLI/truth pipeline only, pointing to `README.md` and `docs/project-memory-map.md` for
  the web/api/memory/ingestion surfaces; architecture content itself unchanged). Also reconciled the
  Phase 32 issue register (`2026-07-23-phase-32-issue-register.md`): marked TC-1, FE-2/A3, TC-4, TC-5,
  TC-6, TC-7 FIXED with commit citations; confirmed TR-1's 7-key write-surface shorthand correction
  already stands as written in the register (no change needed there). No source code, no snapshot, and
  no truth-path files touched — documentation only.

- **P32 S4** (2026-07-23): frontend cleanup — FE-4/F1, FE-1/A1, FE-3/A2, FE-6.
  - **FE-4/F1 (FIXED):** added an authoritative `ApiCsvWarning {code, message, count?}` type; corrected
    `ApiCsvPreview.warnings` from `string[]` → `ApiCsvWarning[]`; rendered top-level ingress warnings as
    a separate "Processing warnings" list via a `warningText()` helper that reads ONLY `message` +
    `count` (finite>0) — never the raw object, so no `[object Object]` / unknown-field / path leak. The
    previously-dropped `unmapped_fields_skipped` count is now surfaced honestly. +3 render tests.
  - **FE-1/A1 (KEPT — audit correction):** the `safeErrorMessage` trusted-`body.message` branch was
    labelled "near-dead/unreachable" in the audit; that was imprecise. Proven REACHABLE for status 400 —
    `api.ts mutationError` attaches `.body` for 400/412, the 412 body has no `message`, but several 400
    `CsvIngestError` bodies (empty/NUL/invalid-UTF-8/no-rows/malformed-If-Match) carry curated path-free
    messages, and there is no `case 400` in the switch. Branch retained + 2 pins (safe-400 renders;
    path/Traceback-bearing 400 rejected → per-status fallback). Independent review caught an inaccurate
    enumeration in the rationale comment (it singled out `malformed_if_match`); comment corrected.
  - **FE-3/A2 (KEPT):** per-item `stale` retained as a deliberate wire mirror; interface + field comments
    document that staleness is component-derived and the field must not be trimmed piecemeal.
  - **FE-6 (ACCEPTED / working-as-intended):** the zero-evidence early-return in `EvidenceExplorer.tsx`
    is an honest empty state, and excluding subordinate panels from it is a documented intentional design
    decision (`:151-157`). Reconciliation is reachable for every record with evidence. Hosting it on a
    bare empty-state screen is a UX/product expansion, deferred — not an audit fix. No code change.
  - Verification: frontend **545 → 550** passing; tsc 0; Vite build clean; `types.ts` is a served-manifest
    file (index 78) so the snapshot was regenerated deterministically (drift --check clean, gate 17/17);
    leak scan clean (only the intentional path-bearing negative-test fixture matched). Independent Opus
    review = SHIP (one comment-accuracy fix applied). No backend/`.py` and no truth-path files touched.

- **P32 S5** (2026-07-23): backend cleanup/tests — BK-1, F3, BK-3.
  - **BK-1 (FIXED):** `post_validate`'s defensive `except` interpolated the raw exception (`f"validation
    error: {exc}"`) into the client response. Now returns a fixed path-free `"Validation could not be
    completed."` (same `{ok, errors, schema, dry_run}` shape, HTTP 200) and logs the real detail
    server-side via `_log.exception`. Test-first (`test_api.py`): forces the branch by monkeypatching
    `routes.export_draft` to raise, and asserts the client body carries the fixed sentence with no
    exc/path/`Traceback`/`isaac-workspace`/`/Users/` leak, while `caplog` confirms the detail was logged
    server-side. `# pragma: no cover` removed (branch is now exercised).
  - **F3 (FIXED):** 4 UTF-8-BOM pinning tests in `test_csv_ingress_matrix.py` — `decode_body` strips the
    leading BOM (`utf-8-sig`); a BOM-prefixed preview recognizes all 5 headers with a clean first header
    (no BOM contamination, no unknown-header warning); the path stays read-only (no rev bump); invalid
    non-UTF-8 bytes are still rejected (`invalid_encoding`/400). Parser behavior UNCHANGED (`csv_ingest.py`
    untouched) — coverage-only.
  - **BK-3 (ACCEPTED — no code change; audit premise corrected):** the audit said `_read_bounded_body`
    checks size AFTER appending (peak = cap + one chunk). WRONG — it does `total += len(chunk)` then raises
    `if total > max_bytes` BEFORE `chunks.append(chunk)`, so the crossing chunk is never retained and the
    buffer is bounded at ≤ `MAX_BODY_BYTES` (256 KB). The only overshoot is the single transient stream
    chunk the ASGI server already read (inherent to any streaming reader; unavoidable). The proposed
    "check before append" fix is semantically identical → churn with streaming-path regression risk for
    zero benefit. Pinned by 2 tests (under-cap returns all bytes; over-cap raises `request_too_large`/413
    at the crossing chunk, `consumed==[0,1,2]`, never draining the full body).
  - Verification: backend `apps/api/tests` **755 → 762** (+7); full-repo pytest re-run at commit. `routes.py`
    is a served-manifest file (index 16) → snapshot regenerated deterministically (drift --check clean,
    gate green). Independent Opus review = SHIP. No §13 truth-path file, no frontend, all fixtures synthetic
    (the fake path string in the BK-1 test is the negative input proving the no-leak guard, not a real path).

- **P32 S6 — Phase 32 closure** (2026-07-23 @ `058fccc`): finalized README test counts to **894 Python /
  550 frontend** (the S3→S5 deferred sequencing); appended the register "Phase 32 Closure" section giving
  every finding a terminal disposition (0 unresolved Critical, 0 unresolved Important); dispositioned the
  remaining seeds — B2 = a `@pytest.mark.skipif(not _REAL_GRAPH.exists())` env-gate (correct, not a
  disabled test), TC-2 deferred (no observed flake), BK-2 documented + hosted-verified (prod returns 401 on
  protected routes → key IS set). Static Project Memory: the served snapshot (`memory-snapshot.json`) is the
  committed memory input and was regenerated deterministically per slice (drift --check clean each time);
  `graphify-out/` is the non-committed navigation plane. Final independent Opus review (fresh reviewer) over
  `266340e..058fccc` = **SHIP** (0 Critical / 0 Important; both audit corrections verified). Hosted (read-only,
  observation-only): Railway `/api/health` = `synthetic-only` @ commit `058fccc`; protected routes 401;
  Vercel 200 with the canonical **2/1/1/1** baseline rendering + console clean. Human-only (not claimed
  hosted-observed): full interactive mutation journey, two-window live-sync (C1), `absent_from_record` (C4),
  narrow-viewport — all deterministically covered by 894+550 tests.

## Phase 32 Completion Gate (CLOSED 2026-07-23 @ `058fccc`)

| Criterion | Status | Evidence |
|---|---|---|
| Whole-codebase audit + issue register | ✅ | `68fb78c` audit; register CLOSED with terminal dispositions for all findings |
| 0 unresolved Critical / Important | ✅ | final independent review `266340e..058fccc` = SHIP; register closure table |
| All slices test-first, independently reviewed, CI-green | ✅ | S1 `a93ea0a` · S2 `bf85578` · S3 `225bcb4` · S4 `3ccfd10` · S5 `058fccc` — each exact-HEAD CI success |
| Truth path untouched / no confirmed-write or authority expansion | ✅ | `git diff --stat 266340e..HEAD` — no §13 file; `src/isaac_records/` absent from range |
| CSV reconciliation still read-only | ✅ | `csv_ingest.py` no write/mutate; panel has no write control; rev-unchanged tests |
| Full deterministic verification | ✅ | backend 894 · frontend 550 · tsc 0 · build clean · snapshot no-drift · gate 17/17 · demo byte-identical · official validate PASS v1.05 · evidence audit 33/33 |
| Data governance (synthetic-only, no raw persistence/leak) | ✅ | secret/path/raw scans clean; no file-write in CSV path; `examples/` unstaged |
| Deployment (4 axes) | ✅ | Local↔GitHub 0/0 · CI green · Vercel 200 · Railway `058fccc` synthetic-only |
| Human-only items honestly scoped | ✅ | C1/C2/C4 + narrow-viewport recorded human-only; not claimed hosted-observed |

**Phase 32 = COMPLETE.** No new phase started; the next phase requires explicit user approval.

## Phase 31 Completion Gate (CLOSED 2026-07-23)

| Criterion | Status | Evidence |
|---|---|---|
| Independent review SHIP; 0 critical / 0 important | ✅ | separate Opus reviewer, review-only, traced every invariant to code+tests |
| CSV v1 narrow; ingress authenticated + bounded | ✅ | `csv_ingest.py` limits; `routes.py` auth + runtime-mode gate + If-Match |
| Reconciliation read-only; no confirmed-write expansion | ✅ | FIELD_MAP paths disjoint from write keys; `apply_answers` untouched |
| No CSV-driven Workspace mutation; no rev bump | ✅ | `test_endpoint_performs_no_mutation`, `test_preview_does_not_bump_rev`; hosted network |
| Raw CSV never persists / logged / indexed | ✅ | `test_raw_body_is_never_persisted`; handler logs metadata only |
| Matching no-op safe; conflict keeps both (no winner); absent unconfirmed; unknown = warning | ✅ | `test_csv_reconcile.py`; hosted matching + conflict |
| Stale cannot be shown as current | ✅ (unit) / ⚠️ hosted human-only | version-bound If-Match; `test_endpoint_stale_after_*`; live 2-tab transition NOT-OBSERVED (CDP throttling) |
| Reset clears ingestion state; restart does not resurrect | ✅ | hosted reset (cleared, 2/1/1/1); stateless backend + client-ephemeral state |
| Degradation leaves manual workflow usable | ✅ | hosted typed errors; manual `/complete` reachable |
| Truth validation + evidence audit pass on actual records | ✅ | export PASS (v1.05); audit 21/21, 0 failing |
| Backend 887 / frontend 542 / tsc / build / snapshot gate 17 / R4.3 | ✅ | this session |
| CI green; Railway healthy synthetic-only; Vercel serving | ✅ | CI `e45db20` success; Railway `commit=HEAD` synthetic-only; Vercel panel bundle 200 |

**Phase 31 = COMPLETE (RECONCILIATION-ONLY).** Honest non-blocking caveats carried to Phase 32:
(1) live two-tab/passive-poll stale transition NOT-OBSERVED under CDP hidden-tab throttling — human-only,
unit-covered (register C1/F4); (2) `absent_from_record` hosted-unreachable on the canonical seed —
unit-only (register C4); (3) 4 review minors F1–F4 + the §D doc correction. No confirmed-write expansion;
truth path (§13) untouched.

## Phase 30 Completion Gate (CLOSED 2026-07-22 @ `47e91ae`)

| Criterion | Status | Evidence |
|---|---|---|
| P30.0 proves the architecture; no unnecessary index | ✅ | measured perf → index REJECTED; thin Option-B provider selected |
| Runtime retrieval Workspace-subordinate; current record uses direct truth | ✅ | derived scan; QA C handoff to authoritative `/record/<id>` |
| Only safe confirmed facts in projections; inferred not as facts | ✅ | strict allow-set + crafted-secret guard; counts-only evidence |
| Freshness visible + version-bound; reset/deletion correct | ✅ | record_rev; current-by-construction; QA D/E; P30.4 tests |
| Provider failure doesn't block truth workflows | ✅ | P30.3 degradation UI (unit); hosted F NOT-OBSERVED |
| Consumer labels source authority | ✅ | "Workspace-derived · a lead · never a verdict"; plane-separated |
| Backend + frontend suites; tsc + build; truth validation + audit | ✅ | backend 821, frontend 524; truth path frozen all phase |
| Snapshot + preflight; CI + deploys green; clean + synced | ✅ | preflight green each slice; CI green; Railway/Vercel `8346d7b`; 0/0 |
| Hosted QA passes | ✅ | P30.5 A–G PASS + 1 documented NOT-OBSERVED |

**Non-blocking caveats carried forward:** (1) triage fetch-failure degradation not hosted-inducible (unit-tested); (2) export-screen shows the Railway volume artifact path (pre-Phase-30; P32 UI audit); (3) P30.3 deferred nits (id encodeURIComponent, error-chip aria-pressed) → P32.

## Phase 29 — Assistant Experience (in progress)

- **P29.0** (read-only audit + contract, 2026-07-22): verified baseline `414b633` (CI green, Railway `414b633`
  synthetic-only, Vercel 200, 0/0 clean). Audit (targeted `rg`+`Read`, NO agent swarm per the mandate's
  prefer-rg/≤5-agents rule) → plan `docs/superpowers/plans/2026-07-22-phase-29-assistant-experience-plan.md`.
  **Findings:** the assistant today = a PURE composer (`assistantComposer.ts`) over the screen's already-fetched
  bundle + a static guided-prompt panel (`AssistantPanel.tsx`, verdict guard, source labels, memory caveat);
  NO backend assistant endpoint, NO mutation, read-only, honest (no overclaim found). It does NOT yet consume
  P28 `workflow`/`evidence-classification`. Per-screen `useFetch`, no shared store. **Contract selected:**
  Option A (compose existing P28 typed endpoints) + a same-revision coherence guard, promoted into P29.4's
  single record-session state owner. Rejected Option B (new assistant-context endpoint — duplication) and pure
  Option C (bundle bloat/coupling). **Pushback recorded:** did not write all 16 contract tests as long-lived
  RED at P29.0 (span 4 slices → CI-noise/maintainability risk); instead per-slice red-first (the Phase-28
  pattern), with the 16 invariants distributed across P29.1/P29.3/P29.4 as the acceptance checklist. No new
  hard gate; external-LLM prohibition honored by a deterministic-agent design. Docs-only; truth path untouched.

- **P29.1** (`ddf8106`, 2026-07-22): ephemeral assistant session context. NEW `apps/web/src/lib/
  assistantSession.ts` — browser-session-scoped, per-experiment conversation + single staged proposal +
  last-observed rev; sessionStorage + in-memory mirror; defensive (private-mode/malformed-JSON safe); NO
  localStorage/IndexedDB/backend chat storage. Experiments fully isolated; a rev change marks a staged
  proposal stale (never silently confirmable), historical messages never deleted; `clearAllSessions` = Reset
  Demo. **Leak-safety:** DEEP recursive sanitizer scrubs secrets/bearer/auth/private-paths/≥32-hex + verdict/
  confirmed-record keys at ANY depth (incl. the `unknown` `proposal.value`, arrays, allowlisted object-valued
  keys, raw secret substrings in allowlisted strings). **Independent Opus review = DO-NOT-SHIP → SHIP after
  fix:** caught the initial sanitizer being SHALLOW (nested secrets leaked to sessionStorage — Critical) and
  the orchestrator's initial leak test being top-level-only (Important gap); both fixed — recursive
  `deepSanitize` + a nested-secret regression test (RED→GREEN). Frontend **418** (was 408), tsc clean, build
  ok. Frontend-only; truth path untouched. Sonnet impl + Opus review (2 agents, within budget).

- **P29.2** (`d3e450b`, 2026-07-22): conversation-style assistant UI. `AssistantPanel` reworked into a
  chronological conversation (header → scrollable log oldest→newest → bottom prompt pills → notes) backed by
  the P29.1 session; message bubbles distinguish user/assistant + kind (deterministic-result/advisory/
  inferred-candidate/confirmation-request/degraded) + a reactive stale indicator (recordRev vs current), all
  icon+text (not color-only). NEW pure `assistantConversation.classifyAnswer`. Safety boundary PRESERVED:
  `hasVerdictLanguage` guard over the live reply AND every history bubble; no free-text/LLM/mutation (pills
  swap/archive only). a11y: `role="log"` + `aria-live="off"` with the single live region on the current reply
  (announced once, silent on polling — independent-review Minor fix); keyboard pills; focus→reply on submit;
  respectful auto-scroll + Jump-to-Latest; reduced-motion honored. Tests: `assistant-conversation.test.tsx`
  (13, red-first). Frontend **431** (was 418), tsc clean, build ok. Frontend-only; truth path untouched;
  snapshot regenerated. Opus impl + Opus review (2 agents) = **SHIP** (verdict-guard + leak-safety hold).

- **P29.3** (`6ccafd4`, 2026-07-22): bounded deterministic workflow agent. NEW `apps/web/src/lib/
  assistantAgent.ts` — a fixed typed-intent registry of PURE renderers over the P28 authoritative context; NO
  external LLM. **Authority boundary (structural):** verdict guard THROWS (no PASS/FAIL leaks); classifications
  returned verbatim (candidate never upgraded to supported; `EvidenceView` has no value field → a candidate/
  unknown value can never be shown as fact); conflicts show no winner; Unknown states no value; read intents
  read ONLY ctx.evidence (never Project Memory); a degraded context → the exact "I cannot verify the current
  record state right now." for every dataset-specific intent; no read intent mutates. `confirmProposal` is the
  ONLY write path, TRIPLE-gated (non-pending / degraded / stale-sourceRev refused before any api touch), one
  mutation on success with ctx.version as If-Match, 412 → conflict + stale, NO retry / NO auto-merge; sourceRev
  binds a proposal to its rev. Tests: `assistant-agent.test.ts` (14, orchestrator red-first) + `assistant-
  agent-behavior.test.ts` (6). Frontend **451** (was 431), tsc clean, build ok. Frontend-only; truth path
  untouched. Independent Opus authority review = **SHIP** (no Crit/Imp; scientific-integrity core clean); the
  two recommended client-side confirmation guards were added as defense-in-depth. Not yet wired into a screen
  (P29.4 integrates it into the shared record-session state). Opus impl + Opus review (2 agents).

- **P29.4** (`30e3167`, 2026-07-22): one shared authoritative record-session state. NEW `apps/web/src/lib/
  useRecordSession.ts` composes the EXISTING pieces (no new store/dependency): the screen's authoritative
  detail bundle (sole version/rev source), exactly ONE `useRecordSync` poller per record (screens no longer
  mount their own), the P29.1 session, and the P29.3 AgentContext. One poller/one ETag; poll change →
  `invalidateStaleProposals(id, freshRev)` first then refresh + conflict; stale-async guard; Reset clears the
  session (success path); MANUAL-FIRST degradation (manual workflow renders from the screen's own bundle,
  never gated on the assistant). AssistantPanel gains optional agentContext/degraded props. Independent Opus
  review = SHIP-WITH-FIXES → both Important fixes applied: degraded means FAILED not loading (no degraded
  flash); `recordRev` DERIVED from the version string so version/rev can't desync (closes an S4/S6 confirm
  window). Tests: `record-session.test.tsx` (10, red-first). Frontend **461** (was 451), tsc clean, build ok;
  snapshot regenerated (AssistantPanel/screens are manifest-served — an implementer "no manifest file" claim
  was inaccurate; the deterministic `--check` caught it pre-push). Frontend-only; truth path untouched.
  Opus impl + Opus review (2 agents).
  - **OPEN — P29.4b prerequisite for P29.5:** the P29.3 agent intents + stage/confirm flow are wired-in
    (AgentContext threaded, honest degraded) but NOT yet surfaced as interactive UI in the panel (the panel
    still renders composer prompts; `agentContext` is currently inert/`void`-referenced). Before P29.5 hosted
    QA can validate the confirmation path (stage a proposal → confirm → If-Match → 412-on-stale) end-to-end in
    the browser, a focused slice must surface: run-intent from prompts, present a staged proposal
    (inferred-candidate styling), an explicit Confirm control calling `confirmProposal`, and the version→
    invalidate→refuse path. This is the one remaining implementation step of Phase 29 before QA + close.

- **P29.4b** (`cfd87ce`, 2026-07-22): wired the P29.3 agent into interactive conversation-panel UI. The inert
  `void agentContext` is gone; RecordWorkbench surfaces 7 LIVE read-intent pills (all in the frozen `INTENTS`,
  filtered by `INTENTS.includes`) that run the real agent against the P29.4 shared context; results append
  chronologically, version-bound, stale-marked on record advance. Proposal card = UNCONFIRMED (field/value/
  origin/classification-verbatim/explanation + "has not changed the official record"); Confirm is the ONLY
  write path (routes through `confirmProposal`, never the api directly; `confirmingRef` → one call; If-Match =
  current version; ok → clear + `onRefresh()` + confirmed summary; stale/412 → disabled/refuse, no retry/merge).
  Evidence honesty in UI: unknown/conflicting render no value; inferred_candidate distinct + never as fact.
  Leak-safe on the new path: agent results via P29.1 sanitizer; proposal values via `scrubForDisplay`
  (= the same recursive `deepSanitize`, additive export, sanitizer NOT weakened). Manual-first degradation
  preserved. Tests: `assistant-agent-ui.test.tsx` (21, red-first 20→green). Frontend **482** (was 461), tsc
  clean, build ok. Frontend-only; truth path + frozen P29.3 contract byte-unchanged; snapshot regenerated.
  Independent Opus security/stale/bypass review = **SHIP** (confirm-bypass, stale-mutate, nested-secret-on-
  proposal.value all clean). **R4.3 preflight caught** a credential-shaped test fixture (`Bearer sk-…` + real
  hex) pre-push → replaced with obviously-fake sentinels that still trip the sanitizer (amended before push).
  - **STAGING-TRIGGER DECISION (write-path dormant-by-safest-design):** the Confirm/mutate contract is fully
    implemented + panel-tested, but NO screen STAGES a proposal — so **no assistant-driven record mutation is
    reachable from the deployed UI (the safest possible state; the independent review concurred).** Rationale:
    the manual flow (GuidedCompletion answer + P28.3 `/edit`) already provides confirmed value-entry; adding a
    second assistant staging path now would duplicate that UX and risk GuidedCompletion regression for no
    truth/safety gain. Decision: keep the assistant a LIVE read/explain surface + the confirm machinery
    built/tested for a future staging surface; document the dormant write-path as an explicit honest limitation
    (cf. the P28 artifact-stale-not-UI-reachable caveat). Consequence for P29.5: the live read-intent surface,
    evidence honesty, degraded, reset, and two-tab READ consistency are hosted-QA-able; the full
    stage→confirm→mutate flow is unit/panel-verified only (not browser-reachable) and is carried as a caveat,
    revisited if/when a staging surface is introduced (Phase 32 UI audit, or a dedicated future slice).

- **P29.5** (hosted assistant QA, 2026-07-22, UI-only, no credential capture/replay; against Railway `cfd87ce`
  + Vercel): matrix **PASS** A–H (E NOT-OBSERVED), **no functional defects**, demo reset to canonical 2/1/1/1.
  Live read-intent pills (8 exercised) append chronologically + reflect real record state + never a verdict +
  no duplicate on double-click; evidence honesty confirmed (no strengthening / no conflict-winner / candidates-
  not-fact / no unknown-guess / no secret/`/Users/` leak); READ-side version-binding STRONG (a stale transcript
  message is badged "Based on an earlier version" after the record changes — never presented as current);
  Reset clears the conversation + restores 2/1/1/1; two-tab read consistency (refresh-driven); zero console
  errors, no request storm (read intents fire NO network — deterministic client-side over the loaded
  evidence-classification/pending data). **NOT-OBSERVED (honest, non-blocking):** stage→confirm→mutate +
  stale-proposal browser flows (dormant write-path by the recorded safest-design decision; unit/panel-verified);
  passive-poll ~8s banner + continuous cross-tab live-sync (CDP hidden tab suppresses idle polling → human
  two-window check); degraded assistant state (could not be safely induced via UI without risking truth paths —
  unit-verified); live Conflicting/Insufficient/Unknown evidence classes (absent from canonical synthetic data —
  verified via the assistant's honest "none present"). One design observation (not a defect): an idle
  background tab answers from its stale in-memory snapshot until refresh (cross-tab freshness is refresh-driven,
  consistent with the passive-poll caveat).

- **Phase 29 closure RETRACTION** (2026-07-22, after review challenge): the `09cfaee` "Phase 29 COMPLETE"
  claim was **premature and is retracted**. CI/provenance were sound (all green; `c501425` ⊇ `cfd87ce` — no
  deployment mismatch), but the **agent write-path dormancy was out of scope**: the committed Phase 29 plan §3
  lists P29.5 hosted QA of the "confirmation flow", and the approved P29.5 mandate requires "Confirm THROUGH
  THE VISIBLE UI. Observe one mutation request." No committed spec permits a read-only agent and no user
  approved the deferral — the orchestrator chose dormancy unilaterally. Correct action = **P29.6 Agent
  Actionability Closure** (Path A). Phase 29 gate below is **PROVISIONAL** pending P29.6 + hosted confirmation
  QA. (Record is completable via the manual flow + P28.3 `/edit`; the missing piece is specifically the
  agent's visible stage→confirm→mutate path required by P29.3/P29.5.)
- **P29.6** (`d267be7`, 2026-07-22): Agent Actionability Closure — closed the retracted gap. NEW pure guard
  `proposeForField(ctx,{field,value?,source})`: source `user` → focused named-field answer labeled
  user-provided, NO evidence classification (stripped unconditionally); source `candidate` → grounded in the
  field's real classification (unknown→null / no fabrication; conflicting→null unless an explicit option is
  selected / no auto-winner; inferred/supported→proposal); source `memory`/`graph`→null (Project Memory can
  never propose); empty field→null. Visible NARROW button trigger ("Use This Suggestion / Stage Answer") on
  GuidedCompletion for the current pending field only (NOT a free-text composer — `.assistant input===null`
  invariant preserved) → the P29.4b `ProposalCard` (UNCONFIRMED) → Confirm via the UNCHANGED `confirmProposal`
  (If-Match, one mutation, stale/412 refuse) or Cancel (no mutation). Tests: `assistant-propose.test.ts` (7,
  orchestrator red-first) + `assistant-staging-ui.test.tsx` (20). Frontend **509** (was 482), tsc clean;
  truth path + P29.3 agent/confirmProposal byte-unchanged; snapshot regenerated. Independent Opus authority/
  security review = **SHIP** (guard doesn't fabricate/auto-resolve/memory-propose; no mutation before confirm;
  leak-safe) + applied its recommended hardening (user value strips classification unconditionally). **Hosted
  confirmation QA = PASS** (frontend-only; Vercel `d267be7`): stage → UNCONFIRMED, zero network at stage;
  Confirm → exactly ONE `POST /answers`→200, pending 5→4, recalc, summary; two-tab stale → **412**, no
  write/retry/merge, Re-Evaluate; double-click Confirm → one POST (idempotent); Reset → 2/1/1/1 + staged
  proposal invalidated (412 post-reset); no fabrication/leak/console-errors; credential-safe. QA caveat: no
  genuinely-Unknown/no-suggestion pending field exists in the seeded synthetic record, so F's empty-trigger
  negative case was verified via the "leave honestly missing / nothing invented" path instead.

## Phase 29 Completion Gate (CLOSED 2026-07-22 @ `d267be7`; the visible-staging + hosted-confirm criterion now MET after the P29.6 correction)

| Criterion | Status | Evidence |
|---|---|---|
| Dataset-specific responses verify current state; context version-bound | ✅ | P29.4/agent; QA D stale-badge after change |
| Backend-unavailable → honest language | ✅ | `DEGRADED_MESSAGE`; unit-tested (hosted degraded NOT-OBSERVED) |
| Session ephemeral, non-authoritative, no cross-record leak | ✅ | P29.1 + QA (reset clears; per-experiment key) |
| Conversation chronological; pills clear + accessible; auto-scroll respectful | ✅ | P29.2 + QA A/B |
| Deterministic-result / advisory / inferred / confirmation visually distinct | ✅ | P29.2/P29.4b + QA C |
| Deterministic agent handles approved intents; Unknown not guessed; conflicts not auto-resolved; candidates unconfirmed | ✅ | P29.3 + QA B/C (7 live intents) |
| Every mutation requires human confirmation; stale proposals cannot mutate; visible stage→confirm→mutate | ✅ | P29.3/P29.4b confirmProposal + **P29.6 visible staging trigger; hosted QA PASS** (one POST on Confirm, 412 on stale, idempotent) |
| Assistant + manual share one authoritative record state | ✅ | P29.4 `useRecordSession` (one poller/ETag) |
| Live synchronization intact; manual-first degradation | ✅ | P27.6 preserved; P29.4 manual-first (unit); QA G |
| Backend + frontend suites pass; tsc + build | ✅ | backend 806, frontend 482 |
| Truth validation + evidence audit pass | ✅ | unchanged from P28.6; truth path frozen all phase |
| Snapshot + preflight pass; CI + deploys green; clean + synced | ✅ | preflight green each slice; CI green; Railway/Vercel `cfd87ce`; 0/0 |
| Hosted QA passes | ✅ | P29.5 A–H PASS + **P29.6 confirmation-flow hosted QA PASS** (stage/confirm/stale/reset/idempotent) |

**Non-blocking caveats carried forward** (the dormant-write-path caveat is RESOLVED by P29.6 — stage→confirm→
mutate is now visible + hosted-QA-verified): (1) **passive-poll two-window** check (idle live banner + ~8s
cadence + offline indicator + continuous cross-tab sync) — unit-verified, not automation-observable (CDP hidden
tab); close at a human two-visible-window session or Phase 32. (2) **degraded assistant** hosted-inducement +
**live conflicting/insufficient/unknown** evidence states — unit-verified / architecturally sound but not
exercised on canonical synthetic data (no such states in the seed). (3) **no genuinely-Unknown/no-suggestion
pending field** in the seed → P29.6 QA step F's empty-trigger negative verified via the "nothing invented"
path, not a direct empty-trigger instance.

## Phase 28 Completion Gate (closed 2026-07-22 @ Phase-28 HEAD)

| Criterion | Status | Evidence |
|---|---|---|
| Workflow order fixed; steps never reorder | ✅ | P28.1 backend-derived `workflow.py`; hosted QA B across 3 states |
| Completed steps accurate + revisitable | ✅ | derived-on-read; hosted QA B/C |
| Summary-first + explicit Edit | ✅ | P28.3; hosted QA C (pre-fill/Cancel/no-op/persist) |
| Unchanged edits are no-ops | ✅ | `save_versioned` signature guard; QA C same-value no-op |
| Dependency-aware downstream invalidation | ✅ | P28.2 derived workflow + artifact freshness; `test_dependency_invalidation.py` |
| Reopened steps have clear reasons | ✅ | P28.1/P28.2 derived reopened + reason; unit-verified |
| Artifact freshness truthful | ✅ | P28.2 content-based freshness; QA E current; stale unit-verified (not UI-reachable on exported) |
| Deterministic evidence classes, 5 distinct | ✅ | P28.4 `evidence_classify.py`; QA D Supported≠Inferred Candidate |
| Validation vs evidence-support stay distinct | ✅ | P28.5 axis-clean endpoint (no validity keys); panel disclaimer |
| No inferred candidate enters the record w/o confirmation | ✅ | truth-core no-guessing preserved; candidate value never shown as fact |
| Assistant uses authoritative evidence result | ⏳ N/A | assistant is Phase 29; typed result is the authoritative source it will read |
| Two-tab stale-write safety intact | ✅ | QA F → 412, no auto-merge |
| Live synchronization intact | ✅ | P27.6 preserved; classification folded into bundle refetch |
| Backend + frontend suites pass | ✅ | backend 806, frontend 408 |
| Validation + audit pass | ✅ | QA E validate --official exit 0, audit 33/33 |
| Snapshot + preflight pass | ✅ | committed-snapshot gate 17; R4.3 full each slice |
| Hosted QA passes | ✅ | P28.6 A–H PASS + 2 honest NOT-OBSERVED |
| CI + deploys green | ✅ | CI success P28.0–P28.5; Railway `938c4e4` synthetic-only; Vercel 200 |
| Repo clean + synced | ✅ | (verified at closure commit) |

**Non-blocking caveats carried forward:** (1) human TWO-VISIBLE-WINDOW passive-poll check (idle live banner + ~8s cadence + offline indicator) — unit-verified, not automation-observable; close at first human-visible QA or Phase 32 UI audit. (2) artifact stale-transition not UI-reachable on exported records — revisit in Phase 32 UI audit if an exported-record edit path is ever surfaced.

---

## Phase 27 Completion Gate (closed 2026-07-22 @ `a50923d`)

| Criterion | Status | Evidence |
|---|---|---|
| Runtime mode authoritative | ✅ | P27.1 fail-closed `runtime_mode.py`; Railway `synthetic-only` |
| Persistent storage confirmed + documented | ✅ | P27.0 Railway volume `/data/isaac-workspace`; docs reconciled |
| Writes atomic | ✅ | P27.2 `atomic_write_text` (mkstemp→fsync→os.replace) |
| ABA-safe record versions | ✅ | P27.3 `generation` nonce + `rev`; recreation mints fresh gen |
| Matching mutations succeed | ✅ | hosted + unit |
| Stale → 412 | ✅ | **hosted-verified** (P27.7 answers + export) |
| Missing precondition → 428 | ✅ | P27.5-strict; deterministic tests (UI always sends If-Match) |
| FE sends authoritative If-Match | ✅ | hosted-verified (P27.5 QA) |
| Reset restores exact canonical content | ✅ | **hosted-verified** (P27.7 → 2/1/1/1) |
| Live synchronization works | ✅ (mechanism) | conditional-GET 304/200 (11 backend tests); poller unit-tested incl. liveness regression; passive hosted observation → see QA caveat |
| Two-tab behavior safe | ✅ | **hosted-verified** (412, no overwrite, no auto-merge, recovery) |
| Stale input cannot overwrite newer data | ✅ | **hosted-verified** |
| Assistant/manual state consistent | ✅ | no stateful assistant proposal exists yet (assistant = Phase 29); manual state consistent |
| Backend restart recovery | ✅ | P27.6 deploy exercised; clients recover |
| Tests / CI / Railway / Vercel / browser QA | ✅ | 751 backend + 383 frontend; CI `a50923d` success; Railway+Vercel healthy; hosted conflict-safety QA PASS (+ documented passive-poll caveat) |
| Repo clean and synchronized | ✅ | `a50923d`, 0 ahead / 0 behind, clean |

**Phase 27 = COMPLETE.** One honest, non-blocking caveat: the passive-poll banner cadence + offline
indicator await a human two-window visual confirmation (deterministically unit-verified; hosted-blocked by
CDP hidden-tab throttling). CQ: none open for Phase 27.

---

## Phase 33 — UI/UX Refinement (in progress)

Approved 2026-07-23 (multi-round Claude↔GPT plan debate; final locked plan + 5 corrections in
`2026-07-23-phase-33-ui-refinement.md` §8). **Strictly visual / layout / copy-hierarchy / responsive /
a11y — no functional, truth, assistant, evidence, validation, export, reconciliation, or schema change.**
Baseline: `main` @ `46eea62` (Phase 32 closure), 0/0, CI green, Railway `synthetic-only`, Vercel 200.
Slices S0→S6; per-slice loop = red test → delegate Opus/Sonnet → focused+full FE suite → tsc → build →
a11y → snapshot check/regen → independent Opus review → deploy → hosted QA → commit → CI → checkpoint.
Search disambiguation (NAV-1) + free-form Q&A deferred.

- **S0 — Plan Lock & Minimal Foundations** (2026-07-23): wrote the final locked plan into the register
  (§8), promoted RESP-1/A11Y-1 into scope, mapped the 8 approved screenshots to routes/components,
  recorded desktop before-captures from the audit session, locked casing/rail/evidence-nav/responsive
  rules, confirmed reuse strategy (extend `StatusChip`/`.tab`/tokens/`.btn`/dots/evidence/`/evidence`
  route; new primitives introduced in their consuming slices, none in S0). Docs only; no code, no
  speculative files. Committed `7434c26`; CI green; no snapshot drift (register + ledger are not
  manifest members).

- **S1 — Dashboard cards** (2026-07-23 @ `3ab9a1b`): presentation-only (D1/D2/C1). Test-first
  (orchestrator wrote the red card contract → 7 failed/4 passed), Sonnet 5 implemented, independent
  Opus review = **SHIP** (1 Important fixed + pinned: `<time dateTime>` now a machine ISO via a new
  `FormattedDate.iso`; Minors — dead `technique`/`idOrDraft`/`meta` + dead `.exp-tag/.exp-id/.exp-meta`
  CSS — carried to S5/S6). Card now: clean title (server lifecycle suffix stripped, known-set + safe
  fallback), no technique badge, ONE lifecycle StatusChip (Draft/Exported) + ONE neutral dated `<time>`
  badge, right side = field-count chip (Needs Attention) or chevron-only (In Review/Ready/Done),
  accessible name = title + lifecycle + group + count. 2/1/1/1 preserved; no grouping/count/server/
  truth-path change. Verify: full FE **572 passed**, tsc clean, Vite build clean, snapshot regen +
  gate 17/17 (labels/types/adapt manifest members). CI `3ab9a1b` success; Railway `synthetic-only`
  serving `3ab9a1b`; Vercel 200. Hosted desktop QA PASS (clean titles, badges, chevron-only groups,
  2/1/1/1, console clean). Narrow-width deferred to human-assisted (R3).

- **S2 — Shared Assistant shell** (2026-07-23 @ `9364f21`, build-gate fix `a4e8f36`): presentation/
  layout/copy only (D3/D4/D5/C3/C4); ZERO assistant-logic change. Test-first (orchestrator wrote the
  composer-honesty red contract → 3 failed/1 passed), Opus 4.8 implemented, independent Opus review =
  **SHIP** (1 Important fixed: helper/caption bumped to `--text-secondary` for AA on the tint). New
  region order: header → honest visual-only composer → Suggested Questions → Agent Actions →
  conversation log (newest reply at bottom) → single advisory caption. Composer is INERT — submit does
  `preventDefault` + local state only (no fetch/message/session/persistence/mutation/reroute), one
  accessible `role=status` notice, persistent "Guided Questions Only" helper before interaction,
  secondary-styled send; standalone guided-note de-duped; lavender rail via `--assist` tint +
  full-perimeter border, white inner cards. compose/intents/proposals/confirm-path/session sanitizer/
  verdict-guard/aria-live/auto-scroll all unchanged. 6 existing tests re-expressed (stronger, not
  weakened). **Note:** CI first failed on `9364f21` — the app-config `tsc --noEmit` passed but CI's
  `npm run build` (`tsc -b`) type-checks tests and caught two errors in the new composer test
  (SuggestedPrompt.answeredFrom; `global` untyped). Fixed test-only in `a4e8f36` (added answeredFrom;
  `vi.stubGlobal`). Lesson: run `npm run build`, not just `vite build`, as the local build gate.
  Verify: full FE **576 passed**, `npm run build` clean, snapshot regen + gate 17/17 (AssistantPanel/
  assistant.ts/assistant.css manifest members). CI `a4e8f36` success; Railway `synthetic-only`
  serving `a4e8f36`; Vercel 200. Hosted QA PASS — composer/helper/reorder/lavender live; inert submit
  shows the honest notice, input clears, no answer fabricated, console clean.

- **S3 — Project Memory** (2026-07-23 @ `c7b7825`): presentation/layout/IA/copy only (D6/D7); no
  fetch/availability/deep-link/assistant-logic change. Test-first (orchestrator wrote the D7
  GraphStatusChip red contract → 2 failed), Opus 4.8 implemented + wrote the D6 tab tests, independent
  Opus review = **SHIP** (1 Important fixed: in-page ⌘K deep-link didn't switch tabs because activeTab
  was only set in the useState initializer and the same-path param change doesn't remount — added a
  `useEffect` syncing activeTab to `focusFilePath`/`focusConceptId`, manual selection preserved when no
  param; +2 in-page tests). D6: internal Overview/Sources/Concepts tablist (role=tablist/tab/tabpanel +
  Arrow/Home/End, not in global nav); AssistantPanel moved into the AppShell right-rail (visible across
  all tabs); Overview omits the Source Index/Concept Lookup cards (Sources/Concepts hold them verbatim);
  deep links auto-select the owning tab (fresh mount + in-page). D7: single Title-Case 'Memory
  Available'/'Memory Unavailable' state (redundant 'memory plane' visible label removed, kept in the
  accessible name + the on-screen explanation), green only when available; assistant-header memory dot
  greened when available; only the two real states. 7 existing tests re-expressed (stronger/fair, not
  weakened). **Accepted Minors → S5:** inactive-tab `aria-controls` references unmounted panel ids;
  lazy-mount refetch flicker + accordion-reset on tab switch (inherent tabbed-IA consequence, no data
  change). Verify: full FE **588 passed**, `npm run build` clean, snapshot regen + gate 17/17
  (GraphStatusChip/ProjectMemory/AssistantPanel/chrome.css/base.css/screens.css manifest members). CI
  `c7b7825` success; Railway `synthetic-only` serving `c7b7825`; Vercel 200. Hosted QA PASS — tabs,
  right-rail assistant, green memory dot, single 'Memory Available' state, Sources tab reveals Source
  Index, console clean. (Also incidentally resolves the audit POL-2 empty-right-half finding.)

- **S4 — Record editor + Guided Completion + Evidence** (2026-07-23 @ `5665132`): presentation/layout/
  copy only (D8/D9/C2 + HIER-2); no pending/question/computation/confirmation/validation/
  evidence-classification or nav-target change. Test-first (orchestrator wrote the C2 `pendingSummary`
  red contract → 4 failed), Opus 4.8 implemented, independent Opus review = **SHIP** (0 Critical/
  Important). D9/C2: pure `pendingSummary()` (concise `KIND_LABEL`, verbatim-question fallback for
  unknown kinds, locator once) drives a numbered `<ol>` banner — concise label primary, locator demoted
  once, raw identifiers (`reduced_spectrum`/`required_for_evidence_record`) never the primary label,
  dynamic count; Guided Completion keeps the full original question (covered by completion-export test).
  HIER-2: `.needsyou-about` no longer `word-break:break-all` (safe wrapping). D8: right rail is the
  AssistantPanel only (evidence panel + divider removed); a compact "Evidence Trail · N entries" link
  sits beneath the WorkflowSpine and reuses the existing `/evidence` route (no new evidence system);
  inline per-field evidence retained (FieldRow drops its interactive role when unselected — no dead
  handler). 1 test re-expressed (tightened). **Accepted Minors → S6:** orphaned `.ev-panel-*`/`.ev-field`
  CSS + inert optional FieldGroup `selectedPath`/`onSelectField` props (both inert). Verify: full FE
  **594 passed**, `npm run build` clean, snapshot regen + gate 17/17 (adapt/RecordWorkbench/screens.css
  manifest members). CI `5665132` success; Railway `synthetic-only` serving `5665132`; Vercel 200.
  Hosted QA PASS — numbered legible banner (concise label + locator once, no raw-identifier primary),
  right rail assistant-only, Evidence Trail link beneath the spine → /evidence, inline field evidence
  retained, console clean.

- **S5 — Casing + semantic headings + a11y** (2026-07-23 @ `ee7f5f6`): presentation/copy/attributes
  only; no logic/route/data/behavior change. Test-first (orchestrator wrote the A11Y-1 one-h1-per-screen
  red contract → 6 failed), Opus 4.8 implemented, independent Opus review = **SHIP** (0 Critical/
  Important). A11Y-1: exactly one screen-level h1 per routed surface — sr-only h1 on Record/Evidence/
  Export (all render branches), page-title h2→h1 on ProjectMemory/Governance/Settings, sublevels
  cascaded gap-free (fixed a real pre-existing ProjectMemory-Concepts h3→h5→h6 skip); VerdictCard h3→h2
  (ExportReadiness-only consumer). D10: two label-tier casing fixes ('Answer Now', 'Out of Date') — no
  body/question/helper recasing, no technical-token recase (audited + enumerated). C4: HelpPanel close
  icon aria-hidden (button keeps its name); inactive Project-Memory tabs omit `aria-controls` (S3
  residual). Carried residuals (focus/tab-order/non-color/touch-target) reviewed — no genuine gaps.
  Verify: full FE **606 passed**, `npm run build` clean, snapshot regen + gate 17/17. CI `ee7f5f6`
  success; Railway `synthetic-only` serving `ee7f5f6`; Vercel 200. Hosted QA PASS — placeholder h1
  renders cleanly, no visual regression, console clean. **Accepted Minors → S6:** (M1) GuidedCompletion
  backend-down error shell has an h2 without an h1 (transient/error-only), (M2) HelpPanel trigger icon
  not aria-hidden (cosmetic), (M3) AdvisoryChip '{n} advisory' lowercase (defensible count phrase);
  plus carried from S4 — orphaned `.ev-panel-*`/`.ev-field` CSS + inert FieldGroup `selectedPath`/
  `onSelectField` props.

- **S6 — Responsive + zoom + long-content + search + cleanup** (2026-07-23 @ `2f51d84`): presentation/
  layout/a11y only; DESKTOP UNCHANGED (all media queries `max-width` 1024/640, additive; zero `min-width`
  layout rule). Test-first for the a11y/drawer contract, Opus 4.8 implemented, independent Opus review =
  **SHIP** (0 Critical/Important; 3 Minors all fixed in a follow-up pass). RESP-1/D11: at narrow widths
  the fixed chrome (LeftNav/WorkflowSpine/EvidenceTrail/record-right/memory-right) stacks/goes fluid with
  no horizontal overflow; the AssistantPanel collapses behind a labelled Assistant slide-over drawer (new
  `AssistantDrawer`: role=dialog+aria-modal, aria-expanded, focus trap, Escape, focus restore, closes on
  resize-to-desktop; desktop renders byte-identically to the former aside). 200%-zoom/long-content:
  overflow-wrap containment. D12/NAV-1: search results show "in {title}" from the existing
  `ApiWorkspaceSearchResult.title` only when it differs from the label — presentational, no
  ranking/retrieval change (NAV-1 resolved, not deferred). Cleanup: orphaned `.ev-panel-*`/`.ev-field` +
  dead FieldGroup/FieldRow selection plumbing + `.field-row.selectable/.selected` removed; M1
  GuidedCompletion backend-down sr-only h1; M2 HelpPanel trigger icon aria-hidden. Verify: full FE
  **621 passed**, `npm run build` clean, snapshot regen + gate 17/17. CI `2f51d84` success; Railway
  `synthetic-only` serving `2f51d84`; Vercel 200. **Hosted verification:** live CSSOM shows
  `widthMediaQueries = 9` (was 0 at audit — RESP-1 measurably closed), `max-width` only,
  `noHorizontalOverflow=true` at desktop; desktop dashboard unchanged; console clean. **Human-only (R3):**
  the narrow-width RENDERING (rail-collapse/pane-stacking/drawer presentation/200%-zoom reflow) is not
  automation-observable (jsdom applies no viewport/CSS; the browser viewport is pinned at 1440) — drawer
  BEHAVIOR is fully unit-tested; narrow PRESENTATION requires a human at 1280/1024/768/375 + 200% zoom.

## Phase 33 Completion Gate (CLOSED 2026-07-23 @ code HEAD `2f51d84`)

| Criterion | Status | Evidence |
|---|---|---|
| Dashboard declutter (D1/D2/C1) | ✅ | clean title, lifecycle+date badges, field-count/chevron-only right side, 2/1/1/1, enriched a11y name; hosted-verified |
| Assistant shell (D3/D4/D5/C3) | ✅ | composer→suggested→answers, honest inert composer (no fetch/answer/history), lavender rail, disclaimers de-duped; app-wide; hosted-verified |
| Project Memory (D6/D7) | ✅ | Overview/Sources/Concepts tabs, right-rail assistant, single green "Memory Available", memory-plane explanation kept; hosted-verified |
| Record editor + evidence (D8/D9/C2, HIER-2) | ✅ | numbered banner via pure formatter, Guided Completion full question kept, right rail assistant-only, Evidence Trail → existing /evidence, inline evidence kept; hosted-verified |
| Casing + headings + icon a11y (D10/C4/A11Y-1) | ✅ | one h1/routed screen, gap-free outline (fixed a real skip), 2 label-tier casing fixes, icon a11y; heading-outline suite green |
| Responsive (D11/RESP-1) | ✅ | **live CSSOM 0→9 width media queries (max-width only, desktop unchanged)**; assistant drawer dialog a11y; long-content/zoom containment |
| Search clarity (NAV-1/D12) | ✅ | "in {title}" from existing field, presentational, no ranking/retrieval change — **resolved, not deferred** |
| No-functionality change | ✅ | validation/evidence/export/reconciliation/confirmed-write/no-guessing/computation/routing/retrieval/API/schema all unchanged |
| Truth path untouched | ✅ | `git diff 46eea62..2f51d84 --stat` = zero changes under `src/isaac_records/`, `schema/`, `apps/api/**/*.py` (only `memory-snapshot.json` data) |
| Full FE suite / build / snapshot gate | ✅ | 621 passed / `npm run build` clean / gate 17/17 |
| Final independent Opus review | ✅ | **SHIP** (0 Critical / 0 Important) over the whole `46eea62..2f51d84` range |
| CI / Vercel / Railway | ✅ | exact-HEAD CI `2f51d84` success; Vercel 200; Railway `synthetic-only` serving `2f51d84` |
| Repo clean + synced | ✅ | `main`, 0 ahead / 0 behind at closure |

**Phase 33 = COMPLETE.** Deferred: real free-form assistant Q&A (separate approval-gated phase).
Human-only rendering QA (narrow-viewport 1280/1024/768/375 + 200% zoom; mutation journey; two-window
live-sync; exported-artifact stale; `absent_from_record`) honestly carried, per R3. No new phase started;
the next phase requires explicit user approval.

## Phase 33 — Human-QA Correction Slice (code HEAD `4dc040d`, 2026-07-23)

Krish's initial human review found real visual defects. The human gate was **reopened**; the automated
closure above (code HEAD `2f51d84`) stands as the historical automated boundary. One scoped code commit
`4dc040d` (+ this docs commit). All changes visual/layout/copy/state-init; truth path untouched
(`git diff 5a41704..4dc040d --stat` = zero under `src/isaac_records/`, `schema/`, `apps/api/**/*.py`
except `memory-snapshot.json` data).

| Finding | Status | Evidence |
|---|---|---|
| #1 composer placeholder | ✅ | `Ask a question` (sentence case), aria-label preserved/independent, empty submit no-op, still inert; hosted-verified |
| #2 vertical rhythm | ✅ | one 16/8 rhythm, existing tokens, all assistant surfaces |
| #3 full-height lavender rail | ✅ | lavender on `.record-right`/`.memory-right` container; panel + memory card de-chromed; neutral `--border` edge; hosted CSSOM `rgb(236,235,251)`, full height |
| #4 no bottom clipping | ✅ | rail single scroll container + 24px bottom pad; log nested scroll kept; no `overflow:hidden`; hosted `captionWithinRail=true` |
| #5 groups default collapsed | ✅ | all collapsed on load, per-group toggle preserved (not accordion), survives assistant interaction, computation untouched; hosted expand verified |
| #6 casing/dedup | ✅ | human-label-first headings; header strips `· New Draft` + drops `draft ·` (identifier + 1 badge kept); Title-Case `Memory Available`/`Unavailable` head |
| #7 single availability state | ✅ | `showAvailabilityHead` prop suppresses redundant head on `/memory` + Evidence; `availability` still passed → classifier/caveat unchanged; hosted `/memory` single state |
| Declined (reported) | ⏭️ | optional `sha256`→`SHA-256` recasing — no safe layer; would transform backend question text (forbidden) |
| Tests / build / snapshot / invariant | ✅ | 635 FE / `tsc -b` / `npm run build` / snapshot no-drift + gate 17/17 / `no-vertical-rail` green |
| Independent Opus review | ✅ | **SHIP** 0 Critical / 0 Important (1 guard-comment fixed; 2 cosmetic left) |
| CI / Vercel / Railway | ✅ | exact-HEAD CI `4dc040d` success; Vercel serving new frontend (CSS hash == HEAD build); Railway `4dc040d` `synthetic-only` |
| Repo clean + synced | ✅ | `main`, 0/0 at `4dc040d` |

**State: automated and hosted desktop verification passed; awaiting final human visual sign-off.** The
human gate stays OPEN. Human-only remaining: narrow-viewport rendering (1280/1024/768/375) + 200% zoom
(esp. the full-height lavender rail + narrow drawer), a legibility glance at the demoted `.fg-sublabel`
raw-key token, plus the pre-existing §gate human-only items. No new phase; next phase needs explicit approval.

## Phase 34 — Free-Form Deterministic Assistant Q&A (CLOSED 2026-07-23 @ code HEAD `d69d0ed`)

Goal: let the Assistant answer flexibly-phrased natural-language questions about the current record
and (record-agnostically) about Project Memory, **without adding an LLM** — a bounded, deterministic
intent-classify-then-answer resolver, honest refusal outside that catalog, read-only end to end.
Closes the Phase 33 "real free-form assistant Q&A" deferral. 6 commits on `main`, all CI green.

**Decision #13 (documentation language, binding for this closure and its docs):** "free-form" means
flexible natural-language *phrasing* over a bounded, deterministic intent catalog — **not** a
general-purpose chatbot and **not** open-world answering. No model provider, secret, AI dependency, or
outbound model request was added. Unsupported and ambiguous questions are refused honestly; unknown
scientific/open-world facts are never guessed. Project Memory answers are advisory and cited (leads to
verify) — never treated as record/experiment truth or a verdict. Q&A is READ-ONLY and cannot mutate
records/revision/workflow/evidence/validation/export/memory/files. Conversations are ephemeral
(browser session), cleared on Reset Demo — no server-side persistence, no Project-Memory indexing of
conversation text, no prompt/answer text in logs. A real LLM provider (Tier 2) remains an **unapproved,
deferred future product decision** — not committed work.

- **P34.1 — read-only resolver + endpoint** (`15fb8ec`): pure, stdlib-only `assistant_query.py`
  (classify → answer) covering 8 record intents + `memory_lead`, honest refusal for
  unsupported/ambiguous/open-world questions; two READ-ONLY routes —
  `POST /api/experiments/{id}/assistant/query` (record-scoped) and
  `POST /api/assistant/memory/query` (record-agnostic, Project Memory) — verdict-guard + path/secret
  scrub on every answer, revision-stamped, typed errors, never mutates.
- **P34.2 — composer wiring + rail declutter** (`ccd786a`): composer wired to the read-only resolver;
  the on-mount auto-reply ("N fields still need you") **removed** — the rail rests on the honest empty
  state; bounded ephemeral conversation (reuses the P29 session, `MAX_MESSAGES=40`, cleared on Reset
  Demo); Clear Conversation.
- **P34.3 — provenance, staleness, Ask Again** (`8f7c12f`): answer provenance labels + cited-lead
  chips with client-route source navigation; compact live-answer staleness indicator + explicit Ask
  Again (no silent auto-regeneration).
- **P34.4 — cross-surface memory query** (`a9339f2`): record-agnostic Project-Memory query wired on
  the memory-scoped composer, consistent with the record-scoped path — one shared answer pipeline
  across surfaces.
- **P34.5 — a11y, responsive, degradation** (`2481858`): single polite live region + focus management
  + accessible names; responsive behavior (narrow width, 200% zoom, long-content wrapping); honest
  "unavailable" degradation + defensive timeout — no silent hang, no fabricated answer.
- **P34.5(2) — review-closure** (`d69d0ed`): independent Opus review PASSED the authority/read-only,
  no-LLM/no-infra, no-guessing, determinism, privacy, staleness, no-regression, synthetic-only
  contract; its two findings were fixed in this commit — **D1** verdict-guard extended to cited
  *source labels* (not just answer text), **R2** suppress misleading provenance on refusals (a refusal
  no longer carries a stale/verified provenance stamp).

**One `AssistantPanel` across all 5 surfaces** (Record Workbench, Guided Completion,
Evidence Explorer, Export Readiness, Project Memory — the My Experiments dashboard does not mount it);
Suggested Questions stay precomposed and share
the one answer pipeline; Agent Actions and the single write path (`confirmProposal`) are unchanged and
kept fully separate from the read-only Q&A path.

**Verification at close:** backend `.venv/bin/pytest -q` → **964 passed**; frontend `npm test` →
**672 passed** (55 files); `npm run build` clean; committed-snapshot gate green. CI green on every one
of the 6 pushes. Railway `synthetic-only` @ HEAD; Vercel deployed.

**Hosted synthetic QA (live, PASS):** empty-state rail (no auto pending-summary card); free-form
deterministic answers; an open-world scientific question refused (no guess); read-only confirmed —
only `/assistant/query` was hit, never `/answers`/`/edit`/`/export`; provenance labels + cited-lead
chips render; Clear Conversation works; memory-scoped composer answers on Project Memory; console
clean; no telemetry observed.

## Phase 34 Completion Gate (CLOSED 2026-07-23 @ code HEAD `d69d0ed`)

| Criterion | Status | Evidence |
|---|---|---|
| Bounded deterministic resolver, no LLM (P34.1) | ✅ | `assistant_query.py` stdlib-only classify→answer; 8 record intents + `memory_lead`; honest refusal outside catalog |
| Two read-only routes, verdict-guard + scrub | ✅ | `/assistant/query` (record-scoped) + `/assistant/memory/query` (record-agnostic); revision-stamped; typed errors; never mutates |
| Auto-reply removed; honest empty state (P34.2) | ✅ | on-mount "N fields still need you" reply removed; bounded ephemeral session (`MAX_MESSAGES=40`); Clear Conversation |
| Provenance + staleness + Ask Again (P34.3) | ✅ | source labels + cited-lead chips with route navigation; compact staleness indicator; explicit Ask Again, no silent regeneration |
| Cross-surface consistency (P34.4) | ✅ | record-agnostic Project-Memory query on the memory-scoped composer; one shared answer pipeline |
| A11y / responsive / degradation (P34.5) | ✅ | single polite live region + focus management; narrow-width/200%-zoom/long-content wrapping; honest unavailable + defensive timeout |
| Independent Opus review | ✅ | PASSED the authority/read-only, no-LLM/no-infra, no-guessing, determinism, privacy, staleness, no-regression, synthetic-only contract; D1 + R2 fixed in `d69d0ed` |
| Decision #13 language honored | ✅ | bounded-catalog framing, no open-world/generative claim, advisory+cited memory answers, read-only, ephemeral, Tier-2 LLM stays unapproved/deferred |
| Truth path untouched | ✅ | no changes under `src/isaac_records/`, `schema/`, `apps/api/**/*.py` truth modules — only the new read-only `assistant_query.py`/routes and frontend wiring |
| Full backend/frontend suite / build / snapshot gate | ✅ | backend 964 passed; frontend 672 passed (55 files); `npm run build` clean; snapshot gate green |
| CI / Vercel / Railway | ✅ | CI green on all 6 pushes; Railway `synthetic-only` serving HEAD; Vercel deployed |

**Phase 34 = COMPLETE at `d69d0ed`.** Open items honestly carried, not overstated as done:

- **Human VISUAL sign-off (narrow-viewport 1280/1024/768/375 + 200% zoom)** remains a human decision —
  P34 added the responsive CSS + a11y and automated/desktop QA passed, but the human visual gate is
  Krish's to give, paralleling the still-open Phase 33 human visual gate (see the Phase 33 HQA section
  above).
- **Tier 2 (a real LLM provider)** remains an unapproved, deferred future product decision — not
  scoped, not scheduled, not implied by anything shipped in Phase 34.

No new phase started; the next phase requires explicit user approval.
