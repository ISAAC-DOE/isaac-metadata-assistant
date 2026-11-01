"""c14n: copies of one workbook, and adopted File List cells, never flip a value with --supersede. Synthetic only (SYN_/ZZ).

* MED-1: a decision carrying this workbook's ``adopt_id`` is made against the value now only when the same person
  (``--by``) recorded it: a copy emailed to a colleague shares the id, and the colleague's ruling, made without seeing
  his, is listed in ``stale_rulings`` ("Synthetic Scientist's ruling on this row (d-N), from another copy of this
  workbook, is what is recorded now"). The scientist correcting their own ruling still supersedes.
* MED-2: an adopted File List answer cell is gated as a ruling is: with ``--supersede`` it records over a different
  prior value only when its workbook is placeable and the decision governing now is one it saw at adopt (``_isaac``
  ``[adopted]`` ``governing_decisions``), or its own (adopt id, same ``--by``), or nothing was recorded on the target
  since the adopt. A plain cell of a template that was never adopted records with ``--supersede`` as before.
* LOW-1: the offered ``decide`` command says ``--value=<v>``, so ``-0.5`` and ``-x`` are never read as options.
* LOW-2: for a per-run answer slot this import added (dropped unless recorded), it says
  ``decide --question <qid> --only run:<rid>``, which ``decide`` now takes for a question asked once for the beamtime.
* LOW-3: a stale ruling that keeps the recorded value says "the value is already X; adopt again to settle this row".
* LOW-4: with no readable adopt id, "a ruling on this row (d-N), from this sheet, is what is recorded now".
* LOW-5: a ``decisions_fingerprint`` row kept with a blank value leaves the workbook unplaceable.
* LOW-6: the clash reason closes its parenthesis before the offered command.
"""

from __future__ import annotations

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
    PH, THEIRS, WHO, _adopt_json, _cand, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c7s import RUNS, TECH, _latest, _sheet, _without_own_target, plain, plain_base  # noqa: F401
from test_local_import_polish_c7s import _rule as _rule_by_value
from test_local_import_polish_c14g_adopt import _rule
from test_local_import_polish_c14j_adopt import _decisions_on, _edit_column
from test_local_import_polish_c14l_adopt import OTHER, _imp, _meta, _sheets, _state, _tid, _value_now
from test_local_import_polish_c14m_adopt import UNPLACEABLE, _mini, _without_recorded_shown

COLLEAGUE = "Colleague Synthetic Scientist"
NAME = "sample.material.name"


def _imp_by(grouped, x, capsys, by, *extra):
    capsys.readouterr()
    code = cli.main(["bundle", "template", "import", str(grouped), str(x), "--by", by, "--json", "--apply", *extra])
    out = capsys.readouterr()
    assert code == 0, out.err
    return json.loads(out.out)


def _offered(reason):
    """The ``decide`` command a reason offers, as argv for ``cli.main`` (``<bundle_dir>`` and the name left)."""
    text = reason.split("record this value directly: ", 1)[1]
    argv = shlex.split(text)
    assert argv[:3] == ["isaac", "bundle", "decide"], text
    return argv[1:]


def _run(argv, bdir, capsys):
    capsys.readouterr()
    code = cli.main([str(bdir) if a == "<bundle_dir>" else WHO if a == "<your name>" else a for a in argv])
    return code, capsys.readouterr().err


def _name_targets(bdir):
    """Each File List run's Sample Name target (run-001 … run-008: their sheet's rows)."""
    b = M.load(bdir)
    out = {}
    for o in [*b["candidates"], *b["missing_values"]]:
        if o["target_field_path"] == NAME and o["run_id"] in RUNS:
            out[o["run_id"]] = o.get("candidate_id") or o["value_id"]
    assert set(out) == set(RUNS), out
    return out


def _name_now(bdir, tid):
    d = [x for x in M.load(bdir)["scientist_decisions"] if x["target"]["id"] == tid]
    return d[-1]["value"] if d else None


