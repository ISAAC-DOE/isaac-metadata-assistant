# Record-screen redesign — before/after evidence, 2026-09-03

This is a measured comparison of the Review Record screen before and after the
record-screen redesign (PR-A through PR-E, plus #232 — see
`docs/session-closure-2026-09-03.md` for the full slice history). Every number
in this document comes from one of the two harness runs described below;
nothing is estimated. **No screenshot from either run is committed to this
repository** (see "Screenshots" below for why); every one referenced here is
named by its local scratchpad path instead.

## Method

**Harness.** A single Playwright script (`capture.mjs`) navigates a fixed set
of pages at five viewports, and records DOM/network/timing/keyboard/
interaction-latency measurements plus screenshots. The identical script,
parametrized by environment variables, produced both runs; the AFTER run used
a copy (`capture-after.mjs`) extended with the four record workspaces the
redesign introduced (`?view=fields|runs|capture|graph`) and updated selectors
for two renamed controls (see "What changed in the harness" below). Both
scripts and their outputs live outside this repo, in this session's scratchpad:

```
/private/tmp/claude-501/-Users-krishverma-Documents-ISAAC/8921bb97-45b0-4cab-8fc0-3d4453250d98/scratchpad/evidence/
  harness/capture.mjs           # BEFORE script (unmodified)
  harness/capture-after.mjs     # AFTER script (workspace-aware)
  harness/build_summary.py      # measurements.json -> summary.md
  before/measurements.json, before/summary.md, before/screenshots/  (79 shots)
  after/measurements.json,  after/summary.md,  after/screenshots/  (110 shots)
```

