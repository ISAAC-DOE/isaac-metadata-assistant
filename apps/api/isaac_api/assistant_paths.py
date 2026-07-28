"""P36V.1 Unit B — DISPLAY-ONLY humanization of validation/blocker locations.

The Python half of a two-implementation, one-behaviour pair. The TypeScript half is
``apps/web/src/lib/assistantPaths.ts``; that module's header carries the full
rationale. In brief:

The deterministic truth core renders a root-level JSON Schema violation as the
literal string ``$``::

    src/isaac_records/official.py:71
        path=".".join(str(p) for p in err.absolute_path) or "$",

For a root-level violation (a missing required TOP-LEVEL property, a root type
error, a root ``additionalProperties`` error) ``err.absolute_path`` is an empty
deque, so the join yields ``""`` and the ``or "$"`` fallback substitutes the
literal. That is a correct JSONPath locator and it is NOT changed here —
``official.py`` is truth core and is not edited. What IS changed is the Assistant's
presentation of it: echoing ``$`` into "1 path is listed as blocking export: $."
named nothing a reader could act on.

This module changes NO validator semantics, NO blocker semantics and NO validation
result. It maps an already-computed locator to (a) a human-facing location phrase
and (b) the EXACT locator, preserved byte-for-byte for a ``Technical Details``
disclosure.

Cross-language equivalence
--------------------------
Literal code sharing across Python and TypeScript is impossible, so the two
implementations are locked together by ONE shared case table —
``apps/web/src/test/validation-path-cases.json`` — replayed by BOTH suites
(``apps/api/tests/test_assistant_paths.py`` and
``apps/web/src/lib/assistantPaths.test.ts``). A change to one implementation that
is not mirrored in the other fails the other language's suite.

The claim that equivalence buys is BOUNDED, and the bound is stated rather than
implied (P36V.1 review, M1): the two implementations agree on every input in the
shared table and in each suite's adversarial corpus — dot-joined JSON locators,
root markers, and degenerate/absent values. They are NOT claimed equal over
arbitrary Unicode: ``str.strip()`` and ``String.prototype.trim()`` have different
whitespace sets (Python strips ``\\x1c``–``\\x1f`` and ``\\x85``; JavaScript strips
``\\ufeff`` — neither strips the other's). The characters the reviewer measured
diverging on are removed explicitly by :data:`_INVISIBLE_RE` in BOTH
implementations so those inputs now agree; some other exotic code point may still
resolve differently in the two runtimes. The deterministic validator emits only
``$`` or a dot-join of schema property names and array indices, so no reachable
locator depends on the difference.

Injectivity is likewise bounded (M2). The mapping is injective over dot-joined
locators whose segments contain neither ``.`` nor the rendered separator
``" → "`` — which is every locator ``official.py`` can emit. It is NOT injective
in general: ``{"$", "$.", "$..", "$ "}`` all render as
:data:`RECORD_LEVEL_LABEL`, and ``{"a → b", "a.b", "a..b"}`` all render as
``a → b``. Every such collision either denotes the SAME JSON location or requires
a segment containing the separator glyph, so no collision can misdescribe a
location — but the property is stated as it holds, not as a blanket guarantee.

Isolation: standard library only. It imports no ``isaac_records``, no ``graphify``,
no ``fastapi`` and no sibling ``isaac_api`` module, does no I/O, and computes no
verdict.
"""

from __future__ import annotations

import re
from typing import Optional

#: The phrase that replaces the raw root locator ``$`` in user-facing copy.
RECORD_LEVEL_LABEL = "the record itself"

#: The phrase used when a blocker carries no usable location at all.
UNKNOWN_LOCATION_LABEL = "an unreported location"

#: The ``Technical Details`` stand-in when no locator string was reported.
NO_PATH_TECHNICAL = "(no path reported)"

#: Rendered between locator segments in a humanized label.
SEGMENT_SEPARATOR = " → "

#: The honest empty answer, shared verbatim with the TypeScript producer.
NO_BLOCKING_ISSUES = (
    "No blocking validation issues are listed in the current validation response."
)

