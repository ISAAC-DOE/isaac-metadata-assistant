"""Skill polish, cycle 1 (G): a scientist's explicit merge always has a path that works.

Found walking the skill on real beamtimes (none of their data is here):

* a merge of two repeat runs differing only in a trailing counter (``…_015`` / ``…_016``) was
  refused, and the counter answer the refusal sent the scientist to changed nothing — the runs state
  no sample, so the grouping step never joins them itself, and the merge check ignored the answer;
* ``04_…_again`` beside ``03_…`` was refused even after the counter question was answered;
* a counter that is always the LAST token sits at a different position in names of different length;
* a merged group's leftover was listed as a group (62 groups for 61 runs), one pair appeared in two
  merge candidates, and a candidate proposed one record of runs whose names state different samples.

What these pin: a merge is honoured when the names differ only at positions the scientist declared
counters (``--positions last`` included), only in a repeat marker, or when the scientist confirmed the
same sample for every run; runs whose conditions differ are never combined. Every refusal names
commands, and following them is tested here.

SYNTHETIC files only: the SYN counter folder and invented XDC scans dated 2099.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_capture_decisions import _combined, _grouped_stems
from test_local_import_xdc_start_time import _import, stamp

BY = "SYNTHETIC TEST"
SAMPLE = "SYN sample"


def _xdc(tmp_path: Path, stems) -> Path:
    """Beamline 4-3 style XDC runs (no source states the sample), grouped."""
    out = _import(tmp_path, {f"{s}.001": stamp("2099-07-14T10:23:45") for s in stems})
    M.group(out)
    return out


def _live(b: Path) -> list[dict]:
    return [g for g in M.load(b)["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES]


def _merge(b: Path, target: str, others) -> dict:
    M.decide(b, target_ids=[target], decision="merge", value=None, by=BY, orcid=None, merge_with=list(others))
    return M.group(b, regroup=True)


def _follow(b: Path, commands, capsys) -> None:
    """Run each command a refusal named, with only its placeholders filled in."""
    assert commands
    for command in commands:
        argv = shlex.split(command.replace("<bundle_dir>", str(b)).replace("<your name>", BY).replace("<the sample>", SAMPLE))
        assert argv[0] == "isaac", command
        assert cli.main(argv[1:]) == 0, command
    capsys.readouterr()


def _not_combined(out: dict) -> dict:
    [nc] = out["merge_decisions_not_combined"]
    assert nc["next_commands"], nc
    for c in nc["next_commands"]:
        assert f"`{c}`" in nc["reason"]  # the reason names exactly the commands it lists
    return nc


# --- 1. the dead end: counters, repeat markers, the same sample -------------------------------------


@pytest.mark.parametrize("answer", ["named", "last"])
def test_a_counter_only_merge_refused_then_honoured_by_following_the_refusal(tmp_path, capsys, answer):
    """BL4-3 shape: runs differing only in a trailing counter, no sample stated. The refusal names the
    counter answer; following it (by position, or `last`) and regrouping combines the runs."""
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    g1, g2 = M.load(b)["record_groups"]
    assert all(s["code"] == "sample_identity_not_stated" for g in (g1, g2) for s in g["split_reasons"])
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "token 4 (015 / 016)" in nc["reason"]
    counter = [c for c in nc["next_commands"] if "set_counter_positions" in c]
    assert counter == ['isaac bundle decide <bundle_dir> --target experiment --decision set_counter_positions '
                       '--positions last --by "<your name>"']
    if answer == "named":
        counter = [counter[0].replace("--positions last", "--positions 4")]
    _follow(b, counter, capsys)
    out = M.group(b, regroup=True)
    assert out["merge_decisions_not_combined"] == []
    [c] = _combined(b)
    assert sorted(c["member_run_keys"]) == sorted(g1["member_run_keys"] + g2["member_run_keys"])
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_a_counter_answer_given_before_the_merge_is_honoured(tmp_path):
    """The real tester's order: counter positions answered first (3..10), then the merge."""
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None,
             positions=[3, 4, 5, 6, 7, 8, 9, 10])
    M.group(b, regroup=True)
    g1, g2 = _live(b)
    out = _merge(b, g1["group_id"], [g2["group_id"]])
    assert out["merge_decisions_not_combined"] == [] and len(_combined(b)) == 1


