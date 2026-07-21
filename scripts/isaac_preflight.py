#!/usr/bin/env python3
"""Deterministic first-push preflight for ISAAC (R4.3).

PURPOSE
-------
Prevent *predictable* failed pushes — the class of failure exemplified by commit
``a0446fe``, which pushed committed-snapshot drift that CI only caught afterward.
This tool runs the exact checks CI (and the Shared Repository Synchronization
Contract) will enforce, *before* a push, and exits non-zero if any would fail.
``/isaac-checkpoint`` invokes it on its push path and REFUSES to push on a
non-zero exit.

DESIGN CONTRACT
---------------
* **Python, not shell** — for strict, testable return-code handling. Every
  subprocess is run via :func:`subprocess.run` with an explicit return-code
  check. NO failure may be hidden behind ``tail`` / ``head`` / ``grep`` / ``tee``
  or any pipeline. The first failing check is reported with a clear message; all
  checks are aggregated and the process exits non-zero if ANY failed.
* **Never pushes.** This tool only *inspects*. It runs a read-only
  ``git fetch --prune origin`` (skippable) and never mutates the working tree,
  the index, refs, or any remote.
* **Scans what the push will actually deliver.** The secret/filename/leak scans
  cover files changed in the working tree AND in commits ahead of ``origin/main``
  (``origin/main...HEAD``). ``/isaac-checkpoint`` typically runs with a CLEAN tree
  and the changes already committed ahead of the remote, so a working-tree-only
  scan would inspect nothing at the moment that matters — ahead-commit content is
  read from the committed blob at ``HEAD``. Enumeration/read errors FAIL closed.
* **Never regenerates the snapshot.** The committed-snapshot check runs the
  generator in ``--check`` mode ONLY (which writes nothing). If it drifts, the
  preflight FAILS and tells the human to regenerate deliberately — it never
  silently regenerates on the push path.
* **The committed-snapshot ``--check`` and its CI gate test run UNCONDITIONALLY
  in EVERY mode.** Snapshot relevance is never inferred from which filenames
  changed (that inference is exactly how ``a0446fe`` slipped through). Docs,
  frontend, backend, and full all run them.

MODES
-----
``docs`` / ``frontend`` / ``backend`` / ``full`` differ ONLY in the advisory
build/test reminders they print. The hard gates (repo identity, branch, remote
divergence, secret/junk file rejection, content leak scan, snapshot ``--check``,
snapshot CI gate test) are identical in all four.

CLI
---
::

    python scripts/isaac_preflight.py MODE [--repo-root .] [--skip-fetch]

Exit code: ``0`` only when every gate passed; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# --- exit codes ---------------------------------------------------------------

EXIT_OK = 0
EXIT_FAIL = 1

MODES = ("docs", "frontend", "backend", "full")

# --- repository identity ------------------------------------------------------

#: Repo-relative marker proving this is the ISAAC checkout (the vendored official
#: schema; mirrors how ``isaac_api.memory._find_repo_root`` anchors the root).
_REPO_MARKER = Path("schema") / "isaac_record_v1.json"
#: The ``origin`` URL must contain this — the Krish-owned ISAAC GitHub project
#: (see the Shared Repository Synchronization Contract; identities stay fixed).
_EXPECTED_REMOTE_SUBSTR = "isaac-metadata-assistant"
_EXPECTED_BRANCH = "main"

# --- snapshot preflight locations (CLAUDE.md §17) -----------------------------

_SNAPSHOT_REL = Path("apps") / "api" / "isaac_api" / "data" / "memory-snapshot.json"
_GRAPH_DIR_REL = Path("graphify-out")
_SNAPSHOT_BUILDER_REL = Path("scripts") / "build_memory_snapshot.py"
_GATE_TEST_REL = "apps/api/tests/test_committed_snapshot.py"

# --- secret-like / junk filename rejection ------------------------------------
#
# PATH-SHAPE rules on the repo-relative POSIX path of any changed/added/untracked
# file. A match aborts the push: these files must never be pushed.

_SECRET_NAME_RE = re.compile(
    r"(^|/)\.env($|\.)"                       # .env, .env.local, .env.production
    r"|\.pem$"                                # PEM private key / cert bundle
    r"|\.key$"                                # raw private key
    r"|\.(p12|pfx|keystore|jks)$"             # keystores
    r"|(^|/)id_(rsa|dsa|ecdsa|ed25519)$"      # SSH private keys
    r"|(^|/)\.npmrc$|(^|/)\.pypirc$"          # registry auth files
    r"|(^|/)\.netrc$|(^|/)credentials$"       # netrc / cloud credential files
    r"|\.p8$",                                # Apple auth key
    re.IGNORECASE,
)

_JUNK_NAME_RE = re.compile(
    r"(^|/)\.DS_Store$"
    r"|\.log$|\.tmp$|\.swp$|\.orig$|\.bak$|\.rej$"
    r"|\.py[co]$|(^|/)__pycache__/",
    re.IGNORECASE,
)

# --- content leak scan (credential-shaped tokens in changed file bytes) -------
# Same shapes the snapshot generator's secret scan uses, applied to the CONTENTS
# of changed/added text files (never binaries, size-capped).

_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----")
_CREDENTIAL_RE = re.compile(
    r"AKIA[0-9A-Z]{16}"        # AWS access key id
    r"|sk-[A-Za-z0-9]{16,}"    # generic secret-key-shaped token
    r"|ghp_[A-Za-z0-9]{20,}"   # GitHub personal access token
    r"|xox[bp]-[A-Za-z0-9-]+"  # Slack bot/user token
)
_MAX_SCAN_BYTES = 2 * 1024 * 1024  # skip files larger than 2 MiB


# --- result model -------------------------------------------------------------


@dataclass
class CheckResult:
    """One preflight check outcome.

    ``severity`` is one of ``"pass"``, ``"fail"``, ``"info"``, ``"warn"``. Only
    ``"fail"`` makes the overall preflight exit non-zero; ``info``/``warn`` are
    reported but never mask or cause a failure."""

    name: str
    severity: str
    detail: str = ""
    lines: list = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.severity == "fail"


def _passed(name: str, detail: str = "", lines=None) -> CheckResult:
    return CheckResult(name, "pass", detail, list(lines or []))


def _failed(name: str, detail: str = "", lines=None) -> CheckResult:
    return CheckResult(name, "fail", detail, list(lines or []))


def _info(name: str, detail: str = "", lines=None) -> CheckResult:
    return CheckResult(name, "info", detail, list(lines or []))


# --- git helpers --------------------------------------------------------------


def _git(repo_root, *args) -> subprocess.CompletedProcess:
    """Run a git subcommand under ``repo_root`` capturing output. NEVER pipes
    through tail/head/grep — the caller inspects ``returncode`` explicitly."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
    )


