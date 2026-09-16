# BL15-2 corpus characterization — measured 2026-09-16

**What this is.** The project owner supplied a real SSRL BL15-2 beamtime archive on
2026-09-16. `ISAAC_EXECUTION_LEDGER.md` had recorded `EXT-10` — *"there is no
representative BL15-2 corpus"* — as the gate on `HIST-002`, `BL15-001`, `HIST-003b`
and `HIST-006`. **This document is the measurement that retires that gate for the
formats the archive contains, and for nothing else.**

**The corpus is NOT in this repository and must never be committed** (`CLAUDE.md` §6:
real experimental artifacts and real human notes). It was read from a local folder the
owner pointed at. Everything below is a count, a structure, or a sanitized excerpt;
**no scientific value, sample identity, or note text is reproduced here** beyond the
filenames the owner already quoted in the authorizing brief.

## 1. Inventory

Measured with `find`, `os.walk` and `hashlib` over the extracted folder.

| Quantity | Value |
|---|---:|
| files | **1,192** |
| directories | **96** (95 top-level + `MERGE`) |
| uncompressed size | **88 MB** |
| `.dat` (scan exports) | **908** |
| extensionless | **187** |
| `.mac` | **59** |
| `.txt` | **34** |
| `.mca` | **2** |
| `.docx` / `.pdf` | 1 / 1 |

Top level: **158 files**, **95 directories** (94 `*_dir`, plus `MERGE`).

| Top-level category | Count |
|---|---:|
| numbered extensionless acquisition files (`^\d+_`) | **92** |
| `*_dir` scan directories | **94** |
| `_dir` with a matching root acquisition file | **94** (zero orphans) |
| macros (`.mac`) | **59** |
| extensionless non-numbered | **3** — `alignment`, `run29`, `IrO2_5wpc_pellet_transmission` |

## 2. Findings that decide the architecture

**2.1 — The extension does not classify the file.** `run29` has no extension and is a
**macro** (its first line is `qdo Ir_XAS.mac`). `alignment` has no extension and is a
**SPEC acquisition** (`#F alignment`). `IrO2_5wpc_pellet_transmission` has no extension
and is a SPEC acquisition of a reference pellet. Classification must be content-led.

**2.2 — One `.mac` is not one measurement, and the spread is wide.** 156 `newfile`
declarations across 60 macro files (59 `.mac` + `run29`): **29 macros declare more than
one**, the maximum is **8** (`run15.mac`), and **4 declare none at all** — `Ir_XAS.mac`
(the acquisition-method definition, `def IrL3_xas`), `trigger.mac`, and
`motors_cpy_pre77.mac` / `motors_cpy_pre112.mac` (motor snapshots). Mapping one macro to
one Run would have produced 60 Runs for 95 declared measurements and would have made four
non-measurements into measurements.

**2.3 — One `.dat` is not one measurement.** 908 `.dat` files live inside the 94 `_dir`
directories, **0 to 233 per directory**. Two `_dir`s are **empty**
(`01_IrO2_oldPellet_f35_dir`, `02_IrO2_oldPellet_f35_newGrid_dir`) — so a measurement can
exist with zero scan children, and "has scans" cannot be a precondition for a candidate.

**2.4 — Every `_dir` also contains a byte-identical copy of its root acquisition file.**
92 extensionless entries inside `_dir` directories; 96 duplicate-content groups covering
193 files. Deduplication must be by **content hash**, and the copy must not be counted as
a second source of corroboration.

**2.5 — Macro intent and acquired files disagree, 9 times in each direction.** 95 distinct
`newfile` targets; **9 targets have no acquisition file** and **9 acquisitions have no
macro target**. The two sets are not independent — the `29`–`32` and `44`–`46` families
are the same measurements under different names:

| macro declared | acquired |
|---|---|
| `29_03_JK2_base_beforeCycling_filter20_060mV` | `29_03_JK2_base_after1500Cycling_filter20_060mV` |
| `30_03_JK2_base_after1400Cycling_filter20_850mV` | `30_03_JK2_base_after1500Cycling_filter20_850mV` |
| `44_04_JK2_base_after1500Cycling_filter20_1500mV` | `44_04_JK2_base_after1500Cycling_filter35_newSpots_1200mV` |

**This is a conflict, not a defect to repair.** Both must survive.

**2.6 — The duplicate legacy number `32` is real, and one half also disagrees with
itself.** Two distinct acquisition files carry legacy number 32:

