"""The local questions screen's routes (``isaac_api/local_bundles.py``). SYNTHETIC bundles only:
the committed multi-operator corpus (``tests_support_records.pristine_bundle``) and the SYN
merge-candidate folder of the capture-decision tests. No real data.

What is pinned, each by behaviour:

* ABSENT unless ``ISAAC_LOCAL_BUNDLES_DIR`` is set: every route is the ordinary 404 and the OpenAPI
  document does not mention one; the boot refuses the variable beside a deployment base path.
* A bundle name never leaves the directory (``..``, encoded traversal, a leading dot, a symlink out,
  a ``bundle.json`` symlinked out).
* An answer through the route leaves the bundle BYTE-IDENTICAL to the same `isaac bundle decide
  --question` on a copy (every file the bundle directory holds).
* A write names the version it was shown: 428 without one, 412 (and nothing written) when a CLI
  write moved the bundle in between.
* A value outside a field's list is refused with the template import's reason; the decision a
  question does not take is refused with the CLI's own sentence; the identity is local_unverified.
* Reading the questions records an exposure for every parser value it shows — at least what
  `isaac bundle questions` records.
"""

from __future__ import annotations

import json
import os
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

BY = "Synthetic Scientist"
FIXED_UTC = "2099-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def grouped_bundle(pristine_bundle, tmp_path_factory):
    out = tmp_path_factory.mktemp("grouped") / "bundle"
    shutil.copytree(pristine_bundle, out)
    M.group(out)
    return out


@pytest.fixture()
def root(tmp_path, grouped_bundle, monkeypatch):
    r = tmp_path / "bundles"
    r.mkdir()
    for name in ("alpha", "beta"):
        shutil.copytree(grouped_bundle, r / name)
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(r))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    monkeypatch.setattr(M, "now_utc", lambda: FIXED_UTC)
    LB._check_memo.clear()
    return r


#: How ISAAC's own page reaches the local server: from this computer, by its loopback name and port,
#: with the header only a preflighted request can carry.
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123), headers={LB.LOCAL_HEADER: "1"})


def local_client(**over):
    return TestClient(create_app(), **{**LOCAL, **over})


@pytest.fixture()
def client(root):
    return local_client()


def _files(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file() and p.name != ".bundle.lock"}


def _version(client, name="alpha"):
    r = client.get("/api/local-bundles")
    return next(b for b in r.json()["bundles"] if b["name"] == name)["bundle_version"]


def _question(bdir: Path, pred):
    return next(q for q in Q.consolidate(M.load(bdir))["questions"] if pred(q))


# --- absent unless configured -----------------------------------------------------------------


