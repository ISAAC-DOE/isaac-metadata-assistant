"""The no-guessing contract for SUGGESTED / INFERRED / AUTO-COMPLETED values.

Every test here exists because a specific way of manufacturing a value out of
nothing is available to this codebase and must stay refused. The eighteen cases
the slice enumerates are grouped below and each is named after the defect it
prevents, not after the function it calls.

Fixtures are synthetic and obviously so: an `Xx` placeholder element, a year-2099
timestamp, and the committed `tests/fixtures/synthetic/` sheet. No production or
production-derived content is read.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from isaac_api import inferability as inf
from isaac_api import serialize
from isaac_api import workspace as ws

from conftest import tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """A worked-example session over an isolated tmp workspace (the package pattern)."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def raw_seed_id(client) -> str:
    """The canonical New Draft seed — the one with every blocker still open."""
    experiments = client.get("/api/experiments").json()["experiments"]
    raw = [e for e in experiments if e["pending_count"] == 5]
    assert len(raw) == 1
    return raw[0]["id"]

# --- synthetic drafts ---------------------------------------------------------


def _draft(formula=None, *, source_type="facility", implicit=None, pending=None):
    """A minimal draft carrying only what the rules under test read."""
    fields = {}
    if formula is not None:
        fields["sample.material.formula"] = {
            "value": formula,
            "status": "verified",
            "evidence": [
                {
                    "source_type": "spreadsheet",
                    "source_file": "synthetic_campaign.csv",
                    "locator": "Sheet 'Sample', field=formula",
                }
            ],
        }
    draft = {"meta": {"source_type": source_type}, "fields": fields}
    if implicit is not None:
        draft["implicit"] = implicit
    if pending is not None:
        draft["pending"] = pending
    return draft


ASSET_BLOCKER = {
    "kind": "asset",
    "uri": "synthetic://never-real/raw/",
    "blocker": "sha256",
    "question": "What is the sha256 of synthetic://never-real/raw/?",
}
SERIES_BLOCKER = {"kind": "series", "blocker": "reduced_spectrum", "question": "Provide the spectrum."}
QC_BLOCKER = {"kind": "qc", "blocker": "qc_status", "question": "What is the QC verdict?"}
DESCRIPTOR_BLOCKER = {
    "kind": "descriptor",
    "blocker": "required_for_evidence_record",
    "question": "Provide at least one descriptor.",
}


# =============================================================================
# 1-6. the five states, reached by the rules that already existed
# =============================================================================


def test_1_unique_inference_is_suggested_with_a_concrete_value():
    """A rule that fires uniquely on this record's own field MAY suggest."""
    result = inf.absorbing_element(_draft("CuO2"))
    assert result.state == inf.SUPPORTED_SUGGESTION
    assert result.value == "Cu"


def test_2_provenance_identifies_the_supporting_fields_and_the_applied_rule():
    """The justification is machine-checkable, not a prose gesture."""
    p = inf.absorbing_element(_draft("CuO2")).provenance
    assert p is not None
    assert p.supporting_fields == ("sample.material.formula",)
    assert "sole non-oxygen element" in p.rule
    assert "CuO2 -> Cu" in p.rule  # the rule states its own application
    assert p.unique is True
    assert p.alternatives_excluded  # why not something else, stated
    assert p.requires_user_confirmation is True
    # The cited evidence is this record's own spreadsheet row.
    assert p.supporting_evidence[0]["source_type"] == "spreadsheet"


def test_3_missing_information_is_needs_user_input_not_a_value():
    """No formula on the record => a question, never a filled-in element."""
    result = inf.absorbing_element(_draft(formula=None))
    assert result.state == inf.NEEDS_USER_INPUT
    assert result.value is None
    assert result.detail["missing"] == ("sample.material.formula",)
    assert result.to_dict()["detail"]["missing"] == ["sample.material.formula"]


def test_4_two_plausible_values_is_ambiguous_and_neither_is_offered():
    """Two non-oxygen elements: counted, never chosen between."""
    result = inf.absorbing_element(_draft("CuFeO2"))
    assert result.state == inf.AMBIGUOUS
    assert result.value is None
    assert result.detail["candidate_count"] == 2
    # The candidate VALUES must not appear anywhere in the payload — offering
    # them beside a "pick one" control is how ambiguity becomes a guess.
    blob = json.dumps(result.to_dict())
    assert "Cu" not in blob and "Fe" not in blob


