"""r4b: what a real-data run on an SSRL BL15-2 Ir L3 HERFD beamtime found (87 runs of 6 electrodes at many potentials,
plus 5 standards, 78 record groups). Synthetic only: the committed multi-operator corpus (ZZ names), the SYN counter
folder and invented scans.

* M1: a beamtime-wide answer for a field covers each run's disagreement about it (the record is composed from that
  answer), counted with ``conflicts_covered_by_decisions``, under the same question id;
* M2: the counter question's example names differ ONLY at the asked position; a not-counter answer cautions every open
  merge candidate whose names differ only there, offers one command to keep them all apart, and decides none; a
  keep_apart of several candidates is said in the plural;
* M3: per-group questions about one field that share a reading in their own files share a ``same_reading_group``,
  answered together with ``--same-reading``; no id changes, and file names that read the field differently never share;
* M4: a field of an optional question asked for the whole beamtime says which groups and runs an answer there reaches
  (the rest are answered per group); the decide reply (and an ``--as-said`` refusal) names them, and says plainly when
  the word would land on groups it does not describe (an ex-situ run, a standard, for a cell type);
* M5: a Campaign Info beamline is compared with the recorded one as the facility-hint comparison reads beamlines
  (``SSRL BL15-2`` is ``BL15-2``); a real clash with a recorded value is a whole-beamtime Disagreements row ruled once;
  a clash a typed cell makes is offered as one ``--question`` command, not one ``--target`` per target;
"""

from __future__ import annotations

import json
import re
import shlex

import openpyxl
import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import template as T

from test_local_import_capture_decisions import _grouped_stems
from test_local_import_polish_c14g_adopt import _rule
from test_local_import_template_adopt import _import, _their_sheet
from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, bdir, fake_upstream, pristine)

WHO = "SYNTHETIC TEST"
TECH = "system.technique"
RULED, UNRULED = "conf-007", "conf-009"  # run-004's and run-005's disagreements in the corpus


# --- M1: a beamtime-wide answer covers the runs' disagreements ----------------------------------------------------


def _technique_disagreements(bdir):
    """The BL15-2 shape: two runs' disagreements are about the technique, and no answer is given yet."""
    M.group(bdir)
    b = M.load(bdir)
    cand_of = {c["candidate_id"]: c for c in b["candidates"]}
    conflicts = {cf["conflict_id"]: cf for cf in b["conflicts"]}
    for cid in (RULED, UNRULED):
        cand_of[conflicts[cid]["candidate_id"]]["target_field_path"] = TECH
    M.save_bundle(bdir, b)
    return conflicts, next(c for c in b["candidates"] if c["target_field_path"] == TECH and c["run_id"] is None)


def _conflict_q(payload, conflict_id):
    return next(q for q in payload["questions"] if q["targets"] == [{"kind": "conflict", "id": conflict_id}])


