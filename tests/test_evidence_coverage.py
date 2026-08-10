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


# --- sha256 EXACTNESS -------------------------------------------------------
#
# `_SHA256_RE` was `^[0-9a-f]{64}$` and applied with `.match()`. Python's `$` also
# matches immediately before a trailing newline, so the 65-character string
# `"9"*64 + "\n"` validated clean as a sha256 — and nothing downstream caught it:
# the official schema declares `assets.items.properties.sha256` as bare
# `{"type": "string"}` with no pattern and no length bound, so the malformed digest
# exported into an official record and passed `validate_official`. The pattern is
# now `\A[0-9a-f]{64}\Z`.
#
# Each case below names EXACTLY the character it appends. A newline and a space are
# separate categories: only the newline was ever accepted, so a case labelled
# "trailing whitespace" that used a space would give false confidence for the
# newline it named.

_GOOD_SHA256 = "9" * 64


def test_sha256_exactly_64_lowercase_hex_is_accepted(draft):
    # Baseline: the fix must not narrow what a legitimate digest looks like.
    draft["assets"][0]["sha256"] = _GOOD_SHA256
    assert validate_draft(draft).ok, validate_draft(draft).render()


def test_sha256_with_trailing_newline_is_refused(draft):
    # THE headline regression. 65 characters, the 65th being LF (0x0a).
    bad = _GOOD_SHA256 + "\n"
    assert len(bad) == 65 and bad[-1] == "\n"
    draft["assets"][0]["sha256"] = bad
    report = validate_draft(draft)
    assert not report.ok
    assert "is not a 64-char lowercase hex digest" in _joined(report)


def test_sha256_with_trailing_space_is_refused(draft):
    # A DIFFERENT character from the case above: SPACE (0x20), not LF. `$` never
    # accepted this one; the case exists so the two are not conflated.
    bad = _GOOD_SHA256 + " "
    assert len(bad) == 65 and bad[-1] == " "
    draft["assets"][0]["sha256"] = bad
    assert not validate_draft(draft).ok


def test_sha256_with_trailing_carriage_return_is_refused(draft):
    # CRLF-terminated file reads produce this; `\Z` refuses it, and `$` did too
    # only because `\r` is not the newline `$` is lenient about.
    bad = _GOOD_SHA256 + "\r\n"
    draft["assets"][0]["sha256"] = bad
    assert not validate_draft(draft).ok


def test_sha256_of_wrong_length_is_refused(draft):
    for bad, why in ((_GOOD_SHA256[:-1], "63 hex chars"), (_GOOD_SHA256 + "9", "65 hex chars")):
        d = copy.deepcopy(draft)
        d["assets"][0]["sha256"] = bad
        assert not validate_draft(d).ok, why


def test_sha256_uppercase_hex_is_refused(draft):
    # Pins PRE-EXISTING intent, not new behaviour: the character class has always
    # been `[0-9a-f]`, and both the constant's comment and the error message say
    # "lowercase". The exactness fix did not change the accepted alphabet.
    draft["assets"][0]["sha256"] = "9" * 63 + "A"
    report = validate_draft(draft)
    assert not report.ok
    assert "is not a 64-char lowercase hex digest" in _joined(report)


def test_sha256_with_leading_whitespace_or_newline_is_refused(draft):
    # `\A` is what refuses these. `^` alone also did (no `re.MULTILINE`), so this
    # pins the start anchor against a future `re.M` being added to the pattern.
    for lead in ("\n", " ", "\t"):
        d = copy.deepcopy(draft)
        d["assets"][0]["sha256"] = lead + _GOOD_SHA256
        assert not validate_draft(d).ok, f"leading {lead!r} must be refused"


def test_malformed_sha256_cannot_reach_an_exported_official_record(draft):
    # The consequence, pinned end-to-end. The official schema cannot catch this
    # (bare `{"type": "string"}`), so the draft gate is the ONLY gate. Measured
    # before the fix: export ok=True, official validate ok=True, 65-char digest.
    draft["assets"][0]["sha256"] = _GOOD_SHA256 + "\n"
    assert export_draft(draft, ROOT, record_id=RID).ok is False