def test_5_contradictory_evidence_when_the_record_disagrees_with_itself():
    """A stored absorber the formula rule contradicts is escalated, not overwritten."""
    draft = _draft("CuO2", implicit=[{"about": "absorbing_element", "value": "Fe"}])
    result = inf.absorbing_element(draft)
    assert result.state == inf.CONTRADICTORY_EVIDENCE
    assert result.value is None
    assert set(result.detail["conflicting_sources"]) == {
        "implicit:absorbing_element",
        "sample.material.formula",
    }


def test_6_unsupported_field_is_not_inferable():
    """A formula with no readable element symbol reaches no answer at all."""
    result = inf.absorbing_element(_draft("???"))
    assert result.state == inf.NOT_INFERABLE
    assert result.value is None
    assert result.detail["reason"] == "formula_unparseable"


# =============================================================================
# 7. the statistically common value is never inserted
# =============================================================================


def test_7_the_common_default_is_never_inserted_for_qc():
    """'valid' is the overwhelmingly common QC verdict. It is still never assumed.

    Two independent refusals are checked, because the value could be manufactured
    at either end: the blocker's inferability state, and the truth core's
    ``apply_answers``, which leaves an unanswered qc blocker pending rather than
    defaulting it.
    """
    from isaac_records.complete import apply_answers

    decision = inf.blocker_inferability(QC_BLOCKER)
    assert decision.state == inf.NOT_INFERABLE
    assert decision.value is None
    assert "not even 'valid'" in decision.explanation

    draft = {"pending": [dict(QC_BLOCKER)]}
    out = apply_answers(draft, {"timestamp": "2099-01-01T00:00:00Z"})
    assert out.get("qc") in (None, {})
    assert [e["kind"] for e in out["pending"]] == ["qc"]


def test_7b_commonly_used_is_refused_as_evidence():
    """Naming the mechanism explicitly: a population fact is not a record fact."""
    for source_type in ("commonly_used", "statistical_prior", "population_default"):
        with pytest.raises(inf.UnsupportedSuggestion, match="not record-specific evidence"):
            inf.supported(
                "measurement.qc.status",
                "valid",
                supporting_fields=("measurement.qc.status",),
                supporting_evidence=({"source_type": source_type},),
                rule="most records use 'valid'",
                explanation="x",
            )


# =============================================================================
# 8-10. constraints: explained, never filled in
# =============================================================================


def test_8_required_field_removal_produces_an_issue_but_no_replacement():
    """Deleting a required field yields a located error and no invented value."""
    from isaac_records.official import validate_official

    sample = ws.REPO_ROOT / "docs/samples/01JQZ0SYNTHXANESDEMO000000.json"
    record = json.loads(sample.read_text(encoding="utf-8"))

    removed = copy.deepcopy(record)
    removed.pop("record_id", None)
    report = validate_official(removed, ws.REPO_ROOT)
    assert not report.ok
    messages = " ".join(e.message for e in report.errors)
    assert "record_id" in messages
    # The error states WHAT is missing. It must not state what the value was.
    original_id = record.get("record_id")
    assert original_id
    assert original_id not in messages


def test_9_a_concrete_repair_is_offered_only_when_uniquely_determined():
    """The same rule that suggests for CuO2 refuses for CuFeO2 — uniqueness is the gate."""
    assert inf.absorbing_element(_draft("CuO2")).value == "Cu"
    assert inf.absorbing_element(_draft("CuFeO2")).value is None
    assert inf.absorbing_element(_draft("O2")).value is None


def test_10_constraint_only_is_explained_without_inventing_the_replacement():
    """Knowing the shape of a valid answer is not knowing this record's answer."""
    constraint = "'telepathy' is not one of ['XAS', 'XRD', 'HERFD-XAS']"
    result = inf.constraint_only("system.technique", constraint)
    assert result.state == inf.NOT_INFERABLE
    assert result.value is None
    assert result.detail["constraint"] == constraint
    assert "not inferable" in result.explanation
    # The enum members appear ONLY inside the quoted constraint, never as a value.
    assert result.to_dict()["value"] is None


def test_10b_the_edge_is_the_canonical_constraint_only_field():
    """The energy window narrows the edge without determining it. Still a question."""
    result = inf.absorption_edge(_draft("CuO2"))
    assert result.state == inf.NEEDS_USER_INPUT
    assert result.value is None
    assert "must come from you" in result.explanation


# =============================================================================
# 11-13. acceptance: never silent, never resurrected, always precondition-gated
# =============================================================================


def test_11_a_suggestion_is_never_silently_persisted(client, raw_seed_id):
    """Reading the pending queue mutates nothing — same rev before and after."""
    before = client.get(f"/api/experiments/{raw_seed_id}")
    rev_before = before.json()["rev"]

    listing = client.get(f"/api/experiments/{raw_seed_id}/pending")
    assert listing.status_code == 200
    assert listing.json()["pending"]  # decisions were computed and served

    after = client.get(f"/api/experiments/{raw_seed_id}")
    assert after.json()["rev"] == rev_before


