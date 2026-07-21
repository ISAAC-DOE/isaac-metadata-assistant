# Phase 25 — Grounded Assistant — Implementation Plan

Status (updated 2026-07-21): **P25.0 approved · P25.1 RELEASED · P25.2 RELEASED** — all on `origin/main`, CI-green and browser-verified. **P25.3 remains an intentional tombstone** (folded into P25.1). **P25.4 (Ground the Export context) is RELEASED** (`e0e3d1a`, CI green, hosted QA green). **P25.5 (Evidence context) is RELEASED** (`5600961`, CI green run `29798842384`, deployed & served-bundle-verified). **P25.6 (Complete Missing Fields context) is RELEASED** (`a0446fe` + served-snapshot regen `5b2fb3d`, CI green run `29804048533`, Vercel bundle serves all three chips, Railway healthy). **R4.2 (Shared Repository Synchronization Contract) is RELEASED** (`093a9f4`; continuity/workflow only). **P25.6 release-evidence closed** (`3012bb0`; CI/Vercel/Railway mapping, hosted-QA deferral preserved). **P25.7 (Project Memory context) is RELEASED** (`bdd590c`, CI green run `29807075500`, Vercel bundle `index-DjSM7pbq.js` serves all three memory chips, Railway healthy at `bdd590c`; interactive hosted QA deferred — no browser tool this session). **P25.9 (retire `ASSISTANT_SAMPLES` + migrate the DEV sanity guard) is RELEASED** (`411481f`, CI green run `29815052880`, deployed & browser-verified). **R4.3 (deterministic first-push preflight) is RELEASED** (`670d249`, CI green run `29814924522`; continuity tooling). **a11y fix CQ-10** (exported-row aria-label `undefined/undefined`) **RELEASED** (`dad3b07`, CI green run `29815570816`, browser-verified). **All four grounded assistant surfaces + Project Memory are now interactively browser-verified on production** (closes the P25.4–P25.7 deferred hosted-QA gate). **P25.10 (full verification + CP-C copy sweep — CQ-2 memory leads-to-verify tail + docs) is RELEASED** (`b30ff19`, CI green run `29841596523`, deployed & interactively browser-verified on both target chips). The **Phase 25 STOP GATE is BLOCKED** on the §8 fresh-session Chrome resilience test (requires a genuinely fresh `claude-slac` process — cannot be self-performed and must not be fabricated); **P25.8 remains EXCLUDED**; **Phase 26 NOT started** (its gate is the stop gate). Per-slice report→review→commit→push→CI→checkpoint and the hard-stop gates remain in force. Direction **DECISION-LOCKED 2026-07-20**.
Date: 2026-07-19 (decisions locked 2026-07-20)  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: 2026-07-16-phases-23-26-arc-decisions.md; `2026-07-20-remaining-work-decision-lock.md` (authoritative); P24 specs (24 / 24.9 / 24.10); this doc EXTENDS the approved arc.

### Session checkpoint — 2026-07-21 (P25.10 CQ-2 RELEASED; Phase 25 STOP GATE blocked on §8 fresh-session Chrome test)
- **P25.10 / CQ-2 RELEASED** — `b30ff19`, CI green run `29841596523`. Appended `MEMORY_LEADS_TAIL` ("Project memory returns leads to verify — never a validation verdict.") to the `memory_freshness` chip and BOTH `included_scope` branches; previously only `memory_provenance` carried it, so freshness/scope answered without the advisory frame (violating the composer file-header invariant). The `memory_unavailable` replacement chip is intentionally unchanged (it states no memory answer exists). Reuses the existing constant; no other composer behavior change. Test-first: new behavior-level CQ-2 describe block over rendered `compose()` output (endsWith + caveat-before-tail ordering + negative guard on the unavailable chip; proven RED before the fix) + updated existing exact `.toBe` assertions (none weakened). Additive dated shipped-status note in `docs/ui-handoff/ai-assistant-and-graphify.md` (design prose preserved, not rewritten). Snapshot deterministically regenerated for the doc sha256 (`served_file_count` 202 unchanged).
- **Verification (verified-now, this session — not checkpoint-claimed):** backend `pytest` 500; web `vitest` 299 (20 files); `tsc -b` + `vite build` clean (bundle `index-D1XTQwN7.js`); snapshot `--check` no drift; committed-snapshot gate 17; synthetic demo end-to-end (official schema valid, byte-identical repro); `isaac validate --official` PASS v1.05; `isaac audit` PASS (evidence 33/33). Independent Opus 4.8 adversarial review APPROVE (8/8 checks; one Advisory doc-wording nit applied). R4.3 `full` preflight PASS (both working-tree and ahead-of-origin commit scan paths).
- **Hosted browser QA (production `isaac-demo-web.vercel.app`, live bundle):** Project Memory — freshness chip now reads "…indexed sources: current. Project memory returns leads to verify — never a validation verdict."; scope chip "…require a Graphify refresh. Project memory returns leads to verify — never a validation verdict." (**CQ-2 confirmed LIVE on both target chips**); provenance unchanged; chip order [provenance, freshness, scope] + approved labels; **no new fetch on chip click** (network empty after clear, both clicks); API calls to Railway HTTPS (`/api/graph/status`, `/memory/files`, `/memory/concepts` all 200); **console clean**; guided-prompts-only + advisory disclaimer, no textbox/send, no verdict/undefined/null. Cross-surface regression: RecordWorkbench `AssistantPanel` intact (`answered from: Workflow & Artifacts`, honest no-pending line, three guided-prompt buttons, no verdict).
- **CQ disposition:** **CQ-2 CLOSED** (this slice). Still open, unchanged: CQ-1 (→Stabilization), CQ-4 (→Stabilization-security), CQ-5 (Minor →cleanup slice), **CQ-6** (Minor doc-truth — the finding wording is imprecise: `MEMORY_UNAVAILABLE_CAVEAT` is LIVE at `assistant.ts:48`, NOT retired; the stale references are a dated historical checkpoint note (do NOT rewrite, §10) and shifted body line refs — recorded for a scoped documentation-truth pass, deliberately NOT fixed here), CQ-7 (→Wave-8 Graphify refresh), CQ-9 (CI Node 20 deprecation →Stabilization-ops). No new Critical/Important findings surfaced.
- **Sync axes (four, separate):** at P25.10 release Local↔GitHub synchronized (HEAD `b30ff19`, 0/0, clean); GitHub↔CI exact-HEAD green (`29841596523`); GitHub↔Vercel auto-deployed & interactively browser-verified live; GitHub↔Railway healthy (API 200 this session). This docs checkpoint commit re-advances Local↔GitHub — verify its own exact-HEAD CI after push.
- **Phase 25 STOP GATE — BLOCKED (hard gate, human-required):** every local + hosted P25.10 criterion passes, BUT §8 requires proving Claude-in-Chrome re-registers in a **genuinely fresh** `claude-slac` process (exit this session → restart via the approved entry point → `isaac-profile` + `isaac-resume` → prove navigate/screenshot/click/console/network). This cannot be self-performed from the current session and must not be fabricated. **Phase 26 is NOT started** (§13 gate). **NEXT HUMAN ACTION:** perform the §8 fresh-session Chrome resilience test; if it passes, mark Phase 25 complete and proceed to Phase 26; document any manual reconnect procedure discovered.

