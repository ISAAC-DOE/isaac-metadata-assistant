# Local import: real-corpus coverage, 2026-10-28

Status: evidence. A one-off run of `isaac import` and `python -m isaac_api.local_import.extract` over the six real beamtime folders the project owner approved for this. **Counts only.** No file names beyond the six folder names, no sample names, no values. The full local report stays outside the repository.

Categories: *read by ISAAC* = a deterministic reader produced statements; *extractable for Claude* = the extractor produced text or images, or Claude Code's Read tool opens the file natively (PDF, image, plain text); *unreadable* = neither.

## Summary

| beamtime folder | files | runs | conflicts | unread | `isaac import` (exit, seconds) | unread: extractable / unreadable |
|---|---:|---:|---:|---:|---|---:|
| `BL15-2 2019-05` | 1345 | 274 | 394 | 7 | 0, 9.8 | 3 / 4 |
| `BL15-2 2021-11` | 1631 | 340 | 298 | 202 | 0, 14.7 | 188 / 14 |
| `BL15-2 2025-04` | 1139 | 94 | 280 | 36 | 0, 11.0 | 36 / 0 |
| `BL4-3 2025-07` | 389 | 54 | 0 | 9 | 0, 1.2 | 0 / 9 |
| `BL4-3 2025-11` | 430 | 61 | 0 | 4 | 0, 1.3 | 0 / 4 |
| `BL6-2c 2018-07` | 1465 | 570 | 430 | 69 | 0, 13.1 | 37 / 32 |

Totals over the six folders: 6399 files; 3815 read by ISAAC readers; 2260 extractable for Claude; 324 unreadable.

## `BL15-2 2019-05`

| extension | files | read by ISAAC readers | extractable for Claude | unreadable |
|---|---:|---:|---:|---:|
| `.txt` | 964 | 589 | 375 | 0 |
| `(none)` | 170 | 170 | 0 | 0 |
| `.nor` | 93 | 0 | 93 | 0 |
| `.mac` | 90 | 90 | 0 | 0 |
| `.mca` | 18 | 0 | 18 | 0 |
| `.prj` | 3 | 0 | 0 | 3 |
| `.py` | 2 | 2 | 0 | 0 |
| `.csv` | 2 | 0 | 2 | 0 |
| `.pxp` | 1 | 0 | 0 | 1 |
| `.xlsx` | 1 | 0 | 1 | 0 |
| `.xmu` | 1 | 0 | 1 | 0 |
| **all** | **1345** | **851** | **490** | **4** |

Embedded images: none.

## `BL15-2 2021-11`

| extension | files | read by ISAAC readers | extractable for Claude | unreadable |
|---|---:|---:|---:|---:|
| `.txt` | 982 | 982 | 0 | 0 |
| `.xlsx` | 186 | 0 | 186 | 0 |
| `.peak` | 179 | 0 | 179 | 0 |
| `(none)` | 164 | 164 | 0 | 0 |
| `.recon` | 35 | 0 | 35 | 0 |
| `.mac` | 25 | 25 | 0 | 0 |
| `.xmu` | 19 | 0 | 19 | 0 |
| `.prj` | 14 | 0 | 0 | 14 |
| `.nor` | 13 | 0 | 13 | 0 |
| `.pca` | 7 | 0 | 7 | 0 |
| `.dat` | 5 | 5 | 0 | 0 |
| `.png` | 2 | 0 | 2 | 0 |
| **all** | **1631** | **1176** | **441** | **14** |

Embedded images: none.

## `BL15-2 2025-04`

| extension | files | read by ISAAC readers | extractable for Claude | unreadable |
|---|---:|---:|---:|---:|
| `.dat` | 908 | 908 | 0 | 0 |
| `(none)` | 186 | 186 | 0 | 0 |
| `.txt` | 34 | 2 | 32 | 0 |
| `.mac` | 7 | 7 | 0 | 0 |
| `.mca` | 2 | 0 | 2 | 0 |
| `.docx` | 1 | 0 | 1 | 0 |
| `.pdf` | 1 | 0 | 1 | 0 |
| **all** | **1139** | **1103** | **36** | **0** |

Embedded images: 1 in 1 document(s) ({'docx': 1}).

## `BL4-3 2025-07`

