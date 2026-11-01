"""c15b: findings of a real-data walk of the "adopt your own sheet" path. Synthetic only (SYN_/ZZ).

* H2: a ruling on a row that named the value recorded now ("recorded `12`; your sheet says `2`: rule which") is
  recorded without --supersede when it was made against that value; nothing else changes (no flip-flop).
* M1: clashes print one line per cell with one command for all its targets; the summary counts them by cell.
* M2: that command names every target (``decide`` takes ``--target`` once per target) and records the whole row; a
  per-target reason of a cell reaching several targets names it instead of its own; ``decide`` warns when it changes
  only some targets of one ruling; a re-adopted row says how many runs hold each value.
* M3: every clash reason says what is recorded now, by whom, when and from where.
* M4: a target already holding the value is not told adopting again settles the row while another holds a different
  value.
* M5: the adopt summary says Campaign Info still reaches the runs on none of their rows.
* M7: a ruling note an older build wrote (cells, no value, no adopt id) settles its row at adopt, never ties.
* L1-L4: the adopt's next command names --by; "Nothing new recorded"; no decision id in prose, "1 awaits"; one sheet
  adopted under two names keeps one vocabulary request, and propose-terms counts an older duplicate once.
"""

from __future__ import annotations

import json
import re
import shlex

import openpyxl

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    WHO, _adopt, _adopt_json, _d, _import, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14g_adopt import ENV, WORD, _rule, _term_draft
from test_local_import_polish_c14j_adopt import _decisions_on
from test_local_import_polish_c14l_adopt import OTHER, _flip_flop_setup, _imp, _sheets, _state, _tid, _value_now
from test_local_import_polish_c14n_adopt import COLLEAGUE, _copies, _imp_by
from test_local_import_polish_c14o_adopt import _beamline_ruling, _latest_value
from test_local_import_polish_c14p_adopt import _beamline_tids, _to

DATE = "2099-01-01"


def _text(bdir, x, capsys, *extra):
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(bdir), str(x), "--by", WHO, *extra]) == 0
    return capsys.readouterr().out


def _summary(out):
    return next(ln for ln in out.splitlines() if ln.startswith("Summary"))


