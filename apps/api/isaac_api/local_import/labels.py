"""Condition labels: the record fields that tell apart records ISAAC keeps apart by condition. Stdlib only.

WHY
===

Grouping splits runs into records by the conditions their files state (``grouping.CONDITION_KEYS``): the
electrode, the filter, the cycling history. Before this module no record field carried them, so records of one
material at one potential exported with the same body and looked like duplicates on the portal. This module
PROPOSES five labels from the readings the grouping already used, and a scientist decides each one. Nothing is
written without a scientist decision. No schema changes:

* ``sample.sample_id`` — the schema: "Stable identifier of the PHYSICAL sample/electrode. Two records share a
  sample_id iff they measured the same physical object." Proposed from the file-name number that names the
  electrode, one id per electrode. WHICH number that is, is never assumed: it is the number the grouping takes as
  the electrode or sample-instance number (``sample_or_electrode_number``) where the files settle it (each such
  number is read beside one sample name), and otherwise the position a scientist gives in answer to ONE
  beamtime-level question (:data:`ELECTRODE_QUESTION_ID`, "which file-name number is the electrode?"). A
  ``set_counter_positions`` answer rules a position out; a ``set_not_counter_positions`` answer is shown as
  evidence, never read as "is the electrode". Not proposed when one number is read beside two sample names, or the
  group's files disagree (the not_proposed row then gives each reading and its file).
* ``system.configuration.beam_attenuator`` — the schema's open namespace for beamline settings, under the key the
  portal's pinned vocabulary lists for it (its allowed flat keys name ``beam_attenuator`` and no ``filter``). The
  value is ``filter<n>``: the filter count the stored rules read (``bl15.filenames.filter_count.v1``: ``filter10``,
  ``f10`` and ``Filter10`` state filter 10; the scan header's ``filter`` motor states the same number), written in
  the file names' own form. ``filter0`` is a count of 0: no filter. Proposed only where every reading agrees.
* ``context.electrochemistry.notes`` — the cycling or pretreatment history, a short sentence. Not
  ``sample.material.provenance``: the portal's pinned vocabulary makes that a closed list ("Origin of the
  material": commercial, synthesized, fabricated, ...), so a sentence there is refused. Not
  ``sample.material.notes``: that is about the material, which is the same before and after cycling. The history
  is the electrochemical treatment the electrode had before this measurement, and the grouping already classes it
  as an electrochemical condition beside the potential, so it goes with the record's other electrochemical
  conditions. The proposal only splits the file-name token into words (``after1500Cycling`` -> "after 1500
  cycling"). It never says what the number is (millivolts or cycles): that is a domain question
  (docs/bl15-2-domain-questions-2026-09-16.md), so the scientist words it.
* ``links`` with rel ``follows``, basis ``same_sample_id`` — "after 1200" follows "before" and "after 1500"
  follows "after 1200", for one sample under otherwise equal conditions. The sample is the one the scientist
  confirmed (its ``sample.sample_id`` answer), else the electrode ISAAC proposes an id for. A stage is the
  scientist's own history answer where there is one, else the file-name token. The order comes from the run
  numbers, or, where those overlap or are missing, the file-creation instants the files state (SPEC ``#E``). A
  link needs its target's record id, which the export mints. So a decision records which RUN a group follows, and
  the export resolves it to that run's record id, exporting the earlier record first (:func:`order_by_follows`).
  The id is part of the later record's body: when the earlier record gets a new id, the later one does too. A link
  is written only when both records carry the same ``sample.sample_id``. Every chain ISAAC could not order is
  listed with its reason.
* ``tags`` — one lowercase hyphenated tag per beamtime, proposed from the folder name.

A scientist's answer to a disagreement on one of these readings (a ``resolve_conflict`` question on the filter,
the cycling token or the electrode number) settles that reading here: the label is then proposed from it, with the
decision as its evidence (:func:`feed_from_conflicts` records it the same way the scientist's earlier label answers
were given).

HOW AN ANSWER IS KEPT
=====================

As a per-run ``missing_values`` entry, a LABEL SLOT (:func:`is_label_slot`), with a ``confirm``, ``correct`` or
``reject`` decision on it (the tag and the electrode position: one beamtime-level slot each). Only bundle sections
and decision kinds that already exist are used, so the bundle format is unchanged. A label slot's eligibility is
derived here (:func:`slot_eligibility`): a scientist-confirmed value its label can hold. The writable set of every
other candidate and missing value is unchanged, so no stored eligibility moves. The electrode position is never a
record field (:func:`take_from_fields` drops it).

The questions (kind :data:`KIND`, scope ``experiment``) are new and never replace one: every existing question
keeps its id, kind, scope and targets.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from . import bundle as B

KIND = "condition_label"
RULE_ID = "isaac.labels.condition_labels.v1"

SAMPLE_ID_PATH = "sample.sample_id"
FILTER_PATH = "system.configuration.beam_attenuator"
HISTORY_PATH = "context.electrochemistry.notes"
#: A label slot at this path holds a proposed ``follows`` link: the run whose record it follows. The export
#: resolves it to that record's id (:func:`follows_link`); it is never a field of the draft.
FOLLOWS_PATH = "links"
TAGS_PATH = "tags"
#: A beamtime-level label slot at this path holds the scientist's answer to "which file-name number is the
#: electrode?": a 1-based token position. It is never a record field (:func:`take_from_fields` drops it).
POSITION_PATH = "electrode_file_name_position"
LABEL_PATHS = (SAMPLE_ID_PATH, FILTER_PATH, HISTORY_PATH, FOLLOWS_PATH, TAGS_PATH, POSITION_PATH)
#: label name -> path
LABELS = {"sample_id": SAMPLE_ID_PATH, "filter": FILTER_PATH, "history": HISTORY_PATH,
          "follows": FOLLOWS_PATH, "tag": TAGS_PATH, "electrode_position": POSITION_PATH}
LABEL_OF_PATH = {v: k for k, v in LABELS.items()}

FOLLOWS_REL, FOLLOWS_BASIS = "follows", "same_sample_id"
#: What each question takes (``decide --question``).
DECISIONS = {"sample_id": ("confirm", "correct", "reject"), "filter": ("confirm", "correct", "reject"),
             "history": ("confirm", "correct", "reject"), "follows": ("confirm", "reject"),
             "tag": ("confirm", "correct", "reject"), "electrode_position": ("correct", "reject")}
#: The partition of a label's RESIDUAL question: the groups ISAAC could not propose a value for, asked on their own
#: once every proposed group holds an answer (its own id: no existing question changes).
RESIDUAL = "not_proposed"
#: The id convention ISAAC proposes: scoped to the beamtime folder, so electrode 02 of another beamtime never
#: shares it. A scientist gives another with ``--decision correct --value``.
SAMPLE_ID_CONVENTION = "{beamtime}:{sample}-{electrode}"
SAMPLE_ID_PLACEHOLDERS = ("beamtime", "sample", "electrode")
FILTER_PLACEHOLDERS = ("filter",)
_PLACEHOLDER = re.compile(r"\{([a-z_]*)\}")
#: The portal's tag rule (schema ``tags.items``): 1..64 characters, no leading or trailing space.
_TAG = re.compile(r"\S(?:.*\S)?")
TAG_MAX = 64
TEXT_MAX = 300
#: ``bl15.filenames.filter_count.v1``: ``filter<n>``, ``f<n>`` and ``Filter<n>`` state filter number n.
_FILTER_NUMBER = re.compile(r"(?:filter|f)?(\d+)", re.IGNORECASE)
_HISTORY = re.compile(r"(?P<side>before|after)(?P<what>.*?)(?P<how>cycling|cycles|cycle|cv)", re.IGNORECASE)
_FILENAME_TOKEN = re.compile(r"filename token (\d+)(?: \[chars (\d+)\.\.(\d+)\])?")
HISTORY_KEYS = ("cycling_state", "before_after_state")
#: The engine reading a ``resolve_conflict`` question is about -> the label it settles (:func:`feed_from_conflicts`).
FEED_KEYS = {"filter": "filter", "cycling_state": "history", "sample_or_electrode_number": "sample_id"}
#: The readings whose disagreement questions point at a label question (``before_after_state`` is the same token).
POINT_KEYS = {**FEED_KEYS, "before_after_state": "history"}
ELECTRODE_KEY = "sample_or_electrode_number"

SLOT_LEAD = "A condition label ISAAC proposed from the files and a scientist answered (question "
SLOT_REASON = SLOT_LEAD + "{question}, rule " + RULE_ID + "): {what}."
_SLOT_QUESTION = re.compile(re.escape(SLOT_LEAD) + r"(Q-[0-9a-f]{10})")

NOT_WRITTEN_FOLLOWS = "Written without its follows link: {why}."
#: How many groups or files a sentence names before it counts the rest (the question's lists hold every one).
NAMED = 12


# --- slots --------------------------------------------------------------------------------------


def is_label_slot(m: Mapping) -> bool:
    """A missing value this module added to hold one run's (or, for the tag and the electrode position, the
    beamtime's) label answer."""
    return m.get("target_field_path") in LABEL_PATHS and str(m.get("reason") or "").startswith(SLOT_LEAD)


def slot_question(m: Mapping) -> str | None:
    hit = _SLOT_QUESTION.match(str(m.get("reason") or "")) if is_label_slot(m) else None
    return hit.group(1) if hit else None


def _as_position(value: Any) -> int | None:
    """A 1-based file-name position given as a whole number (``2``, ``"2"``), or ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    if isinstance(value, float) and value.is_integer() and value >= 1:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) >= 1:
        return int(value.strip())
    return None


def label_value_problem(path: str, value: Any) -> str | None:
    """Why ``value`` cannot be the label at ``path``, or ``None``."""
    if path in (SAMPLE_ID_PATH, HISTORY_PATH):
        if not isinstance(value, str) or not value.strip():
            return f"{path} takes a non-empty text"
        if value != value.strip() or len(value) > TEXT_MAX:
            return f"{path} takes a text of at most {TEXT_MAX} characters with no leading or trailing space"
        return None
    if path == FILTER_PATH:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return f"{path} takes a number or a text"
        if isinstance(value, float) and not math.isfinite(value):
            return f"{path} takes a finite number"
        if isinstance(value, str) and (not value.strip() or value != value.strip() or len(value) > TEXT_MAX):
            return f"{path} takes a non-empty text with no leading or trailing space"
        return None
    if path == TAGS_PATH:
        if not (isinstance(value, list) and len(value) == 1 and isinstance(value[0], str)):
            return "the beamtime tag is one text"
        if not _TAG.fullmatch(value[0]) or len(value[0]) > TAG_MAX:
            return f"a tag is 1 to {TAG_MAX} characters with no leading or trailing space"
        return None
    if path == FOLLOWS_PATH:
        if not (isinstance(value, Mapping) and value.get("rel") == FOLLOWS_REL and value.get("basis") == FOLLOWS_BASIS
                and isinstance(value.get("follows_run_key"), str) and value["follows_run_key"]):
            return "a follows label names the run whose record it follows"
        return None
    if path == POSITION_PATH:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return "the electrode's file-name position is a whole number from 1 (the first token of the name)"
        return None
    return f"{path} is not a condition label"


def slot_eligibility(state: str, m: Mapping, value: Any) -> dict:
    """A label slot's eligibility: :func:`bundle.eligibility_for_official_record`'s rule with this module's write
    route and value check in place of the writable set."""
    if state != B.STATE_SCIENTIST_CONFIRMED or value is None:
        return B.eligibility_for_official_record(state, target_field_path=m.get("target_field_path"), value=value,
                                                 writable_paths=frozenset())
    problem = label_value_problem(m.get("target_field_path"), value)
    if problem is not None:
        return {"eligible": False, "reason": f"{B.UNFIT_REASON_PREFIX}{problem}"}
    return {"eligible": True,
            "reason": ("Confirmed by a scientist: a condition label ISAAC proposed from the files "
                       f"({RULE_ID}). It still becomes official only through a reviewed draft and `isaac export`.")}


def slot_question_text(m: Mapping) -> str:
    return f"Condition label {m.get('target_field_path')} (question {slot_question(m)})"


# --- readings -----------------------------------------------------------------------------------


_ARCHIVE_SUFFIX = re.compile(r"\.(?:zip|tar|tgz|tar\.gz|tar\.bz2|tar\.xz|7z)$", re.IGNORECASE)


def beamtime_label(bundle: Mapping) -> str | None:
    """The beamtime folder's name (an archive's without its ``.zip``/``.tar.gz`` suffix)."""
    for x in ((bundle.get("source_root") or {}).get("label"), (bundle.get("experiment") or {}).get("label")):
        if isinstance(x, str) and x.strip():
            return _ARCHIVE_SUFFIX.sub("", x.strip()) or x.strip()
    return None


def proposed_tag(label: str | None) -> str | None:
    """The folder name, lowercase, every run of other characters one hyphen, at most :data:`TAG_MAX` characters."""
    if not label:
        return None
    tag = re.sub(r"[^0-9a-z]+", "-", label.casefold()).strip("-")
    if len(tag) > TAG_MAX:
        cut = tag[:TAG_MAX]
        tag = cut.rsplit("-", 1)[0] if "-" in cut else cut
    return tag or None


def filter_number(literal: Any) -> int | None:
    if isinstance(literal, bool):
        return None
    if isinstance(literal, int):
        return literal
    if isinstance(literal, float) and literal.is_integer():
        return int(literal)
    m = _FILTER_NUMBER.fullmatch(str(literal or "").strip())
    return int(m.group(1)) if m else None


def history_words(literal: str) -> str | None:
    """The file-name token in words, nothing interpreted: ``after1500Cycling`` -> ``after 1500 cycling``."""
    m = _HISTORY.fullmatch(str(literal or "").strip())
    if not m:
        return None
    what = m.group("what").strip("_- ")
    how = {"cv": "CV", "cycles": "cycles", "cycle": "cycle"}.get(m.group("how").casefold(), "cycling")
    return " ".join(x for x in (m.group("side").casefold(), what, how) if x)


def _own_name(e: Mapping, stem: str) -> bool:
    return (str(e.get("locator") or "").startswith("filename token")
            and PurePosixPath(str(e.get("relative_path") or "")).name == stem)


def _part(g: Mapping, category: str) -> Mapping:
    """One category of a group's basis, or ``{}`` (a hand-made basis may hold anything)."""
    basis = g.get("basis")
    part = basis.get(category) if isinstance(basis, Mapping) else None
    return part if isinstance(part, Mapping) else {}


