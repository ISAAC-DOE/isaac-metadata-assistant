# Record verification — methodology

> ## ⚠ SUPERSEDED IN PART — read this before anything below
>
> **This document is dated 2026-08-06 and describes the state at `59d65c7`. It is kept as a
> dated artifact and is NOT rewritten.** Retracted claims below are struck through and
> labelled, never deleted, so the trail stays legible.
>
> **What changed after this document was written:**
>
> | When | What | Where |
> |---|---|---|
> | 2026-08-07 (`e710f4a`) | The authorized private mode was **wired and became reachable**. `VerificationState` is now constructed with a `provider_factory`, and the route takes a `?mode=` parameter. | `apps/api/isaac_api/routes.py` — `_verification_provider_factory`, `get_runtime_verification` |
> | 2026-08-08 | The private mode **ran, twice, on the deployed application.** | [`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md) |
> | 2026-08-07 | GitHub Actions **executes again** (the org-wide billing block is over) and the repository is **public**. | CI runs on subsequent PRs |
>
> **Superseding artifact: [`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md).**
> Where this document and that one disagree about whether the private run has happened, that
> one is correct. Note that it is **operator-relayed testimony, not a captured artifact** (its
> §0.2), and that only some of the required conditions were measured per-run (its §7) — so
> "it has run" replaces "it has never run", and replaces nothing else.
>
> Everything in this document about the **method** — the engine, the operators, the oracles,
> the accounting, the disclosure control, the leak-scan defect and its fix — is unaffected and
> still current.

**Date:** 2026-08-06 · **Branch:** `feat/record-verification` · **Reviewed SHA:** `59d65c7`

**Read this first.** Two corpora are discussed here and they must never be conflated.

| Term | What it is | Has it been run? |
|---|---|---|
| `public_reference` | The **ten public upstream ISAAC example records** vendored at `tests/fixtures/official/`, recorded at `schema/PROVENANCE.md:26-27` as *"copied verbatim from the upstream `examples/` directory"* | **Yes**, locally, twice. See [`record-verification-summary.md`](record-verification-summary.md) |
| `authorized_private_sample` | The authorized 30-record reference sample held in the application's own datastore | ~~**No. It has never executed.** See §7~~ — **RETRACTED 2026-08-08: it has executed, twice**, on the deployed application. See [`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md), and §7 below for which of this document's structural reasons are now false |

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

## 7. The authorized private mode — ~~implemented, reviewed, NOT executed~~ implemented, reviewed, and SINCE EXECUTED

> **CORRECTED 2026-08-08. Four claims in this section were true on 2026-08-06 and are false at
> HEAD.** They are struck through rather than deleted. The safety properties listed after them
> are unaffected — they describe the code, and the code still does what they say.

The mode exists in code and has passed independent adversarial review. ~~**It has never run.** It cannot run
from this environment, and it has not run anywhere:~~

**RETRACTED — it has run.** It executed twice on 2026-08-08 against the deployed application;
figures and their limits are in
[`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md). It remains
true that it **cannot be run from this environment**: reaching it needs an authenticated
hosted session behind the Authentik edge, which is why the resulting evidence is
operator-relayed testimony rather than a captured response body.

The three structural reasons given for "it cannot run", each corrected:

- The datastore is reachable only from a deployed pod. — **STILL TRUE**, and it is why the run
  had to happen on the deployment rather than here.
- ~~GitHub Actions is **billing-blocked org-wide**, so no image can publish.~~ — **FALSE at
  HEAD.** The org-wide billing block ended on 2026-08-07; Actions execute again, images
  publish, and the repository is now public. (Recorded so the reason is not quoted onward from
  this file; the billing state was never a property of this verification work.)
- ~~**No HTTP route reaches the mode.** `provider_factory` defaults to `None`, the endpoint accepts zero
  parameters, and an AST scan confirms no production module imports `db_provider`. It is fail-closed by
  construction, not by configuration.~~ — **FALSE at HEAD, in all three parts.** Commit
  `e710f4a` wired the mode: `apps/api/isaac_api/routes.py` defines
  `_verification_provider_factory` and passes it into `VerificationState`, so
  `provider_factory` is no longer `None`; `get_runtime_verification` now takes a `?mode=`
  query parameter; and a production module therefore does import `db_provider`. The two guard
  tests that pinned the old shape were **deliberately inverted** in the same commit rather
  than deleted — they were an honesty coupling, not a prohibition. **What survives verbatim:**
  the default is still the public corpus, and a caller who names no mode is never handed the
  datastore one. The mode is now fail-closed **by configuration** — the environment gates in
  `db_recon.check_env_gates` and the provider — rather than by the absence of a wire.

~~**No database connection was opened during any of this work.**~~ — **CORRECTED.** True of the
work described in this document, and false as a standing statement: the 2026-08-08 runs opened
one short-lived read-only connection each, from the pod. The form this project requires is
run-scoped — *"no database connection was opened during this session"* — never the unbounded
past tense.

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
  the approval flag, and a test parses `verificationContract.ts` so the TypeScript copy cannot drift. The
  same test file parses `VERIFICATION_REPORT_FORMAT_VERSION` for the same reason: it is a second
  underived copy of a backend constant, and a one-sided bump would ship a UI that refuses every report as
  `unreadable` without failing a test in either suite.

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
nothing to eliminate against, so the key is not identified by elimination — but its **count** still was,
and against a universe an observer enumerates from the public schema a lone key's exact count *is* the
cell. **So `suppressed_total` is now served as `null` in that case.** Not `0`, which would be a false
claim, and `suppressed_categories` is not reduced — the withholding stays disclosed, only the recoverable
figure goes. This is what bumped the report format to **3**; the field's type is `int | null` from that
version on.

**Both histograms withhold the total together, because they share one.** `failures_by_error_code` and
`failures_by_schema_path` are two breakdowns of the *same* findings — the sweep increments one cell in
each per finding — so `sum(by_code) == sum(by_schema_path) == F`, and every served histogram satisfies
`F = sum(published cells) + suppressed_total`. Nulling only the histogram that reached one category
therefore withholds nothing: the sibling, published adjacent to it on the same screen, gives back
`F − sum(cells)`. The trigger shape is ordinary rather than contrived, since the shadow error-code
vocabulary is closed and small while schema paths are many — two records with a `date-time` violation at
two different pointers produce one error code and two schema paths. So **either** histogram reaching one
category nulls the total on **both**. The decision lives in the block builder, which is the only place
that sees both distributions; the `null` cannot be undone by the record counts, because `records_failing`
and `official_validation.failing` count **records** and are a lower bound on `F`, not `F`.

Both the single-histogram case and the cross-histogram case are pinned by their own tests, including a
reproduction of the two-pointer shape above, rather than skipped.

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

- It does not establish that the actual 30 records pass. ~~**That run has not occurred.**~~ —
  **CORRECTED 2026-08-08: that run has since occurred**, and its result is reported in
  [`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md). The bullet
  itself still stands as written: *this methodology document* establishes nothing about the 30
  records; the separate artifact does, within the limits its §0.2 and §7 set out.
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
