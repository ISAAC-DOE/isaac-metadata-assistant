# UI handoff — screen map

> Design handoff, **not** implementation. The screens below describe a future UI over the existing
> deterministic ISAAC core. Content is grounded in the real artifact shapes in
> [`../samples/`](../samples/) (record + evidence sidecar) — open both files when designing the
> viewers. Companion docs: [`user-workflows.md`](user-workflows.md),
> [`design-system.md`](design-system.md), [`ai-assistant-and-graphify.md`](ai-assistant-and-graphify.md).

## Core metaphor and the suggested layout — verdict

**Core metaphor: a scientific record workbench.** Not a chatbot, not a generic admin dashboard.
The operator is bench-side, assembling one verifiable record from evidence, with a deterministic
inspector that gives a hard pass/fail. Adopt this metaphor; it is correct for the product.

**Suggested layout — recommended with one refinement:**

- **Left rail = workflow steps** (draft → complete → export → validate → audit). Good: the pipeline
  is inherently linear and gated. Use it as a **progress spine**, not just navigation — show which
  gate is currently blocking.
- **Main canvas = current artifact** (draft, record, or sidecar). Good: the artifact is the
  subject; keep it dominant.
- **Right panel = evidence + assistant/memory.** **Refinement:** split this. Evidence is
  deterministic truth and belongs visually with the artifact; the assistant/memory is advisory and
  must read as subordinate. Stack them (evidence on top, assistant below) or tab them, but never let
  assistant styling bleed into evidence. See [`design-system.md`](design-system.md).
- **Status bar = validation / audit / warning state.** Strongly recommended. This is the trust
  readout: a hard verdict (PASS/FAIL), a coverage figure (`evidence N/N`), and an advisory count —
  three visually distinct families, never collapsed into one badge.

This layout holds for the artifact-centric screens (Draft review, Record/sidecar viewer, Validation
& audit). Home, Governance, and Settings are full-canvas and do not need the rail/panel split.

---

## 1. Home / project dashboard

- **Purpose:** orient the operator, surface records + drafts, launch the safe synthetic demo.
- **Primary actions:** run synthetic demo; open a draft; open a record; ask project memory; open
  governance/safety.
- **Key content:** demo card (labeled **synthetic / safe / fake**); list of records under
  `records/` with ULID, `record_domain`, verdict + `evidence N/N`; list of drafts with blocker
  counts. Grounded in `isaac audit` output and the record top-level fields
  (`record_id`, `record_domain`, `source_type`).
- **States:** has records / drafts-only / demo-only.
- **Empty/loading/error:** empty repo → prompt to run the synthetic demo; loading → skeleton list;
  audit unavailable → show records without verdicts and say verdicts are pending a run.
- **Do NOT show:** aggregate "health scores", trend charts, or a validity count that wasn't produced
  by `isaac audit` / `isaac validate`. No invented KPIs.
- **Sources:** [`../operator-playbook.md`](../operator-playbook.md), `src/isaac_records/audit.py`.

## 2. Demo runner

- **Purpose:** run the full synthetic pipeline end to end as the reference happy path.
- **Primary actions:** run demo; step through draft → blockers → completion → export → validate →
  audit → warnings; open resulting artifacts.
- **Key content:** the fixed synthetic story — 26 evidenced fields, the **5** blockers, PASS v1.05,
  `evidence 26/26`, exactly **1** advisory warning (`[NO_LINKS]`). Wraps
  `scripts/run_synthetic_demo.py`; outputs land under a demo dir (e.g. `/tmp/isaac-demo/`).
- **States:** idle / running each stage / complete.
- **Empty/loading/error:** per-stage progress must reflect the **real** command that ran — no faked
  progress bar. If a stage errors, stop and show the actual output.
- **Do NOT show:** any implication the demo used real data, or that the demo proves real-data
  readiness. It proves the pipeline shape on synthetic input only.
- **Sources:** [`../demo.md`](../demo.md), [`../demo-script.md`](../demo-script.md).

## 3. File intake / upload (FUTURE — gated placeholder)

- **Purpose:** placeholder for future structured-file intake. Clearly marked **future / not
  production-ready**.
- **Primary actions (future):** select synthetic / local structured files (`.csv` / `.xlsx`,
  archive listings); trigger extraction.
- **Key content:** a persistent banner — real / private experiment data is **not** supported and
  needs explicit written approval; only structured local parsing exists
  (`extract/structured.py`, `extract/file_listing.py`). Unstructured extraction is designed, not
  built.
