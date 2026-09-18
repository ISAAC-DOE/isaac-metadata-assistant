# Browser QA, 2026-09-18 — ten routes, four widths, local build

**Commit measured: `c9ffed06`** (`main`, PR #271's merge). **This is a LOCAL build, not the hosted
deployment** — `/krish` sits behind an Authentik edge this environment cannot authenticate to, so
nothing here is evidence about any hosted image. Hosted QA remains `PENDING (Krish)`.

**Result: no defects found**, and every candidate finding below was investigated and cleared rather
than reported. Two genuine Minor findings are recorded in §6. §5 is the **first independent
confirmation** of `QA-020`, which the ledger records as shipped *"ORCHESTRATOR-IMPLEMENTED, NOT
INDEPENDENTLY REVIEWED"* — and it also records a correction to my own first draft of that section,
which had called the ledger stale after reading only its earlier superseded row.

---

## 0. What this measured, and what it did NOT

| measured | NOT measured |
|---|---|
| horizontal overflow, over-wide elements, genuine text clipping | interaction flows (create → answer → export) |
| console errors, warnings, uncaught exceptions, unhandled rejections | the three slices in flight at the time (`ACT-003b`, `ACT-004`, `CTX-004`) |
| landmarks, heading order, `h1` presence, document titles | axe rule violations (that is CI's Linux a11y job) |
| accessible names on interactive controls, via the DOM's own `.labels` | true 200% browser zoom — **no CDP method can drive it** |
| snake_case / dotted-path jargon in visible text nodes | pixel heights against `DEC-25`'s 3,820 px density bar |
| not-found and unknown-route states | a real microphone / OS indicator check |

The last three rows stay **human gates** and are not closable from here.

---

## 1. Harness, and the two traps it was built against

Local build: backend `uvicorn isaac_api.app:create_app --factory --port 8010` with
`PYTHONPATH=apps/api`, a **fresh empty `ISAAC_UI_WORKSPACE`**, and
`ISAAC_UI_CORS_ORIGINS=http://localhost:5183`; frontend `vite --port 5183 --strictPort` with
`VITE_API_BASE=http://localhost:8010/api`. `/api/health` confirmed `mode: synthetic-only`,
`database.configured: false`, `experiment_storage.backend: filesystem`, `state: ephemeral`.

**Ports 5173 and 8000 could not be used, and the reason is worth recording.** Both were held by
**orphaned dev servers from dead sessions** — a `vite` running since **Sep 14** (3 d 20 h) and a
`uvicorn` since **Sep 15** (2 d 15 h), `lsof` showing **no client attached to either**. Three
consecutive sessions have reported local a11y and browser QA as "impossible"; the actual cause was
these two orphans, not the architecture. An attempt to reclaim them was refused by this
environment's command classifier and was **not worked around**.

**Consequence, disclosed:** running the API on `8010` sets `VITE_API_BASE`, which flips
`isHostedBuild` (`apps/web/src/lib/api.ts`). Per that file's own comment the only effect is that the
app stops claiming a local run command is the remedy — it withholds an instruction rather than
asserting a false one. That is acceptable for layout/console/label QA and is **why this harness must
not be used to move an a11y baseline cell**, whose rendered text would differ.

**Trap 1 — `resize_window` does not move the rendered viewport in this tooling.** Narrow widths were
therefore exercised in **same-origin iframes** sized explicitly, which is the established workaround
in this repository.

**Trap 2 — an unrendered page measures as perfectly clean.** Load average was **4–13** for this
session's duration (one agent measured **28.99**), so every probe carries a **render gate**: poll up
to 16 s for a non-empty `<h1>` and report `rendered` beside every result. Every row below reads
`rendered: true`. Without this gate, "no overflow" and "no clipping" would be indistinguishable from
"nothing loaded".

---

## 2. Routes × widths

Ten routes — the five global destinations plus all five record workspaces — at **1440, 1024, 390,
320**. Record routes used a record created through the product's own `POST /api/experiments` path,
then renamed and given a run, so it carried **two real activity events** (`experiment_renamed`,
`run_added`, channel `web`, actor `unattributed`).

| | result |
|---|---|
| `horizOverflow` (`documentElement.scrollWidth > innerWidth + 1`) | **false at every route × width** |
| elements wider than the viewport | **none at any route × width** |
| genuine text clipping | **none** — see §4 for the two hits that were not clipping |
| `rendered` gate | **true** for every cell |

Document titles are per-route and correctly ordered page-name-first: `My Experiments · ISAAC
Metadata Assistant`, `Statistics · …`, `Historical Import · …`, `Settings · …`, `Governance & Safety
· …`.

Landmarks on every global route: `header`, `nav[Primary]`, `main`, and on the Library additionally
`nav[Folder path]`. Heading order holds `h1 → h2 → h3` with no skipped level, including the record
screen's `h1` → panel `h2` → Activity day `h3`.

---

## 3. Console — zero, and negative-controlled

**Zero** `console.error`, `console.warn`, `window.error` or `unhandledrejection` events across all
ten routes, captured by a trap installed on each iframe's own `contentWindow` before load and
re-armed on a 30 ms interval until render.

**A bare zero here would have been a non-answer**, which is the failure mode `CLAUDE.md` §11 records
for `tr` on binary input, for `ugrep`'s complexity limit, and for the Impeccable detector's `[]`
exit 0. So the trap was negative-controlled: with the baseline at **0**, injecting all four channels
into a live iframe caught **4 of 4** —

```
error: NEGATIVE CONTROL error
warn: NEGATIVE CONTROL warn
window.error: Uncaught Error: NEGATIVE CONTROL thrown
unhandledrejection: Error: NEGATIVE CONTROL rejected
```

The zero is therefore a measurement.

---

## 4. Five candidate findings, all CLEARED — and why each was not a defect

Recorded in full, because a QA pass that reports only its conclusions gives a future session no way
to tell a checked surface from an unexamined one.

1. **`.record-title` clipped at 320 px** (`scrollWidth 324` vs `clientWidth 274`, ~50 px hidden, on
   all five record workspaces). **Not a defect:** computed style is `text-overflow: ellipsis`,
   `white-space: nowrap`, `overflow-x: hidden` — a deliberate elision — and the **full title is
   present unclipped elsewhere on the page**, in the `h1`'s `.record-page-title-name`
   (`scrollWidth == clientWidth == 242`). The elided copy is the top bar's secondary display.
   *It does carry no `title` attribute*, which would be the fix if the `h1` did not already hold the
   full string; it does.
2. **`.spine-meta` at `clientWidth: 1`** (`scrollWidth 191`, text *"Complete 'Complete Metadata'
   first."*). **Not a defect:** the element carries `spine-meta-compact-narrow`, the **known
   deliberate allowance** (`ALLOW-SPINE-META-COMPACT-NARROW`, `381dc5da`). The allowlist was checked
   *before* theorising a layout cause, which is the lesson a prior session recorded after doing it
   the other way round.
3. **Two "unlabelled" inputs** — `.library-search-input` on the Library and `.hi-input` on
   Historical Import. **Not defects; a gap in my probe.** The DOM's own `.labels` reports
   `"Search Experiments"` (an `sr-only <label for>`) plus `aria-describedby` and a descriptive
   placeholder for the first, and `"Name this import (optional)"` (a wrapping label) for the second.
   The first probe had only checked `aria-label`/`title`/text content.
4. **Small touch targets** on Statistics and Governance (heights 15–19 px). **Not defects:** every
   one is an `<a>` inside a `<p>` or `<span>` — link text in prose, which **WCAG 2.5.8 explicitly
   exempts** ("in a sentence or block of text").
5. **Jargon tokens** — `context.environment`, `timestamps.acquired_start_utc`, `created_utc`
   (Runs); `isaac_propose_field_value` (Capture); `isaac_records` (Settings). **All legitimate:**
   the first group are **schema paths**, which `UX-014` protects on the stated ground that a path is
   how a curator maps a field; `isaac_propose_field_value` names a real MCP tool inside an honest
   explanation of how a proposal arrives and is **deliberately kept** per §11; `isaac_records` is the
   core package name, served by `/api/health` as `core` and rendered among Settings' build facts.
   *A sixth apparent hit, `[BLOCKED: JWT token]`, is the browser tooling's own redaction of a
   long token in the page, not application text.*

---

## 5. `QA-020` — the FIRST INDEPENDENT CONFIRMATION of an item that shipped unreviewed

**A correction to my own first draft, kept because the error is instructive.** This section
originally read *"`QA-020` IS STALE"*, on the strength of the ledger's `### QA-020 — NO NOT-FOUND
STATE EXISTS` heading and its `FILED` row. **That was wrong, and it was wrong in the way this
repository's own resume protocol warns about: I read an earlier section and stopped.** The ledger
records `QA-020` as **DONE** further down, and the earlier `FILED` row is superseded in place —
which is this file's deliberate convention, not a contradiction.

**What IS true, and is the reason this section is worth keeping:** that entry is headed
***"DONE (ORCHESTRATOR-IMPLEMENTED, NOT INDEPENDENTLY REVIEWED)"***. So the measurement below is
the **first independent check** of it, and it confirms the shipped behaviour in both flavours:

| probe | result |
|---|---|
| `/no-such-route-at-all` | `h1` **"Page not found"**, document title **"Page not found · ISAAC Metadata Assistant"**, the attempted path echoed, and the boundary stated — *"This is about the address, not abou…"* |
| `/record/01ZZZZZZZZZZZZZZZZZZZZZZZZ?view=fields` | `h2` **"Record Not Found"**, honest prose (*"This experiment id is not in the workspace — it may not have be…"*), a link back to My Experiments |

**The entry's central design boundary reproduces exactly.** It says the screen answers for an
unrecognised **PATH** and never for a missing **RECORD**, because `/record/<unknown-ULID>` matches
`ROUTE_PATTERNS.record` and must reach `RecordWorkbench`'s own handling. Measured: it does — the two
probes above land on **two different surfaces** with two different headings. The entry notes a
negative control exists for precisely this, on the ground that if an unknown record id ever fell
through to the path screen, its *"no record was looked up"* sentence would become false on the most
common failing address in the product. That neighbouring claim holds at `c9ffed06`.

The workflow spine on the missing-**record** page renders **`spine-step skeleton` with no
`aria-current`** on all eleven nodes, so it claims **no** progress for a record that does not exist.
That was checked specifically, because a spine asserting "Record Created" for a missing record would
have been a false claim.

## 6. Two genuine Minor findings, not fixed here

1. **The missing-record page's document title reads `Record Fields · ISAAC Metadata Assistant`** —
   it names a record's fields screen for a record that is not there, while the unknown-route page
   correctly titles itself `Page not found`. This is not a violation of
   `apps/web/src/lib/documentTitle.ts`'s design but a consequence of it: the title is derived from
   `pathname + search` alone, *deliberately*, so that a screen cannot forget to set it, and screens
   with richer truth **refine** it through `useDocumentTitle`. The not-found branch simply never
   refines. **The fix is that module's own mechanism**, and the module's docstring already names the
   record screen as the one refiner.
2. **The skeleton spine is permanent on a page that has definitively concluded.** It claims no
   progress (good), but a skeleton implies "still loading" beside a settled *"Record Not Found"*.

Both are Minor, both are one-line-shaped, and neither is a false claim about science or validity.

**A third, recorded as taste rather than a defect:** the Statistics activity section's heading
*"Through Which Surface"* invites exactly the reading `activity.py:255-264` disclaims at length —
`web` does **not** mean "a person in a browser"; a `curl`, an OpenAPI consumer and a script are
indistinguishable in it. The source is honest; the screen carries none of that qualification. The
channel vocabulary is `DEC-44`'s and changing it is a decision, not a fix.

---

## 7. Data governance

Synthetic only. The record was created through the product's own API in a **fresh empty workspace**
under this session's scratchpad, outside the repository. Nothing under `examples/` was read or
staged, **no database connection was opened**, no credential was entered, and no external service
was contacted. The two orphaned servers were **not** connected to and **not** killed.
