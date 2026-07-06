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
.venv/bin/pytest                                   # 35 tests: golden records validate, transform is gated
.venv/bin/isaac validate tests/fixtures/cuo_xanes_draft.json          # draft: no-guessing checks
.venv/bin/isaac export  tests/fixtures/cuo_xanes_draft.json --records-dir /tmp/demo   # → record + sidecar
.venv/bin/isaac validate /tmp/demo/*.json --official                  # official schema
```

## Commands

| CLI | Skill | Purpose |
|---|---|---|
| — | `/isaac-draft` | Extract candidates + evidence into a draft mapped to official JSON-paths |
| — | `/isaac-complete` | Ask only what blocks export (no-guessing gaps + official-schema gaps) |
| `isaac validate` | `/isaac-validate` | Draft no-guessing checks, or official-schema validation |
| `isaac export` | `/isaac-export` | Transform draft → official record + evidence sidecar (gated) |
| `isaac audit` | — | Validate every record in `records/` against the official schema |
| `isaac new-id` | — | Print a fresh ULID `record_id` |
| — | `/isaac-query` | Routed Q&A (schema / examples / audit / git / graph) |

Graphify is **optional**: the draft → export → validate pipeline works with it entirely absent.

## Migration note

An earlier version of this repo authored its own provisional schema (before the official one was
located). That is superseded — see `docs/proposal-v2.md` §"Migration". The provisional record
schema, its pint unit checks, and its vocabulary files were removed; the evidence-envelope idea
survives, now correctly positioned as a **draft** format that exports into the official shape.
