# Phase 36V.1 — Hosted-QA Fix-Forward

**Status:** IN PROGRESS
**Authorized:** 2026-07-27, after Krish's authenticated human inspection of the hosted `/krish`
deployment at commit `f563a660356d8026e8a30aad71dee06b879870ed`.
**Baseline:** org canonical `main` `f563a66` · clean · 0 ahead / 0 behind · hosted SHA matches HEAD
exactly · latest image tag `v0.0.24` · no open PRs · CI green.
**Release pacing:** ONE branch, ONE PR, ONE merge commit, ONE image. No partial-slice merges, no
separate docs-only closure merge (12 images have already shipped since the last full hosted QA).

**Scope:** frontend presentation · interaction · information architecture · navigation ·
accessibility · responsive behaviour · **one memory-plane data-layer extension** (deep graph
projection). Synthetic-only · deterministic · **no LLM** · **no new npm dependency** · no portal ·
no real data · **truth core untouched** · **no Phase 37**.

---

## 1. Baseline measured before any edit

| Axis | Value |
|---|---|
| Frontend tests | 1366 across 75 files |
| Backend tests | 1042 |
| Bundle JS | 534.13 kB (gzip 154.67) |
| Bundle CSS | 158.85 kB (gzip 22.93) |
| Snapshot drift | none (exit 0) |
| `tsc -b` | clean |
| Production build | clean, 1671 modules |

## 2. Root causes established before implementation

These were diagnosed from source, not inferred from the screenshots.

### 2.1 Assistant suggested-question clipping (Slice 1)

Not a fixed-height container. A four-link chain in `apps/web/src/components/assistant.css`:

1. `.record-right .assistant, .memory-right .assistant` — `max-height: calc(100vh - 110px)`, `flex: 0 0 auto`.
2. `.assistant-body` — `flex: 1 1 auto; min-height: 0`, but **no `overflow`** (defaults `visible`).
3. `.assistant-empty` — `flex: none`, refuses to shrink, no overflow → overflows the body box downward.
4. `.assistant-foot` — `position: sticky; bottom: 0; z-index: 1; background: var(--assist-tint)`, fully
   **opaque** → paints *on top of* the overflowed third suggestion.

The empty state also renders Agent Actions inside `.assistant-foot` (up to seven pills on
RecordWorkbench via `REVIEW_AGENT_PROMPTS`), enlarging the dock and worsening the squeeze.

`apps/web/src/__tests__/assistant-layout.test.tsx:492-500` **asserts** `.assistant-empty` is
`flex: none` — the suite actively locks in the defect. Replaced with a stronger contract assertion,
never deleted.

### 2.2 Root JSONPath `$` (Slice 3)

Origin is a single line in the **truth core**, `src/isaac_records/official.py:71`:

```python
path=".".join(str(p) for p in err.absolute_path) or "$",
```

For a root-level jsonschema violation (missing required top-level property, root type error,
root `additionalProperties`) `err.absolute_path` is an empty deque, so the join yields `""` and the
`or "$"` fallback substitutes the literal. **`official.py` is not edited.** Humanisation is display-only.

Two independent producers render it and are deliberately template-identical:
`apps/web/src/lib/assistantComposer.ts:88-105` (precomposed chips) and
`apps/api/isaac_api/assistant_query.py:552-566` (free-form). Both need the shared formatter.

### 2.3 "Open Validate" appears inert (Slice 4) — the brief's premise was wrong

`OPEN_VALIDATOR_ACTION` (`assistantComposer.ts:74-78`) already exists, is already labelled
**"Open Validator"**, already targets `/governance?tab=validator`, and already resolves the `/krish`
basename correctly through the router. It is not broken.

What was clicked is a different control. The backend emits a **provenance chip**
`{"label": "Open Validate", "navigate_to": base}` at `assistant_query.py:566` and `:576`, where
`base = ctx.navigate_base` is `/record/<id>` — **the record already on screen**. It navigates to the
current page, so nothing visibly happens.

