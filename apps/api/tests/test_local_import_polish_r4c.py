"""r4c: the review of r4b. Synthetic only: the committed multi-operator corpus (ZZ names), the SYN counter folder and
invented values.

* HIGH-1: the one ``--question`` command a Campaign Info clash cell is offered is found from ONE consolidation, reading
  only the questions on the cell's own field (it was quadratic: two consolidations and a question search per field);
* HIGH-2: what an answer to a beamtime-wide optional question reaches per field is read from one index per
  ``consolidate`` (every ``sample=<key>`` partition used to rebuild the live groups and the run map per field);
* MED-1: a disagreement is covered by decisions only when every decision reaching its runs, and the other runs of their
  live groups (the record pools them), gives one value: one run whose own answer differs is not covered;
* MED-2: a Campaign Info Disagreements row whose recorded value only some runs hold names it: one ruling records it
  for every run, without ``--supersede``, as for a value every run holds; a decision recorded since the adopt still
  clashes;
* L1-L5: ``reveal`` finds a reading in the literal on word boundaries, a number as a number; the shared-reading key
  holds every literal; the bulk keep_apart is pinned to the candidates its reply listed; the deprecated terms match the
  pinned portal validator's; no real-data detail in the docs.
"""

from __future__ import annotations

import copy
import re
import shlex
import time
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import portal
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import template as T

from test_local_import_polish_c14g_adopt import _rule
from test_local_import_polish_r4b import (FACILITY, RULED, STEMS, WHO, _adopt, _conflict_q, _recorded_campaign)
from test_local_import_capture_decisions import _grouped_stems
from test_local_import_template_adopt import _import, _their_sheet
from test_local_import_records import BY, bdir, fake_upstream, pristine  # noqa: F401  (fixtures)


def _scaled(b: dict, copies: int) -> dict:
    """``b`` with its runs (their candidates, missing values, groups AND the decisions on them) copied ``copies`` times."""
    out = copy.deepcopy(b)
    run_level = {c["candidate_id"] for c in b["candidates"] if c["run_id"]} | {
        m["value_id"] for m in b["missing_values"] if m["run_id"]}
    for k in range(1, copies):
        sfx = f"-x{k}"
        out["runs"] += [{**copy.deepcopy(r), "run_id": r["run_id"] + sfx, "run_key": r["run_key"] + sfx} for r in b["runs"]]
        out["candidates"] += [{**copy.deepcopy(c), "candidate_id": c["candidate_id"] + sfx, "run_id": c["run_id"] + sfx}
                              for c in b["candidates"] if c["run_id"]]
        out["missing_values"] += [{**copy.deepcopy(m), "value_id": m["value_id"] + sfx, "run_id": m["run_id"] + sfx}
                                  for m in b["missing_values"] if m["run_id"]]
        out["record_groups"] += [{**copy.deepcopy(g), "group_id": g["group_id"] + sfx,
                                  "member_run_keys": [x + sfx for x in g["member_run_keys"]]} for g in b["record_groups"]]
        out["scientist_decisions"] += [{**copy.deepcopy(d), "decision_id": f"{d['decision_id']}{sfx}",
                                        "target": {**d["target"], "id": d["target"]["id"] + sfx}}
                                       for d in b["scientist_decisions"] if d["target"]["id"] in run_level]
    return out


# --- HIGH-1: the cell's one command, from one consolidation ----------------------------------------------------------


