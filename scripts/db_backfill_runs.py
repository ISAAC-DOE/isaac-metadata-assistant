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

**THAT LAST CLAUSE WAS FALSE UNTIL 2026-08-24, AND IT IS CORRECTED IN PLACE RATHER
THAN QUIETLY REWORDED.** An independent review measured it: ``persist`` reached
``_stamp_projection``, which hard-coded ``PROJECTOR_WRITE_PATH`` at the ONE call site
of ``Q_UPSERT_RUN_PROJECTION``, so every row this script wrote claimed the ordinary
application write path had produced it. ``grep -rn "'backfill'"`` over
``apps/api/isaac_api/``, ``scripts/`` and ``src/`` returned exactly one hit — this
docstring, asserting the behaviour. The value was declared by ``0005``'s CHECK,
indexed first by ``0005``'s index, and grouped on by the packet's own Stage-2b query,
and it could never appear in the table. The fix is a keyword argument threaded
through ``persist`` (default ``write-path``, so no ordinary save changed), and
``apps/api/tests/test_db_backfill_runs.py`` now asserts the PARAMETER TUPLE this
script causes rather than trusting this paragraph.

WHAT IT DOES NOT DO, and each of these is a decision
----------------------------------------------------
* **It does not touch** ``records``. The write path's statement policy refuses any
  statement naming it, by identifier, in any position.
* **It writes no SQL of its own.** Every statement it causes is a module-level
  ``Q_*`` constant in ``experiment_repository``. There is no SQL text in this file.
* **It does not move a reader.** Stage 2b is a separate reviewed slice. A completed
  backfill is its *precondition*, not its trigger.
* **It does not repair a run's ``experiment_id``.** A run whose document carries
  ``experiment_id: ""`` is projected exactly as it is —
  ``workspace._hydrate_runs`` documents why repairing on read is refused, and a
  backfill that repaired that field would change every record's authoritative
  signature and bump ``rev`` across the workspace irreversibly.

  **BUT IT CAN REWRITE A DOCUMENT, and the earlier flat claim "it does not repair a
  document" was too strong.** An independent review measured this. A document written
  by ``persist`` round-trips ``from_state`` → ``to_state`` byte-identically, so the
  compare-and-swap's third clause (*state identical*) accepts and nothing changes —
  which is the normal case and is genuinely a no-op. A **legacy-shaped or
  out-of-band** row does not round-trip: ``from_state`` synthesises ``generation``,
  ``rev: 0``, ``updated_utc`` and ``record_id: null``, and ``persist`` then writes the
  normalised document back.

  That population is the same one this script exists for, so it is not a corner case
  to wave at. It is left as it is rather than guarded, because the normalisation is
  what ``load_experiment`` already returns to every reader — a row this script left
  un-normalised would still be normalised the next time anything read it — and
  because refusing to project exactly the rows that most need projecting would defeat
  the purpose. **What is claimed is narrower and true: no scientific value is
  changed.**
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

``--dry-run`` is the default and opens a connection for READS ONLY. It reports how many
experiments the table holds, how many it could not read, how many carry at least one run,
and how many runs there are to project. It issues no write.

**It does NOT report how many carry a matching claim.** An earlier version of this
paragraph said it did, which is the same false claim the gate paragraph below corrects:
this script never reads ``isaac_run_projection``, so it cannot know. ``--apply`` performs
the projection.

**THE STAGE-2B GATE IS NOT REPORTED BY THIS SCRIPT, and an earlier version of this
docstring said it was.** It claimed the gate was ``never_projected: 0`` and
``stale: 0`` "in a ``--dry-run`` report" — words this script does not print and cannot
compute, because it deliberately never reads ``isaac_run_projection``. An independent
review measured that: the string ``never_projected`` appears in no print statement
anywhere in the repository.

