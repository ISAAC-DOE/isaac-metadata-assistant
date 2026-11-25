"""THE QUESTION SITE, import half: the site's ``answers.json`` read back as recorded decisions
(``isaac bundle site import``). The contract is ``docs/question-site-contract.md``.

Modelled on the question-workbook import (``workbook_answers.py``), and sharing its helpers:

* PREVIEW IS THE DEFAULT and writes nothing: every decision is dry-run through the decide path on a temporary copy
  of ``bundle.json``, so not even a lock file is created in the bundle folder. ``apply`` records each one through
  :func:`mutations.decide_question` / :func:`mutations.decide` (``question_site.run_call``, the same call the export
  dry-ran), with ``by`` = the answer's own name followed by " (question site)" and a note naming the card and the
  time it was answered.
* ``accept`` records the card's suggestion only while ``site-data.json`` still shows the value the scientist saw;
  a card with no suggestion, or another one, is refused.
* ``value`` is parsed as the template import parses a cell (``template._parse_for``) and checked by the decide path
  itself. A TYPED word off the field's list is kept as a vocabulary request, exactly as ``decide --as-said`` keeps
  it: it is the scientist's own word. A picked value is never kept that way.
* ``dont_know`` records ``defer`` (a card that takes none records nothing, and says so).
* A ``note`` is reported and never turned into a decision. A "no" to a yes / no card records nothing either: its
  note says what a person should do.
* AN ANSWER WITH A NOTE ON A CARD FOR SEVERAL MEASUREMENTS IS HELD (review C1): the note may name exceptions
  ("all but the pellet"), and one answer recorded for all of them would then be wrong for some. Nothing is
  recorded for that card until a person has read the note: ``notes_read`` (``--note-read <card id>``) says they
  have and that it names no exception.
* A card the bundle no longer asks (answered since with another answer, or the bundle changed) is reported, not
  applied. A card answered since with the SAME answer is "already recorded", so a second run records nothing.
* ``apply`` refuses a bundle inside a folder whose name starts with ``_runs`` (``workbook_answers.protected_part``).
* ``remember``: after an apply, the answers this import recorded are also written to the answer memory
  (``answer_memory``), only when the scientist has turned it on; when it is off nothing is remembered, and the
  report says so.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import bundle as B
from . import question_site as S
from . import template as T
from . import workbook_answers as W

FORMAT_ID = "isaac.question_site_import"
FORMAT_VERSION = "1.0.0"
ANSWERS_FORMAT_ID = "isaac.question_site_answers"
BY_SUFFIX = " (question site)"
ACTIONS = ("accept", "value", "dont_know")
_YES = frozenset({"yes", "y", "true"})
_NO = frozenset({"no", "n", "false"})
#: the decisions that answer what a target card asks: an earlier one of them means the card is no longer asked
_TARGET_FAMILIES = (frozenset({B.DOSE_READING_DECISION}), frozenset({"confirm", "reject", "split", "merge"}),
                    frozenset(B.PROCESSING_STATE_DECISIONS))


def _read(path: Path, what: str, format_id: str) -> dict:
    try:
        raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        raise S.SiteRefused(f"Cannot read {what} {Path(path).name!r} ({exc.__class__.__name__}). Nothing was recorded.",
                            code=S.EXIT_INPUT_REFUSED) from None
    except ValueError:
        raise S.SiteRefused(f"{what} {Path(path).name!r} is not JSON. Nothing was recorded.",
                            code=S.EXIT_INPUT_REFUSED) from None
    if not isinstance(raw, Mapping) or raw.get("format") != format_id:
        raise S.SiteRefused(f"{Path(path).name!r} is not {what} (its format is not {format_id!r}). Nothing was "
                            "recorded.", code=S.EXIT_INPUT_REFUSED)
    if str(raw.get("format_version") or "").split(".")[0] != "1":
        raise S.SiteRefused(f"{Path(path).name!r} is format version {raw.get('format_version')!r}; this build reads "
                            "1.x. Nothing was recorded.", code=S.EXIT_INPUT_REFUSED)
    return dict(raw)


def decision_note(card: Mapping, at: Any) -> str:
    """The note every decision of one answer carries: the card and when it was answered."""
    return f"question site card {card['card_id']} \"{W._clip(card.get('title'), 120)}\", answered {at}"


def _same_value(path: str | None, a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if T.agrees_for(path, a, b):
        return True
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _yes_no(value: Any) -> bool | None:
    word = str(value).strip().casefold() if not isinstance(value, bool) else ("true" if value else "false")
    return True if word in _YES else False if word in _NO else None


class _Ctx:
    def __init__(self, bundle: Mapping, bundle_arg: str):
        from . import questions as Q

        self.bundle, self.bundle_arg = bundle, bundle_arg
        self.open = Q.consolidate(bundle)
        self.schema, _ = Q._target_schema()
        self._rules: dict[str, dict] = {}
        self._answered: dict | None = None

    def rule(self, path: str | None) -> dict | None:
        if not path:
            return None
        if path not in self._rules:
            self._rules[path] = T.rule_for_path(path, schema=self.schema)
        return self._rules[path]

    def is_open(self, cover: Mapping) -> bool:
        """The cover's question still has an open target in every scope (and field) the call names."""
        from . import questions as Q

        qid, field = cover.get("question_id"), cover.get("field")
        q = Q.question(self.open, qid)
        if q is None:
            if self.filled_cover(cover):
                return True  # 1.18.0: its targets were FILLED by a rule, not answered: the scientist's answer is recorded
            # C1: a sample question leaves the open list once only one of its electrodes is open; its answer still
            # records on the ones still open (decide --question: never on one answered on its own question)
            return self.sample_question(qid) and any(Q.question(self.open, m) is not None
                                                     for m in cover.get("questions") or () if m != qid)
        if q["kind"] == "condition_label":  # its targets are the runs still proposed a label
            return bool(q.get("proposals"))
        return all(bool(Q.targets_for(self.open, qid, sc, field)) for sc in list(cover.get("only_scopes") or ()) or [None])

    def filled_cover(self, cover: Mapping) -> bool:
        """1.18.0 (DEC-96): the cover's question is no longer open only because a registered rule FILLED its targets
        (no scientist answered them): in every scope (and field) the call names, EVERY target is filled. Such an answer
        is a correction of the fill, never "no longer asked", and ``decide --question`` records it (it wins). When any
        target was answered by a scientist since (the question is not open, so none is open), the card is not this:
        ``decide --question`` would write over that newer answer, so it is reported as answered since, as before."""
        from . import questions as Q

        if self._answered is None:
            self._answered = Q.consolidate(self.bundle, include_answered=True, explain_counter=False)
        qid, field = cover.get("question_id"), cover.get("field")
        if Q.question(self._answered, qid) is None:
            return False
        for sc in list(cover.get("only_scopes") or ()) or [None]:
            ids = Q.targets_for(self._answered, qid, sc, field)
            if not ids or len(Q.filled_targets(self.bundle, ids)) != len(ids):
                return False
        return True

    def sample_question(self, qid: str | None) -> bool:
        """Whether ``qid`` is a sample question (C1: ``sample_family``), open or answered."""
        from . import questions as Q

        if self._answered is None:
            self._answered = Q.consolidate(self.bundle, include_answered=True, explain_counter=False)
        return bool((Q.question(self._answered, qid) or {}).get("sample_family"))

    def request_kept(self, plan: Mapping, cover: Mapping, by: str, note: str) -> bool:
        """A vocabulary request this very answer already left: the same word, by the same name, with the same note."""
        return any(r.get("term") == plan.get("value") and (r.get("requested_by") or {}).get("name") == by
                   and r.get("note") == note for r in self.bundle.get("vocabulary_requests") or ())

    def applied_before(self, by: str, note: str) -> bool:
        """A decision this very answer left on an earlier import: the same name, and the card-and-time note in its
        note (a label's decision wraps the note it was given in its own)."""
        return any(note in str(d.get("note") or "") and (d.get("decided_by") or {}).get("name") == by
                   for d in self.bundle.get("scientist_decisions") or ())

    def answered_target(self, target: Mapping) -> Mapping | None:
        """The latest scientist decision that already answers what a target card asks (same family), or ``None``."""
        fam = next((f for f in _TARGET_FAMILIES if target.get("decision") in f), frozenset({target.get("decision")}))
        for d in reversed(self.bundle.get("scientist_decisions") or ()):
            if (d.get("target") or {}).get("id") == target.get("target") and d.get("decision") in fam:
                return d
        return None


