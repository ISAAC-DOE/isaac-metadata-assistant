# Questions and decisions (Step 7)

Read this at Step 7. Open another file only on its trigger:

| Trigger | File |
|---|---|
| before you send the "values still proposed" message | `condition-labels.md` |
| a start-time or clock question is listed, or a record warns "start time left out" | `start-times-and-clock.md` |
| the scientist takes the template, or says a filled sheet is theirs | `template-and-own-sheet.md` |
| they keep a word that is not on a field's list | `vocabulary-requests.md` |
| a question shows `earlier_answers`, or you are about to ask whether to remember answers | `earlier-answers.md` |
| a filled question workbook came back | `workbook-answers.md` |
| they would rather answer a few at a time on a small site, or a site's `answers.json` came back | `question-site.md` |

## What the list gives you

**What a rule filled or guessed is not asked.** A value a registered rule fills from the evidence (a reader's value
with nothing disagreeing, a checked stated reading, the facility and group the folder and a second source agree on, the
beamtime's environment convention), and a value guessed from a checked inferred reading (yellow), is not in the list: it
goes into the records as inferred, naming its rule, and the scientist sees it in the end review (`bundle review`, Step
10), guesses first. A question that left out filled values says so ("Left out, because a
rule filled the value from the evidence"). To correct one now: `decide --target <its id> --decision correct`.

`<isaac> bundle questions <bundle> --blocking-only --limit 10` (add `--no-context` for a large page). Read the JSON page. `--plain` (`--plain --detail`) prints the asks as text for a person reading the terminal; it leaves out `minimum_for_one_group`, the counts, the answer commands, the context and the evidence, so do not work from it.

- Shared questions are asked ONCE (experiment scope). Run questions are collapsed to their group. Blocking ones come first.
- Each question has a `question_id`, an `ask` (one sentence, to say to the scientist as it is), its `answer` (the options),
  a `suggested` value with its reason when there is one, and `about` (what it reaches). The JSON page also keeps the
  full `text`, `why` (why it blocks export), `hints`, a `context`, and an `answer_command`. A question with no `ask`
  (counted in `plain_asks.without_ask`) has only its `text`: put it in your own words.
- Allowed values sit once, in `allowed_values_by_field`. Default decisions sit in `allowed_decisions_by_kind`.
- `counts` are the numbers to quote (`blocking`, `optional`, `informational`, `deferred`, …). Never quote `summary.md`'s "Questions: N".
- A question blocks only when a live group's record needs one of its fields.
- `minimum_for_one_group` says what the nearest group still needs:
  - `questions[]`: what to answer, each with the `only` scope to use;
  - `unasked_required[]`: required fields no question asks, each with its `command`;
  - `plus_decisions`: decisions still to make ("confirm the group", "approve its processing result");
  - `recommended[]`: not blocking, but the record would lack a condition without it (today: the potential scale);
  - `blocked`: why no group can be completed, in words.
- A question that reaches groups that can never be a record says how many of its groups CAN
  (`applies_to.groups_that_can_export`). Say that number.
- Not listed, only counted: questions about runs in no live group (`outside_live_groups`), per-group questions one
  beamtime question answers (`answered_at_once`). Say the count once.
- In `--scope group:<id>`, a question shows only what is still open for that group.
- A printed command with `<placeholders>` is a template. Fill it from the scientist's answer; never run it as it is.

## The messages, in this order

**Message 1: what the records cannot go out without.** The blocking questions.

- Take them from `minimum_for_one_group` and the experiment-scope questions.
- Number them. One line each, with its options. The scientist answers "1 yes, 2 pellet, 3 …".
- An experiment-scope question: "this applies to N groups; one answer for all, or do some differ?"
  `--only group:<id>` answers one group differently.
- Questions that share a reading (`same_reading_group`): ask once ("is ZZ1 the same material in all 38 groups?").
  On yes, run the question's `same_reading_command`.
- Keep the environment convention out of the numbered list: it is the next message.

**Message 2: the environment convention, as one question** (kind `environment_convention`, experiment scope). It is asked
when measurements were held at a potential their own files give and something shows they were electrochemical.

- Its `text` names N measurements and two or three of them at their set-points; its hints and `context` carry the
  set-point tokens and the checked quote (or answer) that shows they were electrochemical. Show those, then ask:
  "These N measurements were taken in electrolyte while the cell was held at a potential. Is their measurement
  environment operando or in situ, or does it differ by measurement?"
- Never answer it from a reading: an inferred reading of the environment is shown only as "an earlier reading
  suggested …". Say which word this beamtime uses is theirs to give.
- Record: `<isaac> bundle decide <bundle> --question <Q> --decision set_environment_convention --value operando|in_situ|per_run --by "<name>"`.
  `operando` or `in_situ` fills every such measurement (each run's own environment question it covered drops out);
  `per_run` fills nothing, and each run's environment is asked again.
- When more measurements qualify after the answer, `bundle status` says so and the question opens again, optional:
  answer it again with the same word to cover them.

**Message 3: values still proposed, not filled.** ISAAC proposes these from the files, but no rule fills them (an
absorber, a set-point's scale, a condition label, a start time). Without them, records of one sample look the same.
Show the proposed value for each and ask for one "yes to all", or which to change. Values a rule filled are not here:
they wait for the end review. Read `condition-labels.md` first.

| What | Where it comes from | Record |
|---|---|---|
| start time of every group | the question `stated_utc_start_times` (see `start-times-and-clock.md`) | `--question <Q> --decision confirm` |
| absorbing element and edge | the question `confirm_absorber` | `--question <Q> --decision set_absorber --element <El> --edge <edge>` |
| potential set-points | one confirm question per value ("The files give `0.06` V (from: '060mV')") | its `same_reading_command`, once per value |
| potential scale | ask once: "all potential holds here are quoted against which reference?" | see "The potential scale" below |
| cycling history, filter, sample ids, tag | the `condition_label` questions | `--question <Q> --decision confirm`, or their own wording |

- Say each value back as the question states it ("0.06 V", "filter20", "Ir L3").
- The absorber needs a clear yes to the pair. "Probably" is not a yes.
- A history label: never say what its number means (mV or cycles). Offer the proposed wording; record theirs if they give one.

**Message 4, only if they want it: the rest.** Optional questions; the template for facts that differ per run.

- Conflicts with `affects_record: false` change no record. Give their count; do not ask them.
- `informational` questions cannot reach a record. Mention their count once.
- A question with `covered_by`: its field is filled by the beamtime answer it names. Ask per group only if a group differs.

Show progress in every message ("7 of 9 blocking answers recorded; 84 of 91 records ready").

## How to put a question

- **Make it a yes/no or a pick.** For a field with a closed list, show the allowed values.
- **Offer a suggestion when you can show its evidence.** "The scans have an emission-energy motor and a fluorescence
  signal: HERFD-XAS?" "These are the beamline's own acquisition files: domain `experimental`?"
  It is a suggestion. Record it only on their yes. Never offer one you cannot back with a line, a value or a plot.
- **No suggestion for:** the instrument clock's time zone; a person's or group's name beyond what the folder name
  gives. When the group is asked (no second source agreed with the folder), ask once with the folder's name as the
  suggestion ("The folder names Quillfeather: the Quillfeather group?").
- **Show the evidence first** (next section), then the question.
- Plain words. No field paths, no ids, no command syntax.
- Take the answer in their words. Map it to exactly one allowed value and say it back ("in situ → `in_situ`, right?").
  Record on their yes. Never stretch a word: a metal foil is none of the sample forms.
- A conflict: show each reading with where it came from. Never recommend a side.
- "My reading of the files suggests …" for an AI reading shown beside a question. Never "the files say".
- An AI suggestion read for fewer runs than the question asks about says so (`read_for`: "read for 2 of 86 runs").
  Say that count; never offer it as a reading of the whole beamtime.

## "I don't know"

It is a valid answer. But on a required field, say what it costs before you record it:

1. "Without the sample form, these 12 records cannot be exported." (The count is the question's groups.)
2. Offer two ways to get it: the template, to pass to a colleague who knows; or leave it open and come back later
   (the working folder keeps every answer).
3. If they still say they don't know: `--decision defer`. A deferred required question still blocks those records.

- A deferred question sorts last. Do not ask it again unless they offer an answer.
- No answer at all is not "I don't know": record nothing.

## Context beside a question

Each question carries a compact `context`: what the files, my readings and the processing hold for it.
`<isaac> bundle show <bundle> question <Q>` prints it in full; `--no-context` leaves it out of a large page.
The minimum also carries it for confirming its group and approving its result (`decision_context`).

Present it before the question:

- `quote`: quote the lines word for word, with the file and locator ("the logbook, line 59: '…'").
  Say where each came from: `origin: ai_reading` is my reading (an AI reading, never file evidence); `parser` is a line
  ISAAC read; `document` is a line of a document the extract tool read.
- "Who is named in the files" (the group and organization questions): say who the lines name. Suggest no name the
  folder or the lines do not give.
- `values`, `table_row`: a small table, a run per row, as the files write them. Say "N of M runs shown".
- `plot`, `image`: open each with the Read tool and describe it. Say where it came from. An item with `not_shown` is
  not opened: say what it says.
- The clock: the `#D` local time beside the `#E` epoch, and the offset the two imply. The offset is not a time
  zone: suggest no zone.

The context helps them answer. It is never the answer. Never record a value because the context shows it.

## Kinds that need care

- **A confirm question states its value**: "The files give `0.06` V (from: '060mV'); `confirm` records exactly that."
  Say that value back. When the text lists several values, `confirm` records each target's own.
- **No value to confirm** (no `confirm` in `allowed_decisions`): there is nothing to accept. Ask "what is X?", show the
  file's text as a hint, record `--decision correct --value <their answer>`.
- **Sample name and form asked per sample reading**: say the reading as the files write it ("sample name 'ZZ1',
  electrode '01'"). A file-name number the files do not settle as the electrode is "the 5th token": never call it the electrode.
- **A value read from a scan header's comment line**: the question quotes the whole line with its line number. Ask
  them to check it is the value held during that scan. A line that names no plain value is quoted with no value: ask for it.
- **A beamtime-wide notes sentence** ("It is read only from a notes statement about the whole beamtime"): show the
  sentence and ask whether it applies to these runs. Answer all groups at once only if they say it applies to all.
- **A cell named only in passing**: a notes line about something else gives no cell type. Show the line once and
  ask "what cell was used?". Record `correct --value <their answer>`.
- **A macro and a file name that state different set-points** (`macro_setpoint_disagrees`): read both aloud with the
  files. They say which is right: `confirm --value <one reading> --json`. Only this question settles it.
- **No reading fits the field** (`readings_that_fit_the_field: 0`): `confirm` would be refused; the command is
  `correct --value <…>`. Show the allowed values and ask. A technique question never offers a macro name as a value.
- **Asked again** (`asked_again`): an earlier answer cannot go into the record. Say the reason it gives and ask again.
- **Control mode** is an ordinary optional value:
  `--field context.electrochemistry.control_mode --decision correct --value <allowed value>`.
  A potentiostatic mode makes the potential set-point required; a galvanostatic one, the current set-point.
- **An optional field asked for the whole beamtime** names the groups its answer lands on (`field_reach`). Say those
  groups. When it says "careful: it would put a cell type on …", answer only the groups it fits (`--only group:<id>`).

### The potential scale

A potential goes into a record only beside its scale. Without the scale, the record is written without its potential.

- It is asked per group, because one beamtime can hold potential holds, open-circuit runs and dry samples.
- Ask the scientist ONCE: "all potential holds in this beamtime are quoted against which reference (RHE, Ag/AgCl, …)?
  Does any group differ?"
- Then record it for each group whose file name states a potential, and only those. Each such group has an
  optional-values question whose `fields` include `context.electrochemistry.potential_scale`:
  `<isaac> bundle decide <bundle> --question <that group's Q> --field context.electrochemistry.potential_scale --decision correct --value <scale> --by "<name>"`
- Never record it on an open-circuit, dry or reference group.
- Groups whose own AI readings of the scale agree share a batch (`same_reading_by_field`): then one call with
  `--same-reading` answers them.
- Once a set-point is confirmed and the scale is not, the scale question blocks that group.

## Recording

- **A consolidated question:**
  `<isaac> bundle decide <bundle> --question <Q> --decision correct|confirm --value <v> --by "<name>" [--note "…"]`.
  `--only group:<id>` answers one group; give it several times for several groups. `--field <path>` picks one field
  of a several-field question. `--json` with `--value` for numbers.
- **Every reply starts with a `statement`** ("Pt L3 recorded for 194 groups."). Read it back. It says what the answer
  reached and which groups keep their own answer.
- **A beamtime answer and one group's own answer that differ** leave that group with two values, and its field stays
  empty. The reply names each group not reached. Say it before recording either; fix it with `--only group:<id>`.
- **A later decision replaces an earlier one**, also through `--question`. Repeating a decision is harmless.
  `bundle show <bundle> question <Q>` shows an answered question with who answered and when (`current_answers`).
- **Several values accepted together:** write their ids to `<bundle>-notes/ids.txt`, one id per line
  (the notes folder beside the bundle, never inside the bundle), then
  `<isaac> bundle decide <bundle> --targets-file <bundle>-notes/ids.txt --decision confirm --by "<name>"`.
  It is refused for any value with no source evidence; do not work around that.
- **A refusal records nothing.** A bulk refusal names every refused target with its reason: say them all, repeat
  the call without them, and decide each refused one on its own.
- **"The bundle changed since it was read"**: something else wrote it (often the Local Imports page). Run
  `bundle questions` again and check the answer still applies.
- **The Local Imports page** (`docs/ui-local-dev.md`) shows the same questions through the same checks. If the
  scientist uses it, run `bundle questions` again before you go on.
- ORCID only if they give one (`--orcid`). `--by` is the name from Step 1; never ask it twice.
- QC status is asked when approving a curve (Step 6), not here.

## Never

Pick a side of a conflict, fill a required value with a plausible one, copy a beamtime fact onto a run for them,
confirm something the scientist has not seen, or ask again what a rule filled (the end review shows it).
