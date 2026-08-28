"""`system.domain` and `system.technique` had no write path anywhere. Measured, then closed.

THE DEFECT
==========
Both are declared REQUIRED by the vendored official schema
(``schema/isaac_record_v1.json`` -> ``properties.system.required == ["domain",
"technique"]``), and neither could be set ON THE RECORD by any request. Measured over
HTTP at ``6d5bda6``, on a record created through ``POST /api/experiments`` with one run,
sending the correct current ``ETag`` for every attempt:

======================================  =================  ====================
route                                   ``system.domain``  ``system.technique``
======================================  =================  ====================
``POST /experiments/{id}/edit``         422 unrecognized   422 unrecognized
``POST /experiments/{id}/answers``      422 unrecognized   422 unrecognized
``PATCH /experiments/{id}/runs/{rid}``  422 unrecognized   422 unrecognized
``POST .../runs/{rid}/edit``            422 unrecognized   422 unrecognized
``POST .../runs/{rid}/answers``         422 unrecognized   422 unrecognized
``POST .../runs/{rid}/overrides``       422 not_overridable  **200**
======================================  =================  ====================

**THE LAST CELL IS THE ONE A RE-MEASUREMENT CORRECTED**, and it is written out because
it is the difference between "no route accepts this" and "one route accepts it and it is
the wrong route". ``field:system.technique`` IS in
``routes.EXPERIMENT_OVERRIDABLE_ADDRESSES`` and its override is accepted — with ANY
value, off-enum included (measured: ``NOT_A_TECHNIQUE`` -> ``200``). But a run override
records a DIVERGENCE from a value the record does not hold, and a run that has recorded
any override stops inheriting the record's implicit derivations. It is not a way to say
what the record is, and it is not a record-level write. ``system.domain`` is not in
``EXTRACTOR_FIELD_MAP`` at all, so it is not even overridable.

WHY IT MATTERED MORE THAN AN ABSENCE. ``system`` is not top-level-required, so a record
carrying NEITHER field exports cleanly. A record carrying a technique (through that
override, or a facility field) and no domain fails official validation with ``'domain'
is a required property`` — and could not be repaired, only cleared. ``CLAUDE.md`` §11
records exactly that: *"`system.domain` HAS NO WRITE PATH ANYWHERE, which is why setting
`technique` or a facility field makes a record un-exportable-until-cleared."*

WHY THIS IS NOT THE DERIVATION §5 FORBIDS
=========================================
The premise prior sessions declined on — that ``domain`` would have to be DERIVED from
``technique``, requiring a 37-entry scientific classification that exists nowhere in this
repository — is avoidable and is not adopted. Both fields are CLOSED ENUMS the official
schema declares, and a scientist choosing one of the schema's own values is a user
confirmation over a bounded set. Nothing is derived, nothing is defaulted, neither is
inferred from the other: a record given only one keeps the other missing and stays
blocked, and ``test_neither_field_is_ever_inferred_from_the_other`` pins that.

Everything here is synthetic: a tmp workspace, records created through
``POST /api/experiments``, no database, no network, no file outside the workspace.
"""

from __future__ import annotations

import json

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws


@pytest.fixture(autouse=True)
def _schema_cache_is_never_left_poisoned():
    """Belt and braces around the process-lifetime cache this module documents.

    One test deliberately induces the fail-closed empty mapping. ``lru_cache`` holds it
    until something clears it, so a bug in that test's own cleanup would silently
    disable this feature for every later test in the process rather than failing where
    the mistake is. It has happened once already; this makes it impossible to happen
    quietly.
    """
    yield
    routes._record_enum_fields.cache_clear()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _experiment(client) -> str:
    r = client.post("/api/experiments", json={"title": "Cu K-edge XANES, 300 K"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _etag(client, url: str) -> str:
    return client.get(url).headers["ETag"]


def _answer(client, experiment_id: str, answers: dict, *, etag: str | None = None):
    url = f"/api/experiments/{experiment_id}"
    return client.post(
        f"{url}/answers",
        json={"confirmed_by_user": True, "answers": answers},
        headers={"If-Match": etag if etag is not None else _etag(client, url)},
    )


def _edit(client, experiment_id: str, answers: dict, *, etag: str | None = None):
    url = f"/api/experiments/{experiment_id}"
    return client.post(
        f"{url}/edit",
        json={"confirmed_by_user": True, "answers": answers},
        headers={"If-Match": etag if etag is not None else _etag(client, url)},
    )


def _stored_fields(experiment_id: str) -> dict:
    """The record's own field map, read from the persisted document.

    Deliberately not the detail response: ``GET /api/experiments/{id}`` serves a
    projected ``draft`` (measured empty on a created record, before and after this
    change), so a test that read it could not see whether anything was written at all.
    """
    exp = ws.load_experiment(experiment_id)
    assert exp is not None
    return (exp.draft or {}).get("fields") or {}


def _schema() -> dict:
    from isaac_records.official import schema_path

    return json.loads(schema_path(ws.REPO_ROOT).read_text(encoding="utf-8"))


# --- the derivation ----------------------------------------------------------


def test_the_writable_enum_paths_are_read_from_the_schema_not_transcribed():
    """The set AND the values come from the vendored document, re-derived here.

    Re-derived rather than asserted against a literal: a test that hard-codes the 37
    techniques is a second transcription of the thing the implementation exists to avoid
    transcribing, and the two would drift together silently on a schema refresh.

    The three gates are asserted individually below, because the equality alone would
    pass for the wrong reason if any one of them stopped being applied and the others
    happened to exclude the same paths.
    """
    schema = _schema()
    served = routes._record_enum_fields()

    system = schema["properties"]["system"]["properties"]
    assert served["system.domain"] == tuple(system["domain"]["enum"])
    assert served["system.technique"] == tuple(system["technique"]["enum"])
    assert set(served) == {"system.domain", "system.technique"}

    # Gate 1 — every served path's schema node declares an enum.
    # Gate 3 — every served path is classified experiment-level.
    for path in served:
        assert ws.field_level(path) == ws.LEVEL_EXPERIMENT, path
        assert served[path], path

    # Gate 2 — the parent declares it required. Both are, and the OPTIONAL enum leaves
    # the schema also carries are excluded: this is the assertion that fails if the
    # `required` gate is dropped.
    assert set(schema["properties"]["system"]["required"]) == {"domain", "technique"}
    optional_enum_leaves = [
        key
        for key, node in system.items()
        if isinstance(node, dict) and "enum" in node and key not in ("domain", "technique")
    ]
    assert all(f"system.{key}" not in served for key in optional_enum_leaves)


def test_a_run_level_enum_and_an_unclassified_one_are_both_excluded():
    """The level gate is real, and both exclusions have their own owner.

    ``context.environment`` is a REQUIRED enum leaf that ``field_level`` classifies as
    run-level — it is written on the run by ``PATCH .../runs/{run_id}``, and admitting it
    here would give one field two write paths at two levels. ``measurement.qc.status`` is
    a required enum that is unclassified — it is the ``qc`` answer key.

    MUTATION: dropping the ``LEVEL_EXPERIMENT`` gate turns this RED.
    """
    served = routes._record_enum_fields()
    assert "context.environment" not in served
    assert ws.field_level("context.environment") == ws.LEVEL_RUN
    assert "context.environment" in routes.RUN_WRITABLE_FIELD_PATHS
    assert "measurement.qc.status" not in served


def test_an_unreadable_schema_fails_closed_and_writes_nothing(client, tmp_path, monkeypatch):
    """A schema this process cannot read means NO path is writable, never an open gate.

    The REAL branch is exercised — the read is made to fail, rather than the function
    being replaced with one that returns nothing. Replacing it would prove only that the
    callers handle an empty mapping, which is the easy half; what has to be proved is
    that an unreadable vendored document produces one instead of raising, and that the
    result is a refusal rather than an open door.

    The cache is cleared on the way in AND on the way out. ``lru_cache`` would otherwise
    hold the poisoned answer for every later test in this process — which is exactly the
    behaviour the implementation documents in production, and exactly why a test that
    induces it has to clean up after itself.
    """
    experiment_id = _experiment(client)
    routes._record_enum_fields.cache_clear()
    monkeypatch.setattr(routes, "schema_path", lambda _root: tmp_path / "no-such-schema.json")
    try:
        assert dict(routes._record_enum_fields()) == {}
        r = _answer(client, experiment_id, {"system.domain": "experimental"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "unrecognized_field"
        assert _stored_fields(experiment_id) == {}
    finally:
        # ORDER IS LOAD-BEARING AND WAS GOT WRONG ONCE: undo the patch FIRST, then
        # clear. Clearing while the patch is still live and then reading the mapping
        # re-caches the EMPTY answer, which poisoned every later test in the process —
        # 26 failures from one line, and a demonstration of the very cache behaviour
        # this test exists to document.
        monkeypatch.undo()
        routes._record_enum_fields.cache_clear()
    assert set(routes._record_enum_fields()) == {"system.domain", "system.technique"}


def test_the_derived_mapping_cannot_be_widened_by_a_caller(client):
    """It is shared — every call returns the same object — so it is read-only.

    A caller that added a path to it would widen this application's write surface for
    the life of the process, at a distance, with no request and no review.
    """
    served = routes._record_enum_fields()
    assert served is routes._record_enum_fields()
    with pytest.raises(TypeError):
        served["sample.material.name"] = ("anything",)


# --- THE NEGATIVE CONTROL: this is what could not be done -------------------


def test_a_scientist_can_set_domain_and_technique_on_a_record_they_created(client):
    """DEFECT-SHAPED NEGATIVE CONTROL. Against pre-change code this fails at the first
    request with ``422 unrecognized_field``.

    It borrows nothing: the record is created through the product's own Create
    Experiment path and both values are written out as a person would choose them from
    the schema's list, for the reason ``test_scientist_can_finish_a_record``'s docstring
    gives — a helper that harvested a seed's answers would start past the part that did
    not work.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"

    r = _answer(
        client,
        experiment_id,
        {"system.domain": "experimental", "system.technique": "XAS"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["invalidation"]["changed"] is True
    assert sorted(body["invalidation"]["changed_fields"]) == [
        "system.domain",
        "system.technique",
    ]

    stored = _stored_fields(experiment_id)
    assert stored["system.domain"]["value"] == "experimental"
    assert stored["system.technique"]["value"] == "XAS"
    for path in ("system.domain", "system.technique"):
        assert stored[path]["status"] == "verified"

    # AND IT SURVIVES A ROUND TRIP THROUGH THE READ SURFACE a scientist actually looks
    # at, not only the stored document.
    trail = {e["path"]: e for e in client.get(f"{url}/evidence").json()["evidence"]}
    assert trail["system.domain"]["value"] == "experimental"
    assert trail["system.technique"]["value"] == "XAS"


def test_the_written_value_carries_the_exact_four_key_user_confirmation(client):
    """The evidence shape is ``complete.py``'s, reused rather than re-invented.

    Asserted as an EXACT key set: a fifth key, or a renamed one, would still read as
    "there is evidence" to every surface that only checks for a non-empty list, and the
    draft validator's coverage rule would still pass. The four keys are what
    ``models.user_confirmation`` produces and what ``complete._user_confirmation``
    produces, and both are asserted against here rather than against a literal.
    """
    from isaac_records.complete import _user_confirmation
    from isaac_records.models import user_confirmation

    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"system.technique": "XAS"}).status_code == 200

    evidence = _stored_fields(experiment_id)["system.technique"]["evidence"]
    assert len(evidence) == 1
    entry = evidence[0]
    assert set(entry) == set(user_confirmation("q", "a", "t"))
    assert set(entry) == set(_user_confirmation("q", "a", "t"))
    assert entry["source_type"] == "user_confirmation"
    assert entry["answer"] == "XAS"
    assert entry["question"] == "Value for system.technique on this record?"
    assert entry["timestamp"]

    # THE QUESTION SAYS "this record", NOT "this run", and that is the one thing the
    # reused writer had to be told. A run's confirmation makes a claim about that run.
    assert "on this run" not in entry["question"]
    assert routes._run_field_question("system.technique") != entry["question"]


# --- the enum gate -----------------------------------------------------------


@pytest.mark.parametrize(
    "path,value",
    [
        ("system.domain", "nope"),
        ("system.domain", "Experimental"),  # the schema's values are case-sensitive
        ("system.technique", "NOT_A_TECHNIQUE"),
        ("system.technique", "xas"),
        ("system.technique", 5),
        ("system.technique", True),
        ("system.technique", ["XAS"]),
        ("system.technique", {"value": "XAS"}),
    ],
)
def test_a_value_the_schema_does_not_allow_is_refused_and_nothing_is_written(
    client, path, value
):
    """Refused BEFORE any mutation, with the record byte-identical afterwards.

    The wrong-TYPED cases are here deliberately: enum membership is the one gate, so a
    number, a bool, a list and an object are all simply not in the list. There is no
    separate type check to disagree with it and no path by which one of them is stored.
    """
    experiment_id = _experiment(client)
    before = ws.load_experiment(experiment_id)
    r = _answer(client, experiment_id, {path: value})

    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "not_an_allowed_value"
    assert body["key"] == path and body["keys"] == [path]
    assert body["experiment_id"] == experiment_id
    assert _stored_fields(experiment_id) == {}
    assert ws.load_experiment(experiment_id).rev == before.rev


def test_the_refusal_names_every_offending_field_and_the_schemas_own_values(client):
    """`allowed` is the schema's list, whole, for both fields — not a pointer elsewhere.

    Echoing all 37 techniques is the decision the implementation argues for: the values
    are the schema's own published vocabulary (already served by ``GET /api/schema``),
    they are bounded and cannot grow with caller input, and a refusal a client must act
    on should say what to send rather than only what not to.

    THE VALUE IS NOT ECHOED, which is this module's standing convention — an error body
    is not a reflection surface for caller-supplied content.
    """
    experiment_id = _experiment(client)
    r = _answer(
        client,
        experiment_id,
        {"system.domain": "nope", "system.technique": "also-nope"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["keys"] == ["system.domain", "system.technique"]

    system = _schema()["properties"]["system"]["properties"]
    assert body["allowed"]["system.domain"] == system["domain"]["enum"]
    assert body["allowed"]["system.technique"] == system["technique"]["enum"]
    assert len(body["allowed"]["system.technique"]) == 37

    assert "also-nope" not in json.dumps(body)


def test_an_enum_field_and_a_shaped_answer_land_together_in_one_request(client):
    """The two writers run side by side in ONE lock, ONE precondition, ONE save.

    ``complete.apply_answers`` writes the blocks its blockers name and has no branch for
    a dotted field path; the enum write is the route's. A caller must not have to know
    that, so a body carrying both is one request, one revision, and one honest count.
    """
    experiment_id = _experiment(client)
    r = _answer(
        client,
        experiment_id,
        {
            "system.domain": "experimental",
            "qc": {
                "status": "valid",
                "evidence": "Scans reproducible across three repeats.",
            },
        },
    )
    assert r.status_code == 200, r.text
    assert sorted(r.json()["invalidation"]["changed_fields"]) == ["qc", "system.domain"]

    stored = ws.load_experiment(experiment_id)
    assert stored.rev == 1
    assert stored.draft["fields"]["system.domain"]["value"] == "experimental"
    assert stored.draft["qc"]["status"] == "valid"


def test_an_off_enum_value_refuses_the_WHOLE_request_and_writes_nothing(client):
    """FAIL-CLOSED, AND FAIL-CLOSED IS ABOUT TIMING AS WELL AS DECISION.

    ``CLAUDE.md`` §11 records the lesson from the reset defect in exactly those words:
    *"fail-closed describes the DECISION, not its TIMING"*, and a refusal filed after a
    partial mutation is worse than no refusal at all. So the enum screen runs BEFORE
    anything is applied, and a body whose only fault is one off-enum value leaves the
    perfectly good ``qc`` beside it unwritten and the revision unmoved — rather than
    storing half of what was sent and reporting failure.
    """
    experiment_id = _experiment(client)
    r = _answer(
        client,
        experiment_id,
        {
            "system.domain": "nope",
            "qc": {"status": "valid", "evidence": "Reproducible across three repeats."},
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "not_an_allowed_value"

    stored = ws.load_experiment(experiment_id)
    assert stored.rev == 0
    assert (stored.draft or {}).get("qc") is None
    assert _stored_fields(experiment_id) == {}
    assert stored.answer_log == []


def test_the_enum_gate_is_applied_by_the_correction_operation_too(client):
    """Same gate, same code, on the route that overwrites a confirmed value.

    MUTATION: screening only the answers operation leaves a confirmed, exportable value
    replaceable with one official validation would refuse — which is strictly worse than
    never having accepted it, because the record was valid before the request.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"system.technique": "XAS"}).status_code == 200

    r = _edit(client, experiment_id, {"system.technique": "NOT_A_TECHNIQUE"})
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "not_an_allowed_value"
    assert _stored_fields(experiment_id)["system.technique"]["value"] == "XAS"


# --- /answers answers what is open; /edit corrects what is answered ----------


def test_correcting_a_field_the_record_has_never_held_is_refused_and_redirected(client):
    """``/edit`` keeps its contract exactly: it corrects, it does not create.

    ``answer_at`` is unconditionally the record's own answers operation, and that is
    provably actionable rather than plausibly so — these paths are experiment-level, so
    that operation accepts them whether or not the record has runs, which the second half
    of this test measures.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"

    r = _edit(client, experiment_id, {"system.domain": "experimental"})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "not_yet_answered"
    assert body["keys"] == ["system.domain"]
    assert body["answer_at"] == "POST /api/experiments/{experiment_id}/answers"
    assert body["experiment_id"] == experiment_id
    assert _stored_fields(experiment_id) == {}

    # The redirect resolves, on a record that HAS a run — the state in which the sibling
    # refusal must withhold its own pointer.
    assert (
        client.post(
            f"{url}/runs",
            json={"confirmed_by_user": True, "label": "Run 1"},
            headers={"If-Match": _etag(client, url)},
        ).status_code
        == 201
    )
    assert _answer(client, experiment_id, {"system.domain": "experimental"}).status_code == 200


def test_answering_a_field_that_already_holds_a_different_value_is_refused(client):
    """``/answers`` keeps its contract exactly: it answers, it does not overwrite.

    Nothing is written and the stored value is unchanged, so a caller that follows
    ``answer_at`` loses nothing — and the operation it names accepts the request, which
    the last two lines measure rather than assume.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"system.technique": "XAS"}).status_code == 200
    rev_before = ws.load_experiment(experiment_id).rev

    r = _answer(client, experiment_id, {"system.technique": "XES"})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "already_answered"
    assert body["keys"] == ["system.technique"]
    assert body["answer_at"] == "POST /api/experiments/{experiment_id}/edit"
    assert _stored_fields(experiment_id)["system.technique"]["value"] == "XAS"
    assert ws.load_experiment(experiment_id).rev == rev_before

    assert _edit(client, experiment_id, {"system.technique": "XES"}).status_code == 200
    assert _stored_fields(experiment_id)["system.technique"]["value"] == "XES"


