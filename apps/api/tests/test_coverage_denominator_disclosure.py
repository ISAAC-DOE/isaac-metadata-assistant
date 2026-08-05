"""A record holding NO measured data must not reach a reader as fully complete.

`test_validation_truthfulness.py` (R2) closed the *silent-pass* half of this: an
empty `measurement.series` no longer deletes an evidenced qc verdict, and the
advisory tier now runs on the standalone validator as well as the per-record route.
What it deliberately did not touch is the COVERAGE figure, and that is what this
file is about.

THE MEASUREMENT THIS FILE EXISTS BECAUSE OF. `isaac_records.audit` enumerates the
coverage denominator from the record's own content — `_block_targets` emits one
target per series the record has. So emptying a record's series REMOVES a target
from the denominator, and the figure stays at a full count. Measured on the
canonical worked example, exported through the real export path both ways:

    series present   →  PASS, 0 schema errors, evidence 33/33, uncovered [], dangling []
    series == []     →  PASS, 0 schema errors, evidence 32/32, uncovered [], dangling []

Both read as 100 %. A count cannot distinguish "everything is evidenced" from
"there is less to evidence", so a record with zero measured data could reach a
reader as complete — on the very surface CLAUDE.md §9 routes "which records are
incomplete?" to.

WHAT IS **NOT** DONE HERE, and must not be done later without a domain owner.
`measurement.series` has no `minItems` in the vendored schema, so `[]` validates
with zero errors — measured, not assumed. Whether an empty series is invalid,
incomplete, not applicable, or deliberately empty is a scientific decision, and
`qa/validator-upload-package/MANIFEST.json` records it as deliberately open. So:

  * the schema is not edited;
  * no verdict changes — `ok` stays computed from schema validation alone;
  * `covered` / `expected` are NOT altered: the numbers above are correct
    statements about a content-derived denominator, and faking a larger
    denominator would be inventing a target the record does not have;
  * the export gate is NOT closed — `export_ready` / `status` / `derive_workflow`
    are unchanged, because refusing to export a schema-valid record would BE the
    domain decision ("incomplete") that this repo reserves for a scientist.

What changed is disclosure, in the application, next to the number: the coverage
figure now states that its denominator is what the record contains, and — when the
advisory reports no measured series — that no series target is counted. The tests
below pin both the measured facts and the non-gating properties, so a later slice
cannot quietly promote the disclosure into a gate or drop it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import dependencies, workflow
from isaac_records.audit import _block_targets, _scalar_targets, audit_records, render_audit
from isaac_records.export import export_draft
from isaac_records.official import validate_official
from isaac_records.portal_warnings import portal_warnings

from conftest import ScopedWorkspace, tutorial_client

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_SRC = REPO_ROOT / "apps/web/src"

QA_EMPTY_SERIES = REPO_ROOT / "qa/validator-upload-package/empty-measurement-series.json"
QA_COMPLETE = REPO_ROOT / "qa/validator-upload-package/complete-valid-record.json"


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _if_match(client: TestClient, exp_id: str) -> dict:
    return {"If-Match": f'"{client.get(f"/api/experiments/{exp_id}").json()["version"]}"'}


def _empty_the_series(client: TestClient) -> str:
    """Empty the canonical Ready-to-Export seed's series IN PLACE, via the store.

    Deliberately NOT via `/answers`: no HTTP surface offers "unset the series", so
    the only way to reach the state under test is the store. The draft is otherwise
    untouched, so every other signal keeps the value it had with the series present
    and the comparison isolates one variable.
    """
    scoped = ScopedWorkspace(client.tutorial_session_id)
    exp = scoped.load_experiment(ws.SEED_READY_ID)
    assert exp is not None and exp.draft["series"], "the seed must start WITH a series"
    exp.draft["series"] = []
    exp.save()
    return ws.SEED_READY_ID


# --- the six surfaces agree, and none of them is a verdict change --------------


def test_the_standalone_validator_passes_the_empty_series_qa_fixture(client):
    """Surface 1. Unchanged and pinned: `ok` comes from the schema alone."""
    record = json.loads(QA_EMPTY_SERIES.read_text())
    body = client.post("/api/validate/record", content=json.dumps(record)).json()
    assert body["ok"] is True, body["errors"]
    assert body["errors"] == []
    assert body["gating"] is False
    assert "NO_MEASUREMENT_SERIES" in {w["code"] for w in body["warnings"]}


def test_record_validation_and_the_standalone_validator_give_the_same_verdict(client):
    """Surfaces 1 and 2 agree — same function, same schema, same answer."""
    exp_id = _empty_the_series(client)
    per_record = client.post(f"/api/experiments/{exp_id}/validate").json()
    assert per_record["ok"] is True
    assert per_record["errors"] == []

    scoped = ScopedWorkspace(client.tutorial_session_id)
    candidate = export_draft(scoped.load_experiment(exp_id).draft, REPO_ROOT).record
    standalone = client.post("/api/validate/record", content=json.dumps(candidate)).json()
    assert standalone["ok"] == per_record["ok"]
    assert standalone["errors"] == per_record["errors"]


def test_the_advisory_reaches_both_validation_channels_with_the_same_code(client):
    """Surface 2's advisory channel and surface 1's carry the SAME code set.

    Asserted as a set of codes rather than a count: a count cannot tell "the
    advisory tier ran and found one thing" from "the advisory tier did not run and
    something else did".
    """
    exp_id = _empty_the_series(client)
    per_record = client.get(f"/api/experiments/{exp_id}/warnings").json()
    scoped = ScopedWorkspace(client.tutorial_session_id)
    candidate = export_draft(scoped.load_experiment(exp_id).draft, REPO_ROOT).record
    standalone = client.post("/api/validate/record", content=json.dumps(candidate)).json()
    assert {w["code"] for w in per_record["warnings"]} == {
        w["code"] for w in standalone["warnings"]
    }
    assert "NO_MEASUREMENT_SERIES" in {w["code"] for w in per_record["warnings"]}
    # Neither channel carries a verdict — by design (mirrors PortalWarningReport).
    assert per_record["gating"] is False
    assert "ok" not in per_record


def test_readiness_and_the_export_gate_are_UNCHANGED_by_an_empty_series(client):
    """Surface 3, pinned as deliberately unchanged.

    This is the assertion a later slice is most likely to want to flip, so it says
    why it must not be flipped here: closing the gate would decide that an empty
    series means INCOMPLETE, which is one of four candidate scientific meanings and
    is a domain owner's call. The disclosure this slice adds is presentation; the
    gate is untouched.
    """
    exp_id = _empty_the_series(client)
    scoped = ScopedWorkspace(client.tutorial_session_id)
    exp = scoped.load_experiment(exp_id)
    assert exp.pending_count() == 0
    assert exp.draft_ok() is True
    assert exp.export_ready() is True
    assert exp.status() == ws.READY_TO_EXPORT
    assert dependencies.artifact_state(exp) == {"state": "none", "reason": None}
    derived = workflow.derive_workflow(
        pending_count=exp.pending_count(),
        draft_ok=exp.draft_ok(),
        ready=exp.export_ready(),
        exported=exp.exported(),
        rev=exp.rev,
    )
    assert derived["current_step"] == "export"
    assert {s["id"] for s in derived["ordered_steps"] if s["state"] == "completed"} == {
        "load_record",
        "complete_metadata",
        "review_evidence",
        "review_export_readiness",
    }


def test_export_writes_the_empty_series_and_keeps_the_qc_verdict(client):
    """Surface 4. The exported artifact carries `series: []` AND the qc block.

    The falsy-guard defect (R2/D1) dropped the whole measurement block for an empty
    series, taking an evidenced qc verdict with it. This asserts the artifact ON
    DISK, not just `transform`'s return value.
    """
    exp_id = _empty_the_series(client)
    resp = client.post(
        f"/api/experiments/{exp_id}/export", headers=_if_match(client, exp_id)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert resp.json()["official_report"]["ok"] is True

    scoped = ScopedWorkspace(client.tutorial_session_id)
    exp = scoped.load_experiment(exp_id)
    record = json.loads(exp.record_path().read_text())
    assert record["measurement"]["series"] == []
    assert record["measurement"]["qc"] == {"status": "valid"}
    # And the written artifact still validates — the disclosure changed no bytes.
    assert validate_official(record, REPO_ROOT).ok


def test_the_written_record_still_advises_and_still_passes(client):
    """Surfaces 2 and 4 agree AFTER export, on the written document (`dry_run: false`)."""
    exp_id = _empty_the_series(client)
    client.post(f"/api/experiments/{exp_id}/export", headers=_if_match(client, exp_id))
    validated = client.post(f"/api/experiments/{exp_id}/validate").json()
    warned = client.get(f"/api/experiments/{exp_id}/warnings").json()
    assert validated == {"ok": True, "errors": [], "schema": "ISAAC v1.05", "dry_run": False}
    assert warned["dry_run"] is False
    assert "NO_MEASUREMENT_SERIES" in {w["code"] for w in warned["warnings"]}


def test_the_audit_reports_a_full_count_over_a_record_with_no_measured_data(client):
    """Surface 5 — the measured fact this slice's disclosure exists for.

    Pinned rather than fixed. `covered == expected` here is a TRUE statement about a
    content-derived denominator, and inflating either number would invent a target
    the record does not have. What was missing is that nothing next to the number
    said so; see the frontend guards below.
    """
    exp_id = _empty_the_series(client)
    client.post(f"/api/experiments/{exp_id}/export", headers=_if_match(client, exp_id))
    body = client.post(f"/api/experiments/{exp_id}/audit").json()
    row = body["records"][0]
    assert row["ok"] is True
    assert row["schema_errors"] == []
    assert row["uncovered"] == []
    assert row["evidence_present"] == row["evidence_expected"]


# --- the denominator, measured directly ---------------------------------------


def test_emptying_the_series_removes_exactly_the_series_target(client):
    """The denominator shrink, asserted as a SET DIFFERENCE, not as two counts.

    Two counts would say "34 became 33" without saying WHICH target left, and a
    count cannot distinguish a shrink from a substitution.
    """
    with_series = json.loads(QA_COMPLETE.read_text())
    without = copy.deepcopy(with_series)
    without["measurement"]["series"] = []

    before = set(_block_targets(with_series))
    after = set(_block_targets(without))
    removed = before - after
    assert after < before, "emptying the series must not ADD targets"
    assert removed == {"series:merged_normalized_spectrum"}
    assert not any(t.startswith("series:") for t in after)
    # Scalar targets are untouched: only the block enumeration reads `series`.
    assert set(_scalar_targets(with_series)) == set(_scalar_targets(without))


def test_a_record_with_no_measurement_block_also_contributes_no_series_target():
    """The other shape `NO_MEASUREMENT_SERIES` fires on, so the disclosure sentence
    ("carries no measurement series") is true of both."""
    record = json.loads(QA_COMPLETE.read_text())
    del record["measurement"]
    assert not any(t.startswith("series:") for t in _block_targets(record))
    assert "NO_MEASUREMENT_SERIES" in {w.code for w in portal_warnings(record).warnings}


def test_the_audit_text_is_measured_both_ways_and_neither_way_fails(tmp_path, monkeypatch):
    """The comparison in this module's docstring, executed.

    Exports the SAME draft twice through the real export path — once with its series,
    once with it emptied — and audits each. Both PASS with a full count; only the
    denominator differs. If this ever stops holding, the docstring above is stale.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    session_id, _ = ws.create_tutorial_session()
    scoped = ScopedWorkspace(session_id)

    def audit_one(mutate) -> tuple[int, int, list, list, str]:
        exp = scoped.load_experiment(ws.SEED_READY_ID)
        draft = copy.deepcopy(exp.draft)
        mutate(draft)
        result = export_draft(draft, REPO_ROOT, record_id=exp.id)
        assert result.ok, result.official_report
        out = tmp_path / f"records-{len(list(tmp_path.iterdir()))}"
        out.mkdir()
        (out / f"{exp.id}.json").write_text(json.dumps(result.record))
        (out / f"{exp.id}.evidence.json").write_text(json.dumps(result.sidecar))
        rows = audit_records(out, REPO_ROOT)
        (_name, report, (covered, expected, uncovered, dangling)) = rows[0]
        assert report.ok
        return covered, expected, uncovered, dangling, render_audit(rows)

    def empty(draft):
        draft["series"] = []
        # Drop the now-orphaned block evidence too: leaving it makes the audit report
        # a `dangling` key, which is a DIFFERENT signal and would mask the point.
        (draft.get("block_evidence") or {}).pop("series:averaged_spectrum", None)

    kept = audit_one(lambda d: None)
    emptied = audit_one(empty)

    assert kept[0] == kept[1], "the unmodified seed audits at a full count"
    assert emptied[0] == emptied[1], "and so does the same record with NO measured data"
    assert emptied[1] == kept[1] - 1, "the denominator shrank by exactly the series target"
    assert kept[2] == emptied[2] == []
    assert kept[3] == emptied[3] == []
    # The rendered audit line says PASS both ways and mentions no series at all.
    assert "PASS" in emptied[4] and "series" not in emptied[4]


