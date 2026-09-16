"""Candidates a scientist reviews — never a value this module chose.

The tests are weighted toward the three things this module is forbidden to do, because
it is the only module in the package that interprets anything and therefore the only one
that could smuggle in a scientific decision: choosing between disagreeing sources,
inventing a value or a mapping, and dropping a concept the schema has no home for.
"""

from __future__ import annotations

import hashlib

from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import reconstruct as rc
from isaac_api.bl15 import relate as R
from isaac_api.bl15.inventory import SourceRecord

SPEC = ev.SOURCE_TYPE_SPEC_ACQUISITION
SCAN = ev.SOURCE_TYPE_SCAN_EXPORT


def rec(path: str, *, content: str | None = None) -> SourceRecord:
    basename = path.rsplit("/", 1)[-1]
    body = (content if content is not None else path).encode("utf-8")
    return SourceRecord(
        archive_path=path,
        basename=basename,
        extension=basename.rsplit(".", 1)[1].lower() if "." in basename else "",
        size_bytes=len(body),
        content_sha256=hashlib.sha256(body).hexdigest(),
        parent_dir=path.rsplit("/", 1)[0] if "/" in path else "",
        depth=path.count("/"),
    )


def item(
    path: str,
    concept: str,
    literal: str,
    *,
    normalized=None,
    unit: str | None = None,
    rule: str | None = None,
    scope: str = ev.SCOPE_MEASUREMENT,
    locator: str = "filename token 4",
) -> ev.SourceEvidence:
    return ev.SourceEvidence(
        evidence_id=f"{path}:{concept}:{literal}",
        source_path=path,
        source_type=SPEC,
        locator=locator,
        raw_literal=literal,
        concept=concept,
        parser_id="test",
        determinism=(
            ev.DETERMINISM_NORMALIZED if normalized is not None else ev.DETERMINISM_READ
        ),
        normalized_value=normalized,
        unit=unit,
        normalization_rule=rule,
        scope=scope,
    )


STEM = "15_02_ZZ1_base_filter10_850mV"


def one_unit(scans: int = 2):
    body = f"#F {STEM}\n"
    entries = [rec(STEM, content=body), rec(f"{STEM}_dir/{STEM}", content=body)]
    classifications = {STEM: SPEC, f"{STEM}_dir/{STEM}": SPEC}
    for i in range(1, scans + 1):
        path = f"{STEM}_dir/{STEM}_{i:03d}.dat"
        entries.append(rec(path))
        classifications[path] = SCAN
    return R.relate(entries=entries, classifications=classifications)


# --- the structural candidate ------------------------------------------------


def test_the_measurement_itself_is_a_candidate_that_can_never_be_sent():
    """Shown so a scientist sees what the import found; not a value, so not a proposal.

    The existing pipeline already refuses an experiment-creation candidate for this
    reason; a run is the same shape of non-value.
    """
    report = rc.reconstruct(relationships=one_unit(), evidence_by_source={})
    unit = report.units[0]
    assert len(unit.candidates) == 1
    candidate = unit.candidates[0]
    assert candidate.kind == "run"
    assert candidate.proposable is False
    assert candidate.not_proposable_reason == rc.RUN_CANDIDATE_NOT_PROPOSABLE
    assert candidate.proposed_value is None
    # the rule states the measured facts, not a slogan
    assert "2 scan file(s)" in candidate.rule


# --- the evidence bridge -----------------------------------------------------


def test_the_statement_carries_the_RAW_literal_and_never_the_normalized_value():
    """THE MOST IMPORTANT ASSERTION IN THIS FILE.

    Handing the normalised value into the review pipeline would put "filter 35" where
    the file says `ffilter35`, and the normalisation would be invisible at exactly the
    moment a scientist reviews it.
    """
    statement = rc.statement_for(
        item(
            STEM,
            ev.CONCEPT_FILTER,
            "ffilter35",
            normalized=35,
            rule="doubled_prefix_typo",
        )
    )
    assert statement.value == "ffilter35"
    assert statement.key == ev.CONCEPT_FILTER
    # the archive path is in the locator, because a bare "#F" means nothing on screen
    assert statement.locator.startswith(f"{STEM} · ")


def test_the_normalized_value_and_its_rule_travel_on_the_candidate():
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={
            STEM: [
                item(
                    STEM,
                    ev.CONCEPT_POTENTIAL_MAGNITUDE,
                    "850mV",
                    normalized=0.85,
                    unit="V",
                    rule="millivolts_to_volts",
                )
            ]
        },
    )
    candidate = next(
        c
        for c in report.units[0].candidates
        if c.candidate_id.endswith(ev.CONCEPT_POTENTIAL_MAGNITUDE)
    )
    assert candidate.proposable is True
    assert candidate.proposed_value == 0.85
    assert "millivolts_to_volts" in candidate.rule
    assert "original text is kept beside the value" in candidate.rule
    # and the statement still holds the literal
    assert candidate.supporting_statements[0]["value"] == "850mV"