# --- MED-1 ----------------------------------------------------------------------------------------------------


def _copies(grouped, tmp_path, capsys):
    """12 recorded; W adopted and copied before anything is imported; he rules 2 on W, his colleague 12 on the copy."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)  # 12
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "W.xlsx", capsys)
    shutil.copy(tmp_path / "W.xlsx", tmp_path / "Wcopy.xlsx")
    _rule(tmp_path / "W.xlsx", tmp_path / "Wa.xlsx", {p["id"]: 2})
    _rule(tmp_path / "Wcopy.xlsx", tmp_path / "Wb.xlsx", {p["id"]: 12})
    assert _meta(tmp_path / "Wa.xlsx")["adopt_id"] == _meta(tmp_path / "Wb.xlsx")["adopt_id"]
    return tid


def test_copies_of_one_workbook_never_flip_flop_with_supersede(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: each import with --supersede added a decision, flipping 2, 12, 2, 12 … forever."""
    tid = _copies(grouped, tmp_path, capsys)
    rep = _imp_by(grouped, tmp_path / "Wa.xlsx", capsys, WHO, "--supersede")
    assert tid in {d["target"]["id"] for d in rep["decisions"]} and _value_now(grouped, tid) == 2
    his = _decisions_on(grouped, tid)[-1]["decision_id"]
    values = []
    for cycle in range(3):
        rep = _imp_by(grouped, tmp_path / "Wb.xlsx", capsys, COLLEAGUE, "--supersede")
        assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"], cycle
        [stale] = rep["stale_rulings"]
        assert stale["target"]["id"] == tid and stale["value"] == 12 and stale["decision_id"] == his
        assert stale["reason"] == (
            f"{WHO}'s ruling on this row (2099-01-01), from another copy of this workbook, is what is recorded now; this "
            "ruling was not made against it, so nothing is recorded for it, even with --supersede, and the value "
            "recorded now is kept. Adopt again and rule against what is recorded now, or record this value directly: "
            f"isaac bundle decide <bundle_dir> --target {tid} --decision confirm --by \"<your name>\"")
        values.append(_value_now(grouped, tid))
        rep = _imp_by(grouped, tmp_path / "Wa.xlsx", capsys, WHO, "--supersede")
        assert rep["recorded"] == 0 and not rep["stale_rulings"], cycle
        values.append(_value_now(grouped, tid))
    assert values == [2] * 6 and len(_decisions_on(grouped, tid)) == 2


def test_the_same_scientist_correcting_their_ruling_on_a_copy_still_supersedes(grouped, tmp_path, capsys, ticking):
    tid = _copies(grouped, tmp_path, capsys)
    _imp_by(grouped, tmp_path / "Wa.xlsx", capsys, WHO, "--supersede")
    rep = _imp_by(grouped, tmp_path / "Wb.xlsx", capsys, WHO, "--supersede")  # his own copy, his own correction
    assert rep["recorded"] == 1 and not rep["stale_rulings"] and _value_now(grouped, tid) == 12


