"""Bundle 1.11.0: the scientists' QUICK MERGES (a file the engine classifies ``processed_spectrum``: no header, every
line two numbers) are processed outputs linked by LEGACY NUMBER — never runs, never record groups.

Measured defect this pins (a real BL15-2 beamtime): 32 headerless two-column ``.txt`` files in a ``MERGE/`` folder
each became a run through the two-column reader, so 32 measurements nobody performed got record groups and questions
(128 groups where 96 are real), and processing said "no XAS channel" for each. SYNTHETIC ``SYN`` names and the
committed ``tests/fixtures/bl15`` files only (their values are invented).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import openpyxl
import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import workbook_answers as W

from test_local_import_reader_xdi import make_xdi

REPO_ROOT = Path(__file__).resolve().parents[3]
FIX = REPO_ROOT / "tests" / "fixtures" / "bl15"
SPEC_STEM = "03_01_ZZ1_acid_beforeCycling_100mV_filter10"
RUN = "04_01_SYN_filter10_again"
WHO = "SYN Scientist"


def _spec_run(root: Path, stem: str, *, scans: bool = True) -> None:
    """A SPEC acquisition and its ``_dir`` copy (as the real archive has), with one scan export when ``scans``."""
    spec = (FIX / "spec" / SPEC_STEM).read_text().replace(SPEC_STEM, stem)
    (root / f"{stem}_dir").mkdir(parents=True)
    (root / stem).write_text(spec)
    (root / f"{stem}_dir" / stem).write_text(spec)
    if scans:
        scan = (FIX / "scans" / f"{SPEC_STEM}_001.dat").read_text()
        (root / f"{stem}_dir" / f"{stem}_001.dat").write_text(scan)


def _quick(path: Path) -> Path:
    """A quick merge: the committed fixture's bytes (two numbers per line, no header) under another name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIX / "processed" / "63_06_ZZ1_f10.txt", path)
    return path


def _beamtime(root: Path) -> Path:
    bt = root / "SYN_BL00_2100-01_QuickMerges"
    for stem in (RUN, "05_01_SYN_filter10", "32_03_SYN_after1400", "32_03_SYN_after1500", "43_04_SYN_f20",
                 "44_04_SYN_f35"):
        _spec_run(bt, stem)
    for name in ("04_01_SYN_f10", "43_44_04_SYN_f20_f35", "32_03_SYN", "04_02_SYN_f10", "SYN_ave"):
        _quick(bt / "MERGE" / f"{name}.txt")
    _quick(bt / "elsewhere" / "05_01_SYN_f10.txt")  # the same kind of file, in no MERGE folder
    make_xdi(bt / "proc" / f"{RUN}.nor")  # an Athena XDI output: keeps the stem rule
    return bt


def _import(capsys, src: Path, out: Path) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    return json.loads((out / "bundle.json").read_text())


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("qm")
    src = _beamtime(root / "src")
    out = root / "out"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    return src, out, json.loads((out / "bundle.json").read_text())


@pytest.fixture()
def b(built):
    return json.loads(json.dumps(built[2]))


def _po(b: dict, label: str, directory: str | None = None) -> dict:
    return next(p for p in b["processed_outputs"] if p["label"] == label and (directory is None or p["directory"] == directory))


def _run(b: dict, stem: str) -> dict:
    return next(r for r in b["runs"] if r["stem"] == stem)


# --- origin: the engine's classification, never a run -----------------------------------------------------------------


def test_a_quick_merge_is_a_processed_output_by_the_engines_classification_never_a_run(b):
    assert not [r for r in b["runs"] if r["source_type"] == "generic:two_column_v1"]
    scan_paths = {s["relative_path"] for r in b["runs"] for s in r["scans"]}
    po = _po(b, "04_01_SYN_f10")
    [f] = po["files"]
    assert f["relative_path"] == "MERGE/04_01_SYN_f10.txt" and f["relative_path"] not in scan_paths
    assert f["processing_origin"] == B.engine_processing_origin()
    assert f["processing_origin"]["rule_id"] == "isaac.processed_output.origin.engine_classification.v0"
    assert f["processing_origin"]["basis"] == "engine_classification"
    src = next(s for s in b["sources"] if s["source_id"] == f["source_id"])
    assert src["classification"]["source_type"] == "processed_spectrum"  # the engine's own reading of the content
    assert po["role"] == "reference_result" and po["becomes_a_record"] is False and "rough reference" in po["statement"]
    assert B.validate_bundle(b) == []


