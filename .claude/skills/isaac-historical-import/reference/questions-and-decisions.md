# Questions and decisions (Step 7)

`<isaac> bundle questions <bundle> [--scope experiment|group:<id>|run:<id>] [--blocking-only] [--limit N] [--offset M] [--skip-deferred] [--with-targets]`
returns `questions.json` v2: shared questions asked ONCE (experiment scope), run questions collapsed
to their record group, blocking first. Each question has `question_id`, `text`, `why` (why it blocks
export), `applies_to` (groups/runs/targets), `hints` (flagged as hints; a hint is never an answer; an AI
suggestion read for fewer runs than the question asks about carries `read_for`, e.g. "read for 2 of 86
runs", and the question's text says it — say that count with the suggestion, never offer it as a reading
of the whole beamtime),
`answer_command`. The reply is compact by default: each question has `targets_count`,
`scopes_count` and `groups_count` instead of its target lists (`decide --question` resolves them;
`--with-targets` prints them; a beamtime-wide question's `groups_count` is the groups its answer reaches,
with `groups_total` beside it when some keep their own, differing answer: say "N of M"), allowed values sit once in `allowed_values_by_field`, default decisions
in `allowed_decisions_by_kind` (a question lists `allowed_decisions` only when it differs), standard
hint notes in `hint_notes`. A question blocks only when a live group's record needs one of its
fields (`blocks_groups`, `required_fields`; reaction drive and catalysis only once a reaction is in
the record, `required_when`; a member an object the record carries requires, e.g. the electrolyte's
`concentration_M` once its name is answered, with `required_because`); questions only about runs in no
live group say `outside_live_groups` and are counted, not listed (`hidden_outside_live_groups`; add
`--include-outside-live-groups` to list them, or ask `--scope run:<id>`); per-group questions that one beamtime
question answers at once are counted, not listed (`answered_at_once`; add `--each-group` to list them); an optional value of such a run is asked in that run's own question,
never inside the beamtime's or a live group's. A beamtime-wide conflict (no run named) counts every live group
it reaches (`applies_to.beamtime_wide: true`, `groups` = `blocks_groups`).
The reply also has
`counts` (for the scope asked; `counts_whole_bundle` beside it when `--scope` is given: `blocking`,
`conflicts_affecting_a_record`, `conflicts_covered_by_decisions`, `conflicts_without_a_record_field`, `optional`, `informational`,
`asked_again`, `deferred`, `outside_live_groups`;
quote these, not `summary.md`'s "Questions: N", which is `fine_grained_v1`) and
`minimum_for_one_group` ("7 blocking questions plus: confirm the group, approve its processing
result"): its `questions[]` list each question to answer with the `only` scope to use (and, for a field
required only because of another, `required_because` and the `command` that answers it),
`unasked_required[]` names required fields no question asks (with `reason` and `command`), and
`plus_decisions` names only the decisions not yet made (an empty list once the group is
confirmed and its result approved); for a group with scans but no processing result yet it says "run
`isaac process` first", and for one whose only results were rejected, "re-process it". It never names a group that cannot export while another exists: no
ISAAC protocol covers its data, its result has no curve, none of its runs lists a scan (`no_scans`, the
`cannot_export_reason` of `bundle list <bundle> groups`), or every run is a reference standard or alignment
scan whose record needs a field nothing can hold (`not_a_measurement_run`). No question counts as blocking for a
group with any `cannot_export_reason`; `blocking_basis.record_composer.groups_that_cannot_export` names those
groups once, with each one's reason (the first 20; `cannot_export_by_reason` counts them all). A question that reaches some of them says how many of its groups can
become a record (`applies_to.groups_that_can_export`, and a sentence in its text): say that number, not the reach.
A disagreement that reaches only such groups affects no record: it is optional, with "Not a record" in its `why`.
When only such groups are left, `blocked` says why
in words and `plus_decisions` never says "approve its processing result" for them. `recommended[]` (never blocking, not counted) names a question
worth answering for that group, with the warning that explains it (`warnings`): today, a potential the
file names state that the record will not carry until its scale is confirmed. Pages hold at most 200 (`--limit` above that is refused). The older fine-grained list (`bundle list <bundle> questions`)
is for lookup only.
In a group's scope a question asked for more runs lists only what is still open for that group: an
optional-values question drops the fields its record already carries (`fields_already_in_this_groups_record`
counts them), and a conflict that affects no record and reaches no group is left out.

Order (SKILL.md Step 7): the minimum for one group → experiment-scope questions, once → the template
(below) for what the files never state, then per group only what it leaves → conflicts that affect a
record → optional. The counter question (`naming_counter_positions`) is asked earlier, in Step 5,
before any group is confirmed: while it is open it is listed FIRST in every scope that lists it, and until a
group is confirmed the minimum names it in `answer_first` (not counted; never after a `defer`). Every printed command with `<placeholders>` (`answer_command`,
`next_commands`) is a template: fill it from the scientist's answer, never run it as it is.

## How to ask

- 3 to 5 per message, grouped by theme. Start with progress: "Conflicts: 4 of 17 done."
- Plain words. Show each reading with where it came from ("the file name says A; the logbook says B").
  Do not recommend a side. Offer "I don't know / leave it open".
- Take the answer in the scientist's own words; convert to the value the question needs
  (a number with its unit, a name). When the question has `allowed_values` (a closed list), map
  their words to exactly one allowed value and say it back ("in situ" → `in_situ`; "a pressed
  pellet" → `pellet`); record it only on their yes. If none fits, say so and offer the list; never
  stretch a word (a metal foil is none of the sample forms). If they keep their own word, see "Not on
  the list at all" below. Use `defer` only if they say they don't know. `decide` refuses a value the field's schema rejects (not on the list, wrong
  type, a time not in UTC), lists the allowed values and records nothing; when one target of a bulk
  answer is refused, nothing is recorded for any. The refusal names EVERY refused target with its reason: say
  them all, then run the call again without them and decide each refused one on its own.
- Ask `produced_by` ("who made these measurements?") once, per beamtime; offer a folder-name hint
  as a question, not an answer. `--by` is the name the scientist gave in Step 1; do not ask again.

## Questions that need care

- **One-group questions** show `scope: group:<id>` even when their id was made at experiment scope
  (`id_scope`); `--scope experiment` no longer lists them. Answer them like any group question.
- **Deferred** (`deferred: {by, decided_utc}`): the scientist said "I don't know". It is still counted
  and sorts last; do not ask it again unless they offer an answer (`--skip-deferred` leaves them out).
  A question they did not answer at all is not deferred: record nothing.
- **Values read from an SSRL XDC scan header's comment lines** (rule `ssrl_xdc_header_comment_v1`: lines 9-12,
  the free text before `Weights:`; on BL4-3 headers these are COMMENTS2-4 on lines 9-11, and COMMENTS1 is line 8,
  there the gain, which is not read): a value is offered ONLY when the line writes
  it in a plain form, each statement its own segment (split at `,` `;` `|` or two spaces), e.g. `0.1 M HClO4,
  pH 1.3, -0.3 V vs RHE` (a set-point `E = -0.3 V (RHE)`, `-300 mV vs RHE`; a pH `pH 1.3`; an electrolyte
  `100 mM NaClO4` or `KOH 1 M`), and nothing else in the line makes it doubtful (a second potential, OCP, eta,
  a step or rate, a sweep, `pre-`/`then`, an offset, a range; a reference, bridge or filling beside an
  electrolyte). Such values always need review: the question quotes the whole line and its line number; ask the
  scientist to check it is the value held during that scan, and confirm or correct each. Otherwise
  (`100mM NaClO4 pH1.3 He`, `1e-3 M KCl`, `eta = 300 mV`) the line is quoted with NO value (`no_value: true`;
  the kind stays `confirm_value`): ask the scientist to state the value (`correct`), or `reject` when the line
  states none for that scan. No gas is read. Questions that quote one line for one field share a
  `same_reading_group` (`same_reading_count` of them): if the value is the same for all, one
  `<isaac> bundle decide <bundle> --question <Q> --same-reading --decision correct --value <v> --by "<name>"`
  answers every open one (its `same_reading_command`). For many runs (30 runs all `1M KOH`), the template's
  File List columns are the easy path: `<isaac> bundle template export <bundle> --out <file.xlsx>`.
