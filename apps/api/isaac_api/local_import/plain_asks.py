"""PLAIN ASKS for ``isaac bundle questions``: each question's one-sentence ask, its options and its suggestion.

The command line's question ``text`` is written for the tool (field paths, decision names, flags, ids): the median is
over a thousand characters. A scientist, and a model talking to one, wants the ask. This module adds it to a question
WITHOUT changing the question: every key it adds is new (``ask``, ``answer``, ``suggested``, ``about``,
``plain_detail``), ``text`` and the rest stay as they were, and ``bundle show <dir> question <id>`` still prints the
whole question.

NO SECOND WORDING SYSTEM. The ask, the options and the suggestion are the question site's own: a question is turned
into a one-question unit and given to ``question_site``'s card builders, whose wording is ``plain_questions``. The few
kinds the site does not ask (the file-name counter, the absorber, the start-time choice, the dose question, the
optional list) take their ask from ``plain_questions`` too. A kind with no wording, or an ask that is not plain
(``plain_questions.not_plain``), gets no ``ask``: it is counted (:func:`missing`) and the question's ``text`` is
what there is. COPY ONLY: nothing here reads a value from a file, picks one, or says more than the question says.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from . import plain_questions as P
from . import question_site as S

#: Keys this module adds to a question.
KEYS = ("ask", "answer", "suggested", "about", "plain_detail")

#: Options shown in full up to this many; a longer list shows the card's short list, the rest named by
#: ``answer.options_total`` (the field's whole list is in ``allowed_values_by_field``).
_SHOW_OPTIONS = P.COMMON_FROM
_ABOUT_ITEMS = 2


def _unit(q: Mapping) -> dict:
    return {"questions": [q], "named": q, "same_reading": False, "each": False, "only_scopes": None, "field": None,
            "identified": False, "lone": False}


def _suggested(s: Mapping | None) -> dict | None:
    if not s:
        return None
    quote = next(iter(s.get("evidence") or ()), None)
    return {"value": s.get("value"), "label": s.get("label"), "confidence": s.get("confidence"), "basis": s.get("basis"),
            "reason": s.get("reason"), **({"evidence": dict(quote)} if quote else {})}


def _answer(card_answer: Mapping) -> dict:
    options = [{"value": o["value"], "label": o.get("label", o["value"])} for o in card_answer.get("options") or ()]
    total = len(options)
    if total > _SHOW_OPTIONS:
        common = set(card_answer.get("common") or ())
        options = [o for o in options if o["value"] in common]
    return {"kind": card_answer.get("kind"), "options": options,
            **({"options_total": total} if total > len(options) else {}),
            **({"unit": card_answer["unit"]} if card_answer.get("unit") else {})}


_YES_NO = {"kind": "yes_no", "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]}


def _from_card(card: Mapping, q: Mapping, answer: Mapping | None = None) -> dict:
    applies = card.get("applies_to") or {}
    items = list(applies.get("items") or ())[:_ABOUT_ITEMS]
    about = applies.get("summary") or ""
    if items and applies.get("count", 0) > 1 and not str(about).startswith("All "):
        about = f"{about}, for example {', '.join(items)}"
    return {"ask": card["title"], "answer": answer or _answer(card["answer"]), "suggested": _suggested(card.get("suggestion")),
            "about": about, "plain_detail": card.get("detail") or ""}


def _kind_card(view: S._View, q: Mapping) -> dict | None:
    """The plain fields of one question, or ``None`` when no wording covers it."""
    kind, path = q.get("kind"), q.get("target_field_path")
    if kind in S.VALUE_KINDS and isinstance(path, str) and "[]" not in path:
        return _from_card(_card(S._value_card, view, q), q)
    if kind == "condition_label" and q.get("label") in S.LABEL_ASKS and q.get("proposals"):
        return _from_card(_card(S._label_card, view, q), q, answer=dict(_YES_NO))
    if kind == "optional_values" and q.get("fields"):
        return {"ask": P.optional_ask(sorted(q["fields"])), "answer": {"kind": "text", "options": []},
                "suggested": None, "about": "", "plain_detail": "Each one you know is answered on its own."}
    if kind == "naming_counter_positions" and q.get("positions"):
        return {"ask": P.counter_ask(q["positions"]), "answer": dict(_YES_NO), "suggested": None,
                "about": "", "plain_detail": ""}
    if kind == "confirm_absorber":
        hint = next((h for h in q.get("hints") or () if h.get("kind") == "suggested_absorber"
                     and h.get("element") and h.get("edge")), None)
        if hint:
            return {"ask": P.absorber_ask(hint["element"], hint["edge"]), "answer": dict(_YES_NO), "suggested": None,
                    "about": "", "plain_detail": ""}
    if kind == "stated_utc_start_times":
        return {"ask": P.START_TIME_ASK, "answer": dict(_YES_NO), "suggested": None, "about": "",
                "plain_detail": "Each file states when it was created, as a UTC instant."}
    if kind == "dose_reading":
        card = S._dose_card(view)
        options = [{"value": v, "label": label} for v, label in S.DOSE_LABELS.items()
                   if v in (q.get("allowed_values") or ())]
        return {"ask": card["title"] if card else P.DOSE_ASK, "answer": {"kind": "choice", "options": options},
                "suggested": None, "about": card["applies_to"]["summary"] if card else "",
                "plain_detail": card["detail"] if card else ""}
    return None


def _card(build, view: S._View, q: Mapping) -> dict:
    card = build(view, _unit(q))
    # the card's detail also says what ONE ANSWER ON THE SITE covers and that a note holds it back: that is the site's
    # rule, not this command's, so only its lead and its "what to do" are kept ("About" says who it reaches)
    if "_lead" in card:
        card["detail"] = " ".join(x for x in (card.get("_lead"), card.get("_alt") or card.get("_then")) if x)
    return card


def plain_fields(view: S._View, q: Mapping) -> dict:
    """The keys to add to ``q`` (empty when no wording covers it, or when the wording would not be plain)."""
    try:
        got = _kind_card(view, q)
    except S._LeftOut:
        return {}
    if not got:
        return {}
    if P.not_plain(got["ask"]) or P.not_plain(S._without_quotes(got["plain_detail"])):
        return {}
    return got


def annotate(page: Sequence[Mapping], bundle: Mapping, bundle_dir: Path, payload: Mapping) -> list[dict]:
    """``page`` with each question's plain keys added (a question with no plain wording is returned as it was)."""
    view = S._View(bundle, Path(bundle_dir), {**payload, "questions": list(page)})
    return [{**q, **plain_fields(view, q)} for q in page]


