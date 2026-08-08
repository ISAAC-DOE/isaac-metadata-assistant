# Publication approval — authorized 30-record verification aggregate

**Date recorded:** 2026-08-08
**Approver:** the project owner (Krish), in session
**Source:** relayed by the project owner; no direct agent-to-database-owner communication
occurred, and no transcript of Dean's own words is quoted here.

This file exists because an independent review asked the right question: the published
artifact cited "an explicit publication approval" that existed nowhere in the repository.
A citation to a document no reader can open is not evidence. This is that document, recorded
in the same shape as
[`2026-08-05-q19-q20-authorization.md`](2026-08-05-q19-q20-authorization.md) — as
**testimony**, not as a captured artifact.

## What was approved

Publication to the **public** repository of a **curated aggregate evidence artifact** from
the authorized 30-record reference sample, **after** a successful deterministic rerun.

Explicitly: *"publish a curated aggregate evidence artifact, not a raw dump of the endpoint
response"*, and *"do not publish merely because a field appeared in the endpoint payload."*

## The approved field list — closed

| # | Field |
|---|---|
| 1 | corpus type |
| 2 | record count |
| 3 | official passing/failing totals |
| 4 | shadow passing/failing totals |
| 5 | operator count |
| 6 | attempted / applicable / skipped totals |
| 7 | expected / unexpected / observation-only totals |
| 8 | oracle-failure totals |
| 9 | source-mutation-failure total |
| 10 | protected/suppressed aggregate distributions |
| 11 | read-only verification result |
| 12 | DML count |
| 13 | DDL count |
| 14 | source-record-modification result |
| 15 | private-value-exposure result |
| 16 | official-validator-unchanged result |
| 17 | export-gating-unchanged result |
| 18 | schema version |
| 19 | approximate duration |
| 20 | deterministic-rerun result |
| 21 | methodology and limitations |

**This list enumerates SEVEN safeguard results (11–17). The endpoint serves EIGHT.**
`parameterized_queries_only` is the eighth and is **not approved**. It shipped in the first
draft of the artifact and was removed after review — see "What this already caught" below.

## Excluded, regardless of availability

Any corpus fingerprint · record-derived hash or digest · record identifier · title · field
value · evidence · attribution · raw validator message · database or service topology ·
connection information · credentials · internal operational identifiers · per-record result ·
raw unsuppressed histogram.

## Enforcement

The list above is executable, not advisory:
[`scripts/scan_public_evidence.py`](../../scripts/scan_public_evidence.py) holds it as a
**closed key allowlist** — an unenumerated key is a failure, not a warning — plus content
patterns for identifiers, digests, timestamps, topology, connection variables and
credentials. `apps/api/tests/test_public_evidence_scan.py` runs it against the committed
artifact **and** against poisoned controls, so the scanner is proven to fail when it should
rather than merely observed to pass.

**The allowlist must equal this approval.** If the two ever disagree, the approval wins and
the allowlist is the bug.

## What this already caught

Publishing to a public repository is irreversible, and the first draft of the artifact
already contained one field beyond this list. An independent review found it before the PR
was opened and named the precedent: `CLAUDE.md` §15 gate **G3**, where five aggregates went
beyond Dean's enumerated list and shipped in `v0.0.32` because only the *top-level* response
keys had been frozen. The reasoning that produced both mistakes is identical — *"it was in
the payload"* — which is why that sentence is now a documented non-reason.

## Scope

This approval covers the publication of aggregate figures. It is **not**:

- an extension of the Q19 approval for what may be computed,
- authorization for hosted per-record display (still **closed by default**, `CLAUDE.md` §15
  gate **G2**),
- authorization to publish anything from a future run without re-checking it against this
  list.
