"""Four facts a careful re-read of a real beamtime found that the import missed (plan item C6, 22 Nov 2026).

Each is a GENERAL rule, tested here on SYNTHETIC files only (every name is ZZ*/YY*, every value invented):

1. A logbook remark that a SAMPLE was bad or did not work (a heading marked ``(bad)``, a line such as "did not work!"
   in that sample's section) reaches that sample's runs and becomes one QC question on the sample's record groups. It
   drops nothing: the scientist keeps the records (confirm) or leaves them out (reject); the files stay either way.
2. The filter motor an acquisition RECORDED outranks the filter a file name states, where every recording agrees
   (the standing rule for recorded motor positions, extended to the filter motor). Recordings that disagree among
   themselves stay a question.
3. A logbook statement is read from the sample's OWN section. A section whose File Number column is empty reaches the
   runs whose file names carry that sample's number (and its name, when the heading gives one), and its statement
   overrides a beamtime-wide line written before any section.
4. The number in a cycling token (``after1200Cycling``) is worded as the cycling's upper potential limit in mV where the
   files say so (the token itself, another file name of the beamtime, or the logbook), never as a cycle count; where
   the logbook says cycles it is worded as cycles, and where nothing says which, the wording stays neutral.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import filenames, scans, spec
from isaac_api.bl15 import reconstruct as rc
from isaac_api.bl15 import resolution as res
from isaac_api.local_import import cli
from isaac_api.local_import import labels as L
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

BY = {"by": "SYN Scientist", "orcid": None}
NOTES = "2099 SYNTHETIC BL 15 notes.txt"


# --- a synthetic beamtime ------------------------------------------------------------------------------------------


def _scan(n: int, filt: int, hour: int) -> str:
    lines = [f"#S {n} gscan 1000 1100 5 0.5", f"#D Fri Jan 01 {hour:02d}:{n:02d}:00 2100", "#T 0.5  (Seconds)",
             f"#P0 0 1000.0 900.0 {filt}", "#N 4", "#L synenergy  I0  vortDT  absev"]
    lines += [f"{1000.0 + 2.5 * k:.1f} 10000 {100 + k} {1000.5 + 2.5 * k:.1f}" for k in range(12)]
    return "\n".join(lines) + "\n"


def _unit(root: Path, stem: str, filters: list[int], hour: int) -> None:
    """One acquisition: a SPEC file whose ``#O0`` names the ``filter`` motor and whose ``#P0`` records it per scan, and
    one exported ``.dat`` per scan that states the same motors by name."""
    head = (f"#F {stem}\n#E {4102444800 + hour * 3600}\n#D Fri Jan 01 {hour:02d}:00:00 2100\n"
            "#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.\n"
            "#O0   dummy0  synenergy  emiss  filter\n\n")
    (root / stem).write_text(head + "\n".join(_scan(n, f, hour) for n, f in enumerate(filters, 1)))
    folder = root / f"{stem}_dir"
    folder.mkdir()
    for n, f in enumerate(filters, 1):
        (folder / f"{stem}_{n:03d}.dat").write_text(
            _scan(n, f, hour).replace(f"#P0 0 1000.0 900.0 {f}", f"#P0 dummy0=0 synenergy=1000.0 emiss=900.0 filter={f}"))


def _table(rows) -> list[str]:
    """``(step, file number or "", procedure, note)`` rows as a DOCX table flattened to text (every cell a tab line)."""
    out = ["\tStep", "\tFile Number", "\tE-chem Procedure", "\tNotes "]
    for step, number, procedure, note in rows:
        out += [f"\t{step}", f"\t{number}", "", f"\t{procedure}", f"\t{note}"]
    return out


UNITS = {
    "01_01_ZZ1_acid_beforeCycling_filter10_100mV": [10, 10],
    "02_01_ZZ1_acid_after1200mVCycling_filter10_100mV": [10, 10],
    "03_02_ZZ2_base_after1200Cycling_filter10_100mV": [10, 10],
    # THE NAME SAYS filter35; BOTH RECORDINGS (the SPEC file and the exports) say the filter motor was at 20
    "04_02_ZZ2_base_after1200Cycling_filter35_900mV": [20, 20],
    "05_02_ZZ2_base_after700Cycling_filter10_100mV": [10, 10],
    # the recordings disagree among themselves (35 then 20): a question, whatever the name says
    "06_02_ZZ2_base_after700Cycling_filter35_1200mV": [35, 20],
    "07_03_ZZ3_base_beforeCycling_filter10_100mV": [10, 10],
    "08_03_ZZ3_base_beforeCycling_filter10_400mV": [10, 10],
    "09_04_YY1_film_filter10_100mV": [10, 10],
    "10_05_ZZ5_base_after500Cycling_filter10_100mV": [10, 10],
    # review of #352, finding 6: a dry measurement of sample 4 (its own name says so)
    "11_04_YY1_dry_filter10": [10, 10],
}


def _notes(*, heading_3: str = "Sample 3 ZZ3 in base (bad)", heading_4: str = "Sample 4",
           remark_3: str = "did not work!", extra: tuple[str, ...] = (),
           lines_4: tuple[str, ...] = ("Cell: H-cell",)) -> list[str]:
    return [
        "SYNTHETIC notes -- invented, no real beamtime, no real person.", "", "Beam January 1-2, 2099", "",
        # a beamtime-wide line before any section that names a cell only in passing
        "The spare parts are on the bench with the flow cell.", "",
        "Sample 1 ZZ1 in acid",
        *_table([(1, "01", "Sets the working potential to 0.1 V", ""),
                 (2, "02", "Sets the working potential to 0.1 V (after 1200 mV cycling)", "After 1200mV CV")]), "",
        "Sample 2 ZZ2 in base",
        *_table([(1, "03", "Sets the working potential to 0.1 V", ""),
                 (2, "04", "Sets the working potential to 0.9 V", "FILTER 35 from here"),
                 (3, "05", "Sets the working potential to 0.1 V", ""),
                 (4, "06", "Sets the working potential to 1.2 V", "")]), "",
        # FACT 1: a sample the logbook calls bad; its section lists no file numbers
        heading_3, remark_3, "",
        # FACT 3: a section with an empty File Number column that states the cell
        heading_4, *lines_4, *_table([(1, "", "Sets the working potential to 0.1 V", "")]), "",
        "Sample 5 ZZ5 in base",
        *_table([(1, "10", "Sets the working potential to 0.1 V", "measured after 500 cycles")]), "",
        *extra,
    ]


def _beamtime(root: Path, **notes) -> Path:
    root.mkdir(parents=True)
    for hour, (stem, filters) in enumerate(UNITS.items(), 1):
        _unit(root, stem, filters, hour)
    (root / NOTES).write_text("﻿" + "\r\n".join(_notes(**notes)) + "\r\n", encoding="utf-8")
    return root


def _import(tmp_path: Path, *, group: bool = True, **notes) -> tuple[Path, dict]:
    root = _beamtime(tmp_path / "SYN_beamtime", **notes)
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    if group:
        M.group(out)
    return out, M.load(out)


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> tuple[Path, dict]:
    return _import(tmp_path_factory.mktemp("facts"))


def _run_id(bundle: dict, prefix: str) -> str:
    return next(r["run_id"] for r in bundle["runs"] if r["stem"].startswith(prefix))


def _group_of(bundle: dict, prefix: str) -> str:
    rid = _run_id(bundle, prefix)
    key = next(r["run_key"] for r in bundle["runs"] if r["run_id"] == rid)
    return next(g["group_id"] for g in bundle["record_groups"] if key in g["member_run_keys"])


def _candidate(bundle: dict, prefix: str, *, path: str | None = None, key: str | None = None) -> dict | None:
    rid = _run_id(bundle, prefix)
    return next((c for c in bundle["candidates"] if c["run_id"] == rid
                 and (path is None or c.get("target_field_path") == path)
                 and (key is None or c.get("statement_key") == key)), None)


# =====================================================================================================================
# FACT 1: a logbook remark that a sample was bad becomes a QC question on that sample, and drops nothing
# =====================================================================================================================


def test_a_bad_heading_and_a_did_not_work_line_reach_the_runs_of_that_sample(imported):
    _, b = imported
    runs = {r["run_id"]: r["stem"][:5] for r in b["runs"]}
    notes = {n["text"]: sorted(runs[r] for r in n["run_ids"]) for n in b["data_quality_notes"]}
    # both remarks of the Sample 3 section reach exactly the runs whose names carry sample number 03 and ZZ3
    assert notes["bad"] == ["07_03", "08_03"]
    assert notes["did not work!"] == ["07_03", "08_03"]
    # a table row's note still reaches only its own file number
    assert notes["FILTER 35 from here"] == ["04_02"]


def _qc_questions(bundle: dict) -> list[dict]:
    return [q for q in Q.consolidate(bundle)["questions"] if q["kind"] == Q.QUALITY_REMARK_KIND]


def test_the_remark_becomes_one_qc_question_on_that_samples_groups(imported):
    _, b = imported
    qs = _qc_questions(b)
    assert len(qs) == 1
    q = qs[0]
    assert {t["id"] for t in q["targets"]} == {_group_of(b, "07_03"), _group_of(b, "08_03")}
    assert all(t["kind"] == "record_group" for t in q["targets"])
    # the scientist's words are quoted, where they were written, and nothing is decided for them
    assert "'bad'" in q["text"] and "'did not work!'" in q["text"] and NOTES in q["text"]
    # worded as what it is, a remark under the heading, never as ISAAC's verdict (review of #352, finding 2)
    assert "has this remark under the sample's heading" in q["text"] and "says this sample failed" not in q["text"]
    assert set(q["allowed_decisions"]) == {"confirm", "reject"}
    assert q["blocking"] is False
    # NOTHING IS DROPPED: the groups are still live proposals, every run is still in the bundle
    live = {g["group_id"]: g["status"] for g in Q.live_groups(b)}
    assert live[_group_of(b, "07_03")] == "proposed" and live[_group_of(b, "08_03")] == "proposed"
    assert {r["stem"][:5] for r in b["runs"]} >= {"07_03", "08_03"}


def test_the_qc_question_id_is_derived_from_what_the_import_recorded():
    """DEC-91: the id comes from the kind and the remark's own source and locator, never from an answer."""
    assert Q.quality_remark_question_id(NOTES, "line 30 sample heading qualifier") == \
        Q.quality_remark_question_id(NOTES, "line 30 sample heading qualifier")
    assert Q.quality_remark_question_id(NOTES, "line 30 sample heading qualifier").startswith("Q-")


