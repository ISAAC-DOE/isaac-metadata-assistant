"""c16a (H2): a BL4-3 style beamtime whose runs differ only in their last token. Synthetic only (SYN names).

On a real BL4-3 sulfur K-edge beamtime (61 runs, names ``<n>_<sample>_<cond>_<NNN>``, each with a ``.exp``
naming ``DATA_FILE``), no file states the sample, so every run was its own group. Measured there:

* ``bundle questions --scope experiment`` had NO counter question: it surfaced first inside a merge refusal;
* the only merge candidate lumped 29 unrelated groups together, elemental S to the electrochemistry runs;
* a ``--positions last`` answer was echoed back as "counter position(s) -1 recorded".

What these pin: the counter question (same id as always) is asked up front about the LAST token; there is one
merge candidate per shared base name (the ``.exp`` ``DATA_FILE`` where read, else the name minus its trailing
number), never one for the whole beamtime; a run alone under its base name is in none; the default groups are
unchanged; a "no" to the question names the whole-number positions; the answer is echoed in words.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import.readers import ssrl_xdc as x

from test_local_import_reader_ssrl_xdc import make_scan

BY = "SYNTHETIC TEST"

#: name -> the .exp DATA_FILE (None: no .exp beside it). Repeats share a base name; the rest are alone.
RUNS = {
    "01_SYNelS_015": "01_SYNelS", "01_SYNelS_016": "01_SYNelS",
    "03_SYNmofA_dry_017": "03_SYNmofA_dry", "03_SYNmofA_dry_018": "03_SYNmofA_dry",
    "04_SYNmofA_wet_019": None, "04_SYNmofA_wet_020": None,  # no .exp: the name minus its last number
    "05_SYNmofB_m150mV_021": "05_SYNmofB_m150mV",  # alone under its base name
    "06_SYNfoil_022": "06_SYNfoil",  # alone
}


def _beamtime(root: Path) -> Path:
    src = root / "SYN_bt43"
    for name, data_file in RUNS.items():
        for i in (1, 2):
            make_scan(src / f"{name}_A.{i:03d}", free_text=("SYNTHETIC comment line",))
        if data_file is not None:
            (src / f"{name}.exp").write_text(f"EXPT_TYPE SYN\nDATA_FILE {data_file}\nCOMMENTS1 SYNTHETIC\n")
    return src


@pytest.fixture(scope="module")
def grouped(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("c16a")
    out = root / "out"
    assert cli.main(["import", str(_beamtime(root)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


def _bundle(out: Path) -> dict:
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    return data


def _labels(b: dict, gids) -> list[list[str]]:
    runs = {r["run_key"]: r["label"] for r in b["runs"]}
    groups = {g["group_id"]: g for g in b["record_groups"]}
    return [sorted(runs[k] for k in groups[gid]["member_run_keys"]) for gid in gids]


def _counter_q(b: dict) -> list[dict]:
    return [q for q in Q.consolidate(b)["questions"] if q["kind"] == "naming_counter_positions"]


def test_the_reader_reads_only_the_data_file_line_of_the_runs_own_exp(tmp_path):
    src = _beamtime(tmp_path)
    runs = {r.label: r for r in x.collect_generic_runs(src)}
    [st] = [s for s in runs["01_SYNelS_015"].statements if s["key"] == "exp_data_file"]
    assert (st["literal"], st["locator"], st["source_relative_path"]) == ("01_SYNelS", "line:2", "01_SYNelS_015.exp")
    assert [c["parsed"] for c in runs["01_SYNelS_015"].companions if c["role"] == "experiment"] == [True]
    assert not [s for s in runs["04_SYNmofA_wet_019"].statements if s["key"] == "exp_data_file"]
    # nothing else of the .exp is a statement (EXPT_TYPE and COMMENTS are not read here)
    assert not [s for s in runs["01_SYNelS_015"].statements if s["source_relative_path"].endswith(".exp") and s["key"] != "exp_data_file"]


def test_the_default_groups_are_unchanged_one_run_each(grouped):
    b = _bundle(grouped)
    live = [g for g in b["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES]
    assert len(live) == len(RUNS) and all(len(g["member_run_keys"]) == 1 for g in live)


def test_one_merge_candidate_per_shared_base_name_never_one_for_the_beamtime(grouped):
    b = _bundle(grouped)
    got = sorted(_labels(b, mc["group_ids"]) for mc in b["merge_candidates"])
    assert got == [
        [["01_SYNelS_015"], ["01_SYNelS_016"]],
        [["03_SYNmofA_dry_017"], ["03_SYNmofA_dry_018"]],
        [["04_SYNmofA_wet_019"], ["04_SYNmofA_wet_020"]],
    ]
    named = {gid for mc in b["merge_candidates"] for gid in mc["group_ids"]}
    alone = {g["group_id"] for g in b["record_groups"] if _labels(b, [g["group_id"]])[0][0] in ("05_SYNmofB_m150mV_021", "06_SYNfoil_022")}
    assert not named & alone


def test_the_data_file_decides_the_base_name_where_it_was_read():
    assert G.base_name_key("03_SYNx_dry_017") == "03_synx_dry"
    assert G.base_name_key("03_SYNx_dry_017", "03_SYNx_dry") == "03_synx_dry"
    # c16-r M4: a DATA_FILE naming another acquisition than the run's own name is not used
    assert G.base_name_key("03_SYNx_dry_017", "SYN_other") == "03_synx_dry"
    assert G.base_name_key("03_SYNx_dry") == "03_synx_dry"  # the last token is a word: the whole name


def test_the_counter_question_is_asked_up_front_about_the_last_token_under_its_id(grouped):
    b = _bundle(grouped)
    [q] = _counter_q(b)
    assert q["question_id"] == Q.COUNTER_QUESTION_ID
    assert q["positions"] == [G.LAST_POSITION] and q["last_token_positions"] == [3, 4]
    assert "last token" in q["text"] and "-1" not in q["text"] and "`last`" in q["text"]
    assert q["example_names"]["-1"][0].endswith("_[015]")


def test_the_last_answer_is_said_in_words_and_closes_the_question(grouped, tmp_path):
    out = tmp_path / "b"
    import shutil
    shutil.copytree(grouped, out)
    got = M.decide(out, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None,
                   positions=[G.LAST_POSITION])
    assert got["statement"].startswith("the last token recorded as the run counter") and "-1" not in got["statement"]
    assert cli.main(["bundle", "group", str(out), "--regroup"]) == 0
    assert not _counter_q(_bundle(out))


def test_a_no_names_the_whole_number_positions_and_closes_the_question(grouped, tmp_path):
    out = tmp_path / "b"
    import shutil
    shutil.copytree(grouped, out)
    got = M.decide_question(out, question_id=Q.COUNTER_QUESTION_ID, decision=B.NOT_COUNTER_DECISION, value=None, by=BY, orcid=None)
    assert "position(s) 3, 4 are NOT" in got["statement"]
    assert not _counter_q(_bundle(out))


def test_the_plain_statement_never_shows_minus_one():
    assert M._counter_positions_words([G.LAST_POSITION]) == "the last token recorded as the run counter"
    assert M._counter_positions_words([2, G.LAST_POSITION]) == "counter position(s) 2 and the last token recorded"
    assert M._counter_positions_words([2, 3]) == "counter position(s) 2, 3 recorded"


def test_names_already_grouped_get_no_up_front_question(tmp_path):
    """A beamtime whose repeats are already ONE group (nothing to merge) is not asked about the last token."""
    bundle = {"runs": [{"run_key": f"k{i}", "run_id": f"run-{i:03d}", "stem": f"SYN_a_{i:03d}"} for i in (1, 2)]}
    infos = [{"run": r} for r in bundle["runs"]]
    assert G._last_token_families(infos, {"k1": "rg-1", "k2": "rg-1"}) == {}
    assert G._last_token_families(infos, {"k1": "rg-1", "k2": "rg-2"}) == {("syn", "a"): {"001": {"rg-1"}, "002": {"rg-2"}}}