Corroborated by the reported wording: `"…blocking export: $. Open Validate to run the deterministic
schema check."` is the *free-form* backend answer (`_ROUTE_TO_VALIDATE`, `assistant_query.py:472`),
and `AssistantQueryResponse` (`apps/web/src/lib/types.ts:242-256`) has **no `action` field** — so
free-form answers cannot render the Open Validator button at all. The frontend retired that prose;
the backend half never was. The fix is a backend response-contract fix.

### 2.4 Evidence top gutter (Slice 6)

`AppShell` + `chrome.css` is the one shared shell. `.screen-main` has no padding; only
`.screen-main.pad` supplies `22px var(--main-gutter)`. Of 14 shell mounts, **exactly one** passes
`mainPad="none"`: `EvidenceExplorer.tsx:217`, the *loaded* branch. The same file's loading/error
branch (`:56-59`) and no-evidence branch (`:130-140`) use `mainPad="pad"` and do get 22px — the page
disagrees with itself. `.wf-progress-banner-inset { margin: 0 24px }` is a prior one-off patch
supplying horizontal inset only. Fixed at the shared shell, per the brief.

### 2.5 Graph zoom reveals nothing (Slice 8)

Confirmed in code, not inferred. `apps/web/src/screens/graph/GraphCanvas.tsx` renders hand-written
inline SVG with a deterministic seeded Fruchterman–Reingold layout. `FILE_RADIUS = 9`,
`CONCEPT_RADIUS = 11`, edge stroke widths and the 11px label font are constant **in user units**, and
nothing reads `state.view.scale` except `unitsPerPx`, the arrow-pan step and the percentage readout.
Zoom is therefore pure magnification *by construction*. There is no level-of-detail layer to repair —
there is one to build.

The committed snapshot embeds **no symbol layer and no edge list**: the 220 nodes are 201 served files
+ 19 concepts, and the 508 edges are derived at request time from `file_detail[*].related.files[]`.
A genuine detail level therefore requires a snapshot schema change, not just a renderer change.

### 2.6 Settings navigation (Slice 12) — net-new, not a migration

Settings is a single flat route `/settings`. Both tab levels are plain `useState`: page tabs
(`SettingsPage.tsx:65-78`) and API sub-tabs (`:518-529`). Neither is deep-linkable; both reset on
refresh. The Endpoint Explorer is three levels deep with no URL, and **nothing in app code links to
it** — `LeftNav.tsx:14` is the only consumer of `ROUTES.settings`. There are therefore no existing
deep links to redirect. What does break is prose: `ApiDocs.tsx:143,150` and
`ConnectAnAgent.tsx:47,65` say "the Endpoint Explorer **above**", which becomes false once it moves.

### 2.7 API Access blank right half (Slice 11)

`AppShell width="wide"` publishes `--content-max: 1200px`; `.settings-panel` and `.settings-card`
adopt it, while every text block in `ApiKeys.tsx` is capped at 62–74ch with **no cap on its own box**
(`screens.css:2305-2416`). ~74ch ≈ 560–600px inside 1200px, so roughly half the card is empty. The
codebase already fixed this once elsewhere: `.settings-provenance-note { max-width: 80ch }`
(`screens.css:1712-1717`).

---

## 3. Graph data decision (Slice 8) — evidence and limits

### 3.1 What was rejected, and why

The existing `graphify-out/graph.html` was **not** revived. It is 2.5 MB, loads `vis-network` from a
**CDN** (violating the no-external-request boundary), is gitignored, and is excluded by both
`.gitignore` and `.dockerignore` from the image. These are the same grounds on which P36R/R1 rejected
it. "Graphify-style" is treated as a *behaviour* target, not an artifact target.

### 3.2 Safety scan of the full source graph — PASSED

`graphify-out/graph.json`: 2,988 nodes · 4,465 links · 257 communities.

| Check | Result |
|---|---|
| Absolute local paths (`/Users/`, `/home/`, `/root/`, drive letters) | **0 occurrences** |
| `source_file` values that are gitignored | **0 of 214 unique** |
| `examples/` exposure | only `examples/README.md`, explicitly un-ignored by `.gitignore`'s `!examples/README.md` |
| `records/` exposure | **none** — an initial substring hit was the false positive `src/isaac_`**`records/`** |
| Populated `author` / `contributor` | **none** |
| External URLs | one: the public upstream `https://github.com/ISAAC-DOE/isaac-ai-ready-record` |
| Runtime Graphify service required | **no** — committed artifact read from disk |

