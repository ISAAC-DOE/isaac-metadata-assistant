"""Schema change requests: an ISAAC-side proposal for a new FIELD in the record schema.

THE UPSTREAM PORTAL HAS NO SUCH PROPOSAL TYPE (``portal/database.py`` ``create_proposal``
and ``portal/ontology.py`` ``apply_approved_proposal`` know ``add_term`` and ``add_category``
only, at ``a1cb1c8``), so these tests pin that the third type:

* is checked against REAL schema paths, derived from the vendored schema, never a list;
* is refused a portal payload, and exported only as a labelled change-request document;
* carries the same honesty as the other two types (no author, temporary, never sent);
* lives in the same store and list as the other two (one screen, one list).

Every refusal has a positive control beside it, so a test cannot pass because the route
refuses everything.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from isaac_api import schema_proposal_rules as rules
from isaac_api import schema_proposals as sp

BASE = "/api/schema-proposals"

FIELD_BODY = {
    "proposal_type": "schema_change",
    "section": "Context",
    "description": "The C-rate of a battery cycling test: the current as a multiple of the capacity.",
    "gate0": {
        "problem": "Two of three battery sets wrote an areal current the paper never gives (3 of 3 runs).",
        "flip_list": "Battery records gain a C-rate; no electrocatalysis record changes.",
    },
    "change": {
        "kind": "add_field",
        "parent_path": "context.electrochemistry",
        "field_name": "c_rate",
        "value_type": "number",
        "unit": "1/h",
        "required": False,
        "example": "0.5",
        "scope": "domain_profile",
    },
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _body(**change_overrides):
    body = copy.deepcopy(FIELD_BODY)
    for key, value in change_overrides.items():
        if value is _DROP:
            body["change"].pop(key, None)
        else:
            body["change"][key] = value
    return body


_DROP = object()


def _schema() -> dict:
    return json.loads(sp._schema_file().read_text(encoding="utf-8"))


def _codes(response) -> set[str]:
    return {e["code"] for e in response.json().get("errors", [])}


# --- the places a field can go are DERIVED from the schema ----------------------


def test_object_paths_are_every_declared_block_with_its_real_fields():
    paths = {p["path"]: p for p in rules.derive_object_paths(_schema())}
    schema = _schema()
    # The root and a nested block, with the schema's own field names and closedness.
    assert paths[""]["section"] == "Record Info"
    assert paths[""]["fields"] == list(schema["properties"])
    echem = schema["properties"]["context"]["properties"]["electrochemistry"]
    assert paths["context.electrochemistry"]["fields"] == list(echem["properties"])
    assert paths["context.electrochemistry"]["open"] is (echem.get("additionalProperties", True) is not False)
    # An array is looked through to its items.
    assert "descriptors.outputs" in paths
    # A leaf is not a place a field can go.
    assert "context.temperature_K" not in paths


def test_a_block_added_to_the_schema_appears_and_a_removed_one_disappears():
    schema = _schema()
    mutated = copy.deepcopy(schema)
    mutated["properties"]["context"]["properties"]["photochemistry"] = {
        "type": "object",
        "properties": {"wavelength_nm": {"type": "number"}},
    }
    del mutated["properties"]["context"]["properties"]["transport"]
    paths = {p["path"] for p in rules.derive_object_paths(mutated)}
    assert "context.photochemistry" in paths
    assert "context.transport" not in paths and "context.transport.feed" not in paths
    # Negative control: the unmutated schema has the opposite.
    original = {p["path"] for p in rules.derive_object_paths(schema)}
    assert "context.photochemistry" not in original and "context.transport" in original


def test_the_vocabulary_names_the_third_type_and_says_the_portal_has_none(client):
    body = client.get(f"{BASE}/vocabulary").json()
    assert body["proposal_types"] == ["add_term", "add_category", "schema_change"]
    assert body["portal_proposal_types"] == ["add_term", "add_category"]
    change = body["schema_change"]
    assert change["kinds"] == ["add_field"]
    assert "no proposal type for a new field" in change["not_a_portal_proposal"]
    served = {p["path"] for p in change["object_paths"]}
    assert served == {p["path"] for p in rules.derive_object_paths(_schema())}
    assert change["upstream"]["repository"] == "https://github.com/ISAAC-DOE/isaac-ai-ready-record"


# --- creating one ---------------------------------------------------------------


def test_a_schema_change_request_is_saved_pending_unattributed_and_temporary(client):
    response = client.post(BASE, json={**FIELD_BODY, "proposed_by": "someone typed this"})
    assert response.status_code == 201, response.json()
    body = response.json()
    proposal = body["proposal"]
    assert proposal["proposal_type"] == "schema_change"
    assert proposal["category"] == "context.electrochemistry.c_rate"
    assert proposal["term"] is None
    assert proposal["status"] == "pending"
    assert proposal["proposed_by"] is None and proposal["attribution"] == "unverified"
    assert body["ignored_fields"] == ["proposed_by"]
    assert body["persistence"]["survives_restart"] == "not_guaranteed"
    assert proposal["sent_by_isaac"] is False
    change = proposal["change"]
    assert change["path"] == "context.electrochemistry.c_rate"
    assert change["value_type"] == "number" and change["unit"] == "1/h" and change["required"] is False
    # Measured from the schema, not asserted from the body.
    echem = _schema()["properties"]["context"]["properties"]["electrochemistry"]
    assert change["parent_open_today"] is (echem.get("additionalProperties", True) is not False)
    # The same list as the other two types.
    listed = client.get(BASE).json()["proposals"]
    assert [p["id"] for p in listed] == [proposal["id"]]


def test_a_root_field_is_allowed_under_record_info(client):
    body = copy.deepcopy(FIELD_BODY)
    body["section"] = "Record Info"
    body["change"]["parent_path"] = ""
    body["change"]["field_name"] = "embargo_until"
    body["change"]["value_type"] = "string"
    body["change"].pop("unit")
    body["change"].pop("example")
    response = client.post(BASE, json=body)
    assert response.status_code == 201, response.json()
    assert response.json()["proposal"]["category"] == "embargo_until"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"parent_path": "context.nowhere"}, "unknown_parent_path"),
        ({"parent_path": "context.temperature_K"}, "unknown_parent_path"),  # a leaf, not a block
        ({"parent_path": _DROP}, "parent_path_required"),
        ({"parent_path": "system"}, "parent_outside_section"),  # section says Context
        ({"field_name": "c rate"}, "invalid_field_name"),
        ({"field_name": "1st"}, "invalid_field_name"),
        ({"field_name": _DROP}, "field_name_required"),
        ({"value_type": "float"}, "invalid_value_type"),
        ({"required": "no"}, "required_must_be_stated"),
        ({"required": _DROP}, "required_must_be_stated"),
        ({"value_type": "boolean", "unit": "V", "example": _DROP}, "unit_not_allowed"),
        ({"example": "half"}, "example_does_not_fit_type"),
        ({"value_type": "integer", "example": "0.5"}, "example_does_not_fit_type"),
        ({"scope": "everyone"}, "invalid_scope"),
        ({"kind": "remove_field"}, "invalid_change_kind"),
        ({"colour": "red"}, "unknown_field"),
    ],
)
def test_a_bad_change_is_refused_per_field_and_nothing_is_saved(client, overrides, code):
    response = client.post(BASE, json=_body(**overrides))
    assert response.status_code == 422, response.json()
    assert code in _codes(response), response.json()
    assert all(e["field"] is None or e["field"].startswith("change") for e in response.json()["errors"])
    assert client.get(BASE).json()["total"] == 0


def test_the_positive_control_for_every_refusal_above_is_accepted(client):
    # The unmodified body passes, so each refusal above is about its own override.
    assert client.post(BASE, json=_body()).status_code == 201


def test_examples_that_fit_their_type_are_accepted(client):
    cases = [
        ("integer", "3", "n_cycles"),
        ("integer", "3.0", "n_cycles_float"),  # JSON Schema counts 3.0 as an integer
        ("boolean", "true", "is_pristine"),
        ("array", "[1, 2]", "cycle_numbers"),
        ("object", '{"a": 1}', "cell_stack"),
        ("string", "anything at all", "separator_name"),
    ]
    for value_type, example, name in cases:
        body = _body(value_type=value_type, example=example, field_name=name, unit=_DROP)
        response = client.post(BASE, json=body)
        assert response.status_code == 201, (value_type, response.json())


def test_a_schema_change_needs_its_problem(client):
    body = copy.deepcopy(FIELD_BODY)
    body["gate0"] = {"flip_list": "Something."}
    response = client.post(BASE, json=body)
    assert response.status_code == 422
    assert "gate0_problem_required" in _codes(response)
    body.pop("gate0")
    assert "gate0_problem_required" in _codes(client.post(BASE, json=body))
    # Negative control: a NEW TERM still needs no problem (its rule is unchanged).
    term = {
        "proposal_type": "add_term",
        "section": "System",
        "category": "system.technique",
        "term": "XMCD",
        "description": "X-ray magnetic circular dichroism, measured at several SSRL beamlines.",
    }
    assert client.post(BASE, json=term).status_code == 201


def test_a_schema_change_takes_no_category_or_term_and_the_others_take_no_change(client):
    with_category = {**FIELD_BODY, "category": "context.electrochemistry.c_rate"}
    assert "category_not_allowed" in _codes(client.post(BASE, json=with_category))
    with_term = {**FIELD_BODY, "term": "c_rate"}
    assert "term_not_allowed" in _codes(client.post(BASE, json=with_term))
    term_with_change = {
        "proposal_type": "add_term",
        "section": "System",
        "category": "system.technique",
        "term": "XMCD",
        "description": "X-ray magnetic circular dichroism, measured at several SSRL beamlines.",
        "change": FIELD_BODY["change"],
    }
    assert "change_not_allowed" in _codes(client.post(BASE, json=term_with_change))
    missing_change = {k: v for k, v in FIELD_BODY.items() if k != "change"}
    assert "change_required" in _codes(client.post(BASE, json=missing_change))


def test_a_field_the_schema_already_has_is_a_conflict_case_insensitively(client):
    existing = _schema()["properties"]["context"]["properties"]["electrochemistry"]["properties"]
    # A mixed-case field the schema really has, spelled all-lowercase: dropping the casefold
    # in the conflict check lets this through.
    assert "potential_vs_RHE" in existing
    for name, spelled in (("potential_vs_RHE", "potential_vs_RHE"), ("potential_vs_RHE", "potential_vs_rhe")):
        response = client.post(BASE, json=_body(field_name=spelled))
        assert response.status_code == 409, response.json()
        assert response.json()["error"] == "field_already_exists"
        assert response.json()["existing_field"] == f"context.electrochemistry.{name}"
    assert client.get(BASE).json()["total"] == 0


def test_the_same_change_pending_twice_is_a_duplicate_and_withdrawing_frees_it(client):
    first = client.post(BASE, json=FIELD_BODY)
    assert first.status_code == 201
    again = client.post(BASE, json=FIELD_BODY)
    assert again.status_code == 409 and again.json()["error"] == "duplicate_pending_proposal"
    pid = first.json()["proposal"]["id"]
    assert client.post(f"{BASE}/{pid}/withdraw").status_code == 200
    assert client.post(BASE, json=FIELD_BODY).status_code == 201


# --- the export: a document, never a portal payload ------------------------------


def test_a_schema_change_has_no_portal_payload(client):
    pid = client.post(BASE, json=FIELD_BODY).json()["proposal"]["id"]
    response = client.get(f"{BASE}/{pid}/portal-payload")
    assert response.status_code == 409
    assert response.json()["error"] == "no_portal_payload"
    assert "no proposal type for a new field" in response.json()["message"]


def test_a_new_term_has_no_change_request_but_keeps_its_portal_payload(client):
    term = {
        "proposal_type": "add_term",
        "section": "System",
        "category": "system.technique",
        "term": "XMCD",
        "description": "X-ray magnetic circular dichroism, measured at several SSRL beamlines.",
    }
    pid = client.post(BASE, json=term).json()["proposal"]["id"]
    assert client.get(f"{BASE}/{pid}/change-request").json()["error"] == "not_a_schema_change"
    payload = client.get(f"{BASE}/{pid}/portal-payload")
    assert payload.status_code == 200
    assert payload.json()["body"] == {
        "proposal_type": "add_term",
        "section": "System",
        "category": "system.technique",
        "term": "XMCD",
        "description": term["description"],
    }


def test_the_change_request_document_carries_exactly_what_was_proposed(client):
    pid = client.post(BASE, json=FIELD_BODY).json()["proposal"]["id"]
    response = client.get(f"{BASE}/{pid}/change-request")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["is_portal_payload"] is False and body["sent_by_isaac"] is False
    assert body["format"] == "isaac.schema-change-request"
    assert body["persistence"]["survives_restart"] == "not_guaranteed"
    doc = body["document"]
    assert doc["is_portal_payload"] is False
    assert doc["change"]["path"] == "context.electrochemistry.c_rate"
    assert doc["definition"] == FIELD_BODY["description"]
    assert doc["gate0"]["problem"] == FIELD_BODY["gate0"]["problem"]
    assert doc["gate0"]["examples"] is None
    assert doc["provenance"]["proposed_by"] is None
    assert doc["provenance"]["sent_by_isaac"] is False and doc["provenance"]["approved_in_isaac"] is False
    assert "approved_by_anyone" not in doc["provenance"]  # ISAAC cannot see an upstream decision
    assert doc["provenance"]["schema_sha256"] == sp.load_vocabulary()["schema_sha256"]
    md = body["markdown"]
    assert md.startswith("# Proposed schema change: add `context.electrochemistry.c_rate`")
    assert "not a portal proposal" in md
    assert FIELD_BODY["gate0"]["problem"] in md and FIELD_BODY["description"] in md
    assert "not recorded (who drafted this was not verified)" in md
    assert "ISAAC approves nothing and records no decision" in md and "nobody has approved" not in md
    assert "Status in ISAAC:** pending" in md and "WITHDRAWN" not in md
    # The envelope's own sentences fit a schema change: no "copy the portal payload" as the only route.
    assert "change-request document" in body["persistence"]["message"]
    assert "upstream repository" in body["review_note"]
    # A section the proposer did not write SAYS so; the two written ones do not.
    assert md.count("Not written yet.") == 3  # examples, records affected, migration
    assert any("turned off" in note for note in body["notes"])


def test_a_pipe_in_a_table_value_cannot_break_the_change_table():
    doc = {
        "id": "01J0000000000000000000000",
        "proposal_type": "schema_change",
        "category": "context.electrochemistry.c_rate",
        "description": "A definition long enough.",
        "status": "pending",
        "change": {
            "kind": "add_field",
            "path": "context.electrochemistry.c_rate",
            "parent_path": "context.electrochemistry",
            "field_name": "c_rate",
            "value_type": "number",
            "unit": "mA|g",
            "required": False,
        },
    }
    md = rules.change_request(doc, schema_version="1.05", schema_sha256=None)["markdown"]
    unit_row = next(line for line in md.splitlines() if line.startswith("| Unit"))
    assert unit_row == "| Unit | mA\\|g |"


def test_a_stored_file_with_an_unexpected_change_key_does_not_leak_it(client):
    pid = client.post(BASE, json=FIELD_BODY).json()["proposal"]["id"]
    path = sp.store_root() / f"{pid}.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["change"]["secret"] = "do not show"
    stored["change"]["unit"] = {"not": "text"}
    path.write_text(json.dumps(stored), encoding="utf-8")
    change = client.get(f"{BASE}/{pid}").json()["proposal"]["change"]
    assert "secret" not in change
    assert change["unit"] is None


def test_a_stored_schema_change_without_its_change_is_unreadable_not_a_crash(client):
    pid = client.post(BASE, json=FIELD_BODY).json()["proposal"]["id"]
    path = sp.store_root() / f"{pid}.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored.pop("change")
    path.write_text(json.dumps(stored), encoding="utf-8")
    assert client.get(f"{BASE}/{pid}").status_code == 404
    assert client.get(BASE).json()["total"] == 0


def test_the_rules_module_imports_no_web_framework():
    """The local CLI imports the rules module; a local install has no FastAPI."""
    import subprocess
    import sys

    code = (
        "import sys; import isaac_api.schema_proposal_rules as r; "
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('fastapi', 'starlette', 'pydantic', 'uvicorn')); "
        "print(','.join(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "", out.stdout


def test_a_withdrawn_change_request_still_exports_and_says_it_was_withdrawn(client):
    pid = client.post(BASE, json=FIELD_BODY).json()["proposal"]["id"]
    assert client.post(f"{BASE}/{pid}/withdraw").status_code == 200
    body = client.get(f"{BASE}/{pid}/change-request").json()
    assert body["status"] == "withdrawn"
    assert "Status in ISAAC:** WITHDRAWN on " in body["markdown"]
    assert body["document"]["status_in_isaac"] == "withdrawn"


def test_the_term_shape_served_to_the_browser_is_the_one_the_server_enforces(client):
    import re

    shape = client.get(f"{BASE}/vocabulary").json()["term_shape"]
    for term in ("catalytic_reactor_test", "HERFD-XAS", "Ag/AgCl", "cathodic corrosion", "a..b", "1abc"):
        served = bool(re.search(shape["term"], term)) and not re.search(shape["path_like"], term)
        server = bool(rules._TERM_SHAPE.match(term)) and not rules._PATH_LIKE.search(term)
        assert served == server, term
