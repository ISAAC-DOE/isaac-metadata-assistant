"""THE QUESTION SITE, export half: a bundle's open questions as plain CARDS (``isaac bundle site export``).

A scientist answers a bundle's questions on a small hosted site, a few at a time: yes / no, pick an option, or type.
This module writes what that site shows, ``<out>/data/site-data.json`` and ``<out>/data/img/<sha256>.<ext>``, to the
contract in ``docs/question-site-contract.md``. ``question_site_import.py`` reads the site's answers back.

ONE CARD PER REAL ASK (:func:`_units`). The consolidated questions (``questions.py``) are joined by their OWN
structure, never by their wording:

* questions that share a ``same_reading_group`` are one card, answered by ONE ``decide --question <first id>
  --same-reading`` (the decide path answers every open question of the group);
* a question asked once for several groups whose honest answers could differ (its files name no sample:
  ``partition == "sample=unrecorded"``; or answers already given for the field differ: ``answers_differ``) is one
  card PER GROUP, each answered with ``only_scopes`` = that group;
* an optional-values question is one card per field (``--field``);
* every other question is its own card. Questions about different sample tokens or different fields are never one
  card.

A CARD IS ANSWERABLE BY THE CALLS IT LISTS (``covers``). Each call is checked at export time by a DRY RUN through
``mutations.decide_question`` / ``mutations.decide`` on a temporary copy of ``bundle.json`` (:func:`_verify`): the
"I don't know" call proves the question resolves to targets, a suggestion's accept call proves the suggestion is a
value the field takes, and a choice card's first option proves a picked value is recorded. A question no call can
answer is left out and counted. A beamtime-wide blocking card is also SIMULATED on its own copy (:func:`_settles`):
the blocking questions its answer settles are left out, so the same thing is not asked twice.

PLAIN WORDS ONLY (``plain_questions.py``): a card's title and detail never carry a field path, a decision name or a
flag (checked: a card that would is left out). A question kind with no plain wording is left out and counted.

A SUGGESTION IS A HINT and says where it came from: a value the files give (``basis: files``), an earlier answer
from the opt-in answer memory, an AI reading with its quote, a rule's proposal, or an entry of ``--suggestions``.
Nothing is chosen for the scientist; "accept" on the site records their decision, not the hint's.

THE BUNDLE IS READ, AND ITS EXPOSURE LOG IS WRITTEN: the parser values the cards show are recorded in ``exposures``
under :data:`EXPOSURE_COMMAND`, as ``bundle questions`` records the ones it prints. No decision, value or question
changes. ``--out`` must be outside every git working tree and outside the bundle folder: it holds real data.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B
from . import plain_questions as P
from . import question_site_hints as H

FORMAT_ID = "isaac.question_site"
FORMAT_VERSION = "1.0.0"
SUGGESTIONS_FORMAT_ID = "isaac.question_site_suggestions"
EXPOSURE_COMMAND = "bundle site export"

EXIT_USAGE = 2
EXIT_INPUT_REFUSED = 3
EXIT_OUTPUT_REFUSED = 4
EXIT_NOT_FOUND = 6

#: the sections of the site, in display order (the contract's)
SECTIONS = (
    {"id": "beamtime", "title": "About the whole beamtime", "blurb": "One answer covers every record."},
    {"id": "samples", "title": "About each sample", "blurb": "One answer covers every measurement of that sample."},
    {"id": "records", "title": "About single measurements", "blurb": ""},
    {"id": "processing", "title": "Processing", "blurb": "How the spectra were merged."},
    {"id": "optional", "title": "Nice to have", "blurb": "Not needed to export, but makes the records more useful."},
)
_SECTION_ORDER = {s["id"]: n for n, s in enumerate(SECTIONS)}

#: what ``--include`` adds to the default export (blocking questions and the dose question)
INCLUDE_OPTIONAL = "optional"
INCLUDE_DEFERRED = "deferred"
INCLUDE_APPROVALS = "approvals"
INCLUDES = (INCLUDE_OPTIONAL, INCLUDE_DEFERRED, INCLUDE_APPROVALS)

#: the question kinds this module has plain wording for
VALUE_KINDS = ("missing_value", "confirm_value", "resolve_conflict")
OPTIONAL_KINDS = ("optional_values", "condition_label")
#: the condition labels a card can ask as one yes / no (a link order and the electrode position are not one)
LABEL_ASKS = {
    "history": ("Should the record describe the sample's history as {value}?",
                "Is the sample history read from the file names right?"),
    "beam_attenuator": ("Was the beam filter {value}?", "Are the beam filter settings read from the file names right?"),
    "sample_id": ("Should the sample ID be {value}?", "Are the sample IDs proposed from the file names right?"),
    "tags": ("Should these records carry the tag {value}?", "Are the tags proposed for these records right?"),
}

CONFIDENCES = H.CONFIDENCES
BASES = H.BASES
MAX_ITEMS = 40
MAX_CONTEXT = 6
MAX_EVIDENCE = 3
#: ``processing.engine_xas.DOSE_QUESTION_FLAG`` (not imported: processing is an optional extra)
DOSE_QUESTION_FLAG = "dose_reading_question"
DOSE_TARGET_ID = "experiment:set_dose_reading"
#: the three readings ``set_dose_reading`` takes (``bundle.DOSE_READINGS``), in the order and words a card offers them
DOSE_LABELS = {
    "beam_damage": "Yes, beam damage: keep only the first scan at each spot",
    "first_scan_settling": "No, the first scan was still settling: leave the first scan out",
    "not_beam_damage": "Neither: keep every scan",
}
PROBE_BY = "site export check (dry run, nothing recorded)"
PROBE_TEXT = "site export check"
_HASH_NAME = re.compile(r"^[0-9a-f]{64}\.(png|jpg|jpeg)$")
#: never copied from the site template, at any depth: installed packages, a deployment's own state, version control
_TEMPLATE_SKIP = shutil.ignore_patterns("node_modules", ".vercel", ".git", ".DS_Store", "__pycache__", "*.pyc")
#: not copied from the template's top folder: its sample data (the export writes the real data/), its tests and
#: fixtures, its local dev server, its example environment file and its read-me (none is part of a deployment)
TEMPLATE_ROOT_SKIP = ("data", "test", "dev-server.js", ".env.example", "README.md")


class SiteRefused(ValueError):
    """The export (or the import) is refused as a whole; nothing was written. ``code`` is the exit code."""

    def __init__(self, message: str, *, code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code


class _LeftOut(Exception):
    """A question (or a card) the export leaves out, with the plain reason the report counts it under."""


# --- where the export may be written ---------------------------------------------------------------------------------

def git_tree_of(path: Path) -> Path | None:
    """The git working tree ``path`` is in (the nearest folder at or above it holding ``.git``), or ``None``."""
    here = Path(path).expanduser().resolve()
    for folder in (here, *here.parents):
        if (folder / ".git").exists():
            return folder
    return None


def out_problem(out: Path, bundle_dir: Path) -> str | None:
    """Why ``out`` cannot hold an export (inside a git working tree, inside or around the bundle folder, a file)."""
    out_r, bundle_r = Path(out).expanduser().resolve(), Path(bundle_dir).expanduser().resolve()
    tree = git_tree_of(out_r)
    if tree is not None:
        return (f"--out is inside a git working tree ({tree.name!r}): the export holds real data and must never be "
                "committed. Give a folder outside every repository.")
    if out_r == bundle_r or bundle_r in out_r.parents or out_r in bundle_r.parents:
        return "--out must be a folder of its own, not the bundle folder, inside it or around it."
    if out_r.exists() and not out_r.is_dir():
        return "--out is a file; give a folder."
    return None


# --- images ------------------------------------------------------------------------------------------------------------

def copy_image(base: Path, rel: str, img_dir: Path) -> str:
    """Copy the PNG or JPEG ``rel`` names inside ``base`` to ``img_dir/<sha256>.<ext>`` and return ``img/<name>``.
    The file is checked exactly as the local image endpoint checks it (``question_context.resolve_context_file``: a
    plain relative path, no symlink, a PNG or JPEG by suffix AND first bytes, never an SVG); anything else raises
    ``question_context.ContextFileRefused`` and nothing is copied."""
    from . import question_context as QC

    target, media_type = QC.resolve_context_file(Path(base), rel)
    data = target.read_bytes()
    if QC.image_format(data[:2048]) not in ("png", "jpeg"):  # the bytes copied are the bytes checked
        raise QC.ContextFileRefused(415, "type_refused", "Only a PNG or JPEG image is copied.")
    name = f"{hashlib.sha256(data).hexdigest()}.{'png' if media_type == 'image/png' else 'jpg'}"
    img_dir.mkdir(parents=True, exist_ok=True)
    dest = img_dir / name
    if not dest.exists():
        dest.write_bytes(data)
    return f"img/{name}"


# --- the bundle, read once -------------------------------------------------------------------------------------------

class _View:
    """What building the cards reads from one bundle."""

    def __init__(self, bundle: Mapping, bundle_dir: Path, payload: Mapping):
        from . import question_context as QC
        from . import questions as Q
        from . import template as T

        self.bundle, self.bundle_dir, self.payload = bundle, Path(bundle_dir), payload
        self.questions = {q["question_id"]: q for q in payload["questions"]}
        self.cands = {c["candidate_id"]: c for c in bundle.get("candidates") or ()}
        self.runs = {r["run_id"]: r for r in bundle.get("runs") or () if r.get("run_id")}
        self.groups = {g["group_id"]: g for g in bundle.get("record_groups") or ()}
        self.live = [g["group_id"] for g in Q.live_groups(bundle)]
        cannot = Q.cannot_export_reasons(bundle)
        self.exportable = [g for g in self.live if g not in cannot]
        self.idx = QC.Index(bundle, self.bundle_dir)
        self.schema, _ = Q._target_schema()
        self._rules: dict[str, dict] = {}
        self._T = T

    def rule(self, path: str | None) -> dict | None:
        if not path:
            return None
        if path not in self._rules:
            self._rules[path] = self._T.rule_for_path(path, schema=self.schema)
        return self._rules[path]

    def group_name(self, gid: str) -> str:
        """A record group as a scientist knows it: its first member file."""
        g = self.groups.get(gid) or {}
        for rid in g.get("member_run_ids") or ():
            run = self.runs.get(rid) or {}
            if run.get("stem") or run.get("label"):
                return str(run.get("stem") or run.get("label"))
        return gid

    def reach(self, gids: Iterable[str]) -> list[str]:
        """``gids`` in bundle order, only those that can become a record (all of them when none can)."""
        wanted = set(gids)
        can = [g for g in self.exportable if g in wanted]
        return can or [g for g in self.live if g in wanted] or sorted(wanted)


def _scopes(q: Mapping) -> list[str]:
    return [k for k in (q.get("per_scope_targets") or {}) if k.startswith("group:")]


def _groups_of(view: _View, q: Mapping, *, only_scopes: Sequence[str] | None = None, field: str | None = None) -> list[str]:
    if only_scopes:
        return [s[len("group:"):] for s in only_scopes if s.startswith("group:")]
    scopes = _scopes(q)
    if field and q.get("kind") == "optional_values":
        mine = set((q.get("fields") or {}).get(field) or ())
        scopes = [s for s in scopes if mine.intersection(q["per_scope_targets"].get(s) or ())]
    if scopes:
        return [s[len("group:"):] for s in scopes]
    if str(q.get("scope") or "").startswith("group:"):
        return [q["scope"][len("group:"):]]
    return list(view.live)


# --- which questions, and how they join ------------------------------------------------------------------------------

def _why_not(q: Mapping, include: Sequence[str]) -> str | None:
    """Why one open question is not asked on the site, or ``None`` when it is."""
    kind, path = q.get("kind"), q.get("target_field_path")
    if q.get("deferred") and INCLUDE_DEFERRED not in include:
        return "answered \"I don't know\" earlier (add --include deferred to ask again)"
    if not q.get("blocking") and INCLUDE_OPTIONAL not in include:
        return "not needed to export (add --include optional)"
    if kind not in VALUE_KINDS + OPTIONAL_KINDS:
        return f"no plain wording for this kind of question yet ({str(kind).replace('_', ' ')})"
    if q.get("informational") or not (q.get("allowed_decisions") or ()):
        return "for information only: nothing is asked"
    if q.get("answered_at_once_by"):
        return "answered at once by a beamtime-wide question the site does not ask yet"
    if kind in VALUE_KINDS and not isinstance(path, str):
        return "about something no record field holds"
    if kind in VALUE_KINDS and "[]" in path:
        return "about how the data files are laid out, not something a scientist is asked"
    if kind in VALUE_KINDS and "correct" not in q["allowed_decisions"]:
        return "takes no value now"
    if kind == "condition_label" and (q.get("label") not in LABEL_ASKS or "confirm" not in q["allowed_decisions"]
                                      or not q.get("proposals")):
        return "a label the site cannot ask as one yes or no"
    if kind == "optional_values" and str(q.get("scope") or "").startswith("group:"):
        return "an optional field asked once per measurement (the metadata template is the easy way to fill these)"
    return None


def _identity(view: _View, q: Mapping) -> tuple[str, str] | None:
    """The grouping's own sample identity of a question's groups, ``(sample name, loading or thickness)``, when they
    all share one and none is a conflicting reading (the electrode number is not part of it: it names the object,
    not the material)."""
    keys = set()
    for gid in _groups_of(view, q):
        sample = ((view.groups.get(gid) or {}).get("basis") or {}).get("sample") or {}
        name, loading = sample.get("sample_name") or {}, sample.get("loading_or_thickness") or {}
        if not name.get("value") or name.get("kind") == "conflicting" or loading.get("kind") == "conflicting":
            return None
        keys.add((str(name["value"]), str(loading.get("value") or "")))
    return next(iter(keys)) if len(keys) == 1 else None


def _loading_said(view: _View, q: Mapping) -> str | None:
    """The loading or thickness of a question's first group as its files write it ("0p5nm"), or ``None``."""
    for gid in _groups_of(view, q):
        loading = (((view.groups.get(gid) or {}).get("basis") or {}).get("sample") or {}).get("loading_or_thickness") or {}
        for cid in loading.get("candidate_ids") or ():
            lits = (view.cands.get(cid) or {}).get("observed_literals") or ()
            if lits:
                return str(lits[0])
        return str(loading["value"]) if loading.get("value") else None
    return None