### 3.3 What is actually servable

Restricting the full graph to nodes whose `source_file` is in the snapshot's 201-entry
served-content manifest — the project's content-governance boundary — yields:

**2,612 nodes · 4,067 edges · 221 communities.**

- Node kinds: code 1,697 · document 691 · rationale 206 · concept 18.
- Real relations, direction preserved, none invented: `contains` 2,161 · `calls` 659 · `imports` 409 ·
  `imports_from` 282 · `references` 258 · `rationale_for` 204 · `method` 69 · `indirect_call` 8 ·
  `re_exports` 7 · `uses` 6 · `inherits` 3 · `shares_data_with` 1.

The 376 nodes outside the manifest are **not shipped**. The hierarchy is real, not synthesised:
`contains` edges give true file→symbol containment and `community` gives true clustering.

`Dockerfile:34` (`COPY apps/api/ apps/api/`) already ships `apps/api/isaac_api/data/`, so **no
Dockerfile, `.dockerignore` or infrastructure change is required.**

### 3.3b Disclosure delta relative to the existing snapshot

The safety scan in §3.2 establishes that nothing outside the served-content boundary ships. It does
not say what is **newly** shipped. Measured against the committed
`memory-snapshot.json` (a string-for-string comparison: a value counts as new when it does not appear
verbatim anywhere in the snapshot):

| New content class | Count | What it is |
|---|---|---|
| Node ids | 2,594 of 2,612 | Graphify symbol ids (`/`-free by construction; 0 contain `/`) |
| Node labels | 1,846 of 2,133 distinct | see the breakdown below |
| — `code` | 1,189 distinct | function / class / method **symbol names** |
| — `document` | 632 distinct | Markdown **section-heading text** |
| — `rationale` | 25 distinct | docstring/rationale **first lines** |
| — `concept` | 0 | every concept label is already in the snapshot |
| Community names | 78 of 221 | cluster names for communities the snapshot never surfaced |
| `source_location` anchors | 845 distinct (2,583 rows) | graph-internal line anchors (`L34`); no path shape |
| Edge list | 4,067 rows | the snapshot embeds **no** edge list at all |

All of it originates from git-tracked files inside the 201-path served set, all labels are ≤ 89
characters (the longest is exactly 89), and no node id, label, community name or line anchor contains
a machine path, an identity, or a credential-shaped string (independently re-scanned in
`test_no_absolute_local_path_anywhere_in_the_response`,
`test_no_secret_shaped_string_anywhere_in_the_response` and
`test_no_external_url_anywhere_in_the_response`). This is therefore **not** a governance violation —
but it is a real increase in the granularity of what the deployment publishes about the repository's
internal structure, from file-level to symbol-level, and it is recorded here rather than left
implicit.

### 3.4 The limitation that must be disclosed, and is

Both `graph.json` and the committed `memory-snapshot.json` carry
`built_at_commit = caab1d0a69c1733524bda5dde495623bc4b7bad1` (2026-07-18) — **213 commits behind
HEAD**. Everything built in Phases 25 through 36V, including the current Assistant, Settings and
Graph frontend, is absent from that graph.

The snapshot is in fact a **hybrid**: the builder recomputes `served_content_manifest` file hashes
from the *current* working tree (`freshness_basis: ci_content_manifest`, re-checked in CI by
`apps/api/tests/test_committed_snapshot.py`), while the graph *structure* remains pinned to
`caab1d0a`. Content freshness and structural freshness are different axes.

Today this is partly masked because only 220 file/concept nodes render. Showing 2,612 symbol-level
nodes will read as a current code map, and it is not. **Explicit structural-staleness provenance is
therefore added to the graph surface as part of this slice.** This is an addition beyond the
authorizing brief, recorded here rather than made silently — it is the same honesty-defect class the
P36R and P36V reviews caught repeatedly.

---

## 4. Internal slices and unit grouping

Fourteen brief slices are implemented as units grouped by **exclusive file ownership**, so no two
concurrent implementers can edit the same file. Each unit gets a fresh implementer and a separate
independent reviewer that implemented none of the work under review.

