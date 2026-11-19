"""AN APPROVED CURVE OLDER THAN ITS EVIDENCE (audit of 18 Nov 2026, finding 2). Stdlib only; reads the bundle.

A scientist's approval of a processing result stays on that result: processing a group again never replaces an
approved curve (``mutations.process`` keeps every decided result). That is right, and it had one silent failure: a
logbook scan note loaded AFTER the approval ("ignore the last scan, it went to open circuit"), or a newer result
processed with that note, changed nothing a scientist was told. The record kept the old curve, ``validate`` said
exportable and ``export`` wrote it with a ``valid`` QC status.

This module says it, and decides nothing:

* :func:`older_than_evidence`: for one record group, the approved result and what is newer than it: a scan note its
  curve was processed without, a scan note recorded after the approval, a newer processing result.
* :func:`warning`: the composer's warning for it (:data:`WARNING`), which ``build-records``, ``validate`` and
  ``export`` print FIRST (``records.warning_rank``).
* :func:`approval_problem`: why an approval is refused: in a BULK call, a result whose group holds a scan note it was
  processed without, or a newer result; on its own, only a result processed without a scan note while the group has
  not been processed again (one command fixes it). Otherwise one approval on its own stays the scientist's call.

Nothing here changes a curve, a decision or what "exportable" means: a warning is said, never a gate.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import bundle as B

WARNING = "approved_curve_older_than_evidence"
#: ``processing.engine_xas.LOGBOOK_KEY`` (not imported: processing is an optional extra)
C_LOGBOOK_KEY = "logbook_notes"
C_ATHENA_SOURCE = "scientist_athena"
NOT_IN_CURVE = "scan_note_not_in_the_approved_curve"
AFTER_APPROVAL = "scan_note_after_the_approval"
NEWER_RESULT = "newer_result"
EVIDENCE_SHOWN = 3


def _group(bundle: Mapping, group_id: str) -> Mapping | None:
    return next((g for g in bundle.get("record_groups") or () if g.get("group_id") == group_id), None)


def _run_ids(bundle: Mapping, group: Mapping | None) -> list[str]:
    if not group:
        return []
    ids = list(group.get("member_run_ids") or ())
    if not ids:
        by_key = {r.get("run_key"): r.get("run_id") for r in bundle.get("runs") or ()}
        ids = [by_key[k] for k in group.get("member_run_keys") or () if k in by_key]
    return ids


def _notes(bundle: Mapping, run_ids: Sequence[str]) -> list[tuple[Mapping, str]]:
    """``[(note, run id)]``: every scan note naming one of ``run_ids``, once per run it names."""
    wanted = set(run_ids)
    return [(n, rid) for n in bundle.get("scan_notes") or () if isinstance(n, Mapping)
            for rid in n.get("run_ids") or () if rid in wanted]


def _block(result: Mapping) -> Mapping | None:
    """The result's logbook block when it has one that could list notes (isaac.xas.v1), else ``None``."""
    lb = result.get(C_LOGBOOK_KEY)
    return lb if isinstance(lb, Mapping) and lb.get("available") is not False else None


def _listed(block: Mapping, note: Mapping, stem: Any) -> bool:
    for e in block.get("notes") or ():
        if not isinstance(e, Mapping):
            continue
        if e.get("scan_note_id") and e.get("scan_note_id") == note.get("scan_note_id"):
            return True
        if (not e.get("scan_note_id") and e.get("run") == stem and e.get("action") == note.get("action")
                and list(e.get("scans") or ()) == list(note.get("scans") or ())):
            return True  # a result an older build made lists a note by its run, action and scans
    return False


#: On a processing result (it allows extra keys): the scan notes that named its group's runs WHEN IT WAS APPROVED,
#: ``{"decision_id", "scan_note_ids"}``, written with the approval (:func:`approval_snapshot`). A note not among them
#: came after the approval, whatever the clocks say (they have one-second resolution).
SNAPSHOT_KEY = "scan_notes_at_approval"


def approval_snapshot(bundle: Mapping, result: Mapping, decision_id: Any) -> dict:
    """What ``decide --decision approve`` keeps on ``result``: the ids of the scan notes on its group's runs now."""
    notes = _notes(bundle, _run_ids(bundle, _group(bundle, result.get("group_id"))))
    return {"decision_id": decision_id, "scan_note_ids": sorted({str(n.get("scan_note_id")) for n, _ in notes})}


