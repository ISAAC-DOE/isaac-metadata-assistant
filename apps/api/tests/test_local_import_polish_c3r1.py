"""Skill polish, cycle 3 review round 1 (processing). Synthetic only.

* THE POST-EDGE LEVEL ``isaac.xas.post_edge_level.v1``. v0 measured the level from the pre-edge line held
  at its E0 value, so a sound TRANSMISSION spectrum fell outside 0..2: its absorption background falls
  across the 50-600 eV post-edge window by more than the edge step (a Co K-edge on a background of 2.5),
  or its pre-edge line has a real slope. v1 measures it from the pre-edge line AT EACH post-edge energy
  (the mean of larch's ``norm`` over the window) AND from the line held at E0, and fails only when BOTH
  are outside 0..2: on real dilute HERFD scans the line's slope, fitted over a 15 eV pre-edge window, is
  extrapolated 280 eV and alone put sound spectra at -0.7 or 2.8.
* THE REFERENCE CHANNEL IS FOR FOILS. The fallback to the reference channel was reached by any group
  whose role is ``reference``, which a ``std``/``standard``/``ref`` token gives a compound standard too
  (``05_SYN_CoO_std_005`` with a dead I1 was switched to ln(I0/I2)). It now needs a run name with a
  ``foil``/``calib`` token, or the ``alignment`` role.
* RULE VERSIONS. ``PROTOCOL_VERSION`` is hashed into every run id, so it stays 0.1.0 (bumping it would
  move every result id); each ISAAC result records instead the rule versions changed since 0.1.0.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
larch_xafs = pytest.importorskip("larch.xafs", reason="XAS processing tests need the optional `processing` extra (xraylarch)")

from isaac_api.local_import.processing import core as C  # noqa: E402
from isaac_api.local_import.processing import protocol as P  # noqa: E402
from isaac_api.local_import.processing import run as RUN  # noqa: E402
from isaac_api.local_import.processing.cli_entry import run_process  # noqa: E402

from test_local_import_polish_c3p import _foil_scan  # noqa: E402
from test_local_import_processing import E0, GRID, fluo_scan, isaac, make_case, mu_edge, spec_file  # noqa: E402

CO_E0 = 7709.0  # a synthetic Co K-edge position (eV); every value below is invented


def _co_transmission(step, top, *, background=2.5, slope=0.0, victoreen=True):
    """A SYNTHETIC clean Co K-edge in transmission: a background of ``background`` (falling as (E0/E)^3,
    as an absorption background does, or flat), plus a pre-edge slope of ``slope`` edge steps per eV, plus
    an edge of ``step``; scanned from 200 eV below E0 to ``top`` eV above it."""
    e = np.concatenate([np.arange(CO_E0 - 200, CO_E0 - 20, 5.0), np.arange(CO_E0 - 20, CO_E0 + 30, 0.5),
                        np.arange(CO_E0 + 30, CO_E0 + top + 1e-9, 3.0)])
    bg = background * (CO_E0 / e) ** 3 if victoreen else np.full(e.size, background)
    return e, bg + slope * step * (e - CO_E0) + step * (0.5 + np.arctan((e - CO_E0) / 1.0) / np.pi)


SOUND_TRANSMISSION = [
    # (step, scan end above E0, pre-edge slope in edge steps per eV, falling background): v0 failed each
    (0.2, 491, 0.0, True),
    (0.1, 191, 0.0, True),
    (0.4, 991, 0.0, True),
    (0.5, 491, 0.01, False),
    (0.5, 491, -0.01, False),
]


@pytest.mark.parametrize("step,top,slope,victoreen", SOUND_TRANSMISSION)
def test_a_sound_transmission_spectrum_is_at_1(step, top, slope, victoreen):
    e, mu = _co_transmission(step, top, slope=slope, victoreen=victoreen)
    nm = C.normalize(e, mu, P.resolve_params(), np, larch_xafs)
    rp = nm["resolved_params"]
    assert C.post_edge_level_implausible(e, mu, nm["pre_edge_curve"], nm["e0_eV"], nm["edge_step"], np,
                                         norm1=rp["norm1"], norm2=rp["norm2"]) is None
    assert C.edge_checks(e, mu, nm, np) == {}
    # what v0 measured (the line held at E0) is far from 1 here; the mean of larch's norm is not
    sel = (e >= nm["e0_eV"] + rp["norm1"]) & (e <= nm["e0_eV"] + rp["norm2"])
    at_e0 = (mu[sel].mean() - np.interp(nm["e0_eV"], e, nm["pre_edge_curve"])) / nm["edge_step"]
    assert not 0.0 < at_e0 < 2.0
    assert 0.8 < float(np.mean(nm["norm"][sel])) < 1.3


def test_the_level_is_measured_both_ways_and_fails_only_when_both_are_off():
    mu = mu_edge(GRID, step=1.5, offset=0.0)
    flat = np.zeros(GRID.size)
    # a pre-edge line whose slope is wrong (fitted over a few noisy points, extrapolated far): from the line
    # at each energy the level is far from 1, from the line held at E0 it is 1 -> not failed
    tilted = 0.03 * (GRID - E0)
    assert C.post_edge_level_implausible(GRID, mu, tilted, E0, 1.5, np, norm1=60.0, norm2=130.0) is None
    # a step that does not describe the jump is off both ways -> failed, with both levels
    bad = C.post_edge_level_implausible(GRID, mu, flat, E0, 0.6, np, norm1=60.0, norm2=130.0)
    assert bad["rule_id"] == C.POST_EDGE_LEVEL_RULE_ID == "isaac.xas.post_edge_level.v1"
    assert bad["level"] == pytest.approx(bad["level_from_line_at_e0"], rel=1e-9) and bad["level"] > 2
    assert "from the pre-edge line at each energy" in bad["statement"] and "held at its E0 value" in bad["statement"]
    # one off each way: neither near 1 -> failed
    mixed = C.post_edge_level_implausible(GRID, mu - 3.0 * (GRID - E0) / 95.0, -0.05 * (GRID - E0), E0, 1.5, np,
                                          norm1=60.0, norm2=130.0)
    assert mixed is not None and (mixed["level"] > 2) != (mixed["level_from_line_at_e0"] > 2)
    assert "neither is near 1" in mixed["statement"]
    assert C.POST_EDGE_LEVEL_RANGE == (0.0, 2.0)


def _trans_scan(seed, step, top):
    e, mu = _co_transmission(step, top)
    rng = np.random.default_rng(seed)
    i0 = np.full(e.size, 1.0e5)
    return {"energy": e, "I0": i0, "I1": i0 * np.exp(-mu) * (1 + rng.normal(0, 2e-5, e.size))}


def test_a_sound_transmission_pellet_is_not_failed_end_to_end(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("01_SYN_CoO_pellet_010", [spec_file(_trans_scan(s, 0.2, 491)) for s in (1, 2)], {})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["channel_choice"]["signal_name"] == "ln(I0/I1)"
    assert "post_edge_not_at_1" not in r["qc"]["reasons"] and r["qc"]["verdict"] in ("pass", "warn"), r["qc"]
    assert "post_edge_level" not in r["qc"]["metrics"]


# --- the reference channel is for foils ------------------------------------------------------------------


def test_a_compound_standard_with_a_dead_i1_is_not_switched_to_the_reference_channel(tmp_path):
    bdir, root, bundle = make_case(tmp_path, [("05_SYN_CoO_std_005", [spec_file(_foil_scan(s)) for s in (1, 2)], {})])
    out = run_process(bdir, source_root=root)
    r = isaac(out)
    assert r["channel_choice"]["signal_name"] == "ln(I0/I1)"
    assert "fallback_from" not in r["channel_choice"]["basis"] and "reference_channel_tried" not in r["channel_choice"]["basis"]
    assert not {RUN.REFERENCE_FALLBACK_FLAG, RUN.REFERENCE_TRIED_FLAG} & set(r["channel_choice"]["flags"])
    assert r["qc"]["verdict"] == "fail"


@pytest.mark.parametrize("stem", ["05_SYN_Co_foil_005", "05_SYN_Co_calib_005", "05_SYN_Cofoil_std_005"])
def test_a_foil_or_calibration_with_a_dead_i1_uses_the_reference_channel(tmp_path, stem):
    bdir, root, _ = make_case(tmp_path, [(stem, [spec_file(_foil_scan(s)) for s in (1, 2)], {})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["channel_choice"]["signal_name"] == "ln(I0/I2)" and RUN.REFERENCE_FALLBACK_FLAG in r["channel_choice"]["flags"]
    assert r["qc"]["verdict"] == "warn"


def test_an_alignment_group_with_a_dead_i1_uses_the_reference_channel(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("07_SYN_align_Zz_003", [spec_file(_foil_scan(s)) for s in (1, 2)], {})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["channel_choice"]["signal_name"] == "ln(I0/I2)" and RUN.REFERENCE_FALLBACK_FLAG in r["channel_choice"]["flags"]


def test_names_a_foil():
    assert RUN._names_a_foil(["31_Ti_foil_I2_120"]) and RUN._names_a_foil(["01_Tifoil_calib_1x3mm_075"])
    assert RUN._names_a_foil(["x", "Co_calibration_02"])
    assert not RUN._names_a_foil(["05_SYN_CoO_std_005"]) and not RUN._names_a_foil(["08_std_CoSO4_ref_030"])


# --- rule versions instead of a protocol bump --------------------------------------------------------------


def test_the_protocol_version_is_not_bumped_and_each_result_records_the_changed_rules(tmp_path):
    assert P.PROTOCOL_VERSION == "0.1.0"  # hashed into every run id: a bump moves every result id
    gid, ids, data = "rg-x", ["a"], [("qc.json", "b")]
    assert RUN.run_id_for(gid, ids, data) == RUN.run_id_for(gid, ids, data)
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(s)) for s in (1, 2)], {"sample_name": "ZZ1"})])
    r = isaac(run_process(bdir, source_root=root))
    rv = r["rule_versions"]
    assert rv == P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION
    assert rv["since_protocol_version"] == "0.1.0"
    assert C.POST_EDGE_LEVEL_RULE_ID in rv["rule_ids"] and RUN.REFERENCE_CHANNEL_RULE_ID in rv["rule_ids"]
    assert RUN.REFERENCE_CHANNEL_RULE_ID == "isaac.xas.reference_channel_fallback.v1"
    # outside the hashed files: qc.json does not carry it
    import json

    qc = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    assert "rule_versions" not in json.loads((bdir / qc["relative_path"]).read_text())
