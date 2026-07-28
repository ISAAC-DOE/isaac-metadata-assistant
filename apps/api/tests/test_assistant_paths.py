"""P36V.1 Unit B — the Python half of the validation-path formatter contract.

The SAME case table is replayed by the TypeScript half in
``apps/web/src/lib/assistantPaths.test.ts``. The two producers of the Assistant's
blocker copy live in different runtimes (``apps/api/isaac_api/assistant_query.py``
and ``apps/web/src/lib/assistantComposer.ts``), so literal code sharing is
impossible; this shared table is what turns a drift between the two
implementations into a test failure instead of a silent divergence in what a hosted
reader sees.

The defect being pinned: ``src/isaac_records/official.py:71`` renders a root-level
JSON Schema violation as the literal locator ``$`` (an empty ``absolute_path``
deque joins to ``""``, and the ``or "$"`` fallback substitutes the literal). Both
producers interpolated that straight into a user-facing sentence. ``official.py``
is truth core and is NOT edited — this is display-only.

Also asserted here: the import-isolation contract both modules claim in their
docstrings.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from isaac_api import assistant_paths as ap
from isaac_api import assistant_query as aq


def _repo_root() -> Path:
    """Locate the repo root by the vendored official schema (mirrors
    ``test_committed_snapshot._repo_root``); never a hardcoded absolute path."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[3]


REPO_ROOT = _repo_root()

#: The ONE shared table. It lives under ``apps/web/src`` because the TypeScript
#: suite can only import JSON from inside its own ``tsconfig`` include root; Python
#: simply reads it from the repo root. One file, two readers.
SHARED_CASES_PATH = REPO_ROOT / "apps" / "web" / "src" / "test" / "validation-path-cases.json"

SHARED = json.loads(SHARED_CASES_PATH.read_text(encoding="utf-8"))

CASES = SHARED["cases"]

CASE_IDS = [c["name"] for c in CASES]

#: The crash-sentinel discrimination table (P36V.1 review IMPORTANT-1).
UNAVAILABLE_CASES = SHARED["unavailable_cases"]

UNAVAILABLE_IDS = [c["name"] for c in UNAVAILABLE_CASES]


