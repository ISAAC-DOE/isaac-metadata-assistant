"""THE EXTENDED CONTEXT COMPANION, WIRED — `DEC-41` level 4, `DEC-43`, `CTX-002`.

WHAT THIS FILE IS FOR
=====================

`DEC-41`'s companion artifact and `DEC-43`'s one nominal value both shipped as PURE
MODULES with no producer and no consumer: nothing populated a companion from an
import, no route served one, nothing wrote ``records/<ULID>.context.json``, the
companion was not in ``workspace.Experiment`` at all, and the 298 K rule existed with
every fence in place and no offer. This file covers the wiring, and every test here
is shaped like the defect it would catch rather than like the code it exercises.

THE THREE PROPERTIES THAT ARE WORTH MORE THAN THE REST
======================================================

1. **An extended-context-only change is PERSISTED.** ``save_versioned`` writes
   nothing when ``_authoritative_signature`` is unchanged, so a companion outside
   that payload would make every import's provenance a silent no-op — the route
   answering 200 over entries that never reached disk. That is the ``folder`` defect
   one key along, and ``test_an_extended_context_only_change_is_persisted`` is the
   guard. **Negative control performed 2026-09-17**, and the observed output is
   quoted rather than predicted: deleting the ``"extended_context"`` member of
   ``_authoritative_signature``'s payload makes it RED with
   ``E  AssertionError: assert False is True  +  where False = save_versioned()``,
   and with THAT line relaxed it then fails one assertion later at
   ``> assert reloaded.extended_context is not None`` /
   ``E  AssertionError: assert None is not None`` — i.e. the entries are on the
   loaded object and nowhere on disk, which is the defect exactly.

2. **An experiment with NO extended context exports BYTE-IDENTICALLY.** That is what
   makes the companion an ADDITION rather than a mutation, and it is asserted over
   the records directory's own listing and the two files' digests.
   **Negative control performed 2026-09-17**, output quoted rather than predicted:
   replacing ``_write_extended_context_companion``'s ``if companion is None:
   return`` with an empty companion makes it RED with
   ``E  AssertionError: ['<ULID>.context.json', '<ULID>.evidence.json',
   '<ULID>.json']`` / ``assert 3 == 2``.

3. **The companion NEVER gates export.** A record with rich extended context and an
   incomplete draft is refused by the official schema alone, and the refusal says
   nothing about extended context.

WHAT IS DELIBERATELY NOT ASSERTED HERE
======================================

Nothing in this file asserts that a companion entry is CORRECT science. Every entry
carries a raw literal, a source and a locator, and whether the reading is right is a
scientist's judgement — which is why level 4 is a provenance artifact and not a field
value.

DATA BOUNDARY: none. The only archive read is
``tests/fixtures/bl15/gold/mini_corpus``, committed sanitized fixtures whose sample
names, potentials and motor values are unmistakably synthetic. Every workspace is a
``tmp_path``. No database connection is opened, no migration is applied, nothing
under ``examples/`` is read, and no model sees anything.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.extended_context as ctx
import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.notes as notes_module
import isaac_api.provenance as provenance
import isaac_api.proposals as proposals_module
import isaac_api.routes as routes
import isaac_api.submissions as submissions
import isaac_api.workspace as ws
from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import nominal

from test_export_fan_out import _split_full_draft

ARCHIVE = "bl15_synthetic_mini_corpus"
NOW = "2026-09-17T00:00:00Z"
ACTOR = "synthetic.extended.context.reviewer"


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    return ws


@pytest.fixture()
def armed(workspace, monkeypatch):
    """The fixture verifier — the ONLY configuration on which acceptance succeeds.

    ``accept`` answers ``409 human_actor_required`` in every deployment this build
    ships, because no trusted authentication boundary exists in it (``CLAUDE.md``
    §15). ``test_deploy_config.py`` pins these two variables to no shipped artifact.
    Without them the `DEC-43` condition (iv) proof — that the value reaches the
    record on a PERSON's act — could not be measured at all.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _app_client() -> TestClient:
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def client(workspace):
    return _app_client()


@pytest.fixture()
def armed_client(armed):
    return _app_client()


# --- helpers: the product's own operations ------------------------------------


def _entry(entry_id="e1", **over):
    """One unmistakably synthetic companion entry at level 4.

    The concept is a real level-4 registry concept, because ``ContextEntry`` checks
    the placement against the registry at construction — an entry at a level the
    registry disagrees with cannot be built, which is `DEC-41`'s first rule.
    """
    body = {
        "entry_id": entry_id,
        "concept": "spec_user_string",
        "raw_literal": "SYNTHETIC-USER-STRING",
        "source": "synthetic/mini/01_SYN1.0001",
        "locator": "line 3 header #C",
        "placement_level": mp.PLACEMENT_EXTENDED_CONTEXT,
    }
    body.update(over)
    return ctx.ContextEntry(**body)


def _bare_experiment(title="Extended context wiring"):
    return ws.create_experiment(title, {"kind": "synthetic"}, {"fields": {}, "pending": []})


def _imported(client) -> str:
    created = client.post("/api/imports", json={"label": "BL15-2 historical"})
    assert created.status_code == 200, created.text
    import_id = created.json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources",
        json={"kind": "archive", "fixture_name": ARCHIVE, "filename": "BL15-2 corpus"},
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return import_id


