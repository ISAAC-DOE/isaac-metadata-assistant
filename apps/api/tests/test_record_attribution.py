"""The server-owned `attribution.uploaded_by` stamp, and the four ways it could lie.

WHAT THIS FILE IS FOR
=====================
``record_attribution`` writes the one field the official schema says the SERVER owns.
The failure mode is not a crash — it is a scientific record naming somebody who did
not upload it, which no amount of green CI would surface. So the tests here are
arranged around the ways a wrong name could get in, and each has a NEGATIVE CONTROL
that fails if the guard is removed:

  1. a draft supplies the name              -> still refused by the truth core
  2. a request supplies the name            -> no header, body or query reaches it
  3. the default deployment invents a name  -> the field is absent, not empty
  4. a stamped artifact reads as changed    -> freshness ignores the stamp, both sides

``tests/test_attribution_uploaded_by.py`` owns (1) and is deliberately not duplicated
here; this file asserts that this slice did not weaken it.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from isaac_api import identity as identity_module
from isaac_api import record_attribution as ra
import isaac_api.workspace as ws
from conftest import tutorial_client, tutorial_ws
from isaac_api.dependencies import artifact_state


# ---------------------------------------------------------------------------
# with_server_stamp / without_server_stamp — the pure half
# ---------------------------------------------------------------------------


def test_no_subject_leaves_the_record_untouched_and_identical():
    """The shipped default. `None` in, the same value out, no `attribution` invented."""
    record = {"record_id": "R", "timestamps": {"created_utc": "2026-01-01T00:00:00Z"}}
    before = copy.deepcopy(record)
    assert ra.with_server_stamp(record, None) == before
    assert "attribution" not in ra.with_server_stamp(record, None)


def test_the_stamp_never_mutates_its_argument():
    """NEGATIVE CONTROL for an in-place write.

    `_write_record` reads `result.record` again after stamping (for the record id) and
    the caller reads it too. An in-place stamp would leak the field into a structure
    those readers did not ask for — the exact defect `_enforce_server_owned_invariant`
    records having been caused once by an in-place `pop`.
    """
    record = {"record_id": "R", "attribution": {"contributors": [{"name": "A"}]}}
    before = copy.deepcopy(record)
    stamped = ra.with_server_stamp(record, "sfaraday")
    assert record == before, "with_server_stamp mutated its argument"
    assert stamped["attribution"]["uploaded_by"] == "sfaraday"
    assert stamped["attribution"]["contributors"] == [{"name": "A"}]
    assert stamped["attribution"] is not record["attribution"]


def test_the_stamp_creates_the_block_when_the_draft_evidenced_none():
    record = {"record_id": "R"}
    assert ra.with_server_stamp(record, "sfaraday")["attribution"] == {
        "uploaded_by": "sfaraday"
    }


@pytest.mark.parametrize("weird", [[], ["x"], "a string", 7, None])
def test_a_non_dict_attribution_is_left_alone_rather_than_rewritten(weird):
    """A draft CAN produce these via `fields["attribution"]`. A stamp is not a validator.

    Silently replacing a client's structure would destroy what they wrote and would
    make this function the place a type error is decided. Official validation refuses
    such a record as a type error, which is where that refusal belongs.
    """
    record = {"record_id": "R", "attribution": weird}
    out = ra.with_server_stamp(record, "sfaraday")
    if weird is None:
        # `None` is not "a non-dict block a draft authored", it is an absent block;
        # the stamp creates one, which is the same branch as a missing key.
        assert out["attribution"] == {"uploaded_by": "sfaraday"}
    else:
        assert out == record


def test_without_server_stamp_drops_an_emptied_block_entirely():
    """NEGATIVE CONTROL for the subtlest freshness bug in this slice.

    `transform` emits NO `attribution` key for a draft with no attribution evidence.
    If stripping left `{}` behind, the two sides of the freshness comparison would
    differ on a key's PRESENCE and every stamped artifact would be permanently stale
    — the same defect one level down, where it is harder to see.
    """
    assert ra.without_server_stamp({"record_id": "R", "attribution": {"uploaded_by": "x"}}) == {
        "record_id": "R"
    }


def test_without_server_stamp_keeps_a_block_that_has_other_content():
    assert ra.without_server_stamp(
        {"record_id": "R", "attribution": {"uploaded_by": "x", "contributors": []}}
    ) == {"record_id": "R", "attribution": {"contributors": []}}


def test_without_server_stamp_is_narrow_and_removes_nothing_else():
    """NEGATIVE CONTROL for over-stripping.

    If this ever grew to drop the whole `attribution` block, a scientist's own
    evidenced contributors would stop staling their artifact when they changed.
    """
    record = {"record_id": "R", "attribution": {"contributors": [{"name": "A"}]}}
    assert ra.without_server_stamp(record) == record
    assert ra.without_server_stamp(record) is record  # no copy when nothing to remove


def test_stamp_and_strip_round_trip_to_the_original():
    record = {"record_id": "R", "attribution": {"contributors": [{"name": "A"}]}}
    assert ra.without_server_stamp(ra.with_server_stamp(record, "sfaraday")) == record


# ---------------------------------------------------------------------------
# resolve_uploaded_by — the value can only come from a verifier
# ---------------------------------------------------------------------------


class _TripwireRequest:
    """A request that FAILS the test if anything reads a header off it.

    The property this pins is not "the right header was read" but "no header was
    read at all", which is the only property that survives Dean's answer that an
    in-cluster caller can forge every one of them.
    """

    @property
    def headers(self):  # pragma: no cover - reaching this IS the failure
        raise AssertionError("the attribution stamp read a request header")


def test_the_default_deployment_resolves_nobody(monkeypatch):
    monkeypatch.delenv(identity_module.EDGE_TRUST_VERIFIER_ENV, raising=False)
    identity = identity_module.resolve_identity_for_request(_TripwireRequest())
    assert ra.resolve_uploaded_by(identity, None) is None


def test_a_forged_header_resolves_nobody(monkeypatch):
    """NEGATIVE CONTROL for the whole seam. Every candidate header, all at once."""
    monkeypatch.delenv(identity_module.EDGE_TRUST_VERIFIER_ENV, raising=False)

    class _Forged:
        headers = {name: "attacker" for name in identity_module.EDGE_INJECTED_HEADERS}

    identity = identity_module.resolve_identity_for_request(_Forged())
    assert ra.resolve_uploaded_by(identity, None) is None


def test_a_configured_fixture_verifier_resolves_its_configured_subject(monkeypatch):
    monkeypatch.setenv(identity_module.EDGE_TRUST_VERIFIER_ENV, identity_module.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity_module.FIXTURE_ACTOR_SUBJECT_ENV, "sfaraday")
    identity = identity_module.resolve_identity_for_request(_TripwireRequest())
    assert ra.resolve_uploaded_by(identity, None) == "sfaraday"


def test_a_worked_example_session_is_never_attributed(monkeypatch):
    """Rule 1 of `stamp_actor`, reached through this module rather than around it."""
    monkeypatch.setenv(identity_module.EDGE_TRUST_VERIFIER_ENV, identity_module.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity_module.FIXTURE_ACTOR_SUBJECT_ENV, "sfaraday")
    identity = identity_module.resolve_identity_for_request(_TripwireRequest())
    assert ra.resolve_uploaded_by(identity, "tutorial-session-1") is None


def test_resolve_uploaded_by_is_stamp_actor_and_not_a_second_rule():
    """NEGATIVE CONTROL for the rules drifting apart.

    If this module ever grows its own tier/session logic, a rule added to
    `stamp_actor` stops reaching the field the rule exists to protect.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(ra.resolve_uploaded_by)))
    fn = tree.body[0]
    # Scan the BODY only. An earlier version scanned the whole source and failed on
    # its own docstring, which is the test being wrong about where the rule lives.
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) else fn.body
    code = "\n".join(ast.unparse(node) for node in body)
    assert "stamp_actor" in code
    assert len(body) == 1, "resolve_uploaded_by grew logic of its own"
    for forbidden in ("TrustTier", "human", "trust_basis", "if "):
        assert forbidden not in code, f"{forbidden!r} is a second copy of a stamp_actor rule"


