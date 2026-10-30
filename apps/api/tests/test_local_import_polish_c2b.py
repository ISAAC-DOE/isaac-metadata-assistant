"""Skill polish, cycle 2 (walking the skill on a 194-group beamtime). SYNTHETIC fixtures only.

* ``bundle list <dir> groups``: one row per line with a few member file stems, the scan count, the reader and
  ``cannot_export_reason`` (``no_scans`` / ``processing_not_applicable:<code>``), counted over the whole list.
* ``bundle build-records`` prints counts and the first few drafts (``--full`` prints all; drafts/index.json keeps
  every row); ``bundle validate`` counts its verdicts' reasons and names the first few groups' plain reasons.
* A question built at experiment scope whose targets are all in ONE group says that group; its id is unchanged.
* ``bundle list <dir> runs`` prints each run's file stem; a findings file names a run by stem or run id, and a
  reference naming two runs is refused, never spread over both.
* The counter question takes ``defer`` ("I don't know"): recorded, grouping unchanged, the question stays, deferred.
* ``summary.md``: runs in no file-name group are said so ("group None" before), and the conflict count says why
  it differs from the conflicting-value count; the import output says the same.
* ``export`` says "Wrote N record(s), refused M group(s)" (its exit code is unchanged).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import suggestions as S

from test_local_import_grouping_cli import _folder
from test_local_import_processing_not_applicable import _group, _na_result, na_bundle  # noqa: F401  (fixture)
from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, SEMANTICS, _decide_everything, _portal, bdir, fake_upstream, pristine,
)


def _run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


@pytest.fixture()
def grouped(tmp_path, capsys):
    out = tmp_path / "grouped"
    assert _run(capsys, "import", SEMANTICS, "--out", out)[0] == 0
    assert _run(capsys, "bundle", "group", out)[0] == 0
    return out


@pytest.fixture()
def counter(tmp_path, capsys):
    """The SYN folder whose file names carry a counter-like token: the counter question is asked."""
    out = tmp_path / "counter"
    assert _run(capsys, "import", _folder(tmp_path), "--out", out)[0] == 0
    assert _run(capsys, "bundle", "group", out)[0] == 0
    return out


def _qids(bdir_: Path) -> set[str]:
    return {q["question_id"] for q in Q.consolidate(M.load(bdir_))["questions"]}


def _groups_signature(bdir_: Path) -> str:
    b = M.load(bdir_)
    return json.dumps([(g["group_id"], g["status"], g["member_run_keys"]) for g in b["record_groups"]])


# --- 1. groups rows: file stems, scans, reader, cannot_export_reason --------------------------------------------


def test_a_groups_row_names_its_files_scans_and_reader_one_row_per_line(grouped, capsys):
    code, out, _ = _run(capsys, "bundle", "list", grouped, "groups", "--limit", "10")
    assert code == 0
    page = json.loads(out)
    b = M.load(grouped)
    runs = {r["run_id"]: r for r in b["runs"]}
    for item in page["items"]:
        members = item["member_run_ids"]
        assert item["files"] == [runs[r]["stem"] for r in members][: cli.GROUP_ROW_FILES]
        assert item["scans"] == sum(runs[r]["scan_count"] for r in members)
        assert item["reader"] == "spec_acquisition"
        assert "cannot_export_reason" not in item
    # one line per row: the page reads as a table, and stays one JSON document
    rows = [line for line in out.splitlines() if line.lstrip().startswith('{"group_id"')]
    assert len(rows) == page["returned"]
    assert "cannot_export" not in page


def test_a_group_the_protocol_does_not_apply_to_says_it_cannot_export(na_bundle, capsys):
    code, out, _ = _run(capsys, "bundle", "list", na_bundle, "groups")
    page = json.loads(out)
    (row,) = [i for i in page["items"] if i["group_id"] == "g1"]
    assert row["cannot_export_reason"] == "processing_not_applicable:no_xas_channel"
    assert page["cannot_export"] == {"processing_not_applicable:no_xas_channel": 1}
    assert "bulk confirm" in page["cannot_export_note"]


def test_a_group_with_no_scans_says_it_cannot_export_and_a_long_member_list_is_counted():
    runs = [{"run_key": f"k{i}", "run_id": f"run-{i:03d}", "stem": f"SYN_{i}", "scan_count": 0,
             "source_type": "spec_acquisition"} for i in range(5)]
    bundle = {"runs": runs, "processing_results": [],
              "record_groups": [{"group_id": "g0", "member_run_keys": [r["run_key"] for r in runs]}]}
    row = cli.group_list_extras(bundle)["g0"]
    assert row == {"files": ["SYN_0", "SYN_1", "SYN_2"], "files_more": 2, "scans": 0, "reader": "spec_acquisition",
                   "cannot_export_reason": "no_scans"}


# --- 2. build-records compact; validate counts its reasons ------------------------------------------------------


def _confirm_all(bdir_: Path) -> int:
    b = M.load(bdir_)
    ids = [g["group_id"] for g in b["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES]
    M.decide(bdir_, target_ids=ids, decision="confirm", value=None, **BY)
    return len(ids)


def test_build_records_prints_counts_and_the_first_few_and_full_prints_every_draft(grouped, capsys):
    n = _confirm_all(grouped)
    assert n > cli.BUILD_ROWS_SHOWN
    code, out, _ = _run(capsys, "bundle", "build-records", grouped)
    assert code == 0
    compact = json.loads(out)
    assert compact["drafts_total"] == n == compact["complete"] + compact["incomplete"]
    assert len(compact["drafts"]) == cli.BUILD_ROWS_SHOWN and compact["drafts_omitted"] == n - cli.BUILD_ROWS_SHOWN
    assert compact["by_reason"]["incomplete"] == compact["incomplete"]
    index = json.loads((grouped / "drafts" / "index.json").read_text())
    assert len(index["drafts"]) == n  # the file keeps every row
    expected = {}
    for d in index["drafts"]:
        for p in d["missing_required"]:
            expected[p] = expected.get(p, 0) + 1
    assert compact["missing_required_by_field"] == expected
    assert "--full" in compact["full_list"]
    code, out, _ = _run(capsys, "bundle", "build-records", grouped, "--full")
    assert code == 0 and len(json.loads(out)["drafts"]) == n


def test_validate_counts_its_reasons_and_names_the_first_groups_plain_reasons(grouped, capsys, monkeypatch):
    n = _confirm_all(grouped)
    from isaac_api.local_import import portal as P

    monkeypatch.setattr(P, "run_portal_check", _portal("reject"))
    code, out, _ = _run(capsys, "bundle", "validate", grouped)
    assert code == 1
    v = json.loads(out)
    assert len(v["verdicts"]) == n and v["exportable"] == 0 and v["not_exportable"] == n
    assert sum(1 for x in v["verdicts"].values() if x == "incomplete") == v["by_reason"]["incomplete"]
    assert v["missing_required_by_field"] and all(isinstance(k, str) for k in v["missing_required_by_field"])
    first = v["not_exportable_first"]
    assert len(first) == R.REASONS_SHOWN and v["not_exportable_omitted"] == n - R.REASONS_SHOWN
    for row in first:
        report = json.loads((grouped / "validation" / f"{row['group_id']}.json").read_text())
        assert row["verdict"] == report["verdict"]
        assert row["reasons"] == R.plain_reasons(report["plain_summary"])
        assert not any(line.startswith("Website schema") for line in row["reasons"])
    assert list(v)[0] == "exportable"  # the counts come before the verdict map


# --- 3. a one-group question says its group; its id is unchanged -----------------------------------------------


def test_a_question_built_at_experiment_scope_for_one_group_says_that_group_and_keeps_its_id(counter):
    payload = Q.consolidate(M.load(counter))
    relabelled = [q for q in payload["questions"] if "id_scope" in q]
    assert relabelled
    for q in relabelled:
        assert q["id_scope"] == "experiment" and q["scope"].startswith("group:")
        assert list(q["per_scope_targets"]) == [q["scope"]]
        # THE ID hashes the scope it was built at, never the displayed one (DEC-91)
        parts = ((q["kind"], q["partition"] or "") if q["kind"] == "optional_values"
                 else (q["kind"], q["target_field_path"], q["partition"] or ""))
        assert q["question_id"] == Q._qid("experiment", *parts)
        assert q["question_id"] in {x["question_id"] for x in Q.filter_questions(payload, scope=q["scope"])}
    # a question that truly spans groups keeps the experiment scope
    multi = [q for q in payload["questions"] if q["scope"] == "experiment"]
    assert all(len(q["per_scope_targets"]) != 1 or "experiment" in q["per_scope_targets"] for q in multi)


# --- 4. runs rows carry the stem; findings name a run by stem or run id -----------------------------------------


def test_a_runs_row_carries_the_file_stem(grouped, capsys):
    code, out, _ = _run(capsys, "bundle", "list", grouped, "runs")
    stems = {r["run_id"]: r["stem"] for r in M.load(grouped)["runs"]}
    for item in json.loads(out)["items"]:
        assert item["stem"] == stems[item["run_id"]] and "path" not in item


def _finding(refs, key="runs") -> dict:
    return {"format": S.READINGS_FORMAT, "findings": [{
        "field_path": "context.environment", "value": "in_situ", "applies_to": {"scope": "runs", key: refs},
        "source": {"path": "SYN_notes.txt", "locator": "line 1"}, "quote": "synthetic quote", "strength": "inferred"}]}


def _env_targets(bundle, run_id):
    return {m["value_id"] for m in bundle["missing_values"] if m["run_id"] == run_id and m["target_field_path"] == "context.environment"}


def test_a_finding_names_a_run_by_its_stem_or_run_id(grouped):
    b = M.load(grouped)
    r1, r2 = b["runs"][0], b["runs"][1]
    assert _env_targets(b, r1["run_id"]) and _env_targets(b, r2["run_id"])
    for key in ("runs", "run_labels"):
        plan = S.readings_to_interpretations(b, _finding([r1["stem"], r2["run_id"]], key), model_id="m")
        assert plan["skipped"] == []
        assert {t["id"] for t, _ in plan["planned"]} == _env_targets(b, r1["run_id"]) | _env_targets(b, r2["run_id"])
    # the label still works where it names one run
    plan = S.readings_to_interpretations(b, _finding([r1["label"]]), model_id="m")
    assert {t["id"] for t, _ in plan["planned"]} == _env_targets(b, r1["run_id"])


def test_a_run_reference_naming_two_runs_is_refused_never_spread(grouped):
    b = copy.deepcopy(M.load(grouped))
    b["runs"][1]["label"] = b["runs"][0]["label"]  # two runs, one label (as `_12_1200mV` / `_1_1200mV` were)
    plan = S.readings_to_interpretations(b, _finding([b["runs"][0]["label"]]), model_id="m")
    assert plan["planned"] == []
    (skip,) = plan["skipped"]
    assert "more than one run" in skip["reason"] and b["runs"][0]["run_id"] in skip["reason"]
    # the run id is never ambiguous
    plan = S.readings_to_interpretations(b, _finding([b["runs"][1]["run_id"]]), model_id="m")
    assert plan["skipped"] == [] and {t["id"] for t, _ in plan["planned"]} == _env_targets(b, b["runs"][1]["run_id"])


def test_a_runs_row_shows_the_path_when_two_runs_share_a_stem(grouped, capsys, monkeypatch):
    b = M.load(grouped)
    twin = copy.deepcopy(b)
    twin["runs"][1]["stem"] = twin["runs"][0]["stem"]
    monkeypatch.setattr(cli, "_load", lambda _d: (twin, cli.EXIT_OK))
    code, out, _ = _run(capsys, "bundle", "list", grouped, "runs", "--limit", "3")
    items = json.loads(out)["items"]
    paths = S.run_paths(b)
    assert items[0]["path"] == paths[items[0]["run_id"]] and items[1]["path"] == paths[items[1]["run_id"]]
    assert "path" not in items[2]


# --- 5. the counter question takes defer -------------------------------------------------------------------------


def test_the_counter_question_can_be_deferred_and_grouping_is_unchanged(counter, capsys):
    (q,) = [q for q in Q.consolidate(M.load(counter))["questions"] if q["kind"] == "naming_counter_positions"]
    assert "defer" in q["allowed_decisions"] and "--decision defer" in q["answer_command"]
    ids, groups = _qids(counter), _groups_signature(counter)
    code, out, err = _run(capsys, "bundle", "decide", counter, "--question", q["question_id"], "--decision", "defer",
                          "--by", "Synthetic Scientist")
    assert code == 0, err
    said = json.loads(out)
    assert said["recorded"] == ["experiment"] and "Grouping is unchanged" in said["statement"]
    assert _run(capsys, "bundle", "group", counter, "--regroup")[0] == 0
    assert _groups_signature(counter) == groups
    payload = Q.consolidate(M.load(counter))
    assert _qids(counter) == ids  # the question stays, under its id
    (again,) = [x for x in payload["questions"] if x["question_id"] == q["question_id"]]
    assert again["deferred"]["by"] == "Synthetic Scientist"
    # replaying it records nothing new
    code, out, _ = _run(capsys, "bundle", "decide", counter, "--question", q["question_id"], "--decision", "defer",
                        "--by", "Synthetic Scientist")
    assert code == 0 and json.loads(out)["unchanged"] == ["experiment"]
    # a later answer supersedes the deferral
    code, _, err = _run(capsys, "bundle", "decide", counter, "--question", q["question_id"], "--decision",
                        B.NOT_COUNTER_DECISION, "--by", "Synthetic Scientist")
    assert code == 0, err
    assert Q.counter_deferral(M.load(counter)) is None
    assert B.validate_bundle(M.load(counter)) == []


def test_a_defer_after_an_answer_is_recorded_and_moves_no_position(counter, capsys):
    (q,) = [q for q in Q.consolidate(M.load(counter))["questions"] if q["kind"] == "naming_counter_positions"]
    pos = ",".join(map(str, q["positions"][:1]))
    assert _run(capsys, "bundle", "decide", counter, "--target", "experiment", "--decision", "set_counter_positions",
                "--positions", pos, "--by", "Synthetic Scientist")[0] == 0
    before = M.counter_positions(M.load(counter)), B.not_counter_positions(M.load(counter))
    code, out, _ = _run(capsys, "bundle", "decide", counter, "--target", "experiment", "--decision", "defer",
                        "--by", "Synthetic Scientist")
    assert code == 0 and json.loads(out)["recorded"] == ["experiment"]
    b = M.load(counter)
    assert (M.counter_positions(b), B.not_counter_positions(b)) == before
    assert Q.counter_deferral(b)["by"] == "Synthetic Scientist"


# --- 6. summary.md and the import output --------------------------------------------------------------------------


def test_the_summary_says_runs_in_no_file_name_group_never_group_none(pristine):
    b = copy.deepcopy(M.load(pristine))
    b["samples"][0]["group_token"] = None
    text = cli.render_summary(b)
    assert "group None" not in text and "- not in a file-name group: " in text


def test_the_conflict_count_says_why_it_differs_from_the_conflicting_values(tmp_path, capsys):
    out = tmp_path / "b"
    code, printed, _ = _run(capsys, "import", SEMANTICS, "--out", out)
    assert code == 0
    b = M.load(out)
    c = b["counts"]
    assert c["conflicts"] != c["conflicting_candidates"]  # the synthetic corpus has both kinds
    no_value = sum(1 for cf in b["conflicts"] if not cf.get("candidate_id"))
    line = next(x for x in (out / "summary.md").read_text().splitlines() if x.startswith("- Conflicts:"))
    assert f"Conflicts: {c['conflicts']} (" in line and f"{no_value} about files, not one value" in line
    assert f"on the {c['conflicting_candidates']} conflicting value(s)" in line
    assert f"{c['conflicts']} conflicts (" in printed and f"{no_value} about files, not one value" in printed
    # where every conflict is on a conflicting value, nothing extra is said
    plain = copy.deepcopy(b)
    plain["conflicts"] = [cf for cf in plain["conflicts"] if cf.get("candidate_id")]
    cand = {x["candidate_id"]: x for x in plain["candidates"]}
    plain["conflicts"] = [cf for cf in plain["conflicts"] if cand[cf["candidate_id"]]["value_state"] == "conflicting"]
    assert cli._conflict_breakdown(plain) == ""


# --- 7. export says what it wrote and refused ----------------------------------------------------------------------


def test_export_says_plainly_what_it_wrote_and_refused(bdir, tmp_path):
    _decide_everything(bdir)  # g1: complete, exportable
    b = M.load(bdir)
    b["record_groups"].append(_group("g2", b["runs"][1]))
    res = _na_result("g2", b["runs"][1])
    b["processing_results"].append(res)
    M.save_bundle(bdir, b)
    M.decide(bdir, target_ids=["g2"], decision="confirm", value=None, **BY)
    out = tmp_path / "records"
    result = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert (result["records_written"], result["groups_refused"]) == (1, 1)
    assert result["outcome"].startswith("Wrote 1 record(s), refused 1 group(s).")
    assert "exit code is 1" in result["outcome"] and str(out) in result["outcome"]
    assert list(result)[0] == "outcome" and cli.compact_export(result)["outcome"] == result["outcome"]
    assert R.export_outcome(0, 3, 0, out) == "Wrote 0 record(s), refused 3 group(s). Nothing was written (exit 1)."
    assert R.export_outcome(2, 0, 0, out).endswith("(exit 0).")

