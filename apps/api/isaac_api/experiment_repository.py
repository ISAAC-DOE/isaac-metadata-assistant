"""The persistence seam for ORDINARY-scope experiments.

WHAT THIS IS FOR
================
``POST /api/experiments`` creates an experiment. Where that experiment LIVES is
a deployment property, not a product one, and the route must not know which
answer is in force. This module is the one place that knows.

Two implementations:

* :class:`FilesystemExperimentRepository` — today's behaviour, unchanged. The
  experiment is a directory under ``ISAAC_UI_WORKSPACE``. On the S3DF pod that
  path is an ``emptyDir`` (``docs/deployment.md``), so it is **EPHEMERAL**: it
  survives navigation and reload, and it is gone on a pod restart.
* :class:`PostgresExperimentRepository` — **DURABLE**. The authoritative state
  is additionally written to the application's own ``isaac_experiments`` table,
  and restored into the workspace directory on read. A pod restart or a
  redeployment loses the directory and gets it back.

THE FILESYSTEM IS STILL THE WORKING COPY, AND THAT IS DELIBERATE
================================================================
Every other route in this application reads a record through
``ws.load_experiment`` and writes it through ``Experiment.save`` /
``save_versioned``, and export writes artifacts into the record's own
``records/`` directory. Replacing that with database reads everywhere would be a
rewrite of the whole record path — the opposite of the bounded change this work
is authorized as.

So Postgres is the **system of record for authoritative experiment state**, and
the workspace directory is a cache of it:

* every ordinary-scope ``save()`` writes through to the database
  (:func:`~isaac_api.workspace.Experiment.save`, one hook, ordinary scope only);
* every ordinary-scope list, and a miss on an ordinary-scope load, hydrates any
  row whose directory is not there.

STATE THE LIMIT PLAINLY. Exported ARTIFACTS (``records/<id>.json`` and its
evidence sidecar) live only in the workspace directory and are NOT in the
database. A pod restart therefore restores an exported record's state — including
``record_id`` — while its artifact files are gone. The artifact readers already
tolerate exactly that (``routes._read_artifact_json`` returns ``None``,
``dependencies.artifact_state`` reports ``stale``), so this degrades to a state
the app already handles rather than to a crash. Persisting artifacts is a
separate slice and is deliberately not in this one.

THE INVARIANT THAT MATTERS MOST
===============================
**A tutorial session's records never reach the database.** It is enforced three
times, at three different levels, because one of them being wired wrongly must
not be enough:

1. the hook in ``workspace.Experiment.save`` fires only when
   ``session_id is None``;
2. :meth:`PostgresOrdinaryStore.persist` RAISES on a non-``None``
   ``session_id`` — so a future caller that reaches it directly is refused, not
   merely unusual;
3. it RAISES on a canonical example id whatever the scope, so the five built-in
   examples can never be persisted even if someone re-materialised one into the
   ordinary workspace by hand.

Guard 3 is also what keeps a claim three product surfaces make true — see
``test_tutorial_scope.py::test_create_experiment_has_no_caller_in_the_api_package``.

WHAT HAPPENS WHEN THE DATABASE IS CONFIGURED AND DOES NOT ANSWER
================================================================
RE-DATED 2026-08-09. This said "the state the deployed pod is in RIGHT NOW" —
true then, false since Dean applied ``0001_experiments``; see
``docs/evidence/hosted-0001-verification-2026-08-09.md``. It is still the state
of a fresh or rolled-back deployment and of the window before ``0002``, where
``PGHOST`` is set, no migration runs at boot, and a missing table raises.

Before this was handled, that turned three previously database-free operations
into unhandled 500s: ``GET /api/experiments`` (My Experiments rendered "Backend
Not Running"), ``GET /api/experiments/<id>`` (a clean 404 became a 500) and
``POST /api/experiments``. The same three 500s would have come back on any
transient outage, permanently — a read path that had never touched a database
had acquired a hard dependency on one.

THE RULE THAT REPLACES IT, and the four parts are deliberately different:

* **THE LIST DEGRADES, AND IT NOW SAYS SO IN BAND.** Hydration is an
  optimisation — it restores directories a restart threw away. A failed hydration
  falls back to the filesystem view and ``GET /api/experiments`` continues, so a
  list stays a list. A short list is INCOMPLETE; it never asserts that the rows it
  omits do not exist. It no longer leaves that to be inferred either: an
  incomplete hydration pass is reported as an ``incomplete`` block on the list
  response, naming which of the two failures occurred and stating that HOW MANY
  rows are missing is unknown. Narrowing the catch so the list raised instead was
  considered and rejected — a scientist with three readable records should still
  see three. See ``workspace.HydrationOutcome``.
* **A SINGLE-RECORD READ DOES NOT DEGRADE WHEN THE STORE MIGHT BE HOLDING THE
  RECORD, AND THAT IS A CORRECTION.** This paragraph used to say "a miss stays a
  404" and count it a virtue. It was measured wrong on the deployed application:
  moments after a rollout, a record screen claimed "This experiment id is not in
  the workspace — it may not have been created yet" about a record that answered
  ``200`` seconds later. An ``emptyDir`` workspace plus a durable row means "no
  directory" no longer implies "no record", so a 404 issued without reading the
  database is a false statement about a scientist's work.
  ``workspace.load_experiment`` lets that outage propagate and the route renders
  ``503`` — true, retryable, and already typed.
* **AND THE TWO FAILURES A READ CAN HIT ARE NOT THE SAME FAILURE.** The rule is
  NOT "any storage failure becomes a 503"; it is **503 only when the store might
  be holding the record and we could not find out**. Two cases, told apart at the
  point the failure is classified (:func:`is_undefined_table`):

  - **The relation does not exist** — the migration has not been applied. No
    durable row *can* exist, the filesystem is the whole truth, and a miss is
    therefore TRUE. :class:`StorageNotProvisioned` is raised, hydration reports
    "restored nothing" — which is complete rather than ambiguous — and the honest
    ``404`` is the answer it always was. Pinned by ``.github/workflows/ci.yml``'s
    ``Prove the app DEGRADES when the migration has not been applied yet``.
  - **The store did not answer** — connection refused, mid-failover, timeout,
    driver failure. Durable rows may exist and we could not look, so a ``404``
    would be a lie. :class:`StorageUnavailable`, rendered ``503``.

  The classification FAILS CLOSED: anything not positively identified as
  "relation absent" is treated as unavailable, because guessing "absent" re-opens
  the exact defect above.

  A genuine miss, and every deployment with no database at all, is unaffected by
  either branch.
* **WRITES DO NOT DEGRADE EITHER.** A failed durable write raises :class:`StorageUnavailable`,
  which ``isaac_api.app`` renders as a typed ``503``. Degrading a write to the
  filesystem would be worse than failing it: the reader has been TOLD their work
  is durable, and a silent ephemeral write takes that promise away without
  telling them. Failing loudly is the only honest option.

**AND IT IS DISCLOSED.** Any failure is recorded in this process
(:func:`storage_failure`) and :func:`storage_status` then reports
``durable: false`` with ``state: "unavailable"``, which is what stops the UI
promising durability. A later success clears it, so a transient outage heals
instead of marking the deployment broken for the life of the pod.

TWO LIMITS OF THAT DISCLOSURE, STATED RATHER THAN GLOSSED:

1. **It is PROCESS-LOCAL.** Each replica observes its own failures. With more
   than one replica, a health read answered by a healthy process cannot know
   about a sibling's outage.
2. **The FIRST health read after a process start says ``durable: true``**, because
   nothing has been attempted yet and ``/api/health`` is the readiness probe and
   must never open a connection. On a persistently broken deployment the first
   experiment read trips the flag, so every subsequent health read is correct;
   the optimistic answer is confined to the window before anything has been
   tried.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Protocol

from . import workspace as ws
from .db_write import WriteRefused, database_configured, pgdatabase_gate, write_transaction

__all__ = [
    "BACKEND_FILESYSTEM",
    "BACKEND_POSTGRES",
    "NEW_EXPERIMENT_SOURCE_DESCRIPTION",
    "RUN_AUTHORITY_COMPLETE",
    "RUN_AUTHORITY_MISMATCH",
    "RUN_AUTHORITY_NEVER_PROJECTED",
    "RUN_AUTHORITY_STALE",
    "RUN_AUTHORITY_STATES",
    "RUN_AUTHORITY_UNAVAILABLE",
    "RUN_ROWS_AUTHORITATIVE_ENV",
    "SQLSTATE_UNDEFINED_TABLE",
    "STORAGE_READ_FAILED_MESSAGE",
    "STORAGE_RESTORE_FAILED_MESSAGE",
    "STORAGE_STATE_DURABLE",
    "STORAGE_STATE_EPHEMERAL",
    "STORAGE_STATE_UNAVAILABLE",
    "STORAGE_WRITE_FAILED_MESSAGE",
    "DurableWriteConflict",
    "ExperimentRepository",
    "FilesystemExperimentRepository",
    "HydrationSkippedRows",
    "NotPersistable",
    "PostgresExperimentRepository",
    "PostgresOrdinaryStore",
    "StorageNotProvisioned",
    "StorageUnavailable",
    "blank_draft",
    "forget_run_authority",
    "forget_run_table_presence",
    "forget_storage_failure",
    "is_undefined_table",
    "ordinary_store",
    "repository",
    "resolve_run_authority",
    "run_authority_summary",
    "run_rows_authoritative",
    "run_table_seen",
    "storage_failure",
    "storage_status",
]


BACKEND_FILESYSTEM = "filesystem"
BACKEND_POSTGRES = "postgres"

#: The three answers ``storage_status`` can give to "where does a new experiment
#: go, and is it going there". They are NAMED rather than left to be re-derived
#: from the two booleans, because the UI has to branch on them and a truth table
#: reconstructed at each call site is a truth table that eventually disagrees
#: with itself.
#:
#: ``ephemeral``   — no database is configured. The workspace directory is all
#:                   there is, and on the pod that directory is an ``emptyDir``.
#: ``durable``     — a database is configured, correctly named, and nothing has
#:                   failed against it in this process.
#: ``unavailable`` — a database is configured and this application is NOT storing
#:                   experiments in it: either the ``PGDATABASE`` gate refused it,
#:                   or a durable operation has failed in this process. The reader
#:                   must not be told their work is durable in this state.
STORAGE_STATE_EPHEMERAL = "ephemeral"
STORAGE_STATE_DURABLE = "durable"
STORAGE_STATE_UNAVAILABLE = "unavailable"


class NotPersistable(RuntimeError):
    """A record that must never be written to the application database was offered.

    Raised rather than ignored. Silently dropping such a write would leave the
    caller believing durable state exists when it does not, and would turn the
    tutorial-isolation invariant into something a test could only observe by its
    absence.
    """


class StorageUnavailable(RuntimeError):
    """A durable write was attempted, and the configured database did not take it.

    DISTINCT FROM :class:`NotPersistable`, and the distinction is the whole point.
    ``NotPersistable`` is a REFUSAL — the record must never be stored, the app is
    working exactly as designed, and no amount of waiting changes it.
    ``StorageUnavailable`` is an OUTAGE — the record should have been stored, and
    was not, for a reason outside this application: the table has not been created
    yet, the server is unreachable, the credentials changed. One is a permanent
    property of the record; the other is a temporary property of the deployment.
    Rendering them as the same HTTP status would tell an operator to fix the wrong
    thing.

    ``isaac_api.app`` registers a handler that turns this into a typed ``503``.
    It carries a FIXED, path-free, credential-free message for exactly the reason
    :class:`~isaac_api.db_write.WriteRefused` does: it reaches a response body, and
    driver messages echo the host, the user and the connection string. The
    underlying exception is chained (``raise ... from exc``) so a server log still
    has the cause; only the CLASS NAME is ever kept in process state.
    """


class StorageNotProvisioned(RuntimeError):
    """The durable store's own table does not exist, so it is holding NOTHING.

    THE FOURTH FAILURE, AND IT EXISTS BECAUSE CI CAUGHT IT BEING CONFLATED WITH
    THE SECOND. :class:`StorageUnavailable` used to cover this case as well —
    both were "the database did not give us rows" — and once a failed READ began
    surfacing as a ``503`` that conflation turned an honest ``404`` into a false
    outage. The two situations are not the same fact about the world:

    * :class:`StorageUnavailable` — the relation may well exist and be full of
      rows; we could not reach it, so we DO NOT KNOW whether the record is there.
      A ``404`` would assert something unknown, so the honest answer is ``503``.
    * :class:`StorageNotProvisioned` — the relation does not exist. Not "we could
      not read it": there is nothing to read, because the migration has not been
      applied and this application has therefore never durably stored anything.
      The workspace filesystem is the entire truth, exactly as it was before
      durable storage existed, and a miss is TRUE. The honest answer is ``404``.

    WHY IT IS DELIBERATELY NOT A SUBCLASS OF :class:`StorageUnavailable`. Every
    handler that means "an outage happened" — ``app``'s ``503`` handler,
    ``workspace._hydrate_ordinary_scope_or_raise``'s re-raise — is written as
    ``except StorageUnavailable``. A subclass would be caught by all of them and
    would silently restore the very 503 this class exists to prevent, while
    *looking* like a distinction had been drawn.

    IT IS A READ-PATH CLASSIFICATION ONLY, and that asymmetry is intentional. A
    WRITE against an absent relation still raises :class:`StorageUnavailable` and
    still fails loudly as a typed ``503``: for a write, "the table is not there"
    means the work cannot be kept, which is an outage the operator must fix, not
    a truthful nothing. Only a read can honestly conclude "there is nothing to
    find" from an absent relation.

    IT IS STILL RECORDED AS A STORAGE FAILURE (:func:`storage_failure`), so
    ``/api/health`` reports ``durable: false`` and the UI stops promising
    durability. An unapplied migration is a real deployment problem and it is
    disclosed as one; it is simply not a reason to doubt the ``404``, because on
    an unmigrated deployment there is genuinely no durable record to find.
    """


class HydrationSkippedRows(RuntimeError):
    """A hydration pass REFUSED a stored row it read, and finished the loop anyway.

    THE OUTCOME THAT USED TO BE SILENT, AND IT IS A FIFTH ONE RATHER THAN A CASE
    OF THE OTHER FOUR. :meth:`PostgresOrdinaryStore.hydrate` skips a row whose
    state document is filed under an id the document itself does not carry:
    writing a directory named one thing and holding another is worse than not
    writing it, so the refusal is right. What was wrong is what the refusal LOOKED
    like from outside — the loop kept running, the pass returned normally,
    ``workspace.HydrationOutcome.complete`` was ``True``, the list disclosed
    nothing, and a by-id read of the skipped record answered exactly the ``404``
    this whole design exists to stop. The ABORT hole was closed and this one was
    left open while the prose said otherwise.

    SO THE SKIP IS COUNTED AND RAISED AT THE END OF THE PASS, after every row that
    COULD be restored has been. That ordering is the difference between this and an
    abort: one unusable row costs only itself, and every row after it still lands.
    ``workspace._hydrate_ordinary_scope``'s "anything else" arm turns this into
    ``restore_failed`` — which the list discloses in band and the single-record read
    raises on.

    IT IS NOT A SUBCLASS OF :class:`StorageUnavailable`, for the same reason
    :class:`StorageNotProvisioned` is not: nothing about the storage failed. It is
    likewise NOT recorded by :func:`storage_failure`, so ``/api/health`` goes on
    reporting ``durable`` — truthfully, because a write against that database would
    still succeed. The list response is again the only place the shortfall shows.

    ``count`` IS NOT A COUNT OF MISSING RECORDS and must never be rendered as one.
    It is how many rows THIS PASS refused. How many records a reader is missing is
    a different question, and no partial pass can answer it — which is why
    ``missing_count`` stays ``null`` on the wire.
    """

    def __init__(self, count: int) -> None:
        super().__init__("a hydration pass refused a stored row it could not place")
        #: How many rows this pass refused. Diagnostic only; never rendered.
        self.count = count


class DurableWriteConflict(RuntimeError):
    """The database ANSWERED, and it declined this particular write.

    THE THIRD FAILURE, AND ALL THREE ARE DELIBERATELY DIFFERENT. The distinction
    :class:`StorageUnavailable` draws against :class:`NotPersistable` is drawn once
    more here, one step further out:

    * :class:`NotPersistable` — this record may NEVER be stored. A permanent
      property of the record. Nobody can fix it and nobody should try.
    * :class:`StorageUnavailable` — the record should have been stored and the
      database did not take it: unreachable, un-migrated, credentials changed. A
      temporary property of the DEPLOYMENT. An operator fixes it.
    * :class:`DurableWriteConflict` — the record should have been stored, the
      database took the request, evaluated it, and refused it because the stored
      document has moved on since this copy was read. A property of the
      CONCURRENCY, and the only one of the three the CLIENT can resolve — by
      re-reading and retrying, which is exactly what ``412 stale_write`` means.

    Rendering it as a ``503`` would tell an operator to go and look at a database
    that is behaving perfectly, and would tell the client to wait rather than to
    refresh. So it is NOT recorded as a storage failure either: the round trip
    worked, and ``/api/health`` must not report an outage because two writers
    raced.

    ``stored_state`` is the document the row ACTUALLY holds, read back inside the
    SAME transaction that refused the write. The route uses it to report the true
    current rev and ETag — reporting the losing write's own (already bumped) rev
    would echo a version that exists nowhere.

    ``experiment_id`` is carried SEPARATELY from ``stored_state`` on purpose. It
    is always known at the raise site, whereas the read-back can fail — and the
    handler of last resort (``routes.durable_write_conflict_handler``) has no
    experiment of its own to fall back on. Without it that handler emitted
    ``experiment_id: null`` where every other ``stale_write`` body carries a
    string, which is a body a client would have to special-case.
    """

    def __init__(
        self, stored_state: dict | None = None, *, experiment_id: str | None = None
    ) -> None:
        super().__init__(
            "the stored experiment has moved on since this copy was read; "
            "this write was not applied"
        )
        #: The winner's state document, or ``None`` if it could not be read back.
        self.stored_state = stored_state
        #: The id of the record whose write was refused. Known at the raise site
        #: even when the read-back returns nothing.
        self.experiment_id = experiment_id

    def current_experiment(self, fallback: "ws.Experiment") -> "ws.Experiment":
        """The experiment as the DATABASE holds it, or ``fallback`` unchanged.

        Fails SOFT rather than raising: this is only ever called while rendering an
        error response, and a failure to parse the winner's row must not turn a
        clean ``412`` into a ``500``. The id is re-checked because a row filed
        under one id holding another describes a different record, and the rest of
        this module already refuses to act on that shape (see :meth:`hydrate`).
        """
        state = self.stored_state
        if not isinstance(state, dict) or state.get("id") != fallback.id:
            return fallback
        try:
            return ws.Experiment.from_state(state, session_id=fallback.session_id)
        except (KeyError, TypeError, ValueError):  # pragma: no cover - defensive
            return fallback



class DiscardRefusedByHistory(RuntimeError):
    """The database ANSWERED, and it refused to delete an experiment row.

    THE FOURTH FAILURE, AND IT IS THE FOREIGN-KEY BACKSTOP FIRING. Discard is
    gated in the route: it refuses before writing anything if any revision or
    submission row exists for the record. That precheck is the mechanism; THIS is
    what happens if the precheck is ever wrong.

    No migration in this repository writes an ``ON DELETE`` clause, so the SQL
    default ``NO ACTION`` applies to every foreign key into ``isaac_experiments``
    — ~~including the four that ``0003_revisions`` and ``0004_submissions``
    declare~~ — **including the TWO of them that those migrations declare, which
    is a correction and not a rewording.** Re-measured over the SQL bodies with the
    comment lines stripped: ``0003``/``0004`` declare SIX foreign keys between
    them, and exactly two point at ``isaac_experiments`` —
    (the reviewer's own first pass at this sentence said FIVE and was wrong by one,
    which is why the count now lives in an executing test rather than in prose:
    ``test_the_FK_BACKSTOP_is_TWO_direct_keys_and_the_rest_are_TRANSITIVE``) —
    ``isaac_experiment_revisions_experiment_fk`` and
    ``isaac_submissions_experiment_fk``. The other four
    (``isaac_run_revisions_revision_fk``, ``isaac_revision_changes_revision_fk``,
    ``isaac_submissions_revision_fk``, ``isaac_submission_runs_submission_fk``)
    point at ``isaac_experiment_revisions`` and ``isaac_submissions``, so they
    cannot refuse
    an ``isaac_experiments`` delete on their own and counting them here overstated
    the backstop by a factor of two in the one docstring that argues for it.

    **THE GUARANTEE IS UNCHANGED, AND IT IS TRANSITIVE RATHER THAN DIRECT** — which
    is the reason the miscount did not become a hole. Every one of those four
    requires a parent in ``isaac_experiment_revisions`` or ``isaac_submissions``,
    and each of those two carries its own ``NOT NULL`` foreign key into
    ``isaac_experiments``. So a history row for an experiment implies a row that
    directly blocks that experiment's delete, and the two direct keys are
    sufficient. Deleting an experiment row that still has a revision or a
    submission is therefore REFUSED BY THE SERVER, the whole transaction rolls
    back, and the two run-side deletes issued before it are undone with it.
    Append-only history survives a defect in this application's own reasoning,
    which is the only kind of guarantee worth having about it.

    IT IS NOT RECORDED AS A STORAGE FAILURE, for :class:`DurableWriteConflict`'s
    reason: the round trip worked and the server behaved exactly as designed, so
    ``/api/health`` must not start reporting an outage over it.

    IT DELIBERATELY CARRIES NO ROW COUNT AND NO ROW. The refusal proves that at
    least one referencing row exists; it does not say how many, in which table, or
    what they contain, and this application must not go looking — reading
    submission history to explain a refusal is a different operation with a
    different authorization.
    """

    def __init__(self, experiment_id: str | None = None) -> None:
        super().__init__(
            "the database refused to remove this experiment because history rows "
            "still reference it; nothing was removed"
        )
        #: The id whose removal was refused. Known at the raise site.
        self.experiment_id = experiment_id


# --- the degradation this process has actually observed -----------------------
#
# ONE MODULE GLOBAL, and it holds an exception CLASS NAME — never a message, a
# host, a path or a credential. It exists so `/api/health` can report a database
# problem WITHOUT opening a connection: the health handler is the container
# readiness probe, so it must never dial anything, but it must also not keep
# promising durability after a durable write has demonstrably failed.
#
# It is deliberately not a counter, a timestamp or a history. The only question
# any caller asks is "has a durable operation failed since the last one
# succeeded", which is one bit plus a label for the report.

_storage_failure: str | None = None


def _note_storage_failure(exc: BaseException) -> None:
    """Record that a durable operation failed. Keeps the exception CLASS NAME only."""
    global _storage_failure
    _storage_failure = type(exc).__name__


def _note_storage_success() -> None:
    """Record that a durable operation succeeded, clearing any earlier failure.

    CLEARING MATTERS AS MUCH AS SETTING. Without it a single transient blip would
    mark the deployment as unavailable for the life of the process, so the UI
    would go on telling a reader their work is not durable long after it was — a
    false claim in the other direction, and one nothing would ever correct.
    """
    global _storage_failure
    _storage_failure = None


def storage_failure() -> str | None:
    """The class name of the last durable-storage failure in this process, or ``None``."""
    return _storage_failure


def forget_storage_failure() -> None:
    """Test seam: drop the observation so cases cannot leak into one another.

    Named for what it does rather than ``reset_...``: this application uses
    "reset" for the guarded destructive workspace operation, and reusing the word
    for a one-variable test helper invites exactly the misreading that word has
    caused here before.
    """
    _note_storage_success()


#: The two fixed, path-free bodies a durable-storage outage can produce. BOTH are
#: literals rather than one formatted string, so neither can acquire a host, a
#: path, a user or a driver message by accident — the property
#: ``test_the_storage_error_body_names_no_host_path_user_or_driver_message``
#: asserts.
#:
#: THERE ARE TWO OF THEM BECAUSE THERE WAS ONE, AND IT WAS WRONG HALF THE TIME.
#: The single message said "did not accept the write. Nothing was saved" and was
#: raised by :meth:`PostgresOrdinaryStore.hydrate` as well — a READ. That never
#: reached a client while a failed read was swallowed, so the inaccuracy was
#: invisible; the moment a failed read became a ``503`` (see
#: ``workspace.load_experiment``) it would have told a reader their save had been
#: lost when nothing had been saved and nothing was at risk. A reader who is told
#: their work was not saved does something about it.
STORAGE_WRITE_FAILED_MESSAGE = (
    "This deployment stores experiments in its own database, and that "
    "database did not accept the write. Nothing was saved."
)
STORAGE_READ_FAILED_MESSAGE = (
    "This deployment stores experiments in its own database, and that "
    "database could not be read just now. Nothing was changed, and this is "
    "usually temporary — try again."
)
#: THE THIRD, AND IT IS HERE FOR THE SAME REASON THE SECOND IS. A hydration pass
#: can fail to represent every stored row with the database ANSWERING PERFECTLY:
#: writing one working copy failed (a full ``emptyDir``), or a row was refused as
#: unplaceable (:class:`HydrationSkippedRows`), or the store could not be resolved
#: at all. Reporting any of those with :data:`STORAGE_READ_FAILED_MESSAGE` would
#: tell an operator the database could not be read, sending them to look at a
#: database that is fine; reporting them with :data:`STORAGE_WRITE_FAILED_MESSAGE`
#: would tell a reader their save was lost when nothing was being saved. It names
#: no path — the directory it failed to write is a server path, and none of these
#: literals may ever carry one.
#:
#: IT DELIBERATELY DOES NOT SAY "usually temporary — try again", WHICH THE OTHER
#: TWO READ-SIDE MESSAGES DO. A refused connection often clears by itself; a full
#: disk and an unplaceable row do not, and this state persists across every retry
#: until someone changes the deployment. Telling a reader to try again would be
#: advice that cannot work, offered in the one state where the honest answer is
#: that the server does not know whether their record exists. It also stops short
#: of promising the opposite — "needs a server-side fix" is what is known.
STORAGE_RESTORE_FAILED_MESSAGE = (
    "This deployment stores experiments in its own database, and this server "
    "could not finish restoring its own working copy of every stored experiment, "
    "so it cannot say whether this record exists. Nothing was changed. Retrying "
    "may not clear this on its own — if it persists, it needs a server-side fix."
)
#: THE FOURTH, AND IT IS THE ONLY ONE THAT DESCRIBES A REMOVAL. The write wording
#: ends "Nothing was saved", which is exactly backwards for an operation whose
#: whole purpose is to stop something being saved: a reader told "nothing was
#: saved" about a failed discard would reasonably conclude the discard had worked.
#: Fixed and path-free for the same reason the other three are.
STORAGE_DISCARD_FAILED_MESSAGE = (
    "This deployment stores experiments in its own database, and that "
    "database did not accept the removal. Nothing was discarded, and the "
    "experiment is still there."
)


def _unavailable(exc: BaseException, message: str = STORAGE_WRITE_FAILED_MESSAGE) -> StorageUnavailable:
    """Record ``exc`` and build the fixed, path-free error the caller should raise.

    ``message`` defaults to the WRITE wording so every existing raise site keeps
    the body it had; the read path passes :data:`STORAGE_READ_FAILED_MESSAGE`.
    """
    _note_storage_failure(exc)
    return StorageUnavailable(message)


#: PostgreSQL's SQLSTATE for ``undefined_table``: "relation ... does not exist".
#: The server's own code for the one failure that means THE MIGRATION HAS NOT BEEN
#: APPLIED, as opposed to the several that mean the server did not answer.
SQLSTATE_UNDEFINED_TABLE = "42P01"


def is_undefined_table(exc: BaseException) -> bool:
    """Whether ``exc`` POSITIVELY identifies "that relation does not exist".

    THE MECHANISM IS THE SQLSTATE, NOT THE EXCEPTION CLASS AND NEVER THE MESSAGE.
    Three reasons, in order of weight:

    1. It is the SERVER's statement about what happened, not the driver's
       rendering of it. ``42P01`` is fixed by the PostgreSQL protocol; a class
       hierarchy and a message are not.
    2. It needs NO DRIVER IMPORT. ``psycopg2`` is imported lazily throughout this
       package precisely because it may be absent (``db_write.connect_psycopg2``
       says so, and it is absent from the developer venv this was written in), so
       ``except psycopg2.errors.UndefinedTable`` cannot even be written at module
       scope here. ``db_provider.TIMEOUT_EXCEPTION_NAMES`` solves the same problem
       by matching exception class NAMES; the SQLSTATE is strictly better where it
       is available, because it is one exact value rather than an open set of
       names that a driver upgrade can extend or rename.
    3. It is identical across ``psycopg2`` (``.pgcode``, ``.diag.sqlstate``) and
       ``psycopg`` 3 (``.sqlstate``), so all three spellings are read and no
       version pin is implied.

    A MESSAGE MATCH IS NOT USED AND MUST NOT BE ADDED. "relation ... does not
    exist" is localised, is a substring of unrelated errors, and is exactly the
    kind of match that turns a driver upgrade into a false ``404``.

    THIS FUNCTION FAILS CLOSED. It returns ``True`` only for a value it read and
    recognised. An exception carrying no SQLSTATE at all — a socket error, a
    ``TimeoutError``, a driver bug, an error class this build has never seen —
    returns ``False`` and is therefore treated as an OUTAGE. That direction is
    chosen deliberately: a wrong "unavailable" costs a retry, while a wrong
    "absent" tells a scientist their work does not exist, which is the defect
    this whole branch exists to stop.

    IT DOES NOT WALK ``__cause__`` OR ``__context__``. The exception it is given
    is the driver's own, raised straight through ``db_write.write_transaction``
    (which re-raises unwrapped). If a future layer wraps it and hides the
    SQLSTATE, this returns ``False`` and the caller reports an outage — the safe
    direction, and a visible one.
    """
    for attribute in ("pgcode", "sqlstate"):
        if str(getattr(exc, attribute, "") or "").strip() == SQLSTATE_UNDEFINED_TABLE:
            return True
    diagnostics = getattr(exc, "diag", None)
    return (
        str(getattr(diagnostics, "sqlstate", "") or "").strip() == SQLSTATE_UNDEFINED_TABLE
    )


#: PostgreSQL's SQLSTATE for ``foreign_key_violation``. The server's own code for
#: the one refusal that means A ROW STILL REFERENCES THIS ONE — which, for the
#: discard path, means append-only history exists for a record the route had
#: concluded had none.
SQLSTATE_FOREIGN_KEY_VIOLATION = "23503"


def is_foreign_key_violation(exc: BaseException) -> bool:
    """Whether ``exc`` POSITIVELY identifies a foreign-key refusal.

    Written as an exact copy of :func:`is_undefined_table`'s mechanism rather than
    as a variation on it, and for the same three reasons: the SQLSTATE is the
    SERVER's statement, it needs no driver import, and it is spelled identically
    across ``psycopg2`` and ``psycopg`` 3. A message match is not used and must not
    be added.

    IT FAILS CLOSED, and the closed direction here is the opposite of the one
    :func:`is_undefined_table` chooses, because the consequences are opposite. An
    exception carrying no recognisable SQLSTATE returns ``False`` and is therefore
    reported as a storage OUTAGE (``503``) rather than as a history refusal
    (``409``). Both answers say the same operational thing — nothing was removed —
    so the cost of the wrong one is a misdirected diagnosis, never a destroyed row.
    """
    for attribute in ("pgcode", "sqlstate"):
        if str(getattr(exc, attribute, "") or "").strip() == SQLSTATE_FOREIGN_KEY_VIOLATION:
            return True
    diagnostics = getattr(exc, "diag", None)
    return (
        str(getattr(diagnostics, "sqlstate", "") or "").strip()
        == SQLSTATE_FOREIGN_KEY_VIOLATION
    )


def _not_provisioned(exc: BaseException) -> StorageNotProvisioned:
    """Record ``exc`` and build the "there is no table, so there is nothing" error.

    Recorded exactly like an outage — :func:`storage_status` must report
    ``durable: false`` on an unmigrated pod, and it is a durable-storage failure
    by any reading. What differs is what the READ concludes from it, not whether
    it is disclosed. The message is a fixed, path-free literal for the same reason
    the other two are, even though this one is never rendered into a response.
    """
    _note_storage_failure(exc)
    return StorageNotProvisioned(
        "the durable experiment table does not exist in this deployment"
    )


# --- what a brand-new experiment contains -------------------------------------

#: A user-created experiment's ``source``. Deliberately NOT
#: ``ws.MANAGED_SOURCE_DESCRIPTION``: that string is the provenance marker for
#: the committed demo fixtures, and ``classify_experiment`` uses it to recognise
#: records this application generated from them. A record a person created is not
#: one of those and must not be classified as one.
NEW_EXPERIMENT_SOURCE_DESCRIPTION = "Created in the app. No source files attached yet."


def new_experiment_source() -> dict:
    """The ``source`` block of a brand-new experiment: named, and empty."""
    return {"description": NEW_EXPERIMENT_SOURCE_DESCRIPTION, "files": []}


def blank_draft() -> dict:
    """The draft a brand-new experiment starts with. NOTHING SCIENTIFIC IS INVENTED.

    Read this against the no-guessing contract (``CLAUDE.md`` §5), clause by
    clause, because "start it empty" is easy to say and easy to get subtly wrong.

    **``meta`` IS set, and it is an inference by a stored rule rather than a
    guess.** ``isaac_records.extract.draft_builder._META`` is that rule: this
    build supports exactly one path — an evidence record, characterization
    domain, facility source — and the deterministic extractor stamps it on every
    draft it produces, from any input. Re-deriving it here would be a second
    definition of the same rule, so the constant is imported and pinned by
    ``test_experiment_repository.py`` instead. If the build ever supports a
    second path, this stops being uniquely inferable and becomes a question.

    **``fields`` is empty, including ``system.domain``.** The extractor DOES emit
    ``system.domain = experimental`` as an inferred field, and it is tempting to
    copy that here since the rule ("a facility-source record is an experiment")
    holds for any record. It is not copied, because the extractor's premise is
    that a ``system`` block EXISTS — it has read a technique and a facility. A
    blank record has no system block, so there is nothing for a domain to be the
    domain OF. Emitting it would be asserting a property of an absent object.

    **``pending`` carries the three blockers that are true of any record on this
    path**, with their questions worded exactly as the extractor words them (the
    two shared ones are pinned byte-for-byte in the tests):

    * ``series`` — an official record needs the reduced spectrum's actual data
      points, which nothing supplies at creation;
    * ``qc`` — the extractor raises this whenever it could not READ a QC verdict,
      and a blank record read nothing;
    * ``descriptor`` — the official schema's ``allOf`` requires descriptors on an
      evidence record.

    There are NO ``asset`` blockers, because those are one-per-candidate-file and
    a blank record names no files. That is an absence with a reason, not an
    omission.

    **What is knowingly NOT asked.** Everything the campaign sheet would have
    supplied — technique, facility, sample, energy window, contributors — has no
    capture surface in this build. Inventing a pending entry for a question nothing
    can answer would make the Guided Completion screen list dead ends.

    ~~"so a new experiment cannot yet be completed to the point of export. That is a
    real limit of the product, not of this function."~~ **NO LONGER TRUE, and struck
    rather than deleted because it was an accurate and useful warning for as long as it
    stood.** A new experiment CAN now be completed and exported: the three blockers
    above are the ones that actually gate an evidence record, and all three are now
    answerable through the product.

    * ``qc`` — ``_answers_to_apply_shape`` did not forward it, so no request could
      supply a verdict. It does now, and the UI has a verdict control.
    * ``series`` and ``descriptor`` — answerable only by CONFIRMING a worked-example
      value, which a created record does not have. ``StructuredValueEntry.tsx`` is
      where a person supplies them.

    ``apps/api/tests/test_scientist_can_finish_a_record.py`` walks create -> answer ->
    export with values written out rather than harvested, so this paragraph cannot go
    stale again without a test failing.

    The unlisted fields above remain uncapturable, and that is still a real limit —
    just not one that stops a record from being finished.
    """
    from isaac_records.extract.draft_builder import _META  # noqa: PLC0415

    return {
        "meta": dict(_META),
        "fields": {},
        "attribution": {"contributors": []},
        "implicit": [],
        "assets": [],
        "pending": [
            {
                "kind": "series",
                "blocker": "reduced_spectrum",
                "question": (
                    "Provide/point to the reduced spectrum (the .xdi reduction_product) "
                    "so measurement.series can be built."
                ),
                "evidence": [],
            },
            {
                "kind": "qc",
                "blocker": "qc_status",
                "question": (
                    "What is the QC verdict for this measurement "
                    "(valid/compromised/failed/pending) and how was it determined?"
                ),
            },
            {
                "kind": "descriptor",
                "blocker": "required_for_evidence_record",
                "question": (
                    "Provide at least one descriptor (e.g. XANES inflection-point energy "
                    "+ uncertainty) — an evidence record requires descriptors."
                ),
                "evidence": [
                    {
                        "source_type": "derivation",
                        "rule": (
                            "evidence record requires descriptors.outputs[] "
                            "(official schema allOf: evidence => descriptors)"
                        ),
                    }
                ],
            },
        ],
    }


# --- the durable store --------------------------------------------------------

#: THE DURABLE COMPARE-AND-SWAP. The ``WHERE`` on the conflict action is the whole
#: point of this statement and is not an optimisation.
#:
#: WHAT IT REPLACED, AND WHY THAT WAS A DEFECT. This used to be a bare
#: ``DO UPDATE SET state = EXCLUDED.state`` — last writer wins, unconditionally.
#: The API's ``If-Match`` / ``ETag`` contract promises a stale write is REFUSED,
#: and that promise was kept only by an in-process ``threading.Lock`` around the
#: read-modify-write. A lock in one process says nothing about a second process:
#: two writers could each pass their own local precondition and the second would
#: silently overwrite the first, with both told they had succeeded. The predicate
#: moves the decision to the one place every process shares.
#:
#: STATED PRECISELY, BECAUSE THE OVERSTATED VERSION IS TEMPTING: this repository
#: does not record how many replicas the hosted deployment runs, and nothing here
#: claims it runs more than one. The defect is that the guarantee was scoped to a
#: process while the STORAGE is shared — a lock cannot enforce a property of a
#: database — and that a rollout, which the deployment does perform, overlaps an
#: old process with a new one. It is a real hole whether or not it has been hit,
#: and it is not observable from here either way.
#:
#: THE PREDICATE, CLAUSE BY CLAUSE. Each is here for a case that really occurs;
#: none is defensive padding.
#:
#: 1. ``generation`` DIFFERS -> accept. ``generation`` is an opaque per-creation
#:    nonce (``workspace._new_generation``) and ``rev`` restarts at 0 with it, so a
#:    genuine re-creation of the same id legitimately arrives carrying a LOWER rev
#:    than the row it replaces. Ordering two generations is meaningless — the nonce
#:    is random by design — so a differing generation is treated as a new object
#:    rather than as a stale write. It must be first: without it a re-created
#:    record would be permanently unwritable behind its predecessor's rev.
#: 2. ``rev`` STRICTLY AHEAD -> accept. The ordinary case. Every authoritative
#:    mutation goes through ``Experiment.save_versioned``, which bumps
#:    ``max(in-memory rev, on-disk rev) + 1``, so a writer that read revision N
#:    offers N+1. A writer whose copy is behind offers a rev the row already has or
#:    has passed, and is refused.
#: 3. The DOCUMENT IS IDENTICAL -> accept. This is the rev-EQUAL case, and it is
#:    admitted deliberately and narrowly.
#:
#:    THE JUSTIFICATION THIS CLAUSE USED TO CARRY WAS FALSE, and is corrected here
#:    rather than quietly dropped. It said the clause exists for the retry after a
#:    fault between the durable write and the workspace-file write: same rev, same
#:    content, re-offered. It is almost never the same content. That retry goes
#:    through ``Experiment.save_versioned``, which re-stamps ``updated_utc``
#:    (``workspace._now_iso``, ONE-SECOND resolution) — and ``updated_utc`` is
#:    INSIDE the compared document. So the retried document matches only when the
#:    retry lands in the same wall-clock second as the write it retries. The clause
#:    is a same-second coincidence, not the partial-failure remedy, and the
#:    partial-failure wedge is closed somewhere else entirely: by
#:    ``Experiment._adopt_winner_locally``, which copies the winner's document into
#:    the workspace file on the way to the 412 so the client's next write is
#:    strictly ahead.
#:
#:    IT IS KEPT, because what it actually covers is worth covering and costs
#:    nothing: ANY re-offer of a byte-identical document at an equal rev — that
#:    same-second retry, two writers producing byte-identical states, and any
#:    caller reaching ``save()`` directly rather than through ``save_versioned``.
#:    Refusing those would report a conflict for a write that changes nothing. It
#:    cannot weaken clause 2: ``rev`` is INSIDE the document, so an identical
#:    document is identical in every field, and applying it is a no-op in all of
#:    them. Comparison is ``jsonb`` equality, which is by VALUE and not by text, so
#:    key order and whitespace cannot make an identical document look different.
#:
#: THE ONE LIMIT OF CLAUSE 1, STATED RATHER THAN GLOSSED. ``generation`` is an
#: opaque random nonce, so two generations cannot be ORDERED — only compared. The
#: clause is therefore symmetric: a writer holding the OLD generation is also
#: admitted over a row carrying a new one. Within a generation the swap is strict;
#: across one it is last-writer-wins, which is what "this is a different object"
#: means. That asymmetry is not reachable in this build — an ordinary-scope
#: record's generation never changes once created, because nothing deletes and
#: re-creates one (``remove_experiment`` is reached only by the tutorial reset,
#: whose records never touch this table) — so the clause is forward-looking. It is
#: kept LOOSE on purpose: tightening it to "a differing generation must also carry
#: ``rev = 0``" would close a hole nothing can reach today at the price of a
#: record that could wedge at ``412`` if the assumption ever failed.
#:
#: THAT SENTENCE USED TO END "…and a permanent wedge is the worse failure" — and
#: clause 2 then created exactly that wedge, one clause further down. Corrected
#: rather than deleted, because the correction is the point. Whenever the ROW is
#: ahead of the WORKSPACE FILE, every later mutation computes
#: ``max(self.rev, disk_rev) + 1``, which is the rev the row already holds: clause
#: 1 is false (same generation), clause 2 is false (not strictly ahead), clause 3
#: is false (``updated_utc`` differs) — a 412 that repeats forever, over reads that
#: keep serving the stale local file. Two ordinary events produce that skew: a
#: fault between ``save()``'s two writes, and a second replica that hydrated the
#: record before it moved on (``hydrate`` skips a record whose directory already
#: exists, so it never refreshes one). WHAT CLOSES IT IS NOT THIS PREDICATE. It is
#: ``Experiment._adopt_winner_locally``: a refusal writes the winner's document
#: into the workspace file before the 412 is raised, so re-read → re-apply → retry
#: converges in one extra round trip. Clause 1 stays loose for the reason above,
#: which is still a reason — but the recovery it appealed to now exists instead of
#: being assumed.
#:
#: ``RETURNING`` exists so the refusal is DETECTABLE: a conflict action whose
#: ``WHERE`` is false updates nothing and raises nothing, so without a returned row
#: (``cursor.rowcount``) a refused write would be indistinguishable from a
#: successful one — which is the original defect wearing a different hat.
#:
#: NO MIGRATION IS REQUIRED OR IMPLIED. This changes a statement, not a schema:
#: ``rev`` and ``generation`` already live inside the stored ``state`` document,
#: which is why the predicate reads them out of ``jsonb`` instead of asking for new
#: columns. It still names only ``isaac_experiments`` and contains no forbidden
#: verb, so it passes ``db_write.WriteStatementPolicy`` — asserted, not assumed
#: (``test_experiment_repository.py``).
#:
#: ``IS DISTINCT FROM`` IS DELIBERATELY NOT USED, and this is the one non-obvious
#: line. It would read better than ``COALESCE(...) <> COALESCE(...)``, and the
#: statement policy would REFUSE it: ``from`` is a table introducer, so the
#: tokenizer would read the following ``COALESCE`` as a table this application does
#: not own. The over-broad refusal is the policy behaving as designed (it refuses
#: loudly rather than admitting quietly); the statement is written around it.
Q_UPSERT_EXPERIMENT = (
    "INSERT INTO isaac_experiments (experiment_id, state) VALUES (%s, %s::jsonb)"
    " ON CONFLICT (experiment_id) DO UPDATE"
    " SET state = EXCLUDED.state, updated_utc = now()"
    " WHERE COALESCE(isaac_experiments.state ->> 'generation', '')"
    " <> COALESCE(EXCLUDED.state ->> 'generation', '')"
    " OR COALESCE((isaac_experiments.state ->> 'rev')::bigint, 0)"
    " < COALESCE((EXCLUDED.state ->> 'rev')::bigint, 0)"
    " OR isaac_experiments.state = EXCLUDED.state"
    " RETURNING experiment_id"
)

#: The winner's document, read back in the SAME transaction that refused a write,
#: so the ``412`` can report the rev that actually exists.
Q_ONE_EXPERIMENT = "SELECT state FROM isaac_experiments WHERE experiment_id = %s"

Q_ALL_EXPERIMENTS = (
    "SELECT experiment_id, state FROM isaac_experiments"
    " ORDER BY created_utc, experiment_id"
)


# --- the run rows: written here, and READ BY ONE READER (Stage 2b) ------------
#
# ~~"a SHADOW WRITE, and nothing reads them"~~ — **THE HEADING AND ONE CLAUSE BELOW
# WERE TRUE UNTIL STAGE 2b AND ARE CORRECTED IN PLACE**, because this comment is
# where a reader comes to find out what the table is for and a stale answer here is
# worse than none.
#
# WHAT THESE FOUR STATEMENTS ARE, AND — MORE IMPORTANTLY — WHAT THEY ARE NOT.
# They make the rows of `isaac_runs` for one experiment equal
# `exp.sorted_runs()`, inside the SAME transaction that upserts the experiment.
# They are ADDITIVE: `Experiment.to_state()` still serialises `runs` and the state
# document is still the authoritative copy. ~~"and NO READ PATH IN THIS APPLICATION
# TOUCHES THIS TABLE"~~ — `PostgresOrdinaryStore.hydrate` now reads
# `Q_RUN_ROWS_FOR_EXPERIMENTS` and builds a RESTORED document's `runs` from these
# rows when that experiment's projection is COMPLETE. That is Stage 2b, it is the
# separately reviewed slice this paragraph said would come, and it is the ONLY
# reader; see the "STAGE 2b" section below. Migration `0002_runs` exists so a Run
# can become the unit of write (contract §8 DECISION D7).
#
# THE POINT OF HAVING WRITTEN ROWS NOBODY READ was that the table is never wrong.
# The reader added later inherited a row set that had been maintained from the
# first write rather than one backfilled from documents of unknown vintage — and
# defects in the projection surfaced under test rather than on the day something
# started depending on it. That bet is what Stage 2b is now collecting on.
#
# WHY THEY ARE MODULE-LEVEL CONSTANTS WITH `%s` PLACEHOLDERS, like every other
# statement in this application: `db_write`'s primary guarantee is that no
# caller-supplied SQL exists anywhere in the write path. A run count is not known
# here, so a multi-row `VALUES (...), (...)` list — which would be one statement
# instead of N — would mean BUILDING SQL TEXT AT RUN TIME. That is the one thing
# this write path does not do, and the diff below is what makes N small anyway.

#: The current row set for one experiment. ONE indexed read — the index
#: `isaac_runs_experiment_order_idx` leads on `experiment_id` — and it is what makes
#: the write a DIFF instead of a blanket rewrite.
#:
#: IT SELECTS `state`, WHICH IS NOT FREE AND IS DELIBERATE. Comparing only the
#: promoted `(rev, generation)` columns would be cheaper and would be WRONG in one
#: reachable direction: `Experiment.save()` is the UNVERSIONED persistence
#: primitive, so a caller that mutates a run and calls `save()` rather than
#: `save_versioned()` changes the document without moving `rev`
#: (`Experiment._bump_changed_runs` is the only writer of `Run.rev`, and it runs
#: only on the write branch of `save_versioned`). Diffing on the version alone would
#: silently leave that row stale, and "stale" is precisely what a shadow write must
#: never be — a row nobody reads is only worth having if it is right.
#:
#: The cost is bounded by something already being paid: `Q_UPSERT_EXPERIMENT` sends
#: `json.dumps(exp.to_state())`, which EMBEDS every run's state, on every save. So
#: reading the states back is the same order of bytes as the write already in
#: flight, and it is still ONE statement rather than N. It is not free and is not
#: claimed to be; it is the honest price of a correct diff, and it stops being
#: payable the day the experiment document stops carrying `runs`.
#:
#: `experiment_id` is NOT selected: the `WHERE` already pins it, so every row this
#: returns carries it by construction.
Q_EXPERIMENT_RUN_ROWS = (
    "SELECT run_id, ordinal, state, rev, generation FROM isaac_runs"
    " WHERE experiment_id = %s"
)

#: Insert or refresh ONE run row. Every column this application owns is written
#: from the projection, so an accepted upsert leaves the row equal to
#: :func:`_run_row_params` in all of them.
#:
#: THE CONFLICT ACTION IS UNCONDITIONAL, and that is not the oversight it looks
#: like next to :data:`Q_UPSERT_EXPERIMENT`'s careful predicate. The two statements
#: answer different questions. The experiment upsert arbitrates BETWEEN WRITERS —
#: it is the shared compare-and-swap that makes `If-Match` mean something across
#: processes, and it must refuse a writer whose copy is behind. This statement is
#: only ever reached AFTER that arbitration has already been won, inside the same
#: transaction, and it writes the winner's own runs. A second predicate here could
#: only refuse a write the shared one has already authorised, which would leave the
#: rows disagreeing with the experiment document that was just committed beside
#: them.
#:
#: `created_utc` is never named: it is the server-side stamp of when the ROW was
#: first written and must survive a refresh. `updated_utc` is stamped `now()` on
#: every accepted update, which is what makes "did this save touch this run" a
#: question a real engine can answer — see the CI assertion that the diff really
#: diffs.
Q_UPSERT_RUN = (
    "INSERT INTO isaac_runs"
    " (run_id, experiment_id, ordinal, state, rev, generation)"
    " VALUES (%s, %s, %s, %s::jsonb, %s, %s)"
    " ON CONFLICT (run_id) DO UPDATE"
    " SET experiment_id = EXCLUDED.experiment_id,"
    " ordinal = EXCLUDED.ordinal,"
    " state = EXCLUDED.state,"
    " rev = EXCLUDED.rev,"
    " generation = EXCLUDED.generation,"
    " updated_utc = now()"
)

#: Remove every row of this experiment that the document no longer names.
#:
#: THE PREDICATE IS THE COMPLEMENT OF THE DESIRED SET, NOT A LIST OF VICTIMS, and
#: that is what makes the row set a PURE FUNCTION of `sorted_runs()` rather than a
#: function of what the `SELECT` happened to see. It is issued only when that
#: `SELECT` showed at least one id the document has dropped — issuing it
#: unconditionally would cost a statement on every save to delete nothing — but
#: when it is issued it removes everything outside the desired set, so a row that
#: appeared between the read and the write is removed too.
#:
#: `%s::text[]` IS CAST EXPLICITLY BECAUSE OF THE EMPTY CASE. Deleting the LAST run
#: of an experiment passes an EMPTY id list, and an empty array literal carries no
#: element type for the server to infer — whichever of psycopg2's two renderings it
#: produces. The cast makes the type explicit, so "every run was removed" is a
#: working statement rather than a type error on the one save that needs it most.
#:
#: STATED AS AN UNMEASURED PRECAUTION, because the machine this was written on has
#: no psycopg2 and no PostgreSQL: the cast is cheap and correct under either
#: rendering, so it is written rather than argued about. CI's `postgres:18` service
#: is what actually binds it — the `postgres-migration` job now clears an
#: experiment's runs and asserts the rows are gone.
#:
#: NO `ON DELETE CASCADE` IS INVOLVED OR IMPLIED. `0002_runs` deliberately writes no
#: `ON DELETE` clause at all, so deleting an experiment that still has runs is
#: refused by the database; this statement deletes RUNS, by their own ids, for an
#: experiment that continues to exist.
Q_DELETE_ABSENT_RUNS = (
    "DELETE FROM isaac_runs WHERE experiment_id = %s AND run_id <> ALL(%s::text[])"
)


# --- the completeness claim: STAGE 2a, and still nothing reads it -------------
#
# WHY A SECOND TABLE EXISTS AT ALL, and it is a measured ambiguity rather than a
# design taste. `Q_EXPERIMENT_RUN_ROWS` returning zero rows means EITHER "this
# experiment has no runs" OR "this experiment's runs were never projected", and
# both are reachable — the second is the normal state of every experiment
# persisted before the shadow write shipped, and of every experiment saved during
# the window between a merge and the operator applying the migration by hand.
# A reader that read zero rows as "no runs" would silently delete every run of
# every pre-existing record the first time it was switched on, and report success.
#
# So the claim is RECORDED rather than inferred, and it is recorded WITH THE
# VERSION IT WAS MADE AT, which is the part that makes staleness detectable
# instead of assumed-absent. The full contract, including the four states every
# future read must distinguish, is `docs/isaac-runs-stage-2-contract.md`.
#
# ~~"NOTHING READS THIS TABLE IN THIS BUILD. Stage 2b — moving a reader onto
# `isaac_runs` — is a separate slice gated on the backfill having run."~~ —
# **CORRECTED IN PLACE: Stage 2b IS this build.** `Q_RUN_PROJECTIONS_FOR_EXPERIMENTS`
# reads it, from `PostgresOrdinaryStore.hydrate`, and nothing else does. The
# "gated on the backfill" half is corrected too, and the correction is the
# contract's own (§7.3): §3's gate governs when the CUTOVER is complete, not when
# the reader may be written. The reader is safe before the backfill by
# construction — every experiment the backfill would cover is NEVER PROJECTED or
# UNAVAILABLE, and both read the document — so it is a no-op for exactly those
# records.

#: The projector the ORDINARY application write path stamps. A CLOSED value set in the
#: migration's own CHECK (`write-path` | `backfill`), so a typo here is refused by the
#: database rather than stored.
PROJECTOR_WRITE_PATH = "write-path"

#: The projector the OPERATOR BACKFILL stamps — ``scripts/db_backfill_runs.py``, and
#: nothing else.
#:
#: IT DID NOT EXIST, AND EVERY BACKFILLED ROW CLAIMED THE OTHER PRODUCER. An independent
#: review measured it: :data:`Q_UPSERT_RUN_PROJECTION` has exactly one call site
#: (:meth:`PostgresOrdinaryStore._stamp_projection`), that site hard-coded
#: :data:`PROJECTOR_WRITE_PATH`, and the backfill reaches it through the same
#: :meth:`PostgresOrdinaryStore.persist` every save uses — so a pass over a
#: never-projected table wrote rows saying they came from the write path. The string
#: ``'backfill'`` appeared in exactly one place in the repository, and it was the
#: backfill's own docstring asserting a behaviour the code did not have
#: (``grep -rn "'backfill'" apps/api/isaac_api/ scripts/ src/ --include='*.py'``).
#:
#: WHY THAT IS A DEFECT AND NOT A COSMETIC LABEL. `0005_run_projection.sql` gives
#: ``projector`` a two-value CHECK and an index that LEADS on it, and
#: ``docs/migration-approval-packet-0005.md`` §8A tells the operator to group the
#: completeness query by it. Both were built to let the operator distinguish "these rows
#: were maintained incidentally by ordinary saves" from "these rows were established by
#: the pass I just ran" — which is the whole question the Stage-2b gate asks. A column
#: whose second value can never appear cannot answer it, and the operator would have read
#: a table with no ``backfill`` rows in it as evidence the backfill had not run.
#:
#: IT IS A PARAMETER RATHER THAN A SECOND WRITER, and that is the load-bearing part.
#: ``_stamp_projection``'s own docstring forbids a second write path — the projection
#: table has no ``session_id`` column and can never gain one, so a worked-example claim
#: that reached it would be permanently uncleanable — so the backfill must keep going
#: through :meth:`persist`, inheriting ``refuse_if_not_persistable``, the ``accepted``
#: gate and the run-row diff. Threading the label through is the change that leaves all
#: of that intact.
PROJECTOR_BACKFILL = "backfill"

#: Insert or refresh the completeness claim for ONE experiment.
#:
#: THE CONFLICT ACTION IS UNCONDITIONAL, for exactly :data:`Q_UPSERT_RUN`'s reason:
#: this statement is only ever reached after the experiment compare-and-swap has
#: already been won, inside the same transaction, and it describes the winner's own
#: rows. A predicate here could only refuse a claim the shared arbitration has
#: already authorised, leaving the claim disagreeing with the rows committed beside
#: it.
#:
#: THERE IS ONE CURRENT CLAIM PER EXPERIMENT AND NO HISTORY OF IT. `experiment_id`
#: is the primary key, so this supersedes in place. A superseded completeness claim
#: is not evidence of anything — it describes a row set that no longer exists.
#:
#: `projected_utc` is stamped `now()` on every accepted update so an operator
#: reading the table by hand can see when the claim was last made. Nothing derives
#: correctness from it; the version pair does that.
Q_UPSERT_RUN_PROJECTION = (
    "INSERT INTO isaac_run_projection"
    " (experiment_id, experiment_rev, experiment_generation, run_count, projector)"
    " VALUES (%s, %s, %s, %s, %s)"
    " ON CONFLICT (experiment_id) DO UPDATE"
    " SET experiment_rev = EXCLUDED.experiment_rev,"
    " experiment_generation = EXCLUDED.experiment_generation,"
    " run_count = EXCLUDED.run_count,"
    " projector = EXCLUDED.projector,"
    " projected_utc = now()"
)

#: The relation :data:`Q_UPSERT_RUN_PROJECTION` names, as a named constant for
#: :data:`Q_PROJECTION_TABLE_PRESENT`'s parameter — same reasoning as
#: :data:`RUN_TABLE`.
PROJECTION_TABLE = "isaac_run_projection"


# --- STAGE 2b: the two reads that move the run list's authority ----------------
#
# WHAT MOVES, AND IT IS ONE THING. When :meth:`PostgresOrdinaryStore.hydrate`
# restores an experiment whose projection is COMPLETE, the restored document's
# ``runs`` key is built from ``isaac_runs`` rows instead of from the stored
# document's own ``runs``. NOTHING ELSE MOVES: the compare-and-swap is still on
# ``isaac_experiments.state``, ``Experiment.to_state()`` still serialises ``runs``,
# ``Q_UPSERT_EXPERIMENT`` is untouched, and every write path is byte-for-byte what
# it was. The contract is `docs/isaac-runs-stage-2-contract.md` §7.
#
# THAT IS ALSO WHERE A SILENT-DATA-LOSS BUG WOULD LIVE, which is why the scope is
# stated this narrowly: get it wrong and a record is restored with no runs and the
# pass reports success. The four states below exist so that outcome is unwritable.
#
# THE FOUR STATES ARE DECIDED BY :func:`resolve_run_authority`, and every read must
# distinguish all four (contract §2.1). Three of them — STALE, NEVER PROJECTED and
# UNAVAILABLE — read the document, and that is NORMAL OPERATION rather than an
# error path. ``run_count = 0`` beside a matching version pair is COMPLETE and
# means "this experiment has no runs", which is the state `0002` alone could not
# express.
#
# WHY THESE TWO STATEMENTS ARE PLURAL. ``hydrate`` reads every stored experiment in
# ONE ``SELECT`` and restores only those whose workspace directory is missing. A
# per-experiment read here would turn one round trip into 2N. ``= ANY(%s::text[])``
# keeps it at two statements for any N, with no SQL built at run time — the same
# shape, and the same explicit cast for the empty case, that
# :data:`Q_DELETE_ABSENT_RUNS` already uses.
#
# AND THEY ARE ISSUED ONLY WHEN THERE IS SOMETHING TO RESTORE. ``hydrate`` runs on
# every ordinary ``GET /api/experiments``, not once per restart (contract §7.1),
# and it skips any record whose ``experiment.json`` is already on disk. So the
# steady state — every record present locally — issues NEITHER of these statements,
# and the added cost is bounded by how many records are genuinely missing, which is
# normally zero and is "all of them" exactly once, after a pod restart.

#: The completeness claims for a batch of experiments.
#:
#: ``run_count`` IS DELIBERATELY NOT SELECTED, and its absence is the mechanical
#: form of a rule rather than an economy. Contract §7.4: ``run_count`` must not be
#: used to detect a mismatch, because §2.2 invariant 4 records that it is
#: ``len(desired_ids)`` — a writer's INTENTION, not an observation — so treating a
#: matching count as evidence of matching rows is exactly the overclaim that
#: invariant corrects. A column that is never read cannot be misused;
#: ``test_the_reader_never_selects_run_count`` pins it.
#:
#: ``projector`` is likewise not selected: who made the claim is an operator's
#: question (it is what `0005`'s index leads on and what the Stage-2b gate query
#: groups by), and it has no bearing on whether the claim is current.
Q_RUN_PROJECTIONS_FOR_EXPERIMENTS = (
    "SELECT experiment_id, experiment_rev, experiment_generation"
    " FROM isaac_run_projection WHERE experiment_id = ANY(%s::text[])"
)

#: The run rows for a batch of experiments, IN THE ORDER ``sorted_runs`` PRODUCES.
#:
#: ORDERING IS A REAL TRAP AND THIS IS WHERE IT IS PAID. ``sorted_runs`` orders by
#: ``(ordinal, created_utc, id)`` where ``created_utc`` is the DOCUMENT field.
#: ``isaac_runs_experiment_order_idx`` is ``(experiment_id, ordinal, run_id)`` and
#: the column of that name on this table is the SERVER-SIDE ROW STAMP — a different
#: value entirely — so a reader that ordered by the index would reproduce a
#: DIFFERENT SEQUENCE. `0002_runs.sql` says so in its own words beside that index
#: and names the reproducing sort; this is that sort, verbatim, with
#: ``experiment_id`` in front so one statement can serve a batch.
#:
#: The order is belt-and-braces rather than load-bearing: a restored document is
#: parsed straight back through ``Experiment.from_state``, which re-sorts. It is
#: written anyway because "the reader reproduces the document" is the property this
#: whole slice is judged on, and reproducing it only up to a permutation is a
#: weaker claim than the one being made.
#:
#: ``rev``, ``generation`` and ``ordinal`` are not selected: the run DOCUMENT is
#: what a restored ``runs`` entry is made of, and the promoted columns are a
#: projection OF that document rather than a part of it.
Q_RUN_ROWS_FOR_EXPERIMENTS = (
    "SELECT experiment_id, run_id, state FROM isaac_runs"
    " WHERE experiment_id = ANY(%s::text[])"
    " ORDER BY experiment_id, ordinal, state ->> 'created_utc', run_id"
)


#: THE KILL SWITCH. ``ISAAC_RUN_ROWS_AUTHORITATIVE=0`` forces every experiment to
#: document-reading behaviour without a redeploy.
#:
#: IT IS DEFENCE FOR AN OPERATOR, NOT A GATE THE DESIGN DEPENDS ON, and the default
#: is therefore ON: a design that needed a flag to be safe would not be safe
#: (contract §7.3). What the flag buys is a single environment edit on a pod that
#: is misbehaving, in a deployment where the alternative is waiting for an image.
#:
#: READ PER CALL, NEVER AT IMPORT, which is what "without a redeploy" requires — a
#: module-level constant resolved at import time would freeze whichever value the
#: process started with.
#:
#: WHEN IT IS OFF, NEITHER STATEMENT ABOVE IS ISSUED AT ALL. The reader does not
#: read the tables and then discard the answer; it does not ask. That is what makes
#: "off" provable by statement inspection rather than by trusting a branch.
RUN_ROWS_AUTHORITATIVE_ENV = "ISAAC_RUN_ROWS_AUTHORITATIVE"

#: The values that turn the switch OFF, compared case-insensitively after
#: stripping. An UNRECOGNISED value leaves the reader ON, deliberately: a typo must
#: not silently disable a shipped behaviour, and the enumerated set is small enough
#: that an operator who wants it off can hit one of them. Unset and empty both mean
#: ON, because empty is what unsetting a variable in a manifest usually produces.
_RUN_ROWS_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})


def run_rows_authoritative(env: Mapping[str, str] | None = None) -> bool:
    """Whether ``isaac_runs`` may be the authority for a COMPLETE projection.

    Configuration only. It opens nothing, and it is read on every hydration pass
    and by :func:`storage_status`, so an operator's edit takes effect on the next
    request rather than on the next roll.
    """
    raw = (os.environ if env is None else env).get(RUN_ROWS_AUTHORITATIVE_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in _RUN_ROWS_DISABLED_VALUES


# The FOUR STATES of contract §2.1, plus the one outcome that is not a state.

#: A projection row exists AND its version pair equals the document's. The rows may
#: be used.
RUN_AUTHORITY_COMPLETE = "complete"

#: A row exists and the pair differs — the rows are behind. Use the document.
RUN_AUTHORITY_STALE = "stale"

#: No row. The rows say nothing about this experiment. Use the document.
RUN_AUTHORITY_NEVER_PROJECTED = "never_projected"

#: ``isaac_runs`` or ``isaac_run_projection`` is absent. Use the document. This is
#: the state of EVERY experiment in every environment until `0005` is applied.
RUN_AUTHORITY_UNAVAILABLE = "unavailable"

#: NOT A STATE — A BUG (contract §7.4). A COMPLETE projection whose rows do not
#: reproduce the document's ``runs``. Per §2.2 invariant 4 the two agree by
#: construction of the upsert-and-delete pair, so a disagreement means a writer, a
#: migration or an out-of-band statement broke that construction. The DOCUMENT is
#: used — it is the side the compare-and-swap protects and the side a scientist's
#: last write landed in — and the disagreement is COUNTED, because a mismatch that
#: only fell back would be indistinguishable from a healthy fallback.
RUN_AUTHORITY_MISMATCH = "mismatch"

#: Every outcome, in a fixed order, so the distribution `storage_status` publishes
#: has a stable shape and a missing key is a defect rather than a zero.
RUN_AUTHORITY_STATES: tuple[str, ...] = (
    RUN_AUTHORITY_COMPLETE,
    RUN_AUTHORITY_STALE,
    RUN_AUTHORITY_NEVER_PROJECTED,
    RUN_AUTHORITY_UNAVAILABLE,
    RUN_AUTHORITY_MISMATCH,
)


def _as_projected_rev(value: Any) -> int | None:
    """``value`` as a non-negative revision, or ``None`` if it is not one.

    ``None`` NEVER COMPARES EQUAL, which is the whole reason this returns it
    instead of ``0``: a document whose ``rev`` cannot be read must not be able to
    match a stamp, because "COMPLETE" is the one verdict that lets the rows
    replace the document.
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stored_projections(rows: Any) -> dict[str, tuple[int | None, Any]]:
    """``experiment_id -> (experiment_rev, experiment_generation)`` for the claims.

    The rev is normalised through :func:`_as_projected_rev` here rather than at the
    comparison, so an unreadable stamp is ``None`` and can never match.
    """
    out: dict[str, tuple[int | None, Any]] = {}
    for row in rows or []:
        out[str(row[0])] = (_as_projected_rev(row[1]), row[2])
    return out