def _units(view: _View, rows: Sequence[Mapping], include: Sequence[str]) -> tuple[list[dict], Counter]:
    """``(units, left_out)``: each unit is one ask, ``{"questions", "named", "same_reading", "each", "only_scopes",
    "field"}`` (``each``: one call per question, for a part of a same-reading group); ``left_out`` counts the
    questions not asked, by reason."""
    left: Counter = Counter()
    wanted = {}
    for q in rows:
        why = _why_not(q, include)
        if why:
            left[why] += 1
        else:
            wanted[q["question_id"]] = q
    by_group: dict[str, list[Mapping]] = {}
    for q in rows:
        if q.get("same_reading_group"):
            by_group.setdefault(q["same_reading_group"], []).append(q)
    units, done = [], set()
    for q in rows:
        qid = q["question_id"]
        if qid not in wanted or qid in done:
            continue
        group = q.get("same_reading_group")
        members = sorted(by_group.get(group) or (), key=lambda m: m["question_id"]) if group else []
        if len(members) > 1 and len({(m["kind"], m.get("target_field_path")) for m in members}) == 1:
            # every open question of the group is answered by the one call, wanted here or not
            for m in members:
                done.add(m["question_id"])
                if m["question_id"] not in wanted:
                    left[_why_not(m, include) or ""] -= 1
            parts = [members]
            if str(members[0].get("target_field_path") or "").startswith("sample."):
                # one token, two materials (a 0.5 nm and a 2 nm film of one name): the grouping's own sample
                # identity tells them apart, so they are two cards; an identity it does not state joins nothing apart
                by_identity: dict[Any, list[Mapping]] = {}
                for m in members:
                    by_identity.setdefault(_identity(view, m), []).append(m)
                if len(by_identity) > 1 and None not in by_identity:
                    parts = list(by_identity.values())
            for part in parts:
                whole = len(part) == len(members)
                units.append({"questions": part, "named": part[0], "same_reading": whole, "each": not whole,
                              "split_identity": not whole, "only_scopes": None, "field": None})
            continue
        done.add(qid)
        scopes = _scopes(q)
        if q["kind"] == "optional_values":
            for field in sorted(q.get("fields") or {}):
                units.append({"questions": [q], "named": q, "same_reading": False, "only_scopes": None, "field": field})
        elif q["kind"] in VALUE_KINDS and len(scopes) > 1 and (q.get("partition") == "sample=unrecorded"
                                                               or q.get("answers_differ")):
            for sc in scopes:  # their honest answers could differ: one card per group
                units.append({"questions": [q], "named": q, "same_reading": False, "only_scopes": [sc], "field": None})
        else:
            units.append({"questions": [q], "named": q, "same_reading": False, "only_scopes": None, "field": None})
    return units, +left


