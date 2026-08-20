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
  module-level constants rather than asserted.
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

# 2. The table does not already exist.
psql -Atc "select count(*) from information_schema.tables
           where table_schema='public' and table_name='isaac_run_projection'"
#    EXPECT: 0

# 3. The runner agrees, and applies nothing while saying so.
python scripts/db_migrate.py --plan
#    EXPECT: pending: 0005_run_projection

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

## 6. The exact command

```bash
python scripts/db_migrate.py --apply
#    EXPECT: applied: 0005_run_projection
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
#    EXPECT four named constraints plus the primary key, and NO occurrence of
#    'ON DELETE' or 'CASCADE' anywhere in the output.

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
- the wrong-order rollback failing safely and dropping nothing;
- **the claim the application's own save writes, read back from the server** and compared
  against the document it was projected from — the version pair, the projector, and
  `run_count` against an actual `count(*)` of `isaac_runs`. Plus a second save superseding
  in place rather than appending.

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