def test_a_campaign_clash_cell_of_4000_runs_is_offered_its_question_command_in_bounded_time(bdir, monkeypatch):
    """Measured before the fix (the reviewer's 4,000-run bundle): 177 s (two consolidations, and a search of every
    question per answered question and field). After: one consolidation, ~4-5 s here."""
    _recorded_campaign(bdir)  # every run's facility name recorded: the Campaign Info cell's targets are answered
    b = M.load(bdir)
    big = _scaled(b, 4000 // len(b["runs"]))
    assert len(big["runs"]) >= 3990
    pairs = [(m["value_id"], "correct") for m in big["missing_values"] if m["target_field_path"] == FACILITY]
    assert len(pairs) == len(big["runs"])
    calls = []
    real = Q.consolidate
    monkeypatch.setattr(Q, "consolidate", lambda *a, **k: calls.append(k) or real(*a, **k))
    start = time.perf_counter()
    command = T._question_command(big, pairs, "Synthetic Light Source", {}, cache := {})
    elapsed = time.perf_counter() - start
    assert elapsed < 25, f"_question_command took {elapsed:.1f}s for {len(big['runs'])} runs"
    assert len(calls) == 1 and calls[0]["include_answered"] is True  # consolidated ONCE
    assert re.search(rf"--question Q-\w+ --field {FACILITY} --decision correct --value='Synthetic Light Source'", command)
    assert list(cache["by_field"]) == [FACILITY]  # only the cell's own field was indexed
    # a second cell reuses the one consolidation
    assert T._question_command(big, pairs[:2], "SYN", {}, cache) is None and len(calls) == 1


def test_the_one_consolidation_finds_what_two_did(bdir):
    """The r4-b index (an open and an answered consolidation) and the r4-c one agree, question for question."""
    _recorded_campaign(bdir)
    M.decide(bdir, target_ids=[m["value_id"] for m in M.load(bdir)["missing_values"]
                               if m["target_field_path"] == "system.facility.beamline"][:3],
             decision="defer", value=None, **BY)
    b = M.load(bdir)
    open_payload, answered = Q.consolidate(b), Q.consolidate(b, include_answered=True, explain_counter=False)
    old = {}
    for q in answered["questions"]:
        for field in (sorted(q.get("fields") or ()) if q["kind"] == "optional_values" else [None]):
            ids = frozenset(Q.targets_for(answered, q["question_id"], None, field))
            if ids and not Q.targets_for(open_payload, q["question_id"], None, field):
                old.setdefault(ids, (q["question_id"], field))
    assert old
    cache: dict = {}
    for ids, (qid, field) in old.items():
        got = T._question_command(b, [(i, "correct") for i in ids], "V", {}, cache)
        assert got and f"--question {qid}" + (f" --field {field} " if field else " ") in got
    assert all(ids in old for idx in cache["by_field"].values() for ids in idx)  # nothing offered that was not


# --- HIGH-2: the reach index, built once per consolidate ---------------------------------------------------------------


def test_consolidate_builds_the_reach_index_once_and_reaches_as_before(bdir, monkeypatch):
    M.group(bdir)
    b = M.load(bdir)
    big = _scaled(b, 20)
    built = []
    real = M.reach_index
    monkeypatch.setattr(M, "reach_index", lambda bundle: built.append(1) or real(bundle))
    p = Q.consolidate(big)
    beamtime = [q for q in p["questions"] if q["kind"] == "optional_values" and q["scope"] == "experiment"]
    assert beamtime and len(built) == 1
    # the same reach as each call building its own (r4-b), field for field
    index = real(big)
    for q in beamtime:
        for f, ids in q["fields"].items():
            mine = M.answer_reach(big, ids, f, index)
            alone = M.answer_reach(big, ids, f, real(big))
            assert mine == alone
            assert M.misfit_groups(big, f, mine["group_ids"], index) == M.misfit_groups(big, f, mine["group_ids"])


def test_the_reach_index_reads_each_target_once_and_keeps_the_bundle_order():
    runs = [{"run_id": f"r{i}", "run_key": f"k{i}"} for i in range(4)]
    b = {"runs": runs, "candidates": [{"candidate_id": "c-beam", "run_id": None}],
         "missing_values": [{"value_id": f"m{i}", "run_id": f"r{i}"} for i in range(4)],
         "record_groups": [{"group_id": "g-b", "member_run_keys": ["k2", "k3"]},
                           {"group_id": "g-a", "member_run_keys": ["k0", "k1"]},
                           {"group_id": "g-dead", "member_run_keys": ["k1"], "status": "rejected"}]}
    got = M.answer_reach(b, ["m3", "m0", "m1", "nowhere"], "sample.material.name")
    assert got == {"group_ids": ["g-b", "g-a"], "run_ids": ["r3", "r0", "r1"], "groups_total": 2,
                   "beamtime_fills_none": False}
    every = M.answer_reach(b, ["c-beam"], "sample.material.name")
    assert every["group_ids"] == ["g-b", "g-a"] and every["run_ids"] == ["r2", "r3", "r0", "r1"]


# --- MED-1: one value across every decision the record pools -----------------------------------------------------------

FORMULA = "sample.material.formula"


def _formula_disagreement(bdir, *, mate=None):
    """run-004's disagreement made one about an optional field (the beamtime-wide missing value miss-0001 too), with
    run-004's own candidate cand-0072 for it; ``mate``: a candidate of run-005 for it, run-005 joined to run-004's
    group (so the record pools both runs' decisions)."""
    M.group(bdir)
    b = M.load(bdir)
    conf = next(cf for cf in b["conflicts"] if cf["conflict_id"] == RULED)

    def f(b):
        for c in b["candidates"]:
            if c["candidate_id"] in (conf["candidate_id"], "cand-0072", mate):
                c["target_field_path"] = FORMULA
        for m in b["missing_values"]:
            if m["value_id"] == "miss-0001":
                m["target_field_path"] = FORMULA
        if mate:
            key = {r["run_id"]: r["run_key"] for r in b["runs"]}
            g4 = next(g for g in b["record_groups"] if key["run-004"] in g["member_run_keys"])
            g5 = next(g for g in b["record_groups"] if key["run-005"] in g["member_run_keys"])
            g4["member_run_keys"].append(key["run-005"])
            b["record_groups"].remove(g5)
    M.mutate(bdir, f)


def _composed(bdir):
    b = M.load(bdir)
    key = {r["run_id"]: r["run_key"] for r in b["runs"]}
    g = next(g for g in Q.live_groups(b) if key["run-004"] in g["member_run_keys"])
    _, rep = R.compose_group(b, g, bdir, R.composition_index(b))
    return [d for d in rep["disagreements"] if d["path"] == FORMULA], [x for x in rep["filled"] if x["path"] == FORMULA]


def test_a_run_whose_own_answer_differs_from_the_beamtime_one_is_not_covered(bdir):
    _formula_disagreement(bdir)
    M.decide(bdir, target_ids=["miss-0001"], decision="correct", value="SYNA", **BY)
    assert _conflict_q(Q.consolidate(M.load(bdir)), RULED)["covered_by_decisions"]  # the beamtime answer alone
    M.decide(bdir, target_ids=["cand-0072"], decision="correct", value="SYNB", **BY)
    q = _conflict_q(Q.consolidate(M.load(bdir)), RULED)
    assert "covered_by_decisions" not in q and q["affects_record"] is True  # one run, two values
    disagreements, filled = _composed(bdir)
    assert disagreements and not filled  # as the record builder sees it
    M.decide(bdir, target_ids=["cand-0072"], decision="correct", value="SYNA", **BY)
    assert len(_conflict_q(Q.consolidate(M.load(bdir)), RULED)["covered_by_decisions"]) == 2


@pytest.mark.parametrize("mate_value, covered", [("SYNB", False), ("SYNA", True)])
def test_another_run_of_its_group_decided_otherwise_keeps_the_disagreement_open(bdir, mate_value, covered):
    _formula_disagreement(bdir, mate="cand-0108")
    M.decide(bdir, target_ids=["miss-0001"], decision="correct", value="SYNA", **BY)
    M.decide(bdir, target_ids=["cand-0108"], decision="correct", value=mate_value, **BY)
    q = _conflict_q(Q.consolidate(M.load(bdir)), RULED)
    assert bool(q.get("covered_by_decisions")) is covered
    disagreements, filled = _composed(bdir)
    assert bool(disagreements) is not covered and bool(filled) is covered


# --- MED-2: a partly recorded Campaign Info row is ruled once ---------------------------------------------------------


def _held(bdir):
    b = M.load(bdir)
    held = {m["value_id"] for m in b["missing_values"] if m["target_field_path"] == FACILITY}
    latest = {}
    for d in b["scientist_decisions"]:
        if d["target"]["id"] in held:
            latest[d["target"]["id"]] = d["value"]
    return held, latest


@pytest.mark.parametrize("recorded_runs", [2, 9])
def test_a_ruling_on_a_recorded_row_records_for_every_run_without_supersede(bdir, tmp_path, capsys, recorded_runs):
    M.group(bdir)
    tids = [m["value_id"] for m in M.load(bdir)["missing_values"] if m["target_field_path"] == FACILITY]
    M.decide(bdir, target_ids=tids[:recorded_runs], decision="correct", value="SYN Lab", by="SYN Other Person", orcid=None)
    s = _their_sheet(bdir, tmp_path / "theirs.xlsx", beamline="SSRL BL15-2")
    adopted = _adopt(bdir, s, tmp_path / "A.xlsx", capsys)
    [row] = [d for d in adopted["disagreements"] if d["kind"] == "recorded"]
    assert row["readings"] == [f"recorded: 'SYN Lab' ({recorded_runs} run(s))"]
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {row["id"]: "Synthetic Light Source"})
    code, rep, err = _import(bdir, tmp_path / "Ar.xlsx", capsys, "--apply")
    assert code == 0, err
    assert not [c for c in rep["clashes"] if c["header"] == "Facility Name"]  # no --supersede needed
    over = rep["rulings_over_the_value_recorded"]
    assert sorted(x["target"]["id"] for x in over) == sorted(tids[:recorded_runs])  # each said, read back
    held, latest = _held(bdir)
    assert len(latest) == len(held) == 9 and set(latest.values()) == {"Synthetic Light Source"}


