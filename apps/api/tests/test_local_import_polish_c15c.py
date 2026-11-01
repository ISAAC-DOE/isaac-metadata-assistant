"""c15c: two fixes from a real-data walk. Synthetic only (the committed multi-operator corpus, ZZ names).

* H1: a decision recorded again with the value it already held (a sheet ruling "tied to your sheet") changes
  only a decision id and time. A re-export keeps the record's id and rewrites only its evidence sidecar; a real
  value change still gets a new id and supersedes; ``upload --dry-run`` names the record ids a record replaces.
* M6: a run's technique disagreement whose run already holds a scientist's decision for the field (a sheet ruling)
  is covered by it: ``affects_record`` false, not counted in ``conflicts_affecting_a_record``, under the same id. A
  run with no decision of its own still counts.
"""

from __future__ import annotations

import json

from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, _decide_everything, _portal, bdir, fake_upstream, pristine)

NAME = "sample.material.name"


def _rerecord_same_value(bdir, path=NAME, run_id="run-001"):
    """What ``template import --apply`` does for a ruling that keeps the value already held (c14i MED-1)."""
    def change(b):
        c = _cand(b, path, run_id)
        latest = [d for d in b["scientist_decisions"] if d["target"] == {"kind": "candidate", "id": c["candidate_id"]}][-1]
        return M.record_decision(b, target_ids=[c["candidate_id"]], decision=latest["decision"], value=latest["value"],
                                 by=BY["by"], orcid=BY["orcid"], note="tied to your sheet", record_unchanged=True)
    got = M.mutate(bdir, change)
    assert got["recorded"], got  # a NEW decision, with a new id and time
    R.build_records(bdir)


def _export(bdir, out):
    [row] = R.export_records(bdir, out, run_portal=_portal("publish"))["exported"]
    return row


def test_a_same_value_re_record_keeps_the_record_id_and_refreshes_only_the_sidecar(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    first = _export(bdir, out)
    rid = first["record_id"]
    record, sidecar = (out / f"{rid}.json").read_bytes(), json.loads((out / f"{rid}.evidence.json").read_text())
    _rerecord_same_value(bdir)
    row = _export(bdir, out)
    assert row["record_id"] == rid and row["export"] == "unchanged" and row["evidence_refreshed"] is True
    assert "replaces_record_id" not in row and "Only its evidence sidecar was rewritten" in row["export_statement"]
    assert (out / f"{rid}.json").read_bytes() == record  # the record, byte for byte
    assert not (out / R.SUPERSEDED_DIR).exists()
    new_sidecar = json.loads((out / f"{rid}.evidence.json").read_text())
    assert new_sidecar != sidecar  # it cites the new decision
    ids = lambda s: {e.get("decision_id") for e in s["evidence"][NAME] if e.get("source_type") == "user_confirmation"}  # noqa: E731
    assert ids(new_sidecar) != ids(sidecar)
    [entry] = json.loads((out / R.EXPORT_INDEX).read_text())["records"]
    assert entry["record_id"] == rid and entry["replaced_record_ids"] == [] and entry["substance_sha256"].startswith("sha256:")
    assert [p["record"] for p in R.upload_plan(out, None)] == [f"{rid}.json"]
    # and exporting once more is unchanged byte for byte, the sidecar included
    files = {p.name: p.read_bytes() for p in out.glob("*.json")}
    again = _export(bdir, out)
    assert again["record_id"] == rid and "evidence_refreshed" not in again
    assert {p.name: p.read_bytes() for p in out.glob("*.json")} == files


def test_an_index_from_an_earlier_build_is_compared_with_the_files_it_wrote(bdir, tmp_path):
    """An index entry with no ``substance_sha256`` (written before this fix): the record on disk is compared."""
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    rid = _export(bdir, out)["record_id"]
    index = json.loads((out / R.EXPORT_INDEX).read_text())
    del index["records"][0]["substance_sha256"]
    (out / R.EXPORT_INDEX).write_text(json.dumps(index))
    _rerecord_same_value(bdir)
    row = _export(bdir, out)
    assert row["record_id"] == rid and row["evidence_refreshed"] is True


def test_a_value_change_still_gets_a_new_id_and_supersedes(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    old = _export(bdir, out)["record_id"]
    _rerecord_same_value(bdir)
    assert _export(bdir, out)["record_id"] == old
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_cand(b, NAME, "run-001")["candidate_id"]], decision="correct",
             value="ZZ1 synthetic, revised", **BY)
    R.build_records(bdir)
    row = _export(bdir, out)
    assert row["export"] == "replaced" and row["replaces_record_id"] == old and row["record_id"] != old
    assert "evidence_refreshed" not in row
    assert not (out / f"{old}.json").exists() and (out / R.SUPERSEDED_DIR / f"{old}.json").is_file()


