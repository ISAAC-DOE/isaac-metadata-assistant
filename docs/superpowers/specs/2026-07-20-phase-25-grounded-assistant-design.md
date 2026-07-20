# P25.0 — Grounded Assistant Design / Spec (mini-spec)

Status: **PROPOSED — awaiting your approval. This is the single P25.0 design gate; NO P25.1+ code is
authorized.**
Date: 2026-07-20 · Baseline commit: `f534a4c` (code) / `3fed890` (docs) · Author: orchestrator
(Opus 4.8), reviewed by an independent Opus 4.8 pass.
Governing plan: `docs/superpowers/plans/2026-07-19-phase-25-grounded-assistant-plan.md`.
Decision authority: `docs/superpowers/plans/2026-07-20-remaining-work-decision-lock.md` §7.

> This spec finalizes the deterministic composer contract, the source-label taxonomy, the per-screen
> chip catalogs + answer templates, value-echo/no-verdict rules, caveat rules, accessibility, tests,
> the P25.1+ slices, and the approval questions — all grounded in the **actual** as-built code
> (verified against `f534a4c`; no divergence from the plan §8). Wording marked *(final)* is proposed
> as final pending your sign-off; wording marked *(illustrative)* is an example for review.

---

## 0. Governing constraints (non-negotiable — from arc item 8 + decision-lock §7)

Deterministic · guided-prompt-driven · **NO LLM / NO freeform chat** · subordinate to the
deterministic core · source/provenance-labeled · invents no scientific values · never validates ·
never silently mutates a record · never bypasses propose→stage→confirm. The composer is a **pure,
synchronous frontend function over already-fetched bundle data** — **zero new fetches, zero new
backend endpoint, zero truth-path change.** The existing guard `hasVerdictLanguage()` is preserved
and now runs over *composed* output as a structural backstop.

---

## 1. As-built facts this spec builds on (verified `f534a4c`)

- `AssistantSource = 'schema' | 'audit' | 'git' | 'graph' | 'files'` (`types.ts:162`). `AssistantMessage
  = {text, answeredFrom, sourceDoc?}`; `SuggestedPrompt = {text, answeredFrom, answer?}` (`types.ts:164-176`).
- Guard (`assistant.ts:30-32`): `hasVerdictLanguage(t) = /\b(PASS|FAIL)\b/.test(t) || /\b(in)?valid against\b/i.test(t)`.
- `AssistantPanel` props `{reply, prompts, availability, note?}` (`AssistantPanel.tsx:13-20`); guard
  substitution text = *"That is a truth question — open the Validate surface for the deterministic
  verdict."* (`:34-42`); chips are native `<button aria-pressed disabled={!p.answer}>` (`:70-82`); the
  disabled free-text `<input>`+send block is `:85-98`; `answered from: {answeredFrom}` renders raw
  (`:60-63`).
- Mounts today: **RecordWorkbench** (`:173-177`, `ASSISTANT_SAMPLES.review`, `availability={graph.availability}`)
  and **ExportReadiness** (`:301-306`, `ASSISTANT_SAMPLES.export` + `note=ROUTE_TO_CLI_NOTE`). No other
  screen mounts the panel.
- Bundles already fetched (zero new fetches needed):
  - `getRecordBundle` → `{detail, groups, pending, validate, audit, warnings, evidence, graph}`.
  - `getExportReadiness` → `{detail, pending, validate, audit, warnings, graph, artifacts}`.
  - `getEvidenceBundle` → `{detail, evidence, artifacts, graph, sourcePreviews}` — **no `audit`**.
  - `GuidedCompletion` fetches only `{detail, pending}` — **no `validate`, no `graph`**.
  - `ProjectMemory` fetches `graph` status + `concepts` + `files` across sub-views.
