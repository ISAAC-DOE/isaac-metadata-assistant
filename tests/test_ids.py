"""``is_record_id`` — the record-id shape gate, and its exactness.

WHY THIS FILE EXISTS. ``RECORD_ID_RE`` was ``^[0-9A-Z]{26}$`` and was applied with
``.match()``. Python's ``$`` also matches immediately BEFORE a trailing newline, so
the 27-character string ``"A"*26 + "\\n"`` passed ``is_record_id``. That predicate is
not decorative: ``workspace.py`` cites it as the reason no record id can collide with
the ``_``-prefixed tutorial namespace, ``export_draft`` uses it as the gate on a
caller-supplied ``record_id``, and ``routes._artifact_stem`` uses it to decide which
files an artifact prune may delete. The pattern is now ``\\A[0-9A-Z]{26}\\Z``.

Each case names EXACTLY the codepoint it appends or substitutes. A newline and a
space are separate categories, and so are ``\\n``, ``\\r``, ``\\v``, ``\\f``, U+0085
and U+2028: only ``\\n`` was ever accepted, so a case labelled "trailing whitespace"
that used a space would give false confidence for the newline it named.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from isaac_records.ids import RECORD_ID_RE, is_record_id, new_record_id

ROOT = Path(__file__).resolve().parents[1]

GOOD = "01JFH3Q8Z1Q9F0XG3V7N4K2M8C"  # 26 chars, the shape `new_record_id` mints


# --- baseline: the fix must not narrow what a legitimate id looks like ---------


def test_a_real_ulid_is_accepted():
    assert len(GOOD) == 26
    assert is_record_id(GOOD)


def test_a_freshly_minted_id_is_accepted():
    minted = new_record_id()
    assert len(minted) == 26
    assert is_record_id(minted)


def test_the_whole_permitted_alphabet_is_still_accepted():
    """Every character the class admits, exactly 26 of them."""
    alphabet = "0123456789ABCDEFGHIJKLMNOP"
    assert len(alphabet) == 26
    assert is_record_id(alphabet)
    assert is_record_id("Z" * 26)
    assert is_record_id("0" * 26)


# --- length -------------------------------------------------------------------


@pytest.mark.parametrize("length", [0, 1, 25, 27, 52])
def test_wrong_length_is_refused(length):
    assert not is_record_id("A" * length)


# --- newlines: the headline regression, and the neighbours it is not ----------


def test_trailing_newline_is_refused():
    """THE regression. 27 characters, the 27th being LF (0x0a).

    Under ``^...$`` with ``.match()`` this returned True.
    """
    bad = GOOD + "\n"
    assert len(bad) == 27 and bad[-1] == "\n"
    assert not is_record_id(bad)


def test_leading_newline_is_refused():
    """Never accepted — ``^`` without ``re.MULTILINE`` only matches at offset 0 —
    and pinned so that a future ``re.M`` on this pattern is a test failure rather
    than a silent traversal surface."""
    assert not is_record_id("\n" + GOOD)


def test_embedded_newline_is_refused():
    """A newline in the MIDDLE, total length still 27. ``$`` was lenient only about
    a newline at the very end, so this was already refused; it is pinned because an
    embedded separator is the shape a filesystem-path injection takes."""
    bad = GOOD[:13] + "\n" + GOOD[13:]
    assert len(bad) == 27
    assert not is_record_id(bad)


def test_only_newline_was_ever_the_lenient_case(
    # Ordered so the failure message names the codepoint.
):
    """The other line-ish terminators, each refused BEFORE and after the fix.

    They are asserted so nobody "generalises" the fix into a strip-then-match, which
    would accept all of them.
    """
    for label, char in (
        ("LF", "\n"),
        ("CR", "\r"),
        ("CRLF", "\r\n"),
        ("VT", "\v"),
        ("FF", "\f"),
        ("FS", "\x1c"),
        ("NEL U+0085", "\x85"),
        ("LINE SEPARATOR U+2028", " "),
        ("PARAGRAPH SEPARATOR U+2029", " "),
        ("NUL", "\x00"),
        ("SPACE", " "),
        ("TAB", "\t"),
    ):
        assert not is_record_id(GOOD + char), f"trailing {label} accepted"
        assert not is_record_id(char + GOOD), f"leading {label} accepted"


# --- alphabet -----------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "01jfh3q8z1q9f0xg3v7n4k2m8c",  # all lowercase
        "01JFH3Q8Z1Q9F0XG3V7N4K2M8c",  # one lowercase, last position
        "01jFH3Q8Z1Q9F0XG3V7N4K2M8C",  # one lowercase, interior
        "not-a-ulid-not-a-ulid-not1",  # 26 chars, punctuation
        "01JFH3Q8Z1Q9F0XG3V7N4K2M8-",  # hyphen
        "01JFH3Q8Z1Q9F0XG3V7N4K2M8.",  # dot — the path-traversal character
        "../JFH3Q8Z1Q9F0XG3V7N4K2M8",  # traversal, exactly 26 chars
        "01JFH3Q8Z1Q9F0XG3V7N4K2M8/",  # separator, exactly 26 chars
        "01JFH3Q8Z1Q9F0XG3V7N4K2M8_",  # underscore — the tutorial-namespace prefix
        "_1JFH3Q8Z1Q9F0XG3V7N4K2M8C",  # leading underscore, 26 chars
    ],
)
def test_invalid_alphabet_is_refused(bad):
    assert len(bad) == 26, "the case must isolate the ALPHABET, not the length"
    assert not is_record_id(bad)


# --- Unicode boundary cases ---------------------------------------------------
#
# ``[0-9A-Z]`` is a literal ASCII class, so none of these can be admitted. They are
# pinned because the tempting rewrites — ``\w``, ``\d``, ``.upper()``, ``casefold()``,
# NFKC normalisation — each admit at least one of them, and the pattern sits on a
# path-traversal boundary where "it looked like an id" is the whole attack.


@pytest.mark.parametrize(
    "label,char",
    [
        # `\d` with Unicode semantics (Python's default for str) matches all three.
        ("ARABIC-INDIC DIGIT ZERO U+0660", "٠"),
        ("DEVANAGARI DIGIT ZERO U+0966", "०"),
        ("FULLWIDTH DIGIT ZERO U+FF10", "０"),
        # `str.isdigit()` is True for these; `\d` is not, and neither is `[0-9]`.
        ("SUPERSCRIPT TWO U+00B2", "²"),
        ("CIRCLED DIGIT ONE U+2460", "①"),
        # Case-folding / NFKC hazards: each maps to or from an ASCII A-Z member.
        ("KELVIN SIGN U+212A", "K"),
        ("ANGSTROM SIGN U+212B", "Å"),
        ("FULLWIDTH LATIN CAPITAL A U+FF21", "Ａ"),
        ("LATIN CAPITAL I WITH DOT ABOVE U+0130", "İ"),
        ("LATIN SMALL DOTLESS I U+0131", "ı"),
        ("CYRILLIC CAPITAL A U+0410", "А"),
        ("GREEK CAPITAL ALPHA U+0391", "Α"),
        # `\w` matches these; `[A-Z]` does not.
        ("CHEROKEE LETTER A U+13A0", "Ꭰ"),
        ("MATHEMATICAL BOLD CAPITAL A U+1D400", "\U0001d400"),
        # Zero-width and bidi controls: invisible, so a human review cannot see them.
        ("ZERO WIDTH SPACE U+200B", "​"),
        ("ZERO WIDTH NO-BREAK SPACE / BOM U+FEFF", "﻿"),
        ("RIGHT-TO-LEFT OVERRIDE U+202E", "‮"),
    ],
)
def test_unicode_lookalikes_are_refused_in_every_position(label, char):
    """Substituted for a real character (length preserved) AND appended."""
    substituted = char + GOOD[1:]
    assert len(substituted) == 26
    assert not is_record_id(substituted), f"{label} accepted as the first character"
    assert not is_record_id(GOOD[:-1] + char), f"{label} accepted as the last character"
    assert not is_record_id(GOOD + char), f"{label} accepted as a 27th character"


def test_a_normalising_or_case_folding_rewrite_would_break_these_cases():
    """Not a property of the code — a property of the CASES, asserted so the file
    keeps its value. If the pattern were ever relaxed to ``(?i)`` or fed
    ``unicodedata.normalize("NFKC", value)``, at least one case above would pass,
    and the suite would go red rather than quiet."""
    import unicodedata

    assert unicodedata.normalize("NFKC", "Ａ" + GOOD[1:]) == "A" + GOOD[1:]
    assert unicodedata.normalize("NFKC", "K") == "K"
    assert ("０" + GOOD[1:]).isalnum() and "０".isdigit()


# --- non-strings --------------------------------------------------------------


@pytest.mark.parametrize("value", [None, 0, 1, 1.0, True, b"A" * 26, ["A" * 26], {"id": "A" * 26}])
def test_non_strings_are_refused_without_raising(value):
    assert is_record_id(value) is False


# --- the structural property the fix buys -------------------------------------


def test_the_pattern_itself_carries_the_exactness():
    """``.match`` and ``.fullmatch`` now agree on every input, which is what makes a
    future ``.match()`` caller safe. Asserted on the CONSTANT, because that is what
    other modules import and what ``workspace.py``'s comments cite."""
    assert "$" not in RECORD_ID_RE.pattern and "^" not in RECORD_ID_RE.pattern
    assert not RECORD_ID_RE.flags & re.MULTILINE
    for candidate in (GOOD, GOOD + "\n", "\n" + GOOD, GOOD[:-1], GOOD + "A", "a" * 26, ""):
        assert (RECORD_ID_RE.match(candidate) is not None) == (
            RECORD_ID_RE.fullmatch(candidate) is not None
        ), repr(candidate)


