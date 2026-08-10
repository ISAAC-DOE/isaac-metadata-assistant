# Migration approval packet — `0002_runs`

> ## STATUS: **AWAITING APPROVAL. Nothing has been applied to any database.**
>
> `0001_experiments` was applied to the hosted database by Dean on 2026-08-09
> ([evidence](evidence/hosted-0001-verification-2026-08-09.md)). **That changes nothing about this
> migration.** `0002_runs` is unapplied, and applying it to the hosted environment is the owner's
> act, not an agent's — the project rule at
> `docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` still bars any agent
> connection to that database from a laptop or from CI, and no kubeconfig, port-forward or Secret
> was requested or used in preparing this packet.
>
> **No database of any kind was contacted while writing this migration.** The machine it was
> written on has no PostgreSQL binary and no Docker (`which psql pg_ctl postgres initdb docker`
> → all not found), so the SQL below has **never been executed anywhere**. §12 says exactly what
> that leaves unproven.

Prepared against the committed files:

| File | sha256 |
|---|---|
| `apps/api/isaac_api/migrations/0002_runs.sql` | `f951cc6d2fda141160a55f6330e102c2e9d99aafc074c07a0628ac5a9f63163a` |
| `apps/api/isaac_api/migrations/0002_runs.rollback.sql` | `0206012116a443fb301e9c161b5eb2ffcfe0e99ee6f460ce83d80e30d327cdd5` |

Quote these in any future re-check rather than re-reading the files by eye. `0001`'s packet notes
that it described its migration in prose rather than quoting it, and that this made "the migration
matches the packet" a weaker claim than it sounded. **This packet quotes the forward SQL verbatim**
(§2), so a byte comparison is available.

---

## 1. Why this migration exists

Today a Run lives *inside* its experiment's `state` document — `Experiment.to_state()` serialises
`runs` as an array (`apps/api/isaac_api/workspace.py:2249`). Contract §8 DECISION D7
(`docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md:480`) rejects that shape on
the brief's own §5 requirement that Runs be independently persisted and loaded: *one jsonb document
rewritten on every autosave keystroke, containing N runs, is precisely the "single enormous object"
the brief forbids.*

This migration creates the table that makes a Run the unit of write. **It moves no data and changes
no application behaviour** — see §4.

## 2. The exact forward SQL

Commentary stripped (the runner drops `--` lines; psql treats them as comments, so the effective SQL
is identical either way). Two statements, separated by a line containing only `--;`:

```sql
CREATE TABLE IF NOT EXISTS isaac_runs (
    run_id         text        PRIMARY KEY
                   CONSTRAINT isaac_runs_id_shape
                   CHECK (run_id ~ '^[0-9A-Z]{26}$'),
    experiment_id  text        NOT NULL
                   CONSTRAINT isaac_runs_experiment_fk
                   REFERENCES isaac_experiments (experiment_id),
    ordinal        bigint      NOT NULL DEFAULT 0
                   CONSTRAINT isaac_runs_ordinal_non_negative
                   CHECK (ordinal >= 0),
    state          jsonb       NOT NULL
                   CONSTRAINT isaac_runs_state_is_object
                   CHECK (jsonb_typeof(state) = 'object'),
    rev            bigint      NOT NULL DEFAULT 0
                   CONSTRAINT isaac_runs_rev_non_negative
                   CHECK (rev >= 0),
    generation     text        NOT NULL,
    created_utc    timestamptz NOT NULL DEFAULT now(),
    updated_utc    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_runs_document_identity
    CHECK (state ->> 'id' = run_id AND state ->> 'experiment_id' = experiment_id)
);

CREATE INDEX IF NOT EXISTS isaac_runs_experiment_order_idx
    ON isaac_runs (experiment_id, ordinal, run_id);
```

**One table. One index. No `ALTER`, no `DROP`, no `TRUNCATE`, no data movement, no backfill.**

### Each element, and why it is there

