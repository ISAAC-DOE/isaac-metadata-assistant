# `isaac_runs` Stage 2 — the completeness contract

**Status: contract + Stage 2a implemented. No read has moved. Migration `0005_run_projection` is
NOT APPLIED ANYWHERE, and applying it is the operator's act, not an agent's.**

Written 2026-08-19. This document exists because the instruction that authorized the work said
*"write an explicit contract first"* and *"prefer an explicit completeness/cutover model over
`rows exist -> use them`"*. Both of those are answers to a defect that was **measured** in this
repository, not anticipated, and §1 states it before anything is proposed.

---

## 1. The blocker, measured

Stage 1 (`0002_runs`, applied to the hosted database by Dean on 2026-08-12) made `isaac_runs` a
**shadow** of the experiment document: after `PostgresOrdinaryStore.persist` returns, the rows for
that experiment equal `exp.sorted_runs()`. Nothing reads them. `Experiment.to_state()` still
carries `runs`, and that document is authoritative.

A read cutover — "read the runs from the table instead of from the document" — **cannot be written
against Stage 1 as it stands**, and the reason is not performance or risk appetite. It is that

> **`SELECT ... FROM isaac_runs WHERE experiment_id = %s` returning zero rows is ambiguous.**

It means *either* "this experiment has no runs" *or* "this experiment's runs have never been
projected". Both are reachable, and the second is the **normal** state of every experiment that
was persisted before Stage 1 shipped:

| How zero rows arises | Reachable? | Evidence |
|---|---|---|
| The experiment genuinely has no runs | yes | a record with no `POST /runs` ever |
| Persisted before the shadow write existed | yes | every row written before this slice |
| Persisted while `isaac_runs` was absent | yes, routinely | the image rolls out on merge and the operator applies migrations by hand afterwards; `experiment_repository._table_available` skips the run writes for exactly this window, and `/api/health` keeps reporting `durable: true`, correctly |
| The operator rolled `0002` back under a running pod | yes | `forget_run_table_presence()` exists because it happened in design review |

A reader that treats zero rows as "no runs" therefore **silently deletes every run of every
pre-existing record** the first time it is switched on, and reports success. That is the defect
this contract exists to make unwritable.

**`rows exist -> use them` does not fix it either.** "Some rows exist" cannot distinguish a
complete projection from a partial one, and it answers the wrong question for the case that
matters most: an experiment with genuinely zero runs would fall back to the document forever, so
the cutover would never be complete and no measurement could ever say it was.

---

## 2. The contract

**A projection is a claim about an experiment at a version, made by a named projector, and it is
recorded as a row.** Absence of the row is absence of the claim.

```
isaac_run_projection (
    experiment_id          -> PK, FK to isaac_experiments
    experiment_rev         -> the rev of the document the rows were projected FROM
    experiment_generation  -> the generation of that document
    run_count              -> how many rows were written (0 is a real answer)
    projector              -> 'write-path' | 'backfill'
    projected_utc          -> server-side stamp
)
```

### 2.1 The four states, and every read must distinguish all four

| State | Predicate | What a reader may do |
|---|---|---|
| **COMPLETE** | a projection row exists AND its `(experiment_rev, experiment_generation)` equal the experiment document's | use `isaac_runs` |
| **STALE** | a row exists and the pair differs | use the document; the rows are behind |
| **NEVER PROJECTED** | no row | use the document; the rows say nothing |
| **UNAVAILABLE** | `isaac_runs` or `isaac_run_projection` absent | use the document |

`run_count = 0` with a matching pair is **COMPLETE and means zero runs** — which is the whole
point, and the state Stage 1 could not express.

### 2.2 Five invariants

1. **The stamp is written in the same transaction as the rows it describes, or not at all.** There
   is no code path that writes one without the other. Two statements in one transaction cannot
   disagree about whether they committed.
