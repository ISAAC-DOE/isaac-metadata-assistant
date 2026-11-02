"""The Local Imports page brought up to date with skill rounds 5-7 (``isaac_api/local_bundles.py``). SYNTHETIC
fixtures only: the r6i start-time corpus (``tests/fixtures/bl15/semantics/multi_operator_corpus``, edited in a tmp
copy) and the committed multi-operator bundle. No real data.

What is pinned, each by behaviour:

* The beamtime-wide start-time question (``stated_utc_start_times``) is LISTED on the page, as one card
  (``answer_kind: start_times``); each per-group start-time question it answers at once stays listed and answerable,
  names it (``answered_at_once_by``), and loses only the sentence that names it by id.
* Its dry run lists every group it would write (it used to list none), and its write leaves the bundle byte-identical
  to `isaac bundle decide --question <id> --decision confirm` on a copy. Question ids are unchanged.
* ``display.text`` / ``display.why`` are the command line's sentences less its own instructions; ``text`` is untouched.
* Progress says groups that cannot export once, by reason, and counts them nowhere else; it lists the scientist's
  unmatched Athena merges read-only, as `bundle list <dir> athena-merges` reads them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_polish_r6i import _corpus

BY = "Synthetic Scientist"
FIXED_UTC = "2099-01-01T00:00:00Z"
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123), headers={LB.LOCAL_HEADER: "1"})
QID = Q.STATED_UTC_START_QUESTION_ID


@pytest.fixture(scope="module")
def start_bundle(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("r7page")
    out = tmp / "grouped"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def root(tmp_path, start_bundle, monkeypatch):
    r = tmp_path / "bundles"
    r.mkdir()
    for name in ("alpha", "beta"):
        shutil.copytree(start_bundle, r / name)
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(r))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    monkeypatch.setattr(M, "now_utc", lambda: FIXED_UTC)
    LB._check_memo.clear()
    return r


@pytest.fixture()
def client(root):
    return TestClient(create_app(), **LOCAL)


def _files(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file() and p.name != ".bundle.lock"}


def _version(client, name="alpha"):
    return next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == name)["bundle_version"]


def _page(client, name="alpha"):
    r = client.get(f"/api/local-bundles/{name}/questions")
    assert r.status_code == 200, r.text
    return r.json()


def test_the_beamtime_start_time_question_is_one_card_and_each_group_stays_answerable(client):
    page = _page(client)
    by_id = {q["question_id"]: q for q in page["questions"]}
    beam = by_id.get(QID)
    assert beam is not None, "the beamtime start-time question is listed"
    assert beam["kind"] == Q.STATED_UTC_START_KIND and beam["display"]["answer_kind"] == "start_times"
    assert beam["display"]["settles_many"] is True
    nested = [q for q in page["questions"] if q.get("answered_at_once_by") == QID]
    assert len(nested) == beam["answers_at_once"] == 3
    for q in nested:
        # the sentence that names the beamtime question by id is the command line's; the page shows the card instead
        assert Q.answered_at_once_sentence(QID).strip() not in q["text"]
        assert q["display"]["answer_kind"] == "conflict" and "correct" in q["allowed_decisions"]
    # the page's own wording drops the command-line instruction and keeps the rest word for word
    assert "--only" in beam["text"] and "--only" not in beam["display"]["text"]
    assert beam["display"]["text"].startswith("One answer for the start time of 3 groups.")


def test_its_dry_run_lists_every_group_and_its_write_equals_the_cli_byte_for_byte(client, root):
    before = _files(root / "alpha")
    r = client.post(f"/api/local-bundles/alpha/questions/{QID}/answer",
                    json={"decision": "confirm", "by": BY, "expected_version": _version(client), "dry_run": True})
    assert r.status_code == 200, r.text
    dry = r.json()
    assert len(dry["would_record"]) == 3 and dry["scopes_total"] == 3
    assert all(g["scope"].startswith("group:") for g in dry["by_scope"])
    assert dry["would_say"].startswith("Would record the start time of 3 group(s)")
    assert _files(root / "alpha") == before  # a dry run writes nothing

    assert cli.main(["bundle", "decide", str(root / "beta"), "--question", QID, "--decision", "confirm", "--by", BY]) == 0
    r = client.post(f"/api/local-bundles/alpha/questions/{QID}/answer",
                    json={"decision": "confirm", "by": BY, "expected_version": _version(client)})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["groups_recorded"] == 3
    assert _files(root / "alpha") == _files(root / "beta")
    # answered: not asked again, and its dry run now has nothing to write
    assert QID not in {q["question_id"] for q in _page(client)["questions"]}


def test_a_group_that_already_holds_its_own_start_keeps_it_and_is_not_previewed(client, root):
    nested = [q for q in _page(client)["questions"] if q.get("answered_at_once_by") == QID]
    first = nested[0]
    r = client.post(f"/api/local-bundles/alpha/questions/{first['question_id']}/answer",
                    json={"decision": "correct", "value": "2100-01-01T00:00:00Z", "by": BY,
                          "expected_version": _version(client)})
    assert r.status_code == 200, r.text
    beam = next(q for q in _page(client)["questions"] if q["question_id"] == QID)
    dry = client.post(f"/api/local-bundles/alpha/questions/{QID}/answer",
                      json={"decision": "confirm", "by": BY, "expected_version": _version(client), "dry_run": True}).json()
    assert first["targets"][0]["id"] not in dry["would_record"]
    # it no longer reaches that group, so the preview lists exactly the two it still reaches
    assert sorted(dry["would_record"]) == sorted(t["id"] for t in beam["targets"]) and len(dry["would_record"]) == 2


def test_page_words_drops_only_the_command_line_instructions():
    said = ("The sources disagree (field_disagreement, x). These readings are local clock times, so they cannot be "
            "recorded: x takes only a UTC instant, and `confirm --value <one reading>` is refused. If none fits, keep "
            "it (--value \"<word>\" --as-said); use --decision defer only if unknown. Each keeps its id: answer one of "
            "them, or add --only group:<id> here for one group. Recommended: isaac bundle decide <bundle_dir> "
            "--question Q-1 --by \"<your name>\"")
    assert LB.page_words(said) == ("The sources disagree (field_disagreement, x). These readings are local clock "
                                   "times, so they cannot be recorded: x takes only a UTC instant. Each keeps its id: "
                                   "answer one of them. Recommended.")
    assert LB.page_words(None) is None and LB.page_words("Plain words.") == "Plain words."


def test_progress_lists_the_unmatched_athena_merges_read_only(client, root):
    proc = root / "alpha" / "processing"
    proc.mkdir(exist_ok=True)
    merges = [{"athena_label": f"SYN merge {i}", "in": [{"prj_relative_path": "SYN_project.prj", "athena_group": f"g{i}"}],
               "candidates": [{"group_id": "rg-syn", "group_name": "SYN_group", "differs_in": "set-point"}],
               "groups_in_project": ["rg-syn"]} for i in range(LB.ATHENA_MERGES_SHOWN + 2)]
    (proc / "processing_results.json").write_text(json.dumps({"athena": {"unmatched_merges": merges}}), encoding="utf-8")
    before = _files(root / "alpha")
    p = client.get("/api/local-bundles/alpha/progress").json()["progress"]
    got = p["athena_merges"]
    assert got["total"] == LB.ATHENA_MERGES_SHOWN + 2 and len(got["items"]) == LB.ATHENA_MERGES_SHOWN
    assert got["items"][0] == M.unmatched_merge_row(merges[0])
    assert {k: v for k, v in _files(root / "alpha").items() if k != "bundle.json"} == {
        k: v for k, v in before.items() if k != "bundle.json"}
    # no processing results: nothing is listed
    shutil.rmtree(proc)
    assert client.get("/api/local-bundles/alpha/progress").json()["progress"]["athena_merges"] is None


def test_progress_counts_a_group_that_cannot_export_once_and_nowhere_else(client, root):
    b = M.load(root / "alpha")
    gid = b["record_groups"][0]["group_id"]
    members = set(b["record_groups"][0]["member_run_keys"])
    for r in b["runs"]:
        if r["run_key"] in members:
            r["scan_count"] = 0
    M.save_bundle(root / "alpha", b)
    p = client.get("/api/local-bundles/alpha/progress").json()["progress"]
    live = len(Q.live_groups(M.load(root / "alpha")))
    assert p["cannot_export"]["total"] == 1 and p["cannot_export"]["by_reason"] == {"no_scans": 1}
    assert p["cannot_export"]["statement"].startswith(f"1 of the {live} live group(s) cannot become a record")
    proposed = sum(1 for g in M.load(root / "alpha")["record_groups"] if g.get("status") == "proposed")
    line = next(s for s in p["blocks_export"] if "proposed, not confirmed" in s)
    assert line.startswith(f"{proposed - 1} record group(s)"), (line, gid)
    unprocessed = next(s for s in p["blocks_export"] if "no processing result to approve" in s)
    assert unprocessed.startswith(f"{live - 1} record group(s)")
