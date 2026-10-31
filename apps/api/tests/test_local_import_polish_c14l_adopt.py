"""c14l: --supersede never lets stale workbooks flip a value; "since" is a place in the log. Synthetic only (SYN_/ZZ).

* MED-1: with ``--supersede``, a Disagreements ruling giving a different value is recorded over the value that
  governs only when it was made against it (:func:`template._rules_against_now` with ``keeps=False``); otherwise it
  is listed in ``stale_rulings`` ("this ruling was made against an earlier value …, even with --supersede"), so two
  workbooks ruling different values converge instead of flipping the value at every import. A fresh ruling against
  the value recorded now still supersedes; without ``--supersede`` such a clash says ``--supersede`` will not help.
* MED-2: adopt keeps the decision log's length (``_isaac`` ``decisions_at_adopt``): a reject, a defer or an off-list
  value recorded BEFORE the adopt never stops a tie, and a reason never says "since" of a decision made before the
  adopt (a workbook without the length says it only when a readable time proves it).
* LOW-1: a ``governing_decisions`` list holding anything but strings is damaged.
* LOW-2: the stale section and summary say "Rulings not tied to your sheet"; each reason gives the cause.
* LOW-3: "N decision(s) recorded, including 1 ruling cell that kept the same value … (1 target)".
* Gaps: three sheets converge; a whole-beamtime row and an Electrolyte name+concentration row across two sheets; an
  old workbook placed by time, then a same-value decision.
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
from test_local_import_polish_c14h_adopt import _edit_ph
from test_local_import_polish_c14j_adopt import _adopted_before_governing_was_kept, _decisions_on, _governing, _import_text

OTHER = "Other Synthetic Scientist"
ENV = "context.environment"
NOT_SINCE = "since"


def _state(grouped, theirs, out, capsys):
    """Adopt ``theirs`` again: (its run-007 pH row, ``settled`` or ``awaiting``)."""
    ph = _d(_adopt_json(grouped, theirs, out, capsys), "pH", run_id="run-007")
    return ph, "settled" if ph["already_recorded"] else "awaiting"


def _imp(grouped, x, capsys, *extra):
    code, rep, err = _import(grouped, x, capsys, "--apply", *extra)
    assert code == 0, err
    return rep


def _sheets(grouped, tmp_path, n, **kw):
    """``n`` of their own sheets (different file names), all saying pH 2 for run-007; the file says 12."""
    s1 = _their_sheet(grouped, tmp_path / THEIRS, **kw)
    out = [s1]
    for i in range(1, n):
        s = tmp_path / f"SYN_sheet_{i}.xlsx"
        shutil.copy(s1, s)
        out.append(s)
    return out


def _tid(grouped):
    return _cand(M.load(grouped), PH, "run-007")["candidate_id"]


def _value_now(grouped, tid):
    from isaac_api.local_import import bundle as B

    b = M.load(grouped)
    cand = next(c for c in b["candidates"] if c["candidate_id"] == tid)
    return B.final_value(cand.get("value"), B.candidate_decision(b, cand), cand.get("readings"))


def _or_decide(tid, decision, value=None) -> str:
    """c14m LOW-2: how every stale and clash reason ends (the `decide` command for its target)."""
    return f", or record this value directly: {T.decide_command(tid, decision, value)}"


def _meta(xlsx) -> dict:
    return T._marker(openpyxl.load_workbook(xlsx))["meta"]


def _without_adopt_position(xlsx, out, exported_utc) -> None:
    """``xlsx`` as a c14j/c14k build wrote it (``governing_decisions`` kept, but no ``decisions_at_adopt``, nor c14m's
    ``decisions_fingerprint`` and ``adopt_id``), adopted at ``exported_utc`` (the bundle's clock ticks from 2099 in
    these tests; the export time is the real clock's)."""
    wb = openpyxl.load_workbook(xlsx)
    for row in wb["_isaac"].iter_rows():
        if row[0].value in ("decisions_at_adopt", "decisions_fingerprint", "adopt_id"):
            row[0].value = row[1].value = None
        if row[0].value == "exported_utc":
            row[1].value = exported_utc
    wb.save(out)


# --- MED-1 ----------------------------------------------------------------------------------------------------


def _flip_flop_setup(grouped, tmp_path, capsys):
    """12 confirmed; sheets A and B both adopted against it; A rules 2, B rules 12."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)  # 12
    [first] = _decisions_on(grouped, tid)
    s1, s2 = _sheets(grouped, tmp_path, 2)
    pa, _ = _state(grouped, s1, tmp_path / "A.xlsx", capsys)
    pb, _ = _state(grouped, s2, tmp_path / "B.xlsx", capsys)
    assert _governing(tmp_path / "A.xlsx", pa["id"]) == _governing(tmp_path / "B.xlsx", pb["id"]) == [first["decision_id"]]
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {pa["id"]: 2})
    _rule(tmp_path / "B.xlsx", tmp_path / "Br.xlsx", {pb["id"]: 12})
    return tid, (s1, s2)


def test_supersede_flip_flop_converges(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: A, B, A, B … each with --apply --supersede recorded one decision every time."""
    tid, _ = _flip_flop_setup(grouped, tmp_path, capsys)
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")  # made against the 12: recorded over it
    assert rep["recorded"] > 0 and not rep["stale_rulings"]
    assert _value_now(grouped, tid) == 2
    after_a = _decisions_on(grouped, tid)[-1]["decision_id"]
    for cycle in range(3):
        rep = _imp(grouped, tmp_path / "Br.xlsx", capsys, "--supersede")
        assert rep["recorded"] == 0 and not rep["clashes"] and not rep["rulings_tied_to_sheet"], cycle
        [stale] = rep["stale_rulings"]
        assert stale["target"]["id"] == tid and stale["value"] == 12 and stale["decision_id"] == after_a
        assert stale["reason"] == (
            f"ruled on a workbook adopted before {after_a}; this ruling was made against an earlier value, so nothing is "
            "recorded for it, even with --supersede, and the value recorded now is kept. Adopt again and rule against "
            "what is recorded now" + _or_decide(tid, "confirm"))
        rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
        assert rep["recorded"] == 0 and not rep["stale_rulings"] and not rep["rulings_tied_to_sheet"], cycle
    assert len(_decisions_on(grouped, tid)) == 2 and _value_now(grouped, tid) == 2


def test_without_supersede_the_stale_clash_says_supersede_does_not_record_it(grouped, tmp_path, capsys, ticking):
    tid, (_s1, s2) = _flip_flop_setup(grouped, tmp_path, capsys)
    _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    rep = _imp(grouped, tmp_path / "Br.xlsx", capsys)
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    assert clash["reason"].startswith("an earlier scientist decision gives a different value; skipped, and --supersede "
                                      "does not record it either: this ruling was not made against the value recorded now")
    assert "pass --supersede" not in clash["reason"]
    # a ruling made against the value recorded now keeps the old advice
    b2, _ = _state(grouped, s2, tmp_path / "B2.xlsx", capsys)
    _rule(tmp_path / "B2.xlsx", tmp_path / "B2r.xlsx", {b2["id"]: 12})
    rep = _imp(grouped, tmp_path / "B2r.xlsx", capsys)
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    assert clash["reason"].endswith("skipped (pass --supersede to record this one)" + _or_decide(tid, "confirm"))
    assert len(_decisions_on(grouped, tid)) == 2


def test_a_fresh_ruling_against_the_value_recorded_now_still_supersedes(grouped, tmp_path, capsys, ticking):
    tid, (_s1, s2) = _flip_flop_setup(grouped, tmp_path, capsys)
    _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")  # 2 recorded over the 12
    assert _imp(grouped, tmp_path / "Br.xlsx", capsys, "--supersede")["stale_rulings"]
    _edit_ph(s2, 2, 3)  # their sheet now says 3, so B adopted again asks the row against the 2 recorded now
    b2, st = _state(grouped, s2, tmp_path / "B2.xlsx", capsys)
    assert st == "awaiting" and _governing(tmp_path / "B2.xlsx", b2["id"]) == [_decisions_on(grouped, tid)[-1]["decision_id"]]
    _rule(tmp_path / "B2.xlsx", tmp_path / "B2r.xlsx", {b2["id"]: 12})
    rep = _imp(grouped, tmp_path / "B2r.xlsx", capsys, "--supersede")
    assert rep["recorded"] >= 1 and not rep["stale_rulings"] and not rep["clashes"]
    assert _value_now(grouped, tid) == 12 and len(_decisions_on(grouped, tid)) == 3
    # A's workbook was adopted before that 12: it never flips it back
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert rep["recorded"] == 0 and [s["target"]["id"] for s in rep["stale_rulings"]] == [tid]
    assert _value_now(grouped, tid) == 12 and len(_decisions_on(grouped, tid)) == 3


def test_a_fresh_ruling_supersedes_a_reject_recorded_before_the_adopt(grouped, tmp_path, capsys, ticking):
    """A reject is not among the decisions a row reads (it gives no value), but recorded before the adopt it was there
    to see: the ruling is made against it and --supersede records it."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="reject", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    assert _governing(tmp_path / "A.xlsx", p["id"]) == []
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 12})
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert [c["target"]["id"] for c in rep["clashes"] if c["target"]["id"] == tid] == [tid]
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    assert not rep["stale_rulings"] and _decisions_on(grouped, tid)[-1]["decision"] in ("confirm", "correct")
    assert _value_now(grouped, tid) == 12


def test_an_old_workbook_supersedes_only_when_its_time_places_it_after_the_value(grouped, tmp_path, capsys, ticking):
    """A workbook adopted before `governing_decisions` (and the log's length) were kept: placed by its export time."""
    tid, _ = _flip_flop_setup(grouped, tmp_path, capsys)
    [first] = _decisions_on(grouped, tid)
    _adopted_before_governing_was_kept(tmp_path / "Br.xlsx", tmp_path / "B_old.xlsx", first["decided_utc"])
    _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")  # 2, recorded after B's workbook
    after_a = _decisions_on(grouped, tid)[-1]
    rep = _imp(grouped, tmp_path / "B_old.xlsx", capsys, "--supersede")
    [stale] = rep["stale_rulings"]
    assert stale["reason"].startswith(f"ruled on a workbook adopted before {after_a['decision_id']}; this ruling was made "
                                      "against an earlier value")
    assert _value_now(grouped, tid) == 2
    _adopted_before_governing_was_kept(tmp_path / "Br.xlsx", tmp_path / "B_new.xlsx", after_a["decided_utc"])
    rep = _imp(grouped, tmp_path / "B_new.xlsx", capsys, "--supersede")
    assert not rep["stale_rulings"] and _value_now(grouped, tid) == 12


# --- MED-2 ----------------------------------------------------------------------------------------------------


def test_adopt_keeps_the_decision_logs_length(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="defer", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    _state(grouped, s, tmp_path / "A.xlsx", capsys)
    assert _meta(tmp_path / "A.xlsx")["decisions_at_adopt"] == len(M.load(grouped)["scientist_decisions"]) == 1


@pytest.mark.parametrize("value, log_length, expected", [
    (0, 0, 0), (3, 5, 3), (5, 5, 5), ("4", 5, 4), (6, 5, None), (-1, 5, None), (True, 5, None), (2.0, 5, None),
    (None, 5, None), ("x", 5, None), ("", 5, None)])
def test_adopt_position_reads_only_a_whole_number_within_the_log(value, log_length, expected):
    assert T._adopt_position(value, log_length) == expected


def _decided_before_adopt(grouped, tmp_path, capsys, decision):
    """``decision`` on run-007 pH, then A adopted (governing ``[]``), ruled 12, then another scientist confirms 12."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision=decision, value=None, by=OTHER, orcid=None)
    [before] = _decisions_on(grouped, tid)
    [s] = _sheets(grouped, tmp_path, 1)
    p, st = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    assert st == "awaiting" and _governing(tmp_path / "A.xlsx", p["id"]) == []
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 12})
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    after = _decisions_on(grouped, tid)[-1]
    return tid, s, before, after


@pytest.mark.parametrize("decision", ["reject", "defer"])
def test_a_reject_or_defer_before_the_adopt_never_stops_a_tie(grouped, tmp_path, capsys, ticking, decision):
    tid, s, before, after = _decided_before_adopt(grouped, tmp_path, capsys, decision)
    code, text, err = _import_text(grouped, tmp_path / "Ar.xlsx", capsys, "--apply")
    assert code == 0, err
    assert f"{before['decision_id']} {decision}ed the value since" not in text
    assert "Rulings not tied to your sheet" not in text
    assert "'Disagreements'!H" in text and f"(was {after['decision_id']})" in text  # tied
    assert _state(grouped, s, tmp_path / "re.xlsx", capsys)[1] == "settled"  # no extra round
    assert len(_decisions_on(grouped, tid)) == 3


@pytest.mark.parametrize("decision", ["reject", "defer"])
def test_without_the_adopt_position_a_decision_before_the_adopt_is_never_said_to_come_since(
        grouped, tmp_path, capsys, ticking, decision):
    """A c14j/c14k workbook (no `decisions_at_adopt`): stale as before, but its reason never says "since" of a
    decision whose time is before the workbook's."""
    tid, s, before, after = _decided_before_adopt(grouped, tmp_path, capsys, decision)
    _without_adopt_position(tmp_path / "Ar.xlsx", tmp_path / "old.xlsx", before["decided_utc"])  # adopted after it
    rep = _imp(grouped, tmp_path / "old.xlsx", capsys)
    [stale] = rep["stale_rulings"]
    assert stale["reason"] == (f"ruled on a workbook adopted before {after['decision_id']}; nothing is recorded for "
                               "this ruling: the value is already 12; adopt again to settle this row")  # c14n LOW-3
    assert NOT_SINCE not in stale["reason"]
    assert len(_decisions_on(grouped, tid)) == 2


def _env_targets(grouped, run_ids):
    b = M.load(grouped)
    out = [c["candidate_id"] for c in b["candidates"] if c.get("target_field_path") == ENV and c.get("run_id") in run_ids]
    out += [m["value_id"] for m in b["missing_values"] if m.get("target_field_path") == ENV and m.get("run_id") in run_ids]
    return out


def test_an_off_list_value_before_the_adopt_never_stops_a_tie(grouped, tmp_path, capsys, ticking):
    """An Environment decision recorded before the adopt whose value the field's list does not take (recorded when
    the word was allowed; a value no record takes, so not among the decisions the row reads); they rule `in_situ`;
    another scientist records `in_situ`: the ruling ties."""
    [s] = _sheets(grouped, tmp_path, 1)
    probe = _d(_adopt_json(grouped, s, tmp_path / "probe.xlsx", capsys), "Environment", kind="not_allowed")
    targets = _env_targets(grouped, probe["runs"])
    assert targets
    M.decide(grouped, target_ids=targets, decision="correct", value="ex_situ", by=OTHER, orcid=None)
    b = M.load(grouped)
    for d in b["scientist_decisions"]:
        d["value"] = "aqueous_electrochemistry"  # off the field's list now
    M.save_bundle(grouped, b)
    n_before = len(M.load(grouped)["scientist_decisions"])
    env = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Environment", kind="not_allowed")
    assert _governing(tmp_path / "A.xlsx", env["id"]) == []
    assert _meta(tmp_path / "A.xlsx")["decisions_at_adopt"] == n_before
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {env["id"]: "in_situ"})
    M.decide(grouped, target_ids=targets, decision="correct", value="in_situ", by=OTHER, orcid=None)
    code, text, err = _import_text(grouped, tmp_path / "Ar.xlsx", capsys, "--apply")
    assert code == 0, err
    assert "a different value was recorded since" not in text and "Rulings not tied to your sheet" not in text
    code, rep, err = _import(grouped, tmp_path / "Ar.xlsx", capsys)
    assert code == 0, err
    assert not rep["stale_rulings"] and not rep["rulings_tied_to_sheet"] and rep["would_record"] == 0
    assert _d(_adopt_json(grouped, s, tmp_path / "re.xlsx", capsys), "Environment", kind="not_allowed")["already_recorded"]


@pytest.mark.parametrize("position", [True, False])
def test_a_different_value_recorded_after_the_adopt_is_still_said_since(grouped, tmp_path, capsys, ticking, position):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)  # 12
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 12})
    if not position:  # placed by time: adopted at the 12's decision, so the 7 decided after it came since
        _without_adopt_position(tmp_path / "Ar.xlsx", tmp_path / "Ar.xlsx", _decisions_on(grouped, tid)[0]["decided_utc"])
    M.decide(grouped, target_ids=[tid], decision="correct", value=7, by=OTHER, orcid=None)
    changed = _decisions_on(grouped, tid)[-1]["decision_id"]
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)  # 12 again
    back = _decisions_on(grouped, tid)[-1]["decision_id"]
    [stale] = _imp(grouped, tmp_path / "Ar.xlsx", capsys)["stale_rulings"]
    assert stale["reason"] == (f"ruled on a workbook adopted before {back}, and a different value was recorded since "
                               f"({changed}); nothing is recorded for this ruling: the value is already 12; adopt again "
                               "to settle this row")  # c14n LOW-3


