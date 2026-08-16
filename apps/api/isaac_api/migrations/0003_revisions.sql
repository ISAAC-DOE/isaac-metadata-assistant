-- 0003_revisions — an append-only history of what an experiment looked like at
-- the moment something was recorded about it.
--
-- WHY IT EXISTS, AND WHY IT CANNOT LIVE IN THE EXPERIMENT DOCUMENT. The obvious
-- cheaper design is "add a `revisions` array to `Experiment.to_state()`". It does
-- not work, and the reason is mechanical rather than aesthetic:
--
--   1. `experiment_repository.Q_UPSERT_EXPERIMENT` accepts a write only when the
--      generation differs, OR the offered `rev` is strictly ahead, OR the document
--      is byte-identical. A CHANGED document at the SAME rev is REFUSED BY THE
--      DATABASE. Recording history is not a scientific mutation and must not bump
--      the record's rev, so a history entry written into the document would be
--      refused by the compare-and-swap.
--   2. `workspace.Experiment.save_versioned` does not even attempt a write unless
--      `_authoritative_signature` moved, and that signature covers only
--      `{title, source, draft, record_id, runs}`. A new document key is invisible
--      to it, so the write would never be issued in the first place.
--
-- There is therefore no "shadow it in the document first, promote it later" path
-- available. History needs its own tables from the first line of code, which is
-- what this migration creates.
--
-- FORWARD-ONLY, ADDITIVE AND IDEMPOTENT. Every statement is
-- `CREATE ... IF NOT EXISTS`, so re-running the file is a no-op even if the
-- bookkeeping row were lost. There is no DROP, no TRUNCATE and no ALTER anywhere
-- in it, and it alters no table 0001 or 0002 created.
--
-- WHAT IT DELIBERATELY DOES NOT TOUCH: the `records` table, which holds the
-- production-derived 30-row sample. This migration neither reads it, writes it,
-- alters it, nor references it in a constraint.
-- `db_write._FORBIDDEN_TABLES` refuses any statement naming it by identifier, in
-- any position and any syntax, and
-- `test_no_committed_migration_may_reference_the_production_table` reads this file
-- off disk and asserts the identifier does not appear in any statement.
--
-- ================= THE IMMUTABILITY LIMIT, STATED BEFORE THE SCHEMA ==========
-- These three tables are APPEND-ONLY BY INVENTORY, NOT BY THE DATABASE, and a
-- reader must not infer a guarantee that is not here.
--
-- Two mechanisms that would give a real database-level guarantee are both
-- unavailable to this project, and neither absence is an oversight:
--
--   * A `BEFORE UPDATE OR DELETE` TRIGGER needs a function body, and a function
--     body needs dollar quoting. `db_migrate.split_statements` REFUSES any
--     migration file containing a dollar-quoted body outright, because the splitter
--     is line-based and comment-blind and would silently mangle one. The opening
--     delimiter is deliberately not written out even in this comment: the refusal
--     scans the WHOLE FILE, comments included, so quoting it here would refuse this
--     migration. (That is not a hypothetical — this comment did exactly that on its
--     first draft, and the loader caught it before anything else did.)
--   * `REVOKE UPDATE, DELETE ON ...` is refused by
--     `db_write._FORBIDDEN_KEYWORDS`, which bans `revoke` (and `grant`) wherever
--     they appear, in migrations included.
--
-- What actually holds the property is therefore an INVENTORY plus a test:
-- every statement this application issues is a module-level `Q_*` constant, and
-- `test_submission_store.py` asserts that no such constant issues an `UPDATE` or a
-- `DELETE` naming any table created by this migration or by 0004. That is a real
-- guard over this application's own code. It is NOT a guarantee about a psql
-- session, a superuser, or a future application, and it must never be described as
-- one.
--
-- Statements are separated by a line containing only `--;`. The runner
-- (`db_migrate.py`) splits on that marker rather than on `;`, so a semicolon inside
-- a string literal or a CHECK regex can never split a statement in half.
--
-- =============================== isaac_experiment_revisions ==================
--
--   revision_id     PRIMARY KEY, a ULID minted by `new_record_id()`. Same shape as
--                   a record id and a run id, and deliberately NOT a record id: it
--                   names a point in an experiment's history, not a published
--                   scientific record. `text` + CHECK rather than `char(26)`, for
--                   0001's reason — `char(n)` blank-pads on read.
--
--   experiment_id   NOT NULL, FOREIGN KEY to `isaac_experiments`. NO `ON DELETE`
--                   CLAUSE IS WRITTEN, so the action is the SQL default, NO ACTION,
--                   which for this non-deferrable constraint behaves as RESTRICT:
--                   deleting an experiment that still has history is REFUSED. That
--                   is the same decision `0002_runs` took and for the same two
--                   reasons — CASCADE would put "destroy every revision in the
--                   deployment" one statement away, and going from CASCADE back to
--                   RESTRICT would need an `ALTER`, which the write policy refuses.
--                   DISCLOSED HONESTLY, exactly as 0002 discloses it: `ON DELETE
--                   CASCADE` is ALSO UNWRITABLE under the current statement policy,
--                   which reads the `delete` after `on` as naming a table this
--                   application does not own. The design argument stands on its
--                   own; this note exists so a reader is not told a constraint was
--                   a free choice when it was also forced.
--
--   revision_no     bigint NOT NULL, CHECK >= 1, UNIQUE per experiment. The
--                   human-facing ordinal — revision 1, revision 2 — assigned by the
--                   writer as `previous + 1` inside the same transaction that
--                   inserts the row. The UNIQUE constraint is what makes that
--                   assignment safe under concurrency: two writers computing the
--                   same next number cannot both land, and the loser's whole
--                   transaction rolls back rather than producing a duplicate.
--                   It also supplies the index for "the latest revision of this
--                   experiment", so no separate index is created for that read.
--
--   experiment_rev  bigint NOT NULL, CHECK >= 0. The record's OWN `rev` at the
--                   moment of capture, copied out of the document. Distinct from
--                   `revision_no`: `rev` counts every authoritative mutation and
--                   moves without anything being recorded here, while `revision_no`
--                   counts entries in THIS table. Conflating them is the mistake
--                   this pair of columns exists to prevent.
--
--   generation      text NOT NULL, no default. The experiment's opaque per-creation
--                   nonce, so `(generation, experiment_rev)` reconstructs the
--                   version token the API served at capture time. NO DEFAULT on
--                   purpose, for 0002's reason: `''` satisfies NOT NULL and would
--                   be meaningless, so a writer that omits it has a bug and should
--                   be told so by the database.
--
--   state           jsonb NOT NULL, CHECK it is a JSON object. The experiment's
--                   `to_state()` verbatim — the whole document, runs included. This
--                   is a SNAPSHOT and not a diff: a diff chain is only as good as
--                   its oldest link, and one corrupt or missing link makes every
--                   later revision unreadable.
--
--   content_signature  text NOT NULL, CHECK a lowercase 64-hex sha256. The
--                   signature of the SUBMITTED CONTENT, computed by
--                   `submissions.content_signature` over the export units' ids and
--                   drafts ONLY. It deliberately excludes `rev`, `updated_utc`,
--                   `record_id` and every server-assigned timestamp, so it is
--                   STABLE ACROSS MATERIALISATION: the signature computed before
--                   artifacts are written equals the one computed after. That
--                   stability is what makes it a usable idempotency key, and it is
--                   the reason the column is not simply a digest of `state`.
--                   ONE DEGRADED EXCEPTION, stated rather than glossed (review item
--                   M4): a unit's composed draft carries sibling links, and
--                   `workspace._linkable` yields nothing for a materialised record
--                   that is unreadable or whose own `record_id` disagrees with the
--                   file carrying it. That unit leaves its sibling group, the
--                   siblings' links change, and the signature moves. The stability
--                   claim holds for every readable, self-consistent artifact set.
--
--   reason          text NOT NULL, CHECK in a closed set. Why this revision was
--                   captured. One member today, `submission`. A closed set rather
--                   than free text because an unconstrained column would become a
--                   place to write prose that nothing can ever query.
--
--   subject         text, NULLABLE. The canonical Authentik username of the person
--                   this revision is attributed to, or NULL. Never a display name,
--                   never an email, never a uid — `docs/identity-trust-contract.md`
--                   §9 disqualifies email as an identifier and records it as
--                   personal data, and the 2026-08-12 decision is that the username
--                   is the one canonical key.
--                   CHECKed NON-EMPTY WHEN PRESENT (review item M1). `''` satisfies
--                   both `text` and the attribution CHECK below — it is not NULL, so
--                   the pairing reads the row as ATTRIBUTED — and it names nobody.
--                   That is the exact defect the attribution CHECK exists to refuse,
--                   surviving through the one value that slips between "a name" and
--                   "no name". Unreachable from this application today
--                   (`HumanActor` and `EdgeAssertion` both reject an empty subject
--                   before a row is built), and added anyway: every other
--                   shape-sensitive column in these two migrations carries a CHECK,
--                   this is the security-relevant one, and `ALTER` is a forbidden
--                   verb so it cannot be added later without a whole new migration.
--
--   trust_basis     text NOT NULL, CHECK in a closed set of three. WHAT VOUCHED FOR
--                   `subject`, recorded in the row itself and not inferable from
--                   anywhere else later. The three members mirror
--                   `identity.RECOGNISED_TRUST_BASES` plus one:
--                     `unattributed`             — nobody was established;
--                     `test_fixture`             — a subject minted from process
--                                                  configuration by
--                                                  `identity.FixtureEdgeVerifier`,
--                                                  which is NOT proof that anyone
--                                                  authenticated;
--                     `verified_edge_assertion`  — a verifier witnessed the trusted
--                                                  boundary. NO VERIFIER IN THIS
--                                                  BUILD MINTS IT, so no row can
--                                                  carry it yet. It is admitted here
--                                                  so that the day one does, the
--                                                  older rows are already visibly
--                                                  labelled as something weaker.
--                   `unattributed` is NOT in `identity.RECOGNISED_TRUST_BASES` and
--                   must not be added to it: that set is the set of bases a
--                   `HumanActor` may claim, and "nobody" is not a person.
--
--   isaac_experiment_revisions_attribution  A table-level CHECK that an attributed
--                   row names somebody and an unattributed row names nobody:
--                   `(trust_basis = 'unattributed') = (subject IS NULL)`. It closes
--                   both halves of the same defect. A row with a subject and
--                   `trust_basis = 'unattributed'` would carry a name nothing
--                   vouched for, which is the one thing this whole seam exists to
--                   refuse. A row with `trust_basis = 'test_fixture'` and no subject
--                   would claim an attribution basis while naming nobody, and would
--                   read downstream as an attributed row.
--
--   created_utc     timestamptz NOT NULL DEFAULT now(). THE SERVER-SIDE ROW
--                   TIMESTAMP, and the one the API reports back as the submission
--                   time. It is not read from a client and not read from the
--                   document — the document's own `updated_utc` stays inside
--                   `state` and means something else (when the RECORD last changed,
--                   not when this ROW was written).

