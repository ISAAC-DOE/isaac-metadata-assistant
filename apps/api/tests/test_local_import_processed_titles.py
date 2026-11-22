"""A file whose own scan title names the scans it was computed from is a processed output, never a run (bundle 1.15.0;
audit of 18 Nov 2026, rule 5). SYNTHETIC files only: every name is ``SYN``/``ZZ``-prefixed and every value invented.

On real beamtimes the scientists' PyMca exports write a full SPEC header (``#F`` included) whose ``#S`` line names
other scans instead of a command: ``#S 1 (A 3.1 DTC + A 1.1 DTC)/2``, ``#S 1 Average of 8 from A 1.1 X to A 8.1 X``,
``#S 1 Norm. (A 1.1 FF1 + A 2.1 FF1)``. The engine called each a SPEC acquisition, so each became a run with no scans,
a record group and questions. What these pin:

* the engine classifies such a SPEC-format file as a processed spectrum by its CONTENT, whatever its name or folder
  (``bl15.classify.PROCESSED_TITLE_RULE_ID``); an acquisition's ``#S <n> gscan ...`` never is;
* beside SPEC acquisitions it is kept by the 1.13.0 average-title origin rule (one mechanism for a ``.mca`` and a
  SPEC-format file), with its title as the statement the validator re-derives it from;
* it is linked to the ONE run whose stem its title names and which has every scan it names
  (``isaac.processed_output.link_by_title_scans.v0``); a title naming no scans falls back to the legacy-number rule;
* a file name (``_ave``) or a folder alone (``averages/``) decides nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.bl15 import classify as C
from isaac_api.bl15.inventory import SourceRecord
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_quick_merges import FIX, SPEC_STEM, _spec_run  # noqa: E402
from test_local_import_reader_mca import make_mca  # noqa: E402

RUN = "SYN_cat_m600mV"
OTHER = "SYN_cat_1200mV"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def _spec_export(path: Path, title: str) -> Path:
    """A SPEC-format file with a `#F` header whose first `#S` line is ``title`` (the scientists' PyMca export)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#F /data/synthetic/{path.name}\n#D Mon Sep  9 03:00:00 2001\n\n#S {title}\n"
                    "#D Mon Sep  9 03:00:00 2001\n#N 2\n#L energy  DTC\n1000 0.1\n1005 0.2\n1010 0.3\n")
    return path


def _beamtime(root: Path) -> Path:
    bt = root / "SYN_BL00_2100-25_Averages"
    for stem in (RUN, OTHER):
        _spec_run(bt, stem)
    _spec_export(bt / "averages" / f"{RUN}_ave.dat", f"1 ({RUN} 1.1 DTC + {RUN} 1.1 I1)/2")
    _spec_export(bt / f"{OTHER}_norm.dat", f"1 Norm. ({OTHER} 1.1 DTC + {OTHER} 9.1 DTC)")  # scan 9: OTHER has none
    _spec_export(bt / "ZZ_both.dat", f"1 ({RUN} 1.1 DTC + {OTHER} 1.1 DTC)/2")              # two runs: no link
    _spec_export(bt / "AVERAGE" / "ZZ_ref.dat", "1 Average of 2 from ZZ_ref 1.1 Y to ZZ_ref 2.1 Y")  # no such run
    make_mca(bt / "PyMcaAdded" / f"{RUN}.mca")
    mca = bt / "PyMcaAdded" / f"{RUN}.mca"
    mca.write_text(mca.read_text().replace("#S 1 (synthetic title 2.1 DTC)", f"#S 1 ({RUN} 1.1 DTC + {RUN} 1.1 I1)/2"))
    # a file named and placed like an average whose content is an acquisition: its content decides, it is a run
    spec = (FIX / "spec" / SPEC_STEM).read_text().replace(SPEC_STEM, "SYN_cat_400mV_ave")
    (bt / "averages" / "SYN_cat_400mV_ave").write_text(spec)
    return bt


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("titles")
    out = root / "out"
    assert cli.main(["import", str(_beamtime(root / "src")), "--out", str(out)]) == 0
    return json.loads((out / "bundle.json").read_text())


def _po(b: dict, label: str) -> dict:
    return next(p for p in b["processed_outputs"] if p["label"] == label)


def _record(name: str) -> SourceRecord:
    return SourceRecord(archive_path=name, basename=name.rsplit("/", 1)[-1], extension=name.rsplit(".", 1)[-1] if "." in name else "",
                        size_bytes=1, content_sha256="0" * 64, parent_dir="", depth=0)