# --- LOW-1 ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("damaged", ["[1]", "[null]", '[["d-00001"]]', '["d-00001", 5]', '["d-00001", true]',
                                     '[{"d": 1}]'])
def test_a_governing_list_with_any_non_string_element_is_damaged(damaged):
    assert T._marker_governing({"governing_decisions": damaged}) == [T.GOVERNING_DAMAGED]
    assert T._marker_governing({"governing_decisions": '["d-00001", "d-00002"]'}) == ["d-00001", "d-00002"]


def test_a_governing_list_with_a_number_beside_the_id_never_ties(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)
    [first] = _decisions_on(grouped, tid)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 12})
    wb = openpyxl.load_workbook(tmp_path / "Ar.xlsx")
    wm = wb["_isaac"]
    [(r0, c0)] = [(c.row, c.column) for row in wm.iter_rows() for c in row if c.value == "governing_decisions"]
    [row] = [r for r in range(r0 + 1, wm.max_row + 1) if wm.cell(r, 1).value == p["id"]]
    wm.cell(row, c0).value = f'["{first["decision_id"]}", 5]'
    wb.save(tmp_path / "Ar.xlsx")
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert not rep["rulings_tied_to_sheet"] and tid not in {d["target"]["id"] for d in rep["decisions"]}
    [stale] = rep["stale_rulings"]
    assert stale["target"]["id"] == tid and "governing_decisions value is damaged" in stale["reason"]
    assert len(_decisions_on(grouped, tid)) == 1


