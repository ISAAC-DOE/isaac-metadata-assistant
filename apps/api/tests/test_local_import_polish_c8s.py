"""Polish c8-s: a split decision makes exactly the groups the scientist named. Synthetic only.

Found by a docs review, then measured: ``decide --decision split --split-into '[[…],[…]]'`` stored the lists
on the decision and nothing read them back. The split group became history (``split``) and its runs were
proposed afresh on the next regroup — and since the fresh proposal was identical to the split group, it was
skipped as "already ruled on": a 3-run group split 2+1 left its three runs in NO live group at all.

What these pin:

* a split makes ONE proposed group per list at once (the decide reply names them), each id derived like every
  other group id (``grouping.group_id_for`` over its runs and ``split-from:<group id>``), so it is stable;
* a regroup keeps the parts exactly as named, the way a confirmed group or a merge decision is kept: a counter
  answer cannot join them, no merge candidate re-asks them, and every other group keeps its id;
* each part is then confirmed (or merged, rejected, split again) on its own;
* a split whose lists do not cover exactly the group's runs, overlap, name an unknown run key, or make fewer than
  two groups is refused with a plain message and nothing recorded;
* an older bundle that holds a split decision with no resulting groups gets them on the next regroup, said plainly.

SYNTHETIC files only: the SYN counter folder with invented stems.
"""

from __future__ import annotations

import json
import shutil

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_capture_decisions import _grouped_stems

BY = "SYNTHETIC TEST"
S02, S02A, S03, S04 = ("Q4_02_SYNcat_pH2_400mV", "Q4_02_SYNcat_pH2_400mV_again", "Q4_03_SYNcat_pH2_400mV",
                       "Q4_04_SYNcat_pH2_400mV")


@pytest.fixture(scope="module")
def three_base(tmp_path_factory):
    """ONE proposed group of three runs (the counter answer joins ``Q4_02/03/04``)."""
    b = _grouped_stems(tmp_path_factory.mktemp("c8s-three"), [S02, S03, S04])
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    M.group(b, regroup=True)
    [g] = _live(b)
    assert len(g["member_run_keys"]) == 3
    return b


@pytest.fixture(scope="module")
def four_base(tmp_path_factory):
    """A 2-run group (``Q4_02`` and its ``_again`` repeat), ``Q4_03`` and ``Q4_04`` alone, and ONE merge candidate
    naming all three groups (the counter question, unanswered)."""
    b = _grouped_stems(tmp_path_factory.mktemp("c8s-four"), [S02, S02A, S03, S04])
    assert [len(g["member_run_keys"]) for g in _live(b)] == [2, 1, 1]
    [mc] = M.load(b)["merge_candidates"]
    assert len(mc["group_ids"]) == 3
    return b


@pytest.fixture()
def three(three_base, tmp_path):
    shutil.copytree(three_base, tmp_path / "three")
    return tmp_path / "three"


@pytest.fixture()
def four(four_base, tmp_path):
    shutil.copytree(four_base, tmp_path / "four")
    return tmp_path / "four"


