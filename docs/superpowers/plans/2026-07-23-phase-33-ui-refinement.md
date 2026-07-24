# Phase 33 — UI/UX Refinement · Issue Register & Plan

**Status:** 33.0 read-only audit complete — awaiting independent review, then prioritized slices.
**Owner:** orchestrator (Opus 4.8, ratified fallback for Fable 5).
**Created:** 2026-07-23.

Goal: substantially improve ISAAC's frontend presentation, information hierarchy,
responsiveness, interaction quality, and perceived polish **without changing the truth
architecture, scientific contracts, or confirmed-write surface**. This is a refinement
phase, not a rewrite.

---

## 1. Immutable Phase 32 Baseline (preserved before any Phase 33 edit)

Verified 2026-07-23 before implementation:

| Axis | Value |
|---|---|
| Branch | `main` |
| HEAD | `46eea62e42cbd28c263e7b7381e52a66dd2904ae` |
| `origin/main` | `46eea62` (0 ahead / 0 behind) |
| Working tree | clean |
| Exact-HEAD CI | completed / **success** |
| Railway | healthy — `mode: synthetic-only`, serving `46eea62`, core `isaac_records`, v0.1.0 |
| Vercel (`isaac-demo-web.vercel.app`) | HTTP 200 |
| Backend / Frontend tests | 894 / 550 (per Phase 32 closure) |
| TypeScript / Vite build / snapshot gate | pass / pass / 17-17 |
| Phase 32 register | 0 unresolved Critical / Important |

**Release tag:** the repository has **no tag convention** (`git tag -l` empty). Per the
directive ("do not invent a tagging convention if the repository has none"), **no tag was
created**; this row is the immutable baseline of record. If a tag convention is later
adopted, `46eea62` is the Phase 32 baseline to annotate.

---

## 2. Methodology

- **Live hosted read-only visual audit** (`isaac-demo-web.vercel.app`, deploy commit
  `46eea62`) at desktop width (1440), observation-only — no auth capture, no mutation.
- **Live CSSOM/DOM measurement** for the responsive assessment (real `window`/`document`
  probes, not fabricated screenshots).
- **Read-only design-system + screen code inventory** (subagent, evidence at `file:line`).
- Routes/states covered live: dashboard (loading + loaded 2/1/1/1), RecordWorkbench (New
  Draft with confirmation banner), Exported record (completed spine), Evidence Explorer
  (classification + CSV reconcile + source preview), Export Readiness, Project Memory,
  global Search dialog (+ Escape/focus behavior), console cleanliness.
- **Honest coverage gaps** (dispositioned in §6, not fabricated): interactive mutation
  journey, conflict/stale/offline/error runtime states, two-window live-sync,
  `absent_from_record`, narrow-viewport *rendering*, GuidedCompletion answer flow interior,
  Reset-Demo dialog interior, Assistant long-message / Jump-to-Latest, Governance/Settings
  placeholders (inventory-covered).

Design direction (preserved): Scientific Clarity, light-first, premium restraint, minimal
noise, strong hierarchy, Title Case, honest state labels, clear provenance, accessible,
calm. Avoid: admin-dashboard styling, excess chrome, fake insights, color-only status,
hidden primary actions, redesigning scientific semantics.

**Overall assessment:** the product is already honest, calm, and functional, with a
centralized token system and strong accessibility fundamentals (landmarks, `aria-live`,
`aria-current`, icon+text status, tested dialog focus). Findings are **refinement-level**:
**0 Critical.** The Export Readiness screen and SourcePreview are the internal quality bar;
several other surfaces fall short of it.

---

## 3. Findings

Severity is deliberately un-inflated. Fields per finding: route/component · file · current
behavior · impact · a11y · responsive · severity · proposal · acceptance · tests · hosted
QA · deps · status. Compact table form; long-form notes follow where needed.

### Priority 1 — misleading/confusing state presentation

| ID | Route/Component | File | Severity | Finding |
|---|---|---|---|---|
| ST-1 | Version chip — `LeftNav.tsx:45` (`.nav-version`) + `SettingsPage.tsx:25` (NOT a footer; NOT on record/evidence screens, which use WorkflowSpine) | `apps/web/src/lib/labels.ts:102` | Minor | The version label hardcodes `isaac v0.1.0 · local`; the hosted production build displays "· local", a dev environment label. Mildly misleading provenance. (Independent review corrected the attribution: the string is not in the `<footer>`/StatusBar and does not appear on every screen; the single fix source is still `labels.ts:102`.) |