def test_rejecting_leaves_the_groups_out_and_keeps_the_files(tmp_path):
    bdir, b = _import(tmp_path)
    qid = _qc_questions(b)[0]["question_id"]
    M.decide_question(bdir, question_id=qid, decision="reject", value=None, note="the logbook says it failed", **BY)
    after = M.load(bdir)
    status = {g["group_id"]: g["status"] for g in after["record_groups"]}
    assert status[_group_of(after, "07_03")] == "rejected" and status[_group_of(after, "08_03")] == "rejected"
    assert {r["stem"][:5] for r in after["runs"]} >= {"07_03", "08_03"}   # the runs and their files stay
    assert _qc_questions(after) == []


def test_confirming_keeps_the_records_and_answers_the_question(tmp_path):
    bdir, b = _import(tmp_path)
    qid = _qc_questions(b)[0]["question_id"]
    M.decide_question(bdir, question_id=qid, decision="confirm", value=None, **BY)
    after = M.load(bdir)
    status = {g["group_id"]: g["status"] for g in after["record_groups"]}
    assert status[_group_of(after, "07_03")] == "scientist_confirmed"
    assert _qc_questions(after) == []


def test_a_later_plain_confirm_does_not_undo_a_keep(tmp_path):
    """Re-review of #352, B: "keep" then a bulk confirm of the grouping leaves the remark answered."""
    bdir, b = _import(tmp_path)
    qid = _qc_questions(b)[0]["question_id"]
    M.decide_question(bdir, question_id=qid, decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=[g["group_id"] for g in M.load(bdir)["record_groups"]], decision="confirm", value=None, **BY)
    after = M.load(bdir)
    assert _qc_questions(after) == []
    assert "this also confirms the grouping of those runs" in next(
        q for q in Q.consolidate(after, include_answered=True)["questions"] if q["question_id"] == qid)["text"]


