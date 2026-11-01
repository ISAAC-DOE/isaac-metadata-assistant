"""c15c: two fixes from a real-data walk. Synthetic only (the committed multi-operator corpus, ZZ names).

* H1: a decision recorded again with the value it already held (a sheet ruling "tied to your sheet") changes
  only a decision id and time. A re-export keeps the record's id and rewrites only its evidence sidecar; a real
  value change still gets a new id and supersedes; ``upload --dry-run`` names the record ids a record replaces.
"""

from __future__ import annotations

import json

from isaac_api.local_import import mutations as M
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
