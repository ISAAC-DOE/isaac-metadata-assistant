-- 0001_experiments — durable storage for experiments THIS APPLICATION creates.
--
-- FORWARD-ONLY AND IDEMPOTENT. Every statement is CREATE ... IF NOT EXISTS, so
-- re-running this file is a no-op even if the bookkeeping row were lost. There is
-- no DROP, no TRUNCATE and no ALTER anywhere in it, and it names no table this
-- application did not create.
--
-- WHAT IT DELIBERATELY DOES NOT TOUCH: the `records` table, which holds the
-- production-derived 30-row sample. This migration neither reads it, writes it,
-- alters it, nor depends on it existing. `apps/api/isaac_api/db_write.py`'s
-- statement policy would refuse a statement naming it, and CI asserts the table
-- is byte-identical across a migration run.
--
-- Statements are separated by a line containing only `--;`. The runner
-- (`db_migrate.py`) splits on that marker rather than on `;`, so a semicolon
-- inside a string literal or a comment can never split a statement in half.

CREATE TABLE IF NOT EXISTS isaac_schema_migrations (
    version      text        PRIMARY KEY,
    applied_utc  timestamptz NOT NULL DEFAULT now()
)
--;
-- The experiment's authoritative state, stored as the SAME JSON document the
-- filesystem repository writes to `experiment.json`
-- (`workspace.Experiment.to_state()`). Storing the whole document rather than a
-- column per field is deliberate: the document's shape is owned by the truth
-- core, and a column-per-field schema here would become a second, drifting
-- definition of it that no test could keep in step.
--
-- `experiment_id` is `text` with a CHECK, not `char(26)`: `char(n)` blank-pads on
-- read, which the record-verification path already has to strip. A `text` column
-- stores exactly what was written.
CREATE TABLE IF NOT EXISTS isaac_experiments (
    experiment_id  text        PRIMARY KEY
                   CONSTRAINT isaac_experiments_id_shape
                   CHECK (experiment_id ~ '^[0-9A-Z]{26}$'),
    state          jsonb       NOT NULL,
    created_utc    timestamptz NOT NULL DEFAULT now(),
    updated_utc    timestamptz NOT NULL DEFAULT now()
)
--;
-- The one read this application performs against its own table is "every
-- experiment, oldest first". The primary key already covers lookup by id.
CREATE INDEX IF NOT EXISTS isaac_experiments_created_idx
    ON isaac_experiments (created_utc)
