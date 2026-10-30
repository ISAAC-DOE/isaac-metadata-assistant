"""`isaac process`: what it refuses, and what `--group` replaces. Synthetic fixture only.

* Without a readable source (no `--source`, no recorded `local_root_hint`, or a folder that holds
  none of the scans) it is REFUSED, exit 2, and nothing is written — it used to exit 0 and store a
  `fail`/`no_readable_scan` verdict for every group.
* `--group ID` replaces only that group's results; every other group's results, decided or not,
  are kept as they were (it used to drop every undecided result of the other groups).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import.processing import run as RUN

SEMANTICS = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
BY = "SYNTHETIC TEST"


def _import(capsys, src: Path, out: Path, *extra: str) -> Path:
    assert cli.main(["import", str(src), "--out", str(out), *extra]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    capsys.readouterr()
    return out


def _tree(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file() and p.name != ".bundle.lock"}


@pytest.fixture()
def bdir(tmp_path, capsys):
    return _import(capsys, SEMANTICS, tmp_path / "bundle")


# --- 1. no reachable source: refused, nothing written -------------------------------------------------


@pytest.mark.parametrize("source", [None, "missing", "elsewhere"])
def test_process_without_a_readable_source_is_refused_and_writes_nothing(bdir, tmp_path, capsys, source):
    before = _tree(bdir)
    argv = ["process", str(bdir)]
    if source == "missing":
        argv += ["--source", str(tmp_path / "no-such-folder")]
    elif source == "elsewhere":  # a real folder, but not the one imported: none of the scans are there
        (tmp_path / "elsewhere").mkdir()
        argv += ["--source", str(tmp_path / "elsewhere")]
    code = cli.main(argv)
    err = capsys.readouterr().err
    assert code == 2
    assert "--source <the beamtime folder you imported>" in err and "nothing was written" in err
    assert _tree(bdir) == before  # no processing/, no results, bundle.json byte-identical
    assert not (bdir / "processing").exists()


def test_a_folder_whose_scans_have_other_bytes_is_refused(bdir, tmp_path, capsys):
    other = tmp_path / "edited"
    shutil.copytree(SEMANTICS, other)
    for p in other.rglob("*"):
        if p.is_file():
            p.write_bytes(p.read_bytes() + b"\n# edited\n")
    assert cli.main(["process", str(bdir), "--source", str(other)]) == 2
    assert "with different bytes than were imported" in capsys.readouterr().err
    assert not (bdir / "processing").exists()


def test_the_recorded_local_root_is_used_while_it_still_exists(tmp_path, capsys, monkeypatch):
    src = tmp_path / "beamtime"
    shutil.copytree(SEMANTICS, src)
    b = _import(capsys, src, tmp_path / "bundle", "--record-local-root")
    seen = {}

    def fake(bundle_dir, **k):
        seen["root"] = k["source_root"]
        return {"status": "processed", "processing_results": [], "summary": {}}

    monkeypatch.setattr(RUN, "process_bundle", fake)
    assert cli.main(["process", str(b)]) == 0
    assert Path(seen["root"]).resolve() == src.resolve()
    shutil.rmtree(src)  # the folder moved: the hint no longer reaches the scans
    capsys.readouterr()
    assert cli.main(["process", str(b)]) == 2
    assert "local_root_hint" in capsys.readouterr().err


# --- 2. --group replaces only that group's results ----------------------------------------------------


def _fake_process_bundle(tag: dict):
    def fake(bundle_dir, *, group_ids=None, bundle=None, **_k):
        gids = [g["group_id"] for g in bundle["record_groups"] if not group_ids or g["group_id"] in group_ids]
        return {"status": "processed", "summary": {}, "processing_results": [
            {"result_id": f"proc-{g}-r-{tag['run']}-isaac", "group_id": g, "protocol_id": "isaac.xas.v0",
             "protocol_version": "0.1", "protocol_status": "draft_unreviewed", "source": "isaac_protocol",
             "inputs": [], "steps": [], "outputs": {"files": [], "e0_eV": None, "edge_step": None, "points": None},
             "qc": {"metrics": {}, "verdict": "warn"}, "comparison": None, "state": "needs_review"} for g in gids]}
    return fake


def test_process_group_replaces_only_that_groups_results(bdir, capsys, monkeypatch):
    tag = {"run": "a"}
    monkeypatch.setattr(RUN, "process_bundle", _fake_process_bundle(tag))
    assert cli.main(["process", str(bdir), "--source", str(SEMANTICS)]) == 0
    capsys.readouterr()
    first = {r["group_id"]: r for r in M.load(bdir)["processing_results"]}
    assert len(first) == 9
    g1, g2 = sorted(first)[:2]

    tag["run"] = "b"
    assert cli.main(["process", str(bdir), "--source", str(SEMANTICS), "--group", g1]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["new"] == 1 and out["kept_other_groups"] == 8 and out["processing_results"] == 9
    after = {r["group_id"]: r for r in M.load(bdir)["processing_results"]}
    assert set(after) == set(first)  # 9 -> 9, not 9 -> 1
    assert after[g1]["result_id"] == f"proc-{g1}-r-b-isaac"  # that group's result replaced
    assert all(after[g] == first[g] for g in first if g != g1)  # the others untouched

    tag["run"] = "c"
    assert cli.main(["process", str(bdir), "--source", str(SEMANTICS), "--group", g1, "--group", g2]) == 0
    capsys.readouterr()
    final = {r["group_id"]: r for r in M.load(bdir)["processing_results"]}
    assert len(final) == 9 and final[g1]["result_id"].endswith("-r-c-isaac") and final[g2]["result_id"].endswith("-r-c-isaac")
    assert cli.main(["bundle", "check", str(bdir)]) == 0


def test_process_group_keeps_a_rejected_result_of_another_group(bdir, capsys, monkeypatch):
    tag = {"run": "a"}
    monkeypatch.setattr(RUN, "process_bundle", _fake_process_bundle(tag))
    assert cli.main(["process", str(bdir), "--source", str(SEMANTICS)]) == 0
    first = {r["group_id"]: r for r in M.load(bdir)["processing_results"]}
    g1, g2 = sorted(first)[:2]
    M.decide(bdir, target_ids=[first[g2]["result_id"]], decision="reject", value=None, by=BY, orcid=None)
    tag["run"] = "b"
    capsys.readouterr()
    assert cli.main(["process", str(bdir), "--source", str(SEMANTICS), "--group", g1]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kept_decided"] == 1 and out["kept_other_groups"] == 7 and out["new"] == 1
    after = {r["group_id"]: r for r in M.load(bdir)["processing_results"]}
    assert len(after) == 9 and after[g2]["result_id"] == first[g2]["result_id"] and after[g2]["state"] == "rejected"


# --- the real protocol (numpy + xraylarch): an approval stays bound to the result it named -----------


def test_real_process_group_keeps_other_groups_and_an_approval_stays_bound(bdir, tmp_path, capsys):
    pytest.importorskip("numpy")
    pytest.importorskip("larch")
    src = str(SEMANTICS)
    assert cli.main(["process", str(bdir), "--source", src]) == 0
    first = {r["group_id"]: r for r in M.load(bdir)["processing_results"] if r["source"] == "isaac_protocol"}
    assert len(first) == 9
    g1, g2 = sorted(first)[:2]
    approved = first[g1]["result_id"]
    M.decide(bdir, target_ids=[approved], decision="approve", value=None, by=BY, orcid=None, qc_status="valid")

    # another group re-processed: the approved result and the 7 untouched groups are kept
    capsys.readouterr()
    assert cli.main(["process", str(bdir), "--source", src, "--group", g2]) == 0
    after = {r["result_id"]: r for r in M.load(bdir)["processing_results"]}
    assert {r["group_id"] for r in after.values()} == set(first) and after[approved]["state"] == "scientist_confirmed"

    # the approved group re-processed with the SAME inputs: same result id, the approval is kept, no duplicate
    assert cli.main(["process", str(bdir), "--source", src, "--group", g1]) == 0
    same = [r for r in M.load(bdir)["processing_results"] if r["group_id"] == g1 and r["source"] == "isaac_protocol"]
    assert [r["result_id"] for r in same] == [approved] and same[0]["state"] == "scientist_confirmed"

    # with DIFFERENT parameters: a new, undecided result beside the approved one, which is not moved
    params = tmp_path / "p.json"
    params.write_text(json.dumps({"normalize": {"pre2": -40.0}}))
    assert cli.main(["process", str(bdir), "--source", src, "--group", g1, "--params-file", str(params)]) == 0
    both = {r["result_id"]: r["state"] for r in M.load(bdir)["processing_results"] if r["group_id"] == g1 and r["source"] == "isaac_protocol"}
    assert both[approved] == "scientist_confirmed" and len(both) == 2
    assert [s for rid, s in both.items() if rid != approved] == ["needs_review"]
    assert len({r["group_id"] for r in M.load(bdir)["processing_results"]}) == 9
    assert cli.main(["bundle", "check", str(bdir)]) == 0
