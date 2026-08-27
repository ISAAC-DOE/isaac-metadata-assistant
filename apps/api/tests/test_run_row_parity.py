"""THE STAGE-1 PARITY ORACLE for the ``isaac_runs`` SHADOW WRITE.

WHAT THIS FILE IS
=================
One property, asserted over and over against a REAL PostgreSQL engine:

    after any save, the rows of ``isaac_runs`` for an experiment are exactly
    ``exp.sorted_runs()`` — id, ordinal, document, rev and generation.

``isaac_runs`` is a SHADOW. ``CLAUDE.md`` §15 is explicit that the experiment
document remains authoritative, that ``state["runs"]`` stays where it is, and that
making ``isaac_runs`` a READ source is a separate, unauthorized decision. **Nothing
in this file reads a run row on behalf of the application.** Every read here is a
TEST reading the table to check the shadow against the document. That is the whole
point of a shadow: a row nobody reads is only worth having if it is right, and the
only way to know it is right is to look at it from outside the application.

WHY IT MUST RUN AGAINST A REAL ENGINE, AND WHY IT SKIPS EVERYWHERE ELSE
======================================================================
``test_experiment_repository.py`` already exercises the run write path against an
IN-PROCESS FAKE DRIVER, and that file's own docstring says what that proves: the
SHAPE — one transaction, the statement policy, the accepted gate, deterministic
rollback. It does not prove the SQL is valid PostgreSQL, it enforces none of
``0002_runs``' seven constraints, and — the one that matters most here — the fake
hands back exactly the document it was given, so a text-vs-document comparison
defect in the diff would PASS there and rewrite every row on every save here.

So this suite is the real-engine half. There is no PostgreSQL on a developer
machine in this project, and by project rule (``CLAUDE.md`` §15, and
``docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52``) no agent
may reach for a kubeconfig, a port-forward or a Secret to obtain one. The engine
this suite is written for is CI's ``postgres:18`` SERVICE CONTAINER, in
``.github/workflows/ci.yml``'s ``postgres-migration`` job. Locally every test here
SKIPS, and a skip is reported as a skip — never as a pass.

THIS SUITE WRITES, SO IT NEVER ACTIVATES BY ACCIDENT
====================================================
**Two variables, and they mean different things. Both are required in CI.**

* :data:`OPT_IN_ENV` (``ISAAC_RUN_REAL_ENGINE_PARITY=1``) is CONSENT TO CONNECT.
  Without it this file opens NOTHING — not at collection, not at run — whatever
  the libpq environment says.
* :data:`REQUIRE_ENV` (``ISAAC_REQUIRE_REAL_ENGINE_PARITY=1``) is a DEMAND THAT
  THE ENGINE BE THERE, and it is the anti-silent-skip guard described below.

They were one variable, and that was a defect. The gates this file used to have
were "is ``PGHOST`` set" and "is ``PGDATABASE`` exactly ``metadata_assistant``" —
and the second is not a discriminator at all, because ``metadata_assistant`` is
the HOSTED database's own name (CI's service container is deliberately named to
match it). ``pyproject.toml``'s ``testpaths`` includes ``apps/api/tests``, so the
documented developer command ``.venv/bin/pytest`` (``CLAUDE.md`` §14) collects
this file, and the probe ran at COLLECTION time. Anyone holding the
``kubectl port-forward`` that ``docs/postgres-test-db-guide.md:83-96`` documents
as a supported convenience would therefore have had a plain ``pytest`` write
~25 experiments, their run rows, an out-of-band ``UPDATE``, a ``DELETE`` and a
``jsonb_set`` tamper into the owner's production-derived database, with no
teardown. The precedent for the fix is one package away:
``db_recon.OPT_IN_ENV``, whose comment is "this entry point never runs by
accident" — and ``db_recon`` only READS.

A LOOPBACK CHECK IS ALSO APPLIED, AND ITS LIMIT IS STATED RATHER THAN IMPLIED.
:func:`_is_loopback_target` splits ``PGHOST`` on ``,`` — libpq accepts a multi-host
list and tries the elements in order — and requires EVERY element to be a loopback
IP literal or ``localhost``. A unix-socket directory is refused; see
:func:`_is_loopback_element` for why that was narrowed rather than kept. That is
defence in depth against a hostname target — it is **NOT** a defence against the
port-forward case, because a port-forward IS on ``localhost`` and passes it. The
opt-in is what closes that case; the loopback check only narrows what an opt-in can
then reach. Do not describe it as making the suite safe.

**A SKIP IS ONLY HONEST IF SOMETHING SOMEWHERE REFUSES TO ACCEPT IT.** A suite that
silently skips in the one environment that can run it is worse than no suite,
because the green tick means "not run" while reading as "verified". So
:data:`REQUIRE_ENV` exists: CI sets ``ISAAC_REQUIRE_REAL_ENGINE_PARITY=1``, and
:func:`test_the_real_engine_is_present_when_the_environment_demands_it` then FAILS
instead of skipping if the engine is not reachable — including when it is
unreachable because the opt-in was not given, which is a configuration error in a
job that demanded an engine.

AND THE ORACLE ITSELF IS CONTROLLED
===================================
:func:`test_the_parity_oracle_FAILS_when_a_row_is_mutated_out_of_band` and its
sibling mutate a row behind the application's back and assert the oracle goes RED.
A control suite that can only produce green is not evidence; it is a gap wearing
the costume of one.

NO HOSTED DATABASE IS CONTACTED BY ANYTHING IN THIS FILE. The connection is
whatever the standard libpq environment variables point at, which in CI is a
throwaway container created and destroyed by the job, and which on a developer
machine is nothing at all.
"""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
from typing import Any, Mapping

import pytest

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.workspace as ws

# =============================================================================
# 0. is there an engine, and is one REQUIRED?
# =============================================================================

#: CONSENT TO CONNECT. Mirrors ``db_recon.OPT_IN_ENV`` deliberately, including the
#: "never runs by accident" intent — and this file, unlike ``db_recon``, WRITES.
#: Absent, :func:`_probe_engine` opens nothing and every scenario below skips.
OPT_IN_ENV = "ISAAC_RUN_REAL_ENGINE_PARITY"
OPT_IN_VALUE = "1"

#: Set by CI's ``postgres-migration`` job. When it is set, an unreachable engine is
#: a FAILURE rather than a skip — see the module docstring. It is NOT consent: CI
#: sets :data:`OPT_IN_ENV` too, and setting this one alone is a hard failure rather
#: than a licence to connect.
REQUIRE_ENV = "ISAAC_REQUIRE_REAL_ENGINE_PARITY"

#: Hostnames accepted as loopback WITHOUT a DNS lookup. Resolution is deliberately
#: not performed: a probe that resolved names would make test collection depend on
#: a resolver, and could block. ``localhost`` is accepted because CI and every
#: throwaway local engine use it — which is exactly why this check cannot stand in
#: for the opt-in (a ``kubectl port-forward`` is also ``localhost``).
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain"})


def _is_loopback_element(element: str) -> bool:
    """Is ONE comma-separated ``PGHOST`` element a loopback IP literal or name?

    A LEADING ``/`` — a unix-socket directory — IS REFUSED, AND THAT IS A DELIBERATE
    NARROWING rather than an oversight. It used to return ``True`` "local by
    construction", which is true of the socket itself and was the premise the
    multi-host hole was built on. Three reasons it is refused now:

    1. **Nothing here uses one.** CI's ``postgres-migration`` job sets
       ``PGHOST: 127.0.0.1`` (``.github/workflows/ci.yml``), and no other environment
       in this repository sets ``PGHOST`` at all. Accepting a shape nothing uses buys
       no capability and only widens the predicate.
    2. **It is the one shape whose safety rests on libpq's interpretation rules
       rather than on the string.** A path is not a target this function can reason
       about; it is an instruction to libpq about how to read the rest.
    3. **``sslmode`` is silently inert on it.** libpq does not negotiate TLS over a
       unix socket, so ``connect_psycopg2``'s ``sslmode=require`` default — a real
       part of the write path's defence — provides nothing on a value of this shape,
       and the check would be quietly admitting the one target where it does not
       apply.

    The cost of the narrowing is a SKIP with a stated reason for anyone who genuinely
    runs a local engine over a socket, which is a visible non-result; and in CI it
    cannot be silent at all, because :data:`REQUIRE_ENV` turns an unreachable engine
    into a failure.
    """
    element = element.strip()
    if not element:
        return False
    if element.startswith("/"):
        return False
    if element.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(element.strip("[]")).is_loopback
    except ValueError:
        return False


def _is_loopback_target(host: str) -> bool:
    """Is ``PGHOST`` a local target, decided from the STRING alone?

    ``True`` only when EVERY comma-separated element is a loopback IP literal
    (``127.0.0.0/8``, ``::1``) or one of :data:`_LOOPBACK_NAMES`. ``False`` for every
    hostname — the one shape the hosted database would take — and for a unix-socket
    directory, per :func:`_is_loopback_element`.

    ── ``PGHOST`` IS A LIST, AND THIS FUNCTION USED TO READ IT AS A SCALAR. ──────────
    Measured by an independent security review. libpq accepts a comma-separated
    multi-host ``PGHOST`` and tries the elements in order until one answers. The old
    predicate returned ``True`` for anything starting with ``/`` and never split, so:

        '/tmp,hosted.example'                 -> True   <- PASSED the gate
        '/var/run/postgresql,hosted.example'  -> True   <- PASSED
        '/../../hosted.example'               -> True   <- PASSED

    The whole string reaches libpq verbatim. With no socket at ``/tmp``, the first
    element fails and libpq falls through to ``hosted.example`` — and this suite
    WRITES. The comma cases that were already refused (``'localhost,hosted.example'``,
    ``'127.0.0.1,hosted.example'``) were refused only because ``'localhost,…'`` is not
    equal to ``'localhost'`` and is not a parseable IP: an accident of scalar
    comparison, not a rule, and one that gave no protection to the path branch that
    returned early.

    Splitting first and requiring ALL is what makes it a rule. An empty element is
    refused rather than skipped, because ``PGHOST=',hosted.example'`` means "use the
    default for the first" and a default this function cannot see is not a target it
    can vouch for.

    NEITHER THIS NOR ``PGHOSTADDR`` IS THE GATE. ``ISAAC_RUN_REAL_ENGINE_PARITY`` is,
    and it is checked first. This is defence in depth on a check that, on three
    measured inputs, did not defend.
    """
    host = (host or "").strip()
    if not host:
        return False
    return all(_is_loopback_element(element) for element in host.split(","))


