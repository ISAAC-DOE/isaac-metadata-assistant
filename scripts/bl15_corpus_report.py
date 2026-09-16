#!/usr/bin/env python3
"""Recompute every count in ``docs/evidence/bl15-2-corpus-characterization-2026-09-16.md``.

**Why this is a script and not a test.** CI has no corpus — the real BL15-2 archive is
real experimental data and is never committed (``CLAUDE.md`` §6). So the numbers in that
document cannot be guarded by a test; they can only be made re-derivable. This tool is
how a future reader checks them, against a folder they hold themselves.

It prints counts and structure. It prints no scientific value, no note text, and no file
contents. It writes nothing and opens no network.

    python3 scripts/bl15_corpus_report.py /path/to/extracted/corpus
"""

from __future__ import annotations

import collections
import hashlib
import os
import re
import sys

NUMBERED = re.compile(r"^\d+_")
NEWFILE = re.compile(r"^\s*newfile\s+(\S+)", re.MULTILINE)


def main(root: str) -> int:
    if not os.path.isdir(root):
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    all_files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        all_files.extend(os.path.join(dirpath, f) for f in filenames)

    by_ext: collections.Counter[str] = collections.Counter()
    for p in all_files:
        name = os.path.basename(p)
        by_ext["." + name.rsplit(".", 1)[1] if "." in name else "(none)"] += 1

    entries = sorted(os.listdir(root))
    top_files = [e for e in entries if os.path.isfile(os.path.join(root, e))]
    top_dirs = [e for e in entries if os.path.isdir(os.path.join(root, e))]
    scan_dirs = [d for d in top_dirs if d.endswith("_dir")]
    stems = {f for f in top_files if "." not in f}

    print("== inventory ==")
    print(f"files                       {len(all_files)}")
    print(f"directories                 {sum(1 for _ in os.walk(root)) - 1}")
    print(f"bytes                       {sum(os.path.getsize(p) for p in all_files)}")
    for ext, n in by_ext.most_common():
        print(f"  {ext:<24} {n}")

    print("\n== top level ==")
    print(f"files                       {len(top_files)}")
    print(f"directories                 {len(top_dirs)}")
    print(f"numbered extensionless      {sum(1 for f in top_files if NUMBERED.match(f) and '.' not in f)}")
    print(f"*_dir                       {len(scan_dirs)}")
    print(f"  with matching stem file   {sum(1 for d in scan_dirs if d[:-4] in stems)}")
    print(f"extensionless non-numbered  {sorted(s for s in stems if not NUMBERED.match(s))}")

    print("\n== scan directories ==")
    counts = {
        d: sum(1 for x in os.listdir(os.path.join(root, d)) if x.endswith(".dat"))
        for d in scan_dirs
    }
    print(f".dat inside *_dir           {sum(counts.values())}")
    if counts:
        print(f"per directory min/max       {min(counts.values())}/{max(counts.values())}")
    print(f"empty *_dir                 {sorted(d for d, c in counts.items() if c == 0)}")
    inner = collections.Counter()
    for d in scan_dirs:
        for x in os.listdir(os.path.join(root, d)):
            if not x.endswith(".dat"):
                inner["(none)" if "." not in x else "." + x.rsplit(".", 1)[1]] += 1
    print(f"non-.dat entries inside     {dict(inner)}")

    print("\n== duplicate content ==")
    digests: dict[str, list[str]] = collections.defaultdict(list)
    for p in all_files:
        with open(p, "rb") as fh:
            digests[hashlib.sha256(fh.read()).hexdigest()].append(
                os.path.relpath(p, root)
            )
    dups = {k: v for k, v in digests.items() if len(v) > 1}
    print(f"groups                      {len(dups)}")
    print(f"files involved              {sum(len(v) for v in dups.values())}")

    print("\n== macros ==")
    macro_paths = [
        os.path.join(root, f)
        for f in top_files
        if f.endswith(".mac") or _looks_like_macro(os.path.join(root, f))
    ]
    per_macro = {}
    targets: set[str] = set()
    for p in macro_paths:
        with open(p, errors="replace") as fh:
            text = fh.read()
        found = NEWFILE.findall(text)
        per_macro[os.path.basename(p)] = len(found)
        targets.update(found)
    print(f"macro files                 {len(macro_paths)}")
    print(f"newfile declarations        {sum(per_macro.values())}")
    if per_macro:
        print(f"per macro min/max           {min(per_macro.values())}/{max(per_macro.values())}")
    print(f"declaring more than one     {sum(1 for c in per_macro.values() if c > 1)}")
    print(f"declaring none              {sorted(f for f, c in per_macro.items() if c == 0)}")

    print("\n== SPEC acquisitions, content-led ==")
    spec = [f for f in sorted(stems) if _first_line_starts(os.path.join(root, f), "#F")]
    macros_without_extension = sorted(set(stems) - set(spec))
    print(f"SPEC acquisitions            {len(spec)}")
    print(f"  numbered ^\\d+_             {sum(1 for f in spec if NUMBERED.match(f))}")
    print(f"  unnumbered                 {[f for f in spec if not NUMBERED.match(f)]}")
    print(f"extensionless NON-acquisition {macros_without_extension}")

    by_number: dict[int, list[str]] = collections.defaultdict(list)
    for f in spec:
        if NUMBERED.match(f):
            by_number[int(f.split("_")[0])].append(f)
    dup = {k: v for k, v in by_number.items() if len(v) > 1}
    print(f"distinct legacy numbers      {len(by_number)}")
    if by_number:
        lo, hi = min(by_number), max(by_number)
        gaps = sorted(set(range(lo, hi + 1)) - set(by_number))
        print(f"  range                      {lo}-{hi}, gaps: {gaps or 'none'}")
    print(f"  carried by >1 file         {({k: v for k, v in dup.items()}) or 'none'}")

    groups: dict[str, list[int]] = collections.defaultdict(list)
    for f in spec:
        parts = f.split("_")
        if NUMBERED.match(f):
            key = parts[1] if len(parts) > 1 and parts[1].isdigit() else "(none)"
            groups[key].append(int(parts[0]))
    print(f"sample/electrode groups      {len(groups)}")
    for key in sorted(groups, key=lambda k: (k == "(none)", k)):
        v = sorted(groups[key])
        print(f"  token {key:>6}             {len(v):3d} measurements, legacy {min(v)}-{max(v)}")

    print("\n== internal #F vs external filename ==")
    # The conflict this corpus is most likely to be misread on. It is FOUR files, not
    # one: a single self-disagreeing file looks like a typo, four consecutive files in
    # one sample group making the identical substitution is a systematic rename.
    mismatched = []
    for f in spec:
        declared = _spec_file_declaration(os.path.join(root, f))
        if declared and declared != f:
            mismatched.append((f, declared))
    print(f"disagreeing                  {len(mismatched)}")
    for name, declared in mismatched:
        print(f"  file: {name}")
        print(f"  #F:   {declared}")

    print("\n== macro intent vs acquired ==")
    print(f"distinct newfile targets    {len(targets)}")
    print(f"declared, never acquired    {len(targets - stems)}")
    for t in sorted(targets - stems):
        print(f"  {t}")
    print(f"acquired, never declared    {len(stems - targets)}")
    for s in sorted(stems - targets):
        print(f"  {s}")
    return 0


def _first_line_starts(path: str, prefix: str) -> bool:
    try:
        with open(path, errors="replace") as fh:
            return fh.readline().startswith(prefix)
    except OSError:
        return False


def _spec_file_declaration(path: str) -> str | None:
    """The name a SPEC acquisition declares for ITSELF, on its ``#F`` line.

    Read rather than inferred, because it is the anchor for the corpus's
    external-name-versus-internal-declaration conflict. Nothing here reconciles the two.
    """
    try:
        with open(path, errors="replace") as fh:
            first = fh.readline().strip()
    except OSError:
        return None
    return first[2:].strip() if first.startswith("#F") else None


def _looks_like_macro(path: str) -> bool:
    """Content-led: an extensionless file whose first non-blank line is a macro command.

    ``run29`` in the real corpus has no extension and is a macro; ``alignment`` has no
    extension and is a SPEC acquisition. A name cannot tell them apart.
    """
    if "." in os.path.basename(path):
        return False
    try:
        with open(path, errors="replace") as fh:
            for _ in range(8):
                line = fh.readline()
                if not line:
                    return False
                if line.strip():
                    return line.split()[0] in {"qdo", "mv", "mvr", "newfile", "def"}
    except OSError:
        return False
    return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__ or "", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
