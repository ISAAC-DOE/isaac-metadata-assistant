"""`DEC-46` / `DOM-001` — number 32 is TWO ACQUISITIONS, and preferring one is forbidden.

**THIS FILE IS THE WHOLE POINT OF `DOM-001`.** The reconstruction layer already preserved
both files and surfaced the disagreement; what did not exist was a test that fails when a
later slice decides to tidy it up. So these tests are written against the tidy-up rather
than against the current behaviour: each one names the plausible "improvement" it exists
to refuse.

**THE TEMPTING IMPROVEMENT IS SPECIFIC AND IT HAS EVIDENCE BEHIND IT.** The beamtime
document's own final log matches one of the two readings and the other matches nothing in
it — which is real, measured, and STILL NOT AN ANSWER. `DEC-46`: *"preferring either one
is forbidden, including by 'the document says so'."* Whether the number was deliberately
reused, whether one file is superseded or mislabelled, and whether the number is unique
at all are `Q16` and remain the domain owner's. A slice that dropped the file the document
does not mention would be discarding an acquisition on evidence that was weighed and
explicitly ruled insufficient — which is why the refusal is a test and not a comment.

The fixture stems are SYNTHETIC (`ZZ2`, not any real sample code); the structure they
reproduce — one legacy number on two acquisitions differing only in cycling state — is
the real one, and the committed fixture
``tests/fixtures/bl15/filenames/duplicate-legacy-number-set.txt`` says so in its own
first line.
"""

from __future__ import annotations

import hashlib

from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import relate as R
from isaac_api.bl15.inventory import SourceRecord

#: The two readings, as the real corpus carries them, with a synthetic sample code.
#: `1400` and `1500` are filename TOKENS — the only category the corpus-characterization
#: document's §0 permits reproducing, and both are already committed in the fixture.
EARLIER = "32_03_ZZ2_base_after1400Cycling_filter20_1500mV"
MATCHES_THE_LOG = "32_03_ZZ2_base_after1500Cycling_filter20_1500mV"


def rec(path: str, *, content: str) -> SourceRecord:
    basename = path.rsplit("/", 1)[-1]
    body = content.encode("utf-8")
    return SourceRecord(
        archive_path=path,
        basename=basename,
        extension=basename.rsplit(".", 1)[1].lower() if "." in basename else "",
        size_bytes=len(body),
        content_sha256=hashlib.sha256(body).hexdigest(),
        parent_dir=path.rsplit("/", 1)[0] if "/" in path else "",
        depth=path.count("/"),
    )


def an_acquisition(stem: str):
    """An acquisition plus its byte-identical `_dir` copy, as the real archive has."""
    body = f"#F {stem}\n"
    entries = [rec(stem, content=body), rec(f"{stem}_dir/{stem}", content=body)]
    classifications = {
        stem: ev.SOURCE_TYPE_SPEC_ACQUISITION,
        f"{stem}_dir/{stem}": ev.SOURCE_TYPE_SPEC_ACQUISITION,
    }
    return entries, classifications


def both_of_them():
    a, ca = an_acquisition(EARLIER)
    b, cb = an_acquisition(MATCHES_THE_LOG)
    return R.relate(entries=a + b, classifications=ca | cb)


# --- both survive, and the count is the assertion ---------------------------


def test_both_acquisitions_become_units_and_neither_is_dropped():
    """The tidy-up this refuses: collapsing them to one unit keyed by the number.

    A legacy number is NOT a key, and 32 is the corpus's own proof. Asserted as the
    exact stem set rather than as ``len(units) == 2``, because a slice that kept one
    file and created a second unit for something else would pass a count.
    """
    out = both_of_them()
    assert sorted(u.stem for u in out.units) == sorted([EARLIER, MATCHES_THE_LOG])
    assert len(out.units) == 2
    for unit in out.units:
        assert unit.legacy_number == 32


def test_the_document_matching_reading_is_given_no_precedence_anywhere():
    """**The specific tidy-up `DEC-46` forbids by name.**

    ``after1500Cycling`` matches the beamtime document's final log; ``after1400Cycling``
    matches nothing in it. If any ordering, flag, ranking or field in the reconstruction
    started to express that, this test is where it would show up: neither unit carries a
    preference, and the conflict names both readings with equal standing.
    """
    out = both_of_them()
    conflicts = [
        c for c in out.corpus_conflicts if c.kind == R.CONFLICT_DUPLICATE_LEGACY_NUMBER
    ]
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.subject == "32"

    values = sorted(r.value for r in conflict.readings)
    assert values == sorted([EARLIER, MATCHES_THE_LOG])
    # the conflict is UNRESOLVED, and there is exactly one way for it to be so
    assert conflict.unresolved_reason == R.UNRESOLVED_SOURCES_DISAGREE
    # no reading is marked as authoritative — there is no field for it, and adding one
    # would be the defect
    assert not any(
        hasattr(r, "preferred") or hasattr(r, "authoritative")
        for r in conflict.readings
    )


