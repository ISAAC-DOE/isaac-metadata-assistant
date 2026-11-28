"""The record of an approved ``isaac.xas.v1`` curve carries how it was processed (local_import/provenance.py).

An end-to-end test on real data (17 Nov 2026) found the record kept only the normalised curve and E0, named only the
protocol version, and left the energy reference, the per-scan shifts and the keep / drop decisions in uncited files.
Now: the merged raw average is a second series; ``generated_by`` names the protocol, adapter and vendored engine
versions and its notes say the processing in plain words; the evidence sidecar has a full ``processing`` block with
each output file's sha256. And three engine fixes the same test found: the merge grid comes from a KEPT scan,
calibration (absolute, none) and alignment (per scan) are said apart, and a remark never contradicts its decision.

SYNTHETIC only: the committed multi-operator corpus (test_local_import_records) and the engine tests' invented SYN_*
scans (test_local_import_engine_xas). The portal runner is mocked.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api.local_import import mutations as M
from isaac_api.local_import import provenance as PV
from isaac_api.local_import import records as R

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _add_group, _cand, _miss, _portal, bdir, fake_upstream, pristine)

REPO_ROOT = ws.REPO_ROOT


@pytest.fixture(scope="module", autouse=True)
def _name_deductions_off():
    """1.22.0 (DEC-100 fix round): this module's subject is not the set-point or control-mode deductions from a run's
    file name, and its synthetic runs were written for set-points that are asked: the two deductions are switched off
    here (``tests_support_records.without_name_deductions``; the rules are pinned in ``test_local_import_guesses``)."""
    from tests_support_records import without_name_deductions

    with without_name_deductions():
        yield


def _engine():
    for mod in ("numpy", "larch", "scipy", "yaml"):
        pytest.importorskip(mod, reason="isaac.xas.v1 needs the optional `processing` extra")
    import test_local_import_engine_xas as T

    return T


def _decide_the_rest(bdir: Path, result_id: str) -> None:
    """test_local_import_records._decide_everything, for a group g1 whose result is ``result_id``."""
    b = M.load(bdir)
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=[result_id], decision="approve", value=None, qc_status="valid", **BY)
    M.decide(bdir, target_ids=[_cand(b, "timestamps.acquired_start_utc", "run-001")["candidate_id"]], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=[_cand(b, "sample.material.name", "run-001")["candidate_id"]], decision="correct", value="ZZ1 synthetic", **BY)
    M.decide(bdir, target_ids=[_cand(b, "system.technique", None)["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    M.decide(bdir, target_ids=[_miss(b, "system.domain", None)], decision="correct", value="experimental", **BY)
    M.decide(bdir, target_ids=[_miss(b, "attribution.produced_by.group", None)], decision="correct", value="Synthetic Scientist group", **BY)
    M.decide(bdir, target_ids=[_miss(b, "attribution.produced_by.organization", None)], decision="correct", value="Synthetic University", **BY)
    for path, value in (("context.environment", "ex_situ"), ("sample.sample_form", "powder"), ("context.temperature_K", 298.0)):
        M.decide(bdir, target_ids=[_miss(b, path, "run-001")], decision="correct", value=value, **BY)


@pytest.fixture()
def engine_run(tmp_path, monkeypatch):
    """A v1 result of the SYN group 02 whose FIRST scan (the first on the modal grid) the scientist dropped, and whose
    noisier scan carries a remark and is dropped by the scientist too."""
    T = _engine()
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")
    scans = [T.scan_cols(20 + k, d=d) for k, d in enumerate(T.SMP_D)] + [T.scan_cols(40, noise=6e-3)]
    runs = [("01_SYN_ZZ1_060mV", 9, [T.scan_cols(10 + k, d=d) for k, d in enumerate(T.REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, scans)]
    eng, root = T.imported(tmp_path / "eng", runs)
    r = T.by_run(T.v1_results(eng), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r["scan_decisions"]["rows"]}
    drop = [rows[1]["scan_id"], rows[6]["scan_id"]]
    M.decide(eng, target_ids=[r["group_id"]], decision="set_scan_decision", value={"decision": "drop", "scans": drop}, **BY)
    M.process(eng, source=str(root), group_ids=[r["group_id"]])
    new = [x for x in T.v1_results(eng) if x["group_id"] == r["group_id"]][-1]
    return eng, new, drop


def _transplant(bdir: Path, eng: Path, result: dict) -> dict:
    """The corpus bundle's group g1 (test_local_import_records._add_group), with the engine's v1 result as its result:
    the result and its files copied in unchanged (paths relative to the bundle), only its group id is g1's."""
    _add_group(bdir)
    b = M.load(bdir)
    b["processing_results"] = [x for x in b["processing_results"] if x["result_id"] != "p1"]
    res = json.loads(json.dumps(result))
    res["group_id"] = "g1"
    res["state"] = "needs_review"
    for f in res["outputs"]["files"]:
        dest = bdir / f["relative_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(eng / f["relative_path"], dest)
    b["processing_results"].append(res)
    M.save_bundle(bdir, b)
    return res


def _exported_v1(bdir, tmp_path, engine_run):
    eng, result, drop = engine_run
    res = _transplant(bdir, eng, result)
    _decide_the_rest(bdir, res["result_id"])
    R.build_records(bdir)
    out = tmp_path / "records"
    export = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert len(export["exported"]) == 1, export
    rid = export["exported"][0]["record_id"]
    record = json.loads((out / f"{rid}.json").read_text())
    sidecar = json.loads((out / f"{rid}.evidence.json").read_text())
    return res, record, sidecar, out, rid, drop


def test_the_v1_record_validates_and_carries_its_processing_story(bdir, tmp_path, engine_run):
    from isaac_records.official import validate_official

    res, record, sidecar, out, rid, drop = _exported_v1(bdir, tmp_path, engine_run)
    import os

    assert validate_official(record, Path(os.environ["ISAAC_PORTAL_VALIDATOR_DIR"])).ok  # the export target
    assert validate_official(record, REPO_ROOT).ok                                      # the vendored schema
    # generated_by: the v1 agent, the protocol + adapter + vendored engine versions, the plain-English story
    (block,) = record["descriptors"]["outputs"]
    gb = block["generated_by"]
    assert gb["agent"] == "isaac.xas.v1"
    assert gb["version"] == (f"protocol {res['protocol_version']}; adapter isaac.xas.engine_adapter.v1; xas-analysis "
                             f"{res['engine']['engine_version']} (vendored, see src/xas_analysis/PROVENANCE.md)")
    notes = gb["notes"]
    assert "none is needed" not in notes
    for said in ("Energy: no absolute energy calibration was applied", "not across beamtimes",
                 "not traced to a tabulated energy", "scan-to-scan spread of the raw IF/I0",
                 "grid point of the maximum first derivative", "no self-absorption (over-absorption) correction",
                 "aligned to one beamtime energy reference, the I0 glitch", "anchored on the earliest group", "shifts ",
                 " meV", "Scans: 4 of 6 kept (4 merged), 2 dropped (the scientist's decision: ",
                 "Normalisation: Victoreen background + McMaster step", "pre-edge ",
                 "post-edge ", "Points excluded: none", "edge step", "no edge-step name", res["result_id"]):
        assert said in notes, said
    assert [d["name"] for d in block["descriptors"]] == ["edge_position"]  # no invented edge-step descriptor
    # the merged raw average is a second series beside the normalised one
    series = {s["series_id"]: s for s in record["measurement"]["series"]}
    assert set(series) == {"g1_normalized", "g1_merged"}
    merged = series["g1_merged"]
    assert [(c["name"], c["role"], c["unit"]) for c in merged["channels"]] == [
        ("absorption", "derived_signal", "arb"), ("absorption_stderr", "quality_monitor", "arb"),
        ("scans_averaged", "quality_monitor", "count")]
    n = merged["channels"][2]["values"]
    assert max(n) == 4.0 and min(n) >= 1.0  # fewer only at the grid's ends, where a shifted scan does not reach
    assert "g1_merged" in series["g1_normalized"]["notes"]
    assert record["measurement"]["processing"]["steps"] == ["energy_alignment", "spectrum_merging", "normalization"]
    assert "series:g1_merged" in sidecar["evidence"]


def test_the_sidecar_processing_block_is_complete_with_correct_hashes(bdir, tmp_path, engine_run):
    res, record, sidecar, out, rid, drop = _exported_v1(bdir, tmp_path, engine_run)
    p = sidecar["processing"]
    assert p["result_id"] == res["result_id"] and p["group_id"] == "g1"
    assert p["protocol"] == {"id": "isaac.xas.v1", "version": res["protocol_version"], "status": "draft_unreviewed"}
    assert p["versions"]["engine"] == "xas-analysis" and p["versions"]["engine_version"] == res["engine"]["engine_version"]
    assert p["versions"]["adapter_rule_id"] == "isaac.xas.engine_adapter.v1"
    assert p["generated_by"] == record["descriptors"]["outputs"][0]["generated_by"]
    assert p["energy"]["reference"]["routes"][0]["mode"] == "glitch_I0"
    assert p["energy"]["absolute_calibration"]["applied"] is False
    assert p["energy"]["alignment"]["scans_aligned"] == 6
    assert len(p["scan_shifts"]["rows"]) == 6 and all("shift_eV" in x for x in p["scan_shifts"]["rows"])
    rows = {x["scan_id"]: x for x in p["scan_decisions"]["rows"]}
    assert len(rows) == 6
    for sid in drop:
        assert rows[sid]["decision"] == "drop" and rows[sid]["decided_by"] == "scientist"
        assert rows[sid]["override"]["decided_by"] == BY["by"]
    assert all("reason_codes" in x and "remarks" in x for x in rows.values())
    assert p["normalization"]["window_eV"] and p["normalization"]["model"] == "victoreen"
    assert p["excluded_points"]["points"] == []
    roles = [a["role"] for a in p["artifacts"]]
    assert roles[:5] == ["params", "scan_decisions", "merged", "normalized", "plot"] and "qc" in roles
    for a in p["artifacts"]:
        on_disk = (bdir / a["relative_path"]).read_bytes()
        assert a["sha256"] == hashlib.sha256(on_disk).hexdigest() and a["matches_file"] is True
        assert not a["relative_path"].startswith("/")
        assert (out / f"{rid}.artifacts" / a["relative_path"]).read_bytes() == on_disk  # beside the record too
    # unchanged on a second export (deterministic: no evidence refresh)
    again = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert again["exported"][0]["export"] == "unchanged" and not again["exported"][0].get("evidence_refreshed")


def test_the_merge_grid_comes_from_a_kept_scan(engine_run):
    _eng, r, drop = engine_run
    merge = next(s for s in r["steps"] if s["step"] == "merge")
    rows = {x["scan_id"]: x for x in r["scan_decisions"]["rows"]}
    grid = merge["outcome"]["grid_from_scan"]
    assert grid not in drop and rows[grid]["decision"] == "keep" and rows[grid]["merged"]
    assert "dropped" in merge["params"]["grid"]  # the regrid is said
    E = [float(line.split(",")[0]) for line in (_eng / next(f["relative_path"] for f in r["outputs"]["files"]
                                                             if f["role"] == "merged")).read_text().splitlines()[2:]]
    shift = next(x for x in r["scan_shifts"]["rows"] if x["scan_id"] == grid)["shift_eV"]
    assert E[0] == pytest.approx(_engine().GRID[0] + shift, abs=1e-5)


def test_calibration_and_alignment_are_said_apart_and_agree(engine_run, capsys):
    from isaac_api.local_import import cli

    eng, r, _drop = engine_run
    cal = next(s for s in r["steps"] if s["step"] == "calibration")["outcome"]
    assert cal["absolute_calibration"]["applied"] is False and cal["applied_shift_eV"] == 0.0
    assert cal["alignment"]["route"] == r["energy_reference"]["routes"][0]["mode"] == "glitch_I0"
    lo, hi = cal["alignment"]["shift_range_eV"]
    merged = [x["shift_eV"] for x in r["scan_decisions"]["rows"] if x["merged"]]
    assert (lo, hi) == (min(merged), max(merged))
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(eng), "processing-result", r["result_id"]]) == 0
    view = json.loads(capsys.readouterr().out)
    said = json.dumps(view["calibration"])
    assert "no energy reference" not in said.lower()
    assert view["calibration"]["alignment"]["statement"].startswith("Each scan was aligned to one beamtime energy "
                                                                    "reference, the I0 glitch")
    cal = view["calibration"]["absolute_calibration"]
    assert "none is needed" not in cal["statement"] and cal["traced_across_beamtimes"] is False
    assert "not traced to a tabulated energy" in cal["statement"]


