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
"""

from __future__ import annotations

import os
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
    """
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


def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Every committed migration, ordered by filename.

    The version IS the filename stem, so ordering is lexicographic and visible in
    a directory listing. Rollback files are excluded by suffix.
    """
    if not directory.is_dir():
        return []
    out: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        if path.name.endswith(_ROLLBACK_SUFFIX):
            continue
        out.append(
            Migration(path.stem, path, split_statements(path.read_text(encoding="utf-8")))
        )
    return out


def applied_versions(cursor: Any, policy: Any) -> list[str]:
    """Versions already recorded in the bookkeeping table.

    Routed through ``policy`` like every other statement, so "every statement the
    write path issues passed the owned-tables guard" stays literally true rather
    than true-of-most-of-them.
    """
    cursor.execute(policy.check(Q_APPLIED_VERSIONS))
    return [str(row[0]) for row in (cursor.fetchall() or [])]


def pending_versions(
    env: Mapping[str, str] | None = None, *, directory: Path = MIGRATIONS_DIR, **kwargs
) -> list[str]:
    """What :func:`migrate` WOULD apply, applying nothing.

    Opens one transaction, ensures the bookkeeping table exists, reads it, and
    commits. It is not read-only (it may create the bookkeeping table), and saying
    so is more useful than a name that implies otherwise.
    """
    env = os.environ if env is None else env
    migrations = load_migrations(directory)
    with write_transaction(env, **kwargs) as (cursor, policy):
        cursor.execute(policy.check(Q_ENSURE_BOOKKEEPING))
        done = set(applied_versions(cursor, policy))
    return [m.version for m in migrations if m.version not in done]


def migrate(
    env: Mapping[str, str] | None = None, *, directory: Path = MIGRATIONS_DIR, **kwargs
) -> list[str]:
    """Apply every pending migration. Returns the versions actually applied.

    ONE TRANSACTION PER MIGRATION, and the bookkeeping row is written inside it.
    A second run returns ``[]``.

    Every statement passes through the write path's statement policy, so a
    migration that tried to ``DROP`` something, or to name a table this
    application does not own, refuses here rather than at the database.
    """
    env = os.environ if env is None else env
    migrations = load_migrations(directory)
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
