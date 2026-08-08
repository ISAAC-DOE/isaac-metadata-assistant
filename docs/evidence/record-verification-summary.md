# Record verification — measured summary

> ## ⚠ SUPERSEDED IN PART — read this before anything below
>
> **This document is dated 2026-08-06 and describes the state at `59d65c7`. It is kept as a
> dated artifact and is NOT rewritten.** Retracted claims are struck through and labelled.
>
> **What changed after it was written:** the authorized private mode was wired on 2026-08-07
> (`e710f4a`), and it **ran twice on 2026-08-08**. The org-wide GitHub Actions billing block
> also ended on 2026-08-07, so CI executes again and the repository is public.
>
> **Superseding artifact: [`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md).**
> Where this page says the private run has not happened, that one is correct. It is
> **operator-relayed testimony, not a captured artifact** (its §0.2), and only some of the
> required safety conditions were measured per-run (its §7).
>
> **Everything in §2–§6 below is unaffected**: those are the ten *public* records, measured
> locally on 2026-08-06, and they were re-run on 2026-08-08 with identical figures — see
> [`public-reference-verification-2026-08-08-rerun.md`](public-reference-verification-2026-08-08-rerun.md).
> The stale claims are confined to §7.

**Date:** 2026-08-06 · **Reviewed SHA:** `59d65c7` · **Method:** [`record-verification-methodology.md`](record-verification-methodology.md)

> The verification framework was exercised against **ten public ISAAC reference records**. ~~A read-only
> mode for an **authorized 30-record reference sample is implemented and independently reviewed but has
> not yet been executed.**~~ — **CORRECTED 2026-08-08: that mode has since been wired and
> executed twice.**

~~**No database connection was opened during this work.**~~ — **CORRECTED.** True of the work
described on this page, and false as a standing statement: the 2026-08-08 private runs each
opened one short-lived read-only connection from the deployed pod. The run-scoped form this
project requires is *"no database connection was opened during this session"*.

---

## 1. Scope — read before quoting any number below

Every figure on this page describes the **ten public upstream ISAAC example records** vendored at
`tests/fixtures/official/` (`schema/PROVENANCE.md:26-27`: *"copied verbatim from the upstream `examples/`
directory"*).

They are **not** the actual 30 records, **not** production records, **not** the private sample, **not**
the complete ISAAC corpus.

## 2. The public reference run — executed 2026-08-06

Raw sanitized aggregate: [`public-reference-verification-2026-08-06.json`](public-reference-verification-2026-08-06.json)

```
verification_mode : public_reference
corpus_size       : 10
duration_ms       : 18,910
schema            : ISAAC v1.05 (vendored)
status            : ok
```

**Baseline and shadow**

| | Passing | Failing |
|---|---|---|
| Official validation | **10** | 0 |
| Format shadow | **10** | 0 |

Both distributions are empty, so no cell was withheld (`suppressed_categories: 0`, `floor: 5`).
Suppression still ran — it is unconditional, not conditional on there being something to hide.

**Mutation accounting — reconciles exactly**

| Category | Count |
|---|---|
| Operators defined | 755 |
| Trials attempted | **7,550** |
| ├─ applicable | 3,111 |
| └─ skipped, not applicable | 4,439 |
| Of the applicable: expected-outcome matches | 2,361 |
| Of the applicable: **unexpected outcomes** | **0** |
| Of the applicable: observation-only | 750 |

```
7,550 = 3,111 + 4,439          ✔
3,111 = 2,361 +     0 +   750  ✔
```

The 750 observation-only trials are applicable and executed, but the schema does not predetermine their
outcome, so no pass/fail judgement is claimed for them. Counting them as successes would inflate the
figure with trials that were never a test of anything.

**Oracles — all seven at zero**

| Oracle | Failures |
|---|---|
| `source_mutation` | **0** |
| `restoration` | 0 |
| `repeatability` | 0 |
| `ordering_instability` | 0 |
| `no_guessing` | 0 |
| `workflow_consistency` | 0 |
| `engine_disagreement` | 0 |

`source_mutation_failures: 0` is the **deep-copy isolation proof** — the oracle re-reads each source
object after every trial. Measured, not asserted.

**Safeguards**

| Safeguard | State |
|---|---|
| `source_records_modified` | `verified` |
| `private_values_exposed` | `verified` |
| `official_validator_unchanged` | `verified` |
| `export_gating_unchanged` | `verified` |
| `transaction_read_only` | `not_applicable` |
| `parameterized_queries_only` | `not_applicable` |
| `dml_statements` | 0 |
| `ddl_statements` | 0 |

The two `not_applicable` entries are the honest values: **this run opened no connection**, so there was no
transaction to have kept read-only and no query to have parameterized. Reporting them as `verified` would
be a claim about an event that never happened.

## 3. Determinism — verified by rerun

Two independent full runs, compared field by field, excluding only `generated_at`, `duration_ms` and
`cache_age_seconds`:

```
deterministic_fields_identical: True
run1 duration_ms: 18910   run2 duration_ms: 18701
run2 mutations: {"expected_outcome_matches": 2361, "observation_only_trials": 750,
                 "operators_defined": 755, "trials_applicable": 3111,
                 "trials_attempted": 7550, "trials_skipped_not_applicable": 4439,
                 "unexpected_outcomes": 0}
```

Every non-volatile field was identical.

## 4. Zero-write and no-leak position

**Zero-write.** No write was attempted or possible: the public path reads committed repository fixtures
and opens no connection. `dml_statements: 0` and `ddl_statements: 0` are the counters' measured values,
not assertions. In the private mode the query-policy guard rejects every write form, and read-only is
verified server-side by reading back `SHOW transaction_read_only` — ~~but **that mode has not run**~~
**and, as of 2026-08-08, that mode HAS run: it reported `transaction_read_only: verified`,
`dml_statements: 0` and `ddl_statements: 0` on both runs.** Note the scope precisely: those are
**object-level and statement-level** results. **No database row was re-read and compared before
and after** — see that artifact's §7, C12.

**No-leak.** The payload carries no record id, title, field value, evidence entry, attribution, per-record
outcome, raw validator message, unsuppressed small cell, database hostname, internal service name,
connection string, or credential. Two runtime measurements enforce this and one is backed by a
planted-sentinel canary across five shapes. Note the scope of that claim honestly: it is **code review
plus a passing canary over the public corpus**, ~~not an observation of the private mode, which has never
executed~~ — **CORRECTED 2026-08-08: the private mode has since executed and reported
`private_values_exposed: verified` on both runs.** That result carries one difference from the
public run that this page could not have known and a reader must not gloss: **the corpus leak
scan does not run in the private mode at all** (it needs the corpus, which that mode discards);
a corpus-free structural audit stands in. See that artifact's §7, C15.

Independent review found and this build fixed a Critical defect in that scan — it compared against
JSON-escaped text and so was blind to any value containing a non-ASCII character, of which the shipped
corpus already contains three. See methodology §9.

## 5. Test verification — measured, not quoted

| Check | Command | Result |
|---|---|---|
| Backend, whole repo | `.venv/bin/pytest -q` | **2,637 passed, 2 skipped, 0 failed** |
| Frontend | `npx vitest run` | **2,949 passed / 2,949, 120 files** |
| Typecheck | `npx tsc -b` | exit 0 |
| Truth-path characterization | `pytest tests/test_truthpath_characterization.py -q` | **77 passed**, file unmodified |
| Truth-path diff | `git diff --stat -- src/ schema/ tests/ pyproject.toml` | **empty** |
| Snapshot, both artifacts | `build_memory_snapshot.py … --detail-out --check` | no drift |

Frontend counts must be taken at low machine load: a vite dev server left running in a sibling worktree
put this machine at load average 85.89, under which the `graph-*` specs exceed their 5,000 ms timeouts.
The same five files pass **111/111 in 13.5 s** in isolation. The figure above was measured at load 3.52.

## 6. Reviewed SHAs

| PR | SHA | Contents | Verdict |
|---|---|---|---|
| #63 | `59d65c7` | Verification engine, authorized private mode, Statistics UI | **SHIP** (backend and frontend reviewed independently) |
| #64 | `4f845ea` | No-guessing suggestion safety | **SHIP** |
| #59 | `25c595d` | Statistics foundation and adapters | Minor round closed |

Both #63 reviews returned DO NOT SHIP on their first pass. The backend's blocker was the Critical leak-scan
defect; the frontend's was a live honesty regression plus a misattributed test failure. Both were fixed and
re-reviewed, and in the second pass each fix was confirmed by **re-injecting the defect and watching the
test fail** — not by a green run alone.

## 7. What has NOT happened

> **This entire section is SUPERSEDED as of 2026-08-08.** It was accurate on 2026-08-06.
> Struck-through lines are retracted, not deleted.

- ~~**The authorized 30-record run has not occurred.** Records evaluated against the private sample: **0**.~~
  — **RETRACTED 2026-08-08.** The run occurred, twice, on the deployed application, and the
  recorded verdict is:

  ```
  PRIVATE_30_VERIFICATION_PASS
  ```

  **Records evaluated against the private sample: 30.** Figures, and the limits on what they
  establish, are in [`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md).
  Three things a reader must carry across with the verdict: the figures are **operator-relayed
  testimony, not a captured artifact** (§0.2 there); **only some of the safety conditions were
  measured per-run** (§7 there), and that condition list is itself a **reconstruction written
  after the run**, not pre-registered criteria; and the verdict is a pass over *that corpus, on
  those two runs, for the conditions actually measured* — nothing wider.