def test_a_decision_recorded_since_the_adopt_still_clashes_with_a_partly_recorded_rows_ruling(bdir, tmp_path, capsys):
    M.group(bdir)
    tids = [m["value_id"] for m in M.load(bdir)["missing_values"] if m["target_field_path"] == FACILITY]
    M.decide(bdir, target_ids=tids[:2], decision="correct", value="SYN Lab", by="SYN Other Person", orcid=None)
    s = _their_sheet(bdir, tmp_path / "theirs.xlsx", beamline="SSRL BL15-2")
    [row] = [d for d in _adopt(bdir, s, tmp_path / "A.xlsx", capsys)["disagreements"] if d["kind"] == "recorded"]
    M.decide(bdir, target_ids=tids[:1], decision="correct", value="SYN Lab North", by="SYN Other Person", orcid=None)
    _rule(tmp_path / "A.xlsx", tmp_path / "Ar.xlsx", {row["id"]: "Synthetic Light Source"})
    code, rep, err = _import(bdir, tmp_path / "Ar.xlsx", capsys, "--apply")
    assert code == 0, err
    [clash] = [c for c in rep["clashes"] if c["target"]["id"] == tids[0]]
    assert "was not made against the value recorded now" in clash["reason"]  # it never saw `SYN Lab North`
    [cell] = [c for c in rep["clashes_by_cell"] if c["header"] == "Facility Name"]
    assert cell["clashes"] == 1 and cell["held_back"] == 8  # the row's runs are held back with it: nothing flips
    _held_ids, latest = _held(bdir)
    assert latest == {tids[0]: "SYN Lab North", tids[1]: "SYN Lab"}


