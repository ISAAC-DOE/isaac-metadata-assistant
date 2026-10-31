"""Polish c8-b: walkthrough findings on a real BL4-3 beamtime (SSRL XDC scans), reproduced here. Synthetic only.

What these pin:

* (MED counts) a scan the SSRL XDC reader READ says so in its source ``reader`` block (which reader, what it gave:
  the run, the statements, the start-time candidate it backs), stored at import and derived for an older bundle
  whose block still says "no reader for this kind of source"; a companion (``.rgn/.det/.exp``, a same-named
  folder's files, ``binary/`` originals) says no reader opened it and which run it was kept beside;
  ``unread`` keeps its meaning, and the import, ``summary.md`` and ``bundle list unread`` count the companions
  apart (``not_listed.companion_not_opened``), ``unread --all`` lists them with run and role;
* (MED cross-check) ``reveal`` compares a blind reading of a scan start time with the header's LOCAL CLOCK time
  (``compared_as: local clock time``) in any spelling, says when it is another scan's time, and never compares a
  reading that names a zone; ``crosscheck-plan`` says what to read;
* (MED potential) a generic run whose FILE NAME states a potential (``500mV``, ``m600mV``) or whose SCAN HEADER
  comment does (``0.5Vrhe``) warns, naming both steps (set-point and scale), the header's scale, and a run whose
  name and header disagree; a name stating open circuit (``OCV``) warns until the control mode is confirmed;
  NO candidate is added;
* (LOW) an optional value of a run no live group holds is asked in that run's own question (counted under
  ``outside_live_groups``), never in the experiment's; "1 processed file"; a closed list says what to do when
  none of its values fits; no question id changes or disappears.

SYNTHETIC files only: every scan below is invented, dated 2099, named ``SYN_``.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_reader_ssrl_xdc import make_scan

BY = "SYNTHETIC TEST"
START = "timestamps.acquired_start_utc"
SETPOINT, SCALE = "context.electrochemistry.potential_setpoint_V", "context.electrochemistry.potential_scale"
MODE = "context.electrochemistry.control_mode"
#: name -> (first scan's local time, header comment line, scans)
RUNS = {
    "SYN_cat_500mV_101": ("2099-07-14T10:00:00", "SYN sample in 1M KOH 0.5Vrhe", 2),
    "SYN_cat_m600mV_102": ("2099-07-14T11:00:00", "SYN sample in 1M KOH 0Vrhe", 1),
    "SYN_cat_OCV_103": ("2099-07-14T12:00:00", "SYN sample in 1M KOH", 1),
    "SYN_align_104": ("2099-07-14T13:00:00", "trans_e.adet", 1),
}
COMPANIONS_PER_RUN = 4  # SYN.rgn, SYN.det, SYN.exp, profile.txt in the run's own folder
COMPANIONS = sum(COMPANIONS_PER_RUN + n for _, _, n in RUNS.values())  # + one binary/ original per scan


def stamp(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%a %b %d %H:%M:%S %Y")


def _scan_time(iso: str, i: int) -> str:
    return iso[:-5] + f"{10 * (i - 1):02d}:00"


@pytest.fixture(scope="module")
def src(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("c8b") / "SYN_bt"
    for name, (iso, comment, n) in RUNS.items():
        for i in range(1, n + 1):
            make_scan(root / f"{name}_A.{i:03d}", timestamp=stamp(_scan_time(iso, i)), free_text=("1x1 mm beam", comment))
            (root / "binary").mkdir(parents=True, exist_ok=True)
            (root / "binary" / f"{name}.{i:03d}").write_bytes(b"\x00\x01SYN")
        (root / name).mkdir(parents=True, exist_ok=True)
        for f in ("SYN.rgn", "SYN.det", "SYN.exp", "profile.txt"):
            (root / name / f).write_text("SYN companion\n")
    (root / "SYN_misc.bin").write_bytes(b"\x00\xffSYN")
    return root


@pytest.fixture(scope="module")
def imported(src, tmp_path_factory):
    out = tmp_path_factory.mktemp("c8b-out") / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def grouped_pristine(imported, tmp_path_factory):
    out = tmp_path_factory.mktemp("c8b-grouped") / "bundle"
    shutil.copytree(imported, out)
    M.group(out)
    return out


@pytest.fixture()
def grouped(grouped_pristine, tmp_path):
    out = tmp_path / "bundle"
    shutil.copytree(grouped_pristine, out)
    return out


@pytest.fixture()
def bdir(imported, tmp_path):
    out = tmp_path / "bundle"
    shutil.copytree(imported, out)
    return out


def _data(out: Path) -> dict:
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    return data


def _src(data: dict, rel: str) -> dict:
    return next(s for s in data["sources"] if s["relative_path"] == rel)


def _run_id(data: dict, label: str) -> str:
    return next(r["run_id"] for r in data["runs"] if r["label"] == label)


def _show(capsys, out: Path, kind: str, ident: str) -> dict:
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(out), kind, ident]) == 0
    return json.loads(capsys.readouterr().out)


def _list(capsys, out: Path, *argv) -> dict:
    capsys.readouterr()
    assert cli.main(["bundle", "list", str(out), *argv]) == 0
    return json.loads(capsys.readouterr().out)


# --- MED counts: what a reader did with each source -------------------------------------------------------------


def test_a_scan_the_xdc_reader_read_says_which_reader_and_what_it_gave(imported, capsys):
    data = _data(imported)
    src = _src(data, "SYN_cat_500mV_101_A.001")
    rid = _run_id(data, "SYN_cat_500mV_101")
    assert src["reader"]["reader_id"] == "ssrl_xdc_reader_v1" and src["reader"]["content_read"] is True
    assert src["reader"]["refused_reason"] is None and src["reader"]["statements_read"] > 0
    [start] = [c for c in data["candidates"] if c["run_id"] == rid and c["target_field_path"] == START]
    shown = _show(capsys, imported, "source", src["source_id"])
    assert shown["reader"] == src["reader"]
    assert shown["read_as"]["reader_id"] == "ssrl_xdc_reader_v1" and shown["read_as"]["as"] == "scan"
    assert shown["read_as"]["run_id"] == rid and shown["read_as"]["opened"] is True
    gave = " | ".join(shown["read_as"]["gave"])
    assert f"scan 1 of run {rid}" in gave and f"evidence for {start['candidate_id']} ({START})" in gave
    assert "no reader for this kind" not in json.dumps(shown)
    assert "2099" not in json.dumps(shown["read_as"])  # ids and fields, never a value


def test_a_companion_says_no_reader_opened_it_and_which_run_kept_it(imported, capsys):
    data = _data(imported)
    rid = _run_id(data, "SYN_cat_500mV_101")
    for rel, role in (("SYN_cat_500mV_101/SYN.rgn", "region"), ("SYN_cat_500mV_101/profile.txt", "other_context"),
                      ("binary/SYN_cat_500mV_101.002", "binary_original")):
        src = _src(data, rel)
        assert src["reader"]["reader_id"] is None and src["reader"]["content_read"] is False
        assert src["reader"]["refused_reason"].startswith("No reader opened this file")
        assert rid in src["reader"]["refused_reason"]
        shown = _show(capsys, imported, "source", src["source_id"])
        assert shown["read_as"] == {**shown["read_as"], "as": "companion", "role": role, "run_id": rid, "opened": False,
                                    "kept_by": "ssrl_xdc_reader_v1", "reader_id": None}


def test_an_older_bundle_whose_blocks_say_no_reader_is_shown_what_was_read(bdir, capsys):
    data = _data(bdir)
    old = {"reader_id": None, "content_read": False, "statements_read": 0, "statements_suppressed": 0, "partial": False,
           "skipped_total": 0, "refused_reason": "This build has no reader for this kind of source, so nothing was "
                                                 "read out of it. It is listed with its classification rather than passed over."}
    for s in data["sources"]:
        if s["relative_path"] != "SYN_misc.bin":
            s["reader"] = dict(old)
    (bdir / "bundle.json").write_text(json.dumps(data))
    scan = _show(capsys, bdir, "source", _src(data, "SYN_cat_m600mV_102_A.001")["source_id"])
    assert scan["reader"]["reader_id"] == "ssrl_xdc_reader_v1" and scan["reader"]["content_read"] is True
    assert scan["reader"]["refused_reason"] is None and scan["read_as"]["as"] == "scan"
    comp = _show(capsys, bdir, "source", _src(data, "SYN_cat_m600mV_102/SYN.det")["source_id"])
    assert comp["reader"]["refused_reason"].startswith("No reader opened this file") and comp["read_as"]["role"] == "detector"
    unread = _show(capsys, bdir, "source", _src(data, "SYN_misc.bin")["source_id"])
    assert "read_as" not in unread and unread["reader"]["refused_reason"].startswith("This build has no reader")


def test_unread_keeps_its_meaning_and_the_companions_are_counted_apart(imported, capsys):
    data = _data(imported)
    assert [u["relative_path"] for u in data["unread_files"]] == ["SYN_misc.bin"]
    page = _list(capsys, imported, "unread")
    assert page["total"] == 1 and page["not_listed"] == {B.NOT_OPENED_REASON_CODE: COMPANIONS}
    assert "--all" in page["not_listed_note"]
    every = _list(capsys, imported, "unread", "--all", "--limit", "200")
    assert every["total"] == 1 + COMPANIONS and "not_listed" not in every
    kept = [i for i in every["items"] if i["reason_code"] == B.NOT_OPENED_REASON_CODE]
    assert len(kept) == COMPANIONS and all(i["run_id"] and i["role"] and i["kept_by"] == "ssrl_xdc_reader_v1" for i in kept)
    assert {i["role"] for i in kept} == {"region", "detector", "experiment", "other_context", "binary_original"}
    # no scan is among them: a scan was read
    assert not any(i["relative_path"].endswith("_A.001") for i in kept)


def test_the_import_and_the_summary_count_the_unopened_files_with_a_plain_label(src, tmp_path, capsys):
    out = tmp_path / "bundle"
    capsys.readouterr()
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    said = capsys.readouterr().out
    assert "1 unread file)" in said
    assert f"{COMPANIONS} files kept beside a run without any reader opening them (companion and binary files)" in said
    assert f"bundle list {out} unread --all" in said
    summary = (out / "summary.md").read_text()
    assert "1 unread or refused" in summary
    assert f"  - {COMPANIONS} files kept beside a run without any reader opening them" in summary
    assert "not counted as unread: `isaac bundle list <dir> unread --all`" in summary


def test_one_processed_file_is_singular():
    assert cli._processed_files_text(1) == "1 processed file" and cli._processed_files_text(2) == "2 processed files"
    assert cli._not_opened_text(1).startswith("1 file kept beside a run without any reader opening it ")


def test_all_is_refused_on_a_kind_it_does_not_apply_to(imported, capsys):
    assert cli.main(["bundle", "list", str(imported), "runs", "--all"]) == cli.EXIT_USAGE
    assert "unread" in capsys.readouterr().err


# --- MED cross-check: a start time is compared as a local clock time ---------------------------------------------


def _start(data: dict, label: str) -> dict:
    rid = _run_id(data, label)
    return next(c for c in data["candidates"] if c["run_id"] == rid and c["target_field_path"] == START)


def _annotate(out: Path, cid: str, value, src_id: str) -> None:
    M.annotate(out, target_id=cid, value=value, excerpt_locator="line 2", source_id=src_id, model_id="synthetic-model",
               blind=True, rationale="the earliest scan's line-2 time")


@pytest.mark.parametrize("reading", ["2099-07-14T10:00:00", "2099-07-14 10:00:00", stamp("2099-07-14T10:00:00"),
                                     "Jul 14 10:00:00 2099", "2099/07/14 10:00:00"])
def test_reveal_compares_a_reading_with_the_header_as_the_same_local_clock_time(bdir, reading):
    c = _start(_data(bdir), "SYN_cat_500mV_101")
    _annotate(bdir, c["candidate_id"], reading, c["evidence"][0]["source_id"])
    out = M.reveal(bdir, c["candidate_id"])
    assert out["parser"]["value"] is None and out["parser"]["local_clock_start"] == "2099-07-14T10:00:00"
    [r] = out["ai_readings"]
    assert r["agrees_with_parser"] is True and r["relation"] == "supports"
    assert r["compared_as"] == "local clock time" and "same local clock time" in r["comparison_note"]


def test_reveal_says_when_a_reading_is_another_scans_time(bdir):
    c = _start(_data(bdir), "SYN_cat_500mV_101")
    _annotate(bdir, c["candidate_id"], "2099-07-14T10:10:00", c["evidence"][0]["source_id"])
    [r] = M.reveal(bdir, c["candidate_id"])["ai_readings"]
    assert r["agrees_with_parser"] is False and r["relation"] == "contradicts"
    assert "SYN_cat_500mV_101_A.002" in r["comparison_note"] and "not the earliest" in r["comparison_note"]


def test_reveal_never_compares_a_reading_that_names_a_zone_with_a_local_clock_time(bdir):
    c = _start(_data(bdir), "SYN_cat_500mV_101")
    _annotate(bdir, c["candidate_id"], "2099-07-14T17:00:00Z", c["evidence"][0]["source_id"])
    [r] = M.reveal(bdir, c["candidate_id"])["ai_readings"]
    assert r["agrees_with_parser"] is None and r["relation"] is None
    assert r["compared_as"] == "local clock time" and "names a time zone" in r["comparison_note"]


def test_after_the_zone_is_stated_a_utc_reading_is_compared_as_an_instant_and_a_clock_reading_as_a_clock(bdir):
    c = _start(_data(bdir), "SYN_cat_500mV_101")
    M.decide(bdir, target_ids=["experiment"], decision="set_clock_time_zone", value="America/Los_Angeles", by=BY, orcid=None)
    _annotate(bdir, c["candidate_id"], "2099-07-14T17:00:00Z", c["evidence"][0]["source_id"])
    _annotate(bdir, c["candidate_id"], "2099-07-14T10:00:00", c["evidence"][0]["source_id"])
    readings = {r["proposed_value"]: r for r in M.reveal(bdir, c["candidate_id"])["ai_readings"]}
    assert readings["2099-07-14T17:00:00Z"]["agrees_with_parser"] is True
    assert "compared_as" not in readings["2099-07-14T17:00:00Z"]
    assert readings["2099-07-14T10:00:00"]["agrees_with_parser"] is True
    assert readings["2099-07-14T10:00:00"]["compared_as"] == "local clock time"


def test_the_crosscheck_plan_says_a_start_time_is_compared_as_a_local_clock_time(imported):
    plan = M.crosscheck_plan(M.load(imported))
    starts = [i for i in plan["items"] if i["field_path"] == START]
    assert len(starts) == len(RUNS)
    assert all(i["compared_as"] == "local clock time" and "EARLIEST" in i["read_note"] for i in starts)
    assert "2099" not in json.dumps(starts)


# --- MED potential: names and headers that state a condition the record will not carry ---------------------------


def _confirm_groups(out: Path) -> dict:
    b = M.load(out)
    ids = [g["group_id"] for g in b["record_groups"] if g["status"] == "proposed" and g.get("role") != "alignment"]
    M.decide(out, target_ids=ids, decision="confirm", value=None, by=BY, orcid=None)
    return M.load(out)


def _warnings_of(out: Path, b: dict, label: str) -> list[dict]:
    rid = _run_id(b, label)
    g = next(x for x in b["record_groups"] if rid in x["member_run_ids"] and x["status"] == "scientist_confirmed")
    return R.with_question_commands(b, R.compose_group(b, g, out)[1]["warnings"])


def test_a_potential_in_the_name_and_the_header_names_both_steps_and_the_headers_scale(grouped):
    b = _confirm_groups(grouped)
    [w] = _warnings_of(grouped, b, "SYN_cat_500mV_101")
    assert w["code"] == R.STATED_POTENTIAL_WARNING and w["needs"] == SCALE and w["also_needs"] == SETPOINT
    assert [(s["literal"], s["stated_in"]) for s in w["stated"]] == [("500mV", "file name"), ("0.5Vrhe", "scan header")]
    assert all(s["read_as_V"] is None and s["candidate_id"] is None for s in w["stated"])
    text = w["text"]
    assert "500mV" in text and "0.5Vrhe is written in the scan header" in text and "(RHE)" in text
    assert "set-point" in text and "scale" in text and "DISAGREE" not in text
    assert f"--field {SETPOINT}" in text and f"--field {SCALE}" in text


def test_a_name_and_a_header_that_write_different_numbers_are_both_named(grouped):
    b = _confirm_groups(grouped)
    [w] = _warnings_of(grouped, b, "SYN_cat_m600mV_102")
    rid = _run_id(b, "SYN_cat_m600mV_102")
    # c8-r: the name writes no scale and the header writes RHE, so they may be one potential on two scales: never
    # "disagree", the scientist is asked which applies
    assert (f"different numbers on possibly different scales for 1 run(s) ({rid}: file name m600mV, scan header "
            "0Vrhe; the header writes RHE, the name none): ask which applies") in w["text"]
    assert "disagree for" not in w["text"].lower() and "neither is used" in w["text"]


def test_a_name_that_states_open_circuit_warns_until_the_control_mode_is_confirmed(grouped):
    b = _confirm_groups(grouped)
    [w] = _warnings_of(grouped, b, "SYN_cat_OCV_103")
    assert w["open_circuit"] is True and w["needs"] == MODE and w["targets"]
    assert "open circuit (OCV" in w["text"] and "control mode" in w["text"] and "--question" in w["text"]
    target = w["targets"][0]
    M.decide(grouped, target_ids=[target], decision="correct", value="open_circuit", by=BY, orcid=None)
    assert _warnings_of(grouped, M.load(grouped), "SYN_cat_OCV_103") == []


def test_validate_and_the_minimum_carry_the_warnings(grouped, capsys):
    _confirm_groups(grouped)
    capsys.readouterr()
    cli.main(["bundle", "validate", str(grouped)])
    report = json.loads(capsys.readouterr().out)
    assert report["warnings_total"] == 3
    assert {w["code"] for w in report["warnings"]} == {R.STATED_POTENTIAL_WARNING}
    b = M.load(grouped)
    gid = next(g["group_id"] for g in b["record_groups"] if _run_id(b, "SYN_cat_m600mV_102") in g["member_run_ids"])
    minimum = Q.minimum_answers_for_one_group(Q.consolidate(b), b, scope=f"group:{gid}")
    assert sorted(f for r in minimum["recommended"] for f in r["fields"]) == sorted([SCALE, SETPOINT])
    assert all("0Vrhe" in r["why"] for r in minimum["recommended"])


def test_no_candidate_is_added_for_a_potential(grouped):
    b = _confirm_groups(grouped)
    assert {c["target_field_path"] for c in b["candidates"]} == {START}
    assert len(b["candidates"]) == len(RUNS)


def test_token_volts_reads_only_the_spelling():
    assert Q._token_volts("m600mV") == -0.6 and Q._token_volts("0.5Vrhe") == 0.5 and Q._token_volts("0p5V") == 0.5
    assert Q._token_volts("0Vrhe") == 0.0 and Q._token_volts("1800mV") == 1.8 and Q._token_volts("KOH") is None


# --- LOW: scope, wording, ids ---------------------------------------------------------------------------------------


def test_an_optional_value_of_a_run_no_live_group_holds_is_asked_in_its_own_run_question(grouped):
    b = M.load(grouped)
    [align] = [g for g in b["record_groups"] if g.get("role") == "alignment"]
    M.decide(grouped, target_ids=[align["group_id"]], decision="reject", value=None, by=BY, orcid=None)
    b = M.load(grouped)
    rid = align["member_run_ids"][0]
    mine = {m["value_id"] for m in b["missing_values"] if m["run_id"] == rid}
    payload = Q.consolidate(b)
    live_scope = [q for q in payload["questions"] if q["kind"] == "optional_values" and not q["scope"].startswith("run:")]
    assert live_scope and all(not mine & {t["id"] for t in q["targets"]} for q in live_scope)
    assert all((q["applies_to"].get("runs_outside_live_groups") or 0) == 0 for q in live_scope)
    [own] = [q for q in payload["questions"] if q["kind"] == "optional_values" and q["scope"] == f"run:{rid}"]
    assert own.get("outside_live_groups") is True and mine & {t["id"] for t in own["targets"]}
    assert payload["counts"]["outside_live_groups"] >= 1


def test_a_closed_list_says_what_to_do_when_none_of_its_values_fits(grouped):
    payload = Q.consolidate(M.load(grouped))
    [form] = [q for q in payload["questions"] if q["kind"] == "missing_value" and q["target_field_path"] == "sample.sample_form"]
    assert form["allowed_values"] and "If none of the allowed values fits, leave it missing (--decision defer)" in form["text"]
    assert "foil" not in form["allowed_values"]  # the vocabulary is not widened


def test_no_question_id_changes_or_disappears(grouped, monkeypatch):
    """Against the bucketing before c8-b (the move switched off), after a rejection leaves a run in no live group:
    every id is still asked, and each kept question keeps its id with only the outside targets gone."""
    b = M.load(grouped)
    [align] = [g for g in b["record_groups"] if g.get("role") == "alignment"]
    M.decide(grouped, target_ids=[align["group_id"]], decision="reject", value=None, by=BY, orcid=None)
    b = M.load(grouped)
    now = {q["question_id"]: q for q in Q.consolidate(b)["questions"]}
    now_answered = {q["question_id"] for q in Q.consolidate(b, include_answered=True)["questions"]}
    monkeypatch.setattr(Q, "_move_outside_optional_targets", lambda *a, **k: None)
    old = {q["question_id"]: q for q in Q.consolidate(b)["questions"]}
    old_answered = {q["question_id"] for q in Q.consolidate(b, include_answered=True)["questions"]}
    assert set(old) <= set(now) and old_answered <= now_answered
    moved = [qid for qid in old if {t["id"] for t in old[qid]["targets"]} != {t["id"] for t in now[qid]["targets"]}]
    assert moved  # the experiment's optional question gave up the alignment run's targets
