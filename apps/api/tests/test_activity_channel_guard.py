"""THE MECHANICAL GUARD FOR ``ACT-002``: no write path may record without a channel.

WHY A SOURCE SCAN AND NOT A BEHAVIOURAL TEST
============================================
``activity.new_event``'s signature already makes ``channel`` a required keyword with
no default, so an event with NO channel is a ``TypeError`` at the call and an event
with an off-vocabulary channel is refused at construction. Those two are behavioural
and are asserted in ``test_activity_model.py``.

What no signature can enforce is the other half of ``ACT-002`` — that a **new write
path records an event at all**. A route added next month that mutates a record and
never calls ``record_activity`` compiles, passes every existing test, and leaves a
silent hole in the audit history. That is what this file is for, and it is the same
device ``test_submission_store`` uses for the append-only claim and
``test_revision_history`` uses for "every ``Q_*`` is a ``SELECT``": an INVENTORY
assertion over the source, with a loud failure when the extraction stops matching.

**THE EXEMPTIONS ARE ENUMERATED WITH A REASON EACH, NOT WITH A WAIVER.** A list of
"functions that do not record" is only honest if each entry says why, and each reason
here is checkable.

WHAT THIS FILE DOES NOT DO
==========================
It does not parse the routes' behaviour and does not assert that a recorded event is
*correct* — ``test_activity_api.py`` does that, over HTTP, per write path. It asserts
only that every write path is accounted for, and that no channel anywhere is a bare
string literal.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from isaac_api import activity, routes

ROUTES = Path(routes.__file__)


def _tree() -> ast.Module:
    return ast.parse(ROUTES.read_text(encoding="utf-8"))


def _enclosing_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    """Every call in ``node``'s subtree whose final attribute or name is ``name``."""
    found = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr == name:
            found.append(child)
        elif isinstance(func, ast.Name) and func.id == name:
            found.append(child)
    return found


#: Functions that call ``_save_versioned`` and deliberately record NO activity event,
#: each with the reason. A new write path must either record, or be added here with a
#: reason that survives review — which is the point: the list is the conversation.
#:
#: It is EMPTY today. That is not an accident of this slice being thorough; it is
#: because the three acts that genuinely cannot be recorded — creating a record,
#: discarding one and resetting the workspace — do not reach ``_save_versioned`` at
#: all. ``activity.py``'s "THREE ACTS THAT RECORD NOTHING" section is where those are
#: argued, and ``test_the_three_unrecorded_acts_are_the_documented_ones`` below is
#: what keeps that section honest.
SAVE_SITES_WITHOUT_ACTIVITY: dict[str, str] = {}


def test_every_write_path_in_routes_records_an_activity_event():
    """``ACT-002``, mechanically. THE TEST THAT FAILS WHEN A NEW WRITE PATH LANDS.

    ``_save_versioned`` is the one funnel every record mutation in ``routes.py`` goes
    through — that is a measured property of this module, re-derived below rather
    than assumed — so "every write path" is exactly "every function that calls it".
    """
    tree = _tree()
    writers = {}
    for function in _enclosing_functions(tree):
        if function.name == "_save_versioned":
            continue
        if _calls(function, "_save_versioned"):
            # BOTH SPELLINGS COUNT, and the second is the one that matters. The three
            # field-write paths (`post_answers`, `post_edit`, `_apply_to_run`) record
            # through the SHARED helper `_record_field_activity`, deliberately — it is
            # what makes the audit row's before/after pair and the response's own
            # `changed_fields` read ONE table (`_ANSWER_KEY_VALUE_SLOT`) and therefore
            # unable to disagree. A scan that only looked for `record_activity` called
            # all three silent, which is how this guard first failed: it was right
            # about the text and wrong about the fact.
            writers[function.name] = bool(
                _calls(function, "record_activity")
                or _calls(function, "_record_field_activity")
            )

    # THE EXTRACTION IS GUARDED, so a shape change cannot make this vacuous. 22 write
    # paths were measured when this guard was written; the floor is deliberately well
    # below that so a legitimate consolidation does not fail, while a broken scan
    # (which yields 0 or 1) does.
    assert len(writers) >= 15, (
        f"only {len(writers)} write paths found in {ROUTES.name}. The extraction "
        "above probably no longer matches this module's shape, which would make the "
        "assertion below pass for the wrong reason. Fix the scan, do not delete it."
    )

    silent = sorted(name for name, records in writers.items() if not records)
    unexplained = [name for name in silent if name not in SAVE_SITES_WITHOUT_ACTIVITY]
    assert unexplained == [], (
        f"{unexplained} mutate a record and record no activity event. DEC-44 requires "
        "an audit row for every act and ACT-002 requires a channel on it. Either call "
        "`exp.record_activity(...)` before the save, or add the function to "
        "`SAVE_SITES_WITHOUT_ACTIVITY` with a reason that says why the act cannot be "
        "recorded — not why it was inconvenient."
    )

    # …and the exemption list is not stale either: an entry for a function that no
    # longer exists, or that now records, reads as a live waiver.
    stale = sorted(set(SAVE_SITES_WITHOUT_ACTIVITY) - set(silent))
    assert stale == [], f"stale exemptions for {stale}"


