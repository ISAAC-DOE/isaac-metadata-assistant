"""Controls for the release gate: red CI must not be able to publish an image.

This file is the reason `scripts/ci_release_gate.py` is Python and not a YAML
`if:` expression. A YAML expression cannot be handed a failing world and watched
to refuse. These tests hand the gate a red world, a still-running world, an empty
world, a wrong-branch world, a pull_request world and a FORK world, and assert it
refuses each one — then hand it a green world and assert it still allows the
publish, so the gate is shown to be a gate rather than a wall.

The scenario the negative control encodes is a real one. Commit 23ce90f published
its GHCR image at 08:19:17 while CI attempt 1 was still running; that attempt
concluded `failure` at 08:52:37.

WHAT AN ADVERSARIAL REVIEW FOUND, AND WHY HALF THIS FILE EXISTS
===============================================================

The first version of this gate passed all of its own tests and was NOT SAFE. An
independent reviewer, given the brief "try to break it", found that the fix had
introduced a worse hole than the one it closed:

* **A fork PR could publish an arbitrary image.** `workflow_run`'s `branches:`
  filter matches the TRIGGERING run's `head_branch`, and for a pull request from
  a fork that is the fork's branch name — recorded in this repository. A fork's
  default branch is `main`. The gate job then checked out that commit and ran
  `scripts/ci_release_gate.py` FROM IT, with `packages: write`. The gate executed
  the attacker's copy of itself.
* **A stale green outranked a newer red**, because runs were ordered by
  `run_attempt`, a number that only means something within one run id.
* **The required workflow was matched by mutable display `name:`**, so any second
  workflow displaying as `CI` became an alternate authority.
* **Six mutations of the workflow passed all 22 tests**, three of them ungated
  publishes: a `run: docker buildx build --push`, an `outputs: type=registry`,
  and `push: "true"` as a string.

Every one of those now has a control below. The lesson worth keeping: the wiring
tests were written against the mechanisms the author had in mind, and an attacker
is not limited to those.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = REPO_ROOT / "scripts" / "ci_release_gate.py"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOW_PATH = WORKFLOW_DIR / "build-push.yaml"
CI_PATH = WORKFLOW_DIR / "ci.yml"

_spec = importlib.util.spec_from_file_location("isaac_ci_release_gate", GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["isaac_ci_release_gate"] = gate
_spec.loader.exec_module(gate)


REPO = "ISAAC-DOE/isaac-metadata-assistant"
SHA = "23ce90f0a992df602be55780999470cc6e492200"
OTHER_SHA = "7fced76f1e49af160053e6f1dfaa210dc020d634"


def run(**overrides):
    """One Actions API run record, green-on-main-in-this-repo by default."""
    record = {
        "id": 31248074055,
        "path": ".github/workflows/ci.yml",
        "name": "CI",
        "head_sha": SHA,
        "head_branch": "main",
        "head_repository": {"full_name": REPO},
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "updated_at": "2026-08-08T09:23:16Z",
    }
    record.update(overrides)
    return record


def decide(runs, sha: str = SHA):
    return gate.evaluate(repo=REPO, sha=sha, fetcher=lambda: runs)


def load(path: Path) -> dict:
    # Deliberately NOT `importorskip`. A skipped wiring check is indistinguishable
    # from a passing one in CI output, and "the check silently did not run" is the
    # same class of failure as "the gate silently did not run". pyyaml is pinned
    # into the dev extra so this always executes.
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow() -> dict:
    return load(WORKFLOW_PATH)


@pytest.fixture(scope="module")
def ci() -> dict:
    return load(CI_PATH)


def triggers(wf: dict) -> dict:
    """PyYAML parses the bare key `on:` as the boolean True, hence the fallback."""
    return wf.get("on", wf.get(True))


# --- negative controls: a publish must be impossible -------------------------


def test_negative_control_failed_ci_cannot_publish():
    """The recorded 23ce90f failure. This is the defect, encoded."""
    decision = decide([run(conclusion="failure", updated_at="2026-08-08T08:52:37Z")])
    assert decision.allowed is False
    assert "'failure'" in decision.reason


def test_negative_control_ci_still_running_cannot_publish():
    """The 08:19:17 moment: CI in flight, image about to ship. Must refuse."""
    decision = decide([run(status="in_progress", conclusion=None)])
    assert decision.allowed is False
    assert "not finished" in decision.reason


def test_negative_control_a_fork_pr_green_run_cannot_publish():
    """The hole the first version of this gate opened.

    A fork's default branch is `main`, and a fork PR's run is recorded in THIS
    repository with the fork's `head_branch`. Every other filter passes; only
    `head_repository` distinguishes it.
    """
    decision = decide([run(head_repository={"full_name": "attacker/isaac-metadata-assistant"})])
    assert decision.allowed is False


@pytest.mark.parametrize(
    "runs, why",
    [
        ([], "no CI run at all"),
        ([run(path=".github/workflows/pr-docker-smoke.yml")], "a different workflow file being green"),
        ([run(path=".github/workflows/impostor.yml")], "a second workflow that merely DISPLAYS as 'CI'"),
        ([run(head_sha=OTHER_SHA)], "a green run belonging to another commit"),
        ([run(head_branch="feat/something")], "a green run on another branch"),
        ([run(event="pull_request")], "a green pull_request check on a merge preview"),
        ([run(head_repository=None)], "a run with no head_repository at all"),
        ([run(head_repository={})], "a run whose head_repository has no full_name"),
        ([run(conclusion="cancelled")], "a cancelled run"),
        ([run(conclusion="skipped")], "a skipped run"),
        ([run(conclusion="timed_out")], "a timed-out run"),
        ([run(conclusion="action_required")], "an unapproved fork run awaiting approval"),
        ([run(conclusion=None, status="queued")], "a queued run"),
    ],
)
def test_negative_control_absence_and_impostors_are_refusals(runs, why):
    """Anything short of an affirmative success for THIS commit refuses.

    Absence of evidence is refusal, never permission — which is why the empty
    list is in this table alongside the impostors.
    """
    assert decide(runs).allowed is False, f"gate wrongly allowed publish on {why}"


def test_negative_control_a_stale_green_cannot_outrank_a_newer_red():
    """The ordering bug, encoded.

    `run_attempt` is only comparable WITHIN one run id. Ordering by it let a run
    sitting at attempt 3 beat a newer run at attempt 1, so a morning green could
    authorise a publish while the latest CI verdict for the commit was `failure`.
    Requiring every relevant run to be green removes the comparison entirely.
    """
    decision = decide(
        [
            run(id=1, run_attempt=3, conclusion="success", updated_at="2026-08-08T09:00:00Z"),
            run(id=2, run_attempt=1, conclusion="failure", updated_at="2026-08-08T23:59:00Z"),
        ]
    )
    assert decision.allowed is False


def test_negative_control_unreachable_api_refuses():
    """If CI status cannot be established, the gate closes rather than guesses."""

    def explode():
        raise gate.GateRefusal("the Actions API was unreachable")

    assert gate.evaluate(repo=REPO, sha=SHA, fetcher=explode).allowed is False


def test_negative_control_a_timeout_refuses_with_a_reason_not_a_traceback():
    """TimeoutError is not a URLError; it used to escape as a stack trace."""

    def explode():
        raise gate._fetch_runs(REPO, SHA, None, api_root="http://127.0.0.1:1")  # noqa: SLF001

    decision = gate.evaluate(repo=REPO, sha=SHA, api_root="http://127.0.0.1:1")
    assert decision.allowed is False
    assert "unknown" in decision.reason


def test_negative_control_short_sha_is_refused():
    """A prefix match could let one commit's green run authorise another's build."""
    assert decide([run()], sha=SHA[:7]).allowed is False


def test_negative_control_exit_code_is_nonzero(monkeypatch):
    """The workflow only obeys the process exit status, so pin it."""
    monkeypatch.setattr(gate, "evaluate", lambda **_: gate.Decision(False, SHA, "red"))
    assert gate.main(["--repo", REPO, "--sha", SHA]) != 0


# --- positive control: a green commit must still ship -------------------------


def test_positive_control_green_ci_publishes():
    decision = decide([run()])
    assert decision.allowed is True
    assert "success" in decision.reason


def test_positive_control_rerun_to_green_publishes():
    """A rerun updates the run's own record rather than adding one.

    Verified against real API data: run 31248074055 attempt 2 contains ALL FOUR
    jobs, three carried forward from attempt 1 and only the failed one
    re-executed. So a workflow-level `success` at attempt N means every job in
    the run is green — and the API returns one record per run, reflecting its
    latest attempt.
    """
    decision = decide([run(run_attempt=2, conclusion="success")])
    assert decision.allowed is True


def test_positive_control_uppercase_sha_is_accepted():
    """`_looks_like_sha` accepts uppercase; matching must too, or it silently
    becomes the indistinguishable 'no CI run found'."""
    assert decide([run()], sha=SHA.upper()).allowed is True


def test_positive_control_exit_code_is_zero(monkeypatch):
    monkeypatch.setattr(gate, "evaluate", lambda **_: gate.Decision(True, SHA, "green"))
    assert gate.main(["--repo", REPO, "--sha", SHA]) == 0


# --- the workflow must actually be wired to the gate --------------------------
#
# The controls above prove the DECISION is correct. These prove the decision is
# CONNECTED — that nothing can publish without it. A correct gate that nothing
# calls is the same defect in a new place.


def test_build_push_no_longer_triggers_on_a_push_to_a_branch(workflow):
    """The original 23ce90f defect, pinned so an edit cannot reintroduce it.

    Checks the whole `push:` key, not just `push.branches`: a bare `push:` (which
    YAML parses as None) fires on EVERY branch, and `branches-ignore` reaches
    `main` too.
    """
    trig = triggers(workflow)
    assert "push" not in trig, (
        "build-push.yaml triggers on a push again. That is the 23ce90f defect: it "
        "runs concurrently with CI and cannot see its result. The `v*` tag form is "
        "also refused here — a push event reads its workflow definition from the "
        "pushed ref's own tree, so a tag can carry a gate-less copy of this file."
    )
    assert "workflow_run" in trig
    assert trig["workflow_run"]["workflows"] == ["CI"]


def test_the_gate_job_refuses_forks_and_non_push_ci_runs(workflow):
    """The `branches:` filter is NOT the fork guard; this `if:` is."""
    condition = " ".join(str(workflow["jobs"]["gate"]["if"]).split())
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in condition, (
        "without this, a fork PR opened from the fork's own `main` satisfies every "
        "other filter and reaches a job holding packages: write"
    )
    assert "github.event.workflow_run.event == 'push'" in condition
    assert "github.event.workflow_run.head_branch == 'main'" in condition


def test_the_gate_does_not_check_out_the_commit_it_is_judging(workflow):
    """The pwn-request guard.

    A `workflow_run` workflow runs with base-repo secrets and a write-scoped
    token. Checking out the triggering commit here would execute code from the
    tree being gated — the gate script would become whatever that tree says it
    is, and every control in this file would be irrelevant.
    """
    for step in workflow["jobs"]["gate"]["steps"]:
        if str(step.get("uses", "")).startswith("actions/checkout"):
            assert "ref" not in (step.get("with") or {}), (
                "the gate job must check out the trusted default branch, never the "
                "commit under release"
            )


def test_publishing_job_depends_on_the_gate(workflow):
    jobs = workflow["jobs"]
    assert "gate" in jobs
    needs = jobs["build-and-push"].get("needs")
    # Accept both the scalar and the list form; `needs: [gate]` is ordinary YAML
    # and an earlier version of this assertion would have failed a safe workflow.
    assert needs == "gate" or needs == ["gate"]


def _publishing_steps(job: dict) -> list[dict]:
    """Every step in `job` that could put an image in a registry.

    Three mechanisms, because an adversarial review got all three past the first
    version of this check, which only looked for `push: true` on the action:

      1. `docker/build-push-action` with a truthy `push` — including the STRING
         `"true"` and an expression, which `is True` misses;
      2. the same action with `outputs: type=registry`, which publishes with no
         `push` key at all;
      3. a plain `run:` block invoking `docker push` or `buildx --push`.
    """
    found = []
    for step in job.get("steps", []) or []:
        uses = str(step.get("uses", ""))
        with_ = step.get("with") or {}
        if uses.startswith("docker/build-push-action"):
            push = with_.get("push")
            if push is True or str(push).strip().lower() in {"true", "yes", "1"} or "${{" in str(push):
                found.append(step)
            elif "type=registry" in str(with_.get("outputs", "")):
                found.append(step)
        script = str(step.get("run", ""))
        if "docker push" in script or ("buildx" in script and "--push" in script):
            found.append(step)
    return found


def test_no_job_in_any_workflow_can_publish_without_the_gate():
    """Scans EVERY workflow file, not just this one.

    A new `.github/workflows/release.yml` that publishes would have been entirely
    unguarded by a check hard-coded to one path.
    """
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        wf = load(path)
        for name, job in (wf.get("jobs") or {}).items():
            for _step in _publishing_steps(job):
                needs = job.get("needs")
                assert needs == "gate" or (isinstance(needs, list) and "gate" in needs), (
                    f"{path.name}: job {name!r} can publish an image but does not need the gate"
                )


def test_gate_invokes_the_tested_script(workflow):
    """The workflow must call THIS script — the one these controls exercise."""
    steps = workflow["jobs"]["gate"]["steps"]
    assert any("scripts/ci_release_gate.py" in str(step.get("run", "")) for step in steps)


def test_image_is_built_from_the_gate_approved_commit(workflow):
    """BOTH the checkout ref and the build-arg, not just the build-arg.

    Pinning only the build-arg let a mutation revert the checkout to
    `github.sha` — building a different tree while `ISAAC_BUILD_COMMIT` kept
    reporting the gated commit. That is a health endpoint describing a tree that
    was never built, which is worse than an ungated build because it is silent.
    """
    build = workflow["jobs"]["build-and-push"]
    checkouts = [s for s in build["steps"] if str(s.get("uses", "")).startswith("actions/checkout")]
    assert checkouts, "the build job must check out something"
    for step in checkouts:
        assert "needs.gate.outputs.sha" in str((step.get("with") or {}).get("ref", ""))

    for step in build["steps"]:
        if str(step.get("uses", "")).startswith("docker/build-push-action"):
            build_args = str(step["with"]["build-args"])
            assert "needs.gate.outputs.sha" in build_args
            assert "github.sha" not in build_args


# --- the gate's premise: a workflow-level success must mean every job green ----


def test_ci_name_matches_what_the_gate_reports(ci):
    """The gate matches on PATH, but its messages name the display title."""
    assert ci.get("name", ci.get(True)) == gate.REQUIRED_WORKFLOW_NAME


def test_ci_path_is_what_the_gate_requires():
    assert CI_PATH.relative_to(REPO_ROOT).as_posix() == gate.REQUIRED_WORKFLOW_PATH


def test_no_ci_job_can_be_red_while_the_workflow_reports_success(ci):
    """The unguarded premise the whole gate rests on.

    A workflow-level `success` is only meaningful if every job had to pass.
    `continue-on-error: true` produces a job conclusion of `failure` with a
    workflow conclusion of `success`, and a job-level `if:` can skip a job
    without failing the run. Either silently converts this gate into a no-op.

    This is not hypothetical: the job that failed on 23ce90f is the flaky
    `browser-a11y`, and `continue-on-error: true` on it is the single most likely
    next edit to `ci.yml`.
    """
    for name, job in ci["jobs"].items():
        assert "continue-on-error" not in job, (
            f"ci.yml job {name!r} has continue-on-error, so the workflow can report "
            "success with this job red — and the release gate would publish it"
        )
        assert "if" not in job, (
            f"ci.yml job {name!r} has a job-level if:, so it can skip without failing "
            "the run, and a skipped required job is not a passed one"
        )
        for step in job.get("steps", []) or []:
            assert "continue-on-error" not in step, (
                f"ci.yml job {name!r} has a step with continue-on-error"
            )
