# Owner hosted-QA issue inventory — 2026-09-22

**Source.** Krish's written QA of the hosted build (`Build Commit: 0a12f7ae9010…`, schema v1.05,
`synthetic-only`, `durable`) in the 2026-09-22 master prompt. **The screenshots named in that
prompt did not arrive with the message** — only its text did — so every item below was REPRODUCED
LOCALLY from `main` at `0a12f7ae` (vite 5173 + uvicorn 8000, fresh `ISAAC_UI_WORKSPACE`, a record
created through `POST /api/experiments`, one run, one finalized transcript minting 2 proposals and
3 notes) and screenshotted at 1440px in a real headless Chromium. Local screenshots are NOT
committed (global rule: no local screenshots in git); they lived in the session scratchpad.

**Outcome:** every row below was addressed by PRs #277, #278 and #279 — see
[`docs/session-closure-2026-09-22.md`](../session-closure-2026-09-22.md) ("Owner complaint → outcome").

Each row: route · component(s) · observed · acceptance criterion.

**HOSTED CONFIRMATION (added the same session).** The owner then signed into Chrome for the agent,
so the hosted build was also observed **read-only** (no write, no credential entered): `/krish/api/health`
reports `commit: 0a12f7ae901069a8…`, `mcp.posture: "unmounted"`, `submission.blockers:
["no_attributable_actor"]`, `verifier_id: "unconfigured"`, run projection `unavailable: 3`. The
owner's QA experiment ("Test", 1 run, 1 open proposal, updated 2026-09-22T18:02Z) shows the same
Capture and Runs layouts as local — **with one difference that matters: the owner runs with the
Assistant rail EXPANDED** (`isaac.assistant-rail-collapsed=0`). At a 1510 px window that leaves
`main` 955 px, the Runs pane 543 px and the Record Map 340 px, and the Runs toolbar wraps onto
three rows. N4 is confirmed on hosted: title `Record Fields · ISAAC Metadata Assistant` and 5
permanent `.spine-step.skeleton` rows on a nonexistent record id.

## Navigation / workflow

| ID | Route | Component | Observed on `0a12f7ae` | Acceptance |
|---|---|---|---|---|
| **N1** | every `/record/:id…` | `WorkflowSpine.tsx` | `Complete Metadata` renders blue/pencil (`state=current`) while the reader is on Runs, Experiment Data, Activity **and even on `/export`**, where the page shown is `Review Export Readiness` (itself drawn locked). Completion state and current location are one visual. | Two independent signals per row: **state** (icon + word: Complete / Current requirement / Locked / Needs review / Ready) and **location** (persistent selected-page background, `aria-current="page"` on the row whose destination is displayed). Hover distinct from selected. |
| **N2** | `/record/:id` | `RecordWorkspaceNav.tsx` | `WORKSPACES → Record Fields` duplicates the destination `Record Created`/`Complete Metadata` already reach. | `Record Fields` removed from workspace navigation; the fields editor stays reachable through the workflow step (and its deep link keeps resolving). |
| **N3** | `/record/:id` | `RecordWorkspaceNav.tsx` | `DATA CAPTURE` group = an `Experiment Data` card + `Runs`. | A coherent **Capture** section: `Capture` (home/choose method) and `Runs` beneath it; `WORKFLOW` (5 steps); `WORKSPACES` = `Activity`, `Evidence Trail`. |
| **N4** | `/record/<missing>` | `RecordWorkbench.tsx` / `documentTitle.ts` | Title `Record Fields · ISAAC…` for a record that does not exist; skeleton spine stays forever beside a settled "Record Not Found". | Title names the not-found state; spine skeleton replaced by a settled state (or omitted) once absence is known. |

## Capture