def test_resubmitting_the_identical_value_is_a_success_and_moves_no_revision(client):
    """The documented retry behaviour, unchanged for these keys.

    A client may repeat a request it is unsure landed. The writer is idempotent, so the
    document is byte-stable, ``rev`` does not move, and the confirmation is not
    restamped — a fresh timestamp on every retry would rewrite provenance for a request
    that changed nothing.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"system.domain": "computational"}).status_code == 200
    after_first = ws.load_experiment(experiment_id)

    r = _answer(client, experiment_id, {"system.domain": "computational"})
    assert r.status_code == 200, r.text
    assert r.json()["invalidation"]["changed"] is False
    assert r.json()["invalidation"]["changed_fields"] == []

    # THE NO-OP REASON UNDERSTATES RATHER THAN OVERSTATES, and that is deliberate.
    # "the submitted value was identical" would be TRUE here, and it is not claimed:
    # `_resubmission_was_identical` reads the apply-shape, which never carries these
    # keys, so the route says the weaker true thing instead of teaching that function a
    # second key set. The sentence that must never appear is the one this module has
    # been caught serving falsely — asserted absent so a future change cannot add it
    # without deciding whether it has earned it.
    reason = r.json()["invalidation"]["reason"] or ""
    assert "nothing was written" in reason, reason
    assert "identical" not in reason, reason

    after_second = ws.load_experiment(experiment_id)
    assert after_second.rev == after_first.rev
    assert after_second.draft == after_first.draft


def test_a_correction_appends_a_fresh_confirmation_and_keeps_the_one_it_displaces(client):
    """Provenance is added to, never overwritten — the writer's existing discipline.

    A scientist who corrects a technique has said two things at two times, and the trail
    records both. This is ``_apply_run_field``'s prior-evidence carry, which is exactly
    why the writer is reused rather than reimplemented.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"system.technique": "XAS"}).status_code == 200
    assert _edit(client, experiment_id, {"system.technique": "XES"}).status_code == 200

    evidence = _stored_fields(experiment_id)["system.technique"]["evidence"]
    assert [e["answer"] for e in evidence] == ["XAS", "XES"]
    assert all(e["source_type"] == "user_confirmation" for e in evidence)


