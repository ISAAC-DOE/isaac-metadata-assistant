"""A wrong-typed TOP-LEVEL draft container is a validation FINDING, not an exception.

WHY THIS FILE EXISTS. ``validate_draft`` walked every top-level container it knows
about without asking what type it was, so a persisted draft whose ``assets`` is a
string reached ``asset.get("sha256")`` and raised ``AttributeError``. Measured over
HTTP on ``721238a``, on a record with nothing pending (so ``Experiment.export_ready``
reaches ``draft_ok``)::

    <workspace>/<id>/state.json  draft["assets"] = "not a list"
    GET /api/experiments/{id}   -> 500

NOT ALL TEN BEHAVED THE SAME WAY, and this docstring said they did until an
independent review measured otherwise. The correction is recorded rather than
silently applied, because the false version concealed the one verdict this change
moves. Measured on ``721238a``, one truthy wrong-typed container at a time:

* **Eight raised unconditionally** — ``meta``, ``fields``, ``attribution``,
  ``assets``, ``descriptors_outputs``, ``implicit``, ``series``, ``links`` — with
  the exception class depending only on whether the wrong type happened to be
  iterable (``TypeError``) or not (``AttributeError``).
* ``qc`` raised only when a series was present, because that is the only thing
  that reads it. The new guard sits inside the SAME ``if series:``, so ``qc``
  behaves identically before and after.
* ``block_evidence`` raised only when a series, a link, a contributor or the qc
  gate looked it up. **A draft with none of those validated CLEAN**, and now
  reports a finding: ``ok`` True -> False, ``Experiment.draft_ok()`` True ->
  False. That is the ONE verdict this change moves, and it moves toward refusal
  on a document that could never have exported — ``export.build_sidecar`` does
  ``(draft.get("block_evidence") or {}).items()``, so it raised out of
  ``export_draft``. Nothing that previously EXPORTED stops exporting.

``_base_draft`` below supplies a ``series``, which is what makes ``qc`` reachable
and is justified for ``qc``. It ALSO makes ``block_evidence`` reachable, which is
why this file's own table could not see the distinction above — the eleventh row
looked like a confirmation. ``test_block_evidence_alone_is_the_one_verdict_this_moves``
covers the case the table cannot.

THE DESIGN. ``validate_draft``'s job is to answer "is this draft fit to become an
official record, and if not, where is it wrong". For a container of the wrong type
the answer is *no, here*: that is a REPORT, and raising instead denies the reader
the answer their record's own validator was asked for. The container is then
treated as EMPTY for the rest of the pass — not coerced, not guessed at, not
walked for per-position claims that would be invented out of a string's characters
(``serialize.py``'s per-item isolation note calls that "a fabricated partial
success, which is worse than the failure it replaced").

WHAT IS DELIBERATELY *NOT* CHANGED, and is pinned at the bottom of this file:
NESTED payloads still raise. ``routes._probe_override`` catches exactly that
(``_PROBE_STRUCTURAL_ERRORS``) to turn a malformed *request* into a typed 422, and
that branch must stay reachable. A request can be refused because the caller sent
it; a persisted document cannot be refused to the reader who did nothing wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_records.draft_validator import (
    _TOP_LEVEL_CONTAINERS,
    DraftReport,
    validate_draft,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"

#: One wrong value per JSON type that is NOT the expected container type, and that is
#: TRUTHY — a falsy wrong type (``0``, ``""``, ``False``) has always been normalised to
#: the empty container by the ``or {}`` / ``or []`` this code has carried since it was
#: written, and that tolerance is deliberately preserved rather than tightened here.
_WRONG_VALUES: tuple[object, ...] = (7, 1.5, True, "a string", ["a", "list"], {"a": "map"})


def _wrong_for(expected: type) -> list[object]:
    return [v for v in _WRONG_VALUES if not isinstance(v, expected)]


def _base_draft() -> dict:
    """A draft minimal enough to be uninteresting, complete enough that EVERY container
    in the table is actually reached.

    ``series`` is present because the ``qc`` container is read only behind ``if
    series:`` — a validator that never looks at ``qc`` on a series-less draft is
    behaving correctly, and a table-driven test that did not supply one would have
    reported that correctness as a missing guard."""
    return {
        "meta": {"record_type": "measurement", "record_domain": "x", "source_type": "y"},
        "series": [{"series_id": "s1"}],
    }


@pytest.mark.parametrize("name", sorted(_TOP_LEVEL_CONTAINERS))
def test_a_wrong_typed_container_is_reported_and_never_raises(name: str):
    """Every declared container, every wrong type: a report, filed AT that container."""
    expected = _TOP_LEVEL_CONTAINERS[name]
    for bad in _wrong_for(expected):
        draft = {**_base_draft(), name: bad}
        report = validate_draft(draft)  # must not raise
        assert isinstance(report, DraftReport), (name, bad)
        assert not report.ok, f"{name}={bad!r} was accepted as valid"
        assert any(where == name for where, _ in report.errors), (
            f"{name}={bad!r} produced no finding filed at {name!r}: {report.errors}"
        )


@pytest.mark.parametrize("name", sorted(_TOP_LEVEL_CONTAINERS))
def test_the_finding_names_the_shape_and_never_quotes_the_stored_value(name: str):
    """The reader is told WHAT SHAPE was found, never handed the content back.

    ``serialize.py``'s ``_JSON_KIND`` took the same decision for the same reason: a
    stored value interpolated into a message is arbitrary content rendered as though
    it were the validator's own words.
    """
    expected = _TOP_LEVEL_CONTAINERS[name]
    secret = "SENSITIVE-VALUE-THAT-MUST-NOT-BE-ECHOED"
    bad = [secret] if expected is dict else {secret: 1}
    report = validate_draft({**_base_draft(), name: bad})
    messages = [m for where, m in report.errors if where == name]
    assert messages, (name, report.errors)
    assert not any(secret in m for m in messages), messages


def test_a_falsy_wrong_type_keeps_its_long_standing_empty_normalisation():
    """UNCHANGED BEHAVIOUR, asserted so a future edit cannot tighten it by accident.

    ``draft.get("assets") or []`` has always read ``0``, ``""`` and ``False`` as "no
    assets". That is not obviously right, but it is not this fix's to change: it is
    the same normalisation ``_hydrate_notes`` applies ("a top-level value that is not
    a list yields no notes at all"), and altering it would change the verdict on
    drafts nobody reported a defect about.
    """
    for falsy in (0, "", False, None, [], {}):
        report = validate_draft({"assets": falsy})
        assert not any(where == "assets" for where, _ in report.errors), (falsy, report.errors)


def test_a_wrong_typed_series_does_not_manufacture_a_second_qc_finding():
    """ONE finding about the real problem, not a second one derived from it.

    ``if draft.get("series"):`` gates "measurement has series but qc verdict has no
    evidence". A truthy-but-unreadable ``series`` used to satisfy that gate by
    truthiness alone; a finding about the QC verdict of a spectrum that cannot be
    read is a claim this module is in no position to make.
    """
    report = validate_draft({"series": "not a list"})
    wheres = [w for w, _ in report.errors]
    assert "series" in wheres, report.errors
    assert "qc" not in wheres, report.errors


def test_a_well_formed_draft_is_completely_unaffected():
    """THE NEGATIVE CONTROL. The committed synthetic XANES draft validates exactly as
    it did — same errors, same warnings, same order — so no well-formed draft's
    verdict moved."""
    draft = json.loads(FIXTURE.read_text())
    report = validate_draft(draft)
    assert report.ok, report.errors
    assert report.errors == []


def test_export_is_refused_rather_than_crashing_and_nothing_new_becomes_exportable():
    """The §13 disclosure, asserted: exported-record behaviour did not change.

    ``export_draft`` validates FIRST and returns early when the report is not ok, so a
    malformed container produces a clean refusal carrying the finding, and ``transform``
    is never reached. Nothing that previously exported stops exporting, and nothing new
    starts.

    ``root`` is only where ``export_draft`` LOOKS UP the vendored schema; it writes
    nothing, so the repository root is the right argument and no file is created."""
    from isaac_records.export import export_draft

    draft = json.loads(FIXTURE.read_text())
    good = export_draft(dict(draft), ROOT, record_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert good.ok, good.draft_report.errors

    broken = dict(draft)
    broken["assets"] = "not a list"
    result = export_draft(broken, ROOT, record_id="01ARZ3NDEKTSV4RRFFQ69G5FAW")
    assert result.ok is False
    assert any(where == "assets" for where, _ in result.draft_report.errors), result.draft_report.errors


# --- what is deliberately NOT widened ----------------------------------------


def test_a_nested_malformed_payload_still_raises_so_the_route_probe_stays_reachable():
    """``routes._probe_override`` DEPENDS on this, in two places.

    It calls ``validate_draft`` on a one-key probe draft and catches
    ``_PROBE_STRUCTURAL_ERRORS`` to answer a typed 422 — the honest answer for a
    malformed REQUEST, which the caller can fix. Widening the guard into nested
    payloads would make both ``except`` branches dead and would replace a refusal the
    caller can act on with a stored-and-later-refused override. The read-path fix and
    the request-path refusal are different answers to different questions, on purpose.
    """
    with pytest.raises(TypeError):
        validate_draft({"fields": {"a.b": {"value": 1, "status": "verified", "evidence": 7}}})
    with pytest.raises(TypeError):
        validate_draft({"attribution": {"contributors": 7}})


def test_a_wrong_typed_ITEM_inside_a_well_formed_list_still_raises():
    """FOUND AND DELIBERATELY NOT FIXED, recorded here so it is not mistaken for covered.

    ``{"assets": [7]}`` is a per-ITEM malformation, not a container one, and it still
    raises ``AttributeError``. Closing it correctly means deciding what a per-item
    degradation SAYS — ``serialize.py`` answers that with ``unavailable`` +
    ``unavailable_reason`` on a served entry, which is a larger design decision with a
    response contract attached. This test pins the current behaviour so the gap is
    visible; invert it when that decision is made.
    """
    with pytest.raises(AttributeError):
        validate_draft({"assets": [7]})


# --- the one verdict this change moves ---------------------------------------
#
# The parametrised table above supplies a `series`, which is what makes `qc`
# reachable. It ALSO makes `block_evidence` reachable, so the table's
# `block_evidence` row is a confirmation on a draft where that container really did
# raise before. It cannot see the case where it did not, and that case is the only
# draft in the repository whose VERDICT this change moves. These three tests cover it.


def _pre_change_raised(draft: dict) -> bool:
    """Did `validate_draft` raise on `721238a` for this draft?

    Derived by REMOVING the guard, not by restating a conclusion: the guard's whole
    effect is that a truthy wrong-typed container is replaced by an empty one, so the
    pre-change path is the same walk with `draft.get(name) or expected()` in place of
    `_container(...)`. This mirrors the file at the branch point closely enough to
    answer the one question asked of it — did the walk reach a `.get` on the wrong
    type — and it is written out rather than imported so that deleting the guard
    cannot make it agree by construction.
    """
    attribution = draft.get("attribution")
    contributors = attribution.get("contributors") if isinstance(attribution, dict) else None
    block_evidence_readers = (
        bool(draft.get("series")) or bool(draft.get("links")) or bool(contributors)
    )
    for name, expected in _TOP_LEVEL_CONTAINERS.items():
        raw = draft.get(name)
        if not raw or isinstance(raw, expected):
            continue
        if name == "qc" and not draft.get("series"):
            continue  # only read behind `if series:`
        if name == "block_evidence" and not block_evidence_readers:
            continue  # only read by the series/links/contributors/qc lookups
        return True
    return False


def test_block_evidence_alone_is_the_one_verdict_this_moves():
    """A truthy non-object `block_evidence` with nothing that reads it: PASS -> FAIL.

    This is the single draft-verdict change in the whole guard, and it was concealed
    for one revision by a claim that "all ten containers raised". They did not.
    """
    draft = {
        "meta": {"record_type": "measurement", "record_domain": "x", "source_type": "y"},
        "fields": {},
        "block_evidence": "free text an operator typed",
    }
    assert _pre_change_raised(draft) is False, "this draft did NOT raise before the guard"

    report = validate_draft(draft)
    assert report.ok is False
    assert [where for where, _ in report.errors] == ["block_evidence"]


def test_the_qc_container_behaves_identically_before_and_after():
    """`qc` is read only behind `if series:`, and the guard is inside that same branch.

    So a series-less draft with a wrong-typed `qc` validated clean before and validates
    clean now — no finding is filed about the QC verdict of a spectrum that does not
    exist. Stated as a test because the corrected disclosure claims it.
    """
    draft = {
        "meta": {"record_type": "measurement", "record_domain": "x", "source_type": "y"},
        "fields": {},
        "qc": "not an object",
    }
    assert _pre_change_raised(draft) is False
    report = validate_draft(draft)
    assert report.ok is True, report.errors


@pytest.mark.parametrize(
    "name",
    sorted(set(_TOP_LEVEL_CONTAINERS) - {"qc", "block_evidence"}),
)
def test_the_other_eight_containers_raised_unconditionally(name: str):
    """The corrected disclosure says EIGHT raised with nothing else in the draft. Pinned.

    If a future change makes one of these reachable only conditionally, this fails and
    the disclosure is re-examined instead of being taken on trust.
    """
    expected = _TOP_LEVEL_CONTAINERS[name]
    minimal = {
        "meta": {"record_type": "measurement", "record_domain": "x", "source_type": "y"},
        "fields": {},
    }
    for bad in _wrong_for(expected):
        draft = {**minimal, name: bad}
        assert _pre_change_raised(draft) is True, (name, bad)
        report = validate_draft(draft)
        assert report.ok is False
        assert any(where == name for where, _ in report.errors), (name, bad, report.errors)


def test_a_draft_that_could_never_have_exported_is_the_only_one_that_flips():
    """The flip is toward refusal on an already-unexportable document — verify, don't assert.

    `export.build_sidecar` does `(draft.get("block_evidence") or {}).items()`, so the
    flipping draft raised `AttributeError` out of `export_draft` on `721238a`. It never
    produced a record. The guard converts that third crash into a clean refusal, which
    is why "nothing that previously exported stops exporting" holds.
    """
    import inspect

    from isaac_records import export

    source = inspect.getsource(export.build_sidecar)
    assert 'draft.get("block_evidence") or {}' in source, (
        "build_sidecar no longer normalises block_evidence with `or {}`; the claim that "
        "the flipping draft was already unexportable must be re-measured"
    )
    with pytest.raises(AttributeError):
        export.build_sidecar({"block_evidence": "free text"}, {})
