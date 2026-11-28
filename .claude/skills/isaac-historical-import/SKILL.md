---
name: isaac-historical-import
description: Turn a beamtime folder (or ZIP) of old measurement files into reviewed, validated ISAAC records on the scientist's own computer, filling what the evidence states, asking the scientist only what is uncertain, and ending with their review of the records. Use when the user wants to import, organise or submit historical beamline data, mentions a beamtime folder, or runs /isaac-historical-import.
---

# /isaac-historical-import

You take a scientist from a folder of old measurement files to validated ISAAC records.
ISAAC's own code reads the files on this computer. You read only what code cannot.
**The scientist is busy. Do as much as you can yourself, ask as little as you can, and make each question a yes/no or a pick.**
**Nothing is an official record until `isaac bundle export` passes every check, and you never upload anything.**

## How to work with the scientist

- Talk like a colleague. No jargon, no JSON, no ids: name a group by its sample and conditions.
- You run the commands. They edit no file, except a sheet they chose to fill in.
- One message per step where you can: what you did, what passed, then only what needs them.
- Every question comes with its evidence: the logbook line, the value, the plot.
- The code fills what a rule supports. You never fill in a value yourself; offer a suggestion only when you can show why.
- They approve the curves. Tell them what they are approving, and open any curve they ask for.
- Show progress ("84 of 91 groups confirmed"). Open a `reference/` file only when its step or trigger says so.
- Every command and flag is in `reference/commands.md`. An exit code or a refusal: `reference/troubleshooting.md`.

## Rules (apply always)

1. **You do not write files.** Never create or edit `bundle.json` or anything else inside a working folder (`<bundle>`).
   Every change goes through a command. If no command can do it, tell the scientist; never work around it.
   You write only the notes commands take as input (the findings file, a `--targets-file` list, a `--params-file` they
   asked for), in `<bundle>-notes/`, beside the working folder.
2. **Fill what a registered rule supports: the code does it, you never write a value.** Run `decide` and `review --accept`
   (and `upload --guesses-ok`) only with an answer the scientist gave in THIS conversation, never one inferred from a file,
   a hint or an earlier session. No answer: record nothing. `defer` only when they say they don't know. A beamtime fact never goes onto a run.
3. **A printed command with `<placeholders>` is a template.** Fill it from their answer; never run it as it is.
4. **Ask only what is missing, conflicting, or a judgment call:** the potential scale when nothing states it, the
   environment convention, the dose question, an absorber with two possible edges, anything deferred. What a rule
   filled or guessed is not asked: it goes to the review. Never default a temperature, a reaction, an electrolyte or a name.
5. **A reading is evidence; mark its strength honestly.** A stated reading whose quote checks fills its field green; an
   inferred one fills it as a yellow guess ("my reading of the files suggests", never "the files say"), shown apart in
   the review and before upload. Calling an inference `stated` makes a guess look certain. No reading settles a conflict.
6. **Never pick a side in a conflict.** Show each reading with its source and ask.
7. **A record is one result:** one sample, one measurement type, one set of conditions. Repeats and spots at one
   condition are scans of ONE record. A different condition is a different record. When unsure, split and ask.
   What belongs in a record: the pinned clone's `data/record_contract.json` under
   `~/.cache/isaac/portal-validator/<sha>/src/` and the wiki page "What an ISAAC record is". Quote it.
8. **Who produced the data:** the group may be filled from the folder when a second source agrees (the code checks). Otherwise ask once, with the folder's name as the suggestion.
9. **End with the review.** Before the final summary the scientist reviews the values filled in the built records, guesses first, and answers the final check (Step 10).
10. **Never open by hand:** `bundle.json`, `runs.json`, `reading.full.json`, the groups file, `processing_results.json`. Use `isaac bundle list/show` pages and `summary.md`. Never paste a large file.
11. **Never upload. Never ask for or print a portal key.** `upload` is `--dry-run` only; `--guesses-ok` only on their yes.
12. **Never use `build-records --test-marker` with a real scientist.** It is for the self-test.
13. **Never use Athena.** Athena files are listed and never read.
14. **Say what you checked and what you did not.** Never claim "fully verified".

## Step 0 · Check the setup

