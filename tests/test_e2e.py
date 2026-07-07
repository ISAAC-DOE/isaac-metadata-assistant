"""Phase-4 synthetic end-to-end: build_draft -> apply_answers -> export -> validate.

Exercises the full path on committed SYNTHETIC fixtures only (never examples/): the
completed draft exports to an official ISAAC v1.05 record + sidecar that pass
validate_official and a clean audit, with every scientific value traced back to the
answers fixture (nothing fabricated) and no graphify import anywhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from isaac_records.audit import audit_records
from isaac_records.complete import apply_answers
from isaac_records.export import export_draft, get_path
from isaac_records.extract.draft_builder import build_draft
from isaac_records.official import validate_official

REPO_ROOT = Path(__file__).resolve().parent.parent
SYN = REPO_ROOT / "tests" / "fixtures" / "synthetic"
CSV_PATH = SYN / "mock_campaign.csv"
LISTING_PATH = SYN / "raw_scan_listing.txt"
ANSWERS_PATH = SYN / "xanes_completion_answers.json"
RID = "01JQZ0SYNTHXANESDEMO000000"
SAMPLE_RECORD = REPO_ROOT / "docs" / "samples" / f"{RID}.json"


def _answers():
    return json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))


def _export(now="2099-03-05T21:00:00Z"):
    draft = build_draft(CSV_PATH, LISTING_PATH)
    completed = apply_answers(draft, _answers())
    return completed, export_draft(completed, REPO_ROOT, record_id=RID, now=now)


def test_full_path_exports_valid_official_record():
    _completed, result = _export()
    assert result.ok, (
        result.draft_report.render(),
        result.official_report and result.official_report.render(),
    )
    assert result.record["record_id"] == RID
    assert validate_official(result.record, REPO_ROOT).ok


def test_sidecar_dotted_paths_resolve_in_record():
    _completed, result = _export()
    assert result.ok
    checked = 0
    for key in result.sidecar["evidence"]:
        if ":" in key:  # namespaced (assets:/descriptors:/implicit:) — not literal paths
            continue
        _, found = get_path(result.record, key)
        assert found, f"sidecar path does not resolve: {key}"
        checked += 1
    assert checked  # there is at least one dotted path to resolve


def test_audit_is_clean(tmp_path):
    _completed, result = _export()
    assert result.ok
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    (records_dir / f"{RID}.json").write_text(
        json.dumps(result.record, indent=2) + "\n", encoding="utf-8"
    )
    (records_dir / f"{RID}.evidence.json").write_text(
        json.dumps(result.sidecar, indent=2) + "\n", encoding="utf-8"
    )

    results = audit_records(records_dir, REPO_ROOT)
    assert results, "audit found no records"
    assert all(report.ok for _name, report, _cov in results)
    # the sidecar's dotted paths all resolve (0 dangling).
    for _name, _report, (resolved, total, dangling) in results:
        assert dangling == []
        assert resolved == total and total > 0


def test_no_fabrication_values_trace_to_fixture():
    completed, result = _export()
    assert result.ok
    answers = _answers()

    # asset sha256s are exactly the fixture's (no invented hash).
    record_sha = {a["uri"]: a["sha256"] for a in result.record["assets"]}
    assert record_sha == answers["asset_sha256"]

    # descriptor value is the fixture's.
    desc = result.record["descriptors"]["outputs"][0]["descriptors"][0]
    assert desc["value"] == answers["descriptor"]["value"]

    # series is the fixture's, verbatim.
    assert result.record["measurement"]["series"] == answers["series"]
    assert completed["series"] == answers["series"]


def test_committed_sample_record_validates():
    record = json.loads(SAMPLE_RECORD.read_text(encoding="utf-8"))
    assert record["record_id"] == RID
    assert validate_official(record, REPO_ROOT).ok


def test_no_graphify_imported_after_full_path():
    _export()  # run the full path
    assert not any(
        n == "graphify" or n.startswith("graphify.") for n in sys.modules
    ), "the Phase-4 path must not import graphify"
