"""The advisory review layer is a placeholder and must stay inert and isolated:
no validity verdict, no record mutation, and never wired into export/validation."""

import copy
import json
import sys
from pathlib import Path

from isaac_records.review import NoOpReviewer, ReviewCategory, ReviewFinding, ReviewReport

ROOT = Path(__file__).resolve().parents[1]
XANES = ROOT / "tests" / "fixtures" / "official" / "ex_situ_xanes_cuo2_record.json"


def test_noop_reviewer_returns_empty_advisory_report():
    record = json.loads(XANES.read_text())
    report = NoOpReviewer().review(record)
    assert isinstance(report, ReviewReport)
    assert report.findings == ()
    assert report.advisory is True


def test_review_report_has_no_validity_verdict():
    # This layer must never look like a validator.
    report = ReviewReport()
    for forbidden in ("ok", "valid", "passed", "is_valid", "errors"):
        assert not hasattr(report, forbidden), f"advisory report must not expose .{forbidden}"


def test_reviewer_does_not_mutate_the_record():
    record = json.loads(XANES.read_text())
    before = copy.deepcopy(record)
    NoOpReviewer().review(record, sidecar={"evidence": {}}, graph_context={"similar": []})
    assert record == before


def test_findings_are_advisory_shaped():
    f = ReviewFinding(
        category=ReviewCategory.POSSIBLE_OVERCLAIMING,
        message="descriptor asserts oxidation state beyond what the spectrum evidences",
        where="descriptors.outputs[0]",
        suggested_question="Is the oxidation-state assignment supported by the XANES edge alone?",
    )
    assert f.category is ReviewCategory.POSSIBLE_OVERCLAIMING
    assert "overclaim" in ReviewReport(findings=(f,)).render().lower()


def test_export_and_validation_do_not_import_review():
    # Importing/using the core truth path must not pull in the advisory layer,
    # guaranteeing the placeholder cannot affect export/validation behavior.
    for mod in list(sys.modules):
        if mod.startswith("isaac_records"):
            del sys.modules[mod]
    import isaac_records  # noqa: F401
    from isaac_records import export, official  # noqa: F401

    assert "isaac_records.review" not in sys.modules, (
        "the review layer must not be imported by the core truth path"
    )
