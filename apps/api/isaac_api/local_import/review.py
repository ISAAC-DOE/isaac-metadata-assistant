"""``isaac bundle review <dir>``: the END REVIEW of the built records (1.21.0, slice 4 of DEC-96, DEC-99).

The project owner's direction (2026-11-25): "at the end, when the user has the final version of the record output, we
can just have them review that". After ``build-records`` this lists every value a registered rule FILLED that the built
records carry — grouped by field, with how many values and how many records, the rule in plain words and a witness a
beamline scientist accepts at a glance (for the environment convention, the scientist's answer and how many
measurements it reached) — and, separately, the processing rule's scan keep / drop decisions with their reasons, read
from the stored processing results (never re-derived).

* ``review <dir> [--field <path> ...]`` READS ONLY: nothing is written to ``bundle.json``; the values it prints are
  recorded beside it in ``exposures.pending.jsonl``, as every read does (1.17.0). It prints a LISTING DIGEST
  (:func:`listing_digest`) over exactly the values it lists, inside the accept command it proposes.
* ``review <dir> [--field ...] --accept --by "<name>" --listing <digest>`` previews the ONE ``review`` decision it would
  record; with ``--apply`` it records it, and only when the listing is still the one that digest names: the scientist
  accepts what they were shown, never what the listing holds by the time they answer. The decision binds each listed
  fill by its target, value, rule and evidence hash (``bundle.review_item``); each bound fill then derives
  ``scientist_confirmed`` (``review.basis`` ``reviewed_final_records``) until any part of it changes. A change is not
  made here: the scientist corrects a value with ``decide`` and runs ``build-records`` again. Answer memory never
  learns a review.

1.22.0 (DEC-100): every listed value carries its COLOUR (``bundle.value_colour``): the GUESSES (an inferred reading,
``guessed``) are listed under their own heading with the quote they rest on, then the values a rule DEDUCED (yellow
too), then the values read from the files (green). ``--accept`` covers all of them, guesses included, and binds each as
before; a bound guess is ``scientist_confirmed`` (green) until any part of it changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B

#: what ``bundle review`` names its exposures by
EXPOSURE_COMMAND = "bundle review"
#: the evidence a witness may be (a draft entry the scientist can open: a document line, a file listing, a sheet cell)
_WITNESS_TYPES = ("document", "file_listing", "spreadsheet")
#: each registered rule, in plain words (why the value is what it is)
RULE_WORDS: Mapping[str, str] = {
    B.FILL_PARSER_EXACT_RULE_ID: "ISAAC's reader read it from the files, and nothing in them disagrees",
    B.FILL_STORED_CONVENTION_RULE_ID: ("the file name says the sample was measured dry or with no electrolyte, which "
                                       "the stored convention reads as ex situ"),
    B.FILL_DOMAIN_RULE_ID: "every measurement was read from the beamline's own acquisition files",
    B.FILL_READING_STATED_RULE_ID: ("a line in the files states it word for word, and the quote was checked against "
                                    "the file"),
    B.FILL_ENVIRONMENT_RULE_ID: ("the measurement was held at a potential its own files give, something shows it was "
                                 "electrochemical, and you gave this beamtime's word for such measurements"),
    B.FILL_FACILITY_RULE_ID: "the folder name and the scan headers name the same facility and beamline",
    B.FILL_ORGANIZATION_RULE_ID: ("the organization that produced the data is the facility the folder name and the "
                                  "scan headers agree on"),
    B.FILL_GROUP_RULE_ID: "the folder name gives the PI, and another file agrees",
    B.FILL_READING_INFERRED_RULE_ID: ("my best reading of a line in your files, which suggests it but does not say it "
                                      "word for word; the quote was checked against the file"),
    B.FILL_SETPOINT_NAME_RULE_ID: ("worked out from the run's own file name, which writes this one potential (e.g. "
                                   "100mV, m800mV for -0.8 V), read as it is written"),
    B.FILL_CONTROL_MODE_RULE_ID: ("worked out from the run's own set-point: a run held at a potential with no current "
                                  "set is potentiostatic (an OCV in its name: open circuit)"),
}
#: 1.22.0 (DEC-100): the three parts of the listing, in order: (key, heading, which values)
SECTIONS = (
    ("guesses", "Guesses — the skill's best reading, please check", "guess"),
    ("deductions", "Worked out by a rule from other values — please check", "deduction"),
    ("read", "Read from your files", "read"),
)


def _kind_of(rule: str | None) -> str:
    """``guess`` (a guess rule), ``deduction`` (another yellow rule) or ``read`` (a green rule), by the colour table."""
    if rule in B.GUESS_RULES:
        return "guess"
    return "deduction" if B.value_colour(B.STATE_FILLED, rule) == B.COLOUR_YELLOW else "read"


def _guess_witness(evidence: Sequence[Mapping]) -> dict | None:
    """A guess's witness: the shortest quote of the INFERRED reading(s) it rests on, with the file and the line."""
    quoted = [e for e in evidence if isinstance(e, Mapping) and e.get("method") == "ai_interpretation"
              and e.get("strength") == "inferred" and e.get("quote")]
    best = _shortest(quoted)
    return _quoted(best) if best is not None else None
#: the words a field is listed under, where the record's own word differs from the questions' (review 17: the record
#: field is ``attribution.produced_by.organization``, so the review says "organization")
FIELD_WORDS: Mapping[str, str] = {B.ORGANIZATION_FILL_PATH: "organization"}
POTENTIAL_PATH = B.POTENTIAL_SETPOINT_PATH
SCALE_PATH = "context.electrochemistry.potential_scale"
#: a unit a field's own NAME carries, as it is said beside a number
_UNIT_OF_SUFFIX = (("_mA_cm2", "mA/cm²"), ("_eV", "eV"), ("_V", "V"), ("_K", "K"), ("_M", "M"))
_MOTOR = re.compile(r"`([A-Za-z_][\w.]*)`")
_EMISSION_MOTORS = frozenset({"emiss", "emission"})
_NUMBER = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")


class ReviewRefused(Exception):
    """The review cannot be listed or recorded as asked; nothing was written. ``code`` is the CLI exit code."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


# --- words ------------------------------------------------------------------------------------------------------------


def field_words(path: str) -> str:
    if path in FIELD_WORDS:
        return FIELD_WORDS[path]
    from .plain_questions import field_label

    try:
        return field_label(path)
    except Exception:  # a path with no noun: its last part, in words
        return path.rsplit(".", 1)[-1].replace("_", " ")


def unit_of(path: str) -> str | None:
    """The unit a field's name carries (``potential_setpoint_V`` -> V), else ``None``."""
    leaf = path.rsplit(".", 1)[-1]
    return next((unit for suffix, unit in _UNIT_OF_SUFFIX if leaf.endswith(suffix)), None)


def value_words(path: str, value: Any, scale: Any = None) -> str:
    """A value as the scientist reads it: a number with its unit (always), a potential with its scale ("0.06 V vs RHE",
    or "scale not stated"), a vocabulary word in words."""
    from .plain_questions import value_label

    unit = unit_of(path) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    said = value_label(value, unit)
    if path == POTENTIAL_PATH:
        said += f" vs {scale}" if isinstance(scale, str) and scale else " (scale not stated)"
    return said


def canonical_field(path: str) -> str:
    """``--field`` as the questions print it or as the record composes it (``context.electrochemistry.reaction`` is the
    record's ``context.reaction.name``)."""
    from .records import FIELD_REMAP

    return FIELD_REMAP.get(path, path)


# --- witnesses ---------------------------------------------------------------------------------------------------------