def test_12_a_rejected_suggestion_does_not_reappear_as_an_accepted_value():
    """Declining a blocker leaves it pending; nothing is written in its place.

    ``apply_answers`` is the only writer. An answers payload that omits the
    blocker (the shape the UI sends for "I don't know") must leave the draft's
    value slots exactly as they were.
    """
    from isaac_records.complete import apply_answers

    draft = {"pending": [dict(DESCRIPTOR_BLOCKER), dict(SERIES_BLOCKER)]}
    once = apply_answers(draft, {"timestamp": "2099-01-01T00:00:00Z"})
    assert "descriptors_outputs" not in once
    assert "series" not in once
    # Re-offering and declining again is still a no-op — a declined value has no
    # memory that could promote it on a second pass.
    twice = apply_answers(once, {"timestamp": "2099-01-01T00:00:01Z"})
    assert "descriptors_outputs" not in twice
    assert "series" not in twice
    assert {e["kind"] for e in twice["pending"]} == {"descriptor", "series"}


def test_13_acceptance_requires_the_version_precondition(client, raw_seed_id):
    """Accepting a suggested answer follows the existing If-Match contract.

    Three refusals, all before any mutation: no ``If-Match`` is 428, a stale one
    is 412, and ``confirmed_by_user`` short of ``true`` is 422.
    """
    from isaac_api import version_contract as vc

    assert vc.precondition_required() is True

    detail = client.get(f"/api/experiments/{raw_seed_id}")
    etag = detail.headers["ETag"]
    body = {"confirmed_by_user": True, "answers": {"qc": {"status": "valid"}}}

    no_precondition = client.post(
        f"/api/experiments/{raw_seed_id}/answers", json=body
    )
    assert no_precondition.status_code == 428

    stale = client.post(
        f"/api/experiments/{raw_seed_id}/answers",
        json=body,
        headers={"If-Match": '"0.0-definitely-stale"'},
    )
    assert stale.status_code == 412

    unconfirmed = client.post(
        f"/api/experiments/{raw_seed_id}/answers",
        json={"confirmed_by_user": False, "answers": {"qc": {"status": "valid"}}},
        headers={"If-Match": etag},
    )
    assert unconfirmed.status_code == 422


# =============================================================================
# 14-15. borrowed values are not evidence
# =============================================================================


def test_14_a_value_from_another_record_is_not_evidence_for_this_one():
    with pytest.raises(inf.UnsupportedSuggestion, match="not record-specific evidence"):
        inf.supported(
            "sample.material.formula",
            "CuO2",
            supporting_fields=("sample.material.formula",),
            supporting_evidence=({"source_type": "other_record", "record_id": "01ABC"},),
            rule="the neighbouring record in the same campaign used this formula",
            explanation="x",
        )


def test_15_tutorial_content_is_not_evidence_and_is_withheld_from_ordinary_records():
    """Two halves of the same rule, because the codebase had both defects.

    (a) ``tutorial_example`` is refused as evidence outright.
    (b) The committed walkthrough answers are withheld from any record outside
        example scope — the leak this slice fixed.
    """
    with pytest.raises(inf.UnsupportedSuggestion, match="not record-specific evidence"):
        inf.supported(
            "descriptors",
            {"value": 9001.2},
            supporting_fields=("descriptors",),
            supporting_evidence=({"source_type": "tutorial_example"},),
            rule="the walkthrough uses this descriptor",
            explanation="x",
        )

    demo = ws.load_demo_answers()
    draft = {"pending": [dict(ASSET_BLOCKER), dict(SERIES_BLOCKER), dict(DESCRIPTOR_BLOCKER)]}

    ordinary = serialize.pending_to_list(draft, demo, example_scope=False)
    assert all(item["demo_answer"] is None for item in ordinary["pending"])
    # The fabricated descriptor value must not appear anywhere in the payload.
    assert "9001.2" not in json.dumps(ordinary)

    example = serialize.pending_to_list(draft, demo, example_scope=True)
    kinds_with_example = {
        item["kind"] for item in example["pending"] if item["demo_answer"] is not None
    }
    assert kinds_with_example == {"series", "descriptor"}  # asset uri is synthetic
    for item in example["pending"]:
        if item["demo_answer"] is None:
            continue
        prov = item["demo_answer"]["provenance"]
        assert prov["is_evidence_for_this_record"] is False
        assert prov["auto_applied"] is False
        assert prov["requires_user_confirmation"] is True
        # And the inferability decision beside it still refuses.
        assert item["inferability"]["state"] != inf.SUPPORTED_SUGGESTION
        assert item["inferability"]["value"] is None
        assert "not evidence about this record" in item["inferability"]["explanation"]


