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

# 2. See what WOULD be applied. Applies no MIGRATION — but it is not read-only:
#    `pending_versions` opens a transaction and ensures the bookkeeping table
#    exists, so it may CREATE TABLE isaac_schema_migrations. That is idempotent
#    and harmless, and it is not nothing. (Corrected 2026-08-08; this line
#    previously read "Changes nothing", which the function's own docstring
#    contradicts.)
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

---

# Re-verification, 2026-08-08 — and why this is still unapplied

The standing authorization is conditional: apply the first hosted migration **only if the exact
current committed migration still matches the reviewed packet**. It was re-checked today.

## The migration has not drifted

`git log --follow -- apps/api/isaac_api/migrations/0001_experiments.sql` returns **one commit**,
`d4c9e08` — the commit that introduced it. The packet above was written later, in `43837b9`. So the
file has never changed since it was reviewed, and no post-review difference exists.

Checked element by element against §1 rather than by eye. All seventeen hold:

| Claim in §1 | Result |
|---|---|
| `CREATE TABLE IF NOT EXISTS isaac_schema_migrations` | ✅ |
| `CREATE TABLE IF NOT EXISTS isaac_experiments` | ✅ |
| `CREATE INDEX IF NOT EXISTS isaac_experiments_created_idx` | ✅ |
| index is on `(created_utc)` | ✅ |
| `version text PRIMARY KEY` | ✅ |
| `applied_utc timestamptz NOT NULL DEFAULT now()` | ✅ |
| `experiment_id text PRIMARY KEY` | ✅ |
| CHECK constraint named `isaac_experiments_id_shape` | ✅ |
| CHECK pattern is `'^[0-9A-Z]{26}$'` | ✅ |
| `state jsonb NOT NULL` | ✅ |
| `created_utc timestamptz NOT NULL DEFAULT now()` | ✅ |
| `updated_utc timestamptz NOT NULL DEFAULT now()` | ✅ |
| the word `records` appears **nowhere** in the statement body | ✅ |
| no `DROP` | ✅ |
| no `TRUNCATE` | ✅ |
| no `ALTER` | ✅ |
| statements separated by a line containing only `--;` (3 statements) | ✅ |

The forward file's sha256 is `69f924c72d31d3f1fbb9cf0f21ea197f67bdd1d1c79b6fd44c1228e72dcfa311` and
the rollback's is `da20f5c177dca878595e1d97e80db84518df93c0cd6dc75c71f1029952915fa5`. Quote these in
any future re-check rather than re-reading the file by eye.

**One honest note about §7 of the packet.** The packet describes the migration in structured prose —
a column-by-column table — and does **not** quote the forward SQL verbatim; its single fenced `sql`
block is the rollback. So "the migration matches the packet" means *every element the packet
describes is present and correct*, verified mechanically, rather than *a byte comparison against a
quoted original*. That is a weaker form of match than the phrase suggests, and it is worth saying so
rather than letting the checkmarks imply more.

## Why it is still unapplied: no *authorized* path from here to that database

This is not caution and it is not an oversight. **Corrected 2026-08-08:** this section previously
said *"There is no mechanism."* That was too strong, and the overstatement mattered, because it
implied a rebuild was needed when none is.

**The migration logic and both `.sql` files ARE inside the running image.** `Dockerfile:34` is
`COPY apps/api/ apps/api/`, and `.dockerignore` excludes neither `isaac_api/db_migrate.py` nor
`isaac_api/migrations/`. `MIGRATIONS_DIR` resolves relative to the installed package
(`db_migrate.py:62`), so it points at real files in the pod. What is absent is only the ~30-line
argparse wrapper in `scripts/`. An operator with cluster access can apply this today with one
`kubectl exec` and no rebuild:

```bash
kubectl -n <ns> exec deploy/<isaac> -- python -c "
import os,sys; sys.path.insert(0,'/app/apps/api')
from isaac_api import db_migrate; print(db_migrate.migrate(os.environ))"
```

**That path is not a safety bypass**, which is the reason it is safe to document: every gate lives
in the module rather than in the wrapper. `db_write.pgdatabase_gate` refuses a wrong target
(verified offline: `PGDATABASE must be exactly 'metadata_assistant' (got 'postgres')`), the
statement policy and `_FORBIDDEN_TABLES` apply identically, and the one-transaction-per-migration
behaviour is `migrate()`'s, not the CLI's.

So the three real reasons it is unapplied are:

1. **The operator *CLI wrapper* is not in the container image.** `Dockerfile:42` copies exactly one
   file out of `scripts/`: `COPY scripts/check_graphify_freshness.py`. `scripts/db_migrate.py` is
   not in the allowlist. This is an inconvenience, not a barrier — see the `kubectl exec` form above.
2. **The application never migrates itself.** Nothing in `apps/api/isaac_api/app.py` calls
   `db_migrate.migrate`, and §5 of this packet says that is deliberate: *"A pod that silently
   migrated its own production database on every rollout is precisely what this design excludes."*
3. **The agent may not reach the database from outside the cluster.** The project rule at
   `docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` blocks any connection
   originating from a laptop or from CI, and blocks requesting a kubeconfig, a port-forward, or a
   Secret. That rule is unaffected by the 2026-08-07 scope lift, which authorizes implementation and
   local/CI testing and explicitly does **not** authorize applying a migration to the hosted
   environment.

Points 1 and 2 are properties of this repository; point 3 is a rule about who may act. Together they
mean **applying `0001_experiments` is an operator action, and can only be one.**

## What CI has proven, and what it has not

`.github/workflows/ci.yml` → `postgres-migration` runs this migration against a `postgres:18` service
container on every PR, and asserts the `records` table is byte-identical across the run. That proves
the SQL is valid, idempotent, transactional, and harmless to `records` **on a clean container**.

It does **not** prove anything about the hosted database with its real data — different server
version, different extensions, different roles, different existing objects. Do not read a green
`postgres-migration` check as a hosted rehearsal.

## Consequence for Create Experiment, stated plainly

Until the migration is applied, `isaac_experiments` does not exist in the hosted database. The app
degrades honestly rather than crashing — `experiment_repository.storage_status` reports
`state: unavailable` and `durable: false` once a write has actually been attempted and failed, and
the UI derives its durability sentence from that — but **a created experiment is not durable on the
hosted deployment today.** Any demo that claims durability before the migration is applied is
claiming something untrue.

## The exact operator sequence

Unchanged from §6–§8 above. It must be run by someone who already holds a SLAC cluster context, from
a shell where the five `PG*` variables point at the database (see `docs/postgres-test-db-guide.md`).
Run the §6 prechecks, then `python scripts/db_migrate.py --apply`, then every §8 postcheck — the
record count in postcheck 1 must equal precheck 3 exactly, in either direction, or the migration has
failed its own contract.