def _plans(entry: Mapping, card: Mapping, ctx: _Ctx) -> tuple[list[dict], str | None, str | None]:
    """``(plans, refused, nothing)``: the decide calls one answer stands for; or why it is refused; or why it records
    nothing though nothing is wrong (a "no", an "I don't know" on a card that takes none)."""
    action, raw = entry.get("action"), entry.get("value")
    path = (card.get("field") or {}).get("path")
    kind = (card.get("answer") or {}).get("kind")
    plans: list[dict] = []
    for cover in card.get("covers") or ():
        if action == "accept":
            shown = card.get("suggestion")
            if not shown:
                return [], "this card shows no suggestion to accept: pick or type the value itself", None
            if not _same_value(path, shown.get("value"), raw):
                return [], (f"the suggestion on this card is now {shown.get('value')!r}, not the {raw!r} that was "
                            "accepted: ask again"), None
            act = cover.get("on_accept")
            if not act:
                return [], "this card's suggestion cannot be accepted as it stands: pick or type the value itself", None
            plan = S.cover_call(cover, act, act.get("value"))
            if act.get("from_earlier_answer"):
                plan["from_earlier_answer"] = act["from_earlier_answer"]
        elif action == "dont_know":
            act = cover.get("on_dont_know")
            if not act:
                return [], None, "nothing is recorded for \"I don't know\" on this card: it stays open"
            plan = S.cover_call(cover, act)
        elif kind == "yes_no":
            said = _yes_no(raw)
            if said is None:
                return [], f"{raw!r} is neither yes nor no", None
            act = cover.get("on_yes") if said else cover.get("on_no")
            if not act:
                return [], None, ("a \"no\" records nothing: read the note and settle it with the scientist" if not said
                                  else "a \"yes\" records nothing on this card")
            plan = S.cover_call(cover, act)
        else:
            act = cover.get("on_value")
            if not act:
                return [], "this card takes no value", None
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                return [], "no value was given", None
            if cover.get("target"):
                value, as_said = (raw.strip() if isinstance(raw, str) else raw), False
            else:
                rule = ctx.rule(cover.get("field") or path)
                if rule and not rule.get("numeric") and isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    return [], "this field takes text, not a number", None
                value, why = (T._parse_for(raw, {**rule, "allowed": None}, cover.get("field") or path) if rule
                              else (raw.strip() if isinstance(raw, str) else raw, None))
                if why or value is None:
                    return [], f"not a value this field takes ({why or 'empty'})", None
                # only the scientist's OWN typed word is kept as a vocabulary request when it is off the list
                as_said = bool(entry.get("typed")) and isinstance(value, str) and bool(rule and rule.get("allowed"))
            plan = S.cover_call(cover, act, value, as_said=as_said)
        plan["_cover"] = cover
        plans.append(plan)
    return plans, None, None