def test_every_route_is_absent_when_the_variable_is_unset(tmp_path, monkeypatch, grouped_bundle):
    monkeypatch.delenv(LB.LOCAL_BUNDLES_ENV, raising=False)
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    c = TestClient(create_app())
    for method, path in (("get", "/api/local-bundles"), ("get", "/api/local-bundles/alpha/questions"),
                         ("get", "/api/local-bundles/alpha/progress"),
                         ("post", "/api/local-bundles/alpha/questions/Q-x/answer"),
                         ("post", "/api/local-bundles/alpha/decisions")):
        r = getattr(c, method)(path, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 404, (method, path, r.status_code)
    schema = c.get("/api/openapi").json()
    assert not [p for p in schema["paths"] if "local-bundles" in p]
    assert LB.TAG_LOCAL_BUNDLES not in {t["name"] for t in schema.get("tags", [])}


def test_a_route_registered_earlier_answers_404_once_the_variable_is_gone(client, monkeypatch):
    assert client.get("/api/local-bundles").status_code == 200
    monkeypatch.delenv(LB.LOCAL_BUNDLES_ENV)
    assert client.get("/api/local-bundles").status_code == 404
    assert client.get("/api/local-bundles/alpha/questions").status_code == 404


def test_the_boot_refuses_it_beside_a_base_path_or_naming_no_directory(root, monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_BASE_PATH", "/krish")
    with pytest.raises(RuntimeError, match="never by a deployment"):
        create_app()
    monkeypatch.delenv("ISAAC_BASE_PATH")
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(tmp_path / "does-not-exist"))
    with pytest.raises(RuntimeError, match="existing directory"):
        create_app()


def test_the_new_operations_meet_the_documentation_rules_every_operation_meets(client):
    """The pinned OpenAPI tests run with the variable unset (so the hosted count is unchanged); this
    holds the five operations that appear only when it is set to the same rules."""
    from test_about_and_openapi import (
        _FORBIDDEN_SUBSTRINGS,
        _INTERNAL_MARKERS,
        _documentation_strings,
        _fastapi_default_summary,
        _operations,
        _route_function_names,
    )

    schema = client.get("/api/openapi").json()
    names = _route_function_names(client.app)
    mine = [(p, m, op) for p, m, op in _operations(schema) if p.startswith("/api/local-bundles")]
    assert sorted((p, m) for p, m, _ in mine) == [
        ("/api/local-bundles", "get"),
        ("/api/local-bundles/{bundle}/decisions", "post"),
        ("/api/local-bundles/{bundle}/progress", "get"),
        ("/api/local-bundles/{bundle}/questions", "get"),
        ("/api/local-bundles/{bundle}/questions/{question_id}/answer", "post"),
    ]
    for path, method, op in mine:
        assert op["summary"] != _fastapi_default_summary(names[(path, method)])
        assert len(op["description"]) > 40
        assert op["tags"] == [LB.TAG_LOCAL_BUNDLES]
        assert "401" in op["responses"]
        assert len([c for c in op["responses"] if c.startswith("2")]) == 1
    dumped = json.dumps(schema).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in dumped, needle
    for where, text in _documentation_strings(schema):
        if "local-bundles" in where:
            assert not any(p.search(text) for p in _INTERNAL_MARKERS), where
    total = sum(1 for _ in _operations(schema))
    assert total == 102 + 5  # the hosted 102 (test_about_and_openapi) plus these five


# --- the directory boundary -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["..", "%2e%2e", ".hidden", "alpha%2f..%2f..", "..%2Fetc"])
def test_a_name_that_leaves_the_directory_is_no_bundle(client, root, name, grouped_bundle):
    shutil.copytree(grouped_bundle, root / ".hidden")  # a real bundle, refused for its leading dot alone
    for suffix in ("/questions", "/progress"):
        r = client.get(f"/api/local-bundles/{name}{suffix}")
        assert r.status_code == 404, (name, r.status_code)


def test_symlinks_out_of_the_directory_are_refused(client, root, tmp_path, grouped_bundle):
    outside = tmp_path / "outside"
    shutil.copytree(grouped_bundle, outside)
    (root / "linked").symlink_to(outside, target_is_directory=True)
    inner = root / "inner"
    inner.mkdir()
    (inner / "bundle.json").symlink_to(outside / "bundle.json")
    for name in ("linked", "inner"):
        r = client.get(f"/api/local-bundles/{name}/questions")
        assert r.status_code == 404 and r.json()["error"] == "bundle_not_found"
    listed = client.get("/api/local-bundles").json()
    assert sorted(b["name"] for b in listed["bundles"]) == ["alpha", "beta"]
    assert listed["not_bundles"] == 2


def test_the_list_reports_check_status_and_counts_without_showing_values(client):
    r = client.get("/api/local-bundles")
    assert r.status_code == 200
    body = r.json()
    alpha = next(b for b in body["bundles"] if b["name"] == "alpha")
    assert alpha["check"]["status"] == "VALID" and alpha["format_version"] == B.FORMAT_VERSION
    assert alpha["source_label"] == "multi_operator_corpus" and alpha["counts"]["runs"] == 9
    assert alpha["bundle_version"].startswith("sha256:")
    assert body["local_only"] is True and "candidates" not in alpha


def test_an_invalid_bundle_is_reported_invalid(client, root):
    data = json.loads((root / "beta" / "bundle.json").read_text())
    data["readiness"]["official_record_ready"] = True
    (root / "beta" / "bundle.json").write_text(json.dumps(data))
    beta = next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == "beta")
    assert beta["check"]["status"] == "INVALID" and beta["check"]["error_count"] >= 1


# --- the questions read -----------------------------------------------------------------------


def test_reading_the_questions_records_at_least_the_cli_exposures(client, root, capsys):
    cli_copy = root.parent / "cli-copy"
    shutil.copytree(root / "alpha", cli_copy)
    assert cli.main(["bundle", "questions", str(cli_copy), "--limit", str(cli.MAX_LIMIT)]) == 0
    capsys.readouterr()
    before = _version(client)
    r = client.get("/api/local-bundles/alpha/questions")
    assert r.status_code == 200
    body = r.json()
    assert body["exposures_recorded"] > 0 and body["bundle"]["bundle_version"] != before
    route_x = {(e["target"]["kind"], e["target"]["id"]) for e in M.load(root / "alpha")["exposures"]}
    cli_x = {(e["target"]["kind"], e["target"]["id"]) for e in M.load(cli_copy)["exposures"]}
    assert cli_x <= route_x
    # every candidate whose extracted value is shown is exposed
    shown = {s["candidate_id"] for q in body["questions"] for s in q["display"]["suggestions"] if s.get("candidate_id")}
    assert shown and {("candidate", c) for c in shown} <= route_x
    again = client.get("/api/local-bundles/alpha/questions").json()
    assert again["exposures_recorded"] == 0 and again["bundle"]["bundle_version"] == body["bundle"]["bundle_version"]


def test_every_suggestion_is_marked_not_confirmed_and_hints_cannot_be_accepted(client):
    body = client.get("/api/local-bundles/alpha/questions").json()
    assert body["counts"]["total"] == body["total"] and body["identity"] == "local_unverified"
    for q in body["questions"]:
        d = q["display"]
        assert d["folder"] == "alpha" and d["beamtime"] == "multi_operator_corpus"
        for s in d["suggestions"]:
            assert s["confirmed"] is False
            if s["hint_kind"] in ("folder_name", "acquisition_system", "related_reading"):
                assert s["acceptable"] is False
    filtered = client.get("/api/local-bundles/alpha/questions", params={"kind": "missing_value", "blocking_only": True}).json()
    assert filtered["questions"] and all(q["kind"] == "missing_value" and q["blocking"] for q in filtered["questions"])