# --- the mapping is never decided here ---------------------------------------


def test_every_field_path_comes_from_the_registry_and_never_from_a_literal():
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={
            STEM: [
                item(
                    STEM,
                    ev.CONCEPT_POTENTIAL_MAGNITUDE,
                    "850mV",
                    normalized=0.85,
                    unit="V",
                    rule="mv_to_v",
                )
            ]
        },
    )
    candidate = next(
        c for c in report.units[0].candidates if c.target_field_path is not None
    )
    expected = mp.mapping_for(ev.CONCEPT_POTENTIAL_MAGNITUDE)
    assert expected is not None
    assert candidate.target_field_path == expected.official_path
    # no path literal anywhere in the module
    source = (
        __import__("pathlib").Path(rc.__file__).read_text(encoding="utf-8")
    )
    assert "context.electrochemistry" not in source
    assert "timestamps.acquired" not in source


def test_a_concept_the_schema_has_no_home_for_is_KEPT_with_the_registrys_own_reason():
    """39 of 45 concepts land here. Dropping them would discard most of the corpus."""
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={
            STEM: [item(STEM, ev.CONCEPT_CYCLING_STATE, "after1500Cycling")]
        },
    )
    candidate = next(
        c
        for c in report.units[0].candidates
        if c.candidate_id.endswith(ev.CONCEPT_CYCLING_STATE)
    )
    assert candidate.proposable is False
    assert candidate.target_field_path is None
    assert candidate.not_proposable_reason == mp.CYCLING_STATE_NO_FIELD_REASON
    # the evidence survives in full
    assert candidate.supporting_statements[0]["value"] == "after1500Cycling"


def test_a_concept_the_registry_has_not_examined_is_reported_and_still_kept():
    """`None` from the registry means nobody looked, which is a finding, not a drop."""
    # every concept IS registered today, so this is proven by monkeypatching the lookup
    # rather than by inventing a concept the vocabulary would refuse.
    real = mp.mapping_for
    try:
        mp.mapping_for = lambda concept: (  # type: ignore[assignment]
            None if concept == ev.CONCEPT_FILTER else real(concept)
        )
        rc.mp.mapping_for = mp.mapping_for  # type: ignore[attr-defined]
        report = rc.reconstruct(
            relationships=one_unit(),
            evidence_by_source={STEM: [item(STEM, ev.CONCEPT_FILTER, "filter10")]},
        )
    finally:
        mp.mapping_for = real  # type: ignore[assignment]
        rc.mp.mapping_for = real  # type: ignore[attr-defined]

    assert report.unregistered_concepts == (ev.CONCEPT_FILTER,)
    candidate = next(
        c for c in report.units[0].candidates if c.candidate_id.endswith("filter")
    )
    assert candidate.proposable is False
    assert "no entry in the mapping registry" in (candidate.not_proposable_reason or "")
    assert candidate.supporting_statements[0]["value"] == "filter10"


# --- disagreement is never resolved ------------------------------------------


def test_two_sources_disagreeing_about_a_value_yield_a_candidate_with_NO_value():
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={
            STEM: [
                item(STEM, ev.CONCEPT_FILTER, "filter10"),
                item(f"{STEM}_dir/{STEM}_001.dat", ev.CONCEPT_FILTER, "filter20"),
            ]
        },
    )
    # both readings are attached to the acquisition's own evidence list here
    candidate = next(
        c for c in report.units[0].candidates if c.candidate_id.endswith("filter")
    )
    assert candidate.proposed_value is None
    assert candidate.unresolved_reason == R.UNRESOLVED_SOURCES_DISAGREE
    assert candidate.proposable is False
    values = sorted(d["value"] for d in candidate.disagreement)
    assert values == ["filter10", "filter20"]
    assert "do not agree" in candidate.rule


def test_two_unit_conventions_for_ONE_value_are_NOT_a_disagreement():
    """Comparing literals alone would manufacture conflicts out of the corpus's own
    two potential spellings. Comparison is on the normalised reading."""
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={
            STEM: [
                item(
                    STEM,
                    ev.CONCEPT_POTENTIAL_MAGNITUDE,
                    "1200mV",
                    normalized=1.2,
                    unit="V",
                    rule="mv_to_v",
                ),
                item(
                    STEM,
                    ev.CONCEPT_POTENTIAL_MAGNITUDE,
                    "1p2V",
                    normalized=1.2,
                    unit="V",
                    rule="p_as_decimal_point",
                ),
            ]
        },
    )
    candidate = next(
        c
        for c in report.units[0].candidates
        if c.candidate_id.endswith(ev.CONCEPT_POTENTIAL_MAGNITUDE)
    )
    assert candidate.unresolved_reason is None
    assert candidate.proposed_value == 1.2
    assert candidate.proposable is True
    # BOTH literals are still attached, so the scientist sees both spellings
    assert sorted(s["value"] for s in candidate.supporting_statements) == [
        "1200mV",
        "1p2V",
    ]


