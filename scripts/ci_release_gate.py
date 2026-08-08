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

#: The workflow whose success is required before anything may be published.
#: This is the ``name:`` field of ``.github/workflows/ci.yml``, not its filename.
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
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise GateRefusal("the Actions API response had no workflow_runs list, so CI status is unknown")
    return runs


def _relevant(runs: Iterable[dict[str, Any]], sha: str) -> list[dict[str, Any]]:
    """Runs of the required workflow, for this exact commit, on the release branch.

    Every filter here is a way the gate could otherwise be fooled, so each is
    checked rather than assumed: the API is asked for one ``head_sha`` but the
    answer is re-checked, because trusting a query parameter to have been honoured
    is the same class of mistake as trusting CI to have run.
    """
    kept = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("name") != REQUIRED_WORKFLOW_NAME:
            continue
        if run.get("head_sha") != sha:
            continue
        if run.get("head_branch") != RELEASE_BRANCH:
            continue
        if run.get("event") not in RELEASE_EVENTS:
            continue
        kept.append(run)
    return kept


def _latest_attempt(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """The most recent attempt wins, so a rerun-to-green can authorise a publish.

    That is deliberate and is the one direction the gate is permissive in: a red
    run that a human reruns successfully *is* a commit whose required CI has
    concluded successfully. What the old pipeline did — publish while CI was still
    running — is a different thing entirely, and stays refused.
    """

    def sort_key(run: dict[str, Any]) -> tuple[int, str]:
        attempt = run.get("run_attempt")
        return (attempt if isinstance(attempt, int) else 0, str(run.get("updated_at") or ""))

    return sorted(runs, key=sort_key)[-1]


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

    fetch = fetcher or (lambda: _fetch_runs(repo, sha, token, api_root=api_root))
    try:
        runs = fetch()
    except GateRefusal as exc:
        return Decision(False, sha, str(exc))

    candidates = _relevant(runs, sha)
    if not candidates:
        return Decision(
            False,
            sha,
            f"no completed {REQUIRED_WORKFLOW_NAME!r} run exists for this commit on {RELEASE_BRANCH!r} "
            "— absence of a result is refusal, not permission",
        )

    run = _latest_attempt(candidates)
    status = run.get("status")
    conclusion = run.get("conclusion")

    if status != "completed":
        return Decision(
            False,
            sha,
            f"the required {REQUIRED_WORKFLOW_NAME!r} run is {status!r}, not finished — "
            "publishing before CI finishes is the exact defect this gate exists to stop",
        )
    if conclusion != "success":
        return Decision(
            False,
            sha,
            f"the required {REQUIRED_WORKFLOW_NAME!r} run concluded {conclusion!r}, not 'success'",
        )

    attempt = run.get("run_attempt", 1)
    return Decision(
        True,
        sha,
        f"the required {REQUIRED_WORKFLOW_NAME!r} run (attempt {attempt}) concluded 'success' for this commit",
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
