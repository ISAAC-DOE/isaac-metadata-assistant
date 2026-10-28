"""Schema Proposals: drafting and tracking proposals to change the ISAAC vocabulary.

WHAT THIS IS, AND WHAT IT IS NOT
================================
A scientist who meets a term the ISAAC vocabulary does not have should be
able to say so in a form the owners of the standard can act on. The upstream ISAAC
portal ("Living Ontology" -> "Propose a Change") is where those owners review
proposals. This module lets a proposal be DRAFTED and TRACKED here and handed to the
portal unchanged.

**ISAAC does not approve, apply or forward anything.** There is no approve endpoint,
no apply endpoint, and nothing here calls the portal (a test pins both: the route
table has no such operation, and this module imports no HTTP client). The two status
values this build records are ``pending`` and ``withdrawn``. ``accepted`` and
``rejected`` are decisions the standard's owners make in the portal; they are
deliberately NOT part of this vocabulary, because a status ISAAC cannot establish is a
status it must not display.

THE UPSTREAM CONTRACT THIS MIRRORS
==================================
``portal/database.py`` (``vocabulary_proposals``) and ``portal/api.py``
(``POST /portal/api/vocabulary/proposals``) of the upstream repository:

* ``proposal_type`` is ``add_term`` or ``add_category``;
* ``add_term`` carries ``section``, ``category``, ``term``, ``description``;
* ``add_category`` carries ``section``, ``category``, ``description`` (no ``term``);
* the portal's own rules: a term is ONE token of at most 80 characters with no
  whitespace; a description is at least 20 characters; a term already in the category
  is refused; a person may have at most 50 proposals waiting.

``GET /api/schema-proposals/{id}/portal-payload`` returns exactly the body the portal
takes, so a person who can reach the portal can send it without retyping.

TWO VOCABULARY SOURCES, BOTH LABELLED, NEITHER LIVE
===================================================
The portal validates a proposal against ITS OWN list (``data/vocabulary.json`` upstream:
68 term lists), and the vendored schema carries its own enums (36 lists). They overlap by
only 30. So the screen shows both, labelled, and a proposal is checked against the one
that will judge it:

* ``portal`` — a verbatim snapshot (``data/portal_vocabulary_a1cb1c8.json``, provenance in
  ``data/PORTAL_VOCABULARY_PROVENANCE.md``). A snapshot, not the live portal.
* ``schema`` — derived at request time from the vendored schema's enums (below).

``add_term`` is valid only against a portal list (the portal would refuse any other),
``add_category`` is refused for a key either source already has and for any schema field
that is not a text field. Neither source is "the official vocabulary" on its own, and the
copy says what each is.

THE SCHEMA SIDE IS DERIVED, NEVER TRANSCRIBED
=============================================
:func:`derive_vocabulary` walks the vendored ``schema/isaac_record_v1.json`` and reads
every ``enum``. A *category* is an enum-bearing property (arrays are looked through to
their ``items``); a *section* is a top-level block of the record, plus ``Record Info``
for the root fields. The category key is the dotted property path, which is the form
the portal uses (``context.environment``, ``system.technique``, and for a root field
just ``record_type``). A hand-written list would be a second definition free to drift
from the one every record is validated against.

IDENTITY IS NOT TRUSTED IN THIS BUILD
=====================================
``proposed_by`` is never read from the request body. It is filled only from
:func:`isaac_api.identity.resolve_identity_for_request`, and only when that identity is
a person vouched for by a verified edge assertion. No verifier in this build mints one,
so on every deployment this build ships, ``proposed_by`` is ``null`` and
``attribution`` is ``"unverified"``. A name typed into the body is ignored, and the
response says it was.

STORAGE: WORKSPACE FILES, TEMPORARY ON THE HOSTED SERVER
========================================================
One JSON file per proposal under ``<workspace>/_schema_proposals/<id>.json``, written
atomically with :func:`isaac_api.workspace.atomic_write_text`: the same mechanism an
import session uses, for the same reason (no migration, no database table; the
``_`` prefix keeps it out of every experiment listing). On the hosted deployment the
workspace directory is an ``emptyDir`` and does not survive a restart, so every
response says proposals on this server are temporary and should be sent to the ISAAC
portal (copy or download the payload). There is no revision token: the store has one
mutation that needs ordering (a proposal is created or withdrawn), and a single
in-process lock serialises it, which is the arrangement the workspace documents for
this single-process server.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Path as PathParam, Query, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from isaac_records.ids import is_record_id, new_record_id
from isaac_records.official import EXPECTED_VERSION, schema_path

from . import identity as identity_module
from . import workspace as ws

__all__ = [
    "PROPOSAL_STATUSES",
    "SCHEMA_PROPOSALS_TAG",
    "TAG_SCHEMA_PROPOSALS",
    "derive_vocabulary",
    "router",
]

# --- the contract's constants ---------------------------------------------------

TAG_SCHEMA_PROPOSALS = "Schema Proposals"

#: Registered next to ``routes.OPENAPI_TAGS`` by ``create_app``. A separate entry
#: rather than a reuse of ``Schema & Vocabulary``, whose published description says no
#: editing affordance exists: true of the schema, and misleading beside a POST.
SCHEMA_PROPOSALS_TAG: dict = {
    "name": TAG_SCHEMA_PROPOSALS,
    "description": (
        "Drafting and tracking proposals to change the ISAAC vocabulary. "
        "A proposal here is a draft for the standard's owners; it changes nothing "
        "in the schema, and ISAAC neither approves nor sends it. Review happens in "
        "the ISAAC portal."
    ),
}

ADD_TERM = "add_term"
ADD_CATEGORY = "add_category"
PROPOSAL_TYPES = (ADD_TERM, ADD_CATEGORY)

#: The only two states this build can establish. ``accepted`` and ``rejected`` are
#: decided in the portal by the standard's owners and are not recorded here.
STATUS_PENDING = "pending"
STATUS_WITHDRAWN = "withdrawn"
PROPOSAL_STATUSES = (STATUS_PENDING, STATUS_WITHDRAWN)

ATTRIBUTION_VERIFIED = "verified"
ATTRIBUTION_UNVERIFIED = "unverified"

PORTAL_SNAPSHOT_COMMIT = "a1cb1c8"
PORTAL_SNAPSHOT_LABEL = f"Portal vocabulary (snapshot {PORTAL_SNAPSHOT_COMMIT})"
PORTAL_SNAPSHOT_FILE = Path(__file__).resolve().parent / "data" / f"portal_vocabulary_{PORTAL_SNAPSHOT_COMMIT}.json"

ROOT_SECTION = "Record Info"
ROOT_SECTION_LABEL = "Record Info (root fields)"

#: Limits. Description bounds mirror the portal's (a description under 20 characters is
#: refused there); the others bound what this store will hold.
LIMITS: dict[str, int] = {
    "section_max": 100,
    "category_max": 255,
    "term_max": 80,
    "description_min": 20,
    "description_max": 2000,
    "problem_max": 2000,
    "examples_max": 2000,
    "affected_records_estimate_max": 200,
    "flip_list_max": 2000,
    "max_pending": 50,
    "max_withdrawn_kept": 500,
    "max_body_bytes": 131_072,
    "page_max": 100,
}

#: The portal's own cap on one person's pending proposals is 50. Here the same number is
#: shared by EVERYONE using this server (one workspace), because nobody is identified; a
#: withdrawn proposal frees its slot, and only the newest ``max_withdrawn_kept`` withdrawn
#: ones are kept on disk (the oldest are removed, and the response says so).
_TERM_SHAPE = re.compile(r"\A[A-Za-z][A-Za-z0-9_./-]*\Z")
_SNAKE_TERM = re.compile(r"\A[a-z][a-z0-9_]*\Z")
_PATH_LIKE = re.compile(r"(\.\.|//|\./|/\.)")
_CATEGORY_SHAPE = re.compile(r"\A[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*\Z")

_GATE0_FIELDS = ("problem", "examples", "affected_records_estimate", "flip_list")

#: Fields the server owns. A request that carries one is not refused (a form that echoes
#: a stored proposal back must not fail), but the value is never used, and the response
#: lists what was ignored so the omission is not silent.
_SERVER_OWNED_KEYS = frozenset(
    {
        "id",
        "proposal_id",
        "proposed_by",
        "proposed_at",
        "attribution",
        "status",
        "reviewed_by",
        "reviewed_at",
        "review_comment",
        "created_utc",
        "persistence",
    }
)
_BODY_KEYS = frozenset({"proposal_type", "section", "category", "term", "description", "gate0"})

#: The portal's endpoint, stated so a person knows where the payload goes. ISAAC never
#: calls it.
PORTAL_PROPOSALS_PATH = "/portal/api/vocabulary/proposals"

PERSISTENCE: dict = {
    "class": "workspace_files",
    "survives_restart": "not_guaranteed",
    "message": (
        "Proposals on this server are temporary. They are kept in this server's "
        "working folder, not in a database, and on the hosted site that folder is "
        "cleared when the server restarts. Send each proposal to the ISAAC portal "
        "for review: copy the portal payload or download it as JSON."
    ),
}

REVIEW_NOTE = (
    "ISAAC drafts and tracks proposals; it does not approve, apply or send them. "
    "The people who own the ISAAC standard review proposals in the ISAAC portal, "
    "and they record any decision there, not here."
)

ATTRIBUTION_NOTE = (
    "Who is calling is not verified on this server, so a proposal records no "
    "author. Anyone who can reach this screen can see and withdraw any proposal."
)


# --- deriving the vocabulary from the schema ------------------------------------


def _is_object_block(node: Any) -> bool:
    """Is this top-level property a block with fields of its own (an object, or an
    array of objects)? Everything else is a root field and belongs to ``Record Info``."""
    if not isinstance(node, dict):
        return False
    if isinstance(node.get("properties"), dict):
        return True
    items = node.get("items")
    return isinstance(items, dict) and isinstance(items.get("properties"), dict)


def _section_label(block: str) -> str:
    return block.replace("_", " ").title()


def _unique_strings(values: Any) -> list[str]:
    """The string members of an ``enum``, in schema order, without duplicates."""
    out: list[str] = []
    if not isinstance(values, list):
        return out
    for value in values:
        if isinstance(value, str) and value not in out:
            out.append(value)
    return out


def _collect(node: Any, path: list[str], found: dict[str, dict]) -> None:
    """Record every enum-bearing property under ``node``, keyed by dotted path.

    Walks ``properties`` and looks through ``items`` (an array's element is the same
    category as the array). ``oneOf`` / ``anyOf`` alternatives are merged into the same
    path. ``if`` / ``then`` / ``else`` are deliberately NOT walked: an ``enum`` there
    is a condition on a value, not a list of the values the field allows.
    """
    if not isinstance(node, dict):
        return
    values = _unique_strings(node.get("enum"))
    if values and path:
        key = ".".join(path)
        entry = found.setdefault(key, {"path": key, "terms": [], "description": ""})
        for value in values:
            if value not in entry["terms"]:
                entry["terms"].append(value)
        description = node.get("description")
        if isinstance(description, str) and not entry["description"]:
            entry["description"] = description.strip()
    properties = node.get("properties")
    if isinstance(properties, dict):
        for name, child in properties.items():
            _collect(child, [*path, str(name)], found)
    items = node.get("items")
    if isinstance(items, dict):
        _collect(items, path, found)
    for key in ("oneOf", "anyOf"):
        alternatives = node.get(key)
        if isinstance(alternatives, list):
            for alternative in alternatives:
                _collect(alternative, path, found)


def derive_vocabulary(schema: dict) -> dict:
    """Sections, categories and allowed terms, read from ``schema``.

    Pure: takes the parsed schema and returns the structure, so a test can hand it a
    mutated copy and see the change come through. Section order is the schema's own,
    with ``Record Info`` (the root fields) first.
    """
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        properties = {}

    root_found: dict[str, dict] = {}
    blocks: list[tuple[str, dict[str, dict]]] = []
    for name, node in properties.items():
        found: dict[str, dict] = {}
        if _is_object_block(node):
            _collect(node, [str(name)], found)
            blocks.append((str(name), found))
        else:
            _collect(node, [str(name)], root_found)

    sections: list[dict] = [
        _section_view(ROOT_SECTION, ROOT_SECTION_LABEL, None, list(root_found.values()))
    ]
    for name, found in blocks:
        sections.append(_section_view(_section_label(name), _section_label(name), name, list(found.values())))
    return {
        "sections": sections,
        "section_count": len(sections),
        "category_count": sum(len(s["categories"]) for s in sections),
        "term_count": sum(len(c["terms"]) for s in sections for c in s["categories"]),
    }


def _section_view(section_id: str, label: str, block: str | None, categories: list[dict]) -> dict:
    return {
        "id": section_id,
        "label": label,
        "block": block,
        "categories": [
            {
                "key": c["path"],
                "label": c["path"].split(".")[-1],
                "description": c["description"],
                "terms": list(c["terms"]),
            }
            for c in categories
        ],
    }


def _text_typed(node: dict) -> bool | None:
    """Is this schema node a text field? ``True`` for ``string``, ``False`` for any other
    type (number, integer, boolean, object, an array of those, or a mixed type), ``None``
    when the node declares no type at all. Arrays are judged by their ``items``."""
    t = node.get("type")
    if t is None and isinstance(node.get("items"), dict):
        return _text_typed(node["items"])
    if t == "array" and isinstance(node.get("items"), dict):
        return _text_typed(node["items"])
    if t is None:
        return None
    kinds = {t} if isinstance(t, str) else set(t) if isinstance(t, list) else set()
    kinds.discard("null")
    return kinds == {"string"}


def derive_fields(schema: dict) -> dict[str, dict]:
    """Every property path the schema declares, with whether it is a text field.

    ``{"context.temperature_K": {"text": False}, ...}``. Same walk as the vocabulary
    (``properties``, looking through ``items``). Used to refuse a "new category" for a
    field the schema already has, and for one that is not a text field.
    """
    out: dict[str, dict] = {}

    def walk(node: Any, path: list[str]) -> None:
        if not isinstance(node, dict):
            return
        if path:
            out.setdefault(".".join(path), {"text": _text_typed(node), "has_enum": bool(node.get("enum"))})
        props = node.get("properties")
        if isinstance(props, dict):
            for name, child in props.items():
                walk(child, [*path, str(name)])
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, path)

    walk(schema, [])
    return out


def derive_portal_vocabulary(doc: dict) -> dict:
    """The portal's ``vocabulary.json`` in the same section/category shape.

    A portal entry with a ``values`` list is a TERM LIST (``kind: "terms"``); an entry with
    only a description or a mapping (the unit alias map, for example) is ``kind: "other"``
    and carries no terms, so it is shown but cannot take an ``add_term``.
    """
    sections: list[dict] = []
    for name, entries in (doc.items() if isinstance(doc, dict) else ()):
        if not isinstance(entries, dict):
            continue
        cats = []
        for key, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            values = _unique_strings(entry.get("values"))
            description = entry.get("description")
            cats.append(
                {
                    "key": str(key),
                    "label": str(key).split(".")[-1],
                    "description": description.strip() if isinstance(description, str) else "",
                    "terms": values,
                    "kind": "terms" if isinstance(entry.get("values"), list) else "other",
                }
            )
        block = None if name == ROOT_SECTION else str(name).lower().replace(" ", "_")
        label = ROOT_SECTION_LABEL if name == ROOT_SECTION else str(name)
        sections.append({"id": str(name), "label": label, "block": block, "categories": cats})
    return {
        "sections": sections,
        "section_count": len(sections),
        "category_count": sum(1 for s_ in sections for c in s_["categories"]),
        "term_list_count": sum(1 for s_ in sections for c in s_["categories"] if c["kind"] == "terms"),
        "term_count": sum(len(c["terms"]) for s_ in sections for c in s_["categories"]),
    }


@lru_cache(maxsize=4)
def _derive_cached(path_str: str, mtime_ns: int, size: int) -> tuple[str, str]:
    """Parse and derive once per schema file state. Returns ``(sha256, json)``."""
    text = Path(path_str).read_text(encoding="utf-8")
    schema = json.loads(text)
    vocabulary = derive_vocabulary(schema)
    vocabulary["fields"] = derive_fields(schema)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), json.dumps(vocabulary)


@lru_cache(maxsize=4)
def _portal_cached(path_str: str, mtime_ns: int, size: int) -> tuple[str, str]:
    text = Path(path_str).read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), json.dumps(derive_portal_vocabulary(json.loads(text)))


def _schema_file() -> Path:
    """The vendored schema. A function so a test can point it at a mutated copy."""
    return schema_path(ws.REPO_ROOT)


def _portal_file() -> Path:
    """The vendored portal snapshot. A function so a test can point it at a mutated copy."""
    return PORTAL_SNAPSHOT_FILE


def load_vocabulary() -> dict:
    """The schema-enum vocabulary for the schema file as it is NOW (cached on its stat).

    Carries ``fields`` (every property path and whether it is a text field) beside the
    sections, and ``schema_sha256``."""
    path = _schema_file()
    stat = path.stat()
    digest, payload = _derive_cached(str(path), stat.st_mtime_ns, stat.st_size)
    vocabulary = json.loads(payload)
    vocabulary["schema_sha256"] = digest
    return vocabulary


def load_portal_vocabulary() -> dict:
    """The portal snapshot as sections and categories, with ``portal_sha256``."""
    path = _portal_file()
    stat = path.stat()
    digest, payload = _portal_cached(str(path), stat.st_mtime_ns, stat.st_size)
    vocabulary = json.loads(payload)
    vocabulary["portal_sha256"] = digest
    return vocabulary


def load_sources() -> dict:
    """Both vocabulary sources and the union of their sections, for one request."""
    schema_v = load_vocabulary()
    portal_v = load_portal_vocabulary()
    sections: list[dict] = []
    seen: set[str] = set()
    for source in (portal_v, schema_v):
        for sec in source["sections"]:
            if sec["id"] in seen:
                continue
            seen.add(sec["id"])
            sections.append({"id": sec["id"], "label": sec["label"], "block": sec["block"]})
    return {"schema": schema_v, "portal": portal_v, "sections": sections}


def _find_section(sources: dict, section: str) -> dict | None:
    for entry in sources["sections"]:
        if entry["id"] == section:
            return entry
    return None


def _portal_term_list(sources: dict, section: str, key: str) -> dict | None:
    """The portal's term list for ``key`` in ``section`` (the portal checks both)."""
    for sec in sources["portal"]["sections"]:
        if sec["id"] == section:
            for c in sec["categories"]:
                if c["key"] == key and c["kind"] == "terms" and c["terms"]:
                    return c
    return None


