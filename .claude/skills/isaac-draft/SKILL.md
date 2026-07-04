---
name: isaac-draft
description: Extract candidate ISAAC metadata with per-field evidence from uploaded files (Excel, screenshots, PDFs, notes, file listings) into a draft record. Use when the user runs /isaac-draft or asks to start a record from experiment files.
---

# /isaac-draft — Fast Draft Mode

Turn source files into a draft ISAAC record. A draft makes **no claim of validity** —
it is an honest inventory of what the sources support, what is missing, and what needs
confirmation.

## Inputs

Use file paths given as arguments; otherwise read everything in `examples/`.
If `examples/` is empty and no paths were given, stop and ask the user to add files
(see `examples/README.md`).

## The one non-negotiable rule

**Evidence is captured at extraction time, or the value does not go in.**
Every non-null value you write must carry an evidence entry created the moment you
extracted it:

```json
{"source_type": "spreadsheet", "source_file": "examples/campaign_metadata.xlsx",
 "locator": "Sheet 'Campaign Info', cell B2", "quote": "SSRL"}
```

`source_type` ∈ document | spreadsheet | screenshot | web_form | file_listing.
`locator` must be precise enough for a human to check: sheet+cell, page number,
form-field name, screenshot region.

## Status assignment (mechanical, not vibes)

| Situation | status | evidence required |
|---|---|---|
| Value literally present in a source | `verified` | the observed entry above |
| Derived by a stated rule (e.g. element from formula) | `inferred` | a `derivation` entry with the rule, plus the supporting observation |
| Plausible but requires scientific judgment | `needs_confirmation` | whatever prompted the guess; value may be filled but will not finalize |
| Not found anywhere | `missing` | none; value must be `null` |
| Contradicted or invalid | `rejected` | the conflicting entries; note the conflict |

Never promote `needs_confirmation` to `verified` yourself — only `/isaac-complete`
(user confirmation) or better source evidence can do that. If two sources conflict,
mark the field `needs_confirmation` and cite both.

## Steps

1. Read the schema: `schema/isaac_record.schema.json` (structure, required blocks,
   `x-field-rules`). The schema is the final authority — never invent field names.
2. Read the sources. Extract candidate values **with evidence per the table above**.
3. Determine required fields: `.venv/bin/isaac required-fields --technique <T>`
   (once technique is extracted). Create an envelope for every required field —
   honestly `missing` if not found.
4. Write the draft to `drafts/<record_id>.json`
   (`record_id` pattern: `isaac-<year>-<sample>-<technique>-<nnnn>`, lowercase).
5. Run `.venv/bin/isaac validate drafts/<record_id>.json --evidence` and show the output.
6. Summarize for the user: verified / inferred / needs-confirmation / missing fields,
   then list the questions that would block finalization — but **do not ask them**;
   tell the user to run `/isaac-complete` when ready.
