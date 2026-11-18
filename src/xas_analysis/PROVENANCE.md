# Provenance of the vendored `xas_analysis` package

| | |
|---|---|
| Package | `xas-analysis` (repository `xas-reduction`), by Oscar (SLAC/SSRL) |
| Version | `0.1.0.dev0` (`pyproject.toml` / `__init__.__version__` of the source) |
| Source | `xas-reduction-main.zip`, as Oscar shared it |
| Source sha256 | `4a667f881081a0923163421cf70b8c1cf239e39e00add0f58940e6809d515d2c` (`shasum -a 256 xas-reduction-main.zip`) |
| Vendored | 2026-11-17, into `src/xas_analysis/` of `ISAAC-DOE/isaac-metadata-assistant` |
| Used by | `apps/api/isaac_api/local_import/processing/engine_xas.py` (processing protocol `isaac.xas.v1`) |

## Permission and licence

The source zip has NO licence file. This copy is used under the authors' permission: the package author (Oscar) and
the ISAAC project scientist (Angel) gave permission to use and vendor this source in the ISAAC metadata assistant,
relayed by the project owner (Krish) on 17 Nov 2026. It carries no other licence grant.

## What was vendored, and what was not

Vendored: `src/xas_analysis/` as in the zip (code, `data/element.json` = the McMaster tables of `element.mat`,
`data/S0_graphite_q0.10.dat` = a FEFF10 computed graphite reference used by the soft-XAS engine, and the package's own
skill documentation `skill/SKILL.md`, `skill/scope.md`, `skill/references/calibration.md`, `normalization.md`,
`recipe.md`, kept as documentation of the engine), then the local modifications below. Unit tests that need no data file: `tests/xas_analysis/test_xas_*.py` (from the
zip's `tests/`, renamed with a `test_xas_` prefix; `test_xas_models.py` without its data-file tests).

NOT vendored: `tests/data/` (real spectra: BL4-3 Ti K averages, soft-XAS inputs and deliverables), `tests/test_parity.py`
(needs the MATLAB golden outputs), `recipes/` (real sample names and logbook notes), `skill/references/gotchas.md`
(per-beamtime notes naming people, samples and files; its general lessons are restated without names in ISAAC's
`docs/xas-processing-protocol-v0.md`, "Energy-reference lessons"), `reference/` (the MATLAB sources
and scripts), `examples/`, `docs/` (`PORT_STATUS.md` and the plan are summarised in `skill/` and below), the
package's `pyproject.toml` / `README.md` (its dependencies are in the repository's `processing` extra).

`model/athena_norm.py` and `model/self_absorption.py` are vendored with the package but never called by ISAAC:
the beamline scientists' rules (17 Nov 2026) are never Athena, and no dead-time or over-absorption correction.

## Local modifications (keep this list current; each has a test)

- **M1 report-only screening and pooled scans** (`pipeline.py`, `average.py`). `screen_report(out, cfg)` runs the
  same screen as `screen_scans` but changes nothing on the scans and returns every flag with its evidence (`test`,
  `reason`, `value`, `median`, `threshold`), so ISAAC's documented rule (`isaac.xas.scan_decision.v1`) decides.
  `screen_scans` is now `screen_report` + apply, with identical results. `AlignedScan.key` (and `.ident`) tells apart
  scans of several files pooled into one sample (spots, repeats), whose scan numbers repeat: `_apply` deduplicated by
  scan number, so pooled scan 1 of file B was silently not reported after scan 1 of file A.
  Tests: `test_xas_isaac_modifications.py::test_screen_report_is_report_only`, `::test_pooled_scans_keep_their_identity`.
- **M2 survey of already-read, pooled files** (`survey.py`). `survey(folder)` is now `collect(folder)` +
  `survey_files(files, docs, folder)`; `survey_files` surveys FileInfo objects a caller built, one per sample, each
  pooling the scans of several SPEC files. `FileInfo.role` (optional) lets a caller that knows the role (a record
  group's sample / reference / alignment / foil) override the name guess.
  Test: `::test_survey_files_on_pooled_groups`.
- **M3 transmission samples are detected** (`survey.py measurement_mode`, `pipeline.py sample_mode`, `reduce`).
  `scope.md` lists transmission-mode samples as NOT SUPPORTED, yet `reduce` read a transmission file's IF column as
  the measurement (a reference pellet named `..._transmission` in a real BL15-2 beamtime was reduced as HERFD).
  `measurement_mode` decides
  from the fluorescence edge contrast, the ln(I0/I1) step (I1 lit) and the name; `reduce` now skips such a sample
  with a warning (`results["skipped_samples"]`, `reduce_diag.json`), unless the recipe sample says
  `mode: fluorescence`. ISAAC hands such groups to its own `isaac.xas.v0`.
  Tests: `::test_measurement_mode_detects_transmission`, `::test_reduce_skips_a_transmission_sample`.
- **M4 `pipeline.tabulated_edge_eV`** (new helper): the McMaster table's K / L1-L3 edge in eV, used by M3.
- **M6 documentation sanitised** (no code change): `skill/SKILL.md` (no named sync service, no `gotchas.md`
  entry), `skill/scope.md` (no beamtime or dataset names), `skill/references/calibration.md` (no named colleague),
  `skill/references/recipe.md` and the `pipeline.py` docstring (`<data root>` for the author's local folder).
- **M5 an undated alignment scan no longer crashes the survey** (`survey.py`): the edge-scan finding formatted
  `s.time` with `%m-%d`, a `TypeError` for a scan without a `#D` date. Test: `::test_survey_undated_alignment_scan`.
