"""Polish c8-a: a curve that is not a usable spectrum is never approved; the scientist's Athena curve in a merged
group names the run it covers; the clock question takes ``defer``; the absorber question does not deny the files
processing read. Found walking the skill on a real BL4-3 beamtime; SYNTHETIC files only.

* A result whose QC ``fail`` names ``edge_step_implausible``, ``no_edge`` or ``post_edge_not_at_1`` cannot be
  approved: ``decide --decision approve`` refuses it (exit 2) with the reason in the result's own QC sentences and
  the options (reject; needs_changes and re-process with a setting the scientist chooses; reject the group), and
  ``validate`` never offers that approval. Any other ``fail`` keeps today's rule: approved with a stated QC status.
* In a MERGED group (two runs), the scientist's Athena curve made from ONE run's scans says which run, is flagged
  ``scientist_selected_subset_of_scans``, and is not preferred for the record (it says why). A one-run group is
  unchanged.
* ``decide --question <clock_time_zone question> --decision defer`` records "I don't know": the question stays,
  marked deferred, under its id, and the counter question is not touched by it.
* The absorber question no longer says "no file the import parsed states the absorber": processing reads a scan
  header's region-file name (e.g. ``ZzK_SYNTHETIC.rgn``) for a reference foil's edge, from a file the import did parse.
"""

from __future__ import annotations

import copy
import json

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _add_group, _portal, bdir, fake_upstream, pristine)

UNUSABLE = ("edge_step_implausible", "no_edge", "post_edge_not_at_1")
SENTENCE = {
    "edge_step_implausible": "SYNTHETIC: the edge step is 9 times the spectrum's whole range.",
    "no_edge": "SYNTHETIC: no edge stands above the noise.",
    "post_edge_not_at_1": "SYNTHETIC: the normalised level after the edge is 3.1, far from 1.",
}


def _fail(bdir, reasons, statements=None) -> None:
    """Group g1 with ONE undecided ISAAC result p1 (a curve on disk) whose QC fails for ``reasons``."""
    _add_group(bdir, verdict="fail")
    b = M.load(bdir)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    p1["qc"] = {"metrics": {}, "verdict": "fail", "reasons": list(reasons) + ["single_scan"],
                **({"statements": statements} if statements else {})}
    M.save_bundle(bdir, b)


def _approve(bdir, pid="p1", qc_status="valid"):
    return M.decide(bdir, target_ids=[pid], decision="approve", value=None, qc_status=qc_status, **BY)


def _validate(bdir) -> dict:
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    R.build_records(bdir)
    R.validate_records(bdir, run_portal=_portal("publish"))
    return json.loads((bdir / "validation" / "g1.json").read_text())


# --- 1. a curve that is not a usable spectrum is never approved ------------------------------------------------


@pytest.mark.parametrize("reason", UNUSABLE)
def test_approving_a_curve_that_fails_as_not_a_spectrum_is_refused_with_the_options(bdir, reason):
    _fail(bdir, [reason], {reason: SENTENCE[reason]})
    before = (bdir / "bundle.json").read_bytes()
    with pytest.raises(M.MutationRefused) as exc:
        _approve(bdir)
    said = str(exc.value)
    assert exc.value.code == 2
    assert f"p1 cannot be approved: its QC fails {reason}" in said and "not a usable spectrum" in said
    assert SENTENCE[reason] in said  # the result's own QC sentence, plainly
    assert "--target p1 --decision reject" in said and "--target p1 --decision needs_changes" in said
    assert "isaac process <bundle_dir> --source" in said and "--group g1 --params-file" in said
    assert "--target g1 --decision reject" in said and "Nothing was recorded" in said
    assert (bdir / "bundle.json").read_bytes() == before
    # whatever QC status is offered
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="failed", qc_note="SYN junk", **BY)
    # the options it names are recorded
    assert M.decide(bdir, target_ids=["p1"], decision="needs_changes", value=None, **BY)["recorded"] == ["p1"]
    assert M.decide(bdir, target_ids=["p1"], decision="reject", value=None, **BY)["recorded"] == ["p1"]