def _schema_enum(sources: dict, key: str) -> dict | None:
    for sec in sources["schema"]["sections"]:
        for c in sec["categories"]:
            if c["key"] == key:
                return c
    return None


def _portal_key_exists(sources: dict, key: str) -> str | None:
    """The portal section holding a category key (term list or not), else ``None``."""
    wanted = key.casefold()
    for sec in sources["portal"]["sections"]:
        for c in sec["categories"]:
            if c["key"].casefold() == wanted:
                return sec["id"]
    return None


def _separator_free(text: str) -> str:
    """A comparison form: case-folded, with ``_ - / .`` and spaces removed."""
    return re.sub(r"[\s_\-/.]+", "", text.casefold())


# --- validation -----------------------------------------------------------------


_SAFE_FIELD_NAME = re.compile(r"\A[A-Za-z0-9_.-]{1,40}\Z")


def _safe_field_name(key: Any) -> str | None:
    """A request key, echoed only when it is plain. A key is attacker-chosen text, and
    one that cannot be encoded (a lone surrogate) would make the refusal itself crash."""
    return key if isinstance(key, str) and _SAFE_FIELD_NAME.match(key) else None


def _error(field: str | None, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def _text_problem(value: str) -> str | None:
    """Why ``value`` cannot be stored as text, or ``None``. Allows newline and tab."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return "contains a character that cannot be stored"
    for ch in value:
        category = unicodedata.category(ch)
        if category == "Cc" and ch not in "\n\t\r":
            return "contains a control character"
        if category == "Cf":
            # Format characters (bidi overrides such as U+202E, zero-width marks, BOM) are
            # invisible in a reviewer's screen and can make one word read as another.
            return "contains an invisible formatting character"
    return None


def _clean_string(
    body: dict,
    field: str,
    *,
    maximum: int,
    errors: list[dict],
    required: bool,
    minimum: int = 1,
    label: str | None = None,
) -> str | None:
    label = label or field
    raw = body.get(field)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if required:
            errors.append(_error(field, f"{field}_required", f"{label.capitalize()} is required."))
        return None
    if not isinstance(raw, str):
        errors.append(_error(field, f"{field}_invalid", f"{label.capitalize()} must be text."))
        return None
    value = unicodedata.normalize("NFC", raw.strip())
    problem = _text_problem(value)
    if problem is not None:
        errors.append(_error(field, f"{field}_invalid", f"{label.capitalize()} {problem}."))
        return None
    if len(value) > maximum:
        errors.append(
            _error(
                field,
                f"{field}_too_long",
                f"{label.capitalize()} can be at most {maximum} characters; this one is {len(value)}.",
            )
        )
        return None
    if len(value) < minimum:
        errors.append(
            _error(
                field,
                f"{field}_too_short",
                f"{label.capitalize()} needs at least {minimum} characters; this one is {len(value)}.",
            )
        )
        return None
    return value


def _validate(body: dict, sources: dict) -> tuple[dict | None, list[dict], list[str]]:
    """Check one request body. Returns ``(clean, field_errors, ignored_keys)``.

    ``clean`` is ``None`` whenever there is any error. Conflicts with what already
    exists (a term already allowed, a duplicate proposal) are not decided here; they
    are 409s and are raised after the shape is known to be good.
    """
    errors: list[dict] = []
    ignored = sorted(k for k in body if k in _SERVER_OWNED_KEYS)
    for key in sorted(body):
        if key not in _BODY_KEYS and key not in _SERVER_OWNED_KEYS:
            errors.append(
                _error(
                    _safe_field_name(key),
                    "unknown_field",
                    "This request carries a field a schema proposal does not take.",
                )
            )

    proposal_type = body.get("proposal_type")
    if proposal_type not in PROPOSAL_TYPES:
        errors.append(
            _error(
                "proposal_type",
                "invalid_proposal_type",
                "Proposal type must be add_term (a new allowed value) or add_category (a new list of allowed values).",
            )
        )
        proposal_type = None

    section_text = _clean_string(
        body, "section", maximum=LIMITS["section_max"], errors=errors, required=True
    )
    section = _find_section(sources, section_text) if section_text else None
    if section_text and section is None:
        errors.append(
            _error(
                "section",
                "unknown_section",
                "That section is in neither the portal vocabulary snapshot nor the ISAAC schema. Choose one from the list.",
            )
        )

    category = _clean_string(
        body, "category", maximum=LIMITS["category_max"], errors=errors, required=True
    )
    term: str | None = None

    if proposal_type == ADD_TERM:
        term = _clean_string(body, "term", maximum=LIMITS["term_max"], errors=errors, required=True)
        existing_terms: list[str] = []
        if section is not None and category:
            portal_list = _portal_term_list(sources, section["id"], category)
            schema_list = _schema_enum(sources, category)
            if portal_list is None and schema_list is not None:
                # A fixed list in the schema that the portal has no list for: the portal's own
                # check would refuse a new term for it, so a draft for it could never be sent.
                errors.append(
                    _error(
                        "category",
                        "category_not_in_portal",
                        "This is a fixed list in the ISAAC schema, but the portal vocabulary snapshot has no list for it "
                        "(in this section), so the portal would refuse a new term for it. Raise it with the owners of the "
                        "standard; no proposal type here fits.",
                    )
                )
            elif portal_list is None:
                errors.append(
                    _error(
                        "category",
                        "unknown_category",
                        f"The portal vocabulary snapshot has no list of terms called that in this section. "
                        "Choose one of its lists, or propose a new category if the field does not exist yet.",
                    )
                )
            else:
                existing_terms = list(portal_list["terms"]) + [
                    t for t in (schema_list["terms"] if schema_list else []) if t not in portal_list["terms"]
                ]
        if term:
            if not _TERM_SHAPE.match(term) or _PATH_LIKE.search(term):
                errors.append(
                    _error(
                        "term",
                        "invalid_term",
                        "A term is a single word with no spaces, starting with a letter, "
                        "using only letters, digits, underscore, hyphen, slash or dot, and no path-like '..' or '//' "
                        "(for example catalytic_reactor_test).",
                    )
                )
            elif existing_terms and all(_SNAKE_TERM.match(t) for t in existing_terms) and not _SNAKE_TERM.match(term):
                errors.append(
                    _error(
                        "term",
                        "invalid_term",
                        "Every existing term in this category is lowercase with underscores "
                        "(like rotating_cylinder), so a new one should be too.",
                    )
                )
    elif proposal_type == ADD_CATEGORY:
        if "term" in body and body.get("term") not in (None, ""):
            errors.append(
                _error(
                    "term",
                    "term_not_allowed",
                    "A new category does not take a term; propose the terms once the category exists.",
                )
            )
        if category:
            if not _CATEGORY_SHAPE.match(category):
                errors.append(
                    _error(
                        "category",
                        "invalid_category",
                        "A category key is a dotted path of field names, such as "
                        "context.transport.viscosity.",
                    )
                )
            elif section is not None:
                block = section["block"]
                first = category.split(".")[0]
                if block is None and "." in category:
                    errors.append(
                        _error(
                            "category",
                            "category_outside_section",
                            "Record Info holds the record's own top-level fields, so its "
                            "category keys have no dots (for example record_type).",
                        )
                    )
                elif block is not None and first != block:
                    errors.append(
                        _error(
                            "category",
                            "category_outside_section",
                            f"A category in the {section['label']} section starts with "
                            f"'{block}.'.",
                        )
                    )
            field = sources["schema"].get("fields", {}).get(category)
            if field is not None and field.get("text") is not True and not any(e["field"] == "category" for e in errors):
                errors.append(
                    _error(
                        "category",
                        "category_not_a_text_field",
                        "This field already exists in the ISAAC schema and does not take words (it is a number, a "
                        "yes/no value, a group or a mixed type), so a list of allowed terms does not fit it.",
                    )
                )

    description = _clean_string(
        body,
        "description",
        maximum=LIMITS["description_max"],
        minimum=LIMITS["description_min"],
        errors=errors,
        required=True,
    )

    gate0 = _validate_gate0(body.get("gate0"), errors)

    if errors:
        return None, errors, ignored
    return (
        {
            "proposal_type": proposal_type,
            "section": section["id"],
            "category": category,
            "term": term,
            "description": description,
            "gate0": gate0,
        },
        [],
        ignored,
    )


def _validate_gate0(raw: Any, errors: list[dict]) -> dict | None:
    """The optional "why, for reviewers" block: four free-text answers."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(_error("gate0", "gate0_invalid", "The reviewer notes must be an object."))
        return None
    for key in raw:
        if key not in _GATE0_FIELDS:
            errors.append(
                _error(
                    f"gate0.{_safe_field_name(key)}" if _safe_field_name(key) else "gate0",
                    "unknown_field",
                    "The reviewer notes take only problem, examples, affected_records_estimate and flip_list.",
                )
            )
    out: dict[str, str] = {}
    for name in _GATE0_FIELDS:
        sub: list[dict] = []
        value = _clean_string(
            raw,
            name,
            maximum=LIMITS[f"{name}_max"],
            errors=sub,
            required=False,
            label=name.replace("_", " "),
        )
        for entry in sub:
            entry["field"] = f"gate0.{name}"
            entry["code"] = f"gate0_{entry['code']}"
        errors.extend(sub)
        if value:
            out[name] = value
    return out or None


# --- the store ------------------------------------------------------------------

STORE_NAMESPACE = "_schema_proposals"

#: One lock for every mutation. The deployed server is a single process (see the
#: workspace's record lock), and create has to read the whole set to check a
#: duplicate and the caps, so a per-proposal lock would not cover it.
_STORE_LOCK = threading.RLock()


class ProposalStoreUnavailable(Exception):
    """The working folder could not be written."""


def store_root() -> Path:
    """``<workspace>/_schema_proposals``: normal scope only, never a worked-example session."""
    return ws.workspace_root() / STORE_NAMESPACE


def _proposal_path(proposal_id: str) -> Path | None:
    if not is_record_id(proposal_id):
        return None
    return store_root() / f"{proposal_id}.json"


def _readable(doc: Any, proposal_id: str) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("id") == proposal_id
        and doc.get("proposal_type") in PROPOSAL_TYPES
        and doc.get("status") in PROPOSAL_STATUSES
        and isinstance(doc.get("section"), str)
        and isinstance(doc.get("category"), str)
        and isinstance(doc.get("description"), str)
    )


