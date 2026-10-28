"""Schema Proposals: drafting and tracking proposals to change the ISAAC vocabulary.

These tests pin BEHAVIOUR, not copy: that the vocabulary is derived from the vendored
schema, that a proposal can be created, listed, read and withdrawn, that nothing here
can approve or send anything, that identity is never taken from the body, and that the
portal payload carries exactly the upstream field names.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from isaac_api import identity as identity_module
from isaac_api import schema_proposals as sp
from isaac_api import workspace as ws

BASE = "/api/schema-proposals"

TERM_BODY = {
    "proposal_type": "add_term",
    "section": "System",
    "category": "system.technique",
    "term": "XMCD",
    "description": "X-ray magnetic circular dichroism, measured at several SSRL beamlines.",
}
CATEGORY_BODY = {
    "proposal_type": "add_category",
    "section": "Context",
    "category": "context.transport.viscosity",
    "description": "Dynamic viscosity of the electrolyte, needed to describe flow cells.",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _create(client, body=None, **overrides):
    payload = dict(body or TERM_BODY)
    payload.update(overrides)
    return client.post(BASE, json=payload)


# --- the vocabulary is DERIVED from the schema ----------------------------------


def _schema() -> dict:
    return json.loads(sp._schema_file().read_text(encoding="utf-8"))


def _terms(vocabulary: dict, key: str, source: str | None = None) -> list[str]:
    """Terms of ``key`` in a derived vocabulary, or in one source of the endpoint's response."""
    if "sources" in vocabulary:
        vocabulary = vocabulary["sources"][source or "schema"]
    for section in vocabulary["sections"]:
        for category in section["categories"]:
            if category["key"] == key:
                return category["terms"]
    raise AssertionError(f"no category {key}")


def test_a_term_present_in_the_schema_appears_in_the_vocabulary(client):
    body = client.get(f"{BASE}/vocabulary").json()
    schema_enum = _schema()["properties"]["system"]["properties"]["technique"]["enum"]
    assert _terms(body, "system.technique") == schema_enum
    schema_side = body["sources"]["schema"]
    assert schema_side["term_count"] == sum(
        len(c["terms"]) for s in schema_side["sections"] for c in s["categories"]
    )
    assert schema_side["sections"][0]["id"] == "Record Info"
    assert "record_type" in [c["key"] for c in schema_side["sections"][0]["categories"]]
    assert body["schema_version"] == "1.05"
    assert re.fullmatch(r"[0-9a-f]{64}", schema_side["sha256"])


def test_the_vocabulary_is_derived_not_transcribed(tmp_path):
    """Mutate a COPY of the schema: the derived vocabulary follows it exactly."""
    original = _schema()
    mutated = copy.deepcopy(original)
    mutated["properties"]["system"]["properties"]["technique"]["enum"].append("zz_invented_term")
    mutated["properties"]["system"]["properties"]["brand_new_field"] = {
        "type": "string",
        "enum": ["alpha", "beta"],
        "description": "A field the vendored schema does not have.",
    }
    del mutated["properties"]["record_domain"]

    before = sp.derive_vocabulary(original)
    after = sp.derive_vocabulary(mutated)

    assert "zz_invented_term" not in _terms(before, "system.technique")
    assert "zz_invented_term" in _terms(after, "system.technique")
    assert _terms(after, "system.brand_new_field") == ["alpha", "beta"]
    root_keys = [c["key"] for c in after["sections"][0]["categories"]]
    assert "record_domain" not in root_keys and "record_type" in root_keys


def test_an_enum_inside_a_condition_is_not_a_list_of_allowed_terms():
    schema = {
        "properties": {
            "block": {
                "type": "object",
                "properties": {"kind": {"type": "string", "enum": ["a", "b"]}},
            }
        },
        "allOf": [{"if": {"properties": {"kind": {"enum": ["a"]}}}, "then": {}}],
    }
    vocabulary = sp.derive_vocabulary(schema)
    assert vocabulary["category_count"] == 1
    assert _terms(vocabulary, "block.kind") == ["a", "b"]