def test_a_group_confirmed_for_another_reason_has_not_answered_the_remark(tmp_path):
    """Review of #352, finding 5: a bulk confirm of the grouping is not "keep them despite the remark"."""
    bdir, b = _import(tmp_path)
    qid = _qc_questions(b)[0]["question_id"]
    M.decide(bdir, target_ids=[g["group_id"] for g in b["record_groups"]], decision="confirm", value=None, **BY)
    after = M.load(bdir)
    assert [q["question_id"] for q in _qc_questions(after)] == [qid]
    M.decide_question(bdir, question_id=qid, decision="confirm", value=None, **BY)
    assert _qc_questions(M.load(bdir)) == []
    with pytest.raises(M.MutationRefused, match="takes no --value"):
        M.decide_question(bdir, question_id=qid, decision="reject", value="SYN", **BY)


@pytest.mark.parametrize("line", ["Beam failed at 2am, refilled", "Bad weather, beam dump", "No signal on reference foil",
                                  "discard first scan", "works but bad contact", "Beam dump, discard first scan",
                                  "not bad at all", "Sample holder broken", "sample changer failed", "bad spot on sample",
                                  "bad I0, sample fine", "sample stage stuck, bad", "Bad spot, moved", "sample looks ok, beam bad",
                                  "ZZ9 fine, beam bad"])
