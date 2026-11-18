"""The beamline scientist answers of 17 Nov 2026 (relayed by Krish) on import, grouping and what processing reads.
SYNTHETIC data only: every spectrum is invented (arctan edges, Poisson counts), every name SYN_*.

* pq-001: a BL15-2 scan's energy axis is always ``absev``; a BL15-2 scan without it is flagged, never read on ``energy``;
* pq-002: a new spot of one sample at one condition is not a new result: one group, each scan's spot recorded;
* pq-003: a differing stepNN never merges, even at the same potential;
* pq-005/pq-007: Athena is never used (no result, comparison, record or QC input);
* pq-006 and over-absorption: no dead-time flag, no over-absorption flag, question or caveat;
* every answered question is closed with its answer; pq-004 (alignment) is answered, its implementation pending.

Per-scan alignment, per-series normalisation windows, the white-line sensitivity report, the repeat-scan E0 check, the
edge-in-range reference check and tolerance changes are NOT here: the xas-analysis reduction engine will do the
reduction maths.
"""

from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")

import test_local_import_processing as T  # noqa: E402
from isaac_api.local_import import grouping as G  # noqa: E402
from isaac_api.local_import.processing import channels as CH  # noqa: E402
from isaac_api.local_import.processing import protocol as P  # noqa: E402
from isaac_api.local_import.processing import run as RUN  # noqa: E402

E0 = 4966.0  # synthetic edge (eV); invented
GRID = np.concatenate([np.arange(4900.0, 4955.0, 2.0), np.arange(4955.0, 4990.0, 0.25), np.arange(4990.0, 5250.0, 1.0)])
GLITCH_EV = 5030.0  # a SYN monochromator glitch (true energy)
SPOT_A = (-27.25, 15.4, -6.7, -45.0)
SPOT_B = (-26.75, 15.9, -6.7, -45.0)


def _edge(e, e0, width=1.0):
    return 0.5 + np.arctan((e - e0) / width) / np.pi


def herfd(seed, delta=0.0, *, chem=0.0, foil_noise=0.002, glitch=True, foil_e0=E0, spot=SPOT_A, absev=True,
          emiss=9000.0, filt=10, account=None, detector="vortDT", motors="keyed"):
    """One SYN BL15-2-like scan as SPEC text (``absev`` and ``energy`` 2 eV apart, I0/I1/I2/vortDT, a #P line with the
    emission energy, filter and the stage motors of ``spot``). ``absev=False`` leaves the absev column out."""
    rng = np.random.default_rng(seed)
    et = GRID
    e = et + delta
    i0_true = 2.0e5 * (1.0 - 2.0e-4 * (et - et[0]))
    if glitch:
        i0_true = i0_true * (1.0 - 0.06 * np.exp(-((et - GLITCH_EV) / 0.8) ** 2))
    i0 = rng.poisson(i0_true).astype(float)
    rate = 0.001 + 0.009 * (_edge(et, E0 + chem) + 0.8 * np.exp(-0.5 * ((et - E0 - chem - 3.0) / 1.5) ** 2))
    vort = rng.poisson(rate * i0).astype(float)
    i1 = 0.5 * i0
    mu_ref = 0.4 + 1.0 * _edge(et, foil_e0, width=1.5) + foil_noise * rng.standard_normal(et.size)
    i2 = i1 * np.exp(-mu_ref)
    cols = {"energy": e - 2.0, **({"absev": e} if absev else {}), "I0": i0, "I1": i1, "I2": i2, detector: vort}
    names = list(cols)
    sx, sy, sz, sr = spot
    head = ["#F SYN", "#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented."]
    if account:
        head.append(f"#C spec  User = {account}")
    if motors == "paired":  # the root acquisition file's form: #O names at file level, unkeyed #P values per scan
        head += ["#O0 dummy0  energy  emiss  filter", "#O1 Sx  Sy  Sz  Sr"]
        pos = [f"#P0 4 4950 {emiss} {filt}", f"#P1 {sx} {sy} {sz} {sr}"]
    elif motors == "mispaired":
        head += ["#O0 dummy0  energy  emiss  filter", "#O1 Sx  Sy  Sz  Sr"]
        pos = [f"#P0 4 4950 {emiss} {filt}", f"#P1 {sx} {sy} {sz}"]
    else:
        pos = [f"#P0 dummy0=4 energy=4950 emiss={emiss} filter={filt} Sx={sx} Sy={sy} Sz={sz} Sr={sr}"]
    lines = head + ["#S 1  gscan energy 4900 4955 2 4990 0.25 5250 1 0.5", *pos, "#L " + "  ".join(names)]
    for row in zip(*(cols[n] for n in names)):
        lines.append(" ".join(f"{v:.6f}" for v in row))
    return "\n".join(lines) + "\n"