def _after_approval(result: Mapping, decision: Mapping, note: Mapping) -> bool:
    """True when ``note`` was not there when ``decision`` approved ``result``: by the approval's own snapshot when
    this build recorded one for that decision, else by the two timestamps (an approval an older build recorded)."""
    snap = result.get(SNAPSHOT_KEY)
    if isinstance(snap, Mapping) and snap.get("decision_id") == decision.get("decision_id"):
        return str(note.get("scan_note_id")) not in set(snap.get("scan_note_ids") or ())
    approved_utc = str(decision.get("decided_utc") or "")
    return bool(approved_utc) and str(note.get("recorded_utc") or "") > approved_utc


def approval_predates_a_note(bundle: Mapping, result: Mapping, approval: Mapping) -> bool:
    """True when a scan note on the runs of ``result``'s group was not there when ``approval`` was recorded."""
    return any(_after_approval(result, approval, note)
               for note, _ in _notes(bundle, _run_ids(bundle, _group(bundle, result.get("group_id")))))


def unlisted_notes(bundle: Mapping, result: Mapping) -> list[dict]:
    """The scan notes on the runs of ``result``'s group that its logbook block does not list: the curve was processed
    without them. ``[]`` for a result with no logbook block (nothing can be compared)."""
    block = _block(result)
    if block is None:
        return []
    stems = {r.get("run_id"): r.get("stem") for r in bundle.get("runs") or ()}
    out, seen = [], set()
    for note, rid in _notes(bundle, _run_ids(bundle, _group(bundle, result.get("group_id")))):
        if note.get("scan_note_id") in seen or _listed(block, note, stems.get(rid)):
            continue
        seen.add(note.get("scan_note_id"))
        out.append(_said(note, stems.get(rid), NOT_IN_CURVE))
    return out


def _said(note: Mapping, stem: Any, why: str) -> dict:
    return {"why": why, "scan_note_id": note.get("scan_note_id"), "run": stem, "action": note.get("action"),
            "scans": list(note.get("scans") or ()), "reason": note.get("reason"), "quote": note.get("quote"),
            "cited": f"{note.get('source_path')} {note.get('locator')}", "recorded_utc": note.get("recorded_utc")}


def _is_newer(other: Mapping, than: Mapping, order: Mapping[str, int]) -> bool:
    a, b = other.get("run_id"), than.get("run_id")
    a_after = b is not None and b in (other.get("prior_run_ids") or ())
    b_after = a is not None and a in (than.get("prior_run_ids") or ())
    if a_after != b_after:
        return a_after
    return order.get(B.processing_id(other), -1) > order.get(B.processing_id(than), -1)


def newer_results(bundle: Mapping, result: Mapping, state_of: Mapping | None = None) -> list[Mapping]:
    """The results of ``result``'s group processed AFTER it that are not rejected (ISAAC's own, never the scientist's
    Athena curve, never "the protocol does not apply")."""
    state_of = state_of if state_of is not None else B.processing_state_decisions(bundle)
    results = list(bundle.get("processing_results") or ())
    order = {B.processing_id(r): i for i, r in enumerate(results)}
    pid = B.processing_id(result)
    out = []
    for r in results:
        if r.get("group_id") != result.get("group_id") or B.processing_id(r) == pid:
            continue
        if r.get("source") == C_ATHENA_SOURCE or B.processing_not_applicable(r):
            continue
        if (state_of.get(("processing_result", B.processing_id(r))) or {}).get("decision") == "reject":
            continue
        if _is_newer(r, result, order):
            out.append(r)
    return out


def approved_result(bundle: Mapping, group_id: str, state_of: Mapping | None = None) -> tuple[Mapping, Mapping] | None:
    """``(result, its approve decision)`` when the group has exactly one approved result, else ``None`` (none, or
    several: the composer already refuses those)."""
    state_of = state_of if state_of is not None else B.processing_state_decisions(bundle)
    found = [(r, d) for r in bundle.get("processing_results") or ()
             if r.get("group_id") == group_id and not B.processing_not_applicable(r)
             and (d := state_of.get(("processing_result", B.processing_id(r))) or {}).get("decision") == "approve"]
    return found[0] if len(found) == 1 else None