- Backend fields the composer may echo verbatim: validate `{ok, errors:[{path,message}], schema, dry_run}`;
  pending items `{id, kind, question, about}`; audit `records[].{evidence_present, evidence_expected,
  uncovered[], dangling[]}`; warnings `{code, where, message}` (`advisory:true, gating:false`); evidence
  `{path, value?, status, evidence[]}`; draft groups `{title, fields[{path,label,value,status,
  evidence_count,source_types}]}`; artifacts `{record, sidecar, record_path, sidecar_path}` (nullable);
  experiment `status ∈ {needs_attention, in_review, ready_to_export, done}`; graph/status
  `{availability, integrity, memory_policy, indexed_sources, provider, note, …fingerprints}`; memory
  `concepts[]`/`files[]` each with `MEMORY_NOTE`.
- Backend strings (values, not importable frontend constants): the memory `note` = *"Project memory
  returns leads to verify — never a validation verdict."* (returned as `graph.note` / on `/memory/*`);
  403 upload reason = *"Real or private data upload is approval-gated and not enabled in this synthetic
  prototype."* The frontend will provision an equivalent const `MEMORY_LEADS_NOTE` for memory templates
  (§12) rather than assume `MEMORY_NOTE` is importable.

---

## 2. Source-label taxonomy (FINAL proposal)

Decision-lock §7 requires five distinguished categories + history. Enum extension:

```ts
// types.ts — extend the union (additive)
export type AssistantSource =
  | 'schema'     // truth state — schema validity gate (/validate, official schema)
  | 'audit'      // truth state (reporting) — evidence coverage counts (/audit)  [not a verdict]
  | 'files'      // evidence — per-field provenance, cited source lines (/evidence, /source-preview, /draft)
  | 'advisory'   // advisory — soft, non-gating warnings (/warnings)             [NEW]
  | 'workflow'   // artifact/workflow state — record/experiment status, artifacts, export-readiness (/experiments/{id}, /artifacts)  [NEW]
  | 'graph'      // Project Memory — concepts, availability, provenance, drift (/graph/status, /memory/*)
  | 'git';       // history (auxiliary) — "what changed"
```

**Display-label map (FINAL — small rendering addition in `AssistantPanel`):** the panel currently
renders the raw enum after "answered from:". To make the five categories legible, add a map so the
*displayed* text is human while the enum stays machine-stable:

```ts
export const SOURCE_LABELS: Record<AssistantSource, string> = {
  schema:   'schema validation',
  audit:    'evidence coverage (audit)',
  files:    'evidence',
  advisory: 'advisory warning',
  workflow: 'record / artifact status',
  graph:    'project memory',
  git:      'history',
};
// MEMORY_LEADS_NOTE — the leads-to-verify caveat appended to every memory answer (frontend const
// mirroring the backend memory `note` text):
// export const MEMORY_LEADS_NOTE = 'Project memory returns leads to verify — never a validation verdict.';
// AssistantPanel renders: `answered from: ${SOURCE_LABELS[active.answeredFrom]}`
```

Five decision-lock categories → labels: **truth state** = `schema` (+ `audit` reporting) · **evidence**
= `files` · **advisory** = `advisory` · **artifact/workflow state** = `workflow` · **Project Memory** =
`graph`. `git` remains an auxiliary history label. `ASSISTANT_SOURCES` (`assistant.ts:14-20`) grows to
the 7 values; the DEV sanity loop keeps checking every sample/composed reply.

> **Approval Q-A:** confirm enum value `'workflow'` for artifact/workflow state and the `SOURCE_LABELS`
> display strings above (or supply preferred wording).

---

## 3. Composer contract (FINAL)

A pure, synchronous, side-effect-free function. No fetching; it receives the bundle the screen already
holds.

