# ISAAC UX / Information-Architecture Plan — Scope V2

**Status:** **APPROVED — IMPLEMENTATION AUTHORIZED 2026-09-12.**
**Created:** 2026-09-12 · **Measured against:** `main` @ `2f9a1133`, local dev stack
(API `127.0.0.1:8000`, Vite `127.0.0.1:5173`), and the authenticated hosted deployment.
**Parent:** [`2026-09-12-isaac-product-scope-v2.md`](2026-09-12-isaac-product-scope-v2.md)

---

> ## STATUS CHANGED 2026-09-12 — IMPLEMENTATION AUTHORIZED
> Krish approved moving from planning into implementation. The planning gate is **CLEARED**.
> Every external-owner, security, migration and data-governance boundary in this document is
> **UNCHANGED**. Decision statuses are reconciled in
> [`ISAAC_PRODUCT_DECISIONS.md`](ISAAC_PRODUCT_DECISIONS.md) — read that first where it disagrees
> with prose written before the gate cleared. Source: `2026-09-12-plan-review-and-revisions.md`.


## Part 0 — Provenance of this critique

> ### ⚠️ DEGRADED: single-context (owner-imposed five-agent ceiling already consumed)
>
> Impeccable's `critique` command requires Assessment A (design review) and Assessment B
> (detector + browser evidence) to run as **two isolated sub-agents**. They did not. The project
> owner set a hard ceiling of five sub-agents for this planning run and all five were already
> dispatched on the parallel investigation workstreams before the critique began. Per the command's
> own rule, a degraded run must be bannered rather than passed off as a dual-agent run, so it is
> bannered here. The consequence is real and should be weighed: Assessment A's judgment was not
> isolated from browser evidence, so the design review and the measurements anchored each other.

**Impeccable availability — confirmed, with one part non-functional.**

| Component | Status | How established |
|---|---|---|
| Skill + playbooks | **AVAILABLE** at `~/.claude-slac/skills/impeccable` | `critique.md` (806 lines), `operate.md`, `shape.md` etc. read and applied |
| Session context (`context.mjs`) | **RAN** | reported `NO_PRODUCT_MD` / `NO DESIGN.md`; per its own routing, a scoped Evaluate command proceeds on the code as visual authority |
| **Mechanical detector (`detect.mjs`)** | **NON-FUNCTIONAL FOR THIS CODEBASE — AND NOT BECAUSE OF THE DEPENDENCIES.** See the finding below; this is now repaired for `.html` and **structurally unfixable for `.tsx`**. | **negative control**: fed a `.tsx` file containing an unlabelled `<img>`, a clickable `<div>` with no role, 8px text, and an `<a>` nested inside a `<button>`; it returned no findings and **exit 0**, with **empty stderr**. |

> ### THE DETECTOR CANNOT MEANINGFULLY SCAN THIS APPLICATION, AND THE REASON IS NOT MISSING PACKAGES
>
> A dedicated repair pass (2026-09-12) fixed the dependency failure and then measured that **the fix
> changes nothing for ISAAC.** Both halves matter:
>
> **What was repaired.** The four unresolvable imports (`htmlparser2`, `css-select`, `css-tree`,
> `domutils` — traced to a single `Promise.all` at
> `detector/engines/static-html/detect-html.mjs:127-135`, and that list is complete) were installed
> into a **sidecar** and injected with Node's `module.register()` + a `resolve` hook. Nothing in the
> skill install or this repository was modified. `NODE_PATH` and running with cwd inside the sidecar
> were both **tested and do not work** — ESM ignores them. Negative control after the repair: a bad
> `.html` fixture now returns **exit 2** with two findings; a clean fixture returns **exit 0**. The
> recipe is durable in the scratchpad (`impeccable-detector/RECIPE.md`), Node here is **v24.15.0**,
> and the skill pins no versions (no `package.json` anywhere in it).
>
> **Why that does not help ISAAC.** Those four packages gate `detectHtml`, which runs **only** for
> `.html`/`.htm`. A `.tsx`/`.jsx` file is routed unconditionally to a **separate regex engine that
> never imports them** — verified by re-running the identical bad `.tsx` fixture *with* the sidecar
> loaded: still **exit 0, zero findings, byte-identical**. That regex engine has **no ARIA or
> accessibility ruleset at all** — no missing-alt check, no clickable-`div`-role check, no
> nested-interactive check — and even its copy rules (`em-dash-overuse`, `marketing-buzzword`) fire
> only for `.html`/`.astro`/`.vue`/`.svelte`.
>
> **ISAAC's UI is entirely `.tsx`.** So a mechanical `detect.mjs` scan of this application is
> **structurally incapable** of reporting the defect classes it is usually cited for, repaired or
> not. Every historical *"Impeccable: 0 findings"* claim in this repository's history was a
> non-answer for **two** reasons, not one — and the second reason survives the fix.
>
> **Consequence for Assessment B, stated so it is not re-derived:** for a `.tsx` codebase,
> mechanical evidence must come from the **in-browser overlay** (a different code path, which does
> work) plus live-browser measurement. `detect.mjs` is the right tool for `.html` output and the
> wrong tool here. One nuance worth keeping: on `.html` input the un-repaired detector *does* print
> a one-time `DEGRADED — HTML parser modules unavailable` line to **stderr**, so a caller checking
> only stdout or the exit code would miss it — which is presumably how this went unnoticed.