def _git_show_bytes(repo_root, spec: str):
    """Return ``(blob_bytes, error)`` for ``git show <spec>`` (e.g.
    ``HEAD:path/to/file``). Bytes (not text) so binary/NUL detection works.
    ``error`` is a non-empty string on failure (caller FAILs closed)."""
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", spec],
        capture_output=True,
    )
    if proc.returncode != 0:
        return None, proc.stderr.decode("utf-8", "replace").strip()
    return proc.stdout, None


def _venv_python(repo_root) -> str:
    """Prefer the project venv interpreter; fall back to the current one."""
    candidate = Path(repo_root) / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


def ahead_commit_files(repo_root):
    """Return ``(paths, error)`` — files changed (deletions EXCLUDED via
    ``--diff-filter=d``) in commits AHEAD of ``origin/main`` (``origin/main...HEAD``).

    These are delivered by a push even when the working tree is CLEAN — the exact
    case ``/isaac-checkpoint`` runs in (changes already committed, tree clean). The
    working-tree-only ``git status`` scan would inspect nothing at that moment, so
    the secret/leak defense must also cover this set.

    Fail-closed: on any git error (e.g. ``origin/main`` unresolvable) return
    ``([], "<message>")`` so the caller turns it into a FAIL — never a silent pass.
    ``-z`` yields NUL-terminated, unquoted repo-relative POSIX paths."""
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--name-only",
         "--diff-filter=d", "-z", "origin/main...HEAD"],
        capture_output=True,
    )
    if proc.returncode != 0:
        return [], (
            "cannot enumerate files ahead of origin/main (origin/main...HEAD): "
            + proc.stderr.decode("utf-8", "replace").strip()
        )
    out = proc.stdout.decode("utf-8", "surrogateescape")
    return [p for p in out.split("\0") if p], None


