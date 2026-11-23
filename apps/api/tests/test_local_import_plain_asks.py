"""``isaac bundle questions``: each question as a plain ask, its options and its suggestion (plain_asks.py).

Synthetic only: the bundle is the shared pristine fixture. The wording is the question site's (plain_questions.py):
these tests also check that the command line does not carry a second system.
"""

from __future__ import annotations

import json
import shutil
import statistics

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import plain_asks as PA
from isaac_api.local_import import plain_questions as P
from isaac_api.local_import import question_site as S
from isaac_api.local_import import questions as Q

from tests_support_records import pristine_bundle  # noqa: F401

COMMAND_SYNTAX = ("isaac bundle", "--decision", "--question", "--by ", "<bundle_dir>", "`")


@pytest.fixture()
def grouped(pristine_bundle, tmp_path):
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    return bdir


def _run(capsys, *argv):
    code = cli.main(["bundle", "questions", *argv])
    return code, capsys.readouterr().out


@pytest.fixture()
def page(grouped, capsys):
    code, out = _run(capsys, str(grouped), "--limit", "200", "--no-context")
    assert code == 0
    return json.loads(out)


def test_every_listed_question_has_a_plain_ask_with_no_command_syntax(page):
    asked = [q for q in page["questions"] if "ask" in q]
    assert len(asked) >= len(page["questions"]) - page["plain_asks"]["without_ask"] and asked
    for q in asked:
        assert q["ask"].endswith("?") and "\n" not in q["ask"]
        assert P.not_plain(q["ask"]) is None, q["ask"]
        assert not any(tok in q["ask"] for tok in COMMAND_SYNTAX), q["ask"]
        assert P.not_plain(S._without_quotes(q["plain_detail"])) is None, q["plain_detail"]
    # the whole point: a sentence, where the text is a paragraph
    assert statistics.median(len(q["ask"]) for q in asked) < 0.25 * statistics.median(len(q["text"]) for q in asked)


def test_the_json_page_only_gains_keys(grouped, capsys):
    """Backward compatible: every key the page and each question had is still there with the same value."""
    plain_keys = set(PA.KEYS)
    code, out = _run(capsys, str(grouped), "--limit", "200")
    after = json.loads(out)
    assert code == 0
    assert [q["question_id"] for q in after["questions"]]
    for q in after["questions"]:
        assert "text" in q and "answer_command" in q  # nothing moved to make room
    # the plain form is beside them, and a question with none is counted
    assert sum(1 for q in after["questions"] if "ask" not in q) == after["plain_asks"]["without_ask"]
    assert all(plain_keys <= set(q) for q in after["questions"] if "ask" in q)
    assert {"plain_asks", "minimum_for_one_group", "counts"} <= set(after)


def test_the_ask_is_the_question_sites_own_wording(grouped, page):
    """No second wording system: a whole-beamtime value question reads as the site's card for it."""
    b = M.load(grouped)
    payload = Q.consolidate(b)
    view = S._View(b, grouped, payload)
    env = next(q for q in payload["questions"] if q["target_field_path"] == "context.environment" and q["kind"] == "missing_value")
    card = S._value_card(view, PA._unit(env))
    got = next(q for q in page["questions"] if q["question_id"] == env["question_id"])
    assert got["ask"] == card["title"] == P.ask_for("context.environment", env["allowed_values"])
    assert [o["value"] for o in got["answer"]["options"]] == env["allowed_values"]
    assert got["answer"]["kind"] == "choice"


def test_a_long_list_shows_a_short_list_and_counts_the_rest(page):
    q = next(q for q in page["questions"] if q.get("target_field_path") == "sample.sample_form" and "answer" in q)
    total = q["answer"].get("options_total")
    assert total and total > len(q["answer"]["options"]) and len(q["answer"]["options"]) <= P.COMMON_FROM


