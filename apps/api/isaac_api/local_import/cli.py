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

``isaac bundle list <dir> runs|conflicts|candidates|questions|unread [--limit N] [--offset M] [--state S]``
    A bounded page as JSON, with ``total`` and how many were omitted before and after.
    Never truncates silently.

``isaac bundle show <dir> run|conflict|candidate|source|question <id>``
    One object as JSON.

``isaac bundle check <dir>``
    Re-validate the bundle against v1: schema, bounds, references, and the state rule.

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
 1    (also) ``validate``/``export``: some draft is not exportable / was not exported
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

LIST_KINDS = ("runs", "conflicts", "candidates", "questions", "unread", "groups", "merge-candidates", "processed-outputs")
SHOW_KINDS = ("run", "conflict", "candidate", "source", "question", "group", "processed-output")
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
    add("")
    add("## Counts")
    add("")
    add(
        f"- Files: {counts['sources']} inventoried, {counts['unread_files']} unread or refused"
        + (f" (walk stopped: {root['truncated_reason']})" if root.get("truncated_reason") else "")
    )
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
        f"- Conflicts: {counts['conflicts']} · Missing values: {counts['missing_values']} "
        f"(nothing defaulted) · Questions: {counts['questions']}"
    )
    add(f"- People named in the sources: {counts['contributors']} (evidence, not the naming profile)")
    groups = bundle.get("record_groups") or []
    if groups or bundle.get("processing_results"):
        add(
            f"- Record groups: {len(groups)} ({sum(1 for g in groups if g['status'] == 'scientist_confirmed')} "
            f"confirmed) · processing results: {len(bundle.get('processing_results') or [])}"
        )
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
            add(
                f"- group {s['group_token']}: {len(s['run_ids'])} runs "
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

    unread = bundle["unread_files"]
    add("## Unread files")
    add("")
    if not unread:
        add("Every inventoried file had a reader.")
    for u in unread[:_SUMMARY_LIST_ROWS]:
        add(f"- {_clip(u['relative_path'] or '(name withheld)', 60)} — {u['reason_code']}")
    if len(unread) > _SUMMARY_LIST_ROWS:
        add(f"- … {len(unread) - _SUMMARY_LIST_ROWS} more: `isaac bundle list <dir> unread`")
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
    errors = B.validate_bundle(bundle)
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
        f"({c['conflicts']} conflicts, {c['needs_review']} need review, "
        f"{c['missing_values']} missing, {c['unread_files']} unread files)"
    )
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


