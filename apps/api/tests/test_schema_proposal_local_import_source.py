"""Schema Proposals: a new term filed from a draft of ``isaac bundle propose-terms --out``.

The Schema Proposals page reads the drafts file in the browser and files ONE draft at a time,
with the proposer's own description, the file's citations and counts as reviewer notes
(``gate0``), and a ``source`` block naming the draft. These tests pin that the server takes that
block, holds it to strict rules (unknown keys, a draft for another field or term, a type a local
import never drafts), and still requires everything it required before: a description of at
least 20 characters, ``pending`` status, a 409 for a duplicate pending proposal, and no route
that approves, applies or sends. Synthetic values only; no file is read and no network is used.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from isaac_api import schema_proposal_rules as R
from isaac_api import schema_proposals as sp
from isaac_api.local_import import propose_terms as P

BASE = "/api/schema-proposals"

FIELD = "context.electrochemistry.cell_type"
TERM = "three_electrode_static_cell"

SOURCE = {
    "kind": "local_import",
    "format": "isaac.term-proposal-drafts",
    "bundle_id": "synthetic-bundle-0001",
    "field_path": FIELD,
    "term": TERM,
    "occurrences": 2,
    "runs": 2,
    "citations_total": 1,
}
GATE0 = {
    "problem": f"The bundle holds '{TERM}' for {FIELD} 2 times; the portal's list does not have it.",
    "examples": "notes/synthetic.pdf · page 1 (synthetic) (AI reading)",
    "affected_records_estimate": "2 readings (2 AI readings) in 2 runs",
}
BODY = {
    "proposal_type": "add_term",
    "section": "Context",
    "category": FIELD,
    "term": TERM,
    "description": "A static three-electrode cell, as the synthetic sheet names it.",
    "gate0": GATE0,
    "source": SOURCE,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _body(**over):
    out = {**BODY, "gate0": dict(GATE0), "source": dict(SOURCE)}
    for key, value in over.items():
        if value is ...:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def _codes(response) -> dict:
    return {e["field"]: e["code"] for e in response.json()["errors"]}


def test_the_format_named_is_the_one_the_cli_writes():
    assert R.LOCAL_IMPORT_DRAFTS_FORMAT == P.FORMAT_ID
    assert P.FORMAT_VERSION == "1"


def test_a_draft_from_a_local_import_is_saved_pending_with_its_source_and_notes(client):
    created = client.post(BASE, json=_body())
    assert created.status_code == 201, created.json()
    proposal = created.json()["proposal"]
    assert proposal["status"] == "pending"
    assert proposal["sent_by_isaac"] is False
    assert proposal["proposed_by"] is None and proposal["attribution"] == "unverified"
    assert proposal["source"] == SOURCE
    assert proposal["gate0"] == GATE0
    # The stored proposal reads back the same, and the list shows it too.
    again = client.get(f"{BASE}/{proposal['id']}").json()["proposal"]
    assert again["source"] == SOURCE
    listed = client.get(BASE).json()["proposals"]
    assert [p["source"] for p in listed] == [SOURCE]
    # The citations and counts reach the portal body as the reviewer notes; nothing is sent.
    payload = client.get(f"{BASE}/{proposal['id']}/portal-payload").json()
    assert payload["sent_by_isaac"] is False
    assert GATE0["examples"] in payload["body"]["description"]
    assert GATE0["affected_records_estimate"] in payload["body"]["description"]
    assert set(payload["body"]) == {"proposal_type", "section", "category", "term", "description"}


def test_runs_and_bundle_id_are_optional(client):
    source = {k: v for k, v in SOURCE.items() if k not in ("runs", "bundle_id")}
    created = client.post(BASE, json=_body(source=source))
    assert created.status_code == 201, created.json()
    assert created.json()["proposal"]["source"] == {**source, "runs": None, "bundle_id": None}


def test_a_proposal_typed_from_scratch_has_no_source(client):
    created = client.post(BASE, json=_body(source=..., gate0=...))
    assert created.status_code == 201
    assert created.json()["proposal"]["source"] is None


@pytest.mark.parametrize("description", [None, "", "too short"])
def test_the_description_is_still_required_and_at_least_20_characters(client, description):
    refused = client.post(BASE, json=_body(description=description))
    assert refused.status_code == 422
    assert _codes(refused)["description"] in ("description_required", "description_too_short")
    assert client.get(BASE).json()["proposals"] == []


@pytest.mark.parametrize(
    ("source", "field", "code"),
    [
        ("from a file", "source", "source_invalid"),
        ({**SOURCE, "evidence": [{"file": "x"}]}, "source.evidence", "unknown_field"),
        ({**SOURCE, "quote": "copied text"}, "source.quote", "unknown_field"),
        ({**SOURCE, "kind": "validator"}, "source.kind", "source_kind_invalid"),
        ({**SOURCE, "format": "something.else"}, "source.format", "source_format_invalid"),
        ({**SOURCE, "field_path": "context.environment"}, "source.field_path", "source_field_path_mismatch"),
        ({**SOURCE, "term": "three electrode static cell"}, "source.term", "source_term_mismatch"),
        ({k: v for k, v in SOURCE.items() if k != "term"}, "source.term", "source_term_required"),
        ({k: v for k, v in SOURCE.items() if k != "occurrences"}, "source.occurrences", "source_occurrences_required"),
        ({**SOURCE, "occurrences": 0}, "source.occurrences", "source_occurrences_invalid"),
        ({**SOURCE, "occurrences": True}, "source.occurrences", "source_occurrences_invalid"),
        ({**SOURCE, "runs": "2"}, "source.runs", "source_runs_invalid"),
        ({**SOURCE, "citations_total": -1}, "source.citations_total", "source_citations_total_invalid"),
        ({**SOURCE, "bundle_id": "x‮y"}, "source.bundle_id", "source_bundle_id_invalid"),
    ],
)
def test_each_source_rule(client, source, field, code):
    refused = client.post(BASE, json=_body(source=source))
    assert refused.status_code == 422, refused.json()
    assert _codes(refused)[field] == code
    assert client.get(BASE).json()["proposals"] == []


@pytest.mark.parametrize("missing", ["examples", "affected_records_estimate"])
def test_the_files_citations_and_counts_must_travel_as_reviewer_notes(client, missing):
    gate0 = {k: v for k, v in GATE0.items() if k != missing}
    refused = client.post(BASE, json=_body(gate0=gate0))
    assert refused.status_code == 422
    assert _codes(refused)[f"gate0.{missing}"] == f"gate0_{missing}_required"
    # Without a source the same notes are optional, as before.
    assert client.post(BASE, json=_body(gate0=gate0, source=...)).status_code == 201


def test_a_new_list_cannot_name_a_local_import(client):
    body = {
        "proposal_type": "add_category",
        "section": "Context",
        "category": "context.transport.viscosity",
        "description": "Dynamic viscosity of the electrolyte, needed to describe flow cells.",
        "gate0": GATE0,
        "source": {**SOURCE, "field_path": "context.transport.viscosity"},
    }
    refused = client.post(BASE, json=body)
    assert refused.status_code == 422
    assert _codes(refused)["source"] == "source_not_for_type"


def test_provenance_at_the_top_level_is_still_refused(client):
    """`source` is the one provenance key; `evidence` or `citations` beside it are unknown."""
    for key in ("evidence", "citations", "portal_payload"):
        refused = client.post(BASE, json={**_body(), key: [{"file": "x", "locator": "y"}]})
        assert refused.status_code == 422
        assert _codes(refused)[key] == "unknown_field"


def test_a_duplicate_pending_proposal_is_still_a_409_with_or_without_a_source(client):
    assert client.post(BASE, json=_body()).status_code == 201
    again = client.post(BASE, json=_body())
    assert again.status_code == 409 and again.json()["error"] == "duplicate_pending_proposal"
    typed = client.post(BASE, json=_body(source=..., gate0=...))
    assert typed.status_code == 409 and typed.json()["error"] == "duplicate_pending_proposal"


def test_a_term_the_portal_already_has_is_still_a_409(client):
    body = _body(term="h_cell", source={**SOURCE, "term": "h_cell"})
    refused = client.post(BASE, json=body)
    assert refused.status_code == 409 and refused.json()["error"] == "term_already_exists"


def test_a_stored_source_of_the_wrong_shape_never_rides_out(client):
    created = client.post(BASE, json=_body()).json()["proposal"]
    doc = sp._load(created["id"])
    doc["source"] = {**doc["source"], "occurrences": "many", "secret": "x"}
    sp._save(doc)
    view = client.get(f"{BASE}/{created['id']}").json()["proposal"]["source"]
    assert view["occurrences"] is None and "secret" not in view
    doc["source"] = {"kind": "something_else"}
    sp._save(doc)
    assert client.get(f"{BASE}/{created['id']}").json()["proposal"]["source"] is None


# The route table (no approve, apply, send or import route) is pinned exactly by
# test_schema_proposals.test_no_route_can_approve_apply_or_review; this change adds none.
