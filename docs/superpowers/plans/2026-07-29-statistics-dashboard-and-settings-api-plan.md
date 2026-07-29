# Statistics Dashboard + Settings & API Navigation Refinement — Plan

**Date:** 2026-07-29
**Base:** `475611d` (image `v0.0.27`) on org `main` — clean tree, 0 ahead / 0 behind, no open PRs
**Branch:** `feat/statistics-dashboard` — one branch, one PR, one merge commit, one image
**Baselines at base:** backend **1375** passed · frontend **1865** passed / 89 files · `tsc -b` clean ·
JS 607.92 kB (gzip 176.91) · CSS 173.58 kB (gzip 24.83) · snapshot drift **none** on both committed artifacts

Nothing here begins Phase 37, adds a dependency, adds telemetry, touches the deterministic truth core,
or changes validation, export, or evidence-authority semantics.

---

## 1. Goal

Add one read-only `/statistics` destination that answers, at a glance, what the current synthetic
workspace contains and where its records stand — and rename the visible `Settings` destination to
`Settings & API` while preserving the `/settings` route.

Non-goals, stated so they cannot creep: no collaboration, no telemetry, no real data, no Postgres,
no identity or roles, no API-key generation, no portal integration, no new npm dependency, no
`isaac-k8` change, no Phase 37 dependency.

---

## 2. The recorded decision this supersedes, and why

`docs/superpowers/plans/2026-07-24-phase-36-closure.md:64-69` skipped **P36.7 Workspace Overview**:

> A synthetic-only overview would duplicate My Experiments … and Settings → Help/About …, or require
> **fabricated analytics (explicitly forbidden)**.

Matching in-code prohibitions: `ExperimentsHome.tsx:17-21` ("not a KPI dashboard"),
`ExperimentQueue.tsx:16-20` ("no aggregate health score, trend chart, or gauge"),
`design-handoff/03-screen-specs/s1-my-experiments.md:10`.

That skip is **superseded by explicit product direction**, and the two reasons behind it are
addressed rather than ignored:

- **Fabrication** — the page contains no analytics. Every figure traces to a field in a live response;
  absent values render as unavailable, never as `0`. Runtime usage analytics are stated as *not
  collected* rather than faked.
- **Redundancy** — partly conceded, and worth stating precisely rather than glossing.
  **Sections 2 (workflow-stage distribution) and 3 (cross-record evidence histogram + export-gate
  distribution) are genuinely new**: they are the aggregate view of `GET /api/runtime/records`, which
  exists nowhere in the UI today — that endpoint is consumed only by the Assistant's triage intents and
  has never been rendered. **Sections 1, 4 and 5 are deliberate compact restatements** with links out,
  not new information: the four record cards overlap My Experiments' group counts and `queueSubcount`
  (`adapt.ts:118-122`); Project Memory's figures repeat seven of the eight already shown by
  `MemoryFigures` (`ProjectMemory.tsx:469-492`), adding only `Deployed App Commit`; and
  `Documented Operations` / `Groups` restate the Endpoint Explorer's own counts (`ApiDocs.tsx:360,384`).
  They are included so the page answers "what is in this workspace" in one place, and each links to the
  surface that owns the detail. An earlier draft of this document claimed these sections "link out
  instead of restating them" — that was **false**, and the independent review caught it.

Surviving constraints are honored: **no health score, no trend chart, no gauge.**

---

## 3. Data contract — reuse, no new endpoint

**Decision: add NO backend endpoint and NO backend code.** Four already-shipped, already-tested
endpoints supply everything:

| Source | Client method (exists) | Supplies |
|---|---|---|
| `GET /api/runtime/records` | `api.getRuntimeRecords()` `api.ts:615` | records total, status distribution, `workflow.current_step`, 5-class evidence histogram, `artifact_state` |
| `GET /api/graph/status` | `api.getGraphStatus()` `api.ts:545` | Project Memory counts + provenance commits |
| `GET /api/about` | `api.getAbout()` `api.ts:297` | runtime mode, persistence, schema version, build commit |
| `GET /api/openapi` | `api.getOpenApi()` `api.ts:305` | API surface, via the existing `apiDocsModel.ts` |

Reasons a consolidated `GET /api/statistics` was rejected:

1. **No missing datum.** `test_runtime_records.py:123` already proves the denominator invariant
   (no filters → every record, `total == 5`), and `limit` defaults to `None`
   (`routes.py:2584-2590`) so an unparameterised call cannot undercount.
2. **It would create a forbidden second catalog.** `apiDocsModel.ts:1-9`: *"Everything the API
   surface states about this API is computed HERE … There is deliberately no second,
   hand-maintained endpoint catalog anywhere in the client."*
