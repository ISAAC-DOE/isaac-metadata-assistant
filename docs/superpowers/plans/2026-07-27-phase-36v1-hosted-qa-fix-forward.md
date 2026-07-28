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

## 7. Per-unit results, reviews and verdicts

Every unit received a **separate independent reviewer that implemented none of the work under
review**. Every reviewer returned findings in Critical / Important / Minor tiers with a `SHIP` /
`DO NOT SHIP` verdict. **Four of four reviews returned `DO NOT SHIP` on the first pass.** All
Critical and Important findings were fixed by a further fresh agent before the PR opened.

### Unit A — Assistant layout, header, active-conversation polish (slices 1, 2, 5)

Root cause was **not** a fixed-height container but a four-link chain (§2.1): `.assistant-body` had
`flex: 1 1 auto; min-height: 0` but **no `overflow`** (default `visible`); `.assistant-empty` was
`flex: none` and refused to shrink; and `.assistant-foot` is `position: sticky` on an **opaque**
`var(--assist-tint)`, so it painted *over* the overflowed third suggestion with nothing scrollable.
`assistant-layout.test.tsx` had **asserted** `flex: none` — the suite locked in the defect. Fixed by
making the body a real scrollport and letting the empty state shrink; the locking assertion was
replaced with a stronger contract assertion, never deleted.

Header rebuilt as one balanced row (icon + `Assistant` left, status dot + `Memory Available` right at
matching 9px gap) with `Clear Conversation` on a subordinate action row that `:empty`-collapses when
there is no conversation. One intentional `max-width: 720px` fallback.

*Orchestrator note carried into review:* both `.assistant-body` and `.assistant-empty` declare
`overflow-y: auto` (nested scrollports in one axis).

### Unit B — root-path humanization + Open Validator (slices 3, 4) — reviewed, then fixed

**The brief's premise for slice 4 was wrong, and the unit said so with evidence.**
`OPEN_VALIDATOR_ACTION` was *already* labelled `Open Validator`, *already* targeted
`/governance?tab=validator`, and *already* resolved the `/krish` basename. Nothing needed renaming.
The actually-inert control was the **backend** chip `{"label": "Open Validate", "navigate_to": base}`
where `base = /record/<id>` — the record already on screen. Corroborated by `AssistantQueryResponse`
having no `action` field, so a free-form answer structurally could not render the working button.

`src/isaac_records/official.py:71` (`".".join(...) or "$"`) was **not** edited — humanisation is
display-only. Two implementations (`assistantPaths.ts`, `assistant_paths.py`) with equivalence locked
by one shared 17-case table replayed by both suites; the report states honestly that there is **no
single shared formatter** because the producers are in different languages.

Reviewer: 0 Critical, 3 Important. Fixes:
- **The validator-crash sentinel was being reported as a finding.** `routes.py` emits
  `{"path": "$", "message": "Validation could not be completed."}` when validation **fails to run**,
  and `_compose` read only `path`. A crash therefore rendered as *"1 record-level validation issue
  may be blocking export."* — false, and *more* credible than the old raw `$`, which at least looked
  like a machine artefact. Now detected on `message` (a genuine root violation always carries a
  jsonschema message, so the honesty-critical direction cannot false-negative) and answered as
  `insufficient_context` with no count and no location. A test reads `routes.py` and asserts the
  literal is still present in **both** producers, so the constant cannot drift from its source.
- **The module's own documented invariant was false**: `$$`, `a.$.b`, `assets.$` emitted a bare `$`
  as a primary label. Now any `$` inside any segment classifies as `unknown`. Enforced not by three
  new cases but by a **generated 1,752-locator corpus** in both languages — which caught `$$$`, a
  case no table entry covered. Verified against the schema that none of its 219 property names
  contains `$` or `.`, so nothing reachable was downgraded.
- **Two more instances of the reported defect were shipping.** `Complete Metadata` and
  `Evidence & Sources` also pointed at the record root. The orchestrator **overrode the reviewer's
  "defer, but record it"** and took the fix: they now open `/record/<id>/complete` and
  `/record/<id>/evidence`, DOM-verified to render. Shipping known instances of the exact defect being
  fixed, from the exact mount where it was reported, inside an image whose notes claim the class was
  closed, would have put the same bug back into the next QA pass. `WORKFLOW_STEP` and
  `RECORD_SUMMARY` were deliberately left at the record root (no `/workflow` route exists;
  `RecordWorkbench` *is* the workflow surface, and the record root *is* the record surface) — pinned
  by tests with the rationale.