def test_a_ruling_by_another_person_on_another_adoption_names_them(grouped, tmp_path, capsys, ticking):
    """Two adoptions of one sheet (two ids): the colleague's ruling recorded now is theirs, never "your earlier"."""
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    pa, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    pb, _ = _state(grouped, s, tmp_path / "B.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {pa["id"]: 2})
    _rule(tmp_path / "B.xlsx", tmp_path / "Br.xlsx", {pb["id"]: 12})
    _imp_by(grouped, tmp_path / "Ar.xlsx", capsys, COLLEAGUE, "--supersede")
    theirs = _decisions_on(grouped, tid)[-1]["decision_id"]
    [stale] = _imp_by(grouped, tmp_path / "Br.xlsx", capsys, WHO, "--supersede")["stale_rulings"]
    assert stale["decision_id"] == theirs  # c15b L3: the reason names the day, never the id
    assert stale["reason"].startswith(f"{COLLEAGUE}'s ruling on this row (2099-01-01) is what is recorded now; this "
                                      "ruling, on another adoption of the same sheet, was not made against it, so ")
    assert _value_now(grouped, tid) == 2


# --- MED-2 ----------------------------------------------------------------------------------------------------


def _two_sheets_differing_on_sample(grouped, tmp_path, capsys):
    s1, s2 = _sheets(grouped, tmp_path, 2)
    _edit_column(s2, "Sample ", "ZZ synthetic catalyst", "ZZ other catalyst")
    _adopt_json(grouped, s1, tmp_path / "A.xlsx", capsys)
    _adopt_json(grouped, s2, tmp_path / "B.xlsx", capsys)


def test_adopted_file_list_cells_of_two_sheets_never_flip_flop_with_supersede(grouped, tmp_path, capsys, ticking):
    """The reviewer's probe: both adopted with nothing recorded; A, B, A, B … each with --supersede recorded every
    Sample Name again, forever."""
    _two_sheets_differing_on_sample(grouped, tmp_path, capsys)
    names = _name_targets(grouped)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys, "--supersede")
    assert {d["target"]["id"] for d in rep["decisions"] if d["header"] == "Sample Name"} == set(names.values())
    first = {tid: _decisions_on(grouped, tid)[-1]["decision_id"] for tid in names.values()}
    n = len(M.load(grouped)["scientist_decisions"])
    for cycle in range(3):
        rep = _imp(grouped, tmp_path / "B.xlsx", capsys, "--supersede")
        assert rep["recorded"] == 0 and not rep["clashes"], cycle
        stale = {x["target"]["id"]: x for x in rep["stale_rulings"]}
        assert set(stale) == set(names.values()), cycle
        tid = names["run-001"]
        assert stale[tid]["decision_id"] == first[tid]
        assert stale[tid]["reason"] == (
            f"this cell was adopted with nothing recorded here, before {WHO} recorded the value now (2099-01-01), so "
            "it never saw it: nothing is recorded for it, even with --supersede, and the value recorded now is kept. Adopt "
            "again, then import with --supersede, or record this value directly: "
            f"isaac bundle decide <bundle_dir> --target {tid} --decision correct --value='ZZ other catalyst' "
            "--by \"<your name>\"")
        rep = _imp(grouped, tmp_path / "A.xlsx", capsys, "--supersede")
        assert rep["recorded"] == 0 and not rep["stale_rulings"], cycle
    assert len(M.load(grouped)["scientist_decisions"]) == n
    assert {_name_now(grouped, tid) for tid in names.values()} == {"ZZ synthetic catalyst"}
    rep = _imp(grouped, tmp_path / "B.xlsx", capsys)  # without --supersede: it says --supersede will not help
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == names["run-001"]]
    assert clash["reason"].startswith("an earlier scientist decision gives a different value (recorded now: 'ZZ synthetic "
                                      f"catalyst' by {WHO} (2099-01-01), from another adoption); skipped, and --supersede "
                                      "does not record it either: this cell was not made against the value recorded now. "
                                      "Adopt again, then import with --supersede")


def test_adopt_keeps_the_decisions_each_adopted_cell_read(grouped, tmp_path, capsys, ticking):
    names = _name_targets(grouped)
    M.decide(grouped, target_ids=[names["run-001"]], decision="correct", value="ZZ old name", by=OTHER, orcid=None)
    [did] = [d["decision_id"] for d in _decisions_on(grouped, names["run-001"])]
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    adopted = T._marker(openpyxl.load_workbook(tmp_path / "A.xlsx"))["adopted"]
    governing = {c: T._marker_governing(e, T.ADOPTED_GOVERNING) for c, e in adopted.items()}
    rows = {rid: f"'File List'!{T._letter([c.header for c in T.FILE_COLUMNS].index('Sample Name') + 1)}"
                 f"{_isaac_row(tmp_path / 'A.xlsx', rid)}" for rid in ("run-001", "run-002")}
    assert governing[rows["run-001"]] == [did] and governing[rows["run-002"]] == []


