"""The durable write path for SUBMISSIONS and the revision history they capture.

WHY THIS IS A SEPARATE MODULE FROM ``experiment_repository``
============================================================
``experiment_repository`` owns ONE thing: the current authoritative state of an
experiment, compare-and-swapped under the ``If-Match`` contract, plus the run rows
that shadow it. Everything it writes is a projection of a document that already
exists, and everything it writes can be rewritten.

This module owns the opposite kind of data: **append-only history**. Nothing here
updates a row and nothing here deletes one. Folding the two together would put an
``UPDATE`` and a ``DELETE`` in the same module as the history writes, and the
append-only property is enforced by a test that reads the statements this
application declares — a property that is much easier to state, and to check, when
the history statements live somewhere that has no other kind.

IT REUSES ``db_write.write_transaction`` UNCHANGED. Same statement policy, same
``PGDATABASE`` gate, same server-side ``current_database()`` re-check, same
deterministic rollback, same short-lived connection. Every statement below is a
module-level constant with ``%s`` placeholders; **no caller-supplied SQL exists on
this path**, and the caller cannot contribute a character of it.

THE APPEND-ONLY GUARANTEE, STATED EXACTLY
=========================================
It is a guarantee about **this application**, enforced by statement inventory and
by ``test_submission_store.py``. It is **not** a database guarantee, and the two
mechanisms that would make it one are both unavailable:

* a ``BEFORE UPDATE OR DELETE`` trigger needs a function body, which needs dollar
  quoting, which ``db_migrate.split_statements`` refuses outright;
* ``REVOKE UPDATE, DELETE`` is refused by ``db_write._FORBIDDEN_KEYWORDS``.

So a psql session, a superuser, or a future application can still change these
rows. Nothing here may be described as immutable at the database level.

WHAT IT DOES NOT DO
===================
It never connects at import time. It never connects unless ``PGHOST`` is set. It
holds no pool, no long-lived session and no retry loop. It writes no experiment
row, no run row and no artifact — the caller has already done all of that, in the
order documented at :func:`record_submission`.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

from isaac_records.ids import new_record_id

from . import experiment_repository as repo
from . import submissions
from .db_write import write_transaction

__all__ = [
    "IDEMPOTENCY_KEY_MAX",
    "REASON_SUBMISSION",
    "REQUIRED_TABLES",
    "ExistingSubmission",
    "IdempotencyKeyConflict",
    "PostgresSubmissionStore",
    "Q_INSERT_REVISION",
    "Q_INSERT_REVISION_CHANGE",
    "Q_INSERT_RUN_REVISION",
    "Q_INSERT_SUBMISSION",
    "Q_INSERT_SUBMISSION_RUN",
    "Q_LATEST_REVISION",
    "Q_SUBMISSION_BY_KEY",
    "Q_SUBMISSION_BY_SIGNATURE",
    "Q_TABLE_PRESENT",
    "SubmissionAlreadyExists",
    "SubmissionRaceLost",
    "SubmissionRecorded",
    "SubmissionTablesMissing",
    "capability",
    "lookup",
    "store",
]


#: The only ``reason`` ``isaac_experiment_revisions`` admits today. Named here so
#: the Python and the migration's CHECK cannot drift; a test asserts the CHECK lists
#: exactly this.
REASON_SUBMISSION = "submission"

#: The longest client-supplied ``Idempotency-Key`` this API will consider. A key is
#: an opaque client token, so there is no shape to validate — only a bound, so an
#: unbounded header cannot become an unbounded row. 200 is generous next to a UUID
#: (36) or a ULID (26) and small enough that a key is never a payload.
IDEMPOTENCY_KEY_MAX = 200

#: Every relation this module's statements name. Probed BEFORE anything is written,
#: because the image rolls out on merge while migrations are applied separately by
#: the operator — so a build routinely runs against a database its own migration has
#: not reached. See :meth:`PostgresSubmissionStore.tables_present`.
REQUIRED_TABLES: tuple[str, ...] = (
    "isaac_experiment_revisions",
    "isaac_run_revisions",
    "isaac_revision_changes",
    "isaac_submissions",
    "isaac_submission_runs",
)


# --- the statements -----------------------------------------------------------
#
# EVERY ONE OF THEM IS A `SELECT` OR AN `INSERT`. There is no `UPDATE` and no
# `DELETE` in this module, by design and by test:
# `test_no_submission_statement_updates_or_deletes_history` parses this module's
# `Q_*` constants and fails on either verb. That test IS the append-only guarantee
# — see the module docstring for why the database cannot provide one.

#: "Does this relation exist yet?" — the same shape, and the same reasoning, as
#: ``experiment_repository.Q_RUN_TABLE_PRESENT``. ``to_regclass`` ANSWERS ``NULL``
#: for a name that does not resolve instead of raising, and it resolves through the
#: same ``search_path`` the unqualified names below use. The table name is a
#: PARAMETER so that "a deployment missing these tables issues no statement naming
#: one" stays a mechanically checkable property.
Q_TABLE_PRESENT = "SELECT to_regclass(%s::text)"

#: The newest revision of one experiment, or no row. Served by
#: ``isaac_experiment_revisions_no_unique``'s index on
#: ``(experiment_id, revision_no)``, which is why 0003 creates no separate index for
#: this read.
#:
#: It returns ``state`` so the previous unit drafts can be reconstructed for the
#: change diff, and ``content_signature`` so an unchanged re-submission is
#: recognisable even before the submissions table is consulted.
Q_LATEST_REVISION = (
    "SELECT revision_id, revision_no, content_signature, state"
    " FROM isaac_experiment_revisions"
    " WHERE experiment_id = %s"
    " ORDER BY revision_no DESC LIMIT 1"
)

#: THE COLUMN LIST EVERY SUBMISSION READ RETURNS, in one place, because two reads
#: below return it and a hand-maintained second copy is how the tuple unpacking in
#: :func:`_submission_row` silently starts reading the wrong column.
_SUBMISSION_COLUMNS = (
    "submission_id, experiment_id, revision_id, content_signature,"
    " idempotency_key, unit_count, conflict_summary, subject, trust_basis,"
    " submitted_utc"
)

Q_SUBMISSION_BY_SIGNATURE = (
    f"SELECT {_SUBMISSION_COLUMNS} FROM isaac_submissions"
    " WHERE experiment_id = %s AND content_signature = %s"
)

Q_SUBMISSION_BY_KEY = (
    f"SELECT {_SUBMISSION_COLUMNS} FROM isaac_submissions"
    " WHERE experiment_id = %s AND idempotency_key = %s"
)

#: ``ON CONFLICT DO NOTHING RETURNING`` on all three inserts that can lose a race,
#: rather than letting a unique violation raise. The reason is not style: a raised
#: ``UniqueViolation`` would have to be classified from a driver SQLSTATE, and
#: ``db_write`` deliberately reports only the exception CLASS (psycopg2 messages
#: echo the host, the user and the connection string). ``rowcount`` over
#: ``RETURNING`` makes the refusal a value this code reads rather than a message it
#: has to parse.
Q_INSERT_REVISION = (
    "INSERT INTO isaac_experiment_revisions"
    " (revision_id, experiment_id, revision_no, experiment_rev, generation,"
    " state, content_signature, reason, subject, trust_basis)"
    " VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)"
    " ON CONFLICT DO NOTHING RETURNING revision_id"
)

Q_INSERT_RUN_REVISION = (
    "INSERT INTO isaac_run_revisions"
    " (run_revision_id, revision_id, run_id, ordinal, state, rev, generation)"
    " VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)"
)

Q_INSERT_REVISION_CHANGE = (
    "INSERT INTO isaac_revision_changes"
    " (change_id, revision_id, unit_id, address, change_kind)"
    " VALUES (%s, %s, %s, %s, %s)"
)

Q_INSERT_SUBMISSION = (
    "INSERT INTO isaac_submissions"
    " (submission_id, experiment_id, revision_id, content_signature,"
    " idempotency_key, unit_count, conflict_summary, subject, trust_basis)"
    " VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)"
    " ON CONFLICT DO NOTHING RETURNING submission_id, submitted_utc"
)

Q_INSERT_SUBMISSION_RUN = (
    "INSERT INTO isaac_submission_runs"
    " (submission_run_id, submission_id, unit_id, run_id, record_id)"
    " VALUES (%s, %s, %s, %s, %s)"
)


# --- typed outcomes -----------------------------------------------------------


class SubmissionTablesMissing(RuntimeError):
    """The deployment stores durably, and the submission tables are not there yet.

    Raised BEFORE anything is written, from a transaction that has issued only
    ``SELECT``s. The route renders it ``503`` — the same code, and the same
    reasoning, ``storage_unavailable_handler`` uses: the request was well formed,
    the application is working, and a dependency this deployment is configured to
    use is not ready. It IS transient in the sense that matters, because the remedy
    is an operator applying a migration that already exists.
    """


class ExistingSubmission(RuntimeError):
    """Base for the two refusals that carry the submission already on record."""

    def __init__(self, message: str, existing: dict) -> None:
        super().__init__(message)
        self.existing = existing


class SubmissionAlreadyExists(ExistingSubmission):
    """This exact content has already been submitted for this experiment."""


class IdempotencyKeyConflict(ExistingSubmission):
    """This ``Idempotency-Key`` was already used for DIFFERENT content.

    Distinct from :class:`SubmissionAlreadyExists` because the remedy is different
    and a client cannot act on a merged message: the first says "you already did
    this, here is the receipt", the second says "your key is reused, pick a new
    one".
    """


class SubmissionRaceLost(RuntimeError):
    """Another writer took the natural key between this transaction's read and write.

    Carries no payload: the winner's row is read back by the caller in a FRESH
    transaction, because this one has rolled back and reading inside it would
    return the loser's own uncommitted view.
    """


class SubmissionRecorded(dict):
    """A committed submission, as the API reports it. A ``dict`` for one reason.

    It goes straight into a JSON response body, and a dataclass would need a second
    serialiser that could drift from the columns. The keys are exactly
    :func:`_submission_row`'s, plus ``replayed``.
    """


# --- row helpers --------------------------------------------------------------


def _as_document(value: Any) -> dict | None:
    """A ``jsonb`` column as a ``dict``, or ``None`` if it is unusable.

    psycopg2 returns ``jsonb`` as a ``dict``; anything without the adapter
    registered returns text. Both are accepted, with the same tolerance
    ``experiment_repository._row_state`` already applies — one behaviour for one
    situation, rather than two that can disagree.
    """
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
    return value if isinstance(value, dict) else None


def _as_utc_text(value: Any) -> str | None:
    """A ``timestamptz`` column as an ISO-8601 string, or ``None``.

    THE SERVER ASSIGNS THE TIME AND THIS APPLICATION ONLY FORMATS IT. psycopg2
    returns a timezone-aware ``datetime``; a driverless fake may return the string
    it was given. Neither is invented here — a value this cannot read becomes
    ``None`` rather than ``datetime.now()``, because a fabricated submission
    timestamp is exactly the kind of plausible-looking lie this project refuses.
    """
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _submission_row(row: Any) -> dict | None:
    """One ``_SUBMISSION_COLUMNS`` row as the API's submission object."""
    if not row:
        return None
    return {
        "submission_id": row[0],
        "experiment_id": row[1],
        "revision_id": row[2],
        "content_signature": row[3],
        "idempotency_key": row[4],
        "unit_count": int(row[5]) if row[5] is not None else None,
        "conflict_summary": _as_document(row[6]) or {},
        "subject": row[7],
        "trust_basis": row[8],
        "submitted_utc": _as_utc_text(row[9]),
    }