def test_shared_table_is_non_trivial():
    """A stubbed-out table must not be able to pass both suites vacuously."""
    assert len(CASES) >= 15
    raw = json.dumps([c["paths"] for c in CASES])
    assert '"$"' in raw, "the reported root-marker defect must be covered"
    assert "null" in raw, "a missing locator must be covered"
    assert '"$$"' in raw, "a $ surviving as a whole segment must be covered (M2)"
    assert len(UNAVAILABLE_CASES) >= 6
    assert any(c["unavailable"] for c in UNAVAILABLE_CASES)
    assert any(not c["unavailable"] for c in UNAVAILABLE_CASES)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_shared_case_table(case):
    paths = case["paths"]
    assert ap.classify_validation_paths(paths) == case["locations"]
    assert ap.technical_paths(paths) == case["technical"]
    assert ap.blocking_summary(paths) == case["summary"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_no_raw_root_marker_reaches_a_primary_summary(case):
    assert "$" not in ap.blocking_summary(case["paths"])


def test_raw_root_marker_is_preserved_in_the_technical_payload():
    root_cases = [c for c in CASES if "$" in c["paths"]]
    assert root_cases, "the table must cover the root marker"
    for case in root_cases:
        assert "$" in ap.technical_paths(case["paths"])


# --- IMPORTANT-2: the no-raw-`$` invariant, enforced GENERALLY ----------------
#
# The module docstring asserts the raw `$` never reaches a primary label. Both
# suites used to assert that only over the shared table's inputs, so the property
# was enforced NOWHERE in general — and the reviewer falsified it with `$$`,
# `a.$.b` and `assets.$`, which the leading-marker strip left untouched. This
# corpus is GENERATED (the SAME construction the TypeScript suite uses), so a
# future change that re-admits a bare `$` into a label fails here even if nobody
# thinks to add a table case for its exact shape.

_SEGMENT_POOL = ("a", "$", "", " ", "0", "$$", ".", "b_c")


def _generated_locators() -> list:
    """Every 1-, 2- and 3-segment dot-join over the pool, each also with a leading
    ``$`` and a leading ``$.`` — 1752 locators."""
    out: list = []
    level: list = [(s,) for s in _SEGMENT_POOL]
    for _depth in range(3):
        for parts in level:
            body = ".".join(parts)
            out.append(body)
            out.append(f"${body}")
            out.append(f"$.{body}")
        level = [parts + (s,) for parts in level for s in _SEGMENT_POOL]
    return out


GENERATED = _generated_locators()


def test_the_generated_corpus_is_large_and_actually_contains_root_markers():
    """Guard the guard: an empty/degenerate corpus must not pass vacuously."""
    assert len(GENERATED) > 500
    assert "$" in GENERATED and "$$" in GENERATED
    assert any(g.endswith(".$") for g in GENERATED)
    assert any(".$." in g for g in GENERATED)


def test_no_bare_root_marker_can_reach_a_label_or_a_summary_for_ANY_locator():
    for raw in GENERATED:
        loc = ap.classify_validation_path(raw)
        assert "$" not in loc["label"], raw
        # a label is always a real phrase — never blank, never invisible
        assert loc["label"].strip() != "", raw
        # …and it is either a known fixed phrase or a verbatim segment join
        if loc["kind"] == ap.FIELD:
            assert ap.ROOT_MARKER not in loc["label"].split(ap.SEGMENT_SEPARATOR), raw
        else:
            assert loc["label"] in (ap.RECORD_LEVEL_LABEL, ap.UNKNOWN_LOCATION_LABEL), raw
        assert "$" not in ap.blocking_summary([raw]), raw
    # and over the whole corpus at once
    assert "$" not in ap.blocking_summary(GENERATED)


def test_a_dollar_segment_is_never_described_as_a_field_location():
    for raw in ("$$", "a.$.b", "assets.$", "$.$", "$.a.$"):
        loc = ap.classify_validation_path(raw)
        assert loc["kind"] == ap.UNKNOWN, raw
        assert loc["label"] == ap.UNKNOWN_LOCATION_LABEL, raw
        # the exact string is still preserved for the disclosure
        assert loc["technical"] == raw, raw


def test_the_documented_injectivity_BOUND_is_the_one_that_actually_holds():
    """M2 — the docstrings now claim injectivity only over dot-joined locators whose
    segments contain neither `.` nor the separator glyph. These are the documented
    collisions; they are pinned so the narrowed claim stays true."""
    same_record = {ap.classify_validation_path(p)["label"] for p in ("$", "$.", "$..", "$ ")}
    assert same_record == {ap.RECORD_LEVEL_LABEL}
    separator_collision = {
        ap.classify_validation_path(p)["label"] for p in ("a → b", "a.b", "a..b")
    }
    assert separator_collision == {"a → b"}
    # …and injectivity DOES hold for the locator shapes official.py can emit
    emitted = ["$", "a", "a.b", "a.b.c", "assets.0.sha256", "sample.material.formula",
               "measurement.series.0.data_points.42.uncertainty.standard_error"]
    labels = [ap.classify_validation_path(p)["label"] for p in emitted]
    assert len(set(labels)) == len(labels)


# --- IMPORTANT-1: the validation-CRASH sentinel is not a validation issue ------


@pytest.mark.parametrize("case", UNAVAILABLE_CASES, ids=UNAVAILABLE_IDS)
def test_shared_unavailable_case_table(case):
    assert ap.is_validation_unavailable(case["errors"]) is case["unavailable"]


@pytest.mark.parametrize("errors", [None, "x", 7, {}, [None], [7], [{"message": 7}],
                                   [{"message": None}]])
def test_is_validation_unavailable_is_total(errors):
    assert ap.is_validation_unavailable(errors) is False


def test_the_sentinel_message_matches_the_literal_routes_py_still_emits():
    """The predicate is only honest while it matches the PRODUCER. `routes.py` is not
    this unit's file and is not edited — so its literal is asserted from here, and a
    future reword of that message fails this test instead of silently turning the
    crash back into "1 record-level validation issue"."""
    src = (REPO_ROOT / "apps" / "api" / "isaac_api" / "routes.py").read_text(encoding="utf-8")
    assert ap.VALIDATION_UNAVAILABLE_MESSAGE in src
    # both producers: post_validate (feeds the frontend composer) and the
    # assistant's own dry-run
    assert src.count(ap.VALIDATION_UNAVAILABLE_MESSAGE) >= 2


def test_without_the_predicate_the_sentinel_WOULD_read_as_a_validation_issue():
    """Documents exactly what IMPORTANT-1 was: run the sentinel through the locator
    formatter alone and the reader is told an issue was found."""
    sentinel = [{"path": "$", "message": ap.VALIDATION_UNAVAILABLE_MESSAGE}]
    misleading = ap.blocking_summary([e["path"] for e in sentinel])
    assert misleading == "1 record-level validation issue may be blocking export."
    # …which is why the predicate exists, and why callers must consult it FIRST
    assert ap.is_validation_unavailable(sentinel) is True


def test_the_unavailable_summary_claims_no_count_no_location_and_no_verdict():
    text = ap.VALIDATION_UNAVAILABLE_SUMMARY
    assert "$" not in text
    assert "validation issue" not in text
    assert "blocking export" not in text
    assert "could not be completed" in text
    assert aq.has_verdict_language(text) is False
    assert aq._is_unsafe_string(text) is False
    assert not re.search(r"\b\d+\b", text), "no count may be stated for a crash"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_every_summary_passes_the_verdict_guard(case):
    text = ap.blocking_summary(case["paths"])
    assert aq.has_verdict_language(text) is False
    # The summary is also emitted inside an answer body, so it must not trip the
    # path/secret scrub either (which would neutralize the whole answer).
    assert aq._is_unsafe_string(text) is False


# --- per-locator classification -----------------------------------------------


def test_bare_root_marker_is_a_record_level_location():
    assert ap.classify_validation_path("$") == {
        "kind": "record",
        "label": ap.RECORD_LEVEL_LABEL,
        "technical": "$",
    }
    assert "$" not in ap.RECORD_LEVEL_LABEL


def test_nested_locator_segments_are_verbatim_no_invented_field_name():
    loc = ap.classify_validation_path("sample.material.formula")
    assert loc["kind"] == "field"
    for segment in loc["label"].split(ap.SEGMENT_SEPARATOR):
        assert segment in "sample.material.formula".split(".")


def test_underscores_are_not_rewritten_so_distinct_locators_cannot_collapse():
    assert ap.classify_validation_path("a.standard_error")["label"] == "a → standard_error"
    assert ap.classify_validation_path("a.standard error")["label"] == "a → standard error"


@pytest.mark.parametrize("raw", [None, 7, 0, {}, [], "", "   ", True, 1.5, b"x"])
def test_absent_or_unusable_locator_claims_no_location(raw):
    assert ap.classify_validation_path(raw) == {
        "kind": "unknown",
        "label": ap.UNKNOWN_LOCATION_LABEL,
        "technical": ap.NO_PATH_TECHNICAL,
    }


def test_reported_locator_is_preserved_byte_for_byte():
    loc = ap.classify_validation_path("  sample.id  ")
    assert loc["technical"] == "  sample.id  "
    assert loc["label"] == "sample → id"


# --- summary counts + caps -----------------------------------------------------


def test_empty_locator_list_is_the_honest_empty_answer():
    assert ap.blocking_summary([]) == ap.NO_BLOCKING_ISSUES
    assert ap.blocking_summary(None) == ap.NO_BLOCKING_ISSUES


def test_stated_count_matches_the_locator_count_past_the_display_cap():
    many = ["a", "b", "c", "d", "e", "f", "g"]
    text = ap.blocking_summary(many)
    assert text.startswith("7 validation issues")
    assert "…and 4 more" in text
    assert len(ap.technical_paths(many)) == 7


def test_all_root_versus_any_non_root_wording():
    assert ap.blocking_summary(["$", "$", "$"]) == (
        "3 record-level validation issues may be blocking export."
    )
    assert ap.blocking_summary(["$", "$", "assets"]) == (
        "3 validation issues may be blocking export: the record itself, "
        "the record itself, assets."
    )


def test_summary_is_hedged_and_never_a_determination():
    text = ap.blocking_summary(["$", "assets.0.sha256"])
    assert "may be blocking export" in text
    assert "valid" not in text.lower().replace("validation", "")


# --- shared text helpers -------------------------------------------------------


def test_count_pluralizes_deterministically():
    assert ap.count(1, "validation issue") == "1 validation issue"
    assert ap.count(2, "validation issue") == "2 validation issues"
    assert ap.count(1, "evidence entry", "evidence entries") == "1 evidence entry"
    assert ap.count(3, "evidence entry", "evidence entries") == "3 evidence entries"
    assert ap.count(0, "field") == "0 fields"
    assert "(s)" not in ap.count(2, "field")


def test_join_capped_shows_three_and_reports_the_remainder():
    assert ap.join_capped([]) == ""
    assert ap.join_capped(["a"]) == "a"
    assert ap.join_capped(["a", "b", "c"]) == "a, b, c"
    assert ap.join_capped(["a", "b", "c", "d"]) == "a, b, c, …and 1 more"


def test_assistant_query_reuses_the_shared_helpers_rather_than_its_own_copies():
    """One implementation per language: the resolver's internal helper names are
    now bound to the shared module's functions."""
    assert aq._count is ap.count
    assert aq._join_capped is ap.join_capped


# --- import isolation ----------------------------------------------------------

_STDLIB_ROOTS = {
    "__future__", "logging", "re", "dataclasses", "typing", "json", "pathlib",
}

_FORBIDDEN_IMPORT_ROOTS = {"isaac_records", "graphify", "fastapi", "isaac_api"}


def _import_roots(module) -> set:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import within isaac_api
                roots.add(f".{node.module or ''}")
            elif node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_assistant_paths_imports_only_stdlib():
    """The formatter is a leaf: standard library only, no sibling coupling."""
    roots = _import_roots(ap)
    assert roots <= _STDLIB_ROOTS, f"non-stdlib imports: {roots - _STDLIB_ROOTS}"
    assert roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


def test_assistant_query_imports_only_stdlib_plus_the_formatter():
    """The resolver's docstring claims stdlib + exactly one sibling formatter. The
    truth core, graphify and fastapi remain absent."""
    roots = _import_roots(aq)
    allowed = _STDLIB_ROOTS | {".assistant_paths"}
    assert roots <= allowed, f"unexpected imports: {roots - allowed}"
    assert roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)