def test_outside_a_merge_folder_it_is_still_a_processed_output(b):
    po = _po(b, "05_01_SYN_f10", "elsewhere")
    assert B.is_engine_classified(po)
    [link] = po["proposed_links"]
    assert link["run_stem"] == "05_01_SYN_filter10"


def test_quick_merges_get_no_record_group_and_no_question(built, capsys, tmp_path):
    src, out, _ = built
    work = tmp_path / "out"
    shutil.copytree(out, work)
    M.group(work)
    g = M.load(work)
    keys = {k for grp in g["record_groups"] for k in grp["member_run_keys"]}
    assert keys == {r["run_key"] for r in g["runs"]}  # only real runs
    groups = {grp["group_id"] for grp in g["record_groups"]}
    for q in Q.consolidate(g, include_answered=True)["questions"]:
        scope = q.get("scope") or ""
        assert not scope.startswith("group:") or scope[6:] in groups
    assert g["counts"]["processed_outputs"] == 7 and g["counts"]["runs"] == 6  # 6 quick merges + 1 XDI output


# --- the link rule ----------------------------------------------------------------------------------------------------


def test_a_quick_merge_links_to_its_run_by_legacy_and_electrode_number(b):
    [link] = _po(b, "04_01_SYN_f10", "MERGE")["proposed_links"]
    run = _run(b, RUN)
    assert link["rule_id"] == "isaac.processed_output.link_by_legacy_number.v0" and link["match"] == "legacy_number"
    assert (link["run_id"], link["run_key"], link["run_stem"], link["status"]) == (run["run_id"], run["run_key"], RUN, "proposed")
    # the name difference is said, and decides nothing
    assert "04 is read as the run's legacy number and 01 as its electrode number" in link["assumption"]
    assert "this output: f10; the run: filter10, again" in link["assumption"]


def test_several_legacy_numbers_span_several_runs_and_link_none(b):
    po = _po(b, "43_44_04_SYN_f20_f35")
    assert po["proposed_links"] == []
    note = po["link_note"]
    assert note["code"] == "spans_several_runs" and note["match"] == "legacy_number"
    assert note["run_keys"] == sorted([_run(b, "43_04_SYN_f20")["run_key"], _run(b, "44_04_SYN_f35")["run_key"]])


def test_a_legacy_number_two_runs_share_is_ambiguous(b):
    po = _po(b, "32_03_SYN")
    assert po["proposed_links"] == [] and po["link_note"]["code"] == "ambiguous"
    assert len(po["link_note"]["run_keys"]) == 2


def test_another_electrode_number_links_nothing(b):
    po = _po(b, "04_02_SYN_f10")
    assert po["proposed_links"] == []
    assert po["link_note"]["code"] == "no_run_named_like_it" and po["link_note"]["match"] == "legacy_number"
    assert po["link_note"]["run_keys"] == [_run(b, RUN)["run_key"]]  # the run with legacy number 04, named, not linked


def test_a_name_with_no_leading_number_stays_unlinked(b):
    po = _po(b, "SYN_ave")
    assert po["proposed_links"] == [] and po["link_note"]["code"] == "no_run_named_like_it" and po["link_note"]["match"] is None
    assert b["counts"]["processed_outputs_linked"] == 3 and b["counts"]["processed_outputs_unlinked"] == 4


def _r(stem, run_id, legacy, scans=1):
    return {"stem": stem, "run_key": f"k:{stem}", "run_id": run_id, "run_candidate": True, "legacy_number": legacy,
            "scan_count": scans, "scans": [{"scan_index": i} for i in range(1, scans + 1)]}


def _engine_po(label):
    return {"label": label, "files": [{"processing_origin": B.engine_processing_origin()}]}