2. **The stamp embeds the version it was made at, so it cannot go stale while looking fresh.** A
   later save that does not maintain the rows advances the document's `rev` or `generation` past
   the stamp, and the pair stops matching. Staleness is *detected*, never *assumed absent*.
   *~~The one case where a document changes without `rev` moving is `Experiment.save()`, the
   unversioned primitive — and it goes through the same `persist`, so the rows are re-diffed and
   the stamp re-written in that same transaction.~~ **The conclusion holds and the reasoning was
   wrong; an independent review measured it.** `Q_UPSERT_EXPERIMENT`'s predicate accepts only
   three cases: the generation differs, the incoming `rev` is strictly greater, or the state is
   byte-identical. A CHANGED document at the SAME `(rev, generation)` matches none of them, so it
   is REFUSED — `DurableWriteConflict` — and nothing is re-diffed and nothing is re-stamped. The
   invariant survives for a better reason than the one first given: such a write does not land at
   all, so it cannot leave a stamp describing rows it did not write.*
3. **The stamp is written only inside the accepted branch of the experiment compare-and-swap.** A
   writer that lost the CAS stamps nothing. This is the same `if accepted` gate the run rows are
   already inside, and it is load-bearing for the same reason: a loser that stamped would claim
   completeness for a document it failed to write.
4. **`run_count` is the size of the row set the transaction ESTABLISHED, and no CHECK
   enforces it.** ~~"MEASURED, not asserted. It is the length of the row set the transaction
   actually wrote, not the length of `sorted_runs()` as an intention."~~ **That was FALSE and
   an independent review measured it.** The value returned is `len(desired_ids)`, and
   `desired_ids` is derived from `exp.sorted_runs()` — so it is *identically*
   `len(exp.sorted_runs())`, and relocating the same expression into the callee is not a
   measurement. Worse, the test that cited the invariant asserted exactly the equality the
   invariant denied.

   **What is true, and is the property a reader actually needs:** after the upsert-and-delete
   pair, the table holds exactly the desired set for that experiment, so the count and the
   rows agree *by construction of those two statements* rather than by observation. It is a
   writer-maintained projection, which `0005_run_projection` says of it in its own comment,
   and the honest place to check it against reality is a real engine — CI compares the stored
   `run_count` against an actual `count(*)` of `isaac_runs`. A per-save `SELECT count(*)`
   would make it observed and would cost a statement on every write to confirm something the
   two preceding statements already determine; that trade was considered and declined.
5. **No read moves in Stage 2a.** The table is written and nothing consults it. Turning a reader
   on is Stage 2b, is a separate reviewed slice, and requires the backfill of §3 to have run.

### 2.3 What is deliberately NOT in the contract

- **No `session_id`.** Same permanent reason as `isaac_runs`: `ALTER` is a forbidden verb in
  `db_write._FORBIDDEN_KEYWORDS` and `CREATE TABLE IF NOT EXISTS` is a silent no-op, so a
  worked-example projection that ever reached this table would be permanently unidentifiable and
  permanently uncleanable. Tutorial isolation is inherited by construction: the stamp is written
  inside `persist`, after `refuse_if_not_persistable`.
- **No global "the projection is complete" flag.** Completeness is per experiment. A deployment-wide
  boolean would be a claim about rows nobody counted.
- **No trigger.** `db_migrate.split_statements` refuses a dollar-quoted body, so a trigger is not
  expressible in a committed migration here. The invariant is held by there being exactly one
  writer.
- **`ON DELETE` is unwritten**, so the default `NO ACTION` applies and deleting an experiment that
  still has a projection row is refused by the database — the same choice `0002_runs` made, for the
  same two reasons (no unbounded silent cascade; and it is the reversible direction, since going
  from `CASCADE` back would need an `ALTER`).

---

## 3. The backfill, and why it is a separate operator action

Every experiment persisted before Stage 1 is **NEVER PROJECTED**. `scripts/db_backfill_runs.py`
walks `isaac_experiments`, projects each experiment's runs through the *same* code path the write
uses, and stamps `projector: 'backfill'`.

