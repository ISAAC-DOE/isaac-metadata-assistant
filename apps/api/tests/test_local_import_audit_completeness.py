"""Audit of 18 Nov 2026, finding 1: a record must not count as ready without the conditions that make it that
record. SYNTHETIC data only (``SYN_`` files, the invented sample ``ZZ1``).

The local completeness gate (``completeness.py``, ``isaac.local.record_completeness.v1``):

* a condition grouping used to keep two records of one sample apart must be in the record, or declined by the
  scientist, before ``export`` writes it; two records that would say the same thing are held too;
  ``--allow-indistinguishable`` writes them anyway;
* official validation is untouched: a held record's verdict is still ``exportable``;
* the questions that fill such a condition are their own tier in ``bundle questions``, after the blocking ones and
  before the optional ones; no existing question id changes;
* ONE beamtime-wide question asks the potential scale, and reaches only the groups whose names state a potential.
"""

from __future__ import annotations

import json
import re
import shutil

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import completeness as CP
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_final_review import _portal
from tests_support_records import BY, fake_upstream_env  # noqa: F401

SETPOINT, SCALE = CP.SETPOINT_PATH, CP.SCALE_PATH


# --- the catch-all: records that say the same thing (no processing extra needed) ---------------------------------


@pytest.fixture(scope="module", autouse=True)
def _name_deductions_off():
    """1.22.0 (DEC-100 fix round): this module's subject is not the set-point or control-mode deductions from a run's
    file name, and its synthetic runs were written for set-points that are asked: the two deductions are switched off
    here (``tests_support_records.without_name_deductions``; the rules are pinned in ``test_local_import_guesses``)."""
    from tests_support_records import without_name_deductions

    with without_name_deductions():
        yield


def _draft(**fields):
    return {"fields": {k: {"value": v} for k, v in fields.items()}}


def test_records_that_say_the_same_thing_are_one_set_whatever_their_curve_ids_or_times():
    same = {"sample.material.name": "ZZ1 synthetic", "system.technique": "HERFD-XAS", "context.environment": "in_situ"}
    drafts = [("g1", _draft(**same, **{"timestamps.acquired_start_utc": "2025-01-01T00:00:00Z"})),
              ("g2", _draft(**same, **{"timestamps.acquired_start_utc": "2025-01-02T00:00:00Z"})),
              ("g3", _draft(**same, **{SETPOINT: 0.06, SCALE: "RHE"}))]
    assert CP.identical_sets({}, drafts) == [["g1", "g2"]]


def test_groups_a_scientist_kept_apart_are_declared_repeats_and_never_a_set():
    same = {"sample.material.name": "ZZ1 synthetic"}
    bundle = {"merge_candidates": [{"merge_candidate_id": "mc-1", "group_ids": ["g1", "g2"]}],
              "scientist_decisions": [{"decision_id": "d-1", "target": {"kind": "merge_candidate", "id": "mc-1"},
                                       "decision": "keep_apart"}]}
    drafts = [("g1", _draft(**same)), ("g2", _draft(**same))]
    assert CP.identical_sets(bundle, drafts) == []
    assert CP.identical_sets({}, drafts) == [["g1", "g2"]]


def test_a_condition_only_the_other_group_states_is_not_this_groups():
    group = {"group_id": "g-ocv", "basis": {"conditions": {"filter": {"value": "10"}}},
             "split_reasons": [{"code": "conditions_differ", "other_group_id": "g-060",
                                "differences": [{"condition": "potential_magnitude", "key_class": "condition",
                                                 "kind": "unknown_vs_known", "this": None, "other": 0.06}]}]}
    assert CP.distinguishing_conditions(group, ["g-ocv", "g-060"]) == {}
    held = {"group_id": "g-060", "basis": {"conditions": {"potential_magnitude": {"value": 0.06}}},
            "split_reasons": [{"code": "conditions_differ", "other_group_id": "g-ocv",
                               "differences": [{"condition": "potential_magnitude", "key_class": "condition",
                                                "kind": "unknown_vs_known", "this": 0.06, "other": None}]}]}
    assert list(CP.distinguishing_conditions(held, ["g-ocv", "g-060"])) == ["potential_magnitude"]
    assert CP.distinguishing_conditions(held, ["g-060"]) == {}      # the other group is no longer live


