"""EXTRA HINTS for the question site's cards: the ``--suggestions <file>`` of ``isaac bundle site export``.

A hint is never a value. It is shown on a card as a suggestion the scientist may accept, or beside it as context; the
decision recorded is always the scientist's own (``docs/question-site-contract.md``).

TWO SHAPES are read (:func:`read_suggestions`), and a file may mix them:

* THE CONTRACT'S: ``{"question_id": "Q-…", "suggestion": {value, label?, confidence, basis, reason, evidence}}`` or
  ``{"field": "<path>", "applies_to": <"all" | a sample name | a file name | [file names]>, "suggestion": {...}}``;
  as a list, under ``"suggestions"``, or as a map from question id to suggestion.
* A READING AUDIT'S: ``{"field", "applies_to": {"sample_token", "electrodes", "group_ids", "files"} | "beamtime…",
  "question_ids": [...], "suggested_value", "alternatives": [...], "confidence", "evidence": [{quote, file,
  locator}], "reasoning", "general_knowledge_note"}``. ``suggested_value`` is the suggestion's value, ``reasoning``
  its reason (its first two sentences), ``evidence`` its evidence, and its basis is ``reading``.

MATCHING (:func:`_rank`), most specific first; a card takes the entries of its best rank only:

1. one of the entry's question ids is a question the card covers (or the card's target id);
2. the entry's field is the card's, and every group the card is about is one of the entry's ``group_ids`` (the
   contract's shape: its ``applies_to`` names the card's sample, its file, or all of its files);
3. the entry's field is the card's, and the entry is beamtime-wide.

WHAT A MATCH BECOMES (:func:`apply`):

* a SUGGESTION, when the value is one the card can record with one click: a scalar, on the field's list where the
  field has one. Entries of one card that give different values give no suggestion (nothing is picked between them).
  A value the files give, which the card confirms as it stands, is never replaced.
* CONTEXT (quotes), when it is not: a value off the field's list, a value with several parts, or an entry about
  something that is no record field (its ``field`` starts ``processing:`` or ``grouping:``; it is shown on the
  matching processing card: the dose card when it speaks of beam damage or settling, or the card of a group it names).
* ``alternatives``: the short list of a choice card (``answer.common``, only values on the field's list), or named
  in the detail of a text card.

A value that has one part per record field (``{"name": …, "concentration_M": …}`` on ``…electrolyte``) is read for
the card of each part (``…electrolyte.name``); a value keyed by file name is read for the card of that one file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from . import plain_questions as P

CONFIDENCES = ("high", "medium", "low")
BASES = ("files", "logbook", "reading", "earlier_answer", "rule", "general_knowledge")
MAX_EVIDENCE = 3
MAX_CONTEXT_QUOTES = 6
MAX_ALTERNATIVES = 4
READING_SOURCE = "an AI reading of the files (not file evidence; the quote is as the reader gave it)"
GENERIC_REASON = "A reading of your files suggests this; the quotes show where."
#: an entry that is about no record field
NOTE_PREFIXES = ("processing:", "grouping:")
#: words that put a ``processing:`` entry on the dose card (``question_site.DOSE_TARGET_ID`` in its ids does too)
DOSE_WORDS = ("beam damage", "settling")


class HintsRefused(ValueError):
    """The suggestions file cannot be read at all."""


def read_suggestions(path: Path) -> list[dict]:
    """The entries of a ``--suggestions`` file, each normalised (:func:`normalise`)."""
    try:
        raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        raise HintsRefused(f"--suggestions: cannot read {Path(path).name!r} ({exc.__class__.__name__}).") from None
    except ValueError:
        raise HintsRefused(f"--suggestions: {Path(path).name!r} is not JSON.") from None
    if isinstance(raw, Mapping) and isinstance(raw.get("suggestions"), list):
        raw = raw["suggestions"]
    elif isinstance(raw, Mapping):
        raw = [{"question_id": k, "suggestion": v} for k, v in raw.items() if k not in ("format", "format_version")]
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise HintsRefused("--suggestions: expected {\"suggestions\": [...]}, a list of entries, or a map from "
                           "question id to suggestion.")
    return [normalise(e, n) for n, e in enumerate(raw)]


MAX_REASON_CHARS = 320


def two_sentences(text: Any) -> str:
    """The first two sentences of ``text`` (a reason on a card is at most two), at most :data:`MAX_REASON_CHARS`
    characters: the first sentence alone when two are longer, cut at a word when one is."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'“])", s)
    two = " ".join(parts[:2]).strip()
    if len(two) <= MAX_REASON_CHARS:
        return two
    one = parts[0].strip()
    if len(one) <= MAX_REASON_CHARS:
        return one
    return one[:MAX_REASON_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:(") + " …"


def normalise(e: Mapping, n: int) -> dict:
    """One entry of either shape as ``{n, question_ids, fields, group_ids, files, applies_to, beamtime, note_only,
    topic, suggestion, alternatives}``."""
    if isinstance(e.get("suggestion"), Mapping) or "suggested_value" not in e:
        s = dict(e.get("suggestion") or {}) if isinstance(e.get("suggestion"), Mapping) else {}
        applies = e.get("applies_to")
        return {"n": n, "question_ids": [e["question_id"]] if e.get("question_id") else list(e.get("question_ids") or ()),
                "fields": [str(e["field"])] if e.get("field") else [], "group_ids": None, "files": None,
                "applies_to": applies, "beamtime": applies in (None, "", "all", "*"), "note_only": False,
                "topic": str(e.get("field") or ""), "suggestion": s, "alternatives": list(e.get("alternatives") or ()),
                "shape": "contract"}
    topic = str(e.get("field") or "").strip()
    note_only = topic.casefold().startswith(NOTE_PREFIXES)
    fields: list[str] = []
    if not note_only:
        for part in topic.split(" / "):
            f = re.sub(r"\s*\(.*\)\s*$", "", part).strip()
            if f and "." not in f and fields:  # "…acquired_start_utc / acquired_end_utc": the second shares the parent
                f = fields[0].rsplit(".", 1)[0] + "." + f
            if f:
                fields.append(f)
    applies = e.get("applies_to")
    is_map = isinstance(applies, Mapping)
    groups = [str(g) for g in applies.get("group_ids") or ()] if is_map and isinstance(applies.get("group_ids"), list) else None
    files = [str(f) for f in applies.get("files") or ()] if is_map and isinstance(applies.get("files"), list) else None
    reason = two_sentences(e.get("reasoning"))
    return {"n": n, "question_ids": [str(q) for q in e.get("question_ids") or ()], "fields": fields, "group_ids": groups,
            "files": files, "applies_to": applies,
            "beamtime": isinstance(applies, str) and applies.strip().casefold().startswith("beamtime"),
            "note_only": note_only, "topic": topic,
            "suggestion": {"value": e.get("suggested_value"), "confidence": e.get("confidence"), "basis": "reading",
                           "reason": reason, "evidence": list(e.get("evidence") or ())},
            "alternatives": list(e.get("alternatives") or ()), "shape": "reading"}


def entry_problem(entry: Mapping) -> str | None:
    """Why an entry is not used on any card (None when it is well formed)."""
    s = entry["suggestion"]
    if entry["shape"] == "contract" and s.get("value") is None:
        return "it has no value"
    if s.get("confidence") not in CONFIDENCES:
        return f"its confidence is not one of {', '.join(CONFIDENCES)}"
    if s.get("basis") not in BASES:
        return f"its basis is not one of {', '.join(BASES)}"
    if s["basis"] == "general_knowledge" and s["confidence"] == "high":
        return "general knowledge is never a high-confidence suggestion (say low or medium)"
    if entry["shape"] == "contract":
        if not isinstance(s.get("reason"), str) or not s["reason"].strip():
            return "it gives no reason"
        if (why := P.not_plain(_unquoted(s["reason"]))) is not None:
            return f"its reason is not plain words: {why}"
    if not isinstance(s.get("evidence") or [], list):
        return "its evidence is not a list"
    if not entry["question_ids"] and not entry["fields"] and not entry["note_only"]:
        return "it names no question and no field"
    return None


def _unquoted(text: str) -> str:
    return re.sub(r"'[^']*'|“[^”]*”|\"[^\"]*\"", "''", str(text or ""))


def _card_ids(card: Mapping) -> set[str]:
    return {q["question_id"] for q in card.get("_questions") or ()} | ({card["_target_id"]} if card.get("_target_id") else set())


def _field_of(card: Mapping) -> str | None:
    return (card.get("field") or {}).get("path")


def _field_matches(entry: Mapping, card: Mapping) -> bool:
    field = _field_of(card)
    if not field:
        return False
    value = entry["suggestion"].get("value")
    for f in entry["fields"]:
        if f == field or (isinstance(value, Mapping) and field.startswith(f + ".") and field[len(f) + 1:] in value):
            return True
    return False


def _rank(entry: Mapping, card: Mapping) -> int | None:
    """How specifically ``entry`` names ``card`` (1 best … 3), or ``None`` when it does not."""
    if set(entry["question_ids"]) & _card_ids(card):
        return 1
    groups = set(card.get("_groups") or ())
    if entry["note_only"]:
        if _field_of(card) is not None or not card.get("_target_id"):
            return None
        if card.get("_is_dose"):
            return 3 if any(w in entry["topic"].casefold() for w in DOSE_WORDS) else None
        return 2 if entry["group_ids"] and groups and groups <= set(entry["group_ids"]) else None
    if not _field_matches(entry, card):
        return None
    if entry["shape"] == "reading":
        if entry["group_ids"] and groups and groups <= set(entry["group_ids"]):
            return 2
        return 3 if entry["beamtime"] else None
    want = entry["applies_to"]
    if entry["question_ids"]:
        return None
    if entry["beamtime"]:
        return 3
    applies = card["applies_to"]
    names = set(applies.get("items") or ())
    if isinstance(want, str):
        sample = str(card.get("_sample") or "")  # "ZZ1 (no. 01)": matched whole, or by the name alone
        mine = {sample.casefold(), sample.split(" (")[0].casefold()} - {""}
        return 2 if want == applies.get("summary") or want in names or want.casefold() in mine else None
    if isinstance(want, list) and not applies.get("more"):
        return 2 if names and names <= {str(w) for w in want} else None
    return None


def _value_for(entry: Mapping, card: Mapping) -> Any:
    """The entry's value for THIS card: itself, its part for the card's field, or its part for the card's one file."""
    value = entry["suggestion"].get("value")
    if not isinstance(value, Mapping):
        return value
    field = _field_of(card) or ""
    for f in entry["fields"]:
        if field.startswith(f + ".") and field[len(f) + 1:] in value:
            return value[field[len(f) + 1:]]
    items = card["applies_to"].get("items") or ()
    if card["applies_to"].get("count") == 1 and items:
        for key, part in value.items():
            if str(key) == items[0] or PurePosixPath(str(key)).stem == items[0]:
                return part
    return None


def _option_value(card: Mapping, value: Any) -> Any:
    """``value`` as one of the card's options (exactly, or its words before a remark in brackets), else ``None``."""
    options = [o["value"] for o in card["answer"].get("options") or ()]
    if value in options:
        return value
    if isinstance(value, str):
        head = value.split(" (")[0].strip()
        return head if head in options else None
    return None


def _quotes(entry: Mapping, label: str) -> dict | None:
    items = [{"quote": str(e.get("quote")), "file": e.get("file"), "locator": e.get("locator")}
             for e in entry["suggestion"].get("evidence") or () if isinstance(e, Mapping) and e.get("quote")]
    if not items:
        return None
    return {"kind": "quotes", "label": label, "source": READING_SOURCE, "items": items[:MAX_CONTEXT_QUOTES]}


def _said(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 140 else text[:137] + "…"


def as_context(card: dict, entry: Mapping, value: Any, why: str | None) -> bool:
    """Show an entry beside the card (quotes only): what a reading found, never offered as a one-click answer."""
    label = ("From your files, found by a reading" if value is None or entry["note_only"] else
             f"A reading of your files suggests “{_said(value)}”" + (f" ({why})" if why else ""))
    item = _quotes(entry, label)
    if item is None:
        return False
    card.setdefault("_extra_context", []).append(item)
    return True


def apply(cards: Sequence[dict], entries: Sequence[Mapping], with_common) -> list[dict]:
    """Put each entry on the cards it names. ``with_common(answer, path, suggestion)`` is the export's own short-list
    rule. Returns one report row per entry: ``{entry, suggested_on, context_on, problem?}``."""
    rows = {e["n"]: {"entry": e["n"], "suggested_on": 0, "context_on": 0} for e in entries}
    usable = []
    for e in entries:
        problem = entry_problem(e)
        if problem:
            rows[e["n"]]["problem"] = problem
        else:
            usable.append(e)
    for card in cards:
        ranked = [(r, e) for e in usable if (r := _rank(e, card)) is not None]
        if not ranked:
            continue
        best = min(r for r, _ in ranked)
        mine = [e for r, e in ranked if r == best]
        notes = [e for e in mine if e["note_only"]]
        hints = [e for e in mine if not e["note_only"]]
        for e in notes:
            if as_context(card, e, None, None):
                rows[e["n"]]["context_on"] += 1
        if not hints:
            continue
        cover = card["covers"][0]
        kind = card["answer"]["kind"]
        values = [(e, _value_for(e, card)) for e in hints]
        distinct = {json.dumps(v, sort_keys=True, default=str) for _, v in values if v is not None}
        confirms = ((card.get("suggestion") or {}).get("basis") == "files"
                    and (cover.get("on_accept") or {}).get("decision") == "confirm")
        for e, v in values:
            why = None
            if v is None:
                why = "no single value for this card"
            elif isinstance(v, (Mapping, list)):
                why = "it has several parts"
            elif len(distinct) > 1:
                why = "the readings for these measurements differ"
            elif kind == "yes_no" or cover.get("on_value") is None:
                why = "this card takes yes or no"
            elif confirms and json.dumps(v, default=str) == json.dumps(card["suggestion"].get("value"), default=str):
                rows[e["n"]]["agrees_on"] = rows[e["n"]].get("agrees_on", 0) + 1  # the files' own value says the same
                continue
            elif confirms:
                why = "your files already give another value here"
            elif card["answer"].get("options") and _option_value(card, v) is None:
                why = "not on this field's list"
            if why:
                if as_context(card, e, v, why if v is not None else None):
                    rows[e["n"]]["context_on"] += 1
                continue
            if card.get("_suggestion_entry") is not None:  # a second entry with the same value: its quotes too
                more = [x for x in e["suggestion"].get("evidence") or () if isinstance(x, Mapping)]
                card["suggestion"]["evidence"] = (card["suggestion"]["evidence"] + more)[:MAX_EVIDENCE]
                rows[e["n"]]["suggested_on"] += 1
                continue
            s = e["suggestion"]
            value = _option_value(card, v) if card["answer"].get("options") else v
            reason = str(s.get("reason") or "").strip()
            if not reason or P.not_plain(_unquoted(reason)):
                reason = GENERIC_REASON
            label = s.get("label") or next((o["label"] for o in card["answer"].get("options") or () if o["value"] == value),
                                           P.value_label(value, card["answer"].get("unit")))
            card["suggestion"] = {"value": value, "label": str(label), "confidence": s["confidence"], "basis": s["basis"],
                                  "reason": reason,
                                  "evidence": [dict(x) for x in s.get("evidence") or () if isinstance(x, Mapping)][:MAX_EVIDENCE]}
            for c in card["covers"]:
                c["on_accept"] = {"decision": c["on_value"]["decision"], "value": value}
            card["_suggestion_entry"] = e["n"]
            card["_suggestion_source"] = e
            rows[e["n"]]["suggested_on"] += 1
            # a reading found what no parser did: the card no longer says that no file states it
            card["detail"] = str(card.get("detail") or "").replace(P.NONE_SAY, "", 1).strip()
            alts = [a for a in e["alternatives"] if isinstance(a, (str, int, float))]
            base = {k: x for k, x in card["answer"].items() if k != "common"}
            if card["answer"].get("options"):
                picks = [value, *[o for a in alts if (o := _option_value(card, a)) is not None]]
                common = list(dict.fromkeys([*picks, *(with_common(base, _field_of(card) or "", card["suggestion"]).get("common") or ())]))
                card["answer"] = {**base, "common": common}
            else:
                card["answer"] = base
                said = [f"“{_said(a)}”" for a in alts[:MAX_ALTERNATIVES]]
                if said:
                    first = re.split(r"(?<=[.!?])\s", str(card.get("detail") or ""), maxsplit=1)[0].strip()
                    card["detail"] = f"{first} A reading of your files also names: {P.or_list(said)}.".strip()
    for e in usable:
        row = rows[e["n"]]
        if not row["suggested_on"] and not row["context_on"] and not row.get("agrees_on"):
            row["problem"] = "no card of this export matches it"
    return [rows[e["n"]] for e in entries]


def demote(card: dict, why: str) -> None:
    """A file suggestion whose accept call the decide path refuses is not offered: it is shown as context instead."""
    entry = card.pop("_suggestion_source", None)
    shown = (card.get("suggestion") or {}).get("value")
    if entry is not None:
        as_context(card, entry, shown, "not a value this field takes as it stands")