def _run_revision_params(revision_id: str, run: Any) -> tuple:
    """THE ONE PLACE A ``Run`` BECOMES AN ``isaac_run_revisions`` ROW.

    Pure: reads a run, returns a tuple, opens nothing. ``state`` is
    ``Run.to_state()`` verbatim — nothing dropped, nothing reordered — so the
    snapshot is the document, not a summary of it.

    The ``generation`` fallback mirrors ``experiment_repository._run_row_params``
    exactly, and for the same reason: the column is ``NOT NULL`` with no default and
    ``''`` SATISFIES ``NOT NULL``, so the database would accept an empty generation
    in silence. Reusing the model's own rule is the only fallback that is not an
    invention. It is not reachable today — ``Run.__post_init__`` mints one — and is
    written anyway.
    """
    from . import workspace as ws  # noqa: PLC0415 - avoids an import cycle at module load

    return (
        new_record_id(),
        revision_id,
        run.id,
        int(run.ordinal),
        json.dumps(run.to_state(), sort_keys=True),
        int(run.rev),
        run.generation or ws._legacy_generation(run.id),
    )


def _previous_unit_drafts(state: Any) -> dict[str, dict] | None:
    """The previous revision's ``unit_id -> resolved draft`` map, or ``None``.

    ``None`` means "there is no comparable predecessor", which
    :func:`submissions.address_changes` treats as "record no changes" rather than as
    "everything was added". Two different situations produce it and BOTH are honest
    as ``None``: there was no earlier revision at all, or there was one and it could
    not be rehydrated.

    THE SECOND CASE IS CAUGHT RATHER THAN ALLOWED TO PROPAGATE, and the reason is
    specific. ``Experiment.from_state`` reads ``id``, ``title`` and ``created_utc``
    as HARD SUBSCRIPTS, so a stored document missing one raises ``KeyError``. Every
    document this application writes has all three — but a submission must not fail
    because a HISTORICAL row is unreadable. The change list is a convenience over an
    append-only log; the submission is the thing that matters, and degrading the
    first to protect the second is the right trade. The route discloses which case
    occurred so the empty list is never mistaken for "nothing changed".
    """
    from . import workspace as ws  # noqa: PLC0415 - avoids an import cycle at module load

    document = _as_document(state)
    if document is None:
        return None
    try:
        previous = ws.Experiment.from_state(document)
        return submissions.units_by_id(previous.export_units())
    except Exception:  # noqa: BLE001 - see the docstring
        return None