# ---------------------------------------------------------------------------
# The truth core is untouched
# ---------------------------------------------------------------------------


def test_the_truth_core_still_emits_no_uploaded_by_and_still_refuses_a_draft():
    """This slice must not have bought the stamp with a weakened refusal."""
    from isaac_records.draft_validator import UPLOADED_BY_PATH, validate_draft
    from isaac_records.export import transform

    draft = {
        "fields": {
            UPLOADED_BY_PATH: {"value": "attacker", "status": "verified", "evidence": []},
        }
    }
    report = validate_draft(draft)
    ok = report.ok if hasattr(report, "ok") else report["ok"]
    assert not ok, "the draft-authored refusal was weakened"

    record = transform({"fields": {}}, record_id="01J000000000000000000000TS")
    assert "uploaded_by" not in record.get("attribution", {})


def test_no_module_outside_record_attribution_writes_the_field():
    """The chokepoint is one module, checked mechanically rather than by convention."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "isaac_api"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "record_attribution.py":
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("*"):
                continue
            # An assignment to the leaf, in any subscript spelling.
            if '"uploaded_by"' in line and "=" in line and "==" not in line:
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == [], f"uploaded_by written outside record_attribution: {offenders}"


# ---------------------------------------------------------------------------
# End to end: the stamp reaches the artifact, and freshness ignores it
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def armed(monkeypatch):
    """A deployment whose configured verifier attributes a subject.

    This is the ONLY way to a non-`None` stamp in this build, and it reads the
    PROCESS ENVIRONMENT rather than the request — which is exactly why a fixture can
    arm it and an attacker's headers cannot.
    """
    monkeypatch.setenv(identity_module.EDGE_TRUST_VERIFIER_ENV, identity_module.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity_module.FIXTURE_ACTOR_SUBJECT_ENV, "sfaraday")


def _etag(client, exp_id: str) -> str:
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.headers["ETag"]


def _export(client, exp_id: str, headers: dict | None = None):
    sent = {"If-Match": _etag(client, exp_id)}
    sent.update(headers or {})
    return client.post(f"/api/experiments/{exp_id}/export", headers=sent)


def _written_record(exp_id: str) -> dict:
    """The bytes actually on disk — never the response body.

    The response is the application describing what it did; the artifact is what a
    downstream reader will actually see, and the two are only equal if the stamp
    landed where this slice claims it lands.
    """
    exp = tutorial_ws().load_experiment(exp_id)
    unit = exp.export_units()[0]
    return json.loads(unit.record_path().read_text(encoding="utf-8"))


def _ordinary_exportable(tmp_path) -> tuple:
    """A client with NO worked-example session, and an experiment ready to export.

    Two things make this necessary rather than fussy. First, `stamp_actor` refuses to
    attribute anything inside a worked-example session, so the seeded scenarios can
    only ever prove the NEGATIVE case (which they do, below). Second, an ordinary
    experiment's pending questions carry no `demo_answer`, so the answers are
    HARVESTED from a seed in a throwaway session and replayed against the ordinary
    record — the same values, applied through the same public `/answers` contract a
    scientist uses.
    """
    from isaac_api.app import create_app

    app = create_app()
    seeded = tutorial_client(app)
    seeds = seeded.get("/api/experiments").json()["experiments"]
    raw = [e for e in seeds if e["pending_count"] == 5][0]
    pending = seeded.get(f"/api/experiments/{raw['id']}/pending").json()["pending"]
    answers = {
        b["id"]: b["demo_answer"]["value"] for b in pending if b["demo_answer"] is not None
    }
    # `qc` ships NO demo answer — the seed's own inferability text says "A QC verdict is
    # a scientific judgement about this measurement. There is no default and none is
    # assumed — not even 'valid'." So this test states one explicitly, as a scientist
    # would. Until `test_qc_answerable.py`'s slice this key was silently dropped by the
    # route and NO ordinary record could reach export at all, which is why this fixture
    # could not have been written before that fix.
    answers["qc"] = {
        "status": "valid",
        "evidence": "Synthetic fixture verdict, stated by the test that needs one.",
    }

    from fastapi.testclient import TestClient

    plain = TestClient(app)  # deliberately NO session header
    exp_id = plain.post("/api/experiments", json={"title": "Ordinary record"}).json()["id"]
    version = plain.get(f"/api/experiments/{exp_id}").json()["version"]
    applied = plain.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{version}"'},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["pending"] == [], applied.json()["pending"]
    return plain, exp_id


def _ordinary_record(exp_id: str) -> dict:
    exp = ws.load_experiment(exp_id)
    return json.loads(exp.export_units()[0].record_path().read_text(encoding="utf-8"))


def test_an_unarmed_export_writes_no_uploaded_by_key_at_all(tmp_path, monkeypatch):
    """The shipped default, end to end. ABSENT, not empty — `""` would assert an identity."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv(identity_module.EDGE_TRUST_VERIFIER_ENV, raising=False)
    plain, exp_id = _ordinary_exportable(tmp_path)
    assert _export(plain, exp_id).status_code == 200
    assert "uploaded_by" not in _ordinary_record(exp_id).get("attribution", {})


