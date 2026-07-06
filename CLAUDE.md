# ISAAC Metadata Assistant — project instructions

Intern project (SSRL/SLAC, ISAAC): turn experiment metadata into validated, evidence-grounded
**official ISAAC records**. Read `docs/proposal-v2.md` for the full design.

## Source of truth

- The **official ISAAC schema** `schema/isaac_record_v1.json` (vendored, v1.05) is the authority
  on record structure, required fields, and vocabulary. It is not ours to edit — see
  `schema/PROVENANCE.md` to refresh it. The upstream standard:
  https://github.com/ISAAC-DOE/isaac-ai-ready-record (+ its wiki).
- Exported records must validate against it (`isaac validate <record> --official`).

## Two planes: truth vs. memory

- **Truth plane** — official schema + validators + export decide validity. Deterministic and
  Graphify-free (enforced by `test_core_never_imports_graphify`).
- **Memory/query plane** — **Graphify is central** for project memory, relationship search,
  similar-record lookup, prior-experiment/document queries, contextual drafting help,
  documentation search, and "what changed?" history. Route memory/query questions through it.
- **Graphify is central for memory and query, but never central for truth.** If a graph answer
  conflicts with the schema, a validated record, or the audit, the deterministic source wins.

## Validation stack (AI never overrides code)

1. Draft no-guessing (`draft_validator.py`) → 2. Official schema (`official.py`) →
3. Official `portal/validation.py` soft warnings (deferred) → 4. AI consistency review
(`review.py`, **advisory only**, placeholder) → 5. Human review. Stage 4 must never mark records
valid/invalid, mutate records, or be wired into export/validation.

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