| extension | files | read by ISAAC readers | extractable for Claude | unreadable |
|---|---:|---:|---:|---:|
| `.001` | 99 | 0 | 53 | 46 |
| `.002` | 42 | 0 | 21 | 21 |
| `.exp` | 34 | 0 | 34 | 0 |
| `.rgn` | 34 | 0 | 34 | 0 |
| `.txt` | 34 | 0 | 34 | 0 |
| `.det` | 34 | 0 | 34 | 0 |
| `.003` | 26 | 0 | 13 | 13 |
| `.004` | 22 | 0 | 11 | 11 |
| `.005` | 16 | 0 | 8 | 8 |
| `.006` | 10 | 0 | 5 | 5 |
| `.prj` | 7 | 0 | 0 | 7 |
| `.007` | 6 | 0 | 3 | 3 |
| `.008` | 6 | 0 | 3 | 3 |
| `.009` | 2 | 0 | 1 | 1 |
| `.010` | 2 | 0 | 1 | 1 |
| `.011` | 2 | 0 | 1 | 1 |
| `.012` | 2 | 0 | 1 | 1 |
| `.013` | 2 | 0 | 1 | 1 |
| `.014` | 2 | 0 | 1 | 1 |
| `.015` | 2 | 0 | 1 | 1 |
| `.016` | 2 | 0 | 1 | 1 |
| `.larix` | 2 | 0 | 0 | 2 |
| `.nor` | 1 | 0 | 1 | 0 |
| **all** | **389** | **0** | **262** | **127** |

Embedded images: none.

## `BL4-3 2025-11`

| extension | files | read by ISAAC readers | extractable for Claude | unreadable |
|---|---:|---:|---:|---:|
| `.001` | 122 | 0 | 61 | 61 |
| `.002` | 44 | 0 | 22 | 22 |
| `.exp` | 35 | 0 | 35 | 0 |
| `.rgn` | 35 | 0 | 35 | 0 |
| `.txt` | 35 | 0 | 35 | 0 |
| `.det` | 35 | 0 | 35 | 0 |
| `.003` | 22 | 0 | 11 | 11 |
| `.004` | 18 | 0 | 9 | 9 |
| `.005` | 6 | 0 | 3 | 3 |
| `.prj` | 4 | 0 | 0 | 4 |
| `.006` | 2 | 0 | 1 | 1 |
| `.007` | 2 | 0 | 1 | 1 |
| `.008` | 2 | 0 | 1 | 1 |
| `.009` | 2 | 0 | 1 | 1 |
| `.010` | 2 | 0 | 1 | 1 |
| `.011` | 2 | 0 | 1 | 1 |
| `.012` | 2 | 0 | 1 | 1 |
| `.013` | 2 | 0 | 1 | 1 |
| `.014` | 2 | 0 | 1 | 1 |
| `.015` | 2 | 0 | 1 | 1 |
| `.016` | 2 | 0 | 1 | 1 |
| `.017` | 2 | 0 | 1 | 1 |
| `.018` | 2 | 0 | 1 | 1 |
| `.019` | 2 | 0 | 1 | 1 |
| `.020` | 2 | 0 | 1 | 1 |
| `.021` | 2 | 0 | 1 | 1 |
| `.022` | 2 | 0 | 1 | 1 |
| `.023` | 2 | 0 | 1 | 1 |
| `.024` | 2 | 0 | 1 | 1 |
| `.025` | 2 | 0 | 1 | 1 |
| `.026` | 2 | 0 | 1 | 1 |
| `.027` | 2 | 0 | 1 | 1 |
| `.028` | 2 | 0 | 1 | 1 |
| `.029` | 2 | 0 | 1 | 1 |
| `.030` | 2 | 0 | 1 | 1 |
| `.031` | 2 | 0 | 1 | 1 |
| `.032` | 2 | 0 | 1 | 1 |
| `.033` | 2 | 0 | 1 | 1 |
| `.034` | 2 | 0 | 1 | 1 |
| `.035` | 2 | 0 | 1 | 1 |
| `.036` | 2 | 0 | 1 | 1 |
| `.037` | 2 | 0 | 1 | 1 |
| `.038` | 2 | 0 | 1 | 1 |
| `.039` | 2 | 0 | 1 | 1 |
| `.040` | 2 | 0 | 1 | 1 |
| `.041` | 2 | 0 | 1 | 1 |
| `.042` | 2 | 0 | 1 | 1 |
| **all** | **430** | **0** | **283** | **147** |

Embedded images: none.

## `BL6-2c 2018-07`

