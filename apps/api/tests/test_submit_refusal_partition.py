"""The submit contract's PUBLICATION PARTITION, pinned against the CODE.

WHAT THIS EXISTS TO PREVENT
===========================

``POST .../submit`` publishes every official ISAAC record BEFORE it opens the
submission transaction — deliberately, because it is the only recoverable order
(the reasoning is at the ``MATERIALISE, THEN RECORD`` comment). So some of its
refusals can arrive with artifacts already on disk, and some cannot, and the
difference is the one thing a caller cannot recover by any other means:
exported records are IMMUTABLE and no route republishes one, so a scientist told
"nothing was written" will edit the record and retry, the retry publishes
nothing, and the artifacts permanently hold the pre-edit science. That is the
failure ``routes._publication_disclosure`` (C1) exists to close in the response
BODY.

**The published CONTRACT had the same defect the bodies were fixed for.** The
``409`` description enumerated seven errors and split them by POSITION — "the
first four are raised before any official record is materialised, the last three
can also be raised after" — and that split was wrong in three places at once:
``already_submitted`` was in the first group and IS reachable after
materialisation; ``sibling_link_conflict`` was in the second and is reachable
only before; ``submission_blocked`` is emitted from two places, one of them
textually inside the materialisation block. No edit to the words "four" and
"three" could make the sentence true. A client author reading the OpenAPI
document therefore learned ``already_submitted => nothing published`` and walked
into the unrecoverable case.

WHY IT IS DERIVED FROM THE AST AND NOT FROM A LIST IN THIS FILE
==============================================================

A second hand-maintained copy of the partition would drift exactly as the first
one did. ``db_write`` records the same lesson about its own statement tally
("that count read eight while the pinning test already enumerated NINE … which
is why the test enumerates the modules' ``Q_*`` names rather than trusting this
number"). So this file parses ``routes.py``, finds every refusal
``post_submit`` can emit, decides each one's side from the code, and compares
that with ``routes._SUBMIT_REFUSAL_PUBLICATION`` — the ONE table the served
description is rendered from. A refusal that changes side, or a new refusal, or
a refusal removed, fails here.

THE DISCRIMINATOR IS THE PUBLICATION DISCLOSURE, NOT THE LINE NUMBER
====================================================================

A refusal "can have published" exactly when its construction is handed
``published``: helper call sites pass it as an argument, and inline bodies splat
``_publication_disclosure``'s fields into the content dict. That is the same seam
the bodies themselves use, so this test and the product agree by construction
rather than by coincidence.

It is also the RIGHT rule where reading by eye is wrong. The second
``submission_blocked`` emission sits textually AFTER the ``MATERIALISE, THEN
RECORD`` comment, but ``_materialise_pending_units`` validates every unit before
writing any (its PHASE 1 returns ``written=False``), so nothing is on disk when
it fires. A positional rule would classify it ``always`` and publish a second
false claim while fixing the first.

WHAT THIS FILE DOES NOT DO
==========================

It does not send a request, so it says nothing about whether a given refusal is
*reachable* at runtime — ``test_submission.py`` covers behaviour, including the
bodies' own ``published_record_count``. It is a static parity check between three
things that must agree: the emitting code, the declared table, and the served
OpenAPI document. Nothing here reads a file outside the repository.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple

import pytest

import isaac_api.routes as routes
import isaac_api.submission_store as submission_store

ROUTES_PY = Path(routes.__file__)

#: The operation whose contract this file pins.
SUBMIT_PATH = "/api/experiments/{experiment_id}/submit"

#: A refusal raised by a DEPENDENCY rather than by the handler body. FastAPI
#: resolves dependencies before the handler runs, so it cannot be
#: post-materialisation by construction — and the assertion below is that it is
#: emitted NOWHERE inside the handler, which is a mechanical check rather than a
#: restatement of that reasoning.
DEPENDENCY_RAISED = {"human_actor_required"}


# =============================================================================
# derivation
# =============================================================================


def _module_functions() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(ROUTES_PY.read_text())
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


#: The module constant a refusal splats to say "I carry the disclosure, and I cannot
#: have published anything". A splat of any OTHER name is the materialised
#: ``_publication_disclosure(published)`` result and means the opposite.
#:
#: THIS DISTINCTION IS NEW AND IS THE REASON THE DERIVATION BELOW RETURNS TWO FACTS
#: RATHER THAN ONE. Until the disclosure was added to the four refusals that lacked
#: it, "splats something" and "may have published" were the same fact, so one boolean
#: served for both. They are now different: six of the seven ``409``s carry the two
#: keys, and only three of those can carry a non-zero count.
NOTHING_PUBLISHED_CONSTANT = "_NOTHING_PUBLISHED_FIELDS"

#: The two keys the disclosure puts on a body. Read off the product constant rather
#: than written out, so a rename cannot leave this file asserting the old names.
DISCLOSURE_KEYS = frozenset(routes._NOTHING_PUBLISHED_FIELDS)


class _Refusal(NamedTuple):
    """One ``JSONResponse`` the code can build, read off the AST."""

    #: The literal ``error`` value.
    name: str
    #: Every key the body sets literally.
    literal_keys: frozenset[str]
    #: The names it dict-unpacks. Empty means it carries no disclosure at all.
    splats: frozenset[str]

    @property
    def carries_disclosure(self) -> bool:
        return bool(self.splats)

    @property
    def can_have_published(self) -> bool:
        """True when the body splats a MATERIALISED disclosure rather than the
        constant-zero one. This is the fact the partition table declares."""
        return any(name != NOTHING_PUBLISHED_CONSTANT for name in self.splats)

    @property
    def keys(self) -> frozenset[str]:
        return self.literal_keys | (DISCLOSURE_KEYS if self.splats else frozenset())


def _json_refusals(node, status: int) -> list[_Refusal]:
    """Every ``JSONResponse(status_code=<status>, ...)`` built inside ``node``.

    The disclosure is detected as dict-unpacking in the content literal —
    ``**fields`` parses to a ``None`` key — because that splat is the only way
    ``_publication_disclosure``'s fields reach a body.

    **WHICH NAME IS SPLATTED IS NOW LOAD-BEARING.** The previous version of this
    helper returned a single boolean for "unpacks something", and read it as "can
    have published". That was sound only while the disclosure appeared exclusively
    on the post-write refusals. It no longer is: ``_NOTHING_PUBLISHED_FIELDS`` puts
    the same two keys on refusals that publish nothing, so a name-blind check would
    now declare four ``never`` refusals ``always`` and fail against a table that is
    correct.
    """
    out: list[_Refusal] = []
    for call in ast.walk(node):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "JSONResponse"
        ):
            continue
        keywords = {kw.arg: kw.value for kw in call.keywords}
        code = keywords.get("status_code")
        if not (isinstance(code, ast.Constant) and code.value == status):
            continue
        content = keywords.get("content")
        assert isinstance(content, ast.Dict), (
            f"a {status} body in {getattr(node, 'name', '?')} is not a dict literal, "
            "so this file can no longer read the contract off the code"
        )
        name = None
        literal_keys: set[str] = set()
        splats: set[str] = set()
        for key, value in zip(content.keys, content.values):
            if key is None:
                assert isinstance(value, ast.Name), (
                    f"a {status} body unpacks an expression this file cannot name "
                    f"({ast.dump(value)[:60]}…), so it can no longer tell a "
                    "constant-zero disclosure from a materialised one"
                )
                splats.add(value.id)
                continue
            assert isinstance(key, ast.Constant), (
                f"a {status} body carries a computed key; the contract can no longer "
                "be derived statically"
            )
            literal_keys.add(key.value)
            if key.value == "error":
                assert isinstance(value, ast.Constant), (
                    "an `error` value is computed rather than literal; the partition "
                    "can no longer be derived statically"
                )
                name = value.value
        assert name is not None, f"a {status} body carries no `error` key"
        out.append(_Refusal(name, frozenset(literal_keys), frozenset(splats)))
    return out


def _supplies_published(call: ast.Call, target: ast.FunctionDef) -> bool:
    """Does this call site hand ``target`` a ``published`` argument?"""
    params = [arg.arg for arg in target.args.args]
    if "published" not in params:
        return False
    index = params.index("published")
    return len(call.args) > index or any(kw.arg == "published" for kw in call.keywords)


def _marker(sides: set[bool]) -> str:
    if sides == {True}:
        return "always"
    if sides == {False}:
        return "never"
    return "either"


def _derived_partition() -> dict[tuple[int, str], str]:
    """``{(status, error or reason): marker}``, read out of ``post_submit``."""
    functions = _module_functions()
    handler = functions["post_submit"]
    sides: dict[tuple[int, str], set[bool]] = {}

    def record(status: int, name: str, published: bool) -> None:
        sides.setdefault((status, name), set()).add(published)

    # Bodies built inline in the handler.
    for refusal in _json_refusals(handler, 409):
        record(409, refusal.name, refusal.can_have_published)

    # Bodies built by a helper the handler calls. Walking CALLS rather than
    # RETURNS is deliberate: `_sibling_link_conflict`'s result is assigned to a
    # local and returned on the next line, so a return-only walk would miss the
    # one refusal whose declared side was wrong.
    for call in ast.walk(handler):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        target = functions.get(call.func.id)
        if target is None or target is handler:
            continue
        published = _supplies_published(call, target)
        for refusal in _json_refusals(target, 409):
            record(409, refusal.name, published)
        if call.func.id == "_submission_unavailable":
            record(503, _reason_of(call), published)
    return {key: _marker(value) for key, value in sides.items()}


def _reason_of(call: ast.Call) -> str:
    """The ``reason`` a ``_submission_unavailable`` call site names.

    The no-storage site names it through ``submission_store``'s constant rather
    than a literal, so the attribute is resolved against the imported module —
    the point of the check is the contract's word, and the constant is where that
    word is defined.
    """
    node = call.args[0] if call.args else None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        assert node.value.id == "submission_store", node.value.id
        return getattr(submission_store, node.attr)
    raise AssertionError(f"unreadable `reason` argument: {ast.dump(node)}")


def _declared_partition() -> dict[tuple[int, str], str]:
    return {
        (status, name): marker
        for status, name, _gloss, marker in routes._SUBMIT_REFUSAL_PUBLICATION
    }


# =============================================================================
# the parity assertions
# =============================================================================


def test_the_derivation_finds_the_refusals_at_all():
    """A guard on the guard: an empty derivation would make every test below vacuous.

    If a future refactor moves these bodies behind a factory, an indirection this
    file cannot follow, or a computed `error`, the helpers above raise — and this
    test states the floor explicitly so the failure names the cause.
    """
    derived = _derived_partition()
    assert derived, "no refusal was found in `post_submit` at all"
    assert {status for status, _ in derived} == {409, 503}, sorted(derived)
    # Every marker value is one this file knows how to render.
    assert set(derived.values()) <= {"never", "either", "always"}


def test_every_refusal_the_code_can_emit_is_declared():
    """The completeness half. A NEW refusal fails here rather than shipping undocumented."""
    derived = _derived_partition()
    declared = _declared_partition()
    undeclared = sorted(set(derived) - set(declared))
    assert not undeclared, (
        "`post_submit` can emit refusals that `_SUBMIT_REFUSAL_PUBLICATION` does not "
        f"declare, so the served description does not mention them: {undeclared}"
    )


def test_every_declared_refusal_still_exists_in_the_code():
    """The other direction: a refusal that was REMOVED must leave the contract too."""
    derived = _derived_partition()
    declared = _declared_partition()
    missing = sorted(set(declared) - set(derived) - {(409, name) for name in DEPENDENCY_RAISED})
    assert not missing, (
        "the contract documents refusals `post_submit` can no longer emit: "
        f"{missing}"
    )


def test_the_declared_side_matches_the_code_for_every_refusal():
    """THE ASSERTION THIS FILE EXISTS FOR.

    The three markers are exactly the three shapes the response body can have, and
    the previous contract got three of seven wrong. Named individually in the
    failure message, because "the partition drifted" would send a reader back to
    re-derive what this test just derived.
    """
    derived = _derived_partition()
    declared = _declared_partition()
    wrong = {
        key: (declared[key], derived[key])
        for key in sorted(set(derived) & set(declared))
        if declared[key] != derived[key]
    }
    assert not wrong, (
        "declared vs. measured materialisation side (declared, measured): "
        f"{wrong} — the served description now makes a false claim about whether "
        "an official record was published before the refusal"
    )


def test_the_dependency_raised_refusal_is_emitted_nowhere_in_the_handler():
    """`human_actor_required` is `never` by construction, and this is the mechanical proof.

    It is raised by `require_human_actor`, a dependency, which FastAPI resolves
    before the handler body runs — so it cannot fire after materialisation. That
    reasoning is only sound while the handler itself never emits it; if a future
    slice raised it from the body, the declared `never` could become false silently.
    """
    functions = _module_functions()
    emitted = {refusal.name for refusal in _json_refusals(functions["post_submit"], 409)}
    for name in DEPENDENCY_RAISED:
        assert name not in emitted, (
            f"`{name}` is now emitted by the handler body, so its declared "
            "`never` is no longer established by dependency ordering"
        )
        assert (409, name) in _declared_partition(), name


# =============================================================================
# the KEYS on each body — the half this file used to leave to inspection
# =============================================================================


def _emitted_refusals() -> dict[str, _Refusal]:
    """``{error name: refusal}`` for every ``409`` ``post_submit`` can build.

    Inline bodies and helper-built bodies alike. A helper reached from more than one
    call site contributes one entry, because the BODY is the same object either way —
    which side of materialisation it fires on is what ``_derived_partition`` answers.
    """
    functions = _module_functions()
    handler = functions["post_submit"]
    out: dict[str, _Refusal] = {}
    for refusal in _json_refusals(handler, 409):
        out[refusal.name] = refusal
    for call in ast.walk(handler):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        target = functions.get(call.func.id)
        if target is None or target is handler:
            continue
        for refusal in _json_refusals(target, 409):
            out[refusal.name] = refusal
    return out


def test_every_refusal_this_operation_emits_carries_the_publication_disclosure():
    """THE ASSERTION THAT WAS MISSING, AND ITS ABSENCE IS WHY THE PROMISE WENT FALSE.

    This file called itself "a static parity check between three things": the emitting
    code, the declared table, and the served document. It compared the MARKER on each
    refusal and never the KEYS on the body — so the served sentence
    "`published_record_count` and `records` are present on EVERY one of these bodies"
    could be false for four of the seven refusals with every test green.

    Measured over HTTP before the fix:

        human_actor_required     -> ['error', 'message', 'operation', 'reason', 'trust']
        tutorial_scope_forbidden -> ['error', 'header', 'message', 'operation']

    plus BOTH `submission_blocked` emissions and `sibling_link_conflict`. A client
    told to read `published_record_count` for the authoritative answer found no such
    key on the refusal it was most likely to receive — `human_actor_required` is what
    every shipped deployment returns, because no verifier is configured.
    """
    disclosure = sorted(DISCLOSURE_KEYS)
    assert disclosure, "the disclosure declares no keys; this test would be vacuous"
    for name, refusal in sorted(_emitted_refusals().items()):
        assert refusal.carries_disclosure, (
            f"the `{name}` 409 body carries none of {disclosure}, while the served "
            "409 description promises them on every body it does not except. Splat "
            f"`{NOTHING_PUBLISHED_CONSTANT}` into it, or — if it genuinely cannot "
            "carry them — except it in the served description the way "
            "`human_actor_required` is excepted, and say why here."
        )
        assert DISCLOSURE_KEYS <= refusal.keys, (name, sorted(refusal.keys))


def test_the_dependency_raised_refusal_is_the_only_declared_exception():
    """The exception is NAMED, bounded, and cannot silently grow.

    `human_actor_required` is built in `identity.py` by a dependency shared with any
    operation that needs an attributable person, so its payload cannot honestly carry
    a claim about what THIS operation published. That is one exception with a reason.
    A second one appearing without a reason is the drift this asserts against.
    """
    declared = {
        name
        for status, name, _gloss, _marker in routes._SUBMIT_REFUSAL_PUBLICATION
        if status == 409
    }
    emitted = set(_emitted_refusals())
    assert declared - emitted == DEPENDENCY_RAISED, (
        "the set of declared 409 refusals `post_submit` does not itself emit has "
        f"changed: {sorted(declared - emitted)}. Every such refusal is an exception "
        "to the disclosure promise and must be named in the served description."
    )


def test_a_constant_zero_disclosure_is_not_read_as_a_published_one():
    """NEGATIVE CONTROL on the derivation change this fix required.

    `_NOTHING_PUBLISHED_FIELDS` puts the SAME two keys on a body as a materialised
    `_publication_disclosure(published)` does. If `_json_refusals` went back to a
    name-blind "does it unpack anything", every refusal that now carries the
    constant-zero disclosure would derive as `always` — a false claim that an official
    record was published before the refusal, introduced while fixing a false claim
    about the keys. So the two are asserted to be distinguishable, and to be
    distinguished the right way round.
    """
    emitted = _emitted_refusals()
    constant_only = {
        name
        for name, refusal in emitted.items()
        if refusal.splats == frozenset({NOTHING_PUBLISHED_CONSTANT})
    }
    assert constant_only, (
        "no refusal splats the constant-zero disclosure any more; either the fix was "
        "reverted or the constant was renamed without updating this file"
    )
    for name in constant_only:
        assert not emitted[name].can_have_published, name
        assert emitted[name].carries_disclosure, name
        assert _declared_partition()[(409, name)] == "never", (
            f"`{name}` splats the constant-zero disclosure but is declared "
            f"{_declared_partition()[(409, name)]!r} — one of the two is wrong"
        )


# =============================================================================
# the served document
# =============================================================================


@pytest.fixture(scope="module")
def submit_responses():
    """The 409/503 descriptions as an OpenAPI CLIENT receives them.

    Read from the generated document rather than from the module constant: the
    constant is what we wrote, the document is what a client author reads, and the
    defect this file closes was in the second.
    """
    from isaac_api.app import create_app

    spec = create_app().openapi()
    return spec["paths"][SUBMIT_PATH]["post"]["responses"]


def test_the_served_description_marks_every_refusal_explicitly(submit_responses):
    for status, name, gloss, marker in routes._SUBMIT_REFUSAL_PUBLICATION:
        description = submit_responses[str(status)]["description"]
        line = next(
            (l for l in description.splitlines() if l.startswith(f"- `{name}`")),
            None,
        )
        assert line is not None, (
            f"the served {status} description does not enumerate `{name}`"
        )
        assert gloss in line, (name, line)
        assert routes._PUBLICATION_MARKER_PROSE[marker] in line, (
            f"`{name}` is served with the wrong publication marker: {line}"
        )


def test_the_served_description_uses_no_positional_split(submit_responses):
    """The defect was the FORM, not only the numbers, so the form is banned.

    A positional split ("the first four … the last three") is unverifiable by a
    reader and silently falsified by reordering the list. These substrings are the
    ones the previous revision used; the general rule is that a count or an
    ordinal is not a way to say which refusal published something.
    """
    forbidden = (
        "The first four",
        "The last three",
        "the first four",
        "the last three",
    )
    for status in ("409", "503"):
        description = submit_responses[status]["description"]
        for phrase in forbidden:
            assert phrase not in description, (status, phrase)


def test_the_true_half_of_the_old_sentence_is_still_told(submit_responses):
    """The old text was WRONG about publication and RIGHT about the submission row.

    Fixing the first must not quietly drop the second: on every one of these paths
    no submission row exists, and that is what a caller most needs to know first.
    """
    assert "no submission was recorded" in submit_responses["409"]["description"]


def test_both_descriptions_send_the_caller_to_the_authoritative_field(submit_responses):
    """A marker says what a refusal CAN carry; only the body says what it DID.

    `published_record_count` is the field `_publication_disclosure` puts on every
    refusal for exactly this purpose, so neither description may leave a caller to
    infer the answer from the marker alone.
    """
    for status in ("409", "503"):
        assert "published_record_count" in submit_responses[status]["description"]


def test_the_409_description_states_its_one_exception_rather_than_overclaiming(
    submit_responses,
):
    """The served sentence must match the bodies, in BOTH directions.

    It used to read "present on EVERY one of these bodies", which was false for four
    of the seven. It now excepts exactly the refusal the code cannot give them to —
    and this asserts the exception is stated, that the exempt refusal is named so a
    client can branch on `error` rather than on prose, and that the unqualified claim
    has not crept back.
    """
    description = submit_responses["409"]["description"]
    for name in sorted(DEPENDENCY_RAISED):
        assert name in description, (
            f"the 409 description does not name `{name}`, so a client cannot tell "
            "which body lacks the disclosure"
        )
    assert "EXCEPT" in description, description
    assert "present on EVERY one of these bodies" not in description, (
        "the unqualified promise is back, and it is false for the "
        f"{sorted(DEPENDENCY_RAISED)} refusal"
    )
