"""The OFFLINE upstream portal check (slice LOCAL-2). Runs nothing on the network.

The official ISAAC portal (upstream ``ISAAC-DOE/isaac-ai-ready-record``) validates a
submitted record with ``portal/validation.validate_record_full`` against the CURRENT
upstream schema, vocabulary and semantic rules — its vocabulary and semantic layers go beyond
what any JSON schema expresses. Since 2026-11-16 this repository's vendored schema is the
pinned commit's own document (``schema/PROVENANCE.md``). This module runs that same function, from a PINNED upstream
checkout, in an ISOLATED interpreter (a subprocess with ``-I``), and hands back its
result verbatim.

Location, in order:

1. ``ISAAC_PORTAL_VALIDATOR_DIR`` (the upstream checkout root, holding
   ``portal/validation.py``) and ``ISAAC_PORTAL_VALIDATOR_PYTHON`` (its interpreter): an
   operator's explicit choice, trusted as named and final (no fallback);
2. otherwise the copy SHIPPED WITH THIS REPOSITORY, ``vendor/isaac-portal-validator/<commit>/``
   (the four files ``validate_record_full`` reads plus the record contract the skill quotes,
   upstream's relative layout kept, ``vendor/isaac-portal-validator/PROVENANCE.md``). The folder
   must hold EXACTLY those files (``__pycache__`` and Finder's ``.DS_Store`` aside) and each
   file's sha256 must equal :data:`VENDORED_SHA256`, or it is unavailable: an extra module there
   (``portal/validation/__init__.py``, ``portal/jsonschema.py``) would be imported ahead of the
   real one. Its interpreter is this checkout's ``.venv`` (or, in a git worktree without one, the
   main checkout's ``.venv``) when the validator's packages (:data:`VALIDATOR_MODULES`) are
   installed there, else the venv of an older ``~/.cache/isaac/portal-validator/<commit>/``
   install.

THE OLDER CACHE INSTALL'S SOURCE (``~/.cache/isaac/portal-validator/<commit>/src``, a full
upstream checkout) IS NO LONGER RUN (28 Nov 2026). Its ``portal/`` folder holds some twenty
importable modules, and ``ontology.py`` imports one of them (``database``) when present, so
checking five files' sha256 could not establish what would execute; the vendored folder can be
checked exactly, and gives byte-identical verdicts. Only the cache's venv (packages, no ISAAC
code) may still be used, as an interpreter.

If none is usable the verdict is ``portal_check_unavailable`` — NEVER a pass. A
result whose vocabulary or semantic layer reports ``degraded`` (the upstream layer did
not actually run) is ``portal_check_degraded``, also never a pass.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

PINNED_COMMIT = "a1cb1c8"
DIR_ENV = "ISAAC_PORTAL_VALIDATOR_DIR"
PYTHON_ENV = "ISAAC_PORTAL_VALIDATOR_PYTHON"
CACHE_ROOT = Path("~/.cache/isaac/portal-validator").expanduser()

VERDICT_UNAVAILABLE = "portal_check_unavailable"
VERDICT_DEGRADED = "portal_check_degraded"

#: this checkout (apps/api/isaac_api/local_import/portal.py -> four levels up)
CHECKOUT_ROOT = Path(__file__).resolve().parents[4]
#: the validator shipped with the repository (see vendor/isaac-portal-validator/PROVENANCE.md)
VENDOR_ROOT = CHECKOUT_ROOT / "vendor" / "isaac-portal-validator"
VENDORED_COMMIT = "a1cb1c861f3e6eb506da33f27196b43312f240f6"
#: every vendored file and its sha256, as PROVENANCE.md lists them. A file that differs (edited,
#: truncated, half-refreshed) makes the vendored copy UNAVAILABLE, never a different verdict.
VENDORED_SHA256 = {
    "portal/validation.py": "d72ac41d5a60cd3f2ecf0fc453dcbf2b58973eb3426521f0635fdc7545ff44f8",
    "portal/ontology.py": "5841f95b36be72ae15ef04c549c1decea77ed39fbf19af245a36ea02b4cd9d8c",
    "schema/isaac_record_v1.json": "7e61cb0041b7537ae506ec8561c212e5d849868757f2d4741888ce3b24ef8c20",
    "data/vocabulary.json": "7d60a2f0383b936ac055c309596e2ba9afe9fb9a1b893fe217f88e7a52b8d0f8",
    # not read by validation: the record contract the skill quotes ("what belongs in a record")
    "data/record_contract.json": "eff30021b0a5c821fcfda924a2a41b6b7ed7f4993b8f45c89b7edf17713d427b",
}
#: the import names validation.py + ontology.py need at import time (pip: jsonschema,
#: rfc3339-validator, PyYAML, GitPython, requests = the `portal` extra in pyproject.toml)
VALIDATOR_MODULES = ("jsonschema", "rfc3339_validator", "yaml", "git", "requests")

def git_head(repo: Path) -> str | None:
    """The checkout's HEAD sha, read from ``.git`` files (no subprocess)."""
    try:
        git = Path(repo) / ".git"
        if git.is_file():
            text = git.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None
            git = (git.parent / text.split(":", 1)[1].strip()).resolve()
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head
        ref = head.split(":", 1)[1].strip()
        if (git / ref).is_file():
            return (git / ref).read_text(encoding="utf-8").strip()
        packed = git / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                parts = line.split(" ")
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    except OSError:
        return None
    return None


