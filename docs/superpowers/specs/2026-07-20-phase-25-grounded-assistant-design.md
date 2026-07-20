# P25.0 — Grounded Assistant Design / Spec (mini-spec) — DECISIONS APPLIED

Status: **DECISIONS APPLIED (2026-07-20). Docs-only. Corrected per the approved P25.0 decisions and
verified against the as-built code. Independent-review-gated: P25.1 is authorized ONLY after this
corrected commit is independently reviewed and pushed. NO P25.1+ code is authorized by this document.**
Date: 2026-07-20 · Supersedes the PROPOSED spec at `3ad4cae` (kept in history; not rewritten).
Baseline: `f534a4c` (code) / `3ad4cae` (docs — the prior PROPOSED spec this corrects). Author:
orchestrator (Opus 4.8); as-built fields independently verified 2026-07-20 (see §17).
Governing plan: `docs/superpowers/plans/2026-07-19-phase-25-grounded-assistant-plan.md`.
Decision authority: `docs/superpowers/plans/2026-07-20-remaining-work-decision-lock.md` §7 + the
2026-07-20 P25.0 decision set (Q-A…Q-G) and its follow-up copy corrections.

> This corrected spec applies the approved decisions: Title-Case source labels (no authority-implying
> wording), a hard **maximum of three visible chips per screen/state**, the approved chip catalog, the
> corrected answer templates (deterministic-schema-check phrasing, precise coverage wording, separated
> Project-Memory axes, deterministic pluralization), and deferral of any chip whose fields are not
> confirmed present. Every field named below is verified against the actual response types and runtime
> payloads (§17). Wording is *(final)* unless marked *(illustrative)*.

---

## 0. Governing constraints (non-negotiable — arc item 8 + decision-lock §7)

Deterministic · guided-prompt-driven · **NO LLM / NO freeform chat** · subordinate to the deterministic
core · source/provenance-labeled · invents no scientific values · **never validates** · never states a
PASS/FAIL or validity conclusion · never silently mutates a record · never bypasses
propose→stage→confirm. The composer is a **pure, synchronous frontend function over already-fetched
bundle data** — **zero new fetches, zero new backend endpoint, zero truth-path change.** The existing
guard `hasVerdictLanguage()` is preserved and runs over *composed* output as a structural backstop.

**Authority-neutrality (hard rule, applies to labels AND copy):** no source label or answer may imply
the assistant itself validates, approves, certifies, or produces a verdict. Truth questions are routed
to the deterministic surface; the assistant echoes already-fetched state and points to sources.

---

## 1. As-built facts this spec builds on (verified 2026-07-20 — see §17 for evidence)

- `AssistantSource = 'schema' | 'audit' | 'git' | 'graph' | 'files'` (`types.ts:162`). `AssistantMessage
  = {text, answeredFrom, sourceDoc?}` (`types.ts:164-168`); `SuggestedPrompt = {text, answeredFrom,
  answer?}` (`types.ts:170-176`). `ASSISTANT_SOURCES = ['schema','audit','git','graph','files']`
  (`assistant.ts:14-20`).
- Guard (`assistant.ts:30-32`): `hasVerdictLanguage(t) = /\b(PASS|FAIL)\b/.test(t) || /\b(in)?valid
  against\b/i.test(t)`.
- Existing assistant constants (`assistant.ts`): `ROUTE_TO_CLI_NOTE` (`:35-36`), `MEMORY_UNAVAILABLE_CAVEAT`
  (`:41-42`, **flagged for replacement — see §6**), `SUBORDINATE_CAPTION` (`:52-53`), `FREEFORM_NOT_WIRED`
  (`:55-56`), `ASSISTANT_SAMPLES` (`:61-179`).
- Bundles already fetched (zero new fetches needed; `apps/web/src/lib/api.ts`):
  - `getRecordBundle` → `{detail, groups, pending, validate, audit, warnings, evidence, graph}` (`api.ts:217-230`).
  - `getExportReadiness` → `{detail, pending, validate, audit, warnings, graph, artifacts}` (`api.ts:235-247`).
  - `getEvidenceBundle` → `{detail, evidence, artifacts, graph, sourcePreviews}` — **no `audit`** (`api.ts:252-266`).
  - `GuidedCompletion` fetches only `{detail, pending}` (`GuidedCompletion.tsx:31-38`).
  - `ProjectMemory` fetches graph status + memory files + concepts across sub-views (`ProjectMemory.tsx:42,308,568`).