def _quoted(e: Mapping) -> dict:
    return {"quote": e.get("quote"), "file": e.get("source_file"), "locator": e.get("locator"),
            "by": "a Claude reading of the files" if e.get("method") == "ai_interpretation" else "the files"}


def _shortest(entries: Sequence[Mapping]) -> Mapping | None:
    return min(entries, key=lambda e: (len(str(e.get("quote") or "")) if e.get("quote") else 10_000,
                                       str(e.get("source_file") or "")), default=None)


#: a SPEC login line (`#C ... User = <account>`): it names an account, never the facility (round 2, minor 3)
_LOGIN_LINE = re.compile(r"(?i)\buser\s*=")
#: where the composer cites the imported folder's own name (``bundle._folder_witness``)
FOLDER_LOCATOR = "the imported folder's name"
TECHNIQUE_PATH = "system.technique"


def names_token(quote: Any, words: Iterable[str]) -> bool:
    """Whether ``quote`` names one of ``words`` as a whole token (case aside: "SSRL" in "SSRL BL15-2", never in
    "ssrl_bob"), and is no login line."""
    text = str(quote or "")
    if _LOGIN_LINE.search(text):
        return False
    return any(w and re.search(rf"(?i)(?<![\w]){re.escape(str(w))}(?![\w])", text) for w in words)


def _same_number(text: Any, value: Any) -> bool:
    try:
        return float(str(text).strip()) == float(value)
    except (TypeError, ValueError):
        return False


def _header_phrase(e: Mapping, path: str, value: Any) -> str | None:
    """A bare number from a scan header said as what it is (review 16), ONLY where that number is what the value rests
    on (round 2): the emission analyser's energy for the technique it shows (HERFD), or a header number that IS the
    value shown. Never a motor position beside some other value."""
    quote = str(e.get("quote") or "").strip()
    motor = _MOTOR.search(str(e.get("locator") or ""))
    if not _NUMBER.match(quote) or motor is None:
        return None
    name = motor.group(1)
    emission = name.casefold() in _EMISSION_MOTORS
    if path == TECHNIQUE_PATH and emission:
        return f"the emission analyser (motor `{name}`) is set to {quote} eV in the scan header"
    if isinstance(value, (int, float)) and not isinstance(value, bool) and _same_number(quote, value):
        return (f"the emission analyser (motor `{name}`) is set to {quote} eV in the scan header" if emission
                else f"motor `{name}` is at {quote} in the scan header")
    return None


def _supports(e: Mapping, value: Any) -> bool:
    """A witness OF this value: a file entry whose relation is ``supports`` (or unstated), and, for a number, not a
    bare number that is another one (round 2: a contradicting "7" is never shown for 0.5)."""
    if not isinstance(e, Mapping) or e.get("source_type") not in _WITNESS_TYPES:
        return False
    if e.get("relation") not in (None, "supports"):
        return False
    quote = str(e.get("quote") or "").strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and _NUMBER.match(quote):
        return _same_number(quote, value) or _MOTOR.search(str(e.get("locator") or "")) is not None
    return True


def witness(rule: str | None, path: str, value: Any, evidence: Sequence[Mapping], *, files: int = 0,
            names: Sequence[str] = (), header: Mapping | None = None) -> dict | None:
    """The witness a beamline scientist accepts at a glance, per rule (review 13-16, round 2), from the evidence of THIS
    value only (the caller pools it per field and value), and only entries that support it:

    * the facility, beamline and organization: the beamtime folder's name the rule read (found by its locator), then a
      scan-header line that names the facility or beamline as a whole word (``names``; ``header``, a line the caller
      found in the runs' own headers), never a ``User = <login>`` line;
    * the group: the folder's name, then the agreeing readme or data-path line;
    * the domain: no quote, "read from N of the beamline's own acquisition files";
    * a header number by its motor, said as what the motor is, only where that number is what the value rests on;
    * otherwise the shortest supporting quote of a file line (a checked Claude reading's quote included), else the file
      and locator. Never the rule's own derivation entry, never an answer, never a contradicting line."""
    quoted = [e for e in evidence if _supports(e, value)]
    if rule == B.FILL_DOMAIN_RULE_ID:
        return {"text": f"read from {files} of the beamline's own acquisition files", "by": "the files"}
    if rule in (B.FILL_FACILITY_RULE_ID, B.FILL_ORGANIZATION_RULE_ID, B.FILL_GROUP_RULE_ID):
        folder = next((e for e in quoted if e.get("source_type") == "file_listing"
                       and e.get("locator") == FOLDER_LOCATOR), None)
        # a header line counts only when it NAMES the value (the facility, the beamline; the PI's name for a group)
        words = list(names) or ([str(value)] if rule != B.FILL_GROUP_RULE_ID
                                else [w for w in str(value).split() if len(w) > 3 and w.casefold() != "group"])
        if rule == B.FILL_GROUP_RULE_ID:
            # the group's second source IS the corroboration its basis recorded (the readme's month header, a #F data
            # path, a contributor, a labelled full name: bundle.folder_fill_witnesses), so it is shown as recorded; a
            # whole-word test would refuse "# 2031-01_Quillfeather" (the surname glued to the month by "_")
            line = next((e for e in quoted if e.get("source_type") == "document"
                         and not _LOGIN_LINE.search(str(e.get("quote") or ""))), None)
        else:
            line = next((e for e in quoted if e.get("source_type") == "document" and names_token(e.get("quote"), words)),
                        None)
        if line is None and header is not None and names_token(header.get("quote"), words):
            line = header
        if folder is None and line is None:
            return None
        out = {"text": f"the beamtime folder's name, {folder.get('quote')}", "by": "the files"} if folder else _quoted(line)
        if folder is not None and line is not None:
            out["also"] = _quoted(line)
        return out
    for e in quoted:
        phrase = _header_phrase(e, path, value)
        if phrase:
            return {"text": phrase, "file": e.get("source_file"), "locator": e.get("locator"), "by": "the files"}
    plain = [e for e in quoted if not (_NUMBER.match(str(e.get("quote") or "").strip())
                                       and _MOTOR.search(str(e.get("locator") or "")))]
    best = _shortest(plain)
    return _quoted(best) if best is not None else None


def _environment_witness(bundle: Mapping, ctx: Mapping, obj_of: Mapping, targets: Sequence[str]) -> dict | None:
    """Both halves of the held-potential rule (round 4, minor 2), from the basis of one of THIS row's values: the run's
    own set-point as its file writes it, and what shows the measurement was electrochemical (a file value, the checked
    quote of a reading, or the scientist's answer to such a field)."""
    for tid in targets:
        _, obj = obj_of.get(tid, (None, None))
        basis = B.environment_fill_basis(obj, ctx) if obj else None
        if not basis:
            continue
        idx = B._witness_index(bundle, ctx)
        setpoint = next((w for cid in basis["setpoints"] for w in B._candidate_witnesses(idx["cands"].get(cid) or {}, 1)),
                        None)
        also = None
        for kind, ref in basis["corroboration"]:
            if kind == "candidate" and ref in idx["cands"]:
                w = next(iter(B._candidate_witnesses(idx["cands"][ref], 1)), None)
                also = _quoted(w) if w else None
            elif kind == "reading" and ref in idx["readings"]:
                also = _quoted(B._reading_witness(idx["readings"][ref]))
            elif kind == "decision" and ref in idx["decisions"]:
                d = idx["decisions"][ref]
                t = d.get("target") or {}
                path = (idx["cands"].get(t.get("id")) or {}).get("target_field_path") or next(
                    (m.get("target_field_path") for m in bundle.get("missing_values") or ()
                     if m.get("value_id") == t.get("id")), None)
                also = {"text": f"your answer: {field_words(path) if path else 'a field'} "
                                f"{value_words(path or '', d.get('value'))}", "by": "you"}
            if also:
                break
        out = _quoted(setpoint) if setpoint else None
        if out is None:
            return also
        if also:
            out["also"] = also
        return out
    return None