def _case(tmp_path, groups, *, bl15=False, matches=None, label="SYN_beamtime", confirmed=None):
    """``bl15``: the bundle's SPEC fingerprint matches BL15-2 alone; ``matches``: the beamlines it matches;
    ``confirmed``: the scientist's answer to the beamline question (system.facility.beamline)."""
    bdir, root, bundle = T.make_case(tmp_path, [(stem, texts, {"sample_name": stem.split("_")[-1]})
                                                for stem, texts in groups], label=label)
    names = ["BL15-2"] if bl15 else list(matches or ())
    if names:
        bundle["experiment"]["acquisition_system"] = {"fingerprint": {"matches": [{"beamline": n} for n in names]}}
    if confirmed:
        bundle["missing_values"] = [{"value_id": "mv-syn-bl", "run_id": None, "target_field_path": "system.facility.beamline",
                                     "value_state": "scientist_confirmed"}]
        bundle["scientist_decisions"] = [{"target": {"kind": "missing_value", "id": "mv-syn-bl"},
                                          "decision": "correct", "value": confirmed}]
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root, bundle


# --- pq-002 and pq-003: spots merge, steps never do ---------------------------------------------------------------------


def test_each_merged_scans_spot_is_recorded_and_shown(tmp_path):
    texts = [herfd(90, 0.0, spot=SPOT_A), herfd(91, 0.0, spot=SPOT_B), herfd(92, 0.0, spot=SPOT_A)]
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", texts)])
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert [i["spot"]["label"] for i in r["inputs"]] == ["spot 1", "spot 2", "spot 1"]
    assert r["inputs"][1]["spot"] == {"Sx": -26.75, "Sy": 15.9, "Sz": -6.7, "Sr": -45.0, "label": "spot 2"}
    assert T.step(r, "merge")["outcome"]["n_scans"] == 3  # the spots are merged (raw mu)
    said = r["qc"]["statements"]["spots_merged"]
    assert "2 spots" in said and "not a new result" in said
    from isaac_api.local_import import cli as CLI

    view = CLI._processing_result_view(json.loads((bdir / "bundle.json").read_text()), r)
    assert view["spots"][0] == "01_SYN_ZZ1_dir/01_SYN_ZZ1_001.dat: spot 1 (Sx=-27.25, Sy=15.4, Sz=-6.7, Sr=-45)"
    # the spot is said only: it moves no curve, so the result id is the one of the same scans with no motors stated
    params_file = next(f for f in r["outputs"]["files"] if f["role"] == "params")
    assert '"spot 1"' not in (bdir / params_file["relative_path"]).read_text()


