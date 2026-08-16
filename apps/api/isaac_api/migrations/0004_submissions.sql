-- 0004_submissions — the scientist's act of SUBMITTING an experiment, recorded
-- once, durably, and attributably.
--
-- SUBMIT IS NOT EXPORT, AND THIS FILE EXISTS BECAUSE THE TWO ARE DIFFERENT ACTS.
-- Export is a mechanical transform: it mints one official ISAAC record per run and
-- writes an artifact pair. It answers "does this validate". Submission is a
-- DECLARATION BY A PERSON — "this experiment is finished, and I am the one saying
-- so" — and it answers "who finalised this, when, over exactly what content".
-- Nothing in `Experiment.to_state()`, in `isaac_experiments`, or in `isaac_runs`
-- can answer that, and DERIVING "submitted" FROM "exported" WOULD BE A FABRICATION:
-- an export can be performed by any caller at any time, and it would silently
-- attribute a declaration nobody made.
--
-- WHY IT CANNOT LIVE IN THE EXPERIMENT DOCUMENT: the same two mechanical reasons
-- `0003_revisions.sql` opens with — `Q_UPSERT_EXPERIMENT` refuses a CHANGED
-- document at the SAME rev, and `save_versioned` does not attempt a write unless
-- `_authoritative_signature` moved, which covers only
-- `{title, source, draft, record_id, runs}`. Read that note; it is not repeated
-- here.
--
-- FORWARD-ONLY, ADDITIVE AND IDEMPOTENT. Every statement is
-- `CREATE ... IF NOT EXISTS`. There is no DROP, no TRUNCATE and no ALTER anywhere
-- in it, and it alters no table 0001, 0002 or 0003 created.
--
-- IT DEPENDS ON 0003 AND MUST BE APPLIED AFTER IT: `isaac_submissions` holds a
-- FOREIGN KEY into `isaac_experiment_revisions`. `db_migrate` orders migrations
-- lexicographically by filename, so `0003_revisions` precedes `0004_submissions`
-- by construction; the CI plan step asserts that order explicitly rather than
-- trusting it.
--
-- WHAT IT DELIBERATELY DOES NOT TOUCH: the `records` table, which holds the
-- production-derived 30-row sample. This migration neither reads it, writes it,
-- alters it, nor references it in a constraint.
--
-- THE IMMUTABILITY LIMIT IS THE SAME ONE 0003 STATES, and it is repeated in one
-- sentence rather than left to a cross-reference, because a reader who opens only
-- this file must not be able to infer a database guarantee that is not here: these
-- two tables are APPEND-ONLY BY STATEMENT INVENTORY AND BY TEST, not by the
-- database. A trigger would need a dollar-quoted body, which the migration runner
-- refuses; `REVOKE` is a forbidden verb in `db_write._FORBIDDEN_KEYWORDS`. Nothing
-- stops a psql session or a superuser.
--
-- Statements are separated by a line containing only `--;`.
--
-- =============================== isaac_submissions ===========================
--
--   submission_id   PRIMARY KEY, a ULID minted by `new_record_id()`. Not a record
--                   id, not a revision id: a submission names an ACT, and the
--                   records it published are named in `isaac_submission_runs`.
--
--   experiment_id   NOT NULL, FOREIGN KEY to `isaac_experiments`. No `ON DELETE`
--                   clause, so the default NO ACTION behaves as RESTRICT and
--                   deleting a submitted experiment is REFUSED. Same decision, same
--                   two reasons, and the same honest disclosure as `0002_runs`:
--                   `ON DELETE CASCADE` is also unwritable under the statement
--                   policy, so the design argument was never the only constraint.
--
--   revision_id     NOT NULL, FOREIGN KEY to `isaac_experiment_revisions`, and
--                   UNIQUE. ONE SUBMISSION PER REVISION, enforced by the database.
--                   The revision is the immutable snapshot of exactly what was
--                   submitted; a second submission pointing at the same snapshot
--                   would be a second declaration over one body of content, with
--                   nothing to distinguish them.
--
--   content_signature  text NOT NULL, CHECK a lowercase 64-hex sha256, UNIQUE PER
--                   EXPERIMENT. THE NATURAL IDEMPOTENCY KEY, and the reason the
--                   submit route needs no lock to be safe across processes: two
--                   callers submitting the same unchanged content compute the same
--                   signature, and the database admits exactly one of them. It is
--                   computed by `submissions.content_signature` over the export
--                   units' ids and drafts only — never over `rev`, `updated_utc`,
--                   `record_id` or any server timestamp — so it is STABLE ACROSS
--                   MATERIALISATION and a retry after a partial failure recomputes
--                   the same value. ONE DEGRADED EXCEPTION (review item M4), the
--                   same one `0003_revisions.sql` records: a materialised record
--                   that is unreadable, or whose own `record_id` disagrees with the
--                   file carrying it, drops out of its sibling group in
--                   `workspace._linkable`, which changes the links composed into its
--                   siblings' drafts and moves the signature. The claim holds for
--                   every readable, self-consistent artifact set, and the database
--                   cannot tell the two cases apart — it simply admits the second
--                   signature as new content. It duplicates the column of the same name on
--                   the revision row DELIBERATELY: the uniqueness is a property of
--                   the SUBMISSION, and enforcing it through a join is not
--                   something a UNIQUE constraint can do.
--
--   idempotency_key text, NULLABLE, UNIQUE PER EXPERIMENT. A client-supplied
--                   `Idempotency-Key` header, echoed back on a replay. NULLABLE
--                   because it is optional, and PostgreSQL's default NULLS DISTINCT
--                   behaviour is what makes that work: any number of rows may carry
--                   NULL, while two rows may not carry the same non-NULL key for
--                   one experiment. CHECKed non-empty when present, because `''`
--                   would be a key that every keyless retry could collide with.
--
--   unit_count      bigint NOT NULL, CHECK >= 1. How many export units this
--                   submission published — one per run, or exactly one for an
--                   experiment with no runs. >= 1 because a submission that
--                   published nothing is not a submission.
--
--   conflict_summary  jsonb NOT NULL DEFAULT '{}', CHECK it is a JSON object.
--                   THE EVIDENCE CONFLICTS THAT WERE PRESENT AT SUBMISSION,
--                   RECORDED AND DISCLOSED — AND DELIBERATELY NOT GATED ON.
--
--                   That is a decision with a measured reason. A field becomes
--                   `conflicting_evidence` (`evidence_classify._classify_entry`
--                   rule 1) as soon as two distinct non-null answers are recorded
--                   for it, and ORDINARY EDITING PRODUCES EXACTLY THAT:
--                   `_apply_run_field` APPENDS a `user_confirmation` entry every
--                   time and never replaces one, and no route in this application
--                   removes an evidence entry. So a scientist who answers a
--                   question, notices a typo, and answers it again has
--                   manufactured a conflict THEY CANNOT CLEAR THROUGH ANY SURFACE
--                   THIS BUILD OFFERS. Gating submission on it would be a
--                   permanent, inescapable block produced by correcting a mistake.
--                   Recording it is honest; refusing on it would be cruel and
--                   would teach nobody anything.
--
--                   It holds counts and the affected addresses, never the
--                   conflicting VALUES: the values are in the revision snapshot,
--                   and duplicating them here would put scientific content into a
--                   disclosure column.
--
--   subject / trust_basis / the attribution CHECK  Identical in meaning, in the
--                   closed set of three, in the paired CHECK, and in the non-empty
--                   CHECK on `subject` (review item M1 — `''` is not NULL, so the
--                   attribution pairing would read a row naming nobody as
--                   ATTRIBUTED), to `isaac_experiment_revisions`. Read that file's
--                   column notes; they are not repeated. The pair is stored on BOTH rows rather
--                   than only on the revision because a revision may in future be
--                   captured by something other than a submission, and a
--                   submission's author is a fact about the submission.
--
--   submitted_utc   timestamptz NOT NULL DEFAULT now(). THE SERVER ASSIGNS THE
--                   SUBMISSION TIME. No client value is accepted for it, and the
--                   API reports back what the database stamped rather than what the
--                   application guessed before the write.

