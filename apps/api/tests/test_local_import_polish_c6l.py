"""Polish c6-l: four small review findings on the local-first import. Synthetic only.

* (1) The counter question, shown as answered, says only what happened: an answer given straight to
  ``decide --target experiment`` (the grouping step never asked) is "not applied yet" until a regroup runs;
  it is never "answered, and the regroup applied it" before one has.
* (2) ``result.json`` is written once, with the run: a re-run into the same run folder never rewrites it, and the
  docs say the current sentences are in bundle.json and the list/show output.
* (3) The descriptor of ISAAC's mean of the scientist's per-scan Athena curves says what ``generated_utc`` is.
* (4) A dry run's statement says what it WOULD record; nothing was written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_polish_c4a import _add_athena, _approve, _exported
from test_local_import_polish_c4r import _approve_athena, _athena_inputs
from test_local_import_polish_c5a import ABSORBER, COUNTER, WHO, _absorber_argv, _run, grouped, grouped_pristine, syn  # noqa: F401  (fixtures)
from test_local_import_records import BY, _decide_everything, bdir, fake_upstream, pristine  # noqa: F401  (fixtures)


def _never_asked(bundle_dir) -> None:
    """The grouping step did not ask the counter question (the answer below is given straight to ``decide``)."""
    b = M.load(bundle_dir)
    b["grouping_questions"] = [g for g in b.get("grouping_questions") or () if g.get("kind") != "naming_counter_positions"]
    M.save_bundle(bundle_dir, b)


def _counter_text(bundle_dir) -> str:
    (q,) = [q for q in Q.consolidate(M.load(bundle_dir), include_answered=True)["questions"]
            if q["question_id"] == COUNTER]
    return q["text"]


# --- (1) the answered counter question says what really happened ------------------------------------------------


def test_a_counter_answer_given_directly_is_not_called_applied_before_a_regroup(syn):
    _never_asked(syn)
    M.decide(syn, target_ids=["experiment"], decision="set_counter_positions", value=None, by=WHO, orcid=None, positions=[2])
    text = _counter_text(syn)
    assert "regroup applied it" not in text
    assert "not applied yet" in text and "isaac bundle group <bundle_dir> --regroup" in text


def test_the_counter_answer_is_called_applied_only_after_the_regroup_ran(syn):
    _never_asked(syn)
    M.decide(syn, target_ids=["experiment"], decision="set_counter_positions", value=None, by=WHO, orcid=None, positions=[2])
    M.group(syn, regroup=True)
    text = _counter_text(syn)
    assert "not applied yet" not in text
    assert "the current groups already follow it" in text


def test_an_answer_to_the_asked_question_still_reads_as_before(syn):
    M.decide(syn, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by=WHO, orcid=None, positions=[2])
    text = _counter_text(syn)
    assert "Already answered: every position it asks about (2)." in text and "not applied yet" not in text


# --- (4) a dry run says "would record" ---------------------------------------------------------------------------


def test_a_dry_run_statement_says_would_record_and_a_real_one_says_recorded(grouped):
    kwargs = dict(question_id=ABSORBER, only=None, only_scopes=None, field=None, decision="set_absorber", value=None, by=WHO,
                  orcid=None, element="Fe", edge="K")
    before = (Path(grouped) / "bundle.json").read_bytes()
    dry = M.decide_question(grouped, dry_run=True, **kwargs)
    assert dry["dry_run"] is True and dry["statement"].startswith("Would record")
    assert "Fe K recorded for 9 groups" in dry["statement"] and "Nothing was written" in dry["statement"]
    assert (Path(grouped) / "bundle.json").read_bytes() == before
    real = M.decide_question(grouped, **kwargs)
    assert real["statement"] == "Fe K recorded for 9 groups." and "Would" not in real["statement"]
    again = M.decide_question(grouped, dry_run=True, **kwargs)  # already answered: nothing would be recorded
    assert again["statement"].startswith("Nothing would be recorded") and "Nothing new recorded" not in again["statement"]


# --- (3) the per-scan mean's descriptor explains generated_utc ----------------------------------------------------


def test_a_per_scan_mean_descriptor_says_generated_utc_is_the_approval_time(bdir, tmp_path):
    _decide_everything(bdir)
    _add_athena(bdir, subset=False)
    _athena_inputs(bdir, scan="SYN_ZZ1_001 [+2 per-scan groups]", athena_group="syn_zz1_001", match_kind="per_scan_set",
                   per_scan_set={"athena_groups": ["syn_zz1_001", "syn_zz1_002", "syn_zz1_003"],
                                 "labels": ["SYN_ZZ1_001", "SYN_ZZ1_002", "SYN_ZZ1_003"], "scans": [1, 2, 3]})
    _approve_athena(bdir)
    [out] = _exported(bdir, tmp_path)["descriptors"]["outputs"]
    approval = next(d for d in reversed(M.load(bdir)["scientist_decisions"]) if d["decision"] == "approve")
    assert out["generated_utc"] == approval["decided_utc"]
    assert "generated_utc is when a scientist approved ISAAC's mean of them" in out["generated_by"]["notes"]


# --- (2) result.json is a snapshot written once ------------------------------------------------------------------


def test_a_rerun_into_an_existing_run_folder_keeps_result_json_and_the_docs_say_so(tmp_path):
    from test_local_import_processing import isaac, make_case, run_process, spec_file, fluo_scan

    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(1)), spec_file(fluo_scan(2))], {"sample_name": "ZZ1"})])
    r1 = isaac(run_process(bdir, source_root=root))
    record = bdir / "processing" / r1["group_id"] / r1["run_id"] / "result.json"
    old = json.loads(record.read_text())
    old["results"][0]["qc"].pop("statements", None)  # as an older build wrote it
    record.write_text(json.dumps(old))
    stale = record.read_bytes()
    isaac(run_process(bdir, source_root=root))
    assert record.read_bytes() == stale  # never rewritten: the run folder is as the run left it
    docs = Path(__file__).resolve().parents[3] / "docs" / "xas-processing-protocol-v0.md"
    text = " ".join(docs.read_text().split())
    assert "`result.json` is written once, with the run" in text and "bundle.json" in text