def _basis(g: Mapping, category: str, key: str) -> Mapping | None:
    r = _part(g, category).get(key)
    return r if isinstance(r, Mapping) and r.get("kind") != "conflicting" else None


def _values(r: Mapping | None) -> list:
    if r is None:
        return []
    v = r.get("value")
    return list(v) if isinstance(v, list) else [v]


def _grouping_position(stem: str, locator_index: int, char_start: int | None) -> int:
    """The 1-based position grouping gives the token at ``char_start`` (``grouping._stem_tokens``: the positions a
    ``set_counter_positions`` answer names). The engine's own token index is the fallback."""
    from . import grouping as G

    if char_start is None:
        return locator_index + 1
    marked = G._SIGN.sub("\x00", str(stem))  # one character for one: offsets unchanged
    for n, m in enumerate(re.finditer(r"[^_\-\s.]+", marked), start=1):
        if m.start() <= char_start < m.end():
            return n
    return locator_index + 1


def _normalised(g: Mapping, *, drop: Sequence[str] = ()) -> dict:
    """The group's basis as conditions are COMPARED: each reading through ``grouping._comparable``, a filter through
    :func:`filter_number` (``10`` and ``filter10`` state one filter), without ``drop``."""
    from . import grouping as G

    out: dict[str, Any] = {}
    basis = g.get("basis") if isinstance(g.get("basis"), Mapping) else {}
    for category in sorted(basis):
        part = basis.get(category)
        if not isinstance(part, Mapping):
            out[category] = json.dumps(part, sort_keys=True, default=str)
            continue
        for key in sorted(part):
            if key in drop:
                continue
            r = part[key]
            if not isinstance(r, Mapping) or "kind" not in r:
                out[f"{category}.{key}"] = json.dumps(r, sort_keys=True, default=str)
            elif key == "filter" and r.get("kind") != "conflicting" and len(nums := {filter_number(v) for v in _values(r)}) == 1 \
                    and None not in nums:
                out[f"{category}.{key}"] = f"filter:{next(iter(nums))}"
            else:
                out[f"{category}.{key}"] = G._comparable(r)
    return out


def _where(locator: Any) -> str:
    """Where a reading was read, in a few words: ``file name``, ``scan header, scan 10``, or the locator itself."""
    loc = str(locator or "")
    if loc.startswith("filename"):
        return "file name"
    if "header" in loc:
        scan = re.search(r"\(scan (\d+)\)", loc)
        return "scan header" + (f", scan {scan.group(1)}" if scan else "")
    return loc


def readings_text(readings: Sequence[Mapping]) -> str:
    """``15 (SYN_1, scan header, scan 10); 20 (SYN_1, file name)``: each competing reading with its file."""
    return "; ".join(f"{r.get('value')} ({r.get('file')}" + (f", {r['where']}" if r.get("where") else "") + ")"
                     for r in readings)


class _Ctx:
    """What the bundle's decisions say, read once per proposal: the label answers, the electrode position a scientist
    gave, the counter answers, and the scientist's answers to disagreements on the readings a label is proposed from."""

    def __init__(self, bundle: Mapping):
        from . import grouping as G

        self.decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
        self.slots = _slot_index(bundle)
        counter = G.counter_positions_decision(bundle)
        self.counter = counter
        self.cpos = list((counter or {}).get("positions") or ())
        self.exempt = (G.last_counter_exempt(r.get("stem") or "" for r in bundle.get("runs") or ())
                       if G.LAST_POSITION in self.cpos else frozenset())
        self.said_not = B.not_counter_positions(bundle)
        d = _answered(self.slots.get((POSITION_PATH, None)), self.decisions)
        #: ``(position or None for "no number is the electrode", decision)`` or ``None`` while unanswered
        self.position = ((None if d.get("decision") == "reject" else _as_position(d.get("value"))), d) if d else None
        self.conflicts: dict[tuple[str, str], list[Mapping]] = {}
        for cf in bundle.get("conflicts") or ():
            key = str(cf.get("engine_conflict_id") or "").rsplit("::", 1)[-1]
            if key in POINT_KEYS:
                for rid in cf.get("run_ids") or ():
                    self.conflicts.setdefault((rid, key), []).append(cf)

    def answer(self, path: str, rid: Any) -> Mapping | None:
        return _answered(self.slots.get((path, rid)), self.decisions)

    def group_answer(self, path: str, runs: Sequence[str]) -> Any:
        """The one value every run of a group holds a (non-reject) answer for at ``path``, else ``None``."""
        got = set()
        for rid in runs:
            d = self.answer(path, rid)
            if d is None or d.get("decision") == "reject":
                return None
            got.add(json.dumps(d.get("value"), sort_keys=True))
        return json.loads(next(iter(got))) if len(got) == 1 else None

    def counted(self, stem: str) -> set[int]:
        from . import grouping as G

        pos = G.stem_counter_positions(stem, self.cpos, self.exempt)
        out = {p for p in pos if p != G.LAST_POSITION}
        if G.LAST_POSITION in pos:
            out.add(len(G._stem_tokens(stem)))
        return out

    def choice(self, cf: Mapping) -> tuple[Any, Mapping] | None:
        """``(value, decision)`` a scientist chose for disagreement ``cf`` (``confirm``/``correct``), or ``None``."""
        d = self.decisions.get(("conflict", cf.get("conflict_id")))
        if d is None or d.get("decision") not in ("confirm", "correct"):
            return None
        v = d.get("value")
        if v is None and isinstance(d.get("chosen_reading_index"), int):
            rs = cf.get("readings") or ()
            v = rs[d["chosen_reading_index"]].get("value") if 0 <= d["chosen_reading_index"] < len(rs) else None
        return (v, d) if v not in (None, "") else None

    def readings(self, runs: Sequence[str], key: str) -> list[dict]:
        """Each competing reading of ``key`` the disagreements on ``runs`` hold, with its first file."""
        out, seen = [], set()
        for rid in runs:
            for cf in self.conflicts.get((rid, key), ()):
                for r in cf.get("readings") or ():
                    w = next(iter(r.get("witnesses") or ()), None) or {}
                    row = {"value": r.get("value"), "file": w.get("relative_path"), "where": _where(w.get("locator")),
                           "conflict_id": cf.get("conflict_id")}
                    if (row["value"], row["file"]) not in seen:
                        seen.add((row["value"], row["file"]))
                        out.append(row)
        return out


class _Facts:
    """What one live group's basis and runs state, read once."""

    __slots__ = ("gid", "runs", "keys", "electrode", "position", "sample", "names", "names_said", "filter", "filter_said",
                 "filter_from", "history", "history_canon", "why_not", "readings", "decided", "run_interval",
                 "time_interval", "loose_key", "full_key", "stems", "sid", "ident", "stage", "stage_from",
                 "position_unsettled", "set_aside_at")

    def __init__(self, gid: str):
        self.gid = gid
        self.runs: list[str] = []
        self.keys: list[str] = []
        self.stems: list[str] = []
        self.electrode = self.position = self.sample = self.filter = self.history = self.history_canon = None
        self.names: set[str] = set()
        self.names_said: list[str] = []
        self.filter_said: list[str] = []
        self.why_not: dict[str, str] = {}
        self.readings: dict[str, list[dict]] = {}
        self.decided: dict[str, list[str]] = {}  # label -> the conflict decisions that settled its reading
        self.run_interval = self.time_interval = self.loose_key = self.full_key = None
        self.sid = self.ident = self.stage = self.stage_from = None
        self.filter_from: set[str] = set()
        self.position_unsettled = False
        self.set_aside_at: tuple[int, str] | None = None  # the position and token the grouping set aside


def _token_at(stem: str, char_start: int | None, char_end: int | None) -> str | None:
    if char_start is None or char_end is None:
        return None
    tok = str(stem)[char_start:char_end]
    return tok or None


def _settled_by_answers(ctx: _Ctx, f: _Facts, key: str) -> tuple[list[tuple[str, Any, Mapping, Mapping]], bool]:
    """For each run of ``f`` with a disagreement on ``key``, ``(run, value chosen, decision, conflict)``; and whether
    every such disagreement holds a scientist's choice (no run of the group has one: ``([], False)``)."""
    got, every, seen = [], True, False
    for rid in f.runs:
        for cf in ctx.conflicts.get((rid, key), ()):
            seen = True
            ch = ctx.choice(cf)
            if ch is None:
                every = False
            else:
                got.append((rid, ch[0], ch[1], cf))
    return got, (every and seen)


def _facts(bundle: Mapping, groups: Sequence[Mapping], ctx: _Ctx | None = None) -> list[_Facts]:
    from . import grouping as G

    ctx = ctx or _Ctx(bundle)
    runs_by_key = {r["run_key"]: r for r in bundle.get("runs") or ()}
    cands = {c["candidate_id"]: c for c in bundle.get("candidates") or ()}
    context = B.context_run_ids(bundle)
    out: list[_Facts] = []
    for g in groups:
        f = _Facts(g["group_id"])
        own: dict[str, dict[str, list]] = {}
        for k in g.get("member_run_keys") or ():
            run = runs_by_key.get(k)
            if run is None or run["run_id"] in context:
                continue
            f.runs.append(run["run_id"])
            f.keys.append(k)
            f.stems.append(str(run.get("stem") or ""))
            mine = own.setdefault(run["run_id"], {})
            for cid in run.get("candidate_ids") or ():
                c = cands.get(cid)
                if c is not None and c.get("statement_key"):
                    mine.setdefault(c["statement_key"], []).append(c)
        if not f.runs:
            continue
        stem_of = dict(zip(f.runs, f.stems))

        def written(key: str) -> list[str]:
            # the literal each measured run's OWN candidates hold for ``key`` (first observed literal)
            got = []
            for rid in f.runs:
                for c in own.get(rid, {}).get(key, ()):
                    if c.get("observed_literals"):
                        got.append(str(c["observed_literals"][0]))
            return got

        names = {x for x in written("sample_name")}
        f.names = {n.casefold() for n in names}
        f.names_said = sorted(names)
        one_name = sorted(names)[0] if len(f.names) == 1 else None
        _electrode(ctx, f, g, own, stem_of, written, one_name)
        _filter(ctx, f, g, own, written)
        _history(ctx, f, g, own, stem_of)
        # THE STAGE (for follows): the scientist's own history answer, else the file-name token
        typed = ctx.group_answer(HISTORY_PATH, f.runs)
        if isinstance(typed, str):
            f.stage, f.stage_from = typed.casefold(), "answer"
        elif f.history_canon is not None:
            f.stage, f.stage_from = f.history_canon, "file name"
        f.sid = ctx.group_answer(SAMPLE_ID_PATH, f.runs)
        # THE ORDER: run numbers, and the instants the files state (#E): a chain uses the first that orders it
        nums = [runs_by_key[k].get("legacy_number") for k in f.keys]
        if all(isinstance(n, int) and not isinstance(n, bool) for n in nums):
            f.run_interval = (min(nums), max(nums))
        epochs = []
        for rid in f.runs:
            lits = [str(c["observed_literals"][0]) for c in own.get(rid, {}).get("acquisition_epoch", ())
                    if c.get("observed_literals") and c.get("extracted_state") != B.STATE_CONFLICTING]
            epochs.append(int(lits[0]) if len(lits) == 1 and lits[0].isdigit() else None)
        if epochs and None not in epochs:
            f.time_interval = (min(epochs), max(epochs))
        # THE KEYS conditions are compared by (normalised, r review M3): without the history and the electrode
        # (one sample's stages are told apart by its sample id), and in full (repeats of one condition)
        norm = _normalised(g)  # read once; each key leaves out its own readings
        f.full_key = json.dumps(norm, sort_keys=True)
        f.loose_key = json.dumps({k: v for k, v in norm.items() if k.rsplit(".", 1)[-1] not in (*HISTORY_KEYS, ELECTRODE_KEY)},
                                 sort_keys=True)
        out.append(f)
    # THE SAMPLE each group is of, for follows: the id a scientist confirmed for it; else the id its electrode's other
    # groups were given (one id per electrode); else its electrode, read from the files
    given: dict[str, set] = {}
    for f in out:
        if f.electrode is not None and isinstance(f.sid, str):
            given.setdefault(f.electrode.casefold(), set()).add(f.sid)
    for f in out:
        if isinstance(f.sid, str):
            f.ident = ("sid", f.sid)
        elif f.electrode is not None:
            ids = given.get(f.electrode.casefold()) or set()
            f.ident = ("sid", next(iter(ids))) if len(ids) == 1 else ("electrode", f.sample.casefold(), f.electrode.casefold())
    return out