# --- the preconditions are untouched ----------------------------------------


def test_the_record_precondition_is_unchanged_for_these_keys(client):
    """428 absent, 412 stale, on both operations, with nothing written.

    The write is gated on the RECORD's ``If-Match`` through the existing
    ``_check_if_match``/``_save_versioned`` compare-and-swap; no second precondition
    mechanism was added and none was weakened.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    assert _answer(client, experiment_id, {"system.domain": "experimental"}).status_code == 200
    stored = _stored_fields(experiment_id)

    for operation, answers in (
        ("answers", {"system.technique": "XAS"}),
        ("edit", {"system.domain": "computational"}),
    ):
        absent = client.post(
            f"{url}/{operation}",
            json={"confirmed_by_user": True, "answers": answers},
        )
        assert absent.status_code == 428, absent.text
        stale = client.post(
            f"{url}/{operation}",
            json={"confirmed_by_user": True, "answers": answers},
            headers={"If-Match": '"0000000000000000.1"'},
        )
        assert stale.status_code == 412, stale.text

    assert _stored_fields(experiment_id) == stored


def test_an_unconfirmed_body_is_still_refused_before_anything_is_read(client):
    """``confirmed_by_user`` is unchanged and still precedes everything."""
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    r = client.post(
        f"{url}/answers",
        json={"answers": {"system.domain": "experimental"}},
        headers={"If-Match": _etag(client, url)},
    )
    assert r.status_code == 422 and r.json()["error"] == "confirmation_required"
    assert _stored_fields(experiment_id) == {}


# --- the level split -------------------------------------------------------


@pytest.mark.parametrize("path", ["system.domain", "system.technique"])
def test_the_run_operations_still_refuse_both_paths(client, path):
    """These are the RECORD's fields. A run INHERITS them and does not own them.

    ``EXPERIMENT_LEVEL_FIELD_PATHS`` lists both, and this slice follows that
    classification rather than widening it. Writing a record-level value on a run would
    put the same value in two places, which is the rule ``patch_run`` already enforces
    and ``test_run_api`` already pins for ``system.domain``.

    ``POST .../runs/{rid}/overrides`` is deliberately NOT asserted here: recording a
    run's DIVERGENCE from an inherited value is a different act, ``system.technique``
    has always been overridable, and this slice does not change that route.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    created = client.post(
        f"{url}/runs",
        json={"confirmed_by_user": True, "label": "Run 1"},
        headers={"If-Match": _etag(client, url)},
    )
    assert created.status_code == 201, created.text
    run = f"{url}/runs/{created.json()['run']['id']}"

    for response in (
        client.patch(
            run,
            json={"confirmed_by_user": True, "fields": {path: "XAS"}},
            headers={"If-Match": _etag(client, run)},
        ),
        client.post(
            f"{run}/answers",
            json={"confirmed_by_user": True, "answers": {path: "XAS"}},
            headers={"If-Match": _etag(client, run)},
        ),
        client.post(
            f"{run}/edit",
            json={"confirmed_by_user": True, "answers": {path: "XAS"}},
            headers={"If-Match": _etag(client, run)},
        ),
    ):
        assert response.status_code == 422, (path, response.text)
        assert response.json()["error"] == "unrecognized_field", path


