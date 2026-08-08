#!/usr/bin/env python3
"""Turn measured axe runs into `a11y-baseline.ts` entries, without hand-transcribing.

WHY THIS EXISTS
===============

`apps/web/e2e/a11y-baseline.ts` records, per axe rule, the exact node count each
`(surface, project, platform)` triple is known to produce. When a new sweep is
added, every pair it scans is unbaselined, so every violation reads as `new` and
the suite fails with a line telling you what to add. Adding those lines by hand
is where this project has been bitten before: a transcription pass once wrote a
laptop reading into a file whose numbers must come from CI, and the error is
invisible until someone runs the suite on the other platform.

So the numbers are read out of the runs mechanically. Nobody retypes a count.

THE CONSTRAINT THAT MAKES THIS TWO-SOURCED, WHICH IS EASY TO MISS
=================================================================

`PlatformCount` (`a11y-baseline.ts:173`) is::

    number | Readonly<Record<'darwin' | 'linux', number>>

and the file says explicitly that there is no third form -- "no range, no
tolerance and no 'unknown'; a platform with no measurement is a platform this
file cannot speak for."

That has a consequence which is not obvious and which defeats the natural
approach. **A bare number is not "the number"; it is the claim that both
platforms measured the same thing.** So a CI log alone -- which is linux only --
cannot honestly produce either encoding. Writing a bare number from it asserts a
darwin measurement that was never taken.

This is not hypothetical. Of 20 pairs measured on darwin during the narrow-sweep
investigation, **2 already disagreed with linux**: `settings-explorer@width-390`
(darwin 58, linux 56) and `load@width-390` color-contrast (darwin 1, linux 2).
A bare-number ingestion would have written both wrong.

Hence: two inputs, merged. Equal on both platforms -> a bare number. Different ->
the explicit object. Present in only one -> **refused**, loudly, with the missing
run named. Refusing is the whole point; a tool that guesses the other platform
would reintroduce by automation exactly the defect that manual transcription
caused.

USAGE
=====

Collect both measurements, then merge::

    # linux, authoritative -- from the CI job on the exact commit
    gh run view <run-id> --log-failed > /tmp/a11y-linux.log

    # darwin -- from a local run of the same commit
    cd apps/web && npx playwright test e2e/specs/a11y-narrow.spec.ts \\
        --project=desktop-1280x800 > /tmp/a11y-darwin.log 2>&1

    python scripts/ingest_a11y_baseline.py \\
        --linux /tmp/a11y-linux.log --darwin /tmp/a11y-darwin.log

It prints entries grouped by axe rule, ready to paste into the matching
`A11Y_BASELINE` entry. It deliberately does **not** edit the TypeScript itself:
each entry in that file carries a prose note explaining the defect it records,
and a machine cannot write that note. The numbers are mechanical; the
explanation is not, and a baseline entry without one is how debt becomes
permanent.

Pass `--linux` alone to see what CI measured -- it will report every pair as
missing its darwin half rather than emitting anything paste-ready.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

#: The failure line the suite prints for an unbaselined pair. Matching the
#: MESSAGE rather than parsing a report format keeps this in step with the suite:
#: if the wording changes, this stops matching and says so, instead of silently
#: reading zero findings and reporting a clean run.
FINDING = re.compile(
    r"NEW\s+(?P<surface>[\w-]+) @ (?P<project>[\w-]+) on (?P<platform>\w+): "
    r'rule "(?P<rule>[\w-]+)" is not baselined here at all, and fired on (?P<nodes>\d+) node'
)


class IngestError(Exception):
    """Something about the inputs makes a truthful baseline impossible."""


def parse(text: str, *, expect_platform: str, source: str) -> dict[tuple[str, str, str], int]:
    """Every `(rule, surface, project) -> node count` the log reports.

    A pair reported twice with the SAME count is normal: the suite prints the
    failure once per assertion. Reported twice with DIFFERENT counts is not, and
    raises -- that would mean the run was not deterministic, and a baseline built
    from a non-deterministic run is worse than none.
    """
    found: dict[tuple[str, str, str], int] = {}
    saw_platform: set[str] = set()

    for match in FINDING.finditer(text):
        platform = match.group("platform")
        saw_platform.add(platform)
        if platform != expect_platform:
            raise IngestError(
                f"{source} reports a finding on platform {platform!r}, but was passed as the "
                f"{expect_platform!r} run. Mixing the columns is the exact error this tool exists "
                f"to prevent, so nothing is emitted."
            )
        key = (match.group("rule"), match.group("surface"), match.group("project"))
        nodes = int(match.group("nodes"))
        if key in found and found[key] != nodes:
            raise IngestError(
                f"{source} reports {key} as both {found[key]} and {nodes} nodes. The run was not "
                f"deterministic; a baseline built from it would encode noise."
            )
        found[key] = nodes

    if not found:
        raise IngestError(
            f"{source} contains no recognisable findings. Either the run had none (in which case "
            f"there is nothing to baseline and the suite should already be green), or the suite's "
            f"failure message changed and this parser is now out of step with it. Both are worth "
            f"looking at before trusting an empty result."
        )
    return found


def render(counts: Iterable[tuple[tuple[str, str, str], int, int]]) -> str:
    """Group into paste-ready blocks, one per axe rule."""
    by_rule: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for (rule, surface, project), darwin, linux in counts:
        by_rule[rule].append((f"{surface}@{project}", darwin, linux))

    out: list[str] = []
    for rule in sorted(by_rule):
        pairs = sorted(by_rule[rule])
        agreeing = sum(1 for _, d, l in pairs if d == l)
        out.append(f"/* --- rule: {rule} --- {len(pairs)} pair(s), {len(pairs) - agreeing} platform-split */")
        for key, darwin, linux in pairs:
            if darwin == linux:
                out.append(f"  '{key}': {linux},")
            else:
                out.append(f"  '{key}': {{ darwin: {darwin}, linux: {linux} }},")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--linux", type=Path, required=True, help="log from the linux CI job (authoritative)")
    parser.add_argument("--darwin", type=Path, help="log from a local darwin run of the SAME commit")
    args = parser.parse_args(argv)

    try:
        linux = parse(args.linux.read_text(errors="replace"), expect_platform="linux", source=str(args.linux))
        darwin = (
            parse(args.darwin.read_text(errors="replace"), expect_platform="darwin", source=str(args.darwin))
            if args.darwin
            else {}
        )
    except (IngestError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    only_linux = sorted(set(linux) - set(darwin))
    only_darwin = sorted(set(darwin) - set(linux))

    print(f"linux findings:  {len(linux)}", file=sys.stderr)
    print(f"darwin findings: {len(darwin)}", file=sys.stderr)

    if only_darwin:
        print(
            f"\n{len(only_darwin)} pair(s) fired on darwin but NOT on linux. That is a real "
            f"difference and each needs a linux number before it can be written:",
            file=sys.stderr,
        )
        for key in only_darwin:
            print(f"  {key}", file=sys.stderr)

    if only_linux:
        print(
            f"\nREFUSING to emit {len(only_linux)} pair(s): measured on linux, not on darwin.\n"
            f"A bare number in a11y-baseline.ts asserts that BOTH platforms measured it, and no "
            f"darwin measurement exists for these. Run the same commit locally and pass --darwin.",
            file=sys.stderr,
        )
        for key in only_linux:
            print(f"  {key}  (linux: {linux[key]})", file=sys.stderr)

    both = sorted(set(linux) & set(darwin))
    if not both:
        print("\nNothing can be emitted truthfully from these inputs.", file=sys.stderr)
        return 1

    split = sum(1 for k in both if linux[k] != darwin[k])
    print(
        f"\nemitting {len(both)} pair(s); {split} differ between platforms and get the object form",
        file=sys.stderr,
    )
    print()
    print(render((k, darwin[k], linux[k]) for k in both))
    print(
        "# Paste each block into the matching A11Y_BASELINE entry, and WRITE THE NOTE.\n"
        "# An entry without a note explaining the defect is how debt becomes permanent.",
    )
    return 0 if not only_linux else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
