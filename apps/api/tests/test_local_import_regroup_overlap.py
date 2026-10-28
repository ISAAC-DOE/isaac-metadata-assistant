"""`isaac bundle group --regroup` keeps a scientist's decided group, and no run may then sit in
that kept group AND a fresh proposal (independent review of 05e11c2e, measured here).

Scenario, all SYNTHETIC (reuses the counter-question CLI test's folder): two single-run groups;
the scientist confirms one; then answers the counter question, which would merge the two runs;
`--regroup` must not propose a fresh group that contains the confirmed group's run.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_grouping_cli import FIXTURE, _folder, _run


def _memberships(bundle: dict) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for g in bundle["record_groups"]:
        for rk in g["member_run_keys"]:
            seen.setdefault(rk, []).append(g["group_id"])
    return seen


def test_regroup_never_puts_a_kept_groups_run_in_a_fresh_group(tmp_path, capsys):
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    first = M.load(b)["record_groups"][0]
    grouped_before = set(_memberships(M.load(b)))
    assert len(first["member_run_keys"]) == 1 and len(grouped_before) == 2
    M.decide(b, target_ids=[first["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions", "--positions", "2", "--by", "SYNTHETIC TEST"], capsys)[0] == 0
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    after = json.loads((b / "bundle.json").read_text())
    doubled = {rk: gids for rk, gids in _memberships(after).items() if len(gids) > 1}
    assert doubled == {}
    kept = next(g for g in after["record_groups"] if g["group_id"] == first["group_id"])
    assert kept["status"] == "scientist_confirmed" and kept["member_run_keys"] == first["member_run_keys"]
    # and nothing went missing: the same runs are grouped as before the regroup
    assert set(_memberships(after)) == grouped_before
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0