def _grouped_run_rows(rows: Any) -> dict[str, list[tuple[str, dict | None]]]:
    """``experiment_id -> [(run_id, state document or None), ...]``, order preserved.

    ``state`` is normalised with the same tolerance :func:`_stored_run_rows`
    applies — psycopg2 returns ``jsonb`` as a ``dict``, anything without the
    adapter registered returns text — and anything else becomes ``None``. A
    ``None`` here can never reproduce a run, so it makes the experiment a MISMATCH
    and the document is used, which is the safe direction.
    """
    out: dict[str, list[tuple[str, dict | None]]] = {}
    for row in rows or []:
        state = row[2]
        if isinstance(state, (str, bytes, bytearray)):
            try:
                state = json.loads(state)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                state = None
        if not isinstance(state, dict):
            state = None
        out.setdefault(str(row[0]), []).append((str(row[1]), state))
    return out


def _document_runs(state: Mapping[str, Any]) -> list[dict] | None:
    """The run DOCUMENTS the stored document names, or ``None`` if it does not say.

    ``None`` MEANS "UNCOMPARABLE", NOT "EMPTY", and the caller turns it into a
    MISMATCH so the document is used unchanged. A ``runs`` value that is not a list
    of objects carrying string ids is a document this application did not write;
    §11's read-path rule is that a malformed value already PERSISTED is read rather
    than refused, and reading it means leaving it exactly as it is.

    IT RETURNS THE ENTRIES, NOT THEIR IDS, and that widening is the whole of the
    2026-08-27 correction to contract §7.4 rule 1. ~~``_document_run_ids``, which
    returned ``list[str] | None``~~ made the id list the only thing the caller
    could compare, so a row whose CONTENT had diverged inside a matching id set was
    unobservable. The ids are still derived here — by the caller, from these
    entries — so every id-shaped refusal above is unchanged.
    """
    runs = state.get("runs")
    if runs is None:
        return []
    if not isinstance(runs, list):
        return None
    entries: list[dict] = []
    for entry in runs:
        if not isinstance(entry, dict):
            return None
        rid = entry.get("id")
        if not isinstance(rid, str) or not rid:
            return None
        entries.append(entry)
    return entries


