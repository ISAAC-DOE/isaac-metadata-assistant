"""LOCAL-4 D1/D2: the record composer reads LOCAL-P's ACTUAL processing output, and a
person can state a QC status the protocol leaves open. Synthetic spectra only."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R

np = pytest.importorskip("numpy")

from tests_support_records import BY, decide_everything, fake_upstream_env, pristine_bundle  # noqa: E402,F401


def test_the_composer_reads_the_processing_writers_own_normalized_csv(tmp_path):
    """CONTRACT: LOCAL-P's `_csv` writer output -> `_read_series_file`, by column NAME."""
    from isaac_api.local_import.processing import run as processing_run

    energy = np.array([1000.0, 1005.0, 1010.0, 1015.0])
    norm = np.array([0.01, 0.2, 0.9, 1.0])
    flat = np.array([0.0, 0.1, 0.95, 1.0])
    path = tmp_path / "normalized.csv"
    processing_run._csv(path, ["energy_eV", "norm", "flat"], [energy, norm, flat], np)
    assert path.read_text().splitlines()[1] == "energy_eV,norm,flat"
    xs, ys = R._read_series_file(path)
    assert xs == list(energy) and ys == pytest.approx(list(norm))


def test_a_header_without_the_contract_columns_is_refused_with_a_reason(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("energy,mu\n1,2\n")
    reason = R._read_series_file(path)
    assert isinstance(reason, str) and "energy_eV" in reason and "norm" in reason


def test_a_headerless_two_column_file_is_still_read(tmp_path):
    path = tmp_path / "x.txt"
    path.write_text("# c\n1000 0.1\n1005 0.2\n")
    assert R._read_series_file(path) == ([1000.0, 1005.0], [0.1, 0.2])


def _contract_result(bdir: Path, verdict: str) -> None:
    """A processing result whose normalised file is written by LOCAL-P's own writer."""
    from isaac_api.local_import.processing import run as processing_run

    b = M.load(bdir)
    gdir = bdir / "processing" / "g1"
    gdir.mkdir(parents=True)
    path = gdir / "normalized.csv"
    processing_run._csv(path, ["energy_eV", "norm", "flat"], [np.linspace(1000, 1100, 21), np.linspace(0, 1, 21), np.linspace(0, 1, 21)], np)
    run = b["runs"][0]
    b["record_groups"] = [{"group_id": "g1", "experiment_key": "e", "member_run_keys": [run["run_key"]],
                           "basis": {"sample": None, "technique": None, "environment": None, "conditions": {}},
                           "split_reasons": [], "status": "proposed", "questions": []}]
    b["processing_results"] = [{"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
                                "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [], "steps": [],
                                "outputs": {"files": [{"role": "normalized", "relative_path": "processing/g1/normalized.csv",
                                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}],
                                            "e0_eV": 1050.0, "edge_step": 1.0, "points": 21},
                                "qc": {"metrics": {"noise": 0.01}, "verdict": verdict}, "comparison": None, "state": "candidate_extracted"}]
    M.save_bundle(bdir, b)


def test_d1_an_approved_real_shaped_result_yields_a_series(pristine_bundle, tmp_path, fake_upstream_env):
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    _contract_result(bdir, "pass")
    decide_everything(bdir, add_group=False)
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    assert len(draft["series"][0]["independent_variables"][0]["values"]) == 21
    assert draft["series"][0]["channels"][0] == {**draft["series"][0]["channels"][0], "name": "absorption", "unit": "mu_normalized", "role": "primary_signal"}


def test_d2_i4_a_qc_status_is_only_ever_a_persons_statement(pristine_bundle, tmp_path, fake_upstream_env):
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    _contract_result(bdir, "pass")
    decide_everything(bdir, add_group=False)
    # I4: approving without a stated QC status is refused, even for a `pass` verdict
    with pytest.raises(M.MutationRefused) as raised:
        M.decide(bdir, target_ids=["p1"], decision="approve", value=None, **BY)
    assert "--qc-status" in str(raised.value)
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="excellent", **BY)
    # and a legacy approval that carries no QC status maps NOTHING automatically
    b = M.load(bdir)
    for d in b["scientist_decisions"]:
        if d["target"]["id"] == "p1":
            d.pop("qc_status", None), d.pop("qc_note", None), d.pop("qc_evidence", None)
    M.save_bundle(bdir, b)
    result = R.build_records(bdir)
    assert "measurement.qc.status" in result["drafts"][0]["missing_required"]
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="compromised",
             qc_note="SYNTHETIC: edge region noisy", **BY)
    d = M.load(bdir)["scientist_decisions"][-1]
    assert d["qc_status"] == "compromised" and d["qc_evidence"] == {"verdict": "pass", "metrics": {"noise": 0.01}}
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    assert draft["qc"] == {"status": "compromised", "evidence": "SYNTHETIC: edge region noisy"}
