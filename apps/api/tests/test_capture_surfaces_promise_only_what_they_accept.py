"""Two surfaces told a scientist to do something this build refuses. Measured, then pinned.

Both defects here have the shape ``CLAUDE.md`` §12 records for the three scoped
Governance claims: a true-sounding sentence pointing at a locked door. Neither had a
test on ``origin/main``; both are asserted here against real HTTP responses, and each
assertion was verified to go RED with the fix reverted.

D1 — *"a value still has to be entered and confirmed on the field itself"*
--------------------------------------------------------------------------
``UnmappedNotesPanel``, the ``review`` operation's description and ``notes.map_note``'s
docstring all said it, of all 25 mappable paths. Measured over HTTP against every write
route this application has, seven of them are refused by every one. Worse, the notes
module docstring named ``POST .../answers`` and ``POST .../edit`` as "the path that
turns a value into a confirmed field", and those two accept ~~**none of the 25**~~ —
**one of the 25 as of 2026-08-29; see D2 below.** The sentence is left standing with
its correction attached because it is the FINDING this file records, and rewriting a
finding to match today's behaviour is how a file stops saying what it was for.

:func:`test_the_served_writable_set_is_what_the_write_routes_actually_do` is the load-
bearing one: it does not compare two constants, it SENDS a write at all 25 paths to
every write route and compares the observed statuses to the served set.

~~"to all five routes … 125 observed statuses"~~ — **CORRECTED 2026-08-29: THE PROBE
CLAIMED TO COVER EVERY WRITE ROUTE AND ENUMERATED FIVE OF SIX.** ``POST
/api/experiments/{id}/runs/{run_id}/edit`` was missing. Its addition changes NO member
of the served set — measured, it answers ``422 unrecognized_field`` at all 25 paths —
so the file's conclusions were right. **That is exactly why it was worth fixing rather
than shrugging at: a set derived from an incomplete route enumeration is only
accidentally right**, the next accepting route added would have been omitted the same
way, and ``routes._record_enum_fields``' own docstring has listed six all along, so two
places in one module disagreed about how many write routes exist. The probe now sends
**150** requests over **six** routes.

D2 — the surfaces' description of WHERE the value is entered
------------------------------------------------------------
A second stale claim in the same family, corrected in the same change: every accepting
route used to be a run's, so five surfaces said the value is entered "on a run of this
record". ``system.technique`` is now also answered at ``POST .../answers`` and corrected
at ``POST .../edit``, which are the RECORD's, and a record with no runs can hold it.
:func:`test_the_record_level_arm_needs_no_run_at_all` measures that, and
``record_writable_field_paths`` serves the per-path answer so no surface has to
transcribe it.

D3 — a contributor set through the only available write path could never export
-------------------------------------------------------------------------------
``POST .../runs/{run_id}/overrides`` at ``block:attribution`` answered ``200`` and wrote
no ``block_evidence``, so ``draft_validator``'s ``attribution:<name>|<role>`` coverage
rule then refused the export with ``official_report: null`` — for a contributor whose
only write path in this build is that route. The evidence requirement is NOT weakened
anywhere; the write now records the ``user_confirmation`` it had already earned, on the
same flag and with the same ``models.user_confirmation`` shape ``_apply_run_field``
already uses for a run field value.

Everything here is synthetic: a tmp workspace, records created through
``POST /api/experiments``, no database, no network, no file outside the workspace.
"""

from __future__ import annotations

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws



@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _stored_run(experiment_id: str):
    """The persisted Run, read from the ORDINARY workspace scope.

    Deliberately not ``conftest.client_ws``: that binds to a worked-example session, and
    every record here is created through ``POST /api/experiments``, which refuses to run
    inside one. Reading the stored document is how a test can see that no evidence entry
    was minted, which no response body reports.
    """
    experiment = ws.load_experiment(experiment_id, session_id=None)
    assert experiment is not None, experiment_id
    return experiment.runs[0]


def _etag(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _experiment(client, title="Capture-surface fixture") -> str:
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _run(client, experiment_id: str) -> str:
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, f"/api/experiments/{experiment_id}")},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]["id"]


#: A value the coercers and the storable-value guard will each accept, per path. Only
#: the numeric paths need one; everything else takes a string. The point of the probe is
#: WHICH ROUTE ACCEPTS THE PATH, so a value refused for being the wrong TYPE would
#: measure the wrong thing.
_NUMERIC = {
    "context.temperature_K": 300,
    "sample.composition.CuO2_mass_fraction": 0.5,
    "sample.composition.sucrose_mass_fraction": 0.5,
    "sample.geometry.pellet_diameter_mm": 5,
    "system.configuration.n_scans": 3,
}


def _envelope(value):
    """A draft field envelope the no-guessing rules accept, built the repository's way."""
    from isaac_records.models import field_value, user_confirmation

    return field_value(
        value,
        status="verified",
        evidence=[user_confirmation("probe", str(value), "2026-08-26T00:00:00Z")],
    )


# --- D1 -----------------------------------------------------------------------


