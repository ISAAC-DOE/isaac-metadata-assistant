"""Polish c10-r: review findings on the c10-m per-scan Athena sets and the local-first skill.
SYNTHETIC files only: every scan and Athena project below is invented and named ``SYN_``.

* (H1) Copies of the same scans in SEVERAL projects are one curve only when their normalisation parameters are the
  same too, and the per-scan sets are formed per project FIRST. Before, a data hash alone kept each scan's first
  copy: when the first project's copies covered every scan, its set formed alone and a second project's other
  normalisation disappeared without a word (A[1,2]+B[1,2], A[1,2,3]+B[1,2], A[1,2]+B[2]; only A[1,2]+B[1,2,3]
  gave two versions). A project whose set is identical (same curves AND parameters) to another's is one set, and
  it is named.
* (H2) A set's identity names its members, so a selection recorded on ONE curve (the old per-scan "versions")
  never resolves to the set that holds it, nor a set's to one curve. When a re-processed result no longer holds
  the chosen version, `isaac process` says which choice is not carried over, and the question is asked again.
"""

from __future__ import annotations

import copy
import json
import shutil

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import.processing import athena as A

from test_local_import_capture_decisions import BY, _p1, _prov, _with_athena_result
from test_local_import_polish_c10m import _case, _process, _processing
from tests_support_records import pristine_bundle  # noqa: F401  (fixture)


# --- H1: a second project's normalisation never disappears ------------------------------------------------------

ORDERS = [([1, 2], [1, 2]), ([1, 2, 3], [1, 2]), ([1, 2], [2]), ([1, 2], [1, 2, 3])]


@pytest.mark.parametrize("swap", [False, True], ids=["a-first", "b-first"])
@pytest.mark.parametrize("first, second", ORDERS, ids=["A12+B12", "A123+B12", "A12+B2", "A12+B123"])
def test_a_second_projects_normalisation_is_its_own_version_in_every_order(tmp_path, first, second, swap):
    _processing()
    paths = ["a/SYN_one.prj", "b/SYN_two.prj"]
    sets = [(first, 60.0), (second, 90.0)]
    if swap:
        sets.reverse()
    bdir, root = _case(tmp_path, dict(zip(paths, sets)))
    out, isa, ath = _process(bdir, root)
    assert ath is None and isa["athena_result_of_record"] is None
    versions = isa["athena_versions"]
    assert [v["provenance"]["prj_relative_path"] for v in versions] == paths
    assert [v["provenance"]["scan_selection"] for v in versions] == [s for s, _ in sets]
    assert [v["provenance"]["params"]["nor1"] for v in versions] == [n for _, n in sets]
    for v, (scans, _) in zip(versions, sets):
        # a project of ONE per-scan group is that curve; of several, it is a set
        assert ("per_scan_set" in v["provenance"]) is (len(scans) > 1)
    [q] = isa["questions"]
    assert q["text"].startswith("2 different Athena versions of this measurement exist.")
    assert out["athena"]["record_groups_with_unselected_versions"] == 1
    assert not [n for n in out["athena"]["notes"] if n["code"] == "identical_athena_set_in_several_projects"]


def test_an_identical_set_in_another_project_is_one_set_and_is_named(tmp_path):
    _processing()
    bdir, root = _case(tmp_path, {"a/SYN_day1.prj": ([1, 2], 60.0), "b/SYN_copy.prj": ([1, 2], 60.0)})
    out, isa, ath = _process(bdir, root)
    assert "athena_versions" not in isa and ath is not None
    assert ath["inputs"][0]["relative_path"] == "a/SYN_day1.prj"
    assert ath["inputs"][0]["per_scan_set"]["identical_in_projects"] == ["b/SYN_copy.prj"]
    [note] = [n for n in out["athena"]["notes"] if n["code"] == "identical_athena_set_in_several_projects"]
    assert note == {**note, "group_id": isa["group_id"], "prj_relative_path": "a/SYN_day1.prj", "identical_in": ["b/SYN_copy.prj"]}
    assert note["statement"] == (
        "The scientist's per-scan Athena groups for scans 1, 2 in b/SYN_copy.prj are the same curves with the same "
        "normalisation parameters as those in a/SYN_day1.prj, so they are one set (read from a/SYN_day1.prj).")


