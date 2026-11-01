"""Skill polish, cycle 1 (processing / decide / export replies). Synthetic only.

* ``decide --decision approve`` on a processing result with NO CURVE (a ``fail`` with no output file,
  e.g. ``no_usable_scan``) is refused, naming the real options; ``needs_changes`` says what it does.
* ``isaac process`` processes only LIVE groups by default; a rejected / merged / split group's results
  and the decisions on them are kept as they were, and the reply counts them apart.
* ``bundle validate`` says a REJECTED result was rejected (not "no processing result exists"), and for
  an approved result with no curve gives a next step that does not loop back to "re-run process".
* ``bundle list processing-results`` pages the results compactly; ``bundle export`` with nothing
  exportable is compact by default (``--full`` prints every refusal); ``crosscheck-plan`` caps
  locators, orders high-value targets first and says which items can be excerpted.
* An Athena project is listed by ``bundle list unread`` as read by ``isaac process``; ``process``
  says in one line why no Athena group matched.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R
from isaac_api.local_import.processing import run as RUN

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY,
    SEMANTICS,
    _add_group,
    _decide_everything,
    _portal,
    bdir,
    fake_upstream,
    pristine,
)


def _run(capsys, *argv):
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def _no_curve(bdir: Path) -> None:
    """p1 becomes what BL4-3's dilute standards gave: a fail with no output file."""
    b = M.load(bdir)
    r = b["processing_results"][0]
    r["outputs"] = {"files": [], "e0_eV": None, "edge_step": None, "points": None}
    r["qc"] = {"metrics": {}, "verdict": "fail", "reasons": ["no_usable_scan"]}
    r["failure"] = {"code": "no_usable_scan", "detail": "too_few_points"}
    M.save_bundle(bdir, b)


# --- 1. approving a result with no curve is refused ----------------------------------------------


def test_approving_a_result_with_no_curve_is_refused_with_the_real_options(bdir, capsys):
    _add_group(bdir)
    _no_curve(bdir)
    before = (bdir / "bundle.json").read_bytes()
    code, _, err = _run(capsys, "bundle", "decide", str(bdir), "--target", "p1", "--decision", "approve",
                        "--qc-status", "valid", "--by", BY["by"])
    assert code == 2
    assert "no curve" in err and "no_usable_scan" in err
    assert "--target p1 --decision reject" in err and "needs_changes" in err
    assert "--target g1 --decision reject" in err  # leave the group out
    assert "Nothing was recorded" in err
    assert (bdir / "bundle.json").read_bytes() == before
    # rejecting it is still possible
    M.decide(bdir, target_ids=["p1"], decision="reject", value=None, **BY)
    assert M.load(bdir)["processing_results"][0]["state"] == "rejected"


def test_needs_changes_says_what_it_does(bdir):
    _add_group(bdir)
    out = M.decide(bdir, target_ids=["p1"], decision="needs_changes", value=None, **BY)
    said = out["statement"]
    assert "needs_review" in said and "not approved" in said
    assert "--params-file" in said and "--group g1" in said  # how a changed result comes about
    assert "keeps it as it is" in said  # a plain re-run does not replace it


# --- 3. validate: a rejected result, and an approved result with no curve -------------------------


def test_validate_says_the_result_was_rejected_not_that_none_exists(bdir):
    _decide_everything(bdir)
    M.decide(bdir, target_ids=["p1"], decision="reject", value=None, **BY)
    R.build_records(bdir)
    R.validate_records(bdir, run_portal=_portal("publish"))
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    fix = report["processing_fix"]
    assert "no processing result exists" not in fix
    assert "its processing result was rejected (p1)" in fix
    assert "--params-file" in fix and "--target g1 --decision reject" in fix