**BEFORE.** Captured 2026-09-03T18:57:29Z against `main` at `6ce3f5c`
(the merge commit of PR #227, released as v0.0.213 — this session's own
starting point, NOT the head of PR #231; `3aa6e95`/`ec945d7` are this
session's own work, six commits and six PRs later. `6ce3f5c` is an ancestor
of this worktree's base `3aa6e95` — `git merge-base --is-ancestor 6ce3f5c
HEAD` exits 0), served from the shared dev servers already running on this
host: web `http://127.0.0.1:5300`, API `http://127.0.0.1:8300/api`. Record: the shared seeded record
`01M1M8SVVGZPRFND96VBV594XZ` ("Synthetic XANES campaign — redesign
baseline"), 2 runs, 1 typed note, 1 open run-scoped proposal; a separately
created 12-run record `01M1M9V4SFBYP3KRHAR5H5BRE5` for the focused-run and
graph interaction-latency measurements.

**AFTER.** Captured 2026-09-04T04:45:10Z against this worktree
(`docs/session-closure-2026-09-03`, based on `3aa6e95`) from two servers
started for this task only: API `.venv/bin/uvicorn isaac_api.app:app` on
`127.0.0.1:8320` against a fresh scratch `ISAAC_UI_WORKSPACE`, web `vite` on
`127.0.0.1:5320`. Records were built via the same public API the BEFORE run
used (`setup_records.py`, in the same `evidence/after/` directory): a 2-run
record `01M1NBN4J8DAD23CDXYEVH38S5` with an equivalent typed note and an
equivalent run-scoped proposal (`system.facility.site` = `SSRL`, run-scoped
to Run B), and a 12-run record `01M1NBN4JT2145PTMTWP6877W2`. Neither shared
server (8300/5300) was touched by this run.

**What changed in the harness, and why.** Two selectors from the BEFORE
script no longer match the redesigned app, both confirmed by reading the
current source before editing the script (not guessed):

- The transcript-capture entry control's accessible name changed from
  `'Start a capture'` to `'Capture Experiment Notes'`
  (`CAPTURE_COPY.entryOpen`, `apps/web/src/lib/transcriptCaptureContent.ts`),
  and the control now lives on the Capture & Proposals workspace rather than
  inline on one page.
- The standalone `aria-label="Focus run …"` button is gone (PR-C review
  finding I-3 — the redesign moved to master-detail, where a compact run
  row's whole header is the open control). The AFTER script clicks
  `.run-card-header-compact` and waits for the URL to gain `?run=`, which is
  the one contract PR-C's own code comments say was kept explicit.
- The Graph switcher changed from an in-page `role="tab"` to a real sidebar
  `<Link>` (`RecordWorkspaceNav`, `RECORD_WORKSPACES` in
  `apps/web/src/lib/routes.ts`); the AFTER script clicks
  `getByRole('link', { name: 'Graph' })` instead of `getByRole('tab', ...)`.

No other page, viewport, or measurement was altered. The full diff reasoning
is in the AFTER script's inline comments at each changed call site.

**Caveats, stated once here rather than repeated per number:**

- API byte totals below are **`/api/` payload only**, not total network
  bytes. Both runs serve unbundled ES module source over `vite dev`, so raw
  totals run into the tens of megabytes on every page in both BEFORE and
  AFTER and are not comparable to a production build; they are excluded from
  every table in this document.
- `/record/<id>/export`'s `.../revisions` call returns HTTP 503 in both runs
  (`experiment_storage.durable: false` — no PostgreSQL configured for either
  local run); this is orthogonal to the redesign and unchanged between runs.
- The BEFORE and AFTER records are **equivalent, not identical** — different
  ULIDs, created independently on different backends a day apart. Where a
  number could plausibly be sensitive to record content (e.g. field-count
  chips), that is noted at the point of use.
- **The Impeccable skill's mechanical UI detector was DEGRADED in this
  environment and produced no information.** No finding in this document
  comes from it; every number here comes from the Playwright harness or from
  reading source.
- **not measured: genuine 200%-zoom behaviour.** No CDP method can drive a
  real browser zoom level (this is a standing, repository-wide limitation —
  see `CLAUDE.md` §11/§15); nothing in this document should be read as that
  sign-off, which remains Krish's alone.
- **not measured: hosted/production timing.** Both runs are `vite dev`
  against a local, single-request backend; no number here says anything
  about `/krish` latency.

## Headline: default record page (fields workspace), before → after

This is the BEFORE run's single record page (`/record/<id>`) against the
AFTER run's **fields workspace**, which is what a bare `/record/<id>` URL
still resolves to by default (`RECORD_VIEW_IDS`'s first/fallback member,
`apps/web/src/lib/routes.ts`) — so this is a like-for-like comparison of the
same URL, not a comparison chosen to flatter one side.

| Viewport (px) | scrollHeight px | DOM nodes | Interactive controls (visible, total) | Interactive controls (first viewport) | Sections on load | Total requests | API requests | API bytes | Unbounded `/pending` | DCL (ms) | FCP (ms) | `.record-title` visible (ms) | Long tasks (n / ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| desktop (1440) | 3116 → 1067 | 515 → 384 | 59 → 34 | 32 → 33 | 14 → 10 | 235 → 232 | 29 → 23 | 56676 B → 43274 B | 2 → 2 | 358.2 → 149.4 | 432 → 188 | 437 → 195 | 0/0 → 0/0 |
| laptop (1280) | 3270 → 1155 | 515 → 384 | 59 → 34 | 26 → 30 | 14 → 10 | 235 → 232 | 29 → 23 | 56676 B → 43274 B | 2 → 2 | 341.3 → 146.8 | 396 → 184 | 403 → 188 | 0/0 → 0/0 |
| tablet (768) | 3707 → 1491 | 515 → 384 | 47 → 21 | 10 → 16 | 14 → 10 | 235 → 232 | 29 → 23 | 56676 B → 43274 B | 2 → 2 | 480.1 → 142.7 | 544 → 180 | 554 → 182 | 0/0 → 0/0 |
| mobile390 (390) | 4969 → 1999 | 515 → 384 | 47 → 21 | 9 → 11 | 14 → 10 | 235 → 232 | 29 → 23 | 56676 B → 43274 B | 2 → 2 | 383 → 140.9 | 424 → 176 | 457 → 182 | 0/0 → 0/0 |
| mobile320 (320) | 5763 → 2260 | 515 → 384 | 47 → 21 | 9 → 11 | 14 → 10 | 235 → 232 | 29 → 23 | 56676 B → 43274 B | 2 → 2 | 339.9 → 148.3 | 388 → 184 | 392 → 188 | 0/0 → 0/0 |

Interaction latency, on the 12-run record (`focus/open a run` and `open the
graph`), desktop viewport:

| Interaction | Before | After |
|---|---|---|
| Open a run (Focus/master-detail row click → editor visible) | 81 ms | 48 ms |
| Open the graph (tab/link click → graph content visible) | 224 ms | 113 ms |

Keyboard walk, desktop viewport, 40 `Tab` presses from page load, no mouse:

| | Before | After |
|---|---|---|
| First interactive stop (after `Skip to content` / logo / Search / spine) | step 7, `Record Fields` | step 6, `Record Fields` |
| Completed a full forward cycle within 40 tabs? | No — still inside the field-block accordion at step 40 (`Environment & Context`) | Yes — cycled back to `Skip to content` at step 36, after 34 stops |
| All 34/40 stops carried a visible focus ring | yes | yes |

The full 40-step traces are in each run's own `measurements.json` →
`keyboard.record_desktop.steps`.

## What the numbers show

The fields workspace is materially smaller and faster to reach on every
viewport measured: page height fell 61–66%, DOM node count fell 25%, visible
interactive controls on the page fell 42–55%, and the section count fell
from 14 to 10 — consistent with the redesign moving Runs and Capture &
Proposals content out of one continuous scroll into their own workspaces
(below). The record's graph is not part of that reduction in the same way:
BEFORE, it was never stacked into the scroll at all — it was reached through
an in-page `.section-tabs` switcher (Fields/Graph) that swapped content in
place — and AFTER it is the fourth workspace, reached by the same navigation
mechanism as the other three rather than a newly-extracted section. API request count and payload fell too (29→23
requests, ~24% fewer bytes), because the fields workspace no longer issues
the run-list and capture-panel reads that used to load on every page view
regardless of which part of the record a reader wanted. DCL and FCP roughly
halved on every viewport (e.g. desktop DCL 358→149 ms, FCP 432→188 ms); this
tracks the smaller initial DOM and is not claimed as a production-network
result (see caveats above — both runs are `vite dev`). The **one number that
did not move** is the unbounded-`/pending` count (2 → 2 on every viewport):
Review Record's initial load is still intentionally unbounded per
`CLAUDE.md` §11 ("Review Record's initial load is unchanged and still
unbounded"), and this run confirms that invariant held through the redesign
rather than drifting.

The keyboard walk shows the same story from a different angle: BEFORE, 40
tabs from page load were still inside the Fields accordion and had not yet
reached Runs, Capture, or any proposal control on the same page. AFTER, one
full loop of the fields workspace — spine, the four workspace links, Evidence
Trail, the field-block accordion headers, and the Assistant panel's own
controls — completes in 34 stops. This is not a claim that the AFTER page
has less content overall; it is a measurement that a reader tabbing through
the **fields workspace specifically** now reaches the end of it, rather than
still being inside one 40-item scroll that also contained two other
workflows' controls.

## The three new workspaces (AFTER only — no BEFORE equivalent page existed)

There is no BEFORE page to compare these against; the numbers below are
reported alone, at desktop viewport, from the AFTER run only.

| Workspace | URL | scrollHeight | DOM nodes | Interactive (visible) | Sections | API requests | API bytes | Unbounded `/pending` |
|---|---|---|---|---|---|---|---|---|
| Runs | `?view=runs` | 1006 | 344 | 34 | 3 | 23 | 44232 B | 2 |
| Capture & Proposals | `?view=capture` | 1484 | 367 | 41 | 4 | 28 | 59128 B | 2 |
| Graph | `?view=graph` | 2481 | 438 | 53 | 2 | 35 | 66840 B | 2 |

`not measured: no BEFORE page existed at these URLs to compare against` — the
redesign's whole premise was splitting one page into four, so there is no
prior number for "the Runs workspace" as a standalone page; the closest
prior comparison is the headline table above, where these three workspaces'
content used to live inside the single `/record/<id>` page's height and DOM
count.

Console errors: none observed on any of the three new workspace pages or on
`record-transcript-open` (which now opens on the Capture & Proposals
workspace). `record-export` shows the same two pre-existing `503` console
errors in both BEFORE and AFTER (see caveats).

## Screenshots

**No screenshot is committed to this repository.** An earlier pass of this
document staged 24 selected PNGs under `docs/evidence/redesign-2026-09-03/`
and described them as committed; that directory was removed
(`git rm`, commit `d474cc0`) because PR #234's frontend CI job failed
`apps/web/src/__tests__/source-is-greppable.test.ts` — this repository's
greppability guard holds every TRACKED file to zero raw NUL bytes, with
exactly one named exemption
(`qa/validator-upload-package/isaac-validator-qa-files.zip`, per
`CLAUDE.md` §11's "Session of 2026-08-26/27" entry). A PNG is binary and
therefore fails that guard by construction; the guard does not distinguish
a "small, individually-reasonable" image from any other binary file, and
adding a second exemption for this bundle was rejected rather than pursued.
All screenshots this evidence run produced exist **only in this session's
local scratchpad bundle**, listed here by filename so a reader with access
to that path (or a re-run of the capture — see "Reproduction" below) can
find them:

`/private/tmp/claude-501/-Users-krishverma-Documents-ISAAC/8921bb97-45b0-4cab-8fc0-3d4453250d98/scratchpad/evidence/after/screenshots/`:

- `record__{desktop,laptop,tablet,mobile390,mobile320}__viewport.png` —
  the fields workspace at 1440/1280/768/390/320.
- `record-runs__{desktop,laptop,tablet,mobile390,mobile320}__viewport.png`
  — the Runs workspace (master-detail list) at the same five widths.
- `record-capture__{desktop,laptop,tablet,mobile390,mobile320}__viewport.png`
  — the Capture & Proposals workspace at the same five widths.
- `record-assistant-drawer__{tablet,mobile390,mobile320}__{viewport,full,assistant}.png`
  — the Assistant drawer open at 768/390/320.
- `record__desktop__assistant-collapsed.png` — the Assistant rail collapsed
  at 1440px (captured with a one-off script, `harness/collapsed-rail-shot.mjs`,
  that clicks `Collapse Assistant` and screenshots the result — not part of
  the main capture pass).

`/private/tmp/claude-501/-Users-krishverma-Documents-ISAAC/8921bb97-45b0-4cab-8fc0-3d4453250d98/scratchpad/prd/shots/`:

- `{01-idle,02-requesting-permission,03-recording,04-held,05-permission-denied,
  06-unsupported,07-processing,08-proposals-ready,09-recoverable-error,
  10-proposal-card-more-open}-{1440,768,390,320}.png` — the ten
  `TranscriptCapturePanel` states at all four widths (40 files, 5.9 MB
  total), from this session's own prior capture.

The full 110-screenshot AFTER set (viewport + full-page for every page ×
viewport, plus the three assistant-drawer captures) is at
`/private/tmp/claude-501/-Users-krishverma-Documents-ISAAC/8921bb97-45b0-4cab-8fc0-3d4453250d98/scratchpad/evidence/after/screenshots/`
(18 MB) and the equivalent 79-screenshot BEFORE set at `.../evidence/before/screenshots/`
(16 MB) — neither set, nor any subset of either, is committed to this
repository.

## Reproduction

```bash
# BEFORE state: git checkout 6ce3f5c (or use the running shared dev servers)
# AFTER state: this worktree, branch docs/session-closure-2026-09-03

cd apps/web && npm ci   # once per worktree

ISAAC_UI_WORKSPACE=<scratch dir> ISAAC_UI_CORS_ORIGINS=http://127.0.0.1:5320 \
  /Users/krishverma/Documents/ISAAC/.venv/bin/uvicorn isaac_api.app:app \
  --app-dir apps/api --host 127.0.0.1 --port 8320 &

cd apps/web && VITE_API_BASE=http://127.0.0.1:8320/api \
  npx vite --host 127.0.0.1 --port 5320 --strictPort &

python3 <scratchpad>/evidence/after/setup_records.py   # creates the two records

cd apps/web
BASE_URL=http://127.0.0.1:5320 API_BASE=http://127.0.0.1:8320/api \
  OUT_DIR=<out> RECORD_ID=<2-run id> MANY_RUNS_RECORD_ID=<12-run id> \
  MANY_RUNS_RUN_ID=<a run id> FOCUS_TARGET_RUN_ID=<a different run id> \
  LABEL=after \
  node <scratchpad>/evidence/harness/capture-after.mjs

python3 <scratchpad>/evidence/harness/build_summary.py <out>/measurements.json <out>/summary.md
```
