# Pre-Dean Review Readiness — Closure

**Date:** 2026-07-28
**Base:** `f57e239` (image `v0.0.26`) on org `main`
**Branch:** `feat/pre-dean-readiness` — one branch, one PR, one merge commit, one image
**Scope authorized:** Tier 1 + Tier 2 only, as a counter-proposal to a broader twelve-item plan.
Nothing here begins Phase 37, adds a dependency, touches the deterministic truth core, or changes
validation, export, or evidence-authority semantics.

The goal was narrow: make the synthetic preview **credible and legible** to a senior technical
reviewer, and put the open questions in writing. Not to broaden the product.

---

## 1. What shipped

| # | Item | Outcome |
|---|---|---|
| 1 | Hosted-environment truthfulness sweep | **Done** — 8 strings in the first pass, 7 more found in review rounds |
| 2 | Visible scenario labels for the five canonical seeds | **Done** — derived, never stored, past tense |
| 3 | Copy Diagnostics extending the existing debug box | **Done** — one generator, two mounts |
| 4 | `What Can I Ask?` | **Done** — the catalog audit proved a real gap |
| 5 | Dean decision brief | `docs/dean-integration-review-brief.md` |
| 6 | Evidence-sidecar audit | `docs/evidence-sidecar-audit.md` |
| 7 | Five-minute demo script | `docs/demo-script-pre-dean.md` |
| 8 | Pre-demo checklist | in the demo script, 21 rows |
| 9 | Readiness-summary duplication audit | **NO GAP — nothing built** |
| 10 | Export-package-preview duplication audit | **ALREADY COVERED — nothing built** |
| 11 | Performance and compression audit | **Measured, nothing changed** |
| 12 | Status and roadmap documentation | this document |

Items 9 and 10 are successes, not omissions: both audits existed to prevent building a second
readiness model or a second exporter preview, and both found the need already met.

---

## 2. Contracts established

### Hosted-environment language contract
The frontend may state only what it can observe. Concretely:

- **Environment label** derives from `isHostedBuild` (`apps/web/src/lib/api.ts`), a compile-time
  comparison of `VITE_API_BASE` against the local default, surfaced through
  `apps/web/src/lib/runtimeContext.ts`. Because that flag is true for **any** non-default base —
  including a developer pointing at another localhost port — it may **never** carry an
  institution-specific claim. The chrome badge says `hosted preview`, not `SLAC Preview`.
- **Access control** is described as *how the deployment is configured and operated*, never as
  something the app verified: the browser cannot see the edge. Four facts are kept separate —
  (a) edge access, (b) app-managed identity/roles (none), (c) the optional shared bearer key,
  (d) per-user API-key management (absent).
- **Synthetic-only** is a statement about configured **mode**, never about content. There is no
  content-based real-vs-synthetic classifier anywhere, and none was added. Real mode genuinely
  refuses to boot: `validate_runtime_mode_or_raise()` makes `create_app()` raise.
- **The provider name is withheld** from client-rendered text. Two pre-existing tests forbid the
  substring (`apps/web/src/__tests__/settings-page.test.tsx` FORBIDDEN list;
  `apps/api/tests/test_about_and_openapi.py`). The copy says "institutional single sign-on".

Two instances of a content-classification falsehood were found and removed —
`screens/LoadMaterials.tsx` ("a file that looks real or private is intercepted") and
`screens/GovernancePage.tsx` ("a real-looking file is intercepted here"). Both asserted a check the
software does not perform: `POST /uploads` refuses **every** request with 403, declares no multipart
form, and reads nothing; the panel has no file input and opens no picker.

**Guard:** `apps/web/src/__tests__/hosted-truthfulness.test.tsx` now walks every `.ts`/`.tsx` under
`apps/web/src`, strips comments, and fails on five claim-class patterns (a file "looks" real/private,
"appears real", content-based detection, classifying an upload, inspecting a file). It scans the
source tree rather than a hand-copied list, so the claim class cannot return silently.

### Synthetic scenario contract
The five canonical seeds carry a **derived, never-stored** scenario label, exposed once at
`routes.py::_summary` from `workspace.py::scenario_label`, and rendered as a secondary line by
`ExperimentRow`.

```
Scenario 1 · seeded: extraction only
Scenario 2 · seeded: partial answers applied
Scenario 3 · seeded: all answers applied
Scenario 4 · seeded: descriptor uncertainty omitted
Scenario 5 · seeded: export run at setup
```