- ~~No image has published. **CI is billing-blocked org-wide**: jobs terminate in 3–10 s with `steps: []`
  and the annotation *"The job was not started because recent account payments have failed or your
  spending limit needs to be increased."* Verified at `59d65c7`, `4f845ea`, `25c595d` and earlier runs.~~
  — **RETRACTED 2026-08-08.** The org-wide billing block ended on 2026-08-07; GitHub Actions
  execute again and images publish. The repository is also public now, which it was not when
  this line was written.
- ~~Nothing here is CI-verified. Nothing has merged.~~ — **RETRACTED.** The work described on
  this page has since merged, and CI has run on subsequent pull requests.
- **No browser QA, no Playwright run, no screenshots.** See [`screenshot-inventory.md`](screenshot-inventory.md).
- Hosted QA remains `HOSTED QA PENDING (Krish)` — `/krish` sits behind an Authentik edge this environment
  cannot authenticate to ~~, and no image has published since `2fbecd4` regardless~~ — **RETRACTED
  2026-08-08.** That clause contradicted the billing-block retraction two bullets above, and it could not
  have been true alongside this page's own central fact: the authorized private verification mode was
  wired in `e710f4a`, and it then ran **on the deployment** — which requires an image carrying `e710f4a`
  to have published. The honest statement is narrower and is about this environment, not about the world:
  **no image build or rollout was observed from here.** Which image `/krish` is serving has not been
  verified by this session, and no rollout is claimed as verified.

## 8. What these results do not establish

Zero unexpected outcomes and zero oracle failures is evidence **over the ten records actually run**. It is
not a proof over all records, all mutations, or the private sample. It says nothing about whether the
actual 30 records pass, whether they contain schema drift, or whether AI suggestions are correct — that
last is a separate property with separate evidence in
[`suggestion-safety-methodology.md`](suggestion-safety-methodology.md).

This bullet stands exactly as written: *these ten records* still establish nothing about the
thirty. The separate 2026-08-08 artifact reports the thirty, and the boundary between the two
corpora is unchanged — nothing here should be quoted as a figure about the private sample, and
nothing there should be quoted as a figure about these ten.
