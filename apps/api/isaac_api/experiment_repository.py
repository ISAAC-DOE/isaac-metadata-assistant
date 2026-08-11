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

* **THE LIST DEGRADES.** Hydration is an optimisation — it restores directories a
  restart threw away. A failed hydration falls back to the filesystem view and
  ``GET /api/experiments`` continues, so a list stays a list. A short list is
  INCOMPLETE; it never asserts that the rows it omits do not exist.
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
    "SQLSTATE_UNDEFINED_TABLE",
    "STORAGE_READ_FAILED_MESSAGE",
    "STORAGE_STATE_DURABLE",
    "STORAGE_STATE_EPHEMERAL",
    "STORAGE_STATE_UNAVAILABLE",
    "STORAGE_WRITE_FAILED_MESSAGE",
    "DurableWriteConflict",
    "ExperimentRepository",
    "FilesystemExperimentRepository",
    "NotPersistable",
    "PostgresExperimentRepository",
    "PostgresOrdinaryStore",
    "StorageNotProvisioned",
    "StorageUnavailable",
    "blank_draft",
    "forget_storage_failure",
    "is_undefined_table",
    "ordinary_store",
    "repository",
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
    capture surface in this build, so a new experiment cannot yet be completed to
    the point of export. That is a real limit of the product, not of this
    function, and inventing a pending entry for a question nothing can answer
    would make the Guided Completion screen list dead ends.
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

    def persist(self, exp: "ws.Experiment") -> None:
        """COMPARE-AND-SWAP one ordinary-scope experiment's authoritative state.

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
        """
        self.refuse_if_not_persistable(exp)
        payload = json.dumps(exp.to_state(), sort_keys=True)
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                cursor.execute(policy.check(Q_UPSERT_EXPERIMENT), (exp.id, payload))
                # A conflict action whose WHERE is false updates nothing and
                # raises nothing. `rowcount` over `RETURNING` is what makes that
                # silence observable.
                accepted = cursor.rowcount == 1
                stored = None
                if not accepted:
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

        It writes ONLY into ``workspace_root()``. The tutorial namespace is never
        addressed: there is no session id anywhere in this method, and a stored
        row can never carry one (``persist`` refuses it). A row whose id is not a
        well-formed record id, or is a canonical example id, is skipped rather
        than written — the same fail-closed reading the rest of the workspace
        layer applies to anything it did not just create itself.

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
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                cursor.execute(policy.check(Q_ALL_EXPERIMENTS))
                rows = cursor.fetchall() or []
        except Exception as exc:  # noqa: BLE001 - any driver/server failure, classified
            if is_undefined_table(exc):
                raise _not_provisioned(exc) from exc
            raise _unavailable(exc, STORAGE_READ_FAILED_MESSAGE) from exc
        _note_storage_success()
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
                # rather than writing a directory named one thing holding another.
                continue
            ws.atomic_write_text(state_path, json.dumps(state, indent=2) + "\n")
            restored += 1
        return restored


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
    }
