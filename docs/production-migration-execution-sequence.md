# Production migration execution sequence — the single operator entry point

**STATUS: every byte is published, approved and verified. NOTHING HAS BEEN APPLIED ANYWHERE.**
The only remaining work in the entire migration programme is production execution, and **that is
the operator's act.** No agent may perform any step on this page.

This document exists because the sequence's steps live in **three different approval packets**, and
the failure the ordering prevents is not a bad statement — it is **a correct statement run at the
wrong time.** An operator should not have to assemble the order from three documents.

---

## 0. What this document is, and what it is NOT

| | |
|---|---|
| **It IS** | one unambiguous ordering, with each step's authoritative detail named and linked |
| **It IS NOT** | an authorization. Owner approval of a migration's bytes is a **precondition** for the operator's step, never a substitute for it |
| **It IS NOT** | a replacement for the packets. Every precheck, postcheck, rollback and gate query stays in its packet; this page does not restate them |
| **It IS NOT** | a new production operation. Nothing here is invented — §1 is [`migration-approval-packet-0005.md`](migration-approval-packet-0005.md) §12A with its self-references resolved |

**Why the sequence is not transcluded byte-for-byte:** §12A is written to be read *inside* the
`0005` packet, so it says *"this packet's §5 prechecks"* and *"this packet's §7 postchecks"*. Copied
verbatim into this file those phrases would point at this file, which has no §5 and no §7 — a false
reference introduced by the act of consolidating. So the references are **resolved to named
documents** below, and a parity test
(`apps/api/tests/test_migration_sequence_index.py`)
pins this page against §12A so the two cannot drift.

---

## 1. The sequence — ordered, and the order is the safety property

**No step may be skipped, reordered, or run in parallel with another.**

```text
 1.  verify backup / restore
 2.  verify the migration ledger          packet 0005 §5, prechecks 1-5
 3.  apply approved 0003 + 0004 TOGETHER  python scripts/db_migrate.py --apply --through 0004_submissions
 4.  verify                               0003's and 0004's OWN postchecks
 5.  apply approved 0005                  python scripts/db_migrate.py --apply --through 0005_run_projection
 6.  verify                               packet 0005 §7 postchecks
 7.  run the isaac_runs backfill          python scripts/db_backfill_runs.py --apply
 8.  REQUIRE every failed / refused / UNREADABLE count = 0
 9.  run BOTH §8A completeness queries    packet 0005 §8A
10.  REQUIRE both = 0
11.  only then may the Stage-2b read cutover be permitted
```

### Where each step's authoritative detail lives

| Step | Read this |
|---|---|
| 2 | [`migration-approval-packet-0005.md`](migration-approval-packet-0005.md) §5 — prechecks 1–5 |
| 3 | [`-0003.md`](migration-approval-packet-0003.md) and [`-0004.md`](migration-approval-packet-0004.md) — approved 2026-08-17 |
| 4 | `0003` §7 and `0004` §7 — **two separate postcheck sets** |
| 5 | [`-0005.md`](migration-approval-packet-0005.md) — approved 2026-09-17 |
| 6 | `0005` §7 |
| 7–8 | `scripts/db_backfill_runs.py`; [`isaac-runs-stage-2-contract.md`](isaac-runs-stage-2-contract.md) |
| 9–10 | `0005` §8A — the two SQL queries, quoted there and nowhere else |
| 11 | `0005` §11 and the Stage-2 contract. **A decision, not a continuation** |

---

## 2. Six things in that sequence that are decisions, not formalities

1. **Step 3 applies two migrations deliberately, and that does not violate the bounded rule.**
   `0003` and `0004` are ONE decision — `0004` declares a foreign key into a table `0003` creates —
   so they are applied together or not at all. `--through 0004_submissions` is what makes
   *"together"* mean *"and not `0005` as well"*.

2. **Steps 4 and 6 are separate verifications and must not be merged.** Running 3 and 5 back to
   back and verifying once at the end produces a state in which a failure cannot be attributed.

3. **Step 8 is a REQUIREMENT, not a report.** A non-zero `UNREADABLE`, `refused` or `failed` means
   some experiment was not projected — and steps 9–10 would then describe an incomplete pass
   **while returning 0**. This is the one place in the sequence where a green reading is actively
   misleading if step 8 was not checked first.

