# Phase 29 — Assistant Experience (plan)

Status: **P29.0 audit + contract complete (2026-07-22).** Active slice: **P29.1 (next).**
Baseline: `main @ 414b633` · CI green · Railway `414b633` synthetic-only · Vercel 200 · backend 806 · frontend 408.

Derived from the P29.0 read-only audit (targeted `rg` + `Read` by the orchestrator — no agent swarm, per the mandate's "prefer rg / don't swarm / ≤5 agents per session"). Obeys the master ledger; does not create a competing master plan.

**Governing principle:** the assistant is another controlled VIEW + interaction surface over the same authoritative Workspace state — never a second record store, hidden truth model, stale chat cache presented as current, alternate classifier/validator, unrestricted chatbot, autonomous decision-maker, or a route around human confirmation. Manual fields, workflow, evidence, export readiness, assistant, search, and future retrieval must all agree on ONE current record revision.

**Hard constraint:** NO external LLM. The agent is a bounded deterministic state machine over typed intents + existing backend tools. Truth-plane (`schema/`, `official.py`, `draft_validator.py`, `export.py`, `audit.py`, `cli.py`) stays FROZEN; `complete.py` is a non-truth authoring module (extendable with care).

---

## 1. Current architecture (P29.0 map)

- **Assistant = a pure composer + a static panel.** `apps/web/src/lib/assistantComposer.ts` is a PURE, synchronous, side-effect-free function over already-fetched bundle data (counts, blocking paths, cited sources) → short `answered from:`-labeled `AssistantMessage`s. It NEVER fetches, mutates, validates, or states PASS/FAIL. `AssistantPanel.tsx` renders the composed reply + guided prompts (each with a STATIC pre-baked `answer`) + a `hasVerdictLanguage()` structural guard + memory-availability caveat + subordinate caption. Wired into 5 screens (review/export/evidence/complete/memory) via `assistantComposer` (P25.1–P25.7).
- **No backend assistant/context endpoint.** `rg` finds none. The assistant is entirely frontend, grounded in whatever bundle the mounting screen already holds.
- **No mutation from the assistant.** Guided prompts only swap in static sample text; there is no compose→stage→confirm→mutate path. The only mutations in the app are the manual `POST /answers`, `POST /export`, and `POST /edit` (P28.3).
- **Grounding sources today:** the composer echoes bundle counts/paths/sources (`SOURCE_LABELS`: Schema Rules / Evidence Audit / Evidence & Sources / Advisory Checks / Workflow & Artifacts / Project Memory / Project History). Project Memory availability is surfaced honestly (P24.10/P25.7 corrected wording — no false "source lookup").
- **Does NOT yet use P28 contracts.** The composer predates Phase 28: it does not consume `workflow` (current step, reopened reasons, next missing field) or `evidence-classification` (supported/insufficient/conflicting/inferred_candidate/unknown). Surfacing those deterministically is the core P29.3 work.
- **Version behavior:** the record bundle (`detail`) carries `version`/`workflow`/`artifact` (P28); `evidence-classification` is a separate endpoint bound to `record_rev`; `getEvidenceBundle` folds detail + classification (P28.5) and the UI shows a stale affordance when `detail.version` rev != `classification.record_rev`. So per-bundle coherence is already partly checked.
- **Degraded:** `FetchStates` (BackendDown / LoadingPanel) + the memory-unavailable caveat. Honest, no cached-as-current.
- **State ownership:** per-screen `useFetch`; no shared store, no cross-screen cache; only the URL `:id` is shared (confirmed P28.0 Track 3).
- **Overclaim check:** no current overclaim found — the composer is verdict-free, source-labeled, guided-only, and the P25.7 memory caveat corrected a prior false claim. `assistantComposer.test.ts` + `assistant.test.tsx` cover it.
- **Test gaps for Phase 29:** no test asserts the assistant uses the CURRENT record rev, matches the backend workflow/evidence result, rejects stale context, invalidates on reset/edit/export, refuses to answer when the backend is unavailable, keeps Project Memory out of record-truth, keeps candidates unconfirmed, or is read-only until a confirmed mutation. No conversation-history, session-context, proposal, or confirmation-from-assistant tests exist (all net-new).

## 2. Selected live-context contract — **Option A (compose existing typed endpoints) + coherence guard**, promoted into P29.4's shared state

**Decision:** compose the EXISTING P28 typed endpoints (record bundle: version/workflow/artifact/pending/status; evidence-classification: field_results/counts bound to record_rev; validate; audit; export-readiness) — every one already carries `record_rev`/`version`. Guarantee ONE coherent revision by a **coherence guard**: all results the assistant uses for a dataset-specific response must share the same record rev; on mismatch, reject/refresh (never answer from a straddled snapshot). This coherence is enforced centrally by the P29.4 single record-session state owner (one poller, one authoritative ETag).

**Rejected alternatives (grounded):**
- **Option B (new `/assistant-context` endpoint):** unnecessary backend duplication — the P28 endpoints already expose everything, version-bound. A new aggregate endpoint would re-derive/duplicate contracts and add a maintenance surface, for no coherence gain over "same-rev guard on existing calls." Violates "do not create an assistant-only copy of business rules."
- **Pure Option C (grow one record bundle to carry everything):** bundle growth + coupling; the evidence-classification is legitimately its own axis/endpoint (P28.5). Folding it is fine (already done for the evidence screen) but forcing ALL surfaces onto one mega-bundle over-couples.

**Live-context rule:** for every dataset-specific request → verify current record rev → retrieve deterministic current context → produce a typed deterministic result → render explanation. If the backend can't verify current state → the assistant says *"I cannot verify the current record state right now."* and never answers from old chat history as current. Project Memory may explain concepts/architecture/policy; it may NOT prove current fields/evidence/validation/audit/export/workflow.

## 3. Slice boundaries + dependency order

Ledger graph: `P29.0 → P29.2 ; P29.1 ; P29.3(needs 27 rev + 28 classifications) → P29.4 → P29.5`.

| Slice | Scope | Primary files (exclusive ownership) | Depends on |
|---|---|---|---|
| **P29.1** ephemeral session context | session-scoped, non-authoritative conversation/proposal store (sessionStorage + in-memory), keyed by session+experiment(+rev); cleared on reset; leak-safe | NEW `apps/web/src/lib/assistantSession.ts` (+ test) | P29.0 |
| **P29.2** conversation UI | chronological messages, bottom prompt pills, message truth-labels (record rev, result type, authority, actionability, stale/current), respectful auto-scroll, a11y | `AssistantPanel.tsx` (rework) + NEW conversation components + `assistant.css` (+ tests) | P29.1 |
| **P29.3** deterministic workflow agent | typed intent registry over P28 workflow + evidence classifications; proposal contract (source rev); confirmation via existing `/edit`/`/answers` with If-Match; 412→stale, no retry | NEW `apps/web/src/lib/assistantAgent.ts` + intent modules; reuses backend (no truth change) (+ tests) | P28 workflow/evidence; P29.1 |
| **P29.4** one shared state | record-session provider: one poller, one ETag, assistant+manual share; version change invalidates stale proposals; reset clears session; manual-first degradation | NEW `apps/web/src/lib/recordSession.tsx` (provider) + wire screens (+ integration tests) | P29.1–P29.3 |
| **P29.5** hosted QA | conversation layout, current-state verification, evidence honesty, confirmation flow, stale proposal, reset, degraded, two-tab | (QA only) | P29.1–P29.4 |

**FORBIDDEN every slice:** the frozen truth path (§ above). No external LLM. No second record store / hidden truth / duplicate workflow-or-evidence derivation. No `localStorage`/IndexedDB, no durable backend chat storage.

## 4. Subagent plan (bounded; ≤5/session; orchestrator owns integration/commits/deploy/QA/ledger)

Per-slice pattern (NOT a swarm): **1 implementation agent** (Opus for P29.3 agent state-machine + P29.4 shared-state architecture; Sonnet for P29.1 session lib + P29.2 components) + **1 independent Opus reviewer**. The orchestrator authors the red-first tests for truth-critical contracts (agent authority boundaries, confirmation/If-Match safety, stale invalidation, leak-safety), delegates implementation, integrates, and commits. Exclusive file ownership per the table; shared high-contention files (types.ts, routes.ts, snapshot, ledger) are edited only by the orchestrator or one agent at a time. No agent commits/pushes.

**Pushback on the "write all 16 P29.0 tests now" instruction:** those 16 invariants span P29.1–P29.4 (session, agent, shared state). Authoring them all as long-lived RED at P29.0 would leave a large failing-test surface across multiple slices — a maintainability/CI-noise risk, and it diverges from the Phase-28 pattern that worked (each slice RED-first for its own portion). Instead each slice writes its own red-first tests for its part of this contract; the 16 invariants are the acceptance checklist distributed across P29.1 (session lifecycle/leak/reset), P29.3 (rev-binding, classifications match, stale rejected, candidates unconfirmed, read-only-until-confirm, memory-not-truth, degraded-honest), and P29.4 (coherence, invalidation on edit/export/reset).

## 5. Human gates

None new (ledger §9 unchanged). External-LLM prohibition honored by design (deterministic agent). Carried non-blocking caveats: human two-visible-window passive-poll check; artifact stale-transition not UI-reachable on exported records (Phase 32).