CREATE TABLE IF NOT EXISTS isaac_submissions (
    submission_id      text        PRIMARY KEY
                       CONSTRAINT isaac_submissions_id_shape
                       CHECK (submission_id ~ '^[0-9A-Z]{26}$'),
    experiment_id      text        NOT NULL
                       CONSTRAINT isaac_submissions_experiment_fk
                       REFERENCES isaac_experiments (experiment_id),
    revision_id        text        NOT NULL
                       CONSTRAINT isaac_submissions_revision_fk
                       REFERENCES isaac_experiment_revisions (revision_id)
                       CONSTRAINT isaac_submissions_revision_unique
                       UNIQUE,
    content_signature  text        NOT NULL
                       CONSTRAINT isaac_submissions_signature_shape
                       CHECK (content_signature ~ '^[0-9a-f]{64}$'),
    idempotency_key    text
                       CONSTRAINT isaac_submissions_idempotency_key_non_empty
                       CHECK (idempotency_key IS NULL OR length(idempotency_key) > 0),
    unit_count         bigint      NOT NULL
                       CONSTRAINT isaac_submissions_unit_count_positive
                       CHECK (unit_count >= 1),
    conflict_summary   jsonb       NOT NULL DEFAULT '{}'
                       CONSTRAINT isaac_submissions_conflict_summary_is_object
                       CHECK (jsonb_typeof(conflict_summary) = 'object'),
    subject            text
                       CONSTRAINT isaac_submissions_subject_non_empty
                       CHECK (subject IS NULL OR length(subject) > 0),
    trust_basis        text        NOT NULL
                       CONSTRAINT isaac_submissions_trust_basis_known
                       CHECK (trust_basis IN ('unattributed', 'test_fixture',
                                              'verified_edge_assertion')),
    submitted_utc      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_submissions_signature_unique
    UNIQUE (experiment_id, content_signature),
    CONSTRAINT isaac_submissions_idempotency_unique
    UNIQUE (experiment_id, idempotency_key),
    CONSTRAINT isaac_submissions_attribution
    CHECK ((trust_basis = 'unattributed') = (subject IS NULL))
)
--;
-- "EVERY SUBMISSION OF THIS EXPERIMENT, NEWEST LAST." The two UNIQUE constraints
-- above index `(experiment_id, content_signature)` and
-- `(experiment_id, idempotency_key)`, and both serve a LOOKUP rather than a listing
-- — neither can order by time. This index is the chronological read, with
-- `submission_id` last so the order is total even for two rows stamped in the same
-- instant. `experiment_id` leads it, so it also serves the parent-side foreign-key
-- check and an examination of an `isaac_experiments` key is not a sequential scan.
CREATE INDEX IF NOT EXISTS isaac_submissions_experiment_time_idx
    ON isaac_submissions (experiment_id, submitted_utc, submission_id)