def test_a_spot_is_read_from_paired_O_and_P_lines_and_an_unread_one_is_said(tmp_path):
    # the root acquisition form: #O names at file level, unkeyed #P values (bl15.spec.pair_motor_positions)
    texts = [herfd(95, spot=SPOT_A, motors="paired"), herfd(96, spot=SPOT_B, motors="paired"),
             herfd(97, spot=SPOT_A, motors="mispaired")]
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", texts)])
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert [(i.get("spot") or {}).get("label") for i in r["inputs"]] == ["spot 1", "spot 2", None]
    assert r["inputs"][1]["spot"] == {"Sx": -26.75, "Sy": 15.9, "Sz": -6.7, "Sr": -45.0, "label": "spot 2"}
    assert "does not pair with its #O line" in r["inputs"][2]["spot_not_read"]  # refused, never guessed
    said = r["qc"]["statements"]["spots_merged"]
    assert "2 spots" in said and "Spot not read for 1 merged scan" in said
    from isaac_api.local_import import cli as CLI

    view = CLI._processing_result_view(json.loads((bdir / "bundle.json").read_text()), r)
    assert view["spots"][2].endswith("spot not read (1 #P line does not pair with its #O line (the counts differ; "
                                     "never guessed))")


_BASE = {"sample_name": ("lit", "ZZ9"), "potential_magnitude": 0.85, "electrolyte_or_medium": ("lit", "acid"),
         "acquisition_method": ("lit", "Zz_XAS.mac")}


def _propose(specs):
    import test_local_import_grouping as TG

    return G.propose(TG._bundle(specs))


def test_spots_of_one_condition_are_one_group():
    assert G.classify_key("new_spot") == "bookkeeping" and G.classify_key("sample_position") == "bookkeeping"
    p = _propose([{"stem": "SYN_850mV_01", "conds": dict(_BASE)},
                  {"stem": "SYN_newSpots_850mV_02", "conds": dict(_BASE, new_spot=("lit", "newSpots"))}])
    [g] = p["record_groups"]
    assert len(g["member_run_keys"]) == 2 and p["merge_candidates"] == []
    assert not any(c.get("key") == "new_spot" for c in g.get("split_reasons") or ())


def test_a_different_filter_still_splits_spots():
    p = _propose([{"stem": "SYN_01", "conds": dict(_BASE, filter=("lit", "10"))},
                  {"stem": "SYN_newSpots_02", "conds": dict(_BASE, filter=("lit", "35"), new_spot=("lit", "newSpots"))}])
    assert len(p["record_groups"]) == 2


def test_two_steps_at_the_same_potential_stay_separate_and_record_their_sequence_position():
    assert G.classify_key("step_number") == "condition" and "step_number" not in G.UNKNOWN_KEYS
    p = _propose([{"stem": "SYN_step05_850mV_01", "conds": dict(_BASE, step_number=("lit", "step05"))},
                  {"stem": "SYN_step08_850mV_02", "conds": dict(_BASE, step_number=("lit", "step08"))}])
    g1, g2 = p["record_groups"]
    assert p["merge_candidates"] == []  # never offered for merging
    assert [g["basis"]["conditions"]["step_number"]["sequence_position"] for g in (g1, g2)] == [5, 8]
    assert g1["basis"]["conditions"]["step_number"]["rule_id"] == G.STEP_RULE_ID
    # step5 and step05 are one sequence position (5): compared by position, never by spelling
    p3 = _propose([{"stem": "SYN_step5_850mV_01", "conds": dict(_BASE, step_number=("lit", "step5"))},
                   {"stem": "SYN_step05_850mV_02", "conds": dict(_BASE, step_number=("lit", "step05"))}])
    assert len(p3["record_groups"]) == 1 and p3["merge_candidates"] == []
    assert p3["record_groups"][0]["basis"]["conditions"]["step_number"]["sequence_position"] == 5
    # spots within ONE step still merge
    p2 = _propose([{"stem": "SYN_step05_850mV_01", "conds": dict(_BASE, step_number=("lit", "step05"))},
                   {"stem": "SYN_step05_newSpots_850mV_02",
                    "conds": dict(_BASE, step_number=("lit", "step05"), new_spot=("lit", "newSpots"))}])
    assert len(p2["record_groups"]) == 1


# --- pq-001: BL15-2 energy is absev ------------------------------------------------------------------------------------