def test_a_beamtime_wide_answer_covers_the_runs_disagreements_about_its_field(bdir):
    _, beam = _technique_disagreements(bdir)
    before = Q.consolidate(M.load(bdir))
    ids = {cid: _conflict_q(before, cid)["question_id"] for cid in (RULED, UNRULED)}
    assert all("covered_by_decisions" not in _conflict_q(before, cid) for cid in ids)
    got = M.decide(bdir, target_ids=[beam["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    after = Q.consolidate(M.load(bdir))
    [did] = {d["decision_id"] for d in M.load(bdir)["scientist_decisions"]}
    for cid in (RULED, UNRULED):
        q = _conflict_q(after, cid)
        assert q["question_id"] == ids[cid]  # the same id
        assert q["covered_by_decisions"] == [did] and q["affects_record"] is False and q["tier"] == Q.TIER_OPTIONAL
        assert q["why"].startswith(f"Already decided: the beamtime-wide answer for {TECH} ({did}) reaches its run")
    assert after["counts"]["conflicts_affecting_a_record"] == 0
    assert after["counts"]["conflicts_covered_by_decisions"] == before["counts"]["conflicts_covered_by_decisions"] + 2
    assert got["recorded"]


def test_a_run_decided_otherwise_still_disagrees_with_the_beamtime_answer(bdir):
    conflicts, beam = _technique_disagreements(bdir)
    M.decide(bdir, target_ids=[beam["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="XAS", **BY)
    p = Q.consolidate(M.load(bdir))
    assert "covered_by_decisions" not in _conflict_q(p, RULED)  # its run's own answer differs: two values
    assert _conflict_q(p, UNRULED)["covered_by_decisions"]
    # the same value on the run as for the beamtime: both decisions cover it, said as decisions of its run
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    q = _conflict_q(Q.consolidate(M.load(bdir)), RULED)
    assert len(q["covered_by_decisions"]) == 2 and q["why"].startswith("Already decided: its run holds")


def test_a_deferred_beamtime_answer_covers_nothing(bdir):
    _, beam = _technique_disagreements(bdir)
    M.decide(bdir, target_ids=[beam["candidate_id"]], decision="defer", value=None, **BY)
    p = Q.consolidate(M.load(bdir))
    assert all("covered_by_decisions" not in _conflict_q(p, cid) for cid in (RULED, UNRULED))


# --- M2: the counter question's examples, and a not-counter answer's merge candidates ------------------------------


def _hand_bundle(stems_by_candidate, more_runs=()):
    stems = [s for c in stems_by_candidate for s in c] + list(more_runs)
    runs = [{"run_key": f"k{i}", "stem": s} for i, s in enumerate(dict.fromkeys(stems))]
    key = {r["stem"]: r["run_key"] for r in runs}
    return {"runs": runs,
            "record_groups": [{"group_id": f"g-{r['run_key']}", "member_run_keys": [r["run_key"]], "role": "sample",
                               "status": "proposed"} for r in runs],
            "merge_candidates": [{"merge_candidate_id": f"mc-{i}", "status": "proposed",
                                  "group_ids": [f"g-{key[s]}" for s in c],
                                  "reasons": [{"code": "numeric_name_token_differs"}]}
                                 for i, c in enumerate(stems_by_candidate)]}


def test_a_counter_example_differs_only_at_the_asked_position():
    # the walk: the candidate's first two names differ at the 1st AND the 2nd token
    bundle = _hand_bundle([["01_13_SYNa_cell", "03_12_SYNa_cell", "02_13_SYNa_cell"]], more_runs=["03_14_SYNa_cell"])
    got = Q._counter_examples(bundle, [1, 2])
    assert got[1]["differ"] == ["[01]_13_SYNa_cell", "[02]_13_SYNa_cell"]
    # no candidate holds two names differing only at the 2nd token: two names of the bundle that do
    assert got[2]["differ"] == ["03_[12]_SYNa_cell", "03_[14]_SYNa_cell"]


def test_no_example_is_shown_where_no_two_names_differ_only_there():
    got = Q._counter_examples(_hand_bundle([["01_13_SYNa_cell", "03_12_SYNa_cell"]]), [1, 2])
    assert got == {}


STEMS = ["01_13_SYNcat_pH2_400mV", "03_12_SYNcat_pH2_400mV", "02_13_SYNcat_pH2_400mV", "01_12_SYNcat_pH2_400mV"]


@pytest.fixture()
def electrodes(tmp_path):
    return _grouped_stems(tmp_path, STEMS)


def test_a_not_counter_answer_cautions_the_candidates_it_names_and_decides_none(electrodes, capsys):
    b = M.load(electrodes)
    open_ids = [mc["merge_candidate_id"] for mc in b["merge_candidates"] if mc["status"] == "proposed"]
    assert len(open_ids) >= 2 and G.said_not_counter_candidates(b) == []
    got = M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.NOT_COUNTER_DECISION, value=None,
                            by=WHO, orcid=None, positions=[1, 2])
    b = M.load(electrodes)
    assert got["said_not_counter_merge_candidates"] == open_ids == G.said_not_counter_candidates(b)
    assert f"{len(open_ids)} open merge candidate(s) have file names that differ only at position(s)" in got["statement"]
    assert Q.KEEP_APART_SAID_NOT_COUNTER_COMMAND in got["statement"]
    assert all(mc["status"] == "proposed" for mc in b["merge_candidates"])  # none decided
    for mc in b["merge_candidates"]:
        caution = G.said_not_counter_caution(b, mc)
        assert caution["statement"].startswith("the scientist said position 1 is not a counter (")
    # shown where a scientist looks at a candidate: `show merge-candidate` and `list merge-candidates`
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(electrodes), "merge-candidate", open_ids[0]]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert [c["code"] for c in shown["caution"]][-1] == G.CAUTION_SAID_NOT_COUNTER
    assert shown["question"].startswith("CAUTION: the scientist said position 1 is not a counter")
    assert any(Q.KEEP_APART_SAID_NOT_COUNTER_COMMAND in c for c in shown["answer_with"])
    assert cli.main(["bundle", "list", str(electrodes), "merge-candidates"]) == 0
    rows = json.loads(capsys.readouterr().out)["items"]
    assert all(any(c.startswith("the scientist said position 1") for c in r["caution"]) for r in rows)


def test_one_command_keeps_them_all_apart_and_says_so_in_the_plural(electrodes, capsys):
    M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.NOT_COUNTER_DECISION, value=None,
                      by=WHO, orcid=None, positions=[1, 2])
    cautioned = G.said_not_counter_candidates(M.load(electrodes))
    argv = shlex.split(Q.KEEP_APART_SAID_NOT_COUNTER_COMMAND.replace("<bundle_dir>", str(electrodes)).replace("<your name>", WHO))
    capsys.readouterr()
    assert argv[0] == "isaac" and cli.main(argv[1:]) == 0
    out = json.loads(capsys.readouterr().out)
    assert sorted(out["recorded"]) == sorted(cautioned)
    assert out["statement"].startswith(f"Recorded: for each of these {len(cautioned)} merge candidates")
    assert "this merge candidate" not in out["statement"]
    b = M.load(electrodes)
    assert all(mc["status"] == "kept_apart" for mc in b["merge_candidates"] if mc["merge_candidate_id"] in cautioned)
    assert G.said_not_counter_candidates(b) == []
    with pytest.raises(M.MutationRefused, match="has nothing to keep apart"):
        M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.KEEP_APART_DECISION, value=None,
                          by=WHO, orcid=None)


def test_the_bulk_keep_apart_needs_a_not_counter_answer_first(electrodes):
    with pytest.raises(M.MutationRefused, match="has nothing to keep apart") as exc:
        M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.KEEP_APART_DECISION, value=None,
                          by=WHO, orcid=None)
    assert exc.value.code == 2
    assert not M.load(electrodes)["scientist_decisions"]


def test_a_candidate_whose_names_differ_at_a_position_still_open_is_not_cautioned(electrodes):
    M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.NOT_COUNTER_DECISION, value=None,
                      by=WHO, orcid=None, positions=[2])
    assert G.said_not_counter_candidates(M.load(electrodes)) == []  # they differ at the 1st token


