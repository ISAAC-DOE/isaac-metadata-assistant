"""Audit of 18 Nov 2026, finding 4 (code half): the beamtime-wide dose-reading question (rule
``isaac.xas.dose_damage.v3``; its id was first minted under v2 and is kept) is ONE experiment-scope question of ``bundle questions``, with the processing plots in
its context, instead of being discovered when a bulk approval is refused. SYNTHETIC scans only (``SYN_`` files).
"""

from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy", reason="the processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="the processing tests need the optional `processing` extra (xraylarch)")
pytest.importorskip("scipy", reason="the xas-analysis engine needs scipy")
pytest.importorskip("yaml", reason="the xas-analysis engine needs pyyaml")

import test_local_import_engine_xas as T  # noqa: E402
from isaac_api.local_import import cli  # noqa: E402
from isaac_api.local_import import mutations as M  # noqa: E402
from isaac_api.local_import import question_context as QC  # noqa: E402
from isaac_api.local_import import questions as Q  # noqa: E402
from isaac_api.local_import.processing import engine_xas as EX  # noqa: E402

BY = {"by": "SYN Scientist", "orcid": None}


@pytest.fixture()
def two_groups(tmp_path, monkeypatch):
    """A SYN reference and TWO sample groups whose white line falls after the first scan at each spot, two scans per
    spot: the rule cannot tell damage from a settling first scan, so each result carries the open question."""
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")
    runs = T._dose_run(lambda j: 3.0 if j == 0 else 2.55, per_spot=2)
    stem, hour, cols, sz = runs[-1]
    runs = [*runs, ("03_SYN_ZZ3_060mV", hour + 2, cols, sz)]
    bdir, root = T.imported(tmp_path, runs)
    return bdir, root


def _flagged(bdir):
    return [r for r in T.v1_results(bdir) if EX.DOSE_QUESTION_FLAG in r["review_flags"]]


def test_the_dose_reading_is_one_experiment_question_with_its_plots(two_groups, capsys):
    bdir, _ = two_groups
    flagged = _flagged(bdir)
    assert len(flagged) == 2
    payload = Q.consolidate(M.load(bdir))
    asked = [q for q in payload["questions"] if q["kind"] == "dose_reading"]
    assert len(asked) == 1
    q = asked[0]
    assert q["question_id"] == Q.DOSE_QUESTION_ID and q["scope"] == "experiment" and q["rule_id"] == EX.DOSE_RULE_ID
    assert sorted(q["group_ids"]) == sorted(r["group_id"] for r in flagged) and q["applies_to"]["groups"] == 2
    assert q["allowed_decisions"] == ["set_dose_reading"] and q["allowed_values"] == list(EX_READINGS)
    assert "beam damage" in q["text"] and "still settling" in q["text"] and "bulk approval refuses" in q["text"]
    assert q["hints"] and "spots measured more than once" in q["hints"][0]["literal"]
    assert "isaac bundle decide" not in q["hints"][0]["literal"]            # the observation, not its command
    # the context: the processing plot of each group, and what the rule measured
    [with_context], _ = QC.annotate([q], M.load(bdir), bdir)
    plots = [i for i in with_context["context"] if i["kind"] == "plot"]
    assert len(plots) == 2 and all(i["path"].endswith(".png") and (bdir / i["path"]).is_file() for i in plots)
    assert any(i["kind"] == "values" and "after the first scan" in i["label"] for i in with_context["context"])
    # ...and `bundle questions` lists it (with the context) in the experiment scope
    assert cli.main(["bundle", "questions", str(bdir), "--scope", "experiment", "--limit", "200"]) == 0
    listed = [x for x in json.loads(capsys.readouterr().out)["questions"] if x["kind"] == "dose_reading"]
    assert len(listed) == 1 and [i["kind"] for i in listed[0]["context"]].count("plot") == 2


EX_READINGS = ("beam_damage", "not_beam_damage", "first_scan_settling")


def test_one_answer_through_the_question_decides_every_group_after_processing_again(two_groups, capsys):
    bdir, root = two_groups
    ids = [r["result_id"] for r in _flagged(bdir)]
    with pytest.raises(M.MutationRefused):                                     # what the audit met first
        M.decide(bdir, target_ids=ids, decision="approve", value=None, qc_status="valid", **BY)
    assert cli.main(["bundle", "decide", str(bdir), "--question", Q.DOSE_QUESTION_ID, "--decision", "set_dose_reading",
                     "--value", "beam_damage", "--by", "SYN Scientist"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["recorded"] == ["experiment"]
    assert "2 processing results made before this answer still carry the open question" in said["statement"]
    assert "isaac process" in said["statement"]
    b = M.load(bdir)
    assert not [q for q in Q.consolidate(b)["questions"] if q["kind"] == "dose_reading"]     # answered: not asked
    shown = Q.answered_question(b, Q.DOSE_QUESTION_ID)
    assert shown["status"] == "answered" and shown["current_answers"][0]["value"] == "beam_damage"
    M.process(bdir, source=str(root))
    assert _flagged(bdir) == []
    fresh = [r["result_id"] for r in T.v1_results(bdir) if (r.get("dose_damage") or {}).get("outcome") == "beam_damage"]
    assert len(fresh) == 2
    M.decide(bdir, target_ids=fresh, decision="approve", value=None, qc_status="valid", **BY)   # the bulk approval goes


def test_a_group_with_its_own_reading_is_not_asked_and_no_question_without_an_open_result(two_groups):
    bdir, root = two_groups
    a, b_ = _flagged(bdir)
    M.decide(bdir, target_ids=[a["group_id"]], decision="set_dose_reading", value="first_scan_settling", **BY)
    q = next(q for q in Q.consolidate(M.load(bdir))["questions"] if q["kind"] == "dose_reading")
    assert q["group_ids"] == [b_["group_id"]] and q["question_id"] == Q.DOSE_QUESTION_ID     # the same id
    M.decide(bdir, target_ids=[b_["group_id"]], decision="set_dose_reading", value="beam_damage", **BY)
    assert not [q for q in Q.consolidate(M.load(bdir))["questions"] if q["kind"] == "dose_reading"]
    with pytest.raises(M.MutationRefused) as exc:
        M.decide_question(bdir, question_id=Q.DOSE_QUESTION_ID, decision="confirm", value=None, **BY)
    assert "set_dose_reading" in str(exc.value) or "No open question" in str(exc.value)


def test_the_dose_question_id_does_not_move_with_the_rule_version():
    # first minted under isaac.xas.dose_damage.v2; the rule is now v3 and the question says so, but its id is kept
    assert Q.DOSE_QUESTION_ID == "Q-362a024010"
    assert Q.DOSE_RULE_ID == "isaac.xas.dose_damage.v3"
