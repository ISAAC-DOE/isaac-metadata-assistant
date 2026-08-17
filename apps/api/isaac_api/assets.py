"""Asset REFERENCES — the domain model behind the four asset operations.

WHAT AN ASSET REFERENCE IS, AND WHAT IT IS NOT
==============================================

An asset reference is metadata *about* a file: where it lives (``uri``), what role
it plays in the experiment (``content_role``), and the digest the scientist says
identifies it (``sha256``). **No bytes are involved anywhere in this module.**
Nothing here opens a file, fetches a URI, streams an upload, or computes a hash.
``POST /api/uploads`` remains an unconditional 403 and this feature does not change
that, does not depend on it, and adds no multipart parsing.

THE ONE RULE THAT MATTERS MOST: THE HASH IS NEVER COMPUTED
==========================================================

The scientist supplies the digest. This module validates its **shape** and nothing
else, and the distinction is not pedantic — it is the whole honesty boundary of the
feature. A 64-character lowercase hex string is a well-formed sha256; whether it is
*this file's* sha256 is a claim only something that read the file could make, and
nothing in ISAAC reads the file. Every surface that reports on a digest must
therefore say "recorded" or "well-formed", never "verified", "checked", or
"matched".

:func:`isaac_records.complete.is_sha256_shaped` is IMPORTED rather than restated.
That predicate is anchored ``\\A…\\Z`` *and* applied with ``fullmatch``, because a
``$``-anchored ``.match()`` accepted ``"9" * 64 + "\\n"`` — a measured, shipped
defect this repository keeps a whole module (``isaac_records.exactness``) about. A
second copy of the pattern here would be a second chance to get that wrong.

WHERE AN ASSET IS STORED, AND WHY IT IS STORED TWICE
====================================================

``workspace.RUN_LEVEL_BLOCKS`` classifies ``assets`` as **run-level**: an asset is a
run's own draft content, and it is NOT an inherited experiment-level address (so
``Experiment.set_run_override`` refuses it, correctly — there is nothing to
override). ``Experiment.resolved_run_draft`` therefore composes each run's export
draft from the RUN's own ``draft["assets"]``, and an experiment-level ``assets``
list reaches no run's exported record.

That leaves a real product problem: a scientist registers one file and wants three
runs to cite it. Two stores are involved and this module owns both:

* ``experiment.draft["assets"]`` — **the library**. The authored content, one entry
  per ``asset_id``. It is also exactly where the pre-existing blocker path
  (``isaac_records.complete.apply_answers``) puts an asset, and it is what a
  zero-run experiment exports today. Nothing about that changes.
* ``run.draft["assets"]`` — **the association**, materialised as a deep copy of the
  library entry. A run carries an entry iff the scientist associated it.

THE COPY IS MAINTAINED, NOT MERELY WRITTEN. Every write in this module rewrites
every run copy of the affected ``asset_id`` from the library inside the caller's
``record_lock``, and a removal drops it from every run. So the two stores cannot
drift: they are rewritten together, in one document, under one lock, in one save.

WHY NOT A SINGLE STORE PLUS EXPORT-TIME COMPOSITION, which is the obvious
alternative and was considered first. It would require teaching
``Experiment.resolved_run_draft`` a new key and a new merge layer — i.e. changing
what every run exports, what ``validate_draft`` sees, what the submission differ
compares, and what the evidence trail walks. The duplication costs a rewrite loop
this module already holds a lock for; the composition change costs a behavioural
edit to the export path for a feature that is supposed to add none. The cheaper
risk was chosen deliberately, and it is recorded here so a later slice that wants
the other shape knows this was a decision rather than an oversight.

WHAT IS DELIBERATELY NOT DONE
=============================

* **Nothing is auto-associated.** Adding a run does not give it the library's
  assets, and creating an asset on an experiment that has runs does not pick one
  for it. An association is a scientific statement about which measurement the file
  belongs to, and this application has no basis for making it.
* **No ``asset_id`` is invented.** The scientist names it. ``apply_answers`` derives
  one from ``content_role`` for a blocker it created itself; this module refuses a
  request that omits it rather than borrowing that rule, because two assets sharing
  an id silently collide in the evidence sidecar (``export.build_sidecar`` keys on
  ``assets:<asset_id>``) and the second one's evidence is lost.
* **No ``citation`` / ``caption_highlights`` sub-structure is defined.** The
  official schema declares both as bare ``{"type": "object"}``; the *description*
  names plausible keys ("authors, title, journal, year …") but a description is not
  a schema, and building a form from it would invent a vocabulary. They are
  accepted verbatim as objects and are not modelled.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache

from isaac_records.complete import is_sha256_shaped
from isaac_records.models import user_confirmation
from isaac_records.official import schema_path

from .workspace import REPO_ROOT

#: The draft/record block these entries live in, in BOTH stores. One constant so a
#: rename cannot leave the library and the run copies reading different keys.
ASSETS_BLOCK = "assets"

#: The draft-only key an asset carries that the official schema does not.
#: ``export.strip_evidence`` removes exactly this key on the way out, which is why
#: no OTHER extra key may ever be stored on an asset — see :func:`_schema_node`.
EVIDENCE_KEY = "evidence"


class UnsupportedAsset(ValueError):
    """A refusal the HTTP layer renders as a typed 422.

    Carries a machine-readable ``error`` code and any extra body keys the refusal
    needs to be actionable (the offending key, the allowed vocabulary). It exists so
    that every shape this module refuses reaches a client as a named 422 and never
    as a traceback: ``complete.py``'s type-guards were added because a wrong-typed
    structured answer used to escape the truth core as an HTTP 500, and a new write
    surface must not reopen that.
    """

    def __init__(self, error: str, message: str, **extra) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.extra = extra


# --- the schema is the vocabulary, and it is READ rather than retyped -----------


@lru_cache(maxsize=1)
def _schema_node() -> dict:
    """The official schema's ``assets.items`` subtree.

    READ FROM THE VENDORED SCHEMA, not transcribed. Every property name, every
    required flag and the twelve ``content_role`` values below come from
    ``schema/isaac_record_v1.json`` through the same ``schema_path`` resolver the
    official validator uses. A transcription would be a second definition of the
    asset shape, free to drift from the one export is validated against — and since
    the schema sets ``additionalProperties: false`` on this subtree, a drifted copy
    would not fail here, it would fail at export, after the write.

    Cached because it is read on every request and the file does not change under a
    running process; ``official.load_official_validator`` caches on the same
    reasoning.
    """
    schema = json.loads(schema_path(REPO_ROOT).read_text(encoding="utf-8"))
    node = (schema.get("properties") or {}).get(ASSETS_BLOCK) or {}
    items = node.get("items") or {}
    if not isinstance(items, dict) or not items.get("properties"):
        # A vendored schema that no longer describes assets is a truth-plane change,
        # not a user error. Refusing loudly at import-of-first-use is better than
        # silently accepting every key.
        raise RuntimeError(
            "the vendored official schema declares no assets[].properties; "
            "this feature cannot state what an asset may contain"
        )
    return items


def content_roles() -> tuple[str, ...]:
    """The twelve ``content_role`` values, in the schema's own order.

    Order is preserved rather than sorted: it is the order the schema's author
    wrote, it is stable across builds, and a client rendering a select gets the
    same list every time without this module imposing an opinion.
    """
    enum = ((_schema_node().get("properties") or {}).get("content_role") or {}).get("enum")
    return tuple(str(value) for value in (enum or []))


def asset_keys() -> tuple[str, ...]:
    """Every key an asset may carry, from the schema. ``evidence`` is not one."""
    return tuple((_schema_node().get("properties") or {}).keys())


def required_keys() -> tuple[str, ...]:
    """The four keys the schema requires: ``asset_id``, ``content_role``, ``uri``, ``sha256``."""
    return tuple(_schema_node().get("required") or ())


def _declared_types(key: str) -> tuple[str, ...]:
    """The JSON types the schema allows at one asset property.

    ``page`` is declared ``["number", "string"]``; everything else is a single
    string. Returned as a tuple either way so the caller has one shape to test.
    """
    spec = (_schema_node().get("properties") or {}).get(key) or {}
    declared = spec.get("type")
    if isinstance(declared, list):
        return tuple(str(t) for t in declared)
    return (str(declared),) if declared else ()


def _matches_type(value: object, declared: str) -> bool:
    """One JSON-Schema primitive type test, written so ``bool`` is not a number.

    ``isinstance(True, int)`` is True in Python, so a bare numeric check would
    accept ``true`` where the schema says ``number`` — the value would then be
    written, exported, and refused by the official validator with a message about a
    field the scientist never typed a boolean into. Booleans are excluded here so
    the refusal happens at the door.
    """
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "object":
        return isinstance(value, dict)
    if declared == "array":
        return isinstance(value, list)
    if declared == "boolean":
        return isinstance(value, bool)
    return False


def _check_declared_type(key: str, value: object) -> None:
    """Refuse a value whose JSON type the schema does not allow at ``key``.

    Also checks an array's ``items.type`` one level deep, which is the only nesting
    this subtree declares (``paper_conclusions_about_figure`` is an array of
    string). Nothing deeper is invented: ``citation`` and ``caption_highlights``
    declare no properties at all, so this refuses a non-object and then stops,
    rather than imposing a structure the schema does not state.
    """
    declared = _declared_types(key)
    if declared and not any(_matches_type(value, t) for t in declared):
        raise UnsupportedAsset(
            "invalid_asset_field",
            (
                f"`{key}` must be {' or '.join(declared)} — that is what the official "
                "ISAAC schema declares for it. Nothing was written, and the value was "
                "not converted: a coerced value is a value the scientist did not enter."
            ),
            key=key,
            expected=list(declared),
        )
    if "array" in declared and isinstance(value, list):
        item_type = (
            ((_schema_node().get("properties") or {}).get(key) or {}).get("items") or {}
        ).get("type")
        if isinstance(item_type, str):
            for index, element in enumerate(value):
                if not _matches_type(element, item_type):
                    raise UnsupportedAsset(
                        "invalid_asset_field",
                        (
                            f"every entry of `{key}` must be {item_type}; entry "
                            f"{index} is not. Nothing was written."
                        ),
                        key=key,
                        expected=[item_type],
                    )


# --- building one asset entry ---------------------------------------------------


def _require_text(key: str, value: object) -> str:
    """A required non-blank string, refused rather than defaulted.

    Blank is refused for both required text keys for the same reason: an
    ``asset_id`` of ``"   "`` is unaddressable by every route below, and a ``uri``
    of ``""`` records that a file exists somewhere unstated, which is a claim with
    no content.
    """
    if not isinstance(value, str) or not value.strip():
        raise UnsupportedAsset(
            f"invalid_{key}",
            (
                f"`{key}` must be a non-blank string. It is not filled in on your "
                "behalf and it is not guessed from the other fields."
            ),
            key=key,
        )
    return value.strip()


def build_asset(
    body: dict,
    *,
    existing: dict | None = None,
    timestamp: str,
    question: str,
) -> dict:
    """One asset entry, validated against the schema's own declarations.

    ``existing`` is the entry being edited; when it is supplied, a key absent from
    ``body`` KEEPS its current value and is not cleared. Clearing an optional key is
    an explicit ``null``, which removes it — a stored ``null`` would export as
    ``"media_type": null`` and fail the official schema, which declares the property
    ``{"type": "string"}``.

    The evidence list is APPENDED to, never replaced. Evidence is the record of what
    a person actually confirmed, and an edit that discarded the original
    confirmation would rewrite history rather than extend it.

    THE CALLER OWNS UNIQUENESS. This function does not see the library, so it cannot
    check that ``asset_id`` is free; :func:`upsert` does that, because that is where
    the library is in hand.
    """
    if not isinstance(body, dict):
        raise UnsupportedAsset("invalid_body", "The request body must be a JSON object.")

    # REFUSED WHOLE, BEFORE ANYTHING ELSE IS LOOKED AT. A request naming one key this
    # object may not carry is rejected in full, so a caller is never left wondering
    # which half of its body was honoured — the same ordering `post_note` uses.
    allowed = set(asset_keys())
    unknown = sorted(str(k) for k in body if k not in allowed and k not in _NON_ASSET_BODY_KEYS)
    if unknown:
        raise UnsupportedAsset(
            "unrecognized_field",
            (
                "These keys are not part of an ISAAC asset. The official schema closes "
                "this object (`additionalProperties: false`), so storing one would make "
                "the record unexportable. `evidence` is not accepted either: it records "
                "what a person confirmed and is written by the server, never by a "
                "request. Nothing was written."
            ),
            key=unknown[0],
            keys=unknown,
        )

    entry: dict = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    changed: list[str] = []

    for key in asset_keys():
        if key not in body:
            continue
        value = body[key]
        if value is None:
            if key in required_keys():
                raise UnsupportedAsset(
                    f"invalid_{key}",
                    (
                        f"`{key}` is required by the official ISAAC schema and cannot "
                        "be cleared. Remove the whole asset reference instead."
                    ),
                    key=key,
                )
            if key in entry:
                del entry[key]
                changed.append(key)
            continue
        if key in ("asset_id", "uri"):
            value = _require_text(key, value)
        elif key == "sha256":
            value = _require_sha256(value)
        elif key == "content_role":
            value = _require_content_role(value)
        else:
            _check_declared_type(key, value)
            if isinstance(value, str) and not value.strip():
                # A blank optional string is ABSENCE, expressed awkwardly. Storing it
                # would put an empty caption or an empty media type into an exported
                # record, which asserts that the field was answered.
                raise UnsupportedAsset(
                    "invalid_asset_field",
                    (
                        f"`{key}` was sent as a blank string. Omit it, or send `null` "
                        "to clear it — a blank value would be exported as though it "
                        "had been answered. Nothing was written."
                    ),
                    key=key,
                )
        if entry.get(key) != value:
            changed.append(key)
        entry[key] = value

    missing = [key for key in required_keys() if key not in entry]
    if missing:
        raise UnsupportedAsset(
            f"invalid_{missing[0]}",
            (
                f"`{missing[0]}` is required by the official ISAAC schema and was not "
                "supplied. It is never invented, and no default stands in for it."
            ),
            key=missing[0],
            keys=missing,
        )

    if changed:
        history = list(entry.get(EVIDENCE_KEY) or [])
        history.append(
            user_confirmation(
                question,
                _confirmed_answer(entry, changed),
                timestamp,
            )
        )
        entry[EVIDENCE_KEY] = history
    return entry


#: Body keys that are part of the REQUEST but not part of an asset. Listed so
#: :func:`build_asset` can refuse everything else by name instead of ignoring it.
_NON_ASSET_BODY_KEYS = frozenset({"confirmed_by_user", "run_ids"})


def _confirmed_answer(entry: dict, changed: list[str]) -> str:
    """What the evidence entry records the person as having confirmed.

    A DETERMINISTIC RENDERING OF THE VALUES THEY SUPPLIED, and nothing more. It
    names the keys that moved and their new values, sorted, so re-confirming the
    same content produces the same string — which is what lets an unchanged write
    stay a byte-stable no-op rather than churning the record's revision.

    It composes no interpretation. There is no "verified", no "matches", and no
    statement about the file at the URI, because this application has not looked at
    it.
    """
    return json.dumps(
        {key: entry.get(key) for key in sorted(set(changed))},
        sort_keys=True,
        ensure_ascii=False,
    )


def _require_sha256(value: object) -> str:
    """The digest, refused unless it is exactly 64 lowercase hex characters.

    ``is_sha256_shaped`` is the truth path's own predicate — ``\\A[0-9a-f]{64}\\Z``
    applied with ``fullmatch`` — imported rather than restated. It refuses
    uppercase, 63 and 65 characters, non-hex, and (the case this repository shipped
    a defect on) a well-formed digest with a trailing newline.

    NOTHING IS TRIMMED FIRST, deliberately. ``.strip()`` here would accept
    ``"<64 hex>\\n"`` by quietly repairing it, which is the same "helpful" coercion
    the anchoring exists to prevent — and the scientist would never learn that what
    they pasted was not what was stored.
    """
    if not is_sha256_shaped(value):
        raise UnsupportedAsset(
            "invalid_sha256",
            (
                "`sha256` must be exactly 64 lowercase hexadecimal characters, with "
                "nothing before or after — not even a trailing newline. It is never "
                "computed, completed, trimmed or corrected here: this application does "
                "not read the file at the URI, so the digest can only be the one you "
                "supply. Nothing was written."
            ),
            key="sha256",
        )
    return str(value)


def _require_content_role(value: object) -> str:
    """The role, refused unless it is one of the schema's twelve enum values."""
    roles = content_roles()
    if not isinstance(value, str) or value not in roles:
        raise UnsupportedAsset(
            "invalid_content_role",
            (
                "`content_role` must be one of the values the official ISAAC schema "
                "enumerates. It is not inferred from the URI, the file extension or "
                "the media type — which role a file plays in an experiment is a "
                "scientific statement, not a naming convention. Nothing was written."
            ),
            key="content_role",
            allowed=list(roles),
        )
    return value