# --- M3: per-group questions that share a reading are answered together ------------------------------------------

NAME = "sample.material.name"
SETPOINT = "context.electrochemistry.potential_setpoint_V"


def _per_group(payload, path):
    return [q for q in payload["questions"] if q["target_field_path"] == path and q["scope"].startswith("group:")
            and q["kind"] == "confirm_value"]


def test_per_group_questions_sharing_a_reading_share_a_group_and_keep_their_ids(bdir, monkeypatch):
    M.group(bdir)
    b = M.load(bdir)
    grouped = Q.consolidate(b)
    with monkeypatch.context() as m:
        m.setattr(Q, "_note_shared_reading_groups", lambda *a: None)  # as before r4-b
        plain = Q.consolidate(b)
    key = lambda p: [(q["question_id"], q["scope"], q["kind"], q["targets"]) for q in p["questions"]]  # noqa: E731
    assert key(grouped) == key(plain)  # no question merged, removed or renamed
    names = _per_group(grouped, NAME)
    zz2 = [q for q in names if "'ZZ2'" in q["text"]]
    assert len(zz2) == 3 and len({q["same_reading_group"] for q in zz2}) == 1 and zz2[0]["same_reading_count"] == 3
    q = zz2[0]
    assert "3 questions share this reading ('ZZ2', as the files write it)" in q["text"]
    assert f"answer them together with {q['same_reading_command']}" in q["text"]
    assert f"--question {q['question_id']} --same-reading --decision correct" in q["same_reading_command"]
    assert "other group(s) hold the same reading" not in q["text"]  # said once, as a group
    assert {m["question_id"] for m in q["same_reading_members"]} == {x["question_id"] for x in zz2}
    # set-points: one group per potential the file names write
    by_value = {}
    for sp in _per_group(grouped, SETPOINT):
        by_value.setdefault(sp.get("same_reading_group"), []).append(sp)
    sizes = sorted(len(v) for k, v in by_value.items() if k)
    assert sizes == [2, 3] and all("their file names read alike for this field" in sp["text"]
                                   for k, v in by_value.items() if k for sp in v)