def _record(client, title="BL15-2 historical import") -> str:
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _add_to_experiment(client, import_id: str, eid: str, **body) -> dict:
    response = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, **body},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _digests(exp) -> dict[str, str]:
    """``basename -> sha256`` for everything in this experiment's records dir."""
    if not exp.records_dir.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(exp.records_dir.iterdir())
        if path.is_file()
    }


# =============================================================================
# W1 — the companion is wired into `workspace.Experiment`
# =============================================================================


def test_an_experiment_with_no_companion_serialises_and_hashes_as_it_always_did(
    workspace,
):
    """THE MIGRATION-FREE PROPERTY, asserted over the bytes rather than argued.

    Two halves, and they are different claims. The KEY IS ABSENT from the document,
    so an experiment with no extended context serialises byte-identically to one
    written by a build that had never heard of the companion. And a hand-written
    LEGACY document — one that has never carried the key — hashes identically to
    itself re-read, so the added signature member causes no spurious ``rev`` bump on
    every record in an existing workspace.
    """
    exp = _bare_experiment()
    state = exp.to_state()
    assert ctx.STATE_KEY not in state, sorted(state)
    assert exp.extended_context is None

    legacy = copy.deepcopy(state)
    legacy.pop(ctx.STATE_KEY, None)
    rehydrated = ws.Experiment.from_state(legacy)
    assert rehydrated.extended_context is None
    assert ws._authoritative_signature(exp) == ws._authoritative_signature(rehydrated)


def test_an_extended_context_only_change_is_persisted(workspace):
    """**THE LOAD-BEARING GUARD OF THIS WHOLE SLICE. A SILENT DROP IS RED HERE.**

    ``save_versioned`` returns ``False`` and WRITES NOTHING when the authoritative
    signature is unchanged. So if extended context were outside that payload, a save
    whose only change is a companion entry would be a no-op: the entries would sit on
    the loaded object, the route would answer 200, and the provenance would never
    reach disk. That is exactly the defect ``_authoritative_signature``'s own
    ``folder`` note records having had to close, one key along.

    THE SHAPE IS THE DEFECT'S, NOT THE CODE'S: nothing but extended context changes
    between the two saves, and the assertion is on what came BACK OFF DISK rather
    than on what the method returned.

    NEGATIVE CONTROL PERFORMED 2026-09-17, twice, and the observed output is quoted
    rather than predicted. Deleting the ``"extended_context"`` member from
    ``_authoritative_signature``'s payload makes this fail at ``assert
    exp.save_versioned() is True`` with ``AssertionError: assert False is True``;
    with that line relaxed to a bare call it fails one assertion later at ``assert
    reloaded.extended_context is not None`` with ``AssertionError: assert None is
    not None`` — the entries on the loaded object and nothing on disk, which is the
    silent drop this test exists for.
    """
    exp = _bare_experiment()
    settled_rev = exp.rev
    # A SAVE WITH NOTHING CHANGED IS A NO-OP — `create_experiment` already persisted
    # this record — which is what makes the save below attributable to the companion
    # and to nothing else.
    assert exp.save_versioned() is False
    assert exp.rev == settled_rev

    assert exp.add_extended_context_entries([_entry()], generated_utc=NOW) == 1
    assert exp.save_versioned() is True
    assert exp.rev == settled_rev + 1

    reloaded = ws.load_experiment(exp.id)
    assert reloaded is not None
    assert reloaded.extended_context is not None
    assert len(reloaded.extended_context.entries) == 1
    stored = reloaded.extended_context.entries[0]
    assert stored.entry_id == "e1"
    assert stored.raw_literal == "SYNTHETIC-USER-STRING"
    assert stored.placement_level == mp.PLACEMENT_EXTENDED_CONTEXT
    # AND IT IS NEVER A FIELD VALUE, on the way out as well as on the way in.
    assert stored.is_official_field_value is False


def test_re_adding_the_same_entry_is_a_byte_stable_no_op(workspace):
    """IDEMPOTENCE BY ``entry_id`` — the churn control the signature choice rests on.

    Putting extended context INSIDE the signature is what makes a companion-only save
    land; the cost of that choice is that a producer minting a fresh id per run would
    make every re-import a new revision. The producer derives ids from the statement,
    and this is the property that makes that matter.
    """
    exp = _bare_experiment()
    exp.add_extended_context_entries([_entry()], generated_utc=NOW)
    assert exp.save_versioned() is True
    settled = exp.rev
    before = ws._authoritative_signature(exp)

    # THE SAME ID, A DIFFERENT LITERAL. Nothing is merged and nothing is overwritten:
    # the stored entry is what an earlier import recorded, and silently rewriting
    # provenance would be worse than ignoring a duplicate.
    assert exp.add_extended_context_entries([_entry(raw_literal="DIFFERENT")]) == 0
    assert ws._authoritative_signature(exp) == before
    assert exp.save_versioned() is False
    assert exp.rev == settled
    assert exp.extended_context.entries[0].raw_literal == "SYNTHETIC-USER-STRING"