def test_a_bl15_2_scan_with_no_absev_is_flagged_never_read_on_energy(tmp_path):
    texts = [herfd(110, 0.0), herfd(111, 0.2), herfd(112, 0.1, absev=False)]
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", texts)], bl15=True)
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert r["channel_choice"]["energy"] == "absev"
    assert r["channel_choice"]["basis"]["energy_rule"]["rule_id"] == CH.BL15_2_ENERGY_RULE_ID
    assert [i.get("skip_reason") for i in r["inputs"]] == [None, None, CH.BL15_2_ENERGY_MISSING_FLAG]
    assert CH.BL15_2_ENERGY_MISSING_FLAG in r["review_flags"]
    assert "no 'absev' column" in r["qc"]["statements"][CH.BL15_2_ENERGY_MISSING_FLAG]
    # every scan without it: a plain failure, never a curve on `energy`
    (tmp_path / "b").mkdir()
    bdir2, root2, _ = _case(tmp_path / "b", [("01_SYN_ZZ1", [herfd(113, absev=False), herfd(114, absev=False)])], bl15=True)
    r2 = T.isaac(T.run_process(bdir2, source_root=root2))
    assert r2["failure"]["code"] == CH.BL15_2_ENERGY_MISSING_FLAG and r2["outputs"]["files"] == []
    assert "not read on another energy column" in r2["qc"]["statements"][CH.BL15_2_ENERGY_MISSING_FLAG]


def _flagged(r):
    return CH.BL15_2_BEAMLINE_UNCONFIRMED_FLAG in r["review_flags"]


def test_specadm_on_a_folder_naming_another_beamline_reads_energy_and_asks_to_confirm(tmp_path):
    # the fingerprint is a HINT: a BL15-2 account in a folder named for BL6-2 does not make the scans BL15-2 scans
    texts = [herfd(130, absev=False, account="specadm"), herfd(131, 0.2, absev=False, account="specadm")]
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", texts)], bl15=True, label="SYN_BL6-2_2099")
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert r["channel_choice"]["energy"] == "energy" and r["outputs"]["files"]  # a curve, on `energy`
    assert [i.get("skip_reason") for i in r["inputs"]] == [None, None]
    assert _flagged(r) and CH.BL15_2_ENERGY_MISSING_FLAG not in r["review_flags"]
    said = r["qc"]["statements"][CH.BL15_2_BEAMLINE_UNCONFIRMED_FLAG]
    assert "no 'absev' column" in said and "if this is BL15-2 data, 'absev' is required" in said
    assert "confirm the beamline" in said and "SYN_BL6-2_2099" in said and "needs review" in said
    from isaac_api.local_import import cli as CLI
    from isaac_api.local_import import mutations as M

    view = CLI._processing_result_view(json.loads((bdir / "bundle.json").read_text()), r)
    assert view["beamline_check"] == said
    assert "absev" in (M.bulk_approve_problem(r) or "")  # a reason the curve is reviewed on its own


def test_a_mixed_folder_is_decided_per_scan(tmp_path):
    # BL15-2 and BL6-2 files in one folder: neither group's scans are KNOWN to be BL15-2 scans
    bl15 = [herfd(140, absev=False, account="specadm"), herfd(141, 0.2, absev=False, account="specadm")]
    bl62 = [herfd(142, absev=False, account="b_user62", detector="FF1"),
            herfd(143, 0.2, absev=False, account="b_user62", detector="FF1")]
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", bl15), ("02_SYN_ZZ2", bl62)], matches=["BL15-2", "BL6-2"])
    payload = T.run_process(bdir, source_root=root)
    a, b = T.isaac(payload, 0), T.isaac(payload, 1)
    assert a["channel_choice"]["energy"] == b["channel_choice"]["energy"] == "energy"
    assert a["outputs"]["files"] and b["outputs"]["files"]
    assert _flagged(a) and "also BL6-2" in a["qc"]["statements"][CH.BL15_2_BEAMLINE_UNCONFIRMED_FLAG]
    assert not _flagged(b)  # its own headers name BL6-2 only: no BL15-2 rule to apply
    # one scan with absev in the mixed folder: read on absev (always right), the scan without it left out
    (tmp_path / "m").mkdir()
    bdir2, root2, _ = _case(tmp_path / "m", [("01_SYN_ZZ1", [herfd(144, account="specadm"),
                                                              herfd(145, absev=False, account="specadm")])],
                            matches=["BL15-2", "BL6-2"])
    r2 = T.isaac(T.run_process(bdir2, source_root=root2))
    assert r2["channel_choice"]["energy"] == "absev"
    assert [i.get("skip_reason") for i in r2["inputs"]] == [None, "scan_lacks_chosen_columns"]