# --- the library, and the run copies that mirror it -----------------------------


def library(draft: object) -> list[dict]:
    """The experiment's asset library — every readable entry, in stored order.

    A container that is not a list, and an element that is not a dict, are SKIPPED
    rather than raised on: a persisted document is untrusted input and one malformed
    entry must not take out the whole surface. :func:`unreadable_count` reports how
    many were skipped so the omission is disclosed rather than silent.
    """
    if not isinstance(draft, dict):
        return []
    stored = draft.get(ASSETS_BLOCK)
    if not isinstance(stored, list):
        return []
    return [item for item in stored if isinstance(item, dict) and item.get("asset_id")]


def unreadable_count(draft: object) -> int:
    """How many stored asset entries this build cannot present, in ONE draft.

    Counts two kinds without separating them, exactly as the notes feature counts
    its own: an element that is not an object, and an object carrying no
    ``asset_id`` (which is unaddressable — no route below could name it). Both are
    left in the document untouched.

    Callers wanting the figure a READER should be shown want
    :func:`unreadable_count_everywhere`, not this. See its docstring for why.
    """
    if not isinstance(draft, dict):
        return 0
    stored = draft.get(ASSETS_BLOCK)
    if not isinstance(stored, list):
        # A non-list container is ONE thing this build cannot read, not N.
        return 1 if stored is not None else 0
    return sum(
        1 for item in stored if not isinstance(item, dict) or not item.get("asset_id")
    )