def test_the_cli_refuses_it_with_exit_2(bdir, capsys):
    _fail(bdir, ["post_edge_not_at_1"], {"post_edge_not_at_1": SENTENCE["post_edge_not_at_1"]})
    code = cli.main(["bundle", "decide", str(bdir), "--target", "p1", "--decision", "approve", "--qc-status", "valid",
                     "--by", "Synthetic Scientist"])
    err = capsys.readouterr().err
    assert code == 2 and "cannot be approved" in err and "post_edge_not_at_1" in err


def test_an_ordinary_fail_is_still_the_scientists_call(bdir):
    _fail(bdir, ["too_few_points"])
    out = M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="failed",
                   qc_note="SYN few points", **BY)
    assert out["recorded"] == ["p1"]
    assert M.unusable_curve_reasons(next(r for r in M.load(bdir)["processing_results"] if r["result_id"] == "p1")) == []


def test_a_warn_naming_the_same_word_is_not_a_fail(bdir):
    # the rule reads the FAIL reasons: a warn verdict never carries them, and is approved as before
    _add_group(bdir, verdict="warn")
    b = M.load(bdir)
    b["processing_results"][-1]["qc"]["reasons"] = ["post_edge_window_too_short"]
    M.save_bundle(bdir, b)
    assert _approve(bdir)["recorded"] == ["p1"]


@pytest.mark.parametrize("reason", UNUSABLE)
def test_validate_never_offers_approving_it(bdir, reason):
    _fail(bdir, [reason])
    report = _validate(bdir)
    text = " ".join(report["plain_summary"])
    assert report["processing_blocker"] == "processing_result_not_a_usable_spectrum"
    assert "--decision approve" not in text and "stating its QC status" not in text
    assert f"p1 is not offered for approval: its QC fails {reason}" in text
    assert "--target p1 --decision reject" in text and "--target p1 --decision needs_changes" in text
    assert "--group g1 --params-file" in text and "--target g1 --decision reject" in text


def test_validate_still_offers_approving_an_ordinary_fail(bdir):
    _fail(bdir, ["too_few_points"])
    report = _validate(bdir)
    text = " ".join(report["plain_summary"])
    assert report["processing_blocker"] == "processing_awaiting_approval"
    assert "--target p1 --decision approve --qc-status <value>" in text and "not offered" not in text


def test_validate_offers_the_other_result_and_says_why_not_the_failing_one(bdir):
    _fail(bdir, ["no_edge"])
    b = M.load(bdir)
    p2 = copy.deepcopy(next(r for r in b["processing_results"] if r["result_id"] == "p1"))
    p2.update(result_id="p2", source="scientist_athena", qc={"metrics": {}, "verdict": "pass", "reasons": []})
    b["processing_results"].append(p2)
    M.save_bundle(bdir, b)
    report = _validate(bdir)
    text = " ".join(report["plain_summary"])
    assert report["processing_blocker"] == "processing_awaiting_approval"
    assert "--target p2 --decision approve" in text and "--target p1 --decision approve" not in text
    assert "p1 is not offered for approval: its QC fails no_edge" in text


# --- 2. the Athena curve of one run in a merged group ------------------------------------------------------------

STEMS = ("01_SYN_ZZ1", "02_SYN_ZZ1")


