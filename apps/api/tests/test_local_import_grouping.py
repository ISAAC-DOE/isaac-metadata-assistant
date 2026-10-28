"""LOCAL-P: record grouping (``local_import.grouping``) — stdlib only, no numpy.

One ISAAC record = one sample + technique + set of conditions. Repeats at the same
condition merge; ANY differing, conflicting or unknown-vs-known condition splits (with a
question when ambiguous); reference/alignment acquisitions get their own groups.

DATA BOUNDARY: synthetic bundles built here, plus the committed synthetic fixture corpus.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from isaac_api.local_import import grouping as G


def _cand(cid, run_id, key, value=None, literals=(), state="needs_review", evidence=()):
    return {
        "candidate_id": cid,
        "run_id": run_id,
        "statement_key": key,
        "value": value,
        "observed_literals": list(literals),
        "extracted_state": state,
        "value_state": state,
        "evidence": list(evidence),
    }


def _bundle(specs, label="SYNTHETIC_beamtime"):
    """specs: list of dicts {stem, conds: {key: value | ("lit", text) | ("conflict", [a, b])}, ...}."""
    runs, cands, sources = [], [], []
    n = 0
    for i, spec in enumerate(specs, start=1):
        rid = f"run-{i:03d}"
        acq = f"src-{i:04d}"
        sources.append({"source_id": acq, "relative_path": spec["stem"], "classification": {"source_type": spec.get("source_type", "spec_acquisition"), "confidence": "content", "classifier_id": "syn", "reason": "syn"}})
        ids = []
        for key, val in spec.get("conds", {}).items():
            n += 1
            cid = f"cand-{n:04d}"
            if isinstance(val, tuple) and val[0] == "lit":
                cands.append(_cand(cid, rid, key, None, [val[1]]))
            elif isinstance(val, tuple) and val[0] == "conflict":
                cands.append(_cand(cid, rid, key, None, val[1], state="conflicting"))
            elif isinstance(val, tuple) and val[0] == "tokens":
                ev = [{"source_id": src, "literal_value": t} for src, t in val[1]]
                cands.append(_cand(cid, rid, key, None, [t for _, t in val[1]], state="unmapped", evidence=[{"source_id": acq if s == "ACQ" else s, "literal_value": t} for s, t in val[1]]))
            else:
                cands.append(_cand(cid, rid, key, val, [str(val)]))
            ids.append(cid)
        scans = spec.get("scans", 2)
        runs.append(
            {
                "run_id": rid,
                "run_key": f"{spec['stem']}@sha256:{i:064x}",
                "stem": spec["stem"],
                "label": spec["stem"],
                "source_type": spec.get("source_type", "spec_acquisition"),
                "acquisition_source_id": acq,
                "scan_count": scans,
                "scans": [{"source_id": f"{acq}-s{j}", "relative_path": f"{spec['stem']}_dir/{spec['stem']}_{j:03d}.dat", "scan_index": j} for j in range(1, scans + 1)],
                "candidate_ids": ids,
                "legacy_number_shared": spec.get("dup", False),
                "shares_legacy_number_with": [],
            }
        )
    return {"bundle_id": "syn", "source_root": {"label": label}, "runs": runs, "candidates": cands, "sources": sources, "unread_files": []}


BASE = {"sample_name": ("lit", "ZZ9"), "potential_magnitude": 0.4, "electrolyte_or_medium": ("lit", "acid"), "acquisition_method": ("lit", "Zz_XAS.mac")}


def _groups(specs):
    return G.propose_record_groups(_bundle(specs))


def test_repeats_at_the_same_condition_merge_and_ids_are_stable():
    specs = [{"stem": "01_SYN_a", "conds": dict(BASE)}, {"stem": "02_SYN_b", "conds": dict(BASE)}]
    groups = _groups(specs)
    assert len(groups) == 1
    g = groups[0]
    assert g["member_run_ids"] == ["run-001", "run-002"]
    assert g["status"] == "proposed" and "multi_run_group" in g["flags"]
    assert g["basis"]["conditions"]["potential_magnitude"]["value"] == 0.4
    assert len(g["basis"]["conditions"]["potential_magnitude"]["candidate_ids"]) == 2
    assert g["group_id"].startswith("rg-") and g["group_id"] == _groups(specs)[0]["group_id"]
    assert g["experiment_key"] == "experiment:SYNTHETIC_beamtime"
    assert set(g["basis"]) >= {"sample", "technique", "environment", "conditions"}


def test_any_differing_condition_splits_with_reasons():
    other = dict(BASE, potential_magnitude=0.8)
    groups = _groups([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": other}])
    assert len(groups) == 2
    reason = groups[0]["split_reasons"][0]
    assert reason["code"] == "conditions_differ" and reason["other_group_id"] == groups[1]["group_id"]
    assert reason["differences"] == [
        {"condition": "potential_magnitude", "key_class": "condition", "category": "conditions", "kind": "differs", "this": 0.4, "other": 0.8}
    ]
    assert not groups[0]["questions"]


def test_differing_literal_condition_splits():
    other = dict(BASE, electrolyte_or_medium=("lit", "base"))
    assert len(_groups([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": other}])) == 2


def test_unknown_vs_known_condition_splits_and_asks():
    known = dict(BASE, cycling_state=("lit", "after500Cycling"))
    groups = _groups([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": known}])
    assert len(groups) == 2
    d = groups[0]["split_reasons"][0]["differences"][0]
    assert d["kind"] == "unknown_vs_known" and d["condition"] == "cycling_state"
    q = groups[0]["questions"][0]
    assert q["code"] == "unknown_vs_known_condition" and q["conditions"] == ["cycling_state"]
    assert groups[1]["questions"][0]["question_id"] == q["question_id"]


def test_conflicting_condition_is_never_merged():
    conflicted = dict(BASE, filter=("conflict", ["10", "20"]))
    groups = _groups([{"stem": "a", "conds": conflicted}, {"stem": "b", "conds": conflicted}])
    assert len(groups) == 2
    for g in groups:
        assert g["split_reasons"][0]["code"] == "conflicting_condition"
        assert g["questions"][0]["code"] == "resolve_conflicting_condition"
        assert g["basis"]["conditions"]["filter"]["kind"] == "conflicting"
        assert g["basis"]["conditions"]["filter"]["value"] is None


def test_no_sample_identity_is_not_merged():
    nosample = {k: v for k, v in BASE.items() if k != "sample_name"}
    groups = _groups([{"stem": "a", "conds": nosample}, {"stem": "b", "conds": nosample}])
    assert len(groups) == 2
    assert all(g["questions"][0]["code"] == "state_sample_identity" for g in groups)


def test_reference_and_alignment_acquisitions_get_their_own_groups():
    specs = [
        {"stem": "01_SYN_sample", "conds": dict(BASE)},
        {"stem": "02_SYN_Zz_foil", "conds": dict(BASE)},
        {"stem": "03_SYN_calib_x", "conds": dict(BASE, sample_name=("lit", "ZZfoil"))},
        {"stem": "SYN_align_scan_001", "conds": dict(BASE)},
        {"stem": "04_SYN_rough", "conds": dict(BASE, potential_magnitude=0.1)},
        {"stem": "alignment", "conds": dict(BASE, potential_magnitude=0.2), "source_type": "alignment"},
        {"stem": "05_SYN_pellet", "conds": dict(BASE, sample_name=("lit", "ZZpellet")), "source_type": "standard_or_reference"},
    ]
    groups = _groups(specs)
    roles = {g["member_run_ids"][0]: (g["role"], g["role_basis"]["basis"]) for g in groups}
    assert roles["run-001"] == ("sample", "default_sample")
    assert roles["run-002"][0] == "reference" and roles["run-002"][1] == "name_token"
    assert roles["run-003"][0] == "reference"
    assert roles["run-004"][0] == "alignment" and roles["run-005"][0] == "alignment"
    assert roles["run-006"] == ("alignment", "engine_classifier")
    assert roles["run-007"] == ("reference", "engine_classifier")
    sample = next(g for g in groups if g["role"] == "sample")
    assert sample["member_run_ids"] == ["run-001"]  # never merged with a reference


def test_duplicate_legacy_numbers_share_a_group_only_when_every_condition_matches():
    same = _groups([{"stem": "05_SYN", "conds": dict(BASE), "dup": True}, {"stem": "05_SYN_x", "conds": dict(BASE), "dup": True}])
    assert len(same) == 1 and "duplicate_legacy_number" in same[0]["flags"]
    diff = _groups([{"stem": "05_SYN", "conds": dict(BASE), "dup": True}, {"stem": "05_SYN_x", "conds": dict(BASE, cycling_state=("lit", "x")), "dup": True}])
    assert len(diff) == 2 and all("duplicate_legacy_number" in g["flags"] for g in diff)


def test_repeat_marker_is_not_a_condition_and_is_flagged():
    groups = _groups([{"stem": "a", "conds": dict(BASE)}, {"stem": "a_again", "conds": dict(BASE, repeat_marker=("lit", "again"))}])
    assert len(groups) == 1 and "repeat_marker_present" in groups[0]["flags"]


def test_an_unseen_statement_key_is_a_condition_fail_closed():
    groups = _groups([{"stem": "a", "conds": dict(BASE, brand_new_concept=("lit", "x"))}, {"stem": "b", "conds": dict(BASE, brand_new_concept=("lit", "y"))}])
    assert len(groups) == 2


def test_unknown_tokens_count_only_from_the_acquisition_file_name():
    scan_only = dict(BASE, unknown_token=("tokens", [("scanfile-1", "001")]))
    scan_only_b = dict(BASE, unknown_token=("tokens", [("scanfile-2", "002")]))
    assert len(_groups([{"stem": "a", "conds": scan_only}, {"stem": "b", "conds": scan_only_b}])) == 1
    acq_a = dict(BASE, unknown_token=("tokens", [("ACQ", "asIs")]))
    acq_b = dict(BASE, unknown_token=("tokens", [("ACQ", "newGrid")]))
    assert len(_groups([{"stem": "a", "conds": acq_a}, {"stem": "b", "conds": acq_b}])) == 2


def test_runs_without_scans_are_their_own_group():
    groups = _groups([{"stem": "a", "conds": dict(BASE), "scans": 0}, {"stem": "b", "conds": dict(BASE)}])
    assert len(groups) == 2 and {"code": "no_scans"} in groups[0]["split_reasons"]


def test_deterministic_order_follows_the_bundle():
    specs = [{"stem": f"{i:02d}_SYN", "conds": dict(BASE, potential_magnitude=i / 10)} for i in range(5)]
    groups = _groups(specs)
    assert [g["member_run_ids"][0] for g in groups] == [f"run-{i:03d}" for i in range(1, 6)]
    assert len({g["group_id"] for g in groups}) == 5


def test_unread_numbered_scans_fallback_skips_binary_twins():
    b = _bundle([])
    b["sources"] = [
        {"source_id": "u1", "relative_path": "SYN_x_A.001", "classification": {"confidence": "content"}},
        {"source_id": "u2", "relative_path": "SYN_x_A.002", "classification": {"confidence": "content"}},
        {"source_id": "u3", "relative_path": "SYN_Zz_foil_A.001", "classification": {"confidence": "content"}},
        {"source_id": "u4", "relative_path": "binary/SYN_x.001", "classification": {"confidence": "unknown"}},
        {"source_id": "u5", "relative_path": "SYN_x.rgn", "classification": {"confidence": "content"}},
    ]
    b["unread_files"] = [{"source_id": s["source_id"], "relative_path": s["relative_path"]} for s in b["sources"]]
    groups = G.propose_unread_acquisition_groups(b)
    assert [g["stem"] for g in groups] == ["SYN_Zz_foil_A", "SYN_x_A"]
    assert [s["scan_index"] for s in groups[1]["member_scans"]] == [1, 2]
    assert groups[0]["role"] == "reference" and groups[1]["role"] == "sample"
    assert all(g["member_run_keys"] == [] and g["questions"] for g in groups)


def test_generic_run_adapter_is_duck_typed():
    runs = [
        SimpleNamespace(stem="SYN_y_A", scans=[SimpleNamespace(relative_path="SYN_y_A.001", scan_index=1), {"path": "SYN_y_A.002"}]),
        {"name": "SYN_align_A", "scans": [{"relative_path": "SYN_align_A.001"}]},
    ]
    groups = G.groups_from_generic_runs(runs, experiment_key="experiment:SYN", sources_by_path={"SYN_y_A.001": "src-9"})
    assert [g["group_kind"] for g in groups] == ["generic_run", "generic_run"]
    assert groups[0]["member_scans"][0] == {"source_id": "src-9", "relative_path": "SYN_y_A.001", "scan_index": 1}
    assert groups[0]["member_scans"][1]["scan_index"] == 2
    assert groups[1]["role"] == "alignment"


def test_committed_fixture_corpus_groups_deterministically():
    import isaac_api.historical_import as hist
    from isaac_api.local_import import bundle as B

    ev: dict = {}
    reading, cands = hist.read_local_archive(hist.archive_root_for("bl15_synthetic_semantics_corpus"), source_id="local-source", evidence_sink=ev)
    bundle = B.build_bundle(reading, cands, evidence_by_source=ev, source_kind="folder", created_utc="2026-10-28T00:00:00Z")
    groups = G.propose_record_groups(bundle)
    assert sum(len(g["member_run_keys"]) for g in groups) == len(bundle["runs"])
    assert len({g["group_id"] for g in groups}) == len(groups)
    keys = {r["run_key"] for r in bundle["runs"]}
    assert all(k in keys for g in groups for k in g["member_run_keys"])
    dup = [g for g in groups if "duplicate_legacy_number" in g["flags"]]
    assert dup and all(len(g["member_run_keys"]) == 1 for g in dup)  # 05_ twins differ in cycling
    assert G.propose_record_groups(bundle) == groups


def test_grouping_imports_no_numpy():
    code = "import sys; import isaac_api.local_import.grouping, isaac_api.local_import.processing; print('numpy' in sys.modules, 'larch' in sys.modules)"
    root = Path(__file__).resolve().parents[3]
    env = {"PYTHONPATH": f"{root / 'apps' / 'api'}:{root / 'src'}", "PATH": ""}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env)
    assert out.stdout.strip() == "False False"


# --- LOCAL-P2: three-way key classes, merge candidates, engine misreadings -------------------


def _propose(specs, mutate=None):
    b = _bundle(specs)
    if mutate:
        mutate(b)
    return G.propose(b)


def test_every_key_has_exactly_one_class_and_unseen_keys_are_unknown():
    assert not set(G.CONDITION_KEYS) & set(G.BOOKKEEPING_KEYS)
    assert not set(G.UNKNOWN_KEYS) & (set(G.CONDITION_KEYS) | set(G.BOOKKEEPING_KEYS))
    assert G.classify_key("potential_magnitude") == "condition"
    assert G.classify_key("repeat_marker") == "bookkeeping"
    assert G.classify_key("new_spot") == "unknown" and G.classify_key("step_number") == "unknown"
    assert G.classify_key("brand_new_concept") == "unknown"
    assert all(G.CONDITION_KEYS.values()) and all(G.BOOKKEEPING_KEYS.values()) and all(G.UNKNOWN_KEYS.values())


def test_bookkeeping_only_differences_make_one_group_and_ask_to_confirm_repeats():
    a = dict(BASE, legacy_run_or_file_number=("lit", "04"))
    b = dict(BASE, legacy_run_or_file_number=("lit", "05"), repeat_marker=("lit", "again"))
    p = _propose([{"stem": "04_01_SYN", "conds": a}, {"stem": "05_01_SYN_again", "conds": b}])
    (g,) = p["record_groups"]
    assert g["status"] == "proposed" and len(g["member_run_keys"]) == 2
    q = next(q for q in g["questions"] if q["code"] == "confirm_repeats_merge")
    assert [d["legacy_run_or_file_number"] for d in q["differing_bookkeeping"]] == [["04"], ["05"]]
    assert q["differing_bookkeeping"][1]["repeat_marker"] == ["again"]
    assert p["merge_candidates"] == []


def test_an_unknown_key_difference_splits_and_offers_one_merge_candidate():
    p = _propose([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": dict(BASE, new_spot=("lit", "newSpot"))}])
    g1, g2 = p["record_groups"]
    (mc,) = p["merge_candidates"]
    assert mc["group_ids"] == [g1["group_id"], g2["group_id"]] and mc["status"] == "proposed"
    (reason,) = mc["reasons"]
    assert reason["code"] == "unknown_key_differs" and reason["key"] == "new_spot"
    assert reason["values_by_group"] == {g1["group_id"]: None, g2["group_id"]: "newspot"}
    assert "new spot" in reason["why_unknown"]
    assert g1["merge_candidate_ids"] == [mc["merge_candidate_id"]] == g2["merge_candidate_ids"]
    assert mc["question"]["code"] == "merge_candidate" and mc["question"] in g1["questions"]
    assert g2["basis"]["unclassified"]["new_spot"]["key_class"] == "unknown"
    assert mc["merge_candidate_id"] == _propose([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": dict(BASE, new_spot=("lit", "newSpot"))}])["merge_candidates"][0]["merge_candidate_id"]


def test_a_condition_difference_is_never_a_merge_candidate():
    p = _propose([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": dict(BASE, potential_magnitude=0.9)}])
    assert len(p["record_groups"]) == 2 and p["merge_candidates"] == []


def test_a_real_condition_conflict_stays_a_hard_split():
    conflicted = dict(BASE, filter=("conflict", ["10", "20"]))
    p = _propose([{"stem": "a", "conds": conflicted}, {"stem": "b", "conds": conflicted}])
    assert len(p["record_groups"]) == 2 and p["merge_candidates"] == []


def _scan_index_conflict(bundle):
    """Shape measured on a real beamtime: each scan file's `_00N` read as the sample number."""
    for run in bundle["runs"]:
        cid = f"cand-scanidx-{run['run_id']}"
        ev = [{"source_id": s["source_id"], "locator": "filename token 6", "literal_value": str(s["scan_index"]), "relation": "contradicts"} for s in run["scans"]]
        bundle["candidates"].append(_cand(cid, run["run_id"], "sample_or_electrode_number", None, [e["literal_value"] for e in ev], state="conflicting", evidence=ev))
        run["candidate_ids"].append(cid)


