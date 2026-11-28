"""``isaac bundle status <dir>``: where an import stands, in a few plain lines (C4 of the 22 Nov 2026 plan).

A second conversation on an unfinished beamtime starts here (skill audit of 18 Nov 2026, finding 10): who the
scientist is and whether they consented to Claude reading the files (both recorded by ``bundle consent``), how many
runs and record groups there are, how many records the last ``bundle validate`` found exportable, the open questions
(blocking and optional), the last processing, and the one thing to do next.

IT READS ONLY. Nothing is written: not ``bundle.json`` (an older format is reported, and upgraded only by the next
command that records something), not an exposure (it prints counts, a name and dates, never a parser value).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

#: Where ``isaac process`` writes its run header (``processing.run.PROCESSING_DIR`` / ``RESULTS_FILE``; not imported:
#: that module loads the processing engine's dependencies).
PROCESSING_RESULTS_FILE = "processing/processing_results.json"
#: A header this large is not read (a processing results file of a real beamtime is a few MB).
MAX_PROCESSING_HEADER_BYTES = 64 * 1024 * 1024


def _day(utc: str | None) -> str | None:
    """``2026-11-22T13:29:00Z`` → ``22 Nov 2026 13:29 UTC`` (plain to read); anything else as given."""
    if not isinstance(utc, str):
        return None
    try:
        t = datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return utc
    return f"{t.day} {t.strftime('%b %Y %H:%M')} UTC"


def _last_processing(bundle_dir: Path) -> str | None:
    from . import records as R

    f = R.contained_file(bundle_dir, PROCESSING_RESULTS_FILE)
    if f is None:
        return None
    try:
        if f.stat().st_size > MAX_PROCESSING_HEADER_BYTES:
            return None
        header = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return header.get("created_utc") if isinstance(header, Mapping) and isinstance(header.get("created_utc"), str) else None


def _last_validation(bundle_dir: Path, bundle: Mapping, live_ids: set[str]) -> dict:
    """What the last ``bundle validate`` wrote for the live groups (``validation/<group>.json``), as the Local Imports
    page reads it (``local_bundles.progress``): exportable, held by the local record-completeness gate, other; and how
    many reports are older than ``bundle.json`` (answers given since are not in them)."""
    from . import bundle as B
    from . import records as R

    try:
        bundle_mtime = B.bundle_path(bundle_dir).stat().st_mtime
    except OSError:
        bundle_mtime = None
    out = {"reports": 0, "exportable": 0, "held": 0, "older_than_bundle": 0, "last_utc": None}
    last = None
    for gid in sorted(live_ids):
        f = R.contained_file(bundle_dir, f"{R.VALIDATION_DIR}/{gid}.json")
        if f is None:
            continue
        try:
            report = json.loads(f.read_text(encoding="utf-8"))
            mtime = f.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(report, Mapping):
            continue
        out["reports"] += 1
        rc = report.get("record_completeness") if isinstance(report.get("record_completeness"), Mapping) else None
        if report.get("verdict") == "exportable":
            if rc and rc.get("ready") is False:
                out["held"] += 1
            else:
                out["exportable"] += 1
        if bundle_mtime is not None and mtime < bundle_mtime:
            out["older_than_bundle"] += 1
        last = mtime if last is None else max(last, mtime)
    if last is not None:
        out["last_utc"] = datetime.fromtimestamp(last, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def _scientist(bundle: Mapping, consent: Mapping | None) -> dict:
    """The scientist's name: the one their consent was recorded under, else the name on their latest answer."""
    if consent:
        return {"name": (consent.get("given_by") or {}).get("name"), "basis": "consent"}
    for d in reversed(bundle.get("scientist_decisions") or ()):
        name = (d.get("decided_by") or {}).get("name")
        if isinstance(name, str) and name.strip():
            return {"name": name, "basis": "latest_answer"}
    return {"name": None, "basis": None}