# --- the answer -------------------------------------------------------------------------------


def _env_question(bdir):
    return _question(bdir, lambda q: q["target_field_path"] == "context.environment" and q["kind"] == "missing_value")


def test_an_answer_equals_the_cli_decide_byte_for_byte(client, root):
    q = _env_question(root / "alpha")
    assert cli.main(["bundle", "decide", str(root / "beta"), "--question", q["question_id"], "--decision", "correct",
                     "--value", "ex_situ", "--by", BY]) == 0
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "ex_situ", "by": BY, "expected_version": _version(client)})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["result"]["recorded"]) == sorted(t["id"] for t in q["targets"])
    assert _files(root / "alpha") == _files(root / "beta")
    d = M.load(root / "alpha")["scientist_decisions"][-1]
    assert d["decided_by"] == {"name": BY, "basis": "self_reported_local_user", "identity": "local_unverified", "orcid_claimed": None}


def test_a_group_only_answer_equals_the_cli_only_answer_byte_for_byte(client, root):
    q = _env_question(root / "alpha")
    only = sorted(q["per_scope_targets"])[0]
    assert cli.main(["bundle", "decide", str(root / "beta"), "--question", q["question_id"], "--only", only,
                     "--decision", "correct", "--value", "in_situ", "--by", BY]) == 0
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "in_situ", "by": BY, "only": only,
                          "expected_version": _version(client)})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["recorded"] == q["per_scope_targets"][only]
    assert _files(root / "alpha") == _files(root / "beta")


def test_a_number_is_typed_as_the_cli_json_flag_types_it(client, root):
    payload = Q.consolidate(M.load(root / "alpha"))
    numeric = [(q, f) for q in payload["questions"] if q["kind"] == "optional_values"
               for f in q["fields"] if LB.unit_of(f)]
    if not numeric:
        pytest.skip("no numeric optional field in this synthetic bundle")
    q, field = numeric[0]
    assert cli.main(["bundle", "decide", str(root / "beta"), "--question", q["question_id"], "--field", field,
                     "--decision", "correct", "--value", "295", "--json", "--by", BY]) == 0
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "295", "field": field, "by": BY,
                          "expected_version": _version(client)})
    assert r.status_code == 200, r.text
    assert r.json()["value"] == 295 and M.load(root / "alpha")["scientist_decisions"][-1]["value"] == 295
    assert _files(root / "alpha") == _files(root / "beta")
    bad = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                      json={"decision": "correct", "value": "warm", "field": field, "by": BY,
                            "expected_version": _version(client)})
    assert bad.status_code in (404, 422)  # answered already (404) or not a number (422); never stored


def test_a_write_needs_the_version_it_was_shown_and_a_cli_write_in_between_is_not_lost(client, root):
    q = _env_question(root / "alpha")
    url = f"/api/local-bundles/alpha/questions/{q['question_id']}/answer"
    before = (root / "alpha" / "bundle.json").read_bytes()
    r = client.post(url, json={"decision": "correct", "value": "ex_situ", "by": BY})
    assert r.status_code == 428 and (root / "alpha" / "bundle.json").read_bytes() == before
    shown = _version(client)
    other = _question(root / "alpha", lambda x: x["kind"] == "missing_value" and x["target_field_path"] == "system.domain")
    assert cli.main(["bundle", "decide", str(root / "alpha"), "--question", other["question_id"], "--decision", "correct",
                     "--value", "experimental", "--by", "Someone at the terminal"]) == 0
    after_cli = (root / "alpha" / "bundle.json").read_bytes()
    r = client.post(url, json={"decision": "correct", "value": "ex_situ", "by": BY, "expected_version": shown})
    assert r.status_code == 412 and r.json()["error"] == "stale_bundle_version"
    assert r.json()["current_version"] == M.bundle_version(root / "alpha")
    assert (root / "alpha" / "bundle.json").read_bytes() == after_cli  # the CLI's write stands, nothing added
    assert M.load(root / "alpha")["scientist_decisions"][-1]["decided_by"]["name"] == "Someone at the terminal"


def test_a_value_off_the_list_is_refused_where_the_cli_would_store_it_ineligible(client, root):
    q = _env_question(root / "alpha")
    assert "outdoors" not in (q["allowed_values"] or [])
    before = (root / "alpha" / "bundle.json").read_bytes()
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "outdoors", "by": BY, "expected_version": _version(client)})
    assert r.status_code == 422 and r.json()["error"] == "value_refused" and "not an allowed value" in r.json()["message"]
    assert (root / "alpha" / "bundle.json").read_bytes() == before
    # the CLI stores it, and it is never eligible: the route takes no path the CLI could not
    assert cli.main(["bundle", "decide", str(root / "beta"), "--question", q["question_id"], "--decision", "correct",
                     "--value", "outdoors", "--by", BY]) == 0
    beta = M.load(root / "beta")
    ids = {t["id"] for t in q["targets"]}
    assert all(not m["eligibility_for_official_record"]["eligible"] for m in beta["missing_values"] if m["value_id"] in ids)
    # a near miss in case is refused with the template's own hint
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "EX_SITU", "by": BY, "expected_version": _version(client)})
    assert r.status_code == 422 and "did you mean 'ex_situ'" in r.json()["message"]


