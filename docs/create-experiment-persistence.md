# Create Experiment — durable persistence

**Status: implemented and tested. NOT applied to the hosted database.**
Applying the migration is the owner's act. This document is what he reviews first.

---

## 1. What was authorized, and what was not

Authorized (2026-08-07, narrowly): durable Create Experiment persistence using the
existing app-owned PostgreSQL database, plus the minimum supporting persistence
architecture that feature requires.

Not authorized, and not done:

- modifying, reading, altering or migrating the `records` table — the
  production-derived 30-row sample;
- any change to the verification truth plane, `db_provider`, `db_recon`, or the
  official validator/export behaviour;
- any Dean-owned infrastructure change;
- destructive migration, `DROP` / `TRUNCATE` / `ALTER` of anything, or broad schema
  cleanup;
- **applying the migration to the hosted environment.** No SLAC database was
  contacted. No kubeconfig, port-forward or Secret was requested or used.

---

## 2. The migration

File: `apps/api/isaac_api/migrations/0001_experiments.sql`
Rollback: `apps/api/isaac_api/migrations/0001_experiments.rollback.sql`
Runner: `apps/api/isaac_api/db_migrate.py` · Operator CLI: `scripts/db_migrate.py`

Statements are separated by a line that is exactly `--;` (a SQL comment, so each
file stays valid runnable SQL for review with psql). Splitting on a bare `;` would
cut a statement in half inside the `CHECK` regex below.

### Exact SQL

```sql
CREATE TABLE IF NOT EXISTS isaac_schema_migrations (
    version      text        PRIMARY KEY,
    applied_utc  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS isaac_experiments (
    experiment_id  text        PRIMARY KEY
                   CONSTRAINT isaac_experiments_id_shape
                   CHECK (experiment_id ~ '^[0-9A-Z]{26}$'),
    state          jsonb       NOT NULL,
    created_utc    timestamptz NOT NULL DEFAULT now(),
    updated_utc    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS isaac_experiments_created_idx
    ON isaac_experiments (created_utc);
```

### Tables and columns created

| Object | Type | Purpose |
|---|---|---|
| `isaac_schema_migrations` | table | Migration bookkeeping. One row per applied version. |
| `isaac_schema_migrations.version` | `text` PK | The migration filename stem, e.g. `0001_experiments`. |
| `isaac_schema_migrations.applied_utc` | `timestamptz` | When it was applied. |
| `isaac_experiments` | table | One row per experiment **this application created**. |
| `isaac_experiments.experiment_id` | `text` PK, CHECK | The ULID. `text` not `char(26)` deliberately — `char(n)` blank-pads on read, which the verification path already has to strip. |
| `isaac_experiments.state` | `jsonb` NOT NULL | The same JSON document the filesystem repository writes to `experiment.json` (`workspace.Experiment.to_state()`). Stored whole rather than as a column per field, because the document's shape is owned by the truth core and a column schema here would become a second, drifting definition of it. |
| `isaac_experiments.created_utc` | `timestamptz` | Row creation. |
| `isaac_experiments.updated_utc` | `timestamptz` | Last upsert. |
| `isaac_experiments_created_idx` | index | The one read the app performs: every experiment, oldest first. |

Nothing else is created. No table that this application did not create is named
anywhere in the migration.

### Idempotence

Twice over, and both halves are proven in CI:

1. The bookkeeping table skips a version already recorded.
2. Every statement is `CREATE ... IF NOT EXISTS`, so re-running is a no-op **even
   if the bookkeeping row is lost**. CI deletes the bookkeeping rows and re-applies,
   then diffs `information_schema.columns` to prove the schema did not move.

One transaction per migration, with the bookkeeping row written inside it — so
"applied" and "recorded" cannot disagree.

---

## 3. Rollback strategy

`apps/api/isaac_api/migrations/0001_experiments.rollback.sql`:

```sql
DROP TABLE IF EXISTS isaac_experiments;
DROP TABLE IF EXISTS isaac_schema_migrations;
```

- **The application cannot run it.** Every statement is a `DROP`, and
  `db_write.WriteStatementPolicy` refuses `DROP` wherever it appears. The only way
  to run it is a human (or CI) driving psql deliberately. That is the intent: a
  rollback is an operator action, not something an app does to itself on a bad boot.
- **It names only tables `0001` created.** `records` is not named and must never be.
- **It destroys user data.** Every experiment a person created is deleted. Before
  running it against a database that has served real users, dump first:

  ```
  \copy (SELECT experiment_id, state FROM isaac_experiments) TO 'experiments.csv' CSV
  ```

- Dropping `isaac_experiments` drops its index and CHECK constraint with it.

---

## 4. Verification plan

### Already run, here

- Backend suite: **2787 passed, 2 skipped** (`pytest -q`), with **no** `PGHOST`, so
  the filesystem fallback is what the whole suite exercises.