def test_a_structural_conflict_becomes_a_candidate_carrying_every_reading():
    relationships = R.relate(
        entries=[rec(STEM, content=f"#F {STEM}\n")],
        classifications={STEM: SPEC},
        internal_declarations={STEM: "15_02_ZZ1_base_filter10_060mV"},
    )
    report = rc.reconstruct(relationships=relationships, evidence_by_source={})
    conflict = next(
        c for c in report.units[0].candidates if "::conflict::" in c.candidate_id
    )
    assert conflict.proposed_value is None
    assert conflict.unresolved_reason == R.UNRESOLVED_SOURCES_DISAGREE
    assert conflict.not_proposable_reason == rc.DISAGREEMENT_NOT_PROPOSABLE
    assert len(conflict.disagreement) == 2
    # the scientist-readable explanation is carried through, not paraphrased
    assert "Neither is preferred automatically" in conflict.rule


# --- shared context, scope, and doubling -------------------------------------


def test_beamtime_scope_readings_are_shared_and_not_copied_onto_each_measurement():
    """A README value rendered 94 times as though entered 94 times is a lie about
    where it came from."""
    relationships = R.relate(
        entries=[rec(STEM, content=f"#F {STEM}\n"), rec("readme.txt")],
        classifications={STEM: SPEC, "readme.txt": ev.SOURCE_TYPE_SHARED_README},
    )
    report = rc.reconstruct(
        relationships=relationships,
        evidence_by_source={
            "readme.txt": [
                item(
                    "readme.txt",
                    ev.CONCEPT_ELEMENT,
                    "Zz",
                    scope=ev.SCOPE_BEAMTIME,
                    locator="line 3",
                )
            ]
        },
    )
    assert len(report.shared) == 1
    assert report.shared[0].candidate_id.startswith("shared::")
    # and it is NOT on the measurement
    assert all(
        ev.CONCEPT_ELEMENT not in c.candidate_id for c in report.units[0].candidates
    )


def test_a_measurement_scope_reading_inside_a_shared_file_does_NOT_become_shared():
    """Selection is by the READING's scope, not by which file it came from.

    A beamtime notes document states things at three scopes at once, so treating a whole
    file as beamtime-scope would attach a sample-specific remark to all 94 measurements.
    """
    relationships = R.relate(
        entries=[rec("notes.txt")],
        classifications={"notes.txt": ev.SOURCE_TYPE_BEAMTIME_NOTES},
    )
    report = rc.reconstruct(
        relationships=relationships,
        evidence_by_source={
            "notes.txt": [
                item(
                    "notes.txt",
                    ev.CONCEPT_BEAMTIME_DATES,
                    "April 2099",
                    scope=ev.SCOPE_BEAMTIME,
                    locator="line 1",
                ),
                item(
                    "notes.txt",
                    ev.CONCEPT_QUALITY_NOTE,
                    "this one was noisy",
                    scope=ev.SCOPE_MEASUREMENT,
                    locator="line 40",
                ),
            ]
        },
    )
    assert [c.candidate_id for c in report.shared] == [
        f"shared::{ev.CONCEPT_BEAMTIME_DATES}"
    ]


def test_a_byte_identical_copy_does_not_double_a_measurements_statements():
    """The statement-level form of the unit-level doubling that made 94 into 181."""
    body = f"#F {STEM}\n"
    copy_path = f"{STEM}_dir/{STEM}"
    relationships = R.relate(
        entries=[rec(STEM, content=body), rec(copy_path, content=body)],
        classifications={STEM: SPEC, copy_path: SPEC},
    )
    report = rc.reconstruct(
        relationships=relationships,
        evidence_by_source={
            STEM: [item(STEM, ev.CONCEPT_FILTER, "filter10")],
            copy_path: [item(copy_path, ev.CONCEPT_FILTER, "filter10")],
        },
    )
    candidate = next(
        c for c in report.units[0].candidates if c.candidate_id.endswith("filter")
    )
    # ONE statement, from the canonical path only
    assert len(candidate.supporting_statements) == 1
    assert candidate.supporting_statements[0]["locator"].startswith(f"{STEM} · ")