def _rows_reproduce_the_document(
    run_rows: list[tuple[str, dict | None]], document_runs: list[dict]
) -> bool:
    """Whether the row documents are the document's ``runs``, AS DOCUMENTS.

    Contract §7.4 rule 2 says the document wins on ANY disagreement, and rule 1
    used to say the comparison was "by run id". Those two disagreed, and the
    disagreement was measured rather than argued: with matching id sets and
    divergent CONTENT, the id comparison returned COMPLETE, the row's document was
    written over the scientist's, and nothing was disclosed. A content divergence
    is exactly as much "a COMPLETE projection that does not reproduce the
    document" as a missing id is, and it is MORE dangerous, because it substitutes
    different science rather than a different count. The contract is being
    corrected to match this function, not the other way round.

    WHAT IS COMPARED, AND WHAT IS DELIBERATELY NOT NORMALISED
    --------------------------------------------------------
    Both sides are ``Run.to_state()`` — `_run_row_params` writes the row's ``state``
    as ``run.to_state()`` VERBATIM and ``Experiment.to_state()`` serialises
    ``[r.to_state() for r in self.sorted_runs()]`` — written by the SAME
    transaction. So the honest comparison is plain ``==`` between two parsed
    documents, and four things that look like they need normalising do not:

    * **Key order.** Nothing to do. Both sides are parsed into ``dict`` before they
      reach here (`_grouped_run_rows` for the rows, the stored state file for the
      document), and ``dict.__eq__`` is order-insensitive. Neither side is ever
      compared as TEXT — which matters, because ``jsonb`` does not preserve key
      order, so a text comparison would report MISMATCH on every experiment and
      quietly disable Stage 2b permanently.
    * **``jsonb`` returned as text.** Already normalised upstream:
      `_grouped_run_rows` ``json.loads`` a ``str``/``bytes`` ``state`` and maps
      anything that is not then a ``dict`` to ``None``, which the caller refuses.
    * **Numeric types.** ``==`` on parsed values makes ``1 == 1.0`` and
      ``-0.0 == 0.0`` true, which is what a ``jsonb`` round trip may legitimately
      produce. A canonical-JSON-string comparison would call those DIFFERENT; it is
      deliberately not used, for that reason.
    * **Legacy ``experiment_id: ""``.** Nothing is normalised and nothing needs to
      be. The row's DOCUMENT keeps whatever the run has always said — including the
      empty string `workspace._hydrate_runs` deliberately never repairs — and the
      row's ``experiment_id`` COLUMN, which does carry the owner's id, is not part
      of this comparison at all.

    THE COMPARISON IS ORDER-INSENSITIVE, AND THAT IS ALSO A REFUSAL TO INVENT A
    MISMATCH. The rows arrive ordered by ``ordinal, state ->> 'created_utc',
    run_id`` — a sort the DATABASE performs under its own collation — while
    ``sorted_runs()`` performs the same sort in Python. For ULIDs and ISO
    timestamps the two agree, but "agree" there is a property of a collation this
    repository does not control, and a permutation must not cost a scientist their
    runs. Order is not load-bearing anyway: the restored document is parsed back
    through ``Experiment.from_state``, which re-sorts. So entries are matched
    WITHIN their run id, which keeps the check O(runs) rather than O(runs²) and
    keeps a duplicated id — which `isaac_runs`' primary key cannot produce —
    comparing as the multiset it is.
    """
    unmatched: dict[str, list[dict]] = {}
    for entry in document_runs:
        unmatched.setdefault(str(entry.get("id")), []).append(entry)
    for run_id, row_document in run_rows:
        bucket = unmatched.get(run_id)
        if not bucket:
            return False
        for index, candidate in enumerate(bucket):
            if candidate == row_document:
                del bucket[index]
                break
        else:
            return False
    return not any(unmatched.values())


