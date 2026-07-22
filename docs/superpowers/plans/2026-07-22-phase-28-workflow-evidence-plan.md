# Phase 28 — Workflow & Evidence Contracts (plan)

Status: **Phase 28 COMPLETE (2026-07-22).** All slices P28.0–P28.6 shipped, independently reviewed
(all SHIP), CI-green, deployed (Railway `938c4e4` synthetic-only, Vercel 200), hosted-QA PASS. Two
non-blocking caveats carried forward (human two-window passive-poll check; artifact stale-transition not
UI-reachable on exported records) — see the master ledger's Phase 28 Completion Gate. Next: Phase 29.
Baseline: `main @ 92ea16f` · CI `29901071582` success · Railway `synthetic-only` · Vercel 200 ·
backend 751 · frontend 383.

This plan is derived from the P28.0 read-only audit (four parallel tracks: backend workflow, evidence/
audit/export, frontend navigation, tests/docs/snapshot). Every claim below carries a `file:line` anchor
from that audit. It obeys the master execution ledger
(`2026-07-21-post-phase-26-master-execution-ledger.md`) and does not create a competing master plan.

**Core principle (from the mandate):** there is ONE authoritative backend-derived interpretation of
record state, workflow completion, current/reopened steps, invalidation reasons, evidence
classifications, validation, export readiness, and artifact freshness. The frontend, assistant, search,
and runtime retrieval may DISPLAY and EXPLAIN these; they may not independently redefine them. No
frontend-only completion model, no duplicated evidence rules in TypeScript, no second hidden workflow
store, no permanent completion flags detached from current record truth.

**Truth-plane protection (CLAUDE.md §13):** Phase 28 is a *contracts + presentation* phase. It must NOT
change what the deterministic truth core validates, gates, or exports. `schema/isaac_record_v1.json`,
`src/isaac_records/official.py`, `draft_validator.py`, `export.py`, `audit.py`, `cli.py` and their tests
stay behaviorally unchanged. New derivation code composes OVER these outputs; it never alters them.

---

## 1. Current architecture (P28.0 map)

### 1.1 Workflow / completion
- **No backend workflow-step model exists.** No step ids/labels/ordering/`current_step` anywhere in
  `apps/api/isaac_api`. The only step-like construct is the transient demo-run pipeline trace
  (`routes.py:250-334`) — not per-record, not persisted.
- A record has **one derived `status`** with four values (`workspace.py:73-76`,
  `needs_attention / in_review / ready_to_export / done`), computed on every read by `status()`
  (`workspace.py:400-417`) from `exported()` + `pending_count()` + an in-memory dry-run `export_draft`.
- **Completion is DERIVED, never persisted** (`workspace.py:15-16, 401`). The persisted state
  (`to_state`, `workspace.py:302-314`) has no status/completed/step field; the only persisted "done"
  proxy is `record_id` presence.
- **Frontend owns a hardcoded stepper.** `WorkflowSpine.buildSpine` (`WorkflowSpine.tsx:84-104`) is a
  fixed 5-entry array (`draft, complete, export, validate, audit`) whose `active` step is **re-derived
  independently in each screen** from ad-hoc booleans: `RecordWorkbench.tsx:202`
  (`detail.exported ? 'validate' : 'draft'`), `GuidedCompletion.tsx:157`
  (`remaining === 0 ? 'export' : 'complete'`), `ExportReadiness.tsx:322`
  (`exported ? 'validate' : 'export'`). **This is the forbidden frontend-only completion model.**
- **No route guard.** `/record/:id/complete|evidence|export` are directly URL-reachable regardless of
  gate state (`App.tsx:17-29`, no loader/guard); "locked" spine steps are merely non-links.
- **No revisit/summary/edit-mode concept.** "Read-only" describes whole non-mutating screens (S3/S5)
  only; answered S4 fields render as a static list with no re-open affordance
  (`GuidedCompletion.tsx:254-265`).