**Assessment B therefore rests on live-browser measurement, not on the detector.** Every number
below was measured in a real Chrome session this session. **No "0 findings" claim is made from the
detector, and none should be believed from any prior session that did not run this same negative
control.**

**Two measurement traps that shaped how these numbers were taken** — both previously cost this
project real time, and both are live:

- Every tab this tooling drives reports `document.visibilityState === "hidden"`. The change feed
  polls only when visible, **so nothing feed-driven ever updates in a driven tab**; CSS transitions
  do not advance; media loading is deferred. Nothing below depends on a feed refresh or a
  transition-settled colour.
- `resize_window` reports success while the rendered viewport does not follow, so **no narrow-width
  or true-zoom finding is claimed here.** Those remain human gates.

---

## Part 1 — The current information architecture, measured

### 1.1 Destination census

Counted by walking the live app, not read from source.

| Level | Destinations | Detail |
|---|---:|---|
| Top-level rail | **5** | My Experiments · Project Memory · Governance & Safety · Statistics · Settings & API |
| Project Memory tabs | 4 | Overview · Sources · Concepts · Graph |
| Governance & Safety tabs | 3 | Policy · **Validator** · Schema Reference |
| Statistics tabs | 2 | General ISAAC · My Stats |
| Settings & API tabs | **7** | Overview · Data & Privacy · About · API Access · Endpoint Explorer · Connect Your Agent · Help & Tutorial |
| **Subtotal outside a record** | **21** | |
| Record rail — `WORKFLOW` | 5 | Load Record · Complete Metadata · Review Evidence · Review Export Readiness · Export |
| Record rail — `DATA CAPTURE` | 1 | Capture & Proposals |
| Record rail — `WORKSPACES` | 3 | Record Fields · Runs · Graph |
| Record rail — footer | 1 | Evidence Trail |
| **Total addressable destinations** | **≈31** | for a product with **two** jobs |

**Corrections to assumptions worth recording.** `/validator` is **not a route** — it redirects to
`/experiments`; the standalone Validator is reachable only as a *tab inside Governance & Safety*.
There is **no Historical Import destination at all**, at any level.

### 1.2 Three navigation taxonomies in one 212px rail

The record screen's left rail carries three visually-labelled groups — `WORKFLOW`, `DATA CAPTURE`,
`WORKSPACES` — but only **two** `<nav>` landmarks, `aria-label="Workflow pipeline"` (212px) and
`aria-label="Record workspaces"` (212px). `Capture & Proposals` renders under its own visual
heading while living inside the *workspaces* landmark. So the visual grouping (3) and the
programmatic grouping (2) disagree.

**Three of the five workflow steps are inert**, each printing the identical 34-character sentence
`Complete 'Complete Metadata' first.` — the same string rendered **three times** inside a 212px
column. Measured: the `Workflow pipeline` landmark exposes exactly **two** activatable targets
(`Load Record`, `Complete Metadata`); the other three are non-interactive text with a lock glyph.

### 1.3 The Assistant rail's permanent cost

| Measurement | Value |
|---|---:|
| Window width | 1512 px |
| Left rail (`nav`) | 212 px |
| Main content (`main`) | 957 px |
| **Assistant rail (`aside`)** | **308 px** |

The Assistant occupies **20.4% of the window** and **24.4% of the non-navigation area**,
permanently, on every record workspace. It holds **13 visible buttons** (`Collapse Assistant`,
three suggested questions, one composer control, `What Can I Ask?`, and **seven** `AGENT ACTIONS`).
It is collapsible — but it is expanded by default, and 13 options is more than three times the
working-memory limit.

Credit where it is due, and it is genuinely rare: the rail states plainly *"There is no language
model in this build. Nothing you type here is sent to a model provider."* and *"The Assistant is
advisory: it explains artifacts and points to sources. It never validates."* That is exactly the
honesty posture the project demands, and any redesign must carry it forward verbatim in substance.

### 1.4 Vertical volume, per surface

| Surface | `scrollHeight` | Visible text elements | Visible buttons |
|---|---:|---:|---:|
| Record → Record Fields (default, collapsed) | 958 px | 95 | 25 |
| **Record → Record Fields (all 11 disclosures expanded)** | **7 653 px** | — | — |
| Record → Runs (no runs yet) | 878 px | — | 18 |
| Record → Capture & Proposals | 1 200 px | 76 | 18 |
| **Record → Graph** | 1 395 px | **145** | **34** |
| Project Memory | 926 px | 58 | 12 |
| Governance & Safety | 772 px | 24 | 5 |
| Settings & API | 1 109 px | 67 | 13 |
| **Statistics** | **3 820 px** | **422** | 6 |