def resolve_run_authority(
    state: Mapping[str, Any],
    projection: tuple[int | None, Any] | None,
    run_rows: list[tuple[str, dict | None]],
    *,
    tables_present: bool,
) -> tuple[str, list[dict] | None]:
    """THE FOUR-STATE PREDICATE, AND THE MISMATCH RULE, IN ONE PLACE.

    Returns ``(state, runs)`` where ``state`` is one of
    :data:`RUN_AUTHORITY_STATES` and ``runs`` is the list the restored document's
    ``runs`` key must hold — or ``None``, meaning USE THE DOCUMENT.

    PURE, AND DELIBERATELY CALLABLE WITHOUT A DATABASE. Everything that decides
    whether a scientist's runs are replaced is decided here, from values, so it can
    be exhaustively tested without a connection and so there is exactly one place
    to read.

    THE ORDER OF THE CHECKS IS THE CONTRACT'S §2.1 TABLE, top to bottom, and
    ``None`` is never treated as a match at any of them:

    * ``tables_present`` false -> UNAVAILABLE. `0005` (or `0002`) is not applied
      here, so the tables say nothing about anything.
    * no projection row -> NEVER PROJECTED. Absence of the row is absence of the
      claim; it is NOT "zero runs".
    * the pair differs -> STALE. Both keys, never ``rev`` alone: ``generation`` is
      what makes a delete-and-recreate distinguishable at rev 0.
    * the pair matches, but the rows do not reproduce the document -> MISMATCH.
    * otherwise -> COMPLETE, and the rows are returned.

    THE COMPARISON IS OF THE FULL RUN DOCUMENTS, not of their ids.
    ~~"THE COMPARISON IS BY RUN ID, as contract §7.4 rule 1 specifies"~~ —
    **SUPERSEDED 2026-08-27, and the contract is being corrected to match this
    function rather than the reverse.** §7.4 rule 1 said "by run id" and rule 2
    said "on disagreement, use the DOCUMENT"; the two disagreed, and the
    implementation of rule 1 measured the consequence: with matching id sets and
    divergent row CONTENT, the row's document was written over the scientist's and
    nothing was disclosed. Rule 2 is the one that governs, because the document is
    the side the compare-and-swap protects and the side a scientist's last write
    landed in. See :func:`_rows_reproduce_the_document` for what is compared and
    for the four things that deliberately are NOT normalised.

    IT IS STILL A MULTISET COMPARISON RATHER THAN A SET ONE, and the id-shaped
    refusals are all kept. A stored document carrying the same run id twice is a
    document `isaac_runs` cannot reproduce — ``run_id`` is that table's primary
    key — so a set comparison would call it equal and then write the de-duplicated
    row version over it. Sorted id lists make that a MISMATCH, which keeps the
    document, which is exactly today's behaviour for a document nobody should have
    written.

    A ROW WHOSE DOCUMENT DOES NOT CARRY ITS OWN ``run_id`` IS ALSO A MISMATCH.
    `0002_runs`' ``isaac_runs_document_identity`` CHECK forbids that pairing, so a
    row of this shape means the CHECK was bypassed; substituting its document for a
    run filed under a different id is the one substitution that could rename a
    scientist's run.
    """
    if not tables_present:
        return RUN_AUTHORITY_UNAVAILABLE, None
    if projection is None:
        return RUN_AUTHORITY_NEVER_PROJECTED, None
    stamped_rev, stamped_generation = projection
    document_rev = _as_projected_rev(state.get("rev"))
    document_generation = state.get("generation")
    if stamped_rev is None or document_rev is None or stamped_rev != document_rev:
        return RUN_AUTHORITY_STALE, None
    if not isinstance(document_generation, str) or not document_generation:
        # A stamped generation is NOT NULL and has no default, so a document that
        # cannot state its own generation cannot be matched by one. STALE rather
        # than MISMATCH: nothing has been compared yet, and the honest reading is
        # that this claim does not describe this document.
        return RUN_AUTHORITY_STALE, None
    if stamped_generation != document_generation:
        return RUN_AUTHORITY_STALE, None
    document_runs = _document_runs(state)
    if document_runs is None:
        return RUN_AUTHORITY_MISMATCH, None
    if any(document is None for _, document in run_rows):
        return RUN_AUTHORITY_MISMATCH, None
    if any(document.get("id") != run_id for run_id, document in run_rows):
        return RUN_AUTHORITY_MISMATCH, None
    if sorted(run_id for run_id, _ in run_rows) != sorted(
        str(entry.get("id")) for entry in document_runs
    ):
        return RUN_AUTHORITY_MISMATCH, None
    if not _rows_reproduce_the_document(run_rows, document_runs):
        # THE CONTENT CHECK, AND IT IS LAST BECAUSE IT IS THE MOST EXPENSIVE.
        # Everything above refuses on a shape the rows could never have produced;
        # this refuses on a shape they could have produced yesterday and no longer
        # do. Contract §7.4 rule 2: the DOCUMENT wins, and rule 3: it is counted.
        return RUN_AUTHORITY_MISMATCH, None
    return RUN_AUTHORITY_COMPLETE, [document for _, document in run_rows]


