"""P34.1 — a PURE, deterministic, READ-ONLY free-form question resolver.

This module is the backend analogue of the frontend grounded composer
(``apps/web/src/lib/assistantComposer.ts``): it turns a free-form user question
into a short, source-labeled, verdict-guarded reply grounded ENTIRELY in state
the route already fetched. It is subordinate and advisory — it NEVER states a
PASS/FAIL or a valid/invalid conclusion, never mutates a record, never guesses a
scientific value, and never authorizes an export.

Truth isolation (mirrors ``memory.py``)
--------------------------------------
Imports the standard library plus ONE sibling, presentation-only, stdlib-only
module: :mod:`isaac_api.assistant_paths` (the display formatter for validation
locators, mirrored in TypeScript). It never imports ``isaac_records``, never
imports ``graphify``, never imports ``fastapi``, computes no verdict, and takes no
filesystem/network action. Both facts are asserted by
``apps/api/tests/test_assistant_paths.py``. Everything it needs is passed in via
:class:`AssistantContext` — a
read-only bundle the route assembles (with expensive grounding supplied as
thunks invoked only for the matched intent). This keeps :func:`classify` pure and
unit-testable without a workspace, and keeps :func:`answer` a deterministic
function of its inputs.

Determinism
-----------
The SAME normalized question + SAME record state + SAME revision produce
byte-identical output. (:data:`RESOLVER_VERSION` is NOT part of that — it is a
documentation-only constant with no consumer anywhere in the repo, so it keys
nothing at runtime; see its own comment.) Classification is an
explicit finite catalog of alias/phrase triggers matched by plain
string-containment (NO probabilistic scoring, NO ML, NO fuzzy classifier); an
explicit precedence order breaks specific ties; genuine ties between distinct
intents resolve to ``ambiguous``; an unmatched/open-world question resolves to
``unsupported`` — never guessed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .assistant_paths import (
    NO_BLOCKING_ISSUES,
    VALIDATION_UNAVAILABLE_SUMMARY,
    blocking_summary,
    count as _count,
    is_validation_unavailable,
    join_capped as _join_capped,
    technical_paths,
)

# Bump when the classification catalog, answer templates, or guards change so a
# cached/grounded answer computed under an older resolver is detectably distinct.
# P36V.1 Unit B changed the blocker answer TEMPLATE (locator humanization) and the
# validate affordance, so this is bumped per its own contract. NOTE, honestly: this
# constant currently has no consumer anywhere in the repo — bumping it documents the
# template change but detects nothing at runtime.
RESOLVER_VERSION = "p36v.1"

_log = logging.getLogger("isaac_api.assistant_query")


# --- intent catalog -----------------------------------------------------------

PENDING_FIELDS = "pending_fields"
EXPORT_BLOCKERS = "export_blockers"
EXPORT_READINESS = "export_readiness"
WORKFLOW_STEP = "workflow_step"
FIELD_PROVENANCE = "field_provenance"
EVIDENCE_SUMMARY = "evidence_summary"
RECORD_SUMMARY = "record_summary"
MEMORY_LEAD = "memory_lead"

UNSUPPORTED = "unsupported"
AMBIGUOUS = "ambiguous"

#: Trigger phrases per intent. Matched by plain lowercase substring containment
#: against the normalized question. Score = count of DISTINCT phrases matched.
#: Kept explicit and finite — never a learned/scored classifier.
_TRIGGERS: dict[str, tuple[str, ...]] = {
    PENDING_FIELDS: (
        "needs attention", "still needs me", "still need me", "what still needs",
        "whats missing", "what's missing", "what is missing", "missing field",
        "missing fields", "pending", "incomplete field", "incomplete fields",
        "review next", "what should i review", "next field", "still need",
    ),
    EXPORT_BLOCKERS: (
        "can't i export", "cant i export", "cannot i export", "can i not export",
        "why can't", "why cant", "whats blocking", "what's blocking",
        "what is blocking", "blocking export", "blocking", "before export",
        "whats left", "what's left", "what is left", "not ready to export",
        "left before export",
    ),
    EXPORT_READINESS: (
        "ready to export", "export readiness", "readiness", "coverage",
        "am i done", "is this ready", "is it ready",
    ),
    WORKFLOW_STEP: (
        "current step", "explain the workflow", "the workflow", "where am i",
        "what step", "which step", "next step", "workflow",
    ),
    FIELD_PROVENANCE: (
        "where did", "where does", "come from", "came from", "provenance of",
        "provenance", "trace", "source of",
    ),
    EVIDENCE_SUMMARY: (
        "summarize the evidence", "summarise the evidence", "the evidence for",
        "evidence for", "whats the evidence", "what's the evidence",
        "what is the evidence", "multiple evidence", "evidence entries",
        "why multiple",
    ),
    RECORD_SUMMARY: (
        "summarize this record", "summarise this record", "what is this record",
        "this record", "record status", "record summary", "overview",
        "summarize the record", "summarise the record",
    ),
    MEMORY_LEAD: (
        "project memory", "does project memory", "memory know about",
        "docs about", "documentation about", "where is", "defined", "concept",
    ),
}

#: General/catch-all intents that YIELD to any specific intent on a score tie.
_GENERAL_INTENTS = frozenset({RECORD_SUMMARY})

#: The one specific precedence relationship (spec §1): a blocker/negation-cued
#: export question outranks a plain export-readiness question.
_EXPORT_PAIR = frozenset({EXPORT_BLOCKERS, EXPORT_READINESS})

#: Intents that carry an extracted field/topic token.
_FIELD_INTENTS = frozenset({FIELD_PROVENANCE, EVIDENCE_SUMMARY})

#: Stable display order for alternatives / catalog listing.
_INTENT_ORDER = (
    PENDING_FIELDS, EXPORT_BLOCKERS, EXPORT_READINESS, WORKFLOW_STEP,
    FIELD_PROVENANCE, EVIDENCE_SUMMARY, RECORD_SUMMARY, MEMORY_LEAD,
)


@dataclass(frozen=True)
class ClassifiedIntent:
    """A pure classification of a question against the finite intent catalog."""

    intent: str
    confidence: str  # 'high' | 'low' | 'none'
    extracted: dict = field(default_factory=dict)  # {} | {'field': ..} | {'topic': ..}
    alternatives: tuple = ()  # distinct intents that tied, when ambiguous


# --- normalization + extraction ----------------------------------------------

_WS_RE = re.compile(r"\s+")
#: Leading/trailing punctuation stripped around the whole normalized question.
_EDGE_PUNCT = " \t\r\n.?!,;:\"'`()[]{}"

_FIELD_STOPWORDS = frozenset({
    "the", "a", "an", "my", "this", "its", "it", "for", "of", "to", "is", "are",
    "do", "does", "did", "come", "from", "value", "values", "field", "fields",
    "and", "in", "on", "s",
})

#: Phrases stripped (longest-first) when extracting a field token, per intent.
_FIELD_STRIP: dict[str, tuple[str, ...]] = {
    FIELD_PROVENANCE: (
        "where did the", "where did", "where does the", "where does",
        "come from", "came from", "provenance of the", "provenance of",
        "trace the", "trace", "source of the", "source of",
    ),
    EVIDENCE_SUMMARY: (
        "summarize the evidence for the", "summarize the evidence for",
        "summarise the evidence for the", "summarise the evidence for",
        "what's the evidence for the", "whats the evidence for the",
        "what's the evidence for", "whats the evidence for",
        "what is the evidence for", "the evidence for", "evidence for",
        "why multiple evidence entries for", "multiple evidence entries",
        "evidence entries", "summarize the evidence", "summarise the evidence",
    ),
}

#: Phrases stripped (longest-first) when extracting a memory topic.
_TOPIC_STRIP: tuple[str, ...] = (
    "what does project memory know about the", "what does project memory know about",
    "does project memory know about the", "does project memory know about",
    "project memory know about", "what does project memory say about",
    "project memory", "docs about the", "docs about", "documentation about the",
    "documentation about", "where is the", "where is", "the concept of",
    "concept of", "defined", "concept", "about",
)


def normalize(question: str) -> str:
    """Deterministic normalization: strip, lowercase, collapse whitespace, and
    strip surrounding punctuation. Never raises for a non-str/empty input."""
    if not isinstance(question, str):
        return ""
    collapsed = _WS_RE.sub(" ", question).strip()
    lowered = collapsed.lower()
    return lowered.strip(_EDGE_PUNCT)


def _strip_phrases(text: str, phrases) -> str:
    """Remove the FIRST occurrence of each phrase (longest-first) from ``text``."""
    out = text
    for phrase in sorted(phrases, key=len, reverse=True):
        idx = out.find(phrase)
        if idx != -1:
            out = out[:idx] + " " + out[idx + len(phrase):]
    return _WS_RE.sub(" ", out).strip()


def _extract_field(normalized: str, intent: str) -> Optional[str]:
    """Extract a candidate field token from a provenance/evidence question.

    Strips the intent's trigger phrases, drops stopwords, and returns the
    remaining token string, or ``None`` when nothing identifiable remains — a
    field is NEVER guessed."""
    remainder = _strip_phrases(normalized, _FIELD_STRIP.get(intent, ()))
    tokens = [t for t in remainder.split() if t and t not in _FIELD_STOPWORDS]
    token = " ".join(tokens).strip(_EDGE_PUNCT)
    return token or None


def _extract_topic(normalized: str) -> str:
    """Extract a memory search topic: the remainder after the trigger phrases,
    falling back to the whole normalized question when nothing remains."""
    remainder = _strip_phrases(normalized, _TOPIC_STRIP)
    tokens = [t for t in remainder.split() if t and t not in _FIELD_STOPWORDS]
    topic = " ".join(tokens).strip(_EDGE_PUNCT)
    return topic or normalized


# --- Phase A: classify --------------------------------------------------------


def classify(question: str) -> ClassifiedIntent:
    """Classify a free-form question against the finite intent catalog (pure).

    Deterministic: identical input yields an identical :class:`ClassifiedIntent`.
    No context, no I/O, no scoring model — only explicit phrase containment plus
    a fixed precedence order."""
    normalized = normalize(question)
    if not normalized:
        return ClassifiedIntent(UNSUPPORTED, "none")

    scores: dict[str, int] = {}
    for intent, phrases in _TRIGGERS.items():
        hits = sum(1 for p in phrases if p in normalized)
        if hits:
            scores[intent] = hits

    if not scores:
        return ClassifiedIntent(UNSUPPORTED, "none")

    top = max(scores.values())
    tied = frozenset(i for i, s in scores.items() if s == top)

    intent = _resolve_tie(tied)
    if intent == AMBIGUOUS:
        alts = tuple(i for i in _INTENT_ORDER if i in tied)
        return ClassifiedIntent(AMBIGUOUS, "none", alternatives=alts)

    extracted: dict = {}
    confidence = "high"
    if intent in _FIELD_INTENTS:
        token = _extract_field(normalized, intent)
        if token is not None:
            extracted["field"] = token
        else:
            # The intent is clear but no field could be identified — a weaker,
            # "which field?" answer follows; never a guessed field.
            confidence = "low"
    elif intent == MEMORY_LEAD:
        extracted["topic"] = _extract_topic(normalized)

    return ClassifiedIntent(intent, confidence, extracted=extracted)


def _resolve_tie(tied: frozenset) -> str:
    """Resolve a score tie to a single intent, or ``AMBIGUOUS``.

    A catch-all (general) intent always yields to a specific one. The one
    specific precedence pair (export blockers over readiness) is resolved
    explicitly. Any remaining genuine tie between distinct specific intents is
    honestly ``ambiguous`` (never a silent pick)."""
    if len(tied) == 1:
        return next(iter(tied))
    specific = tied - _GENERAL_INTENTS
    if not specific:
        # Only general intents tied (in practice a single one) — pick in order.
        return next(i for i in _INTENT_ORDER if i in tied)
    if len(specific) == 1:
        return next(iter(specific))
    if specific == _EXPORT_PAIR:
        return EXPORT_BLOCKERS  # blocker/negation cue outranks readiness
    return AMBIGUOUS


# --- read-only context --------------------------------------------------------


@dataclass(frozen=True)
class AssistantContext:
    """Read-only grounding the route assembles from the loaded experiment.

    Expensive grounding (the validate dry-run, the memory search) is supplied as
    a zero/one-arg thunk invoked ONLY for the matched intent, so classification
    stays cheap and the resolver never does work an intent does not need. Nothing
    here is ever mutated by the resolver."""

    record_summary: dict
    pending: dict            # serialize.pending_to_list(...) -> {"pending": [...]}
    evidence_trail: list     # serialize.evidence_trail_from_draft(...)
    workflow: dict           # derive_workflow(...) -> {ordered_steps, current_step, ...}
    record_rev: int
    version_token: str
    navigate_base: str       # e.g. "/record/<id>"
    validate: Callable[[], dict] = lambda: {"ok": None, "errors": []}
    search: Callable[[str], dict] = lambda _q: {"available": False, "results": []}


# --- guards + safety ----------------------------------------------------------

#: Verdict-language guard — a faithful port of
#: ``apps/web/src/lib/assistant.ts::hasVerdictLanguage``. ``PASS``/``FAIL`` are
#: matched case-SENSITIVELY (reserved verdict tokens); ``(in)?valid against`` is
#: case-insensitive.
_VERDICT_PASSFAIL = re.compile(r"\b(PASS|FAIL)\b")
_VERDICT_VALID = re.compile(r"\b(in)?valid against\b", re.I)

#: Path/secret scrub — a port of ``assistantSession.ts::isUnsafeString``.
_HEX_TOKEN = re.compile(r"\b[0-9a-f]{32,}\b", re.I)

#: Client-route prefixes a ``navigate_to`` / an action target may use (never a
#: filesystem path, never an external URL). P36V.1 Unit B added ``/governance``:
#: the standalone Validator lives at ``/governance?tab=validator``, and the SAME
#: allowlist the frontend applies (``AssistantPanel.isClientRoute``) already
#: includes it. The route is base-path-FREE — the deployed ``/krish`` prefix is
#: applied by the router's ``basename``, never written here.
_CLIENT_ROUTE_PREFIXES = ("/record", "/memory", "/governance")

#: The deterministic Validator's in-app client route. Kept as one constant so the
#: action target and the allowlist can never disagree.
_VALIDATOR_ROUTE = "/governance?tab=validator"

#: P36V.1 Unit B — the ONE bounded navigation action a free-form answer may carry,
#: mirroring the frontend's frozen ``OPEN_VALIDATOR_ACTION``
#: (``apps/web/src/lib/assistantComposer.ts``). ``kind`` is the contract; ``label``
#: and ``to`` make the response self-describing. It navigates and nothing else: it
#: writes no field, runs no validation, changes no validation result, and
#: authorizes no export. Handed out as a COPY (see :func:`_open_validator_action`)
#: so no caller can mutate the shared target.
_OPEN_VALIDATOR_ACTION = {
    "kind": "open-validator",
    "label": "Open Validator",
    "to": _VALIDATOR_ROUTE,
}


def _open_validator_action() -> dict:
    """A fresh copy of the Open Validator action descriptor."""
    return dict(_OPEN_VALIDATOR_ACTION)


def has_verdict_language(text: str) -> bool:
    """True iff ``text`` contains reserved verdict language (never to be emitted)."""
    if not isinstance(text, str):
        return False
    return bool(_VERDICT_PASSFAIL.search(text)) or bool(_VERDICT_VALID.search(text))


def _is_unsafe_string(value: str) -> bool:
    """True iff ``value`` contains a bearer token, an absolute/home path, or a
    long hex token (mirrors ``isUnsafeString``)."""
    if not isinstance(value, str):
        return False
    if "Bearer " in value:
        return True
    if value.startswith("/") or "/Users/" in value or "\\Users\\" in value:
        return True
    if _HEX_TOKEN.search(value):
        return True
    return False


def _safe_navigate_to(value) -> Optional[str]:
    """Return ``value`` only when it is a safe client route, else ``None``."""
    if not isinstance(value, str) or not value:
        return None
    if not value.startswith(_CLIENT_ROUTE_PREFIXES):
        return None
    # Defense in depth: a client route must never smuggle an absolute/home path
    # or a secret through a query string.
    if "/Users/" in value or "\\Users\\" in value or "Bearer " in value:
        return None
    if _HEX_TOKEN.search(value):
        return None
    return value


def _scrub_sources(sources: list) -> list:
    """Drop any source whose label is unsafe OR carries reserved verdict language;
    keep only safe client-route links.

    A cited label is neutralized like the answer text: a label that trips the
    path/secret scrub OR the verdict-language guard is dropped entirely, so a
    project-memory lead titled e.g. "…valid against v1.05" can never surface that
    phrase through a citation chip and bypass the guard on the answer body."""
    out: list = []
    for src in sources:
        label = src.get("label")
        if not isinstance(label, str) or not label or _is_unsafe_string(label):
            continue
        if has_verdict_language(label):
            continue
        out.append({"label": label, "navigate_to": _safe_navigate_to(src.get("navigate_to"))})
    return out


# --- template fragment helpers (mirror the frontend composer) -----------------
#
# P36V.1 Unit B — ``_count`` and ``_join_capped`` are now imported from
# :mod:`isaac_api.assistant_paths` (which the blocker summary needs anyway), so
# there is exactly ONE implementation of each per language instead of two that were
# free to drift. The internal names are unchanged, so no call site moved.


def _pending_labels(pending_items: list) -> list:
    labels = []
    for p in pending_items:
        for key in ("about", "question", "id"):
            v = p.get(key)
            if isinstance(v, str) and v.strip():
                labels.append(v.strip())
                break
        else:
            labels.append("unnamed pending field")
    return labels


def _humanize(path: str) -> str:
    """Humanize the last path segment (``sample.material.formula`` -> ``Formula``)."""
    last = re.split(r"[.:]", path)[-1]
    return last.replace("_", " ").strip().title() or path


def _source_types(evidence) -> list:
    seen: list = []
    for e in evidence or []:
        st = e.get("source_type") if isinstance(e, dict) else None
        if st and st not in seen:
            seen.append(st)
    return seen


def _match_field_entry(token: Optional[str], evidence_trail: list) -> Optional[dict]:
    """First evidence-trail entry whose path/label contains the token (draft
    order → deterministic). ``None`` when unmatched — a field is never guessed."""
    if not token:
        return None
    needle = token.lower()
    for entry in evidence_trail:
        path = str(entry.get("path") or "")
        hay = f"{path} {_humanize(path)}".lower()
        if needle in hay:
            return entry
    return None


def _traceable_labels(evidence_trail: list) -> list:
    labels: list = []
    for entry in evidence_trail:
        if entry.get("evidence"):
            labels.append(_humanize(str(entry.get("path") or "")))
    return labels


_MEMORY_TAIL = "Project memory returns leads to verify — never a validation verdict."
_MEMORY_DISTINCTION = (
    "Memory suggests leads to verify; the current record shows its own confirmed "
    "values."
)

#: P34.4 — the honest refusal the record-agnostic Project-Memory surface returns
#: for ANY non-memory question. It states plainly what this surface answers and
#: points the user at a record for record questions — never a verdict, never a
#: guess, never a fabricated record answer with no record to ground it.
_MEMORY_SCOPE_REFUSAL = (
    "This is the Project Memory view — I answer project-memory questions here. "
    "Open a record to ask about its fields, evidence, workflow, or export "
    "readiness."
)

_STATUS_LABELS = {
    "needs_attention": "needs attention",
    "in_review": "in review",
    "ready_to_export": "ready to export",
    "done": "done",
}

_WORKFLOW_PATH = (
    "Load Record → Complete Metadata → Review Evidence → Review Export Readiness "
    "→ Export"
)

#: P36V.1 Unit B — the user-visible control is named **Open Validator** (the
#: frontend's `OPEN_VALIDATOR_ACTION.label`). This prose used to say "Open
#: Validate", naming a control that did not exist under that name anywhere in the
#: app. It is used ONLY on the answers that also CARRY the action, so the sentence
#: now names a control genuinely rendered beside it. It says "reach", not "run":
#: activating it opens the Validator surface and runs nothing.
_ROUTE_TO_VALIDATE = "Open Validator to reach the deterministic schema check."

#: Where the deterministic schema check lives, for answers that carry NO action
#: (the compose-failure fallback and the verdict-guard replacement). Naming the
#: surface rather than a button avoids pointing at a control that is not on screen.
_VALIDATOR_SURFACE = (
    "The deterministic schema check runs on its own surface — Governance & Safety "
    "→ Validator."
)

#: The neutral replacement text when the verdict guard or the path/secret scrub
#: trips. It carries no verdict and names no absent control.
_NEUTRAL_ROUTED = f"I can point you to the deterministic checks. {_VALIDATOR_SURFACE}"

#: Supported next questions offered as followups, per intent.
_FOLLOWUPS: dict[str, tuple[str, ...]] = {
    PENDING_FIELDS: ("What's blocking export?", "Summarize this record."),
    EXPORT_BLOCKERS: ("What still needs me?", "Is this ready to export?"),
    EXPORT_READINESS: ("What's blocking export?", "What still needs me?"),
    WORKFLOW_STEP: ("What still needs me?", "Summarize this record."),
    FIELD_PROVENANCE: ("What's the evidence for this field?", "Summarize this record."),
    EVIDENCE_SUMMARY: ("Where did this field come from?", "What still needs me?"),
    RECORD_SUMMARY: ("What still needs me?", "What's blocking export?"),
    MEMORY_LEAD: ("Summarize this record.", "What still needs me?"),
}

#: The supported question families named in every refusal.
_SUPPORTED_FAMILIES = (
    "pending fields, export blockers, export readiness, the workflow step, field "
    "provenance, evidence for a field, a record summary, or project-memory leads"
)


# --- Phase B: answer ----------------------------------------------------------


def answer(classified: ClassifiedIntent, context: AssistantContext,
           grounded_rev: Optional[str]) -> dict:
    """Compose a deterministic, verdict-guarded, leak-safe response dict.

    Answers are built from structured template fragments (never free prose) that
    mirror the frontend composer's tone and its 'never a verdict' rule. Every
    composed answer + source label passes the verdict guard and the path/secret
    scrub before it is returned."""
    # P36V.1 Unit B — the two PRESENTATION extras a branch may contribute: the
    # bounded navigation `action` and the exact `technical_paths`. They are
    # collected through this out-dict rather than by widening every one of
    # `_compose`'s ten return tuples (and those of its four helpers) to carry two
    # more positional slots that nine of them would never use. Nothing here feeds
    # classification, grounding, or any verdict — it is display data only.
    extras: dict = {}
    try:
        text, result, grounding, sources, followups = _compose(classified, context, extras)
    except Exception:
        # Never raise / never 500. Log a FIXED, path-free message (mirrors
        # post_validate) — never the question text or the exception detail.
        _log.exception("assistant_query compose failed intent=%s", classified.intent)
        text = (
            "I couldn't complete that from the record's grounded surfaces. "
            f"{_VALIDATOR_SURFACE}"
        )
        result, grounding, sources, followups = "insufficient_context", [], [], []
        # A partially-populated extras dict from a branch that then raised must
        # never be returned alongside a fallback answer.
        extras = {}

    # Verdict guard: a composed answer must never state a verdict. Path/secret guard
    # over the answer text: same replacement.
    if has_verdict_language(text) or _is_unsafe_string(text):
        text = _NEUTRAL_ROUTED
        # P36V.1 review M4 — the replacement names NO locations and (by design, see
        # `_VALIDATOR_SURFACE`) carries no control, so the extras a neutralized
        # branch had already contributed must go with it. Shipping
        # `technical_paths` under an answer that lists no locations made the answer
        # and its own disclosure disagree; shipping the action made the prose name a
        # surface while a button pointed somewhere else.
        extras = {}

    version = context.version_token
    return {
        "answer": text,
        "result": result,
        "grounding": grounding,
        "sources": _scrub_sources(sources),
        "record_rev": context.record_rev,
        "version": version,
        "stale": grounded_rev is not None and grounded_rev != version,
        "followups": list(followups),
        # P36V.1 Unit B — presentation extras, guarded by the SAME client-route
        # allowlist every cited source passes.
        "action": _safe_action(extras.get("action")),
        "technical_paths": _safe_technical_paths(extras.get("technical_paths")),
    }


def _safe_action(action) -> Optional[dict]:
    """Return the action only when it is a well-formed, allowlisted client-route
    navigation descriptor, else ``None``.

    The same rule every cited source passes: a target that is not an in-app client
    route (an absolute server path, an external URL, a smuggled secret) is never
    handed to the client."""
    if not isinstance(action, dict):
        return None
    kind = action.get("kind")
    label = action.get("label")
    if not isinstance(kind, str) or not kind:
        return None
    if not isinstance(label, str) or not label or _is_unsafe_string(label):
        return None
    if has_verdict_language(label):
        return None
    to = _safe_navigate_to(action.get("to"))
    if to is None:
        return None
    return {"kind": kind, "label": label, "to": to}


#: P36V.1 review M5 — the explicit stand-in for a locator withheld from the
#: disclosure because it trips the path/secret scrub. It is deliberately NOT a
#: locator and cannot be mistaken for one (same idiom as
#: ``assistant_paths.NO_PATH_TECHNICAL``): it discloses that something was withheld
#: instead of silently shortening the list.
WITHHELD_TECHNICAL = "(withheld: unsafe to display)"


def _safe_technical_paths(paths) -> list:
    """The exact validation locators, keeping only safe display strings.

    These are JSON locators from the deterministic validator, never filesystem
    paths — but they are rendered verbatim in the Technical Details disclosure, so
    they pass the SAME path/secret scrub as every other emitted string. A locator
    that trips it is never rewritten into something it is not: it is replaced by the
    explicit :data:`WITHHELD_TECHNICAL` marker.

    P36V.1 review M5 — that replacement (rather than a silent drop) is what keeps
    the stated count and the shown disclosure consistent. The prose count comes from
    the UNFILTERED error list, so dropping an unsafe 4th+ locator produced "5
    validation issues" beside 4 rows, with the missing one never named in the text
    either (the ≤3 label cap hides it) and nothing explaining the gap. The count
    stays truthful — it is the validator's error count — and nothing is silently
    truncated (no cap is introduced here).

    An entry that is not a usable string at all is still omitted: it carries no
    locator and cannot occur from :func:`assistant_paths.technical_paths`, which
    yields a non-empty string for every error (``NO_PATH_TECHNICAL`` when the error
    reported no path)."""
    if not isinstance(paths, list):
        return []
    out: list = []
    for p in paths:
        if not isinstance(p, str) or not p:
            continue
        out.append(WITHHELD_TECHNICAL if _is_unsafe_string(p) else p)
    return out


#: P36V.1 review IMPORTANT-3 — the record SUB-SURFACE a cited source points at,
#: appended to ``ctx.navigate_base`` (``/record/<id>``). These are the SAME client
#: routes the frontend owns (``ROUTES.complete`` / ``ROUTES.evidence`` in
#: ``apps/web/src/lib/routes.ts``, mounted by ``AppRoutes`` as
#: ``/record/:id/complete`` and ``/record/:id/evidence``), they are inside the
#: ``/record`` prefix both :func:`_safe_navigate_to` and the panel's
#: ``isClientRoute`` allow, and they are base-path-FREE — the deployed ``/krish``
#: prefix is applied by the router's ``basename``, never written here.
#:
#: They exist because a chip labelled "Complete Metadata" / "Evidence & Sources"
#: whose target was ``base`` navigated to the record page ALREADY on screen when
#: the question was asked from the Record Workbench — the same inert click this
#: slice was opened to fix, in two more places.
_COMPLETE_SUFFIX = "/complete"
_EVIDENCE_SUFFIX = "/evidence"


def _compose(classified: ClassifiedIntent, ctx: AssistantContext, extras: dict):
    """Return ``(answer, result, grounding, sources, followups)`` for an intent.

    ``extras`` is an out-dict for PRESENTATION-only additions (``action``,
    ``technical_paths``); a branch that offers neither leaves it untouched."""
    intent = classified.intent
    base = ctx.navigate_base
    followups = list(_FOLLOWUPS.get(intent, ()))

    if intent == PENDING_FIELDS:
        items = ctx.pending.get("pending") or []
        if not items:
            text = "No pending fields are listed for this record."
        else:
            labels = _pending_labels(items)
            verb = "needs" if len(items) == 1 else "need"
            text = f"{_count(len(items), 'field')} still {verb} you: {_join_capped(labels)}."
        # IMPORTANT-3: "Complete Metadata" now points at the Guided Completion
        # surface, not at the record root the reader was already on.
        return text, "answered", ["workflow"], [
            {"label": "Complete Metadata", "navigate_to": f"{base}{_COMPLETE_SUFFIX}"}
        ], followups

    if intent == EXPORT_BLOCKERS:
        errors = (ctx.validate() or {}).get("errors") or []
        # P36V.1 review IMPORTANT-1 — the CRASH SENTINEL, before anything is
        # described as a finding. `routes.py::_assistant_validate_dryrun` returns
        # `[{"path": "$", "message": "Validation could not be completed."}]` when the
        # dry-run itself RAISED. Read through the locator formatter alone that is
        # indistinguishable from a root-level violation, and this branch told the
        # reader "1 record-level validation issue may be blocking export" — a
        # confident claim about an issue the validator never located, i.e. exactly
        # the guessing CLAUDE.md §3/§5 forbid. `routes.py` is NOT changed (its
        # payload is correct and it is not this unit's file); the INTERPRETATION is.
        # `insufficient_context` is the honest result: no count, no location, no
        # locator disclosure (there is none), and no verdict either way.
        if is_validation_unavailable(errors):
            text = f"{VALIDATION_UNAVAILABLE_SUMMARY} {_ROUTE_TO_VALIDATE}"
            extras["action"] = _open_validator_action()
            return text, "insufficient_context", ["schema"], [], followups
        # P36V.1 Unit B — the locators are HUMANIZED by the shared formatter
        # (`assistant_paths`, mirrored in `assistantPaths.ts`). The old template
        # interpolated the raw locator list, so a root-level violation rendered as
        # "1 path is listed as blocking export: $." — naming nothing actionable.
        # Note the old `str(e.get("path"))` also turned a MISSING path into the
        # literal string "None"; the formatter reports it as an unreported location.
        # The exact locators go to `technical_paths` for the collapsed Technical
        # Details disclosure. Same errors, same count — presentation only.
        raw_paths = [e.get("path") for e in errors]
        if not errors:
            text = f"{NO_BLOCKING_ISSUES} {_ROUTE_TO_VALIDATE}"
        else:
            text = f"{blocking_summary(raw_paths)} {_ROUTE_TO_VALIDATE}"
            extras["technical_paths"] = technical_paths(raw_paths)
        # P36V.1 Unit B — the validate affordance is now a real typed ACTION
        # targeting the standalone Validator, replacing a cited-source chip labelled
        # "Open Validate" whose `navigate_to` was `base` — the record ALREADY on
        # screen — which is why clicking it appeared to do nothing. `sources` is now
        # empty here: an action is not a citation, and the answer's plane label
        # (Schema Rules, from `grounding`) already states where it came from.
        extras["action"] = _open_validator_action()
        return text, "answered", ["schema"], [], followups

    if intent == EXPORT_READINESS:
        pending_n = len(ctx.pending.get("pending") or [])
        # P36V.1 Unit B, incidental: this clause read "This record has 5 fields
        # still need you" — ungrammatical, and in the very sentence whose
        # punctuation this slice had to change. Now the SAME phrasing the
        # PENDING_FIELDS answer uses. No semantic change: same count, same source.
        verb = "needs" if pending_n == 1 else "need"
        text = (
            "Export readiness combines clearing every pending field with a passing "
            f"deterministic schema check. On this record, {_count(pending_n, 'field')} "
            f"still {verb} you. {_ROUTE_TO_VALIDATE} Coverage figures appear after export."
        )
        # Same fix as EXPORT_BLOCKERS: a real action instead of a self-navigating
        # chip. (The sentence break before it was a semicolon, which read as
        # "…needs you; Open Validator to…"; a full stop matches the new control name.)
        extras["action"] = _open_validator_action()
        return text, "answered", ["workflow", "schema"], [], followups

    if intent == WORKFLOW_STEP:
        current = ctx.workflow.get("current_step")
        if current is None:
            text = f"All workflow steps are satisfied for this record. The workflow is: {_WORKFLOW_PATH}."
        else:
            label = _current_step_label(ctx.workflow, current)
            text = f"The current workflow step is '{label}'. The workflow is: {_WORKFLOW_PATH}."
        # IMPORTANT-3 audit — DELIBERATELY left at the record root. The workflow
        # surface IS the record page: `RecordWorkbench` renders both the
        # `WorkflowSpine` and the `WorkflowProgressBanner`, and there is no
        # `/workflow` client route to point at (`ROUTE_PATTERNS` has none). Adding
        # one would be a new surface, not a fix. From the Record Workbench mount this
        # citation is therefore a same-page link rather than a wrong one — the label
        # names where the workflow is shown, and the target is that place.
        return text, "answered", ["workflow"], [{"label": "Workflow", "navigate_to": base}], followups

    if intent == FIELD_PROVENANCE:
        return _provenance(classified, ctx, base, followups)

    if intent == EVIDENCE_SUMMARY:
        return _evidence(classified, ctx, base, followups)

    if intent == RECORD_SUMMARY:
        return _record(ctx, base, followups)

    if intent == MEMORY_LEAD:
        return _memory(classified, ctx.search, followups)

    if intent == AMBIGUOUS:
        alt_labels = _join_capped([a.replace("_", " ") for a in classified.alternatives])
        text = (
            f"That could mean a few things — {alt_labels}. Which did you mean? For "
            "example: \"What's blocking export?\""
        )
        return text, "ambiguous", [], [], []

    # UNSUPPORTED (and any unknown intent) — honest refusal, names what IS supported.
    text = (
        "That question isn't something I can answer from this record's grounded "
        f"surfaces. I can help with: {_SUPPORTED_FAMILIES}. Try: \"What still "
        "needs me?\""
    )
    return text, "unsupported", [], [], []


def _current_step_label(workflow: dict, current: str) -> str:
    for step in workflow.get("ordered_steps") or []:
        if step.get("id") == current:
            return str(step.get("label") or current)
    return current


def _provenance(classified, ctx, base, followups):
    token = classified.extracted.get("field")
    entry = _match_field_entry(token, ctx.evidence_trail)
    if entry is None:
        labels = _traceable_labels(ctx.evidence_trail)
        if labels:
            text = (
                "Tell me which field to trace. Traceable fields include: "
                f"{_join_capped(labels)}."
            )
        else:
            text = "No cited source is recorded for a field yet."
        return text, "insufficient_context", ["files"], [], followups
    label = _humanize(str(entry.get("path") or ""))
    types = _source_types(entry.get("evidence"))
    n = len(entry.get("evidence") or [])
    if types:
        word = "source type" if len(types) == 1 else "source types"
        text = (
            f"{label} traces to {_count(n, 'evidence entry', 'evidence entries')} — "
            f"{word}: {_join_capped(types)}."
        )
    else:
        text = f"{label} has no cited source recorded yet."
    # IMPORTANT-3: the citation opens the Evidence Explorer, not the record root.
    return text, "answered", ["files"], [
        {"label": "Evidence & Sources", "navigate_to": f"{base}{_EVIDENCE_SUFFIX}"}
    ], followups


def _evidence(classified, ctx, base, followups):
    token = classified.extracted.get("field")
    entry = _match_field_entry(token, ctx.evidence_trail)
    if entry is None:
        labels = _traceable_labels(ctx.evidence_trail)
        if labels:
            text = (
                "Tell me which field's evidence to summarize. Fields with evidence "
                f"include: {_join_capped(labels)}."
            )
        else:
            text = "No field has recorded evidence entries yet."
        return text, "insufficient_context", ["files"], [], followups
    label = _humanize(str(entry.get("path") or ""))
    types = _source_types(entry.get("evidence"))
    n = len(entry.get("evidence") or [])
    if n == 0:
        text = f"{label} has no separate evidence entries recorded."
    elif n == 1:
        text = f"{label} has {_count(1, 'evidence entry', 'evidence entries')}: {types[0] if types else 'unspecified source'}."
    else:
        shown = types if types else ["unspecified source"]
        text = (
            f"{label} has {_count(n, 'evidence entry', 'evidence entries')}: "
            f"{_join_capped(shown)}. Multiple entries can provide separate support "
            "for the same field."
        )
    # IMPORTANT-3: the citation opens the Evidence Explorer, not the record root.
    return text, "answered", ["files"], [
        {"label": "Evidence & Sources", "navigate_to": f"{base}{_EVIDENCE_SUFFIX}"}
    ], followups


def _record(ctx, base, followups):
    s = ctx.record_summary or {}
    title = s.get("title")
    status = _STATUS_LABELS.get(s.get("status"), str(s.get("status") or "in progress"))
    pending_n = int(s.get("pending_count") or 0)
    evidenced = int(s.get("evidenced_field_count") or 0)
    name = f" '{title}'" if isinstance(title, str) and title.strip() else ""
    text = (
        f"This record{name} is currently {status}, with "
        f"{_count(pending_n, 'pending field')} and {_count(evidenced, 'evidenced field')}."
    )
    # IMPORTANT-3 audit — DELIBERATELY left at the record root. The label is
    # "Record" and the record root IS the record surface, so the target matches what
    # the chip names. From the Complete / Evidence / Export mounts it is a real
    # navigation back to the record; from the Record Workbench it is a same-page
    # link. Re-pointing it anywhere else would make the citation name one surface and
    # open another.
    return text, "answered", ["workflow"], [{"label": "Record", "navigate_to": base}], followups


def _memory(classified, search, followups):
    topic = classified.extracted.get("topic") or ""
    try:
        res = search(topic) or {}
    except Exception:
        res = {"available": False, "results": []}
    if not res.get("available"):
        text = (
            "Project memory is unavailable, so no leads can be served here. "
            f"{_MEMORY_TAIL}"
        )
        return text, "insufficient_context", ["graph"], [], followups
    results = res.get("results") or []
    if not results:
        text = f"Project memory has no leads for that topic. {_MEMORY_TAIL}"
        return text, "insufficient_context", ["graph"], [], followups
    leads: list = []
    sources: list = []
    for r in results[:3]:
        label = r.get("label") or r.get("id") or r.get("path")
        if not isinstance(label, str) or not label:
            continue
        leads.append(label)
        sources.append({"label": label, "navigate_to": r.get("navigate_to")})
    if not leads:
        text = f"Project memory has no citable leads for that topic. {_MEMORY_TAIL}"
        return text, "insufficient_context", ["graph"], [], followups
    text = (
        f"Memory suggests {_count(len(leads), 'lead')} to verify: {_join_capped(leads)}. "
        f"{_MEMORY_DISTINCTION} {_MEMORY_TAIL}"
    )
    return text, "answered", ["graph"], sources, followups


# --- Phase B (memory scope): record-agnostic Project-Memory answer -------------


def answer_memory_scope(classified: ClassifiedIntent,
                        search: Callable[[str], dict]) -> dict:
    """Compose a deterministic, leak-safe answer for the RECORD-AGNOSTIC Project
    Memory surface (P34.4).

    This surface has NO record. A ``MEMORY_LEAD`` question is answered purely from
    the memory reader (the SAME ``_memory`` logic the record endpoint uses),
    grounded ``["graph"]`` with cited leads and the "leads to verify" advisory
    framing — never a verdict. Any OTHER classification (a record intent,
    unsupported, ambiguous, or empty) is an HONEST refusal that names what this
    surface answers and points the user at a record — it never fabricates a record
    answer with no record to ground it, and never guesses.

    The response mirrors the record endpoint's shape EXCEPT it carries no record:
    ``record_rev``/``version`` are ``null`` and ``stale`` is always ``False`` (there
    is no revision to be stale against). The SAME verdict guard and path/secret
    scrub run over the answer text and every source label. Follow-ups are
    suppressed here: the intent catalog's memory follow-ups are record questions,
    which would dead-end on this record-less surface."""
    if classified.intent == MEMORY_LEAD:
        try:
            # Follow-ups suppressed ([]): the catalog's MEMORY_LEAD follow-ups are
            # record questions that cannot be answered on this record-less surface.
            text, result, grounding, sources, followups = _memory(classified, search, [])
        except Exception:
            _log.exception("assistant_query memory-scope compose failed")
            text = f"Project memory is unavailable, so no leads can be served here. {_MEMORY_TAIL}"
            result, grounding, sources, followups = "insufficient_context", ["graph"], [], []
    else:
        # Every non-memory question is refused honestly — no verdict, no guess, and
        # no fabricated record answer (there is no record on this surface).
        text = _MEMORY_SCOPE_REFUSAL
        result, grounding, sources, followups = "unsupported", [], [], []

    # The SAME guards as the record path: never emit a verdict or a path/secret.
    if has_verdict_language(text):
        text = _NEUTRAL_ROUTED
    if _is_unsafe_string(text):
        text = _NEUTRAL_ROUTED

    return {
        "answer": text,
        "result": result,
        "grounding": grounding,
        "sources": _scrub_sources(sources),
        # No record on this surface: no revision, no version, never stale.
        "record_rev": None,
        "version": None,
        "stale": False,
        "followups": list(followups),
        # P36V.1 Unit B — response-shape parity with the record endpoint. This
        # record-less surface answers memory questions and refuses everything else,
        # so it offers no validate affordance and reports no validation locators.
        "action": None,
        "technical_paths": [],
    }
