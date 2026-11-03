"""Round-9 polish of the condition labels (labels.py). SYNTHETIC fixtures only: every name, number and value is invented.

MED: a follows chain held because one stage states start times (#E) that disagree is released once a scientist
confirms that stage's start time (its ``resolve_conflict`` answer), the hold names that start-time question, and the
words say the shared run number IS the electrode. Every other guard stays: a run number the stages share that is not
the electrode (DEC-46/Q16) holds the chain whatever the times; equal instants hold it.
LOW 1: a group of a chain's sample and stage whose conditions differ only by an extra file-name token is listed.
LOW 2: ``--same-sample`` is held between file names that share no sample word, and between a standard or reference
measurement and one that is not; both files are named. Review MED: each side is read on the same basis, the hold says
it proves nothing, and ``--names-differ-ok`` records the join (in the note and the reply); two different parsed sample
names stay refused, firmly. Review LOW: a conditions_differ row is never told to be "settled".
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import labels as L
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
TEMPLATE = "04_02_ZZ2_base_after500Cycling_filter20_800mV"
FOLDER = "SYN_RR_2099-03_Fake_Acid"
#: invented electrode 01 of ZZ1 at three stages; its first stage's file states two start times (#E) that disagree
E1 = ("01_01_ZZ1_base_beforeCycling_filter10_060mV", "01_02_ZZ1_base_after1200Cycling_filter10_060mV",
      "01_03_ZZ1_base_after1500Cycling_filter10_060mV")
#: invented electrode 02 of ZZ2 at two stages
E2 = ("02_01_ZZ2_base_beforeCycling_filter10_060mV", "02_02_ZZ2_base_after1200Cycling_filter10_060mV")
#: electrode 02 again, at the first stage, with an extra token ("01a"): another condition key
EXTRA = "02_01a_ZZ2_base_beforeCycling_filter10_060mV"
#: electrode 02 at the first stage at ANOTHER potential: a condition both state differently, never listed
OTHER_POTENTIAL = "02_03_ZZ2_base_beforeCycling_filter10_600mV"
#: two invented powders whose names write no number (no electrode), one of them twice
POWDER = "Synthetic_Hexachloro_Powder"
POWDER2 = ("Synthetic_Oxide_Powder", "Synthetic_Oxide_Powder_shortExposure")
#: the review's variant: one invented powder written two ways (one with a parsed sample name, one without)
VARIANT = ("Ir_IV_Oxide", "IrO2")
STEMS = (*E1, *E2, EXTRA, OTHER_POTENTIAL, POWDER, *POWDER2, *VARIANT)
BASE_E = 4102447200
#: E1[0]'s second #E header: an hour and a half after its first, after E1[1] started
LATE_E = BASE_E + 3600 * 1 + 5400
BY = dict(by="Synthetic Scientist", orcid=None)


def _iso(epoch: int) -> str:
    import datetime as dt

    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat()


def _start(stem: str) -> int:
    return BASE_E + 3600 * (STEMS.index(stem) + 1)


def _corpus(tmp: Path) -> Path:
    out = tmp / FOLDER
    out.mkdir()
    for name in ("Zz_XAS.mac", "readme.txt", "2099 SYNTHETIC semantics notes.txt"):
        shutil.copy(SEMANTICS / name, out / name)
    template = (SEMANTICS / TEMPLATE).read_text(encoding="utf-8")
    for stem in STEMS:
        text = template.replace(TEMPLATE, stem).replace(f"#E {BASE_E}", f"#E {_start(stem)}")
        if stem == E1[0]:
            # a second header block in the same file, with another file-creation instant: the readings disagree
            text += f"\n#F {stem}\n#E {LATE_E}\n#D Fri Jan 01 02:30:00 2100\n"
        (out / stem).write_text(text, encoding="utf-8")
        (out / f"{stem}_dir").mkdir()
        for dat in sorted((SEMANTICS / f"{TEMPLATE}_dir").glob("*.dat")):
            (out / f"{stem}_dir" / dat.name.replace(TEMPLATE, stem)).write_text(
                dat.read_text(encoding="utf-8").replace(TEMPLATE, stem), encoding="utf-8")
    (out / "run01.mac").write_text("# SYNTHETIC FIXTURE -- read as TEXT, never executed.\nqdo Zz_XAS.mac\n"
                                   + "".join(f"newfile {s}\n" for s in STEMS), encoding="utf-8")
    return out


@pytest.fixture(scope="module")
def grouped_pristine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("labels_r9")
    out = tmp / "bundle"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def bdir(grouped_pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(grouped_pristine, target)
    return target


def _lq(b: dict, label: str, **kw) -> dict | None:
    return next((q for q in L.label_questions(b, **kw) if q["label"] == label and q.get("partition") is None), None)


def _answer(bdir: Path, qid: str, decision: str = "confirm", **kw):
    return M.decide_question(bdir, question_id=qid, decision=decision, value=kw.pop("value", None),
                             only=kw.pop("only", None), field=None, **BY, **kw)


def _gid(b: dict, stem: str) -> str:
    key = next(r["run_key"] for r in b["runs"] if r["stem"] == stem)
    return next(g["group_id"] for g in Q.live_groups(b) if key in g["member_run_keys"])


def _pairs(b: dict) -> set:
    p = next((x for x in L.proposals(b) if x["label"] == "follows"), None) or {}
    return {(i["said"]["before"], i["said"]["after"]) for i in p.get("items") or ()}


def _held(b: dict) -> list[dict]:
    p = next((x for x in L.proposals(b) if x["label"] == "follows"), None) or {}
    return list(p.get("not_proposed") or ())


def _start_conflict(b: dict) -> tuple[dict, str]:
    """E1[0]'s disagreement on its start time, and the id of the question that asks it."""
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == E1[0])
    cf = next(c for c in b["conflicts"] if rid in c["run_ids"] and c["engine_conflict_id"].endswith("::acquisition_epoch"))
    qs = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "resolve_conflict"
          and (q.get("targets") or [{}])[0].get("id") == cf["conflict_id"]]
    assert len(qs) == 1, "the start-time disagreement is asked"
    return cf, qs[0]["question_id"]