def _header_index(bundle: Mapping) -> dict[str, list[dict]]:
    """``{source id: [header line witnesses]}``: each source's scan-header lines (``extended_context`` statements
    located in a header), for the facility's second source (round 2, minor 2). Built once per listing."""
    source_of = {s.get("source_id"): s for s in bundle.get("sources") or ()}
    out: dict[str, list[dict]] = {}
    for e in bundle.get("extended_context") or ():
        sid, lit = e.get("source_id"), e.get("raw_literal")
        if not sid or not isinstance(lit, str) or "header" not in str(e.get("locator") or "").lower():
            continue
        out.setdefault(sid, []).append({"source_type": "document", "quote": lit, "locator": e.get("locator"),
                                        "source_file": (source_of.get(sid) or {}).get("relative_path"),
                                        "method": "deterministic_parser", "relation": "supports"})
    return out


def _naming_header(bundle: Mapping, index: Mapping[str, list[dict]], run_ids: Iterable[str],
                   words: Sequence[str]) -> dict | None:
    """The first header line of these runs' own files that names one of ``words`` as a whole word (no login line)."""
    runs = {r.get("run_id"): r for r in bundle.get("runs") or ()}
    for rid in sorted(run_ids):
        r = runs.get(rid) or {}
        for sid in [r.get("acquisition_source_id"), *(sc.get("source_id") for sc in r.get("scans") or ())]:
            for h in index.get(sid) or ():
                if names_token(h["quote"], words):
                    return h
    return None


# --- the listing -------------------------------------------------------------------------------------------------------


def _drafts_built(bundle_dir: Path) -> bool:
    from . import records as R

    return (bundle_dir / R.DRAFTS_DIR / "index.json").is_file()


def listing_digest(items: Sequence[Mapping], fields: Sequence[str] | None) -> str:
    """THE LISTING DIGEST (review 1): 16 hex of the sha256, in canonical JSON, of exactly the items a listing holds
    (each target, value, rule and evidence hash) and its field filter. `--accept --apply` records only while the listing
    for the same filter still has this digest, so the scientist accepts what they were shown."""
    payload = {"fields": sorted(set(fields)) if fields else None,
               "items": sorted(items, key=lambda i: (i["target"]["kind"], i["target"]["id"]))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
                          ).hexdigest()[:16]


def _scan_decisions(bundle: Mapping, groups: Sequence[str], labels: Mapping[str, str]) -> list[dict]:
    """The processing rule's keep / drop decisions, AS STORED on each composed group's processing result (the approved
    one when there is one, else every result of the group that is not ``not_applicable``): per group, the counts, each
    dropped scan with its reasons, each scan the scientist decided themselves, and the curve's plot file."""
    out = []
    by_group: dict[str, list[Mapping]] = {}
    wanted = set(groups)
    for r in bundle.get("processing_results") or ():
        if isinstance(r, Mapping) and r.get("group_id") in wanted and not B.processing_not_applicable(r):
            by_group.setdefault(r["group_id"], []).append(r)
    for gid in groups:
        results = by_group.get(gid) or []
        approved = [r for r in results if r.get("state") == B.STATE_SCIENTIST_CONFIRMED]
        for r in approved or results:
            table = r.get("scan_decisions")
            if not isinstance(table, Mapping):
                continue
            rows = [x for x in table.get("rows") or () if isinstance(x, Mapping)]

            def said(x: Mapping) -> dict:
                return {"run": x.get("run") or x.get("file"), "scan": x.get("scan"), "decision": x.get("decision"),
                        "by": "the scientist" if x.get("decided_by") == "scientist" else "the rule",
                        "reasons": [y.get("said") for y in x.get("reasons") or () if isinstance(y, Mapping)
                                    and y.get("said")]}

            dropped = [x for x in rows if x.get("decision") == "drop"]
            plot = next((f.get("relative_path") for f in (r.get("outputs") or {}).get("files") or ()
                         if isinstance(f, Mapping) and "plot" in str(f.get("role") or "")), None)
            out.append({"group_id": gid, "group": labels.get(gid, gid), "result_id": B.processing_id(r),
                        "approved": r.get("state") == B.STATE_SCIENTIST_CONFIRMED, "rule_id": table.get("rule_id"),
                        "kept": sum(1 for x in rows if x.get("decision") == "keep"), "dropped": [said(x) for x in dropped],
                        "decided_by_scientist": [said(x) for x in rows if x.get("decided_by") == "scientist"
                                                 and x.get("decision") != "drop"], "plot": plot})
    return out


def _acquisition_files(bundle: Mapping, run_ids: Iterable[str]) -> int:
    runs = {r.get("run_id"): r for r in bundle.get("runs") or ()}
    return len({(runs.get(rid) or {}).get("acquisition_source_id") for rid in run_ids if rid in runs} - {None})


