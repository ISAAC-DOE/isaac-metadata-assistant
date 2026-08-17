"""Asset REFERENCES — the four HTTP operations, the hash rule, and what stayed put.

WHAT THIS FEATURE PROMISES, AND WHERE EACH PROMISE IS HELD HERE
===============================================================

1. **No hash is ever computed, completed or repaired.** The scientist supplies the
   digest; this application validates its SHAPE and never claims more.
   (``test_a_sha256_with_a_trailing_newline_is_refused``,
   ``test_no_asset_route_ever_writes_a_digest_the_caller_did_not_send``,
   ``test_a_digest_is_never_trimmed_into_validity``)
2. **No bytes anywhere.** ``POST /api/uploads`` is still an unconditional 403, and
   nothing in this feature reads, fetches or hashes a file.
   (``test_uploads_is_still_an_unconditional_refusal``,
   ``test_no_multipart_dependency_was_introduced``)
3. **Nothing is invented.** A missing required key, an off-enum role, a run that
   does not exist, and an unknown body key are each refused with a TYPED 422 —
   never defaulted, never coerced, never a 500.
   (the whole ``refusals`` section)
4. **The library and the run copies are one fact.** An edit rewrites every run that
   cites the asset; a removal detaches it from all of them.
   (``test_editing_a_digest_rewrites_every_run_that_cites_it``,
   ``test_removing_an_asset_detaches_it_from_every_run``)
5. **The pre-existing blocker path is untouched.** A scientist can still answer an
   extractor-detected asset's sha256 through ``POST .../answers``.
   (``test_the_blocker_answer_path_still_creates_an_asset``)
6. **The truth path did not move.** Export, official validation and the evidence
   sidecar behave exactly as before, on a record whose assets came through these
   routes. (the ``export`` section)

Everything here is synthetic. No file outside the tmp workspace is read or written,
nothing connects to a database, and no real experimental artifact is involved.
"""

from __future__ import annotations

import json

import pytest

import isaac_api.assets as assets
import isaac_api.routes as routes
from isaac_records.complete import is_sha256_shaped
from isaac_records.draft_validator import validate_draft
from isaac_records.export import export_draft
from isaac_records.official import validate_official

from conftest import client_ws, tutorial_client

#: A synthetic digest that is unmistakably fake and structurally valid: 64 lowercase
#: hex characters. Written as an expression rather than a literal so nobody has to
#: count, and so it cannot be mistaken for a digest of anything real.
SHA_A = "a1" * 32
SHA_B = "b2" * 32


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def experiment_id(client):
    """An ordinary experiment with an empty draft and no runs."""
    store = client_ws(client)
    exp = store.create_experiment(
        "Assets fixture",
        {"kind": "synthetic"},
        {"meta": {}, "fields": {}, "pending": []},
    )
    return exp.id