def unreadable_count_everywhere(exp) -> int:
    """The same count over the library AND every run draft.

    THE DISCLOSURE HAS TO COVER THE SAME GROUND THE REFUSAL DOES, and the first
    version of this feature did not. The listing reported
    ``unreadable_count(exp.draft)`` — the library only — while
    :func:`refuse_unreadable_containers` checks the experiment *and every run*.

    So a record whose RUN held a non-list ``assets`` container read as perfectly
    clean (``unreadable_entries: 0``, no warning anywhere on the panel), and then
    every write refused with 422 ``unreadable_asset_container`` naming that run.
    A refusal a reader was given no prior disclosure of is the shape of surprise
    this project's honesty rules exist to prevent: the panel was not lying about
    a value, it was quietly reporting on a narrower scope than the one it acted
    on.

    Counting both is the fix rather than narrowing the refusal, because the
    refusal is right: a run container this build cannot read is a real reason to
    decline to write.
    """
    total = unreadable_count(getattr(exp, "draft", None))
    for run in exp.sorted_runs():
        total += unreadable_count(getattr(run, "draft", None))
    return total


def refuse_unreadable_containers(exp) -> None:
    """Refuse to WRITE when a stored ``assets`` container is not a list.

    THIS EXISTS BECAUSE THE DISCLOSURE WOULD OTHERWISE BE A LIE. Every read surface
    says an entry this build cannot present is "kept unchanged on the record", and
    :func:`library` skips a malformed container by returning an empty list — so
    without this guard, the first write would have replaced ``{"assets": {"a": 1}}``
    with a fresh list and silently destroyed whatever was there. A container that is
    not a list has no positions to preserve entries at, so there is no way to write
    around it; the only honest options are to destroy it or to refuse, and refusing
    is the one that matches what every surface promises.

    A per-ELEMENT problem is different and is NOT refused: those have positions,
    :func:`_write_library` carries them through untouched, and they are counted by
    :func:`unreadable_count`. Only the container itself is fatal.

    Checked on the experiment AND on every run, because a write touches both.
    """
    draft = exp.draft if isinstance(exp.draft, dict) else {}
    candidates: list[tuple[str, object]] = [("record", draft.get(ASSETS_BLOCK))]
    for run in exp.sorted_runs():
        run_draft = run.draft if isinstance(run.draft, dict) else {}
        candidates.append((f"run {run.id}", run_draft.get(ASSETS_BLOCK)))
    for where, stored in candidates:
        if stored is not None and not isinstance(stored, list):
            raise UnsupportedAsset(
                "unreadable_asset_container",
                (
                    f"The stored asset list on {where} is not a list, so this server "
                    "cannot add to it or remove from it without discarding whatever "
                    "it holds. Nothing was written, and nothing was changed — the "
                    "stored content is left exactly as it is."
                ),
                where=where,
            )


