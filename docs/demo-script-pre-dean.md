# Pre-Dean Demo Script — Five Minutes

**Audience:** Dean, senior technical stakeholder.
**Build:** the merge of branch `feat/pre-dean-readiness`. Its merge SHA and image tag are not
assigned yet, so read the commit off `/krish/api/health` in the browser (checklist row 1) and say
*that* commit. The previous release was `f57e239` / image `v0.0.26`, which does **not** contain the
three features named below.
**Environment:** `https://isaac.slac.stanford.edu/krish` (Authentik edge). Locally, drop the `/krish`
prefix — the router applies the deployed base path itself and no link in the app writes it
(`apps/web/src/lib/routes.ts:26-52`).

The three items previously marked **PENDING VERIFICATION** all ship in this release and are described
here from the code, not from intent: visible **scenario labels** (step 2), the Assistant's
**What Can I Ask?** disclosure (step 10a), and **Copy Diagnostics** (step 16).

**Two things never to claim, at any step:** that the app can tell real data from synthetic (no such
detector exists anywhere in the codebase — `apps/web/src/lib/settingsContent.ts:25`), and that the
Graph shows current code (it is an index of commit `caab1d0a`, the `built_at_commit` of
`apps/api/isaac_api/data/memory-snapshot.json`).

---

## Timing

| Block | Steps | Target |
|---|---|---|
| The no-guessing core | 1-9 | 2:30 |
| Advisory layer, honestly bounded | 10, 10a, 11-13 | 1:30 |
| Integration surface | 14-16 | 1:00 |

If you are running long, cut step 15 (Endpoint Explorer) and the first half of step 12 (Project Memory
Overview); step 10a compresses to five seconds (open the panel, name the headings, close it). Never cut
step 4 (the five refusals), step 11 (the honest refusal), or step 13's disclosure.

---

## Step 1 — My Experiments

- **Route:** `/experiments`
- **Expected visible state:** Page title "My Experiments" with a derived subcount, records grouped by
  the state that says what to do next, and three actions: Reset Demo, Run Synthetic Demo, New Record.
  Five records.
- **Action:** Nothing yet. Let the grouping land.
- **Say:** "The queue is grouped by what the record needs next, and that grouping is derived from the
  record every time it is read — nothing about state is stored."