### Session checkpoint — 2026-07-21 (P25.9 + R4.3 + CQ-10 RELEASED; browser-capable; P25.10 now active)
- **Environment proven browser-capable.** Toolset `slac` (root `~/.claude-slac`, no context-mode); services on the existing Krish-owned identities (GitHub `Krish-Verma`, Railway `Krish Verma`, Vercel `kvlx`). Claude-in-Chrome verified by real control: navigate + screenshot + click + console(clean) + network (`GET /api/experiments`→200 to Railway prod). Hosted app healthy (Vercel SPA + Railway API 200, no console errors, no mixed content).
- **R4.3 RELEASED** — `670d249`, CI green `29814924522`. New `scripts/isaac_preflight.py`: a Python pre-push gate (modes docs/frontend/backend/full) with strict subprocess return-code handling (no tail/grep masking); never pushes/mutates/regenerates; repo-identity + branch + ff-only divergence + secret/junk filename rejection + content leak scan + committed-snapshot `--check` + gate test run UNCONDITIONALLY. Two independent Opus reviews; second found a false-PASS vector (secret scan blind to committed-ahead content at push time) → hardened to scan the union of working-tree AND ahead-of-origin commit content, fail-closed on git error. 39 preflight tests. Wired into `/isaac-checkpoint` (refuses push on non-zero exit). Used to gate every push this session.
- **P25.9 RELEASED** — `411481f`, CI green `29815052880`. Deleted `ASSISTANT_SAMPLES`, its `import.meta.env.DEV` sanity loop, `ASSISTANT_SOURCES`/`isValidSource`, `AssistantContext`, and the runtime-dead `sourceDoc` field/render/CSS (compose() never set it). No-verdict guarantee now enforced over live/fixture composer output; the exhaustive per-context no-verdict sweeps in `assistantComposer.test.ts` (92) + `memory-composer.test.ts` (35) are unchanged. Independent Opus review APPROVE. Web suite 290; served snapshot regenerated (indexed `assistant.ts`). Zero backend/truth-core change.
- **CQ-10 RELEASED** — `dad3b07`, CI green `29815570816`, browser-verified (`undefinedCount:0`). `ExperimentRow.describeTrailing()` interpolated `coverage undefined/undefined` into exported rows' aria-label (optional `trailing.coverage` omitted by backend for exported records) — screen-reader-only `undefined` leak. Guarded both branches; new `experiment-row.test.tsx` (4 cases, red→green). Snapshot regenerated.
- **Browser QA (production, all grounded surfaces):** RecordWorkbench (live pending, `answered from: Workflow & Artifacts`, no-new-fetch confirmed: 0 requests on chip click), Complete (staged-vs-confirmed + honest "I don't know"), Export (coverage 29/33, no PASS/FAIL echo in assistant, CLI-route note, `answered from: Evidence Audit`), Evidence (selected field drives answer, sidecar framing accurate, `answered from: Evidence & Sources`), Project Memory (4 axes separate, leads-to-verify). Console clean throughout. This CLOSES the P25.4–P25.7 deferred interactive hosted-QA gate.
- **Retrospective audits (read-only):** truth core clean & Graphify-free (461 tests; export double-gated; sidecar id-derived; no-guessing holds); grounded-assistant frontend clean. Corrective queue open: **CQ-1** demo/run unbounded experiment accumulation (`routes.py:153`, → Stabilization), **CQ-2** memory freshness/scope answers lack leads-to-verify tail (`assistantComposer.ts:513/555`, → **P25.10**), **CQ-4** CORS `allow_headers=["*"]` + `/tmp` workspace (→ Stabilization-security), **CQ-5** duplicated pending-label ladder, **CQ-6** stale plan wording re retired `MEMORY_UNAVAILABLE_CAVEAT` (§13:365-366), **CQ-7** committed snapshot manifest indexes 5/8 skills only (graphify-out stale at `caab1d0`; CLAUDE.md §17 "each SKILL.md"/202 slightly overstated — self-corrects at the Wave-8 Graphify refresh), **CQ-9** CI `actions/setup-node@v4` on deprecated Node 20.
- **Sync axes (four, separate):** Local↔GitHub synchronized (HEAD `dad3b07`, 0/0, clean); GitHub↔CI exact-HEAD green (`29815570816`); GitHub↔Vercel auto-deployed & browser-verified live; GitHub↔Railway healthy (API 200). Explicitly NOT re-checked this checkpoint: Railway `/api/health` commit field (not re-queried since the last push).
- **Continuation:** **P25.10 (full verification + CP-C copy sweep — fix CQ-2's leads-to-verify tail on the two memory chips with a regression test + doc update `docs/ui-handoff/ai-assistant-and-graphify.md`)** is the next authorized slice, then the phase-25 final stop gate before Phase 26. No re-authorization needed to resume. R4.3 preflight now gates all pushes.


- **P25.7 RELEASED** — commit `bdd590c` on `origin/main`; `main` clean and synchronized (HEAD = `bdd590c`, 0 ahead / 0 behind). Ground + **new mount** of the grounded assistant on `ProjectMemory` via `compose({context:'memory', graph: graph.data})`, subordinate to the memory-status card, using ONLY the already-fetched `GET /api/graph/status` response — **no new fetch/route**, no LLM, no free-text; **zero** `apps/api/**` / `src/**` / `schema/**` change (verified `git diff --stat` empty on those paths).
- **Chips (spec §5.5, verbatim):** available → `memory_provenance` / `memory_freshness` / `included_scope` (all source `graph` → **Project Memory**); `availability='unavailable'` → the single `memory_unavailable` replacement chip (never four at once). The four axes (availability, integrity, memory_policy, indexed_sources) are stated **separately** per §6, never collapsed; `indexed_sources` never emits a `stale` caveat at runtime; `included_scope` grounds on `file_count` with an honest null path; provider parenthetical dropped when absent/empty/`unavailable`.
- **Deferred P25.6 items resolved:** `MEMORY_UNAVAILABLE_CAVEAT` rewritten to "Project Memory is unavailable, so no memory-based answer is available here." (the prior "…answered from source files directly" was spec-§6-flagged FALSE); `AssistantPanel.availability` made optional so `GuidedCompletion` (never fetches graph status) no longer asserts a memory state — panel renders no memory head line / caveat when availability is omitted.
- **Test-first + verification:** RED captured first (composer threw for `memory`; screen panel absent) → GREEN. `tsc -b` + `vite build` clean; **294 frontend tests / 19 files** (+45 from 249; new `memory-composer.test.ts`). Served snapshot regenerated deterministically **in the same commit** (7 manifest-listed frontend files changed hashes; `served_file_count` unchanged at 202); `test_committed_snapshot.py` 17 passed. Snapshot preflight was run BEFORE the push (drift caught at preflight, not CI — the P25.6 lesson applied).
- **Independent review:** a *separate* Opus 4.8 adversarial reviewer (not the implementer) → **REQUEST CHANGES** for 1 Important finding (duplicate identical sentence on the unavailable mount, which is the actual hosted state) → fixed via an `AssistantPanel` dedupe guard (`caveat` suppressed when byte-identical to the rendered reply) + an occurrence-count regression test; all other 17 checks APPROVE. The type-only 4-sentence `memory_freshness` edge was adjudicated **backend-unreachable** (backend forces `integrity='verified'` whenever available) → left as-is with a pinning test. Advisory (unreachable `MEMORY_FALLBACK`) matches the existing defensive-fallback pattern → left.
- **Sync axes (four, separate):** Local↔GitHub synchronized (HEAD `bdd590c`, 0/0, clean); GitHub↔CI exact-HEAD green (run `29807075500`); GitHub↔Vercel deployed — new production deployment `isaac-demo-2qg6rtt09` Ready, live bundle `index-DjSM7pbq.js` serves all three P25.7 memory chip labels (auto-deployed on push; no manual redeploy); GitHub↔Railway healthy at `bdd590c` (`/api/health` `commit: bdd590c`, auto-redeployed).
- **Hosted QA — NOT performed (honest, blocker disclosed):** this session has **no Claude-in-Chrome / browser-automation tool**, so authenticated interactive hosted click-through (§13) could not be run. Corroboration only: the live production bundle contains all three memory chips (static content check), and the green screen-integration tests render the real `ProjectMemory` + `AssistantPanel`. Interactive authenticated QA remains **deferred pending browser tooling or a human** — consistent with the P25.5/P25.6 disclosure; NOT recorded as complete.
- **Continuation:** stopped at the clean P25.7 boundary. **P25.9 (retire `ASSISTANT_SAMPLES` + migrate the DEV sanity guard) is the next authorized slice**; **P25.8 remains EXCLUDED** by the decision-lock. No re-authorization needed to resume. Deferred to P25.9's session: the open hosted-QA gate for P25.7 (needs browser or human).

### Session checkpoint — 2026-07-21 (P25.6 released; P25.7 now active)
- **P25.6 RELEASED** — feature commit `a0446fe`, served-snapshot regen `5b2fb3d` on `origin/main`; `main` clean and synchronized (HEAD = `5b2fb3d`, 0 ahead / 0 behind). Ground + **new mount** of the grounded assistant on `GuidedCompletion` (Complete Missing Fields) via `rightPanel` on both loaded branches, subordinate to the guided-completion form. Three approved chips (copy verbatim to spec §5.4): `pending_summary`, `explain_pending_item` (`workflow`), `missing_field_behavior` (`schema`, routed to Validate). Grounded strictly in `{detail, pending, selectedPendingId?}` (spec Q-D — **no** validate/audit/graph fetch added; the plan §20 card's older `{pending, draft, validate}` wording is superseded by the spec/type). Composer stays pure; chip clicks issue no network.
- **Honesty decision:** `availability='available'` so the panel renders **no** memory caveat — `unavailable` would surface `MEMORY_UNAVAILABLE_CAVEAT` ("answered from source files directly"), which spec §6 declares FALSE for the composer and defers to P25.7; the accurate `answered from:` line remains the only source claim. The cross-screen "memory:" inconsistency and the caveat rewrite are P25.7's scope.
- **Verification:** `tsc -b` clean; 249 frontend tests + 461 Python tests pass. **A served-snapshot regen was required and initially missed** — `GuidedCompletion.tsx` and `completion-export.test.tsx` are in the served-content manifest; CI's `test_committed_snapshot_indexed_source_gate_dispatches` correctly caught the drift at `a0446fe`; fixed deterministically in `5b2fb3d` (only those two served hashes + fingerprint changed; `served_file_count` unchanged at 202). `GuidedPrompt.tsx`, `apps/api/**`, truth core, and `schema/**` untouched.
- **Independent review:** a *separate* Opus 4.8 adversarial reviewer ran (not the implementer) → **APPROVE**, 0 Critical / 0 Important, 2 Minor deferred to P25.7 (the `available` cross-screen inconsistency; a dead-defensive fallback).
- **Sync axes:** Local↔GitHub synchronized (HEAD `5b2fb3d`); GitHub↔CI exact-HEAD green (run `29804048533`); GitHub↔Vercel deployed — production bundle `index-CBNEVLu9.js` serves all three P25.6 chip labels (+ P25.5 control chip); GitHub↔Railway healthy at `5b2fb3d` (`/api/health` `status: ok`).
- **Hosted QA — partial (honest):** deployed-bundle content verified (all three chips served in production) + interactive behaviors covered by the green screen-integration tests that render the real `GuidedCompletion` + `AssistantPanel`. Full interactive click-through on the authenticated live app was NOT performed this session (consistent with the prior slices' deferral).
- **Continuation:** **P25.7 (Project Memory context) is the next authorized slice** under the master authorization — it also owns the deferred `MEMORY_UNAVAILABLE_CAVEAT` rewrite and the memory-line framing for memory-less contexts. Stopped at the clean P25.6 boundary; no re-authorization needed to resume.

#### P25.6 release-evidence closure — 2026-07-21 (verification only; no P25.6 production code reopened)
Recorded as verification closure; no P25.6 source was changed. All evidence re-verified from live Git/CI/Vercel/Railway state (not chat memory).
- **Exact CI runs (commit → run ID → head SHA → status):**
  - `a0446fe` → run `29803870194` → head `a0446fe2…` → **FAILURE** (the served-snapshot drift, correctly caught by the committed-snapshot gate — preserved as history; the preflight was initially missed and only then corrected).
  - `5b2fb3d` → run `29804048533` → head `5b2fb3d9…` → **success** (deterministic served-snapshot regen).
  - `1e587cb` → run `29804312780` → head `1e587cb9…` → **success** (checkpoint; current exact-HEAD).
- **Vercel commit/bundle mapping (honest):** production alias `isaac-demo-web.vercel.app` → deployment `dpl_EU3774E7Xt7YTQJpFDSHnTuxg4ex`, `target=production`, `Ready`. These are **`vercel --prod` CLI deploys**, so `meta.githubCommitSha` is **null** — a commit cannot be bound from deployment metadata. A local rebuild at HEAD produced `index-CQtagqIO.js` ≠ deployed `index-CBNEVLu9.js` (build-environment difference: Vercel cloud vs local Vite/rollup), so hash reproduction cannot bind it either. **Deterministic binding by source-equivalence:** `git diff --name-status a0446fe..1e587cb` = only `apps/api/isaac_api/data/memory-snapshot.json` + this plan doc — **zero frontend runtime source changed after `a0446fe`**, so the deployed frontend runtime is source-current for HEAD regardless of which working tree produced the CLI deploy. Corroborated by re-fetching the served bundle this session: it contains all three P25.6 chip labels + "Guided prompts only"; the P25.7 memory chip string is absent (expected). It is therefore correct that the deployed frontend runtime corresponds to the P25.6 frontend (unchanged through `1e587cb`, which is docs-only).
- **Railway commit mapping — CORRECTION:** Railway is **at `1e587cb`, not `5b2fb3d`** (prior checkpoint line recorded `5b2fb3d`, true at that instant). Live: active deployment `26108fba…`, `commitHash 1e587cb9…`, branch `main`, RUNNING; `/api/health` → `{"status":"ok","mode":"synthetic-only","commit":"1e587cb9…"}`. Railway auto-redeploys every push to `main`, including the docs-only checkpoint. `git diff 5b2fb3d..1e587cb` = only this plan doc → **no backend/API Python runtime changed**; the only served-runtime artifact that changed after `a0446fe` was `memory-snapshot.json` (in `5b2fb3d`, which Railway serves). Railway remaining green at HEAD is expected and current for the latest backend-relevant commit — **not** a blocker.
- **Authenticated interactive hosted QA — NOT performed (honest, unchanged):** this session has **no Claude-in-Chrome / browser-automation tool available** (verified: no such tool is present; only WebFetch/WebSearch exist). Per CLAUDE.md and the standing rule, static served-bundle inspection is **not** interactive hosted QA and is not recorded as such. The P25.6 interactive click-through remains **deferred** (consistent with the prior slices' disclosure at line 13); the deterministic served-bundle content check above is corroboration only. This is a known, disclosed gap, not a fabricated pass.
- **Sync axes at closure:** Local↔GitHub synchronized (HEAD `1e587cb`, 0/0, clean); GitHub↔CI exact-HEAD green (`29804312780`); GitHub↔Vercel deployed (P25.6 frontend live; commit binding by source-equivalence as above); GitHub↔Railway healthy at `1e587cb`.

### Session checkpoint — 2026-07-21 (R4.2 continuity released; P25.6 remains active)
- **R4.2 — Shared Repository Synchronization Contract RELEASED** — commit `093a9f4` on `origin/main`; `main` clean and synchronized (HEAD = `093a9f4`, 0 ahead / 0 behind). Continuity/workflow only: one authoritative contract in `docs/toolchain-reconnection-runbook.md` (four repository states, the single ff-only auto-reconcile with a mandatory clean-tree self-check, four separate sync axes, single-editor rule, 40-row decision table); concise cross-refs in `CLAUDE.md` §17 and the reconciliation plan's R4.2 follow-up; `isaac-profile`/`isaac-resume`/`isaac-checkpoint` strengthened (additive — no existing refusal removed). Machine-local `.git/isaac-session-state.json` DEFERRED. Pre-existing roadmap/decision-lock authorization-reconciliation notes committed separately first (`ffe30dd`).
- **Verification:** disposable-repo git-safety simulations (git 2.50.1) confirmed ff-only reaches 0/0 from clean-behind, aborts on divergence, non-ff push rejected, and — key finding — ff-only into a *dirty* tree with unrelated changes succeeds, so the skills gate on a clean tree themselves. Deterministic snapshot regenerated (CLAUDE.md manifest-listed; `served_file_count` unchanged); gate test 17 pass; destructive-verb / no-push-in-resume / secret audits clean; truth/backend/schema/frontend/product untouched. Independent Opus 4.8 review: APPROVE-WITH-FIXES (3 Minor applied).
- **Sync axes:** Local↔GitHub synchronized (HEAD `093a9f4`); GitHub↔CI exact-HEAD green (run `29802584013`); GitHub↔Vercel not relevant (no frontend change); GitHub↔Railway healthy at `093a9f4` (`/api/health` `status: ok`).
- **Continuation:** **P25.6 (Complete Missing Fields context / GuidedCompletion) remains the active authorized slice** under the master authorization; no product behavior changed during R4.2; P25.8 excluded. Next: continue P25.6 from this plan §(P25.6) and the P25.0 spec, per the established report→review→commit→push→CI→hosted-QA→checkpoint loop.

### Session checkpoint — 2026-07-21 (post-P25.5: P25.5 released; P25.6 now active)
- **P25.5 RELEASED** — commit `5600961` on `origin/main`; `main` clean and synchronized (HEAD = `5600961`). Ground + **new mount** of the grounded assistant on `EvidenceExplorer` via `rightPanel`, subordinate to the truth surfaces (Evidence Trail + Source Preview). Three approved chips: `evidence_multiplicity`, `sidecar_convention`, `artifact_paths` — matching P25.0 spec §5.3, with the two more-restrained final wordings the user (copy authority) approved (multiplicity "provide separate support"; sidecar "not part of the official ISAAC schema").
- **Verification:** 222 frontend tests pass (baseline 194 + 28 new; the 2 changed test files pass 3/3, one pre-existing test flaked only under parallel-tsc CPU load); `tsc -b` clean; Vite build clean; snapshot regenerated for served-file drift (2 served-file hashes + fingerprint; `served_file_count` unchanged at 202); gate test `test_committed_snapshot.py` 17 pass; no-new-fetch / verdict-guard / undefined-null / secret audits clean; truth/backend/schema untouched.
- **Independent review:** the *separate* Opus 4.8 adversarial-review subagent **could not run — org monthly spend limit** (API error). An **orchestrator adversarial self-review** against the 10 P25.5 invariants was performed instead → APPROVE, zero findings. This substitution is a known, honestly-recorded deviation forced by the billing limit, not a quality choice.
- **CI:** exact-HEAD CI green (run `29798842384`, conclusion success, headSha `5600961`).
- **Deployment:** Railway `/api/health` reports `commit: 5600961` (backend rebuilt on the monorepo push); Vercel latest Production deployment **Ready**; the public production bundle at `isaac-demo-web.vercel.app` (`index-BXdD-zBM.js`) **contains all three P25.5 chip labels + the exact sidecar and multiplicity wording** — the new code is genuinely served.
- **Hosted QA — partial (honest):** deployed-bundle content verified (above) + all interactive behaviors covered by the green screen-integration tests that render the real `EvidenceExplorer`. **Full interactive click-through on the authenticated live app was NOT performed this session** — a long browser flow was too risky under the active spend limit (could fail mid-run). Manual checklist deferred to the P25.5 report. P25.4 and Guided-Prompts-Only were not re-exercised on the live app this session for the same reason.
- **R4.1 fresh-process verification (2026-07-21):** this session launched via `claude-slac`; the SLAC toolset isolation was re-verified fresh (marker `slac`, config root `~/.claude-slac`, context-mode absent/not-installed, `NODE_OPTIONS` unset, node/npm OK, repo-local skills load). Claude account = `UNKNOWN` (shared Keychain — acceptable). R4.1 **not reopened**; see `2026-07-20-slac-account-toolchain-reconciliation.md`.
- **Continuation:** P25.6 is the next authorized slice under the master authorization; it needs a fresh Opus subagent, which the spend limit currently blocks → **stopped at the clean P25.5 boundary with P25.6 marked active** (per the standing instruction; no re-authorization needed to resume).
- Prior checkpoint blocks below are retained as history.

### Session checkpoint — 2026-07-20 (post-R4.1: R4.1 released; P25.4 now active)
- **Reconciliation gate COMPLETE.** R1–R6 done; **R4.1** (toolset-profile separation + `isaac-profile`) released — commit `47aa9c7` on `origin/main`, exact-HEAD CI green (run `29782165668`).
- **HEAD = `47aa9c7`**; `main` clean and synchronized with `origin/main`.
- The **2026-07-20 master authorization** lifts the P25.4 block and authorizes **continuous execution** of the locked core roadmap (P25.4→P25.10 → Phase 26 → UI Refinement → Stabilization → Documentation & Deliverables → one final Graphify/snapshot refresh). Per-slice report→independent review→commit→push→exact-HEAD CI→checkpoint retained; hard-stop gates in force; P25.8 excluded; Convex/institutional infra off-path.
- **P25.4 RELEASED** — commit `e0e3d1a` on `origin/main`; 194 frontend tests, `tsc -b` clean, Vite build, snapshot regen (served-file drift), exact-HEAD CI green (run `29783857915`), independent Opus review APPROVED. **Hosted browser QA GREEN** on `isaac-demo-web.vercel.app` Ready-to-Export: coverage `29/33` from *Evidence Audit*; "What's left before export?" routes to the deterministic check with **no verdict** (record is PASS, assistant does not echo it); 3 §5.2 chips; `ROUTE_TO_CLI_NOTE` preserved.
- **Active authorized slice: P25.5 — ground + mount the Evidence context (EvidenceExplorer)**, delegated to Opus 4.8.
- The prior checkpoint block (below) is retained as history; its "P25.4 not yet authorized" and "HEAD = `5013d7c`" lines are superseded by this block.

### Session checkpoint — 2026-07-20
- **P25.1 and P25.2 are RELEASED**; **no later P25 slice has begun.**
- `main` is **clean and synchronized** with `origin/main`; **HEAD = `5013d7c`**; CI green on that HEAD.
- **P25.3 remains an intentional tombstone** (folded into P25.1).
- **P25.4 (Ground the Export context) is the next proposed slice but is NOT yet authorized** — no work until explicit user approval.
- **[SUPERSEDED 2026-07-20 — see correction below]** ~~Documented deployment concern (needs separate review): the hosted frontend is built with `VITE_API_BASE=http://127.0.0.1:8000`, so an HTTPS Vercel page cannot reach the HTTP-localhost API (mixed content). The deployed *shell* loads (past Vercel SSO), but the hosted frontend cannot fetch data on its own; there is effectively no live Railway backend wired to it.~~ (This claim was refuted by the 2026-07-20 reconciliation audit.)
- **[CORRECTION 2026-07-20 — reconciliation audit]** A local production build created without Vercel environment variables targeted localhost. The hosted Vercel deployment targets the Railway HTTPS API correctly. Previous checkpoint wording conflated the local preview bundle with the hosted production bundle. Evidence: the live `isaac-demo-web.vercel.app` bundle targets `…up.railway.app/api` (zero localhost request-base matches); Railway `/api/health` returns 200 at HEAD; CORS echoes the production origin; unauthenticated data calls correctly return 401. Authenticated *hosted production E2E* was verified GREEN on 2026-07-20 (reconciliation R5): the hosted `isaac-demo-web.vercel.app` frontend calls the Railway HTTPS API with authenticated 200 responses (experiments, memory files/concepts, graph status), zero localhost/CORS/mixed-content/console errors, and P25.1 live composer + P25.2 Guided-Prompts-Only behavior confirmed on the hosted build. See `docs/superpowers/plans/2026-07-20-slac-account-toolchain-reconciliation.md`.
- **Browser data QA method:** performed against a **byte-identical local preview** (`vite preview` of the same production build) + a **local backend**, NOT a live Railway-connected hosted frontend — because of the concern above. Composer/UI behavior is genuinely browser-verified on the shipped build; the hosted URL was verified only to the shell level.

Approval decisions — **RESOLVED by the 2026-07-20 decision-lock:**
- Q1 → **YES.** Add `'advisory'` to `AssistantSource`, **and** add a distinct **artifact/workflow-state** label so the five source categories (truth · evidence · advisory · artifact/workflow · Project Memory) are each honestly labeled. Keep `'git'` for history. (Exact enum spelling of the artifact/workflow label = a P25.0 finalization item.) (see §12)
- Q2 → **RESOLVED (mount set).** Prioritize the 4 record surfaces (Review Record, Complete Missing Fields, Evidence & File Preview, Ready to Export) **plus Project Memory where appropriate**. Do **NOT** mount on My Experiments, Load Materials, Settings, or Governance merely for visual consistency; such a screen gets the assistant only if P25.0 identifies specific useful inputs, deterministic outputs, and user value. (see §6, §13, §20)
- Q3 → **CONFIRMED.** Pure-frontend composer; zero new backend endpoint; zero truth-path change. (see §11)
- Q4 → **CONFIRMED.** Hard-remove the disabled free-text input; use honest `Guided Prompts Only` framing. (see §13)
- Q5 → **APPROVED.** P25.0 is the single design/spec gate before any P25 implementation. (see §23)

---

## Governing constraint (from arc item 8 — non-negotiable)

Phase 25 makes the assistant **genuinely grounded in real live state** while staying:
deterministic · guided-prompt driven · **NO LLM / NO freeform chat** · subordinate to the
deterministic core · source/provenance-labeled · unable to invent scientific values · unable to
validate · unable to silently mutate records · unable to bypass propose→stage→confirm.

The existing guard `hasVerdictLanguage()` and the required `answeredFrom` source label
(`apps/web/src/lib/assistant.ts:30-32`, `apps/web/src/components/AssistantPanel.tsx:38-42,61`) are
**preserved**. What P25 replaces is the static `ASSISTANT_SAMPLES` lookup
(`apps/web/src/lib/assistant.ts:61-179`) with a deterministic composer that reads state the screens
**already fetch** and renders it through fixed templates.

---

## 1. Purpose

Replace the assistant's 100%-static canned-copy table with a **deterministic, template-driven,
LLM-free composer** that answers guided-prompt clicks from the **real live state** already fetched
by each screen (validation blockers, pending/missing fields, evidence-audit findings, advisory
warnings, export readiness, evidence metadata, artifact/record status, and Project Memory
concepts / availability / provenance / drift). The assistant stops reciting fixtures and starts
describing *this* record — without ever becoming a validator, a chatbot, or a value generator.

## 2. User / scientist value

- The assistant's answers become **true for the record in front of the scientist** ("2 fields still
  block export: `$.assets[0].sha256`, `$.spectra[0].reduced_uri`") instead of generic prose that
  might not match the live audit.
- It points to the exact deterministic surface for every truth question, so the scientist always
  knows *where the real answer lives* (Validate / Evidence Trail / Complete Missing Fields).
- Honest degradation: when memory is unavailable or data is missing, it says so plainly rather than
  guessing — reinforcing the no-guessing contract the whole product is built on.

## 3. Mentor / demo value

- Removes the last "demo-looking, secretly static" surface in the app — directly satisfies the arc's
  governing principle ("This must actually work. No demo-looking UI that pretends a capability
  exists").
- Demonstrates a defensible **grounded-but-subordinate** assistant: it reads live truth, echoes it
  faithfully, and refuses to render a verdict — a concrete answer to "is your AI making things up?"
- Shows the two-plane discipline at the UI layer: truth answers cite truth endpoints; memory answers
  carry the "leads to verify — never a verdict" caveat.

## 4. Architectural value

- Introduces a reusable **`prompt → structured query → templated, provenance-labeled reply`** layer
  (the "grounding layer") that Phase 26 search reuses for its `query → results` rendering — per the
  architecture audit's explicit recommendation (`audit-architecture.md` §5 nuance).
- Keeps the composer a **pure function over already-fetched bundle data**: no new network calls, no
  new backend contract, no truth-path change. Deterministic and unit-testable in isolation.
- Hardens the verdict guard by running it over *composed* output (not just hand-written fixtures),
  making the "assistant never states a verdict" invariant structural rather than editorial.

## 5. Dependencies

- **Upstream (satisfied):** P24.10 shipped the separated-freshness `/api/graph/status` contract
  (`availability`, `integrity`, `memory_policy`, `indexed_sources`, fingerprints — `routes.py:548-600`,
  `types.ts` `ApiGraphStatus`). All grounding endpoints already exist and are consumed by the screen
  bundles (`api.ts` `getRecordBundle` 215-230, `getExportReadiness` 232-247, `getEvidenceBundle`
  249-266).
- **Downstream:** Phase 26 (Real Search) reuses this phase's grounding/provenance-rendering
  primitives. P25 must not pre-build search.
- **Blocking gate:** P25.0 design/spec approval by the user before any implementation slice.

## 6. Scope

In scope:
1. A pure, deterministic **assistant composer module** (new `apps/web/src/lib/assistantComposer.ts`)
   that maps `(screenContext, alreadyFetchedBundle)` → `{ reply, prompts }` via fixed templates.
2. **Per-screen guided-chip catalogs** grounded in that screen's live data.
3. **Free-text input removal** + "Guided prompts only" framing (arc item 8).
4. Wiring the composer into the **prioritized surfaces**: the record surfaces that host the panel
   today (Review, Export), the record surfaces that should host it (Evidence, Complete Missing
   Fields), **and Project Memory where appropriate** (memory-caveated).
5. **Excluded by default (decision-lock):** the assistant is **not** mounted on My Experiments, Load
   Materials, Settings, or Governance for visual consistency. Any such non-record screen is mounted
   **only** if P25.0 identifies specific useful inputs, deterministic outputs, and user value — an
   explicit, separately-approved addition, not part of P25-core.
6. Retiring the static `ASSISTANT_SAMPLES` table and migrating the dev-sanity guard.
7. Unit + screen-integration + regression tests; full verification; docs update; deploy gate.

Out of scope (see §7).

## 7. Non-goals

- **NO LLM, NO freeform chat, NO natural-language parsing** (arc item 8; back-burner "LLM/freeform
  assistant"). The free-text box is removed, not wired.
- **NO new scientific values** — the composer only echoes values already present in fetched state.
- **NO validation / verdict** — the assistant never renders PASS/FAIL/validity; it routes to the
  deterministic surfaces.
- **NO record mutation** — the composer is read-only; it never writes answers or bypasses the
  Complete Missing Fields propose→stage→confirm flow (that flow stays in `GuidedPrompt.tsx`).
- **NO new backend endpoint, NO truth-path change** (recommended; Q3). Truth core stays deterministic
  and Graphify-free.
- **NO search** (Phase 26). The no-fake-search regression tests stay untouched.
- **NO Graphify-as-truth**, no real/private data, no second domain, no new slash commands.

## 8. Current baseline (cite files)

- **Assistant component:** `apps/web/src/components/AssistantPanel.tsx` — props
  `{ reply, prompts, availability, note? }` (`:13-20,31`); guard applied to active text
  (`:38-42`); `answered from:` label required (`:61`); chips are native `<button>` with `aria-pressed`,
  `disabled={!p.answer}` (`:70-82`); **disabled free-text box + send** with `aria-hidden` wrapper
  (`:85-98`); subordinate caption (`:100`).
- **Assistant lib:** `apps/web/src/lib/assistant.ts` — `ASSISTANT_SOURCES` (5) (`:14-20`);
  `hasVerdictLanguage()` (`:30-32`); `ROUTE_TO_CLI_NOTE` (`:35`); `MEMORY_UNAVAILABLE_CAVEAT` (`:41-42`);
  `SUBORDINATE_CAPTION` (`:52-53`); `FREEFORM_NOT_WIRED` (`:55-56`); **`ASSISTANT_SAMPLES`** static
  table (`:61-179`); DEV sanity loop over samples (`:183-200`).
- **Types:** `apps/web/src/lib/types.ts` — `MemoryAvailability` (`:158`), `AssistantSource` =
  `'schema'|'audit'|'git'|'graph'|'files'` (`:162`), `AssistantMessage` (`:164-168`),
  `SuggestedPrompt` (`:170-176`), `ApiGraphStatus` (separated-freshness fields).
- **Mount points TODAY (only 2):** `RecordWorkbench.tsx:173-177` (`ASSISTANT_SAMPLES.review`,
  `availability={graph.availability}`); `ExportReadiness.tsx:301-306` (`ASSISTANT_SAMPLES.export` +
  `ROUTE_TO_CLI_NOTE`). **`EvidenceExplorer.tsx`, `GuidedCompletion.tsx`, `ExperimentsHome.tsx`,
  `LoadMaterials.tsx`, `ProjectMemory.tsx` do NOT mount the panel** (verified by grep — only
  `GuidedCompletion.tsx:2` imports `assistant.css`). The `ASSISTANT_SAMPLES.evidence` context exists
  but is currently unmounted.
- **Grounding endpoints (all live):** validate `{ok, errors:[{path,message}], schema, dry_run}`
  (`routes.py:347-381`); pending; audit `{records, text, message}` + coverage
  (`routes.py:387-399`, `serialize.audit_to_dict`); warnings (`routes.py:405+`); evidence
  (`routes.py:438-449`); draft; artifacts (`routes.py:487-509`); experiment status
  (`workspace.py:167-184`); graph/status (`routes.py:548-600`); memory concepts/files/file/concept
  (`routes.py:628-724`, every response carries `MEMORY_NOTE`).
- **Composite bundles already fetched by screens:** `getRecordBundle` / `getExportReadiness` /
  `getEvidenceBundle` (`api.ts:215-266`) — the composer reads these, adds **zero** new fetches.
- **Tests today:** `apps/web/src/__tests__/assistant.test.tsx` (11) — verdict-absence, guard
  substitution, no hardcoded field-count claims, sourcing, free-form-not-wired.

## 9. Files likely touched

Frontend only:
- `apps/web/src/lib/assistantComposer.ts` — **new** pure composer module.
- `apps/web/src/lib/assistant.ts` — remove `ASSISTANT_SAMPLES` + its DEV loop (last slice); keep
  guard, sources, captions, caveats; possibly extend `ASSISTANT_SOURCES`.
- `apps/web/src/lib/types.ts` — possibly extend `AssistantSource` (Q1); add composer input/output
  types.
- `apps/web/src/components/AssistantPanel.tsx` — remove free-text block; add "Guided prompts only"
  framing; add `aria-live` on the reply region.
- `apps/web/src/components/assistant.css` — remove free-form styles; minor layout for guided-only.
- `apps/web/src/screens/RecordWorkbench.tsx`, `ExportReadiness.tsx`, `EvidenceExplorer.tsx`,
  `GuidedCompletion.tsx` — wire composer to already-fetched bundle. (Q2: `ExperimentsHome.tsx`,
  `LoadMaterials.tsx`, `ProjectMemory.tsx`, and `AppShell.tsx` if the panel expands to top-level
  screens.)
- `apps/web/src/__tests__/assistant.test.tsx` + new test files (see §16).
- `docs/ui-handoff/ai-assistant-and-graphify.md` (and cross-refs) — doc update.

## 10. Files that must NOT be touched

- `schema/isaac_record_v1.json` and all of `src/isaac_records/*` (`official.py`, `draft_validator.py`,
  `export.py`, `audit.py`, `cli.py`, `models.py`, `ids.py`, `complete.py`, `review.py`, `extract/*`) —
  the truth path. **Zero backend change** under the recommended design (Q3).
- `apps/api/isaac_api/*` (routes, memory, workspace, auth, serialize) — no new endpoints in P25.
- The no-fake-search regression tests (`help-and-honesty.test.tsx`, `memory-status.test.tsx`,
  `memory-sources.test.tsx`, `memory-concepts.test.tsx` search assertions) — Phase 26 owns those.
- `docs/mentor-brief.md`, `docs/final-deliverable-outline.md`, `docs/paper-notes.md`,
  `docs/mentor-decisions.md` — the Documentation plan owns those stale-doc fixes.
- The propose→stage→confirm flow in `components/GuidedPrompt.tsx` — the assistant advises around it,
  never replaces or drives it.

## 11. Data flow — the deterministic answer-composer contract

**Contract:** `compose(context: ScreenContext, state: GroundingState) → { reply, prompts }`, a
**pure, synchronous, side-effect-free** function. It performs **no fetching** — it receives the
bundle objects the screen already loaded via `useFetch` + `api.getRecordBundle` / `getExportReadiness`
/ `getEvidenceBundle` / graph status / memory endpoints.

Three-stage pipeline (the reusable "grounding layer"), designed so Phase 26 search reuses stages 2–3:

1. **Prompt → structured query.** Each guided chip carries a fixed `GroundedQuery` descriptor:
   `{ intent, plane, resolver }` where `intent` is an enum (e.g. `blockers`, `missing-fields`,
   `coverage`, `advisory`, `field-provenance`, `export-readiness`, `record-status`,
   `memory-concepts`, `memory-availability`, `memory-provenance`, `indexed-source-drift`). No natural
   language is parsed — the descriptor is chosen at authoring time, not derived from user text.
2. **Structured query → resolved values.** The `resolver` is a pure selector over `GroundingState`
   that extracts already-present values (counts, paths, messages, names, statuses). It never derives,
   formats scientific quantities, or computes a verdict. Missing data → an explicit "unavailable"
   marker, never a fabricated value.
3. **Resolved values → templated reply.** A fixed template string interpolates the resolved values
   into a short, source-labeled `AssistantMessage`. Every message is guard-checked
   (`hasVerdictLanguage`) as a structural backstop before render.

`GroundingState` per context = the exact bundle the screen holds:
- Review (RecordWorkbench): record detail, draft groups, pending, evidence, `graph` status.
- Export (ExportReadiness): validate result, audit/coverage, warnings, artifacts, `graph` status.
- Evidence (EvidenceExplorer): evidence entries, source previews, artifacts, `graph` status.
- Complete Missing Fields (GuidedCompletion): pending fields, draft, validate (read-only; the answer
  never submits).
- (Q2) My Experiments: experiment summaries/status list. Load Materials: demo/upload state.
  Project Memory: graph status, concepts, files.

**Loading/error states:** if the underlying bundle is `loading` or `error`, the composer returns a
degraded reply that mirrors the screen state ("that data isn't loaded yet" / defers to `BackendDown`)
and disables chips whose data is not present — reusing the existing `disabled={!p.answer}` pattern.

## 12. API / contracts

- **Backend contracts:** UNCHANGED. P25 adds no route and modifies no response shape (Q3). Every value
  the composer echoes already ships in an existing endpoint payload.
- **Composer output type:** reuses `AssistantMessage` / `SuggestedPrompt` (`types.ts:164-176`) so
  `AssistantPanel` props are unchanged (`{ reply, prompts, availability, note? }`). This keeps the
  component contract stable and the change localized to *how* `reply`/`prompts` are produced.
- **Source-label taxonomy** (rendered as `answered from: <source>`). The 2026-07-20 lock requires the
  taxonomy to clearly distinguish **five source categories** — truth state · evidence · advisory ·
  artifact/workflow state · Project Memory — plus an auxiliary history label:

  | Source category | Meaning | `answeredFrom` label | Backing endpoint(s) |
  |---|---|---|---|
  | **Truth state** | schema validity gate, deterministic checks | `schema` | `/validate`, official schema |
  | **Truth state (reporting)** | evidence coverage counts (info, not a verdict) | `audit` | `/audit` |
  | **Evidence** | per-field provenance, cited source lines, draft field origin | `files` | `/evidence`, `/source-preview`, `/draft` |
  | **Advisory** | soft non-gating warnings | `advisory` *(new)* | `/warnings` |
  | **Artifact / workflow state** | record/experiment status, exported artifacts, export-readiness | `workflow` *(new — exact spelling set at P25.0)* | `/experiments/{id}`, `/artifacts`, `/export` readiness |
  | **Project Memory** | concepts, availability, provenance, drift | `graph` | `/graph/status`, `/memory/*` |
  | **History** *(auxiliary)* | "what changed" | `git` *(existing, low-use)* | git-derived docs |

  **Q1 decision (LOCKED):** the pre-P25 enum (`schema|audit|git|graph|files`) had no dedicated
  **advisory** label (warnings would be mislabeled `schema`) and no **artifact/workflow-state** label
  (status/artifacts/export-readiness would be conflated with truth). The lock adds **`'advisory'`**
  and a distinct **artifact/workflow-state** label (proposed `'workflow'`; final spelling is a P25.0
  item), keeping `git` for history. Mapping advisory/workflow onto `files`/`schema` is rejected — it
  muddies the plane/category distinction the guard and UX depend on.

- **Value-echo restrictions (hard rules):**
  - MAY echo values **verbatim** that already exist in fetched state: pending-field paths, validate
    `errors[].path` / `errors[].message`, coverage `N / N`, advisory warning codes/messages, concept
    names/anchors, `availability`/`memory_policy`/`indexed_sources` status strings, a draft field's
    stored value + its `source_file`/`locator`.
  - MUST NOT synthesize, reformat, unit-convert, round, or derive any scientific value; MUST NOT
    invent hashes, URIs, paths, descriptors, uncertainties, QC, timestamps.
  - When echoing a scientific value it MUST attribute the source and MUST NOT imply it is validated.
  - MUST NOT surface the boolean `validate.ok` as a verdict; it may state a **count** of blockers and
    route to Validate ("2 paths still block export — open Validate for the deterministic verdict"),
    never "PASS/FAIL/valid".

## 13. UI behavior

### Screen contexts + guided chips (per context)

Each context ships a small fixed chip catalog. Chips are authored, not generated; their *answers* are
composed live. Representative catalogs (final wording set at P25.0).

**Prioritized surfaces (decision-lock):**
- **Review Record** (RecordWorkbench): "Explain the fields that need me" (→ live pending paths),
  "Trace a field to its source" (→ evidence for selected field), "What's left before export?"
  (→ blocker count from validate). "Is this record valid yet?" stays a **routed** truth chip.
- **Complete Missing Fields** (GuidedCompletion): "Which fields block export and why?" (→ live pending
  + validate paths), "What happens if I leave this missing?" (→ explains honest-missing). Answers are
  **advisory only** — never submit; the confirm/skip flow stays in `GuidedPrompt.tsx`.
- **Evidence / File Preview** (EvidenceExplorer): "Is the sidecar an official artifact?" (routed to
  the D1 convention note), "What does coverage mean here?" (→ live `N / N` from audit), "Why keep the
  file_listing and my confirmation both?" (→ echoes both evidence entries for the selection).
- **Ready to Export** (ExportReadiness): "What does the verdict mean here?" (routed), "Is coverage the
  same as valid?" (→ explains, echoes live coverage), "Explain the advisory warning" (→ echoes live
  warning codes). Keeps `ROUTE_TO_CLI_NOTE`.
- **Project Memory** (where appropriate): "Where do these leads come from?" (→ provenance/anchor),
  "Is memory current?" (→ echoes `memory_policy`/`indexed_sources`/drift, non-alarming), "Why is
  memory unavailable?" (→ honest availability). All carry the memory caveat (below).

**Excluded by default (decision-lock — NOT mounted for visual consistency):** My Experiments, Load
Materials, Settings, Governance. Each is mounted **only** if P25.0 identifies specific useful inputs,
deterministic outputs, and user value for that screen. Illustrative catalogs to weigh **at P25.0**
(not authorized here): My Experiments — "What needs me next?" (→ statuses/pending counts across the
queue); Load Materials — "Why is upload blocked here?" (→ echoes the 403 governance reason verbatim).

### Allowed vs forbidden input types

- **Allowed:** clicking a guided chip (primary and only input). Keyboard activation of chips via
  native `<button>` semantics.
- **Forbidden / removed:** free-text entry. Per arc item 8 the disabled `<input>`+send block
  (`AssistantPanel.tsx:85-98`) is **removed** (Q4), replaced by a single honest line: **"Guided
  prompts only — the assistant answers the suggested questions above."** No hidden/disabled input
  remains (it currently reads as an unfinished feature; arc item 8 says replace it with honest
  framing).

### No-verdict vocabulary guard

- `hasVerdictLanguage()` is preserved and now runs over **composed** replies (not just fixtures) as a
  structural backstop (`AssistantPanel.tsx:38-42`). Templates are authored guard-clean; the guard is
  the safety net. If a composed reply (e.g. an echoed `validate` message containing "invalid against")
  would trip the guard, the panel substitutes the routing message and drops the source doc — existing
  behavior, now exercised against live data.

### Memory-caveat rules

- `availability === 'unavailable'` → memory chips answer with `MEMORY_UNAVAILABLE_CAVEAT`
  ("answered from source files directly"), never an error/red state.
- Memory available but `memory_policy` / `indexed_sources` is `stale`/`unknown` → append a quiet
  caveat ("indexed sources may be behind the working tree — leads to verify"). Non-alarming, matches
  the P24 "no red, no fake counts" discipline.
- Every memory-sourced answer carries the "leads to verify — never a verdict" note (the
  `MEMORY_NOTE` analogue).

### Unknown / unavailable behavior

- Missing value → say it is missing/absent, never guess.
- Bundle in `loading` → chip disabled or "that data isn't loaded yet."
- Bundle in `error` → defer to the screen's `BackendDown` state; the assistant never fabricates rows.

### Answer length + density rules

- Reply: 1–3 short sentences, one primary source label, optional one caveat line. No walls of text.
- Chip label: ≤ ~44 chars, verb-first, one question.
- At most one echoed value list per reply (e.g. up to the first N pending paths, then "…and K more"),
  never a full dump.

### Keyboard + accessibility behavior

- Chips remain native `<button>` with `aria-pressed` (no custom `onKeyDown`) — consistent with the
  repo's a11y precedent (`ProjectMemory.tsx` comments; `memory-concepts.test.tsx`).
- The reply region gains `aria-live="polite"` so chip-driven answer changes are announced.
- `section aria-label="Assistant (advisory)"` retained; `answered from:` remains visible text, not
  only color. Removing the free-text box simplifies the tab order and removes the `aria-hidden`
  input.

### Copy-review checkpoints

- **CP-A (P25.0):** review every template + chip label for tone (subordinate), guard-cleanliness,
  correct source label, and no implied verdict — before any code.
- **CP-B (per context slice):** review the rendered live answers against a fixture bundle.
- **CP-C (P25.10):** final copy sweep across all contexts + the "Guided prompts only" framing.

## 14. Security / governance constraints

- Frontend-only; no new data exposure. The composer echoes only what endpoints already return to the
  same authenticated client — no new fields, no new sources.
- No LLM → no external model sees any state (nothing leaves the browser/API boundary).
- Governance walls untouched: uploads stay 403; source preview stays allowlisted; memory stays
  metadata/provenance-only.
- Truth path stays deterministic and Graphify-free; memory plane stays stdlib-only. P25 touches
  neither backend plane (Q3).
- No real/private data; synthetic demo only. Nothing under `examples/` read or staged.

## 15. Risks

- **R1 — Echoing live `validate` strings could leak verdict language.** Mitigation: templates surface
  *counts + paths + routing*, never `ok`; guard runs over composed output; dedicated test feeds a
  verdict-ish `validate` payload and asserts substitution.
- **R2 — Mounting on non-record screens changes AppShell layout** (rightPanel exists only on
  `record`/`evidence` variants per the frontend audit). Mitigation: Q2 — either add a deliberate
  layout slice or defer top-level contexts; ship record surfaces first.
- **R3 — Scope creep across 7 screens.** Mitigation: one context per slice, each independently
  shippable; top-level contexts are optional/deferrable.
- **R4 — Sensitive test change** (free-text removal touches `assistant.test.tsx` "free-form-not-wired").
  Mitigation: a dedicated slice (P25.2) with rationale comments; replace with a "guided-only" assertion,
  never silently delete.
- **R5 — Drift/memory caveat wording reading as an error.** Mitigation: CP-B/CP-C copy review + a test
  asserting no error/red styling on memory-unavailable/stale answers.
- **R6 — Hosted state is a single shared ephemeral demo experiment.** The grounded assistant will
  describe that shared demo record accurately; acceptable for the synthetic demo. Documented, not a
  blocker.

## 16. Tests

- **Unit — composer (new `assistantComposer.test.ts`):** for each context, given a fixture
  `GroundingState` → assert exact `{reply, prompts}`: value-echo correctness (paths/counts/messages
  echoed verbatim), guard-cleanliness, no fabricated values, missing-value honesty, memory-unavailable
  caveat, drift caveat, source-label correctness per plane.
- **Unit — verdict resilience:** feed a `validate` payload whose `errors[].message` contains
  "invalid against"/PASS/FAIL; assert the composed reply is guard-substituted/routed, never echoed raw.
- **Screen integration (extend `live-screens.test.tsx` / `completion-export.test.tsx` /
  `evidence.test.tsx`):** each mounting screen renders the **composed** reply from a live bundle
  fixture; backend-down → honest state (no fake reply); memory-unavailable → caveat shown, no red.
- **Regression (`assistant.test.tsx`, updated):** guard still strips; **no free-text box**; "Guided
  prompts only" framing present; `answered from:` present on every reply; no hardcoded field-count
  claims that could contradict a live audit; DEV sanity now runs over composer fixtures.
- **Invariants untouched:** no-fake-search tests unchanged; `no-vertical-rail` unchanged; backend
  suite unchanged (run to confirm 461 still pass — proves truth path untouched).

## 17. Verification

- `cd apps/web && npx vitest run` → all frontend tests pass (137 baseline + new).
- `cd apps/web && npm run build` → typecheck + build clean.
- `.venv/bin/pytest` → backend 461 pass **unchanged** (evidence that P25 touched no backend/truth
  path).
- Manual QA checklist per context: click each chip with a live backend, confirm the answer matches the
  record's real state; confirm memory-unavailable and backend-down degrade honestly; confirm no
  verdict text ever renders; confirm no free-text box.
- Report the exact commands + results; never claim success without them.

## 18. Deployment impact

- Frontend-only change → Vercel redeploys on push; no Railway/backend redeploy needed; no env-var
  change. The hosted assistant becomes grounded in the hosted (shared, ephemeral, synthetic-demo)
  workspace's real state. Deploy gate = frontend build green + manual QA checklist on the preview URL.

## 19. Documentation impact

- Update `docs/ui-handoff/ai-assistant-and-graphify.md` to describe the grounded composer, the
  three-stage grounding layer, the source-label taxonomy, and the "Guided prompts only" framing.
- Cross-reference `docs/ui-handoff/validation-audit-warning-model.md` for the routing behavior.
- Note the `ASSISTANT_SAMPLES` retirement. **Do not** touch the stale docs owned by the Documentation
  plan (§10).

## 20. Bite-sized slices

Each slice: objective · files touched · files forbidden · model · acceptance · tests · report · commit · stop.

> **First-code-slice reconciliation (decision-lock 2026-07-20):** the authoritative first *code*
> slice is **P25.1 = deterministic composer skeleton + source-label rendering on RecordWorkbench**
> (one screen, behind the existing verdict guard, fully unit-tested, no new backend contract) — this
> matches the master roadmap §14 and the decision-lock. The earlier "pure unwired scaffold then wire"
> split has been folded into P25.1 (the pure `compose()` module is still TDD'd first, then wired to
> RecordWorkbench within the same slice). Nothing here is authorized until P25.0 is approved.

- **P25.0 — Design/spec approval gate (DESIGN ONLY — the single gate before implementation).**
  - Objective: produce the P25 design mini-spec in `docs/superpowers/specs/2026-07-20-phase-25-grounded-assistant-design.md`.
    It must define (per the decision-lock): the finalized deterministic composer contract +
    `GroundedQuery`/`GroundingState` shapes; the **5-category source-label taxonomy** (truth · evidence
    · advisory · artifact/workflow · Project Memory) incl. the exact new enum spellings (`advisory`,
    artifact/workflow label); exact **per-screen contexts**; **guided-prompt chip catalogs**; **answer
    templates**; **allowed input fields**; **value-echo / no-verdict rules**; **caveat rules** incl.
    memory-policy & indexed-source caveats; **unavailable & unknown behavior**; **copy-density limits**;
    **accessibility behavior**; **tests**; the **bite-sized P25.1+ slices**; **approval questions**; and
    **visual/copy examples** for review. No production code.
  - Files touched: the spec doc only. Forbidden: everything under `apps/`, `src/`, `schema/`.
  - Model: Opus (design/UX/governance-sensitive) + Opus product-copy review. Acceptance: user approves
    the spec. Tests: none (doc). Report: spec path + the finalized taxonomy/chips/templates. Commit:
    docs-only, on approval. **STOP for user review — no implementation until approved.**

- **P25.1 — Deterministic composer skeleton + source-label rendering on RecordWorkbench. ✅ RELEASED 2026-07-20** — commits `ee60367` (skeleton) · `83aa5b8` (hardening: composer never renders `undefined`/`null`; pending count/list agree) · `7e5a86c` (memory-snapshot CI fix); CI-green on `origin/main`; browser-verified (Record Workbench).
  - Objective: add `lib/assistantComposer.ts` (pure `compose()` + resolvers) + composer types + the
    source-label enum extensions (`advisory` + artifact/workflow label), TDD'd as a pure module, **then
    wire it into RecordWorkbench** (replacing `ASSISTANT_SAMPLES.review`) so the assistant renders
    live, source-labeled answers on that one screen behind the existing verdict guard. No new backend
    contract. Other screens keep `ASSISTANT_SAMPLES` for now.
  - Files: `lib/assistantComposer.ts` (new), `lib/types.ts`, `lib/assistant.ts` (enum), `lib/labels`
    if needed, `screens/RecordWorkbench.tsx`; tests. Forbidden: other screens, backend, truth path.
    Model: Opus. Acceptance: composer fully unit-tested against fixtures; RecordWorkbench chips answer
    from live pending/evidence/blocker state; guard-clean; CP-B. Tests: `assistantComposer.test.ts` +
    extend `live-screens.test.tsx`. Report: module surface + coverage + RecordWorkbench behavior.
    Commit: after tests green. Stop: review before wiring further screens.

- **P25.2 — Free-text removal + "Guided prompts only" framing (arc item 8). ✅ RELEASED 2026-07-20** — commits `8eab6ba` (removal + guided-only note + `aria-live`) · `5a0c049` (memory-snapshot CI fix); CI-green on `origin/main`; browser-verified (Record Workbench + Ready to Export).
  - Objective: remove the disabled input/send block from `AssistantPanel.tsx` + `assistant.css`; add
    the guided-only line; add `aria-live` on the reply region. Update `assistant.test.tsx`
    (free-form-not-wired → guided-only) with rationale comments.
  - Files: `components/AssistantPanel.tsx`, `components/assistant.css`, `__tests__/assistant.test.tsx`,
    `lib/assistant.ts` (retire `FREEFORM_NOT_WIRED`, add guided-only constant). Forbidden: composer,
    backend. Model: Sonnet (mechanical + copy). Acceptance: no input in DOM; guided-only text present;
    a11y intact. Tests: updated regression. Report: diff + test delta. Commit: yes. Stop: review.

- **P25.3 — (FOLDED INTO P25.1.)** RecordWorkbench grounding is now delivered together with the
  composer skeleton in P25.1 per the decision-lock's first-code-slice definition. This ID is retained
  as a tombstone so P25.4–P25.8 keep their numbers; there is no separate P25.3 work.

- **P25.4 — Ground the Export context (ExportReadiness). ✅ RELEASED 2026-07-20 — commit `e0e3d1a`; 194 frontend tests, CI green, hosted QA green.**
  - Objective: replace `ASSISTANT_SAMPLES.export` with `compose('export', bundle)`; keep
    `ROUTE_TO_CLI_NOTE`. Coverage/warnings echoed live; verdict routed. Files:
    `screens/ExportReadiness.tsx`; test. Model: Opus. Tests: extend `completion-export.test.tsx`. CP-B.
    Report + commit + stop.

- **P25.5 — Ground + mount the Evidence context (EvidenceExplorer). ✅ RELEASED 2026-07-21 — commit `5600961`; 222 frontend tests, CI green (run `29798842384`), deployed & served-bundle-verified. Independent review substituted by orchestrator self-review (org spend limit); full interactive hosted QA deferred (spend-limit risk) — see the 2026-07-21 checkpoint.**
  - Objective: mount `AssistantPanel` on `EvidenceExplorer` (new mount) and wire
    `compose('evidence', getEvidenceBundle)`. Files: `screens/EvidenceExplorer.tsx`; test. Model: Opus.
    Acceptance: panel appears below the Evidence Trail (truth above advisory ordering preserved), answers
    echo live coverage/evidence. Tests: extend `evidence.test.tsx`. CP-B. Report + commit + stop.

- **P25.6 — Ground + mount the Complete Missing Fields context (GuidedCompletion). ✅ RELEASED 2026-07-21 — feature commit `a0446fe` + served-snapshot regen `5b2fb3d`; tsc clean, 249 frontend tests + 461 Python tests, CI green (run `29804048533`), Vercel bundle serves all three chips + Railway healthy at `5b2fb3d`. Separate Opus 4.8 independent review: APPROVE (0 Critical/Important).**
  - Objective: mount the panel and wire `compose('complete', {detail, pending, selectedPendingId?})` — **advisory
    only, never submits**. (Spec §5.4 decision Q-D `{detail, pending}`-only supersedes this card's earlier
    `{pending, draft, validate}` wording — no validate/audit/graph fetch added.) Files:
    `screens/GuidedCompletion.tsx`, `lib/assistantComposer.ts` + tests. Model: Opus. Acceptance: answers
    describe pending fields + route the does-it-block truth question to Validate; confirm/skip flow in
    `GuidedPrompt.tsx` untouched. `availability='available'` avoids the spec-§6-flagged-false memory caveat
    (memory-line rework deferred to P25.7). Tests: extended `completion-export.test.tsx` +
    `assistantComposer.test.ts`. CP-B. Released; **P25.7 (Project Memory) is next**.

- **P25.7 — Project Memory context (PRIORITIZED — where appropriate). ✅ RELEASED 2026-07-21 — commit `bdd590c`; 294 frontend tests / 19 files, `tsc -b` + `vite build` clean, CI green (run `29807075500`), Vercel bundle `index-DjSM7pbq.js` serves all three memory chips + Railway healthy at `bdd590c`. Served snapshot regenerated in-commit (202 unchanged). Separate Opus 4.8 independent review: REQUEST CHANGES (1 Important dup-sentence) → fixed → APPROVE-clean. Interactive hosted QA deferred (no browser tool this session).**
  - Objective: mount a grounded, memory-caveated assistant on `ProjectMemory`, wiring
    `compose('memory', graph)` over the already-fetched `GET /api/graph/status` (no new fetch). Files:
    `lib/assistantComposer.ts`, `lib/assistant.ts`, `components/AssistantPanel.tsx`,
    `screens/ProjectMemory.tsx`, `screens/GuidedCompletion.tsx` + tests (new `memory-composer.test.ts`).
    Model: Opus. Four axes stated separately (§6); available → 3 chips, unavailable → 1 replacement chip.
    Also resolved the two deferred P25.6 copy items (caveat rewrite; optional `availability` prop). CP-B.
    Released; **P25.9 is next** (P25.8 excluded).

- **P25.8 — (NOT AUTHORIZED by default) Non-record screens: My Experiments / Load Materials.**
  - Status: **excluded by the 2026-07-20 decision-lock** — the assistant is not mounted on My
    Experiments, Load Materials, Settings, or Governance merely for visual consistency. This slice runs
    **only** if P25.0 explicitly identifies specific useful inputs, deterministic outputs, and user
    value for one of these screens, and the user approves that addition separately.
  - If approved: mount grounded assistant on the named screen(s); may require an AppShell layout slice
    for the `full` variant. Files: `screens/ExperimentsHome.tsx` / `screens/LoadMaterials.tsx`,
    `components/AppShell.tsx`, tests. Model: Opus. Acceptance: layout intact, answers grounded in real
    queue/demo state. Report + commit + stop.

- **P25.9 — Retire `ASSISTANT_SAMPLES` + migrate the DEV sanity guard.**
  - Objective: delete the static table and its DEV loop from `lib/assistant.ts`; migrate the sanity
    check to run over composer outputs/fixtures. Files: `lib/assistant.ts`, tests. Model: Sonnet.
    Acceptance: no dead static table; guard/sanity still enforced. Tests: green. Report + commit + stop.

- **P25.10 — Full verification + docs + deployment gate.**
  - Objective: run full frontend + backend suites, build, CP-C copy sweep, doc update
    (`docs/ui-handoff/ai-assistant-and-graphify.md`), preview-URL QA. Files: docs + any final test
    fixes. Model: Fable verifies; Sonnet applies doc/test fixes. Acceptance: all §17 checks pass;
    backend 461 unchanged. Report: full verification block. Commit + **final phase stop gate**.

## 21. Model / subagent assignment

- **Orchestrator (Fable 5 when available, else Opus 4.8):** orchestration, planning, authoring this
  planning markdown, review of every slice diff against invariants, verification, gate enforcement.
  **Never implements production code.**
- **Opus 4.8 (implementation):** P25.0 design + product-copy review; the composer + RecordWorkbench
  grounding (P25.1); all grounding/UX-sensitive wiring slices (P25.4–P25.7) — grounding correctness,
  verdict-guard integrity, and provenance labeling are design-critical.
- **Sonnet 5 (implementation):** mechanical slices — free-text removal/CSS (P25.2), static-table
  retirement (P25.9), doc + test formatting (P25.10).

## 22. Acceptance criteria (phase-level)

1. The assistant answers guided prompts from **live, per-record state** — no `ASSISTANT_SAMPLES`
   remains.
2. **No LLM, no freeform input** anywhere; "Guided prompts only" framing shipped.
3. Every reply carries a correct `answered from:` label from the taxonomy; memory answers carry the
   leads-to-verify caveat; the verdict guard never lets a verdict render.
4. The composer invents no values and echoes only fetched state; missing/unavailable data degrades
   honestly.
5. Zero backend / truth-path change (backend 461 unchanged); frontend suite + build green.
6. The grounding layer is structured `prompt → structured query → templated reply` and is documented
   as reusable by Phase 26.

## 23. Stop / approval gates

- **P25.0 is the single design/spec approval gate.** No implementation slice begins until the user
  approves the P25.0 spec. (Q1–Q5 are already resolved by the 2026-07-20 decision-lock; P25.0
  finalizes the remaining details — chip wording, templates, exact enum spellings.)
- Every slice ends at a review stop point; the orchestrator reviews the diff before the next slice.
- The non-record-screen mount (P25.8: My Experiments / Load Materials) is **excluded by default** and
  runs only if P25.0 justifies it and the user approves separately — it never blocks the phase.
- Final phase stop at P25.10 before any Phase 26 work.

## 24. Deferred items

- Phase 26 Real Search (reuses this grounding layer) — not started here.
- LLM / freeform assistant — permanently back-burnered (arc list).
- A backend `/assistant/context` aggregation endpoint — only if a future need appears; P25 is
  pure-frontend.
- Related-records / record-similarity answers — back-burnered.
- Non-record-screen assistant contexts (P25.8: My Experiments / Load Materials) — excluded by default
  unless P25.0 justifies specific value; Settings / Governance not in scope.
- History (`git`)-plane chips beyond what already exists — optional, low priority.

## 25. Explicit questions for the user — RESOLVED (2026-07-20 decision-lock)

1. **Q1 — Source-label enum.** ✅ **Add `'advisory'`** and a distinct **artifact/workflow-state**
   label; keep `'git'` for history (5-category taxonomy). Exact artifact/workflow spelling = P25.0.
2. **Q2 — Screen coverage.** ✅ Prioritize the **4 record surfaces + Project Memory where
   appropriate**; **exclude** My Experiments / Load Materials / Settings / Governance unless P25.0
   identifies specific useful inputs, deterministic outputs, and user value.
3. **Q3 — Pure-frontend composer.** ✅ **Confirmed** — zero new backend endpoint, zero truth-path
   change.
4. **Q4 — Free-text removal.** ✅ **Confirmed** — hard-remove the disabled input; `Guided Prompts
   Only` framing.
5. **Q5 — Gate.** ✅ **Approved** — P25.0 is the single gate before any P25 implementation.

**Remaining for P25.0 (not yet decided):** final chip wording, answer templates, the exact
artifact/workflow enum spelling, and copy-density exact limits.
