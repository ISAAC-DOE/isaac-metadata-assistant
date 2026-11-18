"""The scientists' MERGE folder (18 Nov 2026 overnight polish, items 3 and 4; review of PR #335). SYNTHETIC files only:
every name is ``SYN``/``ZZ``-prefixed and every value is invented.

3. **A file whose own content says it is an average is never a measurement run (bundle 1.13.0).** On a real BL15-2
   beamtime two PyMca ``.mca`` averages in ``MERGE/`` (``#S 1 Average of 11 from Norm. …``) were read by the generic
   MCA reader and each became a run. Beside SPEC acquisition runs, a file a generic reader read whose scan title states
   an average of N spectra is a processed output (``isaac.processed_output.origin.average_title.v0``, basis
   ``average_title``), linked by legacy number as the engine-classified quick merges are. A FOLDER NAME IS NEVER
   EVIDENCE: any other file in a folder named ``MERGE`` stays a run, with a note asking whether it is the scientists'
   quick merge, and the scientist rejects or confirms its group. A 1.13.0 import holding an average-title run is
   refused; a 1.12.0 bundle on disk still validates and its first save says re-import to fix it.
4. **A quick merge's file name is not a reading of the measurement.** A processed product is still attached to its run
   (listed in its relationships) but supports no candidate, condition or sample reading.
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
TITLE_RULE = "isaac.processed_output.origin.average_title.v0"
WHO = "SYN Scientist"


def _average(path: Path, n: int = 11) -> Path:
    """A synthetic PyMca average: its scan title states ``Average of <n> from`` the spectra it averages."""
    make_mca(path)
    path.write_text(path.read_text().replace("#S 1 (synthetic title 2.1 DTC)", f"#S 1 Average of {n} from Norm. SYN_scan 1.1 Y"))
    return path


def _beamtime(root: Path, *, spec: bool = True) -> Path:
    bt = root / "SYN_BL00_2100-01_MergeFolder"
    if spec:
        for stem in (RUN, OTHER):
            _spec_run(bt, stem)
    _average(bt / "MERGE" / "ave_ZZ1_filter10.mca")              # an average naming no legacy number
    _average(bt / "MERGE" / "07_01_ZZ1_filter10_ave.mca", 4)     # an average naming RUN's legacy and electrode numbers
    _average(bt / "averages" / "ZZ1_elsewhere_ave.mca", 3)       # an average in no MERGE folder: its content decides
    make_mca(bt / "ZZ9_cell" / "merge" / "ZZ9_fresh_measurement.mca")  # a MERGE folder, a plain title: still a run
    _quick(bt / "MERGE" / "07_01_ZZ1_acid_after1200Cycling_f10_1200mV.txt")  # the re-spelled quick merge (item 4)
    make_mca(bt / "detector" / "SYN_raw_counts.mca")             # an .mca in no MERGE folder: still a run, as before
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


# --- 3. content, never a folder name, makes a processed output -------------------------------------------------------


def test_an_mca_whose_title_states_an_average_is_a_processed_output_never_a_run(b):
    assert B.FORMAT_VERSION == "1.13.0" and b["format_version"] == "1.13.0"
    for label, rel in (("ave_ZZ1_filter10", "MERGE/ave_ZZ1_filter10.mca"),
                       ("07_01_ZZ1_filter10_ave", "MERGE/07_01_ZZ1_filter10_ave.mca"),
                       ("ZZ1_elsewhere_ave", "averages/ZZ1_elsewhere_ave.mca")):
        assert not [r for r in b["runs"] for s in r["scans"] if s["relative_path"] == rel]
        po = _po(b, label)
        [f] = po["files"]
        assert f["relative_path"] == rel
        assert f["processing_origin"]["rule_id"] == TITLE_RULE and f["processing_origin"]["basis"] == "average_title"
        assert po["role"] == "reference_result" and po["becomes_a_record"] is False
        assert "Average of N" in po["statement"] and "never a run" in po["statement"]
        assert B.is_quick_merge(po) and not B.is_engine_classified(po)
    assert B.validate_bundle(b) == []


def test_an_average_links_by_legacy_number_like_a_quick_merge(b):
    [link] = _po(b, "07_01_ZZ1_filter10_ave")["proposed_links"]
    assert link["rule_id"] == B.LEGACY_LINK_RULE_ID and link["run_stem"] == RUN
    assert _po(b, "ave_ZZ1_filter10")["proposed_links"] == []


def test_a_merge_folder_alone_only_proposes_the_run_stays_and_is_flagged(b):
    [run] = [r for r in b["runs"] if r["stem"] == "ZZ9_fresh_measurement"]
    assert run["run_candidate"] is True
    [note] = [a for a in run["other_relationships"]["anomalies"] if a["kind"] == B.MERGE_FOLDER_NOTE_KIND]
    assert note["detail"].startswith("In a MERGE folder: is this the scientists' quick merge?")
    assert "reject its group" in note["detail"] and "confirm it" in note["detail"]
    # an .mca in no MERGE folder: a run with no such note
    [raw] = [r for r in b["runs"] if r["stem"] == "SYN_raw_counts"]
    assert not [a for a in raw["other_relationships"]["anomalies"] if a["kind"] == B.MERGE_FOLDER_NOTE_KIND]


@pytest.mark.parametrize("decision,status", [("reject", "rejected"), ("confirm", "scientist_confirmed")])
def test_the_scientist_decides_which_a_merge_folder_run_is(built, tmp_path, decision, status):
    import shutil

    work = tmp_path / "out"
    shutil.copytree(built[0], work)
    M.group(work)
    g = M.load(work)
    run = next(r for r in g["runs"] if r["stem"] == "ZZ9_fresh_measurement")
    [grp] = [x for x in g["record_groups"] if run["run_key"] in x["member_run_keys"] and x["status"] == "proposed"]
    M.decide(work, target_ids=[grp["group_id"]], decision=decision, value=None, by=WHO, orcid=None)
    after = M.load(work)
    assert next(x for x in after["record_groups"] if x["group_id"] == grp["group_id"])["status"] == status
    assert B.validate_bundle(after) == []


def test_without_a_spec_run_an_average_stays_a_run(tmp_path, capsys):
    b = _import(_beamtime(tmp_path / "src", spec=False), tmp_path / "out", capsys)
    stems = {r["stem"] for r in b["runs"] if r["source_type"] == "generic:mca_v1"}
    assert {"ave_ZZ1_filter10", "07_01_ZZ1_filter10_ave", "ZZ1_elsewhere_ave"} <= stems
    assert not [p for p in b["processed_outputs"] if B.is_quick_merge(p) and not B.is_engine_classified(p)]
    assert B.validate_bundle(b) == []


def test_the_validator_refuses_an_average_run_and_a_forged_average_output(b):
    bad = json.loads(json.dumps(b))
    po = bad["processed_outputs"].pop(bad["processed_outputs"].index(_po(bad, "ave_ZZ1_filter10")))
    f = po["files"][0]
    spec_run = next(r for r in bad["runs"] if r["stem"] == RUN)
    bad["runs"].append({**spec_run, "run_id": "run-999", "run_key": "mca_v1:MERGE/ave_ZZ1_filter10", "stem": "ave_ZZ1_filter10",
                        "label": "ave_ZZ1_filter10", "source_type": "generic:mca_v1", "legacy_number": None,
                        "scans": [{"source_id": f["source_id"], "relative_path": f["relative_path"], "scan_index": None}],
                        "scan_count": 1, "candidate_ids": [], "conflict_ids": [], "data_quality_note_ids": []})
    for e in bad["extended_context"]:
        if e.get("processed_output_id") == po["processed_output_id"]:
            e.pop("processed_output_id")
            e.update(scope="run", run_id="run-999")
    assert any("run run-999" in e and TITLE_RULE in e for e in B.validate_bundle(bad))
    # the same run in a bundle a 1.12.0 build imported is accepted (it stays until a re-import)
    bad["format_version"] = "1.12.0"
    assert not any("run run-999" in e for e in B.validate_bundle(bad))
    # an output said to be an average whose file states no average title is refused
    forged = json.loads(json.dumps(b))
    po = _po(forged, "ave_ZZ1_filter10")
    for e in forged["extended_context"]:
        if e.get("entry_id") in set(po["extended_context_entry_ids"]) and e.get("concept") == "scan_title":
            e["raw_literal"] = "S 1 (synthetic title 2.1 DTC)"
    assert any(TITLE_RULE in e and "keeps no average title" in e for e in B.validate_bundle(forged))


def test_a_1_12_0_bundle_holding_average_runs_validates_and_its_first_save_says_reimport(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(B, "is_average_title", lambda literal: False)  # what a 1.12.0 build made: the averages as runs
    out = tmp_path / "old"
    old = _import(_beamtime(tmp_path / "src"), out, capsys)
    monkeypatch.undo()
    held = B.average_title_runs(old)
    assert len(held) == 3
    old["format_version"] = "1.12.0"
    old.pop("format_upgrades", None)
    assert B.validate_bundle(old) == []
    (out / "bundle.json").write_bytes(B.encode(old))
    M.group(out)
    saved = M.load(out)
    assert saved["format_version"] == "1.13.0"
    [u] = saved["format_upgrades"]
    assert u["from_format_version"] == "1.12.0" and B.CHANGES_ADDED_IN["1.13.0"] in u["statement"]
    assert "3 of its runs" in u["statement"] and "re-import to keep them as processed outputs" in u["statement"]
    assert B.check_bundle(out) == []


def test_the_schema_adds_only_the_new_origin_rule_and_basis():
    s = B.bundle_schema()
    f = s["$defs"]["processed_output"]["properties"]["files"]["items"]["properties"]["processing_origin"]["properties"]
    assert f["rule_id"]["enum"] == ["isaac.processed_output.origin.v0", "isaac.processed_output.origin.engine_classification.v0",
                                    TITLE_RULE]
    assert f["basis"]["enum"] == ["line_1", "fields", "engine_classification", "average_title"]
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
    assert not [grp["group_id"] for grp in g["record_groups"] if any(k.startswith(("mca_v1:MERGE/", "mca_v1:averages/")) for k in grp["member_run_keys"])]
    assert B.validate_bundle(g) == []