def test_the_route_reads_the_schema_file_it_is_pointed_at(client, tmp_path, monkeypatch):
    mutated = _schema()
    mutated["properties"]["system"]["properties"]["technique"]["enum"].append("zz_invented_term")
    path = tmp_path / "mutated_schema.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    monkeypatch.setattr(sp, "_schema_file", lambda: path)

    body = client.get(f"{BASE}/vocabulary").json()
    assert "zz_invented_term" in _terms(body, "system.technique")

    # ...and a proposal for it is then refused, because the (mutated) schema has it.
    refused = _create(client, term="zz_invented_term")
    assert refused.status_code == 409
    assert refused.json()["error"] == "term_already_exists"


# --- create / list / get / withdraw --------------------------------------------


def test_create_list_get_and_withdraw(client):
    created = _create(client)
    assert created.status_code == 201
    proposal = created.json()["proposal"]
    assert proposal["status"] == "pending"
    assert proposal["proposal_type"] == "add_term"
    assert proposal["term"] == "XMCD"

    listed = client.get(BASE).json()
    assert listed["total"] == 1
    assert [p["id"] for p in listed["proposals"]] == [proposal["id"]]
    assert listed["statuses"] == ["pending", "withdrawn"]

    got = client.get(f"{BASE}/{proposal['id']}").json()
    assert got["proposal"] == proposal

    withdrawn = client.post(f"{BASE}/{proposal['id']}/withdraw")
    assert withdrawn.status_code == 200
    assert withdrawn.json()["proposal"]["status"] == "withdrawn"
    assert withdrawn.json()["proposal"]["withdrawn_at"]

    # Only a pending proposal can be withdrawn.
    again = client.post(f"{BASE}/{proposal['id']}/withdraw")
    assert again.status_code == 409
    assert again.json()["error"] == "not_pending"

    # The withdrawn proposal is kept, and filterable.
    assert client.get(f"{BASE}?status=withdrawn").json()["total"] == 1
    assert client.get(f"{BASE}?status=pending").json()["total"] == 0


def test_list_is_newest_first_and_paginated(client):
    ids = []
    for term in ("alpha_one", "alpha_two", "alpha_three"):
        ids.append(_create(client, term=term, category="system.technique").json()["proposal"]["id"])
    page = client.get(f"{BASE}?limit=2").json()
    assert [p["id"] for p in page["proposals"]] == [ids[2], ids[1]]
    assert page["next_offset"] == 2 and page["total"] == 3
    rest = client.get(f"{BASE}?limit=2&offset=2").json()
    assert [p["id"] for p in rest["proposals"]] == [ids[0]]
    assert rest["next_offset"] is None


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "status=accepted"])
def test_list_is_bounded(client, query):
    assert client.get(f"{BASE}?{query}").status_code == 422


def test_an_unknown_or_malformed_id_is_404(client):
    for suffix in ("not-an-id", "01M61TASK3DFS5VX1C7X1RZJS5", "../etc"):
        assert client.get(f"{BASE}/{suffix}").status_code in (404,)
    assert client.post(f"{BASE}/01M61TASK3DFS5VX1C7X1RZJS5/withdraw").status_code == 404
    assert client.get(f"{BASE}/01M61TASK3DFS5VX1C7X1RZJS5/portal-payload").status_code == 404


def test_a_corrupt_file_is_skipped_not_fatal(client):
    created = _create(client).json()["proposal"]
    root = sp.store_root()
    (root / "01M61TASK3DFS5VX1C7X1RZJS5.json").write_text("{not json", encoding="utf-8")
    listed = client.get(BASE).json()
    assert [p["id"] for p in listed["proposals"]] == [created["id"]]


# --- refusals ------------------------------------------------------------------


