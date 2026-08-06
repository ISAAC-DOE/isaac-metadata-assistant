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


# ---------------------------------------------------------------------------
# The route's honesty claims are true only because it takes no parameters
# ---------------------------------------------------------------------------


def test_the_verification_route_accepts_no_parameters():
    """`GET /api/runtime/verification` documents itself as running over "the ten
    public upstream ISAAC example records" and as not connecting to any database.

    Both are true only because the operation takes no parameter, while
    `VerificationState.get()` accepts a mode. A future `?mode=` query parameter
    would silently falsify the published description without touching it. This
    test is that guard: adding a parameter fails here, next to the reason.

    The description itself is deliberately NOT edited to say so --
    `apps/api/isaac_api/routes.py` is in the committed served-content manifest,
    so editing it drifts `memory-snapshot.json`, and regenerating that is out of
    scope for this slice.
    """
    import inspect

    from isaac_api import routes

    assert list(inspect.signature(routes.get_runtime_verification).parameters) == []


def test_the_deployed_state_object_has_no_provider_factory():
    """The other half of the same claim. The route cannot reach a datastore
    because the process-wide `VerificationState` was constructed without a
    provider factory, so the datastore mode has nothing to open."""
    from isaac_api import routes

    assert routes._VERIFICATION_STATE._provider_factory is None
    assert routes._VERIFICATION_STATE.default_mode == verification.PUBLIC_REFERENCE


@pytest.mark.parametrize("mode", ["public_reference", "authorized_private_sample"])
def test_every_declared_mode_has_its_own_fixed_limitation_lines(mode):
    """A mode that published no mode-specific limitation would be describing the
    other one's corpus."""
    lines = verification.limitations_for(mode)
    assert len(lines) > len(verification.LIMITATIONS)
    for line in lines:
        assert "{" not in line and "%s" not in line