Two findings the table makes unavoidable:

1. **An *empty* record's field workspace is 7 653 px tall when opened — 9.2 viewport-heights at
   828 px, with no data entered.** The default collapsed state (958 px) is well-judged; the problem
   is what "open the thing I need" costs.
2. **The Graph workspace is the most control-dense surface in the entire record screen** — 34
   visible buttons and 145 text elements — for the feature this scope change considers least
   relevant to the narrowed product.
3. **Statistics carries 422 visible text elements over 3 820 px**, the densest screen in the app,
   as one of five top-level destinations.

### 1.5 Typography — this is the finding, and it is worse than "no scale"

Measured on the record screen (the primary work surface), excluding `sr-only` content:

| Font size | Text-bearing elements (Record Fields) |
|---|---:|
| 26 px | 1 — **and it is `sr-only`** |
| 15 px | 0 |
| 14 px | 4 |
| 13.5 px | 1 |
| 13 px | 18 |
| 12.5 px | 19 |
| 12 px | 14 |
| 11.5 px | 5 |
| 11 px | 28 |
| 10.5 px | 5 |

**Nine distinct sizes across a 4.5 px range, in 0.5 px steps.** A 0.5 px step is not a hierarchy
level; it is noise. 90 of 95 text elements (94.7%) sit between 10.5 px and 13.5 px. On the Capture
workspace the largest visible text in the entire viewport is **15 px** (3 of 76 elements); on
Graph it is 17 px.

**And the record screen has no visible page title at all.** Its only `<h1>` is
`class="sr-only"`, 1×1 px, `clip: rect(0,0,0,0)` — measured directly. Two consequences:

- **A sighted scientist gets no heading anchor on the screen where they do all their work.** The
  secondary screens (Project Memory, Governance, Statistics, Settings) all render a 22 px visible
  title. The primary surface is the one without one.
- **That hidden `<h1>` reads `"Review Record"` on every workspace** — including `?view=runs`,
  `?view=fields` and `?view=capture`. A screen-reader user is told they are on "Review Record"
  while they are in fact in Runs. It is announced correctly on exactly one of four workspaces.

*One suspicion I checked before publishing it and then discarded:* a probe by `textContent` showed
an apparently empty button label in the Assistant rail. Re-measured over accessible name
(`aria-label`/`title`/`sr-only` child): **zero unlabelled visible controls anywhere on the record
screen.** There is no unlabelled-control defect. Recorded because the false version of that claim
is exactly the kind this project keeps publishing.

### 1.6 The Experiment Library's actual payload

`GET /api/experiments` returns, per experiment and nothing more:

```
id · title · scenario · status · created_utc · pending_count · evidenced_field_count
   · exported · record_id
```

So, mechanically:

- **No run count.** The Library cannot show "how many Runs" without N further requests.
- **No technique / beamline / facility.** The proposed `Beamline` column has no data source.
- **No `updated_utc`.** Only `created_utc` — so **"sort by Last Updated" is not implementable from
  this payload**, and the row's date chip is a *creation* date presented where users read
  recency.
- **No folder, no owner, no tags.**
- The rendered row shows: title, `Draft` chip, date, a `N Fields Need You` chip, chevron. There is
  **no sort control, no filter control, and no per-list search** — only a global `⌘K`.

And the failure mode is already visible in the shipped worked example: **five records all titled
`XANES Example — CuO (Cu K-edge)`**, distinguishable only by a secondary line
(`Example 1 · at setup: extraction only`). That is the Library's core job failing on the product's
own demo data.

---

## Part 2 — Impeccable critique

**Mode: Operate.** The visitor completes a task; scanability, consistency and the real usage scene
outrank expression. **Target:** the record workspace (`apps/web/src/screens/RecordWorkbench.tsx`
and the four `?view=` panels), with the Library and the four secondary screens as context.

### 2.1 Design Health Score

