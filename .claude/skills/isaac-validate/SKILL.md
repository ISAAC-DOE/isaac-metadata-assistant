---
name: isaac-validate
description: Validate a draft (no-guessing checks) or an exported record (official ISAAC schema) and explain the result. Use when the user runs /isaac-validate or asks whether something is valid.
---

# /isaac-validate

Validation is deterministic. This skill runs the CLI and explains output — it must not add,
soften, or overrule findings.

## Steps

1. Resolve the target: path given as argument, else the newest file in `drafts/` or `records/`.
2. Run `.venv/bin/isaac validate <path>`. It auto-detects:
   - a **draft** (has `meta`/`fields`) → no-guessing checks (`draft_validator.py`)
   - a **record** → the official schema `schema/isaac_record_v1.json`
   Force with `--draft` or `--official` if needed.
3. Show the report verbatim, then explain.
4. For an official record, optionally add `--warnings` to also print the **non-gating** advisory
   soft-warnings (see Notes). They are informational only and never change the verdict/exit code.

**Draft findings** mean a value isn't safe to finalize: a verified field with no evidence, a
`missing` field that still has a value, an inferred field with no derivation rule, an asset
with no sha256, a descriptor with a null value.

**Record findings** are official-schema violations (all hard/HTTP-400 in the ISAAC portal):
unknown top-level block; value outside an `enum` (technique, environment, …); anti-pattern
descriptor name; a conditional required field missing for this `record_type`/`record_domain`
(evidence ⇒ descriptors; performance+galvanostatic ⇒ current_setpoint_mA_cm2); `record_id`
not a ULID.

## Notes

- **Advisory soft-warnings (non-gating).** `isaac validate <record> --official --warnings` runs a
  **local** advisory seam (`portal_warnings.py`) emitting structured soft-warnings (`NO_LINKS`,
  `QC_NONVALID_WITHOUT_EVIDENCE`). They **never** change validity or block export — the exit code
  comes only from official validation. This is **not** parity with the official portal's full soft
  tier (MISSING_PH, GALVANOSTATIC_NO_POTENTIAL, FE_SUM_EXCEEDS_UNITY, … from upstream
  `portal/validation.py`, not vendored here) — say so if the user asks why a record passes here but
  the portal warns. See `docs/portal-warnings.md`.
- Never claim validity without having just run the command in this session.