def _electrode(ctx: _Ctx, f: _Facts, g: Mapping, own: Mapping, stem_of: Mapping, written, one_name: str | None) -> None:
    """THE ELECTRODE (sets ``f.electrode/position/sample`` or ``f.why_not['sample_id']``)."""
    from . import grouping as G
    from .questions import _qid

    pos_q = _qid("experiment", KIND, POSITION_PATH)
    el = _basis(g, "sample", ELECTRODE_KEY)
    raw_el = _part(g, "sample").get(ELECTRODE_KEY)
    aside = _part(g, "unclassified").get(ELECTRODE_KEY)
    # where the grouping's reading of the number sits in each run's own name
    positions, tokens = set(), set()
    for rid in f.runs:
        for c in own.get(rid, {}).get(ELECTRODE_KEY, ()):
            for e in c.get("evidence") or ():
                hit = _FILENAME_TOKEN.match(str(e.get("locator") or ""))
                if hit and _own_name(e, stem_of[rid]):
                    start = int(hit.group(2)) if hit.group(2) is not None else None
                    end = int(hit.group(3)) if hit.group(3) is not None else None
                    p = _grouping_position(stem_of[rid], int(hit.group(1)), start)
                    positions.add((rid, p))
                    tok = _token_at(stem_of[rid], start, end)
                    if tok:
                        tokens.add((p, tok))
    counted = sorted({p for rid, p in positions if p in ctx.counted(stem_of[rid])})
    if el is None and isinstance(aside, Mapping):
        f.position_unsettled = True
        if tokens:
            f.set_aside_at = sorted(tokens)[0]
    elif el is not None and counted:
        f.position_unsettled = True
    # A SCIENTIST'S ANSWER to "which file-name number is the electrode?" settles it for every group
    if ctx.position is not None:
        p, d = ctx.position
        if p is None:
            f.why_not["sample_id"] = (f"the scientist said no file-name number is the electrode or sample instance "
                                      f"({d.get('decision_id')}, question {pos_q}): give this group its id")
            return
        at = {rid: (G._stem_tokens(stem_of[rid])[p - 1] if len(G._stem_tokens(stem_of[rid])) >= p else None)
              for rid in f.runs}
        bad = [stem_of[rid] for rid, t in at.items() if t is None or not t.isdigit()]
        if bad:
            f.why_not["sample_id"] = (f"its file name {bad[0]} writes no number at position {p}, the electrode position "
                                      f"the scientist gave ({d.get('decision_id')})")
            return
        if len({t.casefold() for t in at.values()}) > 1:
            f.why_not["sample_id"] = (f"its files write different numbers at position {p}, the electrode position the "
                                      f"scientist gave ({d.get('decision_id')}): "
                                      + "; ".join(f"{t} ({stem_of[rid]})" for rid, t in list(at.items())[:4]))
            return
        if any(p in ctx.counted(stem_of[rid]) for rid in f.runs):
            f.why_not["sample_id"] = (f"position {p} is the electrode by the scientist's answer {d.get('decision_id')} and "
                                      f"a run counter by {(ctx.counter or {}).get('decision_id')}: answer one of them again")
            return
        if one_name is None:
            f.why_not["sample_id"] = "its runs' file names do not state one sample name"
            return
        f.electrode, f.position, f.sample = next(iter(at.values())), p, one_name
        return
    if el is None and isinstance(raw_el, Mapping):
        # THE FILES' ELECTRODE READINGS DISAGREE: settled where a scientist chose one reading of each disagreement
        got, every = _settled_by_answers(ctx, f, ELECTRODE_KEY)
        toks, poss, ids = set(), set(), []
        for rid, value, d, cf in got:
            ids.append(d.get("decision_id"))
            reading = next((r for r in cf.get("readings") or () if str(r.get("value")) == str(value)), None)
            # the chosen reading as this run's own name writes it; a reading of another file (a merge) is taken as
            # chosen, at the same position of the name
            mine = [w for w in (reading or {}).get("witnesses") or () if _own_name(w, stem_of[rid])]
            wit = mine or [w for r in cf.get("readings") or () for w in r.get("witnesses") or () if _own_name(w, stem_of[rid])]
            hit = _FILENAME_TOKEN.match(str((wit[0] if wit else {}).get("locator") or ""))
            if hit is None:
                every = False
                continue
            start = int(hit.group(2)) if hit.group(2) is not None else None
            end = int(hit.group(3)) if hit.group(3) is not None else None
            poss.add(_grouping_position(stem_of[rid], int(hit.group(1)), start))
            toks.add((_token_at(stem_of[rid], start, end) if mine else None) or str(value))
        f.readings["sample_id"] = ctx.readings(f.runs, ELECTRODE_KEY)
        if every and len(toks) == 1 and len(poss) == 1 and one_name is not None and not (poss & set(counted)):
            f.electrode, f.position, f.sample = next(iter(toks)), next(iter(poss)), one_name
            f.decided["sample_id"] = ids
            return
        f.why_not["sample_id"] = "the files' electrode readings disagree" + (
            f": {readings_text(f.readings['sample_id'])}" if f.readings["sample_id"] else "")
        return
    if el is None:
        if isinstance(aside, Mapping):
            p, tok = f.set_aside_at or (None, None)
            f.why_not["sample_id"] = (
                ("the grouping set aside the file-name number at position " + f"{p} (here {tok})" if p else
                 "the grouping set aside the file name's sample number")
                + ": in this beamtime that number is read beside several sample names, so it does not name the electrode "
                f"on its own. Answer question {pos_q} (which file-name number is the electrode), or give this group its "
                "id with --only group:<id> --decision correct --value <id>")
        else:
            f.why_not["sample_id"] = "the file names state no electrode or sample-instance number"
        return
    lits = {x.casefold() for x in written(ELECTRODE_KEY)}
    pos = {p for _, p in positions}
    if len(lits) > 1:
        f.why_not["sample_id"] = "the files' electrode readings disagree"
    elif len(lits) != 1 or len(pos) != 1:
        f.why_not["sample_id"] = "its runs' file names do not state one electrode number at one position"
    elif counted:
        f.why_not["sample_id"] = (f"the number sits at file-name position {counted[0]}, which a set_counter_positions "
                                  f"answer names as a run counter: answer question {pos_q} (which file-name number is "
                                  "the electrode)")
    elif one_name is None:
        f.why_not["sample_id"] = "its runs' file names do not state one sample name"
    else:
        f.electrode = written(ELECTRODE_KEY)[0]
        f.position = next(iter(pos))
        f.sample = one_name


def _filter(ctx: _Ctx, f: _Facts, g: Mapping, own: Mapping, written) -> None:
    """THE FILTER: the number every reading of the group states (bl15.filenames.filter_count.v1, the header motor)."""
    fr = _basis(g, "conditions", "filter")
    raw = _part(g, "conditions").get("filter")
    if fr is None and raw:
        got, every = _settled_by_answers(ctx, f, "filter")
        f.readings["filter"] = ctx.readings(f.runs, "filter") or (
            [{"value": v, "file": f.stems[0], "where": None} for v in (raw.get("readings") or ())]
            if isinstance(raw, Mapping) else [])
        nums = {filter_number(v) for _, v, _, _ in got}
        settled_runs = {rid for rid, *_ in got}
        # a run with no disagreement of its own keeps its own file reading
        for rid in f.runs:
            if rid not in settled_runs:
                nums |= {filter_number(str(c["observed_literals"][0])) for c in own.get(rid, {}).get("filter", ())
                         if c.get("observed_literals") and c.get("extracted_state") != B.STATE_CONFLICTING}
        if every and len(nums) == 1 and None not in nums:
            f.filter = next(iter(nums))
            f.filter_said = sorted({str(v) for _, v, _, _ in got})
            f.filter_from = {"your answer to the disagreement"}
            f.decided["filter"] = [d.get("decision_id") for _, _, d, _ in got]
            return
        f.why_not["filter"] = "the files' filter readings disagree" + (
            f": {readings_text(f.readings['filter'])}" if f.readings["filter"] else "")
        return
    if fr is None:
        f.why_not["filter"] = "the files state no filter"
        return
    nums = {filter_number(v) for v in _values(fr)}
    if len(nums) != 1 or None in nums:
        f.why_not["filter"] = "the files' filter readings do not state one number"
        return
    f.filter = next(iter(nums))
    f.filter_said = sorted({x for x in written("filter")})
    for rid in f.runs:
        for c in own.get(rid, {}).get("filter", ()):
            for e in c.get("evidence") or ():
                loc = str(e.get("locator") or "")
                f.filter_from.add("file name" if loc.startswith("filename") else
                                  "scan header" if "header" in loc else "other")


def _as_written(value: Any, names: Sequence[str]) -> str:
    """The token of ``names`` (file names, split as grouping splits them) that ``value`` is, case and all."""
    from . import grouping as G

    want = str(value).casefold()
    for n in names:
        for t in G._stem_tokens(PurePosixPath(str(n)).name):
            if t.casefold() == want:
                return t
    return str(value)


def _history(ctx: _Ctx, f: _Facts, g: Mapping, own: Mapping, stem_of: Mapping) -> None:
    """THE HISTORY: each run's own file-name token, as written."""
    hr = _basis(g, "conditions", "cycling_state")
    raw = _part(g, "conditions").get("cycling_state")
    if hr is None and raw:
        got, every = _settled_by_answers(ctx, f, "cycling_state")
        f.readings["history"] = ctx.readings(f.runs, "cycling_state")
        canon = {str(v).casefold() for _, v, _, _ in got}
        if every and len(canon) == 1:
            files = [stem_of[rid] for rid, *_ in got] + [w.get("relative_path") for *_, cf in got
                                                        for r in cf.get("readings") or () for w in r.get("witnesses") or ()]
            token = _as_written(got[0][1], files)
            if history_words(token) is not None:
                f.history, f.history_canon = token, token.casefold()
                f.decided["history"] = [d.get("decision_id") for _, _, d, _ in got]
                return
        f.why_not["history"] = "the files' cycling readings disagree" + (
            f": {readings_text(f.readings['history'])}" if f.readings["history"] else "")
        return
    if hr is None:
        f.why_not["history"] = "the file names state no cycling history"
        return
    said = []
    for rid in f.runs:
        for c in own.get(rid, {}).get("cycling_state", ()):
            said += [str(e.get("literal_value")) for e in c.get("evidence") or ()
                     if _own_name(e, stem_of[rid]) and e.get("literal_value")]
    canon = {s.casefold() for s in said}
    if len(canon) != 1:
        f.why_not["history"] = "its runs' file names do not write one cycling token"
    elif history_words(said[0]) is None:
        f.why_not["history"] = f"the file-name token {said[0]!r} is not a before/after cycling token"
    else:
        f.history, f.history_canon = said[0], next(iter(canon))


def _order(members: Sequence[_Facts]) -> tuple[list[_Facts] | None, str | None]:
    """``(members in time order, basis)``: by run numbers when they order every member, else by the file-creation
    instants; ``(None, reason)`` when neither does."""
    for basis, attr in (("run_numbers", "run_interval"), ("start_times", "time_interval")):
        ivs = [getattr(m, attr) for m in members]
        if None in ivs:
            continue
        ordered = sorted(members, key=lambda m: getattr(m, attr))
        if all(getattr(a, attr)[1] < getattr(b, attr)[0] for a, b in zip(ordered, ordered[1:])):
            return ordered, basis
    return None, None


def _interval(f: _Facts, basis: str | None) -> tuple | None:
    return f.run_interval if basis == "run_numbers" else f.time_interval if basis == "start_times" else None


def _chains(facts: Sequence[_Facts]) -> tuple[list[list[_Facts]], list[dict]]:
    """Groups of one sample under otherwise equal conditions, at different history stages, in time order; and every
    such set ISAAC could not order, with its reason (``held``: none is skipped without one)."""
    by_key: dict[str, list[_Facts]] = {}
    for f in facts:
        if f.ident is not None:
            by_key.setdefault(json.dumps([f.ident, f.loose_key]), []).append(f)
    chains, held = [], []

    def hold(members: Sequence[_Facts], reason: str) -> None:
        held.append({"group_ids": [m.gid for m in members], "first_files": [m.stems[0] for m in members],
                     "run_ids": [], "reason": reason})

    for members in by_key.values():
        if len(members) < 2:
            continue
        unstaged = [m for m in members if m.stage is None]
        if len(unstaged) == len(members) and all(m.why_not.get("history") == "the file names state no cycling history"
                                                for m in members):
            continue  # no history anywhere: repeats of one condition, not stages of one sample
        if unstaged:
            hold(members, "; ".join(f"{m.stems[0]} has no settled history stage ({m.why_not.get('history')})"
                                    for m in unstaged)
                 + ", so the order of stages is not certain. Settle its history (its history question, or the "
                 "disagreement on its file) and the chain is proposed")
            continue
        stages: dict[str, list[_Facts]] = {}
        for m in members:
            stages.setdefault(m.stage, []).append(m)
        same = [ms for ms in stages.values() if len(ms) > 1]
        if same:
            hold(members, "two of these groups are at the same history stage ("
                 + "; ".join(" and ".join(m.stems[0] for m in ms) for ms in same) + ")")
            continue
        ordered, basis = _order(members)
        if ordered is None:
            no_time = [m.stems[0] for m in members if m.time_interval is None]
            hold(members, ("their run numbers " + ("overlap" if all(m.run_interval for m in members) else "are missing")
                           + (", and " + ", ".join(no_time) + " state(s) no one file-creation instant (#E missing, or "
                              "its start-time readings disagree)" if no_time else
                              ", and their file-creation instants overlap")
                           + ", so ISAAC cannot put them in one order"))
            continue
        sides = [m.stage.startswith("before") for m in ordered]
        if any(not a and b for a, b in zip(sides, sides[1:])):
            hold(members, "a 'before' measurement comes after an 'after' one in time")
            continue
        # r review M3: a group of these conditions whose sample is not settled, measured between them, may be the stage
        # in between
        lo, hi = _interval(ordered[0], basis)[0], _interval(ordered[-1], basis)[1]
        gap = [f for f in facts if f.ident is None and f.loose_key == members[0].loose_key
               and (iv := _interval(f, basis)) is not None and lo < iv[0] < hi]
        if gap:
            hold(members, f"{gap[0].stems[0]} has these conditions but no settled sample (electrode or sample id) and was "
                 "measured between them, so the order of stages is not certain")
            continue
        chains.append((ordered, basis))
    chains.sort(key=lambda c: _interval(c[0][0], c[1]))
    return [c for c, _ in chains], held


# --- proposals and questions --------------------------------------------------------------------


def _qid(*parts: str) -> str:
    from . import questions as Q

    return Q._qid("experiment", KIND, *parts)


def question_id(label: str, partition: str | None = None) -> str:
    return _qid(LABELS[label], *([partition] if partition else []))


#: The beamtime-level question "which file-name number is the electrode / physical sample?" (a new id).
ELECTRODE_QUESTION_ID = question_id("electrode_position")


