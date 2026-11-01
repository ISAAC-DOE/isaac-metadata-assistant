"""c15a: three wording fixes in the adopt import. Synthetic only (SYN_/ZZ).

* LOW-1: a "seen" clash (one --supersede would record) never says "pass --supersede to record this one" when another
  target of its cell is unseen or split, so --supersede records none of them; the line says what stops it.
* LOW-2: the section and the summary of cells not recorded say "Cells"/"cell(s) not tied to your sheet": adopted cells
  are among them, not only rulings.
* LOW-3: an adopted cell whose target already holds its value is not told to "adopt again to settle this row"; a target
  that already holds the value is not counted as held back.
"""

from __future__ import annotations

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    WHO, _adopt_json, _d, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14l_adopt import OTHER, _imp, _sheets
from test_local_import_polish_c14o_adopt import FAC_CELL, _beamline_ruling, _fac_tids, _from_cell, _latest_value
from test_local_import_polish_c14p_adopt import SAME, _beamline_tids, _text, _to


def _summary(bdir, x, capsys, *extra):
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(bdir), str(x), "--by", WHO, *extra]) == 0
    out = capsys.readouterr().out
    return out, next(ln for ln in out.splitlines() if ln.startswith("Summary"))


OLD_LINE = "skipped (pass --supersede to record this one)"


# --- LOW-1 ----------------------------------------------------------------------------------------------------


def test_a_seen_clash_does_not_offer_supersede_when_another_target_is_unseen(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: run-001 held BL12 before the adopt (seen), run-002 got BL13 after it (unseen)."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)
    rep = _imp(grouped, ruled, capsys)
    own = next(c for c in rep["clashes"] if c["target"]["id"] == tids[0])
    assert OLD_LINE not in own["reason"] and "Pass --supersede" not in own["reason"]
    # c15b M3: what is recorded now, by whom and from where; M2: the cell's one command, never this target's own
    assert own["reason"] == (
        f"an earlier scientist decision gives a different value (recorded now: 'BL12' by {OTHER} (2099-01-01), from a "
        "decide); skipped, and --supersede records none of this ruling's "
        f"targets, because {tids[1]} (run-002) holds a different value this ruling was not made against. Adopt again and "
        "rule against what is recorded now, or record this value for all 9 targets of this cell with one command "
        "(clashes_by_cell: command)")
    assert "blocked_by" not in own  # still its own clash, not a held-back target
    assert all(OLD_LINE not in c["reason"] and "Pass --supersede" not in c["reason"] for c in rep["clashes"])
    # and the line is true: --supersede records 0 of 9
    rep = _imp(grouped, ruled, capsys, "--supersede")
    assert not _to(rep, tids) and {x["target"]["id"] for x in rep["stale_rulings"]} == set(tids)
    assert [_latest_value(grouped, t) for t in tids[:2]] == ["BL12", "BL13"]


def test_the_seen_line_of_an_adopted_cell_says_this_cell(grouped, tmp_path, capsys, ticking):
    tids = _fac_tids(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    # a decision made after the adopt (unseen) on one target; a seen one needs a decision before it
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="ZZ Since Source", by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys)
    unseen = next(c for c in rep["clashes"] if c["target"]["id"] == tids[1])
    assert "was not made against the value recorded now" in unseen["reason"]
    assert all("ruling" not in c["reason"] for c in rep["clashes"] if c["cell"] == FAC_CELL)


def test_a_seen_clash_keeps_its_line_when_every_clash_of_the_cell_is_seen(grouped, tmp_path, capsys, ticking):
    """Unchanged: run-001 held BL12 and run-002 BL13 before the adopt (the row named neither: seven runs held nothing):
    --supersede records it for all nine."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    rep = _imp(grouped, ruled, capsys)
    own = {c["target"]["id"]: c for c in rep["clashes"]}
    assert own[tids[0]]["reason"].startswith("an earlier scientist decision gives a different value (recorded now: "
                                             f"'BL12' by {OTHER} (2099-01-01), from a decide); " + OLD_LINE)
    assert own[tids[1]]["reason"].startswith("an earlier scientist decision gives a different value (recorded now: "
                                             f"'BL13' by {OTHER} (2099-01-01), from a decide); " + OLD_LINE)
    rep = _imp(grouped, ruled, capsys, "--supersede")
    assert {d["target"]["id"] for d in _to(rep, tids)} == set(tids)


# --- LOW-2 ----------------------------------------------------------------------------------------------------


def test_the_section_and_summary_say_cells_not_rulings(grouped, tmp_path, capsys, ticking):
    tids = _fac_tids(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="ZZ Since Source", by=OTHER, orcid=None)
    out, summary = _summary(grouped, tmp_path / "A.xlsx", capsys, "--supersede")
    assert any(ln.startswith("Cells not tied to your sheet (nothing is recorded for them") for ln in out.splitlines())
    assert "Rulings not tied" not in out and "ruling cell(s)" not in out
    assert "; 1 cell(s) not tied to your sheet (nothing recorded)" in summary


def test_a_stale_ruling_is_counted_as_a_cell(grouped, tmp_path, capsys, ticking):
    tids = _beamline_tids(grouped, tmp_path, capsys)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)
    out, summary = _summary(grouped, ruled, capsys, "--supersede")
    assert "Cells not tied to your sheet" in out and "ruling cell(s)" not in summary
    assert "1 cell(s) not tied to your sheet (nothing recorded)" in summary


# --- LOW-3 ----------------------------------------------------------------------------------------------------


def test_an_adopted_cell_whose_target_holds_the_value_is_not_told_to_adopt_again_to_settle_a_row(
        grouped, tmp_path, capsys, ticking):
    """run-001's target holds the cell's value (recorded since the adopt); another target holds something else since
    (unseen): nothing is recorded, and the line of the target that already holds the value gives no ruling's advice."""
    tids = _fac_tids(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value=SAME, by=OTHER, orcid=None)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="ZZ Since Source", by=OTHER, orcid=None)
    for extra in ((), ("--supersede",)):
        rep = _imp(grouped, tmp_path / "A.xlsx", capsys, *extra)
        lines = {x["target"]["id"]: x for x in rep["clashes"] + rep["stale_rulings"] if x["cell"] == FAC_CELL}
        mine = lines[tids[0]]
        assert mine["reason"].endswith(f"nothing is recorded for this one either, and the value is already {SAME!r}"), extra
        assert "settle this row" not in mine["reason"] and "ruling" not in mine["reason"], extra
        assert mine["blocked_by"] == tids[1]
        assert not _from_cell(rep, FAC_CELL)
    assert _latest_value(grouped, tids[0]) == SAME


