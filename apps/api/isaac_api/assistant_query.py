"""P34.1 — a PURE, deterministic, READ-ONLY free-form question resolver.

This module is the backend analogue of the frontend grounded composer
(``apps/web/src/lib/assistantComposer.ts``): it turns a free-form user question
into a short, source-labeled, verdict-guarded reply grounded ENTIRELY in state
the route already fetched. It is subordinate and advisory — it NEVER states a
PASS/FAIL or a valid/invalid conclusion, never mutates a record, never guesses a
scientific value, and never authorizes an export.

Truth isolation (mirrors ``memory.py``)
--------------------------------------
Imports ONLY the standard library. It never imports ``isaac_records``, never
imports ``graphify``, computes no verdict, and takes no filesystem/network
action. Everything it needs is passed in via :class:`AssistantContext` — a
read-only bundle the route assembles (with expensive grounding supplied as
thunks invoked only for the matched intent). This keeps :func:`classify` pure and
unit-testable without a workspace, and keeps :func:`answer` a deterministic
function of its inputs.

Determinism
-----------
The SAME normalized question + SAME record state + SAME revision + SAME
:data:`RESOLVER_VERSION` produce byte-identical output. Classification is an
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

# Bump when the classification catalog, answer templates, or guards change so a
# cached/grounded answer computed under an older resolver is detectably distinct.
RESOLVER_VERSION = "p34.1"

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

#: Client-route prefixes a ``navigate_to`` may use (never a filesystem path).
_CLIENT_ROUTE_PREFIXES = ("/record", "/memory")

_NEUTRAL_ROUTED = (
    "I can point you to the deterministic checks — open Validate for the schema "
    "result."
)


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
    """Drop any source whose label is unsafe; keep only safe client-route links."""
    out: list = []
    for src in sources:
        label = src.get("label")
        if not isinstance(label, str) or not label or _is_unsafe_string(label):
            continue
        out.append({"label": label, "navigate_to": _safe_navigate_to(src.get("navigate_to"))})
    return out


# --- template fragment helpers (mirror the frontend composer) -----------------


def _count(n: int, singular: str, plural: Optional[str] = None) -> str:
    word = singular if n == 1 else (plural or f"{singular}s")
    return f"{n} {word}"


def _join_capped(items: list) -> str:
    shown = items[:3]
    rest = len(items) - len(shown)
    base = ", ".join(shown)
    return f"{base}, …and {rest} more" if rest > 0 else base


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

_ROUTE_TO_VALIDATE = "Open Validate to run the deterministic schema check."

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
    try:
        text, result, grounding, sources, followups = _compose(classified, context)
    except Exception:
        # Never raise / never 500. Log a FIXED, path-free message (mirrors
        # post_validate) — never the question text or the exception detail.
        _log.exception("assistant_query compose failed intent=%s", classified.intent)
        text = (
            "I couldn't complete that from the record's grounded surfaces. "
            f"{_ROUTE_TO_VALIDATE}"
        )
        result, grounding, sources, followups = "insufficient_context", [], [], []

    # Verdict guard: a composed answer must never state a verdict.
    if has_verdict_language(text):
        text = _NEUTRAL_ROUTED
    # Path/secret guard over the answer text.
    if _is_unsafe_string(text):
        text = _NEUTRAL_ROUTED

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
    }


def _compose(classified: ClassifiedIntent, ctx: AssistantContext):
    """Return ``(answer, result, grounding, sources, followups)`` for an intent."""
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
        return text, "answered", ["workflow"], [{"label": "Complete Metadata", "navigate_to": base}], followups

    if intent == EXPORT_BLOCKERS:
        errors = (ctx.validate() or {}).get("errors") or []
        if not errors:
            text = (
                "No blocking paths are listed in the current validation response. "
                f"{_ROUTE_TO_VALIDATE}"
            )
        else:
            verb = "is" if len(errors) == 1 else "are"
            paths = _join_capped([str(e.get("path")) for e in errors])
            text = (
                f"{_count(len(errors), 'path')} {verb} listed as blocking export: "
                f"{paths}. {_ROUTE_TO_VALIDATE}"
            )
        return text, "answered", ["schema"], [{"label": "Open Validate", "navigate_to": base}], followups

    if intent == EXPORT_READINESS:
        pending_n = len(ctx.pending.get("pending") or [])
        need = "field still needs" if pending_n == 1 else "fields still need"
        text = (
            "Export readiness combines clearing every pending field with a passing "
            f"deterministic schema check. This record has {pending_n} {need} you; "
            f"{_ROUTE_TO_VALIDATE} Coverage figures appear after export."
        )
        return text, "answered", ["workflow", "schema"], [{"label": "Open Validate", "navigate_to": base}], followups

    if intent == WORKFLOW_STEP:
        current = ctx.workflow.get("current_step")
        if current is None:
            text = f"All workflow steps are satisfied for this record. The workflow is: {_WORKFLOW_PATH}."
        else:
            label = _current_step_label(ctx.workflow, current)
            text = f"The current workflow step is '{label}'. The workflow is: {_WORKFLOW_PATH}."
        return text, "answered", ["workflow"], [{"label": "Workflow", "navigate_to": base}], followups

    if intent == FIELD_PROVENANCE:
        return _provenance(classified, ctx, base, followups)

    if intent == EVIDENCE_SUMMARY:
        return _evidence(classified, ctx, base, followups)

    if intent == RECORD_SUMMARY:
        return _record(ctx, base, followups)

    if intent == MEMORY_LEAD:
        return _memory(classified, ctx, followups)

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
    return text, "answered", ["files"], [{"label": "Evidence & Sources", "navigate_to": base}], followups


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
    return text, "answered", ["files"], [{"label": "Evidence & Sources", "navigate_to": base}], followups


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
    return text, "answered", ["workflow"], [{"label": "Record", "navigate_to": base}], followups


def _memory(classified, ctx, followups):
    topic = classified.extracted.get("topic") or ""
    try:
        res = ctx.search(topic) or {}
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
