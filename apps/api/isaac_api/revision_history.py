"""The READ path over the append-only submission history. SELECTs only.

WHY THIS IS A SEPARATE MODULE FROM ``submission_store``
======================================================
``submission_store`` is documented, from its first line, as *the durable WRITE
path*, and its central claim is an inventory claim: **every statement it declares
is a ``SELECT`` or an ``INSERT``, and no ``UPDATE`` or ``DELETE`` naming a history
table exists anywhere in this application**. That claim is checked by parsing the
source (``test_submission_store.test_no_submission_statement_updates_or_deletes_history``,
which scans EVERY backend module, so it covers this file too).

Growing that module with a read surface would not break the claim — reads are
already there, in ``preflight`` — but it would blur what the module is *for*, and
"the module with the writes in it" is a much easier thing to review than "the
module with the writes and also the browsing queries". So the split here mirrors
the split this codebase already made once, between ``db_write`` and the read-only
``db_provider``/``db_recon``: same reasoning, one level up.

**A stronger property is available here and is asserted rather than described:
every ``Q_*`` in this module is a ``SELECT``.** ``test_revision_history.py`` pins
it by inventory, the same way the append-only guarantee is pinned. That property
is only cheap to state because this module has no other kind of statement in it.

IT REUSES ``db_write.write_transaction`` UNCHANGED, exactly as
``PostgresSubmissionStore.preflight`` does — same statement policy, same
``PGDATABASE`` gate, same server-side ``current_database()`` re-check, same
short-lived connection, same deterministic close. There is deliberately no new
connection path: a second way to reach this database would be a second thing to
get right. The transaction commits having issued nothing but reads, which is a
no-op, and that is the honest description — this is not a ``READ ONLY``
transaction and must not be described as one. (``db_provider`` and ``db_recon``
issue ``SET TRANSACTION READ ONLY`` and re-verify it server-side; those guarantees
protect the production-derived ``records`` table and are untouched by this file,
which names none of their tables and reuses none of their machinery.)

WHAT IT DOES NOT DO
===================
It writes nothing. It never connects at import time, and never connects unless
``PGHOST`` is set. It returns no stored experiment document over HTTP — see
:meth:`PostgresRevisionReader.revision`, which returns the snapshot to its CALLER
because the diff is computed from it, while the route that renders the detail
never copies it into a response body.

THE ONE THING A CALLER MUST NOT DO WITH THIS MODULE
===================================================
**It must never turn "I could not read the history" into "there is no history".**
Every method here reports ``tables_present`` as a first-class answer, separate from
the rows, precisely so that a caller cannot accidentally collapse the two. An empty
``revisions`` list from this module means *the tables were read and hold nothing for
this experiment*. A caller that renders an empty list for a deployment whose
migrations have not been applied is asserting a fact nobody established.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from . import experiment_repository as repo
from . import submission_store as sstore
from .db_write import write_transaction

__all__ = [
    "DEFAULT_REVISION_LIMIT",
    "PostgresRevisionReader",
    "Q_CHANGES_FOR_REVISION",
    "Q_CHANGE_COUNTS_FOR_REVISION",
    "Q_REVISIONS_FOR_EXPERIMENT",
    "Q_REVISION_BY_NO",
    "Q_REVISION_COUNT",
    "Q_RUN_REVISIONS_FOR_REVISION",
    "Q_SUBMISSION_BY_REVISION",
    "Q_SUBMISSION_RUNS_FOR_SUBMISSION",
    "reader",
]


#: How many revisions one listing returns at most.
#:
#: A BOUND RATHER THAN "EVERY ROW", on the same reasoning the run listing is paged
#: for (``docs/run-scale-measurements.md``): an unbounded read is a read whose cost
#: nobody measured. It is paired with :data:`Q_REVISION_COUNT` so the listing can
#: always state how many revisions EXIST — the same division the notes API already
#: makes, where ``total`` is the record's true total whatever the filter returned.
#: A caller is therefore never left to infer a total from a truncated list.
DEFAULT_REVISION_LIMIT = 200


# --- the statements -----------------------------------------------------------
#
# EVERY ONE OF THEM IS A `SELECT`. There is no `INSERT`, no `UPDATE` and no
# `DELETE` in this module, by design and by test
# (`test_revision_history.test_every_statement_in_the_read_module_is_a_select`).
#
# NONE OF THEM IS A JOIN, and that is a constraint rather than a preference.
# `db_write.WriteStatementPolicy` treats `on` as a table introducer — it has to,
# because `CREATE INDEX ... ON records` was how a statement naming the
# production-derived sample once slipped past it — so `JOIN isaac_submissions s ON
# s.revision_id = ...` is REFUSED: the policy reads the alias `s` as a table this
# application does not own. The rows are therefore fetched separately and stitched
# in Python. Recorded here because the obvious first draft of this module is a join,
# and a future reader deserves to know why it is not one rather than rediscovering
# the refusal.

Q_REVISIONS_FOR_EXPERIMENT = (
    "SELECT revision_id, revision_no, experiment_rev, generation,"
    " content_signature, reason, subject, trust_basis, created_utc"
    " FROM isaac_experiment_revisions"
    " WHERE experiment_id = %s"
    " ORDER BY revision_no DESC LIMIT %s"
)

#: How many revisions this experiment HAS, whatever the bounded listing returned.
Q_REVISION_COUNT = (
    "SELECT count(*) FROM isaac_experiment_revisions WHERE experiment_id = %s"
)

#: How many SUBMISSIONS this experiment has, asked directly rather than inferred
#: from the revision count.
#:
#: WHY BOTH ARE COUNTED, WHEN EVERY SUBMISSION THIS APPLICATION WRITES CARRIES A
#: REVISION. ``record_submission`` writes the revision and the submission in ONE
#: transaction, so through this API the revision count is already the superset and
#: this statement can only ever agree with it. The reason it exists anyway is that
#: the question the discard path asks is not "did this application submit this
#: record" but "does any row anywhere still reference this experiment" — and
#: ``isaac_submissions.experiment_id`` is its OWN foreign key into
#: ``isaac_experiments``, declared by ``0004`` independently of ``0003``'s. A
#: precheck that counted only revisions would be reasoning about one of the two
#: parents' children and calling it both. Rows written by a ``psql`` session are
#: reachable in exactly that way; the FK backstop would catch it, and a precheck
#: that has to be caught by its own backstop is a precheck that is wrong.
#:
#: A SELECT, like every statement in this module. Nothing here removes anything.
Q_SUBMISSION_COUNT_FOR_EXPERIMENT = (
    "SELECT count(*) FROM isaac_submissions WHERE experiment_id = %s"
)

#: One revision, INCLUDING its stored document.
#:
#: The document is fetched because the diff is computed from it. It is not fetched
#: by :data:`Q_REVISIONS_FOR_EXPERIMENT`, deliberately: a listing that dragged N
#: whole experiment snapshots across the wire to render N dates would be paying the
#: largest cost in the schema for the smallest part of the answer.
Q_REVISION_BY_NO = (
    "SELECT revision_id, revision_no, experiment_rev, generation,"
    " content_signature, reason, subject, trust_basis, created_utc, state"
    " FROM isaac_experiment_revisions"
    " WHERE experiment_id = %s AND revision_no = %s"
)

#: The submission over ONE revision. Used by BOTH reads — the detail, and once per
#: listed revision by the listing.
#:
#: **A SECOND, BOUNDED "every submission for this experiment" STATEMENT WAS WRITTEN
#: FIRST AND WITHDRAWN, and the reason is an honesty defect rather than a
#: performance one.** That version paired the two lists in Python after ordering
#: submissions by ``submitted_utc DESC`` under the same ``LIMIT`` as the revision
#: listing. The two orderings are not the same ordering — nothing in the schema ties
#: ``submitted_utc`` to ``revision_no`` — so a revision inside the listing's window
#: whose submission fell outside the submissions' window would have been paired with
#: nothing, and the surface would then have said *"no submission row is recorded
#: against this snapshot"* about a submission that exists. One statement per listed
#: revision, on a unique index, cannot produce that: the pairing is exact by
#: construction, and the sentence stays true.
Q_SUBMISSION_BY_REVISION = (
    f"SELECT {sstore._SUBMISSION_COLUMNS} FROM isaac_submissions"
    " WHERE revision_id = %s"
)

#: ``change_kind -> how many``, for the listing's per-revision summary.
Q_CHANGE_COUNTS_FOR_REVISION = (
    "SELECT change_kind, count(*) FROM isaac_revision_changes"
    " WHERE revision_id = %s GROUP BY change_kind"
)

Q_CHANGES_FOR_REVISION = (
    "SELECT unit_id, address, change_kind FROM isaac_revision_changes"
    " WHERE revision_id = %s ORDER BY unit_id, address"
)

#: One revision's run snapshots.
#:
#: ``state ->> 'label'`` RATHER THAN ``state``. The label is the one thing a reader
#: needs to tell two run snapshots apart, and selecting the whole ``jsonb`` document
#: to read one string from it would pull every recorded value of every run across
#: the wire for a heading. The extraction happens in the SERVER, so nothing this
#: application did not ask for is ever in this process's memory.
Q_RUN_REVISIONS_FOR_REVISION = (
    "SELECT run_revision_id, run_id, ordinal, rev, generation, created_utc,"
    " state ->> 'label'"
    " FROM isaac_run_revisions WHERE revision_id = %s"
    " ORDER BY ordinal, run_id"
)

Q_SUBMISSION_RUNS_FOR_SUBMISSION = (
    "SELECT unit_id, run_id, record_id FROM isaac_submission_runs"
    " WHERE submission_id = %s ORDER BY unit_id"
)


# --- row helpers --------------------------------------------------------------


def _count(row: Any) -> int:
    """One ``count(*)`` row as a non-negative integer, or ``0``.

    FAILS TOWARDS ZERO DELIBERATELY, AND THAT IS SAFE ONLY BECAUSE OF WHERE IT IS
    USED. A ``count(*)`` always returns exactly one row and never ``NULL``, so
    every branch below is defensive; if one were ever reached, ``0`` would mean
    "no history" to the discard precheck, which is the PERMISSIVE direction. It is
    acceptable here — and only here — because the foreign-key backstop refuses the
    delete anyway when a referencing row exists, so a wrong ``0`` costs a
    misdirected error message and never a destroyed history row.
    """
    if not row:
        return 0
    try:
        value = int(row[0])
    except (TypeError, ValueError, IndexError):  # pragma: no cover - defensive
        return 0
    return value if value > 0 else 0


def _revision_row(row: Any, *, with_state: bool) -> dict:
    """One ``isaac_experiment_revisions`` row as this module's revision object.

    ``subject`` and ``trust_basis`` are returned VERBATIM and are never substituted.
    A row written by an unattributable deployment carries ``subject IS NULL`` and
    ``trust_basis = 'unattributed'`` — enforced in both directions by the table's own
    ``CHECK ((trust_basis = 'unattributed') = (subject IS NULL))`` — and the honest
    rendering of that is "no attributable actor was recorded", which is a decision for
    the surface. Inventing a name here, or defaulting one, would put a person's name
    on a declaration they did not make.
    """
    out = {
        "revision_id": row[0],
        "revision_no": int(row[1]),
        "experiment_rev": int(row[2]),
        "generation": row[3],
        "content_signature": row[4],
        "reason": row[5],
        "subject": row[6],
        "trust_basis": row[7],
        "created_utc": sstore._as_utc_text(row[8]),
    }
    if with_state:
        # The stored document, for the diff. NEVER copied into a response body —
        # see the module docstring and `routes._revision_detail`.
        out["state"] = sstore._as_document(row[9])
    return out


def _run_revision_row(row: Any) -> dict:
    return {
        "run_revision_id": row[0],
        "run_id": row[1],
        "ordinal": int(row[2]) if row[2] is not None else None,
        "rev": int(row[3]) if row[3] is not None else None,
        "generation": row[4],
        "created_utc": sstore._as_utc_text(row[5]),
        # `None` when the stored run document carried no label. NOT "Run", not the
        # ordinal, not the id: a heading this module made up is indistinguishable
        # from one the scientist chose.
        "label": row[6] if isinstance(row[6], str) and row[6] != "" else None,
    }


def _change_row(row: Any) -> dict:
    return {"unit_id": row[0], "address": row[1], "change_kind": row[2]}


def _submission_run_row(row: Any) -> dict:
    return {"unit_id": row[0], "run_id": row[1], "record_id": row[2]}


def _decoded_conflict_summary(submission: dict | None) -> dict | None:
    """``conflict_summary`` as an object, whichever way the driver returned it.

    ``submission_store._submission_row`` already applies ``_as_document``; this
    exists for the one shape it cannot cover, a fake or a driver handing back a
    JSON *string*. Both are tolerated exactly as ``_as_document`` tolerates them.
    """
    if submission is None:
        return None
    value = submission.get("conflict_summary")
    if isinstance(value, (str, bytes, bytearray)):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return value if isinstance(value, dict) else {}


# --- the reader ---------------------------------------------------------------


class PostgresRevisionReader:
    """Reads submitted revisions. One short transaction per call, SELECTs only.

    Holds no connection, exactly as :class:`~isaac_api.submission_store.PostgresSubmissionStore`
    does not. ``connect_kwargs`` is injectable so the whole shape is exercisable
    against an in-process double with no driver and no server.
    """

    def __init__(self, env: Mapping[str, str] | None = None, **connect_kwargs: Any) -> None:
        self.env: Mapping[str, str] = os.environ if env is None else env
        self._connect_kwargs = connect_kwargs

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _tables_present(cursor, policy) -> bool:
        """Are all five history relations there?

        The SAME probe ``PostgresSubmissionStore.preflight`` makes, over the SAME
        ``REQUIRED_TABLES`` constant and the SAME parameterised
        ``Q_TABLE_PRESENT`` — reused rather than copied, because two probes that
        could disagree would let the read surface and the write surface report
        different facts about one database.
        """
        for table in sstore.REQUIRED_TABLES:
            cursor.execute(policy.check(sstore.Q_TABLE_PRESENT), (table,))
            row = cursor.fetchone()
            if not row or row[0] is None:
                return False
        return True

    @staticmethod
    def _change_counts(cursor, policy, revision_id: str) -> dict[str, int]:
        cursor.execute(policy.check(Q_CHANGE_COUNTS_FOR_REVISION), (revision_id,))
        return {str(row[0]): int(row[1]) for row in cursor.fetchall()}

    # -- the reads ------------------------------------------------------------

    def history(
        self,
        experiment_id: str,
        content_signature: str,
        limit: int = DEFAULT_REVISION_LIMIT,
    ) -> dict:
        """One transaction answering everything a history listing needs.

        Returns ``{"tables_present", "revisions", "total", "current_submission"}``.

        ``current_submission`` is the submission whose ``content_signature`` equals
        the one the caller computed from the record AS IT IS NOW — i.e. the answer to
        "has this been submitted", over exactly the scope
        ``submissions.SIGNATURE_SCOPE`` names and no wider (the published unit drafts
        and the record's conflict decisions; not the title, the notes or the
        transcript). It reuses
        ``submission_store.Q_SUBMISSION_BY_SIGNATURE``, which is the statement the
        WRITE path already refuses a duplicate submission on, so the read surface and
        the write surface answer that question from one query rather than two that
        could drift.

        WHY ALL OF IT IN ONE TRANSACTION: the answers are read together and are
        rendered together, so one transaction means they describe one instant.
        Three round trips can report a combination that never existed.

        THE PER-REVISION READS COST TWO STATEMENTS EACH — the change counts and the
        submission — and that is stated rather than hidden. Both are bounded by
        ``limit`` (200), both are indexed lookups by ``revision_id``, and both run
        inside the transaction already open. The alternative — grouped statements
        over ``revision_id = ANY(%s)`` — would be two round trips instead of 2N, and
        was not taken for two reasons: it would make the connection double model
        array parameter adaptation, and **no statement anywhere in this application
        currently passes an array parameter**, so it would be the one shape in the
        whole write path whose driver behaviour no committed test and no CI job
        exercises. If a measurement ever shows the round trips matter, that is the
        change to make, with a real PostgreSQL behind it.
        """
        with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
            if not self._tables_present(cursor, policy):
                return {
                    "tables_present": False,
                    "revisions": [],
                    "total": 0,
                    "current_submission": None,
                }

            cursor.execute(
                policy.check(Q_REVISIONS_FOR_EXPERIMENT), (experiment_id, int(limit))
            )
            revisions = [
                _revision_row(row, with_state=False) for row in cursor.fetchall()
            ]

            cursor.execute(policy.check(Q_REVISION_COUNT), (experiment_id,))
            count_row = cursor.fetchone()
            total = int(count_row[0]) if count_row and count_row[0] is not None else 0

            cursor.execute(
                policy.check(sstore.Q_SUBMISSION_BY_SIGNATURE),
                (experiment_id, content_signature),
            )
            current_submission = sstore._submission_row(cursor.fetchone())

            for revision in revisions:
                revision["change_counts"] = self._change_counts(
                    cursor, policy, revision["revision_id"]
                )
                cursor.execute(
                    policy.check(Q_SUBMISSION_BY_REVISION), (revision["revision_id"],)
                )
                # A REVISION WITH NO SUBMISSION IS REPORTED, NOT DROPPED. Every
                # revision this application writes is written in the same
                # transaction as its submission, so `None` is unreachable through
                # any route here — but it is reachable through a psql session, and
                # silently omitting such a row would make the listing disagree with
                # `total` for a reason the reader could never see.
                #
                # **AND IT IS A REAL `None`, NOT A PAIRING THAT FELL OUT OF A
                # WINDOW** — see the note on the statement itself for the version
                # that got this wrong and what it would have said.
                revision["submission"] = sstore._submission_row(cursor.fetchone())

        return {
            "tables_present": True,
            "revisions": revisions,
            "total": total,
            "current_submission": current_submission,
        }

    def presence(self, experiment_id: str) -> dict:
        """DOES ANY HISTORY ROW EXIST FOR THIS EXPERIMENT? Counts only.

        Returns ``{"tables_present", "revision_count", "submission_count"}``.

        THIS IS NOT A HISTORY READ AND MUST NOT GROW INTO ONE. It returns two
        integers and a boolean; it never fetches a ``state`` document, a subject, a
        signature or a change row. Its one caller is the discard precheck, which
        needs to know whether ANY history exists — a question a count answers
        exactly — and which has no business reading the content of history it is
        about to refuse to touch.

        BOTH COUNTS COME FROM ONE TRANSACTION, so they describe one instant. Two
        round trips can report a combination that never existed, and the caller is
        about to make a destructive decision on the pair.

        ``tables_present: False`` IS NOT ``0``, AND THE CALLER MUST NOT COLLAPSE
        THEM. "This deployment has no history tables, so nothing can ever have been
        submitted here" and "the tables are there and this record has no rows" are
        both safe answers for a discard — but the counts are only meaningful on the
        second, and a caller that read ``0`` off an unmigrated deployment would be
        reading a number nobody computed. The same distinction ``revision`` draws
        between "there is no revision 4" and "this deployment cannot see the
        history".
        """
        with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
            if not self._tables_present(cursor, policy):
                return {
                    "tables_present": False,
                    "revision_count": 0,
                    "submission_count": 0,
                }
            cursor.execute(policy.check(Q_REVISION_COUNT), (experiment_id,))
            revision_row = cursor.fetchone()
            cursor.execute(
                policy.check(Q_SUBMISSION_COUNT_FOR_EXPERIMENT), (experiment_id,)
            )
            submission_row = cursor.fetchone()
        return {
            "tables_present": True,
            "revision_count": _count(revision_row),
            "submission_count": _count(submission_row),
        }

    def revision(self, experiment_id: str, revision_no: int) -> dict:
        """One revision, its run snapshots, its recorded changes and its submission.

        Returns ``{"tables_present", "revision"}`` where ``revision`` is ``None`` when
        the tables are there and no such revision number exists for this experiment.
        **Those two are different answers and are never merged**: "there is no
        revision 4" is a fact, and "this deployment cannot see the history" is not.

        The returned object carries the stored ``state`` document, because the diff is
        computed from it. The route that renders this as JSON builds its body field by
        field and never copies ``state`` into it.
        """
        with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
            if not self._tables_present(cursor, policy):
                return {"tables_present": False, "revision": None}

            cursor.execute(
                policy.check(Q_REVISION_BY_NO), (experiment_id, int(revision_no))
            )
            row = cursor.fetchone()
            if not row:
                return {"tables_present": True, "revision": None}
            revision = _revision_row(row, with_state=True)
            revision_id = revision["revision_id"]

            cursor.execute(policy.check(Q_RUN_REVISIONS_FOR_REVISION), (revision_id,))
            revision["run_revisions"] = [
                _run_revision_row(r) for r in cursor.fetchall()
            ]

            cursor.execute(policy.check(Q_CHANGES_FOR_REVISION), (revision_id,))
            revision["changes"] = [_change_row(r) for r in cursor.fetchall()]
            revision["change_counts"] = self._change_counts(cursor, policy, revision_id)

            cursor.execute(policy.check(Q_SUBMISSION_BY_REVISION), (revision_id,))
            submission = sstore._submission_row(cursor.fetchone())
            revision["submission"] = submission
            if submission is not None:
                submission["conflict_summary"] = _decoded_conflict_summary(submission)
                cursor.execute(
                    policy.check(Q_SUBMISSION_RUNS_FOR_SUBMISSION),
                    (submission["submission_id"],),
                )
                revision["submission_runs"] = [
                    _submission_run_row(r) for r in cursor.fetchall()
                ]
            else:
                revision["submission_runs"] = []

        return {"tables_present": True, "revision": revision}


# --- selection ----------------------------------------------------------------


def reader(env: Mapping[str, str] | None = None) -> PostgresRevisionReader | None:
    """The revision reader for this deployment, or ``None`` if it has no database.

    THE GATE IS ``repo._postgres_available``, THE SAME FUNCTION
    ``submission_store.store`` CALLS, and it is called rather than re-implemented for
    the reason recorded there: a copy is a second definition that can drift, and the
    property that matters is *equivalence with the write path*. A deployment where a
    submission cannot be recorded is exactly a deployment where a submission cannot be
    read back, and these two functions must never disagree about which deployment that
    is.

    **There is deliberately no filesystem fallback and no cache.** A submission is a
    durable declaration recorded in one place; answering from anywhere else would be
    answering about something that is not the history.
    """
    env = os.environ if env is None else env
    if not repo._postgres_available(env):
        return None
    return PostgresRevisionReader(env)
