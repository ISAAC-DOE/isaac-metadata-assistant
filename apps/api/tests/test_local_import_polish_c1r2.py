"""Skill polish, cycle 1 review round 2: judging "blocking" by the record composer costs one composition per live
group per page, not (groups x decisions) twice. SYNTHETIC fixtures only.

* ``questions.consolidate`` composes each live group ONCE and reads the whole decision log a fixed number of
  times, however many groups and decisions the bundle holds (``records.composition_index`` is built once per
  consolidation and passed to every ``records.compose_group`` call).
* ``minimum_answers_for_one_group`` reuses the reports ``consolidate`` composed (``compositions_out`` /
  ``reports``) and composes again only a group whose approved processing result it must read from disk; the
  answer is the same as composing everything itself.
* ``compose_group`` with the index is the same draft and report as without it.
* The web progress and questions pages compose each live group once per view.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import bundle as B
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from tests_support_records import BY, fake_upstream_env, pristine_bundle  # noqa: F401


@pytest.fixture()
def grouped(pristine_bundle, tmp_path, fake_upstream_env):  # noqa: F811
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    return bdir


def _spectrum(bdir: Path, gid: str) -> dict:
    gdir = bdir / "processing" / gid
    gdir.mkdir(parents=True, exist_ok=True)
    spec = gdir / "normalized.csv"
    spec.write_text("# synthetic\nenergy_eV,norm,flat\n" + "\n".join(f"{1000 + 5 * i},{i / 20:.3f},{i / 20:.3f}" for i in range(21)) + "\n")
    return {"role": "normalized", "relative_path": f"processing/{gid}/normalized.csv", "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}


def _result(gid: str, files, verdict="pass", reasons=None) -> dict:
    return {"result_id": f"p-{gid}", "group_id": gid, "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
            "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [], "steps": [],
            "outputs": {"files": list(files), "e0_eV": 1050.0 if files else None, "edge_step": 1.0 if files else None,
                        "points": 21 if files else None},
            "qc": {"metrics": {}, "verdict": verdict, **({"reasons": reasons} if reasons else {})},
            "comparison": None, "state": "candidate_extracted"}


@pytest.fixture()
def processed(grouped):
    """Live group 0 confirmed with an APPROVED curve, group 1 an approvable curve that failed QC, group 2 a
    result with no curve, group 3 rejected; answers given for a few values."""
    b = M.load(grouped)
    live = Q.live_groups(b)
    b["processing_results"] = [_result(live[0]["group_id"], [_spectrum(grouped, live[0]["group_id"])]),
                               _result(live[1]["group_id"], [_spectrum(grouped, live[1]["group_id"])], "fail", ["synthetic"]),
                               _result(live[2]["group_id"], [], "fail", ["too_few_common_points"])]
    M.save_bundle(grouped, b)
    M.decide(grouped, target_ids=[live[0]["group_id"]], decision="confirm", value=None, **BY)
    M.decide(grouped, target_ids=[f"p-{live[0]['group_id']}"], decision="approve", value=None, qc_status="valid", **BY)
    M.decide(grouped, target_ids=[live[3]["group_id"]], decision="reject", value=None, **BY)
    for m in [m for m in b["missing_values"] if m["target_field_path"] == "sample.sample_form"][:3]:
        M.decide(grouped, target_ids=[m["value_id"]], decision="correct", value="powder", **BY)
    return grouped


def _scaled(b: dict, copies: int, decisions: int = 0) -> dict:
    """``b`` with every run, value and group copied ``copies`` times (synthetic ids), plus ``decisions`` deferrals."""
    out = copy.deepcopy(b)
    for k in range(1, copies):
        sfx = f"-x{k}"
        for r in b["runs"]:
            out["runs"].append({**copy.deepcopy(r), "run_id": r["run_id"] + sfx, "run_key": r["run_key"] + sfx})
        for c in b["candidates"]:
            out["candidates"].append({**copy.deepcopy(c), "candidate_id": c["candidate_id"] + sfx,
                                      "run_id": c["run_id"] and c["run_id"] + sfx})
        for m in b["missing_values"]:
            if m["run_id"] is not None:
                out["missing_values"].append({**copy.deepcopy(m), "value_id": m["value_id"] + sfx, "run_id": m["run_id"] + sfx})
        for g in b["record_groups"]:
            out["record_groups"].append({**copy.deepcopy(g), "group_id": g["group_id"] + sfx,
                                         "member_run_keys": [x + sfx for x in g["member_run_keys"]]})
    cids = [c["candidate_id"] for c in out["candidates"]]
    for n in range(decisions):
        out["scientist_decisions"].append({"decision_id": f"d-{10_000 + n}", "decision": "defer", "value": None,
                                           "target": {"kind": "candidate", "id": cids[n % len(cids)]},
                                           "by": {"name": "Synthetic Scientist"}, "decided_utc": "2099-01-01T00:00:00Z"})
    return out


class _Counted:
    """Counts the calls of ``records.compose_group`` and ``bundle._decisions_by_target`` (a whole-log read)."""

    def __init__(self, monkeypatch):
        self.compose = self.log_reads = 0
        compose, by_target = R.compose_group, B._decisions_by_target

        def counted_compose(*a, **k):
            self.compose += 1
            return compose(*a, **k)

        def counted_reads(*a, **k):
            self.log_reads += 1
            return by_target(*a, **k)

        monkeypatch.setattr(R, "compose_group", counted_compose)
        monkeypatch.setattr(B, "_decisions_by_target", counted_reads)

    def reset(self):
        self.compose = self.log_reads = 0


def _dump(x) -> str:
    return json.dumps(x, sort_keys=True)


# --- the cost: one composition per live group, a fixed number of whole-log reads ---------------


def test_consolidate_composes_each_live_group_once_and_reads_the_decision_log_a_fixed_number_of_times(grouped, monkeypatch):
    """Before (commit 675419d9): every group's composition re-read the whole decision log, and the minimum composed
    every group again: 135 groups / 20k decisions took ~1.9 s + ~1.9 s, 540 groups ~8 s + ~9 s. The bound is a COUNT,
    not a clock: compositions = live groups, whole-log reads the same at 1x and 10x."""
    counted = _Counted(monkeypatch)
    reads = {}
    for copies in (1, 10):
        big = _scaled(M.load(grouped), copies, decisions=200 * copies)
        live = len(Q.live_groups(big))
        counted.reset()
        reports: dict = {}
        payload = Q.consolidate(big, compositions_out=reports)
        assert counted.compose == live and set(reports) == {g["group_id"] for g in Q.live_groups(big)}
        Q.minimum_answers_for_one_group(payload, big, bundle_dir=grouped, reports=reports)
        assert counted.compose == live, "the minimum composed again what consolidate already had"
        reads[copies] = counted.log_reads
    assert reads[1] == reads[10] <= 8, reads


def test_the_minimum_composes_again_only_a_group_whose_approved_processing_it_reads(processed, monkeypatch):
    b = M.load(processed)
    live = Q.live_groups(b)
    counted = _Counted(monkeypatch)
    reports: dict = {}
    payload = Q.consolidate(b, compositions_out=reports)
    counted.reset()
    Q.minimum_answers_for_one_group(payload, b, bundle_dir=processed, reports=reports)
    assert counted.compose == 1  # live group 0: its approved curve, QC status and outputs come from disk
    counted.reset()
    Q.minimum_answers_for_one_group(payload, b, reports=reports)  # no processing file read: nothing to compose
    assert counted.compose == 0
    counted.reset()
    Q.minimum_answers_for_one_group(payload, b, scope=f"group:{live[1]['group_id']}", bundle_dir=processed,
                                    reports={k: v for k, v in reports.items() if k != live[1]["group_id"]})
    assert counted.compose == 1  # a group the reports lack is composed here


# --- the same answers ---------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["grouped", "processed"])
def test_the_minimum_from_consolidates_reports_is_the_same_as_composing_everything(which, request):
    bdir = request.getfixturevalue(which)
    b = M.load(bdir)
    plain = Q.consolidate(b)
    reports: dict = {}
    payload = Q.consolidate(b, compositions_out=reports)
    assert _dump(payload) == _dump(plain)  # filling compositions_out changes nothing in the payload
    scopes = [None, "experiment"] + [f"group:{g['group_id']}" for g in Q.live_groups(b)]
    for scope in scopes:
        for where in (None, bdir):
            assert (_dump(Q.minimum_answers_for_one_group(payload, b, scope=scope, bundle_dir=where, reports=reports))
                    == _dump(Q.minimum_answers_for_one_group(plain, b, scope=scope, bundle_dir=where))), (scope, where)


def test_compose_group_with_the_index_is_the_same_draft_and_report(processed):
    b = M.load(processed)
    index = R.composition_index(b)
    assert any(g["status"] == "scientist_confirmed" for g in b["record_groups"])
    for g in b["record_groups"]:
        assert _dump(R.compose_group(b, g, processed, index)) == _dump(R.compose_group(b, g, processed)), g["group_id"]


def test_a_candidate_governed_by_its_own_and_its_conflicts_decision_takes_the_later_one(grouped):
    """``bundle.candidate_decision`` with the indexes a caller built once is the same decision as without them,
    including when both the candidate and its conflict were decided (the later one governs)."""
    b = M.load(grouped)
    conflict = next(cf for cf in b["conflicts"] if cf.get("candidate_id"))
    cand = next(c for c in b["candidates"] if c["candidate_id"] == conflict["candidate_id"])
    first = {"decision_id": "d-1", "target": {"kind": "candidate", "id": cand["candidate_id"]}, "decision": "defer"}
    later = {"decision_id": "d-2", "target": {"kind": "conflict", "id": conflict["conflict_id"]}, "decision": "defer"}
    for log in ([first, later], [later, first], [first], []):
        bb = {**b, "scientist_decisions": log}
        plain = B.candidate_decision(bb, cand)
        indexed = B.candidate_decision(bb, cand, B._decisions_by_target(log), B.conflict_ids_by_candidate(bb))
        assert indexed is plain
        assert plain is (log[-1] if log else None)


# --- the web pages: one composition per live group per view -------------------------------------


@pytest.fixture()
def client(tmp_path, grouped, monkeypatch):
    r = tmp_path / "bundles"
    r.mkdir()
    shutil.copytree(grouped, r / "alpha")
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(r))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    return TestClient(create_app(), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123),
                      headers={LB.LOCAL_HEADER: "1"})


@pytest.mark.parametrize("page", ["progress", "questions"])
def test_each_web_view_composes_each_live_group_once(client, grouped, monkeypatch, page):
    live = len(Q.live_groups(M.load(grouped)))
    # the first questions view records the exposures it shows, and that save rewrites questions.json from the
    # changed bundle (one more consolidation, as every save does); a view with nothing new to record saves nothing
    client.get(f"/api/local-bundles/alpha/{page}")
    counted = _Counted(monkeypatch)
    r = client.get(f"/api/local-bundles/alpha/{page}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body.get("minimum_for_one_group") or body.get("progress", {}).get("minimum_for_one_group")) is not None
    assert counted.compose == live