- `_safe_technical_paths` no longer silently drops an unsafe locator; it substitutes
  `(withheld: unsafe to display)` so the stated count and the disclosure always agree — the project
  bans silent caps.
- **Deliberate in-scope addition, recorded not hidden:** a 2-line-per-language invisible-character
  strip (`﻿\x1c\x1d\x1e\x1f\x85`). Without it the two implementations genuinely disagreed on those
  inputs, and Python rendered an all-invisible locator as a **blank location label a reader sees**.

Security-relevant change attacked and cleared by the reviewer: `_CLIENT_ROUTE_PREFIXES` gained
`/governance`. `startswith` would accept `/governance-evil`, but no data-controlled value reaches it
— the action target is a frozen constant and every source `navigate_to` is server-constructed. The
client also refuses to trust the wire: `resolveAssistantAction` maps `kind` through a closed frozen
catalog and returns the frontend's own descriptor, dropping unknown kinds.

### Unit C — deep symbol-level graph layer + route (slice 8a) — reviewed, then fixed

The layer had been built but was **unreachable and untested**: `build_graph_detail` had zero callers
(no route) and zero tests. `GET /api/memory/graph/detail` was wired mirroring `get_memory_graph`
(HTTP 200 always, honest `available: false`), the base projection proven byte-identical before and
after, and 64 tests added.

Reviewer: **0 Critical — data governance clean.** It wrote an independent 30-pattern scanner over all
20,213 strings in the artifact, drove 22 hostile artifact states through a live client, and confirmed
no leak. It also measured the real cost: 3.0 ms cold load, 1.6 µs cached, 2.12 MB retained, 2.6 ms
per request — cheaper per request than the base projection — and confirmed the endpoint is genuinely
lazy (the source is still `None` after app creation and after hitting the base projection).

4 Important. Fixes:
- **`meta.counts` echoed the artifact's own claimed counts unverified** on the non-truncated branch.
  An artifact claiming 999,999,999 nodes was served as `available: true, integrity: "verified"`
  alongside 2,612 actual nodes. Both branches now recompute from what was rendered.
- **The real artifact never passed the generator's own validator or leak scanner in CI**, and the
  test docstring falsely claimed *"a hand-edited or stale artifact cannot pass"*. 10 of 13 tamper
  mutations survived — including reversing an edge's direction and injecting
  `~/private/notes.xlsx`, `\\fileserver\slac\x`, `/Volumes/BEAMTIME/raw.h5` and an email address into
  labels. The three missing gates were added. **Tamper detection: 12 undetected → 6.** The remaining
  6 are semantically plausible single-row edits that **no CI-runnable gate can distinguish** while
  `graphify-out/` is gitignored and absent from CI; they are pinned as explicit `False` rows in a
  16-row table so the file cannot imply a guarantee it does not provide.
- **The documented regeneration command covered neither artifact** (§5). This would have bitten the
  orchestrator's own release step.
- **The new safety scan reproduced the generator's blind spots.** Patterns widened in both the
  generator and the test — and tuned **empirically against all 201 served files**, because naive
  spellings false-positived on this repo's own vocabulary (`settings.local.json`, `.env.local`,
  `src/optional/`, loopback literals). Cross-checking the two independent spellings **caught a real
  gap: the generator never rejected `file://`** though the response scan always did. Two disclosed,
  narrow, test-pinned exemptions: loopback/`0.0.0.0`, and `isaac.slac.stanford.edu` (already
  published in served `docs/deployment.md`).
- `detail_schema_version: true` was accepted as version 1 at every layer (`True != 1` is `False` in
  Python). Fixed in both runtime and generator.

**Disclosure delta, quantified here because the plan previously quantified it nowhere.** Relative to
the committed snapshot the deep artifact newly discloses: 2,594 of 2,612 node ids; **1,846 of 2,133
distinct node labels** (code 1,189 · document 632 · rationale 25 · concept 0); 78 of 221 community
names; 845 distinct `source_location` anchors (the snapshot has none); and the 4,067-row edge list,
which the snapshot does not embed at all. All labels ≤ 89 chars, all from git-tracked files inside
the 201-path served set. **Not a governance violation — a real granularity increase from file level
to symbol level**, and it is what makes the structural-staleness disclosure necessary rather than
decorative.