# --- individual checks --------------------------------------------------------


def check_repo_identity(repo_root) -> CheckResult:
    """Confirm this is the ISAAC repo (marker file present) and ``origin`` points
    at the expected Krish-owned ISAAC project. A wrong repo/remote is a hard
    stop (never push into an unexpected target)."""
    repo_root = Path(repo_root)
    marker = repo_root / _REPO_MARKER
    if not marker.is_file():
        return _failed(
            "repo-identity",
            f"expected ISAAC marker not found: {_REPO_MARKER} (wrong repository?)",
        )
    proc = _git(repo_root, "remote", "get-url", "origin")
    if proc.returncode != 0:
        return _failed("repo-identity", f"cannot read origin remote: {proc.stderr.strip()}")
    url = proc.stdout.strip()
    if _EXPECTED_REMOTE_SUBSTR not in url:
        return _failed(
            "repo-identity",
            f"origin {url!r} does not match expected ISAAC project "
            f"(contains {_EXPECTED_REMOTE_SUBSTR!r})",
        )
    return _passed("repo-identity", f"origin={url}")


def check_branch(repo_root) -> CheckResult:
    """Confirm the current branch is ``main`` (the deployment branch)."""
    proc = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if proc.returncode != 0:
        return _failed("branch", f"cannot resolve current branch: {proc.stderr.strip()}")
    branch = proc.stdout.strip()
    if branch != _EXPECTED_BRANCH:
        return _failed("branch", f"on {branch!r}, expected {_EXPECTED_BRANCH!r}")
    return _passed("branch", branch)


def fetch_origin(repo_root, *, skip: bool) -> CheckResult:
    """Read-only ``git fetch --prune origin``. Skippable (``--skip-fetch`` / test
    / offline). A real preflight cannot verify remote state without it, so a
    fetch FAILURE (when not skipped) is a hard failure; skipping is reported as
    info (the divergence check then uses the existing ``origin/main`` ref)."""
    if skip:
        return _info("fetch", "skipped (--skip-fetch); using existing origin/main ref")
    proc = _git(repo_root, "fetch", "--prune", "origin")
    if proc.returncode != 0:
        return _failed(
            "fetch",
            f"git fetch --prune origin failed (cannot verify remote state before "
            f"push): {proc.stderr.strip()}",
        )
    return _passed("fetch", "fetched origin (prune)")


def check_divergence(repo_root) -> CheckResult:
    """Detect remote advancement / divergence via
    ``git rev-list --left-right --count HEAD...origin/main``.

    * diverged (ahead>0 AND behind>0) → FAIL (never force/merge/rebase to push)
    * behind>0 (remote advanced) → FAIL (fast-forward-only pull required first)
    * ahead-only or 0/0 → PASS (a normal fast-forward push, or nothing to push)

    If ``origin/main`` cannot be resolved, FAIL — remote state is unverifiable."""
    proc = _git(repo_root, "rev-list", "--left-right", "--count", "HEAD...origin/main")
    if proc.returncode != 0:
        return _failed(
            "divergence",
            f"cannot resolve HEAD...origin/main (no origin/main ref?): "
            f"{proc.stderr.strip()}",
        )
    parts = proc.stdout.split()
    if len(parts) != 2 or not all(p.lstrip("-").isdigit() for p in parts):
        return _failed("divergence", f"unexpected rev-list output: {proc.stdout.strip()!r}")
    ahead, behind = int(parts[0]), int(parts[1])
    if ahead > 0 and behind > 0:
        return _failed(
            "divergence",
            f"DIVERGED: {ahead} ahead / {behind} behind origin/main — human "
            f"decision required (no auto merge/rebase/reset/force)",
        )
    if behind > 0:
        return _failed(
            "divergence",
            f"REMOTE_ADVANCED: {behind} behind origin/main — fast-forward-only "
            f"pull required before pushing",
        )
    return _passed("divergence", f"{ahead} ahead / {behind} behind origin/main")