# --- LOW-2 / LOW-3 --------------------------------------------------------------------------------------------


def test_the_stale_section_and_summary_are_neutral(grouped, tmp_path, capsys, ticking):
    _flip_flop_setup(grouped, tmp_path, capsys)
    _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    code, text, err = _import_text(grouped, tmp_path / "Br.xlsx", capsys, "--apply", "--supersede")
    assert code == 0, err
    lines = text.splitlines()
    head = lines.index("Rulings not tied to your sheet (nothing is recorded for them and the value recorded now is kept; "
                       "each line says why):")
    assert lines[head + 1].startswith("  'Disagreements'!H") and " run-007 pH = 12: ruled on a workbook adopted before " in (
        lines[head + 1])
    assert "even with --supersede" in lines[head + 1]
    summary = next(x for x in lines if x.startswith("Summary:"))
    assert "; 1 ruling cell(s) not tied to your sheet (nothing recorded)" in summary
    assert "adopted before the value recorded now" not in text


def test_the_summary_counts_tied_rulings_among_the_decisions_recorded(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 12})
    for extra, verb, said in (((), "would record", "keeps the same value and is to be tied"),
                              (("--apply",), "recorded", "kept the same value and is now tied")):
        code, text, err = _import_text(grouped, tmp_path / "Ar.xlsx", capsys, *extra)
        assert code == 0, err
        summary = next(x for x in text.splitlines() if x.startswith("Summary:"))
        assert f" decision(s) {verb}, including 1 ruling cell that {said} to your sheet (1 target); " in summary
        assert "; 1 ruling cell " not in summary