### Unit D — Evidence top gutter and hierarchy (slices 6, 7)

Fixed **at the shared shell**, as the brief demanded, not as a per-banner margin. A new
`--main-top-gutter` token in `chrome.css` is consumed **exactly once** per preset (`.pad`, the
unpadded `:not(.pad):not(.centered)`, and `.centered-col`); the one-off
`.wf-progress-banner-inset` was replaced by a shared `.main-inset`. `.evclass` was reconciled to zero
top padding so no state produces a double gutter.

*Orchestrator verification:* `mainPad` **defaults to `'none'`** in `AppShell.tsx:60`, so the new
unpadded rule would hit any mount that merely omits the prop. All 14 `AppShell` mounts were
enumerated — every one passes `mainPad` explicitly, and exactly one passes `"none"`
(`EvidenceExplorer.tsx:223`). No regression.

### Unit E — Settings space, navigation, concision (slices 11, 12, 13) — reviewed, then fixed

Found half-done: 3 TypeScript errors (it did not compile) and 92 failing tests. **And the actual
slice-11 fix was missing entirely** — the previous session had written the two-column JSX skeleton but
**no CSS at all**, so `.api-access-grid` and friends were unstyled and the "two-column layout" was
three stacked unstyled `div`s.

Reviewer: 2 Critical, 4 Important. Fixes:
- **The `Full Description` disclosure hid 47% of the contract text.** It fired on **31 of 35**
  operations, hiding **8,568 of 18,314** characters — including exactly the boundary copy this
  project requires visible: the Assistant's *"There is no language model…"*, the graph's
  structural-staleness disclosure, and *"Project Memory provides leads … never a correctness
  ruling."* This inverted the rule Unit E's own sibling suite enshrines
  (`settings-page.test.tsx:612-635`). **A length threshold alone would not have fixed it**: at 400
  chars the three remainders that still exceed it are precisely `assistant/query`, `csv/preview` and
  `memory/graph/detail` — all three carrying their boundary claim in the remainder. The shipped rule
  is length **and** a boundary-caveat check. Result: **0 of 35 operations collapse, 0 characters
  hidden.** `apiFixtures.ts` gained all 35 real descriptions verbatim, because it previously
  contained **zero** multi-paragraph descriptions and no test could have caught this.
- **The `Auth` flag overstated what the app can know.** `Credential required` dropped the conditional
  *"when this deployment enables authentication"*, contradicting the same page's admission that it
  *cannot report whether access is restricted* — and the overstatement was regression-guarded by four
  pinned assertions. Relabelled to the contract fact it genuinely knows: **`401 documented` /
  `No 401 documented`**, plus the legend given an `id` referenced by `aria-describedby`.
- Residual dead zone: `.api-keys-row > dd` was still capped at `74ch` (~20–25% of the widest column
  blank) and `.api-keys-empty-body` put ~420px of centred text inside a ~1,160px dashed box. Caps
  raised to `92ch` / `100ch` and the auto-centring island removed.
- CSS-source-string assertions converted to `getComputedStyle` on rendered elements. **This corrected
  the reviewer's own premise:** jsdom resolves the cascade by *source order and ignores specificity*,
  so a computed check on `.api-access-banner .api-keys-lead` would have read `74ch` where a browser
  computes `none`. The stylesheet was reordered so jsdom and browsers agree, which is what makes the
  assertion meaningful.
- The `cssRule()` helper was rebuilt to strip at-rule bodies (it could previously read a
  `@media` override as the base rule) and to be robust to formatting.
- **Record corrected:** Unit E's report claimed it merged the banner's authentication summary with
  the access model because it "judged these identical". They are two different claims. What actually
  happened is that a banner-level authentication summary was **consciously dropped** so each claim is
  stated once — right call under slice 13, wrong stated rationale.

### Unit F — graph semantic zoom (slice 8b) — reviewed; fixes in progress at the time of writing