| extension | files | read by ISAAC readers | extractable for Claude | unreadable |
|---|---:|---:|---:|---:|
| `.txt` | 758 | 446 | 312 | 0 |
| `.nor` | 168 | 0 | 168 | 0 |
| `(none)` | 148 | 148 | 0 | 0 |
| `.xmu` | 116 | 0 | 116 | 0 |
| `.dat` | 81 | 81 | 0 | 0 |
| `.peak` | 62 | 0 | 62 | 0 |
| `.nder` | 48 | 0 | 48 | 0 |
| `.xlsx` | 37 | 0 | 37 | 0 |
| `.prj` | 30 | 0 | 0 | 30 |
| `.mac` | 10 | 10 | 0 | 0 |
| `.mca` | 5 | 0 | 5 | 0 |
| `.zip` | 2 | 0 | 0 | 2 |
| **all** | **1465** | **685** | **748** | **32** |

Embedded images: none.

## Top-level documents (one each of docx, pptx, pdf, xlsx)

| kind | status | embedded images |
|---|---|---:|
| pptx | extracted | 3 |
| docx | extracted | 3 |
| pdf | read_with_claude | 0 |
| xlsx | extracted | 0 |

## What the run found

- **Every beamtime imports with exit 0.** The import used to refuse the BL6-2c beamtime with exit 5. Two acquisition files with the same name in different sub-folders collided on one run id; that is fixed, and BL6-2c now imports 570 runs, 430 conflicts and 69 unread files in 13.1 s. Later, the BL15-2 2025-04 import was refused by the stricter provenance check: 96 values the engine derived carried no recorded derivation step. The importer now records those steps, so that is fixed too. Final re-import on 2026-10-28, all exit 0 (runs / candidates / conflicts / unread files):
  - BL15-2 2019-05: 274 / 1,780 / 394 / 7
  - BL15-2 2021-11: 340 / 1,869 / 298 / 202
  - BL15-2 2025-04: 128 / 2,329 / 285 / 2
  - BL4-3 2025-07: 54 / 0 / 0 / 9
  - BL4-3 2025-11: 61 / 0 / 0 / 4
  - BL6-2c 2018-07: 570 / 2,113 / 430 / 69
  Counts only.
- **Both BL4-3 beamtimes produce 0 runs.** No deterministic reader exists for their file types (numbered `.001`-`.009` scans, `.exp`, `.rgn`, `.det`, `.txt`), so every file is unread. The extractor makes the plain-text ones readable by Claude; the rest fail the two text tests (a NUL byte, or not UTF-8) and are reported unreadable, not guessed.
- **On the BL1-5.2 and BL6-2c beamtimes the unread files are mostly derived-analysis files and spreadsheets**; every spreadsheet extracted, and nearly all the analysis files are plain text Claude can read directly. **Embedded images are rare**: the only documents carrying any are the top-level Word and PowerPoint files and one Word document inside a beamtime folder.
- Bounds are visible: the counts of preview lines, preview rows, characters and parts not returned are in each manifest's `truncation` block (the local report sums them per beamtime).

The extractor and its limits: `apps/api/isaac_api/local_import/extract.py`; tests `apps/api/tests/test_local_import_extract.py`.


## Generic readers (LOCAL-R2): `collect_all_generic`, 2026-10-28

Precedence (fixed): `ssrl_xdc`, `xdi`, `mca`, `xes_tab`, `two_column`. Files the BL15 readers already read are passed as `skip` and never claimed; each remaining file is claimed by at most one reader. Counts only.

| beamtime | files | read by ISAAC (BL15 readers) | `ssrl_xdc` | `xdi` | `mca` | `xes_tab` | `two_column` | claimed by generic readers | remaining | remaining: extractable for Claude | remaining: unreadable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `BL15-2 2019-05` | 1345 | 851 | 0 | 94 | 18 | 375 | 0 | 487 | 7 | 3 | 4 |
| `BL15-2 2021-11` | 1631 | 1176 | 0 | 253 | 0 | 0 | 0 | 253 | 202 | 188 | 14 |
| `BL15-2 2025-04` | 1139 | 1103 | 0 | 0 | 2 | 0 | 32 | 34 | 2 | 2 | 0 |
| `BL4-3 2025-07` | 389 | 0 | 379 | 1 | 0 | 0 | 0 | 380 | 9 | 0 | 9 |
| `BL4-3 2025-11` | 430 | 0 | 426 | 0 | 0 | 0 | 0 | 426 | 4 | 0 | 4 |
| `BL6-2c 2018-07` | 1465 | 685 | 0 | 395 | 5 | 311 | 0 | 711 | 69 | 37 | 32 |
| **all six** | **6399** | **3815** | 805 | 743 | 25 | 686 | 32 | **2291** | **293** | **230** | **63** |

