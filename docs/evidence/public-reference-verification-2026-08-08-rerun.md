# Public reference preflight — 2026-08-08 rerun

**Date:** 2026-08-08 · **Corpus:** the **ten public upstream ISAAC example records** vendored
at `tests/fixtures/official/` · **Method:**
[`record-verification-methodology.md`](record-verification-methodology.md)

## Why this note exists

Rerunning the public ten-record preflight was a **stated precondition** of the authorized
30-record run on 2026-08-08. It was performed — and it produced no artifact. The only
committed public-reference evidence was
[`public-reference-verification-2026-08-06.json`](public-reference-verification-2026-08-06.json),
dated two days earlier, so a reader checking whether the precondition had been satisfied would
have found only a file that predates the requirement.

A precondition whose satisfaction leaves no trace is indistinguishable from one that was
skipped. This note is that trace.

## What was run

Two executions, both over the same ten public records:

1. **Locally, against `main`** — the engine in `public_reference` mode.
2. **On the deployed instance** — the same mode, through the runtime verification endpoint.

## Result — identical to 2026-08-06 in every reported figure

| | Value |
|---|---|
| Records evaluated | 10 |
| Official validation | **10 passing · 0 failing** |
| Format shadow (advisory) | **10 passing · 0 failing** |
| Mutation operators defined | 755 |
| Trials attempted | 7,550 |
| Trials applicable | 3,111 |
| Trials skipped (not applicable) | 4,439 |
| Expected-outcome matches | 2,361 |
| **Unexpected outcomes** | **0** |
| Observation-only trials | 750 |
| Oracle failures (all seven categories) | **0** |

```
7,550 = 3,111 + 4,439           ✓
3,111 = 2,361 +     0 +   750   ✓
  755 × 10 = 7,550              ✓
```

Every figure matches
[`record-verification-summary.md`](record-verification-summary.md) §2 exactly. That agreement
is the point of the rerun: the engine had changed between the two dates — `e710f4a` wired the
private mode and added a `?mode=` parameter — and the preflight exists to show the **public**
path was not disturbed by it.

## What kind of evidence this is — read before quoting the table

The two executions are **not equally evidenced**, and collapsing them would repeat the defect
this note was written to fix.

- **The local run against `main`** is reproducible by anyone with the repository. It reads
  committed fixtures and opens no connection. It is the stronger of the two.
- **The deployed run** was observed in an authenticated browser session by the project owner
  and relayed. **No response body was captured** — the endpoint keeps its result in process
  memory only, and this environment cannot authenticate to the Authentik edge in front of the
  deployment. In this project's standing phrase (`CLAUDE.md` §15), that half is
  **operator testimony, not a captured artifact.**

**No comparison output was saved for either run**, so "identical in every reported figure" is
a comparison performed at the time and reported, not one this note can re-derive. A reader who
wants a mechanically checkable public-reference figure should use the committed
`public-reference-verification-2026-08-06.json`, which is a real captured payload, and treat
this note as evidence that the preflight was performed and agreed with it.

## What this does not establish

- Nothing about the **authorized 30-record private sample**. These ten are public upstream
  records and are not the private sample, not production records, and not the complete ISAAC
  corpus. The private run is reported separately in
  [`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md).
- Not a claim of scientific correctness. Passing official validation says the records conform
  to the ISAAC v1.05 schema, nothing more.
- Zero unexpected outcomes is a statement about the schema-derived mutation catalogue over
  **these ten records**, not a proof over all records or all mutations.
- **No database connection was opened by the public path**, in either execution: it reads
  committed repository fixtures. `transaction_read_only` is therefore reported
  `not_applicable`, which is the honest word for a transaction that never existed.