def _command(plan: Mapping, ctx: _Ctx, by: str, note: str) -> str:
    shown = {**{k: v for k, v in plan.items() if not k.startswith("_")}, "note": note,
             "target_ids": plan.get("target_ids") or (), "question_id": plan.get("question_id")}
    return W.decide_command(ctx.bundle_arg, shown, by=by)


def _outcome(plan: Mapping, bundle_dir: Path, *, by: str, note: str, dry_run: bool) -> dict:
    """One call through the decide path, as ``workbook_answers._outcome`` reports one."""
    from . import mutations as M
    from . import records as R

    try:
        with contextlib.redirect_stderr(io.StringIO()) if dry_run else contextlib.nullcontext():
            result = S.run_call(plan, bundle_dir, by=by, note=note, dry_run=dry_run)
    except M.OffListRefused as exc:
        if exc.kept is not None:
            return {"outcome": "vocabulary_request_kept" if exc.kept.get("new") else "already_recorded",
                    "request_id": exc.kept.get("request_id"), "statement": exc.kept_statement()}
        if dry_run and plan.get("as_said"):
            return {"outcome": "would_keep_vocabulary_request",
                    "statement": (f"{exc.problem.strip()} --apply keeps it as a vocabulary request in {by}'s name, as "
                                  "`decide --as-said` does (no decision, no value; nothing new if it is kept already)")}
        return {"outcome": "refused", "reason": str(exc)}
    except (M.MutationRefused, R.RecordsRefused) as exc:
        return {"outcome": "refused", "reason": str(exc), "code": getattr(exc, "code", None)}
    n = S._recorded(result)
    return {"outcome": ("would_record" if dry_run else "recorded") if n else "already_recorded", "targets": n,
            "statement": result.get("statement")}