# --- the store ----------------------------------------------------------------


class PostgresSubmissionStore:
    """Append-only submission and revision writes. One short transaction per call.

    Holds no connection, exactly as ``PostgresOrdinaryStore`` does not: every call
    opens one short-lived transaction through ``db_write.write_transaction`` and
    closes it. ``connect_kwargs`` is injectable so the whole shape is exercisable
    against an in-process fake with no driver and no server.
    """

    def __init__(self, env: Mapping[str, str] | None = None, **connect_kwargs: Any) -> None:
        self.env: Mapping[str, str] = os.environ if env is None else env
        self._connect_kwargs = connect_kwargs

    # -- reads ----------------------------------------------------------------

    def preflight(
        self, experiment_id: str, content_signature: str, idempotency_key: str | None
    ) -> dict:
        """ONE read transaction answering the three questions that precede a write.

        Returns ``{"tables_present": bool, "by_signature": row|None,
        "by_key": row|None}``.

        WHY ALL THREE IN ONE TRANSACTION rather than three calls: they are read
        together, they are cheap, and a single transaction means the three answers
        describe one instant. The alternative — three round trips — can report a
        combination that never existed.

        WHY IT IS A SEPARATE TRANSACTION FROM THE WRITE, AND WHAT THAT COSTS. The
        route must be able to refuse **before** it materialises any artifact, and
        materialisation is filesystem work that cannot happen inside a database
        transaction. So the tables can, in principle, be dropped between this read
        and the write; the write then fails and the whole transaction rolls back,
        which is the safe direction. That window is real and is stated rather than
        engineered away, because closing it would mean either holding a transaction
        open across filesystem writes or materialising before checking — and both
        are worse than a refusal that can arrive one moment late.
        """
        with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
            present = True
            for table in REQUIRED_TABLES:
                cursor.execute(policy.check(Q_TABLE_PRESENT), (table,))
                row = cursor.fetchone()
                if not row or row[0] is None:
                    present = False
                    break
            if not present:
                return {"tables_present": False, "by_signature": None, "by_key": None}
            cursor.execute(
                policy.check(Q_SUBMISSION_BY_SIGNATURE), (experiment_id, content_signature)
            )
            by_signature = _submission_row(cursor.fetchone())
            by_key = None
            if idempotency_key is not None:
                cursor.execute(
                    policy.check(Q_SUBMISSION_BY_KEY), (experiment_id, idempotency_key)
                )
                by_key = _submission_row(cursor.fetchone())
        return {
            "tables_present": True,
            "by_signature": by_signature,
            "by_key": by_key,
        }

    def lookup(
        self, experiment_id: str, content_signature: str, idempotency_key: str | None
    ) -> dict:
        """The same three answers, used to read back the winner after a lost race.

        A separate NAME rather than a second call to :meth:`preflight`, because the
        two are read at different moments for different reasons and a reader should
        be able to tell from the call site which one is happening.
        """
        return self.preflight(experiment_id, content_signature, idempotency_key)

    # -- the one write --------------------------------------------------------

    def record_submission(
        self,
        *,
        exp: Any,
        units: Sequence[Any],
        content_signature: str,
        conflict_summary: Mapping[str, Any],
        subject: str | None,
        trust_basis: str,
        idempotency_key: str | None,
    ) -> SubmissionRecorded:
        """Capture a revision and record the submission over it. ONE transaction.

        EVERYTHING OR NOTHING, WITHIN THIS CALL. The revision row, every run
        revision, every change row, the submission row and every submission-run row
        are written inside one transaction, so a fault cannot leave a submission
        pointing at a revision that does not exist, or a revision whose declaration
        never landed. ``db_write.write_transaction`` rolls back on ANY exception,
        including the typed refusals below.

        WHAT IS *NOT* ATOMIC, STATED HONESTLY RATHER THAN GLOSSED. The caller has
        already materialised the export artifacts and saved the experiment state
        BEFORE calling this, and those are filesystem and ``isaac_experiments``
        writes that this transaction cannot enclose. So there is a real window:

            artifacts written -> experiment state saved -> [FAULT] -> no submission

        The surviving state is **recoverable, and that is why the order is this way
        round**. Retrying the submit finds every unit already materialised, skips
        the export entirely (materialised units are never revalidated or rewritten),
        recomputes the SAME content signature — it excludes ``record_id``, ``rev``
        and every timestamp precisely so that it can — and writes the rows.

        *M4 — with one degraded exception, which the recovery story has to own: a
        materialised record that is unreadable, or whose own ``record_id`` disagrees
        with the file carrying it, drops out of its sibling group in
        ``workspace._linkable``, which changes the links composed into its siblings'
        drafts and therefore moves the signature. The retry then looks like new
        content and records a second submission. The claim holds for every readable,
        self-consistent artifact set — which is every non-degraded case — and this
        module does not detect the degraded one.* The
        reverse order would not be recoverable: a submission row referring to
        records that were never written names artifacts that do not exist, and
        nothing could tell that state from a successful submission whose files were
        later deleted.

        THE REVISION NUMBER IS ASSIGNED FROM A READ IN THIS SAME TRANSACTION and is
        protected by ``isaac_experiment_revisions_no_unique``. Two writers computing
        the same next number cannot both land; the loser's insert returns no row,
        raises :class:`SubmissionRaceLost`, and its whole transaction rolls back.

        Raises :class:`SubmissionTablesMissing`, :class:`SubmissionAlreadyExists`,
        :class:`IdempotencyKeyConflict` or :class:`SubmissionRaceLost` — and every
        one of them leaves the database exactly as it was.
        """
        from . import workspace as ws  # noqa: PLC0415 - avoids an import cycle at module load

        repo.PostgresOrdinaryStore.refuse_if_not_persistable(exp)

        experiment_id = exp.id
        state_payload = json.dumps(exp.to_state(), sort_keys=True)
        conflict_payload = json.dumps(dict(conflict_summary), sort_keys=True)
        current_units = submissions.units_by_id(units)
        unit_rows = sorted(
            ((unit.target_id, unit.run_id, unit.current_record_id()) for unit in units),
            key=lambda row: row[0],
        )
        # CHECKED HERE, BEFORE A CONNECTION IS OPENED, because the alternative is a
        # NOT NULL violation from the server on the LAST statement of an otherwise
        # complete transaction — a 503 that says "the database did not answer" about
        # a database that answered perfectly and was right to refuse. The caller
        # materialises every unit before reaching this method; a unit still carrying
        # no record id means that contract was broken, and saying so plainly is
        # better than letting the driver say something misleading.
        unmaterialised = [unit_id for unit_id, _run_id, record_id in unit_rows if not record_id]
        if unmaterialised:
            raise ValueError(
                "every export unit must be materialised before its submission is "
                f"recorded; {len(unmaterialised)} unit(s) carry no record id"
            )
        runs = list(exp.sorted_runs())

        with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
            for table in REQUIRED_TABLES:
                cursor.execute(policy.check(Q_TABLE_PRESENT), (table,))
                row = cursor.fetchone()
                if not row or row[0] is None:
                    # Nothing has been written: only `SELECT`s have been issued, and
                    # the context manager rolls back on the way out regardless.
                    raise SubmissionTablesMissing(
                        "this deployment stores experiments durably, and the "
                        "submission tables have not been created yet"
                    )

            # THE TWO REFUSALS ARE RE-EVALUATED HERE, NOT ONLY IN `preflight`. The
            # preflight ran in an earlier transaction so its answer can be stale by
            # now, and re-reading them inside the writing transaction is what makes
            # "already submitted" a decision about the same instant as the write.
            cursor.execute(
                policy.check(Q_SUBMISSION_BY_SIGNATURE), (experiment_id, content_signature)
            )
            existing = _submission_row(cursor.fetchone())
            if existing is not None:
                raise SubmissionAlreadyExists(
                    "this content has already been submitted", existing
                )
            if idempotency_key is not None:
                cursor.execute(
                    policy.check(Q_SUBMISSION_BY_KEY), (experiment_id, idempotency_key)
                )
                by_key = _submission_row(cursor.fetchone())
                if by_key is not None:
                    raise IdempotencyKeyConflict(
                        "this idempotency key was already used for different content",
                        by_key,
                    )

            cursor.execute(policy.check(Q_LATEST_REVISION), (experiment_id,))
            latest = cursor.fetchone()
            revision_no = int(latest[1]) + 1 if latest else 1
            previous_units = _previous_unit_drafts(latest[3]) if latest else None
            comparable = previous_units is not None

            revision_id = new_record_id()
            cursor.execute(
                policy.check(Q_INSERT_REVISION),
                (
                    revision_id,
                    experiment_id,
                    revision_no,
                    int(exp.rev),
                    exp.generation or ws._legacy_generation(exp.id),
                    state_payload,
                    content_signature,
                    REASON_SUBMISSION,
                    subject,
                    trust_basis,
                ),
            )
            if cursor.rowcount != 1:
                raise SubmissionRaceLost("another writer took this revision number")

            for run in runs:
                cursor.execute(
                    policy.check(Q_INSERT_RUN_REVISION),
                    _run_revision_params(revision_id, run),
                )

            changes = submissions.address_changes(previous_units, current_units)
            for unit_id, address, kind in changes:
                cursor.execute(
                    policy.check(Q_INSERT_REVISION_CHANGE),
                    (new_record_id(), revision_id, unit_id, address, kind),
                )

            submission_id = new_record_id()
            cursor.execute(
                policy.check(Q_INSERT_SUBMISSION),
                (
                    submission_id,
                    experiment_id,
                    revision_id,
                    content_signature,
                    idempotency_key,
                    len(unit_rows),
                    conflict_payload,
                    subject,
                    trust_basis,
                ),
            )
            inserted = cursor.fetchone() if cursor.rowcount == 1 else None
            if inserted is None:
                # A concurrent writer took `(experiment_id, content_signature)` or
                # the idempotency key between the re-read above and this insert.
                raise SubmissionRaceLost("another writer recorded this submission")
            submitted_utc = _as_utc_text(inserted[1]) if len(inserted) > 1 else None

            for unit_id, run_id, record_id in unit_rows:
                cursor.execute(
                    policy.check(Q_INSERT_SUBMISSION_RUN),
                    (new_record_id(), submission_id, unit_id, run_id, record_id),
                )

        return SubmissionRecorded(
            {
                "submission_id": submission_id,
                "experiment_id": experiment_id,
                "revision_id": revision_id,
                "revision_no": revision_no,
                "content_signature": content_signature,
                "idempotency_key": idempotency_key,
                "unit_count": len(unit_rows),
                "conflict_summary": dict(conflict_summary),
                "subject": subject,
                "trust_basis": trust_basis,
                "submitted_utc": submitted_utc,
                "change_count": len(changes),
                # THE DISCLOSURE THAT KEEPS `change_count: 0` HONEST. Zero changes
                # against a readable predecessor means the field values really are
                # identical; zero changes with `changes_comparable: false` means
                # there was nothing to compare against, or the predecessor could not
                # be read. Collapsing the two would let the API assert "nothing
                # changed" about a comparison it never made.
                "changes_comparable": comparable,
                "replayed": False,
            }
        )