Before the generic readers, 2584 of 6399 files were not read by ISAAC. 2291 of those are now parsed by a reader; 293 remain (230 readable by Claude through the extractor or its Read tool, 63 unreadable: gzip Athena project files, an Igor binary, two zip archives).

| beamtime | runs by reader | scans/files parsed | anomaly flags (count by kind) | notes (count by kind) | unparsed | refused |
|---|---|---:|---|---|---:|---:|
| `BL15-2 2019-05` | {'xdi_reader_v1': 94, 'mca_reader_v1': 18, 'xes_tab_reader_v1': 70} | 487 | {'declared_columns_differ': 10} | {'declared_column_numbers_not_contiguous': 10} | 0 | 0 |
| `BL15-2 2021-11` | {'xdi_reader_v1': 253} | 253 | {'column_count_mismatch': 21} | none | 0 | 0 |
| `BL15-2 2025-04` | {'mca_reader_v1': 2, 'two_column_reader_v1': 32} | 34 | none | {'no_header': 32} | 0 | 0 |
| `BL4-3 2025-07` | {'ssrl_xdc_reader_v1': 53, 'xdi_reader_v1': 1} | 126 | none | {'duplicate_column_names': 124} | 0 | 0 |
| `BL4-3 2025-11` | {'ssrl_xdc_reader_v1': 61} | 143 | none | {'duplicate_column_names': 142} | 0 | 0 |
| `BL6-2c 2018-07` | {'xdi_reader_v1': 347, 'mca_reader_v1': 5, 'xes_tab_reader_v1': 62} | 711 | {'declared_columns_differ': 194, 'column_count_mismatch': 24} | {'declared_column_numbers_not_contiguous': 103} | 0 | 0 |

Flags are factual disagreements inside the files, left as found: in the Athena/Demeter exports the declared `Column.N` entries disagree with the column-header line or the row width. No reader found a non-numeric cell, a points mismatch or a non-monotonic grid in this corpus.

`ssrl_xdc` claims include each run's companion files (region, detector, experiment, other context and the binary originals), which are attached as context and not parsed.


## Correction, 2026-10-28 (later the same day): the scientists' processed files are not runs

The run counts above (274 / 340 / 128 / 54 / 61 / 570) are **too high**. They counted every
Athena/Demeter XDI file (`.nor`, `.xmu`, `.peak`, `.recon`, `.pca`, `.nder`) as an
acquisition run, so grouping proposed record groups made of the scientists' own processed
files. Fixed in `e8c21ad1` (bundle format 1.2.0): a file whose line 1 names Athena or
Demeter is a **processed output** (a reference result, never a record), stored in
`processed_outputs[]`. The tables above are kept as they were measured, because "the XDI
reader claimed 743 files" is still true; what was wrong is treating those files as runs.

Re-measured at `fa8a82f5`, after two further fixes the same day: a leading file-name number
is no longer assumed to be a run counter (it had merged pairs of ELECTRODES into one record,
24 of 25 multi-run groups on one beamtime), and groups no XAS protocol covers are reported
as "not applicable", not as QC failures. All six import, group, process and `bundle check`
exit 0, VALID at 1.2.0. Counts only.

| beamtime | runs | processed outputs | record groups | multi-run groups | merge candidates | multi-run groups mixing leading numbers | processing: not applicable | QC pass / warn / fail |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `BL15-2 2019-05` | 180 | 94 | 180 | 0 | 13 | 0 | 102 | 20 / 57 / 1 |
| `BL15-2 2021-11` | 87 | 253 | 83 | 4 | 25 | 0 | 1 | 15 / 65 / 2 |
| `BL15-2 2025-04` | 128 | 0 | 128 | 0 | 2 | 0 | 36 | 9 / 81 / 2 |
| `BL4-3 2025-07` | 53 | 1 | 53 | 0 | 3 | 0 | 0 | 2 / 48 / 3 |
| `BL4-3 2025-11` | 61 | 0 | 61 | 0 | 3 | 0 | 0 | 5 / 49 / 7 |
| `BL6-2c 2018-07` | 223 | 347 | 194 | 28 | 6 | 0 | 121 | 28 / 44 / 1 |

