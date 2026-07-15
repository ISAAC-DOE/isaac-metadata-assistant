"""Honest audit coverage: expected targets are enumerated from RECORD content
(scalars by dict-only traversal + one block target per series/qc/link/asset/
descriptor/contributor), not from the sidecar's own keys.

This is the Phase-21D denominator: a record whose spectrum, qc verdict, or
contributors carry no evidence can never audit at full coverage, and evidence
claiming objects the record does not have surfaces as dangling.
"""

from __future__ import annotations

import json
from pathlib import Path

from isaac_records.audit import _sidecar_coverage

REPO_ROOT = Path(__file__).resolve().parent.parent
LEGACY = REPO_ROOT / "tests" / "fixtures" / "legacy"
LEGACY_RID = "01JQZ0SYNTHXANESDEMO000000"


def _write_sidecar(tmp_path: Path, evidence: dict) -> Path:
    path = tmp_path / f"{LEGACY_RID}.evidence.json"
    path.write_text(json.dumps({"evidence": evidence}), encoding="utf-8")
    return path


def _ev(kind: str = "spreadsheet") -> list[dict]:
    return [{"source_type": kind, "quote": "x"}]


# --- 1. blocks counted in the denominator ------------------------------------


def test_honest_denominator_counts_blocks(tmp_path):
    record = {
        "isaac_record_version": "1.05",
        "record_id": LEGACY_RID,
        "record_type": "evidence",
        "system": {"technique": "HERFD-XAS"},  # scalar leaf
        "sample": {"sample_form": "pellet"},  # scalar leaf
        "measurement": {
            "series": [{"series_id": "s1"}],
            "qc": {"status": "valid"},
        },
        "links": [{"rel": "derived_from", "target": "01JOTHER", "basis": "same_sample"}],
        "assets": [{"asset_id": "a1", "uri": "x://a", "sha256": "0" * 64}],
        "descriptors": {"outputs": [{"descriptors": [{"name": "d1", "value": 1.0}]}]},
        "attribution": {
            "contributors": [
                {"name": "Ada", "role": "curated_record"},
                {"name": "Grace", "role": "curated_record"},
            ]
        },
    }
    sidecar = _write_sidecar(
        tmp_path,
        {"system.technique": _ev(), "sample.sample_form": _ev()},
    )
    covered, expected, uncovered, dangling = _sidecar_coverage(record, sidecar)

    assert expected == 9  # 2 scalar + 7 block targets
    assert covered == 2  # only the two scalars are evidenced
    assert set(uncovered) == {
        "series:s1",
        "qc:status",
        "links:derived_from|01JOTHER|same_sample",
        "assets:a1",
        "descriptors:d1",
        "attribution:Ada|curated_record",
        "attribution:Grace|curated_record",
    }
    assert dangling == []
    # deterministic, sorted output
    assert uncovered == sorted(uncovered)


# --- 2. an unevidenced spectrum makes full coverage impossible ---------------


def test_no_full_coverage_while_series_uncovered(tmp_path):
    record = {
        "system": {"technique": "HERFD-XAS"},
        "measurement": {"series": [{"series_id": "avg"}], "qc": {"status": "valid"}},
    }
    # Every scalar + qc evidenced, but the spectrum itself is not.
    sidecar = _write_sidecar(
        tmp_path, {"system.technique": _ev(), "qc:status": _ev("user_confirmation")}
    )
    covered, expected, uncovered, dangling = _sidecar_coverage(record, sidecar)

    assert expected == 3  # system.technique + series:avg + qc:status
    assert covered < expected  # the old "N/N with fabricated spectrum" is impossible
    assert "series:avg" in uncovered


# --- 3. dangling detection preserved; implicit is informational --------------


