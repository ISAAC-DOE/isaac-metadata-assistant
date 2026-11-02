"""Condition labels: the record fields that tell apart records ISAAC keeps apart by condition. Stdlib only.

WHY
===

Grouping splits runs into records by the conditions their files state (``grouping.CONDITION_KEYS``): the
electrode, the filter, the cycling history. Before this module no record field carried them, so records of one
material at one potential exported with the same body and looked like duplicates on the portal. This module
PROPOSES five labels from the readings the grouping already used, and a scientist decides each one. Nothing is
written without a scientist decision. No schema changes:

* ``sample.sample_id`` — the schema: "Stable identifier of the PHYSICAL sample/electrode. Two records share a
  sample_id iff they measured the same physical object." Proposed from the reading the grouping takes as the
  electrode or sample-instance number (``sample_or_electrode_number``, the second number of a BL15-2 file name,
  DEC-47), one id per electrode. Not proposed when the grouping found that number is not a sample identity here
  (it then sits in the group basis's ``unclassified`` part), when a ``set_counter_positions`` answer names its
  position as a run counter, or when one number is read beside two sample names: the files then do not establish
  the electrode, so the question says so and asks.
* ``system.configuration.beam_attenuator`` — the schema's open namespace for beamline settings, under the key the
  portal's pinned vocabulary lists for it (its allowed flat keys name ``beam_attenuator`` and no ``filter``). The
  value is ``filter<n>``: the filter number the stored rules read (``bl15.filenames.filter_count.v1``: ``filter10``,
  ``f10`` and ``Filter10`` state filter 10; the scan header's ``filter`` motor states the same number), written in
  the file names' own form. Proposed only where every reading agrees.
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
  follows "after 1200", for one electrode under otherwise equal conditions. The order comes from the run numbers
  (or, where those overlap or are missing, the file-creation instants the files state, SPEC ``#E``). A link
  needs its target's record id, which the export mints. So a decision records which RUN a group follows, and
  the export resolves it to that run's record id, exporting the earlier record first
  (:func:`order_by_follows`). The id is part of the later record's body: when the earlier record gets a new id,
  the later one does too. A link is written only when both records carry the same ``sample.sample_id``.
* ``tags`` — one lowercase hyphenated tag per beamtime, proposed from the folder name.

HOW AN ANSWER IS KEPT
=====================

As a per-run ``missing_values`` entry, a LABEL SLOT (:func:`is_label_slot`), with a ``confirm``, ``correct`` or
``reject`` decision on it (the tag: one beamtime-level slot). Only bundle sections and decision kinds that
already exist are used, so the bundle format is unchanged. A label slot's eligibility is derived here
(:func:`slot_eligibility`): a scientist-confirmed value its label can hold. The writable set of every other
candidate and missing value is unchanged, so no stored eligibility moves.

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
LABEL_PATHS = (SAMPLE_ID_PATH, FILTER_PATH, HISTORY_PATH, FOLLOWS_PATH, TAGS_PATH)
#: label name -> path
LABELS = {"sample_id": SAMPLE_ID_PATH, "filter": FILTER_PATH, "history": HISTORY_PATH,
          "follows": FOLLOWS_PATH, "tag": TAGS_PATH}
LABEL_OF_PATH = {v: k for k, v in LABELS.items()}

FOLLOWS_REL, FOLLOWS_BASIS = "follows", "same_sample_id"
#: What each question takes (``decide --question``).
DECISIONS = {"sample_id": ("confirm", "correct", "reject"), "filter": ("confirm", "correct", "reject"),
             "history": ("confirm", "correct", "reject"), "follows": ("confirm", "reject"),
             "tag": ("confirm", "correct", "reject")}
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

SLOT_LEAD = "A condition label ISAAC proposed from the files and a scientist answered (question "
SLOT_REASON = SLOT_LEAD + "{question}, rule " + RULE_ID + "): {what}."
_SLOT_QUESTION = re.compile(re.escape(SLOT_LEAD) + r"(Q-[0-9a-f]{10})")

NOT_WRITTEN_FOLLOWS = "Written without its follows link: {why}."


# --- slots --------------------------------------------------------------------------------------


def is_label_slot(m: Mapping) -> bool:
    """A missing value this module added to hold one run's (or, for the tag, the beamtime's) label answer."""
    return m.get("target_field_path") in LABEL_PATHS and str(m.get("reason") or "").startswith(SLOT_LEAD)


def slot_question(m: Mapping) -> str | None:
    hit = _SLOT_QUESTION.match(str(m.get("reason") or "")) if is_label_slot(m) else None
    return hit.group(1) if hit else None


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


class _Facts:
    """What one live group's basis and runs state, read once."""

    __slots__ = ("gid", "runs", "keys", "electrode", "position", "sample", "filter", "filter_said", "filter_from",
                 "history", "history_canon", "why_not", "interval", "order_basis", "chain_key", "cond_key", "loose_key",
                 "full_key", "stems")

    def __init__(self, gid: str):
        self.gid = gid
        self.runs: list[str] = []
        self.keys: list[str] = []
        self.stems: list[str] = []
        self.electrode = self.position = self.sample = self.filter = self.history = self.history_canon = None
        self.filter_said: list[str] = []
        self.why_not: dict[str, str] = {}
        self.interval = self.order_basis = self.chain_key = self.cond_key = self.loose_key = self.full_key = None
        self.filter_from: set[str] = set()