def test_an_identical_set_among_different_ones_is_collapsed_and_named_on_its_version(tmp_path):
    _processing()
    bdir, root = _case(tmp_path, {"a/SYN_day1.prj": ([1, 2], 60.0), "b/SYN_copy.prj": ([1, 2], 60.0),
                                  "c/SYN_other.prj": ([1, 2], 90.0)})
    out, isa, _ = _process(bdir, root)
    versions = isa["athena_versions"]
    assert [v["provenance"]["prj_relative_path"] for v in versions] == ["a/SYN_day1.prj", "c/SYN_other.prj"]
    assert versions[0]["provenance"]["per_scan_set"]["identical_in_projects"] == ["b/SYN_copy.prj"]
    assert "identical_in_projects" not in versions[1]["provenance"]["per_scan_set"]
    assert [n["identical_in"] for n in out["athena"]["notes"] if n["code"] == "identical_athena_set_in_several_projects"] == [
        ["b/SYN_copy.prj"]]


# --- H2: a set's identity names its members ----------------------------------------------------------------------


def test_a_sets_identity_names_its_members_not_only_its_first_curve(tmp_path):
    _processing()
    bdir, root = _case(tmp_path, {"a/SYN_one.prj": ([1, 2], 60.0), "b/SYN_two.prj": ([1, 2], 90.0)})
    _, isa, _ = _process(bdir, root)
    prefixes = [v["provenance"]["data_sha256_prefix"] for v in isa["athena_versions"]]
    assert all(p.startswith(B.ATHENA_SET_IDENTITY_PREFIX) and len(p) == 20 for p in prefixes)
    assert len(set(prefixes)) == 2  # the same raw scans, other parameters: another set


def _set_version(n: int, prefix: str) -> dict:
    prov = {**_prov(n), "data_sha256_prefix": prefix,
            "per_scan_set": {"athena_groups": [f"SYN_grp_{n}", "SYN_grp_x"], "labels": ["a", "b"], "scans": [1, 2]}}
    return {"version_id": f"g1-v{n:02d}", "provenance": prov, "comparison": {}}


def test_one_curves_selection_never_resolves_to_a_set_nor_a_sets_to_one_curve():
    single = {k: _prov(1)[k] for k in B.ATHENA_IDENTITY_KEYS}
    # a set listed with its FIRST member's identity (as c10-m listed it): one curve's selection never resolves to it
    legacy = {"athena_versions": [_set_version(1, _prov(1)["data_sha256_prefix"])]}
    assert B.athena_resolve(legacy, {"value": "g1-v01", "athena_version_provenance": single}) is None
    # a set's selection never resolves to one curve, even one that claims the set's identity
    named = {**single, "data_sha256_prefix": "set-" + "a" * 16}
    lone = {"athena_versions": [{"version_id": "g1-v01", "provenance": {**_prov(1), "data_sha256_prefix": "set-" + "a" * 16}}]}
    assert B.athena_resolve(lone, {"value": "g1-v01", "athena_version_provenance": named}) is None
    # NEGATIVE CONTROL: the same set, and the same curve, still resolve
    assert B.athena_resolve({"athena_versions": [_set_version(1, "set-" + "a" * 16)]},
                            {"value": "g1-v09", "athena_version_provenance": named}) == "g1-v01"
    assert B.athena_resolve({"athena_versions": [{"version_id": "g1-v02", "provenance": _prov(1)}]},
                            {"value": "g1-v09", "athena_version_provenance": single}) == "g1-v02"


@pytest.fixture()
def athena(pristine_bundle, tmp_path):  # noqa: F811
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    _with_athena_result(bdir)
    return bdir


def _versions_as_g1(isa) -> list[dict]:
    out = []
    for n, v in enumerate(isa["athena_versions"], 1):
        out.append({**copy.deepcopy(v), "version_id": f"g1-v{n:02d}"})
    return out