def test_a_record_level_value_is_inherited_by_every_run(client):
    """Set once on the record, read by each run — never copied down.

    This is what makes the record the right level for it, and it is measured rather than
    argued: the run's resolved view reports the record's value as inherited.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    assert _answer(client, experiment_id, {"system.technique": "XAS"}).status_code == 200
    created = client.post(
        f"{url}/runs",
        json={"confirmed_by_user": True, "label": "Run 1"},
        headers={"If-Match": _etag(client, url)},
    )
    assert created.status_code == 201, created.text
    inherited = created.json()["run"]["inherited"]
    assert inherited["field:system.technique"]["payload"]["value"] == "XAS"
    assert inherited["field:system.technique"]["state"] == "inherited"


# --- no guessing -----------------------------------------------------------


def test_neither_field_is_ever_inferred_from_the_other(client):
    """Give only one and the other stays MISSING. The record stays blocked; that is right.

    This is the whole §5 argument made checkable. An application that filled in
    ``domain: experimental`` because the technique was ``XAS`` would be asserting a
    37-entry scientific classification that exists nowhere in this repository.

    MUTATION: any default, any derivation, any fallback turns this RED.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"system.technique": "XAS"}).status_code == 200
    stored = _stored_fields(experiment_id)
    assert "system.domain" not in stored

    other = _experiment(client)
    assert _answer(client, other, {"system.domain": "computational"}).status_code == 200
    assert "system.technique" not in _stored_fields(other)


