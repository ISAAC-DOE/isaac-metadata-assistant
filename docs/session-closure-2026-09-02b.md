# Session closure — 2026-09-02 (second session): closing the five gaps the first session named

**Read §6 first if you are resuming.** It is the only section that authorizes anything.

Every number here was either measured in this session (command given) or is quoted from a
PR body / commit message with `(from PR #N, not re-measured here)`. Nothing is invented.

---

## 1. The question this session was given, and the answer per gap

The previous session's closure note (`docs/session-closure-2026-09-02.md` §7, "Application-side,
named rather than implied") left five gaps. This session closed all five that were application-side
and reachable, plus wired the two live-refresh halves together and proved the full two-actor
workflow. One gap (`RunsSection` has no refresh path) needed two follow-on PRs to close correctly,
because the first attempt at the consumer side had defects an independent review caught before
merge.

| Gap (from the first session's §7) | Closed by | Merge SHA | Direct proof |
|---|---|---|---|
| `RunsSection` had no change-feed refresh path at all | #222, corrected by #224's contract in #222's own follow-up commit `4151203`, wired live by #226 | `2b8a017` (feat), redesign commit `4151203` pre-merge, wiring in #226 (pending) | `runs-live-refresh-integration.test.tsx` (#226): exactly one bounded `listRuns` re-read for a colleague's run edit, for a run removal, and when the record poller wins the race |
| A colleague's proposal arrived with no announcement | #222 | `2b8a017` | `proposal-arrival-announcement.test.tsx`; suppressed on hydration, on the panel's own review acts, and on repeated no-op polls |
| The drain budget was exactly exhausted at the row ceiling | #221 | `d5498e8` | `useChangeFeed.test.ts` — hard bound proven: ≤ 26 + T/8000 requests in any T ms window under sustained `has_more`; 100-page drain 645 s → 620.5 s |
| Events refetched the full record bundle including unbounded `/pending` | #224 | `0cd8f6b` | `live-refresh-request-graph.test.tsx`: one run edit, record poller first, 44 req / 4 bundles / 4 unbounded `/pending` → 17 / 1 / 0 |
| Run-scoped proposals were "structurally untestable" | #223 | `1ef0c0d` | `test_run_scoped_proposal_lifecycle.py` (30 tests) + `e2e/trusted/*` (5 specs), on a record created through `POST /api/experiments` with two runs |

A sixth item not in the original five but found and closed in the same arc: a newly arrived
proposal on a record already holding 50+ proposals was counted by #222's announcement but not
reachable on the panel's first page (oldest-first, 50-entry default window). Closed by #225
(`newest_first` order + "Show Newest"), merged `f58e8d2`.

A seventh, unrelated to the five gaps but found by independent review mid-session: the Assistant
Companion's lead copy said "nothing you do there changes a record here unless you come back and
change it yourself," which was false the day it shipped — the companion's permitted MCP tool set
already included `isaac_answer_questions`, `isaac_create_run` (direct writes) and
`isaac_propose_field_value` (a reviewable suggestion). Closed by #220, merged `542fe17`.

PR #226 (wiring `RunsSection` to the two live-refresh producers, paging the change feed at 200,
and the two-actor end-to-end proof) is **open, not merged**, at head `83ef774` at the time of
writing. Its independent review already ran and returned three findings (I-1, I-2, four M items),
fixed in that same head commit — see §4. TODO(second pass): merge SHA, release entry, and the
evidence doc it will add (`docs/evidence/two-actor-workflow-proof-2026-09-02.md`).

---

## 2. What was proven, and by what

- **A two-actor proof exists** (#226, `e2e/trusted/two-actor-workflow.spec.ts`, one test, 20
  steps): Scientist A holds the Record Workbench open; Scientist B acts over HTTP. Create → two
  runs added through the website → record-scoped proposal by B → A's page announces it without
  reload → reject with reason → run-scoped proposal on the second run → `RunsSection` and the
  panel refresh with exactly one bounded run re-read → three distinct values compared → stale
  protection (`409 proposal_stale`) → accept under the fixture verifier → only the second run
  changed → change feed drained at `limit=200` → validate/export dry-run see the accepted value →
  the permitted MCP tool list carries no submit/export/accept tool. (Quoted from the PR #226 body;
  the review-fix commit `83ef774` corrected three of this proof's own assertions before it could
  be trusted — see §4.)
