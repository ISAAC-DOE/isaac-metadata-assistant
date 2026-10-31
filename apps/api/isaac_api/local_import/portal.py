"""The OFFLINE upstream portal check (slice LOCAL-2). Runs nothing on the network.

The official ISAAC portal (upstream ``ISAAC-DOE/isaac-ai-ready-record``) validates a
submitted record with ``portal/validation.validate_record_full`` against the CURRENT
upstream schema, vocabulary and semantic rules — stricter than this repository's
vendored v1.05 schema. This module runs that same function, from a PINNED upstream
checkout, in an ISOLATED interpreter (a subprocess with ``-I``), and hands back its
result verbatim.

Location, in order:

1. ``ISAAC_PORTAL_VALIDATOR_DIR`` (the upstream checkout root, holding
   ``portal/validation.py``) and ``ISAAC_PORTAL_VALIDATOR_PYTHON`` (its interpreter);
2. ``~/.cache/isaac/portal-validator/<commit>/src`` and ``.../venv/bin/python``, as
   ``scripts/install_portal_validator.sh`` lays them out.

If neither is usable the verdict is ``portal_check_unavailable`` — NEVER a pass. A
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


def locate() -> dict:
    """``{available, dir, python, commit, reason}``."""
    env_dir, env_py = os.environ.get(DIR_ENV), os.environ.get(PYTHON_ENV)
    candidates: list[tuple[Path, Path]] = []
    if env_dir:
        if not env_py:
            return {"available": False, "reason": f"{DIR_ENV} is set but {PYTHON_ENV} is not."}
        candidates.append((Path(env_dir).expanduser(), Path(env_py).expanduser()))
    else:
        if CACHE_ROOT.is_dir():
            for child in sorted(CACHE_ROOT.iterdir()):
                if child.name.startswith(PINNED_COMMIT):
                    candidates.append((child / "src", child / "venv" / "bin" / "python"))
    pin = PINNED_COMMIT  # no override: a verdict is only ever about the pinned contract
    for src, py in candidates:
        if (src / "portal" / "validation.py").is_file() and py.exists():
            head = git_head(src)
            if not head or not head.startswith(pin):
                # NOT THE PINNED VALIDATOR: its verdict would be about a different contract.
                return {
                    "available": False,
                    "reason": f"the validator checkout is at {head or 'an unknown commit'}, not the pinned {pin}",
                }
            return {
                "available": True,
                "dir": str(src),
                "python": str(py),
                "commit": head,
                "pinned_commit": pin,
                # an operator-named interpreter is trusted as named; a cached one must
                # stay inside the cache it was installed into
                "must_be_within": None if env_dir else str(src.parent),
                "reason": None,
            }
    return {
        "available": False,
        "reason": (
            "No upstream portal validator found. Run scripts/install_portal_validator.sh, or "
            f"set {DIR_ENV} and {PYTHON_ENV}."
        ),
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