def status(bundle_dir: Path, *, shown_as: str | None = None) -> dict:
    """Where the import in ``bundle_dir`` stands: ``{"facts": {...}, "lines": [...]}``. Reads only (module docstring).
    ``shown_as``: the bundle folder as the caller typed it, used in the next step's command (default: its name; an
    absolute path is never put in a message unless the caller gave it). Raises ``mutations.MutationRefused`` as
    ``mutations.load`` does (no bundle, unreadable)."""
    from . import bundle as B
    from . import mutations as M
    from . import questions as Q

    bundle_dir = Path(bundle_dir)
    bundle = M.load(bundle_dir)
    folder = (bundle.get("source_root") or {}).get("label") or bundle_dir.name
    stored = bundle.get("format_version")
    upgrade = B.needs_format_upgrade(bundle)
    consent = B.current_consent(bundle)
    who = _scientist(bundle, consent)

    runs = len(bundle.get("runs") or ())
    groups = bundle.get("record_groups") or ()
    live = Q.live_groups(bundle)
    live_ids = {g["group_id"] for g in live}
    by_status: dict[str, int] = {}
    for g in live:
        by_status[g.get("status") or "?"] = by_status.get(g.get("status") or "?", 0) + 1

    counts = None
    colours = None  # 1.22.0 (DEC-100): the record fields of each colour, as the records compose now
    to_review: set[str] = set()  # 1.21.0: the fills the records of confirmed groups carry, not yet reviewed
    cannot: dict[str, str] = {}
    pending_curve = unprocessed = 0
    try:
        reports: dict = {}
        payload = Q.consolidate(bundle, compositions_out=reports)
        counts = dict(payload["counts"])
        confirmed = {g["group_id"] for g in live if g.get("status") == B.STATE_SCIENTIST_CONFIRMED}
        to_review = {i for gid, rep in reports.items() if gid in confirmed
                     for e in (rep or {}).get("filled_by_rule") or () for i in e.get("from") or ()}
        if groups:
            not_measured = Q.not_a_measurement_groups(bundle, reports=reports or None)
            cannot = {gid: why for gid, why in Q.cannot_export_reasons(bundle, not_measured).items() if gid in live_ids}
        from . import records as R

        composed = [gid for gid in reports if gid in live_ids and gid not in cannot]
        colours = {**R.colour_counts(reports[gid] for gid in composed), "records": len(composed)}
        processed = {r.get("group_id") for r in bundle.get("processing_results") or () if not B.processing_not_applicable(r)}
        for g in live:
            if g["group_id"] in cannot:
                continue
            state = Q._curve(bundle, g["group_id"])["state"]
            if state in ("curve", "no_curve"):
                pending_curve += 1
            elif state == "none" and g["group_id"] not in processed:
                unprocessed += 1
    except Exception as exc:  # a bundle this build cannot consolidate: said, never hidden (as the Local Imports page)
        counts = {"unavailable": type(exc).__name__}

    results = bundle.get("processing_results") or ()
    by_state: dict[str, int] = {}
    gone = 0
    for r in results:
        if r.get("group_id") not in live_ids:
            gone += 1
            continue
        by_state[r.get("state") or "?"] = by_state.get(r.get("state") or "?", 0) + 1
    validation = _last_validation(bundle_dir, bundle, live_ids)
    facts = {
        "folder": folder,
        "format": {"stored": stored, "this_build": B.FORMAT_VERSION, "upgrade_on_next_write": bool(upgrade)},
        "scientist": who,
        "consent": ({"answer": consent.get("answer"), "by": (consent.get("given_by") or {}).get("name"),
                     "recorded_utc": consent.get("recorded_utc"), "agreement": consent.get("agreement")}
                    if consent else None),
        "runs": runs,
        "record_groups": {"live": len(live), "by_status": dict(sorted(by_status.items())),
                          "not_live": len(groups) - len(live), "cannot_export": len(cannot)},
        "questions": counts,
        # 1.18.0 (DEC-96): values a registered rule filled (not asked; the scientist reviews them at the end)
        # ...only those NOT asked anyway: a fill its record group cannot take is asked (questions.fills_asked), as the
        # questions list shows
        # 1.20.0 (round 3, I-1): the beamtime's environment convention, and the runs it now reaches beyond those it was
        # given for (never silent)
        "environment_convention": _environment_convention(bundle),
        "values_filled": sum(1 for o in [*(bundle.get("candidates") or ()), *(bundle.get("missing_values") or ())]
                             if o.get("value_state") in B.FILL_STATES) - len(Q.fills_asked(bundle)),
        # 1.22.0 (DEC-100): of those, the guesses (yellow): an inferred reading the skill filled
        "values_guessed": sum(1 for o in [*(bundle.get("candidates") or ()), *(bundle.get("missing_values") or ())]
                              if o.get("value_state") == B.STATE_GUESSED),
        # 1.22.0: one count per colour over the fields of the records as they compose now (green / yellow / red)
        "colours": colours,
        # 1.21.0 (DEC-99): the end review: fills the scientist confirmed by reviewing the built records, the reviewed
        # ones whose value, rule or evidence changed since (filled again), and whether records have been built
        "values_to_review": len(to_review),
        "values_reviewed": sum(1 for o in [*(bundle.get("candidates") or ()), *(bundle.get("missing_values") or ())]
                               if B.is_reviewed_fill(o)),
        "reviewed_changed_since": len(changed := B.review_changed_since(bundle)),
        "reviewed_changed": {"total": len(changed),
                             "filled_again": sum(1 for c in changed if c.get("now") in B.FILL_STATES),
                             "now_asked": sum(1 for c in changed if c.get("now") not in B.FILL_STATES)},
        "records_built": _records_built(bundle_dir),
        # 1.18.0: where the naming (counter) question stands: a file-name number read by its position is filled only
        # once it is settled (bundle.naming_check: not_grouped / counter_question_open / grouped_no_counter_question /
        # decided)
        "naming": B.naming_check(bundle),
        "processing": {"last_utc": _last_processing(bundle_dir), "live_results_by_state": dict(sorted(by_state.items())),
                       "results_of_groups_no_longer_live": gone, "groups_awaiting_a_curve_decision": pending_curve,
                       "groups_not_processed": unprocessed},
        "last_validation": validation,
    }
    facts["next"] = _next_step(facts, shown_as or bundle_dir.name)
    return {"facts": facts, "lines": _lines(facts)}