| Element | Why |
|---|---|
| `run_id text PRIMARY KEY` | A run is addressed by its own id everywhere in the domain model (`Experiment.get_run`, the override map, the export fan-out). `text` + CHECK rather than `char(26)` for 0001's reason: `char(n)` blank-pads on read. |
| `CHECK isaac_runs_id_shape` | A run id is minted by `new_record_id()` (`workspace.new_run`) — the same ULID shape a record id has, `^[0-9A-Z]{26}$`, though **it is not a record id**. |
| `experiment_id text NOT NULL` | A run with no experiment is unaddressable: nothing can render, version or export it. |
| `FOREIGN KEY → isaac_experiments (experiment_id)` | Makes "a run belongs to an experiment that exists" a database fact rather than an application convention. **No `ON DELETE` clause** — see §3. |
| `ordinal bigint NOT NULL DEFAULT 0`, `CHECK >= 0` | The order key. `Experiment.sorted_runs` sorts on `(ordinal, created_utc, id)` and deliberately never on the label (`"Run 10"` sorts before `"Run 2"`). `DEFAULT 0` mirrors the dataclass. |
| `state jsonb NOT NULL` | Holds `Run.to_state()` verbatim, keeping 0001's rationale: the document's shape is owned by the truth core, and a column-per-field schema here would become a second, drifting definition of it. |
| `CHECK isaac_runs_state_is_object` | `jsonb` accepts a bare scalar or array. A run whose document is the string `"null"` would satisfy `NOT NULL` and hydrate into nothing. |
| `rev bigint NOT NULL DEFAULT 0`, `CHECK >= 0` | The run's monotonic version, written only by `Experiment._bump_changed_runs`. Promoted so a later per-run compare-and-swap compares a typed column instead of `(state ->> 'rev')::bigint`, which is what 0001's experiment-level predicate has to do. |
| `generation text NOT NULL`, **no default** | The per-run opaque nonce that makes a delete→recreate distinguishable at rev 0. No default on purpose: an empty generation is meaningless and `Run.__post_init__` guarantees a non-empty one, so a writer that omits it has a bug and should be told. |
| `created_utc` / `updated_utc timestamptz NOT NULL DEFAULT now()` | Server-side **row** timestamps, exactly as in 0001. They are **not** the document's own `created_utc`/`updated_utc` strings, which stay inside `state`. Easy to conflate; stated so nobody has to guess. |
| `CHECK isaac_runs_document_identity` | Promoting a field out of a document creates exactly one new failure mode — the two copies disagreeing. This closes it for the two identity keys. **Legacy-tolerant by construction**: `->>` yields NULL for an absent key and a CHECK passes unless it is FALSE, so a document *missing* `id` is admitted while a document carrying the *wrong* `id` is refused. |
| `INDEX (experiment_id, ordinal, run_id)` | One index doing three jobs: the experiment-scoped list; the ordinal sort within it; and the parent-side check the foreign key performs on every delete of an experiment row (an unindexed referencing column makes that a sequential scan of every run in the deployment). |

### Why any column is promoted out of the document at all

Two reasons, and the second is the one that forces the hand:

1. `experiment_id` must be a real foreign key and `ordinal` must be indexable. Neither is
   expressible over a jsonb blob without an expression index and a cast.
2. **`ALTER` is refused by the write policy** (`db_write._FORBIDDEN_KEYWORDS`, `db_write.py:202-217`).
   A column omitted here cannot be added later without either changing that policy or creating a
   second table. **This cuts both ways and is a cost, not only a justification: a column included
   here and later found wrong cannot be dropped either.**

### What is *not* enforced by the database, stated plainly

`ordinal`, `rev` and `generation` are **writer-maintained projections** of the document. They are
deliberately *not* covered by the identity CHECK, because each would need a cast
(`(state ->> 'rev')::bigint`) and a cast inside a CHECK raises on malformed text instead of returning
false — trading a clean constraint violation for a cast error. If a future writer sets a column and
the document inconsistently, the database will not catch it. The two **identity** keys are covered,
because a disagreement there means the row names a different run.

## 3. The foreign key refuses a parent delete — and that is a decision

