---
name: isaac-validate
description: Run the deterministic ISAAC validator on a record or draft and explain the report with the per-field evidence map. Use when the user runs /isaac-validate or asks whether a record is valid.
---

# /isaac-validate

Validation is deterministic code, never model judgment. This skill only runs the
CLI and explains its output — it must not add, soften, or overrule findings.

## Steps

1. Resolve the target: the path given as an argument, else the newest file in
   `drafts/`. Use `--finalize` when the user asks about export-readiness (default
   to including it — it is the strictness that actually matters).
2. Run: `.venv/bin/isaac validate <path> --finalize --evidence`
3. Show the report verbatim, then explain each error code in one plain sentence:

| Code | Meaning |
|---|---|
| `SCHEMA` | Structure violates `schema/isaac_record.schema.json` |
| `EVIDENCE_MISSING` | Finalized value with no supporting evidence / derivation rule |
| `STATUS_VALUE_MISMATCH` | Status and value contradict (e.g. `missing` but a value present) |
| `VOCAB_UNSUPPORTED` | Value not in the controlled vocabulary (report lists allowed terms) |
| `UNIT_MISSING` / `UNIT_UNPARSEABLE` / `UNIT_WRONG_DIMENSION` | Unit absent, unrecognized, or dimensionally wrong |
| `RAW_DATA_NOT_URI` | Raw data copied into the record instead of linked by URI |
| `FINALIZATION_INCOMPLETE` | A required field is not `verified`/`inferred` — blocks export |

4. If it fails, say which command fixes what: missing answers → `/isaac-complete`;
   wrong extraction → edit the draft and re-validate.

Never claim a record is valid without having just run the command in this session.
