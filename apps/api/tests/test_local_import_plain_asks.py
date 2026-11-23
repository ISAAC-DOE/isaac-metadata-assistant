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
    assert full.count("Full text:") == 3 and len(full) > 2 * len(short)


def test_detail_alone_is_refused(grouped, capsys):
    code, out = _run(capsys, str(grouped), "--detail")
    assert code == cli.EXIT_USAGE and out == ""


def test_asking_for_the_plain_page_records_the_same_exposures(grouped, tmp_path, capsys):
    """Presentation only: the plain page shows the values the JSON page shows, so it records the same exposures."""
    a, b = tmp_path / "json", tmp_path / "plain"
    shutil.copytree(grouped, a), shutil.copytree(grouped, b)
    _run(capsys, str(a), "--limit", "50")
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