def test_no_channel_anywhere_is_a_bare_string_literal():
    """A channel must be a NAMED constant or ``_api_channel()``, never ``"web"``.

    The bounded set is already enforced at construction, so a typo'd literal fails
    loudly. What a literal costs is different and is why this guard exists: it makes
    the vocabulary ungreppable and lets a site claim ``"web"`` for an act that
    arrived some other way, which is exactly the guess ``CHANNEL_SYSTEM`` exists to
    make unnecessary.
    """
    tree = _tree()
    offenders: list[str] = []
    for call in _calls(tree, "record_activity"):
        channel = next(
            (kw.value for kw in call.keywords if kw.arg == "channel"), None
        )
        if channel is None:
            offenders.append(f"line {call.lineno}: no `channel=` argument at all")
            continue
        if isinstance(channel, ast.Constant):
            offenders.append(
                f"line {call.lineno}: channel is the literal {channel.value!r}"
            )
            continue
        named_constant = (
            isinstance(channel, ast.Attribute)
            and channel.attr.startswith("CHANNEL_")
        )
        resolver = (
            isinstance(channel, ast.Call)
            and isinstance(channel.func, ast.Name)
            and channel.func.id == "_api_channel"
        )
        # A local variable holding `_api_channel()`, which `patch_run` uses because it
        # records inside a loop. Accepted by NAME, so `channel = "web"` would not pass
        # — a literal assigned to that name is caught by the assignment check below.
        indirection = isinstance(channel, ast.Name) and channel.id == "channel"
        if not (named_constant or resolver or indirection):
            offenders.append(
                f"line {call.lineno}: channel is {ast.dump(channel)[:80]}"
            )
    assert offenders == [], offenders

    # THE INDIRECTION IS CLOSED: any local named `channel` in this module is assigned
    # from `_api_channel()` or a named constant, never from a literal.
    for assignment in ast.walk(tree):
        if not isinstance(assignment, ast.Assign):
            continue
        targets = [t.id for t in assignment.targets if isinstance(t, ast.Name)]
        if "channel" not in targets:
            continue
        value = assignment.value
        ok = (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "_api_channel"
        ) or (isinstance(value, ast.Attribute) and value.attr.startswith("CHANNEL_"))
        assert ok, f"line {assignment.lineno}: `channel` assigned {ast.dump(value)[:80]}"


def test_the_guard_above_is_not_vacuous():
    """NEGATIVE CONTROL for the channel scan: a bare literal IS detected.

    The scan is run against a synthetic module rather than against a temporarily
    broken ``routes.py``, so the control cannot leave the tree dirty if it fails.
    """
    bad = ast.parse('exp.record_activity(action="x", channel="web")\n')
    channels = [
        kw.value
        for call in _calls(bad, "record_activity")
        for kw in call.keywords
        if kw.arg == "channel"
    ]
    assert len(channels) == 1
    assert isinstance(channels[0], ast.Constant), "the scan cannot see a literal"

    missing = ast.parse('exp.record_activity(action="x")\n')
    calls = _calls(missing, "record_activity")
    assert calls and not [kw for kw in calls[0].keywords if kw.arg == "channel"], (
        "the scan cannot see a missing channel"
    )


def test_every_channel_constant_named_in_routes_is_in_the_bounded_set():
    """A ``CHANNEL_*`` attribute that does not exist would be an ``AttributeError`` at
    request time — in a write path, which is the worst place for one."""
    tree = _tree()
    names = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr.startswith("CHANNEL_")
    }
    assert names, "no channel constants are named in routes.py at all"
    for name in names:
        value = getattr(activity, name)
        assert value in activity.ACTIVITY_CHANNELS, (name, value)


def test_every_action_and_object_type_named_in_routes_exists_and_is_bounded():
    """Same argument, for the other two vocabularies."""
    tree = _tree()
    for prefix, allowed in (
        ("ACTION_", activity.ACTIVITY_ACTIONS),
        ("OBJECT_", activity.ACTIVITY_OBJECT_TYPES),
    ):
        names = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr.startswith(prefix)
            and hasattr(activity, node.attr)
        }
        assert names, f"no {prefix}* constants are named in routes.py"
        for name in names:
            assert getattr(activity, name) in allowed, name