def test_an_existing_term_is_a_409_case_insensitively(client):
    refused = _create(client, term="xas")
    assert refused.status_code == 409
    body = refused.json()
    assert body["error"] == "term_already_exists"
    assert body["existing_term"] == "XAS"
    # separators do not make a different term
    assert _create(client, term="HERFD_XAS").status_code == 409
    assert client.get(BASE).json()["total"] == 0


def test_an_existing_category_is_a_409(client):
    refused = _create(client, CATEGORY_BODY, category="system.technique", section="System")
    assert refused.status_code == 409
    assert refused.json()["error"] == "category_already_exists"


def test_a_duplicate_pending_proposal_is_a_409_until_it_is_withdrawn(client):
    first = _create(client).json()["proposal"]
    duplicate = _create(client, term="xmcd")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "duplicate_pending_proposal"
    assert duplicate.json()["proposal_id"] == first["id"]
    client.post(f"{BASE}/{first['id']}/withdraw")
    assert _create(client).status_code == 201


def test_validation_errors_are_typed_and_per_field(client):
    response = client.post(
        BASE,
        json={
            "proposal_type": "add_term",
            "section": "Nope",
            "category": "",
            "term": "has space",
            "description": "short",
        },
    )
    assert response.status_code == 422
    body = response.json()
    by_field = {e["field"]: e["code"] for e in body["errors"]}
    assert by_field["section"] == "unknown_section"
    assert by_field["category"] == "category_required"
    assert by_field["term"] == "invalid_term"
    assert by_field["description"] == "description_too_short"
    assert body["error"] == body["errors"][0]["code"]


@pytest.mark.parametrize(
    ("overrides", "field", "code"),
    [
        ({"proposal_type": "approve"}, "proposal_type", "invalid_proposal_type"),
        ({"section": "System", "category": "system.nothing"}, "category", "unknown_category"),
        ({"term": ""}, "term", "term_required"),
        ({"term": "x" * 81}, "term", "term_too_long"),
        ({"term": "9lives"}, "term", "invalid_term"),
        ({"term": "Has_Upper_Mixed"}, "term", None),  # allowed in a mixed-case category
        ({"description": "x" * 2001}, "description", "description_too_long"),
        ({"description": None}, "description", "description_required"),
        ({"description": 7}, "description", "description_invalid"),
        ({"description": "bad \x00 byte " + "x" * 30}, "description", "description_invalid"),
        ({"surprise": 1}, "surprise", "unknown_field"),
        ({"gate0": "text"}, "gate0", "gate0_invalid"),
        ({"gate0": {"problem": "x" * 2001}}, "gate0.problem", "gate0_problem_too_long"),
        ({"gate0": {"mystery": "x"}}, "gate0.mystery", "unknown_field"),
    ],
)
def test_each_validation_rule(client, overrides, field, code):
    response = _create(client, **overrides)
    if code is None:
        assert response.status_code == 201
        return
    assert response.status_code == 422, response.text
    errors = {e["field"]: e["code"] for e in response.json()["errors"]}
    assert errors[field] == code


def test_a_new_term_in_an_all_snake_case_category_must_be_snake_case(client):
    refused = _create(client, section="Context", category="context.environment", term="Liquid")
    assert refused.status_code == 422
    assert refused.json()["errors"][0]["code"] == "invalid_term"
    assert _create(client, section="Context", category="context.environment", term="molten_salt").status_code == 201


def test_add_category_rules(client):
    assert _create(client, CATEGORY_BODY).status_code == 201
    outside = _create(client, CATEGORY_BODY, category="sample.viscosity")
    assert outside.status_code == 422
    assert outside.json()["errors"][0]["code"] == "category_outside_section"
    with_term = _create(client, CATEGORY_BODY, term="x")
    assert with_term.status_code == 422
    assert {e["code"] for e in with_term.json()["errors"]} == {"term_not_allowed"}
    bad_shape = _create(client, CATEGORY_BODY, category="context..bad key")
    assert bad_shape.json()["errors"][0]["code"] == "invalid_category"


