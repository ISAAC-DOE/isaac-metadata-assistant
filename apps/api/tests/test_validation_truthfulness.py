"""R2 · a record with no measured data must not reach a reader as a bare PASS.

Three defects, one theme: the app could present a record holding zero measurement
data as complete and clean, and in one case it deleted an operator's recorded
judgment on the way.

  D1  `export.transform` guarded the measurement block with `if draft.get("series"):`
      — truthiness. A draft with `series: []` fell through the whole block, so the
      exported record carried NO `measurement` at all and an evidenced
      `qc: {status: "compromised", evidence: ...}` was silently DELETED. The record
      then passed official validation.

      NOTE on the status value, recorded because the first version of this file got it
      wrong and the mistake is easy to repeat: the schema enum is
      `valid | compromised | failed | pending`. "nonvalid" is NOT a member — it is only
      the name of the advisory CHECK (`_qc_nonvalid_without_evidence`), which fires on
      any `status != "valid"`. Using "nonvalid" as DATA produces an enum error that
      masks the behaviour under test.

  D2  That deletion also suppressed the warning that would have caught it: with the
      qc block gone, `_qc_nonvalid_without_evidence` had nothing to inspect.

  D3  `POST /api/validate/record` called `validate_official` and nothing else, so the
      standalone validator — the surface an operator points at a candidate file — was
      the one place the advisory tier never ran.

WHAT IS DELIBERATELY *NOT* ASSERTED HERE, because getting this wrong would be worse
than the defect: an empty series is NOT made invalid. `measurement.series` has no
`minItems` in the vendored schema, so `series: []` validates with zero errors. That is
the schema's decision, not this module's. Whether an empty series means invalid,
incomplete, not-applicable or deliberately-empty is a scientific question for a domain
owner. So the fix DISCLOSES it (advisory) and never gates on it — and the tests below
pin that non-gating property explicitly, so a later slice cannot quietly promote it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api.app import create_app

from isaac_records.export import transform
from isaac_records.official import validate_official
from isaac_records.portal_warnings import portal_warnings

REPO_ROOT = Path(__file__).resolve().parents[3]

#: A draft whose series is EMPTY but whose qc verdict is evidenced. This is the exact
#: shape that used to lose the verdict.
EVIDENCED_NONVALID_EMPTY_SERIES = {
    "series": [],
    "qc": {"status": "compromised", "evidence": "Beam damage observed in scans 4-6."},
}

RECORD_ID = "01JFH3Q8Z1Q9F0XG3V7N4K2M8C"
NOW = "2026-01-01T00:00:00Z"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _transform(draft: dict) -> dict:
    return transform(draft, record_id=RECORD_ID, now=NOW)


# --- D1 the evidenced verdict survives ---------------------------------------


def test_d1_an_empty_series_no_longer_deletes_the_measurement_block():
    record = _transform(EVIDENCED_NONVALID_EMPTY_SERIES)
    assert "measurement" in record, (
        "the whole measurement block vanished for `series: []`. This is the falsy-guard "
        "defect: the block was guarded on truthiness, so an empty list skipped it."
    )
    assert record["measurement"]["series"] == []


def test_d1_the_evidenced_qc_verdict_survives_verbatim():
    record = _transform(EVIDENCED_NONVALID_EMPTY_SERIES)
    assert record["measurement"]["qc"] == EVIDENCED_NONVALID_EMPTY_SERIES["qc"], (
        "an operator's recorded judgment that the data was COMPROMISED, with evidence, was "
        "dropped from the exported record. Silently discarding evidence is the defect; "
        "emitting an empty series is legal (the schema sets no minItems)."
    )


def test_d1_the_preserved_record_still_validates_officially():
    """The fix must not trade a deletion for a validation failure.

    Built on a COMPLETE record rather than on the bare two-key draft above: a draft
    holding only `series` + `qc` can never satisfy the schema (no `record_type`, no
    `record_id`, ...), so validating it would fail for reasons that have nothing to do
    with the empty series and would prove nothing either way.
    """
    record = json.loads(
        (REPO_ROOT / "qa/validator-upload-package/complete-valid-record.json").read_text()
    )
    record["measurement"]["series"] = []
    record["measurement"]["qc"] = dict(EVIDENCED_NONVALID_EMPTY_SERIES["qc"])
    report = validate_official(record, REPO_ROOT)
    assert report.ok, [(e.path, e.message) for e in report.errors]


def test_d1_an_absent_series_is_unchanged():
    """Only the EMPTY-list case changes. `series` absent still means no measurement
    block — there is nothing to describe and nothing to preserve, and widening the fix
    to invent one would be guessing."""
    record = _transform({"qc": {"status": "valid"}})
    assert "measurement" not in record


# --- D2 the empty series is disclosed ----------------------------------------


def test_d2_an_empty_series_raises_an_advisory_warning():
    record = _transform(EVIDENCED_NONVALID_EMPTY_SERIES)
    codes = [w.code for w in portal_warnings(record).warnings]
    assert "NO_MEASUREMENT_SERIES" in codes, codes


def test_d2_an_absent_measurement_block_also_raises_it():
    codes = [w.code for w in portal_warnings({}).warnings]
    assert "NO_MEASUREMENT_SERIES" in codes, codes


def test_d2_a_populated_series_does_not_raise_it():
    record = _transform(
        {
            "series": [{"series_id": "s", "independent_variables": [], "channels": []}],
            "qc": {"status": "valid"},
        }
    )
    codes = [w.code for w in portal_warnings(record).warnings]
    assert "NO_MEASUREMENT_SERIES" not in codes, codes


def test_d2_preserving_the_qc_block_re_enables_the_qc_warning():
    """The compounding half of the defect. The deletion did not merely lose data — it
    removed the input `_qc_nonvalid_without_evidence` inspects, so the falsy guard
    suppressed the very warning that would have flagged it. With the block preserved, an
    UNEVIDENCED non-valid verdict is caught again."""
    record = _transform({"series": [], "qc": {"status": "compromised"}})
    codes = [w.code for w in portal_warnings(record).warnings]
    assert "QC_NONVALID_WITHOUT_EVIDENCE" in codes, codes


# --- D3 the standalone validator runs the advisory tier ----------------------


def _validate_record(client: TestClient, payload: dict) -> dict:
    return client.post("/api/validate/record", content=json.dumps(payload)).json()


def test_d3_the_standalone_validator_returns_advisory_warnings(client):
    body = _validate_record(client, {"measurement": {"series": []}})
    codes = [w["code"] for w in body["warnings"]]
    assert "NO_MEASUREMENT_SERIES" in codes, body


def test_d3_the_advisory_channel_is_marked_non_gating(client):
    body = _validate_record(client, {"measurement": {"series": []}})
    assert body["advisory"] is True
    assert body["gating"] is False


def test_d3_a_warning_never_turns_a_pass_into_a_fail(client):
    """The property that keeps this module from becoming a second authority on validity
    alongside the vendored schema. A schema-valid record with warnings stays `ok: True`."""
    record = json.loads(
        (REPO_ROOT / "qa/validator-upload-package/empty-measurement-series.json").read_text()
    )
    body = _validate_record(client, record)
    assert body["ok"] is True, body["errors"]
    assert [w["code"] for w in body["warnings"]], "the file should raise at least one warning"


def test_d3_the_qa_empty_measurement_file_is_no_longer_a_bare_pass(client):
    """The operator-visible outcome this slice exists for. Before: PASS, zero errors, no
    signal of any kind that the record holds no measured data."""
    record = json.loads(
        (REPO_ROOT / "qa/validator-upload-package/empty-measurement-series.json").read_text()
    )
    body = _validate_record(client, record)
    assert "NO_MEASUREMENT_SERIES" in [w["code"] for w in body["warnings"]]


def test_d3_warnings_use_the_same_serializer_as_the_per_record_route(client):
    """Parity by construction: both routes go through `serialize.warnings_to_dict`, so
    the two cannot drift into different shapes for the same advisory."""
    body = _validate_record(client, {"measurement": {"series": []}})
    assert set(body["warnings"][0]) == {"code", "where", "message"}


def test_d3_an_invalid_record_reports_errors_and_warnings_independently(client):
    body = _validate_record(client, {"measurement": {"series": []}})
    assert body["ok"] is False, "a bare measurement stub cannot satisfy the schema"
    assert body["errors"], "schema errors must still be reported"
    assert body["warnings"], "and the advisory tier still runs alongside them"
