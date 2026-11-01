"""c14p: a target that already holds a ruling's value never holds back the rest. Synthetic only (SYN_/ZZ).

* MED-1: a stale ruling whose target already holds its value ("the value is already 'BL11'; adopt again to settle
  this row") is listed, never a reason for all or nothing: run-002 held BL13 at adopt, the ruling says BL11, a
  colleague recorded BL11 there since: the other eight runs record BL11 (before: 0 of 9).
* LOW-1: "Pass --supersede to record it for all of them" is said only when every clash of the cell is one --supersede
  records; a clash it would not record is named instead.
* LOW-2: a target held back with another's clash says so (``blocked_by``), and the summary counts it apart from the
  clashes ("1 clash(es) (7 more target(s) of the same cell(s) held back with them: all or nothing)"); no target is in
  both ``clashes`` and ``stale_rulings``.
* LOW-3: an adopted answer cell is "this cell", settled by "Adopt again, then import with --supersede" (it has no
  Disagreements row to rule on), and that advice works.
"""

from __future__ import annotations

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    WHO, _adopt_json, _d, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14l_adopt import OTHER, _imp, _sheets
from test_local_import_polish_c14o_adopt import FAC_CELL, _beamline_ruling, _fac_tids, _from_cell, _latest_value

SAME = "Synthetic Light Source"  # their sheet's Campaign Info facility name


def _beamline_tids(grouped, tmp_path, capsys):
    """The nine Beamline/Instrument targets, read from a throwaway adopt (nothing is recorded by it)."""
    [s] = _sheets(grouped, tmp_path, 1)
    bl = _d(_adopt_json(grouped, s, tmp_path / "probe.xlsx", capsys), "Beamline/Instrument")
    tids = [m["value_id"] for m in M.load(grouped)["missing_values"] if m.get("target_field_path") == bl["path"]]
    assert len(tids) == 9, tids
    return tids


def _to(rep, tids):
    return [d for d in rep["decisions"] if d["target"]["id"] in set(tids)]


def _text(bdir, x, capsys):
    capsys.readouterr()
    code = cli.main(["bundle", "template", "import", str(bdir), str(x), "--by", WHO])
    assert code == 0
    return capsys.readouterr().out


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_p7_a_target_holding_the_ruling_value_never_holds_back_the_empty_runs(grouped, tmp_path, capsys, ticking):
    """run-002 held BL13 when BL11 was ruled; a colleague then recorded BL11 there (agreeing). Runs 1, 3-9 hold
    nothing: the ruling records on them, with or without --supersede."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL11", by=OTHER, orcid=None)
    rep = _imp(grouped, ruled, capsys)
    assert {d["target"]["id"] for d in _to(rep, tids)} == set(tids) - {tids[1]}
    [stale] = rep["stale_rulings"]
    assert stale["target"]["id"] == tids[1]
    assert stale["reason"].endswith("nothing is recorded for this ruling: the value is already 'BL11'; adopt again to "
                                    "settle this row")
    assert not rep["clashes"]
    assert {_latest_value(grouped, t) for t in tids} == {"BL11"}
    rep = _imp(grouped, ruled, capsys, "--supersede")  # nothing left to record, nothing flips
    assert not _to(rep, tids) and [x["target"]["id"] for x in rep["stale_rulings"]] == [tids[1]]
    assert {_latest_value(grouped, t) for t in tids} == {"BL11"}


def test_p1_a_campaign_info_value_recorded_on_one_run_since_the_adopt_never_blocks_the_rest(grouped, tmp_path, capsys,
                                                                                            ticking):
    tids = _fac_tids(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value=SAME, by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys)
    assert {d["target"]["id"] for d in _from_cell(rep, FAC_CELL)} == set(tids[1:])
    assert [a["target"]["id"] for a in rep["already_decided_same_value"] if a["cell"] == FAC_CELL] == [tids[0]]
    assert not rep["stale_rulings"] and not rep["clashes"]
    assert {_latest_value(grouped, t) for t in tids} == {SAME}


def test_p2_a_ruling_value_recorded_on_one_target_since_the_adopt_never_blocks_the_rest(grouped, tmp_path, capsys,
                                                                                        ticking):
    ruled, tids = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL11", by=OTHER, orcid=None)
    for extra in ((), ("--supersede",)):
        rep = _imp(grouped, ruled, capsys, *extra)
        assert not rep["stale_rulings"] and not rep["clashes"], extra
        assert {_latest_value(grouped, t) for t in tids} == {"BL11"}, extra


# --- LOW-1, LOW-2 ---------------------------------------------------------------------------------------------


def test_p3b_a_same_value_target_and_a_clash_say_one_thing_each(grouped, tmp_path, capsys, ticking):
    """run-001 held BL12 and run-002 BL13 at adopt; BL11 is ruled; a colleague then records BL11 on run-002. Without
    --supersede: run-001 clashes, run-002 is listed once (it holds the value), the other seven are held back with
    run-001; with --supersede all nine hold BL11."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL11", by=OTHER, orcid=None)
    rep = _imp(grouped, ruled, capsys)
    assert not _to(rep, tids)
    clashes = {c["target"]["id"]: c for c in rep["clashes"]}
    stale = {x["target"]["id"]: x for x in rep["stale_rulings"]}
    assert set(stale) == {tids[1]} and set(clashes) == set(tids) - {tids[1]}  # never both
    assert "blocked_by" not in clashes[tids[0]]
    assert clashes[tids[0]]["reason"].startswith("an earlier scientist decision gives a different value; skipped (pass "
                                                 "--supersede to record this one)")
    for tid in tids[2:]:
        assert clashes[tid]["blocked_by"] == tids[0]
        assert clashes[tid]["reason"].startswith(
            f"this ruling reaches 9 targets and is recorded for all of them or none, and {tids[0]} (run-001) holds a "
            "different value, from an earlier scientist decision (its own line says why); nothing is recorded for this "
            "one either. Pass --supersede to record it for all of them")
    assert stale[tids[1]]["reason"].endswith("the value is already 'BL11'; adopt again to settle this row")
    assert ("1 clash(es) (7 more target(s) of the same cell(s) held back with them: all or nothing)"
            in _text(grouped, ruled, capsys))
    rep = _imp(grouped, ruled, capsys, "--supersede")  # what the lines said: --supersede records it for all
    assert {d["target"]["id"] for d in _to(rep, tids)} == set(tids) - {tids[1]}
    assert [x["target"]["id"] for x in rep["stale_rulings"]] == [tids[1]] and not rep["clashes"]
    assert {_latest_value(grouped, t) for t in tids} == {"BL11"}