def _load(proposal_id: str) -> dict | None:
    path = _proposal_path(proposal_id)
    if path is None or not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if _readable(doc, proposal_id) else None


def _save(doc: dict) -> None:
    path = _proposal_path(doc["id"])
    assert path is not None
    try:
        ws.atomic_write_text(path, json.dumps(doc, indent=2, ensure_ascii=True) + "\n")
    except OSError as exc:
        raise ProposalStoreUnavailable() from exc


def _all_proposals() -> list[dict]:
    """Every readable proposal, newest first. An unreadable file is skipped, so one
    corrupt document cannot empty the list for everyone."""
    root = store_root()
    if not root.is_dir():
        return []
    out: list[dict] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.suffix != ".json" or not is_record_id(entry.stem):
            continue
        doc = _load(entry.stem)
        if doc is not None:
            out.append(doc)
    # ULIDs begin with a millisecond timestamp, so id order is creation order.
    out.sort(key=lambda d: d["id"], reverse=True)
    return out


def _prune_withdrawn() -> int:
    """Remove the OLDEST withdrawn proposals beyond ``max_withdrawn_kept``; returns how many.

    A withdrawn proposal no longer counts toward the pending limit, so something has to bound
    how many are kept on disk; this keeps the newest ones and says how many it removed (the
    create response carries ``withdrawn_removed``). Pending proposals are never touched."""
    withdrawn = [d for d in _all_proposals() if d["status"] == STATUS_WITHDRAWN]
    excess = withdrawn[LIMITS["max_withdrawn_kept"] :]  # newest first, so the tail is the oldest
    removed = 0
    for doc in excess:
        path = _proposal_path(doc["id"])
        if path is None:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _term_conflict(sources: dict, clean: dict) -> dict | None:
    """The existing term this one duplicates, if any (case and separator insensitive), in the
    portal list for the category and in the schema enum with the same key."""
    wanted = _separator_free(clean["term"])
    portal_list = _portal_term_list(sources, clean["section"], clean["category"])
    schema_list = _schema_enum(sources, clean["category"])
    for source, entry in (("portal", portal_list), ("schema", schema_list)):
        if entry is None:
            continue
        for existing in entry["terms"]:
            if _separator_free(existing) == wanted:
                return {"existing_term": existing, "existing_in": source}
    return None