# --- relationship to the vendored official schema -----------------------------


def test_our_predicate_is_never_laxer_than_the_official_schema_pattern():
    """MEASURED, and the reason this file's fix had to happen in OUR code.

    ``schema/isaac_record_v1.json`` declares ``record_id`` as
    ``pattern: "^[0-9A-Z]{26}$"``, and at the time of writing a record whose
    ``record_id`` is ``"A"*26 + "\\n"`` validates **ok** through the project's own
    ``validate_official`` — the schema's ``$`` is lenient in exactly the way
    Python's is. Note the mechanism precisely: it is NOT that JSON Schema
    ``pattern`` is unanchored (it is matched with ``re.search``, but ``^`` still
    pins offset 0, which is why a LEADING newline is correctly refused). It is
    ``$``. The vendored schema is upstream-owned (``CLAUDE.md`` §1) and is not
    edited here.

    The assertion is deliberately DIRECTIONAL rather than a snapshot of the schema's
    current behaviour: our predicate must never accept what the schema rejects. That
    stays true whichever way upstream moves, whereas asserting "the schema admits a
    trailing newline" would turn an upstream FIX into a red test.
    """
    pattern = json.loads((ROOT / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8"))[
        "properties"
    ]["record_id"]["pattern"]
    assert pattern == "^[0-9A-Z]{26}$", "the vendored pattern moved — re-read this test"
    schema_admits = re.compile(pattern)  # `search`, as JSON Schema specifies
    for candidate in (
        GOOD,
        GOOD + "\n",
        "\n" + GOOD,
        GOOD[:13] + "\n" + GOOD[13:],
        GOOD + " ",
        GOOD[:-1],
        GOOD + "A",
        "a" * 26,
        "",
    ):
        if is_record_id(candidate):
            assert schema_admits.search(candidate), (
                f"{candidate!r} passes is_record_id but the official schema pattern "
                "refuses it — our gate must never be laxer than the schema's"
            )