def test_one_decide_answers_every_question_of_a_shared_reading(bdir):
    M.group(bdir)
    zz2 = [q for q in _per_group(Q.consolidate(M.load(bdir)), NAME) if "'ZZ2'" in q["text"]]
    got = M.decide_question(bdir, question_id=zz2[0]["question_id"], same_reading=True, decision="correct",
                            value="ZZ2 synthetic", by=WHO, orcid=None)
    assert sorted(got["recorded"]) == sorted(t["id"] for q in zz2 for t in q["targets"])
    left = {q["question_id"] for q in _per_group(Q.consolidate(M.load(bdir)), NAME)}
    assert not left & {q["question_id"] for q in zz2}


def test_file_names_that_read_the_field_differently_never_share_a_group(monkeypatch):
    """The r3c rule: one reading in the files, but the runs' own names write two set-points: two keys, no group."""
    cands = {f"c{i}": {"candidate_id": f"c{i}", "run_id": f"r{i}", "observed_literals": ["SYN 1 V"],
                       "evidence": [{"relative_path": f"SYN_{i}.dat"}]} for i in range(4)}
    runs = [{"run_id": f"r{i}", "stem": f"SYN_{i}"} for i in range(4)]
    qs = [{"question_id": f"Q-{i}", "target_field_path": SETPOINT, "targets": [{"kind": "candidate", "id": f"c{i}"}],
           "same_reading_as": ["Q-x"], "text": "Q.", "answer_command": f"isaac bundle decide <bundle_dir> --question Q-{i} --decision confirm"}
          for i in range(4)]
    monkeypatch.setattr(Q, "file_name_readings", lambda bundle, run, path: [{"value": 0.6 if run["run_id"] in ("r0", "r1") else 0.3}])
    Q._note_shared_reading_groups(qs, cands, {"runs": runs}, {})
    assert qs[0]["same_reading_group"] == qs[1]["same_reading_group"] != qs[2]["same_reading_group"] == qs[3]["same_reading_group"]
    assert all(q["same_reading_count"] == 2 for q in qs)
    assert "their file names read alike for this field (0.6)" in qs[0]["text"]


# --- M4: what a beamtime-wide optional answer reaches, and where it does not fit -----------------------------------

CELL = "context.electrochemistry.cell_type"


def _leftover_cell_type(bdir):
    """Six runs' cell types answered per run (a template's File List), and two of the rest recorded ex situ."""
    M.group(bdir)
    b = M.load(bdir)
    cells = [m["value_id"] for m in b["missing_values"] if m["target_field_path"] == CELL]
    M.decide(bdir, target_ids=cells[:6], decision="correct", value="three_electrode", **BY)
    env = [m["value_id"] for m in b["missing_values"]
           if m["target_field_path"] == "context.environment" and m["run_id"] in ("run-008", "run-009")]
    M.decide(bdir, target_ids=env, decision="correct", value="ex_situ", **BY)
    q = next(q for q in Q.consolidate(M.load(bdir))["questions"] if q["kind"] == "optional_values" and CELL in q["fields"])
    return q, {g["group_id"]: g for g in M.load(bdir)["record_groups"]}


