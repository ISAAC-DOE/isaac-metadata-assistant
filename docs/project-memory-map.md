# Project memory map

A human-readable **semantic anchor** for the ISAAC Metadata Assistant: it maps the
project's major concepts to the actual files, docs, and commands that define them. Use it
to orient yourself in the repo, and use it as a stable landmark for the Graphify memory
plane (so "where does X live?" has one canonical answer to check against).

This is a **map, not an authority**. When a concept has a deterministic source (the schema,
`isaac validate`, `isaac audit`), that source decides the truth — this page only tells you
where it lives. If this map and a deterministic check ever disagree, the check wins and this
page is stale.

For the narrative pipeline see [`architecture.md`](architecture.md); for the CLI see
[`cli.md`](cli.md); for the top-level overview see [`../README.md`](../README.md).

---

## Project purpose

Turn scattered experiment metadata (structured campaign sheets, archive file listings, and —
by design, not yet built — screenshots/PDFs/notes) into **official, evidence-grounded ISAAC
v1.05 records**, while refusing to guess any unsupported scientific value. The official ISAAC
standard is the source of truth; this repo is an **extraction → draft → export** assistant on
top of it, plus a separate evidence sidecar that preserves per-field provenance the official
record format has no room for.

Scope today: a single characterization / XANES-family path, **synthetic data only**.

---

## The four layers

The system is organized into four layers. Keep this vocabulary consistent — the rest of this
map and the other docs use it.

| Layer | What it decides | Made of | Determines truth? |
|---|---|---|---|
| **Deterministic truth plane** | validity, exportability, record shape, audit result | `schema/isaac_record_v1.json`, `official.py`, `draft_validator.py`, `export.py`, `audit.py`, `cli.py`, plus `models.py` / `ids.py` / `extract/` | **Yes — only this plane** |
| **Advisory warning layer** | nothing; surfaces soft "you may want to look" notes | `portal_warnings.py` (`isaac validate --warnings`); `review.py` is a placeholder | No — non-gating |
| **Graphify memory / query layer** | nothing; helps *find / explain / connect* concepts | Graphify (`graphify-out/`, gitignored), the docs, the evidence sidecars | No — leads, never truth |
| **Claude assistant / operator layer** | nothing on its own; guides a human through the CLI | five `.claude/skills/isaac-*` skills | No — authoring UX only |

### Deterministic truth plane

Graphify-free and LLM-free by construction. It parses inputs, builds the evidenced draft, runs
the no-guessing checks, transforms to the official shape, validates against the vendored schema,
and audits. The "never imports Graphify" guarantee is enforced by the test
`test_core_never_imports_graphify` in `tests/test_export.py`. Same input → same answer.

### Advisory warning layer

A small, clearly-labelled **non-gating** seam that emits portal-style soft-warnings and never
changes what counts as valid and never blocks export. It is **not** upstream portal parity — the
real `portal/validation.py` is not vendored. The truth path does not import it (enforced by
`test_truth_path_does_not_import_portal_warnings` in `tests/test_portal_warnings.py`). See
[`portal-warnings.md`](portal-warnings.md).

### Graphify memory / query layer

An optional knowledge graph built from this repo's own files. It returns **leads with source
locations** (`src=<file> loc=L<line>`), not synthesized prose and not verdicts. It helps with
navigation ("where is this?"), relationships ("what connects to this?"), and "what changed?"
context. It **never** validates a record, fills a missing scientific value, or authorizes export.
The pipeline runs correctly with Graphify entirely absent. Deep-dive:
[`graphify-workflow.md`](graphify-workflow.md) and [`query-demo.md`](query-demo.md); routed
question patterns: [`query-cookbook.md`](query-cookbook.md).

### Project Memory (Phase 24 UI + API)

A read-only browsing surface over this same Graphify layer: four `GET /api/memory/*` endpoints
(`apps/api/isaac_api/memory.py`, routed in `apps/api/isaac_api/routes.py`) plus additive fields on
`GET /api/graph/status`, and the `ProjectMemory` screen
(`apps/web/src/screens/ProjectMemory.tsx`) — a status card, a Source Index, and Concept Lookup.
Explicitly **metadata-only**: no file contents are ever served, and there is no search box.

Guardrails:

- **Served allowlist** — the graph manifest minus `examples/**`, `.superpowers/**`,
  `apps/web/.vercel/**`, `.claude/settings.local.json`, and binaries (`.png`); only files on this
  allowlist are ever named or shown as provenance.
