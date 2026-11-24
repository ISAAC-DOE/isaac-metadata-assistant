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

import copy
import re
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
#: What the opt-in answer memory adds to a question (answer_memory.annotate): never read for a plain field.
_MEMORY_KEYS = ("earlier_answers", "earlier_answers_statement")


def _unit(q: Mapping) -> dict:
    return {"questions": [q], "named": q, "same_reading": False, "each": False, "only_scopes": None, "field": None,
            "identified": False, "lone": False}


def _suggested(s: Mapping | None) -> dict | None:
    if not s:
        return None
    quotes = list(s.get("evidence") or ())
    quote = quotes[0] if quotes else None
    return {"value": s.get("value"), "label": s.get("label"), "confidence": s.get("confidence"), "basis": s.get("basis"),
            "reason": s.get("reason"),
            **({"evidence": dict(quote)} if quote else {}),
            # the first quote is shown; the others are counted (the full set is in the question's hints)
            **({"evidence_more": len(quotes) - 1} if len(quotes) > 1 else {})}


def _answer(card_answer: Mapping) -> dict:
    options = [{"value": o["value"], "label": o.get("label", o["value"])} for o in card_answer.get("options") or ()]
    total = len(options)
    if total > _SHOW_OPTIONS:
        common = set(card_answer.get("common") or ())
        # the card's short list where it has one, else the first few: never none (the rest is `options_total`)
        options = [o for o in options if o["value"] in common] or options[:_SHOW_OPTIONS]
    return {"kind": card_answer.get("kind"), "options": options,
            **({"options_total": total} if total > len(options) else {}),
            **({"unit": card_answer["unit"]} if card_answer.get("unit") else {})}


