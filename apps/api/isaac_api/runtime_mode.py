"""Authoritative runtime-mode source for the ISAAC local UI backend.

This module is the SINGLE source of truth for whether the deployment is the
synthetic-only demo or a (currently unsupported) real-data deployment. Both the
reset governance guard (via ``workspace.is_synthetic_only``) and the ``/health``
``mode`` banner read from here, replacing the two independent hard-coded literals
that previously drifted from one another.

Semantics are deliberately FAIL-CLOSED — an accident must never grant real mode:

  * env var ``ISAAC_RUNTIME_MODE`` unset            -> ``synthetic-only``
  * value ``"synthetic-only"`` (whitespace-trimmed)  -> ``synthetic-only``
  * value ``"real"``           (whitespace-trimmed)  -> ``real``
  * ANY other value (incl. empty/whitespace-only)    -> ``synthetic-only``

Resolution never raises: it always yields a usable, safe mode. Detection of a
misconfiguration is the job of ``validate_runtime_mode_or_raise()``, which the
app factory calls at boot so a container configured for ``real`` or with a
garbage value fails to construct rather than booting in a surprising state.

Real mode is intentionally recognised as a distinct value but is NOT yet
supported: the real-data ingestion/governance guardrails do not exist (Phase 31
owns ingestion), so validation refuses to boot in ``real`` mode until they do.
"""

from __future__ import annotations

import os

RUNTIME_MODE_ENV = "ISAAC_RUNTIME_MODE"

SYNTHETIC_ONLY = "synthetic-only"
REAL = "real"

_VALID = {SYNTHETIC_ONLY, REAL}


def _raw() -> str | None:
    """The raw env value, or ``None`` if the var is unset."""
    return os.environ.get(RUNTIME_MODE_ENV)


def runtime_mode() -> str:
    """Resolve the effective runtime mode, fail-closed.

    Returns ``REAL`` only for an explicit, valid ``real`` value; every other
    case (unset, ``synthetic-only``, or anything unrecognised) resolves to
    ``SYNTHETIC_ONLY``. Never raises.
    """
    raw = _raw()
    if raw is None:
        return SYNTHETIC_ONLY
    value = raw.strip()
    if value == REAL:
        return REAL
    # synthetic-only, and every invalid/empty value, fail closed to synthetic.
    return SYNTHETIC_ONLY


def is_synthetic_only() -> bool:
    """True when the effective mode is synthetic-only (the fail-closed default)."""
    return runtime_mode() == SYNTHETIC_ONLY


def validate_runtime_mode_or_raise() -> None:
    """Raise ``RuntimeError`` for a misconfigured runtime mode; else return.

    Passes when ``ISAAC_RUNTIME_MODE`` is unset or exactly ``synthetic-only``
    (whitespace-trimmed). Raises when the var is set to:

      * ``real`` — recognised but unsupported (real-data guardrails not built), or
      * any other value, including empty/whitespace-only — a configuration error.

    Called at the start of ``create_app()`` so a misconfigured container fails to
    boot instead of silently running in the fail-closed synthetic default.
    """
    raw = _raw()
    if raw is None:
        return
    value = raw.strip()
    if value == SYNTHETIC_ONLY:
        return
    if value == REAL:
        raise RuntimeError(
            f"{RUNTIME_MODE_ENV}='real' is not supported: real-data ingestion and "
            "governance guardrails are not implemented. Unset the variable or set "
            f"it to '{SYNTHETIC_ONLY}'."
        )
    raise RuntimeError(
        f"{RUNTIME_MODE_ENV}={raw!r} is invalid. Expected '{SYNTHETIC_ONLY}' or "
        f"'{REAL}' (unset defaults to '{SYNTHETIC_ONLY}')."
    )