def _row(kind: str, obj: Mapping) -> dict:
    if kind == "runs":
        return {
            "run_id": obj["run_id"],
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
        return {
            "merge_candidate_id": obj.get("merge_candidate_id") or obj.get("id"),
            "group_ids": list(obj.get("group_ids") or [])[:50],
            "reason_code": obj.get("reason_code") or obj.get("code") or obj.get("basis"),
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
    if kind == "questions":
        return {
            "question_id": obj["question_id"],
            "kind": obj["kind"],
            "target": obj["target"],
            "run_id": obj["run_id"],
            "prompt": _short(obj["prompt"], 240),
        }
    return {
        "relative_path": obj["relative_path"],
        "source_id": obj["source_id"],
        "source_type": obj["source_type"],
        "reason_code": obj["reason_code"],
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
}
_SHOW_SECTION = {
    "group": ("record_groups", "group_id"),
    "run": ("runs", "run_id"),
    "conflict": ("conflicts", "conflict_id"),
    "candidate": ("candidates", "candidate_id"),
    "source": ("sources", "source_id"),
    "question": ("questions", "question_id"),
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
    if args.state:
        if args.kind != "candidates":
            _err("--state applies only to `candidates`.")
            return EXIT_USAGE
        rows = [r for r in rows if r.get("value_state") == args.state]
    total = len(rows)
    page = rows[args.offset : args.offset + args.limit]
    items = [_row(args.kind, r) for r in page]
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
    print(
        json.dumps(
            {
                "kind": args.kind,
                "total": total,
                "offset": args.offset,
                "limit": args.limit,
                "returned": len(page),
                "omitted_before": min(args.offset, total),
                "omitted_after": max(0, total - args.offset - len(page)),
                "items": items,
            },
            indent=1,
            ensure_ascii=False,
        )
    )
    return EXIT_OK


def cmd_bundle_show(args) -> int:
    bundle, code = _load(args.bundle_dir)
    if bundle is None:
        return code
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
            print(json.dumps(obj, indent=1, ensure_ascii=False))
            return EXIT_OK
    _err(f"No {args.kind} with id {args.id!r} in this bundle.")
    return EXIT_NOT_FOUND


def cmd_bundle_check(args) -> int:
    from . import bundle as B

    path = B.bundle_path(Path(args.bundle_dir).expanduser())
    if not path.is_file():
        _err(f"No bundle.json at {args.bundle_dir}.")
        return EXIT_NOT_FOUND
    errors = B.check_bundle(path)
    if errors:
        print(f"INVALID: the bundle does not meet {B.FORMAT_ID} {B.FORMAT_VERSION} ({len(errors)} error(s) shown):")
        for e in errors:
            print(f"  - {e}")
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
        payload = Q.consolidate(bundle)
        rows = Q.filter_questions(payload, scope=args.scope, blocking_only=args.blocking_only)
        page = rows[args.offset : args.offset + args.limit]
        # HINTS SHOW PARSER LITERALS: that is an exposure, recorded before printing.
        shown = [("candidate", h["candidate_id"]) for q in page for h in q["hints"] if h.get("candidate_id")]
        shown += [("conflict", q["targets"][0]["id"]) for q in page if q["kind"] == "resolve_conflict"]
        if shown:
            M.expose_and_load(Path(args.bundle_dir), shown, "bundle questions")
        return {
            "format": payload["format"], "format_version": payload["format_version"],
            "blocking_basis": payload["blocking_basis"], "counts": payload["counts"],
            "total": len(rows), "offset": args.offset, "limit": args.limit, "returned": len(page),
            "omitted_before": min(args.offset, len(rows)),
            "omitted_after": max(0, len(rows) - args.offset - len(page)),
            "minimum_for_one_group": Q.minimum_answers_for_one_group(payload, bundle),
            "questions": page,
        }

    return _mutation(run)


def _positions(raw: str | None):
    from . import mutations as M

    if raw is None:
        return None
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError as exc:
        raise M.MutationRefused("--positions must be whole numbers separated by commas, e.g. 2,3.") from exc


def cmd_bundle_decide(args) -> int:
    from . import mutations as M

    def run():
        try:
            split = json.loads(args.split_into) if args.split_into else None
        except ValueError as exc:
            raise M.MutationRefused(f"--split-into is not valid JSON: {exc}") from exc
        targets = _targets_from(args)
        if args.question:
            from . import questions as Q

            found = Q.targets_for(Q.consolidate(M.load(Path(args.bundle_dir))), args.question, args.only, args.field)
            if not found:
                raise M.MutationRefused(f"No open question {args.question!r}" + (f" for {args.only}" if args.only else "") + ".", code=6)
            targets.extend(found)
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
            positions=_positions(args.positions),
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


def cmd_bundle_build_records(args) -> int:
    from . import records as R

    return _mutation(lambda: R.build_records(Path(args.bundle_dir), test_marker=args.test_marker))


def cmd_bundle_validate(args) -> int:
    """Exit 0 only when EVERY draft is exportable; 1 otherwise (each verdict printed)."""
    from . import records as R

    holder: dict = {}

    def run():
        holder["r"] = R.validate_records(Path(args.bundle_dir))
        return holder["r"]

    code = _mutation(run)
    if code == EXIT_OK and any(v != "exportable" for v in holder["r"]["verdicts"].values()):
        return EXIT_INVALID
    return code


def cmd_bundle_export(args) -> int:
    """Exit 0 only when nothing was refused; 1 when any draft was not exported."""
    from . import records as R

    holder: dict = {}

    def run():
        holder["r"] = R.export_records(Path(args.bundle_dir), Path(args.out))
        return holder["r"]

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
    q.add_argument("--state", help="candidates only: filter by value_state")
    q.add_argument("--no-values", action="store_true", help="candidates only: omit parser values (records no exposure)")
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
    q.add_argument("--target", required=True)
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
    q.add_argument("--decision", required=True)
    q.add_argument("--value")
    q.add_argument("--json", action="store_true", help="parse --value as JSON")
    q.add_argument("--by", required=True)
    q.add_argument("--orcid")
    q.add_argument("--note")
    q.add_argument("--split-into", help="record groups: JSON list of lists of run keys")
    q.add_argument("--merge-with", nargs="*", help="record groups: group ids to merge with")
    q.add_argument("--qc-status", help="processing result + approve: measurement.qc.status, from the pinned vocabulary")
    q.add_argument("--qc-note", help="with --qc-status: what is compromised or failed, and why")
    q.add_argument("--element", help="record group + approve_calibration: the absorbing element (e.g. Ir)")
    q.add_argument("--edge", help="record group + approve_calibration: the edge (K, L1-L3, M1-M5)")
    q.add_argument("--positions", help="--target experiment + set_counter_positions: filename token positions, e.g. 2 or 2,3")
    q.set_defaults(func=cmd_bundle_decide)

    q = bsub.add_parser("questions", help="consolidated questions: asked once, at the right scope, blocking first")
    q.add_argument("bundle_dir")
    q.add_argument("--scope", help="experiment | group:<id> | run:<id>")
    q.add_argument("--blocking-only", action="store_true")
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

    q = bsub.add_parser("group", help="propose record groups (one record = one sample, technique, set of conditions)")
    q.add_argument("bundle_dir")
    q.add_argument("--regroup", action="store_true", help="replace undecided groups; decided ones are kept")
    q.set_defaults(func=cmd_bundle_group)

    q = bsub.add_parser("build-records", help="compose one ISAAC draft per confirmed record group")
    q.add_argument("bundle_dir")
    q.add_argument("--test-marker", action="store_true", help="SELF-TESTS ONLY: write the fixed self-test marker into the series and QC notes")
    q.set_defaults(func=cmd_bundle_build_records)

    q = bsub.add_parser("validate", help="validate drafts: draft, export dry-run, official, exactness, offline portal")
    q.add_argument("bundle_dir")
    q.set_defaults(func=cmd_bundle_validate)

    q = bsub.add_parser("export", help="write official records that pass every gate")
    q.add_argument("bundle_dir")
    q.add_argument("--out", required=True)
    q.set_defaults(func=cmd_bundle_export)

    q = bsub.add_parser("upload", help="DRY RUN ONLY: what would be sent to the portal")
    q.add_argument("records_dir")
    q.add_argument("--dry-run", action="store_true")
    q.add_argument("--portal-url")
    q.set_defaults(func=cmd_bundle_upload)
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