@pytest.mark.parametrize("marker", ["again", "repeat", "again_2", "redo"])  # a glued rep2 is a replicate (merge_conditions)
def test_names_differing_only_in_a_repeat_marker_are_combined(tmp_path, marker):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", f"Q4_SYNcat_pH2_400mV_{marker}"])
    g1, g2 = M.load(b)["record_groups"]
    out = _merge(b, g2["group_id"], [g1["group_id"]])
    assert out["merge_decisions_not_combined"] == [] and len(_combined(b)) == 1
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_a_repeat_beside_a_not_counter_number_is_honoured_once_the_sample_is_confirmed(tmp_path, capsys):
    """BL15-2 shape: `03_…` beside `04_…_again`, the scientist having said the leading number is NOT a
    counter. The refusal does not send them to the counter answer they contradicted; it names the
    sample confirmation and the statement that 02 / 03 are labels, not conditions, and following them
    combines the runs."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV_again"])
    M.decide(b, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by=BY, orcid=None, positions=[2])
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "token 2 (02 / 03)" in nc["reason"] and "set_counter_positions" not in nc["reason"]
    *samples, ack = nc["next_commands"]
    assert len(samples) == 2 and all("--decision correct --value" in c for c in samples)
    assert "--decision merge" in ack and "--same-conditions" in ack and "the names differ in: 02 / 03" in nc["reason"]
    _follow(b, nc["next_commands"], capsys)
    out = M.group(b, regroup=True)
    assert out["merge_decisions_not_combined"] == [] and len(_combined(b)) == 1
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_a_counter_shaped_difference_offers_both_paths_and_either_works(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV_again"])
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert any("--positions 2 " in c for c in nc["next_commands"])
    _follow(b, [c for c in nc["next_commands"] if "set_counter_positions" in c], capsys)
    M.group(b, regroup=True)
    assert [len(g["member_run_keys"]) for g in _live(b)] == [2]  # joined (by the grouping step or the merge)


def test_word_differences_are_honoured_only_with_the_same_confirmed_sample(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_newspot"])
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "set_counter_positions" not in nc["reason"]  # a word is no counter: that path would not work
    _follow(b, nc["next_commands"], capsys)
    assert M.group(b, regroup=True)["merge_decisions_not_combined"] == [] and len(_combined(b)) == 1


def test_different_confirmed_samples_keep_a_merge_apart_and_name_a_working_step(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_newspot"])
    bun = M.load(b)
    for run, value in zip(bun["runs"], ("SYN one", "SYN two")):
        vid = next(m["value_id"] for m in bun["missing_values"]
                   if m["target_field_path"] == "sample.material.name" and m["run_id"] == run["run_id"])
        M.decide(b, target_ids=[vid], decision="correct", value=value, by=BY, orcid=None)
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "sample.material.name" in nc["reason"] and _combined(b) == []
    _follow(b, nc["next_commands"], capsys)  # keep them apart: confirm each group on its own
    assert sorted(g["status"] for g in _live(b)) == ["scientist_confirmed", "scientist_confirmed"]


def test_runs_whose_conditions_differ_are_never_combined_whatever_is_confirmed(tmp_path, capsys):
    """The refusal stays, worded plainly, and its next step (keep them apart) works."""
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_500mV"])
    bun = M.load(b)
    for m in bun["missing_values"]:
        if m["target_field_path"] == "sample.material.name":
            M.decide(b, target_ids=[m["value_id"]], decision="correct", value=SAMPLE, by=BY, orcid=None)
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[-1])
    M.group(b, regroup=True)
    g1, g2 = _live(b)
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "different conditions" in nc["reason"] and "never combined" in nc["reason"]
    assert _combined(b) == []
    _follow(b, nc["next_commands"], capsys)
    assert sorted(g["status"] for g in _live(b)) == ["scientist_confirmed", "scientist_confirmed"]


def test_a_confirmed_sample_does_not_combine_names_stating_different_conditions(tmp_path):
    """A number-with-unit token (a potential, loading, temperature …) the build did not classify still
    keeps the runs apart, even with the same sample confirmed."""
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    for m in M.load(b)["missing_values"]:
        if m["target_field_path"] == "sample.material.name":
            M.decide(b, target_ids=[m["value_id"]], decision="correct", value=SAMPLE, by=BY, orcid=None)
    bundle = M.load(b)
    h1, h2 = bundle["record_groups"]
    combined = M._combine_for_merge([h1, h2], {"decision_id": "d-99999", "decided_by": {"name": BY}}, h1["group_id"], "exp")
    assert M._merge_blockers(bundle, {}, [h1, h2], combined)  # the same sample alone: the names still differ (015 / 016)
    said = {"decision_id": "d-99999", "decided_by": {"name": BY}, "same_conditions_tokens": ["015", "016"]}
    assert M._merge_blockers(bundle, {}, [h1, h2], combined, said) == []  # the same sample AND the same conditions
    for run, stem in zip(bundle["runs"], ("SYN_MOFdry_0p5wt", "SYN_MOFdry_5wt")):  # as if the names stated a loading
        run["stem"] = stem
    reasons = M._merge_blockers(bundle, {}, [h1, h2], combined, said)
    assert any("state different conditions (0p5wt / 5wt)" in r for r in reasons), reasons


# --- 2. "the last token is a counter" -----------------------------------------------------------------


def test_last_is_a_counter_in_names_of_different_length_where_fixed_positions_are_not(tmp_path):
    stems = ["Q4_SYNcat_pH2_400mV_15", "Q4_SYNcat_pH2_400mV_16", "Q4_SYNcat_pH2_400mV_7_x_25", "Q4_SYNcat_pH2_400mV_8_x_26"]
    b = _grouped_stems(tmp_path, stems)
    assert len(M.load(b)["record_groups"]) == 4
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[-1])
    M.group(b, regroup=True)
    runs = {r["run_key"]: r["stem"] for r in M.load(b)["runs"]}
    sizes = sorted(sorted(runs[k] for k in g["member_run_keys"]) for g in _live(b))
    # the 15/16 pair joins (their last token); the 7/8 pair still differs at token 5, not a counter
    assert sizes == [["Q4_SYNcat_pH2_400mV_15", "Q4_SYNcat_pH2_400mV_16"], ["Q4_SYNcat_pH2_400mV_7_x_25"], ["Q4_SYNcat_pH2_400mV_8_x_26"]]


def test_name_keys_read_last_as_the_last_token():
    assert G.name_stem_key("A_B_15", counter_positions=[-1]) == G.name_stem_key("A_B_16", counter_positions=[-1]) == "a_b"
    assert G.name_stem_key("A_7_B_15", counter_positions=[-1]) == "a_7_b"  # only the last token
    assert G.name_stem_key("A_B_15", counter_positions=[3]) == "a_b"
    assert G.name_stem_key("A_B_X_15", counter_positions=[3]) == "a_b_x_15"  # a fixed position misses it


@pytest.mark.parametrize("raw", ["last", "-1", "LAST", "3,last"])
def test_decide_accepts_last_and_stores_it_as_minus_one(tmp_path, raw, capsys):
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    assert cli.main(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions",
                     "--positions", raw, "--by", BY]) == 0
    d = M.load(b)["scientist_decisions"][-1]
    assert d["positions"] == ([3, -1] if raw.startswith("3") else [-1])
    assert M.counter_positions(M.load(b)) == d["positions"]
    assert G.counter_positions_decision(M.load(b))["positions"] == sorted(set(d["positions"]))
    assert cli.main(["bundle", "check", str(b)]) == 0


@pytest.mark.parametrize("raw", ["0", "-2", "first", "last,last,1,2,3,4,5,6,7"])
def test_decide_refuses_other_positions(tmp_path, raw, capsys):
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    assert cli.main(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions",
                     "--positions", raw, "--by", BY]) != 0
    assert "last" in capsys.readouterr().err


def test_last_is_for_counters_only(tmp_path, capsys):
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    assert cli.main(["bundle", "decide", str(b), "--target", "experiment", "--decision", B.NOT_COUNTER_DECISION,
                     "--positions", "last", "--by", BY]) != 0
    assert "set_counter_positions" in capsys.readouterr().err


def test_decide_help_and_the_counter_question_name_last(tmp_path, capsys):
    try:
        cli.main(["bundle", "decide", "--help"])
    except SystemExit:
        pass
    text = " ".join(capsys.readouterr().out.split())
    assert "last" in text and "the grouping step joins those runs" not in text
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV_15", "Q4_SYNcat_pH2_400mV_16"])
    [q] = [q for q in Q.consolidate(M.load(b))["questions"] if q["kind"] == "naming_counter_positions"]
    assert "--positions <n[,m] or last>" in q["answer_command"]


def test_a_bundle_holding_last_is_the_new_format_and_an_older_one_still_validates(tmp_path):
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_016_A"])
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[-1])
    data = json.loads((b / "bundle.json").read_text())
    assert data["format_version"] == B.FORMAT_VERSION == "1.9.0"
    older = dict(data, format_version="1.8.0", scientist_decisions=[d for d in data["scientist_decisions"] if -1 not in (d.get("positions") or ())])
    assert B.validate_bundle(older) == []
    bad = dict(data, scientist_decisions=[dict(d, positions=[-3]) if d.get("positions") else d for d in data["scientist_decisions"]])
    assert B.validate_bundle(bad)


# --- 3. live listings; one candidate per pair --------------------------------------------------------


def test_list_groups_shows_live_groups_by_default_and_all_with_a_flag(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_again", "Q4_SYNcat_pH2_500mV"])
    g = M.load(b)["record_groups"]
    out = _merge(b, g[0]["group_id"], [g[1]["group_id"]])
    assert out["live_record_groups"] == 2 and out["record_groups"] == 3
    capsys.readouterr()
    assert cli.main(["bundle", "list", str(b), "groups"]) == 0
    live = json.loads(capsys.readouterr().out)
    assert live["total"] == 2 and {i["status"] for i in live["items"]} == {"proposed"}
    assert live["not_listed"] == {"merged": 1}
    assert cli.main(["bundle", "list", str(b), "groups", "--all"]) == 0
    every = json.loads(capsys.readouterr().out)
    assert every["total"] == 3 and "not_listed" not in every
    assert "- Record groups: 2 (0 confirmed) and 1 kept as decision history (1 merged)" in (b / "summary.md").read_text()


def test_a_refused_merge_and_its_rule_candidate_are_one_candidate_keeping_the_rule_id(tmp_path):
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    [before] = M.load(b)["merge_candidates"]
    g1, g2 = M.load(b)["record_groups"]
    _merge(b, g1["group_id"], [g2["group_id"]])
    [mc] = M.load(b)["merge_candidates"]
    assert mc["merge_candidate_id"] == before["merge_candidate_id"]
    assert [r["code"] for r in mc["reasons"]][:2] == ["scientist_decided_merge", "numeric_name_token_differs"]
    assert mc["reason_code"] == "scientist_decided_merge"
    assert cli.main(["bundle", "check", str(b)]) == 0


# --- 4. merge candidates say what they are --------------------------------------------------------------


def test_a_candidate_of_names_stating_different_samples_carries_a_caution(tmp_path, capsys):
    b = _xdc(tmp_path, ["SYN_03_MOFdry_015_A", "SYN_03_MOFdry_spot2_017_A", "SYN_01_Sref_006_A"])
    [mc] = M.load(b)["merge_candidates"]
    assert mc["reason_code"] == "sample_identity_not_stated"
    codes = {c["code"] for c in mc["caution"]}
    assert codes == {"names_state_different_samples_or_conditions", "no_condition_classified"}
    assert any("merging them would make one wrong record — check before saying yes" in c["statement"] for c in mc["caution"])
    assert mc["question"]["text"].startswith("CAUTION:")
    capsys.readouterr()
    assert cli.main(["bundle", "list", str(b), "merge-candidates"]) == 0
    [row] = json.loads(capsys.readouterr().out)["items"]
    assert row["reason_code"] == "sample_identity_not_stated" and row["caution"]
    assert sorted(lab for g in row["groups"] for lab in g["run_labels"]) == sorted(
        ["SYN_03_MOFdry_015", "SYN_03_MOFdry_spot2_017", "SYN_01_Sref_006"])
    assert cli.main(["bundle", "show", str(b), "merge-candidate", mc["merge_candidate_id"]]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["merge_candidate_id"] == mc["merge_candidate_id"] and shown["groups"] and shown["caution"]


def test_a_candidate_of_repeat_names_with_classified_conditions_has_no_caution(tmp_path):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_again"])
    [mc] = M.load(b)["merge_candidates"]
    assert mc["caution"] == [] and mc["reason_code"] == "sample_identity_not_stated"
    assert not mc["question"]["text"].startswith("CAUTION:")


def test_run_labels_are_capped_per_group_with_a_count():
    runs = {f"k{i}": {"run_key": f"k{i}", "stem": f"SYN_{i:03d}"} for i in range(8)}
    bundle = {"runs": list(runs.values()),
              "record_groups": [{"group_id": "g1", "status": "proposed", "member_run_keys": list(runs)}]}
    [g] = G.merge_candidate_groups(bundle, {"group_ids": ["g1"]})
    assert g["runs"] == 8 and len(g["run_labels"]) == 5 and g["run_labels_omitted"] == 3