def test_the_served_writable_set_is_what_the_write_routes_actually_do(client):
    """150 real requests, not a comparison of two constants.

    THIS IS THE TEST THE COPY CLAIM NEEDED AND DID NOT HAVE. A test asserting that
    ``value_writable_field_paths`` equals ``NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT``
    would pass against any set at all, including the empty one and the full 25 — it would
    only prove the server is self-consistent, which is exactly what the false sentence
    also was. So every mappable path is sent to every write operation this application
    has, and the served set is required to be precisely the paths that at least one of
    them accepted.

    ~~125 requests, five routes~~ — **SIX since 2026-08-29.** ``POST
    .../runs/{run_id}/edit`` was absent from a probe whose whole warrant is that it is
    exhaustive. It accepts none of the 25, so no assertion below moved; the enumeration
    is nonetheless the thing this test rests on, and
    :func:`test_the_probe_covers_every_write_route_the_application_publishes` now derives
    it from the served OpenAPI document rather than leaving it to a reader to notice.

    MUTATION: serving ``sorted(NOTE_MAPPABLE_FIELD_PATHS)`` (the old, false claim, made
    machine-readable) turns this RED on 7 paths; serving ``[]`` turns it RED on 18.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    exp = f"/api/experiments/{experiment_id}"
    run = f"{exp}/runs/{run_id}"

    served = client.get(f"{exp}/notes").json()
    mappable = served["mappable_field_paths"]
    assert sorted(mappable) == sorted(routes.NOTE_MAPPABLE_FIELD_PATHS)

    accepted: set[str] = set()
    observed: dict[str, dict[str, int]] = {}
    for path in mappable:
        value = _NUMERIC.get(path, "PROBE-VALUE")
        attempts = {
            "record_answers": client.post(
                f"{exp}/answers",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
            "record_edit": client.post(
                f"{exp}/edit",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
            "run_answers": client.post(
                f"{run}/answers",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, run)},
            ),
            "run_patch": client.patch(
                run,
                json={"confirmed_by_user": True, "fields": {path: value}},
                headers={"If-Match": _etag(client, run)},
            ),
            # THE SIXTH, missing until 2026-08-29. It accepts none of the 25 — which is
            # why nobody noticed, and why an enumeration must be derived rather than
            # remembered.
            "run_edit": client.post(
                f"{run}/edit",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, run)},
            ),
            "run_override": client.post(
                f"{run}/overrides",
                json={
                    "confirmed_by_user": True,
                    "address": ws.field_address(path),
                    "payload": _envelope(value),
                },
                headers={"If-Match": _etag(client, run)},
            ),
        }
        observed[path] = {name: r.status_code for name, r in attempts.items()}
        if any(r.status_code < 300 for r in attempts.values()):
            accepted.add(path)
        # Undo the override so one path's stored value cannot change the next path's
        # answer. The run's own fields are harmless: they are additive and per-path.
        client.post(
            f"{run}/overrides/clear",
            json={"confirmed_by_user": True, "address": ws.field_address(path)},
            headers={"If-Match": _etag(client, run)},
        )

    # THE PROBE'S OWN SHAPE, asserted rather than described: 25 paths x 6 routes. The
    # prose above used to say "five" while claiming to be exhaustive, so the count is
    # now a measurement of what actually ran.
    assert len(observed) == 25
    assert {len(row) for row in observed.values()} == {6}
    assert sum(len(row) for row in observed.values()) == 150

    assert sorted(served["value_writable_field_paths"]) == sorted(accepted), observed

    # BOTH POLARITIES ARE ACTUALLY PRESENT, so the equality above cannot pass vacuously.
    refused = sorted(set(mappable) - accepted)
    assert accepted, observed
    assert refused == [
        "system.configuration.detector_model",
        "system.configuration.monochromator_crystal",
        "system.configuration.n_scans",
        "system.configuration.proposal_id",
        "system.configuration.session_id",
        "system.configuration.spectrometer_geometry",
        "timestamps.created_utc",
    ], observed

    # And the refusal for a path nothing accepts is a TYPED 422 from every route, never
    # a 500 and never a 200 that wrote nothing. This is what makes "no route accepts it"
    # a fact about the contract rather than about one probe's payload.
    for path in refused:
        assert set(observed[path].values()) == {422}, (path, observed[path])


def test_the_record_level_routes_accept_exactly_the_schema_enum_paths(client):
    """~~A record with NO runs can write none of the 25~~ — **NO LONGER TRUE OF ONE OF
    THEM, AND THE TEST IS CORRECTED RATHER THAN DELETED.**

    RENAMED FROM ``test_the_two_write_routes_that_do_accept_these_paths_are_both_a_runs``,
    because the old name asserted the very fact that changed and a name that outlives its
    claim is how the next reader believes it. What it measured was TRUE when it was
    written: both accepting routes were addressed under ``/runs/{run_id}``, so on a record
    with no run every one of the 25 mappable paths was refused ``422
    unrecognized_field``. Its own docstring named the mutation that would turn it RED —
    *"adding either record-level route to the set of routes that accept an official field
    path"* — and that is exactly what has now been done, deliberately.

    WHAT CHANGED AND WHY. ``system.domain`` and ``system.technique`` are declared REQUIRED
    by the official schema on ``system`` and had NO write path on the record at all, which
    made a record carrying a technique and no domain un-exportable and un-repairable. Both
    are closed enums the schema itself publishes, so a scientist choosing one of its
    values is a user confirmation over a bounded set rather than a guess. They are now
    answered at ``POST .../answers`` and corrected at ``POST .../edit``. See
    ``test_system_enum_fields.py``.

    ``system.domain`` is absent from the 25 (it is not in ``EXTRACTOR_FIELD_MAP``), so of
    the paths this test walks exactly ONE moved, and the assertion is now per path rather
    than uniform — a uniform assertion is what let the old one read as a statement about
    all 25 when it had become a statement about 24.

    THE ``not_an_allowed_value`` HALF IS NOT A WEAKENING: ``"PROBE-VALUE"`` is not one of
    the schema's 37 techniques, so the record-level route still writes NOTHING here. Both
    halves of the split are asserted to be non-empty, so neither can pass vacuously.

    MUTATION: adding a record-level route for any OTHER official field path turns this
    RED, exactly as before.
    """
    experiment_id = _experiment(client)
    exp = f"/api/experiments/{experiment_id}"
    record_writable = set(routes._record_enum_fields())
    reached_record_route, refused_by_both = [], []
    for path in sorted(routes.NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT):
        value = _NUMERIC.get(path, "PROBE-VALUE")
        for response in (
            client.post(
                f"{exp}/answers",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
            client.post(
                f"{exp}/edit",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
        ):
            assert response.status_code == 422, (path, response.text)
            if path in record_writable:
                # The route recognised the field and refused the VALUE, which is the
                # distinction this module's own doctrine insists on: a scientist must
                # never be sent looking for a misspelling that is not there.
                assert response.json()["error"] == "not_an_allowed_value", path
                reached_record_route.append(path)
            else:
                assert response.json()["error"] == "unrecognized_field", path
                refused_by_both.append(path)

    assert sorted(set(reached_record_route)) == ["system.technique"]
    assert refused_by_both, "both polarities must be present or the split is vacuous"
    # AND NOTHING WAS WRITTEN BY ANY OF IT, which is what makes the corrected claim as
    # safe as the one it replaces.
    stored = ws.load_experiment(experiment_id, session_id=None)
    assert (stored.draft or {}).get("fields") in (None, {})


#: Every experiment-scoped mutation the OpenAPI document publishes that is NOT one of the
#: six field-path write routes, with the reason it is not. **It exists because the probe
#: above spent months claiming to cover "every write route this application has" while
#: enumerating five of six**, and a hand-written list cannot notice a seventh arriving.
#: A new experiment-scoped mutation therefore fails
#: :func:`test_the_probe_covers_every_write_route_the_application_publishes` until someone
#: decides which side of the line it is on — which is the whole mechanism, not overhead.
_NOT_A_FIELD_PATH_WRITE: dict[str, str] = {
    "PATCH /api/experiments/{experiment_id}": "renames the record; takes `title`, no field path",
    "POST /api/experiments/{experiment_id}/assets": "an asset row, addressed by asset id",
    "PATCH /api/experiments/{experiment_id}/assets/{asset_id}": "an asset row",
    "POST /api/experiments/{experiment_id}/assets/{asset_id}/remove": "an asset row",
    "POST /api/experiments/{experiment_id}/assistant/query": "read-only Q&A",
    "POST /api/experiments/{experiment_id}/audit": "read-only; POST because it takes a body",
    "POST /api/experiments/{experiment_id}/conflicts/resolve": "records a decision, never a value",
    "POST /api/experiments/{experiment_id}/discard": "removes the record",
    "POST /api/experiments/{experiment_id}/export": "reads the draft; writes no field",
    "POST /api/experiments/{experiment_id}/ingestion/csv/preview": "reconciliation-only; applies nothing",
    "POST /api/experiments/{experiment_id}/notes": "captures a note; a note is not a value",
    # THE TWO PROPOSAL ROUTES, AND THE SECOND ONE IS CLASSIFIED HONESTLY RATHER THAN
    # CONVENIENTLY. `create` genuinely writes no value — contract invariant I1 is that
    # creating a proposal leaves `export_draft` and every run's `resolved_run_draft`
    # byte-identical. `review` is the awkward one: on `accept` it DOES write a field
    # value. It is out of the PROBE not because it writes nothing, but because it is
    # not addressed BY a field path — it takes a `proposal_id`, and the value it
    # writes goes through the very writers this probe already covers
    # (`_apply_run_field`, `set_run_override`, `_apply_record_enum_fields`), so
    # probing it would re-measure them through a second door. Saying "records a
    # decision, never a value" here would be the comfortable falsehood this file
    # exists to catch.
    "POST /api/experiments/{experiment_id}/proposals": "creates a proposal; invariant I1 is that it writes no value",
    "POST /api/experiments/{experiment_id}/proposals/{proposal_id}/review": "accept DOES write a value, but through the probed writers and addressed by proposal id, not by field path",
    "POST /api/experiments/{experiment_id}/notes/{note_id}/review": "records a target, not a value",
    "POST /api/experiments/{experiment_id}/runs": "creates a run",
    "POST /api/experiments/{experiment_id}/runs/{run_id}/check": "read-only validation",
    "POST /api/experiments/{experiment_id}/runs/{run_id}/overrides/clear": "removes an override",
    "POST /api/experiments/{experiment_id}/runs/{run_id}/remove": "removes a run",
    "POST /api/experiments/{experiment_id}/submit": "submits what the record already holds",
    "POST /api/experiments/{experiment_id}/transcript": "stores text and proposes; writes no field",
    "POST /api/experiments/{experiment_id}/validate": "read-only validation",
    "POST /api/experiments/{experiment_id}/warnings": "read-only advisory tier",
}

#: The six the probe sends, as they appear in the OpenAPI document.
_PROBED_WRITE_ROUTES: dict[str, str] = {
    "record_answers": "POST /api/experiments/{experiment_id}/answers",
    "record_edit": "POST /api/experiments/{experiment_id}/edit",
    "run_answers": "POST /api/experiments/{experiment_id}/runs/{run_id}/answers",
    "run_patch": "PATCH /api/experiments/{experiment_id}/runs/{run_id}",
    "run_edit": "POST /api/experiments/{experiment_id}/runs/{run_id}/edit",
    "run_override": "POST /api/experiments/{experiment_id}/runs/{run_id}/overrides",
}


def test_the_probe_covers_every_write_route_the_application_publishes(client):
    """The guard the missing sixth route needed, DERIVED from the served document.

    THE DEFECT: ``test_the_served_writable_set_is_what_the_write_routes_actually_do``
    rests entirely on being exhaustive — it is the only thing that makes its 18/7 split
    a fact about the API rather than about one author's memory. It enumerated FIVE
    routes and said "every write route this application has"; ``POST
    .../runs/{run_id}/edit`` was missing, and ``routes._record_enum_fields``' own
    docstring in the same module has listed six all along. Nothing failed, because the
    sixth accepts none of the 25 — the enumeration was wrong and the answer was right.

    So this reads the OpenAPI document, takes every mutating operation under
    ``/api/experiments/{experiment_id}``, and requires each one to be either probed or
    explicitly classified with a reason. **A seventh route cannot arrive silently**: it
    lands in neither set and this goes RED naming it.

    MUTATION: dropping ``run_edit`` from ``_PROBED_WRITE_ROUTES`` — the exact shape of
    the original defect — turns this RED with that operation unclassified.
    """
    spec = client.app.openapi()
    published = {
        f"{method.upper()} {path}"
        for path, item in spec["paths"].items()
        if path.startswith("/api/experiments/{experiment_id}")
        for method in item
        if method in ("post", "put", "patch", "delete")
    }
    probed = set(_PROBED_WRITE_ROUTES.values())

    # Every probed route is real — a typo here would silently shrink the probe.
    assert probed <= published, sorted(probed - published)
    # And every published mutation is on exactly one side of the line.
    unclassified = published - probed - set(_NOT_A_FIELD_PATH_WRITE)
    assert not unclassified, sorted(unclassified)
    stale = set(_NOT_A_FIELD_PATH_WRITE) - published
    assert not stale, sorted(stale)
    # Both sides non-empty and disjoint, so neither list can pass by being everything.
    assert probed and _NOT_A_FIELD_PATH_WRITE
    assert not probed & set(_NOT_A_FIELD_PATH_WRITE)
    assert len(probed) == 6


def test_the_record_level_arm_needs_no_run_at_all(client):
    """~~"Both routes are a run's, so a record with no runs can write none of them
    yet"~~ — the served sentence that was false, measured from the outside.

    THE DEFECT: that sentence ended the ``GET .../notes`` description, and the same
    claim stood in ``UnmappedNotesPanel``'s hint ("a value for this field is entered and
    confirmed **on a run of this record**", for every writable path), in
    ``notes.py``'s module docstring, and in
    ``NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT``'s own comment — which NAMED the
    served sentence as still false and deferred it. It is the mild direction of the
    locked-door defect: a reader told to go and create a run they do not need.

    Nothing here uses a run. The record is created and never given one, and it still has
    none afterwards — which is the assertion that makes this about the RECORD rather
    than about the value happening to land somewhere.

    MUTATION: removing the ``_apply_record_enum_fields`` call from ``post_answers``
    turns the first write RED with ``422 unrecognized_field``.
    """
    experiment_id = _experiment(client, "Record-level, no runs")
    exp = f"/api/experiments/{experiment_id}"
    assert client.get(f"{exp}/runs").json()["total"] == 0

    # A REAL MEMBER OF THE SCHEMA'S OWN ENUM. The earlier probe sends "PROBE-VALUE",
    # which measures the enum rather than the route — the distinction that made the old
    # notes.py paragraph read as "accepts none of them" when it accepts this one.
    answered = client.post(
        f"{exp}/answers",
        json={"confirmed_by_user": True, "answers": {"system.technique": "XAS"}},
        headers={"If-Match": _etag(client, exp)},
    )
    assert answered.status_code == 200, answered.text

    stored = ws.load_experiment(experiment_id, session_id=None)
    assert stored.draft["fields"]["system.technique"]["value"] == "XAS"
    assert stored.runs == []

    corrected = client.post(
        f"{exp}/edit",
        json={"confirmed_by_user": True, "answers": {"system.technique": "XRD"}},
        headers={"If-Match": _etag(client, exp)},
    )
    assert corrected.status_code == 200, corrected.text
    assert ws.load_experiment(experiment_id, session_id=None).draft["fields"][
        "system.technique"
    ]["value"] == "XRD"
    assert client.get(f"{exp}/runs").json()["total"] == 0

    # NEGATIVE CONTROL, so this cannot be read as "the record routes take field paths".
    # They take exactly the schema-enum ones; everything else is still refused.
    other = client.post(
        f"{exp}/answers",
        json={"confirmed_by_user": True, "answers": {"sample.material.name": "CuO"}},
        headers={"If-Match": _etag(client, exp)},
    )
    assert other.status_code == 422, other.text
    assert other.json()["error"] == "unrecognized_field"


def test_the_served_record_writable_set_is_what_the_record_routes_actually_do(client):
    """The new key is MEASURED against the routes, exactly as its wider sibling is.

    A test comparing ``record_writable_field_paths`` to
    ``NOTE_MAPPABLE_PATHS_WRITABLE_ON_THE_RECORD`` would prove only self-consistency —
    the same nothing the false sentence also proved. So every mappable path is sent to
    the record's two operations with a value each will accept if the path is known, and
    the served set must be exactly what came back ``200``.

    THE ENUM MAKES THE PROBE VALUE MATTER, which is the trap the older probe fell into:
    an arbitrary string is refused ``not_an_allowed_value`` by a route that DOES know
    the path, so a probe using one measures the enum and reports "refused".

    MUTATION: serving ``value_writable_field_paths`` for this key (18 paths) turns this
    RED on 17; serving ``[]`` turns it RED on 1.
    """
    experiment_id = _experiment(client, "Record-writable measurement")
    exp = f"/api/experiments/{experiment_id}"
    enums = routes._record_enum_fields()

    accepted, observed = set(), {}
    for path in sorted(routes.NOTE_MAPPABLE_FIELD_PATHS):
        # A value the route would accept IF it knows the path: the schema's own first
        # enum member where there is one, and otherwise the ordinary probe value.
        value = enums[path][0] if path in enums else _NUMERIC.get(path, "PROBE-VALUE")
        responses = {
            "answers": client.post(
                f"{exp}/answers",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
            "edit": client.post(
                f"{exp}/edit",
                json={"confirmed_by_user": True, "answers": {path: value}},
                headers={"If-Match": _etag(client, exp)},
            ),
        }
        observed[path] = {k: r.status_code for k, r in responses.items()}
        if any(r.status_code < 300 for r in responses.values()):
            accepted.add(path)

    served = client.get(f"{exp}/notes").json()
    assert sorted(served["record_writable_field_paths"]) == sorted(accepted), observed
    # BOTH POLARITIES, so the equality cannot pass vacuously in either direction.
    assert accepted == {"system.technique"}, observed
    assert set(routes.NOTE_MAPPABLE_FIELD_PATHS) - accepted, observed
    # AND IT IS A SUBSET OF THE WIDER KEY, which is what stops a client rendering two
    # contradictory sentences about one field.
    assert accepted <= set(served["value_writable_field_paths"])


def test_no_surface_still_says_every_accepting_route_is_a_runs(client):
    """The four copies of the "on a run" claim, pinned so none of them comes back.

    Each is asserted absent as a LIVE claim and present as a struck correction —
    checking only for absence would pass on a file that deleted the paragraph and said
    nothing, which is how a disclosure quietly disappears.

    MUTATION: restoring the sentence in any of the four turns this RED.
    """
    import inspect
    import re
    from pathlib import Path

    import isaac_api.notes as notes

    dead = "so a record with no runs can write none of them yet"

    spec = client.app.openapi()
    listing = spec["paths"]["/api/experiments/{experiment_id}/notes"]["get"]["description"]
    # It survives ONLY inside the sentence that retracts it, and the ORDER is the
    # load-bearing part: a quotation with no retraction beside it reads as the claim.
    assert listing.count(dead) == 1
    assert "AND NOT EVERY ACCEPTING ROUTE IS A RUN'S" in listing
    assert listing.index("used to end") < listing.index(dead)
    assert "`record_writable_field_paths`" in listing
    assert not listing.rstrip().endswith(dead + ".")

    module_text = notes.__doc__ or ""
    stale = "those two routes accept **none of them**"
    # ONCE, AND INSIDE THE STRIKETHROUGH. Asserting mere absence would pass on a file
    # that deleted the paragraph; asserting mere presence would pass on one that
    # restored the claim beside its own retraction, which is the exact accident
    # `test_no_surface_still_promises_...` was extended to catch.
    assert module_text.count(stale) == 1
    struck = re.findall(r"~~(.*?)~~", module_text, re.DOTALL)
    assert sum(stale in block for block in struck) == 1, struck
    assert "CORRECTED 2026-08-29" in module_text
    assert "not_an_allowed_value" in module_text
    assert "NOTE_MAPPABLE_PATHS_WRITABLE_ON_THE_RECORD" in module_text

    constant_doc = Path(inspect.getsourcefile(routes)).read_text()
    assert "THE SERVED SENTENCE STILL SAYS THE OLD THING" in constant_doc
    assert "~~**THE SERVED SENTENCE STILL SAYS THE OLD THING" in constant_doc

    repo_root = Path(__file__).resolve().parents[3]
    panel = repo_root / "apps" / "web" / "src" / "components" / "UnmappedNotesPanel.tsx"
    panel_text = panel.read_text()
    assert panel_text.count("Both write routes are a run's") == 1
    assert "~~\"AND IT SAYS 'ON A RUN'" in panel_text
    assert "recordWritablePaths" in panel_text


def test_the_transcript_route_is_a_second_note_producer(client):
    """~~"nothing in this application creates a `transcript` note, sets a `run_id`, or
    supplies a `candidate_field_path`"~~ — measured false, in FIVE files at once.

    THE DEFECT: `notes.py`'s module docstring, `routes.py`'s section header,
    `provenance.py`'s reachability note, `UnmappedNotesPanel.tsx`'s header and
    `test_provenance.py`'s own docstring all said the note vocabulary had exactly one
    producer. `POST /api/experiments/{id}/transcript` had shipped and does all three of
    the enumerated things. Nothing failed, because no test asserted the absence — the
    claim lived only in prose, which is exactly why it survived five sweeps.

    MUTATION: dropping `run_id=run_id` from `post_transcript`'s `capture_note` call
    turns the run assertion RED; dropping `candidate_field_path=` turns the candidate
    assertion RED.
    """
    experiment_id = _experiment(client, "Transcript producer")
    exp = f"/api/experiments/{experiment_id}"
    run_id = _run(client, experiment_id)

    stored = client.post(
        f"{exp}/transcript",
        json={
            "text": (
                "The beamline was 7-3. The temperature was 300 K. "
                "We re-ran scan three because the beam dropped."
            ),
            "finalized": True,
            "run_id": run_id,
        },
        headers={"If-Match": _etag(client, exp)},
    )
    assert stored.status_code == 200, stored.text

    captured = client.get(f"{exp}/notes").json()["notes"]
    assert len(captured) == 3, captured
    assert {n["source"] for n in captured} == {"transcript"}
    assert {n["run_id"] for n in captured} == {run_id}
    with_candidate = [n for n in captured if n["candidate_field_path"]]
    assert [n["candidate_field_path"] for n in with_candidate] == ["context.temperature_K"]
    # A candidate with no rule is a guess wearing a field name — `notes.py` refuses one,
    # and this proves the route supplies the rule rather than relying on that refusal.
    assert with_candidate[0]["candidate_rule"]
    # BOTH POLARITIES: two of the three proposed nothing, so "supplies a candidate" is
    # not being read as "supplies one for everything".
    assert len(with_candidate) == 1, captured

    # THE THREE SOURCES THAT STILL HAVE NO PRODUCER, which is the half of the old claim
    # that survives and is what the corrected paragraphs now say.
    import isaac_api.notes as notes

    assert {"csv_column", "file_listing_line", "extraction_residue"} < notes.NOTE_SOURCES
    routes_src = __import__("pathlib").Path(routes.__file__).read_text()
    assert "capture_note" in routes_src
    assert routes_src.count("exp.capture_note(") == 2, "a third producer needs the prose updated"


def test_no_surface_still_promises_a_value_can_be_entered_at_every_mapped_path(client):
    """The three copies of the false sentence, pinned so none of them comes back.

    ``notes.py``'s module docstring and ``map_note``'s docstring, and the ``review``
    operation's published description, each carried a promise that was true of 18 paths
    and false for 7. The literal is asserted absent from the SERVED contract and from the
    module, and the correction is asserted present — checking only for absence would pass
    on a file that deleted the whole paragraph and said nothing at all.

    MUTATION: restoring the old sentence in either place turns this RED.
    """
    import inspect

    import isaac_api.notes as notes

    dead = "confirmed-edit path that already exists"
    module_text = notes.__doc__ or ""
    map_text = inspect.getdoc(notes.map_note) or ""

    # It survives ONLY as a quoted correction, never as a live claim. The COUNT is the
    # load-bearing part and was added after a mutation run: asserting the struck
    # quotation is present says nothing about whether a live copy sits beside it, and
    # the first version of this test passed with the old sentence restored one line
    # above the correction that retracts it.
    assert dead not in module_text
    assert map_text.count(dead) == 1
    assert f'~~"through the {dead}"~~' in map_text
    assert "value_writable_field_paths" in module_text
    assert "value_writable_field_paths" in map_text

    spec = client.app.openapi()
    review = spec["paths"]["/api/experiments/{experiment_id}/notes/{note_id}/review"]
    description = review["post"]["description"]
    assert dead not in description
    assert "value_writable_field_paths" in description
    listing = spec["paths"]["/api/experiments/{experiment_id}/notes"]["get"]["description"]
    assert "value_writable_field_paths" in listing


def test_mapping_to_an_unwritable_path_is_still_accepted_and_still_keeps_the_text(client):
    """The honest sentence is a DISCLOSURE, not a new gate.

    Refusing to map a note whose field can hold no value would throw away a scientist's
    own judgement about where their prose belongs in order to avoid having to say one
    awkward thing. The note is mapped, the mapping is recorded, and the verbatim text is
    unchanged.

    MUTATION: gating ``map`` on ``NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT`` turns
    this RED.
    """
    experiment_id = _experiment(client)
    exp = f"/api/experiments/{experiment_id}"
    unwritable = sorted(
        routes.NOTE_MAPPABLE_FIELD_PATHS - routes.NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT
    )[0]
    text = "detector was swapped between scans 2 and 3"

    captured = client.post(
        f"{exp}/notes",
        json={"text": text, "source": "typed_note"},
        headers={"If-Match": _etag(client, exp)},
    )
    assert captured.status_code == 201, captured.text
    note_id = captured.json()["note"]["id"]

    reviewed = client.post(
        f"{exp}/notes/{note_id}/review",
        json={"confirmed_by_user": True, "action": "map", "field_path": unwritable},
        headers={"If-Match": _etag(client, exp)},
    )
    assert reviewed.status_code == 200, reviewed.text
    note = reviewed.json()["note"]
    assert note["state"] == "mapped"
    assert note["mapped_field_path"] == unwritable
    assert note["text"] == text


# --- D3 -----------------------------------------------------------------------


def _set_attribution(client, experiment_id, run_id, payload):
    run = f"/api/experiments/{experiment_id}/runs/{run_id}"
    return client.post(
        f"{run}/overrides",
        json={
            "confirmed_by_user": True,
            "address": ws.block_address("attribution"),
            "payload": payload,
        },
        headers={"If-Match": _etag(client, run)},
    )


def _draft_errors(client, experiment_id, run_id):
    response = client.post(
        f"/api/experiments/{experiment_id}/runs/{run_id}/check", json={}
    )
    assert response.status_code == 200, response.text
    return [e["message"] for e in response.json()["draft"]["errors"]]


def test_a_contributor_set_through_the_only_available_write_path_can_be_exported(client):
    """The measured defect, from the outside: ``200`` accepted, export refused forever.

    On ``origin/main`` this sequence produced
    ``attribution.contributors[0]: "contributor has no evidence; attribution must cite
    its source or be user-confirmed"`` and no ``official_report`` at all — the DRAFT
    validator refused before official validation was reached, and no later request could
    clear it, because ``block:attribution`` is the only contributor write path this build
    offers and it wrote no evidence.

    MUTATION: removing the ``_rewrite_run_attribution_evidence`` call from
    ``post_run_override`` turns this RED with exactly that message.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)

    assert _draft_errors(client, experiment_id, run_id) == []
    response = _set_attribution(
        client,
        experiment_id,
        run_id,
        {"contributors": [{"name": "A Scientist", "role": "operator"}]},
    )
    assert response.status_code == 200, response.text
    assert _draft_errors(client, experiment_id, run_id) == []