# --- L1: reveal finds a reading on word boundaries, a number as a number -------------------------------------------------


@pytest.mark.parametrize("said, literal, found", [
    ("0.1", "0.15 V", False), ("0.1", "-0.1 V", False), ("0.1", "10.1 V", False), ("0.1", "0.1 M KOH", True),
    ("0.10", "0.1 V", True), ("400", "400mV", True), ("KOH", "0.1 M KOH", True), ("KO", "0.1 M KOH", False),
    ("pH 2", "SYN pH 2 acid", True), ("pH 2", "SYN pH 21", False),
])
def test_reveal_finds_a_reading_in_the_literal_on_word_boundaries(said, literal, found):
    got = M._against_literals(said, [literal])
    assert got["agrees_with_literal"] is found or said.casefold() == literal.casefold()
    assert ("is found in" in got["comparison_note"]) is found


# --- L2: the shared-reading key holds every literal -------------------------------------------------------------------


def test_questions_whose_literals_differ_after_the_first_never_share_a_reading():
    lits = [["SYN-A", "SYN 1 V"], ["SYN-A", "SYN 1 V"], ["SYN-A", "SYN 2 V"], ["SYN-A", "SYN 2 V"]]
    cands = {f"c{i}": {"candidate_id": f"c{i}", "run_id": f"r{i}", "observed_literals": lits[i],
                       "evidence": [{"relative_path": f"SYN_{i}.dat"}]} for i in range(4)}
    qs = [{"question_id": f"Q-{i}", "target_field_path": "sample.material.name", "targets": [{"kind": "candidate", "id": f"c{i}"}],
           "same_reading_as": ["Q-x"], "text": "Q.", "answer_command": f"isaac bundle decide <bundle_dir> --question Q-{i} --decision confirm"}
          for i in range(4)]
    Q._note_shared_reading_groups(qs, cands, {"runs": []}, {})
    assert qs[0]["same_reading_group"] == qs[1]["same_reading_group"] != qs[2]["same_reading_group"] == qs[3]["same_reading_group"]
    assert "share this reading ('SYN 1 V', 'SYN-A', as the files write it)" in qs[0]["text"]