def _install(bdir, versions) -> None:
    b = M.load(bdir)
    r = next(x for x in b["processing_results"] if x["result_id"] == "p1")
    r["athena_versions"] = versions
    r["questions"] = [B.athena_question(r)]
    M.save_bundle(bdir, b)


def test_a_legacy_set_version_cannot_be_selected_until_processed_again(athena):
    _install(athena, [_set_version(1, _prov(1)["data_sha256_prefix"]), {"version_id": "g1-v02", "provenance": _prov(2)}])
    with pytest.raises(M.MutationRefused, match="Run `isaac process` again"):
        M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    assert not [d for d in M.load(athena)["scientist_decisions"] if d["decision"] == "select_athena_version"]


@pytest.fixture(scope="module")
def old_and_new_versions(tmp_path_factory):
    """The same two projects listed by the OLD rule (every per-scan group a version) and by the current one (a set per
    project): real Athena projects, real processing."""
    _processing()
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("c10r_old")
    bdir, root = _case(tmp, {"a/SYN_one.prj": ([1, 2], 60.0), "b/SYN_two.prj": ([1, 2, 3], 90.0)})
    mp.setattr(A, "_per_scan_sets_by_project", lambda *a, **k: None)
    try:
        _, old, _ = _process(bdir, root)
    finally:
        mp.undo()
    _, new, _ = _process(bdir, root)
    return _versions_as_g1(old), _versions_as_g1(new)


@pytest.mark.parametrize("chosen", ["g1-v01", "g1-v03", "g1-v05"])
def test_an_old_single_curve_selection_is_not_carried_over_to_a_set_and_is_asked_again(
        athena, monkeypatch, old_and_new_versions, chosen):
    from isaac_api.local_import.processing import cli_entry

    old, new = old_and_new_versions
    assert len(old) == 5 and len(new) == 2  # A1, A2, B1, B2, B3 -> one set per project
    _install(athena, old)
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value=chosen, by=BY, orcid=None)
    d = M.load(athena)["scientist_decisions"][-1]
    if chosen == "g1-v01":
        # the trap: scan 1 of project a has the set's project file and Athena group (the set's first member)
        trio = ("prj_relative_path", "athena_group")
        assert {k: d["athena_version_provenance"][k] for k in trio} == {k: new[0]["provenance"][k] for k in trio}
    fresh = copy.deepcopy(_p1(athena))
    for k in ("athena_result_of_record_basis",):
        fresh.pop(k, None)
    fresh.update({"state": "candidate_extracted", "athena_versions": new, "athena_result_of_record": None,
                  "review_flags": ["protocol_draft_unreviewed", B.ATHENA_UNSELECTED_FLAG],
                  "steps": [{"step": "normalize", "params": {"fresh": True}, "outcome": {}, "flags": []}]})
    fresh["questions"] = [B.athena_question(fresh)]
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"processing_results": [fresh],
                                                                     "summary": {"lines": []}})
    out = M.process(athena)
    r = _p1(athena)
    # never ISAAC's mean of the set in the scientist's name; the fresh result, and the question again
    assert r["steps"][0]["params"] == {"fresh": True}
    assert r["athena_result_of_record"] is None and "athena_result_of_record_basis" not in r
    assert B.ATHENA_UNSELECTED_FLAG in r["review_flags"]
    [q] = r["questions"]
    assert q["code"] == B.ATHENA_QUESTION_CODE and q["version_ids"] == ["g1-v01", "g1-v02"]
    assert q["text"].endswith(f"The earlier choice {chosen} ({d['decision_id']}, by {BY}) is not one of the Athena "
                              "versions ISAAC lists now, so it is not carried over to another curve and the question "
                              "is asked again.")
    said = out["athena_selections_not_carried_over"]
    assert said["results"] == [{"result_id": "p1", "decision_id": d["decision_id"], "value": chosen}]
    assert said["statement"] == (
        f"1 earlier choice(s) of the Athena result of record no longer match a version ISAAC lists after this "
        f"re-processing (p1: {chosen} ({d['decision_id']}, by {BY})): the project files, or how ISAAC reads them, "
        "changed. It is not carried over to another curve: no version is selected for that result now, and the "
        "question \"Which one is the result of record?\" will be asked again.")
    assert said["statement"] in out["summary"]["lines"]
    assert out["kept_decided"] == 0
    assert cli.main(["bundle", "check", str(athena)]) == 0
    # processing again says it again (it is still unanswered), and still selects nothing
    out = M.process(athena)
    assert out["athena_selections_not_carried_over"]["results"][0]["value"] == chosen
    assert _p1(athena)["athena_result_of_record"] is None
    # answered again: it resolves, the note and the question drop out
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)
    r = _p1(athena)
    assert r["athena_result_of_record"] == "g1-v02" and B.ATHENA_NOT_CARRIED_OVER not in r and r["questions"] == []
    assert cli.main(["bundle", "check", str(athena)]) == 0