def test_a_blank_answer_is_dropped_and_never_clears_a_confirmed_value(client):
    """A blank answer is not an answer, and CLEARING is deliberately not built.

    The writer this reuses removes a field when handed ``None``; the filter in front of
    it never hands it one. Un-saying a confirmed record-level classification is a real
    operation with its own questions, and inheriting it as a side effect of a
    blank-tolerant filter would be deciding them by accident.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"system.domain": "experimental"}).status_code == 200
    before = ws.load_experiment(experiment_id)

    for blank in (None, ""):
        r = _answer(client, experiment_id, {"system.domain": blank})
        # A body of only blanks names nothing answerable, exactly as it always has.
        assert r.status_code in (200, 422), r.text
        assert _stored_fields(experiment_id)["system.domain"]["value"] == "experimental"
    assert ws.load_experiment(experiment_id).rev == before.rev


# --- what this slice deliberately did NOT change ----------------------------


def test_setting_these_fields_opens_and_closes_no_blocking_question(client):
    """They are NOT pending questions, and that is a measured decision, not an omission.

    THE MEASUREMENT, AND A CORRECTION TO IT. ~~"including all five canonical seeds, none
    of which carries either field"~~ — **FALSE, and recorded rather than replaced,
    because the mistake is the instructive part.** All five seeds DO carry both
    (``system.domain: experimental``, ``system.technique: HERFD-XAS``); the first reading
    came from ``GET /api/experiments/{id}``'s ``draft``, which is PROJECTED and is ``{}``
    on every record. Read from the store, the seeds are unaffected either way.

    The argument survives the correction, narrowed to what it always actually applied to:
    a record created through ``POST /api/experiments`` carries NEITHER field, and
    ``system`` is not top-level-required, so such a record exports cleanly today with
    both absent. Making them pending would add two blockers to every one of them —
    ``pending_count`` +2, ``status`` to ``needs_attention``, ``export_ready`` to
    ``False`` — blocking records the official schema accepts. That is a behaviour change
    with no defect behind it, so it is not made here.

    So the export gate is unchanged in both directions, and this test pins that:
    answering neither field does not block, and answering both does not unblock.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    before = client.get(url).json()

    assert (
        _answer(
            client,
            experiment_id,
            {"system.domain": "experimental", "system.technique": "XAS"},
        ).status_code
        == 200
    )
    after = client.get(url).json()
    assert after["pending_count"] == before["pending_count"]
    assert after["status"] == before["status"]

    # `export_ready` is asserted on the domain object rather than on the response,
    # because the detail response does not serve it — reading it here rather than
    # skipping it is the point: it is the third derived value a pending entry moves.
    exp = ws.load_experiment(experiment_id)
    assert exp.export_ready() is False
    assert exp.pending_count() == before["pending_count"]