def test_a_suggestion_comes_with_its_reason_and_is_never_the_answer(grouped, capsys):
    """A value the files give is shown as a suggestion with its basis; the question's own state is unchanged."""
    b = M.load(grouped)
    payload = Q.consolidate(b)
    with_suggestion = []
    for q in payload["questions"]:
        got = PA.plain_fields(S._View(b, grouped, payload), q)
        if got.get("suggested"):
            with_suggestion.append((q, got))
    assert with_suggestion, "the fixture has no suggestion to show"
    for q, got in with_suggestion:
        s = got["suggested"]
        assert s["reason"] and s["basis"] in {"files", "logbook", "reading", "earlier_answer", "rule", "general_knowledge"}
        assert not q.get("answered")


def test_the_plain_page_is_text_with_ask_options_and_id_and_nothing_for_the_tool(grouped, capsys):
    code, out = _run(capsys, str(grouped), "--plain", "--blocking-only", "--limit", "5", "--no-context")
    assert code == 0 and not out.lstrip().startswith("{")
    assert "1. " in out and "Question Q-" in out
    body = "\n".join(l for l in out.splitlines() if not l.strip().startswith("Question Q-"))
    assert "isaac bundle" not in body and "--decision" not in body and "answer_command" not in body
    assert out.count("[blocks export]") == 5  # --blocking-only: every question shown blocks export


def test_plain_detail_adds_the_full_text_under_each_question(grouped, capsys):
    _, short = _run(capsys, str(grouped), "--plain", "--limit", "3", "--no-context")
    _, full = _run(capsys, str(grouped), "--plain", "--detail", "--limit", "3", "--no-context")
    assert "Full text:" not in short
    assert full.count("Full text:") == 3 and len(full) > len(short) + 500


def test_detail_alone_is_refused(grouped, capsys):
    code, out = _run(capsys, str(grouped), "--detail")
    assert code == cli.EXIT_USAGE and out == ""


def test_asking_for_the_plain_page_records_the_same_exposures(grouped, tmp_path, capsys):
    """Presentation only: the plain page shows the values the JSON page shows, so it records the same exposures."""
    a, b = tmp_path / "json", tmp_path / "plain"
    shutil.copytree(grouped, a), shutil.copytree(grouped, b)
    _run(capsys, str(a), "--limit", "50", "--no-context")
    _run(capsys, str(b), "--plain", "--limit", "50")
    def _no_clock(d):
        return [{k: v for k, v in e.items() if k != "at_utc"} for e in M.load(d).get("exposures") or []]

    assert _no_clock(a) == _no_clock(b)


# --- the kinds the site does not ask: their asks are plain_questions' -----------------------------------------------

def test_the_counter_question_is_asked_in_words():
    assert P.counter_ask([1]) == ("Is the 1st part of the file names a run counter, a number that only tells repeats of one "
                                  "measurement apart?")
    assert "last part" in P.counter_ask(["last"]) and "2nd part or 3rd part" in P.counter_ask([2, 3])
    assert [P.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]


@pytest.mark.parametrize("q, ask", [
    ({"kind": "naming_counter_positions", "positions": [1]}, P.counter_ask([1])),
    ({"kind": "stated_utc_start_times"}, P.START_TIME_ASK),
    ({"kind": "confirm_absorber", "hints": [{"kind": "suggested_absorber", "element": "Zz", "edge": "L3"}]}, P.absorber_ask("Zz", "L3")),
    ({"kind": "optional_values", "fields": {"system.facility.beamline": ["t1"], "context.temperature_K": ["t2"]}},
     P.optional_ask(["context.temperature_K", "system.facility.beamline"])),
])
def test_each_other_kind_takes_its_ask_from_plain_questions(q, ask):
    got = PA._kind_card(None, q)
    assert got["ask"] == ask and P.not_plain(ask) is None


def test_a_kind_with_no_wording_gets_no_ask_and_is_counted():
    q = {"kind": "resolve_conflict", "target_field_path": None, "question_id": "Q-0000000000"}
    assert PA.plain_fields(None, q) == {} and PA.missing([q]) == 1


def test_a_wording_that_is_not_plain_is_not_added(monkeypatch):
    monkeypatch.setattr(PA, "_kind_card", lambda view, q: {"ask": "Set it with isaac bundle decide?", "plain_detail": ""})
    assert PA.plain_fields(None, {"kind": "x"}) == {}


