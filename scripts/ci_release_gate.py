#!/usr/bin/env python3
"""The required-CI gate that stands between a commit and a published image.

Why this file exists, stated plainly so a future session does not undo it:

Until 2026-08-08, `.github/workflows/build-push.yaml` triggered on `push: main`
and `.github/workflows/ci.yml` triggered on `push: main`, independently. They are
separate workflow files, so `needs:` — which only orders jobs *within one
workflow* — could not connect them. The two ran concurrently, and the publish
decision was made with no knowledge of CI at all.

That is not a theoretical hole. On commit 23ce90f the GHCR image finished
publishing at 08:19:17 while CI attempt 1 was still running; CI attempt 1 then
concluded `failure` at 08:52:37. The image had been public for 33 minutes before
the red result existed. A later rerun went green, which is irrelevant: nothing in
the pipeline had ever consulted CI.

The invariant this script enforces:

    No production/deployable image may be published from a commit whose required
    CI gate has not completed successfully.

The decision lives here, in Python, rather than in a YAML `if:` expression, for
one reason: a YAML expression cannot be given a failing input and observed to
refuse. This can, and `apps/api/tests/test_release_gate.py` does exactly that —
a negative control (red CI must refuse to publish) and a positive control (green
CI must still publish). A gate nobody has watched refuse is not a gate.

Fail-closed is the whole design. Every path that is not an affirmative,
unambiguous "the required workflow concluded success for exactly this commit"
returns a refusal: no CI run found, run still in progress, wrong branch, a run
that belongs to a pull_request rather than the push to main, ambiguous or
malformed API output. Absence of evidence is refusal, never permission.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

#: The workflow whose success is required before anything may be published,
#: identified by its FILE PATH.
#:
#: It used to be identified by display ``name:``, which is mutable and not
#: unique. Two failure directions followed from that, and an adversarial review
#: demonstrated both against this module: rename ``ci.yml``'s ``name:`` and every
#: release silently stops; add any second workflow also displaying as ``CI`` and
#: it becomes an alternate authority whose green can authorise a publish while
#: the real CI is red.
REQUIRED_WORKFLOW_PATH = ".github/workflows/ci.yml"

#: Kept only so failure messages name something a human recognises. It is NOT
#: what the gate matches on. ``test_release_gate.py`` pins it to ``ci.yml``'s
#: actual ``name:`` so the two cannot drift into a misleading message.
REQUIRED_WORKFLOW_NAME = "CI"

#: The only branch a deployable image may be built from.
RELEASE_BRANCH = "main"

#: The only ``event`` that counts. A ``pull_request`` run of CI is green against a
#: *merge preview* commit that no one is releasing, so accepting it would let a
#: green PR check authorise publishing a different tree.
RELEASE_EVENTS = ("push",)


class GateRefusal(Exception):
    """The gate refuses to authorise a publish. The message is the reason."""


@dataclass(frozen=True)
class Decision:
    """The gate's answer, and the sentence a human should read."""

    allowed: bool
    sha: str
    reason: str

    def render(self) -> str:
        verdict = "ALLOWED" if self.allowed else "REFUSED"
        return f"release gate {verdict} for {self.sha or '<unknown commit>'}: {self.reason}"


def _looks_like_sha(value: Any) -> bool:
    """A full 40-hex commit sha, and nothing looser.

    Short shas are rejected on purpose: the gate matches a CI run to a commit by
    string equality, and a prefix match would let a run for one commit authorise
    a different one.
    """
    return isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdef" for c in value.lower())


def _fetch_runs(repo: str, sha: str, token: str | None, *, api_root: str) -> list[dict[str, Any]]:
    """Every completed Actions run recorded against exactly this commit."""
    url = f"{api_root}/repos/{repo}/actions/runs?head_sha={sha}&per_page=100"
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed API host
            payload = json.load(response)
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised via injected fetcher
        raise GateRefusal(f"the Actions API returned HTTP {exc.code}, so CI status is unknown") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - exercised via injected fetcher
        raise GateRefusal(f"the Actions API was unreachable ({exc.reason}), so CI status is unknown") from exc
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001 - deliberately broad; see below
        # A read timeout raises TimeoutError and a non-JSON error page raises
        # JSONDecodeError, neither of which is a URLError. Uncaught, those left
        # the process on a traceback — still a non-zero exit, so still fail-closed,
        # but fail-closed BY ACCIDENT rather than by design, and printing a stack
        # trace where the docstring promised a refusal with a reason. Anything
        # that goes wrong reaching the API means CI status is unknown, and
        # unknown is refusal.
        raise GateRefusal(
            f"the Actions API could not be read ({type(exc).__name__}: {exc}), so CI status is unknown"
        ) from exc
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise GateRefusal("the Actions API response had no workflow_runs list, so CI status is unknown")
    return runs


