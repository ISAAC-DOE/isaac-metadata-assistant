"""SCAN NOTES (bundle 1.12.0): what a logbook says about a run's scans, as a reading pass found it.

A logbook often curates scans: "discard the first scan", "start from scan #5", "only scans 1-8 usable", "ignore
scan 8 (went to open circuit)", "the potentiostat jumped to 2.5 V during this file". That is evidence for the
processing step's scan-selection proposal, which no parser reads. A reading pass writes it as a ``scan_note``
finding in its findings file (``isaac.reading_findings``)::

    {"kind": "scan_note",
     "applies_to": {"scope": "runs", "runs": ["<stem or run id>"]},
     "action": "exclude" | "start_from" | "keep_only" | "flag",
     "scans": [<int>, ...],
     "reason": "<plain words>",
     "source": {"path": "...", "locator": "line 1300"}, "quote": "...",
     "strength": "stated" | "inferred", "reasoning": "..."}

* ``exclude``: leave out the listed scans. ``start_from``: exactly ONE scan number; the scans before it are left
  out. ``keep_only``: keep only the listed scans. ``flag``: NO scan numbers; advice that changes nothing (a jump,
  material loss, a remark about the whole file).
* Scan numbers are the logbook's own (1-based, as the scientist counts the scans of that file): no mapping to any
  other numbering is applied here.
* ``annotate --from-readings`` checks its quote like any finding's (:mod:`.reading_check`), refuses a run reference
  that names no run or more than one, and keeps it in ``bundle["scan_notes"]``, once.

A SCAN NOTE IS AN AI READING, NEVER A DECISION. Nothing here leaves a scan out of anything: the processing step may
PROPOSE a scan selection from it, saying which note it read, and only the scientist's word changes what is merged.

Read them with :func:`scan_notes_for_run` (the processing step's accessor), ``isaac bundle show <dir> run <id>``
(``scan_notes``) and ``isaac bundle list <dir> scan-notes``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

KIND = "scan_note"
ACTIONS = ("exclude", "start_from", "keep_only", "flag")
#: The bound on ``bundle["scan_notes"]`` (the schema's ``maxItems``).
MAX_SCAN_NOTES = 20_000
#: The most runs one note names (the schema's ``run_ids`` maxItems): a note naming more is refused ALONE.
MAX_RUNS_PER_NOTE = 500
#: The most scan numbers one note lists, and the largest scan number.
MAX_SCANS = 500
MAX_SCAN_NUMBER = 100_000
MAX_REASON_CHARS = 500
AUTHORITY = "ai_reading"
NOTE = ("An AI reading of what a file says about these scans: evidence for a scan-selection proposal, never a "
        "decision. Nothing is left out of a merge until the scientist says so.")


def _scans_problem(action: str, scans: Any) -> tuple[list[int] | None, str | None]:
    """``(scans, None)`` normalised (unique, ascending), or ``(None, why)``."""
    if action == "flag":
        if scans in (None, []):
            return [], None
        return None, "a `flag` note names no scan numbers (it is advice about the run that changes nothing): drop `scans`"
    if not isinstance(scans, list) or not scans:
        return None, f"a `{action}` note needs `scans`, a non-empty list of scan numbers"
    if not all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= MAX_SCAN_NUMBER for n in scans):
        return None, f"`scans` holds whole scan numbers from 1 to {MAX_SCAN_NUMBER:,}, as the file numbers them"
    if len(scans) > MAX_SCANS:
        return None, f"`scans` lists at most {MAX_SCANS} scan numbers"
    if action == "start_from" and len(scans) != 1:
        return None, "a `start_from` note takes exactly ONE scan number (the first scan to keep)"
    return sorted(set(scans)), None


def live_run_ids(bundle: Mapping) -> set[str]:
    """Runs in a live record group (every run before grouping)."""
    from . import bundle as B

    groups = bundle.get("record_groups") or ()
    if not groups:
        return {r["run_id"] for r in bundle.get("runs") or ()}
    by_key = {r["run_key"]: r["run_id"] for r in bundle.get("runs") or ()}
    return {by_key[k] for g in groups if g.get("status") in B.LIVE_GROUP_STATUSES
            for k in g.get("member_run_keys") or () if k in by_key}


def plan_scan_note(bundle: Mapping, finding: Mapping, *, fid: str, runs_by_ref: Mapping[str, set], model_id: str,
                   canonical_path: str | None = None) -> tuple[dict | None, dict | None]:
    """``(entry, None)`` for a valid ``scan_note`` finding, or ``(None, skipped)``. Pure. The quote is checked by
    the caller (:mod:`.reading_check`), as for every finding; ``canonical_path`` is the cited path as the folder
    spells it (``reading_check.canonical_cited``), by which its source is found. A run outside every live group is
    accepted: :func:`scan_notes_for_run` marks it (``run_live: false``)."""

    def skip(reason: str, refused: str | None = None) -> tuple[None, dict]:
        return None, {"finding": fid, "kind": KIND, "reason": reason, **({"refused": refused} if refused else {})}

    action = finding.get("action")
    if action not in ACTIONS:
        return skip(f"`action` must be one of {', '.join(ACTIONS)}")
    scans, problem = _scans_problem(action, finding.get("scans"))
    if problem:
        return skip(problem)
    reason = finding.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return skip("a scan note needs `reason`: in plain words, why (as the file says it)")
    source = finding.get("source") if isinstance(finding.get("source"), Mapping) else {}
    quote = finding.get("quote")
    if not source.get("path") or not source.get("locator") or not isinstance(quote, str) or not quote.strip():
        return skip("a scan note needs source.path, source.locator and quote")
    strength = finding.get("strength")
    if strength not in ("stated", "inferred"):
        return skip("a scan note needs `strength`: `stated` or `inferred`")
    applies = finding.get("applies_to") if isinstance(finding.get("applies_to"), Mapping) else {}
    if applies.get("scope") != "runs":
        return skip("a scan note is about particular runs: applies_to.scope must be `runs`")
    refs = applies.get("runs") if "runs" in applies else applies.get("run_labels")
    if not isinstance(refs, list) or not refs or not all(isinstance(r, str) and r for r in refs):
        return skip("applies_to.runs must be a non-empty list of run references (each run's stem or run id)")
    unknown = [r for r in refs if r not in runs_by_ref]
    if unknown:
        return skip(f"run references not in this bundle: {unknown[:5]} (name a run by its file stem or run id, as "
                    "`bundle list <dir> runs` prints them)", "unknown_run")
    ambiguous = [r for r in refs if len(runs_by_ref[r]) > 1]
    if ambiguous:
        return skip(f"a run reference names more than one run ({ambiguous[:3]}): name each by its run id or path",
                    "ambiguous_run")
    run_ids = sorted({rid for r in refs for rid in runs_by_ref[r]})
    if len(run_ids) > MAX_RUNS_PER_NOTE:
        return skip(f"the note names {len(run_ids)} runs, more than the {MAX_RUNS_PER_NOTE} one note may name: split it "
                    "into notes of at most that many runs (only this note was left out)")
    src_by_path = {s.get("relative_path"): s.get("source_id") for s in bundle.get("sources") or ()}
    rel = str(canonical_path or source["path"])
    identity = {"run_ids": run_ids, "action": action, "scans": scans, "source_path": rel,
                "locator": str(source["locator"]), "quote": quote}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    scan_count = {r["run_id"]: r.get("scan_count") for r in bundle.get("runs") or ()}
    beyond = sorted({rid for rid in run_ids for n in scans if isinstance(scan_count.get(rid), int) and n > scan_count[rid]})
    entry = {
        "scan_note_id": f"sn-{digest}",
        "run_ids": run_ids,
        "action": action,
        "scans": scans,
        "reason": reason.strip()[:MAX_REASON_CHARS],
        "source_path": rel[:500],
        "source_id": src_by_path.get(rel),
        "locator": str(source["locator"])[:300],
        "quote": quote[:300],
        "strength": strength,
        "reasoning": str(finding.get("reasoning") or "")[:1000],
        "finding_id": fid,
        "model": {"model_id": str(model_id)[:200]},
        "authority": AUTHORITY,
    }
    if beyond:
        entry["scan_count_note"] = (f"names a scan number past the scans the import counted for {', '.join(beyond[:5])}: "
                                    "the logbook may count scans differently; the processing step says which it used")[:500]
    return entry, None


def record_scan_notes(bundle: dict, planned: list[dict]) -> tuple[int, int]:
    """Append each planned note not already held (by ``scan_note_id``). ``(recorded, already_recorded)``."""
    held = bundle.setdefault("scan_notes", [])
    have = {n.get("scan_note_id") for n in held}
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = 0
    for entry in planned:
        if entry["scan_note_id"] in have:
            continue
        have.add(entry["scan_note_id"])
        held.append({**entry, "recorded_utc": at})
        new += 1
    return new, len(planned) - new


def _conflict(a: Mapping, b: Mapping) -> str | None:
    """Why two notes on one run cannot both be followed, or ``None``. Two notes saying the same thing do not conflict;
    an ``exclude`` beside a ``start_from`` does not either (both leave scans out). A ``flag`` changes nothing."""
    acts = {a["action"], b["action"]}
    sa, sb = set(a.get("scans") or ()), set(b.get("scans") or ())
    if "flag" in acts:
        return None
    if acts == {"exclude", "keep_only"}:
        both = sorted(sa & sb)
        return f"scan(s) {', '.join(map(str, both))} both excluded and kept only" if both else None
    if acts == {"keep_only"} and sa != sb:
        return "two different keep-only lists"
    if acts == {"start_from"} and sa != sb:
        return f"two different first scans to keep ({min(sa)} and {min(sb)})"
    if acts == {"start_from", "keep_only"}:
        first = min(sa if a["action"] == "start_from" else sb)
        kept = sb if a["action"] == "start_from" else sa
        before = sorted(k for k in kept if k < first)
        return (f"the keep-only list holds scan(s) {', '.join(map(str, before))}, before the first scan to keep ({first})"
                if before else None)
    return None


def _notes_on(bundle: Mapping, run_id: str) -> list[Mapping]:
    return [n for n in bundle.get("scan_notes") or () if isinstance(n, Mapping) and run_id in (n.get("run_ids") or ())]


def scan_note_conflicts(bundle: Mapping, run_id: str) -> list[dict]:
    """Every pair of notes on run ``run_id`` that cannot both be followed: ``[{"notes": [id, id], "why"}]``. The
    scientist settles it; nothing here picks one."""
    notes = _notes_on(bundle, run_id)
    out = []
    for i, a in enumerate(notes):
        for b in notes[i + 1:]:
            why = _conflict(a, b)
            if why:
                out.append({"notes": [a.get("scan_note_id"), b.get("scan_note_id")], "why": why})
    return out


def scan_notes_for_run(bundle: Mapping, run_id: str) -> list[dict]:
    """THE ACCESSOR the processing step calls: every scan note naming run ``run_id``, in the order recorded.

    Each is a copy: ``scan_note_id``, ``action`` (``exclude`` / ``start_from`` / ``keep_only`` / ``flag``),
    ``scans`` (the logbook's scan numbers; ``[]`` for ``flag``; one number for ``start_from``), ``reason``, the
    citation (``source_path``, ``locator``, ``quote``), ``strength``, ``reasoning``, ``model_id``, ``recorded_utc``,
    ``run_live`` (``False`` when the run is in no live record group now), ``conflicts`` (``[{"with": <note id>,
    "why"}]``: the notes on this run it cannot be followed together with, :func:`scan_note_conflicts`; ``[]`` for
    none) and, when set, ``scan_count_note``. An AI reading, never a decision: a caller may propose a scan selection
    from it, citing the ``scan_note_id``, must say every conflict instead of choosing a side, and must never leave a
    scan out on its strength alone. ``[]`` for a bundle without the section (older than 1.12.0) or a run no note names."""
    live = run_id in live_run_ids(bundle)
    with_: dict[str, list[dict]] = {}
    for c in scan_note_conflicts(bundle, run_id):
        a, b = c["notes"]
        with_.setdefault(a, []).append({"with": b, "why": c["why"]})
        with_.setdefault(b, []).append({"with": a, "why": c["why"]})
    out = []
    for n in _notes_on(bundle, run_id):
        out.append({
            "scan_note_id": n.get("scan_note_id"),
            "action": n.get("action"),
            "scans": list(n.get("scans") or ()),
            "reason": n.get("reason"),
            "source_path": n.get("source_path"),
            "locator": n.get("locator"),
            "quote": n.get("quote"),
            "strength": n.get("strength"),
            "reasoning": n.get("reasoning"),
            "model_id": (n.get("model") or {}).get("model_id"),
            "recorded_utc": n.get("recorded_utc"),
            "run_live": live,
            "conflicts": with_.get(n.get("scan_note_id"), []),
            **({"scan_count_note": n["scan_count_note"]} if n.get("scan_count_note") else {}),
        })
    return out


def list_row(bundle: Mapping, note: Mapping) -> dict:
    """``bundle list <dir> scan-notes``: one compact row, with the notes it conflicts with on any of its runs and its
    runs that are in no live record group now."""
    stems = {r["run_id"]: r.get("stem") for r in bundle.get("runs") or ()}
    live = live_run_ids(bundle)
    me = note.get("scan_note_id")
    # THIS note against each other note on its runs, each compared once (before: every pair on every run, per row)
    mine = set(note.get("run_ids") or ())
    others = {n.get("scan_note_id"): n for n in bundle.get("scan_notes") or ()
              if isinstance(n, Mapping) and n.get("scan_note_id") != me and mine & set(n.get("run_ids") or ())}
    conflicts = sorted(other for other, n in others.items() if _conflict(note, n))
    not_live = [stems.get(r) or r for r in note.get("run_ids") or () if r not in live]
    return {
        "scan_note_id": me,
        "runs": [stems.get(r) or r for r in note.get("run_ids") or ()][:20],
        "action": note.get("action"),
        "scans": list(note.get("scans") or ())[:50],
        "reason": note.get("reason"),
        "cited": f"{note.get('source_path')} {note.get('locator')}",
        "strength": note.get("strength"),
        "conflicts": conflicts,
        **({"runs_not_live": not_live[:20]} if not_live else {}),
    }
