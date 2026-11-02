"""r6h: fixes found by reading real beamtime walks. SYNTHETIC only: every name, run, record and value below is invented.

* H1   ``export`` and ``upload --dry-run`` print, by default, every refused, withdrawn, replaced or restored row and
       every row with something of its own to say, in full; only the repeated "ok" rows are cut to the first three,
       with ``schemas_used`` once at the top; ``--full`` prints every row. ``refused_by_reason`` is always there when a
       group was refused.
* H2   an open ``macro_setpoint_disagrees`` conflict warns ``macro_setpoint_unanswered`` at build-records, validate and
       export (ranked with a value its sources disagree about); a disagreement about anything else sorts before the
       start-time ones in its tier; a set-point question's ``why`` is read from the groups as composed.
* H3   an in-situ record with no electrolyte, cell type or control mode warns, quoting what the file names state, and
       the questions' minimum recommends the question that asks each; nothing is filled.
* H4   a ``decide`` that records nothing writes nothing (and validates nothing); every write that changes something is
       still saved through the full validity check.
* H5   keeping an approved curve that is no longer the chosen Athena version: reject, then approve again (approving it
       again alone records nothing), as the skill now says.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (BY, SEMANTICS, _decide_everything, _miss, _portal, bdir, fake_upstream,  # noqa: F401
                                       pristine)
import test_local_import_polish_r5f as R5F

SKILL = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "isaac-historical-import"
NOTE = "start time left out: the start-time disagreement is unanswered (question {q}; it offers the UTC reading)"
SCHEMAS = {"local_export_target": {"source": "synthetic", "gates": ["official schema"]}, "website_schema": {"gates": []}}


# --- H1 -------------------------------------------------------------------------------------------------------


def _row(i: int, **extra) -> dict:
    return {"group_id": f"g{i}", "record_id": f"01SYNTHETIC{i:014d}", "record": f"01SYNTHETIC{i:014d}.json",
            "sidecar": f"01SYNTHETIC{i:014d}.evidence.json", "artifacts": ["processing/x/merged.csv"],
            "schemas_used": SCHEMAS, "export": "unchanged",
            "statement": "Valid for the portal's pinned schema; NOT claimed valid for the website.",
            "warnings": [f"Written without the start time: {NOTE.format(q=f'Q-{i:010x}')}"], "warnings_total": 1, **extra}


def _refused(i: int) -> dict:
    return {"group_id": f"r{i}", "verdict": "incomplete", "missing_required": ["measurement.series"],
            "processing_blocker": "no_processing_result",
            "summary": ["Draft checks: pass.", f"Missing required values: measurement.series (group r{i}).",
                        "This is NOT an official record until `isaac bundle export` writes one, and nothing has been uploaded."]}


def _export_result(n_ok: int = 10) -> dict:
    exported = [_row(i) for i in range(n_ok)]
    exported.append(_row(90, export="replaced", replaces_record_id="01SYNTHETICOLD0000000000"))
    exported.append(_row(91, warnings=["Written without the potential set-point: a SYNTHETIC note of its own"]))
    exported.append(_row(92, export="unchanged", restored_from_withdrawn=True))
    return {"outcome": "SYNTHETIC outcome.", "records_ready": len(exported), "records_written": 1,
            "records_unchanged": len(exported) - 1, "groups_refused": 5, "exported": exported,
            "refused": [_refused(i) for i in range(5)],
            "withdrawn": [{"group_id": "w1", "record_id": "01SYNTHETICWITHDRAWN00000", "withdrawn_files": [], "reason": "r"}],
            "on_disk_drafts_ignored_because_they_differ": [], "on_disk_drafts_ignored_with_no_confirmed_group": [],
            "warnings_by_text": [{"text": "Written without the start time: …", "records": n_ok + 3, "example_question": "Q-0000000001"}]}


def test_the_default_export_lists_every_row_with_something_to_say_and_cuts_only_repeated_ok_rows():
    out = cli.compact_export(_export_result(10))
    assert list(out)[0] == "outcome"
    ids = [r["group_id"] for r in out["exported"]]
    assert ids == ["g0", "g1", "g2", "g90", "g91", "g92"]  # the first three ok rows, then every other one, in order
    assert out["exported_omitted"] == 7 and out["exported_shown"] == 6 and "--full" in out["exported_full_list"]
    assert out["exported"][3]["replaces_record_id"] == "01SYNTHETICOLD0000000000"
    # every refused and withdrawn row, in full, with the counts
    assert [r["group_id"] for r in out["refused"]] == [f"r{i}" for i in range(5)]
    assert all(r["missing_required"] == ["measurement.series"] and r["verdict"] == "incomplete" for r in out["refused"])
    assert out["refused_total"] == 5 and out["refused_by_reason"]["incomplete"] == 5
    assert out["missing_required_by_field"] == {"measurement.series": 5}
    assert out["withdrawn"][0]["record_id"] == "01SYNTHETICWITHDRAWN00000"
    # what every row repeated is said once at the top; each row keeps what is its own
    assert out["schemas_used"] == SCHEMAS and not any("schemas_used" in r for r in out["exported"])
    assert out["records_statement"].startswith("Valid for the portal") and not any("statement" in r for r in out["exported"])
    assert out["refused_every_summary_says"] == ["Draft checks: pass.", _refused(0)["summary"][2]]
    assert [r["summary"] for r in out["refused"]] == [[f"Missing required values: measurement.series (group r{i})."]
                                                      for i in range(5)]


def test_the_default_export_is_a_small_fraction_of_the_full_reply_and_loses_no_record_with_its_own_warning():
    result = _export_result(85)
    full, short = json.dumps(result, indent=1), json.dumps(cli.compact_export(result), indent=1)
    assert len(short) < len(full) / 5
    assert "a SYNTHETIC note of its own" in short and "01SYNTHETICOLD0000000000" in short


def test_one_refused_group_still_says_its_reason_counts():
    result = {**_export_result(1), "refused": [_refused(0)], "groups_refused": 1}
    out = cli.compact_export(result)
    assert out["refused_by_reason"]["incomplete"] == 1 and out["refused"][0]["summary"] == _refused(0)["summary"]
    assert "refused_every_summary_says" not in out


def test_rows_with_more_warnings_than_shown_or_a_refreshed_evidence_file_are_listed():
    result = _export_result(5)
    result["exported"][4]["warnings_omitted"] = 2
    result["exported"][3]["evidence_refreshed"] = True
    ids = [r["group_id"] for r in cli.compact_export(result)["exported"]]
    assert "g3" in ids and "g4" in ids


def test_a_small_export_is_printed_whole_but_for_what_it_says_once():
    result = _export_result(0)
    result["exported"] = result["exported"][:1]
    out = cli.compact_export(result)
    assert len(out["exported"]) == 1 and "exported_omitted" not in out and out["schemas_used"] == SCHEMAS


def _records_dir(tmp_path: Path, n: int, *, replaced: int | None = None, own_note: int | None = None) -> Path:
    d = tmp_path / "records"
    (d / R.EXPORT_STATE_DIR).mkdir(parents=True)
    index = []
    for i in range(n):
        rid = f"01SYNTHETIC{i:014d}"
        (d / f"{rid}.json").write_text(json.dumps({"record_id": rid}))
        notes = [NOTE.format(q=f"Q-{i + 1:010x}")] + (["a SYNTHETIC note of its own"] if i == own_note else [])
        (d / f"{rid}.evidence.json").write_text(json.dumps({"notes": notes}))
        index.append({"record_id": rid, "replaced_record_ids": ["01SYNTHETICOLD0000000000"] if i == replaced else []})
    (d / R.EXPORT_INDEX).write_text(json.dumps({"format": R.EXPORT_INDEX_FORMAT, "records": index}))
    return d


def test_the_dry_run_lists_every_replacing_record_and_every_own_note_and_the_first_few_others(tmp_path, capsys):
    d = _records_dir(tmp_path, 12, replaced=7, own_note=9)
    capsys.readouterr()
    assert cli.main(["bundle", "upload", str(d), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["network_calls"] == 0 and out["dry_run"] is True
    assert [r["record"][:25] for r in out["records"]] == [f"01SYNTHETIC{i:014d}" for i in (0, 1, 2, 7, 9)]
    assert out["records_total"] == 12 and out["records_omitted"] == 7 and "--full" in out["records_full_list"]
    assert out["records"][3]["replaces_record_ids"] == ["01SYNTHETICOLD0000000000"]
    assert out["body_bytes_total"] == sum(p.stat().st_size for p in d.glob("01SYNTHETIC*[0-9].json"))
    assert out["statement"].startswith("12 records, 2 requests each")
    capsys.readouterr()
    assert cli.main(["bundle", "upload", str(d), "--dry-run", "--full"]) == 0
    full = json.loads(capsys.readouterr().out)
    assert len(full["records"]) == 12 and full["records_total"] == 12


def test_upload_without_dry_run_is_still_refused_and_sends_nothing(tmp_path, capsys):
    d = _records_dir(tmp_path, 2)
    assert cli.main(["bundle", "upload", str(d), "--full"]) == cli.EXIT_USAGE


def test_the_skill_docs_say_what_the_default_export_and_dry_run_list():
    records = (SKILL / "reference" / "records-and-validation.md").read_text()
    commands = (SKILL / "reference" / "commands.md").read_text()
    trouble = (SKILL / "reference" / "troubleshooting.md").read_text()
    main = (SKILL / "SKILL.md").read_text()
    for term in ("exported_omitted", "refused_every_summary_says", "records_omitted", "replaces_record_ids",
                 "refused_by_reason", "schemas_used"):
        assert term in records, term
    assert "upload <records> --dry-run [--portal-url <url>] [--full]" in commands
    assert "bundle export <bundle> --out <records> [--full]" in commands
    assert "refused_by_reason" in trouble and "refused_by_reason" in main


# --- H2 -------------------------------------------------------------------------------------------------------


def _macro_bundle(tmp_path: Path):
    out = tmp_path / "bundle"
    assert cli.main(["import", str(R5F._corpus(tmp_path)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    b = M.load(out)
    [cf] = R5F._links(b)
    run_key = next(r["run_key"] for r in b["runs"] if r["run_id"] == cf["run_ids"][0])
    group = next(g for g in b["record_groups"] if run_key in g["member_run_keys"])
    return out, cf, group


def _macro_question(b: dict, cf: dict) -> dict:
    return next(x for x in Q.consolidate(b)["questions"] if {"kind": "conflict", "id": cf["conflict_id"]} in x["targets"])


def test_an_open_macro_set_point_disagreement_warns_on_the_record_until_it_is_answered(tmp_path):
    out, cf, group = _macro_bundle(tmp_path)
    b = M.load(out)
    _, report = R.compose_group(b, group, out)
    [w] = [w for w in report["warnings"] if w["code"] == R.MACRO_SETPOINT_WARNING]
    q = _macro_question(b, cf)
    assert w["question_id"] == q["question_id"] and w["conflict_id"] == cf["conflict_id"]
    assert "run2.mac states 0.8 V" in w["text"] and "states 0.7 V" in w["text"] and q["question_id"] in w["text"]
    assert R.warning_rank(w["code"]) == R.warning_rank(R.POTENTIAL_SOURCES_WARNING) == 0
    assert R.written_without(w).startswith("Written with a set-point its macro disagrees about")
    [shown] = R.with_question_commands(b, [w])
    assert shown["command"] == w["command"] and "--decision confirm --value <0.7 or 0.8>" in shown["command"]
    M.decide_question(out, question_id=q["question_id"], decision="confirm", value=0.8, by=BY["by"], orcid=None)
    b = M.load(out)
    _, report = R.compose_group(b, group, out)
    assert not [w for w in report["warnings"] if w["code"] == R.MACRO_SETPOINT_WARNING]
    assert B.check_bundle(out) == []


def test_the_macro_warning_reaches_build_records_and_validate(tmp_path):
    out, cf, group = _macro_bundle(tmp_path)
    M.decide(out, target_ids=[group["group_id"]], decision="confirm", value=None, **BY)
    built = R.build_records(out)
    assert any(w["code"] == R.MACRO_SETPOINT_WARNING for w in built["warnings"])
    v = R.validate_records(out, run_portal=_portal("publish"))
    codes = [w["code"] for w in v["warnings"]]
    assert codes.index(R.MACRO_SETPOINT_WARNING) < codes.index(R.START_TIME_WARNING)  # before the routine note


def test_a_disagreement_about_anything_else_sorts_before_the_start_time_ones_in_its_tier(tmp_path):
    out, cf, _ = _macro_bundle(tmp_path)
    qs = Q.consolidate(M.load(out))["questions"]
    tier = [q for q in qs if q["tier"] == Q.TIER_CONFLICT]
    start = [i for i, q in enumerate(tier) if (q["target_field_path"] or "").startswith("timestamps.")]
    other = [i for i, q in enumerate(tier) if q["kind"] == "resolve_conflict" and i not in start]
    assert start and other and max(other) < min(start)
    assert len({q["question_id"] for q in qs}) == len(qs)


def test_the_set_point_why_is_read_from_the_groups_control_mode(tmp_path):
    out, cf, group = _macro_bundle(tmp_path)
    b = M.load(out)
    q = _macro_question(b, cf)
    rid = cf["run_ids"][0]

    def miss(path):
        return next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] in (rid, None))

    M.decide(out, target_ids=[miss(B.CONTROL_MODE_PATH)], decision="correct", value="potentiostatic", **BY)
    M.decide(out, target_ids=[miss("context.electrochemistry.potential_scale")], decision="correct", value="RHE", **BY)
    M.decide(out, target_ids=[cf["candidate_id"]], decision="confirm", value=None, **BY)
    after = _macro_question(M.load(out), cf)
    assert after["question_id"] == q["question_id"] and after["tier"] == Q.TIER_CONFLICT and not after["blocking"]
    assert "no record group this question reaches has that yet" not in after["why"]
    assert "already has context.electrochemistry.potential_setpoint_V" in after["why"]
    assert "the reading the scientist chooses here is what the record carries" in after["why"]
    assert after["why"].endswith("carry now: potentiostatic.")


# --- H3 -------------------------------------------------------------------------------------------------------


def _in_situ(bdir_: Path) -> None:
    _decide_everything(bdir_)
    b = M.load(bdir_)
    M.decide(bdir_, target_ids=[_miss(b, "context.environment", "run-001")], decision="correct", value="in_situ", **BY)


def test_an_in_situ_record_with_no_electrolyte_cell_type_or_control_mode_warns_and_fills_nothing(bdir):
    _in_situ(bdir)
    built = R.build_records(bdir)
    [w] = [w for w in built["warnings"] if w["code"] == R.IN_SITU_WARNING]
    assert "carries no electrolyte, cell type, control mode or pH" in w["text"]
    assert "--question" in w["command"] and w["text"].count("isaac bundle decide") == 1  # each question named once
    assert all(f"question {qid}" in w["text"] for qid in {x.split("--question ")[1].split()[0] for x in
                                                          [w["command"]]})
    draft = json.loads((bdir / R.DRAFTS_DIR / "g1.draft.json").read_text())
    assert draft["fields"]["context.environment"]["value"] == "in_situ"
    for path, _ in R.IN_SITU_FIELDS:
        assert path not in draft["fields"]
    v = R.validate_records(bdir, run_portal=_portal("publish"))
    assert v["exportable"] == 1 and any(x["code"] == R.IN_SITU_WARNING for x in v["warnings"])  # a warning only


def _minimum(bdir_: Path) -> dict:
    b = M.load(bdir_)
    reports: dict = {}
    payload = Q.consolidate(b, compositions_out=reports)
    return Q.minimum_answers_for_one_group(payload, b, bundle_dir=bdir_, reports=reports)


def test_the_minimum_recommends_the_question_for_each_in_situ_field(bdir):
    _decide_everything(bdir, sample_form=False)  # one blocking answer left: the minimum names its group
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, "context.environment", "run-001")], decision="correct", value="in_situ", **BY)
    minimum = _minimum(bdir)
    assert minimum["group_id"] == "g1"
    rec = [r for r in minimum.get("recommended") or () if any(f in dict(R.IN_SITU_FIELDS) for f in r["fields"])]
    fields = {f for r in rec for f in r["fields"]}
    assert {p for p, _ in R.IN_SITU_FIELDS} <= fields
    assert all(r["question_id"] and not r["blocking"] for r in rec)
    assert all(f"question {r['question_id']}" in r["why"] for r in rec)
    assert sum("an in-situ record" in w for w in minimum["warnings"]) == 1  # the why said once


def test_a_group_with_nothing_left_still_says_the_in_situ_warning_once(bdir):
    _in_situ(bdir)
    minimum = _minimum(bdir)
    assert minimum["groups_with_nothing_left"] == 1
    assert sum("an in-situ record" in w for w in minimum["warnings"]) == 1


def test_answering_them_ends_the_warning(bdir):
    _in_situ(bdir)
    b = M.load(bdir)
    for path, value in ((B.CONTROL_MODE_PATH, "potentiostatic"), ("context.electrochemistry.cell_type", "h_cell")):
        target = next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == "run-001")
        M.decide(bdir, target_ids=[target], decision="correct", value=value, **BY)
    still = [w for w in R.build_records(bdir)["warnings"] if w["code"] == R.IN_SITU_WARNING]
    assert len(still) == 1 and "carries no electrolyte or pH" in still[0]["text"]


def test_an_ex_situ_record_never_gets_it(bdir):
    _decide_everything(bdir)
    assert not [w for w in R.build_records(bdir)["warnings"] if w["code"] == R.IN_SITU_WARNING]


def test_the_file_name_statements_are_quoted_never_read():
    runs = [{"run_id": "run-1", "stem": "ZZ9_01_SYNTH_10MNaOH_500mV", "scans": [{"relative_path": "ZZ9_01_SYNTH_10MNaOH_500mV"}]},
            {"run_id": "run-2", "stem": "ZZ9_02_SYNTH_100mMHClO4_pH1_OCV_3MOF"}]
    said = R._in_situ_statements(runs)
    assert [s["literal"] for s in said] == ["10MNaOH", "100mMHClO4", "pH1", "OCV"]  # 3MOF is a material code
    fields = {"context.environment": {"value": "in_situ", "status": "verified", "evidence": []}}
    bundle = {"candidates": [], "missing_values": []}
    [w] = R._in_situ_warnings(bundle, {"group_id": "gz"}, runs, fields, {})
    assert "the file names state 10MNaOH (ZZ9_01_SYNTH_10MNaOH_500mV), 100mMHClO4 (ZZ9_02_SYNTH_100mMHClO4_pH1_OCV_3MOF)" in w["text"]
    assert "never read as a value" in w["text"]


# --- H4 -------------------------------------------------------------------------------------------------------


def _count_saves(monkeypatch) -> list:
    saves = []
    real = M.save_bundle
    monkeypatch.setattr(M, "save_bundle", lambda d, b: (saves.append(1), real(d, b))[1])
    return saves


def test_a_decide_that_records_nothing_writes_nothing(bdir, monkeypatch):
    _decide_everything(bdir)
    target = [_miss(M.load(bdir), "system.domain", None)]
    before = (bdir / B.BUNDLE_FILE).read_bytes()
    saves = _count_saves(monkeypatch)
    validated = []
    real_validate = B.validate_bundle
    monkeypatch.setattr(B, "validate_bundle", lambda *a, **k: (validated.append(1), real_validate(*a, **k))[1])
    out = M.decide(bdir, target_ids=target, decision="correct", value="experimental", **BY)
    assert out["recorded"] == [] and out["statement"].startswith("Nothing new recorded")
    assert saves == [] and validated == [] and (bdir / B.BUNDLE_FILE).read_bytes() == before
    # a real change is saved, through the full check
    out = M.decide(bdir, target_ids=target, decision="correct", value="computational", **BY)
    assert out["recorded"] == target and saves == [1] and validated == [1]
    assert (bdir / B.BUNDLE_FILE).read_bytes() != before and B.check_bundle(bdir) == []


def test_a_question_answered_again_the_same_way_writes_nothing(bdir, monkeypatch):
    _decide_everything(bdir)
    b = M.load(bdir)
    qid = next(q["question_id"] for q in Q.consolidate(b, include_answered=True)["questions"]
               if q.get("target_field_path") == "system.domain")
    saves = _count_saves(monkeypatch)
    version = M.bundle_version(bdir)
    result, after = M.decide_question(bdir, question_id=qid, decision="correct", value="experimental", by=BY["by"],
                                      orcid=BY["orcid"], with_version=True)
    assert result["recorded"] == [] and saves == [] and after == version


def test_a_write_that_changes_something_is_still_refused_when_it_would_be_invalid(bdir, monkeypatch):
    _decide_everything(bdir)
    target = [_miss(M.load(bdir), "system.domain", None)]
    before = (bdir / B.BUNDLE_FILE).read_bytes()
    monkeypatch.setattr(B, "validate_bundle", lambda *a, **k: ["schema: (root): SYNTHETIC refusal"])
    with pytest.raises(M.MutationRefused, match="SYNTHETIC refusal"):
        M.decide(bdir, target_ids=target, decision="correct", value="computational", **BY)
    assert (bdir / B.BUNDLE_FILE).read_bytes() == before


def test_a_no_op_on_a_bundle_an_older_build_stored_is_still_upgraded_by_its_save(bdir, monkeypatch):
    _decide_everything(bdir)
    target = [_miss(M.load(bdir), "system.domain", None)]
    saves = _count_saves(monkeypatch)
    monkeypatch.setattr(B, "needs_format_upgrade", lambda bundle: True)
    monkeypatch.setattr(B, "record_format_upgrade", lambda bundle, **k: {"statement": "SYNTHETIC upgrade"})
    M.decide(bdir, target_ids=target, decision="correct", value="experimental", **BY)
    assert saves == [1]


def test_the_bundle_validator_is_built_once_per_process_and_the_string_walk_finds_every_string():
    assert B.bundle_validator() is B.bundle_validator()
    obj = {"a": ["x", {"b": "y", "c": [1, None, "z"]}], "d": 2.0}
    assert sorted(B._iter_strings(obj)) == ["a", "b", "c", "d", "x", "y", "z"]
    assert list(B._iter_strings("only")) == ["only"]


# --- H5 -------------------------------------------------------------------------------------------------------


def test_keeping_isaacs_approved_curve_after_choosing_a_version_is_reject_then_approve(bdir):
    from test_local_import_polish_r5c import _with_versions

    _decide_everything(bdir)
    _with_versions(bdir)
    M.decide(bdir, target_ids=["p1"], decision="select_athena_version", value="g1-v02", **BY)

    def warned():
        return [w for w in R.build_records(bdir)["warnings"] if w["code"] == R.ATHENA_NOT_CHOSEN_WARNING]

    [w] = warned()
    assert "reject it and approve it again" in w["text"]
    again = M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)
    assert again["recorded"] == [] and warned()  # approving it again alone records nothing, and the warning stays
    M.decide(bdir, target_ids=["p1"], decision="reject", value=None, **BY)
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)
    assert warned() == []
    doc = (SKILL / "reference" / "records-and-validation.md").read_text()
    assert "reject it\nand then approve it again" in doc and "approving it again alone records nothing new" in doc
    assert "approve it again, or choose its version again" not in doc


# --- r6h review: LOW 1-4 --------------------------------------------------------------------------------------


def test_a_warning_on_some_ready_records_names_every_one_of_their_groups():
    gids = [f"g{i}" for i in range(6)]
    said = [[f"Written without the start time: {NOTE.format(q=f'Q-{i + 1:010x}')}"]
            + (["Written without the potential set-point: SYNTHETIC"] if i in (1, 4, 5) else []) for i in range(6)]
    by_text = R.group_by_text(said)
    pw = {g: [{"code": "SYN_WARN", "path": "x", "message": "SYNTHETIC portal warning"}] for g in ("g0", "g2", "g3", "g5")}
    portal = R.portal_warning_summary(pw)
    assert portal[0]["group_ids"] == ["g0", "g2", "g3"]  # the summary's own cap
    R.name_partial_groups(gids, said, by_text, pw, portal)
    every, some = by_text
    assert "group_ids" not in every and some["records"] == 3 and some["group_ids"] == ["g1", "g4", "g5"]
    assert portal[0]["group_ids"] == ["g0", "g2", "g3", "g5"]  # every group, not the first 3


def test_a_warning_on_every_ready_record_names_no_groups():
    pw = {g: [{"code": "SYN_WARN", "path": None, "message": "m"}] for g in ("g0", "g1")}
    portal = R.portal_warning_summary(pw)
    R.name_partial_groups(["g0", "g1"], [["t"], ["t"]], R.group_by_text([["t"], ["t"]]), pw, portal)
    assert portal[0]["group_ids"] == ["g0", "g1"] and portal[0]["records"] == 2  # unchanged: the summary's own


def test_export_says_which_groups_a_partial_warning_is_on(bdir, tmp_path):
    _decide_everything(bdir)
    res = R.export_records(bdir, tmp_path / "records", run_portal=_portal("publish", warnings=[
        {"code": "SYN_WARN", "path": "x", "message": "SYNTHETIC portal warning"}]))
    [row] = res["portal_warnings"]
    assert row["records"] == len(res["exported"]) == 1 and row["group_ids"] == ["g1"]


def test_the_in_situ_minimum_still_recommends_cell_type_and_control_mode_when_the_electrolyte_is_required(bdir):
    _decide_everything(bdir, sample_form=False)
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, "context.environment", "run-001")], decision="correct", value="in_situ", **BY)
    real = Q._answer_missing
    # the electrolyte name (the warning's first field) required: the others are still recommended
    Q_answer = lambda report: [*real(report), "context.electrochemistry.electrolyte.name"]  # noqa: E731
    try:
        Q._answer_missing = Q_answer
        minimum = _minimum(bdir)
    finally:
        Q._answer_missing = real
    fields = {f for r in minimum.get("recommended") or () for f in r["fields"]}
    assert {"context.electrochemistry.cell_type", B.CONTROL_MODE_PATH} <= fields
    assert "context.electrochemistry.electrolyte.name" not in fields


def test_an_operando_record_warns_and_a_non_electrochemical_in_situ_one_does_not():
    fields = {"context.environment": {"value": "operando", "status": "verified", "evidence": []}}
    runs = [{"run_id": "run-1", "stem": "ZZ9_01_SYNTH_10MNaOH"}]
    [w] = R._in_situ_warnings({"candidates": [], "missing_values": []}, {"group_id": "gz"}, runs, fields, {})
    assert w["text"].startswith("an operando record that carries no")
    plain = [{"run_id": "run-1", "stem": "ZZ9_01_SYNTH_heated_cell"}]
    gas = {"context.environment": {"value": "in_situ", "status": "verified", "evidence": []}}
    assert R._in_situ_warnings({"candidates": [], "missing_values": []}, {"group_id": "gz"}, plain, gas, {}) == []
    # an electrochemistry field the record carries is evidence enough
    echem = {**gas, "context.electrochemistry.potential_scale": {"value": "RHE", "status": "verified", "evidence": []}}
    assert R._in_situ_warnings({"candidates": [], "missing_values": []}, {"group_id": "gz"}, plain, echem, {})
    # and so is a potential in the file name
    named = [{"run_id": "run-1", "stem": "ZZ9_01_SYNTH_500mV"}]
    assert R._in_situ_warnings({"candidates": [], "missing_values": []}, {"group_id": "gz"}, named, gas, {})


def _why_for(modes: list[str], *, filled: bool = False) -> dict:
    """``_agree_with_composer`` on one synthetic set-point question reaching groups with these control modes."""
    path = "context.electrochemistry.potential_setpoint_V"
    gids = [f"g{i}" for i in range(len(modes))]
    q = {"question_id": "Q-0000000000", "kind": "missing_value", "informational": False, "blocking": True, "tier": 1,
         "target_field_path": path, "targets": [{"kind": "missing_value", "id": f"m{i}"} for i in range(len(modes))],
         "applies_to": {"groups": len(modes)}}
    bundle = {"missing_values": [{"value_id": f"m{i}", "run_id": f"r{i}"} for i in range(len(modes))], "conflicts": [],
              "scientist_decisions": [], "candidates": []}
    reports = {g: {"missing_required": [], "filled": [{"path": path}] if filled else [], "control_mode": m if m != "-" else None}
               for g, m in zip(gids, modes)}
    Q._agree_with_composer([q], bundle, {f"r{i}": g for i, g in enumerate(gids)}, {}, reports)
    return q


def test_a_set_point_why_with_groups_of_different_control_modes_takes_the_required_when_branch():
    mixed = _why_for(["potentiostatic", "-"])
    assert mixed["required_when"] and "not every record group this question reaches has that yet" in mixed["why"]
    assert mixed["why"].count("none confirmed, potentiostatic") == 1
    none = _why_for(["-", "-"])
    assert "and no record group this question reaches has that yet" in none["why"]
    every = _why_for(["potentiostatic", "potentiostatic"])
    assert "required_when" not in every and "does not require" in every["why"]
    assert "already has" in _why_for(["potentiostatic", "-"], filled=True)["why"]


def test_the_docs_say_the_partial_warning_groups_and_full():
    doc = (SKILL / "reference" / "records-and-validation.md").read_text()
    assert "lists every one of their `group_ids`" in doc and "`export --full` names every row" in doc
    assert "on each record. The template" not in doc
    assert "in-situ or operando electrochemical record" in doc
