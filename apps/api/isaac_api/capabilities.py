"""TWO CAPABILITY DECLARATIONS a surface reads BEFORE offering a control that would fail.

~~Both are derived from CONFIGURATION ALONE and open nothing — no connection, no request,
no file~~ — **corrected 2026-09-22 after an independent review**, because with staging
enabled that was false: every health read listed the staging directory, and a root made
unreadable (``chmod 000``) turned the readiness probe into a ``500``. What is true now:

* ``/api/health`` reads CONFIGURATION plus ONE ``stat`` and one access check of the
  staging root (:func:`staging_status`). It never lists the directory and never opens a
  file, and every ``OSError`` becomes ``enabled: false`` with a stable reason — so
  nothing here can change the probe's status code.
* The detail block (``GET /api/imports`` and each import session) additionally LISTS
  that ONE directory's direct entries by name. It never opens a file's contents either,
  and a listing that fails is reported the same way (``staging_root_unreadable``).
* The acceptance preflight opens nothing at all.

1. ``historical_file_ingestion`` — ``EXT-13``
=============================================

**DISABLED BY DEFAULT, AND ENABLING IT IS CONFIGURATION, NEVER A REWRITE.** Until this
module, the *behaviour* was already right — ``POST /api/uploads`` is an unconditional
``403``, staging is browser-local, and a SHA-256 is computed client-side over bytes the
server never sees — but there was no named switch, so activating real-byte ingestion
would have been a code change. ``docs/session-closure-2026-09-18.md`` §8 named that as
residue.

What the switch does, precisely, because "ingestion" invites a larger reading than is
true:

* **It never opens ``POST /api/uploads``.** That route stays ``403`` in every
  configuration; ``apps/web/src/__tests__/upload-claim-parity.test.tsx`` pins the claims
  about it and their polarity, and nothing here moves them.
* **When enabled, the ONLY new path is a server-side STAGING DIRECTORY** an operator
  populates (:data:`STAGING_ROOT_ENV`). Its folders and ZIPs become additional names the
  existing archive-attach operation accepts, walked by the SAME bounded, traversal-safe,
  size-limited :mod:`isaac_api.bl15.archive` walk that reads the committed fixtures. The
  bytes are read for evidence only; none of them becomes an official record byte, and no
  digest computed inside the walk is ever published as a manifest ``sha256``.
* **Enabling it for REAL scientific files is ``EXT-13``'s decision** — retention,
  location, classification and deletion path, owned by institutional data governance via
  Hao — and **no shipped deploy artifact sets it** (``test_deploy_config.py`` pins that).
  In this repository it is enabled only by tests, over sanitized synthetic fixtures.

2. ``proposals.acceptance`` — the trusted-actor gate, made visible in advance
=============================================================================

Accepting an ingestion proposal answers ``409 human_actor_required`` with reason
``no_verifier_configured`` in every default deployment, because no trusted
authentication boundary exists in this build (``EXT-01``). A scientist should learn that
BEFORE a guaranteed-failing click. :func:`proposal_acceptance` derives the answer from the
SAME resolution the accept route uses — ``identity.resolve_request_identity`` over the
configured verifier's verdict — rather than from a second description of it, so the two
cannot disagree. **It does not weaken or change the 409**; it only reports it early.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

__all__ = [
    "INGESTION_ENV",
    "INGESTION_MODE_STAGING",
    "STAGING_ROOT_ENV",
    "historical_file_ingestion",
    "proposal_acceptance",
    "staged_archive_names",
    "staged_archive_root",
    "staging_status",
]

#: The switch. Unset, empty or any value other than :data:`INGESTION_MODE_STAGING`
#: fails closed to DISABLED — an accident must never enable byte ingestion.
INGESTION_ENV = "ISAAC_HISTORICAL_FILE_INGESTION"
#: The one enabling value. Named for what it enables — a staging directory — so that a
#: reader of a deployment manifest cannot mistake it for an upload switch.
INGESTION_MODE_STAGING = "staging_directory"
#: Where staged archives live when enabled. Its VALUE is never served: ``/api/health``
#: answers without credentials, and a filesystem path is deployment detail.
STAGING_ROOT_ENV = "ISAAC_HISTORICAL_STAGING_ROOT"

REASON_GOVERNANCE_NOT_APPROVED = "governance_not_approved"
#: The mode is set and no root is named.
REASON_STAGING_ROOT_MISSING = "staging_root_not_configured"
#: A root is named and each of these is what is actually wrong with it — reported by name
#: rather than folded into "not configured", which would send an operator to the wrong fix.
REASON_STAGING_ROOT_ABSENT = "staging_root_missing"
REASON_STAGING_ROOT_NOT_A_DIRECTORY = "staging_root_not_a_directory"
REASON_STAGING_ROOT_IS_SYMLINK = "staging_root_is_symlink"
REASON_STAGING_ROOT_UNREADABLE = "staging_root_unreadable"
INGESTION_REASONS: frozenset[str] = frozenset(
    {
        REASON_GOVERNANCE_NOT_APPROVED,
        REASON_STAGING_ROOT_MISSING,
        REASON_STAGING_ROOT_ABSENT,
        REASON_STAGING_ROOT_NOT_A_DIRECTORY,
        REASON_STAGING_ROOT_IS_SYMLINK,
        REASON_STAGING_ROOT_UNREADABLE,
    }
)

#: A staged archive name: a bare folder or ``.zip`` name, no separator, no dot-segment.
#: Anchored ``\A``/``\Z`` for the reason ``historical_import._FIXTURE_NAME_RE`` is.
_STAGED_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,120}\Z")
#: Staged names are namespaced so they can never collide with a committed fixture name.
STAGED_PREFIX = "staged:"
#: Most staged archives offered at once. A bound on what is LISTED, disclosed in the block.
MAX_STAGED_ARCHIVES = 50


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def staging_status(env: Mapping[str, str] | None = None) -> tuple[Path | None, str | None]:
    """``(root, None)`` when staging is enabled and usable, else ``(None, reason)``.

    CONFIGURATION PLUS ONE ``stat`` AND ONE ACCESS CHECK of the named root. It never lists
    the directory and never opens a file, and it NEVER RAISES: an ``OSError`` anywhere is
    ``staging_root_unreadable``. That is what lets ``/api/health`` — the readiness probe —
    call it.
    """
    values = _env(env)
    if (values.get(INGESTION_ENV) or "").strip() != INGESTION_MODE_STAGING:
        return None, REASON_GOVERNANCE_NOT_APPROVED
    raw = (values.get(STAGING_ROOT_ENV) or "").strip()
    if not raw:
        return None, REASON_STAGING_ROOT_MISSING
    root = Path(raw)
    try:
        if root.is_symlink():
            return None, REASON_STAGING_ROOT_IS_SYMLINK
        if not root.exists():
            return None, REASON_STAGING_ROOT_ABSENT
        if not root.is_dir():
            return None, REASON_STAGING_ROOT_NOT_A_DIRECTORY
        if not os.access(root, os.R_OK | os.X_OK):
            return None, REASON_STAGING_ROOT_UNREADABLE
    except OSError:
        return None, REASON_STAGING_ROOT_UNREADABLE
    return root, None


def staged_archive_root(env: Mapping[str, str] | None = None) -> Path | None:
    """The staging directory when ingestion is enabled AND usable, else ``None``."""
    return staging_status(env)[0]


def _list_staged(root: Path) -> tuple[tuple[str, ...], str | None]:
    """Names of the staged archives directly inside ``root`` — ONE directory, by name only.

    ``(names, None)``, or ``((), "staging_root_unreadable")`` when listing fails. Never
    opens a file's contents and never raises.
    """
    names: list[str] = []
    try:
        for child in sorted(root.iterdir()):
            if child.is_symlink() or not _STAGED_NAME_RE.fullmatch(child.name):
                continue
            if child.is_dir() or (child.is_file() and child.suffix.lower() == ".zip"):
                names.append(f"{STAGED_PREFIX}{child.name}")
            if len(names) >= MAX_STAGED_ARCHIVES:
                break
    except OSError:
        return (), REASON_STAGING_ROOT_UNREADABLE
    return tuple(names), None


def staged_archive_names(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """``staged:<name>`` for every folder or ``.zip`` directly inside the staging root.

    Empty when disabled or when the root cannot be listed. Only DIRECT children with an
    allowlisted name are offered, and a symlink is never offered — the walk would refuse
    it anyway, and listing something that will be refused is a control that promises
    work that cannot happen.
    """
    root = staged_archive_root(env)
    if root is None:
        return ()
    return _list_staged(root)[0]


def resolve_staged(name: str, env: Mapping[str, str] | None = None) -> Path | None:
    """The path of one staged archive, or ``None``. Membership is the traversal boundary."""
    if name not in staged_archive_names(env):
        return None
    root = staged_archive_root(env)
    assert root is not None  # staged_archive_names returned it
    return root / name[len(STAGED_PREFIX):]


def historical_file_ingestion(env: Mapping[str, str] | None = None) -> dict:
    """The capability block. CONFIGURATION, one ``stat``, and a listing of ONE directory
    by name — never a file's contents, never a path, and never an exception."""
    root, reason = staging_status(env)
    names: tuple[str, ...] = ()
    if root is not None:
        names, listing_error = _list_staged(root)
        if listing_error is not None:
            root, reason = None, listing_error
    enabled = root is not None
    return {
        "enabled": enabled,
        "reason": reason,
        "basis": "configuration_only",
        "governance_gate": "EXT-13",
        # WHAT ENABLING DOES, stated in the block so no surface infers more.
        "uploads_route_open": False,
        "path_when_enabled": "server_side_staging_directory",
        "staged_archive_count": len(names) if enabled else 0,
        "staged_archive_limit": MAX_STAGED_ARCHIVES,
    }


