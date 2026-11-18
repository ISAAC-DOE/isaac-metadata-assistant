# Recipe fields

```yaml
data_root: ~/xas_work/<beamtime>      # spec paths resolve here
reader: spec | ssrl_xdc               # SPEC (BL15-2, ...) or EXAFS Data Collector (BL4-3, ...)
sca_channels: [1, 2, 3]               # ssrl_xdc: subset of SCA windows (default: all summed)
column_map: {IF: vortDT}              # spec: logical channel -> SPEC column (Energy_eV absev, IF vortDT,
                                      #   sec sec); 2019 BL15-2: {IF: DTC_FF1, Energy_eV: mono, sec: Seconds}
samples:
  - spec: <file or XDC stem>          # XDC: stem, files <stem>_A.001 ...
    name: ...; output_name: ...
    scans: []                         # empty = all; or the list to keep
    outliers: [1]                     # dropped from the average (hand-picks)
    role: sample | reference
    note: "logbook: discard first scan ..."   # why; keep it with the data
calibration:
  mode: glitch_I0 | ref_foil | foil_timeline | none
  method: model | shape | inflection  # model for glitches, shape for foils, inflection = MATLAB
  glitch_dips: 1 | 2                  # model: 2 = doublet glitch, anchor = midpoint of the two dips
  window_eV: [lo, hi]                 # inflection window (also the template's own anchor)
  shape_window_eV: [lo, hi]           # fit window around the feature (model and shape)
  max_shift_eV: 1.0
  ref_signal: ln(I0/I2)               # ref_foil
  foils: [{spec: ..., ref_signal: ln(I0/I1)}]   # foil_timeline
  foil_window_eV: [lo, hi]            # foil_timeline: inflection window of the foils
  reference_foil: 0                   # foil_timeline: index of the anchor-defining foil
  reference_sample: earliest | <name>
  reference_scan: mean | <scan number> | first
energy_grid: reference                # or an explicit list
averaging: {weights: uniform, min_scans: 1}
screening:                            # optional; drops are logged with the reason
  anchor_mad: 5                       # failed anchors (floor anchor_floor_eV 0.03)
  shape_mad: 6                        # off-shape scans (also > shape_min_ratio 1.5 x median)
  window_eV: [lo, hi]
  min_coverage: 0.9                   # aborted scans
normalize: {element: Ir, core: L3, range: [11166, 11206, 11275, 11487], model: victoreen}
                                      # bg_decreasing: true is the default (false = old free Victoreen)
outputs: {output_dir: reduced, save_per_scan: false, save_avg: true, save_diagnostic: true}
```

Screening flags: dead fluorescence channel, failed anchor, off-shape scan, aborted scan.
It cannot judge which sample spot or which post-step transient is "right": that is a
decision for the user (Example2: two spots with different chemistry; 2021: first scans after
a potential step). Split such files into separate samples with scan lists.

Scan-level distortions (screening, opt-in): `post_drift` (late signal collapse, end vs start of the
post-edge > 15 % of the step) and `ratio_shape` (raw ratio of each scan to the median of the other
scans over a post-edge window: tilt or bump > `mad` x MAD and > `min_frac`). Neither resolves a 4 %
drift in a 4-scan file or a bubble scan in a noisy file (BL6-2 2018 0 V scan 3, -0.6 V scan 5):
those are hand outliers with the reason in the note.
