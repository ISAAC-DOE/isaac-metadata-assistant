"""`CTX-002` — the Extended Context companion, and the two things it must never do.

The weight of this file is deliberately on the DENIALS. A companion that carries a
scientist's metadata is easy to write; a companion that cannot leak into the official
record, cannot gate an export, and cannot be mistaken for a field value is the thing
`DEC-41` level 4 actually asks for, and each of those is a property somebody could break
without noticing.

**THE TWO TESTS THE TASK NAMES ARE BOTH HERE AND ARE DIFFERENT CLAIMS.** One says a rich
companion cannot rescue an incomplete record — the schema still refuses it. The other
says an experiment with NO companion exports byte-identically to how it did before this
module existed, which is the test that proves a COMPANION was added and not a MUTATION.
The second is the stronger of the two and is the one that would catch a well-meant
"while we are here, let us just put the extended context in the record".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api import extended_context as xc
from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import mapping as mp
from isaac_records.export import build_sidecar, transform
from isaac_records.official import validate_official

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"

#: Fixed so an exported record is byte-comparable between two runs. Nothing in the
#: truth path is stubbed: `transform` takes both as parameters precisely so a caller
#: can make an export reproducible.
RECORD_ID = "01SYNTHETICZZFIXTUREZZ0000"  # 26 chars of [0-9A-Z], as the schema requires
NOW = "2099-01-01T00:00:00Z"


def a_reading(
    concept: str = ev.CONCEPT_FILTER,
    *,
    raw: str = "ffilter35",
    source: str = "46_04_ZZ2_base_after1500Cycling_ffilter35_newSpots_1600mV",
    locator: str = "filename token 6",
    normalized=35,
    rule: str | None = "bl15.filenames.filter.v1",
    scope: str = ev.SCOPE_MEASUREMENT,
) -> ev.SourceEvidence:
    """SYNTHETIC read evidence. The sample code is `ZZ2`, which no real sample uses."""
    return ev.SourceEvidence(
        evidence_id="e1",
        source_path=source,
        source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
        locator=locator,
        raw_literal=raw,
        concept=concept,
        parser_id="bl15.filenames",
        determinism=(
            ev.DETERMINISM_NORMALIZED if rule else ev.DETERMINISM_READ
        ),
        scope=scope,
        normalized_value=normalized,
        normalization_rule=rule,
        profile_id="ssrl_bl152_angel",
        profile_version="1",
    )


def an_entry(**kwargs) -> xc.ContextEntry:
    defaults = dict(
        entry_id="x1",
        concept=ev.CONCEPT_CYCLING_STATE,
        raw_literal="after1500Cycling",
        source="32_03_ZZ2_base_after1500Cycling_filter20_1500mV",
        locator="filename token 5",
        placement_level=mp.mapping_for(ev.CONCEPT_CYCLING_STATE).placement_level,
    )
    defaults.update(kwargs)
    return xc.ContextEntry(**defaults)  # type: ignore[arg-type]


# --- it never enters the official record, and never gates export ------------


def test_an_experiment_with_no_extended_context_exports_byte_identically():
    """**THE TEST THAT PROVES A COMPANION WAS ADDED AND NOT A MUTATION.**

    The same draft, exported with nothing about extended context anywhere near it,
    produces the record this repository produced before this module existed — and the
    proof is not "we did not change export.py", it is that the record and the sidecar
    are byte-identical across two transforms and that neither contains a single key or
    marker belonging to the companion.
    """
    draft = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = transform(draft, record_id=RECORD_ID, now=NOW)
    second = transform(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        record_id=RECORD_ID,
        now=NOW,
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    blob = json.dumps(first, sort_keys=True)
    assert xc.ARTIFACT_KIND not in blob
    assert xc.STATE_KEY not in blob
    assert "placement_level" not in blob
    assert validate_official(first, REPO_ROOT).ok

    sidecar = build_sidecar(draft, first)
    assert xc.ARTIFACT_KIND not in json.dumps(sidecar, sort_keys=True)


def test_a_companion_smuggled_into_the_draft_reaches_the_record_nowhere():
    """Level 4 cannot leak even when a caller puts it where export looks.

    :data:`extended_context.STATE_KEY` lives BESIDE ``draft`` in the experiment state
    document, so the normal case is structural. This test attacks the abnormal one: a
    caller writes the companion INTO the draft anyway. The exported record is still
    byte-identical, because ``transform`` reads a closed set of draft keys and the
    companion is not one of them.
    """
    draft = json.loads(FIXTURE.read_text(encoding="utf-8"))
    clean = transform(draft, record_id=RECORD_ID, now=NOW)

    context = xc.build(
        experiment_id="exp-synthetic",
        entries=[an_entry(), an_entry(entry_id="x2", concept=ev.CONCEPT_TRIGGER,
                                      raw_literal="trigger_on",
                                      placement_level=4)],
        generated_utc=NOW,
    )
    smuggled = json.loads(FIXTURE.read_text(encoding="utf-8"))
    smuggled[xc.STATE_KEY] = context.to_state()
    polluted = transform(smuggled, record_id=RECORD_ID, now=NOW)

    assert json.dumps(polluted, sort_keys=True) == json.dumps(clean, sort_keys=True)
    assert xc.ARTIFACT_KIND not in json.dumps(polluted, sort_keys=True)


def test_a_rich_companion_cannot_rescue_an_incomplete_official_record():
    """**Level 4 never gates export, in the direction that matters.**

    An experiment can carry as much extended context as it likes and the official
    schema decides on its own. Here the draft is stripped of ``descriptors``, which the
    schema requires, and the companion carries eleven provenance-backed entries: the
    record is still refused, with exactly the error it would have had with no companion
    at all.
    """
    draft = json.loads(FIXTURE.read_text(encoding="utf-8"))
    draft.pop("descriptors_outputs", None)
    incomplete = transform(draft, record_id=RECORD_ID, now=NOW)

    bare_report = validate_official(incomplete, REPO_ROOT)
    assert not bare_report.ok

    context = xc.build(
        experiment_id="exp-synthetic",
        entries=[
            an_entry(entry_id=f"x{i}", raw_literal=f"after{i}00Cycling")
            for i in range(1, 12)
        ],
        generated_utc=NOW,
    )
    assert len(context.entries) == 11

    with_context = transform(draft, record_id=RECORD_ID, now=NOW)
    report = validate_official(with_context, REPO_ROOT)
    assert not report.ok
    assert [e.message for e in report.errors] == [
        e.message for e in bare_report.errors
    ]
    # and the companion is queryable while the record is refused — the two are simply
    # unrelated, which is the whole claim
    assert context.for_concept(ev.CONCEPT_CYCLING_STATE)


def test_the_state_key_is_not_a_draft_key():
    """The location IS the guarantee, so the location is asserted.

    ``proposals.STATE_KEY``'s reasoning, reused: the draft is what export reads, so a
    companion inside it would travel into the export draft and the submission content
    signature. Out here, "inert to export" is structural rather than promised.
    """
    draft = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert xc.STATE_KEY not in draft
    assert xc.STATE_KEY == "extended_context"


# --- a reader cannot mistake it for an official field value -----------------


def test_no_entry_can_ever_claim_to_be_an_official_field_value():
    entry = an_entry()
    assert entry.is_official_field_value is False
    assert entry.to_state()["is_official_field_value"] is False
    # derived, so it cannot be constructed the other way
    with pytest.raises(TypeError):
        xc.ContextEntry(  # type: ignore[call-arg]
            entry_id="x",
            concept=ev.CONCEPT_TRIGGER,
            raw_literal="t",
            source="s",
            locator="l",
            placement_level=4,
            is_official_field_value=True,
        )


def test_the_companion_document_says_what_it_is_not():
    context = xc.build(
        experiment_id="exp-synthetic", entries=[an_entry()], generated_utc=NOW
    )
    doc = context.companion_document(RECORD_ID)
    assert doc["artifact_kind"] == xc.ARTIFACT_KIND
    assert doc["record_id"] == RECORD_ID
    claim = doc["not_official"]
    assert "not an official ISAAC record" in claim
    assert "official ISAAC schema alone" in claim or "official schema alone" in claim
    # It deliberately claims NO schema version: claiming one is the confusion the whole
    # module exists to prevent.
    assert "schema_version" not in doc
    assert "isaac_record_version" not in doc


def test_the_companion_is_a_sibling_file_and_not_a_record_field():
    assert xc.companion_filename("01ABC") == "01ABC.context.json"
    assert xc.COMPANION_SUFFIX.startswith(".")
    # reads the same way the evidence sidecar does, which is the point
    assert xc.companion_filename("01ABC") != "01ABC.json"


# --- provenance-backed: all four, or no entry -------------------------------


@pytest.mark.parametrize(
    "missing", ["concept", "raw_literal", "source", "locator", "entry_id"]
)
def test_an_entry_without_its_provenance_cannot_be_constructed(missing):
    """`DEC-41`: concept, raw literal, source and locator on every entry.

    Enforced rather than documented, because *"structured, not a prose dump"* is a
    property a single careless call site would otherwise end.
    """
    with pytest.raises(ValueError) as excinfo:
        an_entry(**{missing: ""})
    assert missing in str(excinfo.value)


def test_a_reading_becomes_an_entry_with_nothing_recomputed():
    """The reuse `CTX-002` asks for: ``bl15.evidence`` already records all four.

    And the literal survives. ``ffilter35`` stays ``ffilter35`` with ``35`` beside it
    and the rule that produced it named — the corpus's own typo is the case that makes
    this worth asserting.
    """
    item = a_reading()
    entry = xc.entry_from_source_evidence(item, entry_id="e1")
    assert entry.concept == item.concept
    assert entry.raw_literal == "ffilter35"
    assert entry.normalized_value == 35
    assert entry.normalization_rule == "bl15.filenames.filter.v1"
    assert entry.source == item.source_path
    assert entry.locator == item.locator
    assert entry.profile_id == "ssrl_bl152_angel"
    assert entry.profile_version == "1"
    assert entry.reading_scope == ev.SCOPE_MEASUREMENT
    # the level came from the registry, not from the caller
    assert entry.placement_level == mp.mapping_for(ev.CONCEPT_FILTER).placement_level
    assert entry.official_path == mp.mapping_for(ev.CONCEPT_FILTER).official_path


def test_the_constructor_from_evidence_cannot_be_talked_into_a_level_4_skip():
    """There is no level argument, which is stronger than checking one.

    A potential magnitude read off a filename has a native field, so the entry built
    from it is level 1 — and no caller can ask for level 4, because the parameter does
    not exist.
    """
    item = a_reading(
        concept=ev.CONCEPT_POTENTIAL_MAGNITUDE,
        raw="1500mV",
        normalized=1.5,
        rule="bl15.filenames.potential.v1",
    )
    entry = xc.entry_from_source_evidence(item, entry_id="e2")
    assert entry.placement_level == mp.PLACEMENT_OFFICIAL_FIELD
    assert entry.official_path == "context.electrochemistry.potential_setpoint_V"
    # and constructing the same thing by hand at level 4 is refused
    with pytest.raises(mp.PlacementSkipError):
        an_entry(concept=ev.CONCEPT_POTENTIAL_MAGNITUDE, placement_level=4)


def test_an_unexplained_normalisation_cannot_exist():
    with pytest.raises(ValueError):
        an_entry(determinism=ev.DETERMINISM_NORMALIZED, normalization_rule=None)


# --- Experiment / Run scoped ------------------------------------------------


def test_run_scope_requires_a_run_and_experiment_scope_forbids_one():
    """A beamtime-wide statement attached to one run reads as a manual entry there.

    ``bl15.reconstruct``'s rule, one layer along: *"a README value rendered 94 times as
    though it had been entered 94 times is a lie about where it came from"*.
    """
    with pytest.raises(ValueError):
        an_entry(scope=xc.SCOPE_RUN)
    with pytest.raises(ValueError):
        an_entry(scope=xc.SCOPE_EXPERIMENT, run_id="run-1")
    assert an_entry(scope=xc.SCOPE_RUN, run_id="run-1").run_id == "run-1"


def test_inheritance_is_visible_rather_than_copied():
    """`DEC-40`'s posture, read-only.

    :meth:`for_run` is a run's OWN entries; :meth:`applying_to_run` adds the inherited
    experiment-scoped ones. The two are separate methods because they are separate
    claims, and every entry still carries its own scope so a reader can see which is
    which.
    """
    shared = an_entry(entry_id="shared", concept=ev.CONCEPT_BEAMSIZE,
                      raw_literal="beam <mm> x <mm>", placement_level=2,
                      reading_scope=ev.SCOPE_BEAMTIME)
    mine = an_entry(entry_id="mine", scope=xc.SCOPE_RUN, run_id="run-1")
    theirs = an_entry(entry_id="theirs", scope=xc.SCOPE_RUN, run_id="run-2")
    context = xc.build(
        experiment_id="exp", entries=[shared, mine, theirs], generated_utc=NOW
    )

    assert [e.entry_id for e in context.for_run("run-1")] == ["mine"]
    assert [e.entry_id for e in context.applying_to_run("run-1")] == ["shared", "mine"]
    assert [e.entry_id for e in context.experiment_scoped()] == ["shared"]
    assert context.run_ids() == ("run-1", "run-2")
    # nothing was copied onto a run
    assert sum(1 for e in context.entries if e.entry_id == "shared") == 1


def test_it_is_queryable_by_the_three_things_a_scientist_asks():
    entries = [
        an_entry(entry_id="a", concept=ev.CONCEPT_CYCLING_STATE),
        an_entry(entry_id="b", concept=ev.CONCEPT_FILTER, raw_literal="filter20",
                 placement_level=2),
        an_entry(entry_id="c", concept=ev.CONCEPT_TRIGGER, raw_literal="trig",
                 placement_level=4, scope=xc.SCOPE_RUN, run_id="run-1"),
    ]
    context = xc.build(experiment_id="exp", entries=entries, generated_utc=NOW)
    assert [e.entry_id for e in context.for_concept(ev.CONCEPT_FILTER)] == ["b"]
    assert [e.entry_id for e in context.at_level(4)] == ["c"]
    assert context.concepts() == ("cycling_state", "filter", "trigger")
    assert context.by_level() == {"1": 0, "2": 1, "3": 1, "4": 1}


def test_nothing_is_deduplicated():
    """Sixteen witnesses to one fact is sixteen locators, and losing fifteen is a loss."""
    same = [
        an_entry(entry_id=f"w{i}", locator=f"{i}.dat · #P line 3") for i in range(16)
    ]
    context = xc.build(experiment_id="exp", entries=same, generated_utc=NOW)
    assert len(context.entries) == 16
    assert len({e.locator for e in context.entries}) == 16


def test_an_open_question_travels_with_the_companion():
    item = a_reading(
        concept=ev.CONCEPT_LEGACY_NUMBER, raw="32", normalized=32, rule=None
    )
    entry = xc.entry_from_source_evidence(item, entry_id="e3")
    assert entry.unresolved_questions == ("Q16",)
    context = xc.build(experiment_id="exp", entries=[entry], generated_utc=NOW)
    assert context.open_questions() == ("Q16",)
    assert context.companion_document(RECORD_ID)["open_domain_questions"] == ["Q16"]


# --- versioned, and durable without a migration -----------------------------


def test_the_artifact_version_and_the_profile_version_are_different_versions():
    """They answer different questions and are both carried on every entry that has one."""
    entry = xc.entry_from_source_evidence(a_reading(), entry_id="e1")
    context = xc.build(experiment_id="exp", entries=[entry], generated_utc=NOW)
    assert context.to_state()["artifact_version"] == xc.ARTIFACT_VERSION
    assert entry.to_state()["profile_version"] == "1"
    assert xc.ARTIFACT_VERSION == "1"


def test_an_experiment_written_before_this_existed_hydrates_to_an_empty_companion():
    """Why no migration is required, asserted rather than asserted-in-prose."""
    assert xc.hydrate(None, experiment_id="exp").entries == ()
    assert xc.hydrate({}, experiment_id="exp").entries == ()
    assert xc.hydrate(7, experiment_id="exp").entries == ()
    assert xc.hydrate({"entries": "not a list"}).entries == ()
    assert xc.state_payload(None) is None
    assert xc.state_payload(xc.ExtendedContext(experiment_id="exp")) is None


def test_a_stored_entry_this_build_cannot_read_is_carried_not_discarded():
    """`CLAUDE.md` §11: a malformed PERSISTED value belongs to a reader who did nothing
    wrong, so it is read rather than refused — and an entry nobody can interpret is
    carried verbatim rather than dropped."""
    stored = xc.build(
        experiment_id="exp", entries=[an_entry()], generated_utc=NOW
    ).to_state()
    stored["entries"].append({"entry_id": "broken", "concept": ev.CONCEPT_TRIGGER})
    stored["entries"].append(42)

    read = xc.hydrate(stored)
    assert [e.entry_id for e in read.entries] == ["x1"]
    assert len(read.unreadable) == 2
    assert read.unreadable[0]["entry_id"] == "broken"
    assert read.unreadable[1] == {"unreadable_entry": 42}
    # and it survives a second round trip without losing the unreadable half
    again = xc.hydrate(read.to_state())
    assert len(again.entries) == 1
    assert len(again.unreadable) == 2


def test_a_stored_companion_round_trips_through_json():
    context = xc.build(
        experiment_id="exp",
        entries=[
            xc.entry_from_source_evidence(a_reading(), entry_id="e1"),
            an_entry(entry_id="x2", scope=xc.SCOPE_RUN, run_id="run-9"),
        ],
        generated_utc=NOW,
    )
    blob = json.dumps(context.to_state(), sort_keys=True)
    read = xc.hydrate(json.loads(blob))
    assert read.experiment_id == "exp"
    assert read.generated_utc == NOW
    assert [e.entry_id for e in read.entries] == ["e1", "x2"]
    assert read.entries[0].raw_literal == "ffilter35"
    assert read.entries[1].run_id == "run-9"
    assert json.dumps(read.to_state(), sort_keys=True) == blob


def test_db_write_owned_tables_is_unchanged_by_this_feature():
    """No table, no migration — `CTX-002`'s explicit constraint, and checkable.

    The nine app-owned tables as of 2026-09-17. If a future slice needs a table for
    extended context it will fail here, which is the point: that is a decision with an
    approval packet and an operator act behind it, not an append.
    """
    from isaac_api import db_write

    assert set(db_write.OWNED_TABLES) == {
        "isaac_experiments",
        "isaac_schema_migrations",
        "isaac_runs",
        "isaac_run_projection",
        "isaac_experiment_revisions",
        "isaac_run_revisions",
        "isaac_revision_changes",
        "isaac_submissions",
        "isaac_submission_runs",
    }
