# Migration approval packet — `0005_run_projection`

**STATUS: NOT APPROVED. NOT APPLIED ANYWHERE. Applying it is the operator's act, and no
agent may do it.**

| | |
|---|---|
| Migration | `apps/api/isaac_api/migrations/0005_run_projection.sql` |
| SHA-256 (forward) | `ebff660fc51559cd4ab6ce66a7b1ec943de86f2362d37adde153f0c74c8ae7ee` |
| Rollback | `apps/api/isaac_api/migrations/0005_run_projection.rollback.sql` |
| SHA-256 (rollback) | `54a17432150525f75a6e94557a137029a3ce3fd41cea9debced361abda90e735` |
| Creates | one table, `isaac_run_projection`, and one index |
| Verbs used | `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`. Nothing else. |
| Touches `records` | **No.** The identifier does not appear in any statement, and a test reads the file off disk to assert it. |
| Touches `isaac_experiments`, `isaac_runs`, or the five submission tables | **No.** It declares a foreign key *into* `isaac_experiments`; it alters nothing. `ALTER` is a forbidden verb in `db_write._FORBIDDEN_KEYWORDS`. |
| Data moved | **None.** This migration creates an empty table. |

**Recompute the digests before approving.** They are the bytes this packet describes, and
if they differ from the file on disk then this packet describes something else:

```bash
shasum -a 256 apps/api/isaac_api/migrations/0005_run_projection.sql \
              apps/api/isaac_api/migrations/0005_run_projection.rollback.sql
```

---

## 1. Why this migration exists — a measured ambiguity, not a design preference

`0002_runs` (applied to the hosted database by Dean, 2026-08-12) made `isaac_runs` a
**shadow** of the experiment document. Nothing reads it. A reader cannot be written
against that alone, because

```sql
SELECT ... FROM isaac_runs WHERE experiment_id = %s
```

returning **zero rows** means *either* "this experiment has no runs" *or* "this
experiment's runs were never projected" — and both are reachable:

| How zero rows arises | Reachable? |
|---|---|
| The experiment genuinely has no runs | yes |
| Persisted before the shadow write shipped | yes — every pre-existing row |
| Persisted while `isaac_runs` was absent | **yes, routinely** — the image rolls out on merge and migrations are applied by hand afterwards |
| `0002` rolled back under a running pod | yes |

A reader that treated zero rows as "no runs" would **silently delete every run of every
pre-existing record** the first time it was switched on, and report success. This table
makes that unwritable: absence of a row is absence of a claim, and `run_count = 0` beside
a **matching version pair** is a positive statement that this experiment has no runs.

The full contract, including the four states every future read must distinguish, is
[`docs/isaac-runs-stage-2-contract.md`](isaac-runs-stage-2-contract.md).

## 2. The exact forward SQL

Two statements, separated by a line containing only `--;` (the runner splits on that
marker, never on `;`, so a semicolon in a comment or a string cannot split a statement).

```sql
CREATE TABLE IF NOT EXISTS isaac_run_projection (
    experiment_id          text        PRIMARY KEY
                           CONSTRAINT isaac_run_projection_experiment_fk
                           REFERENCES isaac_experiments (experiment_id),
    experiment_rev         bigint      NOT NULL
                           CONSTRAINT isaac_run_projection_rev_non_negative
                           CHECK (experiment_rev >= 0),
    experiment_generation  text        NOT NULL,
    run_count              bigint      NOT NULL
                           CONSTRAINT isaac_run_projection_count_non_negative
                           CHECK (run_count >= 0),
    projector              text        NOT NULL
                           CONSTRAINT isaac_run_projection_projector_known
                           CHECK (projector IN ('write-path', 'backfill')),
    projected_utc          timestamptz NOT NULL DEFAULT now()
)
--;
CREATE INDEX IF NOT EXISTS isaac_run_projection_projector_idx
    ON isaac_run_projection (projector, projected_utc)
```

The committed file carries ~130 lines of comment above this explaining every column and
constraint. Read the file, not this excerpt, before approving.

## 3. The foreign key refuses a parent delete — and that is a decision

No `ON DELETE` clause is written, so the action is the SQL default `NO ACTION`, which for
this non-deferrable constraint behaves as `RESTRICT`: **deleting an experiment that still
carries a projection claim is refused by the database.** Two independent reasons, the same
two `0002_runs` gives:

1. `ON DELETE CASCADE` turns one statement into an unbounded silent multi-row
   destruction. `DELETE FROM isaac_experiments` already passes the write policy.