- **Path guard** — `GET /api/memory/file` classifies the requested path before anything else:
  segment-based `..` rejection (`".." in path.split("/")`, so a benign filename such as
  `my..note.md` isn't mistaken for traversal) returns `400 unsafe_source_path`; anything else must
  match an **exact** allowlist key or it is `404 source_not_indexed` — there is no partial/fuzzy
  serving path.
- **Honest degraded states** — a missing or unreadable `graph.json` renders `available: false` with
  a stated reason, never a fabricated empty success; a malformed manifest/labels file alone doesn't
  take the plane down, it just degrades to empty served names. `/api/graph/status` and the
  `/api/memory/*` endpoints resolve one reader per request, so status and counts always describe the
  same graph.
- **Hosted = honest-unavailable-for-now** — the hosted demo deployment ships without graph artifacts
  at all, so Project Memory shows an explicit unavailable panel there instead of an empty or
  misleading one. The documented future-wiring path is a sanitized snapshot, a db-backed index, or
  an institution-hosted service behind login — none built yet.
- **Never a validator** — every response carries `plane: "memory"` and a note that this plane
  returns leads to verify, never a validation verdict; it cannot authorize export.

Current real-data state: 19 curated concepts exist, and today all 19 have zero recorded edges in
the graph — Concept Lookup's related-leads panel is honestly empty for every concept rather than
implying connections that aren't there.

### Claude assistant / operator layer

Five slash skills — `/isaac-draft`, `/isaac-complete`, `/isaac-validate`, `/isaac-query`,
`/isaac-export` — that script a human through the deterministic CLI. They are an authoring UX;
they never invent values and never override the CLI. See [`claude-workflow.md`](claude-workflow.md).

---

## End-to-end pipeline

```
synthetic metadata ──▶ evidence-grounded draft ──▶ missing-field blockers
   (structured sheet,     (draft_builder.py:            (pending[]: sha256s,
    file listing)          fields + implicit +           series, descriptor —
                           pending)                       never guessed)
        │                                                       │
        ▼                                            human-confirmed answers
 no-guessing validation                              (complete.py: apply_answers,
 (draft_validator.py)                                 each as user_confirmation)
                                                            │
                                                            ▼
                                    schema-gated export (export.py)
                                    ├─▶ official ISAAC v1.05 record  (records/<ULID>.json)
                                    └─▶ evidence sidecar             (records/<ULID>.evidence.json)
                                                            │
                          ┌─────────────────────────────────┼───────────────────────────┐
                          ▼                                  ▼                            ▼
                 official schema validation          evidence audit          optional advisory warnings
                 (official.py)                        (audit.py)              (portal_warnings.py, non-gating)
```

Optional add-ons that sit *beside* this pipeline, never inside it: the Graphify memory/query
layer and the Claude assistant skills.

---

## Concept → source

The primary anchor. Every path below has been confirmed to exist in the repo.

| Concept | Source(s) |
|---|---|
| Project overview / status | [`../README.md`](../README.md) |
| Pipeline + module map | [`architecture.md`](architecture.md) |
| **Official schema (authority)** | `schema/isaac_record_v1.json` |
| Schema provenance / refresh | `schema/PROVENANCE.md` |
| Draft (envelope) format | `schema/isaac_draft.schema.json`, `src/isaac_records/models.py` |
| Descriptor class vocabulary | `vocabulary/descriptor_class.json` |
| Deterministic extractors | `src/isaac_records/extract/structured.py`, `src/isaac_records/extract/file_listing.py` |
| Draft builder | `src/isaac_records/extract/draft_builder.py` |
| Completion answers | `src/isaac_records/complete.py` |
| Export (draft → record + sidecar) | `src/isaac_records/export.py` |
| Official validation | `src/isaac_records/official.py` (+ [`cli.md`](cli.md)) |
| Draft (no-guessing) validation | `src/isaac_records/draft_validator.py` |
| Evidence audit | `src/isaac_records/audit.py` (+ [`cli.md`](cli.md)) |
| Evidence sidecar | `src/isaac_records/export.py` (`build_sidecar`), [`architecture.md`](architecture.md) "Why the sidecar exists" |
| ULID record ids | `src/isaac_records/ids.py` |
| `isaac` CLI | `src/isaac_records/cli.py`, [`cli.md`](cli.md) |
| Portal-style advisory warnings | `src/isaac_records/portal_warnings.py`, [`portal-warnings.md`](portal-warnings.md) |
| Advisory AI review (placeholder) | `src/isaac_records/review.py` |
| Graphify workflow | [`graphify-workflow.md`](graphify-workflow.md), [`query-demo.md`](query-demo.md) |
| Project Memory API (read-only) | `apps/api/isaac_api/memory.py`, `apps/api/isaac_api/routes.py` (`/api/memory/*`, `/api/graph/status`) |
| Project Memory UI | `apps/web/src/screens/ProjectMemory.tsx`, [`ui-local-dev.md`](ui-local-dev.md) "Project Memory (Phase 24)" |
| Query routing / cookbook | [`query-cookbook.md`](query-cookbook.md), `.claude/skills/isaac-query/SKILL.md` |
| Claude skills | `.claude/skills/isaac-draft/SKILL.md`, `isaac-complete/`, `isaac-validate/`, `isaac-query/`, `isaac-export/SKILL.md`; [`claude-workflow.md`](claude-workflow.md) |
| Synthetic XANES demo | `scripts/run_synthetic_demo.py`, [`demo.md`](demo.md) |
| Synthetic input fixtures | `tests/fixtures/synthetic/` |
| Committed sample record | `docs/samples/01JQZ0SYNTHXANESDEMO000000.json`, [`sample-record-walkthrough.md`](sample-record-walkthrough.md) |
| Committed evidence sidecar | `docs/samples/01JQZ0SYNTHXANESDEMO000000.evidence.json` |
| Official golden records | `tests/fixtures/official/` |
| Tests | `tests/` (`test_export.py`, `test_official.py`, `test_portal_warnings.py`, `test_e2e.py`, …) |
| Data governance | [`data-governance.md`](data-governance.md), [`intake.md`](intake.md) |
| Mentor decisions | [`mentor-decisions.md`](mentor-decisions.md), [`mentor-brief.md`](mentor-brief.md) |
| Extraction strategy (future) | [`extraction.md`](extraction.md) |
| Migration note (old provisional schema) | [`proposal-v2.md`](proposal-v2.md) |
| Contributor / security policy | [`../CONTRIBUTING.md`](../CONTRIBUTING.md), [`../SECURITY.md`](../SECURITY.md) |

---

## Official schema and provenance

`schema/isaac_record_v1.json` is the vendored **official ISAAC v1.05** schema, copied verbatim
from the [upstream standard](https://github.com/ISAAC-DOE/isaac-ai-ready-record) and not ours to
edit. Provenance and the refresh procedure are in `schema/PROVENANCE.md`. The pinned version const
is `EXPECTED_VERSION = "1.05"` in `src/isaac_records/official.py`. The schema is
`additionalProperties: false` throughout, so plain JSON-Schema validation already covers every
hard rule the official portal enforces (unknown blocks, bad vocabulary, anti-pattern descriptor
names, conditional required fields).

## Draft building

`src/isaac_records/extract/draft_builder.py` assembles the draft envelope from the deterministic
extractors (`structured.py` for the sheet, `file_listing.py` for the archive listing). A draft
holds `fields{path: {value, unit?, status, evidence[]}}`, `implicit[]` candidates (absorbing
element, edge), and `pending[]` blockers for anything unsupported. The draft (envelope) format is
`schema/isaac_draft.schema.json` — **ours, not an ISAAC record**.

## Completion answers

`src/isaac_records/complete.py` (`apply_answers`) fills `pending[]` blockers from human-supplied
answers, recording each as `user_confirmation` evidence. It never invents a value; an unanswered
blocker stays open. In the demo the answers come from the fixture
`tests/fixtures/synthetic/xanes_completion_answers.json`; in real use they come through
`/isaac-complete`.

## Export

`src/isaac_records/export.py` (`export_draft`) is **doubly gated**: it runs the no-guessing draft
checks *and* validates the transformed record against the official schema, and writes nothing
unless both pass (no `--force`). It produces two files: the official record and the evidence
sidecar. Records are immutable via the CLI (re-export from the draft; do not hand-edit
`records/`).

## Validation

Two deterministic validators plus staged advisory tiers:

1. **Draft no-guessing validation** — `src/isaac_records/draft_validator.py`; gates authoring.
2. **Official ISAAC schema validation** — `src/isaac_records/official.py`; gates export. This is
   the hard authority.
3. **Portal-style advisory warnings** — `src/isaac_records/portal_warnings.py`; non-gating.
4. **AI scientific consistency review** — `src/isaac_records/review.py`; a placeholder, not
   implemented.
5. **Human review** — the decider for anything flagged.

Run it via `isaac validate <target> [--draft|--official] [--warnings]` — see [`cli.md`](cli.md).

## Evidence audit

`src/isaac_records/audit.py` re-validates every record in a directory against the official schema
**and** reports evidence-sidecar coverage. Since Phase 21 the denominator is enumerated from the
**record's own content** — every scalar leaf plus one block target per series / QC verdict / link /
asset / descriptor / contributor (only `implicit:` keys stay informational and are never counted) —
not from whatever keys happen to be in the sidecar, so an unevidenced spectrum or QC verdict shows up
as `uncovered` instead of silently passing. A clean audit on the committed sample reads
`evidence 33/33` (0 dangling). See `isaac audit` in [`cli.md`](cli.md).

## Evidence sidecar

The official record schema is `additionalProperties: false` and has no per-field provenance slot,
so evidence is preserved in a separate `records/<ULID>.evidence.json` sidecar keyed by official
JSON-path (plus `assets:` / `descriptors:` / `implicit:` for structured blocks). The record stays
schema-clean; auditability survives export. Built by `export.py` (`build_sidecar`); explained in
[`architecture.md`](architecture.md) "Why the sidecar exists". Whether it becomes an official ISAAC
convention is an open mentor decision (D1 in [`mentor-decisions.md`](mentor-decisions.md)).

## Portal-style warnings

`src/isaac_records/portal_warnings.py` emits two schema-grounded **local heuristics**
(`NO_LINKS`, `QC_NONVALID_WITHOUT_EVIDENCE`), surfaced by `isaac validate --official --warnings`.
They are read-only, carry no validity verdict, never gate export, and are **not** the upstream
`portal/validation.py` rule set (that file is not vendored). Full detail and limits:
[`portal-warnings.md`](portal-warnings.md).

## Synthetic XANES demo

`scripts/run_synthetic_demo.py` runs the real pipeline end-to-end on committed synthetic fixtures
(a deliberately fake year-2099 SSRL session) and regenerates the committed sample record
byte-for-byte. It is a demo-only driver — it adds no schema/validation/export logic of its own and
imports nothing from the Graphify plane. Narrative + expected output: [`demo.md`](demo.md). The
resulting artifacts are walked through field-by-field in
[`sample-record-walkthrough.md`](sample-record-walkthrough.md).

## CLI commands

The deterministic `isaac` CLI (`src/isaac_records/cli.py`), documented in [`cli.md`](cli.md):

| Command | Purpose |
|---|---|
| `isaac validate <target>` | Draft no-guessing checks, or official-schema validation (`--warnings` adds non-gating advisory soft-warnings) |
| `isaac export <draft>` | Transform draft → official record + evidence sidecar (doubly gated) |
| `isaac audit` | Validate every record in `records/` against the official schema + report sidecar coverage |
| `isaac new-id` | Print a fresh ULID `record_id` |

`validate` / `export` / `audit` are LLM-free and Graphify-free.

---

## Docs map

| Doc | For |
|---|---|
| [`../README.md`](../README.md) | Top-level overview, status, quickstart |
| [`mentor-brief.md`](mentor-brief.md) | Five-minute review brief — start here for review |
| [`mentor-decisions.md`](mentor-decisions.md) | Detailed open-decision register (D1–D8) |
| [`demo-script.md`](demo-script.md) | Live-meeting demo script |
| [`demo.md`](demo.md) | Reproducible synthetic demo — commands + expected output |
| [`sample-record-walkthrough.md`](sample-record-walkthrough.md) | Field-by-field tour of the committed sample + sidecar |
| [`architecture.md`](architecture.md) | Pipeline + module map |
| [`cli.md`](cli.md) | Full `isaac` CLI reference |
| [`claude-workflow.md`](claude-workflow.md) | The five slash skills as a scripted conversation |
| [`query-demo.md`](query-demo.md) | Graphify memory/query reviewer demo |
| [`graphify-workflow.md`](graphify-workflow.md) | Graphify workflow (build/query/refresh, leads vs. truth) |
| [`query-cookbook.md`](query-cookbook.md) | Routed question patterns (which source owns which question) |
| [`query-safety-checklist.md`](query-safety-checklist.md) | One-screen query-safety checklist (graceful degradation, truth routing) |
| [`portal-warnings.md`](portal-warnings.md) | Non-gating advisory soft-warning seam |
| [`data-governance.md`](data-governance.md) | Synthetic vs. real data rules, LLM-on-real-data policy |
| [`intake.md`](intake.md) · [`extraction.md`](extraction.md) | Intake plan · extraction strategy |
| [`paper-notes.md`](paper-notes.md) | Motivation / methods / results notes |
| [`final-deliverable-outline.md`](final-deliverable-outline.md) | Paper/poster/report outline |
| [`proposal-v2.md`](proposal-v2.md) | Proposal + migration note (old provisional schema) |
| [`github-settings.md`](github-settings.md) | Suggested GitHub repo settings |

---

## Data governance

**Synthetic-only by default; never commit real or private data.** The committed demo data is
deliberately fake. Real SLAC/SSRL artifacts, private spreadsheets, screenshots, PDFs, raw data,
and raw file listings are gitignored (`examples/`) and stay local. `graphify-out/` is derived and
is never committed. Sending real artifacts to an LLM (including Claude) is not allowed by default —
real or sanitized data requires explicit written approval that names the artifacts and the
boundary. The deterministic core is LLM-free. Full rules: [`data-governance.md`](data-governance.md);
intake procedure: [`intake.md`](intake.md).

## Mentor decisions

Open decisions are tracked as **D1–D8** in [`mentor-decisions.md`](mentor-decisions.md) (short
overview in [`mentor-brief.md`](mentor-brief.md)). In brief:

| # | Decision |
|---|---|
| D1 | Is the evidence **sidecar** an acceptable ISAAC assistant convention? |
| D2 | Vendor the upstream **portal soft-warning** validator for true parity, or keep the local seam? |
| D3 | Data-governance boundary for **real / sanitized** data |
| D4 | May **LLMs inspect real** experiment artifacts? |
| D5 | Bring **Graphify** into the near-term demo, or keep it deferred? (since built — Phases 13–16) |
| D6 | Which **domain** comes after XANES-family (recommended: performance / electrochemistry)? |
| D7 | What is the **final summer deliverable**? |
| D8 | What should the **paper/poster** emphasize? |

These docs plus the latest human decision are authoritative — not stale graph memory.

## Roadmap / back-burner items

Project-owner direction as of July 2026:

| Item | Status |
|---|---|
| Second domain — electrochemistry / performance | **Back burner** (recommended next domain when resumed; exercises conditional-required rules) |
| Web UI | **Built** — `apps/api` (FastAPI) + `apps/web` (React/Vite), a synthetic-only prototype since Phase 19, with a protection-gated demo deployment since Phase 20 (see [`deployment.md`](deployment.md)); production hardening is not planned |
| Project Memory browsing (Phase 24) | **Built** — read-only metadata/provenance surface (status card, Source Index, Concept Lookup) over `/api/memory/*`; never a validator; hosted deployment currently ships honest-unavailable (no graph artifacts shipped yet) |
| CI / GitHub Actions | **Implemented** — `.github/workflows/ci.yml` runs two jobs on push/PR to `main`: a backend job (tests, the synthetic demo, official validation, advisory warnings, the evidence audit) and a frontend job (`apps/web`: vitest, build) |
| License | **Pending** mentor/project decision — no license is asserted yet |
| Real / sanitized-data pilot | Requires **explicit written data-governance approval** first |
| Full upstream portal-validator parity | **Not implemented**; only an evaluation-only local seam exists |

There is a synthetic-only web app prototype (`apps/api` + `apps/web`, deployed since Phase 20 — see
[`deployment.md`](deployment.md)) but no MCP server in this repo. LLM-assisted extraction of
screenshots/PDFs/notes is designed ([`extraction.md`](extraction.md)) but not built.

---

## Using this map with Graphify

Graphify is a good way to *reach* the files this page names — ask it "where is the evidence sidecar
built?" or "what connects to `export.py`?" and it returns nodes with `src=<file> loc=L<line>`
leads. Treat those as pointers: open the cited file and confirm. For anything that decides truth —
is a record valid? which fields are required? does the audit pass? — skip the graph and run the
deterministic check (`isaac validate --official`, the schema, `isaac audit`). Graphify provides
context; the deterministic sources provide truth. See [`graphify-workflow.md`](graphify-workflow.md)
and [`query-cookbook.md`](query-cookbook.md).