def _sha256(path: Path) -> str | None:
    import hashlib

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


#: names in the vendored folder that are never imported or read as validator input: compiled files
#: (the runner gives Python a fresh, empty pycache_prefix, so none is ever loaded) and Finder's files
_IGNORED_NAMES = {"__pycache__", ".DS_Store"}


def _unexpected_entries(src: Path) -> list[str]:
    """Every file or folder under ``src`` that is not a listed file or a folder holding one."""
    allowed_files = set(VENDORED_SHA256)
    allowed_dirs = {str(Path(rel).parent.as_posix()) for rel in allowed_files}
    extra = []
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORED_NAMES or (here / d).is_symlink())
        for name in sorted(filenames) + list(dirnames):
            rel = (here / name).relative_to(src).as_posix()
            if name in _IGNORED_NAMES:
                continue
            if rel in allowed_files or (rel in allowed_dirs and (here / name).is_dir() and not (here / name).is_symlink()):
                continue
            extra.append(rel)
    return extra


def vendored_state(root: Path | None = None) -> tuple[Path | None, str | None]:
    """``(dir, None)`` when the vendored folder holds exactly the listed files and every file's sha256
    matches, else ``(None, reason)``. Reads files only."""
    src = Path(root or VENDOR_ROOT) / PINNED_COMMIT
    if not src.is_dir():
        return None, f"no vendored validator at {src}"
    extra = _unexpected_entries(src)
    if extra:
        return None, ("the vendored validator's folder holds files PROVENANCE.md does not list "
                      f"({', '.join(extra[:5])}{', ...' if len(extra) > 5 else ''}); one could be imported in place of "
                      "the validator's own code. Remove them (git status shows them), or restore the folder with git")
    bad = [rel for rel, want in VENDORED_SHA256.items() if _sha256(src / rel) != want]
    if bad:
        return None, ("the vendored validator's files do not match vendor/isaac-portal-validator/PROVENANCE.md "
                      f"(changed or missing: {', '.join(bad)}); restore them with git, or refresh them as PROVENANCE.md says")
    return src, None