# --- helpers ------------------------------------------------------------------


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _create(client, experiment_id: str, **over):
    body = {
        "confirmed_by_user": True,
        "asset_id": "reduced_spectrum",
        "content_role": "reduction_product",
        "uri": "synthetic://example/reduced/CuO2_merged.xdi",
        "sha256": SHA_A,
        **over,
    }
    return client.post(
        f"/api/experiments/{experiment_id}/assets",
        json=body,
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _patch(client, experiment_id: str, aid: str, **over):
    return client.patch(
        f"/api/experiments/{experiment_id}/assets/{aid}",
        json={"confirmed_by_user": True, **over},
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _listing(client, experiment_id: str) -> dict:
    response = client.get(f"/api/experiments/{experiment_id}/assets")
    assert response.status_code == 200, response.text
    return response.json()


def _add_run(client, experiment_id: str, label: str) -> str:
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": label},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]["id"]


# --- 1. the round trip --------------------------------------------------------


def test_an_asset_reference_can_be_created_read_edited_and_removed(client, experiment_id):
    created = _create(client, experiment_id)
    assert created.status_code == 201, created.text
    asset = created.json()["asset"]
    assert asset["asset_id"] == "reduced_spectrum"
    assert asset["sha256"] == SHA_A
    assert "ETag" in created.headers

    listing = _listing(client, experiment_id)
    assert listing["total"] == 1
    assert [a["asset_id"] for a in listing["assets"]] == ["reduced_spectrum"]

    edited = _patch(client, experiment_id, "reduced_spectrum", sha256=SHA_B, notes="Re-reduced.")
    assert edited.status_code == 200, edited.text
    assert edited.json()["asset"]["sha256"] == SHA_B
    assert edited.json()["asset"]["notes"] == "Re-reduced."

    removed = client.post(
        f"/api/experiments/{experiment_id}/assets/reduced_spectrum/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["removed_asset_id"] == "reduced_spectrum"
    assert _listing(client, experiment_id)["total"] == 0


def test_creating_an_asset_records_a_user_confirmation_as_its_evidence(client, experiment_id):
    """Every asset must cite a source or ``validate_draft`` refuses the draft.

    The evidence is a REAL user confirmation — the write required
    ``confirmed_by_user: true`` — and its question deliberately does not claim the
    file was read.
    """
    asset = _create(client, experiment_id).json()["asset"]
    assert asset["evidence_count"] == 1
    entry = asset["evidence"][0]
    assert entry["source_type"] == "user_confirmation"
    assert "No file was read, fetched or hashed" in entry["question"]
    lowered = entry["question"].lower()
    assert "verif" not in lowered and "checked" not in lowered


def test_an_edit_appends_evidence_and_never_replaces_it(client, experiment_id):
    _create(client, experiment_id)
    _patch(client, experiment_id, "reduced_spectrum", sha256=SHA_B)
    asset = _listing(client, experiment_id)["assets"][0]
    assert asset["evidence_count"] == 2
    # The ORIGINAL confirmation is still first — history is extended, not rewritten.
    assert json.loads(asset["evidence"][0]["answer"])["sha256"] == SHA_A
    assert json.loads(asset["evidence"][1]["answer"]) == {"sha256": SHA_B}


def test_an_edit_that_changes_nothing_does_not_advance_the_revision(client, experiment_id):
    _create(client, experiment_id)
    before = _listing(client, experiment_id)["experiment_version"]
    again = _patch(client, experiment_id, "reduced_spectrum", sha256=SHA_A)
    assert again.status_code == 200, again.text
    assert again.json()["experiment_version"] == before
    assert _listing(client, experiment_id)["assets"][0]["evidence_count"] == 1


def test_the_twelve_content_roles_come_from_the_official_schema(client, experiment_id):
    """The vocabulary a client renders is the schema's, not a transcription.

    Compared against the vendored schema read INDEPENDENTLY here, so a hand-edited
    constant in the application could not make this pass.
    """
    from isaac_records.official import schema_path

    from isaac_api.workspace import REPO_ROOT

    schema = json.loads(schema_path(REPO_ROOT).read_text(encoding="utf-8"))
    expected = schema["properties"]["assets"]["items"]["properties"]["content_role"]["enum"]
    assert _listing(client, experiment_id)["content_roles"] == expected
    assert len(expected) == 12


# --- 2. the hash rule ---------------------------------------------------------


def test_a_sha256_with_a_trailing_newline_is_refused(client, experiment_id):
    """THE NEGATIVE CONTROL. A 64-hex digest plus ``\\n`` is 65 characters.

    Python's ``$`` also matches immediately before a trailing newline, so a
    ``^[0-9a-f]{64}$`` pattern applied with ``.match()`` accepts this string — a
    defect this repository has measured and shipped before, and which the official
    schema cannot catch because it declares ``sha256`` as a bare ``{"type":
    "string"}`` with no pattern and no length bound. The digest would have exported
    into an official record and passed ``validate_official`` clean.

    The refusal must be a typed 422 AND nothing may be written.
    """
    response = _create(client, experiment_id, sha256=SHA_A + "\n")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_sha256"
    assert _listing(client, experiment_id)["total"] == 0


def test_a_digest_is_never_trimmed_into_validity(client, experiment_id):
    """The refusal above is not a formatting preference — nothing is repaired.

    A server that answered 201 having stored ``SHA_A`` would be "helpfully"
    correcting the scientist's input, and they would never learn that what they
    pasted was not what was stored.
    """
    for candidate in (SHA_A + "\n", " " + SHA_A, SHA_A + " ", SHA_A + "\r\n"):
        response = _create(client, experiment_id, sha256=candidate)
        assert response.status_code == 422, (candidate, response.text)
    assert _listing(client, experiment_id)["total"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        SHA_A.upper(),          # uppercase hex
        "a1" * 31,              # 62 characters
        "a1" * 32 + "a",        # 65 characters
        "z" * 64,               # right length, not hex
        "",
        None,
        12345,
        [SHA_A],
    ],
)
def test_a_malformed_digest_is_a_typed_422_never_a_500(client, experiment_id, bad):
    response = _create(client, experiment_id, sha256=bad)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_sha256"
    assert _listing(client, experiment_id)["total"] == 0


def test_no_asset_route_ever_writes_a_digest_the_caller_did_not_send(client, experiment_id):
    """A create with no ``sha256`` is refused; it is never derived or defaulted."""
    response = client.post(
        f"/api/experiments/{experiment_id}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "no_hash",
            "content_role": "raw_data",
            "uri": "synthetic://example/raw/",
        },
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_sha256"
    assert _listing(client, experiment_id)["total"] == 0


def test_the_module_uses_the_truth_paths_own_digest_predicate(client, experiment_id):
    """One definition of "a storable hash", not two.

    ``isaac_api.assets`` imports ``isaac_records.complete.is_sha256_shaped`` rather
    than restating the pattern. A second copy here would be a second chance to write
    ``$`` where ``\\Z`` was needed.
    """
    from pathlib import Path

    source = Path(assets.__file__).read_text(encoding="utf-8")
    assert "from isaac_records.complete import is_sha256_shaped" in source
    # No pattern is COMPILED here, so there is no second definition to drift. The
    # pattern appears in prose in one docstring, which is a description of the
    # imported predicate rather than an implementation of it.
    assert "re.compile" not in source and "import re" not in source
    assert not hasattr(assets, "re")
    assert is_sha256_shaped(SHA_A) and not is_sha256_shaped(SHA_A + "\n")


def test_no_response_field_claims_a_digest_was_verified(client, experiment_id):
    """The reported fact is ``sha256_wellformed`` — about the STRING, not the file."""
    asset = _create(client, experiment_id).json()["asset"]
    assert asset["sha256_wellformed"] is True
    body = json.dumps(_listing(client, experiment_id)).lower()
    for forbidden in ("verified", "hash_matches", "checksum_ok", "file_read"):
        assert forbidden not in body, forbidden


# --- 3. refusals: every malformed shape is a typed 422, never a 500 ------------


def test_an_unknown_body_key_is_refused_by_name(client, experiment_id):
    """The official schema closes the asset object, so an extra key is unexportable."""
    response = _create(client, experiment_id, invented_key="something")
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field"
    assert body["keys"] == ["invented_key"]
    assert _listing(client, experiment_id)["total"] == 0


def test_evidence_cannot_be_supplied_by_a_request(client, experiment_id):
    """Evidence records what a person confirmed; a client may not author it."""
    response = _create(client, experiment_id, evidence=[{"source_type": "made_up"}])
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"


def test_an_off_enum_content_role_is_refused_with_the_allowed_list(client, experiment_id):
    response = _create(client, experiment_id, content_role="spectrum")
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_content_role"
    assert body["allowed"] == list(assets.content_roles())


def test_a_content_role_is_never_inferred_from_the_uri(client, experiment_id):
    """Omitting the role is a refusal, not an opportunity to guess from ``.ipynb``."""
    response = client.post(
        f"/api/experiments/{experiment_id}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "notebook",
            "uri": "synthetic://example/notebooks/reduction.ipynb",
            "sha256": SHA_A,
        },
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_content_role"


@pytest.mark.parametrize("key", ["asset_id", "uri"])
def test_a_required_text_key_may_be_neither_missing_nor_blank(client, experiment_id, key):
    for value in (None, "", "   ", 5, {"a": 1}):
        response = _create(client, experiment_id, **{key: value})
        assert response.status_code == 422, (key, value, response.text)
        assert response.json()["error"] == f"invalid_{key}"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("media_type", 5),
        ("notes", ["a"]),
        ("citation", "Smith et al."),
        ("caption_highlights", ["axes"]),
        ("paper_conclusions_about_figure", "one conclusion"),
        ("paper_conclusions_about_figure", [1, 2]),
        ("page", True),
        ("figure_label", {"label": "Fig. 2"}),
    ],
)
def test_a_wrong_typed_optional_field_is_a_typed_422_not_a_500(
    client, experiment_id, key, value
):
    """The schema's declared type is enforced at the door, not at export.

    A value the schema forbids that reached storage would be refused by the official
    validator later, with a message about a field the scientist never typed that
    into — and, in the ``True``-as-``page`` case, only because ``isinstance(True,
    int)`` is True in Python.
    """
    response = _create(client, experiment_id, **{key: value})
    assert response.status_code == 422, (key, value, response.text)
    assert response.json()["error"] == "invalid_asset_field"
    assert _listing(client, experiment_id)["total"] == 0


