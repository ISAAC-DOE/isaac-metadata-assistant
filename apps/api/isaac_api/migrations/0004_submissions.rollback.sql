-- ROLLBACK for 0004_submissions.
--
-- THIS FILE IS NEVER EXECUTED BY THE APPLICATION, and it cannot be.
-- `db_migrate.load_migrations` excludes every `*.rollback.sql` by suffix, so the
-- runner never loads it; and it contains `DROP`, which
-- `db_write.WriteStatementPolicy` refuses wherever it appears. The only path that
-- runs it is a human (or CI) driving psql directly.
--
-- THE SAME HONEST DIFFERENCE `0002` AND `0003`'s ROLLBACKS DISCLOSE: the two DROPs
-- are each independently refused by the write policy, and the `DELETE` against the
-- bookkeeping table is NOT — `delete` is not a forbidden verb and
-- `isaac_schema_migrations` is an owned table. The file as a whole is still
-- refused, and the loader still never reads it.
--
-- ORDER MATTERS, TWICE OVER.
--
--   WITHIN THIS FILE: `isaac_submission_runs` holds a FOREIGN KEY into
--   `isaac_submissions`, and neither drop uses `CASCADE`, so the child goes first.
--
--   ACROSS FILES: THIS FILE MUST RUN FIRST OF ALL FOUR ROLLBACKS.
--   `isaac_submissions` references BOTH `isaac_experiments` (0001) and
--   `isaac_experiment_revisions` (0003), so `0003_revisions.rollback.sql` and
--   `0001_experiments.rollback.sql` each FAIL while these tables exist. The
--   documented full order is: 0004, then 0003, then 0002, then 0001. CI proves both
--   the failure on the wrong order and the success on the right one.
--
-- WHY THE BOOKKEEPING ROW IS DELETED AT ALL. Dropping the tables without removing
-- the row would leave the database in a state that lies: `db_migrate.migrate` skips
-- any version already recorded, so `--apply` would print "nothing to apply" while
-- the tables no longer exist.
--
-- ALL THREE STATEMENTS RUN IN ONE TRANSACTION, so "the tables are gone" and "the
-- version is no longer recorded" cannot end up disagreeing. Run it with
-- `psql -v ON_ERROR_STOP=1 -f <this file>`.
--
-- IT NAMES ONLY WHAT 0004 CREATED. Nothing from 0001, 0002 or 0003 is dropped here,
-- and `records` — the production-derived 30-row sample — is not named here and must
-- never be.
--
-- WHAT ROLLING BACK COSTS: EVERY RECORD OF WHO SUBMITTED WHAT, IRRECOVERABLY. These
-- tables are not a shadow of anything; there is no second copy anywhere. The
-- revision snapshots in 0003 survive, so the CONTENT is not lost — but the
-- declaration, its author, and its timestamp are. Dump before rolling back:
--
--     \copy (SELECT * FROM isaac_submissions) TO 'submissions.csv' CSV HEADER
--     \copy (SELECT * FROM isaac_submission_runs) TO 'submission-runs.csv' CSV HEADER
--
-- Dropping each table also drops its indexes, its foreign keys, its UNIQUE
-- constraints and all of its CHECK constraints; none needs its own statement.

BEGIN;

DROP TABLE IF EXISTS isaac_submission_runs;

DROP TABLE IF EXISTS isaac_submissions;

DELETE FROM isaac_schema_migrations WHERE version = '0004_submissions';

COMMIT;