def _isaac_row(xlsx, run_id):
    for values in openpyxl.load_workbook(xlsx)["_isaac"].iter_rows(values_only=True):
        if values[0] == "File List" and values[2] == run_id:
            return int(values[1])
    raise AssertionError(run_id)


def test_a_sheet_value_against_a_value_the_workbook_saw_still_supersedes(grouped, tmp_path, capsys, ticking):
    names = _name_targets(grouped)
    tid = names["run-001"]
    M.decide(grouped, target_ids=[tid], decision="correct", value="ZZ old name", by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys)  # without --supersede: the ordinary advice (c14n LOW-6)
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tid]
    assert clash["reason"].startswith(f"an earlier scientist decision gives a different value (recorded now: 'ZZ old name' "
                                      f"by {OTHER} (2099-01-01), from a decide); skipped (pass --supersede "
                                      "to record this one), or record this value directly: ")
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys, "--supersede")
    assert tid in {d["target"]["id"] for d in rep["decisions"]} and not rep["stale_rulings"]
    assert _name_now(grouped, tid) == "ZZ synthetic catalyst"
    assert T._note_adopt_id(_decisions_on(grouped, tid)[-1]) == _meta(tmp_path / "A.xlsx")["adopt_id"]


def test_a_value_someone_recorded_since_the_adopt_is_never_superseded_by_an_adopted_cell(grouped, tmp_path, capsys,
                                                                                         ticking):
    names = _name_targets(grouped)
    tid = names["run-001"]
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    M.decide(grouped, target_ids=[tid], decision="correct", value="ZZ later name", by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "A.xlsx", capsys, "--supersede")
    assert [x["target"]["id"] for x in rep["stale_rulings"]] == [tid]
    assert {d["target"]["id"] for d in rep["decisions"] if d["header"] == "Sample Name"} == set(names.values()) - {tid}
    assert _name_now(grouped, tid) == "ZZ later name"


def test_their_own_adopted_cell_edited_and_imported_again_supersedes(grouped, tmp_path, capsys, ticking):
    names = _name_targets(grouped)
    tid = names["run-001"]
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    _imp(grouped, tmp_path / "A.xlsx", capsys)
    wb = openpyxl.load_workbook(tmp_path / "A.xlsx")
    ref = f"{T._letter([c.header for c in T.FILE_COLUMNS].index('Sample Name') + 1)}{_isaac_row(tmp_path / 'A.xlsx', 'run-001')}"
    wb["File List"][ref] = "ZZ corrected name"
    wb.save(tmp_path / "A2.xlsx")
    rep = _imp_by(grouped, tmp_path / "A2.xlsx", capsys, COLLEAGUE, "--supersede")  # not theirs: never over it
    assert [x["target"]["id"] for x in rep["stale_rulings"]] == [tid] and _name_now(grouped, tid) == "ZZ synthetic catalyst"
    rep = _imp(grouped, tmp_path / "A2.xlsx", capsys, "--supersede")
    assert rep["recorded"] == 1 and not rep["stale_rulings"] and _name_now(grouped, tid) == "ZZ corrected name"