```ts
export type ScreenContext = 'review' | 'export' | 'evidence' | 'complete' | 'memory';

// Discriminated GroundingState = exactly the bundle each screen already fetches (§1). No new fields.
export type GroundingState =
  | { context: 'review';   bundle: RecordBundle }          // {detail,groups,pending,validate,audit,warnings,evidence,graph}
  | { context: 'export';   bundle: ExportReadinessBundle } // {detail,pending,validate,audit,warnings,graph,artifacts}
  | { context: 'evidence'; bundle: EvidenceBundle;  selectedPath?: string } // {detail,evidence,artifacts,graph,sourcePreviews}
  | { context: 'complete'; detail: ApiExperimentDetail; pending: ApiPendingItem[] } // NO validate/graph today
  | { context: 'memory';   graph: ApiGraphStatus }; // today's chips read graph only; concept/file-level chips are a future option

// A chip is authored (not generated). Its answer is composed live from state via a pure resolver.
export interface GroundedChip {
  id: string;                              // stable key
  label: string;                           // chip text (≤ ~44 chars, verb-first)
  source: AssistantSource;                 // the plane/category this answers from
  routed?: boolean;                        // truth-question chips that ALWAYS route, never echo a verdict
  resolve(state: GroundingState): AssistantMessage | null; // null → data absent → chip disabled
}

export interface ComposerOutput { reply: AssistantMessage; prompts: SuggestedPrompt[] }

// The composer maps a context + already-fetched state to the existing panel props shape.
export function compose(state: GroundingState): ComposerOutput;
```

Three-stage pipeline (the reusable "grounding layer" Phase 26 search reuses for stages 2–3):

1. **Prompt → structured query.** Each chip carries a fixed `{intent, source, resolver}` chosen at
   authoring time. **No natural language is parsed.**
2. **Structured query → resolved values.** The `resolver` is a pure selector over `GroundingState`
   that reads already-present values (counts, paths, messages, names, statuses). It never derives,
   formats a scientific quantity, or computes a verdict. Missing data → `null` (chip disabled / honest
   "unavailable"), never a fabricated value.
3. **Resolved values → templated reply.** A fixed template interpolates resolved values into a short,
   source-labeled `AssistantMessage`, then `hasVerdictLanguage()` runs as a structural backstop before
   render (existing substitution behavior).

**Loading/error:** if the screen bundle is `loading`/`error`, the panel is not mounted with composed
content — it defers to the screen's existing `LoadingPanel`/`BackendDown`. Individual chips whose
`resolve()` returns `null` are `disabled` (reuse `disabled={!p.answer}`).

---

## 4. Value-echo & no-verdict rules (FINAL — hard rules)

**MAY echo verbatim** (already present in fetched state): pending item `id`/`about`/`question`;
validate `errors[].path`; audit `evidence_present`/`evidence_expected` and `uncovered[]`/`dangling[]`
paths; advisory `code`/`where`/`message`; evidence `path`/`status` and a draft field's stored `value`
+ `source_types`; concept `label`/`community_name`; graph `availability`/`memory_policy`/
`indexed_sources`/`provider`/`note`; experiment `status` literal; artifact `record_path`/`sidecar_path`.

**MUST NOT:** synthesize, reformat, unit-convert, round, or derive any scientific value; invent hashes,
URIs, paths, descriptors, uncertainties, QC, timestamps; **surface `validate.ok` as a verdict.** For
"is it valid / what blocks export," state a **count of blocking paths** + the paths + route to Validate
— never PASS/FAIL/valid/invalid.

**Guard interaction (verified against the regex + validator).** The guard trips on `PASS`/`FAIL` or
`(in)?valid against`. In the current backend, per-error `errors[].message` reads like *"assets is a
required property"* (`official.py:71`) and does **not** contain that phrase — the phrase lives only in
the validator's PASS *summary* string (`official.py:61`), never in per-error messages. The real risk is
echoing the validator **summary** or surfacing `validate.ok` as a verdict. **Therefore templates echo
`errors[].path` + a count and never echo `validate.ok` or the summary** — this is both guard-safe and
better for copy density. The guard still runs over composed output as a structural backstop, and a
dedicated test feeds a verdict-ish payload (e.g. a message containing "invalid against") to assert
substitution regardless.

---

## 5. Per-screen contexts, chip catalogs & answer templates