**Unit F contradicted the authorizing brief's proposed hierarchy, and the reviewer independently
confirmed every number.** The brief proposed community → file → symbol. Measurement of this exact
artifact:

| Claim | Independently verified |
|---|---|
| `contains` edges within-file / cross-file | 2,161 / **0** |
| nodes missing `source_file` | 0 of 2,612 |
| nodes missing `community_id` | 0 of 2,612 |
| communities lying entirely inside ONE file | **188** of 221 |
| files spanning >1 community (max) | **75** (max **58**, `schema/isaac_record_v1.json`) |

A community is therefore a grouping **inside** a file, not a container of files: the brief's ordering
would have required **inventing containment the data denies**. Shipped levels are `file` (the
existing 220-node projection, not re-derived) → `cluster` ((file, community) groups, 363 real) →
`symbol` (payload rows), driven by `state.view.scale`.

The original defect was confirmed as structural, not a bug: `FILE_RADIUS`/`CONCEPT_RADIUS`, edge
widths and the 11px label font were constant **in user units**, and label visibility was gated by
node **count**, never by scale — so zoom was pure magnification *by construction*.

Reviewer verdict `DO NOT SHIP`: 2 Critical, 5 Important, 8 Minor — see §8.

**Ruling on the mid-zoom aggregate edges** (the sharpest judgement in the phase, escalated
deliberately rather than settled quietly): **honest in the model, dishonest on screen.** Verified
honest — every drawn pair has ≥1 real backing edge, the cited `payloadIndex` is a real row whose
endpoints are exactly in the two named groups, intra-group edges are counted not drawn, and the fold
is on the ordered pair so arrow direction is real. Not an invented relationship, and **not removed**.
What was wrong: 193 lines standing for **300** recorded edges, **63** of them silently bundling ≥2
distinct relation types, all with the **same stroke and same arrowhead** as a genuine 1:1 symbol
edge, and **0** carrying `<title>`/`aria` — the proof existed only in `data-*` attributes no user and
no AT can perceive.

### Unit G — suggested commands and help concision (slices 9, 10)

Suggestions are derived from the live index, never hardcoded, and **every candidate is folded through
the real parser and reducer** before being offered — a suggestion that would refuse or return an
empty set is dropped. Two deviations from the brief's example list, both justified: `Community` →
`Cluster` everywhere (the shipped surface says Cluster, while the grammar verb stays `community`),
and `Find a Path From This Node` **not offered** because it is the same canonical command as
`Use as Path Start` — offering one command under two labels would claim a capability the grammar does
not have.

Deep-level suggestions name the mark's **file** or **cluster**, never the symbol, because
`resolveNode` addresses the served-file projection and a symbol name is genuinely not addressable.

Insert-then-Run is the only path for anything that filters, focuses, selects or routes; direct
execution is allowlisted to `fit` alone, enforced by demotion in the generator. Each chip shows a
**word** (`fills the bar` / `runs now` / `opens help`), never colour alone.

The `detail` / `zoom` verb was **declined** with reasons, the decisive one being that the parser is
deliberately index-free and state-free and could not compute a target scale without a new
`GraphAction` in a Unit F file — reported, not built.

Help was rebuilt to eight sections, seven visible, with exact counts / fingerprints / builder ids /
raw relation identifiers / the grammar table / bounds / keyboard detail moved into a collapsed
Technical Details. **Boundary and honesty claims were deliberately kept OUTSIDE every `<details>`**,
with tests asserting so — the same defect class that produced Unit E's C1.

**Its shortcut audit found the previous help was wrong about the implementation**: `=`, `_`,
`Space`/`Spacebar` and `Home`/`End` were all implemented but undocumented, and `Enter` on a deep mark
**pins** rather than selects. The help now presses each documented key in a test and asserts the
documented effect, so it cannot over-promise by prose again. It also corrected a legend that claimed
a shape distinction the canvas does not draw (a cluster is a circle, exactly like a file).

## 8. Unit F review findings — full list, and their disposition

Recorded in full because they were adjudicated *before* the fix round, and because the fix round was
interrupted by an org spend limit (§10).