def _probe_engine(env: Mapping[str, str] | None = None) -> tuple[bool, str]:
    """``(available, reason)``: can this process reach a migrated app database?

    **THE FIRST GATE IS CONSENT, AND IT IS CHECKED BEFORE ANYTHING ELSE IS READ.**
    Without :data:`OPT_IN_ENV` this function returns ``False`` having opened
    nothing — because it runs at IMPORT time under a bare ``pytest``, and the
    scenarios it enables WRITE. See the module docstring for the specific accident
    this closes.

    After consent it probes for the WHOLE precondition rather than just ``PGHOST``:
    the target must be loopback, the driver must be importable, the ``PGDATABASE``
    gate must pass, the server must answer, and ``isaac_runs`` must exist. Anything
    less and the suite would fail for a reason that has nothing to do with parity.

    Note what the ``PGDATABASE`` gate is and is not: it pins the name to
    ``metadata_assistant``, which is the HOSTED database's own name, so it rejects a
    misconfigured target and discriminates nothing about WHICH server is being
    reached. It is a sanity check, never a safety boundary.

    It opens ONE short-lived transaction through the application's own write path,
    so it inherits the timeouts, the database gate and the statement policy. It
    writes nothing.
    """
    env = os.environ if env is None else env
    if (env.get(OPT_IN_ENV) or "").strip() != OPT_IN_VALUE:
        return False, (
            f"{OPT_IN_ENV} is not {OPT_IN_VALUE!r}: this suite WRITES, so it never "
            "connects by accident. Set it only against a throwaway engine."
        )
    if not dbw.database_configured(env):
        return False, "no PGHOST: this suite needs a real PostgreSQL (CI's postgres:18)"
    host = (env.get("PGHOST") or "").strip()
    if not _is_loopback_target(host):
        return False, (
            f"PGHOST={host!r} is not a loopback target; this suite runs only against "
            "a local throwaway engine"
        )
    # ── `PGHOSTADDR` DEFEATED THE CHECK DIRECTLY ABOVE, AND IS REFUSED OUTRIGHT. ──────
    # Measured by an independent security review on 2026-08-24. `_is_loopback_target`
    # reads the `PGHOST` STRING, and libpq fills every unspecified connection parameter
    # from the matching `PG*` variable — so when `PGHOSTADDR` is also set it is the
    # address libpq CONNECTS to, while `host` is used only for TLS/GSSAPI name
    # verification. `PGHOST=localhost` + `PGHOSTADDR=<a hosted address>` +
    # `PGDATABASE=metadata_assistant` therefore passed every gate in this function AND
    # `write_transaction`'s own `current_database()` re-check — which asks the server it
    # is talking to, so it agrees with itself — and this suite, which WRITES, would have
    # written there.
    #
    # `db_write.connect_psycopg2` now passes `hostaddr=None` explicitly, which is the
    # real fix and makes libpq ignore the variable. This refusal is the second half:
    # an environment that sets `PGHOSTADDR` at all is one whose author intends a target
    # this suite cannot verify, so it declines rather than proceeding on the strength of
    # a keyword argument in another module. Refused rather than ignored, because a
    # SKIPPED suite is a visible non-result and a silently-redirected one is not.
    #
    # NEITHER HALF IS THE GATE. `ISAAC_RUN_REAL_ENGINE_PARITY` is, and it is checked
    # first and unconditionally. This is defence in depth on a check that, until now,
    # did not defend — and saying that plainly is better than implying the suite was
    # ever safe by accident.
    hostaddr = (env.get("PGHOSTADDR") or "").strip()
    if hostaddr:
        return False, (
            "PGHOSTADDR is set. libpq would connect to that address while PGHOST was "
            "used only for TLS name verification, so the loopback check above cannot "
            "speak for the target this suite would WRITE to. Unset it."
        )
    try:
        dbw.pgdatabase_gate(env)
    except dbw.WriteRefused as exc:
        return False, f"the PGDATABASE gate refused this environment: {exc}"
    try:
        with dbw.write_transaction(env) as (cursor, policy):
            cursor.execute(policy.check(repo.Q_RUN_TABLE_PRESENT), (repo.RUN_TABLE,))
            row = cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
        return False, f"could not reach the database ({type(exc).__name__})"
    if not row or row[0] is None:
        return False, "isaac_runs does not exist: migration 0002_runs is not applied"
    return True, "a real engine with 0002_runs applied is reachable"


_AVAILABLE, _REASON = _probe_engine()

#: Applied to every parity test individually rather than as a module-level
#: ``pytestmark``, because ONE test in this file must stay collected and runnable
#: when the engine is absent: the one that turns an unexpected absence into a
#: failure.
real_engine = pytest.mark.skipif(not _AVAILABLE, reason=_REASON)


def test_the_real_engine_is_present_when_the_environment_demands_it():
    """THE ANTI-SILENT-SKIP GUARD. Not itself a parity assertion.

    Locally this skips, and says why. In CI, where ``ISAAC_REQUIRE_REAL_ENGINE_PARITY``
    is set, it FAILS if the engine is not reachable — so the whole suite quietly
    skipping in the only place it can run is a red build, not a green one.

    A job that sets :data:`REQUIRE_ENV` but forgets :data:`OPT_IN_ENV` fails here
    too, and that is deliberate: the probe's refusal reason names the missing
    variable, so the failure reads as the configuration error it is rather than as
    an unreachable database.
    """
    if os.environ.get(REQUIRE_ENV) != "1":
        pytest.skip(
            f"{REQUIRE_ENV} is not set, so a real engine is optional here. "
            f"Probe result: {_REASON}"
        )
    assert _AVAILABLE, (
        f"{REQUIRE_ENV}=1 demands a real engine and this one is unusable: {_REASON}"
    )


def _refuse_to_connect(*_args, **_kwargs):
    raise AssertionError(
        "the probe opened a connection when it must not have: this is the accident "
        "the opt-in exists to prevent"
    )


def test_the_suite_does_NOT_activate_without_the_explicit_opt_in(monkeypatch):
    """THE GATE, ASSERTED AT THE ONE INPUT THAT USED TO BE DANGEROUS.

    A fully configured libpq environment pointing at a database whose name passes
    the ``PGDATABASE`` gate — which is to say, the exact environment the
    port-forward at ``docs/postgres-test-db-guide.md:83-96`` produces — and NO
    opt-in. The probe must report unavailable AND must not have opened anything.

    ``write_transaction`` and ``connect_psycopg2`` are both replaced with a raiser,
    so "it did not connect" is measured rather than inferred from the return value:
    a future probe that connected first and gated afterwards would still return
    ``False`` here, and would still have written a connection to the owner's
    database.
    """
    monkeypatch.setattr(dbw, "write_transaction", _refuse_to_connect)
    monkeypatch.setattr(dbw, "connect_psycopg2", _refuse_to_connect)

    port_forwarded = {
        "PGHOST": "localhost",
        "PGPORT": "5432",
        "PGUSER": "metadata_assistant",
        "PGPASSWORD": "irrelevant-to-this-test",
        "PGDATABASE": "metadata_assistant",
    }
    available, reason = _probe_engine(port_forwarded)
    assert available is False
    assert OPT_IN_ENV in reason, reason

    # The same environment, with an opt-in that is present but not exactly "1",
    # is still refused — a truthy-looking value is not consent.
    for near_miss in ("0", "true", "yes", "", " "):
        available, reason = _probe_engine(dict(port_forwarded, **{OPT_IN_ENV: near_miss}))
        assert available is False, near_miss
        assert OPT_IN_ENV in reason, reason

    # And REQUIRE without RUN is not consent either: demanding an engine does not
    # authorise reaching for one.
    available, reason = _probe_engine(dict(port_forwarded, **{REQUIRE_ENV: "1"}))
    assert available is False
    assert OPT_IN_ENV in reason, reason


def test_the_opt_in_alone_does_not_admit_a_non_loopback_target(monkeypatch):
    """DEFENCE IN DEPTH, AND ITS LIMIT, BOTH ASSERTED.

    With consent given, a ``PGHOST`` that is a HOSTNAME is still refused without a
    connection being opened. That is the belt.

    The second half is the honest one, and it is asserted so nobody can read the
    first half as more than it is: ``localhost`` — a port-forward — PASSES the
    loopback check and reaches the connection attempt. The loopback check narrows
    what an opt-in can reach; it does not make an accidental run safe. Only the
    opt-in does that.
    """
    monkeypatch.setattr(dbw, "write_transaction", _refuse_to_connect)
    monkeypatch.setattr(dbw, "connect_psycopg2", _refuse_to_connect)
    consented = {
        OPT_IN_ENV: OPT_IN_VALUE,
        "PGUSER": "metadata_assistant",
        "PGPASSWORD": "irrelevant-to-this-test",
        "PGDATABASE": "metadata_assistant",
    }

    for remote in ("isaac-psql-rw.isaac-psql.svc.cluster.local", "10.0.0.5", "db.example"):
        available, reason = _probe_engine(dict(consented, PGHOST=remote))
        assert available is False, remote
        assert "loopback" in reason, reason

    # No PGHOST at all is refused before the loopback question is even asked.
    available, reason = _probe_engine(dict(consented))
    assert available is False
    assert "PGHOST" in reason

    # ── `PGHOST` IS A LIST, AND THE PREDICATE READ IT AS A SCALAR. ───────────────────
    # Measured by an independent security review. libpq accepts a comma-separated
    # multi-host `PGHOST` and tries the elements in order until one answers; the whole
    # string reaches it verbatim. The predicate returned True for ANYTHING starting
    # with `/` and never split, so the first three below PASSED the gate — with no
    # socket at `/tmp`, libpq falls straight through to `hosted.example`, and this
    # suite WRITES. The last two were refused, but only by the accident that
    # `'localhost,…'` is neither equal to `'localhost'` nor a parseable IP address:
    # scalar comparison, not a rule, and it protected the path branch not at all.
    #
    # A SECOND REASON THE PATH SHAPE IS NOW REFUSED OUTRIGHT: libpq does not negotiate
    # TLS over a unix socket, so `connect_psycopg2`'s `sslmode=require` default is
    # inert on a leading-slash value.
    for smuggled in (
        "/tmp,hosted.example",
        "/var/run/postgresql,hosted.example",
        "/../../hosted.example",
        "localhost,hosted.example",
        "127.0.0.1,hosted.example",
        # ...and the mixed-order forms, so the rule is "every element", not "the first".
        "hosted.example,127.0.0.1",
        "127.0.0.1,10.0.0.5",
        # An EMPTY element means "use the default", which this function cannot see.
        ",hosted.example",
        "127.0.0.1,",
    ):
        assert _is_loopback_target(smuggled) is False, smuggled
        available, reason = _probe_engine(dict(consented, PGHOST=smuggled))
        assert available is False, smuggled
        assert "loopback" in reason, reason

    # ALREADY REFUSED BEFORE THE SPLIT, AND STILL REFUSED AFTER IT. Each is a shape
    # that reads as loopback to a human and is not one to `ipaddress`:
    # `::ffff:127.0.0.1` is an IPv4-mapped IPv6 address and `is_loopback` is False for
    # it; `0.0.0.0` is unspecified, not loopback; `0177.0.0.1` is an octal spelling
    # `ipaddress` refuses outright; and `localhost.` is the fully-qualified root form,
    # which is not the string `localhost`. Pinned so the multi-host change cannot
    # loosen any of them.
    for refused in ("::ffff:127.0.0.1", "0.0.0.0", "0177.0.0.1", "localhost."):
        assert _is_loopback_target(refused) is False, refused
        available, reason = _probe_engine(dict(consented, PGHOST=refused))
        assert available is False, refused
        assert "loopback" in reason, reason

    # A UNIX-SOCKET DIRECTORY IS NOW REFUSED TOO, deliberately — see
    # `_is_loopback_element`. Nothing in this repository sets such a `PGHOST` (CI sets
    # `127.0.0.1`), so the narrowing costs a stated skip and no capability.
    for socket_dir in ("/var/run/pg", "/tmp", "/var/run/postgresql"):
        assert _is_loopback_target(socket_dir) is False, socket_dir

    # THE LIMIT. A loopback target gets past every string gate and is refused only
    # by the connection attempt itself — here, by the raiser standing in for it.
    for local in ("127.0.0.1", "127.0.0.53", "::1", "[::1]", "localhost", "LocalHost"):
        assert _is_loopback_target(local) is True, local
        available, reason = _probe_engine(dict(consented, PGHOST=local))
        assert available is False, local
        assert "could not reach the database (AssertionError)" == reason, reason


