"""c14m: "made against the current value" is exact, and survives copies and forks. Synthetic only (SYN_/ZZ).

* MED-2: adopt keeps a hash of the decisions the log held (``_isaac`` ``decisions_fingerprint``,
  :func:`template.decisions_fingerprint`). A workbook whose position or ``governing_decisions`` point into another log
  (a copied, restored or forked bundle keeps its ``bundle_id``; decision ids repeat) is unplaceable: nothing of it is
  tied or recorded over another value, and its reason says "this bundle's decisions changed since the workbook was
  adopted (copied or restored?); adopt again". A workbook without the hash is read as before.
* MED-3: adopt keeps a random ``adopt_id``, carried by each ruling's note: a scientist correcting a ruling they made
  on this very workbook supersedes it; two adoptions of the same sheet (two ids) still converge, and the refused one
  names "your earlier ruling on this row (d-N)".
* MED-1: a ruling cell is all or nothing: a whole-beamtime ruling is never recorded for some runs and not others.
* LOW-1: a workbook adopted with nothing recorded never says "made against an earlier value".
* LOW-2: every stale and clash reason ends with the ``isaac bundle decide`` command for its target.
* LOW-3: ``_adopt_position`` (and the other ``isdigit()``-then-``int()`` readers) take ASCII digits only.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil

import openpyxl
import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    PH, THEIRS, WHO, _adopt_json, _cand, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14g_adopt import _rule
from test_local_import_polish_c14j_adopt import _decisions_on, _governing, _import_text
from test_local_import_polish_c14l_adopt import OTHER, _imp, _meta, _sheets, _state, _tid, _value_now, _without_adopt_position

UNPLACEABLE = "this bundle's decisions changed since the workbook was adopted (copied or restored?); adopt again"


def _other_target(bdir, tid):
    """A candidate with a value, not run-007's pH: decisions on it move the log without touching the pH."""
    b = M.load(bdir)
    return next(c["candidate_id"] for c in b["candidates"]
                if c["candidate_id"] != tid and c.get("value") is not None and c.get("target_field_path") != PH)


def _targets(rep):
    """The targets an import recorded (or would record) a decision on."""
    return {d["target"]["id"] for d in rep["decisions"]}


def _command_in(reason):
    """The `decide` command a reason offers, as argv for ``cli.main`` (placeholders left for the caller)."""
    text = reason.split("record this value directly: ", 1)[1].rstrip(")")
    return shlex.split(text)[1:]  # without "isaac"


def _run_command(argv, bdir):
    return cli.main([str(bdir) if a == "<bundle_dir>" else WHO if a == "<your name>" else a for a in argv])


# --- MED-2 ----------------------------------------------------------------------------------------------------