def older_than_evidence(bundle: Mapping, group_id: str, state_of: Mapping | None = None) -> dict | None:
    """What is newer than the group's approved curve, or ``None`` (no approved result, or nothing newer):
    ``{"group_id", "approved_result_id", "approved_utc", "evidence": [{"why", ...}], "newer_result_ids"}``.

    A scan note counts when it was NOT THERE when the result was approved (:func:`_after_approval`): ``why`` is
    :data:`NOT_IN_CURVE` when the approved result's logbook block does not list it either (the curve was processed
    without it) and :data:`AFTER_APPROVAL` when the curve lists it (the same curve, but the person approved before
    the note). :data:`NEWER_RESULT`: a result of the group processed after the approved one, not rejected.
    Approving again, with the notes there, is what clears a note; rejecting or approving the newer result clears
    that."""
    state_of = state_of if state_of is not None else B.processing_state_decisions(bundle)
    found = approved_result(bundle, group_id, state_of)
    if found is None:
        return None
    result, decision = found
    approved_utc = str(decision.get("decided_utc") or "")
    block = _block(result)
    stems = {r.get("run_id"): r.get("stem") for r in bundle.get("runs") or ()}
    evidence, seen = [], set()
    for note, rid in _notes(bundle, _run_ids(bundle, _group(bundle, group_id))):
        nid = note.get("scan_note_id")
        if nid in seen:
            continue
        if not _after_approval(result, decision, note):
            continue  # the note was there when the scientist approved this result: their call, nothing newer
        why = NOT_IN_CURVE if block is not None and not _listed(block, note, stems.get(rid)) else AFTER_APPROVAL
        seen.add(nid)
        evidence.append(_said(note, stems.get(rid), why))
    newer = newer_results(bundle, result, state_of)
    for r in newer:
        evidence.append({"why": NEWER_RESULT, "result_id": B.processing_id(r),
                         "has_curve": bool((r.get("outputs") or {}).get("files")),
                         "qc_verdict": (r.get("qc") or {}).get("verdict")})
    if not evidence:
        return None
    return {"group_id": group_id, "approved_result_id": B.processing_id(result), "approved_utc": approved_utc or None,
            "evidence": evidence, "newer_result_ids": [B.processing_id(r) for r in newer],
            "processed_again": processed_again(bundle, result)}


def _note_said(e: Mapping) -> str:
    scans = f" {e['scans']}" if e.get("scans") else ""
    quote = f': "{e["quote"]}"' if e.get("quote") else ""
    return f"{e.get('run')}: {e.get('action')}{scans} ({e.get('reason')}; {e.get('cited')}{quote})"


def text(found: Mapping) -> str:
    """The warning's sentence: what is newer than the approved curve, and the next step for each kind."""
    pid = found["approved_result_id"]
    ev = found["evidence"]
    parts, steps = [], []
    unapplied = [e for e in ev if e["why"] == NOT_IN_CURVE]
    after = [e for e in ev if e["why"] == AFTER_APPROVAL]
    newer = [e for e in ev if e["why"] == NEWER_RESULT]
    for rows, lead in ((unapplied, "it was processed without {n} logbook scan note(s) that name its runs"),
                       (after, "{n} logbook scan note(s) on its runs came after the approval")):
        if rows:
            more = f"; and {len(rows) - EVIDENCE_SHOWN} more" if len(rows) > EVIDENCE_SHOWN else ""
            parts.append(lead.format(n=len(rows)) + " (" + "; ".join(_note_said(e) for e in rows[:EVIDENCE_SHOWN])
                         + more + ")")
    if newer:
        parts.append("a newer processing result exists for the group (" + ", ".join(
            f"{e['result_id']}" + ("" if e.get("has_curve") else ", which has no curve") for e in newer[:EVIDENCE_SHOWN])
            + ")")
    if unapplied and not newer and found.get("processed_again"):
        # processed again already, and that result was rejected: keeping this curve is one more statement
        steps.append(f"the group was processed again and that result is rejected; to keep this curve with the note(s) "
                     f"in front of the scientist, approve {pid} again (--target {pid} --decision approve --qc-status "
                     "<value>), or reject it")
    elif unapplied and not newer:
        steps.append(f"process the group again (`isaac process <bundle_dir> --source <the beamtime folder> --group "
                     f"{found['group_id']}`) and look at the new result")
    if newer:
        steps.append(f"look at {newer[0]['result_id']} (`isaac bundle show <bundle_dir> processing-result "
                     f"{newer[0]['result_id']}`); to make it the record's curve, withdraw this approval (--target "
                     f"{pid} --decision reject) and approve it; to keep this curve, reject the newer result"
                     + (f" and approve {pid} again" if unapplied or after else ""))
    if after and not unapplied and not newer:
        steps.append(f"read the note(s) and approve {pid} again if the curve still stands (--target {pid} --decision "
                     "approve --qc-status <value>), or reject it")
    return (f"The record's curve is approved result {pid}, which is older than its evidence: " + "; and ".join(parts)
            + ". The record keeps the approved curve until a scientist decides. Next: " + "; ".join(steps) + ".")


