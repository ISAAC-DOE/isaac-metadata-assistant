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

## 0. Verdict, and what kind of evidence this is

### 0.1 Verdict

```
PRIVATE_30_VERIFICATION_PASS
```

This verdict was required by the authorizing instruction and, until 2026-08-08, **was stated
in session and nowhere in the repository** — `grep -rn "PRIVATE_30_VERIFICATION_PASS" docs/`
returned nothing. A verdict that exists only in a conversation is not evidence, so it is
recorded here with its conditions attached.

**What the verdict rests on.** Every figure in this list is **operator-relayed testimony** —
read off the screen in an authenticated browser session by the project owner and relayed, with
no response body captured anywhere. That qualification belongs here, at the point of use, and
not only in §0.2 forty lines below, which is where it used to live alone. With it stated: the
following were reported on both runs.

- 30 records read; official validation **30 passing / 0 failing**;
- the advisory format shadow **30 passing / 0 failing**;
- **0** unexpected mutation outcomes over 9,136 applicable trials, with the terminal-outcome
  accounting reconciling arithmetically (§2);
- **0** failures across all seven oracles, including `source_mutation` — the deep-copy
  isolation proof;
- `dml_statements: 0` and `ddl_statements: 0`, as **counted** values;
- `transaction_read_only: verified`, read back from the server rather than declared;
- `source_records_modified: verified` and `private_values_exposed: verified`;
- `official_validator_unchanged: verified`, from a runtime probe.

And one further figure that deliberately sits outside that list, because it is not the kind of
thing that can be "observed on both runs": ~~a second, genuinely fresh execution differing in
**0** of 50 deterministic fields~~ — **restated 2026-08-08 —** the two runs were compared with
each other **once**, and that single cross-run comparison found **0** differences across 50
deterministic fields (§4). One comparison over two runs is not an observation made on each of
them, and listing it beside the per-run figures blurred that.

**What the verdict does NOT cover.** It is a pass over *this corpus, on these two runs, for
the conditions actually measured*. It is **not**:

- a per-record claim of any kind (§5, first bullet);
- a claim of scientific correctness (§5);
- a claim that every safety condition in the authorizing instruction was *measured* —
  **§7 walks a reconstructed twenty-item list and marks each one measured / structural /
  not measured**, and three of them are not measurements at all. That list was
  reconstructed *after* the run and is not pre-registered criteria; §7's opening says so;
- a claim that any database **row** was compared before and after (it was not — §7, C12);
- a claim about future runs, other corpora, or the deployment in general.

Nothing in §2, §3 or §4 is weakened by this framing; §7 exists so the verdict cannot be read
as broader than what stands behind it.

### 0.2 This artifact is operator-relayed testimony, not an inspected artifact

**The figures on this page were read from an authenticated browser session by the project
owner and relayed. No response body was captured.** That is by design — the endpoint keeps
its result in process memory only and this environment cannot authenticate to the Authentik
edge in front of the deployment — but the consequence has to be stated plainly rather than
left for a reader to infer from a table that reads like a measurement.

So, in the same words this project already uses for facts of this shape (`CLAUDE.md` §15,
where the Slice 2A scan and the Authentik header probe are both recorded this way):

> **operator testimony, not a captured artifact.**

Concretely, and each of these is a limitation of the *evidence*, not of the run:

- there is no saved response body for run 1 or run 2 in this repository;
- there is no committed comparison script and no committed diff output for the deterministic
  rerun of §4; the freshness argument — that the second call was taken after the full cache
  lifetime, with a changed report timestamp and a reset cache age — is recorded in a commit
  message and in §4, and was not independently re-observed here;
- the "50 deterministic fields, 0 differences" figure in §4 is a relayed count, not a figure
  this artifact can reproduce;
- the safeguard states in §3 are the words the endpoint emitted, as read off the screen.

The sibling [`2026-08-08-private-30-publication-approval.md`](2026-08-08-private-30-publication-approval.md)
already labels its own contents this way ("relayed by the project owner… no transcript");
this file previously did not, which made a testimony read as a measurement. That asymmetry
was the defect, and this section is the correction.

