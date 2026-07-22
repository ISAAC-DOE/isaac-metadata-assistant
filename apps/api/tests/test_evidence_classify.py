"""P28.4 — deterministic evidence-support classification (backend-origin).

TEST-FIRST contract (authored BEFORE implementation; RED until
`isaac_api.evidence_classify.classify_fields` exists). This is a display/
classification VIEW over the EXISTING truth outputs (draft field envelopes +
evidence). It is a THIRD axis — evidence support — that COMPOSES from the two
existing axes (field-status verified/inferred/needs_confirmation/missing/rejected
+ source_type observed-set/derivation). It MUST NOT change truth-core gating and
MUST stay distinct from schema validity / workflow completion / export readiness /
advisory warnings.

Five classes (deterministic, per field/claim):
  supported            value present, backed by observed evidence OR user_confirmation
                       OR a documented derivation rule (all defensible; all export today)
  inferred_candidate   a PROPOSED value (often null) from a derivation rule, not yet
                       confirmed — NOT authoritative, must not enter the record as fact
  insufficient_evidence a needs_confirmation field with SOME evidence but the value is
                       not established
  conflicting_evidence  >=2 evidence entries assert incompatible non-null values; no
                       automatic winner
  unknown              needs_confirmation/missing with no defensible evidence; plainly absent

Precedence (highest first): conflicting_evidence > supported > inferred_candidate
> insufficient_evidence > unknown.

value_state ∈ {confirmed, candidate, none}. Each result:
  {field, classification, value_state, explanation, sources}.

Pure and non-mutating. Truth core untouched. All fixtures synthetic.
"""

from __future__ import annotations

import copy

import pytest

ALLOWED = {
    "supported",
    "inferred_candidate",
    "insufficient_evidence",
    "conflicting_evidence",
    "unknown",
}
RESULT_KEYS = {"field", "classification", "value_state", "explanation", "sources"}


def _draft(fields: dict) -> dict:
    return {"meta": {"record_type": "x", "record_domain": "y", "source_type": "facility"}, "fields": fields}


def _by_field(results: list[dict]) -> dict:
    return {r["field"]: r for r in results}


def test_classify_importable_and_shaped():
    from isaac_api.evidence_classify import classify_fields

    results = classify_fields(_draft({"a": {"value": "x", "status": "verified", "evidence": [{"source_type": "document"}]}}))
    assert isinstance(results, list) and results
    for r in results:
        assert set(r) == RESULT_KEYS, r
        assert r["classification"] in ALLOWED
        assert r["value_state"] in {"confirmed", "candidate", "none"}
        assert isinstance(r["explanation"], str) and r["explanation"]
        assert isinstance(r["sources"], list)


def test_verified_observed_is_supported():
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields(_draft({
        "sample.material": {"value": "TiO2", "status": "verified", "evidence": [{"source_type": "spreadsheet"}]},
    })))
    assert r["sample.material"]["classification"] == "supported"
    assert r["sample.material"]["value_state"] == "confirmed"


def test_user_confirmation_is_supported():
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields(_draft({
        "sample.form": {"value": "powder", "status": "verified",
                          "evidence": [{"source_type": "user_confirmation", "answer": "powder"}]},
    })))
    assert r["sample.form"]["classification"] == "supported"


def test_rule_backed_inferred_with_value_is_supported_not_candidate():
    """A documented derivation rule with a PRESENT value exports today (truth-core
    'inferred') — it is supported-by-rule, NOT an unconfirmed candidate."""
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields(_draft({
        "beam.energy_ev": {"value": 8333, "status": "inferred",
                            "evidence": [{"source_type": "derivation", "rule": "keV->eV x1000"}]},
    })))
    assert r["beam.energy_ev"]["classification"] == "supported"


def test_null_derivation_candidate_is_inferred_candidate():
    """The implicit['edge']-style pattern: a proposed value (null) from a rule,
    awaiting confirmation — classified as an inferred candidate, never supported."""
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields(_draft({
        "xas.edge": {"value": None, "status": "needs_confirmation",
                      "evidence": [{"source_type": "derivation", "rule": "guessed from incident-energy window"}]},
    })))
    assert r["xas.edge"]["classification"] == "inferred_candidate"
    assert r["xas.edge"]["value_state"] == "candidate"


def test_needs_confirmation_with_some_evidence_is_insufficient():
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields(_draft({
        "sample.purity": {"value": None, "status": "needs_confirmation",
                           "evidence": [{"source_type": "file_listing"}]},
    })))
    assert r["sample.purity"]["classification"] == "insufficient_evidence"


def test_no_evidence_is_unknown():
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields(_draft({
        "sample.origin": {"value": None, "status": "needs_confirmation", "evidence": []},
        "sample.note": {"value": None, "status": "missing", "evidence": []},
    })))
    assert r["sample.origin"]["classification"] == "unknown"
    assert r["sample.note"]["classification"] == "unknown"
    assert r["sample.origin"]["value_state"] == "none"


def test_conflicting_values_is_conflicting_evidence():
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields(_draft({
        "sample.mass_mg": {"value": "12", "status": "needs_confirmation", "evidence": [
            {"source_type": "user_confirmation", "answer": "12"},
            {"source_type": "user_confirmation", "answer": "15"},
        ]},
    })))
    assert r["sample.mass_mg"]["classification"] == "conflicting_evidence"


def test_classification_is_deterministic_and_pure():
    from isaac_api.evidence_classify import classify_fields

    d = _draft({"a": {"value": "x", "status": "verified", "evidence": [{"source_type": "document"}]}})
    frozen = copy.deepcopy(d)
    r1 = classify_fields(d)
    r2 = classify_fields(d)
    assert r1 == r2, "same input must yield identical classification (deterministic)"
    assert d == frozen, "classify_fields must not mutate its input"