def test_a_remark_never_contradicts_its_decision(engine_run):
    """A DROP row's remarks never say "kept" (the real-data row said "an intensity effect, kept"): the noisier scan's
    remark, dropped by the scientist, says the finding is not a reason to drop."""
    T = _engine()
    _eng, r, drop = engine_run
    noisy = next(x for x in r["scan_decisions"]["rows"] if x["scan_id"] == drop[1])
    assert noisy["notes"], noisy
    for x in r["scan_decisions"]["rows"]:
        for n in x["notes"]:
            if x["decision"] == "drop":
                assert not re.search(r"\bkept\b", n["said"]), (x["scan_id"], n["said"])
    # and in the rule itself: every remark kind a dropped scan can carry
    weak, noisy = T._rec("SYN_B#1", 1, scale=0.005, seed=1), T._rec("SYN_B#2", 2, noise=0.05, seed=2)
    flags = {"SYN_B#1": [{"test": "dead_channel", "reason": "dead IF channel", "value": 0.005, "median": 1.0,
                          "threshold": 0.01}],
             "SYN_B#2": [{"test": "shape", "reason": "shape rms 6e-02", "value": 0.06, "median": 0.002,
                          "threshold": 0.012}]}
    overrides = {s: {"decision": "drop", "decision_id": "d-syn", "decided_by": "SYN Scientist"} for s in ("SYN_B#1", "SYN_B#2")}
    rows = T._decide([weak, noisy], flags, overrides=overrides)["rows"]
    assert all(x["decision"] == "drop" and x["notes"] for x in rows)
    for x in rows:
        for n in x["notes"]:
            assert not re.search(r"\bkept\b", n["said"]) and "not a reason to drop" in n["said"], n["said"]


