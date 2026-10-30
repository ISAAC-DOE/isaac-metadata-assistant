# Groups and processing (Steps 5–6)

## Groups

A **record group** is the set of runs that will become ONE ISAAC record: same sample, same
technique, same conditions. Repeats of the same sample in the same condition belong together
(domain owner, 28 Oct 2026). The code proposes groups and splits whenever anything differs or is
unknown; it never merges silently.

Get the groups with `bundle list <bundle> groups` and one in full with `bundle show <bundle> group <id>`; `bundle list <bundle> merge-candidates --limit 20 --offset 0` names groups the code could not decide about (a candidate with fewer than two live groups left proposes nothing: it is listed only with `--all`, its `show` says why, and it is never asked). Every list returns one page: when it says `"more": "5 more: --offset 20"`, run it again with that `--offset` until no `more` is left, before you say how many there are. Present each group like this (no ids unless asked):

> **Group 4 of 12** — sample "SYN_sample_A", acid electrolyte, after 500 cycles, 0.8 V: 3 scans.
> Split from the next group because the potential differs (0.8 V vs 1.0 V).
> Confirm, split, or merge?

- confirm → `decide --target <group id> --decision confirm`
- split → ask which runs go where, then `--decision split --split-into '[["<run key>","<run key>"],["<run key>"]]'`
- merge → three steps: `decide --target <group id> --decision merge --merge-with <other group ids> --by "<name>"`
  (refused unless `--merge-with` names another live record group of this bundle), then
  `bundle group <bundle> --regroup`, then confirm the ONE combined group it proposes. The regroup
  combines them when the names differ only at positions the scientist declared counters, or only in a
  repeat marker (`again`, `repeat`, `redo`; a glued `Rep1`/`rep2` is a replicate, another sample), or
  when the names differ in words the scientist says are labels: the same sample confirmed for every
  run AND the merge recorded with `--same-conditions` (stored with the words it was said for). The
  same sample is not the same conditions: before `--same-conditions`, ask "same sample AND same
  conditions? the names differ in: pristine / cycled" — `pristine`/`cycled`, `before`/`after`,
  `soaked`, `OCV` are usually conditions, and then the answer is separate records. Runs whose
  conditions differ, or whose names differ in a quantity or any letters-and-digits token (`400mV`, `0p5wt`, `T300K`, `spot2`), are never
  combined. Tell the scientist which happened. When it could not combine them, nothing changes: the
  groups keep their ids and stay proposed, the merge stays pending (each regroup tries it again), and
  it is listed in `merge_decisions_not_combined`, with a reason and `next_commands` (the counter answer; or one sample
  confirmation per run and the merge again with `--same-conditions`; or, when the names differ in a
  quantity, plain `confirm` of each group to keep them as separate records): say the reason in words and
  offer exactly those steps, asking the scientist for any value they need; then regroup again.
- a merge candidate with `caution` (its file names state different samples or conditions, or the build
  classified no condition at all): say the caution sentence first; merging such groups would usually
  make one wrong record. `bundle show <bundle> merge-candidate <id>` shows its run labels (no values).
- a merge candidate the scientist says is two distinct things → `decide --target <mc id> --decision
  keep_apart --by "<name>"` (no group changes).
- Say "7 of 12 groups confirmed" after each batch. A reference or alignment run is its own group.
- Beamtime-wide notes are not group members.

## Processing (draft protocol `isaac.xas.v0`)

`isaac process <bundle> --source <folder>` (always give `--source`: without a readable one it exits 2 and
writes nothing; `--group <id>` redoes only that group and keeps every other group's result,
`kept_other_groups`; rejected, merged and split groups are skipped, `not_live_groups`) computes, per live group, a normalised spectrum, an edge position, a quality
verdict (pass / warn / fail), glitch flags, and compares with the scientist's own Athena output when
it finds one. Show per group, in words:

- the verdict and the reasons (counts, noise, glitches, energy range);
- **when scans were skipped** (reason `scans_skipped_lacking_chosen_columns`; flag
  `channel_from_a_later_scan` when the first scan was one of them): the used / readable / skipped
  counts in plain words — "14 of 165 scans were used; 150 had different columns (they may be motor
  or alignment scans); please confirm these belong in one record";
- **when the channel fell back** (reason and flag `channel_fallback_transmission_not_positive`: a
  group named as a reference or standard takes transmission first, but I0 or I1 was not positive in
  every scan, so fluorescence was used): say the sentence in `qc.json` → `statements` and ask the
  scientist to confirm the channel. A scan skipped `signal_not_finite` has its points but a signal
  that is never finite (I0 or I1 ≤ 0); never call that "too few points";
- **when a scan ends early** (reason `scans_truncated`, flag `scan_range_truncated`; `scans_used` still
  counts it): say the sentence in `qc.json` → `statements` (how many scans end early, which, the
  energies each covers, and that part of the merged curve averages fewer scans) and ask whether the
  short scan belongs in the merge;
