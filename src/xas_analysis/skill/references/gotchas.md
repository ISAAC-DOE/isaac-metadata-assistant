# Per-beamtime findings

## BL15-2, Nov 2021, Hersbach IrOx acid (Ir L3 HERFD)
`recipes/ir_l3_hersbach_full_beamtime.yaml` (Example1-XAS is a 19-file subset).
- Mono: Pt L3 foil in front of I1, alignment #43/#44, reset 11567.8 -> 11564.
- Glitch 11232.7 eV (anchor), stable to <50 meV over 59 h. `energy` wanders vs absev.
- Edge jump falls up to 100x with potential/cycling (Ir loss): late spectra are
  normalization-limited (window spread 16-20 %).
- First scans after a potential step still evolving; Athena kept later scans (`_6-8`).
- Dead fluorescence channel scans (IF = 0), aborted IrO2 scan 1.
- vs Thom's Athena (`Normalized/*.nor`, `*_DiffSpectra_60mVRef.xmu`; same scans, constrained bg,
  2026-11-11): one energy offset + one scale per spectrum explain the normalized-spectrum
  differences (white-line rms 0.8-2.3 % -> 0.07-0.13 %). Offsets: 04-06 agree within 2-3 meV; in
  01-03 several spectra differ by 20-78 meV (01_JK1C 1200-1600 mV: his ~20-25 meV higher vs the
  060 mV reference; our glitch anchors stable within 12 meV). Scale: his low-loading JK3C (04, 06)
  and 01_JK1C 1800 mV (post-edge 0.969, -6.8 %) depart from the model-free reference; ours agrees.
  His diff files are not exactly differences of his .nor spectra (0.007-0.018 rms). No calib files
  for 2021: his per-scan shifts must be inferred (open).

