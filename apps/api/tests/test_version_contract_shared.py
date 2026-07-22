"""P27.4 — shared typed version contract + one-release compatibility boundary.

TEST-FIRST acceptance contract (authored BEFORE the P27.4 refactor; RED until a
single canonical version-contract module exists). P27.3 shipped the behaviour
(ETag / If-Match / 412 / compat grace); P27.4 does NOT change any observable
behaviour — it consolidates the version envelope + the deprecation signal +
the one-release grace toggle into ONE typed, documented, testable source that
the P27.5 frontend consumes and whose single toggle the later strict slice flips
to 428. This is a maintainability/rollout-safety slice.

Pinned here:
  * a module `isaac_api.version_contract` exposes: `VersionEnvelope` (typed
    rev/updated_utc/version), `version_fields(exp)` (the single producer of the
    envelope dict), `DEPRECATION_HEADER` / `DEPRECATION_VALUE` (the non-noisy
    missing-If-Match signal), and `precondition_required()` (the ONE grace toggle
    — False during the P27.3/P27.4 grace; the strict slice flips it after the
    deployed frontend is verified sending If-Match).
  * the three version-bearing responses (detail, answers, export) all serialise
    the SAME envelope shape, and it validates against `VersionEnvelope`.
  * the grace is a single boolean point, not a scattered magic string.

All fixtures synthetic; truth core untouched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _real_answers_payload():
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


# --- 1. the canonical module exists and exposes the contract ------------------


def test_version_contract_module_exposes_the_contract():
    from isaac_api import version_contract as vc

    assert hasattr(vc, "VersionEnvelope")
    assert hasattr(vc, "version_fields")
    assert isinstance(vc.DEPRECATION_HEADER, str) and vc.DEPRECATION_HEADER
    assert isinstance(vc.DEPRECATION_VALUE, str) and "if-match" in vc.DEPRECATION_VALUE.lower()
    assert hasattr(vc, "precondition_required")


def test_precondition_required_is_the_single_grace_toggle():
    """During the P27.3/P27.4 grace the toggle is OFF (missing If-Match is
    accepted). It is one boolean function — the single point the strict slice
    flips — not a scattered constant."""
    from isaac_api import version_contract as vc

    assert vc.precondition_required() is False


def test_version_fields_produces_a_valid_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api import version_contract as vc

    ws.ensure_seeded()
    exp = ws.load_experiment(ws.SEED_NEW_DRAFT_ID)
    fields = vc.version_fields(exp)
    assert set(fields) == {"rev", "updated_utc", "version"}
    # validates against the typed model without error
    env = vc.VersionEnvelope(**fields)
    assert env.rev == exp.rev
    assert env.version == exp.version_token()


# --- 2. all version-bearing responses use the SAME shape ----------------------


def test_detail_response_conforms_to_envelope(client):
    from isaac_api import version_contract as vc

    body = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    env = vc.VersionEnvelope(**{k: body[k] for k in ("rev", "updated_utc", "version")})
    assert env.version == body["version"]


def test_answers_and_export_responses_conform_to_envelope(client):
    from isaac_api import version_contract as vc

    a = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload()
    ).json()
    vc.VersionEnvelope(**{k: a[k] for k in ("rev", "updated_utc", "version")})

    e = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export").json()
    vc.VersionEnvelope(**{k: e[k] for k in ("rev", "updated_utc", "version")})


# --- 3. the deprecation signal is the module's named value --------------------


def test_missing_if_match_uses_the_named_deprecation_signal(client):
    from isaac_api import version_contract as vc

    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload()
    )
    assert r.status_code == 200
    assert r.headers.get(vc.DEPRECATION_HEADER) == vc.DEPRECATION_VALUE