- **States:** disabled-by-default / synthetic-enabled / governance-blocked.
- **Empty/loading/error:** empty → explain what structured formats are accepted; a real-looking file
  → route to the governance screen (#11), not to extraction.
- **Do NOT show:** drag-and-drop-any-file affordances, "AI will read your lab notebook" claims,
  progress on parsing formats that aren't supported. No overclaim about extraction breadth.
- **Sources:** [`../operator-playbook.md`](../operator-playbook.md) §10,
  [`../architecture.md`](../architecture.md) (Not built yet).

## 4. Draft review

- **Purpose:** review the evidence-tagged draft before completion/export.
- **Primary actions:** inspect each field; expand evidence; jump to blockers; proceed to complete.
- **Key content:** fields in the envelope shape `{value, status, evidence[]}`. Status chips:
  **verified** (value in a source), **inferred** (derivation rule), **needs_confirmation** (won't
  export), **missing** (value null). Each field shows citations, e.g. `source_type: spreadsheet`,
  `source_file: mock_campaign.csv`, `locator: Sheet 'Sample', field=formula`, `quote: CuO2`. Show
  `implicit[]` inferences (e.g. `absorbing_element = Cu`) and the `pending[]` blocker list.
- **States:** clean draft / has needs_confirmation / has blockers.
- **Empty/loading/error:** no draft → route to intake/demo; malformed draft JSON → surface the parse
  error, do not partially render as if valid.
- **Do NOT show:** a field value without its evidence; a "confidence %" the system does not compute;
  any auto-filled scientific value. A missing field must look honestly missing, not blank-by-error.
- **Sources:** `.claude/skills/isaac-draft/SKILL.md`, `src/isaac_records/extract/draft_builder.py`,
  `src/isaac_records/models.py`.

## 5. Missing fields / completion

- **Purpose:** resolve exactly the blockers that stop export — nothing optional.
- **Primary actions:** answer each `pending[]` blocker; choose enum values; answer "I don't know".
- **Key content:** one question per blocker, verbatim from `draft["pending"]`. In the synthetic
  demo: three asset sha256 questions, the `measurement.series` pointer, and one descriptor
  (inflection-point energy + uncertainty); plus the implicit `edge` confirmation. Enum fields render
  allowed values straight from `schema/isaac_record_v1.json`.
- **States:** N blockers open / partially answered / 0 remaining ("ready to export").
- **Empty/loading/error:** 0 blockers → confirm ready and route to export; an answer outside an enum
  → reject with the allowed values, since it cannot become a valid record.
- **Do NOT show:** pre-filled "suggested" scientific values presented as answers; any path that lets
  the system supply a sha256 / number / URI. "I don't know" must be a safe, honest, non-penalized
  choice. Do not ask optional (non-blocking) questions here.
- **Sources:** `.claude/skills/isaac-complete/SKILL.md`, `src/isaac_records/complete.py`
  (`apply_answers`).

## 6. Evidence sidecar viewer

- **Purpose:** show the provenance trail preserved outside the schema-clean record.
- **Primary actions:** browse evidence by JSON-path; trace a record field to its source; inspect
  asset / descriptor / implicit evidence.
- **Key content:** the sidecar shape — top-level `record_id`, `schema_version`, `generated_utc`, and
  `evidence{}`. Two key families: **dotted JSON-paths** (26 direct field entries, e.g.
  `system.facility.beamline`) each with `{source_type, source_file, locator, quote}`; and
  **namespaced keys** — `assets:processing_notebook` (a `file_listing` entry **plus** a
  `user_confirmation` sha256), `descriptors:xanes_inflection_point_energy` (`user_confirmation`),
  `implicit:absorbing_element` / `implicit:edge` (a `{value, evidence[]}` object combining
  `derivation` and, for `edge`, `user_confirmation`). Distinguish evidence source types visually:
  `spreadsheet`, `file_listing`, `derivation`, `user_confirmation`.
- **States:** all-resolved / has dangling path (surfaced by audit).
- **Empty/loading/error:** no sidecar → the record predates or lost its sidecar; say so, don't
  fabricate evidence.
- **Do NOT show:** the sidecar as an official ISAAC artifact — label it an **assistant convention**.
  Do not imply the record itself carries per-field provenance (the schema forbids extra keys).
- **Sources:** [`../sample-record-walkthrough.md`](../sample-record-walkthrough.md),
  `src/isaac_records/export.py` (`build_sidecar`), [`../samples/`](../samples/).

## 7. Validation & audit results

- **Purpose:** the trust readout — the hard verdict plus evidence coverage.
- **Primary actions:** run validate (draft or official); run audit; read the exact findings.
- **Key content:** two visually distinct families:
  - **Validation (hard gate):** `PASS` / `FAIL` against official ISAAC v1.05 (`isaac validate
    --official`, `official.py`). This is the same gate that decides export. On FAIL, list the exact
    schema errors.
  - **Audit (coverage):** `evidence N/N` and `0 schema errors` per record (`isaac audit`,
    `audit.py`) — re-validation plus sidecar path resolution. In the sample: `evidence 26/26` (the
    26 direct paths; the 6 namespaced keys are not counted by coverage).
- **States:** PASS+covered / PASS+dangling-evidence / FAIL.
- **Empty/loading/error:** not yet run → prompt to run, don't show a stale verdict as current.
- **Do NOT show:** audit coverage styled like a validity verdict, or a warning styled like a FAIL.
  Coverage is not a re-vote on validity. Do not present a green check without the command behind it.
- **Sources:** [`../cli.md`](../cli.md), `src/isaac_records/official.py`, `src/isaac_records/audit.py`.

## 8. Advisory warnings

- **Purpose:** show non-gating soft-warnings from the local heuristic seam.
- **Primary actions:** view `--warnings` output; read what each code means.
- **Key content:** `⚠ [CODE]` chips. Implemented checks: `[NO_LINKS]` (no optional `links` block)
  and `[QC_NONVALID_WITHOUT_EVIDENCE]`. The sample triggers exactly `[NO_LINKS]`. Verdict stays PASS,
  exit code stays `0`.
- **States:** no warnings / one or more warnings.
- **Empty/loading/error:** no warnings → do **not** present as "portal-approved"; it only means the
  local heuristics didn't fire.
- **Do NOT show:** warnings as validity failures; a warning count in the same visual family as the
  hard verdict; any claim of upstream portal parity — the real `portal/validation.py` is not
  vendored here.
- **Sources:** [`../portal-warnings.md`](../portal-warnings.md),
  `src/isaac_records/portal_warnings.py`.

## 9. Graphify / project-memory assistant panel

- **Purpose:** navigation and memory over the project — never validation.
- **Primary actions:** ask navigation / relationship / "which files implement X" questions; follow a
  citation to the real file.
- **Key content:** answers with an explicit **"answered from"** label (schema / audit / git / graph
  / files); a **freshness indicator** (`fresh` / `stale` / `missing`, exit `0` / `1` / `2` from
  `scripts/check_graphify_freshness.py`); grounded prompt chips from
  [`../query-cookbook.md`](../query-cookbook.md).
- **States:** graph fresh / stale / missing / CLI erroring.
- **Empty/loading/error:** stale or missing → answer from files and disclose it; never fabricate a
  graph node or edge.
- **Do NOT show:** Graphify deciding validity, completeness, a missing value, or vocabulary; graph
  output presented as authoritative without opening the cited source.
- **Sources:** [`../graphify-workflow.md`](../graphify-workflow.md),
  [`ai-assistant-and-graphify.md`](ai-assistant-and-graphify.md).

## 10. Export / download

- **Purpose:** finalize a draft into an official record + sidecar, and expose the artifacts.
- **Primary actions:** export; view/download the record; view/download the sidecar; optionally
  commit.
- **Key content:** two separate artifact cards — **record** (`records/<ULID>.json`, schema-clean,
  official v1.05) and **sidecar** (`records/<ULID>.evidence.json`, assistant convention). Export is
  doubly gated; success shows PASS + both paths. Wraps `isaac export` (`export.py`).
- **States:** exportable (0 blockers) / blocked / already-exported (immutable).
- **Empty/loading/error:** blocked (exit 1) → route back (draft failure → completion; mapping
  failure → fix field paths); record already exists → export is refused, not overwritten.
- **Do NOT show:** an "export anyway" / "force" affordance (there is none); a hand-edit control for
  records under `records/`; the sidecar branded as an official standard.
- **Sources:** [`../cli.md`](../cli.md), `.claude/skills/isaac-export/SKILL.md`,
  `src/isaac_records/export.py`.

## 11. Data-governance / safety

- **Purpose:** enforce that real / private data is not processed, and explain why.
- **Primary actions:** read the policy; acknowledge synthetic-only mode; request-approval flow
  (future).
- **Key content:** clear statement that real SLAC/SSRL/private artifacts, private spreadsheets,
  PDFs, screenshots, and raw data must not be uploaded; synthetic fixtures are unmistakably fake;
  approval is human and written.
- **States:** synthetic-only (default) / approval-pending (future) / blocked-upload intercept.
- **Empty/loading/error:** a real-looking upload → intercept, explain, send nothing to any model or
  index.
- **Do NOT show:** any "proceed with real data" shortcut, or language implying the tool is cleared
  for production experiment data.
- **Sources:** [`../operator-playbook.md`](../operator-playbook.md) §10, project `CLAUDE.md` §6.

## 12. Settings / local configuration (minimal)

- **Purpose:** minimal local config — repo root, records dir, demo dir.
- **Primary actions:** set `--root`, records directory, demo output location.
- **Key content:** paths mirroring CLI flags (`--root`, `--records-dir`). Keep it small.
- **States:** default / customized.
- **Empty/loading/error:** invalid path → validate and explain; never silently write elsewhere.
- **Do NOT show:** model keys, cloud toggles, or anything implying remote/real-data operation.
- **Sources:** [`../cli.md`](../cli.md).

## 13. Developer / diagnostics (hidden / advanced)

- **Purpose:** advanced surface for raw CLI output, exit codes, freshness checks, test status.
- **Primary actions:** view raw `isaac …` stdout/exit codes; run freshness helper; view audit
  details.
- **Key content:** exit-code semantics (validate/export/audit `0/1/2`), freshness helper output,
  raw JSON. Hidden behind an advanced toggle.
- **States:** collapsed by default.
- **Empty/loading/error:** show real command output verbatim; never synthesize a result.
- **Do NOT show:** anything that lets a diagnostic action mutate a record or bypass a gate.
- **Sources:** [`../cli.md`](../cli.md), [`../graphify-workflow.md`](../graphify-workflow.md).

---

## Screen → workflow map

Which screens each workflow in [`user-workflows.md`](user-workflows.md) touches, in order:

| Workflow | Screens, in order |
|---|---|
| A — Synthetic demo | Home (1) → Demo runner (2) → Draft review (4) → Completion (5) → Export (10) → Sidecar (6) → Validation & audit (7) → Warnings (8) → Assistant/memory (9) |
| B — Upload (future) | Home (1) → Governance (11) → Intake (3) → Draft review (4) → Completion (5) → Validation & audit (7) → Export (10) |
| C — Claude-assisted | Any artifact screen (4/6/7/10) with Assistant/memory (9) alongside |
| D — Errors / governance | Validation & audit (7), Warnings (8), Assistant/memory (9, stale/missing), Governance (11) |

## Navigation model

- The **left-rail spine** follows the pipeline gate order: Draft → Complete → Export → Validate →
  Audit. A step is reachable only when its predecessor's gate allows it (you cannot export with open
  blockers). The rail should show the **current blocking gate**, not just the current page.
