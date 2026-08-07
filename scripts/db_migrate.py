#!/usr/bin/env python3
"""Apply this application's own forward-only migrations. An OPERATOR command.

WHO RUNS THIS, AND WHO DOES NOT
===============================
A human, or CI against a throwaway service container. **The application never
runs it.** Nothing in ``isaac_api`` imports this file and no route reaches
``db_migrate.migrate``: a pod that silently migrated its own production database
on every rollout is exactly what the authorization for this work excludes, and
the owner reviews the migration before it is applied.

USAGE
=====
It reads the standard libpq environment variables that are already set in the
deployed pod (``PGHOST``, ``PGUSER``, ``PGPASSWORD``, ``PGDATABASE``, …). It
refuses unless ``PGDATABASE`` is exactly ``metadata_assistant``.

    python scripts/db_migrate.py --plan     # what WOULD be applied. Applies nothing.
    python scripts/db_migrate.py --apply    # apply it.

``--plan`` is the default, so a bare invocation cannot change anything.

WHAT IT CANNOT DO
=================
Every statement passes through ``db_write.WriteStatementPolicy``, which refuses
``DROP``, ``TRUNCATE``, ``ALTER``, ``GRANT``, ``REVOKE`` and ``COPY`` anywhere,
and refuses any statement naming a table outside
``db_write.OWNED_TABLES``. The production-derived ``records`` table is not in
that set and never will be, so this command cannot read it, change it, or drop
it — including by way of a migration file someone edits later.

ROLLBACK IS NOT HERE, ON PURPOSE. It is a committed ``.sql`` file
(``apps/api/isaac_api/migrations/0001_experiments.rollback.sql``) that an
operator runs with psql, having read what it destroys. A ``--rollback`` flag on
the same command that applies would make an irreversible act one typo away from
a reversible one.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from isaac_api import db_migrate, db_write  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--plan",
        action="store_true",
        help="report what would be applied and exit. The default.",
    )
    group.add_argument("--apply", action="store_true", help="apply pending migrations")
    args = parser.parse_args(argv)

    if not db_write.database_configured(os.environ):
        print("PGHOST is not set: there is no database to migrate.", file=sys.stderr)
        return 2

    try:
        if args.apply:
            applied = db_migrate.migrate(os.environ)
            if applied:
                print("applied: " + ", ".join(applied))
            else:
                print("nothing to apply (every migration is already recorded)")
        else:
            pending = db_migrate.pending_versions(os.environ)
            print("pending: " + (", ".join(pending) if pending else "(none)"))
    except db_write.WriteRefused as exc:
        # The message is fixed and path-free by construction; see WriteRefused.
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    except db_write.MissingDependency as exc:
        print(str(exc), file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