def test_a_ruling_that_keeps_the_value_still_says_adopt_again_to_settle_this_row(grouped, tmp_path, capsys, ticking):
    """Unchanged for a Disagreements ruling (it has a row)."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL11", by=OTHER, orcid=None)
    rep = _imp(grouped, ruled, capsys)
    st = next(x for x in rep["stale_rulings"] if x["target"]["id"] == tids[1])
    assert st["reason"].endswith("the value is already 'BL11'; adopt again to settle this row")


def test_a_target_already_holding_the_value_is_not_counted_as_held_back(grouped, tmp_path, capsys, ticking):
    """run-001 held BL12 and run-002 BL11 before the adopt; the ruling says BL11: run-001 clashes, run-002 already
    holds it (tied), the other seven are held back with run-001: 1 clash, 7 held back (not 8)."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL11", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    rep = _imp(grouped, ruled, capsys)
    by_id = {c["target"]["id"]: c for c in rep["clashes"]}
    assert set(by_id) == set(tids), sorted(by_id)
    # c15b M4: run-001 still holds BL12, so adopting again would not settle the row
    assert by_id[tids[1]].get("holds_value") and by_id[tids[1]]["reason"].endswith(
        "nothing is recorded for this one either, and the value is already 'BL11'; another target of this row still "
        "holds a different value, so adopting again would ask it again: adopt again and rule the row, or record the "
        "value for all of them with the cell's one command")
    assert not any(by_id[t].get("holds_value") for t in set(tids) - {tids[1]})
    _out, summary = _summary(grouped, ruled, capsys)
    # c15b M1: counted by cell, the targets in brackets
    assert ("1 cell(s) clash (9 target(s): 1 clash; 7 held back with them: all or nothing; "
            "1 already hold the value)") in summary
