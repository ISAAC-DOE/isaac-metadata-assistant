"""The ONE place the local CLI starts another process: the offline upstream portal check.

WHY THIS FILE IS OUTSIDE ``isaac_api``. ``test_attack_injection_and_containment.py``
asserts that no module in the API package (``apps/api/isaac_api/``) calls
``subprocess.*`` — the structural half of "hostile content reaches no interpreter".
That guard has no allowlist by design, and this module does not add one. The
portal check is a LOCAL-CLI-only step (``isaac bundle validate``): the web server never
imports this module (``test_local_import_review_fixes.py::test_the_server_never_loads_the_portal_runner``
proves it in a fresh subprocess), and the only importer is ``isaac_api.local_import.portal``, lazily, inside
the function that runs the check.

THE SAME DISCIPLINE THE GUARD PROTECTS, ENFORCED HERE AND TESTED:

* argv is a fixed LIST — ``[python, "-I", "-c", RUNNER]`` — never a shell, never a
  string a caller composed; ``RUNNER`` is this module's literal;
* the record travels as DATA on stdin (JSON), so no record content is ever code;
* the interpreter path must be absolute, an existing executable file, and (unless the
  operator named it explicitly) inside the pinned validator cache;
* the environment is SCRUBBED to ``PATH``/``HOME``/``PYTHONDONTWRITEBYTECODE``; ``-I``
  ignores ``PYTHON*`` variables and the user site;
* a timeout, and BOUNDED output: stdout/stderr go to temporary files and at most
  :data:`MAX_OUTPUT_BYTES` are read back.

Stdlib only.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

MAX_OUTPUT_BYTES = 16 * 1024 * 1024
TIMEOUT_S = 180

#: The fixed program the validator interpreter runs. It reads the record from stdin.
RUNNER = r"""
import json, sys
sys.path.insert(0, ".")
record = json.loads(sys.stdin.read())
import validation
result = validation.validate_record_full(record)
outcome, held = validation.outcome(result)
print(json.dumps({"result": result, "outcome": outcome, "held": held}, default=str))
"""


class RunnerRefused(ValueError):
    pass


def _checked_python(python: str, *, must_be_within: Path | None) -> str:
    path = Path(python)
    if not path.is_absolute():
        raise RunnerRefused("the validator interpreter path must be absolute")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RunnerRefused("the validator interpreter is not an executable file")
    if must_be_within is not None:
        try:
            path.relative_to(must_be_within)  # lexical: a venv's python is a symlink
        except ValueError as exc:
            raise RunnerRefused("the validator interpreter is outside the pinned cache") from exc
    return str(path)


def run(python: str, portal_dir: str, record_json: str, *, must_be_within: Path | None) -> tuple[int, str, str]:
    """``(returncode, stdout, stderr)`` — both bounded. Raises :class:`RunnerRefused`
    for an unacceptable interpreter or directory, and on timeout."""
    exe = _checked_python(python, must_be_within=must_be_within)
    cwd = Path(portal_dir)
    if not cwd.is_absolute() or not (cwd / "validation.py").is_file():
        raise RunnerRefused("the portal directory must be absolute and hold validation.py")
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp"), "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            done = subprocess.run(
                [exe, "-I", "-c", RUNNER],
                input=record_json.encode("utf-8"),
                stdout=out,
                stderr=err,
                cwd=str(cwd),
                env=env,
                timeout=TIMEOUT_S,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RunnerRefused(f"the validator did not finish within {TIMEOUT_S} s") from exc
        out.seek(0)
        err.seek(0)
        stdout = out.read(MAX_OUTPUT_BYTES).decode("utf-8", errors="replace")
        stderr = err.read(64 * 1024).decode("utf-8", errors="replace")
    return done.returncode, stdout, stderr