def test_no_action_constant_in_the_vocabulary_is_unreachable():
    """A verb with no write site is a verb a reader would look for rows of.

    This is what forced ``ACTION_EXPERIMENT_DISCARDED`` out of the vocabulary: the
    discard path destroys the document the history lives in, so no row can be
    written, and a constant for it would have promised one.
    """
    source = ROUTES.read_text(encoding="utf-8")
    unused = sorted(
        name
        for name in dir(activity)
        if name.startswith("ACTION_") and f"activity.{name}" not in source
    )
    assert unused == [], (
        f"{unused} are in ACTIVITY_ACTIONS and no route records them. Either record "
        "them or remove them — see activity.py's 'THREE ACTS THAT RECORD NOTHING'."
    )


def test_the_three_unrecorded_acts_are_the_documented_ones():
    """Create, discard and reset record nothing — and the code says so, in one place.

    Asserted rather than described, because ``activity.py``'s claim that these three
    are the complete set is exactly the kind of enumeration ``CLAUDE.md`` §15 records
    being published unchecked.
    """
    doc = activity.__doc__ or ""
    assert "THREE ACTS THAT RECORD NOTHING" in doc
    for act in ("CREATE", "DISCARD", "RESET"):
        assert act in doc, act

    # And mechanically: none of the three funnels through `_save_versioned`, which is
    # WHY they are absent from the guard above rather than exempted by it.
    tree = _tree()
    for name in ("create_experiment_route", "post_experiment_discard"):
        function = next(
            (f for f in _enclosing_functions(tree) if f.name == name), None
        )
        assert function is not None, f"{name} no longer exists; re-derive this claim"
        assert not _calls(function, "_save_versioned"), (
            f"{name} now goes through `_save_versioned`, so it IS a write path the "
            "guard above covers. Either record activity there or exempt it with a "
            "reason."
        )


def test_the_landed_key_table_is_shared_with_the_report_path():
    """``_record_field_activity`` and ``_fields_the_write_landed`` read ONE table.

    The audit row's before/after pair and the response's ``changed_fields`` must not
    be able to disagree about where a key's value lives. The table's COVERAGE is
    already pinned by ``test_answers_report_only_what_landed.py``, which parses
    ``_answers_to_apply_shape`` for every key it can forward; this asserts only that
    the activity path uses that same table, which is what makes the coverage guard
    cover it too.
    """
    source = ROUTES.read_text(encoding="utf-8")
    start = source.index("def _record_field_activity(")
    end = source.index("\n@router", start)
    body = source[start:end]
    assert "_ANSWER_KEY_VALUE_SLOT" in body
    assert "_asset_entry(" in body
    # And it reads the two DRAFTS, never the request body — a request says what a
    # caller wanted, the drafts say what the record held.
    assert "draft_before" in body and "draft_after" in body


# ==========================================================================
# the mechanism the channel rests on
# ==========================================================================


def test_the_ambient_channel_reaches_a_synchronous_route_handler():
    """MEASURED, NOT ASSUMED. Starlette runs a sync endpoint in a worker THREAD.

    ``routes.py``'s handlers are ordinary ``def`` functions, so Starlette dispatches
    them through ``anyio.to_thread.run_sync``. ``ContextVar`` propagation into an
    anyio worker thread is a property of anyio's implementation, not of the language,
    and the whole MCP channel rests on it — so it is measured here rather than
    reasoned about. If this ever changes, an agent's write would be recorded as
    ``web`` and nothing else in the build would notice.
    """
    from starlette.concurrency import run_in_threadpool

    def _read() -> str:
        return activity.ambient_channel(activity.CHANNEL_SYSTEM)

    async def _drive() -> tuple[str, str]:
        with activity.channel_scope(activity.CHANNEL_MCP):
            inside = await run_in_threadpool(_read)
        outside = await run_in_threadpool(_read)
        return inside, outside

    inside, outside = asyncio.run(_drive())
    assert inside == activity.CHANNEL_MCP, (
        "the ambient channel did not reach a threadpool-dispatched handler; every "
        "MCP write would be recorded as `web`"
    )
    assert outside == activity.CHANNEL_SYSTEM, "the scope leaked past its block"


def test_the_mcp_client_establishes_the_channel_around_its_own_call():
    """The one place the ``mcp`` channel can honestly be established, asserted by AST.

    A behavioural version of this claim is driven end to end in
    ``test_activity_api.py``; this one says the establishment is in ``client.py`` —
    i.e. around the transport, covering every operation — rather than bolted onto
    whichever tools somebody remembered.
    """
    from isaac_api.mcp import client as mcp_client

    tree = ast.parse(Path(mcp_client.__file__).read_text(encoding="utf-8"))
    scopes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "channel_scope"
    ]
    assert len(scopes) == 1, f"expected exactly one channel_scope in client.py, got {len(scopes)}"
    argument = scopes[0].args[0]
    assert isinstance(argument, ast.Attribute) and argument.attr == "CHANNEL_MCP"

    # And it is inside `call`, which is the ONE function every tool reaches the API
    # through — not inside a helper a new operation could bypass.
    enclosing = [
        function.name
        for function in _enclosing_functions(tree)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "channel_scope"
            for node in ast.walk(function)
        )
    ]
    assert enclosing == ["call"], enclosing