def test_15c_the_route_scopes_the_example_to_the_canonical_records_only():
    """The endpoint description's "for the built-in examples only" is now a fact.

    It was not before: ``_demo_answer_for``'s ``series`` and ``descriptor``
    branches read the fixture unconditionally, so the sentence described a
    boundary the code did not have. ``_example_scope`` is that boundary, and it is
    the SAME ``CANONICAL_IDS`` set reset and removal already enforce — not a second
    definition that could drift from it.
    """
    from isaac_api.routes import _example_scope

    assert ws.CANONICAL_IDS
    for canonical in ws.CANONICAL_IDS:
        assert _example_scope(canonical) is True
    for ordinary in ("01ORDINARYRECORD0000000000", "", "not-an-id"):
        assert _example_scope(ordinary) is False


def test_15d_every_pending_item_pairs_its_example_with_a_refusal(client, raw_seed_id):
    """Over HTTP, on a real canonical record: the two channels never contradict.

    An example answer may be present (this IS a walkthrough record) but the
    inferability decision beside it still refuses, and says in the same breath
    that the example is not evidence.
    """
    body = client.get(f"/api/experiments/{raw_seed_id}/pending").json()
    assert body["pending"]
    for item in body["pending"]:
        decision = item["inferability"]
        assert decision["state"] in (inf.NEEDS_USER_INPUT, inf.NOT_INFERABLE)
        assert decision["value"] is None
        assert decision["provenance"] is None
        if item["demo_answer"] is not None:
            assert "not evidence about this record" in decision["explanation"]
            assert item["demo_answer"]["provenance"]["is_evidence_for_this_record"] is False


def test_15b_the_default_scope_is_closed():
    """Omitting ``example_scope`` withholds the example. Fail closed, not open."""
    draft = {"pending": [dict(SERIES_BLOCKER)]}
    out = serialize.pending_to_list(draft, ws.load_demo_answers())
    assert out["pending"][0]["demo_answer"] is None


#: Strings that exist ONLY inside the committed walkthrough answers
#: (``tests/fixtures/.../demo_answers.json``). None of them is derivable from an
#: ordinary record, so any one of them appearing in an ordinary record's response
#: body IS the leak — whatever route or argument let it through.
_WALKTHROUGH_MARKERS = (
    "9001.2",  # the fabricated descriptor value, with its fabricated uncertainty
    "xanes_inflection_point_energy",  # the fabricated descriptor name
    "averaged_spectrum",  # the fabricated 7-point reduced spectrum
    "Example answer",  # serialize._DEMO_LABEL — the wrapper, not just its content
)


def _assert_no_walkthrough_content(response, where: str) -> dict:
    """Every blocker refuses an example, and no fixture string rode along."""
    assert response.status_code == 200, f"{where}: {response.text}"
    body = response.json()
    assert body["pending"], f"{where}: expected open blockers to assert about"
    for item in body["pending"]:
        assert item["demo_answer"] is None, f"{where}: {item['id']} carried an example"
    for marker in _WALKTHROUGH_MARKERS:
        assert marker not in response.text, f"{where}: leaked {marker!r}"
    return body