- **Fallback:** If you see "Backend Not Running" or an explicit sign-in message, reload once — an
  expired Authentik session renders as an auth state, not a false "backend down"
  (`downCopy`'s auth branch, `apps/web/src/components/FetchStates.tsx:94-113`). If the list is empty,
  click **Reset Demo**.
- **Do NOT claim:** a record count that is not on screen; that these are real experiments.

## Step 2 — The five scenario labels

- **Route:** `/experiments`
- **Expected visible state:** five rows whose scientific title is **identical** — every one reads
  `Synthetic XANES — CuO (Cu K-edge)`. Do **not** point at the title to tell them apart, and do not
  describe a title suffix here: the backend stores one, but the queue strips it before rendering a row
  (`KNOWN_TITLE_SUFFIXES` / `stripLifecycleSuffix`, `apps/web/src/lib/adapt.ts:61-72`) so the
  scientific title stays clean **on this screen** — it is *not* stripped everywhere, see the fallback
  note below. What distinguishes the rows on screen is the **scenario line** below the title, plus the
  Draft/Exported chip and the queue group heading.
- **Action:** Point at the scenario line on each row. The rows are ordered by queue group, **not** by
  scenario number, so top to bottom you will read 1, 2, 4, 3, 5 (`GROUP_ORDER`,
  `apps/web/src/lib/adapt.ts:48-53`). Read them in that on-screen order, not the table's.

| Scenario line (visible, below the title) | Derived status | Pending | Exported |
|---|---|---|---|
| `Scenario 1 · seeded: extraction only` | needs attention | 5 | no |
| `Scenario 2 · seeded: partial answers applied` | needs attention | 2 | no |
| `Scenario 3 · seeded: all answers applied` | ready to export | 0 | no |
| `Scenario 4 · seeded: descriptor uncertainty omitted` | in review | 0 | no |
| `Scenario 5 · seeded: export run at setup` | done | 0 | yes |

- **Say aloud:** "These five are the same experiment seeded into five different states. The line under
  the title says how each one was set up."
- **What NOT to claim:** the scenario line is **not** live status — it is a past-tense statement about
  how the fixture was materialised, and it deliberately does not change when you advance the record.
  The live state is the chip and the group. (Earlier present-tense wording — "Partially Confirmed" —
  was rejected precisely because it survived unchanged onto a fully-confirmed, exported record.)
- The label is derived from the record id and never stored (`workspace.py::scenario_label`, lines
  595-604 — `Experiment.to_state` writes no such field; served by `routes.py::_summary`, line 397). It
  is `null` for any record you create yourself, which renders nothing at all.

  (Ids `01SYNTHXANESSEED000000000{1..5}`, fixed — `apps/api/isaac_api/workspace.py:487-492`. Verified by
  materialising the seed and reading each record's derived state.)
- **Say:** "Five canonical synthetic records covering every state the workflow can be in. Each one is
  built from the same two committed synthetic fixtures through the real pipeline — including 'Export
  Review Required', which fails the official schema for a genuine reason: a descriptor was supplied
  without its required uncertainty."
- **Fallback — and there is no title-suffix fallback on this screen, so do not reach for one.** The
  backend does store a lifecycle suffix on each seed title (`· New Draft`, `· Partially Completed`,
  `· Ready to Export`, `· Export Review Required`, `· Exported Record` — `workspace.py:567-581`), but
  the frontend strips all five before a **queue row** is rendered (`KNOWN_TITLE_SUFFIXES` /
  `stripLifecycleSuffix` at `apps/web/src/lib/adapt.ts:61-72`, applied inside `toExperimentSummary` at
  line 93), so the suffix is not on `/experiments` and not on the Record Workbench heading either
  (`RecordWorkbench.tsx:205`).

  **It is not, however, hidden app-wide — do not say "never visible".** The `TopBar` heading on the
  three record sub-surfaces passes the raw title through unstripped, so the suffix *is* on screen on
  Complete (`GuidedCompletion.tsx:310`), Evidence (`EvidenceExplorer.tsx:135, 188`) and Export
  Readiness (`ExportReadiness.tsx:358`) — steps 4-6 and 8-9 all sit on those screens. The Assistant
  echoes it too (see step 10a), and ⌘K Search shows it as the owning-record context
  (`search.py:276-287`). If Dean notices it, the honest answer is: it is display text on a synthetic
  seed title, nothing reads it back, and the queue strips it so the scientific title stays clean.

  If a scenario line is missing, tell the rows apart from what is genuinely rendered:
  - the **queue-group heading** — Needs Attention (1, 2) · In Review (4) · Ready to Export (3) ·
    Done (5) (`apps/web/src/lib/labels.ts:123-126`);
  - the **`N Fields Need You` chip**, which appears only in Needs Attention and separates scenario 1
    (**5**) from scenario 2 (**2**) (`ExperimentRow.tsx:76-79`; `adapt.ts:76-84`);
  - the **Draft / Exported lifecycle chip** on every row, which is what marks scenario 5
    (`ExperimentRow.tsx:66-73`).

  In that case stop saying "Scenario N" aloud and name the state instead. A record you created yourself
  has no scenario at all and renders no line — that is by design, not a failure.
- **Do NOT claim:** that the states are hand-set or seeded as labels. They are derived
  (`workspace.py:400-412`).

## Step 3 — Open the five-confirmation scenario

- **Route:** click the **`Scenario 1 · seeded: extraction only`** row — first under **Needs
  Attention**, and the one showing `5 Fields Need You` → `/record/01SYNTHXANESSEED0000000001`
- **Expected visible state:** the Record Workbench: field groups, a workflow spine, and a progress
  banner naming the single next action. Steps ahead of the current one are locked and non-clickable.
- **Action:** Click the row. Do not type the URL.
- **Say:** "This is the raw extraction — five things the system refused to fill in."
- **Fallback:** if a sub-surface link looks dead, that is the gate, not a bug: blocked steps are
  deliberately non-navigable (`apps/web/src/components/WorkflowSpine.tsx:39-41, 115`). Use the banner's
  action instead.
- **Do NOT claim:** that you could skip ahead if you wanted to.

## Step 4 — ISAAC refusing to guess

- **Route:** the banner action, or the spine's current step → `/record/01SYNTHXANESSEED0000000001/complete`
- **Expected visible state:** "Complete Missing Fields" with five blockers, each phrased as a question:
  1. sha256 of `ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb`
  2. sha256 of `ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi`
  3. sha256 of `ssrl-archive://BL15-2/2099_run_000/raw/`
  4. the reduced spectrum, so `measurement.series` can be built
  5. at least one descriptor (e.g. XANES inflection-point energy + uncertainty)
- **Action:** Read the five out. Do not answer anything yet.
- **Say:** "Three file hashes, the reduced spectrum, and a descriptor. None of these are derivable from
  the campaign sheet, so the system leaves them missing and asks. That is the whole design claim: it
  would rather block an export than invent a hash."
- **Fallback:** if fewer than five appear, the record has been partially completed in a previous demo —
  go back and use **Reset Demo**, then re-enter.
- **Do NOT claim:** that the system knows what the correct answers are. It does not; it holds a
  *labelled synthetic* demo value for some blockers, which is a different thing.

## Step 5 — Confirm one synthetic value

- **Route:** same
- **Expected visible state:** on a blocker with a demo value, a suggestion block headed
  `Demo answer (synthetic)` followed by `— not a value until you confirm`, a **Use This Suggestion**
  (or **Use This Value**) button, and a **Confirm** button that is disabled until a value is staged
  (`apps/web/src/components/GuidedPrompt.tsx:87-104, 133-139`).
- **Action:** Click **Use This Suggestion**, then **Confirm**, on **one** blocker only — the
  notebook sha256 is the cleanest.
- **Say:** "The synthetic value is offered but it is not a value until a human confirms it. That
  confirmation is stored as evidence of type user-confirmation, with your action as the source."
- **Fallback:** if Confirm stays disabled, nothing is staged — click Use This Suggestion first. If the
  request fails on a revision conflict, reload the page; the record's ETag moved under you.
- **Do NOT claim:** that the assistant filled the field. It never prefills a scientific value
  (`GuidedPrompt.tsx:34-36`).

## Step 6 — Inspect Evidence

- **Route:** `/record/01SYNTHXANESSEED0000000001/evidence`
- **Expected visible state:** "Evidence & File Preview" — the evidence trail on the left/first, each
  entry showing its official path, value, support kind, and the source file plus locator; a source
  preview of the cited synthetic fixture with cited lines marked; and a per-field evidence-support
  classification.
- **Action:** Select one field extracted from the campaign sheet (e.g. a `system.facility.*` field) and
  read its locator aloud, then select the field you just confirmed and contrast the two.
- **Say:** "Every value traces to a source and a locator — a sheet cell, a file listing line, or a human
  confirmation. Pre-export this trail is read from the draft's own evidence envelopes; after export it
  is read from the evidence sidecar written beside the record."
- **Fallback:** if the source preview is empty for the selected field, its evidence cites a field rather
  than a line — expected, not an error. Pick a spreadsheet-sourced field instead.
- **Do NOT claim:** that the sidecar is an official ISAAC artifact. The screen itself says
  `sidecar · assistant convention, not an official ISAAC standard`
  (`apps/web/src/screens/EvidenceExplorer.tsx:213`). If Dean asks, the full audit is
  `docs/evidence-sidecar-audit.md`.

## Step 7 — The standalone Validator

- **Route:** `/governance?tab=validator` (left nav → Governance & Safety → Validator tab)
- **Expected visible state:** a paste area and an upload control, a 512 KB bound, and copy stating that
  the candidate is validated in memory and discarded.
- **Action:** Paste the record JSON from the exported scenario (step 9) or any small JSON, and validate.
  A deliberately broken record is the better demo: validate something missing a required field and show
  the structured errors.
- **Say:** "This is the same `validate_official` that backs the CLI and the per-record route — one
  implementation, one verdict path. Nothing is added to My Experiments and nothing is stored."
- **Fallback:** if the paste is rejected before any request, it exceeded 512 KB — the bound is enforced
  client-side first (`apps/web/src/components/RecordValidator.tsx:31`).
- **Do NOT claim:** that this is a second or "lighter" validator, or that it evaluates scientific
  plausibility. It checks the official schema and nothing else.

## Step 8 — Export Readiness

- **Route:** `/record/01SYNTHXANESSEED0000000003/export` — go via My Experiments → the **Ready to
  Export** group → `Scenario 3 · seeded: all answers applied`
- **Expected visible state:** the readiness panel with a `dry-run · would validate` note and the button
  **Export Official Record + Sidecar**. On the Scenario 1 record you would instead see
  "N fields still block export."
- **Action:** Read the readiness copy. Do not press Export yet.
- **Say:** "Readiness is derived, not asserted — zero pending fields plus a passing in-memory dry-run
  against the official schema. There is no override and no portal submission from here."
- **Fallback:** if the record shows blockers instead, you are on the wrong scenario — return to
  `/experiments` and choose the row under **Ready to Export** (`Scenario 3 · …`).
- **Do NOT claim:** that a passing dry-run is a verdict. The screen says "would validate", deliberately.

## Step 9 — Export, safely

Two options. **Prefer option A.**

**Option A (no mutation, recommended).** Open `/record/01SYNTHXANESSEED0000000005/export` — the
already-exported scenario.
- **Expected visible state:** two separate artifact cards — the official record (`schema-clean · ISAAC
  v1.05`) and the sidecar (`assistant convention — not official`) — with View and Download, plus
  "Review the sidecar before sharing" and a read-only note that content was loaded from the immutable
  files on disk.
- **Action:** Click **View** on each card in turn.
- **Say:** "Export writes two files: a schema-clean official record, and a sidecar that preserves the
  per-field provenance the official schema has no slot for. Records are written once and are immutable."

**Option B (real mutation).** On the **Ready to Export** row (Scenario 3), press **Export Official
Record + Sidecar**.
- **Expected visible state:** the button goes to "Exporting…", then the two artifact cards appear and
  the record's state becomes `done`.
- **Say:** the same line as Option A, plus "that ran the real gated export."
- **Fallback / cleanup:** exporting is a genuine state change and cannot be undone in-app — a second
  export is refused `409` (the immutability guard, `apps/api/isaac_api/routes.py:1206-1216`). Restore with **Reset Demo** on
  `/experiments`, which returns the workspace to exactly the five canonical scenarios, content included.
  If you have less than a minute left, use Option A.
- **Do NOT claim (either option):** that anything was submitted to the ISAAC portal. No submission path
  exists in this build.

## Step 10 — Ask the Assistant a supported question

- **Route:** the assistant rail on any record surface; use `/record/01SYNTHXANESSEED0000000001/complete`
- **Expected visible state:** a composer with placeholder `Ask a question`
  (`apps/web/src/components/AssistantPanel.tsx:1572`), a helper line beneath it, and a
  **What Can I Ask?** trigger below that (step 10a).
- **Action:** Type **`What still needs me?`** and submit.
- **Verified response** on that record (`pending_fields` intent, `result: answered`):
  > 5 fields still need you: ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb,
  > ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi,
  > ssrl-archive://BL15-2/2099_run_000/raw/, …and 2 more.
- **Stronger alternative** if you have time — on the **In Review** row
  (`Scenario 4 · seeded: descriptor uncertainty omitted`, `01SYNTHXANESSEED0000000004`) ask **`What's blocking export?`** (`export_blockers` intent):
  > 1 validation issue may be blocking export: descriptors → outputs → 0 → descriptors → 0. Open
  > Validator to reach the deterministic schema check.

  It arrives with a **Open Validator** button and a Technical Details disclosure carrying the exact
  locator `descriptors.outputs.0.descriptors.0`.
- **Say:** "The assistant is deterministic — a fixed catalog of eight question families matched by
  explicit phrases. No model, no generation. The answer is assembled from the record's own grounded
  surfaces, and it is verdict-guarded: it is not permitted to say a record passes or fails."
- **Fallback:** if the answer comes back ambiguous, it genuinely tied between two intents and says so —
  pick one of the offered readings. If it says the record's grounded surfaces could not answer, the
  dry-run was unavailable; that is an honest insufficient-context state, not a crash.
- **Do NOT claim:** that it understands the question, or that it can reason about new phrasings outside
  the catalog. Phrase matching, `assistant_query.py:237-277`.

## Step 10a — "What Can I Ask?" (30 seconds, and it sets up step 11)

- **Route:** same composer — stay on `/record/01SYNTHXANESSEED0000000001/complete`
- **Expected visible state:** a small **What Can I Ask?** button in the composer dock, below the composer
  input and its helper line. Activating it opens a compact non-modal popover *upward* over the composer
  (`role="dialog"`, dismissed by Escape, by a click outside it, or by **Close** — all three return focus
  to the trigger; on the narrow slide-over mount Escape closes the whole drawer, which is pre-existing
  `AssistantDrawer` behaviour, not a fault of this panel),
  listing the supported families as headings with one or two example questions each as buttons, and
  ending — outside the scroll region, so always visible — with the boundary line:
  > These families are the whole set. Wording is flexible within them; anything outside them is refused,
  > not guessed.

  On a record surface the six headings are **Workflow and Current Step · Missing Fields and
  Confirmations · Export Blockers and Readiness · Evidence and Provenance · Record Summary · Project
  Memory** — six headings covering all eight resolver intents
  (`RECORD_CAPABILITY_GROUPS`, `apps/web/src/lib/assistantCapabilities.ts`).
- **Action:** Make sure the composer is **empty first** (see the note below), open the panel, read the six
  headings, click **`Summarize this record.`** to show the text landing *in the composer* with nothing
  sent, then close the panel. Submit it if you have the time.
- **If you submit it, the answer quotes the STORED title, suffix and all.** Verified on
  `…SEED0000000001`: `This record 'Synthetic XANES — CuO (Cu K-edge) · New Draft' is currently needs
  attention, with 5 pending fields and 26 evidenced fields.` The `record_summary` resolver echoes
  `_summary`'s `title` verbatim (`apps/api/isaac_api/assistant_query.py:883-893`; `routes.py:388`) —
  the queue's suffix stripping is a frontend display step and does not reach the API. Do **not** say the
  suffix is never visible; if it comes up, say it is seed display text and nothing reads it back
  (see step 2).
- **Say:** "This is the catalog, in the product rather than in a document. Six families here, and the
  panel itself says that is the whole set — wording inside a family is flexible, anything outside it is
  refused. Clicking an example fills the composer; it does not send it."
- **One behaviour to know before you click:** inserting never overwrites a half-typed question. With text
  already in the composer the panel closes, focuses the input and leaves your draft exactly as typed —
  and it says so up front: while a draft is present the panel's note reads "Your unsent question stays in
  the composer. Clear it first to insert an example." (`insertCapabilityExample` in `AssistantPanel.tsx`;
  `CAPABILITIES_DRAFT_KEPT_NOTE` in `assistantCapabilities.ts`.) So clear the composer before this step,
  or the click will look like it did nothing.
- **The scoping is the interesting part, if Dean asks:** the list is chosen from what the *surface* can
  actually answer, not from a global list. On Project Memory (`queryScope="memory"`) only the Project
  Memory family is offered, because that surface routes to `assistant_query.py::answer_memory_scope`,
  which refuses every record family — advertising them there would advertise a refusal
  (`MEMORY_CAPABILITY_GROUPS` / `capabilityGroupsFor` in `assistantCapabilities.ts`). A **Graph
  Navigation** group appears only while the Graph tab is mounted, because that is the only time the graph
  interception is wired (`apps/web/src/screens/ProjectMemory.tsx:159-172`).
- **Fallback:** if the panel does not open, skip it — the same eight families are named verbatim in the
  refusal you are about to trigger in step 11, so the point still lands.
- **Do NOT claim:** that the panel lists everything the app can do, or that these are the only accepted
  phrasings — each family holds several trigger phrases. And do not claim an example was answered if you
  only inserted it.

## Step 11 — Ask the Assistant an unsupported question

- **Route:** same composer
- **Action:** Type **`Is this sample scientifically plausible?`** and submit.
- **Verified response** (`result: unsupported`, verbatim):
  > That question isn't something I can answer from this record's grounded surfaces. I can help with:
  > pending fields, export blockers, export readiness, the workflow step, field provenance, evidence for
  > a field, a record summary, or project-memory leads. Try: "What still needs me?"
- **Say:** "This is the behaviour I most want reviewed. It refuses, and it tells you exactly what it can
  do instead — the same catalog you just opened, spelled out as its eight intents. It does not attempt
  scientific judgement, and it does not improvise."
- **Fallback:** if a question you expected to be refused is instead answered, it collided with a trigger
  phrase — try this exact wording, which is verified to refuse. Other verified refusals:
  `Should we publish this result in a paper?`, `Who should I email about beamtime?`,
  `What was the beam current at SSRL last Tuesday?`.
- **Do NOT claim:** that it refuses *everything* outside the catalog with perfect precision. It matches
  phrases; an unusual phrasing containing a trigger word will route.

## Step 12 — Project Memory, and its advisory boundary

- **Route:** left nav → Project Memory → `/memory` (Overview tab)
- **Expected visible state:** memory health/status figures, and the standing line "Project memory
  returns leads to verify — never a validation verdict."
- **Action:** In the rail composer ask **`What does project memory know about the evidence sidecar?`**
- **Verified response** (`memory_lead` intent, `result: answered`):
  > Memory suggests 2 leads to verify: Evidence sidecar (records/<ULID>.evidence.json),
  > src/isaac_records/export.py. Memory suggests leads to verify; the current record shows its own
  > confirmed values. Project memory returns leads to verify — never a validation verdict.

  with two navigable source chips (a concept and a file).
- **Then** ask **`What's blocking export?`** here, to show the scope boundary. Verified response
  (`result: unsupported`):
  > This is the Project Memory view — I answer project-memory questions here. Open a record to ask
  > about its fields, evidence, workflow, or export readiness.
- **Say:** "Memory is a separate plane. It can point you at a document, a concept, or a file, and it
  cannot validate anything, complete a field, or authorise an export. If memory and the schema disagree,
  the schema wins."
- **Fallback:** if memory reports unavailable, the served snapshot did not load — say so plainly and
  move on; the response is an honest `available: false` envelope with zero fabricated nodes
  (`apps/api/isaac_api/memory_graph.py:384-386`).
- **Do NOT claim:** that memory is searching the live repository. It serves a committed snapshot.

## Step 13 — The Graph, only with its disclosure

- **Route:** `/memory?tab=graph`
- **Expected visible state:** the projection plus the visible subtitle "This graph shows project-file
  relationships and navigation leads. It does not represent scientific truth or causality."
- **Action — do this first, before discussing the graph at all:** click **About This Graph** and read
  the boundary statement. It names the source commit and states the two-axes rule
  (`apps/web/src/screens/graph/GraphHelp.tsx:196-210`).
- **Say:** "Two things before anyone reads this as a code map. It is advisory — leads, never verdicts.
  And its structure is a point-in-time index of commit `caab1d0a`, not of current main, so anything
  added or renamed since then is simply absent, including work in this running build. Content
  freshness is a separate check and a current content check does not make the structure current."
- **Content, if you continue:** the projection is 220 nodes (201 served files + 19 concepts) and 508
  reference edges; zooming in reveals a symbol-level layer of 2,612 nodes / 4,067 edges, which carries
  its own on-surface staleness paragraph (`apps/web/src/screens/graph/GraphCanvas.tsx:882-887`).
- **Fallback — and prefer it if the graph would mislead:** skip the canvas and use **Project Memory →
  Overview / Concepts / Sources** instead. Those answer "what does the project know about X" without
  implying a current architecture map. Take this route if Dean starts asking where a specific new file
  is — it will not be there.
- **Do NOT claim:** that this is a current code map; that a node's absence means the code does not
  exist; or that the cluster labels are authoritative.

## Step 14 — API Access, and the unavailable per-user keys

- **Route:** `/settings?tab=api`
- **Expected visible state:** a status banner reading **"API Key Management Is Not Available in This
  Synthetic Preview"**, a "How Access Works Today" column, a genuinely `disabled` **Create API Key**
  button with its always-visible reason, and an empty "Your API Keys" state stating it is empty by
  design, not by circumstance (`apps/web/src/screens/settings/ApiKeys.tsx:96-171`;
  `apps/web/src/lib/settingsContent.ts:282-312, 319-340`).
- **Action:** Read the banner, then the "Current Access Model" row.
- **Say:** "There is one credential belonging to the whole deployment, set on the server before the app
  starts. It identifies the deployment, not a person. There is no operation anywhere in this API that
  creates, lists, revokes, or rotates a credential — so rather than stub a key screen, the screen says
  what is missing and what would have to exist first. That is question 7 on my list for you."
- **Fallback:** if Dean asks to see a key, there is nothing to show and that is the point — open the
  Technical Requirements disclosure, which lists the contracts a real key system would need.
- **Do NOT claim:** that the screen can tell whether deployment auth is switched on. It explicitly
  cannot (`settingsContent.ts:323`, and the same caveat at 202, 204).

## Step 15 — Endpoint Explorer

- **Route:** `/settings?tab=explorer` (or the **Endpoint Explorer** button on the API Access banner)
- **Expected visible state:** a master-detail browser over the generated OpenAPI document — every
  operation, whether it documents a 401, parameters, request body, responses, error states, generated
  code samples, and raw JSON behind a disclosure.
- **Action:** Open one operation — `POST /api/experiments/{experiment_id}/export` is the best one — and
  show its description and its 409.
- **Say:** "This is generated from the running contract, not hand-written, so it cannot drift from the
  API. Paths are shown relative to whatever origin serves the page; no hostname is ever displayed."
- **Fallback:** if the contract fails to load, say so; do not describe operations from memory.
- **Do NOT claim:** an operation exists because it seems like it should. The Explorer is the inventory.

## Step 16 — Copy Diagnostics

- **Route:** `/settings?tab=about` — Settings → **About** (tab id `about`;
  `apps/web/src/lib/routes.ts:18`, `SettingsPage.tsx:90`). **Not** Overview.
- **Expected visible state:** the About card — Identity figures (App Version, Build Commit *short*,
  ISAAC Record Schema, Core), an Authority section, a collapsed **Technical Details** disclosure, and
  then, just **below** Technical Details and not inside it, a **Copy Diagnostics** button with the note
  "Copies this build's version, route, viewport and Project Memory provenance as text you can paste into
  a bug report. Nothing is uploaded." (`SettingsPage.tsx:573-576` → `FetchStates.tsx:389-414`; the note itself at `FetchStates.tsx:353-356`).
- **Action:** Click it. The button's own label changes to **Diagnostics Copied**. Paste it into whatever
  you would paste a bug report into — check it before showing it on a projector.
- **Say:** "One click produces the exact build and configuration any observation was made against, as a
  fenced text block that survives a paste into GitHub or Slack. It performs no request and uploads
  nothing — a test asserts `fetch` is never called."
- **What is in it — four groups, one generator:**
  - `BUILD` — App Version, Build Commit (short **and** full), Runtime Mode, Data Regime, Persistence,
    Record Schema, Deployment, API Base
  - `SESSION` — Generated At, Route, Tab, Record Id, Browser, Viewport, Device Pixel Ratio, Network State
  - `PROJECT MEMORY` — Availability, Integrity, Provider, Source Commit, Snapshot Fingerprint, Policy
    Fingerprint, Served File Count, Snapshot Schema
  - `FAILURE SIGNALS` — **only** on the error mount (below), never on About

  All four come from one pure generator, `apps/web/src/lib/diagnostics.ts::buildDiagnosticsReport`
  (groups at lines 330-407), which takes every value as an argument and reads no global — so what it can
  and cannot emit is a property of a function, not of a component.
- **The second mount, worth 10 seconds if a failure state is on screen anyway:** the same control over
  the same generator sits inside the existing **Technical Details** box of the error state
  (`FetchStates.tsx:229-239`), where it additionally carries `FAILURE SIGNALS` (HTTP status, network-level
  failure, HTML intercept, response content-type, request path) and *omits* the server-derived BUILD and
  PROJECT MEMORY values — because the request that failed is the evidence they are not available, so
  those rows read `not available` rather than a stale value.
- **Two deliberate absences, if Dean asks:**
  - **No zoom field.** `devicePixelRatio` cannot tell a Retina display at 100% from a 1× display at
    200%, and `visualViewport.scale` tracks pinch only. Rather than report a plausible-looking guess, the
    raw `Device Pixel Ratio` is reported under its own honest name (`diagnostics.ts:38-44`).
  - **One `Source Commit`, not two.** `apps/api/isaac_api/memory.py:1055` sets `source_graph_commit` to
    the snapshot's `built_at_commit`, so a separate "memory commit" and "graph commit" would be two
    labels over one value.
- **Privacy, if asked:** no cookie, token, `Authorization` or `x-api-key` header, storage content,
  `VITE_API_KEY`, Assistant transcript or user-entered value can appear — nothing is *read*, everything
  arrives as a typed argument. `DiagnosticsFailure` deliberately has no `body` field, so a failing
  response's body is excluded by the type rather than by a runtime filter (`diagnostics.ts:18-36,
  115-125`).
- **Fallback:** if the clipboard is unavailable the report is rendered below the button as focused,
  pre-selected, selectable text with a stated reason — that *is* the designed path, not a failure, so
  read it from there. If the About tab itself cannot load `/api/about` the panel does not render at all;
  in that case read App Version / Build Commit / Runtime Mode / Data Regime / Persistence off
  `/settings?tab=overview` (Runtime Status — `SettingsPage.tsx:330-341`, sourced from
  `apps/api/isaac_api/routes.py:2863-2871`) and say you are reading them off the page.
- **Do NOT claim:** that anything was uploaded or reported anywhere; that the report includes browser
  zoom; or that the memory rows are missing because something is broken — an unavailable
  `GET /api/graph/status` legitimately renders `not available` and every build fact still appears. And
  read the pasted block before putting it on a shared screen.

## Closing line (15 seconds)

"Deterministic core, advisory everything else, and it refuses rather than guesses. What I need from you
is the governance and integration decisions — the sixteen questions in the brief, starting with the
sidecar and the real-data ingress path."

---

# Pre-Demo Checklist

Run this **immediately before** the meeting, in the deployed environment, signed in. Anything that
fails becomes a thing you do not demo — not a thing you improvise around.

| # | Check | Pass condition | If it fails |
|---|---|---|---|
| 1 | **Hosted health SHA** | `/krish/api/health` returns a `commit` you can read. It must be the merge of `feat/pre-dean-readiness` — the SHA and image tag are not assigned yet, and the previous release (`v0.0.26` → `f57e239`) does **not** contain steps 2, 10a or 16. Not verifiable from a dev shell — read it in the browser while signed in. | Demo whatever commit it actually reports, and say that commit. If it is still `f57e239`, cut steps 2's scenario line, 10a and 16 and use their fallbacks. Never state an unobserved SHA. |
| 2 | **Runtime mode** | `/settings?tab=overview` shows Runtime Mode `synthetic-only`, Data Regime `synthetic-only`, Persistence `ephemeral`. | Stop. A different mode means the app should not have booted (`runtime_mode.py:83-88`). |
| 3 | **Five canonical records present** | `/experiments` lists exactly five, ids `01SYNTHXANESSEED000000000{1..5}`. | Click **Reset Demo**, then re-check. |
| 4 | **Scenario labels visible** | All five rows show a `Scenario N · seeded: …` secondary line under the identical scientific title (`ExperimentRow.tsx:55-65`, from `GET /api/experiments` → `scenario`). Note the on-screen order is by queue group, **not** 1-5: Needs Attention (1, 2) → In Review (4) → Ready to Export (3) → Done (5) (`adapt.ts:48-53`). | There is **no title-suffix fallback on this screen**: the frontend strips all five suffixes before a queue row is rendered (`adapt.ts:61-72`, applied inside `toExperimentSummary` at line 93), so they are not on `/experiments`. (They are *not* hidden everywhere — the Complete / Evidence / Export headings and the Assistant's record summary both show them; see step 2. Never claim they are never visible.) Tell the rows apart by the group heading, the `N Fields Need You` chip (5 vs 2 separates scenarios 1 and 2) and the Draft/Exported chip (scenario 5) — and stop saying "Scenario N" aloud. |
| 5 | **Demo idempotence** | On `/experiments` the **Run Synthetic Demo** button navigates to `/load`; the run itself is the "Run the Synthetic Demo" panel there (`POST /api/demo/run`, `apps/web/src/screens/LoadMaterials.tsx:33-47, 83`). Run it twice: the list stays at **five** records — the canonical ids are upserted in place, never appended. Verified: 5 → 5 → 5, target id `01SYNTHXANESSEED0000000001` both times. | If a sixth appears, do not run the demo during the meeting; use Reset Demo. **Note either way:** a demo run rewrites scenario 1 to its baseline, so it will discard the confirmation you make in step 5. Do not run it mid-demo. |
| 6 | **No console errors** | DevTools console clean on `/experiments`, one record surface, `/memory?tab=graph`, `/settings?tab=explorer`. | Note which surface is noisy and avoid opening DevTools there. |
| 7 | **Assistant composer reachable** | Composer with placeholder `Ask a question` present on the record surfaces and on `/memory`. | Skip steps 10, 10a and 11-12; do not describe answers you have not seen. |
| 8 | **Supported question answers** | `What still needs me?` on `…0001` returns the five-field answer. | Try `Summarize this record.`; if the rail is broken, cut step 10. |
| 9 | **Unsupported question refuses** | `Is this sample scientifically plausible?` returns the `unsupported` refusal naming the eight families. | Use one of the alternates in step 11. |
| 9a | **What Can I Ask? panel** | On a record surface the composer dock shows **What Can I Ask?**; opening it lists the six headings (Workflow and Current Step · Missing Fields and Confirmations · Export Blockers and Readiness · Evidence and Provenance · Record Summary · Project Memory) and the boundary line "…anything outside them is refused, not guessed." With the composer **empty**, clicking `Summarize this record.` puts that text in the composer **without sending it**; with a draft already typed the panel deliberately keeps the draft and says so. Escape closes it. On `/memory` only the **Project Memory** heading appears; a **Graph Navigation** heading appears there only on the Graph tab. | Cut step 10a. The eight families are still named verbatim in step 11's refusal, so the bounded-catalog point survives. |
| 10 | **Open Validator works** | The **Open Validator** button on an `export_blockers` answer lands on `/governance?tab=validator` with the Validator tab genuinely selected. | Navigate to the tab manually; do not click a control you have not tested. |
| 11 | **Browser Back behaves** | Back from a record sub-surface returns to the record, and from `/memory?tab=graph` does not strand you on a blank canvas. In-page tab switches deliberately do **not** create history stops. | Navigate with the left nav only. |
| 12 | **Evidence page** | `/record/…0001/evidence` renders the trail, a source preview with cited lines, and the sidecar convention note. | Cut step 6. |
| 13 | **Export Readiness** | `…0003` shows `dry-run · would validate` and an enabled Export button; `…0001` shows "5 fields still block export". | Cut step 8; demo only the exported artifacts (step 9 Option A). |
| 14 | **Exported artifacts readable** | `/record/…0005/export` shows both artifact cards and both View dialogs open with real JSON. | Do not use step 9 Option B as a substitute under time pressure — it mutates state. |
| 15 | **Project Memory provenance** | `/memory` Overview loads, and the memory question returns leads with the "leads to verify — never a validation verdict" line. | Cut step 12's first half; keep the scope-refusal half if the composer works. |
| 16 | **Graph point-in-time disclosure** | **About This Graph** opens and names commit `caab1d0` in the boundary statement. | **Do not show the graph at all.** Use Project Memory Overview/Concepts/Sources. |
| 17 | **API Access** | `/settings?tab=api` shows the "not available" banner, the disabled Create button with its visible reason, and the empty key list. | Cut step 14. |
| 18 | **Endpoint Explorer** | `/settings?tab=explorer` loads the contract and one operation's detail opens. | Cut step 15; do not describe operations from memory. |
| 19 | **Copy Diagnostics** | `/settings?tab=about` — the **About** tab, **not** Overview — shows **Copy Diagnostics** just below the collapsed Technical Details. Click it, paste the result somewhere private, and read it: the `BUILD`, `SESSION` and `PROJECT MEMORY` groups are populated (`not available` in a memory row is acceptable), `Build Commit (Full)` matches check 1, and there is no hostname, token, cookie or absolute server path anywhere in the block. | If the clipboard is blocked the report appears below the button as selectable text — that is the designed path, use it. If About cannot load app info at all, read App Version / Build Commit / Runtime Mode / Data Regime / Persistence off `/settings?tab=overview` and say you are reading them off the page. |
| 20 | **Narrow-width spot check** | At ~700 px wide: no horizontal page scroll; wide content (tables, JSON blocks, the graph) scrolls inside its own container; the assistant rail reflows rather than clipping. | Demo at full width only and say the responsive sign-off is still open. |
| 21 | **200% zoom spot check** | At 200% browser zoom: no content lost or overlapping on `/experiments`, one record surface, and `/settings?tab=api`. | Same — demo at 100% and state that the zoom sign-off is an open item. |

Checks 20 and 21 are the outstanding human visual sign-off gate. They have not been signed off; if Dean
asks about accessibility, say that plainly rather than implying they passed.