**ST-1** — Proposal: derive the environment suffix from build mode (`import.meta.env`) or drop
the "· local" literal so production does not read "local"; keep version honest. Acceptance:
hosted footer shows an accurate environment (or version only), never "local" in production.
Tests: `labels.test.ts` update. Hosted QA: yes (footer read). Deps: `labels.ts` is
snapshot-manifest-listed → regenerate snapshot in the same commit. Note: not a truth-plane
change.

### Priority 2 — accessibility

| ID | Route/Component | File | Severity | Finding |
|---|---|---|---|---|
| A11Y-1 | RecordWorkbench, EvidenceExplorer, Governance, Settings, ProjectMemory | screens + `AppShell`/`TopBar` | Important | Inconsistent document outline: RecordWorkbench & EvidenceExplorer expose **no screen-level `h1`** (record title is a `<span>` in TopBar); Governance/Settings/ProjectMemory **start at `h2`** (no `h1`); ProjectMemory **skips** `h3→h5→h6`. Screen-reader navigation by heading is uneven. |
| A11Y-2 | assistant | `apps/web/src/components/assistant.css:386` | Minor | References `var(--surface-sunken, …)` — a token **not defined** in `tokens.css`; renders via fallback only. Latent correctness/maintainability bug (not user-visible today). |
| A11Y-3 | Full-variant screens (Home/Memory/Governance/Settings) | `AppShell` | Minor | These variants mount no `<footer>`/contentinfo landmark (only record/evidence variants do); landmark coverage is asymmetric. Not an error, but uneven. |

**A11Y-1** — Proposal: give every routed screen exactly one `h1` (visually-hidden where the
TopBar already shows the title), and fix ProjectMemory's level skips. Acceptance: each route
has exactly one `h1`; no skipped levels; axe/heading-order test passes. Tests: heading-outline
unit tests per screen. Hosted QA: light (screen-reader outline is code-verified; DOM check
live). This is safe presentation only.

### Priority 3 — responsive

| ID | Route/Component | File | Severity | Finding |
|---|---|---|---|---|
| RESP-1 | Whole app | all CSS | Important | The deployed app declares `<meta viewport width=device-width>` **but ships zero width media queries** (live CSSOM: `hasAnyMediaQuery = 0`) with fixed-width chrome (LeftNav 230px, WorkflowSpine 212px, EvidenceTrailPanel 404px, record-right 342/308px; centered cols 1040/720px). On a phone/narrow viewport the layout renders at desktop width, forcing pinch-zoom / horizontal scroll. |

**RESP-1** — Proposal (phased, refinement-scoped, **not** a full mobile app): introduce a
small breakpoint set; at tablet (≥768px) the three-pane record/evidence layouts stack and
content columns become fluid so there is **no horizontal page scroll**; at phone width the
LeftNav collapses to a top/hamburger pattern and fixed side panels stack. Acceptance:
`document.documentElement.scrollWidth <= clientWidth` at 768px and 390px on dashboard,
record, evidence, export; primary actions remain visible; no content clipped. Tests:
add jsdom layout/reflow assertions where feasible + explicit human narrow-viewport QA.
Hosted QA: **human-only rendering** (automation viewport would not honor sub-desktop
resize — see §6). Largest single effort in the phase; may be split into shell-reflow then
per-screen passes.

### Priority 4 — navigation & interaction friction

| ID | Route/Component | File | Severity | Finding |
|---|---|---|---|---|
| NAV-1 | Global Search dialog | `apps/web/src/components/SearchDialog.tsx` | Important | Query "facility" returns **five identical rows** — "Facility Name / matched draft field label" — with no parent-record context, so results are indistinguishable. Field-path matches (Beamline/Endstation) do show the matched path and read better. |

**NAV-1** — Proposal: each workspace result row shows the owning experiment/record label (and/or
status) so duplicate field-label hits are distinguishable; keep the matched-path affordance.
Acceptance: for a term matching N records, the N rows are individually distinguishable by
record. Tests: SearchDialog result-rendering test with fixture yielding duplicate labels.
Hosted QA: yes.

