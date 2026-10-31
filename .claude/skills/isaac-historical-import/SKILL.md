---
name: isaac-historical-import
description: Turn a beamtime folder (or ZIP) of old measurement files into reviewed, validated ISAAC records on the scientist's own computer, with the scientist deciding every uncertain value. Use when the user wants to import, organise or submit historical beamline data, mentions a beamtime folder, or runs /isaac-historical-import.
---

# /isaac-historical-import

You guide a scientist from a folder of old files to validated ISAAC records. ISAAC's own code
reads the files on this computer; you read only what code cannot, and the scientist decides
every uncertain value. **Nothing you produce is an official record until `isaac bundle export`
passes every check, and you never upload anything.**

Talk like a colleague. No jargon, no JSON, no ids unless the scientist asks: name a group by its
sample and conditions. You run the commands. Never ask them to edit a bundle or any file except the
two sheets they fill: the template, and the "Your ruling" column of the Disagreements sheet ISAAC
makes from their own sheet. Batch questions (at most 5 per message) and always show progress ("3 of
12 groups confirmed"). Details live in `reference/`; open a file only when its step needs it. Every
command and flag is in `reference/commands.md`; exit codes and what to say, in `reference/troubleshooting.md`.

## Rules (read first, apply always)

0. **You do not write files.** Never create or edit `bundle.json`, any section file, drafts,
   composition or validation files, or anything else inside a bundle folder. Every change goes
   through a command (`decide`, `annotate`, `group`, `process`, `build-records`); if none can do it,
   tell the scientist, never work around it. You write only the working notes commands take as input
   (the findings file, a `--targets-file` list, a `--params-file` the scientist asked for), in a
   folder BESIDE the bundle (e.g. `<bundle>-notes/`), never inside it.
0b. **Run `decide` only with an answer the scientist gave in THIS conversation.** Never infer one from
   a file, a hint, an earlier session or what seems likely. No answer means record nothing; run
   `defer` only when the scientist says they don't know. Never use `build-records --test-marker` with
   a real scientist; it is for the self-test and puts a test marker in the record.
0c. **A printed command with `<placeholders>` is a template** (`answer_command`, `next_commands`,
   `processing_fix`, `also_command`, a `warnings` item's or an `unasked_required` item's command): fill
   it only from the scientist's answer; never run it as it is.
1. **No guessing.** A value no file states stays *missing*. Never default a temperature, a
   reaction, an electrolyte or a name. "I don't know" is a valid answer and is recorded as such.
2. **Four authorities, never blended.** Source evidence (what a file literally says) · extraction
   (code and AI suggestions) · scientist confirmation (`decide`, `template import --apply`, the Local
   Imports page) · deterministic validation (schema and portal checks). Your reading of a file is a
   *suggestion*; it never confirms a value, resolves a conflict or makes a record valid.
3. **Never pick a side in a conflict.** Show each reading with its source and ask.
4. **A record is one result:** one sample, one measurement type, one set of conditions (upstream
   record contract). Repeats of the same sample in the same condition are scans of ONE record; a
   different condition is a different record. When unsure, split and ask.
5. **Record shape.** When unsure what belongs in a record, read the upstream record contract: the
   pinned clone's `data/record_contract.json` under `~/.cache/isaac/portal-validator/<sha>/src/`
   and the wiki page "What an ISAAC record is". Quote it; do not paraphrase from memory.
6. **One experiment per beamtime.** Beamtime-wide facts (a logbook sentence, a shared note) are
   context, not values for a run. Never copy one onto a run unless the scientist says it applies.
7. **Who produced the data** comes from the scientist. A PI name in the folder name is only a hint
   to offer ("Is this Dr. X's group?"), never an answer.
8. **Never open these by hand:** `bundle.json`, `runs.json`, `reading.full.json`, the groups file,
   `processing_results.json`. Never paste a large file. Use `isaac bundle list/show` pages and `summary.md`.
9. **Never upload, never ask for or print a portal key.** `upload` is `--dry-run` only.
10. **Say what you checked and what you did not.** Never claim "fully verified".

## Step 0 · Check the setup

Find the ISAAC folder: the path in `checkout-path.txt` beside this file. If there is no such file, ask
the scientist where their ISAAC folder is (the one with `scripts/setup_isaac_local.sh`); if they have
none, point them to `docs/local-skill-quickstart.md` and stop. Then run, from that folder,
`scripts/setup_isaac_local.sh --check` (changes nothing): one `[ok]`/`[missing]` line each for the Python
environment, the command, the processing extra and the portal check, then the skill copy in
`~/.claude/skills` (or `--skill-dir`): `[ok]`, `[stale]` or `[skipped]` (none installed there). Use
`<folder>/.venv/bin/isaac` as `<isaac>` and `<folder>/.venv/bin/python` as `<python>`.

- `[stale]`, or (`[skipped]`, or this copy runs from elsewhere) it differs (`reference/troubleshooting.md`)
  → `scripts/setup_isaac_local.sh --install-skill`, restart Claude Code; do not continue on this copy.
- command missing → the ONE fix is `scripts/setup_isaac_local.sh` (then `--install-skill` if there
  was no `checkout-path.txt`); stop.
- processing or portal check missing → say what it costs ("curves and quality checks need
  `scripts/setup_isaac_local.sh --with-processing`"; "records cannot reach *exportable* without
  `scripts/install_portal_validator.sh`") and continue with whatever is available.

## Step 1 · Data flow and their name, BEFORE reading anything

Read `reference/data-flow-and-consent.md` and ask its question. In short: the folder (name only),
that ISAAC's code reads it on this computer with no network, and that **anything I open myself, and
every command output I see, is sent to the Claude model service.** Ask them to confirm they are
allowed to let Claude read this data (`docs/local-first-data-flows.md`), and ask their name: it is
recorded with the consent and every answer (`--by "<name>"`; ask once, reuse it). Say that Step 3, a
spot check where I read a few files before seeing what ISAAC found, can be skipped if they don't
want it. Record their answer in your next message.

- **Yes** → continue.
- **No / not sure** → deterministic mode: run `<isaac> import` and nothing else (it prints counts, no
  content). Open no source or bundle file; give the scientist the other commands to run themselves.
  Stop there unless they change their answer.

## Step 2 · Import

`<isaac> import <folder> --out <bundle>` (`<bundle>` outside the source folder; ask before
overwriting; `--force` only on request). Then read **only** `<bundle>/summary.md`. Tell the
scientist, in 4 lines, what was found: files, runs, conflicts, how many files no reader could open
(import prints these); which `summary.md` counts not to quote, and how to say its conflicts, is in
`reference/records-and-validation.md` ("Reading summary.md"). The question count comes in Step 7;
running it now would show values before the spot check. Import refused (exit 3/4/5): see troubleshooting.

## Step 3 · Blind cross-check (BEFORE any command that prints a value)

Read `reference/blind-crosscheck.md`. Order matters: `crosscheck-plan` → pick the high-value
targets (sample identity, potential/reference, reaction, environment, cell type, acquisition time) →
`excerpt` (raw source text, no parser value) → write what you read → `annotate --blind` →
only then `reveal` to compare. Once a target's value has been printed (`show`, `list candidates`,
`reveal`), its reading is no longer blind and `annotate` records that honestly. Report coverage as
"I independently read 8 of 116 high-value items (5 blind)", never as verification. Skip this step if
the scientist does not want it; say that it was skipped.

## Step 4 · Read what code could not

`<isaac> bundle list <bundle> unread --limit 50` (page). Read `reference/reading-unread-files.md`.
Logbooks, beamtime notes and proposals first. A filled ISAAC metadata sheet in the folder: ask now
whether it is theirs and to use it (if yes: `template adopt`, Step 7). For `.docx/.pptx/.xlsx` run
`<python> -m isaac_api.local_import.extract <file> --root <folder> --out <bundle>-notes/extracted` and
read what it returns; open images, PDFs and plain text with the Read tool. Then read what code DID
read for statements no parser maps (readmes, macro comments, run labels). Read only inside the
approved folder: name a document beside it and ask before opening it. Write every finding to ONE
findings file; load it with `annotate --from-readings` (preview, then `--apply`), naming runs by
`stem` or `run_id` from `bundle list <bundle> runs`, never by `label`. Tell the scientist what each
file held, and which binaries nobody could read.

## Step 5 · Groups

If `<isaac> bundle group --help` fails, say "grouping is not in this build", skip Steps 5, 6, 8 and
9, and after Step 7 go to Step 10. Read `reference/grouping-and-processing.md` (every decision's syntax is there).

1. `<isaac> bundle group <bundle>` proposes groups.
2. **The counter question comes first.** `<isaac> bundle questions <bundle> --scope experiment` shows
   `naming_counter_positions` (which file-name positions hold a running counter) when grouping asks
   it. Ask it before confirming any group: a regroup keeps decided groups, so a later answer can no
   longer join them. Record `set_counter_positions` (or `set_not_counter_positions`; "I don't know"
   is `defer`, and grouping stays as it is), say its `regroup_preview.statement` (what it would join),
   then `<isaac> bundle group <bundle> --regroup` (replaces undecided groups only).
3. **Apply the findings file again** (`annotate --from-readings`, preview then `--apply`) now and after
   every later regroup: absorber findings are skipped until groups exist and do not move to new groups.
4. Page groups with `<isaac> bundle list <bundle> groups --limit 10` and the merge candidates (paging is
   in the reference). Present each in plain words: sample, conditions, how many scans, why runs were split
   ("these two differ in potential"). Say a merge candidate's `caution` before asking about it, and the care
   flags in words: `merged_despite_engine_reading` (the importer read a difference), `sample_key_basis: name_stem` (no file states the sample).
5. Ask the scientist to **confirm, split or merge** each, in batches, with progress. A group that is
   not a result (alignment, a reference foil, a test scan) can be **left out** with `reject`; say it is
   never exported. Several accepted as shown: list each back, then one `--targets-file` confirm; never
   include a group with a `cannot_export_reason`: say why (no curve can ever be made for it) and offer
   `reject` or leaving it unconfirmed. A `--same-conditions` merge needs a yes to "same sample AND same
   conditions? the names differ in: …"; `pristine`/`cycled` are conditions, not labels. After a
   regroup, say any `merge_decisions_not_combined` in words and offer its `next_commands`.

## Step 6 · Processing (a DRAFT protocol)

`<isaac> process <bundle> --source <folder>` once groups are confirmed. Always pass `--source`, the
folder that was imported (the bundle records it only with `import --record-local-root`); without a
readable one `process` refuses and writes nothing. After a ZIP import, ask the scientist to unzip it
outside the bundle, and confirm the unzipped folder is the data they approved. Read the Processing
section of `reference/grouping-and-processing.md`. Page results with
`<isaac> bundle list <bundle> processing-results --limit 20`. For each group show the verdict in words,
glitch flags (with `glitch_check_few_scans`, say its sentence instead), skipped scans, agreement with
their own Athena output, and the plot (open the PNG with Read and describe it). Ask approve / reject / needs changes.

- **Approval is the scientist's call.** A `warn` is theirs to accept. A `fail` for `edge_step_implausible`,
  `no_edge` or `post_edge_not_at_1` is never offered for approval: offer reject or `needs_changes`. When
  approving, ask for the QC status: map their words to one of the four
  (`--qc-status valid|compromised|failed|pending`), say it back, record on yes; never derive it from the verdict.
- **Two results for one group**: ISAAC's curve (`…-isaac`) and their own Athena curve (`…-athena`).
  Show both, say which scans each used, ask which is the record's, approve exactly one.
- A `not_applicable` result is not a fail; never ask to approve it ("no ISAAC processing protocol
  covers this data yet"). A result with **no curve** cannot be approved; offer: reject the result,
  `needs_changes`, or leave the group out.
- A calibration shift (`approve_calibration --element --edge`, in the reference): before asking the element
  and edge, say how many scans show a reference edge and the shift it would apply; never ask when no
  reference is proposed. No answer, no shift. Above 2 eV it needs `--accept-shift` on their yes.

Always say: **the processing protocol is a draft until the ISAAC processing reviewers (Oscar and
Angel) review it**; an approval means "I looked at this curve and accept it for this record", not
"the method is validated". If processing is not installed, say what that costs (no curves, records
stay incomplete) and continue.

## Step 7 · Questions

Read `reference/questions-and-decisions.md`. Use the consolidated list, never the raw one. Each
question has plain text, why it blocks export, hints (a hint is never an answer) and an
`answer_command` template; allowed values are in `allowed_values_by_field`. A question blocks only
when a live group's record needs it. Ask 3 to 5 per message, by theme, with progress, in this order:

1. **The minimum for one group.** `<isaac> bundle questions <bundle> --blocking-only --limit 10` →
   `minimum_for_one_group`: "N answers make the <sample, conditions> group exportable". Answer its
   `questions` (with `--only <only>` when set), then its `unasked_required` items, then its `plus_decisions`.
2. **Experiment-scope questions, once**: "this applies to N groups; answer once, or tell me which
   groups differ" (`--only group:<id>` overrides one group). `clock_time_zone` needs the zone the
   instrument clock was set to (an IANA name); never suggest one.
3. **The template**, for everything the files never state (see below); ask per group only what it leaves.
4. **Conflicts that affect a record.** `affects_record: false` ones change no record: give their count.
5. **The rest, if they want**: optional questions (`--scope group:<id>` shows what blocks one group).

A deferred question sorts last; do not re-ask it unless they offer. How to put each kind of question
is in the reference; in short:

- **Closed lists.** Map their words to one allowed value, say it back ("in situ → `in_situ`,
  right?") and record it only on their yes. A confirm question states the value it records: say it back.
- **No value yet** (no `confirm` in `allowed_decisions`): never invent one; ask, then `correct --value`.
- **Not asked**: `informational` questions (mention their count once) and `covered_by` ones (answered
  by that experiment question; ask per group only if a group differs).
- **Asked again** or **no reading fits**: give the reason, show the allowed values or `utc_readings`, ask.
- **An answer not on the list**: if no allowed value fits and they keep their own word, run
  `decide … --value "<their exact word>" --as-said` once: it records no decision but keeps their word as a
  vocabulary request (`--note`: their own words, or nothing). Never pass a word they did not say.
  Offer `<isaac> bundle propose-terms <bundle> --out <bundle>-notes/terms.json`. They write each
  description themselves on the Schema Proposals page, never in the file and never by you. Saving a proposal
  sends the term, counts and file-name citations to the ISAAC server the page uses; say so before they save.
  Say which terms come only from my readings (`by_origin.ai_reading`); draft one only if they want it.
- **Absorber.** Say the element and edge back; record it only on a clear yes to that pair.
- **AI readings are not file evidence**: say "my reading of the files suggests…", never "the files say".

**The template.** For who produced the data, domain, environment, cell type, reaction with its drive
and catalysis, sample form and formula, facility: "I can give you one spreadsheet to fill in one
sitting." `<isaac> bundle template export <bundle> --out <bundle>-notes/template.xlsx` (answer cells
empty; `ISAAC Suggestions` shows what each run's own files say; every `--out` of `template export`,
`adopt` and `propose-terms` goes in `<bundle>-notes/`). On its return,
`<isaac> bundle template import <bundle> <file.xlsx> --by "<name>"` previews; read back every invalid
cell, clash, replaced or contradicted file reading, beamtime-wide cell and unread column, and add
`--apply` only on their yes. Never fill the sheet for them; never import ISAAC's blank template. **They already filled ISAAC's template and say to use it:**
`<isaac> bundle template adopt` (see "The scientist's own filled sheet" in the reference).
They may also answer on the local-only *Local Imports* page (see the reference); run `bundle questions` again after.

## Step 8 · Build and validate

`<isaac> bundle build-records <bundle>` (counts and the first 3 drafts; `--full` prints all) then
`<isaac> bundle validate <bundle>`. If it reports `nothing_validated`, no group is confirmed yet: go
back to Step 5. Read `reference/records-and-validation.md`; explain the verdicts from validate's
`by_reason`, `missing_required_by_field` and `not_exportable_first` in plain words with the exact fix
(open `validation/<group_id>.json` only for a group those leave unexplained), then go back to the
step that fixes it (a `processing_fix` means its curve needs approval in Step 6). Say each `warnings`
item in words (only 5 warnings show by default; `validate --full` lists all), and ask the scale question it
names (and the set-point if `also_needs`); run its command only with their answer. Never edit a draft or relax a check.

## Step 9 · Export and dry run

`<isaac> bundle export <bundle> --out <records>` writes only `exportable` records. Read its `outcome`
("Wrote N record(s), refused M group(s)"), not its exit code (see `reference/records-and-validation.md`),
then its refusal counts. **If nothing is exportable**, export writes nothing: skip the dry run, say
"no record is ready yet", name what blocks the nearest group (from Step 8), and go to Step 10.
`<isaac> bundle upload <records> --dry-run` shows what *would* be sent: summarise it (how many
records, where to) and say **nothing was sent and this build cannot send**. The scientist uploads
through the ISAAC portal themselves.

## Step 10 · Final summary

Close with a short plain summary: records exported (count, names); records blocked and why;
which values were read by code, which by Claude (suggestions), which confirmed by the scientist;
what was not checked (the high-value items not cross-checked, files nobody could read,
processing still draft); where the files are; and the one next action.