def _facts(bundle: Mapping, groups: Sequence[Mapping]) -> list[_Facts]:
    from . import grouping as G

    runs_by_key = {r["run_key"]: r for r in bundle.get("runs") or ()}
    cands = {c["candidate_id"]: c for c in bundle.get("candidates") or ()}
    context = B.context_run_ids(bundle)
    counter = G.counter_positions_decision(bundle)
    cpos = list((counter or {}).get("positions") or ())
    exempt = (G.last_counter_exempt(r.get("stem") or "" for r in bundle.get("runs") or ())
              if G.LAST_POSITION in cpos else frozenset())
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

        # THE ELECTRODE: the reading the grouping took as the sample identity (basis.sample), never one it set aside
        el = _basis(g, "sample", "sample_or_electrode_number")
        raw_el = _part(g, "sample").get("sample_or_electrode_number")
        if el is None:
            f.why_not["sample_id"] = (
                "the files' electrode readings disagree" if isinstance(raw_el, Mapping)
                else "the grouping set the sample number aside here (it is read beside several sample names)"
                if _part(g, "unclassified").get("sample_or_electrode_number")
                else "the file names state no electrode or sample-instance number")
        else:
            lits = {x.casefold() for x in written("sample_or_electrode_number")}
            positions = set()
            for rid in f.runs:
                for c in own.get(rid, {}).get("sample_or_electrode_number", ()):
                    for e in c.get("evidence") or ():
                        hit = _FILENAME_TOKEN.match(str(e.get("locator") or ""))
                        if hit and _own_name(e, stem_of[rid]):
                            start = int(hit.group(2)) if hit.group(2) is not None else None
                            positions.add((rid, _grouping_position(stem_of[rid], int(hit.group(1)), start)))
            pos = {p for _, p in positions}
            counted = sorted({p for rid, p in positions
                              if p in set(G.stem_counter_positions(stem_of[rid], cpos, exempt))
                              or (G.LAST_POSITION in G.stem_counter_positions(stem_of[rid], cpos, exempt)
                                  and p == len(G._stem_tokens(stem_of[rid])))})
            names = {x for x in written("sample_name")}
            if len(lits) > 1:
                f.why_not["sample_id"] = "the files' electrode readings disagree"
            elif len(lits) != 1 or len(pos) != 1:
                f.why_not["sample_id"] = "its runs' file names do not state one electrode number at one position"
            elif counted:
                f.why_not["sample_id"] = (f"the number sits at file-name position {counted[0]}, which a set_counter_positions "
                                          "answer names as a run counter")
            elif len({n.casefold() for n in names}) != 1:
                f.why_not["sample_id"] = "its runs' file names do not state one sample name"
            else:
                f.electrode = written("sample_or_electrode_number")[0]
                f.position = next(iter(pos))
                f.sample = sorted(names)[0]
        # THE FILTER: the number every reading of the group states (bl15.filenames.filter_count.v1, the header motor)
        fr = _basis(g, "conditions", "filter")
        if fr is None:
            f.why_not["filter"] = ("the files' filter readings disagree" if _part(g, "conditions").get("filter")
                                   else "the files state no filter")
        else:
            nums = {filter_number(v) for v in _values(fr)}
            if len(nums) != 1 or None in nums:
                f.why_not["filter"] = "the files' filter readings do not state one number"
            else:
                f.filter = next(iter(nums))
                f.filter_said = sorted({x for x in written("filter")})
                for rid in f.runs:
                    for c in own.get(rid, {}).get("filter", ()):
                        for e in c.get("evidence") or ():
                            loc = str(e.get("locator") or "")
                            f.filter_from.add("file name" if loc.startswith("filename") else
                                              "scan header" if "header" in loc else "other")
        # THE HISTORY: each run's own file-name token, as written
        hr = _basis(g, "conditions", "cycling_state")
        if hr is None:
            f.why_not["history"] = ("the files' cycling readings disagree" if _part(g, "conditions").get("cycling_state")
                                    else "the file names state no cycling history")
        else:
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
        # THE ORDER: run numbers, else the instants the files state (#E)
        nums = [runs_by_key[k].get("legacy_number") for k in f.keys]
        if all(isinstance(n, int) and not isinstance(n, bool) for n in nums):
            f.interval, f.order_basis = (min(nums), max(nums)), "run_numbers"
        else:
            epochs = []
            for rid in f.runs:
                got = [str(c["observed_literals"][0]) for c in own.get(rid, {}).get("acquisition_epoch", ())
                       if c.get("observed_literals") and c.get("extracted_state") != B.STATE_CONFLICTING]
                epochs.append(int(got[0]) if len(got) == 1 and got[0].isdigit() else None)
            if epochs and None not in epochs:
                f.interval, f.order_basis = (min(epochs), max(epochs)), "start_times"
        # THE KEYS conditions are compared by (normalised, r review M3): without the history (one electrode's stages),
        # also without the electrode (a group whose electrode is not settled), and in full (repeats of one condition)
        norm = _normalised(g)  # read once; each key leaves out its own readings
        f.full_key = json.dumps(norm, sort_keys=True)
        cond = {k: v for k, v in norm.items() if k.rsplit(".", 1)[-1] not in HISTORY_KEYS}
        f.loose_key = json.dumps({k: v for k, v in cond.items() if k.rsplit(".", 1)[-1] != "sample_or_electrode_number"},
                                 sort_keys=True)
        if f.electrode is not None:
            f.cond_key = json.dumps(cond, sort_keys=True)
            if f.history is not None:
                f.chain_key = f.cond_key
        out.append(f)
    return out


