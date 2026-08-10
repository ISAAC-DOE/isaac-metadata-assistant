-- ROLLBACK for 0002_runs.
--
-- THIS FILE IS NEVER EXECUTED BY THE APPLICATION, and it cannot be. Two
-- independent reasons: `db_migrate.load_migrations` excludes every `*.rollback.sql`
-- by suffix, so the runner never loads it; and it contains a `DROP`, which
-- `db_write.WriteStatementPolicy` refuses wherever it appears. The only path that
-- runs it is a human (or CI) driving psql directly. That is the intent — a
-- rollback is an operator action, taken deliberately, not something an app can do
-- to itself on a bad boot.
--
-- ONE HONEST DIFFERENCE FROM `0001_experiments.rollback.sql`, STATED RATHER THAN
-- LEFT TO BE DISCOVERED. Every statement in that file is a `DROP`, so every
-- statement in it is independently refused by the write policy. This file also
-- contains a `DELETE` against the bookkeeping table, and that statement WOULD pass
-- the policy on its own (`delete` is not a forbidden verb and
-- `isaac_schema_migrations` is an owned table). The file as a whole is still
-- refused — the splitter yields it as one chunk containing the `DROP` — and the
-- loader still never reads it. But "every statement here is independently
-- refused" is true of 0001 and is NOT true of this file, and a reader should not
-- infer the stronger property from the shared filename.
--
-- WHY THE BOOKKEEPING ROW IS DELETED AT ALL. Dropping the table without removing
-- the row would leave the database in a state that lies: `db_migrate.migrate`
-- skips any version already recorded, so `--apply` would print "nothing to apply"
-- while `isaac_runs` no longer exists, and no amount of re-running would bring it
-- back. 0001's rollback avoids this by dropping the bookkeeping table outright,
-- which is not available here because 0001 may still be applied.
--
-- BOTH STATEMENTS RUN IN ONE TRANSACTION, so "the table is gone" and "the version
-- is no longer recorded" cannot end up disagreeing. Run it with
-- `psql -v ON_ERROR_STOP=1 -f <this file>`.
--
-- ORDER MATTERS IF YOU ARE ROLLING BACK BOTH MIGRATIONS. `isaac_runs` holds a
-- FOREIGN KEY to `isaac_experiments`, so `0001_experiments.rollback.sql` — which
-- drops `isaac_experiments` WITHOUT `CASCADE` — FAILS while this table exists.
-- Roll back 0002 first, then 0001. CI proves both the failure and the correct
-- order.
--
-- IT NAMES ONLY WHAT 0002 CREATED. `isaac_experiments` is not dropped here (it is
-- 0001's), and `records` — the production-derived 30-row sample — is not named
-- here and must never be.
--
-- WHAT ROLLING BACK COSTS: every run row is deleted. In the build that ships this
-- migration that cost is ZERO, because no application code writes this table yet.
-- That will stop being true the moment the run write path lands; from then on,
-- dump before rolling back:
--
--     \copy (SELECT run_id, experiment_id, state FROM isaac_runs) TO 'runs.csv' CSV
--
-- Dropping `isaac_runs` also drops `isaac_runs_experiment_order_idx`, the foreign
-- key and all five CHECK constraints with it; none needs its own statement.

BEGIN;

DROP TABLE IF EXISTS isaac_runs;

DELETE FROM isaac_schema_migrations WHERE version = '0002_runs';

COMMIT;
