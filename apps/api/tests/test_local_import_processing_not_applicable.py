"""A group the draft XAS protocol cannot apply to is NOT a QC fail.

``isaac process`` used to give every group a QC verdict, so a tab-separated file headed ``xes<N>``,
an MCA array, a headerless two-column file and a group with no scans all read ``fail`` — telling a
scientist their spectrum was bad when the truth is "this protocol does not apply" or "there is
nothing to process". Such a result now carries ``applicability.status = not_applicable`` with a
reason code (``no_xas_channel`` / ``no_scans``), the literals the data states about itself, and
no QC verdict; nothing downstream asks for it to be approved or lets it pass silently.

Every file here is SYNTHETIC (``SYN_*``, invented numbers). No real data.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import.processing import run as RUN

from test_local_import_records import BY, _cand, _miss, _portal, bdir, pristine  # noqa: F401  (fixtures)

# --- synthetic files, in the layouts the generic readers claim -------------------------------------

#: ``xes_tab_v1`` layout: tab-separated ``xes<N>`` header, bare-CR line ends.
XES_TAB = "xes0\txes2\txes9\r" + "".join(f"{7000 + i * 0.5:.2f}\t{100 + i}\t{50 + i % 3}\r" for i in range(40))
#: ``mca_v1`` layout: ``#F``/``#S``/``#@MCA``/``#@CHANN``/``#@CALIB`` then an ``@A`` array.
MCA = "#F /SYN/SYN_mca.mca\n#D SYN\n\n#S 1 (SYN_mca)\n#D SYN\n#@MCA %16C\n#@CHANN 8 0 7 1\n#@CALIB 0 1 0\n@A 1 2 3 4 5 6 7 8\\\n 9 10 11 12\n"
#: ``two_column_v1`` layout: two numbers per line, no header.
TWO_COLUMN = "".join(f"{7000 + i * 0.5:.2f} {0.1 + i * 0.01:.4f}\n" for i in range(40))

GENERIC = {
    "SYN_xes": ("generic:xes_tab_v1", "xes_tab_reader_v1", "xes_tab_v1", XES_TAB),
    "SYN_mca": ("generic:mca_v1", "mca_reader_v1", "mca_v1", MCA),
    "SYN_two": ("generic:two_column_v1", "two_column_reader_v1", "two_column_v1", TWO_COLUMN),
}


def _isaac(payload):
    return {r["group_id"]: r for r in payload["processing_results"] if r["source"] == "isaac_protocol"}


def _by_stem(payload, bundle):
    runs = {r["run_key"]: r for r in bundle["runs"]}
    from isaac_api.local_import import grouping as G

    out = {}
    for g in G.propose_record_groups(bundle):
        stem = runs[g["member_run_keys"][0]]["stem"]
        out[stem] = _isaac(payload)[g["group_id"]]
    return out


@pytest.fixture()
def processed(tmp_path):
    """One genuine XAS group, three generic non-XAS groups and one zero-scan group."""
    pytest.importorskip("numpy", reason="needs the optional `processing` extra")
    pytest.importorskip("larch", reason="needs the optional `processing` extra")
    from test_local_import_processing import fluo_scan, make_case, spec_file

    runs = [("01_SYN_ZZ1", [spec_file(fluo_scan(1)), spec_file(fluo_scan(2))], {"sample_name": "ZZ1"})]
    runs += [(stem, [text], {"sample_name": stem}) for stem, (_, _, _, text) in GENERIC.items()]
    runs += [("05_SYN_empty", [], {"sample_name": "empty"})]
    bdir_, root, bundle = make_case(tmp_path, runs)
    for run in bundle["runs"]:
        if run["stem"] in GENERIC:
            st, rid, prof, _ = GENERIC[run["stem"]]
            run["source_type"] = st
            run["reader"] = {"reader_id": rid, "profile": prof, "profile_version": "1"}
    (bdir_ / "bundle.json").write_text(json.dumps(bundle))
    payload = RUN.process_bundle(bdir_, source_root=root, bundle=bundle, created_utc="2026-10-28T00:00:00Z")
    return payload, bundle


# --- the processing rule ------------------------------------------------------------------------------


@pytest.mark.parametrize("stem,profile", [("SYN_xes", "xes_tab_v1"), ("SYN_mca", "mca_v1"), ("SYN_two", "two_column_v1")])
def test_a_group_with_no_absorption_channel_is_not_applicable_not_a_qc_fail(processed, stem, profile):
    payload, bundle = processed
    r = _by_stem(payload, bundle)[stem]
    app = r["applicability"]
    assert app["status"] == "not_applicable" and app["reason_code"] == "no_xas_channel"
    assert "verdict" not in r["qc"] and r["failure"] is None
    assert r["outputs"]["files"] == [] and r["review_flags"] == ["no_isaac_protocol_applies"]
    states = app["what_the_data_states"]
    assert states["readers"] == [{"source_type": GENERIC[stem][0], "reader_id": GENERIC[stem][1], "profile": profile}]
    # the reader's own stated LAYOUT, never a technique word
    assert states["reader_layout"] == [RUN.READER_LAYOUT[profile]]
    assert not any(w in json.dumps(states).lower() for w in ("emission", "absorption", "xanes", "exafs", "fluorescence"))
    assert "no ISAAC processing protocol covers this data yet" in app["statement"].replace("No ISAAC", "no ISAAC")


def test_the_xes_tab_group_states_its_own_column_labels(processed):
    payload, bundle = processed
    states = _by_stem(payload, bundle)["SYN_xes"]["applicability"]["what_the_data_states"]
    assert states["column_labels"] == ["xes0", "xes2", "xes9"] and states["scan_formats"] == ["delimited_columns"]


def test_a_group_with_no_scans_is_nothing_to_process_not_a_qc_fail(processed):
    payload, bundle = processed
    r = _by_stem(payload, bundle)["05_SYN_empty"]
    assert r["applicability"]["reason_code"] == "no_scans" and r["inputs"] == []
    assert "verdict" not in r["qc"] and r["failure"] is None
    assert r["applicability"]["what_the_data_states"]["readers"][0]["source_type"] == "spec_acquisition"


def test_a_genuine_xas_group_is_processed_exactly_as_before(processed, tmp_path):
    payload, bundle = processed
    r = _by_stem(payload, bundle)["01_SYN_ZZ1"]
    assert "applicability" not in r and r["qc"]["verdict"] in ("pass", "warn") and r["outputs"]["files"]
    # the same group processed ALONE yields the byte-identical result (content-addressed run id)
    from test_local_import_processing import fluo_scan, make_case, spec_file

    sub = tmp_path / "alone"
    sub.mkdir()
    alone_dir, root, alone = make_case(sub, [("01_SYN_ZZ1", [spec_file(fluo_scan(1)), spec_file(fluo_scan(2))], {"sample_name": "ZZ1"})])
    (only,) = _isaac(RUN.process_bundle(alone_dir, source_root=root, bundle=alone, created_utc="2026-10-28T00:00:00Z")).values()
    strip = lambda x: {k: v for k, v in x.items() if k != "prior_run_ids"}  # noqa: E731
    assert strip(only) == strip(r) and only["run_id"] == r["run_id"]


def test_the_summary_reports_not_applicable_apart_from_the_qc_verdicts(processed):
    payload, _ = processed
    s = payload["summary"]
    assert s["groups"] == 5 and s["groups_processed"] == 1 and "fail" not in s["qc_verdicts"]
    assert s["not_applicable"] == {
        "groups": 4,
        "by_reason": {"no_scans": 1, "no_xas_channel": 3},
        "no_xas_channel_by_reader": {"mca_v1": 1, "two_column_v1": 1, "xes_tab_v1": 1},
    }
    text = "\n".join(s["lines"])
    assert "3 groups: no ISAAC processing protocol applies" in text and "mca_v1 1, two_column_v1 1, xes_tab_v1 1" in text
    assert "1 groups: no scans, nothing to process" in text


def test_a_real_qc_failure_is_still_a_fail(tmp_path):
    """The boundary is the code's detection, not "anything that went wrong": a readable XAS
    scan that is too short is still judged and still fails."""
    pytest.importorskip("numpy")
    pytest.importorskip("larch")
    import numpy as np

    from test_local_import_processing import fluo_scan, make_case, spec_file

    short = np.arange(4900.0, 4905.0, 0.5)
    bdir_, root, bundle = make_case(tmp_path, [("01_SYN_short", [spec_file(fluo_scan(1, e=short))], {"sample_name": "ZZ1"})])
    (r,) = _isaac(RUN.process_bundle(bdir_, source_root=root, bundle=bundle)).values()
    assert "applicability" not in r and r["qc"]["verdict"] == "fail"


def _one(tmp_path, scans, stem="01_SYN_case"):
    pytest.importorskip("numpy")
    pytest.importorskip("larch")
    from test_local_import_processing import make_case

    bdir_, root, bundle = make_case(tmp_path, [(stem, scans, {"sample_name": "ZZ1"})])
    (r,) = _isaac(RUN.process_bundle(bdir_, source_root=root, bundle=bundle, created_utc="2026-10-28T00:00:00Z")).values()
    return r


def _trans(seed, *, dead_i1=False, dead_i0=False):
    import numpy as np

    from test_local_import_processing import E0, GRID, mu_edge

    rng = np.random.default_rng(seed)
    i0 = np.full(GRID.size, 1e5)
    i1 = i0 * np.exp(-(mu_edge(GRID, E0) + rng.normal(0, 0.002, GRID.size)))
    return {"energy": GRID, "I0": np.zeros(GRID.size) if dead_i0 else i0, "I1": np.zeros(GRID.size) if dead_i1 else i1}


def _motor_scan(seed):
    """A motor (alignment) scan: the scanned axis is a position, and ``Epoch`` is a monotonic
    clock that happens to lie inside the energy value range."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n = 40
    return {"m1vert": np.linspace(-6.3, -2.3, n), "Epoch": 1000.0 + 2.0 * np.arange(n),
            "I0": np.full(n, 1e5) + rng.normal(0, 10, n), "I1": np.full(n, 5e4) + rng.normal(0, 10, n)}