class _NoRequest:
    """What the capability probe hands the verifier INSTEAD of a request.

    Both shipped verifiers never touch their argument (``identity.py`` pins that with a
    test that passes an object raising on every attribute access), so this reads the
    same verdict the accept route would get. A FUTURE verifier that did read the
    request would raise here, and :func:`proposal_acceptance` then reports that the
    answer depends on the request rather than guessing it.
    """

    __slots__ = ()

    def __getattr__(self, name: str):  # pragma: no cover - reached only by a future verifier
        raise AttributeError(name)


def proposal_acceptance() -> dict:
    """Whether accepting a proposal CAN succeed in this deployment, and if not, why.

    ``reason`` is the SAME code the accept route's ``409`` carries
    (``human_actor_required`` -> ``reason``), because it is computed the same way.
    """
    from . import identity  # noqa: PLC0415 - avoids an import cycle at module load

    verifier = identity.edge_trust_verifier()
    try:
        resolved = identity.resolve_request_identity(verifier.verify(_NoRequest()))
    except Exception:  # pragma: no cover - only a verifier that reads the request
        return {
            "available": None,
            "reason": "depends_on_request",
            "basis": "configuration_only",
            "verifier_id": getattr(verifier, "verifier_id", None),
            "refusal_error": identity.HUMAN_ACTOR_REQUIRED_ERROR,
        }
    available = resolved.trust is identity.TrustTier.EDGE_HUMAN and resolved.human is not None
    return {
        "available": available,
        "reason": None if available else (
            resolved.refusal.value if resolved.refusal is not None else "service_principal_not_attributable"
        ),
        "basis": "configuration_only",
        "verifier_id": getattr(verifier, "verifier_id", None),
        # The typed error a click would receive, so a surface can match it.
        "refusal_error": None if available else identity.HUMAN_ACTOR_REQUIRED_ERROR,
        "refusal_status": None if available else 409,
        "trust_basis_when_available": (
            resolved.human.trust_basis if available and resolved.human is not None else None
        ),
    }


