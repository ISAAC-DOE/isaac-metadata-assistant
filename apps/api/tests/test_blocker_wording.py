"""The three internal blocker identifiers, and the wording the assistant uses.

WHAT WAS WRONG. ``experiment_repository.py:769,778,786`` mints ``reduced_spectrum``,
``qc_status`` and ``required_for_evidence_record`` as a pending entry's ``blocker``
key; ``serialize._blocker_about`` puts the first string of ``uri``/``blocker`` into
the served ``about``; and ``assistant_query._pending_labels`` took that verbatim as
its first rung. So the assistant answered a scientist with

    "3 fields still need you: reduced_spectrum, qc_status,
     required_for_evidence_record."

``CLAUDE.md`` §11 records this as open jargon, and records why the usual exemption
does not apply: ``UX-014``'s rule protects a SCHEMA PATH, on the stated ground that
"it is how a curator maps a field", and these are not schema paths — ``grep -rao``
over ``schema/`` and ``vocabulary/`` returns **0 hits for all three**. §11 also
records that an earlier exemption claim rested on exactly that miscitation and was
withdrawn.

THE PARITY IS THE POINT, and it is why the table below is duplicated rather than
shared: the assistant names these fields in a sentence while the website names them
in a row, and one field must not be called two things. The expectations here are
byte-identical to ``apps/web/src/__tests__/blocker-wording-parity.test.ts``, which
names this file in turn. Two languages cannot share a constant, so they share a
pinned table.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from isaac_api import assistant_query

#: The exact table the TypeScript parity test asserts.
HUMANIZED = [
    ("reduced_spectrum", "Reduced Spectrum"),
    ("qc_status", "QC Status"),
    ("required_for_evidence_record", "Required For Evidence Record"),
]

#: Every real-locator shape this repository actually serves. Verbatim, all of them.
LOCATORS_VERBATIM = [
    "sample.material.formula",
    "assets:sha256",
    "ssrl-archive://BL15-2/2099_run_000/x.xdi",
    "Sheet 'Campaign Info', field=technique",
    "line 16, ssrl-archive://BL15-2/2099_run_000/notebooks/",
]

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(("key", "shown"), HUMANIZED)
def test_each_internal_key_is_humanized(key: str, shown: str) -> None:
    assert assistant_query._blocker_display(key) == shown


@pytest.mark.parametrize("locator", LOCATORS_VERBATIM)
def test_a_real_locator_is_never_rewritten(locator: str) -> None:
    # Measured rather than assumed: the last-segment humanizer turns that URI into
    # "Xdi", which names nothing. That is the reason the predicate is shape-based.
    assert assistant_query._blocker_display(locator) == locator


def test_the_assistant_sentence_names_no_machine_key() -> None:
    """The defect, at the composer that produced it."""
    entries = [
        {"kind": "series", "about": "reduced_spectrum", "question": "q1"},
        {"kind": "qc", "about": "qc_status", "question": "q2"},
        {"kind": "descriptor", "about": "required_for_evidence_record", "question": "q3"},
    ]
    labels = assistant_query._pending_labels(entries)
    assert labels == ["Reduced Spectrum", "QC Status", "Required For Evidence Record"]
    for key, _shown in HUMANIZED:
        assert key not in " ".join(labels)


def test_the_other_three_rungs_are_the_servers_own_words_and_are_untouched() -> None:
    """Only ``about`` is display-mapped.

    ``question`` is prose this application authored, ``id`` is the entry's kind and
    ``unavailable_reason`` is an operator-facing reason. Rewriting any of them would
    be the composer editing text it did not write — and the reason rung in
    particular is the only thing anybody knows about an unreadable entry.
    """
    assert assistant_query._pending_labels([{"question": "what_is_this"}]) == ["what_is_this"]
    assert assistant_query._pending_labels([{"id": "series"}]) == ["series"]
    assert assistant_query._pending_labels([{"unavailable_reason": "stored_shape"}]) == [
        "stored_shape"
    ]


def test_the_three_keys_are_still_absent_from_the_schema_and_the_vocabulary() -> None:
    """The measurement the whole change rests on, re-run rather than quoted.

    If a future schema refresh ever introduced one of these as a real path, the
    ``UX-014`` exemption WOULD reach it and this humanization would need re-arguing
    — so the premise is a test, not a sentence in a commit message.
    """
    haystack = ""
    for folder in ("schema", "vocabulary"):
        for path in sorted((REPO_ROOT / folder).rglob("*")):
            if path.is_file():
                haystack += path.read_text(encoding="utf-8", errors="replace")
    for key, _shown in HUMANIZED:
        assert key not in haystack, f"{key} now appears in the schema/vocabulary"


def test_the_predicate_matches_exactly_the_bare_identifier_shape() -> None:
    for key, _shown in HUMANIZED:
        assert assistant_query._BARE_IDENTIFIER.fullmatch(key)
    # Each differs from a bare identifier in ONE way, so a predicate that drifted
    # fails here rather than on a shape nobody serves.
    for near in (
        "Reduced_Spectrum",
        "reduced spectrum",
        "reduced.spectrum",
        "reduced-spectrum",
        "_reduced",
        "reduced__spectrum",
        "2reduced",
        "",
    ):
        assert assistant_query._BARE_IDENTIFIER.fullmatch(near) is None, near


def test_the_recasing_is_scoped_to_the_blocker_mapping_and_reaches_no_schema_path() -> None:
    """``_humanize`` is UNTOUCHED, and that is the point rather than an omission.

    The first version of this slice put the acronym recasing inside ``_humanize``,
    which has **six other callers**, every one of them humanizing an official
    schema path — so it would have silently restyled field names across every
    assistant answer. Worse, the TypeScript mirror applies the recasing only to a
    blocker key, so the two languages would have had different blast radii while
    the parity table above asserted they agreed.

    "Qc" below is therefore DELIBERATE, not an oversight: restyling a schema path
    is a separate decision with a wider reach, and ``UX-014`` protects a path in a
    way it does not protect an internal key.
    """
    assert assistant_query._humanize("measurement.qc") == "Qc"
    assert assistant_query._humanize("system.qc_flag") == "Qc Flag"
    assert assistant_query._humanize("sample.material.formula") == "Formula"
    # ...while the blocker mapping, and only it, recases.
    assert assistant_query._blocker_display("qc_status") == "QC Status"


def test_the_acronym_recasing_is_casing_only() -> None:
    """It introduces no name: every output word comes from the input."""
    for key, shown in HUMANIZED:
        assert set(re.findall(r"[a-z0-9]+", key)) == {
            w.lower() for w in re.findall(r"[A-Za-z0-9]+", shown)
        }