def _specimen(gid, number, **extra):
    return {"group_id": gid, "split_reasons": extra.pop("split_reasons", []),
            "basis": {"sample": {"sample_name": {"value": "zz1"}, "sample_or_electrode_number": {"value": number}},
                      "conditions": extra}}


def test_two_specimens_of_one_material_are_told_apart_by_which_specimen_it_is():
    """Grouping keeps electrode 02 and electrode 03 of one material apart as different samples and never compares
    their conditions: without the sample id their records say the same thing."""
    a, b, other = _specimen("g-02", "02"), _specimen("g-03", "03"), _specimen("g-x", "02")
    other["basis"]["sample"]["sample_name"]["value"] = "zz9"
    live = ["g-02", "g-03", "g-x"]
    found = CP.distinguishing_conditions(a, live, [a, b, other])
    assert list(found) == ["sample_or_electrode_number"] and found["sample_or_electrode_number"]["others"] == 1
    assert CP.distinguishing_conditions(other, live, [a, b, other]) == {}   # the only group of its material
    assert CP.distinguishing_conditions(a, live) == {}                        # without the peers: split reasons only


def test_a_condition_the_groups_own_files_read_two_ways_must_be_said_when_another_record_shares_its_material():
    care = [{"code": "conflicting_condition", "condition": "filter", "readings": ["10", "20"]}]
    a = _specimen("g-a", "02", filter={"kind": "conflicting", "value": None}, split_reasons=care)
    b = _specimen("g-b", "02")
    found = CP.distinguishing_conditions(a, ["g-a", "g-b"], [a, b])
    assert found["filter"]["own_files_disagree"] is True and found["filter"]["value"] == {"its files read": ["10", "20"]}
    assert CP.distinguishing_conditions(a, ["g-a"], [a]) == {}                # alone in its material: nothing to tell apart


# --- end to end on SYN scans ------------------------------------------------------------------------------------