- **an implausible edge step** (reason `edge_step_implausible`, always a `fail`: the step is more than
  twice the spectrum's whole range, so the post-edge fit did not describe the data): say the sentence
  in `statements`; never offer to approve that curve. On a scientist's Athena curve the comparison is
  `not_comparable` with flag `athena_edge_step_implausible` and a `reason`; it is not overlaid on the
  plot and not preferred;
- **a curve that is not a usable spectrum** (`fail` with `no_edge`: the edge is not distinguishable from
  the pre-edge scatter; or `post_edge_not_at_1`: the normalised level after the edge is far from 1, so
  the normalisation did not work): say the sentence in `statements` and what the plot shows; offer
  reject or `needs_changes`, never approval;
- **a short scan** (`warn` with `post_edge_window_too_short`: the scan ends soon after the edge, so its
  normalised level cannot be checked): say that its edge position is still usable but its normalised
  curve is not checked; the scientist decides whether that is enough for this record;
- **a reference foil whose channel was switched** (flag `channel_fallback_reference_channel`, or
  `reference_channel_tried_not_usable` when every alternative failed too): say which signal was tried
  and why, and ask the scientist which detector the foil was really on — never assume it;
- **or, when the result has `applicability.status: not_applicable` (a `list processing-results` row shows
  `applicability: not_applicable:<code>`), no verdict at all**: say "no
  ISAAC processing protocol covers this data yet" (`no_xas_channel`: no absorption channel could be
  formed; name the reader and the layout it states, never a technique) or "no scans, nothing to
  process" (`no_scans`). Do not call it a fail, show no plot, and ask nothing — `decide` refuses
  every decision on it, and the group cannot become a complete record until a protocol covers it;
- whether it agrees with Athena, and by how much, or "no Athena output found". A group Athena marks
  as already normalised (`athena_ref.athena_data: already_normalized`, e.g. a `.nor` export read back
  into a project) is the scientist's normalised curve exactly as stored (edge step 1 by definition);
  it is never normalised again, so no edge-step ratio is given for it;