def test_the_provenance_states_the_prohibition_rather_than_implying_it():
    """`DOM-001`'s provenance half: the rule travels with the conflict.

    A scientist reading the conflict is told not merely that nothing was chosen but that
    choosing is forbidden, and WHY a matching log does not settle it. That sentence is
    stored (``LEGACY_NUMBER_REUSE_RULE``) rather than written at the call site, so it
    has one home.
    """
    out = both_of_them()
    conflict = next(
        c for c in out.corpus_conflicts if c.kind == R.CONFLICT_DUPLICATE_LEGACY_NUMBER
    )
    explanation = conflict.explanation
    assert R.LEGACY_NUMBER_REUSE_RULE in explanation
    assert "neither is the 'real' one" in explanation
    for phrase in (
        "Both acquisitions are preserved",
        "Neither file may be overwritten, dropped, merged, or preferred",
        "narrows the question without answering it",
    ):
        assert phrase in explanation, phrase


def test_the_question_is_named_and_its_answer_is_that_nobody_knows():
    """`Q16`: ~~still the domain owner's~~ — ANSWERED 2026-09-22 as "I do not know".

    INVERTED rather than deleted. It asserted the question was OPEN; the domain owner
    has since replied that he does not recall whether the two acquisitions are two
    conditions or a typo. That closes the QUESTION and makes the CONFLICT permanent —
    which is the property this file exists for, and it is asserted more strongly now:
    the disposition itself says nothing is ever chosen, and the question id stays on
    the concept that anchors it, so a future session does not re-ask it.
    """
    assert "Q16" not in mp.open_domain_questions()
    question = mp.DOMAIN_QUESTIONS["Q16"]
    assert question.disposition == mp.QUESTION_DOMAIN_OWNER_DOES_NOT_KNOW
    note = question.note
    assert "PERMANENTLY PRESERVED" in note
    assert "neither is preferred" in note
    assert "never the legacy number alone" in note
    entry = mp.mapping_for(ev.CONCEPT_LEGACY_NUMBER)
    assert entry.domain_questions == ("Q16",)


def test_the_files_are_never_called_duplicates_of_each_other():
    """`DEC-46` retires this repository's own *"two duplicate 32 files"* wording.

    The WIRE VALUE keeps its spelling — ``duplicate_legacy_number`` describes a
    duplicated NUMBER, and renaming it would change a contract a client keys on to fix
    a sentence. What must not survive is prose calling the ACQUISITIONS duplicates, so
    the served explanation is checked directly.
    """
    out = both_of_them()
    conflict = next(
        c for c in out.corpus_conflicts if c.kind == R.CONFLICT_DUPLICATE_LEGACY_NUMBER
    )
    assert "neither is a duplicate of the other" in conflict.explanation
    # the kind is about the number, and the wire value is pinned so a rename is a
    # deliberate contract change rather than a tidy-up
    assert R.CONFLICT_DUPLICATE_LEGACY_NUMBER == "duplicate_legacy_number"
    # nothing in the SERVED sentence says the FILES are duplicates
    lowered = conflict.explanation.lower()
    assert "duplicate files" not in lowered
    assert "duplicate acquisitions" not in lowered


def test_one_number_collides_and_its_unremarkable_neighbours_do_not():
    """A conflict list with false entries in it is a list a scientist stops reading.

    So the neighbours from the committed fixture are included: only 32 must collide.
    """
    entries: list[SourceRecord] = []
    classifications: dict[str, str] = {}
    for stem in (
        EARLIER,
        MATCHES_THE_LOG,
        "31_03_ZZ2_base_after1500Cycling_filter20_1200mV",
        "33_03_ZZ2_base_after1400cycling_filter20_1600mV",
    ):
        e, c = an_acquisition(stem)
        entries += e
        classifications |= c
    out = R.relate(entries=entries, classifications=classifications)

    assert len(out.units) == 4
    subjects = [
        c.subject
        for c in out.corpus_conflicts
        if c.kind == R.CONFLICT_DUPLICATE_LEGACY_NUMBER
    ]
    assert subjects == ["32"]


def test_the_committed_fixture_still_carries_both_readings():
    """A fixture that lost one of the two would make every test above vacuous.

    Checked against the file rather than the constants in this module, because the
    fixture is the thing a future "cleanup" would prune.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    text = (
        root
        / "tests"
        / "fixtures"
        / "bl15"
        / "filenames"
        / "duplicate-legacy-number-set.txt"
    ).read_text(encoding="utf-8")
    stems = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    thirty_twos = [s for s in stems if s.startswith("32_")]
    assert len(thirty_twos) == 2
    assert sorted(thirty_twos) == sorted([EARLIER, MATCHES_THE_LOG])
    # and the fixture says in its own words that it is synthetic
    assert text.splitlines()[0].startswith("# SYNTHETIC")
