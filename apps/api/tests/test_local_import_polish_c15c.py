"""c15c: two fixes from a real-data walk. Synthetic only (the committed multi-operator corpus, ZZ names).

* H1: a decision recorded again with the value it already held (a sheet ruling "tied to your sheet") changes
  only a decision id and time. A re-export keeps the record's id and rewrites only its evidence sidecar; a real
  value change still gets a new id and supersedes; ``upload --dry-run`` names the record ids a record replaces.
* H1 review (MED): the id follows the record BODY alone. The same value confirmed by another operator, or read
  from another source file, keeps the id; ``evidence_changed`` says what the rewritten evidence file changed.
* M6: a run's technique disagreement whose run already holds a scientist's decision for the field (a sheet ruling)
  is covered by it: ``affects_record`` false, not counted in ``conflicts_affecting_a_record``, under the same id. A
  run with no decision of its own still counts.
"""

from __future__ import annotations

import json
import time

from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, _decide_everything, _portal, bdir, fake_upstream, pristine)

NAME = "sample.material.name"


def _rerecord_same_value(bdir, path=NAME, run_id="run-001", by=BY["by"]):
    """What ``template import --apply`` does for a ruling that keeps the value already held (c14i MED-1)."""
    def change(b):
        c = _cand(b, path, run_id)
        latest = [d for d in b["scientist_decisions"] if d["target"] == {"kind": "candidate", "id": c["candidate_id"]}][-1]
        return M.record_decision(b, target_ids=[c["candidate_id"]], decision=latest["decision"], value=latest["value"],
                                 by=by, orcid=BY["orcid"], note="tied to your sheet", record_unchanged=True)
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
    first_at = json.loads((out / R.EXPORT_INDEX).read_text())["records"][0]["exported_utc"]
    record, sidecar = (out / f"{rid}.json").read_bytes(), json.loads((out / f"{rid}.evidence.json").read_text())
    time.sleep(1.05)  # r6h: the times below are to the second; without this a fast run wrote both in one second
    _rerecord_same_value(bdir)
    row = _export(bdir, out)
    assert row["record_id"] == rid and row["export"] == "unchanged" and row["evidence_refreshed"] is True
    assert "replaces_record_id" not in row and "The evidence file was rewritten: " in row["export_statement"]
    assert "a decision was recorded again" not in row["export_statement"]
    assert row["evidence_changed"] == [f"{NAME}: the decision id, the decision time"] and row["evidence_changed_total"] == 1
    assert (out / f"{rid}.json").read_bytes() == record  # the record, byte for byte
    assert not (out / R.SUPERSEDED_DIR).exists()
    new_sidecar = json.loads((out / f"{rid}.evidence.json").read_text())
    assert new_sidecar != sidecar  # it cites the new decision
    assert new_sidecar["generated_utc"] != sidecar["generated_utc"]  # written now, not at the record's export time
    ids = lambda s: {e.get("decision_id") for e in s["evidence"][NAME] if e.get("source_type") == "user_confirmation"}  # noqa: E731
    assert ids(new_sidecar) != ids(sidecar)
    [entry] = json.loads((out / R.EXPORT_INDEX).read_text())["records"]
    assert entry["record_id"] == rid and entry["replaced_record_ids"] == [] and entry["body_sha256"].startswith("sha256:")
    assert entry["sidecar_generated_utc"] == new_sidecar["generated_utc"] and entry["exported_utc"] == first_at
    assert [p["record"] for p in R.upload_plan(out, None)] == [f"{rid}.json"]
    # and exporting once more is unchanged byte for byte, the sidecar included
    files = {p.name: p.read_bytes() for p in out.glob("*.json")}
    again = _export(bdir, out)
    assert again["record_id"] == rid and "evidence_refreshed" not in again
    assert {p.name: p.read_bytes() for p in out.glob("*.json")} == files


def test_an_index_from_an_earlier_build_is_compared_with_the_files_it_wrote(bdir, tmp_path):
    """An index entry with no ``body_sha256`` (written before this fix): the record on disk is compared."""
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    rid = _export(bdir, out)["record_id"]
    index = json.loads((out / R.EXPORT_INDEX).read_text())
    del index["records"][0]["body_sha256"]
    del index["records"][0]["sidecar_generated_utc"]
    (out / R.EXPORT_INDEX).write_text(json.dumps(index))
    _rerecord_same_value(bdir)
    row = _export(bdir, out)
    assert row["record_id"] == rid and row["evidence_refreshed"] is True