- Frontend suite: **3145 passed / 126 files**.
- `tsc -b`: exit 0.
- `apps/api/tests/test_experiment_repository.py`: **68 tests** covering the route,
  the seam, the write path, the isolation refusals and the migration runner —
  **against an in-process fake driver**, which proves the shape and not the SQL.

### Specified in CI, and NOT YET EXECUTED — `.github/workflows/ci.yml` → `postgres-migration`

**Read the heading literally.** An earlier revision of this section was titled
*"Already run, in CI"*, and that was false: the job is new on this branch, the
branch had not been pushed when it was written, and **this job has never run**.
The steps below are what it is written to do, not what it has been observed doing.
Nothing in this section may be quoted as a result until a run exists.

The same applies to the version: a `postgres:18` service container is *pinned*, and
whether the hosted server is really 18 is a separate question answered below.

A `postgres:18` service container. `docs/postgres-test-db-guide.md:18` states the
SLAC cluster runs Postgres 18, so the version is **documented parity, not measured
parity** — this environment cannot reach the hosted server to confirm the running
version.

1. `--plan` reports `0001_experiments` and creates no application table.
2. Apply. Assert `applied: 0001_experiments`.
3. Apply again. Assert it is a no-op, and that `information_schema.columns` is
   unchanged. Then delete the bookkeeping rows, apply again, assert unchanged.
4. Diff `information_schema.tables` before and after: exactly
   `isaac_experiments isaac_schema_migrations` added, nothing removed.
5. A stand-in `records` table (synthetic rows, same shape as
   `db_provider.Q_RECORD_PAGE`) is seeded **before** the migration and asserted
   byte-identical after.
6. The durable repository end to end against the real engine: create, read the row
   back, `rmtree` the workspace to simulate a pod restart, and prove the list and
   the detail read still answer. Then open a worked-example session, prove the
   create is refused with 409, and prove the database gained nothing.
7. Run the documented rollback with psql; assert the table set returns to its
   pre-migration state and `records` is still byte-identical.

8. The application's own `records` digest check, taken **after** the repository
   step has run — so "the sample is untouched" covers the running write path and
   not only the DDL.

Two further guards live in the default `test` job: it asserts `PGHOST` is unset and
that `repository()` therefore selects the filesystem backend with `durable: false`.
That keeps the fallback covered by construction rather than by omission.

### Negative controls — run 2026-08-07, and one of them found a real defect

Every guard below was verified by **breaking it on purpose**, running the tests,
recording the result, and reverting. A control that produces zero failures is a
gap, not a pass.

| # | Mutation | Failures | Verdict |
|---|---|---|---|
| a | Create button rendered but not wired to the API | 3 | caught |
| b1 | tutorial gate removed from `workspace._ordinary_store` | 2 | caught |
| b2 | route's 409 removed; create writes into the tutorial scope | 2 | caught |
| c | client-supplied `id` accepted instead of server-minted | 2 | caught |
| d | repository selection ignores `PGHOST`, always filesystem | 5 | caught |
| e | UI claims durability while the filesystem repository is active | 2 | caught |
| f1 | migration gains `ALTER TABLE records ADD COLUMN …` | 3 | caught |
| f2 | migration gains `CREATE INDEX … ON records (record_id)` | **1** | **DEFECT — see below** |
| g | write path builds SQL by string interpolation | 3 | caught |

**Control f2 was the finding.** `WriteStatementPolicy` did not refuse it. `on` had
been deliberately kept out of `_TABLE_INTRODUCERS` so that
`INSERT … ON CONFLICT` would not be read as naming a table called `conflict` — but
that left *every* statement which attaches an object to a table unchecked, because
they all name the table after `ON`. `CREATE INDEX … ON records` and
`CREATE TRIGGER … ON records` both passed. Neither reads or writes a row, which is
why they read as harmless; both take a lock on the production-derived sample and
change its schema permanently.

The single failure it did produce came from a statement-**count** assertion
(`len(statements) == 3`), not from the policy. Had the statement replaced an
existing one rather than being appended, **nothing would have failed**.

Two independent fixes, because the first one is a grammar judgement and grammar is
where the bug lived:

1. `on` is now an introducer, with `conflict` excepted in `_table_after`;
2. `_FORBIDDEN_TABLES = ("records",)` refuses the identifier **anywhere in any
   statement, in any position**, with no syntax to get right.

Re-running control f2 after the fix produces **4 failures**, three of them from the
policy. The refusal set is pinned by
`test_the_statement_policy_refuses_anything_outside_this_applications_tables`, and a
new `test_no_committed_migration_may_reference_the_production_table` scans the
committed migration files directly.

### What CI does NOT prove

