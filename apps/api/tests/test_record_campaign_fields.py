"""A scientist could not describe the record they had just created. Measured, then fixed.

**THE DEFECT.** On a record created through this application's own ``POST
/api/experiments`` path, no request could set a facility, a sample or a contributor ON
THE RECORD. Measured over HTTP across every field/block address × every write route:
the twelve facility/sample paths and the two record-level blocks were accepted at
exactly ONE route, ``POST .../runs/{run_id}/overrides`` — and an override records a
RUN's deliberate DIVERGENCE from a value the record holds, which ``routes``' own
``_record_enum_fields`` docstring already says is *"not a way to say what the record
is"*. The consequence was visible on the run view, which reported ``inherited ==
['block:attribution']`` and nothing else, because an address appears in that map only
once the record CARRIES a value at it — which no route could put there.

``system.domain`` and ``system.technique`` had a record-level write path already, and
this slice generalises the machinery that gave them one rather than adding a second: the
same writer, the same evidence shape, the same refusal codes, the same precondition.

**EVERYTHING HERE IS SYNTHETIC.** A tmp workspace, records created through ``POST
/api/experiments``, no database, no network, no file outside the workspace, and no
production-derived content of any kind.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_records.extract.structured import FIELD_MAP as EXTRACTOR_FIELD_MAP
from isaac_records.models import user_confirmation


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _etag(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _experiment(client, title="Campaign-field fixture") -> str:
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _answer(client, experiment_id: str, answers: dict, etag: str | None = None):
    url = f"/api/experiments/{experiment_id}"
    return client.post(
        f"{url}/answers",
        json={"confirmed_by_user": True, "answers": answers},
        headers={"If-Match": etag if etag is not None else _etag(client, url)},
    )


def _edit(client, experiment_id: str, answers: dict, etag: str | None = None):
    url = f"/api/experiments/{experiment_id}"
    return client.post(
        f"{url}/edit",
        json={"confirmed_by_user": True, "answers": answers},
        headers={"If-Match": etag if etag is not None else _etag(client, url)},
    )


def _add_run(client, experiment_id: str, label="Run 1") -> str:
    url = f"/api/experiments/{experiment_id}"
    created = client.post(
        f"{url}/runs",
        json={"confirmed_by_user": True, "label": label},
        headers={"If-Match": _etag(client, url)},
    )
    assert created.status_code == 201, created.text
    return created.json()["run"]["id"]


def _stored(experiment_id: str):
    experiment = ws.load_experiment(experiment_id, session_id=None)
    assert experiment is not None, experiment_id
    return experiment


def _stored_fields(experiment_id: str) -> dict:
    return (_stored(experiment_id).draft or {}).get("fields") or {}


# --- A. the writable set is DERIVED, and the derivation is what excludes things -----


def test_the_record_writable_set_is_derived_not_transcribed():
    """RE-DERIVED from ``EXTRACTOR_FIELD_MAP``, never compared against a literal list.

    A test that listed the members would pass against a hand-written constant, which is
    the exact drift this constant exists to prevent: ``EXPERIMENT_OVERRIDABLE_ADDRESSES``
    and the record-level write surface answer the same question — "does this path belong
    to the record?" — and if they ever answered it from two expressions, a schema or
    field-map change would move one and not the other.
    """
    expected = {
        path
        for path, _coercer in EXTRACTOR_FIELD_MAP.values()
        if ws.field_level(path) == ws.LEVEL_EXPERIMENT
    }
    assert routes.RECORD_WRITABLE_FIELD_PATHS == expected
    assert routes.RECORD_WRITABLE_BLOCK_ADDRESSES == {
        ws.block_address(key)
        for key in (*ws.EXPERIMENT_LEVEL_BLOCKS, *ws.RUN_LEVEL_BLOCKS)
        if ws.block_level(key) == ws.LEVEL_EXPERIMENT
    }
    # THE OVERRIDE SET IS THE SAME EXPRESSION, COMPOSED — not a parallel derivation.
    assert routes.EXPERIMENT_OVERRIDABLE_ADDRESSES == {
        ws.field_address(path) for path in routes.RECORD_WRITABLE_FIELD_PATHS
    } | routes.RECORD_WRITABLE_BLOCK_ADDRESSES


def test_the_unclassified_paths_are_excluded_by_the_derivation_not_by_a_list():
    """The six ``system.configuration.*`` and ``timestamps.created_utc`` stay refused.

    ``CLAUDE.md`` §15 records all six configuration fields as *"unclassified, verified"*
    pending an external answer: whether two runs of one experiment may legitimately
    differ in detector model is a scientific question this repository has no answer to.
    The brief for this slice named them explicitly as must-not-become-writable.

    THE ASSERTION IS ABOUT THE MECHANISM, not only the outcome. It checks that each is
    ``LEVEL_UNCLASSIFIED`` and that the writable set is exactly the ``LEVEL_EXPERIMENT``
    filter over the field map — so the exclusion follows from the classification rather
    than from a special case somebody could delete without noticing.
    """
    unclassified = {
        path
        for path, _coercer in EXTRACTOR_FIELD_MAP.values()
        if ws.field_level(path) == ws.LEVEL_UNCLASSIFIED
    }
    assert unclassified == {
        "system.configuration.detector_model",
        "system.configuration.monochromator_crystal",
        "system.configuration.n_scans",
        "system.configuration.proposal_id",
        "system.configuration.session_id",
        "system.configuration.spectrometer_geometry",
        "timestamps.created_utc",
    }
    assert unclassified.isdisjoint(routes.RECORD_WRITABLE_FIELD_PATHS)
    assert unclassified.isdisjoint(routes._record_writable_fields())


@pytest.mark.parametrize(
    "path",
    [
        "system.configuration.detector_model",
        "system.configuration.n_scans",
        "system.configuration.proposal_id",
        "timestamps.created_utc",
        # NOT IN THE FIELD MAP AT ALL, and each is a field the server owns or a
        # structural identifier a client must never author.
        "attribution.uploaded_by",
        "record_id",
        "isaac_record_version",
        "timestamps.updated_utc",
        "record_type",
        "record_domain",
        "source_type",
    ],
)
def test_the_fields_that_must_stay_unwritable_are_refused_at_both_operations(client, path):
    """Every path the brief named as must-not-be-writable, measured at both routes."""
    experiment_id = _experiment(client)
    for response in (
        _answer(client, experiment_id, {path: "PROBE"}),
        _edit(client, experiment_id, {path: "PROBE"}),
    ):
        assert response.status_code == 422, (path, response.text)
        assert response.json()["error"] == "unrecognized_field", path
    assert _stored_fields(experiment_id) == {}


# --- the cross-language parity check ------------------------------------------------


#: The frontend's own list of the record-level paths it offers a control for. Read as
#: TEXT because the two halves of this contract are written in different languages —
#: this file cannot import TypeScript, and adding a toolchain to let it would be a
#: dependency in exchange for one set comparison. The discipline, and this parser's
#: shape, are ``test_run_api.py``'s for the run workspace.
RECORD_FIELDS_TS = Path(__file__).resolve().parents[3] / "apps/web/src/lib/recordFields.ts"


def _record_fields_ts_paths() -> set[str]:
    """The ``path:`` literals of ``RECORD_FIELDS``, or a loud failure.

    EVERY FAILURE MODE RAISES. A parse that quietly returned an empty set would make
    the parity test below compare ``set() == set()`` on one side of a real divergence
    and pass — a vacuous guard, which this repository has shipped before and which is
    worse than no guard at all because it reads as coverage.
    """
    if not RECORD_FIELDS_TS.is_file():
        raise AssertionError(f"cannot read the frontend field list: {RECORD_FIELDS_TS}")
    text = RECORD_FIELDS_TS.read_text(encoding="utf-8")
    block = re.search(
        r"export const RECORD_FIELDS[^=]*=\s*\[(.*?)\n\]\s*as const;", text, re.S
    )
    if block is None:
        raise AssertionError(
            "could not locate the `export const RECORD_FIELDS = [ ... ] as const;` "
            f"block in {RECORD_FIELDS_TS} — the declaration was renamed or reshaped, so "
            "this parity test is no longer measuring anything and must be repaired, not "
            "skipped"
        )
    paths = set(re.findall(r"""path:\s*['"]([^'"]+)['"]""", block.group(1)))
    if not paths:
        raise AssertionError(
            f"parsed ZERO paths out of RECORD_FIELDS in {RECORD_FIELDS_TS} — refusing "
            "to compare two empty sets and report agreement"
        )
    return paths


def test_the_record_screen_offers_exactly_the_paths_the_server_accepts():
    """THE CHECK NEITHER SUITE CAN MAKE ALONE, and the reason the panel exists.

    ``system.domain`` and ``system.technique`` had a record-level write path for a
    whole session and **no screen anywhere reached it** — every plausible spelling
    (``recordEnum``, ``enum_fields``, ``allowed_values``, …) returned zero hits under
    ``rg -a`` across ``apps/web/src``. The server suite was green because the route
    worked; the frontend suite was green because it knew nothing about the route. This
    is the assertion that would have been red.

    SET EQUALITY IN BOTH DIRECTIONS, deliberately. A path the server accepts and the
    screen omits is an unreachable field — the defect above. A path the screen offers
    and the server refuses is a control whose only outcome is a 422. Both are failures.

    THE SERVER SIDE IS THE UNION OF THE TWO KEY SETS THE ROUTES CONSULT, derived rather
    than listed: the experiment-level half of the extractor/level split, plus the paths
    the schema closes with an enum and declares required (which is what contributes
    ``system.domain``, absent from ``EXTRACTOR_FIELD_MAP``).
    """
    offered = _record_fields_ts_paths()
    accepted = set(routes._record_writable_fields())
    assert offered == accepted, (
        "the Record Description panel and the record-level write routes disagree — "
        f"offered only: {sorted(offered - accepted)}, "
        f"accepted only: {sorted(accepted - offered)}"
    )


def test_the_frontend_transcribes_no_schema_enum():
    """The 37 techniques are READ, never copied into TypeScript. Asserted, not trusted.

    A second copy of the schema's vocabulary in the client would be free to drift from
    the document ``CLAUDE.md`` §1 makes the authority, and would go stale silently on a
    schema refresh — the client would then offer a value the server refuses, or withhold
    one it accepts, with both suites green.

    THE ASSERTION IS OVER THE SCHEMA'S OWN VALUES, so it cannot be satisfied by renaming
    a constant: every value of every enum this panel offers is checked absent from the
    file, and the panel's own module is checked to contain the reader that fetches them.
    """
    text = RECORD_FIELDS_TS.read_text(encoding="utf-8")
    known = routes._record_writable_fields()
    checked = 0
    for path, spec in known.items():
        for value in spec.enum or ():
            checked += 1
            assert f'"{value}"' not in text and f"'{value}'" not in text, (path, value)
    assert checked >= 37, f"expected at least the 37 techniques to be checked, saw {checked}"
    # AND THE READER IS THERE, so this is not passing because the panel offers nothing.
    assert "recordFieldFacts" in text and "contributorRoleOptions" in text


# --- 1/2. one writer, one envelope, one evidence shape -----------------------------


def test_the_new_write_paths_build_no_second_envelope():
    """THE NEGATIVE CONTROL THE BRIEF ASKED FOR, over the source of the new functions.

    The whole safety argument for this slice is that a record-level value is written by
    ``_apply_run_field`` — the writer that already mints ``complete.py``'s four-key
    ``user_confirmation``, carries prior evidence and the envelope's ``unit`` forward,
    and is idempotent. A second envelope builder anywhere in the new code would be a
    second definition of "what a confirmed field looks like", free to drift from the one
    the exporter and the draft validator read.

    So the new functions are asserted to contain neither a literal ``"status":
    "verified"`` nor a direct ``user_confirmation(`` call. ``_apply_record_blocks`` is
    the one that mints block evidence, and it does so through
    ``_attribution_confirmations`` — the helper the override route already uses — rather
    than by calling the model helper itself.

    IT IS A SOURCE CHECK AND CLAIMS ONLY WHAT A SOURCE CHECK CAN: a function could
    always reach a second builder through a further call. What it does close is the
    cheap and likely regression — someone adding an envelope inline because it looked
    simpler than threading the writer.
    """
    for function in (
        routes._record_field_answers,
        routes._record_block_answers,
        routes._apply_record_fields,
        routes._apply_record_blocks,
        routes._refuse_a_record_value_the_record_cannot_hold,
        routes._refuse_a_record_block_the_record_cannot_hold,
    ):
        source = inspect.getsource(function)
        body = source.split('"""', 2)[-1]  # skip the docstring, which quotes both
        assert '"status": "verified"' not in body, function.__name__
        assert "user_confirmation(" not in body, function.__name__


def test_a_facility_value_lands_with_the_exact_four_key_user_confirmation(client):
    """The stored envelope is the one ``complete.py`` writes, key for key.

    Not "an evidence entry exists" — the SHAPE, compared against
    ``isaac_records.models.user_confirmation`` itself, so a hand-rolled entry with an
    extra or missing key fails here rather than at an export gate.
    """
    experiment_id = _experiment(client)
    assert _answer(
        client, experiment_id, {"system.facility.beamline": "BL-SYNTHETIC-1"}
    ).status_code == 200

    envelope = _stored_fields(experiment_id)["system.facility.beamline"]
    assert envelope["value"] == "BL-SYNTHETIC-1"
    assert envelope["status"] == "verified"
    assert len(envelope["evidence"]) == 1
    entry = envelope["evidence"][0]
    assert set(entry) == set(user_confirmation("q", "a", "t"))
    assert entry["source_type"] == "user_confirmation"
    assert entry["answer"] == "BL-SYNTHETIC-1"
    # THE QUESTION IS THE RECORD'S, NOT THE RUN'S. The two say different true things,
    # and the run's wording ("on this run") would be false on a record-level field.
    assert entry["question"] == "Value for system.facility.beamline on this record?"
    assert entry["question"] != routes._run_field_question("system.facility.beamline")
    assert entry["timestamp"]


def test_nothing_is_derived_defaulted_or_inferred_from_a_sibling(client):
    """Give ONE facility field and the other four stay missing. §5, made checkable.

    An application that filled in ``system.facility.facility_name`` because a beamline
    was named would be asserting a facility catalogue that exists nowhere in this
    repository. It stays absent, and the record stays as incomplete as it truthfully is.
    """
    experiment_id = _experiment(client)
    assert _answer(
        client, experiment_id, {"system.facility.beamline": "BL-SYNTHETIC-1"}
    ).status_code == 200
    assert set(_stored_fields(experiment_id)) == {"system.facility.beamline"}


def test_resubmitting_the_identical_value_moves_no_revision(client):
    """The writer's idempotence, inherited unchanged. A retry is safe."""
    experiment_id = _experiment(client)
    assert _answer(
        client, experiment_id, {"sample.material.name": "Synthetic Cu foil"}
    ).status_code == 200
    first = _stored(experiment_id)

    again = _answer(client, experiment_id, {"sample.material.name": "Synthetic Cu foil"})
    assert again.status_code == 200, again.text
    assert again.json()["invalidation"]["changed"] is False
    second = _stored(experiment_id)
    assert second.rev == first.rev
    assert second.draft == first.draft


def test_a_correction_appends_a_second_confirmation_and_keeps_the_first(client):
    """Provenance is added to, never overwritten — the writer's existing discipline."""
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"sample.sample_form": "pellet"}).status_code == 200
    assert _edit(client, experiment_id, {"sample.sample_form": "powder"}).status_code == 200
    evidence = _stored_fields(experiment_id)["sample.sample_form"]["evidence"]
    assert [e["answer"] for e in evidence] == ["pellet", "powder"]
    assert all(e["source_type"] == "user_confirmation" for e in evidence)