#: The literal root locator the deterministic validator emits for a root-level
#: violation (``src/isaac_records/official.py:71``: an empty ``absolute_path``
#: joins to ``""`` and the ``or "$"`` fallback substitutes this).
ROOT_MARKER = "$"

#: The FIXED message the API emits when the validation dry-run ITSELF failed to
#: run — ``apps/api/isaac_api/routes.py`` ``post_validate`` and
#: ``_assistant_validate_dryrun`` both return
#: ``[{"path": "$", "message": "Validation could not be completed."}]`` from their
#: defensive ``except``. That list is a CRASH SENTINEL, not a validation finding:
#: no schema violation was located, so describing it as "1 record-level validation
#: issue" would state something the validator never reported (``CLAUDE.md`` §3/§5).
#: Neither producer is changed — this constant is how a READER of the response
#: tells the sentinel apart, and ``test_assistant_paths.py`` asserts the literal
#: still appears in ``routes.py`` so the two can never drift apart silently.
VALIDATION_UNAVAILABLE_MESSAGE = "Validation could not be completed."

#: The honest sentence for that case, shared verbatim with the TypeScript producer.
#: It claims NO location, states NO count of issues, and states no verdict.
VALIDATION_UNAVAILABLE_SUMMARY = (
    "The deterministic schema check could not be completed for this record, so no "
    "blocking locations can be listed."
)

#: Location kinds.
RECORD = "record"
FIELD = "field"
UNKNOWN = "unknown"

#: Invisible characters the two runtimes' trim primitives disagree about: Python's
#: ``str.strip()`` removes ``\x1c``–``\x1f`` and ``\x85`` but not the BOM
#: ``\ufeff``; JavaScript's ``trim()`` does the opposite (it strips the BOM and
#: leaves the C1/separator controls). Removing this explicit set FIRST, in
#: both implementations, keeps them in agreement on those inputs and stops an
#: all-invisible "locator" from being rendered as a location label that a reader
#: sees as blank (P36V.1 review, M1). The exact reported string is still preserved
#: byte-for-byte in ``technical``; only the LABEL derivation is affected.
_INVISIBLE_RE = re.compile("[\ufeff\x1c\x1d\x1e\x1f\x85]")


def _trim(value: str) -> str:
    """Trim, with the cross-runtime invisible set removed first."""
    return _INVISIBLE_RE.sub("", value).strip()


def count(n: int, singular: str, plural: Optional[str] = None) -> str:
    """Deterministic pluralization: ``1 field`` / ``2 fields``. No ``field(s)``
    placeholder ever survives to rendered output."""
    word = singular if n == 1 else (plural or f"{singular}s")
    return f"{n} {word}"


def join_capped(items: list) -> str:
    """Join the first <=3 items with ``", "``; append ``", …and K more"``."""
    shown = items[:3]
    rest = len(items) - len(shown)
    base = ", ".join(shown)
    return f"{base}, …and {rest} more" if rest > 0 else base


