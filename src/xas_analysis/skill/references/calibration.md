# Energy reference: decision guide

What changes from beamline to beamline (and beamtime to beamtime) is mostly here. Two layers:

1. **Relative alignment within a beamtime**: put every scan on one energy axis. Choose a mode
   from the evidence `xas-analysis survey` prints.
2. **Absolute energy**: what that axis means. It rests on the beamline mono calibration
   (`mono reset from A to B` lines in the alignment file: e.g. BL15-2 sets a Pt L3 foil
   inflection to 11563.8-11564 eV). Across beamtimes it is NOT guaranteed: align on a shared
   standard (IrO2 for Ir L3) and state it.

## Modes (calibration.mode)

| evidence in the sample scans | mode | notes |
|---|---|---|
| foil edge at the sample's edge in ln(I0/I1), ln(I1/I2) or ln(I0/I2) | `ref_foil` | best: per-scan absolute reference |
| no foil, sharp dip in I0 common to all scans | `glitch_I0` | mono crystal glitch; position changes between beamtimes |
| neither; separate foil scans in the folder | `foil_timeline` | linear interpolation in time between foil anchors |
| nothing | `none` | energies as good as the beamline calibration; say so |

Methods (`calibration.method`):
- `model` (glitch_I0): Gaussian dip + linear trend fitted to ln I0 in `shape_window_eV`;
  template-free, so no grid-phase bias. Default for glitches: 2.6 meV median per-file scatter
  (BL15-2 2025, 3.8 meV 90th pct) vs 4.3 / 12.9 meV for `shape`.
- `shape` (ref_foil, foil_timeline, or glitch): shift of the whole feature against a template
  scan with free scale + offset. Foils: 4-5 meV. For a glitch only ~2 grid points wide it
  inherits the template's sampling: 10-40 meV file-to-file bias when files use different grids.
- `inflection`: max |dy/dE|, reproduces reduce_xas_v2 (MATLAB parity); 10-80 meV scatter.
  `glitch_dips: 2`: DOUBLE glitch, two Gaussian dips with shared width and free separation,
  anchor = midpoint (`doublet_sep_eV` bounds the separation, default 0.8-2.2 eV).
The survey compares model and shape on 12 files and recommends the lower scatter, then tests
for a doublet (two-dip fit ok on >= 70 % of scans, stable separation, lower per-file scatter).

Reference: `reference_sample: earliest` + `reference_scan: mean` (mean anchor of the earliest
file's scans: closest in time to the beamline calibration). The energy grid is that file's
first scan: if it is on an unusual grid, set `reference_sample` to the earliest file on the
common grid (`recipe init` does this).

## Traps (each one happened)
- **energy vs absev** (BL15-2 SPEC): `absev` is the encoder. 2021: `energy` wandered +2/-2.8 eV
  within scans; 2025: `energy` read 2.3 eV below `absev`. Check the reference feature stays
  fixed on absev across the beamtime.
- **Sharp symmetric glitch** (2025, 11226.6 eV, ~0.5 eV wide): the steepest slope flips
  between the two edges, so inflection anchors are bimodal (0.5 eV apart). Use `shape`.
- **Second glitch in the window** (2025: dips at 11226.6 and 11230.75 eV): a shape window that
  takes in both moves ~9 % of the anchors by 50-120 meV when its edges move by <1 eV. Keep the
  window on one dip (survey: half-width <= 0.6 x distance to the next dip) and check the
  survey's window-sensitivity line (< 20 meV; it reports the spread of the per-scan changes,
  a common offset cancels in the shifts).
- **Narrow glitch, mixed grids** (2025: FWHM ~0.5 eV, 0.1-0.5 eV steps, the reference file on
  another grid): the shape fit put every file ~35 meV off the reference file. Use `model`.
- **Absorber in the I0 path** (tender X-rays: S contamination, sulfate dip at 2482.8 eV): a fixed-
  energy marker, but a dip on an edge step; the dip model only follows it near the peak and the
  window moves per-scan shifts by ~30 meV. The survey picks the window from the data; quote it.
- **Doublet glitch** (BL15-2 May 2019, Pt L3: dips at ~11702.1 / 11703.5 eV, ~1.5 % each): a
  one-dip fit jumps between the two dips (anchors bimodal by 1.4 eV, 295 meV per-file scatter;
  single-dip survey window warning 107 meV). The doublet midpoint scatters 34 meV per file and
  agrees with Thom's published per-scan Athena alignment to 34 meV median (corr 0.93). The
  glitch drifted ~0.65 eV in mono units over 43 h: per-scan alignment is essential there.
- **Doublet that looks single** (BL6-2 2018: dips 1.5 eV apart, the one-dip fit 10 meV per file):
  the per-file scatter hides wrong-dip files. The survey decides by the two-dip fit itself
  (ok on >= 70 % of scans, separation std < 0.1 eV), not by comparing scatters. Check per-file
  mean anchors: a file offset by ~ the dip separation (or half of it) is a wrong-dip file.
- **Doublet midpoint is a convention** (BL6-2 2018): the dip separation changed by ~0.02-0.04 eV
  between files (1.52-1.54 vs 1.50 eV), which moves the midpoint ~10-15 meV relative to either dip.
  A shape- or one-dip alignment (Thom's Igor) then differs by that much. Report it as a systematic
  (~half the separation change) and check difference-spectrum conclusions against it.
- **Dark transmission chamber** (BL6-2 2018: I1 a flat ~987-count offset): ln(I0/I1) shows noise
  "edges". The survey skips a channel whose relative spread is < 0.5 % and < 0.3 x that of I0.
- **No absev column** (BL15-2 2019 SPEC: `mono`, time in `Seconds`): the survey reports the energy
  column and `recipe init` maps it (`column_map: {Energy_eV: mono}`); map `sec: Seconds` too
  (a missing time column no longer fails the resample check).
- **Glitch moved**: BL15-2 Ir L3 glitch at 11232.7 eV (2021) vs 11226.6 eV (2025). Never
  copy the window from another beamtime; survey first.
- **Region-step artefacts**: dips of 0.05-0.1 % in ln I0 at scan-region boundaries are
  trend-filter artefacts, not glitches (BL4-3 Ti K). The survey ignores shallow dips there.
- **Foil position**: a foil scanned in another detector position (BL4-3: on I2 instead of I1)
  can have a distorted edge (1.4 eV off). Use one position for the timeline.
- **Foils before the calibration**: the first foil scans of a beamtime may precede the mono
  calibration (BL4-3: 00/01 at 4963.2/4965.8 eV, 02 at 4966.2 eV after it). Keep the last
  foil before the first sample scan.
- **Sparse foil timeline**: two foil checks 19 h apart (BL4-3) bound but do not resolve the
  drift. Quote ~+-0.1 eV and ask for a foil scan per sample block / refill next time.
- **Alignment scans in sample files**: motor scans (Sz, Sy) inside a file are skipped by the
  shape anchor (energy axis does not span the window).
- **Legacy MATLAB** glitch/foil calibration applied no shift (Finding 1): legacy outputs are
  on the raw mono axis.