**The past tense is load-bearing, not stylistic.** The label names how the fixture was *materialised*
and is deliberately never refreshed. An earlier present-tense wording — `Scenario 2 · Partially
Confirmed`, `Scenario 4 · Missing Required Field` — was rejected in review after being demonstrated
false through the ordinary supported flow: applying the committed answers and exporting left the badge
asserting "Partially Confirmed" on a fully-confirmed, exported record, and "Missing Required Field" on
a record that had just passed official validation. **Invariance of the value is not
non-contradiction** when the wording is itself a state description; an invariant present-tense claim
over a mutating record is guaranteed to go false. Live state is carried by the queue group and the
`StatusChip`, and the scenario line must never duplicate or restate it.

Boundaries held and tested: nothing new is persisted (`Experiment.to_state()` gains no key, and a
save→reload→save round-trip is byte-identical); the label never reaches a draft, official record,
evidence sidecar, or the `/artifacts` payload (asserted against the output of the **real**
`export_draft` for all five seeds); it is `null` and renders nothing for any user-created record; and
the demo remains idempotent at exactly five canonical ids.

### Diagnostics privacy contract
`apps/web/src/lib/diagnostics.ts::buildDiagnosticsReport` is a pure function feeding two mounts — the
existing `Technical Details` box on error states, and Settings → About (`/settings?tab=about`) for
normal operation. It emits `BUILD`, `SESSION`, `PROJECT MEMORY`, and `FAILURE SIGNALS` (error mount
only).

Excluded **by type, not by filtering**: `DiagnosticsFailure` has no `body` field, so `ApiError.body`
(typed `unknown`) structurally cannot be forwarded. The module imports no storage, cookie, or header
API; `collectBrowserContext()` is the only impure reader and its key set is pinned by a test, so a
future edit that starts reading storage has nowhere to put the result. Generating and copying perform
**no** network request (asserted with a throwing `fetch` spy). Unobtainable values render an explicit
`not available` rather than a plausible default, and server-supplied strings are whitespace-collapsed
and length-clipped so they cannot forge a section header.

**Zoom is deliberately absent.** `devicePixelRatio` cannot distinguish a Retina display at 100% from a
1× display at 200%, and `visualViewport.scale` tracks pinch only. Raw `Device Pixel Ratio` is reported
under its own honest name instead of a labelled guess. One `Source Commit` is emitted, not two, because
`memory.py` sets `source_graph_commit` to the snapshot's `built_at_commit` — two labels would restate
one value.

### Assistant capability-help contract
`What Can I Ask?` is presentation only. **No intent behaviour was added**; `assistant_query.py`,
`assistantComposer.ts`, and `graphCommands.ts` are unmodified.

Capability is **scope-dependent**, and the catalog respects it. Record surfaces list all eight real
intents under six headings. Project Memory lists only the memory family, because `queryScope="memory"`
routes to `answer_memory_scope`, which returns `_MEMORY_SCOPE_REFUSAL` for every record family — a
flat list would have advertised refusals on the very screen showing them. Graph Navigation appears
only while the `graphCapability` prop is present (Project Memory → Graph tab), and is limited to
parameterless commands: a hardcoded node would tie an example to one specific graph, and a
`<placeholder>` would not route.

Every listed example is held to the real trigger source by tests in **both** languages, so a backend
catalog change breaks the frontend test rather than silently drifting. Clicking an example inserts
text and never submits, and **never overwrites a non-empty composer** — the panel announces that rule
before the click rather than silently declining to act.

---

## 3. Deferred, with reasons

| Deferred | Reason |
|---|---|
| Playwright / real-browser visual regression | Greenfield: new devDependency, browser binaries, a new CI job, and macOS-vs-Linux font baselines. Its designed output is a fresh defect list, and its value is realised after the meeting, not before it. |
| axe / any new accessibility dependency | Same PR, same reason. Note that jsdom computes no layout, so contrast and overlap cannot be automated without the browser harness. |
| Graph regeneration | `graphify-out/` is gitignored; generation depends on a user-local `graphify` binary (`~/.local/bin/graphify` v0.9.4), not a project dependency. Community naming is an **LLM** pass (`--no-label` = "skip LLM community naming"), so full regeneration is non-deterministic **and** would send repository content to an external model — unapproved. |
| Graph freshness CI | CI cannot rebuild the graph for the reasons above, so an exact-match invariant against a rebuild is not implementable today. |
| Performance implementation | Measured and deferred: no compression in-repo (verified by curl — `/openapi.json` returned 66,926 bytes with **no** `content-encoding`), so compression is owned solely by the SLAC edge and is unverifiable from here. One 594 KB JS chunk (172 KB gzip), zero code splitting, Endpoint Explorer in the initial chunk. The Vite size warning corresponds to a real measured cost. The 494 KB deep-graph artifact is already correctly lazy. |
| Settings rename | The page behaves more like system/runtime/API information than adjustable settings, but renaming means route churn and deep-link changes for no functional gain. Raise as a product question. |
| Scenario label in the single-record header | The field already flows to `RecordWorkbench` and typechecks; only a render call is missing. Not done — the list view was where the five looked identical, and adding a surface would have meant another review cycle. |
| Collaboration, ownership, reviewer assignment, comments, multi-user approval, app roles | Explicitly on the back burner. |
| Phase 37 in every part | Real data, Postgres, Authentik claim mapping, API-key generation, portal integration, a real-data detector, external LLM, new scientific domains, evidence-sidecar redesign, `isaac-k8` changes. |

