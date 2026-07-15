"""P21C enforcement: block-evidence coverage, sha256 format, unsupported-block
and duplicate-natural-key refusal.

These close the no-guessing gate: a spectrum/qc/link/contributor must cite
evidence (or be user-confirmed), a malformed sha256 is rejected, and scientific
blocks the exporter has no path for are refused rather than silently dropped.
Perturbations start from the synthetic golden draft (fully covered after P21C).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from isaac_records import validate_draft
from isaac_records.export import export_draft

ROOT = Path(__file__).resolve().parents[1]
DRAFT_PATH = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"
RID = "01JFH3Q8Z1Q9F0XG3V7N4K2M8C"


@pytest.fixture
def draft():
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


def _joined(report) -> str:
    return "\n".join(f"{w} — {m}" for w, m in report.errors)


def test_golden_draft_is_fully_covered(draft):
    # Guard: the fixture the other tests perturb must itself validate clean.
    assert validate_draft(draft).ok, validate_draft(draft).render()


def test_fabricated_spectrum_refused(draft):
    # Headline regression: series present but ZERO block_evidence => no export.
    # (Before P21C this exported successfully.)
    draft.pop("block_evidence", None)
    assert not validate_draft(draft).ok
    assert export_draft(draft, ROOT, record_id=RID).ok is False


def test_series_requires_evidence(draft):
    del draft["block_evidence"]["series:averaged_spectrum"]
    report = validate_draft(draft)
    assert not report.ok
    assert "averaged_spectrum" in _joined(report)


def test_qc_requires_evidence_when_series_present(draft):
    # (a) series covered, qc provenance removed.
    d1 = copy.deepcopy(draft)
    del d1["block_evidence"]["qc:status"]
    r1 = validate_draft(d1)
    assert not r1.ok
    assert "qc" in _joined(r1)

    # (b) qc block missing entirely.
    d2 = copy.deepcopy(draft)
    del d2["qc"]
    r2 = validate_draft(d2)
    assert not r2.ok
    assert "qc" in _joined(r2)


def test_link_requires_evidence(draft):
    draft["links"] = [
        {
            "rel": "derived_from",
            "target": "01JQZ0SYNTHXANESDEMO000000",
            "basis": "same_absorber_edge",
        }
    ]  # no matching block_evidence key
    report = validate_draft(draft)
    assert not report.ok
    assert "link" in _joined(report).lower()


def test_attribution_requires_evidence(draft):
    del draft["block_evidence"]["attribution:Krish Verma|curated_record"]
    report = validate_draft(draft)
    assert not report.ok
    assert "contributor" in _joined(report).lower()


def test_duplicate_natural_keys_refused(draft):
    # Duplicate series_id -> key collision, refused.
    d1 = copy.deepcopy(draft)
    d1["series"].append(copy.deepcopy(d1["series"][0]))
    r1 = validate_draft(d1)
    assert not r1.ok
    assert "duplicate series_id" in _joined(r1)

    # Duplicate link tuple -> refused even when covered (keys can't disambiguate).
    d2 = copy.deepcopy(draft)
    link = {
        "rel": "derived_from",
        "target": "01JQZ0SYNTHXANESDEMO000000",
        "basis": "same_absorber_edge",
    }
    d2["links"] = [copy.deepcopy(link), copy.deepcopy(link)]
    d2["block_evidence"][
        "links:derived_from|01JQZ0SYNTHXANESDEMO000000|same_absorber_edge"
    ] = [
        {
            "source_type": "user_confirmation",
            "question": "How is this linked?",
            "answer": "derived_from",
            "timestamp": "2099-03-05T21:00:00Z",
        }
    ]
    r2 = validate_draft(d2)
    assert not r2.ok
    assert "duplicate link" in _joined(r2)

    # Duplicate contributor name|role -> refused.
    d3 = copy.deepcopy(draft)
    d3["attribution"]["contributors"].append(
        {"name": "Krish Verma", "role": "curated_record"}
    )
    r3 = validate_draft(d3)
    assert not r3.ok
    assert "duplicate contributor" in _joined(r3)


def test_unsupported_block_refused(draft):
    d1 = copy.deepcopy(draft)
    d1["computation"] = {"method": "DFT"}
    r1 = validate_draft(d1)
    assert not r1.ok
    assert "unsupported scientific block 'computation'" in _joined(r1)

    d2 = copy.deepcopy(draft)
    d2["processing"] = {"steps": ["normalize"]}
    r2 = validate_draft(d2)
    assert not r2.ok
    assert "unsupported scientific block 'processing'" in _joined(r2)


def test_sha256_asdf_rejected_at_draft(draft):
    draft["assets"][0]["sha256"] = "asdf"  # stub evidence already present
    report = validate_draft(draft)
    assert not report.ok
    assert "sha256 'asdf'" in _joined(report)