def _fill_sample_id(pattern: str, fill: Mapping[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: str(fill[m.group(1)]), pattern)


def _held(f: _Facts, reason: str | None, label: str | None = None) -> dict:
    row = {"group_id": f.gid, "run_ids": list(f.runs), "first_file": f.stems[0], "reason": reason}
    if label and f.readings.get(label):
        row["readings"] = [dict(r) for r in f.readings[label]]
    return row


def _position_proposal(facts: Sequence[_Facts], ctx: _Ctx) -> dict | None:
    """The groups whose electrode the files do not settle (the grouping set the sample number aside, or a counter
    answer names its position), and each file-name position that could hold their electrode number, with evidence."""
    from . import grouping as G

    unsettled = [f for f in facts if f.position_unsettled]
    if not unsettled:
        return None
    cand: dict[int, dict] = {}
    by_number: dict[int, dict[str, set]] = {}
    ruled_out: set[int] = set()
    for f in unsettled:
        for stem in f.stems:
            counted = ctx.counted(stem)
            ruled_out |= counted
            for i, t in enumerate(G._stem_tokens(stem), start=1):
                if not t.isdigit() or i in counted:
                    continue
                c = cand.setdefault(i, {"position": i, "examples": []})
                if len(c["examples"]) < 3 and all(e["number"].casefold() != t.casefold() for e in c["examples"]):
                    c["examples"].append({"number": t, "file": stem})
                by_number.setdefault(i, {}).setdefault(t.casefold(), set()).update(f.names)
    rows = []
    for p in sorted(cand):
        nbn = by_number[p]
        c = {**cand[p], "numbers": len(nbn), "numbers_beside_several_sample_names": sum(1 for v in nbn.values() if len(v) > 1)}
        if p in ctx.said_not:
            c["said_not_a_counter"] = ctx.said_not[p].get("decision_id")
        rows.append(c)
    return {"label": "electrode_position", "partition": None, "items": [], "candidates": rows,
            "ruled_out": sorted(ruled_out), "groups": [f.gid for f in unsettled],
            "runs": [r for f in unsettled for r in f.runs], "first_files": [f.stems[0] for f in unsettled],
            "not_proposed": [], "answer": ctx.position}


def proposals(bundle: Mapping, groups: Sequence[Mapping] | None = None) -> list[dict]:
    """One entry per question: ``{label, partition, path, items: [{group_id, run_ids, value, fill, said}],
    not_proposed: [...], ...}``. Every value a proposal; nothing here is recorded."""
    from . import questions as Q

    groups = Q.live_groups(bundle) if groups is None else groups
    ctx = _Ctx(bundle)
    facts = _facts(bundle, groups, ctx)
    beamtime = beamtime_label(bundle)
    out: list[dict] = []
    if (pos := _position_proposal(facts, ctx)) is not None:
        out.append(pos)
    # sample ids: one per electrode; an electrode read beside two sample names (or a name with two ids) is asked
    objects: dict[str, set[str]] = {}
    given: dict[str, set[str]] = {}
    for f in facts:
        if f.electrode is not None:
            objects.setdefault(f.electrode.casefold(), set()).add(f.sample.casefold())
            if isinstance(f.sid, str):
                given.setdefault(f.electrode.casefold(), set()).add(f.sid)
    items, held = [], []
    for f in facts:
        el = f.electrode.casefold() if f.electrode is not None else None
        if el is None:
            held.append(_held(f, f.why_not.get("sample_id"), "sample_id"))
        elif len(objects[el]) > 1:
            held.append(_held(f, f"electrode number {f.electrode} is read beside more than one sample name "
                                 f"({', '.join(sorted(objects[el]))})"))
        elif beamtime is None:
            held.append(_held(f, "the beamtime folder has no name"))
        else:
            fill = {"beamtime": beamtime, "sample": f.sample, "electrode": f.electrode}
            ids = given.get(el) or set()
            said = {"electrode": f.electrode, "position": f.position, "sample": f.sample}
            if ctx.position is not None:
                said["position_from"] = ctx.position[1].get("decision_id")
            if f.decided.get("sample_id"):
                said["from_decisions"] = list(f.decided["sample_id"])
            if len(ids) == 1:
                said["as_given_for_this_electrode"] = True
            items.append({"group_id": f.gid, "run_ids": list(f.runs), "object": el,
                          "value": next(iter(ids)) if len(ids) == 1 else _fill_sample_id(SAMPLE_ID_CONVENTION, fill),
                          "fill": fill, "said": said, "first_file": f.stems[0]})
    items, more = _said_not_counter(bundle, facts, items)
    held += more
    if items or held:
        out.append({"label": "sample_id", "partition": None, "items": items, "not_proposed": held})
    items, held = [], []
    for f in facts:
        if f.filter is None:
            if f.why_not.get("filter") != "the files state no filter":
                held.append(_held(f, f.why_not.get("filter"), "filter"))
            continue
        said = {"literals": f.filter_said, "from": sorted(f.filter_from)}
        if f.decided.get("filter"):
            said["from_decisions"] = list(f.decided["filter"])
        items.append({"group_id": f.gid, "run_ids": list(f.runs), "value": f"filter{f.filter}", "fill": {"filter": f.filter},
                      "said": said, "first_file": f.stems[0]})
    if items or held:
        out.append({"label": "filter", "partition": None, "items": items, "not_proposed": held})
    by_history: dict[str, list[dict]] = {}
    held_h = []
    for f in facts:
        if f.history is None:
            if f.why_not.get("history") != "the file names state no cycling history":
                held_h.append(_held(f, f.why_not.get("history"), "history"))
            continue
        said = {"token": f.history}
        if f.decided.get("history"):
            said["from_decisions"] = list(f.decided["history"])
        by_history.setdefault(f.history_canon, []).append(
            {"group_id": f.gid, "run_ids": list(f.runs), "value": history_words(f.history), "fill": {},
             "said": said, "first_file": f.stems[0]})
    for canon, its in by_history.items():
        out.append({"label": "history", "partition": f"history={canon}", "items": its, "not_proposed": [],
                    "token": its[0]["said"]["token"]})
    if held_h:
        # the groups whose file names do not settle a history: asked on their own, one sentence per group
        out.append({"label": "history", "partition": "history=unsettled", "items": [], "not_proposed": held_h,
                    "token": None})
    chains, held_c = _chains(facts)
    items = []
    for chain in chains:
        basis = _order(chain)[1]
        for before, after in zip(chain, chain[1:]):
            items.append({"group_id": after.gid, "run_ids": list(after.runs),
                          "value": {"rel": FOLLOWS_REL, "basis": FOLLOWS_BASIS, "follows_run_key": before.keys[0],
                                    "order_basis": basis},
                          "fill": {}, "said": {"after": after.stems[0], "before": before.stems[0],
                                               "before_group_id": before.gid, "order_basis": basis,
                                               "before_interval": list(_interval(before, basis)),
                                               "after_interval": list(_interval(after, basis)),
                                               "stages_from": sorted({m.stage_from for m in (before, after)})},
                          "first_file": after.stems[0]})
    if items or held_c:
        # HIGH 2 (r8): asked whenever a chain was held too, so every reason is said
        out.append({"label": "follows", "partition": None, "items": items, "not_proposed": held_c,
                    "chains": [[m.gid for m in c] for c in chains]})
    tag = proposed_tag(beamtime)
    if tag and facts:
        out.append({"label": "tag", "partition": None, "not_proposed": [],
                    "items": [{"group_id": None, "run_ids": [], "value": [tag], "fill": {}, "said": {"folder": beamtime},
                               "first_file": None}]})
    for p in out:
        p["path"] = LABELS[p["label"]]
        p["question_id"] = question_id(p["label"], p["partition"])
    return out


def _said_not_counter(bundle: Mapping, facts: Sequence[_Facts], items: list[dict]) -> tuple[list[dict], list[dict]]:
    """r review L4: groups proposed ONE sample id under the SAME conditions whose file names differ at a digit position
    a scientist said is not a run counter (``set_not_counter_positions``: there the numbers name different samples,
    electrodes or conditions, ``grouping.said_not_counter_caution``). The conditions are equal, so the number names
    another sample: both are held, never given one id. ``(items kept, held)``."""
    from . import grouping as G

    said_not = B.not_counter_positions(bundle)
    if not said_not:
        return items, []
    by_gid = {f.gid: f for f in facts}
    buckets: dict[tuple, list[dict]] = {}
    for i in items:
        buckets.setdefault((i["value"], by_gid[i["group_id"]].full_key), []).append(i)
    out_held: dict[str, dict] = {}
    for (_, _), its in buckets.items():
        if len(its) < 2:
            continue
        toks = {i["group_id"]: G._stem_tokens(i["first_file"]) for i in its}
        for p in sorted(said_not):
            seen: dict[str, list[dict]] = {}
            for i in its:
                t = toks[i["group_id"]]
                if len(t) >= p and t[p - 1].isdigit():
                    seen.setdefault(t[p - 1], []).append(i)
            if len(seen) > 1:
                d = said_not[p].get("decision_id")
                for i in (x for group in seen.values() for x in group):
                    f = by_gid[i["group_id"]]
                    out_held.setdefault(i["group_id"], _held(f, (
                        f"under the same conditions as another group proposed {i['value']!r}, its file name differs at "
                        f"position {p}, which a scientist said is not a run counter ({d}): the number may name another "
                        "sample")))
    return [i for i in items if i["group_id"] not in out_held], list(out_held.values())


def _slot_index(bundle: Mapping) -> dict[tuple[str, str | None], Mapping]:
    """``(path, run_id) -> label slot`` (the tag's and the electrode position's run_id is ``None``)."""
    return {(m["target_field_path"], m.get("run_id")): m for m in bundle.get("missing_values") or () if is_label_slot(m)}


def _answered(slot: Mapping | None, decisions: Mapping) -> Mapping | None:
    if slot is None:
        return None
    d = decisions.get(("missing_value", slot["value_id"]))
    return d if d is not None and d.get("decision") not in B.NEUTRAL_DECISIONS else None


_WHAT = {"history": "cycling history", "sample_id": "sample id", "filter": "filter", "follows": "follows link",
         "tag": "tag", "electrode_position": "electrode position"}


def _files(rows: Sequence[Mapping], n: int = NAMED) -> str:
    names = [r.get("first_file") or ", ".join(r.get("first_files") or ()) for r in rows]
    return ", ".join(names[:n]) + (f" and {len(names) - n} more" if len(names) > n else "")


def _held_text(rows: Sequence[Mapping], qid: str, every: bool = False) -> str:
    shown = rows if every else rows[:3]
    return ("; ".join(f"{h.get('first_file') or ' + '.join(h.get('first_files') or ())}: {h['reason']}" for h in shown)
            + ("" if len(shown) == len(rows) else f"; and {len(rows) - len(shown)} more (`isaac bundle show <bundle_dir> "
                                                   f"question {qid}` lists every one with its readings)"))


def _text(p: Mapping, n_groups: int, n_runs: int) -> str:
    items, label = p["items"], p["label"]
    ex = items[:3]
    more = (f" `isaac bundle show <bundle_dir> question {p['question_id']}` lists every group."
            if len(items) > len(ex) else "")
    if label == "sample_id":
        first: dict[str, Mapping] = {}
        for i in items:
            first.setdefault(i["object"], i)
        n_obj, ex = len(first), list(first.values())
        positions = sorted({i["said"].get("position") for i in ex if i["said"].get("position")})
        from_answer = next((i["said"]["position_from"] for i in ex if i["said"].get("position_from")), None)
        where = (f"file-name position {', '.join(map(str, positions))}, the electrode position the scientist gave "
                 f"({from_answer})" if from_answer else
                 f"the number the grouping takes as the electrode or sample-instance number (sample_or_electrode_number, "
                 f"file-name position {', '.join(map(str, positions))}; each such number is read beside one sample name)")
        text = (f"Sample ids for {n_obj} physical sample(s) ({n_groups} group(s), {n_runs} run(s)). ISAAC reads {where} "
                "and proposes one id per electrode, scoped to this beamtime folder: "
                + "; ".join(f"electrode {i['said']['electrode']} ({i['first_file']}) -> {i['value']!r}"
                            + (" (the id given for its other groups)" if i["said"].get("as_given_for_this_electrode") else "")
                            for i in ex) + "."
                + " A sample id names one physical object and must be the same on every record of it. Confirm to "
                "record these ids, or give your own convention with --decision correct --value, using {electrode}, "
                "{sample} and {beamtime} (e.g. \"{sample}-e{electrode}\"). If this electrode was measured in another "
                "beamtime too, give the id used there.")
    elif label == "filter":
        n_val = len({json.dumps(i["value"]) for i in items})

        def source(i: Mapping) -> str:
            said = i.get("said") or {}
            if said.get("from_decisions"):
                return f"your answer {', '.join(said['from_decisions'])} to the files' disagreement"
            got = set(said.get("from") or ())
            return ("file name and scan header" if {"file name", "scan header"} <= got else
                    "file name" if "file name" in got else
                    f"the scan header's filter motor reads {i['fill']['filter']}" if "scan header" in got else "files")
        zero = sum(1 for i in items if i["fill"].get("filter") == 0)
        text = (f"The filter for {n_groups} group(s) ({n_runs} run(s)), into system.configuration.beam_attenuator (the "
                "portal vocabulary's key for it): the filter count a file name (rule bl15.filenames.filter_count.v1) "
                f"or the scan headers' filter motor states, written filter<n> ({n_val} value(s)). "
                + "; ".join(f"{i['first_file']} -> {i['value']!r} ({source(i)})" for i in ex)
                + (f"; and {len(items) - len(ex)} more groups." if len(items) > len(ex) else ".") + more
                + (f" filter0 ({zero} group(s)) is a count of 0: no filter in the beam." if zero else "")
                + " Confirm to record these, or give the scientist's own wording with --decision correct --value, using "
                "{filter} for the number (e.g. \"{filter} filters\"); for the groups with no filter, their own words "
                "with --only group:<id> (several --only in one call) --decision correct --value \"<words>\".")
    elif label == "history":
        text = (f"The sample's cycling history for {n_groups} group(s) ({n_runs} run(s)) whose file names write "
                f"{p['token']!r}, into context.electrochemistry.notes. Proposed wording: {items[0]['value']!r}. It only "
                "splits the file-name token into words; it does not say what the number is (millivolts or cycles). "
                "Confirm it, or give your own sentence with --decision correct --value \"<sentence>\"." + more)
    elif label == "follows":
        text = (f"Links between records of the same sample measured in sequence ({len(items)} link(s) in "
                f"{len(p.get('chains') or ())} chain(s)). For one sample (its confirmed sample id, else its electrode) "
                "under otherwise equal conditions, each later history stage follows the one before it, in the order of "
                "the run numbers (or, where those do not order them, the file-creation instants the files state). A "
                "stage is the scientist's own history answer where there is one, else the file-name token: "
                + "; ".join(f"{i['said']['after']} follows {i['said']['before']}" for i in items) + "."
                + " Each link goes into the later record (rel follows, basis same_sample_id), only when both records "
                "carry the same sample id. Confirm to record them, or reject.")
    else:
        text = (f"One tag for every record of this beamtime, from the folder name {ex[0]['said']['folder']!r}: "
                f"{ex[0]['value'][0]!r}. Confirm it, or give your own with --decision correct --value (lowercase, "
                "hyphenated, at most 64 characters).")
    return text


def _runs_of(path: str, item: Mapping) -> list:
    return list(item["run_ids"]) if path not in (TAGS_PATH, POSITION_PATH) else [None]


def _base_question(qid: str, p: Mapping, **kw) -> dict:
    from . import questions as Q

    return {
        "question_id": qid,
        "partition": kw.pop("partition", p["partition"]),
        "tier": Q.TIER_OPTIONAL,
        "blocking": False,
        "affects_record": True,
        "why": ("Optional: a label that tells this beamtime's records apart (without it, records of one sample at one "
                "potential can share one body). Proposed from the files; nothing is written until a scientist answers."),
        "kind": KIND,
        "label": p["label"],
        "scope": "experiment",
        "target_field_path": p["path"],
        **kw,
        "allowed_values": None,
        "rule_id": RULE_ID,
    }


def _position_question(p: Mapping, include_answered: bool) -> dict | None:
    answered = p.get("answer") is not None
    if answered and not include_answered:
        return None
    qid = p["question_id"]
    rows = p["candidates"]
    said_not = sorted({c["position"] for c in rows if c.get("said_not_a_counter")})
    said_not_d = sorted({c["said_not_a_counter"] for c in rows if c.get("said_not_a_counter")})

    def row(c: Mapping) -> str:
        eg = ", ".join(f"{e['number']} in {e['file']}" for e in c["examples"])
        return (f"position {c['position']} (e.g. {eg}; {c['numbers']} different number(s), "
                + (f"{c['numbers_beside_several_sample_names']} of them read beside more than one sample name)"
                   if c["numbers_beside_several_sample_names"] else "each read beside one sample name)"))
    text = (f"Which file-name number is the electrode or physical sample? The files do not settle it for "
            f"{len(p['groups'])} group(s) ({len(p['runs'])} run(s)), so ISAAC proposes no sample id for them. "
            + (f"The positions that write a number (tokens counted from 1, split at _ and -): "
               + "; ".join(row(c) for c in rows) + "." if rows else
               "No file-name position that writes a number is left (a counter answer rules out "
               + ", ".join(map(str, p["ruled_out"])) + ").")
            + (f" A counter answer rules out position(s) {', '.join(map(str, p['ruled_out']))}." if p["ruled_out"] and rows else "")
            + (f" A scientist said position(s) {', '.join(map(str, said_not))} are not run counters "
               f"({', '.join(said_not_d)}); that alone does not say which one is the electrode." if said_not else "")
            + " Answer with --decision correct --value <position>; ISAAC then proposes one sample id per electrode from "
            "the number at that position (question " + question_id("sample_id") + "). If no file-name number is the "
            "electrode, --decision reject, and give each group its id with that question.")
    q = _base_question(qid, p, text=text,
                       applies_to={"groups": len(p["groups"]), "runs": len(p["runs"]), "targets": 1},
                       targets=[{"kind": "experiment", "id": "experiment"}],
                       per_scope_targets={"experiment": ["experiment"]},
                       proposals=[], not_proposed=[], hints=[],
                       candidate_positions=[dict(c) for c in rows], ruled_out_positions=list(p["ruled_out"]),
                       allowed_decisions=list(DECISIONS["electrode_position"]),
                       answer_command=(f'isaac bundle decide <bundle_dir> --question {qid} --decision correct --value '
                                       '<position> --by "<your name>"'))
    q["why"] = ("Optional: a sample id needs the electrode's number, and the files do not say which file-name number it "
                "is. Nothing is written until a scientist answers.")
    if include_answered:
        q["answered"] = answered
        q["answered_groups"] = len(p["groups"]) if answered else 0
    return q


def _held_chains_question(p: Mapping, include_answered: bool) -> dict:
    qid = p["question_id"]
    held = p["not_proposed"]
    text = (f"No follows link is proposed: ISAAC could not order {len(held)} set(s) of groups of one sample under "
            "otherwise equal conditions. " + _held_text(held, qid, every=True)
            + ". Settle what each reason names and the links are proposed here.")
    q = _base_question(qid, p, text=text, applies_to={"groups": len({g for h in held for g in h["group_ids"]}),
                                                      "runs": 0, "targets": 0},
                       targets=[], per_scope_targets={f"group:{g}": [] for h in held for g in h["group_ids"]},
                       proposals=[], not_proposed=[dict(h) for h in held], hints=[], allowed_decisions=[],
                       informational=True, lands_in_record=False,
                       answer_command="# nothing to answer here: settle what each reason names, then the links are asked")
    q["why"] = "Informational: why no follows link is proposed for these groups."
    if include_answered:
        q["answered"] = False
        q["answered_groups"] = 0
    return q


def label_questions(bundle: Mapping, *, decisions: Mapping | None = None, groups: Sequence[Mapping] | None = None,
                    include_answered: bool = False) -> list[dict]:
    """The consolidated condition-label questions. A question drops out of the open list once every group it
    PROPOSES a value for holds an answer (``include_answered`` keeps it, with ``answered: true``); the groups it
    could not propose for (``not_proposed``) are then asked by its RESIDUAL question (partition
    :data:`RESIDUAL`, its own id). The one question that proposes nothing (``history=unsettled``) is open while one
    of its groups holds no answer. The electrode-position question is open until answered; the follows question
    that proposes nothing is informational: it says why each chain was held."""
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ()) if decisions is None else decisions
    slots = _slot_index(bundle)

    def answered(path: str, item: Mapping) -> bool:
        return all(_answered(slots.get((path, r)), decisions) is not None for r in _runs_of(path, item))

    out = []
    for p in proposals(bundle, groups):
        path = p["path"]
        if p["label"] == "electrode_position":
            if (q := _position_question(p, include_answered)) is not None:
                out.append(q)
            continue
        if p["label"] == "follows" and not p["items"]:
            out.append(_held_chains_question(p, include_answered))
            continue
        open_items = [i for i in p["items"] if not answered(path, i)]
        open_held = [h for h in p["not_proposed"] if h.get("run_ids") and not answered(path, h)]
        is_open = bool(open_items) or (not p["items"] and bool(open_held))
        residual = bool(p["items"]) and p["label"] in ("sample_id", "filter") and any(h.get("run_ids") for h in p["not_proposed"])
        # asked once every proposed group holds an answer (the label's own question lists them until then)
        rq = _residual_question(p, open_held, include_answered) if residual and not open_items and (
            include_answered or open_held) else None
        if not is_open and not include_answered:
            if rq is not None:
                out.append(rq)
            continue
        shown = p["items"] if include_answered else open_items
        done = len(p["items"]) - len(open_items)
        held = p["not_proposed"] if include_answered else [h for h in p["not_proposed"] if h not in shown]
        runs = [r for i in shown for r in i["run_ids"]]
        held_runs = [r for h in held for r in h.get("run_ids") or ()]
        groups_n = len({i["group_id"] for i in shown if i["group_id"]})
        qid = p["question_id"]
        if shown:
            text = _text({**p, "items": shown}, groups_n, len(runs))
        else:
            what = {"history": "the cycling history", "sample_id": "the physical sample",
                    "filter": "the filter"}.get(p["label"], p["label"])
            text = (f"The files do not settle {what} of {len(held)} group(s) ({len(held_runs)} run(s)), so ISAAC "
                    f"proposes nothing for {path}. Give each its value with --only group:<id> --decision correct "
                    "--value \"<value>\" (several --only in one call), or reject it.")
        if done and not include_answered:
            text += f" {done} group(s) hold an answer already and are not asked again."
        if held:
            text += (f" Not proposed for {len(held)} " + ("set(s) of groups" if p["label"] == "follows" else "group(s)")
                     + ": " + _held_text(held, qid, every=p["label"] == "follows") + " (not_proposed)."
                     + (" Answer one with --only group:<id> --decision correct --value <value>, or leave it."
                        if p["label"] != "follows" else " Those are not linked."))
        allowed = list(DECISIONS[p["label"]]) if shown else ["correct", "reject"]
        targets = ([{"kind": "experiment", "id": "experiment"}] if path == TAGS_PATH else
                   [{"kind": "run", "id": r} for r in runs + (held_runs if not shown else [])])
        q = _base_question(
            qid, p, text=text,
            applies_to={"groups": groups_n if shown or path == TAGS_PATH else len(held),
                        "runs": len(runs) if shown else len(held_runs), "targets": len(targets)},
            targets=targets,
            per_scope_targets=({"experiment": ["experiment"]} if path == TAGS_PATH else
                               {f"group:{i['group_id']}": list(i["run_ids"]) for i in (shown or held) if i.get("group_id")}),
            proposals=[{k: i[k] for k in ("group_id", "run_ids", "value", "said", "first_file", "fill", "object")
                        if k in i} for i in shown],
            not_proposed=[dict(h) for h in held],
            hints=[{"kind": "label_proposal", "literal": i["value"] if not isinstance(i["value"], list) else i["value"][0],
                    "group_id": i["group_id"], "first_file": i["first_file"], "rule_id": RULE_ID}
                   for i in shown[:5] if p["label"] != "follows"],
            allowed_decisions=allowed,
            answer_command=((f'isaac bundle decide <bundle_dir> --question {qid} --decision confirm --by "<your name>"'
                             "   # one group only: add --only group:<group_id>") if shown else
                            (f'isaac bundle decide <bundle_dir> --question {qid} --only group:<group_id> '
                             '--decision correct --value "<value>" --by "<your name>"')))
        if include_answered:
            q["answered"] = not is_open
            q["answered_groups"] = done
        out.append(q)
        if rq is not None:
            out.append(rq)  # after the label's own question
    return out