# --- one card ----------------------------------------------------------------------------------------------------------

def card_id(field_path: str | None, covered: Sequence[str]) -> str:
    """``C-`` + 10 hex of sha256(field path, the sorted covered ids). A covered id is a question id, a question id
    with ``@<scope>`` for a card that covers one group of a question, or a target (``experiment:set_dose_reading``)."""
    text = "\n".join([field_path or "", *sorted(covered)])
    return "C-" + hashlib.sha256(text.encode()).hexdigest()[:10]


def _unit_of(path: str, cand: Mapping | None = None) -> str | None:
    from . import questions as Q

    return Q._unit_of(path, cand or {})


def _answer(view: _View, path: str, allowed: Sequence[Any] | None, *, options: Sequence[Any] | None = None) -> dict:
    """The answer box of a value card, from the field's own rule (``template.rule_for_path``)."""
    rule = view.rule(path) or {}
    listed = [v for v in (allowed or options or ()) if v is not None]
    if listed:
        return {"kind": "choice", "options": [{"value": v, "label": P.value_label(v)} for v in listed],
                "allow_text": True, "unit": None, "placeholder": None}
    if path == view._T.TEMPERATURE_PATH:
        return {"kind": "text", "options": [], "allow_text": True, "unit": None, "placeholder": "298.15 K or 25 °C"}
    if rule.get("numeric"):
        return {"kind": "number", "options": [], "allow_text": True, "unit": _unit_of(path), "placeholder": None}
    placeholder = "2100-01-31T08:30:00Z (UTC)" if path.startswith("timestamps.") else None
    return {"kind": "text", "options": [], "allow_text": True, "unit": None, "placeholder": placeholder}


def _with_common(answer: dict, path: str, suggestion: Mapping | None) -> dict:
    values = [o["value"] for o in answer.get("options") or ()]
    if len(values) < P.COMMON_FROM:
        return answer
    first = [suggestion["value"]] if suggestion and suggestion.get("value") in values else []
    common = list(dict.fromkeys([*first, *[v for v in P.COMMON_OPTIONS.get(path, ()) if v in values]]))
    return {**answer, "common": common} if common else answer


def _file_hints(questions: Sequence[Mapping]) -> list[Mapping]:
    """The hints that quote what the covered questions' OWN files hold (never another question's reading)."""
    out, seen = [], set()
    for q in questions:
        for h in q.get("hints") or ():
            if h.get("kind") not in ("file_literal", "reading") or not isinstance(h.get("literal"), (str, int, float)):
                continue
            key = (str(h["literal"]), h.get("relative_path"), h.get("locator"))
            if key not in seen:
                seen.add(key)
                out.append(h)
    return out


def _evidence(hints: Sequence[Mapping]) -> list[dict]:
    out, seen = [], set()
    for h in hints:
        lit = str(h.get("observed_literal") or h.get("literal"))
        if lit in seen:
            continue
        seen.add(lit)
        out.append({"quote": lit, "file": h.get("relative_path") or h.get("source_path"), "locator": h.get("locator")})
    return out[:MAX_EVIDENCE]


def _file_values(view: _View, questions: Sequence[Mapping]) -> tuple[list[Any], Mapping | None]:
    """The distinct values the covered questions' candidates carry (JSON-distinct), and one such candidate."""
    values, first = {}, None
    for q in questions:
        for t in q.get("targets") or ():
            c = view.cands.get(t.get("id")) if t.get("kind") == "candidate" else None
            if c is None or c.get("value") is None:
                return [], None
            first = first or c
            values.setdefault(json.dumps(c["value"], sort_keys=True, default=str), c["value"])
    return list(values.values()), first


def _suggestion_from_bundle(view: _View, unit: Mapping, shape: str, path: str) -> tuple[dict | None, dict | None]:
    """``(suggestion, on_accept)`` from what the bundle holds for a value card, or ``(None, None)``."""
    qs = unit["questions"]
    kind = unit["named"]["kind"]
    allowed = unit["named"].get("allowed_decisions") or ()
    if kind == "confirm_value" and shape == "value" and "confirm" in allowed:
        values, cand = _file_values(view, qs)
        if len(values) == 1:
            hints = [h for h in _file_hints(qs) if h.get("carries_value") is not False]
            written = P.quoted([h["literal"] for h in hints])
            exact = isinstance(values[0], (int, float)) or any(str(h["literal"]).casefold() == str(values[0]).casefold()
                                                               for h in hints)
            return ({"value": values[0], "label": P.value_label(values[0], _unit_of(path, cand)),
                     "confidence": "high" if exact else "medium", "basis": "files",
                     "reason": f"Your files write {written}." if written else "Read from your files.",
                     "evidence": _evidence(hints)}, {"decision": "confirm", "value": None})
    if "correct" not in allowed:
        return None, None
    if kind == "resolve_conflict":
        utc = {}
        for q in qs:
            for r in q.get("utc_readings") or ():
                utc.setdefault(str(r.get("value")), r)
        if len(utc) == 1 and all(q.get("utc_readings") for q in qs):
            r = next(iter(utc.values()))
            return ({"value": r["value"], "label": str(r["value"]), "confidence": "medium", "basis": "files",
                     "reason": "The same file's header also gives the start as a UTC instant.",
                     "evidence": _evidence([{"literal": r.get("observed_literal") or r["value"],
                                             "relative_path": r.get("relative_path"), "locator": r.get("locator")}])},
                    {"decision": "correct", "value": r["value"]})
    earlier = [h for q in qs for h in q.get("earlier_answers") or () if h.get("field") == path]
    distinct = {json.dumps(h.get("value"), sort_keys=True, default=str) for h in earlier}
    if len(distinct) == 1 and not any(h.get("disagrees") for h in earlier):
        h = earlier[0]
        return ({"value": h["value"], "label": P.value_label(h["value"], _unit_of(path)), "confidence": "medium",
                 "basis": "earlier_answer", "reason": f"{h.get('by') or 'A scientist'} gave this answer on "
                 f"{h.get('date')} for an earlier beamtime ({h.get('matched_on')}).", "evidence": []},
                {"decision": "correct", "value": h["value"], "from_earlier_answer": h.get("entry_id")})
    ai = [h for q in qs for h in q.get("hints") or () if h.get("kind") == "ai_suggestion"]
    literals = {json.dumps(h.get("literal"), sort_keys=True, default=str) for h in ai}
    if len(literals) == 1 and not any(h.get("read_for") for h in ai) and all(
            any(h.get("kind") == "ai_suggestion" for h in q.get("hints") or ()) for q in qs):
        h = ai[0]
        quote = [{"quote": str(h["quote"]), "file": h.get("source_path"), "locator": h.get("locator")}] if h.get("quote") else []
        stated = all(str(x.get("strength") or "") == "stated" for x in ai)
        return ({"value": h["literal"], "label": P.value_label(h["literal"], _unit_of(path)),
                 # a reading is never file evidence: "stated" (the quoted line says it) is medium, "inferred" low
                 "confidence": "medium" if stated else "low", "basis": "reading",
                 "reason": ("An AI reading found this stated in your files, in the line quoted. Please check it."
                            if stated else
                            "An AI reading of your files infers this from the line quoted. It is not stated outright."),
                 "evidence": quote}, {"decision": "correct", "value": h["literal"]})
    return None, None