- **Run-scoped proposals are provable end to end** (#223): 30 backend tests target paths derived
  at import from the server's own `PROPOSAL_TARGET_PATHS` / `_proposal_writer_for` /
  `_PROPOSAL_WRITER_SCOPE`, on an experiment with two runs, deliberately targeting the second;
  isolation asserted on the untargeted run's whole served document. Re-measured here:
  `PROPOSAL_TARGET_PATHS` has **18** entries, of which **17** resolve to a run writer
  (`run_field` or `run_override`) and exactly **1** (`system.technique`) resolves to
  `record_enum_fields` —
  ```
  .venv/bin/python -c "import sys; sys.path.insert(0,'apps/api'); from isaac_api import routes; \
    paths=sorted(routes.PROPOSAL_TARGET_PATHS); print(len(paths)); \
    print([routes._proposal_writer_for(p) for p in paths])"
  ```
  confirming the PR's "closed-enum `run_field` target, an unconstrained-string `run_override`
  target" characterization names real, distinct members of the 17.
- **The drain contract is measured, not asserted** (#221, `docs/change-feed-client-contract.md`):
  a deterministic paging server under fake timers, 1,050-entry backlog (21 pages), drained in 13 s
  before and after (exactly at the budget); one page past the budget: 21.0 s → 13.5 s; four past:
  45.0 s → 20.5 s; 100 pages: 645 s → 620.5 s. Sustained `has_more` over 60/120/600 s windows:
  26/34/94 requests before, 29/37/97 after, against a proven bound of 33/41/101.
- **The request graph is measured on a real browser and a real backend** (#224,
  `docs/evidence/live-refresh-request-graph-2026-09-02.md`): 15 runs / 42 questions, event window
  128,718 B → 97,217 B (−24.5%), entirely from `GET /pending` (41,944 B) collapsing to `?limit=10`
  (10,443 B). Quiet control and DOM output unchanged. (Both figures from PR #224 body, matching the
  evidence doc's own title and scope; not independently re-run in this closure pass.)

---

## 3. The premises that proved false

- **"Run-scoped proposals are structurally untestable."** The first session's closure note gave
  this as a fact about the product. It was a fact about the two exported *seed* records the
  browser mutation suite happens to use, which refuse `POST .../runs`. `POST /api/experiments` —
  the product's own ordinary create path — works fine and takes runs. #223's test suite is built
  on a record created that way, not on either seed.
- **The closure note's own release table.** `504c2ee` (PR #215) was recorded as "CI still running
  at the time of writing." It had, in fact, finished and released as `v0.0.206` while PR #219 (the
  closure doc's own PR) sat open — corrected in `4748fda`, quoted in full in §5 below.
- **"0 open PRs · 1 worktree · none stranded."** Measured from *inside* PR #219, which was itself
  open at the time — so the true count was at least 1. Same commit, same correction.
- **CLAUDE.md §11's live NUL-byte trap.** The file said the trap was "LIVE AGAIN, IN A DIFFERENT
  FILE" — `components/RecordDescriptionPanel.tsx`, 2 NUL bytes from an unescaped `rows.join('\0')`.
  Re-measured in this session:
  ```
  python3 -c "print(open('apps/web/src/components/RecordDescriptionPanel.tsx','rb').read().count(b'\x00'))"
  ```
  → **0**. A sweep of all 397 files currently tracked under `apps/web/src` found **zero** files
  holding a NUL byte. A sweep of all 1,019 currently-tracked files repository-wide found exactly
  **one** — the already-documented exemption `qa/validator-upload-package/isaac-validator-qa-files.zip`
  (918 NUL bytes). The file was fixed (consistent with the mechanical guard
  `apps/web/src/__tests__/source-is-greppable.test.ts` that the same paragraph says now exists) and
  the "IS LIVE AGAIN" claim is stale. Corrected in `CLAUDE.md` §11 in place — see §7 below. The
  durable rule the paragraph teaches — a `grep`/`rg` sweep of this tree is only evidence of absence
  when run with `-a` — is unaffected and is not withdrawn.
- **The companion's own lead sentence** — "nothing you do there changes a record here unless you
  come back and change it yourself" — asserted a boundary the shipped tool set had already crossed.
  #220 corrected it in place with a dated comment rather than silently rewriting it, per this
  repository's convention. (See §1.)
- **The change feed's published rate bound.** PR #221's own body records that a first version of
  the bound "had no premise" and that two of its own tests "proved nothing" under a flapping
  server. Re-derived: the reproduction harness measured 100-page drains costing 10 min 45 s (645 s)
  before the fix under sustained `has_more`, and the new bound is proven — not merely observed — to
  hold at ≤ 26 + T/8000 requests in any T ms window, including under a server whose responses flap
  between success and `422 malformed_cursor` (the harness names 85 s / 60 s intervals for that
  case). (From PR #221 body / `docs/change-feed-client-contract.md`; not independently re-run
  here.)
- **The proposals count line described an order the response never carried.** #225's review found
  that `.proposals-count`'s clause was built from client-side `order` request state, not from what
  the response actually returned, so a 503 mid-flight left the line reading "… newest first" over
  zero (stale) cards, and there was no live-region utterance once the claim became true again. Fixed
  by publishing `order` in the response envelope itself and rendering only from the response. See
  §4.

---

## 4. What independent review found that CI did not

One line each, in review order. Every one of these passed its PR's full test suite before review
and would have merged wrong without an independent second pass.

- **#222 (I1):** two mutants survived the arrival-announcement guard — a signal-driven reload whose
  open count did not rise still announced an arrival (an `>=` gate should have been `>`), and the
  `arrivalReloadRef` reset could leak its flag onto a later, unrelated request.
- **#222 (I2):** a signal-driven reload of `RunsSection` truncated a reader's Load More progress on
  a colleague's edit — it reloaded page one instead of re-requesting the size the reader had
  already grown the list to.
- **#224 review, fixed in `4151203` (folded into #222's branch before merge):** the consumer
  gated on `highestRev`, which a stale proposal position inflates and which the swallow branch
  recorded even after the producer's floor had advanced (permanently losing a wrongly-swallowed run
  change); and it parsed the loaded rev as `<generation>.<rev>` while discarding the generation
  half, so a signal after a generation change read as already-seen.
- **#224 review (`a06ffff` I1):** the Assistant chip's `pendingTotal` figure was unpinned — no test
  anywhere named it, and reverting it to `pending.length` passed the full suite unchanged.
- **#224 review (`a06ffff` I3):** `api.getPending`'s documented "still correct twice, do not fix
  those two" instruction in CLAUDE.md §11 had gone stale the moment this slice paged one of the two
  call sites on its live-refresh path; struck and annotated rather than silently rewritten.
- **#223 review (`d8c905c` I1):** a test's own docstring claimed it "shows the same key on a
  DIFFERENT record minting its own" while the test body created no second record at all — the
  assertion the docstring described did not exist.
- **#223 review (`d8c905c` I2):** two literals (`SECOND_RUN_FIELD_PATH`, `SECOND_RUN_FIELD_VALUE`)
  sat under a comment claiming they were derived from the application's own writable-path set "for
  the reason `RECORD_VALUE` is" — they were not; the comment was made true by deriving them, rather
  than deleted.
- **#223 review (`d8c905c` I3):** the `@real_engine` scenario count had grown to six, but three
  sites (a CI skip guard, its converse, and a docstring) still said four.
- **#225 review (`a6cf884` I1):** the proposals count line's "newest first" / "oldest first" clause
  was built from client `order` request state rather than from the response — during a mid-flight
  503 it described a claim about a window that had never loaded.
- **#226 review (`83ef774` I-1):** step 17 of the two-actor proof asserted `changed_at_rev > 0`
  under the label "is above the pre-accept cursor" — but the change feed floors every served
  position at ≥ 1 on read, so no entry the feed could ever return would fail that assertion. It was
  comparing against zero, not against the pre-accept cursor the message claimed.
- **#226 review (`83ef774` M-2):** step 11 asserted a count only ever *reached* one
  (`expect.poll(...).toBe(1)`), never that it *stayed* one — a bound firing once per poll rather
  than once per event would have passed identically.
- **#226 review (`83ef774` M-4/I-1(b)):** two per-entry loops in the proof could iterate zero times
  and still read as a pass; now each asserts its own list is non-empty before checking its content.
- **#226 review (`83ef774` I-2):** the evidence doc and a commit message contradicted each other
  about whether the mutation suite had run on that branch — the doc said "not run," the commit
  reported 113 passed. The commit was right; the doc was stale prose never re-checked.

---

## 5. Measurements that corrected a prior claim

| Claim | Was | Corrected to | Source |
|---|---:|---:|---|
| Drain cost, one page past budget | 21.0 s | **13.5 s** | #221 body |
| Drain cost, four pages past budget | 45.0 s | **20.5 s** | #221 body |
| Drain cost, 100 pages | 645 s | **620.5 s** | #221 body |
| Request graph, one run edit (record poller first) | 44 req / 4 bundles / 4 unbounded `/pending` | **17 / 1 / 0** | #224 body |
| Request graph, one proposal act | 45 req / 4 bundles / 4 unbounded `/pending` | **18 / 1 / 0** | #224 body |
| Real-browser event window | 128,718 B | **97,217 B** (−24.5%) | #224 body |
| Run-scoped proposal targets | "untestable" | **17 run-scoped (`run_field`/`run_override`) + 1 record enum, of 18 total** | measured this session, see §2 |
| Release of `504c2ee` | "not yet released" | **`v0.0.206`** | `4748fda` |
| Open PRs at PR #219's own writing | 0 | **1** (itself) | `4748fda` |
| CLAUDE.md §11 NUL-byte trap | "live again" in `RecordDescriptionPanel.tsx`, 2 bytes | **0 bytes; 0 files under `apps/web/src`; 1 file repo-wide (the documented zip exemption)** | measured this session, see §3 |
| Proposals newest-arrival reachability | counted but not on the visible page past 50 entries | **`newest_first` order + "Show Newest" makes it reachable without paging** | #225 body |

---

## 6. What is NOT done — the only section that authorizes anything

### External gates (nobody in this repository may close these)

**Dean / operator / SLAC**
- `0005_run_projection` approval and hosted application; any later migration.
- Gate **G2** (per-record hosted display) and **G3** (the five withheld aggregates).
- Production remote MCP and OAuth routing.
- **The infrastructure half of trusted identity.** Until it exists, `accept` answers `409
  human_actor_required` in every deployment, and `attribution.uploaded_by` stays unset. No
  application change can close this — confirmed again this session: #223 and #226's proofs both
  run only under the deterministic fixture verifier (`ISAAC_EDGE_TRUST_VERIFIER=test_fixture`),
  and `test_deploy_config.py` pins that no shipped artifact sets it.
- Dean's **D1–D9** deferral is unchanged: no production provider, credential, endpoint, or charge.

**Angel** — the six unclassified `system.configuration.*` fields. Nothing this session touched them
and nothing is blocked on them.

**Krish / authenticated human**
- **`HOSTED QA PENDING` for every image from this session.** `/krish` sits behind an Authentik edge
  this environment cannot authenticate to.
- The genuine browser **200%-zoom sign-off** — no CDP method, flag, or API can drive it.
- Team Owner artifact review and private artifact sharing; a real Claude voice-plus-MCP smoke test.
- Personal Vercel and Railway retirement, preserving the Railway volume.

### Application-side residue, named rather than implied

- **A proposal act still costs one full bundle refetch**, including its bounded `/pending`. #224
  deliberately declined to conclude "proposal-only" from a single feed page — a page boundary can
  split one save's entities across two pages, making that inference unsound. The sound fix is a
  server-side revision discriminator so a proposal-only act need not refetch the whole record
  bundle; tracked, not built.
- **`RUN_LIST_LIMIT_MAX` / `RUN_PAGE_MAX` literal duplication is untested.** #222's redesign
  (`5205496` I2) mirrors the server's `RUN_PAGE_MAX = 200` as a client-side `RUN_LIST_LIMIT_MAX`
  literal rather than reading it from the server; nothing pins the two values against drifting
  apart.
- **The change-feed burst budget is still not refilled at the row ceiling, by design.** #221 fixed
  the cliff at and past the budget; it did not add a refill mechanism, so a client that stays caught
  up for a long session still eventually pays the 8 s cadence rather than ever re-entering burst
  mode. Recorded as intended behaviour, not a defect, but worth naming so a future session does not
  "fix" it without re-deriving why.
- **At-least-once delivery / poison-page semantics of the feed consumer are unexamined.** No test in
  this session's PRs establishes what happens if the same page is delivered twice, or if a
  malformed page can wedge the drain loop permanently rather than just slowly.
- **`isaac_runs` Stage 2b** and an apply route for `POST /ingestion/csv/preview` remain unchanged —
  the latter is a committed human decision (CLAUDE.md §15), not residual work.
- **PR #226 is unmerged** at the time of writing. Its wiring (`RunsSection` now consuming both
  `runActivity` and `recordVersion`; the change feed paged at `limit: 200`; the two-actor proof) has
  passed its own independent review (§4) but has not gone through CI on `main`, has not released an
  image, and has not been hosted-QA'd. Nothing in §1's table should be read as "shipped to
  production" until §7 below is filled in.

---

## 7. Measured state — SECOND PASS

The figures below are placeholders pending PR #226's merge. Do not treat any number in this
section as measured until the markers are replaced.

- Backend test count at final SHA, main checkout: TODO(second pass)
- Frontend test count / file count at final SHA: TODO(second pass)
- `tsc -b` result: TODO(second pass)
- Snapshot `--check` result (both artifacts): TODO(second pass)
- Served path set / manifest counts (should remain 201 / 200 unless a slice added or removed a
  served path): TODO(second pass)
- Backend skip count and classification (baseline this session started from: 43, per the first
  session's closure doc §8): TODO(second pass)
- PR #226 merge SHA: TODO(second pass)
- PR #226 image version / release-gate row: TODO(second pass)
- `docs/evidence/two-actor-workflow-proof-2026-09-02.md` — confirm it exists on `main` and is
  manifest-listed or not: TODO(second pass)
- Open PRs / worktrees / stranded work at the true end of this session: TODO(second pass)
- Whether this document (`docs/session-closure-2026-09-02b.md`) itself is in the served-content
  manifest: **measured now, not deferred** — see §8.

---

## 8. Release state (from gate logs)

All SHAs and tags below were read from each release-gate run's own log output
(`gh run view <id> --log`), not from `gh run list`'s `headSha` field — the latter reports the
*trigger* commit, which the first session's closure note names as a live trap (`docs/session-closure-2026-09-02.md` §6).

| Merge commit | PR | Release-gate run | Result | Released as |
|---|---|---:|---|---|
| `f4ccfc2` | #219 | `33675702145` | `commit under release: f4ccfc2…` → success | **v0.0.207** |
| `542fe17` | #220 | `33679340952` | `commit under release: 542fe17…` → success | **v0.0.208** |
| `d5498e8` | #221 | `33682586441` | `commit under release: d5498e8…` → success | **v0.0.209** |
| `0cd8f6b` | #224 | `33685927878` | `commit under release: 0cd8f6b…` → success | **v0.0.210** |
| `2b8a017` | #222 | `33685276446` | **REFUSED** — `release gate REFUSED for 2b8a017…: a required 'CI' run for this commit concluded 'cancelled', not 'success'` | never released |
| `1ef0c0d` | #223 | `33688344451` | **REFUSED** — `release gate REFUSED for 1ef0c0d…: a required 'CI' run for this commit concluded 'failure', not 'success'` | never released |
| `f58e8d2` | #225 | (final `main` at time of writing) | pending — release gate had not yet reported at time of writing | TODO(second pass) |

**Read the two refusals precisely; they are not the same reason.** `2b8a017`'s own CI run was
*cancelled* (superseded by the next merge landing before it finished). `1ef0c0d`'s own CI run
*concluded `failure`* — the gate log does not say cancellation for this one, and this document
does not assert it did. Both merge commits are superseded in the fast-forward history by later
commits whose own CI did complete successfully, so neither being unreleased blocks anything;
naming this precisely matters because a future reader should not assume every rapid-merge sequence
fails release for the identical reason.

TODO(second pass): `f58e8d2`'s (#225's) release-gate outcome, and PR #226's merge SHA plus its
release-gate outcome, once #226 merges.