def _ph_row(grouped, tmp_path, capsys, name="A.xlsx"):
    """12 confirmed for run-007; their sheet (pH 2) adopted: its row reads "recorded `12` …: rule which"."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    ph, state = _state(grouped, s, tmp_path / name, capsys)
    assert state == "awaiting" and ph["recorded_note"].endswith("your sheet says `2`: rule which"), ph
    return tid, ph


def _decide_cli(argv, bdir, capsys):
    capsys.readouterr()
    code = cli.main([str(bdir) if a == "<bundle_dir>" else WHO if a == "<your name>" else a for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def _all_beamline_held(grouped, tids):
    """Eight runs hold BL12, run-002 BL13, before the adopt: the whole-beamtime row names both."""
    M.decide(grouped, target_ids=[t for t in tids if t != tids[1]], decision="correct", value="BL12", by=OTHER, orcid=None)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL13", by=OTHER, orcid=None)


# --- H2 -------------------------------------------------------------------------------------------------------


def test_a_ruling_the_row_asked_for_is_recorded_without_supersede(grouped, tmp_path, capsys, ticking):
    tid, ph = _ph_row(grouped, tmp_path, capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {ph["id"]: 3})
    out = _text(grouped, tmp_path / "Ar.xlsx", capsys)  # the preview names it, records nothing
    assert "Rulings to be recorded over the value recorded now" in out and _value_now(grouped, tid) == 12
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert not rep["clashes"] and _to(rep, [tid]) and _value_now(grouped, tid) == 3
    [over] = rep["rulings_over_the_value_recorded"]
    assert over["recorded_now"] == 12 and over["target"]["id"] == tid
    assert over["said"] == f"recorded now: 12 by {OTHER} ({DATE}), from a decide"
    # and once recorded, the same workbook records nothing more
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert rep["recorded"] == 0 and not rep["clashes"] and len(_decisions_on(grouped, tid)) == 2
    assert not rep["rulings_over_the_value_recorded"]


def test_a_split_row_ruled_is_recorded_for_every_run_without_supersede(grouped, tmp_path, capsys, ticking):
    tids = _beamline_tids(grouped, tmp_path, capsys)
    _all_beamline_held(grouped, tids)
    [s] = _sheets(grouped, tmp_path, 1)
    bl = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Beamline/Instrument")
    # M2: the row says how many runs hold each value
    assert bl["recorded_note"] == f"recorded `BL12` (8 runs), `BL13` (1 run) ({DATE}); your sheet says `62b`: rule which"
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {bl["id"]: "BL11"})
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert {d["target"]["id"] for d in _to(rep, tids)} == set(tids) and not rep["clashes"]
    assert {_latest_value(grouped, t) for t in tids} == {"BL11"}


def test_two_adoptions_ruled_differently_never_flip_without_supersede(grouped, tmp_path, capsys, ticking):
    """A and B both adopted against the 12; A rules 2, B rules 12: A records, B never flips it back."""
    tid, _sheets_ = _flip_flop_setup(grouped, tmp_path, capsys)
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert _to(rep, [tid]) and _value_now(grouped, tid) == 2
    for extra in ((), ("--supersede",), ()):
        rep = _imp(grouped, tmp_path / "Br.xlsx", capsys, *extra)
        assert not _to(rep, [tid]) and _value_now(grouped, tid) == 2, extra
        rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, *extra)
        assert not _to(rep, [tid]) and _value_now(grouped, tid) == 2, extra
    assert len(_decisions_on(grouped, tid)) == 2


def test_a_copy_imported_by_a_colleague_never_flips_without_supersede(grouped, tmp_path, capsys, ticking):
    tid = _copies(grouped, tmp_path, capsys)
    rep = _imp_by(grouped, tmp_path / "Wa.xlsx", capsys, WHO)  # the row named the 12: no --supersede needed
    assert _to(rep, [tid]) and _value_now(grouped, tid) == 2
    rep = _imp_by(grouped, tmp_path / "Wb.xlsx", capsys, COLLEAGUE)
    assert not _to(rep, [tid]) and _value_now(grouped, tid) == 2
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    assert f"(recorded now: 2 by {WHO} ({DATE}), from another copy of this workbook)" in clash["reason"]
    assert "--supersede does not record it either" in clash["reason"]


def test_a_decision_since_the_adopt_still_needs_a_fresh_adopt(grouped, tmp_path, capsys, ticking):
    tid, ph = _ph_row(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=[tid], decision="correct", value=5, by=OTHER, orcid=None)  # since the adopt
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {ph["id"]: 3})
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert not _to(rep, [tid]) and _value_now(grouped, tid) == 5
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    assert clash["reason"].startswith(f"an earlier scientist decision gives a different value (recorded now: 5 by {OTHER} "
                                      f"({DATE}), from a decide); skipped, and --supersede does not record it either")


def test_a_workbook_without_the_recorded_shown_column_still_needs_supersede(grouped, tmp_path, capsys, ticking):
    tid, ph = _ph_row(grouped, tmp_path, capsys)
    wb = openpyxl.load_workbook(tmp_path / "A.xlsx")
    for row in wb["_isaac"].iter_rows():
        for c in row:
            if c.value == T.RECORDED_SHOWN:
                for r in range(c.row, wb["_isaac"].max_row + 1):
                    wb["_isaac"].cell(r, c.column).value = None
    wb.save(tmp_path / "old.xlsx")
    _rule(tmp_path / "old.xlsx", tmp_path / "oldr.xlsx", {ph["id"]: 3})
    rep = _imp(grouped, tmp_path / "oldr.xlsx", capsys)
    assert not _to(rep, [tid]) and [c["target"]["id"] for c in rep["clashes"]] == [tid]
    assert "skipped (pass --supersede to record this one)" in rep["clashes"][0]["reason"]
    rep = _imp(grouped, tmp_path / "oldr.xlsx", capsys, "--supersede")
    assert _to(rep, [tid]) and _value_now(grouped, tid) == 3


# --- M1, M2 ---------------------------------------------------------------------------------------------------


def _held_back(grouped, tmp_path, capsys):
    """run-001 held BL12 before the adopt (the row could not name it: other runs held nothing); BL11 ruled: 9 clash."""
    tids = _beamline_tids(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    return tids, ruled


def test_clashes_are_one_line_per_cell_with_one_command(grouped, tmp_path, capsys, ticking):
    tids, ruled = _held_back(grouped, tmp_path, capsys)
    out = _text(grouped, ruled, capsys)
    section = out.split("Clashes (skipped; one line per cell, --json lists every target):\n", 1)[1].split("\n\n", 1)[0]
    [line] = section.splitlines()
    assert line.startswith("  'Disagreements'!H2 Beamline/Instrument = 'BL11': 9 target(s) on 9 run(s) (1 clash, 8 held "
                           "back with them): an earlier scientist decision gives a different value (recorded now: 'BL12' "
                           f"by {OTHER} ({DATE}), from a decide); skipped (pass --supersede to record this one). One command "
                           "records it for all 9 of them: isaac bundle decide <bundle_dir> ")
    assert line.count("--target ") == 9 and line.count("isaac bundle decide") == 1
    assert "1 cell(s) clash (9 target(s): 1 clash; 8 held back with them: all or nothing)" in _summary(out)
    # --json keeps every target, and each target's reason names the cell's command, never its own
    rep = _imp(grouped, ruled, capsys)
    assert {c["target"]["id"] for c in rep["clashes"]} == set(tids)
    assert all(c["reason"].endswith(", or record this value for all 9 targets of this cell with one command "
                                    "(clashes_by_cell: command)") for c in rep["clashes"])
    [cell] = rep["clashes_by_cell"]
    assert cell["targets"] == 9 and cell["clashes"] == 1 and cell["held_back"] == 8 and set(cell["target_ids"]) == set(tids)


def test_the_cell_command_records_the_whole_row(grouped, tmp_path, capsys, ticking):
    tids, ruled = _held_back(grouped, tmp_path, capsys)
    [cell] = _imp(grouped, ruled, capsys)["clashes_by_cell"]
    code, _out, err = _decide_cli(shlex.split(cell["command"])[1:], grouped, capsys)
    assert code == 0, err
    assert {_latest_value(grouped, t) for t in tids} == {"BL11"}


def test_decide_warns_when_it_changes_only_some_targets_of_one_ruling(grouped, tmp_path, capsys, ticking):
    tids = _beamline_tids(grouped, tmp_path, capsys)
    ruled, _ = _beamline_ruling(grouped, tmp_path, capsys, "BL11")
    assert len(_to(_imp(grouped, ruled, capsys), tids)) == 9
    code, out, err = _decide_cli(["bundle", "decide", "<bundle_dir>", "--target", tids[0], "--decision", "correct",
                                  "--value=BL12", "--by", WHO], grouped, capsys)
    assert code == 0, err
    rep = json.loads(out)
    [left] = rep["same_ruling_left"]
    assert set(left["target_ids"]) == set(tids[1:]) and left["value"] == "BL11"
    assert "Warning: 8 other target(s) of the same ruling on disagreement D" in rep["statement"]
    # naming every target of the ruling says nothing
    code, out, err = _decide_cli(["bundle", "decide", "<bundle_dir>", *[a for t in tids for a in ("--target", t)],
                                  "--decision", "correct", "--value=BL13", "--by", WHO], grouped, capsys)
    assert code == 0, err
    assert "same_ruling_left" not in json.loads(out)


# --- M3 -------------------------------------------------------------------------------------------------------


def test_a_clash_says_another_adoption_recorded_the_value(grouped, tmp_path, capsys, ticking):
    """A colleague's ruling from another adoption of the sheet is recorded since B was adopted."""
    _flip_flop_setup(grouped, tmp_path, capsys)
    _imp_by(grouped, tmp_path / "Ar.xlsx", capsys, COLLEAGUE)
    rep = _imp(grouped, tmp_path / "Br.xlsx", capsys)
    [clash] = rep["clashes"]
    assert f"(recorded now: 2 by {COLLEAGUE} ({DATE}), from another adoption)" in clash["reason"]
    assert clash["existing"]["source"] == "another adoption" and clash["existing"]["decision_id"].startswith("d-")


