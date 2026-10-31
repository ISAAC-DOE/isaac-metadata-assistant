"""``isaac bundle propose-terms``: off-vocabulary values in a bundle, as draft proposals.

Every test runs over a bundle imported here from the committed SYNTHETIC multi-operator
fixture; off-vocabulary values are put into it through the bundle's own mutation commands
(``annotate``, ``decide``), never by editing ``bundle.json``. No real data, no network.

Each positive has a negative control beside it: an allowed value is not listed, a clean
bundle lists nothing, and a value the website would refuse as a term is listed but never
drafted (and never rewritten into one it would accept).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import schema_proposal_rules as R
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import propose_terms as P

SEMANTICS = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"


@pytest.fixture(scope="module")
def clean_bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("propose") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == cli.EXIT_OK
    return out


@pytest.fixture()
def bundle_dir(clean_bundle, tmp_path):
    copy = tmp_path / "bundle"
    shutil.copytree(clean_bundle, copy)
    return copy


def _bundle(path: Path) -> dict:
    return json.loads((path / "bundle.json").read_text(encoding="utf-8"))


def _missing_id(path: Path, field: str, index: int = 0) -> str:
    ids = [m["value_id"] for m in _bundle(path)["missing_values"] if m["target_field_path"] == field]
    return ids[index]


def _annotate(path: Path, target: str, value: str) -> None:
    code = cli.main(
        [
            "bundle", "annotate", str(path), "--target", target, "--value", value,
            "--model", "synthetic-test-model", "--excerpt-locator", "page 1 (synthetic)",
            "--rationale", "synthetic test reading",
        ]
    )
    assert code == cli.EXIT_OK


def _report(capsys, path: Path, *extra: str) -> dict:
    capsys.readouterr()
    code = cli.main(["bundle", "propose-terms", str(path), *extra])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK, out
    return json.loads(out)


def _term(report: dict, field: str, term: str) -> dict | None:
    for f in report["fields"]:
        if f["field_path"] == field:
            for t in f["terms"]:
                if t["term"] == term:
                    return t
    return None


# --- a clean bundle --------------------------------------------------------------


def test_a_clean_bundle_lists_nothing_and_writes_nothing(bundle_dir, capsys):
    before = (bundle_dir / "bundle.json").read_bytes()
    report = _report(capsys, bundle_dir)
    assert report["format"] == "isaac.term-proposal-drafts"
    assert report["sent_by_isaac"] is False
    assert report["totals"] == {"fields": 0, "terms": 0, "occurrences": 0, "drafts": 0, "answered_since": 0,
                                 "partly_answered": 0, "answered_before_request": 0}
    assert report["exposed_candidates"] == []
    assert (bundle_dir / "bundle.json").read_bytes() == before


# --- an AI reading outside the list ------------------------------------------------


def test_an_ai_reading_outside_a_portal_list_is_listed_and_drafted_in_the_portal_format(bundle_dir, capsys):
    field = "context.electrochemistry.cell_type"
    _annotate(bundle_dir, _missing_id(bundle_dir, field, 0), "three_electrode_static_cell")
    _annotate(bundle_dir, _missing_id(bundle_dir, field, 1), "three_electrode_static_cell")
    _annotate(bundle_dir, _missing_id(bundle_dir, field, 2), "h_cell")  # allowed: negative control
    report = _report(capsys, bundle_dir)
    entry = _term(report, field, "three_electrode_static_cell")
    assert entry is not None
    assert entry["count"] == 2
    assert entry["by_origin"] == {"scientist_confirmed": 0, "parser_reading": 0, "ai_reading": 2, "scientist_request": 0}
    assert _term(report, field, "h_cell") is None
    # Citations are a file and a locator; no quote is copied out.
    assert entry["citations"] and all(set(c) == {"file", "locator", "run_ids", "origin", "ref"} for c in entry["citations"])
    assert entry["citations"][0]["locator"] == "page 1 (synthetic)"
    draft = entry["draft"]
    assert draft["drafted"] is True and draft["ready_to_send"] is False and draft["missing"] == ["description"]
    payload = draft["portal_payload"]
    assert payload["sent_by_isaac"] is False
    assert payload["portal"] == {"method": "POST", "path": "/portal/api/vocabulary/proposals", "rest_supported": True}
    assert payload["body"] == {
        "proposal_type": "add_term",
        "section": "Context",
        "category": field,
        "term": "three_electrode_static_cell",
        "description": "",
    }
    # An AI reading is not a parser value: nothing was exposed.
    assert report["exposed_candidates"] == []


def test_the_draft_is_the_websites_own_format(bundle_dir, capsys, tmp_path, monkeypatch):
    """The same term proposed on the website yields the same portal block and body keys."""
    field = "context.electrochemistry.cell_type"
    _annotate(bundle_dir, _missing_id(bundle_dir, field), "three_electrode_static_cell")
    local = _term(_report(capsys, bundle_dir), field, "three_electrode_static_cell")["draft"]["portal_payload"]

    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    from isaac_api.app import create_app

    client = TestClient(create_app())
    description = "A static three-electrode cell, as the sheet names it for every Pt/C row."
    created = client.post(
        "/api/schema-proposals",
        json={**{k: v for k, v in local["body"].items() if k != "description"}, "description": description},
    )
    assert created.status_code == 201, created.json()
    web = client.get(f"/api/schema-proposals/{created.json()['proposal']['id']}/portal-payload").json()
    assert web["portal"] == local["portal"]
    assert list(web["body"]) == list(local["body"])
    assert {k: v for k, v in web["body"].items() if k != "description"} == {
        k: v for k, v in local["body"].items() if k != "description"
    }
    assert set(web["notes"]) <= set(local["notes"])


def test_a_phrase_is_listed_but_never_drafted_or_rewritten(bundle_dir, capsys):
    field = "context.electrochemistry.reaction"
    _annotate(bundle_dir, _missing_id(bundle_dir, field), "cathodic corrosion")
    report = _report(capsys, bundle_dir)
    entry = _term(report, field, "cathodic corrosion")
    assert entry is not None and entry["draft"]["drafted"] is False
    assert "invalid_term" in {p["code"] for p in entry["draft"]["problems"]}
    assert "single word" in entry["draft"]["reason"]
    # Never transformed into a term that would pass: the one-word form is only what to ASK for.
    assert _term(report, field, "cathodic_corrosion") is None
    assert "e.g. cathodic_corrosion" in entry["draft"]["ask"]
    assert "cathodic_corrosion" not in json.dumps({**report, "fields": [
        {**f, "terms": [{k: v for k, v in t.items() if k != "draft"} for t in f["terms"]]} for f in report["fields"]]})
    assert "portal_payload" not in entry["draft"]
    assert report["totals"]["drafts"] == 0


# --- a scientist-confirmed value outside the list ---------------------------------


def test_a_confirmed_value_off_the_schema_enum_is_listed_and_a_near_duplicate_is_not_drafted(bundle_dir, capsys):
    """`decide` now REFUSES an answer off the schema's enum (contract §25), so a confirmed off-list
    value exists only in a bundle an older build stored: it is put there as that build wrote it."""
    from isaac_api.local_import import mutations as M

    field = "context.environment"
    target = _missing_id(bundle_dir, field)
    code = cli.main(
        ["bundle", "decide", str(bundle_dir), "--target", target, "--decision", "correct",
         "--value", "insitu", "--by", "Synthetic Tester"]
    )
    assert code == 2 and "not one of the schema's allowed values" in capsys.readouterr().err  # kept as a request (1.10.0)
    held = M.load(bundle_dir)
    held.setdefault("scientist_decisions", []).append({
        "decision_id": f"d-{len(held['scientist_decisions']) + 1:05d}", "target": {"kind": "missing_value", "id": target},
        "decision": "correct", "value": "insitu", "chosen_reading_index": None,
        "decided_by": {"name": "Synthetic Tester", "basis": "self_reported_local_user", "identity": "local_unverified",
                       "orcid_claimed": None},
        "decided_utc": "2026-10-28T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None})
    M.save_bundle(bundle_dir, held)
    stored = next(m for m in _bundle(bundle_dir)["missing_values"] if m["value_id"] == target)
    assert stored["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    # The bundle's own eligibility rule refuses it as off the schema's enum: the same miss.
    assert "not one of the schema's allowed values" in stored["eligibility_for_official_record"]["reason"]
    entry = _term(_report(capsys, bundle_dir), field, "insitu")
    assert entry is not None
    assert entry["by_origin"]["scientist_confirmed"] == 1
    assert "schema" in entry["missing_from"]
    # `insitu` is `in_situ` without its separator: the website's duplicate check refuses it.
    assert entry["draft"]["drafted"] is False
    assert "term_already_exists" in {p["code"] for p in entry["draft"]["problems"]}


# --- a parser value outside the list: an exposure ----------------------------------


def test_printing_a_parser_value_records_an_exposure_first(bundle_dir, capsys, monkeypatch):
    """The synthetic fixture has no string parser value at a closed field, so one field is
    judged by a stand-in closed list here; what is under test is the exposure, not the list."""
    field = "timestamps.acquired_start_utc"
    bundle = _bundle(bundle_dir)
    parsed = [c for c in bundle["candidates"] if c["target_field_path"] == field and isinstance(c["value"], str)]
    assert parsed, "the fixture's parser reads start times"
    real = P._schema_list
    monkeypatch.setattr(P, "_schema_list", lambda path: ["NOT_THE_VALUE"] if path == field else real(path))
    assert not bundle.get("exposures")
    report = _report(capsys, bundle_dir)
    listed = {t["term"] for f in report["fields"] if f["field_path"] == field for t in f["terms"]}
    assert listed == {c["value"] for c in parsed}
    assert set(report["exposed_candidates"]) == {c["candidate_id"] for c in parsed}
    exposures = _bundle(bundle_dir)["exposures"]
    assert {e["target"]["id"] for e in exposures if e["command"] == P.COMMAND} == set(report["exposed_candidates"])
    entry = _term(report, field, parsed[0]["value"])
    assert entry["by_origin"]["parser_reading"] == 1
    # Citations come from the parser's own evidence: a file and a locator.
    assert entry["citations"] and entry["citations"][0]["file"]
    # The portal has no list for this field, so there is no portal payload to draft.
    assert entry["draft"]["drafted"] is False and "no list for this field" in entry["draft"]["reason"]


def test_a_portal_list_that_already_holds_the_term_drafts_nothing():
    sources = R.load_sources_at(ws.REPO_ROOT / "schema/isaac_record_v1.json")
    lists = {"schema": ["XAS"], "portal": ["XAS", "XMCD"], "portal_section": "System"}
    draft = P._draft(sources, "system.technique", "XMCD", lists)
    assert draft["drafted"] is False and "lags the portal" in draft["reason"]


# --- --out ------------------------------------------------------------------------


def test_out_writes_a_file_and_refuses_to_overwrite_without_force(bundle_dir, tmp_path, capsys):
    _annotate(bundle_dir, _missing_id(bundle_dir, "context.electrochemistry.cell_type"), "three_electrode_static_cell")
    out = tmp_path / "drafts.json"
    assert cli.main(["bundle", "propose-terms", str(bundle_dir), "--out", str(out)]) == cli.EXIT_OK
    said = capsys.readouterr().out
    assert "Nothing was sent" in said and "1 draft proposal(s)" in said
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["totals"]["drafts"] == 1
    out.write_text("keep me", encoding="utf-8")
    assert cli.main(["bundle", "propose-terms", str(bundle_dir), "--out", str(out)]) == cli.EXIT_OUTPUT_REFUSED
    assert out.read_text(encoding="utf-8") == "keep me"
    assert cli.main(["bundle", "propose-terms", str(bundle_dir), "--out", str(out), "--force"]) == cli.EXIT_OK
    assert json.loads(out.read_text(encoding="utf-8"))["totals"]["drafts"] == 1
    assert cli.main(["bundle", "propose-terms", str(bundle_dir), "--out", str(tmp_path)]) == cli.EXIT_OUTPUT_REFUSED


def test_a_missing_bundle_is_not_found(tmp_path, capsys):
    assert cli.main(["bundle", "propose-terms", str(tmp_path / "nowhere")]) == cli.EXIT_NOT_FOUND


def test_it_is_in_the_isaac_help():
    from isaac_records import cli as top

    out = subprocess.run(
        [sys.executable, "-m", "isaac_records.cli", "bundle", "--help"], capture_output=True, text=True, check=False,
        env=_subprocess_env(),
    )
    assert "propose-terms" in out.stdout
    assert top.LOCAL_IMPORT_COMMANDS == ("import", "bundle", "process")


def test_propose_terms_imports_no_web_framework(clean_bundle, tmp_path):
    copy = tmp_path / "b"
    shutil.copytree(clean_bundle, copy)
    code = (
        "import sys; from isaac_api.local_import import cli; "
        f"rc = cli.main(['bundle', 'propose-terms', {str(copy)!r}, '--out', {str(tmp_path / 'o.json')!r}]); "
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('fastapi', 'starlette', 'pydantic', 'uvicorn') "
        "or m == 'isaac_api.routes' or m == 'isaac_api.schema_proposals'); "
        "print('RESULT', rc, ','.join(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env=_subprocess_env())
    result = [line for line in out.stdout.splitlines() if line.startswith("RESULT ")]
    assert result == ["RESULT 0 "], out.stdout + out.stderr


def test_the_rules_used_are_the_websites(monkeypatch):
    """A term-shape rule changed in the shared module changes what the CLI drafts."""
    sources = R.load_sources_at(ws.REPO_ROOT / "schema/isaac_record_v1.json")
    lists = {"schema": None, "portal": ["h_cell"], "portal_section": "Context"}
    assert P._draft(sources, "context.electrochemistry.cell_type", "three_electrode_static_cell", lists)["drafted"] is True
    import re

    monkeypatch.setattr(R, "_TERM_SHAPE", re.compile(r"\A[A-Z]+\Z"))
    assert P._draft(sources, "context.electrochemistry.cell_type", "three_electrode_static_cell", lists)["drafted"] is False


def _subprocess_env() -> dict:
    """A child interpreter finds this tree's packages the way the test process does
    (CI imports them by path, not from an installed copy)."""
    import os
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    return {**os.environ, "PYTHONPATH": os.pathsep.join([str(repo / "src"), str(repo / "apps" / "api")])}