def test_p4_supersede_is_never_offered_when_a_clash_it_would_not_record_is_there(grouped, tmp_path, capsys, ticking):
    """run-001 held BL12 at adopt (--supersede would record over it); run-002 got BL13 since (it would not)."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)
    rep = _imp(grouped, ruled, capsys)
    held = [c for c in rep["clashes"] if c.get("blocked_by")]
    assert {c["target"]["id"] for c in held} == set(tids[2:])
    for c in held:
        assert c["blocked_by"] == tids[1] and "Pass --supersede" not in c["reason"]
        assert c["reason"].startswith(
            f"this ruling reaches 9 targets and is recorded for all of them or none, and {tids[1]} (run-002) holds a "
            "different value this ruling was not made against (its own line says why); nothing is recorded for this "
            "one either. Adopt again and rule against what is recorded now, or record this value directly: ")
    rep = _imp(grouped, ruled, capsys, "--supersede")  # and indeed: --supersede records none of them
    assert not _to(rep, tids) and {x["target"]["id"] for x in rep["stale_rulings"]} == set(tids)


# --- LOW-3 ----------------------------------------------------------------------------------------------------


def test_an_adopted_cell_is_this_cell_and_adopting_again_then_supersede_records_it(grouped, tmp_path, capsys, ticking):
    tids = _fac_tids(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="ZZ Since Source", by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys)
    own = next(c for c in rep["clashes"] if c["target"]["id"] == tids[0])
    assert own["reason"].startswith(
        "an earlier scientist decision gives a different value; skipped, and --supersede does not record it either: "
        "this cell was not made against the value recorded now. Adopt again, then import with --supersede, or record "
        "this value directly: ")
    assert all("ruling" not in c["reason"] for c in rep["clashes"] if c["cell"] == FAC_CELL)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys, "--supersede")
    stale = {x["target"]["id"]: x for x in rep["stale_rulings"]}
    assert stale[tids[0]]["reason"].startswith(
        "this cell was adopted with nothing recorded here, before ")
    assert all("ruling" not in x["reason"] and "Adopt again, then import with --supersede" in x["reason"]
               for x in stale.values())
    # the advice: adopt again (the cell reads the value recorded now), then import with --supersede
    _adopt_json(grouped, s, tmp_path / "A2.xlsx", capsys)
    rep = _imp(grouped, tmp_path / "A2.xlsx", capsys, "--supersede")
    assert {d["target"]["id"] for d in _from_cell(rep, FAC_CELL)} == set(tids)
    assert {_latest_value(grouped, t) for t in tids} == {SAME}
