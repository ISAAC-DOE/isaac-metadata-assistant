#!/usr/bin/env python3
"""Thin CLI wrapper around the shared reconnaissance service.

EXECUTION STATUS: **STILL UNEXECUTED.** Neither this wrapper nor the service it
calls has ever been run against any database.

WHY THIS IS NOT THE SUPPORTED PATH
----------------------------------
Under the corrected access model in ``docs/postgres-test-db-guide.md`` (lines
8-13) the database is reachable **only from the deployed pod**: the deployment
carries the libpq environment variables, and the guide is explicit that you do
not need Kubernetes access, a kubeconfig, or credentials to write code against
it — you push to ``main``, the image builds, Flux deploys, and the code runs
where the database is. The port-forward section of the guide is an optional
convenience for someone who already holds a SLAC cluster context.

Consequently this CLI is a **design / development artifact**, not the supported
way to run reconnaissance. It is also **deliberately absent from the container
image**: the Dockerfile's COPY allowlist ships exactly one file out of
``scripts/`` (``scripts/check_graphify_freshness.py``), so nothing added here
reaches the pod. The supported path is::

    GET /api/runtime/database/recon

which runs the same logic, in the pod, and returns a strictly narrower
sanitized aggregate projection.

WHAT LIVES WHERE
----------------
All reconnaissance logic — the read-only SQL guard, the redaction primitives,
the schema-vocabulary allowlist, the structural paths, the rule families, the
leak scan, every gate, the SQL constants, ``run_recon`` and
``connect_psycopg2`` — lives in ``apps/api/isaac_api/db_recon.py`` and is
imported here. **Nothing is duplicated.** This file keeps only what is
genuinely CLI-shaped: argument parsing, ``--out`` path safety, exit codes, and
``main()``.

This entry point passes ``require_opt_in=True``, so it additionally demands
``ISAAC_RUN_SLAC_DB_RECON=1`` and can never run by accident. (The HTTP endpoint
passes ``False``: the pod is never given that variable, and its documented
feature switch is ``PGHOST``.)

Output
------
JSON to stdout. ``--out PATH`` also writes a file, but only if PATH is outside
the repository or is git-ignored inside it: reconnaissance output is derived
from real production-derived records and must never drop into a committable
location. ``.gitignore`` in this repo ignores ``graphify-out/``, ``examples/*``
(except its README), ``.venv/``, ``__pycache__/``, ``*.pyc``, ``*.egg-info/``,
``.pytest_cache/``, ``node_modules/``, ``.DS_Store``, ``design-handoff/`` and
``venv/`` — there is **no** generic output directory, so the recommended target
is a path outside the repo (e.g. ``/tmp/isaac-db-recon.json``);
``examples/db-recon.json`` also qualifies.

Exit codes
----------
0 ok · 2 gate refusal · 3 leak scan aborted the run · 4 row counts changed
during the run · 5 psycopg2 not importable · 6 connection failure · 7 bad CLI
usage or unsafe ``--out`` path · 8 unexpected error.

Exit code 4 is a CONCURRENCY CHECK, not a mutation proof: a row-count equality
cannot detect an ``UPDATE`` and cannot distinguish this run's writes from a
concurrent writer's. What makes a write impossible is that the transaction is
verified read-only server-side and every statement passes a SELECT-only
allowlist before it is issued.

Usage
-----
    export PGHOST=... PGPORT=5432 PGDATABASE=metadata_assistant \
           PGUSER=metadata_assistant PGPASSWORD=...
    export ISAAC_RUN_SLAC_DB_RECON=1
    .venv/bin/python scripts/db_recon.py --out /tmp/isaac-db-recon.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

# --- sys.path wiring ----------------------------------------------------------
# Reach ``apps/api/isaac_api`` (the service module) and ``src`` (isaac_records)
# without requiring an install. Mirrors the convention in
# ``scripts/build_memory_snapshot.py``.

_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
_API_PATH = _REPO_ROOT_FOR_IMPORT / "apps" / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))
_SRC_PATH = _REPO_ROOT_FOR_IMPORT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from isaac_api.db_recon import (  # noqa: E402  (after sys.path wiring)
    DEFAULT_MAX_RECORDS,
    EXIT_UNEXPECTED_ERROR,
    RAW_ID_ENV,
    REPO_ROOT,
    ConnectionRefused,
    LeakDetected,
    MissingDependency,
    MutationDetected,
    ReconRefusal,
    UnsafeStatement,
    UsageError,
    check_env_gates,
    connect_psycopg2,
    run_recon,
    scan_for_leaks,
    string_leaves,
)

__all__ = [
    "ConnectionRefused",
    "LeakDetected",
    "MissingDependency",
    "MutationDetected",
    "ReconRefusal",
    "UnsafeStatement",
    "UsageError",
    "build_parser",
    "main",
    "validate_out_path",
]

_log = logging.getLogger("db_recon")


# --- output path safety ------------------------------------------------------


def _git_check_ignore(repo_root: Path, relative: Path) -> bool:
    """True if git reports ``relative`` as ignored. Read-only git usage."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-q", str(relative)],
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        # Cannot prove it is ignored -> treat as not ignored (fail closed).
        return False
    return proc.returncode == 0


