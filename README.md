# ISAAC Metadata Assistant

Turn scattered experimental metadata (Excel sheets, web-form screenshots, PDFs, notes) into
validated, evidence-grounded **official ISAAC records**.

The [official ISAAC standard](https://github.com/ISAAC-DOE/isaac-ai-ready-record) (DOE BES AI
Pathfinder, catalysis) is the **source of truth**. Its machine-readable schema
(`isaac_record_v1.json`, v1.05) is vendored here and every exported record is validated against
it. This project is not a schema — it is an **extraction → draft → export** assistant that helps
authors produce schema-valid records without guessing, and keeps an evidence trail the official
record format has no room for.

Core principle: **no guessing, no invented values, no finalized field without evidence or user
confirmation** — enforced structurally at authoring time, then re-checked against the official
schema at export.

## Two layers

```
examples/  ──/isaac-draft──▶  drafts/<name>.draft.json   (envelope: {value, status, evidence[]})
                                      │  no-guessing enforced here
                                /isaac-export  (deterministic transform, schema-gated)
                                      ├─▶ records/<ULID>.json          valid against official v1.05
                                      └─▶ records/<ULID>.evidence.json evidence sidecar (JSON-path → source)
```

The official record carries no per-field provenance (its schema is `additionalProperties:false`),
so evidence lives in a **sidecar** keyed by official JSON-path. That is where auditability
survives after export.

## Repo layout

