# Legacy results, calibration shifts, changed settings

Read this only when:

- a result's row has `engine_fallback` (protocol `isaac.xas.v0`), or
- a result proposes a calibration shift, or
- the scientist asks for a changed processing setting or to leave a scan out of a legacy merge.

Everything in `grouping-and-processing.md` about approval still holds: the QC status is the scientist's, one approved
result per group, a `warn` is theirs to accept, the protocol is a draft.

## A legacy result (`isaac.xas.v0`)

`process` gives a group a v0 result when the main engine does not cover it. `engine_fallback` on the row says why,
for example a pellet measured in transmission, an alignment group, another file format. Say it in words.

A v0 result does not decide scans. It merges every usable scan and PROPOSES which to leave out.

**The general rule.** `<isaac> bundle show <bundle> processing-result <id>` prints `qc.statements`: one plain sentence
per finding. Say each sentence. Never reword a flag from its name, and never act on one without the scientist.

**Findings that need more than their sentence:**

| Finding | What to do |
|---|---|
| `glitch_check_few_scans` | with one or two scans the check also flags the white line and the oscillations. Say its sentence; never call those points glitches |
| `glitch_points_on_edge` | only the off-edge count is glitches. Points near E0 are unjudged, not cleared: say to look at the plot near E0 |
| `glitch_points_from_one_scan` | one scan's glitch on the edge: name the scan; approve this result on its own |
| `edge_from_single_scan` (fail) | one scan sets the curve's edge. Never offer approval; ask whether that scan belongs in the merge |
| `only_scan_with_edge` | the other scans are dead, dark or out of the beam. Ask about those; never offer to leave the good one out |
| `scans_skipped_lacking_chosen_columns` | "14 of 165 scans were used; 150 had different columns (they may be motor or alignment scans)". Ask them to confirm these belong in one record |
| `scans_skipped_too_few_points`, `scans_skipped_aborted_fragment` | say which scans were left out and why; ask whether a fragment was a stopped scan. Never put one back without their word |
| `scans_truncated` | a scan ends early, so part of the curve averages fewer scans. Ask whether it belongs in the merge |
| `channel_choice_needs_review`, `channel_fallback_transmission_not_positive`, `channel_fallback_reference_channel` | say which signal was used and why. Ask which channel or detector the measurement really used. Never assume it |
| `signal_not_finite` | the scan has its points but the signal is never finite (I0 or I1 ≤ 0). Never call that "too few points" |
| `signal_all_zero` | "`<file>`'s signal is zero at every point, so it was left out", naming the file as the statement does; the curve uses the other scans |
| `merged_scan_has_zero_signal_points` | counts that stop or drop out for a while. Say its sentence ("… zero at 204 of 226 points, from 7,850 eV on; it is merged unchanged"). Ask whether the beam was lost and the scan belongs; never leave it out yourself |
| `merged_scan_isolated_zero_points` | detector dropouts of 1–2 points. Say the count once; ask nothing |
| `outlier_scans_flagged` | the sentence names the scan and where it departs. Ask whether it belongs in the merge |
| `post_edge_window_too_short` (warn) | the edge position is usable; the normalised curve is not checked. Their call |
| `too_few_common_points` (fail) | the scans share too few points to merge; there is no curve. Offer: reject the result, or leave the group out. Never a params file |
| `no_edge`, `edge_step_implausible`, `post_edge_not_at_1` (fail) | not a usable spectrum. Never offer approval; offer reject or `needs_changes` |

