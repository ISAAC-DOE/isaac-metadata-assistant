"""A completed record an agent can build has an evidence trail. It used to have none.

THE DEFECT THIS FILE PINS
=========================
``serialize.evidence_trail_from_draft`` walks ``draft["fields"]``, ``draft["implicit"]``
and ``draft["assets"]`` — and never ``draft["block_evidence"]`` or
``draft["descriptors_outputs"]``, which is exactly where ``complete.apply_answers``
writes the confirmations for ``series``, ``qc`` and the descriptor block. Measured over
HTTP::

    a record with NO runs, `series` answered at the record level  ->  0 entries  []
    a fully completed record, official.ok true, ready_to_export   ->  0 entries  []
    the five seeded worked examples                               ->  28, 31, 31, 31, 36

The seeds only look right because their ``fields`` map comes from a fixture sheet. A
record created through ``POST /api/experiments`` has an EMPTY ``fields`` map, so its
trail was always empty — which made ``isaac_inspect_evidence``'s description
(*"each official path, its value, the kind of support behind it, and the source file and
locator cited"*) false for the only records an agent can build.

WHAT THE FIX IS, AND WHAT IT IS NOT. The entries are added by a SECOND reader,
``serialize.confirmed_block_trail_from_draft``, composed into ``GET
/experiments/{id}/evidence``. The shared walker is deliberately untouched: widening it
would falsify ``provenance._DESCRIBED_DRAFT_KEYS``' own disclosure and would make
``conflict_resolution`` read an append-only confirmation list as two competing answers.
That argument lives in the new function's docstring; the LAST test here is its negative
control.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import tutorial_client

DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}
SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8970, 8980, 8990]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.02, 0.85, 1.45],
            }
        ],
    }
]
QC = {"status": "valid", "evidence": "I0 stable across all scans; no glitches."}


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _etag(client, eid: str) -> str:
    return client.get(f"/api/experiments/{eid}").headers["ETag"]


def _created(client) -> str:
    created = client.post("/api/experiments", json={"title": "Cu K-edge"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _answer(client, eid: str, answers: dict):
    response = client.post(
        f"/api/experiments/{eid}/answers",
        json={"confirmed_by_user": True, "answers": answers},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 200, response.text
    return response


def _trail(client, eid: str) -> list[dict]:
    response = client.get(f"/api/experiments/{eid}/evidence")
    assert response.status_code == 200, response.text
    return response.json()["evidence"]


def _paths(entries: list[dict]) -> list[str]:
    return [entry["path"] for entry in entries]


def test_a_spectrum_confirmed_on_a_created_record_appears_in_its_trail(client):
    """THE NARROWEST MEASUREMENT: one answer, one confirmation, one trail entry."""
    eid = _created(client)
    assert _trail(client, eid) == [], "a record nobody has answered has nothing to show"

    _answer(client, eid, {"series": SERIES})

    paths = _paths(_trail(client, eid))
    assert "series:averaged_spectrum" in paths, paths


def test_a_completed_record_no_longer_has_an_empty_trail_beside_ready_to_export(client):
    """THE REGRESSION TEST FOR THE WHOLE DEFECT: 0 entries beside `ready_to_export`.

    An empty evidence trail on a record the product says is ready to publish is the kind
    of surface this project treats as a defect in its own right, not as a display gap.
    """
    eid = _created(client)
    _answer(client, eid, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})

    detail = client.get(f"/api/experiments/{eid}").json()
    assert detail["status"] == "ready_to_export", detail["status"]

    entries = _trail(client, eid)
    assert entries, "a record the product calls ready to export cited no evidence at all"
    paths = _paths(entries)
    assert "qc:status" in paths, paths
    assert "series:averaged_spectrum" in paths, paths
    assert "descriptors:inflection_point_energy" in paths, paths


def test_every_confirmation_carries_readable_support_rather_than_an_empty_shell(client):
    """An entry with no evidence would be worse than no entry: it asserts support."""
    eid = _created(client)
    _answer(client, eid, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})

    entries = _trail(client, eid)
    # THE LENGTH GUARD, WHICH THIS TEST DID NOT HAVE, and its sibling above did. A `for`
    # over `[]` executes zero assertions and passes, so reverting the whole feature left
    # this test green while it read as coverage of it. The three paths are the three the
    # answer above writes, named rather than counted so a fourth namespace appearing
    # does not silently satisfy the check.
    assert {e["path"] for e in entries} >= {
        "qc:status",
        "series:averaged_spectrum",
        f"descriptors:{DESCRIPTOR['name']}",
    }, sorted(e["path"] for e in entries)

    for entry in entries:
        assert entry["evidence"], f"{entry['path']} is in the trail with no support: {entry}"
        assert entry.get("unavailable") is not True, entry
        # The STATUS is `_status_from_evidence`'s, derived from the readable entries —
        # not the literal `user_confirmation`, which is the SOURCE TYPE inside them.
        # Asserting the derived word here rather than inventing one keeps this test
        # about the trail existing, not about re-deciding what support means.
        assert entry["status"] not in (None, "", "unavailable"), entry
        assert any(
            item.get("source_type") == "user_confirmation" for item in entry["evidence"]
        ), entry


def test_EVERY_block_namespace_the_reader_serves_is_NAMED_by_every_description(client):
    """A READER THAT SERVES A NAMESPACE NOBODY DESCRIBED IS THE DEFECT THIS PR FIXES.

    `confirmed_block_trail_from_draft` walks EVERY key in `block_evidence`, and three
    surfaces — this endpoint's OpenAPI description, `isaac_inspect_evidence`'s tool
    description, and the function's own docstring — enumerated exactly *"the `qc:`,
    `series:` and `descriptors:` keys recorded when a scientist confirms a verdict, a
    spectrum or a descriptor"*. Measured across the five seeded worked examples: the
    reader also serves `attribution:` entries, two per record, and they are not
    scientist confirmations at all — they are spreadsheet citations::

        {"path": "attribution:Ada Lovelace|curated_record", "value": null,
         "status": "verified",
         "evidence": [{"source_type": "spreadsheet", "source_file": "mock_campaign.csv",
                       "locator": "Sheet 'Campaign Info', field=lead_experimenter", ...}]}

    On the two seeds whose only other new entry is `qc:status`, they are the MAJORITY of
    what this change added. *"It described two cases and there were three"* is this
    branch's own words about a sentence it withdrew; this is the same defect in the
    reader it shipped alongside.

    THIS ASSERTION IS DRIVEN BY OBSERVATION, not by the roster: it reads the namespaces
    the application actually serves and requires each to be named. The frozen roster in
    the test below is the other direction, and catches the namespace no fixture happens
    to produce.
    """
    from isaac_api.mcp.tools import TOOLS
    from isaac_api.serialize import confirmed_block_trail_from_draft

    seeded = tutorial_client(client.app)
    served: set[str] = set()
    for eid in seeded.tutorial_record_ids:
        response = seeded.get(f"/api/experiments/{eid}/evidence")
        assert response.status_code == 200, response.text
        for entry in response.json()["evidence"]:
            if ":" in entry["path"]:
                served.add(entry["path"].split(":", 1)[0])
    # ...plus a record built through the product's own path, whose namespaces the
    # seeds cannot exhibit and vice versa.
    eid = _created(client)
    _answer(client, eid, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    for entry in _trail(client, eid):
        if ":" in entry["path"]:
            served.add(entry["path"].split(":", 1)[0])

    assert "attribution" in served, "the measurement this test is built on no longer holds"
    assert {"qc", "series", "descriptors"} <= served, sorted(served)

    # The namespaces the OTHER reader owns (`assets:`, `implicit:`) are described
    # separately and are not this function's to name, so the requirement is scoped to
    # the ones THIS reader introduces.
    block_namespaces = served - {"assets", "implicit"}
    descriptions = {
        "openapi": client.get("/api/openapi").json()["paths"][
            "/api/experiments/{experiment_id}/evidence"
        ]["get"]["description"],
        "mcp": TOOLS["isaac_inspect_evidence"].description,
        "docstring": confirmed_block_trail_from_draft.__doc__ or "",
    }
    for name, text in descriptions.items():
        assert len(text) > 200, (name, len(text))
        for namespace in sorted(block_namespaces):
            assert f"`{namespace}:`" in text, (name, namespace)


def test_the_FROZEN_ROSTER_of_block_namespaces_is_complete_in_both_directions(client):
    """THE OTHER DIRECTION, and the reason a frozen constant exists at all.

    The test above can only see a namespace some fixture produces. `links:` is written
    by no fixture in this repository and is nonetheless a real key
    (`draft_validator` keys it `links:<rel>|<target>|<basis>` and
    `workspace._merge_block_evidence` merges it), so an observation-only guard would
    let it reach a scientist's trail undescribed. The roster names every namespace the
    application can write, and this asserts it in both directions: nothing served is
    outside it, and nothing in it is undescribed.

    WHY A ROSTER AND NOT A SERVING FILTER, which is the alternative the review offered.
    `_DB_RECON_*_KEYS` projects its output ONTO its allowlist, so an unlisted key is
    withheld — and that is right there, where an unlisted key would leak
    production-derived content past a visibility gate. Here it would be exactly wrong:
    withholding an unlisted namespace would silently drop a scientist's own evidence
    from their own record's trail, which is the defect this reader was built to fix,
    reintroduced through the fix. So the roster is a DOCUMENTATION ratchet: a new
    namespace still reaches the trail, and this test fails until somebody says what it
    is.
    """
    from isaac_api.mcp.tools import TOOLS
    from isaac_api.serialize import (
        BLOCK_EVIDENCE_NAMESPACES,
        confirmed_block_trail_from_draft,
    )

    assert "links" in BLOCK_EVIDENCE_NAMESPACES, BLOCK_EVIDENCE_NAMESPACES
    assert "attribution" in BLOCK_EVIDENCE_NAMESPACES, BLOCK_EVIDENCE_NAMESPACES

    seeded = tutorial_client(client.app)
    for eid in seeded.tutorial_record_ids:
        for entry in seeded.get(f"/api/experiments/{eid}/evidence").json()["evidence"]:
            if ":" not in entry["path"]:
                continue
            namespace = entry["path"].split(":", 1)[0]
            if namespace in ("assets", "implicit"):
                continue  # the sibling walker's, described with the sibling walker
            assert namespace in BLOCK_EVIDENCE_NAMESPACES, (namespace, entry["path"])

    for text in (
        client.get("/api/openapi").json()["paths"][
            "/api/experiments/{experiment_id}/evidence"
        ]["get"]["description"],
        TOOLS["isaac_inspect_evidence"].description,
        confirmed_block_trail_from_draft.__doc__ or "",
    ):
        for namespace in sorted(BLOCK_EVIDENCE_NAMESPACES):
            assert f"`{namespace}:`" in text, namespace


def test_a_block_level_entry_reads_the_same_before_and_after_export(client):
    """PARITY IS THE REASON `value` IS NULL, and it is asserted rather than asserted-about.

    `export.build_sidecar` copies `block_evidence` through verbatim and keys descriptors
    as `descriptors:<name>`; `evidence_trail_from_sidecar` resolves a value only for a
    dotted path, an `assets:` key and an `implicit:` key. Had the draft reader resolved
    values, the same record would read differently on either side of an export — on the
    one endpoint whose whole promise is that both are the same trail from the same
    source.
    """
    eid = _created(client)
    _answer(client, eid, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    before = {e["path"]: e for e in _trail(client, eid)}

    exported = client.post(
        f"/api/experiments/{eid}/export", headers={"If-Match": _etag(client, eid)}
    )
    assert exported.status_code == 200 and exported.json()["ok"] is True, exported.text
    after = {e["path"]: e for e in _trail(client, eid)}

    for path in ("qc:status", "series:averaged_spectrum", "descriptors:inflection_point_energy"):
        assert path in before and path in after, (path, sorted(before), sorted(after))
        assert before[path]["value"] is None, before[path]
        assert after[path]["value"] is None, after[path]
        assert before[path]["status"] == after[path]["status"], (before[path], after[path])


def test_the_trail_invents_nothing_for_a_block_nobody_confirmed(client):
    """NEGATIVE CONTROL. The reader must not manufacture an entry per known block name.

    A trail that lists `qc:status` for a record with no verdict would be exactly the
    §5 violation this whole file is about, with the polarity reversed.
    """
    eid = _created(client)
    _answer(client, eid, {"series": SERIES})

    paths = _paths(_trail(client, eid))
    # THE POSITIVE HALF, WHICH THIS TEST DID NOT HAVE. Both assertions below are true of
    # an EMPTY trail, so reverting the feature left this test green — a negative control
    # that passes when the thing it controls does not exist controls nothing. The
    # spectrum WAS confirmed, so it must be present for the absences to mean anything.
    assert "series:averaged_spectrum" in paths, paths
    assert "qc:status" not in paths, paths
    assert not any(p.startswith("descriptors:") for p in paths), paths


def test_a_malformed_block_becomes_one_unavailable_entry_not_a_lost_trail(client):
    """Per-item isolation, the rule the sibling reader already follows.

    One unreadable block must not take the whole trail down, and must not vanish either
    — its absence from a scientist's evidence has to be visible.
    """
    from isaac_api.serialize import confirmed_block_trail_from_draft

    entries = confirmed_block_trail_from_draft(
        {
            "block_evidence": {"qc:status": [{"kind": "user_confirmation"}], "series:s1": 7},
            "descriptors_outputs": [{"descriptors": ["not-a-descriptor"]}, "not-a-block"],
        }
    )
    by_path = {e["path"]: e for e in entries}
    assert by_path["qc:status"].get("unavailable") is not True, by_path["qc:status"]
    assert by_path["series:s1"]["unavailable"] is True, by_path["series:s1"]
    assert any(p.startswith("descriptors:#") for p in by_path), sorted(by_path)
    for path, entry in by_path.items():
        if entry.get("unavailable"):
            assert entry["unavailable_reason"], path
            assert entry["value"] is None and entry["evidence"] == [], path


def test_an_UNEVIDENCED_descriptor_gets_NO_ENTRY_rather_than_an_empty_shell(client):
    """THE ONE GATE IN THIS READER THAT NO TEST EXERCISED, and its own comment says why
    it matters: an entry with empty support *"would read as the opposite of the truth"*.

    Measured before this test existed: deleting `if not payload: continue` from
    `confirmed_block_trail_from_draft` makes it emit

        {"path": "descriptors:e0", "value": null, "status": "verified", "evidence": []}

    — a trail entry asserting a descriptor is supported, with `status: verified`, over no
    support at all — and **0 of 4,344 backend tests failed.** The sibling assertion
    "every entry carries readable support" only walks entries that exist, so it cannot
    see an entry that should not.

    `export.build_sidecar`'s own `if d.get("evidence")` gate is the parity this matches:
    an unevidenced descriptor is absent from the sidecar too, so present-here /
    absent-there would break the before/after-export promise as well.
    """
    from isaac_api.serialize import confirmed_block_trail_from_draft

    entries = confirmed_block_trail_from_draft(
        {
            "descriptors_outputs": [
                {
                    "descriptors": [
                        {"name": "e0", "value": 7112.0},  # no `evidence` key at all
                        {"name": "e0_empty", "value": 1.0, "evidence": []},
                        {
                            "name": "e0_supported",
                            "value": 2.0,
                            "evidence": [{"source_type": "user_confirmation"}],
                        },
                    ]
                }
            ]
        }
    )

    paths = [e["path"] for e in entries]
    # THE POSITIVE CONTROL FIRST, so an over-broad gate cannot make this test pass by
    # emitting nothing at all.
    assert paths == ["descriptors:e0_supported"], entries
    assert entries[0]["evidence"], entries[0]
    # AND NOTHING IN THE TRAIL EVER CARRIES A STATUS OVER NO SUPPORT.
    for entry in entries:
        if not entry.get("unavailable"):
            assert entry["evidence"], entry


def test_a_non_dict_block_evidence_container_is_one_bundle_level_failure(client):
    """"The container is not a container" is one fact, not N per-item facts."""
    from isaac_api.serialize import confirmed_block_trail_from_draft

    entries = confirmed_block_trail_from_draft({"block_evidence": "not-a-map"})

    assert len(entries) == 1, entries
    assert entries[0]["path"] == "block_evidence"
    assert entries[0]["unavailable"] is True


def test_the_shared_walker_is_deliberately_unchanged(client):
    """NEGATIVE CONTROL for the design choice, and it is the one that guards two modules.

    `provenance._DESCRIBED_DRAFT_KEYS` is `{fields, implicit, assets}` and exists so that
    module can OWN UP TO the blocks it does not describe; a test elsewhere pins it against
    `evidence_trail_from_draft`'s own source. `conflict_resolution` reads the same walker
    to find two distinct answers at one address, and `block_evidence["qc:status"]` is
    APPEND-ONLY — folding it in would manufacture a conflict out of one scientist
    answering one question twice.

    So the fix is composed at the endpoint. If a later slice moves the block reader INTO
    the walker, this fails, and the two modules above are what it is telling that slice
    to go and look at.
    """
    from isaac_api.provenance import _DESCRIBED_DRAFT_KEYS
    from isaac_api.serialize import evidence_trail_from_draft

    assert _DESCRIBED_DRAFT_KEYS == frozenset({"fields", "implicit", "assets"})
    assert (
        evidence_trail_from_draft(
            {
                "block_evidence": {"qc:status": [{"kind": "user_confirmation"}]},
                "descriptors_outputs": [
                    {"descriptors": [{"name": "d", "evidence": [{"kind": "user_confirmation"}]}]}
                ],
            }
        )
        == []
    ), "the shared walker started reading the block keys; read this docstring"
