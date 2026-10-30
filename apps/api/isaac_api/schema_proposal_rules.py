"""The rules and formats a schema proposal is held to, with no web framework.

``schema_proposals.py`` serves Schema Proposals over HTTP; this module is the part of it
that does not need HTTP: deriving the vocabulary from the vendored schema and the portal
snapshot, checking a proposal body, the body of the portal's ``POST
/portal/api/vocabulary/proposals``, and the ISAAC-side schema change request document.

It exists as its own module so the LOCAL-FIRST CLI (``isaac bundle propose-terms``, under
``local_import``) can produce drafts in exactly the format the website produces without
importing FastAPI: a scientist's local install has no web framework, and the local import
package is pinned to import none (``test_local_import_engine.py``). Everything here is
pure or reads a file it is given; nothing here writes, sends or calls anything.

``schema_proposals`` re-exports every name it used to define, so the website's behaviour
and its tests are unchanged by the move.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

# --- the contract's constants ---------------------------------------------------

ADD_TERM = "add_term"
ADD_CATEGORY = "add_category"
#: The two proposal types the upstream portal defines (``portal/database.py``
#: ``create_proposal``, ``portal/ontology.py`` ``apply_approved_proposal``, and the "Propose a
#: Change" form in ``portal/app.py``, all at ``a1cb1c8``). It defines no third.
PORTAL_PROPOSAL_TYPES = (ADD_TERM, ADD_CATEGORY)
#: An ISAAC-side "schema change request": a new FIELD in the record schema. THE PORTAL HAS NO
#: SUCH PROPOSAL TYPE, so this is never a portal payload. Its export is a document for the
#: standard's owners, shaped after the upstream repository's own change process
#: (``governance/README.md``: gate 0, "a schema change also needs a migration plan, a version
#: and a rollback"; drafts in ``governance/changes/PROPOSED.md``).
SCHEMA_CHANGE = "schema_change"
PROPOSAL_TYPES = (ADD_TERM, ADD_CATEGORY, SCHEMA_CHANGE)

#: What a schema change request can ask for. One kind: a new field under an object the schema
#: already declares. Changing or removing an existing field is not drafted here.
SCHEMA_CHANGE_ADD_FIELD = "add_field"
SCHEMA_CHANGE_KINDS = (SCHEMA_CHANGE_ADD_FIELD,)
#: JSON Schema's own value types (``null`` is not a field type on its own).
SCHEMA_CHANGE_VALUE_TYPES = ("string", "number", "integer", "boolean", "object", "array")
#: Where the upstream process says a field belongs: the generic core, or one science's
#: profile ("a field only one science wants goes to that science's profile").
SCHEMA_CHANGE_SCOPES = ("core", "domain_profile")
_UNIT_TYPES = ("number", "integer", "array")
_FIELD_NAME = re.compile(r"\A[A-Za-z][A-Za-z0-9_]*\Z")
_CHANGE_KEYS = (
    "kind",
    "parent_path",
    "field_name",
    "value_type",
    "unit",
    "required",
    "example",
    "scope",
    "migration",
)

#: The upstream repository's change process, as read at ``a1cb1c8`` (2026-10-29). Stated so a
#: person knows where a schema change request goes; ISAAC sends it nowhere.
UPSTREAM_GOVERNANCE: dict = {
    "repository": "https://github.com/ISAAC-DOE/isaac-ai-ready-record",
    "read_at_commit": "a1cb1c861f3e6eb506da33f27196b43312f240f6",
    "process": "governance/README.md",
    "ledger": "governance/changes/README.md",
    "drafts": "governance/changes/PROPOSED.md",
    "issues_enabled_when_read": False,
}

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
    "field_name_max": 80,
    "unit_max": 40,
    "example_max": 500,
    "migration_max": 2000,
    "max_pending": 50,
    "max_withdrawn_kept": 500,
    "max_body_bytes": 131_072,
    "page_max": 100,
}

#: The portal's own cap on one person's pending proposals is 50. Here the same number is
#: shared by EVERYONE using this server (one workspace), because nobody is identified; a
#: withdrawn proposal frees its slot, and only the newest ``max_withdrawn_kept`` withdrawn
#: ones are kept on disk (the oldest are removed, and the response says so).
#: ONE definition of a term's shape, compiled here and served to the browser
#: (:data:`TERM_SHAPE_FOR_CLIENTS`), so a "Propose this term" link is offered only for a term
#: these same rules would accept.
TERM_SHAPE_BODY = r"[A-Za-z][A-Za-z0-9_./-]*"
SNAKE_TERM_BODY = r"[a-z][a-z0-9_]*"
PATH_LIKE_PATTERN = r"(\.\.|//|\./|/\.)"
_TERM_SHAPE = re.compile(rf"\A{TERM_SHAPE_BODY}\Z")
_SNAKE_TERM = re.compile(rf"\A{SNAKE_TERM_BODY}\Z")
_PATH_LIKE = re.compile(PATH_LIKE_PATTERN)
#: The same three rules as JavaScript-compatible patterns (``^…$`` for ``\A…\Z``).
TERM_SHAPE_FOR_CLIENTS: dict = {
    "term": f"^{TERM_SHAPE_BODY}$",
    "snake_case": f"^{SNAKE_TERM_BODY}$",
    "path_like": PATH_LIKE_PATTERN,
}
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
_BODY_KEYS = frozenset({"proposal_type", "section", "category", "term", "description", "gate0", "change"})

#: The portal's endpoint, stated so a person knows where the payload goes. ISAAC never
#: calls it.
PORTAL_PROPOSALS_PATH = "/portal/api/vocabulary/proposals"


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


def derive_object_paths(schema: dict) -> list[dict]:
    """Every place a NEW FIELD could go: each object the schema declares with ``properties``.

    ``[{"path": "context.electrochemistry", "section": "Context", "open": False,
    "fields": [...]}, ...]`` in schema order, the record root first (``path`` ``""``, section
    ``Record Info``). Arrays are looked through to their ``items`` (a field of each element
    of ``descriptors.outputs`` is a field of ``descriptors.outputs``). ``open`` is whether the
    schema accepts an undeclared key there today: ``False`` exactly when the object says
    ``additionalProperties: false``. Derived, never transcribed, for the reason
    :func:`derive_vocabulary` gives.
    """
    out: list[dict] = []
    seen: set[str] = set()

    def walk(node: Any, path: list[str]) -> None:
        if not isinstance(node, dict):
            return
        props = node.get("properties")
        if isinstance(props, dict):
            key = ".".join(path)
            if key not in seen:
                seen.add(key)
                section = ROOT_SECTION if not path else _section_label(path[0])
                out.append(
                    {
                        "path": key,
                        "section": section,
                        "open": node.get("additionalProperties", True) is not False,
                        "fields": [str(name) for name in props],
                    }
                )
            for name, child in props.items():
                walk(child, [*path, str(name)])
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, path)

    walk(schema if isinstance(schema, dict) else {}, [])
    return out


def schema_vocabulary_from_text(text: str) -> dict:
    """The schema-enum vocabulary of one schema document's text, with ``fields``,
    ``object_paths`` and ``schema_sha256``. Pure: the caller reads the file."""
    schema = json.loads(text)
    vocabulary = derive_vocabulary(schema)
    vocabulary["fields"] = derive_fields(schema)
    vocabulary["object_paths"] = derive_object_paths(schema)
    vocabulary["schema_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return vocabulary


def portal_vocabulary_from_text(text: str) -> dict:
    """The portal snapshot's text as sections and categories, with ``portal_sha256``."""
    vocabulary = derive_portal_vocabulary(json.loads(text))
    vocabulary["portal_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return vocabulary


def combine_sources(schema_v: dict, portal_v: dict) -> dict:
    """Both vocabulary sources and the union of their sections (portal order first)."""
    sections: list[dict] = []
    seen: set[str] = set()
    for source in (portal_v, schema_v):
        for sec in source["sections"]:
            if sec["id"] in seen:
                continue
            seen.add(sec["id"])
            sections.append({"id": sec["id"], "label": sec["label"], "block": sec["block"]})
    return {"schema": schema_v, "portal": portal_v, "sections": sections}


def load_sources_at(schema_file: Path, portal_file: Path = PORTAL_SNAPSHOT_FILE) -> dict:
    """:func:`combine_sources` over two files. For the local CLI, which has no cache."""
    return combine_sources(
        schema_vocabulary_from_text(Path(schema_file).read_text(encoding="utf-8")),
        portal_vocabulary_from_text(Path(portal_file).read_text(encoding="utf-8")),
    )


def section_of_term_list(sources: dict, category: str) -> str | None:
    """The portal section whose TERM LIST is ``category``, or ``None``. A key the portal holds
    in more than one section is ambiguous and also ``None`` (the snapshot has none)."""
    found = [
        sec["id"]
        for sec in sources["portal"]["sections"]
        for c in sec["categories"]
        if c["key"] == category and c["kind"] == "terms" and c["terms"]
    ]
    return found[0] if len(found) == 1 else None


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
                "Proposal type must be add_term (a new allowed value), add_category (a new list of allowed "
                "values) or schema_change (a new field in the record schema).",
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

    term: str | None = None
    change: dict | None = None
    if proposal_type == SCHEMA_CHANGE:
        # The field's path is the change's own parent path and name, so the server sets it.
        category = None
        if body.get("category") not in (None, ""):
            errors.append(
                _error(
                    "category",
                    "category_not_allowed",
                    "A schema change request names its place in the schema under change.parent_path and "
                    "change.field_name; it takes no category.",
                )
            )
    else:
        category = _clean_string(
            body, "category", maximum=LIMITS["category_max"], errors=errors, required=True
        )
        if "change" in body and body.get("change") is not None:
            errors.append(
                _error(
                    "change",
                    "change_not_allowed",
                    "Only a schema change request (a new field) takes a change; a new term or list does not.",
                )
            )

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
    elif proposal_type == SCHEMA_CHANGE:
        if "term" in body and body.get("term") not in (None, ""):
            errors.append(
                _error(
                    "term",
                    "term_not_allowed",
                    "A schema change request proposes a field, not a term; propose its terms once the field exists.",
                )
            )
        change = _validate_change(body.get("change"), sources, section, errors)
        if change is not None:
            category = change["path"]
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
    if proposal_type == SCHEMA_CHANGE and not (gate0 or {}).get("problem") and not any(
        e["field"] == "gate0.problem" or e["field"] == "gate0" for e in errors
    ):
        # The upstream process blocks a change with no gate-0 proposal: "the problem with
        # counts and examples" first. A new term can be argued from its description; a new
        # field cannot.
        errors.append(
            _error(
                "gate0.problem",
                "gate0_problem_required",
                "A schema change request needs the problem it solves, with counts and examples: the "
                "standard's process will not consider a schema change without one.",
            )
        )

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
            "change": change,
        },
        [],
        ignored,
    )