- **Version propagation is solid.** `currentVersion` seeded from `detail.version`, adopted from each
  response, sent as `If-Match` (`GuidedCompletion.tsx:98,122-143`; `ExportReadiness.tsx:123-126,217-266`;
  `api.ts:197-224`). 412→"changed elsewhere, input kept" banner (no auto-merge); 409 distinct
  (`GuidedCompletion.tsx:375-391`; `ExportReadiness.tsx:246-261,546-561`).
- **No cross-screen store.** Each screen independently `useFetch`es its own bundle (`useFetch.ts`,
  `api.ts:333-382`); `detail`/`version` refetched fresh per route; only `:id` is shared.
- **Live-sync** (P27.6): `GET /experiments/{id}` honours `If-None-Match`→304 (`routes.py:429-447`);
  `useRecordSync` polls as a change-signal only; S3/S5 silent refetch, S4 banner (preserves input),
  S6 silent refresh (`RecordWorkbench.tsx:44-47`, `EvidenceExplorer.tsx:39-42`,
  `GuidedCompletion.tsx:107-109`, `ExportReadiness.tsx:131-133`).

### 1.2 Evidence / audit / export
- **Two orthogonal existing axes**, both truth-core:
  - field **status** (`draft_validator.py:69`): `verified / inferred / needs_confirmation / missing /
    rejected`; `FINAL_STATUSES=(verified, inferred)`.
  - evidence **source_type** (`draft_validator.py:21-28`): observed set
    (`document, spreadsheet, screenshot, web_form, file_listing, user_confirmation`) + rule-backed
    `derivation`.