4. **Step 11 is a DECISION.** Nothing in steps 1–10 authorizes it. The §8A queries returning 0
   makes the cutover *safe to consider*. Whether to make `isaac_runs` a read source is a separate
   reviewed slice; removing `runs` from the experiment document is a **third** decision, justified
   by no measurement in this repository.

5. **Never issue an unbounded `--apply`, at any step.** Three approved-and-unapplied migrations now
   sit on disk, so an unbounded `--apply` would land all three in one unverifiable step — exactly
   the failure the bounded form exists to prevent. `--apply` once globbed every migration on disk,
   which made the documented operator ask *mechanically impossible* to satisfy until `--through`
   was added.

6. **Do not use raw `psql` as a migration substitute at any step.** The runner is what records the
   `isaac_schema_migrations` ledger row; a hand-run statement applies the change and leaves the
   ledger lying about it.

`scripts/db_backfill_runs.py` defaults to **report-only**; `--apply` performs the projection.
`--dry-run` is accepted and is a deliberate no-op, so the documented safe invocation works rather
than erroring.

---

## 3. Preconditions — all satisfied, each mechanically re-derivable

| Precondition | State | How to re-derive rather than trust this table |
|---|---|---|
| `0003` + `0004` owner-approved | **YES**, 2026-08-17 | each packet's STATUS block and §12D |
| `0005` owner-approved | **YES**, 2026-09-17 | `0005` packet STATUS and §12 |
| Migration + rollback bytes on `origin/main` | **YES** | `git diff origin/main -- apps/api/isaac_api/migrations/` is empty |
| All six digests match the packets | **YES** | `shasum -a 256 apps/api/isaac_api/migrations/000{3,4,5}*.sql`, compared against each packet's digest table — and pinned by `test_the_approval_packet_digests_match_the_committed_files` |
| Forward, rollback and wrong-order refusal proven against a real PostgreSQL | **YES, in CI** | `.github/workflows/ci.yml` → `postgres-migration`, against `postgres:18` |
| Constraint refusal coverage | **41 of 46 declared** | Actions run `32800763199`, job `97660962127`, at `c153ec9`. The 5 unblamed are named in the `0003`/`0004` packets' §12B; three are structurally unprovable in isolation because the table's equality CHECKs subsume its shape CHECKs |
| Hosted engine major version matches CI's container | **YES — both 18** | `server_version_major` in [`hosted-observation-2026-09-13.md`](evidence/hosted-observation-2026-09-13.md) |

**What CI still does NOT prove, and it is the whole reason the operator's step is separate:** the
container is empty, with a two-row synthetic stand-in for `records`. *"Behaves against the real
data, roles and grants"* remains **unproven**, and no amount of CI can close it.

---

## 4. What is already applied, and why that is not a precedent

`0001_experiments` (2026-08-09) and `0002_runs` (2026-08-12) were applied to the hosted database
**by the infrastructure owner**. Both are recorded as **operator testimony, not captured
artifacts** — no agent connected to that database, then or since.

**Two migrations having been applied by the infrastructure owner is not a precedent, a delegation,
or a standing permission.** `0003` and later each needed their own packet, their own owner approval
and their own operator action; the first two are done, the third is not.

---

## 5. The hard stop — unchanged by every approval above

`CLAUDE.md` §15. **No agent may** apply a migration, open a connection to the SLAC PostgreSQL,
request a kubeconfig, a port-forward or a Secret, run the backfill, perform the Stage-2b cutover, or
change Kubernetes. Not one of the eleven steps.

The project owner reviews migration text before it is applied — **done for all three.** What remains
is execution, and execution is the operator's.

---

## 6. Audience-specific summaries that derive from this page

[`hao-production-unblock-package-2026-09-17.md`](hao-production-unblock-package-2026-09-17.md) §I
carries a **compressed five-step form** of this sequence for an external operator reading one
document. It is a summary of §1, not a competing sequence; where they differ in granularity §1 and
`0005` §12A govern. If you change the ordering here, change it there too — and expect the parity
test to be the thing that tells you the packet moved.