def test_a_decision_the_question_does_not_take_is_refused_with_the_cli_sentence(client, root, capsys):
    q = _env_question(root / "alpha")
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "set_absorber", "element": "Fe", "edge": "K", "by": BY,
                          "expected_version": _version(client)})
    assert r.status_code == 422
    assert cli.main(["bundle", "decide", str(root / "beta"), "--question", q["question_id"], "--decision", "set_absorber",
                     "--element", "Fe", "--edge", "K", "--by", BY]) == 2
    assert r.json()["message"] in capsys.readouterr().err
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "ex_situ", "by": "  ", "expected_version": _version(client)})
    assert r.status_code == 422 and "--by is required" in r.json()["message"]
    r = client.post("/api/local-bundles/alpha/questions/Q-0000000000/answer",
                    json={"decision": "correct", "value": "ex_situ", "by": BY, "expected_version": _version(client)})
    assert r.status_code == 404
    assert M.load(root / "alpha")["scientist_decisions"] == []


def test_a_dry_run_names_exactly_the_targets_and_writes_nothing(client, root):
    q = _env_question(root / "alpha")
    before = _files(root / "alpha")
    v = _version(client)
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "ex_situ", "by": BY, "expected_version": v, "dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True and body["bundle_version"] == v
    assert sorted(body["would_record"]) == sorted(Q.targets_for(Q.consolidate(M.load(root / "alpha")), q["question_id"]))
    assert _files(root / "alpha") == before
    # a refusal in the dry run is the write's refusal
    bad = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                      json={"decision": "correct", "by": BY, "expected_version": v, "dry_run": True})
    assert bad.status_code == 422 and "needs --value" in bad.json()["message"]


def test_progress_reports_what_blocks_export_and_no_invented_share(client):
    r = client.get("/api/local-bundles/alpha/progress")
    assert r.status_code == 200
    p = r.json()["progress"]
    assert p["questions"]["blocking"] > 0 and p["missing_share"] is None
    assert any("blocking question" in s for s in p["blocks_export"])
    assert p["record_groups"]["by_status"] == {"proposed": 9}
    assert p["readiness"]["official_record_ready"] is False


# --- capture decisions --------------------------------------------------------------------------


@pytest.fixture()
def syn_root(tmp_path, monkeypatch):
    from test_local_import_grouping_cli import FIXTURE, _folder

    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    r = tmp_path / "bundles"
    r.mkdir()
    src = _folder(tmp_path)
    assert cli.main(["import", str(src), "--out", str(r / "syn")]) == 0
    M.group(r / "syn")
    shutil.copytree(r / "syn", r / "syn-cli")  # one import, so both hold the same bundle id
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(r))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setattr(M, "now_utc", lambda: FIXED_UTC)
    return r


def test_keep_apart_through_the_route_equals_the_cli_and_other_decisions_are_refused(syn_root, capsys):
    c = local_client()
    body = c.get("/api/local-bundles/syn/questions").json()
    (mc,) = body["capture"]["merge_candidates"]
    v = body["bundle"]["bundle_version"]
    # the same read on the other copy, so both hold the same exposures before the decision
    c.get("/api/local-bundles/syn-cli/questions")
    g = M.load(syn_root / "syn")["record_groups"][0]["group_id"]
    r = c.post("/api/local-bundles/syn/decisions", json={"target": g, "decision": "confirm", "by": BY, "expected_version": v})
    assert r.status_code == 422 and "not offered here" in r.json()["message"]
    r = c.post("/api/local-bundles/syn/decisions",
               json={"target": mc["merge_candidate_id"], "decision": "keep_apart", "by": BY, "expected_version": v})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["recorded"] == [mc["merge_candidate_id"]]
    assert cli.main(["bundle", "decide", str(syn_root / "syn-cli"), "--target", mc["merge_candidate_id"],
                     "--decision", "keep_apart", "--by", BY]) == 0
    capsys.readouterr()
    a, b = _files(syn_root / "syn"), _files(syn_root / "syn-cli")
    assert a == b
    r = c.post("/api/local-bundles/syn/decisions",
               json={"target": mc["merge_candidate_id"], "decision": "keep_apart", "by": BY, "expected_version": v})
    assert r.status_code == 412  # the version it was shown is gone
    assert os.path.exists(syn_root / "syn" / "bundle.json")


# --- who may ask (DNS rebinding, cross-origin simple requests, a network-facing server) --------------