np = pytest.importorskip("numpy", reason="the processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="the processing tests need the optional `processing` extra (xraylarch)")
pytest.importorskip("scipy", reason="the xas-analysis engine needs scipy")
pytest.importorskip("yaml", reason="the xas-analysis engine needs pyyaml")

import test_local_import_engine_xas as T  # noqa: E402



VALUES = {"attribution.produced_by.group": "Synthetic group", "attribution.produced_by.organization": "Synthetic University",
          "context.environment": "in_situ", "sample.sample_form": "powder", "system.domain": "experimental",
          "system.technique": "HERFD-XAS", "sample.material.name": "ZZ1 synthetic"}


def answer_required(bdir):
    """Answer every blocking question with an invented value (the scientist's part of the minimum)."""
    for _ in range(60):
        open_ = [q for q in Q.consolidate(M.load(bdir))["questions"] if q["blocking"] and q.get("target_field_path") in VALUES]
        if not open_:
            return
        q = open_[0]
        M.decide_question(bdir, question_id=q["question_id"], decision="correct", value=VALUES[q["target_field_path"]], **BY)
    raise AssertionError("blocking questions never ran out")


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    """Three SYN groups of one sample: held at 60 mV, at 120 mV, and one whose name states no potential. Imported,
    grouped, processed, every blocking question answered, groups confirmed, curves approved: what the audit called
    "the minimum"."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PROCESSING_ENGINE", "v1")
        tmp = tmp_path_factory.mktemp("completeness")
        runs = [("01_SYN_ZZ1_base_060mV", 9, [T.scan_cols(10 + k) for k in range(4)]),
                ("02_SYN_ZZ1_base_120mV", 10, [T.scan_cols(40 + k) for k in range(4)]),
                # no OCV token: since 1.16.0 an OCV name suggests the control mode open_circuit, a condition that
                # keeps this group apart of its own (isaac.suggest.name_open_circuit.v1); this group states none
                ("03_SYN_ZZ1_base", 11, [T.scan_cols(60 + k) for k in range(4)])]
        root = tmp / "SYN_beamtime"
        T.write_beamtime(root, runs)
        out = tmp / "out"
        assert cli.main(["import", str(root), "--out", str(out)]) == 0
        M.group(out)
        M.process(out, source=str(root))
        answer_required(out)
        b = M.load(out)
        M.decide(out, target_ids=[g["group_id"] for g in b["record_groups"]], decision="confirm", value=None, **BY)
        M.decide(out, target_ids=[r["result_id"] for r in b["processing_results"]], decision="approve", value=None,
                 qc_status="valid", **BY)
        return out


@pytest.fixture()
def bdir(pristine, tmp_path):
    target = tmp_path / "b"
    shutil.copytree(pristine, target)
    return target


def _group_of(bdir, stem_prefix):
    b = M.load(bdir)
    key = next(r["run_key"] for r in b["runs"] if r["stem"].startswith(stem_prefix))
    return next(g["group_id"] for g in b["record_groups"] if key in g["member_run_keys"])


def _setpoint_question(payload, gid):
    return next(q for q in payload["questions"] if q.get("target_field_path") == SETPOINT and q["scope"] == f"group:{gid}")


def test_the_questions_that_fill_a_distinguishing_condition_are_their_own_tier(bdir, monkeypatch):
    payload = Q.consolidate(M.load(bdir))
    qs = [q for q in payload["questions"] if not q.get("informational")]
    marked = [q for q in qs if q.get("completeness")]
    g060, g120, gocv = (_group_of(bdir, p) for p in ("01_", "02_", "03_"))
    # the beamtime-wide scale question and each potential-stating group's own set-point and scale questions
    assert {q["question_id"] for q in marked} >= {Q.potential_scale_question_id(),
                                                  _setpoint_question(payload, g060)["question_id"],
                                                  _setpoint_question(payload, g120)["question_id"]}
    assert all(q["completeness"]["gate"] == CP.GATE_ID and q["completeness"]["tier"] == "distinguishing" for q in marked)
    assert all(gocv not in q["completeness"]["group_ids"] for q in marked)   # its name states no potential
    # after the blocking ones, before every other question; the tier NUMBER of no question changed
    kinds = ["blocking" if q["blocking"] else "distinguishing" if q.get("completeness") else "rest" for q in qs]
    assert kinds == sorted(kinds, key=["blocking", "distinguishing", "rest"].index)
    assert all(q["tier"] in (Q.TIER_BLOCKING, Q.TIER_CONFLICT, Q.TIER_OPTIONAL) for q in qs)
    assert payload["counts"]["distinguishing"] == len([q for q in marked if not q["blocking"]])
    assert payload["record_completeness"]["held"] == 2 and payload["record_completeness"]["open_conditions"] == {
        "potential_magnitude": 2}
    # no existing question changed: without the new question and the marking, the same ids, tiers and texts
    monkeypatch.setattr(Q, "_potential_scale_question", lambda *a, **k: None)
    monkeypatch.setattr(CP, "mark_questions", lambda *a, **k: None)
    before = {q["question_id"]: (q["tier"], q["text"], q["scope"]) for q in Q.consolidate(M.load(bdir))["questions"]}
    after = {q["question_id"]: (q["tier"], q["text"], q["scope"]) for q in payload["questions"]
             if q["question_id"] != Q.potential_scale_question_id()}
    assert before == after


def test_one_beamtime_question_asks_the_potential_scale_of_the_groups_that_state_a_potential(bdir, capsys):
    payload = Q.consolidate(M.load(bdir))
    q = Q.question(payload, Q.potential_scale_question_id())
    g060, g120, gocv = (_group_of(bdir, p) for p in ("01_", "02_", "03_"))
    assert q["scope"] == "experiment" and q["kind"] == "missing_value" and q["target_field_path"] == SCALE
    assert set(q["per_scope_targets"]) == {f"group:{g060}", f"group:{g120}"}       # never the group whose name states none
    assert q["applies_to"]["groups"] == 2 and q["applies_to"]["groups_not_reached"] == 1
    assert "confirm" not in q["allowed_decisions"] and q["hints"] == []            # nothing is suggested: no file states it
    assert "RHE" in q["allowed_values"] and "01_SYN_ZZ1_base_060mV" in q["text"]
    # one answer, through the CLI, is recorded for exactly those groups' runs
    assert cli.main(["bundle", "decide", str(bdir), "--question", q["question_id"], "--decision", "correct",
                     "--value", "RHE", "--by", "SYN Scientist"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert len(said["recorded"]) == 2
    b = M.load(bdir)
    by_id = {m["value_id"]: m for m in b["missing_values"]}
    runs = {by_id[d["target"]["id"]]["run_id"] for d in b["scientist_decisions"]
            if d["target"]["kind"] == "missing_value" and d["value"] == "RHE"}
    stems = {r["stem"] for r in b["runs"] if r["run_id"] in runs}
    assert stems == {"01_SYN_ZZ1_base_060mV", "02_SYN_ZZ1_base_120mV"}
    payload = Q.consolidate(b)
    assert Q.question(payload, Q.potential_scale_question_id()) is None             # answered: no longer asked
    still = [q for q in payload["questions"] if q["kind"] == "optional_values" and SCALE in (q.get("fields") or {})]
    assert [q["scope"] for q in still] == [f"group:{gocv}"]                         # only the group it never reached


def test_bundle_questions_lists_the_tier_after_the_blocking_questions(bdir, capsys):
    assert cli.main(["bundle", "questions", str(bdir), "--no-context", "--limit", "200"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["record_completeness"]["gate"] == CP.GATE_ID and said["counts"]["distinguishing"] >= 3
    first = [q for q in said["questions"] if not q["blocking"]][0]
    assert first["completeness"]["tier"] == "distinguishing" and "group_ids" not in first["completeness"]
    assert cli.main(["bundle", "questions", str(bdir), "--no-context", "--distinguishing-only"]) == 0
    only = json.loads(capsys.readouterr().out)
    assert only["total"] == said["counts"]["distinguishing"] and all(q["completeness"] for q in only["questions"])


def test_the_scale_question_can_be_answered_for_some_groups_only(bdir):
    g060 = _group_of(bdir, "01_")
    M.decide_question(bdir, question_id=Q.potential_scale_question_id(), only=f"group:{g060}", decision="correct",
                      value="Ag/AgCl", **BY)
    b = M.load(bdir)
    assert len([d for d in b["scientist_decisions"] if d["value"] == "Ag/AgCl"]) == 1
    # inverted at 1.22.0 (DEC-100 fix round, DEC-91 id stability now that the scale can block): the beamtime question
    # KEEPS its id while a group it reaches is open, and asks only that one now
    g120 = _group_of(bdir, "02_")
    q = Q.question(Q.consolidate(b), Q.potential_scale_question_id())
    assert q is not None and set(q["per_scope_targets"]) == {f"group:{g120}"}


def test_official_validation_is_untouched_and_the_local_gate_holds_the_records(bdir, tmp_path, fake_upstream_env):
    v = R.validate_records(bdir, run_portal=_portal())
    assert v["exportable"] == 3 and set(v["verdicts"].values()) == {"exportable"}   # official validation: unchanged
    rc = v["record_completeness"]
    assert v["ready_to_export"] == 0 and rc["gate"] == CP.GATE_ID and rc["held"] == 3
    assert rc["open_conditions"] == {"potential_magnitude": 2} and rc["indistinguishable_sets_total"] == 1
    # the scale once (it also tells the third record, which states no potential, apart from the two that do), and
    # each potential-stating group's own set-point
    assert rc["answer_first"][0] == {"question_id": Q.potential_scale_question_id(), "records": 3}
    assert rc["answers_needed"] == 3
    g060, gocv = _group_of(bdir, "01_"), _group_of(bdir, "03_")
    report = json.loads((bdir / "validation" / f"{g060}.json").read_text())
    assert report["verdict"] == "exportable" and report["record_completeness"]["ready"] is False
    [row] = report["record_completeness"]["conditions"]
    assert row["condition"] == "potential_magnitude" and row["state"] == "open" and row["paths"] == [SETPOINT]
    # no condition of its own is open, and export holds it all the same: it says what another record says (finding 7)
    ocv = json.loads((bdir / "validation" / f"{gocv}.json").read_text())["record_completeness"]
    assert ocv["conditions"] == [] and ocv["ready"] is False and ocv["held_by"] == [CP.HELD_IDENTICAL]

    out = R.export_records(bdir, tmp_path / "records", run_portal=_portal())
    assert out["exported"] == [] and not (tmp_path / "records").exists()
    assert out["records_held_by_completeness"] == 3 and len(out["refused"]) == 3
    for row in out["refused"]:
        assert row["verdict"] == R.HELD_VERDICT and row["official_validation"] == "passed"
        assert "these 3 records would be indistinguishable" in row["summary"][0]
        assert "--allow-indistinguishable" in row["summary"][0] and row["answer"]
    held = next(r for r in out["refused"] if r["group_id"] == g060)
    assert CP.HELD_CONDITION in held["held_by"] and "without the potential" in held["summary"][0]
    assert Q.potential_scale_question_id() in held["summary"][0]
    assert "are held" in out["outcome"] and CP.GATE_ID in out["outcome"]


def test_confirming_or_declining_each_condition_makes_every_record_ready(bdir, tmp_path, fake_upstream_env):
    g060, g120 = _group_of(bdir, "01_"), _group_of(bdir, "02_")
    M.decide_question(bdir, question_id=Q.potential_scale_question_id(), decision="correct", value="RHE", **BY)
    payload = Q.consolidate(M.load(bdir))
    M.decide_question(bdir, question_id=_setpoint_question(payload, g060)["question_id"], decision="confirm", value=None, **BY)
    v = R.validate_records(bdir, run_portal=_portal())
    assert v["ready_to_export"] == 2 and v["record_completeness"]["open_conditions"] == {"potential_magnitude": 1}
    # the scientist DECLINES the other potential: left out on purpose, and the record is then ready
    M.decide_question(bdir, question_id=_setpoint_question(payload, g120)["question_id"], decision="reject", value=None, **BY)
    v = R.validate_records(bdir, run_portal=_portal())
    assert v["ready_to_export"] == 3 and v["record_completeness"]["held"] == 0
    rows = json.loads((bdir / "validation" / f"{g120}.json").read_text())["record_completeness"]["conditions"]
    assert [r["state"] for r in rows] == ["declined"]
    assert not [q for q in Q.consolidate(M.load(bdir))["questions"] if q.get("completeness")]
    out = R.export_records(bdir, tmp_path / "records", run_portal=_portal())
    assert out["records_written"] == 3 and out["refused"] == [] and "records_held_by_completeness" not in out
    bodies = set()
    for row in out["exported"]:
        rec = json.loads((tmp_path / "records" / row["record"]).read_text())
        bodies.add(json.dumps({k: rec.get(k) for k in ("sample", "system", "context")}, sort_keys=True))
    assert len(bodies) == 3                                                         # no two records say the same thing
    carried = json.loads((tmp_path / "records" / next(r["record"] for r in out["exported"] if r["group_id"] == g060)).read_text())
    assert carried["context"]["electrochemistry"]["potential_setpoint_V"] == 0.06


def test_declining_the_scale_declines_the_potential_it_goes_with(bdir, fake_upstream_env):
    g060 = _group_of(bdir, "01_")
    M.decide_question(bdir, question_id=Q.potential_scale_question_id(), only=f"group:{g060}", decision="reject",
                      value=None, **BY)
    R.validate_records(bdir, run_portal=_portal())
    rows = json.loads((bdir / "validation" / f"{g060}.json").read_text())["record_completeness"]["conditions"]
    assert [r["state"] for r in rows] == ["declined"]


def test_the_flag_writes_held_records_anyway_and_every_row_says_so(bdir, tmp_path, fake_upstream_env, capsys):
    code = cli.main(["bundle", "export", str(bdir), "--out", str(tmp_path / "records")])
    assert code == 1 and not (tmp_path / "records").exists()
    capsys.readouterr()
    # the scientist's word is needed: the flag alone is refused, and nothing is written
    assert cli.main(["bundle", "export", str(bdir), "--out", str(tmp_path / "records"), "--allow-indistinguishable"]) == 2
    assert "--by" in capsys.readouterr().err and not (tmp_path / "records").exists()
    out = R.export_records(bdir, tmp_path / "records", run_portal=_portal(), allow_indistinguishable=True,
                           by="SYN Scientist")
    assert out["records_written"] == 3 and out["refused"] == [] and out["records_written_although_incomplete"] == 3
    for row in out["exported"]:
        assert row["warnings"][0].startswith("Written although record completeness holds it")
        assert "SYN Scientist" in row["warnings"][0]
    assert "are written although record completeness would hold them: SYN Scientist decided" in out["outcome"]
    # REVIEW OF PR 342, FINDING 5: the decision is in the bundle (who, which groups), so a later plain export keeps
    # the records instead of withdrawing them
    said = [d for d in M.load(bdir)["scientist_decisions"] if d["decision"] == CP.EXPORT_ANYWAY_DECISION]
    assert sorted(d["target"]["id"] for d in said) == sorted(r["group_id"] for r in out["exported"])
    assert {d["decided_by"]["name"] for d in said} == {"SYN Scientist"}
    assert B.validate_bundle(M.load(bdir)) == []
    again = R.export_records(bdir, tmp_path / "records", run_portal=_portal())
    assert again["records_unchanged"] == 3 and again["refused"] == [] and again["withdrawn"] == []
    v = R.validate_records(bdir, run_portal=_portal())
    assert v["ready_to_export"] == 3 and v["record_completeness"]["exported_anyway"] == 3
    # the flag again records nothing new
    R.export_records(bdir, tmp_path / "records", run_portal=_portal(), allow_indistinguishable=True, by="SYN Scientist")
    assert len([d for d in M.load(bdir)["scientist_decisions"] if d["decision"] == CP.EXPORT_ANYWAY_DECISION]) == 3


def test_a_record_whose_body_changed_since_export_anyway_is_held_again_and_its_withdrawal_said(bdir, tmp_path,
                                                                                               fake_upstream_env):
    R.export_records(bdir, tmp_path / "records", run_portal=_portal(), allow_indistinguishable=True, by="SYN Scientist")
    b = M.load(bdir)
    names = [c["candidate_id"] for c in b["candidates"] if c.get("target_field_path") == "sample.material.name"]
    M.decide(bdir, target_ids=names, decision="correct", value="ZZ1 synthetic, renamed", **BY)   # every body changes
    out = R.export_records(bdir, tmp_path / "records", run_portal=_portal())
    assert out["records_ready"] == 0 and len(out["withdrawn"]) == 3
    assert "3 earlier record(s) were withdrawn because record completeness holds them now" in out["outcome"]
    assert "another record body" in out["refused"][0]["summary"][0]


# --- review of PR 342, finding 3: a group held for a condition is told the question that frees it ---------------


@pytest.fixture()
def filter_disagreement(tmp_path):
    """Two SYN groups of one sample at one potential. The second run's NAME says filter20, its first scan header 10
    and its second 20: its group carries the care flag, and the filter is what keeps the two records apart. (Since C6 a
    name alone against recordings that agree is settled by the recorded filter, bl15.resolution.recorded_filter_motor.v1,
    so the run's own recordings disagree here.)"""
    runs = [("01_SYN_ZZ1_filter10_060mV", 9, [T.scan_cols(10 + k) for k in range(2)]),
            ("02_SYN_ZZ1_filter20_060mV", 11, [T.scan_cols(60 + k) for k in range(2)])]
    root = tmp_path / "SYN_beamtime"
    T.write_beamtime(root, runs)
    stem = "02_SYN_ZZ1_filter20_060mV"
    second = root / f"{stem}_dir" / f"{stem}_002.dat"
    second.write_text(second.read_text().replace("filter=10", "filter=20"))
    head, _, rest = (root / stem).read_text().partition("#S 2 ")
    (root / stem).write_text(head + "#S 2 " + rest.replace("filter=10", "filter=20"))
    bdir = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(bdir)]) == 0
    M.group(bdir)
    b = M.load(bdir)
    M.decide(bdir, target_ids=[g["group_id"] for g in b["record_groups"]], decision="confirm", value=None, **BY)
    held = next(g["group_id"] for g in M.load(bdir)["record_groups"]
                if g["member_run_keys"][0].startswith("02_SYN_ZZ1_filter20"))
    return bdir, held


