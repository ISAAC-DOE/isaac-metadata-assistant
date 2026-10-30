"""Local import bundles: the questions screen and the import progress page, LOCAL-ONLY.

WHAT THIS IS
============
``isaac import`` turns a beamtime folder into a bundle (``apps/api/isaac_api/local_import/``) and
``isaac bundle questions`` lists what a scientist must answer. This router lets the website show
those questions, and record an answer, for bundles that sit in ONE directory on the scientist's
own machine.

IT EXISTS ONLY WHEN THE PROCESS IS STARTED WITH ``ISAAC_LOCAL_BUNDLES_DIR``
==========================================================================
``app.create_app`` includes this router only when :data:`LOCAL_BUNDLES_ENV` names a directory —
the same arrangement as the MCP transport: the default (and every hosted) deployment registers
no route at all, so ``/api/local-bundles/*`` is the ordinary JSON 404 and the OpenAPI document
does not mention it. Each request re-reads the variable as well, so a process whose environment
lost it answers 404 too. A base path (``ISAAC_BASE_PATH``, which only a deployment sets) refuses
to boot with it, because a bundle holds a scientist's real metadata and must never be served.

WHAT IT SERVES, AND WHAT IT NEVER DOES
======================================
* Only what a bundle already holds — its questions, the quotes and locators its evidence
  records, its counts — and the ``validation/<group>.json`` reports ``isaac bundle validate``
  wrote into it. Never a source file: nothing here opens the imported folder.
* A bundle is named by its folder name directly inside the directory. A name with a path
  separator, ``..``, a leading dot, or one that resolves (symlinks followed) outside the
  directory is refused as "no such bundle"; ``bundle.json`` is opened only through
  ``records.contained_file``.
* WRITES go through ``mutations.decide_question`` (``isaac bundle decide --question``) and
  ``mutations.mutate`` + ``record_decision`` (``isaac bundle decide --target``) — the CLI's own
  code — with the typed ``by`` name and identity ``local_unverified``. Every write names the
  ``bundle_version`` it was shown (428 without one) and is refused (412) when the stored bundle is
  no longer that version, checked under the bundle's own lock, so a concurrent CLI write is never
  lost. Nothing is uploaded and no portal is called.
* Reading the questions RECORDS AN EXPOSURE for every parser value it shows (the blind protocol,
  as ``isaac bundle questions`` does), so it can write ``bundle.json``; it says how many it recorded.
"""

from __future__ import annotations

import functools
import hashlib
import ipaddress
import json
import os
import re
import sys
from collections import OrderedDict
from contextlib import ExitStack, contextmanager
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Body, Depends, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

LOCAL_BUNDLES_ENV = "ISAAC_LOCAL_BUNDLES_DIR"
#: The page origins that may use these routes — THEIR OWN list, not the app's CORS allowlist
#: (``ISAAC_UI_CORS_ORIGINS``), so an origin added there for another reason never reaches a bundle.
#: Comma-separated; only loopback ``http(s)://host:port`` origins are honoured (anything else is
#: ignored, with a warning at start-up). Default: the ISAAC web dev server (``apps/web/vite.config.ts``).
LOCAL_BUNDLES_ORIGINS_ENV = "ISAAC_LOCAL_BUNDLES_ORIGINS"
DEFAULT_LOCAL_BUNDLES_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
TAG_LOCAL_BUNDLES = "Local Import Bundles"
LOCAL_BUNDLES_TAG: dict = {
    "name": TAG_LOCAL_BUNDLES,
    "description": (
        "Local-only: the questions a local import bundle asks and the progress of each import, for "
        "bundles in one directory on the computer running this server. Present only when that "
        "directory is configured at start-up; no hosted deployment has it. An answer is recorded "
        "by the same code as the command-line `isaac bundle decide`, as a local, unverified "
        "statement by the name typed. Nothing is uploaded."
    ),
}

#: The page bound of ``isaac bundle questions`` (``cli.MAX_LIMIT``), read at import time.
from .local_import import cli as _cli  # noqa: E402

MAX_LIMIT = _cli.MAX_LIMIT
#: How many targets of one question the screen describes (run names, suggestions). The full target
#: list is always in ``targets``; ``display.targets_described`` says how many were described.
DESCRIBE_TARGETS = 40
SUGGESTIONS_PER_QUESTION = 12
FIELD_KINDS = ("missing_value", "optional_values", "confirm_value", "resolve_conflict")
#: The target decisions the screen may record outside a consolidated question: the 1.6.0 capture
#: decisions and a merge. Every other ``decide --target`` stays a CLI act.
CAPTURE_DECISIONS = frozenset({("merge_candidate", "keep_apart"), ("record_group", "merge"),
                               ("processing_result", "select_athena_version")})
#: A unit read from the FIELD NAME's own suffix (``context.temperature_K``), and nothing else.
_UNIT_SUFFIXES = {"K": "K", "V": "V", "eV": "eV", "mV": "mV", "mA_cm2": "mA/cm²", "s": "s"}
_NAME_RE = re.compile(r"\A[^/\\\x00.][^/\\\x00]{0,254}\Z")


# --- configuration --------------------------------------------------------------------------


def configured_root() -> Path | None:
    raw = (os.environ.get(LOCAL_BUNDLES_ENV) or "").strip()
    return Path(raw).expanduser() if raw else None


def is_requested() -> bool:
    return configured_root() is not None


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    h = host.strip().strip("[]").lower()
    if h == "localhost":
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def launch_hosts(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> list[str]:
    """The interface(s) the server was told to bind, WHERE THAT IS DETECTABLE: uvicorn's ``--host X`` /
    ``--host=X`` on the command line, and ``UVICORN_HOST``. A server started any other way (another
    ASGI server, ``uvicorn.run(host=...)`` in code) is not detected here; the per-request loopback
    check (:func:`require_local_request`) still refuses every non-loopback client."""
    argv = list(sys.argv if argv is None else argv)
    environ = os.environ if environ is None else environ
    hosts = []
    for i, arg in enumerate(argv):
        if arg == "--host" and i + 1 < len(argv):
            hosts.append(argv[i + 1])
        elif arg.startswith("--host="):
            hosts.append(arg.split("=", 1)[1])
    if (environ.get("UVICORN_HOST") or "").strip():
        hosts.append(environ["UVICORN_HOST"].strip())
    return hosts


def _origin_is_loopback(origin: str) -> bool:
    """``http(s)://<loopback host>[:port]`` and nothing more (no path, query, user info)."""
    try:
        parts = urlsplit(origin)
        parts.port  # noqa: B018 - raises ValueError for a port that is not a number
    except ValueError:
        return False
    return (parts.scheme in ("http", "https") and _is_loopback(parts.hostname) and not parts.username
            and not parts.password and parts.path in ("", "/") and not parts.query and not parts.fragment)


def _configured_origins() -> tuple[list[str], list[str]]:
    """``(honoured, ignored)``: the configured origins (else the default), split by loopback."""
    raw = os.environ.get(LOCAL_BUNDLES_ORIGINS_ENV)
    given = [o.strip().rstrip("/").lower() for o in (raw or "").split(",") if o.strip()]
    given = given or list(DEFAULT_LOCAL_BUNDLES_ORIGINS)
    return [o for o in given if _origin_is_loopback(o)], [o for o in given if not _origin_is_loopback(o)]


def startup_warnings() -> list[str]:
    """What start-up says about who may use local bundles, when it is not what one might assume."""
    honoured, ignored = _configured_origins()
    out = []
    if ignored:
        out.append(f"{LOCAL_BUNDLES_ORIGINS_ENV}: ignoring {', '.join(ignored)}: local bundles are served only to pages "
                   "on this computer (http://localhost:<port>, http://127.0.0.1:<port>, http://[::1]:<port>).")
    from .app import _cors_origins

    cors = {o.rstrip("/").lower() for o in _cors_origins()}
    unreachable = [o for o in honoured if o not in cors]
    if unreachable:
        out.append(f"{LOCAL_BUNDLES_ORIGINS_ENV}: {', '.join(unreachable)} is not in ISAAC_UI_CORS_ORIGINS, so a browser "
                   "on it cannot pass the CORS preflight and cannot use local bundles.")
    allowed = ", ".join(honoured) or "this server's own origin"
    others = sorted(cors - set(honoured))
    if others:
        out.append(f"ISAAC_UI_CORS_ORIGINS also allows {', '.join(others)}; those origins may NOT use local bundles "
                   f"(only {allowed}).")
    return out


def startup_note() -> str:
    """The residual risk, said once at start-up: an origin is a scheme, host and port, not an app."""
    allowed = ", ".join(_configured_origins()[0]) or "this server's own origin"
    return (f"Local bundles: any page served from {allowed} can use them (an origin is a scheme, host and port, "
            "not an application); keep other web projects off those ports while this server runs. "
            "See docs/ui-local-dev.md.")


def validate_local_bundles_config_or_raise() -> None:
    """Boot refusal: the variable names no directory, is set beside a deployment base path, or the
    server was (detectably) told to listen on a non-loopback interface. Prints
    :func:`startup_warnings` to stderr."""
    root = configured_root()
    if root is None:
        return
    wide = [h for h in launch_hosts() if not _is_loopback(h)]
    if wide:
        raise RuntimeError(
            f"{LOCAL_BUNDLES_ENV} is set but the server was started to listen on {', '.join(wide)}, which is not this "
            "computer's loopback interface. Local bundles are served only to this computer: start it with "
            "--host 127.0.0.1, or unset the variable."
        )
    if (os.environ.get("ISAAC_BASE_PATH") or "").strip().strip("/"):
        raise RuntimeError(
            f"{LOCAL_BUNDLES_ENV} is set together with ISAAC_BASE_PATH. Local bundles are served only by a "
            "server on the scientist's own computer, never by a deployment; unset one of them."
        )
    if not root.is_dir():
        raise RuntimeError(f"{LOCAL_BUNDLES_ENV} must name an existing directory of local import bundles.")
    for line in startup_warnings():
        print(f"WARNING: {line}", file=sys.stderr)
    print(f"NOTE: {startup_note()}", file=sys.stderr)


# --- who may ask: this computer, by its own name, from this app's own pages -----------------------

#: A request header a page can send only after a CORS preflight the API allows. A cross-origin
#: "simple" request (an ``<img>``, a form) cannot carry it, so it cannot read or record anything here.
LOCAL_HEADER = "X-ISAAC-Local"
LOCAL_HEADER_VALUE = "1"


def _deny(status: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, "message": message})