def _relevant(runs: Iterable[dict[str, Any]], sha: str, repo: str) -> list[dict[str, Any]]:
    """Runs of the required workflow, for this exact commit, on the release branch.

    Every filter here is a way the gate could otherwise be fooled, so each is
    checked rather than assumed: the API is asked for one ``head_sha`` but the
    answer is re-checked, because trusting a query parameter to have been honoured
    is the same class of mistake as trusting CI to have run.

    ``head_repository`` is the one that is easy to leave out and expensive to
    omit. A pull request opened from a FORK produces a run recorded in THIS
    repository whose ``head_branch`` is the fork's branch name — and a fork's
    default branch is ``main``. Without this check, a stranger's green run on
    their own ``main`` satisfies every other filter here.
    """
    kept = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("path") != REQUIRED_WORKFLOW_PATH:
            continue
        if str(run.get("head_sha") or "").lower() != sha:
            continue
        if run.get("head_branch") != RELEASE_BRANCH:
            continue
        if run.get("event") not in RELEASE_EVENTS:
            continue
        head_repo = run.get("head_repository")
        if not isinstance(head_repo, dict) or head_repo.get("full_name") != repo:
            continue
        kept.append(run)
    return kept


def _all_succeeded(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The run to report on if every relevant run is green, else the offender.

    Returns ``None`` when all are green; otherwise returns the first run that is
    not, so the caller can name it.

    **This used to pick a single "latest attempt" and judge only that**, ordering
    by ``run_attempt`` — which is a number that only means anything WITHIN one
    run id. An adversarial review showed the consequence: a stale run sitting at
    attempt 3 outranked a newer run at attempt 1, so a green from the morning
    could authorise a publish while the most recent CI verdict for that same
    commit was ``failure``. Reachable by a force-push of ``main`` back onto a
    commit, or a revert-and-re-merge of the same tree.

    Requiring *all* of them removes the ordering question entirely, which is
    better than getting the ordering right: there is no comparison left to get
    wrong. It is also the honest reading of the invariant — if any completed CI
    verdict for this commit says failure, the commit does not have a clean
    required-CI result.

    Note the API returns ONE record per run, reflecting that run's latest
    attempt. So a rerun-to-green updates the existing record rather than adding
    one, and the ordinary case here is a list of length 1.
    """
    for run in runs:
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            return run
    return None


def evaluate(
    *,
    repo: str,
    sha: str,
    token: str | None = None,
    fetcher: Any = None,
    api_root: str = "https://api.github.com",
) -> Decision:
    """Decide whether ``sha`` may be published. Never raises for a normal refusal.

    ``fetcher`` exists so the controls in the test suite can hand this function a
    red CI world and a green CI world without touching the network.
    """
    if not repo or "/" not in repo:
        return Decision(False, sha, "no repository was supplied, so CI status could not be checked")
    if not _looks_like_sha(sha):
        return Decision(False, str(sha or ""), "no full 40-character commit sha was supplied to check CI against")

    # Compared case-insensitively against the API's value below, so normalise
    # once here. `_looks_like_sha` accepts uppercase; without this an uppercase
    # input matched nothing and became the indistinguishable "no CI run found".
    sha = sha.lower()

    fetch = fetcher or (lambda: _fetch_runs(repo, sha, token, api_root=api_root))
    try:
        runs = fetch()
    except GateRefusal as exc:
        return Decision(False, sha, str(exc))

    candidates = _relevant(runs, sha, repo)
    if not candidates:
        return Decision(
            False,
            sha,
            f"no completed {REQUIRED_WORKFLOW_PATH!r} run exists for this commit on {RELEASE_BRANCH!r} "
            f"in {repo!r} — absence of a result is refusal, not permission",
        )

    offender = _all_succeeded(candidates)
    if offender is not None:
        status = offender.get("status")
        if status != "completed":
            return Decision(
                False,
                sha,
                f"a required {REQUIRED_WORKFLOW_NAME!r} run for this commit is {status!r}, not finished "
                "— publishing before CI finishes is the exact defect this gate exists to stop",
            )
        return Decision(
            False,
            sha,
            f"a required {REQUIRED_WORKFLOW_NAME!r} run for this commit concluded "
            f"{offender.get('conclusion')!r}, not 'success'",
        )

    return Decision(
        True,
        sha,
        f"all {len(candidates)} required {REQUIRED_WORKFLOW_NAME!r} run(s) for this commit "
        "concluded 'success'",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/name")
    parser.add_argument("--sha", default="", help="the full 40-char commit sha under release")
    args = parser.parse_args(argv)

    decision = evaluate(repo=args.repo, sha=args.sha, token=os.environ.get("GITHUB_TOKEN") or None)
    print(decision.render(), file=sys.stderr)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        try:
            with open(step_summary, "a", encoding="utf-8") as handle:
                handle.write(f"### Release gate\n\n{decision.render()}\n")
        except OSError:
            pass

    return 0 if decision.allowed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