- Backend fields the composer may echo verbatim (all confirmed present, §17): validate `{ok,
  errors:[{path,message}], schema, dry_run}`; pending items `{id, kind, question, about?, demo_answer?}`;
  audit `records[].{name, ok, schema_errors[], evidence_present, evidence_expected, uncovered[],
  dangling[]}`; warnings `{code, where, message}` (advisory, non-gating); evidence entry `{path, value?,
  status, evidence[]}` where each `evidence[]` is `{source_type, source_file, locator, quote, …}`
  (`types.ts:29-40`); draft groups `{title, fields[{path,label,value,status,evidence_count,
  source_types}]}`; artifacts `{record, sidecar, record_path, sidecar_path}` (all nullable pre-export);
  `ApiExperimentDetail` includes `source_files: string[]` (`types.ts:284`); experiment `status ∈
  {needs_attention, in_review, ready_to_export, done}`.
- Graph/memory STATUS (`ApiGraphStatus`, `types.ts:408-430`; built `routes.py:548-600`) — **four
  independent axes**, not one combined freshness signal:
  - `availability ∈ {available, unavailable}` (PRIMARY axis).
  - `integrity ∈ {verified, malformed, unsupported, unknown}` — is the snapshot artifact well-formed +
    schema-supported (NOT its contents).
  - `memory_policy ∈ {current, stale, unknown}` — shipped sanitization/exclusion policy+versions vs the
    snapshot's embedded `policy_fingerprint`.
  - `indexed_sources ∈ {current, unknown}` **at runtime** — `stale` (real content drift) is detected
    **only in CI**, never surfaced by the live status. Treat runtime `indexed_sources` as `current` or
    `unknown` only.
  - Also: `provider` (`provider_kind` else `'unavailable'`), `file_count` (number|null — **the value the
    UI renders as "Indexed files"**, `ProjectMemory.tsx:224`), `served_file_count` (number|null —
    **exists but the UI deliberately does NOT render it**, `ProjectMemory.tsx:221-223`), plus
    `node_count/edge_count/community_count/concept_count`, `snapshot_schema_version`,
    `source_graph_commit`, `graph_mtime`, and fingerprints. There is **no** `included_file_count` field.
- The graph-status `note` is **not** arbitrary text: it is one of exactly two curated, user-facing
  strings selected by `availability` (`_GRAPH_STATUS_NOTES`, `routes.py:535-545`). The `/memory/*` `note`
  is the fixed `MEMORY_NOTE = "Project memory returns leads to verify — never a validation verdict."`
  (`routes.py:619`). The composer does not echo `note` raw (§6).

---

## 2. Source-label taxonomy (FINAL — decisions applied)

Enum extension (additive) and the **approved Title-Case display map** (Q-A/Q-B). The internal enum stays
machine-stable; the panel renders the friendly label. **No label implies the assistant validates.**

```ts
// types.ts — extend the union (additive)
export type AssistantSource =
  | 'schema'     // truth-plane gate lives in /validate + official schema; the assistant only routes/echoes counts
  | 'audit'      // evidence-coverage counts from /audit (reporting, not a verdict)
  | 'files'      // per-field provenance, cited source lines (/evidence, /source-preview, /draft)
  | 'advisory'   // soft, non-gating warnings (/warnings)                                   [NEW]
  | 'workflow'   // record/experiment status, pending items, artifacts (/experiments/{id}, /artifacts) [NEW]
  | 'graph'      // Project Memory — concepts, availability, provenance, drift (/graph/status, /memory/*)
  | 'git';       // history — "what changed"

// APPROVED display map (Title Case; rendered as `answered from: <label>`)
export const SOURCE_LABELS: Record<AssistantSource, string> = {
  schema:   'Schema Rules',
  audit:    'Evidence Audit',
  files:    'Evidence & Sources',
  advisory: 'Advisory Checks',
  workflow: 'Workflow & Artifacts',
  graph:    'Project Memory',
  git:      'Project History',
};
```

Removed the prior `'schema validation'` / `'advisory warning'` labels: they implied the assistant
performed validation/adjudication, contradicting §0. `ASSISTANT_SOURCES` grows to the seven values; the
DEV sanity loop keeps checking every sample/composed reply.

---

## 3. Composer contract (FINAL)

A pure, synchronous, side-effect-free function. No fetching; it receives the bundle the screen already
holds.