@pytest.mark.parametrize("case", ["dead_I1", "dead_I0", "beam_lost_60pct"])
def test_a_present_but_dead_detector_is_a_qc_fail_never_not_applicable(tmp_path, case):
    pytest.importorskip("numpy", reason="needs the optional `processing` extra")
    pytest.importorskip("larch", reason="needs the optional `processing` extra")
    import numpy as np

    from test_local_import_processing import fluo_scan, spec_file

    if case == "beam_lost_60pct":
        cols = fluo_scan(1)
        v = np.array(cols["vortDT"])
        v[: int(0.6 * v.size)] = 0
        cols["vortDT"] = v
    else:
        cols = _trans(1, dead_i1=case == "dead_I1", dead_i0=case == "dead_I0")
    r = _one(tmp_path, [spec_file(cols)])
    assert "applicability" not in r and r["qc"]["verdict"] == "fail"
    assert r["failure"]["code"] == "signal_channel_dead"


def test_names_that_say_time_are_never_the_energy_axis():
    from isaac_api.local_import.processing.channels import names_time

    assert all(names_time(x) for x in ("Epoch", "epoch", "Seconds", "Seconds#2", "sec", "TIME", "count_time", "timestamp", "Clock"))
    assert not any(names_time(x) for x in ("energy", "Achieved Energy", "absev", "xes0", "col1", "I0", "mono", "SEC2X"))