# --- 3. type validation, read from the schema rather than transcribed ---------------


@pytest.mark.parametrize(
    "path,value",
    [
        ("sample.material.name", 7),
        ("sample.material.formula", ["Cu", "O"]),
        ("system.facility.site", {"name": "SSRL"}),
        ("sample.sample_form", True),
        # `system.technique` IS DELIBERATELY ABSENT. It is enum-closed, so a wrong-typed
        # value there is refused by `not_an_allowed_value` first — which is strictly more
        # useful, because it tells the caller WHAT to send rather than only what not to.
        # Asserted as its own case in `test_an_off_enum_value_...`.
    ],
)
def test_a_wrong_typed_value_is_refused_and_names_the_declared_type(client, path, value):
    """``422 invalid_field_value`` with ``expected_types`` read from the vendored schema.

    ``expected_types`` is a MAP rather than one string, for the reason
    ``not_an_allowed_value``'s ``allowed`` is: a body may name several fields refused for
    different reasons, and a single prose sentence naming one cause was measured in this
    module being served verbatim about a key it did not describe.

    ``True`` at a ``string`` path is included deliberately: ``bool`` is a subclass of
    ``int``, so a naive numeric check would let it through at a ``number`` path. Here the
    path is a string, and the assertion is that the type gate reads the schema rather
    than accepting anything Python considers truthy.
    """
    experiment_id = _experiment(client)
    response = _answer(client, experiment_id, {path: value})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_field_value"
    assert body["experiment_id"] == experiment_id
    assert body["keys"] == [path] and body["key"] == path
    # THE DECLARED TYPE IS THE SCHEMA'S OWN WORD, not a word this test chose.
    assert body["expected_types"] == {
        path: routes._record_writable_fields()[path].declared_type
    }
    assert _stored_fields(experiment_id) == {}
    assert _stored(experiment_id).rev == 0