def collect_changes(repo_root) -> list:
    """Return ``[(index_char, worktree_char, path), ...]`` for every changed and
    untracked file, via NUL-delimited ``git status --porcelain=v1 -z`` (unquoted
    literal repo-relative POSIX paths). Rename/copy source tokens are consumed."""
    proc = _git(repo_root, "status", "--porcelain=v1", "-z")
    if proc.returncode != 0:
        raise RuntimeError(f"git status failed: {proc.stderr.strip()}")
    tokens = proc.stdout.split("\0")
    changes: list = []
    it = iter(tokens)
    for tok in it:
        if not tok:
            continue
        if len(tok) < 3:
            continue
        index_char, worktree_char, path = tok[0], tok[1], tok[3:]
        if "R" in (index_char, worktree_char) or "C" in (index_char, worktree_char):
            # rename/copy: the NEXT token is the source path — consume it.
            next(it, None)
        changes.append((index_char, worktree_char, path))
    return changes


def display_changes(changes, ahead_paths=()) -> CheckResult:
    """Informational: list working-tree changes + files carried by ahead-of-origin
    commits (both are delivered by a push). Never a failure."""
    lines = []
    for index_char, worktree_char, path in changes:
        staged = index_char not in (" ", "?")
        tag = "staged" if staged else ("untracked" if index_char == "?" else "unstaged")
        lines.append(f"[{index_char}{worktree_char}] {tag:9s} {path}")
    for path in ahead_paths:
        lines.append(f"[  ] ahead-cmt {path}")
    if not lines:
        return _info("changed-files", "working tree clean; nothing ahead of origin/main")
    return _info(
        "changed-files",
        f"{len(changes)} working-tree change(s), {len(ahead_paths)} ahead-commit file(s)",
        lines,
    )


def scan_changed_filenames(paths) -> CheckResult:
    """Reject secret-like and obviously-unrelated (junk) filenames among the
    delivered file set — the union of working-tree/untracked changes AND files
    changed in commits ahead of ``origin/main`` (``paths`` is already that
    de-duplicated union). Any match is a hard failure — these must never push."""
    secret_hits = []
    junk_hits = []
    for path in paths:
        if _SECRET_NAME_RE.search(path):
            secret_hits.append(path)
        elif _JUNK_NAME_RE.search(path):
            junk_hits.append(path)
    if secret_hits or junk_hits:
        lines = [f"secret-like: {p}" for p in secret_hits] + [
            f"unrelated/junk: {p}" for p in junk_hits
        ]
        return _failed(
            "filename-scan",
            f"{len(secret_hits)} secret-like, {len(junk_hits)} junk file(s) must "
            f"not be pushed",
            lines,
        )
    return _passed(
        "filename-scan", "no secret-like or junk filenames among delivered files"
    )


def _scan_bytes_for_leaks(data: bytes, label: str, hits: list) -> None:
    """Append credential-shaped-token findings for ``label`` to ``hits``. Skips
    binaries (NUL byte). ``data`` is assumed already size-capped by the caller."""
    if b"\0" in data:
        return  # binary
    text = data.decode("utf-8", "replace")
    if _PRIVATE_KEY_RE.search(text):
        hits.append(f"{label}: private-key header")
    if _CREDENTIAL_RE.search(text):
        hits.append(f"{label}: credential-shaped token")


