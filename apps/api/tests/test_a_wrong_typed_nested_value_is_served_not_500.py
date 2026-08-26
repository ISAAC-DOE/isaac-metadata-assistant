"""A wrong-typed value NESTED inside a draft container must not take the record away.

WHY THIS FILE EXISTS. ``#177`` guarded the ten top-level containers and ``#179`` guarded
the ITEMS of the five top-level lists. Neither reached one level further down, and an
independent review measured six more read-path 500s at ``724ce58`` that the PR's residue
list did not name. Every one of them is the same shape: ``validate_draft`` walks a value
whose type it never asked about, raises out of the truth core, and
``Experiment.draft_ok`` turns that into an HTTP 500 over a document the reader did not
write and cannot repair from the response.

MEASURED OVER HTTP AT ``724ce58`` — ``TestClient(create_app(),
raise_server_exceptions=False)``, on a record created through ``POST /api/experiments``
with the value written into the persisted state (the only way it can come to exist; see
``_persist`` below). ``GET /api/experiments`` and ``GET /api/experiments/{id}/pending``
answered **200** in every row, which is what made the defect look smaller than it was:
the record is in the list and its questions are readable, and only opening it fails.

=================================================  ========  =======  ==========================
stored value                                       before    after    raised
=================================================  ========  =======  ==========================
``assets[0]["sha256"] = 7``                        **500**   200      ``TypeError`` (``re``)
``assets[0]["evidence"] = 7``                      **500**   200      ``TypeError``
``implicit[0]["evidence"] = 7``                    **500**   200      ``TypeError``
``block_evidence["series:s"] = 7``                 **500**   200      ``TypeError``
``descriptors_outputs[0]["descriptors"] = [7]``    **500**   200      ``AttributeError``
``series[0]["series_id"] = {"a": 1}``              **500**   200      ``TypeError`` (unhashable)
``fields["a.b"]["evidence"] = 7``                  **500**   200      ``TypeError``
=================================================  ========  =======  ==========================

TWO CORRECTIONS TO THE REVIEW'S OWN LIST, both re-measured here rather than asserted:

* ``series[0]["series_id"] = {}`` — the value the review named — answers **200** at
  ``724ce58`` and always did. ``{}`` is FALSY, so it takes the "series has no series_id"
  branch and never reaches the ``in seen_series`` membership test. The defect is real and
  the reproducing value is a TRUTHY unhashable one; both are pinned below so the
  correction cannot be lost.
* ``block_evidence["qc:status"] = 7`` reaches ``_claim_covered`` only when
  ``qc["status"]`` is truthy — the original gate was ``not qc.get("status") or not
  _claim_covered(...)``, and ``or`` short-circuits. A draft with no qc status was
  already refused before the unreadable value was ever read.

WHAT IS DELIBERATELY STILL A 500, and it is NOT an oversight — see the long note at
``draft_validator``'s contributors loop. ``attribution["contributors"]`` (a non-list, or
a list of non-mappings) still raises, because ``routes._refuse_override_payload``'s BLOCK
probe catches exactly those two exceptions to answer ``422 invalid_block_payload`` and
then filters the report to ``UPLOADED_BY_PATH`` alone — so a finding filed at
``attribution.contributors[i]`` would be DISCARDED and the malformed override would be
STORED with 200. Guarding it needs a paired change in ``routes.py``. The residue is
pinned at the bottom of this file, in both directions, so it is visible rather than
implied.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from isaac_api import experiment_repository as repo
from isaac_api import workspace as ws
from isaac_records.draft_validator import validate_draft


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _create(client: TestClient) -> str:
    resp = client.post("/api/experiments", json={"title": "nested malformed"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _persist(exp_id: str, mutate) -> None:
    """Write the value the way it can actually come to exist.

    No shipped write path produces any of these — the reachable producers are an
    operator editing the persisted state (the workspace JSON, or
    ``isaac_experiments.state``) and any future importer or migration. Editing the store
    directly is an honest reproduction of that, not a shortcut around a route that would
    refuse it.
    """
    exp = ws.load_experiment(exp_id)
    assert exp is not None
    mutate(exp.draft)
    exp.save()


#: ``(id, mutation)`` for every nested shape the review measured as a 500, plus the two
#: it did not (``fields.*.evidence``, and the corrected truthy ``series_id``).
_NESTED_MALFORMED = [
    ("assets.sha256", lambda d: d.__setitem__("assets", [{"uri": "file://x", "sha256": 7}])),
    (
        "assets.evidence",
        lambda d: d.__setitem__("assets", [{"uri": "file://x", "sha256": "a" * 64, "evidence": 7}]),
    ),
    ("implicit.evidence", lambda d: d.__setitem__("implicit", [{"about": "x", "evidence": 7}])),
    (
        "block_evidence.value",
        lambda d: (
            d.__setitem__("series", [{"series_id": "s"}]),
            d.__setitem__("block_evidence", {"series:s": 7}),
        ),
    ),
    (
        "descriptors.item",
        lambda d: d.__setitem__("descriptors_outputs", [{"descriptors": [7]}]),
    ),
    (
        "descriptors.container",
        lambda d: d.__setitem__("descriptors_outputs", [{"descriptors": 7}]),
    ),
    (
        "series_id.unhashable",
        lambda d: d.__setitem__("series", [{"series_id": {"a": 1}}]),
    ),
    (
        "fields.evidence",
        lambda d: d.__setitem__(
            "fields", {"a.b": {"value": 1, "status": "verified", "evidence": 7}}
        ),
    ),
]


@pytest.mark.parametrize("case", _NESTED_MALFORMED, ids=[c[0] for c in _NESTED_MALFORMED])
@pytest.mark.parametrize("pending_cleared", [False, True], ids=["blocked", "answered"])
def test_the_record_is_still_readable(client: TestClient, case, pending_cleared: bool):
    """The symptom, at the route that showed it.

    Both parametrizations matter. ``Experiment.export_ready`` short-circuits on
    ``pending_count() > 0``, so a reader might assume a record that still owes questions
    never reaches ``draft_ok`` — it does: the detail route composes the dry run for the
    workflow block regardless. Every row was 500 in BOTH states at ``724ce58``.
    """
    _name, mutate = case
    exp_id = _create(client)
    _persist(exp_id, lambda draft: (draft.__setitem__("pending", []) if pending_cleared else None))
    _persist(exp_id, mutate)

    detail = client.get(f"/api/experiments/{exp_id}")
    assert detail.status_code == 200, detail.text
    assert client.get("/api/experiments").status_code == 200
    assert client.get(f"/api/experiments/{exp_id}/pending").status_code == 200


@pytest.mark.parametrize("case", _NESTED_MALFORMED, ids=[c[0] for c in _NESTED_MALFORMED])
def test_the_reader_is_not_told_the_record_is_fine(client: TestClient, case):
    """THE REJECTED ALTERNATIVE. Every one of these could have been made to answer 200 by
    ignoring the value, and every such version would certify a document nobody could read
    as fit to export."""
    _name, mutate = case
    exp_id = _create(client)
    _persist(exp_id, lambda draft: draft.__setitem__("pending", []))
    _persist(exp_id, mutate)

    exp = ws.load_experiment(exp_id)
    assert exp is not None
    assert exp.draft_ok() is False
    assert exp.export_ready() is False


@pytest.mark.parametrize("case", _NESTED_MALFORMED, ids=[c[0] for c in _NESTED_MALFORMED])
def test_the_document_is_not_repaired_by_being_read(client: TestClient, case):
    """NO SILENT COERCION. Several reads later the stored draft is byte-identical."""
    import copy

    _name, mutate = case
    exp_id = _create(client)
    _persist(exp_id, mutate)
    before = copy.deepcopy(ws.load_experiment(exp_id).draft)

    for _ in range(3):
        assert client.get(f"/api/experiments/{exp_id}").status_code == 200
        assert client.get("/api/experiments").status_code == 200

    assert ws.load_experiment(exp_id).draft == before


# --- what the validator actually says -----------------------------------------


def _errors(**draft_keys) -> list[str]:
    draft = repo.blank_draft()
    draft.update(draft_keys)
    return [where for where, _ in validate_draft(draft).errors]


def test_the_qc_gate_is_not_satisfied_by_an_unreadable_series_item():
    """I6 — ``#177``'s own defect, one level down.

    ``#177`` moved the gate from ``draft.get("series")`` to the guarded ``series``
    because a truthy-but-unreadable CONTAINER satisfied it by truthiness alone, and left
    a comment saying that ``used to`` happen and produced "a claim this module is in no
    position to make, derived from the very value it just refused". The comment was false
    one level down: ``_container`` returns ``[7]`` unchanged, so ``if series:`` was still
    true. Measured at ``724ce58``: ``validate_draft({"series": [7]})`` reported
    ``['series[0]', 'qc']``.

    THE FINDING SET IS PINNED WITH ``==``, NOT ``any(...)``. The test ``#179`` added for
    the item guard asserted only that ``series[0]`` was PRESENT, which is why an extra,
    unfounded ``qc`` finding beside it was invisible. An equality assertion is the whole
    point of this test.
    """
    assert _errors(series=[7]) == ["series[0]"]
    assert _errors(series=[7, "also junk"]) == ["series[0]", "series[1]"]


def test_a_readable_spectrum_beside_a_junk_one_still_owes_a_qc_verdict():
    """THE OPPOSITE ERROR, guarded in the same breath. Suppressing the gate whenever ANY
    series item is unreadable would let a real spectrum ship without a verdict — which is
    the no-guessing rule this gate exists for. There IS a spectrum here, so there IS a
    question."""
    errors = _errors(series=[7, {"series_id": "s"}])
    assert "qc" in errors, errors
    assert "series[0]" in errors, errors


def test_a_readable_series_still_reaches_the_qc_gate():
    """The negative control for the change above: the ordinary path is untouched."""
    assert "qc" in _errors(series=[{"series_id": "s"}])


@pytest.mark.parametrize(
    "series_id, reaches_the_shape_finding",
    [
        ({"a": 1}, True),  # truthy + unhashable — the value that actually 500ed
        ([1], True),  # ditto
        (7, True),  # hashable non-string: never raised, and is refused now
        ({}, False),  # FALSY — the review's value; "no series_id" branch, always 200
        ([], False),
    ],
    ids=["dict", "list", "number", "empty-dict", "empty-list"],
)
def test_a_non_string_series_id_is_refused_rather_than_keyed(series_id, reaches_the_shape_finding):
    """Corrects the review's own reproduction, with the measurement.

    ``series_id`` is what an evidence entry is filed under (``f"series:{series_id}"``),
    so a value of another type is refused rather than coerced into a key the draft never
    wrote. The ``{}``/``[]`` rows are the correction: they are falsy, take the
    "series has no series_id" branch, and never reached the crash.
    """
    messages = [m for w, m in validate_draft({**repo.blank_draft(), "series": [{"series_id": series_id}]}).errors]
    shape = [m for m in messages if "series_id must be a string" in m]
    absent = [m for m in messages if "series has no series_id" in m]
    if reaches_the_shape_finding:
        assert shape, messages
        assert not absent, messages
    else:
        assert absent, messages
        assert not shape, messages


@pytest.mark.parametrize(
    "draft_keys, at",
    [
        ({"assets": [{"sha256": "a" * 64, "evidence": 7}]}, "assets[0] (?)"),
        ({"implicit": [{"about": "x", "evidence": 7}]}, "implicit 'x'"),
        (
            {
                "series": [{"series_id": "s"}],
                "block_evidence": {"series:s": 7},
            },
            "series[0] (s)",
        ),
        (
            {
                "links": [{"rel": "r", "target": "t", "basis": "b"}],
                "block_evidence": {"links:r|t|b": 7},
            },
            "links[0]",
        ),
    ],
    ids=["asset", "implicit", "series", "link"],
)
def test_an_unreadable_evidence_value_is_named_by_its_shape_and_never_echoed(draft_keys, at):
    """I5 — the guard's stated boundary was false, and the falsity was a live 500.

    ``_ITEM_NOUNS``' note justified stopping at the five top-level lists by claiming a
    dict container's values are "each type-checked by its reader (… ``block_evidence``
    goes through ``_claim_covered``)". ``_claim_covered`` was ``any(isinstance(e, dict)
    for e in (entries or []))`` — it ITERATED rather than type-checked. It now does what
    the comment claimed, and the comment records that it did not.
    """
    draft = repo.blank_draft()
    draft.update(draft_keys)
    messages = [m for w, m in validate_draft(draft).errors if w == at]
    assert messages, validate_draft(draft).errors
    assert any("evidence must be a list of source entries" in m for m in messages), messages
    assert any("a number" in m for m in messages), messages
    # The stored value is never handed back — only its JSON shape.
    assert not any("7" in m for m in messages), messages
    # AND no second claim is derived from it: "no evidence"/"has no evidence" would be
    # this module describing sources it just said it could not read.
    assert not any("no evidence" in m for m in messages), messages


def test_a_nested_item_is_located_at_its_REAL_position():
    """THE POSITION IS THE REPAIR INSTRUCTION, so it is pinned exactly.

    ``_mapping_items`` files at ``<container>[<index>]``, which for a top-level list is
    the whole address. A NESTED list needs its owner's index too, or every bad
    descriptor in a record files at ``descriptors[0]`` and the reader is sent to the
    wrong output. Asserted with ``==`` over the whole finding set, not with a substring:
    the defect this guards against produces a plausible-looking address, and a
    containment check accepts it.
    """
    draft = repo.blank_draft()
    draft["descriptors_outputs"] = [
        {"descriptors": [{"value": 1, "evidence": [{"source_type": "document"}]}]},
        {"descriptors": ["junk", 7]},
    ]
    assert [w for w, _ in validate_draft(draft).errors] == [
        "descriptors[1][0]",
        "descriptors[1][1]",
    ], validate_draft(draft).errors


def test_a_readable_but_uncited_claim_still_reports_no_evidence():
    """The negative control. Withholding the "no evidence" finding for an UNREADABLE
    value must not withhold it for a readable, genuinely uncited one — that finding is
    the no-guessing rule itself."""
    messages = [
        m for w, m in validate_draft({**repo.blank_draft(), "assets": [{"sha256": "a" * 64, "evidence": []}]}).errors
    ]
    assert any("no evidence" in m for m in messages), messages


@pytest.mark.parametrize("value", ["abc", {"source_type": "document"}], ids=["string", "object"])
def test_an_iterable_non_list_evidence_value_is_refused_rather_than_walked(value):
    """The two non-list shapes JSON can produce that ARE iterable. Neither ever raised —
    a string yielded characters and a dict yielded keys, and both silently answered "no
    sources". They are now refused by shape, which moves the MESSAGE and not the verdict:
    both were already FAIL."""
    messages = [
        m
        for w, m in validate_draft(
            {**repo.blank_draft(), "assets": [{"sha256": "a" * 64, "evidence": value}]}
        ).errors
        if w == "assets[0] (?)"
    ]
    assert any("evidence must be a list of source entries" in m for m in messages), messages


# --- the ONE verdict this change moves, proved rather than asserted -----------
#
# ``#177``'s disclosure needed a ``_pre_change_raised`` helper because its absolute
# "PASS -> FAIL only where the draft previously RAISED" was false for exactly one
# container, and the false absolute is what concealed it. An independent review noted
# that ``#179`` REUSED the absolute for ITEMS without extending that proof. This change
# does not reuse it: it names its exception and proves it, in both directions.


def _would_have_passed_before(draft: dict) -> bool:
    """Did the pre-change walk reach the evidence lookup for this ``series_id``?

    Derived by re-implementing the two lines the guard replaced, NOT by restating a
    conclusion — the same method ``_pre_change_raised`` uses, and written out rather
    than imported so that deleting the guard cannot make it agree by construction.
    Before the guard, a truthy ``series_id`` of ANY type went straight to
    ``series_id in seen_series`` (which raises only when the value is unhashable) and
    then to ``block_evidence[f"series:{series_id}"]`` — a key built by coercing the
    value with an f-string.
    """
    for s in draft.get("series") or []:
        series_id = s.get("series_id")
        if not series_id:
            return False
        try:
            hash(series_id)
        except TypeError:
            return False  # it RAISED before; there was no verdict to move
        key = f"series:{series_id}"
        if not any(isinstance(e, dict) for e in (draft.get("block_evidence") or {}).get(key) or []):
            return False  # it was already FAIL, for "series has no evidence"
    return True


def test_a_hashable_non_string_series_id_is_the_one_PASS_to_FAIL():
    """The exception the §13 disclosure states, demonstrated.

    ``series_id: 7`` with ``block_evidence`` carrying a covered ``"series:7"`` key never
    raised: ``7`` is hashable, and ``f"series:{7}"`` coerced it into exactly the key an
    operator had written. So this draft VALIDATED CLEAN and now FAILS. It is a flip
    toward refusal, and the reason is CLAUDE.md §5: the evidence key is a name, and
    ``str()``-ing a number into one invents a name the draft never wrote.
    """
    draft = repo.blank_draft()
    draft["meta"] = {"record_type": "measurement", "record_domain": "x", "source_type": "y"}
    draft["series"] = [{"series_id": 7}]
    draft["block_evidence"] = {"series:7": [{"source_type": "document"}]}
    draft["qc"] = {"status": "valid"}
    draft["block_evidence"]["qc:status"] = [{"source_type": "user_confirmation"}]

    # BEFORE: the walk completed and filed nothing about this series.
    assert _would_have_passed_before(draft) is True

    report = validate_draft(draft)
    assert report.ok is False
    assert [w for w, _ in report.errors] == ["series[0] (?)"], report.errors
    assert any("series_id must be a string" in m for _, m in report.errors), report.errors


def test_every_OTHER_non_string_series_id_previously_raised_or_already_failed():
    """The rest of the claim: no OTHER draft's verdict moves.

    An unhashable id raised (no verdict at all); a hashable one whose coerced key is not
    covered was already FAIL for "series has no evidence". Both are asserted through the
    reconstructed pre-change path rather than argued.
    """
    for series_id in ({"a": 1}, ["a"]):  # unhashable -> raised
        draft = {**repo.blank_draft(), "series": [{"series_id": series_id}]}
        assert _would_have_passed_before(draft) is False, series_id
    for series_id in (7, 1.5, True):  # hashable, uncovered key -> already FAIL
        draft = {**repo.blank_draft(), "series": [{"series_id": series_id}]}
        assert _would_have_passed_before(draft) is False, series_id
        assert validate_draft(draft).ok is False


def test_the_committed_synthetic_draft_verdict_is_unchanged():
    """THE NEGATIVE CONTROL every change to this module carries. A real, complete draft
    — the committed synthetic XANES fixture, which exercises assets, descriptors,
    implicit claims, a series, block evidence and attribution together — must still
    PASS, with no finding of any kind. Every guard above files at an address; a guard
    that over-fires here would be visible as an error on a document nothing was wrong
    with."""
    import json

    fixture = ws.REPO_ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"
    report = validate_draft(json.loads(fixture.read_text(encoding="utf-8")))
    assert report.ok is True, report.render()
    assert report.errors == [], report.errors


# --- the residue, named rather than implied -----------------------------------


@pytest.mark.parametrize(
    "contributors",
    [7, "abc", [1], [{"name": "n", "role": "r"}, 7]],
    ids=["number", "string", "non-mapping-item", "one-bad-item"],
)
def test_attribution_contributors_is_STILL_the_one_unguarded_walk(contributors):
    """PINNED IN THE DIRECTION IT ACTUALLY BEHAVES, so nobody "fixes" it in isolation.

    A guard here would turn ``routes._refuse_override_payload``'s ``422
    invalid_block_payload`` into a STORED malformed override, because that route's block
    probe filters the report to ``UPLOADED_BY_PATH`` and would see no findings at all.
    The raise is currently the refusal. Closing it needs the paired ``routes.py`` change,
    and this test is what will go red when that change is made — which is the point.
    """
    with pytest.raises((TypeError, AttributeError)):
        validate_draft({**repo.blank_draft(), "attribution": {"contributors": contributors}})


def test_the_override_route_still_refuses_a_wrong_typed_contributors_payload(client: TestClient):
    """The other half of the pair: the raise above is what this 422 rests on."""
    exp_id = _create(client)
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    run = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "Run 1"},
        headers={"If-Match": f'"{version}"'},
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["run"]["id"] if "run" in run.json() else run.json()["id"]
    # THE RUN's ETag, not the record's version — this route takes the run's token.
    run_view = client.get(f"/api/experiments/{exp_id}/runs/{run_id}")
    assert run_view.status_code == 200, run_view.text
    resp = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/overrides",
        json={
            "address": "block:attribution",
            "payload": {"contributors": 7},
            "confirmed_by_user": True,
        },
        headers={"If-Match": run_view.headers["ETag"]},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"] == "invalid_block_payload", resp.text
