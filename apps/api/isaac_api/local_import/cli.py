"""``isaac import`` and ``isaac bundle`` — the local-first CLI (slice LOCAL-1).

Runs on a scientist's own machine with NO server and NO database. The reading is
:func:`isaac_api.historical_import.read_local_archive` — the hosted site's own
reconstruction chain, not a second parser — and the output is an ISAAC Local Import
Bundle (``docs/local-import-bundle-contract.md``), which is NOT an official record.

COMMANDS
========

``isaac import <folder-or-zip> --out <dir> [--profile auto|<id>] [--force] [--record-local-root]``
    Read the folder or ZIP and write the bundle directory:
    ``bundle.json`` (the full, validated v1 bundle), ``summary.md`` (compact,
    scientist-readable), ``runs.json``, ``conflicts.json``, ``questions.json``,
    ``unread_files.json`` and ``reading.full.json`` (the raw engine state, for lookup).
    Refuses a non-empty ``--out`` unless ``--force`` (which overwrites ONLY those seven
    files and deletes nothing). Refuses an ``--out`` inside the folder being read.
    The local path is never written into the bundle unless ``--record-local-root``.

``isaac bundle list <dir> runs|conflicts|candidates|questions|unread|groups|merge-candidates|processed-outputs|processing-results [--limit N] [--offset M] [--state S]``
    A bounded page as JSON, with ``total`` and how many were omitted before and after.
    Never truncates silently. ``processing-results``: one compact row per result (id, group, verdict,
    applicability, key QC flags and metrics, plot path, Athena agreement, state); ``--state`` filters it
    by state as it filters ``candidates`` by value_state. ``groups`` and ``runs`` print one row per line: a
    ``groups`` row carries up to three member file stems (``files``, ``files_more``), ``scans``, ``reader`` and,
    when the group can never export as it stands, ``cannot_export_reason`` (``no_scans`` or
    ``processing_not_applicable:<code>``, counted over the whole list in ``cannot_export``); a ``runs`` row
    carries the run's file ``stem`` (and ``path`` when two runs share a stem).

``isaac bundle show <dir> run|conflict|candidate|source|question <id>``
    One object as JSON. ``processing-result <result_id>``: one processing result, compact (QC, flags,
    steps' outcomes, Athena comparison and every Athena version with its id; lists are counted, not printed).

``isaac bundle check <dir>``
    Re-validate the bundle against v1: schema, bounds, references, and the state rule.

``isaac bundle propose-terms <dir> [--out FILE] [--force]``
    Values outside a fixed list (the vendored schema's enum or the portal vocabulary
    snapshot's list), grouped by field with counts and file/locator citations, and one
    draft per term in the website's portal-payload format. Sent nowhere; each draft needs
    a description written by a person. Records an exposure for every parser value shown.

LOCAL-2 (``docs/local-import-bundle-contract.md`` §9-§12): ``annotate`` (AI reading,
never above needs_review; ``--blind`` honoured only before exposure), ``decide``
(identity ``local_unverified``; ``--orcid`` is a claimed credit value), ``crosscheck-plan``,
``excerpt``, ``reveal`` (records an exposure), ``build-records``, ``validate``,
``export`` and ``upload --dry-run``. Every mutation re-derives, re-validates and writes
atomically under a lock, or writes nothing.

EXIT CODES
==========

====  ===========================================================================
 0    success (``check``: the bundle meets v1)
 1    ``check``: the bundle does NOT meet v1 (errors printed)
 2    usage error (bad arguments, unknown profile)
 3    input refused: not found, not a folder or ZIP, a symbolic link, unreadable
 4    output refused: ``--out`` not empty (no ``--force``), is a file, or is inside
      the source folder
 5    bounds exceeded, or the built bundle failed its own validation — nothing written
 6    not found: no bundle at ``<dir>``, or no object with that id
 1    (also) ``validate``/``export``: some draft is not exportable / was not exported. ``export`` exits 1
      even when it WROTE some records: its reply's ``outcome`` says "Wrote N record(s), refused M group(s)"
====  ===========================================================================

NOTHING IS EXECUTED. Macros and scripts in the archive are read as text by the
``bl15`` readers; no source is run, imported, or opened by any other program.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_INPUT_REFUSED = 3
EXIT_OUTPUT_REFUSED = 4
EXIT_BOUNDS = 5
EXIT_NOT_FOUND = 6

#: The files ``isaac import`` writes, and the only ones ``--force`` overwrites.
BUNDLE_FILES = (
    "bundle.json",
    "summary.md",
    "runs.json",
    "conflicts.json",
    "questions.json",
    "unread_files.json",
    "reading.full.json",
)

LIST_KINDS = ("runs", "conflicts", "candidates", "questions", "unread", "groups", "merge-candidates", "processed-outputs",
              "processing-results")
SHOW_KINDS = ("run", "conflict", "candidate", "source", "question", "group", "merge-candidate", "processed-output",
              "processing-result")
DEFAULT_LIMIT = 20
MAX_LIMIT = 200
#: The target size of summary.md (bytes). Sections are windowed to stay near it.
SUMMARY_TARGET_BYTES = 6_000
_SUMMARY_RUN_ROWS = 25
_SUMMARY_LIST_ROWS = 10
_LOCAL_SOURCE_ID = "local-source"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _isaac_commit() -> str | None:
    """The checkout's HEAD commit, read from ``.git`` files. ``None`` if not derivable.

    No subprocess: reading three small files is enough, and a missing or unusual
    ``.git`` simply yields ``None`` rather than a guess.
    """
    try:
        from .. import workspace as ws

        git = ws.REPO_ROOT / ".git"
        if git.is_file():  # a worktree: "gitdir: <path>"
            text = git.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None
            git = (git.parent / text.split(":", 1)[1].strip()).resolve()
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            sha = head
        else:
            ref = head.split(":", 1)[1].strip()
            common = git
            commondir = git / "commondir"
            if commondir.is_file():
                common = (git / commondir.read_text(encoding="utf-8").strip()).resolve()
            sha = None
            for base in (git, common):
                candidate = base / ref
                if candidate.is_file():
                    sha = candidate.read_text(encoding="utf-8").strip()
                    break
            if sha is None:
                packed = common / "packed-refs"
                if packed.is_file():
                    for line in packed.read_text(encoding="utf-8").splitlines():
                        parts = line.strip().split(" ")
                        if len(parts) == 2 and parts[1] == ref:
                            sha = parts[0]
                            break
        if sha and len(sha) >= 7 and all(ch in "0123456789abcdef" for ch in sha):
            return sha
    except (OSError, ValueError):
        return None
    return None


def _rules_for_profile(profile: str) -> tuple[list, str] | None:
    """``(rules, recorded request)`` for ``--profile``; ``None`` for an unknown id."""
    from ..bl15 import profiles as prof

    if profile == "auto":
        return [], "auto"
    registered = prof.profile_for(profile)
    if registered is None:
        return None
    if registered.profile_id == prof.DEFAULT_PROFILE_ID:
        # Explicitly naming the build default reads exactly as `auto` does; no binding
        # is minted, so the reading is byte-identical to the server's default.
        return [], f"{registered.profile_id} (the build default; read as auto)"
    from .. import convention_rules as cr

    rule = cr.new_rule(
        rule_id="local-cli-profile",
        kind=cr.KIND_PROFILE_BINDING,
        scope=cr.SCOPE_IMPORT,
        body={"profile_id": registered.profile_id, "profile_version": registered.profile_version},
        selector={},
        confirmed_utc=_now_utc(),
        existing=[],
        import_id="local",
    )
    return [rule], f"{registered.profile_id} v{registered.profile_version} (requested on the command line)"


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        # mkstemp creates 0600; a bundle is an ordinary readable file (review minor).
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


# --- summary.md -------------------------------------------------------------------------


def _clip(text: Any, n: int = 80) -> str:
    s = "" if text is None else str(text)
    s = s.replace("|", "/").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def render_summary(bundle: Mapping) -> str:
    """The compact, scientist-readable summary. Windowed sections, every window counted."""
    from . import bundle as B

    counts = bundle["counts"]
    root = bundle["source_root"]
    readiness = bundle["readiness"]
    lines: list[str] = []
    add = lines.append
    add(f"# ISAAC import summary: {_clip(root['label'], 60)}")
    add("")
    add("> **This is not a validated official ISAAC record.** It is what the deterministic")
    add("> readers extracted from your files, with the evidence for each value. Nothing")
    add("> here is confirmed by a scientist, and nothing has been checked against the")
    add("> official ISAAC schema.")
    add("")
    add(
        f"Bundle `{bundle['bundle_id']}` · {bundle['created_utc']} · "
        f"{bundle['format']} {bundle['format_version']} · {root['kind']}"
    )
    for u in bundle.get("format_upgrades") or ():
        add("")
        add(f"> **Bundle {u['statement']}** (by a {u['derived_by_format_version']} build, {u['upgraded_utc']}).")
    clock = B.clock_zone_status(bundle)
    if clock is not None:
        add("")
        if clock["zone"] is None:
            add(f"Instrument clock time zone: **not stated** — {clock['start_time_candidates']} scan start time(s) are "
                "local clock times with no zone and stay out of the record until a scientist states the zone "
                "(`--target experiment --decision set_clock_time_zone`). None is assumed.")
        else:
            add(f"Instrument clock time zone: **{clock['zone']}** (decision {clock['zone_decision_id']}), applied to "
                f"{clock['start_time_candidates']} scan start time(s).")
        if clock["confirmations_no_longer_counting"]:
            add(f"> **{clock['confirmations_no_longer_counting']} start-time confirmation(s) no longer count**: the clock "
                "time zone changed after they were confirmed. Confirm again: "
                + ", ".join(clock["candidate_ids_to_confirm_again"][:20]) + ".")
    add("")
    add("## Counts")
    add("")
    unread = bundle["unread_files"]
    athena = [u for u in unread if _is_athena_project(u)]
    add(
        f"- Files: {counts['sources']} inventoried, {counts['unread_files']} unread or refused"
        + (f" (walk stopped: {root['truncated_reason']})" if root.get("truncated_reason") else "")
    )
    if athena:
        add(f"  - {_athena_read_by_process(len(athena))} (the import has no reader for them, so they stay in the unread count)")
    add(
        f"- Runs: {counts['runs']} ({counts['runs_sharing_a_legacy_number']} share a legacy "
        f"number with another run; all are kept)"
    )
    pos = bundle.get("processed_outputs") or []
    if pos:
        n_files = sum(len(p["files"]) for p in pos)
        linked = sum(1 for p in pos if p["proposed_links"])
        assumed = sum(1 for p in pos for link in p["proposed_links"] if link.get("assumption"))
        add(
            f"- {n_files} processed files from the scientists (Athena/Demeter), kept as reference "
            f"results, not records ({len(pos)} output(s) by name; {linked} with a proposed link to a run "
            f"by the name rule (same name, or same name plus a selection of that run's own scans), "
            f"{len(pos) - linked} unlinked"
            + (f"; {assumed} of them assume scans are numbered 1..N because the run states no scan index" if assumed else "")
            + "). Not counted as runs; no question is asked about them."
        )
    add(
        f"- Values: {counts['candidates']} — {counts['candidate_extracted']} extracted, "
        f"{counts['needs_review']} need review, {counts['conflicting_candidates']} conflicting, "
        f"{counts['unmapped']} unmapped (kept as evidence)"
    )
    add(
        f"- Conflicts: {counts['conflicts']}{_conflict_breakdown(bundle)} · Missing values: {counts['missing_values']} "
        f"(nothing defaulted) · Questions: {counts['questions']}"
    )
    add(f"- People named in the sources: {counts['contributors']} (evidence, not the naming profile)")
    groups = bundle.get("record_groups") or []
    if groups or bundle.get("processing_results"):
        # live groups are counted; a merged, rejected or split group is decision history, said apart
        live = [g for g in groups if g["status"] in B.LIVE_GROUP_STATUSES]
        history: dict[str, int] = {}
        for g in groups:
            if g["status"] not in B.LIVE_GROUP_STATUSES:
                history[g["status"]] = history.get(g["status"], 0) + 1
        add(
            f"- Record groups: {len(live)} ({sum(1 for g in live if g['status'] == 'scientist_confirmed')} "
            f"confirmed)"
            + (f" and {len(groups) - len(live)} kept as decision history ("
               + ", ".join(f"{n} {k}" for k, n in sorted(history.items())) + ")" if history else "")
            + f" · processing results: {len(bundle.get('processing_results') or [])}"
        )
    if bundle.get("processing_results"):
        # Counts only. A group the protocol does not apply to is reported apart from the QC
        # verdicts: it was not judged, so it is never counted as a fail.
        from .processing.run import summarize

        for line in summarize(bundle["processing_results"])["lines"]:
            add(f"- Processing: {line}")
    add(
        "- This summary shows no parser value except in conflicts, so a blind cross-check "
        "(`isaac bundle crosscheck-plan`) is still possible after reading it."
    )
    add("")

    samples = bundle["samples"]
    if samples:
        add("## Run groups")
        add("")
        for s in samples[:_SUMMARY_LIST_ROWS]:
            # COUNTS ONLY, never the readings themselves: summary.md is read before any
            # blind cross-check, so it must not show a non-conflicting parser value.
            # Runs whose file names carry no group token are in no file-name group: said so, never "group None".
            add(
                (f"- group {s['group_token']}: " if s["group_token"] is not None else "- not in a file-name group: ")
                + f"{len(s['run_ids'])} runs "
                f"({', '.join(s['run_ids'][:6])}{'…' if len(s['run_ids']) > 6 else ''}); "
                f"{len(s['sample_name_readings'])} distinct sample-name reading(s)"
            )
        if len(samples) > _SUMMARY_LIST_ROWS:
            add(f"- … {len(samples) - _SUMMARY_LIST_ROWS} more groups")
        add("")

    runs = bundle["runs"]
    add("## Runs")
    add("")
    add("| Run | Legacy | Scans | Conflicts | Flag |")
    add("|---|---|---|---|---|")
    for r in runs[:_SUMMARY_RUN_ROWS]:
        flag = "shares legacy no." if r["legacy_number_shared"] else ""
        if not r["run_candidate"]:
            flag = (flag + "; " if flag else "") + "not a run (" + _clip(r["source_type"], 20) + ")"
        add(
            f"| {r['run_id']} | {r['legacy_number'] if r['legacy_number'] is not None else '—'} "
            f"| {r['scan_count']} | {len(r['conflict_ids'])} | {flag} |"
        )
    if len(runs) > _SUMMARY_RUN_ROWS:
        add(f"\n{len(runs) - _SUMMARY_RUN_ROWS} more runs: `isaac bundle list <dir> runs --offset {_SUMMARY_RUN_ROWS}`")
    add("")

    add("## Needs review")
    add("")
    conflicts = bundle["conflicts"]
    for cf in conflicts[:_SUMMARY_LIST_ROWS]:
        where = ",".join(cf["run_ids"]) or "beamtime"
        add(f"- {cf['conflict_id']} ({where}): {_clip(cf['kind'], 40)} — {len(cf['readings'])} readings kept")
    if len(conflicts) > _SUMMARY_LIST_ROWS:
        add(f"- … {len(conflicts) - _SUMMARY_LIST_ROWS} more conflicts: `isaac bundle list <dir> conflicts`")
    by_target: dict[str, int] = {}
    for c in bundle["candidates"]:
        if c["value_state"] == "needs_review" and c["target_field_path"]:
            by_target[c["target_field_path"]] = by_target.get(c["target_field_path"], 0) + 1
    ordered = sorted(by_target.items(), key=lambda kv: (-kv[1], kv[0]))
    for path, n in ordered[:_SUMMARY_LIST_ROWS]:
        add(f"- `{path}`: {n} value(s) need review")
    if len(ordered) > _SUMMARY_LIST_ROWS:
        add(f"- … {len(ordered) - _SUMMARY_LIST_ROWS} more fields: `isaac bundle list <dir> questions`")
    add("")

    add("## Unread files")
    add("")
    if not unread:
        add("Every inventoried file had a reader.")
    if athena:
        # an Athena project is not unread: `isaac process` reads it (the import has no reader for it)
        add(f"- {_athena_read_by_process(len(athena))} (`isaac bundle list <dir> unread` shows each with its `read_by`).")
    others = [u for u in unread if not _is_athena_project(u)]
    for u in others[:_SUMMARY_LIST_ROWS]:
        add(f"- {_clip(u['relative_path'] or '(name withheld)', 60)} — {u['reason_code']}")
    if len(others) > _SUMMARY_LIST_ROWS:
        add(f"- … {len(others) - _SUMMARY_LIST_ROWS} more: `isaac bundle list <dir> unread`")
    add("")

    add("## Readiness")
    add("")
    add(
        f"Stage: {readiness['stage']}. Values eligible for an official record: "
        f"{readiness['eligible_value_count']} (only scientist-confirmed values can be). "
        "Official record ready: no."
    )
    add("")
    add(readiness["next_step"])
    add("")
    return "\n".join(lines)


def _conflict_breakdown(bundle: Mapping) -> str:
    """Why the conflict count differs from the count of values in the ``conflicting`` state, or ``""`` when it
    does not: a conflict about a value that is still ``needs_review`` (or decided since), or one about files
    rather than one value (the same file name in two folders), is a conflict without a conflicting value."""
    cand = {c["candidate_id"]: c for c in bundle.get("candidates") or ()}
    on_state: dict[str, int] = {}
    about_no_value = 0
    for cf in bundle.get("conflicts") or ():
        c = cand.get(cf.get("candidate_id") or "")
        if c is None:
            about_no_value += 1
        else:
            on_state[c["value_state"]] = on_state.get(c["value_state"], 0) + 1
    conflicting = on_state.pop("conflicting", 0)
    if not on_state and not about_no_value:
        return ""
    parts = [f"{conflicting} on the {bundle['counts']['conflicting_candidates']} conflicting value(s)"]
    said = {"needs_review": "that need review (not conflicting)", "scientist_confirmed": "a scientist has decided",
            "rejected": "a scientist rejected"}
    parts += [f"{n} on value(s) {said.get(state, 'in state ' + state)}" for state, n in sorted(on_state.items())]
    if about_no_value:
        parts.append(f"{about_no_value} about files, not one value")
    return " (" + "; ".join(parts) + ")"


def _consolidated(bundle: Mapping) -> dict:
    from . import questions as Q

    return Q.consolidate(bundle)


def section_payloads(bundle: Mapping) -> dict[str, bytes]:
    """The derived files regenerated from ``bundle.json`` on import and on every mutation."""
    return {
        "summary.md": render_summary(bundle).encode("utf-8"),
        "runs.json": _json_bytes({"total": len(bundle["runs"]), "runs": bundle["runs"]}),
        "conflicts.json": _json_bytes({"total": len(bundle["conflicts"]), "conflicts": bundle["conflicts"]}),
        # v2 (LOCAL-4): CONSOLIDATED — asked once, at the right scope, blocking first. The
        # fine-grained v1 list stays in bundle.json, where decisions key on its targets.
        "questions.json": _json_bytes(_consolidated(bundle)),
        "unread_files.json": _json_bytes(
            {"total": len(bundle["unread_files"]), "unread_files": bundle["unread_files"]}
        ),
    }


# --- import ----------------------------------------------------------------------------


def cmd_import(args) -> int:
    from .. import historical_import as hist
    from . import bundle as B

    source = Path(args.path).expanduser()
    out = Path(args.out).expanduser()

    resolved = _rules_for_profile(args.profile)
    if resolved is None:
        from ..bl15 import profiles as prof

        _err(f"Unknown naming profile {args.profile!r}. Registered: auto, {', '.join(sorted(prof.PROFILES))}.")
        return EXIT_USAGE
    rules, profile_request = resolved

    if out.exists() and not out.is_dir():
        _err("--out names a file, not a directory. Nothing was written.")
        return EXIT_OUTPUT_REFUSED
    if out.is_dir() and any(out.iterdir()) and not args.force:
        _err("--out is not empty. Pass --force to overwrite the bundle files in it. Nothing was written.")
        return EXIT_OUTPUT_REFUSED
    if source.is_dir() and not source.is_symlink() and _is_within(out, source):
        _err(
            "--out is inside the folder being read, so the next import would read the bundle "
            "as a source. Choose a directory outside it. Nothing was written."
        )
        return EXIT_OUTPUT_REFUSED

    evidence: dict = {}
    try:
        reading, candidates = hist.read_local_archive(
            source, source_id=_LOCAL_SOURCE_ID, rules=rules, evidence_sink=evidence
        )
    except hist.UnsupportedImport as refusal:
        _err(f"Refused ({refusal.error}): {refusal.message}")
        return EXIT_INPUT_REFUSED
    inventory = reading.inventory or {}
    root_refusals = [r for r in inventory.get("refused") or () if not r.get("archive_path")]
    if not reading.manifest and root_refusals:
        _err(f"Refused ({root_refusals[0].get('reason')}): {root_refusals[0].get('detail')}")
        return EXIT_INPUT_REFUSED

    from .. import __version__

    # GENERIC READERS (LOCAL-3): claim the files the engine did not read. A folder only —
    # `collect_all_generic` walks a directory; a ZIP's members stay where the engine put them.
    generic = None
    if source.is_dir():
        from .readers import collect_all_generic

        engine_read = [
            row["archive_path"]
            for row in reading.reading
            if row.get("parser_id") and row.get("refused_reason") is None
        ]
        try:
            generic = collect_all_generic(source, skip=engine_read)
        except ValueError as exc:
            _err(f"Refused (generic readers): {exc}")
            return EXIT_INPUT_REFUSED

    try:
        bundle = B.build_bundle(
            reading,
            candidates,
            evidence_by_source=evidence,
            source_kind="folder" if source.is_dir() else "zip",
            created_utc=_now_utc(),
            local_root_hint=str(source.resolve()) if args.record_local_root else None,
            profile_request=profile_request,
            isaac_commit=_isaac_commit(),
            tool_version=__version__,
            generic=generic,
        )
    except B.BundleBoundsExceeded as exc:
        _err(f"Bounds exceeded: {exc}")
        return EXIT_BOUNDS
    errors = B.validate_bundle(bundle) + [
        f"json: {p} is not a finite number (NaN or infinity is not standard JSON)" for p in B.new_non_finite_paths(bundle, None)]
    if errors:
        _err("The built bundle failed its own v1 validation; nothing was written:")
        for e in errors[:20]:
            _err(f"  - {e}")
        return EXIT_BOUNDS

    try:
        full = B.full_reading(reading, candidates)
    except B.BundleBoundsExceeded as exc:
        _err(f"Bounds exceeded: {exc}")
        return EXIT_BOUNDS
    payloads = {
        "bundle.json": B.encode(bundle),
        **section_payloads(bundle),
        "reading.full.json": B.encode(full),
    }
    out.mkdir(parents=True, exist_ok=True)
    # STAGE EVERY FILE FIRST, then move each into place: a failure while writing leaves
    # --out exactly as it was, and nothing else in --out is ever touched.
    staging = Path(tempfile.mkdtemp(prefix=".isaac-bundle-", dir=str(out.parent)))
    try:
        for name in BUNDLE_FILES:
            _atomic_write(staging / name, payloads[name])
        for name in BUNDLE_FILES:
            os.replace(staging / name, out / name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    c = bundle["counts"]
    print(f"Wrote an ISAAC Local Import Bundle to {out}")
    print(
        f"  {c['sources']} files, {c['runs']} runs, {c['candidates']} values "
        f"({c['conflicts']} conflicts{_conflict_breakdown(bundle)}, {c['needs_review']} need review, "
        f"{c['missing_values']} missing, {c['unread_files']} unread files)"
    )
    if n_athena := sum(1 for u in bundle["unread_files"] if _is_athena_project(u)):
        print(f"  {_athena_read_by_process(n_athena)}")
    if c.get("processed_output_files"):
        print(
            f"  {c['processed_output_files']} processed files from the scientists (Athena/Demeter), "
            "kept as reference results, not records"
        )
    print("  This is NOT a validated official ISAAC record. Start with summary.md.")
    return EXIT_OK


# --- bundle list / show / check -------------------------------------------------------


def _load(dir_arg: str):
    from . import bundle as B

    path = B.bundle_path(Path(dir_arg).expanduser())
    if not path.is_file():
        _err(f"No bundle.json at {dir_arg}.")
        return None, EXIT_NOT_FOUND
    try:
        return B.load_bundle(path), EXIT_OK
    except B.BundleInvalid as exc:
        _err(f"Unreadable bundle: {exc}")
        return None, EXIT_INVALID


def _short(value: Any, n: int = 200) -> Any:
    if isinstance(value, str) and len(value) > n:
        return value[: n - 1] + "…"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
        return value if len(text) <= n else text[: n - 1] + "…"
    return value


def _row(kind: str, obj: Mapping, group_status: Mapping | None = None) -> dict:
    if kind == "runs":
        return {
            "run_id": obj["run_id"],
            # the FILE STEM, the name a scientist recognises (a label reorders and drops tokens, and two runs can
            # share one); `annotate --from-readings` takes it, or the run id, to name a run
            "stem": obj.get("stem"),
            "label": obj["label"],
            "legacy_number": obj["legacy_number"],
            "legacy_number_shared": obj["legacy_number_shared"],
            "run_candidate": obj["run_candidate"],
            "scan_count": obj["scan_count"],
            "candidates": len(obj["candidate_ids"]),
            "conflicts": len(obj["conflict_ids"]),
        }
    if kind == "conflicts":
        return {
            "conflict_id": obj["conflict_id"],
            "kind": obj["kind"],
            "subject": _short(obj["subject"], 120),
            "run_ids": obj["run_ids"],
            "readings": len(obj["readings"]),
            "value_state": obj["value_state"],
        }
    if kind == "candidates":
        return {
            "candidate_id": obj["candidate_id"],
            "run_id": obj["run_id"],
            "statement_key": obj["statement_key"],
            "target_field_path": obj["target_field_path"],
            "value_state": obj["value_state"],
            "value": _short(obj["value"]),
            "evidence_total": obj["evidence_total"],
        }
    if kind == "groups":
        # PLAIN FIELDS ONLY — no basis values, so no exposure; `show group` prints those.
        return {
            "group_id": obj["group_id"],
            "status": obj["status"],
            "member_run_ids": list(obj.get("member_run_ids") or [])[:50],
            "members": len(obj["member_run_keys"]),
            "role": obj.get("role"),
            "split_reasons": len(obj.get("split_reasons") or []),
            "conditions_named": sorted((obj.get("basis") or {}).get("conditions") or {})[:20],
        }
    if kind == "merge-candidates":
        # the groups' run labels (file names, no parser value) are added by cmd_bundle_list
        return {
            "merge_candidate_id": obj.get("merge_candidate_id") or obj.get("id"),
            "status": obj.get("status"),
            "group_ids": list(obj.get("group_ids") or [])[:50],
            "reason_code": _mc_reason_code(obj),
            "caution": [c.get("statement") for c in obj.get("caution") or () if isinstance(c, Mapping)],
        }
    if kind == "processed-outputs":
        # what the files state about themselves, and the proposed link; no parser value
        return {
            "processed_output_id": obj["processed_output_id"],
            "label": obj["label"],
            "files": len(obj["files"]),
            "processed_by": sorted({s["literal"] for s in obj["states"]["processed_by"] if s["literal"]})[:10],
            "proposed_link": (obj["proposed_links"] or [None])[0],
            "link_note": (obj["link_note"] or {}).get("code"),
        }
    if kind == "processing-results":
        # COMPACT: what a reviewer needs to pick and decide a result; the full result (inputs, steps,
        # every metric) stays in processing/processing_results.json and `bundle.json`
        from . import bundle as B

        app = obj.get("applicability") or {}
        qc = obj.get("qc") or {}
        failure = obj.get("failure") or {}
        files = (obj.get("outputs") or {}).get("files") or ()
        comparison = obj.get("comparison") or {}
        channel = obj.get("channel_choice") if isinstance(obj.get("channel_choice"), Mapping) else {}
        return {
            "result_id": B.processing_id(obj),
            "group_id": obj.get("group_id"),
            "group_status": (group_status or {}).get(obj.get("group_id")),
            "source": obj.get("source"),
            "state": obj.get("state"),
            "verdict": qc.get("verdict"),
            "qc_reasons": list(qc.get("reasons") or [])[:10],
            "applicability": f"not_applicable:{app.get('reason_code')}" if B.processing_not_applicable(obj) else "applies",
            "failure": (f"{failure.get('code')}: {_short(failure.get('detail'), 120)}" if failure.get("detail") else failure.get("code")) or None,
            "channel": _short(channel.get("signal_name") or channel.get("mode"), 120) if channel else None,
            "flags": [f for f in obj.get("review_flags") or () if f not in _EVERY_RESULT_FLAGS][:20],
            "metrics": {k: (qc.get("metrics") or {}).get(k) for k in _RESULT_METRICS if k in (qc.get("metrics") or {})},
            "output_files": len(files),
            "plot": next((f.get("relative_path") for f in files if f.get("role") == "plot"), None),
            "athena_agreement": comparison.get("verdict"),
            "athena_versions": len(obj.get("athena_versions") or ()),
            # the ids `decide --decision select_athena_version --value <version_id>` takes, with what names them
            **({"athena_version_choices": [_athena_version_brief(v) for v in obj["athena_versions"]]} if obj.get("athena_versions") else {}),
        }
    if kind == "questions":
        return {
            "question_id": obj["question_id"],
            "kind": obj["kind"],
            "target": obj["target"],
            "run_id": obj["run_id"],
            "prompt": _short(obj["prompt"], 240),
        }
    row = {
        "relative_path": obj["relative_path"],
        "source_id": obj["source_id"],
        "source_type": obj["source_type"],
        "reason_code": obj["reason_code"],
    }
    later = next((how for suffix, how in READ_LATER_BY_SUFFIX.items()
                  if str(obj.get("relative_path") or "").lower().endswith(suffix)), None)
    if later:
        row["read_by"] = later
    return row


#: How many member file names a ``bundle list <dir> groups`` row shows (the rest are counted).
GROUP_ROW_FILES = 3
#: ``cannot_export_reason`` codes on a ``bundle list <dir> groups`` row, said once on the page.
CANNOT_EXPORT_NOTE = ("Such a group can never become an exportable record as it stands; leave it out of a bulk confirm. "
                      "no_scans: none of its runs lists a scan. processing_not_applicable:<code>: no ISAAC processing "
                      "protocol covers this data yet.")


def group_list_extras(bundle: Mapping) -> dict[str, dict]:
    """``{group_id: fields}`` a ``bundle list <dir> groups`` row adds: a few member FILE NAMES (the run's stem,
    the name a scientist recognises), the scan count, the reader (the runs' source type) and, when known,
    ``cannot_export_reason``. File names and counts only — no parser value, so no exposure."""
    from . import bundle as B

    runs = {r["run_key"]: r for r in bundle.get("runs") or ()}
    blocked = B.processing_blocked_groups(bundle)
    out: dict[str, dict] = {}
    for g in bundle.get("record_groups") or ():
        members = [runs[k] for k in g.get("member_run_keys") or () if k in runs]
        stems = [str(r.get("stem") or r["run_id"]) for r in members]
        scans = sum(int(r.get("scan_count") or 0) for r in members)
        row: dict[str, Any] = {"files": stems[:GROUP_ROW_FILES]}
        if len(stems) > GROUP_ROW_FILES:
            row["files_more"] = len(stems) - GROUP_ROW_FILES
        row["scans"] = scans
        row["reader"] = ", ".join(dict.fromkeys(str(r.get("source_type")) for r in members)) or None
        na = blocked.get(g["group_id"])
        if na is not None:
            row["cannot_export_reason"] = f"processing_not_applicable:{(na.get('applicability') or {}).get('reason_code')}"
        elif members and scans == 0:
            row["cannot_export_reason"] = "no_scans"
        out[g["group_id"]] = row
    return out


def _is_athena_project(unread_row: Mapping) -> bool:
    """An unread row whose file a LATER command reads (an Athena ``.prj``: see :data:`READ_LATER_BY_SUFFIX`)."""
    return str(unread_row.get("relative_path") or "").lower().endswith(tuple(READ_LATER_BY_SUFFIX))


def _athena_read_by_process(n: int) -> str:
    """What the summary and the import output say about Athena projects (the stored unread_files keep them)."""
    return f"{n} Athena project{'s are' if n != 1 else ' is'} read by `isaac process`, not at import"


def _mc_reason_code(obj: Mapping) -> str | None:
    """A merge candidate's ``reason_code`` (stored since 1.9.0; derived from its reasons for an older one)."""
    from . import grouping as G

    return obj.get("reason_code") or G.merge_reason_code(obj.get("reasons") or ())


def _merge_candidate_view(bundle: Mapping, obj: Mapping) -> dict:
    """``bundle show merge-candidate``: what the candidate proposes, its groups' run labels, its caution
    and its reasons by code — no reading's value (those stay in bundle.json), so no exposure."""
    from . import grouping as G

    shown_keys = ("code", "group_id", "decision_id", "key", "why_unknown", "detail")
    return {
        "merge_candidate_id": obj.get("merge_candidate_id"),
        "status": obj.get("status"),
        "rule_id": obj.get("rule_id"),
        "reason_code": _mc_reason_code(obj),
        "reason_codes": obj.get("reason_codes") or sorted({r.get("code") for r in obj.get("reasons") or () if r.get("code")}),
        "caution": list(obj.get("caution") or ()),
        "groups": G.merge_candidate_groups(bundle, obj, cap=50),
        "question": (obj.get("question") or {}).get("text"),
        "reasons": [{k: r[k] for k in shown_keys if k in r} for r in obj.get("reasons") or ()],
        "kept_apart_by_decision_id": obj.get("kept_apart_by_decision_id"),
        "answer_with": [
            f"isaac bundle decide <bundle_dir> --target {(obj.get('group_ids') or ['<group>'])[0]} --decision merge "
            f"--merge-with {' '.join((obj.get('group_ids') or [])[1:]) or '<group>'} --by \"<your name>\"  &&  isaac bundle group <bundle_dir> --regroup",
            f"isaac bundle decide <bundle_dir> --target {obj.get('merge_candidate_id')} --decision keep_apart --by \"<your name>\"",
        ],
        "notice": "Readings' values are not printed here; `isaac bundle show <bundle_dir> group <group_id>` prints a group's.",
    }


_LIST_SECTION = {
    "groups": "record_groups",
    "merge-candidates": "merge_candidates",
    "runs": "runs",
    "conflicts": "conflicts",
    "candidates": "candidates",
    "questions": "questions",
    "unread": "unread_files",
    "processed-outputs": "processed_outputs",
    "processing-results": "processing_results",
}
#: ``bundle list <dir> unread``: files the IMPORT has no reader for but a later command reads (by suffix),
#: said on the row so an Athena project is never taken for a file nobody reads.
READ_LATER_BY_SUFFIX = {
    ".prj": ("isaac process (Athena project: its groups are read and matched by name to record groups, as the "
             "scientist's own processing to compare with; the import itself has no reader for it)"),
}
#: Metrics a ``processing-results`` row carries (the rest are in ``processing/processing_results.json``).
_RESULT_METRICS = ("scans_listed", "scans_used", "points", "e0_eV", "edge_step", "pre_edge_noise", "scan_spread",
                   "glitch_points", "outlier_scans", "nonfinite_dropped")
#: Review flags every draft-protocol result carries: left off the compact row (they say nothing per result).
_EVERY_RESULT_FLAGS = frozenset({"protocol_draft_unreviewed"})
_SHOW_SECTION = {
    "group": ("record_groups", "group_id"),
    "run": ("runs", "run_id"),
    "conflict": ("conflicts", "conflict_id"),
    "candidate": ("candidates", "candidate_id"),
    "source": ("sources", "source_id"),
    "question": ("questions", "question_id"),
    "merge-candidate": ("merge_candidates", "merge_candidate_id"),
    "processed-output": ("processed_outputs", "processed_output_id"),
}


def _exposed_by_show(kind: str, obj: Mapping) -> list[tuple[str, str]]:
    """Which targets' parser values ``bundle show <kind>`` prints."""
    if kind == "candidate":
        return [("candidate", obj["candidate_id"])]
    if kind == "conflict":
        return [("conflict", obj["conflict_id"])]
    if kind == "run" and obj.get("signal_selection"):
        return [("run", obj["run_id"])]
    if kind == "question" and obj["target"]["kind"] in ("candidate", "conflict") and obj.get("options"):
        return [(obj["target"]["kind"], obj["target"]["id"])]
    if kind == "processed-output":
        # it prints the files' own header literals (element, edge ...): an exposure of the
        # sources that state them and of the run it proposes to link to
        ids = [("source", f["source_id"]) for f in obj.get("files") or () if f.get("source_id")]
        ids += [("run", link["run_id"]) for link in obj.get("proposed_links") or ()]
        return ids
    if kind == "group":
        # a group's basis prints the readings it was grouped by: each is an exposure
        ids: list[tuple[str, str]] = []
        for section in ("sample", "technique", "environment", "conditions"):
            entries = (obj.get("basis") or {}).get(section)
            if isinstance(entries, Mapping):
                for entry in entries.values():
                    for cid in (entry.get("candidate_ids") or []) if isinstance(entry, Mapping) else []:
                        if ("candidate", cid) not in ids:
                            ids.append(("candidate", cid))
        return ids
    return []


def cmd_bundle_list(args) -> int:
    if args.limit < 1 or args.limit > MAX_LIMIT or args.offset < 0:
        _err(f"--limit must be 1..{MAX_LIMIT} and --offset must be >= 0.")
        return EXIT_USAGE
    bundle, code = _load(args.bundle_dir)
    if bundle is None:
        return code
    rows = list(bundle.get(_LIST_SECTION[args.kind]) or [])
    not_listed: dict[str, int] = {}
    if args.kind == "groups" and not args.all:
        # LIVE GROUPS ONLY by default (1.9.0): a merged, rejected or split group is the history of a
        # decision, not a record (before, a merge left 62 groups listed for 61 runs). --all lists them too.
        from . import bundle as B

        for r in rows:
            if r.get("status") not in B.LIVE_GROUP_STATUSES:
                not_listed[r.get("status")] = not_listed.get(r.get("status"), 0) + 1
        rows = [r for r in rows if r.get("status") in B.LIVE_GROUP_STATUSES]
    elif args.all and args.kind != "groups":
        _err("--all applies only to `groups`.")
        return EXIT_USAGE
    if args.state:
        if args.kind not in ("candidates", "processing-results"):
            _err("--state applies only to `candidates` and `processing-results`.")
            return EXIT_USAGE
        key = "value_state" if args.kind == "candidates" else "state"
        rows = [r for r in rows if r.get(key) == args.state]
    total = len(rows)
    page = rows[args.offset : args.offset + args.limit]
    status = {g["group_id"]: g.get("status") for g in bundle.get("record_groups") or ()}
    items = [_row(args.kind, r, status) for r in page]
    cannot_export: dict[str, int] = {}
    if args.kind == "groups":
        extras = group_list_extras(bundle)
        for item in items:
            item.update(extras.get(item["group_id"]) or {})
        for r in rows:  # counted over every listed group, not only this page
            reason = (extras.get(r["group_id"]) or {}).get("cannot_export_reason")
            if reason:
                cannot_export[reason] = cannot_export.get(reason, 0) + 1
    if args.kind == "runs" and page:
        # a stem two runs share (the same name in two folders) is told apart by the file's relative path
        from . import suggestions as S

        stems: dict[str, int] = {}
        for r in bundle.get("runs") or ():
            stems[str(r.get("stem"))] = stems.get(str(r.get("stem")), 0) + 1
        paths = S.run_paths(bundle) if any(stems.get(str(i.get("stem")), 0) > 1 for i in items) else {}
        for item in items:
            if stems.get(str(item.get("stem")), 0) > 1:
                item["path"] = paths.get(item["run_id"])
    if args.kind == "merge-candidates":
        from . import grouping as G

        for item, r in zip(items, page):
            item["groups"] = G.merge_candidate_groups(bundle, r)
    if args.kind == "candidates":
        if args.no_values:
            for item in items:
                item.pop("value", None)
        elif page:
            # THE PRINT IS AN EXPOSURE: recorded durably BEFORE anything is printed.
            from . import mutations as M

            try:
                M.expose_and_load(Path(args.bundle_dir), [("candidate", r["candidate_id"]) for r in page], "bundle list candidates")
            except M.MutationRefused as exc:
                _err(f"Nothing printed: {exc}")
                return exc.code
    payload = {
        "kind": args.kind,
        "total": total,
        "offset": args.offset,
        "limit": args.limit,
        "returned": len(page),
        "omitted_before": min(args.offset, total),
        "omitted_after": max(0, total - args.offset - len(page)),
        **({"not_listed": dict(sorted(not_listed.items())),
            "not_listed_note": "groups that are decision history (merged, rejected, split), not records: pass --all to list them"}
           if not_listed else {}),
        **({"cannot_export": dict(sorted(cannot_export.items(), key=lambda kv: (-kv[1], kv[0]))),
            "cannot_export_note": CANNOT_EXPORT_NOTE} if cannot_export else {}),
        "items": items,
    }
    # ONE LINE PER ROW for groups and runs (1.9.x polish): a 10-group page with file names, scans and reader
    # stays near 4 KB, and a row reads as a table row. Still one JSON document.
    print(_dumps_rows_inline(payload) if args.kind in INLINE_ROW_KINDS else json.dumps(payload, indent=1, ensure_ascii=False))
    return EXIT_OK


def _athena_version_brief(v: Mapping) -> dict:
    from pathlib import PurePosixPath

    prov = v.get("provenance") or {}
    path = prov.get("prj_relative_path")
    return {
        "version_id": v.get("version_id"),
        "project": prov.get("prj_file_name") or (PurePosixPath(str(path)).name if path else None),
        "group": prov.get("athena_group"),
        "label": _short(prov.get("athena_label"), 80),
    }


#: ``bundle show processing-result``: NO RAW ARRAYS. A list of numbers longer than this (per-scan values,
#: flagged points) is replaced by its length; a range such as ``grid_eV`` [lo, hi] stays.
_SHOW_MAX_NUMBERS = 4
#: ... and any other list (source ids, flags) longer than this.
_SHOW_MAX_LIST = 20


def _compact(value: Any) -> Any:
    """``value`` with every long list replaced by ``"<n> values (not shown)"``."""
    if isinstance(value, Mapping):
        return {k: _compact(v) for k, v in value.items()}
    if isinstance(value, list):
        numbers = all(isinstance(v, (int, float)) and not isinstance(v, bool) or v is None for v in value)
        if len(value) > (_SHOW_MAX_NUMBERS if numbers else _SHOW_MAX_LIST):
            return f"{len(value)} values (not shown)"
        return [_compact(v) for v in value]
    return value


def _scan_ranges(scans: Sequence[int]) -> str:
    """[1, 3, 4, 5, 8] -> "1,3-5,8" (a scan selection, short enough to print whole)."""
    out: list[str] = []
    nums = sorted({int(n) for n in scans})
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ",".join(out)


def _processing_result_view(bundle: Mapping, r: Mapping) -> dict:
    """One processing result, compact: what a reviewer needs to decide it and to pick an Athena version.
    Arrays (per-scan lists, flagged points) are counted, not printed; the full result is in ``result_file``."""
    from pathlib import PurePosixPath

    from . import bundle as B

    inputs = list(r.get("inputs") or ())
    skipped: dict[str, list] = {}
    for i in inputs:
        if i.get("skip_reason"):
            skipped.setdefault(str(i["skip_reason"]), []).append(i.get("source_id"))
    files = (r.get("outputs") or {}).get("files") or ()
    run_dir = next((PurePosixPath(f["relative_path"]).parent.as_posix() for f in files if f.get("relative_path")), None)
    status = {g["group_id"]: g.get("status") for g in bundle.get("record_groups") or ()}
    channel = r.get("channel_choice") if isinstance(r.get("channel_choice"), Mapping) else {}
    versions = []
    for v in r.get("athena_versions") or ():
        prov = v.get("provenance") or {}
        cmp_ = v.get("comparison") or {}
        versions.append({
            **_athena_version_brief(v),
            "project": prov.get("prj_relative_path") or prov.get("prj_file_name"),
            **{k: prov.get(k) for k in ("is_merge", "already_normalized") if prov.get(k) is not None},
            **({"scan_selection": _scan_ranges(prov["scan_selection"])} if prov.get("scan_selection") else {}),
            "flags": list(v.get("flags") or ()),
            "comparison": {"verdict": cmp_.get("verdict"), "flags": list(cmp_.get("flags") or ()),
                           **({"reason": cmp_["reason"]} if cmp_.get("reason") else {}),
                           "metrics": _compact({k: x for k, x in (cmp_.get("metrics") or {}).items() if not isinstance(x, (list, dict))})},
        })
    cmp_ = r.get("comparison") or None
    return _compact({
        "result_id": B.processing_id(r),
        "group_id": r.get("group_id"),
        "group_status": status.get(r.get("group_id")),
        "source": r.get("source"),
        "state": r.get("state"),
        "preferred_for_record": r.get("preferred_for_record"),
        "applicability": r.get("applicability"),
        "failure": r.get("failure"),
        "qc": r.get("qc"),
        "review_flags": list(r.get("review_flags") or ()),
        "channel": {k: channel.get(k) for k in ("mode", "signal_name", "energy", "i0") if channel.get(k) is not None} or None,
        "inputs": {"listed": len(inputs), "used": sum(1 for i in inputs if i.get("used")), "skipped": skipped},
        "steps": [{"step": s.get("step"), "flags": list(s.get("flags") or ()), "outcome": s.get("outcome")} for s in r.get("steps") or ()],
        "outputs": {"e0_eV": (r.get("outputs") or {}).get("e0_eV"), "edge_step": (r.get("outputs") or {}).get("edge_step"),
                    "points": (r.get("outputs") or {}).get("points"),
                    "files": [{"role": f.get("role"), "relative_path": f.get("relative_path")} for f in files]},
        "comparison": ({"verdict": cmp_.get("verdict"), "flags": cmp_.get("flags"), "athena_ref": cmp_.get("athena_ref"),
                        **({"reason": cmp_["reason"]} if cmp_.get("reason") else {}), "metrics": cmp_.get("metrics")} if cmp_ else None),
        "athena_versions": versions,
        "athena_result_of_record": r.get("athena_result_of_record"),
        "questions": r.get("questions") or [],
        "result_file": f"{run_dir}/result.json" if run_dir else None,
    })


#: ``bundle list`` kinds printed one row per line (see :func:`_dumps_rows_inline`).
INLINE_ROW_KINDS = ("groups", "runs")


def _dumps_rows_inline(payload: Mapping) -> str:
    """``payload`` as indented JSON, except that each of its ``items`` is printed on ONE line."""
    rows = [json.dumps(item, ensure_ascii=False) for item in payload["items"]]
    head = json.dumps({k: v for k, v in payload.items() if k != "items"}, indent=1, ensure_ascii=False)
    if not rows:
        return head[:-2] + ',\n "items": []\n}'
    return head[:-2] + ',\n "items": [\n  ' + ",\n  ".join(rows) + "\n ]\n}"


def cmd_bundle_show(args) -> int:
    bundle, code = _load(args.bundle_dir)
    if bundle is None:
        return code
    if args.kind == "processing-result":
        from . import bundle as B

        r = next((x for x in bundle.get("processing_results") or () if B.processing_id(x) == args.id), None)
        if r is None:
            _err(f"No processing-result with id {args.id!r} in this bundle (`bundle list <dir> processing-results` lists them).")
            return EXIT_NOT_FOUND
        print(json.dumps(_processing_result_view(bundle, r), indent=1, ensure_ascii=False))
        return EXIT_OK
    section, key = _SHOW_SECTION[args.kind]
    for obj in bundle.get(section) or ():
        if obj.get(key) == args.id:
            exposed = _exposed_by_show(args.kind, obj)
            if exposed:
                from . import mutations as M

                try:
                    M.expose_and_load(Path(args.bundle_dir), exposed, f"bundle show {args.kind}")
                except M.MutationRefused as exc:
                    _err(f"Nothing printed: {exc}")
                    return exc.code
            print(json.dumps(_merge_candidate_view(bundle, obj) if args.kind == "merge-candidate" else obj, indent=1, ensure_ascii=False))
            return EXIT_OK
    if args.kind == "question":
        # the id `bundle questions` prints (a consolidated question) is not a fine-grained one
        return _show_consolidated_question(args)
    _err(f"No {args.kind} with id {args.id!r} in this bundle.")
    return EXIT_NOT_FOUND


def _question_exposures(page: Sequence[Mapping]) -> list[tuple[str, str]]:
    """The parser values a page of consolidated questions prints: each hint's candidate and each
    resolve-conflict question's conflict (what `bundle questions` and `bundle show question` record)."""
    shown = [("candidate", h["candidate_id"]) for q in page for h in q["hints"] if h.get("candidate_id")]
    shown += [("conflict", q["targets"][0]["id"]) for q in page if q["kind"] == "resolve_conflict"]
    return shown


def _show_consolidated_question(args) -> int:
    """``bundle show <dir> question <Q-…>`` for a consolidated question id: that one question, compact as
    in `bundle questions`, with the exposures `bundle questions` would record for it, written before printing."""
    from . import mutations as M
    from . import questions as Q

    def run():
        bundle = M.load(Path(args.bundle_dir))
        payload = Q.consolidate(bundle)
        q = Q.question(payload, args.id)
        extra: dict = {}
        if q is None or q["kind"] in Q.VALUE_KINDS:
            # AN ANSWERED QUESTION (or an open one with answered targets: an optional-values field answered) is shown
            # under the id it was asked with, with what its answered targets carry now
            seen = Q.answered_question(bundle, args.id, open_payload=payload)
            if seen is not None and (q is None or seen["answered_targets"]):
                extra = {k: seen[k] for k in ("status", "answered_targets", "current_answers", "statement")}
                q = q or seen
        if q is None:
            raise M.MutationRefused(
                f"No question with id {args.id!r} in this bundle (`isaac bundle questions <dir>` lists the ids).", code=EXIT_NOT_FOUND)
        shown = _question_exposures([q])
        if shown:
            M.expose_and_load(Path(args.bundle_dir), shown, "bundle show question")
        return {**{k: v for k, v in _compact_question(q).items() if k not in extra}, **extra}

    return _mutation(run)


def _print_non_finite(bundle) -> None:
    """NAME every non-finite number bundle.json holds (an answer an older build accepted): the file is
    not standard JSON there, and none of them is ever eligible. A write never adds one."""
    from . import bundle as B

    found = B.non_finite_findings(bundle)
    if not found:
        return
    print(f"  NON-FINITE: bundle.json holds {len(found)} NaN/Infinity number(s), stored by an older build; they are "
          "not standard JSON and never eligible. The decision log is append-only, so they stay; a new answer replaces one:")
    for line in found[:50]:
        print(f"    - {line}")
    if len(found) > 50:
        print(f"    ... and {len(found) - 50} more")


def cmd_bundle_check(args) -> int:
    from . import bundle as B

    path = B.bundle_path(Path(args.bundle_dir).expanduser())
    if not path.is_file():
        _err(f"No bundle.json at {args.bundle_dir}.")
        return EXIT_NOT_FOUND
    errors = B.check_bundle(path)
    stale: list = []
    if errors:
        try:
            errors, stale = B.validate_allowing_stale(B.load_bundle(path))
        except B.BundleInvalid:
            pass
    if errors:
        print(f"INVALID: the bundle does not meet {B.FORMAT_ID} {B.FORMAT_VERSION} ({len(errors)} error(s) shown):")
        for e in errors:
            print(f"  - {e}")
        return EXIT_INVALID
    if stale:
        # STALE is not INVALID: an older build stored it, and this build can write more fields.
        # There is no exit code of its own (§10), so it is non-zero (EXIT_INVALID) and says so.
        bundle = B.load_bundle(path)
        print(f"STALE: this bundle (format {bundle.get('format_version')}) was stored by an older build; it is otherwise "
              f"valid against {B.FORMAT_ID} {B.FORMAT_VERSION}, but {len(stale)} value(s) are eligible differently under this build:")
        for x in stale[:50]:
            print(f"  - {x['kind']} {x['id']} ({x['target_field_path']}, {x['value_state']}): "
                  f"eligible {str(x['eligible_before']).lower()} -> {str(x['eligible_now']).lower()}: {x['reason']}")
        if len(stale) > 50:
            print(f"  ... and {len(stale) - 50} more")
        print("  Remedy: any change re-derives it under this build and logs each value in `eligibility_rederived`; "
              "`isaac bundle build-records` does that under the bundle lock before composing.")
        if B.needs_format_upgrade(bundle):
            print(f"  On that write: {B.upgrade_statement(bundle.get('format_version'), B._added_since(bundle.get('format_version')), B.import_rules_missing(bundle))}.")
        else:  # the same format: only the export target's allowed values re-derive them (bundle.allowed_list_rederivations)
            print("  On that write: the format stays the same; only these values' eligibility is re-derived and logged.")
        _print_non_finite(bundle)
        print("  Exit code 1 (EXIT_INVALID): the CLI has no exit code of its own for STALE.")
        return EXIT_INVALID
    bundle = B.load_bundle(path)
    states: dict[str, int] = {}
    for c in bundle["candidates"]:
        states[c["value_state"]] = states.get(c["value_state"], 0) + 1
    b = bundle["bounds"]
    print(f"VALID: meets {B.FORMAT_ID} {B.FORMAT_VERSION} (schema, bounds, references, value states).")
    print(f"  value states: {', '.join(f'{k} {v}' for k, v in sorted(states.items()))}")
    print(
        f"  bounds: {len(bundle['runs'])}/{b['max_runs']} runs, "
        f"{len(bundle['candidates'])}/{b['max_candidates']} candidates, "
        f"{b['evidence_windows_truncated']} evidence windows truncated, "
        f"{b['strings_truncated']} strings clamped"
    )
    for u in bundle.get("format_upgrades") or ():
        print(f"  {u['statement']} (by a {u['derived_by_format_version']} build, {u['upgraded_utc']}).")
    _print_non_finite(bundle)
    print("  This bundle is not an official ISAAC record; official validation does not apply to it.")
    return EXIT_OK


# --- LOCAL-2: mutations, records, upload -------------------------------------------------


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def _mutation(fn) -> int:
    from . import mutations as M
    from . import records as R

    try:
        result = fn()
    except (M.MutationRefused, R.RecordsRefused) as exc:
        _err(str(exc))
        return exc.code
    if result is not None:
        _print(result)
    return EXIT_OK


def cmd_bundle_annotate(args) -> int:
    from . import mutations as M

    def refuse(message: str):
        raise M.MutationRefused(message)

    if args.from_readings:
        if args.target or args.value is not None or args.blind:
            return _mutation(lambda: refuse("--from-readings takes its targets and values from the file, and a reading pass is not blind; drop --target/--value/--blind."))

        def run():
            try:
                findings = json.loads(Path(args.from_readings).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise M.MutationRefused(f"--from-readings cannot be read as JSON: {type(exc).__name__}", code=6) from exc
            return M.annotate_from_readings(Path(args.bundle_dir), findings, model_id=args.model, apply=args.apply)

        return _mutation(run)
    if args.apply:
        return _mutation(lambda: refuse("--apply goes with --from-readings; a single --target reading is recorded at once."))
    if not args.target:
        return _mutation(lambda: refuse("annotate needs --target, or --from-readings <findings.json>."))
    return _mutation(
        lambda: M.annotate(
            Path(args.bundle_dir),
            target_id=args.target,
            value=M.parse_value(args.value, args.json),
            excerpt_locator=args.excerpt_locator,
            source_id=args.source_id,
            model_id=args.model,
            blind=args.blind,
            rationale=args.rationale or "",
        )
    )


def _targets_from(args) -> list[str]:
    from . import mutations as M

    targets = [args.target] if args.target else []
    if args.targets_file:
        try:
            text = Path(args.targets_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise M.MutationRefused(f"--targets-file cannot be read: {type(exc).__name__}", code=6) from exc
        try:
            parsed = json.loads(text)
            ids = parsed if isinstance(parsed, list) else parsed.get("targets", [])
        except ValueError:
            ids = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
        if not all(isinstance(i, str) for i in ids):
            raise M.MutationRefused("--targets-file must list target ids.")
        targets.extend(ids)
    return targets


def cmd_bundle_questions(args) -> int:
    from . import mutations as M
    from . import questions as Q

    if args.limit < 1 or args.limit > MAX_LIMIT or args.offset < 0:
        _err(f"--limit must be 1..{MAX_LIMIT} and --offset must be >= 0.")
        return EXIT_USAGE

    def run():
        bundle = M.load(Path(args.bundle_dir))
        reports: dict = {}  # composed once: consolidate's reports are reused by the minimum below
        payload = Q.consolidate(bundle, compositions_out=reports)
        rows = Q.filter_questions(payload, scope=args.scope, blocking_only=args.blocking_only)
        kept = [q for q in rows if not (args.skip_deferred and q.get("deferred"))]
        page = kept[args.offset : args.offset + args.limit]
        # HINTS SHOW PARSER LITERALS: that is an exposure, recorded before printing.
        shown = _question_exposures(page)
        if shown:
            M.expose_and_load(Path(args.bundle_dir), shown, "bundle questions")
        return {
            "format": payload["format"], "format_version": payload["format_version"],
            "blocking_basis": payload["blocking_basis"],
            # THE SCOPE'S counts (every question --scope selects, before --blocking-only / --skip-deferred), and the
            # whole bundle's under their own name
            "counts": Q.scope_counts(payload, args.scope),
            **({"counts_whole_bundle": payload["counts"]} if args.scope else {}),
            "total": len(kept), "offset": args.offset, "limit": args.limit, "returned": len(page),
            "omitted_before": min(args.offset, len(kept)),
            "omitted_after": max(0, len(kept) - args.offset - len(page)),
            **({"skipped_deferred": len(rows) - len(kept)} if args.skip_deferred else {}),
            "minimum_for_one_group": Q.minimum_answers_for_one_group(payload, bundle, scope=args.scope,
                                                                     bundle_dir=Path(args.bundle_dir), reports=reports),
            **({"questions": page} if args.with_targets else _compact_page(page)),
        }

    return _mutation(run)


#: How many of a long id list a compact question keeps (the count says how many there are).
_COMPACT_KEEP = 5
#: Keys a compact question leaves out when they hold nothing (null, false, empty).
_COMPACT_DROP_EMPTY = frozenset({"partition", "hints", "field_hints", "answers_differ", "allowed_values", "asked_again",
                                 "targets_without_a_value", "targets_with_an_unfit_value"})


def _compact_page(page: Sequence[Mapping]) -> dict:
    """THE DEFAULT PAGE: each question compact (:func:`_compact_question`), and what repeats from question to
    question said ONCE — the allowed values per field (``allowed_values_by_field``: a question's ``allowed_values``
    / ``field_allowed_values`` are there, under its field) and each kind's allowed decisions
    (``allowed_decisions_by_kind``: a question lists ``allowed_decisions`` only where it differs) — and each hint
    kind's standing note (``hint_notes``: a hint carries ``note`` only where it says something else)."""
    from . import questions as Q

    notes: dict[str, str] = {}

    def lean(hints):
        out = []
        for h in hints or ():
            kind, note = h.get("kind"), h.get("note")
            if isinstance(kind, str) and isinstance(note, str) and notes.setdefault(kind, note) == note:
                h = {k: v for k, v in h.items() if k != "note"}
            out.append(h)
        return out

    by_field: dict[str, list] = {}
    by_kind = {q["kind"]: list(Q.ALLOWED_DECISIONS.get(q["kind"], ())) for q in page}
    out = []
    for q in page:
        c = _compact_question(q)
        if c.get("allowed_values") and c.get("target_field_path"):
            by_field[c["target_field_path"]] = c.pop("allowed_values")
        for f, values in (c.pop("field_allowed_values", None) or {}).items():
            by_field[f] = values
        if c.get("allowed_decisions") == by_kind.get(c["kind"]):
            del c["allowed_decisions"]
        if c.get("hints"):
            c["hints"] = lean(c["hints"])
        if c.get("field_hints"):
            c["field_hints"] = {f: lean(hs) for f, hs in c["field_hints"].items()}
        out.append(c)
    return {"targets": ("counted: each question's targets_count, scopes_count and groups_count (--with-targets lists "
                        "them; `decide --question` resolves them itself); allowed values are listed once per field "
                        "in allowed_values_by_field, allowed decisions once per kind in allowed_decisions_by_kind, and "
                        "each hint kind's note once in hint_notes"),
            "allowed_values_by_field": dict(sorted(by_field.items())), "allowed_decisions_by_kind": by_kind,
            "hint_notes": notes, "questions": out}


def _compact_question(q: Mapping) -> dict:
    """A question as `bundle questions` prints it by default: its target id lists (``targets``,
    ``per_scope_targets``, an optional-values question's per-field ids, the groups it blocks) are COUNTED, not
    listed — `decide --question` resolves them itself, and they were most of the page. ``--with-targets`` prints
    them in full."""
    out = {k: v for k, v in q.items() if k not in ("targets", "per_scope_targets", "blocks_group_ids")
           # nothing said by an empty value: left out (the full question, --with-targets, keeps every key)
           and not (k in _COMPACT_DROP_EMPTY and not v)}
    if isinstance(out.get("applies_to"), Mapping) and not out["applies_to"].get("runs_outside_live_groups"):
        out["applies_to"] = {k: v for k, v in out["applies_to"].items() if k != "runs_outside_live_groups"}
    pst = q.get("per_scope_targets") or {}
    out["targets_count"] = len(q.get("targets") or ())
    out["scopes_count"] = len(pst)
    out["groups_count"] = sum(1 for s in pst if s.startswith("group:"))
    if q.get("kind") == "optional_values" and isinstance(q.get("fields"), Mapping):
        out["fields"] = {f: len(ids) for f, ids in q["fields"].items()}
    scopes = q.get("confirmable_scopes")
    if isinstance(scopes, list) and len(scopes) > _COMPACT_KEEP:
        out["confirmable_scopes"] = scopes[:_COMPACT_KEEP]
        out["confirmable_scopes_count"] = len(scopes)
    return out


def _positions(raw: str | None):
    from . import mutations as M

    from .grouping import LAST_POSITION

    if raw is None:
        return None
    try:
        return [LAST_POSITION if x.strip().casefold() == "last" else int(x) for x in raw.split(",") if x.strip()]
    except ValueError as exc:
        raise M.MutationRefused("--positions must be whole numbers or `last` (the last token, whatever the name's length) "
                                "separated by commas, e.g. 2,3 or last.") from exc


def cmd_bundle_decide(args) -> int:
    from . import mutations as M

    def run():
        try:
            split = json.loads(args.split_into) if args.split_into else None
        except ValueError as exc:
            raise M.MutationRefused(f"--split-into is not valid JSON: {exc}") from exc
        targets = _targets_from(args)
        positions = _positions(args.positions)
        if args.question:
            # the question is resolved to its targets under the write's own lock (mutations.decide_question,
            # shared with the local questions screen)
            return M.decide_question(
                Path(args.bundle_dir),
                question_id=args.question,
                only=args.only,
                field=args.field,
                extra_targets=targets,
                decision=args.decision,
                value=M.parse_value(args.value, args.json),
                by=args.by,
                orcid=args.orcid,
                note=args.note,
                split_into=split,
                merge_with=args.merge_with,
                qc_status=args.qc_status,
                qc_note=args.qc_note,
                element=args.element,
                edge=args.edge,
                positions=positions,
                same_conditions=args.same_conditions,
            )
        return M.decide(
            Path(args.bundle_dir),
            target_ids=targets,
            decision=args.decision,
            value=M.parse_value(args.value, args.json),
            by=args.by,
            orcid=args.orcid,
            note=args.note,
            split_into=split,
            merge_with=args.merge_with,
            qc_status=args.qc_status,
            qc_note=args.qc_note,
            element=args.element,
            edge=args.edge,
            positions=positions,
            same_conditions=args.same_conditions,
        )

    return _mutation(run)


def cmd_bundle_crosscheck_plan(args) -> int:
    from . import mutations as M

    def run():
        plan = M.crosscheck_plan(M.load(Path(args.bundle_dir)))
        items = plan["items"]
        plan["offset"], plan["limit"] = args.offset, args.limit
        plan["items"] = items[args.offset : args.offset + args.limit]
        plan["returned"] = len(plan["items"])
        plan["omitted_before"] = min(args.offset, len(items))
        plan["omitted_after"] = max(0, len(items) - args.offset - plan["returned"])
        return plan

    return _mutation(run)


def cmd_bundle_excerpt(args) -> int:
    from . import mutations as M

    return _mutation(lambda: M.excerpt(M.load(Path(args.bundle_dir)), args.id, source=args.source))


def cmd_bundle_reveal(args) -> int:
    from . import mutations as M

    return _mutation(lambda: M.reveal(Path(args.bundle_dir), args.id))


#: How many drafts and skipped groups ``bundle build-records`` prints in full by default (``--full`` prints all).
BUILD_ROWS_SHOWN = 3


def compact_build(result: Mapping) -> dict:
    """``bundle build-records``'s reply as counts: drafts complete / incomplete, why (counted), which required
    fields are missing (counted), the first :data:`BUILD_ROWS_SHOWN` drafts and where the rest are. Measured on a
    real BL6-2c bundle: 78 drafts and 116 skipped groups printed 52 KB."""
    from . import records as R

    drafts = list(result.get("drafts") or ())
    skipped = list(result.get("skipped_groups") or ())
    if len(drafts) <= BUILD_ROWS_SHOWN and len(skipped) <= BUILD_ROWS_SHOWN:
        return dict(result)
    rows = [{"verdict": "complete" if d.get("complete") else "incomplete",
             "processing_blocker": d.get("processing_blocker") or ("processing_not_applicable" if d.get("blocked") else None),
             "missing_required": d.get("missing_required")} for d in drafts]
    by_reason, by_field = R.refusal_counts(rows)
    disagreeing = sum(1 for d in drafts if d.get("disagreements"))
    if disagreeing:
        by_reason["disagreements"] = disagreeing
    by_status: dict[str, int] = {}
    for g in skipped:
        by_status[g.get("status")] = by_status.get(g.get("status"), 0) + 1
    out = {k: v for k, v in result.items() if k not in ("drafts", "skipped_groups")}
    out.update(
        drafts_total=len(drafts),
        complete=sum(1 for d in drafts if d.get("complete")),
        incomplete=sum(1 for d in drafts if not d.get("complete")),
        by_reason=by_reason,
        missing_required_by_field=by_field,
        drafts=drafts[:BUILD_ROWS_SHOWN],
        drafts_omitted=max(0, len(drafts) - BUILD_ROWS_SHOWN),
        skipped_groups_total=len(skipped),
        skipped_by_status=dict(sorted(by_status.items(), key=lambda kv: str(kv[0]))),
        skipped_reason="only a scientist-confirmed record group becomes a draft",
        full_list=(f"{R.DRAFTS_DIR}/index.json lists every draft and skipped group; pass --full to print them all. "
                   "`isaac bundle validate <bundle_dir>` says why each draft is not exportable."),
    )
    return out


def cmd_bundle_build_records(args) -> int:
    from . import records as R

    def run():
        result = R.build_records(Path(args.bundle_dir), test_marker=args.test_marker)
        return result if args.full else compact_build(result)

    return _mutation(run)


def cmd_bundle_validate(args) -> int:
    """Exit 0 only when EVERY draft is exportable and there is at least one; 1 otherwise (each verdict printed)."""
    from . import records as R

    holder: dict = {}

    def run():
        holder["r"] = R.validate_records(Path(args.bundle_dir))
        return holder["r"]

    code = _mutation(run)
    verdicts = holder["r"]["verdicts"] if code == EXIT_OK else {}
    if code == EXIT_OK and (not verdicts or any(v != "exportable" for v in verdicts.values())):
        return EXIT_INVALID
    return code


#: How many refused groups ``bundle export`` prints in full by default (``--full`` prints all).
EXPORT_REFUSED_SHOWN = 3


def compact_export(result: Mapping) -> dict:
    """``bundle export``'s reply without every refused group's full summary: counts by reason, the
    first :data:`EXPORT_REFUSED_SHOWN` refusals in full, and where the rest are. Measured on a real
    BL4-3 bundle with nothing exportable: 35 refusals printed 40 KB."""
    from . import records as R

    refused = list(result.get("refused") or ())
    if len(refused) <= EXPORT_REFUSED_SHOWN:
        return dict(result)
    by_reason, by_field = R.refusal_counts(refused)
    out = {k: v for k, v in result.items() if k != "refused"}
    out.update(
        refused_total=len(refused),
        refused_by_reason=by_reason,
        missing_required_by_field=by_field,
        refused=refused[:EXPORT_REFUSED_SHOWN],
        refused_omitted=len(refused) - EXPORT_REFUSED_SHOWN,
        refused_full_list=("Pass --full to print every refused group's summary, or run `isaac bundle validate "
                           "<bundle_dir>`: it writes each group's full report to <bundle_dir>/validation/<group_id>.json."),
    )
    return out


def cmd_bundle_export(args) -> int:
    """Exit 0 only when nothing was refused; 1 when any draft was not exported."""
    from . import records as R

    holder: dict = {}

    def run():
        holder["r"] = R.export_records(Path(args.bundle_dir), Path(args.out))
        return holder["r"] if args.full else compact_export(holder["r"])

    code = _mutation(run)
    if code == EXIT_OK and holder["r"]["refused"]:
        return EXIT_INVALID
    return code


def cmd_bundle_upload(args) -> int:
    from . import records as R

    if not args.dry_run:
        _err("uploads are disabled in this build. Use --dry-run to see what would be sent.")
        return EXIT_USAGE
    if not Path(args.records_dir).is_dir():
        _err(f"No records directory at {args.records_dir}.")
        return EXIT_NOT_FOUND
    plan = R.upload_plan(Path(args.records_dir), args.portal_url)
    _print({"dry_run": True, "network_calls": 0, "records": plan,
            "statement": "Nothing was sent. The token is never read or printed."})
    return EXIT_OK


def cmd_bundle_propose_terms(args) -> int:
    """Off-vocabulary values in the bundle, as draft term proposals (``propose_terms``)."""
    from .. import schema_locator
    from .. import schema_proposal_rules as SR
    from . import mutations as M
    from . import propose_terms as P

    bundle, code = _load(args.bundle_dir)
    if bundle is None:
        return code
    out_path = Path(args.out).expanduser() if args.out else None
    if out_path is not None:
        if out_path.is_dir():
            _err(f"--out {args.out} is a directory; name a file.")
            return EXIT_OUTPUT_REFUSED
        if out_path.exists() and not args.force:
            _err(f"--out {args.out} already exists; pass --force to replace it. Nothing was written.")
            return EXIT_OUTPUT_REFUSED
        if not out_path.parent.is_dir():
            _err(f"The folder for --out {args.out} does not exist. Nothing was written.")
            return EXIT_OUTPUT_REFUSED
    try:
        sources = SR.load_sources_at(schema_locator.resolve_schema_path())
    except (OSError, ValueError) as exc:
        _err(f"The vocabulary could not be read ({exc}); nothing was compared and nothing was written.")
        return EXIT_INVALID
    report = P.propose_terms(bundle, sources)
    if report["exposed_candidates"]:
        # THE OUTPUT CARRIES PARSER VALUES: recorded as an exposure BEFORE anything is printed
        # or written, as `bundle list candidates` does (contract §11).
        try:
            M.expose_and_load(
                Path(args.bundle_dir), [("candidate", cid) for cid in report["exposed_candidates"]], P.COMMAND
            )
        except M.MutationRefused as exc:
            _err(f"Nothing printed or written: {exc}")
            return exc.code
    text = json.dumps(report, indent=1, ensure_ascii=False) + "\n"
    if out_path is None:
        sys.stdout.write(text)
        return EXIT_OK
    _atomic_write(out_path, text.encode("utf-8"))
    totals = report["totals"]
    print(
        f"Wrote {out_path}: {totals['terms']} term(s) outside the vocabulary in {totals['fields']} field(s), "
        f"{totals['occurrences']} occurrence(s), {totals['drafts']} draft proposal(s). Nothing was sent; "
        "each draft needs a description in your words before it can go to the ISAAC portal."
    )
    return EXIT_OK


def cmd_bundle_group(args) -> int:
    from . import mutations as M

    return _mutation(lambda: M.group(Path(args.bundle_dir), regroup=args.regroup))


def cmd_process(args) -> int:
    from . import mutations as M

    return _mutation(
        lambda: M.process(
            Path(args.bundle_dir),
            source=args.source,
            group_ids=args.group or None,
            athena=not args.no_athena,
            params_file=args.params_file,
        )
    )


def cmd_bundle_template_export(args) -> int:
    """``isaac bundle template export``: the metadata template, answer cells empty."""
    from . import template as T

    try:
        result = T.export_template(Path(args.bundle_dir), Path(args.out), suggestions=not args.no_suggestions, force=args.force)
    except T.TemplateRefused as exc:
        _err(str(exc))
        return exc.code
    if args.json:
        _print(result)
    else:
        print(T.render_export_summary(result))
    return EXIT_OK


def cmd_bundle_template_import(args) -> int:
    """``isaac bundle template import``: preview by default; ``--apply`` records decisions."""
    from . import mutations as M
    from . import template as T

    try:
        report = T.import_template(Path(args.bundle_dir), Path(args.xlsx), by=args.by, orcid=args.orcid,
                                   apply=args.apply, supersede=args.supersede)
    except T.TemplateRefused as exc:
        _err(str(exc))
        return exc.code
    except M.MutationRefused as exc:
        _err(str(exc))
        return exc.code
    if args.json:
        _print(report)
    else:
        print(T.render_report(report, full=args.full))
    return EXIT_OK


# --- argparse ---------------------------------------------------------------------------


def build_parser(prog: str = "isaac") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="ISAAC local-first import: reads a folder or ZIP on this machine into a Local Import Bundle, without starting the web application.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="read a folder or ZIP into an ISAAC Local Import Bundle")
    p.add_argument("path", help="the folder or .zip to read")
    p.add_argument("--out", required=True, help="directory to write the bundle into")
    p.add_argument("--profile", default="auto", help="naming profile id, or auto (default)")
    p.add_argument("--force", action="store_true", help="overwrite the bundle files in a non-empty --out")
    p.add_argument(
        "--record-local-root",
        action="store_true",
        help="also record this machine's absolute path to the source as source_root.local_root_hint (off by default)",
    )
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("process", help="run the draft XAS processing protocol over the bundle's record groups")
    p.add_argument("bundle_dir")
    p.add_argument("--source", help="the folder that was imported (if the bundle does not record it)")
    p.add_argument("--group", action="append", help="process only this group id (repeatable)")
    p.add_argument("--no-athena", action="store_true", help="do not read the scientist's Athena projects")
    p.add_argument("--params-file", help="JSON overrides for the protocol's parameters")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("bundle", help="inspect an ISAAC Local Import Bundle")
    bsub = p.add_subparsers(dest="bundle_command", required=True)
    q = bsub.add_parser("list", help="a bounded, paginated list")
    q.add_argument("bundle_dir")
    q.add_argument("kind", choices=LIST_KINDS)
    q.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    q.add_argument("--offset", type=int, default=0)
    q.add_argument("--state", help="candidates: filter by value_state; processing-results: filter by state")
    q.add_argument("--no-values", action="store_true", help="candidates only: omit parser values (records no exposure)")
    q.add_argument("--all", action="store_true", help="groups only: also list merged, rejected and split groups (decision history)")
    q.set_defaults(func=cmd_bundle_list)
    q = bsub.add_parser("show", help="one object by id")
    q.add_argument("bundle_dir")
    q.add_argument("kind", choices=SHOW_KINDS)
    q.add_argument("id")
    q.set_defaults(func=cmd_bundle_show)
    q = bsub.add_parser("check", help="re-validate a bundle against v1")
    q.add_argument("bundle_dir")
    q.set_defaults(func=cmd_bundle_check)

    q = bsub.add_parser("annotate", help="record an AI interpretation (never above needs_review)")
    q.add_argument("bundle_dir")
    q.add_argument("--target", help="one target id (or use --from-readings)")
    q.add_argument("--from-readings", help="a Claude reading pass's findings file (isaac.reading_findings): one interpretation per target it names")
    q.add_argument("--apply", action="store_true", help="with --from-readings: record them (default: show what would be recorded)")
    q.add_argument("--value")
    q.add_argument("--json", action="store_true", help="parse --value as JSON")
    q.add_argument("--excerpt-locator")
    q.add_argument("--source-id")
    q.add_argument("--model", required=True)
    q.add_argument("--blind", action="store_true")
    q.add_argument("--rationale")
    q.set_defaults(func=cmd_bundle_annotate)

    q = bsub.add_parser("decide", help="record a scientist decision (identity: local_unverified)")
    q.add_argument("bundle_dir")
    q.add_argument("--target")
    q.add_argument("--targets-file")
    q.add_argument("--question", help="answer a consolidated question: one decision per target, each listed")
    q.add_argument("--only", help="with --question: only this scope (group:<id> or run:<id>) — a per-group override")
    q.add_argument("--field", help="with --question on an optional-values question: the one field being answered")
    q.add_argument("--decision", required=True,
                   help="candidate / missing value / conflict: confirm correct reject defer; record group: confirm split merge "
                        "reject defer approve_calibration set_absorber; processing result: approve reject needs_changes defer, "
                        "or select_athena_version --value <one of its athena_versions[].version_id> (the result of record, "
                        "bound to that version's project file, group and data hash, so a renumbering re-processing keeps it; "
                        "changes no QC status and no processed value); merge candidate (mc-...): keep_apart (the groups are "
                        "distinct; no group changes); --target experiment: set_counter_positions (with --positions), "
                        "set_not_counter_positions (with --positions, or --question on the counter question: those positions "
                        "are not counters; grouping is unchanged) or set_clock_time_zone (with --value). "
                        "MERGING two groups takes three steps: (1) --target <group> --decision merge --merge-with <group...>; "
                        "(2) isaac bundle group <dir> --regroup, which proposes ONE combined group (flag "
                        "merged_by_scientist_decision) only when nothing recorded tells them apart: no confirmed run, one role, "
                        "every recorded reading and confirmed run answer equal (runs measured under different conditions are "
                        "never combined), and file names that agree once repeat markers (again, repeat, redo ...) and the positions "
                        "declared run counters (set_counter_positions) are left out — or, where they still differ, the same "
                        "sample.material.name confirmed for every run AND the merge recorded with --same-conditions (the words "
                        "the names differ in are labels, not conditions), no differing token stating a quantity (400mV, "
                        "0p5wt, T300); "
                        "otherwise its merge_decisions_not_combined entry gives the reason and next_commands that move it on; "
                        "(3) --target <combined group> --decision confirm")
    q.add_argument("--value", help="the value; for set_clock_time_zone the IANA name (Area/Location, or UTC) of the time zone "
                                   "the INSTRUMENT CLOCK that wrote the scan headers was set to (no offset, no abbreviation)")
    q.add_argument("--json", action="store_true", help="parse --value as JSON")
    q.add_argument("--by", required=True)
    q.add_argument("--orcid")
    q.add_argument("--note")
    q.add_argument("--split-into", help="record groups: JSON list of lists of run keys")
    q.add_argument("--merge-with", nargs="*", help="record groups: group ids to merge with")
    q.add_argument("--same-conditions", action="store_true",
                   help="with --decision merge: the scientist states the runs measured the same sample under the SAME "
                        "conditions — the words their file names differ in (stored on the decision) are labels, not "
                        "conditions. Refused when the names state different quantities")
    q.add_argument("--qc-status", help="processing result + approve: measurement.qc.status, from the pinned vocabulary")
    q.add_argument("--qc-note", help="with --qc-status: what is compromised or failed, and why")
    q.add_argument("--element", help="record group + approve_calibration (the calibration reference) or set_absorber (the absorber): an element, e.g. Ir")
    q.add_argument("--edge", help="with --element: the edge (K, L1-L3, M1-M5)")
    q.add_argument("--positions", help="--target experiment + set_counter_positions or set_not_counter_positions: "
                                       "1-based filename token positions, e.g. 2 or 2,3; set_counter_positions also takes "
                                       "last (the last token, whatever the name's length), e.g. last or 3,last")
    q.set_defaults(func=cmd_bundle_decide)

    q = bsub.add_parser("questions", help="consolidated questions: asked once, at the right scope, blocking first")
    q.add_argument("bundle_dir")
    q.add_argument("--scope", help="experiment | group:<id> | run:<id>")
    q.add_argument("--blocking-only", action="store_true",
                   help="only what blocks export (with --scope group:<id>: what blocks THAT group's record)")
    q.add_argument("--skip-deferred", action="store_true",
                   help="leave out questions whose every target was deferred (still counted: counts.deferred)")
    q.add_argument("--with-targets", action="store_true",
                   help="list each question's target ids (targets, per_scope_targets); by default they are counted")
    q.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    q.add_argument("--offset", type=int, default=0)
    q.set_defaults(func=cmd_bundle_questions)

    q = bsub.add_parser("crosscheck-plan", help="high-value targets to cross-check (ids and locators, no values)")
    q.add_argument("bundle_dir")
    q.add_argument("--limit", type=int, default=50)
    q.add_argument("--offset", type=int, default=0)
    q.set_defaults(func=cmd_bundle_crosscheck_plan)

    q = bsub.add_parser("excerpt", help="raw source text at a target's locators (no parser value)")
    q.add_argument("bundle_dir")
    q.add_argument("id")
    q.add_argument("--source", help="the folder or ZIP that was imported")
    q.set_defaults(func=cmd_bundle_excerpt)

    q = bsub.add_parser("reveal", help="show a parser value and compare AI readings (records an exposure)")
    q.add_argument("bundle_dir")
    q.add_argument("id")
    q.set_defaults(func=cmd_bundle_reveal)

    q = bsub.add_parser(
        "propose-terms",
        help="values outside the vocabulary, as draft term proposals for the ISAAC portal (local; nothing is sent)",
    )
    q.add_argument("bundle_dir")
    q.add_argument("--out", help="write the drafts to this JSON file instead of printing them")
    q.add_argument("--force", action="store_true", help="replace --out if it exists")
    q.set_defaults(func=cmd_bundle_propose_terms)

    q = bsub.add_parser("group", help="propose record groups (one record = one sample, technique, set of conditions)")
    q.add_argument("bundle_dir")
    q.add_argument("--regroup", action="store_true", help="replace undecided groups; decided ones are kept")
    q.set_defaults(func=cmd_bundle_group)

    q = bsub.add_parser("build-records", help="compose one ISAAC draft per confirmed record group")
    q.add_argument("bundle_dir")
    q.add_argument("--test-marker", action="store_true", help="SELF-TESTS ONLY: write the fixed self-test marker into the series and QC notes")
    q.add_argument("--full", action="store_true", help="print every draft and skipped group (default: counts and the first few; drafts/index.json has them all)")
    q.set_defaults(func=cmd_bundle_build_records)

    q = bsub.add_parser("validate", help="validate drafts: draft, export dry-run, official, exactness, offline portal")
    q.add_argument("bundle_dir")
    q.set_defaults(func=cmd_bundle_validate)

    q = bsub.add_parser("export", help="write official records that pass every gate")
    q.add_argument("bundle_dir")
    q.add_argument("--out", required=True)
    q.add_argument("--full", action="store_true", help="print every refused group's full summary (default: counts and the first few)")
    q.set_defaults(func=cmd_bundle_export)

    q = bsub.add_parser("upload", help="DRY RUN ONLY: what would be sent to the portal")
    q.add_argument("records_dir")
    q.add_argument("--dry-run", action="store_true")
    q.add_argument("--portal-url")
    q.set_defaults(func=cmd_bundle_upload)

    q = bsub.add_parser("template", help="the ISAAC metadata template: export it, fill it once, import the answers")
    tsub = q.add_subparsers(dest="template_command", required=True)
    t = tsub.add_parser("export", help="write the template (answer cells empty; suggestions on their own sheet)")
    t.add_argument("bundle_dir")
    t.add_argument("--out", required=True, help="the .xlsx file to write")
    t.add_argument("--force", action="store_true", help="replace an existing --out file")
    t.add_argument("--no-suggestions", action="store_true", help="leave the ISAAC Suggestions sheet empty (records no exposure)")
    t.add_argument("--json", action="store_true", help="print the full result as JSON, with every column's mapping")
    t.set_defaults(func=cmd_bundle_template_export)
    t = tsub.add_parser("import", help="read a filled template: preview by default, --apply to record decisions")
    t.add_argument("bundle_dir")
    t.add_argument("xlsx")
    t.add_argument("--by", required=True, help="the name of the person whose answers these are")
    t.add_argument("--orcid")
    t.add_argument("--apply", action="store_true", help="record the decisions (default: preview, nothing written)")
    t.add_argument("--supersede", action="store_true", help="record a cell even where an earlier decision gives a different value")
    t.add_argument("--json", action="store_true", help="print the full report as JSON")
    t.add_argument("--full", action="store_true",
                   help="list every decision and cell (default: one line per cell or column, problems in full)")
    t.set_defaults(func=cmd_bundle_template_import)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from .. import schema_locator

    schema_locator.enable_local_cli_override()
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse's own usage error
        return EXIT_USAGE if exc.code not in (0, None) else EXIT_OK
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