# --- selection and capability -------------------------------------------------


def store(env: Mapping[str, str] | None = None) -> PostgresSubmissionStore | None:
    """The submission store for this deployment, or ``None`` if it has no database.

    ``PGHOST`` is the documented feature switch, exactly as it is for
    ``experiment_repository``: the pod sets the standard libpq variables and a local
    checkout or a CI runner sets none.

    **THE GATE IS ``repo._postgres_available``, NOT ``database_configured`` ALONE,
    AND THE DIFFERENCE WAS A MEASURED DEFECT (review item I1).** This used to test
    only ``PGHOST``, while ``experiment_repository.ordinary_store`` additionally
    applies :func:`db_write.pgdatabase_gate`. A deployment with ``PGHOST`` set and
    ``PGDATABASE`` pointing somewhere else therefore built a store here, opened a
    transaction, and had ``WriteRefused`` raised at it from inside
    ``write_transaction`` — an exception no handler in ``create_app`` renders, so the
    submit route answered **HTTP 500** while ``/api/health`` reported
    ``configuration_permits: false, blockers: ['no_durable_storage']`` about the same
    deployment. Two surfaces, one deployment, contradictory answers.

    It calls the SAME FUNCTION rather than repeating its two conditions, deliberately:
    a copy is a second definition that can drift, and the property that matters is
    *equivalence with the experiment repository*, not a particular pair of checks.
    The leading underscore is respected knowingly — the alternative is worse.

    A database that is configured, correctly named, and simply not answering still
    reaches the store, because that cannot be known without connecting; the route
    catches ``WriteRefused`` around the preflight and the write and renders the same
    typed 503.

    **There is deliberately no filesystem fallback**, and that is the one design
    decision in this module a reader is most likely to want to argue with. A
    submission is a durable, attributable declaration; a copy of it in an
    ``emptyDir`` that disappears on the next pod restart is not a weaker version of
    that, it is a false version of it. Refusing with a typed ``503`` tells the
    scientist their declaration was not recorded. Writing it to a file that will
    vanish tells them it was.
    """
    env = os.environ if env is None else env
    if not repo._postgres_available(env):
        return None
    return PostgresSubmissionStore(env)