def validate_out_path(
    raw_path: str,
    *,
    repo_root: Path = REPO_ROOT,
    git_check: Callable[[Path, Path], bool] = _git_check_ignore,
) -> Path:
    """Refuse an ``--out`` path that would drop real-derived output into git.

    Accepted: any path outside ``repo_root``, or a path inside it that git
    already ignores (e.g. ``examples/...``, which ``.gitignore`` covers via
    ``examples/*``). Anything else is refused — fail closed, because "I forgot
    to gitignore it" is exactly how sensitive output gets committed.
    """
    path = Path(raw_path).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:  # pragma: no cover - platform dependent
        raise UsageError("out_path", f"cannot resolve output path: {exc.strerror}")
    try:
        relative = resolved.relative_to(Path(repo_root).resolve())
    except ValueError:
        return resolved  # outside the repository: nothing to gitignore
    if git_check(Path(repo_root), relative):
        return resolved
    raise UsageError(
        "out_path",
        f"refusing to write inside the repository at a path git does not ignore "
        f"({relative.as_posix()}); use a path outside the repo (e.g. "
        f"/tmp/isaac-db-recon.json) or a git-ignored one (e.g. examples/db-recon.json)",
    )


# --- CLI ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db_recon.py",
        description=(
            "Read-only, fail-closed reconnaissance of the isolated app Postgres "
            "database. Emits aggregate counts and value-stripped structure only. "
            "DEV/DESIGN ARTIFACT: the supported path is GET "
            "/api/runtime/database/recon in the deployed pod; this CLI is not in "
            "the container image."
        ),
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        help=(
            "also write the JSON report to PATH. Refused unless PATH is outside "
            "the repository or git-ignored inside it."
        ),
    )
    parser.add_argument(
        "--id-salt",
        metavar="SALT",
        help=(
            "fix the record_id digest salt for reproducible output. Default: a "
            "fresh random salt per run, so digests are not linkable across runs."
        ),
    )
    parser.add_argument(
        "--emit-raw-record-ids",
        action="store_true",
        help=(
            f"emit raw record_id ULIDs. Defaults OFF and additionally requires "
            f"{RAW_ID_ENV}=1. Raw-ID safety is UNDECIDED by the project owner."
        ),
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=DEFAULT_MAX_RECORDS,
        metavar="N",
        help=f"bound on records fetched for analysis (default {DEFAULT_MAX_RECORDS}).",
    )
    parser.add_argument("--indent", type=int, default=2, metavar="N", help="JSON indent.")
    parser.add_argument(
        "--quiet", action="store_true", help="suppress progress logging on stderr."
    )
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
    connect: Optional[Callable[[Mapping[str, str]], Any]] = None,
    stdout: Any = None,
    stderr: Any = None,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    environ: Mapping[str, str] = os.environ if env is None else env
    out_stream = sys.stdout if stdout is None else stdout
    err_stream = sys.stderr if stderr is None else stderr
    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=err_stream)

    connection = None
    try:
        if args.max_records < 1:
            raise UsageError("max_records", "--max-records must be >= 1")

        if args.emit_raw_record_ids and (environ.get(RAW_ID_ENV) or "").strip() != "1":
            raise UsageError(
                "raw_ids_not_authorized",
                f"--emit-raw-record-ids additionally requires {RAW_ID_ENV}=1; raw "
                "record_id emission is not authorised by default",
            )

        out_path = validate_out_path(args.out) if args.out else None

        # Gate 7 and gate 1 before any socket is opened. The CLI always
        # requires the opt-in variable (the endpoint deliberately does not).
        check_env_gates(environ, require_opt_in=True)

        salt = args.id_salt if args.id_salt is not None else hashlib.sha256(
            os.urandom(32)
        ).hexdigest()

        opener = connect_psycopg2 if connect is None else connect
        connection = opener(environ)
        report = run_recon(
            connection,
            env=environ,
            salt=salt,
            max_records=args.max_records,
            emit_raw_record_ids=args.emit_raw_record_ids,
            require_opt_in=True,
        )
        report["records"]["record_id_digests"]["salt_mode"] = (
            "explicit" if args.id_salt is not None else "random_per_run"
        )

        payload = json.dumps(report, indent=args.indent, sort_keys=True, ensure_ascii=True)

        issues = scan_for_leaks(
            payload,
            env=environ,
            allow_raw_ids=bool(args.emit_raw_record_ids),
            leaves=string_leaves(report),
        )
        if issues:
            raise LeakDetected(issues)

        out_stream.write(payload + "\n")
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(payload + "\n", encoding="utf-8")
            # Output is derived from real production-derived records; keep it
            # owner-only rather than the 0644 default.
            os.chmod(out_path, 0o600)
        _log.info(
            "db_recon outcome=ok records=%d analyzed=%d passed=%d failed=%d signatures=%d",
            report["records"]["total"],
            report["records"]["analyzed"],
            report["validation"]["passed"],
            report["validation"]["failed"],
            report["structure"]["distinct_signature_count"],
        )
        return 0
    except ReconRefusal as exc:
        _log.info("db_recon outcome=refused gate=%s", exc.gate)
        err_stream.write(
            json.dumps(
                {"ok": False, "refused_gate": exc.gate, "reason": exc.reason},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return exc.exit_code
    except BaseException as exc:  # noqa: BLE001
        # Anything not modelled as a refusal must NOT escape as a traceback:
        # an unhandled exception bypasses the leak scan entirely and its
        # message may carry a row value, a host or a driver detail (review I3).
        # Only the exception CLASS NAME is reported — never str(exc).
        _log.info("db_recon outcome=error type=%s", type(exc).__name__)
        err_stream.write(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "reason": (
                        "an unexpected error occurred; its message is withheld "
                        "because it may contain row, connection or driver detail"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return EXIT_UNEXPECTED_ERROR
    finally:
        if connection is not None:
            closer = getattr(connection, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