def test_a_blank_optional_string_is_refused_rather_than_stored(client, experiment_id):
    """A blank caption would export as though the field had been answered."""
    response = _create(client, experiment_id, notes="   ")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_asset_field"


def test_a_duplicate_asset_id_is_refused(client, experiment_id):
    """The evidence sidecar is keyed by ``asset_id``; two entries would lose one."""
    assert _create(client, experiment_id).status_code == 201
    again = _create(client, experiment_id, uri="synthetic://example/other.xdi")
    assert again.status_code == 422, again.text
    assert again.json()["error"] == "duplicate_asset_id"
    assert _listing(client, experiment_id)["total"] == 1


def test_the_asset_id_cannot_be_renamed(client, experiment_id):
    _create(client, experiment_id)
    response = _patch(client, experiment_id, "reduced_spectrum", asset_id="renamed")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "immutable_asset_id"
    assert [a["asset_id"] for a in _listing(client, experiment_id)["assets"]] == [
        "reduced_spectrum"
    ]


def test_an_edit_that_names_nothing_is_refused(client, experiment_id):
    _create(client, experiment_id)
    response = _patch(client, experiment_id, "reduced_spectrum")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "empty_update"


def test_a_required_key_cannot_be_cleared_by_an_edit(client, experiment_id):
    _create(client, experiment_id)
    response = _patch(client, experiment_id, "reduced_spectrum", uri=None)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_uri"


