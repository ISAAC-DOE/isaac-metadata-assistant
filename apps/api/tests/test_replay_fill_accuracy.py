"""scripts/replay_fill_accuracy.py: read-only measurement of fill accuracy. Synthetic data only."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

SCRIPT = ws.REPO_ROOT / "scripts/replay_fill_accuracy.py"
SEMANTICS = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
ENV = "context.environment"
BY = dict(by="Synthetic Scientist", orcid=None)

_spec = importlib.util.spec_from_file_location("replay_fill_accuracy", SCRIPT)
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def _bundle(runs, values):
    """runs: {run_id: name}; values: [(run_id|None, path, state, value)] as missing_values."""
    return {
        "runs": [{"run_id": rid, "stem": name} for rid, name in runs.items()],
        "candidates": [],
        "conflicts": [],
        "scientist_decisions": [],
        "missing_values": [
            {"value_id": f"v{i}", "run_id": rid, "target_field_path": path, "value_state": state, "value": value}
            for i, (rid, path, state, value) in enumerate(values)
        ],
    }


def test_classes_matching_by_run_name_and_mismatch_report():
    # same names, DIFFERENT ids in the two bundles: matching must be by name
    answers = _bundle({"run-001": "ZZ_fake_run_01", "run-002": "ZZ_fake_run_02", "run-003": "ZZ_fake_run_03"}, [
        ("run-001", ENV, "scientist_confirmed", "Ex_Situ"),
        ("run-002", ENV, "scientist_confirmed", "in_situ"),
        ("run-003", ENV, "scientist_confirmed", "operando"),
        ("run-001", "system.domain", "scientist_confirmed", "experimental"),
        ("run-002", "system.domain", "scientist_confirmed", "experimental"),
        (None, "attribution.group", "scientist_confirmed", "ZZ fake group"),
        (None, "unrelated.path", "needs_review", "ignored: not confirmed"),
    ])
    replay = _bundle({"r-9": "ZZ_fake_run_03", "r-8": "ZZ_fake_run_02", "r-7": "ZZ_fake_run_01"}, [
        ("r-7", ENV, "filled", " ex_situ "),            # correct (case/whitespace)
        ("r-8", ENV, "filled", "ex_situ"),              # wrong vs in_situ
        ("r-9", ENV, "needs_review", "operando"),       # still asked
        ("r-7", "system.domain", "scientist_confirmed", "experimental"),  # confirmed
        # run 02 domain: absent
        (None, "attribution.group", "filled", "ZZ fake group"),
        ("r-7", "extra.path", "filled", "x"),           # filled_unchecked
        ("r-8", "extra.path", "filled", "y"),
    ])
    res = R.classify(answers, replay)
    assert res["answer_key_size"] == 6
    assert res["counts"] == {"filled_correct": 2, "filled_wrong": 1, "confirmed": 1, "still_asked": 1, "absent": 1}
    assert res["per_path"][ENV] == {"filled_correct": 1, "filled_wrong": 1, "confirmed": 0, "still_asked": 1, "absent": 0}
    assert res["filled_wrong"] == [
        {"run": "ZZ_fake_run_02", "path": ENV, "replay_value": "ex_situ", "answer_value": "in_situ"}]
    assert res["filled_unchecked"] == {"total": 2, "per_path": {"extra.path": 2}}
    text = R.render(res)
    assert "ZZ_fake_run_02" in text and "'ex_situ'" in text and "'in_situ'" in text


def test_a_filled_value_is_read_from_its_fill_block():
    """A filled MISSING value's `value` is always null; what its rule filled is `fill.value` (candidates too)."""
    answers = _bundle({"run-001": "ZZ_fake_run_01"}, [(None, "system.domain", "scientist_confirmed", "experimental"),
                                                      ("run-001", ENV, "scientist_confirmed", "ex_situ")])
    replay = _bundle({"r-1": "ZZ_fake_run_01"}, [(None, "system.domain", "filled", None)])
    replay["missing_values"][0]["fill"] = {"rule_id": "isaac.fill.domain_from_acquisition.v1", "value": "experimental"}
    replay["candidates"] = [{"candidate_id": "c1", "run_id": "r-1", "target_field_path": ENV, "value_state": "filled",
                             "value": "ex_situ", "fill": {"rule_id": "isaac.fill.stored_convention.v1",
                                                          "value": "ex_situ"}}]
    res = R.classify(answers, replay)
    assert res["counts"]["filled_correct"] == 2 and res["counts"]["filled_wrong"] == 0, res


def test_value_equality_normalisation():
    assert R.same(" A b ", "a B") and R.same(1, 1.0) and R.same({"k": " X "}, {"k": "x"}) and R.same([" a"], ["A"])
    assert not R.same("a", "b") and not R.same(1, 2) and not R.same("1", 2)


def test_experiment_scope_is_keyed_by_none():
    answers = _bundle({}, [(None, "a.b", "scientist_confirmed", 5)])
    replay = _bundle({"r": "ZZ_fake_run_01"}, [("r", "a.b", "filled", 5)])  # run-scope there: a different key
    assert R.classify(answers, replay)["counts"]["absent"] == 1


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    out = tmp_path_factory.mktemp("replay") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


def test_real_decision_cli_and_files_untouched(imported, tmp_path, capsys):
    answers, replay = tmp_path / "answers", tmp_path / "replay"
    shutil.copytree(imported, answers)
    shutil.copytree(imported, replay)
    miss = [m for m in M.load(answers)["missing_values"] if m["target_field_path"] == ENV and m["run_id"]][:2]
    assert len(miss) == 2
    M.decide(answers, target_ids=[miss[0]["value_id"]], decision="correct", value="ex_situ", **BY)
    M.decide(answers, target_ids=[miss[1]["value_id"]], decision="correct", value="in_situ", **BY)
    # hand-craft the replay (the `filled` state may not be writable yet): one right, one wrong
    names = {r["run_id"]: r["stem"] for r in M.load(replay)["runs"]}
    path = replay / "bundle.json"
    data = json.loads(path.read_text())
    want = {names[miss[0]["run_id"]]: ("filled", "EX_SITU"), names[miss[1]["run_id"]]: ("filled", "operando")}
    for m in data["missing_values"]:
        if m["target_field_path"] == ENV and names.get(m["run_id"]) in want:
            m["value_state"], m["value"] = want[names[m["run_id"]]]
    path.write_text(json.dumps(data))
    before = (path.read_bytes(), (answers / "bundle.json").read_bytes())

    assert R.main(["--answers", str(answers), "--replay", str(replay), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["counts"]["filled_correct"] == 1 and out["counts"]["filled_wrong"] == 1
    [w] = out["filled_wrong"]
    assert w["replay_value"] == "operando" and w["answer_value"] == "in_situ" and w["path"] == ENV
    assert R.main(["--answers", str(answers), "--replay", str(replay)]) == 0
    assert "filled_wrong (1)" in capsys.readouterr().out
    assert (path.read_bytes(), (answers / "bundle.json").read_bytes()) == before
    assert sorted(p.name for p in replay.iterdir()) == sorted(p.name for p in imported.iterdir())


def test_unreadable_input_exits_2(tmp_path, capsys):
    assert R.main(["--answers", str(tmp_path / "nope"), "--replay", str(tmp_path / "nope2")]) == 2