| # | Heuristic | Score | Key issue |
|---|---|:-:|---|
| 1 | Visibility of System Status | 3 | Gated workflow rail, honest banners, and *"No check has been run here yet… That is not the same as 'no findings'"* are exemplary. Undercut by having no visible page title and no indication of which workspace you are in beyond a rail highlight. |
| 2 | Match System / Real World | 2 | Backend identifiers are printed as product copy: `reduced_spectrum`, `qc_status`, `required_for_evidence_record`, `record-level`, and section headers reading `Environment & Context context`, `Timestamps timestamps`, `Relationships links`. The scientist is shown schema paths, not their own language. |
| 3 | User Control and Freedom | 3 | Unsaved text survives workspace switches; leaving a run with unparseable text asks first in a real focus-trapped dialog; discard and rename exist. But 3 of 5 workflow steps are permanently inert with no action available. |
| 4 | Consistency and Standards | **1** | Nine font sizes in 0.5 px steps; `h2` is 13 px on Fields, 14–15 px on Runs, 15 px on Capture; three visual nav groups over two landmarks; the only `h1` is hidden and mislabels three of four workspaces. |
| 5 | Error Prevention | **4** | Genuinely excellent and should not be touched: typed `RESET` gate, `If-Match` preconditions (run creation refused with `precondition_required` when absent), export gating, explicit no-guessing refusals, acceptance failing closed without a trusted actor. |
| 6 | Recognition Rather Than Recall | 2 | Five identically-titled records; no run count, technique or recency in the row; the scientist must remember which one they were in. |
| 7 | Flexibility and Efficiency | 2 | `⌘K` search exists and is good. No sort, no filter, no folders, no saved views, no cross-experiment review queue. Thirteen assistant buttons is not efficiency. |
| 8 | Aesthetic and Minimalist Design | **1** | 7 653 px on an *empty* record's fields workspace; 34 buttons on Graph; a 308 px assistant rail taking 20.4% of the window by default; 422 text elements on Statistics; one 34-character sentence printed 3× in a 212 px rail. |
| 9 | Error Recovery | 3 | Typed 422s, explicit conflict resolution that supersedes without deleting, `409`/`412` precondition semantics, malformed-persisted-values read rather than refused. One documented destructive silent-failure shape remains unfixed in `IngestionProposalsPanel`. |
| 10 | Help and Documentation | 3 | Guided tutorial, honest inline explanations, `What Can I Ask?`, a `Help & Tutorial` tab. But help is scattered across Settings (7 tabs), Governance (3 tabs), the Assistant rail and inline prose — four homes. |
| **Total** | | **24/40** | **Middling — structurally strong engineering inside a surface that will not scan** |

All ten heuristics apply to an Operate surface; none is scored `n/a`.

### 2.2 Design specificity verdict

**Authored for this product, not category-interchangeable — and that is the reason the redesign
should be a refinement, not a replacement.**

No generic dashboard would ever ship the copy this product ships. *"These are values the system
refuses to guess. Confirm each before this record can export — expected, not a failure."* *"Nothing
here writes a value directly."* *"Every line is drawn from a recorded fact; nothing is inferred from
resemblance."* *"1 node has no chip and can never be hidden, so these numbers total 12, not 13."*
That voice is the product's single strongest design asset and it is unmistakably ISAAC. The
light-first, calm, card-based "Scientific Clarity" language is coherent and appropriate.

**Deterministic scan: unavailable** (negative-control-proven; see Part 0). Nothing in this verdict
comes from a detector.

**Visual overlays: not attempted, and no overlay exists.** Injection was not run and no live-server
overlay was started, so no claim is made that the user can see highlighted findings in their
browser. The evidence here is measurement, not overlay.

**What is category-interchangeable, and it is the one thing that is:** the *structure*. A left rail
of grouped links, a right assistant rail, a centre column of collapsible cards, a coloured status
banner on top — that shell could belong to any B2B SaaS product. The identity lives entirely in the
prose and almost not at all in the composition. Five records titled the same thing, in a list with
no columns, is the clearest symptom: the layout is not doing any of the work the copy is doing.

### 2.3 Cognitive load assessment

| Checklist item | Verdict | Evidence |
|---|:-:|---|
| Single focus | **FAIL** | Amber banner + 11 field cards + 212 px workflow rail + 308 px assistant rail all compete on first paint |
| Chunking (≤4 per group) | **FAIL** | 11 disclosures on Fields; 13 buttons in the Assistant; 7 tabs in Settings |
| Grouping | PASS | Cards, borders and shared backgrounds are genuinely well executed |
| Visual hierarchy | **FAIL** | Max visible font on the primary surface is 15 px; no visible page title |
| One thing at a time | PASS | The four `?view=` workspaces do achieve this, and it was the right call |
| Minimal choices (≤4) | **FAIL** | 13 assistant actions; 34 buttons on Graph; 21 destinations outside a record |
| Working memory | **FAIL** | Five identically-titled records; no recency, run count or technique in the row |
| Progressive disclosure | PASS | 958 px collapsed vs 7 653 px expanded — the default is correct |

**5 of 8 failed → HIGH cognitive load. Critical fix needed.**

The three passes matter: they say the *bones* are right. Progressive disclosure, per-workspace
focus and visual grouping are already in place. What fails is **hierarchy and choice volume** —
which is a typography, layout and triage problem, not an architecture rewrite.

### 2.4 What's working — protect these