Notation: `{…}` = value echoed from fetched state. Every reply is 1–3 short sentences, one primary
source label, ≤1 caveat line. Lists show the first **N = 3** items then "…and K more". Wording is
*(final)* unless marked *(illustrative)*.

### 5.1 Review — RecordWorkbench (`review`; state = getRecordBundle)
| Chip label *(final)* | source | Answer template |
|---|---|---|
| "What still needs me?" | `workflow` | "{pending.length} field(s) still need you: {pending[0..2].about}{…and K more}." · empty → "Nothing pending — every field is confirmed or filled." |
| "What's left before export?" | `schema` | "{validate.errors.length} path(s) still block export: {errors[0..2].path}{…}. Open Validate for the deterministic verdict." (count+paths; never `ok`) |
| "Trace a field to its source" | `files` | "{evidenced field.path} came from {evidence.source_file}{ (locator …)}." · none → "No cited source for a field yet." |
| "Is this record valid yet?" | `schema` (`routed`) | Always routes: "That's a truth question — open Validate for the deterministic verdict." (authored routed; never echoes `ok`) |
| "Where do memory leads come from?" *(only if `graph.availability==='available'`)* | `graph` | "Project-memory leads are drawn from indexed project files/concepts. MEMORY_LEADS_NOTE" |

### 5.2 Ready to Export — ExportReadiness (`export`; state = getExportReadiness; keeps `note=ROUTE_TO_CLI_NOTE`)
| Chip label *(final)* | source | Answer template |
|---|---|---|
| "Is coverage the same as valid?" | `audit` | "Coverage is {audit.records[0].evidence_present}/{evidence_expected} — how many expected fields carry evidence, not whether the record is valid. Validity is the schema gate." · empty (pre-export, `records:[]`) → resolver returns null → chip disabled, or "Nothing exported yet — coverage appears after export." |
| "Explain the advisory warning" | `advisory` | "{warnings[0].code} — {warnings[0].message} (advisory, non-gating; where: {warnings[0].where})." · none → "No advisory warnings on this record." |
| "What's left before export?" | `schema` | "{validate.errors.length} path(s) block export: {errors[0..2].path}{…}." (+ panel `note` routes to CLI) |
| "Where are the exported artifacts?" | `workflow` | artifacts.record → "Exported: record `{record_path}`, sidecar `{sidecar_path}`." · else → "Not exported yet — export writes the record + evidence sidecar." |

### 5.3 Evidence & File Preview — EvidenceExplorer (`evidence`; state = getEvidenceBundle; NEW mount)
No `audit` here → **coverage chips do not live on Evidence** (they live on Export). Chips ground in
evidence/artifacts/sourcePreviews.
| Chip label *(final)* | source | Answer template |
|---|---|---|
| "Is the sidecar an official artifact?" | `files` (`routed`) | "The evidence sidecar is an assistant convention, not an official ISAAC standard — it preserves field-level evidence the official schema has no slot for." (echoes the D1 convention) |
| "Why multiple evidence entries?" | `files` | For `selectedPath`: "{path} has {evidence.length} evidence entr(y/ies): {evidence[0..2] source_type/quote}." · none → "Select a field to trace its evidence." |
| "What files back this record?" | `files` | "This record cites {detail.source_files.length} source file(s): {source_files[0..2]}{…}." |
| "Is project memory current?" *(if `graph.availability==='available'`)* | `graph` | memory-freshness template (§6). |

### 5.4 Complete Missing Fields — GuidedCompletion (`complete`; state = {detail, pending} only)
**Advisory only — never submits.** No `validate`/`graph` fetched today → chips ground in `pending`.
| Chip label *(final)* | source | Answer template |
|---|---|---|
| "Which fields still need me?" | `workflow` | "{pending.length} field(s) need you: {pending[0..2].about}{…and K more}. Confirm or skip each below." |
| "What happens if I leave one missing?" | `schema` | "A required field left missing keeps blocking export and stays honest-missing — never guessed. You can skip it now and return later." |
| "What does this question want?" | `workflow` | For the active pending item: "{pending[i].question} — about {pending[i].about}." (echoes the pending prompt; the confirm/skip flow stays in `GuidedPrompt.tsx`) |