def _category_conflict(sources: dict, clean: dict) -> dict | None:
    """A category key that already exists: as ANY portal entry (a term list or not), as a schema
    enum, or as a schema field of any kind."""
    key = clean["category"]
    in_portal = _portal_key_exists(sources, key)
    if in_portal is not None:
        return {"existing_category": key, "existing_in": "portal", "existing_section": in_portal}
    if _schema_enum(sources, key) is not None:
        return {"existing_category": key, "existing_in": "schema"}
    for field in sources["schema"].get("fields", {}):
        if field.casefold() == key.casefold():
            return {"existing_category": field, "existing_in": "schema"}
    return None


def _same_proposal(a: dict, b: dict) -> bool:
    return (
        a["proposal_type"] == b["proposal_type"]
        and a["section"] == b["section"]
        and a["category"].casefold() == b["category"].casefold()
        and (a.get("term") or "").casefold() == (b.get("term") or "").casefold()
    )


# --- views ----------------------------------------------------------------------


def _view(doc: dict) -> dict:
    """The public shape of one stored proposal. Built field by field, so an unexpected
    key in a stored file can never ride out in a response."""
    gate0 = doc.get("gate0") if isinstance(doc.get("gate0"), dict) else None
    return {
        "id": doc["id"],
        "proposal_type": doc["proposal_type"],
        "section": doc["section"],
        "category": doc["category"],
        "term": doc.get("term") if isinstance(doc.get("term"), str) else None,
        "description": doc["description"],
        "gate0": {k: gate0[k] for k in _GATE0_FIELDS if isinstance(gate0.get(k), str)} if gate0 else None,
        "status": doc["status"],
        "proposed_by": doc.get("proposed_by") if isinstance(doc.get("proposed_by"), str) else None,
        "attribution": (
            ATTRIBUTION_VERIFIED
            if doc.get("attribution") == ATTRIBUTION_VERIFIED and isinstance(doc.get("proposed_by"), str)
            else ATTRIBUTION_UNVERIFIED
        ),
        "proposed_at": doc.get("proposed_at"),
        "withdrawn_at": doc.get("withdrawn_at"),
        "schema_version": doc.get("schema_version"),
        "sent_by_isaac": False,
    }