# --- test gaps --------------------------------------------------------------------------------------------------


def test_three_sheets_converge(grouped, tmp_path, capsys, ticking):
    """Three sheets adopted first (nothing recorded), each ruled 12, imported in three orders: one decision each, and
    every sheet adopted again is settled."""
    sheets = _sheets(grouped, tmp_path, 3)
    tid = _tid(grouped)
    ruled = []
    for i, s in enumerate(sheets):
        p, _ = _state(grouped, s, tmp_path / f"S{i}.xlsx", capsys)
        _rule(tmp_path / f"S{i}.xlsx", tmp_path / f"S{i}r.xlsx", {p["id"]: 12})
        ruled.append(tmp_path / f"S{i}r.xlsx")
    for order in ([2, 0, 1], [1, 2, 0], [0, 1, 2]):
        for i in order:
            assert not _imp(grouped, ruled[i], capsys)["stale_rulings"], (order, i)
    assert len(_decisions_on(grouped, tid)) == 3
    for cycle in range(2):
        for i, s in enumerate(sheets):
            assert _state(grouped, s, tmp_path / f"re{cycle}{i}.xlsx", capsys)[1] == "settled", (cycle, i)
    for i in range(3):
        rep = _imp(grouped, ruled[i], capsys)
        assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"] and not rep["stale_rulings"]
    assert len(_decisions_on(grouped, tid)) == 3


