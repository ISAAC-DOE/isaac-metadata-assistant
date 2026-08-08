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
    branches: [main]      # NOT the guarantee it looks like — see below
```

and then, inside that workflow, an ordinary `needs:` from the publishing job to a
`gate` job that re-checks the Actions API.

### Why there is a gate job as well as a trigger

`workflow_run` fires on *completed*, not on *succeeded* — a failed CI run also
fires it. The conclusion could be checked in a YAML `if:`, but a YAML expression
cannot be handed a red world and watched to refuse, and the decision is worth
testing.

**An earlier revision of this document said the second reason was that the
`v*` tag path "goes through the same gate rather than around it". That was
false, and the tag trigger has since been removed.** For a `push` event the
workflow *definition* is read from the pushed ref's own tree — so anyone able to
push a tag could tag a commit whose `build-push.yaml` has no gate at all,
bypassing `main` entirely and invisibly to the wiring tests, which can only
inspect the file on the branch under test. Nothing needed the trigger: this
repository's version tags are created by this workflow's own final step using
`GITHUB_TOKEN`, and `GITHUB_TOKEN`-created events do not start workflow runs.

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

It is **not** implemented by ordering attempts. An earlier version ordered runs
by `run_attempt`, which is a number that only means something *within one run
id*; an adversarial review showed a stale run at attempt 3 outranking a newer run
at attempt 1, so a morning green could authorise a publish while the latest CI
verdict for that commit was `failure`. The gate now requires **every** relevant
run for the commit to be green, which removes the comparison rather than trying
to get it right.

Verified against real API data: run `31248074055` attempt 2 contains **all four**
jobs — three carried forward from attempt 1 with their original timestamps, only
the failed one re-executed. So a workflow-level `success` at attempt *N* does
mean every job in the run is green, and "re-run a subset to manufacture a green"
is not available. The API also returns one record *per run*, showing its latest
attempt, so a rerun updates the existing record rather than adding one.

### Two correctness details that are easy to get wrong

- **`github.sha` is the wrong commit under `workflow_run`.** It is the default
  branch tip at trigger time, not the commit CI ran on. The BUILD job's checkout
  and `ISAAC_BUILD_COMMIT` both use the gate-approved sha; baking `github.sha`
  would make `/api/health`'s reported `commit` describe a tree that was never
  gated.

  An earlier revision said "a test pins this" while the test pinned only the
  build-arg. Reverting *just* the checkout passed every test and produced the
  exact failure the sentence claimed to prevent — a health endpoint describing a
  tree that was never built, which is worse than an ungated build because it is
  silent. **Both** are pinned now.
- **A `workflow_run` workflow is read from the default branch.** Edits to
  `build-push.yaml` take effect only once merged, and a PR cannot exercise the
  trigger. This is the other reason the decision logic sits in a script: PR CI
  can test the script directly even though it cannot test the trigger.

  **This fact is a hazard as much as a safety property, and an earlier revision
  of this document recorded only the safety half.** Because the trusted wrapper
  runs with base-repo secrets and a write-scoped token, checking out the
  triggering commit inside it would hand that context to whoever wrote the
  commit. See the section below.

## The controls

`apps/api/tests/test_release_gate.py` — **35 tests**, no network, no skips.

**Negative controls (a publish must be impossible):** the recorded `23ce90f`
failure; CI still running; no run at all; a different workflow *file*; a second
workflow that merely *displays* as `CI`; a green run for another commit; another
branch; a `pull_request` run; **a fork PR's green run**; a run with no
`head_repository`; `cancelled`; `skipped`; `timed_out`; `action_required`;
`queued`; a stale green outranking a newer red; a short sha; an unreachable API;
a timeout that is not a `URLError`; and a non-zero process exit status, since the
workflow obeys nothing else.

**Positive controls (a green commit must still ship):** green CI publishes;
rerun-to-green publishes; an uppercase sha is accepted; exit status zero.

**Wiring controls (the gate must be connected, not merely correct):** no `push`
trigger of any form; the gate job's `if:` carries all three guards including the
fork check; the gate job does **not** check out the commit it is judging;
`build-and-push` needs the gate in either the scalar or list form; **no job in
any workflow file** can publish without that dependency; the gate invokes this
script; and both the build checkout *and* the build-arg use the gate-approved
sha.

**Premise controls:** `ci.yml`'s `name:` matches what the gate reports, its path
matches what the gate requires, and **no job or step in `ci.yml` carries
`continue-on-error` or a job-level `if:`** — either would let the workflow report
`success` with a required job red or skipped, silently turning this gate into a
no-op. That is not hypothetical: the job that failed on `23ce90f` is the flaky
`browser-a11y`, and `continue-on-error: true` on it is the most likely next edit.

These parse the workflow with PyYAML rather than pattern-matching it, because a
regex over YAML can be defeated by a reformat. PyYAML is pinned into the `dev`
extra and imported directly rather than via `importorskip` — a skipped wiring
check is indistinguishable from a passing one in CI output, which is the same
class of failure as a gate that silently does not run.

### Mutation-checked, twice

The first version of this gate **passed all of its own tests and was not safe.**
Each control below was verified by applying the mutation and confirming the suite
fails:

| Mutation | Caught |
|---|---|
| bare `on: push:` (fires on every branch) | ✅ |
| `push: branches-ignore: [nothing]` | ✅ |
| ungated job running `docker buildx build --push` | ✅ |
| ungated job publishing via `outputs: type=registry` | ✅ |
| ungated job with `push: "true"` as a string | ✅ |
| ungated job with `push:` as an expression | ✅ |
| an entirely **new** workflow file that publishes | ✅ |
| build checkout reverted to `github.sha` | ✅ |
| gate checkout re-adding `ref:` (the pwn request) | ✅ |
| gate `if:` dropping the fork check | ✅ |

## The hole this fix originally opened, and how it is closed

Worth recording rather than quietly fixing, because it is the more instructive
half of this change: **the first version of the fix was more dangerous than the
defect it repaired.**

`workflow_run`'s `branches:` filter matches the *triggering run's*
`head_branch` — and for a pull request opened from a **fork**, that is the
fork's branch name, on a run recorded in *this* repository. A fork's default
branch is `main`. This repository is public with forking enabled. So
`branches: [main]` matched any fork PR opened from the fork's own `main`, by any
GitHub user.

The gate job then checked out that commit and ran `scripts/ci_release_gate.py`
**from it**, in a job holding `packages: write`. The gate executed the attacker's
copy of the gate. Every negative control in the suite was irrelevant, because
`evaluate()` was no longer the function under test. The result would have been an
arbitrary image published to `:latest` and a `v*` tag pushed into the org repo —
reachable by anyone, where the old defect at least required write access.

Three changes close it, and the first two are the load-bearing ones:

1. The gate job's `if:` requires `workflow_run.event == 'push'`,
   `head_repository.full_name == github.repository`, and `head_branch == 'main'`.
   A false `if:` skips the job, and `build-and-push` needs it, so the workflow
   skips with it.
2. The gate job checks out **no `ref:`** — under `workflow_run` that is the
   default-branch tip, the same trusted ref this workflow file itself came from.
   It costs nothing: the gate script is a stdlib-only decision function that asks
   the Actions API about a sha, and does not depend on the tree it is judging.
3. `_relevant()` independently re-checks `head_repository.full_name`, so the
   decision does not rest on the YAML guard alone.

Plus two defences that should never fire: `build-and-push` asserts the gated
commit is an ancestor of `origin/main`, and the version step **refuses** rather
than defaulting to `0.0.1` when no `v*` tag is found — the old default would have
overwritten `:0.0.1` *and* `:latest` on a bad fetch.

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
