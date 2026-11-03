"""Round-8 polish of the condition labels (labels.py). SYNTHETIC fixtures only: every name, number and value is invented.

A beamtime whose files are named ``<electrode>_<step>_<sample>_...`` (the second number is a step, read beside several
sample names) must not be read as if the second number were the electrode: ISAAC asks ONE beamtime-level question,
"which file-name number is the electrode?", and proposes per electrode from the answer. Follows links come from the
scientist's sample ids too, every held chain is said, a group ISAAC proposed nothing for stays asked, a disagreement
answer feeds the label it settles, and the readings that disagree are named with their files.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import labels as L
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
TEMPLATE = "04_02_ZZ2_base_after500Cycling_filter20_800mV"
FOLDER = "SYN_QQ_2099-02_Fake_Acid"
#: invented electrode 01 of sample ZZ1 at three stages, electrode 02 of ZZ2 at two, electrode 03 of ZZ1 at one; the
#: second number is the STEP, so it is read beside two sample names
E1 = ("01_01_ZZ1_base_beforeCycling_filter10_060mV", "01_02_ZZ1_base_after1200Cycling_filter10_060mV",
      "01_03_ZZ1_base_after1500Cycling_filter10_060mV")
E2 = ("02_01_ZZ2_base_beforeCycling_filter10_060mV", "02_02_ZZ2_base_after1200Cycling_filter10_060mV")
E3 = ("03_01_ZZ1_base_beforeCycling_filter10_060mV",)
STEMS = (*E1, *E2, *E3)
BY = dict(by="Synthetic Scientist", orcid=None)


def _corpus(tmp: Path) -> Path:
    out = tmp / FOLDER
    out.mkdir()
    for name in ("Zz_XAS.mac", "readme.txt", "2099 SYNTHETIC semantics notes.txt"):
        shutil.copy(SEMANTICS / name, out / name)
    for n, stem in enumerate(STEMS):
        # the file-creation instant (#E) follows the list order; the first number (the electrode) is no run counter
        text = (SEMANTICS / TEMPLATE).read_text(encoding="utf-8").replace(TEMPLATE, stem)
        (out / stem).write_text(text.replace("#E 4102447200", f"#E {4102447200 + 3600 * (n + 1)}"), encoding="utf-8")
        (out / f"{stem}_dir").mkdir()
        for dat in sorted((SEMANTICS / f"{TEMPLATE}_dir").glob("*.dat")):
            (out / f"{stem}_dir" / dat.name.replace(TEMPLATE, stem)).write_text(
                dat.read_text(encoding="utf-8").replace(TEMPLATE, stem), encoding="utf-8")
    (out / "run01.mac").write_text("# SYNTHETIC FIXTURE -- read as TEXT, never executed.\nqdo Zz_XAS.mac\n"
                                   + "".join(f"newfile {s}\n" for s in STEMS), encoding="utf-8")
    return out


@pytest.fixture(scope="module")
def grouped_pristine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("labels_r8")
    out = tmp / "bundle"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def bdir(grouped_pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(grouped_pristine, target)
    return target


def _lq(b: dict, label: str, partition: str | None = None, **kw) -> dict | None:
    return next((q for q in L.label_questions(b, **kw) if q["label"] == label
                 and (partition is None or q["partition"] == partition)), None)


def _answer(bdir: Path, qid: str, decision: str = "confirm", **kw):
    return M.decide_question(bdir, question_id=qid, decision=decision, value=kw.pop("value", None),
                             only=kw.pop("only", None), field=None, **BY, **kw)


def _gid(b: dict, stem: str) -> str:
    key = next(r["run_key"] for r in b["runs"] if r["stem"] == stem)
    return next(g["group_id"] for g in Q.live_groups(b) if key in g["member_run_keys"])


def _slot(b: dict, path: str, stem: str):
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == stem)
    m = next((m for m in b["missing_values"] if L.is_label_slot(m) and m["target_field_path"] == path
              and m["run_id"] == rid), None)
    return None if m is None else B._decisions_by_target(b["scientist_decisions"])[("missing_value", m["value_id"])]["value"]


def _decision(b: dict, kind: str, **fields) -> None:
    b["scientist_decisions"].append({
        "decision_id": f"d-{len(b['scientist_decisions']) + 1:05d}", "target": {"kind": "experiment", "id": "experiment"},
        "decision": kind, "value": None, "chosen_reading_index": None,
        "decided_by": {"name": "Synthetic Scientist", "basis": "self_reported_local_user", "identity": "local_unverified",
                       "orcid_claimed": None},
        "decided_utc": "2099-01-01T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None, **fields})


# --- HIGH 1: the electrode position is asked, never assumed --------------------------------------


def test_the_electrode_number_is_asked_once_never_assumed_to_be_the_second(bdir):
    b = M.load(bdir)
    sid = _lq(b, "sample_id")
    assert not sid["proposals"] and len(sid["not_proposed"]) == len(STEMS)
    held = {h["first_file"]: h["reason"] for h in sid["not_proposed"]}
    assert "position 2 (here 02)" in held[E1[1]] and L.ELECTRODE_QUESTION_ID in held[E1[1]]
    pos = _lq(b, "electrode_position")
    assert pos["question_id"] == L.ELECTRODE_QUESTION_ID == L.question_id("electrode_position")
    assert pos["scope"] == "experiment" and pos["allowed_decisions"] == ["correct", "reject"]
    cands = {c["position"]: c for c in pos["candidate_positions"]}
    assert set(cands) == {1, 2}
    assert cands[1]["numbers_beside_several_sample_names"] == 0 and cands[2]["numbers_beside_several_sample_names"] == 2
    assert "01_01_ZZ1" in pos["text"] and "position 2" in pos["text"]


def test_a_not_counter_answer_is_evidence_never_the_electrode(bdir):
    b = M.load(bdir)
    _decision(b, B.NOT_COUNTER_DECISION, not_counter_positions=[1, 2])
    assert not _lq(b, "sample_id")["proposals"], "'not a counter' alone is never 'is the electrode'"
    text = _lq(b, "electrode_position")["text"]
    assert "not run counters" in text and "does not say which one is the electrode" in text


def test_a_counter_answer_rules_a_position_out(bdir):
    b = M.load(bdir)
    _decision(b, "set_counter_positions", positions=[2])
    pos = _lq(b, "electrode_position")
    assert [c["position"] for c in pos["candidate_positions"]] == [1] and pos["ruled_out_positions"] == [2]
    assert not _lq(b, "sample_id")["proposals"], "one position left is still asked, never taken"


def test_the_answer_proposes_one_id_per_electrode(bdir):
    qid = L.ELECTRODE_QUESTION_ID
    with pytest.raises(M.MutationRefused, match="not one of the file-name positions"):
        _answer(bdir, qid, "correct", value="5")
    out = _answer(bdir, qid, "correct", value="1")
    assert "file-name number 1" in out["statement"] and "3 id(s) for 6 group(s)" in out["statement"]
    b = M.load(bdir)
    sid = _lq(b, "sample_id")
    ids = {p["first_file"]: p["value"] for p in sid["proposals"]}
    assert {ids[s] for s in E1} == {f"{FOLDER}:ZZ1-01"} and {ids[s] for s in E2} == {f"{FOLDER}:ZZ2-02"}
    assert ids[E3[0]] == f"{FOLDER}:ZZ1-03", "electrode 03 of ZZ1 is another physical sample"
    assert all(i in sid["text"] for i in set(ids.values())), "every id is read back"
    # answered: out of the open list, still found under its id; never a record field
    assert _lq(b, "electrode_position") is None and _lq(b, "electrode_position", include_answered=True)["answered"]
    _answer(bdir, sid["question_id"])
    draft, _ = R.compose_group(M.load(bdir), next(g for g in Q.live_groups(M.load(bdir))
                                                  if g["group_id"] == _gid(b, E1[0])), bdir)
    assert L.POSITION_PATH not in draft["fields"] and draft["fields"][L.SAMPLE_ID_PATH]["value"] == f"{FOLDER}:ZZ1-01"


def test_existing_questions_keep_their_ids_kinds_scopes_and_targets(bdir):
    def shape(payload):
        return {q["question_id"]: (q["kind"], q["scope"], sorted(t["id"] for t in q["targets"]))
                for q in payload["questions"] if q["kind"] != L.KIND}
    before = {k: shape(Q.consolidate(M.load(bdir), include_answered=k)) for k in (False, True)}
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")
    _answer(bdir, _lq(M.load(bdir), "sample_id")["question_id"])
    after = {k: shape(Q.consolidate(M.load(bdir), include_answered=k)) for k in (False, True)}
    assert after == before


# --- HIGH 2: follows from confirmed ids; every held chain said -----------------------------------


def test_follows_come_from_the_scientists_sample_ids_ordered_by_start_times(bdir):
    b = M.load(bdir)
    assert not (_lq(b, "follows") or {}).get("proposals"), "no electrode, no id: nothing to chain"
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")  # the run number is the electrode: no Q16 tie
    qid = _lq(b, "sample_id")["question_id"]
    # the scientist names electrode 01 of ZZ1 their own way, on its first group; the id is the electrode's
    _answer(bdir, qid, "correct", value="SYN-ZZ1-e1", only=f"group:{_gid(b, E1[0])}")
    b = M.load(bdir)
    assert {_slot(b, L.SAMPLE_ID_PATH, s) for s in E1} == {"SYN-ZZ1-e1"}
    fo = _lq(b, "follows")
    pairs = {(p["said"]["after"], p["said"]["before"]) for p in fo["proposals"]}
    assert pairs == {(E1[1], E1[0]), (E1[2], E1[1]), (E2[1], E2[0])}
    assert {p["said"]["order_basis"] for p in fo["proposals"]} == {"start_times"}, "the run numbers are the electrode"
    assert all(s in fo["text"] for s in E1), "every link is read back"


def test_a_held_chain_is_always_said_and_a_typed_history_is_a_stage(bdir):
    b = M.load(bdir)
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")
    b = M.load(bdir)
    g = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, E2[1]))
    g["basis"]["conditions"]["cycling_state"] = {"kind": "conflicting", "readings": ["after1200cycling", "x"],
                                                 "candidate_ids": []}
    fo = _lq(b, "follows")
    held = [h for h in fo["not_proposed"] if E2[1] in h["first_files"]]
    assert held and "no settled history stage" in held[0]["reason"] and E2[1] in fo["text"]
    # the scientist's own history answer counts as the stage
    L.decide(b, _lq(b, "history", "history=unsettled"), decision="correct", value="after synthetic cycling",
             only=f"group:{g['group_id']}", note=None, **BY)
    pairs = {(p["said"]["after"], p["said"]["before"]) for p in _lq(b, "follows")["proposals"]}
    assert (E2[1], E2[0]) in pairs


def test_a_follows_question_with_only_held_chains_is_informational(bdir):
    b = M.load(bdir)
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")
    b = M.load(bdir)
    for s in (E1[1], E2[1]):
        g = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, s))
        g["basis"]["conditions"]["cycling_state"] = {"kind": "conflicting", "readings": ["a", "b"], "candidate_ids": []}
    q = _lq(b, "follows")
    assert q["informational"] and q["allowed_decisions"] == [] and len(q["not_proposed"]) == 2
    with pytest.raises(L.LabelRefused, match="proposes no link"):
        L.decide(b, q, decision="confirm", value=None, only=None, note=None, **BY)


# --- MED 3: --same-sample is refused across sample names and electrode numbers -------------------


def test_same_sample_is_refused_across_sample_names_naming_files(bdir):
    b = M.load(bdir)
    qid = _lq(b, "sample_id")["question_id"]
    _answer(bdir, qid, "correct", value="SYN-ZZ1-e1", only=f"group:{_gid(b, E1[0])}")
    with pytest.raises(M.MutationRefused) as exc:
        _answer(bdir, qid, "correct", value="SYN-ZZ1-e1", only=f"group:{_gid(b, E2[0])}", same_sample=True)
    assert E1[0] in str(exc.value) and E2[0] in str(exc.value) and "run-0" not in str(exc.value)
    # the same sample name, but another number where the electrode number is (once that position is known)
    b = M.load(bdir)
    facts = {f.stems[0]: f for f in L._facts(b, Q.live_groups(b))}
    assert L._same_sample_problem(facts[E1[0]], facts[E3[0]], None) is None, "the position is not known yet"
    said = L._same_sample_problem(facts[E1[0]], facts[E3[0]], 1)
    assert said and E1[0] in said and E3[0] in said and "position 1" in said
    assert L._same_sample_problem(facts[E1[0]], facts[E1[1]], 1) is None, "one electrode at two steps"


# --- MED 4: the groups ISAAC proposed nothing for stay asked -------------------------------------


def _hold_filter(b: dict, stem: str) -> str:
    g = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, stem))
    g["basis"]["conditions"]["filter"] = {"kind": "conflicting", "readings": ["10", "20"], "candidate_ids": []}
    return g["group_id"]


def test_a_bulk_confirm_keeps_a_residual_question_and_says_who_is_left(bdir):
    b = M.load(bdir)
    held = _hold_filter(b, E3[0])
    out = L.decide(b, _lq(b, "filter"), decision="confirm", value=None, only=None, note=None, **BY)
    assert f"1 group(s) still have no filter: {E3[0]}" in out["statement"]
    assert _lq(b, "filter", None) is not None
    res = _lq(b, "filter", L.RESIDUAL)
    assert res["question_id"] == L.question_id("filter", L.RESIDUAL) != L.question_id("filter")
    assert [h["group_id"] for h in res["not_proposed"]] == [held] and res["allowed_decisions"] == ["correct", "reject"]
    assert _lq(b, "filter", None)["partition"] == L.RESIDUAL, "the label's own question is answered"
    L.decide(b, res, decision="correct", value="SYN filter wording", only=f"group:{held}", note=None, **BY)
    assert _lq(b, "filter") is None and _slot(b, L.FILTER_PATH, E3[0]) == "SYN filter wording"


def test_several_groups_take_one_value_in_one_call(bdir):
    b = M.load(bdir)
    gids = [_gid(b, s) for s in (E1[0], E2[0])]
    qid = _lq(b, "sample_id")["question_id"]
    with pytest.raises(M.MutationRefused, match="same id"):
        _answer(bdir, qid, "correct", value="SYN-shared", only=[f"group:{g}" for g in gids])
    code = cli.main(["bundle", "decide", str(bdir), "--question", qid, "--only", f"group:{gids[0]}",
                     "--only", f"group:{_gid(b, E3[0])}", "--decision", "reject", "--by", BY["by"]])
    assert code == 0
    b = M.load(bdir)
    assert all(_slot(b, L.SAMPLE_ID_PATH, s) is None for s in (E1[0], E3[0]))
    assert len([d for d in b["scientist_decisions"] if d["decision"] == "reject"]) >= 2


# --- MED 5: a disagreement answer feeds the label it settles --------------------------------------


def _filter_conflict(b: dict, stem: str) -> str:
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == stem)
    _hold_filter(b, stem)
    cid = "conf-990"
    b["conflicts"].append({"conflict_id": cid, "engine_conflict_id": f"{stem}::filter", "kind": "field_disagreement",
                           "subject": "filter", "run_ids": [rid], "readings": [
                               {"reading_index": 0, "value": "10", "witnesses": [
                                   {"source_id": "src-x", "relative_path": stem, "locator": "line 36 header #P0 column 3 (scan 1)"}]},
                               {"reading_index": 1, "value": "20", "witnesses": [
                                   {"source_id": "src-x", "relative_path": stem, "locator": "line 90 header #P0 column 3 (scan 2)"}]}]})
    return cid


def _conflict_decision(b: dict, cid: str, value: str) -> None:
    M.record_decision(b, target_ids=[cid], decision="confirm", value=value, **BY)


def test_the_readings_that_disagree_are_named_with_their_files(bdir):
    b = M.load(bdir)
    _filter_conflict(b, E3[0])
    held = next(h for h in _lq(b, "filter")["not_proposed"] if h["first_file"] == E3[0])
    assert [r["value"] for r in held["readings"]] == ["10", "20"] and held["readings"][0]["file"] == E3[0]
    assert "10 (03_01_ZZ1" in held["reason"] and "scan header, scan 2" in held["reason"]


def test_a_settled_disagreement_is_proposed_and_fed_to_the_label(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    gid = _gid(b, E3[0])
    L.decide(b, _lq(b, "filter"), decision="confirm", value=None, only=None, note=None, **BY)  # the others
    # the disagreement's own question points at the label question
    qs = [{"kind": "resolve_conflict", "question_id": "Q-0000000000", "targets": [{"kind": "conflict", "id": cid}],
           "why": "old"}, *L.label_questions(b)]
    L.point_conflicts_at_labels(qs, b, {r: gid for r in next(f.runs for f in L._facts(b, Q.live_groups(b)) if f.gid == gid)})
    # r8 recheck LOW 2: the question that carries the value once settled (never the residual one)
    assert qs[0]["label_question"] == L.question_id("filter") and "changes no record" not in qs[0]["why"]
    _conflict_decision(b, cid, "20")
    item = next(i for i in _lq(b, "filter", include_answered=True)["proposals"] if i["group_id"] == gid)
    assert item["value"] == "filter20" and item["said"]["from_decisions"]
    fed = L.feed_from_conflicts(b, [cid], **BY)
    assert fed["recorded"] and _slot(b, L.FILTER_PATH, E3[0]) == "filter20" and E3[0] in fed["statement"]


def test_a_disagreement_answer_records_nothing_before_the_label_is_answered(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    _conflict_decision(b, cid, "20")
    fed = L.feed_from_conflicts(b, [cid], **BY)
    assert not fed["recorded"] and "now proposes 'filter20'" in fed["statement"]
    assert _slot(b, L.FILTER_PATH, E3[0]) is None


# --- LOW ------------------------------------------------------------------------------------------


def test_the_filter_question_says_zero_is_no_filter_and_invents_no_material(bdir):
    b = M.load(bdir)
    g = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, E3[0]))
    g["basis"]["conditions"]["filter"] = {**g["basis"]["conditions"]["filter"], "value": "0"}
    text = _lq(b, "filter")["text"]
    assert "filter0 (1 group(s)) is a count of 0: no filter" in text and "Al " not in text


def test_a_typed_filter_the_files_contradict_is_named(bdir):
    b = M.load(bdir)
    out = L.decide(b, _lq(b, "filter"), decision="correct", value="filter20", only=f"group:{_gid(b, E1[0])}",
                   note=None, **BY)
    assert out["contradicts_files"] and "contradicts the files" in out["statement"]
    assert "files read 10" in out["statement"] and _slot(b, L.FILTER_PATH, E1[0]) == "filter20"


def test_a_group_scope_shows_only_that_groups_row():
    q = {"question_id": "Q-0000000001", "label": "filter", "kind": L.KIND, "target_field_path": L.FILTER_PATH,
         "applies_to": {"groups": 2}, "targets": [{"kind": "run", "id": "r1"}, {"kind": "run", "id": "r2"}],
         "proposals": [{"group_id": "g1", "run_ids": ["r1"], "value": "filter10", "first_file": "SYN_1"},
                       {"group_id": "g2", "run_ids": ["r2"], "value": "filter20", "first_file": "SYN_2"}],
         "not_proposed": [], "hints": [], "text": "long"}
    one = L.for_group(q, "group:g2")
    assert [p["group_id"] for p in one["proposals"]] == ["g2"] and one["targets"] == [{"kind": "run", "id": "r2"}]
    assert "SYN_2" in one["text"] and "bundle show <bundle_dir> question Q-0000000001" in one["text"]


def test_validate_warns_on_two_ready_records_one_sample_one_condition_set(bdir):
    b = M.load(bdir)
    g1, g2 = _gid(b, E1[0]), _gid(b, E3[0])
    same = {"fields": {L.SAMPLE_ID_PATH: {"value": "SYN-1"}, "context.environment": {"value": "in_situ"}}}
    ws = L.record_warnings(b, [(g1, same, {}), (g2, copy.deepcopy(same), {})], [g1, g2])
    hit = [w for w in ws if w["code"] == L.SAME_RECORD_WARNING]
    assert len(hit) == 2 and E1[0] in hit[0]["text"] and E3[0] in hit[0]["text"]
    assert not [w for w in L.record_warnings(b, [(g1, same, {})], [g1]) if w["code"] == L.SAME_RECORD_WARNING]


def test_an_in_situ_note_on_many_records_is_said_once_with_every_file():
    def note(stem: str, gid: str) -> str:
        return (f"Written without what it was measured in: an in-situ record that carries no electrolyte or cell type: "
                f"what it was measured in would be absent from the record; the file names state 1MSYNA ({stem}) "
                f"(quoted, never read as a value). Ask the scientist (question Q-0123456789 (electrolyte)), e.g. isaac "
                f"bundle questions <bundle_dir> --scope group:{gid}   # answer it there")
    rows = R.group_by_text([[note("SYN_A_1MSYNA", "rg-aaaaaaaaaaaa")], [note("SYN_B_1MSYNA", "rg-bbbbbbbbbbbb")]])
    assert len(rows) == 1 and rows[0]["records"] == 2
    assert rows[0]["files"] == ["SYN_A_1MSYNA", "SYN_B_1MSYNA"] and rows[0]["quoted"] == ["1MSYNA"]
    assert "SYN_B_1MSYNA" in R.grouped_sentence(rows)


def test_the_group_list_flags_a_group_merging_scans_read_at_different_conditions(bdir):
    b = M.load(bdir)
    g = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, E1[0]))
    g["split_reasons"] = [*(g.get("split_reasons") or ()), {"code": "conflicting_condition", "condition": "filter",
                                                          "readings": ["0", "6"]}]
    row = cli.group_list_extras(b)[g["group_id"]]
    assert row["needs_care"]["conditions"] == ["filter"] and "different filter" in row["needs_care"]["note"]
    assert "0" not in json.dumps(row["needs_care"]["conditions"]), "no reading printed on a list row"


# --- review of 9c10c878: H1, H2, L1-L3 --------------------------------------------------------------------------------


def _set_run_number(b: dict, stems, n: int) -> None:
    for r in b["runs"]:
        if r["stem"] in stems:
            r["legacy_number"] = n


def test_h1_stages_sharing_a_run_number_that_is_not_their_electrode_are_held(bdir):
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")
    b = M.load(bdir)
    pairs = {(p["said"]["after"], p["said"]["before"]) for p in _lq(b, "follows")["proposals"]}
    assert (E2[1], E2[0]) in pairs, "the run number IS the electrode (01, 02): the file times order its stages"
    _set_run_number(b, E2, 7)  # one run number, not the electrode's, on two stages: Q16 stays open (DEC-46)
    fo = _lq(b, "follows")
    assert (E2[1], E2[0]) not in {(p["said"]["after"], p["said"]["before"]) for p in fo["proposals"]}
    held = next(h for h in fo["not_proposed"] if E2[0] in h["first_files"])
    assert "share run number 7" in held["reason"] and "Q16" in held["reason"] and "DEC-46" in held["reason"]
    assert {(p["said"]["after"], p["said"]["before"]) for p in fo["proposals"]} >= {(E1[1], E1[0])}


def test_h1_without_an_electrode_position_a_shared_run_number_orders_nothing(bdir):
    b = M.load(bdir)
    qid = _lq(b, "sample_id")["question_id"]
    _answer(bdir, qid, "correct", value="SYN-ZZ1-e1", only=f"group:{_gid(b, E1[0])}")
    _answer(bdir, qid, "correct", value="SYN-ZZ1-e1", only=[f"group:{_gid(b, s)}" for s in E1[1:]], same_sample=True)
    fo = _lq(M.load(bdir), "follows")
    assert not fo["proposals"] and L.ELECTRODE_QUESTION_ID in fo["text"], "is the shared number the electrode? ask"


def test_h2_an_only_answer_is_never_repeated_for_another_group(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    # their own wording for ONE group, and a confirm for one other: neither is an answer for the whole question
    L.decide(b, _lq(b, "filter"), decision="correct", value="10 um SYN foil", only=f"group:{_gid(b, E1[0])}", note=None, **BY)
    L.decide(b, _lq(b, "filter"), decision="confirm", value=None, only=f"group:{_gid(b, E1[1])}", note=None, **BY)
    _conflict_decision(b, cid, "20")
    fed = L.feed_from_conflicts(b, [cid], **BY)
    assert not fed["recorded"] and "now proposes 'filter20'" in fed["statement"] and "answer it there" in fed["statement"]
    assert _slot(b, L.FILTER_PATH, E3[0]) is None, "no material, no thickness, nothing invented"


def test_h2_a_whole_question_pattern_is_repeated_as_the_scientist_stored_it(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    L.decide(b, _lq(b, "filter"), decision="correct", value="{filter} SYN filters", only=None, note=None, **BY)
    _conflict_decision(b, cid, "20")
    fed = L.feed_from_conflicts(b, [cid], **BY)
    assert _slot(b, L.FILTER_PATH, E3[0]) == "20 SYN filters" and "your one answer to that whole question" in fed["statement"]


def test_h2_a_group_specific_history_sentence_is_not_copied(bdir):
    b = M.load(bdir)
    stem = E2[1]
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == stem)
    g = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, stem))
    g["basis"]["conditions"]["cycling_state"] = {"kind": "conflicting", "readings": ["after1200cycling", "after1200cv"],
                                                 "candidate_ids": []}
    b["conflicts"].append({"conflict_id": "conf-991", "engine_conflict_id": f"{stem}::cycling_state",
                           "kind": "field_disagreement", "subject": "cycling_state", "run_ids": [rid], "readings": [
                               {"reading_index": 0, "value": "after1200Cycling", "witnesses": [
                                   {"source_id": "s", "relative_path": stem, "locator": "filename token 5"}]},
                               {"reading_index": 1, "value": "after1200CV", "witnesses": [
                                   {"source_id": "s", "relative_path": "MERGE/SYN.txt", "locator": "filename token 5"}]}]})
    q = _lq(b, "history", "history=after1200cycling")
    L.decide(b, q, decision="correct", value="SYN sentence for one electrode", only=f"group:{_gid(b, E1[1])}", note=None, **BY)
    _conflict_decision(b, "conf-991", "after1200Cycling")
    assert not L.feed_from_conflicts(b, ["conf-991"], **BY)["recorded"] and _slot(b, L.HISTORY_PATH, stem) is None


def test_l1_the_position_reply_says_it_applies_to_settled_groups_and_names_one_id_over_equal_conditions(bdir):
    b = M.load(bdir)
    # two groups of electrode 01 under the same conditions (a second step at the same stage, potential and filter)
    g = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, E1[2]))
    g["basis"] = copy.deepcopy(next(x for x in b["record_groups"] if x["group_id"] == _gid(b, E1[0]))["basis"])
    out = L.decide(b, _lq(b, "electrode_position"), decision="correct", value="1", only=None, note=None, **BY)
    assert "applies to every group of the beamtime" in out["statement"]
    assert "Check this position" in out["statement"] and E1[0] in out["statement"] and E1[2] in out["statement"]


def test_l2_a_stage_s_side_is_its_file_token_not_the_typed_sentence(bdir):
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")
    b = M.load(bdir)
    L.decide(b, _lq(b, "history", "history=after1500cycling"), decision="correct", value="before SYN third step",
             only=None, note=None, **BY)
    pairs = {(p["said"]["after"], p["said"]["before"]) for p in _lq(b, "follows")["proposals"]}
    assert (E1[2], E1[1]) in pairs, "the file name says after1500: an 'after' stage, whatever the sentence says"


def test_l3_deliberate_repeats_kept_apart_get_no_warning(bdir):
    b = M.load(bdir)
    g1, g2 = _gid(b, E1[0]), _gid(b, E3[0])
    same = {"fields": {L.SAMPLE_ID_PATH: {"value": "SYN-1"}, "context.environment": {"value": "in_situ"}}}
    fresh = [(g1, same, {}), (g2, copy.deepcopy(same), {})]
    [w] = [w for w in L.record_warnings(b, fresh, [g1, g2]) if w["code"] == L.SAME_RECORD_WARNING][:1]
    assert "If these are intended repeats, leave them" in w["text"]
    b.setdefault("merge_candidates", []).append({"merge_candidate_id": "mc-syn", "group_ids": [g1, g2]})
    b["scientist_decisions"].append({"decision_id": f"d-{len(b['scientist_decisions']) + 1:05d}",
                                     "target": {"kind": "merge_candidate", "id": "mc-syn"}, "decision": "keep_apart",
                                     "value": None, "decided_by": {"name": "Synthetic Scientist"}})
    assert not [w for w in L.record_warnings(b, fresh, [g1, g2]) if w["code"] == L.SAME_RECORD_WARNING]


# --- recheck of 21af0b57: a held chain never exports an earlier answer; the feed needs one standing whole answer ----


def _pairs(b: dict) -> set:
    fo = _lq(b, "follows") or {}
    return {(p["said"]["before"], p["said"]["after"]) for p in fo.get("proposals") or ()}


def _follows_ready(bdir: Path) -> dict:
    """Position 1 (the run number is the electrode), the ids and the links confirmed, each in one call."""
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")
    b = M.load(bdir)
    L.decide(b, _lq(b, "sample_id"), decision="confirm", value=None, only=None, note=None, **BY)
    assert (E2[0], E2[1]) in _pairs(b)
    L.decide(b, _lq(b, "follows"), decision="confirm", value=None, only=None, note=None, **BY)
    return b


def _link_of(b: dict, stem: str, bdir: Path):
    b = B.apply_derivations(copy.deepcopy(b))  # the states a save derives (answers in memory)
    gid = _gid(b, stem)
    comps = {g["group_id"]: R.compose_group(b, g, bdir) for g in Q.live_groups(b)}
    key_of = {r["run_id"]: r["run_key"] for r in b["runs"]}
    run_group = {key_of[r]: g for g, (_, c) in comps.items() for r in c.get("member_run_ids") or ()}
    drafts = {g: d for g, (d, _) in comps.items()}
    minted = {g: f"01SYNREC{n:018d}" for n, g in enumerate(comps)}
    return L.follows_link(gid, drafts[gid], comps[gid][1], run_group=run_group, drafts=drafts, minted=minted,
                          stale=L.current_follows(b))


def test_recheck_high_an_answer_recorded_before_a_hold_is_never_written(bdir):
    b = _follows_ready(bdir)
    assert _link_of(b, E2[1], bdir)[0] is not None, "it holds now: written"
    _set_run_number(b, E2, 7)  # (a) the bundle meets a hold the answer was given without (DEC-46/Q16)
    assert (E2[0], E2[1]) not in _pairs(b)
    link, _, why = _link_of(b, E2[1], bdir)
    assert link is None and "no longer holds" in why and "Q16" in why and L.question_id("follows") in why
    q = _lq(b, "follows")
    assert E2[1] in q["text"] and "no longer hold" in q["text"], "asked again, never dropped silently"
    gid = _gid(b, E2[1])
    b = B.apply_derivations(copy.deepcopy(b))
    fresh = [(g["group_id"], *R.compose_group(b, g, bdir)) for g in Q.live_groups(b)]
    [w] = [w for w in L.record_warnings(b, fresh, []) if w["code"] == L.STALE_FOLLOWS_WARNING and w["group_id"] == gid]
    assert E2[1] in w["text"] and "asks it again" in w["text"]


def test_recheck_high_a_new_electrode_position_unwrites_the_links(bdir):
    b = _follows_ready(bdir)
    # (b) the scientist re-answers the position: the number at position 2 is a step, read beside two sample names
    pos = next(q for q in L.label_questions(b, include_answered=True) if q["label"] == "electrode_position")
    L.decide(b, pos, decision="correct", value="2", only=None, note=None, **BY)
    link, _, why = _link_of(b, E2[1], bdir)
    assert link is None and "no longer holds" in why
    assert _gid(b, E2[1]) in L.current_follows(b)


def test_recheck_high_an_answer_for_another_pair_is_asked_again(bdir):
    b = _follows_ready(bdir)
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == E1[2])
    m = next(m for m in b["missing_values"] if L.is_label_slot(m) and m["target_field_path"] == L.FOLLOWS_PATH
             and m["run_id"] == rid)
    other = next(r["run_key"] for r in b["runs"] if r["stem"] == E1[0])  # a stage before the one it follows now
    M.record_decision(b, target_ids=[m["value_id"]], decision="correct",
                      value={"rel": "follows", "basis": "same_sample_id", "follows_run_key": other}, **BY)
    q = _lq(b, "follows")
    assert E1[2] in {p["first_file"] for p in q["proposals"]}, "the pair proposed now is asked"
    assert _link_of(b, E1[2], bdir)[0] is None


def _vid(b: dict, stem: str) -> str:
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == stem)
    return next(m["value_id"] for m in b["missing_values"] if L.is_label_slot(m)
                and m["target_field_path"] == L.FILTER_PATH and m.get("run_id") == rid)


def test_recheck_med1_a_regroup_never_hides_an_only_answer(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    L.decide(b, _lq(b, "filter"), decision="correct", value="SYN wording", only=f"group:{_gid(b, E2[0])}", note=None, **BY)
    L.decide(b, _lq(b, "filter"), decision="confirm", value=None, only=None, note=None, **BY)
    g1 = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, E1[0]))
    g2 = next(g for g in b["record_groups"] if g["group_id"] == _gid(b, E2[0]))
    g1["member_run_keys"] = list(g1["member_run_keys"]) + list(g2["member_run_keys"])  # the --only run joins
    b["record_groups"] = [g for g in b["record_groups"] if g is not g2]
    _conflict_decision(b, cid, "20")
    assert not L.feed_from_conflicts(b, [cid], **BY)["recorded"] and _slot(b, L.FILTER_PATH, E3[0]) is None


def test_recheck_med2_a_withdrawn_whole_answer_or_a_later_group_never_feeds(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    L.decide(b, _lq(b, "filter"), decision="confirm", value=None, only=None, note=None, **BY)
    b2 = copy.deepcopy(b)
    # the scientist later defers the answer for every group but one
    M.record_decision(b2, target_ids=[_vid(b2, s) for s in (*E1[1:], *E2)], decision="defer", value=None, **BY)
    _conflict_decision(b2, cid, "20")
    assert not L.feed_from_conflicts(b2, [cid], **BY)["recorded"]
    # a group that joined the question after the call (its filter settled since, unanswered)
    b3 = copy.deepcopy(M.load(bdir))
    cid3 = _filter_conflict(b3, E3[0])
    _hold_filter(b3, E2[0])
    L.decide(b3, _lq(b3, "filter"), decision="confirm", value=None, only=None, note=None, **BY)
    g = next(g for g in b3["record_groups"] if g["group_id"] == _gid(b3, E2[0]))
    g["basis"]["conditions"]["filter"] = copy.deepcopy(
        next(x for x in b3["record_groups"] if x["group_id"] == _gid(b3, E1[0]))["basis"]["conditions"]["filter"])
    _conflict_decision(b3, cid3, "20")
    assert not L.feed_from_conflicts(b3, [cid3], **BY)["recorded"] and _slot(b3, L.FILTER_PATH, E2[0]) is None
    # one --only answer per group, one after another, is never a whole-question answer
    b4 = M.load(bdir)
    cid4 = _filter_conflict(b4, E3[0])
    for s in (*E1, *E2):
        L.decide(b4, _lq(b4, "filter"), decision="confirm", value=None, only=f"group:{_gid(b4, s)}", note=None, **BY)
    _conflict_decision(b4, cid4, "20")
    assert not L.feed_from_conflicts(b4, [cid4], **BY)["recorded"]


def test_recheck_low_the_feed_names_the_groups_the_call_covered(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    L.decide(b, _lq(b, "filter"), decision="confirm", value=None, only=None, note=None, **BY)
    _conflict_decision(b, cid, "20")
    fed = L.feed_from_conflicts(b, [cid], **BY)
    assert fed["recorded"] and "which covered" in fed["statement"] and all(s in fed["statement"] for s in (*E1, *E2))
    assert "every other group" not in fed["statement"]


def test_recheck_low_the_stamp_is_read_only_at_the_start_of_the_note(bdir):
    b = M.load(bdir)
    cid = _filter_conflict(b, E3[0])
    # the scientist's own note quotes a stamp; their answers are --only, one per group
    fake = L.STAMP + '{"call": "000000000000", "question": "x"}] '
    for s in (*E1, *E2):
        L.decide(b, _lq(b, "filter"), decision="confirm", value=None, only=f"group:{_gid(b, s)}", note=fake, **BY)
    assert all(L._stamp(d) is None for d in b["scientist_decisions"][-len((*E1, *E2)):])
    _conflict_decision(b, cid, "20")
    assert not L.feed_from_conflicts(b, [cid], **BY)["recorded"]