# --- what `/api/health` serves ------------------------------------------------
#
# THE HEALTH BANNER CARRIES TWO KEYS PER CAPABILITY, AND ONLY TWO: the shape the
# frontend builds against (`{enabled, reason}` and `{available, reason}`), agreed with
# the orchestrator on 2026-09-22. Each comes from the SAME decision function as the
# full block above, never a second description of it. The ingestion banner stops short
# of the directory listing the detail block performs — see
# `health_historical_file_ingestion`. The detail (the governance gate, that the
# upload route stays closed, the verifier id, the typed error a click would receive)
# lives there, not here: the banner answers without credentials and stays small.

HEALTH_INGESTION_KEYS: tuple[str, ...] = ("enabled", "reason")
HEALTH_ACCEPTANCE_KEYS: tuple[str, ...] = ("available", "reason")


def health_historical_file_ingestion(env: Mapping[str, str] | None = None) -> dict:
    """``{enabled, reason}`` from :func:`staging_status` — the SAME decision the detail
    block starts from, WITHOUT the directory listing (2026-09-22): the readiness probe
    reads configuration and one ``stat``, nothing more, and cannot raise. The two can
    differ only if the root passes its access check and its listing then fails, in
    which case the detail block reports ``staging_root_unreadable``."""
    root, reason = staging_status(env)
    return {"enabled": root is not None, "reason": reason}


def health_proposal_acceptance() -> dict:
    """``{available, reason}`` — projected from :func:`proposal_acceptance`.

    ``reason`` is the code the accept route's ``409`` carries in its own ``reason``
    field, because both come out of the same verifier resolution.
    """
    block = proposal_acceptance()
    return {key: block[key] for key in HEALTH_ACCEPTANCE_KEYS}

