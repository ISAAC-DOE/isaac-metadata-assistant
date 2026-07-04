---
name: isaac-complete
description: Ask only the questions that block finalization of an ISAAC draft record, store answers as user-confirmation evidence, and re-validate. Use when the user runs /isaac-complete or wants to finish a draft record.
---

# /isaac-complete — Validated Minimum Mode

Produce the smallest record that passes finalization. Ask the user **only** what
blocks validation — nothing optional, nothing curious.

## Steps

1. Load the draft: the path given as an argument, else the newest file in `drafts/`.
2. Enumerate blockers deterministically — never from memory:
   `.venv/bin/isaac validate <draft> --finalize`
   The `FINALIZATION_INCOMPLETE` / `EVIDENCE_MISSING` / `VOCAB_UNSUPPORTED` /
   `UNIT_*` errors are the complete question list. If it already passes, say so
   and point to `/isaac-export`.
3. Ask all blocking questions in one batch (use AskUserQuestion when available).
   For vocabulary-controlled fields, present the allowed terms from
   `vocabulary/<name>.json` as the options — free-text answers that are not in the
   vocabulary cannot be stored as valid values.
4. For each answer, update the field envelope:
   - `value` ← exactly what the user said (mapped to the vocabulary term they chose)
   - `status` ← `verified`
   - append evidence:
     `{"source_type": "user_confirmation", "question": "...", "answer": "...", "timestamp": "<ISO-8601 now>"}`
   Do not touch fields the user did not answer. If the user says "I don't know",
   the field stays `missing` — that is a valid, honest state.
5. Re-run step 2. Loop until it passes or the user stops.
6. Show the final report plus the evidence map:
   `.venv/bin/isaac validate <draft> --finalize --evidence`

## Hard rules

- Never fill a value the user did not confirm and no source supports.
- Never rephrase an answer into a different scientific claim; if the answer is
  ambiguous, ask a follow-up instead of interpreting.
- Answers requiring scientific judgment you cannot verify stay the user's claim —
  that is exactly what `user_confirmation` evidence records.
