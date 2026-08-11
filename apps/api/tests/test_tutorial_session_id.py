"""``_SESSION_ID_RE`` is the path-traversal boundary for the tutorial namespace.

REVIEW FINDING F3. The pattern was written bare — ``[A-Za-z0-9_-]{16,64}``, no
anchors at all — and a comment justified that by arguing ``re.fullmatch`` "cannot
be defeated by ``$``'s trailing-newline tolerance". The rationale defended an
anchor the pattern did not contain, and it silently assumed the single
``fullmatch`` call site would remain a ``fullmatch`` forever.

Polarity is ALLOW at every consumer, and one consumer is DESTRUCTIVE:
``dispose_tutorial_session`` is called on a directory name read off the
filesystem. So "the one call site happens to be strict" is the whole of the old
defence, and it is one refactor deep.

These tests pin the anchors themselves, so the guarantee survives a caller
reaching for a different ``re`` method.
"""

from __future__ import annotations

import re

import pytest

from isaac_api.workspace import (
    InvalidTutorialSession,
    _SESSION_ID_RE,
    is_tutorial_session_id,
    validate_tutorial_session_id,
)

WELL_FORMED = "abcdefghijklmnop"  # 16 chars, the minimum


def test_the_pattern_is_anchored_in_its_own_text():
    """``\\A``/``\\Z``, and specifically NOT ``^``/``$``.

    ``^...$`` would not be enough: Python's ``$`` also matches before a trailing
    newline, so an ``^...$`` pattern used with ``.match()`` still admits a
    newline-separated traversal suffix. ``\\Z`` is end-of-string, full stop.
    """
    assert _SESSION_ID_RE.pattern.startswith("\\A")
    assert _SESSION_ID_RE.pattern.endswith("\\Z")
    assert "^" not in _SESSION_ID_RE.pattern
    assert "$" not in _SESSION_ID_RE.pattern


def test_exactness_no_longer_depends_on_the_call_site_using_fullmatch():
    """THE MEASURED INJECTION the old bare pattern allowed.

    With ``[A-Za-z0-9_-]{16,64}`` and ``.match()``, this input passed and the
    caller went on to join an attacker-chosen traversal onto a workspace path.
    With the anchors in the pattern, ``.match()`` and ``.search()`` refuse it too
    — which is the property that makes the boundary robust rather than lucky.
    """
    injection = WELL_FORMED + "\n../../etc/passwd"
    assert _SESSION_ID_RE.match(injection) is None
    assert _SESSION_ID_RE.search(injection) is None
    assert _SESSION_ID_RE.fullmatch(injection) is None
    assert is_tutorial_session_id(injection) is False


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "short",
        "a" * 15,
        "a" * 65,
        WELL_FORMED + "\n",
        WELL_FORMED + "\r\n",
        "\n" + WELL_FORMED,
        WELL_FORMED + "/../etc",
        WELL_FORMED + "/..",
        "../" + WELL_FORMED,
        WELL_FORMED + ".json",
        WELL_FORMED + "\x00",
        WELL_FORMED + " ",
        WELL_FORMED + "\\x",
        "_tutorial",
    ],
)
def test_malformed_session_ids_are_refused(bad):
    assert is_tutorial_session_id(bad) is False
    with pytest.raises(InvalidTutorialSession):
        validate_tutorial_session_id(bad)


@pytest.mark.parametrize(
    "good",
    [
        WELL_FORMED,
        "a" * 64,
        "AbC-dEf_012345678",
        "-" * 16,
        "_" * 16,
    ],
)
def test_well_formed_session_ids_are_accepted(good):
    """Over-refusal guard. ``secrets.token_urlsafe(16)`` yields 22 characters from
    exactly ``[A-Za-z0-9_-]``, and every one of those must still be accepted."""
    assert is_tutorial_session_id(good) is True
    assert validate_tutorial_session_id(good) == good


def test_a_real_server_minted_id_is_accepted():
    """The shape actually produced in production, not just a hand-written sample."""
    import secrets

    for _ in range(50):
        minted = secrets.token_urlsafe(16)
        assert is_tutorial_session_id(minted) is True


def test_non_strings_are_refused_without_raising():
    for value in (None, 123, b"x" * 20, ["a" * 20], {"a": 1}):
        assert is_tutorial_session_id(value) is False


def test_the_call_site_behaviour_is_unchanged_by_the_anchors():
    """With ``fullmatch`` the anchors are redundant — deliberately.

    The exactness now lives in the pattern; this asserts adding it changed no
    verdict at the existing call site, so the fix is a hardening and not a
    behaviour change.
    """
    unanchored = re.compile(r"[A-Za-z0-9_-]{16,64}")
    samples = [
        WELL_FORMED,
        "a" * 64,
        "a" * 15,
        "a" * 65,
        WELL_FORMED + "\n",
        WELL_FORMED + "/../etc",
        "",
        "_tutorial",
        "AbC-dEf_012345678",
    ]
    for sample in samples:
        assert (unanchored.fullmatch(sample) is not None) == (
            _SESSION_ID_RE.fullmatch(sample) is not None
        ), sample