def _listing(bundle_dir: Path, bundle: Mapping, *, fields: Sequence[str] | None) -> dict:
    """What the review lists, composed NOW from the validated bundle (the drafts ``build-records`` wrote are compared
    with it). ``fields``: canonical paths (``canonical_field``), or ``None`` for every field. Refused (exit 2) when a
    named field is in no built record at all (a mistyped path), naming the fields that are."""
    from . import records as R

    marker = bool((bundle.get("self_test") or {}).get("test_marker"))
    composed = R.fresh_compositions(bundle_dir, bundle, test_marker=marker)
    stale = [gid for gid, draft, _ in composed if not (bundle_dir / R.DRAFTS_DIR / f"{gid}.draft.json").is_file()
             or R._on_disk_differs(bundle_dir, gid, draft, {})]
    wanted = set(fields) if fields else None
    if wanted:
        carried = {p for _, draft, _ in composed for p, env in (draft.get("fields") or {}).items()
                   if isinstance(env, Mapping) and env.get("value") is not None}
        unknown = sorted(wanted - carried)
        if unknown:
            reviewable = sorted({e["path"] for _, _, comp in composed for e in comp.get("filled_by_rule") or ()})
            raise ReviewRefused(
                f"No built record has the field {', '.join(unknown)}. Fields with filled values waiting for review: "
                + (", ".join(f"{p} ({field_words(p)})" for p in reviewable) or "none") + ".", code=2)
    obj_of = {**{c["candidate_id"]: ("candidate", c) for c in bundle["candidates"]},
              **{m["value_id"]: ("missing_value", m) for m in bundle["missing_values"]}}
    ctx = B.fill_context(bundle)
    labels = R.group_labels(bundle)
    targets: dict[str, dict] = {}
    rows: dict[tuple, dict] = {}
    reviewed_earlier: set[str] = set()
    for gid, draft, comp in composed:
        dfields = draft.get("fields") or {}
        scale = (dfields.get(SCALE_PATH) or {}).get("value")
        for entry in comp.get("reviewed_by_rule") or ():
            if wanted is None or entry["path"] in wanted:
                reviewed_earlier.update(entry["from"])
        for entry in comp.get("filled_by_rule") or ():
            path = entry["path"]
            if wanted is not None and path not in wanted:
                continue
            env = dfields.get(path) or {}
            for tid in entry["from"]:
                kind, obj = obj_of.get(tid, (None, None))
                if obj is None or obj.get("value_state") not in B.FILL_STATES:  # 1.22.0: a guess too
                    continue
                rule = (obj.get("fill") or {}).get("rule_id")
                value = B.fill_value(obj)
                qualifier = scale if path == POTENTIAL_PATH else None
                key = (path, json.dumps(value, sort_keys=True, default=str), rule, qualifier)
                row = rows.get(key)
                if row is None:  # indexed by key: never a rescan of every row per group (review 10)
                    row = rows[key] = {"path": path, "value": value, "rule_id": rule, "scale": qualifier,
                                       "groups": set(), "targets": [], "evidence": [], "runs": set()}
                if gid not in row["groups"]:
                    row["groups"].add(gid)
                    row["evidence"].extend(env.get("evidence") or ())
                    row["runs"].update(comp.get("member_run_ids") or ())
                if tid not in targets:
                    targets[tid] = B.review_item(bundle, kind, obj, ctx)
                    row["targets"].append(tid)
    conv = B.environment_convention_decision(bundle)
    reached = sum(1 for m in bundle["missing_values"] if (m.get("fill") or {}).get("rule_id") == B.FILL_ENVIRONMENT_RULE_ID
                  and m.get("value_state") in (*B.FILL_STATES, B.STATE_SCIENTIST_CONFIRMED))
    out_fields: list[dict] = []
    headers: dict | None = None
    for path in sorted({r["path"] for r in rows.values()}, key=lambda p: (field_words(p), p)):
        values = []
        mine = [r for r in rows.values() if r["path"] == path]
        for row in sorted(mine, key=lambda r: (-len(r["groups"]), json.dumps(r["value"], sort_keys=True, default=str))):
            names, header = (), None
            if row["rule_id"] in (B.FILL_FACILITY_RULE_ID, B.FILL_ORGANIZATION_RULE_ID):
                names = [str(row["value"])]  # round 4: the field's OWN value (a beamline row never shows a facility line)
                if headers is None:
                    headers = _header_index(bundle)
                header = _naming_header(bundle, headers, row["runs"], names)
            kind = _kind_of(row["rule_id"])
            item = {"value": row["value"], "value_words": value_words(path, row["value"], row["scale"]),
                    "records": len(row["groups"]), "values": len(row["targets"]), "rule_id": row["rule_id"],
                    "rule": RULE_WORDS.get(row["rule_id"], row["rule_id"]),
                    # 1.22.0 (DEC-100): the value's colour, and whether it is a guess or a deduction (both yellow)
                    "colour": B.value_colour(B.STATE_GUESSED if kind == "guess" else B.STATE_FILLED, row["rule_id"]),
                    "kind": kind,
                    "witness": (_guess_witness(row["evidence"]) if kind == "guess" else None) or witness(
                        row["rule_id"], path, row["value"], row["evidence"],
                        files=_acquisition_files(bundle, row["runs"]), names=names, header=header),
                    "target_ids": sorted(row["targets"]), "group_ids": sorted(row["groups"])}
            if path == POTENTIAL_PATH:
                item["scale"] = row["scale"]
            if row["rule_id"] == B.FILL_ENVIRONMENT_RULE_ID:
                item["witness"] = _environment_witness(bundle, ctx, obj_of, row["targets"]) or item["witness"]
            if row["rule_id"] == B.FILL_ENVIRONMENT_RULE_ID and conv is not None:
                given = conv.get(B.ENVIRONMENT_CONVENTION_COVERS_KEY)
                item["convention"] = {"answer": conv.get("value"),
                                      "answer_words": value_words(B.ENVIRONMENT_PATH, conv.get("value")),
                                      "decision_id": conv.get("decision_id"),
                                      "given_for": len(given) if isinstance(given, list) else None, "reached": reached}
            values.append(item)
        out_fields.append({"path": path, "field": field_words(path), "values": values,
                           "values_total": sum(v["values"] for v in values),
                           "records_total": len({g for r in mine for g in r["groups"]})})
    items = [targets[t] for t in sorted(targets)]
    listed = {i["target"]["id"] for i in items}
    changed = B.review_changed_since(bundle)
    return {"items": items, "fields": out_fields, "reviewed_earlier": len(reviewed_earlier),
            "changed_since": [{**c, "listed": c["id"] in listed} for c in changed],
            "scan_decisions": _scan_decisions(bundle, [gid for gid, _, _ in composed], labels),
            "records": len(composed), "records_stale": stale, "groups_live": _live_groups(bundle),
            "digest": listing_digest(items, sorted(wanted) if wanted else None)}


def _live_groups(bundle: Mapping) -> int:
    return sum(1 for g in bundle.get("record_groups") or () if g.get("status") in B.LIVE_GROUP_STATUSES)


def _load(bundle_dir: Path) -> dict:
    from . import records as R

    try:
        return R.load_validated(bundle_dir)
    except R.RecordsRefused as exc:
        raise ReviewRefused(str(exc), code=exc.code) from None


def _canonical_fields(fields: Sequence[str] | str | None) -> list[str] | None:
    if fields is None:
        return None
    if isinstance(fields, str):
        fields = [fields]
    return sorted({canonical_field(f) for f in fields if f}) or None


def _changed_words(changed: Sequence[Mapping]) -> dict:
    """What became of the reviewed values that changed since (review 3): filled again and listed now, filled again but
    in no built record, or now asked (no rule fills it any more, e.g. the convention answered per measurement)."""
    filled = [c for c in changed if c.get("now") in B.FILL_STATES]
    return {"total": len(changed), "listed_again": sum(1 for c in filled if c.get("listed")),
            "filled_outside_records": sum(1 for c in filled if not c.get("listed")),
            "now_asked": len(changed) - len(filled)}


def review(bundle_dir: Path, *, fields: Sequence[str] | str | None = None, limit: int | None = None,
           shown_as: str | None = None) -> dict:
    """The review listing (module docstring). READS ONLY; refused before ``build-records`` has run, and for a field no
    built record has. ``fields``: ``--field`` paths (repeatable; either form, :func:`canonical_field`)."""
    from . import mutations as M

    bundle_dir = Path(bundle_dir)
    d = shown_as or bundle_dir.name
    wanted = _canonical_fields(fields)
    with M.locked(bundle_dir):  # review 9: the version and the bundle the listing is made from are ONE read
        version = M.bundle_version(bundle_dir)
        bundle = _load(bundle_dir)
    if not _drafts_built(bundle_dir):
        raise ReviewRefused(_not_built(bundle, d), code=1)
    out = _listing(bundle_dir, bundle, fields=wanted)
    shown = out["fields"] if limit is None else out["fields"][:limit]
    shown_ids = {t for f in shown for v in f["values"] for t in v["target_ids"]}
    exposed = [(t["target"]["kind"], t["target"]["id"]) for t in out["items"] if t["target"]["id"] in shown_ids]
    if exposed:
        M.record_exposures(bundle_dir, [(exposed, EXPOSURE_COMMAND)])  # beside bundle.json, which a read never writes
    kinds = {k: sum(v["values"] for f in out["fields"] for v in f["values"] if v["kind"] == k) for _, _, k in SECTIONS}
    return {
        "records": out["records"],
        "records_built_since_last_change": not out["records_stale"],
        "fields_filter": wanted,
        "values_to_review": len(out["items"]),
        # 1.22.0 (DEC-100): how many of them are guesses, deductions and reads (yellow, yellow, green)
        "values_by_kind": kinds,
        "fields_total": len(out["fields"]),
        "fields": shown,
        **({"fields_not_shown": len(out["fields"]) - len(shown)} if len(shown) < len(out["fields"]) else {}),
        "reviewed_earlier": out["reviewed_earlier"],
        "reviewed_changed_since": _changed_words(out["changed_since"]),
        "scan_decisions": out["scan_decisions"],
        "bundle_version": version,
        **({"listing": out["digest"]} if out["items"] and len(shown) == len(out["fields"]) else {}),
        "next": _next(out, d, wanted, complete=len(shown) == len(out["fields"])),
    }