def test_an_adopted_cell_of_a_workbook_without_the_governing_ids_is_placed_by_the_log(grouped, tmp_path, capsys,
                                                                                    ticking):
    """A c14m workbook (``decisions_at_adopt`` and the fingerprint, but no ``[adopted]`` governing ids)."""
    names = _name_targets(grouped)
    before, after = names["run-001"], names["run-002"]
    M.decide(grouped, target_ids=[before], decision="correct", value="ZZ old name", by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    wb = openpyxl.load_workbook(tmp_path / "A.xlsx")
    wm = wb["_isaac"]
    [(r0, c0)] = [(c.row, c.column) for row in wm.iter_rows() for c in row if c.value == T.ADOPTED_GOVERNING]
    for r in range(r0, wm.max_row + 1):  # the [adopted] section's column only
        if r > r0 and (wm.cell(r, 1).value is None or str(wm.cell(r, 1).value).startswith("[")):
            break
        wm.cell(r, c0).value = None
    wb.save(tmp_path / "old.xlsx")
    assert not any(T.ADOPTED_GOVERNING in e for e in T._marker(openpyxl.load_workbook(tmp_path / "old.xlsx"))["adopted"].values())
    M.decide(grouped, target_ids=[after], decision="correct", value="ZZ later name", by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "old.xlsx", capsys, "--supersede")
    assert [x["target"]["id"] for x in rep["stale_rulings"]] == [after]
    assert _name_now(grouped, before) == "ZZ synthetic catalyst" and _name_now(grouped, after) == "ZZ later name"


def test_an_unplaceable_workbook_never_records_an_adopted_cell_over_another_value(grouped, tmp_path, capsys, ticking):
    names = _name_targets(grouped)
    tid = names["run-001"]
    M.decide(grouped, target_ids=[tid], decision="correct", value="ZZ old name", by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    _adopt_json(grouped, s, tmp_path / "A.xlsx", capsys)
    _set_meta(tmp_path / "A.xlsx", tmp_path / "x.xlsx", "decisions_fingerprint", "0" * 64)
    rep = _imp(grouped, tmp_path / "x.xlsx", capsys, "--supersede")
    [stale] = [x for x in rep["stale_rulings"] if x["target"]["id"] == tid]
    assert stale["reason"].startswith(UNPLACEABLE) and _name_now(grouped, tid) == "ZZ old name"
    # a cell with nothing recorded on its target records as before
    assert names["run-002"] in {d["target"]["id"] for d in rep["decisions"]}


def test_a_plain_cell_of_a_template_never_adopted_still_supersedes(grouped, tmp_path, capsys, ticking):
    names = _name_targets(grouped)
    tid = names["run-001"]
    out = tmp_path / "t.xlsx"
    assert cli.main(["bundle", "template", "export", str(grouped), "--out", str(out)]) == 0
    marker = T._marker(openpyxl.load_workbook(out))
    assert not marker["adopted"] and "adopt_id" not in marker["meta"]
    wb = openpyxl.load_workbook(out)
    ref = f"{T._letter([c.header for c in T.FILE_COLUMNS].index('Sample Name') + 1)}{_isaac_row(out, 'run-001')}"
    wb["File List"][ref] = "ZZ typed name"
    wb.save(tmp_path / "filled.xlsx")
    M.decide(grouped, target_ids=[tid], decision="correct", value="ZZ later name", by=OTHER, orcid=None)  # since export
    rep = _imp(grouped, tmp_path / "filled.xlsx", capsys, "--supersede")
    assert rep["recorded"] == 1 and not rep["stale_rulings"] and _name_now(grouped, tid) == "ZZ typed name"
    note = _decisions_on(grouped, tid)[-1]["note"]
    assert note.endswith(f"'File List'!{ref}") and T._note_adopt_id({"note": note}) is None


# --- LOW-1 and LOW-6 ------------------------------------------------------------------------------------------


def test_the_offered_command_runs_with_a_negative_number(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: -0.5})
    _without_recorded_shown(tmp_path / "Ar.xlsx")  # c15b H2: else the row's ruling records without --supersede
    [clash] = [c for c in _imp(grouped, tmp_path / "Ar.xlsx", capsys)["clashes"] if c["target"]["id"] == tid]
    assert clash["reason"].endswith("(pass --supersede to record this one), or record this value directly: isaac bundle "
                                    f"decide <bundle_dir> --target {tid} --decision correct --value=-0.5 --json --by "
                                    "\"<your name>\"")
    code, err = _run(_offered(clash["reason"]), grouped, capsys)
    assert code == 0, err
    assert _value_now(grouped, tid) == -0.5


def test_the_offered_command_runs_with_text_that_starts_with_a_dash(grouped, tmp_path, capsys, ticking):
    tid = _name_targets(grouped)["run-001"]
    for value in ("-x", "-ZZ name with 'quotes'"):
        cmd = T.decide_command(tid, "correct", value)
        assert f" --value={shlex.quote(value)} --by " in cmd
        code, err = _run(shlex.split(cmd)[1:], grouped, capsys)
        assert code == 0, err
        assert _name_now(grouped, tid) == value


# --- LOW-2 ----------------------------------------------------------------------------------------------------


def test_a_per_run_answer_slot_is_offered_as_the_question_for_that_run(plain, tmp_path, capsys):
    """A Technique ruling on every run: some runs have a Technique target of their own, the rest get a per-run answer
    slot this import adds. Another scientist records one run's own target after the adopt, so the ruling cell is
    stale for it and (all or nothing) for every slot too; those slots are dropped, so the command names the question."""
    out = tmp_path / "adopted.xlsx"
    _adopt_json(plain, _sheet(plain, tmp_path / THEIRS, beamline="BL15-2", technique="XANES"), out, capsys)
    ruled = _rule_by_value(out, tmp_path / "ruled.xlsx", {("Technique", "XANES"): {"H": "HERFD-XAS"}})
    slotted = _without_own_target(plain, TECH, RUNS)
    b = M.load(plain)
    own = next(c for c in [*b["candidates"], *b["missing_values"]] if c["target_field_path"] == TECH and c["run_id"] in RUNS)
    M.decide(plain, target_ids=[own.get("candidate_id") or own["value_id"]], decision="correct", value="XAS", by=OTHER,
             orcid=None)
    n = len(M.load(plain)["missing_values"])
    qid = next(q["question_id"] for q in Q.consolidate(M.load(plain), include_answered=True)["questions"]
               if q.get("target_field_path") == TECH and list(q["per_scope_targets"]) == ["experiment"])
    code, rep, err = _import(plain, ruled, capsys, "--apply", "--supersede")
    assert code == 0, err
    assert not [d for d in rep["decisions"] if d["target_field_path"] == TECH]
    assert len(M.load(plain)["missing_values"]) == n  # the slots were dropped
    by_run = {x["run_id"]: x for x in rep["stale_rulings"] if x["header"] == "Technique"}
    assert slotted and set(slotted) <= set(by_run)
    for rid in slotted:
        assert by_run[rid]["reason"].endswith(
            f"isaac bundle decide <bundle_dir> --question {qid} --only run:{rid} --decision correct --value=HERFD-XAS "
            "--by \"<your name>\""), rid
    rid = slotted[0]
    code, err = _run(_offered(by_run[rid]["reason"]), plain, capsys)
    assert code == 0, err
    b = M.load(plain)
    latest = _latest(plain)
    got = {m["run_id"]: latest[("missing_value", m["value_id"])]["value"] for m in b["missing_values"]
           if m["target_field_path"] == TECH and m["run_id"] in slotted and ("missing_value", m["value_id"]) in latest}
    assert got == {rid: "HERFD-XAS"}  # that run alone, on a slot of its own


def test_only_a_run_refuses_a_run_in_no_live_group(plain, capsys):
    qid = next(q["question_id"] for q in Q.consolidate(M.load(plain))["questions"]
               if q.get("target_field_path") == TECH and list(q["per_scope_targets"]) == ["experiment"])
    code, _, err = _decide(plain, capsys, "--question", qid, "--only", "run:run-nope", "--decision", "correct", "--value", "XAS")
    assert code == 6 and "No run 'run-nope' in a live record group" in err
    code, _, err = _decide(plain, capsys, "--question", qid, "--only", "run:run-001", "--decision", "defer")
    assert code == 2 and "records an answer for that run only" in err
    assert not M.load(plain).get("scientist_decisions")


def _decide(bdir, capsys, *args):
    capsys.readouterr()
    code = cli.main(["bundle", "decide", str(bdir), *args, "--by", WHO])
    out = capsys.readouterr()
    return code, out.out, out.err


# --- LOW-3, LOW-4 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("against, adopted_at, expected", [
    # c15b L3: named by who and when, never by decision id
    (["d-00001"], 1, "ruled on a workbook adopted before someone recorded the value now (2099-01-01), and a "
                     "different value was recorded since (by someone unnamed, 2099-01-01); nothing is recorded for this "
                     "ruling: the value is already 12; adopt again to settle this row"),
    ([T.GOVERNING_DAMAGED], 1, "ruled on a workbook whose `_isaac` governing_decisions value is damaged, so it is never "
                               "tied; nothing is recorded for this ruling: the value is already 12; adopt again to "
                               "settle this row"),
    ([T.GOVERNING_UNPLACEABLE], None, UNPLACEABLE + "; nothing is recorded for this ruling: the value is already 12; "
                                      "adopt again to settle this row"),
])
def test_a_stale_ruling_that_keeps_the_value_offers_no_command(against, adopted_at, expected):
    chains = _mini([{"decision": "confirm"}, {"decision": "correct", "value": 7}, {"decision": "confirm"}])
    run = chains(2)
    got = T._stale_reason({"value": 12, "ruled_against": against}, [chains.log[p] for p in run], chains, run, None,
                          adopted_at=adopted_at, target="c1", decision="confirm")
    assert got == expected and "record this value directly" not in got


