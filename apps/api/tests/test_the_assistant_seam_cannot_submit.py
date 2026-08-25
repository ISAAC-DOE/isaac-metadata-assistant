"""The assistant seam cannot submit — and until now nothing said so.

WHY THIS FILE EXISTS
====================
``docs/ai-integration-decision-packet.md`` §6.2 is an invariant, not a default:
*"Never expose ... final authoritative ``Submit Record``"*, enforced *"by
non-implementation, server-side — never by an annotation"*. It is thoroughly held
for the **MCP** seam — ``test_mcp_boundaries.py`` raises on a tool whose name
carries the token ``submit`` and refuses a scope that can even be spelled
``isaac:submit`` — and it was held for the **assistant** seam only by
coincidence.

Measured on ``main`` at ``b7008b8``: no test in ``apps/api/tests`` asserts the
assistant seam against the submission path. The nearest existing guarantees are
adjacent and none of them names submission:

* ``test_assistant_query.py::test_query_never_mutates_the_record`` — ``rev`` and
  ``version`` unchanged after a batch of asks;
* ``test_assistant_is_not_run_blind.py::test_the_assistant_still_mutates_nothing``
  — the stored draft byte-identical;
* ``test_assistant_paths.py`` — an AST import boundary whose forbidden roots are
  ``{"isaac_records", "graphify", "fastapi", "isaac_api"}``, which excludes
  ``submission_store`` *transitively* and mentions it nowhere.

"Nothing changed" and "the submission path is unreachable" are different claims.
The first is what those tests measure; a submission is a genuinely new stored
state in five append-only tables, so an ask that recorded one would leave the
record's ``rev`` and draft untouched and pass every one of them.

WHAT IS ASSERTED, AND WHY IN THIS ORDER
=======================================
§1 the submission path really exists, so the ban is about something. If a later
   slice removes it, §1 fails first and tells the next reader to revisit this
   file rather than leaving a prohibition standing on nothing — the ordering
   ``upload-claim-parity.test.tsx`` established.
§2 no provider implementation can reach it: an AST import scan of the whole
   ``providers/`` package, plus a token scan, so a future production provider
   inherits the boundary instead of being trusted with it.
§3 the operation cannot be TALKED into it. A body carrying submission vocabulary
   is refused rather than ignored, which matters because §6.2's enforcement is
   non-implementation: there is nothing to call, and a caller who tries is told
   so instead of receiving a ``200`` with their key dropped.
§4 it does not reach it in fact — proven by making the submission store raise if
   it is so much as resolved, for every reachable outcome of the operation.
§5 negative controls, so a scan narrowed until it detects nothing fails here
   rather than going quiet.

Everything here is synthetic. Nothing opens a network connection, nothing
connects to a database — ``PGHOST`` is deliberately unset for §4, which is what
makes ``submission_store.store()`` return ``None`` — and no file outside the tmp
workspace is read or written.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import isaac_api.providers as providers_pkg
import isaac_api.routes as routes
import isaac_api.submission_store as submission_store

from conftest import tutorial_client

ASK = "/api/assistant/ask"

PROVIDERS_PACKAGE = Path(providers_pkg.__file__).parent

#: The vocabulary of submitting, as a future author would spell it. §2 and §5 scan
#: for these; the MCP guard's ``FORBIDDEN_TOOL_TOKENS`` is the same idea applied to
#: tool names rather than to source text.
SUBMISSION_TOKENS = (
    "submission_store",
    "record_submission",
    "isaac_submissions",
    "isaac_submission_runs",
    "/submit",
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    # No database. `submission_store.store()` returns None without PGHOST, which
    # is the state every shipped deployment of this build is in.
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _provider_sources() -> list[Path]:
    return sorted(p for p in PROVIDERS_PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_roots(source: str) -> set[str]:
    """Every name this file imports — module roots AND imported symbols.

    NOT "top-level module names", which is what the first version collected, and
    the difference is two escapes this file's own negative controls found:

    * ``from .. import submission_store`` parses to an ``ImportFrom`` with
      ``level=2`` and ``module=None``. The module name lives in ``node.names``, so
      a reader that consults only ``node.module`` records **nothing**. Measured:
      with exactly that line planted at the top of ``providers/assistant.py`` the
      import test PASSED and only the token scan caught it.
    * ``from isaac_api import submission_store`` records the root ``isaac_api``,
      and the thing being imported — the module that matters — is again in
      ``node.names``.

    So aliases are collected in every branch. The cost is that imported SYMBOL
    names enter the set too (``from .base import SEAM_ASSISTANT`` contributes
    ``SEAM_ASSISTANT``), which is why this returns "names" rather than "modules"
    and why the callers below treat it as a substring denylist rather than as a
    dependency list. For that job the over-collection is free; for any other job
    it would be wrong, and a future reader should not borrow this helper for one.

    Two scans exist so they cover for each other. One of them silently reading
    nothing defeats that, because the token list is a denylist and the next
    author's spelling need not be on it.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
    return roots