1. **The honesty of the copy.** It is the best thing in the product, it is the scientific-integrity
   requirement made visible, and every line of it must survive the redesign. *"No check has been run
   here yet, so nothing on this record has been checked on this screen. That is not the same as
   'no findings'."* — do not "simplify" that sentence.
2. **Error prevention (scored 4).** `If-Match` preconditions, typed destructive gates, export
   gating, no-guessing refusals, fail-closed acceptance. Untouched by this plan.
3. **The four-workspace split and collapsed-by-default disclosure.** The 2026-09-03 decision to
   stop the infinitely-long record page was correct and is working: 958 px on first paint. The
   redesign builds on it rather than revisiting it.

### 2.5 Priority issues

**P0 — There is no visible typographic hierarchy on the primary work surface, and the hidden title
lies.** Nine sizes in a 4.5 px band; nothing above 15 px; the only `h1` is `sr-only` and says
`"Review Record"` on Fields, Runs and Capture alike. Fix: a real type scale with perceptible steps,
a visible record title, and a per-workspace accessible name that matches the workspace.

**P1 — 21 destinations outside a record, and 3 competing taxonomies inside one.** Statistics (422
text elements), Project Memory (4 tabs), Settings & API (7 tabs) and Governance (3 tabs) are
top-level peers of the scientist's actual job. Fix: two primary destinations plus Settings, with
the Validator promoted out of a Governance tab and the developer surfaces demoted into Settings.

**P2 — The Experiment Library cannot do its job, and the API is the reason.** No run count, no
technique, no `updated_utc`, no sort, no filter, no folders. Five identically-titled demo records
prove it. Fix: extend the list payload first, then the screen; folders after. **This is the
highest-value slice in the whole plan** — it is the returning scientist's entire experience.

**P3 — The Assistant takes 20.4% of the window by default to offer 13 choices in a build with no
model.** Fix: collapsed by default, contextual on demand, with the two honesty claims preserved
verbatim wherever it appears.

**P4 — Backend vocabulary is product copy.** `reduced_spectrum`, `qc_status`,
`required_for_evidence_record`, `Environment & Context context`. Fix: a scientist-facing label per
path, with the schema path available under disclosure — never removed, because it is how a curator
maps a field.

### 2.6 Persona red flags

- **Confused first-timer ("Jordan").** Lands on a record with an amber banner naming
  `reduced_spectrum` and `qc_status`, three locked workflow steps repeating one sentence, and a
  13-button assistant. The guided tutorial is genuinely good — but it is dismissible and, once
  dismissed, hard to find again (it lives behind Settings → Help & Tutorial).
- **Accessibility-dependent user ("Sam").** Told "Review Record" on three of four workspaces.
  Gets two same-width `nav` landmarks whose visual grouping is a third thing. Every substantive
  label is 11–13 px. *Mitigating and real:* zero unlabelled controls, a live-region announcer, and
  an a11y baseline harness at 390 px and 320 px with platform-split transcriptions.
- **Impatient power user ("Alex").** Cannot sort, filter, or fold the Library; must open records to
  tell them apart; gets no cross-experiment "what needs me" view.
- **Distracted mobile user ("Casey").** Unassessed, and honestly so — `resize_window` does not move
  the rendered viewport under this tooling, so no narrow-width claim is made here.

### 2.7 Minor observations

- The empty state (`Start your first experiment` → three cards) is well judged; the `Create
  Experiment` inline form is clean and the character counters are a nice touch.
- `Capture Experiment Notes` is a good, plain label. Keep it.
- `Statistics` splits `General ISAAC` from `My Stats`, which is a sound distinction hidden inside a
  screen the narrowed product should not promote.
- The `Worked Example` mode chip behaved exactly as documented, and skipping the tour discarded the
  example workspace cleanly — the isolation guarantee is observably real.

---

## Part 3 — Proposed information architecture

### 3.1 Top level

```
ISAAC
├── Experiments            ← the Library; the home; the default route
├── Historical Import      ← new; Pillar 2
│
└── Settings               ← absorbs API Access, Endpoint Explorer,
                             Connect Your Agent, Data & Privacy, About,
                             Help & Tutorial, Project Memory, Statistics
```

Three primary items, down from five, with **21 → ~4** destinations outside a record.

`Needs Review` and `Recent` become **views of Experiments** (a filter chip row), not sibling
destinations — they are lenses on one list, and promoting a lens to a peer is what produced the
current census. The cross-experiment review queue is proposed as **DEC-09**, a real decision, not
assumed.

**Validator** moves out of a Governance tab. It is a deterministic scientific tool, not a policy
document; proposed placement is a Library-level action (`Check a record file`) plus its existing
in-record integration. **Governance & Safety's Policy content** stays reachable under Settings —
it carries real disclosures and must not be lost.

### 3.2 Experiment level

