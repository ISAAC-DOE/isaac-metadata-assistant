"""Audit of 18 Nov 2026, finding 12. SYNTHETIC data only.

* The name of the scientists' own merge file is no reading of a run's conditions. A fresh import has not taken it
  as one since 1.13.0 (``test_local_import_overnight_polish_merge`` pins that); a bundle an OLDER build imported
  still holds such a witness, and the care flag it raises now says so.
* A bulk confirm that takes groups carrying a care flag names them and says why.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M

BY = {"by": "SYN Scientist", "orcid": None}


def _old_bundle(merge_witness: bool) -> tuple[dict, dict]:
    """A group whose cycling-state candidate holds two spellings: the run's own name and, in a bundle an older build
    imported, the name of the scientists' merge file of that run (a processed output)."""
    evidence = [{"literal_value": "after1200mVCycling", "source_id": "src-1", "locator": "filename token 4",
                 "relative_path": "07_SYN_ZZ1_after1200mVCycling"},
                {"literal_value": "after1200Cycling", "source_id": "src-2" if merge_witness else "src-3",
                 "locator": "filename token 4" if merge_witness else "line 9 header #P0",
                 "relative_path": "MERGE/07_SYN_ZZ1_after1200Cycling.txt" if merge_witness else "07_SYN_ZZ1_dir/x_001.dat"}]
    bundle = {"candidates": [{"candidate_id": "cand-1", "statement_key": "cycling_state", "evidence": evidence}],
              "sources": [{"source_id": "src-1", "classification": {"source_type": "spec_acquisition"}},
                          {"source_id": "src-2", "classification": {"source_type": "processed_spectrum"}},
                          {"source_id": "src-3", "classification": {"source_type": "scan_export"}}],
              "processed_outputs": []}
    group = {"group_id": "g1", "basis": {"conditions": {"cycling_state": {"kind": "conflicting", "candidate_ids": ["cand-1"]}}},
             "split_reasons": [{"code": "conflicting_condition", "condition": "cycling_state",
                                "readings": ["after1200cycling", "after1200mvcycling"]}]}
    return bundle, group


def test_a_care_flag_raised_only_by_a_merge_file_name_says_it_is_no_reading_of_the_run():
    bundle, group = _old_bundle(merge_witness=True)
    [why] = G.care_reasons(bundle, group)
    assert why["condition"] == "cycling_state" and why["only_a_processed_output_name"] is True
    assert "merge file" in why["why"] and "no reading of the run" in why["why"] and "importing the folder again" in why["why"]
    assert [r["value"] for r in why["readings"]] == ["after1200cycling", "after1200mvcycling"]
    # two readings the run's own files give (its name and its scan header) are a real disagreement: nothing added
    bundle, group = _old_bundle(merge_witness=False)
    [why] = G.care_reasons(bundle, group)
    assert why["only_a_processed_output_name"] is False and "merge file" not in why["why"]
    assert "the file name" in why["why"] and "the scan header" in why["why"]
    assert G.care_reasons(bundle, {"group_id": "g2", "split_reasons": []}) == []


np = pytest.importorskip("numpy", reason="the processing tests need the optional `processing` extra (numpy)")

import test_local_import_engine_xas as T  # noqa: E402
from isaac_api.local_import import cli  # noqa: E402


def test_a_bulk_confirm_names_the_groups_confirmed_with_a_care_flag_and_why(tmp_path, capsys):
    """The SYN scan headers state filter 10; one run's NAME says filter20: its group carries the care flag."""
    runs = [("01_SYN_ZZ1_060mV", 9, [T.scan_cols(10 + k) for k in range(2)]),
            ("02_SYN_ZZ2_filter20_060mV", 11, [T.scan_cols(60 + k) for k in range(2)])]
    bdir, _ = T.imported(tmp_path, runs, process=False)
    b = M.load(bdir)
    flagged = [g for g in b["record_groups"] if G.care_reasons(b, g)]
    assert len(flagged) == 1 and flagged[0]["member_run_keys"][0].startswith("02_SYN_ZZ2_filter20")
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(bdir), *[x for g in b["record_groups"] for x in ("--target", g["group_id"])],
                     "--decision", "confirm", "--by", "SYN Scientist"]) == 0
    said = json.loads(capsys.readouterr().out)
    care = said["confirmed_with_a_care_flag"]
    assert care["groups"] == 1 and care["by_condition"] == {"filter": 1}
    [item] = care["items"]
    assert item["group_id"] == flagged[0]["group_id"] and item["file"] == "02_SYN_ZZ2_filter20_060mV"
    assert "'10'" in item["why"] and "'20'" in item["why"] and "the scan header" in item["why"]
    assert said["statement"].startswith("confirmed for 2 groups.")
    assert "1 of the groups confirmed carry a care flag" in said["statement"] and "02_SYN_ZZ2_filter20_060mV" in said["statement"]
    # a confirm of groups with no flag says nothing more
    other = tmp_path / "plain"
    other.mkdir()
    bdir2, _ = T.imported(other, runs[:1], process=False)
    done = M.decide(bdir2, target_ids=[g["group_id"] for g in M.load(bdir2)["record_groups"]], decision="confirm",
                    value=None, **BY)
    assert "confirmed_with_a_care_flag" not in done and "care flag" not in done["statement"]