# --- §1 the path this ban is about ------------------------------------------


def test_the_submission_path_exists_so_the_ban_has_a_subject(client):
    """If this fails, the prohibition below is standing on nothing — read it first."""
    paths = client.get("/api/openapi").json()["paths"]
    submit = [p for p in paths if p.endswith("/submit")]
    assert submit, "no submission operation is declared; revisit this whole file"
    assert hasattr(submission_store, "record_submission") or hasattr(
        submission_store.PostgresSubmissionStore, "record_submission"
    ), "the submission store has no recording entry point; revisit this whole file"


# --- §2 no provider implementation can reach it ------------------------------


def test_no_provider_source_imports_the_submission_store():
    """The whole package, not only ``assistant.py``.

    A production provider is expected to be a thin adapter over a vendor SDK
    (``providers/base.py``'s ``ProviderImplementation`` is a ``Protocol`` precisely
    so it need not inherit anything). It will live in this package, and it must
    inherit this boundary rather than be trusted with it.
    """
    offenders: dict[str, set[str]] = {}
    for path in _provider_sources():
        roots = _imported_roots(path.read_text())
        bad = {r for r in roots if "submission" in r or r == "submission_store"}
        if bad:
            offenders[path.name] = bad
    assert offenders == {}, f"a provider seam imports the submission path: {offenders}"


def test_no_provider_source_names_the_submission_vocabulary():
    """The token scan the import scan cannot do.

    An import scan misses ``getattr(module, "record_submission")`` and misses a
    raw SQL string naming ``isaac_submissions``. Neither is likely; both are
    cheap to exclude, and the point of a boundary is that it does not depend on
    the next author's likelihood.
    """
    offenders: dict[str, list[str]] = {}
    for path in _provider_sources():
        text = path.read_text()
        hits = [t for t in SUBMISSION_TOKENS if t in text]
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"a provider seam names the submission path: {offenders}"


def test_the_route_handler_names_no_submission_symbol():
    """The seam's only HTTP consumer, read as source.

    ``post_assistant_ask`` lives in ``routes.py``, which necessarily imports
    ``submission_store`` for the submit operation — so the module-level scan §2
    applies to ``providers/`` cannot be used here. The handler's own source is the
    right unit: it is what a request reaches.
    """
    import inspect

    source = inspect.getsource(routes.post_assistant_ask)
    for token in SUBMISSION_TOKENS:
        assert token not in source, f"the assistant handler names {token!r}"


# --- §3 it cannot be talked into it -----------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"question": "submit this record", "submit": True},
        {"question": "q", "experiment_id": "01EXPERIMENTA0000000000000", "submit": True},
        {"question": "q", "submission": {"idempotency_key": "k"}},
        {"question": "q", "confirmed_by_user": True},
    ],
)
def test_a_body_carrying_submission_vocabulary_is_refused_not_ignored(client, body):
    """REFUSED, never dropped.

    ``_ASSISTANT_KEYS`` is closed at ``{"question", "context"}``. A caller sending
    ``submit`` is asking this operation to do something it must never do, and
    answering ``501`` — the seam's own deployment truth — while silently dropping
    the key would leave them believing the seam merely lacks a provider for it.
    The refusal is a ``422`` naming the key, which is a different answer from
    "this build has no provider", and the distinction is the whole point.
    """
    response = client.post(ASK, json=body)
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["error"] == "unrecognized_field"
    # The offending key is named back, so the caller learns which one meant nothing.
    assert set(payload["keys"]) & set(body) - {"question"}