def lookup(
    experiment_id: str,
    content_signature: str,
    idempotency_key: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Module-level convenience over :meth:`PostgresSubmissionStore.lookup`."""
    selected = store(env)
    if selected is None:
        return {"tables_present": False, "by_signature": None, "by_key": None}
    return selected.lookup(experiment_id, content_signature, idempotency_key)


#: The blockers :func:`capability` can report, as stable machine-readable codes.
BLOCKER_NO_DURABLE_STORAGE = "no_durable_storage"
BLOCKER_NO_ATTRIBUTABLE_ACTOR = "no_attributable_actor"


def capability(env: Mapping[str, str] | None = None) -> dict:
    """What ``GET /api/health`` publishes about submission. CONFIGURATION ONLY.

    IT OPENS NOTHING — no connection, no query, no wait — for the reason the two
    blocks beside it on ``/api/health`` open nothing: that operation is the
    container readiness probe, and a database problem must never be able to change
    its result.

    THE FIELD IS CALLED ``configuration_permits`` AND NOT ``available``, AND THE
    NAME IS THE POINT. Whether a submission would actually succeed depends on
    whether the ``0003``/``0004`` tables exist in that database, and **that cannot
    be known without opening a connection**. Reporting ``available: true`` from
    configuration alone would be exactly the defect ``experiment_storage`` was
    corrected for — a pod claiming ``durable: true`` while every write against it
    failed. So this reports what the deployment is SET UP to permit, says in
    ``basis`` that configuration is all it looked at, and never promises the write
    will land.

    ``actor_trust_basis`` IS SURFACED DELIBERATELY. A deployment configured with the
    fixture verifier can attribute submissions on a basis that is **not proof anyone
    authenticated**, and an operator reading this block must be able to see that
    without reading the deployment manifest. ``null`` means no actor can be
    established at all, which is this build's default everywhere.
    """
    from . import identity  # noqa: PLC0415 - avoids an import cycle at module load

    env = os.environ if env is None else env
    storage = repo.storage_status(env)
    attribution = identity.actor_attribution_status()
    blockers: list[str] = []
    if not storage["durable"]:
        blockers.append(BLOCKER_NO_DURABLE_STORAGE)
    if not attribution["can_attribute"]:
        blockers.append(BLOCKER_NO_ATTRIBUTABLE_ACTOR)
    return {
        "configuration_permits": not blockers,
        "blockers": blockers,
        "basis": "configuration_only",
        "requires_attributable_actor": True,
        "actor_trust_basis": attribution["trust_basis"],
        "verifier_id": attribution["verifier_id"],
    }