def main_checkout(root: Path) -> Path | None:
    """The main checkout of a git WORKTREE (``.git`` is a ``gitdir:`` file), read from git's own files;
    ``None`` for a main checkout or no git at all."""
    try:
        git = Path(root) / ".git"
        if not git.is_file():
            return None
        text = git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            return None
        gitdir = (git.parent / text.split(":", 1)[1].strip()).resolve()
        common = gitdir
        if (gitdir / "commondir").is_file():
            common = (gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
        main = common.parent if common.name == ".git" else None
        return main if main and main != Path(root).resolve() else None
    except OSError:
        return None


def has_validator_modules(venv: Path) -> bool:
    """Whether ``venv``'s site-packages hold every :data:`VALIDATOR_MODULES` import. Read from the
    file system, no process started; a broken package makes the RUN fail, which is unavailable."""
    for site in sorted(Path(venv).glob("lib/python3.*/site-packages")):
        if all((site / m / "__init__.py").is_file() or (site / f"{m}.py").is_file() for m in VALIDATOR_MODULES):
            return True
    return False


def vendored_interpreters() -> list[Path]:
    """The venvs that may run the vendored validator, in order: this checkout's ``.venv``, the main
    checkout's ``.venv`` (a git worktree), then an older cache install's venvs (packages only)."""
    venvs = [CHECKOUT_ROOT / ".venv"]
    main = main_checkout(CHECKOUT_ROOT)
    if main is not None:
        venvs.append(main / ".venv")
    if CACHE_ROOT.is_dir():
        venvs += [child / "venv" for child in sorted(CACHE_ROOT.iterdir()) if child.name.startswith(PINNED_COMMIT)]
    return venvs


def _vendored() -> dict:
    src, why = vendored_state()
    if src is None:
        return {"available": False, "reason": why}
    for venv in vendored_interpreters():
        py = venv / "bin" / "python"
        if py.exists() and has_validator_modules(venv):
            return {
                "available": True,
                "dir": str(src),
                "python": str(py),
                "commit": VENDORED_COMMIT,
                "pinned_commit": PINNED_COMMIT,
                "must_be_within": str(venv),
                "source": "vendored",
                "reason": None,
            }
    return {
        "available": False,
        "reason": ("the vendored portal validator is here, but no Python environment has its packages "
                   f"({', '.join(VALIDATOR_MODULES)}). Run: scripts/setup_isaac_local.sh"),
    }


def locate() -> dict:
    """``{available, dir, python, commit, source, reason}``; ``source`` is ``env`` or ``vendored``."""
    env_dir, env_py = os.environ.get(DIR_ENV), os.environ.get(PYTHON_ENV)
    if not env_dir:
        return _vendored()
    if not env_py:
        return {"available": False, "reason": f"{DIR_ENV} is set but {PYTHON_ENV} is not."}
    src, py = Path(env_dir).expanduser(), Path(env_py).expanduser()
    if not ((src / "portal" / "validation.py").is_file() and py.exists()):
        return {"available": False, "reason": f"{DIR_ENV} does not hold portal/validation.py, or {PYTHON_ENV} does not exist."}
    pin = PINNED_COMMIT  # no override: a verdict is only ever about the pinned contract
    head = git_head(src)
    if not head or not head.startswith(pin):
        # NOT THE PINNED VALIDATOR: its verdict would be about a different contract.
        return {"available": False, "reason": f"the validator checkout is at {head or 'an unknown commit'}, not the pinned {pin}"}
    return {
        "available": True,
        "dir": str(src),
        "python": str(py),
        "commit": head,
        "pinned_commit": pin,
        "must_be_within": None,  # an operator-named interpreter is trusted as named
        "source": "env",
        "reason": None,
    }


def verdict_of(check: Mapping) -> str:
    """``publish`` | ``hold`` | ``reject`` | ``portal_check_unavailable`` | ``portal_check_degraded``."""
    if check.get("status") != "ran":
        return VERDICT_UNAVAILABLE
    result = check.get("result") or {}
    if result.get("degraded"):
        return VERDICT_DEGRADED
    return str(check.get("outcome") or VERDICT_UNAVAILABLE)


def run_portal_check(record: Mapping[str, Any]) -> dict:
    """Run upstream ``validate_record_full`` on ``record``. Never raises; never a network call
    from this process. The upstream result is returned VERBATIM under ``result``."""
    where = locate()
    if not where["available"]:
        return {"status": "unavailable", "reason": where["reason"], "verdict": VERDICT_UNAVAILABLE}
    # THE PROCESS IS STARTED OUTSIDE THE API PACKAGE (`apps/api/isaac_portal_runner.py`),
    # which keeps `test_attack_injection_and_containment`'s no-subprocess guarantee for
    # `isaac_api` exactly as written. Imported here, lazily, and nowhere else.
    import isaac_portal_runner as runner

    within = Path(where["must_be_within"]) if where.get("must_be_within") else None
    try:
        code, stdout, stderr = runner.run(where["python"], str(Path(where["dir"]) / "portal"), json.dumps(record), must_be_within=within)
    except runner.RunnerRefused as exc:
        return {"status": "unavailable", "reason": f"the validator was refused: {exc}", "verdict": VERDICT_UNAVAILABLE}
    except OSError as exc:
        return {"status": "unavailable", "reason": f"the validator did not run: {type(exc).__name__}", "verdict": VERDICT_UNAVAILABLE}
    if code != 0:
        tail = (stderr or "").strip().splitlines()[-5:]
        return {"status": "unavailable", "reason": "the validator exited with an error: " + " | ".join(tail), "verdict": VERDICT_UNAVAILABLE}
    try:
        payload = json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"status": "unavailable", "reason": "the validator printed no result", "verdict": VERDICT_UNAVAILABLE}
    check = {
        "status": "ran",
        "validator_commit": where["commit"],
        "pinned_commit": PINNED_COMMIT,
        # env | vendored: which copy gave this verdict (never a local path)
        "validator_source": where.get("source"),
        "result": payload.get("result"),
        "outcome": payload.get("outcome"),
        "held": payload.get("held"),
    }
    check["verdict"] = verdict_of(check)
    return check


def upstream_schema(where: Mapping | None = None) -> dict | None:
    """The upstream checkout's schema document, for the vendored-vs-upstream drift report."""
    where = where or locate()
    if not where.get("available"):
        return None
    path = Path(where["dir"]) / "schema" / "isaac_record_v1.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
