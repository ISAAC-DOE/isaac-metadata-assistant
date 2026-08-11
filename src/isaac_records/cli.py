"""The `isaac` CLI: validate | export | audit | new-id.

Deterministic and LLM-free. `export` transforms a draft into an official record
plus an evidence sidecar, gated by both no-guessing checks and the official schema.
The knowledge graph is never touched here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit_records, render_audit
from .draft_validator import validate_draft
from .exactness import EXACTNESS_HEADING, check_exactness
from .export import export_draft
from .ids import new_record_id
from .official import validate_official
from .portal_warnings import portal_warnings


def find_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return cwd


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _looks_like_draft(obj: dict) -> bool:
    return "meta" in obj or "fields" in obj


def cmd_validate(args, root: Path) -> int:
    obj = _load(Path(args.target))
    as_draft = args.draft or (not args.official and _looks_like_draft(obj))
    if as_draft:
        report = validate_draft(obj)
        print("Draft validation (no-guessing checks):")
        print(report.render())
        if args.warnings:
            print("\n(Advisory portal warnings apply to official records — use --official --warnings.)")
        return 0 if report.ok else 1
    report = validate_official(obj, root)
    print(report.render())
    # EXACTNESS — a HARD gate, printed after the schema verdict and folded into the exit
    # code, unlike the advisory warnings below.
    #
    # It is reported SEPARATELY, and not merged into the schema report, because it is not
    # a schema error: the vendored schema, read as written, accepts these values. Printing
    # it under "valid against official ISAAC schema v1.05" would attribute a local ISAAC
    # policy to upstream. Keeping the two verdicts visibly distinct is what lets a reader
    # tell "your record breaks the official schema" from "your record passes the official
    # schema only through a regex-flavour accident, and ISAAC will not export it".
    #
    # It DOES gate the exit code: `isaac validate --official` is what `CLAUDE.md` §1 tells
    # a user to run, so a value `isaac export` would refuse must not be reported here as a
    # clean PASS. Exiting 0 on a record that cannot be exported is the contradiction this
    # closes.
    exactness = check_exactness(obj, root)
    if not exactness.ok:
        print()
        print(EXACTNESS_HEADING)
        print(exactness.render())
    if args.warnings:
        # Advisory only: printed AFTER the hard official report and NEVER folded into the
        # exit code below, so warnings can never gate validation or export.
        print()
        print(portal_warnings(obj).render())
    # `and exactness.ok` — the ONLY non-schema input to this exit code, and deliberately
    # not `portal_warnings`, which stays advisory. See the block above for why a hard gate
    # that blocks export must also fail the command a user runs to ask "will this export?".
    return 0 if (report.ok and exactness.ok) else 1


def cmd_export(args, root: Path) -> int:
    draft = _load(Path(args.draft))
    result = export_draft(draft, root, record_id=args.record_id)
    if not result.ok:
        if not result.draft_report.ok:
            print("Draft validation failed — nothing exported:")
            print(result.draft_report.render())
        if result.official_report is not None and not result.official_report.ok:
            print("Transformed record fails the official schema — nothing exported:")
            print(result.official_report.render())
        return 1

    records_dir = Path(args.records_dir) if args.records_dir else root / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    rid = result.record["record_id"]
    record_path = records_dir / f"{rid}.json"
    sidecar_path = records_dir / f"{rid}.evidence.json"
    if record_path.exists():
        print(f"Export blocked: {record_path} already exists (records are immutable via the CLI).")
        return 1
    record_path.write_text(json.dumps(result.record, indent=2) + "\n", encoding="utf-8")
    sidecar_path.write_text(json.dumps(result.sidecar, indent=2) + "\n", encoding="utf-8")
    print(result.official_report.render())
    print(f"\nExported record  → {record_path}")
    print(f"Evidence sidecar → {sidecar_path}")
    if result.draft_report.warnings:
        print("\nWarnings:")
        print(result.draft_report.render())
    return 0


def cmd_audit(args, root: Path) -> int:
    records_dir = Path(args.records_dir) if args.records_dir else root / "records"
    results = audit_records(records_dir, root)
    print(render_audit(results))
    return 0 if all(r.ok for _, r, _ in results) else 1


def cmd_new_id(args, root: Path) -> int:
    print(new_record_id())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="isaac", description=__doc__)
    parser.add_argument("--root", help="repo root (default: walk up from cwd to find schema/)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate a draft (no-guessing) or a record (official schema)")
    p.add_argument("target")
    p.add_argument("--draft", action="store_true", help="force draft validation")
    p.add_argument("--official", action="store_true", help="force official-schema validation")
    p.add_argument(
        "--warnings",
        action="store_true",
        help="also print non-gating advisory portal-style soft-warnings (official records)",
    )
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("export", help="transform a draft into an official record + evidence sidecar")
    p.add_argument("draft")
    p.add_argument("--records-dir")
    p.add_argument("--record-id", help="use this ULID instead of generating one")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("audit", help="validate every record in records/ against the official schema")
    p.add_argument("--records-dir")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("new-id", help="print a fresh ULID record_id")
    p.set_defaults(func=cmd_new_id)

    args = parser.parse_args(argv)
    root = find_root(args.root)
    if args.command != "new-id" and not (root / "schema" / "isaac_record_v1.json").exists():
        print(f"No official schema at {root}/schema/isaac_record_v1.json (use --root).", file=sys.stderr)
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
