# Record verification — methodology

**Date:** 2026-08-06 · **Branch:** `feat/record-verification` · **Reviewed SHA:** `59d65c7`

**Read this first.** Two corpora are discussed here and they must never be conflated.

| Term | What it is | Has it been run? |
|---|---|---|
| `public_reference` | The **ten public upstream ISAAC example records** vendored at `tests/fixtures/official/`, recorded at `schema/PROVENANCE.md:26-27` as *"copied verbatim from the upstream `examples/` directory"* | **Yes**, locally, twice. See [`record-verification-summary.md`](record-verification-summary.md) |
| `authorized_private_sample` | The authorized 30-record reference sample held in the application's own datastore | **No. It has never executed.** See §7 |

The ten public records are **not** the actual 30 records, **not** production records, **not** the private
sample, and **not** the complete ISAAC corpus. Any figure in this package that is not explicitly labelled
otherwise describes the ten public records only.

---

## 1. What the framework does

For each record in the corpus, in order:

1. Validate against the vendored official schema `schema/isaac_record_v1.json` — the **baseline**.
2. Run the **format-aware shadow validator** (§4), separately and advisorily.
3. Take a **deep copy** of the parsed record.
4. Apply one bounded, schema-derived **mutation** to the copy.
5. Evaluate the mutation against a **predetermined oracle** (§3).
6. Accumulate **scalar counters only**.
7. Re-read the source object and confirm it is **unchanged**.
8. Discard the copy.

The record source is the only thing that differs between the two modes. The mutation and validation logic
is shared — there is one engine, not two.

## 2. Mutation operators

Operators are **derived from the vendored schema**, not hand-listed, so the operator set tracks the schema
rather than drifting from it. The public run generated **755 operators**. Categories cover required-field
removal (top-level, nested, conditional), optional-field removal, wrong primitive type, wrong structured
type, invalid enum member, invalid declared format, empty string, empty array, empty object, evidence
removal, confirmation removal, and bounded combinations.

**The expected result is declared before execution**, never after observing it. An operator whose outcome
the schema does not determine is recorded as *observation-only* (§5) rather than being retro-fitted with
whichever oracle the run happened to satisfy.

Generation is deterministic. No random seed varies between runs; §6 shows the measured proof.

## 3. The seven oracles

| Oracle | What it asserts |
|---|---|
| `source_mutation` | The source object is byte-identical after the trial. **This is the deep-copy isolation proof.** |
| `restoration` | Reverting the mutation restores the original validity verdict. |
| `repeatability` | The same trial run twice yields the same outcome. |
| `ordering_instability` | Outcomes do not depend on the order trials are executed in. |
| `no_guessing` | No trial causes the system to supply a value it was not given. |
| `workflow_consistency` | Derived workflow state stays consistent with the record's validity. |
| `engine_disagreement` | The official validator and the harness agree on validity. |

`source_mutation` is worth singling out. Deep-copy isolation is **measured, not asserted**: the oracle
re-reads each source object after every trial and compares. A shallow copy, or an in-place mutation that
escaped the copy, moves this counter off zero. It is not a comment claiming isolation — it is a check that
would fail if isolation broke.

## 4. Format-aware shadow validation

JSON Schema treats `format` as an annotation unless a `FormatChecker` is attached. The official validator
deliberately attaches none, so `format` does **not** gate export today.

`apps/api/isaac_api/format_shadow.py` builds **its own** `FormatChecker` and **its own** validator instance,
starting from an empty checker set. It never touches `Draft202012Validator.FORMAT_CHECKER`, never calls
`FormatChecker.cls_checks`, and therefore cannot arm format enforcement for any other caller in the
process. `tests/test_truthpath_characterization.py` passes unmodified, which is the check that would fail
if the global registry had been armed.

The shadow is **advisory and non-gating**. It cannot change an official verdict, export readiness,
workflow state, or persisted record state. Tests pin each of those.

