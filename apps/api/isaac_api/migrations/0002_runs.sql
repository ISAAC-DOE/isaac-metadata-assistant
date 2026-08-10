-- 0002_runs — one relational row per Run, so a Run is independently persisted.
--
-- WHY IT EXISTS. Today a Run lives INSIDE its experiment's `state` document
-- (`workspace.Experiment.to_state()` serialises `runs` as an array). Contract §8
-- DECISION D7 rejects that shape on the brief's own §5 requirement: one jsonb
-- document rewritten on every autosave keystroke, containing N runs, is the
-- "single enormous object" the brief forbids. This migration creates the table
-- that makes a Run the unit of write. It does NOT move any data and does NOT
-- change any application behaviour — see "WHAT THIS MIGRATION IS NOT" below.
--
-- THIS FILE WAS EDITED IN PLACE AFTER REVIEW, AND THAT IS ONLY LEGITIMATE
-- BECAUSE IT HAS NEVER BEEN APPLIED ANYWHERE. The hosted database is migrated to
-- `0001_experiments` only (applied by the owner on 2026-08-09); `0002` is pending
-- everywhere. The edit is the `isaac_runs_document_identity` CHECK, described in
-- full below. Editing a PENDING migration is the only way to change it at all:
-- `ALTER` is a forbidden verb in `db_write._FORBIDDEN_KEYWORDS`, and
-- `CREATE TABLE IF NOT EXISTS` is a silent no-op against a table that already
-- exists — so once this file is applied to an environment, its constraints are
-- fixed there and a correction would need a new table. Any future change to this
-- file must first establish, for every environment, that `0002_runs` is absent
-- from `isaac_schema_migrations`.
--
-- FORWARD-ONLY, ADDITIVE AND IDEMPOTENT. Both statements are
-- `CREATE ... IF NOT EXISTS`, so re-running this file is a no-op even if the
-- bookkeeping row were lost. There is no DROP, no TRUNCATE and no ALTER anywhere
-- in it. In particular it does NOT alter `isaac_experiments`: `alter` is a
-- forbidden verb in `db_write._FORBIDDEN_KEYWORDS`, so an altering migration
-- could not run at all, and the experiments table is left exactly as 0001 created
-- it.
--
-- WHAT IT DELIBERATELY DOES NOT TOUCH: the `records` table, which holds the
-- production-derived 30-row sample. This migration neither reads it, writes it,
-- alters it, nor references it in a constraint. `db_write._FORBIDDEN_TABLES`
-- refuses any statement naming it by identifier, in any position and any syntax,
-- and `test_no_committed_migration_may_reference_the_production_table` reads this
-- file off disk and asserts the identifier does not appear in any statement.
--
-- WHAT THIS MIGRATION IS NOT. No application code writes or reads `isaac_runs`.
-- The nine statements this application issues are module-level constants
-- (`db_write.Q_*`, `db_migrate.Q_*`, `experiment_repository.Q_*`) and none of them
-- names this table — pinned by
-- `test_0002_is_inert_for_this_build_no_statement_names_isaac_runs`. So the
-- application behaves identically with 0002 applied and with 0002 unapplied. The
-- run write path, the per-run compare-and-swap and the backfill from the
-- experiment document are LATER slices, each needing its own review.
--
-- WHY THE COLUMNS ARE PROMOTED OUT OF THE DOCUMENT AT ALL, given 0001's stated
-- rationale that the document's shape is owned by the truth core. Two reasons,
-- and the second is the one that actually forces the hand:
--   1. `experiment_id` and `ordinal` must be INDEXABLE and `experiment_id` must be
--      a real foreign key. Neither is expressible over a jsonb blob without an
--      expression index and a cast, which is a second definition of the same
--      field with worse ergonomics.
--   2. `ALTER` IS REFUSED BY THE WRITE POLICY. A column omitted here cannot be
--      added later without either changing that policy or creating a second
--      table. That cuts both ways and is stated in the approval packet as a cost:
--      a column included here and later found wrong cannot be dropped either.
-- The full `Run.to_state()` document still lands in `state`, exactly as 0001 does
-- for an experiment, so the promoted columns are a projection of the document and
-- never a replacement for it.
--
-- COLUMN BY COLUMN, CONSTRAINT BY CONSTRAINT:
--
--   run_id      PRIMARY KEY. A run is addressed by its own id everywhere in the
--               domain model (`Experiment.get_run`, the override map, the export
--               fan-out). `isaac_runs_id_shape` CHECKs `^[0-9A-Z]{26}$` because a
--               run id is minted by `new_record_id()` — the same ULID shape a
--               record id has (`workspace.new_run`), though it is NOT a record id.
--               `text` + CHECK rather than `char(26)`, for 0001's reason: `char(n)`
--               blank-pads on read.
--
--   experiment_id  NOT NULL, FOREIGN KEY to `isaac_experiments (experiment_id)`.
--               A run with no experiment is unaddressable — nothing can render,
--               version or export it. NO `ON DELETE` CLAUSE IS WRITTEN, so the
--               action is the SQL default, NO ACTION, which for this
--               non-deferrable constraint behaves exactly as RESTRICT: deleting an
--               experiment that still has runs is REFUSED by the database.
--               That is deliberate, not an omission, and there are two independent
--               reasons:
--                 (a) `ON DELETE CASCADE` turns one statement into an unbounded
--                     silent multi-row destruction. `DELETE FROM isaac_experiments`
--                     already passes the write policy (`delete` is not a forbidden
--                     verb and the table is owned), so CASCADE would put "destroy
--                     every run in the deployment" one statement away. Refusing is
--                     the behaviour the rest of this write path is built around.
--                 (b) It is the REVERSIBLE choice. A future delete path can delete
--                     runs explicitly and then the experiment, with no schema
--                     change at all. Going the other way — from CASCADE back to
--                     RESTRICT — would need an ALTER, which the policy refuses.
--               DISCLOSED HONESTLY: `ON DELETE CASCADE` is ALSO UNWRITABLE under
--               the current statement policy, which reads the `delete` after `on`
--               as naming a table it does not own and refuses the statement
--               (measured, not assumed). The design argument above stands on its
--               own; this note exists so a reader is not told a constraint was a
--               free choice when it was also forced.
--
--   ordinal     bigint NOT NULL DEFAULT 0, CHECK >= 0. THE ORDER KEY.
--               `Experiment.sorted_runs` sorts on `(ordinal, created_utc, id)` and
--               deliberately never on the label. DEFAULT 0 mirrors the dataclass
--               default, which is also what every pre-`ordinal` persisted document
--               hydrates to.
--               NO UNIQUE CONSTRAINT ON (experiment_id, ordinal), and that is a
--               decision rather than an oversight: every run in a legacy document
--               hydrates with `ordinal = 0`, so a uniqueness constraint would
--               refuse data this application can already produce. Ties are broken
--               by the sort's later keys, exactly as they are in memory.
--
--   state       jsonb NOT NULL, `isaac_runs_state_is_object` CHECKs it is a JSON
--               object. It holds `Run.to_state()` verbatim. The CHECK exists
--               because `jsonb` accepts a bare scalar or array as a valid value,
--               and a run whose document is the string "null" would hydrate into
--               nothing while satisfying NOT NULL.
--
--   rev         bigint NOT NULL DEFAULT 0, CHECK >= 0. The run's monotonic
--               version, written only by `Experiment._bump_changed_runs`.
--               Promoted so a later per-run compare-and-swap can compare a typed
--               column instead of `(state ->> 'rev')::bigint`, which is what
--               0001's experiment-level predicate has to do.
--
--   generation  text NOT NULL, no default. The per-run opaque nonce that makes a
--               delete->recreate distinguishable at rev 0. NO DEFAULT on purpose:
--               an empty generation is meaningless, and `Run.__post_init__`
--               guarantees a non-empty one, so a writer that omits it has a bug
--               and should be told so by the database rather than given `''`.
--
--   created_utc / updated_utc  timestamptz NOT NULL DEFAULT now(). SERVER-SIDE
--               row timestamps, exactly as in 0001 — they are NOT the document's
--               own `created_utc`/`updated_utc` strings, which stay in `state`.
--               Saying so explicitly because the two are easy to conflate: the
--               column records when this ROW was written; the document records
--               when the RUN was created by the application.
--
--   isaac_runs_document_identity  A table-level CHECK that the two identity keys
--               agree with the document they project: `state ->> 'id' = run_id`
--               and, for `experiment_id`, agreement OR silence. Promoting a field
--               out of a document creates exactly one new failure mode — the two
--               copies disagreeing — and this closes it for the two keys where a
--               disagreement would mean the row names a different run.
--
--               A CORRECTION, RECORDED RATHER THAN QUIETLY APPLIED. This comment
--               used to read "IT IS LEGACY-TOLERANT BY CONSTRUCTION: `->>` yields
--               NULL for an absent key, a comparison against NULL is NULL, and a
--               CHECK passes unless it is FALSE." Every clause of that is true,
--               and the conclusion drawn from it was FALSE for the only legacy
--               shape this application can actually produce. `Run.to_state()`
--               emits every key unconditionally, and `Run.from_state` reads each
--               string through `_as_str`, which returns `''` for an absent one —
--               so a legacy run document carries `"experiment_id": ""`, not a
--               missing key. `'' = experiment_id` is FALSE, not NULL, and the row
--               was REFUSED. The NULL argument only ever described a bare `'{}'`
--               document, which is what the CI fixture happened to insert; that is
--               why nothing caught it. The shape is reachable and permanent:
--               `workspace._hydrate_runs` documents that `experiment_id` is
--               deliberately NOT repaired from the owning experiment, because
--               repairing it on READ would change the run's authoritative
--               signature and bump every record's `rev` on a mere listing.
--
--               SO `experiment_id` NOW TREATS `''` EXACTLY AS IT TREATS AN ABSENT
--               KEY: `coalesce(nullif(state ->> 'experiment_id', ''),
--               experiment_id) = experiment_id`. This is not a weakening of the
--               constraint's intent. What it exists to refuse is a row whose
--               document names a DIFFERENT experiment, and `''` names none — it is
--               this codebase's canonical encoding of "absent" for every string
--               field of a run. Every non-empty disagreeing value is still
--               refused, and the row's own `experiment_id` column is still NOT
--               NULL and still a real foreign key, so the parent is never in
--               doubt. The alternative — repairing the document at hydration —
--               was rejected because it changes documented read behaviour and
--               rewrites `rev` across the workspace irreversibly, to fix a
--               constraint that has never been applied anywhere.
--
--               `id` IS DELIBERATELY NOT RELAXED THE SAME WAY, and the asymmetry
--               is a decision. `_hydrate_runs` DROPS a run whose id is empty, so
--               no document this application persists can carry `id: ''`; a
--               document that identifies no run at all is exactly what this
--               constraint should refuse. Its NULL tolerance for a genuinely
--               absent `id` is unchanged.
--
--               `ordinal`, `rev` and `generation` are deliberately NOT constrained
--               this way. Each would need a cast (`(state ->> 'rev')::bigint`), and
--               a cast inside a CHECK raises on malformed text instead of
--               returning false — trading a clean constraint violation for a cast
--               error. They are writer-maintained projections, and the approval
--               packet says so rather than implying the database enforces it.
--
-- Statements are separated by a line containing only `--;`. The runner
-- (`db_migrate.py`) splits on that marker rather than on `;`, so a semicolon
-- inside a string literal or a comment can never split a statement in half.