#: WHAT THE MOST RECENT HYDRATION PASS OBSERVED, or ``None`` if no pass has
#: classified anything yet. Module-level for the reason :data:`_storage_failure` is:
#: :func:`ordinary_store` builds a new store per call, so per-instance state would
#: be state nobody could read.
#:
#: COUNTS ONLY — no ids, no titles, no record content, and nothing derived from a
#: scientific value. It is an aggregate about THIS APPLICATION'S OWN tables, not
#: about the production-derived ``records`` table, so gates G2 and G3 are untouched
#: by it.
#:
#: IT IS RECORDED ONLY BY A PASS THAT ACTUALLY CLASSIFIED SOMETHING, and that is a
#: truthfulness decision rather than an optimisation. ``hydrate`` runs on every
#: ordinary list and normally has nothing to restore; overwriting this with an
#: all-zero distribution on each of those would erase the one pass that carries
#: information — the post-restart pass, where every record is missing and every
#: record is therefore classified.
_last_run_authority: dict[str, int] | None = None


def run_authority_summary() -> dict | None:
    """The distribution the most recent classifying hydration pass measured.

    ``None`` means no pass has classified an experiment in this process — which is
    the honest answer, and is distinguishable from "a pass ran and found nothing".
    """
    return dict(_last_run_authority) if _last_run_authority is not None else None


def _record_run_authority(counts: Mapping[str, int]) -> None:
    """Record one pass's distribution. Called only when it classified something."""
    global _last_run_authority
    _last_run_authority = {state: int(counts.get(state, 0)) for state in RUN_AUTHORITY_STATES}


def forget_run_authority() -> None:
    """Drop the recorded distribution. For tests, exactly as
    :func:`forget_run_table_presence` is — a process-wide observation needs a
    process-wide reset or one case inherits another's."""
    global _last_run_authority
    _last_run_authority = None


# --- DISCARD: the three deletes, in foreign-key dependency order ---------------
#
# WHAT THESE THREE STATEMENTS ARE, AND — MORE IMPORTANTLY — WHAT THEY ARE NOT.
# They remove ONE experiment this application created, together with the two
# writer-maintained projections OF that experiment, inside ONE transaction. They
# are the durable half of `POST /api/experiments/{id}/discard`, whose whole
# authorization is the project owner's narrow one: **explicit Discard semantics
# for unsubmitted Draft/capture state only.**
#
# THEY ARE NOT A GENERIC DELETE PRIMITIVE AND MUST NOT BECOME ONE. There is no
# statement here that takes a table name, a predicate, or anything but one
# experiment id; each is a module-level constant with `%s` placeholders, exactly
# like every other statement in this application, because `db_write`'s primary
# guarantee is that no caller-supplied SQL exists anywhere in the write path.
#
# THREE TABLES, AND THE FIVE THAT ARE DELIBERATELY ABSENT. These name
# `isaac_run_projection`, `isaac_runs` and `isaac_experiments` and nothing else.
# `isaac_experiment_revisions`, `isaac_run_revisions`, `isaac_revision_changes`,
# `isaac_submissions` and `isaac_submission_runs` are APPEND-ONLY HISTORY: no
# statement in this application may ever UPDATE or DELETE one, which is the whole
# of that guarantee because the database cannot provide it (a trigger needs a
# dollar-quoted body, which `db_migrate.split_statements` refuses; `REVOKE` is a
# forbidden verb). `test_submission_store.test_no_submission_statement_updates_or_deletes_history`
# already scans every `Q_*` in this package for exactly that, and
# `test_discard_an_experiment.py` states the same property over THIS module's
# constants specifically, so the guard names the place a future delete would be
# written.
#
# `records` IS UNREACHABLE FROM HERE BY TWO INDEPENDENT MECHANISMS, and neither is
# this comment: `db_write._FORBIDDEN_TABLES` refuses any statement whose token
# stream contains the identifier at all, and `OWNED_TABLES` does not list it.
#
# THE ORDER IS CHILDREN FIRST, AND IT IS A REQUIREMENT RATHER THAN A PREFERENCE.
# No migration in this repository writes an `ON DELETE` clause anywhere, so the
# SQL default `NO ACTION` applies to every foreign key into `isaac_experiments`:
# PostgreSQL REFUSES to delete a parent row that still has children. Issuing the
# experiment delete first would abort the transaction every time the record had a
# single run. The two projections go first, the experiment last.
#
# AND THE ORDER IS ALSO THE BACKSTOP. Because the experiment delete goes LAST,
# and because ~~`0003`/`0004` declare four more foreign keys into the same parent
# with the same `NO ACTION`~~ — **TWO, re-measured; see
# :class:`DiscardRefusedByHistory` for the count and for why the guarantee is
# unchanged** — `isaac_experiment_revisions_experiment_fk` and
# `isaac_submissions_experiment_fk` name `isaac_experiments` directly with the same
# `NO ACTION`, and every other history row requires a parent in one of those two
# tables — a record that still carries a revision or a
# submission is refused BY THE SERVER at that final statement, and the two
# deletes already issued roll back with it. The route refuses long before this;
# this is what holds if the route's reasoning is ever wrong. See
# :class:`DiscardRefusedByHistory`.

#: The completeness claim for this experiment's run rows (`0005`). Removed first
#: because it is the leaf: nothing references it, and it is meaningless once the
#: rows it describes are gone. A superseded completeness claim is not evidence of
#: anything — it describes a row set that no longer exists.
Q_DELETE_RUN_PROJECTION_FOR_EXPERIMENT = (
    "DELETE FROM isaac_run_projection WHERE experiment_id = %s"
)

#: Every run row of this experiment (`0002`).
#:
#: DISTINCT FROM :data:`Q_DELETE_ABSENT_RUNS`, WHICH IS THE SHADOW-WRITE DIFF. That
#: statement removes the rows a still-existing experiment no longer names, and its
#: predicate is the COMPLEMENT of a desired set; this one removes them all, for an
#: experiment that is about to stop existing. Reusing the diff with an empty id
#: array would work and would be a false economy: the two say different things, and
#: a reader of either deserves to see which.
Q_DELETE_RUNS_FOR_EXPERIMENT = "DELETE FROM isaac_runs WHERE experiment_id = %s"

#: The experiment row itself (`0001`). LAST, for both reasons above.
#:
#: `rowcount` over this statement is MEASURED and returned, never assumed: it is
#: how the caller learns whether a durable row was there at all, which is not the
#: same question as whether a workspace directory was.
Q_DELETE_EXPERIMENT = "DELETE FROM isaac_experiments WHERE experiment_id = %s"

# --- is the table even there yet? the deployment-order guard -------------------

#: The relation the three statements above name. It is a NAMED CONSTANT because
#: :data:`Q_RUN_TABLE_PRESENT` passes it as a parameter rather than writing it into
#: the statement text, and a table name that appears nowhere in any SQL string is a
#: table name nobody greps up.
#: ``test_0002_is_now_written_by_the_write_path_and_by_nothing_else`` pins this
#: constant beside the three statements, in the one place that enumerates them.
RUN_TABLE = "isaac_runs"


#: "DOES ``isaac_runs`` EXIST YET?", ASKED BEFORE ANYTHING WRITES TO IT.
#:
#: WHAT IT PREVENTS, AND IT IS NOT A HYPOTHETICAL. In this project the image rolls
#: out on merge (Flux) and migrations are applied SEPARATELY AND BY HAND by the
#: operator — ``0001_experiments`` was applied to the hosted database on 2026-08-09
#: and ``0002_runs`` on 2026-08-12, each by the owner, neither by a deployment. So a
#: new image ROUTINELY runs against a database its own migration has not reached:
#: that window is the hosted deployment's normal state between a merge and an
#: operator's ``--apply``, its width is however long the operator takes, and the
#: same state is what a deliberate ``0002`` rollback leaves behind. Unguarded, the
#: run writes address a relation that does not exist, the server raises
#: ``undefined_table``, and — see the next paragraph — the experiment upsert dies
#: with it. EVERY SAVE WOULD FAIL,
#: AND DURABLE STORAGE WOULD BREAK, FOR A TABLE NOTHING READS.
#: ``.github/workflows/ci.yml``'s "Apply 0001 ONLY" step caught exactly that, which
#: is what this constant exists to answer.
#:
#: WHY A PRE-CHECK AND NOT A ``try``/``except`` AROUND THE RUN STATEMENTS. In
#: PostgreSQL a failed statement POISONS THE WHOLE TRANSACTION: every later command
#: is refused with "current transaction is aborted, commands ignored until end of
#: transaction block", so "swallow the error and commit the experiment anyway" is
#: not something the server permits — the experiment upsert would roll back with
#: the run write. ``db_write.write_transaction`` independently rolls back on ANY
#: exception, so the shape is refused twice over. That leaves exactly two designs
#: that can work: a ``SAVEPOINT`` around the run writes, or asking first.
#:
#: SAVEPOINTS WERE EVALUATED AND REJECTED, on three counts rather than on taste.
#: They pass the statement policy (measured), so the objection is not feasibility.
#: (1) They cost TWO extra statements on EVERY save, forever, where this probe
#: costs zero once the table has been seen. (2) ``ROLLBACK TO SAVEPOINT`` catches
#: every error alike, so a genuinely broken run write would be silently discarded
#: as "the table must be missing" — the one thing this guard must not do. (3)
#: Recovering that distinction means re-classifying the SQLSTATE afterwards anyway,
#: at which point the savepoint has bought nothing but round trips.
#:
#: WHY ``to_regclass`` AND NOT THE TWO OBVIOUS ALTERNATIVES:
#:
#: * ``information_schema.tables`` and ``pg_catalog.pg_class`` are REFUSED by
#:   :class:`~isaac_api.db_write.WriteStatementPolicy` — neither is in
#:   ``OWNED_TABLES``, and the policy refuses an unowned table by design and
#:   should not be widened for a probe. Measured, not assumed:
#:   ``test_the_catalog_views_this_probe_deliberately_does_not_use_are_REFUSED``.
#: * ``isaac_schema_migrations`` PASSES the policy and is THE WRONG ORACLE. The
#:   bookkeeping row and the relation can disagree, and CI itself builds a state
#:   where they do: the idempotence step runs ``DELETE FROM
#:   isaac_schema_migrations`` while both tables still stand. A bookkeeping-based
#:   probe would then skip the run writes forever against a table that is right
#:   there — silently, because nothing reads it.
#:
#: ``to_regclass`` RETURNS NULL for a name that does not resolve instead of raising
#: (``'isaac_runs'::regclass`` raises, which is the failure being avoided), and it
#: resolves through the same ``search_path`` the unqualified names in the three
#: statements above use — so it answers the question those statements actually ask,
#: rather than a similar question about a hardcoded schema.
#:
#: THE TABLE NAME IS A PARAMETER, AND THAT IS NOT AN EVASION OF ANYTHING.
#: ``isaac_runs`` is owned, so the literal form passes the policy too. It is a
#: parameter so that "a save on a 0001-only deployment issues no statement naming
#: ``isaac_runs``" stays a MECHANICALLY CHECKABLE property — in the tests and in
#: CI — instead of a property carrying an exception. The cost is discoverability,
#: and :data:`RUN_TABLE` above plus its pinning test are what pay it.
Q_RUN_TABLE_PRESENT = "SELECT to_regclass(%s::text)"


#: HAS THIS PROCESS SEEN ``isaac_runs`` EXIST? One bit, module-level for the same
#: reason ``_storage_failure`` is one: :func:`ordinary_store` builds a new store per
#: call, so a per-instance cache would be a cache that never hits.
#:
#: THE ASYMMETRY IS THE DESIGN, NOT AN OPTIMISATION DETAIL, and each half is here
#: for a different failure.
#:
#: ``True`` IS CACHED FOR THE LIFE OF THE PROCESS. A migration cannot un-apply
#: itself; "the table exists" stops being true only if an operator deliberately
#: rolls it back, and :meth:`PostgresOrdinaryStore.persist` handles that case from
#: the server's own SQLSTATE rather than by re-asking on the chance of it. So the
#: steady state — the deployment everyone actually runs — costs ZERO extra
#: statements per save.
#:
#: ``False`` IS NEVER CACHED. The operator applies the migration BY HAND AGAINST A
#: RUNNING POD, and no restart follows; a negative cache would leave ``isaac_runs``
#: permanently empty on exactly the deployment that was just migrated, silently,
#: because nothing reads the table to notice. One probe per save while the table is
#: genuinely absent is the price of not needing that restart, and it is paid only
#: in a window that is meant to be short.
#:
#: A SET RATHER THAN A BOOLEAN, because there are now two migrations whose tables a
#: running pod may not have yet — ``0002_runs`` and ``0005_run_projection``. The
#: reasoning above applies unchanged to each; what would NOT survive is a second
#: copy of it beside a second boolean, so the mechanism is shared and the two
#: callers name their own table.
_tables_seen: set[str] = set()


