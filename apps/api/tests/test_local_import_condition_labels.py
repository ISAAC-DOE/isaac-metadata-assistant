"""Condition labels (labels.py). SYNTHETIC fixtures only: every name, number and value is invented.

Records that grouping keeps apart by condition must not export with one body. ISAAC proposes, from the readings the
grouping already used, a sample id per electrode (sample.sample_id), the filter (system.configuration.beam_attenuator),
the cycling history (context.electrochemistry.notes), a follows link between successive history stages of one
electrode, and one tag per beamtime. Nothing is written without a scientist decision, and no existing question
changes id, kind, scope or targets.
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
FOLDER = "SYN_ZZ_2099-01_Fake_Base"
#: one invented electrode (04) of an invented sample SYN code ZZ4, measured before and after two cyclings
CHAIN = ("11_04_ZZ4_base_beforeCycling_filter10_060mV", "14_04_ZZ4_base_after1200Cycling_filter10_060mV",
         "17_04_ZZ4_base_after1500Cycling_filter10_060mV")
#: a second invented electrode (05) of ZZ4 at the same stage: its own id
OTHER = "20_05_ZZ4_base_beforeCycling_filter10_060mV"
BY = dict(by="Synthetic Scientist", orcid=None)


def _corpus(tmp: Path) -> Path:
    src = tmp / FOLDER
    shutil.copytree(SEMANTICS, src)
    for n, stem in enumerate((*CHAIN, OTHER)):
        text = (src / TEMPLATE).read_text(encoding="utf-8").replace(TEMPLATE, stem)
        # the file-creation instant (#E) follows the run numbers
        text = text.replace("#E 4102447200", f"#E {4102447200 + 3600 * (n + 1)}")
        (src / stem).write_text(text, encoding="utf-8")
        (src / f"{stem}_dir").mkdir()
        for dat in sorted((src / f"{TEMPLATE}_dir").glob("*.dat")):
            (src / f"{stem}_dir" / dat.name.replace(TEMPLATE, stem)).write_text(
                dat.read_text(encoding="utf-8").replace(TEMPLATE, stem), encoding="utf-8")
    mac = src / "run01.mac"
    mac.write_text(mac.read_text(encoding="utf-8") + "".join(f"newfile {s}\n" for s in (*CHAIN, OTHER)), encoding="utf-8")
    return src


@pytest.fixture(scope="module")
def grouped_pristine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("labels")
    out = tmp / "bundle"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def bdir(grouped_pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(grouped_pristine, target)
    return target


def _questions(bdir: Path, **kw) -> dict[str, dict]:
    out = {}
    for q in Q.consolidate(M.load(bdir), **kw)["questions"]:
        if q["kind"] == L.KIND:
            out[q["label"] if q["label"] != "history" else q["partition"]] = q
    return out


def _group_of(b: dict, stem: str) -> dict:
    key = next(r["run_key"] for r in b["runs"] if r["stem"] == stem)
    return next(g for g in Q.live_groups(b) if key in g["member_run_keys"])


def _draft(bdir: Path, stem: str) -> tuple[dict, dict]:
    b = M.load(bdir)
    return R.compose_group(b, _group_of(b, stem), bdir)


def _answer(bdir: Path, qid: str, decision: str = "confirm", **kw):
    return M.decide_question(bdir, question_id=qid, decision=decision, value=kw.pop("value", None),
                             only=kw.pop("only", None), field=None, **BY, **kw)


def _proposal(q: dict, stem: str):
    return next(p["value"] for p in q["proposals"] if p["first_file"] == stem)


# --- proposals -----------------------------------------------------------------------------------


def test_each_label_is_proposed_from_the_readings_the_grouping_used(bdir):
    qs = _questions(bdir)
    assert {"sample_id", "filter", "follows", "tag", "history=beforecycling", "history=after1200cycling",
            "history=after1500cycling"} <= set(qs)
    sid = qs["sample_id"]
    ids = {_proposal(sid, s) for s in CHAIN}
    assert ids == {f"{FOLDER}:ZZ4-04"}, "one id for every record of one electrode"
    assert _proposal(sid, OTHER) == f"{FOLDER}:ZZ4-05", "another electrode, another id"
    assert _proposal(qs["filter"], CHAIN[0]) == "filter10"
    assert _proposal(qs["history=after1500cycling"], CHAIN[2]) == "after 1500 cycling"
    assert _proposal(qs["history=beforecycling"], CHAIN[0]) == "before cycling"
    assert qs["tag"]["proposals"][0]["value"] == ["syn-zz-2099-01-fake-base"]
    for q in qs.values():
        assert q["scope"] == "experiment" and q["blocking"] is False and q["tier"] == Q.TIER_OPTIONAL
        assert q["question_id"] == L.question_id(q["label"], q["partition"])


def test_follows_orders_the_history_stages_of_one_electrode_by_run_number(bdir):
    q = _questions(bdir)["follows"]
    pairs = {(p["said"]["after"], p["said"]["before"]) for p in q["proposals"]}
    assert (CHAIN[1], CHAIN[0]) in pairs and (CHAIN[2], CHAIN[1]) in pairs
    assert not any(OTHER in pair for pair in pairs), "another electrode is never linked"
    assert all(p["said"]["order_basis"] == "run_numbers" for p in q["proposals"])


def test_nothing_is_written_before_a_scientist_answers(bdir):
    draft, report = _draft(bdir, CHAIN[1])
    for path in (L.SAMPLE_ID_PATH, L.FILTER_PATH, L.HISTORY_PATH):
        assert path not in draft["fields"]
    assert not draft.get("tags") and not draft["links"] and "follows" not in report


def test_history_is_words_only_never_an_interpretation():
    assert L.history_words("after1500Cycling") == "after 1500 cycling"
    assert L.history_words("after1200mVCycling") == "after 1200mV cycling"
    assert L.history_words("after1stCycling") == "after 1st cycling"
    assert L.history_words("after1500cv") == "after 1500 CV"
    assert L.history_words("fresh") is None
    assert L.proposed_tag("SYN_Beamtime 2099/Fake") == "syn-beamtime-2099-fake"
    assert len(L.proposed_tag("SYN_" + "x_" * 60)) <= L.TAG_MAX
    assert L.filter_number("f30") == L.filter_number("filter30") == L.filter_number("30") == 30
    assert L.filter_number("ffilter30") is None


def test_a_counter_answer_on_the_electrode_position_stops_the_proposal(bdir):
    b = M.load(bdir)
    b["scientist_decisions"].append({
        "decision_id": f"d-{len(b['scientist_decisions']) + 1:05d}", "target": {"kind": "experiment", "id": "experiment"},
        "decision": "set_counter_positions", "value": None, "chosen_reading_index": None,
        "decided_by": {"name": "Synthetic Scientist", "basis": "self_reported_local_user", "identity": "local_unverified",
                       "orcid_claimed": None},
        "decided_utc": "2099-01-01T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None,
        "positions": [2]})
    q = {q["label"]: q for q in L.label_questions(b)}["sample_id"]
    held = {h["first_file"]: h["reason"] for h in q["not_proposed"]}
    assert not q["proposals"] and "run counter" in held[CHAIN[0]]
    assert q["allowed_decisions"] == ["correct", "reject"], "nothing to confirm: the scientist gives each id"


# --- answers -------------------------------------------------------------------------------------


def test_one_confirm_records_every_electrode_id_and_the_records_carry_it(bdir):
    q = _questions(bdir)["sample_id"]
    result = _answer(bdir, q["question_id"])
    assert result["slots_recorded"] >= 4
    b = M.load(bdir)
    assert not B.validate_bundle(b)
    slots = [m for m in b["missing_values"] if L.is_label_slot(m)]
    assert slots and all(m["eligibility_for_official_record"]["eligible"] for m in slots)
    assert all(L.slot_question(m) == q["question_id"] for m in slots)
    ids = {_draft(bdir, s)[0]["fields"][L.SAMPLE_ID_PATH]["value"] for s in CHAIN}
    assert ids == {f"{FOLDER}:ZZ4-04"}
    assert _draft(bdir, OTHER)[0]["fields"][L.SAMPLE_ID_PATH]["value"] == f"{FOLDER}:ZZ4-05"
    ev = _draft(bdir, CHAIN[0])[0]["fields"][L.SAMPLE_ID_PATH]["evidence"]
    assert ev[0]["source_type"] == "user_confirmation" and q["question_id"] in ev[0]["question"]
    # answered: out of the open list, still found under its id
    assert "sample_id" not in _questions(bdir)
    again = _questions(bdir, include_answered=True)["sample_id"]
    assert again["answered"] is True and again["question_id"] == q["question_id"]


def test_a_convention_is_a_pattern_and_two_electrodes_never_share_an_id(bdir):
    qid = _questions(bdir)["sample_id"]["question_id"]
    with pytest.raises(M.MutationRefused, match="electrode"):
        _answer(bdir, qid, "correct", value="SYN-ZZ4")
    with pytest.raises(M.MutationRefused, match="placeholders"):
        _answer(bdir, qid, "correct", value="SYN-{nope}-{electrode}")
    _answer(bdir, qid, "correct", value="SYN-{sample}-e{electrode}")
    assert _draft(bdir, CHAIN[2])[0]["fields"][L.SAMPLE_ID_PATH]["value"] == "SYN-ZZ4-e04"
    assert _draft(bdir, OTHER)[0]["fields"][L.SAMPLE_ID_PATH]["value"] == "SYN-ZZ4-e05"
    # one group's own id is the electrode's: every group of that electrode gets it ...
    gid = _group_of(M.load(bdir), CHAIN[0])["group_id"]
    _answer(bdir, qid, "correct", value="SYN-electrode-A", only=f"group:{gid}")
    assert {_draft(bdir, s)[0]["fields"][L.SAMPLE_ID_PATH]["value"] for s in CHAIN} == {"SYN-electrode-A"}
    # ... and another electrode cannot take it
    other = _group_of(M.load(bdir), OTHER)["group_id"]
    with pytest.raises(M.MutationRefused, match="one physical"):
        _answer(bdir, qid, "correct", value="SYN-electrode-A", only=f"group:{other}")


def test_filter_history_and_tag_are_written_where_the_portal_takes_them(bdir):
    qs = _questions(bdir)
    _answer(bdir, qs["filter"]["question_id"], "correct", value="SYN filter {filter}")
    _answer(bdir, qs["history=after1500cycling"]["question_id"], "correct", value="after synthetic cycling to 1.5 V")
    _answer(bdir, qs["history=after1200cycling"]["question_id"])
    _answer(bdir, qs["tag"]["question_id"])
    draft, _ = _draft(bdir, CHAIN[2])
    assert draft["fields"][L.FILTER_PATH]["value"] == "SYN filter 10"
    assert draft["fields"][L.HISTORY_PATH]["value"] == "after synthetic cycling to 1.5 V"
    assert draft["tags"] == ["syn-zz-2099-01-fake-base"] and "tags" not in draft["fields"]
    assert _draft(bdir, CHAIN[1])[0]["fields"][L.HISTORY_PATH]["value"] == "after 1200 cycling"
    record = R.compose_record(draft, None, record_id="0" * 26, now="2099-01-01T00:00:00Z")
    assert record["system"]["configuration"] == {"beam_attenuator": "SYN filter 10"}
    assert record["context"]["electrochemistry"]["notes"] == "after synthetic cycling to 1.5 V"
    assert record["tags"] == ["syn-zz-2099-01-fake-base"]
    # the portal's vocabulary closes provenance: the history never goes there
    assert B.allowed_values("sample.material.provenance") and "provenance" not in json.dumps(record.get("sample") or {})


def test_reject_writes_nothing_and_answers_the_question(bdir):
    q = _questions(bdir)["filter"]
    _answer(bdir, q["question_id"], "reject")
    assert L.FILTER_PATH not in _draft(bdir, CHAIN[0])[0]["fields"]
    assert "filter" not in _questions(bdir)


def test_refusals_say_why_and_record_nothing(bdir):
    qs = _questions(bdir)
    before = len(M.load(bdir)["scientist_decisions"])
    with pytest.raises(M.MutationRefused, match="does not answer"):
        _answer(bdir, qs["follows"]["question_id"], "correct", value="x")
    with pytest.raises(M.MutationRefused, match="no group"):
        _answer(bdir, qs["tag"]["question_id"], only="group:rg-none")
    with pytest.raises(M.MutationRefused, match="takes no --value|records the proposed"):
        _answer(bdir, qs["tag"]["question_id"], value="syn")
    with pytest.raises(M.MutationRefused, match="tag is 1 to"):
        _answer(bdir, qs["tag"]["question_id"], "correct", value="x" * 65)
    b = M.load(bdir)
    assert len(b["scientist_decisions"]) == before and not any(L.is_label_slot(m) for m in b["missing_values"])


def test_a_dry_run_records_nothing(bdir):
    q = _questions(bdir)["tag"]
    out = M.decide_question(bdir, question_id=q["question_id"], decision="confirm", value=None, only=None, field=None,
                            dry_run=True, **BY)
    assert out["dry_run"] is True
    assert not any(L.is_label_slot(m) for m in M.load(bdir)["missing_values"])


def test_existing_questions_keep_their_ids_kinds_scopes_and_targets(bdir):
    def shape(payload):
        return {q["question_id"]: (q["kind"], q["scope"], sorted(t["id"] for t in q["targets"]),
                                   {f: sorted(v) for f, v in (q.get("fields") or {}).items()})
                for q in payload["questions"] if q["kind"] != L.KIND}
    before = {k: shape(Q.consolidate(M.load(bdir), include_answered=k)) for k in (False, True)}
    for q in _questions(bdir).values():
        if q["allowed_decisions"][0] == "confirm":
            _answer(bdir, q["question_id"])
    after = {k: shape(Q.consolidate(M.load(bdir), include_answered=k)) for k in (False, True)}
    assert after == before


# --- follows links and record ids -----------------------------------------------------------------


def _follows_ready(bdir: Path) -> None:
    qs = _questions(bdir)
    _answer(bdir, qs["sample_id"]["question_id"])
    _answer(bdir, qs["follows"]["question_id"])


def test_a_follows_answer_resolves_to_the_earlier_record_id_with_its_evidence(bdir):
    _follows_ready(bdir)
    b = M.load(bdir)
    comps = {s: R.compose_group(b, _group_of(b, s), bdir) for s in CHAIN}
    gids = {s: _group_of(b, s)["group_id"] for s in CHAIN}
    later_draft, later = comps[CHAIN[1]]
    assert later["follows"]["follows_run_key"].startswith(CHAIN[0]) and not later_draft["links"]
    run_group = {r["run_key"]: _group_of(b, r["stem"])["group_id"] for r in b["runs"] if r["stem"] in CHAIN}
    drafts = {gids[s]: comps[s][0] for s in CHAIN}
    # the earlier record not exported (yet): the later one is written without the link, and says why
    link, ev, why = L.follows_link(gids[CHAIN[1]], later_draft, later, run_group=run_group, drafts=drafts, minted={})
    assert link is None and "was not exported" in why
    minted = {gids[CHAIN[0]]: "01SYNTHETICRECORD000000000"}
    link, ev, why = L.follows_link(gids[CHAIN[1]], later_draft, later, run_group=run_group, drafts=drafts, minted=minted)
    assert why is None and link == {**link, "rel": "follows", "basis": "same_sample_id",
                                    "target": "01SYNTHETICRECORD000000000"}
    linked = L.with_link(later_draft, link, ev)
    from isaac_records.draft_validator import validate_draft

    assert not [e for e in validate_draft(linked).errors if "link" in str(e)]
    record = R.compose_record(linked, later, record_id="0" * 26, now="2099-01-01T00:00:00Z")
    assert record["links"][0]["target"] == "01SYNTHETICRECORD000000000" and "evidence" not in record["links"][0]
    # a new id for the earlier record is a new body for the later one: ids follow bodies
    other = L.with_link(later_draft, {**link, "target": "01SYNTHETICRECORD000000001"}, ev)
    probe = lambda d: R.body_sha256(R.compose_record(d, later, record_id=R.SUBSTANCE_PROBE_ID,  # noqa: E731
                                                     now=R.SUBSTANCE_PROBE_AT), [])
    assert probe(linked) != probe(other)


def test_no_link_without_the_same_sample_id_on_both_records(bdir):
    qs = _questions(bdir)
    _answer(bdir, qs["follows"]["question_id"])
    b = M.load(bdir)
    gid = {s: _group_of(b, s)["group_id"] for s in CHAIN[:2]}
    drafts = {gid[s]: R.compose_group(b, _group_of(b, s), bdir)[0] for s in CHAIN[:2]}
    later = R.compose_group(b, _group_of(b, CHAIN[1]), bdir)[1]
    run_group = {r["run_key"]: _group_of(b, r["stem"])["group_id"] for r in b["runs"] if r["stem"] in CHAIN[:2]}
    link, _, why = L.follows_link(gid[CHAIN[1]], drafts[gid[CHAIN[1]]], later, run_group=run_group, drafts=drafts,
                                  minted={gid[CHAIN[0]]: "01SYNTHETICRECORD000000000"})
    assert link is None and "sample id" in why


def test_export_order_puts_the_earlier_record_first(tmp_path):
    fresh = [("g-late", {}, {"follows": {"follows_run_key": "k-early"}}), ("g-other", {}, {}), ("g-early", {}, {})]
    order = [g for g, _, _ in L.order_by_follows(fresh, {"k-early": "g-early"})]
    assert order.index("g-early") < order.index("g-late") and len(order) == 3
    paths = [tmp_path / f"{x}.json" for x in ("01AAAA", "01BBBB", "01CCCC")]
    assert [p.name for p in L.order_records_by_links(paths, {"01AAAA": ["01CCCC"]})] == \
        ["01CCCC.json", "01AAAA.json", "01BBBB.json"]
    # a cycle never loops
    assert len(L.order_records_by_links(paths, {"01AAAA": ["01BBBB"], "01BBBB": ["01AAAA"]})) == 3


def test_label_slot_values_are_checked():
    assert L.label_value_problem(L.SAMPLE_ID_PATH, " x") and L.label_value_problem(L.SAMPLE_ID_PATH, "")
    assert L.label_value_problem(L.SAMPLE_ID_PATH, "SYN-1") is None
    assert L.label_value_problem(L.FILTER_PATH, True) and L.label_value_problem(L.FILTER_PATH, 10) is None
    assert L.label_value_problem(L.TAGS_PATH, ["ok"]) is None and L.label_value_problem(L.TAGS_PATH, "ok")
    assert L.label_value_problem(L.FOLLOWS_PATH, {"rel": "follows", "basis": "same_sample_id",
                                                  "follows_run_key": "k"}) is None
    assert L.label_value_problem(L.FOLLOWS_PATH, {"rel": "same_sample_as"})
    m = {"target_field_path": L.SAMPLE_ID_PATH, "reason": L.SLOT_REASON.format(question="Q-0123456789", what="x")}
    assert L.is_label_slot(m) and L.slot_question(m) == "Q-0123456789"
    assert not L.is_label_slot({**m, "target_field_path": "sample.material.name"})
    assert L.slot_eligibility(B.STATE_SCIENTIST_CONFIRMED, m, "SYN-1")["eligible"]
    assert not L.slot_eligibility(B.STATE_MISSING, m, None)["eligible"]


def test_a_group_isaac_proposed_nothing_for_is_answered_on_its_own(bdir):
    q = _questions(bdir)["filter"]
    held = next(h for h in q["not_proposed"] if h["first_file"] == TEMPLATE)
    assert "disagree" in held["reason"]
    with pytest.raises(M.MutationRefused, match="nothing to confirm"):
        _answer(bdir, q["question_id"], only=f"group:{held['group_id']}")
    with pytest.raises(M.MutationRefused, match="nothing to fill"):
        _answer(bdir, q["question_id"], "correct", value="filter{filter}", only=f"group:{held['group_id']}")
    _answer(bdir, q["question_id"], "correct", value="SYN filter 20", only=f"group:{held['group_id']}")
    assert _draft(bdir, TEMPLATE)[0]["fields"][L.FILTER_PATH]["value"] == "SYN filter 20"
    # the proposed groups are still asked
    assert _questions(bdir)["filter"]["proposals"]


# --- review of 7a94d23e: M1-M3, L1-L6 (in memory: the bundle a scientist's answers would leave) ----------------------


def _group(b: dict, stem: str) -> dict:
    return _group_of(b, stem)


def _sid_q(b: dict) -> dict:
    return next(q for q in L.label_questions(b, include_answered=True) if q["label"] == "sample_id")


def _decide(b: dict, label: str, decision: str = "confirm", **kw) -> dict:
    q = next(q for q in L.label_questions(b, include_answered=True) if q["label"] == label
             and (label != "history" or q["partition"] == kw.pop("partition", q["partition"])))
    return L.decide(b, q, decision=decision, value=kw.pop("value", None), only=kw.pop("only", None),
                    by="Synthetic Scientist", orcid=None, note=None, **kw)


def _slot_value(b: dict, path: str, stem: str):
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == stem)
    m = next(m for m in b["missing_values"] if L.is_label_slot(m) and m["target_field_path"] == path and m["run_id"] == rid)
    return B._decisions_by_target(b["scientist_decisions"])[("missing_value", m["value_id"])]["value"]


def _hold_electrode(b: dict, stem: str) -> str:
    g = _group(b, stem)
    g["basis"]["sample"]["sample_or_electrode_number"] = {"kind": "conflicting", "readings": ["05", "55"],
                                                          "candidate_ids": []}
    return g["group_id"]


def test_m1_a_group_isaac_could_not_place_joins_an_electrode_id_only_when_the_scientist_says_so(bdir):
    b = M.load(bdir)
    held = _hold_electrode(b, OTHER)
    q = _sid_q(b)
    assert {h["group_id"]: h["reason"] for h in q["not_proposed"]}[held] == "the files' electrode readings disagree"
    target = f"{FOLDER}:ZZ4-04"
    with pytest.raises(L.LabelRefused, match="--same-sample"):
        _decide(b, "sample_id", "correct", value=target, only=f"group:{held}")
    out = _decide(b, "sample_id", "correct", value=target, only=f"group:{held}", same_sample=True)
    assert out["same_sample"] and "same physical sample" in out["statement"]
    assert "--same-sample" in b["scientist_decisions"][-1]["note"]
    # the reverse order: the bulk confirm that follows is recorded, and names the held answer
    out = _decide(b, "sample_id")
    assert out["shares_id_with"] and out["shares_id_with"][0]["value"] == target
    assert {_slot_value(b, L.SAMPLE_ID_PATH, s) for s in (*CHAIN, OTHER)} == {target}


def test_m1_after_a_bulk_confirm_a_held_group_still_needs_the_statement(bdir):
    b = M.load(bdir)
    held = _hold_electrode(b, OTHER)
    _decide(b, "sample_id")
    with pytest.raises(L.LabelRefused, match="--same-sample"):
        _decide(b, "sample_id", "correct", value=f"{FOLDER}:ZZ4-04", only=f"group:{held}")
    _decide(b, "sample_id", "correct", value="SYN-own-id", only=f"group:{held}")  # an id of its own needs nothing
    with pytest.raises(L.LabelRefused, match="--same-sample goes with"):
        _decide(b, "sample_id", same_sample=True)


def test_m2_a_bulk_answer_never_overwrites_an_earlier_answer_in_a_partly_answered_group(bdir):
    b = M.load(bdir)
    other = _group(b, OTHER)
    _decide(b, "filter", "correct", value="SYN own filter", only=f"group:{other['group_id']}")
    # the scientist then merges OTHER's run into the first chain group (a partly answered group)
    first = _group(b, CHAIN[0])
    first["member_run_keys"] = first["member_run_keys"] + other["member_run_keys"]
    other["status"] = "rejected"
    out = _decide(b, "filter")
    assert [k["group_id"] for k in out["kept"]] == [first["group_id"]] and "never overwritten" in out["statement"]
    assert _slot_value(b, L.FILTER_PATH, OTHER) == "SYN own filter"
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == CHAIN[0])
    assert not any(L.is_label_slot(m) and m["run_id"] == rid and m["target_field_path"] == L.FILTER_PATH
                   for m in b["missing_values"]), "the unanswered run of that group is left too"
    # naming the group replaces its answers: the scientist said which group
    _decide(b, "filter", only=f"group:{first['group_id']}")
    assert _slot_value(b, L.FILTER_PATH, OTHER) == "filter10"


def test_m3_chains_compare_normalised_conditions(bdir):
    b = M.load(bdir)
    _group(b, CHAIN[1])["basis"]["conditions"]["filter"]["value"] = ["10", "filter10"]
    fo = next(p for p in L.proposals(b) if p["label"] == "follows")
    pairs = {(i["said"]["after"], i["said"]["before"]) for i in fo["items"]}
    assert pairs >= {(CHAIN[1], CHAIN[0]), (CHAIN[2], CHAIN[1])} and (CHAIN[2], CHAIN[0]) not in pairs


def test_m3_a_stage_with_no_settled_history_holds_the_chain(bdir):
    b = M.load(bdir)
    _group(b, CHAIN[1])["basis"]["conditions"]["cycling_state"]["kind"] = "conflicting"
    assert not any(p["label"] == "follows" for p in L.proposals(b)), "17 never follows 11 over an unsettled stage"
    chains, held = L._chains(L._facts(b, Q.live_groups(b)))
    assert not chains and any("no settled history stage" in h["reason"] for h in held)


def test_l2_an_archive_suffix_is_not_part_of_the_folder_label():
    assert L.beamtime_label({"source_root": {"label": "SYN_Beamtime_2099.zip"}}) == "SYN_Beamtime_2099"
    assert L.beamtime_label({"source_root": {"label": "SYN_Beamtime_2099.tar.gz"}}) == "SYN_Beamtime_2099"
    assert L.proposed_tag(L.beamtime_label({"source_root": {"label": "SYN_B.ZIP"}})) == "syn-b"


def test_l3_the_electrode_position_is_the_one_grouping_counts():
    # the engine splits on underscores, grouping also on hyphens: `SYN-A_04_x` puts `04` at grouping position 3
    assert L._grouping_position("SYN-A_04_x", 1, 6) == 3
    assert L._grouping_position("11_04_ZZ4", 1, 3) == 2
    assert L._grouping_position("11_04_ZZ4", 1, None) == 2


def test_l4_groups_under_one_condition_that_differ_at_a_not_counter_position_get_no_shared_id(bdir):
    b = M.load(bdir)
    _group(b, CHAIN[2])["basis"] = copy.deepcopy(_group(b, CHAIN[0])["basis"])
    assert not _sid_q(b)["not_proposed"] or all(h["first_file"] not in CHAIN for h in _sid_q(b)["not_proposed"])
    b["scientist_decisions"].append({
        "decision_id": f"d-{len(b['scientist_decisions']) + 1:05d}", "target": {"kind": "experiment", "id": "experiment"},
        "decision": B.NOT_COUNTER_DECISION, "value": None, "chosen_reading_index": None,
        "decided_by": {"name": "Synthetic Scientist", "basis": "self_reported_local_user", "identity": "local_unverified",
                       "orcid_claimed": None},
        "decided_utc": "2099-01-01T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None,
        "not_counter_positions": [1]})
    held = {h["first_file"]: h["reason"] for h in _sid_q(b)["not_proposed"]}
    assert "not a run counter" in held[CHAIN[0]] and "not a run counter" in held[CHAIN[2]]
    assert CHAIN[1] not in held, "a different condition: the number may name that condition"


def test_l5_l6_wording():
    assert L.history_words("after100Cycles") == "after 100 cycles"
    assert L.history_words("after1Cycle") == "after 1 cycle"


def test_l6_the_filter_question_says_where_each_number_was_read(bdir):
    text = _questions(bdir)["filter"]["text"]
    assert "(file name and scan header)" in text and "filter motor" in text
    assert "mV" not in _questions(bdir)["history=after1500cycling"]["text"]
