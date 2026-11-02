"""r4 integration: a curve one scan sets cannot be approved, and a bulk approval is refused for a result whose curve
carries a sentence the scientist must hear first (points on the edge, one scan's glitch, an outlier scan)."""

import pytest

from isaac_api.local_import import mutations as M

from test_local_import_polish_r1a import _processing, _versions_case
from test_local_import_records import BY, fake_upstream  # noqa: F401  (fixture)


def test_edge_from_single_scan_is_an_unusable_curve():
    assert "edge_from_single_scan" in M.UNUSABLE_CURVE_REASONS
    assert M.unusable_curve_reasons({"qc": {"verdict": "fail", "reasons": ["edge_from_single_scan"]}}) == [
        "edge_from_single_scan"]


def test_bulk_approve_problem_names_the_sentence():
    r = {"result_id": "proc-x", "qc": {"statements": {"glitch_points_on_edge": "SYN sentence."}}}
    assert "SYN sentence." in (M.bulk_approve_problem(r) or "")
    assert M.bulk_approve_problem({"result_id": "proc-y", "qc": {"statements": {}}}) is None


def test_a_bulk_approval_is_refused_for_a_flagged_curve_and_one_at_a_time_is_not(tmp_path, capsys):
    _processing()
    bdir, root = _versions_case(tmp_path)
    M.process(bdir, source=str(root))
    capsys.readouterr()
    b = M.load(bdir)
    with_curve = [r for r in b.get("processing_results") or () if r.get("outputs")]
    flagged, other = with_curve[0], next((r for r in with_curve[1:] if r.get("group_id") != with_curve[0].get("group_id")), None)
    if other is None:
        pytest.skip("the fixture has one group with a curve")
    flagged.setdefault("qc", {}).setdefault("statements", {})["outlier_scans"] = "SYN outlier sentence."
    M.save_bundle(bdir, b)
    ids = [M.B.processing_id(flagged), M.B.processing_id(other)]
    with pytest.raises(M.MutationRefused, match="SYN outlier sentence"):
        M.decide(bdir, target_ids=ids, decision="approve", value=None, qc_status="valid", **BY)
    out = M.decide(bdir, target_ids=[ids[0]], decision="approve", value=None, qc_status="valid", **BY)
    assert ids[0] in out["recorded"]