def _ready(bdir: Path) -> dict:
    """Position 1 (the run number IS the electrode) and the proposed sample ids, confirmed."""
    _answer(bdir, L.ELECTRODE_QUESTION_ID, "correct", value="1")
    b = M.load(bdir)
    _answer(bdir, _lq(b, "sample_id")["question_id"])
    return M.load(bdir)


# --- MED: a confirmed start time releases the chain ----------------------------------------------


def test_a_disagreeing_start_time_holds_the_chain_naming_its_question(bdir):
    b = _ready(bdir)
    cf, qid = _start_conflict(b)
    assert {r["value"] for r in cf["readings"]} == {_iso(_start(E1[0])), _iso(LATE_E)}
    assert (E2[0], E2[1]) in _pairs(b), "the other electrode's stages are ordered by their file times"
    assert not {p for p in _pairs(b) if p[0] in E1 or p[1] in E1}
    [h] = [h for h in _held(b) if E1[0] in h["first_files"]]
    assert h["first_files"] == list(E1)
    assert qid in h["reason"] and "start times (#E) that disagree" in h["reason"]
    assert "share run number 1, which is their electrode number" in h["reason"]
    assert "overlap" not in h["reason"], "the run number IS the electrode: no 'run numbers overlap'"
    assert qid in _lq(b, "follows")["text"]