def test_the_evidence_recorded_is_the_repositorys_own_user_confirmation_shape(client):
    """Reused, not invented, and it claims nothing about WHO.

    The entry must be the four-key ``models.user_confirmation`` shape ``complete.py``
    writes for ``qc:status`` and each ``series:<id>``, keyed under the natural key
    ``draft_validator`` looks a contributor up by. And it must name no person: this
    application has no trusted authentication boundary (``CLAUDE.md`` §15), which is the
    same reason ``attribution.uploaded_by`` is refused outright.

    MUTATION: keying the entry as ``attribution:<name>`` (dropping the role) turns the
    key assertion RED and the export assertion above RED with it.
    """
    from isaac_records.models import user_confirmation

    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    _set_attribution(
        client,
        experiment_id,
        run_id,
        {"contributors": [{"name": "A Scientist", "role": "operator"}]},
    )

    block_evidence = _stored_run(experiment_id).draft["block_evidence"]
    assert list(block_evidence) == ["attribution:A Scientist|operator"]
    entry = block_evidence["attribution:A Scientist|operator"][0]

    reference = user_confirmation("q", "a", "t")
    assert set(entry) == set(reference)
    assert entry["source_type"] == "user_confirmation"
    assert entry["answer"] == "A Scientist | operator"
    # The question names the OPERATION and says outright that the person is not
    # recorded. The second assertion is the one that carries the claim: "no verified
    # user identity" alone passed a mutation that appended *"but we record the operator
    # as `isaac-operator`"* to the same sentence, because the phrase it looked for was
    # still there in front of the new claim.
    assert "confirmed_by_user: true" in entry["question"]
    assert entry["question"].endswith("deliberately not recorded.")