def _reaches(q, gid):
    return f"group:{gid}" in (q.get("per_scope_targets") or {})


def _hold(bdir, gid):
    b = M.load(bdir)
    payload = Q.consolidate(b)
    fresh = R.fresh_compositions(bdir, b)
    holds, _, gate_of = R.completeness_holds(b, fresh, payload, [g for g, _, _ in fresh])
    return payload, holds.get(gid), gate_of[gid]


def test_the_disagreement_that_holds_a_group_is_marked_and_named_and_nothing_that_misses_it_is(filter_disagreement):
    bdir, gid = filter_disagreement
    payload, hold, gate = _hold(bdir, gid)
    [row] = [r for r in gate["conditions"] if r["condition"] == "filter"]
    assert row["state"] == "open" and row["conflict_ids"]
    conflict = next(q for q in payload["questions"] if q["kind"] == "resolve_conflict" and q.get("completeness")
                    and _reaches(q, gid))
    assert conflict["completeness"]["group_ids"] == [gid] and "filter" in conflict["completeness"]["conditions"]
    assert conflict["question_id"] in hold["questions"] and conflict["question_id"] in hold["text"]
    assert "which reading is right" in hold["text"]
    # every question the text names reaches this group
    named = set(re.findall(r"Q-[0-9a-f]{10}", hold["text"]))
    by_id = {q["question_id"]: q for q in payload["questions"]}
    assert named and all(_reaches(by_id[q], gid) for q in named), named
    assert "the question that asks" not in hold["text"]