def _chains(facts: Sequence[_Facts]) -> tuple[list[list[_Facts]], list[dict]]:
    """Groups of one electrode under otherwise equal conditions, at different history stages, in time order."""
    by_key: dict[str, list[_Facts]] = {}
    for f in facts:
        if f.chain_key is not None and f.history is not None:
            by_key.setdefault(f.chain_key, []).append(f)
    chains, held = [], []
    for members in by_key.values():
        if len(members) < 2:
            continue
        stems = [m.stems[0] for m in members]
        if len({m.history_canon for m in members}) != len(members):
            held.append({"group_ids": [m.gid for m in members], "first_files": stems[:3],
                         "reason": "two of these groups are at the same history stage"})
            continue
        bases = {m.order_basis for m in members}
        if None in bases or len(bases) != 1:
            held.append({"group_ids": [m.gid for m in members], "first_files": stems[:3],
                         "reason": "their run numbers (or file-creation instants) do not order them"})
            continue
        ordered = sorted(members, key=lambda m: m.interval)
        if any(a.interval[1] >= b.interval[0] for a, b in zip(ordered, ordered[1:])):
            held.append({"group_ids": [m.gid for m in members], "first_files": stems[:3],
                         "reason": "their run numbers (or file-creation instants) overlap"})
            continue
        sides = [m.history_canon.startswith("before") for m in ordered]
        if any(not a and b for a, b in zip(sides, sides[1:])):
            held.append({"group_ids": [m.gid for m in members], "first_files": stems[:3],
                         "reason": "a 'before' measurement comes after an 'after' one in time"})
            continue
        # r review M3: ANOTHER GROUP OF THIS ELECTRODE UNDER THESE CONDITIONS WITH NO SETTLED STAGE, or a group of these
        # conditions whose electrode is not settled measured between them: either may be the stage in between
        lo, hi = ordered[0].interval[0], ordered[-1].interval[1]
        gap = [f for f in facts if f not in members and (
            (f.cond_key == members[0].cond_key and f.chain_key is None)
            or (f.cond_key is None and f.loose_key == members[0].loose_key and f.interval is not None
                and f.order_basis == members[0].order_basis and lo < f.interval[0] < hi))]
        if gap:
            held.append({"group_ids": [m.gid for m in members], "first_files": stems[:3],
                         "reason": (f"group {gap[0].gid} ({gap[0].stems[0]}) has these conditions but no settled "
                                    "history stage or electrode, so the order of stages is not certain")})
            continue
        chains.append(ordered)
    chains.sort(key=lambda c: c[0].interval)
    return chains, held


