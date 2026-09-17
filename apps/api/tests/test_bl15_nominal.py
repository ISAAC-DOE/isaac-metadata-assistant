"""`DEC-43` / `CTX-003` — 298 K, and the four conditions that keep it from spreading.

**ONE TEST PER CONDITION, WHICH IS WHAT THE DECISION ASKS FOR BY NAME.** `DEC-43` is the
only value in this programme this repository supplies without a source, so the tests are
not about whether the number is right — it is a room-temperature assumption, and a
scientist adopted it — but about whether the four fences hold. A fence nobody tested is
the reason a named exception becomes a general habit.

Nothing here describes the value as measured, including the test names.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import nominal
from isaac_api.bl15 import profiles

ANGEL = profiles.SSRL_BL152_ANGEL_V1.profile_id


# --- condition (i): the provenance says it is NOT measured ------------------


def test_the_value_can_never_be_serialized_without_the_nominal_qualifier():
    """**`DEC-43` (i): a record showing 298 K without the qualifier is a DEFECT.**

    So there is no code path that emits the number bare. ``measured`` and ``basis`` are
    always present, ``measured`` is ``False``, and the disclosure sentence says in words
    what the booleans say in structure.
    """
    value = nominal.nominal_temperature_for(ANGEL)
    assert value is not None
    state = value.to_state()
    assert state["value"] == 298
    assert state["unit"] == "K"
    assert state["measured"] is False
    assert state["basis"] == "nominal room temperature"
    assert state["source_class"] == "domain guidance / project-owner adopted"
    assert state["decision_ref"] == "DEC-43"
    # every serialization carries both halves of the qualifier
    assert {"measured", "basis", "source_class", "disclosure"} <= set(state)
    assert "NOT measured" in state["disclosure"]
    json.dumps(state)


def test_measured_is_derived_and_cannot_be_stored_as_true():
    """A stored boolean could be written ``True`` and the number would travel lying.

    Derived, there is nothing to write. The constructor refuses the keyword outright,
    which is a stronger guarantee than a validator that runs after assignment.
    """
    value = nominal.nominal_temperature_for(ANGEL)
    assert value.measured is False
    with pytest.raises(TypeError):
        nominal.NominalValue(  # type: ignore[call-arg]
            official_path=nominal.NOMINAL_TEMPERATURE_PATH,
            value=298,
            unit="K",
            basis=nominal.BASIS,
            source_class=nominal.SOURCE_CLASS,
            profile_id=ANGEL,
            profile_version="1",
            decision_ref="DEC-43",
            disclosure=nominal.DISCLOSURE,
            measured=True,
        )


def test_a_nominal_value_with_no_basis_or_source_class_is_refused():
    """The qualifier is mandatory, not optional — condition (i) in one constructor."""
    for missing in ("basis", "source_class"):
        kwargs = dict(
            official_path=nominal.NOMINAL_TEMPERATURE_PATH,
            value=298,
            unit="K",
            basis=nominal.BASIS,
            source_class=nominal.SOURCE_CLASS,
            profile_id=ANGEL,
            profile_version="1",
            decision_ref="DEC-43",
            disclosure=nominal.DISCLOSURE,
        )
        kwargs[missing] = ""
        with pytest.raises(ValueError):
            nominal.NominalValue(**kwargs)  # type: ignore[arg-type]


def test_the_word_measured_never_describes_the_value_anywhere_in_this_module():
    """A mechanical sweep of the served strings, not of the prose around them.

    Every string this module can put in front of a scientist is checked for a claim
    that the value WAS measured. The check is on the served text rather than on the
    whole file because the file legitimately contains the phrase *"NOT measured"* and
    the explanation of why.
    """
    for text in (nominal.BASIS, nominal.SOURCE_CLASS, nominal.DISCLOSURE):
        lowered = text.lower()
        assert "was measured" not in lowered
        assert "as measured" not in lowered
    assert "nominal" in nominal.BASIS.lower()
    assert "NOT measured" in nominal.DISCLOSURE


# --- condition (ii): BL15-2 Angel profile ONLY ------------------------------


def test_no_other_profile_can_reach_the_nominal_temperature():
    """**`DEC-43` (ii), and the lookup is what makes it structural.**

    A profile that does not match gets ``None``, so its caller has nothing to write and
    the field stays absent — which is the pre-`DEC-43` behaviour, preserved for everyone
    else. An unregistered id and ``None`` itself are covered too, because "some other
    beamline's importer" is exactly the caller this fence exists for.
    """
    assert nominal.nominal_temperature_for(ANGEL) is not None
    assert nominal.nominal_temperature_for("some_other_beamline_profile") is None
    assert nominal.nominal_temperature_for("") is None
    assert nominal.nominal_temperature_for(None) is None
    assert nominal.profiles_with_a_nominal_default() == (ANGEL,)


def test_a_non_matching_profile_leaves_the_field_absent_and_the_record_blocked():
    """The consequence of ``None``, stated as a test rather than as a comment.

    ``context.temperature_K`` is required by the schema whenever a context block is
    present, so a profile with no nominal default keeps producing an incomplete
    candidate — and ``TEMPERATURE_ABSENT_REASON`` is the sentence that explains it,
    which still says the parser must not default the number.
    """
    assert nominal.nominal_temperature_for("another_profile") is None
    reason = mp.TEMPERATURE_ABSENT_REASON
    assert "must not be defaulted into context.temperature_K by this application" in (
        reason
    )
    assert "stays absent" in reason
    # and the narrowing is disclosed in the same sentence rather than left to contradict
    assert "DEC-43" in reason
    assert "BL15-2 Angel" in reason


def test_a_default_scoped_to_an_unregistered_profile_cannot_be_constructed():
    """Otherwise a typo would create a default no profile can reach and none can audit."""
    with pytest.raises(ValueError):
        nominal.NominalValue(
            official_path=nominal.NOMINAL_TEMPERATURE_PATH,
            value=298,
            unit="K",
            basis=nominal.BASIS,
            source_class=nominal.SOURCE_CLASS,
            profile_id="ssrl_bl152_angle",  # transposed, as a typo would be
            profile_version="1",
            decision_ref="DEC-43",
            disclosure=nominal.DISCLOSURE,
        )


# --- condition (iii): it generalizes to nothing -----------------------------


def test_there_is_exactly_one_unsourced_default_and_a_second_fails_here():
    """**`DEC-43` (iii): no second such default may be added by analogy with this one.**

    This is the guard the task asks for. It is an equality on the whole registry rather
    than a length check, so a second default cannot arrive as a quiet append: it arrives
    through this failing test, which is where the argument for it belongs.
    """
    assert len(nominal.NOMINAL_DEFAULTS) == 1
    only = nominal.NOMINAL_DEFAULTS[0]
    assert only.official_path == "context.temperature_K"
    assert only.profile_id == ANGEL
    assert only.value == 298
    assert [d.official_path for d in nominal.NOMINAL_DEFAULTS] == [
        "context.temperature_K"
    ]


def test_there_is_no_way_to_ask_for_a_default_at_another_path():
    """The lookup is by profile AND path, so it answers for one field and no other.

    And there is deliberately no ``default=`` parameter: a parameter that let a caller
    supply a fallback would move the decision to the call site, and `DEC-43`'s whole
    shape is that the decision is made once, dated and scoped.
    """
    assert nominal.nominal_temperature_for(ANGEL).official_path == (
        "context.temperature_K"
    )
    import inspect

    signature = inspect.signature(nominal.nominal_temperature_for)
    assert list(signature.parameters) == ["profile_id"]


def test_it_is_not_a_corpus_concept_and_does_not_move_the_45():
    """**`DEC-43` (iv): the corpus states no temperature anywhere.**

    So there is nothing to read, no source path and no locator — and expressing it as
    ``SourceEvidence`` would require inventing both. It is therefore NOT in the concept
    vocabulary, the registry still examines 45 concepts, and the placement counts are
    unmoved by this module existing.
    """
    from isaac_api.bl15 import evidence as ev

    assert "temperature" not in {c.lower() for c in ev.CONCEPTS}
    assert not any("temperature" in c for c in ev.CONCEPTS)
    assert mp.coverage()["concepts_total"] == 45
    assert mp.unmapped_concepts() == ()
    # and the value's own path is a level-1 field, so nothing about it goes near the
    # extended-context companion
    assert nominal.NOMINAL_TEMPERATURE_PATH in mp.official_paths()


def test_the_authority_is_named_as_a_person_and_not_as_a_file():
    """Condition (iv)'s other half: it is the scientist's authority, not the parser's.

    A reader must never be able to conclude that something in the archive said it, which
    is why the source class names domain guidance and the disclosure says the corpus
    states no temperature.
    """
    value = nominal.nominal_temperature_for(ANGEL)
    assert "project-owner adopted" in value.source_class
    assert "no source in the corpus" in value.disclosure
    assert "scientist's authority" in value.disclosure
