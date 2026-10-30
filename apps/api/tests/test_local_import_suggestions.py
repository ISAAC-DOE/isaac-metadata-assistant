"""Suggestions from what an import already holds, and a Claude reading pass's findings.

* The absorber (element + edge) is SUGGESTED from the scientists' processed outputs linked
  to a group and the beamtime's element evidence, asked once, confirmed by ``set_absorber``,
  and carried only in the draft's ``implicit[]`` (the official schema has no field).
* A findings file becomes AI interpretations: cited, ``needs_review`` at most, and the
  question it lifts is STILL ASKED, with the reading as a hint (before this, an AI reading
  on a missing value made its question disappear).
* Facility hints are text, never values.
* Electrolyte, pH, potential scale and potential set-point are answerable (both schemas
  declare them); a set-point that is not a number never reaches the record.
* Element / edge readings land on record GROUPS and feed the absorber question as AI
  suggestions beside the file evidence, never as it; only ``set_absorber`` gives the absorber.
* The acquisition-system facility hint is shown only when the scan headers carry that
  system's detector columns (the bundle's ``acquisition_system`` is a build default).

SYNTHETIC ``SYN_`` files only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import suggestions as S

from test_local_import_reader_ssrl_xdc import make_scan
from test_local_import_reader_two_column import make_two
from test_local_import_reader_xdi import make_xdi

BY = "SYNTHETIC TEST"
XDI_FIELDS = ("Column.1: energy eV", "Column.2: norm")


def _run(argv, capsys):
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, out


def _beamtime(root: Path, *, second_symbol: str | None = None, processed: bool = True) -> Path:
    bt = root / "SYN_beamtime"
    make_scan(bt / "SYN_run_A.001")
    make_two(bt / "SYN_cell.txt")
    if processed:
        make_xdi(bt / "proc" / "SYN_cell.nor", fields=("Element.edge: K", "Element.symbol: Zz", *XDI_FIELDS))
    if second_symbol:
        make_xdi(bt / "proc" / "SYN_cell.xmu", first_line="# XDI/1.0 Demeter/0.9.26",
                 fields=("Element.edge: K", f"Element.symbol: {second_symbol}", "Demeter.output_filetype: xmu", *XDI_FIELDS))
    return bt


@pytest.fixture()
def grouped(tmp_path, capsys):
    def build(**kw) -> Path:
        out = tmp_path / "out"
        assert _run(["import", str(_beamtime(tmp_path / "src", **kw)), "--out", str(out)], capsys)[0] == 0
        assert _run(["bundle", "group", str(out)], capsys)[0] == 0
        return out
    return build


def _load(b: Path) -> dict:
    return json.loads((b / "bundle.json").read_text())


def _group_of(bundle: dict, label: str) -> dict:
    key = next(r["run_key"] for r in bundle["runs"] if r["label"] == label)
    return next(g for g in bundle["record_groups"] if key in g["member_run_keys"])


# --- the absorber -------------------------------------------------------------------------------


def test_the_absorber_is_suggested_from_the_linked_processed_output(grouped):
    b = _load(grouped())
    sug = S.absorber_for_group(b, _group_of(b, "SYN_cell"))
    assert (sug["element"], sug["edge"], sug["status"]) == ("Zz", "K", "agrees")
    assert sug["linked_processed_outputs"] == 1 and sug["group_specific_statements"] == 2  # symbol + edge lines
    [w] = [w for w in sug["witnesses"] if w["kind"] == "processed_output_header" and w["element"]]
    assert w["relative_path"] == "proc/SYN_cell.nor" and w["locator"]
    assert "not confirmed" in w["link"]


def test_a_group_with_no_linked_output_and_no_beamtime_evidence_gets_no_suggestion(grouped):
    b = _load(grouped())
    sug = S.absorber_for_group(b, _group_of(b, "SYN_run"))
    assert sug["status"] == "none" and sug["element"] is None and sug["edge"] is None


def test_disagreeing_outputs_propose_no_element(grouped):
    b = _load(grouped(second_symbol="Yy"))
    sug = S.absorber_for_group(b, _group_of(b, "SYN_cell"))
    assert sug["status"] == "disagrees" and sug["element"] is None
    assert sug["readings"]["element"] == {"Zz": 1, "Yy": 1}
    assert sug["edge"] == "K"  # the edge half still agrees
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert q["scope"].startswith("group:") and "disagree" in q["text"] and "--element <El>" in q["answer_command"]


def test_the_absorber_is_asked_once_and_a_set_absorber_answer_reaches_the_sidecar_only(grouped, capsys):
    out = grouped()
    b = _load(out)
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert q["blocking"] is False and q["scope"] == "experiment" and "Zz" in q["text"]
    assert q["hints"][0]["kind"] == "processed_output_header"
    group = _group_of(b, "SYN_cell")
    draft, report = R.compose_group(b, group, out)
    assert {i["about"]: i["value"] for i in draft["implicit"]} == {"absorbing_element": None, "edge": None}
    assert report["absorber"]["confirmed"] is False

    code, _ = _run(["bundle", "decide", str(out), "--question", q["question_id"], "--decision", "set_absorber",
                    "--element", "Zz", "--edge", "K", "--by", BY], capsys)
    assert code == 0
    b = _load(out)
    assert not [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    group = _group_of(b, "SYN_cell")
    assert group["status"] == "proposed"  # set_absorber never confirms or rejects a group
    draft, report = R.compose_group(b, group, out)
    imp = {i["about"]: i for i in draft["implicit"]}
    assert imp["absorbing_element"]["value"] == "Zz" and imp["edge"]["value"] == "K"
    assert any(e["source_type"] == "user_confirmation" and e["decided_by"] == BY for e in imp["edge"]["evidence"])
    assert not any("Zz" in json.dumps(v) for v in draft["fields"].values())  # never an official field
    assert B.validate_bundle(b) == []


@pytest.mark.parametrize("element,edge", [("zz", "K"), ("Zz", "L4"), (None, "K"), ("Zz", None)])
def test_set_absorber_refuses_a_malformed_element_or_edge(grouped, element, edge):
    out = grouped()
    gid = _group_of(_load(out), "SYN_cell")["group_id"]
    with pytest.raises(M.MutationRefused):
        M.decide(out, target_ids=[gid], decision="set_absorber", value=None, by=BY, orcid=None, element=element, edge=edge)


# --- a reading pass's findings ------------------------------------------------------------------


def _findings(**over) -> dict:
    f = {
        "field_path": "context.environment",
        "value": "in_situ",
        "applies_to": {"scope": "runs", "run_labels": ["SYN_cell"]},
        "source": {"path": "SYN_cell.txt", "locator": "line 1"},
        "quote": "synthetic quote",
        "strength": "inferred",
        "reasoning": "synthetic reasoning",
    }
    f.update(over)
    return {"format": S.READINGS_FORMAT, "findings": [f]}


def _missing(bundle: dict, label: str, path: str) -> dict:
    rid = next(r["run_id"] for r in bundle["runs"] if r["label"] == label)
    return next(m for m in bundle["missing_values"] if m["run_id"] == rid and m["target_field_path"] == path)


def test_a_preview_writes_nothing_and_apply_records_cited_readings(grouped):
    out = grouped()
    before = (out / "bundle.json").read_bytes()
    plan = M.annotate_from_readings(out, _findings(), model_id="synthetic-model", apply=False)
    assert plan["applied"] is False and plan["interpretations"] == 1
    assert (out / "bundle.json").read_bytes() == before

    done = M.annotate_from_readings(out, _findings(), model_id="synthetic-model", apply=True)
    assert done["applied"] is True and done["interpretations"] == 1
    b = _load(out)
    [i] = b["ai_interpretations"]
    m = _missing(b, "SYN_cell", "context.environment")
    assert i["target"] == {"kind": "missing_value", "id": m["value_id"]}
    assert i["quote"] == "synthetic quote" and i["strength"] == "inferred" and i["source_path"] == "SYN_cell.txt"
    assert i["source_refs"][0]["source_id"] is not None  # a bundle source: its id is cited
    assert i["max_state"] == "needs_review" and m["value_state"] == B.STATE_NEEDS_REVIEW
    assert m["eligibility_for_official_record"]["eligible"] is False
    assert B.validate_bundle(b) == []
    again = M.annotate_from_readings(out, _findings(), model_id="synthetic-model", apply=True)
    assert again["interpretations"] == 0 and again["already_recorded"] == 1


def test_a_missing_value_an_ai_reading_lifted_is_still_asked_with_the_reading_as_a_hint(grouped):
    out = grouped()
    M.annotate_from_readings(out, _findings(), model_id="synthetic-model", apply=True)
    b = _load(out)
    m = _missing(b, "SYN_cell", "context.environment")
    asked = [q for q in Q.consolidate(b)["questions"] if {"kind": "missing_value", "id": m["value_id"]} in q["targets"]]
    assert asked, "the question disappeared once an AI reading touched its target"
    q = asked[0]
    hints = q["hints"] if q["kind"] != "optional_values" else q["field_hints"]["context.environment"]
    [h] = [h for h in hints if h["kind"] == "ai_suggestion"]
    assert h["literal"] == "in_situ" and h["source_path"] == "SYN_cell.txt" and h["quote"] == "synthetic quote"
    # a scientist's answer is what takes it out of the list
    M.decide(out, target_ids=[m["value_id"]], decision="correct", value="in_situ", by=BY, orcid=None)
    b = _load(out)
    assert _missing(b, "SYN_cell", "context.environment")["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    assert not [q for q in Q.consolidate(b)["questions"] if {"kind": "missing_value", "id": m["value_id"]} in q["targets"]]


def test_an_experiment_scope_finding_reaches_every_live_run_and_a_document_beside_the_folder_is_cited_by_path(grouped):
    out = grouped()
    f = _findings(field_path="system.facility.beamline", value="SYN-1", applies_to={"scope": "experiment"},
                  source={"path": "../SYN_proposal.pdf", "locator": "page 2"})
    done = M.annotate_from_readings(out, f, model_id="synthetic-model", apply=True)
    b = _load(out)
    beam = [m for m in b["missing_values"] if m["target_field_path"] == "system.facility.beamline"]
    assert done["interpretations"] == len(beam) >= 2
    assert all(i["source_refs"][0]["source_id"] is None and i["source_path"] == "../SYN_proposal.pdf" for i in b["ai_interpretations"])


@pytest.mark.parametrize("over,reason", [
    ({"applies_to": {"scope": "runs", "run_labels": ["NOT_A_RUN"]}}, "run labels not in this bundle"),
    ({"field_path": "system.not_a_field"}, "no missing value or candidate"),
    ({"quote": ""}, "needs field_path, value"),
    ({"applies_to": {"scope": "beamtime"}}, "applies_to.scope"),
])
def test_a_finding_that_cannot_be_placed_is_reported_never_forced(grouped, over, reason):
    out = grouped()
    done = M.annotate_from_readings(out, _findings(**over), model_id="synthetic-model", apply=True)
    assert done["interpretations"] == 0
    [s] = done["skipped"]
    assert reason in s["reason"]
    assert _load(out)["ai_interpretations"] == []


def test_an_electrolyte_reading_is_offered_unsplit_on_name_and_concentration(grouped):
    out = grouped()
    f = _findings(field_path="context.electrochemistry.electrolyte", value="0.1 M SYN-acid")
    done = M.annotate_from_readings(out, f, model_id="synthetic-model", apply=True)
    assert done["interpretations"] == 2
    b = _load(out)
    paths = {next(m["target_field_path"] for m in b["missing_values"] if m["value_id"] == i["target"]["id"]) for i in b["ai_interpretations"]}
    assert paths == {"context.electrochemistry.electrolyte.name", "context.electrochemistry.electrolyte.concentration_M"}
    assert all(i["proposed_value"] == "0.1 M SYN-acid" and "split it" in i["rationale"] for i in b["ai_interpretations"])


def test_the_cli_reads_a_findings_file_and_refuses_mixing_it_with_a_target(grouped, tmp_path, capsys):
    out = grouped()
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(_findings()))
    code, text = _run(["bundle", "annotate", str(out), "--from-readings", str(path), "--model", "m"], capsys)
    assert code == 0 and json.loads(text)["applied"] is False
    code, _ = _run(["bundle", "annotate", str(out), "--from-readings", str(path), "--model", "m", "--target", "x"], capsys)
    assert code != 0
    code, _ = _run(["bundle", "annotate", str(out), "--model", "m"], capsys)
    assert code != 0


# --- facility hints and the newly answerable fields ---------------------------------------------


def test_facility_questions_carry_text_hints_never_values(grouped):
    b = _load(grouped())
    payload = Q.consolidate(b)
    hinted = {}
    for q in payload["questions"]:
        for path, hints in (q.get("field_hints") or {}).items():
            hinted[path] = hints
        if (q.get("target_field_path") or "").startswith("system.facility."):
            hinted[q["target_field_path"]] = q["hints"]
    assert hinted.get("system.facility.beamline")
    assert {h["kind"] for h in hinted["system.facility.beamline"]} >= {"folder_name"}
    assert all("never an answer" in h["note"] for h in hinted["system.facility.beamline"])
    assert all(m["value_state"] == B.STATE_MISSING for m in b["missing_values"] if m["target_field_path"].startswith("system.facility."))


def test_electrolyte_ph_and_potential_scale_are_answerable_and_compose_into_the_draft(grouped):
    out = grouped()
    b = _load(out)
    for path in B.LOCAL_ANSWER_FIELDS:
        assert any(m["target_field_path"] == path for m in b["missing_values"]), path
    m = _missing(b, "SYN_cell", "context.electrochemistry.potential_scale")
    M.decide(out, target_ids=[m["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    b = _load(out)
    draft, _ = R.compose_group(b, _group_of(b, "SYN_cell"), out)
    assert draft["fields"]["context.electrochemistry.potential_scale"]["value"] == "RHE"


# --- review fixes ---------------------------------------------------------------------------------


def test_an_absorber_question_cannot_be_answered_with_confirm_so_its_groups_stay_proposed(grouped, capsys):
    out = grouped()
    [q] = [q for q in Q.consolidate(_load(out))["questions"] if q["kind"] == "confirm_absorber"]
    assert q["allowed_decisions"] == ["set_absorber", "defer"]
    code, _ = _run(["bundle", "decide", str(out), "--question", q["question_id"], "--decision", "confirm", "--by", BY], capsys)
    assert code != 0
    b = _load(out)
    assert b["scientist_decisions"] == [] and _group_of(b, "SYN_cell")["status"] == "proposed"


def test_every_question_names_the_decisions_that_answer_it(grouped):
    payload = Q.consolidate(_load(grouped()))
    assert payload["questions"]
    for q in payload["questions"]:
        assert q["allowed_decisions"] == list(Q.ALLOWED_DECISIONS[q["kind"]]), q["kind"]


def test_a_set_absorber_decision_without_element_or_edge_is_contract_invalid(grouped):
    out = grouped()
    gid = _group_of(_load(out), "SYN_cell")["group_id"]
    M.decide(out, target_ids=[gid], decision="set_absorber", value=None, by=BY, orcid=None, element="Zz", edge="K")
    b = _load(out)
    del b["scientist_decisions"][-1]["edge"]
    assert any("needs an element and an edge" in e for e in B.validate_bundle(b))
    draft, _ = R.compose_group(b, _group_of(b, "SYN_cell"), out)  # never a KeyError
    assert {i["about"]: i["value"] for i in draft["implicit"]} == {"absorbing_element": None, "edge": None}


def test_the_absorber_witness_quotes_the_files_own_literal(grouped):
    out = grouped()
    b = _load(out)
    draft, _ = R.compose_group(b, _group_of(b, "SYN_cell"), out)
    quotes = {e["quote"] for i in draft["implicit"] for e in i["evidence"] if e.get("method_id") == S.ABSORBER_RULE_ID}
    assert quotes == {"Zz", "K"}


@pytest.mark.parametrize("path", ["/Users/someone/notes.docx", "C:/notes.docx", "../../outside.pdf", "a/../../b.txt"])
def test_a_finding_citing_an_absolute_or_escaping_path_is_refused(grouped, path):
    out = grouped()
    done = M.annotate_from_readings(out, _findings(source={"path": path, "locator": "p1"}), model_id="m", apply=True)
    assert done["interpretations"] == 0 and "never absolute" in done["skipped"][0]["reason"]


def test_run_labels_must_be_a_list_and_runs_outside_live_groups_are_not_reached(grouped):
    out = grouped()
    done = M.annotate_from_readings(out, _findings(applies_to={"scope": "runs", "run_labels": "SYN_cell"}), model_id="m", apply=False)
    assert "non-empty list" in done["skipped"][0]["reason"]
    gid = _group_of(_load(out), "SYN_cell")["group_id"]
    M.decide(out, target_ids=[gid], decision="reject", value=None, by=BY, orcid=None)
    done = M.annotate_from_readings(out, _findings(), model_id="m", apply=False)
    assert done["interpretations"] == 0 and "no live record group" in done["skipped"][0]["reason"]


# --- Gap A: the potential set-point has an answer slot -------------------------------------------

POT = "context.electrochemistry.potential_setpoint_V"
SCALE = "context.electrochemistry.potential_scale"


def test_a_potential_reading_lands_on_a_run_with_no_parsed_potential(grouped):
    out = grouped()
    b = _load(out)
    assert not [c for c in b["candidates"] if c["target_field_path"] == POT]  # no file states one
    assert {m["run_id"] for m in b["missing_values"] if m["target_field_path"] == POT} == {
        r["run_id"] for r in b["runs"] if r["run_candidate"]}
    done = M.annotate_from_readings(out, _findings(field_path=POT, value=-0.8), model_id="synthetic-model", apply=True)
    assert done["interpretations"] == 1 and done["skipped"] == []
    b = _load(out)
    m = _missing(b, "SYN_cell", POT)
    [i] = b["ai_interpretations"]
    assert i["target"] == {"kind": "missing_value", "id": m["value_id"]} and i["proposed_value"] == -0.8
    assert "field_path" not in i  # a value target says its own field
    assert m["value_state"] == B.STATE_NEEDS_REVIEW and not m["eligibility_for_official_record"]["eligible"]
    [q] = [q for q in Q.consolidate(b)["questions"] if m["value_id"] in q.get("fields", {}).get(POT, ())]
    assert [h["literal"] for h in q["field_hints"][POT] if h["kind"] == "ai_suggestion"] == [-0.8]
    assert POT in q["answer_command"] and "--json" in q["answer_command"]  # a number needs --json
    assert B.validate_bundle(b) == []


def test_a_potential_answer_that_is_not_a_number_is_kept_out_of_the_record_and_said(grouped):
    out = grouped()
    m = _missing(_load(out), "SYN_cell", POT)
    # `decide` refuses it now (contract §25); a bundle an older build stored it in is still composed safely
    from tests_support_records import refused_then_stored

    assert "must be number" in refused_then_stored(out, "missing_value", m["value_id"], "-0.8 V")
    b = _load(out)
    m = _missing(b, "SYN_cell", POT)
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    assert m["eligibility_for_official_record"]["eligible"] is False
    assert "must be number" in m["eligibility_for_official_record"]["reason"]
    draft, report = R.compose_group(b, _group_of(b, "SYN_cell"), out)
    assert POT not in draft["fields"]
    [nc] = [n for n in report["not_composed"] if n.get("value_id") == m["value_id"]]
    assert nc["path"] == POT and "must be number" in nc["reason"]
    # a number, beside its confirmed scale, is composed
    M.decide(out, target_ids=[m["value_id"]], decision="correct", value=-0.8, by=BY, orcid=None)
    scale = _missing(_load(out), "SYN_cell", SCALE)
    M.decide(out, target_ids=[scale["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    b = _load(out)
    draft, report = R.compose_group(b, _group_of(b, "SYN_cell"), out)
    assert draft["fields"][POT]["value"] == -0.8 and draft["fields"][SCALE]["value"] == "RHE"
    assert not [n for n in report["not_composed"] if n.get("value_id") == m["value_id"]]


def test_a_potential_setpoint_without_its_scale_is_not_composed_and_says_why(grouped):
    out = grouped()
    m = _missing(_load(out), "SYN_cell", POT)
    M.decide(out, target_ids=[m["value_id"]], decision="correct", value=-0.8, by=BY, orcid=None)
    b = _load(out)
    assert _missing(b, "SYN_cell", POT)["eligibility_for_official_record"]["eligible"] is True  # the number itself is fine
    draft, report = R.compose_group(b, _group_of(b, "SYN_cell"), out)
    assert POT not in draft["fields"] and SCALE not in draft["fields"]
    [nc] = [n for n in report["not_composed"] if n.get("value_id") == m["value_id"]]
    assert nc["path"] == POT and nc["reason"] == R.SETPOINT_NEEDS_SCALE
    assert not [f for f in report["filled"] if f["path"] == POT]
    # a scale confirmed for ANOTHER run of the bundle does not stand in for this run's
    other = _missing(b, "SYN_run", SCALE)
    M.decide(out, target_ids=[other["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    b = _load(out)
    draft, report = R.compose_group(b, _group_of(b, "SYN_cell"), out)
    assert POT not in draft["fields"]
    assert [n["reason"] for n in report["not_composed"] if n.get("value_id") == m["value_id"]] == [R.SETPOINT_NEEDS_SCALE]


# --- Gap B: element / edge readings feed the absorber question ------------------------------------


def _absorber_findings(*pairs, scope=None, locator="line 3") -> dict:
    scope = scope or {"scope": "experiment"}
    return {"format": S.READINGS_FORMAT, "findings": [
        {"field_path": path, "value": value, "applies_to": scope,
         "source": {"path": "SYN_cell.txt", "locator": locator}, "quote": f"synthetic quote {value}",
         "strength": "stated", "reasoning": "synthetic reasoning"}
        for path, value in pairs]}


def test_element_and_edge_readings_without_processed_output_reach_the_groups_and_the_question(grouped, capsys):
    out = grouped(processed=False)
    b = _load(out)
    assert not b.get("processed_outputs") and not b["experiment"]["element_evidence"]
    live = [g for g in b["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES]
    assert len(live) == 2
    assert not [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]  # nothing to ask yet

    f = _absorber_findings(("system.absorbing_element", "Zz"), ("system.edge", "K"))  # an alias is accepted
    done = M.annotate_from_readings(out, f, model_id="synthetic-model", apply=True)
    assert done["interpretations"] == 4 and done["skipped"] == []
    b = _load(out)
    assert {(i["target"]["kind"], i["field_path"]) for i in b["ai_interpretations"]} == {
        ("record_group", "system.element"), ("record_group", "system.edge")}
    assert {i["target"]["id"] for i in b["ai_interpretations"]} == {g["group_id"] for g in live}
    assert B.validate_bundle(b) == []

    group = _group_of(b, "SYN_run")
    sug = S.absorber_for_group(b, group)
    # AI is not file evidence: the files' status and values are unchanged
    assert (sug["status"], sug["element"], sug["edge"], sug["witnesses"]) == ("none", None, None, [])
    assert sorted((r["field"], r["value"]) for r in sug["ai_readings"]) == [("system.edge", "K"), ("system.element", "Zz")]
    r = next(r for r in sug["ai_readings"] if r["field"] == "system.element")
    assert r["source_path"] == "SYN_cell.txt" and r["locator"] == "line 3" and r["quote"] == "synthetic quote Zz"
    assert r["strength"] == "stated" and r["finding_id"] == "finding-001" and len(r["interpretation_ids"]) == 1
    assert sug["ai_vs_files"] == {"element": "no_file_evidence", "edge": "no_file_evidence"}
    assert sug["ai_disagrees_with_files"] is False

    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert q["scope"] == "experiment" and {t["id"] for t in q["targets"]} == {g["group_id"] for g in live}
    assert q["allowed_decisions"] == ["set_absorber", "defer"]
    assert "only an AI reading" in q["text"] and "not file evidence" in q["text"]
    assert "--element <El>" in q["answer_command"]  # an AI reading is never pre-filled as the answer
    ai = [h for h in q["hints"] if h["kind"] == "ai_suggestion"]
    assert {(h["field"], h["literal"]) for h in ai} == {("system.element", "Zz"), ("system.edge", "K")}
    assert all(h["source_path"] == "SYN_cell.txt" and h["quote"] and h["model_id"] == "synthetic-model"
               and "AI reading" in h["note"] and h["groups"] == 2 for h in ai)

    # an AI reading alone writes nothing to implicit[]
    draft, report = R.compose_group(b, group, out)
    assert not [i for i in draft["implicit"] if i["about"] in ("absorbing_element", "edge")]
    assert "absorber" not in report
    code, _ = _run(["bundle", "decide", str(out), "--question", q["question_id"], "--decision", "set_absorber",
                    "--element", "Zz", "--edge", "K", "--by", BY], capsys)
    assert code == 0
    b = _load(out)
    draft, report = R.compose_group(b, _group_of(b, "SYN_run"), out)
    assert {i["about"]: i["value"] for i in draft["implicit"]} == {"absorbing_element": "Zz", "edge": "K"}
    assert not [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert B.validate_bundle(b) == []


def test_an_ai_reading_that_disagrees_with_the_files_is_shown_and_not_resolved(grouped):
    out = grouped()
    f = _absorber_findings(("system.element", "Yy"), scope={"scope": "runs", "run_labels": ["SYN_cell"]})
    assert M.annotate_from_readings(out, f, model_id="synthetic-model", apply=True)["interpretations"] == 1
    b = _load(out)
    group = _group_of(b, "SYN_cell")
    sug = S.absorber_for_group(b, group)
    assert (sug["status"], sug["element"], sug["edge"]) == ("agrees", "Zz", "K")  # the files' answer, unmoved
    assert sug["readings"]["element"] == {"Zz": 1}  # the AI value is not counted as a witness
    assert sug["ai_vs_files"]["element"] == "differs" and sug["ai_disagrees_with_files"] is True
    qs = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    [q] = [q for q in qs if {"kind": "record_group", "id": group["group_id"]} in q["targets"]]
    assert q["scope"] == f"group:{group['group_id']}"  # asked on its own, not folded into the files' answer
    assert "differs" in q["text"] and "Nothing has chosen" in q["text"] and "--element <El>" in q["answer_command"]
    kinds = [h["kind"] for h in q["hints"]]
    assert kinds[0] == "processed_output_header" and kinds[-1] == "ai_suggestion"  # file evidence first
    ai = q["hints"][-1]
    assert ai["literal"] == "Yy" and ai["differs_from_files"] is True and "DIFFERS" in ai["note"]
    draft, _ = R.compose_group(b, group, out)
    assert {i["about"]: i["value"] for i in draft["implicit"]} == {"absorbing_element": None, "edge": None}
    assert B.validate_bundle(b) == []


@pytest.mark.parametrize("path,value", [
    ("system.element", "zz"), ("system.element", "Fe2"), ("system.element", "iron"), ("system.element", 26),
    ("system.edge", "k"), ("system.edge", "L4"), ("system.edge", "K-edge"), ("system.edge", " K"),
])
def test_an_absorber_reading_of_the_wrong_shape_is_skipped_never_normalised(grouped, path, value):
    out = grouped(processed=False)
    done = M.annotate_from_readings(out, _absorber_findings((path, value)), model_id="m", apply=True)
    assert done["interpretations"] == 0
    [s] = done["skipped"]
    assert "is not an absorber" in s["reason"] and "nothing is normalised" in s["reason"]
    assert _load(out)["ai_interpretations"] == []


def test_a_runs_scope_absorber_reading_reaches_only_the_groups_holding_those_runs(grouped):
    out = grouped(processed=False)
    run_group = _group_of(_load(out), "SYN_run")
    done = M.annotate_from_readings(out, _absorber_findings(("system.element", "Zz"), scope={"scope": "runs", "run_labels": ["SYN_run"]}),
                                    model_id="m", apply=True)
    assert done["interpretations"] == 1
    b = _load(out)
    [i] = b["ai_interpretations"]
    assert i["target"] == {"kind": "record_group", "id": run_group["group_id"]}
    assert S.absorber_for_group(b, _group_of(b, "SYN_cell"))["ai_readings"] == []
    # a one-half reading is asked per group, never consolidated
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert q["scope"] == f"group:{run_group['group_id']}" and "name only one half" in q["text"]
    # the same refusals as a value reading
    done = M.annotate_from_readings(out, _absorber_findings(("system.edge", "K"), scope={"scope": "runs", "run_labels": ["NOT_A_RUN"]}),
                                    model_id="m", apply=False)
    assert "run labels not in this bundle" in done["skipped"][0]["reason"]
    M.decide(out, target_ids=[run_group["group_id"]], decision="reject", value=None, by=BY, orcid=None)
    done = M.annotate_from_readings(out, _absorber_findings(("system.edge", "K"), scope={"scope": "runs", "run_labels": ["SYN_run"]}),
                                    model_id="m", apply=False)
    assert done["interpretations"] == 0 and "no live record group" in done["skipped"][0]["reason"]


def test_an_absorber_reading_before_grouping_is_skipped_with_the_reason(tmp_path, capsys):
    out = tmp_path / "out"
    assert _run(["import", str(_beamtime(tmp_path / "src", processed=False)), "--out", str(out)], capsys)[0] == 0
    done = M.annotate_from_readings(out, _absorber_findings(("system.element", "Zz")), model_id="m", apply=True)
    assert done["interpretations"] == 0 and "no live record group yet" in done["skipped"][0]["reason"]


def test_absorber_readings_apply_once_and_element_k_and_edge_k_are_two_readings(grouped):
    out = grouped(processed=False)
    f = _absorber_findings(("system.element", "K"), ("system.edge", "K"))  # potassium, K edge: same value, same line
    first = M.annotate_from_readings(out, f, model_id="m", apply=True)
    assert first["interpretations"] == 4
    again = M.annotate_from_readings(out, f, model_id="m", apply=True)
    assert again["interpretations"] == 0 and again["already_recorded"] == 4
    b = _load(out)
    assert len(b["ai_interpretations"]) == 4
    assert {r["field"] for r in S.absorber_for_group(b, _group_of(b, "SYN_run"))["ai_readings"]} == {"system.element", "system.edge"}


def test_the_validator_refuses_a_tampered_absorber_reading(grouped):
    out = grouped(processed=False)
    M.annotate_from_readings(out, _absorber_findings(("system.element", "Zz")), model_id="m", apply=True)
    b = _load(out)
    b["ai_interpretations"][0]["proposed_value"] = "zz"
    assert any("is not an absorber element" in e for e in B.validate_bundle(b))
    b = _load(out)
    m = b["missing_values"][0]
    b["ai_interpretations"][0]["target"] = {"kind": "missing_value", "id": m["value_id"]}
    assert any("not a record group" in e for e in B.validate_bundle(b))


# --- Gap C: the acquisition-system hint is shown only when the files carry its columns -------------


def test_no_acquisition_system_hint_when_no_run_carries_its_detector_columns(grouped):
    b = _load(grouped())
    assert b["experiment"]["acquisition_system"]["candidate_channels"]  # the build default is still recorded
    hints = S.facility_hints(b)
    assert [h["kind"] for h in hints] == ["folder_name"]


def test_the_acquisition_system_hint_names_the_columns_the_scan_headers_carry(tmp_path, capsys):
    from tests_support_records import SEMANTICS

    out = tmp_path / "bl15"
    assert _run(["import", str(SEMANTICS), "--out", str(out)], capsys)[0] == 0
    b = _load(out)
    [acq] = [h for h in S.facility_hints(b) if h["kind"] == "acquisition_system"]
    # THE EXPECTED COUNT IS READ FROM THE FIXTURE FILES THEMSELVES, not from the bundle's own
    # channel summary: a run counts when one of its scan files' `#L` column line names vortDT*.
    def has_vortex_columns(rel: str) -> bool:
        lines = (SEMANTICS / rel).read_text(errors="replace").splitlines()
        return any(line.startswith("#L") and any(tok.startswith("vortDT") for tok in line.split()) for line in lines)

    expected = sum(1 for r in b["runs"] if any(has_vortex_columns(s["relative_path"]) for s in r["scans"]))
    assert expected >= 1
    assert acq["locator"].startswith(f"{expected} run(s)' scan headers have columns named vortDT")
    assert "(the column naming of: SSRL BL15-2 SPEC scan exports" in acq["locator"]
    assert "matched" not in acq["locator"] and "not proof of the beamline" in acq["note"] and "never an answer" in acq["note"]
    assert any(h["kind"] == "folder_name" for h in S.facility_hints(b))


# --- 2026-10-29: the bundle names BL15-2 only where the facility hint would ------------------------

BL152_SYSTEM_NAME = "SSRL BL15-2 SPEC scan exports — Vortex fluorescence channels"


def test_a_bundle_whose_scan_headers_lack_the_system_columns_does_not_name_bl15_2(grouped):
    b = _load(grouped())
    acq = b["experiment"]["acquisition_system"]
    # the reader profile applied is still recorded, by id (ids name code) ...
    assert acq["system_id"] == "ssrl_bl152_spec_vortex_channels" and acq["candidate_channels"]
    assert acq["applied_as"] == "build_default" and acq["runs_with_its_columns"] == 0 and acq["columns_seen"] == []
    # ... but nothing in these files shows it, so no beamline name is shown, and the statement says why
    assert "display_name" not in acq
    assert "its name is not shown" in acq["statement"] and "nothing in these files says" not in acq["statement"]
    default = [n for n in b["naming_profiles"] if n["basis"] == "build_default"]
    assert default and all(n["display_name"] is None for n in default)
    assert all(n["profile_id"] == "ssrl_bl152_herfd_echem_naming" for n in default)
    assert all("not detected from these files" in n["selector_description"] for n in default)
    assert "BL15-2" not in json.dumps([acq, b["naming_profiles"]])
    assert [h["kind"] for h in S.facility_hints(b)] == ["folder_name"]
    assert B.validate_bundle(b) == []


def test_a_bl15_2_fixture_whose_scan_headers_carry_the_columns_keeps_its_label(tmp_path, capsys):
    """The negative control: the semantics corpus's scan headers name vortDT*, so the system's
    name stays, with a statement that column naming is not proof of the beamline."""
    from tests_support_records import SEMANTICS

    out = tmp_path / "bl15"
    assert _run(["import", str(SEMANTICS), "--out", str(out)], capsys)[0] == 0
    b = _load(out)
    acq = b["experiment"]["acquisition_system"]
    assert acq["display_name"] == BL152_SYSTEM_NAME
    assert acq["runs_with_its_columns"] >= 1 and acq["columns_seen"] and all(c.startswith("vortDT") for c in acq["columns_seen"])
    assert "not proof of the beamline" in acq["statement"]
    [hint] = [h for h in S.facility_hints(b) if h["kind"] == "acquisition_system"]
    assert hint["locator"].startswith(f"{acq['runs_with_its_columns']} run(s)'")
    default = [n for n in b["naming_profiles"] if n["basis"] == "build_default"]
    assert default and all(n["display_name"].startswith("SSRL BL15-2 HERFD electrochemistry filename convention v1") for n in default)
    assert all(n["selector_description"].startswith("every source (this build's default naming convention")
               and "not detected from these files" in n["selector_description"] for n in default)
    assert B.validate_bundle(b) == []


def test_a_file_name_reused_across_run_folders_is_marked_reused_and_its_tokens_are_kept(tmp_path, capsys):
    """`AgL3_xas_exp1.exp` beside Ti data, in every run folder: its tokens stay `unknown_token`
    statements, and their locator now says the name recurs and the file is no run's scan."""
    bt = tmp_path / "src" / "SYN_reuse"
    for i, folder in enumerate(("SYN_01_alpha", "SYN_02_beta", "SYN_03_gamma"), 1):
        make_scan(bt / folder / f"{folder}_A.001")
        (bt / folder / "SYN_QqL3_tmpl.exp").write_text(f"SYNTHETIC macro copied to folder {i}\n")
    (bt / "SYN_01_alpha" / "SYN_once_only.exp").write_text("SYNTHETIC macro in one folder\n")
    out = tmp_path / "out"
    assert _run(["import", str(bt), "--out", str(out)], capsys)[0] == 0
    b = _load(out)
    tokens = [e for e in b["extended_context"] if (e["locator"] or "").startswith("filename token ")]
    reused = [e for e in tokens if e["relative_path"].endswith("/SYN_QqL3_tmpl.exp")]
    assert len({e["relative_path"] for e in reused}) == 3
    assert any(e["raw_literal"] == "QqL3" and e["concept"] == "unknown_token" for e in reused)
    for e in reused:
        assert e["locator"].endswith(
            "; this file name recurs in 3 folders of this import and the file is no run's scan, so the name "
            "is reused and its tokens need not describe this run or beamtime")
        assert e["entry_id"].startswith("filename:") and e["value_state"] == "source_recorded"
    # a name in one folder, and a run's own scan files, are not marked
    others = [e for e in tokens if e not in reused]
    assert any(e["relative_path"].endswith("SYN_once_only.exp") for e in others)
    assert all("recurs in" not in e["locator"] for e in others)
    # the reused name's tokens are nobody's sample and no group's basis
    assert "QqL3" not in json.dumps([b["samples"], b["record_groups"], b["questions"], b["candidates"]])
    assert B.validate_bundle(b) == []