CREATE TABLE IF NOT EXISTS isaac_experiment_revisions (
    revision_id        text        PRIMARY KEY
                       CONSTRAINT isaac_experiment_revisions_id_shape
                       CHECK (revision_id ~ '^[0-9A-Z]{26}$'),
    experiment_id      text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_experiment_fk
                       REFERENCES isaac_experiments (experiment_id),
    revision_no        bigint      NOT NULL
                       CONSTRAINT isaac_experiment_revisions_no_positive
                       CHECK (revision_no >= 1),
    experiment_rev     bigint      NOT NULL
                       CONSTRAINT isaac_experiment_revisions_rev_non_negative
                       CHECK (experiment_rev >= 0),
    generation         text        NOT NULL,
    state              jsonb       NOT NULL
                       CONSTRAINT isaac_experiment_revisions_state_is_object
                       CHECK (jsonb_typeof(state) = 'object'),
    content_signature  text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_signature_shape
                       CHECK (content_signature ~ '^[0-9a-f]{64}$'),
    reason             text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_reason_known
                       CHECK (reason IN ('submission')),
    subject            text
                       CONSTRAINT isaac_experiment_revisions_subject_non_empty
                       CHECK (subject IS NULL OR length(subject) > 0),
    trust_basis        text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_trust_basis_known
                       CHECK (trust_basis IN ('unattributed', 'test_fixture',
                                              'verified_edge_assertion')),
    created_utc        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_experiment_revisions_no_unique
    UNIQUE (experiment_id, revision_no),
    CONSTRAINT isaac_experiment_revisions_attribution
    CHECK ((trust_basis = 'unattributed') = (subject IS NULL))
)
--;
-- THE CHRONOLOGICAL READ. `isaac_experiment_revisions_no_unique` already indexes
-- `(experiment_id, revision_no)`, which is what "the latest revision of this
-- experiment" uses, so this index is deliberately NOT a duplicate of it: it orders
-- by the server-side row timestamp instead, which is the order a history LIST is
-- presented in. `revision_id` is the third column so the index alone gives a
-- deterministic total order rather than an arbitrary one among rows written in the
-- same instant.
--
-- IT ALSO SERVES THE PARENT-SIDE FOREIGN-KEY CHECK. An unindexed referencing column
-- makes every examination of an `isaac_experiments` key a sequential scan of every
-- revision in the deployment; `experiment_id` leads this index, so it does not.
CREATE INDEX IF NOT EXISTS isaac_experiment_revisions_experiment_time_idx
    ON isaac_experiment_revisions (experiment_id, created_utc, revision_id)