- **`inferred` = documented-rule derivation with a present value that legitimately exports**
  (`draft_validator.py:74-82`; rule-only → warning, still passes). This is NOT a "guess"
  (CLAUDE.md §5). The only null-candidate today is the hardcoded `implicit["edge"]`
  (`draft_builder.py:164-183`, `value:None` + derivation note, explicitly "do NOT assert a physics
  fact").
- **Five concepts already cleanly distinct** (do not conflate — mandate + audit §7): schema validity
  (`official.py:67-79`), evidence support (`draft_validator.py` + `audit.py` coverage), workflow
  completion (`workspace.py:400-417`), export readiness (`export.py:147-166`), advisory warnings
  (`portal_warnings.py`, structurally non-gating).
- **Export readiness** = draft PASS **AND** official PASS (`export.py:147-166`); coverage/advisory/status
  do NOT gate.
- **Export immutability = refuse-to-overwrite 409** (`routes.py:580-590`, `cli.py:78-80`). No re-export
  path. One artifact per experiment, keyed by `exp.id`.
- **No artifact-staleness concept.** The artifact is a one-time snapshot of `exp.draft` at export
  (`routes.py:592-604`); the draft stays editable and `save_versioned` bumps `rev` on change; there is
  **no link from the artifact to the source draft rev/signature** (sidecar has only `generated_utc`,
  `export.py:130-135`). An exported artifact can silently drift with zero representation. (This is the
  same class as the reset-content gap fixed for the reset path only in `61c017f`.)
- **No conflict detection, no general inferred-candidate, no distinct insufficient/unknown** class
  exists (audit §4, §B).

### 1.3 No-op / atomicity / versioning (reused foundation, do not rebuild)
- Record-level no-op guard EXISTS but is coarse: `save_versioned` (`workspace.py:335-358`) skips
  rewrite + rev-bump iff the whole `_authoritative_signature` (`sha256` of `{title, source, draft,
  record_id}`, `workspace.py:217-235`) is unchanged. No field-level no-op.
- Atomic writes via `atomic_write_text` (mkstemp→fsync→`os.replace`, `workspace.py:108-139`);
  per-record reentrant `record_lock` RLock (`workspace.py:159-173`).
- Version token opaque-generation-nonce + monotonic rev; `etag()` strong-quoted
  (`workspace.py:190-291`).

### 1.4 Tests / snapshot / preflight
- Full backend 751 (`pytest.ini` runs `tests/` + `apps/api/tests/`); frontend 383 (`vitest run`).
- Committed snapshot manifest = 202 graph-derived served paths (`memory.py` `_is_served`); **newer
  `docs/superpowers/plans/*.md` are absent** because the graph is stale, NOT policy-excluded — so a NEW
  plan doc under `docs/superpowers/plans/` does not drift the snapshot. Verify with `--check` regardless.
- R4.3 preflight (`scripts/isaac_preflight.py`) runs identical hard gates in all four modes (repo/branch/
  remote/secret/leak/snapshot-check/snapshot-CI-gate); modes differ only in advisory reminders.
- Open CQ carried forward: **CQ-7** (snapshot manifest indexes 5/8 skills; graph stale) → P32.5;
  **CQ-4/5/6/9** → Stabilization/P32. None block Phase 28.

---

## 2. Approved target (Phase 28)

A single **backend-derived Workflow & Evidence contract**, surfaced in every record bundle, consumed
identically by all screens and (later) the assistant. Concretely:

1. **Fixed ordered workflow** (P28.1): one permanent sequence, derived — not persisted, not
   frontend-computed. Canonical order (using app-native terms):
   `load_record → complete_metadata → review_evidence → review_export_readiness → export`.
   Each step carries a derived `{id, label(Title Case), state, current, reopened, blocked, reason}`.
   `state ∈ {complete, current, blocked, incomplete, reopened}` derived from current truth only.
2. **Dependency-aware invalidation** (P28.2): a deterministic dependency model computed atomically inside
   the existing `record_lock`/`save_versioned` critical section; a mutation returns record + workflow +
   invalidation together. Field-level no-op rule layered onto the existing signature guard. Exported-
   artifact freshness represented (stale/current) via a stored source signature, never auto-deleted,
   never silently shown as current.
3. **Revisit/summary/explicit-edit** (P28.3): completed steps open read-only/summary with an explicit
   Edit action; unchanged edits are no-ops; conflicts use the existing 412 recovery; no auto-merge, no
   hidden mutation on navigation.
4. **Deterministic evidence classification** (P28.4): a backend-origin classification VIEW over existing
   truth outputs, into `supported / insufficient_evidence / conflicting_evidence / inferred_candidate /
   unknown` — WITHOUT changing truth-core gating and WITHOUT flattening the existing axes.
5. **Typed evidence API + UI** (P28.5): one typed per-record evidence result bound to `record_rev`;
   accessible, non-color-only UI; assistant may explain but never upgrade a classification.
6. **Hosted QA** (P28.6).

### 2.1 Evidence-classification mapping (P28.4 — decided, truth-plane-safe)

The five categories are a **third axis (evidence-support classification)** that COMPOSES from the two
existing axes; it does not replace field-status, source_type, schema validity, workflow completion,
export readiness, or advisory warnings — those stay separate.

| Existing truth signal | → P28.4 class | Lossless? | Notes |
|---|---|---|---|
| `verified` + observed source_type | `supported` | yes | direct inspectable evidence |
| `user_confirmation` entry | `supported` | yes | user_confirmation IS an observed source_type |
| `inferred` + `derivation(rule)` + observed backing | `supported` (rule-backed) | yes | defensible deterministic derivation; exports today, unchanged |
| `inferred` + `derivation(rule)`, NO observed backing (today: warning) | `inferred_candidate` (display) OR `supported`-rule | **DECISION in P28.2/P28.4 mapping audit** | classification is a VIEW; MUST NOT change whether it exports (truth-plane frozen) |
| null candidate (`implicit["edge"]` pattern, `value:None` + note) | `inferred_candidate` | yes | proposed, unconfirmed, NOT in record — matches mandate |
| `needs_confirmation` with SOME evidence present | `insufficient_evidence` | n/a (new) | evidence exists but claim not established; also stays a workflow-pending blocker |
| `needs_confirmation`/`missing` with NO defensible evidence | `unknown` | n/a (new) | plainly no value; no default/guess |
| ≥2 evidence entries proposing incompatible values for one path | `conflicting_evidence` | n/a (**net-new** detection) | no automatic winner; human resolution |

`needs_confirmation` is a **workflow-pending** signal and MUST NOT be flattened into
`insufficient_evidence` wholesale — a field can be pending yet have strong evidence (waiting on user
confirmation) or weak evidence. The evidence-support class is computed independently and shown alongside
the workflow state, never merged.

---

## 3. Dependency matrix & slice order

Ledger graph: `P28.0 → P28.1 → P28.2 → P28.3 ; P28.4 → P28.5 (evidence track parallel) → P28.6`.

| Slice | Depends on | Produces | Consumed by |
|---|---|---|---|
| P28.1 fixed order | P28.0 | backend `workflow` block in detail bundle (ordered steps + states) | FE spine, P28.2, P28.3 |
| P28.2 dep invalidation | P28.1 | atomic recalc + invalidation result + artifact freshness; field no-op | P28.3, S6 |
| P28.3 revisit/edit | P28.1, P28.2 | summary-first + explicit Edit UI | P28.6 |
| P28.4 evidence classes | P28.0 (parallel to 28.1-3) | backend `field_results` classification (deterministic) | P28.5 |
| P28.5 evidence API+UI | P28.4 | typed evidence endpoint + accessible UI | P28.6 |
| P28.6 hosted QA | P28.1–P28.5 | hosted verification | close |

Backend workflow (P28.1/28.2) and evidence classification (P28.4) are the two independent backend
tracks; UI (P28.3, P28.5) follows each. No overlapping ownership of central models between concurrent
subagents (§5).

---

## 4. Allowed / forbidden files per slice

**FORBIDDEN in every slice** (truth plane, CLAUDE.md §13 — behavior frozen):
`schema/isaac_record_v1.json`, `src/isaac_records/official.py`, `src/isaac_records/draft_validator.py`,
`src/isaac_records/export.py`, `src/isaac_records/audit.py`, `src/isaac_records/cli.py`. New derivation
code READS their outputs; it does not modify them. (New deterministic *classification* helpers may be
added as NEW modules that import and compose truth-core outputs read-only.)

- **P28.1 allowed:** `apps/api/isaac_api/workspace.py` (add derived workflow computation — no persisted
  step flags), `routes.py` (surface `workflow` in detail bundle), `serialize.py`, a NEW
  `apps/api/isaac_api/workflow.py`; FE `WorkflowSpine.tsx`, per-screen `active` call sites,
  `lib/types.ts`, `lib/adapt.ts`; tests.
- **P28.2 allowed:** NEW `apps/api/isaac_api/dependencies.py` (dependency model) + `workspace.py`
  (`save_versioned` field-no-op + atomic recalc, `exported_signature` link), `routes.py` (return
  invalidation), `serialize.py`; tests. Artifact freshness stored on `Experiment` state.
- **P28.3 allowed:** FE screens (`GuidedCompletion.tsx`, `RecordWorkbench.tsx`, `ExportReadiness.tsx`),
  new/existing components (`GuidedPrompt.tsx`, `StatusChip.tsx`, `lib/status.ts`), `api.ts`; tests. No
  backend truth change.
- **P28.4 allowed:** NEW `apps/api/isaac_api/evidence_classify.py` (or `src/isaac_records/` NEW module IF
  the classification must live in the deterministic core — decide in slice; must be Graphify-free and
  additive, importing existing validators read-only), `serialize.py`; tests.
- **P28.5 allowed:** `routes.py` (typed evidence endpoint), FE `EvidenceExplorer.tsx`, `EvidenceRow.tsx`,
  `EvidenceTrailPanel.tsx`, `lib/types.ts`, `api.ts`, `assistant*.ts` (explain-only); tests.

**Snapshot manifest note:** editing any manifest-listed served file (`CLAUDE.md`, `AGENTS.md`,
`docs/*.md` that are indexed, `.claude/skills/*/SKILL.md`, or any served `apps/web`/`src` path) requires
deterministic snapshot regeneration in the SAME commit. Run `--check` every slice regardless.

---

## 5. Orchestration & ownership

- Orchestrator: Opus 4.8 (Fable 5 unavailable) — plans, decomposes, reviews, integrates, commits,
  deploys, checkpoints. Does NOT write production code.
- Implementation: Opus 4.8 for P28.1/P28.2/P28.4 (workflow dependency architecture, invalidation
  semantics, artifact freshness, deterministic evidence mapping, truth-plane boundaries) and complex FE
  state (P28.5 shared state); Sonnet 5 for lower-risk component/test/fixture/doc work.
- Independent adversarial review: a SEPARATE Opus 4.8 reviewer per release slice (review focus list in
  the mandate). Fix every Critical + Important before commit.
- Subagents never commit/push. No two concurrent implementers own the same central model.

## 6. Test strategy (test-first every slice; prove RED)

- P28.1: `test_workflow_order.py` — fixed order across all five seed records; states derived
  (complete/current/blocked/incomplete/reopened); visiting ≠ completing; reopened distinguishable;
  no persisted completion flag; FE reads backend states (no local re-derivation) — `workflow.test.tsx`.
- P28.2: the mandate's 18-point list (identical→no-op, presentation-only preserves, scientific-identity
  invalidates, required-removal reopens, evidence add/conflict/resolve, readiness deps, artifact stale on
  authoritative change, unrelated edit doesn't stale, single rev bump, invalidation@same rev, two
  concurrent safe, stale→no invalidation, live-sync coherent, reset baseline, idempotent demo, no FE
  drift).
