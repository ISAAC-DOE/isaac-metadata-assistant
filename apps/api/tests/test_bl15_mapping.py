"""The corpus->schema registry says what it can and cannot map, and never guesses.

These tests exist because a mapping registry is the easiest place in a historical-import
feature to smuggle in a scientific decision: every ``not_expressible`` row is a row
somebody could "fix" by pointing it at a nearby field, and the record would then assert
something no source states. So the tests are weighted toward the REFUSALS rather than
toward the six mappings that work.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import mapping as mp


# --- the guard that makes the registry checkable rather than asserted --------


def test_every_path_the_registry_names_exists_in_the_vendored_schema():
    """Primary paths, required siblings AND candidate homes — all of them.

    A sibling or a candidate home naming a field that does not exist would mislead
    exactly as much as a bad primary path: a scientist sent to choose between two paths
    is owed two real paths.
    """
    assert mp.registry_paths_exist() == ()


def test_the_path_set_is_read_from_the_schema_and_not_transcribed():
    """A schema refresh must be able to break this registry.

    The alternative — a hard-coded path list — would keep passing while pointing at
    fields the schema had dropped, which is the failure this whole module exists to
    avoid one level up.
    """
    declared = mp.official_paths()
    assert "context.electrochemistry.potential_setpoint_V" in declared
    assert "measurement.series[].channels[].role" in declared
    assert "this.path.does.not.exist" not in declared

    # and it really came from the file, not from a literal in this module
    root = Path(mp.__file__).resolve().parents[4]
    raw = json.loads(
        (root / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )
    assert raw["title"].startswith("ISAAC AI-Ready Scientific Record")


def test_every_concept_in_the_vocabulary_has_been_examined():
    """`None` and `not_expressible` are different, and this keeps them apart.

    An explicit ``not_expressible`` entry is a measured finding: somebody read the
    schema and established there is no field. A missing entry means nobody looked. If
    this test ever fails, the honest fix is to examine the new concept — not to delete
    it from the vocabulary.
    """
    assert mp.unmapped_concepts() == ()
    assert set(mp.MAPPINGS) == set(ev.CONCEPTS)


# --- the refusals ------------------------------------------------------------


def test_only_the_statuses_that_carry_a_value_are_proposable():
    for concept, m in mp.MAPPINGS.items():
        if m.status in (mp.STATUS_DETERMINISTIC, mp.STATUS_NORMALIZED):
            assert m.proposable, concept
            assert m.official_path, concept
        else:
            assert not m.proposable, concept


def test_the_proposable_set_is_exactly_these_five_and_the_number_is_the_point():
    """**Only 5 of 45 concepts in a real historical corpus can reach a field today.**

    Pinned as a number because it is the most honest single statement about what
    historical import can do with this corpus, and because a future slice that raises it
    should have to come here and say why. Raising it by reasoning about the schema is
    legitimate; raising it by pointing a refusal at a nearby field is not.

    ── IT WAS SIX, AND THE SIXTH WAS WRONG ────────────────────────────────────────

    ``acquisition_method`` was mapped ``deterministic`` to ``system.technique`` on the
    reasoning that the corpus names a technique the schema's enum contains verbatim.
    **That was reasoning about what a human reading the corpus knows, and a mapping is
    about what the readers emit.** Measured when the registry was first wired to a route:
    from a macro this concept carries THE MACRO'S OWN NAME, and from a filename the
    profile's lowercase alias reading — and **not one of those is a member of that enum**,
    so it proposed an off-enum value from every source. One alias is a detection MODE,
    which the enum has no member for and which is not a technique at all.

    **So this number went DOWN on a correction, which is the direction worth noticing.**
    The wrong value was fully evidenced — a source literally said it, at a locator — so
    ``fabricated_value_rate`` was 0 and stayed 0 throughout. A suite that only checked for
    fabrication would never have seen it: **a mapping error is not a fabrication**, and
    that is the whole reason this registry is checked separately from the harness.
    """
    assert sorted(c for c, m in mp.MAPPINGS.items() if m.proposable) == [
        "acquisition_epoch",
        "acquisition_timestamp",
        "flow_rate",
        "ph",
        "potential_magnitude",
    ]
    cov = mp.coverage()
    # 45 -> 47 ON 2026-09-22, and the proposable five did NOT move. The two concepts
    # added that day — `temperature_statement` (a source's words about temperature, kept
    # verbatim, never converted) and `contributor_statement` (a person a source names,
    # kept as provenance) — are both `needs_domain_review` and neither is proposable, so
    # the count that answers "what can reach a field today" is unchanged and the
    # needs-review count rises by exactly two. Raising the total did not raise the
    # honest number, which is the point of pinning both.
    assert cov["concepts_total"] == 47
    assert cov["deterministic"] + cov["normalized"] == 5
    assert cov["needs_domain_review"] == 17
    assert cov["not_expressible"] == 24
    assert cov["blocked_by_build"] == 1


def test_not_expressible_never_names_an_official_path():
    """Enforced at construction, and asserted here so the enforcement is visible.

    A ``not_expressible`` row carrying a path would read as a mapping to anyone
    scanning the registry for one.
    """
    for concept, m in mp.MAPPINGS.items():
        if m.status == mp.STATUS_NOT_EXPRESSIBLE:
            assert m.official_path is None, concept

    with pytest.raises(ValueError):
        mp.ConceptMapping(
            concept=ev.CONCEPT_FILTER,
            status=mp.STATUS_NOT_EXPRESSIBLE,
            official_path="system.configuration",
            reason="x",
        )


def test_a_normalized_mapping_cannot_exist_without_a_named_rule():
    with pytest.raises(ValueError):
        mp.ConceptMapping(
            concept=ev.CONCEPT_POTENTIAL_MAGNITUDE,
            status=mp.STATUS_NORMALIZED,
            official_path="context.electrochemistry.potential_setpoint_V",
            reason="x",
        )


def test_a_proposable_mapping_cannot_exist_without_a_path():
    with pytest.raises(ValueError):
        mp.ConceptMapping(
            concept=ev.CONCEPT_PH,
            status=mp.STATUS_DETERMINISTIC,
            official_path=None,
            reason="x",
        )


def test_every_entry_carries_a_reason_a_scientist_could_read():
    """Not a code, not a placeholder. The reason is the deliverable for 39 of 45 rows.

    Length is a crude proxy, so this also rejects the shapes a placeholder takes.
    """
    for concept, m in mp.MAPPINGS.items():
        assert len(m.reason) > 80, f"{concept}: reason too short to explain anything"
        assert m.reason.strip() == m.reason
        lowered = m.reason.lower()
        for placeholder in ("tbd", "todo", "fixme", "n/a", "see above"):
            assert placeholder not in lowered, f"{concept}: placeholder reason"


# --- the entries whose exact behaviour is load-bearing ----------------------


def test_the_potential_magnitude_and_its_reference_basis_are_two_separate_entries():
    """The single most consequential split in the registry.

    A filename states a magnitude and says nothing about what it is measured against.
    If these were one entry, a candidate would carry a setpoint and a basis from one
    act of reading, and the basis would be invented.
    """
    magnitude = mp.mapping_for(ev.CONCEPT_POTENTIAL_MAGNITUDE)
    basis = mp.mapping_for(ev.CONCEPT_POTENTIAL_REFERENCE)
    assert magnitude is not None and basis is not None

    assert magnitude.proposable
    assert magnitude.official_path == "context.electrochemistry.potential_setpoint_V"

    # the basis is NOT proposable, and the schema's own absence vocabulary is recorded
    assert not basis.proposable
    assert basis.status == mp.STATUS_NEEDS_DOMAIN_REVIEW
    assert "not_reported" in basis.allowed_values
    assert "not_convertible_no_reference_offset" in basis.allowed_values

    # potential_scale is a CANDIDATE home, never the mapped path: each of its members
    # is a specific claim and the enum has no "unknown", so it is left absent.
    assert basis.official_path == "context.electrochemistry.potential_vs_RHE.rhe_basis"
    assert "context.electrochemistry.potential_scale" in basis.candidate_homes


def test_the_schemas_absence_vocabulary_is_quoted_accurately():
    """Guards against the registry offering a member the schema does not have.

    A domain question of the form "which of these" is only answerable if the options are
    real, so they are checked against the schema file rather than trusted.
    """
    root = Path(mp.__file__).resolve().parents[4]
    schema = json.loads(
        (root / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )
    node = schema["properties"]["context"]["properties"]["electrochemistry"][
        "properties"
    ]["potential_vs_RHE"]["properties"]["rhe_basis"]
    basis = mp.mapping_for(ev.CONCEPT_POTENTIAL_REFERENCE)
    assert basis is not None
    assert set(basis.allowed_values) == set(node["enum"])

    # and value_V really is nullable, which is what makes "no value, here is why" valid
    value = schema["properties"]["context"]["properties"]["electrochemistry"][
        "properties"
    ]["potential_vs_RHE"]["properties"]["value_V"]
    assert "null" in value["type"]


def test_electrolyte_records_that_satisfying_it_needs_a_concentration_it_lacks():
    """`acid`/`base` supplies neither required field, and the registry has to say so."""
    m = mp.mapping_for(ev.CONCEPT_ELECTROLYTE_OR_MEDIUM)
    assert m is not None and not m.proposable
    assert (
        "context.electrochemistry.electrolyte.concentration_M" in m.requires_siblings
    )

    root = Path(mp.__file__).resolve().parents[4]
    schema = json.loads(
        (root / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )
    electrolyte = schema["properties"]["context"]["properties"]["electrochemistry"][
        "properties"
    ]["electrolyte"]
    assert set(electrolyte["required"]) == {"name", "concentration_M"}


def test_assets_are_blocked_by_the_build_and_not_by_the_schema():
    """Two different obstacles with two different remedies, kept apart.

    The schema HAS the right vocabulary for these files. What is missing is a digest
    this build refuses to compute, which is an application fact — so the status is
    `blocked_by_build`, and a reader is not sent to ask upstream for a field that
    already exists.
    """
    m = mp.mapping_for(ev.CONCEPT_SCAN_COMMAND)
    assert m is not None
    assert m.status == mp.STATUS_BLOCKED_BY_BUILD
    assert m.official_path == "assets[].uri"
    assert "sha256" in m.reason

    root = Path(mp.__file__).resolve().parents[4]
    schema = json.loads(
        (root / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )
    assets = schema["properties"]["assets"]["items"]
    assert "sha256" in assets["required"]


def test_the_beamline_account_string_is_refused_rather_than_unmapped():
    """The one entry it would be actively harmful to "fix".

    An acquisition header names the account the beamline software ran under. The schema
    has an uploader field; it is server-stamped behind a trust basis no verifier in this
    build mints, and is absent from every record this deployment produces. Copying a
    beamline account string into it would manufacture the attribution that boundary
    exists to withhold.
    """
    m = mp.mapping_for(ev.CONCEPT_SPEC_USER_STRING)
    assert m is not None
    assert m.status == mp.STATUS_NOT_EXPRESSIBLE
    assert m.official_path is None
    assert m.candidate_homes == ()
    assert "attribution.uploaded_by" not in (m.official_path or "")


def test_cycling_state_has_no_field_and_no_path_is_invented_for_it():
    """The corpus's most important experimental variable, and the schema has no field.

    A candidate home is NAMED (a per-series condition, which is schema-legal) and is
    deliberately not applied — the registry records where it could go, not where it goes.
    """
    for concept in (ev.CONCEPT_CYCLING_STATE, ev.CONCEPT_BEFORE_AFTER_STATE):
        m = mp.mapping_for(concept)
        assert m is not None
        assert m.status == mp.STATUS_NOT_EXPRESSIBLE
        assert m.official_path is None
        assert "measurement.series[].conditions" in m.candidate_homes


def test_system_configuration_is_never_a_default_landing_place():
    """A refusal must not quietly become "put it in the extension namespace".

    That would convert "the schema has nowhere for this" into a decision disguised as a
    default. Where `system.configuration` appears it is a CANDIDATE home carrying the
    two-sided caution, never the mapped path — and the caution names both halves: the
    schema designates the namespace, and its fields are unclassified with no write route.
    """
    for concept, m in mp.MAPPINGS.items():
        assert m.official_path != "system.configuration", concept
        if "system.configuration" in m.candidate_homes:
            assert mp.SYSTEM_CONFIGURATION_CAUTION in m.reason or (
                "system.configuration" in m.reason
            ), concept


def test_technique_is_DEFERRED_because_no_reader_emits_an_enum_member():
    """INVERTED 2026-09-16. It asserted ``deterministic`` and that was wrong.

    The old name — "because the enum contains it verbatim" — states the error exactly:
    the enum does contain ``HERFD-XAS`` verbatim, and **nothing in this build ever
    produces that string for this concept**. The enum containing a value is a fact about
    the schema; what a reader emits is a fact about the readers, and only the second one
    decides whether a mapping is a transcription.

    Kept and inverted rather than deleted, because a test that asserted the defect is the
    most useful place to record why it looked right.
    """
    m = mp.mapping_for(ev.CONCEPT_ACQUISITION_METHOD)
    assert m is not None
    assert m.status == mp.STATUS_NEEDS_DOMAIN_REVIEW
    assert not m.proposable
    # The path is still NAMED, because a scientist asked to choose is owed the field the
    # choice lands in — that is what `needs_domain_review` means as against
    # `not_expressible`.
    assert m.official_path == "system.technique"

    root = Path(mp.__file__).resolve().parents[4]
    schema = json.loads(
        (root / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )
    enum = schema["properties"]["system"]["properties"]["technique"]["enum"]
    assert "HERFD-XAS" in enum
    # The options offered are real members, so the domain question is answerable in one
    # word and the answer is auditable.
    assert set(m.allowed_values) <= set(enum)

    # AND THE MEASUREMENT THE CORRECTION RESTS ON, asserted rather than described: the
    # profile's own alias readings for this concept are not enum members. This is what
    # makes the old `deterministic` status impossible rather than merely unlucky.
    from isaac_api.bl15 import profiles

    # THE HISTORICAL ID, DELIBERATELY: `ssrl_bl152_angel` was renamed to the convention
    # it encodes on 2026-09-22 and must still resolve, so this lookup doubles as a check
    # that the alias did not break a caller written before the rename.
    aliases = profiles.profile_for("ssrl_bl152_angel").acquisition_method_aliases
    assert aliases, "the profile recognises no acquisition-method token at all"
    readings = {normalized for _token, normalized in aliases}
    assert readings.isdisjoint(set(enum)), (
        "a profile alias now normalises straight to a schema technique member, so the "
        f"deterministic reading may be recoverable for those tokens: {readings & set(enum)}"
    )


def test_shared_reasons_have_exactly_one_home():
    """A correction to a shared reason cannot land in one copy of three.

    `CLAUDE.md` records several occasions where a claim was corrected in some of its
    homes and not others; a module-level constant removes the possibility.
    """
    assert mp.CYCLING_STATE_NO_FIELD_REASON == (
        mp.mapping_for(ev.CONCEPT_CYCLING_STATE).reason
    )
    assert mp.ASSETS_BLOCKED_REASON == mp.mapping_for(ev.CONCEPT_SCAN_COMMAND).reason


def test_the_temperature_reason_names_the_specific_wrong_default():
    """`TEMPERATURE_ABSENT_REASON` belongs to NO concept, deliberately.

    No concept maps a temperature to ``context.temperature_K``: a source either states
    none, or states one in words that this build keeps verbatim and never converts — so
    there is nothing to map, and the constant exists for the RECONSTRUCTION to cite when
    it reports why a candidate cannot be export-complete. It is asserted here so it has
    one home rather than being re-worded at the call site. (Corrected 2026-09-22: this
    used to say "because no source states a temperature", which the temperature
    statement concept added that day made false.)

    It must name **298** explicitly. A reason that only said "do not guess" invites the
    guess anyway, because room temperature is the obvious one and a plausible number in
    a required field is indistinguishable downstream from a measured one.
    """
    reason = mp.TEMPERATURE_ABSENT_REASON
    assert "temperature" in reason.lower()
    # STILL NAMES 298, and 2026-09-22 made that MORE important rather than less: the
    # 298 K exception (DEC-43) was withdrawn that day, and the sentence now says both
    # that 298 must not be defaulted in AND that no automatic offer of any number is
    # made. A `temperature_statement` concept exists since the same day, and it maps a
    # source's WORDS to the extended context — never a number to this field, which is
    # why the reason below still belongs to no concept.
    assert "298" in reason
    assert "must not be defaulted" in reason
    assert "offers no value automatically" in reason
    assert "context.temperature_K" in reason
    # INVERTED 2026-09-22. This sentence used to open "this corpus states no
    # temperature anywhere" — and it is served for EVERY archive, including one whose
    # notes say "held at room temperature throughout". That made it false for exactly
    # the corpus it is most needed for. It must now be true in both cases: a corpus
    # that states none, and one that states one only in words (or as a labelled line
    # this build keeps verbatim and never converts). The blocking itself is unchanged.
    assert "states no temperature anywhere" not in reason
    assert "verbatim" in reason and "never converted" in reason
    assert "Not recorded" in reason
    assert mp.unmapped_concepts() == ()
    assert not any(
        reason == m.reason for m in mp.MAPPINGS.values()
    ), "no concept maps temperature, because no source states one"


def test_to_state_is_complete_and_round_trips_as_json():
    for concept, m in mp.MAPPINGS.items():
        state = m.to_state()
        assert set(state) == {
            "concept",
            "status",
            "official_path",
            "reason",
            "rule",
            "requires_siblings",
            "allowed_values",
            "candidate_homes",
            "proposable",
            # DEC-41 / CTX-001, added 2026-09-17. The key set is pinned rather than
            # sampled, so adding a served key has to come here and say so — which is
            # the whole reason this test was written as an equality.
            "placement_level",
            "placement_name",
            "domain_questions",
            "unresolved_questions",
            # ADDED 2026-09-22 for "Data Quality Notes" — the scientist-facing name the
            # domain owner uses for the corpus's quality remarks. `None` for every
            # concept whose own name reads well enough.
            "scientist_label",
            # ADDED 2026-09-22 — how many values the concept is expected to have
            # (`mp.RULE_CARDINALITY`), so a surface can say "varies by scan" from the
            # registry instead of calling per-scan variation a disagreement.
            "cardinality",
        }, concept
        json.dumps(state)


def test_an_unknown_concept_or_status_is_refused_at_construction():
    with pytest.raises(ValueError):
        mp.ConceptMapping(
            concept="not_a_concept",
            status=mp.STATUS_NOT_EXPRESSIBLE,
            official_path=None,
            reason="x" * 100,
        )
    with pytest.raises(ValueError):
        mp.ConceptMapping(
            concept=ev.CONCEPT_FILTER,
            status="probably_fine",
            official_path=None,
            reason="x" * 100,
        )
