"""Read-only record source for the record-verification engine.

WHAT THIS IS
============
A generator that hands the verification engine one parsed record at a time from
the application's own datastore, and nothing else. It is the narrowest thing that
can satisfy Q19 (``authorization.py``): read, aggregate, discard.

It is NOT a repository, NOT an adapter, and NOT a read path for display. It
cannot fetch a record by id, cannot filter, cannot page on a caller's behalf and
cannot be handed a query. The public surface is
:meth:`DatastoreRecordProvider.records`, which takes no arguments at all.

WHERE THE PATTERNS COME FROM
============================
``db_recon.py`` already established connection discipline, masking and
fail-closed envelopes for this deployment, and this module reuses them rather
than inventing a second set:

* :func:`db_recon.check_env_gates` is the environment gate (PGDATABASE pinned).
* The libpq connection is opened the same way, with the driver imported LAZILY,
  the database name pinned from a constant rather than from the environment, and
  only the exception *class* reported — psycopg2 messages echo the host, the user
  and the connection string.
* Statement classification and counting follow ``db_recon.StatementAudit``: the
  counts are an OBSERVATION of what reached a cursor, never an assertion the
  report makes about itself.

The one deliberate divergence is ``application_name``: this connection is labelled
:data:`APPLICATION_NAME` so a session opened by verification is distinguishable
from a reconnaissance session in the server's own view.

HOW EACH OWNER CONSTRAINT IS DISCHARGED
=======================================
``authorization.DATASTORE_CONSTRAINTS`` is the list, in the owner's words. Here
is where each one lives, so a reviewer diffs intent against code instead of
reading both and hoping:

===============================================  =====================================
Constraint                                       Discharged by
===============================================  =====================================
one short-lived connection per run                :meth:`DatastoreRecordProvider._drain`
                                                  opens exactly one, fetches the bounded
                                                  page, and closes it BEFORE the first
                                                  record is yielded; nothing else in
                                                  this module connects
explicit transaction, read-only declared twice    ``set_session(readonly=True)`` then
                                                  :data:`Q_SET_TRANSACTION_READ_ONLY`
read-only VERIFIED server-side                    :func:`verify_transaction_read_only`
conservative timeouts, SET LOCAL                  :data:`Q_SET_STATEMENT_TIMEOUT`,
                                                  :data:`Q_SET_LOCK_TIMEOUT`
deterministic rollback + close, no autocommit     the ``finally`` block; and
                                                  :func:`_refuse_autocommit`
frozen statements, parameterized values           :data:`FROZEN_STATEMENTS` and
                                                  :class:`StatementPolicy`
narrow query-policy guard                         :class:`StatementPolicy`
callers supply nothing                            :meth:`records` takes no arguments
CHAR(26) padding stripped, identifier dropped     :func:`parse_row`
one PARSED record at a time; the whole parsed    the generator in :meth:`records`;
corpus is never retained                          the bounded raw page IS held --
                                                  see "ONE-AT-A-TIME CLAIM" below
dangling cross-references tolerated               nothing in this module reads
                                                  ``links``; see the note below
lazy driver import, safe ``unavailable``          :func:`connect_psycopg2`
===============================================  =====================================

THE ONE-AT-A-TIME CLAIM, STATED AT ITS TRUE STRENGTH
====================================================
This module materializes exactly one PARSED record as a Python object at a time.
That is the claim it makes and the claim its tests check.

It is NOT a claim about the raw rows, and it never could have been. psycopg2's
default client-side cursor buffers the whole result set inside libpq before the
first ``fetchone`` returns, so the page is in this process's memory either way.
An earlier version yielded from inside the open transaction in the belief that
this bought a streaming property; it bought none, and it cost a ~21 minute
idle-in-transaction session at the row ceiling (see :meth:`records`). The rows
are therefore drained and the connection closed BEFORE the first yield, and the
drained list shrinks as it is parsed.

A named (server-side) cursor would make the raw fetch genuinely streaming, and is
deliberately not used: it would put the transaction back around the whole sweep,
which is the thing being fixed. Do not restate this module's guarantee as "the
result set is never in memory" — it is "the parsed corpus is never in memory, and
the transaction is not held across the sweep".

DANGLING CROSS-REFERENCES
=========================
Records reference other records, and the referenced row may not be in the sample
— that is EXPECTED, not corruption. The tolerance here is implemented as
absence: this module never inspects ``links``, never issues a second query, never
resolves a reference and never counts one. A dangling reference is therefore
invisible to it, which is the strongest possible form of "never repair, follow,
or report".

NOTHING PER-RECORD LEAVES
=========================
The identifier is read (Postgres blank-pads ``CHAR(26)``, so it must be stripped
before anything compares it) and then dropped inside :func:`parse_row`. It is
never stored on the provider, never logged, never counted into a key, and never
yielded. Everything downstream of this module sees a record body and no name for
it.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

from . import db_recon
from .authorization import (
    AUTHORIZED_PRIVATE_SAMPLE_MODE,
    Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED,
)

__all__ = [
    "APPLICATION_NAME",
    "FROZEN_STATEMENTS",
    "DatastoreRecordProvider",
    "PolicyViolation",
    "ProviderRefusal",
    "ProviderUnavailable",
    "STATE_ERROR",
    "STATE_NOT_RUN",
    "STATE_OK",
    "STATE_REFUSED",
    "STATE_TIMEOUT",
    "STATE_UNAVAILABLE",
    "StatementPolicy",
    "classify_statement",
    "connect_psycopg2",
    "normalize_identifier",
    "parse_row",
    "verify_transaction_read_only",
]


#: How this connection identifies itself in ``pg_stat_activity``. Distinct from
#: ``db_recon``'s so the two read paths are separable in the server's own view.
APPLICATION_NAME = "isaac_verification_reader"

#: Hard ceiling on rows fetched in one run. The seeded table is documented at 30
#: rows; this is generous enough to cover growth and small enough that a
#: surprise-huge table cannot be paged into pod memory.
#:
#: WHAT IT BOUNDS, stated exactly, because an earlier version of this comment
#: overclaimed. It bounds the RAW ROWS this module holds — which, with
#: psycopg2's default client-side cursor, is the same set libpq has already
#: buffered, so the cap is not adding a second copy. It does NOT bound anything
#: a consumer derives from those rows: ``verification`` builds ~755 mutation
#: trials per record, and bounding that is the consumer's job (it now aggregates
#: incrementally instead of retaining them).
MAX_RECORDS_CEILING = 500

#: Default page size when a caller does not name one.
DEFAULT_MAX_RECORDS = MAX_RECORDS_CEILING


# --------------------------------------------------------------------------
# States and refusals
# --------------------------------------------------------------------------

STATE_NOT_RUN = "not_run"
STATE_OK = "ok"
STATE_UNAVAILABLE = "unavailable"
STATE_TIMEOUT = "timeout"
STATE_REFUSED = "refused"
STATE_ERROR = "error"

#: Every state :attr:`DatastoreRecordProvider.state` may hold. Closed, so a
#: caller can switch on it exhaustively and so no driver text can become a state.
PROVIDER_STATES: tuple[str, ...] = (
    STATE_NOT_RUN,
    STATE_OK,
    STATE_UNAVAILABLE,
    STATE_TIMEOUT,
    STATE_REFUSED,
    STATE_ERROR,
)


class ProviderRefusal(Exception):
    """A fail-closed gate refused. Names the gate; carries no value and no row.

    The reason strings in this module are authored constants or SQL keywords.
    Nothing derived from a row, a credential or a driver message is ever passed
    to one — ``db_recon``'s ``ReconRefusal`` has the same rule, for the same
    reason: the natural caller of an error constructor is ``str(exc)``.
    """

    state = STATE_REFUSED

    def __init__(self, gate: str, reason: str) -> None:
        super().__init__(f"gate={gate}: {reason}")
        self.gate = gate
        self.reason = reason


class PolicyViolation(ProviderRefusal):
    """A statement failed the query policy and never reached a socket."""

    def __init__(self, reason: str) -> None:
        super().__init__("query_policy", reason)


class ReadOnlyNotVerified(ProviderRefusal):
    """The server did not confirm ``transaction_read_only`` as ``on``."""

    def __init__(self, reason: str) -> None:
        super().__init__("transaction_read_only", reason)


class NotAuthorized(ProviderRefusal):
    """The Q19 flag in ``authorization.py`` is not set."""

    def __init__(self, reason: str) -> None:
        super().__init__("authorization", reason)


class ProviderUnavailable(Exception):
    """The source could not be reached. Not a refusal — nothing was refused."""

    state = STATE_UNAVAILABLE

    def __init__(self, gate: str, reason: str) -> None:
        super().__init__(f"gate={gate}: {reason}")
        self.gate = gate
        self.reason = reason


#: Exception CLASS names that mean "the server cancelled us", as opposed to "we
#: could not reach the server". Matched on the name because psycopg2 is imported
#: lazily and may be absent entirely, so the class objects cannot be referenced
#: here. ``QueryCanceledError`` is what psycopg2 raises on ``statement_timeout``
#: and on ``lock_timeout``.
TIMEOUT_EXCEPTION_NAMES: frozenset[str] = frozenset(
    {"QueryCanceledError", "LockNotAvailable", "TimeoutError"}
)


# --------------------------------------------------------------------------
# The frozen statement set
# --------------------------------------------------------------------------
#
# Five statements, all module-level literals. The ONLY thing that varies between
# runs is the LIMIT, and it travels as a bound parameter. There is no template,
# no ``.format``, no f-string and no identifier interpolation anywhere in this
# module — ``db_recon`` needs ``_quote_ident`` because it groups by a column name
# it discovered in the catalog; this module discovers nothing.

#: Declares the transaction read-only on the server. Must be the first statement
#: of the transaction.
Q_SET_TRANSACTION_READ_ONLY = "SET TRANSACTION READ ONLY"

#: Conservative statement timeout. ``SET LOCAL`` so it dies with the transaction
#: and cannot leak into a pooled session.
Q_SET_STATEMENT_TIMEOUT = "SET LOCAL statement_timeout = '15000ms'"

#: Conservative lock timeout. A read should never wait on a lock at all; three
#: seconds is a bound, not a budget.
Q_SET_LOCK_TIMEOUT = "SET LOCAL lock_timeout = '3000ms'"

#: The server-side read-back. This is what turns "we asked for read-only" into
#: "the server says the transaction is read-only".
Q_SHOW_TRANSACTION_READ_ONLY = "SHOW transaction_read_only"

#: The one statement that touches record rows. ``record_id`` is selected so the
#: ordering is over a column this statement names (deterministic paging), and it
#: is discarded by :func:`parse_row` in the same breath — see the module
#: docstring. ``data`` is the record body. Nothing else is read: no title, no
#: owner, no timestamps, no type, no domain.
Q_RECORD_PAGE = "SELECT record_id, data FROM records ORDER BY record_id LIMIT %s"

#: The statements that change session/transaction state. Each makes the session
#: strictly MORE restrictive; none can write.
SESSION_STATEMENTS: tuple[str, ...] = (
    Q_SET_TRANSACTION_READ_ONLY,
    Q_SET_STATEMENT_TIMEOUT,
    Q_SET_LOCK_TIMEOUT,
)

#: The statements that read.
READ_STATEMENTS: tuple[str, ...] = (
    Q_SHOW_TRANSACTION_READ_ONLY,
    Q_RECORD_PAGE,
)

#: THE frozen set. A statement not identical to a member of this tuple is
#: refused by :class:`StatementPolicy` before it reaches a cursor. Identity, not
#: a pattern: a pattern is something a future edit can widen by accident.
FROZEN_STATEMENTS: tuple[str, ...] = SESSION_STATEMENTS + READ_STATEMENTS


# --------------------------------------------------------------------------
# The query policy
# --------------------------------------------------------------------------

#: Statement-initial keywords that WRITE data.
_DML_LEADING = ("insert", "update", "delete", "merge", "truncate", "copy")
#: Statement-initial keywords that change SCHEMA or privileges.
_DDL_LEADING = ("create", "alter", "drop", "grant", "revoke", "comment", "refresh")
#: Statement-initial keywords the policy is willing to classify as a read.
_READ_LEADING = ("select", "with", "show")

#: Word tokens forbidden ANYWHERE in a statement. This is belt-and-braces over
#: the frozen-set check: the frozen set already excludes everything here, so the
#: only way a token search can fire is on a statement that was going to be
#: refused anyway — but it fires with a SPECIFIC reason and, crucially, it fires
#: *after* classification, so an attempted write is COUNTED as a write.
#:
#: ``\b`` boundaries mean ``created_at``, ``updated_at`` and ``record_history``
#: do not false-positive: the character following the keyword is a word
#: character, so there is no boundary.
_FORBIDDEN_TOKENS: tuple[str, ...] = (
    # writes
    "insert", "update", "delete", "merge", "truncate", "copy", "call", "do",
    # schema and privileges
    "create", "alter", "drop", "grant", "revoke", "comment", "refresh",
    # temp tables and their relatives
    "temp", "temporary", "unlogged",
    # sequences
    "nextval", "setval", "currval", "lastval",
    # transaction and session control this module does not perform
    "begin", "start", "commit", "rollback", "savepoint", "release",
    "prepare", "execute", "deallocate", "discard", "reset",
    # server-side side effects
    "vacuum", "reindex", "cluster", "listen", "notify", "unlisten",
    "checkpoint", "load", "lo_import", "lo_export", "pg_read_file",
    "pg_read_binary_file", "pg_terminate_backend", "pg_cancel_backend",
    "dblink", "into",
)
_FORBIDDEN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(token) for token in _FORBIDDEN_TOKENS) + r")\b"
)


def _normalise_sql(sql: str) -> str:
    """Lowercase, strip comments, collapse whitespace, drop one trailing ';'.

    Identical in behaviour to ``db_recon._normalise_sql``. Kept as its own
    function rather than imported so that a future change to the reconnaissance
    guard cannot silently change what this policy considers a statement.
    """
    text = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    if text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def classify_statement(sql: Any) -> str:
    """Classify as ``session`` / ``read`` / ``dml`` / ``ddl`` / ``other``.

    Classification is what makes ``dml_statements: 0`` a MEASUREMENT. A write
    that this module never issues is counted as zero because zero were seen, and
    a write that a future bug constructs is counted as one *and then refused* —
    the count is taken before the refusal, deliberately, so a blocked attempt is
    visible rather than erased.
    """
    if isinstance(sql, str) and sql in FROZEN_STATEMENTS:
        return "session" if sql in SESSION_STATEMENTS else "read"
    text = _normalise_sql(sql if isinstance(sql, str) else str(sql))
    if not text:
        return "other"
    if text.startswith(_DML_LEADING):
        return "dml"
    if text.startswith(_DDL_LEADING):
        return "ddl"
    if text.startswith(_READ_LEADING):
        return "read"
    return "other"


class StatementPolicy:
    """Counts every statement offered, and refuses everything off the frozen set.

    Counting happens FIRST and unconditionally, so ``dml``/``ddl`` report what
    was *attempted*, not what was permitted. A policy that only counted what it
    allowed would report zero writes in exactly the scenario where the number
    matters.

    **WHICH counter moves is a weaker guarantee than the refusal, and the
    difference must not be overstated.** :func:`classify_statement` reads the
    statement-initial keyword, so it sees a bare ``DELETE`` as ``dml``, but a
    write hidden behind a CTE (``WITH x AS (DELETE ...) SELECT ...``) or a
    lock-taking read (``SELECT ... FOR UPDATE``) leads with ``with``/``select``
    and is classified ``read`` — ``dml_statements`` stays 0 for those.

    Every one of them is still REFUSED, by the forbidden-token search and then
    by the frozen-set check, and :attr:`refusals` moves in every case. So the
    reliable statement is: *nothing outside the frozen set executes, and
    ``refusals`` counts every attempt*. ``dml_statements`` is the narrower
    signal — attempts whose leading keyword is a write — and the served report
    is right to publish both it and, through
    :attr:`parameterized_only`, whether any refusal happened at all.

    ``parameterized_only`` is a real observation too: the only statement that
    carries a value is :data:`Q_RECORD_PAGE`, and it is a frozen literal whose
    value arrives as a bound parameter. If a statement ever executes carrying a
    value that is not a bound parameter, it cannot be a member of the frozen set,
    so it is refused and :attr:`refusals` is nonzero.
    """

    __slots__ = ("counts", "refusals", "executed", "parameterized_executions")

    def __init__(self) -> None:
        self.counts: dict[str, int] = {
            "session": 0,
            "read": 0,
            "dml": 0,
            "ddl": 0,
            "other": 0,
        }
        self.refusals = 0
        self.executed = 0
        self.parameterized_executions = 0

    # -- observation ------------------------------------------------------

    @property
    def dml_statements(self) -> int:
        return self.counts["dml"]

    @property
    def ddl_statements(self) -> int:
        return self.counts["ddl"]

    @property
    def parameterized_only(self) -> bool:
        """True when every statement executed was a frozen literal.

        ``executed > 0`` is part of the condition on purpose: a run that issued
        no statement at all has not demonstrated anything, and reporting it as
        "parameterized queries only: verified" would be a claim about an event
        that never happened.
        """
        return self.executed > 0 and self.refusals == 0

    # -- enforcement ------------------------------------------------------

    def check(self, sql: Any, params: Any = None) -> str:
        """Classify, count, then refuse unless ``sql`` is a frozen literal.

        Returns the statement so call sites read ``cursor.execute(policy.check(Q), p)``
        and cannot forget the guard.
        """
        kind = classify_statement(sql)
        self.counts[kind] += 1

        if not isinstance(sql, str) or not sql.strip():
            self.refusals += 1
            raise PolicyViolation("empty or non-string statement")

        text = _normalise_sql(sql)
        if ";" in text:
            self.refusals += 1
            raise PolicyViolation("statement chaining with ';' is not allowed")

        hit = _FORBIDDEN_RE.search(text)
        if hit:
            # The token is a SQL keyword, never data, so naming it is safe and
            # is what makes the refusal actionable.
            self.refusals += 1
            raise PolicyViolation(f"forbidden token {hit.group(0)!r} in statement")

        if sql not in FROZEN_STATEMENTS:
            self.refusals += 1
            raise PolicyViolation("statement is not in the frozen statement set")

        if params is not None and not isinstance(params, (tuple, list)):
            self.refusals += 1
            raise PolicyViolation("parameters must be a bound sequence")

        self.executed += 1
        if params is not None:
            self.parameterized_executions += 1
        return sql


# --------------------------------------------------------------------------
# Row handling
# --------------------------------------------------------------------------


def normalize_identifier(value: Any) -> str:
    """Strip the blank padding Postgres adds to a ``CHAR(26)`` column.

    ``docs/postgres-test-db-guide.md`` ("Gotchas to code around") documents the
    padding. It is stripped here so that no comparison anywhere downstream is
    made against a 26-character string with trailing spaces — and then the
    result is discarded by :func:`parse_row`, which is the only caller.
    """
    return str(value or "").strip()


def parse_row(row: Sequence[Any]) -> Optional[dict]:
    """Turn ``(record_id, data)`` into a record body, DROPPING the identifier.

    Returns ``None`` for a row whose payload will not parse into an object. A
    bad row degrades the sample; it must not delete the report. Nothing about
    which row it was is retained.

    The identifier is normalized and then goes out of scope without being
    returned, stored or logged. That is the whole reason this is a function
    rather than three lines inline: the drop is testable.
    """
    if not isinstance(row, (tuple, list)) or len(row) < 2:
        return None

    # Read, normalize, and let it fall out of scope. Never returned.
    identifier = normalize_identifier(row[0])
    del identifier

    payload = row[1]
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if not isinstance(payload, dict):
        return None
    return payload


# --------------------------------------------------------------------------
# Session gates
# --------------------------------------------------------------------------


def verify_transaction_read_only(cursor: Any, policy: StatementPolicy) -> str:
    """Ask the SERVER whether the transaction is read-only, and refuse if not.

    This is the constraint the owner stated as "server-side verification", and it
    is the difference between a safeguard and a comment. ``set_session`` can be
    absent, silently ignored by a proxy, or overridden by a pooler; the only
    evidence that survives all three is the server's own answer.

    Anything other than ``on`` — including an empty result, a ``None``, an empty
    row, or an unexpected word — refuses. Fail-closed includes failing closed on
    "I do not understand the answer".

    NORMALIZATION IS DELIBERATE AND IS NOT GUESSING. The value is compared after
    ``.strip().lower()``, so ``" ON "`` is accepted. Postgres answers this
    setting with lowercase ``on``/``off``; tolerating surrounding whitespace and
    case reads the answer the server gave rather than inventing one, and it
    costs nothing because the accepted set is the single token ``on``. Anything
    that is not that token after normalization refuses — there is no
    "truthy-looking" branch, so ``t``, ``true``, ``yes`` and ``1`` all refuse.
    """
    cursor.execute(policy.check(Q_SHOW_TRANSACTION_READ_ONLY))
    rows = cursor.fetchone()
    if rows is None:
        raise ReadOnlyNotVerified("server returned no row for the read-only setting")
    if isinstance(rows, (tuple, list)) and len(rows) < 1:
        # An empty row. Indexing it would raise `IndexError` into the caller's
        # generic handler and be reported as an anonymous `unexpected` error,
        # losing the one thing worth knowing: which gate was not satisfied.
        raise ReadOnlyNotVerified("server returned an empty row for the read-only setting")
    value = rows[0] if isinstance(rows, (tuple, list)) else rows
    text = str(value or "").strip().lower()
    if text != "on":
        # The value is a server setting, not data — safe to name, and naming it
        # is what makes the refusal diagnosable.
        raise ReadOnlyNotVerified(
            f"server reports transaction_read_only={text!r}, refusing to proceed"
        )
    return text


def _refuse_autocommit(connection: Any) -> None:
    """Refuse a connection already in autocommit.

    There is no autocommit path in this module — it never sets the attribute. But
    a caller could hand in a connection that has it set, and then ``SET LOCAL``
    would apply to a one-statement transaction and expire immediately, and the
    rollback in ``finally`` would roll back nothing. The guarantee would quietly
    become decorative, which is worse than absent.
    """
    if bool(getattr(connection, "autocommit", False)):
        raise ProviderRefusal(
            "autocommit", "refusing a connection in autocommit; this run needs a "
            "transaction it can roll back"
        )


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------


def connect_psycopg2(env: Mapping[str, str]) -> Any:
    """Open a TLS connection from libpq env vars. The driver is imported LAZILY.

    Lazy for the reason ``db_recon.connect_psycopg2`` is lazy: importing this
    module — and running its whole test suite — must never depend on the driver
    being installed. The deployed image installs the ``api`` extra and has
    ``psycopg2-binary``; a bare developer checkout may not, and in that case the
    run reports :data:`STATE_UNAVAILABLE` rather than failing to import.

    The database name comes from the constant, never from the environment: the
    environment gate has already pinned it, and reading it twice from a mutable
    source is how the two copies diverge.
    """
    try:
        import psycopg2  # noqa: PLC0415 - intentionally lazy; see docstring
    except ImportError:
        raise ProviderUnavailable(
            "driver",
            "psycopg2 is not importable in this interpreter; install the 'api' "
            "extra (pip install -e '.[api]')",
        )

    missing = [
        name for name in ("PGHOST", "PGUSER", "PGPASSWORD") if not (env.get(name) or "")
    ]
    if missing:
        raise ProviderUnavailable(
            "connect",
            "missing required libpq environment variables: " + ", ".join(sorted(missing)),
        )

    try:
        return psycopg2.connect(
            host=env["PGHOST"],
            port=env.get("PGPORT", "5432"),
            dbname=db_recon.EXPECTED_DATABASE,
            user=env["PGUSER"],
            password=env["PGPASSWORD"],
            sslmode=env.get("PGSSLMODE", "require"),
            connect_timeout=int(env.get("PGCONNECT_TIMEOUT", "10")),
            application_name=APPLICATION_NAME,
        )
    except Exception as exc:  # noqa: BLE001
        # Only the exception CLASS is reported. psycopg2's messages echo the
        # host, the user and the connection string.
        raise ProviderUnavailable("connect", f"could not connect ({type(exc).__name__})")


# --------------------------------------------------------------------------
# The provider
# --------------------------------------------------------------------------


class DatastoreRecordProvider:
    """Yields record bodies from the datastore, one at a time, then forgets them.

    Usage is deliberately awkward to misuse::

        provider = DatastoreRecordProvider(os.environ)
        for record in provider.records():
            ...
        provider.state          # "ok" | "unavailable" | "timeout" | "refused" | "error"

    The outcome is read AFTER iteration, from attributes, because a generator
    cannot return one. Every attribute is a scalar or a state word from a closed
    set; none is derived from a row.
    """

    #: The verification mode this provider serves. A provider that served a
    #: different mode would be a second authorization question.
    mode = AUTHORIZED_PRIVATE_SAMPLE_MODE

    def __init__(
        self,
        env: Mapping[str, str],
        *,
        connect: Callable[[Mapping[str, str]], Any] | None = None,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> None:
        # A mapping of environment variables, not a connection string and not a
        # DSN. There is no parameter here for SQL, a table, a schema, an
        # identifier, a pointer or a path, and there is deliberately no way to
        # add one without changing this signature.
        self._env = dict(env)
        self._connect = connect or connect_psycopg2
        self._max_records = max(1, min(int(max_records), MAX_RECORDS_CEILING))

        self.policy = StatementPolicy()
        self.state: str = STATE_NOT_RUN
        self.refusal_gate: str | None = None
        self.read_only_verified = False
        self.records_yielded = 0
        self.rows_unreadable = 0
        self.connections_opened = 0
        #: Drained rows not yet parsed. An integer only — it exists so the
        #: one-parsed-record-at-a-time property is measurable from outside.
        self.rows_remaining = 0

    # -- measurements ------------------------------------------------------

    @property
    def dml_statements(self) -> int:
        return self.policy.dml_statements

    @property
    def ddl_statements(self) -> int:
        return self.policy.ddl_statements

    @property
    def parameterized_only(self) -> bool:
        return self.policy.parameterized_only

    # -- the one public operation -----------------------------------------

    def records(self) -> Iterator[dict]:
        """Yield one parsed record body at a time. Takes no arguments.

        TWO PHASES, AND THE SPLIT IS THE POINT
        ======================================
        1. :meth:`_drain` opens exactly one connection, runs the gates, fetches
           the bounded page, and **rolls back and closes before returning**.
        2. This generator then parses and yields one record at a time, dropping
           each raw row as it goes.

        The transaction is therefore open only for the fetch, not for the sweep.
        That is a correction of a real defect. The previous version yielded from
        inside the open transaction, and the consumer — ``verification._sweep``
        — runs a full official validation, a format shadow and a 755-operator
        mutation harness *between* successive rows, measured at 2.56 s/record.
        At the shipped ceiling of 500 rows that was a ~21 minute
        idle-in-transaction session against a database whose connection limit is
        5, pinning a snapshot and blocking VACUUM the whole time, while
        ``DATASTORE_CONSTRAINTS[0]`` called it "short-lived".

        Nothing is lost by draining, because nothing was being streamed: with
        psycopg2's default client-side cursor libpq has already buffered every
        row before the first ``fetchone`` returns. Holding the transaction open
        across the sweep bought no memory property whatsoever — it only bought
        the lock.

        What "one at a time" now means, precisely: the raw rows are held (bounded
        by :data:`MAX_RECORDS_CEILING`, and identical to what the driver had
        buffered anyway), and exactly one *parsed record* exists at a time, each
        raw row being released as it is parsed.
        """
        self._reset()

        if not Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED:
            # Belt-and-braces. `verification.VERIFICATION_MODES` would not offer
            # this mode at all, so nothing should reach here — but a provider
            # that connected because someone constructed it directly would make
            # the flag advisory rather than binding.
            self._fail(
                NotAuthorized("aggregate datastore verification is not approved")
            )
            return

        rows = self._drain()
        if rows is None:
            # `_drain` has already set `state` and `refusal_gate`.
            return

        # Reversed once so `pop()` is O(1) and still yields ascending record_id
        # order. The list shrinks as it is consumed, so the drained page is
        # released progressively rather than all at the end.
        rows.reverse()
        self.rows_remaining = len(rows)
        try:
            while rows:
                row = rows.pop()
                self.rows_remaining = len(rows)
                record = parse_row(row)
                # `row` is not referenced again; the identifier died in parse_row.
                del row
                if record is None:
                    self.rows_unreadable += 1
                    continue
                self.records_yielded += 1
                yield record
                # The caller is done with it. Drop our reference too, so the
                # "one parsed record at a time" claim is true of this frame.
                del record
            self.state = STATE_OK
        except GeneratorExit:
            # The consumer abandoned us. Not an error, and not an `ok` either:
            # the sweep did not finish, so it must not be reported as complete.
            self.state = STATE_ERROR
            self.refusal_gate = "abandoned"
            raise
        finally:
            # Whether we finished or were abandoned, the undelivered rows go now
            # rather than living as long as the generator object does.
            rows.clear()
            self.rows_remaining = 0

    def _drain(self) -> Optional[list]:
        """Open, gate, fetch the bounded page, close. Return the raw rows.

        Returns ``None`` on any failure, having set :attr:`state` and
        :attr:`refusal_gate` — never raising, and never capturing driver text.

        This is the ONLY function in the module that opens a connection, and it
        does not return until that connection is rolled back and closed.
        """
        try:
            db_recon.check_env_gates(self._env, require_opt_in=False)
        except db_recon.ReconRefusal as exc:
            self._fail(ProviderRefusal(exc.gate, exc.reason))
            return None
        except Exception:  # noqa: BLE001 - a failed gate is never a pass
            self._fail(ProviderRefusal("environment", "environment gate failed"))
            return None

        try:
            connection = self._connect(self._env)
        except (ProviderUnavailable, ProviderRefusal) as exc:
            self._fail(exc)
            return None
        except Exception:  # noqa: BLE001 - never surface driver text
            self._fail(ProviderUnavailable("connect", "connection attempt failed"))
            return None

        self.connections_opened += 1
        cursor = None
        rows: list = []
        try:
            _refuse_autocommit(connection)

            # Defence in depth #1: ask the DRIVER for a read-only session. This
            # must happen before the transaction starts.
            setter = getattr(connection, "set_session", None)
            if callable(setter):
                try:
                    setter(readonly=True)
                except Exception:  # noqa: BLE001 - verified server-side below
                    pass

            cursor = connection.cursor()

            # Defence in depth #2: declare it again inside the transaction, from
            # the frozen set. This is the first statement of the transaction, as
            # SET TRANSACTION requires.
            cursor.execute(self.policy.check(Q_SET_TRANSACTION_READ_ONLY))
            cursor.execute(self.policy.check(Q_SET_STATEMENT_TIMEOUT))
            cursor.execute(self.policy.check(Q_SET_LOCK_TIMEOUT))

            # Defence in depth #3: VERIFY. Refuses unless the server says 'on'.
            verify_transaction_read_only(cursor, self.policy)
            self.read_only_verified = True

            cursor.execute(
                self.policy.check(Q_RECORD_PAGE, (self._max_records,)),
                (self._max_records,),
            )

            # Bounded independently of the server's honouring of LIMIT. A server
            # that returned more rows than asked for would otherwise be able to
            # grow pod memory without bound, which is precisely the class of
            # thing a fetch cap exists to stop.
            while len(rows) < self._max_records:
                row = cursor.fetchone()
                if row is None:
                    break
                rows.append(row)
            return rows
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:  # noqa: BLE001 - never leak, never abort
            if type(exc).__name__ in TIMEOUT_EXCEPTION_NAMES:
                self.state = STATE_TIMEOUT
                self.refusal_gate = "timeout"
            elif isinstance(exc, (ProviderRefusal, ProviderUnavailable)):
                self.state = exc.state
                self.refusal_gate = exc.gate
            else:
                # The exception TEXT is never captured: it can carry a row value,
                # a column name, or a connection string.
                self.state = STATE_ERROR
                self.refusal_gate = "unexpected"
            rows.clear()
            return None
        finally:
            # Deterministic, in this order, each independently guarded: a failed
            # rollback must not prevent the close.
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                connection.rollback()
            except Exception:  # noqa: BLE001
                pass
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

    # -- internals ---------------------------------------------------------

    def _reset(self) -> None:
        """A provider is single-use per sweep; re-running starts from zero.

        Without this a second call would accumulate counts onto the first, and
        ``dml_statements`` would stop being a measurement of *this* run.
        """
        self.policy = StatementPolicy()
        self.state = STATE_NOT_RUN
        self.refusal_gate = None
        self.read_only_verified = False
        self.records_yielded = 0
        self.rows_unreadable = 0
        self.connections_opened = 0
        self.rows_remaining = 0

    def _fail(self, exc: ProviderRefusal | ProviderUnavailable) -> None:
        self.state = exc.state
        self.refusal_gate = exc.gate