def _object_path(sources: dict, path: str) -> dict | None:
    for entry in sources["schema"].get("object_paths") or ():
        if entry["path"] == path:
            return entry
    return None


def _example_problem(example: str, value_type: str) -> str | None:
    """Why ``example`` is not a value of ``value_type``, or ``None``. A number must read as a
    finite number, an integer as a whole number, a boolean as ``true``/``false``, and an object
    or array as JSON of that shape. Text is any text."""
    if value_type == "string":
        return None
    if value_type == "boolean":
        return None if example in ("true", "false") else "An example of a yes/no field is true or false."
    try:
        parsed = json.loads(example)
    except ValueError:
        parsed = None
    if value_type == "number":
        ok = isinstance(parsed, (int, float)) and not isinstance(parsed, bool) and parsed == parsed and abs(parsed) != float("inf")
        return None if ok else "An example of a number field is a number, such as 0.5."
    if value_type == "integer":
        # JSON Schema counts a number with a zero fractional part (3.0) as an integer.
        ok = (isinstance(parsed, int) and not isinstance(parsed, bool)) or (
            isinstance(parsed, float) and parsed.is_integer()
        )
        return None if ok else "An example of a whole-number field is a whole number, such as 3."
    if value_type == "object":
        return None if isinstance(parsed, dict) else "An example of an object field is a JSON object, such as {\"a\": 1}."
    if value_type == "array":
        return None if isinstance(parsed, list) else "An example of a list field is a JSON list, such as [1, 2]."
    return None