def test_recording_the_same_contributor_twice_does_not_move_the_run(client, monkeypatch):
    """The operation's published contract promises this, and a timestamp would break it.

    ``POST .../overrides`` documents that recording the same override twice is a no-op
    which does not restamp and does not advance the run's revision. An evidence entry
    carries a timestamp, so an unconditional rewrite would silently make that false.

    **THE CLOCK IS STUBBED, AND THIS TEST WAS GREEN-BY-LUCK WITHOUT IT.** ``_now_iso``
    has one-second resolution and the two requests below run in about a millisecond, so
    an unconditional rewrite produced a byte-identical entry and the guard passed —
    measured, on the mutation it names. The stub returns a DIFFERENT second per call, so
    the only thing that can keep the document stable is the ``_same`` check. Real
    requests are seconds or minutes apart, which is the case the stub represents.

    MUTATION: writing the fresh entry unconditionally (dropping the ``_same`` check in
    ``_rewrite_run_attribution_evidence``) turns this RED.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    payload = {"contributors": [{"name": "A Scientist", "role": "operator"}]}

    ticks = iter(f"2026-08-26T00:00:{n:02d}Z" for n in range(10, 60))
    monkeypatch.setattr(routes, "_now_iso", lambda: next(ticks))

    _set_attribution(client, experiment_id, run_id, payload)
    before = _stored_run(experiment_id).version_token()
    stored_before = _stored_run(experiment_id).draft["block_evidence"]

    assert _set_attribution(client, experiment_id, run_id, payload).status_code == 200
    after_run = _stored_run(experiment_id)
    assert after_run.version_token() == before
    assert after_run.draft["block_evidence"] == stored_before

    # NEGATIVE CONTROL ON THE STUB ITSELF: a genuinely NEW confirmation must take the
    # next tick, or the assertions above would also pass against a frozen clock — which
    # is exactly the accident that made the first version of this test meaningless.
    assert _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "B", "role": "analyst"}]}
    ).status_code == 200
    fresh = _stored_run(experiment_id).draft["block_evidence"]["attribution:B|analyst"][0]
    assert fresh["timestamp"] != stored_before["attribution:A Scientist|operator"][0][
        "timestamp"
    ]


def test_replacing_the_contributors_does_not_leave_the_old_ones_confirmation_behind(client):
    """A confirmation for somebody the record no longer names is a false provenance claim.

    An override REPLACES the whole ``attribution`` block, so a dropped contributor is
    gone from the record. Their evidence entry must go with them, or ``build_sidecar``
    would emit provenance for a person the exported record does not mention — and a
    stale key could later cover a re-added contributor nobody confirmed again.

    MUTATION: merging instead of replacing (dropping the ``attribution:`` prefix filter)
    turns this RED with two keys.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "A", "role": "operator"}]}
    )
    _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "B", "role": "analyst"}]}
    )

    assert list(_stored_run(experiment_id).draft["block_evidence"]) == ["attribution:B|analyst"]


