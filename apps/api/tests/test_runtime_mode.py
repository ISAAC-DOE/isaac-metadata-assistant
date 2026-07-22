"""P27.1 — authoritative synthetic-only runtime mode (RED-first contract).

One authoritative source (`isaac_api.runtime_mode`) decides synthetic-only vs.
real for BOTH the reset governance guard and the `/health` mode banner, replacing
the two independent hard-coded literals. Semantics are fail-closed:

  * unset / `synthetic-only` / any invalid value  -> resolves to synthetic-only,
  * only an explicit, valid `real` grants real mode,
  * `validate_runtime_mode_or_raise()` refuses to let the app boot when the env is
    set to an invalid value OR to `real` (real-data guardrails are not implemented),
  * `create_app()` runs that validation first, so a misconfigured container cannot
    silently boot in a permissive state.

All checks are deterministic and touch no truth-core code.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from isaac_api import runtime_mode as rm

ENV = "ISAAC_RUNTIME_MODE"


# --- runtime_mode() / is_synthetic_only() resolution --------------------------


def test_unset_defaults_to_synthetic_only(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert rm.runtime_mode() == "synthetic-only"
    assert rm.is_synthetic_only() is True
    rm.validate_runtime_mode_or_raise()  # must not raise


def test_explicit_synthetic_only(monkeypatch):
    monkeypatch.setenv(ENV, "synthetic-only")
    assert rm.runtime_mode() == "synthetic-only"
    assert rm.is_synthetic_only() is True
    rm.validate_runtime_mode_or_raise()  # must not raise


def test_synthetic_only_is_whitespace_tolerant(monkeypatch):
    monkeypatch.setenv(ENV, "  synthetic-only  ")
    assert rm.runtime_mode() == "synthetic-only"
    assert rm.is_synthetic_only() is True
    rm.validate_runtime_mode_or_raise()  # must not raise


def test_real_resolves_but_is_unsupported(monkeypatch):
    monkeypatch.setenv(ENV, "real")
    assert rm.runtime_mode() == "real"
    assert rm.is_synthetic_only() is False
    with pytest.raises(RuntimeError):
        rm.validate_runtime_mode_or_raise()


@pytest.mark.parametrize("value", ["prod", "REAL", "Synthetic", "synthetic", "yes"])
def test_invalid_values_fail_closed_and_raise(monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    # Fail-closed: an unrecognised value NEVER grants real mode.
    assert rm.runtime_mode() == "synthetic-only"
    assert rm.is_synthetic_only() is True
    # But it is still a misconfiguration -> boot-time validation refuses.
    with pytest.raises(RuntimeError):
        rm.validate_runtime_mode_or_raise()


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_empty_or_whitespace_is_invalid_and_raises(monkeypatch, value):
    # Documented choice: an explicitly-set but empty/whitespace-only value is a
    # misconfiguration (someone set the var and left it blank), so it fails
    # closed for resolution AND raises at boot.
    monkeypatch.setenv(ENV, value)
    assert rm.runtime_mode() == "synthetic-only"
    assert rm.is_synthetic_only() is True
    with pytest.raises(RuntimeError):
        rm.validate_runtime_mode_or_raise()


# --- create_app() boot-time validation ----------------------------------------


def _create_app():
    from isaac_api.app import create_app

    return create_app()


def test_create_app_ok_when_unset(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    app = _create_app()
    assert app is not None


def test_create_app_ok_when_synthetic_only(monkeypatch):
    monkeypatch.setenv(ENV, "synthetic-only")
    app = _create_app()
    assert app is not None


def test_create_app_raises_when_real(monkeypatch):
    monkeypatch.setenv(ENV, "real")
    with pytest.raises(RuntimeError):
        _create_app()


def test_create_app_raises_when_invalid(monkeypatch):
    monkeypatch.setenv(ENV, "prod")
    with pytest.raises(RuntimeError):
        _create_app()


# --- health endpoint uses the authoritative source ----------------------------


def test_health_mode_default_is_synthetic_only(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    client = TestClient(_create_app())
    assert client.get("/api/health").json()["mode"] == "synthetic-only"


def test_health_mode_matches_runtime_mode(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "synthetic-only")
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    client = TestClient(_create_app())
    assert client.get("/api/health").json()["mode"] == rm.runtime_mode()
