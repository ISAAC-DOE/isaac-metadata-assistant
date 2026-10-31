"""Polish c7-w: the local-only Local Imports page says what the command line says. SYNTHETIC bundles only (the
committed multi-operator corpus, the SYN counter folder, the c6 "older build" bundle); no real data.

Pinned, each by behaviour:

* The progress page counts processing by GROUP, with the minimum's own curve state (``questions._curve``): a group
  with an ISAAC and an Athena curve awaiting a decision is ONE group, and once either is approved it is none.
* A group the protocol does not apply to (``no_xas_channel``) and one whose runs list no scan (``no_scans``) are
  said apart, as ``bundle list <dir> groups`` says them; a group with scans and no result says "run `isaac process`
  first", never "approve its processing result" — in the minimum (CLI and page) and on the progress page.
* A dry run says what ``decide --dry-run`` says ("Would record: …"), with the counter answer's regroup preview,
  before anything is written; the write's reply carries decide's own statement.
* ``scope`` gives the scope's counts, as ``bundle questions --scope`` does, with the whole bundle's beside them.
* ``bundle check``'s held-in-memory line is said on the page too.
* A per-group question a beamtime question covers names that question by id AND by its own words.
* A defer given through the page is shown back as deferred (who, when), from the bundle.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from tests_support_records import pristine_bundle  # noqa: F401
from test_local_import_polish_c5a import syn  # noqa: F401  (fixture of the c6 fixtures)
from test_local_import_polish_c6a import noted_pristine, plain_pristine  # noqa: F401  (fixtures)
from test_local_import_polish_c6r import _held_ids, older  # noqa: F401  (fixture)

BY = "Synthetic Scientist"
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123), headers={LB.LOCAL_HEADER: "1"})


def _client(root: Path, monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(root))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    return TestClient(create_app(), **LOCAL)


@pytest.fixture()
def grouped(pristine_bundle, tmp_path):
    bdir = tmp_path / "bundles" / "alpha"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    return bdir


def _version(client, name: str) -> str:
    return next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == name)["bundle_version"]


def _result(rid: str, gid: str, state: str = B.STATE_NEEDS_REVIEW, **over) -> dict:
    return {"result_id": rid, "group_id": gid, "source": "isaac_protocol", "state": state,
            "applicability": {"status": "applicable"}, **over}


def _na(rid: str, gid: str, code: str) -> dict:
    return _result(rid, gid, applicability={"status": B.NOT_APPLICABLE, "reason_code": code})


# --- processing, counted by group ---------------------------------------------------------------------


def test_an_isaac_and_an_athena_curve_of_one_group_are_one_group_and_none_once_either_is_approved(grouped):
    b = M.load(grouped)
    g1 = b["record_groups"][0]["group_id"]
    b["processing_results"] = [_result("p-isaac", g1), _result("p-athena", g1, source="athena_project")]
    blocks = LB.progress(grouped, b, {"status": "VALID"})["blocks_export"]
    assert "1 record group(s) have a processing result awaiting a decision and no approved curve." in blocks, blocks
    assert not [s for s in blocks if "processing result(s) are not approved" in s], blocks
    assert Q._curve(b, g1)["state"] in ("curve", "no_curve")
    b["processing_results"][1]["state"] = B.STATE_SCIENTIST_CONFIRMED  # the Athena curve approved
    assert Q._curve(b, g1)["state"] == "approved"
    blocks = LB.progress(grouped, b, {"status": "VALID"})["blocks_export"]
    assert not [s for s in blocks if "awaiting a decision" in s], blocks


def test_no_protocol_and_no_scan_are_said_apart_as_bundle_list_groups_says_them(grouped):
    b = M.load(grouped)
    g1, g2, g3 = (g["group_id"] for g in b["record_groups"][:3])
    scanless = set(b["record_groups"][1]["member_run_keys"])
    for r in b["runs"]:
        if r["run_key"] in scanless:
            r["scan_count"] = 0
    b["processing_results"] = [_na("p-1", g1, B.NA_NO_XAS_CHANNEL), _na("p-3", g3, B.NA_NO_SCANS)]
    extras = cli.group_list_extras(b)
    assert extras[g1]["cannot_export_reason"] == "processing_not_applicable:no_xas_channel"
    assert extras[g2]["cannot_export_reason"] == "no_scans"
    assert extras[g3]["cannot_export_reason"] == "processing_not_applicable:no_scans"
    blocks = LB.progress(grouped, b, {"status": "VALID"})["blocks_export"]
    assert ("1 group(s) have no applicable processing protocol (no_xas_channel: 1), so they cannot become complete "
            "records yet.") in blocks, blocks
    assert ("2 group(s) list no scan (no_scans), so there is nothing to process and they cannot become complete records "
            "as they stand.") in blocks, blocks
    # the other six live groups have scans and no result: nothing to approve until `isaac process` runs
    assert "6 record group(s) have no processing result to approve: run `isaac process` first." in blocks, blocks


# --- the minimum: "run isaac process first" (CLI and page) ---------------------------------------------


def test_a_group_with_scans_and_no_processing_is_told_to_run_isaac_process_first(grouped, capsys, monkeypatch, tmp_path):
    b = M.load(grouped)
    assert not b.get("processing_results")
    mfo = Q.minimum_answers_for_one_group(Q.consolidate(b), b, bundle_dir=grouped)
    assert Q.NOT_PROCESSED_YET in mfo["plus_decisions"], mfo["plus_decisions"]
    assert "approve its processing result" not in mfo["plus_decisions"]
    assert "`isaac process`" in Q.NOT_PROCESSED_YET
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(grouped), "--limit", "1"]) == 0
    cli_mfo = json.loads(capsys.readouterr().out)["minimum_for_one_group"]
    assert cli_mfo["plus_decisions"] == mfo["plus_decisions"]
    client = _client(grouped.parent, monkeypatch, tmp_path)
    page = client.get("/api/local-bundles/alpha/questions", params={"limit": 1}).json()
    assert page["minimum_for_one_group"]["plus_decisions"] == mfo["plus_decisions"]
    prog = client.get("/api/local-bundles/alpha/progress").json()["progress"]
    assert prog["minimum_for_one_group"]["plus_decisions"] == mfo["plus_decisions"]
    # every result rejected: re-process, still never "approve"
    gid = mfo["group_id"]
    b["processing_results"] = [_result("p-gone", gid, state=B.STATE_REJECTED)]
    again = Q.minimum_answers_for_one_group(Q.consolidate(b), b, scope=f"group:{gid}")
    assert not [p for p in again["plus_decisions"] if "approve" in p], again["plus_decisions"]
    assert any(p.startswith("re-process it") for p in again["plus_decisions"]), again["plus_decisions"]


# --- the questions route: scope counts, covered_by --------------------------------------------------------


def test_a_scoped_page_gives_the_scopes_counts_as_the_cli_does(grouped, capsys, monkeypatch, tmp_path):
    b = M.load(grouped)
    scope = f"group:{b['record_groups'][0]['group_id']}"
    payload = Q.consolidate(b)
    client = _client(grouped.parent, monkeypatch, tmp_path)
    page = client.get("/api/local-bundles/alpha/questions", params={"scope": scope}).json()
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(grouped), "--scope", scope]) == 0
    out = json.loads(capsys.readouterr().out)
    assert page["counts"] == out["counts"] == Q.scope_counts(payload, scope)
    assert page["counts"]["scope"] == scope
    assert page["counts_whole_bundle"] == payload["counts"]
    assert out["counts_whole_bundle"]["total"] == page["counts_whole_bundle"]["total"] > page["counts"]["total"]
    unscoped = client.get("/api/local-bundles/alpha/questions").json()
    assert "counts_whole_bundle" not in unscoped and unscoped["counts"] == payload["counts"]


def test_a_covered_question_names_the_beamtime_question_by_id_and_words(grouped, monkeypatch, tmp_path):
    payload = Q.consolidate(M.load(grouped))
    covered = [q for q in payload["questions"] if q.get("covered_by", "").startswith("Q-")]
    assert covered
    text_of = {q["question_id"]: q["text"] for q in payload["questions"]}
    client = _client(grouped.parent, monkeypatch, tmp_path)
    page = client.get("/api/local-bundles/alpha/questions").json()
    shown = {q["question_id"]: q for q in page["questions"]}
    for q in covered:
        cover = shown[q["question_id"]]["display"]["covered_by"]
        assert cover == {"question_id": q["covered_by"], "text": text_of[q["covered_by"]]}
        assert q["covered_by"] in shown[q["question_id"]]["why"]
    assert all("covered_by" not in q["display"] for q in page["questions"] if not q.get("covered_by"))
    # the covering question's words may state extracted values: each is recorded as shown, as on its own card
    b = M.load(grouped)
    stated = {cid for q in covered for cid in Q.confirm_value_shown(b, Q.question(payload, q["covered_by"]))}
    exposed = {e["target"]["id"] for e in b.get("exposures") or () if e["target"]["kind"] == "candidate"}
    assert stated <= exposed


# --- the dry run says what decide --dry-run says --------------------------------------------------------


def test_a_dry_run_says_the_decide_statement_before_anything_is_written(grouped, monkeypatch, tmp_path):
    qid = next(q["question_id"] for q in Q.consolidate(M.load(grouped))["questions"] if q["kind"] == "confirm_absorber")
    raw = M.decide_question(grouped, question_id=qid, decision="set_absorber", value=None, element="Fe", edge="K",
                            by=BY, orcid=None, dry_run=True)
    assert raw["statement"].startswith("Would record") and "Nothing was written" in raw["statement"]
    client = _client(grouped.parent, monkeypatch, tmp_path)
    v0 = _version(client, "alpha")
    r = client.post(f"/api/local-bundles/alpha/questions/{qid}/answer",
                    json={"decision": "set_absorber", "element": "Fe", "edge": "K", "by": BY, "expected_version": v0,
                          "dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["would_say"] == raw["statement"]
    assert "kept_per_group_answers" not in body and "regroup_preview" not in body  # only when decide says them
    assert "Nothing was written" in body["statement"]
    assert M.bundle_version(grouped) == v0  # a dry run writes nothing
    # ...and the write's own reply carries decide's statement, which the page shows
    w = client.post(f"/api/local-bundles/alpha/questions/{qid}/answer",
                    json={"decision": "set_absorber", "element": "Fe", "edge": "K", "by": BY, "expected_version": v0})
    assert w.status_code == 200, w.text
    assert w.json()["result"]["statement"] == raw["statement"][len("Would record: "):-len(" Nothing was written.")]


def test_a_counter_dry_run_says_what_the_next_regroup_would_join(tmp_path, monkeypatch):
    from test_local_import_capture_decisions import _grouped_stems

    b = _grouped_stems(tmp_path / "work", ["Q4_SYNcat_pH2_400mV_15", "Q4_SYNcat_pH2_400mV_16"])
    root = tmp_path / "bundles"
    root.mkdir()
    shutil.copytree(b, root / "counter")
    bdir = root / "counter"
    asked = [q for q in Q.consolidate(M.load(bdir))["questions"] if q["kind"] == "naming_counter_positions"]
    if not asked:
        pytest.skip("this grouping asks no counter question")
    q = asked[0]
    client = _client(root, monkeypatch, tmp_path)
    v0 = _version(client, "counter")
    positions = q.get("positions")[-1:]
    raw = M.decide_question(bdir, question_id=q["question_id"], decision="set_counter_positions", value=None,
                            positions=positions, by=BY, orcid=None, dry_run=True)
    r = client.post(f"/api/local-bundles/counter/questions/{q['question_id']}/answer",
                    json={"decision": "set_counter_positions", "positions": positions, "by": BY, "expected_version": v0,
                          "dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["regroup_preview"] == raw["regroup_preview"]
    assert "isaac bundle group <bundle_dir> --regroup" in body["regroup_preview"]["statement"]
    assert body["would_say"] == raw.get("statement")
    assert M.bundle_version(bdir) == v0


# --- bundle check's held line ---------------------------------------------------------------------------


def test_the_page_says_the_values_bundle_check_holds_in_memory(older, tmp_path, monkeypatch, capsys):
    held = _held_ids(older)
    assert held
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(older)]) == 0
    printed = capsys.readouterr().out
    client = _client(older.parent, monkeypatch, tmp_path)
    listing = next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == "older")
    for check in (listing["check"], client.get("/api/local-bundles/older/progress").json()["progress"]["check"]):
        assert check["status"] == "VALID" and check["held_in_memory"] == len(held)
        assert B.held_statement(len(held)) in check["held_statement"] and B.held_statement(len(held)) in printed
        assert "nothing is written" in check["held_statement"]


def test_a_bundle_holding_nothing_says_nothing_held(grouped, tmp_path, monkeypatch):
    client = _client(grouped.parent, monkeypatch, tmp_path)
    check = next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == "alpha")["check"]
    assert check["status"] == "VALID" and "held_statement" not in check and "held_in_memory" not in check


# --- a defer through the page ---------------------------------------------------------------------------


def test_a_defer_given_on_the_page_is_shown_back_as_deferred(grouped, tmp_path, monkeypatch):
    client = _client(grouped.parent, monkeypatch, tmp_path)
    page = client.get("/api/local-bundles/alpha/questions").json()
    q = next(q for q in page["questions"] if q["kind"] == "missing_value" and "defer" in q["allowed_decisions"]
             and len(q["per_scope_targets"]) == 1 and len(q["targets"]) == 1)
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "defer", "by": BY, "expected_version": page["bundle"]["bundle_version"]})
    assert r.status_code == 200, r.text
    after = client.get("/api/local-bundles/alpha/questions").json()
    again = next(x for x in after["questions"] if x["question_id"] == q["question_id"])
    assert again["deferred"]["by"] == BY and again["deferred"]["decided_utc"]
    assert after["counts"]["deferred"] == 1