def test_the_rule_without_an_import_one_number_names_no_electrode_and_a_run_without_scans_is_said():
    # the shape of the real IrOxBase 01_/02_ merges: one number, and the run's own words (SYNpellet, oldPellet, f35)
    runs = [_r("01_SYNpellet_oldPellet_f35", "run-001", 1), _r("07_02_SYN_x", "run-002", 7, scans=0)]
    one, empty = _engine_po("01_SYNpellet_oldPellet_f35_0p2wtpc"), _engine_po("07_02_SYN_f10")
    B.propose_processed_links([one, empty], runs)
    assert one["proposed_links"][0]["run_id"] == "run-001"  # neither name carries an electrode number
    assert ("neither name carries an electrode number, and they share the name word(s) SYNpellet, oldPellet, f35"
            in one["proposed_links"][0]["assumption"])
    assert empty["proposed_links"] == [] and empty["link_note"]["code"] == "run_has_no_scans"
    assert empty["link_note"]["run_keys"] == ["k:07_02_SYN_x"]


def test_one_number_and_no_shared_name_word_links_nothing():
    """Review M3: ``01_IrO2_ref`` must not link to ``01_RuO2_pellet`` on the number alone."""
    runs = [_r("01_SYNother_pellet", "run-001", 1)]
    po = _engine_po("01_SYNoxide_ref")
    B.propose_processed_links([po], runs)
    assert po["proposed_links"] == []
    assert po["link_note"]["code"] == "no_run_named_like_it" and po["link_note"]["match"] == "legacy_number"
    assert po["link_note"]["run_keys"] == ["k:01_SYNother_pellet"] and "share no name word" in po["link_note"]["detail"]
    # an electrode number is enough on its own: two numbers name the run, whatever the words
    runs2 = [_r("01_02_SYNother_pellet", "run-001", 1)]
    po2 = _engine_po("01_02_SYNoxide_ref")
    B.propose_processed_links([po2], runs2)
    assert po2["proposed_links"][0]["run_id"] == "run-001"


def test_an_xdi_output_keeps_the_stem_rule_and_its_origin(b):
    po = _po(b, RUN, "proc")
    assert not B.is_engine_classified(po)
    assert po["files"][0]["processing_origin"]["rule_id"] == B.PROCESSED_ORIGIN_RULE_ID
    [link] = po["proposed_links"]
    assert (link["rule_id"], link["match"], link["run_stem"]) == (B.LINK_RULE_ID, "exact", RUN)
    assert set(link) == {"rule_id", "status", "match", "scan_selection_literal", "scan_selection_basis", "assumption",
                         "run_id", "run_key", "run_stem", "group_id"}
    assert link["assumption"] is None and po["link_note"] is None


def test_the_validator_re_runs_the_rule_and_refuses_a_tampered_link_or_origin(b):
    forged = json.loads(json.dumps(b))
    _po(forged, "32_03_SYN")["proposed_links"] = [{**_po(b, "04_01_SYN_f10", "MERGE")["proposed_links"][0]}]
    _po(forged, "32_03_SYN")["link_note"] = None
    assert any("link is not what isaac.processed_output.link_by_legacy_number.v0 gives" in e for e in B.validate_bundle(forged))
    dropped = json.loads(json.dumps(b))
    _po(dropped, "04_01_SYN_f10", "MERGE")["proposed_links"] = []
    assert any("link_by_legacy_number" in e for e in B.validate_bundle(dropped))
    # an XDI output relabelled engine-classified would move to the other link rule: refused by its source's class
    relabelled = json.loads(json.dumps(b))
    po = _po(relabelled, RUN, "proc")
    po["files"][0]["processing_origin"] = B.engine_processing_origin()
    assert any("is not classified processed_spectrum" in e for e in B.validate_bundle(relabelled))


def test_the_validator_refuses_a_relabelled_source_class_too(b):
    """Review M2: the classification cannot be re-run without the file, so what the bundle holds is re-derived: an XDI
    output whose origin AND source class are both relabelled still states its own header, which no headerless
    processed spectrum can."""
    bad = json.loads(json.dumps(b))
    po = _po(bad, RUN, "proc")
    f = po["files"][0]
    f["processing_origin"] = B.engine_processing_origin()
    next(s for s in bad["sources"] if s["source_id"] == f["source_id"])["classification"]["source_type"] = "processed_spectrum"
    B.propose_processed_links(bad["processed_outputs"], bad["runs"])  # the forger re-runs the link rule as well
    B.apply_derivations(bad)
    errors = B.validate_bundle(bad)
    assert any("states something about itself" in e for e in errors), errors
    # and a quick merge whose file is swapped for another source is refused by path and sha256
    swapped = json.loads(json.dumps(b))
    sf = _po(swapped, "SYN_ave")["files"][0]
    sf["sha256"] = "0" * 64
    assert any("is not the file its source" in e for e in B.validate_bundle(swapped))