def test_a_body_that_is_not_an_object_is_refused(client):
    for body in ([], "x", 3):
        assert client.post(BASE, json=body).status_code == 422


def test_too_many_pending_proposals_are_refused(client, monkeypatch):
    monkeypatch.setitem(sp.LIMITS, "max_pending", 2)
    assert _create(client, term="one_term").status_code == 201
    assert _create(client, term="two_term").status_code == 201
    third = _create(client, term="three_term")
    assert third.status_code == 429
    assert third.json()["error"] == "too_many_pending"


# --- nothing approves, applies or sends ----------------------------------------


def test_no_route_can_approve_apply_or_review(client):
    paths = sorted(
        {
            (r.path, m)
            for r in _walk(client.app)
            for m in r.methods
            if r.path.startswith(BASE)
        }
    )
    assert paths == sorted(
        [
            (BASE, "GET"),
            (BASE, "POST"),
            (f"{BASE}/vocabulary", "GET"),
            (f"{BASE}/{{proposal_id}}", "GET"),
            (f"{BASE}/{{proposal_id}}/withdraw", "POST"),
            (f"{BASE}/{{proposal_id}}/portal-payload", "GET"),
        ]
    )
    for path, _ in paths:
        assert not re.search(r"approve|apply|accept|reject|review|decide", path)
    created = _create(client).json()["proposal"]
    for verb in ("approve", "apply", "accept", "reject"):
        assert client.post(f"{BASE}/{created['id']}/{verb}").status_code in (404, 405)
    assert client.patch(f"{BASE}/{created['id']}", json={"status": "accepted"}).status_code == 405
    assert client.get(f"{BASE}/{created['id']}").json()["proposal"]["status"] == "pending"


def _walk(node):
    for route in getattr(node, "routes", []):
        if isinstance(route, APIRoute):
            yield route
        else:
            yield from _walk(route)
    included = getattr(node, "original_router", None)
    if included is not None:
        yield from _walk(included)


def test_the_module_cannot_call_the_portal():
    source = Path(sp.__file__).read_text(encoding="utf-8")
    for needle in ("import requests", "import httpx", "urllib.request", "http.client", "aiohttp", "socket"):
        assert needle not in source, needle


def test_the_status_vocabulary_has_no_review_decisions():
    assert sp.PROPOSAL_STATUSES == ("pending", "withdrawn")


def test_the_vocabulary_and_payload_say_isaac_does_not_send_or_decide(client):
    created = _create(client).json()
    assert created["proposal"]["sent_by_isaac"] is False
    assert "portal" in created["review_note"].lower()
    payload = client.get(f"{BASE}/{created['proposal']['id']}/portal-payload").json()
    assert payload["sent_by_isaac"] is False


# --- identity is never taken from the body -------------------------------------


def test_a_body_supplied_proposed_by_is_ignored(client):
    response = _create(client, proposed_by="someone_important", attribution="verified", status="accepted")
    assert response.status_code == 201
    body = response.json()
    proposal = body["proposal"]
    assert proposal["proposed_by"] is None
    assert proposal["attribution"] == "unverified"
    assert proposal["status"] == "pending"
    assert body["ignored_fields"] == ["attribution", "proposed_by", "status"]
    stored = json.loads((sp.store_root() / f"{proposal['id']}.json").read_text())
    assert "someone_important" not in json.dumps(stored)


def test_a_forged_identity_header_establishes_nobody(client):
    response = client.post(
        BASE, json=TERM_BODY, headers={"X-authentik-username": "forged", "X-Isaac-Edge": "x"}
    )
    assert response.json()["proposal"]["proposed_by"] is None
    assert response.json()["proposal"]["attribution"] == "unverified"