The gate is a query the OPERATOR runs, given in
``docs/migration-approval-packet-0005.md`` §8A. What this script contributes is the
work that makes the answer be zero, plus the counts that say whether it did all of it:
``experiments UNREADABLE``, ``refused`` and ``failed`` must every one be **0**, or some
experiment was not projected and the gate query is being asked about an incomplete pass.
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
    # `--dry-run` IS ACCEPTED AND IS A NO-OP, because four committed documents tell an
    # operator to type it and the first version of this script answered
    # `error: unrecognized arguments: --dry-run`, exit 2 — measured by an independent
    # review. Correcting four documents to say "omit the flag" was the alternative and
    # is worse: an operator reaching for the safe invocation should not be punished for
    # naming it, and a flag that means "do the default" cannot be dangerous.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only and write nothing. This is the default; the flag is accepted "
        "so the documented invocation works.",
    )
    args = parser.parse_args(argv)
    if args.dry_run and args.apply:
        parser.error("--dry-run and --apply contradict each other; pass one or neither")
    return args


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

    experiments, unreadable = store.stored_experiments()
    total = len(experiments)
    print(f"experiments readable: {total}")
    if unreadable:
        # NAMED, NOT SILENT. A pass that could not read part of the table must not
        # look complete — and this count is the one figure that decides whether the
        # Stage-2b query below can be trusted at all.
        print(f"experiments UNREADABLE (skipped, not projected): {unreadable}")

    if not args.apply:
        # REPORT ONLY, AND IT DELIBERATELY DOES NOT READ `isaac_run_projection`.
        # This application has no statement that reads that table, and adding one
        # here would make this file its first reader — which is exactly the Stage-2b
        # decision this script is a precondition for rather than a part of, and would
        # break the property `test_0005_is_written_by_the_write_path_and_read_by_nothing`
        # measures. So the dry run reports what the DOCUMENTS say.
        #
        # THE CONSEQUENCE, STATED BECAUSE IT WAS PREVIOUSLY MISSTATED: this script
        # CANNOT report `never_projected` or `stale`. Four committed documents once
        # described the Stage-2b gate as "the backfill reported never_projected: 0",
        # and an independent review measured that no print statement anywhere emits
        # that word. The gate is now a SQL query the operator runs — see the packet's
        # section 8A — and this script's job is to make the answer be zero, not to
        # report it.
        with_runs = sum(1 for exp in experiments if exp.runs)
        print(f"experiments with at least one run: {with_runs}")
        print(f"runs to project: {sum(len(exp.sorted_runs()) for exp in experiments)}")
        print("dry run: nothing was written. Re-run with --apply.")
        return 4 if unreadable else 0

    persisted = 0
    runs_in_persisted = 0
    refused = 0
    failed = 0
    for exp in experiments:
        try:
            # THE SAME METHOD THE APPLICATION USES, not a copy of it. `persist`
            # carries the tutorial refusal, the accepted gate, the run-row diff and
            # the completeness stamp; a second projector would be a second thing to
            # keep correct.
            #
            # `projector=` IS THE ONLY THING THIS CALL SAYS THAT AN ORDINARY SAVE DOES
            # NOT, and it is the whole of the fix for the false claim corrected in this
            # file's docstring. It is a keyword argument rather than a second write
            # path deliberately: `_stamp_projection`'s own docstring forbids a second
            # writer, because `isaac_run_projection` has no `session_id` column and can
            # never gain one, so a worked-example claim that ever reached that table
            # would be permanently uncleanable. Passing a label keeps every one of the
            # guards this call inherits.
            store.persist(exp, projector=repo.PROJECTOR_BACKFILL)
        except repo.DurableWriteConflict:
            # Another writer holds a newer document. Its own save projected its own
            # rows, so this experiment is not left behind — it is simply not ours to
            # project. Counted rather than swallowed.
            refused += 1
            continue
        except Exception:  # noqa: BLE001 - any storage failure, per experiment
            # ONE FAILING EXPERIMENT MUST NOT END THE PASS, for `stored_experiments`'
            # reason: the alternative is that everything after it goes unprojected and
            # the operator has to guess where it stopped. Counted, and the exit code
            # reflects it.
            failed += 1
            continue
        persisted += 1
        runs_in_persisted += len(exp.sorted_runs())

    # ── WHAT THESE COUNTS ARE, STATED PRECISELY, BECAUSE THE FIRST VERSION OVERSTATED
    # ── THEM AND AN INDEPENDENT REVIEW MEASURED IT. ─────────────────────────────────
    # They were printed as `projected:` and `runs written:` — both of which claim
    # something about the DATABASE. They are not: they count `persist` calls that
    # returned without raising, and the runs those documents held. On a deployment
    # where `isaac_runs` is absent, `persist` succeeds and writes NO run row, so
    # "runs written: 2" was printed over a table that received nothing. This
    # repository's own rule is "never report a count you did not just measure", and
    # the honest names are the ones below.
    print(f"experiments persisted without error: {persisted}")
    print(f"runs held by those documents: {runs_in_persisted}")
    print(f"refused (a newer writer won): {refused}")
    print(f"failed (storage error): {failed}")

    # ── WHETHER A ROW OR A CLAIM WAS ACTUALLY WRITTEN IS A SEPARATE QUESTION, and it
    # ── is answered from the process's own observations, not assumed. ───────────────
    # `run_table_seen()` / `projection_table_seen()` report whether THIS PROCESS
    # confirmed each relation exists. The first version read only the second one and
    # named the wrong table in its remedy: `PROJECTION_TABLE` is probed only INSIDE
    # the branch where `RUN_TABLE` is present, so an absent `isaac_runs` leaves the
    # projection unprobed and the old message told the operator to apply `0005` when
    # the missing migration was `0002`. It also fired on an empty database with `0005`
    # applied, because nothing had been probed at all.
    status = 0
    if persisted == 0:
        print(
            "note: no experiment was persisted, so nothing was probed and nothing "
            "was written. This is the expected output for an empty database.",
            file=sys.stderr,
        )
    elif not repo.run_table_seen():
        print(
            "WARNING: isaac_runs was NOT present, so no run row and no completeness "
            "claim was written. Apply 0002_runs first. The experiment documents were "
            "rewritten and are unharmed.",
            file=sys.stderr,
        )
        status = 3
    elif not repo.projection_table_seen():
        print(
            "WARNING: isaac_runs was present and its rows were maintained, but "
            "isaac_run_projection was NOT present, so NO completeness claim was "
            "recorded. Apply 0005_run_projection first.",
            file=sys.stderr,
        )
        status = 3
    if failed or unreadable:
        status = status or 4
    return status


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