def _subject(view: _View, unit: Mapping, groups: Sequence[str], path: str | None) -> tuple[str | None, bool, str | None]:
    """``(subject, plural, sample)``: who a card is about, in words ("sample ZZ1 (no. 01)", "these 5 measurements",
    "this measurement"; ``None`` for the whole beamtime), whether that is several things, and the sample as the files
    write it ("ZZ1 (no. 01)") when the card is about one sample."""
    q = unit["named"]
    pairs = P.sample_pairs(q)
    # only a sample the question's own words give in the files' spelling: a partition key alone is lower-cased
    if pairs and not unit["only_scopes"] and "as the files write it" in str(q.get("text") or ""):
        got = dict(pairs)
        if got.get("sample_name") and set(got) <= {"sample_name", "sample_or_electrode_number", "loading_or_thickness"}:
            name = ", ".join(x for x in (got["sample_name"], got.get("loading_or_thickness")) if x)
            number = f" (no. {got['sample_or_electrode_number']})" if got.get("sample_or_electrode_number") else ""
            return f"sample {name}{number}", False, f"{name}{number}"
    if (unit["same_reading"] or unit.get("split_identity")) and isinstance(path, str) and path.startswith("sample."):
        tokens = q.get("shared_sample_tokens")
        literals = list(dict.fromkeys(str(h["literal"]) for h in _file_hints(unit["questions"])
                                      if h.get("kind") == "file_literal"))
        name = " ".join(str(t) for t in tokens) if tokens else literals[0] if len(literals) == 1 else None
        loading = _loading_said(view, q) if unit.get("split_identity") else None
        if name and loading and loading.casefold() not in name.casefold():
            name = f"{name}, {loading}"
        if name:
            return f"sample {name}", False, name
    whole = (str(q.get("scope")) == "experiment" and not unit["only_scopes"] and not unit["same_reading"]
             and not unit.get("each") and not (q.get("partition") or "").startswith("sample="))
    if whole:
        return None, False, None
    n = len(groups)
    return ("this measurement", False, None) if n <= 1 else (f"these {n} measurements", True, None)


def _applies_to(view: _View, groups: Sequence[str], sample: str | None, whole: bool) -> dict:
    names = [view.group_name(g) for g in groups]
    n = len(names)
    if whole and set(groups) >= set(view.exportable) and n > 1:
        summary = f"All {n} records"
    elif sample:
        summary = f"{n} measurement{'s' if n != 1 else ''} of sample {sample}"
    elif n == 1:
        summary = names[0]
    else:
        summary = f"{n} measurements"
    return {"count": n, "summary": summary, "items": names[:MAX_ITEMS], **({"more": n - MAX_ITEMS} if n > MAX_ITEMS else {})}


def _value_card(view: _View, unit: Mapping) -> dict:
    q = unit["named"]
    qs = unit["questions"]
    kind = q["kind"]
    path = unit["field"] or q["target_field_path"]
    allowed = (q.get("field_allowed_values") or {}).get(path) if unit["field"] else q.get("allowed_values")
    gids = list(dict.fromkeys(g for m in qs for g in _groups_of(view, m, only_scopes=unit["only_scopes"], field=unit["field"])))
    groups = view.reach(gids)
    subject, plural, sample = _subject(view, unit, groups, path)
    shape = P.confirm_shape(q) if kind == "confirm_value" else None
    if kind == "confirm_value" and len({P.confirm_shape(m) for m in qs}) != 1:
        raise _LeftOut("its questions are not all asked the same way")
    suggestion, on_accept = _suggestion_from_bundle(view, unit, shape or "", path)
    literals = [h["literal"] for h in _file_hints(qs)]
    written = P.quoted(literals)
    options = None
    if kind == "resolve_conflict" and not allowed and int(q.get("readings_that_fit_the_field") or 0) > 0:
        options = list(dict.fromkeys(h["literal"] for h in _file_hints(qs) if h.get("kind") == "reading"
                                     and h.get("fits_field") is not False))
    answer = _answer(view, path, allowed, options=options)
    noun_ = P.noun(path)
    ask = P.ask_for(path, allowed, subject=subject, plural=plural, names_sample=bool(sample))
    if kind == "confirm_value" and shape == "value" and suggestion is not None:
        title = P.is_it(path, suggestion["label"], subject=subject)
        detail = suggestion["reason"]
    elif kind == "confirm_value" and shape == "value":
        title = ask
        detail = f"Your files write {written}, read differently from one file to the next." if written else ""
    elif kind == "confirm_value":
        title = ask
        detail = ("The value read from your files does not fit here." if shape == "unfit"
                  else "Your files mention it, but not as a value a record can hold." if not written
                  else f"Your files write {written}, a clock time with no time zone. Please give it in UTC."
                  if path.startswith("timestamps.")
                  else f"Your files only write {written}. Please pick the {noun_} from the list." if allowed
                  else f"Your files only write {written}. Please give the {noun_} itself.")
    elif kind == "resolve_conflict" and options:
        title = P.disagree(path, subject=subject)
        detail = ""
    elif kind == "resolve_conflict":
        title = ask
        said = f"Your files write {written}" if written else "Your files disagree about it"
        detail = (f"{said}. Please pick the {noun_} from the list." if allowed
                  else f"{said}, with no time zone. Please give it in UTC." if path.startswith("timestamps.")
                  else f"{said}. Please give the right {noun_}.")
    else:
        title = ask
        detail = "" if suggestion else P.NONE_SAY
    n = len(groups)
    if n > 1 and subject is None and len(_scopes(q)) > 1:
        detail = f"{detail} One answer covers all {n} measurements; if some differ, say which in the note.".strip()
    blocking = any(m.get("blocking") for m in qs)
    scoped = set(unit["only_scopes"] or ())
    blocks = {g for m in qs if m.get("blocking") for g in m.get("blocks_group_ids") or ()
              if not scoped or f"group:{g}" in scoped}
    covered = [m["question_id"] + (f"@{unit['only_scopes'][0]}" if unit["only_scopes"] else "") for m in qs]
    whole = subject is None
    section = ("optional" if not blocking else "beamtime" if whole else "samples" if sample else "records")
    def cover(named: Mapping, answers: Sequence[Mapping]) -> dict:
        return {
            "question_id": named["question_id"], "same_reading": bool(unit["same_reading"]),
            "only_scopes": list(unit["only_scopes"]) if unit["only_scopes"] else None,
            "field": unit["field"], "on_accept": dict(on_accept) if on_accept else None,
            "on_value": {"decision": "correct"},
            "on_dont_know": {"decision": "defer"} if "defer" in named["allowed_decisions"] else None, "target": None,
            "questions": [m["question_id"] for m in answers],
        }

    # a part of a same-reading group is answered question by question: one call each, the same answer
    covers = [cover(m, [m]) for m in qs] if unit.get("each") else [cover(q, qs)]
    return {
        "card_id": card_id(path, covered), "section": section, "blocking": blocking, "audience": "scientist",
        "title": title, "detail": detail, "field": {"path": path, "label": P.field_label(path)},
        "applies_to": _applies_to(view, groups, sample, whole), "unblocks": len(blocks) if blocking else 0,
        "answer": _with_common(answer, path, suggestion), "suggestion": suggestion, "context": [], "covers": covers,
        "_questions": qs, "_groups": groups, "_sample": sample, "_folder_hint": [h for m in qs for h in m.get("hints") or ()
                                                              if h.get("kind") == "folder_name"],
    }