```ts
export type ScreenContext = 'review' | 'export' | 'evidence' | 'complete' | 'memory';

export type GroundingState =
  | { context: 'review';   bundle: RecordBundle }          // {detail,groups,pending,validate,audit,warnings,evidence,graph}
  | { context: 'export';   bundle: ExportReadinessBundle } // {detail,pending,validate,audit,warnings,graph,artifacts}
  | { context: 'evidence'; bundle: EvidenceBundle; selectedPath?: string } // {detail,evidence,artifacts,graph,sourcePreviews}
  | { context: 'complete'; detail: ApiExperimentDetail; pending: ApiPendingItem[]; selectedPendingId?: string } // {detail,pending} ONLY (Q-D); selectedPendingId picks the active item (added per review 9a, needed at P25.6)
  | { context: 'memory';   graph: ApiGraphStatus };        // graph status only (Q-G scope)

export interface GroundedChip {
  id: string;                              // stable key
  label: string;                           // chip text (≤ ~44 chars, verb-first)
  source: AssistantSource;                 // the plane/category this answers from
  routed?: boolean;                        // truth-question chips that ALWAYS route, never echo a verdict
  resolve(state: GroundingState): AssistantMessage | null; // null → data absent → chip disabled
}

export interface ComposerOutput { reply: AssistantMessage; prompts: SuggestedPrompt[] }
export function compose(state: GroundingState): ComposerOutput;
```

Three-stage pipeline (the reusable "grounding layer" Phase 26 search reuses for stages 2–3):

1. **Prompt → structured query.** Each chip carries a fixed `{intent, source, resolver}` chosen at
   authoring time. **No natural language is parsed.**
2. **Structured query → resolved values.** The `resolver` is a pure selector over `GroundingState`
   reading already-present values (counts, paths, messages, names, statuses). It never derives, formats a
   scientific quantity, computes a ratio, or computes a verdict. Missing data → `null` (chip disabled).
3. **Resolved values → templated reply.** A fixed template interpolates resolved values via a
   **deterministic pluralization helper** (§9) into a short, source-labeled `AssistantMessage`, then
   `hasVerdictLanguage()` runs as a structural backstop before render.

**Loading/error:** if the screen bundle is `loading`/`error`, the panel is not mounted with composed
content — it defers to the screen's existing `LoadingPanel`/`BackendDown`. Individual chips whose
`resolve()` returns `null` are `disabled` (reuse `disabled={!p.answer}`).

---

## 4. Value-echo & no-verdict rules (FINAL — hard rules)

**MAY echo verbatim** (present in fetched state): pending `id`/`about`/`question`; validate
`errors[].path`; audit `evidence_present`/`evidence_expected` and `uncovered[]`/`dangling[]` paths;
advisory `code`/`where`/`message`; evidence `path`/`status` and an entry's `source_type`/`source_file`/
`locator`; a draft field's stored `value` + `source_types` + `evidence_count`; experiment `status`
literal; artifact `record_path`/`sidecar_path`; graph `availability`/`integrity`/`memory_policy`/
`indexed_sources`/`provider`/`file_count`.

**MUST NOT:** synthesize, reformat, unit-convert, round, compute a ratio/percentage, or derive any
scientific value; invent hashes, URIs, paths, descriptors, uncertainties, QC, timestamps; **surface
`validate.ok` as a verdict; conclude a record is valid/invalid; state PASS/FAIL.** For "is it valid /
what blocks export," state a **count of blocking paths** + the paths + route to Validate — using
"deterministic schema check," never "verdict"/"valid"/"invalid".

**Routing phrasing (final).** Blocking-path answers use (via the `count()` helper, §9, so the rendered
form is grammatical — "1 path is listed" / "2 paths are listed"): *"{count(errors.length,'path')} listed
as blocking export: {errors[0..2].path}. Open Validate to run the deterministic schema check."* Empty
error list: *"No blocking paths are listed in the current validation response. Open Validate to run the
deterministic schema check."* Never echo `validate.ok`; never conclude validity.

**Coverage phrasing (final).** *"Coverage is {present}/{expected} evidenced fields. It describes how many
expected fields carry evidence; the schema check is separate."* Coverage is a count, never a validity
determination.

**Graph-note handling (final).** The composer does **not** echo `graph.note` raw. It selects an approved
frontend string by `availability` (available → the leads-to-verify caption; unavailable → the
memory-unavailable caption, §6). This gives the frontend stable control even though the backend `note`
is already curated.