def test_a_scan_file_name_repeated_in_every_run_folder_is_a_run_file_and_is_not_marked_reused(tmp_path, capsys):
    """Each folder's own scan shares one name (`SYN_QqL3_A.001`): the name recurs, but each
    copy is a run's scan, so its tokens describe that run and are not marked as a reused name."""
    bt = tmp_path / "src" / "SYN_same_scan_name"
    for folder in ("SYN_01_alpha", "SYN_02_beta", "SYN_03_gamma"):
        make_scan(bt / folder / "SYN_QqL3_A.001")
    out = tmp_path / "out"
    assert _run(["import", str(bt), "--out", str(out)], capsys)[0] == 0
    b = _load(out)
    scan_tokens = [e for e in b["extended_context"]
                   if (e["locator"] or "").startswith("filename token ") and e["relative_path"].endswith("/SYN_QqL3_A.001")]
    assert len({e["relative_path"] for e in scan_tokens}) == 3
    assert len(b["runs"]) == 3  # each copy IS a run's scan: the premise of the exclusion
    assert all("recurs in" not in e["locator"] for e in scan_tokens)
    assert B.validate_bundle(b) == []


# --- review fixes: regroup after an absorber reading; readings that name some of a group's runs -----


def test_a_regroup_after_an_absorber_reading_supersedes_the_old_groups_and_a_reapply_reaches_the_new(tmp_path, capsys):
    from test_local_import_grouping_cli import _folder

    src, out = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(out)], capsys)[0] == 0
    assert _run(["bundle", "group", str(out)], capsys)[0] == 0
    old = [g["group_id"] for g in _load(out)["record_groups"]]
    assert len(old) == 2
    f = {"format": S.READINGS_FORMAT, "findings": [
        {"field_path": "system.element", "value": "Fe", "applies_to": {"scope": "experiment"},
         "source": {"path": "Zz_XAS.mac", "locator": "line 1"}, "quote": "synthetic quote", "strength": "stated", "reasoning": "r"}]}
    assert M.annotate_from_readings(out, f, model_id="m", apply=True)["interpretations"] == 2
    assert _run(["bundle", "decide", str(out), "--target", "experiment", "--decision", "set_counter_positions",
                 "--positions", "2", "--by", BY], capsys)[0] == 0
    # this used to be refused for good: "a record_group target ... does not exist"
    assert _run(["bundle", "group", str(out), "--regroup"], capsys)[0] == 0
    b = _load(out)
    assert B.validate_bundle(b) == []
    [new] = [g for g in b["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES]
    assert new["group_id"] not in old and len(new["member_run_keys"]) == 2
    sup = {s["group_id"]: s for s in b["superseded_record_groups"]}
    assert set(sup) == set(old) and all("AI reading" in s["reason"] for s in sup.values())
    assert {i["target"]["id"] for i in b["ai_interpretations"]} == set(old)  # the readings stay where they were made
    # the absorber question looks only at the LIVE group: the old readings are not its hints
    assert S.absorber_for_group(b, new)["ai_readings"] == []
    qs = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert not [h for q in qs for h in q["hints"] if h["kind"] == "ai_suggestion"]
    # re-applying the same findings file (the skill's step after --regroup) lands it on the new group
    again = M.annotate_from_readings(out, f, model_id="m", apply=True)
    assert again["interpretations"] == 1 and again["already_recorded"] == 0
    b = _load(out)
    assert [r["value"] for r in S.absorber_for_group(b, new)["ai_readings"]] == ["Fe"]
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert {"kind": "record_group", "id": new["group_id"]} in q["targets"]
    assert [h["literal"] for h in q["hints"] if h["kind"] == "ai_suggestion"] == ["Fe"]
    assert B.validate_bundle(b) == []
    # and a second regroup still succeeds (the superseded groups keep their readings)
    assert _run(["bundle", "group", str(out), "--regroup"], capsys)[0] == 0
    assert B.validate_bundle(_load(out)) == []


def _one_group_of_both_runs(out: Path) -> dict:
    """SYNTHETIC: fold the two proposed groups into one (as a scientist's merge would), so a
    reading can name fewer than all of a group's runs."""
    data = _load(out)
    a, b2 = data["record_groups"][:2]
    a["member_run_keys"] = a["member_run_keys"] + b2["member_run_keys"]
    data["record_groups"] = [a]
    data["merge_candidates"] = []
    a["merge_candidate_ids"] = []
    (out / "bundle.json").write_text(json.dumps(data))
    M.mutate(out, lambda bundle: None)  # re-derived and re-validated on save
    return a


def test_a_runs_scope_reading_on_a_bigger_group_says_which_runs_it_was_read_for(grouped):
    out = grouped(processed=False)
    group = _one_group_of_both_runs(out)
    f = _absorber_findings(("system.element", "Zz"), ("system.edge", "K"), scope={"scope": "runs", "run_labels": ["SYN_run"]})
    assert M.annotate_from_readings(out, f, model_id="m", apply=True)["interpretations"] == 2
    b = _load(out)
    rid = next(r["run_id"] for r in b["runs"] if r["label"] == "SYN_run")
    assert {json.dumps(i["run_ids"]) for i in b["ai_interpretations"]} == {json.dumps([rid])}
    assert all(i["target"] == {"kind": "record_group", "id": group["group_id"]} for i in b["ai_interpretations"])
    sug = S.absorber_for_group(b, group)
    assert all(r["run_ids"] == [rid] and r["read_for"] == f"read for 1 of 2 runs in this group: SYN_run ({rid})" for r in sug["ai_readings"])
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert q["scope"] == "experiment" and "2 AI reading(s) name only some of a group's runs (see the hints)" in q["text"]
    hints = [h for h in q["hints"] if h["kind"] == "ai_suggestion"]
    assert hints and all("read for 1 of 2 runs in this group: SYN_run" in h["note"] for h in hints)
    assert all(h["read_for"] == [{"group_id": group["group_id"], "run_ids": [rid], "text": f"read for 1 of 2 runs in this group: SYN_run ({rid})"}] for h in hints)
    # an experiment-scope reading is about the whole group: no run_ids, no "read for"
    M.annotate_from_readings(out, _absorber_findings(("system.edge", "K"), locator="line 9"), model_id="m", apply=True)
    b = _load(out)
    whole = [r for r in S.absorber_for_group(b, group)["ai_readings"] if r["locator"] == "line 9"]
    assert [(r["run_ids"], r["read_for"]) for r in whole] == [(None, None)]
    assert B.validate_bundle(b) == []


def test_the_validator_refuses_run_ids_outside_the_group_or_on_a_value_reading(grouped):
    out = grouped(processed=False)
    f = _absorber_findings(("system.element", "Zz"), scope={"scope": "runs", "run_labels": ["SYN_run"]})
    M.annotate_from_readings(out, f, model_id="m", apply=True)
    b = _load(out)
    other = next(r["run_id"] for r in b["runs"] if r["label"] == "SYN_cell")
    b["ai_interpretations"][0]["run_ids"] = [other]
    assert any("not in group" in e for e in B.validate_bundle(b))
    b = _load(out)
    M.annotate_from_readings(out, _findings(), model_id="m", apply=True)
    b = _load(out)
    value_reading = next(i for i in b["ai_interpretations"] if i["target"]["kind"] == "missing_value")
    value_reading["run_ids"] = [other]
    assert any("only a record-group absorber reading carries" in e for e in B.validate_bundle(b))


def test_a_parsed_setpoint_is_composed_only_beside_its_runs_confirmed_scale(tmp_path, capsys):
    from test_local_import_grouping_cli import _folder

    src, out = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(out)], capsys)[0] == 0
    assert _run(["bundle", "group", str(out)], capsys)[0] == 0
    b = _load(out)
    pot = next(c for c in b["candidates"] if c["target_field_path"] == POT and c["run_id"] == "run-001")
    M.decide(out, target_ids=[pot["candidate_id"]], decision="confirm", value=None, by=BY, orcid=None)
    b = _load(out)
    key = next(r["run_key"] for r in b["runs"] if r["run_id"] == "run-001")
    group = next(g for g in b["record_groups"] if key in g["member_run_keys"])
    draft, report = R.compose_group(b, group, out)
    assert POT not in draft["fields"]
    assert [n["reason"] for n in report["not_composed"] if n.get("candidate_id") == pot["candidate_id"]] == [R.SETPOINT_NEEDS_SCALE]
    scale = next(m for m in b["missing_values"] if m["target_field_path"] == SCALE and m["run_id"] == "run-001")
    M.decide(out, target_ids=[scale["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    b = _load(out)
    draft, report = R.compose_group(b, group, out)
    assert draft["fields"][POT]["value"] == pot["value"] and draft["fields"][SCALE]["value"] == "RHE"
    assert not [n for n in report["not_composed"] if n.get("candidate_id") == pot["candidate_id"]]


def _two_runs_one_group(tmp_path, capsys):
    from test_local_import_grouping_cli import _folder

    src, out = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(out)], capsys)[0] == 0
    assert _run(["bundle", "group", str(out)], capsys)[0] == 0
    assert _run(["bundle", "decide", str(out), "--target", "experiment", "--decision", "set_counter_positions",
                 "--positions", "2", "--by", BY], capsys)[0] == 0
    assert _run(["bundle", "group", str(out), "--regroup"], capsys)[0] == 0
    b = _load(out)
    [g] = [g for g in b["record_groups"] if g["status"] == "proposed"]
    pots = sorted((c for c in b["candidates"] if c["target_field_path"] == POT), key=lambda c: c["run_id"])
    scales = {m["run_id"]: m for m in b["missing_values"] if m["target_field_path"] == SCALE}
    assert len(g["member_run_keys"]) == 2 and [c["run_id"] for c in pots] == ["run-001", "run-002"]
    return out, g, pots, scales


def test_differing_setpoints_in_one_group_are_a_disagreement_even_when_only_one_has_a_scale(tmp_path, capsys):
    out, g, (a, b2), scales = _two_runs_one_group(tmp_path, capsys)
    M.decide(out, target_ids=[a["candidate_id"]], decision="confirm", value=None, by=BY, orcid=None)  # 0.4
    M.decide(out, target_ids=[b2["candidate_id"]], decision="correct", value=0.6, by=BY, orcid=None)
    M.decide(out, target_ids=[scales["run-001"]["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    draft, report = R.compose_group(_load(out), g, out)
    assert POT not in draft["fields"]  # 0.4 used to be filled, with 0.6 hidden behind the scale gate
    [dis] = [d for d in report["disagreements"] if d["path"] == POT]
    assert sorted(dis["values"]) == [0.4, 0.6] and set(dis["from"]) == {a["candidate_id"], b2["candidate_id"]}
    assert not [n for n in report["not_composed"] if n.get("path") == POT]


def test_an_agreed_setpoint_is_filled_only_when_every_run_has_its_scale(tmp_path, capsys):
    out, g, (a, b2), scales = _two_runs_one_group(tmp_path, capsys)
    assert a["value"] == b2["value"]
    M.decide(out, target_ids=[a["candidate_id"], b2["candidate_id"]], decision="confirm", value=None, by=BY, orcid=None)
    M.decide(out, target_ids=[scales["run-001"]["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    draft, report = R.compose_group(_load(out), g, out)
    assert POT not in draft["fields"] and draft["fields"][SCALE]["value"] == "RHE"
    reasons = {n["candidate_id"]: n["reason"] for n in report["not_composed"] if n.get("path") == POT}
    assert reasons == {b2["candidate_id"]: R.SETPOINT_NEEDS_SCALE, a["candidate_id"]: R.SETPOINT_GROUP_NEEDS_SCALE}
    M.decide(out, target_ids=[scales["run-002"]["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    draft, report = R.compose_group(_load(out), g, out)
    assert draft["fields"][POT]["value"] == a["value"]
    assert not [n for n in report["not_composed"] if n.get("path") == POT]