def test_a_request_from_another_computer_is_refused_before_anything_is_read(root):
    c = local_client(client=("192.0.2.7", 50000))
    r = c.get("/api/local-bundles")
    assert r.status_code == 403 and r.json()["detail"]["error"] == "not_loopback_client"


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "127.0.0.1:9999", "localhost.evil.example:8000"])
def test_a_host_that_does_not_name_this_computer_is_refused(root, host):
    c = local_client()
    before = (root / "alpha" / "bundle.json").read_bytes()
    r = c.get("/api/local-bundles/alpha/questions", headers={"host": host})
    assert r.status_code == 421 and r.json()["detail"]["error"] == "host_not_local"
    r = c.post("/api/local-bundles/alpha/questions/Q-x/answer", headers={"host": host},
               json={"decision": "correct", "value": "ex_situ", "by": BY, "expected_version": "sha256:x"})
    assert r.status_code == 421
    assert (root / "alpha" / "bundle.json").read_bytes() == before


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000"])
def test_each_loopback_name_with_this_port_is_accepted(root, host):
    assert local_client().get("/api/local-bundles", headers={"host": host}).status_code == 200


def test_an_origin_outside_the_allowlist_is_refused_and_the_app_origins_are_not(root):
    c = local_client()
    assert c.get("/api/local-bundles", headers={"origin": "http://evil.example"}).status_code == 403
    assert c.get("/api/local-bundles", headers={"origin": "null"}).status_code == 403
    assert c.get("/api/local-bundles", headers={"origin": "http://localhost:5173"}).status_code == 200
    assert c.get("/api/local-bundles", headers={"origin": "http://127.0.0.1:8000"}).status_code == 200  # same origin


def test_a_request_without_the_local_header_records_no_exposure(root):
    """An <img> or a plain link sends no custom header and cannot without a preflight this API refuses
    to other origins: it must not record anything (measured before the fix: 109 exposures)."""
    c = local_client(headers={})
    before = (root / "alpha" / "bundle.json").read_bytes()
    r = c.get("/api/local-bundles/alpha/questions")
    assert r.status_code == 403 and r.json()["detail"]["error"] == "local_header_required"
    assert (root / "alpha" / "bundle.json").read_bytes() == before


def test_the_boot_refuses_a_server_told_to_listen_beyond_this_computer(root, monkeypatch):
    assert LB.launch_hosts(["uvicorn", "x:app", "--host", "0.0.0.0"], {}) == ["0.0.0.0"]
    assert LB.launch_hosts(["uvicorn", "--host=::"], {"UVICORN_HOST": "10.0.0.2"}) == ["::", "10.0.0.2"]
    monkeypatch.setattr(LB.sys, "argv", ["uvicorn", "isaac_api.app:app", "--host", "0.0.0.0"])
    with pytest.raises(RuntimeError, match="not this computer's loopback"):
        create_app()
    monkeypatch.setattr(LB.sys, "argv", ["uvicorn", "isaac_api.app:app", "--host", "127.0.0.1"])
    create_app()
    monkeypatch.delenv(LB.LOCAL_BUNDLES_ENV)
    monkeypatch.setattr(LB.sys, "argv", ["uvicorn", "isaac_api.app:app", "--host", "0.0.0.0"])
    create_app()  # the hosted shape: no local bundles, nothing refused


# --- review fixes ------------------------------------------------------------------------------------


def test_the_cli_question_path_still_exits_6_and_creates_nothing_in_a_folder_without_a_bundle(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main(["bundle", "decide", str(empty), "--question", "Q-x", "--decision", "correct", "--value", "v", "--by", BY]) == 6
    assert "No bundle.json" in capsys.readouterr().err and list(empty.iterdir()) == []
    assert cli.main(["bundle", "decide", str(tmp_path / "missing"), "--question", "Q-x", "--decision", "correct",
                     "--value", "v", "--by", BY]) == 6


def test_the_check_memo_is_bounded_and_judges_the_bytes_it_was_given(client, root, monkeypatch):
    monkeypatch.setattr(LB, "CHECK_MEMO_MAX", 2)
    for i in range(5):
        LB.check_status(f"sha256:{i}", M.load(root / "alpha"))
    assert len(LB._check_memo) == 2
    version, data = LB.read_bundle(root / "alpha")
    assert version == M.bundle_version(root / "alpha") and data == M.load(root / "alpha")


def test_accept_on_a_confirm_question_states_every_target_value_not_only_the_described_window(client, root, monkeypatch):
    monkeypatch.setattr(LB, "DESCRIBE_TARGETS", 1)
    body = client.get("/api/local-bundles/alpha/questions", params={"kind": "confirm_value"}).json()
    data = M.load(root / "alpha")
    valued = [c for c in data["candidates"] if c.get("value") is not None][:5]
    built = {"kind": "confirm_value", "scope": "experiment", "target_field_path": valued[0]["target_field_path"],
             "targets": [{"kind": "candidate", "id": c["candidate_id"]} for c in valued],
             "per_scope_targets": {"experiment": [c["candidate_id"] for c in valued]}, "hints": []}
    display, shown = LB.describe_question(data, built, folder="alpha")
    assert sum(v["targets"] for v in display["distinct_extracted_values"]) == len(valued) == 5
    assert display["targets_total"] == 5 and display["targets_described"] == 1
    assert {("candidate", c["candidate_id"]) for c in valued} <= set(shown)  # every value counted is exposed
    for q in [q for q in body["questions"] if len(q["targets"]) > 1]:
        cands = {c["candidate_id"]: c for c in M.load(root / "alpha")["candidates"]}
        with_value = sum(1 for t in q["targets"] if (cands.get(t["id"]) or {}).get("value") is not None)
        assert sum(v["targets"] for v in q["display"]["distinct_extracted_values"]) == with_value
        assert q["display"]["targets_described"] == 1 and q["display"]["targets_total"] == len(q["targets"])


def test_the_same_for_all_preview_flags_each_group_whose_own_files_suggest_otherwise(client, root):
    q = _env_question(root / "alpha")
    one_scope = sorted(q["per_scope_targets"])[0]
    target = q["per_scope_targets"][one_scope][0]
    M.annotate(root / "alpha", target_id=target, value="in_situ", excerpt_locator=None, source_id=None,
               model_id="synthetic-model", blind=False, rationale="SYNTHETIC TEST")
    body = client.get("/api/local-bundles/alpha/questions", params={"kind": "missing_value"}).json()
    shown = next(x for x in body["questions"] if x["question_id"] == q["question_id"])
    assert shown["display"]["suggestions_differ"] is False  # one group suggests, the others suggest nothing
    scope = next(sc for sc in shown["display"]["scopes"] if sc["scope"] == one_scope)
    assert [o["value"] for o in scope["own_suggestions"]] == ["in_situ"] and scope["own_suggestions"][0]["confirmed"] is False
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "ex_situ", "by": BY, "dry_run": True,
                          "expected_version": body["bundle"]["bundle_version"]})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["scopes_whose_files_suggest_otherwise"] == 1 and p["scopes_total"] == len(q["per_scope_targets"])
    flagged = [g for g in p["by_scope"] if g["differs"]]
    assert [g["scope"] for g in flagged] == [one_scope] and flagged[0]["own_suggestions"][0]["value"] == "in_situ"
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "in_situ", "by": BY, "dry_run": True,
                          "expected_version": body["bundle"]["bundle_version"]})
    assert r.json()["scopes_whose_files_suggest_otherwise"] == 0


