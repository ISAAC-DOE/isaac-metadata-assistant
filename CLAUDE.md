# ISAAC Metadata Assistant — project instructions

Intern project (SSRL/SLAC, ISAAC): turn experiment metadata into validated, evidence-grounded
**official ISAAC records**. Read `docs/proposal-v2.md` for the full design.

## Source of truth

- The **official ISAAC schema** `schema/isaac_record_v1.json` (vendored, v1.05) is the authority
  on record structure, required fields, and vocabulary. It is not ours to edit — see
  `schema/PROVENANCE.md` to refresh it. The upstream standard:
  https://github.com/ISAAC-DOE/isaac-ai-ready-record (+ its wiki).
- Exported records must validate against it (`isaac validate <record> --official`).
- Graphify output is leads, not facts. If it contradicts the schema or a record, the schema wins.

## Trust rules (enforced by code)

- Never invent or guess values, sha256 hashes, URIs, or numeric results. Every finalized draft
  field needs evidence or user confirmation; `isaac export` is gated by both the no-guessing
  checks and the official schema, with no override.
- `records/` is written only by `isaac export` (record + evidence sidecar). Never hand-edit or
  add files there.
- `examples/` may hold sensitive experiment data: keep it gitignored, never send to external
  services.

## Architecture (two layers)

Draft (`drafts/*.draft.json`, envelope format, no-guessing enforced) → `isaac export` transform →
official record (`records/<ULID>.json`) + evidence sidecar (`records/<ULID>.evidence.json`,
JSON-path → source). Evidence lives in the sidecar because the official record schema forbids
extra keys.

## Project-local skills

`/isaac-draft`, `/isaac-complete`, `/isaac-validate`, `/isaac-query`, `/isaac-export`
(`.claude/skills/`). `/graphify` (global) builds the optional graph; the core pipeline must keep
working without it.

## Dev

- Core: `src/isaac_records/` (`official`, `draft_validator`, `export`, `audit`, `ids`, `cli`),
  venv at `.venv/`, tests `.venv/bin/pytest` (35 tests).
- CLI: `.venv/bin/isaac validate|export|audit|new-id` — deterministic, zero-LLM.
- Deps: `jsonschema`, `python-ulid`. (pint and the provisional-schema code were removed in the
  official-schema migration.)