--;
-- =============================== isaac_run_revisions =========================
--
-- ONE ROW PER RUN PER REVISION. An experiment with no runs contributes ZERO rows
-- here, and that is correct rather than a gap: such an experiment's single export
-- unit is the experiment itself, and its draft is already inside
-- `isaac_experiment_revisions.state`. Writing a synthetic "run row" for it would
-- invent a run that does not exist.
--
--   run_revision_id  PRIMARY KEY, a fresh ULID. It is NOT the run id: the same run
--                   appears in many revisions, so the run id cannot be the key.
--
--   revision_id     NOT NULL, FOREIGN KEY to `isaac_experiment_revisions`. No
--                   `ON DELETE` clause, same reasoning as above.
--
--   run_id          text NOT NULL, CHECK the ULID shape — AND DELIBERATELY NOT A
--                   FOREIGN KEY TO `isaac_runs`. Two independent reasons, and the
--                   first is the one that matters:
--                     (a) HISTORY MUST SURVIVE THE THING IT DESCRIBES. A run can be
--                         removed from an experiment (`Experiment.save` issues
--                         `Q_DELETE_ABSENT_RUNS` for every run the document no
--                         longer names), and when it is, the row in `isaac_runs`
--                         goes away. A foreign key would then either REFUSE that
--                         deletion — freezing the live table behind its own audit
--                         log — or, with CASCADE, DELETE THE HISTORY, which is the
--                         one outcome an append-only history may never have.
--                     (b) `ON DELETE CASCADE` is unwritable under the statement
--                         policy anyway, so the choice was never actually open.
--                   The cost is stated rather than hidden: nothing at the database
--                   level guarantees that a `run_id` here names a row in
--                   `isaac_runs`, and a reader must treat a run id in this table as
--                   a HISTORICAL NAME rather than as a live reference.
--
--   ordinal / rev / generation / state  The same projection `0002_runs` promotes,
--                   frozen at capture. `state` is `Run.to_state()` verbatim and is
--                   CHECKed to be a JSON object, for 0002's reason: `jsonb` accepts
--                   a bare scalar, and a run whose document is the string "null"
--                   would satisfy NOT NULL while hydrating into nothing.
--
--   isaac_run_revisions_revision_run_unique  UNIQUE (revision_id, run_id). One
--                   revision cannot contain the same run twice. This is also the
--                   index for "every run of this revision", which is the only read
--                   this table has, so no second index is created for it.
--
--   isaac_run_revisions_document_identity  `state ->> 'id' = run_id`, with the same
--                   NULL tolerance `0002_runs` documents: `->>` yields NULL for an
--                   absent key and a CHECK passes unless it is FALSE. The
--                   `experiment_id` half of 0002's identity CHECK is NOT repeated
--                   here, and the asymmetry is deliberate — this table has no
--                   `experiment_id` column to compare against, because a run
--                   revision is addressed through its experiment revision.