def test_a_record_from_a_v0_result_is_exported_as_before(bdir, tmp_path):
    """A result of another protocol (here the corpus's synthetic v0-shaped one) composes exactly as before: one
    series, generated_by with the protocol version only, no processing block in the sidecar."""
    from isaac_records.official import validate_official
    import os

    _add_group(bdir)
    b = M.load(bdir)
    p1 = next(x for x in b["processing_results"] if x["result_id"] == "p1")
    p1["protocol_id"], p1["protocol_version"] = "isaac.xas.v0", "0.3.0"
    p1["steps"].insert(0, {"step": "calibration", "params": {}, "outcome": {"applied": True, "applied_shift_eV": 0.4},
                           "flags": []})
    M.save_bundle(bdir, b)
    _decide_the_rest(bdir, "p1")
    R.build_records(bdir)
    out = tmp_path / "records"
    export = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert len(export["exported"]) == 1, export
    rid = export["exported"][0]["record_id"]
    record = json.loads((out / f"{rid}.json").read_text())
    sidecar = json.loads((out / f"{rid}.evidence.json").read_text())
    assert validate_official(record, Path(os.environ["ISAAC_PORTAL_VALIDATOR_DIR"])).ok
    assert [s["series_id"] for s in record["measurement"]["series"]] == ["g1_normalized"]
    assert "notes" not in record["measurement"]["series"][0]
    assert record["descriptors"]["outputs"][0]["generated_by"] == {"agent": "isaac.xas.v0", "version": "0.3.0"}
    assert "calibration" in record["measurement"]["processing"]["steps"]
    assert "processing" not in sidecar
    assert not PV.is_v1(p1)


