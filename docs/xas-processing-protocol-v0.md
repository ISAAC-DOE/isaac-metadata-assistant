# ISAAC XAS processing protocol `isaac.xas.v0` (with record grouping)

> **DRAFT — not reviewed by a beamline scientist. Oscar's protocol supersedes on arrival.**
> Status `draft_unreviewed`, version `0.1.0`. Every result is `state: needs_review`. Nothing
> here produces an official ISAAC value; results are review material for a scientist.

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

**Reference channel for a foil on I2.** When a reference or alignment group's ln(I0/I1) fails the
edge checks of §7 (`no_edge`, `post_edge_not_at_1`, judged on a quick merge of its scans), the
reference channel is tried — only when a reference-after column (`I2`, `Iref`, `IR`) is a positive
intensity in every scan AND either a run name says the foil is on it (a `foil` token and an `I2`
token) or I1 is not a positive intensity in some scan. Candidates in order: ln(I1/I2) (the protocol's
reference pair) when I1 is a positive intensity in every scan, else ln(I0/I2). The first that passes
the same checks is used, flagged `channel_fallback_reference_channel`, with `basis.fallback_from`
naming what failed and every candidate tried, and QC warns
`channel_fallback_transmission_failed_edge_checks`. When none passes, the choice is unchanged (it
fails on its own) and `basis.reference_channel_tried` + flag `reference_channel_tried_not_usable` say
what was tried. Never for a sample group. Measured on a real BL4-3 beamtime (`31_Ti_foil_I2_120`): I1
read −3.6 to 26 counts, so ln(I1/I2) is not tried; ln(I0/I2) is refused too, because I2 RISES about
270× across the edge (≈300 → ≈80 000 counts, as a fluorescence or yield signal does, not a transmitted
beam), so ln(I0/I2) falls at the edge (post-edge level −1.0). That group fails with both statements;
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

Without any reference: no shift, `calibration_reference_unconfirmed`. A foil group's shift is
never propagated to sample groups. `max_plausible_shift_eV` 25; `align_scans_by_reference`
false. **All calibration params need approval.**

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
`scan_range_truncated` (measured: one short scan had cut a group's grid below E0).

## 6. Normalize

larch `pre_edge` on the merged mu: e0 = find_e0, pre1 larch default, **pre2 −30 eV**,
**norm1 = min(100 eV, 0.4·(Emax−E0))**, norm2 larch default, **nnorm 2** (1 if the post-E0
range < 100 eV), flatten on. Defaults measured on 107 scientist Athena groups in the archive
(nor1 median 110 eV, pre2 mode −30, nnorm 2 in 82). Resolved values are recorded.
Outputs `normalized.csv` (norm, flat). **All need approval.**

## 7. QC (data quality only; provenance flags do not move it)

fail: 0 usable scans, < 20 points, edge step ≤ 0, I0 ≤ 0 on > 5 %, all-zero signal, an edge step
more than 2× the spectrum's own range (`edge_step_implausible`: the post-edge fit did not describe the
data, e.g. a zero-width post-edge range), and two checks that a curve is a normalised spectrum at all
(sanity bounds in `processing/core.py`, not protocol parameters; each fails with a plain sentence in
`qc.json` `statements`, and its metric is present only when it fails):

