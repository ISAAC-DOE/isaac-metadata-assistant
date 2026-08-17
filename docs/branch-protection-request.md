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
  published `v0.0.80`. **Be careful with this one as an argument for protection**, because the
  obvious version of it is not quite right: the failure was on the *merge commit's* CI run, and a
  required-status-check rule gates the *PR head's* checks. It would not have caught this unless
  "require branches to be up to date" were also on — which is the setting the table below
  deliberately declines. So this incident is honestly an argument for the workflow fix (PR #82,
  which closes it) more than for protection. It is listed here because it is what prompted the
  question, not because protection would have prevented it.
- **Eight PRs merged in a few hours**, several touching the same files. Nothing but convention
  prevented a direct push to `main` bypassing review entirely.
- **Every PR was reviewed, and not one review is recorded anywhere queryable.** The reviews
  happened as prose in PR bodies; GitHub shows **zero** approvals on #69–#80. Note that the
  instrument for this is *not* in the recommended set below, and the table explains why: with one
  maintainer, a required-approvals rule blocks merges rather than recording reviews. Posting the
  reviews *as GitHub reviews* fixes the record at no cost and needs no admin.

## Recommended minimum

| Setting | Value | Why this one |
|---|---|---|
| Require a pull request before merging | on | closes direct push to `main` |
| Require status checks to pass | on | the four CI jobs already run on every PR; this makes them binding |
| Required checks | `tests and synthetic demo`, `frontend tests and build`, `browser accessibility and responsive baseline`, `migration and durable repository against a real PostgreSQL`, `build + smoke-test production image (local, no push)` | the four CI jobs plus the PR Docker smoke job — all five already run on every PR today |
| Block force pushes | on | history is the audit trail for the evidence artifacts in `docs/evidence/` |
| Block branch deletion | on | — |

Deliberately **not** requested: signed commits, linear history, or an admin-bypass restriction.
Each has real cost for a single-maintainer prototype, and none addresses a failure this project
has actually had.

**Two settings were dropped from an earlier draft of this request, and the reasons are specific
to this repository rather than general.** They are recorded rather than silently removed, because
both are defensible choices and the owner may want either one.

- **Required approvals: 1** — dropped. The argument for it is real and is made above: eight PRs
  merged with every review recorded only as prose, and GitHub showing zero approvals on #69–#80.
  But GitHub does not let a PR author satisfy their own approval requirement, and this repository
  has effectively one maintainer. Turning it on does not convert review into a record; it converts
  every merge into a wait for a second human. That is the "unnecessary organizational friction"
  worth avoiding, and it would block the current work outright. **If the goal is a queryable review
  record, the cheaper instrument is to post reviews as GitHub reviews rather than PR-body prose** —
  which costs nothing, needs no admin, and is a habit this project can adopt today. Enable the rule
  when there is a second reviewer to satisfy it.