def _label_card(view: _View, unit: Mapping) -> dict:
    """A condition label ISAAC proposes from the file names, asked as one yes / no (yes records each proposal)."""
    q = unit["named"]
    proposals = [p for p in q.get("proposals") or () if isinstance(p.get("value"), (str, int, float))]
    if not proposals or len(proposals) != len(q.get("proposals") or ()):
        raise _LeftOut("a label the site cannot ask as one yes or no")
    one, many = LABEL_ASKS[q["label"]]
    values = list(dict.fromkeys(str(p["value"]) for p in proposals))
    title = one.format(value=f"'{values[0]}'") if len(values) == 1 else many
    groups = view.reach([p["group_id"] for p in proposals if p.get("group_id")] or _groups_of(view, q))
    n = len(groups)
    rows = [[str(p.get("first_file") or view.group_name(p.get("group_id") or "")), str(p["value"])] for p in proposals]
    cover = {"question_id": q["question_id"], "same_reading": False, "only_scopes": None, "field": None,
             "on_accept": None, "on_value": None, "on_dont_know": None, "on_yes": {"decision": "confirm"},
             "on_no": None, "target": None, "questions": [q["question_id"]]}
    path = q.get("target_field_path")
    return {
        "card_id": card_id(path, [q["question_id"]]), "section": "optional", "blocking": False, "audience": "scientist",
        "title": title, "detail": "Proposed from the file names; nothing is written until you say yes. "
                                  "If it is not right, say no and add a note.",
        "field": {"path": path, "label": P.field_label(path)} if isinstance(path, str) else None,
        "applies_to": _applies_to(view, groups, None, n == len(view.exportable)), "unblocks": 0,
        "answer": {"kind": "yes_no", "options": [], "allow_text": False, "unit": None, "placeholder": None},
        "suggestion": None,
        "context": [{"kind": "values", "label": "Proposed from the file names", "columns": ["File", "Proposed"],
                     "rows": rows[:8], **({"more": len(rows) - 8} if len(rows) > 8 else {})}],
        "covers": [cover], "_questions": [q], "_groups": groups, "_no_context": True,
    }


# --- the processing card: beam damage, or a first scan still settling ---------------------------------------------------

def _dose_card(view: _View) -> dict | None:
    from . import questions as Q

    bundle = view.bundle
    decided = {(d.get("target") or {}).get("kind"): d for d in bundle.get("scientist_decisions") or ()
               if d.get("decision") == B.DOSE_READING_DECISION and (d.get("target") or {}).get("kind") == "experiment"}
    if decided:
        return None
    own = {(d.get("target") or {}).get("id") for d in bundle.get("scientist_decisions") or ()
           if d.get("decision") == B.DOSE_READING_DECISION and (d.get("target") or {}).get("kind") == "record_group"}
    asked, rows, changes, reasons = [], [], [], Counter()
    for gid in view.live:
        r = Q.curve_result(bundle, gid) if gid not in own else None
        if r is None or DOSE_QUESTION_FLAG not in (r.get("review_flags") or ()):
            continue
        asked.append(gid)
        dose = r.get("dose_damage") or {}
        spots = [s for s in (dose.get("per_spot") or {}).values() if s.get("kind") not in (None, "none")]
        got = [float(s["d12"]) * 100 for s in spots if isinstance(s.get("d12"), (int, float))]
        changes += got
        reasons[str(dose.get("why") or "")] += 1
        rows.append([view.group_name(gid), str(dose.get("spots_measured_more_than_once") or len(spots)),
                     ", ".join(f"{c:+.1f} %" for c in got) or "-"])
    if not asked:
        return None
    n, total = len(asked), len(view.exportable)
    what = "drop" if changes and all(c < 0 for c in changes) else "rise" if changes and all(c > 0 for c in changes) else "change"
    two_scans = set(reasons) == {"only two scans per spot: a change that grows with dose cannot be told from a first "
                                 "scan still settling"}
    why = ("with only two scans at each spot, ISAAC cannot tell beam damage from a first scan that was still settling"
           if two_scans else "ISAAC's rule cannot tell beam damage from a first scan that was still settling")
    options = [{"value": v, "label": label} for v, label in DOSE_LABELS.items() if v in B.DOSE_READINGS]
    cover = {"question_id": None, "same_reading": False, "only_scopes": None, "field": None, "on_accept": None,
             "on_value": {"decision": B.DOSE_READING_DECISION}, "on_dont_know": None,
             "target": {"target": "experiment", "decision": B.DOSE_READING_DECISION}, "questions": []}
    return {
        "card_id": card_id(None, [DOSE_TARGET_ID]), "section": "processing", "blocking": False, "audience": "processing",
        "title": f"The white line {what}s after the first scan at each spot: is that beam damage?",
        "detail": f"Seen in {n} of {total} measurements; {why}. Your answer decides which scans go into every "
                  "merged spectrum.",
        "field": None,
        "applies_to": {"count": n, "summary": f"{n} of {total} measurements",
                       "items": [view.group_name(g) for g in asked[:MAX_ITEMS]],
                       **({"more": n - MAX_ITEMS} if n > MAX_ITEMS else {})},
        "unblocks": 0,
        "answer": {"kind": "choice", "options": options, "allow_text": False, "unit": None, "placeholder": None},
        "suggestion": None,
        "context": [{"kind": "values", "label": "White-line change after the first scan, spot by spot",
                     "columns": ["Measurement", "Spots measured twice", "Change at each changed spot"],
                     "rows": rows[:8], **({"more": len(rows) - 8} if len(rows) > 8 else {})}],
        "covers": [cover], "_questions": [], "_groups": asked, "_no_context": True, "_target_id": DOSE_TARGET_ID,
        "_is_dose": True,
    }


# --- the two other export gates: confirming a group, approving its merged curve (--include approvals) -----------------