def test_a_confirmed_bl15_2_beamline_leaves_a_scan_without_absev_out(tmp_path):
    # the scientist's answer outranks the folder's name: BL15-2 confirmed, so absev is required
    texts = [herfd(150), herfd(151, 0.2, absev=False)]
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", texts)], label="SYN_BL6-2_2099", confirmed="BL15-2")
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert r["channel_choice"]["energy"] == "absev"
    assert "scientist confirmed" in r["channel_choice"]["basis"]["energy_rule"]["bl15_2_basis"]
    assert [i.get("skip_reason") for i in r["inputs"]] == [None, CH.BL15_2_ENERGY_MISSING_FLAG]
    assert not _flagged(r)
    # another beamline confirmed: no BL15-2 rule, no flag, read on `energy`
    (tmp_path / "o").mkdir()
    bdir2, root2, _ = _case(tmp_path / "o", [("01_SYN_ZZ1", [herfd(152, absev=False), herfd(153, absev=False)])],
                            bl15=True, confirmed="BL6-2")
    r2 = T.isaac(T.run_process(bdir2, source_root=root2))
    assert r2["channel_choice"]["energy"] == "energy" and not _flagged(r2) and r2["outputs"]["files"]


def test_a_fingerprint_that_also_matches_bl6_2_is_no_bl15_2_answer(tmp_path):
    texts = [herfd(160, absev=False), herfd(161, 0.2, absev=False)]
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", texts)], matches=["BL15-2", "BL6-2"])
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert r["channel_choice"]["energy"] == "energy" and r["outputs"]["files"]
    assert _flagged(r) and CH.BL15_2_ENERGY_MISSING_FLAG not in r["review_flags"]
    # absev, when a scan has it, is used with no hint at all
    (tmp_path / "n").mkdir()
    bdir2, root2, _ = _case(tmp_path / "n", [("01_SYN_ZZ1", [herfd(162), herfd(163, 0.2)])])
    r2 = T.isaac(T.run_process(bdir2, source_root=root2))
    assert r2["channel_choice"]["energy"] == "absev" and not _flagged(r2)


def test_other_beamlines_still_choose_their_energy_column(tmp_path):
    params = P.resolve_params()
    t = T.parse_text(T.spec_file({"energy": T.GRID[:30], "I0": np.ones(30), "vortDT": np.ones(30)}))
    assert CH.choose_channels(t, params=params).energy == "energy"
    c = CH.choose_channels(t, params=params, bl15_2="SYN basis")
    assert c.energy is None and CH.BL15_2_ENERGY_MISSING_FLAG in c.flags


# --- pq-005/pq-007: Athena is never used -------------------------------------------------------------------------------


def test_athena_is_never_read_into_results(tmp_path):
    bdir, root = T._athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1", T.GRID, T.mu_edge(T.GRID) * 1e-2)]})
    payload = T.run_process(bdir, source_root=root, params={"athena_match": {"rg-syn": [{"project": "SYN.prj",
                                                                                            "athena_group": "x"}]}})
    assert [r["source"] for r in payload["processing_results"]] == ["isaac_protocol"]
    r = payload["processing_results"][0]
    assert r["comparison"] is None and "athena_versions" not in r and not r["preferred_for_record"]
    assert not [f for f in r["outputs"]["files"] if "athena" in f["role"]]
    a = payload["athena"]
    assert a["never_used"] and a["projects_found"] == 1 and a["projects_read"] == 0 and a["groups_read"] == 0
    assert "never used" in a["statement"] and "athena_match is ignored" in a["statement"]
    assert not any(f.startswith("athena") for f in r["review_flags"])


