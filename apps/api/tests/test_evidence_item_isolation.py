"""ONE unreadable evidence item must degrade to ITSELF, never to the whole trail.

THE DEFECT, AS MEASURED ON ``77820bf`` (not as described in a ticket)
---------------------------------------------------------------------
Both trail builders in ``serialize`` read every stored evidence payload with no
shape check. Reproduced against a real exported seed record with 36 sidecar
entries, by replacing exactly ONE payload:

* ``{"system.facility.facility_name": 7}``      -> ``TypeError: 'int' object is
  not iterable`` propagating out of ``GET /experiments/{id}/evidence``. An
  unhandled 500 on a read; all 36 entries lost. In the browser that GET shares a
  ``Promise.all`` with four siblings inside ``getEvidenceBundle``, so the whole
  bundle rejected and the Evidence view rendered "Backend Not Running" — the app
  blaming the server for one field's stored evidence.
* ``{"…": {"source_type": "spreadsheet"}}`` and ``{"…": "spreadsheet"}`` did NOT
  raise; they were served verbatim, and the crash moved to the client (measured
  separately in ``apps/web/src/__tests__/evidence-item-isolation.test.tsx``,
  which recorded an EMPTY DOM for the whole screen).
* A draft ``fields`` envelope that was not a dict was silently ``continue``d —
  the field vanished from the trail with nothing said about it.

WHAT IS ASSERTED HERE
---------------------
1. N valid entries + 1 unreadable one -> N + 1 entries. The valid ones are
   byte-identical to what they were without the bad one (no collateral).
2. The unreadable one is PRESENT, keyed by its own sidecar key / field path /
   position, marked ``unavailable`` with a reason that names the actual shape.
3. Nothing is invented for it: no value, no citation, no source type, and a
   ``status`` that cannot be mistaken for support (``unavailable``).
4. A genuine BUNDLE-level failure still fails the whole read — an evidence block
   that is not a mapping raises rather than being reported as a partial success.
5. The pre-existing bundle-level tolerance is unchanged: an unparseable sidecar
   still degrades to the draft trail (``routes._read_artifact_json``).
6. NO CONSUMER of the trail turns "could not be read" into a claim about the
   record. The evidence-support classifier calls it ``unreadable``, never
   ``unknown``/"No defensible value."; the deterministic Assistant refuses the
   question instead of answering "has no cited source". Both of those were
   REGRESSIONS INTRODUCED BY THIS SLICE — making a previously-absent entry
   visible made two downstream surfaces confident about it — and both are
   pinned here rather than in the surfaces' own files, because it is this
   slice's ``unavailable`` flag they must read.
7. A DRAFT container (``implicit``/``assets``) that is not a list is a
   bundle-level failure like ``fields``/``evidence``, not N per-item ones.
   ``enumerate`` walked a dict's keys and a string's characters and invented a
   row per key/character; it now raises.

Truth core (``src/isaac_records/``) untouched. Every fixture is a committed
synthetic seed; nothing real is read.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from isaac_api import assistant_query as aq
from isaac_api import serialize

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# --- helpers (same shapes as test_api.py) -------------------------------------


def _seed_id(client: TestClient) -> str:
    experiments = client.get("/api/experiments").json()["experiments"]
    raw = [e for e in experiments if e["pending_count"] == 5]
    assert len(raw) == 1
    return raw[0]["id"]


def _if_match(client: TestClient, exp_id: str) -> dict:
    v = client.get(f"/api/experiments/{exp_id}").json()["version"]
    return {"If-Match": f'"{v}"'}


def _export_seed(client: TestClient) -> str:
    """Answer every blocker and export, so a REAL sidecar/record pair exists."""
    exp_id = _seed_id(client)
    pending = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    answers = {
        b["id"]: b["demo_answer"]["value"] for b in pending if b["demo_answer"] is not None
    }
    resp = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers=_if_match(client, exp_id),
    )
    assert resp.status_code == 200
    resp = client.post(f"/api/experiments/{exp_id}/export", headers=_if_match(client, exp_id))
    assert resp.status_code == 200 and resp.json()["ok"] is True, resp.text
    return exp_id


def _sidecar_path(client: TestClient, exp_id: str):
    exp = client_ws(client).load_experiment(exp_id)
    path = exp.sidecar_path()
    assert path is not None and path.exists()
    return path


def _by_path(entries: list[dict]) -> dict[str, dict]:
    return {e["path"]: e for e in entries}


# --- 1. the API contract: one bad item, N good ones ---------------------------


@pytest.mark.parametrize(
    ("payload", "reason_fragment"),
    [
        # The shape that used to 500 the whole endpoint.
        (7, "is a number, not a list of evidence entries"),
        (True, "is a boolean, not a list of evidence entries"),
        # The shapes that used to be served verbatim and crash the client.
        ({"source_type": "spreadsheet"}, "is an object, not a list of evidence entries"),
        ("spreadsheet", "is a string, not a list of evidence entries"),
        # Right container, wrong members.
        (["spreadsheet"], "1 of 1 stored evidence entries cannot be shown"),
    ],
)
def test_one_unreadable_sidecar_entry_leaves_every_other_entry_intact(
    client, payload, reason_fragment
):
    exp_id = _export_seed(client)
    path = _sidecar_path(client, exp_id)
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    keys = list(sidecar["evidence"])
    assert len(keys) > 1, "this fixture needs several entries for isolation to mean anything"
    victim = keys[0]

    # The trail as it reads with NOTHING corrupted — the baseline the fix must not move.
    healthy = _by_path(client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"])

    corrupt = copy.deepcopy(sidecar)
    corrupt["evidence"][victim] = payload
    path.write_text(json.dumps(corrupt), encoding="utf-8")

    resp = client.get(f"/api/experiments/{exp_id}/evidence")
    assert resp.status_code == 200, "one malformed item is not a server error"
    entries = _by_path(resp.json()["evidence"])

    # 1. NOTHING is dropped: the same key set, including the bad one.
    assert set(entries) == set(healthy)

    # 2. Every OTHER entry is byte-identical. This is the isolation claim, and it
    #    is asserted over the whole entry rather than a count, so a fix that
    #    quietly degraded its neighbours would fail here.
    for key in healthy:
        if key == victim:
            continue
        assert entries[key] == healthy[key], f"{key} was collateral damage"

    # 3. The failed entry is still visible, still identified by its own key.
    bad = entries[victim]
    assert bad["path"] == victim
    assert bad["unavailable"] is True
    assert reason_fragment in bad["unavailable_reason"]

    # 4. Nothing is invented in place of what failed, and the status cannot be
    #    read as support (CLAUDE.md §5: unavailable must read as unavailable).
    assert bad["evidence"] == []
    assert bad["status"] == serialize.UNAVAILABLE_STATUS == "unavailable"
    assert bad["status"] not in {"verified", "inferred"}


def test_a_partially_readable_entry_keeps_what_it_has_and_says_what_it_lost(client):
    """Half-readable is neither "fine" nor "gone" — both halves must be stated."""
    exp_id = _export_seed(client)
    path = _sidecar_path(client, exp_id)
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    victim = next(k for k, v in sidecar["evidence"].items() if isinstance(v, list) and v)
    good_entry = sidecar["evidence"][victim][0]

    sidecar["evidence"][victim] = [good_entry, "not an evidence object"]
    path.write_text(json.dumps(sidecar), encoding="utf-8")

    bad = _by_path(client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"])[victim]
    # The readable citation survives, verbatim.
    assert bad["evidence"] == [good_entry]
    # And the loss is disclosed rather than absorbed into a shorter list.
    assert bad["unavailable"] is True
    assert "1 of 2 stored evidence entries cannot be shown" in bad["unavailable_reason"]
    # The status describes exactly what IS on screen, so it is NOT forced to
    # `unavailable` here — there is readable support and it says so.
    assert bad["status"] == "verified"


def test_an_unknown_source_type_is_served_verbatim_and_is_not_an_error(client):
    """A source type this build does not enumerate is DATA, not a malformation.

    Pinned because the client-side fix for it (a fallback glyph) must not be
    mistaken for a licence to rewrite the stored string, and because the backend
    must not start calling an unfamiliar-but-well-formed citation "unavailable".
    """
    exp_id = _export_seed(client)
    path = _sidecar_path(client, exp_id)
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    victim = next(k for k, v in sidecar["evidence"].items() if isinstance(v, list) and v)
    sidecar["evidence"][victim] = [{"source_type": "instrument_log", "locator": "line 4"}]
    path.write_text(json.dumps(sidecar), encoding="utf-8")

    entry = _by_path(client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"])[victim]
    assert entry.get("unavailable") is None
    assert entry["evidence"] == [{"source_type": "instrument_log", "locator": "line 4"}]


# --- 2. the draft trail (pre-export, and the classification that reads it) -----


def _corrupt_draft(client, exp_id: str, mutate) -> None:
    ws = client_ws(client)
    exp = ws.load_experiment(exp_id)
    mutate(exp.draft)
    exp.save()


def test_one_unreadable_draft_envelope_does_not_shorten_the_trail(client):
    """The silent-drop case: a non-dict envelope used to VANISH from the trail."""
    exp_id = _seed_id(client)
    before = _by_path(client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"])
    victim = next(iter(before))

    _corrupt_draft(client, exp_id, lambda d: d["fields"].__setitem__(victim, 7))

    entries = _by_path(client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"])
    assert set(entries) == set(before), "the field must still be listed, not dropped"
    assert entries[victim]["unavailable"] is True
    assert "not an evidence envelope" in entries[victim]["unavailable_reason"]
    assert entries[victim]["value"] is None
    for key in before:
        if key != victim:
            assert entries[key] == before[key]


def test_an_unreadable_implicit_claim_is_named_by_its_position(client):
    """With no readable ``about`` there is no name to print — so print WHERE it is.

    The alternative (a `?` placeholder, or dropping it) would leave a scientist
    unable to find the offending item in their own document.
    """
    exp_id = _seed_id(client)
    _corrupt_draft(client, exp_id, lambda d: d.setdefault("implicit", []).append(7))

    entries = _by_path(client.get(f"/api/experiments/{exp_id}/evidence").json()["evidence"])
    key = next(k for k in entries if k.startswith("implicit:#"))
    assert entries[key]["unavailable"] is True
    assert "not an implicit claim" in entries[key]["unavailable_reason"]
    assert entries[key]["evidence"] == []


def test_evidence_classification_survives_an_unreadable_draft_payload(client):
    """The classifier reads the SAME trail, so it inherited the same 500.

    ``evidence_classify.classify_fields`` iterates ``entry["evidence"]``; with a
    non-iterable payload reaching it, ``GET /evidence-classification`` raised too.
    Normalising inside the trail builder fixes both from one place, and this
    pins that it stays fixed.

    STRENGTHENED after review. The first version of this test asserted ONLY
    ``status_code == 200`` and the count-sum invariant — i.e. it pinned
    NON-CRASH and nothing about what was said. It therefore passed while the row
    read ``classification: "unknown"`` / ``"No defensible value."``, a positive
    claim about a record nobody could read; the count-sum invariant is preserved
    below rather than dropped, so nothing here is weaker than it was.
    """
    exp_id = _seed_id(client)
    victim = None

    def corrupt(d):
        nonlocal victim
        victim = next(iter(d["fields"]))
        d["fields"][victim] = {"value": "x", "status": "verified", "evidence": 7}

    _corrupt_draft(client, exp_id, corrupt)

    resp = client.get(f"/api/experiments/{exp_id}/evidence-classification")
    assert resp.status_code == 200
    body = resp.json()
    # The original two assertions, unchanged.
    assert sum(body["counts"].values()) == len(body["field_results"])

    row = next(r for r in body["field_results"] if r["field"] == victim)
    assert row["classification"] == "unreadable", (
        "an entry that could not be READ is not an entry with no defensible value"
    )
    assert "No defensible value" not in row["explanation"]
    assert "could not be read" in row["explanation"]
    assert row["value_state"] == "unreadable"
    # …and the histogram must not quietly bucket it with the plainly-absent.
    assert body["counts"]["unreadable"] >= 1
    unknown_fields = [
        r["field"] for r in body["field_results"] if r["classification"] == "unknown"
    ]
    assert victim not in unknown_fields


def test_a_non_dict_draft_envelope_is_classified_unreadable_not_unknown(client):
    """The OTHER shape the review measured: ``{"fields": {"a.b": 7}}``.

    On base ``77820bf`` this field was silently absent from the classification
    (the trail builder ``continue``d it). On ``ba8e38e`` it arrived classified
    ``unknown`` / "No defensible value." So an OMISSION had become a positive
    false claim — the opposite direction from the 500 above, same wrong answer.
    """
    exp_id = _seed_id(client)
    victim = None

    def corrupt(d):
        nonlocal victim
        victim = next(iter(d["fields"]))
        d["fields"][victim] = 7

    _corrupt_draft(client, exp_id, corrupt)

    body = client.get(f"/api/experiments/{exp_id}/evidence-classification").json()
    row = next(r for r in body["field_results"] if r["field"] == victim)
    assert row["classification"] == "unreadable"
    assert "No defensible value" not in row["explanation"]
    # The reason names the SHAPE, and the classifier passes it through verbatim.
    assert "not an evidence envelope" in row["explanation"]


def test_a_partially_readable_entry_keeps_its_class_and_discloses_the_rest(client):
    """Partial readability is NOT reclassified — it is classified and disclosed.

    Reclassifying an entry with genuine observed evidence as ``unreadable`` would
    be its own false statement (the support IS there and IS readable). What must
    not happen is the explanation reading as if it described the whole entry.
    """
    exp_id = _seed_id(client)
    victim = None

    def corrupt(d):
        nonlocal victim
        victim = next(
            k for k, v in d["fields"].items() if isinstance(v, dict) and v.get("evidence")
        )
        d["fields"][victim]["evidence"] = list(d["fields"][victim]["evidence"]) + [7]

    _corrupt_draft(client, exp_id, corrupt)

    body = client.get(f"/api/experiments/{exp_id}/evidence-classification").json()
    row = next(r for r in body["field_results"] if r["field"] == victim)
    assert row["classification"] != "unreadable", "readable support is still support"
    assert "could not be read" in row["explanation"], (
        "the class describes only the readable part, so the rest must be said"
    )


def test_the_classification_explanation_never_quotes_the_stored_value(client):
    """The pass-through reason must stay a statement about SHAPE, not content."""
    exp_id = _seed_id(client)

    _corrupt_draft(
        client,
        exp_id,
        lambda d: d["fields"].__setitem__(
            next(iter(d["fields"])),
            {"value": "x", "status": "verified", "evidence": "SECRET-LOOKING-STRING"},
        ),
    )

    text = client.get(f"/api/experiments/{exp_id}/evidence-classification").text
    assert "SECRET-LOOKING-STRING" not in text


# --- 2b. a BUNDLE-level container failure in a DRAFT --------------------------


@pytest.mark.parametrize(
    "key, container",
    [
        # The two shapes the review measured fabricating rows on `ba8e38e`:
        # a dict enumerated its KEYS (2 rows, "position 0"/"position 1"), and a
        # string enumerated its CHARACTERS (3 rows for "abc").
        ("implicit", {"x": 1, "y": 2}),
        ("implicit", "abc"),
        ("implicit", 7),
        ("implicit", True),
        ("implicit", ""),
        ("assets", {"x": 1, "y": 2}),
        ("assets", "ab"),
        ("assets", 7),
        ("assets", 0),
    ],
)
def test_a_draft_container_that_is_not_a_list_fails_the_whole_read(key, container):
    """A container is not N items. Base ``77820bf`` raised on every one of these.

    ``{"implicit": {"x": 1, "y": 2}}`` produced TWO entries on ``ba8e38e``, each
    saying "the stored implicit claim at position 0 is a string, not an implicit
    claim" — a per-position statement about positions that do not exist, built
    out of dict KEYS. That is a plausible-looking partial success, which is
    strictly worse than the failure it replaced, and it contradicted this
    section's own comment that a bundle-level failure is not absorbed here.

    The falsy containers (``""``, ``0``) are included deliberately: ``or []``
    answered "this is not a container" with "this container is empty".
    """
    with pytest.raises(TypeError):
        serialize.evidence_trail_from_draft({"fields": {}, key: container})


@pytest.mark.parametrize("key", ["implicit", "assets"])
def test_an_absent_or_null_draft_container_is_still_legal(key):
    """The guard must not turn an OPTIONAL key into a required one.

    Both keys are genuinely optional in a draft, and ``None`` is what an absent
    one reads as. Raising here would convert every ordinary draft into a failed
    read — the opposite over-correction.
    """
    assert serialize.evidence_trail_from_draft({"fields": {}, key: None}) == []
    assert serialize.evidence_trail_from_draft({"fields": {}}) == []
    assert serialize.evidence_trail_from_draft({"fields": {}, key: []}) == []


# --- 3. a genuine BUNDLE failure must still fail the bundle -------------------


def test_a_sidecar_whose_evidence_block_is_not_a_mapping_still_fails_the_read(client):
    """NOT converted into a partial success.

    There is no per-item question to answer when the item map itself is not a
    map: every entry is equally unreadable, and answering 200 with an empty or
    part-invented trail would be a misleading claim about the record. The read
    fails, loudly, exactly as it did before this slice.
    """
    exp_id = _export_seed(client)
    path = _sidecar_path(client, exp_id)
    path.write_text(json.dumps({"evidence": ["not", "a", "map"]}), encoding="utf-8")

    with pytest.raises(AttributeError):
        client.get(f"/api/experiments/{exp_id}/evidence")


def test_an_unparseable_sidecar_still_degrades_to_the_draft_trail(client):
    """The pre-existing P4 bundle-level tolerance, re-pinned so this slice cannot
    accidentally reclassify a whole-artifact failure as a per-item one."""
    exp_id = _export_seed(client)
    path = _sidecar_path(client, exp_id)
    path.write_text("{not json", encoding="utf-8")

    resp = client.get(f"/api/experiments/{exp_id}/evidence")
    assert resp.status_code == 200
    entries = resp.json()["evidence"]
    assert entries, "the draft's own envelopes are the sidecar's source, so they still answer"
    assert not any(e.get("unavailable") for e in entries), (
        "a whole-artifact failure is not N per-item failures"
    )


# --- 4. unit level: the two builders, directly --------------------------------


def test_trail_from_sidecar_isolates_per_key():
    record = {"assets": [{"asset_id": "A1", "sha256": "0" * 64}]}
    sidecar = {
        "evidence": {
            "system.technique": [{"source_type": "spreadsheet", "source_file": "c.csv"}],
            "system.facility.beamline": 7,
            "assets:A1": [{"source_type": "file_listing", "source_file": "l.txt"}],
        }
    }
    entries = _by_path(serialize.evidence_trail_from_sidecar(sidecar, record))

    assert set(entries) == {"system.technique", "system.facility.beamline", "assets:A1"}
    assert entries["system.technique"]["evidence"][0]["source_file"] == "c.csv"
    # The asset's value still resolves from the record — a neighbour's failure
    # does not cost this entry its sha256.
    assert entries["assets:A1"]["value"] == "0" * 64
    assert entries["system.facility.beamline"]["unavailable"] is True


def test_trail_from_draft_isolates_fields_implicit_and_assets():
    draft = {
        "fields": {
            "a.good": {"value": 1, "status": "verified", "evidence": [{"source_type": "spreadsheet"}]},
            "a.bad": {"value": 2, "status": "verified", "evidence": {"nope": True}},
            "a.worse": 7,
        },
        "implicit": [{"about": "element", "value": "Cu", "evidence": []}, 7],
        "assets": [{"asset_id": "A1", "sha256": "f" * 64, "evidence": []}, "not an asset"],
    }
    entries = _by_path(serialize.evidence_trail_from_draft(draft))

    assert set(entries) == {
        "a.good",
        "a.bad",
        "a.worse",
        "implicit:element",
        "implicit:#1",
        "assets:A1",
        "assets:#1",
    }
    assert entries["a.good"]["evidence"] == [{"source_type": "spreadsheet"}]
    assert entries["a.good"].get("unavailable") is None
    # A readable value is NOT thrown away just because its evidence is not.
    assert entries["a.bad"]["value"] == 2
    assert entries["a.bad"]["unavailable"] is True
    assert entries["assets:A1"]["value"] == "f" * 64
    assert entries["assets:#1"]["unavailable"] is True


def test_an_absent_evidence_list_is_not_reported_as_unavailable():
    """Crying wolf would be its own honesty defect.

    A field legitimately carrying no citation is a normal, common state; it must
    not acquire an error badge from this slice.
    """
    entries = serialize.evidence_trail_from_draft(
        {"fields": {"a.b": {"value": 1, "status": "verified"}}}
    )
    assert entries[0].get("unavailable") is None
    assert entries[0]["evidence"] == []


def test_the_reason_never_quotes_the_stored_value():
    """The reason names the SHAPE found, never the content.

    Interpolating stored content into an error string is how an error message
    starts reading like a citation. The type is enough to locate the problem.
    """
    entries = serialize.evidence_trail_from_draft(
        {"fields": {"a.b": {"value": 1, "status": "verified", "evidence": "SECRET-LOOKING-STRING"}}}
    )
    assert "SECRET-LOOKING-STRING" not in entries[0]["unavailable_reason"]
    assert "is a string" in entries[0]["unavailable_reason"]


# --- 5. the deterministic Assistant must not ANSWER what it could not read ----
#
# The review's most serious finding: this slice created a REGRESSION on a surface
# it did not touch. Making the unreadable entry visible in the trail made
# `_match_field_entry` succeed where it used to return None, and both answer
# functions read `entry["evidence"]` without ever reading `entry["unavailable"]`.
# Measured on `ba8e38e` with `{"fields": {"sample.name": 7}}`:
#
#   base `77820bf`  trail []            -> no match -> `insufficient_context`
#                                          "No cited source is recorded for a
#                                          field yet."
#   branch `ba8e38e` 1 unavailable entry -> MATCH    -> `answered`
#                                          "Name has no cited source recorded
#                                          yet."
#
# A refusal became a confident FALSE claim. The browser side of this same branch
# already refused that exact sentence (`adapt.ts::provenanceFor`).


class _Classified:
    def __init__(self, field):
        self.extracted = {"field": field}


class _Ctx:
    def __init__(self, trail):
        self.evidence_trail = trail


_UNREADABLE = {
    "path": "sample.name",
    "value": None,
    "status": serialize.UNAVAILABLE_STATUS,
    "evidence": [],
    "unavailable": True,
    "unavailable_reason": "this field's stored draft envelope is a number, not an evidence envelope",
}

_PARTIAL = {
    "path": "sample.name",
    "value": "x",
    "status": "verified",
    "evidence": [{"source_type": "spreadsheet"}],
    "unavailable": True,
    "unavailable_reason": "1 of 2 stored evidence entries cannot be shown: not an evidence object",
}


@pytest.mark.parametrize("fn", [aq._provenance, aq._evidence])
def test_assistant_refuses_a_field_whose_evidence_could_not_be_read(fn):
    """Never "has no cited source" / "has no evidence" — the entry may have both."""
    text, result, grounding, citations, _ = fn(
        _Classified("name"), _Ctx([_UNREADABLE]), "/r/1", []
    )

    assert result == "insufficient_context", (
        "this question was not answered from grounded evidence; recording it as "
        "`answered` would make the outcome field itself a false statement"
    )
    assert "could not be read" in text
    assert "no cited source" not in text.lower()
    assert "has no evidence" not in text.lower()
    assert "no separate evidence entries" not in text.lower()
    # The reason is passed through — it names the SHAPE, never the stored value.
    assert "not an evidence envelope" in text
    assert grounding == ["files"]
    # A route to the surface that reports the same failure per entry. It asserts
    # nothing about the evidence; it lets the user go look.
    assert citations and citations[0]["navigate_to"] == "/r/1/evidence"


@pytest.mark.parametrize("fn", [aq._provenance, aq._evidence])
def test_assistant_answers_a_partially_readable_field_and_discloses_the_rest(fn):
    """The readable entries DO answer the question; the gap is named, not hidden.

    Deliberately still `answered` — refusing here would throw away real, readable
    provenance, which is over-refusal rather than honesty.
    """
    text, result, _, citations, _ = fn(
        _Classified("name"), _Ctx([_PARTIAL]), "/r/1", []
    )

    assert result == "answered"
    assert "spreadsheet" in text, "what WAS readable is still stated"
    assert "unavailable" in text.lower(), "and what was not is stated too"
    assert "cannot be shown" in text
    assert citations and citations[0]["navigate_to"] == "/r/1/evidence"


@pytest.mark.parametrize("fn", [aq._provenance, aq._evidence])
def test_assistant_unmatched_fallback_does_not_claim_the_trail_is_empty(fn):
    """The no-labels fallback was the SAME false sentence, one branch over.

    `_traceable_labels` excludes an unreadable entry (correctly — it cannot be
    traced), so a trail of nothing but unreadable entries produced an empty label
    list and fell through to "No cited source is recorded for a field yet." Every
    entry in that trail HAS one; none of them could be read.
    """
    text, result, _, _, _ = fn(_Classified(None), _Ctx([_UNREADABLE]), "/r/1", [])

    assert result == "insufficient_context"
    assert "could not be read" in text
    assert "no cited source is recorded" not in text.lower()
    assert "no field has recorded evidence entries" not in text.lower()


@pytest.mark.parametrize("fn", [aq._provenance, aq._evidence])
def test_assistant_still_says_nothing_is_recorded_when_nothing_is(fn):
    """The honest negative must survive: an empty trail is genuinely empty.

    Without this, the fix above could have been "never say it is empty", which
    would be over-refusal in the one case where the claim is true.
    """
    text, result, _, _, _ = fn(_Classified(None), _Ctx([]), "/r/1", [])

    assert result == "insufficient_context"
    assert "could not be read" not in text
    assert "yet." in text


def test_traceable_labels_excludes_the_unreadable_but_keeps_the_partial():
    """Consistency with the answer path, asserted rather than assumed.

    An entry this surface cannot trace is not offered as traceable; an entry it
    CAN partly trace is offered, and the answer for it discloses the rest.
    """
    assert aq._traceable_labels([_UNREADABLE]) == []
    assert aq._traceable_labels([_PARTIAL]) == ["Name"]
    assert aq._unreadable_trail_count([_UNREADABLE, _PARTIAL]) == 1


def test_assistant_endpoint_refuses_end_to_end_for_an_unreadable_field(client):
    """The unit assertions above, proven through the real route and real draft."""
    exp_id = _seed_id(client)
    victim = None

    def corrupt(d):
        nonlocal victim
        victim = next(iter(d["fields"]))
        d["fields"][victim] = 7

    _corrupt_draft(client, exp_id, corrupt)

    token = victim.split(".")[-1].split(":")[-1].replace("_", " ")
    body = client.post(
        f"/api/experiments/{exp_id}/assistant/query",
        json={"question": f"where did the {token} come from"},
    ).json()

    assert body["result"] == "insufficient_context", body
    assert "could not be read" in body["answer"]
    assert "no cited source" not in body["answer"].lower()