def _judge(plan: Mapping, ctx: _Ctx, tmp: Path, *, by: str, note: str) -> dict:
    """What recording ``plan`` would do now, on the unchanged bundle: ``would_record``, ``already_recorded``,
    ``would_keep_vocabulary_request``, ``refused`` (the decide path's own reason) or ``no_longer_asked``."""
    cover = plan["_cover"]
    target = cover.get("target")
    if target:
        got = _outcome(plan, tmp, by=by, note=note, dry_run=True)
        prior = ctx.answered_target(target)
        if got["outcome"] == "would_record" and prior is not None:
            return {"outcome": "no_longer_asked", "reason": (
                f"answered since by {(prior.get('decided_by') or {}).get('name')} on {prior.get('decided_utc')} "
                f"({prior.get('decision')}{' ' + repr(prior.get('value')) if prior.get('value') is not None else ''})")}
        if got["outcome"] == "refused" and got.get("code") == S.EXIT_NOT_FOUND:
            return {"outcome": "no_longer_asked", "reason": "the bundle no longer holds what this card asked about"}
        return got
    if ctx.is_open(cover):
        got = _outcome(plan, tmp, by=by, note=note, dry_run=True)
        if got["outcome"] == "would_keep_vocabulary_request" and ctx.request_kept(plan, cover, by, note):
            # the same word, kept for the same card under the same name: a second run keeps (and writes) nothing
            return {"outcome": "already_recorded", "statement": "This word is already kept as a vocabulary request."}
        return got
    # answered since (or gone): the same answer again records nothing; another answer is never put over it here
    if ctx.applied_before(by, note):
        return {"outcome": "already_recorded", "statement": "This answer was recorded by an earlier import."}
    alone = {**plan, "same_reading": False}
    got = _outcome(alone, tmp, by=by, note=note, dry_run=True)
    if got["outcome"] == "already_recorded":
        return got
    if got["outcome"] == "would_record" or (got["outcome"] == "refused" and ctx.sample_question(cover.get("question_id"))):
        # (C1: a sample question whose electrodes are all answered on their own questions refuses to change them)
        return {"outcome": "no_longer_asked", "reason": "it was answered since with another answer, which is kept"}
    return {"outcome": "no_longer_asked", "reason": "the bundle no longer asks it (export the site again)"}


HELD_REASON = ("held: the note may name exceptions. This card's answer covers {n} measurements; read the note, then "
               "record the answers yourself, or pass --note-read {card_id} to apply the answer as it was given")