def test_a_confirmed_domain_and_technique_reach_the_exported_official_record(client):
    """The values land in the official record, and the schema stops complaining about them.

    ``transform`` writes every non-missing ``draft["fields"]`` entry into the record by
    its dotted path, so nothing in the truth path needed changing for this to work — and
    nothing in it was changed.

    The record still cannot export for an unrelated reason (a created record owes a
    descriptor), which is exactly right and is asserted rather than worked around: what
    this test proves is that ``system`` is now complete when it is present, not that the
    record is finished.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    assert (
        _answer(
            client,
            experiment_id,
            {"system.domain": "experimental", "system.technique": "XAS"},
        ).status_code
        == 200
    )
    r = client.post(
        f"{url}/export",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, url)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["record"]["system"] == {"domain": "experimental", "technique": "XAS"}
    messages = [e["message"] for e in body["official_report"]["errors"]]
    assert not [m for m in messages if "domain" in m or "technique" in m], messages


def test_the_technique_only_record_that_could_not_be_repaired_now_can_be(client):
    """The concrete trap `CLAUDE.md` §11 names, walked end to end.

    A technique with no domain fails official validation with ``'domain' is a required
    property``, and before this change the only remedy was to clear what had been
    entered. One request now repairs it.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    assert _answer(client, experiment_id, {"system.technique": "XAS"}).status_code == 200

    broken = client.post(
        f"{url}/export",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, url)},
    ).json()
    assert any(
        "'domain' is a required property" in e["message"]
        for e in broken["official_report"]["errors"]
    ), broken["official_report"]

    assert _answer(client, experiment_id, {"system.domain": "experimental"}).status_code == 200
    repaired = client.post(
        f"{url}/export",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, url)},
    ).json()
    assert not any(
        "'domain' is a required property" in e["message"]
        for e in repaired["official_report"]["errors"]
    ), repaired["official_report"]