def test_15e_an_ordinary_record_is_offered_no_example_by_any_mutating_route(client):
    """END-TO-END. The withholding holds on the ROUTES, not only at the seam.

    ``test_15``/``test_15b`` pin ``serialize.pending_to_list`` and ``test_15c``
    pins the ``_example_scope`` predicate, but both are the pieces in isolation.
    An independent review showed the wiring between them was unpinned: replacing
    ``example_scope=_example_scope(experiment_id)`` with ``example_scope=True`` at
    all three call sites in ``routes.py`` — restoring the exact defect this slice
    fixed, a fabricated ``9001.2 eV`` descriptor and a fabricated 7-point spectrum
    offered as the answer to an unrelated record's scientific question — produced
    ZERO behavioural failures. This test is that missing behavioural pin, and it
    covers ALL THREE call sites: ``GET /pending``, ``POST /answers`` and
    ``POST /edit`` each rebuild the list and each must withhold.

    The record is deliberately NOT canonical (random id, so outside
    ``ws.CANONICAL_IDS``) while carrying the SAME draft — and therefore the same
    asset URIs — as the walkthrough seed. That matters: the asset branch of
    ``_demo_answer_for`` keys on the URI, so a record with foreign URIs would miss
    the fixture by accident and prove nothing about scope. Here the fixture WOULD
    match; only scope withholds it.
    """
    from conftest import client_ws

    store = client_ws(client)
    ordinary = store.create_experiment(
        title="Synthetic record outside the walkthrough (Xx placeholder campaign)",
        source={"description": "hand-authored / unknown provenance", "files": []},
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )
    assert ordinary.id not in ws.CANONICAL_IDS

    # 1. GET /pending
    body = _assert_no_walkthrough_content(
        client.get(f"/api/experiments/{ordinary.id}/pending"), "GET /pending"
    )
    asset_ids = [item["id"] for item in body["pending"] if item["kind"] == "asset"]
    assert asset_ids  # the answer/edit legs below need one

    # 2. POST /answers — a sha the USER supplies, never one the app produced.
    pasted = "d" * 64
    etag = client.get(f"/api/experiments/{ordinary.id}").headers["ETag"]
    _assert_no_walkthrough_content(
        client.post(
            f"/api/experiments/{ordinary.id}/answers",
            json={"confirmed_by_user": True, "answers": {asset_ids[0]: pasted}},
            headers={"If-Match": etag},
        ),
        "POST /answers",
    )

    # 3. POST /edit — correct the field just answered; same rebuilt list.
    etag = client.get(f"/api/experiments/{ordinary.id}").headers["ETag"]
    _assert_no_walkthrough_content(
        client.post(
            f"/api/experiments/{ordinary.id}/edit",
            json={"confirmed_by_user": True, "answers": {asset_ids[0]: "e" * 64}},
            headers={"If-Match": etag},
        ),
        "POST /edit",
    )


# =============================================================================
# 16-17. confidence is not evidence, in either direction
# =============================================================================


def test_16_low_confidence_is_not_converted_into_an_answer():
    with pytest.raises(inf.UnsupportedSuggestion, match="claim about a predictor"):
        inf.supported(
            "sample.material.formula",
            "CuO2",
            supporting_fields=("sample.material.formula",),
            supporting_evidence=({"source_type": "spreadsheet", "confidence": 0.11},),
            rule="best guess",
            explanation="x",
        )


def test_17_high_confidence_cannot_override_missing_evidence():
    """The symmetry is the point: 0.999 buys exactly what 0.11 bought."""
    with pytest.raises(inf.UnsupportedSuggestion, match="claim about a predictor"):
        inf.supported(
            "sample.material.formula",
            "CuO2",
            supporting_fields=("sample.material.formula",),
            supporting_evidence=({"source_type": "spreadsheet", "confidence": 0.999},),
            rule="very confident",
            explanation="x",
        )
    # Confidence with NO record evidence at all is refused for the prior reason:
    # there is nothing that speaks about this record.
    for source_type in ("model_confidence", "heuristic_confidence"):
        with pytest.raises(inf.UnsupportedSuggestion, match="not record-specific evidence"):
            inf.supported(
                "sample.material.formula",
                "CuO2",
                supporting_fields=("sample.material.formula",),
                supporting_evidence=({"source_type": source_type},),
                rule="the model is sure",
                explanation="x",
            )


# =============================================================================
# 18. private values never enter outputs
# =============================================================================


def test_18_no_private_value_enters_a_suggestion_payload(client, raw_seed_id):
    """Nothing served here carries a filesystem path, a home dir, or a bearer token."""
    body = client.get(f"/api/experiments/{raw_seed_id}/pending").json()
    blob = json.dumps(body)
    for forbidden in ("/Users/", "\\Users\\", "Bearer ", "/private/tmp", "/home/"):
        assert forbidden not in blob


# =============================================================================
# structural invariants — the guards themselves
# =============================================================================


def test_only_a_supported_suggestion_may_carry_a_value():
    for state in (inf.NEEDS_USER_INPUT, inf.AMBIGUOUS, inf.CONTRADICTORY_EVIDENCE, inf.NOT_INFERABLE):
        with pytest.raises(inf.UnsupportedSuggestion, match="may not carry a concrete value"):
            inf.Inferability(field="f", state=state, explanation="e", value="Cu")


def test_a_concrete_value_without_provenance_is_refused():
    with pytest.raises(inf.UnsupportedSuggestion, match="requires provenance"):
        inf.Inferability(
            field="f", state=inf.SUPPORTED_SUGGESTION, explanation="e", value="Cu"
        )


def test_a_non_unique_inference_cannot_be_supported():
    with pytest.raises(inf.UnsupportedSuggestion, match="ambiguous, not supported"):
        inf.Inferability(
            field="f",
            state=inf.SUPPORTED_SUGGESTION,
            explanation="e",
            value="Cu",
            provenance=inf.SuggestionProvenance(
                supporting_fields=("a",),
                supporting_evidence=({"source_type": "spreadsheet"},),
                rule="r",
                unique=False,
                alternatives_excluded=(),
                requires_user_confirmation=True,
            ),
        )