| Path | Role |
|---|---|
| `schema/isaac_record_v1.json` | **Vendored official schema (v1.05) — the authority.** See `schema/PROVENANCE.md` |
| `schema/isaac_draft.schema.json` | The draft authoring format (ours; not an ISAAC record) |
| `vocabulary/descriptor_class.json` | Descriptor class names the schema references but doesn't inline |
| `tests/fixtures/official/` | The 10 official golden records — must-validate fixtures |
| `records/` | Exported records + evidence sidecars — written only by `isaac export` |
| `drafts/` | Pre-export drafts |
| `examples/` | User-supplied real artifacts (gitignored; see `examples/README.md`) |
| `src/isaac_records/` | Deterministic core (zero LLM): `official`, `draft_validator`, `export`, `audit`, `cli` |
| `.claude/skills/isaac-*` | The assistant workflow (draft/complete/validate/query/export) |
| `graphify-out/` | Optional derived knowledge graph (gitignored) |

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                                   # 80 tests: golden records validate, transform is gated
```

**Run the synthetic end-to-end demo** (structured sheet → evidenced draft → human-answered blockers →
official record + sidecar, on committed synthetic fixtures — no real data):

```bash
.venv/bin/python scripts/run_synthetic_demo.py                        # build → complete → export
.venv/bin/isaac validate /tmp/isaac-demo/*.json --official            # official schema
.venv/bin/isaac audit --records-dir /tmp/isaac-demo                   # record + evidence sidecar
```

The demo regenerates the committed sample (`docs/samples/`) byte-for-byte. See **[`docs/demo.md`](docs/demo.md)**
for the full walkthrough and expected output.

### Documentation

| Doc | For |
|---|---|
| [`docs/mentor-brief.md`](docs/mentor-brief.md) | **Start here for review** — five-minute mentor brief: what exists, what's deterministic, open decisions, next step |
| [`docs/demo-script.md`](docs/demo-script.md) | Live-meeting demo script — what to run, what to point at, what not to overclaim, likely questions |
| [`docs/final-deliverable-outline.md`](docs/final-deliverable-outline.md) | Paper/poster/report outline — titles, abstract, sections, figures/tables |
| [`docs/claude-workflow.md`](docs/claude-workflow.md) | How a user drives the assistant through Claude — the five slash skills as a scripted conversation |
| [`docs/demo.md`](docs/demo.md) | Reproducible synthetic demo — exact commands + expected output |
| [`docs/architecture.md`](docs/architecture.md) | Pipeline + module map for reviewers |
| [`docs/query-demo.md`](docs/query-demo.md) | Graphify memory/query demo — what the graph answers vs. what stays deterministic |
| [`docs/portal-warnings.md`](docs/portal-warnings.md) | Portal-style advisory soft-warnings — non-gating seam vs. the hard schema gate |
| [`docs/paper-notes.md`](docs/paper-notes.md) | Motivation / methods / results notes for intern deliverables |
| [`docs/intake.md`](docs/intake.md) · [`docs/extraction.md`](docs/extraction.md) | Data-governance intake plan · extraction strategy |

## Commands

| CLI | Skill | Purpose |
|---|---|---|
| — | `/isaac-draft` | Extract candidates + evidence into a draft mapped to official JSON-paths |
| — | `/isaac-complete` | Ask only what blocks export (no-guessing gaps + official-schema gaps) |
| `isaac validate` | `/isaac-validate` | Draft no-guessing checks, or official-schema validation (`--warnings` adds non-gating advisory soft-warnings) |
| `isaac export` | `/isaac-export` | Transform draft → official record + evidence sidecar (gated) |
| `isaac audit` | — | Validate every record in `records/` against the official schema |
| `isaac new-id` | — | Print a fresh ULID `record_id` |
| — | `/isaac-query` | Routed Q&A (schema / examples / audit / git / graph) |

## Two planes: truth vs. memory

The system deliberately separates **what is true** from **what we remember**.

- **Truth plane (deterministic, Graphify-free).** The official schema, the validators, and export
  decide whether a record exists and is valid. This path never imports Graphify — enforced by a
  test (`test_core_never_imports_graphify`). The official ISAAC schema and official validator are
  the only authorities on validity.
- **Memory/query plane (Graphify-central).** Graphify is a **major** part of the system for
  memory and context, not a bolt-on: project memory, relationship search, similar-record lookup,
  prior-experiment and document queries, contextual help while drafting, documentation search, and
  "what changed?" history. `/isaac-query` routes here for those questions.

**Graphify is central for memory and query, but never central for truth.** If a graph answer
conflicts with the schema, a validated record, or the audit, the deterministic source wins. The
draft → export → validate pipeline works with Graphify entirely absent.

> Status: the truth plane (draft → export → validate → audit) is implemented and demo-ready. The
> Graphify memory/query plane now has a **reviewer demo** — see [`docs/query-demo.md`](docs/query-demo.md)
> — with `/isaac-query` routing each question to the source that owns it. The deeper query-layer work
> (an automated graceful-degradation test tier) remains **deferred/future**. The memory plane is
> optional and the deterministic pipeline does not depend on it — Graphify never decides validity.

## Validation stack

Records pass through staged checks; each stage has a fixed authority and the AI never overrides code:

1. **Draft no-guessing validation** (`draft_validator.py`) — gates authoring.
2. **Official ISAAC schema validation** (`official.py`, vendored v1.05) — gates export.
3. **Portal-style advisory soft-warnings** (`portal_warnings.py` · `isaac validate --warnings`) —
   a **non-gating** local seam (Phase 8): structured warnings, never blocks export. Not upstream
   parity — the real `portal/validation.py` is not vendored. See [`docs/portal-warnings.md`](docs/portal-warnings.md).
4. **AI scientific consistency review** (`review.py`) — **advisory only**, placeholder today.
5. **Human review** of anything flagged — the decider.

Stage 4 is a placeholder interface (`src/isaac_records/review.py`): it is advisory, never marks a
record valid/invalid, never mutates records, and is not wired into export or validation. A future
Scientific/Consistency Review Agent would implement it and may consult Graphify for similar-record
comparison — as advisory context, never as truth.

## Migration note

An earlier version of this repo authored its own provisional schema (before the official one was
located). That is superseded — see `docs/proposal-v2.md` §"Migration". The provisional record
schema, its pint unit checks, and its vocabulary files were removed; the evidence-envelope idea
survives, now correctly positioned as a **draft** format that exports into the official shape.