def _validate_change(raw: Any, sources: dict, section: dict | None, errors: list[dict]) -> dict | None:
    """The ``change`` block of a schema change request. Returns the clean block (with its
    full ``path``) or ``None``; every problem is appended to ``errors`` under ``change.<key>``.

    The parent must be an object the vendored schema declares (:func:`derive_object_paths`),
    inside the section the request names; the field name must not already be one of the
    parent's fields (that is a ``409``, decided by :func:`_field_conflict`)."""
    if not isinstance(raw, dict):
        errors.append(
            _error(
                "change",
                "change_required",
                "A schema change request needs a change: where the field goes, its name, its type and "
                "whether it is required.",
            )
        )
        return None
    local: list[dict] = []
    for key in sorted(raw):
        if key not in _CHANGE_KEYS:
            safe = _safe_field_name(key)
            local.append(
                _error(
                    f"change.{safe}" if safe else "change",
                    "unknown_field",
                    "A schema change takes only kind, parent_path, field_name, value_type, unit, required, "
                    "example, scope and migration.",
                )
            )

    kind = raw.get("kind", SCHEMA_CHANGE_ADD_FIELD)
    if kind not in SCHEMA_CHANGE_KINDS:
        local.append(
            _error(
                "change.kind",
                "invalid_change_kind",
                "The only schema change drafted here is add_field: a new field under an object the schema "
                "already has.",
            )
        )

    parent_raw = raw.get("parent_path")
    parent: dict | None = None
    if not isinstance(parent_raw, str):
        local.append(
            _error(
                "change.parent_path",
                "parent_path_required",
                "Choose where in the schema the field goes (the record root, or one of its blocks).",
            )
        )
    else:
        parent = _object_path(sources, parent_raw.strip())
        if parent is None:
            local.append(
                _error(
                    "change.parent_path",
                    "unknown_parent_path",
                    "That is not a block the ISAAC schema declares. Choose one from the list.",
                )
            )
        elif section is not None and parent["section"] != section["id"]:
            local.append(
                _error(
                    "change.parent_path",
                    "parent_outside_section",
                    f"{parent['path'] or 'The record root'} is in the {parent['section']} section, not "
                    f"{section['label']}.",
                )
            )

    sub: list[dict] = []
    name = _clean_string(raw, "field_name", maximum=LIMITS["field_name_max"], errors=sub, required=True, label="field name")
    if name is not None and not _FIELD_NAME.match(name):
        sub.append(
            _error(
                "field_name",
                "invalid_field_name",
                "A field name is one word: a letter, then letters, digits or underscores (for example "
                "c_rate or temperature_K).",
            )
        )
        name = None

    value_type = raw.get("value_type")
    if value_type not in SCHEMA_CHANGE_VALUE_TYPES:
        sub.append(
            _error(
                "value_type",
                "invalid_value_type",
                "Choose the kind of value: text, number, whole number, yes/no, a group of fields, or a list.",
            )
        )
        value_type = None

    unit = _clean_string(raw, "unit", maximum=LIMITS["unit_max"], errors=sub, required=False)
    if unit is not None and value_type is not None and value_type not in _UNIT_TYPES:
        sub.append(
            _error(
                "unit",
                "unit_not_allowed",
                "Only a number, a whole number or a list of numbers has a unit.",
            )
        )

    required = raw.get("required")
    if not isinstance(required, bool):
        sub.append(
            _error(
                "required",
                "required_must_be_stated",
                "Say whether a record must carry this field (yes or no).",
            )
        )

    example = _clean_string(raw, "example", maximum=LIMITS["example_max"], errors=sub, required=False)
    if example is not None and value_type is not None:
        problem = _example_problem(example, value_type)
        if problem is not None:
            sub.append(_error("example", "example_does_not_fit_type", problem))

    scope = raw.get("scope")
    if scope is not None and scope not in SCHEMA_CHANGE_SCOPES:
        sub.append(
            _error(
                "scope",
                "invalid_scope",
                "Scope is core (every science) or domain_profile (one science's profile), or left out.",
            )
        )

    migration = _clean_string(raw, "migration", maximum=LIMITS["migration_max"], errors=sub, required=False)

    for entry in sub:
        if entry["field"] and not entry["field"].startswith("change."):
            entry["field"] = f"change.{entry['field']}"
    local.extend(sub)
    errors.extend(local)
    if local or parent is None or name is None:
        return None
    return {
        "kind": kind,
        "parent_path": parent["path"],
        "field_name": name,
        "path": f"{parent['path']}.{name}" if parent["path"] else name,
        "value_type": value_type,
        "unit": unit,
        "required": required,
        "example": example,
        "scope": scope,
        "migration": migration,
        "parent_open_today": parent["open"],
    }


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