def _envelope(**extra: Any) -> dict:
    return {
        **extra,
        "persistence": copy.deepcopy(PERSISTENCE),
        "review_note": REVIEW_NOTE,
        "attribution_note": ATTRIBUTION_NOTE,
    }


def portal_body(doc: dict) -> dict:
    """The body of the portal's ``POST /portal/api/vocabulary/proposals``.

    Exactly the upstream field names. ``proposal_type`` is carried for the portal's
    form (its REST route reads only the other four). The reviewer notes have no field
    upstream, so they are appended to ``description`` under a plain heading rather than
    dropped: the portal's reviewer writes the wiki definition from that text.
    """
    description = doc["description"]
    gate0 = doc.get("gate0") if isinstance(doc.get("gate0"), dict) else None
    if gate0:
        labels = (
            ("problem", "The problem"),
            ("examples", "Examples"),
            ("affected_records_estimate", "Records affected (estimate)"),
            ("flip_list", "What would change"),
        )
        lines = [f"{label}: {gate0[key]}" for key, label in labels if isinstance(gate0.get(key), str)]
        if lines:
            description = description + "\n\nWhy (for reviewers)\n" + "\n".join(lines)
    body: dict = {
        "proposal_type": doc["proposal_type"],
        "section": doc["section"],
        "category": doc["category"],
    }
    if doc["proposal_type"] == ADD_TERM:
        body["term"] = doc.get("term")
    body["description"] = description
    return body