def test_detail_is_closed_by_an_allowlist_not_a_denylist():
    """REVIEW FINDING 1. The denylist banned four spellings of "value" and let
    everything else through, so the payload below — candidate values plus a
    ranking, on an `ambiguous` result — was accepted."""
    with pytest.raises(inf.UnsupportedSuggestion, match="not an allowed detail key"):
        inf.Inferability(
            field="f",
            state=inf.AMBIGUOUS,
            explanation="e",
            detail={"candidates": ["Cu", "Fe"], "most_likely": "Cu"},
        )
    # The four originally-banned spellings are still refused, now by the same rule.
    for key in ("value", "candidate_value", "suggested_value", "proposed_value"):
        with pytest.raises(inf.UnsupportedSuggestion, match="not an allowed detail key"):
            inf.Inferability(
                field="f", state=inf.AMBIGUOUS, explanation="e", detail={key: "Cu"}
            )
    # A key allowed for ANOTHER state is refused for this one.
    with pytest.raises(inf.UnsupportedSuggestion, match="not an allowed detail key"):
        inf.Inferability(
            field="f", state=inf.AMBIGUOUS, explanation="e", detail={"constraint": "x"}
        )
    # A supported suggestion may carry NO detail at all: its justification lives
    # in `provenance`, and a second, unstructured channel beside it is exactly
    # where an unexplained extra value would go.
    with pytest.raises(inf.UnsupportedSuggestion, match="not an allowed detail key"):
        inf.Inferability(
            field="f",
            state=inf.SUPPORTED_SUGGESTION,
            explanation="e",
            value="Cu",
            provenance=inf.absorbing_element(_draft("CuO2")).provenance,
            detail={"reason": "x"},
        )


def test_detail_types_are_enforced_so_an_allowed_key_cannot_carry_a_value():
    """A count must be a count; a string list must be strings."""
    with pytest.raises(inf.UnsupportedSuggestion, match="must be an integer count"):
        inf.Inferability(
            field="f", state=inf.AMBIGUOUS, explanation="e", detail={"candidate_count": "Cu"}
        )
    with pytest.raises(inf.UnsupportedSuggestion, match="must be a sequence of strings"):
        inf.Inferability(
            field="f",
            state=inf.NEEDS_USER_INPUT,
            explanation="e",
            detail={"missing": [{"value": "Cu"}]},
        )


def test_detail_cannot_be_widened_after_construction():
    """REVIEW FINDING 1. `frozen=True` blocks rebinding the attribute, not writing
    THROUGH it: the reviewer set `x.detail["suggested_value"] = "Cu"` on a
    constructed object and `to_dict()` serialized it. `detail` is now a read-only
    mapping over frozen sequences, so both routes raise."""
    x = inf.ambiguous("f", "several candidates", candidate_count=2)
    with pytest.raises(TypeError):
        x.detail["suggested_value"] = "Cu"  # type: ignore[index]
    with pytest.raises(TypeError):
        del x.detail["candidate_count"]  # type: ignore[attr-defined]
    assert "suggested_value" not in x.to_dict()["detail"]

    # And a nested sequence cannot be appended to either.
    y = inf.needs_user_input("f", "no formula", missing=("sample.material.formula",))
    with pytest.raises(AttributeError):
        y.detail["missing"].append("Cu")  # type: ignore[attr-defined]
    assert y.to_dict()["detail"]["missing"] == ["sample.material.formula"]


def test_every_state_must_explain_itself():
    with pytest.raises(inf.UnsupportedSuggestion, match="must explain itself"):
        inf.Inferability(field="f", state=inf.NOT_INFERABLE, explanation="")


def test_derivation_evidence_must_state_its_rule():
    with pytest.raises(inf.UnsupportedSuggestion, match="must state its rule"):
        inf.supported(
            "system.domain",
            "experimental",
            supporting_fields=("meta.source_type",),
            supporting_evidence=({"source_type": "derivation"},),
            rule="r",
            explanation="e",
        )


def test_an_unknown_evidence_source_type_is_refused_not_ignored():
    with pytest.raises(inf.UnsupportedSuggestion, match="unknown evidence source_type"):
        inf.supported(
            "system.domain",
            "experimental",
            supporting_fields=("meta.source_type",),
            supporting_evidence=({"source_type": "vibes"},),
            rule="r",
            explanation="e",
        )


