# Release gating: why a red commit could ship, and what now stops it

## The invariant

> **No production/deployable image may be published from a commit whose required
> CI gate has not completed successfully.**

## The defect, as measured

Until 2026-08-08 this repository had two workflows that both triggered on
`push: branches: [main]`:

| File | `name:` | Trigger |
|---|---|---|
| `.github/workflows/ci.yml` | `CI` | `push: main`, `pull_request: main` |
| `.github/workflows/build-push.yaml` | `Build and Push to GHCR` | `push: main`, `tags: v*` |

They are **separate workflow files**. `needs:` orders jobs *within one workflow*
and cannot reach across files, so nothing connected them. Both started on the
same push, at the same second, and raced. The publish decision consulted CI not
at all — not "consulted it and got the wrong answer", but never looked.

This is not a hypothetical. On merge commit `23ce90f`:

| Workflow | Attempt | Started | Finished | Conclusion |
|---|---|---|---|---|
| CI | 1 | 08:17:26Z | 08:52:37Z | **failure** |
| Build and Push to GHCR | 1 | 08:17:26Z | **08:19:17Z** | success — **image published** |
| CI | 2 (manual rerun) | 09:03:14Z | 09:23:16Z | success |

The image was published and taggable **33 minutes before the red CI result even
existed**, and roughly an hour before the green rerun.

Two things are worth stating precisely, because the softer version of each has
been circulating:

- **The later green rerun does not retire the defect.** It changes the outcome
  for one commit; it changes nothing about the control. The pipeline would have
  published exactly the same image had the rerun stayed red, because the publish
  had already happened.
- **The failures on attempt 1 were subsequently judged to be flakes.** That is a
  statement about those tests, not about release safety. A pipeline that ships
  before CI finishes ships red commits and green commits with equal confidence,
  and cannot tell you which it just did.

Reproduce the finding:

```bash
gh api repos/ISAAC-DOE/isaac-metadata-assistant/actions/runs/31248074055/attempts/1 \
  --jq '{attempt:.run_attempt, conclusion:.conclusion, created:.created_at, updated:.updated_at}'
gh run view 31248074059 --json workflowName,startedAt,updatedAt,conclusion
```

## The fix

`needs:` was **not** the right instrument, because the two jobs are not in one
workflow. The change uses `workflow_run`, which is GitHub's supported mechanism
for ordering one workflow after another across files:

```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
  push:
    tags: ['v*']
```

and then, inside that workflow, an ordinary `needs:` from the publishing job to a
`gate` job that re-checks the Actions API.

### Why there is a gate job as well as a trigger

`workflow_run` fires on *completed*, not on *succeeded* — a failed CI run also
fires it. The conclusion could be checked in a YAML `if:`, but two things argued
against leaving it there:

1. **The tag path would bypass it.** `push: tags: v*` is not a `workflow_run`
   event and has no `workflow_run.conclusion` to test, so a human pushing a tag
   at a red commit would publish. One enforcement point covers both paths.
2. **A YAML expression cannot be tested.** You cannot hand an `if:` a red world
   and watch it refuse.

So the decision lives in `scripts/ci_release_gate.py`, and the controls live in
`apps/api/tests/test_release_gate.py`.

### Fail-closed

The gate authorises a publish only on an affirmative "the required workflow
concluded `success`, for exactly this 40-character commit sha, on `main`, from a
`push` event". Everything else refuses, including the states that are easy to
mistake for harmless:

- no CI run found for the commit — **absence of evidence is refusal**
- CI still `in_progress` or `queued` — this is precisely the 08:19:17 moment
- `failure`, `cancelled`, `skipped`
- a green run for a *different* commit, or a *short-sha* prefix match
- a green run on a different branch
- a green `pull_request` run, which is green against a merge-preview commit that
  nobody is releasing
- the Actions API being unreachable or malformed

### The one permissive direction

A red attempt 1 followed by a green rerun **does** authorise a publish. That is
deliberate: a commit whose required CI has concluded successfully is exactly what
the invariant asks for, and re-running flaky CI is legitimate. It is categorically
different from publishing before CI has finished, which stays refused.

Correspondingly, green attempt 1 followed by a **red** rerun refuses — the gate
orders by attempt, not by optimism.

### Two correctness details that are easy to get wrong

- **`github.sha` is the wrong commit under `workflow_run`.** It is the default
  branch tip at trigger time, not the commit CI ran on. Both the checkout and
  `ISAAC_BUILD_COMMIT` use `github.event.workflow_run.head_sha`; baking
  `github.sha` would make `/api/health`'s reported `commit` describe a tree that
  was never gated. A test pins this.
- **A `workflow_run` workflow is read from the default branch.** Edits to
  `build-push.yaml` take effect only once merged, and a PR cannot exercise the
  trigger. This is the other reason the decision logic sits in a script: PR CI
  can test the script directly even though it cannot test the trigger.

## The controls

`apps/api/tests/test_release_gate.py` — 22 tests, no network, no skips.

**Negative controls (a publish must be impossible):** the recorded `23ce90f`
failure; CI still running; no run at all; a different workflow being green; a
green run for another commit; another branch; a `pull_request` run; `cancelled`;
`skipped`; `queued`; a short sha; an unreachable API; and a non-zero process exit
status, since the workflow obeys nothing else.

**Positive controls (a green commit must still ship):** green CI publishes;
rerun-to-green publishes; exit status zero.

**Wiring controls (the gate must be connected, not merely correct):** the
workflow no longer has a `push.branches` trigger; `build-and-push` `needs: gate`;
no job containing `docker/build-push-action` with `push: true` lacks that
dependency; the gate step actually invokes this script; the image is built from
`needs.gate.outputs.sha`.

These parse the workflow with PyYAML rather than pattern-matching it, because a
regex over YAML can be defeated by a reformat, and the one thing this change must
guarantee is that the gate cannot be quietly un-wired. PyYAML is pinned into the
`dev` extra and the fixture imports it directly rather than via `importorskip` —
a skipped wiring check is indistinguishable from a passing one in CI output, which
is the same class of failure as a gate that silently does not run.

The wiring controls were mutation-checked against the pre-fix file: all three
core assertions fail on it, so they are a real regression guard rather than a
tautology.

## What this does not cover

- **It does not make CI itself trustworthy.** The gate enforces that CI was
  consulted and was green. Whether CI's green is meaningful is a separate
  question, addressed by test quality and by the flake work, not here.
- **It does not gate deployment, only publication.** Flux rolls what is in GHCR.
  Nothing in this change alters that path.
- **It does not stop a repository admin from pushing directly to `main`.** That
  is what branch protection is for, and it is deliberately a separate request —
  see the branch-protection PR. Branch protection and this gate solve adjacent
  problems and neither substitutes for the other.