**No `ON DELETE` clause is written, so the action is the SQL default `NO ACTION`, which for this
non-deferrable constraint behaves exactly as `RESTRICT`:** deleting an `isaac_experiments` row that
still has runs is **refused by the database**.

Two independent reasons, plus one disclosure:

- **`ON DELETE CASCADE` turns one statement into an unbounded silent multi-row destruction.**
  `DELETE FROM isaac_experiments` already passes the write policy (`delete` is not a forbidden verb
  and the table is owned), so CASCADE would put "destroy every run in the deployment" one statement
  away. Refusing is the behaviour the rest of this write path is built around.
- **It is the reversible choice.** A future delete path can delete runs explicitly and then the
  experiment, with no schema change. Going the other way — CASCADE back to RESTRICT — needs an
  `ALTER`, which the policy refuses.
- **Disclosure: `ON DELETE CASCADE` is also unwritable under the current statement policy.**
  Measured, not assumed: the tokenizer reads the `delete` following `on` as naming a table it does
  not own and refuses the statement. The design argument stands on its own, but you should not be
  told a constraint was a free choice when it was also forced.

**Consequence for you to accept or reject:** if you want cascading deletes, this is the moment. It
cannot be changed later without a policy change and a new table.

## 4. What it deliberately does *not* do

**No application code writes or reads `isaac_runs`.** The nine statements this application can issue
are module-level constants (`db_write.Q_*`, `db_migrate.Q_*`, `experiment_repository.Q_*`) and none
names this table. So the application behaves **identically** with 0002 applied and with 0002
unapplied. Both directions are proven — see §6.

`db_write.OWNED_TABLES` gains `isaac_runs`, because the statement policy consults that set and a
`CREATE` naming an unlisted table is refused. **Listing it grants nothing on its own**; it is the
deliberate, reviewable act that lets a later slice write the table.

**Five tables named by contract §8 D7 are deliberately NOT created here:**
`isaac_experiment_revisions`, `isaac_run_revisions`, `isaac_assets`, `isaac_run_assets`,
`isaac_submissions`. Each belongs to the slice that needs it. An over-stuffed migration is harder to
approve, harder to roll back, and creates tables nothing will write for months. A test pins their
absence.

**The `records` table — the production-derived 30-row sample — is not named anywhere** in the
forward migration, the rollback, or the owned-table set. It is neither read, written, altered, nor
referenced in a constraint. Three independent guards, as in 0001: `OWNED_TABLES` excludes it;
`_FORBIDDEN_TABLES = ("records",)` refuses it *by identifier* anywhere in a statement; and the
policy refuses `DROP`/`TRUNCATE`/`ALTER`/`GRANT`/`REVOKE`/`COPY` anywhere at all. A fourth,
file-level guard reads every committed `.sql` off disk and asserts the identifier appears in no
statement.

## 5. Transaction and locking behaviour

**One transaction per migration**, with the bookkeeping row written *inside* it
(`db_migrate.py:215-236`), so "applied" and "recorded" cannot disagree. With two committed
migrations the runner commits **twice**, not once — pinned by test.

### Locks, against a table that already has rows

`isaac_experiments` **is not empty** on the hosted database: 0001 is applied and at least one
experiment has been created through the hosted UI. So this is not the "everything is brand new"
analysis 0001 could give.

| Statement | Lock taken | Held for | Contention |
|---|---|---|---|
| `CREATE TABLE IF NOT EXISTS isaac_runs (…)` | `ACCESS EXCLUSIVE` on `isaac_runs` — a table that does not yet exist | the transaction | **none** on the new table: nothing else can reference it |
| the same statement's `REFERENCES isaac_experiments` | **`SHARE ROW EXCLUSIVE` on `isaac_experiments`** | the transaction | **this is the one lock that can block.** It conflicts with other DDL and with `SHARE ROW EXCLUSIVE`/`EXCLUSIVE`/`ACCESS EXCLUSIVE` — but **not** with ordinary `INSERT`/`UPDATE`/`DELETE` (`ROW EXCLUSIVE`) and **not** with `SELECT`. So concurrent application writes and reads proceed. |
| `CREATE INDEX IF NOT EXISTS … ON isaac_runs` | `SHARE` on `isaac_runs` | the transaction | **none** — the table was created moments earlier in the same transaction and is empty |
| — | **no lock of any kind on `records`** | — | no statement names it |