### Priority 5 — information hierarchy

| ID | Route/Component | File | Severity | Finding |
|---|---|---|---|---|
| HIER-1 | Dashboard experiment cards | `ExperimentRow`/`ExperimentQueue` + `queue.css` | Important | (a) All five card titles share the long identical prefix "Synthetic XANES — CuO (Cu K-edge) · …"; the distinguishing state is at the end, hurting scannability. (b) Right-rail status affordance is inconsistent: Needs-Attention cards show an amber "N Fields Need You" chip and Done shows "Exported", but In-Review and Ready-to-Export cards show **only a chevron** (no status chip). |
| HIER-2 | Confirmation banner ("N Fields Need Your Confirmation") | needsyou-banner (`screens.css`) + RecordWorkbench | Important | The two-column (question \| locator) layout wraps long `ssrl-archive://…` locators **mid-token** (`notebooks`→`n/otebooks`, `spectrum`→`spec/trum`, `evidence_record`→`evid/ence_record`) and the full URI is **duplicated** (inline in the question *and* in the locator column). Poor readability; dents scientific credibility. |

**HIER-1** — Proposal: reduce the shared title prefix's visual weight (or elide it) and
emphasize the distinguishing suffix; give every card a consistent right-side status chip
matched to its group (In Review, Ready to Export) so the rail reads uniformly. Preserve the
canonical 2/1/1/1 grouping and counts. Acceptance: each group's cards carry a status chip;
distinguishing text is the most prominent token in the title; 2/1/1/1 intact. Tests: queue
render tests asserting a chip per card + status labels. Hosted QA: yes.

**HIER-2** — Proposal: single readable question line; show each locator **once** as a mono token
in an `overflow-x:auto` container that never breaks mid-token (`word-break` guarded), or
truncate-with-title. Do not alter which fields are requested or their semantics. Acceptance:
no mid-token wrapping at desktop and narrow width; URI shown once; `Review & Answer` stays
reachable. Tests: banner render test with a long locator asserting no forced mid-token break
markup + single occurrence. Hosted QA: yes.

### Priority 6 — component consistency

| ID | Route/Component | File | Severity | Finding |
|---|---|---|---|---|
| COMP-1 | App-wide clickables | `base.css` + many | Important (maintainability) | 5 canonical `.btn` variants exist, but ~20 bespoke button-styled elements bypass them (`.icon-btn`, `.copy-btn`, `.nav-item`, `.tab`, `.search-result-btn`, `.assistant-*`, `.spine-step-link`, …). Interaction language is fragmented; hover/focus/disabled states diverge. `.btn-primary:disabled` uses hardcoded hex, not tokens. |
| COMP-2 | Tokens | `tokens.css` + all | Minor (maintainability) | No type-scale and no spacing-scale tokens: **18 literal font sizes** (9.5–30px) and all padding/margin/gap are raw px; radius tokens exist but are frequently bypassed by literals (13/9/8/7/6/5/4/3px, literal `999px`). Highest-volume inconsistency; invisible per-screen but compounds drift. |

**COMP-1/COMP-2** — Proposal: introduce a small **type scale** and **space scale** as tokens
(design-system primitives — explicitly in scope) and migrate the **highest-visibility**
surfaces incrementally; consolidate the most-used bespoke clickables onto shared focus/hover
primitives. **Not** a big-bang refactor — scoped, screen-by-screen, each with a review.
Acceptance: new scale tokens defined and adopted on the touched surfaces; no visual regression;
`.btn-primary:disabled` tokenized. Tests: token presence + focus-visible assertions on migrated
controls. Hosted QA: spot visual. Deps: foundational; sequence before the polish slice.

### Priority 7 — visual polish