def import_answers(bundle_dir: Path, answers: Path, *, site_data: Path, apply: bool = False, remember: bool = False,
                   bundle_arg: str | None = None, notes_read: Sequence[str] = ()) -> dict:
    """Read a question site's ``answers.json`` against one bundle. Preview (default) writes nothing."""
    from . import answer_memory as AM
    from . import mutations as M

    bundle_dir = Path(bundle_dir).expanduser()
    if apply and (part := W.protected_part(bundle_dir)):
        raise S.SiteRefused(
            f"--apply refuses a bundle inside {part!r}: folders named _runs… hold the protected real bundles. Copy "
            "the bundle folder (cp -R), apply to the copy, show the scientist what it recorded, and apply to a real "
            "bundle only on their word, from a folder not named _runs…. Nothing was recorded.",
            code=S.EXIT_OUTPUT_REFUSED)
    site = _read(site_data, "a question site's site-data.json", S.FORMAT_ID)
    given = _read(answers, "a question site's answers.json", ANSWERS_FORMAT_ID)
    if not B.bundle_path(bundle_dir).is_file():
        raise S.SiteRefused(f"No bundle.json in {bundle_dir.name!r}.", code=S.EXIT_NOT_FOUND)
    try:
        bundle = M.load(bundle_dir)
    except M.MutationRefused as exc:
        raise S.SiteRefused(str(exc), code=exc.code) from exc
    ids = {"the answers file": given.get("bundle_id"), "site-data.json": site.get("bundle_id"),
           "the bundle": bundle.get("bundle_id")}
    if len(set(ids.values())) != 1:
        raise S.SiteRefused("These are not one bundle's: " + ", ".join(f"{k} is for {v!r}" for k, v in ids.items())
                            + ". Nothing was recorded.", code=S.EXIT_INPUT_REFUSED)
    entries = given.get("answers")
    if not isinstance(entries, list):
        raise S.SiteRefused("The answers file has no `answers` list. Nothing was recorded.", code=S.EXIT_INPUT_REFUSED)
    cards = {c.get("card_id"): c for c in site.get("cards") or () if isinstance(c, Mapping)}
    changed_since = site.get("bundle_version") != M.bundle_version(bundle_dir)
    ctx = _Ctx(bundle, bundle_arg or str(bundle_dir))

    # one answer per card: the latest by its own time, the others named
    latest: dict[Any, Mapping] = {}
    rows: list[dict] = []
    for n, e in enumerate(entries):
        if not isinstance(e, Mapping):
            rows.append({"entry": n, "card_id": None, "outcome": "refused", "reason": "not an answer object"})
            continue
        key = e.get("card_id")
        older = e if key in latest and str(e.get("at") or "") < str(latest[key].get("at") or "") else latest.get(key)
        if older is not None:
            rows.append({"entry": n if older is e else older["_n"], "card_id": key, "outcome": "superseded",
                         "title": (cards.get(key) or {}).get("title"), "action": older.get("action"),
                         "value": older.get("value"), "typed": bool(older.get("typed")), "by": older.get("by"),
                         "at": older.get("at"), "reason": "a later answer to the same card is in the file"})
        if older is not e:
            latest[key] = {**e, "_n": n}

    notes: list[dict] = []
    work: list[dict] = []
    for e in sorted(latest.values(), key=lambda x: x["_n"]):
        card = cards.get(e.get("card_id"))
        row = {"entry": e["_n"], "card_id": e.get("card_id"), "title": (card or {}).get("title"),
               "action": e.get("action"), "value": e.get("value"), "typed": bool(e.get("typed")),
               "by": e.get("by"), "at": e.get("at")}
        rows.append(row)
        if isinstance(e.get("note"), str) and e["note"].strip():
            notes.append({"card_id": e.get("card_id"), "title": row["title"], "by": e.get("by"), "at": e.get("at"),
                          "note": e["note"].strip(), "applies_to": ((card or {}).get("applies_to") or {}).get("summary")})
            row["note"] = e["note"].strip()
        if card is None:
            row.update(outcome="refused", reason="not a card of this site-data.json")
            continue
        if e.get("action") not in ACTIONS:
            row.update(outcome="refused", reason=f"its action is not one of {', '.join(ACTIONS)}")
            continue
        by = f"{str(e.get('by') or '').strip()}{BY_SUFFIX}"
        problem = B.decider_name_problem(e.get("by")) or B.decider_name_problem(by)
        if problem:
            row.update(outcome="refused", reason=f"the answer names no person to record it under (it {problem})")
            continue
        reach = int((card.get("applies_to") or {}).get("count") or 0)
        if row.get("note") and reach > 1 and card["card_id"] not in set(notes_read):
            row.update(outcome="held", reason=HELD_REASON.format(n=reach, card_id=card["card_id"]))
            continue
        plans, refused, nothing = _plans(e, card, ctx)
        if refused:
            row.update(outcome="refused", reason=refused)
            continue
        if nothing:
            row.update(outcome="nothing_to_record", reason=nothing)
            continue
        note = decision_note(card, e.get("at"))
        for p in plans:
            if p.get("from_earlier_answer"):
                try:
                    p["_note"] = AM.provenance_note(p["from_earlier_answer"], decision=p["decision"], value=p.get("value"),
                                                    field=(card.get("field") or {}).get("path"), note=note)
                except AM.MemoryRefused:
                    p["_note"] = note
            else:
                p["_note"] = note
            p["command"] = _command(p, ctx, by, p["_note"])
        row.update(recorded_by=by, decision_note=note, _plans=plans)
        work.append(row)

    if work:
        with tempfile.TemporaryDirectory(prefix="isaac-site-") as tmp:
            shutil.copy2(B.bundle_path(bundle_dir), Path(tmp) / B.BUNDLE_FILE)
            for row in work:
                for p in row["_plans"]:
                    p.update(_judge(p, ctx, Path(tmp), by=row["recorded_by"], note=p["_note"]))
    before = AM.snapshot(bundle_dir) if apply and remember else None
    if apply:
        for row in work:
            for p in row["_plans"]:
                if p["outcome"] in ("would_record", "would_keep_vocabulary_request"):
                    p.update(_outcome(p, bundle_dir, by=row["recorded_by"], note=p["_note"], dry_run=False))
    for row in work:
        plans = row.pop("_plans")
        got = [p["outcome"] for p in plans]
        order = ("refused", "no_longer_asked", "recorded", "would_record", "vocabulary_request_kept",
                 "would_keep_vocabulary_request", "already_recorded")
        row["outcome"] = next(o for o in order if o in got)
        row["decisions"] = [{"command": p["command"], "outcome": p["outcome"],
                             **{k: p[k] for k in ("statement", "reason", "targets", "request_id") if p.get(k) is not None}}
                            for p in plans]
        row["reason"] = next((p.get("reason") for p in plans if p.get("reason")), None)
    rows.sort(key=lambda r: r["entry"])

    learned = None
    if remember:
        if not apply:
            learned = {"remembered": None, "statement": "Preview: nothing is remembered. With --apply, --remember "
                                                         "keeps the recorded answers in the answer memory when it is on."}
        elif before is None:
            learned = {"remembered": None, "statement": (
                "The answer memory is off, so nothing was remembered. The scientist turns it on themselves "
                "(`isaac answer-memory on --by \"<their name>\"`); it is never turned on for them.")}
        else:
            learned = AM.after_write(bundle_dir, before) or {
                "remembered": 0, "statement": "Nothing new to remember: this import recorded no new answer."}

    outcomes: dict[str, int] = {}
    for r in rows:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    done = outcomes.get("recorded", 0) + outcomes.get("vocabulary_request_kept", 0)
    planned = outcomes.get("would_record", 0) + outcomes.get("would_keep_vocabulary_request", 0)
    rest = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(outcomes.items())
                     if k not in ("recorded", "would_record")) or "none"
    if not entries:
        statement = "Nothing to apply: the answers file holds no answer."
    elif apply:
        statement = (f"Recorded {outcomes.get('recorded', 0)} answer(s) of {len(rows)} (the rest: {rest}). "
                     f"{len(notes)} note(s) to read.")
    else:
        statement = (f"Preview, nothing written: {outcomes.get('would_record', 0)} answer(s) would be recorded of "
                     f"{len(rows)} (the rest: {rest}). {len(notes)} note(s) to read. Add --apply to record (a copy first).")
    version_now = M.bundle_version(bundle_dir)
    return {
        "format": FORMAT_ID, "format_version": FORMAT_VERSION, "applied": apply, "answers_file": Path(answers).name,
        "site_data": Path(site_data).name, "bundle_id": bundle.get("bundle_id"), "title": site.get("title"),
        "bundle_changed_since_export": changed_since, "bundle_version": version_now,
        "statement": statement, "counts": {"answers": len(rows), **dict(sorted(outcomes.items())),
                                           "changed_the_bundle": done if apply else 0, "would_change_the_bundle": planned,
                                           "notes": len(notes), "log_entries": len(given.get("log") or ())},
        "answers": rows, "notes": notes, **({"answer_memory": learned} if learned is not None else {}),
    }


