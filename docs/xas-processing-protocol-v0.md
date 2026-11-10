# ISAAC XAS processing protocol `isaac.xas.v0` (with record grouping)

> **DRAFT — not reviewed by a beamline scientist. Oscar's protocol supersedes on arrival.**
> Status `draft_unreviewed`, version `0.1.0`. Every result is `state: needs_review`. Nothing
> here produces an official ISAAC value; results are review material for a scientist.
>
> **Rule versions, not a version bump.** The protocol version is hashed into every run id (§9), so
> bumping it would move EVERY result id and orphan every decision, including on groups a change does not
> touch. Rules added or changed since 0.1.0 are therefore versioned on their own, and every ISAAC result
> records them in `rule_versions` (`since_protocol_version`, `rule_ids`, `statement`;
> `processing/protocol.py` `RULE_VERSIONS_SINCE_PROTOCOL_VERSION`), outside the hashed output files. A
> result a change does touch gets a new id from its own changed outputs.

Code: `apps/api/isaac_api/local_import/grouping.py` (stdlib) and
`apps/api/isaac_api/local_import/processing/` (numpy + xraylarch, optional extra
`processing`, imported lazily). Machine-readable parameters: `processing/protocol.py`
(`DEFAULT_PARAMS`, `PARAM_DOCS`). Entry points: `processing.cli_entry.run_group(bundle_dir)`
and `run_process(bundle_dir, source_root=..., params=...)`; evaluation:
`python -m isaac_api.local_import.processing.evaluate <folder>`.

## 0. Why

An official ISAAC record is ONE RESULT: one sample, one technique, one set of conditions
(upstream wiki *What an ISAAC record is*). Domain owner (Angel, 28 Oct 2026): *"Multiple
scans, multiple runs, or repeats of the same sample in a specific condition create a single
record. It requires scientific knowledge/protocol: energy calibration, identification of
glitches and outliers, merging data, normalization of spectra, checking quality of the
data."* One ISAAC experiment = one beamtime folder (`experiment_key = experiment:<folder name>`).

## 1. Record grouping (`isaac.grouping.record_groups.v1`)

Each run's candidates are read as *readings* (`value`, `literal`, `conflicting`, absent), and
every statement key is in exactly ONE class (`grouping.CONDITION_KEYS`, `BOOKKEEPING_KEYS`,
`UNKNOWN_KEYS`, each entry with its justification in code):

| class | keys | a difference means |
|---|---|---|
| **condition** | sample name/number, loading/thickness; acquisition method (technique); environment, cell type, reaction; potential + its reference; electrolyte/medium, pH; gas, flow; cycling and before/after state; dry state; temperature; filter (changes count rate and dose); HERFD emission energy (selects the line) | split (also on a conflict, or stated for one run only — with a question) |
| **bookkeeping** | legacy run/file number, repeat markers (`again`), timestamps, scan commands/grids/counts, detector columns, motor and stage positions, file declarations, beamtime context … | nothing: runs differing only here form **one proposed group** with question `confirm_repeats_merge` listing the differing bookkeeping literals |
| **unknown** | `new_spot`, `step_number`, unrecognised acquisition-name tokens, and **every key not listed** | split, plus a **`merge_candidate`** naming the key (`unknown_key_differs`), so a scientist merges with one decision |

A proposed group requires, per member: same role; no conflicting condition; a stated sample
identity; ≥ 1 scan; no engine-reading issue; equal condition and unknown readings. A merge
candidate requires same role, equal condition readings, no hard condition conflict, ≥ 1 scan.
Duplicate legacy numbers stay separate runs (flag `duplicate_legacy_number`). Ids are stable
sha256 prefixes (`rg-…`, `mc-…`); order follows the bundle.

**Engine misreadings (`isaac.grouping.engine_misreading.v0`)** are identified with their
evidence (engine fixes for its owner; the engine is not edited). The four MECHANICAL ones do
not block a proposed group — the group records `merged_despite_engine_reading: [{kind,
run_key, evidence}]` and its confirm question says so in plain words:

1. `scan_index_token_read_as_value` — every scan-file witness of a conflict is that scan
   file's own trailing index (`_001` → 1); measured as the sample number on 73/92 runs (2019).
   If this leaves the sample unstated, the sample key is the run's OWN name with counters and
   repeat markers removed (`sample_name_stem`, `sample_key_basis: "name_stem"`) — never a
   guessed material; only in this case. A digit token is a counter ONLY in a counter position
   (the leading token, the trailing scan index, or right after a repeat marker); any other
   differing number (a middle `_12_` vs `_1_`) keeps the runs apart as a merge candidate
   (`numeric_name_token_differs`).
2. `same_value_different_unit_spelling` — `9175.4` vs `9175.4 eV`, only in the field's own unit
   (`FIELD_UNITS`; no conversions).
3. `auxiliary_macro_read_as_method` — exactly one disagreeing `acquisition_method` reading names
   a technique (`*_XAS.mac`), the others are helper macros; 56/92, 67/87 runs.
4. `exported_file_read_as_acquisition` — a zero-scan run named like another run plus a
   data-file extension (`x.dat`); it joins that run's group as **context**
   (`context_run_keys`, no scans merged) when every condition it states agrees; otherwise it
   stays a merge candidate.

Beamtime-level `sample_number_inconsistent_with_sample_name` (≥ 2 sample numbers each read
beside ≥ 2 different sample names) makes `sample_or_electrode_number` **unknown** for that
beamtime (differences → merge candidates). `condition_violations()` independently re-checks
every proposed group (all condition-class keys of its measurement members agree) and is
written into `record_groups.json`; it must be empty.

**Roles (`isaac.grouping.run_role.v0`)**: engine classifier first (`alignment`,
`standard_or_reference`), else stem tokens (`align*`/`rough*` → alignment;
`foil*`/`calib*`/`reference*`/`standard*`/`ref`/`std` → reference), else sample; never merged
with samples.

**Acquisitions with no bundle run** (`isaac.grouping.unread_numbered_scans.v0`): text files
`<stem>.<NNN>` in one directory are one acquisition's scans (binary twins skipped); one group
each, conditions unknown. `isaac.grouping.unread_name_counters.v0` offers merge candidates
between those whose names are equal after removing a leading run counter, a trailing
acquisition counter and repeat markers. `isaac.grouping.unread_header_agreement.v0` turns such a
candidate into ONE proposed group when every scan's literal header statements agree (format,
detector and region files, beamline/mono line, gains, beam size, sample description; date,
point-count and weights/offsets lines are bookkeeping). Disagreement → stays a candidate with
the differing positions; headers absent/unreadable (name-only evidence) → stays a candidate. `groups_from_generic_runs()` adapts a non-engine reader's runs.

**Scientist approves:** the three key lists; the engine-misreading rules; every proposed group
and merge candidate.

## 2. Inputs and channels

Raw files are read from the source folder (`source_root`, else the bundle's
`local_root_hint`); each scan's sha256 must equal the bundle's `content_sha256`
(`source_hash_mismatch` otherwise). Readers (content-sniffed, `processing/readers.py`):
SPEC columns (last `#L` before data, the `bl15.signals` convention), SSRL XDAC text
(`Data:` + one name per line), delimited text; CR/CRLF endings normalised, duplicate column
names kept as `name#2`, short rows skipped and counted, binary content refused.