| ID | Route | Component | Observed | Acceptance |
|---|---|---|---|---|
| **C1** | `?view=capture` | `CaptureIntake.tsx` + `RecordWorkbench` | Four method cards, then `Unmapped Notes` (with its own "Capture a note" form) and `Ingestion Proposals` all inline: **1795 px** tall empty, **3028 px** with 2 proposals. | Capture Home = four method choices only (+ compact counts/links to review). Each method opens a **focused task view** (routes/subviews, experiment context preserved). |
| **C2** | Capture → `Start Writing` | `TranscriptCapturePanel.tsx` | Expands inline **beneath** the cards: a "Before you start" essay, the whole Voice Capture block, retention prose, run picker, textarea, then Unmapped Notes and every proposal: **4297 px**. | Focused Write view: choose Run → type/paste → Finalize and Read → compact result (`N notes stored · M proposals ready for review` + `[Review Proposals] [Capture Another Note]`). Backend semantics unchanged. |
| **C3** | Capture → `Open Recorder` | `TranscriptCapturePanel.tsx` | Opens **the same inline panel** as Start Writing (identical screenshot). The recorder is presented as the primary voice path although audio can never become text in this deployment. | Voice view is primarily a **Claude/MCP** workspace, runtime-aware from `/api/health` `mcp.posture` (`unmounted` → "not enabled yet" + route to Connect Your Agent; `remote-ready`/`oauth-mounted` → "ready for a Claude connector" + 2–4 steps + copyable starter instruction; never "Connected" unless verifiable). Local recorder retained as a **secondary** disclosure ("Record locally instead") with all existing guarantees. |
| **C4** | Capture → `Bring Files` | `CaptureIntake.tsx` | Card links out to Historical Import. | Focused Files bridge view: short explanation + route to Historical Import + asset references entry, with the Record Map. |
| **C5** | all capture views | — | No live view of what the record now knows. | Split view: task left, sticky **Record Map** right (stacks at narrow widths). |

## Runs / Record Map

| ID | Route | Component | Observed | Acceptance |
|---|---|---|---|---|
| **R1** | `?view=runs` | `RunsSection.tsx` | Search / Overrides / Export filters misaligned (search input and two selects on different baselines; help text under search pushes it down); row shows `#1`, italics, "0 of 5 run fields on this screen". | Aligned toolbar; clean row hierarchy (label · state · count · Compare); clear selected Run. Keep filtering + Compare. |
| **R2** | `?view=runs&run=…` | `RunCard.tsx` | Every input carries its raw path (`context.environment`, `context.temperature_K`…) and UTC paragraphs; "Values this run inherits" is three paragraphs. | Human labels; technical path + definition behind an accessible `?`; inheritance summarised in one line with detail on demand. |
| **R3** | Runs right pane | `RunSchemaMirror.tsx` | Raw path under every row; SHARED BY THE RECORD rows are lowercase implementation names (`sample`, `system`, `attribution`, `links`, `assets`, `tags`) with the path repeated; pane has a fixed height and **clips "Show full official schema" mid-glyph** at its bottom edge. | Human labels (Sample, System & Instrument, Attribution, Relationships, Asset References, Tags); state primitive per row with current value where honestly held; path behind `?`; no clipped content. `Not Shown Here` kept (DEC-29) but worded/styled as a neutral state. |
| **R4** | Runs | `ValidateReview.tsx` | "What this checks" is an 11px triangle link; the empty state is two sentences. | Clear disclosure affordance; blockers-first once run (see V1). |

## Record Fields / Complete Metadata

| ID | Route | Component | Observed | Acceptance |
|---|---|---|---|---|
| **F1** | `/record/:id` | `FieldGroup.tsx` | `System & Instrument  system`, `Timestamps  timestamps`, `Sample  sample`, `Environment & Context  context`, `Extended Context  level 4`, `Experiment Name  name`, `Folder folder`, `Record Description record-level`, `Record Info record`, `Relationships links`, `Asset References assets`. | Human heading only; technical object in `?`/advanced. |
| **F2** | `/record/:id` | `FieldGroup.tsx` | Right-side prose tails: `13 fields · none recorded yet`, `What this experiment is called`, `written into the official record at export`. | Structured count badge + state primitive (`[7 fields] ○ Missing` / `✓ Complete` / `! 3 remaining`), never inventing completion when nested fields differ. |
| **F3** | `/record/:id` | `ExtendedContextPanel.tsx` | Empty state expands to a 3-line paragraph flush against the card edge (no padding). | `Extended Context · 0 entries · No additional imported context.` + `?`. |
| **F4** | all | disclosures | Tiny chevron/triangle is the only affordance on accordions (`FieldGroup`, "What this checks", "Show full official schema", "Enter or paste ISO 8601 text"). | Whole-row interactive target with hover, focus-visible, expanded state; keyboard + touch; reduced-motion respected. |

