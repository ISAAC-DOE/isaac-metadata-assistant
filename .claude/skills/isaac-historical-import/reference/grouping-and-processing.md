# Groups and processing (Steps 5–6)

Read this at Step 5 and keep it for Step 6. It covers the usual case: fluorescence or HERFD scans.

Open `legacy-processing.md` only when one of these happens:

- a result's row has `engine_fallback` (its protocol is `isaac.xas.v0`: a transmission sample, an alignment group, another file format);
- a result proposes a calibration shift;
- the scientist asks for a changed processing setting (`--params-file`).

A refusal from any command says why and what to do next. Read it back in plain words; do not work around it.

## Groups

A record group is the runs that become ONE record: one sample, one technique, one set of conditions.

- Repeats and spots of one sample at one condition belong in one group.
- Potential steps never merge. Each potential is its own group.
- The code proposes groups and splits whenever something differs or is unknown. It never merges silently.
- Beamtime-wide notes are not group members.

### Order

1. `<isaac> bundle group <bundle>` proposes groups.
2. The counter question (below), then `<isaac> bundle group <bundle> --regroup`.
3. Load the findings file again (absorber findings need groups; do this after every later regroup too).
4. Triage, then confirm.

A regroup keeps every decided group. So a counter answer given after a group is confirmed can no longer join it.

### The counter question (`naming_counter_positions`)

`<isaac> bundle questions <bundle> --scope experiment` lists it first when grouping asks it.
It asks which positions of the file name hold a running counter, not sample identity.

- Its text shows real file names with the asked token in brackets. Show them as they are.
- Ask: "does that number only count repeats of one measurement?"
- Yes: `<isaac> bundle decide <bundle> --target experiment --decision set_counter_positions --positions 2,3 --by "<name>"`.
  Use `--positions last` when the counter is always the last token.
- The reply's `regroup_preview.statement` says what the answer would join. Tell the scientist, then regroup.
- No: `<isaac> bundle decide <bundle> --target experiment --decision set_not_counter_positions --positions 2 --by "<name>"`.
  Grouping is unchanged. The reply names the merge candidates whose names differ only there
  (`said_not_counter_merge_candidates`). If the scientist says they are all distinct, run the one `keep_apart`
  command the reply prints.
- "I don't know": `<isaac> bundle decide <bundle> --target experiment --decision defer --by "<name>"`. Grouping stays as it is.
- Never guess a position.
- **No counter question in the list:** skip this step. Ask nothing and do not regroup.

### Triage: one confirm for the plain groups, a look at the rest

Page every group: `<isaac> bundle list <bundle> groups --limit 200`, and `<isaac> bundle list <bundle> merge-candidates --limit 200`.
A list returns one page. When it says `"more": "… --offset N"`, run it again until no `more` is left before you count.

A group needs a look when its row has any of these:

| On the row | Say | Ask |
|---|---|---|
| `needs_care` | it merges scans read at different conditions; `<isaac> bundle show <bundle> group <id>` gives the readings | one group, or split? |
| `role_proposed` | "judged from the file name to be a reference / an alignment scan" | is it a sample? (`set_role`, below) |
| `exported_file` | their own exported file of the run is kept as context; its data is not merged | nothing; say it |
| `cannot_export_reason` | it can never become a record as it stands (reasons below) | leave it out (`reject`), or leave it unconfirmed |
| `members` 2 or more | check `bundle show <bundle> group <id>` for `merged_despite_engine_reading` (the importer read a difference) or `sample_key_basis: name_stem` (no file states the sample; grouped by file name) | one group, or split? |

A group also needs a look when the files disagree about a condition that defines it.

- `<isaac> bundle list <bundle> conflicts --limit 200` shows the open disagreements.
- One about a condition in the row's `conditions_named` (filter, potential, cycling history, electrolyte) holds the
  confirm: show both readings with their sources ("the file name says filter 20; every scan header says 10") and ask.
  Several groups with the same disagreement are one question.
- One about anything else (a comment, a unit spelling, a field that does not define the group) does not hold the
  confirm. It is asked in Step 7.

A group of one run merges nothing, so it needs no `bundle show`: its row is enough.
Every merge candidate is also a look. Say its `caution` sentence before asking about it.

All other groups are "as proposed". Put them in ONE message:

> 91 groups. 84 are one sample at one condition each. They differ by potential, filter and cycling history, as the
> file names say (table). 7 need a look; I'll show those next. Confirm the 84 together?