--;
-- =============================== isaac_submission_runs =======================
--
-- ONE ROW PER EXPORT UNIT PUBLISHED BY ONE SUBMISSION — which, under contract §1
-- D1, is one row per official ISAAC record.
--
--   submission_run_id  PRIMARY KEY, a fresh ULID. Not the record id: the same
--                   record id can appear in the history of more than one submission
--                   of the same experiment (a second submission after a correction
--                   republishes nothing, but the row still names the record that
--                   was current), so the record id cannot be the key.
--
--   submission_id   NOT NULL, FOREIGN KEY to `isaac_submissions`. No `ON DELETE`
--                   clause, same reasoning as everywhere else in this feature.
--
--   unit_id         text NOT NULL, ULID shape. `ExportUnit.target_id`: a RUN's id
--                   for an experiment with runs, the EXPERIMENT's own id for one
--                   without.
--
--   run_id          text, NULLABLE, ULID shape when present. The run this unit is,
--                   or NULL for the single unit of an experiment that has no runs.
--                   NULL RATHER THAN A COPY OF `unit_id`: an experiment with no runs
--                   HAS no run, and writing its own id into a column called `run_id`
--                   would assert one exists. `isaac_submission_runs_run_matches_unit`
--                   CHECKs that a non-NULL `run_id` equals `unit_id`, so the two can
--                   never name different things.
--
--   record_id       text NOT NULL, ULID shape.
--
--   isaac_submission_runs_one_record_per_unit  `CHECK (record_id = unit_id)`. THE
--                   ONE-RUN-ONE-RECORD RULE (contract §1 D1) WRITTEN INTO THE
--                   SCHEMA. `ExportUnit.mark_exported` already refuses to let a
--                   unit's target id and its record id diverge, and this is the
--                   same invariant enforced one layer down, where an application
--                   bug cannot reach it. Both columns are kept rather than collapsed
--                   into one, because they MEAN different things — a unit is a thing
--                   to publish, a record is the published thing — and a schema that
--                   states the equality is a schema that can be read without
--                   knowing the domain rule by heart.
--
--   isaac_submission_runs_unit_unique  UNIQUE (submission_id, unit_id). One
--                   submission publishes each unit at most once. This is also the
--                   index for "every unit of this submission", the only read this
--                   table has today.

CREATE TABLE IF NOT EXISTS isaac_submission_runs (
    submission_run_id  text        PRIMARY KEY
                       CONSTRAINT isaac_submission_runs_id_shape
                       CHECK (submission_run_id ~ '^[0-9A-Z]{26}$'),
    submission_id      text        NOT NULL
                       CONSTRAINT isaac_submission_runs_submission_fk
                       REFERENCES isaac_submissions (submission_id),
    unit_id            text        NOT NULL
                       CONSTRAINT isaac_submission_runs_unit_id_shape
                       CHECK (unit_id ~ '^[0-9A-Z]{26}$'),
    run_id             text
                       CONSTRAINT isaac_submission_runs_run_id_shape
                       CHECK (run_id IS NULL OR run_id ~ '^[0-9A-Z]{26}$'),
    record_id          text        NOT NULL
                       CONSTRAINT isaac_submission_runs_record_id_shape
                       CHECK (record_id ~ '^[0-9A-Z]{26}$'),
    created_utc        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_submission_runs_unit_unique
    UNIQUE (submission_id, unit_id),
    CONSTRAINT isaac_submission_runs_one_record_per_unit
    CHECK (record_id = unit_id),
    CONSTRAINT isaac_submission_runs_run_matches_unit
    CHECK (run_id IS NULL OR run_id = unit_id)
)
--;
-- "WHICH SUBMISSION PUBLISHED THIS RECORD?" — the reverse lookup, from an official
-- record id back to the act that published it. The UNIQUE constraint above leads on
-- `submission_id` and cannot serve it.
--
-- STATED HONESTLY, as in 0003: no code in this build issues that read yet. It is
-- created now because `ALTER` is a forbidden verb and `CREATE TABLE IF NOT EXISTS`
-- is a silent no-op against an existing table, so an index omitted here needs a
-- whole further migration, its own approval packet, and its own operator action.
CREATE INDEX IF NOT EXISTS isaac_submission_runs_record_idx
    ON isaac_submission_runs (record_id, submission_id)