**Duration.** Both statements are catalogue operations over an empty table. There is no table
rewrite, no index build over existing rows, and no validation scan of `isaac_experiments` — a new
FK validates the *child* rows, and there are none. The expected hold time is milliseconds.
**`Q_SET_LOCK_TIMEOUT` bounds the wait at 3000 ms and `Q_SET_STATEMENT_TIMEOUT` bounds execution at
15000 ms** (`db_write.py:134-135`, `SET LOCAL`, so they expire with the transaction). If the FK's
lock on `isaac_experiments` cannot be acquired within 3 s — because something else holds conflicting
DDL — **the migration fails and rolls back cleanly rather than queueing**, which is the behaviour you
want: a lock queue on `isaac_experiments` would stall the application's own writes behind it.

**This locking analysis is reasoned from PostgreSQL's documented lock modes, not measured.** No
`pg_locks` observation was taken, here or anywhere.

**Statement splitting** is on a line containing only `--;`, not on `;` (`db_migrate.py:108-161`), so
a semicolon inside the `CHECK` regex literal can never split a statement in half. That regex also
contains a `$`; the dollar-quote refusal is narrow enough not to trip on it, pinned by test.

## 6. Idempotence and legacy compatibility

**Idempotent, twice over.** Both statements are `CREATE … IF NOT EXISTS`, and the bookkeeping table
skips a recorded version. Either alone makes a re-run a no-op; both means losing the bookkeeping row
does not break the runner. CI applies twice, then deletes every bookkeeping row and applies again,
and diffs `information_schema.columns` across all three.

**The application runs unchanged with 0002 applied AND unapplied**, proven in three places:

1. *Unapplied, statically* — no statement the application can issue names `isaac_runs`, measured
   over the module-level constant set rather than asserted
   (`test_0002_is_inert_for_this_build_no_statement_names_isaac_runs`).
2. *Unapplied, behaviourally against a real engine* — CI applies **0001 only**, then creates, reads
   and lists an experiment through the real HTTP surface and asserts `/api/health` still reports
   `durable: true`. **This is the hosted deployment's exact state today**, and the state of every
   deployment between merging this migration and your applying it.
3. *Applied, behaviourally against a real engine* — after the full apply, CI runs the whole durable
   repository exercise (create, read-back, list, pod-restart hydration, tutorial refusal, the
   compare-and-swap cases, the wedge recovery) and then asserts **`isaac_runs` is still empty**.

## 7. Who can run it — and who cannot

**The application never runs migrations.** Nothing in `isaac_api` imports the operator CLI and no
route reaches `db_migrate.migrate`. A pod that silently migrated its own production database on
every rollout is precisely what this design excludes.

`--plan` is the **default**, so a bare invocation cannot change anything. The runner refuses unless
`PGDATABASE` is exactly `metadata_assistant`, and re-verifies server-side with `current_database()`.

`scripts/db_migrate.py` is **not in the container image** (`Dockerfile:42` copies exactly one file
out of `scripts/`), but the migration logic and both `.sql` files **are** — so an operator with
cluster access can apply this with one `kubectl exec` and no rebuild, exactly as documented in
0001's packet:

```bash
kubectl -n <ns> exec deploy/<isaac> -- python -c "
import os,sys; sys.path.insert(0,'/app/apps/api')
from isaac_api import db_migrate; print(db_migrate.migrate(os.environ))"
```

That is not a safety bypass: every gate lives in the module, not in the wrapper.

## 8. Prechecks — run these first, and read the output

