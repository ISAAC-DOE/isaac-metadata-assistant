"""Nominal values — `DEC-43` SUPERSEDED on 2026-09-22, and the fences that replace it.

**WHAT THIS FILE USED TO PROVE, AND WHY IT WAS REWRITTEN RATHER THAN DELETED.** It proved
the four conditions of `DEC-43` (2026-09-17): 298 K offered for the BL15-2 "Angel-style"
profile only, never labelled measured, generalising to nothing. On 2026-09-22 the domain
owner (Angel), relayed by the project owner, withdrew the automatic value: missing
temperature stays missing, "room temperature" may mean 293 K as easily as 298 K, and
published work / NIST should be checked. The check found both are real conventions
answering different questions (``docs/evidence/temperature-convention-research-2026-09-22.md``).

So the tests that pinned "298 is offered" are INVERTED — nothing is offered by default —
and the safety properties that still hold (never measured, never bare, never a second
path, never scoped to an unregistered profile) are kept, now asserted of the reviewed-rule
path that replaces the exception.

Nothing here describes a nominal value as measured, including the test names.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import nominal
from isaac_api.bl15 import profiles

CONVENTION = profiles.SSRL_BL152_HERFD_ECHEM_V1.profile_id
HISTORICAL = profiles.HISTORICAL_ANGEL_PROFILE_ID
REPO_ROOT = Path(__file__).resolve().parents[3]


def _rule(**overrides) -> nominal.NominalRule:
    """A reviewed rule FOR THIS TEST ONLY — never registered outside a test block."""
    fields = dict(
        rule_id="test-rule-ntp",
        rule_version="1",
        profile_id=CONVENTION,
        profile_version=profiles.SSRL_BL152_HERFD_ECHEM_V1.profile_version,
        official_path=nominal.NOMINAL_TEMPERATURE_PATH,
        convention=nominal.CONVENTION_NTP_STYLE,
        reviewed_basis="synthetic test fixture — not a production rule",
    )
    fields.update(overrides)
    return nominal.NominalRule(**fields)


# --- the default: NOTHING is offered ------------------------------------------


def test_no_profile_gets_a_nominal_temperature_by_default():
    """**INVERTED.** It asserted the BL15-2 profile got 298 K. Nothing gets anything now.

    Covered for the renamed convention id AND its historical alias, because a session
    persisted before the rename asks with the old id and must get the same answer.
    """
    for profile_id in (CONVENTION, HISTORICAL, "some_other_profile", "", None):
        assert nominal.nominal_temperature_for(profile_id) is None, profile_id
    assert nominal.profiles_with_a_nominal_default() == ()


def test_there_is_no_enabled_reviewed_rule_and_adding_one_fails_here():
    """**The emptiness is the policy.** A production rule arrives through this failing
    test and a recorded decision, never as a quiet append."""
    assert nominal.REVIEWED_NOMINAL_RULES == ()


def test_the_superseded_decision_is_recorded_not_erased():
    assert "DEC-43" in nominal.SUPERSEDED_DECISION
    assert "SUPERSEDED 2026-09-22" in nominal.SUPERSEDED_DECISION
    assert "no automatic" in nominal.SUPERSEDED_DECISION
    doc = nominal.__doc__ or ""
    # struck, not deleted — the old claim is visible as a withdrawn claim
    assert "~~298 K is supplied" in doc


def test_the_two_conventions_are_named_cited_and_distinct():
    """Both are real; they answer different questions; neither is a default."""
    ntp, satp = nominal.CONVENTION_NTP_STYLE, nominal.CONVENTION_SATP_STYLE
    assert (ntp.value, ntp.unit) == (293.15, "K")
    assert (satp.value, satp.unit) == (298.15, "K")
    assert "NIST" in ntp.authority
    assert "IUPAC" in satp.authority
    assert "REFERENCE STATE" in satp.authority
    for convention in (ntp, satp):
        state = convention.to_state()
        assert state["research_note"] == (
            "docs/evidence/temperature-convention-research-2026-09-22.md"
        )
        assert "Secondary sources" in state["retrieval_note"]
    assert (REPO_ROOT / "docs/evidence/temperature-convention-research-2026-09-22.md").is_file()


# --- the reviewed-rule path, exercised only through the test seam ------------


def test_a_reviewed_rule_offers_a_labelled_nominal_that_requires_confirmation():
    """The path that REPLACES `DEC-43`: a reviewed, convention-naming rule OFFERS a value.

    Everything a surface needs to keep the number honest travels with it — the
    convention and its authority, ``measured: false``, ``requires_confirmation: true``,
    ``determinism: inferred`` and a disclosure saying the same in words.
    """
    with nominal.reviewed_rule_registered_for_tests(_rule()):
        value = nominal.nominal_temperature_for(CONVENTION)
        assert value is not None
        # the historical id asks the same question and gets the same answer
        assert nominal.nominal_temperature_for(HISTORICAL) == value
        state = value.to_state()
    assert state["value"] == 293.15
    assert state["unit"] == "K"
    assert state["measured"] is False
    assert state["requires_confirmation"] is True
    assert state["determinism"] == "inferred"
    assert "nominal" in state["basis"]
    assert "NOT measured" in state["basis"]
    assert state["convention"]["convention_id"] == "ntp_style_293_15_K"
    assert "NTP-style" in state["disclosure"]
    assert "NOT" in state["disclosure"] and "measured" in state["disclosure"]
    assert "only if a scientist confirms" in state["disclosure"]
    assert state["superseded_decision"] == nominal.SUPERSEDED_DECISION
    json.dumps(state)
    # and the seam closes behind itself
    assert nominal.nominal_temperature_for(CONVENTION) is None


def test_a_rule_reviewed_against_another_version_does_not_apply():
    """A rule is about the convention version a reviewer saw, not about its successor."""
    with nominal.reviewed_rule_registered_for_tests(_rule(profile_version="999")):
        assert nominal.nominal_temperature_for(CONVENTION) is None


def test_measured_is_derived_and_cannot_be_stored_as_true():
    """A stored boolean could be written ``True``; derived, there is nothing to write."""
    with nominal.reviewed_rule_registered_for_tests(_rule()):
        value = nominal.nominal_temperature_for(CONVENTION)
    assert value.measured is False
    assert value.requires_confirmation is True
    with pytest.raises(TypeError):
        nominal.NominalValue(  # type: ignore[call-arg]
            official_path=nominal.NOMINAL_TEMPERATURE_PATH,
            value=1.0,
            unit="K",
            rule=_rule(),
            measured=True,
        )


def test_a_rule_for_another_path_or_profile_cannot_be_constructed():
    """No second path by analogy, and no rule scoped to a convention nobody registered."""
    with pytest.raises(ValueError):
        _rule(official_path="context.pressure_Pa")
    with pytest.raises(ValueError):
        _rule(profile_id="ssrl_bl152_herfd_echem_namng")  # transposed, as a typo would be
    with pytest.raises(ValueError):
        _rule(reviewed_basis="   ")


def test_there_is_no_way_to_ask_for_a_default_at_another_path_or_with_a_fallback():
    """No ``default=`` parameter: a fallback at the call site would move the decision."""
    signature = inspect.signature(nominal.nominal_temperature_for)
    assert list(signature.parameters) == ["profile_id"]


def test_the_word_measured_never_describes_the_value():
    """A sweep of the served strings for a claim that the value WAS measured."""
    rule = _rule()
    for text in (nominal.BASIS, nominal.SOURCE_CLASS, rule.disclosure):
        lowered = text.lower()
        assert "was measured" not in lowered
        assert "as measured" not in lowered
    assert "NOT measured" in nominal.BASIS


def test_no_application_module_calls_the_test_seam():
    """The reviewed-rule seam is exercised by tests and reached by nothing else."""
    package = REPO_ROOT / "apps" / "api" / "isaac_api"
    offenders = []
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "nominal.py":
            continue
        if "reviewed_rule_registered_for_tests" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


# --- what a source SAYS about temperature is a different thing ---------------


def test_a_temperature_statement_is_words_kept_at_level_4_and_never_the_number():
    """`temperature_statement` (2026-09-22) carries a source's words, not a value.

    It has no official path — the words have no home in a numeric field — so it lands in
    the extended context verbatim, while the nominal value (if a reviewed rule ever
    offers one) is a SEPARATE thing at the level-1 path.
    """
    entry = mp.mapping_for("temperature_statement")
    assert entry is not None
    assert entry.official_path is None
    assert entry.placement_level == mp.PLACEMENT_EXTENDED_CONTEXT
    assert not entry.proposable
    assert nominal.NOMINAL_TEMPERATURE_PATH in mp.official_paths()
    assert "never" in entry.reason.lower() or "declined" in entry.reason
