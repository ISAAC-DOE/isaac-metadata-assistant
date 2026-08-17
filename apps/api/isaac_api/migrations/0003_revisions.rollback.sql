-- ROLLBACK for 0003_revisions.
--
-- THIS FILE IS NEVER EXECUTED BY THE APPLICATION, and it cannot be. Two
-- independent reasons: `db_migrate.load_migrations` excludes every `*.rollback.sql`
-- by suffix, so the runner never loads it; and it contains `DROP`, which
-- `db_write.WriteStatementPolicy` refuses wherever it appears. The only path that
-- runs it is a human (or CI) driving psql directly. That is the intent — a rollback
-- is an operator action, taken deliberately, not something an app can do to itself
-- on a bad boot.
--
-- AS WITH `0002_runs.rollback.sql`, AND FOR THE SAME REASON, "every statement here
-- is independently refused by the write policy" is TRUE OF THE THREE DROPS AND NOT
-- OF THE `DELETE`: `delete` is not a forbidden verb and `isaac_schema_migrations`
-- is an owned table, so that one statement would pass the policy on its own. The
-- file as a whole is still refused, and the loader still never reads it. A reader
-- should not infer the stronger property from the shared filename.
--
-- ORDER MATTERS, TWICE OVER.
--
--   WITHIN THIS FILE: `isaac_run_revisions` and `isaac_revision_changes` both hold
--   a FOREIGN KEY into `isaac_experiment_revisions`, and none of these drops uses
--   `CASCADE`, so the two children must go first. They are dropped in reverse
--   dependency order below.
--
--   ACROSS FILES: `isaac_submissions` (created by `0004_submissions`) holds a
--   FOREIGN KEY into `isaac_experiment_revisions`, so THIS FILE FAILS while 0004 is
--   applied. Roll back 0004 first, then this, then 0002, then 0001. CI proves both
--   the failure and the correct order.
--
-- WHY THE BOOKKEEPING ROW IS DELETED AT ALL. Dropping the tables without removing
-- the row would leave the database in a state that lies: `db_migrate.migrate` skips
-- any version already recorded, so `--apply` would print "nothing to apply" while
-- the tables no longer exist, and no amount of re-running would bring them back.
--
-- ALL FOUR STATEMENTS RUN IN ONE TRANSACTION, so "the tables are gone" and "the
-- version is no longer recorded" cannot end up disagreeing. Run it with
-- `psql -v ON_ERROR_STOP=1 -f <this file>`.
--
-- IT NAMES ONLY WHAT 0003 CREATED. `isaac_experiments`, `isaac_runs` and
-- `isaac_schema_migrations` are not dropped here, and `records` — the
-- production-derived 30-row sample — is not named here and must never be.
--
-- WHAT ROLLING BACK COSTS: THE ENTIRE SUBMISSION HISTORY, IRRECOVERABLY. Unlike
-- `isaac_runs`, these tables are NOT a shadow of anything — the experiment document
-- carries no revision history, and `Experiment.to_state()` never will (see
-- 0003_revisions.sql's opening note on why it cannot). Dropping them destroys the
-- only copy. Dump before rolling back:
--
--     \copy (SELECT * FROM isaac_experiment_revisions) TO 'revisions.csv' CSV HEADER
--     \copy (SELECT * FROM isaac_run_revisions) TO 'run-revisions.csv' CSV HEADER
--     \copy (SELECT * FROM isaac_revision_changes) TO 'changes.csv' CSV HEADER
--
-- Dropping each table also drops its indexes, its foreign keys and all of its CHECK
-- constraints; none needs its own statement.

BEGIN;

DROP TABLE IF EXISTS isaac_revision_changes;

DROP TABLE IF EXISTS isaac_run_revisions;

DROP TABLE IF EXISTS isaac_experiment_revisions;

DELETE FROM isaac_schema_migrations WHERE version = '0003_revisions';

COMMIT;