It is **idempotent** (a re-run re-projects and re-stamps to the same values), **additive** (it
issues no `DELETE` except the write path's own `Q_DELETE_ABSENT_RUNS`, which removes rows the
document no longer names), and it **never names `records`** — the statement policy refuses that by
identifier in any position.

**It has never been executed.** Like `scripts/db_recon.py` it is deliberately absent from the
container image (the Dockerfile COPY allowlist), so no application route can reach it, and running
it is an operator action against an environment an agent may not connect to.

**Stage 2b must not begin until the backfill has run in the target environment and reported
zero unprojected experiments.** That is the completeness gate, and it is a measurement
rather than a belief.

***AN EARLIER VERSION OF THIS PARAGRAPH SAID THE BACKFILL "reported `never_projected: 0`".
IT DOES NOT AND CANNOT.*** An independent review measured that the string appears in no
print statement anywhere in the repository — and the reason is structural rather than an
oversight: the backfill never reads `isaac_run_projection`, because a read would make it
that table's first reader, which is precisely the Stage-2b decision this gate exists to
*precede* (and would break invariant 5 above).

**So the gate has two halves, and both are needed.** The script reports whether it did all
the work: `experiments UNREADABLE`, `refused` and `failed` must every one be **0**, or some
experiment was not projected. The operator then runs the two SQL queries in
`docs/migration-approval-packet-0005.md` §8A — never-projected and stale — and both must
return 0. Neither half substitutes for the other: a clean script run over a table it could
not fully read proves nothing, and a clean query pair taken before the script finished
describes an incomplete pass.

---

## 4. What Stage 2b will and will not be allowed to claim

When a reader is eventually moved onto `isaac_runs`:

- It reads the projection state first and falls back to the document on any of STALE, NEVER
  PROJECTED or UNAVAILABLE. Fallback is **normal operation**, not an error path.
- `runs` **stays in the experiment document.** Removing it is a third decision and is not justified
  by any measurement in this repository. The brief that motivates it — "contract §8 D7" — is cited
  by several files here and **committed to none of them**, which is recorded rather than treated as
  authority.
- No surface may report the cutover as done on the strength of code alone. The honest statement is
  the measured per-experiment state distribution.

---

## 5. Authorization basis

`CLAUDE.md` §15's 2026-08-07 write lift covers Create Experiment persistence *"plus the minimum
supporting persistence architecture that feature requires"*, and its enumerated table list has been
corrected twice — once for `isaac_runs`, once for the five submission-lifecycle tables — each time
because a slice added a table to `db_write.OWNED_TABLES` that no committed sentence named.

**`isaac_run_projection` is named in `CLAUDE.md` §15**, and it is named here, so the basis is
committed rather than conversational.

***AN EARLIER VERSION OF THIS SENTENCE SAID "in the same change that creates it". THAT WAS
FALSE BY ONE COMMIT, and an independent review measured it:*** the table shipped in `6dce6fd`,
which does not touch `CLAUDE.md`; §15 was updated in `8f7c650`. Recorded rather than softened,
because the claim was published and the point of the enumeration is that it is checkable. One
commit late is a smaller gap than the two previous times and is still not what was claimed. Listing a table in `OWNED_TABLES`
**grants nothing on its own** — it permits a statement naming it to pass the policy; what may be
written is decided by the module-level `Q_*` constants and the tests that enumerate them.

`0002_runs` is **not edited**, and no Stage-2 behaviour is hidden inside `0003_revisions` or
`0004_submissions`. The three were separately reviewed and the first is applied to the hosted
database; touching any of them would be the change this project's rules most explicitly forbid.

---

## 6. The operator packet

`docs/migration-approval-packet-0005.md`. It carries the SHA-256 of the exact bytes, the forward and
rollback statements, the prechecks and postchecks, and the same hard stop every packet carries:
**the owner reviews the migration text and the operator applies it. No agent applies a migration to
the hosted database, and no agent asks for a kubeconfig, a port-forward, or a Secret.**