def missing(page: Sequence[Mapping]) -> int:
    """How many questions of ``page`` have no ``ask``."""
    return sum(1 for q in page if "ask" not in q)


# --- the plain page: what `bundle questions --plain` prints ----------------------------------------------------------

def _options_line(answer: Mapping) -> str:
    kind, options = answer.get("kind"), answer.get("options") or ()
    labels = [str(o.get("label") or o["value"]) for o in options]
    more = int(answer.get("options_total") or 0) - len(options)
    tail = f" and {more} more" if more > 0 else ""
    if kind == "yes_no":
        return "yes or no"
    if kind == "choice" and labels:
        return f"pick one: {'; '.join(labels)}{tail}"
    if kind == "number":
        return f"a number{' in ' + str(answer['unit']) if answer.get('unit') else ''}"
    return "type it" if kind == "text" else ""


def render(report: Mapping, *, detail: bool = False) -> str:
    """The plain page as text: each question's ask, who it is about, its options and its suggestion, its id last."""
    questions = report.get("questions") or []
    counts = report.get("counts") or {}
    lines = [f"{report.get('total', len(questions))} question(s) listed"
             + (f", {counts['blocking']} that block export" if counts.get("blocking") is not None else "")
             + f"; showing {report.get('offset', 0) + 1}-{report.get('offset', 0) + len(questions)}.", ""]
    for n, q in enumerate(questions, start=report.get("offset", 0) + 1):
        lines.append(f"{n}. {q.get('ask') or '(no plain wording yet)'}" + ("  [blocks export]" if q.get("blocking") else ""))
        if q.get("about"):
            lines.append(f"   About: {q['about']}")
        answer = q.get("answer") or {}
        if (shape := _options_line(answer)):
            lines.append(f"   Answer: {shape}")
        s = q.get("suggested")
        if s:
            lines.append(f"   Suggestion: {s.get('label')} ({s.get('confidence')}): {s.get('reason')}")
        if q.get("plain_detail"):
            lines.append(f"   {q['plain_detail']}")
        if detail or "ask" not in q:
            lines.append(f"   Full text: {q.get('text')}")
        lines.append(f"   Question {q.get('question_id')}")
        lines.append("")
    if report.get("more"):
        lines.append(str(report["more"]))
    return "\n".join(lines).rstrip() + "\n"