def test_a_whole_beamtime_ruling_names_the_targets_already_holding_its_value(grouped, tmp_path, capsys, ticking):
    """BL11 on every run before the adopt, BL12 on one since: the ruling BL11 is stale there, so (all or nothing) it
    ties none; the others already hold BL11 and are offered no command."""
    [s] = _sheets(grouped, tmp_path, 1)
    bl = _d(_adopt_json(grouped, s, tmp_path / "probe.xlsx", capsys), "Beamline/Instrument")
    tids = [m["value_id"] for m in M.load(grouped)["missing_values"] if m.get("target_field_path") == bl["path"]]
    M.decide(grouped, target_ids=tids, decision="correct", value="BL11", by=OTHER, orcid=None)
    bl = _d(_adopt_json(grouped, s, tmp_path / "A.xlsx", capsys), "Beamline/Instrument")
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {bl["id"]: "BL11"})
    M.decide(grouped, target_ids=tids[:1], decision="correct", value="BL12", by=OTHER, orcid=None)
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")
    stale = {x["target"]["id"]: x for x in rep["stale_rulings"]}
    assert set(stale) == set(tids) and not rep["rulings_tied_to_sheet"]
    assert "record this value directly: " in stale[tids[0]]["reason"]
    for tid in tids[1:]:
        # c15b M4: run-001 still holds BL12, so adopting again alone would not settle the row
        assert stale[tid]["reason"].endswith("nothing is recorded for this one either, and the value is already "
                                             "'BL11'; another target of this row still holds a different value, so "
                                             "adopting again would ask it again: adopt again and rule the row, or record "
                                             "the value for all of them with the cell's one command"), tid