# --- proposals and questions --------------------------------------------------------------------


def _qid(*parts: str) -> str:
    from . import questions as Q

    return Q._qid("experiment", KIND, *parts)


def question_id(label: str, partition: str | None = None) -> str:
    return _qid(LABELS[label], *([partition] if partition else []))


def _fill_sample_id(pattern: str, fill: Mapping[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: str(fill[m.group(1)]), pattern)


def proposals(bundle: Mapping, groups: Sequence[Mapping] | None = None) -> list[dict]:
    """One entry per question: ``{label, partition, path, items: [{group_id, run_ids, value, fill, said}],
    not_proposed: [...], ...}``. Every value a proposal; nothing here is recorded."""
    from . import questions as Q

    groups = Q.live_groups(bundle) if groups is None else groups
    facts = _facts(bundle, groups)
    beamtime = beamtime_label(bundle)
    out: list[dict] = []
    # sample ids: one per electrode; an electrode read beside two sample names (or a name with two ids) is asked
    objects: dict[str, set[str]] = {}
    for f in facts:
        if f.electrode is not None:
            objects.setdefault(f.electrode.casefold(), set()).add(f.sample.casefold())
    items, held = [], []
    for f in facts:
        if f.electrode is None:
            held.append(_held(f, f.why_not.get("sample_id")))
        elif len(objects[f.electrode.casefold()]) > 1:
            held.append(_held(f, f"electrode number {f.electrode} is read beside more than one sample name"))
        elif beamtime is None:
            held.append(_held(f, "the beamtime folder has no name"))
        else:
            fill = {"beamtime": beamtime, "sample": f.sample, "electrode": f.electrode}
            items.append({"group_id": f.gid, "run_ids": list(f.runs), "object": f.electrode.casefold(),
                          "value": _fill_sample_id(SAMPLE_ID_CONVENTION, fill), "fill": fill,
                          "said": {"electrode": f.electrode, "position": f.position, "sample": f.sample},
                          "first_file": f.stems[0]})
    items, more = _said_not_counter(bundle, facts, items)
    held += more
    if items or held:
        out.append({"label": "sample_id", "partition": None, "items": items, "not_proposed": held})
    items, held = [], []
    for f in facts:
        if f.filter is None:
            if f.why_not.get("filter") != "the files state no filter":
                held.append(_held(f, f.why_not.get("filter")))
            continue
        items.append({"group_id": f.gid, "run_ids": list(f.runs), "value": f"filter{f.filter}", "fill": {"filter": f.filter},
                      "said": {"literals": f.filter_said, "from": sorted(f.filter_from)}, "first_file": f.stems[0]})
    if items or held:
        out.append({"label": "filter", "partition": None, "items": items, "not_proposed": held})
    by_history: dict[str, list[dict]] = {}
    held_h = []
    for f in facts:
        if f.history is None:
            if f.why_not.get("history") != "the file names state no cycling history":
                held_h.append(_held(f, f.why_not.get("history")))
            continue
        by_history.setdefault(f.history_canon, []).append(
            {"group_id": f.gid, "run_ids": list(f.runs), "value": history_words(f.history), "fill": {},
             "said": {"token": f.history}, "first_file": f.stems[0]})
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
        for before, after in zip(chain, chain[1:]):
            items.append({"group_id": after.gid, "run_ids": list(after.runs),
                          "value": {"rel": FOLLOWS_REL, "basis": FOLLOWS_BASIS, "follows_run_key": before.keys[0],
                                    "order_basis": after.order_basis},
                          "fill": {}, "said": {"after": after.stems[0], "before": before.stems[0],
                                               "before_group_id": before.gid, "order_basis": after.order_basis,
                                               "before_interval": list(before.interval),
                                               "after_interval": list(after.interval)},
                          "first_file": after.stems[0]})
    if items:
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


def _held(f: _Facts, reason: str | None) -> dict:
    return {"group_id": f.gid, "run_ids": list(f.runs), "first_file": f.stems[0], "reason": reason}


def _slot_index(bundle: Mapping) -> dict[tuple[str, str | None], Mapping]:
    """``(path, run_id) -> label slot`` (the tag's run_id is ``None``)."""
    return {(m["target_field_path"], m.get("run_id")): m for m in bundle.get("missing_values") or () if is_label_slot(m)}


def _answered(slot: Mapping | None, decisions: Mapping) -> Mapping | None:
    if slot is None:
        return None
    d = decisions.get(("missing_value", slot["value_id"]))
    return d if d is not None and d.get("decision") not in B.NEUTRAL_DECISIONS else None


def _text(p: Mapping, n_groups: int, n_runs: int) -> str:
    items, label = p["items"], p["label"]
    ex = items[:3]
    if label == "sample_id":
        first: dict[str, Mapping] = {}
        for i in items:
            first.setdefault(i["object"], i)
        n_obj, ex = len(first), list(first.values())[:3]
        text = (f"Sample ids for {n_obj} physical sample(s) ({n_groups} group(s), {n_runs} run(s)). ISAAC reads the "
                "number the grouping takes as the electrode or sample-instance number (sample_or_electrode_number, file-"
                f"name position {ex[0]['said']['position']}) and proposes one id per electrode, scoped to this "
                f"beamtime folder: " + "; ".join(f"electrode {i['said']['electrode']} ({i['first_file']}) -> "
                                                f"{i['value']!r}" for i in ex)
                + (f"; and {n_obj - len(ex)} more." if n_obj > len(ex) else ".")
                + " A sample id names one physical object and must be the same on every record of it. Confirm to "
                "record these ids, or give your own convention with --decision correct --value, using {electrode}, "
                "{sample} and {beamtime} (e.g. \"{sample}-e{electrode}\"). If this electrode was measured in another "
                "beamtime too, give the id used there.")
    elif label == "filter":
        n_val = len({json.dumps(i["value"]) for i in items})
        def source(i: Mapping) -> str:
            got = set((i.get("said") or {}).get("from") or ())
            return ("file name and scan header" if {"file name", "scan header"} <= got else
                    "file name" if "file name" in got else
                    f"the scan header's filter motor reads {i['fill']['filter']}" if "scan header" in got else "files")
        text = (f"The filter for {n_groups} group(s) ({n_runs} run(s)), into system.configuration.beam_attenuator (the "
                "portal vocabulary's key for it): the filter number a file name (rule bl15.filenames.filter_count.v1) "
                f"or the scan headers' filter motor states, written filter<n> ({n_val} value(s)). "
                + "; ".join(f"{i['first_file']} -> {i['value']!r} ({source(i)})" for i in ex)
                + (f"; and {len(items) - len(ex)} more groups." if len(items) > len(ex) else ".")
                + " Confirm to record these, or give your own form with --decision correct --value, using {filter} "
                "for the number (e.g. \"Al filter {filter}\").")
    elif label == "history":
        text = (f"The sample's cycling history for {n_groups} group(s) ({n_runs} run(s)) whose file names write "
                f"{p['token']!r}, into context.electrochemistry.notes. Proposed wording: {items[0]['value']!r}. It only "
                "splits the file-name token into words; it does not say what the number is (millivolts or cycles). "
                "Confirm it, or give your own sentence with --decision correct --value \"<sentence>\".")
    elif label == "follows":
        text = (f"Links between records of the same sample measured in sequence ({len(items)} link(s) in "
                f"{len(p.get('chains') or ())} chain(s)). For one electrode under otherwise equal conditions, each "
                "later history stage follows the one before it, in the order of the run numbers (or, where those do "
                "not order them, the file-creation instants the files state): "
                + "; ".join(f"{i['said']['after']} follows {i['said']['before']}" for i in ex)
                + (f"; and {len(items) - len(ex)} more." if len(items) > len(ex) else ".")
                + " Each link goes into the later record (rel follows, basis same_sample_id), only when both records "
                "carry the same sample id. Confirm to record them, or reject.")
    else:
        text = (f"One tag for every record of this beamtime, from the folder name {ex[0]['said']['folder']!r}: "
                f"{ex[0]['value'][0]!r}. Confirm it, or give your own with --decision correct --value (lowercase, "
                "hyphenated, at most 64 characters).")
    return text


def _runs_of(path: str, item: Mapping) -> list:
    return list(item["run_ids"]) if path != TAGS_PATH else [None]


def label_questions(bundle: Mapping, *, decisions: Mapping | None = None, groups: Sequence[Mapping] | None = None,
                    include_answered: bool = False) -> list[dict]:
    """The consolidated condition-label questions. A question drops out of the open list once every group it
    PROPOSES a value for holds an answer (``include_answered`` keeps it, with ``answered: true``); the groups it
    could not propose for (``not_proposed``) stay answerable with ``--only group:<id>``. The one question that
    proposes nothing (``history=unsettled``) is open while one of its groups holds no answer."""
    from . import questions as Q

    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ()) if decisions is None else decisions
    slots = _slot_index(bundle)

    def answered(path: str, item: Mapping) -> bool:
        return all(_answered(slots.get((path, r)), decisions) is not None for r in _runs_of(path, item))

    out = []
    for p in proposals(bundle, groups):
        path = p["path"]
        open_items = [i for i in p["items"] if not answered(path, i)]
        open_held = [h for h in p["not_proposed"] if h.get("run_ids") and not answered(path, h)]
        is_open = bool(open_items) or (not p["items"] and bool(open_held))
        if not is_open and not include_answered:
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
                    "--value \"<value>\", or reject it.")
        if done and not include_answered:
            text += f" {done} group(s) hold an answer already and are not asked again."
        if held:
            text += (f" Not proposed for {len(held)} group(s): "
                     + "; ".join(f"{h.get('first_file') or ', '.join(h.get('first_files') or ())}: {h['reason']}"
                                 for h in held[:3])
                     + ("; …" if len(held) > 3 else "") + " (not_proposed)."
                     + (" Answer one with --only group:<id> --decision correct --value <value>, or leave it."
                        if p["label"] != "follows" else " Those are not linked."))
        allowed = list(DECISIONS[p["label"]]) if shown else ["correct", "reject"]
        targets = ([{"kind": "experiment", "id": "experiment"}] if path == TAGS_PATH else
                   [{"kind": "run", "id": r} for r in runs + (held_runs if not shown else [])])
        q = {
            "question_id": qid,
            "partition": p["partition"],
            "tier": Q.TIER_OPTIONAL,
            "blocking": False,
            "affects_record": True,
            "why": ("Optional: a label that tells this beamtime's records apart (without it, records of one sample at one "
                    "potential can share one body). Proposed from the files; nothing is written until a scientist answers."),
            "kind": KIND,
            "label": p["label"],
            "scope": "experiment",
            "target_field_path": path,
            "text": text,
            "applies_to": {"groups": groups_n if shown or path == TAGS_PATH else len(held),
                           "runs": len(runs) if shown else len(held_runs), "targets": len(targets)},
            "targets": targets,
            "per_scope_targets": ({"experiment": ["experiment"]} if path == TAGS_PATH else
                                  {f"group:{i['group_id']}": list(i["run_ids"]) for i in (shown or held)}),
            "proposals": [{k: i[k] for k in ("group_id", "run_ids", "value", "said", "first_file", "fill", "object")
                           if k in i} for i in shown],
            "not_proposed": [dict(h) for h in held],
            "hints": [{"kind": "label_proposal", "literal": i["value"] if not isinstance(i["value"], list) else i["value"][0],
                       "group_id": i["group_id"], "first_file": i["first_file"], "rule_id": RULE_ID}
                      for i in shown[:5] if p["label"] != "follows"],
            "allowed_values": None,
            "allowed_decisions": allowed,
            "answer_command": ((f'isaac bundle decide <bundle_dir> --question {qid} --decision confirm --by "<your name>"'
                                "   # one group only: add --only group:<group_id>") if shown else
                               (f'isaac bundle decide <bundle_dir> --question {qid} --only group:<group_id> '
                                '--decision correct --value "<sentence>" --by "<your name>"')),
            "rule_id": RULE_ID,
        }
        if include_answered:
            q["answered"] = not is_open
            q["answered_groups"] = done
        out.append(q)
    return out


