# Branch protection for `main` — a request for the repository owner

**Status: NOT CONFIGURED. This agent cannot configure it.** Both facts are measured, not assumed.

## What was measured

```
$ gh api repos/ISAAC-DOE/isaac-metadata-assistant/branches/main/protection
404 Not Found                       # no branch protection exists

$ gh api repos/ISAAC-DOE/isaac-metadata-assistant/rulesets --jq 'length'
0                                   # no ruleset either

$ gh api repos/ISAAC-DOE/isaac-metadata-assistant --jq '.permissions'
{"admin": false, "maintain": false, "push": true}

$ gh api repos/ISAAC-DOE/isaac-metadata-assistant --jq '.visibility'
"public"
```

So: `main` is **unprotected**, on a **public** repository, and the identity doing the work has
**push but not admin** — which is exactly the shape where a mistake is both easy and permanent.

Configuring protection requires `admin`. This is therefore a request, not a task.

## Why it is worth doing now rather than later

This is not hypothetical tidiness. In one session on 2026-08-08:

- **A red `main` shipped an image.** Commit `23ce90f` had
  `browser accessibility and responsive baseline: failure` while `build-and-push: success`
  published `v0.0.80`. The cause is below, and a required-status-check rule would not have
  stopped the push — but it would have stopped the *merge* that produced it.
- **Eight PRs merged in a few hours**, several touching the same files. Nothing but convention
  prevented a direct push to `main` bypassing review entirely.
- **Every PR was reviewed, and not one review is recorded anywhere queryable.** The reviews
  happened as prose in PR bodies; GitHub shows **zero** approvals on #69–#80. A
  required-approvals rule is what turns "we reviewed it" into something a third party can check.

## Recommended minimum

| Setting | Value | Why this one |
|---|---|---|
| Require a pull request before merging | on | closes direct push to `main` |
| Required approvals | 1 | makes review a record rather than a habit |
| Require status checks to pass | on | see the separate defect below |
| Required checks | `tests and synthetic demo`, `frontend tests and build`, `browser accessibility and responsive baseline`, `migration and durable repository against a real PostgreSQL` | the four CI jobs that already run on every PR |
| Require branches to be up to date before merging | on | catches the merge-result regression a green branch can still produce |
| Block force pushes | on | history is the audit trail for the evidence artifacts in `docs/evidence/` |
| Block branch deletion | on | — |

Deliberately **not** requested: signed commits, linear history, or an admin-bypass restriction.
Each has real cost for a single-maintainer prototype, and none addresses a failure this project
has actually had.

## A separate, application-owned defect that protection does NOT fix

**`.github/workflows/build-push.yaml` has no `needs:` on the CI workflow.** It triggers on push to
`main` and publishes to GHCR independently, so a commit whose tests fail still ships an image —
which is exactly what happened with `v0.0.80`.

Branch protection gates *merges*, not *workflow triggers*, so it cannot close this. The fix is a
`needs:` (or a `workflow_run` trigger conditioned on CI success) in a file this repository already
owns. **No infrastructure access is required and this should not be asked of the owner** — it is
listed here only so the two issues are not confused for one another.

## The one question to answer

> Would you enable branch protection on `main` with the seven settings above, or tell us which of
> them you would rather not have?
