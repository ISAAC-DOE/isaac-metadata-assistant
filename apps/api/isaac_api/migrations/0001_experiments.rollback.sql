-- ROLLBACK for 0001_experiments.
--
-- THIS FILE IS NEVER EXECUTED BY THE APPLICATION, and it cannot be: every
-- statement in it is a DROP, and `db_write.WriteStatementPolicy` refuses DROP
-- wherever it appears, so the only path that could run it is a human (or CI)
-- driving psql directly. That is the intent — a rollback is an operator action,
-- taken deliberately, not something an app can do to itself on a bad boot.
--
-- IT NAMES ONLY TABLES 0001 CREATED. `records` — the production-derived 30-row
-- sample — is not named here and must never be. Rolling back removes this
-- application's own experiment storage and nothing else.
--
-- WHAT ROLLING BACK COSTS: every experiment a user created is deleted. It is a
-- destructive operation on user data, and it is safe only for the schema itself.
-- Before running it against a database that has served real users, dump
-- `isaac_experiments` first:
--
--     \copy (SELECT experiment_id, state FROM isaac_experiments) TO 'experiments.csv' CSV
--
-- Dropping `isaac_experiments` also drops `isaac_experiments_created_idx` and the
-- `isaac_experiments_id_shape` constraint with it; neither needs its own statement.

DROP TABLE IF EXISTS isaac_experiments;

DROP TABLE IF EXISTS isaac_schema_migrations;