def test_a_remark_about_something_else_is_not_about_the_sample(line):
    from isaac_api.bl15 import notes as N

    assert not N.is_failure_remark(line) and not N.is_failure_remark(line, "ZZ9")
    assert N.is_failure_remark("did not work!") and N.is_failure_remark("Sample failed") and N.is_failure_remark("bad")


@pytest.mark.parametrize("line", ["did not work, scans noisy", "Sample did not work, no signal on detector",
                                  "Bad sample, all spots damaged", "Electrode failed, reference broken", "Nothing works",
                                  "bad ring of catalyst", "ZZ9 failed, beam fine", "Sample bad, bad spot",
                                  "sample holder fine, sample broken", "Sample OK but failed", "Sample was good but did not work",
                                  "sample looks fine, no signal", "Electrode is intact, no signal", "sample good before, bad after",
                                  "Sample position 4 bad", "Bad spots everywhere, discard"])
def test_a_remark_that_names_the_sample_or_nothing_else_is_about_the_sample(line):
    """Re-review of #352, A: the exclusions never drop a line that names the sample, and are narrowed to the beam."""
    from isaac_api.bl15 import notes as N

    assert N.is_failure_remark(line, "ZZ9")


def _read_notes(lines: list[str]):
    from isaac_api.bl15 import notes as N

    text = "\r\n".join(lines)
    rec = N.SourceRecord(archive_path=NOTES, basename=NOTES, extension=".txt", size_bytes=len(text),
                         content_sha256="x", parent_dir="", depth=0)
    return N.read_beamtime_notes(rec, text).evidence


def test_a_remark_line_is_still_read_for_everything_else_on_it():
    """Review of #352, finding 1: the remark is recorded, and the line goes on to the other readers."""
    found = _read_notes(["Sample 3 ZZ3 in base", "Flow cell leaked, failed", "Operator: SYN Person, did not work", "",
                         *_table([(1, "07", "Sets the working potential to 0.1 V", "")])])
    concepts = {(e.concept, e.raw_literal) for e in found}
    assert (ev.CONCEPT_QUALITY_NOTE, "Flow cell leaked, failed") in concepts
    assert any(c == "cell_type_statement" and lit == "Flow cell leaked, failed" for c, lit in concepts)
    assert any(c == ev.CONCEPT_CONTRIBUTOR_STATEMENT for c, _ in concepts)