def test_the_upload_dry_run_names_the_record_ids_a_record_replaces(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    old = _export(bdir, out)["record_id"]
    [plan] = R.upload_plan(out, None)
    assert "replaces_record_ids" not in plan and "replaces_statement" not in plan  # a first export replaces nothing
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_cand(b, NAME, "run-001")["candidate_id"]], decision="correct",
             value="ZZ1 synthetic, revised", **BY)
    R.build_records(bdir)
    new = _export(bdir, out)["record_id"]
    [plan] = R.upload_plan(out, None)
    assert plan["record"] == f"{new}.json" and plan["replaces_record_ids"] == [old]
    assert old in plan["replaces_statement"] and "the portal still holds it" in plan["replaces_statement"]


# --- M6 ------------------------------------------------------------------------------------------------------------

TECH = "system.technique"
RULED, UNRULED = "conf-007", "conf-009"  # run-004's and run-005's disagreements in the corpus


def _technique_conflicts(bdir):
    """The BL15-2 shape (as test_d6 makes it): two runs' disagreements are about the technique."""
    M.group(bdir)
    b = M.load(bdir)
    cand_of = {c["candidate_id"]: c for c in b["candidates"]}
    conflicts = {cf["conflict_id"]: cf for cf in b["conflicts"]}
    for cid in (RULED, UNRULED):
        cand_of[conflicts[cid]["candidate_id"]]["target_field_path"] = TECH
    M.save_bundle(bdir, b)
    beam = next(c for c in b["candidates"] if c["target_field_path"] == TECH and c["run_id"] is None)
    # the sheet's beamtime Technique: every record has the field, so neither disagreement blocks
    M.decide(bdir, target_ids=[beam["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    return conflicts


def _conflict_q(payload, conflict_id):
    return next(q for q in payload["questions"] if q["targets"] == [{"kind": "conflict", "id": conflict_id}])


def test_a_ruled_technique_on_a_run_takes_its_conflict_out_of_the_affecting_count(bdir):
    conflicts = _technique_conflicts(bdir)
    before = Q.consolidate(M.load(bdir))
    q0 = _conflict_q(before, RULED)
    assert q0["tier"] == Q.TIER_CONFLICT and q0["affects_record"] is True  # the walk's "Answer here only with the same thing"
    # the run's own ruling: HERFD-XAS for run-004 (what a sheet row's Technique ruling records)
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    after = Q.consolidate(M.load(bdir))
    assert next(cf for cf in M.load(bdir)["conflicts"] if cf["conflict_id"] == RULED)["value_state"] == "conflicting"
    q = _conflict_q(after, RULED)
    assert q["question_id"] == q0["question_id"]  # the same id
    assert q["affects_record"] is False and q["tier"] == Q.TIER_OPTIONAL and not q["blocking"]
    [did] = q["covered_by_decisions"]
    assert q["why"].startswith(f"Already decided: its run holds a scientist's decision for {TECH} ({did})")
    assert after["counts"]["conflicts_affecting_a_record"] == before["counts"]["conflicts_affecting_a_record"] - 1
    assert after["counts"]["conflicts_affecting_a_record"] == sum(x["tier"] == Q.TIER_CONFLICT for x in after["questions"])


def test_an_unruled_run_still_counts(bdir):
    conflicts = _technique_conflicts(bdir)
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    p = Q.consolidate(M.load(bdir))
    q = _conflict_q(p, UNRULED)
    assert q["affects_record"] is True and q["tier"] == Q.TIER_CONFLICT and "covered_by_decisions" not in q
    assert p["counts"]["conflicts_affecting_a_record"] >= 1


def test_a_deferred_run_answer_does_not_cover_its_conflict(bdir):
    conflicts = _technique_conflicts(bdir)
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="defer", value=None, **BY)
    q = _conflict_q(Q.consolidate(M.load(bdir)), RULED)
    assert q["affects_record"] is True and q["tier"] == Q.TIER_CONFLICT and "covered_by_decisions" not in q
