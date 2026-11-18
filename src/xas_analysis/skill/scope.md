xas-analysis scope (2026-11)

VALIDATED (reproduces an independent reduction)
  BL15-2 Ir L3 HERFD, SPEC files, I0-glitch calibration
    - reduce_xas_v2 parity on Example1 (19 spectra; MATLAB shifts to 1e-5 eV)
    - mback_v4 model bit-identical to MATLAB (its A_edge is unidentified: not a default)
    - Victoreen + McMaster vs Athena, same scans, 72 spectra: shape residual <0.43 % of the
      white line, scale 0.99-1.13 (edge-jump convention + loading)

WORKING, EXPLORATORY (internally cross-checked, no independent reference yet)
  BL15-2 Cu K HERFD, in-scan foil (ln(I0/I2)), shape-fit anchors (legacy applied no shift)
  BL4-3 Ti K fluorescence, SSRL EXAFS Data Collector files, foil timeline (separate foil scans)
  BL15-2 Ir L3 Apr-2025 beamtime (glitch at 11226.6 eV), logbook curation
  BL8-2 soft XAS engine (soft_pvii, Pearson-VII + FEFF mu0): 8 MATLAB goldens

NOT SUPPORTED (say so; do not improvise)
  transmission-mode samples (sample mu from ln(I0/I1)); the pipeline reduces IF/I0
  EXAFS / chi(k); self-absorption correction; deadtime correction for XDC files (no OCR column)
  per-channel selection of multi-element detectors (all SCA windows are summed)
  absolute energy across beamtimes (2021 vs 2025 Ir L3: IrO2 white line differs by 1.05 eV;
    align on a shared standard by hand and say so)
  live / quick-view during acquisition