def test_confirming_the_start_time_proposes_the_chain_again(bdir):
    b = _ready(bdir)
    _answer(bdir, L.question_id("follows"))  # the links proposed now (electrode 02), answered
    assert _lq(M.load(bdir), "follows") is None
    cf, qid = _start_conflict(M.load(bdir))
    _answer(bdir, qid, "confirm", value=_iso(_start(E1[0])))
    b = M.load(bdir)
    assert {(E1[0], E1[1]), (E1[1], E1[2])} <= _pairs(b), "the confirmed start orders the stages"
    assert not [h for h in _held(b) if E1[0] in h.get("first_files", ())]
    fo = _lq(b, "follows")  # asked again: only the newly proposed links are open
    assert {p["first_file"] for p in fo["proposals"]} == {E1[1], E1[2]}
    d = next(d for d in b["scientist_decisions"] if d["target"] == {"kind": "conflict", "id": cf["conflict_id"]})
    said = next(p["said"] for p in fo["proposals"] if p["first_file"] == E1[1])
    assert said["order_basis"] == "start_times" and said["start_time_answers"] == [d["decision_id"]]
    assert d["decision_id"] in fo["text"]
    L.decide(b, fo, decision="confirm", value=None, only=None, note=None, **BY)
    assert _lq(b, "follows") is None, "every link answered"


@pytest.mark.parametrize("when, why", [
    (_start(E1[1]), "two of them state the same start instant"),  # equal to the next stage's: no order
    (LATE_E, "comes after an 'after' one"),  # the later reading: the 'before' stage would start after 'after 1200'
])
def test_a_confirmed_start_time_that_does_not_order_them_keeps_the_hold(bdir, when, why):
    b = _ready(bdir)
    cf, qid = _start_conflict(b)
    _answer(bdir, qid, "correct" if when != LATE_E else "confirm", value=_iso(when))
    b = M.load(bdir)
    assert not {p for p in _pairs(b) if p[0] in E1 or p[1] in E1}
    [h] = [h for h in _held(b) if E1[0] in h["first_files"]]
    assert why in h["reason"]


def test_a_shared_run_number_that_is_not_the_electrode_stays_held_whatever_the_times(bdir):
    b = _ready(bdir)
    cf, qid = _start_conflict(b)
    _answer(bdir, qid, "confirm", value=_iso(_start(E1[0])))
    b = M.load(bdir)
    assert (E1[0], E1[1]) in _pairs(b)
    for r in b["runs"]:
        if r["stem"] in E1:
            r["legacy_number"] = 7  # one run number on three stages, not their electrode's (DEC-46, Q16 open)
    assert not {p for p in _pairs(b) if p[0] in E1 or p[1] in E1}
    [h] = [h for h in _held(b) if E1[0] in h["first_files"]]
    assert "share run number 7" in h["reason"] and "Q16" in h["reason"] and "DEC-46" in h["reason"]


def test_a_rejected_or_zoneless_start_time_orders_nothing(bdir):
    b = _ready(bdir)
    cf, qid = _start_conflict(b)
    _answer(bdir, qid, "reject")
    b = M.load(bdir)
    [h] = [h for h in _held(b) if E1[0] in h["first_files"]]
    assert "rejected the start time of " + E1[0] in h["reason"]
    # a time with no zone is never taken as UTC (no decide path writes one; the stored answer is edited here)
    d = next(d for d in b["scientist_decisions"] if d["target"] == {"kind": "conflict", "id": cf["conflict_id"]})
    d.update(decision="correct", value="2100-01-01T01:00:00")
    [h] = [h for h in _held(b) if E1[0] in h["first_files"]]
    assert "names no instant with its zone" in h["reason"]
    d.update(value=_iso(_start(E1[0])))
    assert (E1[0], E1[1]) in _pairs(b)


def test_the_start_instant_parser_takes_only_zoned_instants():
    midnight = 4102444800  # 2100-01-01T00:00:00Z
    assert L._instant("2100-01-01T00:00:00+00:00") == midnight == L._instant("2100-01-01T00:00:00Z")
    assert L._instant("2100-01-01T01:00:00+01:00") == midnight and L._instant(_iso(BASE_E)) == BASE_E
    assert L._instant(str(BASE_E)) == BASE_E and L._instant(BASE_E) == BASE_E
    assert L._instant("2100-01-01T00:00:00") is None and L._instant("Fri Jan 01 00:00:00 2100") is None
    assert L._instant(True) is None and L._instant(None) is None and L._instant("") is None


# --- LOW 1: a group of a chain's sample and stage with other conditions is said ------------------