def _merged(tmp_path, athena_groups):
    """ONE confirmed group of two runs (two scans each) and a project holding ``athena_groups`` (label, mu factor)."""
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")
    from test_local_import_processing import GRID, _athena_prj, fluo_scan, make_case, mu_edge, spec_file

    runs = [(s, [spec_file(fluo_scan(10 * i + j)) for j in (1, 2)], {"sample_name": "ZZ1"}) for i, s in enumerate(STEMS)]
    bdir, root, bundle = make_case(tmp_path, runs)
    bundle["record_groups"] = [{"group_id": "g-merged", "experiment_key": "e", "role": "sample",
                                "member_run_keys": [r["run_key"] for r in bundle["runs"]],
                                "basis": {"sample": {}, "technique": {}, "environment": {}, "conditions": {}},
                                "split_reasons": [], "status": B.STATE_SCIENTIST_CONFIRMED, "questions": []}]
    _athena_prj(root / "SYN.prj", [(label, GRID, mu_edge(GRID) * k) for label, k in athena_groups])
    bundle["unread_files"].append({"source_id": "prj-SYN", "relative_path": "SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _process(bdir, root):
    from isaac_api.local_import.processing.cli_entry import run_process

    out = run_process(bdir, source_root=root)
    isa = next(r for r in out["processing_results"] if r["source"] == "isaac_protocol")
    ath = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    return isa, ath


@pytest.mark.parametrize("groups, basis", [
    ([("02_SYN_ZZ1_A.001", 1e-2), ("02_SYN_ZZ1_A.002", 1.01e-2)], "per_scan_set"),
    ([("02_SYN_ZZ1_1-2", 1e-2)], "label"),
])
def test_an_athena_curve_of_one_run_in_a_merged_group_names_it_is_a_subset_and_is_not_preferred(tmp_path, groups, basis):
    bdir, root = _merged(tmp_path, groups)
    isa, ath = _process(bdir, root)
    assert ath["inputs"][0]["scans_basis"] == basis
    said = ath["qc"]["statements"]["scans_used"]
    assert "scans 1-2 of run 02_SYN_ZZ1" in said
    assert "covers only run 02_SYN_ZZ1 of the 2 runs merged in this group (01_SYN_ZZ1, 02_SYN_ZZ1)" in said
    assert "2 of the 4 scans ISAAC merged" in said and "not preferred for the record" in said
    assert M.SCAN_SUBSET_FLAG in ath["comparison"]["flags"] and M.SCAN_SUBSET_FLAG in isa["comparison"]["flags"]
    assert ath["comparison"]["athena_covers"] == {"runs": ["02_SYN_ZZ1"], "group_runs": list(STEMS), "scans": [1, 2],
                                                  "isaac_scans_merged": 4}
    assert ath["preferred_for_record"] is False
    # said on approval, naming the run
    note = M.scan_subset_note(M.load(bdir), ath)
    assert note and "scans 1, 2 of run 02_SYN_ZZ1" in note and "2 of the 4 scan(s) ISAAC merged" in note


def test_an_athena_curve_named_after_one_run_covers_only_that_run_and_a_one_run_group_is_unchanged(tmp_path):
    bdir, root = _merged(tmp_path, [("01_SYN_ZZ1", 1e-2)])  # named exactly after one run; its scans are not stated
    _, ath = _process(bdir, root)
    assert ath["inputs"][0]["scans_basis"] == "not_stated"
    said = ath["qc"]["statements"]["scans_used"]
    assert "covers only run 01_SYN_ZZ1 of the 2 runs merged in this group" in said and "not preferred" in said
    assert ath["preferred_for_record"] is False and M.SCAN_SUBSET_FLAG in ath["comparison"]["flags"]
    assert ath["comparison"]["athena_covers"]["scans"] is None
    from test_local_import_processing import _athena_case, GRID, mu_edge

    (tmp_path / "one").mkdir()
    one, root1 = _athena_case(tmp_path / "one", {"SYN.prj": [("01_SYN_ZZ1_A.001", GRID, mu_edge(GRID) * 1e-2),
                                                             ("01_SYN_ZZ1_A.002", GRID, mu_edge(GRID) * 1.01e-2)]})
    isa1, ath1 = _process(one, root1)
    # a ONE-RUN group is unchanged: no run named, no subset, preferred
    assert ath1["preferred_for_record"] is True and M.SCAN_SUBSET_FLAG not in ath1["comparison"]["flags"]
    assert "athena_covers" not in ath1["comparison"]
    assert ath1["qc"]["statements"]["scans_used"] == (
        "The scientist's curve is ISAAC's mean of 2 per-scan Athena groups, one each for scans 1-2 (read from their "
        "labels). ISAAC's own curve for this group merges 2 of 2 listed scans.")


# --- 3. the clock question takes defer ---------------------------------------------------------------------------

from test_local_import_xdc_start_time import _import, _valid, stamp  # noqa: E402


@pytest.fixture()
def clock(tmp_path):
    return _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45"), "SYN_beta_A.001": stamp("2099-07-15T10:00:00")})


def _clock_q(out) -> dict:
    [q] = [q for q in Q.consolidate(M.load(out))["questions"] if q["kind"] == "clock_time_zone"]
    return q


def test_the_clock_question_can_be_deferred_and_stays_open_marked_deferred(clock, capsys):
    q = _clock_q(clock)
    assert "defer" in q["allowed_decisions"] and "deferred" not in q
    code = cli.main(["bundle", "decide", str(clock), "--question", q["question_id"], "--decision", "defer",
                     "--by", "Synthetic Scientist"])
    out, err = capsys.readouterr()
    assert code == 0, err
    said = json.loads(out)
    assert said["recorded"] == ["experiment"]
    assert "do not know the time zone" in said["statement"] and "set_clock_time_zone" in said["statement"]
    assert "counter" not in said["statement"]
    again = _clock_q(clock)
    assert again["question_id"] == q["question_id"] and again["deferred"]["by"] == "Synthetic Scientist"
    b = _valid(clock)
    assert B.clock_zone_decision(b) is None and Q.counter_deferral(b) is None  # no zone, the counter untouched
    # replaying it records nothing new
    code = cli.main(["bundle", "decide", str(clock), "--question", q["question_id"], "--decision", "defer",
                     "--by", "Synthetic Scientist"])
    assert code == 0 and json.loads(capsys.readouterr().out)["unchanged"] == ["experiment"]
    # a zone answers it: the question is gone, nothing deferred
    M.decide(clock, target_ids=["experiment"], decision="set_clock_time_zone", value="UTC", by="Synthetic Scientist", orcid=None)
    assert not [x for x in Q.consolidate(M.load(clock))["questions"] if x["kind"] == "clock_time_zone"]
    _valid(clock)


def test_a_clock_defer_after_a_zone_is_refused_saying_the_zone_stands(clock):
    q = _clock_q(clock)
    M.decide(clock, target_ids=["experiment"], decision="set_clock_time_zone", value="UTC", by="Synthetic Scientist", orcid=None)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide_question(clock, question_id=q["question_id"], decision="defer", value=None, by="Synthetic Scientist", orcid=None)
    assert "UTC" in str(exc.value) and "Nothing was recorded" in str(exc.value)


def test_a_plain_experiment_defer_is_still_the_counter_questions(clock):
    M.decide(clock, target_ids=["experiment"], decision="defer", value=None, by="Synthetic Scientist", orcid=None)
    b = M.load(clock)
    assert Q.counter_deferral(b) is not None and "deferred" not in _clock_q(clock)


# --- 4. the absorber question does not deny the files processing read ------------------------------------------


from test_local_import_suggestions import _absorber_findings, _load, grouped  # noqa: E402,F401  (fixture)


def test_the_absorber_question_does_not_deny_a_region_file_name_processing_reads(grouped):
    out = grouped(processed=False)
    M.annotate_from_readings(out, _absorber_findings(("system.element", "Zz"), ("system.edge", "K")),
                             model_id="synthetic-model", apply=True)
    b = _load(out)
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_absorber"]
    assert "no file the import parsed states the absorber" not in q["text"]
    assert "only an AI reading" in q["text"] and "not file evidence" in q["text"]
    # what the import does NOT count, said plainly: a scan header's region-file name, which processing reads
    # only to propose a reference foil's edge for calibration
    assert "region-file name" in q["text"] and "reference foil" in q["text"]
    assert q["question_id"] == Q._qid("experiment", "confirm_absorber", "Zz|K")  # the id is unchanged