def test_a_hand_written_unresolved_selection_is_still_refused(athena):
    """NEGATIVE CONTROL: only the note `isaac process` writes for THAT decision lets it stand unresolved."""
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    bad = M.load(athena)
    d = bad["scientist_decisions"][-1]
    d["athena_version_provenance"]["data_sha256_prefix"] = "f" * 16
    r = next(x for x in bad["processing_results"] if x["result_id"] == "p1")
    r[B.ATHENA_NOT_CARRIED_OVER] = {"decision_id": "d-99999"}
    assert any("which is not one of the Athena versions p1 lists" in e for e in B.validate_bundle(bad))
    r[B.ATHENA_NOT_CARRIED_OVER] = {"decision_id": d["decision_id"]}
    assert not any("which is not one of the Athena versions p1 lists" in e for e in B.validate_bundle(bad))


def test_a_result_that_now_lists_no_versions_says_there_is_nothing_to_select(athena, monkeypatch):
    from isaac_api.local_import.processing import cli_entry

    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)
    fresh = copy.deepcopy(_p1(athena))
    for k in ("athena_versions", "athena_result_of_record", "athena_result_of_record_basis"):
        fresh.pop(k, None)
    fresh.update({"state": "candidate_extracted", "questions": [], "review_flags": ["protocol_draft_unreviewed"]})
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"processing_results": [fresh]})
    out = M.process(athena)
    r = _p1(athena)
    assert "athena_versions" not in r and r["questions"] == []
    assert r[B.ATHENA_NOT_CARRIED_OVER]["statement"].endswith("this result lists no Athena versions to choose between now.")
    assert out["athena_selections_not_carried_over"]["statement"].endswith(
        ", which now lists no Athena versions to choose between): the project files, or how ISAAC reads them, changed. "
        "It is not carried over to another curve: no version is selected for that result now.")
    assert cli.main(["bundle", "check", str(athena)]) == 0


# --- LOW-1/2: --as-said is the scientist's answer, and a request kept with it says so ----------------------------

from test_local_import_vocabulary_requests import ENV, REACTION, WHO as SAYER, _miss as _vr_miss  # noqa: E402


@pytest.fixture()
def vb(pristine_bundle, tmp_path):  # noqa: F811
    bdir = tmp_path / "vb"
    shutil.copytree(pristine_bundle, bdir)
    return bdir


def _cli_decide(bdir, capsys, *args):
    capsys.readouterr()
    code = cli.main(["bundle", "decide", str(bdir), *args, "--by", SAYER])
    got = capsys.readouterr()
    return code, got.out, got.err


@pytest.mark.parametrize("decision", ["defer", "reject"])
def test_as_said_with_any_decision_but_confirm_or_correct_is_refused(vb, capsys, decision):
    before = (vb / "bundle.json").read_bytes()
    code, _, err = _cli_decide(vb, capsys, "--target", _vr_miss(vb, ENV)["value_id"], "--decision", decision,
                               "--value", "outdoors", "--as-said")
    assert code == 2 and M.AS_SAID_ONLY_AN_ANSWER in err
    assert (vb / "bundle.json").read_bytes() == before
    with pytest.raises(M.MutationRefused, match="--as-said goes only with --decision confirm or correct"):
        M.decide(vb, target_ids=[_vr_miss(vb, ENV)["value_id"]], decision=decision, value="outdoors", by=SAYER, orcid=None,
                 as_said=True)


