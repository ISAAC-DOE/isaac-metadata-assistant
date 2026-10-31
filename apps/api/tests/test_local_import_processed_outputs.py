"""Bundle 1.2.0: the scientists' own processed outputs (Athena/Demeter XDI) are REFERENCE
RESULTS, kept in ``processed_outputs[]`` — never a run, never a record group.

Measured defect this pins (real corpus, HEAD 05e11c2e): every XDI stem-group the generic
reader formed became an ordinary run, and grouping proposed record groups (future ISAAC
records) made of processed files. SYNTHETIC ``SYN_`` files only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_reader_mca import make_mca
from test_local_import_reader_ssrl_xdc import make_scan
from test_local_import_reader_two_column import make_two
from test_local_import_reader_xdi import make_xdi

DEMETER = "# XDI/1.0 Demeter/0.9.26"
PROC = ("proc/SYN_cell.nor", "proc/SYN_cell.xmu")


def _acquisitions(root: Path) -> Path:
    """Genuine acquisitions, one per generic reader that is not XDI."""
    make_scan(root / "bt" / "SYN_run_A.001")
    make_scan(root / "bt" / "SYN_run_A.002")
    make_mca(root / "mca" / "SYN_spec.mca")
    make_two(root / "two" / "SYN_cell.txt")
    return root


def _with_processed(root: Path) -> Path:
    _acquisitions(root)
    make_xdi(root / PROC[0])  # Athena on line 1, Element.symbol Zz, Element.edge K
    make_xdi(root / PROC[1], first_line=DEMETER, fields=("Demeter.output_filetype: xmu", "Column.1: energy eV", "Column.2: xmu"))
    return root


def _by_path(bundle: dict, obj):
    """``obj`` with every source id replaced by that source's relative path: source ids are
    positions in the inventory, which a processed file beside the scans shifts."""
    path_of = {s["source_id"]: s["relative_path"] for s in bundle["sources"]}
    return json.loads(re.sub(r'"(src-[0-9]{4,})"', lambda m: json.dumps("path:" + path_of[m.group(1)]), json.dumps(obj)))


def _import(capsys, root: Path, out: Path) -> dict:
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    capsys.readouterr()
    return json.loads((out / "bundle.json").read_text())


@pytest.fixture()
def pair(tmp_path, capsys):
    """The same beamtime folder name imported twice: without and with processed outputs."""
    plain = _import(capsys, _acquisitions(tmp_path / "a" / "SYN_beamtime"), tmp_path / "out_a")
    mixed = _import(capsys, _with_processed(tmp_path / "b" / "SYN_beamtime"), tmp_path / "out_b")
    return plain, mixed, tmp_path / "out_a", tmp_path / "out_b"


# --- never a run --------------------------------------------------------------------------------


def test_an_athena_output_is_a_processed_output_never_a_run(pair):
    _, b, _, _ = pair
    scan_paths = {s["relative_path"] for r in b["runs"] for s in r["scans"]}
    assert not scan_paths & set(PROC)
    assert not [r for r in b["runs"] if r["source_type"] == "generic:xdi_v1"]
    [po] = b["processed_outputs"]
    assert po["label"] == "SYN_cell" and po["role"] == "reference_result"
    assert po["is_acquisition"] is False and po["becomes_a_record"] is False
    assert sorted(f["relative_path"] for f in po["files"]) == sorted(PROC)
    assert all(f["source_id"] and len(f["sha256"]) == 64 for f in po["files"])
    assert po["reader"]["reader_id"] == "xdi_reader_v1"
    assert not {u["relative_path"] for u in b["unread_files"]} & set(PROC)  # claimed, so not "unread"
    assert B.validate_bundle(b) == []


def test_what_the_file_states_about_itself_is_recorded_literally_with_locators(pair):
    _, b, _, _ = pair
    [po] = b["processed_outputs"]
    st = po["states"]
    assert sorted(s["literal"] for s in st["processed_by"]) == ["Athena/0.9.24", "Demeter/0.9.26"]
    assert all(s["locator"] == "line:1" for s in st["processed_by"])
    assert [s["literal"] for s in st["element_symbol"]] == ["Zz"] and st["element_symbol"][0]["locator"].startswith("line:")
    assert [s["literal"] for s in st["element_edge"]] == ["K"]
    assert [s["literal"] for s in st["demeter_output_filetype"]] == ["xmu"]
    origins = {f["relative_path"]: f["processing_origin"] for f in po["files"]}
    assert origins[PROC[0]]["names_a_processing_application"] and origins[PROC[0]]["has_athena_fields"]
    assert origins[PROC[1]]["has_demeter_output_filetype"]


def test_its_header_statements_survive_as_processed_output_evidence_not_run_values(pair):
    a, b, _, _ = pair
    [po] = b["processed_outputs"]
    entries = [e for e in b["extended_context"] if e.get("processed_output_id") == po["processed_output_id"]]
    assert entries and len(entries) == po["reader"]["statements_kept"] == po["reader"]["statements_total"]
    assert [e["entry_id"] for e in entries] == po["extended_context_entry_ids"]
    assert {"Element.symbol", "Element.edge", "Demeter.output_filetype"} <= {e["concept"] for e in entries}
    for e in entries:
        assert e["run_id"] is None and e["scope"] == "processed_output"
        assert e["value_state"] == "source_recorded" and e["is_official_field_value"] is False and e["official_path"] is None
    # behavioural: the processed files add NO candidate (no value) anywhere in the bundle
    assert _by_path(b, b["candidates"]) == _by_path(a, a["candidates"])


# --- genuine acquisitions unchanged ------------------------------------------------------------


def test_genuine_acquisitions_are_identical_with_a_processed_output_beside_them(pair):
    a, b, _, _ = pair
    assert {r["source_type"] for r in a["runs"]} >= {"generic:ssrl_xdc_v1", "generic:mca_v1", "generic:two_column_v1"}
    for section in ("runs", "missing_values", "questions"):
        assert _by_path(b, b[section]) == _by_path(a, a[section]), section
    assert _by_path(b, [e for e in b["extended_context"] if e.get("run_id")]) == _by_path(a, [e for e in a["extended_context"] if e.get("run_id")])
    assert b["counts"]["runs"] == a["counts"]["runs"]
    assert Q.consolidate(b)["counts"] == Q.consolidate(a)["counts"]  # no question about a processed file


def test_an_xdi_that_states_no_processing_application_stays_an_acquisition_run(tmp_path, capsys):
    root = _acquisitions(tmp_path / "SYN_beamtime")
    make_xdi(root / "x" / "SYN_raw.xdi", first_line="# XDI/1.0 SYN_Beamline/0.1",
             fields=("Element.symbol: Zz", "Column.1: energy eV", "Column.2: mutrans"))
    b = _import(capsys, root, tmp_path / "out")
    assert b["processed_outputs"] == []
    [run] = [r for r in b["runs"] if r["source_type"] == "generic:xdi_v1"]
    assert run["scans"][0]["relative_path"] == "x/SYN_raw.xdi"


# --- never a record group --------------------------------------------------------------------------


def test_a_processed_output_never_becomes_a_record_group(pair):
    _, _, out_a, out_b = pair
    M.group(out_a)
    M.group(out_b)
    a, b = M.load(out_a), M.load(out_b)
    assert B.check_bundle(out_b) == []
    run_keys = {r["run_key"] for r in b["runs"]}
    assert all(set(g["member_run_keys"]) <= run_keys for g in b["record_groups"])
    assert not any(k.startswith("xdi_v1:") for g in b["record_groups"] for k in g["member_run_keys"])
    assert [g["group_id"] for g in b["record_groups"]] == [g["group_id"] for g in a["record_groups"]]
    assert b["processed_outputs"][0]["processed_output_id"] not in json.dumps(b.get("grouping_questions") or [])


# --- the link rule: exact only ---------------------------------------------------------------------


def _po(b: dict, label: str) -> dict:
    return next(p for p in b["processed_outputs"] if p["label"] == label)


def test_the_link_rule_proposes_only_on_an_exact_name_or_the_runs_own_scans(tmp_path, capsys):
    root = _acquisitions(tmp_path / "SYN_beamtime")  # SYN_run has scans 1 and 2; SYN_cell has one scan
    make_two(root / "dup" / "a" / "SYN_dup.txt")
    make_two(root / "dup" / "b" / "SYN_dup.txt")
    names = ("SYN_cell", "SYN_cell_1", "SYN_cell_500", "SYN_run_1-2", "SYN_run_2", "SYN_run_1-3", "SYN_run_3",
             "SYN_condA_cell", "SYN_cellx", "SYN_cell_a", "SYN_dup")
    for name in names:
        make_xdi(root / "proc" / f"{name}.nor")
    make_xdi(root / "proc_case" / "syn_cell.nor")  # own folder: some filesystems ignore case
    out = tmp_path / "out"
    b = _import(capsys, root, out)
    cell = next(r for r in b["runs"] if r["stem"] == "SYN_cell")
    run_a = next(r for r in b["runs"] if r["stem"] == "SYN_run")
    assert sorted(s["scan_index"] for s in run_a["scans"]) == [1, 2]

    [exact] = _po(b, "SYN_cell")["proposed_links"]
    assert exact["match"] == "exact" and exact["run_key"] == cell["run_key"] and exact["status"] == "proposed"
    [one] = _po(b, "SYN_cell_1")["proposed_links"]  # its only scan, counted (it states no index)
    assert (one["match"], one["scan_selection_literal"], one["scan_selection_basis"], one["run_id"]) == ("scan_selection_suffix", "1", "scan_count", cell["run_id"])
    # R-5: the 1..N numbering is an assumption, stated on the link, in `show` and in the summary
    assert one["assumption"] == "the run states no scan index; its 1 scans are taken to be numbered 1..1"
    assert "1 of them assume scans are numbered 1..N because the run states no scan index" in (out / "summary.md").read_text()
    assert cli.main(["bundle", "show", str(out), "processed-output", _po(b, "SYN_cell_1")["processed_output_id"]]) == 0
    assert "taken to be numbered 1..1" in capsys.readouterr().out
    [sel] = _po(b, "SYN_run_1-2")["proposed_links"]
    assert (sel["scan_selection_literal"], sel["scan_selection_basis"], sel["run_id"]) == ("1-2", "scan_indices", run_a["run_id"])
    assert sel["assumption"] is None and exact["assumption"] is None
    assert _po(b, "SYN_run_2")["proposed_links"][0]["run_id"] == run_a["run_id"]
    # a number that is not one of the run's scans is another sample or condition: no link
    for unlinked in ("SYN_cell_500", "SYN_run_1-3", "SYN_run_3", "SYN_condA_cell", "SYN_cellx", "syn_cell", "SYN_cell_a"):
        po = _po(b, unlinked)
        assert po["proposed_links"] == [] and po["link_note"]["code"] == "no_run_named_like_it", unlinked
    dup = _po(b, "SYN_dup")
    assert dup["proposed_links"] == [] and dup["link_note"]["code"] == "ambiguous" and len(dup["link_note"]["run_keys"]) == 2
    assert b["counts"]["processed_outputs_linked"] == 4 and b["counts"]["processed_outputs_unlinked"] == 8
    assert B.validate_bundle(b) == []


def _run(stem, run_id, scans, *, candidate=True):
    return {"stem": stem, "run_key": f"k:{stem}:{run_id}", "run_id": run_id, "run_candidate": candidate,
            "scan_count": len(scans), "scans": [{"scan_index": i} for i in scans]}


def _links(label, runs):
    po = {"label": label}
    B.propose_processed_links([po], runs)
    return po


def test_a_link_needs_a_run_with_scans_and_an_exact_name_blocks_the_suffix_rule():
    # exact name, but the run has no scan: nothing is linked (kills "drop the scan-count requirement")
    po = _links("SYN_z", [_run("SYN_z", "run-001", [])])
    assert po["proposed_links"] == [] and po["link_note"]["code"] == "exact_name_run_has_no_scans"
    # a not-a-run-candidate run is not a link target either
    assert _links("SYN_z", [_run("SYN_z", "run-001", [1], candidate=False)])["proposed_links"] == []
    # ANY run carrying the exact name (zero-scan included) blocks the scan-selection fallback
    blocked = _links("SYN_z_1", [_run("SYN_z_1", "run-001", []), _run("SYN_z", "run-002", [1, 2])])
    assert blocked["proposed_links"] == [] and blocked["link_note"]["code"] == "exact_name_run_has_no_scans"
    assert _links("SYN_z_1", [_run("SYN_z", "run-002", [1, 2])])["proposed_links"][0]["run_id"] == "run-002"
    # a reversed range selects nothing
    assert _links("SYN_z_2-1", [_run("SYN_z", "run-002", [1, 2])])["proposed_links"] == []


def test_a_link_names_its_record_group_only_by_membership_and_a_forged_one_is_refused(tmp_path, capsys):
    root = _acquisitions(tmp_path / "SYN_beamtime")
    make_xdi(root / "proc" / "SYN_cell.nor")
    out = tmp_path / "out"
    b = _import(capsys, root, out)
    assert _po(b, "SYN_cell")["proposed_links"][0]["group_id"] is None  # nothing grouped yet
    M.group(out)
    b = M.load(out)
    [link] = _po(b, "SYN_cell")["proposed_links"]
    [group] = [g for g in b["record_groups"] if link["run_key"] in g["member_run_keys"]]
    assert link["group_id"] == group["group_id"]
    assert B.validate_bundle(b) == []
    forged = json.loads(json.dumps(b))
    _po(forged, "SYN_cell")["proposed_links"][0]["group_id"] = "rg-0000000000000000"
    assert any("link group disagrees" in e for e in B.validate_bundle(forged))


def test_the_validator_refuses_a_processed_file_that_is_also_a_run_scan(pair):
    _, b, _, _ = pair
    bad = json.loads(json.dumps(b))
    run = next(r for r in bad["runs"] if r["source_type"] == "generic:two_column_v1")
    run["scans"].append({"source_id": None, "relative_path": PROC[0], "scan_index": None})
    assert any("is also a run's scan" in e for e in B.validate_bundle(bad))


# --- versions ----------------------------------------------------------------------------------


def test_a_1_1_0_bundle_without_the_section_still_loads_validates_and_mutates(pair):
    a, _, out_a, _ = pair
    old = json.loads(json.dumps(a))
    old["format_version"] = "1.1.0"
    old.pop("processed_outputs")
    for key in list(old["counts"]):
        if key.startswith("processed_output"):
            old["counts"].pop(key)
    assert B.validate_bundle(old) == []
    (out_a / "bundle.json").write_bytes(B.encode(old))
    assert B.check_bundle(out_a) == []
    M.group(out_a)  # a mutation re-derives and re-validates
    saved = M.load(out_a)
    # NOT relabelled 1.2.0: that would claim its processed outputs had been separated
    assert saved["format_version"] == "1.1.0" and "processed_outputs" not in saved
    assert B.check_bundle(out_a) == []
    one_oh = json.loads(json.dumps(old))
    one_oh["format_version"] = "1.0.0"
    (out_a / "bundle.json").write_bytes(B.encode(one_oh))
    M.save_bundle(out_a, M.load(out_a))
    assert M.load(out_a)["format_version"] == "1.1.0"  # raised to at most 1.1.0


def test_a_1_2_0_bundle_must_carry_the_section(pair):
    _, b, _, _ = pair
    bad = json.loads(json.dumps(b))
    bad.pop("processed_outputs")
    for key in list(bad["counts"]):
        if key.startswith("processed_output"):
            bad["counts"].pop(key)
    assert any("processed_outputs" in e for e in B.validate_bundle(bad))


def _legacy(tmp_path, capsys, monkeypatch) -> Path:
    """A 1.1.0 bundle as the previous build wrote it: the Athena XDI file is a RUN."""
    root = _acquisitions(tmp_path / "SYN_beamtime")
    make_xdi(root / PROC[0])
    out = tmp_path / "legacy"
    with monkeypatch.context() as m:
        m.setattr(B, "_processing_origin", lambda scan, line1: (None, None))  # the old behaviour
        _import(capsys, root, out)
    old = M.load(out)
    assert [r["stem"] for r in old["runs"] if r["source_type"] == "generic:xdi_v1"] == ["SYN_cell"]
    old["format_version"] = "1.1.0"
    old.pop("processed_outputs")
    for key in list(old["counts"]):
        if key.startswith("processed_output"):
            old["counts"].pop(key)
    assert B.validate_bundle(old) == []
    (out / "bundle.json").write_bytes(B.encode(old))
    return out


def test_grouping_and_build_records_refuse_a_pre_1_2_0_bundle_holding_athena_outputs_as_runs(tmp_path, capsys, monkeypatch):
    out = _legacy(tmp_path, capsys, monkeypatch)
    assert B.legacy_processed_runs(M.load(out))
    before = (out / "bundle.json").read_bytes()
    assert cli.main(["bundle", "group", str(out)]) == 2
    err = capsys.readouterr().err
    assert "Re-import" in err and "separate the scientists' processed outputs" in err
    assert cli.main(["bundle", "build-records", str(out)]) == 2
    assert "separate the scientists' processed outputs" in capsys.readouterr().err
    with pytest.raises(M.MutationRefused, match="separate the scientists' processed outputs"):
        M.process(out)  # R-6
    assert (out / "bundle.json").read_bytes() == before  # nothing written


# --- counts and summary ---------------------------------------------------------------------------


def test_counts_and_summary_report_processed_outputs_separately(pair):
    a, b, _, out_b = pair
    c = b["counts"]
    assert (c["processed_outputs"], c["processed_output_files"], c["processed_outputs_linked"], c["processed_outputs_unlinked"]) == (1, 2, 1, 0)
    assert c["runs"] == a["counts"]["runs"]
    summary = (out_b / "summary.md").read_text()
    assert (
        "- 2 processed files from the scientists (Athena/Demeter), kept as reference results, not records "
        "(1 output(s) by name; 1 with a proposed link to a run by the name rule"
    ) in summary
    assert ", 0 unlinked). Not counted as runs; no question is asked about them." in summary
    plain = (out_b.parent / "out_a" / "summary.md").read_text()
    assert "processed files from the scientists" not in plain  # none: no line at all


def test_a_stem_group_mixing_a_stated_and_an_unstated_xdi_file_is_split_file_by_file(tmp_path, capsys):
    root = _acquisitions(tmp_path / "SYN_beamtime")
    make_xdi(root / "mix" / "SYN_mix.nor")
    make_xdi(root / "mix" / "SYN_mix.xdi", first_line="# XDI/1.0 SYN_Beamline/0.1", fields=("Column.1: energy eV", "Column.2: mutrans"))
    b = _import(capsys, root, tmp_path / "out")
    [po] = b["processed_outputs"]
    assert [f["relative_path"] for f in po["files"]] == ["mix/SYN_mix.nor"]
    [run] = [r for r in b["runs"] if r["source_type"] == "generic:xdi_v1"]
    assert [s["relative_path"] for s in run["scans"]] == ["mix/SYN_mix.xdi"]
    run_entries = [e for e in b["extended_context"] if e.get("run_id") == run["run_id"]]
    po_entries = [e for e in b["extended_context"] if e.get("processed_output_id") == po["processed_output_id"]]
    assert {e["relative_path"] for e in run_entries} == {"mix/SYN_mix.xdi"}
    assert {e["relative_path"] for e in po_entries} == {"mix/SYN_mix.nor"}
    ids = [e["entry_id"] for e in b["extended_context"]]
    assert len(ids) == len(set(ids))
    assert B.validate_bundle(b) == []


# --- classification edges (review A-4) ----------------------------------------------------------

RAW_FIELDS = ("Element.symbol: Zz", "Column.1: energy eV", "Column.2: mutrans")


@pytest.mark.parametrize(
    "first_line, extra, processed, disagrees",
    [
        ("# XDI/1.0 SYN_DAQ/1.0 Athena/0.9.26", (), True, False),   # Athena signs it as a token
        ("# XDI/1.0 athena/2.0", (), True, False),                  # case ignored, on the token only
        ("# XDI/1.0 SYN_Athenaish/1.0", (), False, False),          # not a substring match
        ("# XDI/1.0 SYN_DAQ/1.0", ("Athena.note: see logbook",), False, True),
        ("# XDI/1.0 SYN_DAQ/1.0", ("Demeter.output_filetype: nor",), False, True),
        ("# XDI/1.0 SYN_DAQ/1.0", ("Demeter.output_filetype:",), False, False),  # empty states nothing
        ("# XDI/1.0", ("Demeter.output_filetype: nor",), True, False),          # no application named
        ("# XDI/1.0", (), False, False),
    ],
)
def test_line_1_decides_and_fields_never_override_another_named_application(tmp_path, capsys, first_line, extra, processed, disagrees):
    root = _acquisitions(tmp_path / "SYN_beamtime")
    make_xdi(root / "x" / "SYN_e.xdi", first_line=first_line, fields=RAW_FIELDS + extra)
    b = _import(capsys, root, tmp_path / "out")
    assert bool(b["processed_outputs"]) is processed
    runs = [r for r in b["runs"] if r["source_type"] == "generic:xdi_v1"]
    assert bool(runs) is (not processed)
    if runs:
        kinds = [a["kind"] for a in runs[0]["other_relationships"]["anomalies"]]
        assert ("processing_statement_disagrees" in kinds) is disagrees
    assert B.validate_bundle(b) == []


# --- the validator re-derives the links (review A-2) and checks references (A-7) ----------------


def test_the_validator_re_runs_the_link_rule_and_refuses_a_forged_or_dropped_link(tmp_path, capsys):
    root = _acquisitions(tmp_path / "SYN_beamtime")
    make_xdi(root / "proc" / "SYN_cell.nor")
    out = tmp_path / "out"
    _import(capsys, root, out)
    M.group(out)
    b = M.load(out)
    other = next(r for r in b["runs"] if r["stem"] != "SYN_cell" and r["scan_count"])

    retarget = json.loads(json.dumps(b))
    _po(retarget, "SYN_cell")["proposed_links"][0].update(run_id=other["run_id"], run_key=other["run_key"], run_stem="SYN_cell")
    B.apply_derivations(retarget)
    errors = B.validate_bundle(retarget)
    assert any("is not what isaac.processed_output.link_by_run_stem.v0 gives" in e for e in errors)

    mismatch = json.loads(json.dumps(b))
    _po(mismatch, "SYN_cell")["proposed_links"][0]["run_id"] = other["run_id"]
    assert any("by another run's key or stem" in e for e in B.validate_bundle(mismatch))

    dropped = json.loads(json.dumps(b))
    p = _po(dropped, "SYN_cell")
    p["proposed_links"], p["link_note"] = [], {"code": "no_run_named_like_it", "match": None, "run_keys": [], "detail": "x"}
    B.apply_derivations(dropped)
    assert any("is not what" in e for e in B.validate_bundle(dropped))


def test_a_statement_naming_an_unknown_processed_output_or_also_a_run_is_refused(pair):
    _, b, _, _ = pair
    pid = b["processed_outputs"][0]["processed_output_id"]
    unknown = json.loads(json.dumps(b))
    e = next(x for x in unknown["extended_context"] if x.get("processed_output_id") == pid)
    e["processed_output_id"] = "po-0000000000000000"
    assert any("names unknown processed output po-0000000000000000" in x for x in B.validate_bundle(unknown))
    both = json.loads(json.dumps(b))
    e = next(x for x in both["extended_context"] if x.get("processed_output_id") == pid)
    e["run_id"] = both["runs"][0]["run_id"]
    assert any("is attributed to a processed output AND a run" in x for x in B.validate_bundle(both))


# --- CLI list / show (and the exposure show records) -------------------------------------------


def test_bundle_list_and_show_processed_outputs_and_show_records_an_exposure(pair, capsys):
    _, b, _, out_b = pair
    [po] = b["processed_outputs"]
    assert cli.main(["bundle", "list", str(out_b), "processed-outputs"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["total"] == 1 and listed["items"][0]["processed_output_id"] == po["processed_output_id"]
    assert listed["items"][0]["processed_by"] == ["Athena/0.9.24", "Demeter/0.9.26"]
    assert listed["items"][0]["proposed_link"]["match"] == "exact"
    assert not M.load(out_b).get("exposures")  # a list prints no header literal
    assert cli.main(["bundle", "show", str(out_b), "processed-output", po["processed_output_id"]]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["states"]["element_symbol"][0]["literal"] == "Zz"
    exposed = {(e["target"]["kind"], e["target"]["id"]) for e in M.load(out_b)["exposures"]}
    assert {("source", f["source_id"]) for f in po["files"]} <= exposed
    assert ("run", po["proposed_links"][0]["run_id"]) in exposed
    assert cli.main(["bundle", "show", str(out_b), "processed-output", "po-0000000000000000"]) == 6


def test_an_exported_file_named_like_several_runs_is_joined_to_none():
    """Review A-5: the stem lookup used to keep the LAST run of a shared name, silently."""
    from isaac_api.local_import import grouping as G

    runs = [{"stem": "SYN_x", "run_key": "A", "scan_count": 1}, {"stem": "SYN_x", "run_key": "B", "scan_count": 1},
            {"stem": "SYN_x.dat", "run_key": "C", "scan_count": 0}, {"stem": "SYN_y", "run_key": "D", "scan_count": 1},
            {"stem": "SYN_y.dat", "run_key": "E", "scan_count": 0}]
    issues = dict(G._exported_file_misreads({"runs": runs}))
    assert issues["C"]["related_run_key"] is None and issues["C"]["evidence"][0]["ambiguous_run_keys"] == ["A", "B"]
    assert issues["E"]["related_run_key"] == "D" and issues["E"]["evidence"][0]["ambiguous_run_keys"] == []