**Critical**
1. **Keyboard focus is destroyed on every level-of-detail transition.** `GraphCanvas.tsx:192-194`
   calls only `setRovingId`, never `.focus()`; React unmounts the focused `<g>` when the mark set is
   replaced. Reproduced: focus a cluster mark → press `+` ×4 (keys the mark itself handles) →
   `document.activeElement === document.body`. Roving tabindex is maintained correctly; DOM focus is
   simply lost. The existing test crosses that exact boundary and asserts only the zoom readout.
2. **Cluster level affirmatively misstates provenance.** The canvas prints, for *both* deep levels,
   "only the marks and the arrows come from the graph" — at cluster level neither is a graph object —
   and "193 relationships drawn" for 193 folds backing 300 real edges.

**Important**
3. **"The 100% view is pixel-identical to P36R" is false.** `vector-effect="non-scaling-stroke"` is
   newly added and **no stylesheet has ever set `vector-effect`**, so strokes go from ~0.55×
   user-unit to full device px (~1.8× thicker on a 600px canvas); and `SELECTED_MARK_FACTOR = 1.35`
   makes a selected node 35% larger. The radius/label constants *are* preserved at scale 1 — but the
   default view already signed off does change.
4. **At symbol zoom, 260 marks render with ZERO labels** (`deepLabelIds` returns empty whenever
   `level === 'symbol' && nodes.length > 24`). The defect being fixed was "zoom reveals nothing";
   the deepest level reveals 260 anonymous shapes. Inconsistent with the base layer, which uses
   collision-filtered `placedLabelIds` above `LABEL_LIMIT` rather than nothing.
5. **Level transitions are announced to nobody** — no `role="status"` on the level chip, the counts
   note, the focus-suspend note or the unavailable note. With finding 1, *Reveal Detail* gives a
   screen-reader user no feedback **and** destroys focus.
6. **Browse is a second-class fallback, not the accessible complement.** `deepNeeded` requires
   `state.mode === 'explore'`, so entering Browse directly never fetches the layer; and Browse offers
   per-file counts only, so `GraphDeepDetail` is reachable **only** by a canvas gesture. This
   violates two explicit phase requirements ("no pointer-only graph access"; "Browse remains the
   exact accessible textual complement").
7. **The bounded-DOM test is vacuous and the reported number is wrong.** It asserts `< 1200` elements
   against an **8-row fixture**. Real measured counts: **968** file / **557** cluster / **985**
   symbol. Unit F's reported 1,263 is not reproducible and **would fail its own assertion**. (The
   real answer is comfortably inside "do not render thousands".)

**Minor** — staleness sentence duplicated and persisting at 100% zoom where no deep layer is drawn ·
`MAX_DEEP_NEIGHBORS = 40` is the unit's only **silent** cap · the edge cap's wording never says
"capped" · raw NUL/SOH bytes used as string separators (invisible in every diff/grep tool) · a dead
`stalenessSentence` branch · the 19 base concept nodes vanish at deep levels with no disclosure ·
the `served_set_consistency === 'stale'` clause has no coverage and is unreachable today.

**Cross-unit decision (orchestrator):** `deepSelectedId` is never cleared when the canvas returns to
the file level, so the pinned-symbol pane *and* Unit G's deep suggestion set persist at 100% zoom
where no symbol is drawn. Deep-only UI must not claim state that is not on screen; the selection is
to be cleared when the level returns to `file`.

**Verified correct by the reviewer, and not to be re-litigated:** determinism is clean (no
`Math.random`/`Date`/`performance.now`/`rAF`; the single `getBoundingClientRect` feeds only pointer
panning and is pre-existing; two successive plans are `JSON.stringify`-identical) · the `graph.css`
label-declaration removal is clean, with 0 competing `font-size`/`stroke-width` in any stylesheet
including at-rules · the bounded-size tests do measure the rendered DOM · the base layer draws no
arrows (correct, since its edges are deduplicated and undirected) · the file-level "only payload
edges are drawn" invariant holds · caps are enforced in code and the node cap bites on real data
(260 of 336) and **is** disclosed · performance reproduced (parse 0.97–1.08 ms, decode 10.3–12.8 ms,
plan median 0.37–0.83 ms, worst 1.94 ms — the claimed 4.28 ms was conservative) · hover/keyboard
tooltip equivalence is structural and tested · the degraded copy is honest · suspend-on-focus is
explained and tested · *Reveal Detail* is justified (at 2400% centred on the origin the plan yields
0 marks, so uncentred zoom genuinely reveals nothing).