def test_scan_index_tokens_read_as_sample_number_still_form_a_proposed_group():
    p = _propose([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": dict(BASE)}], mutate=_scan_index_conflict)
    (g,) = p["record_groups"]
    assert g["status"] == "proposed" and len(g["member_run_keys"]) == 2
    assert "merged_despite_engine_reading" in g["flags"] and "blocked_by_engine_reading" not in g["flags"]
    despite = g["merged_despite_engine_reading"]
    assert [d["kind"] for d in despite] == ["scan_index_token_read_as_value"] * 2
    assert [e["scan_file_index"] for e in despite[0]["evidence"]] == [1, 2]
    q = next(q for q in g["questions"] if q["code"] == "confirm_repeats_merge")
    assert "scan-file numbers (_001, _002) as a sample number" in q["text"]
    assert p["merge_candidates"] == [] and len(p["engine_reading_issues"]["per_run"]) == 2


def _emission_conflict(lits):
    def mutate(b):
        for run in b["runs"]:
            cid = f"cand-em-{run['run_id']}"
            b["candidates"].append(_cand(cid, run["run_id"], "emission_energy", None, lits, state="conflicting"))
            run["candidate_ids"].append(cid)
    return mutate


def test_unit_spelling_in_the_fields_own_unit_forms_a_proposed_group():
    p = _propose([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": dict(BASE)}], mutate=_emission_conflict(["9175.4", "9175.4 eV"]))
    (g,) = p["record_groups"]
    assert g["merged_despite_engine_reading"][0]["kind"] == "same_value_different_unit_spelling"
    assert g["basis"]["conditions"]["emission_energy"]["value"] == 9175.4
    assert "with and without its unit" in next(q for q in g["questions"] if q["code"] == "confirm_repeats_merge")["text"]


def test_a_different_unit_is_never_normalised():
    for lits in (["9.1754", "9.1754 keV"], ["9175.4 eV", "9175.4 keV"]):
        p = _propose([{"stem": "a", "conds": dict(BASE)}, {"stem": "b", "conds": dict(BASE)}], mutate=_emission_conflict(lits))
        assert len(p["record_groups"]) == 2 and not p["engine_reading_issues"]["per_run"]
    assert G._unit_spelling_misread({"statement_key": "potential_magnitude", "observed_literals": ["0.4", "0.4 V"]}) is None


def test_a_scan_index_conflict_that_does_not_match_the_index_stays_a_conflict():
    def mutate(b):
        _scan_index_conflict(b)
        b["candidates"][-1]["evidence"][0]["literal_value"] = "7"
    p = _propose([{"stem": "a", "conds": dict(BASE)}], mutate=mutate)
    assert not p["engine_reading_issues"]["per_run"]


def test_unit_spelling_and_auxiliary_macro_conflicts_are_engine_readings():
    def mutate(b):
        for run in b["runs"]:
            for key, lits in (("emission_energy", ["9175.4", "9175.4 eV"]), ("acquisition_method", ["Zz_XAS.mac", "syn_helper.mac"])):
                cid = f"cand-{key}-{run['run_id']}"
                b["candidates"].append(_cand(cid, run["run_id"], key, None, lits, state="conflicting"))
                run["candidate_ids"].append(cid)
    base = {k: v for k, v in BASE.items() if k != "acquisition_method"}
    p = _propose([{"stem": "a", "conds": base}, {"stem": "b", "conds": base}], mutate=mutate)
    codes = sorted(i["code"] for i in p["record_groups"][0]["engine_reading_issues"])
    assert codes == ["auxiliary_macro_read_as_method", "same_value_different_unit_spelling"]
    assert p["record_groups"][0]["basis"]["conditions"]["emission_energy"]["value"] == 9175.4
    assert p["record_groups"][0]["basis"]["technique"]["acquisition_method"]["value"] == "zz_xas.mac"
    assert len(p["merge_candidates"]) == 1  # the helper-macro reading still blocks: candidate only
    assert p["record_groups"][0]["flags"].count("blocked_by_engine_reading") == 1
    # a real difference in number is not a unit spelling
    assert G._unit_spelling_misread({"statement_key": "emission_energy", "observed_literals": ["9175.4", "9176.1 eV"]}) is None


def test_sample_number_that_contradicts_sample_name_becomes_unknown_for_the_beamtime():
    specs = [
        {"stem": f"{i:02d}_{n:02d}_SYN", "conds": dict(BASE, sample_name=("lit", name), sample_or_electrode_number=("lit", f"{n:02d}"))}
        for i, (name, n) in enumerate([("A", 1), ("B", 1), ("A", 2), ("B", 2)], start=1)
    ]
    p = _propose(specs)
    (issue,) = p["engine_reading_issues"]["beamtime"]
    assert issue["code"] == "sample_number_inconsistent_with_sample_name" and issue["numbers_with_several_names"] == 2
    assert p["key_classes"]["beamtime_overrides"] == {"sample_or_electrode_number": "unknown"}
    # A/01 and A/02 now differ only in an unknown key -> merge candidate, not a hard split
    assert any(r["key"] == "sample_or_electrode_number" for mc in p["merge_candidates"] for r in mc["reasons"] if r["code"] == "unknown_key_differs")


def test_an_exported_file_read_as_a_zero_scan_run_is_offered_to_its_run():
    p = _propose([{"stem": "SYN_run_7", "conds": dict(BASE)}, {"stem": "SYN_run_7.dat", "conds": dict(BASE), "scans": 0}])
    (mc,) = p["merge_candidates"]
    assert any(r["code"] == "exported_file_read_as_acquisition" for r in mc["reasons"])
    exported = p["record_groups"][1]
    assert exported["engine_reading_issues"][0]["related_run_key"] == p["record_groups"][0]["member_run_keys"][0]


def test_unread_acquisitions_differing_only_in_counters_are_merge_candidates():
    b = _bundle([])
    names = ["17_SYN_m111mV_801_A.001", "18_SYN_m111mV_802_A.001", "19_SYN_m222mV_803_A.001", "SYN_align_701_A.001"]
    b["sources"] = [{"source_id": f"u{i}", "relative_path": n, "classification": {"confidence": "content"}} for i, n in enumerate(names)]
    b["unread_files"] = [{"source_id": s["source_id"], "relative_path": s["relative_path"]} for s in b["sources"]]
    groups = G.propose_unread_acquisition_groups(b)
    (mc,) = G.propose_unread_merge_candidates(groups)
    assert mc["reasons"][0]["stems"] == ["17_SYN_m111mV_801_A", "18_SYN_m111mV_802_A"]
    assert mc["status"] == "proposed" and all(len(g["member_scans"]) == 1 for g in groups)
