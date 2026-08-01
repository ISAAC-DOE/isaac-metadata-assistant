# ISAAC Metadata Assistant — Integration & Review Brief

**Prepared for:** Dean · **From:** Krish Verma (kverma@slac.stanford.edu) · **Date:** 2026-07-28

Every factual claim below is cited to a repository location or a command. Where the answer is not
determinable from this repository, the question is written instead of a guess.

---

## 1. Current State

| Item | Value | Evidence |
|---|---|---|
| Canonical repository | `ISAAC-DOE/isaac-metadata-assistant`, branch `main` | `git remote -v`; `CLAUDE.md` §11 |
| Reference state for this brief | branch `feat/pre-dean-readiness`, whose base is `f57e239` (merge of PR #24). Three features in §2 — visible scenario labels, the Assistant's "What Can I Ask?" catalog, and Copy Diagnostics — are on this branch and are **not** in `f57e239`; they ship together as one PR whose merge SHA and image tag are not assigned yet. | `git status -sb`; `git log --oneline -5` |
| Container images | `v0.0.25` → `95c1ebe`; `v0.0.26` → `f57e239`. The image for the branch above is not built yet. | release records in `docs/superpowers/plans/` |
| Hosted URL | `https://isaac.slac.stanford.edu/krish` | — |
| Hosted running commit | **Not verified.** The deployment sits behind an Authentik edge this environment cannot authenticate to, so `/krish/api/health` was not read. No hosted SHA is claimed as observed. | `routes.py::_build_commit` (`apps/api/isaac_api/routes.py:452-462`) is what `/api/health` reports (line 485) |
| Runtime data mode | `synthetic-only`, **fail-closed** | `apps/api/isaac_api/runtime_mode.py:43-57` |
| Real mode | Recognised as a value but **refuses to boot** | `runtime_mode.py:83-88` — `RuntimeError` on `ISAAC_RUNTIME_MODE='real'`; called at `apps/api/isaac_api/app.py:48` |
| Real-vs-synthetic detection | **Does not exist anywhere.** The app enforces synthetic *mode*, never the contents of what it is handed. | `runtime_mode.py` in full — no content inspection; stated in `apps/web/src/lib/settingsContent.ts:24-27` (the honesty constraint) and rendered from `settingsContent.ts:122, 125` |
| Persistence | `"ephemeral"` — a fixed, non-configurable literal returned by `/api/about` | `apps/api/isaac_api/routes.py:2868` and the maintainer note at 2854-2855 |
| Workspace location | Default `/tmp/isaac-ui-workspace`, overridable by `ISAAC_UI_WORKSPACE` | `apps/api/isaac_api/workspace.py:70, 79-81` |
| Database | **None.** No database driver or ORM in the dependency set. | `pyproject.toml:10-18` — `jsonschema`, `python-ulid`, `openpyxl`; API extra adds `fastapi`, `uvicorn`, `httpx` |
| Edge authentication | Authentik, in front of the app; not implemented in this repository | no Authentik code in `apps/api/` |
| App-managed identity / roles | **None.** No user model, no roles, no per-user state. | `apps/api/isaac_api/auth.py` is the only auth code: one process-wide bearer secret from `ISAAC_UI_API_KEY`, `secrets.compare_digest`, open only for `GET {base}/api/health` and `OPTIONS` (lines 26-56) |
| Truth core | Deterministic, LLM-free, Graphify-free | `src/isaac_records/{official,draft_validator,export,audit,cli}.py`; enforced by `tests/test_export.py:169` `test_core_never_imports_graphify` and `tests/test_e2e.py:112-116` |
| LLM / model provider | **None.** No LLM client and no outbound HTTP in runtime code. | `grep -rnE "openai\|anthropic\|langchain\|httpx\.post\|requests\.post\|aiohttp" apps/api/isaac_api src/isaac_records` → no matches |
| Assistant | Deterministic, advisory, read-only; a finite eight-intent catalog | `apps/api/isaac_api/assistant_query.py:67-123`; unsupported questions are refused (lines 804-810) |
| Project Memory provenance | Served from two committed artifacts, both built at commit `caab1d0a69c1733524bda5dde495623bc4b7bad1` | `apps/api/isaac_api/data/memory-snapshot.json` (`built_at_commit`); `memory-graph-detail.json` (same) |
| Graph freshness | Structure is a **point-in-time index**, machine-readably disclosed | `apps/api/isaac_api/memory_graph.py:319-320` — `is_point_in_time: true`, `describes_current_head: false` |
| API access | The generated OpenAPI contract is browsable in-app; there is **no** operation that creates, lists, revokes, or rotates a credential | `apps/web/src/screens/settings/ApiKeys.tsx:1-31`; `Settings → Endpoint Explorer` |
| Test suites | On the branch above, re-run 2026-07-28: backend **1375 passed, 0 failed**; frontend **1865 passed / 89 files**; `tsc -b` exit `0`; the committed-snapshot drift check clean for **both** committed artifacts. (For comparison, the base commit `f57e239` was backend **1328** / frontend **1750 in 85 files**.) | `.venv/bin/pytest -q`; `npm test` and `./node_modules/.bin/tsc -b` in `apps/web`; `scripts/build_memory_snapshot.py … --check` |

---

## 2. What Works Today

Each item was verified in code before being listed.

### Five distinct synthetic workflow scenarios

Exactly five canonical records, fixed ids and fixed `created_utc`, spanning all four derived workflow
states. Verified by materialising the seed and reading each record's derived state:

| Id | Scenario label (rendered) | Stored title suffix (stripped on the queue and the record root — see below) | Derived status | Pending | Exported |
|---|---|---|---|---|---|
| `01SYNTHXANESSEED0000000001` | `Scenario 1 · seeded: extraction only` | `· New Draft` | `needs_attention` | 5 | no |
| `01SYNTHXANESSEED0000000002` | `Scenario 2 · seeded: partial answers applied` | `· Partially Completed` | `needs_attention` | 2 | no |
| `01SYNTHXANESSEED0000000003` | `Scenario 3 · seeded: all answers applied` | `· Ready to Export` | `ready_to_export` | 0 | no |
| `01SYNTHXANESSEED0000000004` | `Scenario 4 · seeded: descriptor uncertainty omitted` | `· Export Review Required` | `in_review` | 0 | no |
| `01SYNTHXANESSEED0000000005` | `Scenario 5 · seeded: export run at setup` | `· Exported Record` | `done` | 0 | **yes** |

Definitions at `apps/api/isaac_api/workspace.py:487-492, 561-582`. Every draft is derived from the two
committed synthetic fixtures plus the committed demo answers, through the unchanged truth core — no
invented values (`workspace.py:479-485`). Status is derived, never stored (`workspace.py:400-412`).
Scenario 4 is `in_review` for an honest reason: a descriptor was supplied without its required
`uncertainty`, so the real export dry-run genuinely fails the official schema (`workspace.py:522-532`).

**The two label columns are not interchangeable.** All five records share one scientific title
(`Synthetic XANES — CuO (Cu K-edge)`), so the queue needs something to tell them apart. The **scenario
label** is what the UI actually renders — a quiet secondary line under the title
(`apps/web/src/components/ExperimentRow.tsx:55-65`), served by `routes.py::_summary` (line 397) from
`workspace.py::scenario_label` (595-604). It is derived from the record id at read time and **never
stored**: `Experiment` has no `scenario` field, and the value never reaches a draft, an official record,
an evidence sidecar, or an export. A user-created record has no scenario and renders no line at all.
The label is deliberately **past tense** — it states how the fixture was *materialised* at setup and is
never refreshed, so advancing a record changes its chip and its queue group without falsifying the
label. (An earlier present-tense wording, "Scenario 2 · Partially Confirmed", survived unchanged onto a
fully-confirmed, exported record; that is why the wording is what it is.)

The **stored title suffix** is a backend artifact (`workspace.py:567-581`) that the frontend strips on
the two surfaces where the clean scientific title is the point, and **does not strip elsewhere** — so
"stripped" must be stated per surface, not globally:

- **Stripped.** The My Experiments queue rows (`KNOWN_TITLE_SUFFIXES` / `stripLifecycleSuffix` at
  `apps/web/src/lib/adapt.ts:61-72`, applied inside `toExperimentSummary` at line 93, rendered at
  `ExperimentRow.tsx:54`) and the Record Workbench heading
  (`apps/web/src/screens/RecordWorkbench.tsx:205`).
- **Not stripped, and therefore on screen.** The `TopBar` heading on the three record sub-surfaces —
  Complete (`apps/web/src/screens/GuidedCompletion.tsx:310`), Evidence
  (`apps/web/src/screens/EvidenceExplorer.tsx:135, 188`) and Export Readiness
  (`apps/web/src/screens/ExportReadiness.tsx:358`) — each passes the raw `detail.title` straight from
  `GET /api/experiments/{id}`, which `TopBar` renders as the crumb or the page heading
  (`apps/web/src/components/TopBar.tsx:104-113`). There is no detail-level adapter.
- **Not stripped, and therefore in Assistant output.** A `record_summary` answer echoes the stored
  title verbatim (`apps/api/isaac_api/assistant_query.py:883-893`, fed by `routes.py:388`): asking
  *"Summarize this record."* on scenario 1 returns `This record 'Synthetic XANES — CuO (Cu K-edge) ·
  New Draft' is currently needs attention, …` — verified by calling the route. ⌘K Search carries it
  the same way, as the owning-record context (`apps/api/isaac_api/search.py:276-287`;
  `apps/web/src/components/SearchDialog.tsx:556-558`).

None of that makes the suffix load-bearing: it is display text on a synthetic seed title, it is never
a source of state, and no code parses it back out. But it is **not** invisible, so nothing in a demo
should promise that it is.

Independently of the suffix, the live state is carried by the queue-group heading, the Draft/Exported
lifecycle chip, and — in Needs Attention only — an `N Fields Need You` chip (`adapt.ts:76-84`;
`ExperimentRow.tsx:66-79`).

### Guided metadata completion

`/record/:id/complete`. The five blockers on scenario 1 are three asset `sha256` values, the reduced
spectrum (`measurement.series`), and at least one descriptor — each surfaced as a question, none
guessed. A synthetic demo value may be offered, labelled `Demo answer (synthetic) — not a value until
you confirm`, behind a two-step "use, then Confirm" gate; the assistant never prefills a scientific
value (`apps/web/src/components/GuidedPrompt.tsx:34-41, 87-104, 122`).

### Evidence review

`/record/:id/evidence` — field-by-field trail with source file and locator, a source preview of the
cited synthetic fixture with the cited lines marked, the raw record and sidecar JSON, and a per-field
evidence-support classification over five classes (`supported`, `inferred_candidate`,
`insufficient_evidence`, `conflicting_evidence`, `unknown`) that deliberately carries no validity or
exportability verdict (`apps/api/isaac_api/routes.py:1725-1731, 1744-1746`). Pre-export the trail comes from the
draft envelopes; post-export from the evidence sidecar (`routes.py:1712-1717`).

### Authoritative validation

One implementation, `src/isaac_records/official.py::validate_official`, jsonschema `Draft202012` against
the vendored official schema `schema/isaac_record_v1.json` (v1.05, `additionalProperties: false`
throughout). It backs `isaac validate --official`, the per-record validate route, and the standalone
Validator alike — there is no second verdict path.

### Export readiness and export

Readiness is **fully derived** from current signals — no stored state, no human-review step
(`apps/api/isaac_api/workflow.py:39-69`). Export is doubly gated: the no-guessing draft validator, then
the official schema, in that order, and the record is only written if both pass
(`src/isaac_records/export.py:147-166`). Exported records are immutable — a second export is refused
`409` (`routes.py::post_export` — the immutability guard at `apps/api/isaac_api/routes.py:1206-1216`, documented at 1166-1171), and the CLI refuses to overwrite
(`src/isaac_records/cli.py:78-80`). There is no `--force` and no portal submission.

### Export artifacts

An official record `records/<ULID>.json` plus an evidence sidecar `records/<ULID>.evidence.json`, shown
as two separate artifact cards with JSON view and download. The sidecar is labelled "assistant
convention — not official" in every location it appears. See `docs/evidence-sidecar-audit.md`.

### Assistant

Deterministic and read-only. A question is normalised and matched by explicit lowercase phrase
containment against a **finite eight-intent catalog** — pending fields, export blockers, export
readiness, workflow step, field provenance, evidence for a field, record summary, project-memory leads
(`apps/api/isaac_api/assistant_query.py:67-123`). No learned or scored classifier
(`assistant_query.py:81, 238-242`). Answers are built from structured template fragments and pass a
verdict guard (an answer may never state PASS/FAIL or "valid against") and a path/secret scrub before
return (`assistant_query.py:549-605`). Genuine ambiguity is reported as ambiguous rather than silently
resolved (`assistant_query.py:280-297`). An unmatched question is refused and names what *is* supported
(`assistant_query.py:804-810`). The one action an answer may carry is a bounded in-app navigation to the
Validator, which navigates and nothing else (`assistant_query.py:347-358`).

**The catalog is now stated in the product, per surface.** A compact **What Can I Ask?** disclosure in
the composer dock (`apps/web/src/components/AssistantPanel.tsx`, the `.assistant-capabilities` block)
lists the question families supported *on the current surface*, one or two traced examples each, and the
boundary in the panel itself rather than behind a further disclosure: "These families are the whole set.
Wording is flexible within them; anything outside them is refused, not guessed." Clicking an example
**inserts** its exact text into the composer and does not submit; it also never overwrites a half-typed
question — with a draft present the panel keeps it and says so before the click
(`insertCapabilityExample`; `CAPABILITIES_DRAFT_KEPT_NOTE`).

The scoping is the substantive part. Capability is scope-dependent, so the groups are selected from two
facts the panel already holds — its `queryScope` and whether a `graphCapability` was supplied — and never
inferred from the mounting screen (`capabilityGroupsFor` in
`apps/web/src/lib/assistantCapabilities.ts`). Record surfaces get six headings covering all eight
resolver intents (Workflow and Current Step · Missing Fields and Confirmations · Export Blockers and
Readiness · Evidence and Provenance · Record Summary · Project Memory — `RECORD_CAPABILITY_GROUPS`).
Project Memory gets **only** the Project Memory family, because `queryScope="memory"` routes to
`assistant_query.py::answer_memory_scope`, which refuses every record family — advertising one there
would advertise a refusal (`MEMORY_CAPABILITY_GROUPS`). A Graph Navigation group
appears only while the Graph tab is mounted, because that is the only time the graph interception is
wired (`apps/web/src/screens/ProjectMemory.tsx:159-172`). Two tests hold the claim that every listed
example really routes: `apps/web/src/__tests__/assistant-capabilities.test.tsx` re-reads the resolver's
`_TRIGGERS` out of the Python source, and `apps/api/tests/test_assistant_capabilities_catalog.py`
re-reads the TypeScript catalog and runs the real `classify()` over every example.

### Project Memory

`/memory`, four tabs — Overview, Sources, Concepts, Graph (`apps/web/src/screens/ProjectMemory.tsx:68-75`),
deep-linkable via `?tab=`. Served from a sanitised committed snapshot; 201 served file paths and 19
concepts. Every response carries "Project memory returns leads to verify — never a validation verdict."

### Graph exploration — and its freshness limit

The Graph tab renders a deterministic, capped, served-file reference projection: **220 nodes (201 files
+ 19 concepts) and 508 reference edges**, of which 149 files carry references and 52 are isolated
(verified by invoking `memory_graph.build_graph_projection`). A deeper symbol-level layer (2,612 nodes /
4,067 edges) is available on zoom from `memory-graph-detail.json`.

**The limit, stated plainly:** the structure is an index of commit
`caab1d0a69c1733524bda5dde495623bc4b7bad1`, not of current `main`. Anything added, renamed, or removed
since then is absent — including work in the running build. The app discloses this machine-readably
(`is_point_in_time: true`, `describes_current_head: false` — `memory_graph.py:319-320`), in prose inside
"About This Graph" (`apps/web/src/screens/graph/GraphHelp.tsx:196-210`), and on-surface as a staleness
paragraph once the symbol layer is drawn (`apps/web/src/screens/graph/GraphCanvas.tsx:882-887`).
Structure and served-content freshness are two independent axes and are reported separately
(`memory_graph.py:303-306`).

### Standalone Validator

`/governance?tab=validator`. Paste or upload a candidate JSON record (512 KB bound, enforced
client-side first and again server-side) and get the authoritative official-schema verdict without
adding anything to My Experiments. Validated in memory and discarded; no persistence, no content
logging (`apps/web/src/components/RecordValidator.tsx:9-28`).

### Schema Reference

`/governance?tab=schema`. A browser over the vendored official schema — Fields, Conditional Rules, and
Vocabulary subviews with search and cross-citation (`apps/web/src/components/SchemaBrowser.tsx`).

### API documentation

`/settings?tab=api` (Quick Start and Connect an Agent, derived from the contract rather than asserted)
and `/settings?tab=explorer` (Endpoint Explorer — a master-detail browser over the generated OpenAPI
document: every operation, whether it documents a 401, parameters, request body, responses, error
states, generated code samples, raw JSON behind a disclosure). Paths are always the relative paths the
contract itself declares; no origin or host literal is displayed
(`apps/web/src/screens/settings/ApiDocs.tsx:13-26, 157-208`).

### Session-expiration handling

An expired Authentik session no longer reads as "the backend is down". HTTP 401/403, or an HTML page
returned for an API path, produces an explicit auth state — "The ISAAC API rejected this request as
unauthenticated (HTTP 401). The sign-in session is no longer valid." with "Reload the page to sign in
again." A genuinely ambiguous failure says so rather than picking a cause — the fall-through branch
names both possible causes instead of asserting one (`downCopy` at
`apps/web/src/components/FetchStates.tsx:77-151`; the auth branch at 94-113, the ambiguous branch at
140-150).

### Copy Diagnostics

One pasteable support report, from **one pure generator with two render sites**:
`apps/web/src/lib/diagnostics.ts::buildDiagnosticsReport` (groups at 330-407). It takes every value as
an argument and reads no global, so what it can and cannot emit is a property of a function rather than
of a component's incidental behaviour.

The two mounts are `Settings → About` (`/settings?tab=about`), just below the collapsed Technical
Details disclosure (`apps/web/src/screens/SettingsPage.tsx:573-576`), and — for error states only —
inside the existing Technical Details box of the failure panel
(`apps/web/src/components/FetchStates.tsx:229-239`). Both render the same `CopyDiagnostics` control
(`FetchStates.tsx:284-377`).

Sections: `BUILD` (App Version, Build Commit short + full, Runtime Mode, Data Regime, Persistence,
Record Schema, Deployment, API Base) · `SESSION` (Generated At, Route, Tab, Record Id, Browser,
Viewport, Device Pixel Ratio, Network State) · `PROJECT MEMORY` (Availability, Integrity, Provider,
Source Commit, Snapshot Fingerprint, Policy Fingerprint, Served File Count, Snapshot Schema) ·
`FAILURE SIGNALS` on the error mount only. An unobtainable value renders as the single literal
`not available`, never a zero or a plausible default.

Three properties worth naming, because each is a deliberate refusal:

- **No network, ever.** Generating or copying performs no request and uploads nothing; a test asserts
  `fetch` is never called (`apps/web/src/__tests__/diagnostics.test.tsx:387-399`).
- **No zoom field.** `devicePixelRatio` cannot distinguish a Retina display at 100% from a 1× display at
  200%, and `visualViewport.scale` reports pinch-zoom only. Reporting either as "zoom" would be a
  plausible-looking guess, so the raw `Device Pixel Ratio` is reported under its own honest name instead
  (`diagnostics.ts:38-44`).
- **One `Source Commit`, not two.** `apps/api/isaac_api/memory.py:1055` sets `source_graph_commit` to the
  snapshot's `built_at_commit`, so separate "memory" and "graph" commit rows would be two labels over
  one value.

Privacy is type-enforced rather than filtered: no cookie, token, `Authorization`/`x-api-key` header,
storage content, `VITE_API_KEY`, Assistant transcript, user-entered value or record value can appear,
because nothing is read — every value arrives as a typed argument. The one argument that could carry
arbitrary content is a failing request's signals, and `DiagnosticsFailure` deliberately has **no `body`
field**, so `ApiError.body` (typed `unknown`, populated from a response the app does not control) cannot
be passed on (`diagnostics.ts:18-36, 115-125, 176-184`).

### Also present, worth knowing

- **CSV reconciliation preview** — `POST /api/experiments/{id}/ingestion/csv/preview`, surfaced on the
  Evidence screen. A raw `text/csv` body is read in memory under a hard size limit and reconciled field
  by field against the record's current values. It writes nothing: no draft change, no revision bump, no
  export, no indexing, no retained upload; only outcome metadata is logged, never rows or values. It
  requires the record's current `ETag` and is refused outside synthetic-only mode
  (`apps/api/isaac_api/routes.py:1292-1436`). **This is the closest thing in the build to a data
  ingress, and it is the reason question 2 below matters.**
- **Upload governance seam** — `POST /api/uploads` always refuses; no file is ever sent
  (`apps/api/isaac_api/routes.py:2010-2043`; `apps/web/src/screens/LoadMaterials.tsx:53-62`).
- **Reproducible demo** — `scripts/run_synthetic_demo.py` regenerates the committed sample record
  byte-for-byte (the sidecar differs only in its wall-clock `generated_utc`, by design, lines 23-24).
- **Reset Demo** restores the workspace to exactly the five canonical scenarios, content included
  (`workspace.py::reset_to_canonical_seed` — `apps/api/isaac_api/workspace.py:812-822` states the content guarantee, executed at 844-855).

---

## 3. Current Limitations

**Real mode is intentionally unsupported because real-data ingestion and governance guardrails do not
yet exist.** (`apps/api/isaac_api/runtime_mode.py:20-23, 83-88` — the app refuses to boot in `real`
mode.)

Then:

1. **No content-based real/synthetic classification.** Nothing in the codebase inspects data to decide
   whether it is real or synthetic. The app enforces synthetic *mode*; keeping real artifacts out is an
   operator responsibility, not a software check. The app says so itself
   (`apps/web/src/lib/settingsContent.ts:24-27`, surfaced as copy at 122 and 125).
2. **No approved real-data ingress.** File upload always refuses (`routes.py:2010-2043`). The CSV
   preview path exists but is read-only, non-persisting, and synthetic-mode-gated
   (`routes.py:1292-1436`). No path writes externally-supplied data into a record today.
3. **No durable persistence.** `/api/about` reports `persistence: "ephemeral"`
   (`routes.py:2868`); the workspace defaults to `/tmp/isaac-ui-workspace`
   (`workspace.py:70, 79-81`); there is no database dependency (`pyproject.toml:10-18`). Deployment
   manifests are not in this repository, so durability of the hosted volume is not verifiable from here.
4. **No app-level identity or roles.** The only auth in the app is one deployment-wide bearer secret
   (`apps/api/isaac_api/auth.py:26-56`). It identifies the deployment, not a person. All user identity
   comes from the Authentik edge and is not visible to the app.
5. **No official API-key management.** No operation creates, lists, revokes, or rotates a credential;
   the Create control is genuinely `disabled` with a programmatically associated reason, and no key is
   ever generated or displayed (`apps/web/src/screens/settings/ApiKeys.tsx:1-31, 133-146`).
6. **Evidence-sidecar authority unresolved.** Labelled "assistant convention — not official" everywhere
   (`apps/web/src/lib/labels.ts:217-218`), listed as an open question at `README.md:247`, and carried as
   decision **D1** in `docs/mentor-decisions.md:87` (register) and `96-117` (the section). Full audit: `docs/evidence-sidecar-audit.md`.
7. **One demonstrated domain.** Synthetic XANES / characterization (`record_type=evidence`,
   `record_domain=characterization`). Performance/electrochemistry and simulation/theory paths are out
   of scope (`CLAUDE.md` §15).
8. **The graph is point-in-time and currently stale.** Pinned to `caab1d0a`, which is many commits
   behind `f57e239`. The staleness is disclosed, not hidden — but the graph must never be presented as
   a map of current code (`apps/api/isaac_api/memory_graph.py:295-306, 319-320`).
9. **The existing portal remains necessary.** This prototype reimplements neither the portal's
   soft-warning validation tier (`portal/validation.py`, deliberately not reimplemented —
   `src/isaac_records/official.py:10-12`) nor record submission, nor the ontology/propose-review-approve
   workflow, nor durable storage. Nothing here replaces it.

---

## 4. Questions for Dean

1. Is the evidence sidecar an approved official ISAAC artifact, an interim Assistant convention, or a
   format that should be redesigned?
2. What is the approved real-data ingress path?
3. Where must classification, sanitization, and governance enforcement occur?
4. What failure behavior is required when data cannot be classified?
5. What persistence should hold drafts, confirmations, evidence, exports, and audit events?
6. What is the approved real-record source?
7. What machine/API authentication model should be used?
8. Which existing portal APIs are stable and supported?
9. Which experimental techniques and domains must the first real release support?
10. Which existing portal capabilities must remain live?
11. Who owns production secrets?
12. Who owns any future model-provider account and billing?
13. What is the expected rollout, monitoring, and rollback process?
14. Who owns Kubernetes and infrastructure changes?
15. When should old Vercel/Railway deployments be disabled?
16. Who owns Graphify generation, community labeling, freshness, and approval?

Collaboration features — multi-user review, comments, assignment, shared queues — are **explicitly
deferred** and should not dominate the agenda. They depend on questions 5 and 7 being answered first.

---

## 5. Constraints

These hold regardless of how the questions above are answered.

1. **The truth core stays authoritative.** The vendored official schema
   (`schema/isaac_record_v1.json`), `official.py`, `draft_validator.py`, `export.py`, `audit.py`, and
   `cli.py` decide validity and exportability. They are deterministic, LLM-free, and Graphify-free, and
   the no-Graphify-import rule is enforced by a test. If a graph answer, an assistant answer, or a note
   disagrees with the schema or the validators, the deterministic source wins (`CLAUDE.md` §2, §13).
2. **Project Memory and the Assistant stay advisory.** They return leads to verify, never a verdict.
   They cannot mark a record valid, complete a field, or authorise an export. The Assistant is
   verdict-guarded at the point of composition (`apps/api/isaac_api/assistant_query.py:579-589`).
3. **No guessing.** A value with no evidence stays missing or `needs_confirmation`; it is never
   invented. This applies to scientific values, units, hashes, URIs, paths, uncertainties, QC status,
   and timestamps (`CLAUDE.md` §5, enforced by `src/isaac_records/draft_validator.py`).
4. **No real data before governance approval.** Real mode does not boot; upload refuses. Both stay that
   way until questions 2-4 are answered and the guardrails are built.
5. **No secret in source, prompts, screenshots, or logs.** The API scrubs paths and secret-shaped
   tokens from emitted strings (`assistant_query.py:332-333, 373-402`); artifact responses return
   basenames only, never server paths (`routes.py:1894-1896`); the CSV path logs outcome metadata only,
   never rows, values, or filenames (`routes.py:1421-1422, 1426-1433`).
6. **The existing portal stays live until replacements are verified.** Nothing here is a drop-in
   substitute for any portal capability, and no portal submission path exists in this build.
