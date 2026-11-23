"""At SSRL BL4-3: a reference standard named as one, and the absorber the scanned energy range brackets (bundle 1.16.0;
audit of 18 Nov 2026, rules 13 and 14). SYNTHETIC files only.

What these pin:

* an XDC run whose name is a mineral (``ANATASE``), ``elemental`` before an element, a weight-percent dilution
  (``0p8wtpc``) or a dilution matrix (``sucrose``) PROPOSES the role reference (``grouping.XDC_STANDARD_NAME_RULE_ID``),
  said as judged from the name; never beside a potential, an electrolyte, a support or a history word, and never from a
  formula alone;
* a scan whose energy grid has a finest-step window with a pre-edge and a post-edge region around it names the edge
  that window brackets (``suggestions.SCANNED_EDGE_RULE_ID``): a witness for that run's group's absorber SUGGESTION,
  never a value; a uniformly sampled scan names nothing; several edges in the window name the one K/L3 edge, or none.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_reader_ssrl_xdc import make_scan  # noqa: E402

#: a Ti K XANES grid: 5 eV pre-edge steps, 0.25 eV across 4960..4980 (Ti K: 4966.4 eV), 10 eV post-edge steps
TI_K = ([4900.0 + 5 * i for i in range(12)] + [4960.0 + 0.25 * i for i in range(81)]
        + [4990.0 + 10 * i for i in range(20)])
UNIFORM = [4955.0 + 0.5 * i for i in range(61)]  # a uniformly sampled check scan: no XANES region


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


@pytest.mark.parametrize("stem,token", [
    ("03_ZZANATASE_1x1mm_081", None),           # not the word itself
    ("03_ANATASE_1x1mm_081", "anatase"),
    ("10_ANATASE_LowCounts_1x1mm_opt_086", "anatase"),
    ("01_elemental_S_006", "elemental"),
    ("29_0p8wtpc_TiO2_anatase_116", "anatase"),
    ("30_0p7wtpc_Ti2O3_119", "0p7wtpc"),             # a dilution of a stoichiometric compound and nothing else
    ("31_Na2S2O3_5wt_sugar_spot2_065", "5wt"),
    # review of PR 346, I5: a dilution or a matrix alone is how any transmission pellet is made, samples included
    ("08_ZZCoMOF_0p5wt_sucrose_029", None),
    ("40_SYN_BN_pellet_200", None),
    ("15_CoMOF_10wt_BN_016", None),
    ("18_MOFCoTHT_5wt_cellulose_018", None),
    ("26_CoTHT_sugar_026", None),
    ("30_Sample_BN_030", None),
    ("15_RuO2_rutile_film_015", None),               # a rutile-phase film: a sample
    ("28_TiO2_brookite_postXAS_028", None),          # a history word
    ("15_SYNTiON_1x1mm_1MKOHAr_m600mV_096", None),   # a condition
    ("19_SYN_anatase_afterHER_100", None),           # a history word
    ("22_SYN_IrO2_5wt_1MKOH_1200mV_107", None),      # a potential beside the dilution
    ("30_SYN_TiO2_film_119", None),                  # a formula alone
    ("11_elemental_ZZ_092", None),                   # not an element after `elemental`
])
def test_a_standard_is_proposed_by_its_name(stem, token):
    got = G.xdc_standard_role(stem)
    assert got == (None if token is None else (G.ROLE_REFERENCE, token))


def test_the_edge_a_scan_brackets():
    check = {"finest_window_eV": [4960.0, 4980.0], "range_eV": [4900.0, 5180.0], "finest_step_eV": 0.25}
    got = S.scanned_edge(check)
    assert (got["element"], got["edge"]) == ("Ti", "K")
    assert S.scanned_edge({**check, "range_eV": [4960.0, 4980.0]}) is None  # no pre- or post-edge region
    # S K (2472 eV) beside Nb L2 (2465 eV): the K edge is the one scanned
    sk = S.scanned_edge({"finest_window_eV": [2464.2, 2475.8], "range_eV": [2390.0, 2815.0], "finest_step_eV": 0.15})
    assert (sk["element"], sk["edge"]) == ("S", "K")
    assert S.scanned_edge({"finest_window_eV": [40.7, 50.7], "range_eV": [30.0, 60.0]}) is None  # below 1 keV


def _beamtime(root: Path) -> Path:
    bt = root / "SYN_BL43_2100-30_Standards"
    make_scan(bt / "01_SYNTiON_1x1mm_dry_091_A.001", points=len(TI_K), energies=TI_K)
    make_scan(bt / "03_ANATASE_1x1mm_081_A.001", points=len(TI_K), energies=TI_K)
    make_scan(bt / "05_SYNTiON_1x1mm_check_093_A.001", points=len(UNIFORM), energies=UNIFORM)
    return bt


def test_import_proposes_the_role_and_suggests_the_absorber(tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main(["import", str(_beamtime(tmp_path / "src")), "--out", str(out)]) == 0
    M.group(out)
    b = M.load(out)
    role = {k: g["role"] for g in b["record_groups"] for k in g["member_run_keys"]}
    stem = {r["run_key"]: r["stem"] for r in b["runs"]}
    by_stem = {stem[k]: r for k, r in role.items()}
    assert by_stem["03_ANATASE_1x1mm_081"] == G.ROLE_REFERENCE
    assert by_stem["01_SYNTiON_1x1mm_dry_091"] == G.ROLE_SAMPLE
    g = next(g for g in b["record_groups"] if any(stem[k] == "03_ANATASE_1x1mm_081" for k in g["member_run_keys"]))
    assert g["role_basis"]["rule_id"] == G.XDC_STANDARD_NAME_RULE_ID and g["role_basis"]["basis"] == "name_token"
    ev = [e for e in b["experiment"]["element_evidence"] if e["role"] == S.SCANNED_EDGE_ROLE]
    assert {(stem[e["run_key"]], e["element"], e["edge"]) for e in ev} == {
        ("01_SYNTiON_1x1mm_dry_091", "Ti", "K"), ("03_ANATASE_1x1mm_081", "Ti", "K")}  # the uniform scan names none
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber" and q["scope"] == "experiment"]
    # the only witness is the energy grid: said so, never "the files state" (review of PR 346)
    assert "Element Ti, edge K is suggested from the scans' energy grid for 2 group(s)" in q["text"]
    assert "files state" not in q["text"]
    assert any(h["kind"] == "scanned_range" and h["literal"] == "Ti K" for h in q["hints"])
    assert "--element <El>" in q["answer_command"]  # never a ready-to-run answer
    assert not [d for d in b["scientist_decisions"] if d.get("decision") == "set_absorber"]