Counter questions (one answer each settles them): 2019-05 position 2 (11 merge candidates);
2021-11 positions 1 and 2 (25 and 1); 2025-04 position 1 (1); BL6-2c positions 4 and 5.

**Processing against the scientists' own Athena projects**, counted ONCE per group (from
ISAAC's result; the same comparison is also stored on the scientist's Athena result):
**81 groups compared, 19 agree** at ISAAC's default normalization; median RMS of normalized
mu **0.078** at defaults and **0.0106** when ISAAC's merge is normalized with the scientist's
own Athena parameters; median |dE0| **0.62 eV**. Flags: normalized shape differs 59, E0
differs 18, edge-step scale differs 14, scientist used a subset of the scans 9. Separating
the electrodes raised the compared groups on 2021-11 from 26 to 70: each electrode now
matches the scientists' own per-electrode Athena group, which independently supports that
fix. The conclusion is unchanged: data, channel and merge agree; ISAAC's default
normalization and E0 choices differ from the scientists', a protocol-review item for Oscar
and Angel, not something ISAAC overrides.

~~74 groups compared, 6 agree, RMS 0.117 -> 0.0195~~ (stated above in an earlier revision
of this section at `e8c21ad1`): **double-counted**, because each comparison is stored on both
results. At that build it was 37 groups, 3 agree, the same medians.

**2019 grouping:** 0 multi-run groups. 11 merge candidates wait on one scientist answer (is
file-name position 2 a counter?); in that naming scheme position 2 may be a sequence, in which
case the runs are correctly separate.

## Maximum-inference pilot, 2026-10-28: what a scientist is shown per key field

This section records counts only. The real files and the findings stay outside the repository.
The owner approved Claude reading the real archive (DEC-86).

**Measure.** For every live record group, 11 key fields were checked: sample name, sample
number, potential, potential reference, electrolyte/reaction, environment, acquisition time,
technique, element/edge, producer and facility. Each (group, field) cell is put in one class:
- `answered`: a scientist decision covers it;
- `from files`: a parser or stored rule read it;
- `AI suggestion`: a cited Claude reading suggests it;
- `hint only`: a text hint such as the folder name;
- `missing`: nothing.

Nothing in the AI-suggestion class is a value: each one is `needs_review`, cited to a file,
locator and verbatim quote, and waits for a scientist's decision.

**Corpus build.** Six beamtimes were rebuilt with the pilot code. Every import, group, process
and questions step exited 0. Runs and groups are unchanged from the previous build.

| Beamtime | Cells | Missing before | Missing after | AI suggestions | Findings placed |
|---|---:|---:|---:|---:|---:|
| BL15-2 2021-11 | 913 | 48.3% | **13.5%** | 34.7% | 19 of 19 (563 targets) |
| BL15-2 2025-04 | 1,408 | 40.1% | **10.5%** | 29.3% | 40 of 40 (1,556 targets) |

The 2021-11 reading pass produced 19 findings, 6 stated and 13 inferred. The 2025-04 pass
produced 40. Both bundles still check VALID (1.2.0).

**What is still missing, and why:**
- The 2021-11 potential reference: no file states it. The spreadsheets give bare volts.
- Sample numbers and potentials for reference-compound and blank runs: they have none.
- Facility endstation and site: not stated anywhere.

**Shared documents.** The top-level proposal, slides and narrative gave 9 findings, all
marked `beamtime: unclear`. None names a beamtime's date, sample or beamline. They were applied
to no bundle: a finding is never assigned to a beamtime by guess.

**Readability.**
- Unread files fell from 293 to 288 of 6,461. The nested ZIP, Larch and Igor readers read the
  last five files that had no reader: 2 nested ZIPs (62 members), 2 `.larix` and 1 `.pxp`.
- Every remaining unread file is a kind Claude reads directly: `.xlsx` 224, Athena `.prj` 58
  (read by processing), `.csv` 2, `.png` 2, `.docx` 1, `.pdf` 1.

**Contradictions surfaced, not resolved:**
- The 2025-04 notes state one electrolyte for every experiment, while two of their own procedures name others.
- A parser cell-type candidate in 2025-04 comes from a sentence about where TEM grids are kept.

Both are left for the scientist.
