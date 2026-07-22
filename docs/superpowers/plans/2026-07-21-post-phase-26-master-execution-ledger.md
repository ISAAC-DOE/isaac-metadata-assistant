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
| **Current phase** | **Phase 28 COMPLETE** (2026-07-22; two documented non-blocking QA caveats) → Phase 29 — Assistant Experience |
| **Active ticket** | P29.3 — Bounded deterministic workflow agent (next) |
| **Completed** | **Phase 27 (all slices)**: T0 (`859d36c`); P27.0; approval (`33825ff`); P27.1 (`26642eb`); P27.2 (`14477bd`); P27.3 (`ccac6d3`); P27.4 (`41bd20b`); P27.5 (`0112f5f`); P27.5-strict (`d7a9fef`); reset-content (`61c017f`); P27.6 (`ef31f5b`); P27.7 hosted two-tab QA (conflict-safety hosted-PASS). **Phase 28**: P28.0 audit + plan (`a0e2a09`); P28.1 fixed workflow order (`e434de2`); P28.2 dep invalidation + artifact freshness (`859309f`); P28.3 revisit/summary/edit (`039ac1b`); P28.4 evidence classifier (`b1b9cd0`); P28.5 typed evidence API+UI (`bea0a01`) |
| **Next step** | Phase 29 P29.0 live context builder → P29.1 ephemeral session context → P29.2 conversation UI → P29.3 deterministic workflow agent → P29.4 one shared state → P29.5 hosted agent QA |
| **Blockers** | none |
| **Latest impl commit** | `ef31f5b` (P27.6) |
| **Latest checkpoint commit** | `a50923d` (Phase 27 closure docs) |
| **Verification status** | full backend **751 passed**; frontend **383 passed** + build clean; CI green on `a50923d`; Railway `a50923d` synthetic-only; Vercel P27.6 bundle live |
| **Open QA caveat** | P27.7 scenarios 1 (idle passive-poll banner + ~8s cadence) & 5 (offline degraded indicator) NOT hosted-observed — Claude-in-Chrome drives tabs `visibilityState=hidden` and polling is correctly visibility-gated, so an automated hidden tab doesn't passively poll. Both behaviors are deterministically unit-tested (visibility pause/resume, backoff, degraded, LiveSyncNote) + the conflict path is hosted-verified. Recommend a human TWO-WINDOW (both visible) session to visually confirm. Not a defect; not a blocker. |
| **Open decisions** | ledger→resume skill wiring (skill edit needs approval); strict 428 enforcement gated on deployed-FE sending If-Match (P27.4/P27.5) |
| **Approved constraints** | synthetic-only; no LLM; no real data; no new cloud service; no account/billing change (except `ISAAC_RUNTIME_MODE` add) |
| **Next recommended action** | P29.0 — live context builder (assistant reads authoritative live record/workflow/evidence state; no external LLM; confirm-gated) |
| **Git sync** | `main` · local == `origin/main` == `938c4e4` · 0/0 · clean (before Phase-28 closure commit) |
| **Exact-HEAD CI** | P28.0–P28.5 green (`bea0a01`, `938c4e4` = success); closure commit pending push-time verify |
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
