# ISAAC Metadata Assistant

Turn scattered experimental metadata (Excel sheets, web-form screenshots, PDFs, notes)
into validated, evidence-grounded, AI-ready ISAAC records.

Core principle: **no guessing, no invented values, no finalized field without evidence
or user confirmation** — enforced structurally by a deterministic validator, not by prompts.

## Repo layout

| Path | Role |
|---|---|
| `schema/isaac_record.schema.json` | Provisional record schema (final authority on structure + required fields) |
| `vocabulary/*.json` | Controlled vocabulary (provisional until mentor sign-off) |
| `records/` | Validated records — only written by `isaac export` |
| `drafts/` | Pre-validation drafts produced by `/isaac-draft` |
| `examples/` | User-supplied real artifacts (gitignored; see `examples/README.md`) |
| `src/isaac_records/` | Deterministic Python core: validator, audit, export CLI (zero LLM) |
| `tests/` | Golden record + one failing fixture per validation rule |
| `.claude/skills/isaac-*` | The assistant workflow (draft/complete/validate/query/export) |
| `docs/proposal-v2.md` | Revised project proposal |
| `graphify-out/` | Derived knowledge graph (optional, gitignored) |

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                      # golden record passes, rule fixtures fail correctly
.venv/bin/isaac validate tests/fixtures/golden_cuo_xas.json --finalize --evidence
```

## Commands (Claude Code skills)

| Command | Purpose |
|---|---|
| `/isaac-draft` | Extract candidate metadata + per-field evidence from uploaded files → draft |
| `/isaac-complete` | Ask only the questions that block validation; answers become evidence |
| `/isaac-validate` | Run the deterministic validator, show errors/warnings + evidence map |
| `/isaac-query` | Answer questions with explicit routing (schema file / audit / git log / graph) |
| `/isaac-export` | Validate (blocking) → move draft to `records/` → best-effort graph refresh |

The knowledge graph (Graphify) is **optional**: the draft → complete → validate → export
pipeline is fully functional without it.