## 9. Orchestrator verification, and two corrections to the record

Established independently rather than accepted from unit reports.

**Baseline reconstruction.** Canonical `ISAAC-DOE/isaac-metadata-assistant` (`origin`); branch
`feat/p36v1-hosted-qa-fix-forward`; local HEAD == `origin/main` == `f563a66` == the user-supplied
hosted SHA; no open PRs; latest image tag `v0.0.24`; synthetic-only; ephemeral persistence.

**Deep-artifact safety, verified before building any renderer on it.** 2,612 nodes · 4,067 edges ·
221 communities · 493,985 bytes columnar; **byte-identical on rebuild** (sha256
`e403d854f1c40ee14ccde587fdba44daaefc6a41bf06b9a970f2c9b3f7ebafce`); 179 unique `source_file`
values, **all 179 inside** the served-content manifest; `git check-ignore` over all 179 returned
**nothing**; zero `/Users/`, `/home/`, `/root/`, drive-letter, `file://`; zero `http://`/`https://`;
zero secret-pattern matches. It ships via the existing `COPY apps/api/` with **no** Dockerfile or
`.dockerignore` change (verified: no `data/` exclusion).

**Correction 1 — the 200/201 counts.** I first reported CLAUDE.md §17's "201 entries" as simply
wrong. It is more precise than that: `snapshot["served"]` genuinely has **201** paths and the content
manifest has **200**; the difference is `tests/fixtures/memory_snapshot/memory-snapshot.json`, which
the manifest builder self-excludes because embedding a snapshot digest inside a snapshot is circular.
§17 conflated two different sets rather than being off by one. Both numbers are now documented with
their meanings, and the response gained an additive `served_file_count_scope` field so a consumer
cannot misread the provenance block.

**Correction 2 — the "pathological test" was a false alarm I caused.** Unit B reported that
`test_memory_graph_detail.py` had accumulated 43 minutes of CPU and would block CI. That process was
**my own** backgrounded `pytest` run, launched 45 minutes earlier against the file while Unit C was
still mid-edit, and stuck in that broken state. Killed; the identical command then ran **137 passed
in 4.85s**. Three independent measurements agree, and Unit C's reviewer separately confirmed no
residual pathology (also noting `pytest-randomly` is not installed, so a `-p no:randomly` control was
a silent no-op). **There is no test-performance defect.** Operational lesson: never leave a long test
process backgrounded across a unit's edit window — a stale process misleads every later agent that
inspects the machine.

## 10. Interruption, and how the phase was protected

The Unit F fix round was terminated mid-edit by an **org monthly spend limit**, leaving two
TypeScript errors in the tree. Recovery, in order:

1. Diagnosed the breakage: an unused import in a scratch measurement file, and a half-applied
   `served_file_count_scope` addition (the key had been added to a `keyof` constraint list before the
   field existed on the interface).
2. Confirmed **none** of the C1–I5 fixes had landed — `GraphCanvas.tsx` still had exactly one
   `focus()` call, the pre-existing roving-navigation one.
3. Added the missing interface field, and **deleted three orphaned files** the interrupted agent had
   created: a scratch measurement test, `graphRealArtifact.ts` (imported by nothing), and
   `real-graph-projection.json` — a 119 kB duplicate of served content inside the frontend tree,
   which would have been free to drift from the backend. Safety-scanned before the decision (zero
   absolute paths, URLs, emails); removed because it was dead weight, not because it was unsafe.
4. Restored the tree to green and **committed a checkpoint** on the release branch, so any further
   interruption is recoverable from git rather than from a working tree.

This is recorded rather than smoothed over: the orchestration policy in `CLAUDE.md` §10 reserves
production code for implementation subagents and requires independent review per state-changing
slice. Where the budget limit forced the orchestrator to make source edits directly, those edits are
named above and are limited to breakage repair and dead-file removal — no feature work.

**The interrupted agent was then resumed from its own transcript** (far cheaper than re-briefing) with
a revised priority: lock the two Criticals in with tests first, leave the tree green after every
increment, and treat the Importants as best-effort. It completed **all** Criticals, Importants,
Minors and the cross-unit decision — see §11.

## 11. Unit F fix round — what landed