def _next_step(f: Mapping, shown_as: str) -> str:
    import shlex

    d = shlex.quote(shown_as)
    c = f["consent"]
    q = f["questions"] if isinstance(f["questions"], Mapping) else {}
    g = f["record_groups"]
    if not c:
        return (f"Ask the consent question (data-flow-and-consent.md), then record the answer: "
                f"`isaac bundle consent {d} --by \"<name>\"`.")
    if c.get("answer") != "given":
        return ("Consent is withdrawn: run nothing that prints names or values; give the scientist the commands to run "
                "themselves.")
    if not g["live"]:
        return f"Propose the record groups: `isaac bundle group {d}`."
    if q.get("blocking"):
        return f"Answer the blocking questions, a few at a time: `isaac bundle questions {d} --blocking-only --limit 10`."
    p = f["processing"]
    if p["groups_not_processed"]:
        return f"Process the groups that have no curve yet: `isaac process {d} --source <the beamtime folder>`."
    if p["groups_awaiting_a_curve_decision"]:
        return (f"Review the curves awaiting a decision: `isaac bundle list {d} processing-results --state needs_review`.")
    if g["by_status"].get("proposed"):
        return f"Confirm the proposed record groups the scientist agrees with: `isaac bundle list {d} groups`."
    if f.get("records_built") and f.get("values_to_review"):
        # 1.21.0 (DEC-99): the records are built and values a rule filled in them are not yet reviewed: the end review
        return (f"Review the {f['values_to_review']} value(s) filled from the evidence in the records with the scientist: "
                f"`isaac bundle review {d}`, then `--accept` on their yes (or their corrections with `decide`, and "
                "`build-records` again).")
    return (f"Compose and check the records: `isaac bundle build-records {d}`"
            + (f", review the values filled from the evidence (`isaac bundle review {d}`)"
               if f.get("values_filled") and not f.get("records_built") else "")
            + f", then `isaac bundle validate {d}`, then `isaac bundle export {d} --out <folder>`, then the final check "
            f"before sending (`isaac bundle upload <folder> --dry-run --bundle {d}`, which lists any guesses first).")


def _fill_lines(f: Mapping) -> list[str]:
    """1.21.0 (review 3, 4): ONE coherent account of the values a rule filled: how many wait for the end review in the
    built records, how many the review cannot reach yet (in no built record: their groups are not confirmed, or the
    records are not built), how many were reviewed, and what became of reviewed values that changed since."""
    out: list[str] = []
    filled, waiting, reviewed = f.get("values_filled") or 0, f.get("values_to_review") or 0, f.get("values_reviewed") or 0
    outside = max(filled - waiting, 0) if f.get("records_built") else filled
    head = []
    if f.get("records_built") and waiting:
        head.append(f"{waiting} in the built records wait for the end review (`bundle review`)")
    elif f.get("records_built") and reviewed:
        head.append("every one in the built records is reviewed")
    if outside:
        head.append(f"{outside} are in no built record yet (not in a confirmed record group"
                    + (")" if f.get("records_built") else ", or the records are not built)")
                    + ", so the review cannot reach them yet")
    if filled or reviewed:
        guessed = f.get("values_guessed") or 0
        lines = (f"Values a rule filled from the evidence (not asked; they go into the records as inferred, naming the "
                 f"rule): {filled} not yet reviewed" + (f" ({guessed} of them guesses)" if guessed else "")
                 + (f", {reviewed} confirmed in the end review" if reviewed else ""))
        out.append(lines + (": " + "; ".join(head) if head else "") + ".")
    ch = f.get("reviewed_changed") or {}
    if ch.get("total"):
        parts = [f"{ch['filled_again']} filled again, waiting for the next review" if ch.get("filled_again") else "",
                 f"{ch['now_asked']} now asked, since no rule fills them any more" if ch.get("now_asked") else ""]
        out.append(f"{ch['total']} reviewed value(s) changed since the review (their value, rule or evidence): "
                   + "; ".join(p for p in parts if p) + ".")
    return out