def test_a_write_returns_the_version_read_under_its_own_lock(client, root):
    q = _env_question(root / "alpha")
    r = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "ex_situ", "by": BY, "expected_version": _version(client)})
    assert r.status_code == 200 and r.json()["bundle_version"] == M.bundle_version(root / "alpha")


# --- provenance of a group's suggestion, and an answer for several named groups --------------------


def _env_groups(root):
    q = _env_question(root / "alpha")
    data = M.load(root / "alpha")
    groups = {g["group_id"]: g for g in data["record_groups"]}
    runs = {r["run_id"]: r for r in data["runs"]}
    missing = {m["value_id"]: m for m in data["missing_values"]}
    scopes = sorted(q["per_scope_targets"])
    return q, groups, runs, missing, scopes


def test_a_suggestion_is_this_groups_own_only_when_it_cites_one_of_its_runs_files(client, root):
    q, groups, runs, missing, scopes = _env_groups(root)
    a, b = scopes[0], scopes[1]
    ta, tb = q["per_scope_targets"][a][0], q["per_scope_targets"][b][0]
    own_src = runs[missing[ta]["run_id"]]["acquisition_source_id"]
    other_src = runs[missing[ta]["run_id"]]["acquisition_source_id"]  # group A's file, cited for group B
    M.annotate(root / "alpha", target_id=ta, value="in_situ", excerpt_locator="line 1", source_id=own_src,
               model_id="synthetic-model", blind=False, rationale="SYNTHETIC TEST")
    M.annotate(root / "alpha", target_id=tb, value="in_situ", excerpt_locator="line 10", source_id=other_src,
               model_id="synthetic-model", blind=False, rationale="SYNTHETIC TEST")
    body = client.get("/api/local-bundles/alpha/questions", params={"kind": "missing_value"}).json()
    shown = next(x for x in body["questions"] if x["question_id"] == q["question_id"])
    by = {sc["scope"]: sc for sc in shown["display"]["scopes"]}
    (sa,), (sb,) = by[a]["own_suggestions"], by[b]["own_suggestions"]
    assert sa["from_own_files"] is True and sa["provenance_label"] == "This group's own files"
    assert sb["from_own_files"] is False and "not one of its runs" in sb["provenance_label"]
    p = client.post(f"/api/local-bundles/alpha/questions/{q['question_id']}/answer",
                    json={"decision": "correct", "value": "ex_situ", "by": BY, "dry_run": True,
                          "expected_version": body["bundle"]["bundle_version"]}).json()
    flagged = {g["scope"]: g for g in p["by_scope"] if g["differs"]}
    assert flagged[b]["own_suggestions"][0]["from_own_files"] is False  # the same rule in the preview