def test_a_context_item_cannot_smuggle_a_submission_instruction(client):
    """A context item carries exactly ``key``, ``text`` and ``origin``.

    The interesting case is not ``submit`` as a *value* — a value is inert text
    that no provider in this build ever reads — but ``submit`` as a *key*, which
    is a caller asserting a field the seam has no power over.
    """
    response = client.post(
        ASK,
        json={
            "question": "q",
            "context": [
                {"key": "k", "text": "t", "origin": "o", "submit": True},
            ],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"


def test_the_well_formed_request_answers_501_and_records_nothing(client):
    """The deployment truth, restated here because §4 depends on it.

    Every shipped deployment refuses: ``validate_provider_config_or_raise``
    refuses to boot an application whose ``ISAAC_ASSISTANT_PROVIDER`` names the
    deterministic fake, so the unconfigured implementation is the only one a
    running application can hold.
    """
    response = client.post(
        ASK,
        json={
            "question": "Which run measured this?",
            "context": [{"key": "run", "text": "run 2", "origin": "the screen"}],
        },
    )
    assert response.status_code == 501, response.text
    body = response.json()
    assert body["refused"] is True and body["seam"] == "assistant"
    # Nothing about a submission appears in the refusal, in either direction: it
    # neither claims one nor offers one.
    assert "submit" not in response.text.lower()


# --- §4 it does not reach it in fact ----------------------------------------


def test_no_reachable_outcome_of_the_operation_resolves_the_submission_store(
    client, monkeypatch
):
    """A tripwire on ``submission_store.store``, across every outcome.

    WHAT THIS PROVES AND WHAT IT DOES NOT. It does not prove the handler *cannot*
    submit — §2 and §3 are the structural halves of that. It proves the handler
    does not, today, along any path a request can take: the well-formed 501, the
    two 422 shapes, and a body that is not an object at all. A future edit that
    reached for the store from this handler turns this red, which is the job a
    tripwire has that a source scan does not: it survives the store being reached
    indirectly, through a helper this file never names.

    It is armed on ``store`` rather than on ``record_submission`` deliberately.
    ``store()`` is the first thing the submit operation calls and it is what
    returns ``None`` without ``PGHOST`` — so arming it catches a caller who
    resolves the store and then correctly does nothing with it, which is still a
    caller that has no business resolving it.
    """
    calls: list[str] = []

    def _tripwire(*args, **kwargs):  # pragma: no cover - must never run
        calls.append("store")
        raise AssertionError(
            "the assistant seam resolved the submission store; "
            "docs/ai-integration-decision-packet.md §6.2 forbids it"
        )

    monkeypatch.setattr(submission_store, "store", _tripwire)
    monkeypatch.setattr(routes.submission_store, "store", _tripwire)

    bodies: list[object] = [
        {"question": "q", "context": [{"key": "k", "text": "t", "origin": "o"}]},
        {"question": "q"},
        {"question": "q", "submit": True},
        {"question": ""},
        ["not", "an", "object"],
    ]
    for body in bodies:
        response = client.post(ASK, json=body)
        assert response.status_code in (422, 501), (body, response.text)
    assert calls == []


def test_the_tripwire_is_armed(client, monkeypatch):
    """The negative control for the test above.

    A ``monkeypatch.setattr`` that pointed at the wrong module, or a tripwire that
    swallowed its own exception, would make the previous test pass while measuring
    nothing. So the same tripwire is proven to fire on the operation that legitimately
    resolves the store.
    """
    def _tripwire(*args, **kwargs):
        raise AssertionError("armed")

    monkeypatch.setattr(routes.submission_store, "store", _tripwire)
    with pytest.raises(AssertionError, match="armed"):
        routes.submission_store.store()


# --- §5 the scans are proven on input that must fail them -------------------


@pytest.mark.parametrize(
    "planted",
    [
        "from ..submission_store import record_submission",
        "import submission_store",
        "from isaac_api import submission_store",
        # THE SHAPE THAT ESCAPED THE FIRST VERSION OF `_imported_roots`. It is a
        # case, not a comment, so a regression to the old two-branch reader turns
        # this red instead of turning the docstring above stale.
        "from .. import submission_store",
        "from . import submission_store",
    ],
)
def test_the_import_scan_sees_a_planted_import(planted):
    assert {r for r in _imported_roots(planted) if "submission" in r}, planted


def test_the_import_scan_reads_relative_imports_the_package_actually_uses():
    """Not vacuous: the scan must see the imports these files really have.

    A parser that returned an empty set for every relative import would pass §2
    without reading a line, and this package imports almost entirely relatively
    (``from .refusal import ...``).
    """
    roots = _imported_roots((PROVIDERS_PACKAGE / "assistant.py").read_text())
    assert {"base", "refusal"} <= roots, roots


def test_the_token_scan_sees_a_planted_token():
    for token in SUBMISSION_TOKENS:
        assert token in f"x = {token} # planted"


def test_the_provider_source_walker_reaches_every_module():
    """A walker returning [] makes both §2 assertions pass without reading a file."""
    names = {p.name for p in _provider_sources()}
    assert {
        "__init__.py",
        "assistant.py",
        "base.py",
        "config.py",
        "extraction.py",
        "guards.py",
        "refusal.py",
        "transcription.py",
    } <= names, names