def test_PGHOSTADDR_is_refused_because_the_loopback_check_cannot_see_it(monkeypatch):
    """THE HOLE THE LOOPBACK CHECK HAD, and the reason a string check is not a target
    check.

    Measured by an independent security review on 2026-08-24, by reading libpq's
    parameter precedence and this suite's own gates rather than by connecting. libpq
    fills every unspecified connection parameter from the matching `PG*` variable, and
    when `hostaddr` is set it is the address that is CONNECTED to while `host` is used
    only for TLS certificate and GSSAPI name verification. So this environment —

        PGHOST=localhost   PGHOSTADDR=<a hosted address>   PGDATABASE=metadata_assistant

    — passed `_is_loopback_target`, passed `pgdatabase_gate`, and would have passed
    `write_transaction`'s own `current_database()` re-check, because that check asks the
    server it is talking to and therefore agrees with itself. This suite WRITES.

    Two changes, and this asserts the one that lives here. `db_write.connect_psycopg2`
    now passes `hostaddr=None` explicitly, which is the real fix; the probe additionally
    REFUSES an environment that sets the variable, because an author who sets it intends
    a target this suite cannot verify, and a skipped suite is a visible non-result while
    a silently-redirected one is not.

    NEITHER IS THE GATE. `ISAAC_RUN_REAL_ENGINE_PARITY` is, and it is checked first. This
    is defence in depth on a check that until now did not defend.
    """
    monkeypatch.setattr(dbw, "write_transaction", _refuse_to_connect)
    monkeypatch.setattr(dbw, "connect_psycopg2", _refuse_to_connect)
    smuggled = {
        OPT_IN_ENV: OPT_IN_VALUE,
        "PGHOST": "localhost",
        "PGHOSTADDR": "10.42.7.9",
        "PGUSER": "metadata_assistant",
        "PGPASSWORD": "irrelevant-to-this-test",
        "PGDATABASE": "metadata_assistant",
    }
    # The premise, asserted rather than assumed: every OTHER gate says yes.
    assert _is_loopback_target(smuggled["PGHOST"]) is True
    dbw.pgdatabase_gate(smuggled)  # raises WriteRefused if it disagreed

    available, reason = _probe_engine(smuggled)
    assert available is False
    assert "PGHOSTADDR" in reason, reason

    # AND IT IS THE VARIABLE, NOT THE HOST, THAT DECIDES. The same environment without
    # it reaches the connection attempt — the raiser — which is the documented limit of
    # every string gate in this function.
    without = {k: v for k, v in smuggled.items() if k != "PGHOSTADDR"}
    available, reason = _probe_engine(without)
    assert available is False
    assert "could not reach the database (AssertionError)" == reason, reason

    # An EMPTY or whitespace value is not "set": libpq ignores it, so refusing would be
    # a false positive that made a legitimate environment unusable for no gain.
    for blank in ("", "   "):
        available, reason = _probe_engine(dict(without, PGHOSTADDR=blank))
        assert "PGHOSTADDR" not in reason, blank


def test_connect_psycopg2_pins_hostaddr_so_libpq_cannot_fill_it_from_the_environment():
    """THE REAL FIX, ASSERTED WHERE IT ACTUALLY HAPPENS — and the first version of this
    test asserted it one layer too early and so passed over an INERT fix.

    THE FAILURE THIS TEST NOW EXISTS TO PREVENT. Version 1 injected a fake `psycopg2`
    whose `connect` merely recorded its keyword arguments, and asserted
    ``seen["hostaddr"] is None``. That passed. It also could not fail, because the real
    `psycopg2.connect` DOES NOT HAND ITS KEYWORDS TO libpq — it builds a DSN with
    `psycopg2.extensions.make_dsn`, which contains, verbatim::

        # Drop the None arguments
        kwargs = {k: v for (k, v) in kwargs.items() if v is not None}

    So `hostaddr=None` was deleted before libpq saw it, the DSN went out with no
    `hostaddr`, and libpq read `PGHOSTADDR` from the environment exactly as before. The
    application shipped a guard that did nothing and a comment asserting that it worked,
    and a green test between them.

    TWO ASSERTIONS AT TWO LAYERS, deliberately:

    * the CALL still binds the keyword — checkable in any interpreter, with the fake
      driver, and it is what catches a "fix" that renames or drops the parameter;
    * the DSN still CARRIES it — checked against the REAL `make_dsn` when psycopg2 is
      importable, and skipped when it is not. This is the layer version 1 could not
      see, and it is the one the guarantee actually rests on.

    Measured in an interpreter with psycopg2 present::

        make_dsn(host="localhost", dbname="d", hostaddr=None) -> 'host=localhost dbname=d'
        make_dsn(host="localhost", dbname="d", hostaddr="")   -> "... hostaddr=''"

    Still narrower than "the connection goes to PGHOST": no socket is opened here, and no
    agent may connect to the SLAC database. What is established is that libpq is TOLD an
    explicit `hostaddr`, which is what stops it consulting `PGHOSTADDR`; the rest rests on
    libpq's documented precedence.
    """
    import sys
    import types

    seen: dict = {}

    fake = types.ModuleType("psycopg2")
    fake.connect = lambda **kwargs: seen.update(kwargs) or object()  # type: ignore[attr-defined]
    real = sys.modules.get("psycopg2")
    sys.modules["psycopg2"] = fake
    try:
        dbw.connect_psycopg2(
            {
                "PGHOST": "localhost",
                "PGUSER": "metadata_assistant",
                "PGPASSWORD": "irrelevant-to-this-test",
                "PGHOSTADDR": "10.42.7.9",
            }
        )
    finally:
        if real is None:
            del sys.modules["psycopg2"]
        else:  # pragma: no cover - psycopg2 is not installed in this interpreter
            sys.modules["psycopg2"] = real

    assert "hostaddr" in seen, sorted(seen)
    # EMPTY STRING, NOT `None` — `None` is dropped by `make_dsn` and never reaches libpq.
    assert seen["hostaddr"] == "", repr(seen["hostaddr"])

    # LAYER 2: the keyword must SURVIVE INTO THE DSN. This is what version 1 missed.
    make_dsn = pytest.importorskip(
        "psycopg2.extensions",
        reason="psycopg2 is not installed in this interpreter; the CI PostgreSQL job "
        "has it and runs this assertion there.",
    ).make_dsn
    dsn = make_dsn(**{k: v for k, v in seen.items() if k != "connect_timeout"})
    assert "hostaddr" in dsn, dsn
    # And the control that proves the assertion above can fail: the value the fix
    # replaced is dropped by the same function.
    assert "hostaddr" not in make_dsn(host="localhost", dbname="d", hostaddr=None)
    # THE ENVIRONMENT'S VALUE IS NOT FORWARDED UNDER ANY OTHER NAME EITHER, which is the
    # failure mode a "fix" that renamed the parameter would have.
    assert "10.42.7.9" not in {str(v) for v in seen.values()}, seen
    assert seen["host"] == "localhost"
    # AND THE DATABASE IS STILL NEVER THE ENV VALUE — the gate pinned it, and this call
    # has always used the constant. Asserted so the edit above cannot have moved it.
    assert seen["dbname"] == dbw.EXPECTED_DATABASE


# =============================================================================
# 1. reading the table — the TEST's own statements, never the application's
# =============================================================================
#
# These are TEST statements. They are defined here rather than in the application
# for a reason that is a rule and not a preference: `db_write`'s primary guarantee
# is that every statement the WRITE PATH issues is a module-level constant in the
# application, and adding a test-only read to `experiment_repository` would put a
# statement in the application that the application never issues — and would make
# the "no read path names isaac_runs" enumeration in
# `test_0002_is_now_written_by_the_write_path_and_by_nothing_else` false. They
# still go through `policy.check(...)`, so they are bound by the same owned-table
# and forbidden-verb rules as everything else.

#: Every column of every run row in the database, including the two SERVER-SIDE row
#: stamps the application never reads. ``updated_utc`` is how a real engine answers
#: "did this save TOUCH this row", which no in-process fake can answer at all.
Q_TEST_ALL_RUN_ROWS = (
    "SELECT run_id, experiment_id, ordinal, state, rev, generation,"
    " created_utc, updated_utc FROM isaac_runs"
)

#: The same, narrowed to one experiment.
Q_TEST_RUN_ROWS_FOR = Q_TEST_ALL_RUN_ROWS + " WHERE experiment_id = %s"

#: THE OUT-OF-BAND MUTATION the oracle's own control test uses. It is a legal,
#: policy-passing statement against an owned table, issued by the TEST — which is
#: precisely the situation a shadow row can find itself in and the application
#: cannot notice, because nothing in the application ever reads the row back.
Q_TEST_SHIFT_ORDINALS = (
    "UPDATE isaac_runs SET ordinal = ordinal + 1 WHERE experiment_id = %s"
)

#: The second control: a row that has simply gone.
Q_TEST_DELETE_RUNS_OF = "DELETE FROM isaac_runs WHERE experiment_id = %s"

#: DRIFT IN THE DOCUMENT ONLY, with every promoted column left exactly as it was.
#: This is the shape that tells apart a diff comparing ``state`` from one comparing
#: only ``(ordinal, rev, generation)`` — see
#: :func:`test_the_diff_compares_the_DOCUMENT_and_repairs_a_tampered_row`.
Q_TEST_TAMPER_WITH_A_RUN_LABEL = (
    "UPDATE isaac_runs SET state = jsonb_set(state, '{label}',"
    " '\"TAMPERED-OUT-OF-BAND\"') WHERE run_id = %s"
)


