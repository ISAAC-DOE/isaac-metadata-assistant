"""Phase-4 completion: apply simulated human answers to a draft's pending[] blockers.

`complete.apply_answers` is pure and non-truth: it consumes `draft["pending"]`, applies
ONLY values present in the answers fixture (each recorded as user_confirmation evidence),
and never invents a sha256, series point, descriptor, or edge. These tests assert every
applied value traces back to the fixture — not to the system.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from isaac_records.complete import apply_answers
from isaac_records.extract.draft_builder import build_draft

REPO_ROOT = Path(__file__).resolve().parent.parent
SYN = REPO_ROOT / "tests" / "fixtures" / "synthetic"
CSV_PATH = SYN / "mock_campaign.csv"
LISTING_PATH = SYN / "raw_scan_listing.txt"
ANSWERS_PATH = SYN / "xanes_completion_answers.json"


def _draft():
    return build_draft(CSV_PATH, LISTING_PATH)


def _answers():
    return json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))


def test_apply_answers_consumes_pending_deterministically():
    draft = _draft()
    answers = _answers()
    completed = apply_answers(draft, answers)

    # Every blocker resolved -> pending is empty.
    assert completed["pending"] == []

    # 3 assets, each with the sha256 FROM the fixture (asserted, not invented) and
    # BOTH file_listing + user_confirmation evidence.
    assert len(completed["assets"]) == 3
    by_uri = {a["uri"]: a for a in completed["assets"]}
    for uri, sha in answers["asset_sha256"].items():
        asset = by_uri[uri]
        assert asset["sha256"] == sha  # equality with the fixture, not a fabrication
        source_types = {e["source_type"] for e in asset["evidence"]}
        assert "file_listing" in source_types
        assert "user_confirmation" in source_types
        uc = next(e for e in asset["evidence"] if e["source_type"] == "user_confirmation")
        assert uc["answer"] == sha
        assert uc["timestamp"] == answers["timestamp"]

    # series is exactly the fixture series.
    assert completed["series"] == answers["series"]

    # descriptors_outputs carries the fixture descriptor (value from the fixture).
    outputs = completed["descriptors_outputs"]
    assert len(outputs) == 1
    descriptors = outputs[0]["descriptors"]
    assert len(descriptors) == 1
    desc = descriptors[0]
    assert desc["name"] == answers["descriptor"]["name"]
    assert desc["value"] == answers["descriptor"]["value"]
    assert desc["uncertainty"] == answers["descriptor"]["uncertainty"]
    assert desc["evidence"][0]["source_type"] == "user_confirmation"
    assert desc["evidence"][0]["answer"] == str(answers["descriptor"]["value"])

    # the implicit edge is now the confirmed answer value.
    edge = next(i for i in completed["implicit"] if i["about"] == "edge")
    assert edge["value"] == answers["edge"] == "K"
    edge_sources = {e["source_type"] for e in edge["evidence"]}
    assert {"derivation", "user_confirmation"} <= edge_sources


def test_apply_answers_is_pure_and_fills_only_intended_fields():
    draft = _draft()
    before = copy.deepcopy(draft)
    answers = _answers()

    completed = apply_answers(draft, answers)

    # Input draft is not mutated (deepcopy contract).
    assert draft == before

    # completion only touches assets/series/descriptors/pending/implicit-edge:
    # the fields dict is byte-equal to the pre-completion fields.
    assert completed["fields"] == before["fields"]
    assert json.dumps(completed["fields"], sort_keys=True) == json.dumps(
        before["fields"], sort_keys=True
    )


def test_unanswered_blocker_stays_pending():
    draft = _draft()
    answers = _answers()

    # Drop one asset sha256 (the reduced .xdi) -> that blocker cannot resolve.
    dropped_uri = "ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi"
    partial = copy.deepcopy(answers)
    del partial["asset_sha256"][dropped_uri]

    completed = apply_answers(draft, partial)

    # The dropped asset is NOT in assets and its blocker REMAINS pending.
    asset_uris = {a["uri"] for a in completed["assets"]}
    assert dropped_uri not in asset_uris
    assert len(completed["assets"]) == 2

    still_pending = [p for p in completed["pending"] if p.get("uri") == dropped_uri]
    assert len(still_pending) == 1
    assert still_pending[0]["blocker"] == "sha256"

    # Nothing was invented to fill the gap.
    for a in completed["assets"]:
        assert a["sha256"] in partial["asset_sha256"].values()


def test_series_answer_writes_block_evidence():
    draft = _draft()
    answers = _answers()
    completed = apply_answers(draft, answers)

    be = completed["block_evidence"]
    key = "series:averaged_spectrum"
    assert key in be, sorted(be)
    entries = be[key]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_type"] == "user_confirmation"
    assert entry["timestamp"] == answers["timestamp"]


def test_valid_sha256_accepted():
    # A well-formed 64-char lowercase hex sha256 applies successfully and carries a
    # user_confirmation entry (guard for the next slice's rejection logic).
    import re

    draft = _draft()
    answers = _answers()
    completed = apply_answers(draft, answers)

    assert len(completed["assets"]) == 3
    for asset in completed["assets"]:
        assert re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
        uc = next(e for e in asset["evidence"] if e["source_type"] == "user_confirmation")
        assert uc["answer"] == asset["sha256"]