def test_three_sheets_interleaved_with_another_scientists_confirm_converge(grouped, tmp_path, capsys, ticking):
    sheets = _sheets(grouped, tmp_path, 3)
    tid = _tid(grouped)
    pa, _ = _state(grouped, sheets[0], tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {pa["id"]: 12})
    _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    pb, _ = _state(grouped, sheets[1], tmp_path / "B.xlsx", capsys)
    pc, _ = _state(grouped, sheets[2], tmp_path / "C.xlsx", capsys)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    _rule(tmp_path / "B.xlsx", tmp_path / "Br.xlsx", {pb["id"]: 12})
    _rule(tmp_path / "C.xlsx", tmp_path / "Cr.xlsx", {pc["id"]: 12})
    for x in ("Cr", "Br", "Ar", "Cr", "Br"):
        assert not _imp(grouped, tmp_path / f"{x}.xlsx", capsys)["stale_rulings"], x
    assert len(_decisions_on(grouped, tid)) == 4
    for i, s in enumerate(sheets):
        assert _state(grouped, s, tmp_path / f"re{i}.xlsx", capsys)[1] == "settled", i


def test_a_whole_beamtime_row_across_two_sheets_converges(grouped, tmp_path, capsys, ticking):
    s1, s2 = _sheets(grouped, tmp_path, 2)
    ids = []
    for s, tag in ((s1, "A"), (s2, "B")):
        bl = _d(_adopt_json(grouped, s, tmp_path / f"{tag}.xlsx", capsys), "Beamline/Instrument")
        _rule(tmp_path / f"{tag}.xlsx", tmp_path / f"{tag}r.xlsx", {bl["id"]: "BL99"})
        ids.append(bl["path"])
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    reached = {d["target"]["id"] for d in rep["decisions"] if d["target_field_path"] == ids[0]}
    assert len(reached) > 1
    rep = _imp(grouped, tmp_path / "Br.xlsx", capsys)  # adopted with nothing recorded, only that run since: ties
    assert {t["target"]["id"] for t in rep["rulings_tied_to_sheet"]} == reached and not rep["stale_rulings"]
    for cycle in range(2):
        for tag in ("A", "B"):
            rep = _imp(grouped, tmp_path / f"{tag}r.xlsx", capsys)
            assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"] and not rep["stale_rulings"], (cycle, tag)
        for s, tag in ((s1, "A"), (s2, "B")):
            again = _d(_adopt_json(grouped, s, tmp_path / f"{tag}{cycle}.xlsx", capsys), "Beamline/Instrument")
            assert again["already_recorded"]["statement"].startswith("already recorded: 'BL99' ("), (cycle, tag)
    for tid in reached:
        assert len(_decisions_on(grouped, tid)) == 2