# --- the disclosure is wired to the code the backend actually emits -----------

#: The two frontend files that must key on the shared constant, not on their own
#: copy of the literal. Named as a SET so adding a third surface that shows the
#: coverage figure without the disclosure is a visible omission here.
_DISCLOSURE_CONSUMERS = (
    WEB_SRC / "components/CoverageBadge.tsx",
    WEB_SRC / "lib/assistantComposer.ts",
)
_DISCLOSURE_SOURCE = WEB_SRC / "lib/adapt.ts"


def _emitted_code() -> str:
    """The code the Python check emits for an empty series — read, never hard-coded."""
    record = {"measurement": {"series": []}}
    codes = [
        w.code
        for w in portal_warnings(record).warnings
        if w.where.startswith("measurement")
    ]
    assert len(codes) == 1, codes
    return codes[0]


def test_the_frontend_keys_on_the_code_python_actually_emits():
    """A cross-language guard, because the disclosure fails OPEN on a rename.

    If the Python code is renamed and the TypeScript literal is not, nothing throws
    — the badge simply stops disclosing, silently, and a record with no measured
    data goes back to reading as a full count. This test is what makes that loud.
    """
    code = _emitted_code()
    source = _DISCLOSURE_SOURCE.read_text(encoding="utf-8")
    assert f"'{code}'" in source, (
        f"{_DISCLOSURE_SOURCE.name} must declare the advisory code "
        f"portal_warnings emits ({code!r}); a rename on either side breaks the "
        "coverage disclosure without breaking anything else"
    )