# --- identity -------------------------------------------------------------------


def _attribution_for(request: Request) -> tuple[str | None, str]:
    """``(proposed_by, attribution)`` from the identity seam and nothing else.

    A subject is returned only for a person vouched for by a verified edge assertion.
    A fixture-attributed subject is NOT used: it is proof of a configuration, not of a
    person, and a proposal has to be able to say so about itself.
    """
    identity = identity_module.resolve_identity_for_request(request)
    subject = identity_module.stamp_actor(identity, None)
    human = getattr(identity, "human", None)
    if (
        subject
        and human is not None
        and human.trust_basis == identity_module.TRUST_BASIS_VERIFIED_EDGE_ASSERTION
    ):
        return subject, ATTRIBUTION_VERIFIED
    return None, ATTRIBUTION_UNVERIFIED


# --- the routes -----------------------------------------------------------------

class _CappedRequest(Request):
    """A request whose body is read with a ceiling, BEFORE anything parses it.

    FastAPI reads and parses the whole body before a handler runs, so a size check in the
    handler would come after the cost. This reads the stream itself, refuses on a declared
    ``Content-Length`` over the ceiling without reading, and counts the bytes of an
    undeclared (chunked) body as they arrive."""

    async def body(self) -> bytes:
        if not hasattr(self, "_body"):
            cap = LIMITS["max_body_bytes"]
            declared = self.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > cap:
                raise HTTPException(status_code=413, detail="body_too_large")
            chunks: list[bytes] = []
            total = 0
            async for chunk in self.stream():
                total += len(chunk)
                if total > cap:
                    raise HTTPException(status_code=413, detail="body_too_large")
                chunks.append(chunk)
            self._body = b"".join(chunks)
        return self._body


class _CappedRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(_CappedRequest(request.scope, request.receive))
            except HTTPException as exc:
                if exc.status_code == 413:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "body_too_large",
                            "message": f"A proposal is at most {LIMITS['max_body_bytes']} bytes; this request was larger and nothing was read or saved.",
                        },
                    )
                raise

        return handler


router = APIRouter(prefix="/api/schema-proposals", tags=[TAG_SCHEMA_PROPOSALS], route_class=_CappedRoute)

_R_UNAUTHORIZED: dict = {
    401: {
        "description": (
            "The deployment requires an API key and the request did not present a "
            "valid one. Never returned when the deployment leaves this "
            "authentication disabled, which is the default for local runs."
        )
    },
}

_R_NOT_FOUND: dict = {
    404: {
        "description": (
            "No proposal on this server has that id. A proposal on a hosted server "
            "may also be gone because the server restarted."
        )
    },
}

_R_STORE_UNAVAILABLE: dict = {
    503: {
        "description": (
            "This server's working folder could not be written, so nothing was saved."
        )
    },
}


def _refuse(status: int, error: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message, **extra})


def _not_found() -> JSONResponse:
    return _refuse(
        404,
        "proposal_not_found",
        "No proposal on this server has that id. Proposals here are temporary and may "
        "have been cleared by a restart.",
    )


def _unavailable() -> JSONResponse:
    return _refuse(
        503,
        "proposal_store_unavailable",
        "This server could not save the proposal, so nothing was saved. Try again, or "
        "copy the proposal into the ISAAC portal directly.",
    )


