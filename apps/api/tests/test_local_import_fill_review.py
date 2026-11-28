"""Bundle format 1.21.0: the END REVIEW (slice 4 of DEC-96, DEC-99; ``docs/fill-first-design-2026-11-25.md``).
SYNTHETIC data only: the committed multi-operator corpus (unmistakably fake: year 2100, samples ZZ1..ZZ3) imported under
the invented folder ``SSRL_BL152_2031-01_Quillfeather_ZzTestCat`` (PI "Quillfeather", project "ZzTestCat") with the
invented readme and memo of ``test_local_import_fill_folder``.

* ``bundle review`` lists every value a rule filled that the built records carry, by field, with how many records
  carry it, the rule in plain words, the shortest witness and, for the environment convention, the scientist's answer
  and how many measurements it reached; and the scan keep / drop decisions as the processing results store them;
* ``--accept --by --apply`` records ONE ``review`` decision binding each listed fill by target, value, rule and an
  evidence hash; each bound fill derives ``scientist_confirmed`` (basis ``reviewed_final_records``);
* a later change to a bound item returns exactly that item to ``filled``; a decision beats the review;
* the validator re-derives the review block and refuses a review whose items do not exist; older bundles load STALE as
  before; ``bundle status`` says what is not yet reviewed and points to the review; a reviewed fill composes as a
  confirmed value (``verified``) and passes the draft validator; answer memory never learns a review.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R
from isaac_api.local_import import review as RV
from isaac_api.local_import import status as ST

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_fill_first import _add_group  # noqa: E402
from test_local_import_fill_folder import (  # noqa: E402,F401
    BEAMLINE, BY, ENV, FACILITY, GROUP, ORG, RUNS, _chronoamperometry, _convention, _import, _miss, _vendored_schema_basis)

NAME = "SYN Quillfeather"


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> tuple[Path, Path]:
    return _import(tmp_path_factory.mktemp("review"))


@pytest.fixture()
def built(imported, tmp_path) -> Path:
    """Corroborated, the convention answered operando, one confirmed record group of two runs, records built."""
    import shutil

    bdir = tmp_path / "bundle"
    shutil.copytree(imported[1], bdir)
    _chronoamperometry(bdir, imported[0])
    _convention(bdir, "operando")
    _add_group(bdir, run_ids=("run-001", "run-002"))
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    R.build_records(bdir)
    return bdir


def _filled(b: dict) -> list[dict]:
    return [o for o in [*b["candidates"], *b["missing_values"]] if o.get("value_state") == B.STATE_FILLED]


def _reviewed(b: dict) -> list[dict]:
    return [o for o in [*b["candidates"], *b["missing_values"]] if B.is_reviewed_fill(o)]


def _accept(bdir: Path, **kw) -> dict:
    """Show the listing (for the same fields), then accept exactly it, as the skill does."""
    shown = RV.review(bdir, fields=kw.get("fields"))
    return RV.accept(bdir, by=NAME, apply=True, listing=kw.pop("listing", shown.get("listing")), **kw)


# --- the version -------------------------------------------------------------------------------------------------------


def test_the_format_is_1_21_0_and_the_rule_set_is_unchanged():
    assert B.FORMAT_VERSION == "1.22.0" == B._VERSION_ORDER[-1] and B.FILL_RULE_SET == 4  # 1.22.0: guesses (DEC-100)
    assert "1.21.0" in B.CHANGES_ADDED_IN and "review" in B.CHANGES_ADDED_IN["1.21.0"]
    assert B.REVIEW_DECISION in B.DECISIONS_BY_KIND["experiment"]
    assert set(RV.RULE_WORDS) == set(B.FILL_RULES)  # every registered rule has its plain words


# --- the listing ---------------------------------------------------------------------------------------------------------


def test_the_review_lists_every_filled_value_the_built_records_carry_by_field(built):
    before = M.bundle_version(built)
    out = RV.review(built)
    assert M.bundle_version(built) == before  # a read: bundle.json is not written
    assert out["records"] == 1 and out["records_built_since_last_change"] is True
    paths = {f["path"] for f in out["fields"]}
    assert {ENV, FACILITY, BEAMLINE, ORG, GROUP} <= paths
    env = next(f for f in out["fields"] if f["path"] == ENV)
    [v] = env["values"]
    assert v["value"] == "operando" and v["records"] == 1 and v["values"] == 2  # two runs, one record
    assert v["rule_id"] == B.FILL_ENVIRONMENT_RULE_ID and v["rule"] == RV.RULE_WORDS[B.FILL_ENVIRONMENT_RULE_ID]
    assert v["convention"]["answer"] == "operando" and v["convention"]["reached"] == 9
    assert v["convention"]["given_for"] == 9
    assert v["witness"] and (v["witness"].get("quote") or v["witness"].get("text"))
    group = next(f for f in out["fields"] if f["path"] == GROUP)
    assert group["values"][0]["value"] == "Ada Quillfeather group"
    # the listing names every filled value of the composed record, and only those
    b = M.load(built)
    composed = {i for _, _, comp in R.fresh_compositions(built, b) for e in comp.get("filled_by_rule") or ()
                for i in e["from"]}
    assert {t["target"]["id"] for t in RV._listing(built, b, fields=None)["items"]} == composed
    assert out["values_to_review"] == len(composed)
    assert "--accept" in out["next"]


def test_the_plain_listing_names_no_ids_and_says_what_to_do(built):
    out = RV.review(built)
    text = RV.render(out)
    b = M.load(built)
    for o in [*b["candidates"], *b["missing_values"]]:
        assert (o.get("candidate_id") or o.get("value_id")) not in text
    assert "g1" not in text.split("Scans kept")[0] and "isaac.fill." not in text
    assert "Your answer to the environment question: operando" in text and "reached 9 measurement(s)" in text
    assert "Next:" in text and "--accept" in text and "decide" in text and "build-records" in text


def test_the_review_lists_the_scan_decisions_as_stored(built):
    b = M.load(built)
    r = next(x for x in b["processing_results"] if x["group_id"] == "g1")
    r["scan_decisions"] = {"rule_id": "isaac.xas.scan_decision.v1", "rows": [
        {"run": "SYN_run_a", "scan": 1, "decision": "keep", "reasons": []},
        {"run": "SYN_run_a", "scan": 2, "decision": "drop", "reasons": [{"said": "the synthetic spot moved"}]}]}
    M.save_bundle(built, b)
    R.build_records(built)
    [s] = RV.review(built)["scan_decisions"]
    assert s["kept"] == 1 and s["dropped"] == [{"run": "SYN_run_a", "scan": 2, "decision": "drop", "by": "the rule",
                                                "reasons": ["the synthetic spot moved"]}]
    assert "SYN_run_a scan 2 dropped (the synthetic spot moved)" in RV.render(RV.review(built))


def test_the_review_is_refused_before_build_records(imported, tmp_path):
    import shutil

    bdir = tmp_path / "b"
    shutil.copytree(imported[1], bdir)
    with pytest.raises(RV.ReviewRefused, match="No record is built yet"):
        RV.review(bdir)
    assert cli.main(["bundle", "review", str(bdir)]) == 1


def test_the_field_filter_and_the_limit(built):
    only = RV.review(built, fields=[GROUP])
    assert [f["path"] for f in only["fields"]] == [GROUP]
    page = RV.review(built, limit=1)
    assert len(page["fields"]) == 1 and page["fields_not_shown"] == page["fields_total"] - 1
    assert cli.main(["bundle", "review", str(built), "--accept", "--by", NAME, "--limit", "1"]) == 2


# --- accept --------------------------------------------------------------------------------------------------------------


def test_accept_is_a_preview_until_apply(built):
    before = M.bundle_version(built)
    out = RV.accept(built, by=NAME)
    assert out["preview"] is True and out["recorded"] is False and out["values"] > 0
    assert M.bundle_version(built) == before and not B.review_decisions(M.load(built))


def test_accept_binds_each_listed_fill_and_they_become_confirmed(built):
    listed = RV._listing(built, M.load(built), fields=None)["items"]
    out = _accept(built)
    assert out["recorded"] is True and out["values"] == len(listed) == out["confirmed_now"]
    b = M.load(built)
    [d] = B.review_decisions(b)
    assert d["target"] == {"kind": "experiment", "id": "experiment"} and d["decided_by"]["name"] == NAME
    assert d[B.REVIEW_ITEMS_KEY] == listed and d[B.REVIEW_VERSION_KEY].startswith("sha256:")
    for item in d[B.REVIEW_ITEMS_KEY]:
        assert set(item) == {"target", "value", "rule_id", "evidence_sha256"} and len(item["evidence_sha256"]) == 64
    reviewed = {o.get("candidate_id") or o.get("value_id"): o for o in _reviewed(b)}
    assert set(reviewed) == {i["target"]["id"] for i in listed}
    for o in reviewed.values():
        assert o["value_state"] == B.STATE_SCIENTIST_CONFIRMED and o["eligibility_for_official_record"]["eligible"]
        assert o["review"] == {"decision_id": d["decision_id"], "basis": B.REVIEW_BASIS} and o["fill"]
    assert B.validate_bundle(b) == []
    # nothing waits now; accepting again records nothing
    R.build_records(built)
    assert RV.review(built)["values_to_review"] == 0
    again = RV.accept(built, by=NAME)
    assert again["recorded"] is False and len(B.review_decisions(M.load(built))) == 1


def test_accept_is_refused_when_the_records_changed_since_build_records(built):
    M.decide(built, target_ids=[_miss(M.load(built), "sample.sample_form", "run-001")["value_id"]], decision="correct",
             value="powder", **BY)
    with pytest.raises(RV.ReviewRefused, match="changed since they were built"):
        _accept(built)
    assert not B.review_decisions(M.load(built))
    assert RV.review(built)["records_built_since_last_change"] is False


def test_accept_refuses_a_bundle_that_moved_since_the_listing_was_shown(built):
    shown = RV.review(built)["bundle_version"]
    M.decide(built, target_ids=["experiment"], decision="set_clock_time_zone", value="UTC", **BY)
    with pytest.raises(RV.ReviewRefused, match="changed since it was read"):
        _accept(built, expected_version=shown)


def test_decide_cannot_record_a_review():
    with pytest.raises(M.MutationRefused, match="bundle review"):
        M._decide_arguments(target_ids=["experiment"], decision=B.REVIEW_DECISION, by=NAME, orcid=None,
                            qc_status=None, element=None, edge=None, positions=None)


def test_the_cli_round_trip(built, capsys):
    assert cli.main(["bundle", "review", str(built)]) == 0
    assert "Filled from the evidence, not yet reviewed" in capsys.readouterr().out
    assert cli.main(["bundle", "review", str(built), "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["fields"][0]["values"][0]["target_ids"]  # ids only in --json
    assert cli.main(["bundle", "review", str(built), "--apply"]) == 2  # --apply without --accept
    assert cli.main(["bundle", "review", str(built), "--accept", "--by", NAME]) == 0
    assert json.loads(capsys.readouterr().out)["preview"] is True
    assert cli.main(["bundle", "review", str(built), "--accept", "--by", NAME, "--apply",
                     "--version", listed["bundle_version"], "--listing", listed["listing"]]) == 0
    assert json.loads(capsys.readouterr().out)["recorded"] is True


# --- a later change un-reviews exactly the changed item; a decision beats the review ----------------------------------------


def test_a_changed_bound_item_returns_to_filled_and_only_that_one(built):
    _accept(built)
    b = M.load(built)
    target = next(o for o in _reviewed(b) if (o.get("fill") or {}).get("rule_id") == B.FILL_ENVIRONMENT_RULE_ID)
    others = {o.get("candidate_id") or o.get("value_id") for o in _reviewed(b)} - {target["value_id"]}
    # the bound item's evidence changes: its set-point token as the file gave it (an in-memory edit of the evidence)
    d = next(x for x in b["scientist_decisions"] if x["decision"] == B.REVIEW_DECISION)
    [item] = [i for i in d[B.REVIEW_ITEMS_KEY] if i["target"]["id"] == target["value_id"]]
    item["evidence_sha256"] = "0" * 64
    derived = B.apply_derivations(copy.deepcopy(b))
    now = {o.get("candidate_id") or o.get("value_id"): o for o in [*derived["candidates"], *derived["missing_values"]]}
    assert now[target["value_id"]]["value_state"] == B.STATE_FILLED and "review" not in now[target["value_id"]]
    assert all(now[i]["value_state"] == B.STATE_SCIENTIST_CONFIRMED for i in others)
    assert [x["id"] for x in B.review_changed_since(derived)] == [target["value_id"]]


def test_a_changed_value_unreviews_the_items_it_reaches(built):
    """The convention answered again as in_situ: every environment fill changes value, so every environment item returns
    to filled; the facility, organization and group items stay reviewed."""
    _accept(built)
    _convention(built, "in_situ")
    b = M.load(built)
    env = [m for m in b["missing_values"] if (m.get("fill") or {}).get("rule_id") == B.FILL_ENVIRONMENT_RULE_ID
           and m["run_id"] in ("run-001", "run-002")]
    assert env and all(m["value_state"] == B.STATE_FILLED and m["fill"]["value"] == "in_situ" for m in env)
    assert {m["target_field_path"] for m in _reviewed(b)} >= {FACILITY, ORG, GROUP}
    assert ENV not in {m["target_field_path"] for m in _reviewed(b)}
    changed = {x["id"] for x in B.review_changed_since(b)}
    assert changed == {m["value_id"] for m in env}
    facts = ST.status(built)["facts"]
    assert facts["reviewed_changed_since"] == len(changed)
    lines = ST.status(built)["lines"]
    assert any(f"{len(changed)} filled again, waiting for the next review" in line for line in lines), lines


def test_a_decision_beats_the_review(built):
    _accept(built)
    b = M.load(built)
    m = _miss(b, GROUP, None)
    assert B.is_reviewed_fill(m)
    M.decide(built, target_ids=[m["value_id"]], decision="correct", value="SYN other group", **BY)
    after = _miss(M.load(built), GROUP, None)
    assert after["value_state"] == B.STATE_SCIENTIST_CONFIRMED and "review" not in after and "fill" not in after
    assert m["value_id"] not in {x["id"] for x in B.review_changed_since(M.load(built))}  # the decision is the answer
    R.build_records(built)
    draft = json.loads((built / "drafts" / "g1.draft.json").read_text())
    assert draft["fields"][GROUP]["value"] == "SYN other group"


def test_answer_memory_never_learns_a_review(built):
    from isaac_api.local_import import answer_memory as AM

    _accept(built)
    values = AM.person_values(M.load(built))
    assert not any((v["decision"] or {}).get("decision") == B.REVIEW_DECISION for v in values)
    reviewed = {o.get("candidate_id") or o.get("value_id") for o in _reviewed(M.load(built))}
    assert not any(v["target"].split(":", 1)[-1] in reviewed for v in values)


# --- the validator ---------------------------------------------------------------------------------------------------------


def test_the_validator_refuses_a_review_state_it_cannot_rederive(built):
    _accept(built)
    b = M.load(built)
    m = _miss(b, GROUP, None)
    m.pop("review")
    m["value_state"] = B.STATE_FILLED
    assert any("review" in e and m["value_id"] in e for e in B.validate_bundle(b))
    b = M.load(built)
    other = next(o for o in b["missing_values"] if o["value_state"] == B.STATE_MISSING)
    other["review"] = {"decision_id": "d-00001", "basis": B.REVIEW_BASIS}
    assert any(other["value_id"] in e for e in B.validate_bundle(b))


def test_the_validator_refuses_a_review_whose_items_do_not_exist(built):
    _accept(built)
    b = M.load(built)
    d = next(x for x in b["scientist_decisions"] if x["decision"] == B.REVIEW_DECISION)
    d[B.REVIEW_ITEMS_KEY].append({"target": {"kind": "missing_value", "id": "mv-SYN-none"}, "value": "x",
                                  "rule_id": B.FILL_GROUP_RULE_ID, "evidence_sha256": "a" * 64})
    assert any("mv-SYN-none" in e and "does not exist" in e for e in B.validate_bundle(b))
    b = M.load(built)
    d = next(x for x in b["scientist_decisions"] if x["decision"] == B.REVIEW_DECISION)
    d[B.REVIEW_ITEMS_KEY] = []
    assert B.validate_bundle(b)  # the schema's minItems
    b = M.load(built)
    other = next(x for x in b["scientist_decisions"] if x["decision"] == "confirm")
    other[B.REVIEW_ITEMS_KEY] = [{"target": {"kind": "missing_value", "id": "x"}, "value": None, "rule_id": "r",
                                  "evidence_sha256": "a" * 64}]
    assert any("only review does" in e for e in B.validate_bundle(b))


# --- older bundles -------------------------------------------------------------------------------------------------------------


def test_an_older_bundle_still_loads_stale_as_before(built):
    b = M.load(built)
    old = copy.deepcopy(b)
    old["format_version"] = "1.17.0"
    old.pop("fill_rule_set", None)
    for o in [*old["candidates"], *old["missing_values"]]:
        o.pop("fill", None)
        o.pop("review", None)
        if o["value_state"] == B.STATE_FILLED:
            o["value_state"] = o.get("extracted_state", B.STATE_MISSING)
            o["eligibility_for_official_record"] = {"eligible": False, "reason": "stored by an older build"}
    errors, stale = B.validate_allowing_stale(old)
    assert errors == [] and stale and all(s.get("fill_moved") for s in stale)
    # a 1.20.0 bundle (no review possible there) re-derives to the same states: nothing is STALE
    v120 = copy.deepcopy(b)
    v120["format_version"] = "1.20.0"
    assert B.validate_allowing_stale(v120) == ([], [])


# --- status -------------------------------------------------------------------------------------------------------------------


def _next_once_answered(f: dict) -> str:
    """The "Next:" step once nothing comes before the records (every blocking question answered, the curve decided):
    the step order of ``status._next_step`` with those earlier steps settled."""
    settled = copy.deepcopy(f)
    settled["questions"] = {**(settled["questions"] or {}), "blocking": 0}
    settled["processing"].update(groups_not_processed=0, groups_awaiting_a_curve_decision=0)
    return ST._next_step(settled, "bundle")


def test_status_says_what_is_not_yet_reviewed_and_points_to_the_review(built):
    M.record_consent(built, by=NAME)
    out = ST.status(built)
    f = out["facts"]
    assert f["records_built"] is True and f["values_filled"] > 0 and f["values_reviewed"] == 0
    assert 0 < f["values_to_review"] == RV.review(built)["values_to_review"] < f["values_filled"]
    assert any("not yet reviewed" in line and "wait for the end review" in line for line in out["lines"])
    assert "isaac bundle review bundle" in _next_once_answered(f)
    _accept(built)
    out = ST.status(built)
    assert out["facts"]["values_to_review"] == 0 and out["facts"]["values_reviewed"] > 0
    [line] = [x for x in out["lines"] if x.startswith("Values a rule filled")]
    assert "every one in the built records is reviewed" in line and "in no built record yet" in line, line
    assert "isaac bundle review" not in _next_once_answered(out["facts"])


def test_status_before_build_records_names_the_review_in_the_last_step(imported, tmp_path):
    import shutil

    bdir = tmp_path / "b"
    shutil.copytree(imported[1], bdir)
    M.record_consent(bdir, by=NAME)
    f = ST.status(bdir)["facts"]
    assert f["records_built"] is False and f["values_filled"] > 0
    f["record_groups"]["live"] = 1  # as if grouped and settled: the last step names the review between build and validate
    step = _next_once_answered(f)
    assert step.index("build-records") < step.index("bundle review") < step.index("validate")


# --- composition --------------------------------------------------------------------------------------------------------------


def test_a_reviewed_fill_composes_as_a_confirmed_value_and_passes_the_draft_validator(built):
    from isaac_records.draft_validator import validate_draft

    before = json.loads((built / "drafts" / "g1.draft.json").read_text())
    assert before["fields"][ENV]["status"] == "inferred"
    _accept(built)
    R.build_records(built)
    draft = json.loads((built / "drafts" / "g1.draft.json").read_text())
    comp = json.loads((built / "drafts" / "g1.composition.json").read_text())
    d = B.review_decisions(M.load(built))[0]
    for path in (ENV, FACILITY, BEAMLINE, ORG, GROUP):
        env = draft["fields"][path]
        assert env["status"] == "verified" and env["value"] == before["fields"][path]["value"], path
        assert any(e.get("source_type") == "derivation" and e.get("rule") for e in env["evidence"]), path  # rule kept
        assert any(e.get("source_type") == "user_confirmation" and e.get("decision_id") == d["decision_id"]
                   and e.get("basis") == B.REVIEW_BASIS for e in env["evidence"]), path
    assert not comp.get("filled_by_rule") and {e["path"] for e in comp["reviewed_by_rule"]} >= {ENV, GROUP}
    report = validate_draft(draft)
    assert report.ok, report.errors


def test_questions_and_the_question_site_ask_no_reviewed_value(built, tmp_path):
    from isaac_api.local_import import questions as Q

    _accept(built)
    b = M.load(built)
    reviewed = {o.get("candidate_id") or o.get("value_id") for o in _reviewed(b)}
    payload = Q.consolidate(b)
    asked = {t["id"] for q in payload["questions"] for t in q.get("targets") or ()}
    assert not asked & reviewed
    # still addressable for a correction (decide --question finds them among the answered)
    every = Q.consolidate(b, include_answered=True)
    assert reviewed & {t["id"] for q in every["questions"] for t in q.get("targets") or ()}


def test_a_changed_witness_unreviews_exactly_that_candidate(imported, tmp_path):
    """A one-run record whose #D reading a scientist rejected, so its #E epoch start is a filled candidate
    (parser_exact) in the record; after the review its file witness changes: that candidate alone returns to filled."""
    import shutil

    from test_local_import_fill_first import START, _reject_local_starts

    bdir = tmp_path / "one"
    shutil.copytree(imported[1], bdir)
    _chronoamperometry(bdir, imported[0])
    _convention(bdir, "operando")
    _add_group(bdir, run_ids=("run-001",))
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    _reject_local_starts(bdir, "run-001")
    R.build_records(bdir)
    _accept(bdir)
    b = M.load(bdir)
    [target] = [c for c in b["candidates"] if B.is_reviewed_fill(c) and c["target_field_path"] == START]
    assert len(_reviewed(b)) > 1
    target["evidence"][0]["locator"] = "SYN edited locator"
    derived = B.apply_derivations(copy.deepcopy(b))
    moved = [o.get("candidate_id") or o.get("value_id") for o in [*derived["candidates"], *derived["missing_values"]]
             if (o.get("candidate_id") or o.get("value_id")) in {x.get("candidate_id") or x.get("value_id")
                                                                  for x in _reviewed(b)}
             and not B.is_reviewed_fill(o)]
    assert moved == [target["candidate_id"]]


def test_every_command_still_reads_a_reviewed_bundle(built, tmp_path, capsys):
    _accept(built)
    R.build_records(built)
    d = str(built)
    for argv in (["bundle", "check", d], ["bundle", "status", d], ["bundle", "questions", d, "--limit", "5"],
                 ["bundle", "questions", d, "--plain"], ["bundle", "validate", d], ["bundle", "list", d, "candidates"],
                 ["bundle", "template", "export", d, "--out", str(tmp_path / "t.xlsx")],
                 ["bundle", "site", "export", d, "--out", str(tmp_path / "site")],
                 ["bundle", "propose-terms", d], ["bundle", "review", d]):
        code = cli.main(argv)
        capsys.readouterr()
        assert code in (0, 1), (argv, code)


# --- the skill text ---------------------------------------------------------------------------------------------------------


def test_the_skill_fills_first_asks_only_what_remains_and_ends_with_the_review():
    from tests_support_records import REPO_ROOT

    skill_dir = REPO_ROOT / ".claude" / "skills" / "isaac-historical-import"
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 250
    for said in ("Fill what a registered rule supports: the code does it, you never write a value",
                 "Ask only what is missing, conflicting, or a judgment call",
                 # inverted at 1.22.0 (DEC-100): an inferred reading fills as a yellow guess, never green
                 "A reading is evidence", "inferred one fills it as a yellow guess", "mark its strength honestly",
                 "the group may be filled from the folder when a second source agrees",
                 "End with the review.", "## Step 10 · The review of the final records", "## Step 11 · Final summary",
                 "Never infer operando or in situ yourself", "word for word", "environment_convention",
                 "--listing <digest>", "what was filled by rule",
                 # fix round (review 11): the review needs the scientist's own yes, a scan is corrected in Step 6.3,
                 # and the local page is still a way to answer
                 "Run `decide` and `review --accept`", "set_scan_decision`, re-process", "*Local Imports* page"):
        assert said in text, said
    # the old rules are gone, the kept ones stay
    for gone in ("Your reading is a suggestion.", "A name in the folder name is a hint to offer, never an answer",
                 "**Values to confirm**", "an inferred one never does"):
        assert gone not in text, gone
    for kept in ("You do not write files.", "Never pick a side in a conflict.", "Never upload.",
                 "answer the scientist gave in THIS conversation"):
        assert kept in text, kept
    assert text.index("## Step 10 · The review") < text.index("## Step 11 · Final summary")
    refs = "\n".join(p.read_text(encoding="utf-8") for p in (skill_dir / "reference").glob("*.md"))
    assert "## The end review (Step 10)" in refs and "beyond a folder-name hint" not in refs
    assert "Never present your reading as confirmed" not in refs


# --- fix round: the listing digest, several fields, wording -------------------------------------------------------------

SCALE = "context.electrochemistry.potential_scale"
POT = "context.electrochemistry.potential_setpoint_V"


def test_apply_needs_the_listing_and_binds_only_what_was_shown(built, capsys):
    """Review 1: `review --field group` showed one value; an --accept with no --field would bind every field's. With
    the listing digest it is refused, so only what the scientist saw is ever recorded."""
    shown = RV.review(built, fields=[GROUP])
    assert shown["values_to_review"] == 1 and shown["listing"] in shown["next"]
    with pytest.raises(RV.ReviewRefused, match="needs --listing"):
        RV.accept(built, by=NAME, apply=True)
    with pytest.raises(RV.ReviewRefused, match="changed since you were shown them") as exc:
        RV.accept(built, by=NAME, apply=True, listing=shown["listing"])  # no --field: another listing
    assert exc.value.code == 1 and not B.review_decisions(M.load(built))
    preview = RV.accept(built, by=NAME)
    assert preview["preview"] and "--listing" in preview["statement"]
    out = RV.accept(built, by=NAME, apply=True, fields=[GROUP], listing=shown["listing"])
    assert out["values"] == 1 and [i["target"]["id"] for i in B.review_decisions(M.load(built))[0]["reviewed_fills"]] \
        == [_miss(M.load(built), GROUP, None)["value_id"]]
    assert cli.main(["bundle", "review", str(built), "--accept", "--by", NAME, "--apply"]) == 2  # no --listing


def test_a_listing_that_changed_since_it_was_shown_is_refused(built, capsys):
    shown = RV.review(built)
    _convention(built, "in_situ")  # every environment value changes
    R.build_records(built)
    code = cli.main(["bundle", "review", str(built), "--accept", "--by", NAME, "--apply", "--listing", shown["listing"]])
    assert code == 1 and "changed since you were shown them" in capsys.readouterr().err
    assert not B.review_decisions(M.load(built))


def test_several_fields_are_one_listing_one_decision_and_next_says_what_is_left(built, capsys):
    shown = RV.review(built, fields=[GROUP, ORG])
    assert [f["path"] for f in shown["fields"]] == sorted([GROUP, ORG], key=lambda p: (RV.field_words(p), p))
    assert "--field attribution.produced_by.group" in shown["next"] or "--field attribution.produced_by.organization" in shown["next"]
    assert cli.main(["bundle", "review", str(built), "--field", GROUP, "--field", ORG, "--accept", "--by", NAME,
                     "--apply", "--listing", shown["listing"]]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["recorded"] and out["values"] == 2 and set(out["by_field"]) == {GROUP, ORG}  # keyed on the path
    assert out["by_field"][ORG]["field"] == "organization" and out["by_field"][ORG]["records"] == 1
    assert "build-records" in out["next"] and "bundle review" in out["next"] and "what is left" in out["next"]
    assert len(B.review_decisions(M.load(built))) == 1
    # the second pass: build again, then the rest is reviewable
    R.build_records(built)
    rest = RV.review(built)
    assert {GROUP, ORG}.isdisjoint({f["path"] for f in rest["fields"]}) and rest["values_to_review"] > 0
    assert _accept(built)["recorded"] is True


def test_a_mistyped_field_is_refused_naming_the_reviewable_fields(built, capsys):
    with pytest.raises(RV.ReviewRefused, match="No built record has the field system.no_such") as exc:
        RV.review(built, fields=["system.no_such"])
    assert exc.value.code == 2 and GROUP in str(exc.value)
    assert cli.main(["bundle", "review", str(built), "--field", "system.no_such"]) == 2


def test_the_questions_path_and_the_records_path_are_both_accepted():
    assert RV.canonical_field("context.electrochemistry.reaction") == "context.reaction.name"
    assert RV.canonical_field(GROUP) == GROUP


def test_changed_reviewed_values_say_what_became_of_them(built):
    """Review 3: the convention answered again per measurement: no rule fills the environment any more, so the
    reviewed environment values are NOW ASKED, not 'filled again'."""
    _accept(built)
    _convention(built, "per_run")
    b = M.load(built)
    assert not any(B.is_reviewed_fill(m) for m in b["missing_values"] if m["target_field_path"] == ENV)
    R.build_records(built)
    ch = RV.review(built)["reviewed_changed_since"]
    assert ch["now_asked"] == ch["total"] > 0 and ch["listed_again"] == 0
    text = RV.render(RV.review(built))
    assert "now asked (no rule fills them any more)" in text and "listed below" not in text
    lines = ST.status(built)["lines"]
    assert any("now asked, since no rule fills them any more" in x for x in lines)
    assert not any("filled again" in x for x in lines)


def test_a_changed_set_point_value_unreviews_the_environment_it_rests_on(built):
    """Review 8: the environment's evidence hash covers the set-point's VALUE, not only its id."""
    _accept(built)
    b = M.load(built)
    env1 = _miss(b, ENV, "run-001")
    [cid] = B.environment_fill_basis(env1, B.fill_context(b))["setpoints"]
    next(c for c in b["candidates"] if c["candidate_id"] == cid)["value"] = 0.123
    derived = B.apply_derivations(copy.deepcopy(b))
    assert not B.is_reviewed_fill(_miss(derived, ENV, "run-001"))
    assert B.is_reviewed_fill(_miss(derived, ENV, "run-002"))


def test_the_validator_refuses_a_review_item_no_fill_could_have_been(built):
    _accept(built)
    b = M.load(built)
    d = B.review_decisions(b)[0]
    item = next(i for i in d["reviewed_fills"] if i["rule_id"] == B.FILL_GROUP_RULE_ID)
    item["rule_id"] = B.FILL_DOMAIN_RULE_ID  # the domain rule never fills the group
    assert any("never fills it" in e for e in B.validate_bundle(b))
    b = M.load(built)
    B.review_decisions(b)[0]["value"] = "SYN"
    assert any("carries a value" in e for e in B.validate_bundle(b))
    # a target a scientist had decided BEFORE the review: no fill was there to bind
    b = M.load(built)
    d = B.review_decisions(b)[0]
    m = _miss(b, "sample.sample_form", "run-001")
    d["reviewed_fills"].append({"target": {"kind": "missing_value", "id": m["value_id"]}, "value": "powder",
                                "rule_id": B.FILL_READING_STATED_RULE_ID, "evidence_sha256": "b" * 64})
    b["scientist_decisions"].insert(0, {**b["scientist_decisions"][0], "decision_id": "d-SYN-early",
                                        "target": {"kind": "missing_value", "id": m["value_id"]},
                                        "decision": "defer", "value": None})
    assert any("already decided" in e for e in B.validate_bundle(b))


def test_the_set_point_is_listed_only_when_the_record_carries_it_with_its_unit_and_scale(built):
    """Review 13: a set-point the scale gate keeps out of the record is no fill of it; beside its scale it is listed as
    "0.1 V vs RHE". (The synthetic runs' own set-points are held for review, so one is taken as a fill IN MEMORY: the
    composer and the listing read the derived state as stored.)"""
    def as_filled(b: dict) -> dict:
        c = next(c for c in b["candidates"] if c["target_field_path"] == POT and c["run_id"] == "run-001")
        c.update(value_state=B.STATE_FILLED, fill={"rule_id": B.FILL_PARSER_EXACT_RULE_ID, "value": c["value"]},
                 eligibility_for_official_record={"eligible": True, "reason": "SYN"})
        return b

    def one_run_group(b: dict) -> dict:
        g = next(g for g in b["record_groups"] if g["group_id"] == "g1")
        g["member_run_keys"] = [r["run_key"] for r in b["runs"] if r["run_id"] == "run-001"]
        return b

    b = one_run_group(as_filled(M.load(built)))
    group = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    draft, comp = R.compose_group(b, group, built)
    assert POT not in draft["fields"] and POT not in {e["path"] for e in comp.get("filled_by_rule") or ()}
    assert POT not in {f["path"] for f in RV._listing(built, b, fields=None)["fields"]}
    M.decide(built, target_ids=[_miss(M.load(built), SCALE, "run-001")["value_id"]], decision="correct", value="RHE",
             **BY)
    b = one_run_group(as_filled(M.load(built)))
    group = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    draft, comp = R.compose_group(b, group, built)
    assert draft["fields"][POT]["value"] == 0.1 and POT in {e["path"] for e in comp["filled_by_rule"]}
    [pot] = [f for f in RV._listing(built, b, fields=None)["fields"] if f["path"] == POT]
    assert [v["value_words"] for v in pot["values"]] == ["0.1 V vs RHE"]


def test_value_words_carry_the_unit_and_the_scale():
    assert RV.value_words(POT, 0.06, "RHE") == "0.06 V vs RHE"
    assert RV.value_words(POT, 0.06, None) == "0.06 V (scale not stated)"
    assert RV.value_words("context.temperature_K", 298.0) == "298.0 K"
    assert RV.value_words(ENV, "in_situ") != "in_situ"


def test_the_witness_a_beamline_scientist_accepts():
    folder = {"source_type": "file_listing", "quote": "SSRL_BL152_2031-01_Quillfeather_ZzTestCat",
              "locator": RV.FOLDER_LOCATOR}
    login = {"source_type": "document", "quote": "#C SYN spec User = zzlogin", "source_file": "a.dat", "locator": "line 3"}
    named = {"source_type": "document", "quote": "#C SYN SSRL beamline", "source_file": "a.dat", "locator": "line 4"}
    w = RV.witness(B.FILL_FACILITY_RULE_ID, FACILITY, "SSRL", [login, folder])
    assert w["text"].startswith("the beamtime folder's name") and "also" not in w  # never the login line
    w = RV.witness(B.FILL_FACILITY_RULE_ID, FACILITY, "SSRL", [login, folder, named])
    assert w["also"]["quote"] == named["quote"]
    w = RV.witness(B.FILL_DOMAIN_RULE_ID, "system.domain", "experimental", [named], files=9)
    assert w == {"text": "read from 9 of the beamline's own acquisition files", "by": "the files"}
    motor = {"source_type": "document", "quote": "9175.4", "source_file": "a.dat", "locator": "line 7 header #P2 (`emiss`)"}
    w = RV.witness(B.FILL_PARSER_EXACT_RULE_ID, "system.technique", "HERFD-XAS", [motor])
    assert w["text"] == "the emission analyser (motor `emiss`) is set to 9175.4 eV in the scan header"
    reading = {"source_type": "document", "quote": "SYNTHETIC held at 0.06 V vs RHE", "method": "ai_interpretation",
               "source_file": "SYN_memo.txt", "locator": "line 3"}
    w = RV.witness(B.FILL_READING_STATED_RULE_ID, POT, 0.06, [{"source_type": "derivation", "rule": "x"}, reading])
    assert w["quote"] == reading["quote"] and w["by"] == "a Claude reading of the files"


def test_the_listing_says_organization_and_counts_values_and_records(built):
    out = RV.review(built)
    org = next(f for f in out["fields"] if f["path"] == ORG)
    assert org["field"] == "organization"
    fac = next(f for f in out["fields"] if f["path"] == FACILITY)
    assert fac["values"][0]["witness"]["text"].startswith("the beamtime folder's name")
    text = RV.render(out)
    assert "Organization" in text and "Institution" not in text
    assert "2 value(s), in 1 record(s)" in text  # the environment: two runs' values in one record
    preview = RV.accept(built, by=NAME, listing=out["listing"])
    assert preview["listing_matches"] and "value(s) in 1 record(s)" in preview["statement"]


def test_no_confirmed_group_says_no_record_is_built_and_points_to_the_groups(imported, tmp_path, capsys):
    import shutil

    bdir = tmp_path / "b"
    shutil.copytree(imported[1], bdir)
    _add_group(bdir, run_ids=("run-001",))  # proposed, never confirmed
    with pytest.raises(RV.ReviewRefused, match="no record group is confirmed"):
        RV.review(bdir)
    R.build_records(bdir)  # builds nothing
    out = RV.review(bdir)
    assert out["records"] == 0 and "no record group is confirmed" in out["next"] and "build-records" in out["next"]
    assert "No record is built yet" in RV.render(out) and "Nothing filled is waiting" not in RV.render(out)


# --- round 2: a witness is always OF the value shown ---------------------------------------------------------------------


def test_a_contradicting_quote_is_never_shown():
    contradicts = {"source_type": "document", "quote": "7", "relation": "contradicts", "source_file": "a", "locator": "l1"}
    context = {"source_type": "document", "quote": "SYN context line", "relation": "context", "source_file": "a",
               "locator": "l2"}
    supports = {"source_type": "document", "quote": "0.5", "relation": "supports", "source_file": "b", "locator": "l3"}
    other_number = {"source_type": "document", "quote": "7", "relation": "supports", "source_file": "c", "locator": "l4"}
    assert RV.witness(B.FILL_PARSER_EXACT_RULE_ID, POT, 0.5, [contradicts, context, other_number]) is None
    assert RV.witness(B.FILL_PARSER_EXACT_RULE_ID, POT, 0.5, [contradicts, context, supports])["quote"] == "0.5"


def test_the_motor_phrase_is_never_attached_to_a_value_it_does_not_show():
    emiss = {"source_type": "document", "quote": "9175.4", "relation": "supports", "source_file": "a.dat",
             "locator": "line 7 header #P2 (`emiss`)"}
    assert RV.witness(B.FILL_PARSER_EXACT_RULE_ID, POT, 0.5, [emiss]) is None  # a set-point of 0.5: not the motor
    assert RV.witness(B.FILL_PARSER_EXACT_RULE_ID, ENV, "operando", [emiss]) is None
    assert "emission analyser" in RV.witness(B.FILL_PARSER_EXACT_RULE_ID, "system.technique", "HERFD-XAS",
                                             [emiss])["text"]
    held = {**emiss, "quote": "0.5", "locator": "line 8 header #P3 (`pot`)"}
    assert RV.witness(B.FILL_PARSER_EXACT_RULE_ID, POT, 0.5, [emiss, held])["text"] == \
        "motor `pot` is at 0.5 in the scan header"


def test_the_folder_witness_is_found_by_its_locator_and_a_login_line_never_names_the_facility():
    other_listing = {"source_type": "file_listing", "quote": "SYN_other_listing", "locator": "a listing",
                     "relation": "supports"}
    folder = {"source_type": "file_listing", "quote": "SSRL_BL152_2031-01_Quillfeather_ZzTestCat",
              "locator": RV.FOLDER_LOCATOR, "relation": "supports"}
    login = {"source_type": "document", "quote": "#C SYN spec User = ssrl_bob", "relation": "supports",
             "source_file": "a.dat", "locator": "line 3"}
    w = RV.witness(B.FILL_FACILITY_RULE_ID, FACILITY, "SSRL", [other_listing, login, folder], names=["SSRL", "BL15-2"])
    assert w["text"].endswith(folder["quote"]) and "also" not in w
    assert not RV.names_token("ssrl_bob", ["SSRL"]) and not RV.names_token("#C User = SSRL", ["SSRL"])
    assert RV.names_token("#C SYN at SSRL BL15-2", ["SSRL"]) and RV.names_token("#C SYN BL15-2 run", ["BL15-2"])
    header = {"source_type": "document", "quote": "#C SYN measured at SSRL BL15-2", "relation": "supports",
              "source_file": "a.dat", "locator": "line 2 header #C"}
    w = RV.witness(B.FILL_FACILITY_RULE_ID, BEAMLINE, "BL15-2", [folder], names=["SSRL", "BL15-2"], header=header)
    assert w["also"]["quote"] == header["quote"]  # the second source the rule rests on is visible


def test_a_header_line_naming_the_facility_is_shown_beside_the_folder(built):
    b = M.load(built)
    run = next(r for r in b["runs"] if r["run_id"] == "run-001")
    b["extended_context"].append({**b["extended_context"][0], "entry_id": "ec-SYN-facility",
                                  "source_id": run["acquisition_source_id"], "locator": "line 2 header #C",
                                  "raw_literal": "#C SYNTHETIC measured at SSRL BL15-2", "run_id": run["run_id"]})
    fac = next(f for f in RV._listing(built, b, fields=None)["fields"] if f["path"] == FACILITY)
    w = fac["values"][0]["witness"]
    assert w["text"].startswith("the beamtime folder's name") and w["also"]["quote"] == "#C SYNTHETIC measured at SSRL BL15-2"


def test_a_field_filled_in_one_record_and_corrected_in_another_shows_only_the_fills_own_witness(imported, tmp_path):
    """Round 2: witnesses are pooled per (field, value). run-001's record has the filled operando; run-002's record has
    a scientist's in_situ. The operando row cites only run-001's own set-point; the in_situ record lists nothing."""
    import shutil

    bdir = tmp_path / "two"
    shutil.copytree(imported[1], bdir)
    _chronoamperometry(bdir, imported[0])
    _convention(bdir, "operando")
    _add_group(bdir, run_ids=("run-001",))
    b = M.load(bdir)
    g2 = {**copy.deepcopy(next(g for g in b["record_groups"] if g["group_id"] == "g1")), "group_id": "g2",
          "member_run_keys": [r["run_key"] for r in b["runs"] if r["run_id"] == "run-002"]}
    b["record_groups"].append(g2)
    M.save_bundle(bdir, b)
    M.decide(bdir, target_ids=["g1", "g2"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=[_miss(M.load(bdir), ENV, "run-002")["value_id"]], decision="correct", value="in_situ",
             **BY)
    R.build_records(bdir)
    env = next(f for f in RV.review(bdir)["fields"] if f["path"] == ENV)
    [row] = env["values"]
    assert row["value"] == "operando" and row["group_ids"] == ["g1"] and row["records"] == 1
    run1 = next(r for r in M.load(bdir)["runs"] if r["run_id"] == "run-001")
    assert row["witness"]["quote"] == "100mV" and run1["stem"] in str(row["witness"]["file"])


def test_the_validator_refuses_a_review_item_no_rule_could_have_given(built):
    _accept(built)
    b = M.load(built)
    d = B.review_decisions(b)[0]
    cell = next(m for m in b["missing_values"] if m["target_field_path"] == "context.electrochemistry.cell_type"
                and m["value_state"] == B.STATE_MISSING)
    d["reviewed_fills"].append({"target": {"kind": "missing_value", "id": cell["value_id"]}, "value": "flow_cell",
                                "rule_id": B.FILL_READING_STATED_RULE_ID, "evidence_sha256": "c" * 64})
    assert any("never fills it" in e and cell["value_id"] in e for e in B.validate_bundle(b))
    # round 4: a VALUE no fill gives (another than the candidate's own) is no error — the value is not timeless; such
    # an item simply never binds
    b = M.load(built)
    d = B.review_decisions(b)[0]
    c = next(c for c in b["candidates"] if c["value"] is not None and c["run_id"] == "run-001")
    d["reviewed_fills"].append({"target": {"kind": "candidate", "id": c["candidate_id"]}, "value": "SYN other",
                                "rule_id": B.FILL_PARSER_EXACT_RULE_ID, "evidence_sha256": "d" * 64})
    assert B.validate_bundle(b) == []
    assert not B.is_reviewed_fill(next(x for x in B.apply_derivations(copy.deepcopy(b))["candidates"]
                                       if x["candidate_id"] == c["candidate_id"]))


def test_the_group_row_shows_the_folder_and_the_readme_month_header_that_agrees(built):
    """Round 3 regression: the group rule needs a SECOND source; the readme's month header the group basis recorded
    ("# 2031-01_Quillfeather", the surname glued to the month) is shown beside the folder's name."""
    group = next(f for f in RV.review(built)["fields"] if f["path"] == GROUP)
    w = group["values"][0]["witness"]
    assert w["text"].startswith("the beamtime folder's name")
    assert w["also"]["quote"] == "# 2031-01_Quillfeather" and w["also"]["file"] == "readme.txt"
    assert '; and "# 2031-01_Quillfeather" (readme.txt' in RV.render(RV.review(built))
    login = {"source_type": "document", "quote": "#C SYN User = quillfeather", "relation": "supports"}
    folder = {"source_type": "file_listing", "quote": "SYN_folder", "locator": RV.FOLDER_LOCATOR, "relation": "supports"}
    assert "also" not in RV.witness(B.FILL_GROUP_RULE_ID, GROUP, "Quillfeather group", [folder, login])