def classify_validation_path(raw) -> dict:
    """Classify ONE reported locator into ``{kind, label, technical}``.

    Total: never raises, whatever it is handed (``None``, a non-string, an empty
    or whitespace-only value all resolve to the honest ``unknown`` location)."""
    reported = raw if isinstance(raw, str) else ""
    trimmed = _trim(reported)
    # Nothing usable was reported. Honest: no location is claimed, none invented.
    if trimmed == "":
        return {
            "kind": UNKNOWN,
            "label": UNKNOWN_LOCATION_LABEL,
            "technical": NO_PATH_TECHNICAL,
        }

    technical = reported
    root_marked = trimmed.startswith(ROOT_MARKER)
    body = trimmed[1:] if root_marked else trimmed
    if body.startswith("."):
        body = body[1:]
    body = _trim(body)

    segments = [_trim(s) for s in body.split(".")]
    segments = [s for s in segments if s != ""]

    if not segments:
        # A bare root marker (``$``, ``$.``) — the case that produced the reported
        # defect. It is a RECORD-level location, not a field.
        if root_marked:
            return {"kind": RECORD, "label": RECORD_LEVEL_LABEL, "technical": technical}
        # A reported-but-unusable locator (e.g. ``"."``): keep the exact string for
        # the disclosure, but claim no location.
        return {
            "kind": UNKNOWN,
            "label": UNKNOWN_LOCATION_LABEL,
            "technical": technical,
        }

    if any(ROOT_MARKER in s for s in segments):
        # A ``$`` that survived INSIDE a segment rather than as the leading root
        # marker (``$$``, ``a.$.b``, ``assets.$``, ``$$$``). Only the LEADING marker
        # is stripped above, so this used to be emitted verbatim into the primary
        # label — "1 validation issue may be blocking export: assets → $." — which
        # is exactly the raw-locator defect this module exists to prevent, and it
        # falsified this module's own documented invariant (P36V.1 review, M2).
        # The honest answer is that no location can be named: the exact string is
        # still preserved for the disclosure. Rejecting the whole GLYPH (not just a
        # ``$``-only segment) is what makes ``"$" not in label`` hold universally, and
        # it downgrades nothing reachable: every locator ``official.py`` emits is
        # ``$`` itself or a dot-join of ISAAC-schema property names and array indices,
        # and NO property name in ``schema/isaac_record_v1.json`` contains ``$`` or
        # ``.`` (all 219 checked).
        return {
            "kind": UNKNOWN,
            "label": UNKNOWN_LOCATION_LABEL,
            "technical": technical,
        }

    return {
        "kind": FIELD,
        "label": SEGMENT_SEPARATOR.join(segments),
        "technical": technical,
    }


def is_validation_unavailable(errors) -> bool:
    """True iff ``errors`` is the API's validation-CRASH sentinel rather than a list
    of validation findings.

    The sentinel is ``[{"path": "$", "message": "Validation could not be
    completed."}]`` — emitted by ``routes.py`` when the deterministic dry-run raised.
    Read through the locator formatter alone it is indistinguishable from a genuine
    root-level violation, and the humanized copy would then tell the reader "1
    record-level validation issue may be blocking export" when NO issue was found.

    Detection keys on the MESSAGE, not the path: the message is the distinguishing
    field (the ``$`` path is incidental, and a real root-level violation carries a
    ``jsonschema`` message). Whitespace-tolerant, and total for any shape. Returns
    False for an empty list, so "no errors" stays the honest empty answer."""
    if not isinstance(errors, list) or not errors:
        return False
    for err in errors:
        message = err.get("message") if isinstance(err, dict) else None
        if not isinstance(message, str):
            return False
        if _trim(message) != VALIDATION_UNAVAILABLE_MESSAGE:
            return False
    return True


def classify_validation_paths(raws) -> list:
    """Classify every reported locator, order preserved (never deduplicated)."""
    return [classify_validation_path(r) for r in (raws or [])]


def technical_paths(raws) -> list:
    """The EXACT technical locators, order preserved — the ``Technical Details``
    payload. This is the ONLY place a raw ``$`` is allowed to surface."""
    return [loc["technical"] for loc in classify_validation_paths(raws)]


def blocking_summary(raws) -> str:
    """The primary, user-facing blocker sentence.

    * no locators           -> :data:`NO_BLOCKING_ISSUES`
    * every locator is root -> ``N record-level validation issues may be blocking export.``
    * otherwise             -> ``N validation issues may be blocking export: <=3 locations.``

    It states a COUNT and WHERE — never a validity conclusion, never ``ok``, and
    never a bare ``$``."""
    locations = classify_validation_paths(raws)
    if not locations:
        return NO_BLOCKING_ISSUES
    if all(loc["kind"] == RECORD for loc in locations):
        return (
            f"{count(len(locations), 'record-level validation issue')} "
            "may be blocking export."
        )
    labels = join_capped([loc["label"] for loc in locations])
    return f"{count(len(locations), 'validation issue')} may be blocking export: {labels}."