def find(draft: object, asset_id: str) -> dict | None:
    """The library entry with this id, or ``None``."""
    for entry in library(draft):
        if entry.get("asset_id") == asset_id:
            return entry
    return None


def _write_library(draft: dict, entries: list[dict]) -> None:
    """Replace the library, PRESERVING every entry this build could not read.

    The unreadable ones are carried through in their original positions relative to
    each other rather than dropped. This module refuses to present them; deleting
    them because of that would be the silent data loss the disclosure exists to
    avoid.
    """
    stored = draft.get(ASSETS_BLOCK)
    preserved = (
        [
            item
            for item in stored
            if not isinstance(item, dict) or not item.get("asset_id")
        ]
        if isinstance(stored, list)
        else []
    )
    draft[ASSETS_BLOCK] = list(entries) + preserved


def upsert(exp, entry: dict, *, creating: bool) -> None:
    """Write one asset into the library — appending on create, replacing on edit.

    ``creating`` refuses a duplicate ``asset_id``. Uniqueness is not cosmetic: the
    evidence sidecar is keyed ``assets:<asset_id>`` (``export.build_sidecar``), so
    two entries sharing an id publish one evidence list and lose the other's —
    silently, in an exported artifact, which is the worst place for it.

    THERE IS NO RENAME, AND THAT IS A DECISION RATHER THAN AN OMISSION. The id is
    the address in the URL, the key of every run's copy, and the key of the sidecar
    entry; changing it would have to move all three atomically, and a half-moved
    rename is exactly the drift the single-write-under-one-lock rule exists to
    prevent. An edit that supplies a different ``asset_id`` is refused by the route
    before this is reached.
    """
    draft = exp.draft if isinstance(exp.draft, dict) else {}
    exp.draft = draft
    asset_id = entry["asset_id"]
    entries = library(draft)
    if creating and any(item.get("asset_id") == asset_id for item in entries):
        raise UnsupportedAsset(
            "duplicate_asset_id",
            (
                f"This record already has an asset reference called {asset_id!r}. Ids "
                "must be unique: the evidence sidecar is keyed by them, so two "
                "entries sharing one id would publish a single evidence list and lose "
                "the other. Nothing was written."
            ),
            key="asset_id",
        )
    replaced = False
    out: list[dict] = []
    for item in entries:
        if item.get("asset_id") == asset_id:
            out.append(entry)
            replaced = True
        else:
            out.append(item)
    if not replaced:
        out.append(entry)
    _write_library(draft, out)


