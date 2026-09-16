# The reading chain, driven end to end over the sanitized fixtures

**What this is.** Before the session/route wiring existed, the whole reading layer was
driven as a chain — `archive` → `classify` → read → `relate` → `reconstruct` — over
`tests/fixtures/bl15/gold/mini_corpus`, using only merged code. It establishes that the
six modules **compose**, which is a different claim from each passing its own tests.

**It is not a substitute for the committed acceptance test.** This was a throwaway script
in a scratchpad; CI cannot re-check it. Its value is that it produced the expected numbers
*before* the wiring slice ran, so a discrepancy there is a finding rather than a puzzle.

## What it did

```text
inventory    14 entries, 4,463 B, 0 refused, 2 duplicate groups, truncated=None
relate        5 units, 4 run candidates, 5 conflicts, 3 unattached
reconstruct  95 candidates, 17 proposable, 2 shared (README), 0 unregistered concepts
             by mapping status — deterministic 8 · normalized 9 ·
             needs_domain_review 25 · not_expressible 40 · blocked_by_build 5
```

The five units, with the classification each was given by content:

| unit | run candidate | scans | conflicts | type |
|---|---|---:|---:|---|
| `alignsynth` | **no** | 0 | 0 | `alignment` |
| `01_01_SYN1_acid_beforeCycling_filter10_060mV` | yes | 2 | 0 | `spec_acquisition` |
| `02_01_…_060mV_again` | yes | **0** | 0 | `spec_acquisition` |
| `03_02_SYN2_base_after1500Cycling_ffilter35_1200mV_zz9` | yes | 0 | **2** | `spec_acquisition` |
| `03_02_SYN2_base_after1500Cycling_filter20_0p5nm_1200mV` | yes | 0 | **1** | `spec_acquisition` |

The alignment source is a **unit but not a run candidate** — which is the arrangement that
stopped 242 of the real corpus's 908 scans being orphaned, exercised here on a fixture.
`02_01_…_again` has an **empty** scan directory, deliberately reproducing the two empty
`_dir`s in the real archive; so "every unit has at least one scan" is a false invariant and
nothing may assert it.

## The five proofs the authorizing brief requires

| | result |
|---|---|
| 1. `.dat` files do **not** become Runs | 2 scan files, **0** became units — **PASS** |
| 2. `.mac` files do **not** become Runs | 3 macros, **0** became units — **PASS**. And `run01.mac` yields **2** candidates from its two `newfile` blocks, so a multi-`newfile` macro really does produce several measurements |
| 3. shared README context is **inherited**, not copied | **2** shared candidates, **0** copied onto any unit — **PASS** |
| 4. conflicts stay visible with **no** chosen winner | 5 conflicts, and **every** conflicted candidate's `proposed_value` is `None` — **PASS**. That is enforced by the type (`SemanticCandidate` refuses a value beside an `unresolved_reason`), not by the walk |
| 5. unknown tokens and unmapped concepts **survive** | 2 `unknown_token` items and **65** unmapped-or-deferred candidates — **PASS** |

The five conflicts, each surfaced with every reading intact:

- `duplicate_legacy_number: 3` — two distinct fixtures carry legacy number 3
- `macro_declared_never_acquired: 99_NEVER_ACQUIRED_SYN`
- one `internal_declaration_vs_filename`
- two `acquired_never_declared`

## What it exposed

**A signature in the wiring slice's brief was wrong, and only running the code found it.**
`filenames.read_filename` takes **no text**: it is
`read_filename(record, *, profile_id=…, source_type=None, stem=None, id_prefix="")` and
reads the stem off `SourceRecord.basename`. The brief had it as `(record, text, *, profile)`.
The correction was sent to that slice before it wrote against the wrong shape, along with
the instruction to treat every other signature in the brief as a claim to check — because
the brief was written from the design document rather than from calling the code.

`stem=` is the interesting part of the real signature: it is how a SPEC `#F` declaration
and a macro `newfile` target get read by the **same** recognizers as an external filename,
so no second tokenizing path is needed anywhere.

## Reproducing it

The script is not committed. What is committed and equivalent in coverage is the
per-module suite (`apps/api/tests/test_bl15_*.py`, 390 tests) plus the wiring slice's
acceptance walk. To re-derive these numbers, drive the six entry points in the order above
against `tests/fixtures/bl15/gold/mini_corpus`; the sequence is written out in
`docs/bl15-2-integration-design-2026-09-16.md` §6.
