"""P36X — the Assistant's "What Can I Ask?" catalog is exercised against the REAL
resolver.

The frontend catalog (``apps/web/src/lib/assistantCapabilities.ts``) advertises a
per-surface list of questions and, for each one, the intent family it claims to
reach. Its sibling frontend test checks those claims against ``_TRIGGERS`` read out
of this module's source. THIS test closes the loop from the authoritative side: it
reads the TypeScript catalog and runs the real :func:`isaac_api.assistant_query.classify`
over every advertised example, so an example that would be refused, or that would
land in a different family than the panel says, fails here.

Read-only: it classifies strings. It loads no workspace, writes nothing, and
composes no answer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from isaac_api import assistant_query as aq

CATALOG = Path(__file__).resolve().parents[3] / "apps/web/src/lib/assistantCapabilities.ts"

#: The groups advertised on the record surfaces vs. on Project Memory, as named in
#: the TS catalog. The graph group is EXCLUDED here on purpose: its examples are
#: recognised by the frontend graph classifier (``graphCommands.ts``) BEFORE the
#: composer ever calls this resolver, so they are not this module's questions and
#: the frontend test owns them.
_RECORD_CONST = "RECORD_CAPABILITY_GROUPS"
_MEMORY_CONST = "MEMORY_CAPABILITY_GROUPS"
_GRAPH_CONST = "GRAPH_CAPABILITY_GROUP"

_EXAMPLE_RE = re.compile(r"text:\s*(?:'([^']*)'|\"([^\"]*)\")\s*,\s*intent:\s*'([a-z_]+)'")


def _block(const: str, source: str) -> str:
    """The source text of one exported catalog constant."""
    start = source.index(f"export const {const}")
    nxt = source.find("\nexport ", start + 1)
    return source[start : nxt if nxt != -1 else len(source)]


def _examples(const: str) -> list[tuple[str, str]]:
    source = CATALOG.read_text(encoding="utf-8")
    found = [
        (m.group(1) if m.group(1) is not None else m.group(2), m.group(3))
        for m in _EXAMPLE_RE.finditer(_block(const, source))
    ]
    assert found, f"no examples parsed out of {const} — the catalog format changed"
    return found


RECORD_EXAMPLES = _examples(_RECORD_CONST)
MEMORY_EXAMPLES = _examples(_MEMORY_CONST)
GRAPH_EXAMPLES = _examples(_GRAPH_CONST)


def test_catalog_file_is_present_and_parsed():
    assert CATALOG.is_file(), f"{CATALOG} is missing"
    # A silently-empty parse would make every assertion below vacuous.
    assert len(RECORD_EXAMPLES) >= 8
    assert len(MEMORY_EXAMPLES) >= 1
    assert len(GRAPH_EXAMPLES) >= 1


@pytest.mark.parametrize("text,intent", RECORD_EXAMPLES + MEMORY_EXAMPLES)
def test_every_advertised_example_classifies_to_the_family_it_claims(text: str, intent: str):
    classified = aq.classify(text)
    assert classified.intent == intent, (
        f"{text!r} is advertised as {intent} but classifies as {classified.intent}"
    )
    # Neither refused nor ambiguous — those are the two outcomes an advertised
    # question must never produce.
    assert classified.intent not in {aq.UNSUPPORTED, aq.AMBIGUOUS}
    assert classified.alternatives == ()


@pytest.mark.parametrize("text,intent", MEMORY_EXAMPLES)
def test_memory_surface_examples_are_answerable_on_the_record_less_surface(text: str, intent: str):
    """The Project Memory surface answers ONLY ``memory_lead``; its advertised
    examples must therefore be memory questions that the record-agnostic resolver
    genuinely answers rather than refuses."""
    assert intent == aq.MEMORY_LEAD
    classified = aq.classify(text)
    result = aq.answer_memory_scope(classified, lambda _q: {"available": True, "results": [
        {"label": "A lead", "navigate_to": "/memory"}
    ]})
    assert result["result"] == "answered"
    assert result["grounding"] == ["graph"]
    # The refusal this surface gives every OTHER family must not appear.
    assert "This is the Project Memory view" not in result["answer"]


def test_record_families_really_are_refused_on_the_memory_surface():
    """The scoping claim the panel relies on, asserted rather than assumed: a record
    question on the record-less Project Memory surface is refused, which is exactly
    why the catalog omits those families there."""
    for text, intent in RECORD_EXAMPLES:
        if intent == aq.MEMORY_LEAD:
            continue  # genuinely supported on both surfaces
        result = aq.answer_memory_scope(aq.classify(text), lambda _q: {"available": False, "results": []})
        assert result["result"] == "unsupported", f"{text!r} unexpectedly answered on /memory"
        assert "This is the Project Memory view" in result["answer"]


def test_graph_examples_are_not_this_resolvers_questions():
    """Documented boundary: the graph examples are intercepted by the frontend graph
    classifier before this resolver is called. They are advertised ONLY when that
    interception is wired, so it is correct — and honest — that this catalog does not
    recognise them."""
    for text, _intent in GRAPH_EXAMPLES:
        assert aq.classify(text).intent in {aq.UNSUPPORTED, aq.AMBIGUOUS}