def test_an_approved_athena_result_composes_no_record(tmp_path):
    from test_local_import_records import SEMANTICS, _decide_everything

    from isaac_api.local_import import cli as CLI
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import import records as R

    bdir = tmp_path / "bundle"
    assert CLI.main(["import", str(SEMANTICS), "--out", str(bdir)]) == 0
    _decide_everything(bdir)
    b = M.load(bdir)
    _, ok = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    assert ok["processing"]["series"] and "athena_never_used" not in ok["processing"]  # ISAAC's own result composes
    # the same approval on the scientist's Athena curve (an older build's result): nothing from it is used
    b["processing_results"][0]["source"] = "scientist_athena"
    _, report = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    assert report["processing"]["used"] is None and report["processing"]["athena_never_used"] is True
    assert "never the result of record" in report["processing"]["reason"]


def _athena_approved_earlier(tmp_path):
    """A SYN bundle whose group g1 has the scientist's Athena curve ``pa`` approved under an older build (``decide``
    refuses that approval now) beside its ISAAC-processed result ``p1``, every other value decided."""
    from test_local_import_records import BY, SEMANTICS, _add_group, _cand, _miss

    from isaac_api.local_import import cli as CLI
    from isaac_api.local_import import mutations as M

    bdir = tmp_path / "bundle"
    assert CLI.main(["import", str(SEMANTICS), "--out", str(bdir)]) == 0
    _add_group(bdir)
    b = M.load(bdir)
    pa = json.loads(json.dumps(b["processing_results"][0]))
    pa["result_id"] = "pa"
    b["processing_results"].insert(0, pa)
    M.save_bundle(bdir, b)
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=["pa"], decision="approve", value=None, qc_status="valid", **BY)
    b = M.load(bdir)
    next(r for r in b["processing_results"] if r["result_id"] == "pa")["source"] = "scientist_athena"  # an older build's
    M.save_bundle(bdir, b)
    for path, run_id, decision, value in [
            ("timestamps.acquired_start_utc", "run-001", "confirm", None),
            ("sample.material.name", "run-001", "correct", "ZZ1 synthetic"),
            ("system.technique", None, "correct", "HERFD-XAS")]:
        M.decide(bdir, target_ids=[_cand(b, path, run_id)["candidate_id"]], decision=decision, value=value, **BY)
    for path, run_id, value in [
            ("system.domain", None, "experimental"), ("attribution.produced_by.group", None, "Synthetic Scientist group"),
            ("attribution.produced_by.organization", None, "Synthetic University"),
            ("context.environment", "run-001", "ex_situ"), ("sample.sample_form", "run-001", "powder"),
            ("context.temperature_K", "run-001", 298.0)]:
        M.decide(bdir, target_ids=[_miss(b, path, run_id)], decision="correct", value=value, **BY)
    return bdir, BY


def test_decide_refuses_a_new_approval_of_an_athena_result_naming_the_isaac_result(tmp_path):
    from isaac_api.local_import import mutations as M

    bdir, by = _athena_approved_earlier(tmp_path)
    M.decide(bdir, target_ids=["pa"], decision="reject", value=None, **by)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=["pa"], decision="approve", value=None, qc_status="valid", **by)
    said = str(exc.value)
    assert "pa cannot be approved: it is the scientist's Athena curve" in said and "never the result of record" in said
    assert "--target p1 --decision approve" in said and "Nothing was recorded" in said