All 15 findings closed. Frontend **1690 → 1721** tests (84 files), no test weakened.

- **C1** `pendingFocus` is armed **only** from the two mark keydown handlers — the only path that can
  destroy focus, since toolbar and command-bar actions keep focus on a control that stays mounted.
  `transitionFocusTarget` resolves by **containment** in both directions (file→cluster, cluster→symbol
  or its file, symbol→its cluster, any→its file), falling back to `svgRef.focus()`; never `<body>`.
  The request stays armed across renders while the mark survives (the deep payload is lazy and can
  replace the set a render later) and disarms the moment `document.activeElement` is no longer that
  mark, so focus is never *stolen*. Tested in both directions from base and deep marks, including the
  cold/lazy no-counterpart case and **two negative cases**.
- **C2** Aggregates kept. Cluster copy now says a mark is a *group* and a line *summarises*; the
  symbol level says "ONE recorded symbol / ONE recorded reference". One pure `deepCountsSentence`
  states real backing, folds, multi-relation folds and intra-cluster edges counted-not-drawn. Visually
  `.memory-graph-deep-edge-aggregate` is dashed, wider, and uses a **hollow** arrowhead against the
  solid symbol-level one — shape and dash, never colour alone. Each aggregate carries a `<title>` and
  `role="img"`/`aria-label` naming the backing count, both endpoint files and the folded relation
  kinds, plus a keyboard-reachable sentence in the pinned cluster panel. `data-*` is now explicitly
  test-only.
- **I1** Resolved per cause. `vector-effect` **kept** (those widths are state-driven CSS rules, so they
  cannot be attributes, and in user units the 3.4 focus ring reached ~44 device px at the 2400% clamp)
  — and the fact that **the signed-off 100% view therefore changed** is now stated plainly in
  `graphModel.ts` instead of denied. `SELECTED_MARK_FACTOR` **reverted** for the base layer, restoring
  P36R parity; kept for deep marks only.
- **I2** `placedDeepLabelIds` mirrors the base layer's `placedLabelIds`: all marks ≤ 24, else ≤ 18
  collision-filtered landmarks, at **both** deep levels. Measured 0 labels / 260 marks before; > 0 at
  both levels now, asserted against the real artifact, bound disclosed on the canvas.
- **I3** One canvas-owned visually-hidden `role="status"`; the loading note's separate region was
  folded into it, so the surface still has exactly one and the existing "one live region" tests still
  hold. The string is a function of the drawn level and deep state only — no counts — and is empty on
  arrival. Tested: one announcement per level change, **zero** across 3 zoom steps and 2 pans inside a
  level, and the genuine "nothing drawn" crossing *is* announced.
- **I4** `deepNeeded` no longer requires Explore. Browse has its own opt-in **Load Symbol-Level
  Detail** control (still lazy, states the cost); each file row's count became a real `aria-expanded`
  disclosure opening a textual symbol list (kind · cluster · line · relationship count, capped at 40,
  **disclosed**); selecting one opens the shared `GraphDeepDetail`. `deepShowing` was split from
  `deepNeeded` so a Browse fetch can never make the canvas count line lie.
- **I5** True counts reproduced against the live backend: **968 file / 557 cluster / 985 symbol**;
  labels 18 / 18 / 0-before; cluster 193 lines ↔ **300** backing, 73 folded, 63 multi-relation.
  **1,263 was wrong and is corrected in the code.** The new `graph-real-artifact.test.tsx` reads the
  committed artifact **from disk** — no duplicated bytes — and its header states exactly what is real
  and what is reconstructed, so the per-level figures are same-order but not claimed equal to live.
- **Minors** staleness gated on a drawn plan and de-duplicated (exactly one occurrence per screen,
  asserted) · deep selection cleared when no deep layer is drawn, value cleared and prop untouched so
  Unit G's contract holds, **Browse deliberately exempt** because there it is the textual route in ·
  stale served-set clause covered both ways · neighbour cap, "capped from" wording and departing
  concept nodes disclosed · raw NUL/SOH replaced with ` `/`` · the dead staleness branch
  widened (it would still have printed a false denial for a HEAD-describing point-in-time payload).

