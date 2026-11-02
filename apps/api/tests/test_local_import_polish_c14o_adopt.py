"""c14o: every gated cell is all or nothing, on a stale target and on a clash. Synthetic only (SYN_/ZZ).

* MED-1: a gated cell's targets are kept per cell, whatever its sheet: an adopted Campaign Info answer that reaches
  every run is recorded for all of them or none under ``--supersede`` (before, only a Disagreements ruling was, so
  runs 2-9 took the new value and run-001 kept another: the beamtime split for good). A Technique cell stays one per
  File List row ("… via 'File List'!B5"), so its rows are gated per run.
* MED-2: a clash on a gated cell that reaches several targets records none of them either: each other target is
  listed in ``clashes``, naming the target that clashed, with "adopt again" and its ``decide`` command. A later
  ``--supersede`` import keeps nothing split.
* LOW-1: one person importing two copies of one workbook that rule differently, each with ``--supersede`` and the
  same ``--by``, alternates the value: each is their own correction (documented in the bundle contract).
* LOW-2: ``--by "Name "`` is the same person as ``Name`` (decisions store the stripped name).
* LOW-3: the command offered for a cell asked once for the whole beamtime says ``--value=<v>``.
* Also pinned: ``--only run:<id>`` on a run of a multi-run group (and its reach wording); a template never adopted
  imports as before (records over another value with ``--supersede``, clashes on that target alone without it).
"""

from __future__ import annotations

import copy
import json
import shlex
import shutil

import openpyxl
import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    PH, THEIRS, WHO, _adopt_json, _cand, _col, _d, _import, _row_of, _their_sheet, corpus, grouped, grouped_base,
    ticking)
from test_local_import_polish_c3t import _export, _fill
from test_local_import_polish_c7s import RUNS, TECH
from test_local_import_polish_c14g_adopt import _rule
from test_local_import_polish_c14j_adopt import _decisions_on
from test_local_import_polish_c14l_adopt import OTHER, _imp, _sheets, _state, _tid, _value_now
from test_local_import_grouping_cli import FIXTURE, SRC_STEM

FAC = "system.facility.facility_name"
FAC_CELL = "'Campaign Info'!B3"
NAME = "sample.material.name"


#: c15b M2: how a per-target reason of a cell reaching several targets ends
CELL_TAIL = ", or record this value for all {n} targets of this cell with one command ({key}: command)"


def _latest_value(bdir, tid):
    d = [x for x in M.load(bdir)["scientist_decisions"] if x["target"]["id"] == tid]
    return d[-1].get("value") if d else None


def _fac_tids(bdir):
    """Each run's facility name target (missing everywhere: a Campaign Info answer reaches all nine)."""
    tids = [m["value_id"] for m in M.load(bdir)["missing_values"] if m["target_field_path"] == FAC]
    assert len(tids) == 9, tids
    return tids


def _beamline_ruling(grouped, tmp_path, capsys, value):
    """Their sheet adopted, and its whole-beamtime Beamline/Instrument row ruled ``value``: (ruled workbook, targets)."""
    [s] = _sheets(grouped, tmp_path, 1)
    bl = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Beamline/Instrument")
    tids = [m["value_id"] for m in M.load(grouped)["missing_values"] if m.get("target_field_path") == bl["path"]]
    assert len(tids) == 9, tids
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {bl["id"]: value})
    return tmp_path / "Ar.xlsx", tids


def _from_cell(rep, cell):
    return [d for d in rep["decisions"] if d["cell"] == cell]


def _on(bdir, tids):
    """How many decisions the bundle holds on ``tids``."""
    return len([d for d in M.load(bdir)["scientist_decisions"] if d["target"]["id"] in set(tids)])