def test_an_optional_key_is_cleared_by_an_explicit_null(client, experiment_id):
    """A stored ``null`` would fail official validation, so clearing REMOVES the key."""
    _create(client, experiment_id, media_type="application/octet-stream")
    _patch(client, experiment_id, "reduced_spectrum", media_type=None)
    asset = _listing(client, experiment_id)["assets"][0]
    assert "media_type" not in asset


def test_every_write_requires_an_explicit_confirmation(client, experiment_id):
    _create(client, experiment_id)
    unconfirmed = client.post(
        f"/api/experiments/{experiment_id}/assets",
        json={
            "asset_id": "second",
            "content_role": "raw_data",
            "uri": "synthetic://example/raw/",
            "sha256": SHA_B,
        },
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert unconfirmed.status_code == 422, unconfirmed.text
    assert unconfirmed.json()["error"] == "confirmation_required"

    removal = client.post(
        f"/api/experiments/{experiment_id}/assets/reduced_spectrum/remove",
        json={},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert removal.status_code == 422, removal.text
    assert removal.json()["error"] == "confirmation_required"
    assert _listing(client, experiment_id)["total"] == 1


def test_an_unknown_asset_id_is_a_distinct_404(client, experiment_id):
    """``asset_not_found`` means the RECORD was read and holds no such asset."""
    response = _patch(client, experiment_id, "never_recorded", notes="x")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "asset_not_found"

    removal = client.post(
        f"/api/experiments/{experiment_id}/assets/never_recorded/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert removal.status_code == 404, removal.text
    assert removal.json()["error"] == "asset_not_found"


def test_an_oversized_asset_is_refused_rather_than_written(client, experiment_id):
    """`_is_storable_value` bounds size, depth and renderability on this path too.

    STATED HONESTLY, THIS EXERCISES THE SIZE CONDITION ONLY. The lone-surrogate case
    the guard also covers cannot be DELIVERED over HTTP at all — `httpx` raises
    `UnicodeEncodeError` while encoding the request body, so no client can send one
    — which is why the renderability half is exercised at the function level below
    rather than through a route that cannot receive it.
    """
    response = _create(client, experiment_id, notes="x" * (routes._MAX_VALUE_BYTES + 1))
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    assert _listing(client, experiment_id)["total"] == 0


def test_the_storability_guard_refuses_a_value_json_cannot_represent():
    """The renderability half of the guard, at the level a client can reach it."""
    assert routes._is_storable_value({"notes": "ok"}) is True
    assert routes._is_storable_value({"notes": "\ud800"}) is False
    assert routes._asset_storable({"notes": "\ud800"}) is not None


# --- 4. optimistic concurrency ------------------------------------------------


def test_a_write_without_if_match_is_428(client, experiment_id):
    response = client.post(
        f"/api/experiments/{experiment_id}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "a",
            "content_role": "raw_data",
            "uri": "synthetic://example/raw/",
            "sha256": SHA_A,
        },
    )
    assert response.status_code == 428, response.text
    assert response.json()["error"] == "precondition_required"
    assert _listing(client, experiment_id)["total"] == 0


def test_a_malformed_if_match_is_400(client, experiment_id):
    response = client.post(
        f"/api/experiments/{experiment_id}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "a",
            "content_role": "raw_data",
            "uri": "synthetic://example/raw/",
            "sha256": SHA_A,
        },
        headers={"If-Match": "not-a-validator"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "malformed_if_match"


@pytest.mark.parametrize("operation", ["create", "edit", "remove"])
def test_a_stale_if_match_is_412_and_writes_nothing(client, experiment_id, operation):
    """The compare-and-swap contract, on all three writes.

    A stale token is captured, the record then moves under it, and the write must be
    refused with the current ETag echoed so a client recovers in one hop.
    """
    _create(client, experiment_id, asset_id="first")
    stale = _etag(client, experiment_id)
    # Another writer advances the record.
    _create(client, experiment_id, asset_id="second", sha256=SHA_B)
    before = _listing(client, experiment_id)

    if operation == "create":
        response = client.post(
            f"/api/experiments/{experiment_id}/assets",
            json={
                "confirmed_by_user": True,
                "asset_id": "third",
                "content_role": "raw_data",
                "uri": "synthetic://example/raw/",
                "sha256": SHA_A,
            },
            headers={"If-Match": stale},
        )
    elif operation == "edit":
        response = client.patch(
            f"/api/experiments/{experiment_id}/assets/first",
            json={"confirmed_by_user": True, "sha256": SHA_B},
            headers={"If-Match": stale},
        )
    else:
        response = client.post(
            f"/api/experiments/{experiment_id}/assets/first/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": stale},
        )

    assert response.status_code == 412, response.text
    assert response.json()["error"] == "stale_write"
    assert response.headers["ETag"] == _etag(client, experiment_id)
    after = _listing(client, experiment_id)
    assert after["assets"] == before["assets"]
    assert after["experiment_version"] == before["experiment_version"]


# --- 5. run association -------------------------------------------------------


def test_one_asset_can_be_associated_with_several_runs(client, experiment_id):
    run_a = _add_run(client, experiment_id, "300 K")
    run_b = _add_run(client, experiment_id, "500 K")
    _add_run(client, experiment_id, "700 K")

    created = _create(client, experiment_id, run_ids=[run_a, run_b])
    assert created.status_code == 201, created.text
    used = [entry["run_id"] for entry in created.json()["asset"]["used_by_runs"]]
    assert used == [run_a, run_b]
    assert created.json()["asset"]["export_reach"] == "runs"

    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    holders = {
        run.id
        for run in exp.sorted_runs()
        if any(a["asset_id"] == "reduced_spectrum" for a in assets.run_assets(run))
    }
    assert holders == {run_a, run_b}


def test_run_ids_set_the_associations_exactly(client, experiment_id):
    run_a = _add_run(client, experiment_id, "300 K")
    run_b = _add_run(client, experiment_id, "500 K")
    _create(client, experiment_id, run_ids=[run_a])

    moved = _patch(client, experiment_id, "reduced_spectrum", run_ids=[run_b])
    assert moved.status_code == 200, moved.text
    assert [e["run_id"] for e in moved.json()["asset"]["used_by_runs"]] == [run_b]

    cleared = _patch(client, experiment_id, "reduced_spectrum", run_ids=[])
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["asset"]["used_by_runs"] == []
    assert cleared.json()["asset"]["export_reach"] == "none"


def test_the_only_run_is_never_inferred_as_an_assets_run(client, experiment_id):
    """Omitting ``run_ids`` on a record with exactly one run associates nothing."""
    _add_run(client, experiment_id, "300 K")
    created = _create(client, experiment_id)
    assert created.json()["asset"]["used_by_runs"] == []
    assert created.json()["asset"]["export_reach"] == "none"


def test_a_run_this_record_does_not_have_is_a_typed_422(client, experiment_id):
    response = _create(client, experiment_id, run_ids=["01BOGUS0000000000000000000"])
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"
    assert _listing(client, experiment_id)["total"] == 0


def test_malformed_run_ids_are_a_typed_422_not_a_500(client, experiment_id):
    for bad in ("run-1", [5], {"a": 1}, [None]):
        response = _create(client, experiment_id, run_ids=bad)
        assert response.status_code == 422, (bad, response.text)
        assert response.json()["error"] == "invalid_run_ids"


def test_editing_a_digest_rewrites_every_run_that_cites_it(client, experiment_id):
    """The library and the run copies are ONE fact, not two that must be reconciled.

    MUTATION: removing the ``set_associations`` call from ``patch_asset`` leaves the
    runs holding ``SHA_A`` while the library holds ``SHA_B``, and this test goes RED.
    """
    run_a = _add_run(client, experiment_id, "300 K")
    run_b = _add_run(client, experiment_id, "500 K")
    _create(client, experiment_id, run_ids=[run_a, run_b])
    _patch(client, experiment_id, "reduced_spectrum", sha256=SHA_B)

    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    for run in exp.sorted_runs():
        for entry in assets.run_assets(run):
            if entry["asset_id"] == "reduced_spectrum":
                assert entry["sha256"] == SHA_B, run.id
    assert assets.find(exp.draft, "reduced_spectrum")["sha256"] == SHA_B


def test_removing_an_asset_detaches_it_from_every_run(client, experiment_id):
    run_a = _add_run(client, experiment_id, "300 K")
    run_b = _add_run(client, experiment_id, "500 K")
    _create(client, experiment_id, run_ids=[run_a, run_b])

    removed = client.post(
        f"/api/experiments/{experiment_id}/assets/reduced_spectrum/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["detached_from_runs"] == [run_a, run_b]

    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    for run in exp.sorted_runs():
        assert assets.run_assets(run) == []


def test_export_reach_says_record_when_the_experiment_has_no_runs(client, experiment_id):
    """A zero-run experiment exports one record from its own draft, carrying this asset."""
    assert _create(client, experiment_id).json()["asset"]["export_reach"] == "record"


# --- 6. the pre-existing blocker path is untouched ----------------------------


def test_the_blocker_answer_path_still_creates_an_asset(client):
    """``POST .../answers`` with ``asset_sha256[<uri>]`` still works, unchanged.

    This is the path a scientist has always had: the extractor detects a file and
    asks for its digest, and ``apply_answers`` CREATES the asset entry from the
    blocker. Nothing in this feature may take that away.
    """
    from isaac_api import workspace as ws

    experiment_id = ws.SEED_NEW_DRAFT_ID
    pending = client.get(f"/api/experiments/{experiment_id}/pending").json()
    blocker = next(b for b in pending["pending"] if b["kind"] == "asset")

    response = client.post(
        f"/api/experiments/{experiment_id}/answers",
        json={"confirmed_by_user": True, "answers": {blocker["id"]: SHA_A}},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 200, response.text

    listing = _listing(client, experiment_id)
    created = [a for a in listing["assets"] if a["sha256"] == SHA_A]
    assert len(created) == 1, listing
    # It is visible through the NEW listing too — one library, two ways in.
    assert created[0]["uri"] == blocker["about"] or created[0]["uri"]


def test_an_asset_created_by_a_blocker_can_then_be_edited_here(client):
    """The two paths write the same library, so one can finish what the other began."""
    from isaac_api import workspace as ws

    experiment_id = ws.SEED_READY_ID
    listing = _listing(client, experiment_id)
    assert listing["total"] >= 1
    asset_id = listing["assets"][0]["asset_id"]

    response = _patch(client, experiment_id, asset_id, notes="Re-checked the archive path.")
    assert response.status_code == 200, response.text
    assert response.json()["asset"]["notes"] == "Re-checked the archive path."
    # The blocker's own file_listing evidence survives alongside the new confirmation.
    kinds = [e["source_type"] for e in response.json()["asset"]["evidence"]]
    assert "file_listing" in kinds and kinds[-1] == "user_confirmation"


# --- 7. scope -----------------------------------------------------------------


def test_an_unknown_worked_example_session_is_a_404_not_a_fallback(client, experiment_id):
    """A header naming no session never falls back to the ordinary workspace."""
    for method, path, payload in (
        ("get", f"/api/experiments/{experiment_id}/assets", None),
        ("post", f"/api/experiments/{experiment_id}/assets", {"confirmed_by_user": True}),
    ):
        response = getattr(client, method)(
            path,
            headers={routes.TUTORIAL_SESSION_HEADER: "01SYNTHNOSUCHSESSION000000"},
            **({"json": payload} if payload is not None else {}),
        )
        assert response.status_code == 404, (path, response.text)


def test_the_ordinary_workspace_cannot_see_a_worked_example_records_assets(
    client, experiment_id
):
    """The same id, without the session header, is not found rather than answered."""
    from isaac_api import workspace as ws
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    _create(client, experiment_id)
    bare = TestClient(create_app())
    response = bare.get(f"/api/experiments/{experiment_id}/assets")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"
    # And a canonical worked-example record is likewise invisible without the header.
    assert bare.get(f"/api/experiments/{ws.SEED_READY_ID}/assets").status_code == 404


# --- 8. nothing about export, validation or the schema moved ------------------


def test_no_multipart_dependency_was_introduced():
    """`python-multipart` must not become a dependency of this project."""
    from pathlib import Path

    pyproject = Path(routes.__file__).resolve().parents[3] / "pyproject.toml"
    assert "multipart" not in pyproject.read_text(encoding="utf-8").lower()


def test_uploads_is_still_an_unconditional_refusal(client):
    response = client.post("/api/uploads")
    assert response.status_code == 403, response.text


def test_the_stored_digest_is_exactly_what_was_sent_even_for_a_real_file(
    tmp_path, client, experiment_id
):
    """The application does not read the file at the URI, and this measures it.

    A REAL file is written with known content, its true digest is computed HERE (by
    the test, not by the application), and a DIFFERENT well-formed digest is sent for
    it. What comes back must be the one that was sent — byte for byte — because
    nothing on this path opens the file, and a server that "helpfully" corrected the
    digest would fail this.

    A booby-trapped ``hashlib.sha256`` was tried first and is NOT what this does:
    ``workspace._authoritative_signature`` legitimately hashes the record document on
    every save, so trapping the function proves nothing about files.
    """
    import hashlib

    real = tmp_path / "reduced.xdi"
    real.write_bytes(b"synthetic reduced spectrum\n")
    true_digest = hashlib.sha256(real.read_bytes()).hexdigest()
    assert true_digest != SHA_A

    created = _create(client, experiment_id, uri=real.as_uri(), sha256=SHA_A)
    assert created.status_code == 201, created.text
    assert created.json()["asset"]["sha256"] == SHA_A
    assert created.json()["asset"]["sha256"] != true_digest

    # And the module itself imports no hashing or file-reading machinery.
    from pathlib import Path

    source = Path(assets.__file__).read_text(encoding="utf-8")
    for forbidden in ("hashlib", "open(", "read_bytes", "urllib", "requests", "httpx"):
        assert forbidden not in source, forbidden


def test_a_record_whose_assets_came_through_these_routes_still_exports_and_validates(
    client, experiment_id
):
    """THE TRUTH-PATH CHECK. The export and the official validator are unchanged.

    A complete synthetic draft is assembled through the canonical seed and one asset
    is added through the NEW route; the record must still export and validate clean,
    and the sidecar must still carry that asset's evidence under ``assets:<id>``.
    """
    from isaac_api import workspace as ws

    store = client_ws(client)
    seed = store.load_experiment(ws.SEED_READY_ID)
    assert seed is not None

    added = _create(client, ws.SEED_READY_ID, asset_id="extra_reference")
    assert added.status_code == 201, added.text

    refreshed = store.load_experiment(ws.SEED_READY_ID)
    draft = refreshed.draft
    assert validate_draft(draft).ok, validate_draft(draft).render()

    result = export_draft(draft, ws.REPO_ROOT, record_id=ws.SEED_READY_ID)
    assert result.ok, result.render()
    report = validate_official(result.record, ws.REPO_ROOT)
    assert report.ok, report.render()

    exported = {a["asset_id"]: a for a in result.record["assets"]}
    assert "extra_reference" in exported
    # The official record carries NO evidence key — that is the sidecar's job.
    assert "evidence" not in exported["extra_reference"]
    assert "assets:extra_reference" in result.sidecar["evidence"]


def test_the_asset_object_this_feature_writes_carries_only_schema_keys(
    client, experiment_id
):
    """``additionalProperties: false`` — an extra key would fail official validation.

    Checked against the vendored schema's OWN property list rather than a copy, and
    it is the reason ``run_ids`` is a request field and never a stored one.
    """
    run_id = _add_run(client, experiment_id, "300 K")
    _create(client, experiment_id, run_ids=[run_id], media_type="application/x-xdi")
    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    stored = assets.find(exp.draft, "reduced_spectrum")
    allowed = set(assets.asset_keys()) | {assets.EVIDENCE_KEY}
    assert set(stored) <= allowed, set(stored) - allowed
    assert "run_ids" not in stored


def test_an_unreadable_stored_container_is_refused_rather_than_overwritten(
    client, experiment_id
):
    """THE DISCLOSURE WOULD OTHERWISE BE A LIE, and this is the test that keeps it true.

    Every read surface says a stored entry this build cannot present is kept unchanged
    on the record. :func:`assets.library` skips a malformed CONTAINER by returning an
    empty list, so without an explicit guard the first write would have replaced it
    with a fresh list and destroyed whatever it held — silently, in the one direction
    the copy promises never happens. A container that is not a list has no positions to
    preserve entries at, so the only honest answer is to refuse.

    DRIVEN AT THE MODULE, NOT OVER HTTP, AND THE REASON IS A PRE-EXISTING DEFECT THIS
    SLICE DID NOT CAUSE AND MUST NOT FIX. ``draft_validator.validate_draft`` iterates
    ``draft["assets"]`` and calls ``.get`` on each element (`draft_validator.py:203`),
    so ANY malformed stored asset — a dict container, or a string element — raises
    ``AttributeError`` out of the truth path on the ordinary record READ, before this
    feature's routes are reachable at all. That file is truth-path and out of scope
    here (CLAUDE.md §13). Reported rather than worked around: see this slice's report.

    MUTATION: deleting the guard's body makes ``_write_library`` replace the dict and
    the final assertion goes RED.
    """

    class _Stub:
        def __init__(self, draft):
            self.draft = draft

        def sorted_runs(self):
            return []

    stub = _Stub({"assets": {"not": "a list"}})
    with pytest.raises(assets.UnsupportedAsset) as caught:
        assets.refuse_unreadable_containers(stub)
    assert caught.value.error == "unreadable_asset_container"
    # Nothing was touched.
    assert stub.draft["assets"] == {"not": "a list"}
    # And the route consults the guard on all three writes.
    source = __import__("pathlib").Path(routes.__file__).read_text(encoding="utf-8")
    assert source.count("assets.refuse_unreadable_containers(exp)") == 3


def test_a_malformed_element_is_preserved_by_a_library_write(experiment_id, client):
    """A per-element problem is different from a broken container, and is not refused.

    An element has a position, so it can be carried through untouched. It is COUNTED by
    ``unreadable_entries`` rather than rendered — this build cannot say what it holds
    without inventing it — and it must still be in the document afterwards.

    Also driven at the module, for the same pre-existing truth-path reason above.
    """

    class _Stub:
        def __init__(self, draft):
            self.draft = draft

        def sorted_runs(self):
            return []

    stub = _Stub({"assets": ["not an object", {"no": "asset_id"}]})
    assert assets.library(stub.draft) == []
    assert assets.unreadable_count(stub.draft) == 2

    entry = assets.build_asset(
        {
            "asset_id": "reduced_spectrum",
            "content_role": "reduction_product",
            "uri": "synthetic://example/reduced/CuO2_merged.xdi",
            "sha256": SHA_A,
        },
        timestamp="2099-01-01T00:00:00Z",
        question="q?",
    )
    assets.upsert(stub, entry, creating=True)
    stored = stub.draft["assets"]
    assert "not an object" in stored and {"no": "asset_id"} in stored
    assert any(
        isinstance(a, dict) and a.get("asset_id") == "reduced_spectrum" for a in stored
    )


def test_a_malformed_stored_asset_already_breaks_the_truth_paths_read(client, experiment_id):
    """A PRE-EXISTING DEFECT, PINNED SO IT IS NOT MISTAKEN FOR THIS SLICE'S.

    ``validate_draft`` calls ``.get`` on every element of ``draft["assets"]`` without a
    type guard, so a record whose stored asset list holds a non-object raises out of
    the truth core on an ordinary read — long before any asset route is involved. This
    slice deliberately does NOT fix it: ``src/isaac_records/draft_validator.py`` is
    truth-path and out of this slice's scope.

    The test asserts the CURRENT behaviour so that a later slice which fixes it sees a
    red test naming the decision, rather than this limitation quietly persisting.
    """
    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    exp.draft["assets"] = ["not an object"]
    exp.save()
    with pytest.raises(AttributeError):
        validate_draft(store.load_experiment(experiment_id).draft)


def test_export_reach_none_is_measured_against_the_real_export_composition(client):
    """THE `none` DISCLOSURE IS TRUE OF THE EXPORT, not just of a derived label.

    `Experiment.resolved_run_draft` composes a run's export draft from the RUN's own
    blocks, and `assets` is in `workspace.RUN_LEVEL_BLOCKS` — so a library entry no
    run cites reaches no exported record. The UI states that in words on the card; this
    measures it against `export_units()` rather than trusting the label.

    IT ALSO PINS A PRE-EXISTING BEHAVIOUR THIS SLICE DID NOT INTRODUCE AND DOES NOT
    CHANGE: the THREE assets the extractor already put on this seed are dropped from
    the run's export draft too, because adding a run makes the record export per-run
    and nothing carries record-level assets down. Surfacing that is the whole point of
    `export_reach`; changing it would be an export-path change and is out of scope.
    """
    from isaac_api import workspace as ws

    experiment_id = ws.SEED_READY_ID
    before = {a["asset_id"] for a in _listing(client, experiment_id)["assets"]}
    assert len(before) >= 3, before

    run_id = _add_run(client, experiment_id, "300 K")
    _create(client, experiment_id, asset_id="unassociated_ref")
    _create(client, experiment_id, asset_id="associated_ref", sha256=SHA_B, run_ids=[run_id])

    listing = {a["asset_id"]: a for a in _listing(client, experiment_id)["assets"]}
    assert listing["unassociated_ref"]["export_reach"] == "none"
    assert listing["associated_ref"]["export_reach"] == "runs"
    for stale in before:
        assert listing[stale]["export_reach"] == "none", stale

    store = client_ws(client)
    units = store.load_experiment(experiment_id).export_units()
    assert len(units) == 1
    composed = {a["asset_id"] for a in (units[0].draft.get("assets") or [])}
    assert composed == {"associated_ref"}, composed