def test_every_coverage_surface_uses_the_shared_predicate_not_its_own_literal():
    """Each consumer imports the predicate; none re-spells the code or the sentence.

    Asserted per FILE (a set of files, each checked), not as a count of matches:
    "two files mention it" would pass if one of them mentioned it in a comment.
    """
    code = _emitted_code()
    for path in _DISCLOSURE_CONSUMERS:
        source = path.read_text(encoding="utf-8")
        assert "carriesNoMeasurementSeries" in source, path.name
        assert "NO_SERIES_COVERAGE_NOTE" in source, path.name
        assert f"'{code}'" not in source, (
            f"{path.name} re-spells the advisory code instead of importing "
            "NO_MEASUREMENT_SERIES_CODE — two literals are two things to rename"
        )


def test_the_disclosure_sentence_classifies_nothing():
    """The sentence shipped to a reader must state an observation only.

    The four candidate meanings of an empty series (invalid / incomplete / not
    applicable / deliberately empty) belong to a domain owner. Asserted as a SET of
    forbidden verdict words over the sentence AS SHIPPED (read out of adapt.ts), so
    it also fails if the sentence is edited in place to say more than it may.
    """
    source = _DISCLOSURE_SOURCE.read_text(encoding="utf-8")
    marker = "export const NO_SERIES_COVERAGE_NOTE ="
    assert marker in source
    sentence = source.split(marker, 1)[1].split(";", 1)[0].strip().strip("'\"\n ").lower()
    assert sentence, "the disclosure sentence must not be empty"
    assert "no series target is counted" in sentence
    for forbidden in (
        "invalid",
        "incomplete",
        "not applicable",
        "failed",
        "compromised",
        "suspicious",
        "should",
        "must",
        "error",
    ):
        assert forbidden not in sentence, (
            f"the disclosure says {forbidden!r} — that classifies the empty series, "
            "which is a scientific decision this app does not make"
        )