- P28.4: five classes distinct; validation vs evidence-support separate; truth-core export behavior
  UNCHANGED (golden export tests still pass byte-for-byte); conflicting detection; candidate lifecycle.
- P28.5: typed result bound to `record_rev`; a11y (label+icon+text, not color-only); assistant cannot
  upgrade a class; search/runtime never treat candidates as confirmed.
- Every slice: focused → full backend (`.venv/bin/pytest`) → full frontend (`vitest run`) → tsc + Vite
  build → truth validation + evidence audit + synthetic demo → snapshot `--check` (+ gate test) →
  path/secret/leak scan → R4.3 `full` → independent Opus review → commit → push → exact-HEAD CI →
  Railway + Vercel → hosted QA for user-visible behavior.

## 7. Browser-QA matrix (P28.6)

Fixed workflow (order stable across records, current clear, completed stays green while valid, viewing
preserves completed styling, back/forward, deep links, refresh, two-tab consistent); revisit/edit
(summary-first, Edit, Cancel=no mutation, same-value=no-op, scientific change reopens only relevant +
explains why, two-tab stale→412, no auto-merge); evidence classes (supported/insufficient/conflicting/
inferred_candidate/unknown labels + explanations + sources + confirmation states + a11y + assistant
language) via deterministic synthetic fixtures; export/artifact freshness (export ready; presentation-
only change keeps artifact current; authoritative change → not-current + readiness recalculates +
regeneration behavior + sidecar behavior + two-tab stale export blocked); live-sync (updates reach a
visible tab, assistant context refreshes, unsaved input protected, bounded polling, no console errors, no
request storm). **Carry forward** the human two-visible-window passive-poll check (idle banner + ~8s
cadence + offline "live updates paused") — automation drives tabs `visibilityState=hidden`, so passive
polling is not automation-observable; this is a documentation follow-up, not a gate.

## 8. Commit boundaries

One scoped commit per slice (P28.1 … P28.6), each after its full verification loop + independent review +
green exact-HEAD CI + deploy check. Ledger updated per slice. `/isaac-checkpoint` per slice.

## 9. Human gates (stop only for these — ledger §9)

No new hard gate found in P28.0. The one potential spec collision (P28.4 `inferred_candidate` vs
committed Phase-21 `inferred`-exports) is RESOLVED by scoping P28.4 as a display/classification layer
that does not change truth-core gating (§2.1). Proceed automatically through P28.1–P28.6 unless a
Critical/Important defect proves unresolvable within this architecture, or two committed specs are found
irreconcilable.