```
Experiment: <title>                      [Draft] [ULID]
├── Overview     identity · shared metadata · state · readiness · next action · recent activity
├── Runs         browse · search · create · focus · edit · compare · inherited vs overridden
├── Capture      current run · notes · transcript · native mic · Claude-originated capture
├── Review       proposals · ambiguities · conflicts · unmapped · missing · decisions
└── Record       resolved record · validator · provenance · revisions · submission/export
```

Five workspaces, up from four — because `Review` currently has **no home of its own**: proposals
and unmapped notes live inside `Capture`, conflicts and evidence live elsewhere, and export
readiness lives in the workflow rail. Consolidating them is the single largest IA simplification
available, and it is what makes one review experience possible across voice, transcript, CSV and
historical import.

**The workflow spine stays server-derived and gated. It is not replaced by these tabs.** Proposed
treatment: the spine becomes a compact horizontal progress strip that *states the single next
action*, and the five workspaces become the ungated navigation — resolving the current
three-taxonomies-in-one-rail problem without weakening a gate.

**Capture is a destination, not a sixth workflow step.** There is no derivable criterion for
"capture is finished"; `notes >= 1` would nag every record that legitimately needs none, inventing
a completion criterion nobody defined. The repository already argued this exact case for
submission ("a DECLARATION BY A PERSON"). No tick, no lock, no ordering, no `aria-current="step"`.

**Labels are proposals, not approvals.** `Overview / Runs / Capture / Review / Record` must be
reconciled against the application's established language before implementation — the repo's own
prior direction used `Lab Records`, `Experiment Details`, `Capture & Proposals`, `Review Evidence`,
`Review Export`. Label selection is **DEC-05**.

### 3.3 Folders

Folder membership is **application organization and nothing else**. Moving an Experiment must not
change scientific metadata, record identity, Run values, or any validation result — this is a
test-enforced invariant, not a guideline.

Proposed scope: create · rename · nested where useful · move · breadcrumbs · browse · search across
everything · choose a destination on create and on import. **Not** Google Drive's full feature set,
and explicitly **not** sharing or per-user ACLs — those require a trusted authentication boundary
ISAAC does not have. The data model must let ownership arrive later without a rewrite; the
storage-shape decision is **DEC-06** and is resolved in the data-model workstream, with a strong
prior toward **no new table** (a feature needing a new migration does not work until an operator
acts, which is a hard stop no agent can lift).

### 3.4 Validator presentation

The deterministic validator **stays and is not weakened**. Only its presentation changes. A
scientist should read one of: **ready · incomplete · needs review · blocking issue · advisory** —
terminology reconciled with `workflow.py`'s actual derived states, never invented alongside them.

Three separations the current UI has already learned the hard way and that must be preserved:

- the schema's own verdict stays visible as `schema_ok`;
- exactness findings stay in their own list and are **never** reported as official-schema errors;
- advisory warnings can never turn a PASS into a FAIL.

Detailed technical output goes under progressive disclosure. No CLI transcript is ever
reintroduced — no CLI is invoked.

### 3.5 Historical Import

```
New Import → Sources → Parse → Reconstruct → Review → Add to Experiments
```

The scientist must be able to see: which files were recognized; what parsed; what failed; what
Experiments ISAAC thinks exist; what Runs it thinks exist; **which source supports each
interpretation**; what was inferred rather than read; where sources disagree; what is unresolved.

The anti-pattern to design against, stated as a ban: **Upload Files → Spinner → Mysterious JSON.**

Imported work then lands in the ordinary Experiment Library and behaves like any other
Experiment — searchable, folder-organizable, Run-aware, provenance-aware, validated, exportable.
Historical Import is an ingestion workflow, not a parallel application universe.

### 3.6 Visual identity — refinement, not replacement

Retained: light-first, calm, card-based, evidence-first, premium-instrument. The existing token
system, colour language and component vocabulary stay.

Changed — and this is the whole visual programme:

1. **A real type scale.** Replace nine sizes in 0.5 px steps with a scale whose steps are
   perceptible, and give the record screen a **visible** title.
2. **One primary action per surface**, with secondaries demoted and the rest grouped.
3. **The Assistant collapsed by default**, contextual on demand, honesty claims preserved verbatim.
4. **Reduce repetition**: one inert-step explanation, not three.
5. **Scientist-facing labels** with schema paths under disclosure.

Two existing guards constrain any repaint and must be honoured rather than edited:
`src/__tests__/interaction-states.test.ts` (no green/red hex or pass/fail token in *any*
interaction-state rule — it bans the raw hex too, so that is not an escape; `base.css`'s
`filter: brightness()` idiom is the sanctioned route), and the phantom-custom-property ratchet.
Accessibility contrast work must be re-transcribed from **Linux CI**, with the darwin column
measured locally rather than reasoned — a carried-forward darwin half has been wrong before, in 19
of 168 cells.

---

## Part 4 — What this plan deliberately does not do