def test_dangling_still_detected(tmp_path):
    record = {
        "system": {"technique": "HERFD-XAS"},
        "measurement": {"series": [{"series_id": "avg"}], "qc": {"status": "valid"}},
    }
    sidecar = _write_sidecar(
        tmp_path,
        {
            "system.technique": _ev(),  # covered
            "system.nonexistent.path": _ev(),  # dotted, does NOT resolve -> dangling
            "series:avg": _ev(),  # covered (expected)
            "series:ghost": _ev(),  # namespaced, no such series -> dangling
            "qc:status": _ev(),  # covered
            "implicit:absorbing_element": {"value": "Cu", "evidence": _ev("derivation")},
        },
    )
    covered, expected, uncovered, dangling = _sidecar_coverage(record, sidecar)

    assert expected == 3  # system.technique + series:avg + qc:status
    assert covered == 3  # all three expected targets present
    assert uncovered == []
    assert "system.nonexistent.path" in dangling
    assert "series:ghost" in dangling
    # implicit keys are informational: never expected, covered, uncovered, or dangling
    assert "implicit:absorbing_element" not in dangling
    assert "implicit:absorbing_element" not in uncovered


# --- 4. legacy (pre-Phase-21) sidecar audits honestly, no crash --------------


def test_legacy_sidecar_backward_compat():
    record = json.loads((LEGACY / f"{LEGACY_RID}.json").read_text(encoding="utf-8"))
    sidecar_path = LEGACY / f"{LEGACY_RID}.evidence.json"

    covered, expected, uncovered, dangling = _sidecar_coverage(record, sidecar_path)

    # Derived from the frozen fixture: 25 scalar + 8 block = 33 expected; the legacy
    # sidecar covers all 25 scalars + 3 assets + 1 descriptor = 29 (block keys for
    # series/qc/attribution did not exist before Phase 21).
    assert expected == 33
    assert covered == 29
    assert dangling == []  # every legacy dotted/asset/descriptor key resolves
    assert {
        "series:averaged_spectrum",
        "qc:status",
        "attribution:Ada Lovelace|curated_record",
        "attribution:Grace Hopper|curated_record",
    } <= set(uncovered)


# --- 5. missing sidecar file reports 0-of-expected, not 0-of-0 ---------------


def test_no_sidecar_reports_zero_of_expected(tmp_path):
    record = {
        "system": {"technique": "HERFD-XAS"},
        "measurement": {"series": [{"series_id": "avg"}], "qc": {"status": "valid"}},
    }
    missing = tmp_path / "does_not_exist.evidence.json"
    covered, expected, uncovered, dangling = _sidecar_coverage(record, missing)

    assert covered == 0
    assert expected > 0
    assert uncovered == sorted(["system.technique", "series:avg", "qc:status"])
    assert dangling == []


# --- 6. excluded scalars never become expected targets -----------------------


def test_excluded_scalars_are_not_expected(tmp_path):
    record = {
        "isaac_record_version": "1.05",  # identity, excluded
        "record_id": LEGACY_RID,  # identity, excluded
        "record_type": "evidence",  # identity, excluded
        "record_domain": "characterization",  # identity, excluded
        "source_type": "facility",  # identity, excluded
        "tags": ["cu", "xanes"],  # user labels, excluded subtree
        "timestamps": {
            "created_utc": "2099-03-05T20:15:00Z",  # system stamp, excluded
            "acquired_start_utc": "2099-03-01T18:30:00Z",  # a real scalar target
        },
        "sample": {"sample_form": "pellet"},  # a real scalar target
        "measurement": {"qc": {"status": "valid"}},  # qc subtree excluded (qc:status block)
        "attribution": {"contributors": [{"name": "Ada", "role": "curated_record"}]},
    }
    sidecar = _write_sidecar(tmp_path, {})
    covered, expected, uncovered, dangling = _sidecar_coverage(record, sidecar)

    # 2 scalar targets (acquired_start_utc, sample_form) + 2 block (qc:status, contributor)
    assert expected == 4
    assert covered == 0
    # excluded leaves never appear as targets
    for excluded in (
        "isaac_record_version",
        "record_id",
        "record_type",
        "record_domain",
        "source_type",
        "tags",
        "timestamps.created_utc",
        "measurement.qc.status",
    ):
        assert excluded not in uncovered
    # non-excluded scalars DO appear
    assert "timestamps.acquired_start_utc" in uncovered
    assert "sample.sample_form" in uncovered