def test_the_validator_re_derives_a_spec_runs_legacy_number_from_its_stem(b):
    """Review M2: a forged legacy number would forge a link that the re-run rule then agrees with."""
    bad = json.loads(json.dumps(b))
    _run(bad, "32_03_SYN_after1500")["legacy_number"] = 33  # now 32_03_SYN names one run only
    B.propose_processed_links(bad["processed_outputs"], bad["runs"])
    B.apply_derivations(bad)
    assert _po(bad, "32_03_SYN")["proposed_links"]  # the forged link the rule alone would accept
    errors = B.validate_bundle(bad)
    assert any("legacy_number 33 is not what its stem '32_03_SYN_after1500' states (32)" in e for e in errors), errors


# --- only beside SPEC acquisitions (review H1) ------------------------------------------------------------------------


def test_a_root_of_two_column_files_alone_keeps_its_runs_with_a_note(tmp_path, capsys):
    from test_local_import_reader_two_column import make_two

    bt = tmp_path / "SYN_other_facility"
    make_two(bt / "SYN_sample_a.txt")
    make_two(bt / "SYN_sample_b.txt")
    out = tmp_path / "out"
    b = _import(capsys, bt, out)
    runs = [r for r in b["runs"] if r["source_type"] == "generic:two_column_v1"]
    assert sorted(r["stem"] for r in runs) == ["SYN_sample_a", "SYN_sample_b"] and b["processed_outputs"] == []
    for r in runs:
        [note] = [a for a in r["other_relationships"]["anomalies"] if a["kind"] == B.ENGINE_PROCESSED_NOTE_KIND]
        assert note["source_relative_path"] == r["scans"][0]["relative_path"] and "a scientist says" in note["detail"]
    assert B.validate_bundle(b) == []
    assert "quick merges" not in (out / "summary.md").read_text()
    # an engine-classified output in such a root is refused: the validator re-derives the condition from the runs
    forged = json.loads(json.dumps(b))
    run = forged["runs"].pop()
    forged["processed_outputs"].append({**_po_like(run, forged)})
    assert any("applies only beside a SPEC acquisition run" in e for e in B.validate_bundle(forged))


def _po_like(run, bundle):
    sid = run["scans"][0]["source_id"]
    src = next(s for s in bundle["sources"] if s["source_id"] == sid)
    return {"processed_output_id": "po-00000000000000aa", "output_key": run["run_key"], "label": run["label"],
            "directory": "", "role": "reference_result", "is_acquisition": False, "becomes_a_record": False,
            "statement": "forged", "reader": {"reader_id": "two_column_reader_v1", "profile": "two_column_v1",
                                              "profile_version": "1", "statements_total": 0, "statements_kept": 0},
            "files": [{"source_id": sid, "relative_path": src["relative_path"], "sha256": src["content_sha256"],
                       "size_bytes": src["size_bytes"], "extension": ".txt", "columns": [], "points": 3,
                       "processing_origin": B.engine_processing_origin()}],
            "states": {"processed_by": [], "element_symbol": [], "element_edge": [], "demeter_output_filetype": []},
            "anomalies": [], "extended_context_entry_ids": [], "proposed_links": [],
            "link_note": {"code": "no_run_named_like_it", "match": None, "run_keys": [],
                          "detail": "Its name starts with no number, so no legacy number names a run; it stays unlinked."},
            "value_state": "source_recorded"}


def test_two_column_files_beside_spec_runs_are_outputs_even_unlinked(b):
    spec = [r for r in b["runs"] if r["source_type"] == "spec_acquisition"]
    assert spec and B.quick_merges_apply(b["runs"])
    quick = [p for p in b["processed_outputs"] if B.is_engine_classified(p)]
    assert len(quick) == 6 and len([p for p in quick if not p["proposed_links"]]) == 4
    ave = _po(b, "SYN_ave")  # unlinked, still an output, never a run
    assert ave["proposed_links"] == [] and not [r for r in b["runs"] if r["stem"] == "SYN_ave"]
    assert not [r for r in b["runs"] if any(a.get("kind") == B.ENGINE_PROCESSED_NOTE_KIND
                                            for a in (r["other_relationships"].get("anomalies") or ()))]
    # a 1.11.0 import holding one of them as a run is refused (the condition re-derived from the stored runs)
    bad = json.loads(json.dumps(b))
    po = bad["processed_outputs"].pop(bad["processed_outputs"].index(_po(bad, "SYN_ave")))
    f = po["files"][0]
    bad["runs"].append({**_run(bad, RUN), "run_id": "run-999", "run_key": "two_column_v1:MERGE/SYN_ave", "stem": "SYN_ave",
                        "label": "SYN_ave", "source_type": "generic:two_column_v1", "legacy_number": None,
                        "scans": [{"source_id": f["source_id"], "relative_path": f["relative_path"], "scan_index": None}],
                        "scan_count": 1, "candidate_ids": [], "conflict_ids": [], "data_quality_note_ids": []})
    assert any("run run-999 is a file the engine classifies processed_spectrum" in e for e in B.validate_bundle(bad))