def run_table_seen() -> bool:
    """Whether this process has confirmed ``isaac_runs`` exists.

    An OBSERVATION for tests and reports. Nothing in the application branches on
    it — :func:`_table_available` is what decides, and it decides against the
    open transaction.
    """
    return RUN_TABLE in _tables_seen


def projection_table_seen() -> bool:
    """Whether this process has confirmed ``isaac_run_projection`` exists."""
    return PROJECTION_TABLE in _tables_seen


def forget_run_table_presence() -> None:
    """Drop EVERY cached "the table is there" observation. TWO REAL CALLERS.

    The tests, so one case cannot inherit another's cache — the same reason
    :func:`forget_storage_failure` exists and is cleared by an autouse fixture.

    And :meth:`PostgresOrdinaryStore.persist`, when the server answers
    ``undefined_table`` from a run statement after this process had already seen
    the table. That means the operator rolled ``0002`` back under a live pod. The
    save still FAILS — the transaction is already aborted and nothing is being
    swallowed — but the next one re-probes, finds the table gone, and skips the run
    writes, so saves recover after one failure instead of after a restart nobody
    is watching for.

    IT CLEARS BOTH TABLES DESPITE ITS NAME, and that is deliberate rather than
    sloppy. The one production caller reaches here because a server said
    ``undefined_table`` and this code cannot tell WHICH relation the server meant
    — the SQLSTATE carries no name this path reads. Clearing more than necessary
    costs one extra probe on the next save; clearing less would leave a false
    positive cached for the life of the pod, which is the failure this function
    exists to prevent. The name is kept because it is the name every existing
    caller and test uses, and renaming a safety hook is a worse trade than
    documenting one.
    """
    _tables_seen.clear()


def _table_available(cursor, policy, table: str) -> bool:
    """Whether ``table`` exists, asked at most once per process once it does.

    Uses the transaction ALREADY OPEN, so the answer is the one this transaction's
    own statements would get, from the same ``search_path``, at the same instant.

    IT SWALLOWS NOTHING, and that is the property that keeps "the table is absent"
    and "the write is broken" distinguishable. ``to_regclass`` ANSWERS ``NULL`` for
    an absent relation — it does not raise — so a ``False`` here is a fact the
    server stated. If the probe itself fails, that exception propagates exactly as
    any other statement's would and :meth:`PostgresOrdinaryStore.persist` reports
    the outage it is. There is no ``except`` anywhere on this path.
    """
    if table in _tables_seen:
        return True
    cursor.execute(policy.check(Q_RUN_TABLE_PRESENT), (table,))
    row = cursor.fetchone()
    if not row or row[0] is None:
        return False
    _tables_seen.add(table)
    return True


def _run_row_params(experiment_id: str, run: "ws.Run") -> tuple:
    """THE ONE PLACE A ``Run`` BECOMES AN ``isaac_runs`` ROW.

    Returns the parameters for :data:`Q_UPSERT_RUN`, in its order. Pure: it reads a
    run and returns a tuple, opens nothing, and is deliberately callable — and
    tested — without a database.

    ``experiment_id`` IS THE OWNING EXPERIMENT'S ID AND NEVER ``run.experiment_id``.
    They are normally equal and the case where they are not is the whole reason to
    be explicit: ``workspace._hydrate_runs`` documents that a run's
    ``experiment_id`` is deliberately NOT repaired from its owner, because
    repairing it on READ would change the run's authoritative signature and bump
    every record's ``rev`` on a mere listing. So a legacy run document carries
    ``experiment_id: ""``, permanently. The COLUMN is a real foreign key and must
    name the experiment whose transaction is writing this row; the DOCUMENT keeps
    whatever it has always said. ``0002_runs``' ``isaac_runs_document_identity``
    CHECK is written to admit exactly that pairing — it treats ``''`` as absent —
    and a row built any other way would be refused by the database.

    ``state`` IS ``run.to_state()`` VERBATIM, including its ``runs``-side
    duplication with the experiment document. Nothing is dropped, reordered or
    "cleaned": the promoted columns are a projection OF the document and never a
    replacement for it, which is `0002_runs`' own stated rationale.

    ``sort_keys=True`` matches what :meth:`PostgresOrdinaryStore.persist` already
    does for the experiment payload. It is presentation only — the column is
    ``jsonb``, which compares by VALUE — and it keeps the parameter deterministic,
    which is what makes a test able to assert on it.

    THE ``generation`` FALLBACK IS DEFENCE IN DEPTH AND IS NOT REACHABLE TODAY.
    ``Run.__post_init__`` mints ``_legacy_generation(self.id)`` for any run
    constructed without one, and nothing in this package assigns ``.generation``
    afterwards, so ``run.generation`` is non-empty by construction. It is written
    anyway because the column is ``NOT NULL`` with NO DEFAULT and ``''`` SATISFIES
    ``NOT NULL``: the migration's own comment says a writer that omits the
    generation "has a bug and should be told so by the database", and the database
    would in fact accept the empty string in silence. Reusing the model's own rule
    is the only fallback that is not an invention.
    """
    return (
        run.id,
        experiment_id,
        int(run.ordinal),
        json.dumps(run.to_state(), sort_keys=True),
        int(run.rev),
        run.generation or ws._legacy_generation(run.id),
    )


def _stored_run_rows(rows: Any) -> dict[str, tuple]:
    """``run_id -> (ordinal, state, rev, generation)`` for the rows already stored.

    ``state`` is normalised to a document with the same tolerance
    :func:`_row_state` applies: psycopg2 returns ``jsonb`` as a ``dict``, and
    anything without the adapter registered returns text. A value that is neither
    is mapped to ``None``, which can never equal a run's ``to_state()`` — so an
    unreadable stored document makes the row look DIFFERENT and gets rewritten,
    which is the safe direction for a row that is meant to be a projection.
    """
    out: dict[str, tuple] = {}
    for row in rows or []:
        state = row[2]
        if isinstance(state, (str, bytes, bytearray)):
            try:
                state = json.loads(state)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                state = None
        if not isinstance(state, dict):
            state = None
        out[str(row[0])] = (row[1], state, row[3], row[4])
    return out


def _row_state(row: Any) -> dict | None:
    """The state document in a ``(state,)`` row, or ``None`` if it is unusable.

    ``jsonb`` comes back as a ``dict`` from psycopg2 and as text from anything
    that has not registered the adapter, so both are accepted — the same tolerance
    :meth:`PostgresOrdinaryStore.hydrate` already applies to the rows it reads.
    """
    if not row:
        return None
    state = row[0]
    if isinstance(state, (str, bytes, bytearray)):
        try:
            state = json.loads(state)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
    return state if isinstance(state, dict) else None


