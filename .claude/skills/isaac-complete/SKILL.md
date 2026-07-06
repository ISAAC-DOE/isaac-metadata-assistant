---
name: isaac-complete
description: Ask only the questions that block a draft from exporting to a valid ISAAC record, store answers as evidence, and re-check. Use when the user runs /isaac-complete or wants to finish a draft.
---

# /isaac-complete — Validated Minimum Mode

Get a draft to the point where it exports cleanly. Ask the user **only** what blocks that —
nothing optional.

## Where the questions come from (never from memory)

Two deterministic sources:

1. **No-guessing gaps:** `.venv/bin/isaac validate <draft>` — any finalized field missing
   evidence, any asset missing `sha256`, any descriptor missing a value.
2. **Official-schema gaps:** attempt the transform and validate the result. Run
   `.venv/bin/isaac export <draft> --records-dir /tmp/isaac-preview` (a throwaway dir). If it
   is blocked, the reported errors — missing required blocks for this `record_type`/`domain`,
   bad vocabulary, conditional requirements — are the exact remaining questions.

The union of those two lists is the complete question set. If both pass, say so and point to
`/isaac-export`.

## Asking

- Batch the questions (AskUserQuestion when available).
- For fields the official schema controls with an `enum` (technique, environment, cell_type,
  control_mode, …), present the allowed values from `schema/isaac_record_v1.json` as options —
  a free-text answer outside the enum cannot become a valid record.
- For each answer, update the draft: set `value`, set `status: verified`, and append
  `{"source_type":"user_confirmation","question":...,"answer":...,"timestamp":"<ISO now>"}`.
- "I don't know" ⇒ the field stays `missing` (null). That is honest and allowed unless the
  schema requires the field, in which case the record genuinely cannot be finalized yet.

## Hard rules

- Never fill a value the user did not confirm and no source supports.
- Never fabricate a `sha256`, a URI, or a numeric result to satisfy the schema.
- Re-run both checks after edits; loop until export is unblocked or the user stops.