- It does not delete the Evidence Graph. It removes it from primary scientist navigation and
  requires a dependency analysis before any backend removal. **Provenance stays**; the
  *visualization* stops being a destination.
- It does not remove native microphone capture. It assigns it a role.
- It does not weaken, replace, or reinterpret the deterministic validator.
- It does not touch the truth path, the export gate, or the exactness gate.
- It does not claim any narrow-width, 200%-zoom, or real-microphone verification. Those are human
  gates this tooling provably cannot drive.

---

## Part 5 — Root cause: the design system is half-built

Part 1 measured *symptoms* in the rendered page. A parallel code-level audit found the cause, and it
reframes the whole typographic problem. Independently measured over `apps/web/src`:

| Measurement | Value | Consequence |
|---|---|---|
| `styles/tokens.css` total tokens | **82** | — |
| …of which **colour** | **70** | |
| …**radii** | 6 | |
| …**shadows** | 4 | |
| …**font families** | 2 | |
| …**font sizes** | **0** | |
| …**font weights** | **0** | |
| …**line heights** | **0** | |
| …**spacing** | **0** | |
| Hand-authored `font-size` declarations | **1 073**, in **20 distinct values** | nothing to be consistent *with* |
| …share in 11–13 px | **82.4%** (90.3% within 10.5–13 px) | matches my rendered 94.7% |
| Distinct font weights in use | **8**, including non-standard **550 / 620 / 650** | |
| Spacing literals | **2 407**, in **32 distinct values** — every integer 1–18 px in use | |
| `16px` declarations in the entire product | **one** | |
| Informational grey text inks | **8**, the bottom four within 0.5:1 contrast of each other | |
| Colour tokenization | **99.3%** | |
| Live phantom custom properties | **0** (142 declared, 142 referenced) | the ratchet is holding |

**And the base is 13 px, not 16 px:** `styles/base.css:21` sets `body { font-size: 13px }`. So the
whole product renders at 81% of the browser default before a single component decides anything.

> **This is the finding that should drive the visual programme.** The team did not fail at
> typography through carelessness — **colour is 99.3% tokenized and there are zero phantom
> properties, which is genuinely disciplined work.** Type, weight, line-height and spacing were
> simply never given tokens, so 1,073 declarations had nothing to conform to and drifted into 20
> values, 8 weights and 32 spacing steps. The fix is therefore *not* "restyle the app". It is
> **finish the token system** — add the four missing axes, then migrate declarations onto them.
> That is mechanical, reviewable, and testable in a way a restyle is not.

**One correction worth keeping**, because it is the class of error this repository keeps making: a
first pass reported "no root font-size override exists, so the browser's 16 px applies" and
"8 phantom custom properties". **Both were false** — `base.css:21` sets 13 px, and all 8 phantoms
existed only inside comments. They were caught by re-measuring rather than by a test. Treat any
token or typography figure in this plan as re-derivable, and re-derive it.

## Part 6 — Redundancy, measured

| Claim | How many places it is stated |
|---|---:|
| **Validation state** | **9** |
| "What to do next" | **6 on one record screen** |
| Pending / needs-you counts | **5** |

The six next-action claims on a single record screen are: the workflow-spine current step, the
workspace nav's capture card, `NeedsYouBanner`, `WorkflowProgressBanner`, the status-bar phase, and
the Assistant's suggestions. **The code already knows two of them collide** —
`WorkflowProgressBanner` takes an `excludeSteps` prop whose own comment says it exists *"so the
same next action never shows twice."* A prop that suppresses a duplicate is evidence that the
duplicate is structural.

**And there are two different five-step workflow vocabularies in the shipped product:**

| Source | Steps |
|---|---|
| Server-derived spine | Load Record · Complete Metadata · Review Evidence · Review Export Readiness · Export |
| `HelpPanel` | Draft · Complete · Export · Validate · Audit |

A first-time scientist reading Help is taught the second one — and `HelpPanel` is reachable only
from the `home` TopBar variant, so **help is absent from every record screen**, which is exactly
where a first-timer needs it. Reconciling these two vocabularies is part of **DEC-05**, and the
server's is authoritative because it is derived rather than written.

## Part 7 — Two false shipped strings found during this audit

Reported here rather than fixed, because this is a planning run — and recorded because this
repository's dominant defect class is a true-looking claim beside green tests.

1. **`HelpPanel.tsx:7`** promises draft extraction **"from your files"**. `POST /api/uploads` is an
   **unconditional 403**, and no path in this build turns a scientist's file into a draft. The
   claim is false, and it is the product's own help text.
2. **`HelpPanel.tsx:10`** attributes the entire validate verdict to the official schema. That is
   **stale**: `ok = schema_ok AND exactness_ok`, and §11 is explicit that no surface may report an
   exactness refusal as an official-schema error.

Both belong in the redesign's first slice, and both should be pinned by the existing
`upload-claim-parity` guard family rather than merely edited — an unpinned correction is one edit
away from returning.