| Unit | Brief slices | Exclusive surface |
|---|---|---|
| A | 1, 2, 5 | `AssistantPanel.tsx`, `AssistantDrawer.tsx`, `assistant.css`, `assistant-drawer.css` |
| B | 3, 4 | `assistantComposer.ts`, `assistant_query.py`, `types.ts`, shared path formatter |
| C | 8a | `build_memory_snapshot.py`, `memory.py`, `memory_graph.py`, graph routes |
| D | 6, 7 | `EvidenceExplorer.tsx`, `EvidenceClassificationPanel.tsx`, `classification.css`, `AppShell.tsx`, `chrome.css` |
| E | 11, 12, 13 | `SettingsPage.tsx`, `screens/settings/*`, `routes.ts`, `App.tsx`, Settings CSS |
| F | 8b | `GraphCanvas.tsx`, `graphModel.ts` |
| G | 9, 10 | `GraphCommandBar.tsx`, `graphCommands.ts`, `GraphHelp.tsx`, `MemoryGraphCard.tsx` |
| H | 14 | cross-surface consistency + accessibility sweep |

Ordering constraints: B follows A (both touch `AssistantPanel.tsx`); F follows C (depends on the data
contract); G follows F (both touch `MemoryGraphCard.tsx`); H is last.

## 5. Snapshot regeneration discipline

Per `CLAUDE.md` §17, several units edit files listed in the served-content manifest (64 entries are
`apps/web/src/**`, including `__tests__`). Regenerating per-unit would capture other units' in-flight
hashes. **No implementer regenerates the snapshot.** The orchestrator regenerates exactly once, after
all units settle, then re-runs the drift check and the committed-snapshot gate test.

**Both committed artifacts must be in that one command.** Unit C added a second committed artifact,
`apps/api/isaac_api/data/memory-graph-detail.json`, written only when `--detail-out` is passed.
`--detail-out` is opt-in and nothing in the repo passed it, so the previously documented command was
unsafe in both modes: `--check` **without** `--detail-out` exits 0 with "ok: no drift" while a stale
deep artifact sits on disk, and regeneration without it rewrites the snapshot and leaves the deep
artifact stale. The script now prints a note to stderr in that case (exit code and default paths
unchanged, so existing callers are not broken), and `CLAUDE.md` §17 carries the corrected command
block. The orchestrator's release sequence is:

```bash
# 1. regenerate BOTH artifacts, once, after every unit has settled
.venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json \
  --detail-out apps/api/isaac_api/data/memory-graph-detail.json
# 2. re-check BOTH (exit 0 = no drift; 6 = drift, and BOTH drifts are now reported)
.venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json \
  --detail-out apps/api/isaac_api/data/memory-graph-detail.json --check
# 3. re-run both gate suites
.venv/bin/pytest apps/api/tests/test_committed_snapshot.py \
  apps/api/tests/test_memory_graph_detail.py -q
```

Note the deep artifact's structure is pinned to `graphify-out/graph.json` at `caab1d0a` (see §3.4), so
step 1 changes it only if the source graph or the served path set changes — an ordinary frontend edit
drifts the snapshot's content manifest but not the deep artifact.

## 6. Boundaries held

Preserved: deterministic truth core · validation authority · evidence authority · export eligibility
semantics · no guessing · no generated scientific values · explicit confirmation for writes ·
Assistant deterministic, non-LLM, advisory, read-only, ephemeral · Project Memory non-authoritative ·
graph relationships as navigation leads only · synthetic-only runtime.

Not touched: record-validation results · export rules · evidence classifications · record state
transitions · Assistant intent-resolution semantics · graph relationship semantics · schema data ·
API operational behaviour · authentication infrastructure · persistence.

Explicitly not done: no real SLAC data · no Postgres · no external model · no embeddings · no vector
database · no telemetry · no runtime Graphify service · no new credentials · no API-key backend ·
no `isaac-k8` change · no infrastructure change · **no Phase 37**.

---

*Sections 7 onward (per-unit results, reviews, verification battery, release, remaining human QA)
are completed as the phase proceeds.*