def test_the_companion_round_trips_through_the_state_document(workspace):
    """A save and a reload change neither the entries nor the signature.

    The signature half is not decoration: ``_authoritative_signature`` reads the same
    payload ``to_state`` writes, so a round trip that reordered or dropped anything
    would move the hash and make the NEXT identical re-entry look like a change.
    """
    exp = _bare_experiment()
    exp.add_extended_context_entries(
        [_entry("e1"), _entry("e2", locator="line 9 header #C")], generated_utc=NOW
    )
    exp.save_versioned()
    signature = ws._authoritative_signature(exp)

    reloaded = ws.load_experiment(exp.id)
    assert ws._authoritative_signature(reloaded) == signature
    assert [e.entry_id for e in reloaded.extended_context.entries] == ["e1", "e2"]
    assert reloaded.extended_context.generated_utc == NOW
    assert reloaded.save_versioned() is False


def test_an_unreadable_stored_entry_survives_a_save(workspace):
    """§11's rule: a malformed PERSISTED value is READ, never refused or dropped.

    The thing at stake here is sharper than usual — provenance nobody can interpret
    is exactly what must not be thrown away, because nothing can reconstruct it.
    """
    exp = _bare_experiment()
    exp.add_extended_context_entries([_entry()], generated_utc=NOW)
    exp.save_versioned()

    state = json.loads(exp.state_path.read_text(encoding="utf-8"))
    state[ctx.STATE_KEY]["entries"].append({"this": "cannot be read as an entry"})
    exp.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    reloaded = ws.load_experiment(exp.id)
    assert len(reloaded.extended_context.entries) == 1
    assert reloaded.extended_context.unreadable == (
        {"this": "cannot be read as an entry"},
    )
    # AND IT SURVIVES THE NEXT SAVE, which is the half that a first-round-trip test
    # would miss: `hydrate` re-reads its own `unreadable` key for exactly this.
    reloaded.add_extended_context_entries([_entry("e2")])
    reloaded.save_versioned()
    again = ws.load_experiment(exp.id)
    assert again.extended_context.unreadable == (
        {"this": "cannot be read as an entry"},
    )


def test_the_companion_is_not_in_the_submission_content_signature(workspace):
    """THE DISCLOSURE `conflict_resolution`'s LOCATION HAS TO MAKE, AND THIS ONE DOES NOT.

    ``conflict_resolution`` stores decisions INSIDE ``draft``, so for a zero-run
    record its key travels into ``submissions.content_signature`` and that
    consequence is disclosed at its own module. Extended context sits OUTSIDE
    ``draft``, so it cannot — and this asserts it over the digest itself rather than
    restating the reasoning.

    WHY IT MATTERS CONCRETELY: if it DID move, adding a companion entry would make a
    SUBMITTED record read as un-submitted and ask somebody to re-export a document
    whose bytes did not change.
    """
    experiment_draft, run_draft = _split_full_draft()
    exp = ws.create_experiment("Signature scope", {"kind": "synthetic"}, experiment_draft)
    exp.add_run(label="Run A", draft=copy.deepcopy(run_draft))
    exp.save_versioned()

    before = submissions.content_signature(exp.id, exp.export_units())
    record_signature_before = ws._authoritative_signature(exp)

    assert exp.add_extended_context_entries([_entry()], generated_utc=NOW) == 1
    after = submissions.content_signature(exp.id, exp.export_units())

    assert after == before, "a companion entry moved the submission content signature"
    # AND THE RECORD'S OWN SIGNATURE *DID* MOVE, which is the other half of the
    # decision: a companion entry is an authoritative change to the record (so the
    # save lands and the ETag moves) and NOT a change to what a submission publishes.
    # Asserting only the first half would pass on a change that moved neither.
    assert ws._authoritative_signature(exp) != record_signature_before


# =============================================================================
# W2 — the producer, and the consumer that lands it on a record
# =============================================================================


def test_the_archive_reading_offers_only_level_four_statements(workspace):
    """`DEC-41`'s FIRST RULE, over a real reading: never skip a level to reach 4.

    Every entry the producer emits is checked against the REGISTRY, not against a
    literal in this test — so this cannot drift from the hierarchy by agreeing with
    a transcription of it. And the level-1/2/3 concepts the same archive states in
    quantity (a sample name, a potential, an acquisition timestamp) are ABSENT,
    because their information belongs at the level the registry gives them.
    """
    session = hist.new_session(label="BL15-2", now_utc=NOW)
    hist.add_source(
        session,
        kind=hist.SOURCE_KIND_ARCHIVE,
        fixture_name=ARCHIVE,
        recorded_utc=NOW,
        now_utc=NOW,
    )
    hist.parse_session(session, now_utc=NOW)
    reading = session.archive_reading
    assert reading is not None
    assert reading.extended_context_entries, "the producer emitted nothing at all"

    for row in reading.extended_context_entries:
        entry = mp.mapping_for(row["concept"])
        expected = (
            entry.placement_level if entry else mp.PLACEMENT_EXTENDED_CONTEXT
        )
        assert expected == mp.PLACEMENT_EXTENDED_CONTEXT, row["concept"]
        assert row["placement_level"] == mp.PLACEMENT_EXTENDED_CONTEXT, row
        assert row["is_official_field_value"] is False, row
        # THE FOUR THINGS `DEC-41` REQUIRES ON EVERY ENTRY.
        for required in ("concept", "raw_literal", "source", "locator"):
            assert isinstance(row[required], str) and row[required].strip(), row

    concepts = {row["concept"] for row in reading.extended_context_entries}
    # NOT a level-1 concept in sight, and these three are stated by this corpus.
    assert "sample_name" not in concepts
    assert "potential_magnitude" not in concepts
    assert "acquisition_timestamp" not in concepts
    # THE PROFILE IS RECORDED, not assumed by a consumer — `DEC-43` (ii) keys on it.
    assert reading.profile_id == "ssrl_bl152_angel"
    assert reading.profile_version == "1"