## Part 8 — Surface census, reconciled

A code-level walk counted **53 scientist-facing surfaces**: 11 routes, 22 URL-addressable
tabs/views behind them, plus independently-mounted panels. That is the number to plan against; my
rendered census of ~31 *destinations* counted only what a user can navigate to by clicking, and
both are correct about different sets. 29 screen components, 61 reusable components, 41 CSS files,
**250,937 lines under `apps/web/src`** — of which **120,493 are `__tests__`**, more than half of
all non-CSS source.

### Feature triage — 59 rows over 53 surfaces

| Disposition | Count |
|---|---:|
| CORE — KEEP AND IMPROVE | 26 |
| KEEP UNDER ADVANCED / SETTINGS | 11 |
| KEEP BUT MOVE | 6 |
| MERGE INTO ANOTHER WORKFLOW | 5 |
| REMOVE FROM PRIMARY SCIENTIST UI | 3 |
| CANDIDATE FOR COMPLETE REMOVAL | 5 |
| UNKNOWN — NEEDS EVIDENCE | **0** |

**Merges identified:** `WorkflowProgressBanner` + `NeedsYouBanner`; Guided Completion into
`?view=fields`; `RunFindings` + `ValidateReview`; Load Materials into Settings → Help;
Statistics→mine into My Experiments.

### Evidence Graph — verdict and the one real blocker

**CANDIDATE-FOR-COMPLETE-REMOVAL, visualization-only.** Measured: **6,169 lines** (panel 1,543 +
CSS 1,109 + `lib/evidenceGraph.ts` 3,517), **123 tests**, **zero backend routes**, **zero backend
tests**, **zero other consumers** of its lib or CSS, invisible to the Assistant, and **zero
accessibility-baseline cells — it is not in `e2e/surfaces.ts` at all**, so the densest view of a
record has never been scanned. Old `?view=graph` bookmarks cannot break, because `list` is already
the fallback.

**The one blocker, and it must be closed first:** `GET /experiments/{id}/provenance` loses its only
frontend caller. The Evidence List must grow a provenance read-out **before** the graph is cut, or
`derived_from` chains become invisible — which would be removing provenance to simplify the UI,
exactly what §38 forbids. Provenance itself is untouched by the cut. Full *backend* removal is not
applicable: there is no backend to remove.

*A prior claim that the Evidence Graph carried "7 a11y baseline cells" was re-measured and is
**false** — those strings exist only in comments, one of them doubly struck through.*

### Project Memory — the larger prize, and it was not on the list

**~7,800 lines and 578 test cases — the largest single test mass in the application — plus one of
five top-level navigation slots, for a graph of *this repository's own source code*, shown to
scientists.** It is a developer/authoring tool occupying prime scientist navigation. All four of
its tabs are removal candidates from the primary UI. This is a bigger simplification than the
Evidence Graph and was not named in the authorizing directive; it is raised here rather than
actioned.

### Assistant — KEEP BUT MOVE, five mounts to one or two

Confirmed exactly **5 mounts**; **29 answerable families** (8 Q&A intents, 9 graph intents, 12
agent actions); pure substring matching; refuses honestly; never guesses; cannot mutate except
through an explicit user-confirmed `stageAnswer`. **`ASSISTANT_NO_MODEL_CLAIM` renders ungated on
all five mounts and was verified true** — `/api/assistant/ask` returns `501
no_provider_configured`. Against that: **517 test cases across 29 files**, largely restating counts
five other surfaces already state.

**It is not a directory delete.** Six lib modules have non-Assistant consumers, and
`assistant.css` is shared with `GuidedPrompt`. Demotion is a mount-count and placement change, not
a removal.

## Part 9 — Honest gaps in this critique

- **No rendered-height measurement exists for 6 of the 11 routes.** Only `/record/:id` and its four
  views have ever been harnessed. My live measurements cover 9 surfaces; the rest are code-level
  only.
- **Real 200% zoom is undriveable by any CDP method.** **28 fixed-height scroll-clipped containers**
  are where it would bite, and not one has been observed under real zoom. Human gate.
- **Narrow widths were not measured**, because `resize_window` reports success while the rendered
  viewport does not follow. Human gate, or the same-origin-iframe workaround.
- The token census measured **declarations, not computed values**.
- The Impeccable **mechanical detector is non-functional here** and contributed nothing. No "0
  findings" claim is made.
- My rendered numbers (212 px rail, 1 395 px / 34-button graph at 1512 px on an empty record) and
  the committed `docs/evidence/redesign-before-after-2026-09-03.md` figures (240 px rail, 2 481 px /
  53 controls at 1440 px) differ because they measure different records at different widths on
  different dates. **Neither supersedes the other; both need their vantage point quoted.** The
  conclusion is identical either way: the graph is the densest view of a record.
