"""Portal-style advisory warnings are a LOCAL soft-warning seam: structured, read-only,
non-gating, isolated from the truth path, and Graphify-free. They must never change what
counts as officially valid or whether a record exports."""

import copy
import json
import sys
from pathlib import Path

from isaac_records.cli import main
from isaac_records.official import validate_official
from isaac_records.portal_warnings import (
    PortalWarning,
    PortalWarningReport,
    portal_warnings,
)

ROOT = Path(__file__).resolve().parents[1]
XANES = ROOT / "tests" / "fixtures" / "official" / "ex_situ_xanes_cuo2_record.json"
SAMPLE = ROOT / "docs" / "samples" / "01JQZ0SYNTHXANESDEMO000000.json"


def test_portal_warnings_returns_a_report():
    record = json.loads(XANES.read_text())
    report = portal_warnings(record)
    assert isinstance(report, PortalWarningReport)
    assert report.advisory is True
    assert all(isinstance(w, PortalWarning) for w in report.warnings)


def test_report_has_no_validity_verdict():
    # This layer must never look like a validator or a gate.
    report = PortalWarningReport()
    for forbidden in ("ok", "valid", "passed", "is_valid", "errors"):
        assert not hasattr(report, forbidden), f"advisory report must not expose .{forbidden}"


def test_portal_warnings_does_not_mutate_the_record():
    record = json.loads(XANES.read_text())
    before = copy.deepcopy(record)
    portal_warnings(record)
    assert record == before


def test_empty_report_renders_as_none():
    assert "none" in PortalWarningReport().render().lower()


def test_no_links_warning_fires_when_links_absent():
    record = {"record_id": "X", "measurement": {"qc": {"status": "valid"}}}
    codes = {w.code for w in portal_warnings(record).warnings}
    assert "NO_LINKS" in codes


def test_no_links_warning_absent_when_links_present():
    record = {
        "links": [{"rel": "derived_from", "target": "0" * 26, "basis": "same_absorber_edge"}],
        "measurement": {"qc": {"status": "valid"}},
    }
    codes = {w.code for w in portal_warnings(record).warnings}
    assert "NO_LINKS" not in codes


def test_qc_nonvalid_without_evidence_fires():
    record = {"links": [1], "measurement": {"qc": {"status": "compromised"}}}
    codes = {w.code for w in portal_warnings(record).warnings}
    assert "QC_NONVALID_WITHOUT_EVIDENCE" in codes


def test_qc_warning_absent_when_valid_or_evidence_present():
    valid = {"links": [1], "measurement": {"qc": {"status": "valid"}}}
    with_ev = {
        "links": [1],
        "measurement": {"qc": {"status": "failed", "evidence": "detector saturated mid-scan"}},
    }
    assert "QC_NONVALID_WITHOUT_EVIDENCE" not in {w.code for w in portal_warnings(valid).warnings}
    assert "QC_NONVALID_WITHOUT_EVIDENCE" not in {w.code for w in portal_warnings(with_ev).warnings}


def test_sample_record_is_officially_valid_yet_warns_non_gating():
    # The committed synthetic sample is officially valid AND audit-clean, yet the advisory
    # layer surfaces NO_LINKS. Presence of the advisory warning must NOT change validity.
    record = json.loads(SAMPLE.read_text())
    assert validate_official(record, ROOT).ok  # hard gate passes
    codes = {w.code for w in portal_warnings(record).warnings}
    assert "NO_LINKS" in codes  # advisory warning present
    assert validate_official(record, ROOT).ok  # still valid — warning did not gate it


def test_truth_path_does_not_import_portal_warnings():
    # Importing/using the core truth path must not pull in the advisory layer, guaranteeing
    # it cannot affect export/validation/audit behavior.
    for mod in list(sys.modules):
        if mod.startswith("isaac_records"):
            del sys.modules[mod]
    import isaac_records  # noqa: F401
    from isaac_records import audit, export, official  # noqa: F401

    assert "isaac_records.portal_warnings" not in sys.modules, (
        "the advisory portal-warning layer must not be imported by the core truth path"
    )


def test_cli_validate_warnings_is_non_gating(capsys):
    # `validate --official --warnings` on a valid record exits 0 (non-gating) and still
    # prints the hard PASS result plus the advisory warning.
    code = main(["--root", str(ROOT), "validate", str(SAMPLE), "--official", "--warnings"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "PASS" in out  # hard official result
    assert "NO_LINKS" in out  # advisory warning shown
    assert "non-gating" in out.lower()