OWN_NOTE = ("template B.xlsx 'Disagreements'!H2 (your ruling on disagreement D1: SYN_sheet.xlsx 'File List'!H8 = 2)"
            + T._adopt_note("ab" * 16))
TAIL = (" nothing is recorded for it, even with --supersede, and the value recorded now is kept. Adopt again and rule "
        "against what is recorded now, or record this value directly: isaac bundle decide <bundle_dir> --target c1 "
        "--decision correct --value=2 --json --by \"<your name>\"")


@pytest.mark.parametrize("note, adopt_id, by, expected", [
    # LOW-4: no readable adopt id on this workbook: which adoption the ruling recorded now came from is not known
    # c15b L3: named by who and when, never by decision id
    (OWN_NOTE, None, WHO, f"a ruling on this row (by {WHO}, 2099-01-01), from this sheet, is what is recorded now; this "
                          "ruling was not made against it, so" + TAIL),
    (OWN_NOTE.split(" (adopt id ")[0], None, WHO, f"a ruling on this row (by {WHO}, 2099-01-01), from this sheet, is what "
                                                  "is recorded now; this ruling was not made against it, so" + TAIL),
    # another adoption (another id), by them or by someone else
    (OWN_NOTE, "cd" * 16, WHO, "your earlier ruling on this row (2099-01-01) is what is recorded now; this ruling, on "
                               "another adoption of the same sheet, was not made against it, so" + TAIL),
    (OWN_NOTE, "cd" * 16, COLLEAGUE, f"{WHO}'s ruling on this row (2099-01-01) is what is recorded now; this ruling, on "
                                     "another adoption of the same sheet, was not made against it, so" + TAIL),
    # MED-1: a copy of this very workbook (the same id), imported by someone else
    (OWN_NOTE, "ab" * 16, COLLEAGUE, f"{WHO}'s ruling on this row (2099-01-01), from another copy of this workbook, is what "
                                     "is recorded now; this ruling was not made against it, so" + TAIL),
])
def test_the_ruling_recorded_now_is_named_honestly(note, adopt_id, by, expected):
    chains = _mini([{"decision": "confirm", "note": note, "decided_by": {"name": WHO}}])
    run = chains(0)
    cell = {"value": 2, "ruled_against": [], "ruling": ("SYN_sheet.xlsx", "'File List'!H8", 2)}
    got = T._stale_reason(cell, [chains.log[p] for p in run], chains, run, None, adopted_at=0, keeps=False, target="c1",
                          decision="correct", adopt_id=adopt_id, by=by)
    assert got == expected