def test_the_optional_ask_names_at_most_six_and_counts_the_rest():
    ask = P.optional_ask([f"context.field_{n}" for n in range(9)])
    assert ask.endswith("(and 3 more)?")


# --- C8: the Athena message ------------------------------------------------------------------------------------------

def test_the_import_never_says_athena_projects_are_read():
    text = cli._athena_listed_only(3)
    assert "never read" in text and "read by `isaac process`" not in text and "3 Athena projects" in text
    assert cli._athena_listed_only(1).startswith("1 Athena project is")


# --- review fixes (#348) ---------------------------------------------------------------------------------------------

def _view_and_payload(grouped):
    b = M.load(grouped)
    payload = Q.consolidate(b)
    return b, payload, S._View(b, grouped, payload)


def test_plain_records_no_context_exposure(grouped, tmp_path, capsys):
    """Finding 8: --plain prints no context, so it records none (a model reading the context uses the JSON page)."""
    from isaac_api.local_import import question_context as QC

    _run(capsys, str(grouped), "--plain", "--limit", "200")
    assert not [e for e in M.load(grouped).get("exposures") or [] if e.get("command") == QC.EXPOSURE_COMMAND]


def test_plain_page_says_what_it_leaves_out_and_an_empty_page_is_not_a_range(grouped, capsys):
    """Findings 1 and 10: the plain page names what it omits; past the end it says so, not "showing 11-10"."""
    _, out = _run(capsys, str(grouped), "--plain", "--limit", "5")
    assert "the JSON page" in out and "minimum for one group" in out
    _, past = _run(capsys, str(grouped), "--plain", "--offset", "5000")
    assert "none at this offset" in past and "showing" not in past


def test_a_long_list_with_no_short_list_shows_the_first_few_and_counts_the_rest():
    """Finding 3: a closed list over the limit with no common options still has options and an Answer line."""
    options = [{"value": f"v{n}", "label": f"Value {n}"} for n in range(12)]
    got = PA._answer({"kind": "choice", "options": options, "common": []})
    assert len(got["options"]) == P.COMMON_FROM and got["options_total"] == 12
    line = PA._options_line(got)
    assert line.startswith("pick one: Value 0") and line.endswith("and 5 more")