# --- round 4: a review is append-only history, so a later build can never make it an error ---------------------------------


def test_a_later_build_that_refuses_a_reviewed_value_unreviews_it_and_the_bundle_stays_valid(imported, tmp_path,
                                                                                         monkeypatch):
    """Accept a review; then a later build's vocabulary refuses one reviewed value, and a newer hold rule clears a
    reviewed candidate's value. The review decision is never an error: those two items stop binding (filled or
    missing again), every other item stays reviewed."""
    import shutil

    from test_local_import_fill_first import START, _reject_local_starts

    bdir = tmp_path / "one"
    shutil.copytree(imported[1], bdir)
    _chronoamperometry(bdir, imported[0])
    _convention(bdir, "operando")
    _add_group(bdir, run_ids=("run-001",))
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    _reject_local_starts(bdir, "run-001")
    R.build_records(bdir)
    _accept(bdir)
    b = M.load(bdir)
    reviewed = {o.get("candidate_id") or o.get("value_id") for o in _reviewed(b)}
    group_id = _miss(b, GROUP, None)["value_id"]
    [start] = [c for c in b["candidates"] if B.is_reviewed_fill(c) and c["target_field_path"] == START]
    assert group_id in reviewed and start["candidate_id"] in reviewed
    real = B.value_problem
    monkeypatch.setattr(B, "value_problem", lambda path, value: "SYN: no longer on the list"
                        if path == GROUP else real(path, value))
    later = copy.deepcopy(b)
    next(c for c in later["candidates"] if c["candidate_id"] == start["candidate_id"])["value"] = None
    derived = B.apply_derivations(later)
    assert B.validate_bundle(derived) == []  # the review decision is no error under the later build
    now = {o.get("candidate_id") or o.get("value_id"): o for o in [*derived["candidates"], *derived["missing_values"]]}
    assert not B.is_reviewed_fill(now[group_id]) and not B.is_reviewed_fill(now[start["candidate_id"]])
    assert all(B.is_reviewed_fill(now[i]) for i in reviewed - {group_id, start["candidate_id"]})
    assert {x["id"] for x in B.review_changed_since(derived)} == {group_id, start["candidate_id"]}
    errors, _ = B.validate_allowing_stale(b)  # the stored bundle, read by the later build
    assert not [e for e in errors if e.startswith("decision:")]