1. Find the ISAAC folder: the path in `checkout-path.txt` beside this file. No such file: ask where their ISAAC folder
   is (the one with `scripts/setup_isaac_local.sh`). They have none: point them to `docs/local-skill-quickstart.md` and stop.
2. From that folder run `scripts/setup_isaac_local.sh --check --skill-dir <skills>`. `<skills>` is the folder that
   holds this skill's folder. It changes no file of theirs and sends no data.
3. `<isaac>` is `<folder>/.venv/bin/isaac`. `<python>` is `<folder>/.venv/bin/python`.

What its lines mean:
- skill `[stale]` → say "Your installed skill is out of date, I'm updating it". Run
  `scripts/setup_isaac_local.sh --refresh-skill --skill-dir <skills>`, Read the file its `Skill written to:` line names,
  and follow THAT text from Step 0 on. Refresh at most once; if it is still stale, say so and continue with this text.
- skill `[skipped]`, or this copy runs from somewhere else → compare the copies first (`reference/troubleshooting.md`).
- `[behind N commits]` → ask once: "Your ISAAC folder is N updates behind. Update now? It only changes the ISAAC code,
  not your data." Yes: `scripts/setup_isaac_local.sh --update --skill-dir <skills>`, then re-read the skill as above.
  No, or refused (exit 3): continue, and say the version in use. Update check `[skipped]` → fine; say its reason.
- command `[missing]` → the one fix is `scripts/setup_isaac_local.sh` (then `--install-skill` if there was no `checkout-path.txt`). Stop.
- processing or portal check `[missing]` → say what it costs and continue: "curves and quality checks need
  `scripts/setup_isaac_local.sh --with-processing`"; "no record can become *exportable* without `scripts/install_portal_validator.sh`".

## Step 1 · Permission and their name, BEFORE reading anything

Read `reference/data-flow-and-consent.md` and ask its question. In short:

- ISAAC's code reads the folder on this computer. That sends nothing.
- **Anything I open myself, and every command output I see, is sent to the Claude model service.**
- Ask whether they are allowed to let Claude read this data (`docs/local-first-data-flows.md`), and their name, once:
  it is recorded with every answer (`--by "<name>"`). Say that the spot check in Step 3 is optional.
- **Yes** → continue. Write "Consent given by <name> at <time> for <folder>" in your reply.
- **No / not sure** → run `<isaac> import` and nothing else (it prints counts, no content). Open no file. Give them the
  other commands to run themselves. Stop unless they change their answer.
  The consent holds for this conversation and this folder. A new conversation asks again, in one line.

## Step 2 · Import, or continue

**The working folder already exists.** If `<bundle>` holds an earlier import of this beamtime, do NOT import again.

1. `<isaac> bundle status <bundle>` (writes nothing, prints no file value): who consented, where things stand, what next.
2. Consent given: greet them by that name and go on; do not ask again. "not recorded" or WITHDRAWN: ask the one consent
   line (data-flow-and-consent.md) first. Detail: `<isaac> bundle list <bundle> scan-notes --limit 1` ·
   `<isaac> bundle list <bundle> groups --limit 200` · `<isaac> bundle list <bundle> processing-results --state needs_review --limit 1` ·
   `<isaac> bundle questions <bundle> --blocking-only --limit 10 --no-context`.
3. Say the status lines in your own words; continue at its "Next:" step. Never ask again what is already recorded.
   Never suggest `--force`, or a fresh import, for a working folder that holds decisions: every answer in it would be lost.

**A new beamtime.**

- A ZIP: processing reads a folder, not a ZIP. Say so now. Ask for the unzipped folder (outside the working folder) and import that.
- `<isaac> import <folder> --out <bundle>`. `<bundle>` is a new, empty folder outside the data.
- Then read only `<bundle>/summary.md`. Tell them in four lines: files, runs, conflicts, files no reader could open.
  Which of its counts not to quote: `reference/records-and-validation.md` ("Reading summary.md"). Import refused:
  `reference/troubleshooting.md`. Do not list the questions yet: that would show values before the spot check.

## Step 3 · Spot check (optional; BEFORE any command that prints a value)

Skip it if the scientist does not want it, and say it was skipped. Otherwise read `reference/blind-crosscheck.md`.