| Param | Default | Approve |
|---|---|---|
| `channels.energy_candidates` | `Achieved Energy, absev, energy, Energy, mono, Requested Energy, …` (measured: scientists' Athena energies equal BL15-2 `absev`, not `energy`) | yes |
| `channels.use_bl15_signal_selection` | true — use `bl15/signals.py`'s proposed HERFD channel | yes |
| `channels.fluorescence_candidates` | `vortDT…4, sum:DTC_FF, sum:FF, sum:SCA1_, Lytle, PIPS, If, fluor` (dead elements excluded, flagged) | yes |
| `channels.i0_candidates` | `I0, i0, IO`; none → `signal_only` + `i0_missing` | yes |
| `channels.transmission_after_sample` | `I1, It, IT` → mu = ln(I0/I1); reference/alignment groups prefer transmission | yes |
| `channels.reference_after_reference` | `I2, Iref, IR` → reference mu = ln(I1/I2) | yes |
| `channels.dead_time_rate_prefix` | `ICR1_` → flag `dead_time_correction_not_applied` (no rule approved) | yes |

Every choice, its basis and alternatives are in `channel_choice`; flags
`channel_choice_needs_review` / `channel_from_bl15_selector_suggestion`,
`energy_column_alternatives`, `multiple_signal_alternatives`.

**Reference channel for a foil on I2** (`isaac.xas.reference_channel_fallback.v1`, recorded as
`fallback_rule`). When an alignment group's ln(I0/I1), or that of a reference group a run name says is a
foil or a calibration (a token starting `foil`/`calib` or ending `foil`, e.g. `Tifoil`), fails the
edge checks of §7 (`no_edge`, `post_edge_not_at_1`, judged on a quick merge of its scans), the
reference channel is tried. v0 tried it for every `reference` group, and the `std`/`standard`/`ref`
tokens make a compound standard a reference too: a CoO standard with a dead I1 was switched to
ln(I0/I2), whose I2 is no reference foil's. It is tried only when a reference-after column (`I2`, `Iref`, `IR`) is a positive
intensity in every scan AND either a run name says the foil is on it (a `foil` token and an `I2`
token) or I1 is not a positive intensity in some scan. Candidates in order: ln(I1/I2) (the protocol's
reference pair) when I1 is a positive intensity in every scan, else ln(I0/I2). The first that passes
the same checks is used, flagged `channel_fallback_reference_channel`, with `basis.fallback_from`
naming what failed and every candidate tried, and QC warns
`channel_fallback_transmission_failed_edge_checks`. When none passes, the choice is unchanged (it
fails on its own) and `basis.reference_channel_tried` + flag `reference_channel_tried_not_usable` say
what was tried. Never for a sample group. Measured on a real BL4-3 beamtime (a Ti foil run said to be on I2): I1
read −3.6 to 26 counts, so ln(I1/I2) is not tried; ln(I0/I2) is refused too, because I2 RISES about
270× across the edge (≈300 → ≈80 000 counts, as a fluorescence or yield signal does, not a transmitted
beam), so ln(I0/I2) falls at the edge (post-edge level −0.68 from the pre-edge line at each energy,
−1.02 at E0; re-measured under v1 of §7). That group fails with both statements;
which signal its I2 is, is a question for the scientist. Per scan: energy sorted
(non-monotonic steps counted), exact duplicate energies averaged, non-finite points dropped
and counted.

## 3. Calibration

E0 = larch `find_e0` (maximum of the first derivative). Reference: a reference group's own
signal, else an in-scan reference channel (I1/I2) whose edge SNR ≥ `reference_min_edge_snr`
(10). The shift is tabulated − measured (table `processing/edges.py`, xraydb 4.5.8 /
Elam-Ravel-Sieber 2002).

**Authority rule.** Only a scientist's processing-approval decision applies a shift:
`calibration_approvals[group_id] = {element, edge, decided_by, decision_id}`, recorded by the
scientist (with `--by`) through the bundle's decision commands; an approval without a named
decider is ignored (`calibration_approval_incomplete_ignored`). Everything else can only
**propose** the reference element/edge — the shift is then computed and reported but NOT
applied (`calibration_shift_awaiting_approval`, `reference_approved: false`):

* a params-file value `calibration.proposed_reference` (labelled `params_file_value`; a params
  file is never a scientist decision; the v0 key `confirmed_reference` is read the same way);
* for a reference group, file-name/header evidence (`stated_by_evidence`): a `foil` token plus
  exactly one element-symbol token, and an edge from the bundle's element evidence and/or a
  header `<El><Edge>_` symbol (XDAC region file), all agreeing.

Without any reference: no shift, `no_reference_available` (r2-a: not also
`calibration_reference_unconfirmed`, which flags a reference found but not approved). A foil group's shift is
never propagated to sample groups. `max_plausible_shift_eV` 25; `align_scans_by_reference`
false. **All calibration params need approval.**

**An in-scan reference needs two usable scans** (`isaac.xas.in_scan_reference_min_scans.v0`). An
in-scan reference channel is proposed only when its edge is usable (SNR ≥ 10) in at least 2 scans;
otherwise no reference is proposed, flag `reference_edge_in_too_few_scans`, no shift is computed or
applied even under an approval, and `approve_calibration` is refused. Measured on a real BL4-3
beamtime: a 16-scan sample group had ONE scan at SNR 10.46, the others 0.6–3.5, per-scan reference
"edges" 4964.6–4985.5 eV; an approval as Ti K applied −8.6 eV (E0 4978.0 → 4969.4) from that one
scan, erasing the chemical shift the study measures (also 1 of 4 and 1 of 6 scans in two other
groups). A reference group's own signal still needs one scan. The result says
`reference_scans_usable` of `reference_scans_listed`, `reference_proposed` and
`reference_statement`; `reference_e0_spread_eV` is null with fewer than 2 usable scans (one scan
has no spread). r5: when the usable edges spread more than 0.5 eV (flag `reference_edges_disagree`),
`reference_proposed` is false and the sentence no longer says "naming its element and edge gives the
shift". An approval is still possible, only with `--accept-shift`. Measured on a real BL15-2 beamtime:
4 results had usable edges 5–20 eV apart (scatter, not an edge) and said `reference_proposed: true`.
Neither key is in `qc.json` or `params.json`, so no id moves.

*Why one scan for a reference group and two for an in-scan channel.* A reference group is a scan
of the reference itself (a foil run on its own): its signal is the reference's absorption in the
main channel, the edge sits far above the noise (a clean foil scan has SNR in the hundreds), and one
scan is often all a beamtime has of it, so that one scan is the measurement. An in-scan channel
rides along SAMPLE scans: whether it saw a reference at all depends on a foil being in the beam
behind the sample, and on a weak or absent reference its per-scan "edge" is wherever the noise
peaks. One scan just over SNR 10 among many below it is then what a fluctuation looks like (the
measured case above: per-scan edges spread over 21 eV); a second usable scan is the least that
shows the edge is the channel's own, and gives a spread to judge it by. `bundle show
processing-result` says when a result's spread is null although its hashed `qc.json` /
`params.json` say 0.0 (`calibration.reference_e0_spread_note`: they predate this rule).

**A large shift's size is confirmed** (`isaac.xas.calibration_shift_size_confirmed.v0`). Before
anything is recorded, `approve_calibration --element --edge` says the shift it would apply
against the tabulated edge ("the reference edge sits 8.6 eV above Ti K's tabulated 4966.0 eV;
approving applies -8.6 eV"); `bundle show processing-result` says it too (`calibration.would_apply`,
for an approved, proposed or absorber element/edge). A shift above `qc.warn_energy_shift_eV` (2 eV)
is recorded only with `--accept-shift <the value shown>` (to 0.1 eV; stored as the decision's
`value.accepted_shift_eV`), else refused with nothing recorded; processing applies such a shift
only when the approval's confirmed size matches, else flags `calibration_shift_size_not_confirmed`.
Shifts of 2 eV or less behave as before. These sentences, counts and the null spread are in the
result only: `params.json` and `qc.json` (hashed into the run id) keep exactly what they held, so a
group whose curve does not change keeps its result id.

A shift within 0.1 eV of the warning level is said and compared to 0.01 eV (`+2.04` needs its size
confirmed; `+1.96` does not; `--accept-shift` still matches to 0.1 eV), so the shown value never
reads as at or below the level while being above it.

**A curve that already carries a shift the rules would not apply** (c12-r). A result approved
under an older build may have baked in a shift these rules refuse (measured: −8.6 eV from 1 of 16
usable in-scan scans, no size confirmed). A decided result is kept on re-processing, so its curve
and E0 keep that shift. `bundle show processing-result` says the shift the curve carries
(`calibration.applied_shift_eV`) and, when the current rules would not apply it,
`calibration.carried_shift` ("This curve carries −8.6 eV that is now unconfirmed: … re-approve with
`--accept-shift -8.6`, or reject the result"). `build-records` and `validate` block that group
(`approved_result_calibration_unconfirmed`; nothing from the result composes, so it is never
exported) until the scientist either confirms the size (`approve_calibration --element --edge
--accept-shift <the carried size>`, accepted even when the reference is no longer proposed, since it
confirms the curve that exists) or rejects the result. When a re-processed result's approval is not
applied (`reference_edge_in_too_few_scans`, `calibration_shift_size_not_confirmed`),
`qc.statements.calibration_approval_not_applied` names that approval (decision, element/edge,
decider) and what would apply it.

**Overrides only make the calibration rules stricter**
(`isaac.xas.calibration_overrides_stricter_only.v0`). A params file may lower
`qc.warn_energy_shift_eV` (more shifts need their size confirmed) and raise
`calibration.reference_min_edge_snr` for in-scan channels, never the reverse: the confirmation
level used is min(2 eV, the override) and the in-scan SNR max(10, the override). An ignored override
is said in `qc.statements.params_override_ignored` and in the processing summary. (Measured on
synthetic data: `warn_energy_shift_eV: 30` let a plain approval apply −8.0 eV, and
`reference_min_edge_snr: 0.1` turned noise into a proposed reference with a 177 eV spread.) The
`large_energy_shift` QC warning still uses the configured value (it is a warning, and changing it
would move result ids); a reference group's own signal takes the configured SNR as before.

## 4. Deglitch / outliers (flag, never drop by default)

* ≥ `min_scans_for_cross_scan` (3) scans: each scan fitted as `a + b·median`; a point is
  flagged when |residual − median| > `point_z_threshold` (6) × scale, scale = max(scan's
  residual 1.4826·MAD, across-scan 1.4826·MAD at that energy) — so the edge under sub-eV
  jitter is not flagged but a one-scan spike is.
* fewer scans: residual against the line through the two neighbours, scaled by its MAD.
* a scan whose residual RMS/span > `scan_rms_ratio_threshold` (3) × the median scan's and >
  `scan_rms_floor` (0.005) is an outlier scan.
* `exclude_flagged` **false**: flagged points/scans are listed as `would_exclude`, kept in
  the merge, marked × in the plot. **Scientist approves k, the thresholds and exclusion.**

## 5. Merge

Grid = energy points of the widest-range scan; every scan contributes only inside its own
range (linear interpolation, no extrapolation); per point N, mean, std (ddof 1),
stderr = std/√N (`merged.csv`). Scans covering < 90 % of the grid are flagged
`scan_range_truncated` (measured: one short scan had cut a group's grid below E0); the result's
`scans_truncated` sentence names each scan's file (`qc.json`, hashed into the run id, keeps the
sentence it was first written with, naming source ids). The params key `merge.grid` keeps its
historical value `first_scan_points_within_common_overlap` although the grid is the WIDEST scan's
points: the params are hashed into every run id, so renaming it would move every result id.

**Aborted fragments** (r5, `isaac.xas.skip_aborted_scan_fragment.v0`). A usable scan with fewer
points than `merge.min_points` (20), in a group where another usable scan has at least that many,
stopped early: it is left out of the merge (skip reason `aborted_scan_fragment`, metric and warn
`scans_skipped_aborted_fragment`, `qc.statements.aborted_scan_fragment` names it). When no scan has
20 points nothing is left out. Measured on the real beamtimes: 26 fragments of 6–18 points, each
beside a scan of 222 points or more (BL15-2 2025-04: 6 groups; 2021-11: 1; BL6-2c: 17; BL4-3 MOF-Co:
2); they had been merged into the curves. The shortest scan still merged has 21 points. Those groups get new result ids
(their merged curve changes); no other id moves.
When the merged curve's first or last point comes from one scan alone whose signal is zero there
(the merged value is 0), `qc.statements.merged_curve_end_from_one_scan` says so; the grid is not
trimmed (that would change those curves and their ids). Measured on a real BL15-2 beamtime: a
7-scan group's last point (11497.1 eV) came only from a scan whose counts had stopped (normalised
−0.013); the widest scan reaching a fraction of an eV past the others (52 of 78 groups) with a real
value is not said.

**Zero signal points** (said after the run id; nothing is dropped; `isaac.xas.zero_signal_runs.v0`).
Each run of points where a merged scan's signal is exactly zero while another merged scan's is not
is one of three kinds:

* the counts STOP (a run of at least 2 points to the scan's LAST point), or a run whose counts come
  back that is at least **5 % of the scan's points and at least 3 points**: said in
  `qc.statements.merged_scan_zero_signal_points` and flagged `merged_scan_has_zero_signal_points`
  ("A person checks whether the beam was lost");
* runs of 1–2 points: isolated dropouts, one count line `qc.statements.merged_scan_isolated_zero_points`
  ("they read as detector dropouts, like glitches"), no flag;
* runs of 3 points or more under 5 % of the scan: one count line `qc.statements.merged_scan_short_zero_runs`
  with no claim of what they are (a dropout or a brief loss of beam cannot be told from the data), no flag.

Why 5 % and not a fixed number of points (measured, c12-r, every merged scan with such zeros on the
real beamtimes): on BL15-2 2021-11 (445 scans) recovering runs were at most 11 points, in 226-point
scans (4.9 %; 8 scans had a run of 5 or more), and I0 was positive at all of them; on BL15-2 2025-04
(610 scans, 6–222 points) recovering runs reached 25 of 46 and 30 of 74 points; BL15-2 2019-05 and
BL6-2c 2018-07 had runs of at most 4 points in 225. A fixed 5 points would flag 8 scans in 2021-11
and 202 in 2025-04, most of them short dropouts in long scans; 5 % (with 3 points at least) flags 1
and 54, the ones where a sizeable part of the scan has no counts. The counts-stop cases: 204 of 226
and 25 of 105 (2021-11), 138 of 222 (2025-04), 80 of 225 (2018-07). Before c12-r a 30-point run in
a 40-point scan whose counts came back was said as isolated dropouts: never again. Re-processed with
this rule, the flag is on 3 of 83 results of 2021-11 (was 2) and 15 of 128 of 2025-04 (was 1);
every result id is unchanged (83/83, 128/128, and 53/53 on BL4-3 2025-07), as the sentences are
added after the run id.

### 5.1 Scan selection: a proposal per scan (`isaac.xas.scan_selection_proposal.v0`)

Rules from the beamline scientist (Angel, 9 Nov 2026), binding:

* **Normalised data are never merged.** Each scan is normalised ALONE, only to judge it (trends, glitches, beam
  drops, diffraction peaks, errors); the merge is the RAW mu (If/I0) of the scans used, as in §5 (`core.merge`
  is unchanged).
* **An intensity drop alone never excludes a scan.** A scan is judged by its SNR, its quality and whether
  including it makes sense; an edge-step change is a group OBSERVATION ("possible dissolution or detachment"),
  never a reason.
* **Every exclusion is a proposal.** Nothing is left out by this rule: the scientist confirms with the params
  file's `exclude_scans` (§5, r4-a M6) and re-processes; the new result is the one approved.

**Series** — a *scan-template series (all samples measured with the same scan command)*, never one sample's
scans. Every energy scan of the bundle (every group's, once each) belongs to the series of its SPEC template (`#S`
command and scanned motor, e.g. `gscan energy`) and overlapping energy range. The series E0 is the median
per-scan E0 (larch `find_e0`) of its scans covering at least 95 % of its median scan's span. Every scan of the
series is normalised with ONE parameter set: E0 = the series E0 (plus the group's applied calibration shift), the
pre-edge a line from the second point to E0−30, the post-edge a line from E0+100 to the end. A scan with no `#S`
line (another reader) takes its group's own median E0. A motor scan (`ascan Sz`, `a2scan`, `loopscan`: the
scanned motor is not `energy`) is `not_an_energy_scan`, never a proposal. ONE time axis everywhere (trend,
first-vs-last, stability): the scan numbers, so a gap is real time (else the scans' places in the group). The
series pass is guarded: if it fails, every group's proposal is `not_evaluated` with the reason (processing never
fails for it). Each source file is hashed once per run. A `--group` run reuses the series stored by the last
processing run when its fingerprint (every source's bytes, every group's scans, the channel and merge parameters,
the rule) is this run's, reads no other group's files for it, and says so (`scan_selection_series.reused`).

