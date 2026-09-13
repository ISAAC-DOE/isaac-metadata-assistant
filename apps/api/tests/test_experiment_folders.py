"""FOLDERS: the virtual nested path-label model, and the invariants that make it safe.

WHAT A FOLDER IS HERE. One string on the experiment state document, e.g.
``"Cu K-edge/2026 campaign"``. A path MATERIALISES when at least one experiment is
assigned to it and stops existing when the last one leaves. There is NO durable
folder entity: no table, no row, no id, no owner. ``db_write.OWNED_TABLES`` is
unchanged by this feature and no migration exists for it, because
``isaac_experiments`` stores the whole document in one ``jsonb`` column
(``experiment_repository.Q_UPSERT_EXPERIMENT``), so a new key in it needs no schema
change and no operator action.

THE AUTHORIZATION BASIS, cited rather than assumed, because ``CLAUDE.md`` §15
records FIVE occasions on which something reached the write path before any
committed sentence named it. The FEATURE is authorized by §15's 2026-08-29
application-side extension ("the scientist-facing Experiment Data Workspace ... and
the associated tests, documentation ... and safe integration"). The PERSISTENCE
LOCATION is authorized by the 2026-08-07 lift's "app-owned tables for experiments
and **their normal application state**" — the same sentence
``docs/ingestion-proposal-contract.md`` §8.1 cites for storing proposals at
``state["proposals"]``, cited here for the same reason rather than re-argued.

THIS MODULE IS ``LIB-003a``, AND IT IS THE REASON THE DESIGN IS SAFE. ``LIB-003``'s
original acceptance proved a move does not shift ``content_signature`` and never
proved the property that actually matters: that ``folder`` reaches NO exported
record and NO evidence sidecar. Both are asserted here, over real export output,
together with every other half of the invariant — no scientific metadata moves, no
record identity moves, no run value moves, no validation verdict moves.

THE MECHANICAL TRAP THIS MODULE ALSO PINS. ``save_versioned()`` returns ``False``
and WRITES NOTHING when ``_authoritative_signature`` is unchanged, and
``from_state`` drops unknown keys. So ``folder`` had to be a real dataclass field
AND join that signature, or every first assignment would be silently discarded —
a route answering 200 over a value that never reached disk. ``test_a_first_folder_
assignment_actually_persists_across_a_reload`` is the direct check, and
``test_folder_is_inside_the_authoritative_signature`` is the mechanism.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app())


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """A worked-example client, for the five fully-populated canonical records.

    Used ONLY by the invariant tests, which need a record carrying real scientific
    content and a real export to prove that a folder move does not disturb it. The
    folder WRITE path is exercised against ordinary created records, because the
    route refuses a session header by design.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _create(client: TestClient, title: str, folder: str | None = None) -> dict:
    body: dict = {"title": title}
    if folder is not None:
        body["folder"] = folder
    response = client.post("/api/experiments", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _etag(client: TestClient, experiment_id: str) -> str:
    return client.get(f"/api/experiments/{experiment_id}").json()["version"]


def _move(client: TestClient, experiment_id: str, folder: str | None):
    return client.patch(
        f"/api/experiments/{experiment_id}/folder",
        json={"folder": folder},
        headers={"If-Match": f'"{_etag(client, experiment_id)}"'},
    )


# --- normalisation: what is stored, and what is REFUSED rather than repaired ----


@pytest.mark.parametrize(
    ("supplied", "stored"),
    [
        ("Cu K-edge", "Cu K-edge"),
        ("a/b/c", "a/b/c"),
        # Trimmed per level, empty levels dropped, so these four are ONE path.
        (" a / b ", "a/b"),
        ("/a/b", "a/b"),
        ("a/b/", "a/b"),
        ("a//b", "a/b"),
        # Unfiled, three spellings of it.
        ("", ""),
        ("   ", ""),
        (None, ""),
        # Deliberately NOT lower-cased, NOT transliterated, NOT punctuation-stripped:
        # a folder name is the scientist's label, not our identifier.
        ("CuO₂ · 2026 (β)", "CuO₂ · 2026 (β)"),
    ],
)
def test_normalisation_is_exactly_trim_and_drop_empty_levels(supplied, stored):
    assert ws.normalize_folder_path(supplied) == stored


@pytest.mark.parametrize(
    ("supplied", "reason"),
    [
        (7, "invalid_folder"),
        ({}, "invalid_folder"),
        (["a"], "invalid_folder"),
        (".", "invalid_folder_segment"),
        ("..", "invalid_folder_segment"),
        ("a/../b", "invalid_folder_segment"),
        ("a/./b", "invalid_folder_segment"),
        # A control character cannot be rendered, and — measured three times over in
        # this repository — makes the file holding it invisible to `grep`.
        ("a\nb", "invalid_folder_segment"),
        ("a\x00b", "invalid_folder_segment"),
        ("a\tb", "invalid_folder_segment"),
        ("x" * 65, "folder_segment_too_long"),
        ("/".join("abc" for _ in range(9)), "folder_too_deep"),
    ],
)
def test_a_path_this_server_will_not_store_is_REFUSED_not_repaired(supplied, reason):
    with pytest.raises(ws.FolderPathRefused) as raised:
        ws.normalize_folder_path(supplied)
    assert raised.value.reason == reason
    # THE MESSAGE NAMES NO OUTCOME, and that is the point of checking it here. The
    # same refusal is raised on the create path (where the honest sentence is
    # "Nothing was created") and on the move path ("Nothing was changed"), so a
    # message asserting either would be false on one of them. Each route appends
    # its own.
    assert "Nothing was" not in raised.value.message


def test_the_whole_path_length_limit_is_checked_and_is_reachable():
    """A path can be inside the depth and segment limits and still be too long.

    Asserted because the three limits are independent and a test that only ever
    tripped one of them would leave the other two unproven. 8 levels of 40
    characters is 327 characters, over the 300-character ceiling, while every
    level is inside the 64-character one and the depth is exactly at the maximum.
    """
    path = "/".join("x" * 40 for _ in range(8))
    assert len(path) > ws.FOLDER_MAX_PATH_LENGTH
    with pytest.raises(ws.FolderPathRefused) as raised:
        ws.normalize_folder_path(path)
    assert raised.value.reason == "folder_path_too_long"
    # AND THE LIMITS ARE NOT VACUOUS — one level shorter is accepted, so the refusal
    # above is the length rule firing rather than something else refusing everything.
    shorter = "/".join("x" * 40 for _ in range(7))
    assert ws.normalize_folder_path(shorter) == shorter


def test_trimming_happens_BEFORE_the_limits_are_checked():
    """Trailing whitespace a scientist cannot see must never push a legible name
    over a limit. `"x"*64 + "   "` is 67 characters and is accepted as 64."""
    assert ws.normalize_folder_path("x" * 64 + "   ") == "x" * 64


# --- the mechanical trap: signature membership and real persistence -------------


def test_folder_is_inside_the_authoritative_signature():
    """THE MECHANISM the next test depends on, asserted separately so a failure says
    WHICH half broke.

    ``save_versioned`` compares this hash and writes nothing when it is unchanged,
    so a ``folder`` outside it would make every first assignment a silent no-op.
    """
    a = ws.Experiment(id="A" * 26, title="t", created_utc="2026-07-12T00:00:00Z", source={}, draft={})
    b = ws.Experiment(id="A" * 26, title="t", created_utc="2026-07-12T00:00:00Z", source={}, draft={})
    assert ws._authoritative_signature(a) == ws._authoritative_signature(b)
    b.folder = "Archive"
    assert ws._authoritative_signature(a) != ws._authoritative_signature(b)


def test_a_legacy_document_with_no_folder_key_causes_no_spurious_rev_bump():
    """The property runs, notes and proposals each had to have.

    A document written before folders existed carries no ``folder`` key; it must
    hydrate to ``""`` and hash identically to the same experiment re-read from
    disk, or the added signature key would bump ``rev`` on every legacy record the
    first time it was touched.
    """
    legacy = {
        "id": "A" * 26,
        "title": "t",
        "created_utc": "2026-07-12T00:00:00Z",
        "source": {},
        "draft": {},
    }
    assert "folder" not in legacy
    hydrated = ws.Experiment.from_state(legacy)
    assert hydrated.folder == ""
    round_tripped = ws.Experiment.from_state(json.loads(json.dumps(hydrated.to_state())))
    assert round_tripped.folder == ""
    assert ws._authoritative_signature(hydrated) == ws._authoritative_signature(round_tripped)


def test_a_wrong_typed_persisted_folder_is_READ_not_refused():
    """§11's rule, applied to this key: a malformed value already PERSISTED must be
    read, not refused to a reader who did nothing wrong.

    A non-string reads as unfiled. Nothing raises, nothing is coerced (which would
    manufacture ``"7"`` out of a number), and the record stays readable — the
    alternative is a whole-list 500 over one bad key, which this repository has
    measured twice.
    """
    for bad in (7, {}, [], True, None):
        state = {
            "id": "A" * 26,
            "title": "t",
            "created_utc": "2026-07-12T00:00:00Z",
            "source": {},
            "draft": {},
            "folder": bad,
        }
        assert ws.Experiment.from_state(state).folder == ""


def test_a_first_folder_assignment_actually_persists_across_a_reload(client):
    """THE TRAP, CHECKED END TO END. If ``folder`` were outside the authoritative
    signature this would pass in memory and fail here: ``save_versioned`` would
    return ``False``, write nothing, and the reload would answer ``""``."""
    created = _create(client, "Unfiled at first")
    assert created["folder"] == ""
    moved = _move(client, created["id"], "Cu K-edge/2026 campaign")
    assert moved.status_code == 200, moved.text
    assert moved.json()["folder"] == "Cu K-edge/2026 campaign"
    # A FRESH READ, not the write's own echo — the echo is built from the in-memory
    # instance and would agree with itself whether or not anything was written.
    reread = client.get(f"/api/experiments/{created['id']}").json()
    assert reread["folder"] == "Cu K-edge/2026 campaign"
    # AND IN THE LIST, which is the payload the Library renders from.
    listed = {e["id"]: e for e in client.get("/api/experiments").json()["experiments"]}
    assert listed[created["id"]]["folder"] == "Cu K-edge/2026 campaign"


def test_the_assignment_bumps_rev_and_invalidates_the_held_etag(client):
    """A DISCLOSED COST, asserted rather than described. `folder` is inside the
    authoritative signature, so a move advances the version — which is what makes
    the `If-Match` contract hold, and which means a client holding the old token
    must re-read."""
    created = _create(client, "Versioned")
    before = client.get(f"/api/experiments/{created['id']}")
    old_version = before.json()["version"]
    old_rev = before.json()["rev"]
    assert _move(client, created["id"], "Archive").status_code == 200
    after = client.get(f"/api/experiments/{created['id']}").json()
    assert after["rev"] == old_rev + 1
    assert after["version"] != old_version
    # THE OLD TOKEN IS NOW REFUSED, writing nothing — the loss the precondition
    # exists to prevent.
    stale = client.patch(
        f"/api/experiments/{created['id']}/folder",
        json={"folder": "Somewhere else"},
        headers={"If-Match": f'"{old_version}"'},
    )
    assert stale.status_code == 412
    assert client.get(f"/api/experiments/{created['id']}").json()["folder"] == "Archive"


def test_re_sending_the_same_folder_is_a_true_no_op(client):
    created = _create(client, "Idempotent", folder="A/B")
    first = client.get(f"/api/experiments/{created['id']}").json()
    again = _move(client, created["id"], "A/B")
    assert again.status_code == 200
    assert again.json()["rev"] == first["rev"]
    assert again.json()["version"] == first["version"]


def test_clearing_and_null_both_unfile(client):
    for cleared in ("", None):
        created = _create(client, f"Clear {cleared!r}", folder="A/B")
        assert created["folder"] == "A/B"
        response = _move(client, created["id"], cleared)
        assert response.status_code == 200, response.text
        assert response.json()["folder"] == ""
        assert client.get(f"/api/experiments/{created['id']}").json()["folder"] == ""


# --- the route's refusals -------------------------------------------------------


def test_the_route_refuses_a_bad_path_with_a_typed_422_and_writes_nothing(client):
    created = _create(client, "Refused", folder="Keep me")
    response = _move(client, created["id"], "a/../b")
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_folder_segment"
    assert response.json()["message"].endswith("Nothing was changed.")
    assert client.get(f"/api/experiments/{created['id']}").json()["folder"] == "Keep me"


def test_the_create_route_refuses_a_bad_path_and_creates_NOTHING(client):
    before = len(client.get("/api/experiments").json()["experiments"])
    response = client.post("/api/experiments", json={"title": "Nope", "folder": ".."})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_folder_segment"
    assert response.json()["message"].endswith("Nothing was created.")
    # THE RECORD DOES NOT LAND UNFILED WITH A WARNING. A scientist who named a
    # destination did not ask for that.
    assert len(client.get("/api/experiments").json()["experiments"]) == before


def test_an_absent_folder_key_is_refused_rather_than_read_as_either(client):
    """`folder` is REQUIRED and nullable. An absent key would be ambiguous between
    "unfile it" and "leave it where it is", and guessing between those on a write
    is exactly the inference `CLAUDE.md` §5 forbids."""
    created = _create(client, "Absent key", folder="A")
    response = client.patch(
        f"/api/experiments/{created['id']}/folder",
        json={},
        headers={"If-Match": f'"{_etag(client, created["id"])}"'},
    )
    assert response.status_code == 422
    assert client.get(f"/api/experiments/{created['id']}").json()["folder"] == "A"


def test_the_route_writes_the_folder_and_NOTHING_else(client):
    """`extra="forbid"`, so a body naming a second field is a 422 and never a
    partial write."""
    created = _create(client, "Original name")
    for extra in ({"folder": "A", "title": "Renamed"}, {"folder": "A", "description": "x"}):
        response = client.patch(
            f"/api/experiments/{created['id']}/folder",
            json=extra,
            headers={"If-Match": f'"{_etag(client, created["id"])}"'},
        )
        assert response.status_code == 422, response.text
    fresh = client.get(f"/api/experiments/{created['id']}").json()
    assert fresh["title"] == "Original name"
    assert fresh["folder"] == ""


def test_the_precondition_is_required(client):
    created = _create(client, "Precondition")
    absent = client.patch(f"/api/experiments/{created['id']}/folder", json={"folder": "A"})
    assert absent.status_code == 428
    malformed = client.patch(
        f"/api/experiments/{created['id']}/folder",
        json={"folder": "A"},
        headers={"If-Match": "not-a-token"},
    )
    assert malformed.status_code == 400
    assert client.get(f"/api/experiments/{created['id']}").json()["folder"] == ""


def test_a_worked_example_session_is_refused_and_nothing_changes(seeded):
    experiments = seeded.get("/api/experiments").json()["experiments"]
    target = experiments[0]["id"]
    response = seeded.patch(
        f"/api/experiments/{target}/folder",
        json={"folder": "A"},
        headers={"If-Match": f'"{seeded.get(f"/api/experiments/{target}").json()["version"]}"'},
    )
    assert response.status_code == 409
    assert response.json()["error"] == "ordinary_scope_required"
    assert seeded.get(f"/api/experiments/{target}").json()["folder"] == ""


def test_a_missing_record_is_404_and_a_bad_path_is_still_422_first(client):
    missing = client.patch(
        "/api/experiments/" + "Z" * 26 + "/folder",
        json={"folder": "A"},
        headers={"If-Match": '"1"'},
    )
    assert missing.status_code == 404
    # A BODY THIS SERVER WILL NOT STORE IS REFUSED BEFORE THE RECORD IS LOOKED UP,
    # deliberately: it could never become a write however the record turns out, so
    # holding the record lock to decide that would serialise other writers behind a
    # request that was always going to fail.
    bad = client.patch(
        "/api/experiments/" + "Z" * 26 + "/folder",
        json={"folder": ".."},
        headers={"If-Match": '"1"'},
    )
    assert bad.status_code == 422


# --- LIB-003a: the invariant that makes the design safe -------------------------


def test_a_folder_move_changes_NO_science_and_reaches_NO_exported_artifact(seeded, tmp_path, monkeypatch):
    """``LIB-003a``. The one test this whole design rests on.

    It is driven through the STORE rather than over HTTP, because the property is
    about export output and validation verdicts on a record carrying real
    scientific content — and the five canonical records are the only ones in this
    repository that have any. The move route itself is exercised over HTTP by the
    tests above; what is asserted here is that setting the field disturbs nothing.
    """
    from conftest import open_tutorial_scope

    scope = open_tutorial_scope()
    experiments = scope.list_experiments()
    # THE EXPORTED ONE, deliberately: a record with a real record file and a real
    # evidence sidecar on disk is the only one that can prove `folder` reaches
    # neither.
    exported = [e for e in experiments if e.record_id is not None]
    assert exported, "the fixture must include an exported record or this proves nothing"
    exp = exported[0]

    def snapshot(record):
        units = record.export_units()
        return {
            "draft": copy.deepcopy(record.draft),
            # `ExportUnit.draft` is the composed draft that will be exported —
            # there is no `Experiment.export_draft()`. A zero-run record has one
            # unit holding `self.draft` itself; a fan-out has one per run.
            "unit_drafts": [copy.deepcopy(u.draft) for u in units],
            "runs": [copy.deepcopy(r.to_state()) for r in record.sorted_runs()],
            "resolved": [copy.deepcopy(record.resolved_run_draft(r)) for r in record.sorted_runs()],
            "content_signature": __import__(
                "isaac_api.submissions", fromlist=["submissions"]
            ).content_signature(record.id, units),
            "record_id": record.record_id,
            "pending": copy.deepcopy(record.pending()),
            "status": record.status(),
            "evidenced": record.evidenced_field_count(),
            "artifacts": {
                path.name: path.read_text(encoding="utf-8")
                for path in sorted(record.records_dir.glob("*.json"))
            },
        }

    before = snapshot(exp)
    assert before["artifacts"], "the exported record must have artifacts on disk"

    exp.folder = "Somewhere/Else"
    assert exp.save_versioned() is True, "the assignment must actually write"
    after_instance = scope.load_experiment(exp.id)
    assert after_instance is not None
    assert after_instance.folder == "Somewhere/Else"
    after = snapshot(after_instance)

    # NOTHING SCIENTIFIC MOVED.
    assert after["draft"] == before["draft"]
    assert after["unit_drafts"] == before["unit_drafts"]
    assert after["resolved"] == before["resolved"]
    # NO RUN VALUE MOVED. (Run version metadata is excluded from the signature, so a
    # run's own document is byte-identical too.)
    assert after["runs"] == before["runs"]
    # NO RECORD IDENTITY MOVED, and NO CONTENT SIGNATURE MOVED — so a submitted
    # revision stays submitted and an exported artifact stays `current`.
    assert after["record_id"] == before["record_id"]
    assert after["content_signature"] == before["content_signature"]
    # NO VALIDATION RESULT MOVED.
    assert after["pending"] == before["pending"]
    assert after["status"] == before["status"]
    assert after["evidenced"] == before["evidenced"]
    # AND THE EXPORTED ARTIFACTS ARE BYTE-IDENTICAL.
    assert after["artifacts"] == before["artifacts"]

    # THE PROPERTY `LIB-003`'s ORIGINAL ACCEPTANCE OMITTED, AND THE ONLY REASON THIS
    # DESIGN IS SAFE: the word does not appear ANYWHERE in the exported record or in
    # the evidence sidecar. Checked over the raw bytes rather than over a key path,
    # because a key path only proves the key we thought to look for is absent.
    for name, text in after["artifacts"].items():
        assert "Somewhere/Else" not in text, name
        assert "folder" not in json.loads(text), name


def test_folder_reaches_no_export_unit_and_no_sidecar_for_a_FRESH_export(seeded):
    """The same property on the OTHER side of the boundary: a record filed in a
    folder and exported AFTERWARDS must produce artifacts that do not mention it.

    The test above proves a move does not disturb artifacts that already exist.
    This proves the field cannot LEAK into artifacts built while it is set, which is
    a different claim and the one a future export-path change would break.
    """
    from conftest import open_tutorial_scope

    scope = open_tutorial_scope()
    ready = [e for e in scope.list_experiments() if e.pending_count() == 0 and e.record_id is None]
    assert ready, "the fixture must include an unexported, fully-answered record"
    exp = ready[0]
    exp.folder = "Leak/Check"
    assert exp.save_versioned() is True

    for unit in exp.export_units():
        assert "folder" not in unit.draft
        assert "Leak/Check" not in json.dumps(unit.draft, ensure_ascii=False)

    from isaac_records import export as truth_export

    units = exp.export_units()
    assert units, "the record must have at least one exportable unit"
    for unit in units:
        # `root` is the repository root the truth core resolves sidecar paths
        # against. It is the same value `routes._write_record` hands it.
        result = truth_export.export_draft(unit.draft, ws.REPO_ROOT)
        assert result.ok, result.draft_report.errors
        # OVER THE RAW BYTES, not over a key path: a key path only proves the key we
        # thought to look for is absent, and the property is that the VALUE cannot
        # appear anywhere in either artifact.
        assert "folder" not in result.record
        assert "Leak/Check" not in json.dumps(result.record, ensure_ascii=False)
        assert "Leak/Check" not in json.dumps(result.sidecar, ensure_ascii=False)


def test_no_folder_value_ever_becomes_a_filesystem_path(client, tmp_path):
    """A folder is a LABEL, not a directory, and nothing derives a path from it.

    Every path this application builds for a record comes from ``Experiment.id``
    (``scope_root`` / ``records_dir``). Asserted over the workspace tree rather
    than by reading the code, because the claim is about behaviour: after filing a
    record under a nested path, no directory of that name exists anywhere.
    """
    created = _create(client, "Pathless", folder="outer/inner")
    assert _move(client, created["id"], "outer/inner").status_code == 200
    root = tmp_path / "ws"
    names = {p.name for p in root.rglob("*")}
    assert "outer" not in names
    assert "inner" not in names
    # AND THE RECORD IS STILL WHERE IT ALWAYS WAS — under its own id.
    assert (root / created["id"] / "experiment.json").is_file()


# --- the list payload the Library renders from ---------------------------------


def test_the_list_serves_the_folder_and_the_library_columns(client):
    created = _create(client, "Listed", folder="A/B")
    row = next(
        e for e in client.get("/api/experiments").json()["experiments"] if e["id"] == created["id"]
    )
    assert row["folder"] == "A/B"
    # A CREATED RECORD HAS NO SCIENTIFIC CONTENT, so both record-level values are
    # `null` — the honest representation of a value nothing has supplied, and the
    # reason these are `null` rather than a placeholder string.
    assert row["technique"] is None
    assert row["beamline"] is None
    assert row["run_count"] == 0
    assert row["open_proposal_count"] == 0
    assert row["updated_utc"]


def test_the_seeded_rows_carry_a_real_technique_and_beamline(seeded):
    """The planning document said these had no data source. Measured otherwise.

    `2026-09-12-isaac-ux-ia-plan.md` §1.6 states "No technique / beamline /
    facility. The proposed `Beamline` column has no data source." The data source is
    the draft envelope the list already loads, and both values carry evidence.
    """
    rows = seeded.get("/api/experiments").json()["experiments"]
    assert rows, "the worked example must be seeded or this proves nothing"
    for row in rows:
        assert row["technique"] == "HERFD-XAS"
        assert row["beamline"] == "15-2"


def test_a_needs_confirmation_field_is_withheld_from_the_list(client):
    """An unconfirmed value is a QUESTION, not an answer. Rendering it in a list
    column would present a pending question as a recorded fact (`CLAUDE.md` §5)."""
    created = _create(client, "Unconfirmed")
    exp = ws.load_experiment(created["id"], session_id=None)
    assert exp is not None
    exp.draft.setdefault("fields", {})["system.technique"] = {
        "value": "HERFD-XAS",
        "status": "needs_confirmation",
        "evidence": [],
    }
    exp.save()
    row = next(
        e for e in client.get("/api/experiments").json()["experiments"] if e["id"] == created["id"]
    )
    assert row["technique"] is None
    # AND THE GUARD IS NOT VACUOUS: the same value with an established status IS
    # reported, so the `None` above is the status rule firing rather than the lookup
    # failing for some other reason.
    exp.draft["fields"]["system.technique"]["status"] = "verified"
    exp.save()
    row = next(
        e for e in client.get("/api/experiments").json()["experiments"] if e["id"] == created["id"]
    )
    assert row["technique"] == "HERFD-XAS"


@pytest.mark.parametrize(
    "malformed",
    [
        {"fields": 7},
        {"fields": {"system.technique": "not a dict"}},
        {"fields": {"system.technique": {"value": 7, "status": "verified"}}},
        {"fields": {"system.technique": {"value": "   ", "status": "verified"}}},
        {"fields": {"system.technique": {}}},
    ],
)
def test_a_malformed_draft_is_READ_not_500(client, malformed):
    """One bad key must not take the whole list down.

    This repository has measured that defect twice — a persisted non-iterable
    `draft["pending"]` and a wrong-typed top-level container each returned 500 from
    BOTH the detail route and the whole-workspace list. The Library's new columns
    must not reintroduce it through a third door.
    """
    created = _create(client, "Malformed")
    exp = ws.load_experiment(created["id"], session_id=None)
    assert exp is not None
    exp.draft.update(malformed)
    exp.save()
    listed = client.get("/api/experiments")
    assert listed.status_code == 200, listed.text
    row = next(e for e in listed.json()["experiments"] if e["id"] == created["id"])
    assert row["technique"] is None
    assert client.get(f"/api/experiments/{created['id']}").status_code == 200


def test_open_proposal_count_counts_only_OPEN_ones(seeded):
    """Decided proposals are kept forever rather than deleted, so a TOTAL would only
    grow and would answer a question nobody asked. The Library needs "what is waiting
    for me", so the count is the OPEN ones.

    THE TERMINAL STATES ARE REACHED THROUGH `proposals.py`'S OWN REVIEW ACTS, not by
    replacing one field on a frozen object. The first version of this test did the
    latter and the model REFUSED it — `ImmutableProposal.__post_init__` raises on an
    accepted proposal with no `accepted_value`, because "an accepted proposal with no
    value would claim a decision nobody made". That refusal is correct and the
    shortcut was the defect: a fixture that bypasses an invariant is a fixture that
    can assert a state the product cannot produce.
    """
    from conftest import open_tutorial_scope
    from isaac_api import proposals as proposals_module
    from isaac_api import submissions

    scope = open_tutorial_scope()
    exp = scope.list_experiments()[0]

    def minted(index: int):
        return proposals_module.new_proposal(
            proposal_id=f"01JQZZ2PROPOSAL000000000{index}",
            experiment_id=exp.id,
            note_id=f"01JQZZ2NOTE00000000000000{index}",
            run_id=None,
            target_field_path="context.temperature_K",
            proposed_value=300 + index,
            rule="a captured note stated the temperature",
            source="typed_note",
            proposed_utc="2026-07-12T00:00:00Z",
            base_rev=exp.rev,
            target_digest="d" * 64,
            # `unattributed` is the ONLY basis available here, and the reason is the
            # one `CLAUDE.md` §15 records: no trusted authentication boundary exists
            # in this build, so nothing may claim a verified actor. The other two
            # recognised bases each REQUIRE a named subject, and inventing one for a
            # test about a COUNT would assert a verification of nobody.
            trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
        )

    # Two OPEN, one ACCEPTED, one REJECTED.
    exp.add_proposal(minted(0))
    exp.add_proposal(minted(1))
    exp.add_proposal(
        proposals_module.accept_proposal(
            minted(2),
            at="2026-07-12T00:01:00Z",
            accepted_value=302,
            # `candidate` = the value the proposal already carried, as opposed to
            # `edited` = a value the scientist corrected before accepting. Read off
            # `proposals.ACCEPTED_FROM_VALUES` rather than guessed — the first
            # attempt invented `"proposed_value"` and the model refused it, which is
            # the enum doing its job.
            accepted_from="candidate",
            # One of `proposals.py`'s three recognised WRITERS, not a route string:
            # `accepted` is terminal-AND-applied here, so the row has to say which
            # writer wrote the value. `record_enum_fields` is the record-level one.
            applied_via="record_enum_fields",
            applied_rev=exp.rev + 1,
            applied_target_digest="d" * 64,
            actor_trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
        )
    )
    exp.add_proposal(
        proposals_module.reject_proposal(
            minted(3),
            at="2026-07-12T00:02:00Z",
            reason="the note was about a different sample",
            actor_trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
        )
    )
    exp.save()

    from isaac_api import routes

    reloaded = scope.load_experiment(exp.id)
    assert reloaded is not None
    assert len(reloaded.proposals) == 4, "all four must survive the round trip"
    assert routes._summary(reloaded)["open_proposal_count"] == 2


def test_an_unreadable_proposal_is_not_counted_as_open(seeded):
    """An entry this build cannot parse has NO state, so it cannot be asserted to be
    open. It is preserved verbatim across saves — the whole point of
    `unreadable_proposals` — and stays visible on the record's own proposals
    surface, which is where an unparseable entry can actually be looked at."""
    from conftest import open_tutorial_scope
    from isaac_api import proposals as proposals_module
    from isaac_api import routes

    scope = open_tutorial_scope()
    exp = scope.list_experiments()[0]
    state = exp.to_state()
    state[proposals_module.STATE_KEY] = [{"not": "a proposal"}]
    scope_id = exp.session_id
    rehydrated = ws.Experiment.from_state(state, session_id=scope_id)
    assert rehydrated.unreadable_proposals, "the fixture must produce an unreadable entry"
    assert rehydrated.proposals == []
    assert routes._summary(rehydrated)["open_proposal_count"] == 0


def test_run_count_is_the_documents_own_runs_and_costs_no_extra_read(seeded):
    """The planning document said this needed N further requests. Measured otherwise.

    `2026-09-12-isaac-ux-ia-plan.md` §1.6: "No run count. The Library cannot show
    'how many Runs' without N further requests." The runs live INSIDE the experiment
    state document, so the count is a `len()` over data the list read already paid
    for.

    *** C-5, FOUND BY INDEPENDENT REVIEW 2026-09-13: THE ORIGINAL VERSION OF THIS
    TEST COULD NOT FAIL, AND ITS DOCSTRING CLAIMED A COMPARISON IT DID NOT MAKE. ***

    It read: "proven here by counting `Path.read_text` calls across a list read with
    the Library's columns and without them." The "without" arm was:

        def stripped_summary(exp, **kwargs):
            row = real_summary(exp, **kwargs)   # computes ALL six columns first
            for key in (...): row.pop(key, None)

    Popping a key from a dict removes no file read. Both arms executed identical
    I/O, so the two counts were equal by construction. It was
    with-columns versus with-columns-then-popped. The reviewer demonstrated it by
    adding an unguarded `Path.read_text` inside `_evidenced_field_value`:
    `MUTANT HITS: 32 | with_count=15 without_count=15 -> 1 passed`.

    ── THE REPLACEMENT IS ATTRIBUTABLE RATHER THAN COMPARATIVE ─────────────────

    There is no honest "without" arm available: any control that calls `_summary`
    pays its I/O, and one that reimplements `_summary`'s other nine fields would be
    a second copy of the code under test. So the claim is now measured DIRECTLY, on
    the only thing it was ever about: **`_summary` itself must perform ZERO file
    reads.** Every `_summary` call is wrapped, the read counter is sampled on entry
    and exit, and any non-zero delta fails and names the paths it read.

    That is a STRICTLY STRONGER property than the comparison claimed. The
    comparison would have tolerated a read that happened to occur in both arms;
    this tolerates none, and it localises the cost to the function that would carry
    it instead of to a whole-request total that a dozen unrelated reads move.
    """
    import pathlib

    scope_client = seeded
    rows = scope_client.get("/api/experiments").json()["experiments"]
    target = rows[0]["id"]
    etag = scope_client.get(f"/api/experiments/{target}").json()["version"]
    assert (
        scope_client.post(
            f"/api/experiments/{target}/runs",
            json={"label": "Cold"},
            headers={"If-Match": f'"{etag}"'},
        ).status_code
        == 201
    )

    reads: list[str] = []
    real_read_text = pathlib.Path.read_text

    def counting_read_text(self, *args, **kwargs):
        reads.append(str(self))
        return real_read_text(self, *args, **kwargs)

    import isaac_api.routes as routes_module

    real_summary = routes_module._summary

    # Every `_summary` call, with the reads it performed. A row whose six Library
    # columns reached the filesystem shows up here as a non-empty list.
    per_row_reads: list[tuple[str, list[str]]] = []

    def measured_summary(exp, **kwargs):
        before = len(reads)
        row = real_summary(exp, **kwargs)
        per_row_reads.append((getattr(exp, "id", "?"), reads[before:]))
        return row

    routes_module._summary = measured_summary
    pathlib.Path.read_text = counting_read_text
    try:
        rows = scope_client.get("/api/experiments").json()["experiments"]
    finally:
        pathlib.Path.read_text = real_read_text
        routes_module._summary = real_summary

    # The columns are actually populated — without this the assertion below would
    # pass for a build that stopped computing them entirely.
    row = next(r for r in rows if r["id"] == target)
    assert row["run_count"] == 1, row
    for key in (
        "updated_utc",
        "run_count",
        "open_proposal_count",
        "folder",
        "technique",
        "beamline",
    ):
        assert key in row, f"{key} is not being served at all; this test proves nothing"

    # The fixture must actually have exercised the function, or "zero reads" is the
    # arithmetic of an empty list.
    assert per_row_reads, "no _summary call was observed; the instrumentation missed"

    offenders = {eid: paths for eid, paths in per_row_reads if paths}
    assert not offenders, (
        "building a Library row reached the filesystem, so the six columns are NOT "
        f"free: {offenders}. They are supposed to be read out of the experiment "
        "document the list read already loaded."
    )