_YES_NO = {"kind": "yes_no", "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]}


def _about(applies: Mapping) -> str:
    items = list(applies.get("items") or ())[:_ABOUT_ITEMS]
    about = applies.get("summary") or ""
    if items and applies.get("count", 0) > 1 and not str(about).startswith("All "):
        about = f"{about}, for example {', '.join(items)}"
    return about


def _from_card(card: Mapping, q: Mapping, answer: Mapping | None = None, detail: str | None = None) -> dict:
    suggested = _suggested(card.get("suggestion"))
    text = card.get("detail") if detail is None else detail
    # the suggestion's reason is printed with the suggestion: the detail does not say it a second time
    if suggested and suggested.get("reason") and text:
        text = " ".join(text.replace(str(suggested["reason"]), "").split())
    return {"ask": card["title"], "answer": answer or _answer(card["answer"]), "suggested": suggested,
            "about": _about(card.get("applies_to") or {}), "plain_detail": text or ""}


#: What a proposed label's ONE yes cannot tell, said where the label is asked (copy of the question's own caution).
_LABEL_CAUTION = {
    "history": "It only splits the file-name number into words; it does not say whether the number is millivolts or cycles.",
    "sample_id": "A sample ID names one physical object and must be the same on every record of it.",
}
_MAX_PROPOSED = 12
#: How a "not right" is answered. A sentence or a tag is recorded as given; a sample ID or a filter is a PATTERN filled
#: in for each measurement (labels.SAMPLE_ID_PLACEHOLDERS / FILTER_PLACEHOLDERS), because one literal would give every
#: electrode the same ID (refused) or every group the same filter (review of #348).
_LABEL_CORRECTION_LITERAL = "If it is not right, give the wording you want instead, and that is what is recorded."
_LABEL_CORRECTION = {
    "sample_id": ("If it is not right, give the ID you want. Where there is more than one electrode, write it with "
                  "{electrode} (and {sample} or {beamtime} if you like, for example '{sample}-e{electrode}'), so each "
                  "electrode keeps its own ID."),
    "filter": ("If it is not right, give the wording you want. Where the measurements had different filters, write it "
               "with {filter} for the number (for example 'filter{filter}'), so each keeps its own."),
}


def _label_detail(card: Mapping, q: Mapping) -> str:
    """What the one yes records: every proposal (compact), the caution, and how to say it is not right."""
    rows = next((c.get("rows") for c in card.get("context") or () if c.get("kind") == "values"), None) or []
    shown = [f"'{r[0]}' ({r[1]} measurement{'s' if r[1] != '1' else ''}, for example {r[2]})" for r in rows[:_MAX_PROPOSED]]
    more = len(rows) - len(shown)
    proposed = ("Proposed from the file names: " + "; ".join(shown) + (f"; and {more} more" if more > 0 else "") + "."
                if shown else "Proposed from the file names.")
    return " ".join(x for x in (proposed, _LABEL_CAUTION.get(str(q.get("label"))),
                                "Nothing is recorded until you say yes. "
                                + _LABEL_CORRECTION.get(str(q.get("label")), _LABEL_CORRECTION_LITERAL)) if x)


def _kind_card(view: S._View, q: Mapping) -> dict | None:
    """The plain fields of one question, or ``None`` when no wording covers it."""
    kind, path = q.get("kind"), q.get("target_field_path")
    if kind in S.VALUE_KINDS and isinstance(path, str) and "[]" not in path:
        return _from_card(_card(S._value_card, view, q), q)
    if kind == "condition_label" and q.get("label") in S.LABEL_ASKS and q.get("proposals"):
        card = _card(S._label_card, view, q)
        return _from_card(card, q, answer=dict(_YES_NO), detail=_label_detail(card, q))
    if kind == "optional_values" and q.get("fields"):
        return {"ask": P.optional_ask(sorted(q["fields"])), "answer": {"kind": "text", "options": []},
                "suggested": None, "about": "", "plain_detail": "Each one you know is answered on its own."}
    if kind == "naming_counter_positions" and q.get("positions"):
        return {"ask": P.counter_ask(q["positions"]), "answer": dict(_YES_NO), "suggested": None,
                "about": "", "plain_detail": "If only one of them is a counter, say which: a part number, or the last part."}
    if kind == "confirm_absorber":
        hint = next((h for h in q.get("hints") or () if h.get("kind") == "suggested_absorber"
                     and h.get("element") and h.get("edge")), None)
        if hint:
            pair = f"{hint['element']} {hint['edge']}"
            basis = str(hint.get("basis") or "")
            only_ai = "AI reading" in basis and "stated in the files" not in basis
            ids = [t["id"] for t in q.get("targets") or () if t.get("kind") == "record_group"]
            groups = view.reach(ids) if ids else []
            about = _about(S._applies_to(view, groups, None, False)) if groups else ""
            return {"ask": P.absorber_ask(hint["element"], hint["edge"]), "answer": dict(_YES_NO),
                    "suggested": {"value": pair, "label": pair, "confidence": None,
                                  # the site's vocabulary: an AI reading is "reading", the rest "files"
                                  "basis": "reading" if only_ai else "files",
                                  "reason": ("No file the import counts as evidence states it; only an AI reading of the "
                                             "files suggests it, so it needs your confirmation." if only_ai else
                                             f"{basis[:1].upper()}{basis[1:]}." if basis else "Suggested from the files.")},
                    "about": about,
                    "plain_detail": "Answer once for all of them, or one by one if a group differs (a reference foil or "
                                    "a blank cell may)."}
    if kind == "stated_utc_start_times":
        reached = len(q.get("per_scope_targets") or {}) or int(q.get("answers_at_once") or 0)
        left = len(q.get("not_reached") or ())
        about = (f"{reached} measurement{'s' if reached != 1 else ''}, answered together" if reached else "")
        if left:
            about += (f"; {left} more with a start-time question that this answer does not reach "
                      "(they are answered one by one)")
        return {"ask": P.START_TIME_ASK, "answer": dict(_YES_NO), "suggested": None, "about": about,
                "plain_detail": "Each file states when it was created, as a UTC instant."}
    if kind == "dose_reading":
        card = _dose_card_of(view, q)
        options = [{"value": v, "label": label} for v, label in S.DOSE_LABELS.items()
                   if v in (q.get("allowed_values") or ())]
        return {"ask": card["title"] if card else P.DOSE_ASK, "answer": {"kind": "choice", "options": options},
                "suggested": None, "about": card["applies_to"]["summary"] if card else f"{len(q.get('group_ids') or ())} measurements",
                "plain_detail": card["detail"] if card else ""}
    return None


def _dose_card_of(view: S._View, q: Mapping) -> dict | None:
    """The site's dose card counted over THIS question's own groups (``group_ids``, from ``dose_question_results``).
    The site card selects its groups by a narrower flag test, so its counts can differ; when they do, there is no card
    here and the ask carries no counts (the site card itself is not changed)."""
    own = list(q.get("group_ids") or ())
    narrowed = copy.copy(view)
    narrowed.live = [g for g in view.live if g in set(own)]
    card = S._dose_card(narrowed)
    return card if card and set(card.get("_groups") or ()) == set(own) else None


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
    # THE EARLIER-ANSWER MEMORY (answer_memory, opt-in) NEVER CHANGES A PLAIN FIELD: its hint stays in `earlier_answers`,
    # labelled as an earlier answer, and is not a suggestion from the files. The fields are built from the question as
    # it is without the memory, so ask / answer / suggested are the same whether the memory is on or off.
    bare = [{k: v for k, v in q.items() if k not in _MEMORY_KEYS} for q in page]
    view = S._View(bundle, Path(bundle_dir), {**payload, "questions": bare})
    return [{**q, **plain_fields(view, b)} for q, b in zip(page, bare)]


def missing(page: Sequence[Mapping]) -> int:
    """How many questions of ``page`` have no ``ask``."""
    return sum(1 for q in page if "ask" not in q)


# --- the plain page: what `bundle questions --plain` prints ----------------------------------------------------------

_CONFIRMING = re.compile(r"^(?:Is|Are|Was|Were|Should|Do|Does|Did|Can)\b")


def _confirms(q: Mapping) -> bool:
    """Whether the ask puts the suggestion as a yes / no ("Is the absorbing element and edge Ir L3?"), so "yes" answers
    it. An either/or ask ("Was this done operando, in situ, ex situ or in silico?") does not name one value to say yes
    to, so "yes" means nothing there: it is offered only when the suggested value is in the ask (review of #348)."""
    ask, s = str(q.get("ask") or ""), q.get("suggested") or {}
    if not s or not _CONFIRMING.match(ask):
        return False
    def words(*xs: Any) -> set[str]:
        return {str(x).casefold() for x in xs if x is not None and str(x).strip()}

    def found(x: str, text: str) -> bool:
        return re.search(rf"(?<![\w]){re.escape(x)}(?![\w])", text) is not None

    text = ask.casefold()
    said = words(s.get("label"), s.get("value"))
    if not any(found(x, text) for x in said):
        return False
    # ...and, with the suggestion taken out (so "XAS" is not found inside "HERFD-XAS"), names no other answer and no
    # "or": "Is this experimental or computational work?" is an either/or
    for x in sorted(said, key=len, reverse=True):
        text = re.sub(rf"(?<![\w]){re.escape(x)}(?![\w])", " ", text)
    others = set().union(*(words(o.get("label"), o.get("value")) for o in (q.get("answer") or {}).get("options") or ()))
    return not any(found(x, text) for x in others - said) and not re.search(r"\bor\b", text)


def _options_line(answer: Mapping, confirming: bool = False) -> str:
    kind, options = answer.get("kind"), answer.get("options") or ()
    labels = [str(o.get("label") or o["value"]) for o in options]
    more = int(answer.get("options_total") or 0) - len(options)
    tail = f" and {more} more" if more > 0 else ""
    if kind == "yes_no":
        return "yes or no"
    # a question put as "Is it X?" is answered yes, or with the right value: said so, not "pick one" after a yes/no ask
    yes_first = confirming and kind in ("choice", "number", "text")
    if kind == "choice" and labels:
        return f"{'yes, or pick another' if yes_first else 'pick one'}: {'; '.join(labels)}{tail}"
    if kind == "number":
        unit = ' in ' + str(answer['unit']) if answer.get('unit') else ''
        return f"yes, or a different number{unit}" if yes_first else f"a number{unit}"
    if kind == "text":
        return "yes, or type the right one" if yes_first else "type it"
    return ""


def render(report: Mapping, *, detail: bool = False) -> str:
    """The plain page as text: each question's ask, who it is about, its options and its suggestion, its id last."""
    questions = report.get("questions") or []
    counts = report.get("counts") or {}
    shown = (f"showing {report.get('offset', 0) + 1}-{report.get('offset', 0) + len(questions)}" if questions
             else "none at this offset")
    lines = [f"{report.get('total', len(questions))} question(s) listed"
             + (f", {counts['blocking']} that block export" if counts.get("blocking") is not None else "")
             + f"; {shown}.",
             "This page is the asks only. It leaves out the counts, the minimum for one group, each answer command, the "
             "context and the evidence: the JSON page (without --plain) has them.", ""]
    for n, q in enumerate(questions, start=report.get("offset", 0) + 1):
        lines.append(f"{n}. {q.get('ask') or '(no plain wording yet)'}" + ("  [blocks export]" if q.get("blocking") else ""))
        if q.get("about"):
            lines.append(f"   About: {q['about']}")
        answer = q.get("answer") or {}
        if (shape := _options_line(answer, _confirms(q))):
            lines.append(f"   Answer: {shape}")
        s = q.get("suggested")
        if s:
            how = f" ({s['confidence']})" if s.get("confidence") else ""
            lines.append(f"   Suggestion: {s.get('label')}{how}: {s.get('reason')}")
            if (quote := s.get("evidence")):
                where = ", ".join(str(x) for x in (quote.get("file"), quote.get("locator")) if x)
                more = int(s.get("evidence_more") or 0)
                lines.append(f"   Quoted: '{quote.get('quote')}'" + (f" ({where})" if where else "")
                             + (f", and {more} more quote{'s' if more != 1 else ''}" if more else ""))
        for e in q.get("earlier_answers") or ():  # the opt-in memory, shown as what it is: an earlier answer
            lines.append(f"   Earlier answer: {e.get('value')}"
                         + (f" ({e.get('by') or 'a scientist'}, {e['date']})" if e.get("date") else ""))
        if q.get("plain_detail"):
            lines.append(f"   {q['plain_detail']}")
        if detail or "ask" not in q:
            lines.append(f"   Full text: {q.get('text')}")
        lines.append(f"   Question {q.get('question_id')}")
        lines.append("")
    if report.get("more"):
        lines.append(str(report["more"]))
    return "\n".join(lines).rstrip() + "\n"
