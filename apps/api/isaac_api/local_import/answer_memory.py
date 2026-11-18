"""Earlier answers: what a scientist confirmed on EARLIER beamtimes, offered as hints on a new one. Stdlib only.

WHY
===

Inside one beamtime an answer persists and one answer can cover many groups. Across beamtimes nothing carried over:
"pellet" for sample JK3 on beamtime A was asked again from scratch on beamtime B. This module keeps a small,
OPT-IN memory of confirmed scientist decisions in ONE file on the scientist's own computer, and shows a matching
earlier answer beside a new question as a HINT. It never sets a value: the person answering now confirms it with a
normal decision (``decide ... --from-earlier-answer <entry_id>``), which records them as the decider and notes where
the value came from.

WHERE
=====

``~/.isaac/answer-memory.json`` (:data:`MEMORY_ENV` overrides it; tests always set it). Outside every bundle and
outside the repository: a path inside either is refused. Nothing is written until the scientist turns it on
(``isaac answer-memory on --by <name>``); ``off`` stops both writing and suggesting (entries are kept until
``forget``). Under pytest without :data:`MEMORY_ENV` the memory is off and nothing is read or written.

WHAT IS STORED (:func:`entries_from_bundle`)
============================================

Only a person's decision: the LATEST decision on a value target (a candidate, a missing value, a conflict's
candidate) that confirms or corrects a value, recorded as ``scientist_answer`` under a valid ``--by`` name (the CLI,
the Local Imports page, a template or workbook import all record so), and the beamtime's ``set_clock_time_zone``.
Never ``defer`` ("I don't know"), never ``reject``, never an AI interpretation, never a value a parser read that no
person confirmed.

WHEN: at the moment of the decision, never retroactively (:func:`snapshot` before a write, :func:`after_write`
after it). A write stores only the decisions IT added, while the memory is on: never a decision recorded before the
scientist turned it on, while it was off, or by a dry run or a preview (which add none). A later decision on a
remembered target (a defer, a reject, another value) withdraws it from its entry. A forgotten entry or beamtime is
therefore never re-learned from the bundle's existing decisions: only a NEW decision on it is stored. The one
exception is ``isaac answer-memory learn <bundle> --by <name>``, the scientist's explicit yes to remember a bundle's
recorded answers (it replaces that bundle's entries).

Only the fields in :data:`FIELD_SCOPES` are stored, each with the scope that makes it reusable:

* ``sample`` facts (``sample.*`` except ``sample.sample_id``, a per-beamtime label): the grouping's own sample
  identity of the run's live record group (``basis.sample.sample_name``, plus ``loading_or_thickness`` when read;
  never a name-stem guess, never a conflicting reading, never the per-beamtime electrode number). The beamtime's
  confirmed research group / organization are kept beside it so a different group's "S1" is never offered.
* ``beamline`` facts (endstation, site, facility organization, the instrument clock's time zone): the facility name
  and beamline a person CONFIRMED in that bundle (one value each).
* ``facility identity`` (facility name, beamline): the SPEC headers' acquisition fingerprint, only when exactly one
  beamline matches and the folder's name does not disagree with it.
* ``people`` facts: the research group is keyed by the confirmed organization, the organization by the confirmed
  research group.

Each entry records the field, the value, who answered, when, the beamtime FOLDER NAME (never a path), the bundle id
and the bundle's targets the answer was given on (so a later decision on one withdraws it). The scope keys are the
bundle's own (its confirmed facility, beamline, research group, organization): they are refreshed from the bundle at
each later write to it, so an answer given before the beamline or the group was confirmed becomes reusable once they
are (until then its ``scope`` is ``null`` or lacks them, and it is offered nowhere).

MATCHING (:func:`earlier_answers_for`)
=====================================

A hint is shown only when every scope key of the field's class matches the new bundle's: the same sample identity
AND a confirmed research group or organization present on BOTH sides and equal (one missing on either side is no
match; one present on both that differs is no match), the same confirmed facility and beamline, the same
fingerprint, the same organization or group. A key the new bundle does not hold yet is a mismatch (no hint). A
beamline is compared conservatively (:func:`beamline_key`): case-insensitive, its separator significant (``BL11-2``
is never ``BL1-12``), and one written without a separator (``BL152``: 15-2 or 1-52?) or naming two beamlines is
ambiguous and matches nothing; no spelling is mapped to another. Answers from the same bundle are not "earlier".
When earlier answers differ, every value is shown and the hint says they disagree.

SHOWN TO CLAUDE: every target an earlier answer is shown for is recorded in the bundle's ``exposures`` log under
:data:`EXPOSURE_COMMAND` (:func:`exposures`), as `bundle questions` records the parser values it prints.

NOT HERE: processing-method answers (dead-time rules, the energy column a protocol reads) belong to the versioned
processing protocol in the repository (``processing/protocol.py``), never to this per-computer memory.
"""

from __future__ import annotations

import contextlib
import copy
import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B

FORMAT_ID = "isaac.answer_memory"
FORMAT_VERSION = "1.0.0"
MEMORY_ENV = "ISAAC_ANSWER_MEMORY"
HINT_KIND = "earlier_answer"
MAX_ENTRIES = 5000
#: distinct earlier values shown per field (each with its newest answer)
MAX_VALUES_SHOWN = 6
CLOCK_ZONE_FIELD = "clock_time_zone"
#: the ``exposures`` command an earlier answer shown beside a question is recorded under (a value shown to Claude)
EXPOSURE_COMMAND = "bundle questions (earlier answer)"