CREATE TABLE IF NOT EXISTS isaac_run_revisions (
    run_revision_id  text        PRIMARY KEY
                     CONSTRAINT isaac_run_revisions_id_shape
                     CHECK (run_revision_id ~ '^[0-9A-Z]{26}$'),
    revision_id      text        NOT NULL
                     CONSTRAINT isaac_run_revisions_revision_fk
                     REFERENCES isaac_experiment_revisions (revision_id),
    run_id           text        NOT NULL
                     CONSTRAINT isaac_run_revisions_run_id_shape
                     CHECK (run_id ~ '^[0-9A-Z]{26}$'),
    ordinal          bigint      NOT NULL DEFAULT 0
                     CONSTRAINT isaac_run_revisions_ordinal_non_negative
                     CHECK (ordinal >= 0),
    state            jsonb       NOT NULL
                     CONSTRAINT isaac_run_revisions_state_is_object
                     CHECK (jsonb_typeof(state) = 'object'),
    rev              bigint      NOT NULL DEFAULT 0
                     CONSTRAINT isaac_run_revisions_rev_non_negative
                     CHECK (rev >= 0),
    generation       text        NOT NULL,
    created_utc      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_run_revisions_revision_run_unique
    UNIQUE (revision_id, run_id),
    CONSTRAINT isaac_run_revisions_document_identity
    CHECK (state ->> 'id' = run_id)
)
--;
-- THE PER-RUN HISTORY READ — "show me every revision this run appears in". The
-- UNIQUE constraint above indexes `(revision_id, run_id)` and cannot serve a query
-- whose leading column is `run_id`, so this is a genuinely different access path
-- and not a duplicate.
--
-- STATED HONESTLY: NO CODE IN THIS BUILD ISSUES THAT READ YET. The index is created
-- now because `ALTER` is a forbidden verb and `CREATE TABLE IF NOT EXISTS` is a
-- silent no-op against an existing table, so anything omitted here needs a whole
-- further migration, its own approval packet, and its own operator action. The cost
-- of the index is one B-tree maintained on an append-only table; the cost of
-- omitting it is a second round of the process that produced this file.
CREATE INDEX IF NOT EXISTS isaac_run_revisions_run_idx
    ON isaac_run_revisions (run_id, revision_id)
