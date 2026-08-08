# Migration approval packet — `0001_experiments`

**Status: AWAITING APPROVAL. Nothing has been applied to any database.**
This packet exists because the standing rule is that the first hosted migration is not
applied without explicit approval. It states exactly what would run, what it would lock,
what would happen if it failed halfway, and how to undo it.

Prepared from the code on `feat/my-experiments-create` (PR #69). Every claim below is
cited; nothing is described from intent.

---

## 1. What it creates

Two tables and one index. **Nothing is altered, dropped, truncated, or renamed.**

### `isaac_schema_migrations` — bookkeeping

| Column | Type | Constraints |
|---|---|---|
| `version` | `text` | **PRIMARY KEY** |
| `applied_utc` | `timestamptz` | `NOT NULL DEFAULT now()` |

### `isaac_experiments` — the experiments this application creates

| Column | Type | Constraints |
|---|---|---|
| `experiment_id` | `text` | **PRIMARY KEY**, `CHECK (experiment_id ~ '^[0-9A-Z]{26}$')` named `isaac_experiments_id_shape` |
| `state` | `jsonb` | `NOT NULL` |
| `created_utc` | `timestamptz` | `NOT NULL DEFAULT now()` |
| `updated_utc` | `timestamptz` | `NOT NULL DEFAULT now()` |

**Index:** `isaac_experiments_created_idx` on `(created_utc)` — serves the one read this
application performs against its own table ("every experiment, oldest first"). Lookup by
id is already covered by the primary key.

**Two design choices worth reviewing rather than skimming:**

- **`text` + `CHECK`, not `char(26)`.** `char(n)` blank-pads on read — a behaviour the
  record-verification path already has to strip. A `text` column stores exactly what was
  written.
- **The whole document in one `jsonb` column, not a column per field.** The document's
  shape is owned by the truth core; a column-per-field schema here would become a second,
  drifting definition of it that no test could keep in step.

## 2. What it deliberately does not touch

**The `records` table — the production-derived 30-row sample — is not named anywhere in
the forward migration, the rollback, or the owned-table set.** It is neither read, written,
altered, nor depended upon.

That is enforced in three independent places, not merely intended:

1. `db_write.OWNED_TABLES` does not contain `records`, and any statement naming a table
   outside that set is refused.
2. `_FORBIDDEN_TABLES = ("records",)` refuses it **by identifier**, anywhere in a statement.
3. `WriteStatementPolicy` refuses `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, `REVOKE` and
   `COPY` anywhere at all.

**Layer 2 exists because layer 1 was not enough, and that is worth knowing.**
`db_write.py:231` records that `CREATE INDEX isaac_probe_idx ON records (record_id)` once
*passed* this policy, as did `CREATE TRIGGER ... ON records` — neither reads nor writes a
row, so a keyword-and-verb check let them through. A negative-control pass found it and the
identifier refusal closed it. The protection is layered because someone tried to break it.

CI additionally asserts `records` is byte-identical across a migration run.

## 3. Transaction and locking behaviour

**One transaction per migration**, with the bookkeeping row written *inside* it
(`db_migrate.py:215-236`). So "applied" and "recorded" cannot disagree: a failure part-way
rolls back the DDL *and* the bookkeeping together, and the database is left exactly as it
was.

**Locking — no user-visible contention:**

| Statement | Lock | Contention |
|---|---|---|
| `CREATE TABLE IF NOT EXISTS isaac_schema_migrations` | `ACCESS EXCLUSIVE` on a table that does not yet exist | none — nothing else can reference it |
| `CREATE TABLE IF NOT EXISTS isaac_experiments` | same | none |
| `CREATE INDEX IF NOT EXISTS isaac_experiments_created_idx` | `SHARE` on `isaac_experiments` | none — the table was created moments earlier in the same transaction and is empty |

The index is created **non-concurrently**, which normally blocks writes. Here it cannot
matter: the table is new and empty within the same transaction, so there is no existing
writer to block and no rows to scan.

**No lock of any kind is taken on `records`,** because no statement names it.

**Statement splitting** is on a line containing only `--;`, not on `;`
(`db_migrate.py:108-146`) — so a semicolon inside a string literal or comment can never
split a statement in half.

## 4. Idempotence

Every statement is `CREATE ... IF NOT EXISTS`. Re-running is a no-op even if the
bookkeeping row were lost. A second `--apply` returns `[]` (`db_migrate.py:213`).

## 5. Who can run it — and who cannot

**The application never runs this.** Nothing in `isaac_api` imports the CLI and no route
reaches `db_migrate.migrate`. A pod that silently migrated its own production database on
every rollout is precisely what this design excludes.

`--plan` is the **default**, so a bare invocation cannot change anything.

The runner refuses unless `PGDATABASE` is exactly `metadata_assistant`.

## 6. Prechecks — run these first, and read the output

```bash
# 1. Confirm the target. Must print exactly: metadata_assistant
echo "$PGDATABASE"

# 2. See what WOULD be applied. Changes nothing.
python scripts/db_migrate.py --plan

# 3. Confirm the production sample is present and its size, to compare afterwards.
psql -c "SELECT count(*) AS records_before FROM records;"

# 4. Confirm the target tables do NOT already exist (expect 0 rows).
psql -c "SELECT tablename FROM pg_tables
         WHERE tablename IN ('isaac_experiments','isaac_schema_migrations');"
```

**Do not proceed if:** `PGDATABASE` is anything other than `metadata_assistant`; `--plan`
lists a version you have not reviewed; or step 4 returns rows you did not expect (the
migration is idempotent, so this is informational rather than fatal — but know before you
run).

## 7. The exact command

```bash
python scripts/db_migrate.py --apply
```

Expected output: the single version `0001_experiments`. A second run prints nothing applied.

## 8. Postchecks

```bash
# 1. The record count must be UNCHANGED from precheck 3.
psql -c "SELECT count(*) AS records_after FROM records;"

# 2. Both tables exist.
psql -c "\d isaac_experiments"
psql -c "\d isaac_schema_migrations"

# 3. The version is recorded.
psql -c "SELECT version, applied_utc FROM isaac_schema_migrations;"

# 4. The index exists.
psql -c "SELECT indexname FROM pg_indexes WHERE tablename = 'isaac_experiments';"

# 5. Idempotence: a second run applies nothing.
python scripts/db_migrate.py --apply
```

**The migration has failed its own contract if** the record count in step 1 differs from
precheck 3 by any amount, in either direction.

## 9. Rollback

**`0001_experiments.rollback.sql` is never executed by the application and cannot be** —
every statement in it is a `DROP`, which the write policy refuses wherever it appears. The
only path that runs it is a human or CI driving `psql` directly. That is deliberate: a
rollback is an operator action, not something an app does to itself on a bad boot.

```sql
DROP TABLE IF EXISTS isaac_experiments;
DROP TABLE IF EXISTS isaac_schema_migrations;
```

Dropping `isaac_experiments` also drops its index and CHECK constraint; neither needs its
own statement. **`records` is not named and must never be.**

### What rolling back costs

**Every experiment a user created is deleted.** This is destructive to user data and is
safe only for the schema itself. Before rolling back a database that has served real users:

```
\copy (SELECT experiment_id, state FROM isaac_experiments) TO 'experiments.csv' CSV
```

### Rollback criteria — roll back if

- the record count moved (postcheck 1) — this would mean something is very wrong, and the
  cause must be understood **before** rolling back, since rollback does not restore `records`;
- the application fails to start or serve reads against the migrated database;
- a defect is found in the table shape that cannot be fixed forward.

**Do not roll back merely to "undo" a successful migration.** The tables are additive,
inert when unused, and the application already tolerates a configured-but-unmigrated
database (that is what `5b40db5` fixed). Leaving them costs nothing; dropping them destroys
user data.

## 10. What this packet does not cover

- **When to run it.** Timing is the operator's call.
- **Whether the deployment should get durable persistence at all.** That is already
  approved; this packet covers only the mechanics of the first application.
- **Any subsequent migration.** `0002` and later need their own packet.
- **Backup/restore of the wider database.** Out of scope for this application, and
  `records` is untouched regardless.