- Give a short table: sample, what tells its groups apart (`conditions_named`), how many groups, how many scans.
- Offer to list any of them in full. Name a group by its sample and conditions, never by its id.
- On their yes: write the ids to `<bundle>-notes/groups.txt` (the notes folder beside the bundle, one id per line), then
  `<isaac> bundle decide <bundle> --targets-file <bundle>-notes/groups.txt --decision confirm --by "<name>"`.
- Never put a group that needs a look in the bulk confirm. The command would accept it without a word.
- Then show the ones that need a look, a few per message, with progress ("3 of 7 looked at").

### Group decisions

- **Confirm one:** `<isaac> bundle decide <bundle> --target <group id> --decision confirm --by "<name>"`.
- **Leave out** a group that is not a result (alignment, a test scan): `--decision reject`. Say it is never exported.
- **What it is:** `<isaac> bundle decide <bundle> --target <group id> --decision set_role --value sample --by "<name>"`
  (`sample`, `reference` or `alignment`). The latest answer wins.
- **Split:** ask which runs go where, in file names. Then
  `<isaac> bundle decide <bundle> --target <group id> --decision split --split-into '[["<run key>","<run key>"],["<run key>"]]' --by "<name>"`.
  - A run key is an entry of `member_run_keys` in `bundle show <bundle> group <id>`. It is not the `run_id` or `stem`.
  - One list per group to make. Together they name every run exactly once. At least two lists.
  - The reply's `split_into_groups` names the new groups. Each is `proposed`: read them back and confirm each.
  - An absorber answered before the split is not carried to the parts. Each part shows it as a hint
    (`answered_before_split`): ask again per part.
- **Merge** takes three steps:
  1. `<isaac> bundle decide <bundle> --target <group id> --decision merge --merge-with <other group ids> --by "<name>"`
  2. `<isaac> bundle group <bundle> --regroup`
  3. confirm the ONE combined group it proposes.
  - The regroup combines them only when nothing recorded tells them apart: names that differ only at counter
    positions or in a repeat marker (`again`, `repeat`, `redo`).
  - Names that differ in other words: ask "same sample AND same conditions? The names differ in: pristine / cycled".
    `pristine`/`cycled`, `before`/`after`, `soaked`, `OCV` are usually conditions, and then the answer is separate records.
    Only on a yes to both, record the merge with `--same-conditions`.
  - Names that differ in a quantity (`400mV`, `0p5wt`, `T300K`, `spot2`) are never combined.
  - When it could not combine them, nothing changes and the reply lists `merge_decisions_not_combined` with a
    reason and `next_commands`. Say the reason and offer exactly those steps.
  - One of those steps may be one material-name answer per run. That answer is the record's material name: ask for
    it in full, never the file-name word.
- **A merge candidate that is two distinct things:**
  `<isaac> bundle decide <bundle> --target <mc id> --decision keep_apart --by "<name>"`. No group changes.

### Groups that cannot become a record (`cannot_export_reason`)

- `no_scans`: no run lists a scan (no scan file in a `<stem>_dir` folder and no energy scan in its SPEC file).
- `processing_not_applicable:<code>`: no ISAAC protocol covers this data yet (an `.mca` or emission file).
- `not_a_measurement_run`: every run is a reference standard, an alignment or a calibration scan. Its curve can be
  approved, but it is not a record.

A SPEC run with no scan file in its `<stem>_dir` folder takes the energy scans inside its SPEC file.
`bundle show <bundle> group <id>` says which (`scans_in_spec_file`). Say so when you present the group.

## Processing (`isaac.xas.v1`)

`<isaac> process <bundle> --source <folder>`

- Always pass `--source`: the folder that was imported. Without a readable one, `process` refuses and writes nothing.
- It reads a folder, never a ZIP (Step 2 settles that before the import).
- `--group <id>` redoes only that group and keeps every other group's result.
- The processing protocol is a draft until the ISAAC processing reviewers have reviewed it. Say so once per message
  that asks for an approval. An approval means "I looked and accept this curve for this record", not "the method is validated".

What it does to each group, in this order:

1. **Aligns every scan on the reference measured in that same scan** (a foil in transmission, or the glitch in its
   own I0), shifted once to the beamtime's one reference position. Never on the sample's own edge.
2. **Decides which scans to keep** (rule `isaac.xas.scan_decision.v1`). These are decisions with reasons, not
   questions. The scientist may override any of them.
3. Averages the kept scans' raw signal (IF/I0). Normalised data are never merged.
4. Normalises the average once.

Spots of one sample at one condition are merged into one curve.
Athena is never used: Athena project files are listed as files and nothing is read from them.

### Before you process

Step 4 must be done first. Its closing message says one of the lines below. If it did not, say one now, before you
run `process`:

- "I loaded N scan notes from the logbook" (N is `total` in `<isaac> bundle list <bundle> scan-notes --limit 1`), or
- "I read the whole logbook; it says nothing about which scans to use", or
- "this folder has no logbook or notes file".

A result's `logbook_notes.state` says which is true: `no_reading_loaded` (notes files are present and no reading was
loaded; `process` says it once in its summary), `read_no_note_for_these_runs`, or `notes`.
Never relay the first as "the logbook says nothing" unless you read the logbook yourself.

### The scan decisions

A scan is dropped only for one of these reasons. Say the reason in these words:

| Reason on the row | In words |
|---|---|
| `logbook (stated)` / `logbook (inferred)` | "the logbook says …" / "my reading of the logbook is …" |
| `before_stable_window` | the sample was still changing |
| `coverage` | the scan stopped early |
| `anchor`, `no_energy_reference`, `reference_fit_failed` | it could not be aligned (say the row's own words) |
| `shape` | its shape differs from the other scans, beyond their noise |
| beam damage / first scan settling at a spot | see "The dose question" below |
| a dead channel with no edge | there is no spectrum in it |

- **An intensity drop alone never drops a scan.** A weaker or noisier scan is kept and remarked
  (`weak_signal`, `noisier_not_off_shape`). Never offer to drop a scan for being weaker.
- A row "kept by the scientist but cannot be merged" is not in the curve (no energy anchor). Say so.
- An "override not applied" line names an override that matches no scan now (after a regroup or split).
  Say it and offer to state it again on the right scans.

**The scientist overrides a decision**, only on their own word in this conversation:

`<isaac> bundle decide <bundle> --target <group id> --decision set_scan_decision --value drop --scans "<scan id>,<scan id>" --note "<their words>" --by "<name>"`

- `--value keep` puts a dropped scan back. One call per keep or drop.
- Scan ids are the ones the result's `scan_decisions` rows give (`<run name>#<scan number>`, or the file name).
- Then `<isaac> process <bundle> --source <folder> --group <group id>` and show the new result. It has a new id and
  shows the row as the scientist's.

**An approved curve older than its evidence** (`approved_curve_older_than_evidence`): a scan note on a run whose curve
is already approved, or a newer result than the approved one, is the first warning of `build-records`, `validate` and
`export`. Tell the scientist at once and read its "Next:". The record keeps the approved curve until they decide.
A bulk approval refuses such a result; one approval of a result processed without the note waits until a result that
lists the note exists.

### The dose question (ask it before any bulk approval)

**When.** Some results carry `dose_reading_question`. The rule `isaac.xas.dose_damage.v2` saw the white line change
between the first and the later scans at the same spot, at two or more spots, and cannot tell why.
A bulk approval refuses every such result. Ask once for the whole beamtime.

**How.**

1. Count the results that carry it (the `qc_reasons` of each row).
2. Pick two or three of them. For each: say its sentence (`qc.statements.dose_reading_question` in
   `<isaac> bundle show <bundle> processing-result <id>`) in plain words, and open its plot with Read.
3. If a logbook line speaks of it ("discard the first scans", equilibration, a CV), quote it with its line number.
4. Ask one pick:

   > In 36 groups the first scan at each spot differs from the later ones (three examples above). Which is it?
   > (a) beam damage: keep the first scan at each spot, drop the later ones
   > (b) the first scan was still settling: drop the first scan at each spot
   > (c) neither: judge every scan by the other rules
   > One answer covers the beamtime. Tell me if a group differs.

5. Record it:
   `<isaac> bundle decide <bundle> --target experiment --decision set_dose_reading --value beam_damage --by "<name>"`
   (`beam_damage`, `first_scan_settling` or `not_beam_damage`).
   A group that differs: the same with `--target <group id>`. A group's own answer wins.
6. Re-process: `<isaac> process <bundle> --source <folder>`. Then triage again; the verdicts change.

- Never choose for them. A logbook exclude or start-from note on a group always wins over this answer.
- "I don't know": record nothing. Those results are then approved one by one, or left.

### Triage: one approval for the curves that passed, a look at the rest

Page every result: `<isaac> bundle list <bundle> processing-results --state needs_review --limit 200`.
Never read `processing/processing_results.json`. Sort the rows into three sets.

**A. Passed.** `verdict: pass`, `protocol: isaac.xas.v1`, and none of the flags in B.

**B. Needs a look.** Any of:

- `verdict: warn` or `fail`;
- a flag a bulk approval refuses: `dose_reading_question`, `no_energy_reference`, `spots_disagree`,
  `outlier_scans_flagged`, `only_scan_with_edge`, `glitch_points_from_one_scan`, `scan_selection_proposed`,
  `absev_missing_beamline_unconfirmed`;
- a legacy result (`engine_fallback` on the row): read `legacy-processing.md`;
- its group was confirmed with a care flag.

**C. Not for approval.** Never offer to approve these; `decide` refuses.

- `applicability: not_applicable:<code>`: say "no ISAAC processing protocol covers this data yet". Not a fail. Ask nothing.
- No curve (`output_files: 0`): say why; offer to reject the result, mark it `needs_changes`, or leave the group out.
- `fail` for `no_edge`, `edge_step_implausible`, `post_edge_not_at_1` or `edge_from_single_scan`: say its
  sentence; offer reject or `needs_changes`.

**The message for set A** (one message, one answer):

> 87 of 93 curves passed every check: each scan aligned on its reference, an edge found, a plausible edge step.
> Table: sample and condition · scans kept / dropped (why) · edge position · edge step.
> Here are three of them as examples [plots]. Name any other and I'll open it.
> Approve the 87 together? If yes, which QC status: valid, compromised, failed or pending?
> (The processing method is still a draft under review.)

- The table must say, per curve, how many scans were kept and dropped, and why the dropped ones were dropped.
  The row gives the counts (`scan_decisions`). The reasons are in `bundle show <bundle> processing-result <id>`
  (`scan_decisions.rows`): read them for the curves with a dropped scan. For many curves, give a reader subagent
  the ids and have it return one line per curve.
- Open two or three plots with Read as examples (`plot` on the row, under `<bundle>/`). Kept scans are solid,
  dropped scans dashed with the reason in the legend, the average black; below, the normalised curve.
- The scientist can ask for any curve. Open it and describe it before they answer.
- **QC status is theirs.** Map their words to one of the four, say it back, record on their yes. Never derive it
  from the verdict. `compromised` and `failed` need `--qc-note "<their words>"`.
- On their yes: write the result ids to `<bundle>-notes/results.txt`, then
  `<isaac> bundle decide <bundle> --targets-file <bundle>-notes/results.txt --decision approve --qc-status <word> --by "<name>"`.
- A bulk call is all or nothing. If it is refused, it names every refused result and why: take those into set B and repeat without them.

**Set B, with its plot each time.** For each curve say, from `<isaac> bundle show <bundle> processing-result <id>`:

- the verdict and each reason, using the sentence the result gives (`qc.statements`); never reword a flag you do not know;
- the energy reference (`energy_reference.statement`) and the shift range ("shifts +65 to +77 meV", `scan_shifts`);
- each dropped scan with its reason, and each kept scan that has a remark;
- then open the plot with Read and describe it.

Ask: approve (with a QC status), reject, or needs changes.

- A `warn` is theirs to accept. Show it plainly; never suggest approving it.
- Curves that need a look for the same reason can go in one message: the reason once, two or three plots, one question.
  Not the flags a bulk approval refuses: approve those one at a time.
- `no_energy_reference`: say it first and loudly: "no energy reference was found for this beamtime; no scan was aligned".
- `measurement_mode_unknown`: ask how it was measured.
- `normalization`: the absorber it used and its basis. When it says "not confirmed", offer the absorber question (Step 7).
- One at a time:
  `<isaac> bundle decide <bundle> --target <result_id> --decision approve --qc-status <word> [--qc-note "<their words>"] --by "<name>"`, or
  `<isaac> bundle decide <bundle> --target <result_id> --decision reject --note "<their words>" --by "<name>"`
  (`needs_changes` the same way).
- One approved result per group. Approving a second is refused: withdraw the first (`reject` or `defer` on it), then approve the other.

**Their quick beamtime merge** (block `scientist_quick_merges`, row `quick_merge_agreement`): a ROUGH reference only.
The scientists said those merges may not be rigorous. Say its verdict ("your quick merge at the beamline differs
from ISAAC's by …"). Never call it the answer key, never say ISAAC's curve is wrong because it differs, never offer to approve it.

### If evidence arrives after a curve was approved

A scan note loaded later, an override or a dose answer does not change an approved curve. The approval stays on the
old result, and `validate` and `export` do not warn about it. So you must:

1. Tell the scientist: "N approved curves were made before this note. I'm re-processing them."
2. `<isaac> process <bundle> --source <folder> --group <id>` for each affected group.
   (`process` lists them as `decided_results_on_an_older_run`.)
3. Show what changed (scans kept before and now) with the new plot.
4. On their yes: reject the old result, then approve the new one with a QC status.

A new build's rules can also give a group a new result. Say "this curve was re-made under a newer rule; please look
at it again". A record exported before is replaced on the next export.

If processing is not installed, say "curves and quality checks are not available; records will stay incomplete" and continue.