def test_a_motor_scan_whose_epoch_looks_like_energy_forms_no_channel(tmp_path):
    from test_local_import_processing import spec_file

    r = _one(tmp_path, [spec_file(_motor_scan(1)), spec_file(_motor_scan(2))])
    assert r["applicability"]["reason_code"] == "no_xas_channel" and "verdict" not in r["qc"]
    assert r["channel_choice"]["energy"] is None


def test_a_group_whose_first_scan_lacks_the_channel_is_processed_from_the_scans_that_have_it(tmp_path):
    from test_local_import_processing import fluo_scan, spec_file

    r = _one(tmp_path, [spec_file(_motor_scan(1)), spec_file(fluo_scan(2)), spec_file(fluo_scan(3))])
    assert "applicability" not in r and r["qc"]["verdict"] in ("pass", "warn")
    assert r["channel_choice"]["energy"] == "energy" and r["channel_choice"]["basis"]["chosen_from_scan_position"] == 1
    assert "channel_from_a_later_scan" in r["review_flags"]
    first, *rest = r["inputs"]
    assert first["used"] is False and first["skip_reason"] == "scan_lacks_chosen_columns"
    assert all(i["used"] for i in rest) and r["qc"]["metrics"]["scans_used"] == 2
    # the scientist is told most of a group may have been left out: a WARN reason, never a pass
    assert r["qc"]["verdict"] == "warn" and "scans_skipped_lacking_chosen_columns" in r["qc"]["reasons"]
    m = r["qc"]["metrics"]
    assert (m["scans_readable"], m["scans_skipped_lacking_chosen_columns"]) == (3, 1)