def _records_built(bundle_dir: Path) -> bool:
    """Whether ``build-records`` has written its drafts index (``drafts/index.json``)."""
    from . import records as R

    return R.contained_file(bundle_dir, f"{R.DRAFTS_DIR}/index.json") is not None


def _environment_convention(bundle: Mapping) -> dict | None:
    from . import bundle as B

    d = B.environment_convention_decision(bundle)
    if d is None:
        return None
    given_for = d.get(B.ENVIRONMENT_CONVENTION_COVERS_KEY)
    more = B.environment_convention_extension(bundle)
    from . import questions as Q

    return {"value": d.get("value"), "decision_id": d.get("decision_id"), "question_id": Q.ENV_CONVENTION_QUESTION_ID,
            "given_for": len(given_for) if isinstance(given_for, list) else None, "more_since_the_answer": len(more)}


def _lines(f: Mapping) -> list[str]:
    fmt = f["format"]
    lines = [f"Beamtime: {f['folder']} (bundle format {fmt['stored']}"
             + (f"; the next answer upgrades it to {fmt['this_build']}, looking writes nothing)" if fmt["upgrade_on_next_write"]
                else ")")]
    c = f["consent"]
    who = f["scientist"]["name"]
    if c and c.get("answer") == "given":
        lines.append(f"Scientist: {c['by']}. Consent to Claude reading these files: given {_day(c['recorded_utc'])} "
                     f"({c.get('agreement')}); do not ask again.")
    elif c:
        lines.append(f"Scientist: {c['by']}. Consent to Claude reading these files: WITHDRAWN {_day(c['recorded_utc'])}.")
    else:
        lines.append(f"Scientist: {who + ' (the name on the latest answer)' if who else 'not recorded'}. "
                     "Consent to Claude reading these files: not recorded; ask once.")
    g = f["record_groups"]
    st = ", ".join(f"{n} {s.replace('scientist_', '')}" for s, n in g["by_status"].items())
    lines.append(f"Runs: {f['runs']}, in {g['live']} record group(s)" + (f" ({st})" if st else "")
                 + (f"; {g['cannot_export']} cannot become a record as they stand" if g["cannot_export"] else "") + ".")
    v = f["last_validation"]
    if v["reports"]:
        lines.append(f"Records: {v['exportable']} exportable at the last validate ({_day(v['last_utc'])})"
                     + (f", {v['held']} held by the completeness check" if v["held"] else "")
                     + (f"; {v['older_than_bundle']} report(s) predate later answers, validate again" if v["older_than_bundle"] else "")
                     + ".")
    else:
        lines.append("Records: none validated yet.")
    q = f["questions"]
    if isinstance(q, Mapping) and "unavailable" not in q:
        lines.append(f"Open questions: {q.get('blocking', 0)} blocking, "
                     f"{q.get('conflicts_affecting_a_record', 0)} disagreement(s) affecting a record, "
                     f"{q.get('optional', 0)} optional.")
    else:
        lines.append(f"Open questions: not counted ({(q or {}).get('unavailable')}); `isaac bundle check` says why.")
    co = f.get("colours")
    if co and co.get("records"):
        # 1.22.0 (DEC-100): ONE line, one count per colour (bundle.value_colour)
        lines.append(f"Values in the {co['records']} record(s) as they stand: {co['green']} green (read from the files or "
                     f"confirmed by you), {co['yellow']} yellow (my guesses or deductions, not yet confirmed), "
                     f"{co['red']} red (needed and not known yet).")
    lines.extend(_fill_lines(f))
    ec = f.get("environment_convention")
    if ec:
        lines.append(f"Environment of the measurements held at a potential: {ec['value']} ({ec['decision_id']}"
                     + (f", given for {ec['given_for']} measurement(s)" if ec.get("given_for") is not None else "") + ")"
                     + (f"; {ec['more_since_the_answer']} more measurement(s) now take it, which qualified after the "
                        "answer: the convention question is open again (optional; the question site has no card for "
                        f"it) — confirm it for them with `isaac bundle decide <bundle_dir> --question {ec['question_id']} "
                        f"--decision set_environment_convention --value {ec['value']} --by \"<your name>\"`, or "
                        "--value per_run" if ec.get("more_since_the_answer") else "") + ".")
    p = f["processing"]
    if p["live_results_by_state"] or p["last_utc"]:
        states = ", ".join(f"{n} {s.replace('_', ' ')}" for s, n in p["live_results_by_state"].items())
        lines.append(f"Processing: last run {_day(p['last_utc']) or 'at an unknown time'}"
                     + (f"; {states}" if states else "; no result for a live group") + ".")
    else:
        lines.append("Processing: not run yet.")
    lines.append(f"Next: {f['next']}")
    return lines