```bash
# 1. Confirm the target. Must print exactly: metadata_assistant
echo "$PGDATABASE"

# 2. Confirm 0001 is applied and 0002 is not. Expect exactly one row: 0001_experiments.
psql -c "SELECT version, applied_utc FROM isaac_schema_migrations ORDER BY version;"

# 3. See what WOULD be applied. Expect: pending: 0002_runs
#    Applies no MIGRATION — but it is NOT read-only: `pending_versions` opens a
#    transaction and ensures the bookkeeping table exists.
python scripts/db_migrate.py --plan

# 4. Confirm the production sample is present and its size, to compare afterwards.
psql -c "SELECT count(*) AS records_before FROM records;"

# 5. Confirm how many experiment rows exist, to compare afterwards.
psql -c "SELECT count(*) AS experiments_before FROM isaac_experiments;"

# 6. Confirm the target table does NOT already exist (expect 0 rows).
psql -c "SELECT tablename FROM pg_tables WHERE tablename = 'isaac_runs';"

# 7. Confirm nothing is holding conflicting DDL on isaac_experiments (expect 0 rows).
#    The FK takes SHARE ROW EXCLUSIVE on it and the lock_timeout is 3s.
psql -c "SELECT pid, mode, granted FROM pg_locks l
         JOIN pg_class c ON c.oid = l.relation
         WHERE c.relname = 'isaac_experiments' AND l.mode LIKE '%Exclusive%';"
```

**Do not proceed if:** `PGDATABASE` is anything other than `metadata_assistant`; step 2 does not show
`0001_experiments`; step 3 lists a version you have not reviewed; or step 7 returns a granted
exclusive lock held by something else.

## 9. The exact command

```bash
python scripts/db_migrate.py --apply
```

Expected output: `applied: 0002_runs` — **not** `0001_experiments, 0002_runs`. If you see 0001 in
that list, the bookkeeping row for 0001 is missing from this database and you should stop and find
out why before continuing. (The apply is still safe — `CREATE … IF NOT EXISTS` — but a missing
bookkeeping row means something you did not expect happened to this database.)

## 10. Postchecks — what would prove it worked

```bash
# 1. The record count must be UNCHANGED from precheck 4. This is the one that matters.
psql -c "SELECT count(*) AS records_after FROM records;"

# 2. The experiment count must be UNCHANGED from precheck 5.
psql -c "SELECT count(*) AS experiments_after FROM isaac_experiments;"

# 3. The table exists with the columns and constraints this packet describes.
psql -c "\d isaac_runs"

# 4. The index exists on (experiment_id, ordinal, run_id).
psql -c "SELECT indexdef FROM pg_indexes WHERE tablename = 'isaac_runs';"

# 5. The version is recorded.
psql -c "SELECT version, applied_utc FROM isaac_schema_migrations ORDER BY version;"

# 6. It is empty, and stays empty: no application code writes it.
psql -c "SELECT count(*) FROM isaac_runs;"

# 7. Idempotence: a second run applies nothing.
python scripts/db_migrate.py --apply

# 8. The application is unaffected. Through the hosted UI:
#    /api/health -> experiment_storage {backend: "postgres", durable: true, state: "durable"}
#    create an experiment; it still works; My Experiments still lists it.
```

**The migration has failed its own contract if** the count in step 1 differs from precheck 4 by any
amount in either direction, or the count in step 2 differs from precheck 5.

## 11. Rollback

`0002_runs.rollback.sql`, run by a human or CI with psql. The application cannot run it:
`load_migrations` excludes every `*.rollback.sql` by suffix, and the file contains a `DROP`, which
the write policy refuses.

```sql
BEGIN;

DROP TABLE IF EXISTS isaac_runs;

DELETE FROM isaac_schema_migrations WHERE version = '0002_runs';

COMMIT;
```

```bash
psql -v ON_ERROR_STOP=1 -f apps/api/isaac_api/migrations/0002_runs.rollback.sql
```

Dropping `isaac_runs` also drops its index, its foreign key and all five CHECK constraints; none
needs its own statement.

**Three things about this rollback that differ from 0001's, each deliberate:**

- **It deletes its own bookkeeping row.** Without that, `--apply` would print "nothing to apply"
  over a table that no longer exists, and no amount of re-running would bring it back — a silent,
  unrecoverable trap. 0001's rollback avoids the problem by dropping the bookkeeping table outright,
  which is not available here because 0001 may still be applied.