def _residual_question(p: Mapping, open_held: Sequence[Mapping], include_answered: bool) -> dict:
    """MED 4 (r8): the groups of a label ISAAC proposed nothing for, still asked once every proposed group is answered
    (a new id, :data:`RESIDUAL`; the label's own question keeps its id)."""
    qid = question_id(p["label"], RESIDUAL)
    held = [h for h in p["not_proposed"] if h.get("run_ids")] if include_answered else list(open_held)
    runs = [r for h in held for r in h["run_ids"]]
    what = _WHAT[p["label"]]
    text = (f"{len(held)} group(s) still have no {what}: ISAAC could not propose one, so nothing is written for "
            f"{p['path']} on their records until you answer. " + _held_text(held, qid, every=len(held) <= NAMED)
            + f". Give each its value with --only group:<id> --decision correct --value \"<value>\" (several --only in "
            "one call when they take one value), or reject to record that it is not written.")
    q = _base_question(qid, {**p, "partition": RESIDUAL}, text=text,
                       applies_to={"groups": len(held), "runs": len(runs), "targets": len(runs)},
                       targets=[{"kind": "run", "id": r} for r in runs],
                       per_scope_targets={f"group:{h['group_id']}": list(h["run_ids"]) for h in held},
                       proposals=[], not_proposed=[dict(h) for h in held], hints=[],
                       allowed_decisions=["correct", "reject"],
                       answer_command=(f'isaac bundle decide <bundle_dir> --question {qid} --only group:<group_id> '
                                       '--decision correct --value "<value>" --by "<your name>"'),
                       residual_of=p["question_id"])
    if include_answered:
        q["answered"] = not open_held
        q["answered_groups"] = len(held) - len(open_held)
    return q


def question_by_id(bundle: Mapping, qid: str) -> dict | None:
    """The label question ``qid`` (open or answered), or ``None`` when ``qid`` is not one."""
    return next((q for q in label_questions(bundle, include_answered=True) if q["question_id"] == qid), None)


def for_group(q: Mapping, scope: str) -> Mapping:
    """r8 LOW: a label question as one group's list shows it (``--scope group:<id>``): only that group's row, with a
    pointer to the whole question. Its id, and the unscoped question, are unchanged (a copy is returned)."""
    gid = scope[len("group:"):]
    mine = [i for i in q.get("proposals") or () if i.get("group_id") == gid]
    held = [h for h in q.get("not_proposed") or () if h.get("group_id") == gid or gid in (h.get("group_ids") or ())]
    if not mine and not held:
        return q
    runs = [r for i in (*mine, *held) for r in i.get("run_ids") or ()]
    pointer = (f" The question asks {q['applies_to'].get('groups')} group(s) in all: `isaac bundle show <bundle_dir> "
               f"question {q['question_id']}` shows every one.")
    if mine:
        i = mine[0]
        value = i["value"]["follows_run_key"].split("@")[0] if isinstance(i["value"], Mapping) else i["value"]
        text = (f"For this group ({i['first_file']}) ISAAC proposes {value!r} for {q['target_field_path']}"
                + (f" (it follows {i['said'].get('before')})" if q.get("label") == "follows" else "")
                + f". Confirm it for this group with --only {scope}, or give another value with --only {scope} "
                "--decision correct --value <value>." + pointer)
    else:
        h = held[0]
        text = (f"ISAAC proposes no {_WHAT.get(q.get('label'), q.get('label'))} for this group "
                f"({h.get('first_file') or ' + '.join(h.get('first_files') or ())}): {h['reason']}."
                + ("" if q.get("label") == "follows" else
                   f" Give its value with --only {scope} --decision correct --value <value>, or leave it.") + pointer)
    return {**q, "text": text, "proposals": [dict(i) for i in mine], "not_proposed": [dict(h) for h in held],
            "targets": [{"kind": "run", "id": r} for r in runs] if q.get("targets") else [],
            "per_scope_targets": {scope: runs}, "hints": [h for h in q.get("hints") or () if h.get("group_id") == gid],
            "applies_to": {**q["applies_to"], "groups_in_this_scope": 1}, "scoped_to_group": gid}


