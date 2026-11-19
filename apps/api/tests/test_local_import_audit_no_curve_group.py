"""Audit of 18 Nov 2026, finding 11: a live group whose only processing results have no curve can never export as
it stands, so it gets a ``cannot_export_reason`` and its questions stop counting as blocking. SYNTHETIC scans only.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import questions as Q


def test_only_a_group_whose_every_result_has_no_curve_is_named():
    ok = {"result_id": "p1", "group_id": "g1", "outputs": {"files": [{"role": "normalized"}]}}
    failed = {"result_id": "p2", "group_id": "g2", "outputs": {"files": []},
              "failure": {"code": "syn_no_energy_axis", "detail": "SYN: no energy column"}}
    again = {**failed, "result_id": "p3"}
    b = {"processing_results": [ok, failed, again, {**failed, "result_id": "p4", "group_id": "g1"}]}
    assert Q.groups_with_no_curve(b) == {"g2": "syn_no_energy_axis: SYN: no energy column"}
    assert Q.groups_with_no_curve({"processing_results": []}) == {}          # not processed yet is not "no curve"


np = pytest.importorskip("numpy", reason="the processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="the processing tests need the optional `processing` extra (xraylarch)")
pytest.importorskip("scipy", reason="the xas-analysis engine needs scipy")
pytest.importorskip("yaml", reason="the xas-analysis engine needs pyyaml")

import test_local_import_engine_xas as T  # noqa: E402
from isaac_api.local_import import cli  # noqa: E402
from isaac_api.local_import import mutations as M  # noqa: E402


def test_a_group_with_no_curve_cannot_export_and_blocks_nothing(tmp_path, monkeypatch, capsys):
    """A SYN group whose one scan stops below the edge: its result is a failure with no curve."""
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")
    n = int(np.flatnonzero(T.GRID >= 11208.0)[0]) + 1
    runs = T._two_groups() + [("03_SYN_ZZ3_060mV", 13, [T.scan_cols(150, n_points=n)])]
    bdir, root = T.imported(tmp_path, runs, process=False)
    b = M.load(bdir)
    key = next(r["run_key"] for r in b["runs"] if r["stem"] == "03_SYN_ZZ3_060mV")
    gid = next(g["group_id"] for g in b["record_groups"] if key in g["member_run_keys"])
    before = Q.consolidate(b)
    blocking_before = [q["question_id"] for q in before["questions"] if q["blocking"] and q["scope"] == f"group:{gid}"]
    assert blocking_before and gid not in Q.cannot_export_reasons(b)          # not processed yet: asked as any group
    M.process(bdir, source=str(root))
    b = M.load(bdir)
    assert Q.cannot_export_reasons(b)[gid] == Q.NO_CURVE_REASON
    after = Q.consolidate(b)
    mine = [q for q in after["questions"] if q["scope"] == f"group:{gid}"]
    assert {q["question_id"] for q in mine} >= set(blocking_before)             # the same questions, the same ids
    assert not [q for q in mine if q["blocking"]]                               # ...none of them blocking now
    assert gid in after["blocking_basis"]["record_composer"]["groups_that_cannot_export"]
    assert after["counts"]["blocking"] < before["counts"]["blocking"]
    capsys.readouterr()
    assert cli.main(["bundle", "list", str(bdir), "groups"]) == 0
    listed = json.loads(capsys.readouterr().out)
    row = next(x for x in listed["items"] if x["group_id"] == gid)
    assert row["cannot_export_reason"] == Q.NO_CURVE_REASON
    assert "processing_result_has_no_curve" in json.dumps(listed)
