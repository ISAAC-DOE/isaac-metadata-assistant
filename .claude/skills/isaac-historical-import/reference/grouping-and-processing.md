# Groups and processing (Steps 5–6)

## Groups

A **record group** is the set of runs that will become ONE ISAAC record: same sample, same
technique, same conditions. Repeats of the same sample in the same condition belong together
(domain owner, 28 Oct 2026). The code proposes groups and splits whenever anything differs or is
unknown; it never merges silently.

**Order:** `bundle group`, then the counter question (`naming_counter_positions`, below; shown by
`<isaac> bundle questions <bundle> --scope experiment`) and a regroup, then apply the findings file
again (absorber findings), and only then confirm, split or merge. A regroup keeps every decided group,
so a counter answer given after a group is confirmed can no longer join it.

Get the groups with `bundle list <bundle> groups` and one in full with `bundle show <bundle> group <id>`; `bundle list <bundle> merge-candidates --limit 20 --offset 0` names groups the code could not decide about (a candidate with fewer than two live groups left proposes nothing: it is listed only with `--all`, its `show` says why, and it is never asked). Every list returns one page: when it says `"more": "5 more: --offset 20"`, run it again with that `--offset` until no `more` is left, before you say how many there are. Present each group like this (no ids unless asked):

> **Group 4 of 12** — sample "SYN_sample_A", acid electrolyte, after 500 cycles, 0.8 V: 3 scans.
> Split from the next group because the potential differs (0.8 V vs 1.0 V).
> Confirm, split, or merge?

