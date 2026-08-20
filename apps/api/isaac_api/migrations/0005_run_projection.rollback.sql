-- ROLLBACK for 0005_run_projection.
--
-- THIS FILE IS NEVER EXECUTED BY THE APPLICATION, and it cannot be. Two
-- independent reasons: `db_migrate.load_migrations` excludes every `*.rollback.sql`
-- by suffix, so the runner never loads it; and it contains a `DROP`, which
-- `db_write.WriteStatementPolicy` refuses wherever it appears. The only path that
-- runs it is a human (or CI) driving psql directly.
--
-- As in `0002_runs.rollback.sql`, and stated rather than left to be inferred from
-- the shared filename: NOT every statement here is independently refused by the
-- write policy. The `DELETE` against the bookkeeping table would pass it on its own
-- (`delete` is not a forbidden verb and `isaac_schema_migrations` is owned). The
-- file as a whole is still refused, because the splitter yields it as one chunk
-- containing the `DROP`, and the loader still never reads it.
--
-- WHY THE BOOKKEEPING ROW IS DELETED. Dropping the table without removing the row
-- leaves a database that lies: `db_migrate.migrate` skips a version already
-- recorded, so `--apply` would print "nothing to apply" while
-- `isaac_run_projection` no longer exists, and no amount of re-running would bring
-- it back.
--
-- BOTH STATEMENTS RUN IN ONE TRANSACTION, so "the table is gone" and "the version
-- is no longer recorded" cannot disagree. Run it with
-- `psql -v ON_ERROR_STOP=1 -f <this file>`.
--
-- ORDER MATTERS IF YOU ARE ROLLING BACK SEVERAL. This table holds a FOREIGN KEY to
-- `isaac_experiments`, so `0001_experiments.rollback.sql` — which drops
-- `isaac_experiments` WITHOUT `CASCADE` — FAILS while this table exists. It holds
-- NO reference to `isaac_runs`, so rolling `0002` back does not require rolling
-- this one back first; doing so leaves this table present and every row in it
-- STALE-or-unverifiable, which the four-state read model already handles as
-- fallback. Roll back in descending version order if in doubt.
--
-- IT NAMES ONLY WHAT 0005 CREATED. `isaac_experiments`, `isaac_runs` and the five
-- submission-lifecycle tables are not named here; `records` — the
-- production-derived 30-row sample — is not named here and must never be.
--
-- WHAT ROLLING BACK COSTS: every completeness claim is deleted, and the honest
-- consequence is that every experiment becomes NEVER PROJECTED again. The run rows
-- themselves are untouched, so nothing scientific is lost — but a Stage-2b reader,
-- if one existed, would fall back to the document for every record, which is
-- correct behaviour and not a failure. Re-establishing the claims means re-running
-- the backfill. In the build that ships this migration the cost is ZERO, because
-- no read consults the table.
--
-- Dropping the table drops `isaac_run_projection_projector_idx`, the foreign key
-- and both CHECK constraints with it; none needs its own statement.

BEGIN;

DROP TABLE IF EXISTS isaac_run_projection;

DELETE FROM isaac_schema_migrations WHERE version = '0005_run_projection';

COMMIT;