def test_an_answer_for_several_named_groups_writes_exactly_their_targets(client, root):
    q, _groups, _runs, _missing, scopes = _env_groups(root)
    two = scopes[:2]
    url = f"/api/local-bundles/alpha/questions/{q['question_id']}/answer"
    v = _version(client)
    p = client.post(url, json={"decision": "correct", "value": "in_situ", "by": BY, "only_scopes": two,
                               "dry_run": True, "expected_version": v}).json()
    want = [t for sc in two for t in q["per_scope_targets"][sc]]
    assert p["would_record"] == want and sorted(g["scope"] for g in p["by_scope"]) == sorted(two)
    assert client.post(url, json={"decision": "correct", "value": "in_situ", "by": BY, "only_scopes": two, "only": two[0],
                                  "expected_version": v}).status_code == 422
    before = (root / "alpha" / "bundle.json").read_bytes()
    r = client.post(url, json={"decision": "correct", "value": "in_situ", "by": BY, "only_scopes": [two[0], "group:nope"],
                               "expected_version": v})
    assert r.status_code == 404 and (root / "alpha" / "bundle.json").read_bytes() == before  # refused whole
    r = client.post(url, json={"decision": "correct", "value": "in_situ", "by": BY, "only_scopes": two,
                               "expected_version": p["bundle_version"]})
    assert r.status_code == 200 and r.json()["result"]["recorded"] == want
    others = {t for sc in scopes[2:] for t in q["per_scope_targets"][sc]}
    decided = {d["target"]["id"] for d in M.load(root / "alpha")["scientist_decisions"]}
    assert decided == set(want) and not decided & others


# --- re-review: per-run comparison, an unparseable origin, a scan file is a run's own -----------------


def test_an_origin_whose_port_is_not_a_number_is_refused_not_a_server_error(root):
    r = local_client().get("/api/local-bundles", headers={"origin": "http://localhost:8000.evil.com"})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "origin_not_allowed"


def test_a_scan_file_of_the_run_is_its_own_file(client, root):
    q, _groups, runs, missing, scopes = _env_groups(root)
    t = q["per_scope_targets"][scopes[0]][0]
    run = runs[missing[t]["run_id"]]
    scan_src = run["scans"][0]["source_id"]
    assert scan_src != run["acquisition_source_id"]
    M.annotate(root / "alpha", target_id=t, value="in_situ", excerpt_locator="line 2", source_id=scan_src,
               model_id="synthetic-model", blind=False, rationale="SYNTHETIC TEST")
    body = client.get("/api/local-bundles/alpha/questions", params={"kind": "missing_value"}).json()
    shown = next(x for x in body["questions"] if x["question_id"] == q["question_id"])
    (sug,) = next(sc for sc in shown["display"]["scopes"] if sc["scope"] == scopes[0])["own_suggestions"]
    assert sug["from_own_files"] is True and sug["provenance_label"] == "This group's own files"


@pytest.fixture()
def multi_run_root(tmp_path, monkeypatch):
    """The SYN folder's two runs joined into ONE record group (their differing name token stated as a run
    counter, then a regroup), so the group's per-run targets can disagree."""
    from test_local_import_grouping_cli import FIXTURE, _folder

    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    r = tmp_path / "bundles"
    r.mkdir()
    b = r / "multi"
    assert cli.main(["import", str(_folder(tmp_path)), "--out", str(b)]) == 0
    M.group(b)
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    M.group(b, regroup=True)
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(r))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return b


def test_a_multi_run_group_whose_runs_disagree_is_mixed_and_the_preview_names_the_differing_run(multi_run_root):
    b = multi_run_root
    data = M.load(b)
    live = [g for g in data["record_groups"] if g["status"] in ("proposed", "scientist_confirmed") and len(g["member_run_ids"]) == 2]
    assert live, "the regroup should propose one group of both runs"
    gscope = f"group:{live[0]['group_id']}"
    q = next(x for x in Q.consolidate(data)["questions"]
             if x["target_field_path"] == "context.environment" and len(x["per_scope_targets"].get(gscope, [])) == 2)
    t1, t2 = q["per_scope_targets"][gscope]
    missing = {m["value_id"]: m for m in data["missing_values"]}
    runs = {r["run_id"]: r for r in data["runs"]}
    for t, v in ((t1, "in_situ"), (t2, "ex_situ")):
        M.annotate(b, target_id=t, value=v, excerpt_locator="line 1", source_id=runs[missing[t]["run_id"]]["acquisition_source_id"],
                   model_id="synthetic-model", blind=False, rationale="SYNTHETIC TEST")
    c = local_client()
    body = c.get("/api/local-bundles/multi/questions").json()
    shown = next(x for x in body["questions"] if x["question_id"] == q["question_id"])
    sc = next(s for s in shown["display"]["scopes"] if s["scope"] == gscope)
    assert sc["mixed"] is True and sc["has_unanimous_value"] is False and sc["unanimous_from_own_files"] is False
    assert {t["target_id"]: [o["value"] for o in t["own_suggestions"]] for t in sc["per_target"]} == {t1: ["in_situ"], t2: ["ex_situ"]}
    p = c.post(f"/api/local-bundles/multi/questions/{q['question_id']}/answer",
               json={"decision": "correct", "value": "in_situ", "by": BY, "only_scopes": [gscope], "dry_run": True,
                     "expected_version": body["bundle"]["bundle_version"]}).json()
    (g,) = p["by_scope"]
    assert g["differs"] is True and [t["target_id"] for t in g["differing_targets"]] == [t2]
    assert p["scopes_whose_files_suggest_otherwise"] == 1


# --- audit hardening: own origin allowlist, the lock, a read-only bundle, no absolute path in a body ---