def warning(found: Mapping) -> dict:
    """The composer's warning for :func:`older_than_evidence` (``records.compose_group``): first in every list."""
    gid, pid = found["group_id"], found["approved_result_id"]
    newer = found.get("newer_result_ids") or []
    if newer:
        command = f"isaac bundle show <bundle_dir> processing-result {newer[0]}"
    elif any(e["why"] == NOT_IN_CURVE for e in found["evidence"]) and not found.get("processed_again"):
        command = f"isaac process <bundle_dir> --source <the beamtime folder you imported> --group {gid}"
    else:
        command = (f'isaac bundle decide <bundle_dir> --target {pid} --decision approve --qc-status <value> '
                   f'--by "<your name>"')
    return {"code": WARNING, "group_id": gid, "path": "measurement.series", "needs": "measurement.series", "targets": [],
            "approved_result_id": pid, "newer_result_ids": list(newer),
            "evidence": [dict(e) for e in found["evidence"]], "command": command, "text": text(found)}


def processed_again(bundle: Mapping, result: Mapping) -> bool:
    """True when the group holds a result processed AFTER ``result``, whatever was decided on it."""
    results = list(bundle.get("processing_results") or ())
    order = {B.processing_id(r): i for i, r in enumerate(results)}
    return any(r.get("group_id") == result.get("group_id") and B.processing_id(r) != B.processing_id(result)
               and r.get("source") != C_ATHENA_SOURCE and _is_newer(r, result, order) for r in results)


def approval_problem(bundle: Mapping, result: Mapping, *, bulk: bool) -> str | None:
    """Why approving ``result`` is refused because its curve is older than its evidence, or ``None``.

    * Its group holds a scan note the result was processed without: refused in a bulk call always, and on its own
      until the group has been processed again (then the scientist has the newer result beside it and may keep this
      curve, on its own).
    * A newer result of its group exists (not rejected): refused in a bulk call; on its own it is the scientist's call."""
    pid, gid = B.processing_id(result), result.get("group_id")
    missing = unlisted_notes(bundle, result)
    again = processed_again(bundle, result)
    if missing and (bulk or not again):
        more = f"; and {len(missing) - EVIDENCE_SHOWN} more" if len(missing) > EVIDENCE_SHOWN else ""
        step = (f"Approve the result processed with them, or approve {pid} on its own if the scientist keeps this curve."
                if again else
                f"Process the group again (`isaac process <bundle_dir> --source <the beamtime folder> --group {gid}`) "
                "and approve the result it makes; if it makes the same curve, this one then lists the note(s) and can "
                "be approved.")
        return (f"{pid} was processed without {len(missing)} logbook scan note(s) that name its runs ("
                + "; ".join(_note_said(e) for e in missing[:EVIDENCE_SHOWN]) + more + "): its curve is older than "
                f"that evidence. {step} Nothing was recorded.")
    if bulk:
        newer = newer_results(bundle, result)
        if newer:
            return (f"{pid} is not the newest result of group {gid}: {B.processing_id(newer[0])} was processed after "
                    f"it. Approve the newer one, or approve {pid} on its own if the scientist keeps this curve. "
                    "Nothing was recorded.")
    return None


def refresh_kept_block(kept: dict, fresh: Mapping) -> list[str]:
    """``process`` made the SAME result again (same id, so the same curve) for a result a scientist already decided:
    the kept result's logbook block takes the notes the fresh one lists, so it no longer reads as "processed without
    them" (whether they came after the approval is the approval's own snapshot, :data:`SNAPSHOT_KEY`). Returns the
    scan note ids gained. Touches nothing else of ``kept``."""
    new_block = fresh.get(C_LOGBOOK_KEY)
    if not isinstance(new_block, Mapping):
        return []
    old_block = kept.get(C_LOGBOOK_KEY) if isinstance(kept.get(C_LOGBOOK_KEY), Mapping) else {}
    had = {e.get("scan_note_id") for e in old_block.get("notes") or () if isinstance(e, Mapping)}
    gained = [e.get("scan_note_id") for e in new_block.get("notes") or ()
              if isinstance(e, Mapping) and e.get("scan_note_id") and e.get("scan_note_id") not in had]
    if gained:
        kept[C_LOGBOOK_KEY] = dict(new_block)
    return gained
