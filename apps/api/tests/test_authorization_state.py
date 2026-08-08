"""The authorization record, and the guard that stops it drifting from the code.

Before this file existed, "may the verification engine read the datastore?" was
answered in three places -- a Markdown file, a module docstring, and a test
asserting a literal tuple -- none of which was derived from the others. This
suite exists so there is exactly one answer and one place to change it.

Two of these tests are unusual and deliberate:

* :func:`test_flipping_the_approval_flag_makes_the_drift_guard_fail` is a
  NEGATIVE CONTROL. A guard that passes is worthless unless something can make
  it fail, and this proves the flag is what does.
* :func:`test_the_format_enforcement_question_is_still_unanswered` ties an
  unrelated-looking truth-path property to this file, because Q19 and Q20 were
  explicitly not bundled and an approval to one is routinely misread as an
  approval to both.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from isaac_api import authorization, verification

ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_the_approval_is_recorded_with_its_date_and_its_relay():
    """The source string must keep saying how the approval arrived.

    "Relayed by the project owner" is not a hedge -- it is the difference
    between testimony and a captured artifact, the same distinction `CLAUDE.md`
    §15 draws about the one observed reconnaissance scan. A future session that
    reads `APPROVAL_SOURCE` must not be able to mistake this for a transcript.
    """
    assert authorization.APPROVAL_DATE == "2026-08-05"
    assert authorization.APPROVAL_SOURCE == (
        "relayed by the project owner; no direct agent-to-owner communication "
        "occurred"
    )


def test_the_authorization_record_is_plain_serializable_data():
    """It must be safe to log or serve: no object, no path, no environment."""
    import json

    record = authorization.authorization_record()
    round_tripped = json.loads(json.dumps(record))
    assert round_tripped == record
    assert record["approval_date"] == authorization.APPROVAL_DATE
    assert record["verification_modes"] == list(authorization.verification_modes())


def test_the_constraints_and_the_exclusions_are_both_present():
    """`NOT_AUTHORIZED` is load-bearing, not decoration.

    An approval to COMPUTE aggregates over a corpus is routinely misread as an
    approval to SHOW it -- this project shipped that mistake once already (the
    five aggregates withdrawn in v0.0.32). The exclusion list is what a future
    slice is supposed to read before widening anything.
    """
    assert len(authorization.DATASTORE_CONSTRAINTS) >= 10
    assert all(isinstance(line, str) and line for line in authorization.DATASTORE_CONSTRAINTS)
    assert len(authorization.NOT_AUTHORIZED) >= 5
    joined = " ".join(authorization.NOT_AUTHORIZED).lower()
    assert "per-record display" in joined
    assert "write" in joined


def test_no_constraint_line_interpolates_anything():
    """These strings are quoted into documentation and could be logged."""
    for line in authorization.DATASTORE_CONSTRAINTS + authorization.NOT_AUTHORIZED:
        assert "{" not in line and "%s" not in line


# ---------------------------------------------------------------------------
# The drift guard
# ---------------------------------------------------------------------------


def test_the_engine_modes_are_derived_from_the_authorization_record():
    """THE guard. `verification.VERIFICATION_MODES` must not be a literal.

    If someone re-declares the tuple in `verification.py`, this fails -- which
    is the only mechanical thing standing between "the approval was withdrawn"
    and "the mode is still there".
    """
    assert verification.VERIFICATION_MODES == authorization.verification_modes()


def test_the_datastore_mode_exists_only_while_the_flag_is_set():
    assert authorization.Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED is True
    assert authorization.AUTHORIZED_PRIVATE_SAMPLE_MODE in verification.VERIFICATION_MODES
    assert verification.AUTHORIZED_PRIVATE_SAMPLE == "authorized_private_sample"
    assert verification.PUBLIC_REFERENCE == "public_reference"


def test_clearing_the_flag_removes_the_mode_rather_than_disabling_it(monkeypatch):
    """Withdrawal must be ABSENCE.

    The authorization audit is explicit: "a disabled runner is a runner someone
    enables"
    (`docs/superpowers/plans/2026-08-02-corpus-validation-authorization.md:221-223`).
    So there must be no `enabled=False` state to flip back.
    """
    monkeypatch.setattr(
        authorization, "Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED", False
    )
    modes = authorization.verification_modes()
    assert modes == (authorization.PUBLIC_REFERENCE_MODE,)
    assert authorization.AUTHORIZED_PRIVATE_SAMPLE_MODE not in modes


def test_flipping_the_approval_flag_makes_the_drift_guard_fail(monkeypatch):
    """NEGATIVE CONTROL for the guard above.

    Without this, `test_the_engine_modes_are_derived_from_the_authorization_record`
    would also pass against a `verification.py` that hard-coded the same two
    strings -- it would look like a derivation and be a coincidence. Here the
    flag is cleared and the guard's own comparison is asserted to FAIL, which is
    only possible if the tuple genuinely tracks the flag.
    """
    monkeypatch.setattr(
        authorization, "Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED", False
    )
    assert verification.VERIFICATION_MODES != authorization.verification_modes()


def test_a_provider_refuses_to_run_when_the_flag_is_cleared(monkeypatch):
    """Belt-and-braces below the mode list.

    Removing the mode stops the ENGINE offering it. It does not stop somebody
    constructing a provider directly, so the provider re-checks the flag before
    it does anything at all -- otherwise the flag would be advisory.
    """
    from isaac_api import db_provider

    monkeypatch.setattr(
        db_provider, "Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED", False
    )

    def exploding_connect(env):  # pragma: no cover - must never be called
        raise AssertionError("the provider connected despite the flag being clear")

    provider = db_provider.DatastoreRecordProvider(
        {"PGDATABASE": "metadata_assistant", "PGHOST": "h", "PGUSER": "u", "PGPASSWORD": "p"},
        connect=exploding_connect,
    )
    assert list(provider.records()) == []
    assert provider.state == db_provider.STATE_REFUSED
    assert provider.refusal_gate == "authorization"
    assert provider.connections_opened == 0


# ---------------------------------------------------------------------------
# Q20 was NOT bundled with Q19
# ---------------------------------------------------------------------------


def test_the_format_enforcement_question_is_still_unanswered():
    """Q19's approval says nothing about Q20.

    The packet states the two are independent decisions
    (`docs/dean-authorization-packet.md:6`). The failure mode this guards is a
    future session reading "authorization arrived on 2026-08-05" and arming
    `format` enforcement, which would change what
    `records_passing_full_schema` MEANS for the owner's own data.
    """
    assert authorization.Q20_FORMAT_ENFORCEMENT_APPROVED is False


def test_the_official_validator_is_still_format_blind():
    """The mechanical consequence of the flag above, measured on the live code.

    `tests/test_truthpath_characterization.py` is the fuller record and is not
    modified by the slice that added this file.
    """
    from isaac_records.official import load_official_validator

    assert load_official_validator(ROOT).format_checker is None


# ---------------------------------------------------------------------------
# The fourth copy: the frontend contract
# ---------------------------------------------------------------------------

CONTRACT_TS = ROOT / "apps" / "web" / "src" / "lib" / "verificationContract.ts"


def _modes_declared_in_typescript() -> list[str]:
    """Extract `VERIFICATION_MODES` from the TS contract by reading the file.

    READ-ONLY on purpose. This test exists to detect drift, so it must not be
    able to cause any: it never writes, and it is deliberately tolerant of
    formatting (single or double quotes, one line or many) while being strict
    about the VALUES.
    """
    source = CONTRACT_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export\s+const\s+VERIFICATION_MODES\s*=\s*Object\.freeze\(\s*\[(.*?)\]",
        source,
        re.DOTALL,
    )
    assert match, (
        "could not find `VERIFICATION_MODES` in verificationContract.ts; if its "
        "shape changed, update this parser rather than deleting the check"
    )
    return re.findall(r"""['"]([^'"]+)['"]""", match.group(1))


def test_the_typescript_contract_matches_the_authorization_record():
    """The mode tuple had FOUR underived copies: `authorization.py`,
    `verification.py`, this repository's Python tests, and a hand-maintained
    literal in `verificationContract.ts` with no cross-language check at all.

    `authorization.py`'s own docstring says three underived copies of one fact
    "is exactly the shape that drifts". The consequence was demonstrated: with
    the approval flag cleared the backend goes completely clean -- refused
    everywhere, `connections_opened == 0` -- while the TypeScript contract on
    disk still advertised both modes to every reader of the UI.

    This test reads the file rather than importing it, so it detects drift
    without owning the file.
    """
    assert _modes_declared_in_typescript() == list(authorization.verification_modes())


def test_the_typescript_contract_and_the_engine_agree():
    """Belt-and-braces at the other end of the chain: TS <-> engine, not just
    TS <-> authorization record."""
    assert _modes_declared_in_typescript() == list(verification.VERIFICATION_MODES)


def test_the_parity_check_would_notice_a_withdrawal(monkeypatch):
    """NEGATIVE CONTROL. With the flag cleared the two sides must DISAGREE --
    that disagreement is the alarm, and it is what a withdrawal has to trigger."""
    monkeypatch.setattr(
        authorization, "Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED", False
    )
    assert _modes_declared_in_typescript() != list(authorization.verification_modes())


def _report_format_version_declared_in_typescript() -> int:
    """Extract `VERIFICATION_REPORT_FORMAT_VERSION` from the TS contract.

    READ-ONLY and formatting-tolerant, in the same style as
    `_modes_declared_in_typescript` above and for the same reason: this exists to
    detect drift, so it must not be able to cause any.
    """
    source = CONTRACT_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export\s+const\s+VERIFICATION_REPORT_FORMAT_VERSION\s*=\s*(\d+)",
        source,
    )
    assert match, (
        "could not find `VERIFICATION_REPORT_FORMAT_VERSION` in "
        "verificationContract.ts; if its shape changed, update this parser "
        "rather than deleting the check"
    )
    return int(match.group(1))


def test_the_report_format_version_agrees_across_the_two_languages():
    """The SECOND pair of underived copies of one fact, now checked.

    `verification.REPORT_FORMAT_VERSION` and the TypeScript
    `VERIFICATION_REPORT_FORMAT_VERSION` are two hand-maintained literals of the
    same number, and `readVerificationBody` REFUSES any report announcing a
    different one -- it renders `unreadable`. So a one-sided bump does not
    degrade gracefully: it ships a UI that rejects every single report, while
    every test in both suites still passes, because neither suite crossed the
    language boundary to compare them.

    That is the identical shape `VERIFICATION_MODES` drifted in, which is why
    that guard exists a few lines above. This one is its counterpart. Bumping
    the format is fine; bumping it on one side only is what this catches.
    """
    assert (
        _report_format_version_declared_in_typescript()
        == verification.REPORT_FORMAT_VERSION
    ), (
        "the frontend and backend disagree on the report format version; the UI "
        "would refuse every report as unreadable. Bump BOTH, in one change."
    )


def test_the_format_version_check_would_notice_a_one_sided_bump(monkeypatch):
    """NEGATIVE CONTROL, matching `test_the_parity_check_would_notice_a_withdrawal`.

    Moves the backend copy and nothing else -- exactly what a one-sided bump is
    -- and requires the two to disagree. Without this, a parser that silently
    returned the backend's own value would pass the test above forever.
    """
    monkeypatch.setattr(verification, "REPORT_FORMAT_VERSION", 999)
    assert (
        _report_format_version_declared_in_typescript()
        != verification.REPORT_FORMAT_VERSION
    )


# ---------------------------------------------------------------------------
# The route's honesty claims are true only because it takes no parameters
# ---------------------------------------------------------------------------


def test_the_verification_route_takes_a_mode_AND_its_description_says_so():
    """The same guard as before, pointed at the state that is now true.

    THIS TEST USED TO ASSERT THE OPPOSITE, and the change is deliberate rather
    than a capitulation. Its previous form read:

        assert list(inspect.signature(get_runtime_verification).parameters) == []

    and its docstring explained why: the published description claimed the
    operation ran over "the ten public upstream ISAAC example records" and
    connected to no database, and *both claims were true only because the route
    took no parameter*. A `?mode=` added on its own would have silently
    falsified a description nobody edited. The guard existed to couple the two,
    and it was never a prohibition on wiring -- it even named the reason the
    description was left alone (regenerating the snapshot was out of that
    slice's scope).

    Q19 authorized the datastore mode on 2026-08-05, the wire now exists, and
    the description WAS edited in the same commit. So the coupling is preserved
    by inverting the assertion: the route must take the mode parameter, and the
    description must disclose both corpora. Deleting the test would have removed
    the coupling; that is the one thing that must not happen.
    """
    import inspect

    from isaac_api import routes

    params = list(inspect.signature(routes.get_runtime_verification).parameters)
    assert params == ["mode"], (
        "the route must expose exactly the mode parameter -- an extra one is a "
        "caller-influenced value on a path that reaches a datastore"
    )

    # The other half: the description must not still describe a single public
    # corpus, and must not make a bare no-database claim about the deployment.
    description = _verification_route_description(routes)
    assert "`mode`" in description
    assert verification.AUTHORIZED_PRIVATE_SAMPLE in description
    assert "ten public upstream ISAAC example records: official schema" not in description, (
        "the lead sentence still describes only the public corpus"
    )


def _verification_route_description(routes_module) -> str:
    """The description FastAPI will actually publish for the route."""
    for route in routes_module.router.routes:
        if getattr(route, "path", None) == "/api/runtime/verification":
            return route.description or ""
    raise AssertionError("the verification route is not registered")


def _sentences(text: str) -> list[str]:
    """Sentence-ish units, so a claim is judged with its own qualification.

    A whole-description substring search cannot tell "does not connect to any
    database" (false of the operation now) from "a run in `public_reference`
    mode does not connect to any database" (true). Splitting on terminal
    punctuation is crude and deliberately so: the units it produces are the ones
    a reader reads.
    """
    import re

    flat = " ".join(text.split())
    return [s for s in re.split(r"(?<=[.!?])\s+", flat) if s]


def test_the_verification_description_makes_no_UNQUALIFIED_no_database_claim():
    """The sentence this slice deleted must not be able to come back unscoped.

    The inverted guard above asserts the old LEAD sentence is gone. It never
    asserted anything about the other false sentence -- "this operation does not
    connect to any database" -- and `test_backend_copy_truthfulness.py`'s
    `\\bno\\s+database\\b` pattern does not match that phrasing either, so
    re-adding it would have passed both guards. This closes that hole.

    What is banned is the UNQUALIFIED form. A mode-scoped statement stays legal,
    because it is still true: `public_reference` reads vendored files and opens
    nothing. So a sentence may make the claim only if it names that mode in the
    same sentence.
    """
    from isaac_api import routes

    description = _verification_route_description(routes)
    for sentence in _sentences(description):
        lowered = sentence.lower()
        if "connect to any database" not in lowered and (
            "does not open a database connection" not in lowered
        ):
            continue
        assert verification.PUBLIC_REFERENCE in sentence, (
            "a no-database claim must be scoped to the public mode in its own "
            f"sentence; this one is unqualified and now false: {sentence!r}"
        )


def test_the_verification_description_pairs_each_failure_word_with_its_own_cause():
    """`refused` and `unavailable` have different causes, MEASURED to differ.

    Measured in `apps/api/tests/test_verification_route_wiring.py`, which drives
    the real provider factory under two environments:

    * `PGDATABASE` absent or wrong -> the pin rejects it -> `refused`
    * `PGDATABASE` pinned, no host/user/password (or no driver) -> `unavailable`

    The published description used to say the private mode "is refused rather
    than attempted when its environment gates are unmet, and reports
    `unavailable` when the driver is absent". Read against the measurement that
    is wrong twice: a missing `PGHOST` is an unmet gate that does NOT refuse, and
    the driver is not the only cause of `unavailable`. An operator debugging a
    pod that reported `unavailable` would look for a missing driver in the image
    rather than for an unset host.

    So the contract must NAME which condition produces which word, and must not
    re-generalize refusal back over the whole environment.
    """
    from isaac_api import routes

    description = _verification_route_description(routes)
    sentences = _sentences(description)

    assert any("refused" in s and "PGDATABASE" in s for s in sentences), (
        "the description must name the PGDATABASE pin as the cause of `refused`"
    )
    assert any("unavailable" in s and "PGHOST" in s for s in sentences), (
        "the description must name a missing host as a cause of `unavailable`"
    )

    for sentence in sentences:
        lowered = sentence.lower()
        if "refus" not in lowered:
            continue
        assert "gates are unmet" not in lowered and "gate is unmet" not in lowered, (
            "refusal is re-generalized over the whole environment, which is "
            f"false: only the PGDATABASE pin refuses. {sentence!r}"
        )
        if any(var in sentence for var in ("PGHOST", "PGUSER", "PGPASSWORD")):
            assert "unavailable" in lowered, (
                "a sentence associating a missing host, user or password with "
                f"refusal must say the word those conditions produce: {sentence!r}"
            )


def test_the_deployed_state_object_HAS_a_provider_factory_and_still_defaults_to_public():
    """The other half of the same claim, likewise inverted deliberately.

    Previously: `_provider_factory is None`, because the route could not reach a
    datastore at all. Q19 authorized it, so the factory is supplied.

    What must NOT change, and is asserted here rather than assumed: the DEFAULT
    is still the public corpus. A caller who names no mode must never be handed
    the datastore one. That is the part of the old guarantee that survives
    verbatim, and it is the part a careless refactor would take.
    """
    from isaac_api import routes

    assert routes._VERIFICATION_STATE._provider_factory is not None
    assert routes._VERIFICATION_STATE.default_mode == verification.PUBLIC_REFERENCE


@pytest.mark.parametrize("mode", ["public_reference", "authorized_private_sample"])
def test_every_declared_mode_has_its_own_fixed_limitation_lines(mode):
    """A mode that published no mode-specific limitation would be describing the
    other one's corpus."""
    lines = verification.limitations_for(mode)
    assert len(lines) > len(verification.LIMITATIONS)
    for line in lines:
        assert "{" not in line and "%s" not in line
