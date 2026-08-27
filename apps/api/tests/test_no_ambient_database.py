"""A BARE ``pytest`` MUST NOT CONNECT THE WRITE PATH TO WHATEVER ``PGHOST`` NAMES.

WHAT WAS MEASURED, AND HOW
==========================
``db_write.database_configured`` is effectively ``bool(PGHOST)``, and that alone
selects the PostgreSQL repository over the filesystem one. ``pyproject.toml``'s
``testpaths`` includes ``apps/api/tests``. ``docs/postgres-test-db-guide.md`` tells
anyone who already holds a SLAC cluster context to export exactly
``PGHOST``/``PGPORT``/``PGUSER``/``PGPASSWORD``/``PGDATABASE`` for the documented
port-forward convenience. So ``CLAUDE.md`` §14's own developer command —
``.venv/bin/pytest`` — was a write client for whatever that shell pointed at.

Measured with a COUNTING DOUBLE at ``db_write.connect_psycopg2`` and those five
variables exported. **Nothing was connected to**: the double answers in process, and
no agent may reach that database (``CLAUDE.md`` §15). Before the fixture, the single
file ``test_pending_reads_are_boundable.py`` opened **70** connections and issued
**11,633** mutating statements against ``isaac_experiments``, ``isaac_runs`` and
``isaac_run_projection``, on a DSN carrying ``application_name=isaac_app_write``.

WHY THE THREE EXISTING GUARDS DID NOT COVER IT
==============================================
* ``.github/workflows/ci.yml``'s ``test`` job asserts ``PGHOST`` is unset. That is a
  guard on CI's environment and says nothing about a developer's shell. It is not
  duplicated or weakened by anything here.
* ``test_run_row_parity.py``'s ``ISAAC_RUN_REAL_ENGINE_PARITY`` opt-in closed the
  accident **for that one file**, in words general enough to read as closing it
  everywhere. It never was in scope for the other files that write through the same
  repository, and that belief is what made this dangerous rather than merely open.
* ``db_write``'s ``PGDATABASE`` gate pins the name to ``metadata_assistant`` — which
  is the HOSTED database's own name. It rejects a misconfiguration; it discriminates
  nothing about which server is reached.

WHAT THIS FILE ASSERTS
======================
That the conftest fixture is real (this process has no libpq environment), that it
recognises exactly the opt-in the real-engine suites already use, that its
enumeration is by PREFIX rather than by a list that would age, and — the part that
is a proof rather than an assertion — that a representative writing test opens
**zero** connections with the fixture in place and a non-zero number without it,
measured by running that test in a subprocess both ways.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import isaac_api.db_write as dbw
import test_run_row_parity as parity
from conftest import (
    REAL_ENGINE_OPT_IN,
    REAL_ENGINE_OPT_IN_VALUE,
    libpq_variable_names,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The one test the subprocess proof drives. Chosen because it is ordinary — it
#: creates a record and answers a question, which is what most of this package does —
#: and because it lives in the file that measured worst.
REPRESENTATIVE = (
    "apps/api/tests/test_pending_reads_are_boundable.py"
    "::test_a_run_answer_on_a_large_record_returns_a_window_not_the_record"
)

#: The exact five the guide tells an operator to export, with a host that cannot
#: resolve or route anywhere. The double intercepts before libpq is reached at all,
#: so the name is belt-and-braces rather than load-bearing — but it is chosen so that
#: a defect in the double degrades into a DNS failure rather than into a connection.
BOGUS_LIBPQ_ENV = {
    "PGHOST": "isaac-canary.invalid",
    "PGPORT": "5432",
    "PGUSER": "metadata_assistant",
    "PGPASSWORD": "never-sent-anywhere",
    "PGDATABASE": "metadata_assistant",
}


def test_this_process_has_no_libpq_environment():
    """THE FIXTURE IS REAL, asserted from inside the session it protects."""
    if (os.environ.get(REAL_ENGINE_OPT_IN) or "").strip() == REAL_ENGINE_OPT_IN_VALUE:
        pytest.skip(
            f"{REAL_ENGINE_OPT_IN} is set: this session consented to a real engine, "
            "so the libpq environment is deliberately left intact."
        )
    assert libpq_variable_names(os.environ) == []
    assert dbw.database_configured(os.environ) is False


def test_the_opt_in_this_conftest_honours_is_the_suites_own():
    """NO SECOND SWITCH, AND NO DRIFT.

    The conftest re-declares the opt-in rather than importing it, because importing a
    test module from a conftest would execute that module's ``_probe_engine()`` at
    conftest-import time — the one moment the conftest exists to make uninteresting.
    Re-declaration is only safe if something pins the two together, so this does.

    A SECOND MECHANISM WOULD BE A SECOND WAY IN. If the fixture honoured a variable of
    its own, an environment could keep the libpq variables without the real-engine
    suites' consent, which is precisely the state this whole change removes.
    """
    assert REAL_ENGINE_OPT_IN == parity.OPT_IN_ENV
    assert REAL_ENGINE_OPT_IN_VALUE == parity.OPT_IN_VALUE
    # ...and it is not a libpq variable, so exporting the documented five cannot set
    # it. That is the answer to "can the opt-in be triggered by accident".
    assert not REAL_ENGINE_OPT_IN.startswith("PG")


def test_the_libpq_sweep_is_by_prefix_and_not_a_hand_written_list():
    """A LIST WOULD BE CORRECT ON THE DAY IT WAS WRITTEN AND STALE AFTERWARDS.

    ``PGSERVICE`` and ``PGSERVICEFILE`` are the case that makes this more than
    tidiness: either can name a complete connection in a service file with no
    ``PGHOST`` present anywhere in the environment.
    """
    sample = {
        "PGHOST": "h",
        "PGHOSTADDR": "1.2.3.4",
        "PGPORT": "5432",
        "PGUSER": "u",
        "PGPASSWORD": "p",
        "PGDATABASE": "d",
        "PGSSLMODE": "require",
        "PGSERVICE": "svc",
        "PGSERVICEFILE": "/tmp/svc.conf",
        "PGPASSFILE": "/tmp/pgpass",
        "PGOPTIONS": "-c x=y",
        "PGCONNECT_TIMEOUT": "10",
        "PGSSLROOTCERT": "/tmp/root.crt",
        # A variable no list in this repository has ever mentioned. It is swept
        # because the rule is the prefix; that is the whole point.
        "PGCHANNELBINDING": "require",
        "PG_A_VARIABLE_INVENTED_FOR_THIS_TEST": "1",
        # ...and these must NOT be swept.
        "PATH": "/usr/bin",
        "ISAAC_UI_WORKSPACE": "/tmp/ws",
        "POSTGRES_PASSWORD": "not-a-libpq-variable",
    }
    swept = libpq_variable_names(sample)
    assert "PGCHANNELBINDING" in swept
    assert "PG_A_VARIABLE_INVENTED_FOR_THIS_TEST" in swept
    assert [n for n in swept if not n.startswith("PG")] == []
    assert len(swept) == len([n for n in sample if n.startswith("PG")])


# ---------------------------------------------------------------------------
# the proof
# ---------------------------------------------------------------------------

#: A pytest plugin, written to ``tmp_path`` and loaded with ``-p``, that counts what
#: would have reached a real server. It replaces ``db_write.connect_psycopg2``, which
#: ``write_transaction`` resolves at CALL time from the module global — deliberately,
#: per that function's own docstring — so the substitution is total.
#:
#: ``PGCANARY_REARM=1`` additionally re-sets the libpq variables from a
#: FUNCTION-scoped autouse fixture, which runs AFTER the session-scoped conftest
#: fixture has cleared them. That is how the "without the fixture" arm is simulated
#: without adding a bypass to the fixture itself: a switch that disabled the guard
#: would be a second way in, and this measurement must not create the hazard it
#: measures.
_CANARY_PLUGIN = '''
import json, os
import pytest

REPORT = os.environ["PGCANARY_REPORT"]
REARM = json.loads(os.environ.get("PGCANARY_REARM_ENV") or "{}")
COUNT = {"connections": 0, "statements": 0, "mutating": 0}
_MUTATING = ("insert", "update", "delete", "create", "drop", "alter", "truncate")


class _Cursor:
    def __init__(self):
        self._last = ""

    def execute(self, sql, params=None):
        self._last = str(sql)
        COUNT["statements"] += 1
        head = self._last.strip().lower().split()
        if head and head[0] in _MUTATING:
            COUNT["mutating"] += 1

    def fetchone(self):
        low = self._last.lower()
        if "current_database" in low:
            return ("metadata_assistant",)
        if "to_regclass" in low or "count(" in low or "exists" in low:
            return (1,)
        return None

    def fetchall(self):
        return []

    def close(self):
        pass

    # The repository reads `rowcount` to decide whether its compare-and-swap was
    # accepted, and `description` when it inspects a result set. A double missing
    # either raises inside the write path, which would understate the control arm by
    # aborting it after its first connection instead of letting it run.
    @property
    def rowcount(self):
        return 1

    description = None


class _Conn:
    autocommit = False

    def cursor(self):
        return _Cursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _connect(env, *a, **k):
    COUNT["connections"] += 1
    return _Conn()


def pytest_configure(config):
    import isaac_api.db_write as dbw

    dbw.connect_psycopg2 = _connect


@pytest.fixture(scope="session", autouse=True)
def _rearm_the_ambient_environment(_no_ambient_database):
    # SESSION-SCOPED, AND IT DEPENDS ON THE FIXTURE IT UNDOES. Both together are
    # what make this a faithful reproduction rather than an approximation: the
    # dependency guarantees it runs AFTER the conftest fixture cleared the
    # environment, and the session scope guarantees it runs BEFORE any module- or
    # function-scoped fixture that builds an app or saves a record. An earlier
    # function-scoped version re-armed halfway through a test's own setup, which
    # measured one connection and a failure — a control that was technically
    # non-zero while reproducing nothing.
    for name, value in REARM.items():
        os.environ[name] = value
    yield


def pytest_sessionfinish(session, exitstatus):
    with open(REPORT, "w") as handle:
        json.dump(COUNT, handle)
'''


def _run_arm(tmp_path: Path, *, rearm: bool) -> dict:
    """Run :data:`REPRESENTATIVE` in a subprocess and return the counting double's tally."""
    plugin_dir = tmp_path / ("rearmed" if rearm else "as_shipped")
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "pgcanary_proof.py").write_text(
        textwrap.dedent(_CANARY_PLUGIN), encoding="utf-8"
    )
    report = plugin_dir / "report.json"

    env = dict(os.environ)
    env.update(BOGUS_LIBPQ_ENV)
    env["PGCANARY_REPORT"] = str(report)
    env["PGCANARY_REARM_ENV"] = json.dumps(BOGUS_LIBPQ_ENV if rearm else {})
    env["PYTHONPATH"] = os.pathsep.join(
        [str(plugin_dir), *[p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]]
    )
    # Never inherited: this subprocess must exercise the DEFAULT posture, and the
    # opt-in would tell the conftest to leave the environment alone.
    env.pop(REAL_ENGINE_OPT_IN, None)
    env.pop(parity.REQUIRE_ENV, None)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "pgcanary_proof", REPRESENTATIVE, "-q"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert report.exists(), (
        f"the counting plugin never wrote its report; the subprocess said:\n"
        f"{completed.stdout[-4000:]}\n{completed.stderr[-2000:]}"
    )
    tally = json.loads(report.read_text(encoding="utf-8"))
    tally["returncode"] = completed.returncode
    tally["stdout_tail"] = completed.stdout[-2000:]
    return tally