**Per scan.** Completeness: it reaches E0+150 and covers ≥ 95 % of the group's widest scan (else
`incomplete_scan`). Noise: counting noise by detection mode — fluorescence μ = N/I0 with integer counts N:
σ = √(N+1)/I0; transmission μ = ln(I0/It) with BOTH It and I0 integer counts: σ = √(1/It + 1/I0) — and the
excess-noise factor F = measured ÷ counting noise from the residuals against the line through each point's neighbours, pre-edge
(below E0−10) and post-edge (above E0+40); a signal that is not counts uses its own neighbour scatter (no F).
Edge SNR = edge step ÷ post-edge noise per point. White-line energy and height (quadratic vertex), the energy at
half step, and their spreads by 40 noise-injection replicas seeded by the scan's own bytes. Artifacts: clusters of
at most 6 points beyond 6σ against the group consensus, quiet either side: a spike (one point), a diffraction peak
(a positive bump), a dip, or a beam drop (I0 under 90 % of its usual level there, the ring current divided out);
a beam drop mu = If/I0 divides out is listed apart. Merge relevance R = the bias the scan puts on the raw merge ÷
that merge's noise (XANES window E0−20…+80), and the merged edge SNR with and without it.

**Consistency and trend.** Each scan's energy shift and χ²/ν against the leave-one-out consensus (weighted by
edge step, as a raw merge weighs) over E0−20…+80. The trend test on shift, white-line energy and height is a
weighted slope (inflated by excess scatter) with a t-test at p < 0.01/3, confirmed by a first-vs-last difference
≥ 3σ, and beyond physical floors (0.15 eV; 0.03 in height). A step-at-start change-point test (the leading block
against the rest, multiplicity-corrected) catches a change that is a step, not a slope. The stable window is the
scans after the latest change, with no trend left. Groups of 2–3 scans get pairwise tests only
(`two_scans_disagree`, `odd_one_of_three`, `three_scans_change`: to look at). **Shift resolution** (review): the
shift fit favours fractional shifts (identical scans come out up to ~0.4 of the point spacing apart), so a shift is
never `energy_shifted` under one median point spacing within E0 ± 10 eV, and a trend or step in the shift needs a
change of at least half of it (and 0.15 eV). Two repairs of the fit itself were measured on the validated beamtime
and not taken: propagating the noise through the interpolation pinned shifts to whole spacings (26 of 666
proposals moved, the step-at-start group lost); shifting the consensus instead of the scan moved 16 and put two
scans 0.45 eV off in white-line energy inside a stable window.