CI removes the *"is this valid PostgreSQL / is it idempotent / does it touch other
tables"* class of risk. It does **not** remove *"does this behave correctly against
the hosted database with its real 30-row dataset, its roles and its grants"*. Only
the owner applying it, deliberately, resolves that.

### What the owner should run, in order, when he chooses to apply

```
# 1. see the plan. Applies nothing.
python scripts/db_migrate.py --plan
#    expect: pending: 0001_experiments

# 2. record the table set BEFORE, so the diff is his own measurement
psql -Atc "select table_name from information_schema.tables
           where table_schema='public' order by table_name"

# 3. record the real records table's digest BEFORE
psql -Atc "select md5(string_agg(record_id || data::text, '|' order by record_id))
           from records"

# 4. apply
python scripts/db_migrate.py --apply

# 5. re-run steps 2 and 3 and diff. Expect exactly two added tables and an
#    identical records digest.

# 6. hosted smoke: GET {base}/api/health -> experiment_storage should read
#    {"configured": true, "backend": "postgres", "durable": true}
#    then create an experiment in the UI, restart the pod, and confirm it is
#    still listed.
```

---

## 5. Architecture

```
POST /api/experiments  (routes.py)
        │  knows nothing about storage
        ▼
experiment_repository.repository(env)      ← selection, environment-driven
        ├── FilesystemExperimentRepository   (no PGHOST)      durable: false
        └── PostgresExperimentRepository     (PGHOST + gate)  durable: true
                    │
                    ▼
            PostgresOrdinaryStore  ── persist() / hydrate()
                    │
                    ▼
            db_write.write_transaction  ── one connection, explicit transaction,
                                           statement policy, deterministic
                                           rollback and close
```

- **Selection** keys off `PGHOST`, the deployment's documented feature switch. No
  `PGHOST` ⇒ filesystem, which is every developer machine and every CI job except
  `postgres-migration`. `PGDATABASE` is then gated to `metadata_assistant`; a
  mismatch degrades to the filesystem and **says so** (`configured: true,
  durable: false`), rather than creating tables somewhere unintended.
- **The filesystem stays the working copy.** Postgres is the system of record for
  authoritative experiment *state*; the workspace directory is a cache of it. Every
  ordinary-scope `save()` writes through (durable write FIRST, so a failed write
  does not leave a change the reader can see); every ordinary-scope list, and a miss
  on a load, hydrates any row whose directory is gone.
- **Known limit, stated rather than discovered later:** exported ARTIFACT FILES
  (`records/<id>.json` and the evidence sidecar) live only in the workspace
  directory and are not in the database. A pod restart restores an exported
  record's state, including `record_id`, while its artifact files are gone. The
  artifact readers already tolerate that (`routes._read_artifact_json` → `None`,
  `dependencies.artifact_state` → `stale`), so it degrades to a state the app
  already handles. Persisting artifacts is a separate slice.

---

## 6. Tutorial isolation

**A worked-example session's records never reach the database.** Enforced three
times, at three levels, so one of them being wired wrongly is not enough:

1. `workspace.Experiment.save()` consults `_ordinary_store(session_id)`, which
   returns `None` for any non-`None` session before it looks at the environment.
2. `PostgresOrdinaryStore.refuse_if_not_persistable` **raises** `NotPersistable` on
   a non-`None` `session_id` — so a future caller that reaches it directly is
   refused, not merely unusual.
3. It raises on a canonical example id in **any** scope, so the five built-in
   examples cannot be made durable even from a workspace left by an older build
   that already holds them.

`POST /api/experiments` additionally refuses a `X-Isaac-Tutorial-Session` header
with `409 ordinary_scope_required`, writing nothing.

---

## 7. Safety properties of the write path

`apps/api/isaac_api/db_write.py` is a **separate** path from `db_provider` and
`db_recon`. Those two are read-only by construction (`SET TRANSACTION READ ONLY`,
server-side re-verification, a frozen statement allowlist) and are **unchanged** —
no guarantee on the verification path was weakened, reused, or relaxed.

- `OWNED_TABLES = {isaac_schema_migrations, isaac_experiments}`. `records` is
  deliberately, permanently absent.
- `WriteStatementPolicy` refuses `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, `REVOKE`,
  `COPY`, `VACUUM`, `REINDEX`, `CLUSTER` anywhere, and any statement naming a table
  outside `OWNED_TABLES`. Every statement the app issues is routed through it.
- Every value is a `%s` parameter. There is no caller-supplied SQL anywhere.
- One short-lived connection per call; `autocommit = False`; `SET LOCAL
  statement_timeout = 15s` and `lock_timeout = 3s`; a server-side
  `current_database()` check that refuses a redirected connection; rollback on any
  exception; cursor and connection closed in a `finally`.
- `application_name = isaac_app_write`, so an operator reading `pg_stat_activity`
  can tell it from `isaac_db_recon` and `isaac_record_verification`.
