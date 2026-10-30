# Questions and decisions (Step 7)

`<isaac> bundle questions <bundle> [--scope experiment|group:<id>|run:<id>] [--blocking-only] [--limit N] [--offset M] [--skip-deferred] [--with-targets]`
returns `questions.json` v2: shared questions asked ONCE (experiment scope), run questions collapsed
to their record group, blocking first. Each question has `question_id`, `text`, `why` (why it blocks
export), `applies_to` (groups/runs/targets), `hints` (flagged as hints; a hint is never an answer),
`answer_command`. The reply is compact by default: each question has `targets_count`,
`scopes_count` and `groups_count` instead of its target lists (`decide --question` resolves them;
`--with-targets` prints them), allowed values sit once in `allowed_values_by_field`, default decisions
in `allowed_decisions_by_kind` (a question lists `allowed_decisions` only when it differs), standard
hint notes in `hint_notes`. A question blocks only when a live group's record needs one of its
fields (`blocks_groups`, `required_fields`; reaction drive and catalysis only once a reaction is in
the record, `required_when`); questions only about runs in no live group say `outside_live_groups`.
The reply also has
`counts` (for the scope asked; `counts_whole_bundle` beside it when `--scope` is given: `blocking`,
`conflicts_affecting_a_record`, `conflicts_without_a_record_field`, `optional`, `informational`,
`asked_again`, `deferred`, `outside_live_groups`;
quote these, not `summary.md`'s "Questions: N", which is `fine_grained_v1`) and
`minimum_for_one_group` ("7 blocking questions plus: confirm the group, approve its processing
result"): its `questions[]` list each question to answer with the `only` scope to use,
`unasked_required[]` names required fields no question asks (with `reason` and `command`), and
`plus_decisions` names only the decisions not yet made (an empty list once the group is
confirmed and its result approved). Pages hold at most 200 (`--limit` above that is refused). The older fine-grained list (`bundle list <bundle> questions`)
is for lookup only.

Order: blocking (export cannot happen without them) → conflicts that affect a record → optional.

## How to ask

- 3 to 5 per message, grouped by theme. Start with progress: "Conflicts: 4 of 17 done."
- Plain words. Show each reading with where it came from ("the file name says A; the logbook says B").
  Do not recommend a side. Offer "I don't know / leave it open".
- Take the answer in the scientist's own words; convert to the value the question needs
  (a number with its unit, a name). When the question has `allowed_values` (a closed list), map
  their words to exactly one allowed value and say it back ("in situ" → `in_situ`; "a pressed
  pellet" → `pellet`); record it only on their yes. If none fits, say so and offer the list; never
  stretch a word to fit. `decide` refuses a value the field's schema rejects (not on the list, wrong
  type, a time not in UTC), lists the allowed values and records nothing; when one target of a bulk
  answer is refused, nothing is recorded for any.
- Ask `produced_by` ("who made these measurements?") once, per beamtime; offer a folder-name hint
  as a question, not an answer. Use their own name for `--by` once, ask for it once, reuse it.

## Questions that need care

- **Deferred** (`deferred: {by, decided_utc}`): the scientist said "I don't know". It is still counted
  and sorts last; do not ask it again unless they offer an answer.
- **A conflict with `affects_record: false`** (`no_record_field`): the readings differ, but no record
  field carries them (a comment line, a unit spelling). Say how many there are; do not ask each.

- **No value to confirm.** Text like "What is the technique? The files hold text for it … but no
  value this build can carry", with no `confirm` in `allowed_decisions`, means there is nothing to
  accept. Never invent a value and never confirm one. Ask "What is X?", show the file's text (the
  `file_literal` hint) as a hint, and record `correct --value <their answer>`.
- **Informational** (`"informational": true`, empty `allowed_decisions`, an `answer_command` that is
  only a `#` comment): no answer can reach the record. Do not ask the scientist. Mention them once,
  as a count "listed for information", and move on.
- **`covered_by`**: a per-group question (often the technique) whose field a beamtime-wide answer
  fills. It is not blocking: answer the experiment question it names. Ask per group only when the
  scientist says a group differs (two different confirmed values fill nothing).
- **Asked again** (`asked_again`, or a `why_asked_again` hint): an answer stored earlier cannot go into
  the record (an older build accepted it). The question keeps its id and says why; tell the scientist
  the reason and the allowed values, and ask again.
- **The absorber** (`confirm_absorber`): `answer_command` is a template with `<El>` and `<edge>`; the
  files' pair is only a `suggested_absorber` hint. Say the pair back ("Zz, L3 edge, for all 9
  groups?") and run `--decision set_absorber --element <El> --edge <edge>` only on a clear yes to that
  pair. "Yes, probably" or "sure" is not an answer; ask again. Never run the template as it is.
- **Control mode** (`context.electrochemistry.control_mode`) is an ordinary value among a group's
  optional fields: `--field context.electrochemistry.control_mode --decision correct --value <one of
  its allowed values>`. A potentiostatic mode makes the potential set-point required; a galvanostatic
  one, the current set-point.

## Recording

- **An answer to a consolidated question:** `decide <bundle> --question <Q> --decision correct|confirm --value <v> --by "<name>" [--note "..."]`. It records one decision per target, each listed in the reply; read the list back. `--only group:<id>` answers for one group only (a per-group override of an experiment-wide answer); `--field <path>` picks the one field when a question covers several optional fields.
- **Experiment-scope question:** say "This applies to N groups. One answer for all, or do some differ?" Only split when the scientist says so.
- **The instrument clock's time zone** (`clock_time_zone`, experiment scope, optional): SSRL XDC
  (beamline 4-3 style) scan headers write the start as a local clock time with no zone, so those
  start times have no value until the scientist states the zone the instrument clock was set to.
  Ask it in their words; **suggest no zone** — no file states one, and the facility's location is
  not evidence about the clock. Record: `decide <bundle> --question <Q> --decision set_clock_time_zone
  --value <the IANA name they give: Area/Location, or UTC> --by "<name>"` (an offset like
  `-08:00` or an abbreviation like `PST` is refused; ask again for the zone name; a value starting
  with `-` must be written `--value=-08:00` or the command line itself rejects it before any check). Then each start
  time is shown converted to UTC and needs its own `confirm` (bulk allowed). A time that falls in
  the daylight-saving fall-back hour or spring-forward gap gets no value: ask for the UTC start and
  record it with `correct --value YYYY-MM-DDTHH:MM:SSZ` (`confirm` takes no `--value` here). If the
  zone is changed later to a different zone, every start confirmed under the old one stops counting
  until confirmed again: `decide` reports how many, and `bundle questions` asks them again; say so.
- **QC status** is asked when approving processing, not here (Step 6).
- **In a browser.** The local-only *Local Imports* page (`docs/ui-local-dev.md`) shows the same
  questions and records answers through the same checks. If the scientist uses it, run `bundle
  questions` again before you go on; never assume what they answered.
- **Never** pass `--test-marker` to `build-records` with a real scientist; it is for the self-test.

- Conflict: `decide --target <conflict id> --decision correct --value "<chosen or new value>" --by "<name>" --note "<why, in their words>"` (use `confirm --value` when they pick one of the listed readings).
- Missing value they know: `--decision confirm|correct --value <v>`; they do not know: `--decision defer`.
- Extracted value they accept: `--decision confirm`; reject: `--decision reject`.
- Several evidence-backed values the scientist accepts together: write their ids to a temporary file
  OUTSIDE the bundle folder (`f=$(mktemp)`, one id per line; delete it afterwards), list each item to
  them first, then `decide --targets-file "$f" --decision confirm --by "<name>"`. Bulk confirm is refused for any
  value with no source evidence; do not work around that.
- **"The bundle changed since it was read"** (exit 2, nothing written): something else wrote the bundle
  meanwhile, often the *Local Imports* page. Run `bundle questions` again and re-check the answer still
  applies before recording it.
- **Not on the list at all.** When the scientist's answer is a real value the closed list lacks, say so,
  record nothing, and offer to draft a vocabulary proposal: `<isaac> bundle propose-terms <bundle> --out
  <file.json>` (outside the bundle; it sends nothing, and each draft needs a description the scientist
  writes). The value stays missing until the vocabulary has it.
- Use `--json` with `--value` for numbers/objects. ORCID only if the scientist gives one (`--orcid`).
- Repeating a decision is harmless (recorded once). A later decision replaces an earlier one.

## The template (answer everything the files never state, in one sitting)

- Export: `<isaac> bundle template export <bundle> --out <file.xlsx>`. One row per run in a live
  record group, named by its file's path; Campaign Info answers apply to every File List run.
  Electrolyte is the name only: "0.1 M KOH" goes in as Electrolyte `KOH` and Electrolyte
  Concentration (M) `0.1` (ISAAC's added columns, with pH, after Gas Feed). Take the split from the
  scientist; do not split it for them. Answer cells are empty;
  `ISAAC Suggestions` shows that run's own extracted values, hints and AI readings with file and
  locator. Campaign Info also holds "Your group" and "Your organization (who produced the data)"
  (distinct from "Facility organization") and "Domain"; File List ends with "Reaction Drive" and
  "Reaction Catalysis" (dropdowns of their allowed values). A sheet exported by an older build (the old
  "Organization" label) still imports.
- Import: `<isaac> bundle template import <bundle> <file.xlsx> --by "<name>"` previews compactly
  (one line per cell or column; `--full` for every decision); add `--apply` only after the scientist has seen the preview. Each cell becomes decisions; each note
  cites its cell. Invalid cells (not an allowed value exactly, not a number) record nothing.
- A cell that disagrees with an earlier decision is a clash and is skipped. Use `--supersede` only
  when the scientist says the sheet is the newer answer.
- Columns recorded nowhere (no official field, or no target in this bundle) are listed with their
  cells. Tell the scientist; do not move their values into another field.

## Never

Pick a side of a conflict, fill a required value with a plausible number, copy a beamtime fact
onto a run for them, or confirm something the scientist has not seen.