2. It is the **reversible** choice. A future delete path can delete claims explicitly and
   then the experiment, with no schema change. Going the other way needs an `ALTER`, which
   the policy refuses.

**Disclosed as `0002` disclosed it:** `ON DELETE CASCADE` is *also unwritable* under the
current statement policy, which reads the `delete` after `on` as naming a table it does
not own. The design argument stands on its own; this note exists so a reader is not told a
constraint was a free choice when it was also forced.

## 4. What it deliberately does not do

- **No read moves.** Exactly ONE statement in the application names this table
  (`experiment_repository.Q_UPSERT_RUN_PROJECTION`) and nothing reads it — pinned by
  `test_0005_is_written_by_the_write_path_and_read_by_nothing`, measured over the
  module-level constants rather than asserted. **That includes the backfill**, which
  computes its own report from the experiment documents and never reads the claim table;
  the Stage-2b completeness question is therefore answered by an SQL query an operator
  runs (§8A), not by the script.
- **No backfill runs.** `scripts/db_backfill_runs.py` exists, has **never been executed
  anywhere**, and is deliberately absent from the container image (the Dockerfile COPY
  allowlist ships one file out of `scripts/`; a test asserts this one is not it).
- **No `session_id` column, and none can ever be added.** `ALTER` is forbidden and
  `CREATE TABLE IF NOT EXISTS` is a silent no-op against an existing table, so a
  worked-example claim that ever reached this table would be permanently unidentifiable
  and permanently uncleanable. Tutorial isolation is inherited by construction: the stamp
  is written inside `persist`, after `refuse_if_not_persistable`.
- **No trigger.** `db_migrate.split_statements` refuses a dollar-quoted body, so a trigger
  is not expressible in a committed migration here. `run_count` is a writer-maintained
  projection and this packet says so rather than implying the database enforces it.

## 5. Prechecks — run these first, and read the output

```bash
# 1. Every earlier migration is applied. `0005` declares a foreign key into
#    `isaac_experiments`, which `0001` creates.
psql -Atc "select version from isaac_schema_migrations order by version"
#    EXPECT: 0001_experiments, 0002_runs, 0003_revisions, 0004_submissions
#
#    IF 0003 AND 0004 ARE ABSENT, STOP AND READ SECTION 6. They are owner-approved
#    and, as of this writing, NOT applied to the hosted database — and `--apply` has
#    no per-version option, so it would apply all three at once.

# 2. The table does not already exist.
psql -Atc "select count(*) from information_schema.tables
           where table_schema='public' and table_name='isaac_run_projection'"
#    EXPECT: 0

# 3. The runner agrees, and applies nothing while saying so.
python scripts/db_migrate.py --plan
#    EXPECT (once 0003/0004 are applied): pending: 0005_run_projection
#    EXPECT (if they are not):            pending: 0003_revisions, 0004_submissions, 0005_run_projection
#
#    This is the SAME check as precheck 1, read from the runner instead of from the
#    table. Both are listed because they fail differently: precheck 1 catches a
#    bookkeeping row that exists without its table, and this catches a migration
#    file the runner cannot see.

# 4. Baseline counts, so the postchecks can be a comparison rather than an assertion.
psql -Atc "select count(*) from records"
psql -Atc "select count(*) from isaac_experiments"
psql -Atc "select count(*) from isaac_runs"

# 5. The engine build, recorded because the CI proof runs against postgres:18.
psql -Atc "select version()"
```

**Precheck 4 is not optional and its two `records`/`isaac_experiments` halves have been
skipped before.** `0002`'s operator report omitted exactly these, and the omission is
recorded in that packet as a gap. A count you did not take before cannot be compared
after.

## 6. The exact command — and it applies EVERY pending migration, not just this one

**READ THIS BEFORE RUNNING IT.** `db_migrate` has `--plan` and `--apply` and **no
`--only <version>`**. `--apply` applies every pending migration in lexical order. As of this
writing `0003_revisions` and `0004_submissions` are owner-approved and **not applied to the
hosted database**, so against the real hosted database this one command would apply **three**
migrations, two of which have their own packets and their own operator step.

That is not a hidden hazard — precheck 1 is what catches it, and it is why the precheck comes
first. Two acceptable sequences, and no third:

1. **Apply `0003` and `0004` first**, from their own packets; confirm precheck 1 reads
   `0001, 0002, 0003, 0004`; then run the command below and expect exactly
   `applied: 0005_run_projection`.