def test_a_confirm_question_is_answered_yes_or_with_the_right_value_not_pick_one():
    """Finding 10: an "Is it X?" ask with a suggestion reads "yes, or ...", never a bare "pick one"."""
    answer = {"kind": "choice", "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]}
    assert PA._options_line(answer, True).startswith("yes, or pick another")
    assert PA._options_line(answer, False).startswith("pick one")
    assert PA._options_line({"kind": "number", "options": [], "unit": "V"}, True) == "yes, or a different number in V"


def test_a_suggestion_prints_its_quote_with_file_and_line_and_its_reason_once(grouped, capsys):
    """Findings 2 and 10: the quote the reason refers to is printed, and the card's detail does not repeat the reason."""
    _, out = _run(capsys, str(grouped), "--plain", "--limit", "200")
    blocks = [b for b in out.split("\n\n") if "Suggestion:" in b]
    assert blocks
    for block in blocks:
        reason = next(l for l in block.splitlines() if l.strip().startswith("Suggestion:")).split("): ", 1)[-1]
        assert block.count(reason) == 1, block
    quoted = [b for b in blocks if "Quoted:" in b]
    assert quoted and all("(" in next(l for l in b.splitlines() if "Quoted:" in l) for b in quoted)
    s = PA._suggested({"value": 1, "label": "1", "reason": "r", "evidence": [{"quote": "a"}, {"quote": "b"}, {"quote": "c"}]})
    assert s["evidence"] == {"quote": "a"} and s["evidence_more"] == 2


def test_a_label_question_shows_its_proposals_and_how_to_say_it_is_wrong(grouped):
    """Finding 4: one yes records every proposal, so every proposal is shown; no site wording "add a note", no flags."""
    b, payload, view = _view_and_payload(grouped)
    gids = [g["group_id"] for g in b["record_groups"]][:3]
    q = {"question_id": "Q-1111111111", "kind": "condition_label", "label": "history", "scope": "experiment",
         "target_field_path": "context.electrochemistry.notes", "allowed_decisions": ["confirm", "correct", "defer"],
         "proposals": [{"group_id": g, "value": v, "first_file": f"{n}_x.dat"}
                       for n, (g, v) in enumerate(zip(gids, ["after 1400 mV", "after 1400 mV", "before cycling"]))]}
    got = PA.plain_fields(view, q)
    assert got["ask"].endswith("?") and got["answer"]["kind"] == "yes_no"
    detail = got["plain_detail"]
    assert "'after 1400 mV' (2 measurements" in detail and "'before cycling' (1 measurement" in detail
    assert "millivolts or cycles" in detail and "add a note" not in detail and "give the wording you want" in detail
    assert P.not_plain(S._without_quotes(detail)) is None


def test_the_absorber_ask_carries_its_basis_and_scope(grouped):
    """Finding 5: an AI-only suggestion says so, and the question says which measurements it reaches."""
    b, payload, view = _view_and_payload(grouped)
    gids = [g["group_id"] for g in b["record_groups"]]
    q = {"question_id": "Q-2222222222", "kind": "confirm_absorber", "scope": "experiment",
         "targets": [{"kind": "record_group", "id": g} for g in gids[:4]],
         "hints": [{"kind": "suggested_absorber", "element": "Zz", "edge": "L3", "basis": "an AI reading of the files"}]}
    got = PA.plain_fields(view, q)
    assert got["ask"] == P.absorber_ask("Zz", "L3")
    assert got["suggested"]["basis"] == "reading" and "only an AI reading" in got["suggested"]["reason"]
    assert got["suggested"]["confidence"] is None  # nothing is invented
    assert got["about"].startswith("4 measurements") or got["about"].startswith("All ")
    files = {**q, "hints": [{**q["hints"][0], "basis": "stated in the files"}]}
    assert "AI" not in PA.plain_fields(view, files)["suggested"]["reason"]


def test_the_start_time_ask_says_who_it_reaches_and_who_it_does_not(grouped):
    """Finding 6."""
    b, payload, view = _view_and_payload(grouped)
    q = {"question_id": "Q-3333333333", "kind": "stated_utc_start_times", "scope": "experiment",
         "per_scope_targets": {"group:a": ["c1"], "group:b": ["c2"], "group:c": ["c3"]}, "answers_at_once": 3,
         "not_reached": [{"group_id": "g9", "question_id": "Q-x", "reason": "gap"}]}
    about = PA.plain_fields(view, q)["about"]
    assert about.startswith("3 measurements, answered together") and "1 more" in about


def test_the_dose_ask_counts_over_the_questions_own_groups(grouped):
    """Finding 7: counts come from the question's own set; where the site card's set differs there are no counts."""
    b, payload, view = _view_and_payload(grouped)
    gids = [g["group_id"] for g in b["record_groups"]]
    q = {"question_id": "Q-4444444444", "kind": "dose_reading", "scope": "experiment", "group_ids": gids[:2],
         "allowed_values": ["beam_damage", "not_beam_damage"]}
    # no result carries the site card's flag here, so the site card's set (none) differs from the question's own
    got = PA.plain_fields(view, q)
    assert got["ask"] == P.DOSE_ASK and got["about"] == "2 measurements"
    assert [o["value"] for o in got["answer"]["options"]] == ["beam_damage", "not_beam_damage"]


def test_the_counter_ask_says_how_to_name_one_part(grouped):
    """Finding 10: the `last` choice is not lost."""
    _, _, view = _view_and_payload(grouped)
    got = PA.plain_fields(view, {"question_id": "Q-5555555555", "kind": "naming_counter_positions", "positions": [1, "last"]})
    assert "the last part" in got["plain_detail"] and got["answer"]["kind"] == "yes_no"


def test_unread_athena_rows_and_the_import_agree_that_nothing_reads_them():
    """Finding 9: no marker says a later command reads an Athena project."""
    assert "never read" in cli.ATHENA_NOTE and not hasattr(cli, "READ_LATER_BY_SUFFIX")