def test_a_good_heading_asks_nothing(tmp_path):
    _, b = _import(tmp_path, heading_3="Sample 3 ZZ3 in base (good)", remark_3="")
    assert _qc_questions(b) == []


def test_a_section_whose_name_the_numbered_files_do_not_carry_reaches_no_run(tmp_path):
    """The files numbered 03 say ZZ3; a heading "Sample 3 XX7" is about some other sample numbering, so the remark is
    kept, unbound, and asks nothing about the ZZ3 records."""
    _, b = _import(tmp_path, heading_3="Sample 3 XX7 in base (bad)")
    bad = next(n for n in b["data_quality_notes"] if n["text"] == "bad")
    assert bad["run_ids"] == []
    assert _qc_questions(b) == []


# =====================================================================================================================
# FACT 2: the recorded filter motor outranks the file name's filter
# =====================================================================================================================


def _filter_reading(literal: str, *, parser: str, n: int, scan: str | None = None) -> ev.SourceEvidence:
    by_name = parser == filenames.PARSER_ID
    return ev.SourceEvidence(
        evidence_id=f"e{n}", source_path="ZZ_unit" if by_name or parser == spec.PARSER_ID else f"ZZ_unit_dir/{n}.dat",
        source_type=ev.SOURCE_TYPE_SCAN_EXPORT if parser == scans.PARSER_ID else ev.SOURCE_TYPE_SPEC_ACQUISITION,
        locator="filename token 5" if by_name else f"line 4 header #P0 key `filter` ({n})",
        raw_literal=literal, concept=ev.CONCEPT_FILTER, parser_id=parser, determinism=ev.DETERMINISM_NORMALIZED,
        normalization_rule="bl15.test.rule", normalized_value=int(literal),
        scope=ev.SCOPE_MEASUREMENT if by_name else ev.SCOPE_SCAN, scan=scan, item=None if by_name else "filter")


def _filter_candidate(items):
    return {c.candidate_id.split("::")[-1]: c for c in rc._candidates_from_evidence(
        items, candidate_prefix="ZZ_unit", source_ids={}, by_concept=defaultdict(int), by_status=defaultdict(int),
        unregistered=set())}[ev.CONCEPT_FILTER]


def test_the_recorded_filter_motor_outranks_the_file_names_filter():
    c = _filter_candidate([
        _filter_reading("35", parser=filenames.PARSER_ID, n=1),
        _filter_reading("20", parser=scans.PARSER_ID, n=2, scan="1"),
        _filter_reading("20", parser=scans.PARSER_ID, n=3, scan="2"),
        _filter_reading("20", parser=spec.PARSER_ID, n=4, scan="1"),
    ])
    # BOTH READINGS KEPT; the rule names which one is used
    assert sorted(r["value"] for r in c.disagreement) == ["20", "35"]
    assert c.resolved_by_rule == res.STANDING_RULE_RECORDED_FILTER
    assert c.standing_resolution["chosen_source_role"] == res.ROLE_INSTRUMENT_HEADER
    assert c.standing_resolution["over_source_role"] == res.ROLE_HUMAN_LABEL
    assert {row["value"] for row in c.standing_resolution["reading_used"]} == {"20"}
    # ISAAC'S RULE, NOT THE DOMAIN OWNER'S: it says so, and never claims his confirmation
    assert c.standing_resolution["authority"] == "isaac_rule_pending_domain_owner"
    assert c.standing_resolution["layer"] == res.LAYER_ISAAC_RULE != res.LAYER_CONFIRMED_RESOLUTION
    assert "NOT confirmed by the domain owner" in c.standing_resolution["attribution"]


def test_MUTATION_recordings_that_disagree_among_themselves_stay_a_question():
    c = _filter_candidate([
        _filter_reading("35", parser=filenames.PARSER_ID, n=1),
        _filter_reading("35", parser=scans.PARSER_ID, n=2, scan="1"),
        _filter_reading("20", parser=scans.PARSER_ID, n=3, scan="2"),
    ])
    assert c.resolved_by_rule is None and c.standing_resolution is None


