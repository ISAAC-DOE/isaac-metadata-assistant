"""SPEC ``#C`` lines are an event log, and a read-back position equal to the commanded one within motor resolution is
one position (bundle 1.15.0; audit of 18 Nov 2026, rule 2). SYNTHETIC files only.

On real beamtimes every SPEC run carried a "which reading is right?" question about its comment lines (``do
run3.mac`` beside ``do Pt_XAS.mac`` beside ``spec User = ...``) and about a motor the macro moved to ``-21.2782``
that the header reads back as ``-21.27825``. What these pin:

* two comment lines of different kinds, or two events, are no conflict: the candidate keeps its id and its readings
  as evidence and says why (``isaac.import.comment_lines_are_events.v1``); two different session lines still are;
* positions within 1e-3 of the motor's unit are one position (``isaac.import.position_within_motor_resolution.v1``);
  a position further away (another spot) is still a disagreement;
* every other conflict keeps the id an import without these rules gave it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_quick_merges import _spec_run  # noqa: E402

USER = "#C spec  User = synthetic"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def _edit(bt: Path, stem: str, old: str, new: str) -> None:
    for p in (bt / stem, bt / f"{stem}_dir" / stem):
        p.write_text(p.read_text().replace(old, new))


def _beamtime(root: Path) -> Path:
    bt = root / "SYN_BL00_2100-27_Events"
    for stem in ("SYN_cat_events", "SYN_cat_users", "SYN_cat_near", "SYN_cat_far"):
        _spec_run(bt, stem)
    _edit(bt, "SYN_cat_events", USER, USER + "\n#C Mon Sep  9 01:46:41 2001.  do run9.mac.\n"
                                            "#C Mon Sep  9 01:46:42 2001.  gap reset from 7.47 to 7.46.")
    _edit(bt, "SYN_cat_users", USER, USER + "\n#C spec  User = another")  # two session lines: a real disagreement
    # the macros move Sx before declaring the run; the header reads Sx back as -1.25
    (bt / "run1.mac").write_text("mv Sx -1.2504\nnewfile SYN_cat_near\n")
    (bt / "run2.mac").write_text("mv Sx 4.5\nnewfile SYN_cat_far\n")
    (bt / "run9.mac").write_text("newfile SYN_cat_events\nnewfile SYN_cat_users\n")
    return bt


def _import(src: Path, out: Path) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    b = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(b) == []
    return b


def _conflicts(b: dict, stem: str, key: str) -> list[dict]:
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == stem)
    keys = {c["candidate_id"]: c["statement_key"] for c in b["candidates"]}
    return [c for c in b["conflicts"] if rid in c["run_ids"] and keys.get(c.get("candidate_id")) == key]


def _cand(b: dict, stem: str, key: str) -> dict:
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == stem)
    [c] = [c for c in b["candidates"] if c["run_id"] == rid and c["statement_key"] == key]
    return c


def test_comment_lines_are_events_and_positions_within_resolution_are_one(tmp_path, capsys):
    b = _import(_beamtime(tmp_path / "src"), tmp_path / "out")
    assert _conflicts(b, "SYN_cat_events", "spec_user_string") == []
    events = _cand(b, "SYN_cat_events", "spec_user_string")
    assert B.COMMENT_EVENT_RULE_ID in events["state_basis"]["not_proposable_reason"]
    assert "do run9.mac" in json.dumps(events["evidence"])  # the readings stay evidence
    assert len(_conflicts(b, "SYN_cat_users", "spec_user_string")) == 1  # two session lines still disagree
    assert _conflicts(b, "SYN_cat_near", "sample_position") == []
    near = _cand(b, "SYN_cat_near", "sample_position")
    assert B.POSITION_RESOLUTION_RULE_ID in near["state_basis"]["not_proposable_reason"]
    assert len(_conflicts(b, "SYN_cat_far", "sample_position")) == 1  # 4.5 against -1.25: another spot
    assert b["counts"][B.NOT_A_CONFLICT_COUNT] == 2


@pytest.mark.parametrize("key,readings,rule", [
    ("spec_user_string", ["Wed May 01 17:41:54 2019.  do run3.mac.", "spec  User = SYN"], B.COMMENT_EVENT_RULE_ID),
    ("spec_user_string", ["Fri Apr 11 12:11:46 2025.  gap reset from 7.47 to 7.46.", "Fri Apr 11 12:12:00 2025.  do a.mac."],
     B.COMMENT_EVENT_RULE_ID),
    ("spec_user_string", ["spec  User = SYN", "spec  User = ZZ"], None),
    # review of PR 346, I2: only the event verbs are events; any other dated line is still a reading
    ("spec_user_string", ["Mon Sep  9 01:46:41 2001.  potential set to 1.2 V", "Mon Sep  9 02:46:41 2001.  potential set to 0.4 V"], None),
    ("spec_user_string", ["Mon Sep  9 01:46:41 2001.  changed sample to SYN_B", "Mon Sep  9 02:46:41 2001.  changed sample to SYN_C"], None),
    ("spec_user_string", ["Mon Sep  9 01:46:41 2001.  do run3.mac.", "Mon Sep  9 01:47:00 2001.  Sx reset from 1.2 to 1.25.",
                          "spec  User = SYN"], B.COMMENT_EVENT_RULE_ID),
    ("sample_position", ["Sx -21.2782", "Sx -21.27825"], B.POSITION_RESOLUTION_RULE_ID),
    ("sample_position", ["Sx 21.1537", "Sx 21.15375", "Sz 30.4142", "Sz 30.41425"], B.POSITION_RESOLUTION_RULE_ID),
    ("sample_position", ["Sz 30.4142", "Sz 30.43925"], None),
    # the whole spread counts, never a chain of small steps (review of PR 346)
    ("sample_position", ["Sx 1.0000", "Sx 1.0009", "Sx 1.0018", "Sx 1.0027", "Sx 1.0036"], None),
    ("motor_position", ["11215.198", "9174.8014"], None),  # no motor named: compared as the engine compared it
    ("counting_time", ["0.2  (Seconds)", "1  (Seconds)"], None),
])
def test_what_is_not_a_conflict(key, readings, rule):
    assert B.not_a_conflict(key, readings) == rule


def test_every_other_conflict_keeps_its_id(tmp_path, capsys, monkeypatch):
    src = _beamtime(tmp_path / "src")
    now = _import(src, tmp_path / "now")
    with monkeypatch.context() as mp:
        mp.setattr(B, "not_a_conflict", lambda *a, **k: None)
        before = _import(src, tmp_path / "before")
    was = {c["conflict_id"]: (c["kind"], c["subject"], c.get("candidate_id")) for c in before["conflicts"]}
    assert len(now["conflicts"]) == len(was) - 2
    for c in now["conflicts"]:
        assert was[c["conflict_id"]] == (c["kind"], c["subject"], c.get("candidate_id"))
    assert [c["candidate_id"] for c in now["candidates"]] == [c["candidate_id"] for c in before["candidates"]]