def test_clearing_the_override_takes_its_confirmations_with_it(client):
    """"The run inherits again" has to mean the evidence too.

    MUTATION: removing the ``_rewrite_run_attribution_evidence(run, {})`` call from the
    clear route turns this RED.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)
    run = f"/api/experiments/{experiment_id}/runs/{run_id}"
    _set_attribution(
        client, experiment_id, run_id, {"contributors": [{"name": "A", "role": "operator"}]}
    )

    cleared = client.post(
        f"{run}/overrides/clear",
        json={"confirmed_by_user": True, "address": ws.block_address("attribution")},
        headers={"If-Match": _etag(client, run)},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["cleared"] is True

    assert "block_evidence" not in _stored_run(experiment_id).draft


@pytest.mark.parametrize(
    "contributor, expected",
    [
        ({}, "contributor missing name/role — cannot key its evidence"),
        (
            {"name": ["a"], "role": "b"},
            "contributor has no evidence; attribution must cite its source or be user-confirmed",
        ),
    ],
)
def test_a_contributor_this_build_cannot_key_gets_no_confirmation_and_stays_refused(
    client, contributor, expected
):
    """FAIL-CLOSED, and this is the assertion that keeps the fix from being a hole.

    ``_refuse_override_payload`` applies no contributor SHAPE check — measured, and
    recorded in its own docstring — so both of these are stored with ``200``. Minting an
    evidence entry keyed off a list-valued name would let a contributor the official
    schema cannot hold pass the coverage gate and reach an exported record. So no entry
    is minted and the gate goes on refusing them.

    MUTATION: relaxing the ``isinstance(name, str)`` guard to a truthiness test turns the
    second case RED — it would be silently confirmed and would export.
    """
    experiment_id = _experiment(client)
    run_id = _run(client, experiment_id)

    response = _set_attribution(client, experiment_id, run_id, {"contributors": [contributor]})
    assert response.status_code == 200, response.text

    assert _stored_run(experiment_id).draft.get("block_evidence") in (None, {})
    assert _draft_errors(client, experiment_id, run_id) == [expected]