- the plot PNG (`<bundle>/processing/<group id>/<run id>/plot.png`; the result's `outputs.files` gives the path): open it with Read, describe the curve (edge, pre/post-edge, obvious artefacts); the numbers are in `qc.json` beside it. Never read `processing/processing_results.json` (it can be
  over a MB): `<isaac> bundle list <bundle> processing-results --limit 20` pages each result's
  `result_id`, verdict, applicability, failure, flags, key metrics, `plot` path, Athena agreement and,
  when there are several Athena versions, `athena_version_choices` (each `version_id` with its project
  file, Athena group and label). `<isaac> bundle show <bundle> processing-result <result_id>` prints one
  result compactly (QC with its `statements`, each step's outcome, the Athena comparison and every
  version's comparison; long lists are counted, not printed); its `result_file` is the full result.
- when `process` says why none of the scientist's Athena groups matched (`athena.statement`), say it
  in those words.

Ask: approve, reject, or needs changes (with a note):
`decide --target <result_id> --decision approve --qc-status <word> [--qc-note "<why>"] --by "<name>"`, or
`decide --target <result_id> --decision reject|needs_changes --note "<why>" --by "<name>"`. Rules:

- **QC status is the scientist's.** Approving also needs `--qc-status <word>` (and `--qc-note` when the status says something is compromised or failed: `decide` refuses those without one). The processing verdict (`pass`/`warn`/`fail`) is shown to help them choose; it is never turned into a status for them, and `warn` never auto-maps. Offer the allowed words from the vocabulary and the flags that bear on the choice.
- **One approved result per group.** A group can hold ISAAC's result (`…-isaac`) and one for the
  scientist's own Athena curve (`…-athena`, often `preferred_for_record: true`); the record uses exactly
  one. Approving one while the other is approved is refused (`decide` names the approved one):
  keep it, or withdraw it first (`--decision defer` or `reject` on it) and then approve the other. A bundle
  an older build let hold two approvals says so in `validate` (`processing_blocker:
  more_than_one_approved_result`, "two results approved for this group; approve exactly one: <ids>");
  re-processing does not help, deferring one does.
- **Scans the Athena curve uses.** When an Athena result's comparison flags
  `scientist_selected_subset_of_scans` (its label names e.g. scans 5-6 of 6), say so plainly when you show
  or approve it: its E0 and curve describe those scans, not ISAAC's full merge. `decide` says it on
  approval, and the record's E0 descriptor notes it.
- **Who made the E0.** An approved Athena result's E0 descriptor is attributed to the scientist's Athena
  processing (`generated_by.agent: Athena`, `source: imported`, the project and Athena group in `notes`);
  an approved ISAAC result's names ISAAC's protocol (`isaac.xas.v0`, `source: auto`).
- **A result with no curve** (no output file, e.g. `no_usable_scan`) cannot be approved; `decide`
  refuses. Say why in words and offer: reject the result; `needs_changes` (the protocol needs a setting
  the scientist chooses; only on their explicit choice re-process with `--params-file`); or leave the
  group out (`reject` on the group).
- **Approval is the scientist's**, per group. A `warn` or `fail` is shown prominently and never
  approved on your suggestion. A rejected group yields no series and stays incomplete.
- The protocol is a **draft until Oscar and Angel review it**. Say so each time you ask.
- If processing is unavailable, say "curves and quality checks are not available; records will stay
  incomplete" and continue.
- **Several Athena versions.** When a result lists more than one of the scientist's Athena versions
  (`athena_versions[]`), ask which one is their result of record and record `decide --target
  <result_id> --decision select_athena_version --value <version_id> --by "<name>"`. It changes no QC
  status and no processed value, and it is not an approval.
- **The record lists only what was applied.** `measurement.processing.steps` comes from the approved
  result's steps, without a calibration whose shift was not applied (`outcome.applied: false`) and
  without a "merge" of a single scan. Never tell the scientist a record was calibrated unless its
  result says `applied: true`.

## Calibration shift (only when processing proposes one)

Processing never shifts the energy axis on its own. When a result's flags say the calibration reference
is unconfirmed, explain it plainly and ask the scientist which element and edge the reference foil
measures (`--element Ir`, `--edge L3` style). Record `decide --target <group id> --decision
approve_calibration --element <symbol> --edge <K|L1-L3|M1-M5> --by "<name>"`, then run
`process --source <folder> --group <group id>` again. Without that decision the shift is not applied; do not guess the
element or edge from a file name.

## Groups that need an explanation

- `merged_despite_engine_reading`: more than one run was proposed as one group although the importer read
  something that differs. Say what differs in words and ask; confirming is the scientist's call.
- `sample_key_basis: name_stem`: no file states the sample, so runs were grouped by the stem of their file
  names. Say so, and ask the scientist to confirm or split.
- **A groups row** (`bundle list <bundle> groups`) has `files` (the first 3 member stems; `files_more`
  counts the rest), `scans`, `reader` (the runs' source type), `exported_file` when a member is the
  scientist's exported/processed file of a run (kept as context, its data not merged: say so), and, when known, `cannot_export_reason`:
  `no_scans` (no run lists a scan) or `processing_not_applicable:<code>` (e.g. an `.mca` or `xes` file:
  no ISAAC protocol covers it). The page's `cannot_export` counts them over the whole list. Such a group
  can never become an exportable record as it stands: present it as such, leave it out of a bulk confirm,
  and offer `reject` (it is kept as decision history) or leaving it unconfirmed.
- `naming_counter_positions` (an experiment-scope question): which positions of the file name are running
  counters, not sample identity. Ask once. Answer with `decide <bundle> --target experiment --decision
  set_counter_positions --positions 2,3 --by "<name>"` (`--positions last` when the counter is
  always the last token, whatever the name's length; where some names sharing a prefix end in a
  shorter run of numbers, `…_3` beside `…_3_001`, only the longest is read as ending in a counter),
  then `bundle group <bundle> --regroup` (decided groups are kept). The reply's
  `regroup_preview.statement` says how many groups the answer would join and which pending merge
  decisions it would let the regroup combine (`merge_decisions_unblocked`): tell the scientist before
  regrouping. When they say a position is NOT a counter: `decide <bundle> --target experiment
  --decision set_not_counter_positions --positions 2 --by "<name>"` (grouping is unchanged; the
  question drops out). When they do not know: `decide <bundle> --target experiment --decision defer --by
  "<name>"` records it; grouping is unchanged, the question stays, marked `deferred`, and a later
  answer supersedes it. Never guess a position for them.

## After a new build re-processes

New rules (a fallback channel, an already-normalised Athena curve, a skip reason) can give a group
a NEW result id. An earlier approval stays on the old result and never moves to the new curve: tell the
scientist "this curve was re-made under a newer rule; please look at it again". A record exported
before is replaced on the next export (the old one moves to `superseded/`); say so.

## A changed processing setting (`--params-file`), only on the scientist's explicit choice

After `needs_changes`, when the scientist names a different setting ("use I2 as the reference", "fit the
post-edge from 150 eV"), write a JSON file in the notes folder beside the bundle, shaped
`{"<section>": {"<key>": <value>}}` with sections and keys from the protocol defaults
(`apps/api/isaac_api/local_import/processing/protocol.py`, `DEFAULT_PARAMS`: `channels`, `calibration`,
`deglitch`, `merge`, `normalize`, `qc`, `athena`; each result's `params.json` shows the resolved values). Unknown
keys are refused. Then `process <bundle> --source <folder> --group <id> --params-file <file>`. Say back
exactly what changed; every changed value is recorded on the result. Never use it to pass a QC check:
a threshold is the protocol's, not a fix.