# --- review of PR #334 ------------------------------------------------------------------------------------------------

def _merged_csv(path: Path, n: list[float], err: list[float]) -> Path:
    rows = [f"{11200 + i:.6f},{0.1 + 0.01 * i:.8g},{e:.8g},{k:.8g}" for i, (k, e) in enumerate(zip(n, err))]
    path.write_text("# SYNTHETIC FIXTURE\nenergy_eV,mu_mean,mu_stderr,n_scans\n" + "\n".join(rows) + "\n")
    return path


def _all_channels(series_list):
    return {c["name"]: (s, c) for s in series_list for c in s["channels"]}


def test_no_standard_error_is_claimed_where_one_scan_contributes(tmp_path):
    """MEDIUM: the engine writes err = 0 where ONE scan contributes (average.py: var / max(1, n - 1)). A standard
    error of 0 there is a claim the data does not support: those points carry no standard error."""
    series, said, stderr = PV.merged_series("g", _merged_csv(tmp_path / "m.csv", [1, 2, 3, 3, 2, 1], [0, .1, .2, .2, .1, 0]))
    ch = _all_channels(series)
    s, c = ch["absorption_stderr"]
    assert s["series_id"] == "g_merged_stderr" and len(c["values"]) == 4 and 0 not in c["values"]
    assert s["independent_variables"][0]["values"] == [11201.0, 11202.0, 11203.0, 11204.0]
    assert "fewer than 2 scans" in s["notes"] and stderr == "partial"
    main = next(x for x in series if x["series_id"] == "g_merged")
    assert [x["name"] for x in main["channels"]] == ["absorption", "scans_averaged"]
    assert len(main["channels"][0]["values"]) == 6
    # every point from two or more scans: the channel sits in the merged series itself
    series, said, stderr = PV.merged_series("g", _merged_csv(tmp_path / "m2.csv", [2, 3, 2], [.1, .2, .1]))
    assert [s["series_id"] for s in series] == ["g_merged"] and stderr == "all"
    assert "absorption_stderr" in [c["name"] for c in series[0]["channels"]]
    # one scan everywhere: no standard error at all, and the words say so
    series, said, stderr = PV.merged_series("g", _merged_csv(tmp_path / "m3.csv", [1, 1, 1], [0, 0, 0]))
    assert "absorption_stderr" not in _all_channels(series) and stderr is None
    assert "standard error" in said and "not given" in said