def _group_of(groups, run_id):
    return next(gid for gid, g in groups.items() if run_id in g["member_run_ids"])


def test_the_question_says_which_groups_a_beamtime_answer_reaches_per_field(bdir):
    q, groups = _leftover_cell_type(bdir)
    assert q["scope"] == "experiment" and len(q["fields"][CELL]) == 3
    reach = q["field_reach"][CELL]
    assert reach["groups"] == 3 and reach["groups_total"] == 9 and reach["runs"] == 3
    assert reach["group_ids"] == [_group_of(groups, r) for r in ("run-007", "run-008", "run-009")]
    assert [b["group_id"] for b in reach["misfit_groups"]] == [_group_of(groups, r) for r in ("run-008", "run-009")]
    assert f"{CELL} reaches 3 of 9 group(s) (3 run(s): " in q["text"]
    assert "the other 6 already answered per group" in q["text"]
    assert "careful: it would put a cell type on " in q["text"] and "recorded ex situ: measured outside a cell" in q["text"]


def test_the_decide_reply_names_the_groups_and_runs_it_reached_and_the_misfits(bdir):
    q, groups = _leftover_cell_type(bdir)
    got = M.decide_question(bdir, question_id=q["question_id"], field=CELL, decision="correct", value="beaker_cell",
                            by=WHO, orcid=None)
    assert got["reach"]["run_ids"] == ["run-007", "run-008", "run-009"] and got["reach"]["groups_total"] == 9
    assert f"For {CELL} it reaches 3 of the beamtime's 9 record groups (3 runs: " in got["statement"]
    assert "It reaches every record group" not in got["statement"]
    assert "Careful: it puts a cell type on 2 groups it does not describe" in got["statement"]


def test_an_as_said_word_says_which_groups_it_would_reach(bdir):
    q, _ = _leftover_cell_type(bdir)
    with pytest.raises(M.OffListRefused) as exc:
        M.decide_question(bdir, question_id=q["question_id"], field=CELL, decision="correct", value="SYN cell",
                          by=WHO, orcid=None, as_said=True)
    said = str(exc.value)
    assert "kept as a vocabulary request" in said
    assert "recorded, it would reach 3 of the beamtime's 9 record groups (3 runs: " in said
    assert "Careful: it would put a cell type on 2 groups it does not describe" in said


def test_a_standard_is_never_described_by_a_cell_type():
    bundle = {"runs": [{"run_key": "k1", "run_id": "r1"}, {"run_key": "k2", "run_id": "r2"}],
              "record_groups": [{"group_id": "g-std", "role": G.ROLE_REFERENCE, "member_run_keys": ["k1"]},
                                {"group_id": "g-cell", "role": G.ROLE_SAMPLE, "member_run_keys": ["k2"]}],
              "candidates": [], "missing_values": [], "scientist_decisions": []}
    assert [b["group_id"] for b in M.misfit_groups(bundle, CELL, ["g-std", "g-cell"])] == ["g-std"]
    assert M.misfit_groups(bundle, "sample.material.name", ["g-std"]) == []  # only a cell's own words


# --- M5: Campaign Info against the values already recorded ----------------------------------------------------------

BEAMLINE, FACILITY = "system.facility.beamline", "system.facility.facility_name"


def _recorded_campaign(bdir, beamline="BL15-2", facility="SYN Lab"):
    """Every run's beamline and facility name recorded by a decide (before any sheet)."""
    M.group(bdir)
    b = M.load(bdir)
    for path, value in ((BEAMLINE, beamline), (FACILITY, facility)):
        tids = [m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path]
        M.decide(bdir, target_ids=tids, decision="correct", value=value, by="SYN Other Person", orcid=None)
    return b


def _adopt(bdir, theirs, out, capsys):
    capsys.readouterr()
    assert cli.main(["bundle", "template", "adopt", str(bdir), str(theirs), "--out", str(out), "--json"]) == 0
    return json.loads(capsys.readouterr().out)["adopted"]