def test_system_domain_rule_covers_facility_only():
    assert inf.system_domain(_draft("CuO2")).state == inf.SUPPORTED_SUGGESTION
    assert inf.system_domain(_draft("CuO2")).value == "experimental"
    assert inf.system_domain(_draft("CuO2", source_type="simulation")).state == inf.NOT_INFERABLE
    assert inf.system_domain(_draft("CuO2", source_type=None)).state == inf.NEEDS_USER_INPUT


def test_infer_all_is_deterministic_and_covers_every_rule():
    draft = _draft("CuO2")
    first = [i.to_dict() for i in inf.infer_all(draft)]
    second = [i.to_dict() for i in inf.infer_all(draft)]
    assert first == second
    assert [i["field"] for i in first] == [
        "implicit:absorbing_element",
        "system.domain",
        "implicit:edge",
    ]


def test_every_blocker_kind_refuses_and_none_carries_a_value():
    for entry in (ASSET_BLOCKER, SERIES_BLOCKER, QC_BLOCKER, DESCRIPTOR_BLOCKER, {"kind": "novel"}):
        decision = inf.blocker_inferability(entry)
        assert decision.state in (inf.NEEDS_USER_INPUT, inf.NOT_INFERABLE)
        assert decision.value is None
        assert decision.provenance is None


def test_the_rule_wrapper_agrees_with_the_rule_it_wraps():
    """The wrapper must not become a second, drifting implementation."""
    from isaac_records.extract.draft_builder import _absorbing_element

    for formula in ("CuO2", "CuFeO2", "O2", "???", "Fe2O3", ""):
        wrapped = inf.absorbing_element(_draft(formula or None))
        assert wrapped.value == _absorbing_element(formula)


# =============================================================================
# review findings 5 + 6 — the two holes the adversarial review found
# =============================================================================


def test_record_evidence_source_types_is_derived_from_the_truth_plane():
    """REVIEW FINDING 5. This set used to be a hand-copied mirror of
    ``OBSERVED_SOURCE_TYPES`` with nothing keeping the two aligned. Widening the
    truth-plane tuple would have left this behind — and because an unlisted
    source type makes ``_check_evidence`` RAISE, that silent drift armed a 500 on
    a read path. The relationship is pinned here, not the contents, so adding an
    observed type in the truth plane flows through instead of breaking."""
    from isaac_records.draft_validator import OBSERVED_SOURCE_TYPES

    assert inf.RECORD_EVIDENCE_SOURCE_TYPES == frozenset(OBSERVED_SOURCE_TYPES) | {"derivation"}
    # And the two vocabularies must stay disjoint: a type cannot simultaneously be
    # evidence about this record and a reason to refuse.
    assert not (inf.RECORD_EVIDENCE_SOURCE_TYPES & inf.NON_EVIDENCE_SOURCE_TYPES)


def test_infer_all_degrades_instead_of_raising_on_unknown_evidence():
    """REVIEW FINDING 5. An evidence ``source_type`` outside the allowlist used to
    propagate out of ``pending_to_list`` — reached by ``GET /pending``,
    ``POST /answers`` and ``POST /edit`` — turning a READ into a 500. It now
    degrades to the most conservative state, which can only remove a suggestion."""
    draft = _draft("CuO2")
    draft["fields"]["sample.material.formula"]["evidence"] = [{"source_type": "literature"}]

    results = inf.infer_all(draft)
    by_field = {r.field: r for r in results}
    absorber = by_field["implicit:absorbing_element"]
    assert absorber.state == inf.NOT_INFERABLE
    assert absorber.value is None
    assert absorber.detail["reason"] == "rule_refused"
    # The refusal text must not quote the offending source type back at a user.
    assert "literature" not in absorber.explanation
    # Every rule still reports, under its own field name.
    assert [r.field for r in results] == [
        "implicit:absorbing_element",
        "system.domain",
        "implicit:edge",
    ]


def test_infer_all_degrades_on_a_REAL_seed_draft_not_just_a_stub(client, raw_seed_id):
    """The same defect, driven through a real canonical seed draft.

    REPLACES a test that asserted `GET /pending` returned 200 after planting
    unknown evidence. That test was VACUOUS: `pending_to_list` no longer calls
    `infer_all` at all, so the endpoint could not have been affected — an
    independent reviewer replaced `infer_all`'s whole body with an unconditional
    `raise` and it still passed. A test whose passing means nothing is worse than
    no test, so this one calls `infer_all` directly, on the real seed draft the
    app ships, and would fail if the function raised.
    """
    from isaac_api import workspace

    exp = workspace.load_experiment(raw_seed_id, session_id=client.tutorial_session_id)
    draft = copy.deepcopy(exp.draft)
    formula = (draft.get("fields") or {}).get("sample.material.formula")
    assert formula is not None, "the canonical seed must carry a formula to plant on"
    formula["evidence"] = [{"source_type": "literature"}]

    results = inf.infer_all(draft)
    by_field = {r.field: r for r in results}
    absorber = by_field["implicit:absorbing_element"]
    assert absorber.state == inf.NOT_INFERABLE
    assert absorber.detail["reason"] == "rule_refused"
    assert "literature" not in absorber.explanation