def question_by_id(bundle: Mapping, qid: str) -> dict | None:
    """The label question ``qid`` (open or answered), or ``None`` when ``qid`` is not one."""
    return next((q for q in label_questions(bundle, include_answered=True) if q["question_id"] == qid), None)


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


def _values_for(asked: Mapping, items: Sequence[Mapping], decision: str, value: Any) -> dict[str, Any]:
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
    if label == "sample_id":
        by_value: dict[str, set] = {}
        for i in items:
            by_value.setdefault(out[i["group_id"]], set()).add(_object(i) or i["group_id"])
        clash = [v for v, objs in by_value.items() if len(objs) > 1]
        if clash:
            raise LabelRefused(f"--value {value!r} gives two physical samples the same id ({clash[0]!r}): a sample id "
                               "names one object. Put {electrode} in it. Nothing was recorded.")
    return out


def decide(bundle: dict, asked: Mapping, *, decision: str, value: Any, only: str | None, by: str,
           orcid: str | None, note: str | None, same_sample: bool = False) -> dict:
    """``decide --question`` on a label question, under the caller's lock, on ``bundle`` in memory (the caller
    saves). ``confirm`` records the proposed values; ``correct`` records the scientist's value (for ids and filters a
    pattern, ``{electrode}`` / ``{filter}``); ``reject`` records that the label is not written.

    WITHOUT ``--only`` an answer writes ONLY slots that hold no answer yet: a run already answered keeps its answer,
    and a group whose answered runs hold another value than this answer gives is left out whole and named
    (``kept``), never overwritten. ``--only group:<id>`` answers that one group (its answered runs too: the scientist
    named it), and also a group ISAAC proposed nothing for (``correct`` or ``reject`` only). A sample id given for
    one group is the electrode's: it is recorded for every group of that electrode.

    A SAMPLE ID NAMES ONE PHYSICAL OBJECT. Refused when runs of another electrode hold (or are proposed) the id. A
    group ISAAC could not place (``not_proposed``) takes an id other runs hold or are proposed only with
    ``same_sample``: the scientist's statement that it is the same physical sample, said in the reply and the
    decision's note. A later bulk answer that gives an electrode the id such a group holds is recorded and names it
    (``shares_id_with``). One decision per run's slot, through :func:`mutations.record_decision`."""
    from . import mutations as M

    qid, path, label = asked["question_id"], asked["target_field_path"], asked["label"]
    if decision not in DECISIONS[label] or (decision == "confirm" and not asked["proposals"]):
        raise LabelRefused(f"`{decision}` does not answer question {qid} ({KIND}); use one of: "
                           f"{', '.join(asked['allowed_decisions'])}. Nothing was recorded.")
    if same_sample and (label != "sample_id" or only is None or decision != "correct"):
        raise LabelRefused("--same-sample goes with the sample-id question, --only group:<id> and --decision correct "
                           "--value <id>. Nothing was recorded.")
    full = {i["group_id"]: i for i in asked["proposals"]}
    held = {h["group_id"]: {**h, "value": None, "said": {}, "fill": {}} for h in asked.get("not_proposed") or ()
            if h.get("group_id") and h.get("run_ids")}
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    slots = _slot_index(bundle)

    def answer_of(rid: Any) -> Mapping | None:
        return _answered(slots.get((path, rid)), decisions)

    if only is not None:
        gid = only[len("group:"):] if only.startswith("group:") else None
        if label == "tag" or gid is None or (gid not in full and gid not in held):
            raise LabelRefused(f"Question {qid} has no group {only!r}"
                               + (" (it is asked once for the beamtime: answer it without --only)" if label == "tag" else "")
                               + ". Nothing was recorded.")
        if gid in held and (decision == "confirm" or label == "follows"):
            raise LabelRefused(f"ISAAC proposed nothing for group {gid} ({held[gid]['reason']}), so there is nothing to "
                               "confirm" + (": it is not linked." if label == "follows" else
                                            "; give the value with --decision correct --value <value>.")
                               + " Nothing was recorded.")
        items = [full.get(gid) or held[gid]]
        if label == "sample_id" and decision == "correct" and _object(items[0]) is not None:
            # AN ID IS THE OBJECT'S: given for one group, it is recorded for every group of that electrode
            items = [i for i in asked["proposals"] if _object(i) == _object(items[0])]
    else:
        items = list(asked["proposals"])
        if not items:
            raise LabelRefused(f"Question {qid} proposes nothing: answer each group with --only group:<id> "
                               "--decision correct --value <value>. Nothing was recorded.")
    values = _values_for(asked, items, decision, value)
    for v in values.values():
        if v is not None and (problem := label_value_problem(path, v)) is not None:
            raise LabelRefused(f"{problem}; {v!r} cannot be the label. Nothing was recorded.")
    # WHICH SLOTS THIS ANSWER WRITES (r: never an earlier answer, unless --only names its group)
    kept: list[dict] = []
    write: list[tuple[dict, list]] = []
    for i in items:
        runs = _runs_of(path, i)
        if only is not None:
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
                         "decision_id": d.get("decision_id"), "holds": d.get("value") if d.get("decision") != "reject" else None,
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
        obj_of_run = {r: _object(i) for i in asked["proposals"] for r in i["run_ids"]}
        # who holds each id now (an answer), or is proposed it (a proposal not yet answered)
        holders: dict[str, list[tuple[Any, str, str]]] = {}
        for (p, rid), m in slots.items():
            d = _answered(m, decisions)
            if p == SAMPLE_ID_PATH and rid not in mine and d is not None and d.get("decision") != "reject":
                holders.setdefault(json.dumps(d.get("value")), []).append((obj_of_run.get(rid), rid, "holds"))
        if only is not None:
            for i in asked["proposals"]:
                if answer_of(i["run_ids"][0]) is None and not set(i["run_ids"]) & mine:
                    holders.setdefault(json.dumps(i["value"]), []).append((_object(i), i["run_ids"][0], "is proposed"))
        for i, _ in write:
            v, me = values[i["group_id"]], _object(i)
            for other, rid, how in holders.get(json.dumps(v), ()):
                if me is not None and other is not None:
                    if me != other:
                        raise LabelRefused(f"{v!r} {'is already' if how == 'holds' else 'is proposed as'} the sample id of "
                                           f"electrode {other} (run {rid}): a sample id names one physical object. "
                                           "Nothing was recorded.")
                    continue
                if only is not None and not same_sample:
                    raise LabelRefused(
                        f"Run {rid} {'already holds' if how == 'holds' else 'is proposed'} {v!r}, and ISAAC does not "
                        f"read group {i['group_id']} as that electrode ({(held.get(i['group_id']) or {}).get('reason') or 'its electrode is not settled'}). "
                        "A sample id names one physical object. If the scientist says it IS the same physical sample, "
                        "add --same-sample; otherwise give it another id. Nothing was recorded.")
                if only is not None:
                    joined.append({"group_id": i["group_id"], "with_run": rid, "value": v})
                else:
                    shares.append({"group_id": i["group_id"], "with_run": rid, "value": v})
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
        said += (" The scientist stated this group is the same physical sample as run "
                 + ", ".join(sorted({j["with_run"] for j in joined})) + " (--same-sample).")
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
        statement += (f" Recorded as the same physical sample as run {joined[0]['with_run']} ({joined[0]['value']!r}), "
                      "as the scientist stated (--same-sample).")
    if shares:
        statement += (" " + "; ".join(f"group {x['group_id']} now shares {x['value']!r} with run {x['with_run']}, which a "
                                      "scientist gave that id on its own" for x in shares[:3])
                      + ": they are one physical sample in the records. If they are not, give one of them another id "
                      "with --only group:<id>.")
    if kept:
        statement += " " + _kept_sentence(qid, kept)
    return {"statement": statement, "question_id": qid, "label": label, "path": path,
            "groups_recorded": len(groups), "slots_recorded": recorded, "slots_unchanged": unchanged,
            "values": [value_of[k] for k in list(value_of)[:5]], "values_total": len(value_of),
            **({"kept": kept} if kept else {}), **({"same_sample": joined} if joined else {}),
            **({"shares_id_with": shares} if shares else {})}


def _kept_sentence(qid: str, kept: Sequence[Mapping], nothing: bool = False) -> str:
    """The groups an answer left out because some of their runs already hold another answer."""
    shown = "; ".join(f"group {k['group_id']} ({k.get('first_file')}): run {k['run_id']} holds "
                      + (f"{k['holds']!r}" if k.get("holds") is not None else f"a {k['decision']}")
                      + f" ({k['decision_id']})" for k in kept[:3]) + ("; …" if len(kept) > 3 else "")
    return ((f"Nothing was recorded: " if nothing else f"Left out {len(kept)} group(s) whose runs already hold another "
             "answer, never overwritten: ") + shown + f". To change one, answer question {qid} with --only group:<id>.")


# --- records ------------------------------------------------------------------------------------


def take_from_fields(fields: dict, report: dict) -> dict:
    """Move the tag and the follows label out of a draft's ``fields`` (neither is a scalar field):
    ``{"tags": [..], "tags_evidence": [...], "follows": {...}}``."""
    out: dict[str, Any] = {}
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
        return None, None, f"the record it follows (group {target_gid}) was not exported"
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