def _live(b) -> list[dict]:
    return [g for g in M.load(b)["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES]


def _key(b, stem: str) -> str:
    return next(r["run_key"] for r in M.load(b)["runs"] if r["stem"] == stem)


def _group_with(b, stem: str) -> dict:
    k = _key(b, stem)
    return next(g for g in _live(b) if k in g["member_run_keys"])


def _stems(b, g) -> list[str]:
    stem = {r["run_key"]: r["stem"] for r in M.load(b)["runs"]}
    return sorted(stem[k] for k in g["member_run_keys"])


def _split(b, gid: str, lists) -> dict:
    keys = [[_key(b, s) for s in part] for part in lists]
    return M.decide(b, target_ids=[gid], decision="split", value=None, by=BY, orcid=None, split_into=keys)


def _part_id(b, parent: str, stems) -> str:
    return G.group_id_for(G.experiment_key_of(M.load(b)), [_key(b, s) for s in stems] + [f"split-from:{parent}"])


def _layout(b) -> list[tuple]:
    """Every group: id, status, its runs' stems (what a scientist sees)."""
    return [(g["group_id"], g["status"], _stems(b, g)) for g in M.load(b)["record_groups"]]


def _one_live_group_per_run(b) -> None:
    held = [k for g in _live(b) for k in g["member_run_keys"]]
    assert sorted(held) == sorted(r["run_key"] for r in M.load(b)["runs"]), "a run is in no live group, or in two"


def _check(b) -> None:
    assert cli.main(["bundle", "check", str(b)]) == 0


# --- the measured defect ------------------------------------------------------------------------------


def test_a_split_makes_one_proposed_group_per_list_and_the_reply_names_them(three):
    [g] = _live(three)
    out = _split(three, g["group_id"], [[S02, S03], [S04]])
    p1, p2 = _part_id(three, g["group_id"], [S02, S03]), _part_id(three, g["group_id"], [S04])
    assert [x["group_id"] for x in out["split_into_groups"]] == [p1, p2]
    assert [len(x["member_run_keys"]) for x in out["split_into_groups"]] == [2, 1]
    assert p1 in out["statement"] and p2 in out["statement"] and "confirm each" in out["statement"]
    assert out["recorded"] == [g["group_id"]]
    layout = _layout(three)
    assert (g["group_id"], "split", [S02, S03, S04]) in layout
    assert [(gid, st, s) for gid, st, s in layout if st == "proposed"] == [(p1, "proposed", [S02, S03]),
                                                                          (p2, "proposed", [S04])]
    made = {x["group_id"]: x for x in M.load(three)["record_groups"]}
    assert made[p1]["split_by_decision"]["split_group_id"] == g["group_id"]
    assert made[p1]["split_by_decision"]["decision_id"] == out_decision_id(three, g["group_id"])
    assert "split_by_scientist_decision" in made[p1]["flags"]
    _one_live_group_per_run(three)
    _check(three)


def out_decision_id(b, gid: str) -> str:
    return B._decisions_by_target(M.load(b)["scientist_decisions"])[("record_group", gid)]["decision_id"]


def test_a_regroup_keeps_the_parts_exactly_as_named(three):
    """Before: the regroup proposed the three runs afresh, skipped that proposal as identical to the split group,
    and left the three runs in no live group."""
    [g] = _live(three)
    _split(three, g["group_id"], [[S02, S03], [S04]])
    after_decide = _layout(three)
    for _ in range(2):
        out = M.group(three, regroup=True)
        assert _layout(three) == after_decide
        _one_live_group_per_run(three)
    [applied] = out["splits_applied"]
    assert applied["group_id"] == g["group_id"] and applied["applied_now"] is False
    assert [x["group_id"] for x in applied["groups"]] == [_part_id(three, g["group_id"], [S02, S03]),
                                                          _part_id(three, g["group_id"], [S04])]
    _check(three)


def test_each_part_is_confirmed_on_its_own_and_a_regroup_keeps_it(three):
    [g] = _live(three)
    out = _split(three, g["group_id"], [[S02, S03], [S04]])
    p1, p2 = (x["group_id"] for x in out["split_into_groups"])
    M.decide(three, target_ids=[p1], decision="confirm", value=None, by=BY, orcid=None)
    M.group(three, regroup=True)
    status = {gid: st for gid, st, _ in _layout(three)}
    assert status[p1] == "scientist_confirmed" and status[p2] == "proposed"
    M.decide(three, target_ids=[p2], decision="confirm", value=None, by=BY, orcid=None)
    M.group(three, regroup=True)
    assert [(gid, st) for gid, st, _ in _layout(three) if st in B.LIVE_GROUP_STATUSES] == [
        (p1, "scientist_confirmed"), (p2, "scientist_confirmed")]
    _one_live_group_per_run(three)
    _check(three)


# --- refusals: plain, and nothing recorded ----------------------------------------------------------


@pytest.mark.parametrize(("lists", "said"), [
    (None, "--split-into"),
    ([[S02, S03, S04]], "at least two"),
    ([[S02, S03], []], "empty"),
    ([[S02], [S03]], "leave out"),
    ([[S02, S03], [S03, S04]], "more than one"),
    ([[S02, S03], [S04, "SYN_nope@sha256:00"]], "no run of this bundle"),
])
def test_a_split_that_does_not_name_exactly_the_groups_runs_is_refused(three, lists, said):
    [g] = _live(three)
    before = (three / "bundle.json").read_bytes()
    keys = None if lists is None else [[_key(three, s) if not s.startswith("SYN_nope") else s for s in part] for part in lists]
    with pytest.raises(M.MutationRefused) as refused:
        M.decide(three, target_ids=[g["group_id"]], decision="split", value=None, by=BY, orcid=None, split_into=keys)
    assert said in str(refused.value) and "Nothing was recorded" in str(refused.value)
    assert (three / "bundle.json").read_bytes() == before


def test_a_split_naming_a_run_of_another_group_is_refused(four):
    a = _group_with(four, S02)
    before = (four / "bundle.json").read_bytes()
    with pytest.raises(M.MutationRefused) as refused:
        _split(four, a["group_id"], [[S02], [S02A, S03]])
    assert f"not a run of group {a['group_id']}" in str(refused.value)
    assert (four / "bundle.json").read_bytes() == before


def test_the_cli_says_the_groups_a_split_made_and_refuses_plainly(three, capsys):
    [g] = _live(three)
    lists = json.dumps([[_key(three, S02), _key(three, S03)], [_key(three, S04)]])
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(three), "--target", g["group_id"], "--decision", "split",
                     "--split-into", json.dumps([[_key(three, S02)], [_key(three, S03)]]), "--by", BY]) == 2
    err = capsys.readouterr().err
    assert "leave out" in err and "Nothing was recorded" in err
    assert cli.main(["bundle", "decide", str(three), "--target", g["group_id"], "--decision", "split",
                     "--split-into", lists, "--by", BY]) == 0
    reply = json.loads(capsys.readouterr().out)
    assert [len(x["member_run_keys"]) for x in reply["split_into_groups"]] == [2, 1]