**Decision.** `exclude_proposed`: `incomplete_scan`, `before_stable_window`, `shape_out_of_trend` (χ²/ν above both
its p = 10⁻³ value and 1.5 × the group median, AND R ≥ 1), `many_artifacts` (≥ 3 visible in the merge).
`needs_look`: `lowers_merge_snr` (the merged edge SNR is under 98 % of it without the scan: the scan is weaker —
a smaller edge step or more noise — not wrong; review: a look, never an exclusion, as an intensity drop alone never
excludes a scan), an artifact with R ≥ 1,
`beam_drop` (I0 under 50 %), `excess_noise` (F > 2), `energy_shifted` (beyond max(0.2 eV, 3σ, 4 × the robust
spread of the others, one point spacing)), `too_noisy_to_evaluate` (SNR < 2), `setup_differs_emiss` / `setup_differs_filter` (the
`#P` header), `i0_nonpositive`, `normalization_failed`, `still_evolving_no_stable_window`. Everything else is
`include` (with `*_below_merge_noise` / `beam_dip_divided_out` said). An edge-step change of 5 % or more is said
in `group_observations`. When NO scan of a group reaches the series window (a XANES-only or calibration-scan
design), none can be judged with the series parameters: `scan_selection.status` is `not_evaluated`, every scan
`not_evaluated` (`series_window_not_reached`), and nothing is proposed (an addition to the prototype, which would
have proposed every such scan for leaving out).

**Where it is, and why no id moves.** The thresholds are module constants in `processing/core.py` (`SEL_*`), not
protocol parameters: `params.json` is hashed into every run id. The rule id is in
`RULE_VERSIONS_SINCE_PROTOCOL_VERSION`. The proposal is attached after the run id: the result's `scan_selection`
(per scan `proposal`, `reasons[]`, `said[]`, `metrics{}`, `exclude_as`; per group `trend`, `change_point`,
`stable_window`, `edge_step_change`, `group_observations`, `merge_snr`, `exclude_proposed`, `needs_look`, `open`),
`qc.statements.scan_selection` (with the exact `exclude_scans` snippet, keeping any scan already left out) and the
review flag `scan_selection_proposed` while a proposal is open. `processing_results.json` (format 0.3.0) lists
every series under `scan_selection_series`. `merged.csv`, `qc.json`, `params.json` and every `run_id` are
byte-identical with the rule on or off. A bulk approval is refused while a proposal is open
(`mutations.BULK_APPROVE_REVIEW`); one approval records the open items in its note. The old `scan_to_scan_spread`
warning (`qc.warn_scan_spread`) stays: retiring it moves ids, and it is deferred.

**Measured** (one real BL15-2 Ir L3 HERFD beamtime, 90 sample groups, 666 scans): the proposals match the
validated prototype's on 662 of 666 scans; two are scans the merge already left out (a signal of zero at every
point, too few points), and two the prototype proposed leaving out for `lowers_merge_snr` alone are now to look at.
Every `merged.csv` and `run_id` is byte-identical with the rule off. On synthetic identical scans with 0.35 and
0.5 eV steps across the edge, no scan is said shifted (before the resolution floor: 17 and 14 of 96).

## 6. Normalize

