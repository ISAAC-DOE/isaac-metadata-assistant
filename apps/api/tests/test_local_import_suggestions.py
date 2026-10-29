"""Suggestions from what an import already holds, and a Claude reading pass's findings.

* The absorber (element + edge) is SUGGESTED from the scientists' processed outputs linked
  to a group and the beamtime's element evidence, asked once, confirmed by ``set_absorber``,
  and carried only in the draft's ``implicit[]`` (the official schema has no field).
* A findings file becomes AI interpretations: cited, ``needs_review`` at most, and the
  question it lifts is STILL ASKED, with the reading as a hint (before this, an AI reading
  on a missing value made its question disappear).
* Facility hints are text, never values.
* Electrolyte, pH and potential scale are answerable (both schemas declare them).

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


def _beamtime(root: Path, *, second_symbol: str | None = None) -> Path:
    bt = root / "SYN_beamtime"
    make_scan(bt / "SYN_run_A.001")
    make_two(bt / "SYN_cell.txt")
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
