---
name: isaac-draft
description: Extract candidate metadata with per-field evidence from uploaded files into an ISAAC draft (envelope format). Use when the user runs /isaac-draft or asks to start a record from experiment files.
---

# /isaac-draft — Fast Draft Mode

Turn source files into an ISAAC **draft** (`drafts/<name>.draft.json`). A draft is not an
ISAAC record — it is the authoring format where the no-guessing rule is enforced before
anything is transformed into the official schema. Export happens later (`/isaac-export`).

## Inputs

Paths given as arguments, else everything in `examples/`. If empty, stop and ask the user to
add files (see `examples/README.md`).

## The draft format

```
{
  "meta":   {record_type, record_domain, source_type},   # classify FIRST — it gates required fields
  "fields": {"<dotted.official.path>": {value, unit?, status, evidence[]}},
  "series": [...], "qc": {...},         # measurement data, official shape
  "assets": [{asset_id, content_role, uri, sha256, evidence[]}],
  "descriptors_outputs": [{label, generated_utc, generated_by, descriptors:[{name,kind,source,value,uncertainty,evidence[]}]}],
  "links": [...], "attribution": {...}, "tags": [...],
  "implicit": [{about, value, evidence[]}]   # inferences with NO official field (see below)
}
```

Keys under `fields` are **dotted paths into the official schema** — read
`schema/isaac_record_v1.json` and map every value to its real path (e.g. sample formula →
`sample.material.formula`, beamline → `system.facility.beamline`, environment →
`context.environment`). Never invent a path or block; the export step validates against the
official schema and will reject unknown fields.

## The one non-negotiable rule

Evidence is captured at extraction time or the value does not go in. Each non-null field's
`evidence[]` cites where it came from: `source_type` ∈ document|spreadsheet|screenshot|
web_form|file_listing, with a precise `locator` (sheet+cell, page, form field).

## Status assignment

| Situation | status | evidence |
|---|---|---|
| Value present in a source | `verified` | the observed entry |
| Derived by a stated rule | `inferred` | a `derivation` entry with `rule`, plus supporting observation |
| Needs scientific judgment | `needs_confirmation` | whatever prompted it; won't export |
| Not found | `missing` | none; `value` must be null |

## ISAAC-specific gotchas (from the real schema)

- **`record_type` + `record_domain` decide required fields** (evidence ⇒ descriptors;
  performance+electrochemistry ⇒ control_mode + setpoint). Pick them first.
- **Assets need a real `sha256`.** Raw data is linked and hashed, never copied. If you don't
  have the hash, ask for it (`/isaac-complete`) — do not fabricate one.
- **Some values have no field.** Absorbing element and edge are implicit (from
  `sample.material.formula` + `system.technique`); detection setup is open-namespace
  `system.configuration.*`. Put element/edge in `implicit[]` (sidecar-only), not in `fields`.
- **Descriptor names** follow the controlled class list (`vocabulary/descriptor_class.json`),
  e.g. `edge_shift`, `white_line_energy`, `oxidation_state`.

## Steps

1. Read `schema/isaac_record_v1.json`. Choose meta (type/domain/source).
2. Extract values into `fields` (dotted paths) + structured blocks, evidence per the table.
3. Write `drafts/<name>.draft.json`.
4. `.venv/bin/isaac validate drafts/<name>.draft.json` (no-guessing checks) and show output.
5. Summarize verified / inferred / needs-confirmation / missing, and list what would block
   export — but don't ask yet. Point the user to `/isaac-complete`.
