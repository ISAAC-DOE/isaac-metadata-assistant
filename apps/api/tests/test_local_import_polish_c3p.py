"""Skill polish, cycle 3 (processing, measured on two real SSRL BL4-3 beamtimes). Synthetic only.

* ATHENA NAMES THAT ARE XDC SCAN FILES (``isaac.athena.match_by_name.v1``). On BL4-3 the scientists'
  Athena groups are named after the scan FILE they hold, ``<run stem>_A.001`` (the SSRL EXAFS Data
  Collector writes a run's scans as ``<stem>_A.NNN``): 161 + 29 Athena groups matched no record group
  under v0. v1 accepts exactly that suffix (``_A.NNN`` / ``_a_NNN``, any case) as naming the run, and
  reads it as scan NNN; nothing looser (no prefix or substring match), and an Athena name that fits
  two record groups still matches neither, with a note.
* JUNK OR MIS-NORMALISED ISAAC CURVES FAIL. A curve whose post-edge level, measured from the pre-edge
  line at E0, is not between 0 and 2 edge steps (``post_edge_not_at_1``), or whose edge step is not 5
  times the pre-edge scatter (``no_edge``), fails with a plain sentence instead of warning.
* A REFERENCE FOIL WHOSE ln(I0/I1) FAILS THOSE CHECKS tries the reference channel: ln(I1/I2), or
  ln(I0/I2) when I1 is not a positive intensity — only for a foil said to be on I2 or one whose I1 is
  not positive, recorded and flagged, never silent.
"""

from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")

from isaac_api.local_import.processing import athena as A  # noqa: E402
from isaac_api.local_import.processing import run as RUN  # noqa: E402
from isaac_api.local_import.processing.cli_entry import run_process  # noqa: E402

from test_local_import_processing import GRID, _athena_case, isaac, mu_edge  # noqa: E402

# --- 1. Athena names that are XDC scan files -----------------------------------------------------------


def test_the_xdc_scan_file_suffix_names_the_run():
    stem = "03_syn_dry_015"
    for name in ("03_SYN_dry_015_A.001", "03_syn_dry_015_a_001", "03_SYN_DRY_015_a.012"):
        assert A._match_kind([A.normalise_name(name)], stem) == "xdc_scan_file", name
    # nothing looser: another letter, no separator, a word, or more after the number
    for name in ("03_SYN_dry_015_B.001", "03_SYN_dry_015_A001", "03_SYN_dry_015_Ab.001", "03_SYN_dry_015_A.001_x",
                 "03_SYN_dry_0150_A.001", "x03_SYN_dry_015_A.001"):
        assert A._match_kind([A.normalise_name(name)], stem) is None, name
    # the v0 shapes are unchanged
    assert A._match_kind(["03_syn_dry_015"], stem) == "exact" and A._match_kind(["03_syn_dry_015_001"], stem) == "suffix"
    assert A.MATCH_RULE_ID == "isaac.athena.match_by_name.v1"


def test_an_xdc_scan_file_name_selects_that_scan():
    assert A.scan_selection("03_SYN_dry_015_A.001", ["03_SYN_dry_015"]) == [1]
    assert A.scan_selection("03_SYN_dry_015_a_012.xmu", ["03_SYN_dry_015"]) == [12]
    assert A.scan_selection("SYN_x_A.003", ["SYN_x_A"]) == [3]  # unchanged: a stem that ends in A
    assert A.scan_selection("03_SYN_dry_015_B.001", ["03_SYN_dry_015"]) is None


def test_an_xdc_name_that_fits_two_record_groups_matches_neither():
    entry = {"names": ["syn_x_a_001"], "label": "SYN_x_A.001", "prj_relative_path": "SYN.prj", "data_hash": "h", "is_merge": False}
    groups = [{"group_id": "g-x", "_stems": ["SYN_x"], "_has_scans": True},      # SYN_x + _A.001
              {"group_id": "g-xa", "_stems": ["SYN_x_A"], "_has_scans": True}]   # SYN_x_A + _001
    matched, notes = A.match(groups, [entry], np)
    assert matched == {}
    assert notes == [{"code": "athena_group_matches_several_record_groups", "athena_label": "SYN_x_A.001",
                      "prj_relative_path": "SYN.prj", "group_ids": ["g-x", "g-xa"]}]


def test_an_athena_group_named_after_one_xdc_scan_file_is_compared(tmp_path):
    bdir, root = _athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1_A.001", GRID, mu_edge(GRID) * 1e-2)]})
    out = run_process(bdir, source_root=root)
    isa = isaac(out)
    ref = isa["comparison"]["athena_ref"]
    assert ref["match_kind"] == "xdc_scan_file" and ref["match_rule"] == "isaac.athena.match_by_name.v1"
    assert isa["comparison"]["athena_scan_selection"] == [1]
    assert "scientist_selected_subset_of_scans" in isa["comparison"]["flags"]  # the group has scans 1 and 2
    assert out["athena"]["match_rule"] == "isaac.athena.match_by_name.v1" and out["athena"]["record_groups_matched"] == 1
    assert [r["source"] for r in out["processing_results"]] == ["isaac_protocol", "scientist_athena"]


def test_one_athena_group_per_xdc_scan_file_is_compared_as_a_set(tmp_path):
    groups = [("01_SYN_ZZ1_A.001", GRID, mu_edge(GRID) * 1e-2), ("01_SYN_ZZ1_A.002", GRID, mu_edge(GRID) * 1.01e-2)]
    bdir, root = _athena_case(tmp_path, {"SYN.prj": groups})
    isa = isaac(run_process(bdir, source_root=root))
    assert isa["comparison"]["athena_ref"]["match_kind"] == "per_scan_set"
    assert "athena_versions" not in isa


def test_the_no_match_line_names_only_suffixes_the_rule_does_not_accept():
    groups = [{"group_id": "g1", "_stems": ["03_SYN_dry_015"], "_has_scans": True}]
    entries = [{"names": ["03_syn_dry_015_b_001"], "label": "x"}, {"names": ["unrelated"], "label": "z"}]
    line = RUN.athena_match_statement(groups, entries, matched={}, notes=[])
    assert "isaac.athena.match_by_name.v1" in line and "_A.001" in line
    assert "1 of them" in line and "'_b_001'" in line
    # a name the rule accepts is never said to end in a suffix it does not accept (it was ambiguous)
    line = RUN.athena_match_statement(groups, [{"names": ["03_syn_dry_015_a_001"], "label": "y"}], matched={},
                                      notes=[{"code": "athena_group_matches_several_record_groups"}])
    assert "does not accept" not in line and "1 matched several record groups" in line
