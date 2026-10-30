# Groups and processing (Steps 5–6)

## Groups

A **record group** is the set of runs that will become ONE ISAAC record: same sample, same
technique, same conditions. Repeats of the same sample in the same condition belong together
(domain owner, 28 Oct 2026). The code proposes groups and splits whenever anything differs or is
unknown; it never merges silently.

Get the groups with `bundle list <bundle> groups` and one in full with `bundle show <bundle> group <id>`; `bundle list <bundle> merge-candidates` names groups the code could not decide about. Present each group like this (no ids unless asked):

> **Group 4 of 12** — sample "SYN_sample_A", acid electrolyte, after 500 cycles, 0.8 V: 3 scans.
> Split from the next group because the potential differs (0.8 V vs 1.0 V).
> Confirm, split, or merge?

- confirm → `decide --target <group id> --decision confirm`
- split → ask which runs go where, then `--decision split --split-into '[["<run key>","<run key>"],["<run key>"]]'`
- merge → three steps: `decide --target <group id> --decision merge --merge-with <other group ids> --by "<name>"`
  (refused unless `--merge-with` names another live record group of this bundle), then
  `bundle group <bundle> --regroup`, then confirm the ONE combined group it proposes. The regroup
  combines them only when nothing recorded tells them apart (any differing file-name token blocks
  it); otherwise it keeps a merge candidate saying why. Tell the scientist which happened. The
  regroup also lists older merge decisions it could not apply (`merge_decisions_not_combined`):
  say each in words. If the names differ only in a run counter, answer the counter question instead.
- a merge candidate the scientist says is two distinct things → `decide --target <mc id> --decision
  keep_apart --by "<name>"` (no group changes).
- Say "7 of 12 groups confirmed" after each batch. A reference or alignment run is its own group.
- Beamtime-wide notes are not group members.

## Processing (draft protocol `isaac.xas.v0`)

`isaac process <bundle> --source <folder>` (always give `--source`: without a readable one it exits 2 and
writes nothing; `--group <id>` redoes only that group and keeps every other group's result,
`kept_other_groups`) computes, per confirmed group, a normalised spectrum, an edge position, a quality
verdict (pass / warn / fail), glitch flags, and compares with the scientist's own Athena output when
it finds one. Show per group, in words:

- the verdict and the reasons (counts, noise, glitches, energy range);
- **when scans were skipped** (reason `scans_skipped_lacking_chosen_columns`; flag
  `channel_from_a_later_scan` when the first scan was one of them): the used / readable / skipped
  counts in plain words — "14 of 165 scans were used; 150 had different columns (they may be motor
  or alignment scans); please confirm these belong in one record";
- **or, when the result has `applicability.status: not_applicable`, no verdict at all**: say "no
  ISAAC processing protocol covers this data yet" (`no_xas_channel`: no absorption channel could be
  formed; name the reader and the layout it states, never a technique) or "no scans, nothing to
  process" (`no_scans`). Do not call it a fail, show no plot, and ask nothing — `decide` refuses
  every decision on it, and the group cannot become a complete record until a protocol covers it;
- whether it agrees with Athena, and by how much, or "no Athena output found";
- the plot PNG (`<bundle>/processing/<group id>/<run id>/plot.png`; the result's `outputs.files` gives the path): open it with Read, describe the curve (edge, pre/post-edge, obvious artefacts); the numbers are in `qc.json` beside it and in `processing/processing_results.json`.

Ask: approve, reject, or needs changes (with a note):
`decide --target <result_id> --decision approve --qc-status <word> [--qc-note "<why>"] --by "<name>"`, or
`decide --target <result_id> --decision reject|needs_changes --note "<why>" --by "<name>"`. Rules:

- **QC status is the scientist's.** Approving also needs `--qc-status <word>` (and `--qc-note` when the status says something is compromised or failed: `decide` refuses those without one). The processing verdict (`pass`/`warn`/`fail`) is shown to help them choose; it is never turned into a status for them, and `warn` never auto-maps. Offer the allowed words from the vocabulary and the flags that bear on the choice.
- **Approval is the scientist's**, per group. A `warn` or `fail` is shown prominently and never
  approved on your suggestion. A rejected group yields no series and stays incomplete.
- The protocol is a **draft until Oscar and Angel review it**. Say so each time you ask.
- If processing is unavailable, say "curves and quality checks are not available; records will stay
  incomplete" and continue.
- **Several Athena versions.** When a result lists more than one of the scientist's Athena versions
  (`athena_versions[]`), ask which one is their result of record and record `decide --target
  <result_id> --decision select_athena_version --value <version_id> --by "<name>"`. It changes no QC
  status and no processed value, and it is not an approval.

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
- `naming_counter_positions` (an experiment-scope question): which positions of the file name are running
  counters, not sample identity. Ask once. Answer with `decide <bundle> --target experiment --decision
  set_counter_positions --positions 2,3 --by "<name>"`, then `bundle group <bundle> --regroup` (decided
  groups are kept). When they say a position is NOT a counter: `decide <bundle> --target experiment
  --decision set_not_counter_positions --positions 2 --by "<name>"` (grouping is unchanged; the
  question drops out).
