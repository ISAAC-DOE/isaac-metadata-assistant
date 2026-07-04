"""The `isaac` CLI: validate | audit | export | required-fields.

Deterministic and LLM-free. Export never touches the knowledge graph —
graph refresh is a best-effort step in the /isaac-export skill layer, so
the core pipeline works with Graphify entirely absent.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .audit import audit_records, render_audit
from .validator import (
    iter_envelopes,
    load_schema,
    load_vocabularies,
    required_paths,
    validate_record,
)


def find_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "schema" / "isaac_record.schema.json").exists():
            return candidate
    return cwd


def _load_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence_summary(env: dict) -> str:
    entries = [e for e in (env.get("evidence") or []) if isinstance(e, dict)]
    if not entries:
        return "—"
    e = entries[0]
    kind = e.get("source_type", "?")
    if kind == "user_confirmation":
        detail = f"Q: {e.get('question', '')!s}"
    elif kind == "derivation":
        detail = f"rule: {e.get('rule', '')!s}"
    else:
        detail = f"{e.get('source_file', '')} → {e.get('locator', '')}"
    more = f" (+{len(entries) - 1} more)" if len(entries) > 1 else ""
    return f"{kind}: {detail}{more}"


def render_evidence_map(record: dict) -> str:
    rows = []
    for path, env in iter_envelopes(record):
        value = env.get("value")
        unit = env.get("unit")
        shown = "null" if value is None else str(value)
        if len(shown) > 40:
            shown = shown[:37] + "..."
        if unit:
            shown = f"{shown} {unit}"
        rows.append((path, shown, str(env.get("status")), _evidence_summary(env)))
    if not rows:
        return "No field envelopes found."
    widths = [max(len(r[i]) for r in rows + [("field", "value", "status", "evidence")]) for i in range(4)]
    header = ("field", "value", "status", "evidence")
    lines = [
        "  ".join(h.ljust(w) for h, w in zip(header, widths)),
        "  ".join("-" * w for w in widths),
    ]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in rows]
    return "\n".join(lines)


def cmd_validate(args, root: Path) -> int:
    schema = load_schema(root)
    vocabularies = load_vocabularies(root)
    record = _load_record(Path(args.record))
    report = validate_record(record, schema, vocabularies, finalize=args.finalize)
    print(report.render())
    if args.evidence:
        print()
        print(render_evidence_map(record))
    return 0 if report.ok else 1


def cmd_audit(args, root: Path) -> int:
    schema = load_schema(root)
    vocabularies = load_vocabularies(root)
    records_dir = Path(args.records_dir) if args.records_dir else root / "records"
    results = audit_records(records_dir, schema, vocabularies)
    print(render_audit(results))
    return 0 if all(r.ok for _, r in results) else 1


def cmd_export(args, root: Path) -> int:
    schema = load_schema(root)
    vocabularies = load_vocabularies(root)
    draft_path = Path(args.draft)
    record = _load_record(draft_path)
    report = validate_record(record, schema, vocabularies, finalize=True)
    if not report.ok:
        print(report.render())
        print(f"\nExport blocked: {len(report.errors)} validation error(s). Nothing was moved.")
        return 1

    records_dir = Path(args.records_dir) if args.records_dir else root / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    dest = records_dir / f"{record['record_id']}.json"
    if dest.exists():
        print(f"Export blocked: {dest} already exists. Records are immutable via the CLI — use a new record_id.")
        return 1
    shutil.move(str(draft_path), dest)
    print(report.render())
    print(f"\nExported → {dest}")
    print("Knowledge graph refresh is optional and never blocks export (see /isaac-export).")
    return 0


def cmd_required_fields(args, root: Path) -> int:
    schema = load_schema(root)
    paths = required_paths(schema, technique=args.technique)
    for path in paths:
        print(path)
    if not args.technique:
        techniques = sorted(schema.get("x-field-rules", {}).get("technique_requirements", {}))
        if techniques:
            print(f"\nTechnique-specific fields exist for: {', '.join(techniques)} (use --technique)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="isaac", description=__doc__)
    parser.add_argument("--root", help="repo root (default: walk up from cwd to find schema/)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate a record or draft")
    p.add_argument("record")
    p.add_argument("--finalize", action="store_true", help="apply the finalization rule (export-level strictness)")
    p.add_argument("--evidence", action="store_true", help="print the per-field evidence map")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("audit", help="finalization-level validation of every record in records/")
    p.add_argument("--records-dir")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("export", help="validate (blocking) then move a draft into records/")
    p.add_argument("draft")
    p.add_argument("--records-dir")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("required-fields", help="list required fields from the schema")
    p.add_argument("--technique")
    p.set_defaults(func=cmd_required_fields)

    args = parser.parse_args(argv)
    root = find_root(args.root)
    if not (root / "schema" / "isaac_record.schema.json").exists():
        print(f"No schema found at {root}/schema/isaac_record.schema.json (use --root).", file=sys.stderr)
        return 2
    try:
        return args.func(args, root)
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
