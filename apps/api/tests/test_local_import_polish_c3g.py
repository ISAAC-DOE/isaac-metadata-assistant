"""Skill polish, cycle 3 (G): grouping says what it will do, and a merge it cannot apply changes nothing.

Found walking the skill on a real BL4-3 beamtime (none of its data is here):

* the counter answer's ``regroup_preview`` said "this answer would join none of the current groups",
  and the next regroup then combined a pending merge decision (``…_015`` + ``…_016``) the answer had
  unblocked — the scientist was told the answer did nothing. The preview now counts the merge decisions
  it would let the regroup combine, and says so; it is computed as the regroup computes it.
* a merge candidate whose groups were all rejected was still listed as ``proposed`` and its question
  could still be asked. A candidate with fewer than two LIVE groups proposes nothing: it is kept (same
  id, same stored record) but not listed by default, never asked, and ``show`` says why.
* a merge decision the regroup could NOT combine still retired its group (``merged``) and re-proposed
  the same run under a new id, so ids changed under the scientist, ``list groups`` said ``merged 1``
  although nothing merged, and the refusal's next commands named a group that was no longer live. An
  uncombined merge now leaves every group exactly as it was; the decision stays pending.

SYNTHETIC files only: the SYN counter folder and invented XDC scans dated 2099.
"""

from __future__ import annotations

import json
import shlex

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_capture_decisions import _combined, _grouped_stems
from test_local_import_merge_paths import BY, _live, _merge, _not_combined, _xdc

COUNTER_LAST = dict(target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[-1])


def _groups(b) -> list[tuple[str, str, tuple]]:
    return [(g["group_id"], g["status"], tuple(g["member_run_keys"])) for g in M.load(b)["record_groups"]]


def _live_ids(b) -> set[str]:
    return {g["group_id"] for g in _live(b)}


def _cli_json(argv, capsys) -> dict:
    capsys.readouterr()
    assert cli.main(argv) == 0
    return json.loads(capsys.readouterr().out)


# --- 3. a merge the regroup cannot combine changes nothing --------------------------------------------


def test_an_uncombined_merge_leaves_every_group_exactly_as_it_was(tmp_path, capsys):
    """The BL4-3 shape: two repeats differing in a trailing counter, no sample stated, no counter answer."""
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    before = _groups(b)
    g1, g2 = (g for g, _, _ in before)
    M.decide(b, target_ids=[g1], decision="merge", value=None, by=BY, orcid=None, merge_with=[g2])
    assert _groups(b) == before  # pending until a regroup applies it: nothing retired yet
    out = M.group(b, regroup=True)
    assert _groups(b) == before  # same ids, same status (proposed), same members, same order
    assert out["combined_by_merge_decision"] == [] and out["live_record_groups"] == 2 and out["record_groups"] == 2
    nc = _not_combined(out)
    assert nc["decision_id"] == "d-00001"
    # every group a follow-up command names is live
    named = {t for c in nc["next_commands"] for t in shlex.split(c) if t.startswith("rg-")}
    assert named and named <= _live_ids(b) and g1 in named and g2 in named
    listed = _cli_json(["bundle", "list", str(b), "groups"], capsys)
    assert listed["total"] == 2 and "not_listed" not in listed
    assert "superseded_record_groups" not in M.load(b) or not M.load(b)["superseded_record_groups"]
    assert not any("reproposed" in json.dumps(g) for g in M.load(b)["record_groups"])
    # again: stable, still pending, still reported, no new id
    again = M.group(b, regroup=True)
    assert _groups(b) == before and [x["decision_id"] for x in again["merge_decisions_not_combined"]] == ["d-00001"]
    [mc] = [m for m in M.load(b)["merge_candidates"] if "scientist_decided_merge" in m.get("reason_codes", ())]
    assert sorted(mc["group_ids"]) == sorted([g1, g2])
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_the_pending_merge_is_applied_once_its_blocker_is_answered_and_its_group_becomes_history(tmp_path):
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    g1, g2 = (g for g, _, _ in _groups(b))
    _merge(b, g1, [g2])
    M.decide(b, **COUNTER_LAST)
    out = M.group(b, regroup=True)
    [done] = out["combined_by_merge_decision"]
    assert done["decision_id"] == "d-00001" and sorted(done["from_groups"]) == sorted([g1, g2])
    statuses = {gid: s for gid, s, _ in _groups(b)}
    assert statuses[g1] == "merged" and g2 not in statuses and statuses[done["group_id"]] == "proposed"
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_a_rejected_combination_puts_the_merged_group_back_unchanged(tmp_path):
    """The combined group rejected: the merge decision's group is live again under its own id (it no longer
    has anywhere else to be), and the regroup does not propose that combination again."""
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    before = _groups(b)
    g1, g2 = (g for g, _, _ in before)
    M.decide(b, **COUNTER_LAST)
    M.group(b, regroup=True)
    assert _groups(b) == before  # the counter answer alone joins nothing here (no sample stated)
    _merge(b, g1, [g2])
    [c] = _combined(b)
    M.decide(b, target_ids=[c["group_id"]], decision="reject", value=None, by=BY, orcid=None)
    assert {gid: s for gid, s, _ in _groups(b)}[g1] == "proposed"
    out = M.group(b, regroup=True)
    assert any("already decided (rejected)" in x["reason"] for x in out["merge_decisions_not_combined"])
    assert _live_ids(b) == {g1, g2}
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_an_older_bundle_holding_a_reproposed_group_still_checks_and_heals_on_regroup(tmp_path):
    """Before this fix the regroup retired the merged group and re-proposed its run under a new id
    (``reproposed_after_group_id``). Such a bundle still validates (the merged group's run is held by the
    re-proposed group, so it stays `merged`), and the next regroup gives the run its own id back."""
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    before = _groups(b)
    g1, g2 = (g for g, _, _ in before)
    M.decide(b, target_ids=[g1], decision="merge", value=None, by=BY, orcid=None, merge_with=[g2])
    bundle = M.load(b)
    old = next(g for g in bundle["record_groups"] if g["group_id"] == g1)
    twin = json.loads(json.dumps(old))
    twin.update(group_id="rg-0123456789abcdef", reproposed_after_group_id=g1, status="proposed",
                flags=list(old.get("flags") or []) + ["reproposed_after_merge_decision"])
    bundle["record_groups"].append(twin)
    M.save_bundle(b, bundle)
    stored = {gid: s for gid, s, _ in _groups(b)}
    assert stored[g1] == "merged" and stored["rg-0123456789abcdef"] == "proposed"
    assert cli.main(["bundle", "check", str(b)]) == 0
    M.group(b, regroup=True)
    assert _groups(b) == before