def test_an_electrolyte_name_and_concentration_row_across_two_sheets_converges(grouped, tmp_path, capsys, ticking):
    s1, s2 = _sheets(grouped, tmp_path, 2)
    for s, tag in ((s1, "A"), (s2, "B")):
        el = _d(_adopt_json(grouped, s, tmp_path / f"{tag}.xlsx", capsys), "Electrolyte", kind="name_only")
        _rule(tmp_path / f"{tag}.xlsx", tmp_path / f"{tag}n.xlsx", {el["id"]: "KOH"})
        _rule(tmp_path / f"{tag}n.xlsx", tmp_path / f"{tag}r.xlsx", {el["id"]: 0.1}, column=T.DISAGREE_CONC_COLUMN)
    first = _imp(grouped, tmp_path / "Ar.xlsx", capsys)
    assert first["recorded"] > 0
    rep = _imp(grouped, tmp_path / "Br.xlsx", capsys)
    assert rep["rulings_tied_to_sheet"] and not rep["stale_rulings"]
    log = len(M.load(grouped)["scientist_decisions"])
    for cycle in range(2):
        for tag in ("A", "B"):
            rep = _imp(grouped, tmp_path / f"{tag}r.xlsx", capsys)
            assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"] and not rep["stale_rulings"], (cycle, tag)
        for s, tag in ((s1, "A"), (s2, "B")):
            el = _d(_adopt_json(grouped, s, tmp_path / f"{tag}{cycle}.xlsx", capsys), "Electrolyte", kind="name_only")
            assert el["already_recorded"]["statement"].startswith("already recorded: name 'KOH', concentration 0.1 M ("), (
                cycle, tag)
    assert len(M.load(grouped)["scientist_decisions"]) == log


def test_an_old_workbook_placed_by_time_then_a_same_value_decision_ties(grouped, tmp_path, capsys, ticking):
    """Adopted (by its time) at the 12's decision, before `governing_decisions` were kept; another scientist confirms
    the same 12 before the import: the run reaches back to the decision it was adopted against, so it ties."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=WHO, orcid=None)
    [first] = _decisions_on(grouped, tid)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 12})
    _adopted_before_governing_was_kept(tmp_path / "Ar.xlsx", tmp_path / "old.xlsx", first["decided_utc"])
    assert "decisions_at_adopt" not in _meta(tmp_path / "old.xlsx")
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "old.xlsx", capsys)
    assert [t["target"]["id"] for t in rep["rulings_tied_to_sheet"]] == [tid] and not rep["stale_rulings"]
    assert _state(grouped, s, tmp_path / "re.xlsx", capsys)[1] == "settled"
    rep = _imp(grouped, tmp_path / "old.xlsx", capsys)
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert len(_decisions_on(grouped, tid)) == 3