- **Require branches to be up to date before merging** — dropped. Normally sound. Here it is
  actively expensive: `apps/api/isaac_api/data/memory-snapshot.json` is a generated artifact that
  changes on almost every PR, so each merge to `main` already forces every other open PR to
  regenerate it. Adding "must be up to date" would additionally force a full CI re-run on every
  open PR after every merge, serialising a queue that is already serialised by the artifact. It
  buys protection against a merge-result regression that the required checks largely cover, at a
  cost this repository can measure.

  **Addendum, 2026-08-17 — the decision is unchanged, one of its inputs is not.** The concrete
  merge-result regression this rule would have caught had a name: two branches independently
  raising `A11Y_BASELINE_TOTAL_NODES` to the same literal for different reasons, which git merges
  without a conflict while both sets of baseline entries survive. It was real, it recurred, and
  until now its only detector lived in the ~30-minute `browser-a11y` job — so it was found on
  `main`, after the merge, half an hour late.

  That detector now also runs in the fast `frontend` job, on every pull request and every push to
  `main` (`apps/web/e2e/invariants/baseline-aggregate.invariant.test.ts`, logic in
  `apps/web/e2e/baseline-aggregate.ts`). The stale-base window is not closed — a PR merged without
  seeing the current base still fails on `main` rather than before it — but the cost of landing in
  that window fell from **~26 minutes to ~4**, and the failure message now names the merge as the
  likely cause and prints the exact number to write.

  **~4 minutes, not "seconds", and the difference is the point.** An earlier revision of this
  addendum said "to seconds". The *check* is 6 ms locally and 26 ms in CI — but the **signal** costs
  whatever the job costs, and the `frontend` job is `npm ci` + the full vitest suite + `vite build`.
  Measured over the last runs on `main` (`gh api .../actions/runs/<id>/jobs`): `frontend tests and
  build` 3m06s and 3m48s; `browser accessibility and responsive baseline` 26m13s and 26m42s. So the
  honest figure is a ~7× improvement, not ~300×. Quoting the test's own runtime as the feedback
  latency is exactly the kind of unmeasured count `CLAUDE.md` §12 forbids, and it was caught by
  independent review rather than by me.

  **And a second correction, because the sentence above could be read as more than it is.** `main`
  currently has **no required status checks at all** — measured, not assumed:
  `gh api repos/ISAAC-DOE/isaac-metadata-assistant/branches/main --jq '.protected'` → `false`;
  `.../rulesets` → `[]`; `.../branches/main/protection` → `404`. So the fast check **reports; it does
  not block**. A pull request can be merged with it red, or still running. That is this document's
  whole subject and is stated in its header, but it needs saying here too, next to the claim that the
  hazard is now caught quickly.

  So the rule buys less than it did when this section was written, at the same price. Declining it
  remains the right call, and this is recorded so a future reader does not mistake the unchanged
  verdict for an unexamined one.

## A separate, application-owned defect that protection does NOT fix

**`.github/workflows/build-push.yaml` published a deployable image without consulting CI at all.**
It triggered on push to `main`, as `ci.yml` also did, so the two raced and the publish decision
never looked at the test result. On `23ce90f` the image finished publishing at **08:19:17** while
CI attempt 1 was still running; that attempt concluded `failure` at **08:52:37**. The image was
public for 33 minutes before the red result existed.

Branch protection gates *merges*, not *workflow triggers*, so it could not have closed this.

**An earlier draft of this document said the fix was "a `needs:`". That was wrong**, and the error
is worth keeping visible because it is the natural first guess: `needs:` orders jobs **within one
workflow**, and these are two separate workflow files. It cannot reach across them. The fix is a
`workflow_run` trigger ordered after CI, plus a gate job that re-checks the Actions API for the
exact commit — shipped in **PR #82**, with negative and positive controls in
`apps/api/tests/test_release_gate.py` and the full account in
[`release-gating.md`](release-gating.md).

**No infrastructure access was required and none of this should be asked of the owner** — it is
listed here only so the two issues are not confused for one another.

## The one question to answer

> Would you enable branch protection on `main` with the five settings above, or tell us which of
> them you would rather not have?

Nothing in the current work is blocked on the answer.

---

## A message you can send

First-person, for the repository owner. Nothing in it needs an agent to have written it.

> Hi Dean — could you turn on branch protection for `main` on
> `ISAAC-DOE/isaac-metadata-assistant`? It's currently a public repo with no protection and no
> ruleset at all, and I only have push, not admin, so I can't set it myself.
>
> The minimum I'd like is: require a pull request before merging, require the five status checks
> that already run on every PR (`tests and synthetic demo`, `frontend tests and build`,
> `browser accessibility and responsive baseline`,
> `migration and durable repository against a real PostgreSQL`, and
> `build + smoke-test production image (local, no push)`), block force pushes, and block branch
> deletion.
>
> I'm deliberately **not** asking for required approvals or "branch must be up to date" — with one
> maintainer the first blocks every merge instead of recording reviews, and the second would force
> a full CI re-run on every open PR after every merge because of a generated file that changes on
> almost every PR.
>
> Context for why now: a commit shipped a container image about 33 minutes before its own CI run
> finished failing. I've already fixed that half in the repo (the two workflows were racing), so
> this isn't a request to fix that — it's the merge-side protection that the fix doesn't cover.
> Nothing I'm working on is blocked waiting for it.