# --- conflicts with what already exists ----------------------------------------


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


def _field_conflict(sources: dict, clean: dict) -> dict | None:
    """The field a schema change request duplicates, if any: a field of the same parent whose
    name matches case-insensitively (``temperature_k`` is ``temperature_K``)."""
    change = clean.get("change") or {}
    parent = _object_path(sources, change.get("parent_path", ""))
    if parent is None:
        return None
    wanted = str(change.get("field_name", "")).casefold()
    for existing in parent["fields"]:
        if existing.casefold() == wanted:
            path = f"{parent['path']}.{existing}" if parent["path"] else existing
            return {"existing_field": path, "existing_in": "schema"}
    return None


def _same_proposal(a: dict, b: dict) -> bool:
    return (
        a["proposal_type"] == b["proposal_type"]
        and a["section"] == b["section"]
        and a["category"].casefold() == b["category"].casefold()
        and (a.get("term") or "").casefold() == (b.get("term") or "").casefold()
    )


# --- the portal's body ----------------------------------------------------------


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


def portal_payload(doc: dict) -> dict:
    """Where a new term or list goes and the body to send: the ``portal``, ``body``,
    ``sent_by_isaac`` and ``notes`` of ``GET .../portal-payload``. Shared by the website and the
    local ``isaac bundle propose-terms``, so the two hand out one format."""
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
    return {
        "portal": {"method": "POST", "path": PORTAL_PROPOSALS_PATH, "rest_supported": rest_supported},
        "body": portal_body(doc),
        "sent_by_isaac": False,
        "notes": notes,
    }