def _not_built(bundle: Mapping, d: str) -> str:
    """Why there is nothing to review before any record is built (review 19), and the step that builds one."""
    q = shlex.quote(d)
    if not any(g.get("status") == B.STATE_SCIENTIST_CONFIRMED for g in bundle.get("record_groups") or ()):
        return _next({"records": 0, "groups_live": _live_groups(bundle)}, d, None)
    return f"No record is built yet, so there is nothing to review. Run `isaac bundle build-records {q}` first."


def _field_args(fields: Sequence[str] | None) -> str:
    return "".join(f" --field {shlex.quote(f)}" for f in fields or ())


def _next(out: Mapping, d: str, fields: Sequence[str] | None, *, complete: bool = True) -> str:
    q = shlex.quote(d)
    if not out["records"]:
        if out["groups_live"]:
            return (f"No record is built yet: no record group is confirmed. Confirm the groups the scientist agrees with "
                    f"(`isaac bundle list {q} groups`), then `isaac bundle build-records {q}` and review again.")
        return f"No record is built yet: propose the record groups (`isaac bundle group {q}`) first."
    if out["records_stale"]:
        return (f"The records changed since they were built: run `isaac bundle build-records {q}` again, then review "
                "them.")
    if not out["items"]:
        return ("Nothing filled is waiting for review" + (f" in {', '.join(fields)}" if fields else "") + ".")
    if not complete:
        return "Show every field first (drop --limit): the accept command needs the whole listing."
    return (f"If it all looks right: `isaac bundle review {q}{_field_args(fields)} --accept --by \"<your name>\" "
            f"--listing {out['digest']}` (a preview), then the same with --apply. To change a value: `isaac bundle "
            f"decide` with the correction, then `isaac bundle build-records {q}` again.")


def accept(bundle_dir: Path, *, by: str, orcid: str | None = None, note: str | None = None,
           fields: Sequence[str] | str | None = None, apply: bool = False, listing: str | None = None,
           expected_version: str | None = None, shown_as: str | None = None) -> dict:
    """``--accept``: the ONE ``review`` decision over every fill the review lists now for ``fields`` (repeatable; all
    fields when none). A preview unless ``apply``. ``--apply`` REQUIRES ``listing`` (the digest ``bundle review``
    printed) and records only while the listing for the same fields still has it. Refused when the records changed
    since ``build-records``, when nothing is waiting, or when ``expected_version`` is given and the bundle moved."""
    from . import mutations as M

    problem = B.decider_name_problem(by)
    if problem:
        raise ReviewRefused(f"--by is required: the name of the person who reviewed the records (this one {problem}).")
    if orcid is not None and not M.ORCID_RE.fullmatch(orcid):
        raise ReviewRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).")
    if apply and not listing:
        raise ReviewRefused("--apply needs --listing <digest>: the one `isaac bundle review` printed with the values the "
                            "scientist saw, so only those are recorded. Run `isaac bundle review` and show them first. "
                            "Nothing was recorded.")
    bundle_dir = Path(bundle_dir)
    d = shown_as or bundle_dir.name
    wanted = _canonical_fields(fields)
    with M.locked(bundle_dir):
        try:
            M._require_version(bundle_dir, expected_version)
        except M.MutationRefused as exc:
            raise ReviewRefused(str(exc), code=exc.code) from None
        version = M.bundle_version(bundle_dir)
        bundle = _load(bundle_dir)
        if not _drafts_built(bundle_dir):
            raise ReviewRefused(_not_built(bundle, d) + " Nothing was recorded.", code=1)
        out = _listing(bundle_dir, bundle, fields=wanted)
        if not out["records"]:
            raise ReviewRefused(_next(out, d, wanted) + " Nothing was recorded.", code=1)
        if out["records_stale"]:
            raise ReviewRefused(f"The records changed since they were built ({len(out['records_stale'])} record(s)), so "
                                f"the review would not be of what the scientist saw: run `isaac bundle build-records {d}` "
                                "and `isaac bundle review` again. Nothing was recorded.", code=1)
        if listing and listing != out["digest"]:
            raise ReviewRefused("The values changed since you were shown them; run `isaac bundle review` again and show "
                                "the scientist what it lists now. Nothing was recorded.", code=1)
        items = out["items"]
        if not items:
            return {"recorded": False, "values": 0,
                    "statement": "Nothing filled is waiting for review; nothing was recorded."}
        if len(items) > B.MAX_REVIEW_ITEMS:
            raise ReviewRefused(f"{len(items)} values are more than one review binds ({B.MAX_REVIEW_ITEMS}); review "
                                "them a few fields at a time (--field). Nothing was recorded.", code=5)
        by_field = {f["path"]: {"field": f["field"], "values": f["values_total"], "records": f["records_total"]}
                    for f in out["fields"]}
        # 1.22.0 (DEC-100): the accept covers the guesses too, and says how many
        guesses = sum(v["values"] for f in out["fields"] for v in f["values"] if v["kind"] == "guess")
        guessed_words = f" ({guesses} of them guesses)" if guesses else ""
        said = "; ".join(f"{x['field']}: {x['values']} value(s) in {x['records']} record(s)" for x in by_field.values())
        if not apply:
            return {"recorded": False, "preview": True, "values": len(items), "records": out["records"],
                    "by_field": by_field, "bundle_version": version,
                    **({"listing_matches": True} if listing else {}),
                    "guesses": guesses,
                    "statement": (f"Would record {by} reviewing {len(items)} filled value(s)" + guessed_words
                                  + f" in {out['records']} "
                                  f"record(s) as right ({said}). Nothing was recorded: add --apply"
                                  + ("." if listing else " with --listing <the digest `bundle review` printed>; it "
                                     "will be refused if the values changed since they were shown."))}
        decisions = bundle.setdefault("scientist_decisions", [])
        if len(decisions) + 1 > B.MAX_SCIENTIST_DECISIONS:
            raise ReviewRefused(M.log_full_message("scientist_decisions", len(decisions), 1, B.MAX_SCIENTIST_DECISIONS),
                                code=5)
        entry = {
            "decision_id": f"d-{len(decisions) + 1:05d}",
            "target": {"kind": "experiment", "id": "experiment"},
            "decision": B.REVIEW_DECISION,
            "value": None,
            "chosen_reading_index": None,
            "decided_by": M._decider(by, orcid),
            "decided_utc": M.now_utc(),
            "method": "scientist_answer",
            "note": note,
            "batch_id": None,
            B.REVIEW_ITEMS_KEY: items,
            B.REVIEW_VERSION_KEY: version,
        }
        decisions.append(entry)
        try:
            M.save_bundle(bundle_dir, bundle)
        except M.MutationRefused as exc:
            raise ReviewRefused(str(exc), code=exc.code) from None
        after = M.load(bundle_dir)
        confirmed = sum(1 for o in [*after["candidates"], *after["missing_values"]]
                        if (o.get("review") or {}).get("decision_id") == entry["decision_id"])
    q = shlex.quote(d)
    nxt = (f"Run `isaac bundle build-records {q}` again so the records carry the confirmation, then `isaac bundle "
           f"review {q}` for what is left" + (" in the other fields" if wanted else "") + ".")
    return {"recorded": True, "decision_id": entry["decision_id"], "values": len(items), "records": out["records"],
            "confirmed_now": confirmed, "by_field": by_field, "next": nxt, "guesses": guesses,
            "statement": (f"Recorded: {by} reviewed {len(items)} filled value(s){guessed_words} in {out['records']} "
                          f"record(s) and said "
                          f"they are right ({said}); {confirmed} are now confirmed. {nxt}")}