def test_a_group_with_no_skipped_scan_carries_no_skip_metrics(tmp_path):
    from test_local_import_processing import fluo_scan, spec_file

    r = _one(tmp_path, [spec_file(fluo_scan(2)), spec_file(fluo_scan(3))])
    assert "scans_skipped_lacking_chosen_columns" not in r["qc"]["metrics"] and "scans_skipped_lacking_chosen_columns" not in r["qc"]["reasons"]


def test_a_dead_i0_on_a_scan_with_no_energy_axis_is_not_an_xas_scan_so_not_a_fail(tmp_path):
    """Deadness is judged only where a spectrum could exist: without an energy axis the scan is
    not an XAS scan, so a dead I0 on it does not make a QC fail."""
    pytest.importorskip("numpy", reason="needs the optional `processing` extra")
    pytest.importorskip("larch", reason="needs the optional `processing` extra")
    import numpy as np

    from test_local_import_processing import spec_file

    cols = _motor_scan(1)
    cols.pop("Epoch")
    cols["I0"] = np.zeros(cols["I1"].size)
    r = _one(tmp_path, [spec_file(cols)])
    assert r["applicability"]["reason_code"] == "no_xas_channel" and r["failure"] is None


# --- the bundle contract: stored, validated, never decided ----------------------------------------------


def _na_result(group_id: str, run: dict, code: str = B.NA_NO_XAS_CHANNEL) -> dict:
    res = RUN._base({"group_id": group_id}, "isaac_protocol")
    if code == B.NA_NO_XAS_CHANNEL:
        res["inputs"] = [{"source_id": run["scans"][0]["source_id"], "scan": 1, "channel": None, "used": False, "format": "delimited_columns"}]
        res["channel_choice"] = {"energy": "xes0", "mode": None, "signal_columns": [], "i0": None}
    states = {"readers": [{"source_type": "generic:xes_tab_v1", "reader_id": "xes_tab_reader_v1", "profile": "xes_tab_v1"}]}
    return RUN._not_applicable(res, code, "no_signal_channel_found", states)


def _group(group_id: str, run: dict) -> dict:
    return {"group_id": group_id, "experiment_key": "exp", "member_run_keys": [run["run_key"]],
            "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
            "split_reasons": [], "status": "proposed", "questions": []}


@pytest.fixture()
def na_bundle(bdir):
    b = M.load(bdir)
    b["record_groups"].append(_group("g1", b["runs"][0]))
    b["processing_results"].append(_na_result("g1", b["runs"][0]))
    M.save_bundle(bdir, b)
    return bdir


def _rid(bdir):
    return B.processing_id(M.load(bdir)["processing_results"][0])


def test_a_not_applicable_result_is_stored_and_validates(na_bundle):
    b = M.load(na_bundle)
    assert B.validate_bundle(b) == []
    assert B.processing_not_applicable(b["processing_results"][0])
    assert b["format_version"] == B.FORMAT_VERSION  # no format bump: the field is optional and additive


@pytest.mark.parametrize("decision", ["approve", "reject", "needs_changes", "defer"])
def test_no_decision_is_accepted_on_a_not_applicable_result(na_bundle, decision):
    kw = {"qc_status": "valid"} if decision == "approve" else {}
    with pytest.raises(M.MutationRefused, match="not a curve"):
        M.decide(na_bundle, target_ids=[_rid(na_bundle)], decision=decision, value=None, **kw, **BY)
    assert M.load(na_bundle)["scientist_decisions"] == []


def test_the_validator_refuses_an_approval_written_onto_a_not_applicable_result(na_bundle):
    b = M.load(na_bundle)
    b["scientist_decisions"].append(
        {"decision_id": "d-99999", "target": {"kind": "processing_result", "id": _rid(na_bundle)}, "decision": "approve",
         "value": None, "chosen_reading_index": None, "decided_utc": "2026-10-28T00:00:00Z", "method": "scientist_answer",
         "note": None, "batch_id": None, "qc_status": "valid",
         "decided_by": {"name": "SYN", "basis": "self_reported_local_user", "identity": "local_unverified", "orcid_claimed": None}}
    )
    B.apply_derivations(b)
    errs = B.validate_bundle(b)
    assert any("not_applicable" in e and "d-99999" in e for e in errs), errs