def _approval_cards(view: _View) -> tuple[list[dict], Counter]:
    """One yes / no card per record group still to confirm and per merged curve still to approve. ``yes`` is one
    decide call (``confirm`` the group; ``approve`` the result with QC status ``valid``); ``no`` records nothing (the
    note says why). Left out, and counted: every group while the file-name counter question is open (its answer can
    still regroup the runs), a curve with an open dose question or an open scan proposal (its merge can still
    change), and a curve the quality check does not pass (its QC status is a statement to make with a person)."""
    from . import mutations as M
    from . import question_context as QC
    from . import questions as Q

    bundle, left = view.bundle, Counter()
    counter_open = any(q["kind"] == "naming_counter_positions" and not q.get("deferred") for q in view.payload["questions"])
    cards = []
    held = dict(M.BULK_APPROVE_REVIEW)
    for gid in view.exportable:
        group, name = view.groups[gid], view.group_name(gid)
        runs = [view.idx.run_name(r) for r in group.get("member_run_ids") or ()]
        if group.get("status") == "proposed":
            if counter_open:
                left["a group to confirm, held until the question about counters in the file names is answered"] += 1
            else:
                shown: list = []
                ctx = QC.context_for({"kind": "record_group", "scope": f"group:{gid}",
                                      "targets": [{"kind": "record_group", "id": gid}]}, view.idx, shown, theme="group")
                cover = {"question_id": None, "same_reading": False, "only_scopes": None, "field": None,
                         "on_accept": None, "on_value": None, "on_dont_know": None, "on_yes": {"decision": "confirm"},
                         "on_no": None, "target": {"target": gid, "decision": "confirm"}, "questions": []}
                cards.append({
                    "card_id": card_id(None, [f"{gid}:confirm"]), "section": "records", "blocking": True,
                    "audience": "scientist",
                    "title": ("Is this one measurement that should become one record?" if len(runs) <= 1 else
                              f"Do these {len(runs)} files belong together as one measurement and one record?"),
                    "detail": "If not, say no and add a note saying what should be split or joined.",
                    "field": None, "applies_to": {"count": 1, "summary": name, "items": runs[:MAX_ITEMS] or [name]},
                    "unblocks": 1, "answer": {"kind": "yes_no", "options": [], "allow_text": False, "unit": None,
                                              "placeholder": None},
                    "suggestion": None, "context": [], "covers": [cover], "_questions": [], "_groups": [gid],
                    "_context_items": ctx, "_shown": shown, "_target_id": f"{gid}:confirm"})
        r = Q.curve_result(bundle, gid)
        if r is None or r.get("state") not in B.PROCESSING_UNDECIDED_STATES or not (r.get("outputs") or {}).get("files"):
            continue
        flags = [f for f in r.get("review_flags") or () if f in held]
        verdict = (r.get("qc") or {}).get("verdict") if isinstance(r.get("qc"), Mapping) else None
        if flags:
            left["a merged curve to approve, held until its open processing question is answered"] += 1
            continue
        if verdict != "pass" or M.unusable_curve_reasons(r):
            left["a merged curve to approve whose quality check did not pass (its status is stated with a person)"] += 1
            continue
        shown = []
        ctx = QC.context_for({"kind": "record_group", "scope": f"group:{gid}", "target_field_path": "measurement.qc.status",
                              "targets": [{"kind": "record_group", "id": gid}]}, view.idx, shown, theme="curve")
        if not any(i.get("kind") == "plot" and i.get("path") and not i.get("not_shown") for i in ctx):
            left["a merged curve to approve with no picture to show"] += 1
            continue
        rid = r["result_id"]
        cover = {"question_id": None, "same_reading": False, "only_scopes": None, "field": None, "on_accept": None,
                 "on_value": None, "on_dont_know": None, "on_yes": {"decision": "approve", "qc_status": "valid"},
                 "on_no": None, "target": {"target": rid, "decision": "approve"}, "questions": []}
        cards.append({
            "card_id": card_id(None, [f"{rid}:approve"]), "section": "processing", "blocking": True,
            "audience": "scientist", "title": "Is this merged spectrum good to use in the record?",
            "detail": "Yes approves it as valid data. If something is wrong with it, say no and add a note.",
            "field": None, "applies_to": {"count": 1, "summary": name, "items": [name]}, "unblocks": 1,
            "answer": {"kind": "yes_no", "options": [], "allow_text": False, "unit": None, "placeholder": None},
            "suggestion": None, "context": [], "covers": [cover], "_questions": [], "_groups": [gid],
            "_context_items": ctx, "_shown": shown, "_target_id": f"{rid}:approve"})
    return cards, left


# --- checking a card's calls by dry run -----------------------------------------------------------------------------

def cover_call(cover: Mapping, action: Mapping, value: Any = None, *, as_said: bool = False) -> dict:
    """The one decide call a cover stands for with ``action`` (its ``on_accept`` / ``on_value`` / ``on_dont_know`` /
    ``on_yes``): what the export dry-runs and the import records."""
    target = cover.get("target")
    if target:
        return {"call": "target", "target_ids": [target["target"]], "decision": action["decision"], "value": value,
                "qc_status": action.get("qc_status")}
    return {"call": "question", "question_id": cover["question_id"], "decision": action["decision"], "value": value,
            "field": cover.get("field"), "same_reading": bool(cover.get("same_reading")),
            "only_scopes": list(cover["only_scopes"]) if cover.get("only_scopes") else None, "as_said": as_said}


def run_call(plan: Mapping, bundle_dir: Path, *, by: str, note: str | None, dry_run: bool, orcid: str | None = None) -> dict:
    """Run one :func:`cover_call` through the decide path (``mutations.decide_question`` / ``mutations.decide``)."""
    from . import mutations as M

    if plan["call"] == "target":
        return M.decide(bundle_dir, target_ids=plan["target_ids"], decision=plan["decision"], value=plan.get("value"),
                        by=by, orcid=orcid, note=note, qc_status=plan.get("qc_status"), dry_run=dry_run)
    return M.decide_question(bundle_dir, question_id=plan["question_id"], decision=plan["decision"],
                             value=plan.get("value"), by=by, orcid=orcid, note=note, field=plan.get("field"),
                             same_reading=bool(plan.get("same_reading")), only_scopes=plan.get("only_scopes"),
                             as_said=bool(plan.get("as_said")), dry_run=dry_run)


def _recorded(result: Mapping) -> int:
    got = result.get("recorded")
    if got is None:
        got = result.get("slots_recorded")
    return len(got) if isinstance(got, (list, tuple)) else int(got or 0)


def _dry(plan: Mapping, tmp: Path) -> str | None:
    """``None`` when the decide path would record ``plan`` (or holds it already), else why it refuses."""
    from . import mutations as M
    from . import records as R

    try:
        with contextlib.redirect_stderr(io.StringIO()):  # a load's own notices are the real command's to print, once
            result = run_call(plan, tmp, by=PROBE_BY, note=None, dry_run=True)
    except (M.MutationRefused, R.RecordsRefused) as exc:
        return str(exc)
    return None if (_recorded(result) or result.get("unchanged") is not None) else "it would record nothing"


def _verify(card: dict, tmp: Path) -> tuple[bool, str | None]:
    """Dry-run the calls ``card`` lists. ``(True, note)``: it is answerable (``note``: a suggestion that was dropped
    because its accept call is refused). ``(False, why)``: no call can answer it."""
    dropped = None
    for cover in card["covers"]:
        proved = False
        if cover.get("on_dont_know"):
            why = _dry(cover_call(cover, cover["on_dont_know"]), tmp)
            if why:
                return False, why
            proved = True
        if cover.get("on_yes"):
            why = _dry(cover_call(cover, cover["on_yes"]), tmp)
            if why:
                return False, why
            proved = True
        if cover.get("on_accept"):
            acc = cover["on_accept"]
            why = _dry(cover_call(cover, acc, acc.get("value")), tmp)
            if why:
                dropped = why
                H.demote(card, why)
                for c in card["covers"]:
                    c["on_accept"] = None
                card["suggestion"] = None
                card.pop("_suggestion_entry", None)
            else:
                proved = True
        options = card["answer"].get("options") or ()
        if cover.get("on_value") and options:
            why = None
            for opt in options[:3]:  # an option the files contradict for these runs is refused by its value alone
                why = _dry(cover_call(cover, cover["on_value"], opt["value"]), tmp)
                if not why:
                    break
            if why:
                return False, why
            proved = True
        if not proved:
            return False, "no call of this card could be checked by a dry run"
    return True, dropped


def _probe_value(card: Mapping) -> Any:
    """A value to simulate a beamtime-wide answer with: the suggestion, the first option, or a plain word."""
    if card.get("suggestion"):
        return card["suggestion"]["value"]
    options = card["answer"].get("options") or ()
    if options:
        return options[0]["value"]
    return PROBE_TEXT if card["answer"]["kind"] == "text" and not card["answer"].get("placeholder") else None


def _settles(card: Mapping, bundle_file: Path, blocking_before: set[str]) -> set[str]:
    """The OTHER blocking questions that stop blocking once ``card`` (beamtime-wide) is answered: found by recording
    a probe answer on a throwaway copy of ``bundle.json`` and listing the questions again."""
    from . import mutations as M
    from . import questions as Q
    from . import records as R

    value = _probe_value(card)
    cover = card["covers"][0]
    if value is None or not cover.get("on_value") or cover.get("target"):
        return set()
    with tempfile.TemporaryDirectory(prefix="isaac-site-") as tmp:
        shutil.copy2(bundle_file, Path(tmp) / B.BUNDLE_FILE)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                run_call(cover_call(cover, cover["on_value"], value), Path(tmp), by=PROBE_BY, note=None, dry_run=False)
                after = {q["question_id"] for q in Q.consolidate(M.load(Path(tmp)))["questions"] if q.get("blocking")}
        except (M.MutationRefused, R.RecordsRefused):
            return set()
    return blocking_before - after - set(cover.get("questions") or ())


# --- context ---------------------------------------------------------------------------------------------------------

