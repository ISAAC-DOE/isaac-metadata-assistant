#!/usr/bin/env python3
"""Project every experiment's runs into ``isaac_runs`` and stamp the completeness claim.

EXECUTION STATUS: **NEVER EXECUTED, ANYWHERE.** No agent has run this against any
database, and no agent may: connecting to the SLAC database from a laptop or from
CI is refused by
``docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52``, and
``CLAUDE.md`` §15's hard stop makes applying or driving a migration the operator's
act. This file exists so the operator's step is a reviewed, readable artifact
rather than an improvised SQL session.

IT IS DELIBERATELY ABSENT FROM THE CONTAINER IMAGE, exactly as ``db_recon.py`` is:
the Dockerfile's COPY allowlist ships one file out of ``scripts/``
(``check_graphify_freshness.py``), so no application route can reach this, and
``test_the_backfill_is_not_in_the_image`` asserts it.

WHY A BACKFILL IS NEEDED AT ALL
-------------------------------
``0005_run_projection`` records a claim; it does not make one. Every experiment
persisted before the shadow write shipped — and every experiment saved in the
window between a merge and the operator applying ``0002`` — is **NEVER
PROJECTED**: no projection row, and possibly no run rows either. That state is
correct and is handled by falling back to the experiment document, which remains
authoritative. What it is NOT is a state a read cutover can be measured against:
until every experiment is either COMPLETE or knowably absent, "the rows are
usable" is not a statement anybody can make about the deployment.

So this walks ``isaac_experiments``, re-persists each experiment through the SAME
code path the write uses, and stamps ``projector: 'backfill'``.

WHAT IT DOES NOT DO, and each of these is a decision
----------------------------------------------------
* **It does not touch** ``records``. The write path's statement policy refuses any
  statement naming it, by identifier, in any position.
* **It writes no SQL of its own.** Every statement it causes is a module-level
  ``Q_*`` constant in ``experiment_repository``. There is no SQL text in this file.
* **It does not move a reader.** Stage 2b is a separate reviewed slice. A completed
  backfill is its *precondition*, not its trigger.
* **It does not repair a document.** A run whose document carries
  ``experiment_id: ""`` is projected exactly as it is —
  ``workspace._hydrate_runs`` documents why repairing on read is refused, and a
  backfill that repaired would change every record's authoritative signature and
  bump ``rev`` across the workspace irreversibly.
* **It does not delete.** The only ``DELETE`` it can cause is the write path's own
  ``Q_DELETE_ABSENT_RUNS``, which removes run rows the document no longer names —
  which is the projection being correct, not the backfill being destructive.

IDEMPOTENT, AND IN A SPECIFIC SENSE
-----------------------------------
Re-running it re-projects and re-stamps to the same values. It does NOT skip an
experiment that already carries a matching claim, and that is deliberate: a
"skip if COMPLETE" fast path would trust the very claim the backfill exists to
establish, so a claim that was wrong would be permanent. The cost is one
transaction per experiment on every run; the benefit is that a re-run is a
verification and not merely a no-op.

WHAT IT PRINTS
--------------
Counts only. No record id, no title, no scientific value, no document — the same
rule ``db_recon.py`` follows, for the same reason: this may be run by an operator
against a database seeded with production-derived records.

    $ python scripts/db_backfill_runs.py --dry-run
    $ python scripts/db_backfill_runs.py --apply

``--dry-run`` is the default and opens a connection for READS ONLY: it reports how
many experiments exist, how many carry a matching claim, and how many do not. It
issues no write. ``--apply`` performs the projection.

THE STAGE-2B GATE is ``never_projected: 0`` **and** ``stale: 0`` in a ``--dry-run``
report taken AFTER an ``--apply``. Anything else means some experiment's rows are
not known-good, and a reader switched on in that state would be guessing.
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "apps", "api"))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="db_backfill_runs.py",
        description=(
            "Project every experiment's runs into isaac_runs and stamp the "
            "per-experiment completeness claim. Reports counts only."
        ),
    )
    # `--apply` rather than `--dry-run`, so the DEFAULT is the harmless one. A flag
    # whose absence writes is a flag somebody forgets.
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the projection. Without it, report only and write nothing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # IMPORTED INSIDE `main`, so `--help` works on a machine with no psycopg2 and so
    # importing this module for a test cannot open anything.
    import isaac_api.experiment_repository as repo

    store = repo.ordinary_store()
    if store is None or not isinstance(store, repo.PostgresOrdinaryStore):
        print(
            "no durable store: PGHOST is unset, so the repository is the filesystem "
            "fallback and there is nothing to project.",
            file=sys.stderr,
        )
        return 2

    experiments = store.stored_experiments()
    total = len(experiments)
    print(f"experiments: {total}")

    if not args.apply:
        # REPORT ONLY. Deliberately NOT a read of `isaac_run_projection`: this
        # application has no statement that reads that table and adding one here
        # would make this file the first reader of it — which is exactly the Stage-2b
        # decision this script is a precondition for, not a part of. So the dry run
        # reports what it can see from the documents alone.
        with_runs = sum(1 for exp in experiments if exp.runs)
        print(f"experiments with at least one run: {with_runs}")
        print(f"runs to project: {sum(len(exp.sorted_runs()) for exp in experiments)}")
        print("dry run: nothing was written. Re-run with --apply.")
        return 0

    projected = 0
    runs = 0
    refused = 0
    for exp in experiments:
        try:
            # THE SAME METHOD THE APPLICATION USES, not a copy of it. `persist`
            # carries the tutorial refusal, the accepted gate, the run-row diff and
            # the completeness stamp; a second projector would be a second thing to
            # keep correct.
            store.persist(exp)
        except repo.DurableWriteConflict:
            # Another writer holds a newer document. Its own save projected its own
            # rows, so this experiment is not left behind — it is simply not ours to
            # project. Counted rather than swallowed.
            refused += 1
            continue
        projected += 1
        runs += len(exp.sorted_runs())

    print(f"projected: {projected}")
    print(f"runs written: {runs}")
    print(f"refused (a newer writer won): {refused}")
    if not repo.projection_table_seen():
        # SAID OUT LOUD, because the rows would be correct and the CLAIM absent, and
        # a silent success there is the one outcome that would mislead the operator
        # into thinking the Stage-2b gate had been met.
        print(
            "WARNING: isaac_run_projection was not present, so run rows were "
            "maintained but NO completeness claim was recorded. Apply "
            "0005_run_projection first.",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