- `32_03_JK2_base_after1400Cycling_filter20_1500mV` — internal `#F` **agrees** with its
  external name; `#E 1744501604` (Sat Apr 12 16:46:44 2025).
- `32_03_JK2_base_after1500Cycling_filter20_1500mV` — internal `#F` reads
  **`32_03_JK2_base_beforeCycling_filter20_1500mV`**; `#E 1744500067` (16:21:07 2025).

So the external name says `after1500Cycling`, the internal declaration says
`beforeCycling`, and a sibling file says `after1400Cycling`. Three readings, one legacy
number. Neither file may be overwritten and none of the three may be silently chosen.

**2.6a — CORRECTED 2026-09-16, same day: the internal-`#F` disagreement is FOUR files,
not one, and that changes what it means.** §2.6 was written from the one example the
authorizing brief named, and reads as though a single file disagrees with itself.
Measured over all 94 SPEC acquisitions by comparing each `#F` against its own filename:

| file | its own `#F` says |
|---|---|
| `29_03_JK2_base_after1500Cycling_filter20_060mV` | `29_03_JK2_base_beforeCycling_filter20_060mV` |
| `30_03_JK2_base_after1500Cycling_filter20_850mV` | `30_03_JK2_base_beforeCycling_filter20_850mV` |
| `31_03_JK2_base_after1500Cycling_filter20_1200mV` | `31_03_JK2_base_beforeCycling_filter20_1200mV` |
| `32_03_JK2_base_after1500Cycling_filter20_1500mV` | `32_03_JK2_base_beforeCycling_filter20_1500mV` |

**Four consecutive files, one sample group, the same substitution every time** —
`beforeCycling` internally, `after1500Cycling` externally. A single file disagreeing
with itself looks like a typo; four consecutive files agreeing with each other and
disagreeing with their names is a **systematic rename after acquisition**, which is a
different finding and a stronger one. It also lines up exactly with §2.5's
"declared, never acquired" list, which contains `29_03_..._beforeCycling_...`,
`30_..._after1400Cycling_...` and `31_..._after1400Cycling_...`: the macro, the internal
declaration and the filename are **three** sources and at least two of them disagree
for this group.

**Consequence for the reconstruction:** conflict detection must run over every
acquisition rather than being seeded with a known case, and the surface must be able to
show a THREE-way disagreement, not just two. It also means a plausible-sounding
"trust the internal `#F`, it is closer to the instrument" rule would be wrong for these
four — the rename is likelier to be the scientist's correction than the header is.

**2.7 — `ffilter35` is real.** `46_04_JK2_base_after1500Cycling_ffilter35_newSpots_1600mV`.

**2.8 — The candidate-unit arithmetic, measured, because it is what the reconstruction
must reproduce.** Classification content-led (first line begins `#F`):

| quantity | value |
|---|---:|
| SPEC acquisitions — **the candidate measurement units** | **94** |
| of which numbered `^\d+_` | 92 |
| of which unnumbered | 2 — `alignment`, `IrO2_5wpc_pellet_transmission` |
| extensionless files that are **macros**, not acquisitions | 1 — `run29` |
| distinct legacy numbers | **91**, range 1–91, **no gaps** |
| legacy numbers carried by more than one file | **1** — number 32 |
| sample/electrode groups (second numeric token) | **10** |
| scan children over all 94 | **908**, max 233 in one, **2 with zero** |
| `MERGE/` entries | 34 — 27 leading with a number, 7 without |

Group sizes, which are what a review surface groups by: token `01` 8 measurements
(legacy 3–10), `02` 12 (11–22), `03` 13 (23–34), `04` 13 (35–47), `05` 12 (48–59),
`06` 11 (60–70), `07` 12 (71–82), `08` 5 (83–87), `09` 4 (88–91), and 2 measurements
with no group token at all (legacy 1–2, the old pellets — which are also the two with
zero scan children).

**The ranges are contiguous and non-overlapping**, which is independent corroboration of
the beamtime notes' own `Sample N … File Number` sections. **Corroboration is not proof**:
the second token could mean something else and still produce contiguous ranges, which is
why "does the second token always mean the sample/electrode instance" is the first
question in the domain packet rather than an assumption in the parser.

## 3. Formats, as they actually are

**3.1 — The root acquisition files are SPEC text with SEPARATED name and position
blocks.** `#F` `#E` `#D` `#C`, then `#O0`–`#O21` (22 lines of whitespace-column motor
NAMES, ~180 motors), then per-scan `#S` `#D` `#T` `#G*` `#Q` `#P0`–`#P21` (positions, in
the same order), `#N` (column count), `#L` (whitespace-separated column names), then the
data rows. **The `#O`/`#P` blocks must be paired by index and zipped by position** — the
names are in `#O`, the values in `#P`, and nothing in a `#P` line names its motor.

