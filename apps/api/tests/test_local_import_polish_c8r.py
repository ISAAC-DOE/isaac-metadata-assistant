"""Polish c8-r: review findings on c8-a/b/s. Synthetic only.

What these pin:

* (MED-1) an approval an older build let through for a curve whose QC now fails ``edge_step_implausible``,
  ``no_edge`` or ``post_edge_not_at_1`` is not used: the group is blocked as
  ``approved_result_not_a_usable_spectrum`` (nothing from the result composes), said plainly with the way to
  withdraw it (reject / needs_changes and re-process / reject the group); export refuses it.
* (MED-2) the minimum never says "approve its processing result" for a group whose only undecided result is not a
  usable spectrum: it says why and the real steps, and such a group is never the nearest while another exists.
* (MED-3) a file name and a scan header that write different numbers are said to DISAGREE only when both carry the
  same scale (or both none); a name with no scale and a header writing RHE may be one potential on two scales, and
  the warning says to ask which applies.
* (LOW-4) a scan-header token is a potential only with a scale written onto it or a size a potential can have
  (|V| <= 3, not in brackets): ``800V``, ``1500V``, ``12V``, ``5v``, ``(1.2V)`` are not; a file name's whole-token
  match is unchanged.
* (LOW-8) the header's scale keeps its own spelling (``Hg/HgO``, ``Ag/AgCl``).
* (LOW-5) ``defer`` / ``merge`` of a group whose runs another live group now holds (a split group's parts) is refused
  plainly; a re-split into a partition whose part ids already exist says to confirm the rejected part instead.
* (LOW-6) an absorber answered on a group before its split is shown to each part as a hint (never as its answer),
  and a split part is never asked ``confirm_repeats_merge`` (the scientist named its runs).
* (LOW-7) ``defer`` on the experiment takes no ``--value``: only the clock question's own defer carries one.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _add_group, _decide_everything, _portal, bdir, fake_upstream, pristine)
from test_local_import_polish_c8a import SENTENCE, _fail


def _as_an_older_build_approved_it(bdir, reason: str) -> None:
    """Everything decided (p1 approved, valid), then p1's QC said to fail ``reason``: what a bundle an older build
    approved looks like now (``decide`` refuses that approval today)."""
    _decide_everything(bdir)
    b = M.load(bdir)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    p1["qc"] = {"metrics": {}, "verdict": "fail", "reasons": [reason], "statements": {reason: SENTENCE[reason]}}
    M.save_bundle(bdir, b)


# --- MED-1: an older approval of a curve that is not a usable spectrum -------------------------------------------


def test_the_complete_group_exports_before_its_qc_says_otherwise(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    assert len(R.export_records(bdir, tmp_path / "out", run_portal=_portal("publish"))["exported"]) == 1


@pytest.mark.parametrize("reason", ("edge_step_implausible", "no_edge", "post_edge_not_at_1"))
def test_an_older_approval_of_a_curve_that_is_not_a_spectrum_blocks_the_record(bdir, tmp_path, reason):
    _as_an_older_build_approved_it(bdir, reason)
    R.build_records(bdir)
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    assert comp["processing"]["result"] == "p1" and comp["processing"]["unusable_curve"] == reason
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    assert not draft.get("series") and not draft.get("qc") and not draft.get("descriptors_outputs")
    R.validate_records(bdir, run_portal=_portal("publish"))
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    assert report["verdict"] == "incomplete"
    assert report["processing_blocker"] == "approved_result_not_a_usable_spectrum"
    text = " ".join(report["plain_summary"])
    assert f"the approved result p1 is not a usable spectrum: its QC fails {reason}" in text
    assert SENTENCE[reason] in text
    assert "--target p1 --decision reject" in text and "--target p1 --decision needs_changes" in text
    assert "--group g1 --params-file" in text and "--target g1 --decision reject" in text
    assert "approve the new result if its curve is usable" in text
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal("publish"))
    assert out["exported"] == []
    [row] = out["refused"]
    assert row["processing_blocker"] == "approved_result_not_a_usable_spectrum"


def test_withdrawing_that_approval_leaves_the_unusable_result_not_offered(bdir):
    _as_an_older_build_approved_it(bdir, "no_edge")
    M.decide(bdir, target_ids=["p1"], decision="needs_changes", value=None, **BY)
    R.build_records(bdir)
    R.validate_records(bdir, run_portal=_portal("publish"))
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    assert report["processing_blocker"] == "processing_result_not_a_usable_spectrum"


def test_an_ordinary_fail_approved_with_a_stated_status_still_composes(bdir):
    _decide_everything(bdir)
    b = M.load(bdir)
    next(r for r in b["processing_results"] if r["result_id"] == "p1")["qc"] = {
        "metrics": {}, "verdict": "fail", "reasons": ["too_few_points"]}
    M.save_bundle(bdir, b)
    R.build_records(bdir)
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    assert "unusable_curve" not in comp["processing"] and comp["processing"]["series"] == "processing/g1_norm.txt"


# --- MED-2: the minimum with only an unusable result ---------------------------------------------------------------


def _minimum(bdir, scope=None):
    b = M.load(bdir)
    return Q.minimum_answers_for_one_group(Q.consolidate(b), b, scope=scope, bundle_dir=bdir)


def test_the_minimum_never_says_approve_a_curve_that_is_not_a_spectrum(bdir):
    _fail(bdir, ["no_edge"])
    curve = Q._curve(M.load(bdir), "g1")
    assert curve["state"] == "unusable" and curve["result_id"] == "p1" and curve["reasons"] == ["no_edge"]
    m = _minimum(bdir, "group:g1")
    said = json.dumps(m)
    assert "approve its processing result" not in said
    assert "p1 is not offered for approval: its QC fails no_edge, so its curve is not a usable spectrum" in m["blocked"]
    assert "--target p1 --decision reject|needs_changes" in m["blocked"] and "--group g1 --params-file" in m["blocked"]
    assert "--target g1 --decision reject" in m["blocked"]


def test_the_minimum_offers_a_usable_result_beside_an_unusable_one(bdir):
    _fail(bdir, ["no_edge"])
    b = M.load(bdir)
    p2 = json.loads(json.dumps(next(r for r in b["processing_results"] if r["result_id"] == "p1")))
    p2.update(result_id="p2", source="scientist_athena", qc={"metrics": {}, "verdict": "pass", "reasons": []})
    b["processing_results"].insert(0, p2)  # the unusable one is the LATEST: it is still never the one offered
    M.save_bundle(bdir, b)
    curve = Q._curve(M.load(bdir), "g1")
    assert curve["state"] == "curve" and curve["result_id"] == "p2"
    m = _minimum(bdir, "group:g1")
    assert "approve its processing result" in m["plus_decisions"] and "blocked" not in m


def test_an_older_approval_of_an_unusable_curve_is_a_hard_step_saying_withdraw_it(bdir):
    _as_an_older_build_approved_it(bdir, "post_edge_not_at_1")
    curve = Q._curve(M.load(bdir), "g1")
    assert curve["state"] == "unusable" and curve.get("approved") is True
    m = _minimum(bdir, "group:g1")
    assert "approved processing result p1 is not a usable spectrum" in m["blocked"]
    assert "withdraw the approval" in m["blocked"] and "--target p1 --decision reject|needs_changes" in m["blocked"]


def test_a_group_with_only_an_unusable_result_is_never_the_nearest(bdir):
    _fail(bdir, ["edge_step_implausible"])
    b = M.load(bdir)
    # a SECOND group (another run), with no processing result yet: it needs more, but it can be completed
    run = b["runs"][1]
    b["record_groups"].append({"group_id": "g2", "experiment_key": "exp", "member_run_keys": [run["run_key"]],
                               "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
                               "split_reasons": [], "status": "proposed", "questions": []})
    M.save_bundle(bdir, b)
    assert len(M.load(bdir)["runs"]) > 1
    assert _minimum(bdir)["group_id"] not in (None, "g1")


# --- MED-3 / LOW-4 / LOW-8: the stated potential in a scan header ---------------------------------------------------


def _note(stated) -> str:
    return Q.stated_potential_notes({"stated": stated})


def _s(lit, where, scale=None, rid="run-1"):
    return {"literal": lit, "stated_in": where, "runs": [rid], **({"scale": scale} if scale else {})}


def test_a_name_without_a_scale_and_a_header_on_rhe_are_not_said_to_disagree():
    text = _note([_s("m600mV", "file name"), _s("0Vrhe", "scan header", "RHE")])
    assert "DISAGREE" not in text and "disagree" not in text
    assert ("different numbers on possibly different scales for 1 run(s) (run-1: file name m600mV, scan header "
            "0Vrhe; the header writes RHE, the name none): ask which applies") in text


def test_a_name_and_a_header_on_the_same_scale_disagree():
    assert "disagree for 1 run(s) (run-1: file name m600mV, scan header 0V)" in _note(
        [_s("m600mV", "file name"), _s("0V", "scan header")])
    assert "disagree for 1 run(s)" in _note([_s("0.2Vrhe", "file name", "RHE"), _s("0.5Vrhe", "scan header", "RHE")])
    # the same number is no disagreement, whatever the scales
    text = _note([_s("500mV", "file name"), _s("0.5Vrhe", "scan header", "RHE")])
    assert "disagree" not in text and "different numbers" not in text


@pytest.mark.parametrize("tok", ["800V", "1500V", "12V", "5v", "(1.2V)", "-4V", "3500mV"])
def test_a_header_token_that_cannot_be_a_potential_is_not_one(tok):
    assert Q.header_potential(tok) is None


@pytest.mark.parametrize("tok, scale", [
    ("0.5Vrhe", "RHE"), ("-0.6V_RHE", "RHE"), ("500mV", None), ("1.2V", None), ("-3V", None), ("(0.5Vrhe)", "RHE"),
    ("12V_RHE", "RHE"), ("0.1V_vs_Hg/HgO", "Hg/HgO"), ("0.1VHgHgO", "Hg/HgO"), ("0.2Vagagcl", "Ag/AgCl"),
    ("0.2V_Ag/AgCl", "Ag/AgCl"), ("0.3Vsce", "SCE"), ("0.3Vmse", "MSE"), ("0.3Vnhe", "NHE"), ("0.3Vshe", "SHE"),
])
def test_a_header_potential_keeps_its_scales_own_spelling(tok, scale):
    got = Q.header_potential(tok)
    assert got is not None and got["scale"] == scale


def test_a_file_name_keeps_whole_token_matching():
    # file names are read as before: any whole token in the name's own spelling (no magnitude rule there)
    assert R._POTENTIAL_TOKEN.match("1500mV") and R._POTENTIAL_TOKEN.match("m600mV")
    assert not R._POTENTIAL_TOKEN.match("0.5Vrhe")


# --- LOW-5: decisions on a split group whose parts are live, and a re-split -----------------------------------------

from test_local_import_polish_c8s import S02, S03, S04, _live, _part_id, _split, three, three_base  # noqa: E402,F401


@pytest.mark.parametrize("decision", ["defer", "merge"])
def test_defer_or_merge_of_a_split_group_whose_parts_are_live_is_refused_plainly(three, decision):
    [g] = _live(three)
    gid = g["group_id"]
    _split(three, gid, [[S02, S03], [S04]])
    before = (three / "bundle.json").read_bytes()
    other = _live(three)[0]["group_id"]
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(three, target_ids=[gid], decision=decision, value=None, by="SYNTHETIC TEST", orcid=None,
                 merge_with=[other] if decision == "merge" else None)
    said = str(exc.value)
    assert f"The runs of {gid} are now in" in said and other in said and "Nothing was recorded" in said
    assert "more than one live group" not in said and "invalid" not in said
    assert (three / "bundle.json").read_bytes() == before


def test_a_resplit_into_parts_that_already_exist_says_to_confirm_the_rejected_part(three):
    [g] = _live(three)
    gid = g["group_id"]
    made = [p["group_id"] for p in _split(three, gid, [[S02, S03], [S04]])["split_into_groups"]]
    M.decide(three, target_ids=made, decision="reject", value=None, by="SYNTHETIC TEST", orcid=None)
    before = (three / "bundle.json").read_bytes()
    with pytest.raises(M.MutationRefused) as exc:
        _split(three, gid, [[S04], [S02, S03]])  # the same partition, the lists in another order
    said = str(exc.value)
    assert "duplicate" not in said and "invalid" not in said and "Nothing was recorded" in said
    assert all(p in said for p in made) and "rejected" in said
    assert any(f"--target {p} --decision confirm" in said for p in made)
    assert (three / "bundle.json").read_bytes() == before
    # a DIFFERENT partition is a new split, as before (checked on a copy)
    import shutil

    other = three.parent / "other"
    shutil.copytree(three, other)
    again = _split(other, gid, [[S02], [S03, S04]])
    assert {p["group_id"] for p in again["split_into_groups"]} == {_part_id(other, gid, [S02]),
                                                                  _part_id(other, gid, [S03, S04])}
    # what it says to do works
    assert M.decide(three, target_ids=[made[0]], decision="confirm", value=None, by="SYNTHETIC TEST",
                    orcid=None)["recorded"] == [made[0]]


# --- LOW-6: what a split part inherits from the group it was split from -----------------------------------------


def test_an_absorber_answered_before_a_split_is_a_hint_for_each_part_and_no_repeats_question(three):
    [g] = _live(three)
    gid = g["group_id"]
    M.decide(three, target_ids=[gid], decision="set_absorber", value=None, by="SYNTHETIC TEST", orcid=None,
             element="Ir", edge="L3")
    made = [p["group_id"] for p in _split(three, gid, [[S02, S03], [S04]])["split_into_groups"]]
    M.group(three, regroup=True)
    b = M.load(three)
    parts = {x["group_id"]: x for x in b["record_groups"] if x["group_id"] in made}
    assert not [q for p in parts.values() for q in p.get("questions") or () if q.get("code") == "confirm_repeats_merge"]
    asked = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert {t["id"] for q in asked for t in q["targets"]} == set(made)  # still asked: a hint is never an answer
    for q in asked:
        [hint] = [h for h in q["hints"] if h["kind"] == "answered_before_split"]
        assert hint["group_id"] == gid and (hint["element"], hint["edge"]) == ("Ir", "L3")
        assert "Ir L3" in q["text"] and gid in q["text"] and "confirm" in q["text"]
    from isaac_api.local_import import suggestions as S

    assert not set(made) & set(S.absorber_decisions(b))


# --- LOW-7: defer on the experiment takes no --value -------------------------------------------------------------

from test_local_import_polish_c8a import _clock_q, clock  # noqa: E402,F401


def test_defer_on_the_experiment_with_a_value_is_refused(clock, capsys):
    before = (clock / "bundle.json").read_bytes()
    for value in (M.CLOCK_ZONE_DEFER_VALUE, "anything"):
        with pytest.raises(M.MutationRefused) as exc:
            M.decide(clock, target_ids=["experiment"], decision="defer", value=value, by="Synthetic Scientist", orcid=None)
        assert "takes no --value" in str(exc.value) and "--question" in str(exc.value)
    code = cli.main(["bundle", "decide", str(clock), "--target", "experiment", "--decision", "defer", "--value",
                     "clock_time_zone", "--by", "Synthetic Scientist"])
    assert code == 2 and "takes no --value" in capsys.readouterr().err
    assert (clock / "bundle.json").read_bytes() == before


def test_the_clock_question_defer_refuses_a_value_and_records_its_own(clock):
    q = _clock_q(clock)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide_question(clock, question_id=q["question_id"], decision="defer", value="Europe/Berlin",
                          by="Synthetic Scientist", orcid=None)
    assert "takes no --value" in str(exc.value)
    out = M.decide_question(clock, question_id=q["question_id"], decision="defer", value=None,
                            by="Synthetic Scientist", orcid=None)
    assert out["recorded"] == ["experiment"] and M.clock_zone_deferral(M.load(clock)) is not None


def test_the_counter_question_defer_refuses_a_value(three):
    b = M.load(three)
    qs = [q for q in Q.consolidate(b, include_answered=True, explain_counter=False)["questions"]
          if q["kind"] == "naming_counter_positions"]
    if not qs:
        pytest.skip("no counter question in this fixture")
    with pytest.raises(M.MutationRefused) as exc:
        M.decide_question(three, question_id=qs[0]["question_id"], decision="defer", value=M.CLOCK_ZONE_DEFER_VALUE,
                          by="SYNTHETIC TEST", orcid=None)
    assert "takes no --value" in str(exc.value)
    assert M.clock_zone_deferral(M.load(three)) is None