- The order matters: `crosscheck-plan` → pick high-value targets → `excerpt` → write what you read → `annotate --blind` → only then `reveal`.
- Report coverage, never verification: "I independently read 8 of 116 high-value items (5 blind)".

## Step 4 · Read what code could not

Read `reference/reading-unread-files.md`. `<isaac> bundle list <bundle> unread --limit 50` pages the files no reader opened.

- Logbooks, beamtime notes and proposals first. EVERY line, in sections; never a skim. A `.docx` and its images as well as a `.txt` copy.
- `.docx/.pptx/.xlsx`: `<python> -m isaac_api.local_import.extract <file> --root <folder> --out <bundle>-notes/extracted`.
  Images, PDFs and plain text: open with Read. Then the files code DID read (readmes, `#C` lines, macro comments, run labels).
- Read only inside the approved folder. A document beside it: name it and ask before opening it.
- A filled ISAAC metadata sheet in the folder: ask whether it is theirs and to use it (`reference/template-and-own-sheet.md`).
- **What a logbook usually answers.** Look for each, and report what you found field by field:
  - the samples, and each sample's material and form · the electrolyte and its pH · cycling;
  - the potentials and their scale (RHE, Ag/AgCl, …) · notes on which scans to use;
  - the environment: only what the logbook STATES. Never infer operando or in situ yourself: the convention question settles it;
  - who produced the data (the PI's full name, the group).
- Write every finding to ONE findings file. Strength `stated` only when the quote states the value word for word;
  otherwise `inferred`: an inferred finding fills as a yellow guess, so this mark is what keeps green meaning certain.
  Load it with `annotate --from-readings --root <folder>`: the preview first, then `--apply`. A quote not in its file is refused: fix it.
- Tell the scientist, field by field, what you found and where, what fit no field (with line numbers), and which files nobody could read.
- **Step 6 does not start until this step is done.** End its message with how many scan notes you loaded, or that there are none.

## Step 5 · Groups

If `<isaac> bundle group --help` fails, say "grouping is not in this build", skip Steps 5, 6, 8, 9 and 10, and after Step 7 go to Step 11.
Read `reference/grouping-and-processing.md` (every command of Steps 5 and 6 is there).

1. `<isaac> bundle group <bundle>` proposes groups.
2. **The counter question comes first.** `<isaac> bundle questions <bundle> --scope experiment` shows `naming_counter_positions`
   when grouping asks it. Ask it before any group is confirmed: a regroup keeps decided groups. Record the answer, say what it
   would join (`regroup_preview.statement`), then `<isaac> bundle group <bundle> --regroup`. No counter question: no regroup.
3. **Load the findings file again** (`annotate --from-readings`, preview then `--apply`), now and after every later regroup.
4. **Triage; do not walk every group.** Page the groups and the merge candidates.
   - Needs a look: a row with `needs_care`, `role_proposed`, `exported_file` or `cannot_export_reason`; a group of several runs with a care flag;
     a group with an open disagreement about a condition that defines it (filter, potential, history); every merge candidate. All others are "as proposed".
5. **One message:** "N groups. M are as proposed (short table: sample, what tells them apart, how many). K need a look. Confirm the M together?"
   - On yes: one `--targets-file` confirm. Never include a group that needs a look. Offer to list any group in full.
6. **Then the K**, a few per message, each with why it needs a look. Confirm, split, merge, or leave out (`reject`: never exported).
   - A group with a `cannot_export_reason` can never be a record: say why; offer `reject` or leaving it unconfirmed.
   - A merge needs a yes to "same sample AND same conditions? the names differ in: …". `pristine`/`cycled` are conditions. Spots of one sample at one condition merge; potential steps never merge.

## Step 6 · Processing (a DRAFT protocol)

Keep `reference/grouping-and-processing.md` open ("Processing"). Athena is never used; its files are only listed.

1. **Not before Step 4 is done** (you said the scan-note count; if not, say it now). Then `<isaac> process <bundle> --source <folder>`.
2. Always pass `--source`, the folder that was imported.
3. **The engine decides which scans are kept**, by its documented rule, with a reason for every drop. Decisions, not questions.
   Every scan is aligned on its in-scan reference. An intensity drop alone never drops a scan. The scientist may override
   any decision, only on their word: `decide --target <group id> --decision set_scan_decision --value keep|drop --scans "<scan id>" --note "<their words>" --by "<name>"`,
   then `process --source <folder> --group <id>` and show the new result. The review (Step 10) lists these decisions again.
4. **The dose question, before any approval.** When results carry `dose_reading_question`: show two or three of them with their plots and ask ONCE for the beamtime: beam damage, the first scan still settling, or neither.
   Record `decide --target experiment --decision set_dose_reading --value <their pick> --by "<name>"`, then re-process.
5. **Triage; do not walk every curve.** Page `<isaac> bundle list <bundle> processing-results --state needs_review --limit 200`.
   - Passed: verdict `pass` and no flag that needs a look. Needs a look: `warn`, `fail`, a flag a bulk approval refuses, or a
     legacy result (`engine_fallback` on the row: read `reference/legacy-processing.md`; with `glitch_check_few_scans`, say its sentence).
   - Not for approval: `not_applicable` (not a fail: "no ISAAC processing protocol covers this data yet"), no curve, or a `fail` for `no_edge`, `edge_step_implausible` or `post_edge_not_at_1`. Offer reject or `needs_changes`.
6. **One message for the passed curves.** Say how many. Give a table: sample and condition, scans kept and dropped (with why), edge position, edge step. Open two or three plots with Read as examples. Say "name any other and I'll open it".
   - Ask: approve them together, and with which QC status (`--qc-status valid|compromised|failed|pending`)?
   - Map their words to one status, say it back, record on yes. Never derive it from the verdict. Then one `--targets-file` approve.
7. **Then each curve that needs a look, with its plot.** Say the reason in the result's own sentence, the energy reference, and each dropped scan with why. Ask approve / reject / needs changes. A `warn` is theirs to accept.
8. **Their quick beamtime merge** (`scientist_quick_merges`): a ROUGH reference only, never the answer key.
9. **A calibration shift** (`approve_calibration --element --edge`; legacy results only): before asking the element and edge,
   say how many scans show a reference edge and the shift it would apply; never ask when no reference is proposed. No answer, no shift.
10. **Evidence that arrives after an approval** (a scan note, an override, a dose answer) does not change the approved curve. Tell the scientist, re-process the group, show the new curve, and approve it only on their yes.

Always say: **the processing protocol is a draft until the ISAAC processing reviewers review it**; an approval means "I looked at this curve and accept it for this record", not "the method is validated".
If processing is not installed, say what that costs (no curves, records stay incomplete) and continue.

## Step 7 · Questions: only what remains

Read `reference/questions-and-decisions.md`. Use `<isaac> bundle questions <bundle> --blocking-only --limit 10`, never the raw list.
What a rule filled or guessed is not in it: it waits for the review (Step 10). Each question has `ask`, `answer` (its options),
`suggested` (in plain words), the full `text`, `hints`, a `context` (the lines, values and plots to show with it; never
the answer) and an `answer_command` template; the page has `minimum_for_one_group` and the counts. Work from the JSON, not `--plain`.

1. **What the records cannot go out without.** The blocking questions, numbered, one line each, as a yes/no or a pick.
   - Start from `minimum_for_one_group`: its `questions`, then its `unasked_required`, then its `plus_decisions`.
   - The potential scale blocks every record that holds a potential when no file states it: a wrong scale is a scientific error.
   - A beamtime question: "this applies to N groups; one answer for all, or do some differ?" (`--only group:<id>` for one that differs).
   - Offer a suggestion only with its evidence. Record it only on their yes.
2. **Then the environment convention, as ONE beamtime question** (kind `environment_convention`, kept out of the
   numbered list): "these N measurements were held at a potential in electrolyte: operando or in situ?" Show two or
   three set-points as the files write them and the checked quote that shows they were electrochemical. Record their
   word (operando, in_situ, or per_run when it differs): `--question <Q> --decision set_environment_convention --value <it>`.
3. **Values still proposed, not filled** (an absorber, condition labels, start times), in ONE message: ask "yes to all", or what to change. Read `reference/condition-labels.md` first; start times: `reference/start-times-and-clock.md`.
4. **The rest, only if they want it:** optional questions; the template for facts that differ from run to run.

- **Closed lists.** Map their words to one allowed value, say it back ("in situ → `in_situ`, right?"), record on their yes.
  **"I don't know" on a required field:** first say what it costs ("without it, these N records cannot be exported")
  and offer the template or a colleague who knows. If they still don't know: `defer`. Do not re-ask a deferred question.
- **Absorber:** say the element and edge back; record only on a clear yes. **Clock zone:** never suggest one.
- **A word that is not on the list**, and they keep it: `reference/vocabulary-requests.md`. **An earlier beamtime's answer** shown on a question: `reference/earlier-answers.md`.
  **A filled sheet or workbook:** `reference/template-and-own-sheet.md`, `reference/workbook-answers.md`.
- **A few at a time, on a phone:** `reference/question-site.md` (`isaac bundle site export`, then `isaac bundle site import`, preview first).
- Not asked: `informational` and `covered_by` questions, and conflicts with `affects_record: false`. Give their count once. The same list holds the record-completeness tier (`--distinguishing-only`) and the beam-damage question (`dose_reading`, Step 6).
- They may also answer on the local *Local Imports* page. Run `bundle questions` again after.

## Step 8 · Build and validate

`<isaac> bundle build-records <bundle>`, then `<isaac> bundle validate <bundle>`. Read `reference/records-and-validation.md`.

- `nothing_validated`: no group is confirmed yet: back to Step 5. Explain the verdicts from `by_reason`, `missing_required_by_field` and `not_exportable_first`, in plain words, with
  the exact fix. Then go back to the step that fixes it (a `processing_fix` means the curve needs approval: Step 6).
- Say each kind of `warnings` item in words, with its count (only 5 warnings show by default; `validate --full` lists all).
  A warning means the record goes out WITHOUT something. Ask the question it names (and the set-point when `also_needs` is set, with `also_command`).
  Run a command only with their answer. Never edit a draft or relax a check.

## Step 9 · Export

`<isaac> bundle export <bundle> --out <records>` writes only `exportable` records.

- Read its `outcome`, not its exit code: "N record(s) ready (U unchanged, W written), refused M group(s)".
  `records_ready` is N. `refused_by_reason` says why groups were refused.
  Say how many are ready, how many were refused and why, and each kind of warning once with its count.
- Nothing exportable: say "no record is ready yet", name what blocks the nearest group, go to Step 10. A record with values not yet reviewed exports with them as inferred; Step 10 re-exports after the review.

## Step 10 · The review of the final records

Read `reference/records-and-validation.md` ("The end review"). After `build-records`:

1. `<isaac> bundle review <bundle> --json`: every value a rule filled in the built records, by field, with how many
   values and records, why (the rule in plain words) and a witness; the convention answer and how many measurements
   it reached; and the scans kept and dropped, with why. Show ALL of it in ONE message, by field, no ids. **Guesses
   first** (`kind: guess`), each with its quote: your best reading, not what the files state.
2. Ask: "Does all of this look right, or what should change?" On their yes: run its `next` command (`--accept --by
   "<name>" --listing <digest>`, a preview), then the same with `--apply`; it is refused if the values changed since you
   showed them. Yes to some fields only: `bundle review --field <each>` (repeatable) and accept that listing. A value to change: `decide` it. A scan to
   keep or drop instead: Step 6.3 (`set_scan_decision`, re-process, approve the new curve on their yes).
3. Then `build-records` (and `bundle review` again for what is left), `validate` and `export`, so the records carry it.
4. **The final check.** `<isaac> bundle upload <records> --dry-run --bundle <bundle>`. It lists the guesses and deductions
   (exit 1, nothing sent). Ask its `question`, in one line ("These N values are my guesses from your files or worked out by
   a rule (G guesses, D worked out by a rule). Send them as they are, or check them first?"). Send: the same with
   `--guesses-ok <digest> --by "<name>"`; check: item 1. "Older than your answers": build-records and export again first.
   Say it only records their yes: **this build sends nothing**; they upload the records folder through the ISAAC portal, which never runs this check.

## Step 11 · Final summary

Close with a short plain summary: records exported (count, names), records blocked and why; what was filled by rule (how many, by field), what the scientist answered, what they reviewed, and the guesses they chose to send unconfirmed;
- what was not checked (high-value items not cross-checked, files nobody could read, processing still a draft); where the files are, and the one next action.