larch `pre_edge` on the merged mu: e0 = find_e0, pre1 larch default, **pre2 −30 eV**,
**norm1 = min(100 eV, 0.4·(Emax−E0))**, norm2 larch default, **nnorm by window width: a line under 300 eV, a quadratic from 300 eV** (larch
counts the polynomial degree, and this is larch's own rule), flatten on. Defaults measured on 107 scientist Athena groups in the archive
(nor1 median 110 eV, pre2 mode −30, Athena order 2 in 82). Athena's order counts coefficients, so
its 2 is a line, larch's 1 (`isaac.xas.post_edge_order_is_larch_degree.v0`, 9 Nov 2026; until then
the default was larch 2, a quadratic, for every window: one order above what the scientists used on XANES ranges). Re-measured on
1304 groups in 50 real projects: Athena order 2 in 735, 3 in 569. A scientist who sets a degree
above 1 gets 1 when the post-E0 range is under 100 eV. Resolved values are recorded.
Outputs `normalized.csv` (norm, flat). **All need approval.**

## 7. QC (data quality only; provenance flags do not move it)

fail: 0 usable scans, < 20 points, edge step ≤ 0, I0 ≤ 0 on > 5 %, all-zero signal, an edge step
more than 2× the spectrum's own range (`edge_step_implausible`: the post-edge fit did not describe the
data, e.g. a zero-width post-edge range), and two checks that a curve is a normalised spectrum at all
(sanity bounds in `processing/core.py`, not protocol parameters; each fails with a plain sentence in
`qc.json` `statements`, and its metric is present only when it fails):