**3.2 — The `.dat` scan exports carry `name=value` positions instead.** Same `#S`/`#D`/
`#T`/`#N`/`#L` header, but `#P0 dummy0=4 energy=11164.999 emiss=9175.4 filter=10 Sx=...`
— already keyed, no `#O` block, no `#F`. So the two readers are genuinely different and
the `.dat` reader is the simpler of the two. Useful motors observed: `energy`, `emiss`
(emission energy, e.g. `9175.4`), `filter`, `Sx`/`Sy`/`Sz`/`Sr` (sample position).

**3.3 — `Ir_XAS.mac` defines the acquisition method**, not a measurement:
`def IrL3_xas '{ ... }'`, with the energy grid as a literal
(`XAS_MAIN_GRID = "11165 11195 5 11205 1 ... 11500 5"`) and a documented four-argument
call signature `IrL3_xas cntSec nbrScan emission nbrFilter`. The `run*.mac` files call it:
`IrL3_xas 0.5 2 9175.4 10` is *0.5 s/point, 2 scans, 9175.4 eV emission, filter 10*.
Other commands observed: `qdo` (include), `mv` / `mvr` (absolute / relative motor move),
`newfile`, `trigger`. **Nothing is ever executed; a macro is read as text.**

**3.4 — `MERGE/` holds processed products, 34 entries**: 32 `.txt` two-column
`energy value` spectra and 2 `.mca`. Their names are RE-SPELLED (`f10` where the
acquisition says `filter10`, `43_44_04_...` naming two legacy numbers in one file,
`ave_JK2_filter10_1600mv` naming no legacy number at all). A `MERGE` entry is a
**candidate processed artifact**; nothing here makes it ISAAC's official reduced spectrum.

**3.5 — `readme.txt` is beamtime-scope shared context** (13 lines): element `Ir`, beamsize
at 11215 eV, spectrometer slit/crystal/emission line, monochromator calibration foil.
**One root README only** — no nested READMEs in this archive, so nested-scope inheritance
must not be designed against assumptions (the brief's §20).

**3.6 — The beamtime notes are one source family in three representations.** `.docx`,
`.pdf` and `.txt` of `250411 BL 15 IrOx NP HERFD acid base`. The `.txt` is ~29.7 KB and
contains DOCX-table-flattened sections `Sample N <name> in <medium>` with
`Step / File Number / E-chem Procedure / Notes` rows — the independent human mapping from
file number to condition. **Three files are one witness, not three.**

**3.7 — The notes contain a broad claim that contradicts the same document.** *"In ALL
experiments we used 0.1 M KOH from the same solution prepared in the beginning of the beam
time"* sits above `Sample 1 JK3 in acid`, in a document whose own preparation section
specifies 0.5 M H2SO4. A broad human statement is **candidate shared context**, and
sample-specific contrary evidence is a **conflict** — never an app-wide overwrite.

## 4. Reproducing this

```bash
# from the extracted corpus folder
find . -type f | wc -l
find . -type f | sed 's/.*\///' | awk -F. 'NF>1{print "."$NF} NF==1{print "(none)"}' | sort | uniq -c | sort -rn
# the per-macro newfile spread, the duplicate-content groups and the
# target-vs-acquisition difference: scripts/bl15_corpus_report.py
```

`scripts/bl15_corpus_report.py` recomputes every number in §1 and §2 against a folder
given on the command line. It is **not** wired into CI — CI has no corpus — and it
deliberately prints counts and structure only.

## 5. What this does NOT establish

- **No scientific mapping.** Which ISAAC v1.05 path `acid`/`base` belongs at, whether the
  second numeric token is always an electrode instance, and what reference basis a bare
  `850mV` may be assumed to have are **domain questions with Angel**, itemised in
  `docs/bl15-2-domain-questions-2026-09-16.md`. Nothing in this repository answers them.
- **No provider approval.** `HIST-003b` (model-assisted reconstruction over this corpus)
  stays blocked on **DEC-22** institutional data-egress approval. Nothing in this corpus
  has been or may be sent to any external provider.
- **No generalisation past this archive.** One beamtime, one scientist's convention, one
  element. The profile built from it is `SSRL BL15-2 — Angel-style historical naming
  profile v1`, which is the first profile and not a beamline standard.
