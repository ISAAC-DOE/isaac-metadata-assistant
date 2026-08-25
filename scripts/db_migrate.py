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

BOUNDING A RUN — ``--through VERSION``
=====================================
Both forms take ``--through VERSION``, which selects every pending migration
**up to and including** that version and leaves everything after it alone::

    python scripts/db_migrate.py --plan  --through 0004_submissions
    python scripts/db_migrate.py --apply --through 0004_submissions

It exists because an operator can be approved to apply some migrations and
forbidden to apply a later one, and without it there was no invocation of this
command that did the first without the second. ``--through`` bounds ``--plan``
identically, so **the plan you read is the apply you get** — read the plan
first, against the packet.

Four properties worth knowing before you type it:

* **"Up to and including" is the only shape.** There is no per-version pick and
  no way to skip one in the middle. Each migration here declares a foreign key
  into a table an earlier one creates, so a runner that could apply ``0004``
  without ``0003`` would be a runner for breaking a schema.
* **A typo REFUSES, loudly, before any connection is opened.** The version must
  be given exactly as its file stem. It never falls back to applying everything
  or to applying nothing quietly.
* **IT IS NOT A ROLLBACK.** It selects a prefix of the forward set to apply. It
  removes nothing, drops nothing and deletes no bookkeeping row, and it cannot
  be pointed at a ``*.rollback.sql`` file — see the rollback note below.
* **The bookkeeping stays correct and the bound is not remembered.** Only the
  versions actually applied are recorded. A later unbounded ``--apply`` applies
  exactly what the bound withheld; a second identical bounded ``--apply`` is a
  no-op.

A bounded run also prints, on its own line, what it withheld — so "``0005`` was
not applied" is something you read rather than something you infer.

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

``--through`` does not weaken any of that, and it is worth saying why rather than
leaving it to be assumed. It selects a prefix of the FORWARD set. The only names
it accepts are the versions ``load_migrations`` returns, and that function
excludes ``*.rollback.sql`` by suffix — so ``--through 0003_revisions.rollback``
is a refusal, not a rollback. Nothing about the flag can drop a table, delete a
bookkeeping row, or undo an applied migration, and it changes nothing about the
statement policy every statement still passes through.
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
    parser.add_argument(
        "--through",
        metavar="VERSION",
        default=None,
        help=(
            "bound the run to every pending migration UP TO AND INCLUDING this "
            "version, leaving every later one alone. Bounds --plan and --apply "
            "identically. Forward-only: this is not a rollback. An unknown "
            "version is refused, never treated as 'all' or 'none'."
        ),
    )
    args = parser.parse_args(argv)

    # THE BOUND IS VALIDATED BEFORE THE ENVIRONMENT GATE, so a typo refuses on a
    # laptop with no database configured as loudly as it does in front of the real
    # one. `load_migrations` reads and parses the committed files and touches no
    # network; `select_through` then either returns the prefix or raises.
    #
    # This loads the directory a second time (`pending_versions`/`migrate` load it
    # again with the same `through=`). That is deliberate: five small files, no
    # connection, and the alternative — threading a pre-loaded list through the
    # runner's public functions — would widen their signatures so a caller could
    # hand them migrations that are not the committed ones.
    try:
        withheld = db_migrate.select_through(db_migrate.load_migrations(), args.through)[1]
    except db_write.WriteRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3

    #: Printed after the result line whenever a bound left something out, so an
    #: operator confirms "the one I must not apply was not applied" by READING it
    #: rather than by inferring it from an absence. It is a fact about the
    #: committed file set, not about the database.
    withheld_line = (
        f"withheld by --through {args.through}: " + ", ".join(withheld)
        if withheld
        else None
    )
    #: Every bounded message says "through <version>". Unbounded output is
    #: BYTE-IDENTICAL to what this command has always printed — the packets and CI
    #: quote those strings exactly, and a bound must not silently reword them.
    suffix = f" through {args.through}" if args.through else ""

    if not db_write.database_configured(os.environ):
        print("PGHOST is not set: there is no database to migrate.", file=sys.stderr)
        return 2

    try:
        if args.apply:
            applied = db_migrate.migrate(os.environ, through=args.through)
            if applied:
                print(f"applied{suffix}: " + ", ".join(applied))
            elif args.through:
                print(
                    f"nothing to apply through {args.through} "
                    "(every migration up to it is already recorded)"
                )
            else:
                print("nothing to apply (every migration is already recorded)")
        else:
            pending = db_migrate.pending_versions(os.environ, through=args.through)
            print(f"pending{suffix}: " + (", ".join(pending) if pending else "(none)"))
        if withheld_line:
            print(withheld_line)
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
