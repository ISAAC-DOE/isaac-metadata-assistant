-- 0005_run_projection — the per-experiment completeness claim for `isaac_runs`.
--
-- WHY IT EXISTS, and the reason is a MEASURED ambiguity rather than a design
-- preference. `0002_runs` made `isaac_runs` a shadow of the experiment document:
-- after `PostgresOrdinaryStore.persist` returns, the rows for that experiment
-- equal `exp.sorted_runs()`. Nothing reads them. A future reader cannot be written
-- against that alone, because
--
--     SELECT ... FROM isaac_runs WHERE experiment_id = %s
--
-- returning ZERO ROWS means EITHER "this experiment has no runs" OR "this
-- experiment's runs were never projected", and both are reachable. The second is
-- the normal state of every experiment persisted before the shadow write shipped,
-- and of every experiment saved while `0002` was still pending — a window this
-- deployment enters on every merge, because the image rolls out on merge and the
-- operator applies migrations by hand afterwards
-- (`experiment_repository._table_available` exists for exactly that window).
--
-- A reader that reads zero rows as "no runs" therefore SILENTLY DELETES EVERY RUN
-- OF EVERY PRE-EXISTING RECORD the first time it is switched on, and reports
-- success. This table makes that unwritable: absence of a row is absence of a
-- claim, and `run_count = 0` beside a MATCHING version pair is a positive
-- statement that this experiment has no runs.
--
-- `rows exist -> use them` was the obvious alternative and is rejected in the
-- contract (`docs/isaac-runs-stage-2-contract.md` §1): it cannot tell a complete
-- projection from a partial one, and it answers the wrong question for an
-- experiment with genuinely zero runs, which would fall back forever.
--
-- WHAT THIS MIGRATION IS NOT. It does NOT move any data, does NOT backfill, and
-- does NOT change any read. No read path in this application consults this table
-- in the build that ships it — the write path stamps it and nothing else. Moving a
-- reader onto `isaac_runs` is Stage 2b, a separate reviewed slice, gated on the
-- backfill of the contract's §3 having RUN and reported `never_projected: 0`.
--
-- IT DOES NOT TOUCH `0002_runs`, `0003_revisions` OR `0004_submissions`. `0002` is
-- applied to the hosted database (by Dean, 2026-08-12) and editing it is
-- impossible in any case: `ALTER` is a forbidden verb in
-- `db_write._FORBIDDEN_KEYWORDS` and `CREATE TABLE IF NOT EXISTS` is a silent
-- no-op against a table that already exists. No Stage-2 behaviour is hidden inside
-- `0003` or `0004`; they are owner-approved for their own contents and this file
-- adds nothing to them.
--
-- WHAT IT DELIBERATELY DOES NOT TOUCH: the `records` table, which holds the
-- production-derived 30-row sample. This migration neither reads it, writes it,
-- alters it, nor references it in a constraint.
-- `test_no_committed_migration_may_reference_the_production_table` reads this file
-- off disk and asserts the identifier does not appear in any statement.
--
-- FORWARD-ONLY, ADDITIVE AND IDEMPOTENT. Both statements are
-- `CREATE ... IF NOT EXISTS`. No DROP, no TRUNCATE, no ALTER.
--
-- ORDERING IS WHAT MAKES ONE PRESENCE CHECK ENOUGH. The runner applies migrations
-- in lexical version order and refuses to apply one out of order (proven in CI),
-- so `isaac_runs` exists in every environment where this table does. The write
-- path still stamps only inside the branch where it actually wrote run rows, so a
-- hand-rolled-back `0002` under a live pod produces no stamp rather than a false
-- one.
--
-- COLUMN BY COLUMN, CONSTRAINT BY CONSTRAINT:
--
--   experiment_id  PRIMARY KEY and FOREIGN KEY to
--               `isaac_experiments (experiment_id)`. Completeness is PER
--               EXPERIMENT, deliberately: a deployment-wide boolean would be a
--               claim about rows nobody counted. The primary key is what makes
--               the stamp an upsert rather than an append — there is one current
--               claim per experiment and history of it is not kept, because a
--               superseded claim is not evidence of anything.
--               NO `ON DELETE` CLAUSE IS WRITTEN, so the action is the SQL
--               default, NO ACTION, which for this non-deferrable constraint
--               behaves as RESTRICT: deleting an experiment that still has a
--               projection row is REFUSED by the database. Same two reasons
--               `0002_runs` gives — `ON DELETE CASCADE` would put an unbounded
--               silent multi-row destruction one statement away, and RESTRICT is
--               the REVERSIBLE direction, since going back from CASCADE would
--               need an `ALTER` the policy refuses. Disclosed as `0002` disclosed
--               it: `ON DELETE CASCADE` is ALSO unwritable under the current
--               statement policy, which reads the `delete` after `on` as naming a
--               table it does not own. The design argument stands on its own;
--               this note exists so a reader is not told a constraint was a free
--               choice when it was also forced.
--
--   experiment_rev  bigint NOT NULL, CHECK >= 0. THE REV OF THE DOCUMENT THE ROWS
--               WERE PROJECTED FROM — not the current rev, and the difference is
--               the entire mechanism. A stamp that recorded "complete" without
--               recording WHEN would be indistinguishable from a stale one, so
--               staleness would have to be assumed absent. Here it is DETECTED: a
--               later save that does not maintain the rows advances the document
--               past this value and the pair stops matching.
--               `isaac_experiments` has no `rev` column — the experiment's
--               version lives inside its jsonb `state`, which is why
--               `Q_UPSERT_EXPERIMENT` casts `(state ->> 'rev')::bigint` — so this
--               is a promoted copy of a document field, exactly as `isaac_runs`'
--               `rev` is.
--
--   experiment_generation  text NOT NULL, no default. The experiment's opaque
--               per-record nonce, which is what makes a delete-and-recreate
--               distinguishable at rev 0. Both keys are compared, for the same
--               reason `Q_UPSERT_EXPERIMENT` compares both: rev alone cannot see
--               a record that was destroyed and rebuilt.
--               NO DEFAULT on purpose: an empty generation is meaningless, and a
--               writer that omits it has a bug and should be told so by the
--               database rather than given `''`.
--
--   run_count   bigint NOT NULL, CHECK >= 0. How many rows the transaction
--               actually wrote. MEASURED, NOT ASSERTED — it is the length of the
--               projected row set, not the length of `sorted_runs()` as an
--               intention. `0` is a real answer and is the state `0002` alone
--               could not express.
--               NO CHECK TIES IT TO ANYTHING. It cannot be: a CHECK cannot count
--               rows in another table, and a trigger is not expressible in a
--               committed migration here because `db_migrate.split_statements`
--               refuses a dollar-quoted body. It is a writer-maintained
--               projection and this file says so rather than implying the
--               database enforces it.
--
--   projector   text NOT NULL, CHECK IN ('write-path', 'backfill'). WHO made the
--               claim. It exists because the two have different trust
--               properties: the write path stamps inside the same transaction as
--               the rows and inside the accepted branch of the experiment
--               compare-and-swap, while the backfill is an operator action over
--               documents of unknown vintage. A completeness report that could
--               not tell them apart could not answer "has the backfill actually
--               run here", which is the Stage-2b gate.
--               A CLOSED VALUE SET rather than free text, because an unrecognised
--               projector is a bug and a CHECK is the cheapest place to find it.
--               The cost is stated: adding a third projector needs a new table,
--               since `ALTER` is refused.
--
--   projected_utc  timestamptz NOT NULL DEFAULT now(). SERVER-SIDE row stamp, as
--               in 0001 and 0002. It is NOT a document field and nothing derives
--               correctness from it — the version pair does that. It is for an
--               operator reading the table by hand.
--
-- Statements are separated by a line containing only `--;`. The runner
-- (`db_migrate.py`) splits on that marker rather than on `;`, so a semicolon
-- inside a string literal or a comment can never split a statement in half.

