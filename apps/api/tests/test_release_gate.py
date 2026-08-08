"""Controls for the release gate: red CI must not be able to publish an image.

This file is the reason `scripts/ci_release_gate.py` is Python and not a YAML
`if:` expression. A YAML expression cannot be handed a failing world and watched
to refuse. These tests hand the gate a red world, a still-running world, an empty
world, a wrong-branch world and a pull_request world, and assert it refuses each
one — and then hand it a green world and assert it still allows the publish, so
the gate is shown to be a gate rather than a wall.

The scenario the negative control encodes is a real one, not a hypothetical.
Commit 23ce90f published its GHCR image at 08:19:17 while CI attempt 1 was still
running; that attempt concluded `failure` at 08:52:37. `test_negative_control_*`
below reconstructs both moments.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = REPO_ROOT / "scripts" / "ci_release_gate.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build-push.yaml"

_spec = importlib.util.spec_from_file_location("isaac_ci_release_gate", GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["isaac_ci_release_gate"] = gate
_spec.loader.exec_module(gate)


REPO = "ISAAC-DOE/isaac-metadata-assistant"
SHA = "23ce90f0a992df602be55780999470cc6e492200"
OTHER_SHA = "7fced76f1e49af160053e6f1dfaa210dc020d634"


def run(**overrides):
    """One Actions API run record, green-on-main by default."""
    record = {
        "name": "CI",
        "head_sha": SHA,
        "head_branch": "main",
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


@pytest.mark.parametrize(
    "runs, why",
    [
        ([], "no CI run at all"),
        ([run(name="PR Docker Smoke")], "a different workflow being green"),
        ([run(head_sha=OTHER_SHA)], "a green run belonging to another commit"),
        ([run(head_branch="feat/something")], "a green run on another branch"),
        ([run(event="pull_request")], "a green pull_request check on a merge preview"),
        ([run(conclusion="cancelled")], "a cancelled run"),
        ([run(conclusion="skipped")], "a skipped run"),
        ([run(conclusion=None, status="queued")], "a queued run"),
    ],
)
def test_negative_control_absence_and_impostors_are_refusals(runs, why):
    """Anything short of an affirmative success for THIS commit refuses.

    Absence of evidence is refusal, never permission — which is why the empty
    list is in this table alongside the impostors.
    """
    assert decide(runs).allowed is False, f"gate wrongly allowed publish on {why}"


def test_negative_control_unreachable_api_refuses():
    """If CI status cannot be established, the gate closes rather than guesses."""

    def explode():
        raise gate.GateRefusal("the Actions API was unreachable")

    decision = gate.evaluate(repo=REPO, sha=SHA, fetcher=explode)
    assert decision.allowed is False


def test_negative_control_short_sha_is_refused():
    """A prefix match could let one commit's green run authorise another's build."""
    assert decide([run()], sha=SHA[:7]).allowed is False


def test_negative_control_exit_code_is_nonzero(monkeypatch, capsys):
    """The workflow only obeys the process exit status, so pin it."""
    monkeypatch.setattr(gate, "evaluate", lambda **_: gate.Decision(False, SHA, "red"))
    assert gate.main(["--repo", REPO, "--sha", SHA]) != 0


# --- positive control: a green commit must still ship -------------------------


def test_positive_control_green_ci_publishes():
    decision = decide([run()])
    assert decision.allowed is True
    assert "success" in decision.reason


def test_positive_control_rerun_to_green_publishes():
    """A red attempt 1 followed by a green attempt 2 is a commit whose required
    CI *has* concluded successfully, so it may ship. This is the one direction
    the gate is permissive in, and it is deliberate: it is what actually happened
    to 23ce90f, and it is categorically different from publishing before CI ran.
    """
    decision = decide(
        [
            run(run_attempt=1, conclusion="failure", updated_at="2026-08-08T08:52:37Z"),
            run(run_attempt=2, conclusion="success", updated_at="2026-08-08T09:23:16Z"),
        ]
    )
    assert decision.allowed is True
    assert "attempt 2" in decision.reason


def test_positive_control_green_then_red_rerun_refuses():
    """Ordering is by attempt, not by optimism: a later red attempt refuses."""
    decision = decide(
        [
            run(run_attempt=1, conclusion="success"),
            run(run_attempt=2, conclusion="failure", updated_at="2026-08-08T10:00:00Z"),
        ]
    )
    assert decision.allowed is False


def test_positive_control_exit_code_is_zero(monkeypatch):
    monkeypatch.setattr(gate, "evaluate", lambda **_: gate.Decision(True, SHA, "green"))
    assert gate.main(["--repo", REPO, "--sha", SHA]) == 0


# --- the workflow must actually be wired to the gate --------------------------
#
# The controls above prove the DECISION is correct. These prove the decision is
# CONNECTED — that the publishing job cannot run without it. A correct gate that
# nothing calls is the same defect in a new place.


@pytest.fixture(scope="module")
def workflow() -> dict:
    # Deliberately NOT `importorskip`. A skipped wiring check is indistinguishable
    # from a passing one in CI output, and "the check silently did not run" is the
    # same class of failure as "the gate silently did not run". pyyaml is pinned
    # into the dev extra so this always executes.
    import yaml

    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_build_push_no_longer_triggers_on_a_push_to_main(workflow):
    """The original defect, pinned so it cannot be reintroduced by an edit.

    PyYAML parses the bare key `on:` as the boolean True, hence the lookup.
    """
    triggers = workflow.get("on", workflow.get(True))
    push = triggers.get("push") or {}
    assert "branches" not in push, (
        "build-push.yaml triggers on a branch push again. That is the exact "
        "23ce90f defect: it runs concurrently with CI and cannot see its result."
    )
    assert "workflow_run" in triggers, "the gate depends on ordering after the CI workflow"
    assert triggers["workflow_run"]["workflows"] == ["CI"]


def test_publishing_job_depends_on_the_gate(workflow):
    jobs = workflow["jobs"]
    assert "gate" in jobs
    assert jobs["build-and-push"]["needs"] == "gate"


def test_only_the_gated_job_can_push_an_image(workflow):
    """No `push: true` may live in a job that does not need the gate."""
    for name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("docker/build-push-action"):
                if step.get("with", {}).get("push") is True:
                    assert job.get("needs") == "gate", f"job {name!r} publishes without the gate"


def test_gate_invokes_the_tested_script(workflow):
    """The workflow must call THIS script — the one these controls exercise."""
    steps = workflow["jobs"]["gate"]["steps"]
    assert any("scripts/ci_release_gate.py" in str(step.get("run", "")) for step in steps)


def test_image_is_built_from_the_gate_approved_commit(workflow):
    """`github.sha` under workflow_run is the branch tip, not the commit CI ran on.

    Baking it would make /api/health report a commit that was never gated.
    """
    for step in workflow["jobs"]["build-and-push"]["steps"]:
        if str(step.get("uses", "")).startswith("docker/build-push-action"):
            build_args = step["with"]["build-args"]
            assert "needs.gate.outputs.sha" in build_args
            assert "github.sha" not in build_args
