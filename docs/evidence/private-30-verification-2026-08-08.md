# Authorized 30-Record Reference Sample — Verification Evidence

**Date:** 2026-08-08 · **Machine-readable figures:**
[`private-30-verification-2026-08-08.json`](private-30-verification-2026-08-08.json)

This is a **curated aggregate artifact**, not a dump of the endpoint response. Fields were
selected against an explicit publication approval and then checked mechanically by
[`scripts/scan_public_evidence.py`](../../scripts/scan_public_evidence.py), which enforces a
**closed key allowlist** — a key that is not enumerated is a failure, not a warning. Several
fields that *were* present in the served payload are deliberately absent here; appearing in
the payload was never a reason to publish.

---

## 1. What was run

Three programs over one corpus, in a single pass, on the deployed application:

1. **Official ISAAC schema validation** — the authority on validity.
2. **A stricter format-aware shadow validation** — advisory. It decides nothing, gates
   nothing, and cannot make a record invalid.
3. **A deterministic mutation harness** — deep-clones each record, mutates only the clone,
   and checks the validator reacted as the injected change intended.

Records were read one at a time, deep-copied in memory, mutated only as copies, and
discarded. The corpus was never retained.

## 2. Results

| Programme | Result |
|---|---|
| Records evaluated | **30** |
| Official validation | **30 passing · 0 failing** |
| Format shadow (advisory) | **30 passing · 0 failing** |
| Mutation operators defined | 755 |
| Trials attempted | 22,650 |
| Trials applicable | 9,136 |
| Trials skipped (not applicable) | 13,514 |
| Expected-outcome matches | 7,021 |
| **Unexpected outcomes** | **0** |
| Observation-only trials | 2,115 |
| Oracle failures (all seven categories) | **0** |
| Approximate duration | ~225 s |

**The accounting reconciles, and was checked rather than asserted:**

```
trials_attempted  == applicable + skipped        22650 == 9136 + 13514   ✓
trials_applicable == expected + unexpected + observation-only
                                                  9136 == 7021 + 0 + 2115 ✓
operators × records == attempted                 755 × 30 == 22650        ✓
```

### Protected distributions

Both breakdowns — by error code and by schema path — are **empty**: `cells: []`,
0 categories withheld, 0 occurrences withheld, disclosure floor 5. There were no shadow
failures, so there was nothing to distribute and nothing to suppress.

That is a fact about this corpus, not a property of the mechanism. The suppression
machinery (minimum cell size, plus an absorption step that prevents identifying a withheld
category by elimination) was armed throughout and simply had no input.

## 3. Safeguards — six measured at runtime, one asserted

| Safeguard | Result | Measured at runtime? |
|---|---|---|
| Transaction read-only | **verified** | yes — declared twice, then re-read back from the server |
| DML statements | **0** | yes — counted |
| DDL statements | **0** | yes — counted |
| Source records modified | **verified** (none were) | yes — independent structural snapshot before and after each record |
| Private values exposed | **verified** (none were) | yes — scan of the assembled payload |
| Official validator unchanged | **verified** | yes — runtime probe of the loaded validator |
| Export gating unchanged | **verified** | **no — see below** |

**One row is asserted, not measured, and saying so is the point of this table.**
`export_gating_unchanged` is a fixed literal in the report builder
(`apps/api/isaac_api/verification.py:1149`). Its backing is real but static: this module
imports nothing from the export path and writes nothing, and a test asserts that
import-absence mechanically. That is a good guarantee — but it is a property of the code,
established in CI, **not a measurement taken during this run**, and it would not notice a
change made after the test last ran.

Contrast `official_validator_unchanged` immediately above it, which *is* a runtime probe
(`verification.py:1143`, calling `_official_validator_is_unchanged`): it loads the official
validator on the running deployment and checks it is still format-blind, so it would flip to
`unverified` in production rather than only failing a test.

An earlier draft of this document headed this section "all measured, none assumed" and said
"`verified` is a measurement, not an assertion". That was **false for this one row**, and an
independent review caught it before publication. The claim is corrected rather than removed,
because the distinction between a measured guarantee and an asserted one is exactly what a
reader of this artifact needs in order to weigh it.

## 4. Deterministic rerun

The programme was executed **twice**, and the second execution was genuinely fresh.

This needed care. The report is cached, and calling the endpoint again inside the cache
window returns a byte-identical copy of the first result — comparing that to run 1 is a
tautology that cannot fail, and would have produced a meaningless green. The second run was
therefore taken only after the full cache lifetime had elapsed, and was confirmed fresh by
its report timestamp changing and its cache age resetting.

| | Result |
|---|---|
| Runs compared | 2 |
| Deterministic fields compared | 50 |
| **Deterministic differences** | **0** |
| Key sets identical | yes |
| Volatile fields that differed | 3 (report timestamp, measured duration, cache age) |

Every figure in §2 and §3 is identical across both runs.

## 5. Limitations

- **These figures describe an aggregate. They establish nothing about any individual
  record**, and no per-record outcome was computed into this artifact.
- **The format shadow is advisory.** Its 30/30 result is not a second validity verdict; it
  cannot make a record valid or invalid and gates nothing.
- **For six of the seven safeguards, `verified` means a check ran and held on this run.** It
  is not a claim about other runs, other corpora, or the deployment in general. For the
  seventh — `export_gating_unchanged` — it is a static assertion backed by a CI test, not a
  runtime measurement; §3 says which is which and why the difference matters.
- **Zero unexpected outcomes is a statement about the mutation catalogue**, which is derived
  from the schema. A defect no operator in that catalogue expresses would not appear here.
- **Passing official validation is not a claim of scientific correctness.** It says the
  records conform to the ISAAC v1.05 schema, nothing more.
- **The empty distributions are a property of this corpus**, as noted in §2 — not evidence
  that the suppression mechanism is effective, since it had no input to act on.
- **Two runs establish reproducibility, not stability over time.** They ran about an hour
  apart against the same deployment and the same data.

## 6. What is deliberately not published here

Excluded regardless of having been available: any corpus or schema fingerprint, any
record-derived hash or digest, record identifiers, titles, field values, evidence entries,
attribution, raw validator messages, per-record results, unsuppressed histograms, exact
timestamps, database or service topology, connection details, and internal operational
identifiers.

The scanner treats each of these as a failure rather than trusting review, and it was itself
tested against a deliberately-poisoned control file to confirm it fails when it should.
One honest limitation of that scanner: its **key allowlist** is the primary defence. Free
text placed under an *approved* key would not be caught by any content pattern, which is why
this artifact contains only enumerated scalars and prose written for publication.
