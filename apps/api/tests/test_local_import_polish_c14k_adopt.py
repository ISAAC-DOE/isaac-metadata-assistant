"""c14k: a ruling settles its row anywhere in the run of the same value. Synthetic only (SYN_/ZZ names).

* MED-1: a re-adopted row is settled when a ruling on that sheet cell is ANY decision of the unbroken same-value run
  ending at the decision that governs (:class:`template._Chains`; a different value, a reject or a defer ends it),
  and a ruling made against any decision of that run is tied. Two sheets of theirs ruled the same value both stay
  settled after one tie each; a second scientist's ``decide`` confirm between adopt and import costs no extra ruling
  round; a real value change in between asks the row again. A workbook adopted with nothing recorded for the target
  ties when every decision since is of the run (both sheets adopted first, then imported in turn: no extra round). A
  ruling on a workbook adopted before the run began is listed apart (``stale_rulings``), never "already recorded".
* LOW-1: a deeply nested hidden-sheet value is damaged, never a RecursionError.
* LOW-2: with the ``governing_decisions`` column there, a damaged value never ties (``GOVERNING_DAMAGED``), never
  by time, and is never read as ``[]`` (adopted with nothing recorded, which ties when nothing else came between).
* LOW-5: the summary says the decisions recorded and the tied ruling cells as two counts.
"""

from __future__ import annotations

import shutil

import openpyxl
import pytest

from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    PH, THEIRS, WHO, _adopt_json, _cand, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14g_adopt import _rule
from test_local_import_polish_c14j_adopt import _decisions_on, _edited_and_ruled_again, _governing

OTHER = "Other Synthetic Scientist"


def _state(grouped, theirs, out, capsys):
    """Adopt ``theirs`` again: (its run-007 pH row, ``settled`` or ``awaiting``)."""
    ph = _d(_adopt_json(grouped, theirs, out, capsys), "pH", run_id="run-007")
    return ph, "settled" if ph["already_recorded"] else "awaiting"


def _imp(grouped, x, capsys, *extra):
    code, rep, err = _import(grouped, x, capsys, "--apply", *extra)
    assert code == 0, err
    return rep