SCOPE_SAMPLE = "sample"
SCOPE_BEAMLINE = "beamline"
SCOPE_FINGERPRINT = "spec_fingerprint"
SCOPE_ORGANIZATION = "organization"
SCOPE_RESEARCH_GROUP = "research_group"

GROUP_PATH = "attribution.produced_by.group"
ORGANIZATION_PATH = "attribution.produced_by.organization"
FACILITY_PATH = "system.facility.facility_name"
BEAMLINE_PATH = "system.facility.beamline"

#: field -> the scope key that makes an earlier answer to it reusable (the only fields stored)
FIELD_SCOPES: Mapping[str, str] = {
    FACILITY_PATH: SCOPE_FINGERPRINT,
    BEAMLINE_PATH: SCOPE_FINGERPRINT,
    "system.facility.endstation": SCOPE_BEAMLINE,
    "system.facility.site": SCOPE_BEAMLINE,
    "system.facility.organization": SCOPE_BEAMLINE,
    CLOCK_ZONE_FIELD: SCOPE_BEAMLINE,
    GROUP_PATH: SCOPE_ORGANIZATION,
    ORGANIZATION_PATH: SCOPE_RESEARCH_GROUP,
}
#: ``sample.*`` fields that are NOT sample facts: a per-beamtime label (condition_label), never carried over
NOT_SAMPLE_FACTS = frozenset({"sample.sample_id"})

NOTE = ("An answer a scientist confirmed on an EARLIER beamtime, remembered on this computer only. A HINT, never an "
        "answer: nothing is recorded until the person answering now says it applies here.")
DISAGREE_NOTE = "Earlier answers disagree: ask which applies here; never pick one."
#: what a value confirmed from an earlier answer adds to the decision's note
PROVENANCE_PREFIX = "Confirmed from an earlier answer"