def _as_document(value: Any) -> Any:
    """A ``jsonb`` column as a PARSED DOCUMENT, whatever the driver handed back.

    psycopg2 registers a jsonb loader and returns a ``dict``; a build without it
    returns text. Comparing as TEXT would be wrong in the direction that matters:
    ``jsonb`` normalises key order and whitespace on the way in, so a text
    comparison reports a difference on every single save and would make a broken
    diff look like a working one. The application's own ``_stored_run_rows``
    applies the same tolerance for the same reason.
    """
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


def _query(sql: str, params: tuple | None = None) -> list[tuple]:
    """Run one read against the real engine through the application's write path."""
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(sql), params)
        return list(cursor.fetchall() or [])


def _execute(sql: str, params: tuple | None = None) -> int:
    """Run one out-of-band statement. Used ONLY by the oracle's control tests."""
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(sql), params)
        return cursor.rowcount


def _full_rows(experiment_id: str | None = None) -> dict[str, tuple]:
    """``run_id -> every column``, with ``state`` parsed. The whole table, or one
    experiment's slice of it.

    Includes ``created_utc``/``updated_utc``, so "these rows did not move" is a
    claim about the SERVER's own stamps and not about what the test re-derived.
    """
    if experiment_id is None:
        rows = _query(Q_TEST_ALL_RUN_ROWS)
    else:
        rows = _query(Q_TEST_RUN_ROWS_FOR, (experiment_id,))
    return {
        row[0]: (row[1], row[2], _as_document(row[3]), row[4], row[5], row[6], row[7])
        for row in rows
    }


# =============================================================================
# 2. THE ORACLE
# =============================================================================


def _observed(experiment_id: str) -> list[tuple]:
    """``(run_id, ordinal, state, rev, generation)`` for every row of one experiment."""
    rows = _query(
        "SELECT run_id, ordinal, state, rev, generation FROM isaac_runs"
        " WHERE experiment_id = %s",
        (experiment_id,),
    )
    return sorted(
        ((row[0], row[1], _as_document(row[2]), row[3], row[4]) for row in rows),
        key=lambda row: row[0],
    )


def _expected(exp: "ws.Experiment") -> list[tuple]:
    """The same tuple, projected from the AUTHORITATIVE document."""
    return sorted(
        (
            (run.id, run.ordinal, run.to_state(), run.rev, run.generation)
            for run in exp.sorted_runs()
        ),
        key=lambda row: row[0],
    )


def assert_parity(exp: "ws.Experiment") -> None:
    """THE ORACLE. The rows for ``exp`` ARE ``exp.sorted_runs()``, column by column.

    ``sorted(...)`` is keyed on the run id EXPLICITLY. The natural
    ``sorted(list_of_tuples)`` would compare the tuples element by element and, on
    an ordinal tie, would reach the ``state`` DICT — which is unorderable and would
    raise ``TypeError`` instead of failing the assertion. Run ids are unique (the
    primary key on one side, ``_hydrate_runs`` dropping duplicates on the other),
    so keying on the id is a total order that never has to look further.

    ``state`` is compared as a PARSED DOCUMENT, never as text: the column is
    ``jsonb`` and normalises key order and whitespace on the way in.

    The ``experiment_id`` COLUMN is deliberately not part of the tuple — the
    ``WHERE`` already pinned it, so every row returned carries it by construction.
    The document's own ``experiment_id`` IS compared, inside ``state``, which is
    what the legacy-empty-string case turns on.
    """
    observed = _observed(exp.id)
    expected = _expected(exp)
    assert observed == expected, (
        "isaac_runs disagrees with the experiment document.\n"
        f"  rows:     {observed}\n"
        f"  document: {expected}"
    )