def test_one_beamline_in_two_spellings_is_no_clash(bdir, tmp_path, capsys):
    _recorded_campaign(bdir)
    s = _their_sheet(bdir, tmp_path / "theirs.xlsx", beamline="SSRL BL15-2")
    adopted = _adopt(bdir, s, tmp_path / "A.xlsx", capsys)
    assert not [d for d in adopted["disagreements"] if d["header"] == "Beamline/Instrument"]
    code, rep, err = _import(bdir, tmp_path / "A.xlsx", capsys)
    assert code == 0, err
    assert not [c for c in rep["clashes"] if c["header"] == "Beamline/Instrument"]
    held = [x for x in rep["already_decided_same_value"] if x["cell"] == "'Campaign Info'!B5"]
    assert len(held) == 9  # every run's recorded BL15-2 is the beamline their sheet names
    assert T.agrees_for(BEAMLINE, "SSRL BL15-2", "BL15-2") and not T.agrees_for(BEAMLINE, "BL15-2", "BL11-2")
    assert not T.agrees_for(FACILITY, "SSRL", "SSRL BL15-2")  # only a beamline is read so


def test_a_campaign_value_a_recorded_answer_contradicts_is_ruled_once_on_its_row(bdir, tmp_path, capsys):
    _recorded_campaign(bdir)
    s = _their_sheet(bdir, tmp_path / "theirs.xlsx", beamline="SSRL BL15-2")
    adopted = _adopt(bdir, s, tmp_path / "A.xlsx", capsys)
    [row] = [d for d in adopted["disagreements"] if d["kind"] == "recorded"]
    assert row["header"] == "Facility Name" and row["scope"] == "experiment" and row["runs"] == []
    assert row["readings"] == ["recorded: 'SYN Lab' (9 run(s))"]
    assert row["recorded_note"].endswith("your sheet says `Synthetic Light Source`: rule which")
    assert openpyxl.load_workbook(tmp_path / "A.xlsx")["Campaign Info"]["B3"].value is None  # not adopted
    code, rep, _ = _import(bdir, tmp_path / "A.xlsx", capsys)
    assert code == 0 and rep["clashes"] == []  # nothing clashes: it waits on its row
    # one ruling on the row records it for every run, without --supersede (the row named the recorded value)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {row["id"]: "Synthetic Light Source"})
    code, rep, err = _import(bdir, tmp_path / "Ar.xlsx", capsys, "--apply")
    assert code == 0, err
    b = M.load(bdir)
    held = {m["value_id"]: m for m in b["missing_values"] if m["target_field_path"] == FACILITY}
    latest = {}
    for d in b["scientist_decisions"]:
        if d["target"]["id"] in held:
            latest[d["target"]["id"]] = d["value"]
    assert set(latest.values()) == {"Synthetic Light Source"} and len(latest) == 9
    # adopting again: nothing left to rule, the value is adopted
    again = _adopt(bdir, s, tmp_path / "B.xlsx", capsys)
    assert not [d for d in again["disagreements"] if d["kind"] == "recorded"]


def test_a_typed_campaign_clash_is_offered_as_one_question_command(bdir, tmp_path, capsys):
    _recorded_campaign(bdir)
    out = tmp_path / "T.xlsx"
    assert cli.main(["bundle", "template", "export", str(bdir), "--out", str(out)]) == 0
    wb = openpyxl.load_workbook(out)
    wb["Campaign Info"]["B3"] = "Synthetic Light Source"  # typed by the scientist, never adopted
    wb.save(out)
    code, rep, err = _import(bdir, out, capsys)
    assert code == 0, err
    [cell] = rep["clashes_by_cell"]
    assert cell["targets"] == 9 and "--target" not in cell["command"]
    assert re.search(rf"--question Q-\w+ --field {FACILITY} --decision correct --value='Synthetic Light Source'", cell["command"])
    # the command records exactly the cell's targets
    argv = shlex.split(cell["command"].replace("<bundle_dir>", str(bdir)).replace("<your name>", WHO))
    capsys.readouterr()
    assert cli.main(argv[1:]) == 0
    got = json.loads(capsys.readouterr().out)
    assert sorted(got["recorded"]) == sorted(cell["target_ids"])