**What is NOT testimony**, and can be checked by anyone with the repository: everything
asserted about the *code* — the safeguard implementation, the projection allowlists, the
scanner and its poisoned controls, the import-absence test behind `export_gating_unchanged`,
and every structural claim marked as such in §7. Those are code review and CI, which is a
different and weaker claim than a runtime observation, but it is a checkable one.

---

## 1. What was run

Three programs over one corpus, in a single pass, on the deployed application:

1. **Official ISAAC schema validation** — the authority on validity.
2. **A stricter format-aware shadow validation** — advisory. It decides nothing, gates
   nothing, and cannot make a record invalid.
3. **A deterministic mutation harness** — deep-clones each record, mutates only the clone,
   and checks the validator reacted as the injected change intended.

Records were parsed one at a time, deep-copied in memory, mutated only as copies, and
discarded. Stated precisely, because a looser earlier wording ("read one at a time… the corpus
was never retained") overclaimed: the raw rows arrive as **one bounded page which is held
whole**, capped by `MAX_RECORDS_CEILING` and identical to what the driver had already buffered;
rows are released progressively as they are consumed; exactly one *parsed* record exists at a
time; and **nothing is retained past the sweep**. That last property — not an impossibility of
holding the rows — is what the corpus-retention condition actually rests on. See §7, C13.

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
(`apps/api/isaac_api/verification.py:1187`). Its backing is real but static: this module
imports nothing from the export path and writes nothing, and a test asserts that
import-absence mechanically. That is a good guarantee — but it is a property of the code,
established in CI, **not a measurement taken during this run**, and it would not notice a
change made after the test last ran.

Contrast `official_validator_unchanged` immediately above it, which *is* a runtime probe
(`verification.py:1181`, calling `_official_validator_is_unchanged`): it loads the official
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
- **The corpus leak scan did not run in this mode.** It needs the corpus, and this mode does
  not retain it past the sweep — and the skip is a *design decision* (`records = None`), not
  something the code was unable to do. A different, corpus-free check stood in. See §7, C15 —
  this was undisclosed here until 2026-08-08.
- **Seven safeguards is not twenty conditions.** §7 walks a twenty-item condition list and
  marks each measured / structural / not measured; three are not measurements, and one
  (no source **row** compared, §7 C12) was never measured at all. That list is a
  **reconstruction written after the run**, not pre-registered execution criteria, and even
  its cardinality is reconstructed — §7's opening and its honesty notes 1 and 2 state the
  consequences, including that the list post-dates the results by about seven hours.
- **Everything numeric on this page is operator-relayed testimony**, not an inspected
  response body. §0.2 states the scope of that limitation.

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

## 7. The reconstructed safety-condition checklist, and which of them were measured

> **This section is a RECONSTRUCTED AUDIT CHECKLIST, not pre-registered execution criteria.**
> The authorizing instruction was given in session and no copy of it is committed, so the
> conditions below — **and the count "twenty" itself** — are this document's reconstruction,
> written *after* the run. "Twenty" is therefore not an independently attested cardinality and
> must not be quoted as one; the document already concedes that two of the twenty (C2 and C3)
> are one measurement reported as two conditions. Honesty notes 1 and 3 below give the detail.

Read on that footing: the reconstruction lists **twenty** safety conditions. §3 reports seven
safeguard rows, which is roughly a third of them — and reporting a third of a list without saying so
lets a reader assume the other two thirds were checked and simply not tabulated. They were
not all checked. This section states, for every condition, one of three verdicts:

| Verdict | Meaning |
|---|---|
| **measured per-run** | a check executed during *this* run and its result is in the payload |
| **holds structurally** | a property of the code, established by review and/or a CI test — true of the build, **not** an observation of the run |
| **not measured** | neither of the above; the condition is argued for, not checked |

**Three honesty notes about this section itself, before the table.**

1. **The twenty-item list is reconstructed, not quoted — and so is the number twenty.** The
   authorizing instruction was given in session and **no copy of it is committed to this
   repository**, so the wording, the grouping *and the cardinality* below are this document's
   reconstruction from the instruction as relayed, the safeguard set the endpoint actually
   serves, and [`record-verification-methodology.md`](record-verification-methodology.md) §7.
   The count is soft in a way the table can be seen making: C2 and C3 are **one** server-side
   read-back reported as two conditions (see C3 and the summary), so a differently-grouped
   reconstruction of the same instruction would not have said "twenty". If the original list
   is ever committed and disagrees, the original wins and this table is the bug — the same
   rule the publication approval already sets for its own allowlist.

2. **This checklist was written AFTER the results were known.** The run and its first evidence
   artifact were committed in `95e9d64` (2026-08-07 19:28). This §7 twenty-condition list first
   appears in `0edad53` (2026-08-08 02:14) — about seven hours later. So the author fixing
   *what the conditions were* already knew *which results existed*: which checks had passed,
   which had never run, and which had never been measured at all. That is the reverse of
   pre-registration, and it is the weakness a reader should hold against this section. It does
   not make any individual verdict below false — each cites a basis that can be checked
   independently — but it does mean the **set** is not evidence that the right things were
   required in advance, and a list assembled with the answers in hand can be shaped to them,
   unconsciously or otherwise. Read §7 as an after-the-fact audit of what was done, never as
   the criteria the run was held to while it ran.
3. **"Holds structurally" is a real guarantee and a weaker one.** It is established in CI
   against the committed code, so it would not notice a change made after the test last ran,
   and it is not evidence that anything happened during this run. §3 already makes exactly
   this distinction for one row; this table applies it to all twenty.

### Transport and database access

| # | Condition | Verdict | Basis |
|---|---|---|---|
| C1 | Exactly one short-lived connection, opened only for this run | **holds structurally** | one `_drain` call per run, in code; no per-run connection counter is served |
| C2 | The transaction is declared read-only | **measured per-run** | `transaction_read_only: verified` |
| C3 | Read-only is confirmed **by the server**, not merely declared by the driver | **measured per-run** | same probe as C2 — the server setting is read back, and a value that is not affirmative refuses **before** the record query is issued. C2 and C3 are one measurement reported as two conditions |
| C4 | Zero DML statements | **measured per-run** | `dml_statements: 0`, a counted value |
| C5 | Zero DDL statements | **measured per-run** | `ddl_statements: 0`, a counted value |
| C6 | Every statement parameterized; no identifier or value interpolation | **measured per-run, but withheld** | the endpoint serves this as an **eighth** safeguard. The publication approval enumerates **seven**, so its value is **not published here** and its name is not reproduced — it was removed from an earlier draft of this artifact in review. Its result is therefore not available to a reader of this page, and this row must not be read as a pass |
| C7 | No write form admitted by the query-policy guard | **holds structurally** | five frozen statements; 29 smuggling attempts admitted zero, in CI. The run does serve a refusal counter, but it is not an approved publication field |
| C8 | The connection is closed before the first record is yielded | **holds structurally** | code shape (`_drain` closes before yielding); nothing in the payload observes it |
| C9 | The record identifier is dropped before the record reaches the caller | **holds structurally** | `parse_row` normalizes then drops it; test-backed |
| C10 | Cross-references outside the sample are tolerated, never followed or repaired | **holds structurally** | code review; no counter is served |

### Isolation of the source records

| # | Condition | Verdict | Basis |
|---|---|---|---|
| C11 | Each record is deep-copied and only the copy is mutated | **measured per-run** | `source_mutation_failures: 0` — the oracle re-reads each source object after every trial |
| C12 | **No source ROW changed** | **not measured** | This is the one worth reading twice. What was compared is the **in-memory source object**, before and after each trial (C11, and `source_records_modified` in §3). **No database row was re-read and compared after the run** — it could not be, because the connection is closed before the sweep begins (C8). The zero-write position rests on C2–C7, not on a row-level before/after comparison, and this artifact should never be cited as evidence that a stored row was checked |
| C13 | The corpus is not retained | **holds structurally** | ~~records are streamed and discarded one at a time; never all in memory at once~~ — **CORRECTED 2026-08-08, because the code says otherwise and already said so in its own docstring.** `DatastoreRecordProvider._drain` accumulates the ENTIRE bounded page into one `rows` list and returns it whole (`apps/api/isaac_api/db_provider.py:857-862`). The accurate statement, which is the one the module itself makes (`db_provider.py:738-742`): **the raw drained page IS held**, bounded by `MAX_RECORDS_CEILING` and identical to what the driver had already buffered client-side; **rows are released progressively as they are consumed** (the list is popped and cleared, `:760-791`); **exactly one *parsed* record exists at a time**; and **nothing is retained past the sweep**, which is why the corpus is unavailable at report-assembly time. The condition holds on non-retention, NOT on an "all in memory" impossibility. Not separately measured — and see C15, which is the price paid for it |

### Output and privacy

| # | Condition | Verdict | Basis |
|---|---|---|---|
| C14 | No private value appears in the served payload | **measured per-run** | `private_values_exposed: verified`, computed over the **assembled** payload by a structural string allowlist plus a planted-sentinel canary that proves the allowlist is not a no-op |
| C15 | **The corpus leak scan does not run in this mode** | **DISCLOSURE — not a check that ran** | `_leak_scan` compares the payload against the corpus's own strings, so it *requires the corpus*. In this mode the corpus is consumed and dropped as the sweep proceeds (C13) — it is ~~never available to scan against~~ **not retained past the sweep, and therefore unavailable at report-assembly time**, which is when this scan would run — so **it did not run**. Two precisions the earlier wording elided. First, the raw page IS held whole while the sweep runs (C13); the property being relied on is non-retention afterwards, not an impossibility of holding it. Second, **the skip is a DESIGN DECISION, not a physical impossibility**: `run_verification` sets `records = None` for this mode (`apps/api/isaac_api/verification.py:1072`), and the corpus *could* be retained to make the scan runnable. It deliberately is not, because non-retention is worth more than the scan. `_structural_string_audit` stands in, asking the complementary question — *is every served string accountable to public information?* — which needs no corpus. That substitution is documented in the engine and is arguably the stronger question, since it catches a string arriving by a route nobody anticipated. **It was nevertheless undisclosed on this page until 2026-08-08, and that omission mattered**: a reader comparing this run to the public one would reasonably assume the same two scans ran in both, and they did not |
| C16 | No private value appears in **logs** | **holds by structural ABSENCE** | there is **no logging call on this path** — neither the verification engine nor the datastore provider emits a log record, a warning or a print. So the condition holds because there is nothing that could log, which is *not* the same as a check that inspected log output and found it clean. No log was captured, examined, or asserted about |
| C17 | Aggregate only — no identifier, title, field value, evidence entry or per-record outcome | **holds structurally, plus enforced at publication** | the report builder projects every block through a frozen key allowlist, and the published artifact is additionally scanned by a closed allowlist with poisoned controls |
| C18 | Disclosure floor applied unconditionally | **armed, not exercised** | both distributions were empty (§2), so the suppression machinery had **no input**. Arming is structural; this run is not evidence that it suppresses correctly |

### Truth path

| # | Condition | Verdict | Basis |
|---|---|---|---|
| C19 | The official validator is unchanged | **measured per-run** | runtime probe of the loaded validator (`verification.py:1181`), so it would flip on the running deployment rather than only in a unit test |
| C20 | Export gating is unchanged | **not measured — asserted** | a fixed literal at `verification.py:1187`, backed by a mechanical import-absence test in CI. **Already disclosed in §3**, which explains why the distinction matters; repeated here so the twenty-condition walk does not appear to add a measurement it does not have |

### Summary of the walk

All twenty accounted for:

| Verdict | Count | Conditions |
|---|---|---|
| measured per-run | 7 | C2, C3, C4, C5, C11, C14, C19 |
| measured per-run but **withheld** from publication | 1 | C6 |
| holds structurally (incl. C16, which holds by *absence*) | 8 | C1, C7, C8, C9, C10, C13, C16, C17 |
| armed but not exercised | 1 | C18 |
| a check that **did not run** in this mode | 1 | C15 |
| **not measured** | 2 | C12, C20 |

Two arithmetic notes, so the table is not read as stronger than it is. Those **7 measured
rows are 6 distinct measurements** — C2 and C3 are one server-side read-back reported as two
conditions — which is why §3 counts "six measured at runtime" and this section counts seven
rows. And **13 of the 20 have no per-run result at all**: the 8 structural, C18, C15, C12, C20
and, from a published reader's position, C6.

That is a materially different picture from a table of seven rows all reading `verified`, and
it is the picture the verdict in §0.1 should be read against.