def _site_context(items: Sequence[Mapping], view: _View, img_dir: Path, images: list[str]) -> list[dict]:
    """Question context (``question_context``) in the contract's three kinds: quotes, values, image. A plot or image
    is copied (:func:`copy_image`); one that is not a PNG or JPEG inside the bundle or its notes folder is left out."""
    from . import question_context as QC

    out: list[dict] = []
    quotes: dict[tuple, dict] = {}
    roots = {"bundle": view.bundle_dir, "notes": QC.notes_root(view.bundle_dir)}
    for it in items:
        kind, label, source = it.get("kind"), str(it.get("label") or ""), it.get("source")
        if kind == "quote":
            block = quotes.get((label, source))
            if block is None:
                block = quotes[(label, source)] = {"kind": "quotes", "label": label, "source": source, "items": []}
                out.append(block)
            block["items"].append({"quote": it.get("quote"), "file": it.get("path"), "locator": it.get("locator")})
        elif kind == "values":
            more = int(it.get("rows_total") or 0) - len(it.get("rows") or ())
            out.append({"kind": "values", "label": label, "source": source, "columns": list(it.get("columns") or ()),
                        "rows": [list(r) for r in it.get("rows") or ()], **({"more": more} if more > 0 else {})})
        elif kind == "table_row":
            cells = it.get("cells") or {}
            out.append({"kind": "values", "label": label, "source": source, "columns": [str(k) for k in cells],
                        "rows": [[str(v) for v in cells.values()]]})
        elif kind == "example_files":
            names = [str(n) for n in it.get("names") or ()]
            more = int(it.get("total") or 0) - len(names)
            out.append({"kind": "values", "label": label, "source": source, "columns": ["File"],
                        "rows": [[n] for n in names], **({"more": more} if more > 0 else {})})
        elif kind in ("plot", "image") and it.get("path") and not it.get("not_shown") and roots.get(it.get("base")):
            try:
                rel = copy_image(roots[it["base"]], str(it["path"]), img_dir)
            except (QC.ContextFileRefused, OSError):
                continue
            images.append(rel)
            out.append({"kind": "image", "label": label, "source": source, "image": rel,
                        "alt": str(it.get("alt") or label)})
    return out[:MAX_CONTEXT]


def _card_context(card: dict, view: _View, img_dir: Path, images: list[str], shown: list) -> None:
    from . import question_context as QC

    extra = list(card.get("_extra_context") or ())  # what a reading found (--suggestions): shown first
    if card.get("_context_items") is not None:
        card["context"] = (extra + _site_context(card["_context_items"], view, img_dir, images))[:MAX_CONTEXT]
        shown += card.get("_shown") or []
        return
    if card.get("_no_context"):
        card["context"] = (list(card.get("context") or ()) + extra)[:MAX_CONTEXT]
        return
    qs = card["_questions"]
    q = qs[0]
    if len(qs) > 1:  # one context for the whole card: every covered question's targets
        q = {**q, "scope": "experiment", "targets": [t for m in qs for t in m.get("targets") or ()]}
    cover = card["covers"][0]
    if cover.get("only_scopes"):
        ids = {i for sc in cover["only_scopes"] for i in (q.get("per_scope_targets") or {}).get(sc) or ()}
        q = {**q, "scope": cover["only_scopes"][0], "targets": [t for t in q.get("targets") or () if t.get("id") in ids]}
    if cover.get("field"):
        ids = set((q.get("fields") or {}).get(cover["field"]) or ())
        q = {**q, "kind": "missing_value", "target_field_path": cover["field"],
             "targets": [t for t in q.get("targets") or () if t.get("id") in ids]}
    items = _site_context(QC.context_for(q, view.idx, shown, full=True), view, img_dir, images)
    folder = card.get("_folder_hint") or ()
    if folder:
        items = [{"kind": "quotes", "label": "The imported folder's name", "source": "the folder you imported",
                  "items": [{"quote": str(folder[0].get("literal")), "file": None,
                             "locator": "a name in a folder name is a hint, never an answer"}]}, *items][:MAX_CONTEXT]
    card["context"] = (extra + items)[:MAX_CONTEXT]


# --- the export ------------------------------------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_template() -> Path:
    """The repository's ``apps/question-site`` (the site's own source), found relative to this package."""
    return Path(__file__).resolve().parents[3] / "question-site"


def _progress(text: str, quiet: bool) -> None:
    if not quiet:
        print(text, file=sys.stderr, flush=True)


