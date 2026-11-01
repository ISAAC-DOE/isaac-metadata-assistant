"""Polish c12-q: walkthrough findings on a real BL15-2 beamtime, reproduced here. SYNTHETIC files only (the committed
multi-operator corpus, whose file names state ``100mV``; hand-made groups and processing results).

* (MED-1) A DEAD END: a potentiostatic group whose set-point is CONFIRMED but whose potential scale is unknown. The
  set-point composes only beside its scale (``bundle.COMPOSES_ONLY_WITH``), so the composer held it back and then
  listed the SET-POINT as missing; the minimum sent the scientist to ``decide --target <set-point> --decision correct``
  (answering it again changes nothing), the scale question stayed optional, and the stated-potential warning vanished
  (the set-point's ``missing`` placeholder counted as "carried"). Now the missing item is the SCALE: the composer
  lists it (with why), ``validate`` and the minimum name it and its question's command, that question blocks the
  group, the set-point is not listed as missing, and the warning stays. Confirm set-point -> the minimum names the
  scale -> answer the scale -> exportable.
* (LOW) An exported record's descriptor notes never carry the internal group id or the flag code
  ``scientist_selected_subset_of_scans``: plain words only, and the record stays valid.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import portal as P
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, _decide_everything, _miss, _portal, bdir, fake_upstream, pristine)

POT = "context.electrochemistry.potential_setpoint_V"
SCALE = "context.electrochemistry.potential_scale"
CM = B.CONTROL_MODE_PATH
REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / ".claude" / "skills" / "isaac-historical-import"


def _potentiostatic(bdir: Path, *, confirm_setpoint: bool = True, decided: bool = False) -> None:
    if not decided:
        _decide_everything(bdir)
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, CM, "run-001")], decision="correct", value="potentiostatic", **BY)
    if confirm_setpoint:
        M.decide(bdir, target_ids=[_cand(b, POT, "run-001")["candidate_id"]], decision="confirm", value=None, **BY)


def _scale_question_id(bdir: Path) -> str:
    [q] = [q for q in Q.consolidate(M.load(bdir))["questions"]
           if q["kind"] == "optional_values" and SCALE in (q.get("fields") or {}) and q["scope"] == "group:g1"]
    return q["question_id"]


def _questions(bdir: Path, capsys) -> dict:
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(bdir), "--scope", "group:g1", "--blocking-only"]) == 0
    return json.loads(capsys.readouterr().out)


def _validate(bdir: Path, monkeypatch, capsys) -> tuple[dict, dict]:
    monkeypatch.setattr(P, "run_portal_check", _portal("publish"))
    capsys.readouterr()
    assert cli.main(["bundle", "validate", str(bdir)]) in (0, 1)
    out = json.loads(capsys.readouterr().out)
    return out, json.loads((bdir / "validation" / "g1.json").read_text())


# --- MED-1: a confirmed set-point held back by a missing scale names the SCALE --------------------------------------


def test_the_composer_lists_the_scale_not_the_confirmed_setpoint(bdir):
    _potentiostatic(bdir)
    draft, report = R.compose_group(M.load(bdir), next(g for g in M.load(bdir)["record_groups"] if g["group_id"] == "g1"),
                                    bdir)
    missing = {m["path"]: m for m in report["missing_required"]}
    assert POT not in missing and SCALE in missing
    assert missing[SCALE]["from"] == R.FROM_AN_ANSWER
    assert "0.1 V" in missing[SCALE]["required_because"] and POT in missing[SCALE]["required_because"]
    assert POT not in draft["fields"] and draft["fields"][SCALE] == {"value": None, "status": "missing", "evidence": []}
    # the set-point stays where it was: confirmed, held back by the gate, said
    assert any(n.get("path") == POT and n["reason"] == R.SETPOINT_NEEDS_SCALE for n in report["not_composed"])
    # the warning that the record will not carry the stated potential stays, naming the scale
    [w] = [w for w in report["warnings"] if w["code"] == R.STATED_POTENTIAL_WARNING]
    assert w["needs"] == SCALE and "until the potential scale is confirmed" in w["text"]


def test_negative_control_an_unanswered_setpoint_is_still_the_missing_item(bdir):
    _potentiostatic(bdir, confirm_setpoint=False)
    draft, report = R.compose_group(M.load(bdir), next(g for g in M.load(bdir)["record_groups"] if g["group_id"] == "g1"),
                                    bdir)
    paths = [m["path"] for m in report["missing_required"]]
    assert POT in paths and SCALE not in paths
    assert draft["fields"][POT]["status"] == "missing"


def test_the_whole_loop_confirm_setpoint_then_the_minimum_names_the_scale_then_exportable(bdir, monkeypatch, capsys):
    _decide_everything(bdir)
    scale_qid = _scale_question_id(bdir)  # its id before the mode and the set-point are decided: it must not change
    assert not next(q for q in Q.consolidate(M.load(bdir))["questions"] if q["question_id"] == scale_qid)["blocking"]
    _potentiostatic(bdir, decided=True)
    assert _scale_question_id(bdir) == scale_qid

    out, report = _validate(bdir, monkeypatch, capsys)
    assert report["verdict"] == "incomplete" and report["missing_required"] == [SCALE]
    assert out["missing_required_by_field"] == {SCALE: 1}
    [w] = report["warnings"]
    assert w["code"] == R.STATED_POTENTIAL_WARNING and w["needs"] == SCALE
    assert f"--question {scale_qid} --field {SCALE}" in w["command"]

    qs = _questions(bdir, capsys)
    listed = {q["question_id"]: q for q in qs["questions"]}
    assert scale_qid in listed and listed[scale_qid]["blocking"] is True
    assert SCALE in listed[scale_qid]["required_fields"] and "0.1 V" in listed[scale_qid]["why"]
    minimum = qs["minimum_for_one_group"]
    assert minimum["group_id"] == "g1" and minimum["unasked_required"] == []
    assert minimum["missing_required_now"] == [SCALE]
    [entry] = minimum["questions"]
    assert entry["question_id"] == scale_qid and entry["fields"] == [SCALE]
    assert POT in entry["required_because"][SCALE]
    assert f"--question {scale_qid} --field {SCALE}" in entry["command"]
    # never also "recommended, not blocking": it is asked above, blocking
    assert scale_qid not in {r["question_id"] for r in minimum.get("recommended") or ()}
    assert not any(f"--target {_cand(M.load(bdir), POT, 'run-001')['candidate_id']}" in str(x) for x in qs.values())

    # answer the scale with the command the minimum named: the record is exportable and carries the set-point
    argv = shlex.split(entry["command"].replace("<bundle_dir>", str(bdir)).replace("<value>", "RHE")
                       .replace("<one of its allowed values>", "RHE").replace("<your name>", "Synthetic Scientist"))
    assert argv[0] == "isaac"
    capsys.readouterr()
    assert cli.main(argv[1:]) == 0
    R.build_records(bdir)
    out, report = _validate(bdir, monkeypatch, capsys)
    assert report["verdict"] == "exportable", report["missing_required"]
    assert report["warnings"] == []
    b = M.load(bdir)
    draft, _ = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    assert draft["fields"][POT]["value"] == 0.1 and draft["fields"][SCALE]["value"] == "RHE"
    assert _questions(bdir, capsys)["minimum_for_one_group"].get("questions", []) == []


def test_the_skill_reference_says_the_scale_is_named(bdir):
    text = (SKILL / "reference" / "records-and-validation.md").read_text()
    assert "the scale is listed as missing" in text


# --- LOW: plain words in an exported record's notes ------------------------------------------------------------------


def test_an_exported_records_notes_carry_no_group_id_and_no_flag_code(bdir, tmp_path):
    from test_local_import_polish_c4a import _add_athena, _approve, _exported

    _decide_everything(bdir)
    _add_athena(bdir)
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)
    _approve(bdir, "p2")
    record = _exported(bdir, tmp_path)
    [out] = record["descriptors"]["outputs"]
    notes = out["generated_by"]["notes"]
    assert "uses only scans 2, 3 of the 3 scan(s)" in notes  # the subset is still said
    assert M.SCAN_SUBSET_FLAG not in notes and not re.search(r"\bg1\b", notes)
    assert "The scientist's Athena curve uses only scans 2, 3" in notes


def test_the_plain_note_drops_every_group_id_and_the_code():
    gid = "rg-ababd9e41f4fce53"
    for raw in (f"The scientist's Athena curve for group {gid} names scan(s) 2468, which … ({M.SCAN_SUBSET_FLAG}): its E0.",
                f"The scientist's Athena curve for group {gid} uses only scans 1, 3 ({M.SCAN_SUBSET_FLAG}): its E0."):
        plain = R.plain_record_note(raw, gid)
        assert gid not in plain and M.SCAN_SUBSET_FLAG not in plain and "group" not in plain
        assert plain.startswith("The scientist's Athena curve ") and plain.endswith(": its E0.")