# --- decide -------------------------------------------------------------------------------------


class LabelRefused(ValueError):
    pass


def _object(item: Mapping) -> Any:
    """The physical object a sample-id proposal is of: its electrode number, case-folded (``None``: not proposed)."""
    return str((item.get("said") or {}).get("electrode") or "").casefold() or None


def _pattern_values(asked: Mapping, items: Sequence[Mapping], value: str) -> dict[str, Any]:
    label = asked["label"]
    names = SAMPLE_ID_PLACEHOLDERS if label == "sample_id" else FILTER_PLACEHOLDERS
    used = _PLACEHOLDER.findall(value)
    if sorted({u for u in used if u not in names}) or value.count("{") != len(used) or value.count("}") != len(used):
        raise LabelRefused(f"--value {value!r}: the placeholders it takes are "
                           + ", ".join("{" + n + "}" for n in names) + " (and no other braces). Nothing was recorded.")
    if used and any(i.get("value") is None for i in items):
        raise LabelRefused(f"--value {value!r} uses placeholders, but ISAAC proposed nothing for this group, so there "
                           "is nothing to fill them with: give the value itself. Nothing was recorded.")
    key = "electrode" if label == "sample_id" else "filter"
    distinct = {json.dumps(i["value"]) for i in items}
    if len(distinct) > 1 and key not in used:
        raise LabelRefused(f"--value {value!r} would give {len(distinct)} different proposals one value: put "
                           "{" + key + "} in it, or answer one group with --only group:<id>. Nothing was recorded.")
    return {i["group_id"]: _fill_sample_id(value, i.get("fill") or {}) for i in items}


def _values_for(asked: Mapping, items: Sequence[Mapping], decision: str, value: Any, *, same_sample: bool = False) -> dict[str, Any]:
    """``group_id -> value`` this answer records (``None`` for ``reject``). Refused with the reason."""
    label = asked["label"]
    if decision == "reject":
        if value is not None:
            raise LabelRefused("`reject` takes no --value. Nothing was recorded.")
        return {i["group_id"]: None for i in items}
    if decision == "confirm":
        if value is not None:
            raise LabelRefused("`confirm` records the proposed values; to give your own, use --decision correct "
                               "--value. Nothing was recorded.")
        return {i["group_id"]: i["value"] for i in items}
    if value is None:
        raise LabelRefused("`correct` needs --value. Nothing was recorded.")
    if label == "tag":
        return {i["group_id"]: [value] if isinstance(value, str) else value for i in items}
    if label == "history":
        return {i["group_id"]: value for i in items}
    if not isinstance(value, str):
        # a number given with --json: one filter for groups proposed one value (or one group), never for several
        if label == "filter" and len({json.dumps(i["value"]) for i in items}) == 1:
            return {i["group_id"]: value for i in items}
        names = SAMPLE_ID_PLACEHOLDERS if label == "sample_id" else FILTER_PLACEHOLDERS
        raise LabelRefused(f"--value for question {asked['question_id']} is one text pattern using "
                           + ", ".join("{" + n + "}" for n in names) + ". Nothing was recorded.")
    out = _pattern_values(asked, items, value)
    if label == "sample_id" and not same_sample:
        by_value: dict[str, set] = {}
        for i in items:
            by_value.setdefault(out[i["group_id"]], set()).add(_object(i) or i["group_id"])
        clash = [v for v, objs in by_value.items() if len(objs) > 1]
        if clash:
            raise LabelRefused(f"--value {value!r} gives two physical samples the same id ({clash[0]!r}): a sample id "
                               "names one object. Put {electrode} in it"
                               + (", or, if the scientist says these groups are one physical sample, add --same-sample"
                                  if all(_object(i) is None for i in items) else "") + ". Nothing was recorded.")
    return out


def _onlys(only: Any) -> list[str] | None:
    if only is None:
        return None
    return [only] if isinstance(only, str) else list(dict.fromkeys(only))


def _same_sample_problem(a: _Facts, b: _Facts, position: int | None) -> str | None:
    """MED 3 (r8): why groups ``a`` and ``b`` cannot be one physical sample by their own file names, or ``None``: their
    sample names differ, or the numbers at the electrode position (where it is known) differ."""
    from . import grouping as G

    if a.names and b.names and a.names != b.names:
        return (f"{a.stems[0]} is sample {'/'.join(a.names_said)} and {b.stems[0]} is sample "
                f"{'/'.join(b.names_said)}")
    for p in sorted({x for x in (position, a.position, b.position) if x}):
        ta = [t[p - 1] for t in (G._stem_tokens(s) for s in a.stems) if len(t) >= p]
        tb = [t[p - 1] for t in (G._stem_tokens(s) for s in b.stems) if len(t) >= p]
        if ta and tb and ta[0].isdigit() and tb[0].isdigit() and ta[0].casefold() != tb[0].casefold():
            return (f"{a.stems[0]} writes {ta[0]} and {b.stems[0]} writes {tb[0]} at file-name position {p}, where the "
                    "electrode number is")
    return None


def _contradictions(asked: Mapping, items: Sequence[Mapping], values: Mapping[str, Any]) -> list[str]:
    """LOW (r8): a filter the scientist typed that the files' own readings contradict, named as template import does.
    Recorded all the same: the scientist's word stands."""
    if asked["label"] != "filter":
        return []
    out = []
    for i in items:
        v = values.get(i["group_id"])
        n = filter_number(v) if v is not None else None
        if n is None:
            m = re.search(r"\d+", str(v)) if isinstance(v, str) else None
            n = int(m.group(0)) if m and len(re.findall(r"\d+", str(v))) == 1 else None
        if n is None:
            continue
        read = ([i["fill"]["filter"]] if (i.get("fill") or {}).get("filter") is not None else
                [x for x in (filter_number(r.get("value")) for r in i.get("readings") or ()) if x is not None])
        if read and n not in read:
            out.append(f"{i.get('first_file')}: you gave {v!r} (filter {n}), but the files read "
                       + (readings_text(i["readings"]) if i.get("readings") else
                          f"{read[0]} ({', '.join((i.get('said') or {}).get('from') or ()) or 'files'})"))
    return out


def _decide_position(bundle: dict, asked: Mapping, *, decision: str, value: Any, only: Any, by: str,
                     orcid: str | None, note: str | None) -> dict:
    """``decide --question`` on the electrode-position question: one beamtime-level slot."""
    from . import mutations as M

    qid = asked["question_id"]
    if only is not None:
        raise LabelRefused(f"Question {qid} is asked once for the beamtime: answer it without --only. Nothing was recorded.")
    if decision not in DECISIONS["electrode_position"]:
        raise LabelRefused(f"`{decision}` does not answer question {qid} ({KIND}); use one of: correct (with --value "
                           "<position>), reject. Nothing was recorded.")
    candidates = [c["position"] for c in asked.get("candidate_positions") or ()]
    p = None
    if decision == "correct":
        p = _as_position(value)
        if p is None or p not in candidates:
            raise LabelRefused(f"--value {value!r} is not one of the file-name positions that write a number here ("
                               + (", ".join(map(str, candidates)) or "none") + f"; see question {qid}). Nothing was "
                               "recorded.")
    elif value is not None:
        raise LabelRefused("`reject` takes no --value. Nothing was recorded.")
    slot = _slot_index(bundle).get((POSITION_PATH, None))
    added = []
    if slot is None:
        n = max((int(m["value_id"].split("-", 1)[1]) for m in bundle.get("missing_values") or ()
                 if re.fullmatch(r"miss-\d+", str(m.get("value_id")))), default=0)
        slot = B._missing(n, None, POSITION_PATH, "record",
                          SLOT_REASON.format(question=qid, what="which file-name number is the electrode"), {}, frozenset())
        slot["eligibility_for_official_record"] = slot_eligibility(B.STATE_MISSING, slot, None)
        bundle.setdefault("missing_values", []).append(slot)
        added.append(slot["value_id"])
    said = f"Answered with question {qid} ({KIND}, {RULE_ID})."
    try:
        r = M.record_decision(bundle, target_ids=[slot["value_id"]], decision=decision, value=p, by=by, orcid=orcid,
                              note=f"{note} {said}" if note else said)
    finally:
        M.drop_unrecorded_slots(bundle, added)
    recorded = len(r.get("recorded") or ())
    now = next((x for x in proposals(bundle) if x["label"] == "sample_id"), None) or {"items": [], "not_proposed": []}
    objs = {i["object"] for i in now["items"]}
    sid_q = question_id("sample_id")
    if not recorded:
        statement = f"Nothing new recorded: question {qid} already holds that answer."
    elif p is not None:
        statement = (f"Recorded: the electrode is file-name number {p} (question {qid}). The sample-id question {sid_q} "
                     f"now proposes {len(objs)} id(s) for {len(now['items'])} group(s); "
                     f"{len(now['not_proposed'])} group(s) still get none. Read them back and confirm there.")
    else:
        statement = (f"Recorded: no file-name number is the electrode (question {qid}). Give each group its id with "
                     f"question {sid_q} (--only group:<id> --decision correct --value <id>).")
    return {"statement": statement, "question_id": qid, "label": "electrode_position", "path": POSITION_PATH,
            "groups_recorded": 0, "slots_recorded": recorded, "slots_unchanged": len(r.get("unchanged") or ()),
            "values": [p] if p is not None else [None], "values_total": 1}


def _file_of_run(bundle: Mapping) -> dict[str, str]:
    return {r["run_id"]: str(r.get("stem") or r["run_id"]) for r in bundle.get("runs") or ()}