# --- 1. the counter answer's preview counts the merges it unblocks ------------------------------------


def test_the_counter_preview_counts_the_merge_decision_it_unblocks_and_the_regroup_does_exactly_that(tmp_path, capsys):
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    g1, g2 = (g for g, _, _ in _groups(b))
    _not_combined(_merge(b, g1, [g2]))
    reply = _cli_json(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions",
                       "--positions", "last", "--by", BY], capsys)
    preview = reply["regroup_preview"]
    assert preview["groups_joined"] == 0  # the naming rule alone joins nothing (no sample stated) ...
    [unblocked] = preview["merge_decisions_unblocked"]  # ... but the pending merge can now be applied
    assert unblocked["decision_id"] == "d-00001" and sorted(unblocked["group_ids"]) == sorted([g1, g2])
    assert "join none" not in preview["statement"]
    assert "1 pending merge decision (d-00001" in preview["statement"] and g1 in preview["statement"]
    assert len(M.load(b)["record_groups"]) == 2  # a preview: nothing regrouped
    out = M.group(b, regroup=True)
    assert [(x["decision_id"], sorted(x["from_groups"]), x["group_id"]) for x in out["combined_by_merge_decision"]] == [
        (unblocked["decision_id"], sorted(unblocked["group_ids"]), unblocked["combined_group_id"])]


def test_the_counter_preview_does_not_count_a_merge_that_combines_without_it(tmp_path):
    """A pending merge the regroup applies anyway (a repeat marker) is not the answer's doing."""
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_again", "Q4_SYNcat_pH2_500mV"])
    g = [gid for gid, _, _ in _groups(b)]
    M.decide(b, target_ids=[g[0]], decision="merge", value=None, by=BY, orcid=None, merge_with=[g[1]])
    preview = M.decide(b, **COUNTER_LAST)["regroup_preview"]
    assert preview["merge_decisions_unblocked"] == []
    assert "merge decision" not in preview["statement"]


def test_the_counter_preview_of_an_answer_that_unblocks_nothing_is_unchanged(tmp_path):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV_15", "Q4_SYNcat_pH2_400mV_16"])
    preview = M.decide(b, **COUNTER_LAST)["regroup_preview"]
    assert preview["groups_joined"] == 2 and preview["merge_decisions_unblocked"] == []
    assert preview["statement"] == ("On the next regroup (`isaac bundle group <bundle_dir> --regroup`) this answer would "
                                    "join 2 of the current groups into 1. Nothing is regrouped until then; tell the "
                                    "scientist before regrouping.")


# --- 2. a merge candidate with fewer than two live groups proposes nothing -----------------------------


def _three_group_candidate(tmp_path):
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV", "Q4_04_SYNcat_pH2_400mV"])
    [mc] = M.load(b)["merge_candidates"]
    assert len(mc["group_ids"]) == 3
    return b, mc