def test_a_verified_person_is_recorded_and_a_fixture_is_not(client, monkeypatch):
    def identity_for(basis):
        actor = identity_module.HumanActor(subject="real_user", trust_basis=basis)
        return identity_module.RequestIdentity.for_human(actor)

    monkeypatch.setattr(
        sp.identity_module,
        "resolve_identity_for_request",
        lambda request: identity_for(identity_module.TRUST_BASIS_VERIFIED_EDGE_ASSERTION),
    )
    verified = _create(client).json()["proposal"]
    assert verified["proposed_by"] == "real_user"
    assert verified["attribution"] == "verified"

    monkeypatch.setattr(
        sp.identity_module,
        "resolve_identity_for_request",
        lambda request: identity_for(identity_module.TRUST_BASIS_TEST_FIXTURE),
    )
    fixture = _create(client, term="another_term").json()["proposal"]
    assert fixture["proposed_by"] is None
    assert fixture["attribution"] == "unverified"


# --- the portal payload ---------------------------------------------------------

#: The fields the upstream portal reads (portal/api.py `vocabulary_propose`) and writes
#: (portal/database.py `create_proposal`).
UPSTREAM_ADD_TERM_FIELDS = {"proposal_type", "section", "category", "term", "description"}
UPSTREAM_ADD_CATEGORY_FIELDS = {"proposal_type", "section", "category", "description"}


def test_portal_payload_shape_for_add_term(client):
    created = _create(client).json()["proposal"]
    payload = client.get(f"{BASE}/{created['id']}/portal-payload").json()
    assert set(payload["body"]) == UPSTREAM_ADD_TERM_FIELDS
    assert payload["body"] == {**TERM_BODY}
    assert payload["portal"] == {
        "method": "POST",
        "path": "/portal/api/vocabulary/proposals",
        "rest_supported": True,
    }
    # The portal's own validation would accept it.
    body = payload["body"]
    assert body["term"] and len(body["term"]) <= 80 and not any(c.isspace() for c in body["term"])
    assert len(body["description"]) >= 20


def test_portal_payload_shape_for_add_category(client):
    created = _create(client, CATEGORY_BODY).json()["proposal"]
    payload = client.get(f"{BASE}/{created['id']}/portal-payload").json()
    assert set(payload["body"]) == UPSTREAM_ADD_CATEGORY_FIELDS
    assert "term" not in payload["body"]
    assert payload["portal"]["rest_supported"] is False


def test_portal_payload_appends_reviewer_notes_to_the_description(client):
    created = _create(
        client,
        gate0={
            "problem": "Eleven records carry a note admitting a substituted technique.",
            "examples": "rec_a, rec_b",
            "affected_records_estimate": "about 11",
            "flip_list": "Those eleven would validate cleanly.",
        },
    ).json()["proposal"]
    assert created["gate0"]["affected_records_estimate"] == "about 11"
    payload = client.get(f"{BASE}/{created['id']}/portal-payload").json()
    assert set(payload["body"]) == UPSTREAM_ADD_TERM_FIELDS
    description = payload["body"]["description"]
    assert description.startswith(TERM_BODY["description"])
    for text in ("Eleven records", "rec_a, rec_b", "about 11", "validate cleanly"):
        assert text in description
    # without reviewer notes the description is untouched
    plain = _create(client, term="plain_term").json()["proposal"]
    assert client.get(f"{BASE}/{plain['id']}/portal-payload").json()["body"]["description"] == TERM_BODY["description"]


# --- persistence is disclosed ---------------------------------------------------


def test_every_response_says_proposals_are_temporary(client):
    created = _create(client).json()
    pid = created["proposal"]["id"]
    for response in (
        created,
        client.get(BASE).json(),
        client.get(f"{BASE}/{pid}").json(),
        client.get(f"{BASE}/{pid}/portal-payload").json(),
        client.post(f"{BASE}/{pid}/withdraw").json(),
    ):
        assert response["persistence"]["class"] == "workspace_files"
        assert response["persistence"]["survives_restart"] == "not_guaranteed"
        assert "portal" in response["persistence"]["message"].lower()


def test_proposals_live_under_the_workspace_and_touch_no_experiment_listing(client):
    _create(client)
    root = ws.workspace_root() / "_schema_proposals"
    assert root.is_dir() and len(list(root.glob("*.json"))) == 1
    assert ws._experiment_dirs(ws.workspace_root()) == []