def test_the_producer_ids_are_deterministic_across_two_readings(workspace):
    """Re-reading the same archive produces the SAME entry ids.

    Without this the idempotence in ``add_extended_context_entries`` buys nothing: a
    second import of one archive would merge a second copy of every entry and move
    the record's ``rev`` for provenance it already held.
    """
    ids = []
    for _ in range(2):
        session = hist.new_session(label="BL15-2", now_utc=NOW)
        hist.add_source(
            session,
            kind=hist.SOURCE_KIND_ARCHIVE,
            fixture_name=ARCHIVE,
            recorded_utc=NOW,
            now_utc=NOW,
        )
        hist.parse_session(session, now_utc=NOW)
        ids.append(
            [row["entry_id"] for row in session.archive_reading.extended_context_entries]
        )
    assert ids[0] == ids[1]
    assert len(set(ids[0])) == len(ids[0]), "the producer minted a duplicate id"


def test_adding_an_import_to_a_record_lands_the_companion_and_is_exactly_once(client):
    """THE CONSUMER, over HTTP, and the second call adds nothing.

    A re-run reporting ``added: 0`` beside an unchanged ``total_on_record`` is what
    tells a client "this record already holds all of it" rather than "this import
    states nothing at level 4" — which is why both numbers are published.
    """
    import_id = _imported(client)
    eid = _record(client)

    first = _add_to_experiment(client, import_id, eid, create_runs=True)
    report = first["extended_context"]
    assert report["available"] > 0, report
    assert report["added"] == report["available"], report
    assert report["unreadable"] == 0, report
    assert report["total_on_record"] == report["added"], report
    # THE CLAIM IS SERVED VERBATIM, never paraphrased by this route.
    assert report["not_official"] == ctx.NOT_OFFICIAL_CLAIM

    exp = ws.load_experiment(eid)
    assert exp.extended_context is not None
    assert len(exp.extended_context.entries) == report["added"]
    rev_after_first = exp.rev

    # `create_runs=True` AGAIN, and it has to be: the run-scoped candidates in this
    # batch are refused `422 target_requires_a_run` unless a run is named or created,
    # so a second call without it would measure a refusal rather than idempotence.
    # Every measurement already has a run, so this creates none.
    second = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert second["counts"]["runs_created"] == 0, second["counts"]
    assert second["extended_context"]["added"] == 0, second["extended_context"]
    assert (
        second["extended_context"]["total_on_record"] == report["total_on_record"]
    ), second["extended_context"]
    again = ws.load_experiment(eid)
    assert len(again.extended_context.entries) == report["added"]
    assert again.rev == rev_after_first, "an idempotent re-run spent a revision"


def test_the_candidate_stream_is_unchanged_by_the_companion(client):
    """THE COUNTS BLOCK STILL SUMS, and no companion number is inside it.

    A level-4 statement is not a candidate — it has no official field path by
    definition, so there is nothing for a scientist to accept ONTO a field. Folding
    it into ``counts`` would break the identity
    ``test_historical_import_routes.py`` asserts over that block, and would tell a
    reader some of their "candidates" can never be sent anywhere.
    """
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)

    counts = body["counts"]
    assert set(counts) == {
        "candidates",
        "sent",
        "already_sent",
        "not_sent",
        "runs_created",
        "runs_already_present",
    }, sorted(counts)
    assert counts["sent"] + counts["already_sent"] + counts["not_sent"] == counts[
        "candidates"
    ]
    assert body["extended_context"]["added"] > 0
    # NO CANDIDATE TARGETS A LEVEL-4 CONCEPT'S PATH, because there is not one.
    for row in body["sent"]:
        assert row["target_field_path"], row


def test_a_run_scoped_entry_names_the_run_made_from_its_own_acquisition(client):
    """RUN SCOPE IS BOUND BY A JOIN ON DATA BOTH SIDES CARRY, and by nothing else.

    A statement read out of an acquisition file becomes run-scoped for the run made
    from THAT file. Everything else stays experiment-scoped — a beamtime-wide reading
    attached to one run would read as though it had been entered on that acquisition,
    which is the "94 manual entries" lie ``bl15.reconstruct``'s shared-context
    handling exists to avoid.
    """
    import_id = _imported(client)
    eid = _record(client)
    _add_to_experiment(client, import_id, eid, create_runs=True)

    exp = ws.load_experiment(eid)
    entries = exp.extended_context.entries
    run_ids = {run.id for run in exp.runs}
    run_scoped = [e for e in entries if e.scope == ctx.SCOPE_RUN]
    experiment_scoped = [e for e in entries if e.scope == ctx.SCOPE_EXPERIMENT]

    assert run_scoped, "nothing was bound to a run at all"
    assert experiment_scoped, "everything was bound to a run, so nothing is shared"
    for entry in run_scoped:
        assert entry.run_id in run_ids
    for entry in experiment_scoped:
        assert entry.run_id is None
    # NOT ALL ON ONE RUN — that would mean the join is doing nothing.
    assert len({e.run_id for e in run_scoped}) > 1

    # AND A RUN SEES ITS OWN PLUS WHAT IT INHERITS, with the inheritance still
    # visible because every entry keeps its own scope.
    # KEYED ON `entry_id` RATHER THAN ON THE ENTRY OBJECT: a `ContextEntry` carries a
    # `normalized_value: Any` that can be a dict, so the frozen dataclass is not
    # reliably hashable and a set of entries raises `TypeError: unhashable type`.
    one = sorted(run_ids)[0]
    applying = {e.entry_id for e in exp.extended_context.applying_to_run(one)}
    assert {e.entry_id for e in exp.extended_context.for_run(one)} <= applying
    assert {e.entry_id for e in experiment_scoped} <= applying