| ID | Route/Component | File | Severity | Finding |
|---|---|---|---|---|
| POL-1 | Dashboard loading | `ExperimentsHome` / `FetchStates` | Minor | Loading state is a single dot + "Loading your experiments…" — sparse for the primary screen. |
| POL-2 | ProjectMemory (and centered screens) | `screens.css` | Minor | On a 1440 screen the content sits in a ~640px left column leaving the right ~half empty — unbalanced whitespace ("oversized empty area"). |
| POL-3 | Evidence classification list | `EvidenceClassificationPanel`/`classification.css` | Minor | Long run of near-identical rows repeating "Backed by observed evidence." + `spreadsheet` + locator; differentiation is low (mitigated where classes differ — derivation / user_confirmation / file_listing do vary). |
| POL-4 | WorkflowSpine locked steps | `WorkflowSpine.tsx`/`workflow.css` | Minor | The helper line "Complete 'Complete Metadata' first." repeats on every locked step (×3). |

Polish proposals: POL-1 a considered loading treatment (skeleton or calmer indicator);
POL-2 center the column or use the space (e.g. a related-leads rail) without inventing fake
insights; POL-3 condense repeated backing text / emphasize non-supported classifications;
POL-4 show the gating hint once. Acceptance: no functional/semantic change; visual review +
existing tests green. Hosted QA: spot visual.

### Not a defect / working as intended (no change)

- **Export Readiness** — clear PASS gate, honest "coverage · not a verdict", non-gating
  advisory, doubly-gated download. Quality bar; keep.
