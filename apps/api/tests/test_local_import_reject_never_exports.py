"""A value a scientist REJECTS on the Local Imports page (or with ``isaac bundle decide --decision
reject``) never reaches the draft, the record ``export`` composes, or its evidence sidecar — even
when the reject comes after a confirm or a correction that had put a value there.

The local path stores a reject as a decision; ``bundle.derive_value_state`` makes the value
``rejected``, so it is not eligible, and ``bundle.final_value`` gives it no value. This pins that
so the truth-plane rule (``isaac_records.export``: a ``rejected`` envelope is never written) holds
on this path too. SYNTHETIC files only (the grouping CLI fixture).
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R
from isaac_records.export import build_sidecar

from test_local_import_grouping_cli import FIXTURE, _folder

PH = "context.electrochemistry.pH"
BY = dict(by="SYNTHETIC TEST", orcid=None)


@pytest.fixture()
def confirmed(tmp_path):
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert cli.main(["import", str(src), "--out", str(b)]) == 0
    M.group(b)
    gid = M.load(b)["record_groups"][0]["group_id"]
    M.decide(b, target_ids=[gid], decision="confirm", value=None, **BY)
    bd = M.load(b)
    keys = set(bd["record_groups"][0]["member_run_keys"])
    runs = {r["run_id"] for r in bd["runs"] if r["run_key"] in keys}
    cid = next(c["candidate_id"] for c in bd["candidates"] if c["target_field_path"] == PH and c["run_id"] in runs)
    return b, gid, cid


def _composed(b, gid):
    """What ``validate`` and ``export`` would write for the group: its draft, record and sidecar."""
    R.build_records(b)
    disk = json.loads((b / R.DRAFTS_DIR / f"{gid}.draft.json").read_text())
    _, draft, comp = next(x for x in R.fresh_compositions(b, R.load_validated(b)) if x[0] == gid)
    record = R.compose_record(draft, comp, record_id="0" * 26, now="2099-01-01T00:00:00Z")
    return disk, record, build_sidecar(dict(draft), record)


@pytest.mark.parametrize("before", [("confirm", None), ("correct", 3)])
def test_a_rejected_value_never_reaches_the_draft_record_or_sidecar(confirmed, before):
    b, gid, cid = confirmed
    M.decide(b, target_ids=[cid], decision=before[0], value=before[1], **BY)
    draft, record, sidecar = _composed(b, gid)
    assert PH in draft["fields"]  # the confirmed (or corrected) value is composed ...
    assert record["context"]["electrochemistry"]["pH"] == draft["fields"][PH]["value"]

    M.decide(b, target_ids=[cid], decision="reject", value=None, **BY)
    draft, record, sidecar = _composed(b, gid)
    assert PH not in draft["fields"]  # ... and the reject removes it everywhere
    assert "pH" not in ((record.get("context") or {}).get("electrochemistry") or {})
    assert PH not in sidecar["evidence"]
    assert all(env.get("status") != "rejected" for env in draft["fields"].values())