Findings carry a stable error code and a **schema** path. They deliberately **do not** carry the
validator's message, because a jsonschema message embeds the offending value — the same reasoning already
recorded at `apps/api/isaac_api/db_recon.py:1349`.

**Measured scope note:** the vendored v1.05 schema declares exactly **one** format, `date-time`, at six
sites. The checker covers the complete declared set. A guard test fails if a future schema revision
declares a format the shadow does not implement, so the coverage claim cannot go stale silently.

## 5. Terminal-outcome accounting

Every attempted trial belongs to **exactly one** terminal category, and the totals reconcile exactly:

```
attempted  = applicable + skipped_not_applicable
applicable = expected_outcome_matches + unexpected_outcomes + observation_only_trials
```

Pinned at `apps/api/tests/test_corpus_mutation.py:318-334`, and displayed on the Statistics page with the
backend field names printed beside the plain labels so the words and the implementation cannot drift.

Two categories are easy to misread:

- **`skipped_not_applicable`** — the operator does not apply to that record's structure (e.g. removing a
  field the record does not have). Attempted, never executed.
- **`observation_only_trials`** — applicable and executed, but the schema does not predetermine the
  outcome, so no pass/fail judgement is claimed. Recording these as "expected matches" would inflate the
  success figure with trials that were never a test of anything.

## 6. Determinism

Two independent full runs were compared field by field, excluding only `generated_at`, `duration_ms` and
`cache_age_seconds`. **Every remaining field was identical.** Commands and output in
[`record-verification-summary.md`](record-verification-summary.md) §3.

## 7. The authorized private mode — implemented, reviewed, NOT executed

The mode exists in code and has passed independent adversarial review. **It has never run.** It cannot run
from this environment, and it has not run anywhere:

- The datastore is reachable only from a deployed pod.
- GitHub Actions is **billing-blocked org-wide**, so no image can publish.
- **No HTTP route reaches the mode.** `provider_factory` defaults to `None`, the endpoint accepts zero
  parameters, and an AST scan confirms no production module imports `db_provider`. It is fail-closed by
  construction, not by configuration.

**No database connection was opened during any of this work.**

Its safety properties, all verified under adversarial attack rather than asserted:

- Five frozen SQL statements, the only variable bound as `%s`. 29 smuggling attempts — `;`-chaining,
  comment tricks, case-disguised writes, CTE-wrapped writes, `FOR UPDATE`, `pg_read_file`, `lo_import`,
  `dblink`, `nextval`, `SELECT … INTO`, `CREATE TEMP`, `COPY`, `CALL`, `DO $$` — **zero admitted**.
- Read-only is **verified server-side**: `SHOW transaction_read_only` must read back `on`. Driver-level
  `set_session(readonly=True)` and `SET TRANSACTION READ ONLY` are belt-and-braces and cannot by
  themselves authorize the `verified` safeguard. `off`, `OFF`, `None`, blank, an unrecognised word and an
  empty row all refuse **before the record query is issued**.
- `CHAR(26)` blank padding is stripped and the identifier **dropped before the record reaches the
  caller** — not merely unused.
- Rows are **drained and the connection closed before the first record is yielded**. An earlier design
  held the transaction across the whole sweep (~22 minutes at the ceiling, against a documented
  connection limit of five); since psycopg2 had already buffered every row client-side, holding it bought
  the streaming property nothing.
- Cross-references pointing outside the sample are **expected**; missing rows are tolerated, never
  repaired, followed, or disclosed.
- Withdrawal is **absence, not a disabled switch**: `verification_modes()` computes the mode tuple from
  the approval flag, and a test parses `verificationContract.ts` so the TypeScript copy cannot drift.

## 8. Disclosure control

Floor-5 minimum cell size with **second-cell absorption**, applied **unconditionally in both modes** —
including on the public corpus where it is not needed. A gate that arms only for the private corpus is a
gate someone forgets to arm.

