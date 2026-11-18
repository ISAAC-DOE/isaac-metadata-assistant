"""The scientists' MERGE folder (18 Nov 2026 overnight polish, items 3 and 4). SYNTHETIC files only: every name is
``SYN``/``ZZ``-prefixed and every value is invented.

3. **A file in a MERGE folder is never a measurement run (bundle 1.13.0).** On a real BL15-2 beamtime two PyMca
   ``.mca`` averages in ``MERGE/`` (``#S 1 Average of 11 from Norm. …``) were read by the generic MCA reader and each
   became a run of its own, so a record group and questions were made for a measurement nobody performed and
   processing said ``bl15_2_energy_column_missing``. Beside SPEC acquisition runs, a file a generic reader read that
   sits under a folder named ``MERGE`` is a processed output (``isaac.processed_output.origin.merge_folder.v0``,
   basis ``merge_folder``), linked by legacy number as the engine-classified quick merges are. With no SPEC run it
   stays a run, as before. A 1.13.0 import holding such a run is refused; a 1.12.0 bundle on disk still validates and
   its first save says re-import to fix it.
4. **A quick merge's file name is not a reading of the measurement.** The engine attached each MERGE product to the
   run sharing its legacy number and read its FILE NAME as evidence, so ``MERGE/07_01_…after1200Cycling…`` (the
   scientist's re-spelled label) disagreed with the acquisition's ``after1200mVCycling``: a spurious conflict and a
   question. A processed product is still attached to its run (listed in its relationships) but supports no candidate,
   condition or sample reading.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_quick_merges import _quick, _spec_run  # noqa: E402
from test_local_import_reader_mca import make_mca  # noqa: E402

RUN = "07_01_ZZ1_acid_after1200mVCycling_filter10_1200mV"
OTHER = "05_01_ZZ1_acid_beforeCycling_filter10_060mV"
MERGE_RULE = "isaac.processed_output.origin.merge_folder.v0"


def _beamtime(root: Path, *, spec: bool = True) -> Path:
    bt = root / "SYN_BL00_2100-01_MergeFolder"
    if spec:
        for stem in (RUN, OTHER):
            _spec_run(bt, stem)
    make_mca(bt / "MERGE" / "ave_ZZ1_filter10.mca")          # an average naming no legacy number
    make_mca(bt / "MERGE" / "07_01_ZZ1_filter10_ave.mca")    # an average naming RUN's legacy and electrode numbers
    _quick(bt / "MERGE" / "07_01_ZZ1_acid_after1200Cycling_f10_1200mV.txt")  # the re-spelled quick merge (item 4)
    make_mca(bt / "detector" / "SYN_raw_counts.mca")         # an .mca in no MERGE folder: still a run, as before
    return bt


def _import(src: Path, out: Path, capsys) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    return json.loads((out / "bundle.json").read_text())


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("mergefolder")
    out = root / "out"
    assert cli.main(["import", str(_beamtime(root / "src")), "--out", str(out)]) == 0
    return out, json.loads((out / "bundle.json").read_text())


@pytest.fixture()
def b(built):
    return json.loads(json.dumps(built[1]))


def _po(b: dict, label: str) -> dict:
    return next(p for p in b["processed_outputs"] if p["label"] == label)


# --- 3. MERGE .mca files are processed outputs, never runs ---------------------------------------------------------


def test_an_mca_in_a_merge_folder_is_a_processed_output_never_a_run(b):
    assert B.FORMAT_VERSION == "1.13.0" and b["format_version"] == "1.13.0"
    in_merge = [r for r in b["runs"] for s in r["scans"] if s["relative_path"].startswith("MERGE/")]
    assert in_merge == []
    for label in ("ave_ZZ1_filter10", "07_01_ZZ1_filter10_ave"):
        po = _po(b, label)
        [f] = po["files"]
        assert f["relative_path"] == f"MERGE/{label}.mca"
        assert f["processing_origin"]["rule_id"] == MERGE_RULE and f["processing_origin"]["basis"] == "merge_folder"
        assert po["role"] == "reference_result" and po["becomes_a_record"] is False
        assert "MERGE folder" in po["statement"] and "never a run" in po["statement"]
        assert B.is_quick_merge(po) and not B.is_engine_classified(po)
    assert B.validate_bundle(b) == []


def test_a_merge_folder_mca_links_by_legacy_number_like_a_quick_merge(b):
    [link] = _po(b, "07_01_ZZ1_filter10_ave")["proposed_links"]
    assert link["rule_id"] == B.LEGACY_LINK_RULE_ID and link["run_stem"] == RUN
    assert _po(b, "ave_ZZ1_filter10")["proposed_links"] == []


def test_an_mca_outside_a_merge_folder_stays_a_run(b):
    assert [r["stem"] for r in b["runs"] if r["source_type"] == "generic:mca_v1"] == ["SYN_raw_counts"]


def test_without_a_spec_run_a_merge_folder_mca_stays_a_run(tmp_path, capsys):
    b = _import(_beamtime(tmp_path / "src", spec=False), tmp_path / "out", capsys)
    stems = {r["stem"] for r in b["runs"] if r["source_type"] == "generic:mca_v1"}
    assert {"ave_ZZ1_filter10", "07_01_ZZ1_filter10_ave"} <= stems
    assert not [p for p in b["processed_outputs"] if B.is_quick_merge(p) and not B.is_engine_classified(p)]
    assert B.validate_bundle(b) == []


def test_the_validator_refuses_a_merge_folder_run_and_a_forged_merge_folder_output(b):
    bad = json.loads(json.dumps(b))
    po = bad["processed_outputs"].pop(bad["processed_outputs"].index(_po(bad, "ave_ZZ1_filter10")))
    f = po["files"][0]
    spec_run = next(r for r in bad["runs"] if r["stem"] == RUN)
    bad["runs"].append({**spec_run, "run_id": "run-999", "run_key": "mca_v1:MERGE/ave_ZZ1_filter10", "stem": "ave_ZZ1_filter10",
                        "label": "ave_ZZ1_filter10", "source_type": "generic:mca_v1", "legacy_number": None,
                        "scans": [{"source_id": f["source_id"], "relative_path": f["relative_path"], "scan_index": None}],
                        "scan_count": 1, "candidate_ids": [], "conflict_ids": [], "data_quality_note_ids": []})
    assert any("run run-999" in e and MERGE_RULE in e for e in B.validate_bundle(bad))
    # the same run in a bundle a 1.12.0 build imported is accepted (it stays until a re-import)
    bad["format_version"] = "1.12.0"
    assert not any("run run-999" in e for e in B.validate_bundle(bad))
    # an output said to be in a MERGE folder whose file is not in one is refused
    forged = json.loads(json.dumps(b))
    po = _po(forged, "ave_ZZ1_filter10")
    src = next(s for s in forged["sources"] if s["source_id"] == po["files"][0]["source_id"])
    src["relative_path"] = po["files"][0]["relative_path"] = "elsewhere/ave_ZZ1_filter10.mca"
    assert any(MERGE_RULE in e and "not in a MERGE folder" in e for e in B.validate_bundle(forged))


def test_a_1_12_0_bundle_holding_merge_folder_runs_validates_and_its_first_save_says_reimport(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(B, "in_merge_folder", lambda rel: False)  # what a 1.12.0 build made: the averages as runs
    out = tmp_path / "old"
    old = _import(_beamtime(tmp_path / "src"), out, capsys)
    monkeypatch.undo()
    held = B.merge_folder_runs(old)
    assert len(held) == 2
    old["format_version"] = "1.12.0"
    old.pop("format_upgrades", None)
    assert B.validate_bundle(old) == []
    (out / "bundle.json").write_bytes(B.encode(old))
    M.group(out)
    saved = M.load(out)
    assert saved["format_version"] == "1.13.0"
    [u] = saved["format_upgrades"]
    assert u["from_format_version"] == "1.12.0" and B.CHANGES_ADDED_IN["1.13.0"] in u["statement"]
    assert "2 of its runs" in u["statement"] and "re-import to keep them as processed outputs" in u["statement"]
    assert B.check_bundle(out) == []


def test_the_schema_adds_only_the_new_origin_rule_and_basis():
    s = B.bundle_schema()
    f = s["$defs"]["processed_output"]["properties"]["files"]["items"]["properties"]["processing_origin"]["properties"]
    assert f["rule_id"]["enum"] == ["isaac.processed_output.origin.v0", "isaac.processed_output.origin.engine_classification.v0",
                                    MERGE_RULE]
    assert f["basis"]["enum"] == ["line_1", "fields", "engine_classification", "merge_folder"]
    assert s["properties"]["format_version"]["enum"][-1] == "1.13.0"


# --- 4. a quick merge's file name is not condition or sample evidence -----------------------------------------------


def _cites_merge(obj) -> bool:
    return "MERGE/" in json.dumps(obj)


def test_no_condition_or_sample_reading_cites_a_quick_merge_file(b):
    assert [c["conflict_id"] for c in b["conflicts"] if _cites_merge(c)] == []
    assert [c["candidate_id"] for c in b["candidates"] if _cites_merge(c.get("evidence")) or _cites_merge(c.get("readings"))] == []
    run = next(r for r in b["runs"] if r["stem"] == RUN)
    # the product is still attached to its run, as a relationship only
    assert "MERGE/07_01_ZZ1_acid_after1200Cycling_f10_1200mV.txt" in (run["other_relationships"].get("processed_products") or [])
    cyc = [c for c in b["candidates"] if c["run_id"] == run["run_id"] and c.get("statement_key") == "cycling_state"]
    assert cyc and all(c["extracted_state"] != "conflicting" for c in cyc)


def test_grouping_makes_no_group_or_question_from_a_merge_file(built, tmp_path):
    out, _ = built
    import shutil

    work = tmp_path / "out"
    shutil.copytree(out, work)
    M.group(work)
    g = M.load(work)
    assert not [grp["group_id"] for grp in g["record_groups"] if any(k.startswith("mca_v1:MERGE/") for k in grp["member_run_keys"])]
    assert B.validate_bundle(g) == []
