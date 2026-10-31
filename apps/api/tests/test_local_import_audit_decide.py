"""Audit findings on ``isaac bundle decide`` (mutations.py, shared by the CLI and the local
questions screen), each pinned by a defect-shaped test. Synthetic fixture only.

1. an off-list value for a closed field is refused at decide time (never stored as a confirmed
   value that can never be eligible);
2. a replayed decision is "unchanged" only when it is the decision that GOVERNS the value now;
4. a merge that names nothing to merge is refused, and an old one is reported on regroup;
6. the append-only logs' bounds are raised (1.8.0) and a write past them is refused up front.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

SEMANTICS = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
BY = dict(by="Synthetic Scientist", orcid=None)
ENV = "context.environment"


@pytest.fixture(scope="module")
def grouped(tmp_path_factory):
    out = tmp_path_factory.mktemp("audit") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def b(grouped, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(grouped, target)
    return target


def _bytes(bdir: Path) -> bytes:
    return (bdir / "bundle.json").read_bytes()


def _all_but_requests(raw: bytes) -> dict:
    """The bundle without its vocabulary requests (1.10.0): an off-list answer is kept there, and nowhere else."""
    data = json.loads(raw)
    data.pop("vocabulary_requests", None)
    return data


def _env_question(bdir: Path) -> dict:
    payload = Q.consolidate(M.load(bdir))
    return next(q for q in payload["questions"] if q["kind"] == "missing_value"
                and any(m["target_field_path"] == ENV for m in M.load(bdir)["missing_values"]
                        if m["value_id"] == q["targets"][0]["id"]))


def _miss(bdir: Path, path: str) -> dict:
    return next(m for m in M.load(bdir)["missing_values"] if m["target_field_path"] == path and m["run_id"])


# --- 1. off-list values for a closed field -----------------------------------------------------------


def test_decide_question_refuses_an_off_list_value_and_writes_nothing(b, capsys):
    q = _env_question(b)
    before = _bytes(b)
    code = cli.main(["bundle", "decide", str(b), "--question", q["question_id"], "--decision", "correct",
                     "--value", "ex situ", "--by", "X", "--as-said"])
    err = capsys.readouterr().err
    assert code == 2
    assert "'ex situ' is not one of the schema's allowed values for context.environment" in err
    allowed = (B._schema_node(ENV) or {})["enum"]
    assert f"Allowed values for {ENV}: {', '.join(allowed)}" in err and "Nothing was recorded" in err
    # no decision and no value: the scientist's own word (--as-said) is kept as a vocabulary request only (1.10.0)
    assert "kept as a vocabulary request" in err
    assert _all_but_requests(_bytes(b)) == _all_but_requests(before)
    assert [r["term"] for r in json.loads(_bytes(b))["vocabulary_requests"]] == ["ex situ"]
    # the allowed spelling is recorded, and is eligible
    assert cli.main(["bundle", "decide", str(b), "--question", q["question_id"], "--decision", "correct",
                     "--value", "ex_situ", "--by", "X"]) == 0
    m = next(x for x in M.load(b)["missing_values"] if x["value_id"] == q["targets"][0]["id"])
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and m["eligibility_for_official_record"]["eligible"]


def test_decide_by_target_refuses_a_wrong_type_with_the_json_hint(b):
    cand = next(c for c in M.load(b)["candidates"] if c["target_field_path"] == "context.electrochemistry.potential_setpoint_V")
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(b, target_ids=[cand["candidate_id"]], decision="correct", value="-0.8 V", **BY)
    assert exc.value.code == 2 and "must be number" in str(exc.value) and "--json" in str(exc.value)
    assert not M.load(b).get("scientist_decisions")


def test_a_bulk_decision_with_one_off_list_target_records_nothing(b):
    """All-or-nothing: the shared record_decision (the local screen's path too) checks every target first."""
    ids = [m["value_id"] for m in M.load(b)["missing_values"] if m["target_field_path"] == ENV][:3]
    before = _bytes(b)
    with pytest.raises(M.MutationRefused):
        M.decide(b, target_ids=ids, decision="correct", value="ExSitu", as_said=True, **BY)
    # nothing is decided; the word (the scientist's own, as_said) is kept once, as a vocabulary request naming every target it reached (1.10.0)
    assert _all_but_requests(_bytes(b)) == _all_but_requests(before)
    [req] = json.loads(_bytes(b))["vocabulary_requests"]
    assert req["term"] == "ExSitu" and [t["id"] for t in req["targets"]] == ids


def test_a_stored_confirmed_but_unfit_value_loads_and_can_be_corrected(b):
    """An older build stored `ex situ` as confirmed (never eligible). The bundle still loads and
    writes, the value is identified as unfit, and a later `correct` with an allowed value works."""
    m = _miss(b, ENV)
    bundle = M.load(b)
    bundle["scientist_decisions"].append({
        "decision_id": "d-00001", "target": {"kind": "missing_value", "id": m["value_id"]}, "decision": "correct",
        "value": "ex situ", "chosen_reading_index": None,
        "decided_by": {"name": "Older Build", "basis": "self_reported_local_user", "identity": "local_unverified",
                       "orcid_claimed": None},
        "decided_utc": "2026-10-28T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None})
    M.save_bundle(b, bundle)  # as the older build wrote it: valid, never eligible
    stored = next(x for x in M.load(b)["missing_values"] if x["value_id"] == m["value_id"])
    assert stored["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    assert "not one of the schema's allowed values" in B.value_unfit_reason(stored)
    assert cli.main(["bundle", "check", str(b)]) == 0
    out = M.decide(b, target_ids=[m["value_id"]], decision="correct", value="ex_situ", **BY)
    assert out["recorded"] == [m["value_id"]]
    now = next(x for x in M.load(b)["missing_values"] if x["value_id"] == m["value_id"])
    assert now["eligibility_for_official_record"]["eligible"] and B.value_unfit_reason(now) is None


# --- 2. the governing decision, not the last on the same target ------------------------------------


def _cand22(bdir):
    bundle = M.load(bdir)
    conf = next(c for c in bundle["conflicts"] if c["conflict_id"] == "conf-001")
    cand = next(c for c in bundle["candidates"] if c["candidate_id"] == conf["candidate_id"])
    return cand, conf, [r["value"] for r in conf["readings"]]


def _composed(bdir, cid):
    bundle = M.load(bdir)
    cand = next(c for c in bundle["candidates"] if c["candidate_id"] == cid)
    return B.final_value(cand["value"], B.candidate_decision(bundle, cand), cand.get("readings"))


def test_re_correcting_a_candidate_after_its_conflict_was_decided_is_recorded(b):
    cand, conf, readings = _cand22(b)
    r0, r1 = readings[0], readings[1]
    assert r0 != r1
    M.decide(b, target_ids=[cand["candidate_id"]], decision="correct", value=r0, **BY)
    M.decide(b, target_ids=[conf["conflict_id"]], decision="confirm", value=r1, **BY)
    assert _composed(b, cand["candidate_id"]) == r1
    out = M.decide(b, target_ids=[cand["candidate_id"]], decision="correct", value=r0, **BY)
    assert out["recorded"] == [cand["candidate_id"]] and out["unchanged"] == []
    assert _composed(b, cand["candidate_id"]) == r0
    # and a true replay of the governing decision is still unchanged
    again = M.decide(b, target_ids=[cand["candidate_id"]], decision="correct", value=r0, **BY)
    assert again["recorded"] == [] and again["unchanged"] == [cand["candidate_id"]]


def test_re_confirming_a_conflict_after_its_candidate_was_corrected_is_recorded(b):
    cand, conf, readings = _cand22(b)
    r0, r1 = readings[0], readings[1]
    M.decide(b, target_ids=[conf["conflict_id"]], decision="confirm", value=r1, **BY)
    M.decide(b, target_ids=[cand["candidate_id"]], decision="correct", value=r0, **BY)
    assert _composed(b, cand["candidate_id"]) == r0
    out = M.decide(b, target_ids=[conf["conflict_id"]], decision="confirm", value=r1, **BY)
    assert out["recorded"] == [conf["conflict_id"]]
    assert _composed(b, cand["candidate_id"]) == r1


# --- 4. merge validation ------------------------------------------------------------------------------


def _groups(bdir):
    return [g["group_id"] for g in M.load(bdir)["record_groups"]]


@pytest.mark.parametrize("case", ["none", "unknown", "itself", "rejected"])
def test_a_merge_that_names_nothing_to_merge_is_refused(b, case):
    g1, g2 = _groups(b)[:2]
    if case == "rejected":
        M.decide(b, target_ids=[g2], decision="reject", value=None, **BY)
    merge_with = {"none": None, "unknown": ["rg-0000000000000000"], "itself": [g1], "rejected": [g2]}[case]
    before = _bytes(b)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(b, target_ids=[g1], decision="merge", value=None, merge_with=merge_with, **BY)
    said = str(exc.value)
    assert exc.value.code == 2 and "Nothing was recorded" in said
    assert {"none": "needs --merge-with", "unknown": "names no record group", "itself": "itself",
            "rejected": "no longer live"}[case] in said
    assert _bytes(b) == before


def test_a_valid_merge_is_still_recorded(b):
    g1, g2 = _groups(b)[:2]
    out = M.decide(b, target_ids=[g1], decision="merge", value=None, merge_with=[g2], **BY)
    assert out["recorded"] == [g1]


def test_regroup_reports_an_old_invalid_merge_instead_of_skipping_it(b):
    """An older build accepted `merge` with no merge_with: on regroup it is LISTED, with the reason."""
    g1 = _groups(b)[0]
    bundle = M.load(b)
    bundle["scientist_decisions"].append({
        "decision_id": "d-00001", "target": {"kind": "record_group", "id": g1}, "decision": "merge", "value": None,
        "chosen_reading_index": None,
        "decided_by": {"name": "Older Build", "basis": "self_reported_local_user", "identity": "local_unverified",
                       "orcid_claimed": None},
        "decided_utc": "2026-10-28T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None})
    M.save_bundle(b, bundle)
    out = M.group(b, regroup=True)
    [nc] = [x for x in out["merge_decisions_not_combined"] if x["decision_id"] == "d-00001"]
    assert "names no group to merge with" in nc["reason"] and "merged nothing" in nc["reason"]


# --- 6. the bounds of the append-only logs ----------------------------------------------------------


def test_the_log_bounds_match_the_other_bounds_and_the_schema():
    props = B.bundle_schema()["properties"]
    assert props["scientist_decisions"]["maxItems"] == B.MAX_SCIENTIST_DECISIONS == 200_000
    assert props["ai_interpretations"]["maxItems"] == B.MAX_AI_INTERPRETATIONS == 200_000
    assert props["missing_values"]["maxItems"] == props["exposures"]["maxItems"] == 200_000
    assert "1.8.0" in props["format_version"]["enum"] and B.FORMAT_VERSION in props["format_version"]["enum"]


def _filler(n: int, target_id: str) -> list[dict]:
    one = {"target": {"kind": "missing_value", "id": target_id}, "decision": "defer", "value": None,
           "chosen_reading_index": None,
           "decided_by": {"name": "Synthetic", "basis": "self_reported_local_user", "identity": "local_unverified",
                          "orcid_claimed": None},
           "decided_utc": "2026-10-28T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None}
    return [{**copy.deepcopy(one), "decision_id": f"d-{i:05d}"} for i in range(1, n + 1)]


def test_decision_20001_is_written(b):
    """At the 1.7.0 bound (20,000) the next decision failed validation, and so did every later one."""
    m = _miss(b, ENV)
    bundle = M.load(b)
    bundle["scientist_decisions"] = _filler(20_000, m["value_id"])
    M.save_bundle(b, bundle)
    out = M.decide(b, target_ids=[m["value_id"]], decision="correct", value="ex_situ", **BY)
    assert out["recorded"] == [m["value_id"]]
    assert len(M.load(b)["scientist_decisions"]) == 20_001


def test_a_decision_past_the_bound_is_refused_up_front_with_the_reason(b, monkeypatch):
    m = _miss(b, ENV)
    bundle = M.load(b)
    bundle["scientist_decisions"] = _filler(5, m["value_id"])
    M.save_bundle(b, bundle)
    before = _bytes(b)
    monkeypatch.setattr(B, "MAX_SCIENTIST_DECISIONS", 5)
    held = M.load(b)
    with pytest.raises(M.MutationRefused) as exc:
        M.record_decision(held, target_ids=[m["value_id"]], decision="correct", value="ex_situ", **BY)
    said = str(exc.value)
    assert "already holds 5 scientist decisions" in said and "bound of 5" in said and "nothing was written" in said
    assert len(held["scientist_decisions"]) == 5  # the refusal leaves the loaded bundle as it was
    with pytest.raises(M.MutationRefused):
        M.decide(b, target_ids=[m["value_id"]], decision="correct", value="ex_situ", **BY)
    assert _bytes(b) == before


def test_an_interpretation_past_the_bound_is_refused_up_front(b, monkeypatch):
    m = _miss(b, ENV)
    monkeypatch.setattr(B, "MAX_AI_INTERPRETATIONS", 0)
    before = _bytes(b)
    with pytest.raises(M.MutationRefused) as exc:
        M.annotate(b, target_id=m["value_id"], value="ex_situ", excerpt_locator=None, source_id=None,
                   model_id="synthetic", blind=False, rationale="")
    assert "AI interpretations" in str(exc.value) and "nothing was written" in str(exc.value)
    assert _bytes(b) == before


def test_a_1_7_0_bundle_is_upgraded_on_its_next_write_and_says_so(b, capsys):
    raw = json.loads(_bytes(b))
    raw["format_version"] = "1.7.0"
    raw.pop("format_upgrades", None)
    (b / "bundle.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert B.validate_bundle(B.load_bundle(b)) == []  # loads and validates as stored
    M.decide(b, target_ids=[_miss(b, ENV)["value_id"]], decision="correct", value="ex_situ", **BY)
    assert "1.8.0 raises the bounds on scientist_decisions" in capsys.readouterr().err
    after = M.load(b)
    assert after["format_version"] == B.FORMAT_VERSION  # 1.9.0 since (the last-token counter)
    [u] = after["format_upgrades"]
    assert u["from_format_version"] == "1.7.0" and u["to_format_version"] == B.FORMAT_VERSION
    assert "200,000" in u["statement"] and u["newly_writable_paths"] == []


# --- the lock file, the path in a message, `process --group` (coordinator follow-ups) -----------------


def test_a_lock_file_that_is_a_symlink_is_refused_and_its_target_is_never_created(b, tmp_path):
    target = tmp_path / "elsewhere" / "planted.txt"
    target.parent.mkdir()
    lock = b / ".bundle.lock"
    if lock.exists() or lock.is_symlink():
        lock.unlink()
    lock.symlink_to(target)
    before = _bytes(b)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(b, target_ids=[_miss(b, ENV)["value_id"]], decision="correct", value="ex_situ", **BY)
    assert exc.value.code == 1 and "symbolic link" in str(exc.value)
    assert str(tmp_path) not in str(exc.value) and "planted" not in str(exc.value)  # no path in the message
    assert not target.exists() and _bytes(b) == before


def test_a_new_lock_file_is_owner_only(b):
    lock = b / ".bundle.lock"
    if lock.exists():
        lock.unlink()
    with M.locked(b):
        pass
    assert (lock.stat().st_mode & 0o777) == 0o600


def test_no_bundle_message_names_the_folder_never_its_absolute_path(tmp_path):
    empty = tmp_path / "deep" / "not_a_bundle"
    empty.mkdir(parents=True)
    for call in (lambda: M.load(empty),
                 lambda: M.decide_question(empty, question_id="Q-x", decision="confirm", value=None, **BY)):
        with pytest.raises(M.MutationRefused) as exc:
            call()
        assert exc.value.code == 6 and "'not_a_bundle'" in str(exc.value) and str(tmp_path) not in str(exc.value)


def _result(gid: str, pid: str) -> dict:
    return {"result_id": pid, "group_id": gid, "protocol_id": "isaac.xas.synthetic", "protocol_version": "0.1",
            "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [], "steps": [],
            "outputs": {"files": []}, "qc": {"metrics": {}, "verdict": "pass"}, "comparison": None,
            "state": "candidate_extracted"}


def test_process_with_group_keeps_every_other_groups_undecided_results(b, monkeypatch):
    from isaac_api.local_import.processing import cli_entry

    g1, g2 = _groups(b)[:2]
    bundle = M.load(b)
    bundle["processing_results"] = [_result(g1, "p-old-1"), _result(g2, "p-2")]
    M.save_bundle(b, bundle)
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {
        "status": "ran", "processing_results": [_result(g1, "p-new-1")], "summary": {}})
    M.process(b, group_ids=[g1])
    ids = {r["result_id"] for r in M.load(b)["processing_results"]}
    assert ids == {"p-new-1", "p-2"}  # g1 re-processed; g2's undecided result untouched
    # without --group every undecided result is replaced, as before
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {
        "status": "ran", "processing_results": [_result(g1, "p-new-1")], "summary": {}})
    M.process(b)
    assert {r["result_id"] for r in M.load(b)["processing_results"]} == {"p-new-1"}