def test_a_number_is_accepted_where_the_schema_declares_no_type(client):
    """The three OPEN-namespace paths carry no declared type, and none is invented.

    ``sample.composition`` declares no ``properties`` at all — *"Open by design"*, in the
    schema's own description — and ``sample.geometry`` declares ``properties`` that do not
    include ``pellet_diameter_mm``. ``CLAUDE.md`` §1 makes the schema the authority and §5
    forbids inventing what it declined to say, so no type is enforced at those three and
    the official validator remains the authority on the value.
    """
    experiment_id = _experiment(client)
    for path in (
        "sample.composition.CuO2_mass_fraction",
        "sample.geometry.pellet_diameter_mm",
    ):
        assert routes._record_writable_fields()[path].declared_type is None
    assert _answer(
        client,
        experiment_id,
        {
            "sample.composition.CuO2_mass_fraction": 0.5,
            "sample.geometry.pellet_diameter_mm": 5,
        },
    ).status_code == 200
    stored = _stored_fields(experiment_id)
    assert stored["sample.composition.CuO2_mass_fraction"]["value"] == 0.5
    assert stored["sample.geometry.pellet_diameter_mm"]["value"] == 5


def test_an_off_enum_value_is_refused_with_the_schemas_own_allowed_list(client):
    """The enum gate still fires, and only where the schema declares an enum.

    The twelve facility/sample paths carry no enum, so they pass this gate untouched —
    which is the half that had to be got right when the refusal's input widened: the old
    ``value not in known.get(path, ())`` would have refused EVERY value at every non-enum
    path once the key set grew.
    """
    experiment_id = _experiment(client)
    response = _answer(client, experiment_id, {"system.technique": "NOT-A-TECHNIQUE"})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "not_an_allowed_value"
    assert body["keys"] == ["system.technique"]
    assert body["allowed"]["system.technique"] == list(
        routes._record_writable_fields()["system.technique"].enum
    )
    # A non-enum path with a well-typed value is NOT caught by this gate.
    assert _answer(
        client, experiment_id, {"sample.material.provenance": "anything at all"}
    ).status_code == 200