def test_the_local_origins_are_their_own_list_not_the_apps_cors_list(root, monkeypatch):
    """An origin added to ISAAC_UI_CORS_ORIGINS (for another reason) does not reach a bundle."""
    monkeypatch.setenv("ISAAC_UI_CORS_ORIGINS", "http://localhost:5173,https://tools.example.org,http://localhost:3000")
    c = local_client()
    assert c.get("/api/local-bundles", headers={"origin": "https://tools.example.org"}).status_code == 403
    assert c.get("/api/local-bundles", headers={"origin": "http://localhost:3000"}).status_code == 403
    assert c.get("/api/local-bundles", headers={"origin": "http://localhost:5173"}).status_code == 200
    assert c.get("/api/local-bundles", headers={"origin": "http://127.0.0.1:5173"}).status_code == 200


def test_a_non_loopback_local_origin_is_refused_even_when_configured(root, monkeypatch):
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ORIGINS_ENV, "https://tools.example.org, http://192.168.1.5:5173, http://localhost:5180")
    monkeypatch.setenv("ISAAC_UI_CORS_ORIGINS", "https://tools.example.org,http://192.168.1.5:5173,http://localhost:5180")
    c = local_client()
    for origin in ("https://tools.example.org", "http://192.168.1.5:5173", "http://localhost:5173"):
        r = c.get("/api/local-bundles", headers={"origin": origin})
        assert r.status_code == 403 and r.json()["detail"]["error"] == "origin_not_allowed", origin
    assert c.get("/api/local-bundles", headers={"origin": "http://localhost:5180"}).status_code == 200
    assert c.get("/api/local-bundles", headers={"origin": "http://127.0.0.1:8000"}).status_code == 200  # same origin
    warnings = LB.startup_warnings()
    assert any("ignoring https://tools.example.org, http://192.168.1.5:5173" in w for w in warnings)


def test_start_up_warns_about_ignored_origins_and_states_the_residual_risk(root, monkeypatch, capsys):
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ORIGINS_ENV, "https://tools.example.org")
    create_app()
    err = capsys.readouterr().err
    assert "WARNING: ISAAC_LOCAL_BUNDLES_ORIGINS: ignoring https://tools.example.org" in err
    assert "NOTE: Local bundles: any page served from this server's own origin can use them" in err


def test_a_symlinked_bundle_lock_is_refused_and_its_target_is_not_created(client, root, tmp_path):
    target = tmp_path / "elsewhere" / "created-by-the-lock"
    target.parent.mkdir()
    lock = root / "alpha" / ".bundle.lock"
    lock.unlink(missing_ok=True)
    lock.symlink_to(target)
    for r in (client.get("/api/local-bundles/alpha/progress"), client.get("/api/local-bundles/alpha/questions"),
              client.post("/api/local-bundles/alpha/questions/Q-x/answer",
                          json={"decision": "correct", "value": "x", "by": BY, "expected_version": "sha256:x"})):
        assert r.status_code == 409 and r.json()["error"] == "bundle_not_accessible" and "symlink" in r.json()["message"]
    listed = next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == "alpha")
    assert listed["not_accessible"] and "symlink" in listed["check"]["errors"][0]
    assert not target.exists()


@pytest.mark.skipif(os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="needs POSIX permissions, not root")
def test_a_read_only_bundle_is_a_clear_refusal_not_a_server_error(root):
    c = TestClient(create_app(), raise_server_exceptions=False, **LOCAL)
    (root / "alpha" / ".bundle.lock").unlink(missing_ok=True)
    os.chmod(root / "alpha", 0o555)
    try:
        r = c.get("/api/local-bundles")
        assert r.status_code == 200
        alpha = next(b for b in r.json()["bundles"] if b["name"] == "alpha")
        assert alpha["check"]["status"] == "INVALID" and "read-only" in alpha["check"]["errors"][0]
        assert next(b for b in r.json()["bundles"] if b["name"] == "beta")["check"]["status"] != "INVALID"
        for path in ("/api/local-bundles/alpha/progress", "/api/local-bundles/alpha/questions"):
            r = c.get(path)
            assert r.status_code == 409 and r.json()["error"] == "bundle_not_accessible", path
            assert str(root) not in r.text and os.path.realpath(root) not in r.text
    finally:
        os.chmod(root / "alpha", 0o755)


def test_a_bundle_json_that_vanishes_after_the_check_is_not_reported_by_absolute_path(client, root, monkeypatch):
    real = LB.resolve_bundle_dir

    def racing(r, name):
        found = real(r, name)
        if found is not None:
            (found / "bundle.json").unlink()  # the race: gone between the check and the read
        return found

    monkeypatch.setattr(LB, "resolve_bundle_dir", racing)
    r = client.get("/api/local-bundles/alpha/progress")
    assert r.status_code == 404
    assert str(root) not in r.text and os.path.realpath(root) not in r.text and "alpha" in r.json()["message"]


def test_a_refusal_message_naming_the_directory_is_scrubbed(root):
    from isaac_api.local_import import mutations as M

    exc = M.MutationRefused(f"No bundle.json at {os.path.realpath(root)}/alpha.", code=6)
    body = json.loads(LB._refusal(exc).body)
    assert body["message"] == "No bundle.json at alpha."
