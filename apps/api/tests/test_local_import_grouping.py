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
    specs = [{"stem": "01_SYN_a", "conds": dict(BASE)}, {"stem": "02_SYN_a", "conds": dict(BASE)}]
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
    same = _groups([{"stem": "05_SYN", "conds": dict(BASE), "dup": True}, {"stem": "05_SYN", "conds": dict(BASE), "dup": True}])
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
    assert len(_groups([{"stem": "01_SYN", "conds": scan_only}, {"stem": "02_SYN", "conds": scan_only_b}])) == 1
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
    p = _propose([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": dict(BASE, new_spot=("lit", "newSpot"))}])
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
    assert mc["merge_candidate_id"] == _propose([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": dict(BASE, new_spot=("lit", "newSpot"))}])["merge_candidates"][0]["merge_candidate_id"]


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
    p = _propose([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": dict(BASE)}], mutate=_scan_index_conflict)
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
    p = _propose([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": dict(BASE)}], mutate=_emission_conflict(["9175.4", "9175.4 eV"]))
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
    p = _propose([{"stem": "01_SYN", "conds": base}, {"stem": "02_SYN", "conds": base}], mutate=mutate)
    (g,) = p["record_groups"]  # both misreadings are mechanical: ONE proposed group
    assert sorted({d["kind"] for d in g["merged_despite_engine_reading"]}) == ["auxiliary_macro_read_as_method", "same_value_different_unit_spelling"]
    assert g["basis"]["conditions"]["emission_energy"]["value"] == 9175.4
    assert g["basis"]["technique"]["acquisition_method"]["value"] == "zz_xas.mac"
    assert "helper macro" in next(q for q in g["questions"] if q["code"] == "confirm_repeats_merge")["text"]
    assert p["merge_candidates"] == []
    # a real difference in number is not a unit spelling
    assert G._unit_spelling_misread({"statement_key": "emission_energy", "observed_literals": ["9175.4", "9176.1 eV"]}) is None
    # two technique-named readings are not a helper macro: identified, blocking
    assert G._auxiliary_macro_misread({"statement_key": "acquisition_method", "observed_literals": ["Zz_XAS.mac", "Yy_XAS.mac"]})["code"] == "several_technique_macros"


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


def test_an_exported_file_joins_its_runs_group_as_context():
    b = _bundle([{"stem": "SYN_run_7", "conds": dict(BASE)}, {"stem": "SYN_run_7.dat", "conds": dict(BASE), "scans": 0}])
    p = G.propose(b)
    (g,) = p["record_groups"]
    assert g["member_run_keys"] == [r["run_key"] for r in b["runs"]] and g["context_run_keys"] == [b["runs"][1]["run_key"]]
    assert "export_kept_as_context" in g["flags"] and g["merged_despite_engine_reading"][0]["kind"] == "exported_file_read_as_acquisition"
    assert "not a measurement" in next(q for q in g["questions"] if q["code"] == "confirm_repeats_merge")["text"]
    assert p["merge_candidates"] == [] and G.condition_violations(b, p) == []


def test_an_exported_file_stating_a_different_condition_stays_a_candidate():
    p = _propose([{"stem": "SYN_run_7", "conds": dict(BASE)}, {"stem": "SYN_run_7.dat", "conds": dict(BASE, potential_magnitude=0.9), "scans": 0}])
    assert len(p["record_groups"]) == 2
    (mc,) = p["merge_candidates"]
    assert any(r["code"] == "exported_file_read_as_acquisition" for r in mc["reasons"])


def test_scan_index_misread_with_no_sample_groups_on_the_name_stem():
    nosample = {k: v for k, v in BASE.items() if k != "sample_name"}
    specs = [
        {"stem": "01_SYN_E1_x_400mV", "conds": dict(nosample)},
        {"stem": "07_SYN_E1_x_400mV_again", "conds": dict(nosample)},
        {"stem": "02_SYN_E2_x_400mV", "conds": dict(nosample)},
    ]
    b = _bundle(specs)
    _scan_index_conflict(b)
    p = G.propose(b)
    multi = [g for g in p["record_groups"] if len(g["member_run_keys"]) > 1]
    assert len(multi) == 1 and multi[0]["member_run_ids"] == ["run-001", "run-002"]
    key = multi[0]["basis"]["sample"]["sample_name_stem"]
    assert key["value"] == "syn_e1_x_400mv" and key["sample_key_basis"] == "name_stem"
    assert "file names with run counters and repeat markers removed" in next(q for q in multi[0]["questions"] if q["code"] == "confirm_repeats_merge")["text"]
    assert len(p["record_groups"]) == 2  # E2 is its own group
    assert G.name_stem_key("012_SYN_A_rep2_7") == "syn_a"  # zero-padded edge + number after a repeat marker
    assert G.name_stem_key("12_SYN_A_rep2_7") == "12_syn_a"  # a bare leading 12 may be an electrode: kept
    assert G.name_stem_key("SYN_x_12_400mV") == "syn_x_12_400mv"  # a middle number is kept
    assert G.name_stem_key("SYN_x_again_2_400mV") == "syn_x_400mv"  # the number after a repeat marker is a counter
    assert G.name_stem_key("SYN_x_12_400mV", loose=True) == "syn_x_400mv"
    assert G.condition_violations(b, p) == []


def test_a_unit_token_with_leading_zeros_is_the_same_number():
    # Measured on a real beamtime: `..._0mV` and `..._000mV` names were kept apart as different potentials.
    assert G.name_stem_key("SYN_E6_x_000mV") == G.name_stem_key("SYN_E6_x_0mV") == "syn_e6_x_0mv"
    assert G.name_stem_key("SYN_E6_x_-000mV") == "syn_e6_x_-0mv"
    # ONLY zero: a non-zero padded number is kept literally (`05V` may mean 0.5 V), and a token
    # split off a decimal has significant zeros (independent review: `0.05V` had merged with `0.5V`)
    assert G.name_stem_key("SYN_E6_x_0400mV") == "syn_e6_x_0400mv"
    assert G.name_stem_key("SYN_E6_x_05V") != G.name_stem_key("SYN_E6_x_5V")
    assert G.name_stem_key("SYN_E6_x_0.05V") != G.name_stem_key("SYN_E6_x_0.5V")
    assert G.name_stem_key("SYN_E6_x_1.0400V") != G.name_stem_key("SYN_E6_x_1.400V")
    assert G.name_stem_key("SYN_E6_x_007c") != G.name_stem_key("SYN_E6_x_7c")  # `c` may mean cycles
    # a sign after a separator is kept: -50 mV and 50 mV are different potentials
    assert G.name_stem_key("SYN_E6_x_-50mV") != G.name_stem_key("SYN_E6_x_50mV")
    assert G.name_stem_key("-50mV_SYN_E6") == "-50mv_syn_e6"
    # a hyphen between words or after a word still separates
    assert G.name_stem_key("SYN_Pt-C_x") == "syn_pt_c_x" and G.name_stem_key("SYN_E1-400mV") == "syn_e1_400mv"
    # never a conversion
    assert G.name_stem_key("SYN_E6_x_500mV") != G.name_stem_key("SYN_E6_x_0.5V")
    # the sign reaches the counter question's two other tokenisation sites too
    assert G.counter_tokens("a_b_-01") == [] and G.counter_tokens("a_b_01") == ["01"]
    assert G._differing_number_positions(["a_-1_400mV", "a_-2_400mV"]) == []
    assert G._differing_number_positions(["a_1_400mV", "a_2_400mV"]) == [2]
    nosample = {k: v for k, v in BASE.items() if k != "sample_name"}
    b = _bundle([{"stem": "SYN_E6_x_000mV", "conds": dict(nosample)}, {"stem": "SYN_E6_x_0mV", "conds": dict(nosample)}])
    _scan_index_conflict(b)
    p = G.propose(b)
    (g,) = p["record_groups"]
    assert len(g["member_run_keys"]) == 2 and G.condition_violations(b, p) == []
    b2 = _bundle([{"stem": "SYN_E6_x_0.05V", "conds": dict(nosample)}, {"stem": "SYN_E6_x_0.5V", "conds": dict(nosample)}])
    _scan_index_conflict(b2)
    assert [len(g["member_run_keys"]) for g in G.propose(b2)["record_groups"]] == [1, 1]


def test_a_middle_number_difference_is_a_merge_candidate_not_a_group():
    nosample = {k: v for k, v in BASE.items() if k != "sample_name"}
    b = _bundle([{"stem": "SYN_E1_12_400mV", "conds": dict(nosample)}, {"stem": "SYN_E1_1_400mV", "conds": dict(nosample)}])
    _scan_index_conflict(b)
    p = G.propose(b)
    assert len(p["record_groups"]) == 2 and all(len(g["member_run_keys"]) == 1 for g in p["record_groups"])
    (mc,) = p["merge_candidates"]
    (r,) = [x for x in mc["reasons"] if x["code"] == "numeric_name_token_differs"]
    assert sorted(r["values_by_group"].values()) == ["syn_e1_12_400mv", "syn_e1_1_400mv"]
    # counter positions still merge: leading index, trailing scan index, after a repeat marker
    b2 = _bundle([{"stem": "07_SYN_E1_400mV_001", "conds": dict(nosample)}, {"stem": "09_SYN_E1_400mV_again_2", "conds": dict(nosample)}])
    _scan_index_conflict(b2)
    p2 = G.propose(b2)
    assert len(p2["record_groups"]) == 1 and p2["merge_candidates"] == []


def test_name_stem_key_is_only_used_after_a_scan_index_misread():
    nosample = {k: v for k, v in BASE.items() if k != "sample_name"}
    p = _propose([{"stem": "SYN_01_x", "conds": dict(nosample)}, {"stem": "SYN_02_x", "conds": dict(nosample)}])
    assert len(p["record_groups"]) == 2  # no misread: sample stays unstated


def test_condition_violations_catches_a_tampered_group():
    b = _bundle([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": dict(BASE, potential_magnitude=0.9)}])
    p = G.propose(b)
    assert G.condition_violations(b, p) == []
    g1, g2 = p["record_groups"]
    g1["member_run_keys"] = g1["member_run_keys"] + g2["member_run_keys"]
    (v,) = G.condition_violations(b, p)
    assert v["key"] == "potential_magnitude"


def test_unread_acquisitions_differing_only_in_counters_are_merge_candidates():
    b = _bundle([])
    names = ["17_SYN_m111mV_801_A.001", "18_SYN_m111mV_802_A.001", "19_SYN_m222mV_803_A.001", "SYN_align_701_A.001"]
    b["sources"] = [{"source_id": f"u{i}", "relative_path": n, "classification": {"confidence": "content"}} for i, n in enumerate(names)]
    b["unread_files"] = [{"source_id": s["source_id"], "relative_path": s["relative_path"]} for s in b["sources"]]
    groups = G.propose_unread_acquisition_groups(b)
    (mc,) = G.propose_unread_merge_candidates(groups)
    assert mc["reasons"][0]["stems"] == ["17_SYN_m111mV_801_A", "18_SYN_m111mV_802_A"]
    assert mc["status"] == "proposed" and all(len(g["member_scans"]) == 1 for g in groups)


def _unread_bundle(names):
    b = _bundle([])
    b["sources"] = [{"source_id": f"u{i}", "relative_path": n, "classification": {"confidence": "content"}} for i, n in enumerate(names)]
    b["unread_files"] = [{"source_id": x["source_id"], "relative_path": x["relative_path"]} for x in b["sources"]]
    return b


HEAD = ["SSRL SYNTHETIC Data Collector", "Fri Jan 01 00:00:00 2099", "PTS: 10 COLS: 4", "syn.det", "SynK_SYNTHETIC.rgn", "syn beamline line", "i0 1e8 i1 1e8", "1x1 mm beam", "SYN sample description", "Weights:", "1 1", "Offsets:", "0.1 0.2"]


def test_unread_counter_names_with_agreeing_headers_become_one_proposed_group():
    b = _unread_bundle(["07_SYN_m111mV_801_A.001", "07_SYN_m111mV_801_A.002", "08_SYN_m111mV_802_A.001", "09_SYN_m222mV_803_A.001"])
    groups = G.propose_unread_acquisition_groups(b)
    cands = G.propose_unread_merge_candidates(groups)
    heads = {rel: list(HEAD) for rel in (s["relative_path"] for s in b["sources"])}
    heads["08_SYN_m111mV_802_A.001"][1] = "Sat Jan 02 11:11:11 2099"  # a date differs: bookkeeping
    heads["08_SYN_m111mV_802_A.001"][-1] = "9.9 9.9"  # offsets differ: bookkeeping
    out, remaining = G.promote_unread_by_headers(groups, cands, heads.get)
    multi = [g for g in out if len(g.get("acquisition_keys") or ()) > 1]
    assert len(multi) == 1 and remaining == []
    m = multi[0]
    assert m["stems"] == ["07_SYN_m111mV_801_A", "08_SYN_m111mV_802_A"] and len(m["member_scans"]) == 3
    assert m["basis"]["header_statements"]["value"][2] == "SynK_SYNTHETIC.rgn" and m["questions"][0]["code"] == "confirm_repeats_merge"
    assert len(out) == 2


def test_unread_header_disagreement_or_absence_keeps_a_candidate():
    b = _unread_bundle(["07_SYN_m111mV_801_A.001", "08_SYN_m111mV_802_A.001"])
    groups = G.propose_unread_acquisition_groups(b)
    cands = G.propose_unread_merge_candidates(groups)
    heads = {"07_SYN_m111mV_801_A.001": list(HEAD), "08_SYN_m111mV_802_A.001": [*HEAD[:6], "i0 5e8 i1 1e8", *HEAD[7:]]}
    out, (mc,) = G.promote_unread_by_headers(groups, cands, heads.get)
    assert len(out) == 2 and mc["reasons"][-1] == {"code": "header_statements_disagree", "statement_positions": [4]}
    out2, (mc2,) = G.promote_unread_by_headers(groups, cands, lambda rel: None)
    assert len(out2) == 2 and mc2["reasons"][-1]["code"] == "headers_unreadable_name_only_evidence"


def _middle_counter_bundle(decisions=()):
    nosample = {k: v for k, v in BASE.items() if k != "sample_name"}
    b = _bundle([
        {"stem": "SYN_XX_02_x_400mV", "conds": dict(nosample)},
        {"stem": "SYN_XX_03_x_400mV", "conds": dict(nosample)},
        {"stem": "SYN_YY_04_x_400mV", "conds": dict(nosample)},
    ])
    _scan_index_conflict(b)
    b["scientist_decisions"] = list(decisions)
    return b


DECISION = {
    "decision": "set_counter_positions",
    "target": {"kind": "experiment", "id": "experiment"},
    "positions": [3],
    "decided_by": {"name": "SYN Scientist", "basis": "self_reported_local_user", "identity": "local_unverified"},
    "decision_id": "dec-syn-cp-1",
}


def test_without_a_decision_one_experiment_question_asks_about_the_counter_position():
    p = G.propose(_middle_counter_bundle())
    assert all(len(g["member_run_keys"]) == 1 for g in p["record_groups"])
    (q,) = p["experiment_questions"]
    assert q["code"] == "set_counter_positions" and q["scope"] == "experiment" and q["positions"] == [3]
    assert q["candidates_resolved_by_position"] == {"3": 1} and "3rd" in q["text"] and "XX_02_" in q["text"]
    assert q["answer_shape"]["decision"] == "set_counter_positions" and p["counter_positions_decision"] is None


def test_a_counter_position_decision_groups_names_differing_only_there():
    p = G.propose(_middle_counter_bundle([DECISION]))
    multi = [g for g in p["record_groups"] if len(g["member_run_keys"]) > 1]
    assert len(multi) == 1 and multi[0]["member_run_ids"] == ["run-001", "run-002"]
    assert multi[0]["counter_positions_basis"] == "dec-syn-cp-1"
    assert len(p["record_groups"]) == 2 and p["merge_candidates"] == []  # YY stays its own group
    assert p["experiment_questions"] == [] and p["counter_positions_decision"]["positions"] == [3]
    assert G.condition_violations(_middle_counter_bundle([DECISION]), p) == []


def test_invalid_counter_decisions_are_ignored():
    for bad in (
        {**DECISION, "target": {"kind": "record_group", "id": "rg-x"}},
        {**DECISION, "positions": []},
        {**DECISION, "positions": [0]},
        {**DECISION, "positions": [True]},
        {**DECISION, "decision": "confirm"},
    ):
        p = G.propose(_middle_counter_bundle([bad]))
        assert all(len(g["member_run_keys"]) == 1 for g in p["record_groups"]), bad
    # the LAST decision wins (via mutations.counter_positions)
    p = G.propose(_middle_counter_bundle([DECISION, {**DECISION, "positions": [1], "decision_id": "dec-2"}]))
    assert p["counter_positions_decision"]["decision_id"] == "dec-2"
    assert all(len(g["member_run_keys"]) == 1 for g in p["record_groups"])
    assert p["counter_positions_decision"]["decided_by"] == "SYN Scientist"


# --- re-review fixes ---------------------------------------------------------------------------


def _nosample_scanidx(stems, legacy=None):
    nosample = {k: v for k, v in BASE.items() if k != "sample_name"}
    b = _bundle([{"stem": st, "conds": dict(nosample)} for st in stems])
    _scan_index_conflict(b)
    for run, n in zip(b["runs"], legacy or []):
        run["legacy_number"] = n
    return b


def test_bare_edge_numbers_are_not_counters():
    for stems in (["SYN_cat_400", "SYN_cat_800"], ["3_SYN_cat_400mV", "5_SYN_cat_400mV"]):
        b = _nosample_scanidx(stems)
        p = G.propose(b)
        assert all(len(g["member_run_keys"]) == 1 for g in p["record_groups"]), stems
        (mc,) = p["merge_candidates"]
        assert any(r["code"] == "numeric_name_token_differs" for r in mc["reasons"])
    assert G.name_stem_key("SYN_cat_400") == "syn_cat_400" and G.name_stem_key("3_SYN_cat") == "3_syn_cat"


def test_zero_padded_or_legacy_numbered_edges_are_counters_and_are_named_in_the_question():
    p = G.propose(_nosample_scanidx(["03_SYN_cat_400mV", "05_SYN_cat_400mV"]))
    (g,) = p["record_groups"]
    q = next(q for q in g["questions"] if q["code"] == "confirm_repeats_merge")
    assert "03 / 05" in q["text"] and [d["counter_tokens"] for d in q["differing_bookkeeping"]] == [["03"], ["05"]]
    p2 = G.propose(_nosample_scanidx(["3_SYN_cat_400mV", "5_SYN_cat_400mV"], legacy=[3, 5]))
    assert len(p2["record_groups"]) == 1  # equals the run's own legacy number: a counter
    p3 = G.propose(_nosample_scanidx(["SYN_cat_400mV_001", "SYN_cat_400mV_002"]))
    assert len(p3["record_groups"]) == 1  # trailing zero-padded scan index


def test_condition_violations_also_checks_non_counter_name_tokens():
    b = _nosample_scanidx(["SYN_cat_400", "SYN_cat_800"])
    p = G.propose(b)
    g1, g2 = p["record_groups"]
    g1["member_run_keys"] = g1["member_run_keys"] + g2["member_run_keys"]
    assert {v["key"] for v in G.condition_violations(b, p)} == {"name_non_counter_tokens"}


def test_violations_are_enforced_by_dissolving_the_group(monkeypatch):
    b = _bundle([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": dict(BASE)}])
    real = G.condition_violations
    calls = {"n": 0}

    def flaky(bundle, proposal):
        calls["n"] += 1
        multi = [g for g in proposal["record_groups"] if len(g["member_run_keys"]) > 1]
        if calls["n"] == 1 and multi:
            return [{"group_id": multi[0]["group_id"], "key": "synthetic_injected", "values": {}}]
        return real(bundle, proposal)

    monkeypatch.setattr(G, "condition_violations", flaky)
    p = G.propose(b)
    assert all(len(g["member_run_keys"]) == 1 for g in p["record_groups"])
    assert len(p["violations_prevented"]) == 1 and p["condition_violations"] == []
    (mc,) = p["merge_candidates"]
    assert any(r["code"] == "condition_check_failed" for r in mc["reasons"])


def test_run_group_reports_enforcement_counts():
    from isaac_api.local_import.processing.cli_entry import build_groups_payload

    payload = build_groups_payload(_bundle([{"stem": "01_SYN", "conds": dict(BASE)}, {"stem": "02_SYN", "conds": dict(BASE)}]))
    assert payload["condition_violations"] == [] and payload["violations_prevented"] == 0
    assert "merges_prevented_by_name_tokens" in payload


def test_header_timestamps_are_anchored():
    a = ["SSRL SYNTHETIC", "Mon Jan 01 10:00:00 2099", "SYN Ti foil measured Mon Jan 01 10:00"]
    b = ["SSRL SYNTHETIC", "Tue Jan 02 11:00:00 2099", "SYN TiO2 pellet measured Mon Jan 01 10:00"]
    ha, hb = G.header_statements(a), G.header_statements(b)
    assert ha == ["SSRL SYNTHETIC", "SYN Ti foil measured <timestamp>"]  # pure timestamp line dropped
    assert ha != hb  # the descriptions differ; the shared timestamp does not hide it
    assert G.header_statements(["SYN x measured Mon Jan 01 10:00"]) == G.header_statements(["SYN x measured Fri Feb 09 12:30"])


def test_unread_non_padded_leading_numbers_need_a_decision():
    b = _unread_bundle(["17_SYN_m111mV_801_A.001", "18_SYN_m111mV_802_A.001"])
    groups = G.propose_unread_acquisition_groups(b)
    (mc,) = G.propose_unread_merge_candidates(groups)
    assert not mc["names_agree_on_non_counter_tokens"] and mc["reasons"][0]["code"] == "numeric_name_token_differs"
    out, rem = G.promote_unread_by_headers(groups, [mc], lambda rel: list(HEAD))
    assert len(out) == 2 and len(rem) == 1  # identical headers cannot settle a differing number
    (mc2,) = G.propose_unread_merge_candidates(groups, counter_positions=[1])
    out2, rem2 = G.promote_unread_by_headers(groups, [mc2], lambda rel: list(HEAD))
    assert rem2 == [] and len(out2) == 1


def test_counter_decision_without_a_named_decider_is_ignored():
    bad = {**DECISION, "decided_by": {"name": "  ", "basis": "self_reported_local_user"}}
    p = G.propose(_middle_counter_bundle([bad]))
    assert p["counter_positions_decision"] is None and all(len(g["member_run_keys"]) == 1 for g in p["record_groups"])


def test_a_second_technique_macro_is_never_merged():
    def mutate(b):
        for run in b["runs"]:
            cid = f"cand-am-{run['run_id']}"
            b["candidates"].append(_cand(cid, run["run_id"], "acquisition_method", None, ["Zz_XAS.mac", "kbeta_emission.mac"], state="conflicting"))
            run["candidate_ids"].append(cid)
    base = {k: v for k, v in BASE.items() if k != "acquisition_method"}
    p = _propose([{"stem": "01_SYN", "conds": base}, {"stem": "02_SYN", "conds": base}], mutate=mutate)
    assert all(len(g["member_run_keys"]) == 1 for g in p["record_groups"])
    (mc,) = p["merge_candidates"]
    assert any(r["code"] == "blocked_by_engine_reading" and r["issue"]["code"] == "several_technique_macros" for r in mc["reasons"])