def test_rejecting_the_disagreement_declines_the_filter_and_frees_the_group(filter_disagreement):
    bdir, gid = filter_disagreement
    payload, _, _ = _hold(bdir, gid)
    conflict = next(q for q in payload["questions"] if q["kind"] == "resolve_conflict" and q.get("completeness"))
    M.decide_question(bdir, question_id=conflict["question_id"], decision="reject", value=None, **BY)
    _, hold, gate = _hold(bdir, gid)
    assert [r["state"] for r in gate["conditions"] if r["condition"] == "filter"] == ["declined"]
    assert hold is None or CP.HELD_CONDITION not in hold["held_by"]


def test_settling_the_disagreement_leads_to_the_label_question_for_this_group(filter_disagreement):
    bdir, gid = filter_disagreement
    payload, _, _ = _hold(bdir, gid)
    conflict = next(q for q in payload["questions"] if q["kind"] == "resolve_conflict" and q.get("completeness"))
    M.decide_question(bdir, question_id=conflict["question_id"], decision="correct", value="filter20", **BY)
    payload, hold, _ = _hold(bdir, gid)
    label = next(q for q in payload["questions"] if q["kind"] == "condition_label" and q.get("label") == "filter")
    assert _reaches(label, gid) and label.get("completeness") and gid in label["completeness"]["group_ids"]
    assert label["question_id"] in hold["text"] and f"--only group:{gid}" in hold["text"]
    M.decide_question(bdir, question_id=label["question_id"], only=f"group:{gid}", decision="confirm", value=None, **BY)
    _, hold, gate = _hold(bdir, gid)
    assert [r["state"] for r in gate["conditions"] if r["condition"] == "filter"] == ["in_record"]