class MemoryRefused(ValueError):
    """A memory command that cannot be done; nothing was written."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


class MemoryUnreadable(MemoryRefused):
    """The memory file cannot be parsed at all (``forget --all`` removes it)."""


# --- where the file lives ------------------------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def memory_path() -> Path | None:
    """The memory file, or ``None`` (off, nothing read or written) under pytest without :data:`MEMORY_ENV`."""
    raw = os.environ.get(MEMORY_ENV)
    if raw is not None and raw.strip():
        return Path(raw).expanduser()
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None  # a test never reads or writes the real ~/.isaac
    return Path.home() / ".isaac" / "answer-memory.json"


def location_problem(path: Path) -> str | None:
    """Why ``path`` cannot hold the memory (inside the repository or a bundle folder), or ``None``."""
    p = path.expanduser().resolve()
    try:
        p.relative_to(_repo_root())
        return "it is inside the ISAAC repository (the memory is personal: it stays outside the repository)"
    except ValueError:
        pass
    for parent in p.parents:
        if (parent / "bundle.json").is_file():
            return f"it is inside the bundle folder {parent.name!r} (the memory stays outside every bundle)"
    return None


def _empty() -> dict:
    return {"format": FORMAT_ID, "format_version": FORMAT_VERSION, "enabled": False, "entries": [],
            "statement": ("Answers a scientist confirmed on earlier beamtimes, kept on this computer only and shown as "
                          "hints on later beamtimes. Never uploaded, never a value: each is confirmed again.")}


def load(path: Path | None = None) -> dict:
    """The memory (an empty, disabled one when there is no file). A file that is not a memory is refused."""
    path = path if path is not None else memory_path()
    if path is None or not path.is_file():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MemoryUnreadable(f"The answer memory at {path} cannot be read ({exc.__class__.__name__}); nothing was "
                               "changed. `isaac answer-memory forget --all` removes the unreadable file (every "
                               "remembered answer is lost and the memory is off until `isaac answer-memory on`).") \
            from None
    if not isinstance(data, dict) or data.get("format") != FORMAT_ID or not isinstance(data.get("entries"), list):
        raise MemoryRefused(f"{path} is not an ISAAC answer memory; nothing was changed. It is left alone: set "
                            f"{MEMORY_ENV} to another file (or move this one away) to keep an answer memory.")
    return data


def is_enabled(path: Path | None = None) -> bool:
    path = path if path is not None else memory_path()
    if path is None:
        return False
    try:
        return bool(load(path).get("enabled"))
    except MemoryRefused:
        return False


@contextlib.contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.name == ".isaac":
        with contextlib.suppress(OSError):
            os.chmod(path.parent, 0o700)  # the default folder is the scientist's own
    lock = path.with_name(path.name + ".lock")
    with open(lock, "a+") as fh:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - no fcntl (Windows): one writer is assumed
            pass
        yield


def _save(path: Path, data: Mapping) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".answer-memory.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _require_path() -> Path:
    path = memory_path()
    if path is None:
        raise MemoryRefused(f"No answer-memory file is configured ({MEMORY_ENV} is not set under a test run). "
                            "Nothing was written.")
    if (why := location_problem(path)) is not None:
        raise MemoryRefused(f"The answer memory cannot be kept at {path}: {why}. Set {MEMORY_ENV} to a file in your "
                            "home folder. Nothing was written.")
    return path


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --- turning it on and off, listing, forgetting --------------------------------------------------------------------

def set_enabled(enabled: bool, *, by: str | None = None) -> dict:
    """``on`` (with the scientist's name: their agreement) or ``off``. ``off`` with no file writes nothing."""
    path = _require_path()
    if enabled:
        if not by or B.decider_name_problem(by) is not None:
            raise MemoryRefused("Turning the answer memory on needs --by \"<your name>\": it is your agreement. "
                                "Nothing was written.")
    elif not path.is_file():
        return status(path) | {"statement": "The answer memory is off. Nothing was written (there is no memory file)."}
    with _locked(path):
        data = load(path)
        data["enabled"] = enabled
        data[("enabled_utc" if enabled else "disabled_utc")] = _now()
        if enabled:
            data["enabled_by"] = by.strip()
        _save(path, data)
    said = ("On: from now on, answers you confirm with --by, and workbook or template imports you apply, are "
            "remembered on this computer only and shown as hints on later beamtimes (answers recorded before now are "
            "not, unless you say `isaac answer-memory learn <bundle> --by`). Nothing is ever applied without you."
            if enabled else
            "Off: nothing is remembered and no earlier answer is shown. Entries already kept stay until you forget them "
            "(`isaac answer-memory forget --all`).")
    return status(path) | {"statement": said}


def status(path: Path | None = None) -> dict:
    path = path if path is not None else memory_path()
    data = load(path) if path is not None else _empty()
    entries = data.get("entries") or []
    return {"enabled": bool(data.get("enabled")), "path": str(path) if path is not None else None,
            "file_exists": bool(path is not None and path.is_file()), "entries": len(entries),
            "beamtimes": len({e.get("beamtime") for e in entries}),
            **({"enabled_by": data["enabled_by"]} if data.get("enabled") and data.get("enabled_by") else {})}


def list_entries(*, field: str | None = None, beamtime: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    data = load()
    rows = [e for e in data.get("entries") or ()
            if (field is None or e.get("field") == field) and (beamtime is None or e.get("beamtime") == beamtime)]
    rows.sort(key=lambda e: (str(e.get("decided_utc") or ""), str(e.get("entry_id"))), reverse=True)
    page = rows[offset: offset + limit]
    return {"enabled": bool(data.get("enabled")), "total": len(rows), "offset": offset, "returned": len(page),
            "entries": [{**e, "said": said(e)} for e in page]}


def forget(*, entry_ids: Sequence[str] = (), beamtime: str | None = None, all_entries: bool = False) -> dict:
    """Remove entries by id, every entry from one beamtime folder, or all of them (the on/off setting is kept)."""
    if not entry_ids and beamtime is None and not all_entries:
        raise MemoryRefused("Name what to forget: --entry <id>, --beamtime <folder name> or --all. Nothing was changed.")
    path = _require_path()
    if not path.is_file():
        return {"forgotten": 0, "entries": 0, "statement": "Nothing to forget: there is no memory file."}
    with _locked(path):
        try:
            data = load(path)
        except MemoryUnreadable:
            if not all_entries:
                raise
            return _remove_unreadable(path)
        before = data["entries"]
        if all_entries:
            kept = []
        else:
            unknown = [i for i in entry_ids if not any(e.get("entry_id") == i for e in before)]
            if unknown:
                raise MemoryRefused(f"No remembered entry {', '.join(unknown)}. Nothing was changed.")
            kept = [e for e in before if e.get("entry_id") not in set(entry_ids)
                    and (beamtime is None or e.get("beamtime") != beamtime)]
        data["entries"] = kept
        _save(path, data)
    n = len(before) - len(kept)
    return {"forgotten": n, "entries": len(kept), "statement": f"Forgot {n} remembered answer(s); {len(kept)} kept."}


def _remove_unreadable(path: Path) -> dict:
    """``forget --all`` on a memory file that cannot be parsed: removed WITHOUT parsing it, once it is confirmed to
    be the memory file at the configured path (a regular file, not a link, where :func:`memory_path` points)."""
    configured = memory_path()
    if (configured is None or path.is_symlink() or not path.is_file()
            or path.resolve() != configured.expanduser().resolve()):
        raise MemoryRefused(f"{path} is not the configured answer-memory file; nothing was changed.")
    path.unlink()
    return {"forgotten": None, "entries": 0, "removed_unreadable_file": True, "enabled": False,
            "statement": (f"The answer memory at {path} could not be read, so it was removed without reading it: "
                          "nothing is remembered and the memory is off. `isaac answer-memory on --by \"<your name>\"` "
                          "starts a new one.")}


# --- what a bundle holds -------------------------------------------------------------------------------------------

def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def beamline_key(value: Any) -> str | None:
    """How a confirmed beamline is compared across beamtimes, or ``None`` (ambiguous: it matches nothing).

    Conservative: case-insensitive, a leading ``BL`` / ``beamline`` and a facility word around it ignored, every
    dash style read as ``-``, and the SEPARATOR significant (``BL15-2``, ``15-2`` and ``SSRL BL15–2`` are ``15-2``;
    ``BL11-2`` is ``11-2``, never ``BL1-12``). A beamline of two or more digits written with no separator
    (``BL152``: 15-2 or 1-52?) or a value naming two beamlines is ambiguous: no mapping is guessed. A value with no
    beamline-shaped token is compared as written (case and spacing aside)."""
    from .template import _BEAMLINE_SHAPE, _DASHES

    if not _scalar(value):
        return None
    text = _DASHES.sub("-", str(value)).casefold()
    tokens = list(_BEAMLINE_SHAPE.finditer(text))
    if not tokens:
        return _norm(text) or None
    keys = set()
    for m in tokens:
        first, second, letter = m.group(1), m.group(2), m.group(3) or ""
        if second is None and len(first) > 1:
            return None  # no separator: where it splits is unknown
        keys.add(f"{first}-{second}{letter}" if second is not None else f"{first}{letter}")
    return keys.pop() if len(keys) == 1 else None


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and not (isinstance(value, str) and not value.strip())


def _person(d: Mapping | None) -> str | None:
    """The decider's name when ``d`` is a person's recorded answer, else ``None``."""
    if not isinstance(d, Mapping) or d.get("method") != "scientist_answer":
        return None
    name = (d.get("decided_by") or {}).get("name")
    return name.strip() if B.decider_name_problem(name) is None else None


def person_values(bundle: Mapping) -> list[dict]:
    """Every value a PERSON stands behind now: ``{"field", "value", "run_id", "decision", "target"}``, one per value
    target (``target``: ``"<kind>:<id>"``) whose latest (governing) decision confirms or corrects a value. Never a
    defer, a reject, an AI interpretation or an unconfirmed parser value."""
    decisions = bundle.get("scientist_decisions") or ()
    decision_of = B._decisions_by_target(decisions)
    out: list[dict] = []

    def add(path: Any, value: Any, run_id: Any, d: Mapping, target: str) -> None:
        if isinstance(path, str) and _scalar(value) and _person(d):
            out.append({"field": path, "value": value, "run_id": run_id, "decision": d, "target": target})

    for c in bundle.get("candidates") or ():
        d = B.candidate_decision(bundle, c, decision_of)
        if d is not None and d.get("decision") in ("confirm", "correct"):
            add(c.get("target_field_path"), B.final_value(c.get("value"), d), c.get("run_id"), d,
                f"candidate:{c.get('candidate_id')}")
    for m in bundle.get("missing_values") or ():
        d = decision_of.get(("missing_value", str(m.get("value_id"))))
        if d is not None and d.get("decision") in ("confirm", "correct"):
            add(m.get("target_field_path"), B.final_value(None, d), m.get("run_id"), d,
                f"missing_value:{m.get('value_id')}")
    zone = B.clock_zone_decision(bundle)
    if zone is not None:
        add(CLOCK_ZONE_FIELD, zone.get("value"), None, zone, "experiment:" + CLOCK_ZONE_FIELD)
    return out


def _unique(values: Iterable[Any]) -> str | None:
    seen = {_norm(v): v for v in values}
    return str(next(iter(seen.values()))).strip() if len(seen) == 1 else None


def _sample_identity(group: Mapping) -> dict | None:
    """The grouping's own sample identity of one group: its stated sample name (and loading), never a name-stem guess,
    a conflicting reading or the per-beamtime electrode number."""
    sample = ((group.get("basis") or {}).get("sample")) or {}
    name = sample.get("sample_name") or {}
    if (name.get("kind") == "conflicting" or name.get("sample_key_basis") or not _scalar(name.get("value"))):
        return None
    ident = {"sample_name": _norm(name["value"])}
    loading = sample.get("loading_or_thickness") or {}
    if loading:
        if loading.get("kind") == "conflicting" or not _scalar(loading.get("value")):
            return None
        ident["loading_or_thickness"] = _norm(loading["value"])
    return ident


def _fingerprint(bundle: Mapping) -> dict | None:
    fp = ((bundle.get("experiment") or {}).get("acquisition_system") or {}).get("fingerprint") or {}
    matches = fp.get("matches") or ()
    if len(matches) != 1 or fp.get("disagrees_with_folder_name"):
        return None
    m = matches[0]
    if not m.get("fingerprint_id") or not m.get("facility") or not m.get("beamline"):
        return None
    return {"fingerprint_id": str(m["fingerprint_id"]), "facility": str(m["facility"]), "beamline": str(m["beamline"])}


class Context:
    """What one bundle holds that scopes an answer: run -> live group -> sample identity, the confirmed facility and
    beamline, research group and organization, and the SPEC fingerprint."""

    def __init__(self, bundle: Mapping, values: Sequence[Mapping] | None = None):
        from . import questions as Q

        values = person_values(bundle) if values is None else values
        self.bundle_id = bundle.get("bundle_id")
        self.beamtime = str((bundle.get("source_root") or {}).get("label") or "")
        self.group_of_run: dict[str, Mapping] = {}
        for g in Q.live_groups(bundle):
            for rid in g.get("member_run_ids") or ():
                self.group_of_run[rid] = g
        self.cands = {c["candidate_id"]: c for c in bundle.get("candidates") or ()}
        self.missing = {m["value_id"]: m for m in bundle.get("missing_values") or ()}
        self.conflicts = {c["conflict_id"]: c for c in bundle.get("conflicts") or ()}

        def confirmed(path: str) -> str | None:
            return _unique(v["value"] for v in values if v["field"] == path)

        facility, beamline = confirmed(FACILITY_PATH), confirmed(BEAMLINE_PATH)
        self.beamline = {"facility": facility, "beamline": beamline} if facility and beamline else None
        self.research_group = confirmed(GROUP_PATH)
        self.organization = confirmed(ORGANIZATION_PATH)
        self.fingerprint = _fingerprint(bundle)

    def sample_of_run(self, run_id: Any) -> dict | None:
        g = self.group_of_run.get(run_id) if run_id else None
        return _sample_identity(g) if g is not None else None

    def runs_of_target(self, kind: str | None, tid: str) -> list[str]:
        if kind == "candidate":
            return [r for r in [(self.cands.get(tid) or {}).get("run_id")] if r]
        if kind == "missing_value":
            return [r for r in [(self.missing.get(tid) or {}).get("run_id")] if r]
        if kind == "conflict":
            return list((self.conflicts.get(tid) or {}).get("run_ids") or ())
        return []

    def scope_for(self, scope_class: str, sample: Mapping | None) -> dict | None:
        """The scope keys an answer of ``scope_class`` carries in this bundle, or ``None`` (not reusable here)."""
        if scope_class == SCOPE_SAMPLE:
            if not sample:
                return None
            return {"sample": dict(sample),
                    **({"research_group": self.research_group} if self.research_group else {}),
                    **({"organization": self.organization} if self.organization else {})}
        if scope_class == SCOPE_BEAMLINE:
            return {"beamline": dict(self.beamline)} if self.beamline else None
        if scope_class == SCOPE_FINGERPRINT:
            return {"spec_fingerprint": dict(self.fingerprint)} if self.fingerprint else None
        if scope_class == SCOPE_ORGANIZATION:
            return {"organization": self.organization} if self.organization else None
        if scope_class == SCOPE_RESEARCH_GROUP:
            return {"research_group": self.research_group} if self.research_group else None
        return None


def scope_class_of(field: str | None) -> str | None:
    """The scope class of a field (or the clock-zone question), or ``None`` (never remembered)."""
    if not isinstance(field, str):
        return None
    if field in FIELD_SCOPES:
        return FIELD_SCOPES[field]
    if field.startswith("sample.") and field not in NOT_SAMPLE_FACTS:
        return SCOPE_SAMPLE
    return None


def _entry_id(entry: Mapping) -> str:
    """Stable across a scope refresh: the field, value, the sample identity (a sample fact) or the scope class, the
    bundle and who answered. One bundle holds one facility, beamline, group and organization at a time, so these
    name one entry."""
    core = (entry.get("scope") or {}).get("sample") if entry["scope_class"] == SCOPE_SAMPLE else entry["scope_class"]
    key = json.dumps([entry["field"], entry["value"], core, entry["bundle_id"], entry["by"]], sort_keys=True)
    return "am-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _entries(values: Sequence[Mapping], ctx: Context) -> dict[str, dict]:
    """``{entry_id: entry}`` for these person values (one entry per field, value, scope and person; its targets)."""
    out: dict[str, dict] = {}
    for v in values:
        cls = scope_class_of(v["field"])
        if cls is None:
            continue
        sample = ctx.sample_of_run(v["run_id"]) if cls == SCOPE_SAMPLE else None
        if cls == SCOPE_SAMPLE and not sample:
            continue  # no stated sample identity: never reusable
        d = v["decision"]
        entry = {"field": v["field"], "scope_class": cls, "value": v["value"], "by": _person(d),
                 "decided_utc": d.get("decided_utc"), "beamtime": ctx.beamtime, "bundle_id": ctx.bundle_id,
                 "decision": d.get("decision"), "scope": ctx.scope_for(cls, sample), "targets": [v["target"]]}
        entry["entry_id"] = _entry_id(entry)
        prior = out.get(entry["entry_id"])
        if prior is not None:
            entry["targets"] = sorted(set(prior["targets"]) | set(entry["targets"]))
            if str(entry["decided_utc"] or "") < str(prior["decided_utc"] or ""):
                entry = {**prior, "targets": entry["targets"]}
        out[entry["entry_id"]] = entry
    return out


def entries_from_bundle(bundle: Mapping) -> list[dict]:
    """The memory entries ALL of one bundle's person decisions stand for (one per field, value and scope). Only the
    explicit ``answer-memory learn`` stores these; a write stores only its own new decisions (:func:`after_write`)."""
    values = person_values(bundle)
    return sorted(_entries(values, Context(bundle, values)).values(), key=lambda e: e["entry_id"])


def _refreshed(entry: Mapping, ctx: Context) -> dict:
    """``entry`` (of this bundle) with its scope keys read from the bundle as it is now: its sample identity is
    kept, the bundle's confirmed facility, beamline, group and organization are re-read."""
    cls = entry.get("scope_class")
    sample = (entry.get("scope") or {}).get("sample") if cls == SCOPE_SAMPLE else None
    if cls == SCOPE_SAMPLE and not sample:
        return dict(entry)
    return {**entry, "scope": ctx.scope_for(cls, sample)}


def _decision_ids(bundle: Mapping) -> frozenset[str]:
    return frozenset(str(d.get("decision_id")) for d in bundle.get("scientist_decisions") or ()
                     if isinstance(d, Mapping) and d.get("decision_id"))


def _writable_path() -> Path | None:
    path = memory_path()
    if path is None or location_problem(path) is not None or not is_enabled(path):
        return None
    return path


def snapshot(bundle_dir: Path) -> frozenset[str] | None:
    """Taken BEFORE a write: the bundle's decision ids, so :func:`after_write` stores only the decisions that write
    adds. ``None`` (nothing read beyond the setting) when the memory is off."""
    if _writable_path() is None:
        return None
    try:
        raw = json.loads(B.bundle_path(Path(bundle_dir)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _decision_ids(raw if isinstance(raw, Mapping) else {})


def _statement(n: int) -> str:
    return (f"Remembered on this computer: {n} answer(s) from this beamtime, for later beamtimes (hints only)."
            if n else "Nothing from this beamtime is remembered for later beamtimes (no answer with a reusable scope).")


def learn_new_decisions(bundle_dir: Path, before: frozenset[str] | None) -> dict | None:
    """After a write: remember the person answers among the decisions it ADDED (ids not in ``before``), withdraw a
    remembered target a new decision now governs, and refresh this bundle's entries' scope keys. Nothing else of the
    bundle is learned: never a decision recorded before (before opt-in, while off, or forgotten since). ``None``
    (nothing written) when the memory is off or the write added no decision (a dry run, a preview, a replay)."""
    if before is None:
        return None
    path = _writable_path()
    if path is None:
        return None
    from . import mutations as M

    bundle = M.load(Path(bundle_dir))
    new_ids = _decision_ids(bundle) - before
    if not new_ids:
        return None
    values = person_values(bundle)
    ctx = Context(bundle, values)
    governed = {v["target"]: v for v in values}

    def still(target: str) -> bool:  # governed by the same, older person decision as when it was remembered
        v = governed.get(target)
        return v is not None and str(v["decision"].get("decision_id")) not in new_ids

    fresh = _entries([v for v in values if str(v["decision"].get("decision_id")) in new_ids], ctx)
    bid = bundle.get("bundle_id")
    with _locked(path):
        data = load(path)
        if not data.get("enabled"):
            return None
        kept, mine, withdrawn = [], {}, 0
        for e in data["entries"]:
            if e.get("bundle_id") != bid:
                kept.append(e)
                continue
            targets = [t for t in e.get("targets") or () if still(t)]
            if not targets:
                withdrawn += 1
                continue
            mine[e["entry_id"]] = _refreshed({**e, "targets": targets}, ctx)
        added = 0
        for eid, e in fresh.items():
            prior = mine.get(eid)
            if prior is None:
                added += 1
                mine[eid] = e
            else:
                mine[eid] = {**prior, "targets": sorted(set(prior["targets"]) | set(e["targets"])),
                             "decided_utc": max(str(prior.get("decided_utc") or ""), str(e.get("decided_utc") or ""))
                             or None, "decision": e.get("decision")}
        merged = kept + list(mine.values())
        merged.sort(key=lambda e: str(e.get("decided_utc") or ""))
        data["entries"] = merged[-MAX_ENTRIES:]
        _save(path, data)
    return {"remembered": len(fresh), "added": added, "withdrawn": withdrawn,
            "beamtime": ctx.beamtime, "statement": _statement(len(fresh))}


def learn_from_bundle(bundle_dir: Path) -> dict | None:
    """``isaac answer-memory learn``, the scientist's explicit yes: remember EVERY person answer ``bundle_dir``
    records now, REPLACING that bundle's earlier entries. ``None`` when the memory is off (nothing written)."""
    path = _writable_path()
    if path is None:
        return None
    from . import mutations as M

    bundle = M.load(Path(bundle_dir))
    new = entries_from_bundle(bundle)
    with _locked(path):
        data = load(path)
        if not data.get("enabled"):
            return None
        kept = [e for e in data["entries"] if e.get("bundle_id") != bundle.get("bundle_id")]
        before = {e.get("entry_id") for e in data["entries"] if e.get("bundle_id") == bundle.get("bundle_id")}
        merged = (kept + new)
        merged.sort(key=lambda e: str(e.get("decided_utc") or ""))
        data["entries"] = merged[-MAX_ENTRIES:]
        _save(path, data)
    now = {e["entry_id"] for e in new}
    return {"remembered": len(new), "added": len(now - before), "removed": len(before - now),
            "beamtime": str((bundle.get("source_root") or {}).get("label") or ""), "statement": _statement(len(new))}


def after_write(bundle_dir: Path, before: frozenset[str] | None) -> dict | None:
    """What a write path adds to its output: :func:`learn_new_decisions` for the decisions the write added since
    :func:`snapshot` (``before``), never raising (the decision is recorded either way; a memory that could not be
    updated is said)."""
    try:
        return learn_new_decisions(bundle_dir, before)
    except Exception as exc:  # noqa: BLE001 - the bundle write already happened; say why the memory was not updated
        return {"remembered": None, "statement": f"The answer memory was not updated ({exc.__class__.__name__}): "
                                                 f"{str(exc)[:200]}"}


# --- matching ------------------------------------------------------------------------------------------------------

def _date(utc: Any) -> str:
    try:
        t = _dt.datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
    except ValueError:
        return str(utc or "an unknown date")
    return f"{t.day} {t:%b %Y}"


def _scope_said(entry: Mapping) -> str:
    sc = entry.get("scope") or {}
    if "sample" in sc:
        s = sc["sample"]
        who = "".join(f", {label} {sc[k]}" for k, label in (("research_group", "research group"),
                                                            ("organization", "organization")) if sc.get(k))
        return (f"same sample {s.get('sample_name')}"
                + (f", {s['loading_or_thickness']}" if s.get("loading_or_thickness") else "") + who)
    if "beamline" in sc:
        return f"same beamline {sc['beamline'].get('facility')} {sc['beamline'].get('beamline')}"
    if "spec_fingerprint" in sc:
        f = sc["spec_fingerprint"]
        return f"same SPEC header fingerprint as {f.get('facility')} {f.get('beamline')}"
    if "organization" in sc:
        return f"same organization {sc['organization']}"
    if "research_group" in sc:
        return f"same research group {sc['research_group']}"
    return "not offered yet: this beamtime's facility, beamline or research group is not confirmed"


def _shown(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def said(entry: Mapping) -> str:
    """``Earlier answer: pellet — Angel, 17 Nov 2026, beamtime SSRL_..._IrOxBase (same sample jk3)``."""
    return (f"Earlier answer: {_shown(entry.get('value'))} — {entry.get('by')}, {_date(entry.get('decided_utc'))}, "
            f"beamtime {entry.get('beamtime')} ({_scope_said(entry)})")


def _matches(entry: Mapping, want: Mapping) -> bool:
    """``entry``'s scope matches the new bundle's (``want``, from :meth:`Context.scope_for`): every key of its class
    equal; for a sample fact, a research group or organization present on BOTH sides and equal too (strict)."""
    have = entry.get("scope") or {}
    cls = entry.get("scope_class")
    if cls == SCOPE_SAMPLE:
        if not have.get("sample") or have.get("sample") != want.get("sample"):
            return False
        # STRICT: a group or organization confirmed on BOTH sides and equal; one missing on either side is no match
        shared = [k for k in ("research_group", "organization") if have.get(k) and want.get(k)]
        return bool(shared) and all(_norm(have[k]) == _norm(want[k]) for k in shared)
    if cls == SCOPE_BEAMLINE:
        a, b = have.get("beamline") or {}, want.get("beamline") or {}
        ka, kb = beamline_key(a.get("beamline")), beamline_key(b.get("beamline"))
        return bool(a and b) and _norm(a.get("facility")) == _norm(b.get("facility")) and ka is not None and ka == kb
    if cls == SCOPE_FINGERPRINT:
        a = (have.get("spec_fingerprint") or {}).get("fingerprint_id")
        return a is not None and a == (want.get("spec_fingerprint") or {}).get("fingerprint_id")
    if cls in (SCOPE_ORGANIZATION, SCOPE_RESEARCH_GROUP):
        return bool(have.get(cls)) and bool(want.get(cls)) and _norm(have[cls]) == _norm(want[cls])
    return False


def _fits(field: str, value: Any) -> bool:
    if field == CLOCK_ZONE_FIELD:
        return B.clock_zone_problem(value) is None
    if field in B._writable_paths():
        return B.value_problem(field, value) is None
    return True


def earlier_answers_for(entries: Sequence[Mapping], ctx: Context, field: str,
                        target_runs: Sequence[Sequence[str]] | None) -> list[dict]:
    """The earlier-answer hints for ``field`` in the new bundle (``ctx``), one per distinct value (its newest answer).
    ``target_runs``: each target's runs (a sample fact needs every target in a group of ONE sample identity)."""
    cls = scope_class_of(field)
    if cls is None:
        return []
    sample = None
    if cls == SCOPE_SAMPLE:
        idents = []
        for runs in target_runs or ():
            if not runs:
                return []
            idents += [ctx.sample_of_run(r) for r in runs]
        if not idents or any(i is None for i in idents) or len({json.dumps(i, sort_keys=True) for i in idents}) != 1:
            return []  # a target outside a group, without a stated sample, or a question spanning two samples
        sample = idents[0]
    want = ctx.scope_for(cls, sample)
    if want is None:
        return []
    found = [e for e in entries if e.get("field") == field and e.get("bundle_id") != ctx.bundle_id
             and _matches(e, want) and _fits(field, e.get("value"))]
    by_value: dict[str, list[Mapping]] = {}
    for e in sorted(found, key=lambda e: str(e.get("decided_utc") or ""), reverse=True):
        by_value.setdefault(_norm(e.get("value")), []).append(e)
    differ = len(by_value) > 1
    hints = []
    for group in list(by_value.values())[:MAX_VALUES_SHOWN]:
        e = group[0]
        hints.append({
            "kind": HINT_KIND, "field": field, "literal": e["value"], "value": e["value"], "entry_id": e["entry_id"],
            "by": e.get("by"), "decided_utc": e.get("decided_utc"), "date": _date(e.get("decided_utc")),
            "beamtime": e.get("beamtime"), "matched_on": _scope_said(e),
            "locator": f"beamtime {e.get('beamtime')}, answered by {e.get('by')} on {_date(e.get('decided_utc'))}",
            "times_given": len(group), "said": said(e), "disagrees": differ, "note": NOTE,
        })
    return hints


def question_hints(q: Mapping, entries: Sequence[Mapping], ctx: Context) -> list[dict]:
    """Every earlier-answer hint for one consolidated question (value questions and the clock-zone question)."""
    kind = q.get("kind")
    kind_of = {t.get("id"): t.get("kind") for t in q.get("targets") or ()}

    def runs(ids: Iterable[str]) -> list[list[str]]:
        return [ctx.runs_of_target(kind_of.get(i), i) for i in ids]

    if kind == "clock_time_zone":
        return earlier_answers_for(entries, ctx, CLOCK_ZONE_FIELD, None)
    if kind == "optional_values":
        out = []
        for path, ids in sorted((q.get("fields") or {}).items()):
            out += earlier_answers_for(entries, ctx, path, runs(ids))
        return out
    from . import questions as Q

    if kind in Q.VALUE_KINDS and q.get("target_field_path"):
        return earlier_answers_for(entries, ctx, q["target_field_path"], runs(kind_of))
    return []


def statement_of(hints: Sequence[Mapping]) -> str:
    """One sentence for a question's earlier answers: each said, and that they disagree when they do."""
    by_field: dict[str, list[Mapping]] = {}
    for h in hints:
        by_field.setdefault(h["field"], []).append(h)
    parts = []
    for field, hs in by_field.items():
        if len(hs) > 1:
            parts.append(f"Earlier answers disagree for {field}: "
                         + "; ".join(h["said"].removeprefix("Earlier answer: ") for h in hs) + ". " + DISAGREE_NOTE)
        else:
            parts.append(hs[0]["said"] + ".")
    return " ".join(parts) + " A hint, never an answer: confirm it with the scientist first."


def annotate(questions: Sequence[Mapping], bundle: Mapping, *, entries: Sequence[Mapping] | None = None) -> list[dict]:
    """``questions`` with ``earlier_answers`` (and ``earlier_answers_statement``) ADDED where an earlier answer
    matches: a copy; ids, blocking, counts, hints and text are never changed. Unchanged when the memory is off."""
    if entries is None:
        path = memory_path()
        if path is None or not is_enabled(path):
            return list(questions)
        try:
            entries = load(path).get("entries") or []
        except MemoryRefused:
            return list(questions)
    if not entries:
        return list(questions)
    ctx = Context(bundle)
    out = []
    for q in questions:
        hints = question_hints(q, entries, ctx)
        out.append({**q, "earlier_answers": hints, "earlier_answers_statement": statement_of(hints)} if hints else q)
    return out


def exposures(questions: Sequence[Mapping]) -> list[tuple[str, str]]:
    """``[(kind, id)]``: every target an annotated question shows an earlier answer for (an optional-values
    question: the hinted fields' targets), to record in the bundle's ``exposures`` under :data:`EXPOSURE_COMMAND`
    before the page is printed, as the parser values a page shows are recorded."""
    out: list[tuple[str, str]] = []
    for q in questions:
        hints = q.get("earlier_answers") or ()
        if not hints:
            continue
        kind_of = {t.get("id"): t.get("kind") for t in q.get("targets") or ()}
        if q.get("kind") == "optional_values":
            ids = [i for f in dict.fromkeys(h["field"] for h in hints) for i in (q.get("fields") or {}).get(f) or ()]
        else:
            ids = list(kind_of)
        out += [(str(kind_of[i]), str(i)) for i in ids if kind_of.get(i)]
    return list(dict.fromkeys(out))


def annotate_minimum(minimum: Mapping | None, payload: Mapping, bundle: Mapping,
                     exposed: list | None = None) -> Mapping | None:
    """``minimum_for_one_group`` with each of its questions' earlier answers added (for the scope it is answered at).
    ``exposed``: extended with the targets those earlier answers are shown for (:func:`exposures`)."""
    if not minimum or not minimum.get("questions"):
        return minimum
    by_id = {q["question_id"]: q for q in payload.get("questions") or ()}
    wanted = []
    for m in minimum["questions"]:
        q = by_id.get(m.get("question_id"))
        if q is None:
            continue
        if m.get("only") and (q.get("per_scope_targets") or {}).get(m["only"]) is not None:
            ids = set(q["per_scope_targets"][m["only"]])
            q = {**q, "targets": [t for t in q.get("targets") or () if t.get("id") in ids],
                 **({"fields": {f: [i for i in v if i in ids] for f, v in q["fields"].items()}} if q.get("fields") else {})}
        wanted.append(q)
    annotated = {q["question_id"]: q for q in annotate(wanted, bundle) if q.get("earlier_answers")}
    if not annotated:
        return minimum
    if exposed is not None:
        exposed.extend(exposures(list(annotated.values())))
    out = copy.deepcopy(dict(minimum))
    for m in out["questions"]:
        a = annotated.get(m.get("question_id"))
        if a is not None:
            # the standing note is the statement's last sentence: said once, not per hint
            m["earlier_answers"] = [{k: v for k, v in h.items() if k != "note"} for h in a["earlier_answers"]]
            m["earlier_answers_statement"] = a["earlier_answers_statement"]
    return out


# --- confirming one ------------------------------------------------------------------------------------------------

def provenance_note(entry_id: str, *, decision: str, value: Any, field: str | None, note: str | None) -> str:
    """The note a decision confirmed from an earlier answer carries. Refused unless the entry exists, is for this
    field, and the decision gives exactly its value (``correct --value`` / ``set_clock_time_zone --value``)."""
    entries = (load().get("entries") or []) if memory_path() is not None else []
    entry = next((e for e in entries if e.get("entry_id") == entry_id), None)
    if entry is None:
        raise MemoryRefused(f"No remembered earlier answer {entry_id!r} on this computer. Nothing was recorded.")
    if decision not in ("correct", "set_clock_time_zone"):
        raise MemoryRefused("--from-earlier-answer goes with --decision correct (or set_clock_time_zone) and --value "
                            "<the earlier value>. Nothing was recorded.")
    if field is not None and entry.get("field") != field:
        raise MemoryRefused(f"Earlier answer {entry_id} is for {entry.get('field')}, not {field}. Nothing was recorded.")
    if value is None or _norm(value) != _norm(entry.get("value")):
        raise MemoryRefused(f"Earlier answer {entry_id} is {_shown(entry.get('value'))!r}; --value must give exactly "
                            "that value (or answer without --from-earlier-answer). Nothing was recorded.")
    said_note = (f"{PROVENANCE_PREFIX} ({entry_id}): {_shown(entry.get('value'))!r} given by {entry.get('by')} on "
                 f"{_date(entry.get('decided_utc'))} for beamtime {entry.get('beamtime')} ({_scope_said(entry)}); "
                 "confirmed for this beamtime by the person answering now.")
    return f"{note.strip()} {said_note}" if isinstance(note, str) and note.strip() else said_note


def field_of_question(q: Mapping | None, field: str | None) -> str | None:
    if q is None:
        return None
    if q.get("kind") == "clock_time_zone":
        return CLOCK_ZONE_FIELD
    if q.get("kind") == "optional_values":
        return field
    return q.get("target_field_path")