def test_a_group_matching_a_chain_on_sample_and_stage_but_not_conditions_is_listed(bdir):
    b = _ready(bdir)
    assert (E2[0], E2[1]) in _pairs(b)
    rows = [h for h in _held(b) if h.get("kind") == L.OFF_CONDITION]
    assert [h["first_files"] for h in rows] == [[EXTRA]], "the other-potential group is another condition: not listed"
    [h] = rows
    assert h["group_ids"] == [_gid(b, EXTRA)] and h["matches_file"] == E2[0] and h["run_ids"] == []
    assert "01a" in h["reason"] and E2[0] in h["reason"] and "not on its conditions" in h["reason"]
    assert f"{FOLDER}:ZZ2-02" in h["reason"]
    fo = _lq(b, "follows")
    assert EXTRA in fo["text"] and "matches a chain on sample id and stage" in fo["text"]
    assert all(EXTRA not in (p["said"]["before"], p["said"]["after"]) for p in fo["proposals"])
    with pytest.raises(L.LabelRefused, match="Nothing was recorded"):
        L.decide(b, fo, decision="confirm", value=None, only=f"group:{_gid(b, EXTRA)}", note=None, **BY)


# --- LOW 2: --same-sample is refused across file names that share no sample-name token ----------


def _residual(b: dict) -> dict:
    return next(q for q in L.label_questions(b) if q["question_id"] == L.question_id("sample_id", L.RESIDUAL))


def test_same_sample_is_held_between_a_powder_and_an_electrode_naming_both_files(bdir):
    b = _ready(bdir)
    sid = f"{FOLDER}:ZZ1-01"
    residual = _residual(b)
    assert _gid(b, POWDER) in {h["group_id"] for h in residual["not_proposed"]}
    with pytest.raises(M.MutationRefused) as exc:
        _answer(bdir, residual["question_id"], "correct", value=sid, only=f"group:{_gid(b, POWDER)}", same_sample=True)
    said = str(exc.value)
    assert "share no word that can name a sample" in said and POWDER in said and E1[0] in said
    assert "does not prove" in said and L.NAMES_DIFFER_OK in said and "Nothing was recorded" in said
    assert "files say they are not one physical sample" not in said
    # two powders whose names share their sample words are one sample if the scientist says so
    out = _answer(bdir, residual["question_id"], "correct", value="SYN-oxide-powder",
                  only=[f"group:{_gid(b, s)}" for s in POWDER2], same_sample=True)
    assert out["statement"] and L.NAMES_DIFFER_OK not in out["statement"]
    b = M.load(bdir)
    assert all(d["decision"] == "correct" for d in b["scientist_decisions"][-2:])


def test_the_review_variant_one_powder_written_two_ways_is_held_then_recorded_on_the_second_flag(bdir):
    b = _ready(bdir)
    facts = {f.stems[0]: f for f in L._facts(b, Q.live_groups(b))}
    a, c = facts[VARIANT[0]], facts[VARIANT[1]]
    assert not a.names and c.names, "one side has a parsed sample name, the other none"
    assert L._same_sample_problem(a, c, 1) is None, "no two parsed names differ: never a firm refusal"
    said = L._same_sample_caution(a, c)
    assert said and VARIANT[0] in said and VARIANT[1] in said and "ir, iv, oxide against iro2" in said, \
        "both sides read on one basis: the file-name words"
    only = [f"group:{_gid(b, s)}" for s in VARIANT]
    qid = _residual(b)["question_id"]
    with pytest.raises(M.MutationRefused, match="does not prove they are two samples"):
        _answer(bdir, qid, "correct", value="SYN-iro2-powder", only=only, same_sample=True)
    with pytest.raises(M.MutationRefused, match="goes with --same-sample"):
        _answer(bdir, qid, "correct", value="SYN-iro2-powder", only=only, names_differ_ok=True)
    out = _answer(bdir, qid, "correct", value="SYN-iro2-powder", only=only, same_sample=True, names_differ_ok=True)
    assert L.NAMES_DIFFER_OK in out["statement"] and "share no word" in out["statement"]
    assert any(j.get("names_differ") for j in out["same_sample"])
    b = M.load(bdir)
    notes = [d["note"] for d in b["scientist_decisions"][-2:]]
    assert all(L.NAMES_DIFFER_OK in n and "They confirmed it although" in n for n in notes)
    assert {d["value"] for d in b["scientist_decisions"][-2:]} == {"SYN-iro2-powder"}