# --- plain text --------------------------------------------------------------------------------------------------------


def _witness_line(w: Mapping) -> str:
    where = ", ".join(str(x) for x in (w.get("file"), w.get("locator")) if x)
    if w.get("text"):
        return w["text"] + (f" ({where})" if where else "")
    return (f"\"{w['quote']}\"" + (f" ({where})" if where else "")) if w.get("quote") else where


def render(result: Mapping) -> str:
    """The plain listing: colleague wording, no ids."""
    lines: list[str] = []
    n, recs = result["values_to_review"], result["records"]
    if not recs:
        lines.append("No record is built yet, so there is nothing to review.")
    else:
        if not result["records_built_since_last_change"]:
            lines.append("The records changed since they were last built; build them again before reviewing.")
        only = f" in {', '.join(field_words(f) for f in result['fields_filter'])}" if result.get("fields_filter") else ""
        if n:
            k = result.get("values_by_kind") or {}
            split = "; ".join(x for x in (f"{k['guess']} guess(es)" if k.get("guess") else "",
                                          f"{k['deduction']} worked out by a rule" if k.get("deduction") else "",
                                          f"{k['read']} read from your files" if k.get("read") else "") if x)
            lines.append(f"Filled from the evidence, not yet reviewed{only}: {n} value(s) in {result['fields_total']} "
                         f"field(s), across {recs} built record(s)" + (f" ({split})" if split else "") + ".")
        else:
            lines.append(f"Nothing filled is waiting for review{only} in the {recs} built record(s).")
    if result.get("reviewed_earlier"):
        lines.append(f"Reviewed earlier and still standing: {result['reviewed_earlier']} value(s).")
    ch = result.get("reviewed_changed_since") or {}
    if ch.get("total"):
        parts = [f"{ch['listed_again']} filled again and listed below" if ch.get("listed_again") else "",
                 f"{ch['filled_outside_records']} filled again but in no built record" if ch.get("filled_outside_records")
                 else "",
                 f"{ch['now_asked']} now asked (no rule fills them any more)" if ch.get("now_asked") else ""]
        lines.append(f"Reviewed earlier but changed since (their value, rule or evidence): {ch['total']} value(s): "
                     + "; ".join(p for p in parts if p) + ".")
    for _key, heading, kind in SECTIONS:
        # 1.22.0 (DEC-100): the guesses first, under their own heading, then the deductions, then the values read
        part = [(f, [v for v in f["values"] if v.get("kind", "read") == kind]) for f in result["fields"]]
        part = [(f, vs) for f, vs in part if vs]
        if not part:
            continue
        lines.append("")
        lines.append(f"{heading}:")
        for f, values in part:
            lines.append(f"{f['field'][:1].upper()}{f['field'][1:]}")
            for v in values:
                lines.append(f"  {v['value_words']}: {v['values']} value(s), in {v['records']} record(s). "
                             f"Why: {v['rule']}.")
                c = v.get("convention")
                if c:
                    given = f", given for {c['given_for']} measurement(s)" if c.get("given_for") is not None else ""
                    lines.append(f"    Your answer to the environment question: {c['answer_words']}{given}; it reached "
                                 f"{c['reached']} measurement(s).")
                w = v.get("witness")
                if w:
                    also = w.get("also")
                    lines.append(f"    Shown by {w['by']}: {_witness_line(w)}"
                                 + (f"; and {'by ' + also['by'] + ': ' if also.get('by') != w.get('by') else ''}"
                                    f"{_witness_line(also)}" if also else ""))
    if result.get("fields_not_shown"):
        lines.append(f"\n...and {result['fields_not_shown']} more field(s) (drop --limit to see them all).")
    scans = result.get("scan_decisions") or []
    if scans:
        lines.append("")
        lines.append("Scans kept and dropped (the processing rule decided these; each says why):")
        for s in scans:
            drops = "; ".join(f"{x['run']} scan {x['scan']} dropped" + (f" ({', '.join(x['reasons'])})" if x["reasons"] else "")
                              + (" by the scientist" if x["by"] == "the scientist" else "") for x in s["dropped"])
            lines.append(f"  {s['group']}: {s['kept']} kept, {len(s['dropped'])} dropped" + (f": {drops}" if drops else "")
                         + (f". Curve: {s['plot']}" if s.get("plot") else "") + ".")
    lines.append("")
    lines.append(f"Next: {result['next']}")
    return "\n".join(lines)


# --- the final check before an upload (1.22.0, DEC-100) ----------------------------------------------------------------
#
# The owner's direction (2026-11-28): "before submitting, a final check: these N values are guesses, submit anyway?".
# `bundle upload <records_dir>` reads the records it would send and their evidence files, and lists every YELLOW value
# (``bundle.evidence_colour``: a guess, or a deduction no scientist confirmed), grouped by field and value, with how many
# records carry it and the quote or the rule it rests on. It sends nothing until the scientist's yes comes back as
# ``--guesses-ok <digest>`` over exactly that list; the yes is kept as ONE ``submit_with_guesses`` decision in the
# bundle. The official record has no free-text note to carry the marks (``schema/isaac_record_v1.json`` has no
# record-level note), so the portal copy will not show which values were guesses: the final check says so.

#: What the final check says the portal copy cannot carry (the official schema has no record-level note).
PORTAL_COPY_NOTE = ("The records sent to the portal will not show which values were guesses: the ISAAC record has no "
                    "place for that note. This bundle and the evidence files keep it.")
#: Review I4: this build sends nothing, and the portal never runs this check: said wherever the yes is asked or kept.
UPLOAD_NOTE = ("This build sends nothing: you upload the records folder through the ISAAC portal yourself, and the portal "
               "does not run this check. Your yes is kept in this bundle as the record that the values were sent as "
               "they are.")
#: The most items one final check lists in its decision (the schema's bound on ``guesses_sent``).
MAX_SUBMIT_ITEMS = 5000
#: Review I1: a record whose evidence file is missing or unreadable: what it holds cannot be told, so never green.
UNKNOWN_PATH = "(the whole record)"
UNKNOWN_NO_EVIDENCE = "isaac.final_check.no_evidence_file"
UNKNOWN_DERIVATION = "isaac.final_check.unregistered_derivation"


def _at(record: Mapping, path: str) -> Any:
    """The record's value at a dotted ``path`` (``None`` when absent)."""
    node: Any = record
    for part in path.split("."):
        if not isinstance(node, Mapping):
            return None
        node = node.get(part)
    return node


def _record_files(records_dir: Path) -> list[Path]:
    return [p for p in sorted(Path(records_dir).glob("*.json")) if not p.name.endswith(".evidence.json")]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _deduction_witness(entries: Sequence[Mapping]) -> Mapping | None:
    """A deduction's shortest observed quote (a file line), never its derivation or an answer."""
    quoted = [e for e in entries if isinstance(e, Mapping) and e.get("source_type") in _WITNESS_TYPES and e.get("quote")]
    return _shortest(quoted)


def _yellow_derivations(entries: Sequence[Mapping]) -> list[tuple[Mapping, str]]:
    """``[(derivation, kind)]`` of a field's evidence that keep it yellow (``bundle.evidence_colour``, entry by entry):
    a fill no confirmation names (``guess`` or ``deduction``), or a derivation naming no registered rule (``unknown``)."""
    confirmed = {str(e.get("target_id")) for e in entries if isinstance(e, Mapping)
                 and e.get("source_type") == "user_confirmation" and e.get("target_id") is not None}
    out = []
    for d in entries:
        if not (isinstance(d, Mapping) and d.get("source_type") == "derivation"):
            continue
        rule = d.get("rule")
        if rule in B.FILL_RULES:
            if str(d.get("candidate_id") or d.get("value_id")) in confirmed:
                continue
            guess = d.get("guess") is True or rule in B.GUESS_RULES
            if B.value_colour(B.STATE_GUESSED if guess else B.STATE_FILLED, rule) == B.COLOUR_YELLOW:
                out.append((d, "guess" if guess else "deduction"))
        elif d.get(B.ABSENCE_DERIVATION_KEY) is not True:
            out.append((d, "unknown"))
    return out