- **A macro and a file name that state different set-points** (`macro_setpoint_disagrees`; `affects_record: true`, on the potential set-point): a macro `run<N>.mac` named a file `…_800mV` that was never acquired, and the file acquired in its place (between run N-1 and run N+1 in time, the only undeclared one there, its name equal but for the potential) is `…_700mV`. Read both aloud with the files; the scientist says which is right (`confirm --value <one reading> --json`). Only this question's answer settles it: confirming the set-point value on its own leaves it open (its question names this one), and a bare confirm of the value later does not undo an answer given here; a correction with a value does. Nothing is raised when the run number or the time does not tie them, or when more than one file could be the one; then the macro's own conflict (`affects_record: false`) is all there is. A bundle imported before this check has none: re-import to get it.
- **A conflict with `affects_record: false`** (`no_record_field`): the readings differ, but no record
  field carries them (a comment line, a unit spelling). Say how many there are; do not ask each.
- **A conflict with `covered_by_decisions`** (also `affects_record: false`; counted in
  `conflicts_covered_by_decisions`, not in `optional`): each of its runs already holds the scientist's decision for
  that field, one value across its runs (e.g. a sheet's Technique ruling, or a beamtime-wide answer, which reaches
  every run a live group holds), and the record is built from it. Do not ask it again; say how many there are. A run
  whose own answer differs from the beamtime-wide one, or another run of its group answered otherwise (the record pools
  them), is not covered: the record fills nothing for that field until they agree.
- **A conflict no reading of which the field takes** (`readings_that_fit_the_field: 0`; each reading
  hint has `fits_field`): `confirm --value <one reading>` would be refused, so `answer_command` is
  `correct --value <…>`. Start times: the `#D` readings are local clock times with no zone and can never
  be recorded; `utc_readings` (also `utc_reading` hints) lists the UTC instants the bundle already holds
  for that run, each with its source (e.g. the `#E` epoch line). Show them as readings, ask which is the
  start, and record `correct --value <the instant they choose>`; never pick it for them. Many groups at once:
  see the next item. A closed field
  (e.g. the technique read from macro names or Python helper lines): show `allowed_values` and record
  the one they name. When only some readings fit, `confirm` one of those.