- **Both statements run in one transaction**, so "dropped" and "unrecorded" cannot disagree.
- **It contains one statement the write policy would accept on its own** (the `DELETE`, against an
  owned table). The file as a whole is still refused because of the `DROP`, and the loader still
  never reads it — but "every statement here is independently refused" is true of 0001's rollback
  and is **not** true of this one. Pinned by test so the claim cannot drift.

### ORDER MATTERS if you are rolling back both migrations

`0001_experiments.rollback.sql` drops `isaac_experiments` **without `CASCADE`**, and `isaac_runs`
references it. **Rolling back 0001 first FAILS.** That is the safe failure — nothing is destroyed,
and with `ON_ERROR_STOP=1` psql stops before the second `DROP` — but an operator reaching for a
rollback is not in a mood to debug a dependency error. **Roll back 0002 first, then 0001.** CI proves
both the wrong-order failure and the right-order success.

### What rolling back costs

**In the build that ships this migration: nothing.** No application code writes `isaac_runs`, so
there is no data to lose. **That stops being true the moment the run write path lands.** From then
on, dump first:

```
\copy (SELECT run_id, experiment_id, state FROM isaac_runs) TO 'runs.csv' CSV
```

### Roll back if

- the count in postcheck 1 or 2 moved — understand the cause **before** rolling back, since rollback
  does not restore either table;
- the application fails to start or serve reads against the migrated database;
- a defect is found in the table shape that cannot be fixed forward — and note that under this write
  policy, "fixed forward" means a **new table**, not an `ALTER`.

**Do not roll back merely to "undo" a successful migration.** The table is additive, inert while
nothing writes it, and the application already tolerates a configured-but-unmigrated database.

## 12. What remains unproven — read this before approving

- **The SQL has never been executed.** Not on a laptop, not in CI, not anywhere. The machine this
  was written on has no PostgreSQL and no Docker. Everything asserted about the constraints'
  *behaviour* in §2 and §3 is reasoned from PostgreSQL's documentation and from the constraint text;
  it becomes evidence only when the `postgres-migration` job runs.
- **CI has not been observed either.** This work was not pushed, so no `postgres-migration` run
  exists for it. The job's new steps are *specified* here, not *witnessed*.
- **CI proving this against `postgres:18` is NOT the same as proving it against the hosted
  database.** Different server build, different extensions, different roles, different existing
  objects, and — the part CI structurally cannot model — **real data**. CI removes the "is this
  valid SQL / is it idempotent / does it touch other tables / do the constraints fire" class of
  risk. It does not remove the "does it behave correctly against the hosted database as it actually
  is" class. Only you applying it, deliberately, resolves that. Do not read a green
  `postgres-migration` check as a hosted rehearsal.
- **Version parity is documented, not measured.** `docs/postgres-test-db-guide.md` states the SLAC
  cluster runs PostgreSQL 18 and the service container is pinned to 18. This environment cannot
  reach the hosted server to confirm the running version.
- **The locking analysis in §5 is reasoned, not measured.** No `pg_locks` observation exists.
- **`isaac_experiments` is not empty on the hosted database, and its contents are unknown here.**
  The FK validates child rows and there are none, so no scan of the parent is expected — but "no
  scan is expected" is an inference from how PostgreSQL adds a foreign key, not an observation of
  this database.
- **The `ordinal`/`rev`/`generation` columns are unenforced projections** of the document (§2). No
  test and no constraint will catch a future writer that sets one inconsistently.
- **Nothing here is a schema for run *revisions*, assets, or submissions.** Contract §8 D7's other
  five tables are deferred and will each need their own migration and their own packet.

## 13. What this packet does not cover

- **When to run it.** Timing is yours.
- **Whether Runs should be relational at all.** That is contract §8 DECISION D7, already recorded;
  this packet covers the mechanics.
- **The run write path.** No code writes this table. The upsert, the per-run compare-and-swap, and
  the backfill of runs out of the experiment document are later slices, each independently reviewed.
- **Any subsequent migration.** `0003` and later need their own packets.
- **Backup/restore of the wider database.** Out of scope, and `records` is untouched regardless.