def test_as_said_on_a_value_the_field_accepts_is_recorded_and_says_nothing_was_kept(vb, capsys):
    code, out, err = _cli_decide(vb, capsys, "--target", _vr_miss(vb, ENV)["value_id"], "--decision", "correct",
                                 "--value", "ex_situ", "--as-said")
    assert code == 0, err
    assert json.loads(out)["statement"].endswith(M.AS_SAID_ON_LIST)
    assert not M.load(vb).get("vocabulary_requests")


def test_a_request_kept_with_as_said_records_it(vb, capsys):
    code, _, err = _cli_decide(vb, capsys, "--target", _vr_miss(vb, REACTION)["value_id"], "--decision", "correct",
                               "--value", "cathodic corrosion", "--as-said")
    assert code == 2 and "kept as a vocabulary request" in err
    [req] = M.load(vb)["vocabulary_requests"]
    assert req["source"]["as_said"] is True
    assert B.check_bundle(vb) == []


# --- LOW-3: no `scopes` key on a hint ----------------------------------------------------------------------------

from test_local_import_polish_c10m import ENV as C10M_ENV, _annotated, _env_question  # noqa: E402
from test_local_import_records import bdir, pristine  # noqa: E402,F401  (fixtures)


def test_differing_ai_suggestions_add_no_key_to_any_hint_and_a_group_still_leads_with_its_own(bdir, capsys):  # noqa: F811
    _annotated(bdir, ["ex_situ", "in_situ", "in_situ"])
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(bdir), "--limit", "200", "--with-targets"]) == 0
    page = json.loads(capsys.readouterr().out)["questions"]
    ai = [h for q in page for h in q.get("hints") or () if h.get("kind") == "ai_suggestion"]
    assert ai and not any("scopes" in h or "read_in_scopes" in h for h in ai)
    payload = Q.consolidate(M.load(bdir))
    assert not any("scopes" in h for q in payload["questions"] for h in q.get("hints") or ())
    # the scoped lead (c10-m) is unchanged
    mine = _env_question(Q.filter_questions(payload, scope="group:g0"))
    assert [h["literal"] for h in mine["hints"] if h["kind"] == "ai_suggestion"] == ["ex_situ", "in_situ"]
    assert C10M_ENV == "context.environment"


# --- LOW-4: a group page shows the covering question in that group's words ---------------------------------------

from test_local_bundles_parity import _client, grouped  # noqa: E402,F401  (fixture)


def test_a_group_page_shows_the_covering_question_led_by_the_suggestion_read_for_the_group(grouped, monkeypatch, tmp_path):  # noqa: F811
    real = Q.consolidate
    first = real(M.load(grouped))
    covered = next(q for q in first["questions"] if str(q.get("covered_by", "")).startswith("Q-"))
    scope, cover = covered["scope"], covered["covered_by"]
    a = {"kind": "ai_suggestion", "literal": "SYN-A", "source_path": "SYN_a.txt", "locator": "line 1", "targets": 2}
    b = {"kind": "ai_suggestion", "literal": "SYN-B", "source_path": "SYN_b.txt", "locator": "line 2", "targets": 1}

    def consolidate(bundle, **kw):
        payload = real(bundle, **kw)
        q = Q.question(payload, cover)
        ai = [Q._ScopedHint(a, ["experiment"]), Q._ScopedHint(b, [scope])]
        q["hints"] = ai + list(q.get("hints") or ())
        q["text"] += Q._ai_sentence(ai)
        return payload

    monkeypatch.setattr(Q, "consolidate", consolidate)
    client = _client(grouped.parent, monkeypatch, tmp_path)
    shown = {q["question_id"]: q for q in client.get("/api/local-bundles/alpha/questions", params={"scope": scope}).json()["questions"]}
    said = shown[covered["question_id"]]["display"]["covered_by"]
    assert said["question_id"] == cover
    assert "An AI reading of the files suggests 'SYN-B'" in said["text"] and "suggests 'SYN-A'" not in said["text"]
    # NEGATIVE CONTROL: unscoped, the covering question's own words
    whole = {q["question_id"]: q for q in client.get("/api/local-bundles/alpha/questions").json()["questions"]}
    assert "An AI reading of the files suggests 'SYN-A'" in whole[covered["question_id"]]["display"]["covered_by"]["text"]


