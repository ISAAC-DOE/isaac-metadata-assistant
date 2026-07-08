"""Query-safety invariants live in the docs and the isaac-query skill, not in code —
so a doc rewrite could silently drop them. These tests pin the load-bearing phrases:
Graphify returns leads (never truth), validity/evidence route to `isaac validate` /
`isaac audit`, Graphify never validates or fills scientific values, real/private data
needs approval, portal warnings stay advisory/non-gating, and no doc claims full portal
parity is done. Pure stdlib: reads a fixed set of tracked docs, never runs graphify,
never touches graphify-out/ or examples/."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "isaac-query" / "SKILL.md"
GRAPHIFY_WORKFLOW = ROOT / "docs" / "graphify-workflow.md"
SAFETY_CHECKLIST = ROOT / "docs" / "query-safety-checklist.md"
PORTAL_WARNINGS = ROOT / "docs" / "portal-warnings.md"
README = ROOT / "README.md"


def _norm(text: str) -> str:
    """Lowercase and collapse every run of whitespace to a single space, so phrase
    checks are case-insensitive and tolerant of line wraps and indentation."""
    return " ".join(text.lower().split())


def _present(haystack: str, needle) -> bool:
    """`needle` is either a phrase (must appear) or a tuple of alternative phrasings
    (any one may appear). Both sides are normalized before the substring check."""
    if isinstance(needle, tuple):
        return any(_norm(alt) in haystack for alt in needle)
    return _norm(needle) in haystack


# (file, human-readable invariant, needle). `needle` is a phrase, or a tuple of
# acceptable alternatives (any-of). To update an invariant, edit one row.
REQUIRED = [
    (SKILL, "Graphify returns leads, not final truth",
     ("leads, not answers", "leads, not truth", "leads, not final truth")),
    (SKILL, "record validity routes to isaac validate", "isaac validate"),
    (SKILL, "evidence coverage routes to isaac audit", "isaac audit"),
    (SKILL, "Graphify must not validate records",
     ("cannot decide validity", "graphify is never truth", "graphify may never answer")),
    (SKILL, "Graphify must not fill missing scientific values",
     ("cannot fill a missing scientific value", "missing scientific value")),
    (SKILL, "real / private data must not be indexed without approval",
     ("never index real / private data without explicit approval", "never index real")),
    (SKILL, "portal warnings are advisory / non-gating",
     ("advisory / non-gating", "non-gating")),
    (GRAPHIFY_WORKFLOW, "documents graceful degradation", "graceful degradation"),
    (SAFETY_CHECKLIST, "covers unavailable Graphify", "graphify is unavailable"),
    (SAFETY_CHECKLIST, "covers stale Graphify", "graphify is stale"),
    (SAFETY_CHECKLIST, "routes real-data questions to data-governance",
     "data-governance.md"),
    (PORTAL_WARNINGS, "warnings are advisory and non-gating",
     ("advisory and non-gating", "advisory / non-gating", "non-gating")),
    (PORTAL_WARNINGS, "honest: not full upstream portal parity",
     ("not official portal parity", "not a reproduction of the upstream")),
    (README, "honest: no upstream portal-validator parity",
     ("no upstream portal-validator parity", "portal-validator parity")),
]

# Phrases that would falsely claim the advisory seam reached full portal parity.
# Negations ("portal parity is NOT implemented") do not match these, so they pass.
FORBIDDEN_PARITY_CLAIMS = (
    "portal parity is complete",
    "portal parity complete",
    "full portal parity is implemented",
    "full portal parity is complete",
    "achieved portal parity",
    "achieved full portal parity",
    "portal-validator parity is complete",
    "full portal-validator parity is implemented",
)

NEGATIVE_FILES = [SKILL, GRAPHIFY_WORKFLOW, SAFETY_CHECKLIST, PORTAL_WARNINGS, README]


@pytest.mark.parametrize(
    "path, invariant, needle",
    REQUIRED,
    ids=[f"{p.name}::{inv}" for p, inv, _ in REQUIRED],
)
def test_required_safety_phrase_present(path, invariant, needle):
    assert path.is_file(), f"missing safety doc: {path}"
    text = _norm(path.read_text(encoding="utf-8"))
    assert _present(text, needle), f"{path.name} no longer states: {invariant}"


@pytest.mark.parametrize("path", NEGATIVE_FILES, ids=[p.name for p in NEGATIVE_FILES])
def test_no_false_portal_parity_claim(path):
    text = _norm(path.read_text(encoding="utf-8"))
    for claim in FORBIDDEN_PARITY_CLAIMS:
        assert claim not in text, (
            f"{path.name} appears to claim full portal parity is done: {claim!r}"
        )
