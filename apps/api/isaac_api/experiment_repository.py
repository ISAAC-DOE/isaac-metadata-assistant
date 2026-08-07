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
This is the state the deployed pod is in RIGHT NOW, and it is why this section
exists rather than being left to "it will be fine". ``PGHOST`` and ``PGDATABASE``
are already set in the pod, so the durable backend selects itself on the next
image roll — and the migration is deliberately NOT applied at boot, so
``isaac_experiments`` does not exist. Every statement against it raises.

Before this was handled, that turned three previously database-free operations
into unhandled 500s: ``GET /api/experiments`` (My Experiments rendered "Backend
Not Running"), ``GET /api/experiments/<id>`` (a clean 404 became a 500) and
``POST /api/experiments``. The same three 500s would have come back on any
transient outage, permanently — a read path that had never touched a database
had acquired a hard dependency on one.

THE RULE THAT REPLACES IT, and the two halves are deliberately different:

* **READS DEGRADE.** Hydration is an optimisation — it restores directories a
  restart threw away. A failed hydration therefore falls back to the filesystem
  view and the read continues, so a list stays a list and a miss stays a 404.
* **WRITES DO NOT.** A failed durable write raises :class:`StorageUnavailable`,
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
    "STORAGE_STATE_DURABLE",
    "STORAGE_STATE_EPHEMERAL",
    "STORAGE_STATE_UNAVAILABLE",
    "ExperimentRepository",
    "FilesystemExperimentRepository",
    "NotPersistable",
    "PostgresExperimentRepository",
    "PostgresOrdinaryStore",
    "StorageUnavailable",
    "blank_draft",
    "forget_storage_failure",
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


def _unavailable(exc: BaseException) -> StorageUnavailable:
    """Record ``exc`` and build the fixed, path-free error the caller should raise."""
    _note_storage_failure(exc)
    return StorageUnavailable(
        "This deployment stores experiments in its own database, and that "
        "database did not accept the write. Nothing was saved."
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

Q_UPSERT_EXPERIMENT = (
    "INSERT INTO isaac_experiments (experiment_id, state) VALUES (%s, %s::jsonb)"
    " ON CONFLICT (experiment_id) DO UPDATE"
    " SET state = EXCLUDED.state, updated_utc = now()"
)

Q_ALL_EXPERIMENTS = (
    "SELECT experiment_id, state FROM isaac_experiments"
    " ORDER BY created_utc, experiment_id"
)


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
        """Upsert one ordinary-scope experiment's authoritative state.

        RAISES :class:`StorageUnavailable` if the database does not take the write,
        and deliberately does NOT fall back to the filesystem. The caller
        (``workspace.Experiment.save``) has already been told, through
        ``storage_status``, that this deployment stores experiments durably; a
        quiet ephemeral write would withdraw that promise without saying so, and
        the reader would only discover it at the next pod restart. Failing here
        means the workspace file is not rewritten either, so the record is not left
        looking saved.

        The isolation refusal is raised OUTSIDE the try, and that ordering is
        load-bearing: :class:`NotPersistable` is a permanent property of the
        record, not an outage, and must never be reported as one or recorded as a
        storage failure.
        """
        self.refuse_if_not_persistable(exp)
        payload = json.dumps(exp.to_state(), sort_keys=True)
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                cursor.execute(policy.check(Q_UPSERT_EXPERIMENT), (exp.id, payload))
        except Exception as exc:  # noqa: BLE001 - any driver/server failure, uniformly
            raise _unavailable(exc) from exc
        _note_storage_success()

    # -- restore ---------------------------------------------------------------

    def hydrate(self) -> int:
        """Write back any stored experiment whose workspace directory is missing.

        Returns how many were restored — a MEASURED count of directories this
        call created, not the row count.

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
        """
        root = ws.workspace_root()
        restored = 0
        try:
            with write_transaction(self.env, **self._connect_kwargs) as (cursor, policy):
                cursor.execute(policy.check(Q_ALL_EXPERIMENTS))
                rows = cursor.fetchall() or []
        except Exception as exc:  # noqa: BLE001 - any driver/server failure, uniformly
            raise _unavailable(exc) from exc
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