def decide(bundle: dict, asked: Mapping, *, decision: str, value: Any, only: Any, by: str,
           orcid: str | None, note: str | None, same_sample: bool = False) -> dict:
    """``decide --question`` on a label question, under the caller's lock, on ``bundle`` in memory (the caller
    saves). ``confirm`` records the proposed values; ``correct`` records the scientist's value (for ids and filters a
    pattern, ``{electrode}`` / ``{filter}``); ``reject`` records that the label is not written.

    WITHOUT ``--only`` an answer writes ONLY slots that hold no answer yet: a run already answered keeps its answer,
    and a group whose answered runs hold another value than this answer gives is left out whole and named
    (``kept``), never overwritten. ``--only group:<id>`` answers that one group (its answered runs too: the scientist
    named it), and also a group ISAAC proposed nothing for (``correct`` or ``reject`` only); several ``--only`` answer
    each of those groups with the one value. A sample id given for one group is the electrode's: it is recorded for
    every group of that electrode.

    A SAMPLE ID NAMES ONE PHYSICAL OBJECT. Refused when runs of another electrode hold (or are proposed) the id. A
    group ISAAC could not place (``not_proposed``) takes an id other runs hold or are proposed only with
    ``same_sample``: the scientist's statement that it is the same physical sample, said in the reply and the
    decision's note. Even then it is refused when the two groups' own file names state another sample name, or
    another number at the electrode position (MED 3, r8). A later bulk answer that gives an electrode the id such a
    group holds is recorded and names it (``shares_id_with``). One decision per run's slot, through
    :func:`mutations.record_decision`."""
    from . import mutations as M
    from . import questions as Q

    qid, path, label = asked["question_id"], asked["target_field_path"], asked["label"]
    if label == "electrode_position":
        if same_sample:
            raise LabelRefused("--same-sample goes with the sample-id question. Nothing was recorded.")
        return _decide_position(bundle, asked, decision=decision, value=value, only=only, by=by, orcid=orcid, note=note)
    if asked.get("informational"):
        raise LabelRefused(f"Question {qid} proposes no link: it says why each chain was held ("
                           + _held_text(asked.get("not_proposed") or (), qid) + "). Settle that, and the links are "
                           "asked. Nothing was recorded.")
    if decision not in DECISIONS[label] or (decision == "confirm" and not asked["proposals"]):
        raise LabelRefused(f"`{decision}` does not answer question {qid} ({KIND}); use one of: "
                           f"{', '.join(asked['allowed_decisions'])}. Nothing was recorded.")
    onlys = _onlys(only)
    if same_sample and (label != "sample_id" or not onlys or decision != "correct"):
        raise LabelRefused("--same-sample goes with the sample-id question, --only group:<id> and --decision correct "
                           "--value <id>. Nothing was recorded.")
    full = {i["group_id"]: i for i in asked["proposals"]}
    held = {h["group_id"]: {**h, "value": None, "said": {}, "fill": {}} for h in asked.get("not_proposed") or ()
            if h.get("group_id") and h.get("run_ids")}
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    slots = _slot_index(bundle)
    file_of = _file_of_run(bundle)

    def answer_of(rid: Any) -> Mapping | None:
        return _answered(slots.get((path, rid)), decisions)

    def named(gid: str) -> str:
        i = full.get(gid) or held.get(gid) or {}
        return f"{i.get('first_file') or gid}"

    if onlys is not None:
        items: list[dict] = []
        for sc in onlys:
            gid = sc[len("group:"):] if sc.startswith("group:") else None
            if label == "tag" or gid is None or (gid not in full and gid not in held):
                raise LabelRefused(f"Question {qid} has no group {sc!r}"
                                   + (" (it is asked once for the beamtime: answer it without --only)" if label == "tag" else "")
                                   + ". Nothing was recorded.")
            if gid in held and (decision == "confirm" or label == "follows"):
                raise LabelRefused(f"ISAAC proposed nothing for {named(gid)} ({held[gid]['reason']}), so there is nothing "
                                   "to confirm" + (": it is not linked." if label == "follows" else
                                                   "; give the value with --decision correct --value <value>.")
                                   + " Nothing was recorded.")
            mine = [full.get(gid) or held[gid]]
            if label == "sample_id" and decision == "correct" and _object(mine[0]) is not None:
                # AN ID IS THE OBJECT'S: given for one group, it is recorded for every group of that electrode
                mine = [i for i in asked["proposals"] if _object(i) == _object(mine[0])]
            items += [i for i in mine if all(i["group_id"] != x["group_id"] for x in items)]
    else:
        items = list(asked["proposals"])
        if not items:
            raise LabelRefused(f"Question {qid} proposes nothing: answer each group with --only group:<id> "
                               "--decision correct --value <value> (several --only in one call). Nothing was recorded.")
    values = _values_for(asked, items, decision, value, same_sample=same_sample)
    for v in values.values():
        if v is not None and (problem := label_value_problem(path, v)) is not None:
            raise LabelRefused(f"{problem}; {v!r} cannot be the label. Nothing was recorded.")
    # WHICH SLOTS THIS ANSWER WRITES (r: never an earlier answer, unless --only names its group)
    kept: list[dict] = []
    write: list[tuple[dict, list]] = []
    for i in items:
        runs = _runs_of(path, i)
        if onlys is not None:
            write.append((i, runs))
            continue
        v = values[i["group_id"]]
        theirs = {rid: d for rid in runs if (d := answer_of(rid)) is not None}
        differ = {rid: d for rid, d in theirs.items()
                  if (d.get("decision") == "reject") != (decision == "reject")
                  or json.dumps(d.get("value"), sort_keys=True) != json.dumps(v, sort_keys=True)}
        if differ:
            rid, d = next(iter(differ.items()))
            kept.append({"group_id": i["group_id"], "first_file": i.get("first_file"), "run_id": rid,
                         "file": file_of.get(rid), "decision_id": d.get("decision_id"),
                         "holds": d.get("value") if d.get("decision") != "reject" else None,
                         "decision": d.get("decision"), "this_answer": v})
            continue
        rest = [rid for rid in runs if rid not in theirs]
        if rest:
            write.append((i, rest))
    if not write:
        if kept:
            raise LabelRefused(_kept_sentence(qid, kept, nothing=True))
        raise LabelRefused(f"Every group of question {qid} holds an answer already; to change one, add --only "
                           "group:<id>. Nothing was recorded.")
    joined: list[dict] = []
    shares: list[dict] = []
    if label == "sample_id" and decision != "reject":
        mine = {r for i, runs in write for r in runs}
        # every proposal of the label, not only the asked question's (a residual question proposes none)
        every = asked["proposals"] if asked.get("partition") != RESIDUAL else next(
            (p["items"] for p in proposals(bundle) if p["label"] == label), [])
        obj_of_run = {r: _object(i) for i in every for r in i["run_ids"]}
        facts = None
        # who holds each id now (an answer), or is proposed it (a proposal not yet answered)
        holders: dict[str, list[tuple[Any, str, str]]] = {}
        for (p, rid), m in slots.items():
            d = _answered(m, decisions)
            if p == SAMPLE_ID_PATH and rid not in mine and d is not None and d.get("decision") != "reject":
                holders.setdefault(json.dumps(d.get("value")), []).append((obj_of_run.get(rid), rid, "holds"))
        if onlys is not None:
            for i in every:
                if answer_of(i["run_ids"][0]) is None and not set(i["run_ids"]) & mine:
                    holders.setdefault(json.dumps(i["value"]), []).append((_object(i), i["run_ids"][0], "is proposed"))
        # the groups of this one call that are given one id together (several --only with --same-sample)
        together: dict[str, list[dict]] = {}
        for i, _ in write:
            together.setdefault(json.dumps(values[i["group_id"]]), []).append(i)
        for i, _ in write:
            v, me = values[i["group_id"]], _object(i)
            others = list(holders.get(json.dumps(v), ()))
            if same_sample:
                others += [(None, x["run_ids"][0], "is given it in this answer") for x in together[json.dumps(v)]
                           if x["group_id"] != i["group_id"] and _object(x) is None]
            for other, rid, how in others:
                if me is not None and other is not None:
                    if me != other:
                        raise LabelRefused(f"{v!r} {'is already' if how == 'holds' else 'is proposed as'} the sample id of "
                                           f"electrode {other} ({file_of.get(rid, rid)}): a sample id names one physical "
                                           "object. Nothing was recorded.")
                    continue
                if onlys is not None and not same_sample:
                    raise LabelRefused(
                        f"{file_of.get(rid, rid)} {'already holds' if how == 'holds' else 'is proposed'} {v!r}, and ISAAC "
                        f"does not read {named(i['group_id'])} as that electrode "
                        f"({(held.get(i['group_id']) or {}).get('reason') or 'its electrode is not settled'}). "
                        "A sample id names one physical object. If the scientist says it IS the same physical sample, "
                        "add --same-sample; otherwise give it another id. Nothing was recorded.")
                if onlys is not None:
                    if facts is None:
                        ctx = _Ctx(bundle)
                        facts = {r: f for f in _facts(bundle, Q.live_groups(bundle), ctx) for r in f.runs}
                    a, b = facts.get(i["run_ids"][0]), facts.get(rid)
                    pos = ctx.position[0] if ctx.position else None
                    problem = _same_sample_problem(a, b, pos) if a is not None and b is not None and a is not b else None
                    if problem:
                        raise LabelRefused(
                            f"--same-sample refused: {problem}. Their own file names say they are not one physical "
                            f"sample, so {v!r} cannot name both. Give {named(i['group_id'])} its own id; if the file "
                            "names are wrong, say so in the beamtime notes and ask the beamline. Nothing was recorded.")
                    joined.append({"group_id": i["group_id"], "with_run": rid, "with_file": file_of.get(rid, rid),
                                   "value": v})
                else:
                    shares.append({"group_id": i["group_id"], "first_file": i.get("first_file"), "with_run": rid,
                                   "with_file": file_of.get(rid, rid), "value": v})
    contradicts = _contradictions(asked, [i for i, _ in write], values) if decision == "correct" else []
    numbers = [int(m["value_id"].split("-", 1)[1]) for m in bundle.get("missing_values") or ()
               if re.fullmatch(r"miss-\d+", str(m.get("value_id")))]
    n = max(numbers, default=0)
    what = {"sample_id": "the physical sample's id", "filter": "the filter setting", "history": "the sample's history",
            "follows": "the record this run's record follows", "tag": "the beamtime's tag"}[label]
    reason = SLOT_REASON.format(question=qid, what=what)
    targets: dict[str, list[str]] = {}
    value_of: dict[str, Any] = {}
    added: list[str] = []
    for i, runs in write:
        v = values[i["group_id"]]
        key = json.dumps(v, sort_keys=True)
        value_of[key] = v
        for rid in runs:
            slot = slots.get((path, rid))
            if slot is None:
                slot = B._missing(n, rid, path, "run" if rid is not None else "record", reason, {}, frozenset())
                slot["eligibility_for_official_record"] = slot_eligibility(B.STATE_MISSING, slot, None)
                n += 1
                bundle.setdefault("missing_values", []).append(slot)
                slots[(path, rid)] = slot
                added.append(slot["value_id"])
            targets.setdefault(key, []).append(slot["value_id"])
    recorded, unchanged = 0, 0
    said = f"Answered with question {qid} ({KIND}, {RULE_ID})."
    if joined:
        said += (" The scientist stated this group is the same physical sample as "
                 + ", ".join(sorted({j["with_file"] for j in joined})) + " (--same-sample).")
    if contradicts:
        said += " It contradicts the files: " + "; ".join(contradicts) + "."
    try:
        for key, ids in targets.items():
            r = M.record_decision(bundle, target_ids=ids, decision=decision, value=value_of[key], by=by, orcid=orcid,
                                  note=f"{note} {said}" if note else said)
            recorded += len(r.get("recorded") or ())
            unchanged += len(r.get("unchanged") or ())
    finally:
        M.drop_unrecorded_slots(bundle, added)
    groups = [i["group_id"] for i, _ in write if i["group_id"]]
    n_runs = sum(len(runs) for i, runs in write if i["group_id"])
    verb = {"confirm": "Recorded the proposed", "correct": "Recorded your", "reject": "Recorded: no"}[decision]
    statement = (f"{verb} {path} for " + (f"{len(groups)} group(s) ({n_runs} run(s))" if groups else "the beamtime")
                 + f", question {qid}.")
    if label == "follows" and decision != "reject":
        statement += " Each link is written at export, into the later record, when both records carry the same sample id."
    if unchanged and not recorded:
        statement = f"Nothing new recorded: every group question {qid} reaches already holds that answer."
    if joined:
        statement += (f" Recorded as the same physical sample as {joined[0]['with_file']} ({joined[0]['value']!r}), "
                      "as the scientist stated (--same-sample).")
    if shares:
        statement += (" " + "; ".join(f"{x['first_file']} now shares {x['value']!r} with {x['with_file']}, which a "
                                      "scientist gave that id on its own" for x in shares[:3])
                      + ": they are one physical sample in the records. If they are not, give one of them another id "
                      "with --only group:<id>.")
    if contradicts:
        statement += " Recorded as you gave it, but it contradicts the files: " + "; ".join(contradicts[:3]) + "."
    if kept:
        statement += " " + _kept_sentence(qid, kept)
    # MED 4 (r8): a bulk answer says which groups it could not reach (an --only answer names its own groups)
    left = _still_without(bundle, asked) if recorded and onlys is None else []
    if left:
        rq = (question_id(label, RESIDUAL) if label in ("sample_id", "filter") and asked.get("proposals") else
              asked["question_id"] if label in ("sample_id", "filter") else question_id("history", "history=unsettled"))
        statement += (f" {len(left)} group(s) still have no {_WHAT[label]}: {_files(left)}. ISAAC could not propose one; "
                      f"answer them with question {rq} (--only group:<id> --decision correct --value <value>), or leave "
                      "them.")
    return {"statement": statement, "question_id": qid, "label": label, "path": path,
            "groups_recorded": len(groups), "slots_recorded": recorded, "slots_unchanged": unchanged,
            "values": [value_of[k] for k in list(value_of)[:5]], "values_total": len(value_of),
            **({"kept": kept} if kept else {}), **({"same_sample": joined} if joined else {}),
            **({"shares_id_with": shares} if shares else {}), **({"contradicts_files": contradicts} if contradicts else {}),
            **({"still_without": [{"group_id": h["group_id"], "first_file": h.get("first_file"), "reason": h.get("reason")}
                                  for h in left]} if left else {})}


def _still_without(bundle: Mapping, asked: Mapping) -> list[dict]:
    """MED 4 (r8): the groups of ``asked``'s label ISAAC proposed nothing for that hold no answer (after this one)."""
    label = asked["label"]
    if label not in ("sample_id", "filter", "history"):
        return []
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    slots = _slot_index(bundle)
    out = []
    for p in proposals(bundle):
        if p["label"] != label or (label == "history" and p["partition"] != "history=unsettled"):
            continue
        for h in p["not_proposed"]:
            if h.get("run_ids") and any(_answered(slots.get((p["path"], r)), decisions) is None for r in h["run_ids"]):
                out.append(h)
    return out


def _kept_sentence(qid: str, kept: Sequence[Mapping], nothing: bool = False) -> str:
    """The groups an answer left out because some of their runs already hold another answer."""
    shown = "; ".join(f"{k.get('first_file')}: {k.get('file') or k['run_id']} holds "
                      + (f"{k['holds']!r}" if k.get("holds") is not None else f"a {k['decision']}")
                      + f" ({k['decision_id']})" for k in kept[:3]) + ("; …" if len(kept) > 3 else "")
    return ((f"Nothing was recorded: " if nothing else f"Left out {len(kept)} group(s) whose runs already hold another "
             "answer, never overwritten: ") + shown + f". To change one, answer question {qid} with --only group:<id>.")


# --- the readings' own disagreement questions ----------------------------------------------------


def _conflict_key(cf: Mapping) -> str:
    return str(cf.get("engine_conflict_id") or "").rsplit("::", 1)[-1]


def point_conflicts_at_labels(questions: list[dict], bundle: Mapping, group_of: Mapping[str, str]) -> None:
    """MED 5 (r8): a ``resolve_conflict`` question on a reading a label is proposed from (the filter, the cycling
    token, the electrode number) says, in its ``why``, which label question writes the field for its group, and that
    settling it here feeds that question. Its id, kind, scope and targets are unchanged."""
    cfs = {cf["conflict_id"]: cf for cf in bundle.get("conflicts") or () if _conflict_key(cf) in POINT_KEYS}
    if not cfs:
        return
    labels_by_group: dict[tuple[str, str], str] = {}
    for q in questions:
        if q.get("kind") == KIND and not q.get("informational"):
            for sc in q.get("per_scope_targets") or ():
                if sc.startswith("group:"):
                    labels_by_group.setdefault((q["label"], sc[len("group:"):]), q["question_id"])
    for q in questions:
        if q.get("kind") != "resolve_conflict" or not q.get("targets"):
            continue
        cf = cfs.get(q["targets"][0].get("id"))
        if cf is None:
            continue
        label = POINT_KEYS[_conflict_key(cf)]
        gids = sorted({group_of[r] for r in cf.get("run_ids") or () if r in group_of})
        if not gids:
            continue
        gid = gids[0]
        lq = labels_by_group.get((label, gid)) or question_id(label, "history=unsettled" if label == "history" else None)
        q["label_question"] = lq
        generic = str(q.get("why") or "").startswith("The sources disagree")
        if q.get("no_record_field"):
            # the classification (and so the counts) is unchanged; its words are true again
            q["no_record_field"] = f"the {_WHAT[label]} reading, which only the condition-label question {lq} writes"
        said = (f"The sources disagree about the {_WHAT[label]} reading of this group. Settling it here records which "
                    f"reading is right. It does not write {LABELS[label]} by itself: the condition-label question {lq} "
                    f"does, for this group (`--question {lq} --only group:{gid}`). Once you settle it, that question "
                    "proposes the value from your answer; if you answered that label for the other groups already, your "
                    "answer here records it for this group the same way, and the reply says so.")
        # a why that says something of its own (e.g. "Already decided: ...") is kept, and this is added after it
        q["why"] = said if generic else f"{q.get('why')} {said}"