3. **It would defeat the required partial-failure behaviour.** Four independent sources map 1:1 onto
   per-section localized errors; a single endpoint either returns or does not.
4. **It would falsify shipped assertions.** A new operation breaks
   `test_about_and_openapi.py:312` (`checked == 35`) and staledates the "35 operations" statements at
   `ApiDocs.tsx:487,492,562`.

All derivation is a pure frontend module, `apps/web/src/lib/statisticsModel.ts`, unit-tested
exhaustively. The full frozen contract is reproduced in §4 of the closure document.

### Two truthfulness decisions that depart from the request's illustrative shape

- **No `validation: {passed, failed, not_run}` triple.** There is no stored verdict and **no
  "not run" state** anywhere in the backend — status is derived on read via an in-memory
  `export_draft` dry-run and nothing is persisted (`workspace.py:15-16`). A `not_run` bucket would
  fabricate a state. The page instead reports the **export gate**, derived from the four mutually
  exclusive `status` values (`workspace.py:72-76`, `400-417`): `ready_to_export` means the official
  export dry-run passes; `in_review` means zero open questions **and** the dry-run does not pass.
- **Four evidence classes → five.** The real enum is
  `supported, inferred_candidate, insufficient_evidence, conflicting_evidence, unknown`
  (`runtime_records.py:30-38`), displayed in severity precedence, not sorted by count.

### Counting hazards explicitly guarded

- Distribution uses `workflow.current_step` only. The `blocked`/`reopened` booleans are
  OR-reductions (`runtime_records.py:107-111`) and are **not** mutually exclusive
  (`workflow.py:93-97`) — counting them would double-count.
- `graph/status` returns **both** `served_file_count` (200, the content manifest) and `file_count`
  (201, the served path set) in one body (`routes.py:1984` vs `routes.py:2000`). They are
  deliberately different sets (`CLAUDE.md` §17). The page shows one, labelled with its scope.

---

## 4. Navigation

Sidebar order becomes: `My Experiments` · `Project Memory` · `Governance & Safety` ·
**`Statistics`** · **`Settings & API`**.

The rename is a **one-line change**: `labels.ts:112 navSettings` is the single authored string, and
both `LeftNav.tsx:14` (nav label) and `SettingsPage.tsx:132` (page `<h1>`) consume it. Route
`/settings` and the `?tab=` deep links are unchanged. No component or route identifier is renamed —
cosmetic internal churn is explicitly avoided.

No test asserts the literal `'Settings'` as a nav label or `h1`. The one Settings-word assertion is
the tablist accessible name at `settings-page.test.tsx:173`, updated deliberately alongside the
destination name.

---

## 5. Workstreams (exclusive file ownership)

| WS | Owns | Reviewer |
|---|---|---|
| **A** data layer | `lib/statisticsModel.ts`, `lib/workflowSteps.ts`, its tests, minimal page shell | independent Opus |
| **B** nav + rename | `routes.ts`, `App.tsx`, `LeftNav.tsx`, `icons.tsx`, `labels.ts`, `WorkflowSpine.tsx` (dedup), `SettingsPage.tsx`, nav/settings/heading tests | independent Opus |
| **C** dashboard UI | `screens/statistics/**`, `test/apiFixtures.ts` (additive), statistics tests | independent Opus |
| **D** review | nothing | Opus, implemented none of it |

Orchestrator exclusively owns git, snapshot regeneration, the PR, the merge, and release monitoring.
`A` runs first (it publishes the contract and the shell); `B` and `C` then run concurrently over
disjoint files; `D` reviews after integration.

---

## 6. Verification gates

Backend suite · frontend suite · `tsc -b` · production build · Docker build + smoke ·
`/krish` base-path tests · CSS-source gate tests (`no-vertical-rail`, `interaction-states`,
`native-control-accent`, `layout-width-modes`) · privacy scan of derivations and rendered DOM ·
`.only`/skip audit · snapshot drift check with `--detail-out` and a single regeneration after all
workstreams settle · bundle-size comparison · session-local browser screenshots.

**Automated visual-regression coverage does not exist in this repository** and none is added
(Playwright remains deferred for the reasons in the P36V.1 closure). Layout claims are DOM
assertions, CSS-cascade readings, or session-local browser observations — never a claim of Krish's
human sign-off.

---

## 7. Known limitation recorded up front

The **empty-workspace state is not reachable through the shipped product.** `list_experiments()`
calls `ensure_seeded()` (`workspace.py:687-697`) and there is no per-experiment delete operation, so
the record count is always ≥ 5. The empty branch is implemented defensively and covered by a
fixture-level test; it is **not** claimed to be reachable in the running app.
