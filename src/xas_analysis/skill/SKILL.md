---
name: xas-analysis
description: Reduce hard X-ray absorption spectra (fluorescence / HERFD XANES) from SSRL beamlines with the xas-analysis package — survey a beamtime folder, pick the energy reference (I0 glitch, in-scan foil, foil timeline) and its anchor method, align, screen, average and normalize (Victoreen + McMaster). Validated on BL15-2 Ir L3 HERFD (SPEC); working on BL15-2 Cu K and BL4-3 Ti K (EXAFS Data Collector files). Also the BL8-2 soft-XAS engine. This is the absorption (MBACK-lineage) skill, NOT xrs-analysis.
---

# XAS reduction skill

Status (2026-11): hard-XAS pipeline ported from the MATLAB `reduce_xas_v2` + `mback_v4`
lineage at parity (`docs/PORT_STATUS.md`), then extended. `xas-analysis scope` says what is
validated, what is working but exploratory, and what is not supported. Check it before
promising a reduction.

The skill ships inside the package: `xas-analysis skill path` prints where;
`xas-analysis skill install [--link]` puts it in `~/.claude/skills/xas-analysis`.

## Rules
- Reduce only through the package (`xas-analysis` CLI or the `xas_analysis` API). Never
  re-implement alignment, averaging or normalization in an ad hoc script; analysis and
  figure scripts read the package outputs.
- Every choice lives in a recipe (YAML). Curation (dropped scans, flags, why) goes in the
  recipe as `scans` / `outliers` / `note`, with the logbook reason.
- Never write into raw-data folders; never work on OneDrive copies (on-demand files stall):
  copy the beamtime to local disk first.
- Report every warning (survey warnings, screening drops, normalize failures). Never hide one.
- Keep the user's hand-picks. Automatic screening complements them; when it disagrees
  with a logbook note, show both and ask.

## New reduction
1. **Survey**: `xas-analysis survey <folder> --json survey.json`. It reports edge, fluorescence
   channel, `energy`-vs-`absev` offset, foil edges, I0 glitches, `mono reset` lines and foil
   scans, and recommends a calibration with reasons. Read `references/calibration.md` and
   tell the user which energy reference applies and why.
2. **Read the documents** the survey lists (logbook .docx/.txt, readme). Logbook tables
   (`File Number | Notes`) carry the curation: "discard first scan", "start from scan #5",
   "potentiostat went to 2.5 V", "sample bad". Extract the .docx tables with zipfile + XML
   (python-docx may be absent).
3. **Draft**: `xas-analysis recipe init <folder> -o recipe.yaml`. Then review: roles, the
   reference sample, the calibration block, normalization windows; add the logbook curation
   as `scans`/`outliers`/`note`. Check with `xas-analysis recipe show recipe.yaml`.
4. **Reduce**: `xas-analysis reduce recipe.yaml`. Outputs per sample: `<name>_avg_raw`
   [E, IF/I0, err, sec], `<name>_avg_nrm` [E, norm, McMaster mu], `reduce_diag.json`
   (anchors, shifts, kept scans, A_edge).
5. **Inspect** before interpreting: per-scan glitch/foil alignment and the fit of one sample
   (`examples/show_alignment_and_fit.py`), all spectra per series, edge jump vs time.
   Look for: anchor scatter (> 30 meV is suspicious with the shape fit), first scans after a
   potential step still evolving, edge jump falling within a file (material loss: shape can
   stay constant), spot dependence (sample position motors), aborted scans.
6. Report: calibration mode + evidence, scans dropped and why, flags, normalization
   convention and its uncertainty (`references/normalization.md`).

## Order of operations (do not change it)
Per scan: anchor -> shift (reference anchor - scan anchor) -> one interpolation onto the
reference grid. Then screen, average IF/I0 over kept scans, normalize the AVERAGE once.
Averaging raw IF/I0 then normalizing = averaging normalized scans weighted by their edge
jump; fine while the shape is stable within the file. If the shape evolves within a file,
split it (scan lists) instead of averaging.

## Comparing with legacy MATLAB / Athena
- Legacy `energy_calibration_xas_glitch.m` and `energy_calibration_xas_wref.m` apply NO shift
  (double interp1 cancels). Legacy outputs are on the unshifted mono axis.
- Use the same scans as the other reduction before comparing (Athena encodes its picks in
  column names, e.g. `_6-8`). Differences then reduce to one scale factor per spectrum.
- Victoreen vs Athena (same scans, Ir L3 2021): shape agrees to <0.5 % of the white line. With the
  constrained background (default) the normalized level is ours/Athena 0.975 (0.93-1.05) with no
  loading trend; the old free Victoreen gave 1.00 at full loading rising to 1.13 at ~1 % loading.
  The ~2.5 % offset is the convention: our post-edge follows McMaster, Athena's is flattened to 1.
- Difference spectra: check with `xas_analysis.diffspec` (model-free relative difference and the
  scale / onset-shift / broadening decomposition; the shift is the method-robust quantity).

## References
- `references/calibration.md`: energy reference decision guide, per mode, with the traps
- `references/normalization.md`: Victoreen + McMaster model, windows, edge-jump uncertainty
- `references/recipe.md`: recipe fields
- `references/gotchas.md`: per-beamtime findings (BL15-2 2019/2021/2025, BL4-3 2025, Cu K 2024)