def test_a_copy_by_the_same_person_is_made_against_the_value_now():
    log = [{"decision_id": "d-00001", "note": "x" + T._adopt_note("ab" * 16), "decided_by": {"name": WHO}}]
    cell = {"ruled_against": []}
    common = dict(adopted_at=0, places={id(log[0]): 0}, keeps=False, adopt_id="ab" * 16)
    assert T._rules_against_now(cell, log[0], None, log, log, by=WHO, **common)
    assert not T._rules_against_now(cell, log[0], None, log, log, by=COLLEAGUE, **common)


# --- LOW-5 ----------------------------------------------------------------------------------------------------


def _set_meta(xlsx, out, key, value):
    wb = openpyxl.load_workbook(xlsx)
    [row] = [row for row in wb["_isaac"].iter_rows() if row[0].value == key]
    row[1].value = value
    wb.save(out)


def test_a_blank_fingerprint_row_leaves_the_workbook_unplaceable(grouped, tmp_path, capsys, ticking):
    tid = _tid(grouped)
    M.decide(grouped, target_ids=[tid], decision="confirm", value=None, by=OTHER, orcid=None)
    [s] = _sheets(grouped, tmp_path, 1)
    p, _ = _state(grouped, s, tmp_path / "A.xlsx", capsys)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {p["id"]: 2})
    _set_meta(tmp_path / "Ar.xlsx", tmp_path / "blank.xlsx", "decisions_fingerprint", None)
    meta = _meta(tmp_path / "blank.xlsx")
    assert "decisions_fingerprint" in meta and meta["decisions_fingerprint"] is None
    rep = _imp(grouped, tmp_path / "blank.xlsx", capsys, "--supersede")
    [stale] = rep["stale_rulings"]
    assert stale["reason"].startswith(UNPLACEABLE) and _value_now(grouped, tid) == 12
    log = M.load(grouped)["scientist_decisions"]
    assert T._placed({"decisions_at_adopt": 1, "decisions_fingerprint": ""}, log) == (None, True)
    assert T._placed({"decisions_at_adopt": 1, "decisions_fingerprint": None}, log) == (1, False)  # no row: as before
    rep = _imp(grouped, tmp_path / "Ar.xlsx", capsys, "--supersede")  # the same workbook with its fingerprint
    assert rep["recorded"] == 1 and _value_now(grouped, tid) == 2