def test_validate_for_an_approved_result_with_no_curve_does_not_loop(bdir):
    _decide_everything(bdir)
    _no_curve(bdir)  # an approval made before the guard existed: hand-made, as the BL4-3 bundle holds
    b = M.load(bdir)
    for d in b["scientist_decisions"]:
        if d["target"]["id"] == "p1":
            d["approved_files"] = []
    M.save_bundle(bdir, b)
    R.build_records(bdir)
    R.validate_records(bdir, run_portal=_portal("publish"))
    fix = json.loads((bdir / "validation" / "g1.json").read_text())["processing_fix"]
    assert "Re-run `isaac process <bundle_dir>" not in fix  # the old, looping advice
    assert "has no curve" in fix and "no_usable_scan" in fix
    assert "--target p1 --decision reject" in fix and "--target g1 --decision reject" in fix
    assert "--params-file" in fix


def test_validate_never_asks_to_approve_an_undecided_result_with_no_curve(bdir):
    _decide_everything(bdir)
    M.decide(bdir, target_ids=["p1"], decision="needs_changes", value=None, **BY)  # undecided again
    _no_curve(bdir)
    R.build_records(bdir)
    R.validate_records(bdir, run_portal=_portal("publish"))
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    fix = report["processing_fix"]
    assert "--decision approve" not in fix  # decide would refuse it
    assert "has no curve, so there is nothing to approve: p1 (no_usable_scan: too_few_points)" in fix
    assert "--target p1 --decision reject" in fix and "--target g1 --decision reject" in fix
    assert report["processing_blocker"] == "processing_result_has_no_curve"


# --- 4a. bundle list processing-results ------------------------------------------------------------


def test_list_processing_results_is_compact_and_paged(bdir, capsys):
    _add_group(bdir)
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "processing-results")
    page = json.loads(out)
    assert code == 0 and page["kind"] == "processing-results" and page["total"] == 1
    [row] = page["items"]
    assert row["result_id"] == "p1" and row["group_id"] == "g1" and row["group_status"] == "proposed"
    assert row["verdict"] == "pass" and row["applicability"] == "applies" and row["state"] == "candidate_extracted"
    assert set(row) >= {"failure", "flags", "metrics", "plot", "athena_agreement", "channel"}
    assert "inputs" not in row and "steps" not in row
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "processing-results", "--offset", "1")
    assert code == 0 and json.loads(out)["items"] == []
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "processing-results", "--state", "rejected")
    assert code == 0 and json.loads(out)["total"] == 0


# --- 4b / 6. export with nothing exportable --------------------------------------------------------


def _many_unexportable_groups(bdir: Path, n: int) -> None:
    b = M.load(bdir)
    assert len(b["runs"]) >= n
    for i in range(n):
        b["record_groups"].append(
            {"group_id": f"g{i}", "experiment_key": "exp", "member_run_keys": [b["runs"][i]["run_key"]],
             "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
             "split_reasons": [], "status": "proposed", "questions": []})
    M.save_bundle(bdir, b)
    M.decide(bdir, target_ids=[f"g{i}" for i in range(n)], decision="confirm", value=None, **BY)