def test_the_canonical_seed_still_yields_a_supported_suggestion(client, raw_seed_id):
    """The degrade must not be able to hide a genuinely broken rule.

    `infer_all` swallows `UnsupportedSuggestion` per rule, which is right for
    availability but means a future edit that (say) emptied `supporting_fields`
    would turn every suggestion into a permanent `not_inferable` with every other
    test still green — they assert refusals, and a refusal is what a broken rule
    produces. This asserts the POSITIVE direction end-to-end on the real shipped
    seed: the rule fires, uniquely, WITH provenance, THROUGH `infer_all`.
    """
    from isaac_api import workspace

    exp = workspace.load_experiment(raw_seed_id, session_id=client.tutorial_session_id)
    by_field = {r.field: r for r in inf.infer_all(exp.draft)}

    absorber = by_field["implicit:absorbing_element"]
    assert absorber.state == inf.SUPPORTED_SUGGESTION, (
        "the shipped seed carries a single-absorber formula; a refusal here means "
        "the rule broke and infer_all's degrade swallowed the reason"
    )
    assert absorber.value is not None
    assert absorber.provenance is not None
    assert absorber.provenance.supporting_fields == ("sample.material.formula",)
    assert absorber.provenance.unique is True

    domain = by_field["system.domain"]
    assert domain.state == inf.SUPPORTED_SUGGESTION
    assert domain.value == "experimental"


def test_a_nested_confidence_number_is_refused():
    """REVIEW FINDING 6. The guard scanned ``set(entry)`` — the top level only —
    while this repository's own corpus writes the key one level down:
    ``operando_xanes_co2rr_record.json`` carries
    ``"uncertainty": {"confidence": 0.86}``. So the exact shape the guard was
    named for was the shape it passed."""
    nested = {
        "source_type": "spreadsheet",
        "locator": "Sheet 'Sample'",
        "uncertainty": {"confidence": 0.86},  # the corpus's own shape
    }
    with pytest.raises(inf.UnsupportedSuggestion, match="claim about a predictor"):
        inf.supported(
            "sample.material.formula",
            "CuO2",
            supporting_fields=("sample.material.formula",),
            supporting_evidence=(nested,),
            rule="r",
            explanation="e",
        )


def test_confidence_is_refused_at_any_depth_and_inside_a_list():
    for entry in (
        {"source_type": "spreadsheet", "meta": {"model": {"probability": 0.4}}},
        {"source_type": "spreadsheet", "runs": [{"score": 12}]},
        {"source_type": "spreadsheet", "a": {"b": {"c": {"confidence": 1.0}}}},
    ):
        with pytest.raises(inf.UnsupportedSuggestion, match="claim about a predictor"):
            inf.supported(
                "sample.material.formula",
                "CuO2",
                supporting_fields=("sample.material.formula",),
                supporting_evidence=(entry,),
                rule="r",
                explanation="e",
            )
    # A deeply nested entry with NO confidence key still passes — the scan must
    # refuse the key, not merely refuse nesting.
    ok = inf.supported(
        "sample.material.formula",
        "CuO2",
        supporting_fields=("sample.material.formula",),
        supporting_evidence=({"source_type": "spreadsheet", "a": {"b": {"c": "d"}}},),
        rule="r",
        explanation="e",
    )
    assert ok.value == "CuO2"


def test_the_corpus_shape_that_motivated_the_nested_scan_still_exists():
    """Pins the fixture the finding was measured against, so this test does not
    quietly become a test of nothing if the corpus is rewritten."""
    import json as _json
    from pathlib import Path

    fixture = ws.REPO_ROOT / "tests/fixtures/official/operando_xanes_co2rr_record.json"
    assert fixture.exists()
    text = fixture.read_text(encoding="utf-8")
    assert '"uncertainty"' in text and '"confidence"' in text
    assert inf._confidence_keys_in(_json.loads(text)) == ["confidence"]
    del Path


def test_pending_response_no_longer_ships_an_unconsumed_inferences_block():
    """The ``inferences`` block reached three endpoints with no client consumer,
    shipped concrete values, and bypassed the client's own re-check (which only
    ran over ``item.inferability``). Serving it was speculative surface."""
    out = serialize.pending_to_list({"pending": [dict(SERIES_BLOCKER)]}, {})
    assert set(out) == {"pending"}