**Guard interaction (verified).** Per-error `errors[].message` reads like *"assets is a required
property"* (`official.py`) and does not contain the guarded phrase; the "valid against" summary lives
only in the CLI render path, never in the API response (§17.10). Templates echo `errors[].path` + a
count and never echo `validate.ok` or any summary — guard-safe and better for density. The guard still
runs over composed output; a dedicated test feeds a verdict-ish payload to assert substitution.

---

## 5. Per-screen contexts, chip catalogs & answer templates (APPROVED — max 3 chips/screen)

Notation: `{…}` = value echoed from fetched state; `count(n,'field')` = deterministic singular/plural
(§9); lists show first **≤3** then "…and K more". Every reply is 1–3 short sentences, exactly one source
label, ≤1 caveat line (the sole documented exception is the memory-freshness chip, §5.5/§9).

### 5.1 Record Workbench (`review`; state = `getRecordBundle`)
| Chip label *(final)* | intent | source → label | Answer template |
|---|---|---|---|
| "What still needs me?" | `pending_summary` | `workflow` → **Workflow & Artifacts** | "{count(pending.length,'field')} still {needs/need} you: {pending[0..2].about}{, …and K more}." · empty → "No pending fields are listed for this record." · absent → chip disabled |
| "What's left before export?" | `blocking_paths` | `schema` → **Schema Rules** | "{count(errors.length,'path')} {is/are} listed as blocking export: {errors[0..2].path}{, …and K more}. Open Validate to run the deterministic schema check." · empty → "No blocking paths are listed in the current validation response. Open Validate to run the deterministic schema check." · never echoes `validate.ok` |
| "Trace a field to its source" | `field_provenance` | `files` → **Evidence & Sources** | For the first evidenced entry: "{path} traces to {source_file}{ (locator: {locator})} — source type: {source_type}." · none → "No cited source is recorded for a field yet." |

Deferred **by the 3-chip cap (not by field-absence — both fields verified present, §17):**
"Is this record valid yet?" (routed) and a record-level Project-Memory provenance chip. The blocker chip
already demonstrates route-to-authoritative-check behavior, so a separate validity chip is redundant.

### 5.2 Ready to Export (`export`; state = `getExportReadiness`; keeps `note = ROUTE_TO_CLI_NOTE`)
| Chip label *(final)* | intent | source → label | Answer template |
|---|---|---|---|
| "Is coverage the same as valid?" | `coverage_vs_validity` | `audit` → **Evidence Audit** | "Coverage is {audit.records[0].evidence_present}/{evidence_expected} evidenced fields. It describes how many expected fields carry evidence; the schema check is separate." · pre-export (`records:[]`) → "No coverage figures yet — coverage appears after export." (chip disabled) |
| "What's left before export?" | `blocking_paths` | `schema` → **Schema Rules** | Same template as §5.1; panel `note = ROUTE_TO_CLI_NOTE` routes to the CLI. |
| "Explain the advisory warning" | `advisory_detail` | `advisory` → **Advisory Checks** | "{warnings[0].code} — {warnings[0].message} (advisory, non-gating; where: {warnings[0].where}){. …and K more}." · none → "No advisory warnings on this record." |

Artifact-path chip intentionally **not** placed here (it lives on Evidence and in the export UI); these
three best explain the distinct audit / schema / advisory planes.

### 5.3 Evidence / File Preview (`evidence`; state = `getEvidenceBundle`; NEW mount; no `audit` → no coverage chip)
| Chip label *(final)* | intent | source → label | Answer template |
|---|---|---|---|
| "Why multiple evidence entries?" | `evidence_multiplicity` | `files` → **Evidence & Sources** | For `selectedPath`: "{path} has {count(len,'evidence entry','evidence entries')}: {evidence[0..2].source_type}{, …and K more}. Multiple entries can corroborate one field." · no selection → "Select a field to trace its evidence." |
| "What is the evidence sidecar?" | `sidecar_convention` | `files` → **Evidence & Sources** | "The evidence sidecar is an assistant convention, not an official ISAAC standard — it preserves field-level evidence the official schema has no slot for." (static) |
| "Where are the exported artifacts?" | `artifact_paths` | `workflow` → **Workflow & Artifacts** | `artifacts.record` → "Exported: record `{record_path}`, sidecar `{sidecar_path}`." · else → "Not exported yet — export writes the record plus its evidence sidecar." |