### Graph status, stated plainly
The served graph is a **point-in-time index of commit `caab1d0a`**, not a map of current code, and the
app already discloses this (`is_point_in_time: true`, `describes_current_head: false`,
`served_set_consistency`, and the disclosure in `GraphCanvas`). Current staleness is therefore a
**quality limitation, not a hidden truthfulness defect** — which is why regeneration was deferred
rather than rushed.

Future options, none chosen: (1) an institution-approved Graphify/model regeneration path;
(2) a deterministic `--no-label` build plus stored reviewed labels; (3) a replacement deterministic
graph builder; (4) excluding the graph from production until freshness can be guaranteed. Ownership of
graph generation, community labelling, freshness, and approval is Dean question 16.

---

## 4. Visual QA status — the accurate wording

- Krish has performed **repeated hosted human spot checks**, and they have found real defects: the
  expired-session down-state shipped as `v0.0.26` came from his own hosted QA of `v0.0.25`.
- **Automated visual-regression coverage does not exist** in this repository. There is no browser
  harness, no screenshot comparison, and no contrast tooling; vitest + jsdom computes **no layout**.
- **No browser or screenshot QA was performed in this effort.** Every layout claim in it is a DOM
  assertion or a reading of the CSS cascade.
- Formal repeatable browser and accessibility testing is **deferred until after the Dean meeting**.
- **Final authenticated hosted human QA remains required and open.** The hosted deployment sits behind
  an identity edge this environment cannot authenticate to, so no rollout is claimed as observed.

Known layout risks that need a human browser and are on the checklist:
1. The new scenario line's rendered height at ~320 px and at 200% zoom (`ExperimentRow` wraps rather
   than clips by reading, but the height change is a visual judgement).
2. Whether the `What Can I Ask?` popover fits above its trigger in the **empty-conversation** state,
   where `.assistant` is content-sized and the ancestor `.screen-card` has `overflow: hidden`. The cap
   was lowered to 34vh and the load-bearing sentences moved outside the scroll region, nearest the
   trigger — a **mitigation, not a fix**.
3. Contrast on three small 11 px strings in the capability panel remains `--text-tertiary` (3.86:1,
   below AA 4.5:1). The feature's load-bearing boundary sentence was moved to `--text-secondary`
   (8.07:1); the rest is a pervasive pre-existing repo-wide pattern, left for the deferred a11y work
   rather than swept the night before a review.

---

## 5. Process

Six workstreams under exclusive file ownership, at most three concurrent, because the served-content
manifest and shared label files must be reconciled centrally. Snapshot regeneration was performed
**once, by the orchestrator, after every workstream settled** — per `CLAUDE.md` §17, with
`--detail-out`, since concurrent slices would otherwise capture each other's in-flight hashes.

**Three independent reviews ran, and all three returned `DO NOT SHIP` on the first pass** — matching
the P36V.1 pattern of four out of four. No finding was a design defect; every one was a truthfulness
or test-generality defect that the full suite passed through. The reviews earned their place:

- The scenario-label review **demonstrated** the falsehood by driving the real API rather than arguing
  it, and found that the two tests which should have caught it had been narrowed to exactly the cases
  where the property holds — one `status_words` list omitted precisely `Exported` and `Done`, the two
  display strings that actually appear on rows.
- The truthfulness review reported "nothing Critical in the reviewed diff" and then blocked the branch
  on a **pre-existing** falsehood on the data-governance screen that the sweep had not reached.
- The capability review re-ran all twelve advertised examples through the real classifier itself
  instead of trusting the implementer's tests.

**Two of the authorizing prompt's own prescriptions were wrong and were corrected rather than
implemented**: the claim that the five seeds share one title (they carry distinct titles; the frontend
strips the distinguishing suffix at `adapt.ts:69`), and two of the five suggested scenario labels
(`Needs Five Confirmations` embeds a count that goes stale within the demo; `Evidence Review`
misdescribes a missing-required-field fault as an evidence fault). This continues the P36R **R9**
pattern of a brief's prescribed copy being falsifiable.