- **SourcePreview** — line-numbered read-only CSV with tabs; synthetic labeling explicit. Keep.
- **CSV Reconcile panel (idle)** — review-only contract is visually obvious (strong "does not
  change the official record" + synthetic-only banners); no import affordance. Keep.
- **Status system** — icon+text everywhere; unconfirmed/absent kinds dashed; not color-only. Keep.
- **Dark mode absent** — light-first is the intended design direction; out of scope unless
  explicitly requested. Not a defect.

---

## 4. Prioritized Slice Sequence (small, reviewable, no broad rewrite first)

Ordered by the directive's priority ladder, front-loading contained high-impact fixes and
sequencing the one foundational (tokens) slice before polish. Each slice runs the full
per-slice loop (reproduce → failing test → delegate to Opus/Sonnet → focused+full FE tests →
tsc → build → a11y → snapshot check/regen → independent Opus review → deploy → hosted QA →
commit → CI → checkpoint).

- **S1 — State honesty + quick a11y bug:** ST-1 (footer env) + A11Y-2 (undefined token). Small, low-risk, snapshot-touching (labels.ts). Good warm-up slice.
- **S2 — Heading outline / landmarks:** A11Y-1 (+ A11Y-3). Presentation-only, test-heavy.
- **S3 — Search result disambiguation:** NAV-1.
- **S4 — Dashboard card hierarchy + consistent status chip + loading polish:** HIER-1 + POL-1.
- **S5 — Confirmation-banner long-locator readability:** HIER-2 (+ POL-4 spine text).
- **S6 — Responsive foundation:** RESP-1 (shell reflow + fluid columns; phone nav). Largest; may split S6a shell / S6b per-screen.
- **S7 — Design-system primitives + remaining polish:** COMP-1/COMP-2 (type/space scale, button consolidation on touched surfaces) + POL-2 + POL-3. Foundational tokens land here and are adopted incrementally.

Sequence is a proposal for independent review; it may reorder. S6 (responsive) is the
highest-effort item and the most likely to be split or to carry explicit human narrow-viewport
QA.

---

## 5. Scope Boundaries (in force)

May change: layout, spacing, typography, component composition, navigation clarity, status
presentation, empty/loading/error presentation, responsive behavior, keyboard/focus, tooltips
& copy, design-system primitives, safe frontend state presentation.

Must **not** change without a hard gate: ISAAC schema, truth authority, evidence
classification, validation/export semantics, confirmed-write surface, CSV reconciliation-only
policy, runtime-retrieval authority, Project-Memory authority, storage/DB, auth, external
services, real/private-data policy. No new features to fill space. Truth path (CLAUDE.md §13)
untouched; deterministic core stays Graphify-free.

---

## 6. Human-Only Verification (carried forward + Phase 33 additions)

Not fabricated; require a human at a real browser/device:

- **Narrow-viewport rendering** (RESP-1 verification) — the automation window resized to 390px
  but the rendered viewport stayed at 1440 (`window.innerWidth` verified). The *defect* is
  proven from the live CSSOM (zero media queries + fixed widths); the *fix* must be verified by
  a human in DevTools device mode / a real phone.
- Full authenticated interactive mutation journey (confirm-field → recompute → export).
- Two-visible-window live synchronization.
- Exported-artifact `stale` transition.
- `absent_from_record` reconciliation row.

These do not block the read-only audit or presentation-only slices.

---

## 7. Register Status

| Category | Count |
|---|---|
| Critical | 0 |
| Important | A11Y-1, RESP-1, NAV-1, HIER-1, HIER-2, COMP-1 (6) |
| Minor | ST-1, A11Y-2, A11Y-3, COMP-2, POL-1..4 (8) |
| Not a defect | Export Readiness, SourcePreview, CSV idle, status system, dark mode |
| Human-only | 5 (see §6) |

Next: independent Opus review of this register/sequence, then S1.

---

## 8. FINAL LOCKED PLAN (approved 2026-07-23 — authoritative; supersedes §4 sequencing)

Negotiated across a multi-round Claude↔GPT plan debate; approved by Krish with five final
corrections. This section is the authoritative Phase 33 scope. §3 audit findings that align are
folded in; RESP-1/A11Y-1 promoted into scope (S5/S6); NAV-1 (search) deferred (§9); COMP tokens
handled only as needed (no big-bang).

**Hard functional boundary:** strictly visual / layout / copy-hierarchy / responsive / a11y.
No change to assistant abilities/routing/suggested-question behavior, validation, evidence
classification, workflow/missing-field computation, confirmation, export, CSV reconciliation-only,
confirmed-write, no-guessing, record truth, runtime retrieval, Project-Memory authority, search
ranking/retrieval, API behavior, backend persistence, ISAAC schema, or truth-path code. No fake
answers/validation/evidence/statuses, no invented memory states, no second evidence/status system,
no parallel component library. Truth path (CLAUDE.md §13) untouched; core stays Graphify-free.

### Locked decisions (D1–D12)
- **D1 Dashboard title/badges:** canonical title `Synthetic XANES — CuO (Cu K-edge)`; remove
  lifecycle suffixes (New Draft / Partially Completed / Export Review Required / Ready to Export /
  Exported Record); remove the separate technique badge; metadata row = one lifecycle badge
  (`Draft`/`Exported`) + one neutral date badge (visible `Jul 12, 2026`, accessible
  `Created July 12, 2026`).
- **D2 Dashboard right side:** Needs Attention → actionable field-count chip; In Review /
  Ready to Export / **Done** → chevron only. `Exported` appears only as the Done lifecycle badge,
  never repeated on the right. No nested buttons; card is the single click target. Accessible
  card name = title + lifecycle + group state + field count. `2/1/1/1` preserved. Never a verdict
  (protects `adapt.ts:64-65`).
- **D3 Honest composer box:** present now, visual-only. Persistent helper before interaction
  (`Guided Questions Only — choose a suggested question below for an answer.`); on unsupported
  submit an accessible inline `Free-form questions are not supported in this build. Choose one of
  the suggested questions below.` (no "Coming Soon"). No network / answer / history / persistence /
  log / mutation / rerouting. Secondary visual hierarchy. Suggested questions unchanged.
- **D4 Assistant order:** heading+availability → composer → suggested questions → existing answer
  region/history → compact provenance → one advisory footer. **Do not invent a conversation stream
  if the component holds one answer** (R2). Newest at bottom if a stream already exists. Dedupe
  the repeated disclaimers.
- **D5 Assistant rail treatment:** one shared light translucent lavender/indigo rail (existing
  `--assist` tokens), white/lightly-tinted inner cards, restrained purple accent, accessible
  contrast, not louder than the main task. Applied to Project Memory, Record editor, Guided
  Completion, Evidence Explorer.
- **D6 Project Memory:** internal tabs Overview / Sources / Concepts (not global nav); assistant
  in the right rail across all three; Overview omits the full Source Index + Concept Lookup;
  Source Index → Sources, Concept Lookup → Concepts.
- **D7 Memory availability:** one accessible `Memory Available` state, green dot only when the
  existing backend contract reports availability; no invented states; remove only the redundant
  adjacent `memory plane` label; keep the meaningful memory-plane-vs-truth-plane explanation.
- **D8 Evidence placement:** right rail assistant-only; compact `Evidence Trail · N Entries`
  destination beneath the workflow steps → navigates to and reuses the existing `/evidence`
  `EvidenceExplorer` route; compact inline field-evidence beside/below the relevant field. No new
  route/state/API/classifier/second system.
- **D9 Missing-fields (presentation-only formatter, C2):** numbered summary; leaves backend
  questions / answer mapping / missing-field computation / confirmation / validation unchanged;
  uses existing structured metadata (type/field/locator) to render a concise label + locator
  **once**; demotes raw identifiers (`required_for_evidence_record`, `reduced_spectrum`); **falls
  back to the full original question** when no safe structured presentation exists; never parses
  or guesses a locator/scientific meaning from arbitrary text. Guided Completion keeps the complete
  original question. Dynamic count.
- **D10 Casing:** Title Case for page titles/nav/tabs/buttons/section+card headings/badge+status
  labels/workflow step labels; sentence case for questions/task sentences/body/helper/errors/
  assistant responses; preserve exact scientific/technical casing (XANES, Cu K-edge, sha256, paths,
  schema paths, IDs, hashes, units, filenames, user values). No blanket transform; centralize labels.
- **D11 Responsive + a11y** on every touched screen (targeted, not a mobile redesign). Narrow →
  assistant collapses behind a clear `Assistant` control (slide-over drawer built in S2, polished
  in S6); do not compress side-by-side into unusable widths.
- **D12 Search disambiguation deferred** (future UI-clarity ticket; S6 pull-forward only if
  strictly presentational + context already on the result object + low-risk + explicit approval).

### Refinements (R1–R5)
R1 present existing question content via the formatter, not hand-rewritten copy. R2 reorder only;
no invented history. R3 narrow-viewport verification human-assisted (automation viewport pinned at
1440; verified). R4 responsive target = no horizontal overflow + usable stacking/collapse. R5
identical synthetic titles are an accepted outcome (group + field-count disambiguate).

### Five final corrections (C1–C5)
C1 Done right side chevron-only, `Exported` only as lifecycle badge. C2 presentation-only
missing-fields formatter with safe fallback (see D9). C3 composer limitation visible before
interaction (see D3), no "Coming Soon". C4 icon a11y: decorative `aria-hidden`; icon-only controls
need accessible names; semantic status icons need text equivalent; no redundant names. C5 no
speculative S0 primitives — introduce each in its first consuming slice with a named consumer +
reuse justification; extend existing (`StatusChip`, `.tab`, tokens, `.btn`, dots, evidence
components, routes) rather than parallel builds.

### Slice order (each runs the full 32-step per-slice loop)
- **S0 · Plan Lock & Minimal Foundations** — write this locked plan + register + ledger; map
  screenshots→routes; record befores; lock rules; confirm reuse strategy. Docs only; no
  speculative files.
- **S1 · Dashboard cards** (D1, D2, C1).
- **S2 · Shared Assistant shell, app-wide** (D3, D4, D5, C3) — lands before S3/S4.
- **S3 · Project Memory** (D6, D7).
- **S4 · Record editor + Guided Completion + Evidence** (D8, D9, C2).
- **S5 · Casing + semantic headings + keyboard/focus/non-color/touch-target a11y** (D10, C4, A11Y-1).
- **S6 · Responsive residuals + 200% zoom + long-content + final visual QA + closure** (D11, RESP-1;
  D12 search only if qualified).

### New primitives + first consumers (C5)
AssistantRail → S2 (4 surfaces) via extending `AssistantPanel` + `--assist`. NumberedActionList →
S4 only. TechnicalLocator helper → S4 only if summary + evidence both reuse it. MetadataBadge → S1
only if no existing neutral chip/`.meta` works. SectionTabs → S3 only if `.tab` insufficient. No
unused files in S0.

### §9. Deferred (explicit)
- **Free-form assistant Q&A** — real backend behind the D3 box; separate approval-gated phase;
  must never fabricate/validate.
- **Search-result disambiguation** (NAV-1) — future UI-clarity ticket (D12).
- Full mobile redesign — out of scope.

### Human-only QA (from §6): narrow-viewport rendering, full mutation journey, two-window live-sync,
exported-artifact stale, `absent_from_record`. Not fabricated.

### Manifest note (corrected)
The served-content-manifest members among the files this phase touches are the frontend source
files (`lib/labels.ts`, `lib/types.ts`, `lib/status.ts`, `lib/adapt.ts`, `components/AssistantPanel.tsx`,
`screens/ProjectMemory.tsx`, `screens/RecordWorkbench.tsx`, `components/GraphStatusChip.tsx`, etc.) —
regenerate `memory-snapshot.json` deterministically in the same commit whenever any of them is touched
(CLAUDE.md §17). The plan docs themselves — **this register and the master ledger — are NOT manifest
members** (verified: editing them produces no snapshot drift), so doc-only commits need no regeneration.

---

## 10. PHASE 33 CLOSURE (CLOSED 2026-07-23 — code HEAD `2f51d84`)

Final independent whole-phase Opus review (`46eea62..2f51d84`): **SHIP** — all 7 completion-gate
criteria PASS, truth path provably untouched, no-functionality boundary holds, no parallel systems,
build + 621 FE tests + snapshot gate green, 0 Critical / 0 Important.

### Slice ledger
| Slice | Code commit | Doc commit |
|---|---|---|
| S0 plan lock | `7434c26` | (in S0) |
| S1 dashboard | `3ab9a1b` | `8cd253d` |
| S2 assistant shell | `9364f21` (+fix `a4e8f36`) | `bc750c6` |
| S3 Project Memory | `c7b7825` | `b8b491e` |
| S4 record editor + evidence | `5665132` | `b55f30a` |
| S5 headings/casing/a11y | `ee7f5f6` | `cf5c29c` |
| S6 responsive/drawer/search/cleanup | `2f51d84` | this closure commit |

### Terminal disposition — decisions & findings
- **D1–D12 all SHIPPED.** D1 dashboard title/badges · D2 right-side declutter · D3 honest composer ·
  D4 assistant order · D5 lavender rail · D6 memory tabs + right-rail assistant · D7 single green
  "Memory Available" · D8 evidence out of the rail · D9/C2 numbered banner formatter · D10 casing tiers ·
  D11 responsive · D12 search context.
- **C1–C5 all applied.** **R1–R5 honored.**
- **Audit findings folded in & resolved:** HIER-1 (dashboard), HIER-2 (banner mid-token wrap), A11Y-1
  (one h1/screen), RESP-1 (**measurably closed: live CSSOM 0→9 width media queries**), NAV-1 (**search
  context — resolved, not deferred**), COMP dead-code (orphaned CSS + dead props removed). POL-2
  (empty-right-half) incidentally resolved by the memory right-rail.
- **Deferred (explicit):** real free-form assistant Q&A (separate approval-gated backend phase).
- **Accepted Minors (non-blocking):** AdvisoryChip "{n} advisory" count phrase (defensible sentence case).

### Human-only QA outstanding (R3 — honestly dispositioned, NOT fabricated)
Narrow-viewport **rendering** at 1280/1024/768/375 + 200% zoom; full authenticated mutation journey;
two-visible-window live-sync; exported-artifact stale; `absent_from_record`. The automation viewport is
pinned at 1440 and jsdom applies no CSS/viewport, so narrow **presentation** is code/CSSOM-verified only;
drawer **behavior** is fully unit-tested. A human should confirm the narrow layout + drawer presentation
on real widths before treating RESP-1 as visually signed-off on devices.

**Phase 33 = COMPLETE.** No new phase started; the next phase requires explicit user approval.

---

## 11. HUMAN-QA CORRECTION SLICE (2026-07-23 — code HEAD `4dc040d`)

Krish's initial human review of the shipped Phase 33 UI found real visual defects/regressions. The
human gate was **reopened**; the prior automated closure (§10, code HEAD `2f51d84`, docs `5a41704`)
remains the **historical automated boundary** and is unchanged. Phase 33 is **not finally
human-signed-off** until this correction is deployed and Krish visually verifies it.

**Orchestration:** Opus 4.8 fallback orchestrator (Fable 5 unavailable) planned/reviewed/verified;
implementation delegated to 3 Opus subagents (disjoint files) + 1 independent Opus reviewer. Test-first:
orchestrator authored the failing tests (red shown) before delegating.

### Findings & disposition (all VISUAL / layout / copy / state-init — truth path untouched)
| # | Finding | Resolution |
|---|---|---|
| 1 | Composer had no placeholder | `placeholder="Ask a question"` (sentence case); `aria-label` preserved & independent; empty submit now a true no-op; still inert (no fetch/append/persist) |
| 2 | Inconsistent assistant vertical spacing | One rhythm (16px section / 8px within) across every assistant surface, existing tokens |
| 3 | Lavender ended mid-column (looked unfinished) | Lavender moved from the `.assistant` card onto the rail container `.record-right`/`.memory-right` (full height); panel + `.memory-assistant-card` de-chromed; **neutral** `--border` edge (no-vertical-rail rule) |
| 4 | Content appeared cut off at the bottom | Root cause: only the card's 14px pad gave bottom room, so the caption sat flush at the scroll edge — NOT a true clip. Fix: rail is the single height-bounded scroll container with **24px** bottom padding; intentional `.assistant-log` nested scroll kept; no `overflow:hidden`. Live CSSOM: `captionWithinRail=true`, `paddingBottom=24px` |
| 5 | Groups started expanded | All groups **collapsed** on initial workbench load (`toggles[block] ?? false`); per-group independent toggle preserved (not an accordion); expansion survives assistant interaction (state lives in the workbench, not the panel); missing-field/workflow computation untouched |
| 6 | Casing / duplicate-state | Group headers lead with the human label (raw key demoted to mono, kept for provenance); record header strips `· New Draft` (reuses existing `stripLifecycleSuffix`) + drops the redundant `draft ·` filename token (identifier + single Draft badge kept); assistant memory head → Title-Case `Memory Available`/`Memory Unavailable` |
| 7 | Redundant availability state | New presentation-only `showAvailabilityHead` prop (default true) suppresses the redundant head where a `GraphStatusChip` already owns it (`/memory`, Evidence Explorer). `availability` still passed everywhere → `classifyAnswer` + unavailable caveat unchanged |

**Grounded pushback (reported, not silently done):** (a) #4 "cut off" was partly a mis-diagnosis — no
height hack, no removal of the intentional log scroll; (b) **DECLINED** the optional `sha256`→`SHA-256`
recasing — no safe presentation layer exists and it would transform backend question text, which the
finding itself forbids.

### Verification (code HEAD `4dc040d`)
- **635 web tests** (was 621; +14 new `p33-hqa-*`, 3 existing re-expressed not weakened), `tsc -b`,
  `npm run build`, snapshot `--check` (no drift) + **17/17** committed-snapshot gate, `no-vertical-rail`
  invariant — all green.
- **Independent Opus review: SHIP** — 0 Critical / 0 Important; 3 Minor (1 guard-comment fixed; dead
  `collapsedByDefault` + `.fg-block`/`.fg-sublabel` name-vs-content cosmetic left as non-blocking).
- **Exact-HEAD CI `4dc040d`: completed success.** Vercel serving the new frontend (CSS hash == local
  HEAD build). Railway `4dc040d`, `synthetic-only`, healthy.
- **Hosted desktop QA (live, 1440):** header deduped (1 Draft badge, no `· New Draft`/`draft ·`,
  identifier kept); 4 groups collapsed, expansion works; lavender rail full-height (`rgb(236,235,251)`,
  neutral edge), caption within rail; `Memory Available` head on workbench, single state on `/memory`
  (`assistantHeadPresent:false`); placeholder visible; console clean.

### State
**Automated and hosted desktop verification passed; awaiting final human visual sign-off.** The human
gate stays OPEN.

### Human-only verification still outstanding (R3 — NOT fabricated)
- Narrow-viewport **rendering** at 1280 / 1024 / 768 / 375 + **200% zoom** (automation pinned at 1440;
  jsdom applies no CSS) — especially the full-height lavender rail with no gray beneath short content and
  the narrow-screen drawer presentation.
- A glance at the demoted `.fg-sublabel` raw-key token (11px, `--text-quaternary` on white) for
  legibility (reviewer residual).
- Pre-existing human-only items still standing from §10 (mutation journey, two-window live-sync,
  exported-artifact stale, `absent_from_record`).

**Next human action:** Krish reviews the corrected UI on real narrow widths + 200% zoom; on approval,
Phase 33 is finally human-signed-off. No new phase begins without explicit approval.

