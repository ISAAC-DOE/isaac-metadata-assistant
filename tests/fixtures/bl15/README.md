# BL15-2 reader fixtures — SYNTHETIC. Every byte in this directory is invented.

**NO PART OF THE REAL SSRL BL15-2 ARCHIVE IS HERE, AND NONE MAY EVER BE PUT HERE.**
The corpus the readers were built against is real experimental data and real human
notes (`CLAUDE.md` §6); it lives on the project owner's machine and is never
committed. These fixtures reproduce that archive's **structure** and its
**anomalies** at a fraction of its size, with everything a scientist could
recognise replaced:

| Real | Here |
|---|---|
| sample codes | `ZZ1`, `ZZ2`, `ZZ3`, `SYNTH2` — obviously fake |
| materials | `SyOx`, `SyTiO2` |
| potentials | round numbers only (`100mV`, `1p2V`) |
| motor positions | `1`, `2`, `3`, … or round decimals |
| energies | `1000`–`1100`, nowhere near any real absorption edge |
| the scientist's name, the beamtime label, note prose | absent entirely |

A guard test (`apps/api/tests/test_bl15_readers.py`, *"every fixture is
synthetic"*) greps every file in this directory for a list of real-corpus markers
and fails if any appears. It exists so a future session cannot paste a real file
in here "just to check something".

**What is NOT replaced, and why.** SPEC and beamline **command, header and motor
names** are the real ones — `#F`, `#O0`, `qdo`, `newfile`, `mv`, `mvr`, `umv`,
`trigger`, `IrL3_xas`, `XAS_MAIN_GRID`, `Sx`/`Sy`/`Sz`/`Sr`, `c1p`/`c1y`. A
fixture that renamed them would exercise none of the readers' patterns, and none
of them is a scientific value, a sample identity or a line of anybody's notes.
The element symbol is replaced anyway (`Sy`, which is not an element) wherever a
fixture states one as data rather than as part of a command name.

Each fixture either states in its own first line that it is synthetic, or is named
and described in the table below — and several carry the anomaly they exist for in
their own filename.

## What each fixture reproduces

| Fixture | Real structure it reproduces |
|---|---|
| `filenames/angel-style-set.txt` | a set of Angel-style stems covering every concept the profile recognises |
| `filenames/potential-units-set.txt` | `mV` and `p`-decimal volts naming the same potentials, as `MERGE/` and the acquisitions do |
| `filenames/ffilter-typo-set.txt` | the real `ffilter35` doubled-prefix typo beside its correctly-spelled family |
| `filenames/duplicate-legacy-number-set.txt` | two distinct measurements carrying one legacy number (real: `32`) |
| `filenames/unknown-token-set.txt` | stems carrying a token no profile knows, beside tokens it does |
| `spec/03_01_ZZ1_acid_beforeCycling_100mV_filter10` | a root SPEC acquisition: separated `#O`/`#P` blocks, 2 scans, then a THIRD block whose `#P1` line is deliberately mispaired — **and a `#F` that is an ABSOLUTE PATH rather than a bare stem**, which 2 of the archive's 188 `#F` lines are |
| `spec/rename-group/29_03_ZZ2_base_after1500Cycling_filter20_100mV` | **a GROUP of three** consecutive acquisitions whose internal `#F` disagrees with its filename, all making the identical substitution — a systematic rename, not a typo |
| `spec/rename-group/30_…`, `spec/rename-group/31_…` | the other two members of that group |
| `spec/alignment` | an extensionless SPEC acquisition whose stem says alignment — content-led classification's exhibit A |
| `spec/SyOx_5wpc_pellet_transmission` | an extensionless SPEC acquisition of a reference pellet |
| `scans/03_01_ZZ1_acid_beforeCycling_100mV_filter10_001.dat` | a per-scan export: keyed `#P` lines, no `#O`, no `#F` |
| `macros/run15.mac` | a macro declaring THREE `newfile` blocks (real maximum: 8), commands before the first declaration, and one call with the wrong argument count |
| `macros/run99-unacquired.mac` | a macro declaring a target no acquisition file provides (real: 9 of them) |
| `macros/Ir_XAS.mac` | a `def` method macro declaring ZERO `newfile` blocks, with two `XAS_MAIN_GRID` literals and the printed call signature |
| `macros/motors_cpy_pre99.mac` | a motor snapshot: all `umv`, no `newfile`, no `def`, and crystal motors that must NOT read as a sample position |
| `notes/readme.txt` | the archive's single root readme — beamtime-scope shared context, no BOM, LF endings |
| `notes/beamtime-notes.txt` | the DOCX-flattened notes: a `Step / File Number / E-chem Procedure / Notes` table with a POPULATED column, a second table whose column is EMPTY throughout, a broad "in ALL experiments" claim contradicting one of its own sample sections, a UTF-8 BOM and CRLF endings |
| `processed/63_06_ZZ1_f10.txt` | a `MERGE/` two-column processed spectrum: no header at all |
| `oversize/` | built at test time, not committed — the byte and evidence ceilings are exercised by generated input rather than by a large committed file |

## Two fixtures whose whole point is a REFUSAL

`spec/03_01_ZZ1_acid_beforeCycling_100mV_filter10` carries a third scan block whose
`#P1` line has **one fewer field than its `#O1` line**. The real archive has **zero**
mispaired lines (measured over all 94 acquisitions), so this case cannot be exercised
without inventing it — and it must be exercised, because a silently mispaired mapping
shifts every later motor's value onto its neighbour's name.

`notes/beamtime-notes.txt`'s second table has an empty `File Number` column from top
to bottom. That is not decoration: the first version of the notes reader paired any two
bare integers it met and read Sample 1's **step** numbers as **file** numbers, because
an empty DOCX cell flattens to a lone tab that a blank-line skip swallowed. The fixture
pins the fix.