**A real defect found by its own new test:** *Reveal Detail* from 140% landed on
`1.7499999999999998`, which read as the **file** level — so the button zoomed in and revealed nothing,
and `nextLodScale` returned 1.75 again, meaning repeated presses could **never** reach the symbol
level. Fixed with a scale epsilon and the exact float pinned in a test. The `LOD_*` constants are
unchanged, so Unit G's help cannot drift from them.

**Graph help corrections (orchestrator, copy only).** Unit F reported four items in `GraphHelp.tsx`,
which it does not own. All were applied: the same false *"only the marks and the arrows come from the
graph"* claim removed; the level-dependent meaning of a mark and a line documented; the neighbour cap,
deep label bounds and pinned-symbol release disclosed; and the arrow legend corrected so a dashed
aggregate cannot read as a single reference. **Unit G's concision guard was held, not relaxed** —
adding honesty copy pushed visible text from ~5,500 to 5,773 chars against a 5,500 bound with a row
over the 240-char limit, so redundant existing prose was trimmed to pay for it (final: 5,4xx visible,
ratio 0.56). Weakening that bound to fit new prose would have been the exact "do not weaken tests"
violation the phase forbids.

## 12. Unit H — DEFERRED, with reasons

Slice 14 (cross-surface visual-consistency sweep) was **not run as a separate unit.** Stating this
plainly rather than implying coverage:

- The org monthly spend limit ended the subagent budget mid-phase.
- Much of slice 14's substance was already enforced *within* each unit and its independent review:
  heading hierarchy, focus rings, chip colours, top gutters, long-path wrapping, no-colour-only
  meaning and disclosure discipline were all findings-level items in the E, B, C and F reviews, and
  all were fixed.
- What is genuinely **not** done is a single pass comparing all changed surfaces against each other
  for Title-Case/sentence-case consistency, divider and card-padding consistency, and cross-surface
  chip-colour agreement. No claim is made that this was checked.

## 13. Verification battery — final, on the merge candidate

| Check | Result |
|---|---|
| Frontend suite | **1721 passed / 84 files** |
| Backend suite | **1328 passed / 0 failed** |
| `tsc -b` | clean |
| Production build | clean, 1673 modules |
| `/krish` base-path build | verified — `/krish/assets/` prefixing, `/krish/api` baked in |
| Snapshot drift, BOTH artifacts | **exit 0** — `--detail-out` form |
| Committed-artifact gates | 155 passed (`test_committed_snapshot` + `test_memory_graph_detail`) |
| Secret scan (staged diff) | clean |
| Forbidden-path scan | clean — no `dist/`, `examples/`, `drafts/`, `records/`, `graphify-out/`, `.env` |
| `.only` / `.skip` / `xit` audit | none |
| Bundle | JS 589.63 kB (gzip 171.14) · CSS 167.74 kB (gzip 24.21) |
| Bundle vs `f563a66` baseline | **+55.50 kB JS (+16.47 gzip) · +8.89 kB CSS (+1.28 gzip)** |
| New npm dependencies | **none** |

**Not run, and not claimed:** Docker build/smoke (heavy, and the image content is unchanged in
structure — the new artifact ships via the existing `COPY apps/api/`), and automated accessibility or
contrast tooling (none exists in this repo).

## 14. Visual QA — what was and was not done

**No browser screenshot QA was performed.** This must be said directly, because the authorizing brief
asked for it. The repository has **no Playwright, no screenshot harness and no visual-regression
tooling** — only vitest + jsdom — and the phase forbids new dependencies. jsdom computes **no layout**:
it produces no pixels, no reflow, no contrast and no frame rate.

Every layout and hierarchy claim in this phase is therefore either a DOM-structure assertion or an
arithmetic argument from declared CSS values. Where units reported layout improvements they said so
explicitly, and those statements are reproduced here rather than upgraded:

- Settings API Access: the residual dead zone is *reasoned* to fall from ~20–25% to under ~10% of the
  widest column. **Not measured.**
- The dashed aggregate stroke, the hollow arrowhead, the new Browse disclosures and the I1 stroke-width
  change are **reasoned from declared values only.**
- No contrast ratio was machine-verified. Unit G hand-computed ~5.6:1 for its section eyebrows; the
  `runs now` / `fills the bar` tags are 9.5px italic and want a human look.

**Krish's human visual sign-off is therefore still required and is not claimed here.**