def _two_sheets(grouped, tmp_path):
    """Two of their own sheets (different file names), both saying pH 2 for run-007; the file says 12."""
    s1 = _their_sheet(grouped, tmp_path / THEIRS)
    s2 = tmp_path / "SYN_second_sheet.xlsx"
    shutil.copy(s1, s2)
    return s1, s2


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_two_sheets_ping_pong(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: both adopted before anything is recorded; 12 ruled in both; imported in turn, then each
    sheet adopted again (and ruled when asked) three times over."""
    s1, s2 = _two_sheets(grouped, tmp_path)
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    pa, _ = _state(grouped, s1, tmp_path / "A.xlsx", capsys)
    pb, _ = _state(grouped, s2, tmp_path / "B.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {pa["id"]: 12})
    _rule(tmp_path / "B.xlsx", tmp_path / "Br.xlsx", {pb["id"]: 12})
    ties = 0
    for name in ("Ar", "Br", "Ar", "Br"):
        rep = _imp(grouped, tmp_path / f"{name}.xlsx", capsys)
        ties += len(rep["rulings_tied_to_sheet"])
        assert not rep["stale_rulings"]
    # A's ruling recorded; B's (adopted with nothing recorded either) tied once; nothing more
    assert ties == 1 and len(_decisions_on(grouped, tid)) == 2
    for cycle in range(3):
        for sheet, tag in ((s1, "A"), (s2, "B")):
            assert _state(grouped, sheet, tmp_path / f"{tag}{cycle}.xlsx", capsys)[1] == "settled", (cycle, tag)
    for x in ("Ar", "Br"):  # every ruled workbook again: nothing more
        rep = _imp(grouped, tmp_path / f"{x}.xlsx", capsys)
        assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"], x
    assert len(_decisions_on(grouped, tid)) == 2


def test_both_sheets_adopted_first_then_imported_in_either_order_settle_both(grouped, tmp_path, capsys, ticking):
    """Adopt A, adopt B, import B, import A: B's ruling is recorded, A's (adopted with nothing recorded) is tied, and
    every later import or adopt records nothing."""
    s1, s2 = _two_sheets(grouped, tmp_path)
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    pa, _ = _state(grouped, s1, tmp_path / "A.xlsx", capsys)
    pb, _ = _state(grouped, s2, tmp_path / "B.xlsx", capsys)
    assert _governing(tmp_path / "A.xlsx", pa["id"]) == [] == _governing(tmp_path / "B.xlsx", pb["id"])
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {pa["id"]: 12})
    _rule(tmp_path / "B.xlsx", tmp_path / "Br.xlsx", {pb["id"]: 12})
    rep = _imp(grouped, tmp_path / "Br.xlsx", capsys)
    assert rep["recorded"] >= 1 and not rep["rulings_tied_to_sheet"]
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    [tied] = [t for t in rep["rulings_tied_to_sheet"] if t["target"]["id"] == tid]
    assert not rep["stale_rulings"] and tied["decision_id"] == _decisions_on(grouped, tid)[0]["decision_id"]
    assert len(_decisions_on(grouped, tid)) == 2
    for cycle in range(2):
        for x in ("Ar", "Br"):
            rep = _imp(grouped, tmp_path / f"{x}.xlsx", capsys)
            assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"] and not rep["stale_rulings"], (cycle, x)
        for sheet, tag in ((s1, "A"), (s2, "B")):
            assert _state(grouped, sheet, tmp_path / f"{tag}{cycle}.xlsx", capsys)[1] == "settled", (cycle, tag)
    assert len(_decisions_on(grouped, tid)) == 2


def test_adopted_with_nothing_recorded_then_a_different_value_never_ties(grouped, tmp_path, capsys, ticking):
    """Adopted with nothing recorded; a different value (7) recorded since: a ruling of 12 clashes; with 12 recorded
    again after the 7, the same ruling is stale ("a different value was recorded since"), never tied."""
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    ph, _ = _state(grouped, theirs, tmp_path / "A.xlsx", capsys)
    assert _governing(tmp_path / "A.xlsx", ph["id"]) == []
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {ph["id"]: 12})
    M.decide(grouped, target_ids=[tid], decision="correct", value=7, by=OTHER, orcid=None)
    changed = _decisions_on(grouped, tid)[-1]["decision_id"]
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert not rep["rulings_tied_to_sheet"] and tid in [c["target"]["id"] for c in rep["clashes"]]
    assert _state(grouped, theirs, tmp_path / "A1.xlsx", capsys)[1] == "awaiting"
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)  # 12 again
    back = _decisions_on(grouped, tid)[-1]["decision_id"]
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    [stale] = rep["stale_rulings"]
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert stale["reason"].startswith(f"ruled on a workbook adopted before {back}, and a different value was recorded "
                                      f"since ({changed}); ")
    assert _state(grouped, theirs, tmp_path / "A2.xlsx", capsys)[1] == "awaiting"
    assert len(_decisions_on(grouped, tid)) == 2


def test_two_sheets_each_tie_once_and_both_stay_settled(grouped, tmp_path, capsys, ticking):
    """The file's 12 confirmed; sheets A and B (both 2) each adopted against it and ruled 12: one tie each, and
    either sheet adopted again is settled; cycling them records nothing more."""
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)
    s1, s2 = _two_sheets(grouped, tmp_path)
    for sheet, tag in ((s1, "A"), (s2, "B")):
        p, st = _state(grouped, sheet, tmp_path / f"{tag}.xlsx", capsys)
        assert st == "awaiting"
        _rule(tmp_path / f"{tag}.xlsx", tmp_path / f"{tag}r.xlsx", {p["id"]: 12})
        assert len(_imp(grouped, tmp_path / f"{tag}r.xlsx", capsys)["rulings_tied_to_sheet"]) == 1
    assert len(_decisions_on(grouped, tid)) == 3
    for cycle in range(2):
        for sheet, tag in ((s1, "A"), (s2, "B")):
            assert _state(grouped, sheet, tmp_path / f"{tag}{cycle}.xlsx", capsys)[1] == "settled", (cycle, tag)
            rep = _imp(grouped, tmp_path / f"{tag}r.xlsx", capsys)
            assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"] and not rep["stale_rulings"]
    assert len(_decisions_on(grouped, tid)) == 3


def test_a_second_scientists_confirm_between_adopt_and_import_costs_no_ruling_round(grouped, tmp_path, capsys, ticking):
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)
    [first] = _decisions_on(grouped, tid)
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    ph, st = _state(grouped, theirs, tmp_path / "A.xlsx", capsys)
    assert st == "awaiting" and _governing(tmp_path / "A.xlsx", ph["id"]) == [first["decision_id"]]
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)  # the same 12
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {ph["id"]: 12})
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    [tied] = rep["rulings_tied_to_sheet"]
    assert tied["target"]["id"] == tid and tied["decision_id"] == _decisions_on(grouped, tid)[1]["decision_id"]
    assert not rep["stale_rulings"]
    assert _state(grouped, theirs, tmp_path / "again.xlsx", capsys)[1] == "settled"  # no second ruling round
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert len(_decisions_on(grouped, tid)) == 3


def test_a_real_value_change_in_between_asks_the_row_again(grouped, tmp_path, capsys, ticking):
    """Both sheets settled; the value is corrected to 7 and confirmed back to 12: each sheet's row awaits again, and a
    workbook ruled before the change is stale, saying what changed."""
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)
    s1, s2 = _two_sheets(grouped, tmp_path)
    for sheet, tag in ((s1, "A"), (s2, "B")):
        p, _ = _state(grouped, sheet, tmp_path / f"{tag}.xlsx", capsys)
        _rule(tmp_path / f"{tag}.xlsx", tmp_path / f"{tag}r.xlsx", {p["id"]: 12})
        _imp(grouped, tmp_path / f"{tag}r.xlsx", capsys)
    assert _state(grouped, s1, tmp_path / "A0.xlsx", capsys)[1] == "settled"
    M.decide(grouped, target_ids=[tid], decision="correct", value=7, by=OTHER, orcid=None)
    changed = _decisions_on(grouped, tid)[-1]["decision_id"]
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)  # 12 again
    back = _decisions_on(grouped, tid)[-1]["decision_id"]
    for sheet, tag in ((s1, "A"), (s2, "B")):
        assert _state(grouped, sheet, tmp_path / f"{tag}1.xlsx", capsys)[1] == "awaiting", tag
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    [stale] = rep["stale_rulings"]
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert stale["reason"].startswith(f"ruled on a workbook adopted before {back}, and a different value was recorded "
                                      f"since ({changed}); ")
    assert stale["reason"].split(", or record this value directly: ")[0].endswith("Adopt again to settle this sheet")


def test_a_reject_or_defer_ends_the_run(grouped, tmp_path, capsys, ticking):
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    ph, _ = _state(grouped, theirs, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {ph["id"]: 12})
    _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert _state(grouped, theirs, tmp_path / "A0.xlsx", capsys)[1] == "settled"
    M.decide(grouped, target_ids=[tid], decision="defer", value=None, by=OTHER, orcid=None)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    assert _state(grouped, theirs, tmp_path / "A1.xlsx", capsys)[1] == "awaiting"


def test_chains_read_a_candidate_and_its_conflicts_in_log_order():
    def d(i, kind, tid, decision, value=None):
        return {"decision_id": f"d-{i:04d}", "target": {"kind": kind, "id": tid}, "decision": decision, "value": value}

    bundle = {"candidates": [{"candidate_id": "cand-1", "value": 12}], "conflicts": [{"conflict_id": "conf-1",
              "candidate_id": "cand-1"}], "missing_values": [{"value_id": "miss-1"}],
              "scientist_decisions": [d(1, "candidate", "cand-1", "correct", 7), d(2, "candidate", "cand-1", "confirm"),
                                      d(3, "missing_value", "miss-1", "correct", 12), d(4, "conflict", "conf-1", "correct", 12),
                                      d(5, "candidate", "cand-1", "confirm"), d(6, "candidate", "cand-1", "defer"),
                                      d(7, "candidate", "cand-1", "confirm")]}
    chains = T._Chains(bundle)
    assert chains(4) == [4, 3, 1] and chains.before(1) == 0  # 12, 12 (via the conflict), 12; then 7
    assert chains(6) == [6] and chains.before(6) == 5  # the defer ends it
    assert chains(2) == [2] and chains.before(2) is None and chains(-1) == []
    assert [x["decision_id"] for x in chains.history(4)] == ["d-0001", "d-0002", "d-0004", "d-0005", "d-0006", "d-0007"]
    log = bundle["scientist_decisions"]
    # adopted with nothing recorded for it: tied only when every decision since is of the run
    assert T._rules_against_now({"ruled_against": []}, log[2], None, [log[2]], chains.history(2))
    assert not T._rules_against_now({"ruled_against": []}, log[4], None, [log[p] for p in chains(4)], chains.history(4))
    assert not T._rules_against_now({"ruled_against": ["d-0001"]}, log[4], None, [log[p] for p in chains(4)],
                                    chains.history(4))  # it saw the 7


# --- LOW-1 ----------------------------------------------------------------------------------------------------


def test_a_deeply_nested_hidden_sheet_value_is_damaged_not_a_crash():
    deep = "[" * 100_000
    assert T._marker_governing({"governing_decisions": deep}) == [T.GOVERNING_DAMAGED]
    assert T._marker_their_value({"their_value": deep}) == (None, False)
    note = f"x (your ruling on disagreement D1: SYN.xlsx 'File List'!H8 = {deep})"
    assert not T._ruled_here([{"note": note}], 0, ("SYN.xlsx", "'File List'!H8", 2))


# --- LOW-2 ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("damaged", [None, '"{id}"', '{{"{id}": true}}', "null"])
def test_a_damaged_governing_decisions_value_never_ties(grouped, tmp_path, capsys, ticking, damaged):
    """The column is there but its value is not a list (even one naming the decision that governs, as a bare string or
    an object): never tied, even when the workbook's time would tie it."""
    theirs, ph, current = _edited_and_ruled_again(grouped, tmp_path, capsys)
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    [first] = _decisions_on(grouped, tid)
    assert _governing(current, ph["id"]) == [first["decision_id"]]
    wb = openpyxl.load_workbook(current)
    wm = wb["_isaac"]
    [(r0, c0)] = [(c.row, c.column) for row in wm.iter_rows() for c in row if c.value == "governing_decisions"]
    [row] = [r for r in range(r0 + 1, wm.max_row + 1) if wm.cell(r, 1).value == ph["id"]]
    wm.cell(row, c0).value = damaged.format(id=first["decision_id"]) if damaged else damaged
    [r1] = [c.row for row in wm.iter_rows() for c in row if c.column == 1 and c.value == "exported_utc"]
    wm.cell(r1, 2).value = first["decided_utc"]  # adopted at the decision: the time check alone would tie it
    wb.save(current)
    assert _governing(current, ph["id"]) == [T.GOVERNING_DAMAGED]  # never read as "[]", adopted with nothing recorded
    rep = _imp(grouped, current, capsys)
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    [stale] = rep["stale_rulings"]
    assert stale["target"]["id"] == tid and "governing_decisions value is damaged" in stale["reason"]
    assert len(_decisions_on(grouped, tid)) == 1


@pytest.mark.parametrize("damaged", ['"d-0001"', '{"d": 1}', "null", "", "not json"])
def test_marker_governing_is_damaged_for_a_damaged_value_with_the_column(damaged):
    assert T._marker_governing({"governing_decisions": damaged}) == [T.GOVERNING_DAMAGED]
    assert T._marker_governing({"governing_decisions": None}) == [T.GOVERNING_DAMAGED]
    assert T._marker_governing({"governing_decisions": "[]"}) == []  # adopted with nothing recorded: not damaged
    assert not T._rules_against_now({"ruled_against": [T.GOVERNING_DAMAGED]}, {"decision_id": "d-1"}, None, (),
                                    [{"decision_id": "d-1"}])
    assert T._marker_governing({"their_value": "2"}) is None  # no column: adopted before it was kept


# --- LOW-5 ----------------------------------------------------------------------------------------------------


def test_the_tied_summary_says_two_counts():
    two = [{"cell": "'Disagreements'!H2"}, {"cell": "'Disagreements'!H3"}, {"cell": "'Disagreements'!H3"}]
    assert T._tied_summary({"rulings_tied_to_sheet": two, "applied": False}) == (
        ", including 2 ruling cells that keep the same value and are to be tied to your sheet (3 targets)")
    assert T._tied_summary({"rulings_tied_to_sheet": two, "applied": True}) == (
        ", including 2 ruling cells that kept the same value and are now tied to your sheet (3 targets)")
    assert T._tied_summary({"rulings_tied_to_sheet": two[:1], "applied": False}) == (
        ", including 1 ruling cell that keeps the same value and is to be tied to your sheet (1 target)")
    assert T._tied_summary({"rulings_tied_to_sheet": [], "applied": True}) == ""
