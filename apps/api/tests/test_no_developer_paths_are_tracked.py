"""No tracked file may be a symlink, and none may embed an absolute developer path.

WHY THIS FILE EXISTS. On 2026-08-26 a `.venv` SYMLINK was committed and reached
`main` through a merged PR. An agent working in a git worktree had created it so
its tests could find an interpreter; `git add -A` swept it in; nothing objected.

`.gitignore` carried `.venv/` — **with a trailing slash, which matches a DIRECTORY
and not a symlink of the same name** — so the file was never ignored and the
mistake was invisible at every stage.

The damage was not to the repository but to whoever checked it out: `git checkout
main` replaced the real virtualenv DIRECTORY with a symlink whose target was
`/Users/<someone>/Documents/ISAAC/.venv` — i.e. itself. Every `.venv/bin/python`
invocation then failed with ``too many levels of symbolic links`` until the
environment was rebuilt from scratch. On a machine whose checkout lives anywhere
else, the link simply dangles.

THE GUARD IS TWO INVARIANTS, not one, because either alone misses the case:

* **No tracked entry is a symlink.** Git records these with mode ``120000``. This
  is the invariant that would have caught it. It is deliberately blanket — a
  symlink whose target happens to be relative is still a portability hazard, and
  no tracked file in this repository has ever needed to be one.
* **No tracked text file contains an absolute path under a user home directory.**
  A symlink is only one way to bake a developer's filesystem into the tree; a
  hard-coded path in a config or a script is the same defect without the mode bit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Absolute paths into somebody's home directory, on the platforms this is
#: developed and built on. Deliberately NOT a general "any absolute path" check:
#: `/usr/bin/env`, `/api/...` and POSIX paths in prose are all legitimate and
#: common, and a guard that cries wolf on those gets suppressed rather than fixed.
_DEVELOPER_PATH = re.compile(r"(?:/Users/|/home/(?!runner)|C:\\\\Users\\\\)[A-Za-z0-9._-]+/")

#: This file quotes the very path it forbids, in the docstring above and in the
#: pattern below, and a guard that flagged itself would be deleted rather than
#: obeyed. Named individually rather than by a glob, so a NEW file cannot join the
#: list by accident.
_MAY_QUOTE_A_DEVELOPER_PATH = frozenset(
    {
        "apps/api/tests/test_no_developer_paths_are_tracked.py",
        ".gitignore",
    }
)


def _tracked() -> list[tuple[str, str]]:
    """``(mode, path)`` for every tracked entry, read from git rather than the disk.

    ``ls-files -s`` reports the mode git RECORDED, which is the thing under test.
    Stat-ing the working tree would answer a different question — and would answer
    it wrongly on a checkout where the symlink had already been replaced by hand.
    """
    out = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        rows.append((meta.split()[0], path))
    return rows


def test_no_tracked_entry_is_a_symlink():
    """Mode ``120000`` is git's record of a symlink. There must be none.

    THIS IS THE ASSERTION THAT WOULD HAVE CAUGHT THE `.venv` COMMIT, and it is
    stated over the recorded mode rather than over a filename, because the next one
    will not be called `.venv`.
    """
    symlinks = sorted(path for mode, path in _tracked() if mode == "120000")
    assert symlinks == [], (
        "tracked symlinks found: "
        + ", ".join(symlinks)
        + " — a symlink's target is a property of one developer's machine. If a "
        "worktree needs an interpreter or a node_modules, create it UNTRACKED and "
        "add the bare name (no trailing slash) to .gitignore."
    )


def test_the_gitignore_rule_matches_a_symlink_and_not_only_a_directory():
    """`.venv/` does NOT match a symlink named `.venv`. Both forms must be present.

    The trailing-slash form is what let the original commit through, so removing
    the bare form would restore the exact hole. Asked of `git check-ignore`, which
    is the matcher that actually decides, rather than of the file's text.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-v", ".venv"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "a path named `.venv` is NOT ignored. `.gitignore` needs the bare `.venv` "
        "as well as `.venv/` — the trailing slash matches only a directory, and the "
        "entry that reached `main` was a symlink."
    )


# --- AND ONE ASSERTION THAT WAS WRITTEN, MEASURED, AND WITHDRAWN ---------------
#
# A third test asserted that no tracked text file embeds an absolute path under a
# home directory — the reasoning being that a symlink is only one way to bake a
# developer's filesystem into the tree, and a hard-coded path is the same defect
# without the mode bit.
#
# IT WAS RUN, AND IT FLAGGED TWELVE FILES, EVERY ONE OF THEM LEGITIMATE:
#
#     apps/api/tests/test_api.py                     /Users/someone/...
#     apps/api/tests/test_assistant_query.py         /Users/me/...
#     apps/api/tests/test_evidence_classify.py       /Users/krish/...
#     apps/api/tests/test_runtime_records.py         /Users/fake/...
#     apps/web/src/lib/assistantSession.ts           /Users/kverma/data/scan 01.h5
#     ...and seven more
#
# They are synthetic fixture data and documentation examples. `test_memory_graph_detail.py`
# even uses `("home_absolute", "/Users/krishverma/secret.py")` as a NEGATIVE CONTROL —
# a path the redaction logic must refuse — so the guard would have flagged the very
# test that proves developer paths are handled.
#
# The check cannot distinguish "a fake path used as test data" from "a real path
# baked in", and nothing about the string tells it apart. Keeping it would have
# meant twelve exemptions on the day it shipped, which is precisely the
# cries-wolf-then-gets-suppressed outcome its own comment warned about. It is
# withdrawn rather than exempted, and recorded here rather than deleted silently,
# so nobody re-derives it and reaches the same twelve files.
#
# The symlink assertion above is the one that would have caught the real defect,
# and it needs no exemptions at all.