def remove(exp, asset_id: str) -> bool:
    """Drop one asset from the library. Returns whether anything was dropped."""
    draft = exp.draft if isinstance(exp.draft, dict) else {}
    exp.draft = draft
    entries = library(draft)
    kept = [item for item in entries if item.get("asset_id") != asset_id]
    if len(kept) == len(entries):
        return False
    _write_library(draft, kept)
    return True


def run_assets(run) -> list[dict]:
    """One run's own asset list — its associations. Malformed entries skipped."""
    draft = run.draft if isinstance(run.draft, dict) else {}
    stored = draft.get(ASSETS_BLOCK)
    if not isinstance(stored, list):
        return []
    return [item for item in stored if isinstance(item, dict) and item.get("asset_id")]


def associated_run_ids(exp, asset_id: str) -> list[str]:
    """Every run of this experiment that carries this asset, in run order."""
    return [
        run.id
        for run in exp.sorted_runs()
        if any(item.get("asset_id") == asset_id for item in run_assets(run))
    ]


def set_associations(exp, entry: dict, run_ids: set[str] | None) -> None:
    """Materialise one asset onto exactly the named runs, and off every other.

    ``run_ids is None`` means "leave the associations alone" — but the entry itself
    may have changed, so every run that already carries it is REWRITTEN from the
    library copy. That rewrite is what makes the two stores one fact rather than
    two: an edit can never leave a run holding a stale digest.

    ``run_ids`` given (including the empty set) SETS the membership exactly. Whole-set
    semantics rather than add/remove, because a scientist looking at a list of
    checkboxes is stating which runs use the file, and an add-only API would make
    "none of them" unreachable.

    A DEEP COPY PER RUN. Sharing one dict between the library and N runs would make
    the document's JSON serialisation correct and its in-memory aliasing a trap: a
    later mutation of one would silently move all of them.

    AN EXISTING ASSOCIATION KEEPS ITS POSITION; only a NEW one is appended. The
    first version of this function filtered the entry out and re-appended it
    unconditionally, so every write reordered the run's ``assets`` array —
    including a write that changed nothing.

    That was not cosmetic, and independent review proved it by running it. Three
    consequences, in increasing order of seriousness:

      * ``upsert`` replaces IN PLACE in the library, so the two stores disagreed
        about order after the very first edit — two copies of one fact that are
        not byte-equal;
      * the reordered array is the one that goes into that run's exported ISAAC
        record;
      * ``_run_signature_payload`` includes ``run.draft``, so the reorder advanced
        the experiment's ``rev``. A second client holding the pre-click ETag then
        got a **412 manufactured by a no-op** — a stale-write refusal with no
        stale write behind it, which is precisely the signal ``_check_if_match``
        exists to keep meaningful.

    It also contradicted this feature's own shipped contract, which states that
    "a request that changes nothing is a no-op that does not advance the record's
    revision".

    It was invisible to the suite because the no-op test used a ZERO-RUN
    experiment holding ONE asset, and the reorder needs a run holding at least
    two. ``test_a_no_op_edit_does_not_reorder_a_runs_assets`` closes that gap.
    """
    asset_id = entry["asset_id"]
    for run in exp.sorted_runs():
        draft = run.draft if isinstance(run.draft, dict) else {}
        run.draft = draft
        stored = draft.get(ASSETS_BLOCK)
        current = stored if isinstance(stored, list) else []
        holds = any(
            isinstance(item, dict) and item.get("asset_id") == asset_id
            for item in current
        )
        wanted = holds if run_ids is None else run.id in run_ids
        rebuilt: list = []
        placed = False
        for item in current:
            if isinstance(item, dict) and item.get("asset_id") == asset_id:
                # Replace the FIRST occurrence in place and drop any later
                # duplicate — matching `upsert`'s in-place behaviour rather than
                # inventing a second ordering rule for the same fact.
                if wanted and not placed:
                    rebuilt.append(copy.deepcopy(entry))
                    placed = True
                continue
            rebuilt.append(item)
        if wanted and not placed:
            # A genuinely NEW association. Appending is the only defensible
            # position: there is no prior slot to preserve.
            rebuilt.append(copy.deepcopy(entry))
        if rebuilt or ASSETS_BLOCK in draft:
            draft[ASSETS_BLOCK] = rebuilt