_HEADINGS = (
    ("recorded", "Applied"), ("would_record", "Would be applied"),
    ("vocabulary_request_kept", "Kept as a vocabulary request (the scientist's own word; no value recorded)"),
    ("would_keep_vocabulary_request", "Would be kept as a vocabulary request (the scientist's own word)"),
    ("already_recorded", "Already recorded (nothing new)"), ("refused", "Refused"),
    ("no_longer_asked", "Cards no longer asked (not applied)"),
    ("held", "Held: the note may name exceptions (not applied)"),
    ("nothing_to_record", "Nothing to record"), ("superseded", "Earlier answers to a card answered again"),
)


def _answer_said(r: Mapping) -> str:
    action, value = r.get("action"), r.get("value")
    if action == "value" and isinstance(value, bool):
        return "said yes" if value else "said no"
    return ("I don't know" if action == "dont_know" else f"accepted {value!r}" if action == "accept"
            else f"{'typed' if r.get('typed') else 'picked'} {value!r}")


def render_report(rep: Mapping) -> str:
    out = [f"Question site answers: {rep['answers_file']} -> bundle {rep.get('title') or rep['bundle_id']} "
           f"({'APPLIED' if rep['applied'] else 'preview: nothing written'})", rep["statement"]]
    for key, heading in _HEADINGS:
        mine = [r for r in rep["answers"] if r["outcome"] == key]
        if not mine:
            continue
        out += ["", f"{heading} ({len(mine)}):"]
        for r in mine:
            who = f" by {r['recorded_by']}" if r.get("recorded_by") else ""
            out.append(f"  {r.get('card_id')} \"{W._clip(r.get('title') or '', 90)}\": {_answer_said(r)}{who}")
            if r.get("reason"):
                out.append(f"      {W._clip(r['reason'], 400)}")
            decisions = list(r.get("decisions") or ())
            for d in decisions[:3]:
                out.append(f"      {d['command']}")
                if d.get("statement"):
                    out.append(f"      -> {W._clip(d['statement'], 300)}")
            if len(decisions) > 3:  # a card answered question by question: the same answer through each call
                out.append(f"      … and {len(decisions) - 3} more call(s) with the same answer (--json lists each)")
    if rep["notes"]:
        out += ["", f"Notes to read ({len(rep['notes'])}); none is turned into a decision:"]
        out += [f"  {n.get('card_id')} \"{W._clip(n.get('title') or '', 70)}\" ({n.get('by')}, {n.get('at')}): {n['note']}"
                for n in rep["notes"]]
    if rep.get("answer_memory"):
        out += ["", rep["answer_memory"]["statement"]]
    return "\n".join(out)