**Why hiding the key is not enough.** The key universe here is publicly enumerable — these are schema
paths anyone can read out of the vendored schema. Withholding exactly one key therefore identifies it by
elimination, and a published `suppressed_total` then gives its exact count. So while exactly one category
is withheld and any cell remains published, the smallest published cell is absorbed (ties broken by key,
ascending, for determinism) until at least two are withheld.

Verified by brute force over 44,681 count-maps: `suppressed_categories == 1` occurs **only** when the
input has a single sub-floor key and there is nothing left to absorb. With zero published cells there is
nothing to eliminate against, so the key is not identified — only its count is. That case is carved out
explicitly and pinned by its own test rather than skipped.

**Instance-path histograms are withheld.** This project shipped `by_instance_path` in `v0.0.32` and
withdrew it: over a ~30-row corpus an error count of one at an instance path **is** a single-record fact.
Path breakdowns here are **schema** paths, obeying *the schema may describe the data; the data may not
describe itself*. Instance paths are computed internally and never projected.

## 9. Leak detection, and the defect that was found in it

Two runtime privacy measurements guard the payload:

- **`private_values_exposed`** scans the **assembled payload**, so it tests what would be served rather
  than what the code intends to serve. Backed by a planted-sentinel canary across five shapes.
- **`official_validator_unchanged`** reads the live validator, so arming format enforcement globally would
  flip it on the running deployment, not merely in a unit test.

**A Critical defect was found here by independent review and is recorded rather than quietly fixed.** The
scan compared candidate values against `json.dumps(payload)`, which defaults to `ensure_ascii=True`. So
`→` became the six characters `→` in the haystack while the needle stayed raw, and the comparison was
**always false**. Three of the 392 candidate strings in the shipped ten-record corpus are already
non-ASCII, and chemistry metadata (Å, µ, °C, →, en-dashes) makes this the common case rather than a corner
case. The payload consequently reported `private_values_exposed: "verified"` without having earned it, and
the docstring enumerated "Two residuals" without naming this one.

The scan now walks the payload's **decoded string leaves**, keys included, so there is no representation
for an escape to hide in. Its proving test derives the candidate from the live corpus rather than
hard-coding one, and fails loudly if the corpus ever stops containing a non-ASCII value — so it cannot
silently become a test of nothing.

A related weakness was fixed in the structural audit, which had admitted strings by **shape**: a sha256
digest, `deadbeef` and an RFC 3339 timestamp were all accepted — exactly what ISAAC records carry in
`raw_data` pointers and `created_utc`. Shape regexes are replaced by **equality** against the values the
run actually emitted, with the schema fingerprint **recomputed** from the vendored schema's bytes rather
than read back from the payload, so it cannot whitelist itself.

## 10. Safeguards are tri-state

Each safeguard reports `verified` | `not_applicable` | `unverified`. **Never a bare `true`.**

In the public run `transaction_read_only` reports **`not_applicable`**, not `verified`, because no
connection is opened and there is no transaction to have kept read-only. Reporting it as verified would be
a claim about an event that never happened. The UI renders a distinct word per state and tones
`not_applicable` as neutral rather than as success.

## 11. What this methodology does not establish

- It does not establish that the actual 30 records pass. **That run has not occurred.**
- It does not establish that the private sample behaves identically to the public one.
- It does not establish that the private sample contains no schema drift.
- Zero oracle failures is evidence **over the corpus actually run**, not a proof over all records or all
  possible mutations.
- Passing mutation tests says nothing about whether AI suggestions are correct. That is a separate
  property with separate evidence — see [`suggestion-safety-methodology.md`](suggestion-safety-methodology.md).

## Authorization

The 2026-08-05 approval basis is recorded at
[`2026-08-05-q19-q20-authorization.md`](2026-08-05-q19-q20-authorization.md). It is **relayed testimony**:
no transcript exists in this repository and no agent-to-owner communication occurred. It contradicts the
previously committed state (`docs/dean-authorization-packet.md`, *"Status: NOT SENT"*), which is marked
superseded rather than deleted so the trail stays legible.

The public preflight needs no authorization from anyone: the ten records are already public upstream.