class PostgresOrdinaryStore:
    """Durable storage for ORDINARY-scope experiment state. Nothing else.

    It holds no connection: every call opens one short-lived transaction through
    :func:`~isaac_api.db_write.write_transaction` and closes it. That is slower
    than a pool and it is the right trade here — this is a low-frequency path
    (a create, a save after an answer, a list) and a pool is state that can go
    wrong on a pod that is expected to be restarted freely.
    """

    def __init__(self, env: Mapping[str, str] | None = None, **connect_kwargs: Any) -> None:
        self.env: Mapping[str, str] = os.environ if env is None else env
        self._connect_kwargs = connect_kwargs

    # -- the isolation guard, in one place ------------------------------------

    @staticmethod
    def refuse_if_not_persistable(exp: "ws.Experiment") -> None:
        """Raise unless ``exp`` is an ordinary-scope, non-example record.

        BOTH conditions, and both matter for a different reason.

        ``session_id is not None`` — a worked-example session is temporary,
        synthetic and discarded with the session. Writing one to the database
        would make a temporary workspace durable, which is the single thing this
        change must not do.

        ``id in CANONICAL_IDS`` — the five built-in example records. Nothing in
        this build puts one in the ordinary scope, but a workspace left by an
        older build can already contain them (``workspace.py`` documents that
        state at length), and hydration + write-through would otherwise promote
        that historical accident into the database permanently.
        """
        if exp.session_id is not None:
            raise NotPersistable(
                "a worked-example session record can never be written to the "
                "application database"
            )
        if exp.id in ws.CANONICAL_IDS:
            raise NotPersistable(
                "a built-in example record can never be written to the "
                "application database"
            )

    # -- write-through ---------------------------------------------------------

    def persist(
        self, exp: "ws.Experiment", *, projector: str = PROJECTOR_WRITE_PATH
    ) -> None:
        """COMPARE-AND-SWAP one ordinary-scope experiment's authoritative state.

        ``projector`` NAMES WHO IS DOING THE PROJECTING, and it is the ONE value in
        the completeness claim that this method cannot derive from ``exp``. It
        defaults to :data:`PROJECTOR_WRITE_PATH`, so every existing caller —
        ``ws.Experiment.save`` and every test — keeps the exact behaviour it had;
        the only caller that passes anything else is
        ``scripts/db_backfill_runs.py``, which passes :data:`PROJECTOR_BACKFILL`.
        See :data:`PROJECTOR_BACKFILL` for what was measured wrong and why a
        keyword argument is the right shape rather than a second write path.

        IT IS DELIBERATELY NOT VALIDATED HERE. The closed value set lives in
        ``0005_run_projection``'s own CHECK, so a value that is neither of the two
        is refused by the database rather than stored — and a second copy of the
        enumeration in this module is a second thing that can drift away from the
        migration. The two constants above exist so no caller has to type a
        literal.

        RAISES :class:`StorageUnavailable` if the database is not REACHABLE, and
        deliberately does NOT fall back to the filesystem. The caller
        (``workspace.Experiment.save``) has already been told, through
        ``storage_status``, that this deployment stores experiments durably; a
        quiet ephemeral write would withdraw that promise without saying so, and
        the reader would only discover it at the next pod restart. Failing here
        means the workspace file is not rewritten either, so the record is not left
        looking saved.

        RAISES :class:`DurableWriteConflict` if the database evaluated the write
        and REFUSED it — the stored document had already moved on. That is not an
        outage and is not recorded as one; see the exception's own docstring for
        why all three failure types are kept apart, and :data:`Q_UPSERT_EXPERIMENT`
        for the predicate itself.

        THE "SO THE WORKSPACE FILE IS NOT REWRITTEN" CLAUSE ABOVE BELONGS TO THE
        OUTAGE AND NOT TO THE REFUSAL, and it used to be phrased as though it
        covered both. This client's state is never written locally in either case
        — but on a refusal the caller rewrites the workspace file with the
        WINNER's document before re-raising, which is what stops a strict
        compare-and-swap wedging (``ws.Experiment._adopt_winner_locally``).

        THE TWO REFUSALS ARE RAISED IN DIFFERENT PLACES, AND BOTH PLACEMENTS ARE
        LOAD-BEARING. :class:`NotPersistable` is raised before the try, because it
        is a permanent property of the record and must never be reported as, or
        recorded as, a storage failure. :class:`DurableWriteConflict` is raised
        AFTER the ``with`` block for the same family of reason: inside it, the
        blanket ``except Exception`` would relabel it as an outage, and the
        transaction would roll back rather than commit — which is harmless (nothing
        was written) but would leave the read-back of the winner's row in a
        rolled-back transaction. Committing an empty transaction and then raising
        keeps "what the database decided" and "how this application reports it"
        separable.

        IT ALSO WRITES THE RUN ROWS, AND THAT IS WHY THIS METHOD IS THE ONLY PLACE
        THEY CAN BE WRITTEN FROM. `isaac_runs` is a PROJECTION of the experiment
        document: after this returns, the rows of that table for this experiment
        equal ``exp.sorted_runs()``, while ``to_state()`` still carries ``runs``.
        ~~"and remains the authoritative copy that every read path uses"~~ —
        CORRECTED FOR STAGE 2b: it remains the authoritative copy for every read
        path EXCEPT :meth:`hydrate`, which builds a restored document's ``runs``
        from the rows when the projection is COMPLETE, and which falls back to the
        document in all three other states and on any mismatch. See
        :data:`Q_EXPERIMENT_RUN_ROWS` and the statements beside it.

        IT WRITES THEM ONLY IF THE TABLE IS THERE, AND THAT IS A DEPLOYMENT FACT
        RATHER THAN A DEFENSIVE HABIT. The image rolls out on merge and an operator
        applies migrations by hand afterwards, so a build runs against a database
        missing its own table as a matter of course. When ``isaac_runs`` is absent
        the run rows are SKIPPED and everything else is unchanged: the experiment
        row is written, the transaction commits, and ``/api/health`` goes on
        reporting ``durable: true`` — which is TRUE, because the experiment
        document is the durable state and it is stored. The rows are a shadow
        nothing reads, so their absence must never fail a save or downgrade the
        claim made about one. :data:`Q_RUN_TABLE_PRESENT` is the check and carries
        the reasoning.

        THE TUTORIAL RULE IS SATISFIED BY ARCHITECTURE, NOT BY A FOURTH CHECK. The
        run write lives after :meth:`refuse_if_not_persistable`, in the one method
        the isolation guards already protect, so it inherits all three of them by
        construction. A ``PostgresRunStore`` — or any second write path — must never
        be created, and the reason is specific rather than stylistic:
        ``isaac_runs`` HAS NO ``session_id`` COLUMN AND CAN NEVER GAIN ONE.
        ``ALTER`` is a forbidden verb in ``db_write._FORBIDDEN_KEYWORDS`` and
        ``CREATE TABLE IF NOT EXISTS`` is a silent no-op against a table that
        already exists, so a worked-example run that ever reached this table would
        be permanently unidentifiable and permanently uncleanable. The cost of that
        leak is not "a cleanup script"; it is that no cleanup script could be
        written.
        """
        self.refuse_if_not_persistable(exp)
        payload = json.dumps(exp.to_state(), sort_keys=True)
        # THE WHOLE DESIRED ROW SET IS PROJECTED BEFORE THE TRANSACTION OPENS, and
        # the placement is deliberate: inside the `try` below, ANY exception is
        # relabelled as a storage outage, so a defect in this application's own
        # projection would be reported as "the database did not answer" and would
        # set the process-wide `durable: false` bit over a database that is
        # perfectly healthy. Out here it raises as itself.
        desired = [(run, _run_row_params(exp.id, run)) for run in exp.sorted_runs()]
        desired_ids = [run.id for run, _ in desired]
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                cursor.execute(policy.check(Q_UPSERT_EXPERIMENT), (exp.id, payload))
                # A conflict action whose WHERE is false updates nothing and
                # raises nothing. `rowcount` over `RETURNING` is what makes that
                # silence observable.
                accepted = cursor.rowcount == 1
                stored = None
                if accepted:
                    # ── THE SINGLE MOST DANGEROUS LINE IN THIS SLICE IS THE ONE
                    # ── ABOVE: `if accepted`. ────────────────────────────────────
                    # Before run rows existed, a refused upsert wrote nothing
                    # because there was only one statement to refuse. With these
                    # statements added, a writer that LOST the compare-and-swap and
                    # stamped its runs anyway would overwrite the winner's rows
                    # while correctly reporting 412 to its own client — the exact
                    # last-writer-wins defect `Q_UPSERT_EXPERIMENT`'s predicate was
                    # written to close, reintroduced one level down and invisible,
                    # because the losing client is told it lost. The run writes are
                    # strictly inside the accepted branch, and
                    # `test_a_refused_experiment_upsert_writes_no_run_statement_at_all`
                    # goes RED if they are moved out of it.
                    #
                    # ── AND THE SECOND GATE: DOES THE TABLE EXIST YET? ───────────
                    # The image rolls out on merge; the operator applies migrations
                    # by hand afterwards. So this build routinely runs against a
                    # database where `0002` is still pending, and the run writes
                    # would address a relation that is not there — aborting the
                    # transaction and taking the experiment upsert down with it.
                    # A save that fails for a table NOTHING READS is the whole
                    # defect; see `Q_RUN_TABLE_PRESENT` for why this is a
                    # pre-check and not a `try`/`except`.
                    if _table_available(cursor, policy, RUN_TABLE):
                        try:
                            written = self._write_run_rows(
                                cursor, policy, exp.id, desired, desired_ids
                            )
                            # ── AND THE COMPLETENESS CLAIM, INSIDE THE SAME
                            # ── TRANSACTION AS THE ROWS IT DESCRIBES. ───────────
                            # There is deliberately no path that writes one
                            # without the other: two statements in one transaction
                            # cannot end up disagreeing about whether they
                            # committed. It is also strictly inside the `accepted`
                            # branch, for the same reason the run rows are — a
                            # writer that LOST the compare-and-swap claiming
                            # completeness would be claiming it for a document it
                            # failed to write.
                            #
                            # `written` is MEASURED — the number of rows the
                            # projection actually contains after this transaction —
                            # not `len(desired)` as an intention. The contract
                            # (`docs/isaac-runs-stage-2-contract.md` §2.2) requires
                            # that, and they differ if `_write_run_rows` ever grows
                            # a skip.
                            #
                            # The presence check is SEPARATE from the run table's
                            # because rolling `0005` back while `0002` stays is a
                            # reachable operator action.
                            # ~~"the migration ORDER guarantees the converse cannot
                            # happen."~~ — CORRECTED 2026-08-24, the same overreach
                            # an independent review measured in
                            # `0005_run_projection.sql`'s header. The converse IS
                            # reachable: `0005_run_projection.rollback.sql` states
                            # that rolling `0002` back does not require rolling
                            # `0005` back first, and
                            # `test_0002_ABSENT_makes_no_claim_either_even_though_0005_may_be_there`
                            # exists because it is. Nothing about THIS CODE changes
                            # — the two probes were already separate and the stamp
                            # is already nested inside the run-row branch, so that
                            # environment produces no claim rather than a false
                            # one. Only the comment claimed a guarantee the runner
                            # does not give.
                            if _table_available(cursor, policy, PROJECTION_TABLE):
                                self._stamp_projection(
                                    cursor, policy, exp, written, projector
                                )
                        except Exception as exc:  # noqa: BLE001 - re-raised below
                            # NOT A RECOVERY, AND NOT A CONTINUE. The transaction
                            # is already aborted and this save is already lost; the
                            # `raise` is unconditional and one line down. All that
                            # happens here is that a POSITIVE cache which the server
                            # has just contradicted stops being believed — the
                            # operator rolled `0002` back under a running pod, and
                            # without this the pod would keep failing every save
                            # until someone restarted it. Classified from the
                            # server's own SQLSTATE, which `is_undefined_table`
                            # reads fail-closed, so a broken write against a table
                            # that DOES exist changes nothing here and still raises.
                            if is_undefined_table(exc):
                                forget_run_table_presence()
                            raise
                else:
                    cursor.execute(policy.check(Q_ONE_EXPERIMENT), (exp.id,))
                    stored = _row_state(cursor.fetchone())
        except Exception as exc:  # noqa: BLE001 - any driver/server failure, uniformly
            raise _unavailable(exc) from exc
        # The round trip WORKED, whichever way it was decided — so an earlier
        # outage is cleared either way. A refused write is not evidence of a sick
        # database, and `/api/health` must not start reporting one because two
        # writers raced.
        _note_storage_success()
        if not accepted:
            raise DurableWriteConflict(stored, experiment_id=exp.id)

    @staticmethod
    def _write_run_rows(cursor, policy, experiment_id: str, desired, desired_ids) -> int:
        """Make this experiment's ``isaac_runs`` rows equal ``desired``. DIFFED.

        NOT A SECOND WRITE PATH, and it is written so that it cannot become one: it
        takes an ALREADY-OPEN cursor and the policy of the transaction that owns it,
        so there is no way to call it that does not go through
        :meth:`persist`'s transaction — and therefore through
        :meth:`refuse_if_not_persistable` and the accepted gate. It is a private
        method rather than a class because a class is what a future caller
        instantiates.

        IT ASSUMES THE TABLE EXISTS, DELIBERATELY. Its one caller has already
        established that through :func:`_table_available`, so nothing here
        tolerates an absent relation and nothing here should start to: a
        ``try``/``except`` in this method could not work anyway (an error aborts
        the transaction, so the experiment upsert would roll back with it), and a
        second check would only make the first one look optional.

        THE DIFF IS REQUIRED, NOT AN OPTIMISATION. Rewriting all N rows on every
        save would issue N+1 statements under a 15-second per-statement timeout —
        for a wide record that is worse than the single document write it is
        supposed to improve on, which would make this change a regression dressed
        as progress. One indexed ``SELECT`` establishes what is already there;
        normally exactly one run has moved, so exactly one write follows.

        WHAT COUNTS AS "DIFFERENT" IS EVERY COLUMN THIS APPLICATION OWNS —
        ``ordinal``, ``state``, ``rev`` and ``generation`` — not just the version
        pair. ``state`` is in the comparison because a run's document can change
        without its ``rev`` moving (``Experiment.save()`` is the unversioned
        primitive; only ``save_versioned`` bumps), and the promoted columns are in
        it because they are writer-maintained projections that no CHECK constrains
        — ``0002_runs`` says so itself. ``created_utc`` and ``updated_utc`` are
        excluded: they are server-side row stamps, not projections of anything.

        THE ORDER IS SELECT -> UPSERT -> DELETE. Run ids are freshly minted ULIDs
        and the primary key is ``run_id``, so no ordering here can collide; the
        delete goes last so that a wide save's writes are not preceded by a
        statement that usually deletes nothing.
        """
        cursor.execute(policy.check(Q_EXPERIMENT_RUN_ROWS), (experiment_id,))
        stored = _stored_run_rows(cursor.fetchall())
        for run, params in desired:
            current = stored.get(run.id)
            # `params` is (run_id, experiment_id, ordinal, state_json, rev,
            # generation); the stored tuple is (ordinal, state, rev, generation).
            # `experiment_id` is not compared because the SELECT's WHERE already
            # pinned it, and `state_json` is compared as a DOCUMENT rather than as
            # text — the column is jsonb, which normalises key order and whitespace,
            # so a text comparison would report a difference on every save and turn
            # the diff back into a blanket rewrite.
            if current is not None and current == (
                params[2],
                run.to_state(),
                params[4],
                params[5],
            ):
                continue
            cursor.execute(policy.check(Q_UPSERT_RUN), params)
        if set(stored) - set(desired_ids):
            cursor.execute(
                policy.check(Q_DELETE_ABSENT_RUNS), (experiment_id, list(desired_ids))
            )
        # THE MEASURED ROW COUNT, returned rather than recomputed by the caller.
        # After this method the table holds exactly the desired set for this
        # experiment: every desired row was upserted or found already equal, and
        # everything outside the set was deleted. `len(desired_ids)` is that number
        # BECAUSE of the two statements above, which is why it is returned from
        # here — from the caller it would be an assumption about this method.
        return len(desired_ids)

    @staticmethod
    def _stamp_projection(
        cursor, policy, exp: "ws.Experiment", run_count: int, projector: str
    ) -> None:
        """Record that this experiment's ``isaac_runs`` rows are complete AT THIS
        VERSION.

        NOT A SECOND WRITE PATH, and written so it cannot become one: it takes an
        already-open cursor and the policy of the transaction that owns it, so
        there is no way to call it that does not go through :meth:`persist`'s
        transaction — and therefore through :meth:`refuse_if_not_persistable`, the
        ``accepted`` gate, and the run-row write whose result it describes.

        WHY THE VERSION PAIR IS STAMPED AND NOT JUST A BOOLEAN. A bare "complete"
        flag is indistinguishable from a stale one, so a reader would have to
        ASSUME staleness absent. Recording the ``(rev, generation)`` the rows were
        projected from makes staleness DETECTABLE: a later save that does not
        maintain the rows advances the document past this value and the pair stops
        matching. Both keys, not just ``rev``, for :data:`Q_UPSERT_EXPERIMENT`'s
        reason — ``rev`` alone cannot see a record destroyed and rebuilt at rev 0.

        THE VALUES COME FROM THE DOCUMENT BEING WRITTEN, not from a re-read.
        ``exp.rev`` and ``exp.generation`` are the same fields
        ``json.dumps(exp.to_state())`` just embedded in the row this transaction
        upserted, so the claim describes the document that was committed rather
        than whatever a second statement might have found.

        TUTORIAL ISOLATION IS INHERITED BY CONSTRUCTION and must stay that way.
        ``isaac_run_projection`` HAS NO ``session_id`` COLUMN AND CAN NEVER GAIN
        ONE — ``ALTER`` is a forbidden verb in ``db_write._FORBIDDEN_KEYWORDS`` and
        ``CREATE TABLE IF NOT EXISTS`` is a silent no-op against an existing table
        — so a worked-example claim that ever reached this table would be
        permanently unidentifiable and permanently uncleanable. The cost of that
        leak is not "a cleanup script"; it is that no cleanup script could be
        written. Hence: one writer, inside the one method the isolation guards
        already protect.

        THE PROJECTOR IS PASSED IN, NOT ASSUMED, and the previous version assumed it.
        It hard-coded :data:`PROJECTOR_WRITE_PATH` at this one call site, which is the
        only place :data:`Q_UPSERT_RUN_PROJECTION` is ever executed — so the operator
        backfill, which reaches here through :meth:`persist` exactly as an ordinary save
        does, stamped every row it wrote with the producer it was not. See
        :data:`PROJECTOR_BACKFILL` for the measurement and for why the Stage-2b gate
        query in ``docs/migration-approval-packet-0005.md`` §8A could not be answered
        while that was true.
        """
        cursor.execute(
            policy.check(Q_UPSERT_RUN_PROJECTION),
            (exp.id, exp.rev, exp.generation, run_count, projector),
        )

    # -- discard ---------------------------------------------------------------

    def discard(self, exp: "ws.Experiment") -> int:
        """REMOVE one ordinary-scope experiment's durable state. Nothing else.

        Returns how many ``isaac_experiments`` rows were removed — MEASURED from
        the server's own ``rowcount``, so ``0`` is the honest answer for a record
        this deployment never persisted (created before the migration was applied,
        or written while the database was unreachable) and is not an error.

        WHAT IT REMOVES, EXHAUSTIVELY: this experiment's row, its ``isaac_runs``
        rows, and its ``isaac_run_projection`` claim. The three statements are
        named above, in foreign-key dependency order, and the whole reasoning about
        why that order is a requirement rather than a preference lives there.

        WHAT IT NEVER REMOVES: any row of the five submission-lifecycle tables, and
        anything at all in ``records``. No statement here names one, which is the
        whole of the guarantee — see the comment above the statements for why the
        database cannot provide it and which test states it.

        ONE TRANSACTION, so the three deletes are all-or-nothing. A record that
        still carries history therefore loses NOTHING: the final statement is
        refused by the server's foreign key and the two run-side deletes roll back
        with it.

        RAISES :class:`NotPersistable` before opening anything, for a worked-example
        record or a canonical example id — the same guard :meth:`persist` runs, in
        the same place, for the same reason. It is a permanent property of the
        record and must never be reported as, or recorded as, a storage failure.
        In practice this is unreachable from ``workspace.discard_experiment``,
        which resolves no store at all for a session scope; it is asserted here
        because this class is what a future caller would reach for.

        RAISES :class:`DiscardRefusedByHistory` when the server refuses the
        experiment delete with a foreign-key violation. That is the backstop
        firing, it is not an outage, and it is deliberately NOT recorded as one.

        RAISES :class:`StorageUnavailable` for every other failure, carrying
        :data:`STORAGE_DISCARD_FAILED_MESSAGE` rather than the write wording — a
        reader told "nothing was saved" about a failed discard would conclude the
        discard had worked.

        THERE IS NO COMPARE-AND-SWAP HERE, AND THAT IS A STATEMENT ABOUT WHERE THE
        PRECONDITION LIVES RATHER THAN AN OMISSION. ``If-Match`` is checked by the
        route, inside the same ``record_lock`` critical section as this call, over
        an experiment re-read inside that lock. A durable predicate as well would
        need the delete to name a ``rev`` — and the honest failure mode of getting
        that wrong is the opposite of the one the upsert guards: an upsert that
        loses a race writes stale science, while a delete that loses one removes a
        record whose new content the deleter never saw. That case is bounded here
        by the fact that this process serialises on the record and by the route's
        own re-read; a cross-process delete race would need the same treatment
        ``Q_UPSERT_EXPERIMENT`` gets, and is named as not-done rather than implied.
        """
        self.refuse_if_not_persistable(exp)
        removed = 0
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                # THE TABLE-PRESENCE PROBES ARE THE SAME ONES THE WRITE PATH MAKES,
                # for the same deployment reason: the image rolls out on merge and
                # the operator applies migrations by hand afterwards, so this build
                # routinely runs against a database where `0002` and/or `0005` are
                # still pending. Naming an absent relation would abort the
                # transaction and take the experiment delete down with it — a
                # discard that fails for a table NOTHING READS.
                if _table_available(cursor, policy, PROJECTION_TABLE):
                    cursor.execute(
                        policy.check(Q_DELETE_RUN_PROJECTION_FOR_EXPERIMENT), (exp.id,)
                    )
                if _table_available(cursor, policy, RUN_TABLE):
                    cursor.execute(
                        policy.check(Q_DELETE_RUNS_FOR_EXPERIMENT), (exp.id,)
                    )
                cursor.execute(policy.check(Q_DELETE_EXPERIMENT), (exp.id,))
                count = cursor.rowcount
                removed = int(count) if isinstance(count, int) and count > 0 else 0
        except Exception as exc:  # noqa: BLE001 - classified, then re-raised as ours
            if is_foreign_key_violation(exc):
                # The round trip WORKED and the server behaved exactly as designed.
                # Recording an outage here would send an operator to look at a
                # healthy database and would make `/api/health` claim durability
                # had failed.
                _note_storage_success()
                raise DiscardRefusedByHistory(exp.id) from exc
            if is_undefined_table(exc):
                # A positive cache the server has just contradicted stops being
                # believed — the operator rolled a migration back under a running
                # pod. This is NOT a recovery: the transaction is already aborted
                # and this discard is already lost. See `forget_run_table_presence`.
                forget_run_table_presence()
            raise _unavailable(exc, STORAGE_DISCARD_FAILED_MESSAGE) from exc
        _note_storage_success()
        return removed

    # -- restore ---------------------------------------------------------------

    def hydrate(self) -> int:
        """Write back any stored experiment whose workspace directory is missing.

        Returns how many were restored — a MEASURED count of directories this
        call created, not the row count.

        IT RESTORES; IT DOES NOT REFRESH. The skip is on ``experiment.json``, not
        on the row: a record whose state file is already present is left exactly as
        it is, however stale it is — so a replica that hydrated a
        record once never sees a later revision of it through this path. That is
        deliberate (a re-read must not silently overwrite local state), and it is
        the reason a refused durable write adopts the winner's document into the
        workspace file itself — see ``ws.Experiment._adopt_winner_locally``.

        THIS IS ALSO THE ONE PLACE STAGE 2b MOVES, AND IT MOVES ONE KEY. For an
        experiment whose projection is COMPLETE, the restored document's ``runs``
        is built from ``isaac_runs`` rows rather than from the stored document's
        own ``runs`` — see :func:`resolve_run_authority` for the four-state
        predicate and the mismatch rule, and the section above it for what
        deliberately does NOT move. On STALE, NEVER PROJECTED, UNAVAILABLE or a
        mismatch the document is written exactly as it was stored, which is what
        every build before this one did for every experiment. Fallback is normal
        operation, not an error path.

        THE ADDED READS ARE SKIPPED ENTIRELY WHEN THERE IS NOTHING TO RESTORE, and
        that bound is the reason this is affordable on a per-request path: this
        method runs on every ordinary ``GET /api/experiments``, and on a warm pod
        every ``experiment.json`` is already present, so the candidate list is
        empty and no statement naming either table is issued.

        It writes ONLY into ``workspace_root()``. The tutorial namespace is never
        addressed: there is no session id anywhere in this method, and a stored
        row can never carry one (``persist`` refuses it). A row whose id is not a
        well-formed record id, or is a canonical example id, is skipped rather
        than written — the same fail-closed reading the rest of the workspace
        layer applies to anything it did not just create itself.

        THREE ``continue`` ARMS, AND THEY ARE NOT THE SAME KIND OF THING. Stating
        this precisely matters because the docstring here once said the disclosure
        hole was closed while two of these still dropped rows in silence.

        * ``state_path.exists()`` — NOT A SKIP AT ALL. The working copy is already
          on disk, so the record IS in the list; there was nothing to do.
        * a non-record id, or a canonical example id — A REFUSAL, AND IT IS NOT
          REPORTED AS AN INCOMPLETE PASS. Neither shape is an ordinary experiment
          this scope may hold: a canonical id belongs to the worked-example
          namespace, which never reads this table, and an id that is not a record
          id could not be addressed by a request even if it were written. Nothing
          this application does can create either row. Declaring the ordinary list
          incomplete because a foreign object sits in the table would be a claim in
          the other direction — that an ordinary experiment is missing, when none
          is — and it would be PERMANENT, since no retry removes the row. That is a
          judgement, not an oversight; if it is ever wrong, it is wrong here.
        * a state document whose ``id`` is not the id the row is filed under — A
          REFUSAL THAT **IS** REPORTED. This one claims to be an ordinary record of
          this scope, and the pass did not represent it, so the pass did not do
          what a caller may assume it did. It is counted and raised as
          :class:`HydrationSkippedRows` AFTER the loop, so every row that could be
          restored still is; the caller degrades and discloses rather than losing
          the rest of the scope to one unusable row.

        RAISES :class:`HydrationSkippedRows` when the loop finished but refused a
        row of that last shape. This application's own writes cannot produce one —
        ``persist`` writes ``exp.id`` alongside ``json.dumps(exp.to_state())``, and
        the document's ``["id"]`` is that same id — so it takes an out-of-band
        write, a partial migration, or a future writer bug. It is raised rather
        than logged because the alternative was measured: the pass looked complete,
        and the record came back as a ``404``.

        RAISES :class:`StorageUnavailable` if the read fails, and the CALLER
        (``workspace._hydrate_ordinary_scope``) is what degrades. The split is
        deliberate: this method's job is to say truthfully whether it restored
        anything, and swallowing the error here would make "restored 0" mean both
        "there was nothing to restore" and "I could not look", which is exactly
        the ambiguity that let a failed read reach a request handler as a 500.

        EXCEPT FOR ONE FAILURE, WHICH IS NOT AN OUTAGE AND IS RAISED AS ITS OWN
        TYPE. If the ``SELECT`` fails because the relation does not exist
        (SQLSTATE ``42P01``, :func:`is_undefined_table`), the store is not
        unreachable — it is UNPROVISIONED, holds nothing, and "restored 0" is then
        a complete and true answer rather than an ambiguous one.
        :class:`StorageNotProvisioned` says so, and the single-record read is what
        acts on the difference: it must go on answering an honest ``404`` in a
        state where no durable record can exist. THIS IS WHY THE CLASSIFICATION
        LIVES HERE and not at the call site — this is the only frame that still
        holds the driver exception, and one frame later there is nothing left to
        classify. Everything else, and anything unrecognised, is an outage.
        """
        root = ws.workspace_root()
        restored = 0
        skipped = 0
        authoritative = run_rows_authoritative(self.env)
        projections: dict[str, tuple[int | None, Any]] = {}
        run_rows: dict[str, list[tuple[str, dict | None]]] = {}
        tables_present = False
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                cursor.execute(policy.check(Q_ALL_EXPERIMENTS))
                rows = cursor.fetchall() or []
                # WHICH ROWS THIS PASS WILL ACTUALLY RESTORE, decided from the id
                # and the filesystem alone — NO JSON IS PARSED IN HERE. That
                # placement is deliberate and is not tidiness: everything inside
                # this `try` is relabelled below as a database outage, and a
                # malformed stored document is not one. Parsing it here would set
                # the process-wide `durable: false` bit over a database that
                # answered perfectly, and would report `store_unavailable` for a
                # record this application simply cannot read.
                candidates = [
                    rid
                    for rid in (str(row[0] or "").strip() for row in rows)
                    if ws.is_record_id(rid)
                    and rid not in ws.CANONICAL_IDS
                    and not (root / rid / "experiment.json").exists()
                ]
                # ── STAGE 2b, AND THE GUARD THAT KEEPS IT FREE IN THE STEADY
                # ── STATE. ──────────────────────────────────────────────────────
                # `hydrate` runs on EVERY ordinary `GET /api/experiments`, and it
                # RESTORES rather than refreshes — so on a warm pod `candidates`
                # is empty and neither statement below is issued at all. The added
                # cost is bounded by how many records are genuinely missing, which
                # is normally zero and is "all of them" exactly once, after a
                # restart. The kill switch is read here too, so an operator's
                # `ISAAC_RUN_ROWS_AUTHORITATIVE=0` stops the statements from being
                # issued rather than merely stopping their answer from being used.
                if candidates and authoritative:
                    try:
                        tables_present = _table_available(
                            cursor, policy, RUN_TABLE
                        ) and _table_available(cursor, policy, PROJECTION_TABLE)
                        if tables_present:
                            cursor.execute(
                                policy.check(Q_RUN_PROJECTIONS_FOR_EXPERIMENTS),
                                (candidates,),
                            )
                            projections = _stored_projections(cursor.fetchall())
                            cursor.execute(
                                policy.check(Q_RUN_ROWS_FOR_EXPERIMENTS),
                                (candidates,),
                            )
                            run_rows = _grouped_run_rows(cursor.fetchall())
                    except Exception as exc:  # noqa: BLE001 - classified, then degraded
                        # THE ONE PLACE THIS READER IS ALLOWED TO SWALLOW, AND IT
                        # SWALLOWS EXACTLY ONE THING. `undefined_table` here means
                        # the operator rolled `0002` or `0005` back under a running
                        # pod AFTER this process had cached "the table is there".
                        # Before Stage 2b that environment served the list fine;
                        # letting this propagate would turn a working My
                        # Experiments into a disclosed-incomplete one for a table
                        # whose whole contract says its absence is normal
                        # operation. Degrading to UNAVAILABLE reads the document,
                        # which is what that environment did yesterday.
                        #
                        # NOTHING FURTHER IS ISSUED ON THIS TRANSACTION. A failed
                        # statement poisons it, so the arm below runs no SQL — it
                        # only forgets a positive cache the server has just
                        # contradicted, exactly as `persist` does. The commit that
                        # follows is an empty one the server turns into a rollback.
                        #
                        # ANY OTHER EXCEPTION RE-RAISES and is classified as the
                        # outage it is. Narrowing this to one SQLSTATE is what
                        # keeps "the table is absent" and "the read is broken"
                        # distinguishable.
                        if not is_undefined_table(exc):
                            raise
                        forget_run_table_presence()
                        tables_present = False
                        projections = {}
                        run_rows = {}
        except Exception as exc:  # noqa: BLE001 - any driver/server failure, classified
            if is_undefined_table(exc):
                raise _not_provisioned(exc) from exc
            raise _unavailable(exc, STORAGE_READ_FAILED_MESSAGE) from exc
        _note_storage_success()
        counts = dict.fromkeys(RUN_AUTHORITY_STATES, 0)
        classified = 0
        for row in rows:
            rid = str(row[0] or "").strip()
            if not ws.is_record_id(rid) or rid in ws.CANONICAL_IDS:
                continue
            state_path = root / rid / "experiment.json"
            if state_path.exists():
                continue
            state = row[1]
            if isinstance(state, (str, bytes, bytearray)):
                state = json.loads(state)
            if not isinstance(state, dict) or state.get("id") != rid:
                # The row does not describe the record it is filed under. Skip it
                # rather than writing a directory named one thing holding another —
                # and COUNT the skip, because a row of this shape claims to be an
                # ordinary record of this scope and the list is about to be built
                # without it. Silently continuing here left the pass looking
                # complete, which is the whole defect this counter closes.
                skipped += 1
                continue
            if authoritative:
                # ── THE ONE LINE STAGE 2b ADDS TO THE RESTORE ────────────────────
                # `resolve_run_authority` returns the runs the rows prove, or
                # `None` meaning USE THE DOCUMENT. Three of the four states and
                # every mismatch return `None`, and that is NORMAL OPERATION — the
                # document is the side the compare-and-swap protects and the side a
                # scientist's last write landed in.
                authority, resolved = resolve_run_authority(
                    state,
                    projections.get(rid),
                    run_rows.get(rid, []),
                    tables_present=tables_present,
                )
                counts[authority] += 1
                classified += 1
                if resolved is not None:
                    # A SHALLOW COPY, so the row's parsed document is not mutated:
                    # `rows` is still being iterated and nothing else may observe a
                    # `runs` key this method substituted.
                    state = dict(state)
                    state["runs"] = resolved
            ws.atomic_write_text(state_path, json.dumps(state, indent=2) + "\n")
            restored += 1
        if classified:
            # ONLY A PASS THAT CLASSIFIED SOMETHING PUBLISHES A DISTRIBUTION. See
            # `_last_run_authority` for why an all-zero overwrite on every warm
            # list would destroy the one measurement that carries information.
            _record_run_authority(counts)
        if skipped:
            # AFTER the loop, deliberately: every restorable row has been restored
            # by now, so refusing one row costs only that row. See the docstring.
            raise HydrationSkippedRows(skipped)
        return restored


    def stored_experiments(self) -> tuple[list["ws.Experiment"], int]:
        """Every ordinary experiment the DATABASE holds, hydrated, and how many it
        could not read. READ ONLY.

        WHO THIS IS FOR, and it is one caller: ``scripts/db_backfill_runs.py``, the
        operator-run projection backfill. It exists here rather than in that script
        because this application's rule is that no SQL text lives outside a
        module-level ``Q_*`` constant in this package — a backfill that wrote its own
        ``SELECT`` would be the first exception, in the file least likely to be read
        again.

        IT IS NOT :meth:`hydrate`, and the difference is the point. ``hydrate`` writes
        workspace files and SKIPS any record whose file already exists, so it answers
        "what is missing locally". This answers "what does the database hold", which
        is the only question a completeness backfill can be driven by: an experiment
        whose workspace file is present is exactly the one ``hydrate`` would pass over
        and whose runs may never have been projected.

        THREE REFUSALS, AND THE THIRD WAS MISSING. A row whose id is not a
        well-formed record id, or is a canonical example id, is skipped — neither is
        an ordinary experiment this scope may hold, and nothing this application does
        can create either row. A row whose document does not describe the record it is
        filed under is skipped too. **And a row whose document cannot be HYDRATED is
        skipped**, which the first version of this method did not do while its
        docstring claimed it did.

        THAT OMISSION WAS MEASURED BY AN INDEPENDENT REVIEW, and it mattered because
        the docstring's reasoning was right and its claim was wrong.
        :meth:`ws.Experiment.from_state` uses hard subscripts — ``state["title"]``,
        ``state["created_utc"]`` — and ``int(state.get("rev") or 0)``, so
        ``{"id": "<a valid rid>"}`` raises ``KeyError`` and ``{"rev": "nope"}`` raises
        ``ValueError``. One such row aborted the whole enumeration, and every
        experiment after it went unprojected — verbatim the outcome the docstring said
        this method avoids.

        The rows are not hypothetical: they are exactly what an out-of-band
        ``INSERT`` produces, and this repository's own CI creates one
        (``INSERT INTO isaac_experiments (experiment_id, state) VALUES ('$parent',
        '{"id": "$parent"}')``). Out-of-band rows are the whole reason the earlier two
        guards exist.

        ALSO CORRECTED: this said "THE SAME TWO REFUSALS ``hydrate`` APPLIES".
        ``hydrate`` never calls ``from_state`` at all — it writes the document
        straight to disk — so this method has a raising surface ``hydrate`` does not,
        and describing them as the same set hid exactly the gap above.

        SKIPS ARE COUNTED AND RETURNED, never swallowed. The caller reports them, so a
        pass that could not read part of the table says so rather than looking
        complete — the same rule ``hydrate``'s own ``HydrationSkippedRows`` follows,
        without the raise, because here every remaining row is still projectable.

        NO SESSION SCOPE EXISTS HERE and none can. ``isaac_experiments`` has no
        ``session_id`` column, and :meth:`refuse_if_not_persistable` is what keeps a
        worked-example record out of it — so every row this returns is an ordinary
        experiment by construction.

        IT OPENS A ``write_transaction`` FOR A READ, and that is worth stating rather
        than leaving to inference. There is one transaction helper in this write path
        and it is where the statement policy and the per-transaction timeouts live, so
        a read that avoided it would be a read with no policy and no timeout. It
        issues exactly one ``SELECT``; the transaction commits empty.
        """
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                cursor.execute(policy.check(Q_ALL_EXPERIMENTS))
                rows = cursor.fetchall() or []
        except Exception as exc:  # noqa: BLE001 - classified exactly as `hydrate` does
            if is_undefined_table(exc):
                raise _not_provisioned(exc) from exc
            raise _unavailable(exc, STORAGE_READ_FAILED_MESSAGE) from exc
        _note_storage_success()
        out: list["ws.Experiment"] = []
        unreadable = 0
        for row in rows:
            rid = str(row[0] or "").strip()
            if not ws.is_record_id(rid) or rid in ws.CANONICAL_IDS:
                continue
            state = row[1]
            try:
                if isinstance(state, (str, bytes, bytearray)):
                    state = json.loads(state)
                if not isinstance(state, dict) or state.get("id") != rid:
                    unreadable += 1
                    continue
                out.append(ws.Experiment.from_state(state))
            except Exception:  # noqa: BLE001 - any unhydratable document, uniformly
                # DELIBERATELY BROAD, and the breadth is the point. `from_state`'s
                # failure modes are its own business and they change; what must not
                # change is that ONE bad row costs that row and not the pass. The
                # exception is not logged with the document, because the document is
                # what may carry scientific content — the count is what a report can
                # honestly carry.
                unreadable += 1
        return out, unreadable


