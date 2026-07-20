# Phase 25 — Grounded Assistant — Implementation Plan

Status: PROPOSED — awaiting approval. Direction **DECISION-LOCKED 2026-07-20**; P25.0 (design/spec) is the only authorized next step, and no production code (P25.1+) is authorized.
Date: 2026-07-19 (decisions locked 2026-07-20)  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: 2026-07-16-phases-23-26-arc-decisions.md; `2026-07-20-remaining-work-decision-lock.md` (authoritative); P24 specs (24 / 24.9 / 24.10); this doc EXTENDS the approved arc.

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

- **P25.1 — Deterministic composer skeleton + source-label rendering on RecordWorkbench.**
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

- **P25.2 — Free-text removal + "Guided prompts only" framing (arc item 8).**
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

- **P25.4 — Ground the Export context (ExportReadiness).**
  - Objective: replace `ASSISTANT_SAMPLES.export` with `compose('export', bundle)`; keep
    `ROUTE_TO_CLI_NOTE`. Coverage/warnings echoed live; verdict routed. Files:
    `screens/ExportReadiness.tsx`; test. Model: Opus. Tests: extend `completion-export.test.tsx`. CP-B.
    Report + commit + stop.

- **P25.5 — Ground + mount the Evidence context (EvidenceExplorer).**
  - Objective: mount `AssistantPanel` on `EvidenceExplorer` (new mount) and wire
    `compose('evidence', getEvidenceBundle)`. Files: `screens/EvidenceExplorer.tsx`; test. Model: Opus.
    Acceptance: panel appears below the Evidence Trail (truth above advisory ordering preserved), answers
    echo live coverage/evidence. Tests: extend `evidence.test.tsx`. CP-B. Report + commit + stop.

- **P25.6 — Ground + mount the Complete Missing Fields context (GuidedCompletion).**
  - Objective: mount the panel and wire `compose('complete', {pending, draft, validate})` — **advisory
    only, never submits**. Files: `screens/GuidedCompletion.tsx`; test. Model: Opus. Acceptance: answers
    describe blockers; confirm/skip flow in `GuidedPrompt.tsx` untouched. Tests: extend
    `completion-export.test.tsx`. CP-B. Report + commit + stop.

- **P25.7 — Project Memory context (PRIORITIZED — where appropriate).**
  - Objective: mount a grounded, memory-caveated assistant on `ProjectMemory`, wiring
    `compose('memory', graphStatus/concepts/files)`. Files: `screens/ProjectMemory.tsx`, test. Model:
    Opus. Acceptance: availability/drift/provenance echoed, non-alarming, carries the leads-to-verify
    caveat; mounted only where it adds real grounded value (per the decision-lock "where appropriate").
    Tests: extend `memory-concepts.test.tsx`/screen test. CP-B. Report + commit + stop.

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
