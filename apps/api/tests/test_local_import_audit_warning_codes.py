"""Audit of 18 Nov 2026, finding 16: ``export`` and ``upload --dry-run`` say their warnings BY CODE, with counts,
instead of one sentence per variant (18 "kinds" that differed only in a voltage, about 3,000 characters).
SYNTHETIC data only.
"""

from __future__ import annotations

import json

from isaac_api.local_import import records as R


def _lines(volts, q):
    return [("stated_potential_not_in_record",
             f"Written without the potential set-point: the file names state a potential ({volts}mV) but the record "
             f"will not carry it until the set-point is confirmed: isaac bundle decide <bundle_dir> --question {q}"),
            ("start_time_left_out", "Written without the start time: start time left out: the start-time disagreement is "
                                    f"unanswered (question Q-00000000{volts % 100:02d})")]


def test_warnings_are_grouped_by_code_with_counts_variants_and_a_question():
    per_record = [_lines(v, f"Q-aaaaaaaa{n:02d}") for n, v in enumerate((60, 600, 1200, 60, 1500))]
    per_record.append([("start_time_left_out", "Written without the start time: start time left out: the instrument "
                                               "clock zone is not answered yet (question Q-0000000099)")])
    rows = R.group_by_code(per_record)
    assert [(r["code"], r["records"]) for r in rows] == [("start_time_left_out", 5), ("stated_potential_not_in_record", 5),
                                                         ("start_time_left_out", 1)] or \
        {(r["code"], r["what"]): r["records"] for r in rows} == {
            ("start_time_left_out", "Written without the start time"): 6,
            ("stated_potential_not_in_record", "Written without the potential set-point"): 5}
    by = {r["code"]: r for r in rows}
    potential = by["stated_potential_not_in_record"]
    assert potential["records"] == 5 and potential["variants"] == 4          # four different potentials, said once
    assert potential["questions"][0] == "Q-aaaaaaaa00" and potential["questions_total"] == 5
    # a question many records name (one that answers them at once) leads, before each record's own
    shared = [[("start_time_left_out", f"Written without the start time: unanswered (question Q-00000000{n:02d}). Or answer "
                                       "every such group at once: question Q-ffffffffff.")] for n in range(3)]
    assert R.group_by_code(shared)[0]["questions"][0] == "Q-ffffffffff"
    assert by["start_time_left_out"]["records"] == 6 and by["start_time_left_out"]["variants"] == 2
    said = R.by_code_sentence(rows)
    assert "5 record(s) written without the potential set-point (4 variants" in said
    assert "6 record(s) written without the start time" in said
    assert said.count("mV") == 0 and len(said) < 500                           # no variant is spelled out
    json.dumps(rows)                                                           # plain data


def test_an_export_index_without_codes_is_grouped_by_what_each_line_says(tmp_path):
    """``upload --dry-run`` on records an older export wrote: the index has no codes, so the lines' leads are used."""
    plan = [{"record": str(tmp_path / f"{n:026d}.json"), "requests": [{}, {}],
             "notes": [f"Written without the potential set-point: the file names state a potential ({v}mV)",
                       "Written without the start time: start time left out"]} for n, v in enumerate((60, 600, 1200))]
    out = R.upload_summary(plan, tmp_path, None)
    assert [(r["what"], r["records"], r["variants"]) for r in out["notes_by_code"]] == [
        ("Written without the potential set-point", 3, 3), ("Written without the start time", 3, 1)]
    assert "3 record(s) written without the potential set-point (3 variants" in out["statement"]
    assert "600mV" not in out["statement"] and out["notes_by_text"]             # every sentence is still listed apart
    # with the codes export keeps: by the line's text, whatever order the dry run lists a record's notes in
    index = {"format": R.EXPORT_INDEX_FORMAT, "records": [
        {"record_id": f"{n:026d}", "written_without": list(reversed(p["notes"])),
         "written_without_codes": ["start_time_left_out", "stated_potential_not_in_record"]} for n, p in enumerate(plan)]}
    (tmp_path / R.EXPORT_STATE_DIR).mkdir()
    (tmp_path / R.EXPORT_INDEX).write_text(json.dumps(index))
    coded = R.upload_summary(plan, tmp_path, None)["notes_by_code"]
    assert [(r["code"], r["what"]) for r in coded] == [
        ("stated_potential_not_in_record", "Written without the potential set-point"),
        ("start_time_left_out", "Written without the start time")]