2. **Apply all three together, deliberately**, having read all three packets, and expect
   `applied: 0003_revisions, 0004_submissions, 0005_run_projection`. Report the postchecks for
   all three.

What is NOT acceptable is running the command because this packet said to and discovering
afterwards that three migrations landed.

```bash
python scripts/db_migrate.py --apply
#    EXPECT (once 0003/0004 are applied): applied: 0005_run_projection
#    EXPECT (if they are not):            applied: 0003_revisions, 0004_submissions, 0005_run_projection
```

One transaction. The runner issues `CREATE TABLE IF NOT EXISTS isaac_schema_migrations`
once per transaction (which is what makes losing the bookkeeping table survivable), then
the two statements above, then records the version.

## 7. Postchecks — what would prove it worked

```bash
# The table, its constraints, and NO `ON DELETE`.
psql -c "\d+ isaac_run_projection"
psql -Atc "select conname, pg_get_constraintdef(oid) from pg_constraint
           where conrelid = 'isaac_run_projection'::regclass order by conname"
#    EXPECT the four NAMED constraints and the primary key to be PRESENT, and NO
#    occurrence of 'ON DELETE' or 'CASCADE' anywhere in the output.
#
#    DO NOT CHECK THE ROW COUNT. Some engines catalogue NOT NULL as pg_constraint
#    rows and some do not, so the total is engine-dependent and a count would fail
#    for a reason that has nothing to do with this migration. Check for each name:
#    isaac_run_projection_experiment_fk, _rev_non_negative, _count_non_negative,
#    _projector_known.

# Empty. This migration moves no data.
psql -Atc "select count(*) from isaac_run_projection"     # EXPECT: 0

# Idempotent.
python scripts/db_migrate.py --apply
#    EXPECT: nothing to apply (every migration is already recorded)

# Precheck 4's counts, unchanged.
psql -Atc "select count(*) from records"
psql -Atc "select count(*) from isaac_experiments"
psql -Atc "select count(*) from isaac_runs"

# The application is healthy and still durable.
curl -s <base>/api/health | jq '{mode, database}'
```

## 8. Rollback

`apps/api/isaac_api/migrations/0005_run_projection.rollback.sql`, run with
`psql -v ON_ERROR_STOP=1 -f`. Both statements in one transaction, so "the table is gone"
and "the version is no longer recorded" cannot disagree.

**The dependency is NOT the one the numbering suggests.** `isaac_run_projection`
references `isaac_experiments`, **not** `isaac_runs`. So:

- it must be rolled back before `0001`;
- it is **independent of `0002`** — rolling `0002` back while this table stands is legal,
  and leaves every claim in it describing rows that no longer exist. The four-state read
  model handles that as fallback, which is why the rollback file documents it rather than
  forbidding it.

**What rolling back costs:** every completeness claim is deleted, so every experiment
becomes NEVER PROJECTED again. The run rows are untouched, so **nothing scientific is
lost**. In the build that ships this migration the cost is **zero**, because no read
consults the table. **Dump first anyway** if a later build has a reader:

```bash
psql -c "\copy (SELECT * FROM isaac_run_projection) TO 'run-projection.csv' CSV HEADER"
```

## 8A. The Stage-2b completeness gate — a query YOU run, not a number a script prints

**Four committed documents once described this gate as "the backfill reported
`never_projected: 0`". No script prints that, and none can:** the backfill deliberately
never reads `isaac_run_projection`, because a read would make it the table's first reader
and that is the Stage-2b decision the gate exists to *precede*. An independent review
measured the gap. The gate is these two queries.

**Run them AFTER `python scripts/db_backfill_runs.py --apply` has reported
`experiments UNREADABLE: 0`, `refused: 0` and `failed: 0`.** Any non-zero there means some
experiment was not projected, and the queries below would then be describing an incomplete
pass rather than a complete one.

```sql
-- 1. NEVER PROJECTED. Must be 0.
SELECT count(*) FROM isaac_experiments e
 WHERE NOT EXISTS (SELECT 1 FROM isaac_run_projection p
                    WHERE p.experiment_id = e.experiment_id);

-- 2. STALE — a claim exists but names a different document version. Must be 0.
SELECT count(*) FROM isaac_experiments e
  JOIN isaac_run_projection p ON p.experiment_id = e.experiment_id
 WHERE p.experiment_rev        <> COALESCE((e.state ->> 'rev')::bigint, 0)
    OR p.experiment_generation <> COALESCE(e.state ->> 'generation', '');
```