def test_a_ride_along_key_beside_one_of_these_keeps_its_existing_treatment(client):
    """The recognition seam does not widen what any other key means.

    An unrecognised key travelling beside a recognised one is still dropped on a ``200``
    that withholds the identical-value reason — the behaviour ``_dropped_answer_keys``
    exists to make reportable. Adding these two paths to the recognised set must not
    change that, and must not make a body of ONLY an unknown key stop being refused.
    """
    experiment_id = _experiment(client)
    r = _answer(
        client,
        experiment_id,
        {"system.domain": "experimental", "sample.material.nmae": "Fe2O3"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["invalidation"]["changed_fields"] == ["system.domain"]
    assert "identical" not in (r.json()["invalidation"]["reason"] or "")
    assert "sample.material.nmae" not in _stored_fields(experiment_id)

    only_unknown = _answer(client, _experiment(client), {"sample.material.nmae": "Fe2O3"})
    assert only_unknown.status_code == 422
    assert only_unknown.json()["error"] == "unrecognized_field"


# ---------------------------------------------------------------------------
# The PUBLISHED contract, per level.
# ---------------------------------------------------------------------------
#
# `_refuse_a_value_the_schema_does_not_allow` is called at exactly two sites, both
# RECORD-level, so `not_an_allowed_value` is a code the two RUN-level operations can
# never emit. They answer `unrecognized_field` for these keys, and always have.
#
# The 422 blocks were SHARED constants, and a first version of this slice added the
# record-only prose to the shared ones — so the run's answers/edit contract published a
# refusal code its route cannot raise, and told the caller the two fields are answered
# THERE. That is the failure `routes.py`'s own note calls a sentence pointing at a
# locked door: an agent reads the run contract, sends a correctly spelled key, and is
# told `unrecognized_field`, which means "you misspelled a key".
#
# The remedy was composition: the record-only text lives in its own module-level
# constants and is composed into `_R_ANSWER_REFUSED_RECORD` /
# `_R_CORRECTION_REFUSED_RECORD`, which are mounted on the two record operations only.
# These tests fail if it is ever put back on the shared constant, in either direction.

_RECORD_ANSWERS_PATH = "/api/experiments/{experiment_id}/answers"
_RECORD_EDIT_PATH = "/api/experiments/{experiment_id}/edit"
_RUN_ANSWERS_PATH = "/api/experiments/{experiment_id}/runs/{run_id}/answers"
_RUN_EDIT_PATH = "/api/experiments/{experiment_id}/runs/{run_id}/edit"


def _served_openapi(client) -> dict:
    """The document a machine client actually reads, not a constant read from source.

    Asserting over `routes._R_ANSWER_REFUSED` would pass while the wrong constant was
    mounted, which is precisely the defect: both blocks were correct in isolation and
    the mount was the mistake.
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    return response.json()


def _refusal_description(doc: dict, path: str) -> str:
    return doc["paths"][path]["post"]["responses"]["422"]["description"]


def test_only_the_record_operations_publish_not_an_allowed_value(client):
    """The four 422 descriptions, measured off the served document."""
    doc = _served_openapi(client)
    named = {
        path: "not_an_allowed_value" in _refusal_description(doc, path)
        for path in (
            _RECORD_ANSWERS_PATH,
            _RECORD_EDIT_PATH,
            _RUN_ANSWERS_PATH,
            _RUN_EDIT_PATH,
        )
    }
    assert named == {
        _RECORD_ANSWERS_PATH: True,
        _RECORD_EDIT_PATH: True,
        _RUN_ANSWERS_PATH: False,
        _RUN_EDIT_PATH: False,
    }, named


def test_the_run_contract_does_not_claim_these_fields_are_answered_there(client):
    """The prose, not only the code name — the sentence is the misdirection.

    A run description could drop the literal `not_an_allowed_value` and still tell its
    caller that `system.domain` and `system.technique` are written there, which is the
    half that sends a scientist to the wrong route.
    """
    doc = _served_openapi(client)
    for path in (_RUN_ANSWERS_PATH, _RUN_EDIT_PATH):
        description = _refusal_description(doc, path)
        for claim in (
            "These two fields are answered here",
            "ALSO COVERS THOSE TWO FIELDS",
            "system.domain",
            "system.technique",
        ):
            assert claim not in description, (path, claim)


def test_the_split_took_nothing_away_from_the_run_contract(client):
    """Every refusal the run operations DO raise is still described for them.

    The other direction of the same mistake: hoisting the record-only prose out of a
    shared constant is only safe if the shared refusals came through untouched.
    """
    doc = _served_openapi(client)
    answers_shared = ("unrecognized_field", "invalid_field_value", "already_answered")
    for code in answers_shared:
        assert code in _refusal_description(doc, _RUN_ANSWERS_PATH), code
        assert code in _refusal_description(doc, _RECORD_ANSWERS_PATH), code
    for code in ("unrecognized_field", "invalid_field_value", "not_yet_answered"):
        assert code in _refusal_description(doc, _RUN_EDIT_PATH), code
        assert code in _refusal_description(doc, _RECORD_EDIT_PATH), code
    # The `HTTPValidationError` ref is what `_R_ANSWER_REFUSED`'s own note says must be
    # present on BOTH, because declaring a 422 makes FastAPI stop generating its own.
    for path in (
        _RECORD_ANSWERS_PATH,
        _RECORD_EDIT_PATH,
        _RUN_ANSWERS_PATH,
        _RUN_EDIT_PATH,
    ):
        ref = doc["paths"][path]["post"]["responses"]["422"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        assert ref == "#/components/schemas/HTTPValidationError", path


def test_the_two_levels_do_not_share_one_422_block(client):
    """The structural half: a re-shared constant makes the two descriptions equal.

    Stated over the served document rather than over the module's names, so it also
    fails if someone reintroduces sharing by mounting the record block on the run.
    """
    doc = _served_openapi(client)
    assert _refusal_description(doc, _RECORD_ANSWERS_PATH) != _refusal_description(
        doc, _RUN_ANSWERS_PATH
    )
    assert _refusal_description(doc, _RECORD_EDIT_PATH) != _refusal_description(
        doc, _RUN_EDIT_PATH
    )


def test_what_the_run_operations_actually_answer_for_these_keys(client):
    """The measurement the contract above has to agree with.

    The published refusal set is only honest if it matches what the route emits, so the
    behaviour is asserted beside the document rather than assumed from it.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    created = client.post(
        f"{url}/runs",
        json={"confirmed_by_user": True, "label": "Run 1"},
        headers={"If-Match": _etag(client, url)},
    )
    assert created.status_code == 201, created.text
    run = f"{url}/runs/{created.json()['run']['id']}"
    for suffix in ("answers", "edit"):
        for path in ("system.domain", "system.technique"):
            response = client.post(
                f"{run}/{suffix}",
                json={"confirmed_by_user": True, "answers": {path: "XAS"}},
                headers={"If-Match": _etag(client, run)},
            )
            assert response.status_code == 422, (suffix, path, response.text)
            assert response.json()["error"] == "unrecognized_field", (suffix, path)