def _index_rows(records_dir: Path) -> dict[str, Mapping]:
    from . import records as R

    index = _read_json(Path(records_dir) / R.EXPORT_INDEX)
    rows = index.get("records") if isinstance(index, Mapping) else None
    return {str(r.get("record_id")): r for r in rows or () if isinstance(r, Mapping) and r.get("record_id")}


def _stale_records(bundle_dir: Path, rows: Mapping[str, Mapping], record_ids: Sequence[str]) -> list[str]:
    """Review I3: the records (of ``record_ids``) exported from ``bundle_dir`` whose group composes DIFFERENTLY now (a
    decision since, e.g. a guess corrected), or not at all: ``records.content_sha256`` of the draft now against the one
    the export index keeps. Reads only."""
    from . import records as R

    bundle = _load(bundle_dir)
    marker = bool((bundle.get("self_test") or {}).get("test_marker"))
    now = {gid: R.content_sha256(draft, comp) for gid, draft, comp in R.fresh_compositions(bundle_dir, bundle,
                                                                                         test_marker=marker)}
    bid = str(bundle.get("bundle_id"))
    out = []
    for rid in record_ids:
        row = rows.get(rid) or {}
        if str(row.get("bundle_id")) != bid:
            continue
        if now.get(str(row.get("group_id"))) != row.get("content_sha256"):
            out.append(rid)
    return out


def final_check(records_dir: Path, bundle_dir: Path | None = None) -> dict:
    """The final check over the records in ``records_dir`` (module comment above). READS ONLY. ``{items, values, guesses,
    deductions, unknown, records, records_checked, digest, bundle_ids, records_without_bundle, stale_records,
    statement}``: ``items`` one per field, value and rule, with its kind (``guess``, ``deduction``, or ``unknown``: a
    record with no readable evidence file, review I1, or a derivation no rule registers), how many values and records
    carry it, and the quote, file and line or the rule; ``values`` the yellow fields over every record, counted by
    ``bundle.count_colours`` (the aggregation ``bundle status`` uses, review C1); ``digest`` over exactly the items and
    the records; ``stale_records`` (``bundle_dir`` given, review I3) the records older than the bundle's answers."""
    records_dir = Path(records_dir)
    rows: dict[tuple, dict] = {}
    colour_maps: list[dict[str, str]] = []
    yellow: dict[str, set[str]] = {}  # record id -> its yellow fields
    kinds_of: dict[tuple[str, str], set[str]] = {}
    files = _record_files(records_dir)

    def add(fpath: str, value: Any, rule: Any, kind: str, stem: str, quote: Any = None, file: Any = None,
            locator: Any = None) -> None:
        key = (fpath, json.dumps(value, sort_keys=True, default=str), str(rule))
        row = rows.get(key)
        if row is None:
            row = rows[key] = {"path": fpath, "value": value, "rule_id": str(rule), "kind": kind,
                               "guess": kind == "guess", "values": 0, "records": set(), "quote": quote, "file": file,
                               "locator": locator}
        row["values"] += 1
        row["records"].add(stem)
        kinds_of.setdefault((stem, fpath), set()).add(kind)

    for path in files:
        stem = path.name[: -len(".json")]
        record = _read_json(path)
        sidecar = _read_json(path.with_name(stem + ".evidence.json"))
        ev = sidecar.get("evidence") if isinstance(sidecar, Mapping) else None
        if not isinstance(ev, Mapping) or not isinstance(record, Mapping):
            # review I1: what this record holds cannot be told, and the upload would still send it: never green
            add(UNKNOWN_PATH, None, UNKNOWN_NO_EVIDENCE, "unknown", stem,
                quote="its evidence file is missing or cannot be read, so nothing says which values are certain")
            colour_maps.append({UNKNOWN_PATH: B.COLOUR_YELLOW})
            yellow.setdefault(stem, set()).add(UNKNOWN_PATH)
            continue
        colours: dict[str, str] = {}
        for fpath, entries in sorted(ev.items()):
            if ":" in fpath or not isinstance(entries, list):
                continue
            colour = B.evidence_colour(entries)
            if colour is None:
                continue
            colours[fpath] = colour
            if colour != B.COLOUR_YELLOW:
                continue
            yellow.setdefault(stem, set()).add(fpath)
            value = _at(record, fpath)
            for d, kind in _yellow_derivations(entries):
                if kind == "guess":
                    add(fpath, value, d.get("rule"), kind, stem, d.get("quote"), d.get("source_file"), d.get("locator"))
                elif kind == "deduction":
                    w = _deduction_witness(entries) or {}
                    add(fpath, value, d.get("rule"), kind, stem, w.get("quote"), w.get("source_file"), w.get("locator"))
                else:
                    add(fpath, value, UNKNOWN_DERIVATION, kind, stem, quote=str(d.get("rule") or "")[:200])
        colour_maps.append(colours)
    items = [{**row, "records": len(row["records"]), "record_ids": sorted(row["records"])}
             for row in sorted(rows.values(), key=lambda r: (r["kind"] != "guess", field_words(r["path"]), r["path"],
                                                             json.dumps(r["value"], sort_keys=True, default=str)))]
    record_ids = sorted(yellow)
    counted = B.count_colours(colour_maps)
    n = counted[B.COLOUR_YELLOW]
    # each yellow field counted once: a guess if any guess keeps it yellow, else a deduction, else unknown
    first = ["guess" if "guess" in ks else "deduction" if "deduction" in ks else "unknown" for ks in kinds_of.values()]
    kinds = {k: first.count(k) for k in ("guess", "deduction", "unknown")}
    index_rows = _index_rows(records_dir)
    bundle_of = {rid: str(r.get("bundle_id")) for rid, r in index_rows.items() if r.get("bundle_id")}
    payload = {"items": [{k: i[k] for k in ("path", "value", "rule_id", "kind", "values", "record_ids")} for i in items],
               "records": record_ids}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
                            ).hexdigest()[:16]
    stale = _stale_records(Path(bundle_dir), index_rows, sorted(index_rows)) if bundle_dir is not None else []
    return {"items": items, "values": n, "guesses": kinds["guess"], "deductions": kinds["deduction"],
            "unknown": kinds["unknown"], "records": record_ids, "records_checked": len(files), "digest": digest,
            "bundle_ids": sorted({bundle_of[r] for r in record_ids if r in bundle_of}),
            "records_without_bundle": [r for r in record_ids if r not in bundle_of],
            "stale_records": stale,
            "statement": (values_sentence(n, kinds) + f", in {len(record_ids)} of the {len(files)} record(s). "
                          + PORTAL_COPY_NOTE) if n else
                         f"None of the {len(files)} record(s) carries a guess or a deduction you have not confirmed."}


def values_sentence(n: int, kinds: Mapping[str, int]) -> str:
    """Review M1: "N values are my guesses or worked out by a rule, not confirmed by you (G guesses, D worked out by a
    rule[, U I cannot tell])", the plural right for one."""
    split = [f"{kinds.get('guess', 0)} {'guess' if kinds.get('guess', 0) == 1 else 'guesses'}",
             f"{kinds.get('deduction', 0)} worked out by a rule"]
    if kinds.get("unknown"):
        split.append(f"{kinds['unknown']} I cannot tell, since what they rest on is not in the evidence file")
    one = n == 1
    return (f"{n} value{'' if one else 's'} {'is' if one else 'are'} my guess{'' if one else 'es'} or worked out by a "
            f"rule, not confirmed by you ({', '.join(split)})")