- confirm → `<isaac> bundle decide <bundle> --target <group id> --decision confirm --by "<name>"`
- split → ask which runs go where, then
  `<isaac> bundle decide <bundle> --target <group id> --decision split --split-into '[["<run key>","<run key>"],["<run key>"]]' --by "<name>"`.
  A run key is an entry of the group's `member_run_keys` (`bundle show <bundle> group <id>`); it is not
  the `run_id` or `stem`. Ask the scientist in file names, then use the matching keys. One list per
  group to make, together naming every run of the group exactly once (at least two lists); anything else
  is refused and nothing is recorded. The reply's `split_into_groups` names the new groups, one per
  list, each `proposed`: read them back to the scientist in file names and ask them to confirm each (a
  part can also be merged, rejected or split again). The split group is kept as history. A regroup keeps
  the parts exactly as named, under the same ids: a later counter answer does not join them and no merge
  candidate asks about them. To join a part with another group, merge it like any group. If a regroup
  reply lists `split_decisions_not_applied` (an older bundle's split with no usable lists), say why and
  record the split again with `--split-into`; `splits_applied[].applied_now` means an older split's groups
  were only made now: present them like a fresh split.
  Once its parts are live, the split group itself is not deferred, merged, confirmed or split again
  (`decide` refuses, naming the parts: decide those instead). Splitting it again into the same lists
  after both parts were rejected is refused too (the parts would be the same groups): confirm the
  rejected part instead (the refusal gives the command), or split into other lists. A part is never
  asked "these runs look like repeats — merge them?" (the scientist named its runs). An absorber
  answered for the group before the split is NOT carried to the parts: each part's absorber question
  shows it as an `answered_before_split` hint and says so; ask the scientist to confirm it per part.
- merge → three steps: `<isaac> bundle decide <bundle> --target <group id> --decision merge --merge-with <other group ids> --by "<name>"`
  (refused unless `--merge-with` names another live record group of this bundle), then
  `bundle group <bundle> --regroup`, then confirm the ONE combined group it proposes. The combined group's id
  follows its runs only, so the same merges in another order give the same group (an id stored before r5 stays). The regroup
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
  it is listed in `merge_decisions_not_combined`, with a reason and `next_commands` (the counter answer; or one
  material-name answer per run and the merge again with `--same-conditions`: that answer is the record's material
  name, so ask for it in full, as for the other runs of the sample, never the file-name word; or, when the names differ in a
  quantity, plain `confirm` of each group to keep them as separate records): say the reason in words and
  offer exactly those steps, asking the scientist for any value they need; then regroup again.
- a merge candidate with `caution` (its file names state different samples or conditions, or the build
  classified no condition at all): say the caution sentence first; merging such groups would usually
  make one wrong record. `bundle show <bundle> merge-candidate <id>` shows its run labels (no values).
- a merge candidate the scientist says is two distinct things →
  `<isaac> bundle decide <bundle> --target <mc id> --decision keep_apart --by "<name>"` (no group changes).
- Say "7 of 12 groups confirmed" after each batch. A reference or alignment run is its own group.
- Beamtime-wide notes are not group members.

## Processing (draft protocol `isaac.xas.v0`)

`isaac process <bundle> --source <folder>` (always give `--source`; the bundle records the folder only
with `import --record-local-root`, and without a readable one `process` exits 2 and writes nothing. After
a ZIP import, ask the scientist to unzip it outside the bundle and confirm the folder is the data they
approved, and if everything in the ZIP is inside one folder pass that folder, where the bundle's paths start; `--group <id>` redoes only that group and keeps every other group's result,
`kept_other_groups`; rejected, merged and split groups are skipped, `not_live_groups`) computes, per live group, a normalised spectrum, an edge position, a quality
verdict (pass / warn / fail), glitch flags, and compares with the scientist's own Athena output when
it finds one. Show per group, in words:

- the verdict and the reasons (counts, noise, glitches, energy range). **Glitch counts with fewer than 3
  scans**: when `qc.statements.glitch_check_few_scans` is present, say that sentence instead of reading
  the count as glitches (with one or two scans the check compares neighbouring points and also flags the
  white line and the oscillations); never call those points glitches yourself. **Points on the edge**:
  when `qc.statements.glitch_points_on_edge` is present (metrics `glitch_points_on_edge` /
  `glitch_points_off_edge`), say that sentence; only the off-edge count is glitches. With fewer than 3 scans
  none is: whenever `glitch_check_few_scans` is said, `glitch_points_unjudged` counts every flagged point, so
  never call any a glitch (flagged points within
  5 eV of E0 or in the steep stretch of the edge are unjudged, not cleared: say to look at the plot near E0;
  the stored verdict is unchanged). A point from ONE scan alone, far beyond the other scans there, is never
  "unjudged": `qc.statements.glitch_points_from_one_scan` names the scan and counts those points as glitches.
  **One scan sets the curve** (QC `fail` `edge_from_single_scan`, `qc.statements.edge_from_single_scan`): with
  that scan left out the merged curve's range shrinks more than 5 times, so its white line, edge step and E0 are
  that scan's stretch (or, said as such, its post- or pre-edge). Say the sentence, never offer to approve the
  curve, and ask whether the scan belongs in the merge. **The only scan with an edge** (flag and
  `qc.statements.only_scan_with_edge`, never a fail): the other scans are dead, dark or out of the beam; say it
  and ask about those scans, never offer to leave the good one out;
- **scans left out for too few points** (`qc.statements.scans_skipped_too_few_points`): say the sentence; it
  says which are not energy scans (a motor or emission `ascan`, the energy column one value) and which
  stopped early. **Aborted fragments** (`warn` `scans_skipped_aborted_fragment`, `qc.statements.aborted_scan_fragment`):
  a scan with fewer than 20 points beside full scans was left out of the merge; say it and ask whether it was
  stopped, never offer to put it back without the scientist saying so;
- **when scans were skipped** (reason `scans_skipped_lacking_chosen_columns`; flag
  `channel_from_a_later_scan` when the first scan was one of them): the used / readable / skipped
  counts in plain words — "14 of 165 scans were used; 150 had different columns (they may be motor
  or alignment scans); please confirm these belong in one record". The sentence names each skipped file by its
  path in the folder (`PtO2_H2O_dir/PtO2_H2O_004.txt`), never by a source id. The result's `qc.statements` has the
  sentence (`bundle show processing-result`; it is not in `qc.json`), and every `list processing-results`
  row has a `scans` line ("5 of 11 scans used; 6 skipped (scan_lacks_chosen_columns)");
- **which scans the scientist's Athena curve used** (the `…-athena` result's `scans` line and its
  `qc.statements.scans_used`): either the scans its Athena label names, the per-scan groups of a set, or
  "the project does not say which scans". An Athena project does not list the scan files it merged, so
  say which of the three it is and, when it is the last, ask the scientist; never infer scans from the
  curve. `scans_used: null` in its metrics means exactly that, not zero scans. A set over several runs names
  each run's scans ("6 per-scan groups from 2 runs: scans 1-2 of run …; scans 1-4 of run …");
- **a channel chosen by name** (flag `channel_choice_needs_review`, `qc.statements.channel_choice_needs_review`): the
  protocol's column-name order chose it, not the BL15-2 selector; say the sentence (the channel, why, the other
  channels the scan has) and ask the scientist to confirm it is the channel the measurement used. After `template
  adopt`, its "Channel hints" line shows the channel their own Configurations row states: say it beside the flag,
  as a hint, never as the answer;