def test_export_with_nothing_exportable_is_compact_and_says_there_is_nothing_to_dry_run(bdir, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("isaac_api.local_import.portal.run_portal_check", _portal("publish"))
    _many_unexportable_groups(bdir, 7)
    out_dir = tmp_path / "records"
    code, out, _ = _run(capsys, "bundle", "export", str(bdir), "--out", str(out_dir))
    reply = json.loads(out)
    assert code == 1 and reply["exported"] == []
    assert reply["refused_total"] == 7 and len(reply["refused"]) == 3 and reply["refused_omitted"] == 4
    assert reply["refused_by_reason"]["incomplete"] == 7
    assert reply["missing_required_by_field"]
    assert "--full" in reply["refused_full_list"]
    assert "nothing to dry-run" in reply["statement"] and not out_dir.exists()
    code, full, _ = _run(capsys, "bundle", "export", str(bdir), "--out", str(out_dir), "--full")
    assert code == 1 and len(json.loads(full)["refused"]) == 7
    assert len(full) > len(out)
    # upload's behaviour is unchanged
    assert _run(capsys, "bundle", "upload", str(out_dir), "--dry-run")[0] == cli.EXIT_NOT_FOUND


# --- 4c. crosscheck-plan ---------------------------------------------------------------------------


def test_crosscheck_plan_caps_locators_orders_high_value_first_and_marks_excerptable(pristine):
    b = M.load(pristine)
    run = b["runs"][0]
    extra = [dict(run["scans"][0], scan_index=100 + i) for i in range(12)]
    run["scans"] = list(run["scans"]) + extra
    plan = M.crosscheck_plan(b)
    items = plan["items"]
    assert all(len(i["locators"]) <= M.MAX_PLAN_LOCATORS for i in items)
    big = next(i for i in items if i["target"] == {"kind": "run", "id": run["run_id"]} and i["category"] == "run_association")
    assert big["locators_total"] > M.MAX_PLAN_LOCATORS and len(big["locators"]) == M.MAX_PLAN_LOCATORS
    rank = {c: n for n, c in enumerate(M.CROSSCHECK_ORDER)}
    excerptable = [i for i in items if i["excerptable"]]
    assert [rank[i["category"]] for i in excerptable] == sorted(rank[i["category"]] for i in excerptable)
    first_not = next(n for n, i in enumerate(items) if not i["excerptable"])
    assert all(not i["excerptable"] for i in items[first_not:])  # every excerptable item comes first
    missing = [i for i in items if i["target"]["kind"] == "missing_value"]
    assert missing and all(i["field_path"] and not i["excerptable"] and i["not_excerptable_because"] for i in missing)
    assert plan["excerptable"] == len(excerptable) and plan["not_excerptable"] == len(items) - len(excerptable)
    with pytest.raises(M.MutationRefused, match="nothing in the source states it"):
        M.excerpt(b, missing[0]["target"]["id"], source=str(SEMANTICS))


def test_crosscheck_plan_cli_pages_after_ordering(pristine, capsys):
    code, out, _ = _run(capsys, "bundle", "crosscheck-plan", str(pristine), "--limit", "5")
    plan = json.loads(out)
    assert code == 0 and plan["returned"] == 5 and "statement_excerptable" in plan


# --- 5. Athena projects: listed as read by processing; process says why nothing matched -------------


def test_an_athena_project_is_listed_as_read_by_processing(tmp_path, capsys):
    src = tmp_path / "beamtime"
    shutil.copytree(SEMANTICS, src)
    (src / "SYN_analysis.prj").write_bytes(b"\x1f\x8b SYNTHETIC not a real project")
    out = tmp_path / "b"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    code, page, _ = _run(capsys, "bundle", "list", str(out), "unread", "--limit", "200")
    rows = [r for r in json.loads(page)["items"] if r["relative_path"].endswith(".prj")]
    assert code == 0 and rows
    assert all("isaac process" in r["read_by"] for r in rows)


def test_process_says_in_one_line_why_no_athena_group_matched():
    groups = [{"group_id": "g1", "_stems": ["03_SYN_dry_015"], "_has_scans": True}]
    # (``_a_001``, the XDC scan-file suffix measured on BL4-3, is accepted since match_by_name.v1)
    entries = [{"names": ["03_syn_dry_015_b_001"], "label": "x"}, {"names": ["03_syn_dry_015_b_002"], "label": "y"},
               {"names": ["unrelated"], "label": "z"}]
    line = RUN.athena_match_statement(groups, entries, matched={}, notes=[])
    assert "3 Athena group(s)" in line and "matched no record group" in line
    assert "2 of them" in line and "'_b_001'" in line
    assert RUN.athena_match_statement(groups, [], matched={}, notes=[]) is None
    assert RUN.athena_match_statement(groups, entries, matched={"g1": {}}, notes=[]) is None


# --- 2. process only live groups ---------------------------------------------------------------------


def _fake_process_bundle(tag: dict):
    def fake(bundle_dir, *, group_ids=None, skip_group_ids=(), bundle=None, **_k):
        gids = [g["group_id"] for g in bundle["record_groups"]
                if (not group_ids or g["group_id"] in group_ids) and g["group_id"] not in set(skip_group_ids)]
        tag["processed"] = gids
        return {"status": "processed", "summary": {"lines": ["synthetic"]}, "processing_results": [
            {"result_id": f"proc-{g}-r-{tag['run']}-isaac", "group_id": g, "protocol_id": "isaac.xas.v0",
             "protocol_version": "0.1", "protocol_status": "draft_unreviewed", "source": "isaac_protocol",
             "inputs": [], "steps": [], "outputs": {"files": [], "e0_eV": None, "edge_step": None, "points": None},
             "qc": {"metrics": {}, "verdict": "warn"}, "comparison": None, "state": "needs_review"} for g in gids]}
    return fake


@pytest.fixture()
def grouped(tmp_path, capsys):
    out = tmp_path / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    capsys.readouterr()
    return out


def test_process_skips_groups_that_are_no_longer_live_and_keeps_their_results(grouped, capsys, monkeypatch):
    tag = {"run": "a"}
    monkeypatch.setattr(RUN, "process_bundle", _fake_process_bundle(tag))
    assert cli.main(["process", str(grouped), "--source", str(SEMANTICS)]) == 0
    capsys.readouterr()
    first = {r["group_id"]: r for r in M.load(grouped)["processing_results"]}
    dead, other = sorted(first)[:2]
    M.decide(grouped, target_ids=[dead], decision="reject", value=None, **BY)
    M.decide(grouped, target_ids=[first[dead]["result_id"]], decision="needs_changes", value=None, **BY)
    tag["run"] = "b"
    code, out, _ = _run(capsys, "process", str(grouped), "--source", str(SEMANTICS))
    reply = json.loads(out)
    assert code == 0 and dead not in tag["processed"] and other in tag["processed"]
    assert reply["not_live_groups"]["groups"] == 1 and reply["not_live_groups"]["by_status"] == {"rejected": 1}
    assert reply["not_live_groups"]["results_kept"] == 1
    assert any("not processed" in line for line in reply["summary"]["lines"])
    after = {r["group_id"]: r for r in M.load(grouped)["processing_results"]}
    assert after[dead] == first[dead] | {"state": "needs_review"}  # kept as it was, its decision intact
    assert after[other]["result_id"].endswith("-r-b-isaac")
    assert len(after) == len(first)
    # naming a non-live group with --group still processes it
    tag["run"] = "c"
    assert cli.main(["process", str(grouped), "--source", str(SEMANTICS), "--group", dead]) == 0
    assert tag["processed"] == [dead]


def test_process_with_no_live_group_is_refused(grouped, capsys, monkeypatch):
    monkeypatch.setattr(RUN, "process_bundle", _fake_process_bundle({"run": "a"}))
    gids = [g["group_id"] for g in M.load(grouped)["record_groups"]]
    M.decide(grouped, target_ids=gids, decision="reject", value=None, **BY)
    code, _, err = _run(capsys, "process", str(grouped), "--source", str(SEMANTICS))
    assert code == 2 and "no live record group" in err.lower()


def test_real_process_keeps_live_result_ids_and_a_rejected_groups_result(grouped, capsys):
    pytest.importorskip("numpy")
    pytest.importorskip("larch")
    assert cli.main(["process", str(grouped), "--source", str(SEMANTICS)]) == 0
    capsys.readouterr()
    first = {r["result_id"]: r for r in M.load(grouped)["processing_results"]}
    by_group = {r["group_id"]: r["result_id"] for r in first.values() if r["source"] == "isaac_protocol"}
    dead = sorted(by_group)[0]
    M.decide(grouped, target_ids=[dead], decision="reject", value=None, **BY)
    code, out, _ = _run(capsys, "process", str(grouped), "--source", str(SEMANTICS))
    reply = json.loads(out)
    assert code == 0 and reply["not_live_groups"]["groups"] == 1
    assert reply["summary"]["groups"] == len(by_group) - 1
    after = {r["result_id"]: r for r in M.load(grouped)["processing_results"]}
    assert set(after) == set(first)  # live ids unchanged; the rejected group's result kept
    assert cli.main(["bundle", "check", str(grouped)]) == 0
