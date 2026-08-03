"""Slice 2A — the BACKEND half of the whole-application-claim sweep guard.

WHY THIS EXISTS
---------------
Slice 2A gave the deployed pod a protected, read-only diagnostic
(``GET /api/runtime/database/recon``) over an isolated SLAC test database seeded
with production-derived ISAAC records. It returns sanitized aggregates only, no
per-record content, and it writes nothing. Krish's instruction on the copy that
followed was a single sentence:

    "Do not describe the entire application as simply `synthetic-only` without
    this qualification."

Eleven copy surfaces were corrected one at a time, and a per-copy-unit CI guard
was written to stop a twelfth — ``apps/web/src/__tests__/db-recon-truthfulness
.test.tsx`` §13-14. That guard scans FRONTEND sources only. It reads no backend
string at all, and it would not have caught the one that had already shipped:

    apps/api/isaac_api/app.py, OpenAPI ``info.summary``
    "Synthetic-only FastAPI wrapper over the deterministic isaac_records core."

Two independent gaps let that through, and this file closes both.

  (a) COVERAGE. Nothing scanned backend copy. Yet the OpenAPI document is served
      to users at ``GET /api/openapi`` and rendered in Settings → API
      Documentation, and the response-body ``message`` / ``reason`` constants in
      ``routes.py`` are shown verbatim by the frontend when a request is refused.

  (b) THE PATTERNS MISSED THE ADJECTIVAL SHAPE. "Synthetic-only <noun phrase>"
      used as a LABEL for the whole API matched none of the nine patterns: the
      closest one needs ``build|prototype|deployment|app|application`` within 40
      characters, and "FastAPI wrapper over the deterministic…" supplies none.
      A tenth pattern was added — to the TypeScript list, so both guards get it.

TWO GUARDS EXIST, AND NEITHER IMPLIES THE OTHER
-----------------------------------------------
================  ==========================================================
this file         the generated OpenAPI document (``info.summary``,
                  ``info.description``, every tag description, every operation
                  ``summary``/``description``) and every string literal in
                  ``apps/api/isaac_api/**/*.py`` — which is where the
                  response-body message constants live.
the TSX guard     the structured copy units of ``lib/settingsContent.ts`` and
                  every non-test ``.ts``/``.tsx`` under ``apps/web/src``.
================  ==========================================================

A green run here says nothing about frontend copy, and a green run there says
nothing about backend copy. Both must run.

THE RULES ARE SHARED, AND THE SHARING IS ENFORCED
--------------------------------------------------
A Vitest module and a pytest module cannot import each other, so
``FLAT_WHOLE_APP_CLAIM``, ``DIAGNOSTIC_CLAIMS``, ``QUALIFICATION`` and
``CAPABILITY_STATEMENT`` are written out twice. The duplication is not silent:
:func:`test_pattern_lists_are_identical_to_the_frontend_guard` parses the TSX
file and asserts both label lists and both pattern *sources* match
character-for-character. Adding a pattern to one guard and not the other fails
CI rather than quietly opening a gap. The patterns are deliberately written in
the common subset of JavaScript and Python regex syntax so the sources can be
compared as plain strings.

THE RULE ITSELF
---------------
A copy unit may not make a flat whole-application data claim UNLESS the same
unit also carries the qualification, and a unit that states the diagnostic
capability must state every one of its bounds. A claim is wrong when it is
*unqualified*, not when the words appear — so the guard encodes the pairing
rather than banning vocabulary.

WHAT THIS GUARD DOES **NOT** CATCH
----------------------------------
It is a RATCHET, not a detector for the claim class. What it reliably catches is
the set of shapes that have actually shipped — each pinned below as a retired
string that must keep failing — plus their near neighbours. Novel phrasings of
the same false claim pass it. These five were written by a reviewer and pass
both this guard and the frontend one, today:

    "This prototype only ever handles synthetic data."
    "No real records are read anywhere in this build."
    "This application never touches production records."
    "Nothing real is ever read by this deployment."
    "All data in this prototype is fabricated."

They are recorded as known gaps, NOT as targets. Patterns chasing them would
widen the net over honest mode-and-workspace copy — the whole reason the shipped
patterns are narrow on head noun, distance and sentence position — and would
leave the next reader believing the class is covered. An incomplete detector
that says so is worth more than one that looks complete.

A HUMAN REVIEWER REMAINS THE BACKSTOP for any newly written data claim. What CI
guarantees is only this: no retired string comes back, and no near-variant of a
shipped shape lands unqualified.

WHAT IS NOT SCANNED, AND WHY
----------------------------
Python docstrings. They are developer documentation, and several of them
correctly *discuss* the mode ("This module is the SINGLE source of truth for the
WORKSPACE data mode…"); reading them as user copy would make the guard cry wolf
in exactly the places the codebase is being most careful. The one case where a
docstring becomes user-visible — FastAPI promoting an endpoint docstring to an
operation description when ``description=`` is absent — is covered anyway,
because the OpenAPI scan reads the generated document rather than the source.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# --- locate the two source trees ---------------------------------------------

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
BACKEND_SRC = _REPO / "apps" / "api" / "isaac_api"
FRONTEND_GUARD = _REPO / "apps" / "web" / "src" / "__tests__" / "db-recon-truthfulness.test.tsx"


# --- the shared rules (mirrored from the TSX guard; parity is asserted) -------

#: Each entry is one way of claiming the whole application/build/deployment
#: takes only synthetic data, or that real data is out of scope for it.
FLAT_WHOLE_APP_CLAIM: tuple[tuple[str, str], ...] = (
    (
        "the build/deployment itself is synthetic-only",
        r"\b(this|the)\s+(build|prototype|deployment|app|application)\b[^.!?]{0,80}\bsynthetic[- ]only\b",
    ),
    (
        "synthetic-only used as a name for the build/deployment",
        r"\bsynthetic[- ]only\b[^.!?]{0,40}\b(build|prototype|deployment|app|application)\b",
    ),
    # The ADJECTIVAL shape, added by this backend sweep. See the TSX guard for
    # the full rationale; in short, it is narrow on three axes so the mode token
    # stays usable where it is honest — the token must open the unit or a
    # sentence, at most three words may intervene, and the head noun must denote
    # the SOFTWARE ITSELF (`workspace`, `mode` and `operation` are deliberately
    # absent from that noun list).
    (
        "synthetic-only as an adjectival label for the whole API/app",
        r"(?:^|[.!?]\s+)synthetic[- ]only\s+(?:[a-z0-9_]+\s+){0,3}"
        r"(api|service|server|backend|wrapper|application|app|prototype|build|deployment|tool|assistant|platform|system)\b",
    ),
    (
        'calling the whole thing "this synthetic <build>"',
        r"\bthis\s+synthetic\s+(build|prototype|deployment|app|application|preview)\b",
    ),
    ('"synthetic (demo) data only"', r"\bsynthetic\s+(demo\s+)?data\s+only\b"),
    (
        "real data out of scope for the build/deployment",
        r"out of scope for (this|the)\s+(prototype|build|deployment|app|application)",
    ),
    (
        "a claim about which data is in scope at all",
        r"\b(data|records?|artifacts?)\b[^.!?]{0,40}\b(is|are)\s+in\s+scope\b",
    ),
    ("a flat denial that any database exists", r"\bthere\s+is\s+no\s+database\b"),
    # The negative lookahead keeps the truthful "no database records are
    # displayed" out of the net: that is a claim about DISPLAY, not about a
    # database's existence.
    ('"no database" as a bare fact about the deployment', r"\bno\s+database\b(?!\s+records)"),
    (
        "no real experiment data, with no scope on it",
        r"\bno\s+real\s+(experiment|facility|scientific)?\s*data\b",
    ),
)

#: The bounds. A unit that states the capability must state all of them.
DIAGNOSTIC_CLAIMS: tuple[tuple[str, str], ...] = (
    ("the diagnostic MAY run — not that it is running", r"may run a protected, read-only diagnostic"),
    (
        "the database is an isolated test database of production-derived records",
        r"isolated SLAC test database containing production-derived records",
    ),
    ("records are processed transiently in pod memory", r"transiently in pod memory"),
    ("only sanitized aggregate results are returned", r"sanitized aggregate results are returned"),
    ("no record is modified", r"no record is modified"),
    ("nothing is sent to any model", r"nothing is sent to any model"),
    (
        "database-backed record display is closed pending a decision",
        r"(record display|display) remains disabled pending an explicit visibility decision",
    ),
)

#: The marker that a unit states the diagnostic rather than promising it away.
QUALIFICATION = r"protected,\s*read-only[^.!?]{0,40}diagnostic"

#: The capability statement. A unit that makes it must state every bound.
CAPABILITY_STATEMENT = r"may run a protected, read-only diagnostic"

_FLAT = tuple((label, re.compile(src, re.I)) for label, src in FLAT_WHOLE_APP_CLAIM)
_DIAG = tuple((label, re.compile(src, re.I)) for label, src in DIAGNOSTIC_CLAIMS)
_QUAL = re.compile(QUALIFICATION, re.I)
_CAP = re.compile(CAPABILITY_STATEMENT, re.I)


def _normalize(text: str) -> str:
    """Read prose the way it is rendered, not the way the source wraps it.

    Backend copy is assembled from implicitly concatenated literals and carries
    ``\\n\\n`` paragraph breaks, so a clause that reads as one sentence to a user
    spans several physical pieces. Without this the multi-clause patterns miss
    real defects and the bounds check raises false alarms.
    """
    return re.sub(r"\s+", " ", text).strip()


# --- the ALLOWLIST ------------------------------------------------------------
#
# Each entry exempts ONE pattern for ONE sentence, never a whole file and never a
# whole pattern.
#
# HOW THE EXEMPTION IS SCOPED, precisely. An earlier version of this comment
# claimed an entry "cannot launder a different claim that happens to trip the
# same pattern", while `_allowed` tested only `fragment in text` — so the mere
# PRESENCE of an exempted sentence anywhere in a copy unit silenced that pattern
# for the ENTIRE unit. It laundered exactly what the comment said it could not:
#
#     "Available only while the deployment is in synthetic-only data mode.
#      This prototype is synthetic-only and never reads anything else."
#
# passed, because sentence one is allowlisted. Both sentences are pinned as
# regression cases in `test_an_allowlisted_sentence_does_not_launder_its_neighbour`.
#
# What the code now does: a pattern is exempt for a unit only when EVERY match of
# that pattern in the unit falls WHOLLY INSIDE an allowlisted fragment for that
# same pattern. One match outside — a second sentence, a longer clause the
# fragment does not cover — and the unit is flagged. Containment is used rather
# than excising the fragment and re-scanning, because excision splices the text
# on either side of the removed sentence together and can manufacture a match
# (or a sentence boundary) that the copy never contained.
#
# `test_every_allowlist_entry_is_still_needed` fails if an entry stops matching
# anything, so a stale exemption cannot sit here unnoticed.

ALLOWED: tuple[tuple[str, str, str], ...] = (
    # --- runtime-MODE statements, by the mode's proper name ------------------
    # The distinction this whole sweep rests on is mode vs. contents: the app
    # enforces a runtime mode, and cannot inspect what it is handed. Naming that
    # mode is therefore a claim the app can keep, and the frontend keeps it on
    # purpose too (Help: "configured for synthetic-only operation"). Pattern 1
    # cannot tell "the deployment is in synthetic-only data mode" apart from
    # "the deployment is synthetic-only", and tightening it to try would stop it
    # catching the retired settings card, which is pinned below. So these three
    # sentences are exempted individually instead.
    (
        "the build/deployment itself is synthetic-only",
        "Available only while the deployment is in synthetic-only data mode.",
        "A gate condition on ONE operation, naming the runtime mode. It makes no "
        "claim about what data the deployment as a whole touches, and it is true: "
        "the CSV preview really is refused outside synthetic-only mode.",
    ),
    (
        "the build/deployment itself is synthetic-only",
        "Refused because the deployment is not in synthetic-only data mode.",
        "The 403 description on the reset operation — a NEGATED mode statement "
        "describing when the refusal fires. It asserts nothing about the data "
        "regime; it is the condition under which the operation declines.",
    ),
    (
        "the build/deployment itself is synthetic-only",
        "The deployment is not in synthetic-only data mode, so this preview path is refused.",
        "The 403 description on the CSV preview operation. Same negated mode "
        "statement as the entry above, for the other mode-gated operation.",
    ),
    # --- a conditional, not a denial -----------------------------------------
    (
        '"no database" as a bare fact about the deployment',
        "When the deployment has no database configured, the operation reports that and connects to nothing.",
        "Not a denial that a database exists — it is the documented behaviour of "
        "the recon operation in the branch where PGHOST is absent, and it is the "
        "sentence that stops a reader assuming the endpoint always connects. The "
        "same description names the isolated test database at length elsewhere.",
    ),
)


def _exempt_spans(label: str, text: str) -> list[tuple[int, int]]:
    """Character ranges of every allowlisted fragment for ``label`` in ``text``."""
    spans: list[tuple[int, int]] = []
    for lab, frag, _why in ALLOWED:
        if lab != label:
            continue
        start = text.find(frag)
        while start != -1:
            spans.append((start, start + len(frag)))
            start = text.find(frag, start + 1)
    return spans


def _allowed(label: str, text: str, spans: list[tuple[int, int]]) -> bool:
    """True only if EVERY match of ``label``'s pattern sits inside an exemption.

    See the allowlist comment above: presence of an exempted sentence is not
    enough — a second, unexempted match of the same pattern elsewhere in the
    unit still flags it.
    """
    exempt = _exempt_spans(label, text)
    if not exempt:
        return False
    return all(any(lo <= start and end <= hi for lo, hi in exempt) for start, end in spans)


def unqualified_claims(text: str) -> list[str]:
    """Flat whole-application claims in ``text`` that nothing in it qualifies."""
    norm = _normalize(text)
    if _QUAL.search(norm):
        return []
    flagged: list[str] = []
    for label, pat in _FLAT:
        spans = [match.span() for match in pat.finditer(norm)]
        if spans and not _allowed(label, norm, spans):
            flagged.append(label)
    return flagged


def missing_bounds(text: str) -> list[str]:
    """Bounds a unit owes because it states the capability, and does not state."""
    norm = _normalize(text)
    if not _CAP.search(norm):
        return []
    return [label for label, pat in _DIAG if not pat.search(norm)]


# --- unit collection: (a) the generated OpenAPI document ----------------------


@pytest.fixture(scope="module")
def openapi_document(tmp_path_factory) -> dict:
    """The REAL generated document, not a mirror of it.

    Mirroring backend strings into a fixture is precisely what made these strings
    expensive to correct — eleven surfaces, five rounds. Generating the document
    means a new operation is covered the day it is written.
    """
    import os

    ws = tmp_path_factory.mktemp("ws")
    old = {k: os.environ.get(k) for k in ("ISAAC_UI_WORKSPACE", "ISAAC_BASE_PATH", "ISAAC_UI_API_KEY")}
    os.environ["ISAAC_UI_WORKSPACE"] = str(ws)
    os.environ.pop("ISAAC_BASE_PATH", None)
    os.environ.pop("ISAAC_UI_API_KEY", None)
    try:
        from isaac_api.app import create_app

        return create_app().openapi()
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _openapi_units(spec: dict) -> list[tuple[str, str]]:
    units: list[tuple[str, str]] = []
    info = spec.get("info", {})
    for key in ("summary", "description"):
        if info.get(key):
            units.append((f"openapi info.{key}", info[key]))
    for tag in spec.get("tags") or []:
        if tag.get("description"):
            units.append((f"openapi tag {tag['name']}.description", tag["description"]))
    for path, item in sorted(spec.get("paths", {}).items()):
        for method, op in sorted(item.items()):
            if not isinstance(op, dict):
                continue
            for key in ("summary", "description"):
                if op.get(key):
                    units.append((f"{method.upper()} {path} .{key}", op[key]))
    return units


# --- unit collection: (b) every string literal in the backend source ----------


def _backend_files() -> list[Path]:
    return sorted(p for p in BACKEND_SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _literal_units(path: Path) -> list[tuple[str, str]]:
    """Every non-docstring string literal of three or more words, with its line.

    AST rather than a regex sweep of the file, for two reasons the TSX guard has
    to work around: comments are simply not nodes, so a note recording a RETIRED
    string (``routes.py`` has several) can never be read as the defect; and
    implicitly concatenated literals — how every long backend message is written
    — arrive already joined into one node, which is the granularity a reader
    experiences.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

    rel = path.relative_to(_REPO).as_posix()
    units: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        value: str | None = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            value = node.value
        elif isinstance(node, ast.JoinedStr):
            # An f-string: scan the literal parts. The interpolated values are
            # ids, counts and limits, never prose.
            value = "".join(
                part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
        if value is None or len(value.split()) < 3:
            continue
        units.append((f"{rel}:{node.lineno}", value))
    return units


def _all_literal_units() -> list[tuple[str, str]]:
    units: list[tuple[str, str]] = []
    for path in _backend_files():
        units.extend(_literal_units(path))
    return units


_LITERAL_UNITS = _all_literal_units()


# --- 1. the scan reaches what it claims to reach ------------------------------


def test_openapi_scan_covers_the_document_level_copy(openapi_document):
    units = dict(_openapi_units(openapi_document))
    assert "openapi info.summary" in units
    assert "openapi info.description" in units
    # Not a handful of hand-picked operations: the whole surface.
    operations = [w for w in units if w.startswith(("GET ", "POST "))]
    assert len(operations) > 60, f"only {len(operations)} operation copy units — did the scan break?"
    for expected in (
        "GET /api/health .description",
        "GET /api/runtime/database/recon .description",
        "POST /api/uploads .description",
        "GET /api/experiments/{experiment_id}/source-preview .description",
    ):
        assert expected in units


def test_literal_scan_covers_the_response_body_message_constants():
    """The scan is a SUPERSET of the user-facing message constants, not a list.

    Listing them would be the mirror-maintenance trap again, so the scan takes
    every literal and this test proves the known ones are inside it. Each
    fragment below is returned in a response body and rendered by the frontend.
    """
    corpus = [_normalize(text) for _where, text in _LITERAL_UNITS]
    for fragment in (
        # _UPLOAD_BLOCKED["reason"] — the 403 body of POST /api/uploads
        "Real or private data upload is approval-gated and not enabled in this workspace.",
        # the source_not_allowed 404 body
        "Only the two committed reference files may be previewed.",
        # a representative spread of the other response-body messages
        "Path traversal rejected — pass a bare filename.",
        "CSV preview is available only in synthetic-only mode.",
        "Nothing exported yet — export this experiment before auditing.",
        "confirmed_by_user must be true to apply answers.",
        "The body must be a JSON object (a candidate ISAAC record).",
        "A non-empty question is required.",
        # MEMORY_NOTE, attached to every memory-plane response
        "Project memory returns leads to verify — never a validation verdict.",
        # a _DB_RECON_LIMITATIONS entry, returned inside every recon report shape
        "This operation returns AGGREGATES ONLY.",
    ):
        assert any(fragment in text for text in corpus), f"not scanned: {fragment}"


def test_literal_scan_covers_every_backend_module():
    scanned = {where.rsplit(":", 1)[0] for where, _ in _LITERAL_UNITS}
    for expected in (
        "apps/api/isaac_api/routes.py",
        "apps/api/isaac_api/app.py",
        "apps/api/isaac_api/db_recon.py",
        "apps/api/isaac_api/runtime_mode.py",
    ):
        assert expected in scanned


# --- 2. the guard proper ------------------------------------------------------


def test_openapi_units_make_no_unqualified_whole_application_claim(openapi_document):
    offenders = [
        f"{where}: {', '.join(flagged)}"
        for where, text in _openapi_units(openapi_document)
        if (flagged := unqualified_claims(text))
    ]
    assert offenders == []


def test_openapi_units_state_every_bound_if_they_state_the_capability(openapi_document):
    offenders = [
        f"{where}: missing {', '.join(missing)}"
        for where, text in _openapi_units(openapi_document)
        if (missing := missing_bounds(text))
    ]
    assert offenders == []


def test_backend_literals_make_no_unqualified_whole_application_claim():
    offenders = [
        f"{where}: {', '.join(flagged)} >>> {_normalize(text)[:120]}"
        for where, text in _LITERAL_UNITS
        if (flagged := unqualified_claims(text))
    ]
    assert offenders == []


def test_backend_literals_state_every_bound_if_they_state_the_capability():
    offenders = [
        f"{where}: missing {', '.join(missing)}"
        for where, text in _LITERAL_UNITS
        if (missing := missing_bounds(text))
    ]
    assert offenders == []


def test_the_api_description_that_states_the_capability_really_states_the_bounds(openapi_document):
    """Not a tautology of the test above: it proves the bounds check has teeth.

    ``info.description`` is the one backend unit that states the capability, so
    if the bounds check were broken — a mistyped pattern, a normalizer that ate
    the paragraph — the two ``missing_bounds`` tests above would pass vacuously.
    """
    description = openapi_document["info"]["description"]
    assert _CAP.search(_normalize(description)), "info.description no longer states the capability"
    assert missing_bounds(description) == []


# --- 3. the guard is proven on the strings it was written for -----------------

#: ``apps/api/isaac_api/app.py`` OpenAPI ``info.summary`` before this sweep.
#: RETIRED — a fixture, not copy. Do not "fix" it; it must keep failing.
RETIRED_APP_SUMMARY = "Synthetic-only FastAPI wrapper over the deterministic isaac_records core."

#: ``routes.py`` ``_UPLOAD_BLOCKED["reason"]`` before this sweep.
#: RETIRED — a fixture, not copy. Do not "fix" it; it must keep failing.
RETIRED_UPLOAD_BLOCKED = (
    "Real or private data upload is approval-gated and not enabled in this synthetic prototype."
)

#: ``routes.py`` the ``source_not_allowed`` 404 message before this sweep.
#: RETIRED — a fixture, not copy. Do not "fix" it; it must keep failing.
RETIRED_SOURCE_NOT_ALLOWED = (
    "Only the two committed synthetic fixtures may be previewed in this synthetic prototype."
)


@pytest.mark.parametrize(
    ("what", "retired"),
    [
        ("the OpenAPI info.summary", RETIRED_APP_SUMMARY),
        ("the upload-refusal reason", RETIRED_UPLOAD_BLOCKED),
        ("the source-preview refusal message", RETIRED_SOURCE_NOT_ALLOWED),
    ],
)
def test_guard_flags_every_retired_backend_string(what, retired):
    assert unqualified_claims(retired), f"{what} is no longer flagged"


def test_the_new_adjectival_pattern_is_the_only_one_that_sees_the_openapi_summary():
    """The whole reason a tenth pattern exists: the other nine miss this shape."""
    assert unqualified_claims(RETIRED_APP_SUMMARY) == [
        "synthetic-only as an adjectival label for the whole API/app"
    ]


def test_the_two_prototype_labelled_strings_are_flagged_for_their_label():
    for retired in (RETIRED_UPLOAD_BLOCKED, RETIRED_SOURCE_NOT_ALLOWED):
        assert 'calling the whole thing "this synthetic <build>"' in unqualified_claims(retired)


@pytest.mark.parametrize(
    "truthful",
    [
        # What actually shipped in app.py: the token is scoped to the workspace
        # and the diagnostic is named in the same breath.
        "FastAPI wrapper over the deterministic isaac_records core: a synthetic-only "
        "example workspace plus one read-only, aggregate-only database diagnostic.",
        # The two corrected message constants.
        "Real or private data upload is approval-gated and not enabled in this workspace.",
        "Only the two committed reference files may be previewed.",
        # Runtime-MODE statements, which the project keeps on purpose.
        "CSV preview is available only in synthetic-only mode.",
        "Synthetic-only mode — file upload is refused outright.",
        # apps/web/src/screens/LoadMaterials.tsx:120, reviewed and found NOT a
        # defect: it makes no data-regime claim, and "build" is a neutral label
        # for the thing the affordance is disabled in. Pinned here as well as in
        # the TSX guard because the adjectival pattern added by this file is the
        # one that could plausibly have over-reached onto it.
        "not enabled in this build",
    ],
)
def test_guard_leaves_truthful_backend_copy_alone(truthful):
    assert unqualified_claims(truthful) == []


def test_a_half_qualification_cannot_silence_the_guard():
    repaired = (
        RETIRED_APP_SUMMARY + " This deployment may run a protected, read-only diagnostic."
    )
    assert unqualified_claims(repaired) == []
    # ...and the pairing rule immediately demands the rest of the bounds.
    assert missing_bounds(repaired)


def test_every_allowlist_entry_is_still_needed():
    """No stale exemptions: each entry must exempt a real, currently-present flag.

    An allowlist that outlives the string it was written for is how a guard
    rots — the next over-claim lands on an exemption nobody re-read.
    """
    corpus = [_normalize(text) for _where, text in _LITERAL_UNITS]
    for label, fragment, why in ALLOWED:
        assert why.strip(), f"allowlist entry {fragment!r} has no justification"
        hosts = [text for text in corpus if fragment in text]
        assert hosts, f"allowlist entry no longer matches any backend copy: {fragment!r}"
        pattern = dict(_FLAT)[label]
        assert any(pattern.search(text) for text in hosts), (
            f"allowlist entry for {label!r} is unnecessary — {fragment!r} no longer trips it"
        )


def test_every_allowlisted_sentence_is_exempt_on_its_own():
    """The four legitimate exemptions still pass, judged as isolated units.

    This is the other half of the containment rule: an entry is only usable if
    the pattern's match really does fall inside the fragment. If a fragment were
    ever shortened so the match ran past its end, the entry would silently stop
    exempting anything and the honest copy it protects would start failing CI —
    here, rather than in whichever module happens to contain it.
    """
    for label, fragment, _why in ALLOWED:
        pattern = dict(_FLAT)[label]
        assert pattern.search(fragment), (
            f"{fragment!r} no longer trips {label!r} — the entry exempts nothing"
        )
        assert unqualified_claims(fragment) == [], fragment


def test_an_allowlisted_sentence_does_not_launder_its_neighbour():
    """I-1 regression: presence of an exemption must not clear the whole unit.

    Both strings are the reviewer's working bypasses of the previous
    ``fragment in text`` test. Each is an allowlisted sentence followed by a
    genuine unqualified whole-application claim that trips the SAME pattern, and
    each returned ``[]`` before the containment rule replaced the presence test.
    """
    laundered_mode_claim = (
        "Available only while the deployment is in synthetic-only data mode. "
        "This prototype is synthetic-only and never reads anything else."
    )
    assert "the build/deployment itself is synthetic-only" in unqualified_claims(
        laundered_mode_claim
    )

    laundered_no_database_claim = (
        "When the deployment has no database configured, the operation reports that and "
        "connects to nothing. This deployment has no database at all."
    )
    assert '"no database" as a bare fact about the deployment' in unqualified_claims(
        laundered_no_database_claim
    )


def test_a_second_copy_of_an_allowlisted_sentence_is_still_exempt():
    """Containment is per MATCH, not per unit — repetition is not an over-claim.

    Guards against the opposite failure: scoring the exemption once and flagging
    every later occurrence would make honest copy fail as soon as two operations
    documented the same gate condition, which two of the entries below already
    do in ``routes.py``.
    """
    twice = (
        "Refused because the deployment is not in synthetic-only data mode. "
        "The deployment is not in synthetic-only data mode, so this preview path is refused."
    )
    assert unqualified_claims(twice) == []


# --- 4. the two guards cannot drift apart -------------------------------------

_TS_BLOCK = re.compile(r"^const (\w+): \[string, RegExp\]\[\] = \[$(.*?)^\];$", re.M | re.S)
_TS_TOKEN = re.compile(r"'((?:[^'\\]|\\.)*)'" r"|/((?:[^/\\\n\[]|\\.|\[(?:[^\]\\]|\\.)*\])+)/[a-z]*")


def _parse_ts_pairs(name: str) -> list[tuple[str, str]]:
    source = FRONTEND_GUARD.read_text(encoding="utf-8")
    match = next((m for m in _TS_BLOCK.finditer(source) if m.group(1) == name), None)
    assert match is not None, f"cannot find `const {name}` in {FRONTEND_GUARD}"
    body = "\n".join(
        line for line in match.group(2).splitlines() if not line.strip().startswith("//")
    )
    pairs: list[tuple[str, str]] = []
    pending: str | None = None
    for token in _TS_TOKEN.finditer(body):
        if token.group(1) is not None:
            pending = token.group(1).replace("\\'", "'")
        else:
            assert pending is not None, f"regex without a label in {name}"
            pairs.append((pending, token.group(2)))
            pending = None
    assert pending is None, f"trailing label without a regex in {name}"
    return pairs


@pytest.mark.parametrize(
    ("name", "mine"),
    [("FLAT_WHOLE_APP_CLAIM", FLAT_WHOLE_APP_CLAIM), ("DIAGNOSTIC_CLAIMS", DIAGNOSTIC_CLAIMS)],
)
def test_pattern_lists_are_identical_to_the_frontend_guard(name, mine):
    """The duplication is declared, so it must also be enforced.

    Labels AND pattern sources, in order. If this fails, a rule was changed in
    one guard only — fix both, do not relax this test.
    """
    theirs = _parse_ts_pairs(name)
    assert theirs, f"{name} parsed as empty — the TSX guard's shape changed"
    assert [label for label, _ in theirs] == [label for label, _ in mine]
    assert [pattern for _, pattern in theirs] == [pattern for _, pattern in mine]


def test_the_scalar_patterns_match_the_frontend_guard():
    source = FRONTEND_GUARD.read_text(encoding="utf-8")
    for name, mine in (
        ("QUALIFICATION", QUALIFICATION),
        ("CAPABILITY_STATEMENT", CAPABILITY_STATEMENT),
    ):
        match = re.search(rf"^const {name} = /(.+)/[a-z]*;$", source, re.M)
        assert match is not None, f"cannot find `const {name}` in {FRONTEND_GUARD}"
        assert match.group(1) == mine


def test_the_frontend_guard_still_exists_and_still_says_so():
    """A cross-reference nobody checks is a comment. This one is checked."""
    assert FRONTEND_GUARD.exists()
    source = FRONTEND_GUARD.read_text(encoding="utf-8")
    assert "apps/api/tests/test_backend_copy_truthfulness.py" in source, (
        "the frontend guard no longer points at this file — a reader there would "
        "assume its green run covers the backend, which it does not"
    )