@router.get(
    "/vocabulary",
    summary="Browse the Vocabulary Sources",
    description=(
        "Two labelled lists of sections, categories and allowed terms. `portal` is a verbatim "
        "snapshot of the ISAAC portal's vocabulary file at a named upstream commit, the list "
        "the portal checks a proposed term against; it is a snapshot and the portal's own copy may "
        "have moved. `schema` is the enums of the vendored official record schema, read at the moment "
        "of the request, the lists a record is validated against. The two overlap only in part, "
        "and neither is the live portal.\n\n"
        "A category is a field whose value must be one of a fixed list; a section is a top-level "
        "block of the record, with the record's own root fields under Record Info. `proposal_sections` "
        "is the union a proposal may name, with the portal term lists a new term may join.\n\n"
        "The response also carries the limits a proposal is held to, so a client does not carry a second "
        "copy of them. It is read-only: nothing here changes the schema or the portal."
    ),
    response_description="Both vocabulary sources, the sections a proposal may name, and the proposal limits.",
    responses={**_R_UNAUTHORIZED},
)
def get_vocabulary() -> dict:
    sources = load_sources()
    schema_v, portal_v = sources["schema"], sources["portal"]
    schema_public = {k: schema_v[k] for k in ("sections", "section_count", "category_count", "term_count")}
    proposal_sections = []
    for sec in sources["sections"]:
        lists = [
            c["key"]
            for p in portal_v["sections"]
            if p["id"] == sec["id"]
            for c in p["categories"]
            if c["kind"] == "terms" and c["terms"]
        ]
        proposal_sections.append({**sec, "term_lists": lists})
    return {
        "schema_version": EXPECTED_VERSION,
        "default_source": "portal",
        "sources": {
            "portal": {
                "id": "portal",
                "label": PORTAL_SNAPSHOT_LABEL,
                "detail": (
                    "A copy of the ISAAC portal's vocabulary file at one upstream commit. A new term is checked "
                    "against these lists. It may be out of date: the portal's own copy is the one that decides."
                ),
                "snapshot_commit": PORTAL_SNAPSHOT_COMMIT,
                "sha256": portal_v["portal_sha256"],
                "section_count": portal_v["section_count"],
                "category_count": portal_v["category_count"],
                "term_list_count": portal_v["term_list_count"],
                "term_count": portal_v["term_count"],
                "sections": portal_v["sections"],
            },
            "schema": {
                "id": "schema",
                "label": f"Schema enums (vendored v{EXPECTED_VERSION})",
                "detail": (
                    "The fixed lists in the official record schema this build validates records against, read from "
                    "the vendored file. Only part of it is also a portal list."
                ),
                "derived_from": "schema/isaac_record_v1.json",
                "sha256": schema_v["schema_sha256"],
                **schema_public,
                "term_list_count": schema_public["category_count"],
            },
        },
        "proposal_sections": proposal_sections,
        "proposal_types": list(PROPOSAL_TYPES),
        "limits": dict(LIMITS),
        "term_rule": (
            "One word, no spaces, starting with a letter. If every existing term in the "
            "category is lowercase with underscores, a new term must be too."
        ),
        "review_note": REVIEW_NOTE,
    }


@router.post(
    "",
    status_code=201,
    summary="Draft a Schema Proposal",
    description=(
        "Saves a proposal to change the ISAAC vocabulary, in the shape the "
        "ISAAC portal takes. `proposal_type` is `add_term` (needs `section`, `category`, "
        "`term`, `description`) or `add_category` (needs `section`, `category`, "
        "`description`). An optional `gate0` object holds four free-text answers for "
        "reviewers: `problem`, `examples`, `affected_records_estimate`, `flip_list`.\n\n"
        "THIS APPROVES NOTHING AND SENDS NOTHING. The proposal is stored as `pending` "
        "on this server; the owners of the standard review it in the ISAAC portal, and "
        "any decision is recorded there. Use the portal-payload operation to get the "
        "exact body to send.\n\n"
        "Nobody is identified on this server, so `proposed_by` is `null` and "
        "`attribution` is `unverified`. A name in the request body is ignored and "
        "listed in `ignored_fields`. Proposals are temporary on a hosted server; the "
        "response says so in `persistence`.\n\n"
        "A body that fails validation is refused with `422` and an `errors` list, one "
        "entry per field (`field`, `code`, `message`), so a form can show each problem "
        "in place. A new term is checked against the portal vocabulary snapshot's list for the category "
        "(and the schema enum with the same key): one already there is `409 term_already_exists`, and a "
        "category the portal has no list for is `422`. A new category is refused with `409` when either "
        "source already has the key and with `422 category_not_a_text_field` for a schema field that "
        "does not take words. The same proposal already pending is `409 duplicate_pending_proposal`. "
        "A body over 131072 bytes is `413` and is not read."
    ),
    response_description="The saved proposal, as pending.",
    responses={
        **_R_UNAUTHORIZED,
        409: {
            "description": (
                "The term or category already exists in the schema, or an identical "
                "proposal is already pending."
            )
        },
        413: {"description": "The request body is larger than a proposal can be; it was not read."},
        429: {
            "description": (
                "This server already holds the maximum number of pending proposals. The "
                "limit is shared by everyone using this server (one workspace); withdrawing "
                "a proposal frees its place."
            )
        },
        **_R_STORE_UNAVAILABLE,
    },
)
def post_schema_proposal(
    request: Request,
    body: Any = Body(
        default=None,
        description=(
            "`{\"proposal_type\": \"add_term\" | \"add_category\", \"section\", "
            "\"category\", \"term\" (add_term only), \"description\", \"gate0\" "
            "(optional)}`."
        ),
    ),
):
    if not isinstance(body, dict):
        return _refuse(422, "invalid_body", "The request body must be a JSON object.", errors=[])
    sources = load_sources()
    clean, errors, ignored = _validate(body, sources)
    if clean is None:
        return _refuse(
            422,
            errors[0]["code"],
            "The proposal needs a few changes before it can be saved.",
            errors=errors,
        )

    if clean["proposal_type"] == ADD_TERM:
        conflict = _term_conflict(sources, clean)
        if conflict is not None:
            where = "the portal vocabulary snapshot" if conflict["existing_in"] == "portal" else "the ISAAC schema"
            return _refuse(
                409,
                "term_already_exists",
                f"'{conflict['existing_term']}' is already an allowed term in this category ({where}). "
                "Use it instead of proposing it.",
                **conflict,
            )
    else:
        conflict = _category_conflict(sources, clean)
        if conflict is not None:
            where = "the portal vocabulary snapshot" if conflict["existing_in"] == "portal" else "the ISAAC schema"
            return _refuse(
                409,
                "category_already_exists",
                f"That category or field already exists in {where}.",
                **conflict,
            )

    proposed_by, attribution = _attribution_for(request)
    doc = {
        "id": new_record_id(),
        "proposal_type": clean["proposal_type"],
        "section": clean["section"],
        "category": clean["category"],
        "term": clean["term"],
        "description": clean["description"],
        "gate0": clean["gate0"],
        "status": STATUS_PENDING,
        "proposed_by": proposed_by,
        "attribution": attribution,
        "proposed_at": _now(),
        "withdrawn_at": None,
        "schema_version": EXPECTED_VERSION,
    }
    try:
        with _STORE_LOCK:
            existing = _all_proposals()
            for other in existing:
                if other["status"] == STATUS_PENDING and _same_proposal(other, doc):
                    return _refuse(
                        409,
                        "duplicate_pending_proposal",
                        "An identical proposal is already pending on this server.",
                        proposal_id=other["id"],
                    )
            pending = sum(1 for d in existing if d["status"] == STATUS_PENDING)
            if pending >= LIMITS["max_pending"]:
                return _refuse(
                    429,
                    "too_many_pending",
                    f"This server already holds {LIMITS['max_pending']} pending proposals. The limit is shared by "
                    "everyone using this server, and withdrawing a proposal frees its place. Send the pending "
                    "ones to the ISAAC portal first.",
                )
            _save(doc)
            removed = _prune_withdrawn()
    except ProposalStoreUnavailable:
        return _unavailable()
    return JSONResponse(
        status_code=201,
        content=_envelope(proposal=_view(doc), ignored_fields=ignored, withdrawn_removed=removed),
    )