> **Fetch-gap decision (Q-D):** to answer "which fields block export" with *validate paths* on this
> screen, GuidedCompletion would need to also fetch `/validate`. **Recommended: do NOT add the fetch —
> ground on `pending`** (which already encodes what's missing), preserving the zero-new-fetch purity.
> Alternative (add a `validate` fetch) is a small, backend-contract-free frontend change if you prefer
> validate-path wording. Default = pending-grounded.

### 5.5 Project Memory — ProjectMemory (`memory`; state = graph + concepts + files; PRIORITIZED, where appropriate)
Every answer carries the leads-to-verify caveat; never red for degraded memory.
| Chip label *(final)* | source | Answer template |
|---|---|---|
| "Where do these leads come from?" | `graph` | "Leads come from indexed project files/concepts (provider: {graph.provider}). MEMORY_LEADS_NOTE" |
| "Is project memory current?" | `graph` | "Indexed sources: {graph.indexed_sources}; memory policy: {graph.memory_policy}." + stale/unknown → quiet caveat (§6). |
| "Why is memory unavailable?" *(only if `availability==='unavailable'`)* | `graph` | "{graph.note} {MEMORY_UNAVAILABLE_CAVEAT}" (honest; not an error state) |

### 5.6 Excluded screens (decision-lock)
My Experiments, Load Materials, Settings, Governance are **not** mounted. Illustrative catalogs to
weigh only if you later approve one (with specific inputs/outputs/value): My Experiments — "What needs
me next?" (→ per-experiment `status`/`pending_count`); Load Materials — "Why is upload blocked here?"
(→ echoes the verbatim 403 reason). **Not proposed for P25-core.**

> **Approval Q-C:** confirm the per-screen chip catalogs + wording above (or edit any chip/label).

---

## 6. Caveat rules (FINAL)
- `availability === 'unavailable'` → memory chips answer with `MEMORY_UNAVAILABLE_CAVEAT`
  (*"Project memory is unavailable — answered from source files directly."*), **no red / no error styling.**
- Memory available but `memory_policy` or `indexed_sources` ∈ {`stale`,`unknown`} → append a **quiet**
  caveat: *"Indexed sources may be behind the working tree — leads to verify."* Non-alarming (matches
  the P24 "no red, no fake counts" discipline).
- Every memory-sourced answer carries the leads-to-verify note (the `MEMORY_NOTE` analogue).

## 7. Unknown / unavailable behavior (FINAL)
- Missing value → say it is missing/absent; **never guess**.
- `resolve()` returns `null` when its data is absent → chip is `disabled` (existing pattern).
- Bundle `loading` → panel not shown / chip disabled; `error` → defer to `BackendDown`. The assistant
  never fabricates rows.

## 8. Allowed vs forbidden input (FINAL)
- **Allowed:** clicking a guided chip (primary and only input); keyboard activation via native
  `<button>` semantics.
- **Forbidden / removed:** free-text entry. The disabled `<input>`+send block (`AssistantPanel.tsx:85-98`)
  is **removed** and replaced by one honest line: **"Guided prompts only — the assistant answers the
  suggested questions above."** `FREEFORM_NOT_WIRED` is retired; a `GUIDED_ONLY_NOTE` constant replaces
  it. No hidden/disabled input remains.

## 9. Copy-density limits (FINAL)
- Reply: **1–3 short sentences**, exactly **one** primary source label, **≤1** caveat line. No walls of text.
- Chip label: **≤ ~44 chars**, verb-first, one question.
- **At most one** echoed value list per reply; show first **N = 3**, then "…and K more" — never a full dump.

## 10. Accessibility behavior (FINAL)
- Chips stay native `<button aria-pressed disabled={!answer}>` — **no custom `onKeyDown`** (repo a11y
  precedent).
- The reply region gains `aria-live="polite"` so chip-driven answer changes are announced.
- `section aria-label="Assistant (advisory)"` retained; `answered from: <label>` remains **visible
  text** (via `SOURCE_LABELS`), not color-only. Removing the free-text box simplifies tab order and
  removes the `aria-hidden` input.

## 11. Tests (FINAL plan)
- **Unit — `assistantComposer.test.ts` (new):** per context, given a fixture `GroundingState` → assert
  exact `{reply, prompts}`: value-echo correctness (paths/counts/messages echoed verbatim),
  guard-cleanliness, no fabricated values, `null`/disabled on missing data, memory-unavailable +
  stale/unknown caveats, correct `SOURCE_LABELS`/source per chip.
- **Unit — verdict resilience:** feed a `validate` payload whose `errors[].message` contains
  "invalid against"/PASS/FAIL → assert the composed reply is guard-substituted/routed, never echoed raw.
- **Screen integration:** each mounting screen renders the composed reply from a live bundle fixture;
  backend-down → honest state (no fake reply); memory-unavailable → caveat, no red.
- **Regression — `assistant.test.tsx` (updated):** guard still strips; **no free-text box**; "Guided
  prompts only" present; `answered from:` present on every reply; no hardcoded field-count claims; DEV
  sanity loop now runs over composer outputs. The existing 11 assertions are preserved/adapted (the
  "free-form not wired" test becomes a "guided-only" assertion with a rationale comment — never a
  silent delete).
- **Invariants untouched:** no-fake-search, no-vertical-rail unchanged; backend **461** re-run to prove
  the truth path is untouched.

## 12. Exact files & contracts (FINAL)
New/edited (frontend only — **zero** `apps/api/**`, `src/**`, `schema/**`):
- **New** `apps/web/src/lib/assistantComposer.ts` — `compose()`, resolvers, `GroundedChip`, per-context
  `CATALOG`.
- `apps/web/src/lib/types.ts` — extend `AssistantSource` (+`advisory`,`workflow`); add `ScreenContext`,
  `GroundingState`, `GroundedChip`, `ComposerOutput`.
- `apps/web/src/lib/assistant.ts` — grow `ASSISTANT_SOURCES`; add `SOURCE_LABELS`, `GUIDED_ONLY_NOTE`,
  and `MEMORY_LEADS_NOTE` (frontend const mirroring the backend memory note — the memory templates use
  this, not an assumed-importable `MEMORY_NOTE`); retire `FREEFORM_NOT_WIRED`; (last slice) delete
  `ASSISTANT_SAMPLES` + migrate the DEV sanity loop.
- `apps/web/src/components/AssistantPanel.tsx` — render `SOURCE_LABELS[...]`; remove free-text block;
  add `aria-live` on the reply region; add the guided-only line.
- `apps/web/src/components/assistant.css` — remove free-form styles; minor guided-only layout.
- Screens: `RecordWorkbench.tsx`, `ExportReadiness.tsx`, `EvidenceExplorer.tsx` (new mount),
  `GuidedCompletion.tsx` (new mount), `ProjectMemory.tsx` (new mount).
- Tests as §11; doc `docs/ui-handoff/ai-assistant-and-graphify.md`.
Forbidden: everything under `apps/api/**`, `src/isaac_records/**`, `schema/**`; the no-fake-search
tests; the propose→stage→confirm flow in `GuidedPrompt.tsx` (the assistant advises around it, never
drives it); the stale docs owned by the Documentation plan.

## 13. Bite-sized P25.1+ slices (aligns with the plan §20; NONE authorized yet)
- **P25.1** — composer skeleton + `SOURCE_LABELS`/enum extension + **source-label rendering on
  RecordWorkbench** (pure module TDD'd, then wired to that one screen, behind the guard). Model: Opus.
- **P25.2** — free-text removal + "Guided prompts only" framing; adapt `assistant.test.tsx`. Model: Sonnet.
- **P25.3** — *(tombstone — folded into P25.1)* RecordWorkbench grounding ships with the composer
  skeleton in P25.1; the ID is retained so P25.4–P25.8 keep their numbers (matches plan §20).
- **P25.4** — ground the Export context. Model: Opus.
- **P25.5** — ground + **mount** the Evidence context. Model: Opus.
- **P25.6** — ground + **mount** the Complete context (advisory-only; pending-grounded). Model: Opus.
- **P25.7** — ground + **mount** the Project Memory context (where appropriate). Model: Opus.
- **P25.8** — *(excluded by default)* non-record screens; only if you approve specific value. Model: Opus.
- **P25.9** — retire `ASSISTANT_SAMPLES` + migrate the DEV sanity loop. Model: Sonnet.
- **P25.10** — full verification (frontend + backend 461) + docs + preview QA. Final phase stop gate.
Every slice: one subagent, independently reviewable, its own stop gate; orchestrator (Fable 5 else
Opus 4.8) reviews each diff and never implements.

## 14. Visual / copy examples (for your review)

**Review context — memory available, 2 pending, 2 blocking paths (illustrative render):**
```
┌ Assistant (advisory) ───────────────────────────── memory: available ┐
│ 2 fields still need you: sample environment temperature, and the      │
│ reduced-spectrum URI.                                                  │
│ answered from: record / artifact status                               │
│                                                                        │
│  [ What still needs me? ▸ ]  [ What's left before export? ▸ ]          │
│  [ Trace a field to its source ▸ ]  [ Is this record valid yet? ▸ ]    │
│                                                                        │
│  Guided prompts only — the assistant answers the suggested questions.  │
│  The assistant is advisory — it explains artifacts and points to       │
│  sources. It never validates; deterministic validation is the         │
│  authority.                                                            │
└────────────────────────────────────────────────────────────────────┘
```
Click **"What's left before export?"** →
```
2 path(s) still block export: $.assets[0].sha256, $.spectra[0].reduced_uri.
Open Validate for the deterministic verdict.        answered from: schema validation
```
Click **"Is this record valid yet?"** (routed; guard-clean) →
```
That's a truth question — open Validate for the deterministic verdict.
answered from: schema validation
```

**Export context — advisory warning present (illustrative):**
```
[NO_LINKS] — the record declares no relationships to others; advisory, non-gating (where: $.links).
answered from: advisory warning
```

**Project Memory — indexed sources stale (illustrative):**
```
Indexed sources: stale; memory policy: current.
Indexed sources may be behind the working tree — leads to verify.
answered from: project memory
```

---

## 15. Approval questions (please resolve to close P25.0)
- **Q-A** — enum value `'workflow'` for artifact/workflow state + the `SOURCE_LABELS` display strings (§2)? (Recommend yes.)
- **Q-B** — the `SOURCE_LABELS` display-map rendering change in `AssistantPanel` (friendly text instead of raw enum) is in scope for P25.1? (Recommend yes — it is what makes the 5 categories legible; tiny, frontend-only.)
- **Q-C** — the per-screen chip catalogs + wording in §5 (edit any chip/label). (Recommend as written.)
- **Q-D** — Complete context grounds on `pending` only (no added `validate` fetch), keeping zero-new-fetch purity? (Recommend yes.)
- **Q-E** — Evidence context has no `audit`, so coverage chips stay on Export only? (Recommend yes.)
- **Q-F** — copy-density `N = 3` echoed items before "…and K more"? (Recommend yes.)
- **Q-G** — Project Memory is mounted in P25.7 as a prioritized surface ("where appropriate"); confirm it is genuinely useful there vs. deferring it? (Recommend mount — the freshness/provenance answers are real and grounded.)

## 16. Stop
This spec is docs-only. **No P25.1+ code is authorized.** On your approval of Q-A…Q-G (or edits), the
first code slice is **P25.1 (composer skeleton + source-label rendering on RecordWorkbench)** — one
screen, behind the verdict guard, fully unit-tested, no new backend contract.