def final_check_question(check: Mapping) -> str:
    """The ONE plain question the skill asks (review M1: the split said, the plural right)."""
    n = check["values"]
    one = n == 1
    return (f"{'This value is' if one else f'These {n} values are'} my guess{'' if one else 'es'} from your files or "
            f"worked out by a rule ({check['guesses']} {'guess' if check['guesses'] == 1 else 'guesses'}, "
            f"{check['deductions']} worked out by a rule"
            + (f", {check['unknown']} I cannot tell" if check.get("unknown") else "")
            + f"). Send {'it' if one else 'them'} as {'it is' if one else 'they are'}, or check "
            f"{'it' if one else 'them'} first?")


def render_final_check(check: Mapping, *, records_dir: str, bundle: str | None = None) -> str:
    """The final check in plain words: the question, then each yellow value by field, then the command for a yes (the
    real bundle folder when it was given, review M5)."""
    if not check["values"]:
        return check["statement"]
    lines = [f"Before sending: {check['statement']}", ""]
    for i in check["items"]:
        kind = {"guess": "my guess", "deduction": "worked out by a rule"}.get(i["kind"], "cannot tell")
        where = ", ".join(str(x) for x in (i.get("file"), i.get("locator")) if x)
        said = (f"\"{i['quote']}\"" + (f" ({where})" if where else "")) if i.get("quote") else RULE_WORDS.get(
            i["rule_id"], i["rule_id"])
        field = field_words(i["path"]) if i["path"] != UNKNOWN_PATH else UNKNOWN_PATH
        lines.append(f"  {field}: {value_words(i['path'], i['value']) if i['path'] != UNKNOWN_PATH else '?'} — {kind}, "
                     f"in {i['records']} record(s). From: {said}")
    q = shlex.quote(records_dir)
    b = shlex.quote(bundle) if bundle else "<bundle_dir>"
    lines += ["", final_check_question(check),
              (f"To send them as they are: `isaac bundle upload {q} --dry-run --bundle {b} --guesses-ok "
               f"{check['digest']} --by \"<your name>\"`. To check them first: `isaac bundle review {b}`; an answer "
               f"changes this list only after `isaac bundle build-records {b}` and `isaac bundle export {b} --out {q}` "
               "again."), UPLOAD_NOTE]
    return "\n".join(lines)


def accept_guesses(records_dir: Path, bundle_dir: Path, *, digest: str, by: str, orcid: str | None = None,
                   note: str | None = None) -> dict:
    """The scientist's yes to sending the records with the yellow values the final check lists. Refused unless the name
    is given, ``digest`` is the check's digest NOW (the values changed since they were shown otherwise), every record
    with a yellow value names ``bundle_dir``'s bundle in the export index (review I2: an index that names no bundle, or
    another, refuses), and no record of this bundle is older than its answers (review I3). Records ONE
    ``submit_with_guesses`` decision (who, when, the digest, every listed item and record), only once per digest
    (review M2). It confirms nothing: each value stays yellow."""
    from . import mutations as M

    problem = B.decider_name_problem(by)
    if problem:
        raise ReviewRefused(f"--by is required with --guesses-ok: the name of the person who said to send the guesses "
                            f"(this one {problem}). Nothing was recorded.")
    if orcid is not None and not M.ORCID_RE.fullmatch(orcid):
        raise ReviewRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).")
    bundle_dir = Path(bundle_dir)
    check = final_check(records_dir, bundle_dir)
    if not check["values"]:
        return {"recorded": False, "check": check, "statement": check["statement"]}
    q = shlex.quote(str(bundle_dir))
    if check["stale_records"]:
        raise ReviewRefused(f"The records are older than your answers ({len(check['stale_records'])} record(s) compose "
                            f"differently now): run `isaac bundle build-records {q}` and `isaac bundle export {q} --out "
                            "<records>` again, then the final check. Nothing was recorded.", code=1)
    if digest != check["digest"]:
        raise ReviewRefused("The guesses changed since you were shown them (the --guesses-ok digest is not the one the "
                            "final check gives now); run the upload again without --guesses-ok and show the scientist "
                            "what it lists now. Nothing was recorded.", code=1)
    if len(check["items"]) > MAX_SUBMIT_ITEMS:
        raise ReviewRefused(f"{len(check['items'])} listed values are more than one yes records ({MAX_SUBMIT_ITEMS}); "
                            "send the records a few at a time. Nothing was recorded.", code=5)
    with M.locked(bundle_dir):
        bundle = _load(bundle_dir)
        bid = str(bundle.get("bundle_id"))
        if check["records_without_bundle"] or check["bundle_ids"] != [bid]:
            raise ReviewRefused(
                "The records folder does not say these records come from this bundle "
                + (f"({len(check['records_without_bundle'])} record(s) with guesses are in no export index entry, e.g. "
                   "an index that was removed)" if check["records_without_bundle"] else
                   f"(they name {', '.join(check['bundle_ids'])}, this bundle is {bid})")
                + ": export them from the bundle with `isaac bundle export`, give that bundle with --bundle, or send each "
                "bundle's records on their own. Nothing was recorded.", code=2)
        earlier = next((d for d in B.submit_decisions(bundle) if d.get(B.SUBMIT_DIGEST_KEY) == check["digest"]), None)
        if earlier is not None:
            # review M2: the same yes to the same list is recorded once
            return {"recorded": False, "already_recorded": True, "decision_id": earlier.get("decision_id"),
                    "check": check, "statement": (f"Already recorded ({earlier.get('decision_id')}): "
                                                  f"{(earlier.get('decided_by') or {}).get('name')} said to send exactly "
                                                  "these values as they are. " + UPLOAD_NOTE)}
        decisions = bundle.setdefault("scientist_decisions", [])
        if len(decisions) + 1 > B.MAX_SCIENTIST_DECISIONS:
            raise ReviewRefused(M.log_full_message("scientist_decisions", len(decisions), 1, B.MAX_SCIENTIST_DECISIONS),
                                code=5)
        entry = {
            "decision_id": f"d-{len(decisions) + 1:05d}",
            "target": {"kind": "experiment", "id": "experiment"},
            "decision": B.SUBMIT_WITH_GUESSES_DECISION,
            "value": None,
            "chosen_reading_index": None,
            "decided_by": M._decider(by, orcid),
            "decided_utc": M.now_utc(),
            "method": "scientist_answer",
            "note": note,
            "batch_id": None,
            B.SUBMIT_DIGEST_KEY: check["digest"],
            B.SUBMIT_ITEMS_KEY: [{k: i[k] for k in ("path", "value", "rule_id", "kind", "guess", "values", "records",
                                                    "quote", "file", "locator")} for i in check["items"]],
            B.SUBMIT_RECORDS_KEY: check["records"],
        }
        decisions.append(entry)
        try:
            M.save_bundle(bundle_dir, bundle)
        except M.MutationRefused as exc:
            raise ReviewRefused(str(exc), code=exc.code) from None
    return {"recorded": True, "decision_id": entry["decision_id"], "check": check,
            "statement": (f"Recorded ({entry['decision_id']}): {by} said to send the records as they are, though "
                          + values_sentence(check["values"], {"guess": check["guesses"], "deduction": check["deductions"],
                                                              "unknown": check["unknown"]})
                          + ". They stay marked as guesses in this bundle and in the evidence files. " + UPLOAD_NOTE)}