def _to(rep, tid):
    return [d for d in rep["decisions"] if d["target"]["id"] == tid]


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_an_adopted_campaign_info_answer_is_all_or_nothing_under_supersede(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: nine runs hold "ZZ Old Source"; adopt; run-001 gets "ZZ Since Source"; import with
    --supersede. Before, runs 2-9 took their sheet's value and run-001 kept the other, for good. r4-b M5: a Campaign
    Info value that differs from the one recorded is a whole-beamtime Disagreements row, never an adopted cell; its
    ruling is gated the same way: all nine or none."""
    tids = _fac_tids(grouped)
    M.decide(grouped, target_ids=tids, decision="correct", value="ZZ Old Source", by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    row = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Facility Name", kind="recorded")
    assert FAC_CELL not in T._marker(openpyxl.load_workbook(tmp_path / "A.xlsx"))["adopted"]
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {row["id"]: "Synthetic Light Source"})
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="ZZ Since Source", by=OTHER, orcid=None)
    n = _on(grouped, tids)
    for _ in range(2):  # and again: nothing flips
        rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
        assert not [d for d in rep["decisions"] if d["target"]["id"] in set(tids)]
        stale = {x["target"]["id"]: x for x in rep["stale_rulings"] if x["target"]["id"] in set(tids)}
        assert set(stale) == set(tids)
        for tid in tids[1:]:
            assert stale[tid]["reason"].startswith(
                f"this ruling reaches 9 targets and is recorded for all of them or none, and {tids[0]} (run-001) was not "
                "made against the value recorded there now (its own line says why); nothing is recorded for this one "
                "either. Adopt again and rule against what is recorded now"), stale[tid]["reason"]
            # c15b M2: the cell's one command for all nine, never this target's own
            assert stale[tid]["reason"].endswith(CELL_TAIL.format(n=9, key="stale_by_cell"))
    assert _on(grouped, tids) == n  # nothing recorded
    assert {t: _latest_value(grouped, t) for t in tids} == {tids[0]: "ZZ Since Source",
                                                             **{t: "ZZ Old Source" for t in tids[1:]}}


def test_an_adopted_campaign_info_answer_is_recorded_for_all_runs_when_none_changed_since(grouped, tmp_path, capsys,
                                                                                          ticking):
    """The "all" of all or nothing: with nothing recorded since the adopt, the row's ruling is recorded on all nine
    (r4-b M5: the row named the value recorded, so without --supersede)."""
    tids = _fac_tids(grouped)
    M.decide(grouped, target_ids=tids, decision="correct", value="ZZ Old Source", by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    row = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Facility Name", kind="recorded")
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {row["id"]: "Synthetic Light Source"})
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert {d["target"]["id"] for d in rep["decisions"] if d["target"]["id"] in set(tids)} == set(tids)
    assert {_latest_value(grouped, t) for t in tids} == {"Synthetic Light Source"}


def test_adopted_technique_cells_are_gated_per_file_list_row(grouped, tmp_path, capsys, ticking):
    """A Technique cell is one per File List row: the row whose run changed since the adopt is not recorded, the
    others are (each row reaches its own run, so all or nothing never spans the rows)."""
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    b = M.load(grouped)
    own = {o["run_id"]: o.get("candidate_id") or o["value_id"] for o in [*b["candidates"], *b["missing_values"]]
           if o["target_field_path"] == TECH and o["run_id"] in RUNS}
    assert len(own) >= 3, own
    (rid, tid), *rest = sorted(own.items())
    M.decide(grouped, target_ids=[tid], decision="correct", value="XAS", by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys, "--supersede")
    stale = [x for x in rep["stale_rulings"] if x["header"] == "Technique"]
    assert [(x["run_id"], x["target"]["id"]) for x in stale] == [(rid, tid)]
    assert " via 'File List'!" in stale[0]["cell"]
    recorded = {d["run_id"]: d for d in rep["decisions"] if d["target_field_path"] == TECH}
    assert set(recorded) == {r for r, _t in rest}
    assert len({d["cell"] for d in recorded.values()}) == len(rest)  # one cell per row
    assert _latest_value(grouped, tid) == "XAS"


# --- MED-2 ----------------------------------------------------------------------------------------------------


def test_a_clash_on_a_whole_beamtime_ruling_records_none_of_its_targets(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: a Beamline ruling of BL11 with nothing recorded first; after the adopt, BL12 is recorded
    on one target. Before, a plain import recorded BL11 on 8 targets and clashed on the 9th, and a later --supersede
    import kept that split."""
    ruled, tids = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    n = _on(grouped, tids)
    rep = _imp(grouped, ruled, capsys)
    assert not [d for d in rep["decisions"] if d["target"]["id"] in tids]
    clashes = {c["target"]["id"]: c for c in rep["clashes"]}
    assert set(clashes) == set(tids)
    assert clashes[tids[0]]["reason"].startswith("an earlier scientist decision gives a different value (recorded now: "
                                                 f"'BL12' by {OTHER} (2099-01-01), from a decide); skipped, and "
                                                 "--supersede does not record it either")
    for tid in tids[1:]:
        assert clashes[tid]["reason"] == (
            f"this ruling reaches 9 targets and is recorded for all of them or none, and {tids[0]} (run-001) holds a "
            "different value this ruling was not made against (its own line says why); nothing is recorded for this "
            "one either. Adopt again and rule against what is recorded now" + CELL_TAIL.format(n=9, key="clashes_by_cell"))
    # a later --supersede import keeps nothing split: the ruling never saw BL12, so it is stale for all nine
    rep = _imp(grouped, ruled, capsys, "--supersede")
    assert not [d for d in rep["decisions"] if d["target"]["id"] in tids]
    assert {x["target"]["id"] for x in rep["stale_rulings"]} == set(tids)
    assert _on(grouped, tids) == n
    assert {t: _latest_value(grouped, t) for t in tids} == {tids[0]: "BL12", **{t: None for t in tids[1:]}}


def test_a_clash_on_a_ruling_made_against_the_value_now_says_supersede_records_it_everywhere(grouped, tmp_path, capsys,
                                                                                             ticking):
    """BL12 is on one target BEFORE the adopt, so the ruling saw it: without --supersede it clashes there and records
    nowhere ("pass --supersede"); with --supersede it is recorded on all nine."""
    [s] = _sheets(grouped, tmp_path, 1)
    bl = _d(_adopt_json(grouped, s, tmp_path / "probe.xlsx", capsys), "Beamline/Instrument")
    tids = [m["value_id"] for m in M.load(grouped)["missing_values"] if m.get("target_field_path") == bl["path"]]
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    ruled, again = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    assert again == tids
    rep = _imp(grouped, ruled, capsys)
    assert not [d for d in rep["decisions"] if d["target"]["id"] in tids]
    clashes = {c["target"]["id"]: c for c in rep["clashes"]}
    assert set(clashes) == set(tids)
    assert clashes[tids[0]]["reason"].startswith("an earlier scientist decision gives a different value (recorded now: "
                                                 f"'BL12' by {OTHER} (2099-01-01), from a decide); skipped (pass "
                                                 "--supersede to record this one)")
    assert clashes[tids[1]]["reason"] == (
        f"this ruling reaches 9 targets and is recorded for all of them or none, and {tids[0]} (run-001) holds a "
        "different value, from an earlier scientist decision (its own line says why); nothing is recorded for this one "
        "either. Pass --supersede to record it for all of them, or adopt again and rule against what is recorded now"
        + CELL_TAIL.format(n=9, key="clashes_by_cell"))
    rep = _imp(grouped, ruled, capsys, "--supersede")
    assert {d["target"]["id"] for d in rep["decisions"]} >= set(tids) and not rep["stale_rulings"]
    assert {_latest_value(grouped, t) for t in tids} == {"BL11"}


def test_a_clash_on_an_adopted_campaign_info_answer_records_none_of_its_targets(grouped, tmp_path, capsys, ticking):
    """The same without --supersede for an adopted Campaign Info answer: before, it recorded on runs 2-9."""
    tids = _fac_tids(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="ZZ Since Source", by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys)
    assert not _from_cell(rep, FAC_CELL)
    clashes = {c["target"]["id"]: c for c in rep["clashes"] if c["cell"] == FAC_CELL}
    assert set(clashes) == set(tids)
    assert clashes[tids[4]]["reason"].startswith(
        f"this cell reaches 9 targets and is recorded for all of them or none, and {tids[0]} (run-001) holds a "
        "different value this cell was not made against")
    assert {t: _latest_value(grouped, t) for t in tids} == {tids[0]: "ZZ Since Source", **{t: None for t in tids[1:]}}


def test_a_template_never_adopted_records_as_before(grouped, tmp_path, capsys, ticking):
    """A Campaign Info cell typed into an exported template is not gated: without --supersede it clashes on the one
    target holding another value and records on the rest; with --supersede it records over it."""
    tids = _fac_tids(grouped)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="ZZ Since Source", by=OTHER, orcid=None)
    filled = _fill(_export(grouped, tmp_path), tmp_path / "f.xlsx", {("Campaign Info", "B3"): "ZZ Typed Source"})
    rep = _imp(grouped, filled, capsys)
    assert {d["target"]["id"] for d in _from_cell(rep, FAC_CELL)} == set(tids[1:])
    assert [c["target"]["id"] for c in rep["clashes"]] == [tids[0]]
    assert rep["clashes"][0]["reason"].startswith("an earlier scientist decision gives a different value (recorded now: "
                                                  f"'ZZ Since Source' by {OTHER} (2099-01-01), from a decide); skipped "
                                                  "(pass --supersede to record this one)")
    rep = _imp(grouped, filled, capsys, "--supersede")
    assert [d["target"]["id"] for d in _from_cell(rep, FAC_CELL)] == [tids[0]]
    assert not rep["clashes"] and not rep["stale_rulings"]
    assert {_latest_value(grouped, t) for t in tids} == {"ZZ Typed Source"}