def test_the_validator_refuses_a_not_applicable_result_carrying_a_qc_verdict(na_bundle):
    b = M.load(na_bundle)
    b["processing_results"][0]["qc"]["verdict"] = "fail"
    assert any("processing_results/0" in e for e in B.validate_bundle(b))


def test_the_validator_recomputes_the_no_scans_reason_from_the_inputs(na_bundle):
    b = M.load(na_bundle)
    b["processing_results"][0]["applicability"]["reason_code"] = "no_scans"  # but an input is listed
    assert any("disagrees with its 1 listed inputs" in e for e in B.validate_bundle(b))


def test_the_validator_refuses_a_not_applicable_result_with_output_files(na_bundle):
    b = M.load(na_bundle)
    b["processing_results"][0]["outputs"]["files"] = [{"role": "merged", "relative_path": "processing/x.csv", "sha256": "0" * 64}]
    assert B.validate_bundle(b)


def test_the_validator_refuses_a_not_applicable_result_preferred_for_record(na_bundle):
    b = M.load(na_bundle)
    b["processing_results"][0]["preferred_for_record"] = True
    assert any("preferred_for_record" in e for e in B.validate_bundle(b))


@pytest.mark.parametrize("forge", ["channel_formed", "channel_choice_absent", "no_scan_read", "scan_marked_used"])
def test_a_forged_no_xas_channel_is_refused_against_the_results_own_record(bdir, forge):
    b = M.load(bdir)
    b["record_groups"].append(_group("g1", b["runs"][0]))
    r = _na_result("g1", b["runs"][0])
    if forge == "channel_formed":
        r["channel_choice"] = {"energy": "energy", "mode": "fluorescence", "signal_columns": ["vortDT"], "i0": "I0"}
    elif forge == "channel_choice_absent":
        r.pop("channel_choice")
    elif forge == "no_scan_read":
        r["inputs"][0]["skip_reason"] = "source_file_not_found"
    else:
        r["inputs"][0]["used"] = True
    b["processing_results"].append(r)
    B.apply_derivations(b)
    assert any("says no_xas_channel" in e for e in B.validate_bundle(b))


# --- downstream: summary.md, questions, records ----------------------------------------------------------


def test_summary_md_reports_not_applicable_groups_apart_and_never_as_a_fail(na_bundle):
    text = (na_bundle / "summary.md").read_text()
    assert "Processing: 1 groups: no ISAAC processing protocol applies" in text and "xes_tab_v1 1" in text
    assert "QC none" in text and "fail" not in text.split("## Counts")[1].split("##")[0].lower()