def export_site(bundle_dir: Path, out: Path, *, suggestions: Path | None = None, include: Sequence[str] = (),
                site_template: Path | None = None, quiet: bool = True) -> dict:
    """``isaac bundle site export``: write ``<out>/data/site-data.json`` and its images; returns the report."""
    from . import answer_memory as AM
    from . import mutations as M
    from . import questions as Q

    bundle_dir, out = Path(bundle_dir).expanduser(), Path(out).expanduser()
    unknown = [i for i in include if i not in INCLUDES]
    if unknown:
        raise SiteRefused(f"--include takes {', '.join(INCLUDES)}; not {', '.join(unknown)}.")
    if not B.bundle_path(bundle_dir).is_file():
        raise SiteRefused(f"No bundle.json in {bundle_dir.name!r}.", code=EXIT_NOT_FOUND)
    if (problem := out_problem(out, bundle_dir)) is not None:
        raise SiteRefused(f"{problem} Nothing was written.", code=EXIT_OUTPUT_REFUSED)
    try:
        entries = H.read_suggestions(suggestions) if suggestions is not None else []
    except H.HintsRefused as exc:
        raise SiteRefused(f"{exc} Nothing was written.", code=EXIT_INPUT_REFUSED) from None
    try:
        bundle = M.load(bundle_dir)
    except M.MutationRefused as exc:
        raise SiteRefused(str(exc), code=exc.code) from exc
    payload = Q.consolidate(bundle)
    rows, outside = Q.hide_outside_live_groups(payload["questions"], scope=None, include=False)
    rows = AM.annotate(rows, bundle)
    view = _View(bundle, bundle_dir, {**payload, "questions": rows})

    left: Counter = Counter()
    if outside:
        left["about runs no record is built from"] += len(outside)
    units, not_asked = _units(view, rows, include)
    left.update(not_asked)
    cards: list[dict] = []
    for unit in units:
        try:
            card = _label_card(view, unit) if unit["named"]["kind"] == "condition_label" else _value_card(view, unit)
        except _LeftOut as exc:
            left[str(exc)] += len(unit["questions"])
            continue
        cards.append(card)
    dose = _dose_card(view)
    if dose is not None:
        cards.append(dose)
    if INCLUDE_APPROVALS in include:
        more, held = _approval_cards(view)
        cards += more
        left.update(held)
    suggestion_report = H.apply(cards, entries, _with_common)

    # every card's calls, dry-run on a temporary copy of bundle.json (not even a lock file in the bundle folder)
    kept: list[dict] = []
    dropped_suggestions: list[dict] = []
    bundle_file = B.bundle_path(bundle_dir)
    blocking_before = {q["question_id"] for q in rows if q.get("blocking")}
    with tempfile.TemporaryDirectory(prefix="isaac-site-") as tmp:
        shutil.copy2(bundle_file, Path(tmp) / B.BUNDLE_FILE)
        for n, card in enumerate(cards, start=1):
            _progress(f"  checking card {n} of {len(cards)}", quiet)
            ok, note = _verify(card, Path(tmp))
            if not ok:
                left[f"no call can answer it now ({_first_sentence(note)})"] += max(1, len(card["_questions"]))
                continue
            if note:
                dropped_suggestions.append({"card_id": card["card_id"], "title": card["title"], "why": _first_sentence(note)})
            if (why := P.not_plain(card["title"])) or (why := P.not_plain(_without_quotes(card["detail"]))):
                left[f"its wording would not be plain ({why})"] += max(1, len(card["_questions"]))
                continue
            kept.append(card)
    cards = kept

    # a beamtime-wide blocking answer settles some per-group questions: those are not asked a second time
    settled: dict[str, str] = {}
    for card in cards:
        if card["section"] == "beamtime" and card["blocking"]:
            _progress(f"  checking what \"{card['title']}\" settles", quiet)
            for qid in _settles(card, bundle_file, blocking_before):
                settled.setdefault(qid, card["title"])
    if settled:
        still = []
        for card in cards:
            asks = [q["question_id"] for q in card["_questions"] if q.get("blocking")]
            if asks and all(q in settled for q in asks):
                left[f"settled by the beamtime-wide answer to \"{settled[asks[0]]}\""] += len(card["_questions"])
            else:
                still.append(card)
        cards = still

    cards.sort(key=lambda c: (not c["blocking"], -int(c["unblocks"]), -int(c["applies_to"]["count"]),
                              _SECTION_ORDER.get(c["section"], 9), c["title"], c["card_id"]))
    ids = Counter(c["card_id"] for c in cards)
    clash = [i for i, n in ids.items() if n > 1]
    if clash:  # never two cards under one id: the answers file is keyed by it
        raise SiteRefused(f"Two cards would share an id ({clash[0]}); nothing was written. This is a bug to report.",
                          code=EXIT_INPUT_REFUSED)

    data_dir, img_dir = out / "data", out / "data" / "img"
    data_dir.mkdir(parents=True, exist_ok=True)
    images: list[str] = []
    shown: list = []
    for card in cards:
        _card_context(card, view, img_dir, images, shown)
    if img_dir.is_dir():  # an image of an earlier export that no card shows now is real data left behind: removed
        keep = {Path(i).name for i in images}
        for f in img_dir.iterdir():
            if f.is_file() and _HASH_NAME.match(f.name) and f.name not in keep:
                f.unlink()

    # the parser values the cards show are exposures, recorded before anything is written for a reader
    asked = [q for c in cards for q in c["_questions"]]
    exposed = [("candidate", h["candidate_id"]) for q in asked for h in q.get("hints") or () if h.get("candidate_id")]
    exposed += [("conflict", q["targets"][0]["id"]) for q in asked if q["kind"] == "resolve_conflict" and q.get("targets")]
    exposed += [("candidate", cid) for q in asked if q["kind"] == "confirm_value" for cid in Q.confirm_value_shown(bundle, q)]
    exposed += [x for x in shown if isinstance(x, (list, tuple)) and len(x) == 2]
    exposed = list(dict.fromkeys((str(k), str(i)) for k, i in exposed))
    if exposed:
        def change(b):
            for kind, tid in exposed:
                M.record_exposure(b, kind, tid, EXPOSURE_COMMAND)
            return b
        try:
            M.mutate(bundle_dir, change)
        except M.MutationRefused as exc:
            raise SiteRefused(f"The values the cards show could not be recorded as shown ({exc}); nothing was "
                              "exported.", code=exc.code) from exc

    public = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]
    used_sections = {c["section"] for c in public}
    site_data = {
        "format": FORMAT_ID, "format_version": FORMAT_VERSION, "bundle_id": bundle.get("bundle_id"),
        "bundle_version": M.bundle_version(bundle_dir),
        "title": str((bundle.get("source_root") or {}).get("label") or bundle_dir.name),
        "generated_at": _now(),
        "totals": {"records": len(view.exportable), "cards": len(public),
                   "blocking_cards": sum(1 for c in public if c["blocking"])},
        "sections": [dict(s) for s in SECTIONS if s["id"] in used_sections],
        "cards": public,
    }
    (data_dir / "site-data.json").write_text(json.dumps(site_data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    template = Path(site_template).expanduser() if site_template is not None else default_template()
    copied = False
    if template.is_dir():
        def skip(folder, names):
            hidden = set(_TEMPLATE_SKIP(folder, names))
            if Path(folder).resolve() == template.resolve():
                hidden.update(TEMPLATE_ROOT_SKIP)  # its sample data never replaces (or sits beside) the real export
            return hidden
        shutil.copytree(template, out, dirs_exist_ok=True, ignore=skip)
        copied = True

    covered = {q["question_id"] for c in cards for q in c["_questions"]}
    blocking_total = sum(1 for q in payload["questions"] if q.get("blocking"))
    by_section = Counter(c["section"] for c in public)
    return {
        "format": "isaac.question_site_export", "format_version": FORMAT_VERSION, "out": str(out),
        "site_data": str(data_dir / "site-data.json"), "bundle_id": bundle.get("bundle_id"),
        "title": site_data["title"], "include": list(include),
        "cards": len(public), "blocking_cards": site_data["totals"]["blocking_cards"],
        "cards_by_section": {s["id"]: by_section[s["id"]] for s in SECTIONS if by_section.get(s["id"])},
        "questions_open": len(payload["questions"]), "questions_blocking": blocking_total,
        "questions_covered": len(covered),
        "blocking_questions_covered": len({q["question_id"] for q in asked if q.get("blocking")}),
        "left_out": dict(sorted(left.items(), key=lambda kv: (-kv[1], kv[0]))),
        "with_suggestion": sum(1 for c in public if c["suggestion"]),
        "suggestions_file": suggestion_report, "suggestions_dropped": dropped_suggestions,
        "images": len(set(images)), "exposures_recorded": len(exposed),
        "site_template": str(template) if copied else None,
        "site_template_note": (f"Site copied from {template.name!r}: the folder deploys as it is." if copied else
                               f"No site template at {str(template)!r}: only data/ was written. Copy the site's "
                               "files beside it (or pass --site-template) before deploying."),
    }


def _first_sentence(text: str | None) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    cut = re.split(r"(?<=[.!?])\s", s, maxsplit=1)[0]
    return (cut if len(cut) <= 160 else cut[:157] + "...").rstrip(".")


def _without_quotes(text: str) -> str:
    """``text`` without what it quotes from the files ('...'): a file's own words may hold a dot or an underscore."""
    return re.sub(r"“[^”]*”|'[^']*'", "''", str(text or ""))


def render_export(rep: Mapping) -> str:
    out = [f"Question site export: {rep['title']} -> {rep['out']}",
           f"{rep['cards']} card(s), {rep['blocking_cards']} blocking; they cover {rep['questions_covered']} of "
           f"{rep['questions_open']} open question(s) ({rep['blocking_questions_covered']} of "
           f"{rep['questions_blocking']} blocking).", "", "Cards by section:"]
    titles = {s["id"]: s["title"] for s in SECTIONS}
    out += [f"  {titles[k]}: {v}" for k, v in rep["cards_by_section"].items()] or ["  (none)"]
    out += ["", f"{rep['with_suggestion']} card(s) carry a suggestion; {rep['images']} image(s) copied; "
                f"{rep['exposures_recorded']} shown value(s) recorded in the bundle's exposure log."]
    if rep["left_out"]:
        out += ["", "Questions left out, and why:"]
        out += [f"  {n}: {why}" for why, n in rep["left_out"].items()]
    hints = rep["suggestions_file"]
    if hints:
        out += ["", f"--suggestions: {len(hints)} entr{'y' if len(hints) == 1 else 'ies'}; "
                    f"{sum(1 for h in hints if h['suggested_on'])} became a suggestion, "
                    f"{sum(1 for h in hints if h['context_on'] and not h['suggested_on'])} are shown as context only, "
                    f"{sum(1 for h in hints if h.get('problem'))} not used."]
        problems: dict[str, list[int]] = {}
        for h in hints:
            if h.get("problem"):
                problems.setdefault(h["problem"], []).append(h["entry"] + 1)
        out += [f"  not used ({why}): entr{'y' if len(ns) == 1 else 'ies'} {', '.join(map(str, ns))}"
                for why, ns in problems.items()]
    for s in rep["suggestions_dropped"]:
        out.append(f"  suggestion dropped from \"{s['title']}\": {s['why']}")
    out += ["", rep["site_template_note"], f"Data: {rep['site_data']}"]
    return "\n".join(out)