# --- review of PR 342, finding 4: records that differ only in a declined or unrecordable condition --------------


def test_declining_both_potentials_frees_both_records(bdir, fake_upstream_env):
    payload = Q.consolidate(M.load(bdir))
    for gid in (_group_of(bdir, "01_"), _group_of(bdir, "02_")):
        M.decide_question(bdir, question_id=_setpoint_question(payload, gid)["question_id"], decision="reject",
                          value=None, **BY)
    v = R.validate_records(bdir, run_portal=_portal())
    rc = v["record_completeness"]
    assert v["ready_to_export"] == 3 and rc["held"] == 0 and rc["indistinguishable_sets_total"] == 0


def test_a_set_is_split_by_the_conditions_that_were_declined_or_have_no_record_field():
    groups = [{"group_id": g, "basis": {"conditions": {"potential_magnitude": {"value": v}, "emission_energy": {"value": e}}}}
              for g, v, e in (("g1", 0.06, "9175"), ("g2", 0.12, "9175"), ("g3", 0.06, "9175"), ("g4", 0.06, "9176"))]
    bundle = {"record_groups": groups}
    same = {"sample.material.name": "ZZ1 synthetic"}
    drafts = [(g["group_id"], _draft(**same)) for g in groups]
    row = lambda c, st: {"condition": c, "state": st}  # noqa: E731
    gate_of = {g: {"conditions": [row("potential_magnitude", "declined"), row("emission_energy", "no_record_field")]}
               for g in ("g1", "g2", "g3", "g4")}
    # g1 and g3 say the same thing AND agree on everything left out: still one set; g2 and g4 differ in what was left out
    assert CP.identical_sets(bundle, drafts, gate_of) == [["g1", "g3"]]
    assert CP.identical_sets(bundle, drafts) == [["g1", "g2", "g3", "g4"]]   # without the gate: as before