def test_a_split_group_is_not_split_again_but_its_part_is(three):
    [g] = _live(three)
    out = _split(three, g["group_id"], [[S02, S03], [S04]])
    p1 = out["split_into_groups"][0]["group_id"]
    with pytest.raises(M.MutationRefused) as refused:
        _split(three, g["group_id"], [[S02], [S03, S04]])
    assert p1 in str(refused.value)
    again = _split(three, p1, [[S02], [S03]])
    q1, q2 = (x["group_id"] for x in again["split_into_groups"])
    assert (q1, q2) == (_part_id(three, p1, [S02]), _part_id(three, p1, [S03]))
    layout = _layout(three)
    M.group(three, regroup=True)
    assert _layout(three) == layout
    assert sorted(s for _, st, s in layout if st == "proposed") == [[S02], [S03], [S04]]
    _one_live_group_per_run(three)
    _check(three)


# --- interactions -----------------------------------------------------------------------------------


def test_a_counter_answer_after_a_split_does_not_join_its_parts(four):
    """``Q4_02`` and ``Q4_02_again`` split apart; the counter answer then joins ``Q4_03``/``Q4_04`` — and over the
    whole bundle it would have joined all four runs, the split parts with them."""
    a = _group_with(four, S02)
    out = _split(four, a["group_id"], [[S02], [S02A]])
    p1, p2 = (x["group_id"] for x in out["split_into_groups"])
    M.decide(four, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    M.group(four, regroup=True)
    live = [(gid, s) for gid, st, s in _layout(four) if st == "proposed"]
    assert (p1, [S02]) in live and (p2, [S02A]) in live
    assert [S03, S04] in [s for _, s in live]
    assert all(set(mc["group_ids"]).isdisjoint({p1, p2}) for mc in M.load(four)["merge_candidates"])
    _one_live_group_per_run(four)
    _check(four)


def test_a_part_merged_with_another_group_is_combined_and_the_other_part_stays(four):
    a = _group_with(four, S02)
    out = _split(four, a["group_id"], [[S02], [S02A]])
    p1, p2 = (x["group_id"] for x in out["split_into_groups"])
    M.decide(four, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    M.group(four, regroup=True)
    g34 = _group_with(four, S03)
    M.decide(four, target_ids=[p2], decision="merge", value=None, by=BY, orcid=None, merge_with=[g34["group_id"]])
    reply = M.group(four, regroup=True)
    [combined] = reply["combined_by_merge_decision"]
    layout = _layout(four)
    assert (combined["group_id"], "proposed", [S02A, S03, S04]) in layout
    assert (p1, "proposed", [S02]) in layout and (p2, "merged", [S02A]) in layout
    M.group(four, regroup=True)
    assert _layout(four) == layout
    M.decide(four, target_ids=[combined["group_id"]], decision="confirm", value=None, by=BY, orcid=None)
    M.group(four, regroup=True)
    status = {gid: st for gid, st, _ in _layout(four)}
    assert status[combined["group_id"]] == "scientist_confirmed" and status[p1] == "proposed" and status[p2] == "merged"
    _one_live_group_per_run(four)
    _check(four)


def test_a_split_of_a_group_a_merge_candidate_names_is_never_re_asked(four):
    a = _group_with(four, S02)
    [mc] = M.load(four)["merge_candidates"]
    assert a["group_id"] in mc["group_ids"]
    out = _split(four, a["group_id"], [[S02], [S02A]])
    parts = {x["group_id"] for x in out["split_into_groups"]}
    b = M.load(four)
    assert all(set(m["group_ids"]).isdisjoint(parts) for m in b["merge_candidates"])
    assert all(not g.get("merge_candidate_ids") for g in b["record_groups"] if g["group_id"] in parts)
    M.group(four, regroup=True)
    b = M.load(four)
    for m in b["merge_candidates"]:
        assert a["group_id"] not in m["group_ids"] and set(m["group_ids"]).isdisjoint(parts)
    _one_live_group_per_run(four)
    _check(four)


# --- an older bundle: a split decision with no groups --------------------------------------------------


def _as_an_older_build_left_it(b, gid: str) -> None:
    """What a build before c8-s wrote: the split decision (with its lists), the group ``split``, and no parts."""
    data = M.load(b)
    data["record_groups"] = [g for g in data["record_groups"] if (g.get("split_by_decision") or {}).get("split_group_id") != gid]
    M.save_bundle(b, data)


def test_an_older_split_with_no_groups_is_applied_on_the_next_regroup_and_nothing_else_moves(four, tmp_path):
    a = _group_with(four, S02)
    out = _split(four, a["group_id"], [[S02], [S02A]])
    named = [x["group_id"] for x in out["split_into_groups"]]
    shutil.copytree(four, tmp_path / "this-build")  # what this build's decide leaves
    _as_an_older_build_left_it(four, a["group_id"])
    others = {g["group_id"]: g["member_run_keys"] for g in M.load(four)["record_groups"]}
    reply = M.group(four, regroup=True)
    [applied] = reply["splits_applied"]
    assert applied["applied_now"] is True and [x["group_id"] for x in applied["groups"]] == named
    assert "applied now" in applied["statement"] and all(x in applied["statement"] for x in named)
    assert applied["statement"] in reply["statement"]
    after = M.load(four)
    ids = {g["group_id"]: g["member_run_keys"] for g in after["record_groups"]}
    assert all(ids[gid] == keys for gid, keys in others.items())  # every other group: the same id, the same runs
    assert set(ids) == set(others) | set(named)
    # exactly where this build lands after the same regroup: the same groups, merge candidates and question ids
    M.group(tmp_path / "this-build", regroup=True)
    mine = M.load(tmp_path / "this-build")
    assert _layout(four) == _layout(tmp_path / "this-build")
    assert [m["merge_candidate_id"] for m in after["merge_candidates"]] == [m["merge_candidate_id"] for m in mine["merge_candidates"]]
    assert {q["question_id"] for q in Q.consolidate(after)["questions"]} == {q["question_id"] for q in Q.consolidate(mine)["questions"]}
    _one_live_group_per_run(four)
    _check(four)


def test_an_older_split_with_no_lists_is_said_plainly_and_can_be_decided_again(three):
    [g] = _live(three)
    data = M.load(three)
    data["scientist_decisions"].append({
        "decision_id": f"d-{len(data['scientist_decisions']) + 1:05d}", "target": {"kind": "record_group", "id": g["group_id"]},
        "decision": "split", "value": None, "chosen_reading_index": None,
        "decided_by": {"name": BY, "basis": "self_reported_local_user", "identity": "local_unverified", "orcid_claimed": None},
        "decided_utc": "2099-01-01T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None})
    M.save_bundle(three, data)
    reply = M.group(three, regroup=True)
    [nope] = reply["split_decisions_not_applied"]
    assert nope["group_id"] == g["group_id"] and "--split-into" in nope["reason"]
    assert any("--decision split --split-into" in c for c in nope["next_commands"])
    out = _split(three, g["group_id"], [[S02, S03], [S04]])
    assert [len(x["member_run_keys"]) for x in out["split_into_groups"]] == [2, 1]
    M.group(three, regroup=True)
    _one_live_group_per_run(three)
    _check(three)