Renamed per decision: "Is the sidecar an official artifact?" → **"What is the evidence sidecar?"**
(clearer; avoids ambiguity over "official"). **Deferred** (held by the 3-chip cap; fields verified
present, so this is a scope choice): "What files back this record?" (`detail.source_files`). **No
coverage chip on this screen** (no `audit` in the bundle).

### 5.4 Complete Missing Fields (`complete`; state = `{detail, pending}` ONLY — Q-D)
**Advisory only — never submits. No `validate`/`audit`/`graph` fetch added.** Chips ground in `pending`.
| Chip label *(final)* | intent | source → label | Answer template |
|---|---|---|---|
| "Which fields still need me?" | `pending_summary` | `workflow` → **Workflow & Artifacts** | "{count(pending.length,'field')} {needs/need} you: {pending[0..2].about}{, …and K more}. Confirm or skip each below." · empty → "This draft currently has no pending fields listed." |
| "What does this question want?" | `explain_pending_item` | `workflow` → **Workflow & Artifacts** | For the pending item picked by `selectedPendingId` (§3): "{pending[i].question} — about {pending[i].about}. Answer via propose → stage → confirm below." · none selected → "Select a field below to see what it asks." |
| "What if I leave one missing?" | `missing_field_behavior` (routed) | `schema` → **Schema Rules** | "Leaving a field missing keeps it honest-missing — never guessed. Whether it blocks export is a schema question — open Validate to run the deterministic schema check." (static; routes for blocker truth) |

### 5.5 Project Memory (`memory`; state = `graph` status only; **mounted P25.7**)
Every answer carries the leads-to-verify framing; degraded memory is **never** styled red/error. **Max 3
chips at any time.** When `availability === 'unavailable'`, the freshness/scope chips are **replaced**
(not supplemented) by "Why is memory unavailable?" — never four chips at once.

**When `availability === 'available'`:**
| Chip label *(final)* | intent | source → label | Answer template |
|---|---|---|---|
| "Where do these leads come from?" | `memory_provenance` | `graph` → **Project Memory** | "Leads come from indexed project files and concepts{ (provider: {graph.provider})}. Project memory returns leads to verify — never a validation verdict." (drop the parenthetical if `provider` is absent/'unavailable') |
| "Is project memory current?" | `memory_freshness` | `graph` → **Project Memory** | "Snapshot integrity: {integrity}; policy consistency: {memory_policy}; indexed sources: {indexed_sources}." + per-axis caveat (see §6) — axes stated **separately**, never collapsed. |
| "What sources are included?" | `included_scope` | `graph` → **Project Memory** | "This snapshot indexes {count(graph.file_count,'project file')}. That scope covers files already in the snapshot; newly added indexable files require a Graphify refresh." · `file_count` null → "The indexed-file count is unavailable for this snapshot." |

**When `availability === 'unavailable'` (replacement chip):**
| Chip label *(final)* | intent | source → label | Answer template |
|---|---|---|---|
| "Why is memory unavailable?" | `memory_unavailable` | `graph` → **Project Memory** | "Project Memory is unavailable, so no memory-based answer is available here." (approved frontend string by `availability`; NOT raw `graph.note`; NOT "answered from source files directly") |

Scope-chip grounding decision: uses **`graph.file_count`** (the "Indexed files" value the screen already
renders), **not** `included_file_count` (does not exist) and **not** `served_file_count` (exists but the
screen deliberately withholds it — surfacing it would exceed what the screen shows).

### 5.6 Excluded screens (decision-lock)
My Experiments, Load Materials, Settings, Governance are **not** mounted. Not proposed for P25-core.

---

## 6. Caveat rules (FINAL — separated Project-Memory axes)

Project Memory reports **four independent axes**; the assistant **never collapses them into one universal
freshness claim**. The `memory_freshness` chip states each axis it is asked about and appends only the
precise, per-axis caveat that applies (this chip may use up to 3 short sentences — the single documented
exception to the ≤1-caveat rule, required by the "state each axis separately/precisely" decision):

- `integrity ∈ {malformed, unsupported, unknown}` → "Snapshot integrity is {integrity} — the snapshot
  artifact itself could not be fully verified." (`verified` → no caveat).
- `memory_policy === 'stale'` → "The shipped sanitization/exclusion policy or its versions differ from
  what this snapshot was built under." · `memory_policy === 'unknown'` → "Policy consistency: comparison
  could not be established." (state policy inconsistency **separately** from source status).