def test_questions_never_ask_to_approve_a_not_applicable_result(na_bundle, capsys):
    b = M.load(na_bundle)
    mfo = Q.minimum_answers_for_one_group(Q.consolidate(b), b)
    assert mfo["group_id"] == "g1" and mfo["plus_decisions"] == ["confirm the group"]
    assert B.NO_PROTOCOL_COVERS in mfo["blocked"] and mfo["groups_without_an_applicable_processing_protocol"] == 1
    assert cli.main(["bundle", "questions", str(na_bundle), "--limit", "1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "approve its processing result" not in json.dumps(out["minimum_for_one_group"])


def test_the_nearest_group_offered_is_one_processing_can_complete(na_bundle):
    b = M.load(na_bundle)
    b["record_groups"].append(_group("g2", b["runs"][1]))
    ok = copy.deepcopy(_na_result("g2", b["runs"][1]))
    ok.pop("applicability")
    ok.update(result_id="p-ok", review_flags=[], qc={"metrics": {}, "verdict": "warn", "reasons": []})
    # an approvable result has a curve: one with no output file is refused by `decide --decision approve`
    spec = na_bundle / "processing" / "g2" / "normalized.csv"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# synthetic\nenergy_eV,norm\n" + "\n".join(f"{1000 + 5 * i},{i / 20:.3f}" for i in range(21)) + "\n")
    ok["outputs"] = {"files": [{"role": "normalized", "relative_path": "processing/g2/normalized.csv",
                                "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}],
                     "e0_eV": 1050.0, "edge_step": 1.0, "points": 21}
    b["processing_results"].append(ok)
    M.save_bundle(na_bundle, b)
    b = M.load(na_bundle)
    mfo = Q.minimum_answers_for_one_group(Q.consolidate(b), b)
    assert mfo["group_id"] == "g2" and mfo["plus_decisions"] == ["confirm the group", "approve its processing result"]
    assert "blocked" not in mfo


def test_a_not_applicable_group_cannot_become_a_record_and_says_why(na_bundle, tmp_path):
    b = M.load(na_bundle)
    M.decide(na_bundle, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(na_bundle, target_ids=[_cand(b, "sample.material.name", "run-001")["candidate_id"]], decision="correct", value="ZZ1 synthetic", **BY)
    M.decide(na_bundle, target_ids=[_miss(b, "system.domain", None)], decision="correct", value="experimental", **BY)
    built = R.build_records(na_bundle)
    (d,) = built["drafts"]
    assert d["complete"] is False and B.NO_PROTOCOL_COVERS in d["blocked"]
    assert "measurement.series" in d["missing_required"]
    comp = json.loads((na_bundle / "drafts" / "g1.composition.json").read_text())
    assert comp["processing"]["used"] is None and comp["processing"]["not_applicable"]["reason_code"] == "no_xas_channel"
    assert any(m.get("blocked") == B.NO_PROTOCOL_COVERS for m in comp["missing_required"] if m["path"] == "measurement.series")
    v = R.validate_records(na_bundle, run_portal=_portal("publish"))
    assert v["verdicts"] == {"g1": "incomplete"}
    report = json.loads((na_bundle / "validation" / "g1.json").read_text())
    assert B.NO_PROTOCOL_COVERS in report["processing_blocked"]
    assert any(line.startswith("Processing: no ISAAC processing protocol covers") for line in report["plain_summary"])
    assert R.export_records(na_bundle, tmp_path / "records", run_portal=_portal("publish"))["exported"] == []


def test_an_older_rejected_result_does_not_make_a_now_not_applicable_group_approvable(bdir):
    """Re-running ``process`` keeps a decided older result (here a rejected ``fail``) beside the
    new not-applicable one. The LATEST decides: nothing approvable is offered, nothing deleted."""
    b = M.load(bdir)
    b["record_groups"].append(_group("g1", b["runs"][0]))
    old = _na_result("g1", b["runs"][0])
    old.pop("applicability")
    old.update(result_id="p-old", qc={"metrics": {}, "verdict": "fail", "reasons": ["no_channel"]}, failure={"code": "no_channel", "detail": ""})
    b["processing_results"].append(old)
    M.save_bundle(bdir, b)
    M.decide(bdir, target_ids=["p-old"], decision="reject", value=None, **BY)
    b = M.load(bdir)
    b["processing_results"].append(_na_result("g1", b["runs"][0]))
    M.save_bundle(bdir, b)
    b = M.load(bdir)
    assert [r["result_id"] for r in b["processing_results"]][0] == "p-old"  # kept
    mfo = Q.minimum_answers_for_one_group(Q.consolidate(b), b)
    assert mfo["plus_decisions"] == ["confirm the group"] and B.NO_PROTOCOL_COVERS in mfo["blocked"]
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    (d,) = R.build_records(bdir)["drafts"]
    assert B.NO_PROTOCOL_COVERS in d["blocked"]


def test_a_group_with_an_approved_curve_is_never_blocked_by_a_later_not_applicable_run(bdir):
    b = M.load(bdir)
    b["record_groups"].append(_group("g1", b["runs"][0]))
    ok = _na_result("g1", b["runs"][0])
    ok.pop("applicability")
    ok.update(result_id="p-ok", qc={"metrics": {}, "verdict": "pass", "reasons": []})
    # a curve has an output file (`decide` refuses to approve a result without one)
    (bdir / "processing").mkdir(exist_ok=True)
    spec = bdir / "processing" / "SYN_ok_norm.txt"
    spec.write_text("# SYNTHETIC\n7000 0.0\n7010 1.0\n")
    import hashlib

    ok["outputs"] = {**ok.get("outputs", {}), "files": [{"role": "normalized_spectrum", "relative_path": "processing/SYN_ok_norm.txt",
                                                      "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}]}
    b["processing_results"].append(ok)
    M.save_bundle(bdir, b)
    M.decide(bdir, target_ids=["p-ok"], decision="approve", value=None, qc_status="valid", **BY)
    b = M.load(bdir)
    b["processing_results"].append(_na_result("g1", b["runs"][0]))
    M.save_bundle(bdir, b)
    b = M.load(bdir)
    assert B.processing_blocked_groups(b) == {}
    mfo = Q.minimum_answers_for_one_group(Q.consolidate(b), b)
    assert "blocked" not in mfo and "groups_without_an_applicable_processing_protocol" not in mfo