@pytest.mark.parametrize("title,processed", [
    ("1 (SYN_a 3.1 DTC_FF1 + SYN_a 1.1 DTC_FF1)/2", True),
    ("1 Average of 8 from SYN_a 1.1 vortDT to SYN_a 8.1 vortDT", True),
    ("1 Norm. (SYN_a 1.1 FF1 + SYN_a 2.1 FF1)", True),
    ("1 (Norm. SYN_ref 3.1 Y + Norm. SYN_ref 6.1 Y)/2", True),
    ("1 Norm. SYN_a 3.1 Y", True),
    ("1  gscan energy 1000 1020 5 1040 1 1100 2 0.500000", False),
    ("1 ascan th 0 1 10 1", False),
    ("1 (synthetic title 2.1 DTC)", False),
])
def test_the_engine_reads_what_a_title_is_by_its_content(title, processed):
    got = C.classify(_record("averages/SYN_x_ave.dat"), head_text=f"#F SYN_x\n#D Mon Sep  9 03:00:00 2001\n#S {title}\n")
    assert (got.source_type == "processed_spectrum") is processed
    if processed:
        assert got.confidence == C.CONFIDENCE_CONTENT and C.PROCESSED_TITLE_RULE_ID in got.reason
        assert B.is_average_title(title)
    else:
        assert got.source_type == "spec_acquisition" or "synthetic title" in title


@pytest.mark.parametrize("title,named", [
    ("1 (SYN(a)_01 1.1 DTC + SYN(a)_01 2.1 DTC)/2", [("SYN(a)_01", 1), ("SYN(a)_01", 2)]),
    ("1 (SYN_a 3.1 DTC_FF1 + SYN_a 1.1 DTC_FF1)/2", [("SYN_a", 3), ("SYN_a", 1)]),
    # an operator glued to a name: a stem holding `+` or `/`, or an operator with no space around it, cannot be told
    # apart, so the title names nothing to link by
    ("1 (SYN+C_01 1.1 DTC + SYN+C_01 2.1 DTC)/2", []),
    ("1 (SYN/x_01 1.1 DTC + SYN/x_01 3.1 DTC)/2", []),
    ("1 Norm. (SYN_a 1.1 FF1+SYN_a 2.1 FF1)", []),
])
def test_a_title_term_is_a_whole_name_never_a_cut_one(title, named):
    # review of PR 346, I1: a stem holding `+`, `(` or `/` is never cut to the part after it (`C_01`, `_01`, `x_01`)
    assert C.processed_title_scans(title) == named


def test_a_cut_name_links_no_other_run(tmp_path):
    runs = [{"run_id": "run-001", "run_key": "k1", "stem": "C_01", "run_candidate": True, "scan_count": 2, "scans": []}]
    po = {"processed_output_id": "po-1", "label": "ZZ", "files": [{"processing_origin": {"rule_id": B.AVERAGE_TITLE_ORIGIN_RULE_ID}}]}
    entry = {"processed_output_id": "po-1", "concept": "scan_title", "raw_literal": "1 (SYN+C_01 1.1 DTC + SYN+C_01 2.1 DTC)/2"}
    B.propose_processed_links([po], runs, [entry])
    assert po["proposed_links"] == []


def test_the_scans_a_title_names():
    assert C.processed_title_scans("1 (SYN_a 3.1 X + SYN_a 1.1 X)/2") == [("SYN_a", 3), ("SYN_a", 1)]
    assert C.processed_title_scans("1 Average of 3 from Norm. SYN_a 2.1 Y to Norm. SYN_a 4.1 Y") == [
        ("SYN_a", 2), ("SYN_a", 3), ("SYN_a", 4)]
    assert C.processed_title_scans("S 1 Average of 11 from Norm. SYN_scan 1.1 Y") == [("SYN_scan", 1)]
    assert C.processed_title_scans("1 gscan energy 1000 1020 5") == []


def test_a_titled_file_is_a_processed_output_never_a_run(built):
    b = built
    assert B.validate_bundle(b) == []
    stems = {r["stem"] for r in b["runs"]}
    assert {RUN, OTHER, "SYN_cat_400mV_ave"} <= stems  # the acquisitions, whatever they are named
    for label in (f"{RUN}_ave", f"{OTHER}_norm", "ZZ_both", "ZZ_ref", RUN):
        po = _po(b, label)
        [f] = po["files"]
        assert f["processing_origin"]["rule_id"] == B.AVERAGE_TITLE_ORIGIN_RULE_ID and po["becomes_a_record"] is False
        assert label not in stems or label == RUN  # the .mca shares RUN's stem; RUN is still its own run
    assert not any(r["stem"].endswith(("_ave.dat", "_norm.dat")) or r["stem"] in ("ZZ_both.dat", "ZZ_ref.dat")
                   for r in b["runs"])
    titled = _po(b, f"{RUN}_ave")
    [entry] = [e for e in b["extended_context"] if e["entry_id"] in titled["extended_context_entry_ids"]]
    assert entry["concept"] == "scan_title" and entry["raw_literal"] == f"1 ({RUN} 1.1 DTC + {RUN} 1.1 I1)/2"
    assert entry["locator"] == "line:4" and "names the scans it was computed from" in titled["statement"]