# --- LOW-5: groups_count is decide's reach, "N of M" -------------------------------------------------------------

from test_local_import_polish_c7r import _groups, _only  # noqa: E402
from test_local_import_polish_c7s import _technique_question, plain, plain_base  # noqa: E402,F401  (fixtures)
from test_local_import_template_adopt import WHO as ADOPTER  # noqa: E402


def _listed(capsys, bdir, qid):
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(bdir), "--limit", "200"]) == 0
    return next(q for q in json.loads(capsys.readouterr().out)["questions"] if q["question_id"] == qid)


def test_a_beamtime_questions_groups_count_is_the_reach_decide_states(plain, capsys):  # noqa: F811
    qid, groups = _technique_question(plain), _groups(plain)
    before = _listed(capsys, plain, qid)
    assert before["groups_count"] == len(groups) and "groups_total" not in before
    _only(capsys, plain, qid, groups[0], "XAS")
    q = _listed(capsys, plain, qid)
    planned = M.decide_question(plain, question_id=qid, decision="correct", value="HERFD-XAS", by=ADOPTER, orcid=None,
                                dry_run=True)
    n, m = planned["reach"]["groups_reached"], planned["reach"]["groups"]
    assert f"It reaches {n} of the beamtime's {m} record groups" in planned["statement"]
    assert (q["groups_count"], q["groups_total"]) == (n, m) == (len(groups) - 1, len(groups))
    assert q["applies_to"]["groups"] == m and q["applies_to"]["groups_reached"] == n


# --- LOW-6: an Athena set that includes a scan ISAAC skipped is a different set -----------------------------------


def test_a_curve_with_a_scan_isaac_did_not_merge_is_a_different_set_not_only_part():
    from isaac_api.local_import.processing import run as RUN

    said = RUN._athena_scans_used({"label": "SYN_x_1-3", "params": {}}, ["SYN_x"], (2, 3), None, [1, 2])["statement"]
    assert "It is a different set of scans from the 2 ISAAC merged: it includes scan 3, which ISAAC did not merge" in said
    assert "covers only" not in said
    left = RUN._athena_scans_used({"label": "SYN_x_2-3", "params": {}}, ["SYN_x"], (2, 3), None, [1, 2])["statement"]
    assert "it includes scan 3, which ISAAC did not merge, and leaves out scan 1:" in left
    # NEGATIVE CONTROL: a true subset still says "covers only"
    part = RUN._athena_scans_used({"label": "SYN_x_1", "params": {}}, ["SYN_x"], (2, 2), None, [1, 2])["statement"]
    assert "It covers only scan 1 of the 2 scans ISAAC merged" in part
    isa = {"group_id": "g1", "source": "isaac_protocol", "run_id": None,
           "inputs": [{"scan": 1}, {"scan": 2}, {"scan": 3, "skip_reason": "too_few_points"}]}
    ath = {"group_id": "g1", "source": "scientist_athena", "run_id": None,
           "comparison": {"flags": ["scientist_selected_subset_of_scans"], "athena_scan_selection": [1, 2, 3]}}
    note = M.scan_subset_note({"processing_results": [isa, ath]}, ath)
    assert note.startswith("The scientist's Athena curve for group g1 uses a different set of scans (1, 2, 3) from the 2 "
                           "scan(s) ISAAC merged, including scan(s) 3 that ISAAC did not merge")
    ath["comparison"]["athena_scan_selection"] = [1]
    assert "uses only scans 1 of the 2 scan(s) ISAAC merged" in M.scan_subset_note({"processing_results": [isa, ath]}, ath)
