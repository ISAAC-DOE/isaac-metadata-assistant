"""Overnight polish, 18 Nov 2026: CLI and import items found by an end-to-end run. SYNTHETIC files only (the committed
multi-operator corpus and invented SYN spectra).

1. A refused ``bundle decide --question`` on a question that exists but has no open target in the named scope exits 2
   (a refused decision, reference/commands.md) and says nothing was recorded; only an unknown id is exit 6.
2. ``bundle upload --dry-run`` says the notes ``bundle export`` said ("Written without the potential set-point: …").
5. A set-point the file names give as ONE value, waiting for a confirm, is asked WITH its missing scale (both
   commands), so the scientist is not sent round twice.
6. ``decide --target <group> --decision set_role --value sample|reference|alignment`` sets what a group is; the cell
   wording follows the role.
9. A BL15-2 reading that rests on the SPEC fingerprint only (an account such as ``specadm``) tells the scientist to
   answer the beamline question, with the command.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_polish_c3q import SCALE, SETPOINT, _group_of_run  # noqa: E402
from test_local_import_polish_c5a import _answer, _warning, grouped, grouped_pristine  # noqa: E402,F401  (fixtures)
from test_local_import_records import (  # noqa: E402,F401  (fixtures)
    _decide_everything, _portal, bdir, fake_upstream, pristine)

WHO = "SYN Scientist"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    """The vendored schema basis (no portal validator installed, as in CI)."""
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def _run(capsys, *argv):
    capsys.readouterr()
    code = cli.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def _decide(capsys, bdir, *argv):
    return _run(capsys, "bundle", "decide", bdir, *argv, "--by", WHO)


# --- 1. a refused decide exits 2 ---------------------------------------------------------------------------------


def _experiment_question(b):
    return next(q for q in Q.consolidate(b)["questions"]
                if q["kind"] == "missing_value" and list(q.get("per_scope_targets") or ()) == ["experiment"])


def test_a_question_that_reaches_none_of_the_named_groups_is_refused_with_exit_2(grouped, capsys):
    b = M.load(grouped)
    qid = _experiment_question(b)["question_id"]
    g1, g2 = [g["group_id"] for g in Q.live_groups(b)][:2]
    before = (grouped / "bundle.json").read_bytes()
    code, out, err = _decide(capsys, grouped, "--question", qid, "--only", f"group:{g1}", "--only", f"group:{g2}",
                             "--decision", "correct", "--value", "SYN group")
    assert code == 2, err
    assert f"No open question {qid!r}" in err and "nothing was recorded" in err.lower() and out == ""
    assert (grouped / "bundle.json").read_bytes() == before


@pytest.mark.parametrize("kind,argv", [("resolve_conflict", ["--decision", "confirm"]),
                                       ("optional_values", ["--decision", "correct", "--value", "3"])])
def test_a_group_question_answered_for_a_group_it_does_not_reach_exits_2(grouped, capsys, kind, argv):
    b = M.load(grouped)
    live = [g["group_id"] for g in Q.live_groups(b)]
    q, outside = next((q, out) for q in Q.consolidate(b)["questions"] if q["kind"] == kind
                      and "experiment" not in (q.get("per_scope_targets") or {})
                      and (out := [g for g in live if f"group:{g}" not in (q.get("per_scope_targets") or {})]))
    before = (grouped / "bundle.json").read_bytes()
    code, out, err = _decide(capsys, grouped, "--question", q["question_id"], "--only", f"group:{outside[0]}", *argv)
    assert code == 2, err
    assert f"No open question {q['question_id']!r} for group:{outside[0]}" in err and "nothing was recorded" in err
    assert out == "" and (grouped / "bundle.json").read_bytes() == before


def test_only_an_open_question_missing_the_scope_turns_not_found_into_refused(grouped):
    """Review of PR #335: a question no longer open (answered, of a kind not answered again) stays exit 6, as before;
    only an OPEN question that reaches none of the named scopes is exit 2."""
    b = M.load(grouped)
    payload = Q.consolidate(b)
    qid = payload["questions"][0]["question_id"]
    exc = M.MutationRefused(f"No open question {qid!r} for group:x.", code=6)
    assert M._scope_refused(exc, b, None, None, payload, qid).code == 2
    assert M._scope_refused(exc, b, None, None, payload, "Q-0000000000") is exc  # not open (answered, or unknown)
    assert M._scope_refused(exc, b, None, None, None, qid) is exc                # nothing open was resolved


def test_an_unknown_question_or_group_is_still_not_found(grouped, capsys):
    b = M.load(grouped)
    qid = _experiment_question(b)["question_id"]
    g1 = Q.live_groups(b)[0]["group_id"]
    code, _, err = _decide(capsys, grouped, "--question", "Q-0000000000", "--decision", "correct", "--value", "x")
    assert code == 6 and "No open question 'Q-0000000000'" in err
    code, _, err = _decide(capsys, grouped, "--question", qid, "--only", f"group:{g1}", "--only", "group:rg-nope",
                           "--decision", "correct", "--value", "SYN group")
    assert code in (2, 6) and "nothing was recorded" in err.lower()
    code, _, err = _decide(capsys, grouped, "--question", qid, "--only", "group:rg-nope", "--decision", "correct",
                           "--value", "SYN group")
    assert code == 6
    code, _, err = _decide(capsys, grouped, "--target", "nope", "--decision", "confirm")
    assert code == 6


# --- 2. the upload dry run says export's notes ---------------------------------------------------------------------


def test_the_upload_dry_run_says_the_set_point_note_export_said(bdir, tmp_path, capsys):
    # the synthetic corpus' file names state 100mV and no potential scale is confirmed: export says the record is
    # written without the potential set-point
    _decide_everything(bdir)
    R.build_records(bdir)
    out_dir = tmp_path / "out"
    out = R.export_records(bdir, out_dir, run_portal=_portal("publish"))
    [row] = out["exported"]
    said = [w for w in row["warnings"] if w.startswith("Written without the potential set-point: ")]
    assert said
    [plan] = R.upload_plan(out_dir, "https://portal.invalid")
    assert said[0] in plan["notes"]
    code, text, err = _run(capsys, "bundle", "upload", out_dir, "--dry-run")
    assert code == 0, err
    reply = json.loads(text)
    assert "Written without the potential set-point" in reply["statement"]


# --- 5. one parsed set-point is asked with its scale -------------------------------------------------------------


def test_a_parsed_set_point_is_asked_with_the_missing_scale_in_one_step(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    _answer(b, gid, "confirm")
    w = _warning(b, gid, grouped)  # 100mV, read as 0.1 V; no scale
    assert w["needs"] == SCALE and w["also_needs"] == SETPOINT and w["setpoint_parsed_V"] == 0.1
    assert w["command"] in w["text"] and w["also_command"] in w["text"]
    assert "--decision confirm" in w["also_command"] and "0.1 V" in w["text"] and "no second question follows" in w["text"]
    minimum = Q.minimum_answers_for_one_group(Q.consolidate(b), b, scope=f"group:{gid}")
    assert SETPOINT in {f for r in minimum["recommended"] for f in r["fields"]}


def test_after_the_scale_only_the_parsed_set_point_is_left(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    _answer(b, gid, "confirm")
    from test_local_import_polish_c3q import _miss

    _answer(b, _miss(b, SCALE, "run-001"), "correct", "RHE")
    w = _warning(b, gid, grouped)
    assert w["needs"] == SETPOINT and "also_needs" not in w and "setpoint_parsed_V" not in w


# --- 6. set_role ----------------------------------------------------------------------------------------------------


def test_set_role_sets_what_a_group_is_and_the_cell_wording_follows_it(grouped, capsys):
    b = M.load(grouped)
    gid = Q.live_groups(b)[0]["group_id"]
    cell = sorted(M.CELL_FIELDS)[0]
    assert M.misfit_groups(b, cell, [gid]) == []  # a sample group
    code, out, err = _decide(capsys, grouped, "--target", gid, "--decision", "set_role", "--value", "reference")
    assert code == 0, err
    assert "role 'reference' recorded" in json.loads(out)["statement"]
    b = M.load(grouped)
    g = next(x for x in b["record_groups"] if x["group_id"] == gid)
    assert g["role"] == "reference" and g["role_basis"]["basis"] == "scientist_decision"
    assert g["status"] == "proposed"  # no status moves
    [mis] = M.misfit_groups(b, cell, [gid])
    assert mis["why"].startswith("a reference group: a standard or reference foil") and "set_role --value sample" in mis["why"]
    code, _, err = _decide(capsys, grouped, "--target", gid, "--decision", "set_role", "--value", "alignment")
    assert code == 0, err
    [mis] = M.misfit_groups(M.load(grouped), cell, [gid])
    assert mis["why"].startswith("an alignment group: an alignment or calibration scan")
    code, _, err = _decide(capsys, grouped, "--target", gid, "--decision", "set_role", "--value", "sample")
    assert code == 0, err
    b = M.load(grouped)
    assert next(x for x in b["record_groups"] if x["group_id"] == gid)["role"] == "sample"
    assert M.misfit_groups(b, cell, [gid]) == [] and B.validate_bundle(b) == []


def test_set_role_refuses_another_word_and_another_target(grouped, capsys):
    b = M.load(grouped)
    gid = Q.live_groups(b)[0]["group_id"]
    before = (grouped / "bundle.json").read_bytes()
    code, _, err = _decide(capsys, grouped, "--target", gid, "--decision", "set_role", "--value", "standard")
    assert code == 2 and "set_role needs --value sample, reference or alignment" in err and "Nothing was recorded" in err
    code, _, err = _decide(capsys, grouped, "--target", "experiment", "--decision", "set_role", "--value", "sample")
    assert code == 2
    assert (grouped / "bundle.json").read_bytes() == before
    # a forged value in the stored log is refused by the validator
    b = M.load(grouped)
    M.record_decision(b, target_ids=[gid], decision="set_role", value="sample", by=WHO, orcid=None)
    b["scientist_decisions"][-1]["value"] = "standard"
    assert any("set_role needs --value" in e for e in B.validate_bundle(B.apply_derivations(b)))


def test_set_role_keeps_the_proposed_basis_beside_the_decision(grouped, capsys):
    b = M.load(grouped)
    g = Q.live_groups(b)[0]
    proposed_role, proposed_basis = g["role"], g["role_basis"]
    for value in ("reference", "alignment"):
        assert _decide(capsys, grouped, "--target", g["group_id"], "--decision", "set_role", "--value", value)[0] == 0
        basis = next(x for x in M.load(grouped)["record_groups"] if x["group_id"] == g["group_id"])["role_basis"]
        assert basis["basis"] == "scientist_decision" and basis["proposed_role"] == proposed_role
        assert basis["proposed_basis"] == proposed_basis


def test_a_role_is_carried_onto_regrouped_groups_whose_runs_all_come_from_the_decided_group(grouped, capsys):
    b = M.load(grouped)
    g1, g2, g3 = [g["group_id"] for g in Q.live_groups(b)][:3]
    k = {g["group_id"]: g["member_run_keys"][0] for g in b["record_groups"]}
    M.record_decision(b, target_ids=[g1], decision="set_role", value="reference", by=WHO, orcid=None)
    # g1 retired by a regroup into what it held (its run and g2's), then split into one group per run; a third group
    # holds g1's run and another one (a merge): it is not all from g1, so it keeps its own role
    old = next(g for g in b["record_groups"] if g["group_id"] == g1)
    b["record_groups"].remove(old)
    b["superseded_record_groups"] = [{**old, "member_run_keys": [k[g1], k[g2]]}]
    merged = {**next(g for g in b["record_groups"] if g["group_id"] == g3), "group_id": "rg-zz-merged",
              "member_run_keys": [k[g1], k[g3]]}
    b["record_groups"].append(merged)
    B.apply_derivations(b)
    part = next(g for g in b["record_groups"] if g["group_id"] == g2)
    assert part["role"] == "reference" and part["role_basis"]["carried_from_group"] == g1
    assert part["role_basis"]["proposed_role"] == "sample"
    assert next(g for g in b["record_groups"] if g["group_id"] == "rg-zz-merged")["role"] == "sample"


def test_a_role_survives_a_regroup(grouped, capsys):
    b = M.load(grouped)
    g = Q.live_groups(b)[0]
    assert _decide(capsys, grouped, "--target", g["group_id"], "--decision", "set_role", "--value", "reference")[0] == 0
    M.group(grouped, regroup=True)
    after = M.load(grouped)
    [same] = [x for x in Q.live_groups(after) if x["member_run_keys"] == g["member_run_keys"]]
    assert same["role"] == "reference" and B.validate_bundle(after) == []


def test_a_name_proposed_role_says_how_to_make_it_a_sample():
    from isaac_api.local_import import grouping as G

    assert "--decision set_role --value sample" in G.NAME_ROLE_NOTE


# --- 9. a fingerprint-only BL15-2 reading asks the beamline question ---------------------------------------------------


def _protocol_gaps():
    import test_local_import_processing_protocol_gaps as PG

    return PG


def test_a_bl15_2_reading_from_the_fingerprint_alone_asks_the_beamline_question(tmp_path):
    PG = _protocol_gaps()
    from isaac_api.local_import.processing import channels as CH

    texts = [PG.herfd(160, absev=False, account="specadm"), PG.herfd(161, 0.2, absev=False, account="specadm")]
    bdir, root, _ = PG._case(tmp_path, [("01_SYN_ZZ1", texts)], bl15=True)
    r = PG.T.isaac(PG.T.run_process(bdir, source_root=root))
    said = r["qc"]["statements"][CH.BL15_2_ENERGY_MISSING_FLAG]
    assert "a person checks the file" in said  # if it IS BL15-2
    assert "answer" in said.lower() and "beamline question" in said and "isaac bundle" in said and "re-process" in said


def test_a_scientist_confirmed_bl15_2_is_not_asked_again(tmp_path):
    PG = _protocol_gaps()
    from isaac_api.local_import.processing import channels as CH

    texts = [PG.herfd(170), PG.herfd(171, 0.2, absev=False)]
    bdir, root, _ = PG._case(tmp_path, [("01_SYN_ZZ1", texts)], confirmed="BL15-2")
    r = PG.T.isaac(PG.T.run_process(bdir, source_root=root))
    said = r["qc"]["statements"][CH.BL15_2_ENERGY_MISSING_FLAG]
    assert said.endswith("a person checks the file.") and "beamline question" not in said


def test_an_unconfirmed_beamline_names_the_command(tmp_path):
    PG = _protocol_gaps()
    from isaac_api.local_import.processing import channels as CH

    texts = [PG.herfd(180, absev=False, account="specadm"), PG.herfd(181, 0.2, absev=False, account="specadm")]
    bdir, root, _ = PG._case(tmp_path, [("01_SYN_ZZ1", texts)], bl15=True, label="SYN_BL6-2_2099")
    r = PG.T.isaac(PG.T.run_process(bdir, source_root=root))
    said = r["qc"]["statements"][CH.BL15_2_BEAMLINE_UNCONFIRMED_FLAG]
    assert "Answer the beamline question: isaac bundle" in said


# --- 10. the schema drift note is pinned (test_local_import_audit_round2) ; 12. a slow trend is no dose question ------


@pytest.mark.parametrize("slope", [0.01, 0.02, 0.03, 0.05, 0.15])
def test_a_global_trend_is_never_a_dose_decision_or_question(tmp_path, monkeypatch, slope):
    """A white line that changes scan after scan across the whole run, spots included: the sample's evolution (the
    stability rule says it), never beam damage, never a settling first scan (before: 0.03 dropped every first scan as
    settling) and never a dose question."""
    import test_local_import_engine_xas as EXT
    from isaac_api.local_import.processing import engine_xas as EX

    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")
    bdir, _ = EXT.imported(tmp_path, EXT._dose_run(lambda j, k: 3.0 - slope * k))
    r = EXT.by_run(EXT.v1_results(bdir), "02_SYN_ZZ2")
    # isaac.xas.v1 1.1.0 (N6): a judged check that found nothing, or the sample's own trend, SAYS so; it decides nothing
    assert EXT._dose(r).get("outcome") in (EX.DOSE_NO_CHANGE, EX.DOSE_EVOLUTION), EXT._dose(r)
    assert EXT._dose(r)["statement"]                    # always one line, never silent
    assert EX.DOSE_QUESTION_FLAG not in r["review_flags"]
    codes = {y["code"] for x in r[EX.DECISIONS_KEY]["rows"] for y in x["reasons"]}
    assert not codes & {EX.DOSE_CODE, EX.SETTLING_CODE}


def _dose_of(tmp_path, monkeypatch, wl):
    import test_local_import_engine_xas as EXT

    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")
    bdir, _ = EXT.imported(tmp_path, EXT._dose_run(wl))
    return EXT._dose(EXT.by_run(EXT.v1_results(bdir), "02_SYN_ZZ2"))


@pytest.mark.parametrize("case,wl,outcomes", [
    # review of PR #335: a within-spot change that resets at every fresh spot is never silent
    ("slow_damage_0.02", lambda j, k: 3.0 - 0.02 * j, {"question", "beam_damage"}),
    ("damage_0.04", lambda j, k: 3.0 - 0.04 * j, {"beam_damage"}),
    ("damage_0.3", lambda j, k: 3.0 - 0.3 * j, {"beam_damage"}),
    ("trend_plus_damage", lambda j, k: 3.0 - 0.02 * k - 0.3 * j, {"question", "beam_damage"}),
    ("settling", lambda j, k: 2.5 if j == 0 else 3.0, {"first_scan_settling"}),
    ("rise", lambda j, k: 3.0 + 0.3 * j, {"question"}),
    ("offset_only_spots", lambda j, k: 3.0 + 0.15 * (k // 3), {"no_change_at_judged_spots"}),   # 1.1.0: said
])
def test_the_dose_rule_still_sees_every_within_spot_change(tmp_path, monkeypatch, case, wl, outcomes):
    d = _dose_of(tmp_path, monkeypatch, wl)
    assert d.get("outcome") in outcomes, (case, d.get("outcome"), d.get("why"))


def test_a_very_slow_trend_within_each_spot_raises_no_dose_question(tmp_path, monkeypatch):
    """0.02 per scan across the whole run: no scan-to-scan step is a change (each is under the rule's floor), so the
    spots are not 'mixed' and no beam-damage question is asked (before: a question at every spot)."""
    import test_local_import_engine_xas as EXT
    from isaac_api.local_import.processing import engine_xas as EX

    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")  # the engine the dose rule belongs to (as its own tests)
    bdir, _ = EXT.imported(tmp_path, EXT._dose_run(lambda j, k: 3.0 - 0.02 * k))
    r = EXT.by_run(EXT.v1_results(bdir), "02_SYN_ZZ2")
    # isaac.xas.v1 1.1.0 (N6): a judged check that found nothing, or the sample's own trend, SAYS so; it decides nothing
    assert EXT._dose(r).get("outcome") in (EX.DOSE_NO_CHANGE, EX.DOSE_EVOLUTION), EXT._dose(r)
    assert EXT._dose(r)["statement"]                    # always one line, never silent
    assert EX.DOSE_QUESTION_FLAG not in r["review_flags"]