def test_it_is_linked_by_the_scans_its_title_names(built):
    b = built
    run = next(r for r in b["runs"] if r["stem"] == RUN)
    for label in (f"{RUN}_ave", RUN):  # the SPEC-format file and the .mca alike
        [link] = _po(b, label)["proposed_links"]
        assert link["rule_id"] == B.TITLE_LINK_RULE_ID and link["match"] == "title_scans"
        assert link["run_id"] == run["run_id"] and link["scan_selection_literal"] == "1"
    assert _po(b, f"{OTHER}_norm")["link_note"]["code"] == "no_run_named_like_it"  # it names a scan the run lacks
    assert _po(b, "ZZ_both")["link_note"]["code"] == "spans_several_runs"
    assert _po(b, "ZZ_ref")["link_note"]["code"] == "no_run_named_like_it"  # no run is named ZZ_ref: the legacy rule decides


def test_the_validator_re_runs_the_title_link(built):
    b = json.loads(json.dumps(built))
    po = _po(b, f"{RUN}_ave")
    po["proposed_links"][0]["scan_selection_literal"] = "1,2"
    assert any(B.TITLE_LINK_RULE_ID in e for e in B.validate_bundle(b))
    b = json.loads(json.dumps(built))
    entry = next(e for e in b["extended_context"] if e["entry_id"] in _po(b, f"{RUN}_ave")["extended_context_entry_ids"])
    entry["raw_literal"] = "1  gscan energy 1000 1020 5"  # no longer an average: the origin rule is not re-derived
    assert any(B.AVERAGE_TITLE_ORIGIN_RULE_ID in e for e in B.validate_bundle(b))


# --- a macro that was overwritten is not a conflict (rule 5, second half) -------------------------------------------


def _macro_beamtime(root: Path) -> Path:
    bt = root / "SYN_BL00_2100-26_Macros"
    for stem in ("SYN_cat_run9", "SYN_cat_hand"):
        _spec_run(bt, stem)
    # the run's own header says run9.mac started it; run9.mac was later overwritten and declares another target
    for p in (bt / "SYN_cat_run9", bt / "SYN_cat_run9_dir" / "SYN_cat_run9"):
        p.write_text(p.read_text().replace("#C spec  User = synthetic",
                                           "#C spec  User = synthetic\n#C Mon Sep  9 01:46:41 2001.  do run9.mac."))
    (bt / "run9.mac").write_text("newfile SYN_cat_later\numv Sx 1\n")
    return bt


def test_a_run_its_own_comment_line_says_a_macro_ran_is_no_acquired_never_declared_conflict(tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main(["import", str(_macro_beamtime(tmp_path / "src")), "--out", str(out)]) == 0
    b = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(b) == []
    rid = {r["stem"]: r["run_id"] for r in b["runs"]}
    never = {r for c in b["conflicts"] if c["kind"] == "acquired_never_declared" for r in c["run_ids"]}
    assert rid["SYN_cat_hand"] in never        # driven by hand, as far as the files say: the conflict stays
    assert rid["SYN_cat_run9"] not in never    # its header says run9.mac ran it
    assert b["counts"][B.NOT_A_CONFLICT_COUNT] >= 1
    assert B.not_a_conflict_text(1) in (out / "summary.md").read_text() or B.NOT_A_CONFLICT_RULES[0] in (out / "summary.md").read_text()


def test_conflict_ids_after_a_dropped_one_keep_their_numbers(tmp_path, capsys, monkeypatch):
    src = _macro_beamtime(tmp_path / "src")
    now = tmp_path / "now"
    assert cli.main(["import", str(src), "--out", str(now)]) == 0
    with monkeypatch.context() as mp:
        mp.setattr(B, "not_a_conflict", lambda *a, **k: None)  # the build before: every disagreement a conflict
        before = tmp_path / "before"
        assert cli.main(["import", str(src), "--out", str(before)]) == 0
    capsys.readouterr()
    was = {c["conflict_id"]: (c["kind"], c["subject"], c.get("candidate_id"))
           for c in json.loads((before / "bundle.json").read_text())["conflicts"]}
    got = json.loads((now / "bundle.json").read_text())["conflicts"]
    assert len(got) < len(was)
    for c in got:
        assert was[c["conflict_id"]] == (c["kind"], c["subject"], c.get("candidate_id"))