**Both must be 0, and 0 for query 1 is the answer that could not be given before this
migration existed** — an experiment with genuinely no runs and an experiment never
projected both looked like zero rows in `isaac_runs`.

**A third query is worth running and is NOT a gate**, because it can be legitimately
non-zero on a live deployment: it reports claims made by the write path versus the
backfill. If every row says `backfill`, no scientist has saved anything since the backfill
ran, which is information rather than a fault.

```sql
SELECT projector, count(*) FROM isaac_run_projection GROUP BY projector;
```

**What zero on both does NOT establish:** that the ROWS are right. It establishes that a
claim exists for every experiment and that each claim names the current document. The rows
are what the claim is about, and the claim is written in the same transaction as the rows
— which is the invariant, not a measurement. A reader built on this should still fall back
to the document on any mismatch; the contract's §2.1 four-state table is what it must
implement.

## 9. Evidence, and what remains unproven — read this before approving

**Proven, against a real `postgres:18` service container in CI**
(`.github/workflows/ci.yml` → `postgres-migration`):

- forward application, in order, with `0005` last;
- the plan output naming it, and `--plan` creating no table;
- idempotence, including with the bookkeeping row deleted;
- the table set gaining **exactly nine** application-owned tables and `records` being
  byte-identical (an md5 over every row, before and after);
- **every one of the five constraints refusing what it claims to refuse**, each case
  naming the object PostgreSQL must blame — the foreign key, both non-negative CHECKs,
  the closed `projector` value set, `experiment_generation`'s NOT NULL, the primary key,
  and the parent-delete refusal;
- the rollback, in the documented order, restoring the pre-migration table set;
- the wrong-order rollback failing safely and dropping nothing.

**ONE ITEM WAS LISTED HERE AS PROVEN AND HAD NEVER EXECUTED. Recorded rather than quietly
re-listed once it did.** This section claimed *"the claim the application's own save writes,
read back from the server"* was proven in CI. It was not: the step that does it called
`exp.save_versioned(None)`, and that method takes no argument, so the job died on a
`TypeError` before the read-back, the projector assertion, the `run_count`-versus-`count(*)`
comparison and the supersede-in-place check ever ran. An independent review found the packet
asserting proof for a step that had never executed — which is the failure mode a packet
exists to prevent, appearing in the packet itself.

Two things follow, and neither is "it works now". The signature is fixed, and a local test
now makes the same API calls without Postgres so a third signature mistake cannot reach CI.
And this row stays BELOW the proven list until a green `postgres-migration` run on this
branch has executed it:

- **PENDING, NOT PROVEN:** the claim the application's own save writes, read back from the
  server and compared against the document it was projected from — the version pair, the
  projector, and `run_count` against an actual `count(*)` of `isaac_runs`, plus a second save
  superseding in place rather than appending. **Do not treat this row as evidence until a CI
  run has executed the step.**

**NOT proven, and this is the whole reason the operator's step is separate:** the CI
container is **empty**, with a two-row synthetic stand-in for `records`. So *"behaves
against the real data, the real roles and the real grants"* is unproven, exactly as it was
for `0001` through `0004`.

**Also not proven:** no agent has connected to the hosted database, and none may. Every
hosted figure in this packet will be **operator testimony**, not a captured artifact —
the same standing caveat `0002`'s report carries.

## 10. Authorization basis

`CLAUDE.md` §15's 2026-08-07 write lift covers Create Experiment persistence *"plus the
minimum supporting persistence architecture that feature requires"*, and its enumerated
table list **now names `isaac_run_projection`, added in the same change that creates the
table** (§15, "added 2026-08-19").

That ordering is the point. The list has been corrected twice — once for `isaac_runs`,
found and reported by the implementing slice; once for the five submission-lifecycle
tables, found only by an independent review. **This is the first time the sentence exists
before the table is written**, and it is stated here so a future reader can see it was not
a permission written down late.

## 11. What this packet does not cover

- **Stage 2b — moving a reader onto `isaac_runs`.** A separate reviewed slice, gated on
  the backfill having RUN in the target environment and reported `never_projected: 0`.
  That is a measurement, not a belief.
- **Removing `runs` from the experiment document.** A third decision, justified by no
  measurement in this repository. The brief that motivates it ("contract §8 D7") is cited
  by several files here and committed to none of them.
- **Running the backfill.** An operator action, against an environment an agent may not
  connect to.
- **Any change to `records`, the verification truth plane, the official validator, export
  behaviour, or Dean-owned infrastructure.**