def test_many_witnesses_of_one_fact_are_one_candidate_with_many_statements():
    """16 scan files recording one filter index is one fact with 16 witnesses."""
    relationships = one_unit(scans=16)
    by_source = {
        f"{STEM}_dir/{STEM}_{i:03d}.dat": [
            item(f"{STEM}_dir/{STEM}_{i:03d}.dat", ev.CONCEPT_FILTER, "filter10")
        ]
        for i in range(1, 17)
    }
    report = rc.reconstruct(relationships=relationships, evidence_by_source=by_source)
    filters = [
        c for c in report.units[0].candidates if c.candidate_id.endswith("filter")
    ]
    assert len(filters) == 1
    assert len(filters[0].supporting_statements) == 16
    assert "16 sources" in filters[0].rule


# --- the report --------------------------------------------------------------


def test_the_report_breaks_down_by_status_and_offers_no_completion_ratio():
    """39 of 45 concepts have no proposable mapping, so a percentage would report the
    schema's coverage as this feature's failure."""
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={
            STEM: [
                item(
                    STEM,
                    ev.CONCEPT_POTENTIAL_MAGNITUDE,
                    "850mV",
                    normalized=0.85,
                    unit="V",
                    rule="mv_to_v",
                ),
                item(STEM, ev.CONCEPT_CYCLING_STATE, "after1500Cycling"),
                item(STEM, ev.CONCEPT_FILTER, "filter10"),
            ]
        },
    )
    state = report.to_state()
    assert state["by_mapping_status"][mp.STATUS_NORMALIZED] == 1
    assert state["by_mapping_status"][mp.STATUS_NOT_EXPRESSIBLE] == 2

    # NO COMPLETION FIGURE ANYWHERE IN THE REPORT — asserted over the KEY SET, not by
    # searching the serialized payload. The first version of this test did the latter
    # (`"ratio" not in str(state)`) and FAILED, matching the substring inside the word
    # "configuration" in a registry reason. That is the trap this repository already
    # records for a different payload: enumerate the block's keys; never grep the
    # serialization, because a designed value and its own violation have the same
    # signature under a flat-text search.
    assert set(state) == {
        "units",
        "shared",
        "by_concept",
        "by_mapping_status",
        "unregistered_concepts",
        "candidate_count",
        "proposable_count",
    }
    for forbidden in ("percent", "ratio", "complete", "progress", "score"):
        assert not any(forbidden in key for key in state), forbidden

    assert set(state["by_concept"]) == {
        ev.CONCEPT_POTENTIAL_MAGNITUDE,
        ev.CONCEPT_CYCLING_STATE,
        ev.CONCEPT_FILTER,
    }
    # counts add up: 1 structural + 3 concepts
    assert state["candidate_count"] == 4
    assert state["proposable_count"] == 1


def test_nothing_this_module_produces_is_ever_marked_inferred():
    """`inferred` is for a value NO source states, and nothing here produces one.

    A normalised reading is still deterministic: a stored, named rule was applied to what
    a source literally says.
    """
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={
            STEM: [
                item(
                    STEM,
                    ev.CONCEPT_PH,
                    "13",
                    normalized=13.0,
                    rule="ph_read_verbatim",
                ),
                item(STEM, ev.CONCEPT_FILTER, "filter10"),
            ]
        },
    )
    everything = list(report.units[0].candidates) + list(report.shared)
    assert everything
    assert all(c.determinism == "deterministic" for c in everything)


def test_every_candidate_names_a_source_a_scientist_can_find():
    report = rc.reconstruct(
        relationships=one_unit(),
        evidence_by_source={STEM: [item(STEM, ev.CONCEPT_FILTER, "filter10")]},
    )
    for candidate in report.units[0].candidates:
        assert candidate.supporting_source_ids
        assert all(candidate.supporting_source_ids)


def test_session_source_ids_replace_paths_when_supplied_and_paths_are_the_fallback():
    """Provenance never depends on the id map being supplied."""
    relationships = one_unit()
    with_ids = rc.reconstruct(
        relationships=relationships,
        evidence_by_source={STEM: [item(STEM, ev.CONCEPT_FILTER, "filter10")]},
        source_ids={STEM: "src-1"},
    )
    without = rc.reconstruct(
        relationships=relationships,
        evidence_by_source={STEM: [item(STEM, ev.CONCEPT_FILTER, "filter10")]},
    )
    assert with_ids.units[0].candidates[0].supporting_source_ids == ("src-1",)
    assert without.units[0].candidates[0].supporting_source_ids == (STEM,)
    # the locator carries the archive path either way
    assert all(
        STEM in s["locator"]
        for c in with_ids.units[0].candidates
        for s in c.supporting_statements
    )