def test_no_module_reads_the_channel_from_a_request(monkeypatch):
    """NEGATIVE CONTROL on the whole design: the channel comes from no header.

    A header would have been forgeable — ``docs/identity-trust-contract.md`` §2 (Q4):
    the Service is a plain ClusterIP with no NetworkPolicy — and a forged channel is a
    false line in an audit log. So this asserts the shape rather than trusting it: no
    backend module names a channel header, under any plausible spelling.
    """
    import isaac_api

    root = Path(isaac_api.__file__).parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        # The spellings a future slice would reach for. `x-isaac-channel` is the one
        # this design explicitly rejected, and it is named in a COMMENT in two files
        # explaining why — so the scan looks for a header LOOKUP, not for the string.
        for pattern in (
            'headers.get("x-isaac-channel"',
            "headers.get('x-isaac-channel'",
            'headers["x-isaac-channel"',
            'headers.get("x-activity-channel"',
        ):
            if pattern in text:
                offenders.append(f"{path.name}: {pattern}")
    assert offenders == [], offenders


def test_the_change_feed_decision_is_recorded_and_the_cursor_version_is_unmoved():
    """``activity`` is NOT a change-feed kind, and this pins BOTH halves of that.

    The decision is published as ``activity.WHY_NO_CHANGE_FEED_KIND`` rather than left
    in a commit message, because "surface activity through the feed" is the obvious
    next request. The arithmetic it rests on is that ``activity`` sorts FIRST of the
    five kinds, so a v3 cursor would already be past every activity position at its
    own revision and would never report one — which forces a version bump and the
    refusal of every cursor in flight.

    So this asserts the feed is unchanged. A future slice that adds the kind has to
    change this test deliberately, and the constant tells it what else to change.
    """
    from isaac_api import change_feed as cf

    kinds = {collector.kind for collector in cf.RECORD_COLLECTORS}
    assert kinds == {"experiment", "run", "proposal", "note"}
    assert cf.CURSOR_VERSION == 3
    assert "activity" not in cf.feed_kinds()

    # The arithmetic the decision rests on, re-derived rather than quoted: `kind` is
    # compared as a string, and `activity` sorts before every existing kind.
    assert all("activity" < kind for kind in kinds)

    doc = activity.WHY_NO_CHANGE_FEED_KIND
    assert "CURSOR_VERSION" in doc and "3 -> 4" in doc
    assert "since_seq" in doc


def test_the_read_module_assigns_nothing_and_deletes_nothing():
    """The INVENTORY claim ``activity_history.py``'s docstring makes about itself.

    ``revision_history.py``'s device — "every ``Q_*`` in this module is a ``SELECT``",
    pinned by inventory rather than reviewed — applied to a module whose equivalent
    property is that it only reads. A read path that could assign to an event is one
    refactor away from being a write path with no route in front of it.

    The scan is over the AST, so a name in a docstring cannot satisfy or break it.
    """
    from isaac_api import activity_history as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Delete):
            offenders.append(f"line {node.lineno}: `del`")
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, (ast.Attribute, ast.Subscript)):
                    offenders.append(
                        f"line {node.lineno}: assignment to {ast.dump(target)[:60]}"
                    )
    assert offenders == [], offenders

    # …and the scan is not vacuous: it DOES see an attribute assignment.
    bad = ast.parse("event.after = 1\ndel event.before\n")
    seen = [
        type(node).__name__
        for node in ast.walk(bad)
        if isinstance(node, (ast.Assign, ast.Delete))
    ]
    assert sorted(seen) == ["Assign", "Delete"], seen


@pytest.mark.parametrize(
    "module_name", ["isaac_api.activity", "isaac_api.activity_history"]
)
def test_neither_activity_module_imports_the_truth_core_or_graphify(module_name):
    """``CLAUDE.md`` §13: the deterministic core stays reachable from nothing here.

    And the reverse direction — the truth core not importing these — is asserted in
    ``test_activity_model.py``. Both, because an import in either direction is a path
    by which an audit row could reach an exported record.
    """
    import importlib

    module = importlib.import_module(module_name)
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("isaac_records") for name in imported), imported
    assert not any("graphify" in name for name in imported), imported