## BL6-2c, Jul 2018, Hersbach Pt cathodic corrosion (Pt L3 HERFD; Nature Mater. 2025 data)
`recipes/pt_l3_hersbach_2018_07.yaml`; Readme: Pt foil FIP 11563.7 eV (alignment #49). Columns
`mono`, `Seconds`; I1 is DARK (~987 counts offset): no foil in the beam (the survey used to flag
ln(I0/I1) "edges" from it). I0 glitch = DOUBLET 11701.5 / 11703.0 eV (sep 1.516 +- 0.018 eV).
A one-dip fit looked fine per file (10 meV) but took the other dip in six files (250-390 meV
off Thom's per-scan shifts); with glitch_dips 2: median 4 meV, 95 % 20 meV (294 scans; one
scan where Thom's alignment failed by +1.5 eV). Same scans as Thom's 2023 renorm (28 spectra):
offset +0.520 eV (std 6 meV), shape rms 0.33 % WL, scale 0.95-1.02. Fig. 2b difference
spectra (Electrode2 vs 0.4 V, boxcar 5) reproduce at -0.6/-0.8/-1.0 V; -0.4 V differs by a
2.5 % edge-step difference (normalization, not energy).
Electrode2 = PtCCNPs_on_Au_*, Electrode3 = PtCCNPs_on_Au_3_*; Thom's picks are in the recipe.
Fig. 2b exploration (2026-11-11): the free Victoreen bg rose to 14 % of the step (5 pre-edge
points) -> bg_decreasing; then ours = model-free relative normalization (0.0016 rms). Remaining
differences vs Thom's published curves have three sources: 0 V = his near-edge post-edge excess
(per-spectrum Athena post-edge quadratic, windows +77..+101 eV; ~1 % post-edge offsets between his
spectra); -1.0 V = alignment convention: the doublet separation is 1.50 eV in that file vs 1.52-1.54
in the 0.4 V reference, so the midpoint vs a one-dip/shape alignment differs by ~10-15 meV (his
-1.0 V sits 14.4 meV further from the reference; others agree within 1.4 meV); -0.4 V = time
evolution in the 30 min hold (scans 1-4: min -0.12, shift +94 meV; 5-10: -0.03, +51 meV). Hand
outliers: 0 V scan 3 (+4 % intensity drift across the post-edge), -0.6 V scan 5 (bubble). Robust
metric: onset shift from scale+shift+broadening decomposition (both methods: +25, +68, +58, +110,
+114..128 meV at 0..-1.0 V; paper 0 -> -1.0 V: 0.1 eV). Doublet systematic: ~half the separation
change between files (~10 meV).

## BL15-2, May 2019, Hersbach Pt oxidation (Pt L3 HERFD, published; Thom's Athena reduction)
`recipes/pt_l3_hersbach_2019_05.yaml`; metadata `ISAAC_Metadata_...xlsx` (setup, conditions; no
curation notes). Columns: `mono` (no absev), DTC_FF1, `Seconds`. Mono calibrated on Pt foil
(11563.7 eV). I0 glitch = DOUBLET 11702.1 / 11703.5 eV, drifts ~0.65 eV over 43 h ->
`glitch_dips: 2`. Thom's per-scan shifts: `<file>_dir/<file>_calib_N.txt` (raw + one shift,
CR line endings); his Athena files: `AlignedAndNormalized/*.nor`, scans in the name (`_1-3_5`).
Same scans (80 spectra): energy offset Athena - ours +0.40 eV (reference convention), per-
spectrum spread 56 meV; shape rms diff 0.34 % of the white line (95 % 0.63 %); scale 0.94-1.04
(5-95 %). His alignment failed on ~18 scans (+0.7..+4.7 eV, -12.6 eV), mostly excluded from his
averages, not all (O7_06 scans 4-5). O5_16 Athena post window 140.9-150 eV (scale 1.50).
Metadata: minus sign dropped on negative potentials; O7_01 listed pH 2.

## BL15-2, Apr 2025, Sokaras IrOx acid/base + IrTiO2 (Ir L3 HERFD)
`recipes/ir_l3_sokaras_2025_04.yaml`; logbook `250411 BL 15 IrOx NP HERFD acid base.docx`.
- Mono: Pt foil between I1 and I2, alignment #128-130, reset to 11563.8.
- Glitch 11226.6 eV, sharp symmetric, second dip at 11230.75: inflection bimodal; shape fit
  biased ~35 meV by the reference file's grid -> `method: model` on 11224.4-11229.2.
  `energy` = absev - 2.3 eV.
- Filters 0/10/20/22/35: logbook found them consistent; filter 35 empties the HERFD pre-edge.
- IrO2 white line 11219.85 eV vs 11218.80 eV in 2021: +1.05 eV between beamtimes, unresolved.
- Logbook curation in the recipe notes (27, 35, 46, 47, 17, sample 6).

## BL15-2, Jun 2024, Cu K HERFD (Example2-XAS)
`recipes/cu_k_example2.yaml`. Cu foil between I1 and I2; ln(I0/I2). Mono very stable
(~10 meV between files). Spectra depend on the sample position (Sz): 8980 eV peak 0.62 vs 0.38;
averaged per position group; the legacy scan list mixed them. First scans at a fresh spot
evolve (dose).

## BL4-3, Jul 2025, Abebe TiON (Ti K fluorescence, Example3-XAS)
`recipes/ti_k_example3.yaml`. No in-scan reference (I1/I2 dark through the cell), no I0
glitch. Foil timeline 02 (after calibration) -> 33/34 next morning: +0.11 eV in 19 h.
Foil on I2 (31) distorted. No OCR column: no deadtime correction. Aborted scans (17, 21).

## BL4-3, Nov 2025, Marinescu MOF-Co (S K fluorescence)
`recipes/s_k_marinescu_2025_11.yaml`. Tender X-ray, no foil. I0 carries a 2.4 %, 1.8 eV wide dip at
2482.8 eV = the sulfate energy (S contamination upstream of I0, i.e. an in-line absorber): stable
2482.76-2482.87 eV over 2.5 days, used as the marker (method model, 2481.3-2484.3 eV). It is a dip on
an absorption step, so the fit is window-dependent: ~+-30 meV per scan. Absolute: Na2S2O3 (5 wt%)
first peak 2471.90 eV (convention 2472.02); undiluted elemental S 2472.5-2472.8 (self-absorption).
Two region files (XANES_HR to 2663 eV, EXAFS k9 to 2815 eV): min_coverage 0.6. File 05 dry spots
lose signal 2x per scan (flagged); file 07 (42 scans) white line -2 % after scan ~25; scans 10/20/30 (and weakly 40)
off by 90-140 meV (every 10th scan; 40 by 32 meV, kept). Normalization: fluorescence background
options (normalization.md): pre-edge falls steeply, post-edge IF/I0 rises with E (I0 ~ E^-3 -> F = (E/E_edge)^3).
Self-absorption: _avg_sac for the diluted standards only; elemental S fails the thick-limit check (not thick).
OPEN (ask beamline/user): I0 gas + length, path/windows I0->sample, sample/detector angles, MOF film
thickness and dry-MOF dilution. Spot checks 17-20 and calibration scan 00 (2467-2487 eV) left out.