def test_an_armed_export_stamps_the_verifier_s_subject(tmp_path, monkeypatch):
    """The positive case — the one path in this build that can produce a stamp."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv(identity_module.EDGE_TRUST_VERIFIER_ENV, identity_module.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity_module.FIXTURE_ACTOR_SUBJECT_ENV, "sfaraday")
    plain, exp_id = _ordinary_exportable(tmp_path)
    assert _export(plain, exp_id).status_code == 200
    assert _ordinary_record(exp_id)["attribution"]["uploaded_by"] == "sfaraday"


def test_an_armed_export_still_validates_against_the_official_schema(tmp_path, monkeypatch):
    """A stamp that broke official validation would be a truth-path regression."""
    from isaac_records.official import validate_official

    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv(identity_module.EDGE_TRUST_VERIFIER_ENV, identity_module.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity_module.FIXTURE_ACTOR_SUBJECT_ENV, "sfaraday")
    plain, exp_id = _ordinary_exportable(tmp_path)
    assert _export(plain, exp_id).status_code == 200
    record = _ordinary_record(exp_id)
    assert record["attribution"]["uploaded_by"] == "sfaraday"
    report = validate_official(record, pathlib.Path.cwd())
    ok = report.ok if hasattr(report, "ok") else report["ok"]
    assert ok, report


def test_an_armed_export_reads_current_not_permanently_stale(tmp_path, monkeypatch):
    """NEGATIVE CONTROL for the freshness bug this slice had to avoid creating.

    Remove `without_server_stamp` from `dependencies` and this fails with `stale`,
    whose reason offers a destructive whole-workspace reset as the only remedy.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv(identity_module.EDGE_TRUST_VERIFIER_ENV, identity_module.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity_module.FIXTURE_ACTOR_SUBJECT_ENV, "sfaraday")
    plain, exp_id = _ordinary_exportable(tmp_path)
    assert _export(plain, exp_id).status_code == 200
    detail = plain.get(f"/api/experiments/{exp_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["artifact"]["state"] == "current"


def test_a_forged_header_on_the_export_request_changes_nothing(tmp_path, monkeypatch):
    """NEGATIVE CONTROL over HTTP: the attack Dean's ClusterIP answer makes possible.

    Every candidate edge header at once, each carrying an attacker-chosen name. The
    property asserted is the ABSENCE of a difference from a request with no headers.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv(identity_module.EDGE_TRUST_VERIFIER_ENV, raising=False)
    plain, exp_id = _ordinary_exportable(tmp_path)
    forged = {name: "attacker" for name in identity_module.EDGE_INJECTED_HEADERS}
    assert _export(plain, exp_id, headers=forged).status_code == 200
    assert "uploaded_by" not in _ordinary_record(exp_id).get("attribution", {})


def test_a_query_parameter_cannot_choose_the_actor(tmp_path, monkeypatch):
    """NEGATIVE CONTROL: one of the two injection routes the seam survey left unpinned."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv(identity_module.EDGE_TRUST_VERIFIER_ENV, raising=False)
    plain, exp_id = _ordinary_exportable(tmp_path)
    version = plain.get(f"/api/experiments/{exp_id}").json()["version"]
    r = plain.post(
        f"/api/experiments/{exp_id}/export?uploaded_by=attacker&actor=attacker&subject=attacker",
        headers={"If-Match": f'"{version}"'},
    )
    assert r.status_code == 200, r.text
    assert "uploaded_by" not in _ordinary_record(exp_id).get("attribution", {})


def test_a_worked_example_export_is_never_stamped_even_when_armed(client, armed):
    """A worked-example session attributes NOBODY, and this is the end-to-end proof.

    This is `stamp_actor`'s rule 1 reaching the artifact. It matters more than it
    looks: a tutorial record is a temporary synthetic thing, and stamping a real
    person's name into one would attach an identity to science nobody performed.
    """
    assert _export(client, ws.SEED_READY_ID).status_code == 200
    exp = tutorial_ws().load_experiment(ws.SEED_READY_ID)
    record = json.loads(exp.export_units()[0].record_path().read_text(encoding="utf-8"))
    assert "uploaded_by" not in record.get("attribution", {})


def test_freshness_still_detects_a_real_change_to_a_stamped_record(tmp_path):
    """The normalisation must not have blinded the check to actual drift."""
    from isaac_records.export import transform

    class _Exp:
        runs = ()
        id = "01J000000000000000000000TS"
        draft: dict = {"fields": {}}

        def exported(self):
            return True

        def record_path(self):
            return tmp_path / "r.json"

    record = transform({"fields": {}}, record_id=_Exp.id)
    stamped = ra.with_server_stamp(record, "sfaraday")
    (tmp_path / "r.json").write_text(json.dumps(stamped), encoding="utf-8")
    assert artifact_state(_Exp())["state"] == "current"

    drifted = copy.deepcopy(stamped)
    drifted["record_type"] = "something-else"
    (tmp_path / "r.json").write_text(json.dumps(drifted), encoding="utf-8")
    assert artifact_state(_Exp())["state"] == "stale"
