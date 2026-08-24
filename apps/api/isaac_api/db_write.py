"""The application's ONLY write path to its own PostgreSQL database.

WHY THIS IS A SEPARATE MODULE FROM ``db_provider`` / ``db_recon``
=================================================================
Those two are **read-only by construction** and their guarantees are pinned by
tests: ``SET TRANSACTION READ ONLY``, a server-side re-verification that the
transaction really is read-only, a frozen statement allowlist, and a statement
policy that refuses anything outside it. Those guarantees protect the
production-derived 30-row ``records`` sample, and they must remain exactly as
strong as they are.

So this module does not extend, relax, subclass or reuse them. It is a second,
independent connection path with its own discipline, its own
``application_name``, and its own narrow reason to exist:

    persisting experiments that THIS APPLICATION created, in tables THIS
    APPLICATION created.

WHAT IT MAY TOUCH, AND WHAT IT MAY NOT
======================================
:data:`OWNED_TABLES` is the complete list of tables this application owns. Every
statement issued through :func:`write_transaction` is checked against
:class:`WriteStatementPolicy`, which refuses:

* any statement naming a table that is not in :data:`OWNED_TABLES` — most
  importantly ``records``, which holds the production-derived sample;
* ``DROP``, ``TRUNCATE``, ``ALTER``, ``GRANT``, ``REVOKE``, ``COPY``, ``VACUUM``,
  ``REINDEX``, ``CLUSTER``, and any statement naming ``ROLE``, ``USER``,
  ``DATABASE``, ``EXTENSION`` or ``AUTHORIZATION`` as a bare token — so
  ``CREATE ROLE``, ``CREATE USER``, ``CREATE DATABASE``, ``CREATE EXTENSION``,
  ``SET ROLE``, ``SET SESSION AUTHORIZATION`` and ``DROP OWNED BY`` are all
  refused, anywhere they appear.

**THIS LIST WAS WRONG UNTIL IT WAS MEASURED, AND THAT IS THE POINT OF THE
PARAGRAPH BELOW.** It named ``CREATE ROLE``/``USER``/``DATABASE``/``EXTENSION``
as refused "anywhere at all" while :data:`_FORBIDDEN_KEYWORDS` contained none of
those four words, so all four were ACCEPTED, as was ``SET ROLE postgres``. A
docstring in a *safety* module is read as a specification and was reviewed as one;
it was made true by extending the list rather than by softening the sentence. The
verbs are enumerated here now instead of summarised, because a summary is what
drifted.

That is a defence-in-depth guard, not the primary one. The primary one is that
every statement this module's callers issue is a module-level constant with
``%s`` placeholders — no caller-supplied SQL exists anywhere in the write path.

KNOWN, ACCEPTED LIMITS OF THE STATEMENT POLICY
==============================================
Recorded rather than fixed, because each fix would cost more than it buys and
because an undocumented limit is what a future reader mistakes for a guarantee.

* **It is a TOKENIZER, not a SQL parser.** It lowercases, extracts
  identifier-shaped tokens, and reasons about which token follows which. It does
  not know about string literals, dollar-quoted bodies or nesting.
* **Concretely: a forbidden verb assembled at run time inside a ``DO`` block is
  not seen.** ``DO $$ BEGIN EXECUTE 'TRUNC' || 'ATE rec' || 'ords'; END $$`` is
  ACCEPTED — no token in it is ``truncate`` or ``records``. This is NOT a
  reachable attack on this application: the only SQL that ever reaches this policy
  is a module-level constant or a committed migration file, both of which a human
  reviews before merge, and neither the route layer nor any request body can
  contribute a character of it. Contorting the tokenizer to catch a shape that
  can only arrive through deliberately obfuscated *committed* SQL would trade real
  clarity for imaginary protection.
* **What actually stops that class of statement is upstream**: no caller-supplied
  SQL exists, and :data:`_FORBIDDEN_TABLES` refuses ``records`` by identifier in
  any position and any syntax, so the plain forms need no grammar to be right.
* ``db_migrate.split_statements`` REFUSES a migration file containing a
  dollar-quote outright, which removes the one committed-file route by which such
  a body could reach here at all.

WHY THE DATABASE NAME IS PINNED FROM A CONSTANT
===============================================
Exactly as ``db_recon`` does it: ``PGDATABASE`` is *gated* (it must read
``metadata_assistant``) and then *ignored*, with the name taken from
:data:`~isaac_api.db_recon.EXPECTED_DATABASE`. A misconfigured or redirected
``PGDATABASE`` therefore refuses rather than writing somewhere unexpected, and a
second server-side check (``current_database()``) catches a redirected
connection that lied.

WHAT THIS MODULE DOES NOT DO
============================
It never connects at import time, it never connects unless ``PGHOST`` is set, it
holds no pool and no long-lived session, and it has no retry loop. One
transaction per call, deterministic rollback, deterministic close.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from .db_recon import EXPECTED_DATABASE

__all__ = [
    "APPLICATION_NAME",
    "EXPECTED_DATABASE",
    "MissingDependency",
    "OWNED_TABLES",
    "Q_SET_LOCK_TIMEOUT",
    "Q_SET_STATEMENT_TIMEOUT",
    "WriteRefused",
    "WriteStatementPolicy",
    "connect_psycopg2",
    "database_configured",
    "pgdatabase_gate",
    "write_transaction",
]


#: How a session opened by the application's write path identifies itself to the
#: server. Deliberately distinct from ``isaac_db_recon`` and
#: ``isaac_record_verification`` so an operator reading ``pg_stat_activity`` can
#: tell the three apart without guessing.
APPLICATION_NAME = "isaac_app_write"


#: Every table this application owns and may write. NOTHING else is writable
#: through this module — see :class:`WriteStatementPolicy`.
#:
#: ``records`` is deliberately, permanently absent. It holds the production-derived
#: 30-row sample and is owned by the record-verification read path; this
#: application must never read it through here, let alone write it.
#:
#: ``isaac_runs`` WAS ADDED FOR MIGRATION ``0002_runs`` AND IS NOW WRITTEN.
#: This set is what the statement policy consults, so a table must be listed here
#: before its own CREATE statement can run — the migration file alone is not
#: enough. Listing it granted nothing on its own; it was the deliberate, reviewable
#: act that let a later slice write the table, and that slice has landed.
#:
#: THE PREVIOUS SENTENCE HERE SAID THE TABLE WAS "NOT YET WRITTEN BY ANYTHING" and
#: cited ``test_0002_is_inert_for_this_build_no_statement_names_isaac_runs`` as the
#: pin. Both are superseded: ``experiment_repository`` now issues
#: ``Q_EXPERIMENT_RUN_ROWS``, ``Q_UPSERT_RUN`` and ``Q_DELETE_ABSENT_RUNS`` inside
#: ``PostgresOrdinaryStore.persist``, and that test has been INVERTED rather than
#: deleted — it now pins the property that is true instead: the WRITE path names
#: this table and the READ path still does not. The wording is replaced rather than
#: softened, because a claim of inertness in a safety module is read as a guarantee.
#: THE FIVE SUBMISSION-LIFECYCLE TABLES (``0003_revisions``, ``0004_submissions``)
#: ARE LISTED HERE IN THE SAME CHANGE THAT CREATES THEM, AND THAT IS NOT OPTIONAL.
#: This set is what :class:`WriteStatementPolicy` consults, and it is consulted
#: BEFORE a connection is opened — so a ``CREATE TABLE isaac_submissions`` in a
#: committed migration file is refused by this application at load time unless the
#: name is here first. Splitting the two across changes does not produce a
#: half-working feature; it produces a migration that cannot run at all.
#:
#: LISTING A TABLE GRANTS NOTHING BY ITSELF. It permits a statement naming it to
#: pass this policy. What may actually be written is decided by the statements that
#: exist, all of which are module-level ``Q_*`` constants, and by the tests that
#: enumerate them. In particular ``test_submission_store.py`` asserts that no
#: ``Q_*`` constant anywhere in this application issues an ``UPDATE`` or a
#: ``DELETE`` naming any of these five — which is the whole of the append-only
#: guarantee, because neither a trigger (it needs a dollar-quoted body, which
#: ``db_migrate.split_statements`` refuses) nor ``REVOKE`` (a forbidden verb, below)
#: is available to enforce it in the database.
#:
#: THEIR AUTHORIZATION BASIS, CITED HERE BECAUSE THE LAST TIME IT WAS NOT, IT WENT
#: UNNOTICED. ``CLAUDE.md`` §15's 2026-08-07 write lift covers Create Experiment
#: persistence "plus the minimum supporting persistence architecture that feature
#: requires", and its enumerated table list named only ``isaac_experiments``,
#: ``isaac_schema_migrations`` and ``isaac_runs`` when these five were added — a gap
#: an independent review found rather than the implementing slice, exactly as
#: happened for ``isaac_runs``. The list is now corrected and both approval packets
#: carry an "Authorization basis" section. Listing a table here is a **recorded
#: scope extension**, and adding a sixth needs the same treatment.
OWNED_TABLES: frozenset[str] = frozenset(
    {
        "isaac_schema_migrations",
        "isaac_experiments",
        "isaac_runs",
        "isaac_experiment_revisions",
        "isaac_run_revisions",
        "isaac_revision_changes",
        "isaac_submissions",
        "isaac_submission_runs",
        # `isaac_run_projection` (0005). LISTED IN THE SAME CHANGE THAT CREATES IT.
        #
        # ~~"and NAMED IN `CLAUDE.md` §15 IN THAT SAME CHANGE — which is the whole
        # point of the two corrections recorded above."~~ **THAT HALF WAS FALSE BY ONE
        # COMMIT, and an independent review measured it.** The table shipped in
        # `6dce6fd`, which does not touch `CLAUDE.md`; §15 was updated in `8f7c650`.
        # So the enumeration was corrected AFTER the write existed for the third time
        # running — a smaller gap than the two below, and not the thing that was
        # claimed. Struck through rather than deleted, because the point of those two
        # corrections is that a claim like this is checkable, and quietly replacing a
        # checked-false claim is the failure they exist to record. `isaac_runs` and the five
        # submission-lifecycle tables were both added here before any committed
        # sentence named them; for the second of those it took an independent
        # review to notice. Its authorization basis is §15's "minimum supporting
        # persistence architecture that feature requires" clause PLUS the
        # enumeration, not the clause alone, and the contract that says why the
        # table has to exist at all is `docs/isaac-runs-stage-2-contract.md` §1.
        #
        # WHAT LISTING IT PERMITS, precisely: `0005`'s two CREATE statements, and
        # the write path's `Q_UPSERT_RUN_PROJECTION`. Nothing reads it. There is no
        # UPDATE and no DELETE naming it anywhere in this application — the upsert
        # is the only writer, and the rollback's DROP lives in a file the runner
        # never loads.
        "isaac_run_projection",
    }
)


#: Conservative per-transaction limits, ``SET LOCAL`` so they expire with the
#: transaction and can never leak into another session's settings.
Q_SET_STATEMENT_TIMEOUT = "SET LOCAL statement_timeout = '15000ms'"
Q_SET_LOCK_TIMEOUT = "SET LOCAL lock_timeout = '3000ms'"

#: Gate 2, server-side: guards against a ``PGDATABASE`` lie or a redirected
#: connection. The same check ``db_recon`` makes, for the same reason.
Q_CURRENT_DATABASE = "SELECT current_database()"


class MissingDependency(RuntimeError):
    """psycopg2 is not importable in this interpreter."""


class WriteRefused(RuntimeError):
    """The write path refused before doing anything.

    Carries a FIXED, path-free, credential-free message for the same reason
    ``db_recon.InvalidTutorialSession``-style errors do: this can surface on a
    request path, and psycopg2's own messages echo the host, the user and the
    connection string.
    """


# --- statement policy ---------------------------------------------------------

#: Verbs refused WHEREVER they appear, whatever they name. Each is a shape that
#: could destroy or expose data this application does not own, and the owner's
#: authorization forbids all of them by name. None of them has a legitimate use
#: anywhere in this application's write path — including in its own migrations,
#: which are forward-only and create-only.
#:
#: ``do`` is deliberately NOT here: it is a required keyword of
#: ``INSERT ... ON CONFLICT ... DO UPDATE``, which is how an experiment's state is
#: upserted. ``DO $$ ... $$`` anonymous blocks are refused by the fact that this
#: application never writes one, not by this list.
#:
#: ``role``, ``user``, ``database`` AND ``extension`` WERE MISSING, AND THE MODULE
#: DOCSTRING SAID THEY WERE NOT. It claimed ``CREATE ROLE`` / ``USER`` /
#: ``DATABASE`` / ``EXTENSION`` were refused "anywhere at all"; measured against the
#: policy as it stood, all four were ACCEPTED, as was ``SET ROLE postgres``. The
#: list is what the docstring described, so the list is what was corrected — the
#: alternative, weakening the docstring to match, would have documented a gap
#: instead of closing one, and closing it costs four strings.
#:
#: ``SET ROLE`` IS INCLUDED DELIBERATELY, on the same reasoning as the others
#: rather than as an afterthought. It changes the identity a statement executes
#: as, which is the one thing that could make every other guard in this module
#: irrelevant — a session that becomes a superuser mid-transaction is no longer
#: constrained by which tables this application owns. Nothing this application
#: issues names a role, so the cost of refusing it is zero. ``RESET ROLE`` is
#: covered by the same ``role`` token.
#:
#: ``authorization`` IS ITS OWN ENTRY, and it is here because a test caught the
#: claim that it was not needed. ``SET SESSION AUTHORIZATION postgres`` tokenizes
#: to ``set session authorization postgres`` — it contains neither ``role`` nor
#: ``user``, so an earlier draft of this comment asserting it was "covered by the
#: same token" was simply wrong. It is the same privilege-switch shape as
#: ``SET ROLE`` and is refused by name rather than by hope.
#:
#: VERIFIED AGAINST WHAT THE APPLICATION ACTUALLY ISSUES, not assumed: all TWELVE
#: module-level statements and all five committed migration statements (three from
#: ``0001_experiments``, two from ``0002_runs``) still pass, pinned by
#: ``test_every_statement_this_application_actually_issues_passes_the_policy`` and
#: by ``test_the_committed_migrations_load_and_are_create_only``.
#: (That count read "eight" while the pinning test already enumerated NINE, and it
#: is now twelve: ``experiment_repository`` added the three ``isaac_runs``
#: statements. A hand-maintained tally in a safety comment drifts, which is why the
#: test enumerates the modules' ``Q_*`` names rather than trusting this number.)
#: The near-misses are worth naming, because they are why this is a token match
#: and not a substring one: ``current_database`` (in ``Q_CURRENT_DATABASE``) and
#: ``isaac_schema_migrations`` are each a SINGLE identifier token, so neither
#: contains ``database`` or ``user`` as far as this filter is concerned. A
#: substring check would have refused the write path's own database-verification
#: query.
_FORBIDDEN_KEYWORDS = (
    "drop",
    "truncate",
    "alter",
    "grant",
    "revoke",
    "copy",
    "vacuum",
    "reindex",
    "cluster",
    "role",
    "user",
    "database",
    "extension",
    "authorization",
)

#: Identifier-ish tokens. Used to find table names; deliberately crude, because
#: this is a *refusal* filter — an over-broad match refuses a legal statement
#: (loud, fixable) rather than admitting an illegal one (silent, not).
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: The clauses after which a table name appears.
#:
#: ``on`` IS IN THIS LIST, AND IT WAS NOT AT FIRST. It was left out because
#: ``INSERT ... ON CONFLICT (id) DO UPDATE`` would otherwise be read as naming a
#: table called ``conflict``. That reasoning was right about ``ON CONFLICT`` and
#: wrong about everything else: ``CREATE INDEX ... ON <table>`` names a table
#: after ``on`` too, so a migration statement reading
#: ``CREATE INDEX isaac_probe_idx ON records (record_id)`` PASSED this policy —
#: as did ``CREATE TRIGGER ... ON records``. Neither reads or writes a row, which
#: is why they read as harmless; both take a lock on the production-derived sample
#: and change its schema permanently, which is exactly what this guard exists to
#: stop.
#:
#: HOW IT WAS FOUND, since that is the part worth keeping: not by review, and not
#: because the statement was ever committed. It was a deliberate temporary
#: mutation during the negative-control pass over this feature — append a
#: statement touching a table the migration does not own, run the tests, see what
#: fails, revert. What failed was a statement-COUNT assertion in
#: ``test_the_committed_migration_loads_and_is_create_only``, not this policy; had
#: the statement replaced an existing one instead of being appended, nothing would
#: have failed at all.
#:
#: ``ON CONFLICT`` is handled where it belongs, in :meth:`_table_after`, rather
#: than by omitting the keyword and hoping no other ``ON`` clause ever appears.
_TABLE_INTRODUCERS = ("from", "join", "into", "update", "table", "on")

#: Tables that may NEVER be named, in any statement, in any position, whatever
#: the surrounding syntax.
#:
#: This is a second, independent guard and it is deliberately redundant with the
#: owned-tables check above. That check reasons about GRAMMAR — which token
#: follows which clause — and grammar is where the bug above lived. This one
#: reasons about nothing: if the identifier appears at all, the statement is
#: refused. A future SQL shape nobody anticipated cannot slip a reference to
#: ``records`` past it, because there is no shape to get right.
#:
#: ``records`` holds the production-derived 30-row sample. This application must
#: not read it, write it, index it, analyze it, or reference it in a constraint.
_FORBIDDEN_TABLES = ("records",)


class WriteStatementPolicy:
    """Refuses any statement outside this application's own tables.

    Deliberately a *policy object* rather than a frozen allowlist of literal
    strings: the migration runner executes SQL read from committed files, so the
    exact text is not known here. What IS knowable — and is what matters — is
    which tables may be named and which verbs may never appear.
    """

    def __init__(self, owned: frozenset[str] = OWNED_TABLES) -> None:
        self.owned = owned
        #: Every statement that passed, in order. An OBSERVATION for tests and
        #: reports, never an assertion the module makes about itself.
        self.seen: list[str] = []

    def check(self, sql: str) -> str:
        stripped = sql.strip()
        if not stripped:
            raise WriteRefused("empty statement")
        lowered = stripped.lower()
        tokens = _IDENT_RE.findall(lowered)
        for index, token in enumerate(tokens):
            if token in _FORBIDDEN_KEYWORDS:
                raise WriteRefused(f"statement uses a forbidden verb: {token}")
            if token in _FORBIDDEN_TABLES:
                raise WriteRefused(
                    "statement names a table this application must never reference"
                )
            if token not in _TABLE_INTRODUCERS:
                continue
            named = self._table_after(tokens, index)
            if named is None:
                # The introducer named nothing this pass can resolve — e.g.
                # ``ON CONFLICT ... DO UPDATE SET``, where ``update`` introduces a
                # SET clause rather than a table. Not a table reference, so not a
                # table this guard has anything to say about.
                continue
            if named not in self.owned:
                raise WriteRefused(
                    "statement names a table this application does not own"
                )
        self.seen.append(stripped)
        return stripped

    @staticmethod
    def _table_after(tokens: list[str], index: int) -> str | None:
        """The table name an introducer at ``index`` names, or ``None``.

        Skips the modifiers that may sit between them (``CREATE TABLE IF NOT
        EXISTS x``, ``DELETE FROM ONLY x``) and returns ``None`` for the one
        shape where the introducer is not introducing a table at all
        (``DO UPDATE SET``).
        """
        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor] in ("if", "not", "exists", "only"):
            cursor += 1
        if cursor >= len(tokens):
            return None
        candidate = tokens[cursor]
        # ``DO UPDATE SET`` — a conflict action, not a table.
        if candidate == "set":
            return None
        # ``ON CONFLICT`` — the upsert clause, not a table reference. This is the
        # ONE reason ``on`` was originally kept out of the introducer list; naming
        # the exception here is what let it go back in, which is what closes
        # ``CREATE INDEX ... ON <table>``.
        if candidate == "conflict":
            return None
        return candidate


# --- environment --------------------------------------------------------------


def database_configured(env: Mapping[str, str]) -> bool:
    """Whether this deployment has an application database configured.

    ``PGHOST`` is the deployment's documented feature switch
    (``docs/postgres-test-db-guide.md``, ``docs/deployment.md``): the pod sets the
    standard libpq variables, and a local checkout or a CI runner sets none. So
    "no ``PGHOST``" means "no database", which is exactly what makes the
    filesystem fallback the default everywhere except the deployed pod.

    Configuration only. This function opens nothing and proves nothing about
    reachability.
    """
    return bool((env.get("PGHOST") or "").strip())


def pgdatabase_gate(env: Mapping[str, str]) -> None:
    """Gate 1 — ``PGDATABASE`` must read exactly :data:`EXPECTED_DATABASE`.

    Raises :class:`WriteRefused` otherwise. The observed value IS named: it is a
    database name the operator supplied, not data, and naming it is what makes
    the refusal actionable.
    """
    pgdatabase = (env.get("PGDATABASE") or "").strip()
    if pgdatabase != EXPECTED_DATABASE:
        raise WriteRefused(
            f"PGDATABASE must be exactly {EXPECTED_DATABASE!r} (got {pgdatabase!r})"
        )


def connect_psycopg2(env: Mapping[str, str]) -> Any:
    """Open a TLS connection using libpq env vars. psycopg2 imported LAZILY.

    ``psycopg2-binary>=2.9`` is a declared project dependency (the ``api`` extra).
    The import is still deferred to call time so importing this module — and
    running its tests — never depends on the driver being present.
    """
    try:
        import psycopg2  # noqa: PLC0415 - intentionally lazy; see docstring
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise MissingDependency(
            "psycopg2 is not importable in this interpreter. It IS a declared "
            "project dependency (the 'api' extra in pyproject.toml, "
            "psycopg2-binary>=2.9): install it with `pip install -e '.[api]'`."
        ) from exc
    missing = [n for n in ("PGHOST", "PGUSER", "PGPASSWORD") if not (env.get(n) or "")]
    if missing:
        raise WriteRefused(
            "missing required libpq environment variables: " + ", ".join(sorted(missing))
        )
    try:
        return psycopg2.connect(
            host=env["PGHOST"],
            # ── `hostaddr=None` IS EXPLICIT, AND IT IS NOT REDUNDANT. ─────────────────
            # libpq fills EVERY connection parameter this call leaves unspecified from
            # the corresponding `PG*` environment variable, and `PGHOSTADDR` is one of
            # them. When both are set, `hostaddr` is the address libpq actually
            # CONNECTS to and `host` is used only for TLS certificate and GSSAPI name
            # verification — so passing `host=` and saying nothing about `hostaddr`
            # means the string this application reasoned about is not necessarily the
            # machine it reached.
            #
            # WHAT THAT DEFEATED, measured by an independent security review on
            # 2026-08-24. `apps/api/tests/test_run_row_parity.py` — a suite that
            # WRITES — decides "this is a local throwaway engine" from the `PGHOST`
            # STRING alone (`_is_loopback_target`). With `PGHOST=localhost`,
            # `PGHOSTADDR=<a hosted address>` and `PGDATABASE=metadata_assistant`,
            # every gate in that suite passes — including `write_transaction`'s own
            # `current_database()` re-check, which asks the server it is talking to and
            # so agrees with itself — and the writes land wherever `hostaddr` points.
            # Passing `None` explicitly makes libpq ignore `PGHOSTADDR` entirely, so
            # `host` is once again both the name that is verified and the target that
            # is reached.
            #
            # THIS WAS CODE-VERIFIED, NOT EXECUTED. psycopg2 is not installed in this
            # interpreter (see `test_db_provider`'s absent-driver test), and no agent
            # may connect to the SLAC database, so the claim above rests on libpq's
            # documented parameter precedence and on reading this call — not on a
            # connection anybody opened. The test beside it asserts the KEYWORD is
            # passed and is `None`, which is the part that is checkable here.
            #
            # IT IS DEFENCE IN DEPTH AND THE OPT-IN IS STILL THE REAL GATE.
            # `ISAAC_RUN_REAL_ENGINE_PARITY` is what stops that suite connecting at
            # all; this closes a hole in a check that was already the second line, and
            # it should not be described as making the environment safe.
            hostaddr=None,
            port=env.get("PGPORT", "5432"),
            dbname=EXPECTED_DATABASE,  # never the env value: the gate already pinned it
            user=env["PGUSER"],
            password=env["PGPASSWORD"],
            sslmode=env.get("PGSSLMODE", "require"),
            connect_timeout=int(env.get("PGCONNECT_TIMEOUT", "10")),
            application_name=APPLICATION_NAME,
        )
    except Exception as exc:  # noqa: BLE001
        # Only the exception CLASS is reported: psycopg2 messages echo the host,
        # the user and the connection string.
        raise WriteRefused(f"could not connect ({type(exc).__name__})")


# --- the one transaction shape ------------------------------------------------


@contextmanager
def write_transaction(
    env: Mapping[str, str], *, connect=None
) -> Iterator[tuple[Any, WriteStatementPolicy]]:
    """One short-lived connection, one explicit transaction, deterministic close.

    Yields ``(cursor, policy)``. Every statement the body issues MUST go through
    ``policy.check(...)`` — that is what makes the owned-tables guard real rather
    than advisory, and the tests assert on ``policy.seen``.

    Commits on a clean exit; rolls back on ANY exception and re-raises. Closes the
    cursor and the connection in a ``finally`` either way, so no session is left
    idle-in-transaction.

    ``connect`` is injectable so the whole shape can be exercised against an
    in-process fake with no driver and no server. It defaults to ``None`` rather
    than to :func:`connect_psycopg2` DELIBERATELY: a default evaluated at ``def``
    time captures the function object, so a test that monkeypatches
    ``db_write.connect_psycopg2`` would be silently ignored and would appear to
    prove the app never connects when in fact it had connected for real.
    """
    pgdatabase_gate(env)
    connect = connect_psycopg2 if connect is None else connect
    conn = connect(env)
    policy = WriteStatementPolicy()
    cursor = None
    try:
        # Explicit, never autocommit: a partially applied migration or a
        # half-written experiment must not survive an error.
        conn.autocommit = False
        cursor = conn.cursor()
        cursor.execute(policy.check(Q_SET_STATEMENT_TIMEOUT))
        cursor.execute(policy.check(Q_SET_LOCK_TIMEOUT))
        cursor.execute(policy.check(Q_CURRENT_DATABASE))
        row = cursor.fetchone()
        actual = str((row or [""])[0] or "").strip()
        if actual != EXPECTED_DATABASE:
            raise WriteRefused(
                f"connected database is {actual!r}, expected {EXPECTED_DATABASE!r}"
            )
        yield cursor, policy
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001 - pragma: no cover - best effort
            pass
        raise
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001 - pragma: no cover - best effort
                pass
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - pragma: no cover - best effort
            pass