# --- M4 -------------------------------------------------------------------------------------------------------


def test_a_target_holding_the_value_is_not_told_adopting_again_settles_a_split_row(grouped, tmp_path, capsys, ticking):
    """run-001 held BL12 (the ruling saw it, but the row could not name it); run-002 got BL11 since: run-002 already
    holds the value, run-001 still holds another, so adopting again would still ask the row."""
    tids, ruled = _held_back(grouped, tmp_path, capsys)
    M.decide(grouped, target_ids=tids[1:2], decision="correct", value="BL11", by=OTHER, orcid=None)
    rep = _imp(grouped, ruled, capsys)
    [held] = [x for x in rep["clashes"] + rep["stale_rulings"] if x["target"]["id"] == tids[1]]
    assert "adopt again to settle this row" not in held["reason"]
    assert held["reason"].endswith("the value is already 'BL11'; another target of this row still holds a different "
                                    "value, so adopting again would ask it again: adopt again and rule the row, or "
                                    "record the value for all of them with the cell's one command")
    [cell] = rep["clashes_by_cell"]
    assert tids[1] not in cell["target_ids"] and len(cell["target_ids"]) == 8


# --- M5, L1, L3 -----------------------------------------------------------------------------------------------


def test_the_adopt_summary_says_campaign_info_reaches_runs_on_none_of_their_rows(grouped, tmp_path, capsys, ticking):
    [s] = _sheets(grouped, tmp_path, 1)
    code, text, err = _adopt(grouped, s, tmp_path / "A.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    assert ("1 run(s) are on none of your rows (Campaign Info still applies to them: its answers reach every File List "
            "run).") in text
    assert f"--by '{WHO}' (a preview; add --apply to record)." in text
    assert '--by "<your name>"' not in text.splitlines()[-1]
    code, text, err = _adopt(grouped, s, tmp_path / "B.xlsx", capsys)  # no --by: the placeholder stays
    assert code == 0, err
    assert '--by "<your name>" (a preview' in text


def test_one_row_left_awaits(grouped, tmp_path, capsys, ticking):
    [s] = _sheets(grouped, tmp_path, 1)
    code, text, err = _adopt(grouped, s, tmp_path / "A.xlsx", capsys, "--json")
    assert code == 0, err
    result = json.loads(text)
    ds = result["adopted"]["disagreements"]
    assert len(ds) > 2
    for d in ds[1:]:  # every row but one settled, as a later adopt says it
        d["already_recorded"] = {"statement": "already recorded: 'x'; leave blank to keep"}
    out = T.render_adopt_summary(result)
    assert f"Disagreements already recorded: {len(ds) - 1} of {len(ds)}" in out
    assert "; 1 awaits your ruling." in out and " 1 await your" not in out


def test_no_decision_id_in_the_text_report(grouped, tmp_path, capsys, ticking):
    _flip_flop_setup(grouped, tmp_path, capsys)
    _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    for extra in ((), ("--supersede",)):
        out = _text(grouped, tmp_path / "Br.xlsx", capsys, *extra)
        assert not re.search(r"\bd-\d{5}\b", out), out
    rep = _imp(grouped, tmp_path / "Br.xlsx", capsys, "--supersede")
    [stale] = rep["stale_rulings"]
    assert not re.search(r"\bd-\d{5}\b", stale["reason"]) and stale["decision_id"].startswith("d-")


# --- M7 -------------------------------------------------------------------------------------------------------


def test_a_ruling_an_older_build_recorded_settles_its_row(grouped, tmp_path, capsys, ticking):
    tid, ph = _ph_row(grouped, tmp_path, capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {ph["id"]: 3})
    _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    # the note as a build before c14h wrote it: their cells, no value, no adopt id
    bundle = json.loads((grouped / "bundle.json").read_text(encoding="utf-8"))
    d = [x for x in bundle["scientist_decisions"] if x["target"]["id"] == tid][-1]
    old = d["note"].split(" = ", 1)[0] + ")"
    assert "ruling on disagreement" in old and "adopt id" not in old
    d["note"] = old
    (grouped / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    [s] = _sheets(grouped, tmp_path, 1)
    again = _d(_adopt_json(grouped, s, tmp_path / "B.xlsx", capsys), "pH", run_id="run-007")
    assert again["already_recorded"]["statement"].startswith(
        f"already recorded: 3 ({DATE}), by your ruling on this row from an earlier build (it kept no copy of your cell's "
        "value then: if you changed that cell since, rule it again); leave blank to keep")
    # never read for tying: the strict reading still says no
    assert not T._ruled_here([d], 0, ("SYN_their.xlsx", "'File List'!H8", 2))


# --- L2, L4 ---------------------------------------------------------------------------------------------------


def test_an_apply_that_records_nothing_says_so(grouped, tmp_path, capsys, ticking):
    _, ph = _ph_row(grouped, tmp_path, capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {ph["id"]: 3})
    assert "Recorded as scientist decisions" in _text(grouped, tmp_path / "Ar.xlsx", capsys, "--apply")
    out = _text(grouped, tmp_path / "Ar.xlsx", capsys, "--apply")
    assert "Nothing new recorded: no scientist decision." in out and "Recorded as scientist decisions" not in out


def test_one_sheet_adopted_under_two_names_keeps_one_request(grouped, tmp_path, capsys, ticking):
    [s] = _sheets(grouped, tmp_path, 1)
    code, _t, err = _adopt(grouped, s, tmp_path / "A.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    before = [r for r in M.load(grouped)["vocabulary_requests"] if r["field_path"] == ENV and r["term"] == WORD]
    assert len(before) == 1
    code, text, err = _adopt(grouped, s, tmp_path / "B.xlsx", capsys, "--by", OTHER)
    assert code == 0, err
    after = [r for r in M.load(grouped)["vocabulary_requests"] if r["field_path"] == ENV and r["term"] == WORD]
    assert [r["request_id"] for r in after] == [before[0]["request_id"]]
    assert f"by {WHO}; the same cells, so not kept again (a request keeps one name)" in text


def test_propose_terms_counts_an_older_duplicate_once(grouped, tmp_path, capsys, ticking):
    [s] = _sheets(grouped, tmp_path, 1)
    assert _adopt(grouped, s, tmp_path / "A.xlsx", capsys, "--by", WHO)[0] == 0
    one = _term_draft(grouped, capsys)["count"]
    # a build before c15b kept the same cells again under another name
    bundle = json.loads((grouped / "bundle.json").read_text(encoding="utf-8"))
    req = next(r for r in bundle["vocabulary_requests"] if r["field_path"] == ENV and r["term"] == WORD)
    bundle["vocabulary_requests"].append({**req, "request_id": "vr-09999",
                                          "requested_by": {**req["requested_by"], "name": OTHER}})
    (grouped / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    assert _term_draft(grouped, capsys)["count"] == one