def _host_and_port(value: str) -> tuple[str, int | None]:
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        host, rest = value[1:end], value[end + 1:]
        port = rest[1:] if rest.startswith(":") else ""
    elif value.count(":") == 1:
        host, port = value.split(":", 1)
    else:
        host, port = value, ""
    try:
        return host.lower(), (int(port) if port else None)
    except ValueError:
        return host.lower(), -1


def _allowed_origins() -> list[str]:
    """This router's OWN allowlist (:data:`LOCAL_BUNDLES_ORIGINS_ENV`), loopback origins only, read
    at request time. Never the app's CORS list: a remote origin configured there is not honoured."""
    return _configured_origins()[0]


def require_local_request(request: Request) -> None:
    """Every ``/api/local-bundles/*`` request: refused unless it comes from THIS computer, names it
    by a loopback Host (so a DNS-rebinding page cannot reach it under its own name), carries no
    Origin outside this router's own loopback allowlist (:func:`_allowed_origins`) or this server's
    own loopback origin, and sends
    :data:`LOCAL_HEADER`. Absent the configuration, the ordinary 404."""
    if not is_requested():
        raise HTTPException(status_code=404, detail="Not Found")
    client = request.client.host if request.client else None
    if not _is_loopback(client):
        raise _deny(403, "not_loopback_client", "Local bundles are served only to this computer.")
    server = request.scope.get("server")
    server_port = server[1] if isinstance(server, (tuple, list)) and len(server) > 1 else None
    host, port = _host_and_port(request.headers.get("host", ""))
    if port is None:
        port = 443 if request.url.scheme == "https" else 80
    if not _is_loopback(host) or (server_port is not None and port != server_port):
        raise _deny(421, "host_not_local",
                    "This request did not name this computer (localhost, 127.0.0.1 or [::1], with this server's port).")
    origin = request.headers.get("origin")
    if origin is not None:
        o = origin.rstrip("/")
        try:
            parts = urlsplit(o)
            same = (parts.scheme in ("http", "https") and _is_loopback(parts.hostname)
                    and (parts.port or (443 if parts.scheme == "https" else 80)) == server_port)
        except ValueError:  # an unparseable origin (e.g. a port that is not a number) is not ours
            same = False
        if o.lower() not in _allowed_origins() and not same:
            raise _deny(403, "origin_not_allowed", "This page's origin may not use local bundles.")
    if request.headers.get(LOCAL_HEADER) != LOCAL_HEADER_VALUE:
        raise _deny(403, "local_header_required",
                    f"Local bundle requests must carry the {LOCAL_HEADER} header (sent only by ISAAC's own pages).")


# --- path safety ----------------------------------------------------------------------------


def _root() -> Path | None:
    root = configured_root()
    if root is None:
        return None
    try:
        resolved = root.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def resolve_bundle_dir(root: Path, name: str) -> Path | None:
    """The bundle folder ``name`` directly inside ``root``, or ``None``. Symlinks are followed and
    must stay inside ``root``; ``bundle.json`` must be a regular file inside the folder."""
    from .local_import import records as R

    if not isinstance(name, str) or not _NAME_RE.match(name) or name in (".", ".."):
        return None
    try:
        target = (root / name).resolve(strict=True)
    except OSError:
        return None
    if target.parent != root or not target.is_dir():
        return None
    if R.contained_file(target, "bundle.json") is None:
        return None
    return target


# --- small readers ----------------------------------------------------------------------------


def _refuse(status: int, error: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message, **extra})


def _not_enabled() -> JSONResponse:
    return _refuse(404, "not_found", "Not Found")


def _no_bundle() -> JSONResponse:
    return _refuse(404, "bundle_not_found",
                   "No bundle folder by that name directly inside the local bundles directory.")


def _scrub(message: str) -> str:
    """A refusal's text with every absolute path to the local bundles directory replaced by the
    bundle's own name: a response body never says where on this computer the bundles are."""
    raw = configured_root()
    prefixes = set()
    for p in (raw, _root()):
        if p is not None:
            prefixes.add(str(p))
            prefixes.add(os.path.realpath(str(p)))
    for prefix in sorted((x for x in prefixes if x and x != os.sep), key=len, reverse=True):
        message = message.replace(prefix + os.sep, "").replace(prefix, "<local bundles directory>")
    return message


class BundleNotAccessible(Exception):
    """The bundle's lock cannot be taken, or its folder cannot be read or written (a read-only
    folder, a ``.bundle.lock`` that is a symlink). Said by bundle name, never by path."""


LOCK_FILE = ".bundle.lock"


def _lock_refusal(bundle_dir: Path) -> str | None:
    """Why the bundle's lock may not be taken here, or ``None``. A ``.bundle.lock`` that is a
    symlink is refused (``mutations.locked`` would open the link's target)."""
    lock = Path(bundle_dir) / LOCK_FILE
    if lock.is_symlink():
        return f"Bundle {Path(bundle_dir).name!r}: its {LOCK_FILE} is a symlink, which is refused; remove it."
    if not lock.exists() and not os.access(bundle_dir, os.W_OK):
        return (f"Bundle {Path(bundle_dir).name!r} is in a read-only folder: its {LOCK_FILE} cannot be created, so it "
                "is not read here (every read and write takes that lock).")
    return None


@contextmanager
def bundle_lock(bundle_dir: Path):
    """``mutations.locked`` for this router: refused (:class:`BundleNotAccessible`) when the lock
    cannot be taken, instead of a server error."""
    from .local_import import mutations as M

    why = _lock_refusal(bundle_dir)
    if why:
        raise BundleNotAccessible(why)
    stack = ExitStack()
    try:
        stack.enter_context(M.locked(bundle_dir))
    except OSError as exc:
        raise BundleNotAccessible(f"Bundle {Path(bundle_dir).name!r}: its {LOCK_FILE} cannot be opened "
                                  f"({type(exc).__name__}: {exc.strerror or 'refused'}).") from exc
    with stack:
        yield


def _not_accessible(exc: Exception, name: str) -> JSONResponse:
    if isinstance(exc, BundleNotAccessible):
        message = str(exc)
    else:  # an OSError's own text names the file's absolute path: never sent
        message = (f"Bundle {name!r} could not be read or written on this computer "
                   f"({type(exc).__name__}: {getattr(exc, 'strerror', None) or 'refused'}; a read-only folder?).")
    return _refuse(409, "bundle_not_accessible", _scrub(message) + " Nothing was written.")


def _io_refusals(route):
    """A route's lock and file-system failures become a 409 naming the bundle, never a 500."""
    @functools.wraps(route)
    def wrapped(*args, **kwargs):
        try:
            return route(*args, **kwargs)
        except (BundleNotAccessible, OSError) as exc:
            return _not_accessible(exc, str(kwargs.get("bundle") or ""))
    return wrapped