def test_an_unwritable_store_is_a_503_and_nothing_is_claimed(client, monkeypatch):
    real = ws.atomic_write_text

    def boom(path, text):
        raise OSError("disk full")

    monkeypatch.setattr(ws, "atomic_write_text", boom)
    response = _create(client)
    assert response.status_code == 503
    assert response.json()["error"] == "proposal_store_unavailable"
    monkeypatch.setattr(ws, "atomic_write_text", real)
    assert client.get(BASE).json()["total"] == 0


# --- the classification other sweeps rely on ------------------------------------


def test_a_proposal_write_leaves_every_experiment_document_byte_identical(client):
    """`test_submitted_history_survives_every_write_path` lists both write routes as NOT
    addressed to an experiment record. This is the measurement that makes that true: with
    experiments present, create and withdraw change no file outside `_schema_proposals/`."""
    root = ws.workspace_root()
    for title in ("First record", "Second record"):
        assert client.post("/api/experiments", json={"title": title}).status_code in (200, 201)

    def snapshot() -> dict[str, bytes]:
        return {
            str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and sp.STORE_NAMESPACE not in p.relative_to(root).parts
        }

    before = snapshot()
    assert any(name.endswith("experiment.json") for name in before), "no experiment was created"

    created = _create(client).json()["proposal"]
    assert client.post(f"{BASE}/{created['id']}/withdraw").status_code == 200
    # A refused write touches nothing either.
    assert _create(client, term="xas").status_code == 409

    assert snapshot() == before
    assert (root / sp.STORE_NAMESPACE / f"{created['id']}.json").is_file()


# --- review fixes: the portal's vocabulary is a second, labelled source ----------------------

UPSTREAM_PORTAL_VOCABULARY_SHA256 = "7d60a2f0383b936ac055c309596e2ba9afe9fb9a1b893fe217f88e7a52b8d0f8"


def test_the_portal_snapshot_is_the_pinned_upstream_file_and_says_what_it_is(client):
    import hashlib

    assert hashlib.sha256(sp._portal_file().read_bytes()).hexdigest() == UPSTREAM_PORTAL_VOCABULARY_SHA256
    provenance = (sp._portal_file().parent / "PORTAL_VOCABULARY_PROVENANCE.md").read_text(encoding="utf-8")
    assert UPSTREAM_PORTAL_VOCABULARY_SHA256 in provenance and "a1cb1c861f3e6eb506da33f27196b43312f240f6" in provenance
    assert "snapshot" in provenance.lower() and "not an authority" in provenance.lower()
    assert sp._portal_file().parent.name == "data" and "schema" not in sp._portal_file().parts[-3:-1]

    body = client.get(f"{BASE}/vocabulary").json()
    portal, schema = body["sources"]["portal"], body["sources"]["schema"]
    assert portal["label"] == "Portal vocabulary (snapshot a1cb1c8)" and portal["snapshot_commit"] == "a1cb1c8"
    assert schema["label"] == "Schema enums (vendored v1.05)"
    assert portal["sha256"] == UPSTREAM_PORTAL_VOCABULARY_SHA256
    assert body["default_source"] == "portal"
    # The two sources really differ, which is why both are shown.
    portal_lists = {c["key"] for s in portal["sections"] for c in s["categories"] if c["kind"] == "terms"}
    schema_lists = {c["key"] for s in schema["sections"] for c in s["categories"]}
    assert portal_lists - schema_lists and schema_lists - portal_lists
    assert "sample.sample_form" in portal_lists and "sample.sample_form" not in schema_lists
    assert "Official Vocabulary" not in json.dumps(body)