CREATE TABLE IF NOT EXISTS isaac_runs (
    run_id         text        PRIMARY KEY
                   CONSTRAINT isaac_runs_id_shape
                   CHECK (run_id ~ '^[0-9A-Z]{26}$'),
    experiment_id  text        NOT NULL
                   CONSTRAINT isaac_runs_experiment_fk
                   REFERENCES isaac_experiments (experiment_id),
    ordinal        bigint      NOT NULL DEFAULT 0
                   CONSTRAINT isaac_runs_ordinal_non_negative
                   CHECK (ordinal >= 0),
    state          jsonb       NOT NULL
                   CONSTRAINT isaac_runs_state_is_object
                   CHECK (jsonb_typeof(state) = 'object'),
    rev            bigint      NOT NULL DEFAULT 0
                   CONSTRAINT isaac_runs_rev_non_negative
                   CHECK (rev >= 0),
    generation     text        NOT NULL,
    created_utc    timestamptz NOT NULL DEFAULT now(),
    updated_utc    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_runs_document_identity
    CHECK (state ->> 'id' = run_id
           AND coalesce(nullif(state ->> 'experiment_id', ''), experiment_id)
               = experiment_id)
)
--;
-- ONE INDEX, DOING THREE JOBS, and no second index is created because no second
-- read exists yet:
--   1. the experiment-scoped list — "every run of this experiment" — which is the
--      only read the run write path will perform;
--   2. the ordinal sort within that list, which is `sorted_runs`' leading key;
--   3. the parent-side check the FOREIGN KEY performs whenever an experiment row
--      is deleted or its key is examined. An unindexed referencing column makes
--      that check a sequential scan of every run in the deployment.
-- `run_id` is the third column so the index alone gives a deterministic total
-- order. It is NOT the same total order as `sorted_runs`, which tie-breaks on the
-- DOCUMENT's `created_utc` between `ordinal` and `id`; that key is not a column
-- here (the column of that name is the server-side row timestamp, see above), and
-- adding it to the index would have meant introducing an unenforced invariant
-- between a timestamptz column and a text field inside the document. A query that
-- must reproduce `sorted_runs` exactly will sort on
-- `(ordinal, state ->> 'created_utc', run_id)`; this index still serves its
-- leading columns, and the missing key only orders runs that share both an
-- experiment and an ordinal.
CREATE INDEX IF NOT EXISTS isaac_runs_experiment_order_idx
    ON isaac_runs (experiment_id, ordinal, run_id)