def read_bundle(bundle_dir: Path) -> tuple[str, dict]:
    """``(bundle_version, bundle)`` from ONE read of ``bundle.json`` — the contained file
    (``records.contained_file``: no ``..``, no symlink out), opened once, size-checked on the open
    handle before parsing (``bundle.MAX_BUNDLE_BYTES``), so the version and the content are the same
    bytes. The version is :func:`mutations.bundle_version`'s (sha256 of the bytes). Raises
    ``MutationRefused`` (code 6 absent, 1 unreadable) as ``mutations.load`` does."""
    from .local_import import bundle as B
    from .local_import import mutations as M
    from .local_import import records as R

    path = R.contained_file(Path(bundle_dir), B.BUNDLE_FILE)
    if path is None:
        raise M.MutationRefused(f"No bundle.json in bundle {Path(bundle_dir).name!r}.", code=6)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            if size > B.MAX_BUNDLE_BYTES:
                raise M.MutationRefused(f"Unreadable bundle: bundle.json is {size} bytes, over the bound of {B.MAX_BUNDLE_BYTES}", code=1)
            raw = handle.read()
    except OSError as exc:
        raise M.MutationRefused(f"Unreadable bundle: cannot read bundle.json: {type(exc).__name__}", code=1) from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise M.MutationRefused(f"Unreadable bundle: bundle.json is not readable JSON: {exc}", code=1) from exc
    if not isinstance(data, dict):
        raise M.MutationRefused("Unreadable bundle: bundle.json does not hold a JSON object", code=1)
    return "sha256:" + hashlib.sha256(raw).hexdigest(), data


#: Check results by stored version, newest last; bounded so a long session cannot grow it without end.
_check_memo: "OrderedDict[str, dict]" = OrderedDict()
CHECK_MEMO_MAX = 64


def check_status(version: str, bundle: Mapping) -> dict:
    """VALID / STALE / INVALID — the order ``isaac bundle check`` decides it in (``validate_bundle``,
    then ``validate_allowing_stale``) — of the bundle AS READ at ``version`` (:func:`read_bundle`).
    Memoised per version (the version is a hash of the very bytes judged)."""
    from .local_import import bundle as B

    if version in _check_memo:
        _check_memo.move_to_end(version)
        return _check_memo[version]
    errors = B.validate_bundle(bundle)
    stale: list = []
    if errors:
        errors, stale = B.validate_allowing_stale(bundle)
    if errors:
        out = {"status": "INVALID", "errors": [str(e) for e in errors[:10]], "error_count": len(errors), "stale_values": 0,
               "statement": f"The bundle does not meet {B.FORMAT_ID} {B.FORMAT_VERSION}; `isaac bundle check` lists why."}
    elif stale:
        out = {"status": "STALE", "errors": [], "error_count": 0, "stale_values": len(stale),
               "statement": (f"Stored by an older build: {len(stale)} value(s) are eligible differently under this build. "
                             "The next answer re-derives them and logs each one.")}
    else:
        out = {"status": "VALID", "errors": [], "error_count": 0, "stale_values": 0,
               "statement": f"Meets {B.FORMAT_ID} {B.FORMAT_VERSION}. A bundle is not an official record."}
    _check_memo[version] = out
    while len(_check_memo) > CHECK_MEMO_MAX:
        _check_memo.popitem(last=False)
    return out


def _latest_value(bundle: Mapping) -> dict:
    from .local_import import bundle as B

    return B._decisions_by_target(bundle.get("scientist_decisions") or ())


def beamline_readings(bundle: Mapping) -> list[dict]:
    """What the bundle holds for ``system.facility.beamline``: extracted values with their state, and
    scientist answers. Several distinct readings are all listed; none is chosen."""
    seen: dict[str, dict] = {}
    for c in bundle.get("candidates") or ():
        if c.get("target_field_path") == "system.facility.beamline" and c.get("value") is not None:
            seen.setdefault(json.dumps(c["value"]), {"value": c["value"], "basis": c.get("value_state")})
    latest = _latest_value(bundle)
    for m in bundle.get("missing_values") or ():
        if m.get("target_field_path") != "system.facility.beamline":
            continue
        d = latest.get(("missing_value", m["value_id"]))
        if d is not None and d.get("value") is not None and d.get("decision") in ("correct", "confirm", "provide_value"):
            seen[json.dumps(d["value"])] = {"value": d["value"], "basis": "scientist_answer (local, unverified)"}
    return list(seen.values())[:5]