def test_the_portal_side_is_derived_from_the_snapshot_file(client, tmp_path, monkeypatch):
    doc = json.loads(sp._portal_file().read_text(encoding="utf-8"))
    doc["Sample"]["sample.zz_new_list"] = {"description": "x", "values": ["only_term"]}
    path = tmp_path / "portal.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(sp, "_portal_file", lambda: path)
    assert _terms(client.get(f"{BASE}/vocabulary").json(), "sample.zz_new_list", "portal") == ["only_term"]
    assert _create(client, section="Sample", category="sample.zz_new_list", term="another_term").status_code == 201


def test_a_term_can_be_added_to_a_portal_list_the_schema_has_no_enum_for(client):
    # `sample.sample_form` is a portal list and not a schema enum: the previous build said unknown_category.
    created = _create(client, section="Sample", category="sample.sample_form", term="aerogel_monolith")
    assert created.status_code == 201, created.text
    payload = client.get(f"{BASE}/{created.json()['proposal']['id']}/portal-payload").json()
    assert payload["body"]["category"] == "sample.sample_form" and payload["portal"]["rest_supported"] is True


def test_an_existing_portal_term_is_a_409_naming_its_source(client):
    existing = sp.load_portal_vocabulary()
    terms = next(c["terms"] for s in existing["sections"] for c in s["categories"] if c["key"] == "sample.sample_form")
    refused = _create(client, section="Sample", category="sample.sample_form", term=terms[0])
    assert refused.status_code == 409 and refused.json()["error"] == "term_already_exists"
    assert refused.json()["existing_in"] == "portal"


def test_a_schema_only_list_is_refused_with_a_reason_the_portal_would_give(client):
    schema_only = "computation.method.relativistic"
    assert sp._schema_enum(sp.load_sources(), schema_only) is not None
    assert sp._portal_key_exists(sp.load_sources(), schema_only) is None
    refused = _create(client, section="Computation", category=schema_only, term="brand_new_term")
    assert refused.status_code == 422
    assert refused.json()["errors"][0]["code"] == "category_not_in_portal"
    assert client.get(BASE).json()["total"] == 0


def test_a_portal_list_in_the_wrong_section_is_unknown(client):
    refused = _create(client, section="System", category="sample.sample_form", term="aerogel_monolith")
    assert refused.status_code == 422 and refused.json()["errors"][0]["code"] == "unknown_category"


@pytest.mark.parametrize(
    ("section", "category", "status", "code"),
    [
        ("Sample", "sample.sample_form", 409, "category_already_exists"),  # a portal list
        ("System", "system.technique", 409, "category_already_exists"),  # a schema enum and a portal list
        ("Computation", "computation.method.relativistic", 409, "category_already_exists"),  # schema enum only
        ("Context", "context.temperature_K", 422, "category_not_a_text_field"),  # a number in the schema
        ("Sample", "sample.sample_id", 409, "category_already_exists"),  # an existing free-text field
        ("Units", "units.general", 409, "category_already_exists"),  # a portal entry with no term list
    ],
)
def test_a_new_category_is_refused_for_any_field_either_source_already_has(client, section, category, status, code):
    refused = _create(client, CATEGORY_BODY, section=section, category=category)
    assert refused.status_code == status, refused.text
    body = refused.json()
    found = body["error"] if status == 409 else body["errors"][0]["code"]
    assert found == code
    assert client.get(BASE).json()["total"] == 0


def test_a_genuinely_new_category_is_still_accepted(client):
    assert _create(client, CATEGORY_BODY).status_code == 201
    assert _create(client, CATEGORY_BODY, section="Units", category="units.zz_brand_new").status_code == 201


def test_the_proposal_sections_carry_the_portal_lists_a_term_may_join(client):
    sections = {s["id"]: s for s in client.get(f"{BASE}/vocabulary").json()["proposal_sections"]}
    assert "sample.sample_form" in sections["Sample"]["term_lists"]
    assert "Units" in sections and "Timestamps" in sections


# --- review fixes: capacity -----------------------------------------------------------------