# --- repositories -------------------------------------------------------------


class ExperimentRepository(Protocol):
    """What ``POST /api/experiments`` is allowed to know about persistence."""

    backend: str
    durable: bool

    def create(self, *, title: str, description: str | None) -> "ws.Experiment": ...

    def hydrate(self) -> int: ...


class _BaseRepository:
    """Creation is identical in both backends, and that is the point of the seam.

    A new experiment is minted, given a blank draft, and saved through the
    workspace layer. Whether that save ALSO writes through to a database is
    decided by :func:`ordinary_store`, not here — so the create path has exactly
    one implementation and cannot drift between backends.
    """

    backend = BACKEND_FILESYSTEM
    durable = False

    def create(self, *, title: str, description: str | None) -> "ws.Experiment":
        source = new_experiment_source()
        if description:
            source["description"] = description
        # NO `id=` ARGUMENT, EVER. `create_experiment` mints a fresh ULID when no
        # id is given; passing one through from a request body is the exact defect
        # `test_create_experiment_has_no_caller_in_the_api_package` was written to
        # make impossible to add silently. The route's request model forbids extra
        # fields, so a client cannot even name one — this is the second guard.
        # `session_id` is likewise never passed: the ordinary scope is the only
        # scope this repository addresses.
        return ws.create_experiment(title=title, source=source, draft=blank_draft())

    def hydrate(self) -> int:
        return 0


class FilesystemExperimentRepository(_BaseRepository):
    """Workspace directories only. EPHEMERAL on the deployed pod (``emptyDir``)."""

    backend = BACKEND_FILESYSTEM
    durable = False


class PostgresExperimentRepository(_BaseRepository):
    """Workspace directories, with the authoritative state mirrored to Postgres.

    DURABLE: a created experiment survives navigation, reload, a pod restart and
    a redeployment. See the module docstring for the one thing that does not
    survive (exported artifact FILES) and why that degrades safely.
    """

    backend = BACKEND_POSTGRES
    durable = True

    def __init__(self, store: PostgresOrdinaryStore) -> None:
        self.store = store

    def hydrate(self) -> int:
        return self.store.hydrate()


# --- selection ----------------------------------------------------------------
#
# Environment-driven and re-resolved on every call, deliberately. A cached module
# global would make the choice untestable without reaching into private state,
# and would freeze whichever environment happened to be present at import time —
# which, in a test suite that monkeypatches the environment per test, is the
# wrong one almost always.


def _postgres_available(env: Mapping[str, str]) -> bool:
    """Whether the durable backend is both configured AND correctly configured.

    ``PGHOST`` is the deployment's feature switch. ``PGDATABASE`` is then gated to
    the one expected name, exactly as the read paths gate it: a redirected or
    mistyped database must degrade to the filesystem rather than have this
    application create its tables somewhere unintended.

    Degrading is not silent. :func:`storage_status` reports ``configured: true``
    with ``backend: "filesystem"``, which is a distinguishable state, and the UI
    derives its durability sentence from that — so a misconfigured pod tells the
    reader their work is not durable instead of promising that it is.
    """
    if not database_configured(env):
        return False
    try:
        pgdatabase_gate(env)
    except WriteRefused:
        return False
    return True


def ordinary_store(env: Mapping[str, str] | None = None) -> PostgresOrdinaryStore | None:
    """The durable store for the ordinary scope, or ``None`` when there is none.

    This is what ``workspace`` calls (through a lazy import, so the two modules
    do not form an import cycle). ``None`` means "filesystem only", which is the
    answer on every developer machine and in CI's backend job.
    """
    env = os.environ if env is None else env
    return PostgresOrdinaryStore(env) if _postgres_available(env) else None


def repository(env: Mapping[str, str] | None = None) -> ExperimentRepository:
    """The active repository. The route calls this and asks nothing further."""
    env = os.environ if env is None else env
    store = ordinary_store(env)
    if store is None:
        return FilesystemExperimentRepository()
    return PostgresExperimentRepository(store)


def storage_status(env: Mapping[str, str] | None = None) -> dict:
    """The ``experiment_storage`` block on ``GET /api/health``.

    IT OPENS NOTHING. No connection, no query, no wait — the same discipline the
    adjacent ``database`` block keeps, and for the same reason: ``/health`` is the
    container readiness probe and a database problem must not be able to fail it.

    IT IS NO LONGER DERIVED FROM CONFIGURATION ALONE, AND THAT IS THE CORRECTION.
    It used to be, and the result was a pod reporting ``durable: true`` while every
    write against it failed, because "configured" and "working" are not the same
    claim and only one of them is what a reader hears. So this now also reads
    :func:`storage_failure` — a value RECORDED BY OTHER CODE PATHS that already
    tried, never a probe issued from here. Configuration says where experiments
    are meant to go; the observation says whether they are getting there.

    The three ``state`` values are documented at :data:`STORAGE_STATE_DURABLE` and
    friends. ``durable`` stays as the boolean it always was and stays consistent
    with ``state``, so an older client reading only the boolean is told the truth
    rather than being left on the optimistic branch.

    Both limits of the observation — it is process-local, and the first read after
    a process start is optimistic because nothing has been attempted — are stated
    in this module's docstring. Neither is hidden behind a reassuring value here.

    IT ALSO CARRIES THE STAGE-2b ``run_projection`` BLOCK, and the placement is a
    DELIBERATE DEPARTURE FROM WHAT THE CONTRACT ASKED FOR — reported rather than
    made quietly. `docs/isaac-runs-stage-2-contract.md` §7.6 says the distribution
    goes in ``/api/health``'s ``database`` block. That block's own comment in
    ``routes.py`` says it is about the read-only diagnostic over the
    PRODUCTION-DERIVED sample and that "conflating them would be the kind of error
    this file has made before", while ``experiment_storage`` is about where THIS
    APPLICATION'S OWN experiments are stored. The distribution is an aggregate over
    ``isaac_runs`` and ``isaac_run_projection``, which are this application's own
    tables — §7.6 says so itself, in the sentence that explains why gates G2 and G3
    are untouched by it — so it belongs in the second block, not the first. Moving
    it is a one-line change if the contract's author prefers the literal reading.

    ``authoritative`` IS CONFIGURATION AND ``last_pass`` IS AN OBSERVATION, kept
    apart for the reason the rest of this function keeps them apart. The first is
    the kill switch, read from the environment on every call so an operator's edit
    takes effect without a redeploy; the second is what the most recent classifying
    hydration pass measured, and it is ``None`` until one has run. Neither opens a
    connection.

    THE COUNTS ARE COUNTS. No id, no title, no record content, nothing derived from
    a scientific value. And nothing here may ever be read as "the cutover is
    complete": until an operator applies `0005` the honest distribution is every
    experiment ``unavailable``, and between `0005` and the backfill it is every
    experiment ``never_projected``. Both are the reader working correctly.
    """
    env = os.environ if env is None else env
    configured = database_configured(env)
    selected = _postgres_available(env)
    failure = storage_failure()
    durable = selected and failure is None
    if durable:
        state = STORAGE_STATE_DURABLE
    elif configured:
        # A database IS wired up and experiments are not going into it — because
        # the PGDATABASE gate refused it, or because it stopped answering. Both
        # are "configured but not storing", which is one state to a reader even
        # though it is two causes to an operator.
        state = STORAGE_STATE_UNAVAILABLE
    else:
        state = STORAGE_STATE_EPHEMERAL
    return {
        # `backend` REPORTS WHAT IS SELECTED, NOT WHETHER IT IS WORKING, and those
        # came apart the moment a failure could be observed. A pod whose database
        # has stopped answering still HAS the Postgres repository selected — it
        # keeps trying, which is what lets it recover — so reporting
        # `backend: "filesystem"` there would describe a fallback the app is not
        # performing. `durable` and `state` are where "is it working" is answered.
        "configured": configured,
        "backend": BACKEND_POSTGRES if selected else BACKEND_FILESYSTEM,
        "durable": durable,
        "state": state,
        "run_projection": {
            "authoritative": run_rows_authoritative(env),
            "last_pass": run_authority_summary(),
        },
    }