* **`post_edge_not_at_1`** (`isaac.xas.post_edge_level.v0`, metric `post_edge_level`): the post-edge
  level — mean mu over the post-edge window (norm1 to norm2 above E0) minus the pre-edge line AT E0,
  over the edge step — is outside 0 to 2. A normalised spectrum sits about 1 step above; below 0 it
  falls at the edge (larch's edge step is |jump|, so a falling edge still has a positive step). Measured
  on every pass/warn curve of four real beamtimes (BL15-2, BL6-2c, two BL4-3; 225 with a window): every
  curve whose plot shows a normalised spectrum lies at 0.31 to 1.89; outside were a TiO2 anatase scan
  ending 122 eV above E0 (2.44: a quadratic post-edge over 49–120 eV of EXAFS gave a step of 0.58 for a
  jump of about 1.4), a noisy dilute Ir HERFD scan (2.11: step half its post-edge level, white line 13),
  two Ti foil calibration scans ending 19 eV above E0 (3.05, 3.43: the "post-edge" window lies inside the
  edge; their E0 is unaffected) and a Ti foil whose ln(I0/I1) falls (−1.75). The plain mean of larch's
  `norm` over the window was measured first and is NOT the test: it also carries the pre-edge line's
  slope extrapolated across the window, which put good spectra (a CoSO4 standard in sucrose 1.93, IrO2
  in transmission 1.40, nine dilute HERFD scans with 3 pre-edge points 2.1–2.8 or −0.7) far from 1; at
  |mean − 1| > 0.5 it would have failed 18 curves, most of them sound.
* **`no_edge`** (`isaac.xas.edge_above_noise.v0`, metric `edge_to_pre_edge_noise`): the edge step is
  less than 5 times the pre-edge scatter (std of mu about the pre-edge line; `1 / pre_edge_noise`).
  Measured on the 150 pass/warn curves with ≥ 3 pre-edge points: 16.5 to 5600, except that Ti foil read
  through a dead I1 (2.4). Curves with fewer than 3 pre-edge points (76, mostly BL6-2c) have no
  `pre_edge_noise` and are not judged by it. A derivative test (maximum of dmu/dE against its pre-edge
  scatter) was measured too and does not separate that foil (113) from real spectra.

Verdicts changed by the two checks (pass/warn → fail): BL4-3 TiON 4 (the anatase scan, both Ti
calibration scans, the Ti foil on I2), BL15-2 1 (the dilute Ir HERFD scan), BL4-3 MOF-Co 0, BL6-2c 0
(one curve that already failed `signal_all_zero` also fails `post_edge_not_at_1`).
warn: 1 scan, pre-edge noise/step > 0.02, median stderr/step > 0.02, glitches or outlier
scans flagged, readable scans skipped for lacking the chosen columns
(`scans_skipped_lacking_chosen_columns`, with `scans_readable` / `scans_skipped_lacking_chosen_columns`
metrics), |shift| > 2 eV, reference E0 spread > 0.5 eV, ≥ 3 identical maximum signal
values (saturation), non-monotonic energy, non-finite points, some I0 ≤ 0, a kept scan that ends
early (`scans_truncated`, flag `scan_range_truncated`, with the overlap range), a fallback from
transmission to fluorescence (`channel_fallback_transmission_not_positive`: transmission was chosen but
every scan kept fewer than 20 finite points; the statement in `qc.json` says what was tried). Else pass.
A scan whose signal is non-finite at most points is skipped as `signal_not_finite` (with `points_read`
and `nonfinite_dropped`), never as `too_few_points`.

### Known limits (for review)

* Deglitch can flag another element's real edge inside the scan range as a glitch (measured: the Mo
  L3/L2 edges in a MoS2 sulfur K-edge scan); flags never drop points, but a scientist should be told.
* Deglitch flags real spectral features as glitches: white lines and EXAFS oscillations, mostly in
  groups of one or two scans (the neighbour-line method), where a sharp real feature looks like a
  spike. Measured on real BL4-3 standards: a CoSO4 standard in sucrose, 32 of 303 points flagged; a
  0.8 wt% TiO2 anatase, 31 of 173. `glitches_flagged` therefore warns on most curves of those
  beamtimes. The detector is unchanged (flags never drop points; `exclude_flagged` is false); its
  thresholds are for the scientist to approve.
* The two §7 shape checks judge the normalisation made with the default post-edge range: a short scan
  (calibration foils ending ~20 eV above E0) fails `post_edge_not_at_1` although its E0 is sound.

**The scientist's Athena results.** A group Athena marks already normalised (`is_nor`) is used as
stored (edge step 1, no re-normalisation), and believed only when it looks normalised: pre-edge mean
within 0.25 of 0 and post-edge mean within 0.25 of 1 (20 eV below / 50 eV above E0). Otherwise, and for
any Athena group whose reproduced edge step is implausible, the curve is not compared, not plotted
and not preferred, and its QC fails with the plain sentence. **Thresholds need approval.**
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
count once; one merged group wins; one-group-per-scan in one project is compared as a set
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

## 9. Outputs and states

Each run writes to its own **content-addressed run directory**
`processing/<group_id>/<run_id>/` (`run_id` = sha256 over protocol version, group, used input
digests and every data output; the plot is excluded). Earlier runs are never overwritten or
deleted: an identical re-run reuses the same directory and ids without rewriting a byte, and
any changed parameter yields a NEW `run_id` and NEW, undecided `result_id`s
(`proc-<group>-<run_id>-isaac|athena`), with `prior_run_ids` listed. Each run directory also
holds `result.json`. Paths are relative to the bundle directory and never contain `..`.

`<bundle_dir>/record_groups.json`; `<bundle_dir>/processing/processing_results.json`
(`processing_results[]` in the bundle-v1.1 shape, `unread_acquisition_results[]`);
per group `merged.csv`, `normalized.csv`, `qc.json`, `params.json`, `plot.png`
(`athena_normalized.csv` when matched) — paths relative to the bundle dir, each with sha256.
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