**The scan-selection proposal** (flag `scan_selection_proposed`; block `scan_selection`; row line "proposes leaving
out 3 of 9 merged scans; not applied").

- It is a proposal per scan, never a drop. The merge still uses every scan.
- Each scan is `include`, `needs_look` or `exclude_proposed`, with a sentence (`said`). Say the sentences and ask about each scan.
- A scan that is only weaker or noisier (`lowers_merge_snr`) is "to look at". Never say it should go: an intensity drop alone never drops a scan.
- An edge-step change is an observation only. Never offer to leave a scan out for it.
- Only on the scientist's word, leave the scan out with the `exclude_scans` snippet the sentence gives (below) and re-process the group.
- A result with open proposals is approved on its own; a bulk approval refuses it.
- The plot marks proposed scans dotted ("proposed: leave out") or dash-dotted ("proposed: look at").

**The record lists only what was applied.** Never tell the scientist a record was calibrated unless its result says `applied: true`.

## Calibration shift (only when processing proposes one)

Processing never shifts the energy axis of a legacy result on its own. No answer, no shift.
Read the result's `calibration` block first: `reference_scans_usable` of `reference_scans_listed`, `reference_proposed`,
`reference_statement`, `would_apply`.

- **No reference proposed** (flags `reference_edge_not_found`, `reference_edge_in_too_few_scans`,
  `reference_noise_degenerate`, `no_reference_available`): say the `reference_statement`. Do NOT ask for an element
  or edge; `approve_calibration` is refused.
- **Usable edges that disagree** (`reference_edges_disagree`): not proposed. Say the sentence and ask about the channel
  (a missing foil, a channel seeing the sample, drift). Only if they say the reference is what they name, approve with
  `--accept-shift <the shift shown>`.
- **A reference is proposed** (`reference_proposed: true`): say how many scans show a reference edge and where
  ("2 of 2 scans show a reference edge at 4974.6 eV"). Ask which element and edge the reference measures. Never guess
  it from a file name. Then
  `<isaac> bundle decide <bundle> --target <group id> --decision approve_calibration --element <symbol> --edge <K|L1-L3|M1-M5> --by "<name>"`.
  The reply says the shift it applies, in words. Say it to the scientist.
- **A shift above 2 eV** is refused until they accept its size. It moves every energy of the record. Ask
  "apply -8.6 eV to this group?" and only on their yes add `--accept-shift -8.6` (the value shown; another is refused).
  A result whose approval lacks it carries `calibration_shift_size_not_confirmed` and is not shifted.
- **A reference group's own edge** (`reference_source: reference_group_own_signal`) is a calibration only if the
  sample is a pure element. A chemical standard is not an energy calibrant. It ALWAYS needs `--accept-shift`.
  With `own_signal_not_named_as_pure_element`, do not ask for an element unless the scientist says it is a pure element.
- **A reference edge within 0.5 eV of the sample's own edge** (`reference_edge_at_sample_e0`): the channel may be
  seeing the sample. Ask whether it holds a foil; approving needs `--accept-shift` whatever the size.
- **A curve that already carries an unconfirmed shift** (`calibration.carried_shift`, `confirmed: false`): its record
  is blocked. Say its statement and ask: keep it (`approve_calibration … --accept-shift <its size>`) or reject the result.
- Then `<isaac> process <bundle> --source <folder> --group <group id>` and say the result's `applied_shift_eV`.
- A params file can only make these rules stricter. A looser value is ignored and said.

## A changed setting (`--params-file`), only on the scientist's explicit choice

After `needs_changes`, when the scientist names a setting ("use I2 as the reference", "fit the post-edge from 150 eV"):

1. Write a JSON file in the notes folder beside the bundle, shaped `{"<section>": {"<key>": <value>}}`.
   Sections: `channels`, `calibration`, `deglitch`, `merge`, `normalize`, `qc`. Each result's `params.json` shows the
   resolved values. Unknown keys are refused.
2. `<isaac> process <bundle> --source <folder> --group <id> --params-file <file>`.
3. Say back exactly what changed. Every changed value is recorded on the result.

Never use a params file to pass a QC check. A threshold is the protocol's, not a fix.

**Leaving a scan out of a legacy merge**, only when the scientist says it does not belong:
`{"exclude_scans": {"<group id>": ["<file name>"]}}` (`<file>#<scan>` for one scan of a multi-scan file; the result's
sentence gives the exact snippet). Re-process that group with it. The new result lists the scan as left out; the
earlier result stays as it was. Keep the file and pass it on every later `process` of that group.