def test_the_beamline_row_shows_a_header_line_only_when_it_names_the_beamline(built):
    b = M.load(built)
    run = next(r for r in b["runs"] if r["run_id"] == "run-001")
    b["extended_context"].append({**b["extended_context"][0], "entry_id": "ec-SYN-fac", "run_id": run["run_id"],
                                  "source_id": run["acquisition_source_id"], "locator": "line 2 header #C",
                                  "raw_literal": "#C SYNTHETIC run at SSRL"})
    fields = {f["path"]: f for f in RV._listing(built, b, fields=None)["fields"]}
    assert fields[FACILITY]["values"][0]["witness"]["also"]["quote"] == "#C SYNTHETIC run at SSRL"
    assert "also" not in fields[BEAMLINE]["values"][0]["witness"]  # a facility-only line is no beamline witness


def test_the_environment_row_shows_the_set_point_and_what_shows_it_was_electrochemical(built):
    env = next(f for f in RV.review(built)["fields"] if f["path"] == ENV)
    w = env["values"][0]["witness"]
    assert w["quote"] == "100mV"
    assert "chronoamperometry" in w["also"]["quote"] and w["also"]["by"] == "a Claude reading of the files"
    assert "; and by a Claude reading of the files: \"SYNTHETIC: every ZzTestCat scan ran under chronoamperometry" \
        in RV.render(RV.review(built))