def test_the_keep_apart_advice_is_given_only_when_there_is_a_merge_candidate(bdir, fake_upstream_env, monkeypatch):
    monkeypatch.setattr(CP, "questions_for", lambda payload: {})     # a set no open question tells apart
    b = M.load(bdir)
    assert not b.get("merge_candidates")
    out = R.export_records(bdir, bdir.parent / "records", run_portal=_portal())
    said = [r["summary"][0] for r in out["refused"] if CP.HELD_IDENTICAL in r["held_by"]]
    assert said and all("No open question tells them apart" in t and "keep_apart" not in t for t in said)
    # with a merge candidate over the set, its keep_apart command is offered
    gids = [g["group_id"] for g in b["record_groups"]]
    raw = json.loads((bdir / "bundle.json").read_text())
    raw["merge_candidates"] = [{"merge_candidate_id": "mc-0123456789abcdef", "group_ids": gids}]
    holds, _, _ = R.completeness_holds(raw, R.fresh_compositions(bdir, b), {"questions": []}, gids)
    assert all("--target mc-0123456789abcdef --decision keep_apart" in h["text"] for h in holds.values()
               if CP.HELD_IDENTICAL in h["held_by"])


# --- review of PR 342, finding 7: the Local Imports page never calls a held record exportable ---------------------