def test_an_oversized_value_is_refused_without_naming_a_type(client):
    """Storability and type are two conditions under one code, told apart by the body.

    A key present in ``expected_types`` was refused for its type; a key absent from it
    could not be stored at all. The message says exactly that and asserts nothing else,
    so no sentence claims a per-key cause it cannot know.
    """
    experiment_id = _experiment(client)
    response = _answer(
        client, experiment_id, {"sample.material.name": "x" * (64 * 1024 + 1)}
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_field_value"
    assert body["keys"] == ["sample.material.name"]
    assert body["expected_types"] == {}
    assert _stored_fields(experiment_id) == {}


# --- 4. blocks ---------------------------------------------------------------------


def test_a_contributor_set_on_the_record_earns_the_evidence_that_lets_it_export(client):
    """``block:attribution`` writes the block AND the ``block_evidence`` it earned.

    THE DEFECT THIS MIRRORS is the one the override route already fixed: the block was
    stored with no ``block_evidence``, and ``draft_validator``'s
    ``attribution:<name>|<role>`` coverage rule then refused the export — for a
    contributor whose only write path was that route. The record-level write must not
    reintroduce it one level up.

    NO EVIDENCE RULE IS WEAKENED. ``draft_validator`` is truth-path code and is
    untouched; the write records the confirmation it actually has instead of discarding
    it and then failing a gate for its absence.
    """
    experiment_id = _experiment(client)
    payload = {"contributors": [{"name": "A. Synthetic", "role": "performed_measurement"}]}
    assert _answer(client, experiment_id, {"block:attribution": payload}).status_code == 200

    draft = _stored(experiment_id).draft
    assert draft["attribution"] == payload
    entries = draft["block_evidence"]["attribution:A. Synthetic|performed_measurement"]
    assert len(entries) == 1
    assert set(entries[0]) == set(user_confirmation("q", "a", "t"))
    assert entries[0]["source_type"] == "user_confirmation"
    assert entries[0]["answer"] == "A. Synthetic | performed_measurement"
    # THE QUESTION NAMES THE ACT THAT ACTUALLY HAPPENED. The override route's wording
    # says "this run" and names the overrides operation; both would be false here, and
    # stored evidence describing an act nobody performed is fabricated provenance.
    assert "this record" in entries[0]["question"]
    assert "/overrides" not in entries[0]["question"]
    # AND IT NAMES NO PERSON: this application receives no verified user identity.
    assert "A. Synthetic" not in entries[0]["question"]


def test_uploaded_by_stays_refused_inside_an_attribution_payload(client):
    """The one field no client may author, planted directly. Measured, not assumed.

    The schema declares ``attribution.uploaded_by`` stamped from an authenticated
    identity, and ``CLAUDE.md`` §11 records that no verifier in this build mints the
    ``trust_basis`` that would license one. The refusal is the deterministic draft
    validator's own — this route holds a reference to the rule, not a copy.
    """
    experiment_id = _experiment(client)
    response = _answer(
        client,
        experiment_id,
        {"block:attribution": {"uploaded_by": "someone", "contributors": []}},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_block_payload"
    assert body["experiment_id"] == experiment_id
    assert body["address"] == "block:attribution"
    assert body["findings"], "the validator's own words must travel with the refusal"
    # NOTHING WAS WRITTEN: the block is still the empty scaffold `POST /api/experiments`
    # seeds, and the revision did not move. Asserted as "unchanged" rather than "absent",
    # because a created record already carries `attribution: {"contributors": []}` — the
    # very fact `_block_payload_carries_nothing` exists for.
    assert (_stored(experiment_id).draft or {}).get("attribution") == {"contributors": []}
    assert _stored(experiment_id).rev == 0


@pytest.mark.parametrize(
    "address,payload",
    [
        ("block:attribution", ["not", "an", "object"]),
        ("block:attribution", "a string"),
        ("block:tags", {"not": "an array"}),
        ("block:tags", "a string"),
    ],
)
def test_a_block_payload_of_the_wrong_type_is_refused(client, address, payload):
    """``422 invalid_block_payload`` naming the type the official schema declares."""
    experiment_id = _experiment(client)
    response = _answer(client, experiment_id, {address: payload})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_block_payload"
    assert body["address"] == address
    assert body["expected_type"] in ("object", "array")
    assert body["message"].count("override") == 0, (
        "a record-level write is not an override, and a refusal that calls it one "
        "describes the wrong act on the screen a scientist reads to fix it"
    )


def test_the_seeded_empty_attribution_block_is_open_not_already_answered(client):
    """A created record ships with ``attribution: {"contributors": []}``. Measured.

    Treating key presence as "already answered" made the FIRST contributor unaddable
    through the answering operation on every record this application creates: ``/answers``
    refused ``already_answered`` and pointed at ``/edit``, the operation documented to
    CORRECT a value the record holds. So an empty scaffold is OPEN — answered at
    ``/answers``, refused at ``/edit`` with ``not_yet_answered`` — and it stops being open
    the moment it carries a contributor.

    THE PREDICATE IS STRUCTURAL AND GENERIC, not a rule spelled per block: see
    ``_block_payload_carries_nothing``. Both directions are asserted here so it cannot be
    weakened to "the key is absent" or strengthened to "the payload is falsy".
    """
    experiment_id = _experiment(client)
    assert _stored(experiment_id).draft["attribution"] == {"contributors": []}
    assert routes._block_payload_carries_nothing({"contributors": []}) is True
    assert routes._block_payload_carries_nothing({"contributors": [{}]}) is False

    # OPEN: `/edit` says so, and `/answers` accepts the first contributor.
    refused = _edit(client, experiment_id, {"block:attribution": {"contributors": []}})
    assert refused.status_code == 422 and refused.json()["error"] == "not_yet_answered"
    first = {"contributors": [{"name": "A. Synthetic", "role": "performed_measurement"}]}
    assert _answer(client, experiment_id, {"block:attribution": first}).status_code == 200

    # AND NOW CLOSED: a DIFFERENT value at `/answers` is refused, `/edit` takes it.
    second = {"contributors": [{"name": "B. Synthetic", "role": "performed_analysis"}]}
    again = _answer(client, experiment_id, {"block:attribution": second})
    assert again.status_code == 422, again.text
    assert again.json()["error"] == "already_answered"
    assert _edit(client, experiment_id, {"block:attribution": second}).status_code == 200
    assert _stored(experiment_id).draft["attribution"] == second
    # THE SUPERSEDED CONTRIBUTOR'S CONFIRMATION GOES WITH THEM. Leaving it behind would
    # put a provenance entry for a person the record no longer names into the sidecar.
    assert set(_stored(experiment_id).draft["block_evidence"]) == {
        "attribution:B. Synthetic|performed_analysis"
    }


def test_a_block_payload_too_large_to_store_is_refused_with_the_shared_code(client):
    """``unrepresentable_value`` — the override route's gate 1, reached from here.

    IT IS THE SAME CODE THE OVERRIDE ROUTE SERVES, because it is the same gate applied
    to the same store, and a second code for one condition is how a client ends up
    branching on prose. It is declared in the record operations' published `422` in the
    same change that made them able to raise it — the gap `_R_CORRECTION_REFUSED`'s own
    note records ("the record's 422 enumerated three refusals while the route performed
    four").
    """
    experiment_id = _experiment(client)
    response = _answer(client, experiment_id, {"block:tags": ["x" * (64 * 1024 + 1)]})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrepresentable_value"
    assert body["experiment_id"] == experiment_id
    assert body["address"] == "block:tags"
    assert "override" not in body["message"]
    assert (_stored(experiment_id).draft or {}).get("tags") is None


def test_the_published_contract_names_every_code_these_routes_can_now_raise(client):
    """The refusals are DESCRIBED where a machine client reads them, not only performed.

    This module has been caught twice with a route performing a refusal its published
    `422` did not enumerate. Asserted over the SERVED document, and asserted ABSENT from
    the run-level operations' block, which cannot raise any of them — a contract naming
    a code its operation cannot emit sends a caller with a correctly spelled key to hunt
    for a misspelling.
    """
    doc = client.app.openapi()

    def refusal(path: str) -> str:
        return doc["paths"][path]["post"]["responses"]["422"]["description"]

    record = "/api/experiments/{experiment_id}"
    run = "/api/experiments/{experiment_id}/runs/{run_id}"
    for code in ("invalid_block_payload", "unrepresentable_value", "block:attribution"):
        assert code in refusal(f"{record}/answers"), code
        assert code in refusal(f"{record}/edit"), code
        assert code not in refusal(f"{run}/answers"), code
        assert code not in refusal(f"{run}/edit"), code


def test_tags_are_written_and_inherited_and_mint_no_evidence(client):
    """``tags`` is exempt from block-evidence coverage BY DESIGN; none is invented."""
    experiment_id = _experiment(client)
    assert _answer(
        client, experiment_id, {"block:tags": ["synthetic-campaign", "xanes"]}
    ).status_code == 200
    draft = _stored(experiment_id).draft
    assert draft["tags"] == ["synthetic-campaign", "xanes"]
    assert "block_evidence" not in draft


# --- 5. the precondition -----------------------------------------------------------


def test_the_record_precondition_is_unchanged_for_the_new_keys(client):
    """428 absent, 412 stale, on both operations, with nothing written."""
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    assert _answer(client, experiment_id, {"sample.material.name": "Cu"}).status_code == 200
    before = _stored_fields(experiment_id)

    for operation, answers in (
        ("answers", {"system.facility.site": "SSRL-SYNTHETIC"}),
        ("edit", {"sample.material.name": "Fe"}),
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
    assert _stored_fields(experiment_id) == before


def test_a_body_the_route_cannot_read_is_a_422_even_with_a_stale_validator(client):
    """RESOLVED BEFORE THE PRECONDITION — the ordering the brief asked for, measured.

    A screen that reads only the body and the vendored schema answers the same thing
    whether or not the caller's token is current, so answering ``412`` first would send
    a compliant client to refresh and rebuild a request that is still unreadable: the
    loop that cannot terminate, which is why
    ``_refuse_answers_that_are_not_an_object`` already sits above the precondition.

    **THIS IS A DELIBERATE BEHAVIOUR CHANGE FOR ``not_an_allowed_value``**, which used to
    run after the precondition and answered ``412`` in this state. It is stated here
    rather than left to be discovered.

    The STATE screens (``already_answered``) stay BELOW the precondition, which the next
    test measures — answering about the record's current contents to a caller whose token
    does not match them would describe a record they have not seen.
    """
    experiment_id = _experiment(client)
    url = f"/api/experiments/{experiment_id}"
    stale = '"0000000000000000.1"'
    for answers, expected in (
        ({"system.technique": "NOT-A-TECHNIQUE"}, "not_an_allowed_value"),
        ({"sample.material.name": 7}, "invalid_field_value"),
        ({"block:tags": "not an array"}, "invalid_block_payload"),
    ):
        response = client.post(
            f"{url}/answers",
            json={"confirmed_by_user": True, "answers": answers},
            headers={"If-Match": stale},
        )
        assert response.status_code == 422, (answers, response.text)
        assert response.json()["error"] == expected, answers
    assert _stored_fields(experiment_id) == {}


def test_a_state_refusal_stays_below_the_precondition(client):
    """``already_answered`` is about the RECORD's contents, so a stale token wins.

    The other half of the split above, asserted so the two cannot quietly merge: a
    caller holding a stale validator is told their token is stale, not told about a
    stored value they have not seen.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"sample.material.name": "Cu"}).status_code == 200
    response = client.post(
        f"/api/experiments/{experiment_id}/answers",
        json={"confirmed_by_user": True, "answers": {"sample.material.name": "Fe"}},
        headers={"If-Match": '"0000000000000000.1"'},
    )
    assert response.status_code == 412, response.text


def test_answering_a_confirmed_field_with_a_different_value_is_refused(client):
    """``/answers`` answers what is open; ``/edit`` corrects what is answered."""
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"sample.material.name": "Cu"}).status_code == 200
    rev_before = _stored(experiment_id).rev

    response = _answer(client, experiment_id, {"sample.material.name": "Fe"})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "already_answered"
    assert body["keys"] == ["sample.material.name"]
    assert body["answer_at"] == "POST /api/experiments/{experiment_id}/edit"
    assert _stored_fields(experiment_id)["sample.material.name"]["value"] == "Cu"
    assert _stored(experiment_id).rev == rev_before

    assert _edit(client, experiment_id, {"sample.material.name": "Fe"}).status_code == 200
    assert _stored_fields(experiment_id)["sample.material.name"]["value"] == "Fe"


def test_correcting_a_block_the_record_never_held_is_refused_and_redirected(client):
    """The block half of the same split, which the field half alone would not cover."""
    experiment_id = _experiment(client)
    response = _edit(client, experiment_id, {"block:tags": ["x"]})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "not_yet_answered"
    assert body["keys"] == ["block:tags"]
    assert body["answer_at"] == "POST /api/experiments/{experiment_id}/answers"
    assert (_stored(experiment_id).draft or {}).get("tags") is None


# --- 6. inheritance is untouched ---------------------------------------------------


def test_a_record_level_value_is_inherited_by_every_run_by_reference(client):
    """Set once on the record, resolved by each run — never copied down.

    This is the mechanism that makes the record the right level, and it is the reason
    the defect mattered: before, these addresses appeared in a run's ``inherited`` map
    only once the record carried a value, which no route could put there.
    """
    experiment_id = _experiment(client)
    assert _answer(
        client, experiment_id, {"system.facility.beamline": "BL-SYNTHETIC-1"}
    ).status_code == 200
    run_id = _add_run(client, experiment_id)

    run = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}").json()["run"]
    inherited = run["inherited"]["field:system.facility.beamline"]
    assert inherited["payload"]["value"] == "BL-SYNTHETIC-1"
    assert inherited["state"] == "inherited"
    # NOT COPIED: the run's own field map does not carry it.
    assert "system.facility.beamline" not in (run.get("fields") or {})

    # AND IT FOLLOWS A LATER RECORD-LEVEL CORRECTION, which is what "by reference" means.
    assert _edit(
        client, experiment_id, {"system.facility.beamline": "BL-SYNTHETIC-2"}
    ).status_code == 200
    run = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}").json()["run"]
    assert (
        run["inherited"]["field:system.facility.beamline"]["payload"]["value"]
        == "BL-SYNTHETIC-2"
    )


def test_an_existing_run_override_survives_a_record_level_write_and_keeps_winning(client):
    """A run's recorded divergence is not overwritten by the record it diverged from.

    Both directions matter and both are asserted: the override still wins after the
    record-level write, and CLEARING it falls back to the record's CURRENT value rather
    than to the one the override displaced.
    """
    experiment_id = _experiment(client)
    assert _answer(client, experiment_id, {"sample.material.name": "Cu"}).status_code == 200
    run_id = _add_run(client, experiment_id)
    run_url = f"/api/experiments/{experiment_id}/runs/{run_id}"

    from isaac_records.models import field_value

    override_payload = field_value(
        "Fe",
        status="verified",
        evidence=[user_confirmation("probe", "Fe", "2026-08-30T00:00:00Z")],
    )
    recorded = client.post(
        f"{run_url}/overrides",
        json={
            "confirmed_by_user": True,
            "address": "field:sample.material.name",
            "payload": override_payload,
        },
        headers={"If-Match": _etag(client, run_url)},
    )
    assert recorded.status_code == 200, recorded.text

    # THE RECORD-LEVEL CORRECTION LANDS, and the run keeps its own value.
    assert _edit(client, experiment_id, {"sample.material.name": "Ni"}).status_code == 200
    run = client.get(run_url).json()["run"]
    resolved = run["inherited"]["field:sample.material.name"]
    assert resolved["state"] == "overridden"
    assert resolved["payload"]["value"] == "Fe"

    # REVERT: clearing the override falls back to the record's CURRENT value.
    cleared = client.post(
        f"{run_url}/overrides/clear",
        json={"confirmed_by_user": True, "address": "field:sample.material.name"},
        headers={"If-Match": _etag(client, run_url)},
    )
    assert cleared.status_code == 200, cleared.text
    run = client.get(run_url).json()["run"]
    resolved = run["inherited"]["field:sample.material.name"]
    assert resolved["state"] == "inherited"
    assert resolved["payload"]["value"] == "Ni"


def test_the_run_operations_still_refuse_every_record_level_key(client):
    """These are the RECORD's. A run INHERITS them and does not own them.

    The level split is followed rather than widened: writing a record-level value on a
    run would put the same value in two places, which is the rule ``patch_run`` already
    enforces. ``POST .../overrides`` is deliberately not asserted here — recording a
    run's DIVERGENCE is a different act and this slice does not change that route.
    """
    experiment_id = _experiment(client)
    run_id = _add_run(client, experiment_id)
    run_url = f"/api/experiments/{experiment_id}/runs/{run_id}"
    for key in ("sample.material.name", "system.facility.beamline", "block:tags"):
        for response in (
            client.patch(
                run_url,
                json={"confirmed_by_user": True, "fields": {key: "PROBE"}},
                headers={"If-Match": _etag(client, run_url)},
            ),
            client.post(
                f"{run_url}/answers",
                json={"confirmed_by_user": True, "answers": {key: "PROBE"}},
                headers={"If-Match": _etag(client, run_url)},
            ),
            client.post(
                f"{run_url}/edit",
                json={"confirmed_by_user": True, "answers": {key: "PROBE"}},
                headers={"If-Match": _etag(client, run_url)},
            ),
        ):
            assert response.status_code == 422, (key, response.text)
            assert response.json()["error"] == "unrecognized_field", key


# --- 7. a submitted record ---------------------------------------------------------


def test_the_new_keys_get_exactly_the_submitted_record_treatment_the_old_ones_get():
    """THE HONEST ANSWER: these two operations apply NO submitted-record gate at all.

    The brief asked that a submitted record refuse these writes *"exactly as it refuses
    the existing ones"*, and the measurement is that it refuses neither: nothing in
    ``post_answers`` or ``post_edit`` consults submission state, so a record that has
    been submitted accepts a ``series`` answer and a facility name on identical terms.
    Adding a gate for the new keys alone would be inventing a rule the operation does not
    have, applied to half its key set — which is how two halves of one contract drift
    apart.

    This is a SOURCE-STRUCTURE assertion and claims only what one can: that neither
    handler names the submission store, so no branch can treat the two key sets
    differently. A submitted record cannot be produced in this environment at all —
    ``POST .../submit`` requires durable PostgreSQL storage and answers ``503`` without
    it — so an over-HTTP proof is not available here and is not claimed.
    """
    for handler in (routes.post_answers, routes.post_edit):
        source = inspect.getsource(handler)
        for marker in ("submission_store", "submissions.", "revision_history"):
            assert marker not in source, (handler.__name__, marker)


# --- the whole point: a record can now be described -------------------------------


def test_a_scientist_can_describe_a_created_record_end_to_end(client):
    """The defect, stated as the behaviour that was missing and now works.

    Create a record through the product's own path and then set the facility, the
    sample, the technique, the domain, a contributor and a tag — all on the RECORD,
    with no run in existence. Every value is read back from the stored document, and
    each run added afterwards inherits all of them.
    """
    experiment_id = _experiment(client)
    campaign = {
        "system.domain": "experimental",
        "system.technique": "XAS",
        "system.facility.site": "SSRL-SYNTHETIC",
        "system.facility.facility_name": "Synthetic Light Source",
        "system.facility.organization": "SYNTHETIC-ORG",
        "system.facility.beamline": "BL-SYNTHETIC-1",
        "system.facility.endstation": "ES-1",
        "sample.material.name": "Synthetic Cu foil",
        "sample.material.formula": "Cu",
        "sample.material.provenance": "synthetic fixture",
        "sample.sample_form": "foil",
        "sample.composition.CuO2_mass_fraction": 0.5,
        "sample.composition.sucrose_mass_fraction": 0.5,
        "sample.geometry.pellet_diameter_mm": 5,
        "block:attribution": {"contributors": [{"name": "A. Synthetic", "role": "performed_measurement"}]},
        "block:tags": ["synthetic-campaign"],
    }
    response = _answer(client, experiment_id, campaign)
    assert response.status_code == 200, response.text
    assert sorted(response.json()["invalidation"]["changed_fields"]) == sorted(campaign)

    draft = _stored(experiment_id).draft
    for path, value in campaign.items():
        if path.startswith("block:"):
            assert draft[ws.parse_address(path)[1]] == value, path
        else:
            assert draft["fields"][path]["value"] == value, path

    run_id = _add_run(client, experiment_id)
    inherited = client.get(
        f"/api/experiments/{experiment_id}/runs/{run_id}"
    ).json()["run"]["inherited"]
    for path in campaign:
        address = path if path.startswith("block:") else ws.field_address(path)
        assert address in inherited, address
        assert inherited[address]["state"] == "inherited", address