- **when the channel fell back** (reason and flag `channel_fallback_transmission_not_positive`: a
  group named as a reference or standard takes transmission first, but I0 or I1 was not positive in
  every scan, so fluorescence was used): say the sentence in `qc.json` → `statements` and ask the
  scientist to confirm the channel. A scan skipped `signal_not_finite` has its points but a signal
  that is never finite (I0 or I1 ≤ 0); never call that "too few points" (when no scan is left,
  `qc.statements.no_usable_scan` says it, e.g. a beam that was off). A scan skipped `signal_all_zero`
  recorded a signal of zero at every point: say it in words, naming the file as the statement does
  ("SYN_008.txt's signal is zero at every point, so it was left out"); the curve uses the other scans. A
  merged scan flagged `merged_scan_has_zero_signal_points` has counts that STOP (zero from some point to the
  scan's end) or DROP OUT for a while (a run of zeros at least 5 % of the scan, the counts coming back). Say
  its sentence ("SYN_008.txt's signal is zero at 204 of 226 points, from 7,850 eV on; it is merged unchanged")
  and ask the scientist whether the beam was lost and the scan belongs in the merge;
  never leave it out yourself. Runs of 1-2 zeros are one count line, `qc.statements.merged_scan_isolated_zero_points` (no flag):
  say it once, like glitches (detector dropouts), never as a lost beam, and ask nothing about it. Longer runs
  under 5 % are `qc.statements.merged_scan_short_zero_runs` (no flag): say the count, and do not call them
  dropouts or a lost beam. `merged_curve_end_from_one_scan`: the curve's first or
  last point comes from one scan alone whose signal is zero there (the merged value is 0, a visible drop):
  say it when you describe the plot. An outlier scan (`outlier_scans_flagged`) is named in
  `qc.statements.outlier_scans` with where it departs from the other scans and what merging it did ("…_003.dat
  departs … from 4985.0 to 5100.0 eV: its signal there is about 5% of theirs; … about 24% lower"): say it and ask
  whether the scan belongs in the merge, as for zeros;
- **when a scan ends early** (reason `scans_truncated`, flag `scan_range_truncated`; `scans_used` still
  counts it): say the sentence in `bundle show processing-result` → `qc.statements`, which names each file
  (`qc.json` keeps the source ids it was first written with): how many scans end early, which, the
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
  reject or `needs_changes`, never approval. A scientist's Athena curve is judged the same way, over its
  project's own post-edge range (flag `athena_post_edge_not_at_1`, not preferred; a listed version that
  fails carries the flag: say it when asking which version is the result of record). **A rebuilt Athena
  curve**: larch's reading of the project gives another curve than Athena shows, so ISAAC made it as Athena does
  (the project's stored values where they still fit the data, else Athena's own re-fit). r6: `process` says this
  once, in one summary line; results no longer carry the flag `athena_renormalisation_differs` (older decided
  results still do). `bundle show processing-result` prints `reproduced_with` on the normalize step: say which way
  the curve was made if asked. Never present it as the scientist's error.
  **A decided result kept on its old curve** (`process` reply `decided_results_on_an_older_run`): say the line
  (why the group has new results, and that the approval stands on the old curve) and ask whether the scientist
  wants to review the new result. When a params file made it, the line says what the file did (a scan left out, a
  tie, a parameter, or one of these not passed this time); "this build" means a rule changed;
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
  version's comparison; long lists are counted, not printed); its `result_file` (`result.json`) is the result as the run first wrote it and is never rewritten, so
  the current sentences are in this output, not necessarily in that file.
- **a merge that matches no group** (r6; summary line "A merge exists but was not matched", list
  `athena.unmatched_merges`; on each near group's results `qc.statements.athena_merge_not_matched`, flag
  `athena_merge_not_matched`, question `athena_unmatched_merge_for_group`): the scientist merged in Athena, but the
  merge's name is not a group's scan name, so ISAAC did not use it. Say the line. The near names are hints only:
  never pick one yourself. Say how the names differ (the sentence names the words). Ask the scientist, one merge at
  a time, which group it is for, if any. Only on their answer, write
  `{"athena_match": {"<group id>": [{"project": "<project file>", "athena_group": "<Athena label>"}]}}`
  to a params file (the sentence gives the exact snippet) and run
  `<isaac> process <bundle> --source <folder> --params-file <file>`. On a "no", write the same under
  `athena_match_not`, so the question does not come back. If it is no group's at all, write
  `{"athena_ignore": [{"project": "<project file>", "athena_group": "<Athena label>"}]}`: it is no longer listed
  (pass it on later runs too). `<isaac> bundle list <bundle> athena-merges` pages every unmatched merge (label,
  projects, near groups, `groups_in_project`); the `process` reply lists the first 10 (`athena_unmatched_merges`).
  A merge with no near name is named too: ask which group it is for, naming the groups that share its project.
  Athena's reference channels ("Ref <name>") are no sample merges: the line counts them; never ask about them. A
  hint never crosses run numbers (`01_05` is not `03_04`). A tied merge is compared and listed for approval like any
  Athena curve (flag `athena_named_by_scientist`); the group's result id changes. Approve it on its own, after the
  scientist confirms the tie: a bulk approval refuses it, and the approval's note records the tie. Keep the params
  file and pass it on every later `process`, or the tie is gone (`process` then says it was not passed). A tie that
  names nothing says so in the summary;
- **an Athena group that matches several groups** (summary line "match several record groups by name, so ISAAC
  used none"): say it. When it says the groups "may be one sample", ask the scientist; merge only on their yes
  (step 5), never on the hint alone. Otherwise tie it to its group in `athena_match`;
- when `process` says why none of the scientist's Athena groups matched (`athena.statement`), say it
  in those words. After `process --group`, it speaks of the groups processed now ("none of the 2 group(s) processed
  now has an Athena match"), counting the project's Athena groups that match other groups (stored results too).

Ask: approve, reject, or needs changes (with a note):
`<isaac> bundle decide <bundle> --target <result_id> --decision approve --qc-status <word> [--qc-note "<their words>"] --by "<name>"`, or
`<isaac> bundle decide <bundle> --target <result_id> --decision reject|needs_changes --note "<their words>" --by "<name>"`. Rules:

- **QC status is the scientist's.** Approving also needs `--qc-status <word>` (and `--qc-note` when the status says something is compromised or failed: `decide` refuses those without one). The processing verdict (`pass`/`warn`/`fail`) is shown to help them choose; it is never turned into a status for them, and `warn` never auto-maps. Offer the allowed words from the vocabulary and the flags that bear on the choice.
- **One approved result per group.** A group can hold ISAAC's result (`…-isaac`) and one for the
  scientist's own Athena curve (`…-athena`, often `preferred_for_record: true`); the record uses exactly
  one: the APPROVED one. "Preferred" is only a suggestion; `preferred_for_record: false` on a result can leave no
  result preferred, and the record still uses only the approved result. Approving one while the other is approved
  is refused (`decide` names the approved one):
  keep it, or withdraw it first (`--decision defer` or `reject` on it) and then approve the other. A bundle
  an older build let hold two approvals says so in `validate` (`processing_blocker:
  more_than_one_approved_result`, "two results approved for this group; approve exactly one: <ids>");
  re-processing does not help, deferring one does.
- **Scans the Athena curve uses.** When an Athena result's comparison flags
  `scientist_selected_subset_of_scans` (its label names e.g. scans 5-6 of 6), say so plainly when you show
  or approve it: its E0 and curve describe those scans, not ISAAC's full merge. `decide` says it on
  approval, and the record's E0 descriptor notes it.
- **An Athena curve in a merged group.** Scan numbers restart in each run, so in a group of several runs
  the statement (`qc.statements.scans_used`) names the run(s) the curve covers ("scans 1-2 of run
  …_092") and `comparison.athena_covers` lists `runs`, `group_runs`, `scans` and `isaac_scans_merged`.
  A curve of only some of the group's runs is flagged `scientist_selected_subset_of_scans` and is **not**
  `preferred_for_record` (the statement says why: ISAAC's curve merges every run). Say which run it covers
  and that it describes only those scans; the scientist may still approve it.
- **Who made the E0.** An approved Athena result's E0 descriptor is attributed to the scientist's Athena
  processing (`generated_by.agent: Athena`, `source: imported`, the project's file name and Athena group in
  `notes`); an approved ISAAC result's names ISAAC's protocol (`isaac.xas.v0`, `source: auto`). When the
  scientist kept one Athena group per scan (`match_kind: per_scan_set`), the curve and E0 are ISAAC's MEAN of
  those groups, not a merge the scientist made: the descriptor says so, names the groups, and is ISAAC's
  (`source: auto`). Say that plainly before they approve it. A record names no folder, only the project's file name.
  The scientist's own merge named before the run name (`merge4_<name>`, `merge_<name>`, where `<name>` is a run's
  name or the group's name without its run counter: `match_kind: scientist_merge`) is matched and preferred over
  the per-scan groups beside it; per-scan groups of every run of a merged group form one set (`per_scan_set.runs`).
  Either way the result's steps include a merge, so the record lists `spectrum_merging`. The per-scan groups beside
  such a merge are listed as set aside (`athena_per_scan_sets_set_aside`, `qc.statements.athena_per_scan_set_set_aside`):
  say so. When they cover every scan of the group and their mean differs from the merge (flag
  `athena_merge_differs_from_per_scan_set`, question `athena_merge_or_per_scan_set`), the merge is not preferred: say
  the statement and ask which is the result of record before approving either.
- **An Athena E0 that may be a setting** (flag `athena_e0_possibly_fixed`, `qc.statements.athena_e0_possibly_fixed`,
  question `athena_e0_measured_or_set`): the same Athena E0 (to 0.001 eV) in different Athena curves of groups whose
  ISAAC E0s (QC pass or warn) differ by 0.5 eV or more is likely a normalisation setting typed or carried over in Athena,
  not a measured edge position (one curve matched to two groups is one curve). Every Athena group of the result's
  own project counts too, matched or not (e.g. groups rejected before processing): one whose record group has an
  ISAAC E0 counts only when it differs by 0.5 eV or more; one without (or when this group's own ISAAC QC failed) counts
  when its own stored data puts its edge 0.5 eV or more from that E0 (names equal apart from counters are one sample's
  repeats, never other samples). Nothing is flagged when this curve's own data puts its edge at that E0. The result is
  not preferred. Say the statement and ask "was this E0 measured from this group's edge, or set?" before approving
  it; approve it only on "measured", with `--e0-measured` (`decide` refuses it without). If it was set, it is not the edge position: offer
  ISAAC's result instead. A result already decided is kept as it is: the summary line "approved result <id> carries
  a possibly fixed Athena E0" names it; ask the scientist the same question about it. With `--group`, other groups'
  stored results are one count line ("N more stored results of M groups not processed now …").
- **A result with no curve** (no output file, e.g. `no_usable_scan`) cannot be approved; `decide`
  refuses. Say why in words and offer: reject the result; `needs_changes` (the protocol needs a setting
  the scientist chooses; only on their explicit choice re-process with `--params-file`); or leave the
  group out (`reject` on the group).
- **Too few common points** (QC `fail`, `failure.code: too_few_common_points`, `detail` = the points the scans share): the scans have too few points in common to merge, so there is no curve. The result has a statement (`qc.statements.too_few_common_points`: how many scans were listed and used, how many points they share, how many the merge needs) and `scans` says "N of M scans used". Processing again with other parameters cannot add points the scans do not have, so the remedies name only: reject the result, or leave the group out; never `--params-file` for it.
- **A curve that is not a usable spectrum** (QC `fail` naming `edge_step_implausible`, `no_edge` or
  `post_edge_not_at_1`) cannot be approved either, whatever QC status is given: `decide --decision
  approve` exits 2 with the result's own QC sentence and the same three options. `validate` never offers
  that approval (`processing_blocker: processing_result_not_a_usable_spectrum`, "… is not offered for
  approval: its QC fails …"); when the group has another result that can be approved (e.g. the Athena
  curve), it offers that one and says why not the other. `bundle questions`' minimum never says "approve
  its processing result" for such a group: it is `blocked` with the same options, and never offered as
  the nearest group while another exists.
- **An older approval of such a curve** (made before `decide` refused it) is not used: nothing from the
  result composes (no series, QC status, steps or E0), the record is incomplete with
  `processing_blocker: approved_result_not_a_usable_spectrum`, and `validate` says "the approved result …
  is not a usable spectrum". Say so, and offer withdrawing the approval: reject the result, or
  `needs_changes` and re-process with a setting the scientist chooses, or reject the group.
- **Approval is the scientist's**, per group. A `warn` is shown prominently and is their call; never
  suggest approving it. Any other `fail` (e.g. `too_few_points`) is approved only if the scientist asks
  to, with the QC status they state. A rejected group yields no series and stays incomplete.
- The protocol is a **draft until the ISAAC processing reviewers (Oscar and Angel) review it**. Say so
  each time you ask.
- If processing is unavailable, say "curves and quality checks are not available; records will stay
  incomplete" and continue.
- **Several Athena versions.** When a result lists more than one of the scientist's Athena versions
  (`athena_versions[]`), ask which one is their result of record and record
  `<isaac> bundle decide <bundle> --target <result_id> --decision select_athena_version --value <version_id> --by "<name>"`. It changes no QC
  status and no processed value, and it is not an approval. Then run `process --source <folder> --group <group id>`
  again: the chosen version gets its own Athena result (`…-athena-v02`, `athena_version_id`; its
  `qc.statements.athena_version_selected` says it), built like any Athena result. Its plot is
  `plot_athena_v<n>.png` (`athena_version_plot`): that version's curve over ISAAC's. Open that one, not
  `plot.png` (drawn before the choice, ISAAC's curve only). Show it and ask for approval
  as usual: the record carries the E0 and curve of the ONE approved result (ISAAC's, if that is the one approved),
  never of a version that was only chosen. The choice carries over when ISAAC's own result id changes (a params
  file, a calibration): it is matched by the version's project file, Athena group and data hash. If they choose
  another version after one was approved (or after ISAAC's own curve was approved), the `select_athena_version`
  reply says so at once (`approved_result_not_chosen`: the record still carries the approved curve, and the
  steps: `process` for the chosen version if needed, reject the old result, approve the new one), and `validate`
  and `export` warn `athena_version_no_longer_chosen` until that is done: ask before each step. When `isaac process` replies `athena_selections_not_carried_over` (or a summary line says
  so), say its statement in plain words: their earlier choice no longer
  matches a version ISAAC lists (the files, or how ISAAC reads them, changed), nothing is selected now,
  and ask the question again. A version that is a set of per-scan groups names any project holding the
  identical set (`per_scan_set.identical_in_projects`); say so.
- **The record lists only what was applied.** `measurement.processing.steps` comes from the approved
  result's steps, without a calibration whose shift was not applied (`outcome.applied: false`) and
  without a "merge" of a single scan. Never tell the scientist a record was calibrated unless its
  result says `applied: true`.

## Calibration shift (only when processing proposes one)

Processing never shifts the energy axis on its own. Before any calibration question, read the result's
`calibration` block (`bundle show <bundle> processing-result <id>`): `reference_scans_usable` of
`reference_scans_listed`, `reference_proposed`, `reference_statement`, and `would_apply` (the shift for
an element/edge already named for the group: approved, proposed, or the group's absorber).

- **No reference proposed** (flags `reference_edge_not_found`, `reference_edge_in_too_few_scans`,
  `reference_noise_degenerate` or `no_reference_available`; `reference_proposed` is false then, but it is false
  for disagreeing edges too, the next bullet, so go by the flags): say the `reference_statement` ("only 1 of
  16 scans shows a usable reference edge; an in-scan reference needs one in at least 2 scans") and do NOT
  ask for an element or edge: no shift can be approved, and `approve_calibration` is refused. A scan whose
  reference edge stands more than 1,000,000 times its pre-edge noise is a channel that is not counting, never
  usable (flag `reference_noise_degenerate`), and is said the same way.
- **Usable edges that disagree** (flag `reference_edges_disagree`, `reference_proposed: false`,
  `calibration_proposed: false`: they spread
  over more than 0.5 eV, `qc.warn_reference_e0_spread_eV`, stricter only): not proposed. Say the sentence ("its
  usable edges spread 6.10 eV (… median 11216.2 eV of 2 scans) …") and ask about the channel (a missing foil, a
  channel seeing the sample, drift). Only if the scientist says the reference is what they name (a foil drifting
  between scans), approve with `--accept-shift <the shift shown>`, whatever its size (without it: refused;
  processing does not apply it, `calibration_reference_spread_not_confirmed`).
- **A reference group's own edge** (`reference_source: reference_group_own_signal`, not a separate foil channel)
  is a calibration only if its sample is a pure element, and names cannot settle that: a chemical standard is not
  an energy calibrant (its edge sits where its chemistry puts it; "S K" would move a MoS2 standard onto elemental
  sulfur's edge and erase the chemical shift it was measured to show). So `approve_calibration` on it ALWAYS needs
  `--accept-shift <the shift shown>`, whatever its size and names (without it: refused, nothing recorded; processing
  does not apply it, `calibration_own_signal_shift_not_confirmed`). The names only hint: "its names say it is S; if
  so, approve with --accept-shift +0.4" (a closed list: symbol or English name, S8, `Cu foil`, `Tifoil`, `Sref`,
  `S_K`, beside words of how it was measured: calib, a beam size `1x3mm`, a thickness `7um`, I0-I3, trans, fluor, PIPS,
  Lytle, run counters; a one-letter symbol beside a channel word, `S_trans`, needs `foil` or `ref`), or "ISAAC cannot tell from its names that this is a pure element" (flag
  `own_signal_not_named_as_pure_element`, `calibration_proposed: false`): then do NOT ask for an element or edge
  unless the scientist says it is a pure element. The same reading proposes the element, so the two never disagree.
  With no edge stated the sentence names no shift ("naming its element and edge gives the shift"): get it from
  `would_apply` after they name the edge. A reply naming another element than the names ("its names say it is Fe,
  not Cu") is said and asked. Once a confirmed calibration is applied, the flag is gone and the statement says the
  scientist confirmed it: do not ask again. An approval recorded before this rule (no `--accept-shift`) is not
  applied to a result processed now (its statement says so); a result already approved keeps its curve.
- **A reference is proposed** (`calibration.reference_proposed: true` in `show processing-result`, without the flag
  `own_signal_not_named_as_pure_element`; the flag
  `calibration_reference_unconfirmed` alone only means no reference is approved yet): say how many scans show a
  reference edge and where ("2 of 2 scans show a reference edge at 4974.6 eV"), then ask which element and
  edge the reference measures (`--element Ir`, `--edge L3` style). Never guess it from a file name. Record
  `<isaac> bundle decide <bundle> --target <group id> --decision approve_calibration --element <symbol> --edge <K|L1-L3|M1-M5> --by "<name>"`.
  The reply (or the refusal) says the shift it applies: "the reference edge sits 8.6 eV above Ti K's
  tabulated 4966.0 eV; approving applies -8.6 eV", and what it is read from ("the median of 3 usable scans
  (4974.6 eV, spread 0.20 eV)"). Say it to the scientist in those words. **An in-scan reference edge within
  0.5 eV of the group's own sample E0** (flag `reference_edge_at_sample_e0`): the channel may be seeing the
  sample, not a foil. Say the sentence and ask whether the channel holds a reference foil; approving it needs
  `--accept-shift` whatever the size (without it processing does not apply it,
  `calibration_reference_at_sample_e0_not_confirmed`).
- **A shift above the protocol's 2 eV warning level** (`qc.warn_energy_shift_eV`) is refused until the
  scientist also accepts its size: it moves every energy of the record, E0 included, by that much, and can
  erase a chemical shift the study measures. Say the size, ask "apply -8.6 eV to this group?", and only on
  their yes add `--accept-shift -8.6` (the value shown, to 0.1 eV; another value is refused). Nothing is
  recorded by a refusal. A result whose approval lacks the confirmed size carries
  `calibration_shift_size_not_confirmed` and is not shifted.
- Then run `process --source <folder> --group <group id>` again and say the result's `applied_shift_eV`.
  On a separate foil channel, a shift of 2 eV or less is approved without `--accept-shift`; a group's own edge
  always needs it.
- **A curve that already carries a shift** (`calibration.carried_shift`, `confirmed: false`): a result
  approved under an older build baked in a shift the current rules would not apply (e.g. -8.6 eV from 1 of 16
  usable scans, or a large shift whose size nobody confirmed). It is kept on re-processing, and
  build-records / validate block its record (`approved_result_calibration_unconfirmed`). Say its statement
  ("This curve carries -8.6 eV that is now unconfirmed ...") and ask: keep it (`approve_calibration ...
  --accept-shift -8.6` on their yes) or reject the result. `qc.statements.calibration_approval_not_applied`
  on a re-processed result names an approval the current rules did not apply; say it.
- A params file can only make these rules stricter: a higher `qc.warn_energy_shift_eV` or a lower in-scan
  `calibration.reference_min_edge_snr` is ignored and said (`qc.statements.params_override_ignored`).

## Groups that need an explanation

- A SPEC run, or a standard/reference measurement (e.g. a reference pellet), with no scan file in a
  `<stem>_dir` folder lists the energy scans (`gscan`) inside its SPEC file; an alignment file never does. Its
  `other_relationships.scans_in_spec_file` names the `#S` blocks used and each one left out, with why (an
  alignment scan, no data rows, a repeated number), and `scan_dir_present_empty: true` when the `_dir` folder
  exists but is empty. When its SPEC file could not be read, or the run is an
  exported copy of another run (`SYN_A.dat` beside `SYN_A`), its `why` says so. The HERFD channel selector reads
  the same `#S` blocks, so such a run's `signal_selection` reflects its in-file scans. Say so when you present the group.
- `merged_despite_engine_reading`: more than one run was proposed as one group although the importer read
  something that differs. Say what differs in words and ask; confirming is the scientist's call.
- `sample_key_basis: name_stem`: no file states the sample, so runs were grouped by the stem of their file
  names. Say so, and ask the scientist to confirm or split.
- **A groups row** (`bundle list <bundle> groups`) has `files` (the first 3 member stems; `files_more`
  counts the rest), `scans`, `reader` (the runs' source type), `exported_file` when a member is the
  scientist's exported/processed file of a run (kept as context, its data not merged: say so), `needs_care`
  when the group merges scans its files read at different conditions (`conflicting_condition`, e.g. two filter
  settings in one file: check it before a bulk confirm; `bundle show <bundle> group <id>` gives the readings),
  and, when known, `cannot_export_reason`:
  `no_scans` (no run lists a scan: no scan file in a `_dir` folder and no energy scan with data in its SPEC
  file; the same code before and after `isaac process`), `processing_not_applicable:<code>` (e.g. an `.mca` or `xes` file:
  no ISAAC protocol covers it), or `not_a_measurement_run` (every run is a reference standard, an alignment
  or a calibration scan: the import asks nothing about its sample or conditions, so the fields in
  `cannot_export_fields`, e.g. sample form and environment, have nowhere to hold an answer; its curve can be
  approved, but it is not a record). When `bundle group` makes the groups, it names the groups that hold no
  measurement run and gives each its `cannot_export_reason` exactly as this list does (one that also has no scan
  is said as `no_scans`). The page's
  `cannot_export` counts them over the whole list. Such a group
  can never become an exportable record as it stands: present it as such, leave it out of a bulk confirm,
  and offer `reject` (it is kept as decision history) or leaving it unconfirmed.
- **A run kept as context** (`exported_file`): it is not a measurement run. No question asks about it, no
  count, `applies_to` or reach includes it, and its values fill nothing in the record. `--only group:<id>`
  answers the group's measurement runs, which is enough to fill the field. The template's File List shows its row in grey with a note;
  anything typed on that row is recorded nowhere (`rows_refused`).
- `naming_counter_positions` (an experiment-scope question): which positions of the file name are running
  counters, not sample identity. Ask once, before any group is confirmed. Answer with
  `<isaac> bundle decide <bundle> --target experiment --decision set_counter_positions --positions 2,3 --by "<name>"` (`--positions last` when the counter is
  always the last token, whatever the name's length; where some names sharing a prefix end in a
  shorter run of numbers, `…_3` beside `…_3_001`, only the longest is read as ending in a counter),
  then `bundle group <bundle> --regroup` (decided groups are kept). The reply's
  `regroup_preview.statement` says how many groups the answer would join and which pending merge
  decisions it would let the regroup combine (`merge_decisions_unblocked`): tell the scientist before
  regrouping. When they say a position is NOT a counter:
  `<isaac> bundle decide <bundle> --target experiment --decision set_not_counter_positions --positions 2 --by "<name>"`
  (grouping is unchanged; the question drops out). Every open merge candidate whose names differ ONLY at those
  positions then carries the caution "the scientist said position N is not a counter", and the reply names them
  (`said_not_counter_merge_candidates`); none is decided. If the scientist agrees they are all distinct, one command
  keeps them all apart: `<isaac> bundle decide <bundle> --question <counter question id> --decision keep_apart --by "<name>"
  --target <mc-…> …`, naming each candidate the reply listed (the reply prints it so); it is refused, naming what
  changed, when the cautioned candidates are no longer exactly those.
  When they say they do not know:
  `<isaac> bundle decide <bundle> --target experiment --decision defer --by "<name>"` records it; grouping is unchanged, the question stays, marked `deferred`, and a later
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
keys are refused. Then `<isaac> process <bundle> --source <folder> --group <id> --params-file <file>`. Say back
exactly what changed; every changed value is recorded on the result. Never use it to pass a QC check:
a threshold is the protocol's, not a fix.

**Leaving a scan out of a merge**, only when the scientist says it does not belong (a dead scan, a lost beam,
one scan's spike): the outlier, zero-signal and `edge_from_single_scan` sentences give the exact file,
`{"exclude_scans": {"<group id>": ["<file name>"]}}` (a relative path or source id works too, and the sentence uses
the relative path when a file name repeats across folders; `<file>#<scan>` for one scan of a multi-scan file; a
name that left out more than one scan, or a group id that is no group, is said). Re-process that group with it as above: the new result lists the scan as skipped
`scans_excluded_by_params_file`, says it (`qc.statements.scans_excluded_by_params_file`, also a name that matched
no scan), and records it in `params.json` `excluded_scans`; the earlier result stays as it was.