def test_the_notes_say_the_standard_error_only_when_the_record_has_it(engine_run):
    _eng, r, _ = engine_run
    assert "with its standard error" in PV.summary(r, merged_series_id="g_merged", merged_stderr="all")
    partial = PV.summary(r, merged_series_id="g_merged", merged_stderr="partial")
    assert "standard error where two or more scans contribute" in partial
    none = PV.summary(r, merged_series_id="g_merged", merged_stderr=None)
    assert "standard error" not in none


def test_the_scan_count_note_names_both_reasons_for_fewer_scans(tmp_path):
    series, _, _ = PV.merged_series("g", _merged_csv(tmp_path / "m.csv", [2, 3, 2], [.1, .2, .1]))
    note = _all_channels(series)["scans_averaged"][1]["notes"]
    assert "I0 dropout" in note and "ends of the grid" in note


@pytest.mark.parametrize("bad", ["../outside.csv", "/abs/merged.csv", "C:/x/merged.csv", "a\\..\\b.csv", ""])
def test_an_unsafe_artifact_path_is_left_out_of_the_sidecar_with_a_note(tmp_path, bad):
    assert PV.bundle_relative(bad) is None
    assert PV.bundle_relative("processing/g/r-1/merged.csv") == "processing/g/r-1/merged.csv"
    result = {"protocol_id": "isaac.xas.v1", "source": "isaac_protocol", "engine": {}, "result_id": "p-syn",
              "outputs": {"files": [{"role": "plot", "relative_path": bad, "sha256": "0" * 64}]}}
    (art,) = PV.sidecar_block(result, tmp_path, group_id="g", generated=None)["artifacts"]
    assert "relative_path" not in art and art["matches_file"] is False
    assert "not a bundle-relative path" in art["note"]


def test_an_unsafe_artifact_path_is_left_out_of_the_export_row(bdir, tmp_path, monkeypatch):
    """The bundle schema refuses such a path on write; a bundle that carries one anyway (edited by hand) still never
    has it echoed into the export reply (defence in depth: the output list is given one past the bundle's validation)."""
    _add_group(bdir)
    _decide_the_rest(bdir, "p1")
    R.build_records(bdir)
    real = R._artifact_sources

    def with_bad_path(bundle, bundle_dir, group_id):
        return real(bundle, bundle_dir, group_id) + [
            ({"role": "plot", "relative_path": "../SYN_outside.png", "sha256": "0" * 64}, None)]

    monkeypatch.setattr(R, "_artifact_sources", with_bad_path)
    export = R.export_records(bdir, tmp_path / "records", run_portal=_portal("publish"))
    (row,) = export["exported"]
    refused = [a for a in row["artifacts"] if isinstance(a, dict)]
    assert refused and all("relative_path" not in a for a in refused), refused
    assert "not a bundle-relative path" in refused[0]["refused"]


def test_without_a_generated_by_in_the_record_the_sidecar_shows_none(bdir, tmp_path, engine_run):
    """LOW: no numeric E0, no descriptors output in the record, so no generated_by: the sidecar does not show one."""
    eng, result, _ = engine_run
    res = _transplant(bdir, eng, result)
    _decide_the_rest(bdir, res["result_id"])
    R.build_records(bdir)
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    block = R.processing_sidecar(M.load(bdir), bdir, "g1", comp, {"record_id": "SYN"})
    assert "generated_by" not in block and "no generated_by" in block["generated_by_note"]
    assert block["summary"].startswith("Processed from the raw scans by isaac.xas.v1")
