"""The assistant seam cannot submit — and until now nothing said so.

WHY THIS FILE EXISTS
====================
``docs/ai-integration-decision-packet.md`` §6.2 is an invariant, not a default.
Quoted in full, because an earlier revision of this docstring elided three words
and the elision mattered:

    **Never expose over MCP:** final authoritative ``Submit Record``; application
    of a migration; ...

enforced *"by non-implementation, server-side — never by an annotation"*. **The
invariant as written is scoped to MCP.** It is thoroughly held there —
``test_mcp_boundaries.py`` raises on a tool whose name carries the token
``submit`` and refuses a scope that can even be spelled ``isaac:submit`` — and
applying it to the **assistant** seam, which is what this file does, is an
EXTENSION of an MCP-scoped rule rather than pre-existing coverage of the
assistant. The extension is right: §6.2's reason (a non-human caller must not be
able to finalise a scientist's record) is about the caller, not the transport.
But it is an extension, and quoting §6.2 without "over MCP" made it read as
though the assistant seam had always been in scope.

Measured on ``main`` at ``b7008b8``: no test in ``apps/api/tests`` asserted the
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

THE PROOF WAS DEFEATABLE, AND NOTHING WAS BROKEN — READ BOTH HALVES
===================================================================
An independent review defeated the first version of this file **three ways, each
with all 20 tests green**. None of the three is a live vulnerability: measured at
``b301e93`` the real runtime import closure of ``isaac_api.providers`` is 13
modules (9 ``isaac_api`` + 4 ``isaac_records.extract``) and reaches nothing near
submission, and no provider source names any of the forbidden vocabulary. This is
a **proof-strength** finding — the boundary held, the *evidence* that it held did
not — and the distinction is worth keeping straight, because a reader who takes it
for a breach will go looking for a fix in the wrong place.

The three, each now a negative control in §5 rather than a paragraph:

1. **A PRE-BOUND REFERENCE.** At module level in ``providers/assistant.py``::

       _BOUND = getattr(__import__("isaac_api." + "sub" + "mission_store",
                                   fromlist=["store"]), "store")

   then ``_BOUND()`` from the unconfigured ``answer()``. Reproduced here:
   ``_BOUND is submission_store.store`` → ``True``, the provider called the REAL
   store on **every** assistant request, tripwire-visible calls **0**, and **20
   passed**. Two independent reasons it escaped. The AST scan reads
   ``ast.Import``/``ast.ImportFrom`` nodes and ``__import__`` is a *call*, so
   there is no import node to read; the token scan is a substring denylist and
   ``"sub" + "mission_store"`` is not a substring of anything. And
   ``monkeypatch.setattr(submission_store, "store", ...)`` rebinds a **module
   attribute**, while a name bound at import time holds the ORIGINAL object —
   the patch cannot see it and the tripwire never fires.

2. **ONE DIRECTORY OUT.** A natural-looking ``from .submission_store import
   store`` in a new ``isaac_api/_bridge.py``, imported from ``providers/``.
   Reproduced: **20 passed**. Both source scans are ``providers/``-directory
   scoped. (They do correctly cover new files and subpackages *inside*
   ``providers/`` — ``_provider_sources`` globs recursively; verified.)

3. **THE ARMED-NESS CONTROL NAMED ITS OWN TARGET.** ``test_the_tripwire_is_armed``
   hardcoded ``routes.submission_store.store`` instead of deriving it from the
   thing the main test patches, so it could not detect the one failure mode its
   docstring claimed to exclude. Reproduced by mis-pointing the main test's patch
   from ``store`` to ``lookup``: **20 passed**, both tests green, nothing
   measured.

WHAT IS ASSERTED, AND WHY IN THIS ORDER
=======================================
§1 the submission path really exists, so the ban is about something. If a later
   slice removes it, §1 fails first and tells the next reader to revisit this
   file rather than leaving a prohibition standing on nothing — the ordering
   ``upload-claim-parity.test.tsx`` established.
§2 no provider implementation can reach it. THREE mechanisms, and the order is
   the point: the **runtime import closure** first, because it is the only one
   that does not depend on how the next author spells things, then the AST import
   scan and the token scan, which cover what the closure cannot see. So a future
   production provider inherits the boundary instead of being trusted with it.
§3 the operation cannot be TALKED into it. A body carrying submission vocabulary
   is refused rather than ignored, which matters because §6.2's enforcement is
   non-implementation: there is nothing to call, and a caller who tries is told
   so instead of receiving a ``200`` with their key dropped.
§4 it does not reach it in fact — proven by making the submission store, the
   store's own recording entry point, and the generic durable write API each
   raise if it is so much as resolved.
§5 negative controls, including the three escapes above, so a scan narrowed until
   it detects nothing fails here rather than going quiet.

THE THREE MECHANISMS IN §2 AND WHAT EACH ONE ALONE MISSES
=========================================================
Stated explicitly, because "two scans exist so they cover for each other" was the
first version's claim and the escapes above are exactly the gap it did not name.

* **Runtime closure** (``_runtime_module_closure``) walks ``sys.modules``
  reachability from the imported ``providers`` package — module objects in each
  namespace, and the ``__module__`` of every other bound object. It is
  spelling-independent, so it catches escapes 1 and 2 at once. It sees only what
  is bound **at import time**: a deferred ``from ..submission_store import
  store`` inside a function body is invisible to it.
* **AST import scan** reads every ``Import``/``ImportFrom`` node anywhere in the
  file, including inside a function — so it catches exactly the deferred import
  the closure misses. It cannot see ``__import__`` or ``importlib``.
* **Token scan** is a substring denylist. It catches a raw SQL string and a
  ``getattr(module, "record_submission")``. **Narrowing the list is undetectable
  by construction** — no control here can prove a denylist is complete, which is
  the reason §2 now leads with the closure rather than with the scans.

What escapes all three, named rather than implied: a **deferred** import
assembled from string fragments inside a function body, resolving the store on a
code path §4's bodies do not exercise. §4's tripwire is what closes the ordinary
form of that (it fires on resolution, however the resolution was spelled), and it
covers every path a request can take **through an unconfigured provider** — which
is every path a booted deployment has, since ``validate_provider_config_or_raise``
refuses to boot an application whose ``ISAAC_ASSISTANT_PROVIDER`` names the
deterministic fake. A path reachable only through a *configured* provider is
covered by none of this, and there is no configured provider to reach it with.

Everything here is synthetic. Nothing opens a network connection, nothing
connects to a database — ``PGHOST`` is deliberately unset for §4, which is what
makes ``submission_store.store()`` return ``None`` — and no file outside the tmp
workspace is read or written. The synthetic modules §5 registers in
``sys.modules`` are built in-process from source strings and removed again.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import sys
import types
from pathlib import Path
from typing import Callable

import pytest

import isaac_api.db_write as db_write
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

#: THE GENERIC DURABLE WRITE API, added because naming the submission path is not
#: the only way to write to it (finding I4).
#:
#: ``db_write.write_transaction`` plus ``OWNED_TABLES ∋ "isaac_submissions"``
#: accepts a runtime-assembled ``INSERT INTO isaac_submissions ...`` issued from
#: anywhere. Measured directly against the policy, with the table name never
#: appearing as a literal::
#:
#:     WriteStatementPolicy().check(f"INSERT INTO {'isaac_' + 'submissions'} ...")
#:     → returns the statement (accepted)
#:
#: The only thing that stopped such a write from a provider was the absence of
#: ``PGHOST`` — an environment fact, not a guard. See
#: ``test_no_provider_reaches_the_generic_durable_write_api`` for what is and is
#: not closed here, and for why the fix is reachability rather than a check inside
#: ``write_transaction``.
DURABLE_WRITE_TOKENS = (
    "db_write",
    "write_transaction",
    "OWNED_TABLES",
)

#: What the source scans refuse, as one list.
FORBIDDEN_SOURCE_TOKENS = SUBMISSION_TOKENS + DURABLE_WRITE_TOKENS

#: Modules the providers package must not reach AT RUNTIME, by any spelling.
FORBIDDEN_MODULES = frozenset(
    {
        "isaac_api.submission_store",
        "isaac_api.db_write",
    }
)

#: Which module names the closure walk descends INTO. Everything referenced is
#: recorded regardless; this only bounds traversal, so the walk does not wander
#: through the standard library.
PROJECT_PREFIXES = ("isaac_api", "isaac_records")


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

    ``ast.walk`` reaches nodes inside function bodies, so a DEFERRED import is
    read too — that is this scan's one advantage over the runtime closure, and the
    reason it is kept rather than replaced by it.
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


def _import_offenders(paths: list[Path]) -> dict[str, set[str]]:
    """The §2 import scan, as a function, so §5 can run THE SCAN and not a copy."""
    offenders: dict[str, set[str]] = {}
    for path in paths:
        roots = _imported_roots(path.read_text())
        bad = {r for r in roots if "submission" in r or r in {"submission_store", "db_write"}}
        if bad:
            offenders[path.name] = bad
    return offenders


def _token_offenders(paths: list[Path], tokens: tuple[str, ...]) -> dict[str, list[str]]:
    """The §2 token scan, as a function, for the same reason.

    The control in §5 used to format a token into an f-string and assert it was
    there — a tautology that never invoked the scan and would have passed for a
    scan that read no files at all. It now calls THIS.
    """
    offenders: dict[str, list[str]] = {}
    for path in paths:
        text = path.read_text()
        hits = [t for t in tokens if t in text]
        if hits:
            offenders[path.name] = hits
    return offenders


# --- the runtime import closure ----------------------------------------------


def _provider_module_names() -> list[str]:
    """Every module in the providers package, imported, so the closure is real.

    ``walk_packages`` + ``import_module`` rather than relying on whatever the
    package ``__init__`` happens to pull in: a submodule nobody imports is still a
    file a future provider will live in, and the boundary has to cover it.
    """
    names = [providers_pkg.__name__]
    for info in pkgutil.walk_packages(providers_pkg.__path__, providers_pkg.__name__ + "."):
        importlib.import_module(info.name)
        names.append(info.name)
    return names


def _runtime_module_closure(
    start: list[str], prefixes: tuple[str, ...] = PROJECT_PREFIXES
) -> tuple[set[str], set[str]]:
    """Modules reachable from ``start`` through live object references.

    Returns ``(traversed, referenced)``. ``referenced`` is every module NAME any
    reachable namespace points at, by either of the two edges that exist at
    runtime:

    * a bound ``types.ModuleType`` — ``import x`` and ``from . import x``;
    * the ``__module__`` of any other bound object — which is what catches a
      PRE-BOUND function, class or constant lifted out of a module the file never
      names. That edge is the whole reason this exists: escape 1 binds
      ``submission_store.store`` under the name ``_BOUND``, and
      ``_BOUND.__module__`` is ``"isaac_api.submission_store"`` no matter how the
      import was spelled.

    ``prefixes`` bounds only the DESCENT. Everything referenced is recorded, so a
    single-hop reference into a module outside the prefixes is still reported.

    What it cannot see: a name that is not bound at import time. A function-local
    import binds nothing in the module namespace, so the AST scan above stays
    load-bearing.
    """
    traversed: set[str] = set()
    referenced: set[str] = set()
    frontier = list(start)
    while frontier:
        name = frontier.pop()
        if name in traversed:
            continue
        traversed.add(name)
        module = sys.modules.get(name)
        if module is None:
            continue
        for value in vars(module).values():
            if isinstance(value, types.ModuleType):
                target = getattr(value, "__name__", None)
            else:
                target = getattr(value, "__module__", None)
            if not isinstance(target, str):
                continue
            referenced.add(target)
            if target.startswith(prefixes) and target not in traversed:
                frontier.append(target)
    return traversed, referenced


def _closure_offenders(referenced: set[str]) -> set[str]:
    return {n for n in referenced if "submission" in n} | (FORBIDDEN_MODULES & referenced)


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


def test_the_runtime_closure_of_the_providers_package_never_reaches_the_submission_path():
    """THE ASSERTION THE SOURCE SCANS COULD NOT MAKE.

    Both scans read text, and text is the attacker's choice of spelling. This
    reads the objects the interpreter actually holds, so
    ``__import__("isaac_api." + "sub" + "mission_store", ...)`` and a bridge
    module one directory out are the same thing to it: a reference whose
    ``__module__`` is ``isaac_api.submission_store``.

    Measured at ``b301e93``: 13 modules traversed — the 9 in ``providers/`` plus
    ``isaac_api.inferability`` and three ``isaac_records.extract`` modules — and
    zero references to anything matching ``submission``.
    """
    traversed, referenced = _runtime_module_closure(_provider_module_names())
    # Non-vacuous: a walker that traversed nothing would pass every line below.
    assert len(traversed) >= 9, sorted(traversed)
    assert {
        "isaac_api.providers",
        "isaac_api.providers.assistant",
        "isaac_api.providers.base",
        "isaac_api.providers.config",
        "isaac_api.providers.refusal",
    } <= traversed, sorted(traversed)
    assert len(referenced) >= 10, sorted(referenced)
    assert _closure_offenders(referenced) == set(), (
        "the providers package reaches the submission path at runtime: "
        f"{sorted(_closure_offenders(referenced))}"
    )


def test_no_provider_reaches_the_generic_durable_write_api():
    """FINDING I4, CLOSED WHERE §2's OWN PURPOSE SENTENCE PUTS THE BOUNDARY.

    §2 exists "so a future production provider inherits the boundary instead of
    being trusted with it", and until now the boundary was about the submission
    path by name. It was not about ``db_write.write_transaction``, which is a
    generic API over ``OWNED_TABLES`` — a set that contains ``isaac_submissions``
    and ``isaac_submission_runs``. So the five append-only tables were reachable
    without ``submission_store`` appearing anywhere, and the statement policy
    accepts an assembled table name (measured; see ``DURABLE_WRITE_TOKENS``).

    WHAT IS CLOSED: provider code cannot reach ``isaac_api.db_write`` — not by
    import, not by pre-bound reference, not through a module one directory out.
    That is the same guarantee the submission path now has, at the same boundary,
    by the same mechanism.

    WHAT IS **NOT** CLOSED, AND THE CLAIM IS SCOPED ACCORDINGLY:
    ``write_transaction`` performs no caller check and this slice does not add
    one. Anything already inside ``isaac_api`` that can reach ``db_write`` can
    still name those tables. A stack-inspecting or caller-allowlisting guard
    inside ``write_transaction`` was considered and REJECTED: it would put a
    security control in a function that cannot enumerate its legitimate callers,
    it is defeated by one layer of indirection, and it would edit the durable
    write path — which ``CLAUDE.md`` §15 authorizes for named persistence work,
    not for hardening a test. Reachability is the guarantee this file can actually
    make, so it is the one it claims.
    """
    _, referenced = _runtime_module_closure(_provider_module_names())
    assert "isaac_api.db_write" not in referenced, sorted(referenced)
    assert "isaac_submissions" in db_write.OWNED_TABLES, (
        "the premise of this test changed: the submission tables are no longer "
        "writable through the generic API, so re-read the reasoning above"
    )


def test_no_provider_source_imports_the_submission_store():
    """The whole package, not only ``assistant.py``.

    A production provider is expected to be a thin adapter over a vendor SDK
    (``providers/base.py``'s ``ProviderImplementation`` is a ``Protocol`` precisely
    so it need not inherit anything). It will live in this package, and it must
    inherit this boundary rather than be trusted with it.

    Kept alongside the closure above rather than replaced by it: this reads
    function bodies, and the closure does not.
    """
    offenders = _import_offenders(_provider_sources())
    assert offenders == {}, f"a provider seam imports the submission path: {offenders}"


def test_no_provider_source_names_the_submission_vocabulary():
    """The token scan the import scan cannot do.

    An import scan misses ``getattr(module, "record_submission")`` and misses a
    raw SQL string naming ``isaac_submissions``. Neither is likely; both are
    cheap to exclude, and the point of a boundary is that it does not depend on
    the next author's likelihood.

    It is a DENYLIST, and no test can prove a denylist complete — which is why
    the closure above runs first and does not depend on this list at all.
    """
    offenders = _token_offenders(_provider_sources(), FORBIDDEN_SOURCE_TOKENS)
    assert offenders == {}, f"a provider seam names the submission path: {offenders}"


def test_the_route_handler_names_no_submission_symbol():
    """The seam's only HTTP consumer, read as source.

    ``post_assistant_ask`` lives in ``routes.py``, which necessarily imports
    ``submission_store`` for the submit operation — so neither the module-level
    scan nor the runtime closure §2 applies to ``providers/`` can be used here.
    The handler's own source is the right unit: it is what a request reaches.
    """
    import inspect

    source = inspect.getsource(routes.post_assistant_ask)
    for token in FORBIDDEN_SOURCE_TOKENS:
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


@pytest.mark.parametrize(
    "item",
    [
        {"key": "k", "text": {"submit": True}, "origin": "o"},
        {"key": "k", "text": ["submit"], "origin": "o"},
        {"key": ["k"], "text": "t", "origin": "o"},
        {"key": "k", "text": "t", "origin": {"trust": "me"}},
        {"key": "k", "text": 1, "origin": "o"},
    ],
)
def test_a_context_item_value_of_the_wrong_TYPE_is_refused_not_carried(client, item):
    """THE OTHER HALF OF "carries exactly ``key``, ``text`` and ``origin``".

    That sentence — the refusal message the route returns for an unrecognised key
    — was true of the item's KEY NAMES and false of its VALUE SHAPES.
    ``ContextItem.__post_init__`` tested truthiness alone, so
    ``{"key": "k", "text": {"submit": true}, "origin": "o"}`` constructed
    successfully and was answered ``501``. It never reached a provider in this
    build, but ``DeterministicAssistantFake.answer`` concatenates ``text``, so the
    one code path whose entire subject is refusing honestly raised ``TypeError``
    on ``dict + str`` and would have answered ``500``.

    A caller who nests an object under ``text`` is doing something this operation
    has no meaning for, and the honest answer is the typed ``422`` every other
    malformed context item already gets — not a ``501`` that reads as "your
    request was fine, this build just has no provider".
    """
    response = client.post(ASK, json={"question": "q", "context": [item]})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_field_value"
    assert body["key"] == "context[0]"


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

#: THE TRIPWIRE TARGETS, IN ONE PLACE, SO THE ARMED-NESS CONTROL CANNOT BE
#: MIS-POINTED SILENTLY.
#:
#: Escape 3 was possible because the main test patched ``store`` and the control
#: independently hardcoded ``store`` — two literals that could drift apart. Both
#: now read THIS tuple, and each entry carries a fourth element: how PRODUCTION
#: resolves the same object, written as an independent lookup rather than as
#: ``getattr(owner, attr)`` (which would make the control a tautology again).
#: ``_assert_target_is_armed`` checks the two agree BEFORE patching, so a
#: mis-pointed entry fails there instead of passing quietly.
#:
#: Three targets, not one. ``store()`` is the first thing the submit operation
#: calls and it is what returns ``None`` without ``PGHOST``, so arming it catches
#: a caller who resolves the store and then correctly does nothing with it —
#: still a caller that has no business resolving it. ``record_submission`` is the
#: act itself, arm-able independently of how the store was obtained. And
#: ``write_transaction`` is finding I4: the durable write API through which those
#: tables can be named without naming the store.
TRIPWIRE_TARGETS: tuple[tuple[str, object, str, Callable[[], object]], ...] = (
    (
        "isaac_api.submission_store.store",
        submission_store,
        "store",
        lambda: importlib.import_module("isaac_api.submission_store").store,
    ),
    (
        "isaac_api.submission_store.PostgresSubmissionStore.record_submission",
        submission_store.PostgresSubmissionStore,
        "record_submission",
        lambda: importlib.import_module(
            "isaac_api.submission_store"
        ).PostgresSubmissionStore.record_submission,
    ),
    (
        "isaac_api.db_write.write_transaction",
        db_write,
        "write_transaction",
        lambda: importlib.import_module("isaac_api.db_write").write_transaction,
    ),
)


def test_the_handler_and_the_route_module_share_one_submission_store_object():
    """Why patching ``submission_store`` is enough, stated rather than assumed.

    The first version patched ``submission_store.store`` AND
    ``routes.submission_store.store``, which reads as belt-and-braces. It is
    actually one patch: ``routes`` does ``import ... submission_store``, so the
    two names are the same module object. Asserting the identity is worth more
    than the duplicate patch — if ``routes`` ever held its own copy, the
    redundancy comment would be false and this line says so.
    """
    assert routes.submission_store is submission_store


def test_no_reachable_outcome_of_the_operation_resolves_the_submission_store(
    client, monkeypatch
):
    """A tripwire on all three targets, across every outcome a request can take.

    WHAT THIS PROVES AND WHAT IT DOES NOT. It does not prove the handler *cannot*
    submit — §2 and §3 are the structural halves of that. It proves the handler
    does not, today, along any path a request can take: the well-formed 501, the
    two 422 shapes, and a body that is not an object at all.

    THE PHRASE "survives the store being reached indirectly, through a helper this
    file never names" IS CORRECTED, NOT DELETED, BECAUSE IT WAS OVERSTATED IN ONE
    DIRECTION. A tripwire on a module attribute survives an indirect *call*; it
    does NOT survive an indirect *binding*. Escape 1 bound ``store`` at import
    time, before any patch could exist, and this tripwire saw nothing — 0 calls,
    20 green. What closes that is the runtime closure in §2, not this. What THIS
    adds, and no source scan does, is that a future edit resolving the store
    dynamically from inside a request turns it red however the resolution is
    spelled.
    """
    calls: list[str] = []

    def _make_tripwire(label: str):
        def _tripwire(*args, **kwargs):  # pragma: no cover - must never run
            calls.append(label)
            raise AssertionError(
                f"the assistant seam resolved {label}; "
                "docs/ai-integration-decision-packet.md §6.2 forbids it"
            )

        return _tripwire

    for label, owner, attr, _reach in TRIPWIRE_TARGETS:
        monkeypatch.setattr(owner, attr, _make_tripwire(label))

    bodies: list[object] = [
        {"question": "q", "context": [{"key": "k", "text": "t", "origin": "o"}]},
        {"question": "q"},
        {"question": "q", "submit": True},
        {"question": ""},
        {"question": "q", "context": [{"key": "k", "text": {"n": 1}, "origin": "o"}]},
        # NOT the handler's own `isinstance` guard — see the test below.
        ["not", "an", "object"],
    ]
    for body in bodies:
        response = client.post(ASK, json=body)
        assert response.status_code in (422, 501), (body, response.text)
    assert calls == []


def test_the_non_object_body_is_answered_by_FASTAPI_not_by_the_handler(client):
    """"EVERY REACHABLE OUTCOME" WAS OVERSTATED BY ONE, AND THIS IS THE CORRECTION.

    ``["not", "an", "object"]`` is in the list above, and it is a real request
    with a real 422 — but it never reaches ``post_assistant_ask``. The parameter
    is annotated ``body: dict``, so FastAPI's own coercion answers first with a
    ``dict_type`` error under ``detail``, and the handler's ``isinstance(body,
    dict)`` guard is HTTP-UNREACHABLE.

    That guard is still worth having (the handler is an ordinary function and the
    annotation is not a runtime check), so it is covered here the only way it can
    be: called directly. Now the claim "every reachable outcome" is true of the
    pair of tests rather than false of one of them.
    """
    over_http = client.post(ASK, json=["not", "an", "object"])
    assert over_http.status_code == 422
    assert "detail" in over_http.json(), over_http.text
    assert over_http.json().get("error") is None

    direct = routes.post_assistant_ask(["not", "an", "object"])  # type: ignore[arg-type]
    assert direct.status_code == 422
    assert b'"invalid_body"' in direct.body


def _assert_target_is_armed(
    monkeypatch, label: str, owner: object, attr: str, reach: Callable[[], object]
) -> None:
    """The armed-ness check, DERIVED — this is what escape 3 could not do.

    Two properties, in this order:

    1. **The patch points where production looks.** ``reach()`` resolves the
       object by an independent path (``importlib.import_module`` from the module's
       dotted name), and it must be the SAME object ``getattr(owner, attr)``
       returns. A mis-pointed entry — the measured escape swapped ``store`` for
       ``lookup`` — fails here, before anything is patched.
    2. **A patched target fires.** After patching, the independent path must
       resolve to the tripwire and calling it must raise. A tripwire that
       swallowed its own exception fails here.
    """
    before = getattr(owner, attr)
    assert reach() is before, (
        f"{label}: the tripwire patches an attribute that production does not "
        "resolve — the patch and the control have drifted apart"
    )

    def _tripwire(*args, **kwargs):
        raise AssertionError("armed")

    monkeypatch.setattr(owner, attr, _tripwire)
    assert reach() is _tripwire, f"{label}: the patch did not take on the real path"
    with pytest.raises(AssertionError, match="armed"):
        reach()()


@pytest.mark.parametrize("target", TRIPWIRE_TARGETS, ids=lambda t: t[0])
def test_every_tripwire_target_is_armed(monkeypatch, target):
    """The negative control for the test above, over the SAME tuple it patches."""
    _assert_target_is_armed(monkeypatch, *target)


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
        # I4: the generic write API is now part of the import boundary too.
        "from .. import db_write",
        "from ..db_write import write_transaction",
        # A DEFERRED import, which is what this scan has that the closure has not.
        "def answer(self):\n    from ..submission_store import store\n    return store()",
    ],
)
def test_the_import_scan_sees_a_planted_import(tmp_path, planted):
    path = tmp_path / "planted.py"
    path.write_text(planted)
    # THE REAL SCAN, not a re-implementation of its predicate.
    assert _import_offenders([path]), planted


def test_the_import_scan_reads_relative_imports_the_package_actually_uses():
    """Not vacuous: the scan must see the imports these files really have.

    A parser that returned an empty set for every relative import would pass §2
    without reading a line, and this package imports almost entirely relatively
    (``from .refusal import ...``).
    """
    roots = _imported_roots((PROVIDERS_PACKAGE / "assistant.py").read_text())
    assert {"base", "refusal"} <= roots, roots


@pytest.mark.parametrize("token", FORBIDDEN_SOURCE_TOKENS)
def test_the_token_scan_sees_a_planted_token(tmp_path, token):
    """NO LONGER A TAUTOLOGY.

    This used to be ``assert token in f"x = {token} # planted"`` — a string
    formatted and then found in itself. It never called the scan, so it would have
    passed for a scan that read no files, globbed nothing, or had been narrowed to
    the empty tuple. It now writes a file and runs ``_token_offenders``, the same
    function §2 runs.

    It still cannot detect a NARROWED token list, and nothing can: a denylist's
    completeness is not a testable property. That limit is why §2's first
    assertion is the runtime closure, which does not consult this tuple.
    """
    path = tmp_path / "planted.py"
    path.write_text(f"x = {token!r}  # planted\n")
    offenders = _token_offenders([path], FORBIDDEN_SOURCE_TOKENS)
    assert token in offenders.get("planted.py", []), offenders


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


# --- §5b the three escapes, reproduced as controls --------------------------
#
# Each is built as a SYNTHETIC module registered in `sys.modules` and removed
# again — never by editing a file under `apps/api/isaac_api/`. The escapes were
# reproduced against the real tree once, by hand, to establish that they are real
# (20/20 green each time, files restored and verified by sha256); reproducing them
# in CI has to be hermetic, because a test that mutates a shipped module and
# crashes leaves the tree broken for every test after it.


@pytest.fixture()
def synthetic_modules():
    """Register in-process modules built from source strings; remove them after."""
    created: list[str] = []

    def make(name: str, source: str) -> types.ModuleType:
        module = types.ModuleType(name)
        module.__file__ = f"<synthetic {name}>"
        sys.modules[name] = module
        created.append(name)
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        return module

    yield make
    for name in reversed(created):
        sys.modules.pop(name, None)


#: Escape 1, verbatim. Kept as a string so the two source scans can be run
#: against the exact text that defeated them.
ESCAPE_PREBOUND_SOURCE = (
    '_BOUND = getattr(__import__("isaac_api." + "sub" + "mission_store", '
    'fromlist=["store"]), "store")\n'
)


def test_escape_1_a_prebound_reference_defeats_both_source_scans(tmp_path):
    """The measurement, as an assertion: the scans are BLIND to this text.

    Not a criticism of the scans — it is the reason the closure exists, and if a
    future edit ever made a source scan see this, that would be worth knowing too.
    """
    path = tmp_path / "prebound.py"
    path.write_text(ESCAPE_PREBOUND_SOURCE)
    assert _import_offenders([path]) == {}, "the AST scan unexpectedly sees __import__"
    assert (
        _token_offenders([path], FORBIDDEN_SOURCE_TOKENS) == {}
    ), "the token scan unexpectedly sees an assembled module name"


def test_escape_1_is_caught_by_the_runtime_closure(synthetic_modules):
    """RED WITHOUT THE CLOSURE. The escape that ran the real store, 20/20 green."""
    synthetic_modules("seamproof_escape1", ESCAPE_PREBOUND_SOURCE)
    _, referenced = _runtime_module_closure(
        ["seamproof_escape1"], prefixes=("seamproof_",) + PROJECT_PREFIXES
    )
    assert "isaac_api.submission_store" in referenced, sorted(referenced)
    assert _closure_offenders(referenced), sorted(referenced)


def test_escape_2_a_bridge_one_directory_out_is_caught_by_the_runtime_closure(
    synthetic_modules,
):
    """The second escape: the naming is innocent, the file is outside the scan.

    ``_provider_sources()`` globs ``providers/`` and nothing else — asserted here
    rather than described, because "one directory out" is only an escape while
    that is true. The provider module's own text is clean either way; the closure
    reports it anyway.

    BOTH IMPORT SHAPES, because they are caught by DIFFERENT edges and only one of
    them was the shape actually reproduced:

    * ``from ..\\_bridge import store as _bridged_store`` — the measured escape.
      It binds the FUNCTION, not the bridge module, so the bridge is never
      traversed and the catch is the one-hop ``__module__`` edge.
    * ``import _bridge`` then ``_bridge.store()`` — binds the MODULE, so the catch
      requires descending into the bridge and reading ITS namespace. A closure
      that followed only ``__module__`` and not module objects would miss this
      one, which is why it is asserted separately rather than assumed equivalent.
    """
    assert all(
        p.is_relative_to(PROVIDERS_PACKAGE) for p in _provider_sources()
    ), "the source scans no longer stop at providers/; re-read this control"

    synthetic_modules(
        "seamproof_escape2_bridge", "from isaac_api.submission_store import store\n"
    )

    # (a) the measured shape: the symbol is lifted out, the bridge is not bound.
    symbol_source = "from seamproof_escape2_bridge import store as _bridged_store\n"
    synthetic_modules("seamproof_escape2_symbol", symbol_source)
    # The provider file itself names nothing forbidden...
    assert {"submission", "db_write"}.isdisjoint(_imported_roots(symbol_source))
    assert not [t for t in FORBIDDEN_SOURCE_TOKENS if t in symbol_source]
    _, referenced = _runtime_module_closure(
        ["seamproof_escape2_symbol"], prefixes=("seamproof_",) + PROJECT_PREFIXES
    )
    assert "isaac_api.submission_store" in referenced, sorted(referenced)
    assert _closure_offenders(referenced), sorted(referenced)

    # (b) the module-object shape, caught only by descending into the bridge.
    module_source = "import seamproof_escape2_bridge as _bridge\n"
    synthetic_modules("seamproof_escape2_module", module_source)
    assert {"submission", "db_write"}.isdisjoint(_imported_roots(module_source))
    traversed, referenced = _runtime_module_closure(
        ["seamproof_escape2_module"], prefixes=("seamproof_",) + PROJECT_PREFIXES
    )
    assert "seamproof_escape2_bridge" in traversed, sorted(traversed)
    assert "isaac_api.submission_store" in referenced, sorted(referenced)
    assert _closure_offenders(referenced), sorted(referenced)


def test_escape_3_a_mispointed_tripwire_is_now_detected(monkeypatch):
    """The third escape, exactly as measured: ``store`` swapped for ``lookup``.

    Both tests stayed green because the control named its own target. Fed through
    ``_assert_target_is_armed``, the same mis-pointing now fails on the identity
    check — and it fails BEFORE the patch, so the message says what is wrong
    rather than reporting an absent call.
    """
    mispointed = (
        "decoy",
        submission_store,
        "lookup",
        lambda: importlib.import_module("isaac_api.submission_store").store,
    )
    with pytest.raises(AssertionError, match="production does not resolve"):
        _assert_target_is_armed(monkeypatch, *mispointed)


def test_the_runtime_closure_is_not_vacuous_on_a_clean_synthetic_module(
    synthetic_modules,
):
    """The other half of the control: it must also say NO.

    A closure walker that reported an offender for every input would make the two
    escape controls above pass while proving nothing. A module importing only
    ``json`` has no offenders.
    """
    synthetic_modules("seamproof_clean", "import json\n\nVALUE = json.dumps({})\n")
    traversed, referenced = _runtime_module_closure(
        ["seamproof_clean"], prefixes=("seamproof_",) + PROJECT_PREFIXES
    )
    assert traversed == {"seamproof_clean"}
    assert "json" in referenced
    assert _closure_offenders(referenced) == set(), sorted(referenced)