def test_another_operator_confirming_the_same_value_keeps_the_id_and_says_what_changed(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    rid = _export(bdir, out)["record_id"]
    record = (out / f"{rid}.json").read_bytes()
    _rerecord_same_value(bdir, by="Another Synthetic Operator")
    row = _export(bdir, out)
    assert row["record_id"] == rid and row["export"] == "unchanged" and row["evidence_refreshed"] is True
    assert (out / f"{rid}.json").read_bytes() == record
    [line] = row["evidence_changed"]
    assert line.startswith(f"{NAME}: ") and "who confirmed it" in line
    assert [p.get("replaces_record_ids") for p in R.upload_plan(out, None)] == [None]


def test_the_same_value_read_from_another_source_file_keeps_the_id(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    rid = _export(bdir, out)["record_id"]
    record = (out / f"{rid}.json").read_bytes()

    def cite_another_file(b):
        for e in _cand(b, NAME, "run-001")["evidence"]:
            if e["method"] != "ai_interpretation":
                e["relative_path"] = "SYN_other/ZZ_same_statement.txt"
    M.mutate(bdir, cite_another_file)
    R.build_records(bdir)
    row = _export(bdir, out)
    assert row["record_id"] == rid and row["export"] == "unchanged" and (out / f"{rid}.json").read_bytes() == record
    assert any(x.startswith(f"{NAME}: ") and "the source file" in x for x in row["evidence_changed"])
    sidecar = json.loads((out / f"{rid}.evidence.json").read_text())
    assert any(e.get("source_file") == "SYN_other/ZZ_same_statement.txt" for e in sidecar["evidence"][NAME])


def test_a_newer_build_composing_another_body_from_the_same_draft_gets_a_new_id(bdir, tmp_path, monkeypatch):
    """c15c LOW 1: the same draft (content_sha256 unchanged) is not enough; the body hash is compared too."""
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    old = _export(bdir, out)["record_id"]
    compose = R.compose_record

    def newer_build(draft, composition, *, record_id, now):
        record = compose(draft, composition, record_id=record_id, now=now)
        record["tags"] = ["SYN-from-a-newer-build"]
        return record
    monkeypatch.setattr(R, "compose_record", newer_build)
    row = _export(bdir, out)
    assert row["export"] == "replaced" and row["record_id"] != old and row["replaces_record_id"] == old
    assert (out / R.SUPERSEDED_DIR / f"{old}.json").is_file()


def test_a_restored_record_leaves_no_copy_in_withdrawn(bdir, tmp_path):
    """c15c LOW 2: restored under its id (the same body): its withdrawn copy is removed, one id names one set of files."""
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    rid = _export(bdir, out)["record_id"]
    R.export_records(bdir, out, run_portal=_portal("needs_review"))
    assert (out / R.WITHDRAWN_DIR / f"{rid}.json").is_file()
    _rerecord_same_value(bdir, by="Another Synthetic Operator")
    row = _export(bdir, out)
    assert row["record_id"] == rid and row["restored_from_withdrawn"] is True and row["evidence_refreshed"] is True
    names = [f"{rid}.json", f"{rid}.evidence.json", f"{rid}.artifacts"]
    assert row["withdrawn_copy_removed"] == [f"{R.WITHDRAWN_DIR}/{n}" for n in names]
    assert not any((out / R.WITHDRAWN_DIR / n).exists() for n in names)
    assert (out / f"{rid}.artifacts").is_dir()  # the processed curve is at the top, with the record
    assert "its copy in isaac-export/withdrawn/ was removed" in row["export_statement"]
    assert [p["record"] for p in R.upload_plan(out, None)] == [f"{rid}.json"]


def test_evidence_changes_match_entries_by_content():
    """c15c LOW 3: an added entry is said as such, never as positional mismatches; a reordered list differs in nothing."""
    a = {"source_type": "document", "source_file": "SYN_a.txt", "quote": "ZZ1"}
    b = {"source_type": "document", "source_file": "SYN_b.txt", "quote": "ZZ1"}
    c = {"source_type": "user_confirmation", "decided_by": "Synthetic Scientist", "answer": "ZZ1"}
    old = {"evidence": {NAME: [a, c]}, "schemas_used": {}}
    assert R.evidence_changes(old, {"evidence": {NAME: [b, a, c]}, "schemas_used": {}}) == [f"{NAME}: entries added or removed"]
    assert R.evidence_changes(old, {"evidence": {NAME: [c, a]}, "schemas_used": {}}) == []
    assert R.evidence_changes(old, {"evidence": {NAME: [c, b]}, "schemas_used": {}}) == [f"{NAME}: the source file"]


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
    assert plan["replaces_statement"].startswith(f"This record replaces an earlier export of the same group: {old} "
                                                 f"(in {R.SUPERSEDED_DIR}/).")
    assert "the portal still holds it" in plan["replaces_statement"]
    # a second change: two earlier exports, each named where it is
    M.decide(bdir, target_ids=[_cand(M.load(bdir), NAME, "run-001")["candidate_id"]], decision="correct",
             value="ZZ1 synthetic, revised twice", **BY)
    R.build_records(bdir)
    newest = _export(bdir, out)["record_id"]
    [plan] = R.upload_plan(out, None)
    assert plan["record"] == f"{newest}.json" and plan["replaces_record_ids"] == [old, new]
    assert plan["replaces_statement"].startswith(
        f"This record replaces earlier exports of the same group: {old} (in {R.SUPERSEDED_DIR}/); {new} (in "
        f"{R.SUPERSEDED_DIR}/). If any of them was already uploaded")


# --- M6 ------------------------------------------------------------------------------------------------------------

TECH = "system.technique"
# r4-b M1: a beamtime-wide technique answer now covers every run's technique disagreement itself, so the run-level
# rulings below are tested on an OPTIONAL field no beamtime answer fills (a disagreement there never blocks)
OWN = "sample.material.formula"
RULED, UNRULED = "conf-007", "conf-009"  # run-004's and run-005's disagreements in the corpus


def _technique_conflicts(bdir, path=OWN):
    """The BL15-2 shape (as test_d6 makes it): two runs' disagreements are about one field. For the technique, the
    sheet's beamtime Technique is answered too: every record has the field, so neither disagreement blocks."""
    M.group(bdir)
    b = M.load(bdir)
    cand_of = {c["candidate_id"]: c for c in b["candidates"]}
    conflicts = {cf["conflict_id"]: cf for cf in b["conflicts"]}
    for cid in (RULED, UNRULED):
        cand_of[conflicts[cid]["candidate_id"]]["target_field_path"] = path
    M.save_bundle(bdir, b)
    if path == TECH:
        beam = next(c for c in b["candidates"] if c["target_field_path"] == TECH and c["run_id"] is None)
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
    assert q["why"].startswith(f"Already decided: its run holds a scientist's decision for {OWN} ({did})")
    assert after["counts"]["conflicts_affecting_a_record"] == before["counts"]["conflicts_affecting_a_record"] - 1
    assert after["counts"]["conflicts_affecting_a_record"] == sum(x["tier"] == Q.TIER_CONFLICT for x in after["questions"])
    # counted apart, never as optional (c15c review)
    assert after["counts"]["conflicts_covered_by_decisions"] == before["counts"]["conflicts_covered_by_decisions"] + 1
    assert after["counts"]["optional"] == before["counts"]["optional"]


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


def _two_runs(bdir):
    """RULED's disagreement names run-004 and run-005 (UNRULED's candidate is run-005's technique)."""
    def change(b):
        next(cf for cf in b["conflicts"] if cf["conflict_id"] == RULED)["run_ids"] = ["run-004", "run-005"]
    M.mutate(bdir, change)


def test_a_two_run_conflict_is_covered_only_when_its_runs_decisions_agree(bdir):
    conflicts = _technique_conflicts(bdir)
    _two_runs(bdir)
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    M.decide(bdir, target_ids=[conflicts[UNRULED]["candidate_id"]], decision="correct", value="XAS", **BY)
    q = _conflict_q(Q.consolidate(M.load(bdir)), RULED)
    assert "covered_by_decisions" not in q and q["affects_record"] is True  # the runs were decided differently
    M.decide(bdir, target_ids=[conflicts[UNRULED]["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    q = _conflict_q(Q.consolidate(M.load(bdir)), RULED)
    assert len(q["covered_by_decisions"]) == 2 and q["affects_record"] is False
    assert q["why"].startswith("Already decided: each of its runs holds")


def test_a_covered_conflict_is_not_also_shown_as_deferred(bdir):
    conflicts = _technique_conflicts(bdir)
    M.decide(bdir, target_ids=[RULED], decision="defer", value=None, **BY)  # "I don't know" on the disagreement
    assert _conflict_q(Q.consolidate(M.load(bdir)), RULED).get("deferred")
    M.decide(bdir, target_ids=[conflicts[RULED]["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    p = Q.consolidate(M.load(bdir))
    q = _conflict_q(p, RULED)
    assert q["covered_by_decisions"] and "deferred" not in q
    assert p["counts"]["deferred"] == sum(bool(x.get("deferred")) for x in p["questions"])