# --- LOW-1, LOW-2 ---------------------------------------------------------------------------------------------


def _two_copies(grouped, tmp_path, capsys):
    """One adopted workbook copied, the copies ruling run-007's pH 2 and 7: (their paths, the pH target)."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)  # 12, the file's
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "W.xlsx", capsys)
    shutil.copy(tmp_path / "W.xlsx", tmp_path / "Wcopy.xlsx")
    _rule(tmp_path / "W.xlsx", tmp_path / "Wa.xlsx", {p["id"]: 2})
    _rule(tmp_path / "Wcopy.xlsx", tmp_path / "Wb.xlsx", {p["id"]: 7})
    return tmp_path / "Wa.xlsx", tmp_path / "Wb.xlsx", tid


def _imp_by(grouped, x, capsys, by, *extra):
    capsys.readouterr()
    code = cli.main(["bundle", "template", "import", str(grouped), str(x), "--by", by, "--json", "--apply", *extra])
    out = capsys.readouterr()
    assert code == 0, out.err
    return json.loads(out.out)


def test_one_person_importing_two_diverging_copies_alternates_the_value_as_intended(grouped, tmp_path, capsys, ticking):
    wa, wb, tid = _two_copies(grouped, tmp_path, capsys)
    values = []
    for _ in range(3):
        for x in (wa, wb):
            rep = _imp(grouped, x, capsys, "--supersede")
            assert len(_to(rep, tid)) == 1 and not rep["stale_rulings"]
            values.append(_value_now(grouped, tid))
    assert values == [2, 7, 2, 7, 2, 7]  # each import is their own correction of the value their last one recorded
    assert {(d.get("decided_by") or {}).get("name") for d in _decisions_on(grouped, tid)[1:]} == {WHO}


def test_by_with_a_trailing_space_is_the_same_person(grouped, tmp_path, capsys, ticking):
    wa, wb, tid = _two_copies(grouped, tmp_path, capsys)
    assert len(_to(_imp_by(grouped, wa, capsys, WHO, "--supersede"), tid)) == 1
    rep = _imp_by(grouped, wb, capsys, WHO + " ", "--supersede")
    assert len(_to(rep, tid)) == 1 and not rep["stale_rulings"]
    assert _value_now(grouped, tid) == 7
    assert (_decisions_on(grouped, tid)[-1].get("decided_by") or {}).get("name") == WHO
    # a colleague's copy is still theirs, not the scientist's
    rep = _imp_by(grouped, wa, capsys, " Colleague Synthetic Scientist ", "--supersede")
    assert not _to(rep, tid) and "from another copy of this workbook" in rep["stale_rulings"][0]["reason"]


# --- LOW-3 ----------------------------------------------------------------------------------------------------


def _name_asked_once(bdir):
    """This bundle with Sample Name asked once for the whole beamtime (no run holds a target of its own for it)."""
    b = M.load(bdir)
    gone = {c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == NAME}
    for r in b["runs"]:
        r["candidate_ids"] = [x for x in r.get("candidate_ids") or () if x not in gone]
    b["candidates"] = [c for c in b["candidates"] if c["target_field_path"] != NAME]
    b["missing_values"] = [m for m in b["missing_values"] if m["target_field_path"] != NAME]
    record = next(m for m in b["missing_values"] if m["run_id"] is None)
    b["missing_values"].append({**copy.deepcopy(record), "value_id": "miss-9901", "target_field_path": NAME})
    M.save_bundle(bdir, b)


def test_the_beamtime_wide_command_says_value_equals_and_runs(grouped, tmp_path, capsys):
    _name_asked_once(grouped)
    xlsx = _export(grouped, tmp_path)
    filled = _fill(xlsx, tmp_path / "f.xlsx", {("File List", f"{_col('Sample Name')}{_row_of(xlsx, 'run-001')}"): "-ZZ1"})
    code, rep, err = _import(grouped, filled, capsys)
    assert code == 0, err
    [asked] = rep["asked_beamtime_wide"]
    assert asked["command"] == (f"isaac bundle decide <bundle_dir> --question {asked['question_id']} --decision correct "
                                f"--value=-ZZ1 --by {shlex.quote(WHO)}")
    assert asked["reason"].endswith(asked["command"])
    capsys.readouterr()
    argv = [str(grouped) if a == "<bundle_dir>" else a for a in shlex.split(asked["command"])[1:]]
    assert cli.main(argv) == 0, capsys.readouterr().err
    assert _latest_value(grouped, "miss-9901") == "-ZZ1"


# --- --only run:<id> in a multi-run group ---------------------------------------------------------------------

STEMS = ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV", "Q4_SYNcat_pH9_900mV"]


def _two_run_group(root):
    """Three synthetic runs; the counter position answered, so the first two are one record group."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src = root / "src"
    src.mkdir()
    acq = (FIXTURE / SRC_STEM).read_text().replace("01_01_ZZ1_acid_beforeCycling_filter10_100mV", SRC_STEM)
    scan = (FIXTURE / f"{SRC_STEM}_dir" / f"{SRC_STEM}_001.dat").read_text()
    (src / "Zz_XAS.mac").write_text((FIXTURE / "Zz_XAS.mac").read_text())
    for stem in STEMS:
        (src / stem).write_text(acq.replace(SRC_STEM, stem))
        d = src / f"{stem}_dir"
        d.mkdir()
        for i in (1, 2):
            (d / f"{stem}_{i:03d}.txt").write_text(scan.replace(SRC_STEM, stem))
    bdir = root / "b"
    assert cli.main(["import", str(src), "--out", str(bdir)]) == 0
    M.group(bdir)
    M.decide(bdir, target_ids=["experiment"], decision="set_counter_positions", value=None, positions=[2], by=WHO,
             orcid=None)
    M.group(bdir, regroup=True)
    return bdir