def test_two_different_parsed_sample_names_stay_refused_whatever_the_flags(bdir):
    b = M.load(bdir)  # no electrode position yet: the groups are ISAAC's to place, the scientist's to join
    qid = L.question_id("sample_id")
    _answer(bdir, qid, "correct", value="SYN-ZZ1-e1", only=f"group:{_gid(b, E1[0])}")
    with pytest.raises(M.MutationRefused) as exc:
        _answer(bdir, qid, "correct", value="SYN-ZZ1-e1", only=f"group:{_gid(b, E2[0])}", same_sample=True,
                names_differ_ok=True)
    said = str(exc.value)
    assert E1[0] in said and E2[0] in said and f"{L.NAMES_DIFFER_OK} does not lift this" in said


def test_same_sample_is_held_between_a_reference_and_a_sample(bdir):
    b = _ready(bdir)
    facts = {f.stems[0]: f for f in L._facts(b, Q.live_groups(b))}
    a, c = facts[E1[0]], facts[E1[1]]
    assert L._same_sample_caution(a, c) is None and L._same_sample_problem(a, c, 1) is None, "one electrode, two stages"
    c.role = "reference"
    said = L._same_sample_caution(a, c)
    assert said and "standard or reference" in said and E1[0] in said and E1[1] in said
    assert L._same_sample_problem(a, c, 1) is None, "a role is a caution the scientist may override, never firm"
    assert L._same_sample_caution(facts[POWDER2[0]], facts[POWDER2[1]]) is None
    said = L._same_sample_caution(facts[POWDER], facts[E2[0]])
    assert said and POWDER in said and E2[0] in said


# --- review LOW: a conditions_differ row is never told to be settled ------------------------------


def test_the_held_follows_question_words_its_ending_per_row_kind():
    off = {"group_ids": ["rg-x"], "first_files": ["X_01a"], "run_ids": [], "kind": L.OFF_CONDITION, "reason": "r"}
    held = {"group_ids": ["rg-y", "rg-z"], "first_files": ["Y", "Z"], "run_ids": [], "reason": "s"}
    p = {"question_id": L.question_id("follows"), "label": "follows", "partition": None, "path": L.FOLLOWS_PATH,
         "items": [], "stale": []}
    only_off = L._held_chains_question({**p, "not_proposed": [off]}, False)
    assert "Settle" not in only_off["text"] and "nothing to answer for it" in only_off["text"]
    assert "settle" not in only_off["answer_command"]
    both = L._held_chains_question({**p, "not_proposed": [held, off]}, False)
    assert "Settle what each held set's reason names" in both["text"] and "nothing to answer for it" in both["text"]
    with pytest.raises(L.LabelRefused) as exc:
        L.decide({}, only_off, decision="confirm", value=None, only=None, note=None, **BY)
    assert "Settle" not in str(exc.value) and "nothing to answer" in str(exc.value)


# --- ids --------------------------------------------------------------------------------------


def test_existing_question_ids_kinds_scopes_and_targets_are_unchanged(bdir):
    def shape(payload):
        return {q["question_id"]: (q["kind"], q["scope"], sorted(t["id"] for t in q["targets"]))
                for q in payload["questions"] if q["kind"] != L.KIND}
    before = shape(Q.consolidate(M.load(bdir), include_answered=True))
    b = _ready(bdir)
    _, qid = _start_conflict(b)
    _answer(bdir, qid, "confirm", value=_iso(_start(E1[0])))
    after = shape(Q.consolidate(M.load(bdir), include_answered=True))
    assert after == before
    assert L.question_id("follows") == _lq(M.load(bdir), "follows")["question_id"]