def test_a_representative_writing_test_opens_ZERO_connections_and_would_have_opened_some(
    tmp_path,
):
    """THE PROOF, AS AN A/B, because an assertion about a guard is not evidence for it.

    Both arms run the SAME test, in a subprocess, with the five documented libpq
    variables exported and a counting double at ``connect_psycopg2``. They differ in
    one thing: the ``rearmed`` arm re-sets those variables from a function-scoped
    autouse fixture, which runs after the session-scoped conftest fixture cleared
    them — reproducing the world as it was before this change without giving the
    fixture a bypass.

    A CONTROL IS PART OF THE PROOF. If the ``rearmed`` arm also measured zero, this
    test would be green for the wrong reason — the double could be mis-wired, the
    representative test could have stopped writing — and would read as evidence while
    proving nothing.
    """
    rearmed = _run_arm(tmp_path, rearm=True)
    assert rearmed["connections"] > 0, (
        "the control measured no connections, so the zero below proves nothing about "
        f"the fixture: {rearmed}"
    )
    assert rearmed["mutating"] > 0, rearmed
    # AND THE CONTROL MUST HAVE PASSED. A control that measured one connection and
    # then died is not a reproduction of the accident — it is an aborted one, and it
    # would let a much weaker "before" stand in for the real thing. The first version
    # of this plugin measured exactly that (1 connection, a `KeyError`) because its
    # cursor double lacked `rowcount`.
    assert rearmed["returncode"] == 0, rearmed["stdout_tail"]

    as_shipped = _run_arm(tmp_path, rearm=False)
    assert as_shipped["connections"] == 0, (
        "a bare pytest still reached the write path's connection seam with an ambient "
        f"libpq environment: {as_shipped}"
    )
    assert as_shipped["statements"] == 0, as_shipped
    # ...and it must have PASSED while doing so: the fixture moves the test onto the
    # filesystem repository, it does not make the test fail its way to zero.
    assert as_shipped["returncode"] == 0, as_shipped["stdout_tail"]