- **Home (1)**, **Governance (11)**, and **Settings (12)** sit outside the spine as full-canvas
  destinations. **Diagnostics (13)** is a hidden advanced surface.
- The **status bar** persists across the artifact screens (4/6/7/8/10) so the verdict / coverage /
  advisory readout is always visible while working on a record.
- Forward motion is **earned by resolving gates**, never by dismissing them. There is no "skip
  validation" or "export anyway" path anywhere in the navigation.

## Loading, latency, and offline behavior

- The backend is a **local deterministic CLI** (`isaac …`) plus stdlib helpers — operations are fast
  and fully offline. Loading states should be brief and honest; they reflect a real command running,
  never a decorative delay.
- Long content (measurement `values[]`, full sha256 hashes, raw JSON) renders progressively inside
  scrollable containers rather than blocking the screen.
- No network dependency for truth: validation, export, and audit run locally. The assistant/memory
  panel may be unavailable (Graphify missing/stale) without affecting any deterministic screen —
  those screens must remain fully functional when the memory layer is down.
- Every stage indicator on the Demo runner (#2) and Export (#10) maps to an actual command result;
  never advance a progress indicator past a step whose command hasn't returned.

## Cross-screen rules

- Every displayed value is traceable to evidence or a CLI result. If it isn't, it isn't shown.
- Three verdict families stay visually distinct everywhere: **hard gate** (PASS/FAIL), **coverage**
  (`evidence N/N`), **advisory** (`⚠ [CODE]`). Never merge them into one badge.
- Assistant / memory content is always visually subordinate and labeled as explanation.
- Synthetic content is always labeled synthetic. Real-data affordances do not exist in this UI yet.