def content_leak_scan(repo_root, changes, ahead_paths=()) -> CheckResult:
    """Scan the CONTENT that a push will actually deliver for credential-shaped
    tokens (private-key headers, AWS/GitHub/Slack tokens, generic ``sk-`` secrets):

    * **Working-tree changes** (``changes`` from ``git status``): read from disk.
    * **Ahead-of-origin commits** (``ahead_paths``): read the COMMITTED blob at
      ``HEAD`` via ``git show HEAD:<path>`` — because at push time the tree is
      typically clean and the secret lives only in a commit, not on the worktree
      delta. A path present in both sets is scanned in both forms.

    Skips deleted files, binaries (NUL byte), and content over the size cap.
    **Fail-closed:** if a committed ahead-blob cannot be read (unexpected, since
    deletions are excluded upstream), that is a FAILURE, never a silent skip."""
    repo_root = Path(repo_root)
    hits: list = []
    errors: list = []

    # (1) working-tree changed/untracked files — current on-disk bytes.
    for index_char, worktree_char, path in changes:
        if "D" in (index_char, worktree_char):
            continue  # deleted; nothing on disk to scan
        fpath = repo_root / path
        try:
            if not fpath.is_file() or fpath.stat().st_size > _MAX_SCAN_BYTES:
                continue
            data = fpath.read_bytes()
        except OSError:
            continue
        _scan_bytes_for_leaks(data, f"{path} (working tree)", hits)

    # (2) files carried by ahead-of-origin commits — the COMMITTED blob at HEAD.
    for path in ahead_paths:
        blob, err = _git_show_bytes(repo_root, f"HEAD:{path}")
        if err is not None or blob is None:
            errors.append(
                f"{path} (ahead-commit): cannot read committed blob (fail-closed): "
                f"{err or 'no output'}"
            )
            continue
        if len(blob) > _MAX_SCAN_BYTES:
            continue
        _scan_bytes_for_leaks(blob, f"{path} (ahead-commit HEAD)", hits)

    if errors or hits:
        detail = f"{len(hits)} leak(s) in delivered files"
        if errors:
            detail += f"; {len(errors)} unreadable ahead-commit blob(s) (fail-closed)"
        return _failed("content-leak-scan", detail, hits + errors)
    return _passed(
        "content-leak-scan", "no credential-shaped tokens in delivered files"
    )


def snapshot_check_command(
    repo_root, *, graph_dir=None, out_path=None, snapshot_repo_root=None, python=None
) -> list:
    """Build the committed-snapshot ``--check`` command. Exposed so tests can
    assert ``--check`` is present and that no regeneration variant is ever
    constructed on this path. ``snapshot_repo_root`` anchors the generator's
    ``--repo-root`` (defaults to ``repo_root``; tests point it at a fixture
    served-root)."""
    repo_root = Path(repo_root)
    python = python or _venv_python(repo_root)
    builder = repo_root / _SNAPSHOT_BUILDER_REL
    graph_dir = Path(graph_dir) if graph_dir is not None else repo_root / _GRAPH_DIR_REL
    out_path = Path(out_path) if out_path is not None else repo_root / _SNAPSHOT_REL
    snapshot_repo_root = (
        Path(snapshot_repo_root) if snapshot_repo_root is not None else repo_root
    )
    return [
        python,
        str(builder),
        "--graph-dir",
        str(graph_dir),
        "--out",
        str(out_path),
        "--repo-root",
        str(snapshot_repo_root),
        "--check",  # NEVER dropped on this path — check-only, writes nothing
    ]


def run_snapshot_check(
    repo_root, *, graph_dir=None, out_path=None, snapshot_repo_root=None, python=None
) -> CheckResult:
    """Run the committed-snapshot drift check UNCONDITIONALLY in ``--check`` mode.
    Never regenerates: on drift it FAILS and instructs the human to regenerate
    deliberately (CLAUDE.md §17), rather than mutating the snapshot on a push
    path. Exit 0 from the generator is required to pass."""
    cmd = snapshot_check_command(
        repo_root, graph_dir=graph_dir, out_path=out_path,
        snapshot_repo_root=snapshot_repo_root, python=python,
    )
    assert "--check" in cmd, "snapshot check must run in --check mode (never regenerate)"
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr.strip() or proc.stdout.strip() or "non-zero exit")
        return _failed(
            "snapshot-check",
            f"committed-snapshot drift or error (exit {proc.returncode}). Regenerate "
            f"deliberately with build_memory_snapshot.py (no --check), then re-run. "
            f"Detail: {detail}",
        )
    return _passed("snapshot-check", proc.stdout.strip() or "no drift")