def test_each_validation_report_and_the_local_imports_row_say_a_held_record_is_held(bdir, fake_upstream_env):
    from isaac_api import local_bundles as LB

    R.validate_records(bdir, run_portal=_portal())
    b = M.load(bdir)
    gocv = _group_of(bdir, "03_")                                  # held only as indistinguishable from the other two
    report = json.loads((bdir / "validation" / f"{gocv}.json").read_text())
    assert report["verdict"] == "exportable"                       # official validation: unchanged
    rc = report["record_completeness"]
    assert rc["ready"] is False and rc["held_by"] == [CP.HELD_IDENTICAL] and rc["text"].startswith("Held (")
    rows = {r["group_id"]: r for r in LB.progress(bdir, b, {"status": "OK"})["last_validation"]["reports"]}
    assert rows[gocv]["verdict"] == "exportable" and rows[gocv]["export_verdict"] == R.HELD_VERDICT
    assert rows[gocv]["record_completeness"] == {"gate": CP.GATE_ID, "ready": False, "held_by": [CP.HELD_IDENTICAL]}
    # a group the gate does not hold reads as before
    payload = Q.consolidate(b)
    for gid in (_group_of(bdir, "01_"), _group_of(bdir, "02_")):
        M.decide_question(bdir, question_id=_setpoint_question(payload, gid)["question_id"], decision="reject",
                          value=None, **BY)
    R.validate_records(bdir, run_portal=_portal())
    rows = {r["group_id"]: r for r in LB.progress(bdir, M.load(bdir), {"status": "OK"})["last_validation"]["reports"]}
    assert all(r["export_verdict"] == "exportable" and r["record_completeness"]["ready"] for r in rows.values())


# --- review of PR 342, finding 8: export judges identical records among the groups that pass ---------------------


def test_export_holds_identical_records_only_among_the_groups_official_validation_passes(bdir, tmp_path,
                                                                                         fake_upstream_env, monkeypatch):
    g060, g120, gocv = (_group_of(bdir, p) for p in ("01_", "02_", "03_"))
    ocv_runs = set(next(g for g in M.load(bdir)["record_groups"] if g["group_id"] == gocv)["member_run_ids"])
    real = R.validate_draft_file

    def portal_refuses_the_ocv_record(draft, *, run_portal, composition=None):
        report = real(draft, run_portal=run_portal, composition=composition)
        if set((composition or {}).get("member_run_ids") or ()) == ocv_runs:
            report = {**report, "verdict": "portal_reject"}
        return report

    seen = []
    real_holds = R.completeness_holds

    def spy(bundle, fresh, payload, candidates):
        seen.append(list(candidates))
        return real_holds(bundle, fresh, payload, candidates)

    monkeypatch.setattr(R, "validate_draft_file", portal_refuses_the_ocv_record)
    monkeypatch.setattr(R, "completeness_holds", spy)
    out = R.export_records(bdir, tmp_path / "records", run_portal=_portal())
    assert seen and all(gocv not in c and set(c) == {g060, g120} for c in seen)
    refused = {r["group_id"]: r for r in out["refused"]}
    assert refused[gocv]["verdict"] == "portal_reject"
    # the two that pass are still held for their own open potential, never for being like the refused one
    for gid in (g060, g120):
        assert refused[gid]["verdict"] == R.HELD_VERDICT and gocv not in (refused[gid].get("indistinguishable_from") or ())