# --- the schema change request (ISAAC-side; never a portal payload) ---------------

CHANGE_REQUEST_FORMAT = "isaac.schema-change-request"
CHANGE_REQUEST_FORMAT_VERSION = "1"

_VALUE_TYPE_WORDS = {
    "string": "text",
    "number": "number",
    "integer": "whole number",
    "boolean": "yes/no",
    "object": "a group of fields",
    "array": "a list",
}

NOT_A_PORTAL_PROPOSAL = (
    "The ISAAC portal's Propose a Change takes two kinds of proposal: a new term for an existing "
    "list, and a new list. It has no proposal type for a new field in the schema, so this is not a "
    "portal proposal and there is no portal payload for it."
)


def _md_cell(text: str) -> str:
    """One Markdown table cell: pipes escaped, line breaks flattened."""
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def change_request(doc: dict, *, schema_version: str, schema_sha256: str | None) -> dict:
    """The document a schema change request exports: ``{"markdown": ..., "document": ...}``.

    Shaped after the upstream repository's own change files (``governance/changes/``): the
    product and kind, then the change, then gate 0 (the problem with counts and examples, and
    the flip list), then what a schema change also needs (a migration plan, a version and a
    rollback). Every section the proposer did not write SAYS it was not written, rather than
    being left out, so a reader can tell "nothing to say" from "not asked". Built only from the
    stored proposal; nothing is inferred.
    """
    change = doc.get("change") if isinstance(doc.get("change"), dict) else {}
    gate0 = doc.get("gate0") if isinstance(doc.get("gate0"), dict) else {}
    path = str(change.get("path") or doc.get("category") or "")
    parent = str(change.get("parent_path") or "")
    open_today = change.get("parent_open_today")
    scope = change.get("scope")
    scope_words = {"core": "the generic core", "domain_profile": "a domain profile (one science)"}.get(
        scope, "not stated"
    )
    author = doc.get("proposed_by") if doc.get("attribution") == ATTRIBUTION_VERIFIED else None
    not_written = "Not written yet."
    # A withdrawn draft still exports (as a withdrawn term's portal payload does), and says so.
    status_line = (
        f"- **Status in ISAAC:** WITHDRAWN on {doc.get('withdrawn_at') or 'an unrecorded date'}. "
        "The proposer withdrew this draft; it is kept for the record and is not being proposed."
        if doc.get("status") == STATUS_WITHDRAWN
        else "- **Status in ISAAC:** pending (a draft; this says nothing about any decision upstream)."
    )

    document = {
        "format": CHANGE_REQUEST_FORMAT,
        "format_version": CHANGE_REQUEST_FORMAT_VERSION,
        "is_portal_payload": False,
        "not_a_portal_proposal": NOT_A_PORTAL_PROPOSAL,
        "isaac_draft_id": doc.get("id"),
        "status_in_isaac": doc.get("status"),
        "change": {
            "kind": change.get("kind"),
            "path": path,
            "parent_path": parent,
            "parent_accepts_undeclared_keys_today": open_today,
            "field_name": change.get("field_name"),
            "value_type": change.get("value_type"),
            "unit": change.get("unit"),
            "required": change.get("required"),
            "example": change.get("example"),
            "scope": scope,
        },
        "definition": doc.get("description"),
        "gate0": {
            "problem": gate0.get("problem"),
            "examples": gate0.get("examples"),
            "affected_records_estimate": gate0.get("affected_records_estimate"),
            "flip_list": gate0.get("flip_list"),
        },
        "migration_version_rollback": change.get("migration"),
        "provenance": {
            "drafted_with": "ISAAC Metadata Assistant",
            "drafted_at": doc.get("proposed_at"),
            "schema_version": schema_version,
            "schema_sha256": schema_sha256,
            "proposed_by": author,
            "attribution": doc.get("attribution") if author else ATTRIBUTION_UNVERIFIED,
            "sent_by_isaac": False,
            # ISAAC cannot see a decision made upstream, so it states only its own part.
            "approved_in_isaac": False,
        },
        "upstream_process": dict(UPSTREAM_GOVERNANCE),
    }

    def block(text: Any) -> str:
        return text.strip() if isinstance(text, str) and text.strip() else not_written

    required = change.get("required")
    rows = [
        ("Path", f"`{path}`"),
        ("Goes in", f"`{parent}`" if parent else "the record root"),
        (
            "Today",
            "the schema refuses any key it does not declare here"
            if open_today is False
            else "the schema accepts undeclared keys here (an open namespace)"
            if open_today is True
            else "not known",
        ),
        ("Type", _VALUE_TYPE_WORDS.get(str(change.get("value_type")), str(change.get("value_type")))),
        ("Unit", change.get("unit") or "none stated"),
        ("Required", "yes" if required is True else "no" if required is False else "not stated"),
        ("Example", f"`{change['example']}`" if change.get("example") else "none given"),
        ("Scope", scope_words),
    ]
    lines = [
        f"# Proposed schema change: add `{path}`",
        "",
        "> Drafted in the ISAAC Metadata Assistant for the owners of the ISAAC standard. "
        + NOT_A_PORTAL_PROPOSAL
        + " ISAAC has not sent this anywhere; ISAAC approves nothing and records no decision on it.",
        "",
        f"- **Product:** repository (schema). **Kind:** schema change ({change.get('kind') or 'add_field'}).",
        "- **Owner of the rule:** not stated; the standard's owners assign one.",
        f"- **Schema it changes:** ISAAC record schema v{schema_version}"
        + (f" (vendored copy, sha256 `{schema_sha256}`)." if schema_sha256 else "."),
        "- **Proposed by:** "
        + (f"{author}." if author else "not recorded (who drafted this was not verified)."),
        f"- **Drafted:** {doc.get('proposed_at') or 'unknown'}. **ISAAC draft id:** `{doc.get('id')}`.",
        status_line,
        "",
        "## The change",
        "",
        "| | |",
        "|---|---|",
        *[f"| {label} | {_md_cell(str(value))} |" for label, value in rows],
        "",
        "### Definition",
        "",
        block(doc.get("description")),
        "",
        "## Gate 0: the proposal",
        "",
        "### The problem, with counts and examples",
        "",
        block(gate0.get("problem")),
        "",
        "### Examples",
        "",
        block(gate0.get("examples")),
        "",
        "### Records affected (estimate)",
        "",
        block(gate0.get("affected_records_estimate")),
        "",
        "### Flip list: what would change outcome or messages",
        "",
        block(gate0.get("flip_list")),
        "",
        "## Migration, version and rollback",
        "",
        block(change.get("migration")),
        "",
        "---",
        "",
        "The upstream process (`governance/README.md` in "
        f"{UPSTREAM_GOVERNANCE['repository']}) asks every change for a gate-0 proposal and every schema "
        "change for a migration plan, a version and a rollback. Unwritten sections above say so.",
        "",
    ]
    return {"markdown": "\n".join(lines), "document": document}
