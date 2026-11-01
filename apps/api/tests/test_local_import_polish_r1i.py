"""r1 integration: the ``--e0-measured`` gate on approving an Athena result whose E0 may be a fixed setting."""

import pytest

from isaac_api.local_import import mutations as M

from test_local_import_polish_r1a import _processing, _versions_case
from test_local_import_records import BY, fake_upstream  # noqa: F401  (fixture)


def _flag_one_result(bundle_dir):
    b = M.load(bundle_dir)
    r = next(r for r in b.get("processing_results") or () if r.get("outputs"))  # the gate reads the flag only
    r.setdefault("review_flags", []).append("athena_e0_possibly_fixed")
    M.save_bundle(bundle_dir, b)
    return M.B.processing_id(r)


def test_e0_measured_refused_without_approve():
    with pytest.raises(M.MutationRefused, match="--e0-measured goes with --decision approve"):
        M._decide_arguments(target_ids=["proc-x"], decision="reject", by="Synthetic Scientist", orcid=None,
                            qc_status=None, element=None, edge=None, positions=None, e0_measured=True)


def test_a_possibly_fixed_e0_needs_e0_measured(tmp_path, capsys):
    _processing()
    processed_bundle, root = _versions_case(tmp_path)
    M.process(processed_bundle, source=str(root))
    capsys.readouterr()
    pid = _flag_one_result(processed_bundle)
    with pytest.raises(M.MutationRefused, match="possibly fixed Athena E0"):
        M.decide(processed_bundle, target_ids=[pid], decision="approve", value=None, qc_status="valid", **BY)
    out = M.decide(processed_bundle, target_ids=[pid], decision="approve", value=None, qc_status="valid", e0_measured=True, **BY)
    assert pid in out["recorded"]
    d = M.load(processed_bundle)["scientist_decisions"][-1]
    assert d["qc_evidence"]["e0_measured"] == {"confirmed": True, "flag": "athena_e0_possibly_fixed"}