- **One answer for every group's start time** (`stated_utc_start_times`, experiment scope). A SPEC file
  states in its header when the file was CREATED: `#E` (a UTC epoch) and `#D` (the same instant, a local
  clock time with no zone). Each scan then writes its own `#D`, a little later. When these disagree in two
  or more groups, this one question asks once. `#E` is the file's creation, not the first scan's start. The
  question says the largest gap to the first scan (`largest_file_to_first_scan_s`, read on one clock) and
  leaves out a run whose gap is above 10 minutes. Ask the scientist: "Use each file's creation instant (#E)
  as the record's start? The first scan started at most N s later." Only on their yes:
  `decide --question <Q> --decision confirm --by "<name>"` (no `--value`; `--only group:<id>` for one
  group). Each run gets its own `#E` instant; nothing is shared between runs. Which instant a record's start
  should be (file creation or first scan) is open for the protocol review (DEC-89): say so. The reply says
  how many groups were recorded, which open groups it does not reach and why (`not_reached`, one entry per
  group: no `#E` line, `#E` readings that disagree, a late first scan, a group with two runs, where the
  scientist says which run's start the record takes, or a file started more than once), and which groups keep an
  answer of their own. A file started more than once (in several sessions) has two or more `#E` lines: "its file
  was started N times (#E at line 2: …; line 152: …)". Its `#E` question asks which is the start. Its `#D`
  question names that one (`asked_by_question`) and needs no answer of its own. A group that cannot become a
  record is left out of `not_reached` (counted in `not_a_record`): nothing to answer for it. Answer
  the groups it does not reach one by one. A record whose runs were given different starts carries none and
  warns "start time left out: this group's runs were given different start times". While the question is
  open, each start-time warning names it too.
  The question is never asked for local clock times waiting on a clock zone (BL4-3; `clock_time_zone`).
  `bundle questions` lists it and folds the per-group start-time questions it answers
  (`answered_at_once`; `--each-group` lists them). Each per-group question keeps its id and stays
  answerable: answer one to give that group another value. The Local Imports page does not show this
  question yet; it asks per group.

- **A confirm question states its value.** Its text says exactly what `confirm` records, with the unit
  the field's name fixes and the file text it was read from: "The files give `0.06` V (from: '060mV');
  `confirm` records exactly that." Say that value back ("0.06 V for this group, right?") and confirm only on
  their yes; when the text lists several values, `confirm` records each target's own. Every value the text
  states is recorded as shown, so a later `annotate --blind` of one of those targets is not blind.
- **A beamtime-wide notes statement** ("It is read only from a notes statement about the whole beamtime"):
  a logbook sentence before any sample section, naming no sample, is context, not a run's value (Rule 6).
  The import holds it for review (`needs_review`, never a silent extracted value; an older bundle is held
  the same way by every command that reads it, and stored so by its next change, which prints "held N
  value(s) read only from a beamtime-wide notes sentence for review"), so every group it reaches is asked,
  once per group, with the sentence.
  Show the sentence and ask whether it applies to these runs; a sentence that only mentions the thing in
  passing is usually a `reject` or a `correct`. Answer all groups at once only when they say it applies to all.
- **A cell named only in passing** ("What is the cell type? … The notes name a cell only in passing, in a
  sentence about something else: '…'"): a notes line that names a cell but is about something else gives no
  cell type. That is a to-do or reminder ("TODO: flow cell needs a gasket"), handling or storing it ("kept with
  the flow cell", "rinse the flow cell"), or any line not shaped like a statement of the cell. The question quotes the line and asks. When one
  line is behind many groups, only the first question quotes it; the others name that question, and each keeps the
  line in its `file_literal` hint. Show the line once. It offers no `confirm` and no
  `--same-reading` batch. Ask "What cell was used for these runs?" per group (or in the template's Cell Type
  column) and record `correct --value <their answer>`. A record cites such a line as `context`, never as
  support. A line about the cell is read as before: a short header ("PEEK flow cell", "In situ flow cell,
  5 ml/min"), a label ("Cell: H-cell"), "is a flow cell", or "measured in a flow cell".
- **Sample questions asked once for several groups** name the shared sample reading as the files write it
  ("with the same sample reading (sample name 'ZZ1', sample or electrode number '01', as the files write
  it)"). Say that reading when you ask.
- **Per-group questions that share a reading** (73 groups' material name `'JK1C'`, one set-point per potential) are
  kept one per group (each record carries its own answer; their ids never change), but share a `same_reading_group`
  (`same_reading_count` of them), and the text says "N questions share this reading (…); answer them together with
  … --same-reading …". Ask once ("are all N the same thing?"); on a yes, run its `same_reading_command`. Runs whose
  file names read the field differently never share one; answer the others on their own. A confirm is batched by the
  value it records, not by how the file writes it: `0p8V` and `800mV` are one batch, "N questions share this value
  (`0.8` V; the files write it '0p8V', '800mV')". Say the value back, and the spellings.
- **Material name and form asked per group because no source states the sample** (the partition is each group's
  whole file name, `sample_name_stem`): groups whose names share every sample token share a `same_reading_group`. A sample
  token is a part of the name with a letter in it that is no counter, set-point, pH, concentration or open-circuit
  word (`Q4`, `SYNcat` and `5wp` of `Q4_06_SYNcat_5wp_pH2_000mV`; `shared_sample_tokens`). A temperature, time, gas or
  state word (`400C`, `2h`, `H2`, `fresh`) counts as a sample token unless the parser read it as a condition. The text names the
  tokens and the files. A bare number (an electrode, a step) is no sample token, so two electrodes of one material
  share a batch. Ask once ("is the material the same for all N?"); on a yes, run its `same_reading_command`.
  Names that differ in any sample token (`Q4` and `Q5`, `5wt` and `5wp`) are never batched: ask those apart. A
  reading made for another sample's group (its own sample name) is never a hint on these questions.
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
  A group that differs (a reference foil) is answered with `--only group:<id>`, before or after the
  answer for all. Re-running the answer for all later never undoes it: the reply names each group that
  kept its own answer (`kept_per_group_answers`); say so, and change one only with `--only`.
  When only an AI reading suggests the pair, the text says the import counted no file statement of the
  absorber; a scan header's region-file name (e.g. `TiK_XANES.rgn`) is not counted, though processing reads
  it to propose a reference foil's edge (its calibration `reference.basis: stated_by_evidence`). If the
  scientist asks, say exactly that: both read the same header; only processing used the region name.
  A split part's question may carry an `answered_before_split` hint (the pair answered for the group it
  was split from): it is a hint, never the part's answer; read it back and record it per part only on
  the scientist's yes.
- **The counter question** (`naming_counter_positions`): its text shows real file names of this
  bundle with the asked token in brackets (`SYNnp_on_Au_[12]_1500mV` vs `SYNnp_on_Au_[2]_1500mV`;
  also `example_names`), and one name where that token is not a number (`SYNfilm_on_Au_[OCV]`). Show
  them as they are; ask whether that number marks repeats of one measurement. When no two names differ only
  there, it shows one real name with the token marked ("[03]_01_SYN… (no two names here differ only there)");
  it never shows a pattern like `XX_02_…`.
- **Control mode** (`context.electrochemistry.control_mode`) is an ordinary value among a group's
  optional fields: `--field context.electrochemistry.control_mode --decision correct --value <one of
  its allowed values>`. A potentiostatic mode makes the potential set-point required; a galvanostatic
  one, the current set-point. Once the potential set-point is confirmed, the potential scale is what is
  missing until it is answered (the set-point goes in only beside it), so the scale question blocks.
  With neither answered, both are required now and counted together in the minimum (the scale's
  `required_because` says it is asked with the set-point), so the scientist is not asked twice.
- **An optional field asked for the whole beamtime** whose groups were mostly answered already (a File List): its
  `field_reach` (and the text, "… reaches 9 of 78 group(s) …, the other 69 already answered per group") says which
  groups and runs an answer there lands on; the reply to `--field` says the same. Say those groups, not "the whole
  beamtime". When it says "careful: it would put a cell type on …" (a standard, or a run recorded ex situ), do not
  answer it there: answer only the groups it fits (`--only group:<id>`).
- **Potential scale and control mode are asked per group** (DEC-90: one beamtime can hold open-circuit references,
  potential holds and dry samples). Groups whose own AI readings of the field all agree share a batch for that field
  (`same_reading_by_field.<field>`: its group key, count, members and `same_reading_command`). Say the suggested value,
  that it is an AI reading, and the groups; on a yes, run `decide --question <Q> --field <path> --same-reading`. Groups
  whose readings differ or that have none stay apart. An open-circuit run is never batched with a potential hold, and
  a reference or ex-situ group is never batched in. Each group's own question id still answers it with `--field`.

## Recording

- **An answer to a consolidated question:** `<isaac> bundle decide <bundle> --question <Q> --decision correct|confirm --value <v> --by "<name>" [--note "..."]`. It records one decision per target, each listed in the reply; read the list back. `--only group:<id>` answers for one group only (a per-group override of an experiment-wide answer); `--field <path>` picks the one field when a question covers several optional fields.
  A question the files ask ONCE for the whole beamtime (one beamtime-wide target, e.g. Technique from a shared
  macro; its reply says "It reaches every record group of the beamtime: N groups, M runs") also takes
  `--only group:<id>` with `correct` (or `confirm --value`): the answer is recorded for that group's runs only,
  on their own targets or on a per-run answer slot, never on the beamtime-wide target. The reply says so. If the
  beamtime-wide question is answered with a different value (before or after), that group gets two values and fills
  nothing for the field: say it before recording either. The beamtime-wide reply then says "It reaches 8 of the
  beamtime's 9 record groups" and names each group NOT reached ("group:<id> keeps its own answer 'XAS' … answer
  `--only group:<id>` to change it"; `reach.not_reached`); a template import's preview lists the same under "Not
  reached by a beamtime-wide answer" (`not_reached`). Read it back; the two agree only when the group is
  re-answered with `--only group:<id>` (its reply: "It agrees with the beamtime-wide answer") or the beamtime
  question is answered with the group's value. For such a group the minimum's `unasked_required` command is that
  `--question <Q> --only group:<id>` one, never `--target` on the beamtime target (that rewrites every group).
  A slot belongs to its run: a group (e.g. after a merge) fills the field from slots only when every run of it
  has the same answer (a slot, its own, or the beamtime-wide one); otherwise it is missing and the composer says
  why. A slot no decision names is dropped on save; a deferred slot is no longer asked once the beamtime-wide
  question has a value (it stays in the bundle: the log names it).
- **Experiment-scope question:** say "This applies to N groups. One answer for all, or do some differ?" Only split when the scientist says so. A question built at experiment scope whose targets all sit in ONE group (a sample field asked per sample reading) is shown with that group's `scope: group:<id>` and carries `id_scope: experiment`: the scope its id was made from, kept so the id never changes. Ask it for that group only.
- **The instrument clock's time zone** (`clock_time_zone`, experiment scope, optional): SSRL XDC
  (beamline 4-3 style) scan headers write the start as a local clock time with no zone, so those
  start times have no value until the scientist states the zone the instrument clock was set to.
  Ask it in their words; **suggest no zone** — no file states one, and the facility's location is
  not evidence about the clock. Record:
  `<isaac> bundle decide <bundle> --question <Q> --decision set_clock_time_zone --value <the IANA name they give: Area/Location, or UTC> --by "<name>"` (an offset like
  `-08:00` or an abbreviation like `PST` is refused; ask again for the zone name; a value starting
  with `-` must be written `--value=-08:00` or the command line itself rejects it before any check). Then each start
  time is shown converted to UTC and needs its own `confirm` (bulk allowed). A time that falls in
  the daylight-saving fall-back hour or spring-forward gap gets no value: ask for the UTC start and
  record it with `correct --value YYYY-MM-DDTHH:MM:SSZ` (`confirm` takes no `--value` here). If the
  zone is changed later to a different zone, every start confirmed under the old one stops counting
  until confirmed again: `decide` reports how many, and `bundle questions` asks them again; say so.
  If they do not know the zone: `--question <Q> --decision defer` (no `--value`: a `defer` on the
  experiment takes none, and `--target experiment --decision defer --value …` is refused; the question
  chooses which "I don't know" it is). That records "I don't know":
  no start time is converted, the question stays under its id, marked `deferred`, and the counter
  question is not touched. Every record of those runs then goes out without its start time, and says
  so: `validate` and `export` warn "start time left out: instrument clock zone deferred (question <Q>)"
  (while the question is not answered at all: "… not answered yet (question <Q>)"; on a SPEC beamtime, with no
  clock question, a run whose start-time readings disagree and are unsettled: "start time left out: the start-time
  disagreement is unanswered (question <Q>; …)", whose question offers the `#E` epoch's UTC reading),
  the record's evidence file keeps that line under `notes`, and `upload --dry-run` says it once with a count; tell the
  scientist before they export. Once a zone is recorded, `defer` is refused (it would not withdraw the
  zone); to change the zone, state it again.
- **QC status** is asked when approving processing, not here (Step 6).
- **In a browser.** The local-only *Local Imports* page (`docs/ui-local-dev.md`) shows the same
  questions and records answers through the same checks. If the scientist uses it, run `bundle
  questions` again before you go on; never assume what they answered.
- **Never** pass `--test-marker` to `build-records` with a real scientist; it is for the self-test.

- Conflict: `<isaac> bundle decide <bundle> --target <conflict id> --decision correct --value "<chosen or new value>" --by "<name>" --note "<why, in their words>"` (use `confirm --value` when they pick one of the listed readings that fits the field).
- Missing value they know: `--decision confirm|correct --value <v>`; they say they do not know: `--decision defer`.
- Extracted value they accept: `--decision confirm`; reject: `--decision reject`.
- Several evidence-backed values the scientist accepts together: write their ids to `<bundle>-notes/ids.txt`
  (the notes folder beside the bundle, one id per line), never inside the bundle, list each item to
  them first, then `<isaac> bundle decide <bundle> --targets-file <bundle>-notes/ids.txt --decision confirm --by "<name>"`. Bulk confirm is refused for any
  value with no source evidence; do not work around that.
- **"The bundle changed since it was read"** (exit 2, nothing written): something else wrote the bundle
  meanwhile, often the *Local Imports* page. Run `bundle questions` again and re-check the answer still
  applies before recording it.
- **Not on the list at all.** When the scientist's answer is a real value the closed list lacks, say so
  and record no decision. If no allowed value fits and they keep their own word, run
  `decide … --value "<their exact word>" --as-said` once: it records no decision but keeps their word as
  a vocabulary request, in the `--by` name, with the field, runs and where it was said. The command exits 0 and its reply starts with that (`vocabulary_request_kept`, `decision_recorded: false`). Never pass a word
  they did not say: without `--as-said` an off-list value keeps nothing (the reply says "if this is the
  scientist's own word, repeat with --as-said"), so a value you try while working out a mapping is never
  put in their name. `template import --apply` keeps their own off-list cells the same way, and `template
  adopt` for their own sheet only with `--by`, passed once they say the sheet is theirs; the Local Imports
  page never keeps one. `--note` holds only the
  scientist's own words about the term, word for word, or is left out: never your summary or wording; the reply says "kept as a vocabulary request; `isaac bundle propose-terms` can draft
  it". It is never a decision or a value. Where a decision already gives the field an allowed value, the record
  keeps exporting it and the reply names it ("the record keeps `surface_oxidation` meanwhile"): ask whether that
  is acceptable until the term exists. Where none is held, the field stays missing (`bundle validate` lists it under
  `pending_vocabulary`) until the vocabulary has the term or they give an allowed value. A later `decide` that
  answers an open request says "This answers your request for 'oxidation' (vr-…); it is no longer drafted" (or what
  still drafts it): say that too. Offer to draft:
  `<isaac> bundle propose-terms <bundle> --out <bundle>-notes/terms.json` (outside the bundle; it sends nothing).
  Say which terms come only from my readings (`by_origin.ai_reading`), not from their answers; draft one
  only if they want it.
  Read each draft back: a word that NAMES an existing term (`reversible_hydrogen_electrode` is `RHE`) is
  not drafted, "use `RHE` (an existing term)": ask whether to answer `RHE`. A close term (`XANES` beside
  `XAS`, `HERFD-XAS`) is drafted with `check_existing`: its description must say why none of those fits.
  A term whose draft says `answered: true` is not drafted: the scientist has since given an allowed value
  (`answered_with`) for every run they asked it for, so never offer it. Say a draft's `partly_answered` sentence
  when you offer it; with `answered_before_request`, `answered_same_step` or `answered_order_unknown`, ask
  whether they still want the term. If they now choose the allowed value, record it with `decide`: for
  `answered_before_request` or `answered_same_step` it is recorded again and answers the request; for
  `answered_order_unknown` first record their word again with `--as-said`, then `decide`. A sheet cell equal
  to the current value records nothing. A draft counts only the requests still open: an earlier one answered since
  is set apart (`answered_scientist_notes`; `earlier_requests_answered_note`: "The open request (vr-…) is for 1 run(s)
  (which hold `surface_oxidation` from before it); the request answered since (vr-…, from their own sheet, 139
  run(s)) is not part of this draft"). Say that sentence; never the answered request's runs as the draft's.
  A term with a space is not drafted (the `--out` summary counts them: "N term(s) need a one-word form (ask)"); its `ask` says what to ask for (one word, e.g. `cathodic_corrosion`):
  record their one-word answer again, never rewrite it yourself. Once the one-word form is kept too, the spaced request is answered (`one_word_form_given`) and no longer counted. They write each description themselves on
  the Schema Proposals page (Propose a Change → Load drafts from a local import), never in the file and
  never by you. Nothing is sent until they save a proposal; saving one sends the term, its counts and
  its file-name citations to the ISAAC server that page uses (the hosted server when they use the
  website): their choice (row D in `data-flow-and-consent.md`); say so before they save. After
  more answers, `--merge` updates the same file and keeps every description in it (who wrote one is not
  known: read it back to them); no draft is ever marked ready to send, and a term no longer found is
  carried over as not current, never proposed. A description of a term answered since (`earlier_description`,
  counted apart in the summary) is kept only in case they ask for the word again: it is not to be filed.
- Use `--json` with `--value` for numbers/objects. ORCID only if the scientist gives one (`--orcid`).
- Repeating a decision is harmless (recorded once). A later decision replaces an earlier one, also
  through `--question`: `decide --question <Q>` resolves a question that is already answered (by an
  earlier answer or a template import) under the same id, with the same checks. This holds for every
  kind: a value, the absorber (`--only group:<id>` for one group), the counter question, the clock
  zone. `bundle show <bundle> question <Q>` shows an answered question with `status: answered` and
  `current_answers` (each decision, value, `element`/`edge` or `positions`, how many targets, who,
  when); an open one with answered parts lists those too.
- **Every `decide` reply starts with a `statement`** ("Pt L3 recorded for 194 groups.", "deferred for
  140 runs: environment.", "Nothing new recorded: …"). Read that sentence back to the scientist; the
  id lists after it are for checking, not for reading out.

## The template (answer everything the files never state, in one sitting)

- Export: `<isaac> bundle template export <bundle> --out <bundle>-notes/template.xlsx` (every `--out` of
  `template export`, `adopt` and `propose-terms` goes in `<bundle>-notes/`, beside the bundle). One row per run in a live
  record group, named by its file's path; Campaign Info answers apply to every File List run.
  Electrolyte is the name only: "0.1 M KOH" goes in as Electrolyte `KOH` and Electrolyte
  Concentration (M) `0.1` (ISAAC's added columns, with pH, after Gas Feed). Take the split from the
  scientist; do not split it for them. Answer cells are empty;
  `ISAAC Suggestions` shows that run's own extracted values, hints and AI readings with file and
  locator. Campaign Info also holds "Your group" and "Your organization (who produced the data)"
  (distinct from "Facility organization") and "Domain"; File List ends with "Reaction Drive" and
  "Reaction Catalysis" (dropdowns of their allowed values), then "Temperature" and "Gas Atmosphere" (template
  1.5.0). A sheet exported by an older build (the old "Organization" label) still imports.
- Temperature is typed with its unit: `298.15 K` or `25 °C` (`℃` too). A bare number is an invalid cell: ISAAC never
  guesses the unit. A °F value and a range (`25-30 °C`) are invalid too, each with its own reason: ask for one value
  in K or °C. A °C value is converted to kelvin and listed in the preview under "Would convert to kelvin". Read each
  one back before `--apply`.
- A deprecated term typed (`three_electrode` for Cell Type) is still recorded as typed. The preview lists it under
  "Deprecated terms" with what to use instead. Say it, and ask whether they meant the cell body (e.g. `beaker_cell`).
- Import: `<isaac> bundle template import <bundle> <file.xlsx> --by "<name>"` previews compactly
  (one line per cell or column; `--full` for every decision); add `--apply` only after the scientist has seen the preview. Each cell becomes decisions; each note
  cites its cell. Invalid cells (not an allowed value exactly, not a number) record nothing.
- A cell that disagrees with an earlier decision is a clash and is skipped. Use `--supersede` only
  when the scientist says the sheet is the newer answer. A clash's `clashes_by_cell` command is a `--question`
  command when the cell's targets are exactly one question's. (A ruling on an adopted sheet's Disagreements row that
  named the value recorded now needs no `--supersede`; see below.)
- Columns recorded nowhere (no official field, or no target in this bundle) are listed with their
  cells. Tell the scientist; do not move their values into another field.
- A run's cell for a field this bundle asks ONCE for the whole beamtime (e.g. Technique, a shared
  macro) is listed under "Asked once for the whole beamtime" with that question's id and command (each
  cell named once, with how many runs reach it); it is not recorded. Ask the scientist that question (the cell's value is in the command) and run it.
  This holds only for a run that has no target of its own for the field: a run whose files state their
  own value (e.g. its own macro name, so it has a per-run Technique candidate) takes the cell as a
  decision on that candidate like any other cell (a `confirm` if the value matches, else a `correct`),
  so one preview can record Technique for some runs and list it as asked once for others.
- The preview names, one line each, every cell that would REPLACE an extracted value or CONTRADICT the
  run's own file name (a typed `0.8` for an `m800mV` file, pH `2` for a `pH12` one) under "Replaces or
  contradicts a file reading". Read each one back and ask; never let a "correct N" count stand for them.
- Electrolyte is the name only: "0.01 M HClO4" in it is an invalid cell ("name only: put 0.01 in
  Electrolyte Concentration (M)"). Ask the scientist for the split; do not make it.

## The scientist's own filled sheet

Only when the scientist says **in this conversation** that a filled ISAAC metadata template is theirs
and to use it (a sheet you found in the folder is not that; ask first). Never retype it for them.

1. `<isaac> bundle template adopt <bundle> <their.xlsx> --out <bundle>-notes/adopted.xlsx` (outside the bundle
   folder). It refuses anything that is not a filled copy of ISAAC's template (the blank one too, known
   by its example values even if it ships example File List rows, and a sheet ISAAC exported: that one is
   imported). It maps their File List rows to runs by the run's OWN folder or name (`<stem>_dir` and the
   files directly inside it; a parent folder such as `raw` names no run) and writes the bundle's template: an answer cell holds THEIR
   value only where no file reading contradicts it, with a note citing their cell (`'File List'!K31`).
   Every value a file reading contradicts (an extracted value, a potential or pH file-name token, an AI
   reading of a file), or that the field does not take, is NOT in an answer cell: it is a row of the
   `Disagreements` sheet with their value, EVERY reading of that field for those runs with its source (each
   marked `differs:` or `agrees:`; read both kinds back), and an empty "Your ruling". A Campaign Info
   beamline (or a one-word facility acronym) that names another one than a facility HINT (the folder's name,
   the SPEC headers' fingerprint (their SPEC account and column names), or the acquisition system the scan
   headers match: what `ISAAC Suggestions` shows) is a row too, kind
   `hint`: compared without `BL` and separators, so `BL15-2`, `BL152` and `15-2` agree and `62b` does not. A
   fingerprint that states no branch (`BL6-2`) agrees with any branch (`62b`). When the hints disagree with each
   other, the row says so first and marks each hint `differs from` or `agrees with`: read every one back. A
   hint is not a reading; say both and let them rule. The facility's organization is in no hint and is not
   compared. A Campaign Info value that differs from an answer already RECORDED for the runs it reaches (`SLAC
   National Accelerator Laboratory` beside a recorded `SLAC`) is a whole-beamtime row too, kind `recorded`: one ruling
   settles it for every run. A beamline is compared as the hints are, so `SSRL BL15-2` beside a recorded `BL15-2` agrees.
2. Say the summary: rows matched, cells adopted, their columns not read (File List and Configurations; the
   Configurations line lists what each column holds, e.g. `Primary Signal Channel` `FF1`: no field holds it, so it
   stays in their sheet), unmatched rows and runs (those
   runs get nothing from their File List rows; when it says "Campaign Info still applies to them", their
   Campaign Info answers do reach those runs: say so), and the rows that reach more than one run, with the count (a scan
   and its `_dir` calibration file are two runs; one value of theirs goes to each). Then read **every** disagreement back, one by one, in plain words:
   "your sheet says 0.8 V for Q4_07; the file name says m800mV, which these names use for −0.8 V". For
   a not-allowed value, give the field's allowed list once and map their words to one value only on
   their yes; for an electrolyte with a concentration, ask for the name and the concentration
   separately. A not-allowed row may carry a hint from a column adopt does not read ("your sheet's column I
   'Environment mode' says 'insitu' (= `in_situ`)"): say it as their own sheet's words, never as the answer.
   An allowed list marks a deprecated term ("three_electrode (deprecated: use …)"): never offer it.
   A temperature column is read only when its header states the unit (`Temperature (°C)`, `Temperature (K)`); the
   cell keeps the unit and the import converts it. `Temperature ©` states none and is not read: ask them to type
   the values with their unit. "Channel hints" lines show the channel their Configurations row states beside a
   processing result that chose its channel by name (`channel_choice_needs_review`): say both. It is a hint, never
   the answer; another channel is used only on their word, with a params file.
   Rows count runs ("for 77 run(s), from 38 of your cell(s)"). When a reaction is adopted or on a row, the
   summary says it makes Reaction Drive and Reaction Catalysis required for N groups: ask those too. Never
   pick a side, and never suggest a ruling. "N row(s) name only runs in no live record group": those rows give
   nothing (their runs are in a rejected group or none); say so, never as unmatched.
   **Adopting again** (after a new reading): a row is settled only when what is recorded equals their sheet's
   value, or came from their ruling on that same row in an earlier import of this sheet. It says
   "already recorded: 'in_situ' (2026-10-30); leave blank to keep", counted apart ("Disagreements already recorded: 14 of 16"): do not
   ask for that ruling again; say it is settled, and read back only the rest. A row whose recorded value is older
   than the sheet and differs says "recorded `12` (date); your sheet says `2`: rule which": it still awaits their
   ruling, so read both values back. "Rule which" means: the bundle holds one value, their sheet says another, and
   ISAAC picks neither; whatever they type in "Your ruling" (either value, or a third) is recorded for every run of the
   row by `template import --apply`, no `--supersede` needed (the row was made against the value recorded now; if
   something was recorded for it since the adopt, the import says so and nothing is recorded: adopt again). Runs
   holding different values are counted per value ("recorded `-0.8` (8 runs), `-0.6` (1 run)"): say which, and that
   one ruling sets them all. An electrolyte row with only the name ruled says "name recorded: 'KOH';
   concentration awaits your ruling": ask the concentration (column J).
   A word "The sheet still says 'oxidation' … answered since with `surface_oxidation`" (with or without `--by`,
   under "Answered since") is said as: "your sheet's 'oxidation' was already replaced by surface_oxidation;
   nothing to do unless you want your own word kept".
3. **Their rulings go in the sheet, by them**: they type each ruling in the "Your ruling" column of
   `Disagreements` (the value to record, exactly as the field takes it; blank records nothing). Do not
   type it for them. A ruling reaches exactly the runs that row names, and its decision cites the
   ruling cell and their original cell. An Electrolyte row whose value states a concentration
   ("0.01 M HClO4") takes the NAME in "Your ruling" and the concentration in mol/L in "Your ruling:
   concentration (M)" (column J), both recorded for that row's runs: that is the one path for it here (no
   per-group command). J on any other row records nothing and is said. A ruling for a field the bundle asks
   once for the whole beamtime (Technique) is recorded per run for exactly the row's runs (a per-run answer
   slot where a run has none), never on the beamtime-wide question; the preview names it and how many groups
   that question still covers.
4. `<isaac> bundle template import <bundle> <adopted.xlsx> --by "<name>"` previews: say the decisions,
   the rulings it read, and each "awaiting your ruling" row (nothing is recorded for those); rows under
   "Disagreements already recorded" keep their value when left blank, and "N decision(s) (from M cell(s)) already
   recorded" are answers given before: neither is asked again. Add
   `--apply` only on their yes. Re-importing the same file after more rulings is harmless. Rulings on rows that
   named the value recorded now are listed under "Rulings … over the value recorded now": read each back (old value,
   new value, runs) before `--apply`. Clashes and "Cells not tied to your sheet" are one line per cell (`--json` lists
   every target), each with ONE command for all its targets: offer that one, never a single target's (it would split
   the row), and `decide` warns if a command changed only some targets of one ruling.
   **"Cells not tied to your sheet"** are cells whose workbook did not see the value recorded now: a decision came
   since the adopt (a `decide`, another adoption of the sheet, or "another copy of this workbook": a colleague, or
   they, importing a copy of the same file), or the bundle was copied or restored. Nothing is recorded for them and
   the value now is kept; each line says who recorded it and when ("recorded now: '12' by Name (date), from a
   decide"). Say that plainly; tell them to run `template adopt` again and rule against what is recorded now, or use
   the cell's one command if they are sure. Never read a decision id out (`--json` keeps them).
   A file reading added AFTER the adopt (an AI reading of a scan file, say) that contradicts an adopted
   cell is named under "Replaces or contradicts a file reading" as *not recorded* and listed as awaiting
   a ruling "(not yet on the Disagreements sheet)": run `template adopt` again so it gets a Disagreements
   row to rule on. A cell the scientist TYPED (an ordinary exported template, or a ruling) that a file
   reading contradicts is named the same way as *you typed it* and is still recorded: read it back first.
   The same holds for a typed Campaign Info beamline a facility hint names differently: named once (not once
   per run), recorded as typed; an adopted one is held back until adopt is run again.

## Never

Pick a side of a conflict, fill a required value with a plausible number, copy a beamtime fact
onto a run for them, or confirm something the scientist has not seen.