@router.get(
    "",
    summary="Browse Schema Proposals",
    description=(
        "Proposals on this server, newest first, in pages. `limit` is at most 100 and "
        "`offset` counts from the newest; `status` narrows to `pending` or "
        "`withdrawn`. `total` counts every match, so a client can page without "
        "guessing.\n\n"
        "THERE ARE ONLY TWO STATUSES HERE. A decision by the standard's owners is "
        "made and recorded in the ISAAC portal, never in this list. Everyone who can "
        "reach this server sees every proposal, because nobody is identified."
    ),
    response_description="One page of proposals, newest first.",
    responses={**_R_UNAUTHORIZED},
)
def list_schema_proposals(
    limit: int = Query(25, ge=1, le=LIMITS["page_max"], description="Page size, at most 100."),
    offset: int = Query(0, ge=0, le=100_000, description="How many of the newest to skip."),
    status: str | None = Query(
        None,
        pattern="^(pending|withdrawn)$",
        description="Only proposals with this status: `pending` or `withdrawn`.",
    ),
) -> dict:
    everything = _all_proposals()
    pending_total = sum(1 for d in everything if d["status"] == STATUS_PENDING)
    items = everything
    if status is not None:
        items = [d for d in items if d["status"] == status]
    page = items[offset : offset + limit]
    end = offset + len(page)
    return _envelope(
        proposals=[_view(d) for d in page],
        total=len(items),
        limit=limit,
        offset=offset,
        next_offset=end if end < len(items) else None,
        statuses=list(PROPOSAL_STATUSES),
        capacity={
            "pending": pending_total,
            "max_pending": LIMITS["max_pending"],
            "max_withdrawn_kept": LIMITS["max_withdrawn_kept"],
            "scope": "Shared by everyone using this server (one workspace); a withdrawn proposal frees its place.",
        },
    )


@router.get(
    "/{proposal_id}",
    summary="Read One Schema Proposal",
    description=(
        "One proposal, with its status, its reviewer notes if any, and who proposed "
        "it. `proposed_by` is `null` and `attribution` is `unverified` unless a "
        "verified person made the request, which no deployment of this build "
        "provides.\n\n"
        "A proposal that is not on this server, including one cleared by a restart of "
        "a hosted server, is a `404`."
    ),
    response_description="The proposal.",
    responses={**_R_UNAUTHORIZED, **_R_NOT_FOUND},
)
def get_schema_proposal(
    proposal_id: str = PathParam(..., description="The proposal's id."),
):
    doc = _load(proposal_id)
    if doc is None:
        return _not_found()
    return _envelope(proposal=_view(doc))


@router.post(
    "/{proposal_id}/withdraw",
    summary="Withdraw a Schema Proposal",
    description=(
        "Marks a pending proposal as withdrawn. Only a proposal that is still "
        "`pending` can be withdrawn; anything else is `409 not_pending`. The proposal "
        "is kept, so the list still shows it.\n\n"
        "WITHDRAWING HERE DOES NOT RECALL A PROPOSAL ALREADY SENT TO THE PORTAL. "
        "ISAAC never sends one, so a person who sent it must withdraw or discuss it "
        "there. Nobody is identified on this server, so anyone who can reach it can "
        "withdraw any pending proposal."
    ),
    response_description="The proposal, now withdrawn.",
    responses={
        **_R_UNAUTHORIZED,
        **_R_NOT_FOUND,
        409: {"description": "The proposal is not pending, so it cannot be withdrawn."},
        **_R_STORE_UNAVAILABLE,
    },
)
def withdraw_schema_proposal(
    proposal_id: str = PathParam(..., description="The proposal's id."),
):
    try:
        with _STORE_LOCK:
            doc = _load(proposal_id)
            if doc is None:
                return _not_found()
            if doc["status"] != STATUS_PENDING:
                return _refuse(
                    409,
                    "not_pending",
                    f"Only a pending proposal can be withdrawn; this one is {doc['status']}.",
                    current_status=doc["status"],
                )
            doc["status"] = STATUS_WITHDRAWN
            doc["withdrawn_at"] = _now()
            _save(doc)
            _prune_withdrawn()
    except ProposalStoreUnavailable:
        return _unavailable()
    return _envelope(proposal=_view(doc))


@router.get(
    "/{proposal_id}/portal-payload",
    summary="Get the Portal Payload for a Proposal",
    description=(
        "The exact JSON body the ISAAC portal's proposal endpoint takes, for a person "
        "who has portal access to send. ISAAC never calls the portal and never holds "
        "portal credentials; this only prepares the text.\n\n"
        "The portal's REST endpoint accepts `add_term` proposals. An `add_category` "
        "proposal is entered in the portal's Ontology Editor with the same "
        "fields, and `portal.rest_supported` says which applies. The reviewer notes "
        "have no field upstream, so they are appended to `description` under a "
        "plain heading."
    ),
    response_description="The portal request body and where it goes.",
    responses={**_R_UNAUTHORIZED, **_R_NOT_FOUND},
)
def get_schema_proposal_portal_payload(
    proposal_id: str = PathParam(..., description="The proposal's id."),
):
    doc = _load(proposal_id)
    if doc is None:
        return _not_found()
    rest_supported = doc["proposal_type"] == ADD_TERM
    notes = [
        "ISAAC has not sent this. Someone with ISAAC portal access has to.",
        "The ISAAC standard's owners review it in the portal and record any decision there.",
    ]
    if doc.get("gate0"):
        notes.append(
            "The reviewer notes are appended to the description, because the portal has no separate field for them."
        )
    if rest_supported:
        notes.append(
            "The portal checks the section and category against its own vocabulary; if the "
            "portal's list differs from the schema ISAAC reads, it may ask for a different category key."
        )
    else:
        notes.append(
            "The portal's web endpoint takes new terms only. A new category is entered in the portal's "
            "Ontology Editor (its Propose a Change form), using these fields; do not post this body to the "
            "web endpoint, which would refuse it."
        )
    return _envelope(
        proposal_id=doc["id"],
        status=doc["status"],
        portal={
            "method": "POST",
            "path": PORTAL_PROPOSALS_PATH,
            "rest_supported": rest_supported,
        },
        body=portal_body(doc),
        sent_by_isaac=False,
        notes=notes,
    )
