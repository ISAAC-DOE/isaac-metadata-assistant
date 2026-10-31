"""Review fixes to the merge paths (cycle 1, review 1): a merge never combines different conditions.

Found in review of the paths that give a scientist's merge a way through (none of it on real data):

* H1: the "same sample" path combined `…_pristine` with `…_cycled`. A scientist could truthfully
  confirm one sample (the same material) and the runs were combined, although the names state two
  conditions. A sample confirmation alone is no longer enough when the names differ in a token: the
  scientist also says the differing tokens are labels, not conditions (`--same-conditions`, stored on
  the merge decision with the tokens it was given for). Glued letter+number tokens (T300, E1, P2) are
  read as possible quantities, which nothing combines.
* M1: `--positions last` joined `…_3` with `…_4` (sample numbers on names with no counter) because
  `…_3_001` showed the counter is the token AFTER them. The last token is a counter only where names
  sharing its prefix have no longer form; the `decide` reply says what the answer would join.
* L1: `Rep1_ZnO` / `Rep2_ZnO` name replicate samples: a differing RepN token is not "just a repeat
  marker" on the merge path.

SYNTHETIC files only: the SYN counter folder and invented XDC scans dated 2099.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M

from test_local_import_capture_decisions import _combined, _grouped_stems
from test_local_import_merge_paths import BY, SAMPLE, _follow, _live, _merge, _not_combined, _xdc


def _confirm_samples(b, value=SAMPLE):
    for m in M.load(b)["missing_values"]:
        if m["target_field_path"] == "sample.material.name":
            M.decide(b, target_ids=[m["value_id"]], decision="correct", value=value, by=BY, orcid=None)


def _stems_of(b, group):
    runs = {r["run_key"]: r["stem"] for r in M.load(b)["runs"]}
    return sorted(runs[k] for k in group["member_run_keys"])


# --- H1: the same sample is not the same conditions ------------------------------------------------


def test_a_confirmed_sample_alone_does_not_combine_names_that_differ_in_a_word(tmp_path):
    """The reviewer's case: one material, measured pristine and cycled. Confirming the sample (true)
    and regrouping keeps them apart; the reason asks for the conditions too, naming the words."""
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_pristine", "Q4_SYNcat_pH2_cycled"])
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "same sample AND same conditions? the names differ in: cycled / pristine" in nc["reason"]
    assert any("--same-conditions" in c for c in nc["next_commands"])
    _confirm_samples(b)
    out = M.group(b, regroup=True)
    assert _combined(b) == []
    nc = _not_combined(out)
    assert "the names differ in: cycled / pristine" in nc["reason"]
    assert [c for c in nc["next_commands"] if "--same-conditions" in c] == nc["next_commands"]  # only the acknowledgement is left


def test_following_the_refusal_with_the_acknowledgement_combines_and_records_the_tokens(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_pristine", "Q4_SYNcat_pH2_cycled"])
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    _follow(b, nc["next_commands"], capsys)
    out = M.group(b, regroup=True)
    assert out["merge_decisions_not_combined"] == []
    [c] = _combined(b)
    assert sorted(c["member_run_keys"]) == sorted(g1["member_run_keys"] + g2["member_run_keys"])
    d = [x for x in M.load(b)["scientist_decisions"] if x["decision"] == "merge"][-1]
    assert d["same_conditions_tokens"] == ["cycled", "pristine"]
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_the_acknowledgement_covers_only_the_tokens_it_was_given_for(tmp_path):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_pristine", "Q4_SYNcat_pH2_cycled", "Q4_SYNcat_pH2_soaked"])
    _confirm_samples(b)
    bundle = M.load(b)
    h1, h2, h3 = bundle["record_groups"]
    d = {"decision_id": "d-99999", "decided_by": {"name": BY}, "same_conditions_tokens": ["cycled", "pristine"]}
    pair = M._combine_for_merge([h1, h2], d, h1["group_id"], "exp")
    assert M._merge_blockers(bundle, {}, [h1, h2], pair, d) == []
    three = M._combine_for_merge([h1, h2, h3], d, h1["group_id"], "exp")
    [reason] = M._merge_blockers(bundle, {}, [h1, h2, h3], three, d)
    assert "the names differ in: cycled / pristine / soaked" in reason
    assert M._merge_blockers(bundle, {}, [h1, h2], pair, {**d, "same_conditions_tokens": None})  # no acknowledgement


def test_same_conditions_is_stored_on_the_merge_decision_and_validates(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_before", "Q4_SYNcat_pH2_after"])
    g1, g2 = M.load(b)["record_groups"]
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(b), "--target", g1["group_id"], "--decision", "merge",
                     "--merge-with", g2["group_id"], "--same-conditions", "--by", BY]) == 0
    reply = json.loads(capsys.readouterr().out)
    assert "after / before" in reply["statement"]
    data = json.loads((b / "bundle.json").read_text())
    assert data["scientist_decisions"][-1]["same_conditions_tokens"] == ["after", "before"]
    assert data["format_version"] == "1.9.0" and B.validate_bundle(data) == []
    bad = dict(data, scientist_decisions=[dict(x, same_conditions_tokens=[]) for x in data["scientist_decisions"]])
    assert B.validate_bundle(bad)
    # an older bundle (no such field) still validates
    older = dict(data, scientist_decisions=[{k: v for k, v in x.items() if k != "same_conditions_tokens"} for x in data["scientist_decisions"]])
    assert B.validate_bundle(older) == []


def test_same_conditions_is_refused_where_it_cannot_apply(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_again", "Q4_SYNcat_pH2_500mV"])
    g1, g2, g3 = M.load(b)["record_groups"]
    with pytest.raises(M.MutationRefused, match="goes with --decision merge"):
        M.decide(b, target_ids=[g1["group_id"]], decision="confirm", value=None, by=BY, orcid=None, same_conditions=True)
    with pytest.raises(M.MutationRefused, match="do not differ"):  # only a repeat marker: nothing to acknowledge
        M.decide(b, target_ids=[g1["group_id"]], decision="merge", value=None, by=BY, orcid=None,
                 merge_with=[g2["group_id"]], same_conditions=True)
    with pytest.raises(M.MutationRefused, match="400mV / 500mV"):  # a quantity is never a label
        M.decide(b, target_ids=[g1["group_id"]], decision="merge", value=None, by=BY, orcid=None,
                 merge_with=[g3["group_id"]], same_conditions=True)
    assert not [d for d in M.load(b)["scientist_decisions"] if d["decision"] == "merge"]


@pytest.mark.parametrize("stems,stated", [
    (["Cu_T300", "Cu_T500"], ["T300", "T500"]),
    (["SYN_E1_film", "SYN_E2_film"], ["E1", "E2"]),
    (["SYN_P2_x", "SYN_P3_x"], ["P2", "P3"]),
    # verification review: shapes the patterns did not know now fail closed — any letters+digits token
    (["SYN_spot2_x", "SYN_spot3_x"], ["spot2", "spot3"]),
    (["Q4_T300K_x", "Q4_T500K_x"], ["T300K", "T500K"]),
    (["Q4_E0p4V_x", "Q4_E0p6V_x"], ["E0p4V", "E0p6V"]),
    (["Q4_Pt0p5wt_x", "Q4_Pt1wt_x"], ["Pt0p5wt", "Pt1wt"]),
    (["Q4_Temp300_x", "Q4_Temp500_x"], ["Temp300", "Temp500"]),
    (["Q4_cyc10_x", "Q4_cyc50_x"], ["cyc10", "cyc50"]),
    (["Q4_t1h_x", "Q4_t5h_x"], ["t1h", "t5h"]),
    (["SYN_x_015", "SYN_x_016"], []),  # a bare counter is left to the counter rules
])
def test_glued_letter_and_number_tokens_are_possible_quantities(stems, stated):
    assert M._stated_quantities(stems) == stated


def test_names_differing_in_a_glued_quantity_are_never_combined(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_T300", "Q4_SYNcat_T500"])
    _confirm_samples(b)
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "state different conditions (T300 / T500)" in nc["reason"] and "never combined" in nc["reason"]
    assert not any("--same-conditions" in c for c in nc["next_commands"])


# --- the repeat-marker path: the marker is the ONLY difference; RepN is a replicate (L1) -------------


def test_a_repeat_marker_beside_a_differing_word_needs_the_acknowledgement(tmp_path):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_pristine", "Q4_SYNcat_pH2_cycled_again"])
    _confirm_samples(b)
    g1, g2 = M.load(b)["record_groups"]
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "the names differ in: cycled / pristine" in nc["reason"] and _combined(b) == []


@pytest.mark.parametrize("stems", [["Rep1_ZnO_pH2", "Rep2_ZnO_pH2"], ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_rep2"]])
def test_a_differing_rep_number_is_a_replicate_not_a_repeat_marker(tmp_path, capsys, stems):
    b = _grouped_stems(tmp_path, stems)
    groups = M.load(b)["record_groups"]
    if len(groups) < 2:
        pytest.skip("the default grouping joined these (unchanged by design)")
    g1, g2 = groups
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "same sample AND same conditions?" in nc["reason"] and _combined(b) == []
    _follow(b, nc["next_commands"], capsys)  # the scientist says: one sample, and RepN is only a label
    assert M.group(b, regroup=True)["merge_decisions_not_combined"] == [] and len(_combined(b)) == 1


# --- M1: `last` is a counter only where it is one ----------------------------------------------------


def test_last_does_not_join_sample_numbers_on_names_without_a_counter(tmp_path):
    stems = ["Q4_SYNcat_pH2_3", "Q4_SYNcat_pH2_4", "Q4_SYNcat_pH2_3_001", "Q4_SYNcat_pH2_3_002"]
    b = _grouped_stems(tmp_path, stems)
    before = sorted(_stems_of(b, g) for g in _live(b))
    reply = M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[-1])
    assert reply["regroup_preview"]["groups_joined"] == 0
    M.group(b, regroup=True)
    after = sorted(_stems_of(b, g) for g in _live(b))
    assert ["Q4_SYNcat_pH2_3", "Q4_SYNcat_pH2_4"] not in after
    assert after == before


def test_last_exempts_only_the_shorter_names_of_a_prefix():
    exempt = G.last_counter_exempt(["A_pH2_3", "A_pH2_4", "A_pH2_3_001", "B_x_015", "B_x_016", "C_s1_7_x_25"])
    assert exempt == {"a_ph2_3", "a_ph2_4"}
    # BL4-3 shape: every name ends in a counter, names of different length: nothing exempt
    assert G.last_counter_exempt(["01_SYNzz_s1_015", "01_SYNzz_s1_016", "08_std_ZZSO4_x_030", "SYN_7_x_25"]) == frozenset()


def test_last_still_joins_counters_on_names_of_different_length(tmp_path):
    """The case `last` was built for, counters not zero-padded so only `last` can say so."""
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV_15", "Q4_SYNcat_pH2_400mV_16", "Q4_SYNcat_film_x_400mV_25", "Q4_SYNcat_film_x_400mV_26"])
    reply = M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[-1])
    preview = reply["regroup_preview"]
    assert preview["groups_joined"] == 4 and preview["into"] == 2
    assert "would join 4 of the current groups into 2" in preview["statement"]
    M.group(b, regroup=True)
    assert sorted(len(g["member_run_keys"]) for g in _live(b)) == [2, 2]


def test_a_bl43_style_merge_with_last_is_still_combined(tmp_path):
    b = _xdc(tmp_path, ["01_SYNzz_s1_015_A", "01_SYNzz_s1_016_A", "08_std_ZZSO4_x_030_A"])
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[-1])
    M.group(b, regroup=True)
    by_stem = {tuple(_stems_of(b, g)): g for g in _live(b)}
    g1, g2 = by_stem[("01_SYNzz_s1_015",)], by_stem[("01_SYNzz_s1_016",)]
    out = _merge(b, g1["group_id"], [g2["group_id"]])
    assert out["merge_decisions_not_combined"] == [] and len(_combined(b)) == 1


def test_the_counter_answer_reply_counts_what_it_would_join(tmp_path, capsys):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV_15", "Q4_SYNcat_pH2_400mV_16"])
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions",
                     "--positions", "last", "--by", BY]) == 0
    reply = json.loads(capsys.readouterr().out)
    assert reply["regroup_preview"]["groups_joined"] == 2 and reply["regroup_preview"]["into"] == 1
    assert "isaac bundle group <bundle_dir> --regroup" in reply["regroup_preview"]["statement"]
    assert len(M.load(b)["record_groups"]) == 2  # a preview: nothing regrouped


@pytest.mark.parametrize("stems", [
    ["Q4_SYNcat_pristine_cycled", "Q4_SYNcat_cycled_pristine"],
    ["Q4_SYNcat_pH2_ox", "Q4_SYNcat_pH2_ox_ox"],
])
def test_names_with_the_same_words_reordered_or_repeated_are_never_combined(tmp_path, capsys, stems):
    """Verification review: an order-only or repeat-only difference left no word to acknowledge, so a
    sample confirmation alone combined them. Nothing recorded can say which reading is right: never."""
    b = _grouped_stems(tmp_path, stems)
    g1, g2 = M.load(b)["record_groups"]
    _confirm_samples(b)
    nc = _not_combined(_merge(b, g1["group_id"], [g2["group_id"]]))
    assert "same words in a different order or a different number of times" in nc["reason"]
    assert not any("--same-conditions" in c for c in nc["next_commands"])
    assert _combined(b) == []
