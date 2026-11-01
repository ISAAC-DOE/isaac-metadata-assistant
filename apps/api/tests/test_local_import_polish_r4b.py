"""r4b: what a real-data run on an SSRL BL15-2 Ir L3 HERFD beamtime found (87 runs of 6 electrodes at many potentials,
plus 5 standards, 78 record groups). Synthetic only: the committed multi-operator corpus (ZZ names), the SYN counter
folder and invented scans.

* M1: a beamtime-wide answer for a field covers each run's disagreement about it (the record is composed from that
  answer), counted with ``conflicts_covered_by_decisions``, under the same question id;
"""

from __future__ import annotations

from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, bdir, fake_upstream, pristine)

TECH = "system.technique"
RULED, UNRULED = "conf-007", "conf-009"  # run-004's and run-005's disagreements in the corpus


# --- M1: a beamtime-wide answer covers the runs' disagreements ----------------------------------------------------


def _technique_disagreements(bdir):
    """The BL15-2 shape: two runs' disagreements are about the technique, and no answer is given yet."""
    M.group(bdir)
    b = M.load(bdir)
    cand_of = {c["candidate_id"]: c for c in b["candidates"]}
    conflicts = {cf["conflict_id"]: cf for cf in b["conflicts"]}
    for cid in (RULED, UNRULED):
        cand_of[conflicts[cid]["candidate_id"]]["target_field_path"] = TECH
    M.save_bundle(bdir, b)
    return conflicts, next(c for c in b["candidates"] if c["target_field_path"] == TECH and c["run_id"] is None)


def _conflict_q(payload, conflict_id):
    return next(q for q in payload["questions"] if q["targets"] == [{"kind": "conflict", "id": conflict_id}])


def test_a_beamtime_wide_answer_covers_the_runs_disagreements_about_its_field(bdir):
    _, beam = _technique_disagreements(bdir)
    before = Q.consolidate(M.load(bdir))
    ids = {cid: _conflict_q(before, cid)["question_id"] for cid in (RULED, UNRULED)}
    assert all("covered_by_decisions" not in _conflict_q(before, cid) for cid in ids)
    got = M.decide(bdir, target_ids=[beam["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    after = Q.consolidate(M.load(bdir))
    [did] = {d["decision_id"] for d in M.load(bdir)["scientist_decisions"]}
    for cid in (RULED, UNRULED):
        q = _conflict_q(after, cid)
        assert q["question_id"] == ids[cid]  # the same id
        assert q["covered_by_decisions"] == [did] and q["affects_record"] is False and q["tier"] == Q.TIER_OPTIONAL
        assert q["why"].startswith(f"Already decided: the beamtime-wide answer for {TECH} ({did}) reaches its run")
    assert after["counts"]["conflicts_affecting_a_record"] == 0
    assert after["counts"]["conflicts_covered_by_decisions"] == before["counts"]["conflicts_covered_by_decisions"] + 2
    assert got["recorded"]


def test_a_run_decided_otherwise_still_disagrees_with_the_beamtime_answer(bdir):
    conflicts, beam = _technique_disagreements(bdir)
    M.decide(bdir, target_ids=[beam["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="XAS", **BY)
    p = Q.consolidate(M.load(bdir))
    assert "covered_by_decisions" not in _conflict_q(p, RULED)  # its run's own answer differs: two values
    assert _conflict_q(p, UNRULED)["covered_by_decisions"]
    # the same value on the run as for the beamtime: both decisions cover it, said as decisions of its run
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    q = _conflict_q(Q.consolidate(M.load(bdir)), RULED)
    assert len(q["covered_by_decisions"]) == 2 and q["why"].startswith("Already decided: its run holds")


def test_a_deferred_beamtime_answer_covers_nothing(bdir):
    _, beam = _technique_disagreements(bdir)
    M.decide(bdir, target_ids=[beam["candidate_id"]], decision="defer", value=None, **BY)
    p = Q.consolidate(M.load(bdir))
    assert all("covered_by_decisions" not in _conflict_q(p, cid) for cid in (RULED, UNRULED))
