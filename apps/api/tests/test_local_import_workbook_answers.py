"""``isaac bundle answers import``: a scientist's filled-in QUESTION WORKBOOK read back into a bundle.

Synthetic only: the bundle is the multi-operator fixture imported under a fake folder name, and the workbook is
built here, with every tab kind the question workbook has (start page, read-me, new questions N*, Athena merges,
rules R*, Claude's proposals with value and rule rows, blocking and optional tabs with collapsed G rows and their
per-record twins, file-name numbers, merge or keep apart, element and edge, clock time zone, Athena versions,
No answer needed) plus an unknown tab. No real workbook, bundle, folder or name is used.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import openpyxl
import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import workbook_answers as W

from tests_support_records import SEMANTICS

FOLDER = "SYN_BL00_2100-01_Synthetic"
OTHER = "SYN_BL99_2100-02_OtherBeamtime"
WHO = "SYN Scientist"

QHEAD = ["Ref", "Beamline", "Beamtime", "Folder", "Blocks export?", "Topic", "Applies to", "Record (run names)",
         "Question", "Suggested answer (NOT confirmed)", "Suggested by", "File (inside the beamtime folder)",
         "Where in the file", "Text in the file", "Other readings or alternatives", "Allowed answers", "YOUR ANSWER",
         "Your notes", "ISAAC question ID"]
QHEAD_B = [*QHEAD, "Covered by collapsed row"]
PHEAD = ["Ref", "Kind", "Beamline", "Beamtime", "Folder", "From tab", "Original ref", "Topic", "Record (run names)",
         "Question", "Claude proposes", "What 'ok' records", "Allowed answers", "YOUR ANSWER", "Your notes",
         "ISAAC question ID", "Proposal ID"]
FHEAD = ["Ref", "Applies to", "Topic", "Who should answer", "Question", "Why it matters / what it settles",
         "What ISAAC does now", "YOUR ANSWER", "Your notes"]
AHEAD = ["Ref", "Beamline", "Beamtime", "Folder", "Athena project file(s)", "Athena group label",
         "Near name (hint only, never matched)", "Other record groups in the same project", "YOUR ANSWER", "Your notes",
         "Athena group (as stored)"]
NHEAD = ["Ref", "Beamline", "Beamtime", "Folder", "From tab", "Original ref", "Topic", "Record (run names)", "Kind",
         "Rule", "Why no answer is needed", "ISAAC question ID"]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp("wa")
    src = root / FOLDER
    shutil.copytree(SEMANTICS, src)
    out = root / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    M.group(out)
    return out


@pytest.fixture()
def bdir(base, tmp_path):
    d = tmp_path / "work" / "bundle"
    shutil.copytree(base, d)
    return d


def _qs(bdir):
    return Q.consolidate(M.load(bdir), include_answered=True)["questions"]


def _q(bdir, kind, path=None, *, scope=None, n=0):
    hits = [q for q in _qs(bdir) if q["kind"] == kind and (path is None or q.get("target_field_path") == path)
            and (scope is None or q["scope"].startswith(scope))]
    return hits[n]


def _digest(d):
    return hashlib.sha256((d / "bundle.json").read_bytes()).hexdigest()


def _tab(wb, title, header, rows, *, a1="SYN title line"):
    ws = wb.create_sheet(title)
    ws["A1"] = a1
    if header is None:
        for i, r in enumerate(rows, start=2):
            ws.cell(i, 1, r)
        return ws
    for c, h in enumerate(header, start=1):
        ws.cell(2, c, h)
    for i, r in enumerate(rows, start=3):
        for c, h in enumerate(header, start=1):
            if h in r:
                ws.cell(i, c, r[h])
    return ws


def _workbook(bdir, path, answers=None, *, extra=None, rename=None):
    """A synthetic question workbook for this bundle: every tab kind. ``answers``: {ref: (answer, notes)}."""
    answers = answers or {}
    sf = [q for q in _qs(bdir) if q["kind"] == "missing_value" and q.get("target_field_path") == "sample.sample_form"]
    pot = [q for q in _qs(bdir) if q["kind"] == "confirm_value"
           and q.get("target_field_path") == "context.electrochemistry.potential_setpoint_V"]
    group_q = _q(bdir, "missing_value", "attribution.produced_by.group")
    group_hint = W._offered(group_q, "attribution.produced_by.group")[0]  # the hint ISAAC shows (the folder's name)
    env_q = _q(bdir, "missing_value", "context.environment")
    dom_q = _q(bdir, "missing_value", "system.domain")
    opt_q = next(q for q in _qs(bdir) if q["kind"] == "optional_values" and "system.facility.beamline" in (q.get("fields") or {}))
    abs_q = _q(bdir, "confirm_absorber")
    live = [g["group_id"] for g in M.load(bdir)["record_groups"] if g.get("status") in B.LIVE_GROUP_STATUSES]
    stem = M.load(bdir)["runs"][0]["stem"]

    def a(ref, row):
        if ref in answers:
            ans, notes = answers[ref]
            row = {**row, "YOUR ANSWER": ans, **({"Your notes": notes} if notes else {})}
        return {"Ref": ref, **row}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    t = rename or {}
    _tab(wb, t.get("start", "Start here"), None, ["Start here: SYN asks", "1. type in YOUR ANSWER"])
    _tab(wb, "Read Me", None, ["SYN read me"])
    _tab(wb, t.get("new", "0 New since 29 Oct"), FHEAD, [a("N1", {"Topic": "SYN limit", "Question": "SYN?"}),
                                                        a("N2", {"Topic": "SYN other", "Question": "SYN?"})])
    _tab(wb, "Athena merges", AHEAD, [
        a("AM01", {"Folder": FOLDER, "Athena project file(s)": "SYN_a.prj; SYN_b.prj", "Athena group label": "SYN merge 1",
                   "Near name (hint only, never matched)": f"syn near ({live[0]})", "Athena group (as stored)": "syn_merge_1"}),
        a("AM02", {"Folder": FOLDER, "Athena project file(s)": "SYN_a.prj", "Athena group label": "SYN merge 2",
                   "Near name (hint only, never matched)": "none"}),
        a("AM03", {"Folder": FOLDER, "Athena project file(s)": "SYN_a.prj", "Athena group label": "SYN merge 3",
                   "Near name (hint only, never matched)": "none"}),
        a("AM04", {"Folder": FOLDER, "Athena project file(s)": "SYN_c.prj", "Athena group label": "SYN merge 4",
                   "Near name (hint only, never matched)": f"syn near ({live[1]})"}),
        a("AM05", {"Folder": OTHER, "Athena project file(s)": "SYN_z.prj", "Athena group label": "SYN other"}),
    ])
    _tab(wb, t.get("rules", "1 Rules and protocol"), FHEAD, [a("R1", {"Topic": "SYN axis", "Question": "SYN?"}),
                                                            a("R2", {"Topic": "SYN spot", "Question": "SYN?"})])
    _tab(wb, "Claude's proposals (say ok)", PHEAD, [
        a("CR1", {"Kind": "Rule", "From tab": "rule", "Topic": "SYN rule", "Claude proposes": "Accept this rule",
                  "Proposal ID": "CR1"}),
        a("P-0001", {"Kind": "Value", "Folder": FOLDER, "Topic": "Domain (experimental or computational)",
                     "Claude proposes": "experimental", "What 'ok' records": "sets system.domain = 'experimental'",
                     "ISAAC question ID": dom_q["question_id"], "Proposal ID": "P-syn0000001"}),
    ])
    _tab(wb, t.get("missing", "2 Missing (blocks export)"), QHEAD, [
        a("2-0001", {"Folder": FOLDER, "Topic": "Research group that produced the data",
                     "Suggested answer (NOT confirmed)": group_hint, "ISAAC question ID": group_q["question_id"]}),
        a("2-0002", {"Folder": FOLDER, "Topic": "Measurement environment (operando / in situ / ex situ)",
                     "ISAAC question ID": env_q["question_id"]}),
        a("2-0003", {"Folder": FOLDER, "Topic": "Sample form (powder, film, ...)", "ISAAC question ID": sf[0]["question_id"]}),
        a("2-G001", {"Folder": FOLDER, "Topic": "Sample form (powder, film, ...)", "ISAAC question ID": "G-syn0000001"}),
        a("2-0009", {"Folder": FOLDER, "Topic": "Sample form (powder, film, ...)", "ISAAC question ID": "Q-0000000000"}),
        a("2-0010", {"Folder": OTHER, "Topic": "Sample form (powder, film, ...)", "ISAAC question ID": "Q-1111111111"}),
    ])
    _tab(wb, "2b Missing per record", QHEAD_B, [
        a("2-0004", {"Folder": FOLDER, "Topic": "Sample form (powder, film, ...)", "ISAAC question ID": sf[1]["question_id"],
                     "Covered by collapsed row": "2-G001"}),
        a("2-0005", {"Folder": FOLDER, "Topic": "Sample form (powder, film, ...)", "ISAAC question ID": sf[2]["question_id"],
                     "Covered by collapsed row": "2-G001"}),
    ])
    _tab(wb, "5 File-name numbers", QHEAD, [a("5-0001", {"Folder": FOLDER, "ISAAC question ID": "Q-2222222222"})])
    _tab(wb, "6 Merge or keep apart", QHEAD, [a("6-0001", {"Folder": FOLDER, "ISAAC question ID": "mc-0000000000000000"})])
    _tab(wb, "7 Element and edge", QHEAD, [a("7-0001", {"Folder": FOLDER, "Topic": "Absorbing element and edge",
                                                        "Suggested answer (NOT confirmed)": "Zz L3",
                                                        "ISAAC question ID": abs_q["question_id"]})])
    _tab(wb, "8 Clock time zone", QHEAD, [a("8-0001", {"Folder": OTHER, "ISAAC question ID": "Q-3333333333"})])
    _tab(wb, "9 Confirm (optional)", QHEAD, [
        a("9-G001", {"Folder": FOLDER, "Topic": "Applied potential (V)", "ISAAC question ID": "G-syn0000002",
                     "Allowed answers": "yes only (each record's own shown value)"})])
    _tab(wb, "9b Confirm (opt) per record", QHEAD_B, [
        a(f"9-000{i}", {"Folder": FOLDER, "Topic": "Applied potential (V)", "Suggested answer (NOT confirmed)": q_val,
                        "ISAAC question ID": q["question_id"], "Covered by collapsed row": "9-G001"})
        for i, (q, q_val) in enumerate(((pot[0], 0.1), (pot[1], 0.2)), start=1)
    ] + [a("9-0003", {"Folder": FOLDER, "Topic": "Applied potential (V)", "Suggested answer (NOT confirmed)": 0.4,
                      "ISAAC question ID": pot[2]["question_id"]}),
         a("9-0004", {"Folder": FOLDER, "Topic": "Applied potential (V)", "Suggested answer (NOT confirmed)": 0.8,
                      "ISAAC question ID": pot[3]["question_id"]})])
    _tab(wb, t.get("optional", "11 Optional fields"), QHEAD, [
        a("11-0001", {"Folder": FOLDER, "Topic": "Beamline", "ISAAC question ID": opt_q["question_id"]}),
        a("11-0002", {"Folder": FOLDER, "Topic": "SYN topic nobody knows", "ISAAC question ID": opt_q["question_id"]}),
    ])
    _tab(wb, "12 Athena versions", QHEAD, [a("12-0001", {"Folder": FOLDER, "ISAAC question ID": live[2]})])
    _tab(wb, "No answer needed", NHEAD, [{"Ref": "N-0001", "Folder": FOLDER, "Kind": "Informational",
                                          "ISAAC question ID": pot[4]["question_id"]},
                                         {"Ref": "N-0002", "Folder": FOLDER, "ISAAC question ID": "Q-4444444444"}])
    for title, header, rows in extra or ():
        _tab(wb, title, header, rows)
    wb.save(path)
    return {"sf": sf, "pot": pot, "group": group_q, "group_hint": group_hint, "env": env_q, "dom": dom_q, "opt": opt_q, "abs": abs_q,
            "live": live, "stem": stem}


def _run(bdir, xlsx, capsys, *extra, by=WHO):
    capsys.readouterr()
    code = cli.main(["bundle", "answers", "import", str(bdir), str(xlsx), "--by", by, "--json", *extra])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if code == 0 else None), out.err


ANSWERS = {
    "2-0001": ("yes", None),                     # accepts the shown suggestion (an offered literal): correct
    "2-0002": ("in_situ", None),                 # a typed value on its list: correct
    "2-0003": ("SYN blob", None),                # an off-list word: a vocabulary request, as --as-said keeps it
    "2-G001": ("film", "same for all of them"),  # a collapsed row: one answer for its two per-record rows
    "2-0009": ("powder", None),                  # an id that no longer resolves
    "2-0010": ("powder", None),                  # another beamtime's row: counted, never read here
    "P-0001": ("OK", None),                      # Claude's proposal: what 'ok' records
    "CR1": ("ok", None),                         # a rule proposal: free text
    "N1": ("SYN first", None), "R2": ("SYN a repeat", None),
    "AM01": ("yes", None), "AM02": ("none", None), "AM03": ("SYN no such group", None), "AM04": ("no", None),
    "9-0003": ("yes", None),                     # confirm: the files' own value
    "9-0004": ("no", None),                      # a no is not a value
    "11-0001": ("SYN-BL1", None),                # one field of a several-field question, by its topic
    "11-0002": ("x", None),                      # a topic naming no known field
    "7-0001": ("yes", None),                     # 'Zz L3': no element, so nothing is guessed
    "6-0001": ("Keep apart", None), "12-0001": ("v01", None),
}


def test_unfilled_workbook_has_nothing_to_apply_and_resolves_every_id(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_questions.xlsx"
    _workbook(bdir, xlsx)
    before, files = _digest(bdir), sorted(p.name for p in bdir.iterdir())
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0
    assert rep["statement"].startswith("Nothing to apply")
    assert rep["decisions"] == [] and rep["not_applied"] == [] and rep["free_text"] == [] and rep["athena_merges"] == []
    kinds = {t["tab"]: t["kind"] for t in rep["tabs"]}
    assert kinds["Start here"] == kinds["Read Me"] == "info"
    assert kinds["0 New since 29 Oct"] == kinds["1 Rules and protocol"] == "free_text"
    assert kinds["Athena merges"] == "athena_merges" and kinds["No answer needed"] == "no_answer"
    assert kinds["2b Missing per record"] == kinds["Claude's proposals (say ok)"] == "questions"
    ids = rep["id_rows"]
    # Q- rows of this bundle: every tab, the No answer needed tab included; the other beamtime's are not looked up
    assert ids["not_resolving"] == 3 and ids["not_resolving_by_tab"] == {
        "2 Missing (blocks export)": 1, "5 File-name numbers": 1, "No answer needed": 1}
    assert ids["question_id_rows"] == ids["for_this_bundle"] + 2
    assert _digest(bdir) == before and sorted(p.name for p in bdir.iterdir()) == files  # not even a lock file
    capsys.readouterr()
    assert cli.main(["bundle", "answers", "import", str(bdir), str(xlsx), "--by", WHO]) == 0
    assert "Nothing to apply" in capsys.readouterr().out


def test_preview_maps_each_answer_to_its_exact_decide_and_writes_nothing(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_filled.xlsx"
    info = _workbook(bdir, xlsx, ANSWERS)
    before, files = _digest(bdir), sorted(p.name for p in bdir.iterdir())
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0 and rep["applied"] is False
    assert _digest(bdir) == before and sorted(p.name for p in bdir.iterdir()) == files
    by_ref = {}
    for p in rep["decisions"]:
        by_ref.setdefault(p.get("for_row") or p["ref"], []).append(p)
    # yes -> correct with the shown (offered) suggestion
    (p,) = by_ref["2-0001"]
    assert (p["question_id"], p["decision"], p["value"]) == (info["group"]["question_id"], "correct", info["group_hint"])
    assert p["cell"] == "Q3" and p["outcome"] == "would_record"
    assert p["command"].startswith(f"isaac bundle decide {bdir} --question {info['group']['question_id']} --decision correct")
    assert f"--by '{WHO}'" in p["command"] and "--note 'workbook SYN_filled.xlsx '\"'\"'2 Missing (blocks export)'\"'\"'!Q3'" in p["command"]
    # a typed value on its list
    (p,) = by_ref["2-0002"]
    assert (p["decision"], p["value"], p["as_said"], p["outcome"]) == ("correct", "in_situ", True, "would_record")
    # an off-list word: kept as a vocabulary request by --apply, as decide --as-said keeps it
    (p,) = by_ref["2-0003"]
    assert p["as_said"] and "--as-said" in p["command"] and p["outcome"] == "would_keep_vocabulary_request"
    # the collapsed row answers each per-record row it covers, citing the collapsed row's cell
    assert {p["question_id"] for p in by_ref["2-0004"] + by_ref["2-0005"]} == {info["sf"][1]["question_id"], info["sf"][2]["question_id"]}
    assert all(p["ref"] == "2-G001" and p["value"] == "film" and "collapsed row 2-G001" in p["note"]
               for p in by_ref["2-0004"] + by_ref["2-0005"])
    # Claude's proposal: 'ok' records what the row says it records
    (p,) = by_ref["P-0001"]
    assert (p["question_id"], p["decision"], p["value"]) == (info["dom"]["question_id"], "correct", "experimental")
    # confirm: the files' own value
    (p,) = by_ref["9-0003"]
    assert (p["decision"], p["value"]) == ("confirm", None) and "--value" not in p["command"]
    # one field of a several-field question, found by the row's topic
    (p,) = by_ref["11-0001"]
    assert (p["field"], p["value"]) == ("system.facility.beamline", "SYN-BL1") and "--field system.facility.beamline" in p["command"]
    assert set(by_ref) == {"2-0001", "2-0002", "2-0003", "2-0004", "2-0005", "P-0001", "9-0003", "11-0001"}

    problems = {p["ref"]: p for p in rep["not_applied"]}
    assert problems["2-0009"]["problem"] == "not_resolving" and "Q-0000000000" in problems["2-0009"]["reason"]
    assert problems["9-0004"]["problem"] == "declined"
    assert problems["11-0002"]["problem"] == "not_resolving" and "names no field" in problems["11-0002"]["reason"]
    assert problems["7-0001"]["problem"] == "needs_translation" and "element and an edge" in problems["7-0001"]["reason"]
    assert problems["6-0001"]["problem"] == "not_resolving" and "no merge candidate" in problems["6-0001"]["reason"]
    assert problems["12-0001"]["problem"] == "not_resolving" and "no Athena versions" in problems["12-0001"]["reason"]
    assert "2-0010" not in problems and rep["counts"]["answered_rows_other_beamtimes"] == 1

    # free text: reported with how to translate it, never applied
    assert {(f["ref"], f["kind"]) for f in rep["free_text"]} == {("N1", "new_question"), ("R2", "rule"), ("CR1", "rule_proposal")}
    assert all("Not applied" in f["how"] for f in rep["free_text"])
    # Athena merges: the params-file entries to use, never applied
    am = {a["ref"]: a for a in rep["athena_merges"]}
    assert am["AM01"]["params_entry"] == {"athena_match": {info["live"][0]: [
        {"project": "SYN_a.prj", "athena_group": "syn_merge_1"}, {"project": "SYN_b.prj", "athena_group": "syn_merge_1"}]}}
    assert am["AM02"]["params_entry"] == {"athena_ignore": [{"project": "SYN_a.prj", "athena_group": "SYN merge 2"}]}
    assert am["AM03"]["params_entry"] is None and "not one" in am["AM03"]["reading"]
    assert am["AM04"]["params_entry"] == {"athena_match_not": {info["live"][1]: [{"project": "SYN_c.prj", "athena_group": "SYN merge 4"}]}}
    assert set(am["AM03"]["params_entries_to_use"]) == {"athena_match", "athena_match_not", "athena_ignore"}
    # 'same for all' is reported, never expanded
    assert [(s["ref"], s["notes"]) for s in rep["same_for_all"]] == [("2-G001", "same for all of them")]
    counts = {t["tab"]: t for t in rep["tabs"]}
    assert counts["2 Missing (blocks export)"]["answered"] == 5 and counts["2 Missing (blocks export)"]["answered_other_beamtimes"] == 1

    capsys.readouterr()
    assert cli.main(["bundle", "answers", "import", str(bdir), str(xlsx), "--by", WHO]) == 0
    text = capsys.readouterr().out
    assert "preview: nothing written" in text and "Free-text rows (3)" in text and "Athena merges (4)" in text


def test_apply_records_through_decide_with_a_cell_note_and_a_second_run_records_nothing(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_filled.xlsx"
    info = _workbook(bdir, xlsx, ANSWERS)
    code, rep, _ = _run(bdir, xlsx, capsys, "--apply")
    assert code == 0 and rep["applied"] is True
    outcomes = [p["outcome"] for p in rep["decisions"]]
    assert outcomes.count("recorded") == 7 and outcomes.count("vocabulary_request_kept") == 1
    assert rep["counts"]["vocabulary_requests_new_recorded"] == 1
    b = M.load(bdir)
    mine = [d for d in b["scientist_decisions"] if (d.get("decided_by") or {}).get("name") == WHO]
    assert mine and all(d.get("note", "").startswith("workbook SYN_filled.xlsx '") for d in mine)
    assert any(d.get("note") == "workbook SYN_filled.xlsx '2 Missing (blocks export)'!Q3" and d.get("value") == info["group_hint"]
               for d in mine)
    kept = [r for r in b.get("vocabulary_requests") or () if (r.get("requested_by") or {}).get("name") == WHO]
    assert [(r["field_path"], r["term"]) for r in kept] == [("sample.sample_form", "SYN blob")]
    # nothing from a free-text, Athena, declined or unresolved row was recorded
    assert not any("'1 Rules and protocol'" in d.get("note", "") or "'Athena merges'" in d.get("note", "") for d in mine)
    assert cli.main(["bundle", "check", str(bdir)]) == 0
    code, again, _ = _run(bdir, xlsx, capsys, "--apply")
    assert code == 0 and again["counts"].get("decisions_recorded", 0) == 0
    assert again["counts"]["vocabulary_requests_new_recorded"] == 0 and again["counts"]["decisions_unchanged"] == 7
    after = M.load(bdir)
    assert after["scientist_decisions"] == b["scientist_decisions"]
    # the off-list word again is the same request, only re-stamped as `decide --as-said` re-stamps it
    strip = lambda rs: [{k: v for k, v in r.items() if k != "reaffirmed_utc"} for r in rs or ()]
    assert strip(after.get("vocabulary_requests")) == strip(b.get("vocabulary_requests"))
    # the questions answered are answered now
    open_ids = {q["question_id"] for q in Q.consolidate(M.load(bdir))["questions"]}
    assert info["group"]["question_id"] not in open_ids and info["dom"]["question_id"] not in open_ids


def test_apply_refuses_a_bundle_in_a_runs_folder_and_preview_there_writes_nothing(base, tmp_path, capsys):
    protected = tmp_path / "_runs_v99" / FOLDER / "bundle"
    shutil.copytree(base, protected)
    xlsx = tmp_path / "SYN_filled.xlsx"
    _workbook(protected, xlsx, ANSWERS)
    before, files = _digest(protected), sorted(p.name for p in protected.iterdir())
    code, _, err = _run(protected, xlsx, capsys, "--apply")
    assert code == W.EXIT_OUTPUT_REFUSED and "_runs_v99" in err and "Nothing was recorded" in err
    code, rep, _ = _run(protected, xlsx, capsys)
    assert code == 0 and rep["decisions"]
    assert _digest(protected) == before and sorted(p.name for p in protected.iterdir()) == files


def test_tabs_and_columns_are_found_by_header_not_title_and_unknown_tabs_are_reported(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_renamed.xlsx"
    shuffled = list(reversed(QHEAD))
    extra = [
        ("SYN odd tab", ["Thing", "YOUR ANSWER"], [{"Thing": "x", "YOUR ANSWER": "yes"}]),
        ("SYN shuffled", shuffled, [{"Ref": "S-0001", "Folder": FOLDER, "Topic": "Measurement environment (operando / in situ / ex situ)",
                                     "YOUR ANSWER": "ex_situ", "ISAAC question ID": _q(bdir, "missing_value", "context.environment")["question_id"]}]),
    ]
    _workbook(bdir, xlsx, {"2-0002": ("operando", None), "R1": ("SYN", None)}, extra=extra,
              rename={"missing": "SYN Missing values", "rules": "SYN Rules", "start": "SYN Welcome"})
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0
    kinds = {t["tab"]: (t["kind"], t["title_known"]) for t in rep["tabs"]}
    assert kinds["SYN Missing values"] == ("questions", False) and kinds["SYN Rules"] == ("free_text", False)
    assert kinds["SYN Welcome"] == ("info", False) and kinds["SYN odd tab"] == ("unknown", False)
    assert rep["unknown_tabs"] == ["SYN odd tab"]
    assert [p["problem"] for p in rep["not_applied"] if p["tab"] == "SYN odd tab"] == ["unknown_tab"]
    # the same question answered differently in two cells: neither is recorded
    clash = [p for p in rep["not_applied"] if "answered differently" in p["reason"]]
    assert {p["tab"] for p in clash} == {"SYN Missing values", "SYN shuffled"} and not rep["decisions"]
    assert {t["tab"]: t["problems"] for t in rep["tabs"]}["SYN shuffled"] == 1
    assert [f["ref"] for f in rep["free_text"]] == ["R1"]


def test_a_collapsed_row_whose_records_differ_takes_yes_only_and_yes_confirms_each(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_g.xlsx"
    _workbook(bdir, xlsx, {"9-G001": ("0.5", None)})
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0 and not rep["decisions"]
    (p,) = rep["not_applied"]
    assert p["ref"] == "9-G001" and p["problem"] == "refused" and "'yes' only" in p["reason"]
    _workbook(bdir, xlsx, {"9-G001": ("Yes", None)})
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert [(p["for_row"], p["decision"]) for p in rep["decisions"]] == [("9-0001", "confirm"), ("9-0002", "confirm")]


def test_blank_unsure_formula_and_same_for_all_answers_record_nothing(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_misc.xlsx"
    _workbook(bdir, xlsx, {"2-0001": ("?", None), "2-0002": ("=A1", None), "2-0003": ("same for all", None),
                           "9-0003": (None, "ditto")})
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0 and not rep["decisions"]
    kinds = {p["ref"]: p["problem"] for p in rep["not_applied"]}
    assert kinds == {"2-0001": "unsure", "2-0002": "invalid", "2-0003": "needs_translation"}
    assert {s["ref"] for s in rep["same_for_all"]} == {"2-0003", "9-0003"}


def test_by_and_orcid_are_checked_and_a_missing_workbook_is_refused(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN.xlsx"
    _workbook(bdir, xlsx)
    assert _run(bdir, xlsx, capsys, by=" ")[0] == W.EXIT_USAGE
    assert _run(bdir, xlsx, capsys, "--orcid", "123")[0] == W.EXIT_USAGE
    assert _run(bdir, tmp_path / "nope.xlsx", capsys)[0] == W.EXIT_NOT_FOUND


# --- the kinds the synthetic bundle has no live example of, planned on its context ---------------------------------


@pytest.fixture()
def ctx(bdir):
    b = M.load(bdir)
    gids = [g["group_id"] for g in b["record_groups"] if g.get("status") in B.LIVE_GROUP_STATUSES]
    b["merge_candidates"] = [{"merge_candidate_id": "mc-syn0000000000001", "group_ids": gids[:2], "status": "proposed"}]
    b["processing_results"] = [{"result_id": "proc-syn", "group_id": gids[0],
                                "athena_versions": [{"version_id": f"{gids[0]}-v01"}, {"version_id": f"{gids[0]}-v02"}]}]
    return W._Ctx(b, folder=FOLDER, xlsx_name="SYN.xlsx", bundle_arg="SYN/bundle", by=WHO, orcid=None), gids


def _row(**kw):
    return {"tab": "SYN tab", "row": 3, "cell": "Q3", "ref": "X-0001", "folder": FOLDER, **kw}


def test_counter_merge_clock_absorber_and_athena_version_rows_map_to_their_decide(ctx):
    c, gids = ctx
    counter = {"question_id": "Q-syncounter", "kind": "naming_counter_positions", "positions": [2]}
    (p,) = W._plan_question(_row(answer="counter"), "value", "counter", counter, c)
    assert (p["call"], p["target_ids"], p["decision"], p["positions"]) == ("target", ["experiment"], "set_counter_positions", [2])
    assert "--target experiment --decision set_counter_positions --positions 2" in p["command"] and "--regroup" in p["follow_up"][0]
    (p,) = W._plan_question(_row(answer="Sequence"), "value", "Sequence", counter, c)
    assert (p["question_id"], p["decision"]) == ("Q-syncounter", "set_not_counter_positions")
    assert "problem" in W._plan_question(_row(answer="some of each"), "value", "some of each", counter, c)[0]
    two = {**counter, "positions": [1, 2]}
    assert "which of them" in W._plan_question(_row(answer="counter"), "value", "counter", two, c)[0]["reason"]

    clock = {"question_id": "Q-synclock", "kind": "clock_time_zone", "target_field_path": "timestamps.acquired_start_utc"}
    (p,) = W._plan_question(_row(answer="UTC"), "value", "UTC", clock, c)
    assert (p["decision"], p["value"]) == ("set_clock_time_zone", "UTC")
    assert "problem" in W._plan_question(_row(answer="yes"), "yes", "yes", clock, c)[0]  # nothing suggested

    absorber = {"question_id": "Q-synabs", "kind": "confirm_absorber"}
    (p,) = W._plan_question(_row(answer="yes", suggestion="Pt L3"), "yes", "yes", absorber, c)
    assert (p["decision"], p["element"], p["edge"]) == ("set_absorber", "Pt", "L3") and "--element Pt --edge L3" in p["command"]
    (p,) = W._plan_question(_row(answer="co k-edge"), "value", "co k-edge", absorber, c)
    assert (p["element"], p["edge"]) == ("Co", "K")
    assert "problem" in W._plan_question(_row(answer="yes", suggestion="Ti"), "yes", "yes", absorber, c)[0]

    (p,) = W._plan_row(_row(id="mc-syn0000000000001", answer="Keep apart"), "value", c, {})
    assert (p["target_ids"], p["decision"]) == (["mc-syn0000000000001"], "keep_apart")
    (p,) = W._plan_row(_row(id="mc-syn0000000000001", answer="merge"), "value", c, {})
    assert (p["target_ids"], p["decision"], p["merge_with"]) == ([gids[0]], "merge", [gids[1]])
    assert f"--merge-with {gids[1]}" in p["command"] and len(p["follow_up"]) == 2

    (p,) = W._plan_row(_row(id=gids[0], answer="v02"), "value", c, {})
    assert (p["target_ids"], p["decision"], p["value"]) == (["proc-syn"], "select_athena_version", f"{gids[0]}-v02")
    assert "problem" in W._plan_row(_row(id=gids[0], answer="none"), "value", c, {})[0]
    assert "problem" in W._plan_row(_row(id=gids[0], answer="v09"), "value", c, {})[0]


def test_answer_words_topics_and_absorber_text():
    assert [W.classify(x) for x in (None, " ", "Yes", "OK.", "y", "no", "No (wrong sample)", "?", "unknown", "in situ", 0.5)] == [
        "blank", "blank", "yes", "yes", "yes", "no", "no", "unsure", "placeholder", "value", "value"]
    assert W.topic_field("Atmosphere  or gas") == "context.thermodynamics.atmosphere"
    assert W.topic_field("Facility’s organization") == "system.facility.organization"
    assert W.topic_field("Sample composition: SYNX2 mass fraction") == "sample.composition.SYNX2_mass_fraction"
    assert W.topic_field("SYN unknown topic") is None
    assert W.parse_absorber("Fe, K") == ("Fe", "K") and W.parse_absorber("Zz L3") is None and W.parse_absorber("Pt") is None
    assert W.SAME_FOR_ALL.search("Same as above") and not W.SAME_FOR_ALL.search("the same sample")
    assert set(W.TAB_KINDS) == {"info", "no_answer", "questions", "free_text", "athena_merges", "unknown"}


def test_the_cli_documents_its_flags():
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert cli.main(["bundle", "answers", "import", "--help"]) == 0
    for flag in ("--by", "--orcid", "--apply", "--folder", "--json"):
        assert flag in buf.getvalue()


def _script(name):
    import importlib.util

    path = W.__file__.rsplit("/apps/api/", 1)[0] + f"/scripts/scientist_workbook/{name}.py"
    spec = importlib.util.spec_from_file_location(f"syn_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_ported_workbook_checks_run_on_paths_given_as_arguments(base, tmp_path, capsys):
    root = tmp_path / "bundles"
    shutil.copytree(base, root / FOLDER / "bundle")
    old, new = tmp_path / "SYN_old.xlsx", tmp_path / "SYN_new.xlsx"
    _workbook(root / FOLDER / "bundle", old)
    _workbook(root / FOLDER / "bundle", new, {"2-0001": ("yes", None)})
    idcheck, idcompare, wbdiff = _script("idcheck"), _script("idcompare"), _script("wbdiff")
    capsys.readouterr()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    # the OTHER beamtime's rows have no bundle here: point that folder at the same bundle so every row is looked up
    shutil.copytree(base, root / OTHER / "bundle")
    assert idcheck.main([str(old), str(root), "--out", str(a)]) == 0
    assert idcheck.main([str(new), str(root), "--out", str(b)]) == 0
    out = capsys.readouterr().out
    rows = json.loads(a.read_text())
    assert {r["sheet"] for r in rows if not r["resolves"]} == {"2 Missing (blocks export)", "5 File-name numbers",
                                                               "No answer needed", "8 Clock time zone"}
    assert "do not resolve" in out
    assert idcompare.main([str(a), str(b)]) == 0
    assert wbdiff.main([str(old), str(old)]) == 0
    assert wbdiff.main([str(old), str(new)]) == 1  # the one answer typed is the one differing cell
    assert "differences 1" in capsys.readouterr().out


def test_a_field_its_question_no_longer_asks_is_reported_with_the_question_that_asks_it_now(bdir, tmp_path, capsys):
    opt = next(q for q in _qs(bdir) if q["kind"] == "optional_values" and q["scope"].startswith("group:")
               and "context.temperature_K" not in (q.get("fields") or {}))
    now = [q for q in _qs(bdir) if q["scope"] == opt["scope"] and q.get("target_field_path") == "context.temperature_K"]
    assert len(now) == 1
    xlsx = tmp_path / "SYN_t.xlsx"
    _workbook(bdir, xlsx, extra=[("SYN per record", QHEAD, [
        {"Ref": "11-0009", "Folder": FOLDER, "Topic": "Temperature (K)", "YOUR ANSWER": "298 K",
         "ISAAC question ID": opt["question_id"]}])])
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0 and not rep["decisions"]
    (p,) = rep["not_applied"]
    assert p["problem"] == "asked_elsewhere" and "the bundle changed" not in p["reason"]
    assert p["reason"].startswith(f"context.temperature_K is asked in its own question for this scope, {now[0]['question_id']}")
    assert "not applied here" in p["reason"] and opt["question_id"] in p["reason"]


# --- review of 65d86a6e: the reviewer's scenarios (sc2.py, s5.py, s6.py), synthetic ---------------------------------


def test_med1_an_answer_that_would_replace_a_later_decision_is_refused_and_named_unless_supersede(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_stale.xlsx"
    info = _workbook(bdir, xlsx, {"2-0002": ("in_situ", None), "2-0001": ("yes", None)})
    later = M.decide_question(bdir, question_id=info["env"]["question_id"], decision="correct", value="operando",
                              by="SYN Later", orcid=None, note="said later")
    assert later["recorded"]
    held = len(M.load(bdir)["scientist_decisions"])
    code, rep, _ = _run(bdir, xlsx, capsys)
    by_ref = {p["ref"]: p for p in rep["decisions"]}
    p = by_ref["2-0002"]
    assert p["outcome"] == "refused_replaces" and "SYN Later" in p["reason"] and "'operando'" in p["reason"]
    assert p["replaces"][0]["decided_by"] == "SYN Later" and p["replaces"][0]["decided_utc"]
    assert "--supersede" in p["reason"] and by_ref["2-0001"]["outcome"] == "would_record"
    assert rep["freshness"] == "per_target"
    capsys.readouterr()
    assert cli.main(["bundle", "answers", "import", str(bdir), str(xlsx), "--by", WHO]) == 0
    assert "would replace: " in capsys.readouterr().out
    # --apply: the later decision stands; the rest is recorded
    code, rep, _ = _run(bdir, xlsx, capsys, "--apply")
    log = M.load(bdir)["scientist_decisions"]
    env_targets = {t["id"] for t in info["env"]["targets"]}
    assert not [d for d in log[held:] if d["target"]["id"] in env_targets]
    assert len(log) > held and {p["ref"]: p["outcome"] for p in rep["decisions"]}["2-0002"] == "refused_replaces"
    # --supersede: recorded over it, and said so
    code, rep, _ = _run(bdir, xlsx, capsys, "--apply", "--supersede")
    p = {p["ref"]: p for p in rep["decisions"]}["2-0002"]
    assert p["outcome"] == "recorded" and p["statement"].startswith("REPLACED a later decision:")
    last = [d for d in M.load(bdir)["scientist_decisions"] if d["target"]["id"] in env_targets][-1]
    assert (last["value"], last["decided_by"]["name"]) == ("in_situ", WHO)


def test_med2_ok_on_a_confirm_proposal_only_confirms_the_value_the_files_give_now(bdir, tmp_path, capsys):
    pot = [q for q in _qs(bdir) if q["kind"] == "confirm_value"
           and q.get("target_field_path") == "context.electrochemistry.potential_setpoint_V"]
    path = "context.electrochemistry.potential_setpoint_V"
    xlsx = tmp_path / "SYN_confirm.xlsx"
    _workbook(bdir, xlsx, extra=[
        ("SYN proposals 2", PHEAD, [
            {"Ref": "P-0009", "Kind": "Value", "Folder": FOLDER, "Topic": "Applied potential (V)", "Claude proposes": 0.95,
             "What 'ok' records": f"confirms the value the files give: {path} = 0.95",
             "ISAAC question ID": pot[2]["question_id"], "YOUR ANSWER": "ok"},
            {"Ref": "P-0010", "Kind": "Value", "Folder": FOLDER, "Topic": "Applied potential (V)", "Claude proposes": 0.8,
             "What 'ok' records": f"confirms the value the files give: {path} = 0.8",
             "ISAAC question ID": pot[3]["question_id"], "YOUR ANSWER": "ok"}]),
        ("SYN stale", QHEAD, [{"Ref": "9-0099", "Folder": FOLDER, "Topic": "Applied potential (V)",
                               "Suggested answer (NOT confirmed)": 0.95, "ISAAC question ID": pot[4]["question_id"],
                               "YOUR ANSWER": "yes"}])])
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert [(p["ref"], p["decision"], p["value"]) for p in rep["decisions"]] == [("P-0010", "confirm", None)]
    stale = {p["ref"]: p for p in rep["not_applied"]}
    assert stale["P-0009"]["problem"] == "stale" and "the files now give 0.4" in stale["P-0009"]["reason"]
    assert stale["9-0099"]["problem"] == "stale" and "the files now give 0.8" in stale["9-0099"]["reason"]


def test_low1_the_runs_refusal_ignores_case_and_follows_links(base, tmp_path, capsys):
    upper = tmp_path / "_RUNS_v98" / FOLDER / "bundle"
    shutil.copytree(base, upper)
    (tmp_path / "innocent").symlink_to(tmp_path / "_RUNS_v98")
    assert W.protected_part(upper) == "_RUNS_v98"
    assert W.protected_part(tmp_path / "innocent" / FOLDER / "bundle") == "_RUNS_v98"
    xlsx = tmp_path / "SYN.xlsx"
    _workbook(upper, xlsx, {"2-0002": ("in_situ", None)})
    before = _digest(upper)
    for d in (upper, tmp_path / "innocent" / FOLDER / "bundle"):
        code, _, err = _run(d, xlsx, capsys, "--apply")
        assert code == W.EXIT_OUTPUT_REFUSED and "_RUNS_v98" in err
    assert _digest(upper) == before


def test_low3_a_blank_folder_is_no_bundles_and_folder_must_be_the_workbooks_and_the_bundles(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_folders.xlsx"
    env = _q(bdir, "missing_value", "context.environment")
    _workbook(bdir, xlsx, {"2-0002": ("in_situ", None)}, extra=[("SYN no folder", QHEAD, [
        {"Ref": "X-0001", "Topic": "Measurement environment (operando / in situ / ex situ)", "YOUR ANSWER": "ex_situ",
         "ISAAC question ID": env["question_id"]}])])
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0 and [p["ref"] for p in rep["decisions"]] == ["2-0002"]
    (p,) = [p for p in rep["not_applied"] if p["ref"] == "X-0001"]
    assert p["problem"] == "blank_folder"
    assert {t["tab"]: t.get("blank_folder") for t in rep["tabs"]}["SYN no folder"] == 1
    assert ("CR1" not in {p["ref"] for p in rep["not_applied"]})  # a free-text row with no Folder is every bundle's
    assert rep["workbook_folders"] == sorted([FOLDER, OTHER]) and rep["bundle_folder"] == FOLDER
    code, _, err = _run(bdir, xlsx, capsys, "--folder", "SYN_NOT_IN_IT")
    assert code == W.EXIT_INPUT_REFUSED and "no row of" in err
    code, _, err = _run(bdir, xlsx, capsys, "--folder", OTHER)
    assert code == W.EXIT_USAGE and "--folder-differs-ok" in err
    code, rep, _ = _run(bdir, xlsx, capsys, "--folder", OTHER, "--folder-differs-ok")
    assert code == 0 and rep["folder"] == OTHER and rep["counts"]["answered_rows_other_beamtimes"] >= 1


def test_low4_placeholder_answers_record_nothing_and_keep_no_vocabulary_request(bdir, tmp_path, capsys):
    xlsx = tmp_path / "SYN_placeholders.xlsx"
    words = {"2-0001": "-", "2-0002": "none", "2-0003": "TBD", "11-0001": "not applicable", "9-0003": "—",
             "9-0004": "n.a."}
    _workbook(bdir, xlsx, {k: (v, None) for k, v in words.items()} | {"AM02": ("none", None), "12-0001": ("None", None)})
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert code == 0 and not rep["decisions"]
    kinds = {p["ref"]: p["problem"] for p in rep["not_applied"]}
    assert all(kinds[k] == "placeholder" for k in words)
    # on the Athena tabs "none" is a listed answer, read there
    assert {a["ref"]: list(a["params_entry"] or {}) for a in rep["athena_merges"]}["AM02"] == ["athena_ignore"]
    assert kinds["12-0001"] != "placeholder"
    code, rep, _ = _run(bdir, xlsx, capsys, "--apply")
    assert not [r for r in M.load(bdir).get("vocabulary_requests") or () if (r.get("requested_by") or {}).get("name") == WHO]


def test_low5_collapsed_rows_yes_without_a_suggestion_and_per_record_precedence(bdir, tmp_path, capsys):
    pot = [q for q in _qs(bdir) if q["kind"] == "confirm_value"
           and q.get("target_field_path") == "context.electrochemistry.potential_setpoint_V"]
    sf = [q for q in _qs(bdir) if q["kind"] == "missing_value" and q.get("target_field_path") == "sample.sample_form"]

    def g_tab(g_row, kids):
        return [("SYN G", QHEAD, [g_row]), ("SYN Gb", QHEAD_B, kids)]

    kids = [{"Ref": f"K-000{i}", "Folder": FOLDER, "Topic": "Applied potential (V)", "Suggested answer (NOT confirmed)": v,
             "ISAAC question ID": q["question_id"], "Covered by collapsed row": "K-G001"}
            for i, (q, v) in enumerate(((pot[0], 0.1), (pot[1], 0.2)), start=1)]
    # 'yes' on a collapsed row that shows no suggestion and does not say "each record's own": reported, not expanded
    xlsx = tmp_path / "SYN_g1.xlsx"
    _workbook(bdir, xlsx, extra=g_tab({"Ref": "K-G001", "Folder": FOLDER, "Topic": "Applied potential (V)",
                                       "ISAAC question ID": "G-synk", "YOUR ANSWER": "yes"}, kids))
    code, rep, _ = _run(bdir, xlsx, capsys)
    assert not rep["decisions"]
    (p,) = [p for p in rep["not_applied"] if p["ref"] == "K-G001"]
    assert p["problem"] == "needs_translation" and "shows no suggestion" in p["reason"]
    # a per-record answer overrides the collapsed row for its record; the others take the collapsed row's answer
    kids3 = [{"Ref": f"S-000{i}", "Folder": FOLDER, "Topic": "Sample form (powder, film, ...)",
              "ISAAC question ID": q["question_id"], "Covered by collapsed row": "S-G001",
              **({"YOUR ANSWER": "pellet"} if i == 1 else {})} for i, q in enumerate(sf, start=1)]
    xlsx = tmp_path / "SYN_g2.xlsx"
    _workbook(bdir, xlsx, extra=g_tab({"Ref": "S-G001", "Folder": FOLDER, "Topic": "Sample form (powder, film, ...)",
                                       "ISAAC question ID": "G-syns", "YOUR ANSWER": "film"}, kids3))
    code, rep, _ = _run(bdir, xlsx, capsys)
    got = {(p["question_id"], p["value"]) for p in rep["decisions"]}
    assert got == {(sf[0]["question_id"], "pellet"), (sf[1]["question_id"], "film"), (sf[2]["question_id"], "film")}
    (o,) = [p for p in rep["not_applied"] if p["problem"] == "overridden"]
    assert o["ref"] == "S-G001" and o["for_row"] == "S-0001" and "takes precedence" in o["reason"]
    assert not [p for p in rep["not_applied"] if "answered differently" in p["reason"]]