One orchestrator error is recorded for the same reason: the "state-independent fixture identity"
rationale behind the first label set was mine, and it was wrong.

**A second orchestrator error, of the opposite kind — an over-broad correction.** The fix for the
title-suffix claim went from "the seeds share one title" to "the suffix is never on screen", and the
second statement is also false. `stripLifecycleSuffix` is applied on exactly two surfaces — the
`/experiments` queue rows (`adapt.ts:93`) and the Record Workbench heading
(`RecordWorkbench.tsx:205`). The `TopBar` heading on Complete (`GuidedCompletion.tsx:310`), Evidence
(`EvidenceExplorer.tsx:135, 188`) and Export Readiness (`ExportReadiness.tsx:358`) passes the raw
`detail.title` through — there is no detail-level adapter — and the Assistant's `record_summary`
resolver echoes the stored title verbatim (`assistant_query.py:883-893`), verified by calling the
route: `This record 'Synthetic XANES — CuO (Cu K-edge) · New Draft' is currently needs attention, …`.
⌘K Search carries it the same way (`search.py:276-287`). Since the demo checklist prescribes clicking
`Summarize this record.`, the presenter would have been contradicted live by the app. All three Dean
documents now scope the claim per surface. The lesson matches R9: a correction is a claim too, and
gets the same verification as the thing it corrects.

---

## 6. Dean materials

| Document | Contents |
|---|---|
| `docs/dean-integration-review-brief.md` | Current state, what works, limitations (real-mode unsupported first), 16 questions, constraints |
| `docs/evidence-sidecar-audit.md` | Structure, creation/read paths, dependency analysis, authority status, migration risk under each ruling |
| `docs/demo-script-pre-dean.md` | Five-minute flow with route · expected state · action · what to say · fallback · what not to claim, plus a 21-row pre-demo checklist |

**Evidence-sidecar verdict: advisory in code, and code does not exceed the documentation.** Official
validation, export gating, and the audit exit status are each independent of it. Two findings sharpen
the Dean question rather than changing it: the sidecar has **no schema at all** (its shape is defined
solely by `build_sidecar`, pinned by ~20 tests), and for an already-exported record it is the sole
source of the Evidence Trail, opened unguarded at `routes.py:1714` (`get_evidence`) and `:1890`
(`get_artifacts`) — a missing sidecar would raise rather than degrade. Not reachable in the synthetic
demo, out of the authorized scope, and therefore documented as a post-meeting item rather than patched
tonight.

Two committed documents were found to **overstate enforcement**. Both claimed audit guarantees "every
sidecar path resolves (0 dangling)". It does not — `cli.py::cmd_audit` gates on `OfficialReport.ok`
alone (`cli.py:96`), and `render_audit` prints PASS while dangling paths exist. `docs/cli.md` had it
right, so the docs contradicted each other.

**The correction landed in two passes, and the first pass was incomplete — recorded because the
incompleteness was invisible in the diff.** The first pass fixed one instance in each file
(`architecture.md`'s ASCII box, `mentor-decisions.md`'s "What is already working" bullet) while
`docs/evidence-sidecar-audit.md` §6 pointed Dean at those same two files as where the defect lived — so
a reader following the pointer would still have found it. The second pass fixed the two survivors,
`docs/architecture.md:90` (the module-map `audit.py` row) and `docs/mentor-decisions.md:109-112` (the D1
drift-risk tradeoff), and rewrote §6 to record all four corrections in a table rather than to report an
open discrepancy. **All four instances are now corrected**; §6 is the authoritative list.

The same second pass corrected a stale audit figure that the CLI disproves: `mentor-decisions.md` and
`docs/ui-handoff/validation-audit-warning-model.md` both said `evidence 26/26`, where the committed
sample actually audits `PASS … 0 schema errors, evidence 33/33`. `26` is the sidecar's *dotted-key*
count; the audit denominator is enumerated from the **record** (33 targets). Both files now state the
number and what the denominator counts.

---

## 7. What Krish must still do

Hosted QA of this release is **not self-verifiable from this environment** and remains his gate. The
21-row pre-demo checklist in the demo script is the authoritative list. The rows that cover work new in
this release: the commit read off `/krish/api/health` (row 1), the five scenario lines (row 4),
`What Can I Ask?` (row 9a), Copy Diagnostics (row 19), and the two standing visual rows — narrow width
(row 20) and 200% zoom (row 21), which remain **unsigned-off**.
