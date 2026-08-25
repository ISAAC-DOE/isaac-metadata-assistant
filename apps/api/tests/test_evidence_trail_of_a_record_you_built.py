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

    for entry in _trail(client, eid):
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