## Proposals / acceptance

| ID | Route | Component | Observed | Acceptance |
|---|---|---|---|---|
| **P1** | Capture | `IngestionProposalsPanel.tsx` | Each card: state chip, raw path, "On run Run 1", timestamp, "A suggestion about this field…", Proposed value, full rule paragraph, note id, quote, "As of this read…", Show What the Record Holds Now, Accept/Reject/More Actions, "Leaving this proposal alone…", Show history. ~290 px per card of mostly prose. | `[Awaiting Review] Temperature · Run 1` / **425 K** / quote + source / `[Accept] [Edit] [Reject]` / `Why this was proposed ?`. Provenance preserved behind disclosure. |
| **P2** | Capture → Accept | `IngestionProposalsPanel.tsx` | Clicking `Accept as Proposed` produces a full-width paragraph card ("Accepting writes a scientific value… NOTHING WAS WRITTEN…"). The failure was knowable before the click: `/api/health` reports `submission.verifier_id: unconfigured`, `blockers: [no_attributable_actor]`. | Preflight capability → compact `🔒 Acceptance unavailable on this deployment · Trusted scientist identity has not been enabled yet · [Why?] [Reload]`; Accept locked when success is known impossible; `409 human_actor_required` unchanged and still handled if reached. |
| **P3** | Capture | `UnmappedNotesPanel.tsx` | Full notes manager (filter, capture form, per-note 5-button row, suggested-field prose) inline under Capture. | Moved to a focused review surface; Capture shows counts + link. |

## Validation / export readiness

| ID | Route | Component | Observed | Acceptance |
|---|---|---|---|---|
| **V1** | Runs, `/export` | `ValidateReview.tsx`, `ExportReadiness.tsx`, `RunFindingList.tsx` | Findings shown as `$ — 'descriptors' is a required property` beneath two paragraphs; advisories repeated twice on `/export`; submission history is four prose cards. | Top verdict `Run 1 · × 1 blocker · ! 2 advisories`; blockers first with field name + `Go to Field`; schema detail / advisories / submission detail behind disclosures. Validation truth unchanged. |

## Historical Import

| ID | Route | Component | Observed | Acceptance |
|---|---|---|---|---|
| **H1** | `/imports` → Open session | `HistoricalImport.tsx`, `ImportCorpusReview.tsx` | Empty landing is calm. **An opened session is a flat dump:** the synthetic BL15 mini-corpus (`bl15_synthetic_mini_corpus`, 14 files, 5 measurements, **101 candidates**) renders a **43,994 px** page at 1440px; the two-fixture session 3,940 px. Every candidate carries a raw path heading (`measurement.series[].independent_variables[].values`), "No value was chosen", a multi-paragraph normalization rule (`bl15.filenames.bare_integer_ordinal.v1: THE ONLY ORDERING RULE…`) and a refusal paragraph; internal tokens leak (`Unresolved — sources_disagree`, `Reconstructed by deterministic_fake`); every stage's explanatory prose (Sources, What Was Read, Candidates, Add to Experiments) is visible at once. Agreement vs conflict is carried in prose and a single amber box. | Focused stage flow (Source Bundle → What ISAAC Read → Runs/Candidates → Conflicts → Review → Add to Experiment), summary counts first, shared semantic statuses (`✓ Sources Agree`, `× Sources Conflict`, `○ Unmapped`, `! Needs Review`, `✓ Ready`), conflicts shown source-by-source with "No value has been selected." |