def test_through_the_import_the_filter_is_the_recorded_one_and_blocks_nothing(imported):
    _, b = imported
    c = _candidate(b, "04_02", key="filter")
    assert (c["standing_resolution"] or {}).get("rule_id") == res.STANDING_RULE_RECORDED_FILTER
    assert c["state_basis"]["resolved_by_rule"] == res.STANDING_RULE_RECORDED_FILTER
    gid = _group_of(b, "04_02")
    group = next(g for g in b["record_groups"] if g["group_id"] == gid)
    basis = group["basis"]["conditions"]["filter"]
    assert (basis["kind"], basis["value"]) == ("value", "20")
    # the disagreement stays on record (both readings kept) and, exactly as for a recorded motor position the standing
    # rule settles, is listed only as an optional disagreement: it blocks nothing and holds no group apart
    mine = {cf["conflict_id"] for cf in b["conflicts"] if cf.get("candidate_id") == c["candidate_id"]}
    asked = [q for q in Q.consolidate(b)["questions"] if any(t["id"] in mine for t in q["targets"])]
    assert all(q["tier"] == Q.TIER_OPTIONAL and not q["blocking"] for q in asked)
    assert not any(r.get("code") == "conflicting_condition" for r in group.get("split_reasons") or ())
    # the label proposed for the group is the recorded filter
    label = next(p for p in L.proposals(b) if p["label"] == "filter")
    assert next(i["value"] for i in label["items"] if i["group_id"] == gid) == "filter20"
    # review of #352, finding 4: the bulk question names the group the rule settled, the file name it overruled, and
    # that the rule is ISAAC's, not yet the scientist's
    text = next(q for q in L.label_questions(b) if q.get("label") == "filter")["text"]
    assert "04_02_ZZ2_base_after1200Cycling_filter35_900mV -> 'filter20' (the file name says 'filter35')" in text
    assert "by ISAAC's rule (bl15.resolution.recorded_filter_motor.v1), not yet confirmed by the scientist" in text
    # review of #352, finding 7: a scientist's reject on the settled disagreement still declines the condition
    from isaac_api.local_import import completeness as CP

    index = CP._Index(b)
    assert index.conflicts(group, "filter") == ([], False)
    cid = next(iter(mine))
    b2 = __import__("copy").deepcopy(b)
    M.record_decision(b2, target_ids=[cid], decision="reject", value=None, **BY)
    assert CP._Index(b2).conflicts(group, "filter") == ([], True)
    # the run whose recordings disagree among themselves is still a disagreement
    assert _candidate(b, "06_02", key="filter")["extracted_state"] == "conflicting"


# =====================================================================================================================
# FACT 3: a statement comes from the sample's own section, not from a neighbouring line
# =====================================================================================================================

CELL = "context.electrochemistry.cell_type"


def test_a_section_with_no_file_numbers_states_the_cell_for_its_own_numbered_runs(imported):
    _, b = imported
    c = _candidate(b, "09_04", path=CELL)
    assert c["value"] == "h_cell"
    assert [e["literal_value"] for e in c["evidence"]] == ["Cell: H-cell"]
    # the beamtime-wide line before any section does not reach a run whose own section states the cell
    assert all("spare parts" not in e["literal_value"] for e in c["evidence"])


def test_runs_whose_section_says_nothing_keep_only_the_beamtime_line(imported):
    _, b = imported
    for prefix in ("01_01", "03_02", "07_03"):
        c = _candidate(b, prefix, path=CELL)
        assert [e["literal_value"] for e in c["evidence"]] == ["The spare parts are on the bench with the flow cell."]
        assert c["value"] is None   # named only in passing (r5 B1): unchanged