def test_an_athena_approval_blocks_the_record_with_a_remedy_that_completes(tmp_path):
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import import records as R

    bdir, by = _athena_approved_earlier(tmp_path)
    b = M.load(bdir)
    _, report = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    proc = report["processing"]
    assert proc["used"] is None and proc["athena_never_used"] and proc["result"] == "pa" and proc["isaac_results"] == ["p1"]
    assert R.processing_blocker(proc) == "approved_result_is_athena"
    remedy = R.processing_remedy(proc)
    assert "Re-run `isaac process`" not in remedy  # the loop: the Athena approval survives re-processing
    withdraw = 'isaac bundle decide <bundle_dir> --target pa --decision reject --by "<your name>"'
    approve = 'isaac bundle decide <bundle_dir> --target p1 --decision approve --qc-status <value> --by "<your name>"'
    assert withdraw in remedy and approve in remedy and remedy.index(withdraw) < remedy.index(approve)
    # approving p1 first is refused with the same two steps (never "keep pa (nothing more to do)")
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **by)
    assert "nothing more to do" not in str(exc.value) and withdraw in str(exc.value) and approve in str(exc.value)
    # the scientist follows the remedy: the record composes from p1
    M.decide(bdir, target_ids=["pa"], decision="reject", value=None, **by)
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **by)
    b = M.load(bdir)
    _, done = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    assert done["processing"]["series"] and "athena_never_used" not in done["processing"]
    assert not done["missing_required"]


# --- pq-006 and over-absorption: never flagged -------------------------------------------------------------------------


def test_there_are_no_dead_time_or_over_absorption_flags(tmp_path):
    params = P.resolve_params()
    assert "dead_time_rate_prefix" not in params["channels"]
    xd = T.parse_text(T.xdac_file({"Achieved Energy": T.GRID[:10], "I0": np.ones(10), "I1": np.ones(10), "I2": np.ones(10),
                                   "SCA1_1": np.ones(10), "ICR1_1": np.ones(10)}))
    assert "dead_time_correction_not_applied" not in CH.choose_channels(xd, params=params).flags
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", [herfd(120), herfd(121, 0.2)])])
    payload = T.run_process(bdir, source_root=root)
    r = T.isaac(payload)
    text = json.dumps({k: v for k, v in payload.items() if k != "protocol"})  # the closed questions name the topics
    for word in ("dead_time", "over_absorption", "self_absorption", "herfd_not_transmission_equivalent", "disclosure"):
        assert word not in text, word
    assert "protocol_disclosures" not in payload["protocol"] and not hasattr(P, "PROTOCOL_DISCLOSURES")
    assert r["qc"]["verdict"] in ("pass", "warn")


# --- the questions and their answers -----------------------------------------------------------------------------------


def test_the_answered_questions_are_closed_with_their_answers():
    by = {q["question_id"]: q for q in P.PROTOCOL_QUESTIONS}
    assert set(by) == {f"pq-00{i}" for i in range(1, 8)}
    for q in by.values():
        assert q["status"] == "closed" and q["answer"] and q["answered_by"] == (
            "beamline scientist answers relayed by Krish, 17 Nov 2026")
    assert [by[k]["topic"] for k in sorted(by)] == [
        "energy_column", "grouping.new_spot", "grouping.step_number", "calibration.foil_shift_to_samples",
        "athena.e0_frame", "channels.dead_time", "athena.result_of_record"]
    assert "NOT a new result" in by["pq-002"]["answer"] and "NEVER merged" in by["pq-003"]["answer"]
    a4 = by["pq-004"]
    assert "I0" in a4["answer"] and "foil" in a4["answer"] and "element under study" in a4["answer"]
    assert "xas-analysis" in a4["implementation"] and "pending" in a4["implementation"]
    for rid in (RUN.ATHENA_NEVER_RULE_ID, CH.BL15_2_ENERGY_RULE_ID):
        assert rid in P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION["rule_ids"]
    # none of the backed-out reduction changes is in this build
    assert P.DEFAULT_PARAMS["qc"]["warn_reference_e0_spread_eV"] == 0.5
    assert P.DEFAULT_PARAMS["calibration"]["align_scans_by_reference"] is False
    assert "one_set_per_series" not in P.DEFAULT_PARAMS["normalize"]