# --- L3: the bulk keep_apart is pinned to the candidates its reply listed -----------------------------------------------


@pytest.fixture()
def electrodes(tmp_path):
    return _grouped_stems(tmp_path, STEMS)


def test_the_bulk_keep_apart_records_only_the_candidates_its_reply_listed(electrodes, capsys):
    got = M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.NOT_COUNTER_DECISION, value=None,
                            by=WHO, orcid=None, positions=[1, 2])
    listed = got["said_not_counter_merge_candidates"]
    command = Q.keep_apart_said_not_counter_command(listed)
    assert f"`{command}`" in got["statement"] and all(f"--target {i}" in command for i in listed)
    # without the list: refused, naming the candidates and the pinned command
    with pytest.raises(M.MutationRefused, match="keeps apart exactly the merge candidates you name") as exc:
        M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.KEEP_APART_DECISION, value=None,
                          by=WHO, orcid=None)
    assert command in str(exc.value) and "Nothing was recorded." in str(exc.value)
    # one of them decided since the reply: the list changed, so nothing is recorded
    M.decide(electrodes, target_ids=[listed[0]], decision=B.KEEP_APART_DECISION, value=None, by=WHO, orcid=None)
    with pytest.raises(M.MutationRefused, match=f"no longer open and cautioned: {listed[0]}") as exc:
        M.decide_question(electrodes, question_id=Q.COUNTER_QUESTION_ID, decision=B.KEEP_APART_DECISION, value=None,
                          by=WHO, orcid=None, extra_targets=listed)
    assert Q.keep_apart_said_not_counter_command(listed[1:]) in str(exc.value)
    assert [mc["status"] for mc in M.load(electrodes)["merge_candidates"]].count("kept_apart") == 1
    # the list as it stands now: recorded, from the command line
    argv = shlex.split(Q.keep_apart_said_not_counter_command(listed[1:]).replace("<bundle_dir>", str(electrodes))
                       .replace("<your name>", WHO))
    capsys.readouterr()
    assert cli.main(argv[1:]) == 0
    assert G.said_not_counter_candidates(M.load(electrodes)) == []


# --- L4: the deprecated terms are the pinned portal validator's ---------------------------------------------------------


def _cached_validator() -> Path | None:
    """The pinned validator's source in the cache (never ``ISAAC_PORTAL_VALIDATOR_DIR``: the tests point it at a fake)."""
    root = Path("~/.cache/isaac/portal-validator").expanduser()
    found = sorted(root.glob(f"{portal.PINNED_COMMIT}*/src/portal/validation.py")) if root.is_dir() else []
    return found[0] if found else None


def test_the_deprecated_terms_are_the_ones_the_pinned_portal_validator_warns_about():
    source = _cached_validator()
    if source is None:
        pytest.skip("no cached portal validator (~/.cache/isaac/portal-validator/<pin>/src/portal/validation.py)")
    text = source.read_text(encoding="utf-8")  # read as text only: never imported or run here
    warned = {(m["path"].replace("/", "."), m["term"], m["code"]) for m in re.finditer(
        r'if \w+ == "(?P<term>[\w-]+)":\s*warnings\.append\(\{\s*"code": "(?P<code>DEPRECATED_\w+)", "path": "(?P<path>[\w/]+)"',
        text)}
    assert warned, "the validator's deprecated-term warnings were not found: read its source again"
    assert {c for c in re.findall(r'"code": "(DEPRECATED_\w+)"', text)} == {c for _p, _t, c in warned}  # none missed
    ours = {(path, term, code) for path, terms in T.DEPRECATED_TERMS.items() for term, (code, _use) in terms.items()}
    assert ours == warned