CREATE TABLE IF NOT EXISTS isaac_run_projection (
    experiment_id          text        PRIMARY KEY
                           CONSTRAINT isaac_run_projection_experiment_fk
                           REFERENCES isaac_experiments (experiment_id),
    experiment_rev         bigint      NOT NULL
                           CONSTRAINT isaac_run_projection_rev_non_negative
                           CHECK (experiment_rev >= 0),
    experiment_generation  text        NOT NULL,
    run_count              bigint      NOT NULL
                           CONSTRAINT isaac_run_projection_count_non_negative
                           CHECK (run_count >= 0),
    projector              text        NOT NULL
                           CONSTRAINT isaac_run_projection_projector_known
                           CHECK (projector IN ('write-path', 'backfill')),
    projected_utc          timestamptz NOT NULL DEFAULT now()
)
--;
-- ONE INDEX, AND IT IS NOT ON THE PRIMARY KEY. The per-experiment lookup a future
-- reader performs is served by the primary key already. This index serves the ONE
-- query that is not per-experiment: the completeness report — "how many
-- experiments has each projector claimed, and how stale are they" — which the
-- backfill prints and which the Stage-2b gate is measured from. Leading on
-- `projector` because that is the column the report groups by.
CREATE INDEX IF NOT EXISTS isaac_run_projection_projector_idx
    ON isaac_run_projection (projector, projected_utc)