def _form_of(label: str, answered: Sequence[tuple[Mapping, Mapping]]) -> tuple[str, Any] | None:
    """How the scientist's answers to ``label`` for OTHER groups were given, so ISAAC can give a new group the same:
    ``("proposal", None)`` (they confirmed what ISAAC proposed), ``("pattern", "<words with {filter}>")`` (their own
    filter wording, the same for every group), ``("literal", value)`` (one history sentence for every group of the
    token), or ``None`` when the answers do not show one form. ``answered``: ``(item, decision)``."""
    forms = set()
    for i, d in answered:
        if d.get("decision") == "reject":
            return None
        v = d.get("value")
        if json.dumps(v, sort_keys=True) == json.dumps(i.get("value"), sort_keys=True):
            forms.add(("proposal", None))
        elif label == "filter" and isinstance(v, str) and (i.get("fill") or {}).get("filter") is not None:
            n = str(i["fill"]["filter"])
            ok = v.count(n) == 1 and not re.search(r"\d", v.replace(n, "")) and "{" not in v
            forms.add(("pattern", v.replace(n, "{filter}")) if ok else None)
        elif label == "history" and isinstance(v, str):
            forms.add(("literal", v))
        else:
            forms.add(None)
    return next(iter(forms)) if len(forms) == 1 and None not in forms else None


def feed_from_conflicts(bundle: dict, conflict_ids: Sequence[str], *, by: str, orcid: str | None,
                        note: str | None = None) -> dict | None:
    """MED 5 (r8): after a scientist settled a disagreement on a label's reading, record that label for the group
    through :func:`decide` (``--only group:<id>``), as the scientist's own earlier answers to that label question
    were given: only when the group now has a proposal, holds no label answer, and the scientist answered that label
    for other groups in one form (they confirmed the proposals, or gave one wording). Otherwise nothing is recorded
    and the reply says where the label is now proposed. ``{statement, recorded: [...]}`` or ``None``."""
    cfs = [cf for cf in bundle.get("conflicts") or () if cf.get("conflict_id") in set(conflict_ids)
           and _conflict_key(cf) in FEED_KEYS]
    if not cfs:
        return None
    runs = {r for cf in cfs for r in cf.get("run_ids") or ()}
    labels = {FEED_KEYS[_conflict_key(cf)] for cf in cfs}
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    slots = _slot_index(bundle)
    said, recorded = [], []
    for q in label_questions(bundle, include_answered=True):
        if q["label"] not in labels or not q.get("proposals"):
            continue
        path = q["target_field_path"]
        mine = [i for i in q["proposals"] if set(i["run_ids"]) & runs]
        if not mine:
            continue
        answered = [(i, d) for i in q["proposals"] if i not in mine and i["run_ids"]
                    and (d := _answered(slots.get((path, i["run_ids"][0])), decisions)) is not None]
        for i in mine:
            if any(_answered(slots.get((path, r)), decisions) is not None for r in i["run_ids"]):
                continue
            form = (("proposal", None) if (i.get("said") or {}).get("as_given_for_this_electrode") else
                    _form_of(q["label"], answered) if answered else None)
            if form is None:
                said.append(f"{i['first_file']}: question {q['question_id']} now proposes {i['value']!r} for {path}; "
                            "answer it there")
                continue
            value = (None if form[0] == "proposal" else form[1] if form[0] == "literal" else
                     _fill_sample_id(form[1], i.get("fill") or {}))
            try:
                r = decide(bundle, q, decision="confirm" if form[0] == "proposal" else "correct", value=value,
                           only=f"group:{i['group_id']}", by=by, orcid=orcid,
                           note=((note + " ") if note else "") + "Recorded from the scientist's answer to the files' "
                           "disagreement on this reading (" + ", ".join(i["said"].get("from_decisions") or ()) + "), in "
                           "the form of their earlier answers to this label question.")
            except LabelRefused as exc:
                said.append(f"{i['first_file']}: {path} not recorded ({exc})")
                continue
            if r.get("slots_recorded"):
                recorded.append({"group_id": i["group_id"], "first_file": i["first_file"], "path": path,
                                 "question_id": q["question_id"], "value": value if value is not None else i["value"]})
                said.append(f"{i['first_file']}: also recorded {path} = "
                            f"{recorded[-1]['value']!r} (question {q['question_id']}), as you answered it for the other groups")
    if not said:
        return None
    return {"statement": "Condition labels: " + "; ".join(said) + ".", "recorded": recorded}


# --- validate -----------------------------------------------------------------------------------


SAME_RECORD_WARNING = "same_sample_and_conditions"
UNPROPOSED_WARNING = "label_not_proposed"


def record_warnings(bundle: Mapping, fresh: Sequence[tuple[str, Mapping, Mapping]], exportable: Sequence[str]) -> list[dict]:
    """r8 LOW and MED 4: ``validate``'s warnings about labels (never a refusal):

    * two ready records that carry one sample id and every condition the same (a repeat ``SYN_01`` and ``SYN_01a``,
      say): the portal would hold two records it cannot tell apart;
    * a ready record without a label ISAAC could not propose (``not_proposed``), while nobody answered it."""
    ready = set(exportable)
    out: list[dict] = []
    seen: dict[str, list[tuple[str, Mapping]]] = {}
    for gid, draft, _ in fresh:
        fields = draft.get("fields") or {}
        if gid not in ready or SAMPLE_ID_PATH not in fields:
            continue
        key = json.dumps({p: (fields[p] or {}).get("value") for p in sorted(fields)
                          if p.split(".", 1)[0] in ("sample", "system", "context")}, sort_keys=True, default=str)
        seen.setdefault(key, []).append((gid, draft))
    from . import questions as Q

    stem_of = {r["run_key"]: str(r.get("stem")) for r in bundle.get("runs") or ()}
    first = {g["group_id"]: stem_of.get(g["member_run_keys"][0], g["group_id"]) for g in Q.live_groups(bundle)
             if g.get("member_run_keys")}
    for same in seen.values():
        if len(same) < 2:
            continue
        files = [first.get(g, g) for g, _ in same]
        sid = (same[0][1]["fields"][SAMPLE_ID_PATH] or {}).get("value")
        for gid, _ in same:
            out.append({"code": SAME_RECORD_WARNING, "group_id": gid, "path": SAMPLE_ID_PATH, "needs": SAMPLE_ID_PATH,
                        "targets": [], "command": f"isaac bundle show <bundle_dir> group {gid}",
                        "text": (f"{len(same)} ready records carry one sample id ({sid!r}) and every condition the same: "
                                 + ", ".join(files) + ". The portal cannot tell them apart. If they are repeats of one "
                                 "measurement, merge their groups; if not, give the one that differs its own label.")})
    left: dict[str, list[tuple[str, str]]] = {}
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    slots = _slot_index(bundle)
    for p in proposals(bundle):
        if p["label"] not in ("sample_id", "filter", "history") or not p["not_proposed"]:
            continue
        rq = (question_id(p["label"], RESIDUAL) if p["label"] != "history" else question_id("history", "history=unsettled"))
        if p["label"] != "history" and not p["items"]:
            rq = p["question_id"]
        for h in p["not_proposed"]:
            if h.get("group_id") in ready and h.get("run_ids") and all(
                    _answered(slots.get((p["path"], r)), decisions) is None for r in h["run_ids"]):
                left.setdefault(h["group_id"], []).append((p["label"], rq, h.get("first_file"), h.get("reason")))
    for gid, rows in left.items():
        out.append({"code": UNPROPOSED_WARNING, "group_id": gid, "path": LABELS[rows[0][0]], "needs": LABELS[rows[0][0]],
                    "targets": [],
                    "command": (f'isaac bundle decide <bundle_dir> --question {rows[0][1]} --only group:{gid} --decision '
                                'correct --value "<value>" --by "<your name>"'),
                    "text": (f"{rows[0][2]} is written without its " + " and ".join(_WHAT[r[0]] for r in rows)
                             + ": ISAAC could not propose " + ("it" if len(rows) == 1 else "them") + " ("
                             + "; ".join(f"{_WHAT[r[0]]}: {r[3]}" for r in rows) + "). Answer "
                             + ", ".join(f"question {r[1]}" for r in rows) + f" with --only group:{gid}, or leave it.")})
    return out


# --- records ------------------------------------------------------------------------------------


def take_from_fields(fields: dict, report: dict) -> dict:
    """Move the tag and the follows label out of a draft's ``fields`` (neither is a scalar field):
    ``{"tags": [..], "tags_evidence": [...], "follows": {...}}``. The electrode position (an answer about the file
    names, never a record field) is dropped."""
    out: dict[str, Any] = {}
    if fields.pop(POSITION_PATH, None) is not None:
        report["filled"] = [f for f in report["filled"] if f["path"] != POSITION_PATH]
    env = fields.pop(TAGS_PATH, None)
    if env is not None and isinstance(env.get("value"), list):
        out["tags"] = list(env["value"])
        out["tags_evidence"] = list(env.get("evidence") or ())
    env = fields.pop(FOLLOWS_PATH, None)
    if env is not None and isinstance(env.get("value"), Mapping):
        filled = next((f for f in report["filled"] if f["path"] == FOLLOWS_PATH), None)
        report["filled"] = [f for f in report["filled"] if f["path"] != FOLLOWS_PATH]
        out["follows"] = {**dict(env["value"]), "evidence": list(env.get("evidence") or ()),
                          "from": list((filled or {}).get("from") or ())}
    return out


def order_by_follows(fresh: Sequence[tuple[str, dict, dict]], run_group: Mapping[str, str]) -> list:
    """``fresh`` with every group a follows label names before the group that follows it (otherwise unchanged)."""
    by_gid = {gid: (gid, d, c) for gid, d, c in fresh}
    after: dict[str, str] = {}
    for gid, _, comp in fresh:
        f = comp.get("follows") or {}
        target = run_group.get(f.get("follows_run_key"))
        if target and target != gid and target in by_gid:
            after[gid] = target
    out, done, busy = [], set(), set()

    def visit(gid: str) -> None:
        if gid in done or gid in busy:
            return
        busy.add(gid)
        if gid in after:
            visit(after[gid])
        busy.discard(gid)
        done.add(gid)
        out.append(by_gid[gid])

    for gid, _, _ in fresh:
        visit(gid)
    return out


def follows_link(gid: str, draft: Mapping, composition: Mapping, *, run_group: Mapping[str, str],
                 drafts: Mapping[str, Mapping], minted: Mapping[str, str]) -> tuple[dict | None, list | None, str | None]:
    """``(link, evidence, why_not)`` for group ``gid``'s follows label: the link to the record of the group that
    holds the run it names, minted earlier in this export (``minted``: group -> record id). ``(None, None, why)``
    when it cannot be written; ``(None, None, None)`` when the group has no follows label."""
    f = composition.get("follows")
    if not f:
        return None, None, None
    target_gid = run_group.get(f.get("follows_run_key"))
    if target_gid is None or target_gid == gid:
        return None, None, "the run it follows is in no scientist-confirmed record group now"
    if target_gid not in minted:
        stem = str(f.get("follows_run_key") or "").split("@", 1)[0]
        return None, None, f"the record it follows ({stem}, group {target_gid}) was not exported"
    mine = ((draft.get("fields") or {}).get(SAMPLE_ID_PATH) or {}).get("value")
    theirs = (((drafts.get(target_gid) or {}).get("fields") or {}).get(SAMPLE_ID_PATH) or {}).get("value")
    if mine is None or theirs is None or mine != theirs:
        return None, None, ("the two records do not carry the same sample id (basis same_sample_id)"
                            if mine is not None and theirs is not None else
                            "both records need a confirmed sample id (basis same_sample_id)")
    basis_said = {"run_numbers": "the run numbers", "start_times": "the file-creation instants"}.get(
        f.get("order_basis"), "the run numbers")
    link = {"rel": FOLLOWS_REL, "target": minted[target_gid], "basis": FOLLOWS_BASIS,
            "notes": (f"Same sample ({mine}), measured after the target record; the order is from {basis_said}, "
                      "confirmed by a scientist.")}
    evidence = list(f.get("evidence") or ()) + [{
        "source_type": "derivation", "rule": RULE_ID,
        "statement": (f"group {gid} follows group {target_gid}: the label names run {f.get('follows_run_key')}, held "
                      f"by group {target_gid}, whose record is {minted[target_gid]}"),
        "missing_value_ids": list(f.get("from") or ())}]
    return link, evidence, None


def with_link(draft: Mapping, link: Mapping, evidence: Sequence[Mapping]) -> dict:
    out = json.loads(json.dumps(draft))
    out["links"] = [*(out.get("links") or ()), dict(link)]
    out.setdefault("block_evidence", {})[f"links:{link['rel']}|{link['target']}|{link['basis']}"] = list(evidence)
    return out


def order_records_by_links(paths: Sequence[Any], links_of: Mapping[str, Sequence[str]]) -> list:
    """Record files with each link's target before the record that links to it (otherwise in the given order):
    the portal looks a link's target up in the records it already holds."""
    by_id = {p.name[: -len(".json")]: p for p in paths}
    out, done, busy = [], set(), set()

    def visit(rid: str) -> None:
        if rid in done or rid in busy or rid not in by_id:
            return
        busy.add(rid)
        for t in links_of.get(rid) or ():
            visit(t)
        busy.discard(rid)
        done.add(rid)
        out.append(by_id[rid])

    for p in paths:
        visit(p.name[: -len(".json")])
    return out