def _modified_utc(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        return None


def bundle_header(name: str, bundle_dir: Path, bundle: Mapping, version: str | None) -> dict:
    from .local_import import bundle as B

    root = bundle.get("source_root") or {}
    return {
        "name": name,
        "source_label": root.get("label"),
        "source_kind": root.get("kind"),
        "format_version": bundle.get("format_version"),
        "bundle_id": bundle.get("bundle_id"),
        "beamline": beamline_readings(bundle),
        "bundle_version": version,
        "modified_utc": _modified_utc(B.bundle_path(bundle_dir)),
    }


def _group_runs(bundle: Mapping) -> tuple[dict[str, Mapping], dict[str, Mapping]]:
    runs = {r["run_id"]: r for r in bundle.get("runs") or ()}
    groups = {g["group_id"]: g for g in bundle.get("record_groups") or ()}
    return runs, groups


def _run_name(run: Mapping | None) -> str | None:
    if not run:
        return None
    return str(run.get("stem") or run.get("label") or run.get("run_id"))


def _group_run_names(group: Mapping, runs: Mapping[str, Mapping]) -> list[str]:
    names = [_run_name(runs.get(rid)) for rid in group.get("member_run_ids") or ()]
    return [n for n in names if n]


def unit_of(path: str | None) -> str | None:
    if not path:
        return None
    leaf = path.rsplit(".", 1)[-1]
    for suffix in sorted(_UNIT_SUFFIXES, key=len, reverse=True):
        if leaf.endswith("_" + suffix):
            return _UNIT_SUFFIXES[suffix]
    return None


# --- describing a question for a person ---------------------------------------------------------


_WHO = {
    "deterministic_parser": ("parser", "Read from the file by ISAAC's parser"),
    "stored_rule": ("stored_rule", "Set by a stored convention rule"),
    "ai_interpretation": ("ai_reading", "Suggested by an AI reading of the files"),
}


def _source_path(sources: Mapping[str, Mapping], source_id: str | None, fallback: str | None = None) -> str | None:
    return fallback or (sources.get(source_id or "") or {}).get("relative_path")


#: Hint kinds whose ``literal`` is text a reader took from a file at its locator.
_FILE_LITERAL_HINTS = ("related_reading", "reading", "local_clock_literal")


def _suggestion_from_hint(h: Mapping, sources: Mapping[str, Mapping], kind: str) -> dict:
    hk = h.get("kind")
    if hk == "ai_suggestion":
        who, label = "ai_reading", "Suggested by an AI reading of the files"
        acceptable = kind != "optional_values"
    elif hk == "reading":
        who, label, acceptable = "file_reading", "One reading the files give", True
    elif hk == "related_reading":
        who, label, acceptable = "parser", "A related reading by ISAAC's parser (a hint)", False
    elif hk in ("processed_output_header", "beamtime_element_evidence"):
        who, label, acceptable = "file_reading", "Stated in the files", False
    else:
        who, label, acceptable = "hint", "A hint about what is asked, never an answer", False
    return {
        "who": who,
        "who_label": label,
        "hint_kind": hk,
        "value": h.get("literal"),
        "relative_path": _source_path(sources, h.get("source_id"), h.get("source_path") or h.get("relative_path")),
        "locator": h.get("locator"),
        # the text as the file has it: an AI reading's own quote, or the literal a reader took from the file
        "quote": h.get("quote") if hk == "ai_suggestion" else (h.get("literal") if hk in _FILE_LITERAL_HINTS else None),
        "model_id": h.get("model_id"),
        "field": h.get("field"),
        "note": h.get("note"),
        "acceptable": acceptable,
        "confirmed": False,
    }


def _candidate_suggestions(c: Mapping, sources: Mapping[str, Mapping]) -> list[dict]:
    out = []
    ev = next((e for e in c.get("evidence") or () if e.get("method") != "ai_interpretation"), None)
    if c.get("value") is not None:
        who, label = _WHO.get((ev or {}).get("method"), ("parser", "Read from the file by ISAAC's parser"))
        out.append({
            "who": who, "who_label": label, "hint_kind": "extracted_value", "value": c["value"],
            "relative_path": _source_path(sources, (ev or {}).get("source_id"), (ev or {}).get("relative_path")),
            "locator": (ev or {}).get("locator"), "quote": (ev or {}).get("literal_value"),
            "model_id": None, "field": c.get("target_field_path"), "candidate_id": c["candidate_id"],
            "value_state": c.get("value_state"), "evidence_total": c.get("evidence_total"),
            "note": None, "acceptable": True, "confirmed": False,
        })
    elif c.get("observed_literals"):
        who, label = _WHO.get((ev or {}).get("method"), ("parser", "Read from the file by ISAAC's parser"))
        out.append({
            "who": who, "who_label": label, "hint_kind": "literal_no_value", "value": c["observed_literals"][0],
            "relative_path": _source_path(sources, (ev or {}).get("source_id"), (ev or {}).get("relative_path")),
            "locator": (ev or {}).get("locator"), "quote": (ev or {}).get("literal_value") or c["observed_literals"][0],
            "model_id": None, "field": c.get("target_field_path"), "candidate_id": c["candidate_id"],
            "value_state": c.get("value_state"), "evidence_total": c.get("evidence_total"),
            "note": "The file's own text; no value was derived from it, so there is nothing to confirm. Correct it with the value.",
            "acceptable": False, "confirmed": False,
        })
    return out


def _dedupe(suggestions: list[dict]) -> list[dict]:
    """One row per (who, value, file, locator); ``targets`` counts how many it stood for."""
    out: dict[tuple, dict] = {}
    for s in suggestions:
        key = (s["who"], s["hint_kind"], json.dumps(s["value"], sort_keys=True, default=str), s["relative_path"], s["locator"])
        if key in out:
            out[key]["targets"] = out[key].get("targets", 1) + 1
            for n in s.get("run_names") or ():
                if n not in out[key].setdefault("run_names", []):
                    out[key]["run_names"].append(n)
        else:
            out[key] = {**s, "targets": s.get("targets") or 1}
    return list(out.values())


class BundleIndex:
    """Lookups one request builds once over the bundle it read."""

    def __init__(self, bundle: Mapping):
        self.bundle = bundle
        self.runs, self.groups = _group_runs(bundle)
        self.sources = {s["source_id"]: s for s in bundle.get("sources") or ()}
        self.cands = {c["candidate_id"]: c for c in bundle.get("candidates") or ()}
        self.missing = {m["value_id"]: m for m in bundle.get("missing_values") or ()}
        self.conflicts = {c["conflict_id"]: c for c in bundle.get("conflicts") or ()}
        self.source_by_path = {s.get("relative_path"): s["source_id"] for s in bundle.get("sources") or ()}
        #: each run's OWN files: its acquisition file and its scan files (a notes file naming many runs is not one)
        self.run_files: dict[str, set[str]] = {}
        for r in bundle.get("runs") or ():
            files = {r.get("acquisition_source_id")} | {sc.get("source_id") for sc in r.get("scans") or () if isinstance(sc, Mapping)}
            self.run_files[r["run_id"]] = {f for f in files if f}
        self.ai: dict[tuple[str, str], list[Mapping]] = {}
        for i in bundle.get("ai_interpretations") or ():
            t = i.get("target") or {}
            self.ai.setdefault((str(t.get("kind")), str(t.get("id"))), []).append(i)


def own_suggestions(idx: BundleIndex, target: Mapping) -> tuple[list[dict], list[tuple[str, str]]]:
    """What the bundle suggests for ONE target from its own evidence — its extracted value (ISAAC's
    parser or a stored rule) and the AI readings made for it — and the parser values that shows."""
    out: list[dict] = []
    shown: list[tuple[str, str]] = []
    kind, tid = str(target.get("kind")), str(target.get("id"))
    if kind == "candidate":
        c = idx.cands.get(tid)
        if c is not None and c.get("value") is not None:
            ev = next((e for e in c.get("evidence") or () if e.get("method") != "ai_interpretation"), None)
            who, label = _WHO.get((ev or {}).get("method"), ("parser", "Read from the file by ISAAC's parser"))
            out.append({"value": c["value"], "who": who, "who_label": label, "model_id": None,
                        "source_id": (ev or {}).get("source_id") or idx.source_by_path.get((ev or {}).get("relative_path")),
                        "relative_path": _source_path(idx.sources, (ev or {}).get("source_id"), (ev or {}).get("relative_path")),
                        "locator": (ev or {}).get("locator"), "quote": (ev or {}).get("literal_value"), "confirmed": False})
            shown.append(("candidate", tid))
    for i in idx.ai.get((kind, tid), []):
        if i.get("proposed_value") is None:
            continue
        ref = (i.get("source_refs") or [{}])[0] or {}
        out.append({"value": i.get("proposed_value"), "who": "ai_reading", "who_label": "Suggested by an AI reading of the files",
                    "model_id": (i.get("model") or {}).get("model_id"),
                    "source_id": ref.get("source_id") or idx.source_by_path.get(i.get("source_path")),
                    "relative_path": i.get("source_path") or _source_path(idx.sources, ref.get("source_id")),
                    "locator": i.get("excerpt_locator") or ref.get("locator"), "quote": i.get("quote"), "confirmed": False})
    return out, shown


def scope_runs(idx: BundleIndex, scope: str) -> set[str] | None:
    """The run ids a scope stands for; ``None`` for the whole beamtime (no run's files are "its own")."""
    if scope.startswith("group:"):
        return set((idx.groups.get(scope[6:]) or {}).get("member_run_ids") or ())
    if scope.startswith("run:"):
        return {scope[4:]}
    return None


def _provenance(idx: BundleIndex, sug: Mapping, runs: set[str] | None) -> tuple[bool | None, str]:
    """Is the cited file one of the scope's OWN runs' files? Only then is it "this group's own"."""
    src = sug.get("source_id")
    if runs is None:
        return None, "Cited for the whole beamtime"
    if not src:
        return None, "A reading for this group; the file it was read from is not recorded"
    own = any(src in idx.run_files.get(r, ()) for r in runs)
    if own:
        return True, "This group's own files"
    return False, ("A reading for this group's runs, quoted from a file that is not one of its runs ("
                   + (sug.get("relative_path") or src) + ")")


def scope_suggestions(idx: BundleIndex, target_ids: Sequence[str], kind_of: Mapping[str, str],
                      scope: str | None = None) -> tuple[list[dict], list[tuple[str, str]]]:
    """One row per distinct (value, provenance) the targets' evidence suggests, with how many targets it
    stands for. ``from_own_files`` is true only when the cited source is one of the scope's own runs'
    files (acquisition or scan file); a reading quoted from another file is labelled as such."""
    rows: dict[tuple, dict] = {}
    shown: list[tuple[str, str]] = []
    runs = scope_runs(idx, scope) if scope else None
    for tid in target_ids:
        got, more = own_suggestions(idx, {"kind": kind_of.get(tid), "id": tid})
        shown += more
        for sug in got:
            own, label = _provenance(idx, sug, runs)
            key = (json.dumps(sug["value"], sort_keys=True, default=str), own, sug.get("relative_path"))
            row = rows.get(key)
            if row is None:
                rows[key] = {**sug, "targets": 1, "from_own_files": own, "provenance_label": label}
            else:
                row["targets"] += 1
    ordered = sorted(rows.values(), key=lambda r: (r["from_own_files"] is not True,))
    return ordered, shown


def _value_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _target_run(idx: BundleIndex, kind: str | None, tid: str) -> str | None:
    if kind == "candidate":
        return (idx.cands.get(tid) or {}).get("run_id")
    if kind == "missing_value":
        return (idx.missing.get(tid) or {}).get("run_id")
    return None


def per_target_agreement(idx: BundleIndex, target_ids: Sequence[str], kind_of: Mapping[str, str], scope: str) -> dict:
    """Targets are per RUN, so a group of several runs is judged run by run: ``per_target`` lists each
    target's own suggestions; ``unanimous_value`` is set only when every target that has any suggestion
    suggests exactly that one value; ``unanimous_from_own_files`` only when, besides, every such
    suggestion cites one of the group's own runs' files; ``mixed`` when the targets' suggestions differ."""
    runs = scope_runs(idx, scope)
    per_target = []
    value_sets: list[set[str]] = []
    values: dict[str, Any] = {}
    all_own = True
    for tid in target_ids:
        got, _shown = own_suggestions(idx, {"kind": kind_of.get(tid), "id": tid})
        rows = []
        for sug in got:
            own, label = _provenance(idx, sug, runs)
            rows.append({**sug, "targets": 1, "from_own_files": own, "provenance_label": label})
            values[_value_key(sug["value"])] = sug["value"]
            all_own = all_own and own is True
        rid = _target_run(idx, kind_of.get(tid), tid)
        per_target.append({"target_id": tid, "run_id": rid, "run_name": _run_name(idx.runs.get(rid)) if rid else None,
                           "own_suggestions": rows[:5]})
        if rows:
            value_sets.append({_value_key(r["value"]) for r in rows})
    keys = set().union(*value_sets) if value_sets else set()
    unanimous = next(iter(keys)) if len(keys) == 1 else None
    return {
        "per_target": per_target,
        "mixed": len(keys) > 1,
        "unanimous_value": values[unanimous] if unanimous is not None else None,
        "has_unanimous_value": unanimous is not None,
        "unanimous_from_own_files": unanimous is not None and all_own,
    }


def describe_question(bundle: Mapping, q: Mapping, *, folder: str,
                      idx: BundleIndex | None = None) -> tuple[dict, list[tuple[str, str]]]:
    """``(display, shown)`` — what the screen shows beside one consolidated question, and the
    candidates whose parser values it shows (each recorded as an exposure before it is returned)."""
    from .local_import import suggestions as S
    from .local_import import template as T

    idx = idx or BundleIndex(bundle)
    runs, groups, sources, cands = idx.runs, idx.groups, idx.sources, idx.cands
    missing, conflicts = idx.missing, idx.conflicts
    shown: list[tuple[str, str]] = []
    kind_of = {t["id"]: t["kind"] for t in q.get("targets") or ()}
    per_scope_values: list[set[str]] = []

    def runs_of_target(t: Mapping) -> list[str]:
        k, tid = t.get("kind"), t.get("id")
        if k == "candidate":
            return [r for r in [(cands.get(tid) or {}).get("run_id")] if r]
        if k == "missing_value":
            return [r for r in [(missing.get(tid) or {}).get("run_id")] if r]
        if k == "conflict":
            return list((conflicts.get(tid) or {}).get("run_ids") or ())
        if k == "record_group":
            return list((groups.get(tid) or {}).get("member_run_ids") or ())
        return []

    scopes = []
    for scope, ids in (q.get("per_scope_targets") or {}).items():
        entry: dict = {"scope": scope, "target_count": len(ids)}
        if scope == "experiment":
            entry.update(kind="experiment", label="The whole beamtime", run_names=[])
        elif scope.startswith("group:"):
            g = groups.get(scope[6:]) or {}
            names = _group_run_names(g, runs)
            entry.update(kind="group", group_id=scope[6:], label=f"Record group {scope[6:]}", run_names=names[:20],
                         run_count=len(names), group_status=g.get("status"))
        else:
            rid = scope[4:] if scope.startswith("run:") else scope
            entry.update(kind="run", run_id=rid, label=f"Run {_run_name(runs.get(rid)) or rid} (not in a record group)",
                         run_names=[n for n in [_run_name(runs.get(rid))] if n])
        # what THIS scope's own evidence suggests, so a person answering one group — or all of them —
        # sees where the groups' files disagree (field questions only; a conflict's readings are its subject)
        # (not optional values: one scope's targets there are several FIELDS, whose values do not compare)
        if q.get("kind") in ("missing_value", "confirm_value"):
            own, more = scope_suggestions(idx, ids, kind_of, scope)
            shown += more
            entry["own_suggestions"] = own[:5]
            entry["own_suggestions_total"] = len(own)
            agreement = per_target_agreement(idx, ids, kind_of, scope)
            entry.update(mixed=agreement["mixed"], has_unanimous_value=agreement["has_unanimous_value"],
                         unanimous_value=agreement["unanimous_value"],
                         unanimous_from_own_files=agreement["unanimous_from_own_files"],
                         per_target=agreement["per_target"][:DESCRIBE_TARGETS] if len(ids) > 1 else [])
            if own:
                per_scope_values.append({_value_key(o["value"]) for o in own})
        else:
            entry.update(own_suggestions=[], own_suggestions_total=0, mixed=False, has_unanimous_value=False,
                         unanimous_value=None, unanimous_from_own_files=False, per_target=[])
        scopes.append(entry)

    targets = list(q.get("targets") or ())
    described = targets[:DESCRIBE_TARGETS]
    record_names: list[str] = []
    for t in described:
        for rid in runs_of_target(t):
            n = _run_name(runs.get(rid))
            if n and n not in record_names:
                record_names.append(n)

    kind = q.get("kind")
    suggestions: list[dict] = []
    if kind == "confirm_value":
        for t in described:
            c = cands.get(t.get("id"))
            if c is not None:
                got = _candidate_suggestions(c, sources)
                if got:
                    shown.append(("candidate", c["candidate_id"]))
                    for s in got:
                        s["run_names"] = [n for n in [_run_name(runs.get(c.get("run_id")))] if n]
                suggestions += got
    for h in q.get("hints") or ():
        suggestions.append(_suggestion_from_hint(h, sources, kind))
    suggestions = _dedupe(suggestions)
    field_suggestions: dict[str, list[dict]] = {}
    for fpath, hints in (q.get("field_hints") or {}).items():
        field_suggestions[fpath] = [_suggestion_from_hint(h, sources, kind) for h in hints][:SUGGESTIONS_PER_QUESTION]

    # a confirm_value question's distinct extracted values over EVERY target (not only the described
    # window), so "accept" says exactly what it confirms; each value counted is shown, so exposed
    distinct: dict[str, dict] = {}
    if kind == "confirm_value":
        for t in targets:
            c = cands.get(t.get("id"))
            if c is None or c.get("value") is None:
                continue
            shown.append(("candidate", c["candidate_id"]))
            d = distinct.setdefault(_value_key(c["value"]), {"value": c["value"], "targets": 0})
            d["targets"] += 1

    value_rule = None
    fields: dict[str, dict] = {}
    path = q.get("target_field_path")
    if kind in FIELD_KINDS and path:
        rule = T.rule_for_path(path)
        value_rule = {**rule, "unit": unit_of(path)}
    if kind == "optional_values":
        for fpath, ids in (q.get("fields") or {}).items():
            rule = T.rule_for_path(fpath)
            fields[fpath] = {**rule, "unit": unit_of(fpath), "target_count": len(ids)}

    absorber = None
    if kind == "confirm_absorber":
        pairs = set()
        for t in targets:
            g = groups.get(t.get("id"))
            if g is None:
                continue
            sug = S.absorber_for_group(bundle, g)
            if sug.get("status") == "agrees" and sug.get("element") and sug.get("edge") and not sug.get("ai_disagrees_with_files"):
                pairs.add((sug["element"], sug["edge"], "files"))
            else:
                pairs.add((None, None, None))
        if len(pairs) == 1 and next(iter(pairs))[0]:
            el, ed, basis = next(iter(pairs))
            absorber = {"element": el, "edge": ed, "basis": "stated in the files (not confirmed)"}

    answer_kind = {
        "missing_value": "field_value", "optional_values": "optional_values", "confirm_value": "confirm_value",
        "resolve_conflict": "conflict", "naming_counter_positions": "counter_positions",
        "clock_time_zone": "clock_zone", "confirm_absorber": "absorber",
    }.get(kind, "other")
    settles_many = q.get("scope") == "experiment" and (len(q.get("per_scope_targets") or {}) > 1 or len(targets) > 1
                                                       or kind in ("naming_counter_positions", "clock_time_zone"))
    return {
        "folder": folder,
        "beamtime": (bundle.get("source_root") or {}).get("label"),
        "beamline": beamline_readings(bundle),
        "answer_kind": answer_kind,
        "settles_many": settles_many,
        "scopes": scopes,
        "record_run_names": record_names[:60],
        "targets_described": len(described),
        "targets_total": len(targets),
        "suggestions_differ": len(set().union(*per_scope_values)) > 1 if per_scope_values else False,
        "suggestions": suggestions[:SUGGESTIONS_PER_QUESTION],
        "suggestions_total": len(suggestions),
        "distinct_extracted_values": list(distinct.values()),
        "field_suggestions": field_suggestions,
        "value_rule": value_rule,
        "fields": fields,
        "suggested_absorber": absorber,
        "suggestion_statement": "A suggestion is NOT confirmed: nothing is recorded until you answer.",
    }, shown


def capture_items(bundle: Mapping) -> dict:
    """The open capture decisions (bundle 1.6.0): merge candidates still proposed, and processing
    results with Athena versions and no result of record selected."""
    from .local_import import bundle as B

    runs, groups = _group_runs(bundle)
    merges = []
    for mc in bundle.get("merge_candidates") or ():
        if mc.get("status") != "proposed":
            continue
        merges.append({
            "merge_candidate_id": mc.get("merge_candidate_id"),
            "group_ids": list(mc.get("group_ids") or ()),
            "groups": [{"group_id": gid, "run_names": _group_run_names(groups.get(gid) or {}, runs)[:20],
                        "status": (groups.get(gid) or {}).get("status")} for gid in mc.get("group_ids") or ()],
            "question": (mc.get("question") or {}).get("text") if isinstance(mc.get("question"), Mapping) else mc.get("question"),
            "reasons": [r.get("code") if isinstance(r, Mapping) else r for r in mc.get("reasons") or ()][:10],
        })
    athena = []
    for r in bundle.get("processing_results") or ():
        ids = B.athena_version_ids(r)
        if not ids or r.get("athena_result_of_record"):
            continue
        versions = []
        for v in r.get("athena_versions") or ():
            if not isinstance(v, Mapping) or not v.get("version_id"):
                continue
            prov = v.get("provenance") if isinstance(v.get("provenance"), Mapping) else {}
            versions.append({"version_id": v["version_id"], "project_file": prov.get("project_file") or prov.get("relative_path"),
                             "athena_group": prov.get("athena_group") or prov.get("group")})
        athena.append({"processing_id": B.processing_id(r), "group_id": r.get("group_id"),
                       "run_names": _group_run_names(groups.get(r.get("group_id")) or {}, runs)[:20], "versions": versions})
    return {"merge_candidates": merges, "athena_selections": athena}


# --- progress -------------------------------------------------------------------------------


def progress(bundle_dir: Path, bundle: Mapping, check: Mapping) -> dict:
    from .local_import import bundle as B
    from .local_import import questions as Q
    from .local_import import records as R

    counts = bundle.get("counts") or {}
    readiness = bundle.get("readiness") or {}
    group_status: dict[str, int] = {}
    for g in bundle.get("record_groups") or ():
        group_status[g.get("status") or "?"] = group_status.get(g.get("status") or "?", 0) + 1
    proc_state: dict[str, int] = {}
    for r in bundle.get("processing_results") or ():
        proc_state[r.get("state") or "?"] = proc_state.get(r.get("state") or "?", 0) + 1
    out: dict = {
        "check": dict(check),
        "runs": counts.get("runs"),
        "run_candidates": counts.get("run_candidates"),
        "record_groups": {"total": len(bundle.get("record_groups") or ()), "by_status": group_status},
        "processing_results": {"total": len(bundle.get("processing_results") or ()), "by_state": proc_state},
        "scientist_decisions": len(bundle.get("scientist_decisions") or ()),
        "values": {k: counts.get(k) for k in ("candidates", "conflicts", "missing_values", "needs_review",
                                              "candidate_extracted", "scientist_confirmed", "rejected", "unmapped")},
        "readiness": {"stage": readiness.get("stage"), "eligible_value_count": readiness.get("eligible_value_count"),
                      "blocking": readiness.get("blocking"), "official_record_ready": False},
        "missing_share": None,
        "missing_share_statement": ("Not shown: no command in this build computes a missing-value share, and this page "
                                    "does not invent one. The counts above are the bundle's own."),
    }
    questions_counts = None
    minimum = None
    if check.get("status") != "INVALID":
        try:
            payload = Q.consolidate(bundle)
            questions_counts = payload["counts"]
            minimum = Q.minimum_answers_for_one_group(payload, bundle)
        except Exception as exc:  # a bundle this build cannot consolidate: said, never hidden
            questions_counts = {"unavailable": f"{type(exc).__name__}"}
    out["questions"] = questions_counts
    out["minimum_for_one_group"] = minimum

    blocks: list[str] = []
    if check.get("status") == "INVALID":
        blocks.append("The bundle does not pass `isaac bundle check`; nothing can be composed from it.")
    if isinstance(questions_counts, Mapping) and questions_counts.get("blocking"):
        blocks.append(f"{questions_counts['blocking']} blocking question(s) are open.")
    unconfirmed = group_status.get("proposed", 0)
    if unconfirmed:
        blocks.append(f"{unconfirmed} record group(s) are proposed, not confirmed (a group is confirmed with "
                      "`isaac bundle decide --target <group> --decision confirm`).")
    if not bundle.get("record_groups"):
        blocks.append("No record groups yet: `isaac bundle group` proposes them.")
    # NOT APPROVED means a live group's curve awaiting a decision: a rejected result, a not-applicable
    # one (no curve to approve: its group is counted on the next line) and any result of a rejected,
    # split or merged group are not blockers
    live = {g.get("group_id") for g in Q.live_groups(bundle)}
    pending = sum(1 for r in bundle.get("processing_results") or ()
                  if r.get("state") not in (B.STATE_SCIENTIST_CONFIRMED, B.STATE_REJECTED)
                  and not B.processing_not_applicable(r) and r.get("group_id") in live)
    if pending:
        blocks.append(f"{pending} processing result(s) are not approved.")
    blocked = Q.processing_blocked_groups(bundle) if bundle.get("record_groups") else {}
    if blocked:
        blocks.append(f"{len(blocked)} group(s) have no applicable processing protocol, so they cannot become complete records yet.")
    out["blocks_export"] = blocks

    reports = []
    bundle_mtime = None
    try:
        bundle_mtime = B.bundle_path(bundle_dir).stat().st_mtime
    except OSError:
        pass
    for g in bundle.get("record_groups") or ():
        f = R.contained_file(bundle_dir, f"{R.VALIDATION_DIR}/{g['group_id']}.json")
        if f is None:
            continue
        try:
            report = json.loads(f.read_text(encoding="utf-8"))
            mtime = f.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(report, Mapping):
            continue
        reports.append({
            "group_id": g["group_id"],
            "verdict": report.get("verdict"),
            "missing_required": list(report.get("missing_required") or ())[:20],
            "written_utc": datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "older_than_bundle": bundle_mtime is not None and mtime < bundle_mtime,
        })
    out["last_validation"] = {
        "reports": reports,
        "statement": ("What the last `isaac bundle validate` wrote, per group. It is not re-run here; a report older "
                      "than the bundle does not reflect the answers given since."),
    }
    return out


# --- the request bodies -------------------------------------------------------------------------


class LocalAnswerRequest(BaseModel):
    """One answer to one consolidated question (``isaac bundle decide --question``)."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(max_length=64, description="One of the question's `allowed_decisions`.")
    value: str | None = Field(default=None, max_length=20_000, description=(
        "The answer as typed. For a field it is parsed by the metadata template's own rules: a number "
        "field takes a number, a field with a fixed list takes one of its values exactly."))
    by: str = Field(max_length=200, description="The name of the person answering (the command line's `--by`).")
    orcid: str | None = Field(default=None, max_length=19)
    note: str | None = Field(default=None, max_length=2_000)
    only: str | None = Field(default=None, max_length=300, description="One scope of the question: `group:<id>` or `run:<id>`.")
    only_scopes: list[str] | None = Field(default=None, max_length=500, description=(
        "Several scopes of the question, each `group:<id>` or `run:<id>`: the answer is written to exactly their "
        "targets. Refused with `only`, and refused whole when any of them has no open target."))
    field: str | None = Field(default=None, max_length=300, description="An optional-values question: the field answered.")
    element: str | None = Field(default=None, max_length=3)
    edge: str | None = Field(default=None, max_length=3)
    positions: list[int] | None = Field(default=None, max_length=8)
    expected_version: str | None = Field(default=None, max_length=80, description="The `bundle_version` the answer was given against.")
    dry_run: bool = Field(default=False, description="Resolve and check exactly as a write would, and write nothing.")


class LocalDecisionRequest(BaseModel):
    """One capture decision on one target (``isaac bundle decide --target``)."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(max_length=300)
    decision: str = Field(max_length=64)
    value: str | None = Field(default=None, max_length=300)
    merge_with: list[str] | None = Field(default=None, max_length=50)
    by: str = Field(max_length=200)
    orcid: str | None = Field(default=None, max_length=19)
    note: str | None = Field(default=None, max_length=2_000)
    expected_version: str | None = Field(default=None, max_length=80)


# --- the routes -------------------------------------------------------------------------------


router = APIRouter(prefix="/api/local-bundles", tags=[TAG_LOCAL_BUNDLES], dependencies=[Depends(require_local_request)])

_R_UNAUTHORIZED: dict = {401: {"description": (
    "The deployment requires an API key and the request did not present a valid one. Never returned when "
    "the deployment leaves this authentication disabled, which is the default for local runs.")}}
_R_NOT_FOUND: dict = {404: {"description": (
    "Local bundles are not configured on this server, or there is no bundle folder by that name directly "
    "inside the local bundles directory (a name that leaves the directory is refused the same way), or no "
    "open question or target by that id.")}}
_R_REFUSED: dict = {422: {"description": (
    "The answer was refused, with the command line's own reason (a decision that does not answer the "
    "question, a missing name, a value outside the field's allowed list). Nothing was written.")}}
_R_LOCAL: dict = {
    403: {"description": (
        "Refused before anything was read: the request did not come from this computer, came from a page whose "
        "origin may not use local bundles, or lacks the header ISAAC's own pages send.")},
    421: {"description": "Refused before anything was read: the request did not name this computer as its host."},
}
_R_CONFLICT: dict = {409: {"description": "The bundle cannot be read or would be left invalid; nothing was written."}}
_R_STALE: dict = {
    412: {"description": "The bundle changed since `expected_version` was read; nothing was written. `current_version` says what is stored now."},
    428: {"description": "`expected_version` is required for a write; nothing was written."},
}


def _open(name: str) -> tuple[Path | None, JSONResponse | None]:
    if not is_requested():
        return None, _not_enabled()
    root = _root()
    if root is None:
        return None, _refuse(404, "not_found", "Not Found")
    bdir = resolve_bundle_dir(root, name)
    if bdir is None:
        return None, _no_bundle()
    why = _lock_refusal(bdir)
    if why:
        return None, _not_accessible(BundleNotAccessible(why), name)
    return bdir, None


def _refusal(exc: Exception) -> JSONResponse:
    from .local_import import mutations as M

    if isinstance(exc, M.StaleBundleVersion):
        return _refuse(412, "stale_bundle_version", _scrub(str(exc)), current_version=exc.current)
    code = getattr(exc, "code", 2)
    message = _scrub(str(exc))
    if code == 6:
        return _refuse(404, "not_found_in_bundle", message)
    if code in (1, 5):
        return _refuse(409, "bundle_refused", message)
    return _refuse(422, "refused", message)


@router.get(
    "",
    summary="List the Local Import Bundles",
    description=(
        "Every bundle folder directly inside the local bundles directory: its folder name, the name of the "
        "folder or ZIP it was imported from (usually the beamtime), any beamline the bundle records, its "
        "format version, its `isaac bundle check` status (VALID, STALE or INVALID), its counts and its "
        "readiness block, and the `bundle_version` a write must name. Read-only; it shows no extracted value."
    ),
    response_description="The bundles, newest first, and how many folder entries are not bundles.",
    responses={**_R_UNAUTHORIZED, **_R_LOCAL, **_R_NOT_FOUND},
)
@_io_refusals
def list_local_bundles():
    from .local_import import mutations as M

    if not is_requested():
        return _not_enabled()
    root = _root()
    if root is None:
        return _refuse(404, "not_found", "Not Found")
    bundles, skipped = [], 0
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        return _refuse(409, "directory_not_accessible",
                       f"The local bundles directory {root.name!r} cannot be listed ({type(exc).__name__}: "
                       f"{exc.strerror or 'refused'}).")
    for entry in entries:
        bdir = resolve_bundle_dir(root, entry.name)
        if bdir is None:
            skipped += 1
            continue
        try:
            with bundle_lock(bdir):
                try:
                    version, bundle = read_bundle(bdir)
                except M.MutationRefused as exc:
                    bundles.append({"name": entry.name, "check": {"status": "INVALID", "errors": [_scrub(str(exc))], "error_count": 1,
                                                                  "stale_values": 0, "statement": "The bundle cannot be read."},
                                    "bundle_version": M.bundle_version(bdir)})
                    continue
        except (BundleNotAccessible, OSError) as exc:
            body = json.loads(_not_accessible(exc, entry.name).body)
            bundles.append({"name": entry.name, "check": {"status": "INVALID", "errors": [body["message"]], "error_count": 1,
                                                          "stale_values": 0, "statement": "The bundle cannot be read here."},
                            "bundle_version": None, "not_accessible": True})
            continue
        check = check_status(version, bundle)
        counts = bundle.get("counts") or {}
        bundles.append({
            **bundle_header(entry.name, bdir, bundle, version),
            "check": check,
            "counts": {k: counts.get(k) for k in ("runs", "run_candidates", "candidates", "conflicts", "missing_values",
                                                  "needs_review", "scientist_confirmed")},
            "record_groups": len(bundle.get("record_groups") or ()),
            "scientist_decisions": len(bundle.get("scientist_decisions") or ()),
            "readiness": {"stage": (bundle.get("readiness") or {}).get("stage"),
                          "eligible_value_count": (bundle.get("readiness") or {}).get("eligible_value_count"),
                          "blocking": (bundle.get("readiness") or {}).get("blocking")},
        })
    bundles.sort(key=lambda b: b.get("modified_utc") or "", reverse=True)
    return {
        "local_only": True,
        "directory_name": root.name,
        "bundles": bundles,
        "not_bundles": skipped,
        "statement": ("Bundles on this computer. They are not official records, and nothing on this page is uploaded "
                      "or sent anywhere."),
    }


@router.get(
    "/{bundle}/progress",
    summary="Show One Bundle's Import Progress",
    description=(
        "Where one import stands: runs, record groups by status, processing results by state, the consolidated "
        "question counts (blocking, conflicts, optional), the fewest answers between one group and export, what "
        "still blocks export, and the verdicts the last `isaac bundle validate` wrote, each marked when it is older "
        "than the bundle. No share of missing values is given, because no command computes one. Read-only."
    ),
    response_description="The bundle's header and its progress.",
    responses={**_R_UNAUTHORIZED, **_R_LOCAL, **_R_NOT_FOUND},
)
@_io_refusals
def get_local_bundle_progress(bundle: str = PathParam(..., max_length=255, description="The bundle's folder name.")):
    from .local_import import mutations as M

    bdir, refused = _open(bundle)
    if refused is not None:
        return refused
    with bundle_lock(bdir):
        try:
            version, data = read_bundle(bdir)
        except M.MutationRefused as exc:
            return _refusal(exc)
    check = check_status(version, data)
    return {"bundle": bundle_header(bundle, bdir, data, version), "progress": progress(bdir, data, check)}


@router.get(
    "/{bundle}/questions",
    summary="List One Bundle's Consolidated Questions",
    description=(
        "The consolidated questions of `isaac bundle questions` — asked once at the right scope, blocking first — "
        "filtered by `kind`, `blocking_only` and `scope`, and paged with `limit` and `offset`. Each question carries "
        "a `display` block for a person: the folder, beamtime and beamline, the record groups and run names it "
        "applies to, each suggestion with who made it (ISAAC's parser, a stored rule, an AI reading), the file, the "
        "place in the file and the quoted text, and the rule for the value. A suggestion is never confirmed. "
        "`capture` lists the open merge and Athena-version decisions.\n\n"
        "Showing a parser value is recorded as an exposure in the bundle first, as `isaac bundle questions` does, "
        "so this read can write `bundle.json`; `exposures_recorded` says how many it added and `bundle_version` is "
        "the version after them. Like every operation here it needs the header ISAAC's own pages send, so a page "
        "on another site cannot make it record anything."
    ),
    response_description="The questions page, its counts, the capture decisions and the bundle version.",
    responses={**_R_UNAUTHORIZED, **_R_LOCAL, **_R_NOT_FOUND, **_R_CONFLICT},
)
@_io_refusals
def get_local_bundle_questions(
    bundle: str = PathParam(..., max_length=255, description="The bundle's folder name."),
    kind: str | None = Query(None, max_length=64, description="Only questions of this kind."),
    blocking_only: bool = Query(False, description="Only the questions that block export."),
    scope: str | None = Query(None, max_length=300, description="`experiment`, `group:<id>` or `run:<id>`."),
    limit: int = Query(MAX_LIMIT, ge=1, le=MAX_LIMIT, description="Page size."),
    offset: int = Query(0, ge=0, le=1_000_000, description="Questions to skip."),
):
    from .local_import import mutations as M
    from .local_import import questions as Q

    bdir, refused = _open(bundle)
    if refused is not None:
        return refused
    with bundle_lock(bdir):
        try:
            _read_version, data = read_bundle(bdir)
        except M.MutationRefused as exc:
            return _refusal(exc)
        payload = Q.consolidate(data)
        rows = Q.filter_questions(payload, scope=scope, blocking_only=blocking_only)
        if kind:
            rows = [q for q in rows if q["kind"] == kind]
        page = rows[offset: offset + limit]
        # THE EXPOSURES `bundle questions` RECORDS (hint candidates, conflicts), plus every candidate
        # whose extracted value this page shows beside a confirm question
        shown = [("candidate", h["candidate_id"]) for q in page for h in q["hints"] if h.get("candidate_id")]
        shown += [("conflict", q["targets"][0]["id"]) for q in page if q["kind"] == "resolve_conflict"]
        out_questions = []
        idx = BundleIndex(data)
        for q in page:
            display, more = describe_question(data, q, folder=bundle, idx=idx)
            shown += more
            out_questions.append({**q, "display": display})
        minimum = Q.minimum_answers_for_one_group(payload, data)
        capture = capture_items(data)
        before = len(data.get("exposures") or ())
        for k, tid in shown:
            M.record_exposure(data, k, tid, "bundle questions")
            if k == "conflict":
                cid = next((c.get("candidate_id") for c in data.get("conflicts") or () if c.get("conflict_id") == tid), None)
                if cid:
                    M.record_exposure(data, "candidate", cid, "bundle questions")
        added = len(data.get("exposures") or ()) - before
        if added:
            try:
                M.save_bundle(bdir, data)
            except M.MutationRefused as exc:
                return _refuse(409, "exposure_not_recorded",
                               f"The exposures could not be recorded, so nothing is shown: {exc}")
        version = M.bundle_version(bdir) if added else _read_version
    header = bundle_header(bundle, bdir, data, version)
    return {
        "bundle": header,
        "format": payload["format"],
        "format_version": payload["format_version"],
        "blocking_basis": payload["blocking_basis"],
        "counts": payload["counts"],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "omitted_before": min(offset, len(rows)),
        "omitted_after": max(0, len(rows) - offset - len(page)),
        "minimum_for_one_group": minimum,
        "questions": out_questions,
        "capture": capture,
        "exposures_recorded": added,
        "identity": "local_unverified",
        "statement": ("Answers are recorded in this bundle on this computer as a local, unverified statement by the "
                      "name you type. Nothing is uploaded."),
    }


def _scope_label(idx: BundleIndex, scope: str) -> tuple[str, list[str]]:
    if scope == "experiment":
        return "The whole beamtime", []
    if scope.startswith("group:"):
        return f"Record group {scope[6:]}", _group_run_names(idx.groups.get(scope[6:]) or {}, idx.runs)
    rid = scope[4:] if scope.startswith("run:") else scope
    name = _run_name(idx.runs.get(rid))
    return f"Run {name or rid} (not in a record group)", [name] if name else []


def preview_by_scope(bundle: Mapping, q: Mapping, target_ids: Sequence[str], value: Any) -> list[dict]:
    """For a dry run: every scope the answer would be written to, its targets, what ITS OWN files (and
    AI readings made for it) suggest, and ``differs`` when they suggest something and none of it is the
    value being written — so "same for all" cannot silently write over a group whose files say otherwise.
    A decision with no value (confirm, set_absorber) is not compared (``compared: false``)."""
    idx = BundleIndex(bundle)
    wanted = set(target_ids)
    kind_of = {t["id"]: t["kind"] for t in q.get("targets") or ()}
    compare = value is not None and q.get("kind") in ("missing_value", "optional_values", "confirm_value")
    out = []
    for scope, ids in (q.get("per_scope_targets") or {}).items():
        mine = [i for i in ids if i in wanted]
        if not mine:
            continue
        own, _shown = scope_suggestions(idx, mine, kind_of, scope) if compare or q.get("kind") == "confirm_value" else ([], [])
        label, names = _scope_label(idx, scope)
        # PER TARGET (a target is one run): a run whose own suggestions exist and exclude the value differs,
        # even when another run of the same group suggests it
        agreement = per_target_agreement(idx, mine, kind_of, scope) if compare else {"per_target": []}
        differing = [t for t in agreement["per_target"] if t["own_suggestions"]
                     and _value_key(value) not in {_value_key(o["value"]) for o in t["own_suggestions"]}]
        out.append({
            "scope": scope, "label": label, "run_names": names[:20], "run_count": len(names), "target_ids": mine,
            "own_suggestions": own[:5], "compared": compare,
            "differs": bool(compare and differing),
            "differing_targets": differing,
        })
    return out


def _typed_value(q: Mapping, body: LocalAnswerRequest) -> tuple[Any, str | None]:
    """The answer's value, typed by the metadata template's parsing for the field it answers."""
    from .local_import import template as T

    if body.value is None:
        return None, None
    if q["kind"] in FIELD_KINDS and body.decision in ("confirm", "correct"):
        path = body.field if q["kind"] == "optional_values" else q.get("target_field_path")
        if path:
            value, why = T.parse_answer(body.value, T.rule_for_path(path))
            if why:
                return None, f"{path}: {why}. Nothing was recorded."
            return value, None
    value = body.value.strip()
    return (value or None), None


@router.post(
    "/{bundle}/questions/{question_id}/answer",
    summary="Answer One Consolidated Question",
    description=(
        "Records one answer to one consolidated question with the command line's own code "
        "(`isaac bundle decide --question`): one decision per target, each listed, as a local, unverified "
        "statement by `by`. `only` answers one group (or run) of the question; without it every target the "
        "question lists is answered. `dry_run` resolves and checks exactly as the write would and returns the "
        "targets it would write, writing nothing.\n\n"
        "A field value is typed by the metadata template's rules: a number field takes a number and a field with a "
        "fixed list takes one of its values exactly. The question is resolved under the bundle's lock, after "
        "`expected_version` is checked against what is stored, so an answer never lands on a bundle another "
        "command changed since it was read. Nothing is uploaded."
    ),
    response_description="What was recorded (or, for a dry run, would be), and the bundle version after.",
    responses={**_R_UNAUTHORIZED, **_R_LOCAL, **_R_NOT_FOUND, **_R_CONFLICT, **_R_STALE, **_R_REFUSED},
)
@_io_refusals
def post_local_bundle_answer(
    bundle: str = PathParam(..., max_length=255, description="The bundle's folder name."),
    question_id: str = PathParam(..., max_length=64, description="The consolidated question's id."),
    body: LocalAnswerRequest = Body(...),
):
    from .local_import import mutations as M
    from .local_import import questions as Q

    bdir, refused = _open(bundle)
    if refused is not None:
        return refused
    if not body.expected_version:
        return _refuse(428, "expected_version_required",
                       "Name the bundle_version the answer was given against; nothing was written.")
    try:
        read_version, data = read_bundle(bdir)
    except M.MutationRefused as exc:
        return _refusal(exc)
    if read_version != body.expected_version:
        return _refusal(M.StaleBundleVersion(body.expected_version, read_version))
    asked = Q.question(Q.consolidate(data), question_id)
    if asked is None:
        return _refuse(404, "not_found_in_bundle", f"No open question {question_id!r}.")
    value, why = _typed_value(asked, body)
    if why:
        return _refuse(422, "value_refused", why)
    try:
        result = M.decide_question(
            bdir, question_id=question_id, only=body.only, only_scopes=body.only_scopes, field=body.field, decision=body.decision, value=value,
            by=body.by, orcid=body.orcid, note=body.note, element=body.element, edge=body.edge,
            positions=body.positions, expected_version=body.expected_version, dry_run=body.dry_run,
            with_version=not body.dry_run,
        )
    except M.MutationRefused as exc:
        return _refusal(exc)
    if body.dry_run:
        groups = preview_by_scope(data, asked, result.get("recorded", []), value)
        return {
            "by_scope": groups,
            "scopes_total": len(groups),
            "scopes_whose_files_suggest_otherwise": sum(1 for g in groups if g["differs"]),
            "dry_run": True,
            "question_id": question_id,
            "would_record": result.get("recorded", []),
            "unchanged": result.get("unchanged", []),
            "target_ids": result.get("target_ids", []),
            "value": value,
            "bundle_version": result.get("bundle_version"),
            "statement": "Nothing was written. The write re-checks all of this, and re-validates the whole bundle.",
        }
    result, version = result
    return {
        "dry_run": False,
        "question_id": question_id,
        "result": result,
        "value": value,
        "bundle_version": version,
        "identity": "local_unverified",
        "statement": (f"Recorded in this bundle as a local, unverified statement by {body.by.strip()!r}. "
                      "Nothing was uploaded."),
    }


@router.post(
    "/{bundle}/decisions",
    summary="Record One Capture Decision",
    description=(
        "Records one decision on one target with the command line's own code (`isaac bundle decide --target`), "
        "limited to the capture decisions this screen offers: `keep_apart` on a merge candidate, `merge` on a "
        "record group (with `merge_with`), and `select_athena_version` on a processing result (with `value`, one "
        "of its listed versions). As a local, unverified statement by `by`. `expected_version` is checked against "
        "what is stored, under the bundle's lock. Any other decision is refused here and stays a command-line act."
    ),
    response_description="What was recorded and the bundle version after.",
    responses={**_R_UNAUTHORIZED, **_R_LOCAL, **_R_NOT_FOUND, **_R_CONFLICT, **_R_STALE, **_R_REFUSED},
)
@_io_refusals
def post_local_bundle_decision(
    bundle: str = PathParam(..., max_length=255, description="The bundle's folder name."),
    body: LocalDecisionRequest = Body(...),
):
    from .local_import import mutations as M

    bdir, refused = _open(bundle)
    if refused is not None:
        return refused
    if not body.expected_version:
        return _refuse(428, "expected_version_required",
                       "Name the bundle_version the decision was made against; nothing was written.")
    value = body.value.strip() if isinstance(body.value, str) and body.value.strip() else None
    params = dict(target_ids=[body.target], decision=body.decision, value=value, by=body.by, orcid=body.orcid,
                  note=body.note, merge_with=body.merge_with or None)

    def change(data):
        kind, _obj = M.resolve_target(data, body.target)
        if (kind, body.decision) not in CAPTURE_DECISIONS:
            raise M.MutationRefused(
                f"`{body.decision}` on a {kind} is not offered here; record it with `isaac bundle decide`. Nothing was recorded.")
        return M.record_decision(data, **params)

    try:
        M._decide_arguments(**params, qc_status=None, element=None, edge=None, positions=None)
        result, version = M.mutate(bdir, change, expected_version=body.expected_version, with_version=True)
    except M.MutationRefused as exc:
        return _refusal(exc)
    return {
        "result": result,
        "bundle_version": version,
        "identity": "local_unverified",
        "statement": (f"Recorded in this bundle as a local, unverified statement by {body.by.strip()!r}. "
                      "Nothing was uploaded."),
    }


__all__ = [
    "LOCAL_BUNDLES_ENV",
    "LOCAL_BUNDLES_TAG",
    "TAG_LOCAL_BUNDLES",
    "configured_root",
    "is_requested",
    "resolve_bundle_dir",
    "router",
    "validate_local_bundles_config_or_raise",
]
