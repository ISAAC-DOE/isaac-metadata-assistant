# ISAAC Metadata Assistant — project instructions

Intern project (SSRL/SLAC, ISAAC): turn experiment metadata into validated,
evidence-grounded ISAAC records. Read `docs/proposal-v2.md` for the full design.

## Trust rules (non-negotiable, enforced by code)

- Never invent or guess metadata values. Every finalized field needs evidence or
  user confirmation — the validator (`isaac validate`) rejects records that don't
  comply, and export is validator-gated with no override.
- The schema (`schema/isaac_record.schema.json`) and validator are final
  authorities. Graphify output is leads, not facts.
- `records/` is written only by `isaac export`. Never edit or add files there by hand.
- `examples/` may contain sensitive experiment data: keep it gitignored, never
  send its contents to external services.

## Project-local skills

`/isaac-draft`, `/isaac-complete`, `/isaac-validate`, `/isaac-query`, `/isaac-export`
(in `.claude/skills/`). Use them for any record-creation or record-question task.
`/graphify` (global skill) builds the optional knowledge graph; the core pipeline
must keep working without it.

## Dev

- Python core: `src/isaac_records/`, venv at `.venv/`, run tests with `.venv/bin/pytest`.
- CLI: `.venv/bin/isaac validate|audit|export|required-fields` (deterministic, zero-LLM).
- Any change to `schema/` or `vocabulary/` needs mentor sign-off before records
  are created against it (Week-1 hard gate in the roadmap).