def run_gate_test(repo_root, *, python=None) -> CheckResult:
    """Run the committed-snapshot CI gate test UNCONDITIONALLY (same test CI runs
    over the shipped artifact). Any non-zero pytest exit fails the preflight."""
    repo_root = Path(repo_root)
    python = python or _venv_python(repo_root)
    cmd = [python, "-m", "pytest", _GATE_TEST_REL, "-q"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if proc.returncode != 0:
        tail = (proc.stdout.strip().splitlines() or ["(no output)"])[-15:]
        return _failed(
            "snapshot-gate-test",
            f"pytest {_GATE_TEST_REL} failed (exit {proc.returncode})",
            tail,
        )
    return _passed("snapshot-gate-test", (proc.stdout.strip().splitlines() or [""])[-1])


def mode_reminders(mode: str) -> list:
    """Advisory (info) reminders per mode. These never gate the push — the hard
    gates are identical across all modes."""
    reminders = {
        "docs": [
            "docs: verify manifest-listed docs regenerated the snapshot (already "
            "gated above); check markdown links/paths.",
        ],
        "frontend": [
            "frontend: run the Vite build and the web unit tests before pushing "
            "(apps/web) — not gated here.",
        ],
        "backend": [
            "backend: run the full backend test suite (.venv/bin/pytest) and any "
            "typecheck before pushing — not gated here.",
        ],
        "full": [
            "full: run .venv/bin/pytest (all), the Vite build, and typecheck; "
            "confirm CI/Vercel/Railway axes separately after push — not gated here.",
        ],
    }
    return [_info(f"reminder:{mode}", r) for r in reminders.get(mode, [])]


# --- runner -------------------------------------------------------------------


def run_preflight(repo_root, mode: str, *, skip_fetch: bool = False) -> list:
    """Run every gate, aggregate, and return the ordered list of results. The
    committed-snapshot ``--check`` and its gate test run in EVERY mode; snapshot
    relevance is never inferred from filenames."""
    repo_root = Path(repo_root).resolve()
    results: list = [
        check_repo_identity(repo_root),
        check_branch(repo_root),
        fetch_origin(repo_root, skip=skip_fetch),
        check_divergence(repo_root),
    ]

    try:
        changes = collect_changes(repo_root)
    except RuntimeError as exc:
        results.append(_failed("changed-files", str(exc)))
        changes = []
    else:
        # A push delivers BOTH working-tree changes AND everything already
        # committed ahead of origin/main. Scan the union so a secret committed in
        # an ahead-commit (clean tree) cannot slip past.
        ahead_paths, ahead_err = ahead_commit_files(repo_root)
        results.append(display_changes(changes, ahead_paths))
        if ahead_err is not None:
            # Fail closed — never silently skip the ahead-commit scan.
            results.append(_failed("ahead-commits", ahead_err))
        worktree_paths = [p for _index, _worktree, p in changes]
        union_paths = list(dict.fromkeys(worktree_paths + ahead_paths))
        results.append(scan_changed_filenames(union_paths))
        results.append(content_leak_scan(repo_root, changes, ahead_paths))

    # UNCONDITIONAL in every mode (never inferred from filenames).
    results.append(run_snapshot_check(repo_root))
    results.append(run_gate_test(repo_root))

    results.extend(mode_reminders(mode))
    return results


_MARK = {"pass": "[PASS]", "fail": "[FAIL]", "info": "[INFO]", "warn": "[WARN]"}


def _print_results(results, mode: str) -> None:
    print(f"ISAAC first-push preflight — mode={mode}")
    print("=" * 60)
    for r in results:
        head = f"{_MARK.get(r.severity, '[????]')} {r.name}"
        print(f"{head}: {r.detail}" if r.detail else head)
        for line in r.lines:
            print(f"        {line}")
    print("=" * 60)


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Deterministic first-push preflight (prevents predictable failed pushes)."
    )
    parser.add_argument("mode", choices=MODES, help="preflight mode")
    parser.add_argument("--repo-root", default=Path("."), type=Path,
                        help="repository root (default: cwd)")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="skip the read-only 'git fetch --prune origin' "
                             "(offline/tests); divergence still uses origin/main")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    # env escape hatch mirrors --skip-fetch for CI/offline contexts.
    skip_fetch = args.skip_fetch or os.environ.get("ISAAC_PREFLIGHT_SKIP_FETCH") == "1"
    results = run_preflight(args.repo_root, args.mode, skip_fetch=skip_fetch)
    _print_results(results, args.mode)

    failures = [r for r in results if r.failed]
    if failures:
        print(f"PREFLIGHT FAILED — {len(failures)} check(s) failed; DO NOT PUSH.")
        for r in failures:
            print(f"  - {r.name}: {r.detail}")
        return EXIT_FAIL
    print("PREFLIGHT PASSED — all gates green; push is safe to proceed.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