def test_only_a_run_of_a_multi_run_group_reaches_that_run_alone(tmp_path, capsys):
    bdir = _two_run_group(tmp_path)
    b = M.load(bdir)
    run_of = {r["run_key"]: r["run_id"] for r in b["runs"]}
    groups = sorted([run_of[k] for k in g["member_run_keys"]] for g in Q.live_groups(b))
    assert groups == [["run-001", "run-002"], ["run-003"]]
    q = next(q for q in Q.consolidate(b)["questions"]
             if q.get("target_field_path") == TECH and list(q["per_scope_targets"]) == ["experiment"])
    capsys.readouterr()
    code = cli.main(["bundle", "decide", str(bdir), "--question", q["question_id"], "--only", "run:run-002",
                     "--decision", "correct", "--value", "XES", "--by", WHO])
    out = capsys.readouterr()
    assert code == 0, out.err
    reply = json.loads(out.out)
    assert reply["statement"] == (
        f"'XES' recorded for 1 run: technique. It reaches run:run-002 only (1 run; 1 answer slot added for runs the "
        f"files give no target of their own). The beamtime-wide question {q['question_id']} covers the rest of the "
        "beamtime; if its answer differs from this one, this run's group's record gets two values for technique and "
        "fills nothing for it.")
    assert reply["reach"] == {"question_id": q["question_id"], "path": TECH, "scope": "run:run-002", "runs": 1,
                              "slots_added": 1, "other_groups": 1}
    b = M.load(bdir)
    [slot] = [m for m in b["missing_values"] if m["target_field_path"] == TECH and m["run_id"] is not None]
    assert slot["run_id"] == "run-002" and reply["recorded"] == [slot["value_id"]]  # never run-001, of its group
    assert [d["target"]["id"] for d in b["scientist_decisions"] if d.get("value") == "XES"] == [slot["value_id"]]