def test_withdrawn_proposals_never_lock_the_store(client, monkeypatch):
    monkeypatch.setitem(sp.LIMITS, "max_pending", 2)
    monkeypatch.setitem(sp.LIMITS, "max_withdrawn_kept", 3)
    # Far more proposals than the old stored-cap (the pending cap here is 2) pass through, one at a time.
    for i in range(12):
        created = _create(client, term=f"cycle_term_{i}")
        assert created.status_code == 201, created.text
        assert client.post(f"{BASE}/{created.json()['proposal']['id']}/withdraw").status_code == 200
    listed = client.get(f"{BASE}?status=withdrawn").json()
    assert listed["total"] == 3, "only the newest max_withdrawn_kept withdrawn proposals stay on disk"
    assert listed["capacity"]["pending"] == 0 and listed["capacity"]["max_pending"] == 2
    assert "everyone using this server" in listed["capacity"]["scope"]


def test_the_oldest_withdrawn_are_removed_and_pending_ones_never_are(client, monkeypatch):
    monkeypatch.setitem(sp.LIMITS, "max_withdrawn_kept", 1)
    keep = _create(client, term="still_pending").json()["proposal"]
    first = _create(client, term="first_withdrawn").json()["proposal"]
    client.post(f"{BASE}/{first['id']}/withdraw")
    second = _create(client, term="second_withdrawn").json()["proposal"]
    client.post(f"{BASE}/{second['id']}/withdraw")
    third = _create(client, term="third_one")
    assert third.status_code == 201 and third.json()["withdrawn_removed"] == 0
    assert client.get(f"{BASE}/{first['id']}").status_code == 404  # the oldest withdrawn went, at the second withdraw
    assert client.get(f"{BASE}/{second['id']}").status_code == 200
    assert client.get(f"{BASE}/{keep['id']}").json()["proposal"]["status"] == "pending"


def test_the_pending_limit_is_stated_as_shared_and_a_withdraw_frees_a_place(client, monkeypatch):
    monkeypatch.setitem(sp.LIMITS, "max_pending", 1)
    first = _create(client, term="one_term").json()["proposal"]
    full = _create(client, term="two_term")
    assert full.status_code == 429 and "everyone using this server" in full.json()["message"]
    client.post(f"{BASE}/{first['id']}/withdraw")
    assert _create(client, term="two_term").status_code == 201


# --- review fixes: input hygiene -------------------------------------------------------------


@pytest.mark.parametrize("char", ["‮", "​", "⁦", "﻿"])
def test_invisible_format_characters_are_refused_everywhere_text_is_taken(client, char):
    for field, overrides in (
        ("term", {"term": f"abc{char}def"}),
        ("description", {"description": f"A perfectly ordinary description{char} of the term."}),
        ("gate0.problem", {"gate0": {"problem": f"fine{char}text"}}),
    ):
        refused = _create(client, **overrides)
        assert refused.status_code == 422, (field, refused.text)
        assert any(e["field"] == field for e in refused.json()["errors"]), (field, refused.json())
    assert client.get(BASE).json()["total"] == 0


@pytest.mark.parametrize("term", ["a..b", "a/../b", "ab//cd", "a/.b", "x./y"])
def test_a_path_like_term_is_refused(client, term):
    refused = _create(client, term=term)
    assert refused.status_code == 422 and refused.json()["errors"][0]["code"] == "invalid_term"


def test_an_oversize_body_is_refused_before_it_is_parsed(client):
    big = json.dumps({**TERM_BODY, "description": "d" * (sp.LIMITS["max_body_bytes"] + 10)})
    declared = client.post(BASE, content=big, headers={"content-type": "application/json"})
    assert declared.status_code == 413 and declared.json()["error"] == "body_too_large"

    def chunks():
        for i in range(0, len(big), 4096):  # no Content-Length: counted as it arrives
            yield big[i : i + 4096].encode()

    undeclared = client.post(BASE, content=chunks(), headers={"content-type": "application/json"})
    assert undeclared.status_code == 413
    assert client.get(BASE).json()["total"] == 0
    # a normal body is untouched by the ceiling
    assert _create(client).status_code == 201
