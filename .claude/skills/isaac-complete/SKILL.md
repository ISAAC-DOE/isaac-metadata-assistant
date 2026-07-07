---
name: isaac-complete
description: Ask only the questions that block a draft from exporting to a valid ISAAC record, store answers as evidence, and re-check. Use when the user runs /isaac-complete or wants to finish a draft.
---

# /isaac-complete — Validated Minimum Mode

Get a draft to the point where it exports cleanly. Ask the user **only** what blocks that —
nothing optional.

## Where the questions come from (never from memory)

The question set is **exactly `draft["pending"]`** — the blockers `build_draft` emitted
deterministically. There is one question per pending entry, and it is that entry's
`question` string verbatim (e.g. `"What is the sha256 of <uri>?"`, the reduced-spectrum
`series` blocker, the required-descriptor blocker). Nothing is asked from memory, and no
extra questions are invented beyond what `pending[]` lists.

Cross-check the same two deterministic gates if you want to confirm the list is complete:

1. **No-guessing gaps:** `.venv/bin/isaac validate <draft>` — any finalized field missing
   evidence, any asset missing `sha256`, any descriptor missing a value.
2. **Official-schema gaps:** attempt the transform and validate the result. Run
   `.venv/bin/isaac export <draft> --records-dir /tmp/isaac-preview` (a throwaway dir). If it
   is blocked, the reported errors — missing required blocks for this `record_type`/`domain`,
   bad vocabulary, conditional requirements — are the exact remaining questions.

If `pending[]` is empty and both gates pass, say so and point to `/isaac-export`.

## How answers are applied

Answers are applied by `isaac_records.complete.apply_answers(draft, answers)` (a pure,
non-truth authoring function — it imports only stdlib, never graphify or the truth plane).
It consumes `draft["pending"]`:

- an `asset` blocker resolves when `answers["asset_sha256"]` has the candidate `uri`; a
  schema-shaped asset (`asset_id`, `content_role`, `uri`, `media_type`, `sha256`) is appended
  to `assets`;
- the `series` blocker resolves when `answers["series"]` supplies the measurement series;
- the `descriptor` blocker resolves when `answers["descriptor"]` supplies a descriptor;
- the implicit `edge` candidate is confirmed when `answers["edge"]` is given.

**Every applied answer becomes `user_confirmation` evidence** (`{source_type:
"user_confirmation", question, answer, timestamp}`), added alongside the deterministic
`file_listing`/`derivation` evidence already present — never replacing it. A resolved
blocker is removed from `pending`; an **unanswered blocker stays in `pending` and keeps
blocking export**. `apply_answers` never adds a value that is not in `answers` — no sha256,
series point, descriptor, or edge is guessed by the system.

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