def test_adopt_keeps_a_fingerprint_of_the_log_and_a_fresh_adopt_id(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _state(grouped, s, tmp_path / "B.xlsx", capsys)
    a, b = _meta(tmp_path / "A.xlsx"), _meta(tmp_path / "B.xlsx")
    log = M.load(grouped)["scientist_decisions"]
    assert a["decisions_at_adopt"] == 1 and a["decisions_fingerprint"] == T.decisions_fingerprint(log, 1)
    assert T._adopt_id(a["adopt_id"]) and T._adopt_id(b["adopt_id"]) and a["adopt_id"] != b["adopt_id"]


def test_the_fingerprint_hashes_exactly_the_five_fields_of_the_prefix():
    log = [{"decision_id": "d-00001", "decided_utc": "2099-01-01T00:00:01Z", "target": {"kind": "candidate", "id": "c1"},
            "decision": "confirm", "value": None, "note": "a"},
           {"decision_id": "d-00002", "decided_utc": "2099-01-01T00:00:02Z", "target": {"kind": "candidate", "id": "c2"},
            "decision": "correct", "value": 7, "note": "b"}]
    assert T.decisions_fingerprint([], 0) == T.decisions_fingerprint(log, 0) == hashlib.sha256(b"[]").hexdigest()
    one = T.decisions_fingerprint(log, 1)
    assert one == T.decisions_fingerprint(log[:1], 1) != T.decisions_fingerprint(log, 2)
    assert T.decisions_fingerprint([{**log[0], "note": "other", "batch_id": "x"}], 1) == one  # not among the five
    for key, value in (("decision_id", "d-00009"), ("decided_utc", "2099-01-02T00:00:00Z"), ("decision", "reject"),
                       ("value", 12), ("target", {"kind": "candidate", "id": "c9"})):
        assert T.decisions_fingerprint([{**log[0], key: value}], 1) != one, key


def _forked(grouped, tmp_path, capsys, ruling):
    """Copy A of the bundle (same bundle_id) gets two decisions on another target, then the sheet is adopted there
    (nothing on run-007's pH) and ruled ``ruling``; the original (copy B) moves on with decisions of its own."""
    tid = _tid(grouped)
    copy_a = tmp_path / "copyA"
    shutil.copytree(grouped, copy_a)
    other = _other_target(copy_a, tid)
    for _ in range(2):
        M.decide(copy_a, target_ids=[other], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(copy_a, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: ruling})
    return tid, other


def test_a_position_from_another_copy_never_supersedes(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: 12 confirmed on copy B, then an unrelated decision; A's position (2) points past the 12
    in B's log, so it read as "nothing recorded since": a false supersede."""
    tid, other = _forked(grouped, tmp_path, capsys, 2)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    M.decide(grouped, target_ids=[other], decision="confirm", value=None, by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert tid not in _targets(rep) and not rep["rulings_tied_to_sheet"]
    [stale] = [x for x in rep["stale_rulings"] if x["target"]["id"] == tid]
    assert stale["reason"].startswith(UNPLACEABLE + " and rule against what is recorded now; nothing is recorded for "
                                      "this ruling, even with --supersede,")
    assert stale["reason"].endswith(f"--target {tid} --decision correct --value=2 --json --by \"<your name>\"")
    assert _value_now(grouped, tid) == 12 and len(_decisions_on(grouped, tid)) == 1
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)  # without --supersede: a clash that says so
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    # c15b M3: what is recorded now, by whom and from where
    assert clash["reason"].startswith(f"an earlier scientist decision gives a different value (recorded now: 12 by {OTHER} "
                                      "(2099-01-01), from a decide); skipped, and --supersede does not record it either: "
                                      + UNPLACEABLE)


def test_a_position_from_another_copy_never_ties(grouped, tmp_path, capsys, ticking):
    """The restore probe: on B a 7 is recorded, then 12 again after A's position; A (ruled 12) never saw the 7."""
    tid, other = _forked(grouped, tmp_path, capsys, 12)
    M.decide(grouped, target_ids=[tid], decision="correct", value=7, by=OTHER, orcid=None)
    for _ in range(2):
        M.decide(grouped, target_ids=[other], decision="confirm", value=None, by=OTHER, orcid=None)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert not rep["rulings_tied_to_sheet"] and tid not in _targets(rep)
    [stale] = [x for x in rep["stale_rulings"] if x["target"]["id"] == tid]
    assert stale["reason"].startswith(UNPLACEABLE) and "even with --supersede" not in stale["reason"]
    assert len(_decisions_on(grouped, tid)) == 2


def test_a_restored_bundle_with_fewer_decisions_is_unplaceable(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    backup = tmp_path / "backup"
    shutil.copytree(grouped, backup)
    other = _other_target(grouped, tid)
    M.decide(grouped, target_ids=[other], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    shutil.rmtree(grouped)
    shutil.copytree(backup, grouped)  # restored: the log holds fewer decisions than at the adopt
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert tid not in _targets(rep) and [x["reason"].startswith(UNPLACEABLE) for x in rep["stale_rulings"]] == [True]
    assert _value_now(grouped, tid) == 12


def test_the_same_bundle_after_more_decisions_is_still_placed(grouped, tmp_path, capsys, ticking):
    """Decisions recorded after the adopt leave the prefix as it was: a fresh ruling against the 12 supersedes."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    M.decide(grouped, target_ids=[_other_target(grouped, tid)], decision="confirm", value=None, by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert not rep["stale_rulings"] and _value_now(grouped, tid) == 2


@pytest.mark.parametrize("damage", ["", "0" * 64, "not a hash"])
def test_a_damaged_fingerprint_is_unplaceable(grouped, tmp_path, capsys, ticking, damage):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    wb = openpyxl.load_workbook(tmp_path / "Ar.xlsx")
    for row in wb["_isaac"].iter_rows():
        if row[0].value == "decisions_fingerprint":
            row[1].value = damage or " "
    wb.save(tmp_path / "Ar.xlsx")
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert [x["reason"].startswith(UNPLACEABLE) for x in rep["stale_rulings"]] == [True]
    assert _value_now(grouped, tid) == 12


def test_a_workbook_without_the_fingerprint_is_placed_by_its_position_as_before(grouped, tmp_path, capsys, ticking):
    """A c14l workbook (position, no hash, no adopt id): a reject before the adopt never stops a tie, as in c14l."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="reject", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 12})
    wb = openpyxl.load_workbook(tmp_path / "Ar.xlsx")
    for row in wb["_isaac"].iter_rows():
        if row[0].value in ("decisions_fingerprint", "adopt_id"):
            row[0].value = row[1].value = None
    wb.save(tmp_path / "old.xlsx")
    assert "decisions_fingerprint" not in _meta(tmp_path / "old.xlsx") and _meta(tmp_path / "old.xlsx")["decisions_at_adopt"] == 1
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "old.xlsx", capsys)
    assert [t["target"]["id"] for t in rep["rulings_tied_to_sheet"]] == [tid] and not rep["stale_rulings"]


# --- MED-3 ----------------------------------------------------------------------------------------------------


def test_a_scientist_correcting_their_own_ruling_on_the_same_workbook_supersedes(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: adopted with nothing recorded, ruled 2 and imported, then the same cell edited to 12."""
    tid = _tid(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    p, st = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    assert st == "awaiting" and _governing(tmp_path / "A.xlsx", p["id"]) == []
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    [first] = _decisions_on(grouped, tid)
    adopt_id = _meta(tmp_path / "A.xlsx")["adopt_id"]
    assert first["note"].endswith(f"= 2){T._adopt_note(adopt_id)}") and T._note_adopt_id(first) == adopt_id
    _rule(tmp_path / "Ar.xlsx", tmp_path / "Ar12.xlsx", {p["id"]: 12})
    rep = _imp(grouped, tmp_path / "Ar12.xlsx", capsys)  # without --supersede: the ordinary advice
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    # their own correction on the same workbook still needs --supersede (c15b H2 is only a ruling against what the
    # row named); the reason says where the value recorded now came from (c15b M3)
    assert clash["reason"].startswith(f"an earlier scientist decision gives a different value (recorded now: 2 by {WHO} "
                                      "(2099-01-01), from an earlier import of this workbook); skipped (pass --supersede")
    rep = _imp(grouped, tmp_path / "Ar12.xlsx", capsys, "--supersede")
    assert rep["recorded"] == 1 and not rep["stale_rulings"] and not rep["clashes"]
    assert _value_now(grouped, tid) == 12 and len(_decisions_on(grouped, tid)) == 2
    _rule(tmp_path / "Ar12.xlsx", tmp_path / "Ar7.xlsx", {p["id"]: 7})  # and again: still their own
    assert _imp(grouped, tmp_path / "Ar7.xlsx", capsys, "--supersede")["recorded"] == 1 and _value_now(grouped, tid) == 7
    again, st = _state(grouped, s, tmp_path / "re.xlsx", capsys)
    assert st == "settled" and again["already_recorded"]["statement"].startswith("already recorded: 7 (")


def test_their_correction_is_never_made_against_a_value_someone_else_recorded_since(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    M.decide(grouped, target_ids=[tid], decision="correct", value=7, by=OTHER, orcid=None)
    _rule(tmp_path / "Ar.xlsx", tmp_path / "Ar12.xlsx", {p["id"]: 12})
    rep = _imp(grouped, tmp_path / "Ar12.xlsx", capsys, "--supersede")
    assert tid not in _targets(rep) and [x["target"]["id"] for x in rep["stale_rulings"]] == [tid]
    assert _value_now(grouped, tid) == 7


@pytest.mark.parametrize("recorded_first", [False, True])
def test_two_adoptions_of_the_same_sheet_still_converge(grouped, tmp_path, capsys, ticking, recorded_first):
    """A and B adopted from ONE sheet (two adopt ids), A rules 2, B rules 12: A, B, A, B … with --supersede."""
    tid = _tid(grouped)
    if recorded_first:
        M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    pa, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    pb, _ = _state(grouped, s, tmp_path / "B.xlsx", capsys)
    assert _meta(tmp_path / "A.xlsx")["adopt_id"] != _meta(tmp_path / "B.xlsx")["adopt_id"]
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {pa["id"]: 2})
    _rule(tmp_path / "B.xlsx", tmp_path / "Br.xlsx", {pb["id"]: 12})
    assert tid in _targets(_imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")) and _value_now(grouped, tid) == 2
    ruled = _decisions_on(grouped, tid)[-1]["decision_id"]
    n = len(_decisions_on(grouped, tid))
    for cycle in range(3):
        rep = _imp(grouped, tmp_path / "Br.xlsx", capsys, "--supersede")
        assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"], cycle
        [stale] = rep["stale_rulings"]
        # c15b L3: named by its day, never its decision id (the entry's decision_id keeps it)
        assert stale["decision_id"] == ruled
        assert stale["reason"].startswith("your earlier ruling on this row (2099-01-01) is what is recorded now; this "
                                          "ruling, on another adoption of the same sheet, was not made against it, so "
                                          "nothing is recorded for it, even with --supersede"), cycle
        rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
        assert rep["recorded"] == 0 and not rep["stale_rulings"] and not rep["rulings_tied_to_sheet"], cycle
    assert len(_decisions_on(grouped, tid)) == n and _value_now(grouped, tid) == 2


def test_adopting_again_into_a_settled_row_then_ruling_differently_supersedes(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    p2, st = _state(grouped, s, tmp_path / "A2.xlsx", capsys)
    assert st == "settled" and p2["already_recorded"]["statement"].endswith("; leave blank to keep")
    _rule(tmp_path / "A2.xlsx", tmp_path / "A2r.xlsx", {p2["id"]: 12})
    rep = _imp(grouped, tmp_path / "A2r.xlsx", capsys, "--supersede")
    assert rep["recorded"] == 1 and not rep["stale_rulings"] and _value_now(grouped, tid) == 12
    later = _decisions_on(grouped, tid)[-1]["decision_id"]
    # the first adoption, ruled 2, never flips it back: their later ruling is what is recorded now
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert rep["recorded"] == 0
    [stale] = rep["stale_rulings"]
    assert stale["reason"].startswith("your earlier ruling on this row (2099-01-01) is what is recorded now")
    assert stale["decision_id"] == later
    assert _value_now(grouped, tid) == 12


def test_ruled_here_reads_notes_with_and_without_the_adopt_id():
    their = ("SYN_sheet.xlsx", "'File List'!H8")
    base = "template A.xlsx 'Disagreements'!H2 (your ruling on disagreement D1: SYN_sheet.xlsx 'File List'!H8 = "
    aid = "ab" * 16
    odd = "x) (adopt id " + "c" * 32 + ")"
    log = [{"note": base + "2)"}, {"note": base + "2)" + T._adopt_note(aid)}, {"note": base + json.dumps(odd) + ")"},
           {"note": base + json.dumps(odd) + ")" + T._adopt_note(aid)}, {"note": base + "2) (adopt id nothex)"}]
    assert T._ruled_here(log, 0, (*their, 2)) and T._ruled_here(log, 1, (*their, 2))
    assert not T._ruled_here(log, 1, (*their, 3))
    assert T._ruled_here(log, 2, (*their, odd)) and T._ruled_here(log, 3, (*their, odd))
    assert not T._ruled_here(log, 4, (*their, 2))  # not an adopt id: the value read is not 2
    assert [T._note_adopt_id(d) for d in log] == [None, aid, None, aid, None]
    assert T._adopt_id(" " + aid.upper() + " ") == aid and T._adopt_id("xyz") is None and T._adopt_id(5) is None


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_a_whole_beamtime_ruling_is_recorded_for_every_run_or_none(grouped, tmp_path, capsys, ticking):
    """Campaign Info's beamline row reaches every run; BL11 recorded on each before the adopt, then another scientist
    records BL12 on ONE run. The ruling (BL99) with --supersede: nothing recorded, every target listed."""
    [s] = _sheets(grouped, tmp_path, 1)
    bl = _d(_adopt_json(grouped, s, tmp_path / "probe.xlsx", capsys), "Beamline/Instrument")
    b = M.load(grouped)
    tids = [m["value_id"] for m in b["missing_values"] if m.get("target_field_path") == bl["path"]]
    assert len(tids) == 9
    M.decide(grouped, target_ids=tids, decision="correct", value="BL11", by=OTHER, orcid=None)
    bl = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Beamline/Instrument")
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {bl["id"]: "BL99"})
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    n = {tid: len(_decisions_on(grouped, tid)) for tid in tids}
    code, rep, err = _import(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert code == 0, err
    assert not set(tids) & _targets(rep) and not rep["rulings_tied_to_sheet"]
    stale = {x["target"]["id"]: x for x in rep["stale_rulings"]}
    assert set(stale) == set(tids) and len(rep["stale_rulings"]) == 9
    assert stale[tids[0]]["reason"].startswith("ruled on a workbook adopted before ")
    for tid in tids[1:]:
        assert stale[tid]["reason"].startswith(
            f"this ruling reaches 9 targets and is recorded for all of them or none, and {tids[0]}"), tid
        # c15b M2: the cell's one command for all nine (stale_by_cell), never this target's own
        assert stale[tid]["reason"].endswith(", or record this value for all 9 targets of this cell with one command "
                                             "(stale_by_cell: command)")
    [cell] = rep["stale_by_cell"]
    assert cell["command"].count("--target ") == 9 and cell["command"].endswith("--value=BL99 --by \"<your name>\"")
    code, text, err = _import_text(grouped, tmp_path / "Ar.xlsx", capsys, "--apply", "--supersede")
    assert code == 0, err
    summary = next(x for x in text.splitlines() if x.startswith("Summary:"))
    assert "; 1 cell(s) not tied to your sheet (nothing recorded)" in summary
    assert {tid: len(_decisions_on(grouped, tid)) for tid in tids} == n


def test_a_whole_beamtime_ruling_against_what_is_recorded_now_is_recorded_for_every_run(grouped, tmp_path, capsys, ticking):
    [s] = _sheets(grouped, tmp_path, 1)
    bl = _d(_adopt_json(grouped, s, tmp_path / "probe.xlsx", capsys), "Beamline/Instrument")
    tids = [m["value_id"] for m in M.load(grouped)["missing_values"] if m.get("target_field_path") == bl["path"]]
    M.decide(grouped, target_ids=tids, decision="correct", value="BL11", by=OTHER, orcid=None)
    bl = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Beamline/Instrument")
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {bl["id"]: "BL99"})
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert set(tids) <= _targets(rep) and not rep["stale_rulings"]
    assert all(_decisions_on(grouped, tid)[-1]["value"] == "BL99" for tid in tids)


# --- LOW-1 and the keeps=False wordings ---------------------------------------------------------------------------


def _nothing_then_a_value(grouped, tmp_path, capsys):
    tid = _tid(grouped)
    [s] = _sheets(grouped, tmp_path, 1)
    p, st = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    assert st == "awaiting" and _governing(tmp_path / "A.xlsx", p["id"]) == []
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    return tid, _decisions_on(grouped, tid)[-1]["decision_id"]


NEVER_SAW = ("ruled on a workbook adopted with nothing recorded here; this ruling was made before " + OTHER + " recorded "
             "the value now (2099-01-01), so it never saw it: nothing is recorded for it, even with --supersede, and the "
             "value recorded now is kept. Adopt again and rule against what is recorded now, or record this value "
             "directly: isaac bundle decide <bundle_dir> --target {} --decision correct --value=2 --json --by "
             "\"<your name>\"")


def test_a_workbook_adopted_with_nothing_recorded_never_says_an_earlier_value(grouped, tmp_path, capsys, ticking):
    tid, did = _nothing_then_a_value(grouped, tmp_path, capsys)
    [stale] = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")["stale_rulings"]
    assert stale["reason"] == NEVER_SAW.format(tid) and "earlier value" not in stale["reason"]
    assert stale["decision_id"] == did
    assert _value_now(grouped, tid) == 12


def test_a_c14k_workbook_adopted_with_nothing_recorded_then_a_value(grouped, tmp_path, capsys, ticking):
    """No `decisions_at_adopt` (nor fingerprint, nor adopt id): placed by its time, which is before the 12."""
    tid, did = _nothing_then_a_value(grouped, tmp_path, capsys)
    _without_adopt_position(tmp_path / "Ar.xlsx", tmp_path / "old.xlsx", _meta(tmp_path / "Ar.xlsx")["exported_utc"])
    rep = _imp(grouped, tmp_path / "old.xlsx", capsys, "--supersede")
    assert tid not in _targets(rep)
    [stale] = rep["stale_rulings"]
    assert stale["reason"] == NEVER_SAW.format(tid)
    rep = _imp(grouped, tmp_path / "old.xlsx", capsys)
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    assert "--supersede does not record it either" in clash["reason"] and f"--target {tid} --decision correct" in clash["reason"]
    assert _value_now(grouped, tid) == 12 and len(_decisions_on(grouped, tid)) == 1


def _mini(decisions):
    """A bundle of one candidate ``c1`` (extracted 12) and these decisions on it, for :func:`template._stale_reason`."""
    log = [{"decision_id": f"d-{i:05d}", "target": {"kind": "candidate", "id": "c1"}, "decided_utc": f"2099-01-01T00:00:0{i}Z",
            **d} for i, d in enumerate(decisions, start=1)]
    return T._Chains({"scientist_decisions": log, "candidates": [{"candidate_id": "c1", "value": 12}]})


TAIL = (" nothing is recorded for it, even with --supersede, and the value recorded now is kept. Adopt again and rule "
        "against what is recorded now, or record this value directly: isaac bundle decide <bundle_dir> --target c1 "
        "--decision correct --value=2 --json --by \"<your name>\"")
OWN_NOTE = ("template B.xlsx 'Disagreements'!H2 (your ruling on disagreement D1: SYN_sheet.xlsx 'File List'!H8 = 2)"
            + T._adopt_note("ab" * 16))


@pytest.mark.parametrize("decisions, against, adopted_at, exported, ruling, expected", [
    # made against an earlier value: it read d-00001 (12), and d-00002 recorded 7 since
    ([{"decision": "confirm"}, {"decision": "correct", "value": 7}], ["d-00001"], 1, None, None,
     "ruled on a workbook adopted before someone recorded the value now (2099-01-01); this ruling was made against an "
     "earlier value, so" + TAIL),
    # LOW-1: nothing recorded at the adopt
    ([{"decision": "confirm"}], [], 0, None, None,
     "ruled on a workbook adopted with nothing recorded here; this ruling was made before someone recorded the value "
     "now (2099-01-01), so it never saw it:" + TAIL),
    # not placed: no position, and a time that cannot be read
    ([{"decision": "confirm"}], [], None, "not a time", None,
     "ruled on a workbook not shown to have been adopted against the value someone recorded (2099-01-01), so" + TAIL),
    # MED-3: their own earlier ruling on this row, from another adoption of the same sheet
    ([{"decision": "confirm", "note": OWN_NOTE}], [], 0, None, ("SYN_sheet.xlsx", "'File List'!H8", 2),
     "your earlier ruling on this row (2099-01-01) is what is recorded now; this ruling, on another adoption of the same "
     "sheet, was not made against it, so" + TAIL),
    ([{"decision": "confirm"}], [T.GOVERNING_DAMAGED], 0, None, None,
     "ruled on a workbook whose `_isaac` governing_decisions value is damaged, so it is never recorded over another "
     "value, even with --supersede; the value recorded now is kept and nothing is recorded for this ruling. Adopt "
     "again and rule against what is recorded now, or record this value directly: isaac bundle decide <bundle_dir> "
     "--target c1 --decision correct --value=2 --json --by \"<your name>\""),
    # MED-2: unplaceable
    ([{"decision": "confirm"}], [T.GOVERNING_UNPLACEABLE], None, None, None,
     UNPLACEABLE + " and rule against what is recorded now; nothing is recorded for this ruling, even with --supersede, "
     "and the value recorded now is kept, or record this value directly: isaac bundle decide <bundle_dir> --target c1 "
     "--decision correct --value=2 --json --by \"<your name>\""),
])
def test_the_keeps_false_wordings(decisions, against, adopted_at, exported, ruling, expected):
    chains = _mini(decisions)
    place = len(chains.log) - 1
    run = chains(place)
    cell = {"value": 2, "ruled_against": against, **({"ruling": ruling} if ruling else {})}
    got = T._stale_reason(cell, [chains.log[p] for p in run], chains, run, exported, adopted_at=adopted_at, keeps=False,
                          target="c1", decision="correct", adopt_id="cd" * 16)  # c14n LOW-4: this workbook's own id
    assert got == expected


# --- LOW-2 ----------------------------------------------------------------------------------------------------


def test_the_command_a_stale_reason_offers_records_the_value(grouped, tmp_path, capsys, ticking):
    tid, _did = _nothing_then_a_value(grouped, tmp_path, capsys)
    [stale] = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")["stale_rulings"]
    argv = _command_in(stale["reason"])
    assert argv[:2] == ["bundle", "decide"] and argv[argv.index("--target") + 1] == tid
    capsys.readouterr()
    assert _run_command(argv, grouped) == 0, capsys.readouterr().err
    assert _value_now(grouped, tid) == 2


def _without_recorded_shown(xlsx) -> None:
    """``xlsx`` as a build before c15b wrote it: no ``recorded_shown`` column, so a ruling over another value needs
    --supersede (c15b H2)."""
    wb = openpyxl.load_workbook(xlsx)
    ws = wb["_isaac"]
    for row in ws.iter_rows():
        for c in row:
            if c.value == T.RECORDED_SHOWN:
                for r in range(c.row, ws.max_row + 1):
                    ws.cell(r, c.column).value = None
    wb.save(xlsx)


def test_every_clash_reason_offers_the_command(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    _without_recorded_shown(tmp_path / "Ar.xlsx")  # c15b H2: else the row's ruling records without --supersede
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    # c15b M3: what is recorded now, by whom and from where (the row did not name it: its workbook predates c15b)
    assert clash["reason"] == (f"an earlier scientist decision gives a different value (recorded now: 12 by {OTHER} "
                               "(2099-01-01), from a decide); skipped (pass --supersede to "
                               "record this one), or record this value directly: isaac bundle decide <bundle_dir> "
                               f"--target {tid} --decision correct --value=2 --json --by \"<your name>\"")  # c14n LOW-6
    argv = _command_in(clash["reason"])
    capsys.readouterr()
    assert _run_command(argv, grouped) == 0, capsys.readouterr().err
    assert _value_now(grouped, tid) == 2


def test_decide_command_quotes_text_and_passes_other_values_as_json():
    assert T.decide_command("mv-1", "correct", "BL 11") == (
        "isaac bundle decide <bundle_dir> --target mv-1 --decision correct --value='BL 11' --by \"<your name>\"")
    assert T.decide_command("c-1", "correct", 0.1).endswith("--value=0.1 --json --by \"<your name>\"")  # c14n LOW-1
    assert T.decide_command("c-1", "confirm", 12) == (
        "isaac bundle decide <bundle_dir> --target c-1 --decision confirm --by \"<your name>\"")


# --- LOW-3 ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value, expected", [("²", None), ("4²", None), ("٣", None), ("１", None), (" 4 ", 4), ("4", 4)])
def test_adopt_position_takes_ascii_digits_only(value, expected):
    assert T._adopt_position(value, 5) == expected


def test_a_scan_selection_with_a_superscript_digit_is_not_a_selection():
    from isaac_api.local_import.processing import athena

    assert athena.scan_selection("SYN_a_²", ["SYN_a"]) is None
    assert athena.scan_selection("SYN_a_3", ["SYN_a"]) == [3]