def test_the_summary_says_what_the_quick_merges_are(built):
    _, out, _ = built
    text = (out / "summary.md").read_text()
    assert ("6 processed files the engine reads as processed spectra" in text
            and "2 with a proposed link to a run by legacy number, 4 unlinked" in text
            and "1 of them spanning several runs" in text and "1 naming a legacy number several runs share" in text)
    assert "1 processed file from the scientists (Athena/Demeter)" in text  # the XDI output, said as before


# --- older bundles ----------------------------------------------------------------------------------------------------


def test_a_1_10_0_bundle_still_validates_and_its_first_save_says_what_1_11_0_added(tmp_path, capsys, monkeypatch):
    # what an older build made: the quick merges as runs (the engine classification not yet a processed-output rule)
    monkeypatch.setattr(B, "ENGINE_PROCESSED_SOURCE_TYPE", "no_such_class")
    out = tmp_path / "old"
    old = _import(capsys, _beamtime(tmp_path / "src"), out)
    monkeypatch.undo()
    assert [r for r in old["runs"] if r["source_type"] == "generic:two_column_v1"]
    assert not [p for p in old["processed_outputs"] if B.is_engine_classified(p)]
    old["format_version"] = "1.10.0"
    old.pop("format_upgrades", None)
    assert B.validate_bundle(old) == []
    (out / "bundle.json").write_bytes(B.encode(old))
    assert B.check_bundle(out) == []
    M.group(out)
    saved = M.load(out)
    assert saved["format_version"] == B.FORMAT_VERSION == "1.11.0"
    [u] = saved["format_upgrades"]
    assert u["from_format_version"] == "1.10.0" and B.CHANGES_ADDED_IN["1.11.0"] in u["statement"]
    # review L5: the runs it still holds of the quick merges are named, and re-import is said to fix them
    held = B.quick_merge_runs(saved)
    assert len(held) == 6
    assert f"{len(held)} of its runs ({', '.join(held[:5])}, ...) are files the engine reads as processed spectra" in u["statement"]
    assert "re-import to keep them as processed outputs" in u["statement"]
    assert B.check_bundle(out) == []


def test_a_1_10_0_validator_shape_refuses_nothing_old_and_the_new_enums_are_the_approved_ones():
    s = B.bundle_schema()
    f = s["$defs"]["processed_output"]["properties"]["files"]["items"]["properties"]["processing_origin"]["properties"]
    assert f["rule_id"]["enum"] == ["isaac.processed_output.origin.v0", "isaac.processed_output.origin.engine_classification.v0"]
    assert f["basis"]["enum"] == ["line_1", "fields", "engine_classification"]
    link = s["$defs"]["processed_output"]["properties"]["proposed_links"]["items"]["properties"]
    assert link["rule_id"]["enum"] == ["isaac.processed_output.link_by_run_stem.v0", "isaac.processed_output.link_by_legacy_number.v0"]
    assert link["match"]["enum"] == ["exact", "scan_selection_suffix", "legacy_number"]
    note = s["$defs"]["processed_output"]["properties"]["link_note"]["anyOf"][1]["properties"]
    assert note["code"]["enum"][-2:] == ["spans_several_runs", "run_has_no_scans"]
    assert "legacy_number" in note["match"]["enum"]


# --- answers given to the runs that disappear are reported, never applied ----------------------------------------------