- `indexed_sources === 'unknown'` → "Indexed-source status: comparison could not be established."
  **`indexed_sources` is never `stale` at runtime** (real content drift is CI-only). *(Documented but
  runtime-unreachable: if a future runtime ever surfaces `stale`, use "One or more included sources no
  longer match the versions verified for this snapshot; newly added indexable files still require a
  Graphify refresh." Do NOT emit this from today's live status.)*
- **Never** say memory is "behind the working tree" — the P24.10 contract is per-fingerprint
  self-comparison of the snapshot, not a working-tree diff.
- `availability === 'unavailable'` → the memory chips are replaced by `memory_unavailable` (§5.5); no
  red/error styling. The existing `MEMORY_UNAVAILABLE_CAVEAT` string ("…answered from source files
  directly") is **flagged for replacement** at P25.7 because the assistant performs no such source
  lookup; the approved wording is "Project Memory is unavailable, so no memory-based answer is available
  here."
- Every available-memory answer carries the leads-to-verify framing.

## 7. Unknown / unavailable behavior (FINAL)
- Missing value → say it is missing/absent; **never guess**.
- `resolve()` returns `null` when its data is absent → chip is `disabled` (existing pattern).
- Bundle `loading` → panel not shown / chip disabled; `error` → defer to `BackendDown`. Never fabricates rows.

## 8. Allowed vs forbidden input (FINAL)
- **Allowed:** clicking a guided chip (primary and only input); keyboard activation via native `<button>`.
- **Forbidden / removed (at P25.2, not P25.1):** free-text entry. The disabled `<input>`+send block
  (`AssistantPanel.tsx`) is removed and replaced by one honest line: **"Guided prompts only — the
  assistant answers the suggested questions above."** `FREEFORM_NOT_WIRED` is retired; a
  `GUIDED_ONLY_NOTE` constant replaces it. **P25.1 preserves the existing free-text block** (removal is
  P25.2).

## 9. Copy-density limits (FINAL)
- **Max 3 visible chips per screen/state** (fewer when a 3rd would be filler). Chip label ≤ ~44 chars,
  verb-first where natural, one question.
- Reply: **1–3 short sentences**, exactly **one** primary source label, **≤1** caveat line — *except* the
  `memory_freshness` chip, which may use up to 3 sentences to report separated axes precisely (§6).
- **At most one** echoed value list per reply; show first **≤3**, then "…and K more" — never a full dump.
- **Deterministic pluralization (hard rule).** No `entr(y/ies)` / `field(s)` / `path(s)` placeholders in
  rendered output. A helper `count(n, singular, plural?)` produces "1 field" / "2 fields", and templates
  select verb forms ("needs"/"need", "is"/"are"). Implemented and unit-tested in the composer.

## 10. Accessibility behavior (FINAL)
- Chips stay native `<button aria-pressed disabled={!answer}>` — **no custom `onKeyDown`**.
- The reply region gains `aria-live="polite"`.
- `section aria-label="Assistant (advisory)"` retained; `answered from: <label>` remains **visible text**
  (via `SOURCE_LABELS`), not color-only.

## 11. Tests (FINAL plan)
- **Unit — `assistantComposer.test.ts` (new):** per context, fixture `GroundingState` → assert exact
  `{reply, prompts}`: value-echo correctness, guard-cleanliness, no fabricated values, `null`/disabled on
  missing data, correct `SOURCE_LABELS`/source per chip.
- **Unit — pluralization:** n=0/1/2 render grammatically correct singular/plural + verb agreement; no raw
  placeholders survive.
- **Unit — verdict resilience:** a `validate`/`errors[].message` payload containing "invalid
  against"/PASS/FAIL → composed reply is guard-substituted/routed, never echoed raw.
- **Unit — Project-Memory axes:** integrity/memory_policy/indexed_sources reported as separate rows;
  `indexed_sources` fixture is only `current`/`unknown` (a `stale` fixture asserts the runtime path never
  emits it); `unknown` → "comparison could not be established"; unavailable → approved replacement
  string (never "answered from source files directly"); scope chip grounds on `file_count`.
- **Screen integration:** each mounting screen renders the composed reply from a live bundle fixture;
  backend-down → honest state; memory-unavailable → replacement chip, no red.
- **Regression — `assistant.test.tsx`:** guard still strips; (P25.2) no free-text box + "Guided prompts
  only"; `answered from:` present on every reply; no hardcoded field-count claims; DEV sanity loop runs
  over composer outputs. Existing assertions preserved/adapted (never silently deleted).
- **Invariants untouched:** no-fake-search, no-vertical-rail unchanged; backend suite re-run to prove the
  truth path is untouched.

## 12. Exact files & contracts (FINAL)
New/edited (frontend only — **zero** `apps/api/**`, `src/**`, `schema/**`):
- **New** `apps/web/src/lib/assistantComposer.ts` — `compose()`, resolvers, `GroundedChip`, per-context
  `CATALOG`, the `count()` pluralization helper.
- `apps/web/src/lib/types.ts` — extend `AssistantSource` (+`advisory`,`workflow`); add `ScreenContext`,
  `GroundingState`, `GroundedChip`, `ComposerOutput`.
- `apps/web/src/lib/assistant.ts` — grow `ASSISTANT_SOURCES`; add the Title-Case `SOURCE_LABELS`,
  `GUIDED_ONLY_NOTE`, and a memory-available/leads const; **replace** the `MEMORY_UNAVAILABLE_CAVEAT`
  string (§6, P25.7); retire `FREEFORM_NOT_WIRED` (P25.2); (last slice) delete `ASSISTANT_SAMPLES` +
  migrate the DEV sanity loop.
- `apps/web/src/components/AssistantPanel.tsx` — render `SOURCE_LABELS[...]`; (P25.2) remove free-text
  block; add `aria-live`; add the guided-only line.
- `apps/web/src/components/assistant.css` — (P25.2) remove free-form styles.
- Screens: `RecordWorkbench.tsx` (P25.1), `ExportReadiness.tsx`, `EvidenceExplorer.tsx` (new mount),
  `GuidedCompletion.tsx` (new mount), `ProjectMemory.tsx` (new mount).
- Tests as §11; doc `docs/ui-handoff/ai-assistant-and-graphify.md`.
Forbidden: everything under `apps/api/**`, `src/isaac_records/**`, `schema/**`; the no-fake-search tests;
the propose→stage→confirm flow in `GuidedPrompt.tsx` (advise around it, never drive it).

## 13. Bite-sized P25.1+ slices (NONE authorized until this corrected spec is reviewed + pushed)
- **P25.1** — pure composer skeleton (tests first) + `AssistantSource` +`advisory`/`workflow` +
  Title-Case `SOURCE_LABELS` rendering + wire **RecordWorkbench only**; preserve free-text block; other
  screens unchanged; no new fetch/route; no truth-core/schema change. Model: Opus 4.8 subagent.
- **P25.2** — free-text removal + "Guided prompts only"; adapt `assistant.test.tsx`. Model: Sonnet.
- **P25.3** — *(tombstone — folded into P25.1)*.
- **P25.4** — ground the Export context. Model: Opus.
- **P25.5** — ground + **mount** the Evidence context. Model: Opus.
- **P25.6** — ground + **mount** the Complete context (advisory-only; pending-grounded). Model: Opus.
- **P25.7** — ground + **mount** Project Memory (separated axes; replace `MEMORY_UNAVAILABLE_CAVEAT`). Model: Opus.
- **P25.8** — *(excluded by default)* non-record screens. Model: Opus.
- **P25.9** — retire `ASSISTANT_SAMPLES` + migrate the DEV sanity loop. Model: Sonnet.
- **P25.10** — full verification (frontend + backend) + docs + preview QA. Final stop gate.
Every slice: one subagent, independently reviewable, its own stop gate; orchestrator reviews each diff
and never implements production code.

## 14. Visual / copy examples (corrected — one normal + one degraded per screen)

> Example `about`/`path` values below are illustrative renders of real echoed fields (real `about`
> derives from the pending item's URI/blocker); `source_type` values are drawn from the actual
> `SourceType` enum (`types.ts:12-19`: spreadsheet, file_listing, derivation, user_confirmation,
> document, screenshot, web_form).


**Record Workbench** — normal / degraded (empty error list):
```
2 fields still need you: sample environment temperature, and reduced-spectrum URI.
answered from: Workflow & Artifacts
```
```
No blocking paths are listed in the current validation response. Open Validate to run the deterministic schema check.
answered from: Schema Rules
```

**Complete Missing Fields** — normal / degraded (routed missing-field behavior):
```
3 fields need you: beamline id, monochromator crystal, and i0 gas mix. Confirm or skip each below.
answered from: Workflow & Artifacts
```
```
Leaving a field missing keeps it honest-missing — never guessed. Whether it blocks export is a schema question — open Validate to run the deterministic schema check.
answered from: Schema Rules
```

**Evidence / File Preview** — normal / degraded (no selection):
```
$.spectra[0].reduced_uri has 2 evidence entries: document, spreadsheet. Multiple entries can corroborate one field.
answered from: Evidence & Sources
```
```
Select a field to trace its evidence.
answered from: Evidence & Sources
```

**Ready to Export** — normal / degraded (pre-export):
```
Coverage is 11/14 evidenced fields. It describes how many expected fields carry evidence; the schema check is separate.
answered from: Evidence Audit
```
```
No coverage figures yet — coverage appears after export.
answered from: Evidence Audit
```

**Project Memory** — normal / degraded (policy stale, sources unknown — the runtime-possible degraded state):
```
Snapshot integrity: verified; policy consistency: current; indexed sources: current.
answered from: Project Memory
```
```
Snapshot integrity: verified; policy consistency: stale; indexed sources: unknown.
The shipped sanitization/exclusion policy or its versions differ from what this snapshot was built under. Indexed-source status: comparison could not be established.
answered from: Project Memory
```
*(Corrected from the prior spec's "indexed sources: stale" example — that state cannot occur at runtime;
`indexed_sources` is only `current`/`unknown` live, drift is CI-only.)*

## 15. Resolved decisions (2026-07-20) — replaces the prior open approval questions
- **Q-A** — enum `'workflow'` approved; Title-Case `SOURCE_LABELS` approved (§2), replacing the
  authority-implying labels.
- **Q-B** — friendly-label rendering lands in P25.1.
- **Q-C** — chip catalogs approved with the corrections applied in §5 (rename, deferrals, template fixes).
- **Q-D** — Complete grounds on `{detail, pending}` only; no added validate/audit fetch.
- **Q-E** — Evidence has no `audit`; coverage stays on Export.
- **Q-F** — max 3 chips per screen/state; ≤3 echoed items before "…and K more".
- **Q-G** — Project Memory mounts in P25.7 with separated integrity/policy/indexed-sources axes, exact
  included-source scope via `file_count`, the Graphify-refresh limitation, and leads-to-verify framing.

## 16. Stop
This spec is docs-only. **No P25.1+ code is authorized by this document.** P25.1 (composer skeleton +
Title-Case source-label rendering on RecordWorkbench) is authorized only after this corrected commit is
independently reviewed and pushed.

## 17. As-built field verification (2026-07-20) — provenance for §1
Independent read-only verification against the actual response types and runtime payloads. Notable
outcomes that corrected earlier assumptions:
1. `AssistantSource` = 5 members (`types.ts:162`); `hasVerdictLanguage` regex `assistant.ts:30-32`.
2. `getEvidenceBundle` has **no `audit`** (`api.ts:252-266`) — confirms coverage stays off Evidence.
3. `GuidedCompletion` fetches only `{detail, pending}` (`GuidedCompletion.tsx:31-38`) — Q-D honored.
4. **`ApiExperimentDetail.source_files` EXISTS** (`types.ts:284`; `routes.py:83`) — the deferred
   "What files back this record?" chip is field-safe; its deferral is a 3-cap scope choice.
5. **Evidence entry has `source_type`, `source_file`, `locator`, `quote`** (`types.ts:29-40`) — the
   provenance chip's fields are verified present.
6. **`included_file_count` does NOT exist.** The served count is `served_file_count` (number|null,
   `types.ts:416`) — **not rendered by the UI** (`ProjectMemory.tsx:221-223`). The UI renders
   `file_count` as "Indexed files" (`types.ts:426`; `ProjectMemory.tsx:224`). The scope chip grounds on
   `file_count`.
7. **Freshness is four independent axes**; `indexed_sources` is `current`/`unknown` at runtime and
   **never `stale`** live (drift CI-only) — `memory.py:246-292`; `docs/project-memory-map.md:94-98`.
8. `graph.note` is one of two `availability`-keyed curated strings (`routes.py:535-545`), not arbitrary;
   the composer selects a frontend string by `availability` instead of echoing it.
9. audit records fields confirmed (`serialize.py:87-90`); validate `{ok,errors:[{path,message}]}` with no
   PASS summary in the API (`routes.py:381`; summary is CLI-only, `official.py:60-61`).
10. artifacts + draft-group fields confirmed (`types.ts:375-380`, `286-298`).