def detach_everywhere(exp, asset_id: str) -> None:
    """Remove one asset from every run. Used only by the removal operation."""
    for run in exp.sorted_runs():
        draft = run.draft if isinstance(run.draft, dict) else {}
        run.draft = draft
        stored = draft.get(ASSETS_BLOCK)
        if not isinstance(stored, list):
            continue
        draft[ASSETS_BLOCK] = [
            item
            for item in stored
            if not (isinstance(item, dict) and item.get("asset_id") == asset_id)
        ]


def export_reach(exp, asset_id: str) -> str:
    """WHERE this asset actually reaches an exported record. A fact, not advice.

    Three answers, and the third is the one that has to exist:

    * ``record`` — this experiment has no runs, so it exports one record from its own
      draft and this asset is part of it.
    * ``runs`` — it is associated with at least one run, and each of those runs
      exports a record carrying it.
    * ``none`` — this experiment HAS runs, and this asset is associated with none of
      them, so no exported record will carry it. ``Experiment.resolved_run_draft``
      composes a run's export draft from the run's own blocks, and ``assets`` is
      run-level, so an unassociated library entry is genuinely invisible to export.
      Saying so plainly is the point: the alternative is a scientist who recorded a
      file, saw it listed, and never learns it was left out.
    """
    if associated_run_ids(exp, asset_id):
        return "runs"
    return "none" if exp.sorted_runs() else "record"