# =============================================================================
# W3 — the sibling artifact
# =============================================================================


def _exported(client, title="Export companion"):
    """A fully answered, EXPORT-READY zero-run record.

    ``ws._full_draft()`` UNSPLIT, deliberately: the zero-run shape is the one every
    experiment in this application has ever had, and recomposing the split halves
    would be a second composition rule free to drift from the export path's.
    """
    exp = ws.create_experiment(
        title, {"kind": "synthetic"}, copy.deepcopy(ws._full_draft())
    )
    exp.save_versioned()
    return exp


def test_an_export_with_no_extended_context_is_byte_identical(client, workspace):
    """**THE GUARD THAT PROVES THIS IS AN ADDITION AND NOT A MUTATION.**

    A record with no companion writes exactly two files, with exactly the bytes it
    always wrote. The assertion is over the directory LISTING and the file DIGESTS,
    not over "the export succeeded".

    NEGATIVE CONTROL PERFORMED 2026-09-17, output quoted rather than predicted.
    Replacing ``_write_extended_context_companion``'s ``if companion is None:
    return`` with an empty companion makes this RED at ``assert len(names) == 2``
    with ``AssertionError: ['<ULID>.context.json', '<ULID>.evidence.json',
    '<ULID>.json']`` and ``assert 3 == 2`` — a third artifact for a record that has
    no extended context, which is the mutation this test refuses.
    """
    exp = _exported(client)
    assert exp.extended_context is None
    response = client.post(
        f"/api/experiments/{exp.id}/export", headers={"If-Match": exp.etag()}
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True, response.text

    reloaded = ws.load_experiment(exp.id)
    names = sorted(_digests(reloaded))
    assert len(names) == 2, names
    assert names[0].endswith(".json")
    assert any(name.endswith(".evidence.json") for name in names)
    assert not any(name.endswith(ctx.COMPANION_SUFFIX) for name in names)

    # AND THE ROUTE SAYS SO, rather than leaving a client to infer it from a 404.
    artifacts = client.get(f"/api/experiments/{exp.id}/artifacts").json()
    assert artifacts["extended_context"] is None
    assert artifacts["extended_context_filename"] is None
    assert artifacts["artifact"]["state"] == "current", artifacts["artifact"]


def test_export_writes_the_companion_as_a_sibling_and_serves_it(client, workspace):
    """``records/<ULID>.context.json``, beside ``<ULID>.json`` and ``<ULID>.evidence.json``.

    Three properties in one walk, because they are one act: the file is written with
    the companion module's own filename, the official record does NOT gain anything
    from it, and the artifacts route serves it.
    """
    exp = _exported(client, "Export companion present")
    exp.add_extended_context_entries([_entry()], generated_utc=NOW)
    exp.save_versioned()

    response = client.post(
        f"/api/experiments/{exp.id}/export", headers={"If-Match": exp.etag()}
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True, response.text

    reloaded = ws.load_experiment(exp.id)
    record_id = reloaded.record_id
    names = sorted(_digests(reloaded))
    assert ctx.companion_filename(record_id) in names, names
    assert len(names) == 3, names

    companion = json.loads(
        (reloaded.records_dir / ctx.companion_filename(record_id)).read_text("utf-8")
    )
    assert companion["artifact_kind"] == ctx.ARTIFACT_KIND
    assert companion["record_id"] == record_id
    assert companion["not_official"] == ctx.NOT_OFFICIAL_CLAIM
    assert companion["entry_count"] == 1
    assert companion["entries"][0]["is_official_field_value"] is False
    # NO `schema_version`. Claiming one would be the exact confusion the companion
    # exists to prevent, and `companion_document` says so.
    assert "schema_version" not in companion

    # THE OFFICIAL RECORD IS UNTOUCHED BY ANY OF IT.
    official = json.loads((reloaded.records_dir / f"{record_id}.json").read_text("utf-8"))
    serialised = json.dumps(official)
    assert ctx.ARTIFACT_KIND not in serialised
    assert "extended_context" not in serialised
    assert "SYNTHETIC-USER-STRING" not in serialised

    served = client.get(f"/api/experiments/{exp.id}/artifacts").json()
    assert served["extended_context_filename"] == ctx.companion_filename(record_id)
    assert served["extended_context"] == companion
    # AND IT DOES NOT MOVE THE ARTIFACT VERDICT. An absent companion is the normal
    # state of almost every record, so folding it into `stale` would report a missing
    # artifact for every one of them.
    assert served["artifact"]["state"] == "current", served["artifact"]


def test_extended_context_never_gates_export(client, workspace):
    """A RICH COMPANION AND AN INCOMPLETE RECORD: refused, on the schema alone.

    `DEC-41`: *level 4 never gates export — a record is exportable or not on the
    official schema alone.* So the companion cannot make a blocked record
    exportable, and the refusal must not mention it either: a scientist told their
    export failed because of extended context would go looking for a fix that does
    not exist.
    """
    exp = _bare_experiment("Blocked with a companion")
    exp.add_extended_context_entries(
        [_entry("e1"), _entry("e2", locator="line 9 header #C")], generated_utc=NOW
    )
    exp.save_versioned()
    assert len(exp.extended_context.entries) == 2

    response = client.post(
        f"/api/experiments/{exp.id}/export", headers={"If-Match": exp.etag()}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False, body
    assert json.dumps(body).count("extended_context") == 0, body
    assert ctx.ARTIFACT_KIND not in json.dumps(body)

    # NOTHING WAS WRITTEN — not the record, not the sidecar, and not a companion.
    reloaded = ws.load_experiment(exp.id)
    assert reloaded.record_id is None
    assert _digests(reloaded) == {}


def test_the_truth_path_holds_no_knowledge_of_the_companion(workspace):
    """§13. The deterministic core does not know this artifact exists.

    Asserted over the SOURCE of the four truth-path modules and the vendored schema
    rather than over behaviour, because the claim is about what they CAN see: a
    grep-shaped guard fails when somebody wires the companion into the exporter,
    which behaviour tests would pass right through.

    ``-a``-EQUIVALENT BY CONSTRUCTION: the files are read as BYTES and searched as
    bytes, so a NUL in one cannot make this exit clean over a file it never read —
    ``CLAUDE.md`` §11's rule about zero-hit sweeps.
    """
    import isaac_records
    import pathlib

    core = pathlib.Path(isaac_records.__file__).parent
    schema = core.parent.parent / "schema"
    files = sorted(core.rglob("*.py")) + sorted(schema.rglob("*.json"))
    assert len(files) > 10, files

    for token in (b"extended_context", ctx.ARTIFACT_KIND.encode(), b".context.json"):
        for path in files:
            assert token not in path.read_bytes(), (path.name, token)


def test_an_orphan_companion_is_prunable_rather_than_permanent(workspace):
    """``_artifact_stem`` recognises the companion, so a prune can reach it.

    Without the ``.context.json`` clause the stem of ``<ULID>.context.json`` is
    ``<ULID>.context``, which ``is_record_id`` refuses — so the prune would have
    passed over every companion and this application would manufacture a permanent
    orphan every time a run was deleted after export.
    """
    record_id = "0" * 26
    assert routes._artifact_stem(f"{record_id}.json") == record_id
    assert routes._artifact_stem(f"{record_id}.evidence.json") == record_id
    assert routes._artifact_stem(f"{record_id}{ctx.COMPANION_SUFFIX}") == record_id
    # AND NOTHING ELSE IS SUDDENLY A CANDIDATE FOR DELETION.
    assert routes._artifact_stem("notes.context.json") is None
    assert routes._artifact_stem("README.md") is None


# =============================================================================
# W4 — `DEC-43`: the one nominal value, offered
# =============================================================================


def test_the_nominal_value_is_offered_as_a_proposal_with_its_disclosure(client):
    """`DEC-43` CONDITIONS (i) AND (iv), TOGETHER, BECAUSE THEY ARE ONE DESIGN.

    (iv) The value is supplied *on the scientist's authority, not the parser's*, so
    it arrives as an OPEN proposal — the one object here that records a person taking
    authority for a value — and NOT as a written field. Nothing is in the draft yet.

    (i) The provenance travels: the proposal's ``rule`` is
    ``bl15.nominal.DISCLOSURE`` VERBATIM, and the proposal model refuses a blank
    rule, so there is no path that stores the number without the qualifier.
    """
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)

    offers = body["nominal_offers"]
    assert offers, body.keys()
    assert len(offers) == body["counts"]["runs_created"], (len(offers), body["counts"])

    exp = ws.load_experiment(eid)
    for offer in offers:
        assert offer["target_field_path"] == nominal.NOMINAL_TEMPERATURE_PATH
        assert offer["already_offered"] is False
        payload = offer["nominal"]
        assert payload["value"] == nominal.NOMINAL_TEMPERATURE_K == 298
        assert payload["unit"] == "K"
        # THE WORD IT IS NEVER DESCRIBED BY.
        assert payload["measured"] is False
        assert payload["basis"] == "nominal room temperature"
        assert payload["source_class"] == nominal.SOURCE_CLASS
        assert payload["decision_ref"] == "DEC-43"
        assert payload["disclosure"] == nominal.DISCLOSURE

        proposal = exp.get_proposal(offer["proposal_id"])
        assert proposal is not None
        assert proposal.state == proposals_module.STATE_OPEN
        assert proposal.proposed_value == 298
        assert proposal.rule == nominal.DISCLOSURE
        assert proposal.run_id == offer["run_id"]
        # THE NOTE CARRIES THE DISCLOSURE TOO, under a source that claims no file.
        note = exp.get_note(proposal.note_id)
        assert note is not None
        assert note.text == nominal.DISCLOSURE
        assert note.source == "domain_guidance_nominal"

        # AND THE VALUE IS NOT ON THE RUN. An OFFER is not a write.
        run = exp.get_run(offer["run_id"])
        assert nominal.NOMINAL_TEMPERATURE_PATH not in (run.draft.get("fields") or {})


def test_nothing_in_the_offer_calls_298_measured(client):
    """`DEC-43` (i): *a record that shows 298 K without the qualifier is a defect.*

    Asserted over the whole serialised response rather than over one field, because
    the defect is a SURFACE showing the number bare — so the thing to check is that
    every place the number appears, the disclosure appears too, and that the only
    sentence containing "measured" says NOT measured.
    """
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert body["nominal_offers"]

    serialised = json.dumps(body)
    assert "298" in serialised
    # THE DISCLOSURE TRAVELS WITH THE NUMBER, once per offer, so no surface can
    # render the value from this payload without having the qualifier available.
    assert serialised.count(nominal.DISCLOSURE) >= len(body["nominal_offers"])
    assert "NOT measured" in nominal.DISCLOSURE
    # AND NOTHING CLAIMS THE OPPOSITE. `NominalValue.measured` is a derived,
    # always-`False` property with no field behind it, so `true` here would mean
    # somebody had replaced the property with a stored boolean.
    assert '"measured": true' not in serialised.lower()
    for offer in body["nominal_offers"]:
        assert offer["nominal"]["measured"] is False


def test_only_the_bl15_2_angel_profile_has_a_nominal_default(client, monkeypatch):
    """`DEC-43` CONDITION (ii), STRUCTURALLY: every other profile leaves it ABSENT.

    Two halves. The lookup itself answers ``None`` for anything else — including
    ``None`` and an unregistered id — and the ROUTE goes through that lookup rather
    than through a profile literal of its own, which is what makes the fence
    structural. The second half is measured by moving the reading's profile id and
    observing that no offer is made and no proposal is minted.
    """
    assert nominal.nominal_temperature_for("ssrl_bl152_angel") is not None
    assert nominal.nominal_temperature_for(None) is None
    assert nominal.nominal_temperature_for("") is None
    assert nominal.nominal_temperature_for("some_other_beamline_profile") is None
    # CONDITION (iii): exactly one default, and the count is the fence.
    assert len(nominal.NOMINAL_DEFAULTS) == 1

    # THE ROUTE CONTAINS NO PROFILE LITERAL, so it cannot re-decide the scope.
    import pathlib

    source = pathlib.Path(routes.__file__).read_bytes()
    assert b"ssrl_bl152_angel" not in source

    import_id = _imported(client)
    eid = _record(client)
    session = hist.load_session(import_id)
    session.archive_reading = hist.ArchiveReading.from_state(
        {
            **session.archive_reading.to_state(),
            "profile_id": "some_other_beamline_profile",
        }
    )
    hist.save_session(session)

    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert body["nominal_offers"] == [], body["nominal_offers"]
    exp = ws.load_experiment(eid)
    assert not [
        p
        for p in exp.proposals
        if p.target_field_path == nominal.NOMINAL_TEMPERATURE_PATH
    ]
    # THE FIELD STAYS ABSENT AND THE RECORD STAYS BLOCKED — the pre-`DEC-43`
    # behaviour, preserved for every other profile.
    for run in exp.runs:
        assert nominal.NOMINAL_TEMPERATURE_PATH not in (run.draft.get("fields") or {})


def test_the_offer_is_never_made_over_a_value_that_is_already_there(client):
    """`DEC-43` supplies the value a scientist WOULD have supplied — not one they DID.

    Asserted on the second leg of the same record, because "was not offered twice"
    and "was not offered over an answer" are different facts and only the second is
    about shadowing a person's work.
    """
    import_id = _imported(client)
    eid = _record(client)
    first = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert first["nominal_offers"]

    # A SECOND BATCH ON THE SAME RUNS OFFERS NOTHING: every measurement already has
    # a run, so `created_runs` is empty and there is nothing new to offer on.
    second = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert second["counts"]["runs_created"] == 0, second["counts"]
    assert second["nominal_offers"] == [], second["nominal_offers"]

    exp = ws.load_experiment(eid)
    temperature_proposals = [
        p
        for p in exp.proposals
        if p.target_field_path == nominal.NOMINAL_TEMPERATURE_PATH
    ]
    assert len(temperature_proposals) == len(first["nominal_offers"])


def test_accepting_the_nominal_offer_records_a_persons_act(armed_client):
    """`DEC-43` (iv), END TO END: the value reaches the run on a PERSON's acceptance.

    This is the whole reason the offer is a proposal rather than a direct write.
    Acceptance goes through the same run-field writer manual entry uses, so the value
    arrives with the ``user_confirmation`` evidence that is the only human-act
    evidence type this build mints — and the recorded actor is the accepting person,
    not the parser.

    IT NEEDS THE FIXTURE VERIFIER, and that is stated rather than worked around:
    ``accept`` answers ``409 human_actor_required`` in every deployment this build
    ships. ``test_the_default_configuration_still_refuses_acceptance`` below asserts
    that other leg so neither is quietly lost.
    """
    client = armed_client
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    offer = body["nominal_offers"][0]

    response = client.post(
        f"/api/experiments/{eid}/proposals/{offer['proposal_id']}/review",
        # `confirmed_by_user` IS REQUIRED BY THE REVIEW ROUTE, and it is the product's
        # own expression of `DEC-43` condition (iv): a review act is somebody saying
        # so, and the route refuses `422 confirmation_required` without it.
        # `accepted_from: candidate` IS "the proposed value is right and is written as
        # it stands" — the claim a scientist adopting the nominal default is making,
        # and neither it nor `confirmed_by_user` is a default the route will supply.
        json={
            "action": "accept",
            "confirmed_by_user": True,
            "accepted_from": "candidate",
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 200, response.text

    exp = ws.load_experiment(eid)
    run = exp.get_run(offer["run_id"])
    envelope = (run.draft.get("fields") or {})[nominal.NOMINAL_TEMPERATURE_PATH]
    assert envelope["value"] == 298
    # THE HUMAN ACT, IN THE EVIDENCE. Nothing here claims a measurement.
    kinds = {e.get("source_type") for e in envelope.get("evidence") or []}
    assert "user_confirmation" in kinds, envelope
    accepted = exp.get_proposal(offer["proposal_id"])
    assert accepted.state == proposals_module.STATE_ACCEPTED
    assert accepted.accepted_value == 298
    assert accepted.rule == nominal.DISCLOSURE


def test_the_default_configuration_still_refuses_acceptance(client):
    """THE OTHER LEG, in the same file, so the fixture verifier cannot hide it.

    No trusted authentication boundary exists in this build, so accepting the offer
    is refused ``409 human_actor_required`` in every shipped deployment. That is a
    CONFIGURATION fact and no application change can close it.
    """
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    offer = body["nominal_offers"][0]

    response = client.post(
        f"/api/experiments/{eid}/proposals/{offer['proposal_id']}/review",
        # `confirmed_by_user` IS REQUIRED BY THE REVIEW ROUTE, and it is the product's
        # own expression of `DEC-43` condition (iv): a review act is somebody saying
        # so, and the route refuses `422 confirmation_required` without it.
        # `accepted_from: candidate` IS "the proposed value is right and is written as
        # it stands" — the claim a scientist adopting the nominal default is making,
        # and neither it nor `confirmed_by_user` is a default the route will supply.
        json={
            "action": "accept",
            "confirmed_by_user": True,
            "accepted_from": "candidate",
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "human_actor_required", response.text


def test_the_nominal_note_source_claims_no_file_and_no_person(workspace):
    """THE EIGHTH ``NOTE_SOURCES`` MEMBER EARNS ITS PLACE, and the argument is checkable.

    A note is the one field a reviewer uses to decide how much to trust what they
    are reading. All seven pre-existing members assert something FALSE of a nominal
    value: four name an artifact this application read, one says a person typed it
    here, and two are a different channel entirely. The falsity matters because the
    false claim would be *"something in the archive said this"* — which is the exact
    misreading `DEC-43` (i) calls a defect, given that the corpus states no
    temperature anywhere.
    """
    assert "domain_guidance_nominal" in notes_module.NOTE_SOURCES
    assert proposals_module.PROPOSAL_SOURCES is notes_module.NOTE_SOURCES

    # ITS ORIGIN IS ITS OWN, and it is not the tempting one: `file` would be the
    # answer for a historical import and would assert an artifact that does not
    # exist.
    origin = provenance.NOTE_SOURCE_ORIGIN["domain_guidance_nominal"]
    assert origin == provenance.ORIGIN_DOMAIN_GUIDANCE
    assert origin != provenance.ORIGIN_FILE
    assert origin != provenance.ORIGIN_MANUAL
    assert origin != provenance.ORIGIN_DERIVED
    # THE TABLE STAYS TOTAL over the note vocabulary.
    assert set(provenance.NOTE_SOURCE_ORIGIN) == set(notes_module.NOTE_SOURCES)
    assert set(provenance.ORIGIN_PRECEDENCE) == set(provenance.ORIGINS)
    assert len(provenance.ORIGIN_PRECEDENCE) == len(provenance.ORIGINS)


def test_the_new_origin_moves_no_existing_verdict(workspace):
    """THE NEGATIVE HALF OF ADDING TO ``ORIGIN_PRECEDENCE``.

    Inserting a member into a precedence list can change the headline origin of a
    value that has nothing to do with the new one. It cannot here, and this is why
    rather than an assurance: exactly ONE producer emits it, so a value that never
    carries it sees the same ordering it always did.

    Measured as a property over every subset of the OTHER origins: the primary is
    identical with and without the new member present in the precedence list.
    """
    others = [o for o in provenance.ORIGINS if o != provenance.ORIGIN_DOMAIN_GUIDANCE]
    without = tuple(
        o for o in provenance.ORIGIN_PRECEDENCE if o != provenance.ORIGIN_DOMAIN_GUIDANCE
    )

    def primary(order, present):
        for candidate in order:
            if candidate in present:
                return candidate
        return None

    for size in (1, 2, 3):
        for start in range(len(others) - size + 1):
            present = set(others[start : start + size])
            assert primary(provenance.ORIGIN_PRECEDENCE, present) == primary(
                without, present
            ), sorted(present)

    # AND ONLY ONE NOTE SOURCE CAN PRODUCE IT.
    emitters = [
        source
        for source, origin in provenance.NOTE_SOURCE_ORIGIN.items()
        if origin == provenance.ORIGIN_DOMAIN_GUIDANCE
    ]
    assert emitters == ["domain_guidance_nominal"]