def test_a_number_that_heads_two_sections_binds_nothing_and_listed_runs_are_never_reached(tmp_path):
    """Review of #352, finding 3: a second, unnamed "Sample 2" section (no rows) states a cell. Which of the two
    sections the files numbered 02 belong to is not something the number decides, and files 03-06 are listed in the
    named section's rows anyway: none of them takes the cell."""
    _, b = _import(tmp_path, group=False, extra=("Sample 2", "Cell: H-cell", ""))
    for prefix in ("03_02", "04_02", "05_02", "06_02"):
        c = _candidate(b, prefix, path=CELL)
        assert all(e["literal_value"] != "Cell: H-cell" or "line 5" in e["locator"] for e in c["evidence"]), prefix
        assert c["value"] is None


def test_the_rule_says_the_number_is_the_only_link_for_an_unnamed_heading(tmp_path):
    _, b = _import(tmp_path, group=False, lines_4=("Cell: H-cell", "Water oxidation until 2 V"))
    assert "the heading names no sample, so the number is the only link" in _candidate(b, "09_04", path=CELL)["rule"]
    # re-review of #352, C: also on the path where the statement gives no value ("water oxidation" is no schema option)
    rx = _candidate(b, "09_04", path="context.electrochemistry.reaction")
    assert rx["value"] is None and [e["literal_value"] for e in rx["evidence"]] == ["Water oxidation until 2 V"]
    assert "the heading names no sample, so the number is the only link" in rx["rule"]


def test_a_dry_measurement_gets_the_sections_cell_only_as_a_suggestion(imported):
    """Review of #352, finding 6: a run whose own name says it was dry may not have been in the cell."""
    _, b = imported
    c = _candidate(b, "11_04", path=CELL)
    assert c["value"] is None and [e["literal_value"] for e in c["evidence"]] == ["Cell: H-cell"]
    assert "dry or had no electrolyte" in c["state_basis"]["not_proposable_summary"] + c["state_basis"]["not_proposable_reason"]
    assert _candidate(b, "09_04", path=CELL)["value"] == "h_cell"


def test_a_heading_name_the_numbered_files_do_not_carry_binds_nothing(tmp_path):
    _, b = _import(tmp_path, group=False, heading_4="Sample 4 XX9")
    c = _candidate(b, "09_04", path=CELL)
    assert all(e["literal_value"] != "Cell: H-cell" for e in c["evidence"])


# =====================================================================================================================
# FACT 4: a cycling token's number is a potential limit in mV where the files say so, never a cycle count
# =====================================================================================================================


def _history(bundle: dict) -> dict[str, dict]:
    return {p["token"].casefold(): p for p in L.proposals(bundle) if p["label"] == "history" and p.get("token")}


def test_a_token_that_writes_mV_is_worded_as_a_potential_limit(imported):
    _, b = imported
    p = _history(b)["after1200mvcycling"]
    assert {i["value"] for i in p["items"]} == {"after cycling up to 1200 mV"}


def test_a_bare_number_another_file_name_writes_in_mV_is_worded_in_mV_too(imported):
    _, b = imported
    p = _history(b)["after1200cycling"]
    assert {i["value"] for i in p["items"]} == {"after cycling up to 1200 mV"}
    q = next(x for x in L.label_questions(b) if x["question_id"] == p["question_id"])
    assert "upper potential limit" in q["text"] and "not a cycle count" in q["text"]
    assert "after1200mVCycling" in q["text"]   # says where the unit is written


def test_a_bare_number_the_logbook_calls_cycles_is_worded_as_cycles(imported):
    _, b = imported
    assert {i["value"] for i in _history(b)["after500cycling"]["items"]} == {"after 500 cycles"}


def test_a_bare_number_nothing_explains_stays_neutral(imported):
    _, b = imported
    p = _history(b)["after700cycling"]
    assert {i["value"] for i in p["items"]} == {"after 700 cycling"}
    q = next(x for x in L.label_questions(b) if x["question_id"] == p["question_id"])
    assert "nothing in this beamtime's files says" in q["text"]


def test_the_history_question_ids_are_unchanged():
    """The id is the token's partition, as before: the wording is never part of it."""
    assert L.question_id("history", "history=after1200cycling") == Q._qid(
        "experiment", L.KIND, L.LABELS["history"], "history=after1200cycling")