def test_classification_is_not_schema_validity_or_completion():
    """Evidence support is a distinct axis — the result must not carry validity /
    workflow-completion / export-readiness verdicts (those stay separate)."""
    from isaac_api.evidence_classify import classify_fields

    r = classify_fields(_draft({"a": {"value": "x", "status": "verified", "evidence": [{"source_type": "document"}]}}))[0]
    assert "valid" not in r and "ok" not in r and "exportable" not in r and "complete" not in r


def test_sources_never_leak_secrets_or_private_paths():
    """Security regression (independent-review must-fix): `sources` must expose only
    a source_type + a SAFE locator — never a raw answer/quote, a sha256/token, or an
    absolute/private path. Poison every unsafe channel and assert none surfaces."""
    from isaac_api.evidence_classify import classify_fields

    secret = "SECRET-TOKEN-DO-NOT-LEAK"
    sha = "a" * 64
    priv = "/Users/krish/private/raw.h5"
    results = classify_fields(_draft({
        "sample.poison": {"value": "12", "status": "needs_confirmation", "evidence": [
            {"source_type": "user_confirmation", "answer": secret, "quote": secret},
            {"source_type": "document", "sha256": sha, "locator": sha, "source_file": priv},
        ]},
    }))
    blob = repr(results)
    assert secret not in blob, "a raw answer/quote must never appear in sources"
    assert sha not in blob, "a sha256/token-like value must never appear in sources"
    assert priv not in blob and "/Users/" not in blob, "an absolute/private path must never leak"
    # sources still carry the benign channel (source_type) so the view stays useful.
    for r in results:
        for s in r["sources"]:
            assert set(s) <= {"source_type", "locator"}, s


# --- structural: assets + implicit are classified, empty draft is safe --------


def test_implicit_null_derivation_is_inferred_candidate():
    """An implicit null-derivation claim (implicit['edge'] pattern) classifies as a
    candidate — a proposed value, never entered as supported fact."""
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields({
        "meta": {},
        "fields": {},
        "implicit": [
            {"about": "edge", "value": None,
             "evidence": [{"source_type": "derivation", "rule": "awaiting scientific confirmation"}]},
        ],
    }))
    assert r["implicit:edge"]["classification"] == "inferred_candidate"
    assert r["implicit:edge"]["value_state"] == "candidate"


def test_answered_asset_with_sha_and_user_confirmation_is_supported():
    from isaac_api.evidence_classify import classify_fields

    r = _by_field(classify_fields({
        "meta": {},
        "fields": {},
        "assets": [
            {"asset_id": "reduced_spectrum", "sha256": "b3b0" + "0" * 60,
             "evidence": [
                 {"source_type": "file_listing", "source_file": "raw_scan_listing.txt"},
                 {"source_type": "user_confirmation", "answer": "b3b0" + "0" * 60},
             ]},
        ],
    }))
    assert r["assets:reduced_spectrum"]["classification"] == "supported"
    assert r["assets:reduced_spectrum"]["value_state"] == "confirmed"


def test_empty_draft_yields_empty_list_no_crash():
    from isaac_api.evidence_classify import classify_fields

    assert classify_fields({}) == []
    assert classify_fields(_draft({})) == []


# --- seed-based behavioral checks (real truth-core drafts, isolated workspace) -


@pytest.fixture()
def seeded_ws(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    import isaac_api.workspace as ws
    from isaac_api.app import create_app

    create_app()  # seeds the five canonical scenarios into the isolated workspace
    return ws


def test_seed_ready_is_predominantly_supported_and_never_unknown(seeded_ws):
    """SEED_READY (fully answered) — every earned scientific value is supported:
    predominantly `supported`, zero `unknown`, and the two hardest earned claims
    (the confirmed implicit edge + each answered asset) are supported-by-evidence."""
    from isaac_api.evidence_classify import classify_fields

    draft = seeded_ws.load_experiment(seeded_ws.SEED_READY_ID).draft
    results = classify_fields(draft)
    by = {r["field"]: r for r in results}

    classes = [r["classification"] for r in results]
    assert classes.count("supported") > len(classes) / 2  # predominantly supported
    assert "unknown" not in classes

    # The edge — a derivation proposal in the raw draft — is now user-confirmed here.
    assert by["implicit:edge"]["classification"] == "supported"
    # Every answered asset (sha + user_confirmation) is supported.
    asset_results = [r for f, r in by.items() if f.startswith("assets:")]
    assert asset_results
    assert all(r["classification"] == "supported" for r in asset_results)


def test_seed_new_draft_has_unearned_candidate_not_supported(seeded_ws):
    """SEED_NEW_DRAFT (raw) — the assistant must NOT claim a `supported` value it
    has not earned. The edge is still only a derivation PROPOSAL (value None), so it
    classifies `inferred_candidate`, NOT `supported`; and no answered asset exists
    yet to be supported. This is the honest raw-vs-ready contrast."""
    from isaac_api.evidence_classify import classify_fields

    draft = seeded_ws.load_experiment(seeded_ws.SEED_NEW_DRAFT_ID).draft
    by = {r["field"]: r for r in classify_fields(draft)}

    assert by["implicit:edge"]["classification"] == "inferred_candidate"
    assert by["implicit:edge"]["value_state"] == "candidate"
    # No asset has been answered in the raw draft, so none is a supported fact.
    assert not [f for f, r in by.items()
                if f.startswith("assets:") and r["classification"] == "supported"]
