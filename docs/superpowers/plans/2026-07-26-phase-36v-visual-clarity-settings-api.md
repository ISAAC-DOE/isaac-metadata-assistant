# Phase 36V — Visual Clarity, Settings & API Experience Refinement

**Authorized:** 2026-07-26. **Branch point:** org canonical `main` `f56f1ce`.
**Scope:** frontend presentation · information architecture · responsive layout ·
accessibility · navigation · **OpenAPI documentation-metadata enrichment**.
**Not this phase:** Phase 37, real data, Postgres, portal integration, identity/roles,
external model provider, `isaac-k8`, new dependencies, CDN runtime.

---

## 1. Verified starting state

| Axis | Value |
|---|---|
| Canonical repo | `ISAAC-DOE/isaac-metadata-assistant` (`origin`) |
| HEAD | `f56f1ce` (P36R closure merge #18) |
| Tree | clean · 0 ahead / 0 behind · no open PRs · no stray branches |
| Backend tests | **1029 passed** |
| Frontend tests | **1120 passed / 69 files** |
| Production build | clean — JS 500.98 kB, CSS 145.47 kB (**baseline at `f56f1ce`**, not a post-change figure) |
| Snapshot | `--check` no drift · 201 served entries |
| Hosted `/krish` | not readable from this environment (identity edge) |

Baseline QA was performed against a **true production build served at `/krish`**
(`VITE_BASE_PATH=/krish/ VITE_API_BASE=/krish/api` + `ISAAC_STATIC_DIR`), not the dev
server — so base-path behaviour is covered by the same evidence.

## 2. Baseline defects reproduced (production build, `/krish`)

Assistant, confirmed visually:

1. Clear control reads `Clear`, not `Clear Conversation`.
2. `Memory Available` sits at the far right of the header and renders on only **2 of 5**
   mounts.
3. The assistant answer has **no bubble, no icon and no `Assistant` label** — the live
   answer is a bare `<p>` — while the user message correctly gets a bordered bubble.
4. Provenance renders lowercase monospace `answered from: …`.
5. A collapsed `Suggested Questions & Agent Actions` accordion sits **between** the
   transcript and the composer.
6. `Clear` does not reset a staged, unconfirmed `proposal` (found by audit, not in the
   authorizing spec).
7. There is **no Open Validator control at all** — only reply prose. `/governance` is
   absent from the Assistant nav allowlist and the Validator tab is not deep-linkable.

Concepts / Graph / Settings / API, confirmed by audit:

8. Concept primary labels carry implementation identifiers, e.g.
   `AI scientific consistency review (review.py NoOpReviewer)`. No Technical Details
   disclosure exists anywhere in the app.
9. Graph exposes ~13 interactive controls plus 7 prose blocks before the canvas; no
   filter drawer, no active-filter chips; `Clear filters` is stranded inside the path
   form; `imports_from` and `shares_data_with` render raw.
10. Settings duplicates **6 distinct claims** across Overview / Data & Privacy / About —
    two of them character-for-character via shared helpers — plus a repeated 6-row
    figure table. The truth-vs-memory boundary appears in all three tabs.
11. The API tab renders a **raw internal Python docstring** as an endpoint's user-facing
    purpose. Of 34 operations: zero tags, 26 with no description at all (only FastAPI's
    auto-generated function-name summary), responses limited to `200`/`422`.

## 3. Already shipped by P36R — not re-implemented

The API tab is **already** master-detail with search, 13 derived groups, method badges,
roving tabindex and one-level `$ref` resolution. Concepts is **already** master-detail.
Graph help is **already** sectioned and focus-trapped. Assistant overflow handling is
already thorough (the old 340px clip is gone and guarded). This phase refines these; it
does not rebuild them.

## 4. Plan — three cohesive PRs

**PR 1 — Assistant and shared interaction polish.**
Shared header with a status row beneath the title; `Clear Conversation`; full ephemeral
reset including the staged proposal; a labelled left-aligned Assistant bubble for both
live and archived answers; `Source:` provenance; `Related Questions`; composer directly
beneath the transcript; empty-state divider; italic secondary footer; status on every
mount that can truthfully report it. Plus **Open Validator**: a real control, `/governance`
added to the nav allowlist, a deep-linkable Validator tab, preserved history and base
path, and focus moved to the destination.

**PR 2 — Concepts and Graph refinement.**
Humanized concept titles with a Technical Details disclosure preserving every raw value;
Concepts hierarchy and concision. Graph primary toolbar; filters moved into a panel with
removable active-filter chips and `Clear All Filters`; a focused `Find a Path` tool;
humanized display labels; legend readability; help redesigned into the ten named
sections; a single boundary statement. No graph-data or filter-semantics change.

**PR 3 — Settings, API Keys, API Documentation, OpenAPI metadata.**
Backend OpenAPI documentation-metadata enrichment for all 34 operations with guard tests;
a shared typed Settings content source; Overview reduced to summaries; Data & Privacy as
the canonical detailed home; About focused with Technical Details disclosures; API
sub-navigation; an honest API-key unavailable state; API Status, Quick Start, code tabs
and `Connect an Agent`.

## 4a. PR 1 outcome

Frontend **1120 → 1165 passed** (69 → 71 files). Backend 1029 unchanged. `tsc -b` clean;
production build clean (JS 503.05 kB, CSS 146.31 kB); snapshot regenerated, `--check` no
drift, diff is sha entries + `served_manifest_fingerprint` only; no `.only`, no `.skip`.

Verified against a production build served at `/krish`, not the dev server: Open Validator
navigates to `/krish/governance?tab=validator` with the Validator tab genuinely selected,
base path preserved, **no full page reload**, focus on `#rec-val-heading`, and browser Back
returning exactly to the origin URL. Clear Conversation empties the transcript, the `Source:`
line and the proposed-action regions, unmounts with zero reserved space, restores the empty
state and focuses the composer. Zero horizontal-overflow offenders at 1054 px.

Independent review returned **DO NOT SHIP** on two Important findings, both accepted and
fixed (**N5**, **N6**), plus five minors. Its five mutation probes and the fix slice's five
all caught real regressions. One orchestrator error is recorded honestly: a first attempt to
verify **N6** in the browser used a leaf-only DOM filter that silently excluded
`.assistant-memory` (it wraps a status dot), producing a misleading count; re-verified with
an outermost-statement query before the result was accepted.

## 4b. PR 2 outcome

Frontend **1165 → 1242 passed** (71 → 73 files). Backend 1029 unchanged. `tsc -b` clean;
production build clean; snapshot regenerated, `--check` no drift, non-sha diff is
`served_manifest_fingerprint` only.

The graph surface went from **~13 interactive controls plus 7 prose blocks above the
canvas** to four controls and two lines, carrying exactly the prescribed single boundary
sentence. Verified in a production build at `/krish`: the Filters panel opens with every
former control reachable; the trigger reports an active count; chips are removable; `Clear
All Filters` restores 220 of 220 nodes; the help dialog renders exactly the ten prescribed
sections in order with `aria-modal="true"`, Technical Details collapsed, focus moved inside,
and Escape restoring focus to its trigger.

Independent review returned **DO NOT SHIP** on one Critical and three Important findings.
The Critical (**C1**) is the phase's most instructive defect: the active-filter chips
enumerated the relations still **shown** rather than those **hidden**, so on the real
five-relation payload unticking one relation produced a trigger reading "Filters 1 active"
beside **four** chips whose accessible names — "Remove the Imports relationship filter" —
named relations being kept, and whose activation *narrowed* the graph while every sibling
control widened it. Both test fixtures carry only one or two relation types, so the wording
reads correctly there and all 1242 tests passed. The orchestrator's own browser QA had
exercised the cluster filter but not the relation filter, and missed it as well. Confirmed
in the browser on the real payload before being fixed.

The first review attempt stalled mid-mutation-probe. Tree integrity was re-established
before continuing — snapshot `--check` (which fails if any manifest-listed source is
altered), both suites, and `tsc -b` all confirmed the branch state was intact.

## 5. Reconciliations (recorded, never silent)

- **N1 — the edge provider is not named in client copy.** The authorizing spec asks
  `Connect an Agent` to state that "Authentik browser access is not automatically
  equivalent to headless external-agent authentication." The string `authentik` is
  forbidden in Settings by `apps/web/src/__tests__/settings-page.test.tsx`, whose comment
  records that the list mirrors what `apps/api/tests/test_about_and_openapi.py` withholds
  from `GET /api/about` — naming the edge provider in client copy discloses infrastructure
  topology. The same substance is expressed provider-neutrally: browser access through the
  deployment's identity layer is not equivalent to headless access for an external agent.
  The guard is left intact.
- **N2 — Base URL is rendered relative, and DERIVED rather than hardcoded.** `127.0.0.1`
  and `localhost` are forbidden literals in Settings by the same guard, and an absolute
  origin would be wrong under a deployed base path in any case. This plan originally
  specified the literal relative string `/api`; **that would have been wrong on the actual
  hosted target.** `app.py` mounts the router at `base_path()`, so under `/krish` the
  document's own paths — and therefore their shared base — are `/krish/api`. The base is
  now derived from the longest common `/api`-terminated prefix of the served document's
  paths, with tests pinning both the local case (`/api`) and a deployed case
  (`/base/api`); when the paths share no single base the screen says so rather than
  printing a wrong value. Code examples use an unexpanded `$ISAAC_BASE_URL` placeholder,
  never a host literal.
- **N3 — no accent edge on the Assistant bubble.** The spec calls a purple accent edge
  "optional". `apps/web/src/__tests__/no-vertical-rail.test.ts` enforces the permanent,
  system-wide no-vertical-rail rule (`no-vertical-rail-rule.md`). The edge is omitted; the
  bubble is distinguished by border and surface instead.
- **N4 — Open Validator is additive, not a repair.** The spec describes it as an existing
  action that "appears nonfunctional". No such control exists; only reply prose. Delivered
  as a new control plus the route state it requires.
- **N5 — the prescribed advisory-footer copy was weaker than what it replaced, and was
  corrected.** The spec prescribes: *"The Assistant is advisory. It explains artifacts and
  points to sources; deterministic validation remains authoritative."* The copy already
  shipping contained an explicit negative capability claim — **"It never validates"** —
  which the prescribed sentence drops in favour of a weaker relative statement about where
  authority sits. Independent review caught that this weakening landed in the *same slice*
  that adds an `Open Validator` button and a `Deterministic Schema Check` card to the panel,
  i.e. exactly when the claim matters most. Shipped copy restores the clause while keeping
  the prescribed treatment and rhythm: *"The Assistant is advisory: it explains artifacts
  and points to sources. It never validates — deterministic validation remains
  authoritative."* A positive `/never validates/i` assertion now guards it. Same precedent
  as P36R **R9**, where the authorizing prompt's own prescribed copy was false.
- **N6 — the availability status is NOT restated on surfaces the page already owns.** The
  spec requires the status on "every Assistant mount". Enabling it unconditionally
  reversed a Phase-33 human-QA fix (HQA #7) and produced two consequences that outweigh
  spec-literal consistency: the same axis acquired **two differently-worded accessible
  names** (`GraphStatusChip`'s "Project memory available — memory plane, advisory only,
  never a validator" vs. the row's "Memory Available"), and deleting the opt-out destroyed
  a real capability — `availability` also drives `classifyAnswer`'s degraded-vs-advisory
  decision, so a mount could no longer both *use* the value and let the page own the
  *label*. The visible row renders on Record Workbench and Export Readiness, where the
  panel is the sole owner; it is suppressed on Project Memory and Evidence Explorer, whose
  pages already state it. Guided Completion renders nothing because it genuinely cannot
  know. This satisfies the phase's own "free of repeated definitions" goal and the
  accessibility requirements, which the literal reading contradicted.

- **N7 — relation types are humanized; cluster names are not.** The spec lists
  `cell_type → Cell Type` among its humanization requirements. Measured against the real
  snapshot: relation types are a **closed set of five** (`references` 389, `imports` 382,
  `calls` 160, `imports_from` 69, `shares_data_with` 2) and are safe to map explicitly.
  Cluster/community names are **open-ended arbitrary data** — 100+ distinct values including
  `SHE_work_function_eV`, `test_export.py`, `record_id`, `slab_model` and `cell_type` itself,
  which is a `community_name`, not a field type. The same snake_case rule applied to that
  namespace yields **"She Work Function Ev"** (destroying a standard-hydrogen-electrode
  acronym and an electronvolt unit) and **"Test Export.py"**. Fabricating a scientific label
  is precisely what the no-guessing rule forbids, so relation types are mapped through an
  exhaustive verifiable table with **verbatim fallthrough for anything unknown**, and cluster
  names render exactly as the data holds them, with the raw cluster id on `title`.
  Readability was improved structurally instead: real node shapes, counts separated from
  titles, and Technical Details disclosures. Independent review re-measured and endorsed the
  boundary against the spec. Humanizing cluster names would require a curated per-value map
  approved by a human — not a rule.
- **N8 — the legend's secondary raw token line was removed.** It printed the five raw
  relation values a second time, in a second casing, directly beneath a group already listing
  them — the duplication this phase exists to remove — as an unlabelled bare `<p>` of
  context-free monospace on the primary surface. The raw token remains available at the three
  places closer to the action: the filter checkbox's own `title`, `GraphDetail`'s `title`, and
  the help's Relationship Types section, which pairs each label with its raw value and states
  which of the two the filter and the `relation` command match. Per-entry `title` attributes
  replace the line, matching how cluster entries already expose their raw id.

## 6. Boundaries held

Truth core, official schema authority, evidence audit, export eligibility, no-guessing,
assistant determinism / read-only / non-LLM / ephemeral transcript, Project Memory
separation, graph nodes + edges + filter semantics, synthetic-only runtime, persistence
architecture and authentication infrastructure are all unchanged. OpenAPI enrichment is
documentation metadata only: no route, parser, payload, schema, status-code, validation or
auth behaviour change.