def _workbook(path: Path, folder: str, rows: list[tuple[str, str]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("2 Missing (blocks export)")
    ws["A1"] = "SYN title line"
    head = ["Ref", "Folder", "Question", "YOUR ANSWER", "Your notes", "ISAAC question ID"]
    for c, h in enumerate(head, start=1):
        ws.cell(2, c, h)
    for i, (qid, answer) in enumerate(rows, start=3):
        for c, v in enumerate([f"2-{i:04d}", folder, "SYN question", answer, None, qid], start=1):
            ws.cell(i, c, v)
    wb.save(path)
    return path


def test_answers_to_the_quick_merge_runs_an_older_build_asked_about_are_reported_never_applied(tmp_path, capsys, monkeypatch):
    src = _beamtime(tmp_path / "src")
    monkeypatch.setattr(B, "ENGINE_PROCESSED_SOURCE_TYPE", "no_such_class")
    old_dir = tmp_path / "old"
    old_b = _import(capsys, src, old_dir)
    monkeypatch.undo()
    old_b["format_version"] = "1.10.0"  # what the older build labelled it
    (old_dir / "bundle.json").write_bytes(B.encode(old_b))
    M.group(old_dir)
    old = M.load(old_dir)
    gone = {r["run_key"] for r in old["runs"] if r["source_type"] == "generic:two_column_v1"}
    gone_groups = {g["group_id"] for g in old["record_groups"] if set(g["member_run_keys"]) <= gone}
    orphaned = sorted(q["question_id"] for q in Q.consolidate(old, include_answered=True)["questions"]
                      if (q.get("scope") or "").removeprefix("group:") in gone_groups)
    assert orphaned
    new_dir = tmp_path / "new"
    _import(capsys, src, new_dir)
    M.group(new_dir)
    new_ids = {q["question_id"] for q in Q.consolidate(M.load(new_dir), include_answered=True)["questions"]}
    assert not set(orphaned) & new_ids
    folder = M.load(new_dir)["source_root"]["label"]
    xlsx = _workbook(tmp_path / "answers.xlsx", folder, [(orphaned[0], "290")])
    before = (new_dir / "bundle.json").read_bytes()
    for apply in (False, True):
        rep = W.import_answers(new_dir, xlsx, by=WHO, apply=apply)
        [p] = rep["not_applied"]
        assert p["id"] == orphaned[0] and p["problem"] == "not_resolving" and "the bundle changed" in p["reason"]
        assert rep["decisions"] == [] and rep["id_rows"]["not_resolving"] == 1
    assert M.load(new_dir)["scientist_decisions"] == []
    assert json.loads((new_dir / "bundle.json").read_bytes())["scientist_decisions"] == json.loads(before)["scientist_decisions"]


# --- processing: a rough reference, from the stored link ---------------------------------------------------------------

np = None


@pytest.fixture()
def proc():
    global np
    np = pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    import test_local_import_processing as TP
    from isaac_api.local_import.processing import quick_merge as QM
    return TP, QM


def _case_with_quick_merge(tmp_path, TP, scans, values, *, name="01_01_SYN_f10.txt"):
    stem = "01_01_SYN_filter10"
    bdir, root, bundle = TP.make_case(tmp_path, [(stem, [TP.spec_file(s) for s in scans], {"sample_name": "SYN"})])
    rel = f"MERGE/{name}"
    (root / "MERGE").mkdir()
    (root / rel).write_text("".join(f"{e:.4f}  {v:.10e}\n" for e, v in zip(TP.GRID, values)))
    run = bundle["runs"][0]
    bundle["processed_outputs"] = [{
        "processed_output_id": "po-0000000000000001", "label": name[:-4], "directory": "MERGE",
        "files": [{"source_id": None, "relative_path": rel, "sha256": TP._sha(root / rel), "size_bytes": None,
                   "extension": ".txt", "columns": ["column_1", "column_2"], "points": len(values),
                   "processing_origin": B.engine_processing_origin()}],
        "proposed_links": [{"rule_id": B.LEGACY_LINK_RULE_ID, "status": "proposed", "match": "legacy_number",
                            "run_id": run["run_id"], "run_key": run["run_key"], "run_stem": stem, "group_id": None}],
        "link_note": None}]
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _signal(cols):
    """What ISAAC merges for a fluorescence scan: signal / I0, from the values as the scan file writes them."""
    return np.array([float(f"{v:.6f}") for v in cols["vortDT"]]) / np.array([float(f"{v:.6f}") for v in cols["I0"]])


def test_a_normalised_quick_merge_is_compared_as_stored_never_refitted_and_never_preferred(tmp_path, proc):
    TP, QM = proc
    scans = [TP.fluo_scan(s) for s in (1, 2)]
    normalised = 0.5 + np.arctan((TP.GRID - TP.E0) / 0.5) / np.pi
    bdir, root = _case_with_quick_merge(tmp_path, TP, scans, normalised)
    r = TP.isaac(TP.run_process(bdir, source_root=root))
    [c] = r[QM.RESULT_KEY]
    assert c["normalization"] == "already_normalized" and c["metrics"]["edge_step_scientist"] == 1.0
    assert "raw_comparison" not in c and "scan_subset_hint" not in c
    assert any("compared as stored, edge step 1, never re-fitted" in a for a in c["assumptions"])
    assert any(a.startswith("column 1 is read as energy in eV") for a in c["assumptions"])
    assert c["matched_by"]["rule_id"] == B.LEGACY_LINK_RULE_ID
    assert c["role"] == "rough_reference" and c["preferred_for_record"] is False and c["treated_as_truth"] is False
    assert c["verdict"] in ("agree", "differs") and c["metrics"]["rms_norm"] is not None
    # ISAAC's own result is untouched: the same result id as with no quick merge at all
    (tmp_path / "plain").mkdir()
    plain_dir, plain_root, _ = TP.make_case(tmp_path / "plain",[("01_01_SYN_filter10", [TP.spec_file(s) for s in scans], {"sample_name": "SYN"})])
    plain = TP.isaac(TP.run_process(plain_dir, source_root=plain_root))
    assert plain["result_id"] == r["result_id"] and QM.RESULT_KEY not in plain
    assert r["preferred_for_record"] == plain["preferred_for_record"] and r["review_flags"] == plain["review_flags"]


def test_a_merge_of_scans_1_2_and_4_names_that_subset_as_a_hint_only(tmp_path, proc):
    TP, QM = proc
    scans = [TP.fluo_scan(s, noise=0.02) for s in (1, 2, 3, 4)]
    quick = np.mean([_signal(scans[i]) for i in (0, 1, 3)], axis=0)
    bdir, root = _case_with_quick_merge(tmp_path, TP, scans, quick)
    r = TP.isaac(TP.run_process(bdir, source_root=root))
    [c] = r[QM.RESULT_KEY]
    assert c["normalization"] == "normalized_with_isaac_parameters"
    assert any("normalised here with ISAAC's OWN parameters" in a for a in c["assumptions"])
    raw = c["raw_comparison"]
    assert raw["median_ratio_to_isaac_merged_mu"] == pytest.approx(1.0, abs=0.05) and raw["relative_rms_residual"] > 0
    h = c["scan_subset_hint"]
    assert h["tried"] and h["subsets_tried"] == 15 and h["subsets_that_rebuild"] == 1 and h["applied"] is False
    assert h["scans_not_in_it"] == ["01_01_SYN_filter10_003.dat"]
    assert '"exclude_scans": {"' + r["group_id"] + '": ["01_01_SYN_filter10_003.dat"]}' in h["exclude_scans_snippet"]
    assert h["statement"].startswith("HINT ONLY, never applied")
    assert [i.get("skip_reason") for i in r["inputs"]] == [None] * 4  # nothing was left out of ISAAC's merge
    assert c["preferred_for_record"] is False


def test_a_first_column_outside_the_groups_energy_range_is_not_read_as_energy(tmp_path, proc):
    TP, QM = proc
    scans = [TP.fluo_scan(s) for s in (1, 2)]
    bdir, root = _case_with_quick_merge(tmp_path, TP, scans, _signal(scans[0]))
    rel = root / "MERGE" / "01_01_SYN_f10.txt"
    rel.write_text("".join(f"{i:.4f}  {v:.10e}\n" for i, v in enumerate(_signal(scans[0]))))
    data = json.loads((bdir / "bundle.json").read_text())
    data["processed_outputs"][0]["files"][0]["sha256"] = TP._sha(rel)
    (bdir / "bundle.json").write_text(json.dumps(data))
    [c] = TP.isaac(TP.run_process(bdir, source_root=root))[QM.RESULT_KEY]
    assert c["verdict"] == "not_comparable" and "not read as an energy" in c["reason"] and c["assumptions"] == []
