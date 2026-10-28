# Questions and decisions (Step 7)

`<isaac> bundle questions <bundle> [--scope experiment|group:<id>|run:<id>] [--blocking-only] [--limit N] [--offset M]`
returns `questions.json` v2: shared questions asked ONCE (experiment scope), run questions collapsed
to their record group, blocking first. Each question has `question_id`, `text`, `why` (why it blocks
export), `applies_to` (groups/runs/targets), `hints` (flagged as hints; a hint is never an answer),
`allowed_values` where the schema closes the field, and `answer_command`. The reply also has
`counts` and `minimum_for_one_group` ("7 blocking questions plus: confirm the group, approve its
processing result"). The older fine-grained list (`bundle list <bundle> questions`) is for lookup only.

Order: blocking (export cannot happen without them) → conflicts that affect a record → optional.

## How to ask

- 3 to 5 per message, grouped by theme. Start with progress: "Conflicts: 4 of 17 done."
- Plain words. Show each reading with where it came from ("the file name says A; the logbook says B").
  Do not recommend a side. Offer "I don't know / leave it open".
- Take the answer in the scientist's own words; convert to the value the question needs
  (a number with its unit, a name). Echo your conversion back if it is not obvious.
- Ask `produced_by` ("who made these measurements?") once, per beamtime; offer a folder-name hint
  as a question, not an answer. Use their own name for `--by` once, ask for it once, reuse it.

## Recording

- **An answer to a consolidated question:** `decide <bundle> --question <Q> --decision correct|confirm --value <v> --by "<name>" [--note "..."]`. It records one decision per target, each listed in the reply; read the list back. `--only group:<id>` answers for one group only (a per-group override of an experiment-wide answer); `--field <path>` picks the one field when a question covers several optional fields.
- **Experiment-scope question:** say "This applies to N groups. One answer for all, or do some differ?" Only split when the scientist says so.
- **QC status** is asked when approving processing, not here (Step 6).
- **Never** pass `--test-marker` to `build-records` with a real scientist; it is for the self-test.

- Conflict: `decide --target <conflict id> --decision correct --value "<chosen or new value>" --by "<name>" --note "<why, in their words>"` (use `confirm --value` when they pick one of the listed readings).
- Missing value they know: `--decision confirm|correct --value <v>`; they do not know: `--decision defer`.
- Extracted value they accept: `--decision confirm`; reject: `--decision reject`.
- Several evidence-backed values the scientist accepts together: write their ids to a temporary file
  OUTSIDE the bundle folder (`f=$(mktemp)`, one id per line; delete it afterwards), list each item to
  them first, then `decide --targets-file "$f" --decision confirm --by "<name>"`. Bulk confirm is refused for any
  value with no source evidence; do not work around that.
- Use `--json` with `--value` for numbers/objects. ORCID only if the scientist gives one (`--orcid`).
- Repeating a decision is harmless (recorded once). A later decision replaces an earlier one.

## Never

Pick a side of a conflict, fill a required value with a plausible number, copy a beamtime fact
onto a run for them, or confirm something the scientist has not seen.