def test_a_candidate_with_one_live_group_is_kept_but_not_listed_and_not_asked(tmp_path, capsys):
    from isaac_api.local_bundles import capture_items

    b, mc = _three_group_candidate(tmp_path)
    mcid = mc["merge_candidate_id"]
    first, second, third = mc["group_ids"]
    M.decide(b, target_ids=[first], decision="reject", value=None, by=BY, orcid=None)
    # two live groups left: it still proposes a merge
    assert [i["merge_candidate_id"] for i in _cli_json(["bundle", "list", str(b), "merge-candidates"], capsys)["items"]] == [mcid]
    M.decide(b, target_ids=[second], decision="reject", value=None, by=BY, orcid=None)
    listed = _cli_json(["bundle", "list", str(b), "merge-candidates"], capsys)
    assert listed["total"] == 0 and listed["items"] == []
    assert listed["not_listed"] == {"fewer_than_two_live_groups": 1} and "--all" in listed["not_listed_note"]
    every = _cli_json(["bundle", "list", str(b), "merge-candidates", "--all"], capsys)
    assert [i["merge_candidate_id"] for i in every["items"]] == [mcid] and "not_listed" not in every
    # kept: same id, same stored record (status as the grouping step wrote it)
    stored = next(m for m in M.load(b)["merge_candidates"] if m["merge_candidate_id"] == mcid)
    assert {k: v for k, v in stored.items()} == {k: v for k, v in mc.items()}
    shown = _cli_json(["bundle", "show", str(b), "merge-candidate", mcid], capsys)
    assert shown["question"] is None and shown["answer_with"] == []
    assert "1 of its 3 groups is live" in shown["proposes_nothing"] and "2 rejected" in shown["proposes_nothing"]
    # never asked: not in the group's questions, not on the questions screen
    group = _cli_json(["bundle", "show", str(b), "group", third], capsys)
    assert not [q for q in group["questions"] if q.get("merge_candidate_id") == mcid]
    assert capture_items(M.load(b))["merge_candidates"] == []
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_a_live_candidate_is_shown_and_asked_as_before(tmp_path, capsys):
    from isaac_api.local_bundles import capture_items

    b, mc = _three_group_candidate(tmp_path)
    shown = _cli_json(["bundle", "show", str(b), "merge-candidate", mc["merge_candidate_id"]], capsys)
    assert shown["question"] == mc["question"]["text"] and shown["answer_with"] and "proposes_nothing" not in shown
    assert [m["merge_candidate_id"] for m in capture_items(M.load(b))["merge_candidates"]] == [mc["merge_candidate_id"]]
    group = _cli_json(["bundle", "show", str(b), "group", mc["group_ids"][0]], capsys)
    assert [q for q in group["questions"] if q.get("merge_candidate_id") == mc["merge_candidate_id"]]


def _older_build_pending_merge(tmp_path):
    """What a build before this fix wrote after `decide --decision merge` and before the regroup: the merge
    decision alone made the group `merged` (the format version is the same, 1.9.0)."""
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    before = _groups(b)
    g1, g2 = (g for g, _, _ in before)
    M.decide(b, target_ids=[g1], decision="merge", value=None, by=BY, orcid=None, merge_with=[g2])
    data = json.loads((b / "bundle.json").read_text())
    next(g for g in data["record_groups"] if g["group_id"] == g1)["status"] = "merged"
    (b / "bundle.json").write_text(json.dumps(data, indent=1))
    return b, before, g1, g2


def test_an_older_builds_merged_status_for_a_pending_merge_is_valid_history(tmp_path, capsys):
    b, before, g1, g2 = _older_build_pending_merge(tmp_path)
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(b)]) == 0
    said = capsys.readouterr().out
    assert said.startswith("VALID:") and "INVALID" not in said and "STALE" not in said
    assert (f"1 record group(s) ({g1}) are stored as merged by an older build, for a merge decision no regroup has "
            "applied yet: valid history.") in said
    assert "the next change to the bundle rewrites them so" in said and "--regroup" in said
    assert B.validate_bundle(json.loads((b / "bundle.json").read_text())) == []
    # a real status mismatch is still an error
    data = json.loads((b / "bundle.json").read_text())
    next(g for g in data["record_groups"] if g["group_id"] == g2)["status"] = "merged"
    assert any(f"record group {g2} is merged" in e for e in B.validate_bundle(data))


def test_every_command_reads_the_older_bundle_and_the_next_save_rewrites_it(tmp_path, capsys):
    b, before, g1, g2 = _older_build_pending_merge(tmp_path)
    for argv in (["bundle", "list", str(b), "groups", "--all"], ["bundle", "list", str(b), "merge-candidates"],
                 ["bundle", "show", str(b), "group", g1], ["bundle", "questions", str(b)], ["bundle", "list", str(b), "runs"]):
        assert cli.main(argv) == 0, argv
    assert cli.main(["bundle", "check", str(b)]) == 0
    # the next save (any decision) rewrites the status by this build's rule: proposed, the merge pending
    M.decide(b, target_ids=["experiment"], decision="set_clock_time_zone", value="UTC", by=BY, orcid=None)
    assert _groups(b) == before
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(b)]) == 0
    assert "stored as merged by an older build" not in capsys.readouterr().out
    # and the regroup applies the merge or says why not, under the same ids
    out = M.group(b, regroup=True)
    assert _groups(b) == before and [x["decision_id"] for x in out["merge_decisions_not_combined"]] == ["d-00001"]


def test_the_regroup_reads_the_older_status_directly(tmp_path):
    b, before, g1, g2 = _older_build_pending_merge(tmp_path)
    out = M.group(b, regroup=True)
    assert _groups(b) == before and [x["decision_id"] for x in out["merge_decisions_not_combined"]] == ["d-00001"]
    assert cli.main(["bundle", "check", str(b)]) == 0