* **`post_edge_not_at_1`** (`isaac.xas.post_edge_level.v1`, metric `post_edge_level`): the post-edge
  level over the post-edge window (norm1 to norm2 above E0), in edge steps, is measured TWO ways — from
  the pre-edge line at each energy (`mean(mu − pre_edge_line) / step`, the mean of larch's `norm`) and
  from the pre-edge line held at its E0 value (`(mean(mu) − pre_edge_line(E0)) / step`) — and the curve
  fails only when BOTH are outside 0 to 2 (metric: the first; the finding also carries
  `level_from_line_at_e0`). A normalised spectrum sits about 1 step above; below 0 it falls at the edge
  (larch's edge step is |jump|, so a falling edge still has a positive step). Why both: v0 used only the
  line at E0, which ignores the line's slope across a 50–600 eV window, so sound transmission spectra
  failed (review: clean synthetic Co K-edges on a background of 2.5 at −0.44 to −0.09; a pre-edge slope
  of ±0.01 step/eV at −2 or 4); the line at each energy alone is wrong the other way when its slope,
  fitted over a short pre-edge window, is extrapolated far (real dilute Ir HERFD scans, 3 pre-edge
  points over 15 eV, extrapolated 280 eV: −0.73, 2.2–2.8). Measured with v1 on the four real beamtimes
  (BL15-2, BL6-2c, two BL4-3; 212 pass/warn curves judged): from the line at each energy −0.73 to 2.77
  (5th–95th percentile 0.80–1.49), from the line at E0 0.34 to 1.89 (0.82–1.27), the level nearer 1
  0.50 to 1.89; 7 sound fluorescence/HERFD curves are outside one way only (none in transmission: IrO2
  in transmission is 1.39 / 0.35). Failed both ways: a TiO2 anatase scan ending 122 eV above E0
  (2.49 / 2.45: a quadratic post-edge over 49–120 eV of EXAFS gave a step of 0.58 for a jump of about
  1.4), a noisy dilute Ir HERFD scan (2.11 / 2.11: step half its post-edge level, white line 13), a Ti
  foil whose ln(I0/I1) falls (−0.88 / −1.82) and an all-zero signal (3.84, already failing). The bounds
  stay 0 and 2 (the measurements do not move them), and no verdict on the four beamtimes changed from
  v0. **Not judged** when the scan ends
  less than 50 eV above E0 (no real post-edge window; measured: scans end 0.9–27 eV or ≥ 64 eV above
  E0): QC warns `post_edge_window_too_short` instead (metric `post_edge_span_eV`, "the scan ends N eV
  above E0, so the normalised level cannot be checked; its edge position is still usable") — 11 such
  curves on the four beamtimes, among them the two Ti calibration scans (19 eV), which therefore warn.
* **`no_edge`** (`isaac.xas.edge_above_noise.v0`, metric `edge_to_pre_edge_noise`): the edge step is
  less than 5 times the pre-edge scatter (std of mu about the pre-edge line; `1 / pre_edge_noise`).
  Measured on the 150 pass/warn curves with ≥ 3 pre-edge points: 16.5 to 5600, except that Ti foil read
  through a dead I1 (2.4). Curves with fewer than 3 pre-edge points (76, mostly BL6-2c) have no
  `pre_edge_noise` and are not judged by it. A derivative test (maximum of dmu/dE against its pre-edge
  scatter) was measured too and does not separate that foil (113) from real spectra.

Verdicts changed by the two checks from the build before them (pass/warn → fail): BL4-3 TiON 2 (the
anatase scan, the Ti foil on I2), BL15-2 1 (the dilute Ir HERFD scan), BL4-3 MOF-Co 0, BL6-2c 0 (one
curve that already failed `signal_all_zero` also fails `post_edge_not_at_1`). `post_edge_level.v1` and
`reference_channel_fallback.v1` changed no verdict on the four beamtimes (no real group was a compound
standard reaching the reference channel); their results keep their ids except the 4 failing
`post_edge_not_at_1`, whose statement now gives both levels.
warn: 1 scan, pre-edge noise/step > 0.02, median stderr/step > 0.02, glitches or outlier
scans flagged, readable scans skipped for lacking the chosen columns
(`scans_skipped_lacking_chosen_columns`, with `scans_readable` / `scans_skipped_lacking_chosen_columns`
metrics), |shift| > 2 eV, reference E0 spread > 0.5 eV, ≥ 3 identical maximum signal
values (saturation), non-monotonic energy, non-finite points, some I0 ≤ 0, a kept scan that ends
early (`scans_truncated`, flag `scan_range_truncated`, with the overlap range), a fallback from
transmission to fluorescence (`channel_fallback_transmission_not_positive`: transmission was chosen but
every scan kept fewer than 20 finite points; the statement in `qc.json` says what was tried). Else pass.
A scan whose signal is non-finite at most points is skipped as `signal_not_finite` (with `points_read`
and `nonfinite_dropped`), never as `too_few_points`. r5: scans skipped as `too_few_points` are said in
`qc.statements.scans_skipped_too_few_points` (after the run id): a scan with 5 or more points whose
energy column holds fewer than 5 values is not an energy scan (a motor or emission `ascan`; the SPEC
`#S` line is quoted), any other is a scan that stopped (aborted). Measured on BL15-2 2025-04: 30 such
scans, most of them `ascan`s of a sample motor or the emission energy, were skipped with no word. A scan whose signal is zero at every point is skipped
as `signal_all_zero` (c11-a; measured on BL15-2 2021: the last of 8 scans recorded no counts and pulled the
merged curve to 0 at its end) and the other scans are merged: warn `scans_skipped_signal_all_zero`, metric
`scans_skipped_signal_all_zero`, and a statement naming the scan. Only a scan that would otherwise be used
gets this reason, so only a result with such a scan has a new id. With every scan's signal zero there is no
curve. The `signal_all_zero` fail (metric `signal_all_zero_scans`, over the scans used) stays, for a result
an older build made. The rule is `isaac.xas.skip_signal_all_zero.v0` (named in each result's `rule_versions`).
A scan whose signal is exactly zero at SOME points where another merged scan's is not (per-scan
diagnostic `signal_zero_points`) is merged unchanged; section 5 says which runs of zeros are flagged
`merged_scan_has_zero_signal_points` and which are only counted (all outside `qc.json`, so no id moves).
Whether to leave such a scan out is the scientist's call: nothing is dropped for it.

### Known limits (for review)

* Deglitch can flag another element's real edge inside the scan range as a glitch (measured: the Mo
  L3/L2 edges in a MoS2 sulfur K-edge scan); flags never drop points, but a scientist should be told.
* Deglitch flags real spectral features as glitches: white lines and EXAFS oscillations, mostly in
  groups of one or two scans (the neighbour-line method), where a sharp real feature looks like a
  spike. Measured on real BL4-3 standards: a CoSO4 standard in sucrose, 32 of 303 points flagged; a
  0.8 wt% TiO2 anatase, 31 of 173. `glitches_flagged` therefore warns on most curves of those
  beamtimes. The detector is unchanged (flags never drop points; `exclude_flagged` is false); its
  thresholds are for the scientist to approve. r5: with fewer than 3 scans no flagged point is counted as
  a glitch, on the edge or off it: whenever `glitch_check_few_scans` is said,
  `qc.metrics.glitch_points_unjudged` counts them all (with or without points on the edge) and
  `glitch_points_off_edge` is absent (measured on BL6-2c: the on-edge sentence had counted the off-edge
  points as glitches beside the few-scan sentence saying they were no evidence). With fewer than
  `min_scans_for_cross_scan` (3) scans
  a result with flagged points carries `qc.statements.glitch_check_few_scans` ("with N scan(s), the
  glitch check compares neighbouring points and also flags real features such as the white line and
  oscillations; these N flags are not by themselves evidence of glitches"); measured on a real BL4-3
  beamtime: a clean Ti foil had 21 points flagged (z up to 37.7), two-scan groups 30–31, and 30 of
  34 results carried `glitches_flagged`. No count, flag, verdict or id changes (said after the run id).
  r2-a (`isaac.xas.glitch_points_on_edge.v0`): a flagged point within 5 eV of E0, or inside the one
  stretch of steep slope that holds the edge (slope taken on the merged curve WITH THE FLAGGED POINTS LEFT
  OUT, between the points two places either side; at least a quarter of its steepest), is on the edge:
  the check cannot tell a glitch from the edge there, so the point is unjudged, never cleared. Such
  points are listed apart (`steps[deglitch].outcome.flagged_points_on_edge`), counted
  (`qc.metrics.glitch_points_on_edge` / `glitch_points_off_edge`) and said
  (`qc.statements.glitch_points_on_edge`: "neither counted as glitches nor cleared"); measured on a
  real Pt L3 HERFD beamtime: with 4–5 scans the flagged points sat at E0 and on the white line, and 27
  groups carried `glitches_flagged`. The rule is not a protocol parameter (params.json is hashed); the
  stored count, flag and verdict stay as first written, so no result id moves.

  r4 (a real Ir L3 HERFD beamtime):
  - **Reference scans.** A reference scan whose edge step is more than 10^6 times its pre-edge noise (or not
    finite) is a degenerate channel, not a usable reference. Usable reference edges that spread more than
    `qc.warn_reference_e0_spread_eV` are not proposed, and an approval of them applies only with
    `--accept-shift`. A reference edge within 0.5 eV of the group's own sample E0 may be the sample itself and
    also needs `--accept-shift`.
  - **One scan sets the curve.** When leaving one scan out shrinks the merged curve's range more than 5× while the
    other scans show an edge of their own, the verdict is `fail` with `edge_from_single_scan`: the record's E0
    would be that scan's. `decide` refuses to approve it. When the other scans have no edge (dead, out of beam,
    dark), nothing fails and `only_scan_with_edge` says so. A flagged point from one scan whose affine-corrected
    residual lies far outside the median curve's own range is that scan's glitch, never "on the edge".
  - **Leaving a scan out.** A params file's `exclude_scans` (`{group id: [file name | relative path | source
    id[#scan]]}`) leaves named scans out of one group's merge (recorded in that group's params.json).
  - **Naming an Athena group for a group** (r6). A params file's `athena_match` (`{group id: [{"project":
    relative path | file name, "athena_group": Athena group name | label}]}`) ties one Athena group to one
    group, exactly. It is for a merge whose name matches no group (§8). Recorded in that group's params.json.
    `athena_match_not` (same shape) is the scientist's "no": that merge is not that group's.
    `athena_ignore` (r7; `[{"project": …, "athena_group": …}]`) sets aside a merge that is no group's: it is no
    longer listed. It is said once, in the run that passes it. Nothing is matched and no id moves. One that names
    no Athena group, several, or a merge that matches a group sets nothing aside and says so. One the same file
    ties in `athena_match` stays tied ("tied"). A capped list (500 kept) says how many there are.
  - **Bulk approval.** A bulk `decide --decision approve` is refused for any result whose curve carries a sentence
    the scientist must hear: one scan's glitch, an outlier scan, or the only scan with an edge. Plain points on the
    edge the glitch check cannot judge do not stop it: they are common on any sharp edge.
* The §7 post-edge level cannot judge a scan ending < 50 eV above E0 (`post_edge_window_too_short`
  warns; its normalised curve is unchecked, its E0 usable).

**The scientist's Athena results.** A group Athena marks already normalised (`is_nor`) is used as
stored (edge step 1, no re-normalisation), and believed only when it looks normalised: pre-edge mean
within 0.25 of 0 and post-edge mean within 0.25 of 1 (20 eV below / 50 eV above E0). Otherwise, and for
any Athena group whose reproduced edge step is implausible, the curve is not compared, not plotted
and not preferred, and its QC fails with the plain sentence. r5: every other Athena curve is judged by
the §7 post-edge level (`isaac.xas.post_edge_level.v1`) over the project's own nor1–nor2 window, the
pre-edge line being `mu − norm·step`; a per-scan set is judged on its mean normalised curve. Failing
both ways, its QC fails `post_edge_not_at_1` (so `decide` refuses to approve it), it is flagged
`athena_post_edge_not_at_1` and not preferred; a listed version that fails carries the flag. A result
decided before this check is kept as it was, with the flag and the sentence added (its stored verdict
is not rewritten).

**The scientist's own normalisation** (r5 review, `isaac.athena.project_normalisation.v1`). larch's
`AthenaProject.read(do_preedge=True)` is not Athena's curve: it passes `bkg_nnorm` to `pre_edge` unchanged,
while Athena (Ifeffit) counts coefficients (2 is a line, 3 a quadratic), and it ignores what the project
stores. ISAAC makes the curve as Athena does. With X = stored energy + `bkg_eshift` (`bkg_e0` in that
frame), L = `bkg_int` + `bkg_slope`·X and P = Σ `bkg_nc<k>`·X^k (all in absolute X; P fits mu itself):
`norm = (mu − L) / bkg_step`; `flat = norm` below E0 and `norm − [(P − L)(X) − (P − L)(E0)] / bkg_step` at
and above it (with `bkg_fixstep` too). The stored values are used only when they are current: a fresh
least-squares line over the stored pre-edge window is within 0.02 of a step of L, a fresh fit of P's own
degree over the stored normalisation window is within 0.03 of a step of P, and (step not fixed) P − L at E0
is the stored step within 1 %. A window too short to fit is not judged, unless Athena marks the group for
re-normalisation (`update_norm`). Otherwise Athena re-fits on display, and so does ISAAC: larch `pre_edge` on
X with the project's ranges, `nnorm = bkg_nnorm − 1`, and the stored step only with `bkg_fixstep`. Stored and
re-fitted values are never mixed. A per-scan set is the mean of its members, each made this way first. This
curve is what `athena_normalized.csv` (and so a record) carries, what is compared and what A1 judges; the
result's `reproduced_with` says which way it was made (`bundle show processing-result` prints it; a per-scan
set says how many of its groups were made each way). When it differs from larch's reading (by more than
0.01 anywhere, or the step by more than 1 %), that is larch's reproduction, never a fault of the scientist.
r6: it is said once per bundle, in one summary line, and no longer flagged on each result. Each result still
records it (`renormalised_from_project`), with the largest difference over the post-edge range
(`post_edge_difference_from_larch`) and `material` (more than 0.02 of the step there); the summary line names
the material results, and `bundle show processing-result` prints the record. On BL4-3 MOF-Co the
flag was on 16 of 16 Athena results, and 16 of 18 differ by more than 0.02, so a threshold alone would not
thin it out. Measured on the projects of five real beamtimes
(1,406 Athena groups): of 799 sample groups with a positive stored step, 763 are current and 36 re-fitted;
105 of 108 reference-channel groups are re-fitted (their stored values no longer fit the data). The
tolerances sit between the two: sample groups' lines deviate 0.0002 (median) to 0.009 (95th percentile),
their post-edge curves 0.002 to 0.022, the stale reference lines 0.1 (median) and up to 26. On BL4-3
MOF-Co (all 52 groups of the day-2 project current) the three curves that failed the post-edge check on
larch's reading (levels near 82 and 2.7; larch's step 0.0058 where the project stores 1.566) pass and agree
with ISAAC's curves. Over all 1,406 groups the check fails 36 sample groups on larch's reading and 17 now,
all difference spectra (`diff …` groups, levels −3.3 to 122), and 51 reference-channel groups (29 on
larch's reading); none of those is matched, one is listed as a version. Every result whose Athena curve, or
a listed version's, changed has a new id (against the first r5 commit: 36 results in 18 groups on MOF-Co,
11 in 6 on TiON, 150 in 76 on BL15-2 2021-11, 23 on BL6-2c, none on BL15-2 2025-04). The E0 a result
reports is still `bkg_e0` + `bkg_eshift`, which protocol question pq-005 (`athena.e0_frame`) leaves to Oscar (the real
shifts are at most 0.1 eV). **Thresholds need
approval.**
`qc.json` records metrics, reasons and thresholds. **Thresholds need approval.**

**Not applicable is not a verdict.** A group listing no scan (`no_scans`), or none of whose readable
scans yields an energy axis plus a signal under §3's channel rules (`no_xas_channel` — measured:
tab-separated `xes<N>` files, MCA arrays, headerless two-column files), gets
`applicability: {status: not_applicable, reason_code, what_the_data_states}` and NO QC verdict, no
output file and nothing to approve: "no ISAAC processing protocol covers this data yet". What the
data states is literal (source type, reader and profile, the reader's stated layout, column
labels); no technique is inferred. Everything else that goes wrong is still judged (`fail`).
Three rules keep that boundary honest: (1) every readable scan is asked, and when some form a
channel the first that does supplies the group's choice — the others are skipped with
`scan_lacks_chosen_columns` (flag `channel_from_a_later_scan`), never mixed in; (2) a signal-side
candidate column (I0, transmission, fluorescence, `sum:` member) that is present but not live is
a data-quality failure, `fail signal_channel_dead`, never "not applicable"; (3) a column whose
label names time (whole token `epoch`/`time`/`sec`/`seconds`/`timestamp`/`clock`) is never the
energy axis by value shape.

## 8. Athena-first

`.prj` files the bundle inventoried are read with larch (`AthenaProject.read(do_preedge=True)`
— larch's reproduction of the stored e0/pre1/pre2/nor1/nor2/nnorm/flatten); comparison in
the scientist's frame (energy + `bkg_eshift`). Matching (`isaac.athena.match_by_name.v1`):
normalised label/file name equals a member run stem, or stem + `_` + scan selection
(`5-6`, `001`, `merge…`), or stem + the SSRL XDC scan-file suffix `_A.NNN` (normalised `_a_NNN`,
any case; read as scan NNN) — v1 = v0 + that suffix, measured on two real BL4-3 beamtimes whose
scientists named each Athena group after the scan file it holds (`<stem>_A.001`): 161 + 29 Athena
groups matched nothing under v0; under v1 MOF-Co compares 20 record groups (5 agree, 15 differ; 2
more list several versions) and TiON 10 (2 agree, 8 differ), and for 12 + 9 of them ISAAC's data
normalised with the scientist's parameters reproduces the scientist's curve (rms < 0.01). Nothing
looser: no other letter, no prefix or substring matching; a name fitting two record groups matches
neither and is noted. Exact beats suffix; zero-scan groups take no part; identical data
count once; one merged group wins (r5: Athena's `is_merge` is read as written, `'e'`/`'n'`/`'k'` for the
space it merged in, `''` for none; reading it as a number made every merge false on five real
beamtimes); several merged groups beside per-scan groups are listed as versions with the per-scan
groups of each project as ONE set version, never a version per scan (measured on BL4-3 TiON: a
two-run group listed 6 versions, now 3); a group merged away (status `merged` or `split`) takes no
part in the match (measured: on BL4-3 MOF-Co 16 Athena groups and on TiON 4 were ambiguous between a
dead group and the live one holding its runs; a rejected group still takes part);
one-group-per-scan in one project is compared as a set
(mean of the scientist's per-scan normalisations, labelled derived); anything else
anything else is **several versions**: each is listed in `athena_versions[]` with what its
own files state (project path and file name, years in the path, label, merge flag, scan
selection, parameters), compared individually, and **none is selected**
(`athena_result_of_record: null`, question `which_athena_version_is_result_of_record`).
Matched: a `scientist_athena` result (their params recorded,
`preferred_for_record: true`) plus the ISAAC result with `comparison`: E0 delta, RMS of
flattened/normalised mu on the overlap, edge-step ratio, verdict `agree` (|ΔE0| ≤ 1 eV and
RMS ≤ 0.05) | `differs` | `not_comparable` (< 20 points or < 30 eV overlap). Diagnostics
(not in the verdict): `rms_norm_with_athena_params` (ISAAC data, scientist parameters) and
`rms_norm_same_scans_same_params`. Disagreement is a review item, never an override.

**A merge that matches no group** (r6, `isaac.athena.unmatched_merge_hint.v0`). A scientist's merge (Athena
`is_merge`, or a merge word in its name) whose name matches no group is not used. It is never dropped
silently. `isaac process` lists each one (`athena.unmatched_merges`; the same label and data in several
projects is one) and says "a merge exists but was not matched" in one summary line. Near names are hints
only, never a match. A group (not rejected) is a candidate when the merge's name STARTS with the group's
run number and shares another word with it, or when the two names (without run numbers) are at least 85 %
alike. A number later in the name (scans `1_4`, a replicate `_2`) is no run number. A likeness is vetoed
when the names differ in a token with the same letters and other digits (`m200mV` / `m300mV`, `s1` / `s2`):
that is another sample. Run-number hints come first; they never hide likeness hints. Each hint names the
words in which the names differ. Each candidate group's results carry the sentence
(`qc.statements.athena_merge_not_matched`, flag `athena_merge_not_matched`) and ISAAC's own result asks
`athena_unmatched_merge_for_group`. None of this is in a hashed file, so no id moves. The scientist decides:
to use a merge, name it in a params file's `athena_match` and process again. It is then that group's
candidate (match kind `named_by_scientist`), handled like any other: one merge is preferred over the
per-scan groups beside it, several are versions to choose between. Its run id moves (another curve). A
copy of it in another project is no longer listed. A tie that names no Athena group, several, or no live
group ties nothing and says so; a tie that takes an Athena group from the group its name matched says so.
To say no, name it in `athena_match_not`: it is no longer hinted for that group (nothing else changes).

r7 changes (`isaac.athena.unmatched_merge_hint.run_numbers.v0`, `isaac.athena.reference_channel.v0`):

- A hint never crosses run numbers. When both names start with numbers (electrode and run, `01_05_…`), they must
  be the same numbers in the same order, or the shorter list must start with the same number and sit inside the
  longer (`01_12_13` and `01_12`). A single number may be one the other names (a merge `03_05_…` of runs
  03 and 05 still hints group `05_…`). The same numbers rank first. `differs_in` names the run numbers that differ.
  A leading `Ref` word is no part of the name.
- Athena names the reference channel it reads beside a sample `"  Ref <name>"` (exactly: two spaces, `Ref`, a
  space; every one of 108 real labels has this form). Such a group is a reference foil,
  not a sample merge. It is never listed, hinted or asked about; the summary line counts it. Measured on a real
  BL15-2 beamtime: 77 of 79 "merges that match no group" were reference channels, and their hints sat on 116 of
  153 results. After: 2 merges, hints on 3 results.
- Every unmatched merge is named. The summary line names the ones with no near name too: label, project, and the
  groups whose Athena groups share that project (`groups_in_project`). The `process` reply lists the first 10
  (`athena_unmatched_merges`). `isaac bundle list <bundle_dir> athena-merges` pages them all.
- An Athena group whose name matches several groups is used for none. It is said in one summary line, with the
  groups. When they are live, the line says they may be one sample measured in several runs, and names a proposed
  merge candidate between them. A hint only: ISAAC never merges groups. The scientist decides.

A tie is no decision kind of its own. The tied Athena result says it (`athena_match_tie`: project, Athena
group, the run's params.json; flag `athena_named_by_scientist`). A bulk approval refuses it. Its approval's
note records the tie, the record's `generated_by.notes` says it, and the params.json is evidence in the
sidecar. Once a group's merge is tied (now, or in its decided result), the group is not hinted or asked
again, and kept results lose the sentence. A later `process` without that params file says "the params
file's athena_match for this group was not passed this time". r7: when a params file made the new run, the line on a
decided result says so: "the params file's exclude_scans leaves X out of the merge", "… athena_match ties …", "the
params file sets qc.k", or that one of these was not passed this time. Each run's params.json is read for it: its
`excluded_scans` and its `changed_from_default`. A parameter that differs while neither run's params file set it is
the build's doing ("this build added or changed the default of …"), and so are other rule versions ("this build
processes it under other rules"). The build's reason is said beside a params-file reason, never hidden by it. Measured on BL4-3 MOF-Co: 46 of the
scientists' 56 merges (27 distinct) matched no group, with typed-short names (`spt2` for `spot2`, `sugar`
for `sucrose`, `0V` for `m0V`, `postXA`); 12 have near-name hints, naming 13 groups. ISAAC said nothing
of them before.

## 9. Outputs and states

Each run writes to its own **content-addressed run directory**
`processing/<group_id>/<run_id>/` (`run_id` = sha256 over protocol version, group, used input
digests and every data output; the plot is excluded). Earlier runs are never overwritten or
deleted: an identical re-run reuses the same directory and ids without rewriting a byte, and
any changed parameter yields a NEW `run_id` and NEW, undecided `result_id`s
(`proc-<group>-<run_id>-isaac|athena`), with `prior_run_ids` listed. Each run directory also
holds `result.json`: the result as the run first produced it. `result.json` is written once, with the run, and a re-run
into an existing run folder never rewrites it, so a plain sentence added to `qc.statements` by a later build (the
statements are not hashed into `run_id`) is in `bundle.json`, `isaac bundle list <bundle_dir> processing-results` and
`isaac bundle show <bundle_dir> processing-result <result_id>`, which are the current result. Paths are relative to the
bundle directory and never contain `..`.

`<bundle_dir>/record_groups.json`; `<bundle_dir>/processing/processing_results.json`
(`processing_results[]` in the bundle-v1.1 shape, `unread_acquisition_results[]`);
per group `merged.csv`, `normalized.csv`, `qc.json`, `params.json`, `plot.png`
(`athena_normalized.csv` when matched; r7: `plot_athena_v<n>.png` for a chosen Athena version, its curve over
ISAAC's, named in that result's `athena_version_plot`; never hashed, so no id moves) — paths relative to the bundle dir, each with sha256.
Without numpy/xraylarch: `processing/status.json` with `processing_unavailable`, no results.

## 10. What a scientist must approve before any of this is relied on

Every proposed group; the condition/bookkeeping split; channel and energy-column choices;
calibration reference and shift; deglitch thresholds and whether to exclude; the merge
grid rule; normalisation ranges and E0; QC thresholds; Athena tolerances and the matching
rule. `params.json` lists `needs_scientist_approval` per group.

## 11. Open questions for Oscar / Angel (`protocol_questions`)

Machine-readable in `processing/protocol.py` `PROTOCOL_QUESTIONS`, written into every
`params.json` and the `processing_results.json` header so the skill can ask them:

```json
[
  {
    "question_id": "pq-001",
    "topic": "energy_column",
    "ask": "angel_or_oscar",
    "text": "At SSRL BL15-2, is `absev` (encoder/absolute energy) the energy axis to use, rather than `energy`? Measured: the scientists' Athena energy arrays equal `absev`, 1.7-3.4 eV from `energy`.",
    "affects": [
      "channels.energy_candidates"
    ],
    "current_default": "absev before energy",
    "status": "open"
  },
  {
    "question_id": "pq-002",
    "topic": "grouping.new_spot",
    "ask": "angel_or_oscar",
    "text": "Is a measurement on a NEW SPOT of the same sample, at the same condition, a repeat (one record) or a different result?",
    "affects": [
      "grouping.UNKNOWN_KEYS.new_spot"
    ],
    "current_default": "unknown: separate groups plus a merge candidate",
    "status": "open"
  },
  {
    "question_id": "pq-003",
    "topic": "grouping.step_number",
    "ask": "angel_or_oscar",
    "text": "Is a numbered step (`stepNN`) a repeat at the same condition, or a different point in a protocol?",
    "affects": [
      "grouping.UNKNOWN_KEYS.step_number"
    ],
    "current_default": "unknown: separate groups plus a merge candidate",
    "status": "open"
  },
  {
    "question_id": "pq-004",
    "topic": "calibration.foil_shift_to_samples",
    "ask": "oscar",
    "text": "Should the energy shift measured on a reference-foil group be applied to the beamtime's sample groups (and under which conditions)?",
    "affects": [
      "calibration.proposed_reference",
      "calibration.apply_shift_when_confirmed"
    ],
    "current_default": "never propagated automatically",
    "status": "open"
  },
  {
    "question_id": "pq-005",
    "topic": "athena.e0_frame",
    "ask": "oscar",
    "text": "Is the E0 stored in an Athena project in the energy-SHIFTED frame (after bkg_eshift) or the stored-energy frame? This build follows larch's read_athena reproduction (stored frame) and compares in the shifted frame.",
    "affects": [
      "athena comparison: e0_delta_eV"
    ],
    "current_default": "larch read_athena convention",
    "status": "open"
  },
  {
    "question_id": "pq-006",
    "topic": "channels.dead_time",
    "ask": "oscar",
    "text": "For SSRL XDAC data, should SCA fluorescence channels be dead-time corrected with the ICR columns, and by which rule?",
    "affects": [
      "channels.dead_time_rate_prefix"
    ],
    "current_default": "no correction; flag dead_time_correction_not_applied",
    "status": "open"
  },
  {
    "question_id": "pq-007",
    "topic": "athena.result_of_record",
    "ask": "scientist_of_the_beamtime",
    "text": "When several Athena projects hold different versions of one measurement (re-normalised, glitch-removed, smoothed), which is the result of record?",
    "affects": [
      "processing_results[].athena_versions"
    ],
    "current_default": "none selected; each listed and compared",
    "status": "open"
  }
]
```