# =============================================================================
# 3. fixtures and helpers
# =============================================================================


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A private ordinary-scope workspace, with the REAL database left configured.

    ``PGHOST`` and friends are deliberately NOT cleared — this suite exists to talk
    to the engine. Only the workspace directory is redirected, so each test gets
    its own working copy and cannot see another's files.
    """
    root = tmp_path / "ws"
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(root))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    return root


def _new_experiment(title: str) -> "ws.Experiment":
    """Create an ordinary experiment through the real repository seam.

    Asserts the DURABLE backend was selected. Without that, a misconfigured
    environment would silently exercise the filesystem repository and every parity
    assertion below would be reading an empty table and comparing it against an
    experiment with no runs — green, and meaningless.
    """
    repository = repo.repository()
    assert repository.backend == repo.BACKEND_POSTGRES, repository.backend
    return repository.create(title=title, description=None)


def _with_runs(title: str, count: int) -> "ws.Experiment":
    """An experiment carrying ``count`` runs, persisted in ONE versioned save."""
    exp = _new_experiment(title)
    for index in range(count):
        exp.add_run(label=f"run {index}")
    if count:
        assert exp.save_versioned() is True
    return exp


def _envelope(value: str) -> dict:
    """A draft field envelope. Synthetic, and unmistakably so.

    ``status``/``evidence`` are present because the draft shape carries them, not
    because anything here is asserting a scientific claim: the value is a fixture
    string, and no test in this file reads it as science.
    """
    return {
        "value": value,
        "status": "verified",
        "evidence": [{"source_type": "user_confirmation", "detail": "synthetic fixture"}],
    }


# =============================================================================
# 4. the scenarios
# =============================================================================


@real_engine
def test_parity_an_experiment_with_no_runs_leaves_isaac_runs_holding_no_row_for_it(
    workspace,
):
    """ZERO IS A ROW COUNT, NOT AN ABSENCE OF EVIDENCE — and the neighbours matter.

    The interesting half is the second assertion. ``Q_DELETE_ABSENT_RUNS`` deletes
    "every row of this experiment the document no longer names", and a predicate
    that lost its ``experiment_id`` clause would still leave THIS experiment with
    no rows while quietly emptying every other experiment's. So a run-less save is
    checked against a SNAPSHOT OF THE WHOLE TABLE, stamps included.
    """
    neighbour = _with_runs("parity: the neighbour that must not move", 2)
    assert_parity(neighbour)
    before = _full_rows()
    assert len(before) >= 2

    empty = _new_experiment("parity: no runs at all")
    assert empty.runs == []
    assert _observed(empty.id) == []
    assert_parity(empty)

    # A second save, this time versioned, so the run-less path is exercised on both
    # of the application's persistence primitives.
    empty.title = "parity: still no runs"
    assert empty.save_versioned() is True
    assert _observed(empty.id) == []

    assert _full_rows() == before, "a run-less save disturbed another experiment's rows"


@real_engine
def test_parity_one_run_produces_exactly_one_row_equal_to_its_to_state(workspace):
    """The base case, stated in full rather than by the oracle alone.

    The oracle compares tuples; this also asserts the DOCUMENT is ``to_state()``
    verbatim — every key, including the ``experiment_id`` duplication and the empty
    ``overrides`` map that ``to_state`` always emits. Nothing is dropped, cleaned or
    reordered on the way into ``jsonb``.
    """
    exp = _with_runs("parity: exactly one", 1)
    (run,) = exp.runs

    rows = _full_rows(exp.id)
    assert list(rows) == [run.id]
    experiment_id, ordinal, state, rev, generation, _created, _updated = rows[run.id]
    assert experiment_id == exp.id
    assert ordinal == run.ordinal
    assert rev == run.rev
    assert generation == run.generation
    assert state == run.to_state()
    # The document really does carry every key, so "verbatim" is a measured claim.
    assert set(state) == {
        "id",
        "experiment_id",
        "label",
        "ordinal",
        "created_utc",
        "draft",
        "record_id",
        "overrides",
        "rev",
        "updated_utc",
        "generation",
    }
    assert_parity(exp)


@real_engine
@pytest.mark.parametrize("n", [1, 2, 50, 200])
def test_parity_holds_at_every_run_count_from_one_to_two_hundred(workspace, n):
    """THE COUNT IS NOT A DETAIL. Different things break at different sizes.

    ``1`` and ``2`` are the ordinary shapes. ``50`` and ``200`` are where a diff
    that silently degraded into a blanket rewrite would still be CORRECT and would
    be issuing N+1 statements under a 15-second per-statement timeout.

    ``0`` WAS A PARAMETER HERE AND IS REMOVED, because it was vacuous and its
    justification was false. ``_with_runs`` never saves at ``count == 0``, so the
    body reduced to ``0 == 0`` twice and an oracle comparing ``[] == []`` — it
    passed with the shadow write deleted entirely. And the claim it carried — that
    ``0`` is "the one save where ``Q_DELETE_ABSENT_RUNS``' ``%s::text[]`` cast is
    load-bearing" — is not true of this parameter at all: the delete is issued only
    when ``set(stored) - set(desired_ids)`` is non-empty, and an experiment that
    never had a run has nothing stored, so no delete is ever issued. The empty
    array is genuinely bound by the drop-every-run tail below and by
    :func:`test_the_delete_of_the_last_run_binds_the_empty_text_array`; the
    run-less save itself is covered by
    :func:`test_parity_an_experiment_with_no_runs_leaves_isaac_runs_holding_no_row_for_it`
    and :func:`test_a_byte_identical_re_save_of_a_run_less_experiment_still_holds`.

    A row-count equality is asserted BESIDE the oracle deliberately: the oracle
    compares two sorted lists, and two lists can only be equal if they are the same
    length — but stating the count separately is what makes a failure legible as
    "the table has the wrong number of rows" rather than as a wall of tuples.
    """
    exp = _with_runs(f"parity: {n} runs", n)
    assert len(exp.runs) == n
    assert len(_observed(exp.id)) == n
    assert_parity(exp)

    # And the set really is a function of the document, not of insertion history:
    # drop every run and the table follows. Unconditional now that ``n >= 1``,
    # which is also what makes the empty ``%s::text[]`` binding reachable from
    # every parameter rather than from none.
    exp.runs = []
    assert exp.save_versioned() is True
    assert _observed(exp.id) == []
    assert_parity(exp)


@real_engine
def test_parity_an_inherited_address_is_absent_from_the_run_row_because_absence_is_the_inheritance(
    workspace,
):
    """CONTRACT §2 D2, VISIBLE IN THE TABLE: a run stores only the ABSENCE.

    ``workspace.py``'s ``Run.overrides`` says it directly — "THE ABSENCE OF A KEY IS
    THE INHERITANCE. Nothing is copied down from the experiment." This asserts the
    shadow row honours that. If a future writer ever "helpfully" materialised the
    resolved view into the row, every experiment-level edit would silently stop
    flowing through to its runs, and the table would be the place that lied.

    Both halves are asserted, because only the pair means anything: the inherited
    content is ABSENT from the row, and ``resolve_inherited`` nonetheless reports it
    for that run. Absence without live resolution would just be data loss.
    """
    exp = _new_experiment("parity: inheritance is an absence")
    exp.draft = {
        "fields": {"sample.material.name": _envelope("SYNTHETIC-FIXTURE-MATERIAL")},
        "attribution": {"contributors": [{"name": "Synthetic Fixture"}]},
        "tags": ["synthetic-campaign"],
    }
    run = exp.add_run(label="inherits everything")
    assert exp.save_versioned() is True

    rows = _full_rows(exp.id)
    state = rows[run.id][2]

    # The run's own draft is empty and its override map is empty...
    assert state["draft"] == {}
    assert state["overrides"] == {}
    # ...and no trace of the experiment-level content reached the row, in any key.
    blob = json.dumps(state, sort_keys=True)
    assert "SYNTHETIC-FIXTURE-MATERIAL" not in blob
    assert "synthetic-campaign" not in blob
    assert "Synthetic Fixture" not in blob

    # THE OTHER HALF: the run really does inherit, computed on read.
    resolved = exp.resolve_run(run)
    inherited = resolved[ws.field_address("sample.material.name")]
    assert inherited.provenance == ws.PROVENANCE_INHERITED
    assert inherited.value == "SYNTHETIC-FIXTURE-MATERIAL"
    assert resolved[ws.block_address("tags")].payload == ["synthetic-campaign"]

    assert_parity(exp)


@real_engine
def test_parity_an_override_and_its_displaced_payload_round_trip_verbatim(workspace):
    """AN OVERRIDE IS AUDITED STATE, so the row must carry ALL THREE of its parts.

    ``payload`` (what this run says), ``recorded_utc`` (when the displacement was
    recorded) and ``displaced`` (what the experiment said AT THAT MOMENT). The third
    is the one a projection is tempted to drop, and it is the one contract §2 D2
    requires: an override records what it displaced. It is also a HISTORICAL fact —
    so the test edits the experiment afterwards and asserts ``displaced`` did NOT
    follow, which is the difference between a captured record and a live alias.
    """
    exp = _new_experiment("parity: an override survives verbatim")
    address = ws.field_address("sample.material.name")
    exp.draft = {"fields": {"sample.material.name": _envelope("EXPERIMENT-LEVEL-VALUE")}}
    run = exp.add_run(label="overrides one address")
    override = exp.set_run_override(run, address, _envelope("RUN-LEVEL-VALUE"))
    assert exp.save_versioned() is True

    state = _full_rows(exp.id)[run.id][2]
    assert set(state["overrides"]) == {address}
    stored = state["overrides"][address]
    assert stored == override.to_state()
    assert stored["payload"]["value"] == "RUN-LEVEL-VALUE"
    assert stored["recorded_utc"] == override.recorded_utc
    assert stored["displaced"]["value"] == "EXPERIMENT-LEVEL-VALUE"
    assert_parity(exp)

    # HISTORY IS NOT REFRESHED. Editing the experiment moves what is INHERITED and
    # leaves what was DISPLACED exactly where it was.
    exp.draft["fields"]["sample.material.name"] = _envelope("EDITED-AFTERWARDS")
    assert exp.save_versioned() is True
    after = _full_rows(exp.id)[run.id][2]
    assert after["overrides"][address]["displaced"]["value"] == "EXPERIMENT-LEVEL-VALUE"
    assert_parity(exp)


@real_engine
def test_parity_clearing_an_override_removes_the_address_from_the_row(workspace):
    """THE SIBLING OF THE TEST ABOVE, and the direction a projection gets wrong.

    Adding a key to a document is easy to project. REMOVING one is where a writer
    that merges instead of replacing leaves the old key behind — and since nothing
    reads this table, a stale override would sit there indefinitely, invisible.
    """
    exp = _new_experiment("parity: clearing an override")
    address = ws.field_address("sample.material.name")
    exp.draft = {"fields": {"sample.material.name": _envelope("EXPERIMENT-LEVEL-VALUE")}}
    run = exp.add_run(label="overrides then inherits")
    exp.set_run_override(run, address, _envelope("RUN-LEVEL-VALUE"))
    assert exp.save_versioned() is True
    assert set(_full_rows(exp.id)[run.id][2]["overrides"]) == {address}

    assert exp.clear_run_override(run, address) is True
    assert exp.save_versioned() is True

    state = _full_rows(exp.id)[run.id][2]
    assert state["overrides"] == {}, "a cleared override survived in the shadow row"
    blob = json.dumps(state, sort_keys=True)
    assert "RUN-LEVEL-VALUE" not in blob
    assert_parity(exp)


@real_engine
def test_parity_a_versioned_save_moves_only_the_changed_runs_rev_and_the_row_agrees(
    workspace,
):
    """THE DIFF, PROVEN BY THE SERVER'S OWN STAMPS.

    ``_write_run_rows`` skips a run whose stored columns already equal the desired
    ones. Only a real engine can check that, and it checks it through
    ``updated_utc``, which ``Q_UPSERT_RUN`` stamps ``now()`` on every ACCEPTED
    update. If the stored ``jsonb`` document ever compared unequal to
    ``Run.to_state()`` — the text-vs-document defect the in-process fake cannot
    catch — all three stamps would move here and this test would go red.
    """
    exp = _with_runs("parity: only the changed run moves", 3)
    before = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}
    assert len(before) == 3
    revs_before = {run.id: run.rev for run in exp.runs}

    edited = exp.sorted_runs()[1]
    edited.draft = {"fields": {"context.temperature_K": _envelope("77")}}
    assert exp.save_versioned() is True

    # THE DOCUMENT: exactly one rev moved.
    moved = [run.id for run in exp.runs if run.rev != revs_before[run.id]]
    assert moved == [edited.id], moved
    assert edited.rev == revs_before[edited.id] + 1

    # THE ROWS AGREE — and the two untouched rows were not even rewritten.
    after = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}
    assert after[edited.id] != before[edited.id], "the changed run's row was not written"
    for run in exp.sorted_runs():
        if run.id != edited.id:
            assert after[run.id] == before[run.id], (
                f"an unchanged run row was rewritten: {run.id}"
            )
    assert_parity(exp)


@real_engine
def test_parity_reordering_rewrites_only_the_ordinals_that_moved(workspace):
    """A REORDER IS A CONTENT CHANGE FOR THE RUNS THAT MOVED AND FOR NO OTHERS.

    ``ordinal`` is inside ``_run_signature_payload``, so swapping two ordinals
    genuinely changes those two runs and genuinely leaves the third alone. The row
    set must follow exactly that, in both directions: the two that moved are
    rewritten, the one that did not is untouched.
    """
    exp = _with_runs("parity: a reorder", 3)
    ordered = exp.sorted_runs()
    first, second, third = ordered
    before = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}

    first.ordinal, second.ordinal = second.ordinal, first.ordinal
    assert exp.save_versioned() is True

    # The canonical order really did change.
    assert [run.id for run in exp.sorted_runs()] == [second.id, first.id, third.id]

    after = _full_rows(exp.id)
    assert after[first.id][6] != before[first.id]
    assert after[second.id][6] != before[second.id]
    assert after[third.id][6] == before[third.id], "an unmoved run's row was rewritten"
    # The promoted ordinal column follows the document, not the insertion order.
    assert after[first.id][1] == first.ordinal
    assert after[second.id][1] == second.ordinal
    assert_parity(exp)


@real_engine
def test_parity_a_run_added_later_appears_without_rewriting_its_siblings(workspace):
    """GROWTH IS INCREMENTAL. Adding the Nth run must cost one row write, not N.

    This is the property that makes the diff worth its extra ``SELECT``: an
    experiment that accumulates runs over a session must not rewrite its whole row
    set on every addition. The siblings' server-side ``updated_utc`` is the
    measurement.
    """
    exp = _with_runs("parity: a later arrival", 3)
    before = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}

    added = exp.add_run(label="the fourth")
    assert exp.save_versioned() is True

    after = _full_rows(exp.id)
    assert set(after) == set(before) | {added.id}
    for run_id, stamp in before.items():
        assert after[run_id][6] == stamp, f"adding a run rewrote sibling {run_id}"
    assert after[added.id][1] == added.ordinal == 4
    assert_parity(exp)


@real_engine
def test_parity_survives_a_pod_restart_and_hydration_leaves_the_rows_untouched(
    workspace,
):
    """A POD RESTART, AND THE PROPERTY IS "UNCHANGED", NOT "REBUILT".

    ``PostgresOrdinaryStore.hydrate`` reads ``isaac_experiments`` and writes FILES.
    It does not read ``isaac_runs`` and it does not write it — nothing in this
    application reads that table at all. So the honest property after a restart is
    that the rows are exactly as the last save left them, byte for byte including
    the server-side stamps, and that the restored working copy still agrees with
    them.

    Asserting "the rows were rebuilt" would be asserting a behaviour that does not
    exist and should not; asserting "unchanged" is what actually protects the
    shadow, because a hydration that DID touch the rows would be a second, unowned
    write path.
    """
    exp = _with_runs("parity: a pod restart", 3)
    rid = exp.id
    before_all = _full_rows()
    before_mine = _full_rows(rid)
    assert len(before_mine) == 3

    # The pod restarts: the emptyDir workspace is gone.
    shutil.rmtree(ws.workspace_root())
    # THE PROBE IS THE FILESYSTEM, NOT ``load_experiment`` — measured, after this
    # test asserted the wrong thing. ``ws.load_experiment`` HYDRATES ON A MISS by
    # design (``experiment_repository``'s module docstring: "a miss on an
    # ordinary-scope load" consults the store, because on an ``emptyDir`` pod "no
    # directory" no longer implies "no record"), so it returns the record rather
    # than ``None`` and would have made this step assert the opposite of the
    # product's actual, correct behaviour.
    assert not (ws.workspace_root() / rid / "experiment.json").exists()

    restored = repo.repository().hydrate()
    assert restored >= 1, restored

    # NOT ONE ROW MOVED — not this experiment's, and not anybody else's.
    assert _full_rows(rid) == before_mine
    assert _full_rows() == before_all

    reloaded = ws.load_experiment(rid)
    assert reloaded is not None
    assert len(reloaded.runs) == 3
    assert_parity(reloaded)

    # And a save AFTER the restart still agrees, so the restored working copy is a
    # usable basis for the diff rather than merely a readable one.
    reloaded.sorted_runs()[0].label = "renamed after the restart"
    assert reloaded.save_versioned() is True
    assert_parity(reloaded)


class _RecordingCursor:
    """A real cursor that also writes down the SQL it is asked to execute.

    Everything except ``execute`` falls through to the real driver object, so
    ``rowcount``, ``fetchone`` and ``fetchall`` are the engine's answers and not a
    fake's. It observes; it changes nothing.
    """

    def __init__(self, inner, log: list[tuple]) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_log", log)

    def execute(self, sql, params=None):
        self._log.append((sql, params))
        return self._inner.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


class _RecordingConnection:
    """The same, one level up. ``autocommit`` is a SET, so ``__setattr__`` forwards.

    Without the ``__setattr__`` forward, ``write_transaction``'s
    ``conn.autocommit = False`` would land on the proxy and the REAL connection
    would stay on autocommit — a wrapper that silently disabled the transaction it
    was meant to watch.
    """

    def __init__(self, inner, log: list[tuple]) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_log", log)

    def cursor(self):
        return _RecordingCursor(self._inner.cursor(), self._log)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


def _recording_store() -> tuple[repo.PostgresOrdinaryStore, list[tuple]]:
    """A REAL durable store whose statements are recorded.

    ``PostgresOrdinaryStore`` forwards ``**connect_kwargs`` to
    ``write_transaction``, whose ``connect`` seam exists precisely so the shape can
    be observed. Here it wraps the genuine ``connect_psycopg2`` rather than
    replacing it, so this is a real connection to the real engine with a notebook
    attached.
    """
    log: list[tuple] = []

    def connect(env):
        return _RecordingConnection(dbw.connect_psycopg2(env), log)

    return repo.PostgresOrdinaryStore(os.environ, connect=connect), log


@real_engine
def test_parity_a_lost_compare_and_swap_leaves_the_winners_rows_untouched(workspace):
    """THE MOST DANGEROUS LINE IN THE SHADOW WRITE, CHECKED AGAINST A REAL ENGINE.

    ``persist`` writes run rows strictly inside ``if accepted:``. A writer that lost
    the experiment-level compare-and-swap and stamped its runs anyway would overwrite
    the WINNER's rows while correctly reporting ``412`` to its own client — the
    last-writer-wins defect ``Q_UPSERT_EXPERIMENT``'s predicate exists to close,
    reintroduced one level down and INVISIBLE, because the loser is told it lost and
    nothing ever reads the rows.

    TWO REAL CONNECTIONS, AND THEY ARE SEQUENTIAL, NOT CONCURRENT — stated plainly
    rather than implied. The predicate is decided from the ROW's state, not from wall
    clock overlap, so the wedge is built the way the deployment actually builds it:
    a winner moves the row forward (a second replica, or a fault between ``save()``'s
    two writes) while this process's workspace file stays behind. The loser then
    offers a rev the row has already passed and is refused by the server.

    THREE THINGS ARE ASSERTED, and the third is the one this test exists for:
      1. the loser really was refused (``DurableWriteConflict``, not a success);
      2. its transaction issued NO statement naming ``isaac_runs`` — and did not
         even reach the ``to_regclass`` probe, which lives inside the same branch;
      3. the winner's rows are byte-identical afterwards, stamps included.
    """
    exp = _with_runs("parity: a lost compare-and-swap", 2)
    rid = exp.id
    winner_rows = _full_rows(rid)
    assert len(winner_rows) == 2

    # THE WINNER moves the row forward without touching the workspace file or the
    # run rows — exactly what a second replica's save looks like from here.
    wedged = dict(exp.to_state(), rev=exp.rev + 7, title="a replica won")
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(
            policy.check(repo.Q_UPSERT_EXPERIMENT),
            (rid, json.dumps(wedged, sort_keys=True)),
        )
        assert cursor.rowcount == 1, "the winner's own write was refused"

    # THE LOSER: this process's copy, still at the old rev, with a genuine change.
    loser = ws.load_experiment(rid)
    assert loser is not None and loser.rev == exp.rev
    loser.sorted_runs()[0].label = "the loser's rename"
    loser.runs[0].rev += 1  # what _bump_changed_runs would have done

    store, log = _recording_store()
    with pytest.raises(repo.DurableWriteConflict) as refusal:
        store.persist(loser)
    assert refusal.value.experiment_id == rid
    assert refusal.value.stored_state["rev"] == exp.rev + 7

    issued = [sql for sql, _ in log]
    assert not [sql for sql in issued if "isaac_runs" in sql.lower()], issued
    assert repo.Q_RUN_TABLE_PRESENT not in issued, (
        "the loser reached the run-table probe, which lives inside the accepted branch"
    )
    assert repo.Q_UPSERT_EXPERIMENT in issued and repo.Q_ONE_EXPERIMENT in issued

    assert _full_rows(rid) == winner_rows, "a losing writer rewrote the winner's rows"


@real_engine
def test_parity_holds_for_a_legacy_run_document_carrying_an_empty_experiment_id(
    workspace,
):
    """THE SHAPE ``isaac_runs_document_identity``'S ``coalesce(nullif(...))`` EXISTS FOR.

    ``Run.to_state()`` emits ``experiment_id`` unconditionally and ``Run.from_state``
    reads it through ``_as_str``, which returns ``''`` for an absent key — so a
    legacy run document carries ``"experiment_id": ""``, not a missing key.
    ``_hydrate_runs`` deliberately does NOT repair it from the owning experiment,
    because repairing it on READ would change the run's authoritative signature and
    bump every record's ``rev`` on a mere listing. The value is therefore PERMANENT,
    and the row must be writable with it.

    The CHECK's original form compared ``'' = experiment_id``, which is FALSE (not
    NULL) and REFUSED this row; the fixture that "proved" it worked inserted a bare
    ``'{}'``. So this test builds the document the way the APPLICATION builds it —
    through ``Run.from_state`` — rather than by hand, which is the whole reason the
    earlier check passed while the constraint was wrong.

    A row rejected here would abort the transaction and take the EXPERIMENT upsert
    down with it, so this is not a cosmetic case: it is whether an experiment holding
    a legacy run can be saved at all.
    """
    exp = _new_experiment("parity: a legacy run document")
    legacy = ws.Run.from_state(
        {
            "id": ws.new_record_id(),
            # every string key absent -> `_as_str` yields "" for each
            "created_utc": "2026-01-01T00:00:00Z",
        }
    )
    assert legacy.experiment_id == "", "the premise of this test moved"
    exp.runs.append(legacy)
    assert exp.save_versioned() is True

    rows = _full_rows(exp.id)
    assert list(rows) == [legacy.id]
    experiment_id_column, _ordinal, state, _rev, _generation, _c, _u = rows[legacy.id]
    # THE COLUMN names the owning experiment; the DOCUMENT keeps what it always said.
    assert experiment_id_column == exp.id
    assert state["experiment_id"] == ""
    assert state["id"] == legacy.id
    assert_parity(exp)

    # It stays writable: a second save of the same legacy run is not a one-off.
    legacy.label = "renamed legacy run"
    assert exp.save_versioned() is True
    assert _full_rows(exp.id)[legacy.id][2]["experiment_id"] == ""
    assert_parity(exp)


@real_engine
def test_parity_an_UNVERSIONED_save_of_a_CHANGED_document_is_refused_and_leaves_no_stale_row(
    workspace,
):
    """WRITTEN TO PROVE ONE THING, AND IT MEASURED ANOTHER. Both are recorded.

    THE PREMISE THIS TEST WAS COMMISSIONED WITH: ``Experiment.save()`` is the
    UNVERSIONED persistence primitive, ``_bump_changed_runs`` is the only writer of
    ``Run.rev`` and runs only on the write branch of ``save_versioned`` — so a
    caller that mutates a run and calls ``save()`` changes the run's document while
    ``rev``, ``ordinal`` and ``generation`` all stay put, and a diff comparing only
    the promoted columns would leave the row STALE.

    WHAT A REAL ENGINE ACTUALLY DOES, measured here: that write never lands at all.
    ``Q_UPSERT_EXPERIMENT``'s predicate admits a differing generation, a strictly
    greater rev, or a byte-identical document — and an unversioned save of a CHANGED
    document is none of the three. The server refuses it and ``persist`` raises
    ``DurableWriteConflict``. So on a durable deployment the run rows CANNOT go stale
    by this route, because the experiment write they ride inside is rejected first.

    THAT IS A FINDING ABOUT THE PRODUCT, NOT A BUG THIS SLICE FIXES, and it is
    reported rather than patched. Two consequences worth writing down where they
    will be found:

    * ``Experiment.save()`` can persist to Postgres ONLY when the document is
      byte-identical (clause 3) or the rev has already moved. Its filesystem
      behaviour — write whatever you are holding — is not its durable behaviour.
    * ``_bump_changed_runs``' documented case "a run first persisted by a plain
      ``save()`` sits at rev 0" is therefore a FILESYSTEM-ONLY reality. Against a
      database that same sequence is refused, because adding a run changes the
      document without moving the experiment's rev.

    WHAT IS ASSERTED, then, is the property that is true and that still matters: the
    refusal is CLEAN. No run row is half-written, none is left stale, and the rows
    still agree with the document the database actually holds. The load-bearing case
    for ``state`` being inside the diff is proven separately and reachably, by
    :func:`test_the_diff_compares_the_DOCUMENT_and_repairs_a_tampered_row`.
    """
    exp = _with_runs("parity: an unversioned save of a changed document", 2)
    target = exp.sorted_runs()[0]
    before = _full_rows(exp.id)
    rev_before = target.rev

    target.label = "renamed without a version bump"
    target.draft = {"fields": {"context.environment": _envelope("SYNTHETIC-ENV")}}

    with pytest.raises(repo.DurableWriteConflict):
        exp.save()  # the UNVERSIONED primitive, against a document that changed

    assert target.rev == rev_before, "the premise moved: save() bumped a run's rev"
    # NOTHING WAS WRITTEN. Not the changed run, not its sibling, not a stamp.
    assert _full_rows(exp.id) == before

    # And the rows still describe the document the DATABASE holds.
    stored = ws.load_experiment(exp.id)
    assert stored is not None
    assert_parity(stored)
    assert stored.get_run(target.id).label != "renamed without a version bump"


@real_engine
def test_the_diff_compares_the_DOCUMENT_and_repairs_a_tampered_row(workspace):
    """WHY ``Q_EXPERIMENT_RUN_ROWS`` SELECTS ``state``, PROVEN AT A REACHABLE INPUT.

    Selecting the whole document on every save is not free, and its stated
    justification — an unversioned save changing a run without moving its ``rev`` —
    turns out to be unreachable against a real engine (see the test above: the
    compare-and-swap refuses that write). This is the reachable case, and it is the
    one a shadow table actually has to survive: a row whose DOCUMENT has drifted
    while every promoted column still matches.

    A diff comparing only ``(ordinal, rev, generation)`` would see nothing to do and
    the drift would persist forever, invisibly, because no read path in this
    application consults the table. The repair rides in on a BYTE-IDENTICAL re-save,
    which is admitted by clause 3 and needs no new SQL.

    The tampering is done by a TEST statement, out of band, which is exactly the
    provenance such drift would have: a migration, an operator, or a future second
    writer — never this application, whose only write is the one under test.
    """
    exp = _with_runs("parity: a tampered document", 2)
    target = exp.sorted_runs()[0]
    before = _full_rows(exp.id)

    tampered = _execute(Q_TEST_TAMPER_WITH_A_RUN_LABEL, (target.id,))
    assert tampered == 1
    drifted = _full_rows(exp.id)
    assert drifted[target.id][2]["label"] == "TAMPERED-OUT-OF-BAND"
    # The promoted columns are untouched, which is the whole point of the case.
    assert drifted[target.id][1:2] == before[target.id][1:2]
    assert drifted[target.id][3:6] == before[target.id][3:6]
    # The oracle's own message, for the reason the deletion control states: a bare
    # `AssertionError` would be satisfied by any assertion inside `assert_parity`.
    with pytest.raises(AssertionError) as drift_failure:
        assert_parity(exp)
    assert "isaac_runs disagrees with the experiment document" in str(drift_failure.value)

    exp.save()  # byte-identical: admitted by clause 3, and the diff repairs the row

    repaired = _full_rows(exp.id)
    assert repaired[target.id][2] == target.to_state()
    assert repaired[target.id][6] != drifted[target.id][6], "the drifted row was skipped"
    # The sibling, whose document did NOT drift, was not rewritten.
    sibling = exp.sorted_runs()[1]
    assert repaired[sibling.id] == before[sibling.id]
    assert_parity(exp)


# =============================================================================
# 5. THE CONTROLS — without these the whole stage is worthless
# =============================================================================


@real_engine
def test_the_parity_oracle_FAILS_when_a_row_is_mutated_out_of_band(workspace):
    """THE NEGATIVE CONTROL. A suite that can only go green proves nothing.

    Every assertion above is worth exactly as much as this one: the oracle must be
    able to FAIL. One statement moves every ordinal by one behind the application's
    back — a change the application can never notice, because no read path in this
    codebase consults ``isaac_runs`` — and the oracle must go red on the next call.

    It then repairs the damage through the ordinary write path and confirms the
    oracle goes green again, so a later test in the same database is not left
    reading a table this one broke.
    """
    exp = _with_runs("parity: the negative control", 3)
    assert_parity(exp)

    changed = _execute(Q_TEST_SHIFT_ORDINALS, (exp.id,))
    assert changed == 3, changed

    with pytest.raises(AssertionError) as failure:
        assert_parity(exp)
    assert "isaac_runs disagrees with the experiment document" in str(failure.value)

    # REPAIR, through the application rather than by hand: an unversioned re-save
    # rewrites the rows the diff now sees as different.
    exp.save()
    assert_parity(exp)


@real_engine
def test_the_parity_oracle_FAILS_when_a_row_is_deleted_out_of_band(workspace):
    """THE SECOND CONTROL, for the other direction.

    The ordinal control proves the oracle notices a row that is WRONG. This proves
    it notices a row that is GONE — a different failure, and the one a projection
    that only ever upserts would produce.

    THE ORACLE'S OWN MESSAGE IS ASSERTED, matching its sibling above. A bare
    ``pytest.raises(AssertionError)`` stood here, and it would have been satisfied
    by ANY assertion inside ``assert_parity`` — including a future second one that
    fired for an unrelated reason, letting this control pass while the property it
    exists to check went unmeasured.
    """
    exp = _with_runs("parity: the deletion control", 2)
    assert_parity(exp)

    removed = _execute(Q_TEST_DELETE_RUNS_OF, (exp.id,))
    assert removed == 2, removed
    assert _observed(exp.id) == []

    with pytest.raises(AssertionError) as failure:
        assert_parity(exp)
    assert "isaac_runs disagrees with the experiment document" in str(failure.value)

    exp.save()
    assert_parity(exp)


# =============================================================================
# 6. the byte-identical re-save: is it the backfill primitive it looks like?
# =============================================================================


@real_engine
def test_a_byte_identical_re_save_is_accepted_and_rewrites_the_run_rows(workspace):
    """THE CLAIM UNDER TEST, read from statement text and never executed until now.

    ``Q_UPSERT_EXPERIMENT``'s third clause — ``isaac_experiments.state =
    EXCLUDED.state`` — admits a re-offer of a BYTE-IDENTICAL document at an equal
    rev. If that is true against a real engine, then ``persist`` reaches
    ``if accepted:`` and runs ``_write_run_rows``, which means an unchanged re-save
    is an IN-PATH REPAIR for the run rows: it needs no new SQL, no new route and no
    new statement, and it can rebuild a row set that has gone missing.

    THE PROOF IS CONSTRUCTED SO IT CANNOT PASS VACUOUSLY. The rows are DELETED out
    of band first, so "the rows are correct afterwards" can only be true if the
    re-save actually wrote them — a run of this test against a build where clause 3
    refused would leave an empty table and fail.

    Three layers, deliberately, because they can fail independently:
      1. the SQL clause itself: the same document offered twice, ``rowcount == 1``;
      2. the STORE: ``persist`` of an unchanged experiment issues ``Q_UPSERT_RUN``
         per run and restores the row set;
      3. the IN-PATH primitive: a plain ``exp.save()`` — what an application caller
         actually has — does the same thing.
    """
    exp = _with_runs("parity: the byte-identical re-save", 3)
    expected_rows = _expected(exp)
    payload = json.dumps(exp.to_state(), sort_keys=True)

    # ── 1. THE CLAUSE. The same bytes, at the same rev, offered again. ──────────
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(repo.Q_UPSERT_EXPERIMENT), (exp.id, payload))
        assert cursor.rowcount == 1, (
            "a byte-identical re-offer was REFUSED: clause 3 of Q_UPSERT_EXPERIMENT "
            "does not behave as its comment claims, and the run-row backfill "
            "primitive this test documents does not exist"
        )

    # ── 2. THE STORE. Rows deleted behind its back; an unchanged persist repairs. ─
    assert _execute(Q_TEST_DELETE_RUNS_OF, (exp.id,)) == 3
    assert _observed(exp.id) == []

    store, log = _recording_store()
    store.persist(exp)  # no DurableWriteConflict: the document is unchanged

    issued = [sql for sql, _ in log]
    assert issued.count(repo.Q_UPSERT_RUN) == 3, issued
    assert repo.Q_EXPERIMENT_RUN_ROWS in issued
    assert _observed(exp.id) == expected_rows
    assert_parity(exp)

    # ── 3. THE IN-PATH PRIMITIVE. What a caller actually has. ───────────────────
    assert _execute(Q_TEST_DELETE_RUNS_OF, (exp.id,)) == 3
    assert _observed(exp.id) == []
    reloaded = ws.load_experiment(exp.id)
    assert reloaded is not None
    before_rev = reloaded.rev
    reloaded.save()
    assert reloaded.rev == before_rev, "a plain save() moved the experiment rev"
    assert_parity(reloaded)
    assert _observed(exp.id) == expected_rows

    # AND IT IS A REPAIR, NOT A REWRITE OF HISTORY: the document is untouched.
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(repo.Q_ONE_EXPERIMENT), (exp.id,))
        stored = _as_document(cursor.fetchone()[0])
    assert stored == json.loads(payload)


@real_engine
def test_a_byte_identical_re_save_of_a_run_less_experiment_still_holds(workspace):
    """The same clause, at the boundary the ``%s::text[]`` cast exists for.

    A re-save of an experiment with NO runs reaches ``_write_run_rows`` with an
    empty desired set. Nothing should be written and nothing should be deleted —
    but the SELECT still runs, and this is the case where a mistake would produce a
    type error rather than a wrong answer.
    """
    exp = _new_experiment("parity: a run-less byte-identical re-save")
    store, log = _recording_store()
    store.persist(exp)
    issued = [sql for sql, _ in log]
    assert repo.Q_EXPERIMENT_RUN_ROWS in issued
    assert repo.Q_UPSERT_RUN not in issued
    assert repo.Q_DELETE_ABSENT_RUNS not in issued
    assert _observed(exp.id) == []


@real_engine
def test_the_delete_of_the_last_run_binds_the_empty_text_array(workspace):
    """``Q_DELETE_ABSENT_RUNS``' ``%s::text[]`` CAST, at the one input that needs it.

    Deleting the LAST run passes an EMPTY id list. An empty array literal carries no
    element type for the server to infer, whichever of psycopg2's renderings it
    produces, so without the explicit cast this is a type error on the one save that
    matters most. The machine the cast was written on had no PostgreSQL and no
    psycopg2; this is where the precaution stops being unmeasured.
    """
    exp = _with_runs("parity: the empty array", 1)
    assert len(_observed(exp.id)) == 1

    exp.runs = []
    # THE REV IS BUMPED BY HAND, and that is not a shortcut around anything. The
    # recording store is needed to observe the PARAMETER, so this cannot go through
    # ``save_versioned`` (which builds its own store) — and a bare ``persist`` of a
    # changed document at an unchanged rev is REFUSED by the compare-and-swap, as
    # the unversioned-save test above measures. ``max(rev, disk_rev) + 1`` is
    # exactly what ``save_versioned`` would have offered.
    exp.rev += 1
    store, log = _recording_store()
    store.persist(exp)

    issued = [sql for sql, params in log]
    assert repo.Q_DELETE_ABSENT_RUNS in issued
    empty_binding = [
        params for sql, params in log if sql == repo.Q_DELETE_ABSENT_RUNS
    ]
    assert empty_binding == [(exp.id, [])], empty_binding
    assert _observed(exp.id) == []
    assert_parity(exp)


# =============================================================================
# 7. what the ORACLE itself is, asserted where a reader will find it
# =============================================================================


def test_this_suite_reads_isaac_runs_only_as_a_test_and_never_on_the_apps_behalf():
    """A NAME-AND-VALUE DRIFT GUARD OVER TWO MODULES. It opens nothing.

    ``CLAUDE.md`` §15: the run write is a SHADOW, the document is authoritative, and
    making ``isaac_runs`` a READ SOURCE is a separate, unauthorized decision. This
    file reads the table constantly, and that could be mistaken for exactly the
    change that is not authorized.

    **WHAT THIS TEST CHECKS, precisely.** It builds the set of ``Q_``-prefixed
    module-level values of ``db_write`` and ``experiment_repository`` and asserts
    that none of FOUR of the five TEST statements below is among them, and that each
    still passes the application's own ``WriteStatementPolicy``. So a future slice
    that MOVES one of them into either of those two modules trips here.

    **IT WAS FIVE, AND ONE OF THEM COLLIDED — RECORDED RATHER THAN QUIETLY
    EXEMPTED.** ``Q_TEST_DELETE_RUNS_OF`` is
    ``DELETE FROM isaac_runs WHERE experiment_id = %s``, and the DISCARD slice gave
    ``experiment_repository`` a statement with exactly those bytes
    (``Q_DELETE_RUNS_FOR_EXPERIMENT``) — for its own authorized reason, removing an
    unsubmitted experiment's run rows before the experiment row itself. Nothing was
    MOVED: two statements arrived at one string independently.

    So for that one the assertion is INVERTED rather than dropped, which is the
    stronger of the two available readings: it is pinned EQUAL to the application
    constant it collides with, by name. A change to either side trips here and names
    the other, where a bare exemption would have gone quiet forever. What is lost is
    real and is stated: this file can no longer tell "the test's own delete" from
    "the application's delete" by text, so the enumeration that keeps
    ``isaac_runs`` a write-path-only table is
    ``test_0002_is_now_written_by_the_write_path_and_by_nothing_else``'s, not this
    one's.

    **WHAT IT DOES NOT CHECK, and this is stated because the claim was once made
    more broadly than the code supports.** It is NOT a reachability proof. It would
    not notice a run-row read added to ``routes.py``, ``db_provider.py`` or any
    other module; it would not notice a constant that is not prefixed ``Q_``; and it
    would not notice inline SQL built at a call site. The property that no read path
    names ``isaac_runs`` does hold today, but the evidence for it is
    ``test_0002_is_now_written_by_the_write_path_and_by_nothing_else``'s enumeration
    plus review — not this assertion.

    The one thing this test contributes to that wider property is negative: it
    confirms the five statements here are not part of the application's constant
    set, so the enumeration elsewhere is not silently made false by this file.
    """
    application_statements = set()
    for module in (dbw, repo):
        for name in dir(module):
            if name.startswith("Q_"):
                application_statements.add(getattr(module, name))
    for sql in (
        Q_TEST_ALL_RUN_ROWS,
        Q_TEST_RUN_ROWS_FOR,
        Q_TEST_SHIFT_ORDINALS,
        Q_TEST_TAMPER_WITH_A_RUN_LABEL,
    ):
        assert sql not in application_statements, sql
        # ...and each is still bound by the same policy every application
        # statement is: owned tables only, no forbidden verb.
        assert dbw.WriteStatementPolicy().check(sql) == sql

    # THE COLLISION, PINNED BY NAME rather than exempted. See the docstring: the
    # discard slice's `Q_DELETE_RUNS_FOR_EXPERIMENT` is byte-identical to this
    # file's out-of-band control, arrived at independently. Asserting the equality
    # means a change to EITHER side fails here and names the other.
    assert Q_TEST_DELETE_RUNS_OF == repo.Q_DELETE_RUNS_FOR_EXPERIMENT
    assert Q_TEST_DELETE_RUNS_OF in application_statements
    assert (
        dbw.WriteStatementPolicy().check(Q_TEST_DELETE_RUNS_OF)
        == Q_TEST_DELETE_RUNS_OF
    )

    # The application's read of the table remains the ONE inside the write path.
    assert repo.Q_EXPERIMENT_RUN_ROWS in application_statements


def test_the_oracle_projects_the_same_tuple_the_application_writes():
    """A PURE, ENGINE-FREE CHECK THAT THE ORACLE IS COMPARING THE RIGHT THING.

    ``_expected`` is hand-written here, so it could drift from
    ``experiment_repository._run_row_params`` — the one place a ``Run`` becomes a
    row — and an oracle comparing the wrong projection would agree with the table
    for the wrong reason. This pins the two together WITHOUT a database:
    ``_run_row_params`` is pure and deliberately callable without one.

    ``state`` is compared after a ``json.loads`` because ``_run_row_params``
    serialises with ``sort_keys=True`` for determinism, while the oracle compares
    documents.
    """
    exp = ws.Experiment(
        id="01ABCDEFGHJKMNPQRSTVWXYZ00",
        title="oracle projection",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )
    run = ws.Run(
        id="01AAAAAAAAAAAAAAAAAAAAAAAA",
        experiment_id=exp.id,
        label="a run",
        ordinal=3,
        created_utc="2026-01-01T00:00:00Z",
        draft={"fields": {}},
        rev=7,
        generation="gen-fixture",
    )
    exp.runs.append(run)

    run_id, experiment_id, ordinal, state_json, rev, generation = repo._run_row_params(
        exp.id, run
    )
    assert experiment_id == exp.id
    assert _expected(exp) == [
        (run_id, ordinal, json.loads(state_json), rev, generation)
    ]
    # The document the WRITE PATH serialises is the document the ORACLE projects.
    assert json.loads(state_json) == run.to_state()
    # ...and it is serialised DETERMINISTICALLY, with sorted keys.
    #
    # Two assertions used to stand here and NEITHER COULD FAIL: `json.loads(...) is
    # not run.to_state()` is true of any two separately-built objects, and
    # `copy.deepcopy(x) == x` is true of any value-equal structure. They were
    # labelled a guard against an aliased document and guarded nothing. This one
    # can go red, on a real and documented property: `_run_row_params`' own
    # docstring says `sort_keys=True` is "presentation only — the column is jsonb,
    # which compares by VALUE — and it keeps the parameter deterministic, which is
    # what makes a test able to assert on it". Several tests DO assert on the
    # parameter, so a writer that dropped the sort would not be a correctness
    # regression against the engine but would make those assertions
    # order-dependent. It is pinned where the claim is made.
    assert state_json == json.dumps(run.to_state(), sort_keys=True)


# =============================================================================
# 8. THE FAKE-DRIVER HALF — only the shapes the existing fake suite does NOT cover
# =============================================================================
#
# `test_experiment_repository.py` §7b already proves, against the in-process fake:
# the row set at four widths, the legacy empty `experiment_id`, the deduped row
# set, the null `record_id`, add/rename/override/remove each writing only what
# moved, the empty `::text[]` parameter, the no-op second save, a drifted promoted
# column being repaired, and — the important one — that a REFUSED upsert issues no
# run statement at all. NONE of that is repeated here. Duplicating it would create
# a second place for the same property to be maintained and a second place for it
# to drift.
#
# TWO SHAPES ARE GENUINELY UNCOVERED THERE and are cheap to cover here. Both are
# FAKE-DRIVER tests: they prove the STATEMENTS and the projected row set under a
# faithful-but-simplified store, and they prove nothing about PostgreSQL. The
# real-engine counterparts above are the authority.
#
# The fake is IMPORTED rather than re-implemented. A second copy of a 190-line
# connection double is exactly how two suites end up disagreeing about what the
# driver does.

from test_experiment_repository import FakeConnection, _connector, _env  # noqa: E402


def _fake_persist(exp, conn=None):
    conn = FakeConnection() if conn is None else conn
    repo.PostgresOrdinaryStore(_env(), connect=_connector(conn)).persist(exp)
    return conn


def _bare_experiment(rid: str = "01ABCDEFGHJKMNPQRSTVWXYZ00") -> "ws.Experiment":
    return ws.Experiment(
        id=rid,
        title="fake-driver fixture",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )


def test_FAKE_an_inherited_address_never_reaches_the_projected_run_row():
    """FAKE-DRIVER. The projection half of the inheritance property, with no engine.

    The real-engine test of the same name asserts this against the stored ``jsonb``.
    This one asserts it one layer earlier, in the PARAMETERS the write path sends —
    so a projection that started copying resolved experiment content down into the
    row would fail here even on a machine with no database, which is every
    developer machine in this project.
    """
    exp = _bare_experiment()
    exp.draft = {
        "fields": {"sample.material.name": _envelope("SYNTHETIC-FIXTURE-MATERIAL")},
        "tags": ["synthetic-campaign"],
    }
    run = exp.add_run(label="inherits everything")

    conn = _fake_persist(exp)
    _experiment_id, _ordinal, state, _rev, _generation = conn.runs[run.id]
    assert state["draft"] == {} and state["overrides"] == {}
    blob = json.dumps(state, sort_keys=True)
    assert "SYNTHETIC-FIXTURE-MATERIAL" not in blob
    assert "synthetic-campaign" not in blob
    # ...while the run genuinely inherits, computed on read.
    assert exp.resolve_run(run)[ws.field_address("sample.material.name")].value == (
        "SYNTHETIC-FIXTURE-MATERIAL"
    )


@real_engine
def test_parity_removing_a_run_over_HTTP_removes_its_row_and_moves_no_other(workspace):
    """REAL ENGINE. The removal operation's half of the shadow contract.

    Every other scenario in this file drives the document directly. This one drives
    the HTTP route that a scientist's Remove button calls, because the row set has to
    follow THE DOCUMENT THE PRODUCT WRITES, not a document a test composed.

    Two properties, and the second is the one a partial implementation would miss:

    * the removed run's row is gone;
    * every SURVIVOR's row is byte-for-byte what it was — ordinal included. The
      removal deliberately does not renumber, so a row diff that decided to rewrite
      the survivors "while it was in there" would fail here rather than silently
      churning every row on every removal.

    ``assert_parity`` then re-states the whole invariant against the document, so a
    row that was deleted for the wrong reason fails too.
    """
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    exp = _with_runs("parity: removal over HTTP", 3)
    ids = [run.id for run in exp.sorted_runs()]
    assert_parity(exp)
    before = {run_id: row for run_id, row in _full_rows(exp.id).items()}
    assert set(before) == set(ids)

    client = TestClient(create_app())
    tag = client.get(f"/api/experiments/{exp.id}").headers["ETag"]
    response = client.post(
        f"/api/experiments/{exp.id}/runs/{ids[1]}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": tag},
    )
    assert response.status_code == 200, response.text

    after = _full_rows(exp.id)
    assert set(after) == {ids[0], ids[2]}
    for run_id in (ids[0], ids[2]):
        assert after[run_id] == before[run_id], f"{run_id}'s row moved"
    assert_parity(ws.load_experiment(exp.id))


def test_FAKE_hydration_issues_no_statement_naming_isaac_runs(workspace):
    """FAKE-DRIVER. The read half of the pod-restart property, stated as a shape.

    ``hydrate`` reads ``isaac_experiments`` and writes FILES. The real-engine test
    asserts the OUTCOME — not one run row moved. This asserts the MECHANISM: the
    hydration transaction issues exactly one application statement and it is
    ``Q_ALL_EXPERIMENTS``. A future hydration that started "helpfully" rebuilding
    run rows would be a second, unowned write path into the shadow table, and it
    would fail here.
    """
    exp = _bare_experiment()
    exp.add_run(label="a run the row set already holds")
    state = exp.to_state()

    conn = FakeConnection(rows=[(exp.id, json.dumps(state))])
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    before = dict(conn.runs)
    store.hydrate()

    assert [sql for sql, _ in conn.statements if "isaac_runs" in sql.lower()] == []
    assert repo.Q_RUN_TABLE_PRESENT not in [sql for sql, _ in conn.statements]
    assert conn.runs == before, "hydration wrote to the shadow table"
