"""A minimal, dependency-free, forward-only migration runner.

WHY NOT ALEMBIC
===============
The repository has no migration tooling and no ORM, and this change needs exactly
two tables. A heavyweight migrator would add a dependency, a config file, an
autogenerate story and a second source of truth about the schema, in exchange for
features nothing here uses (downgrades, branching, autogeneration from models).
This runner is ~100 lines, has no dependency beyond the driver already declared,
and can be read in full before it is trusted with a production database.

THE CONTRACT
============
* **Forward-only.** There is no ``downgrade``. A rollback is a committed ``.sql``
  file an operator runs deliberately with psql; the application has no path to it
  (``db_write.WriteStatementPolicy`` refuses ``DROP``).
* **Idempotent, twice over.** :data:`_MIGRATIONS` bookkeeping skips a version that
  has already been applied, AND every statement in every migration is
  ``CREATE ... IF NOT EXISTS``. Either alone would make a re-run a no-op; both
  means losing the bookkeeping table does not break the runner.
* **Create-only.** Nothing here may ``DROP``, ``TRUNCATE`` or ``ALTER``, and
  nothing may name a table outside :data:`~isaac_api.db_write.OWNED_TABLES`.
  That is enforced statement by statement, not asserted in a comment.
* **One transaction per migration.** A migration that fails part-way leaves the
  database exactly as it was, and the bookkeeping row is written inside the same
  transaction as the DDL it records — so "applied" and "recorded" can never
  disagree.

WHO RUNS IT
===========
Not the application at boot. :func:`migrate` is called by
``scripts/db_migrate.py`` (an operator command) and by CI against a service
container. A pod does not migrate itself: the owner reviews and applies the
migration, and an app that silently migrates its own production database on every
rollout is precisely what the authorization for this work excludes.

:func:`pending_versions` is the read-only half — it reports what WOULD be applied
without applying anything, so the operator can see the plan first.

BOUNDING A RUN: "UP TO AND INCLUDING", AND NOTHING ELSE
======================================================
:func:`select_through` truncates the ordered migration list to the PREFIX ending
at a named version, and :func:`load_migrations`, :func:`pending_versions` and
:func:`migrate` all take the same ``through=`` keyword. It exists for one
measured reason: an operator can be approved to apply some migrations and
forbidden to apply a later one, and until this existed there was no invocation
of the operator command that did the first without the second — so the approval
and the prohibition were not jointly satisfiable and the operator was told not
to start.

**A PREFIX IS THE ONLY SHAPE, ON PURPOSE.** There is deliberately no
per-version cherry-pick and no "skip this one": every migration here declares
foreign keys into tables an earlier one creates, and the presence checks inside
a migration are sound only because everything before it has run. A tool that
could apply ``0004`` without ``0003`` would be a tool for corrupting a schema,
so that shape is not expressible rather than merely discouraged.

**IT IS NOT A ROLLBACK AND CANNOT BECOME ONE.** ``through`` selects a prefix of
the FORWARD set to apply; it removes nothing, drops nothing, and deletes no
bookkeeping row. Rollback remains what it has always been — a committed
``*.rollback.sql`` file a human runs with psql, which this module never loads
(excluded by suffix) and which the write path's statement policy refuses.

**THE BOOKKEEPING STAYS THE SAME BOOKKEEPING.** A bounded apply records exactly
the versions it applied, in the same transaction as their DDL, so a later
unbounded apply picks up precisely what the bound withheld, and a second bounded
apply is a no-op. The bound is an argument to one invocation; it is never
persisted, so no state can remember it and quietly withhold something later.

**AN UNKNOWN VERSION REFUSES, LOUDLY, BEFORE ANY CONNECTION IS OPENED.** The
failure mode that would matter is a typo silently applying everything or
nothing, so the match is exact — no prefix, no substring, no glob.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .db_write import WriteRefused, write_transaction

__all__ = [
    "MIGRATIONS_DIR",
    "STATEMENT_SEPARATOR",
    "Migration",
    "applied_versions",
    "load_migrations",
    "migrate",
    "pending_versions",
    "select_through",
    "split_statements",
]


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

#: Statements inside a migration file are separated by a line that is exactly
#: ``--;``. Splitting on a bare ``;`` would cut a statement in half whenever one
#: appeared inside a string literal, a ``CHECK`` regex or a comment — and this
#: migration's ``CHECK (experiment_id ~ '^[0-9A-Z]{26}$')`` is exactly the kind of
#: literal that invites that bug. A marker that is itself a SQL comment keeps each
#: file valid, runnable SQL when handed to psql for review.
STATEMENT_SEPARATOR = "--;"

#: A rollback file is committed beside its migration for review, and is never
#: loaded by this runner.
_ROLLBACK_SUFFIX = ".rollback.sql"

#: A PostgreSQL dollar-quoted string — ``$$ … $$`` or ``$tag$ … $tag$``. Matching
#: the OPENING delimiter is enough: :func:`split_statements` refuses the file
#: outright rather than trying to find the matching close, which would be the
#: first step down the road of writing a SQL parser here.
_DOLLAR_QUOTE_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")

Q_ENSURE_BOOKKEEPING = (
    "CREATE TABLE IF NOT EXISTS isaac_schema_migrations ("
    " version text PRIMARY KEY,"
    " applied_utc timestamptz NOT NULL DEFAULT now())"
)
Q_APPLIED_VERSIONS = "SELECT version FROM isaac_schema_migrations ORDER BY version"
Q_RECORD_VERSION = (
    "INSERT INTO isaac_schema_migrations (version) VALUES (%s)"
    " ON CONFLICT (version) DO NOTHING"
)


class Migration:
    """One committed migration file: a version and its ordered statements."""

    __slots__ = ("version", "path", "statements")

    def __init__(self, version: str, path: Path, statements: Sequence[str]) -> None:
        self.version = version
        self.path = path
        self.statements = tuple(statements)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Migration {self.version} ({len(self.statements)} statements)>"


def split_statements(sql: str) -> list[str]:
    """Split a migration file into statements on :data:`STATEMENT_SEPARATOR`.

    THE SPLIT IS LINE-BASED, on a line that is EXACTLY the marker after stripping —
    not on every occurrence of the marker in the text. That is not fussiness: the
    first version split on the substring, and the migration file's own header
    comment quotes the marker while explaining it, so the file cut itself in half
    inside a sentence and the first "statement" was a fragment of prose. A file
    must be able to document its own conventions.

    Comment-only and blank chunks are dropped: a file that is entirely commentary
    yields no statements, rather than one statement that is a comment.

    A DOLLAR-QUOTED BODY IS REFUSED, NOT PARSED, and the refusal is the feature.
    This splitter is line-based and comment-blind: it drops every line beginning
    ``--`` and cuts on a line that is exactly ``--;``. Inside ``$$ … $$`` — a
    ``DO`` block, a function body — both rules are wrong, because such a line is
    body text rather than syntax. It would be SILENTLY MANGLED: a line of the
    body starting ``--`` would vanish, and a body line reading ``--;`` would split
    the block in two, producing two statements that are each invalid SQL and
    neither of which is what the author wrote. No committed migration uses one
    today, so the honest options were "refuse" or "write a SQL parser". Refusing
    fails loudly at load time, before a connection is opened, and can be revisited
    the day a migration genuinely needs a function body.

    :class:`~isaac_api.db_write.WriteRefused` rather than a new exception type: the
    caller already handles it, and the meaning is the same one it always carries —
    this SQL will not be executed.
    """
    if _DOLLAR_QUOTE_RE.search(sql):
        raise WriteRefused(
            "this migration contains a dollar-quoted body ($$ ... $$), which the "
            "line-based statement splitter cannot read without silently mangling "
            "it. Rewrite the statement without one, or teach the splitter to "
            "understand dollar quoting before using it."
        )
    out: list[str] = []
    chunk: list[str] = []

    def flush() -> None:
        body = "\n".join(
            line for line in chunk if not line.strip().startswith("--")
        ).strip()
        if body:
            out.append(body)
        chunk.clear()

    for line in sql.splitlines():
        if line.strip() == STATEMENT_SEPARATOR:
            flush()
        else:
            chunk.append(line)
    flush()
    return out


def select_through(
    migrations: Sequence[Migration], through: str | None
) -> tuple[list[Migration], list[str]]:
    """Truncate an ordered migration list to the prefix ENDING AT ``through``.

    Returns ``(selected, withheld_versions)``. ``through=None`` selects
    everything and withholds nothing, which is the unbounded behaviour this
    runner has always had.

    A PREFIX, NOT A PICK. ``selected`` is always ``migrations[:i + 1]`` for the
    index of ``through``, so a caller cannot express "apply 0004 but not 0003",
    "apply them in another order", or "skip one in the middle". Those are not
    options this function withholds by policy; they are shapes its return type
    cannot represent. That matters because every migration here declares a
    foreign key into a table an earlier one creates, and because the presence
    checks inside a later migration are sound only if the runner's ordering
    guarantee held.

    ``withheld_versions`` is a fact about the FILE SET, not about the database:
    it is every version after the boundary, applied or not. It is returned so a
    caller can say out loud what a bounded run is leaving alone, which is the
    thing an operator has to confirm. Computing it needs no connection.

    AN EXACT MATCH OR A REFUSAL. A typo must never quietly apply everything or
    quietly apply nothing, so there is no prefix match, no substring match and
    no glob. A ``*.rollback.sql`` stem is not in ``migrations`` at all (excluded
    by suffix in :func:`load_migrations`), so naming one refuses here — this is
    a forward-only selector and cannot be pointed at a rollback.
    """
    ordered = list(migrations)
    if through is None:
        return ordered, []
    versions = [m.version for m in ordered]
    if through not in versions:
        known = ", ".join(versions) if versions else "(none)"
        raise WriteRefused(
            f"no migration is named {through!r}, so there is nothing to apply "
            f"through. The committed versions are: {known}. A version must be "
            "given EXACTLY as its file stem — no prefix, substring or partial "
            "match is accepted, and a rollback file is never a migration. "
            "Nothing was applied and no connection was opened."
        )
    cut = versions.index(through) + 1
    return ordered[:cut], versions[cut:]


def load_migrations(
    directory: Path = MIGRATIONS_DIR, *, through: str | None = None
) -> list[Migration]:
    """Every committed migration, ordered by filename.

    The version IS the filename stem, so ordering is lexicographic and visible in
    a directory listing. Rollback files are excluded by suffix.

    ``through`` bounds the result to the prefix ending at that version, and
    refuses if no such version exists — see :func:`select_through`. The bound is
    applied AFTER loading, so a version that exists but sits after the boundary
    is still read and still parsed: a syntactically broken migration cannot hide
    behind a bound.
    """
    if not directory.is_dir():
        return select_through([], through)[0]
    out: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        if path.name.endswith(_ROLLBACK_SUFFIX):
            continue
        out.append(
            Migration(path.stem, path, split_statements(path.read_text(encoding="utf-8")))
        )
    return select_through(out, through)[0]


def applied_versions(cursor: Any, policy: Any) -> list[str]:
    """Versions already recorded in the bookkeeping table.

    Routed through ``policy`` like every other statement, so "every statement the
    write path issues passed the owned-tables guard" stays literally true rather
    than true-of-most-of-them.
    """
    cursor.execute(policy.check(Q_APPLIED_VERSIONS))
    return [str(row[0]) for row in (cursor.fetchall() or [])]


def pending_versions(
    env: Mapping[str, str] | None = None,
    *,
    directory: Path = MIGRATIONS_DIR,
    through: str | None = None,
    **kwargs,
) -> list[str]:
    """What :func:`migrate` WOULD apply, applying nothing.

    Opens one transaction, ensures the bookkeeping table exists, reads it, and
    commits. It is not read-only (it may create the bookkeeping table), and saying
    so is more useful than a name that implies otherwise.

    ``through`` bounds the answer EXACTLY as it bounds :func:`migrate`, and that
    is the whole point of it being the same keyword on both: the plan an operator
    reads is the plan the apply carries out. A bad ``through`` refuses before the
    transaction is opened, because :func:`load_migrations` runs first.
    """
    env = os.environ if env is None else env
    migrations = load_migrations(directory, through=through)
    with write_transaction(env, **kwargs) as (cursor, policy):
        cursor.execute(policy.check(Q_ENSURE_BOOKKEEPING))
        done = set(applied_versions(cursor, policy))
    return [m.version for m in migrations if m.version not in done]


def migrate(
    env: Mapping[str, str] | None = None,
    *,
    directory: Path = MIGRATIONS_DIR,
    through: str | None = None,
    **kwargs,
) -> list[str]:
    """Apply every pending migration. Returns the versions actually applied.

    ONE TRANSACTION PER MIGRATION, and the bookkeeping row is written inside it.
    A second run returns ``[]``.

    Every statement passes through the write path's statement policy, so a
    migration that tried to ``DROP`` something, or to name a table this
    application does not own, refuses here rather than at the database. **That
    is as true of a bounded run as of an unbounded one** — ``through`` narrows
    which files are considered and changes nothing about how their statements are
    checked or executed, which is why it is not a way around the policy.

    ``through`` applies every pending migration UP TO AND INCLUDING that version
    and nothing after it. Bookkeeping is unchanged: only the versions actually
    applied are recorded, each inside its own transaction, so a later unbounded
    run applies exactly what the bound withheld and a second bounded run returns
    ``[]``. The bound is never persisted anywhere.
    """
    env = os.environ if env is None else env
    migrations = load_migrations(directory, through=through)
    applied: list[str] = []
    for migration in migrations:
        if not migration.statements:
            raise WriteRefused(f"migration {migration.version} contains no statements")
        with write_transaction(env, **kwargs) as (cursor, policy):
            cursor.execute(policy.check(Q_ENSURE_BOOKKEEPING))
            if migration.version in set(applied_versions(cursor, policy)):
                continue
            for statement in migration.statements:
                cursor.execute(policy.check(statement))
            cursor.execute(policy.check(Q_RECORD_VERSION), (migration.version,))
            applied.append(migration.version)
    return applied