--;
-- =============================== isaac_revision_changes ======================
--
-- WHAT CHANGED, ADDRESS BY ADDRESS, BETWEEN THIS REVISION AND THE ONE BEFORE IT.
--
-- THE SCOPE OF "CHANGED" IS NARROW AND IS WRITTEN DOWN HERE SO IT IS NOT MISREAD.
-- `submissions.address_changes` compares, for every export unit, the unit's DRAFT
-- FIELD VALUES — the `value` of each entry under `fields`, canonicalised as JSON.
-- It does NOT diff evidence entries, run overrides, answer logs, assets, implicit
-- claims, or anything nested inside a field's value beyond that value's canonical
-- form. A row here therefore means "this field's value differs from the previous
-- revision", and the ABSENCE of a row means only "no field value differed", never
-- "nothing about this unit changed".
--
--   change_id       PRIMARY KEY, a fresh ULID.
--
--   revision_id     NOT NULL, FOREIGN KEY to `isaac_experiment_revisions`. The
--                   revision these changes were observed AT, i.e. the newer of the
--                   two compared. No `ON DELETE` clause, same reasoning as above.
--
--   unit_id         text NOT NULL. The export unit the address belongs to: a RUN's
--                   id for an experiment with runs, and the EXPERIMENT's own id for
--                   one without. That is exactly `ExportUnit.target_id`, so a
--                   change row is addressable to the same thing a record is.
--                   It is a plain column and not a foreign key for the same reason
--                   `run_id` above is not one.
--
--   address         text NOT NULL, non-empty. The draft field path, e.g.
--                   `sample.mass_mg`. CHECKed non-empty because an empty address
--                   addresses nothing and would still satisfy NOT NULL.
--
--   change_kind     text NOT NULL, CHECK in a closed set of three: `added`,
--                   `removed`, `modified`. Nothing else is expressible, so a
--                   consumer can switch on it exhaustively.
--
--   isaac_revision_changes_unique  UNIQUE (revision_id, unit_id, address). One
--                   address changes at most once per revision. This is also the
--                   index for "every change in this revision", the only read this
--                   table has today.
--
-- WHAT IS DELIBERATELY NOT STORED: the OLD and NEW values. They are already in the
-- two revisions' `state` documents, so storing them here would be a second copy
-- that can disagree with the first — and it would put scientific values into a
-- table whose purpose is navigation.

CREATE TABLE IF NOT EXISTS isaac_revision_changes (
    change_id    text        PRIMARY KEY
                 CONSTRAINT isaac_revision_changes_id_shape
                 CHECK (change_id ~ '^[0-9A-Z]{26}$'),
    revision_id  text        NOT NULL
                 CONSTRAINT isaac_revision_changes_revision_fk
                 REFERENCES isaac_experiment_revisions (revision_id),
    unit_id      text        NOT NULL
                 CONSTRAINT isaac_revision_changes_unit_id_shape
                 CHECK (unit_id ~ '^[0-9A-Z]{26}$'),
    address      text        NOT NULL
                 CONSTRAINT isaac_revision_changes_address_non_empty
                 CHECK (length(address) > 0),
    change_kind  text        NOT NULL
                 CONSTRAINT isaac_revision_changes_kind_known
                 CHECK (change_kind IN ('added', 'removed', 'modified')),
    created_utc  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_revision_changes_unique
    UNIQUE (revision_id, unit_id, address)
)
--;
-- "WHEN DID THIS ADDRESS LAST CHANGE?" — the field-history read, whose leading
-- column is the address rather than the revision, so the UNIQUE constraint's index
-- cannot serve it. Created now for the same reason the run-history index above is,
-- and with the same disclosure: no code in this build issues this read yet.
CREATE INDEX IF NOT EXISTS isaac_revision_changes_address_idx
    ON isaac_revision_changes (unit_id, address, revision_id)
