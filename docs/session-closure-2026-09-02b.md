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
| `RunsSection` had no change-feed refresh path at all | #222, corrected by #224's contract in #222's own follow-up commit `4151203`, wired live by #226 | `2b8a017` (feat), redesign commit `4151203` pre-merge, wiring merged `fd179f2` | `runs-live-refresh-integration.test.tsx` (#226): exactly one bounded `listRuns` re-read for a colleague's run edit, for a run removal, and when the record poller wins the race |
| A colleague's proposal arrived with no announcement | #222 | `2b8a017` | `proposal-arrival-announcement.test.tsx`; suppressed on hydration, on the panel's own review acts, and on repeated no-op polls |
| The drain budget was exactly exhausted at the row ceiling | #221 | `d5498e8` | `apps/web/src/__tests__/change-feed.test.ts` — hard bound proven: ≤ 26 + T/8000 requests in any T ms window under sustained `has_more`; 100-page drain 645 s → 620.5 s |
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
and the two-actor end-to-end proof) **merged as `fd179f2`** (head `83ef774`, `mergedAt`
2026-09-02T22:57:09Z, verified via `gh pr view 226 --json mergeCommit,mergedAt,state`). Its
independent review returned **MERGE-after-fixes** (quoted verbatim from the review-fix commit
`83ef774`: *"Independent review returned MERGE-after-fixes on this branch"*) on findings I-1, I-2
and four M items, all fixed in that same head commit before merge — see §4.
`docs/evidence/two-actor-workflow-proof-2026-09-02.md` is now present on `main` (confirmed via
`git show origin/main:docs/evidence/two-actor-workflow-proof-2026-09-02.md | head`) — read and
cited in §2.

---

## 2. What was proven, and by what

- **A two-actor proof exists** (#226, merged `fd179f2`, `e2e/trusted/two-actor-workflow.spec.ts`,
  one test, 20 steps): Scientist A holds the Record Workbench open; Scientist B acts over HTTP.
  Create → two runs added through the website → record-scoped proposal by B → A's page announces
  it without reload → reject with reason → run-scoped proposal on the second run → `RunsSection`
  and the panel refresh with exactly one bounded run re-read → three distinct values compared →
  stale protection (`409 proposal_stale`) → accept under the fixture verifier → only the second run
  changed → change feed drained at `limit=200` → validate/export dry-run see the accepted value →
  the permitted MCP tool list carries no submit/export/accept tool. (Quoted from the PR #226 body;
  the review-fix commit `83ef774` corrected three of this proof's own assertions before it could
  be trusted — see §4.) Full evidence, now on `main`:
  [`docs/evidence/two-actor-workflow-proof-2026-09-02.md`](docs/evidence/two-actor-workflow-proof-2026-09-02.md),
  which states its own three tiers of claim rather than blurring them: **proven here** — all 20
  steps, against a real FastAPI process, a real Chromium, and a real filesystem-backed workspace;
  **proven only in CI** — durability across a process restart, against a real PostgreSQL, via
  `apps/api/tests/test_proposal_durability.py`'s real-engine scenarios (cited, never claimed by
  this proof itself); **proven nowhere** — anything hosted, because no shipped deploy artifact
  sets either trusted-identity variable (`test_deploy_config.py` pins that) and hosted acceptance
  answers `409 human_actor_required` — `HOSTED QA PENDING (Krish)`. **B is HTTP, not a second
  browser, for a measured reason, not convenience**: no surface in this build can create a
  proposal (`routes.py`: *"NOTHING WAS REWIRED TO FEED THEM"*), so the reviewed act still happens
  through the visible UI and B only establishes starting state and reads server state back as an
  independent check — except step 13, labelled as the deliberate exception: **its stale-accept
  `409` and the following withdraw are observed from B's HTTP request context, not from A's page**,
  because the guarantee under test is the *server's* refusal (the panel deliberately still offers
  the button regardless).
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
  holding a NUL byte. ~~A sweep of all 1,019 currently-tracked files repository-wide found exactly
  one~~ — **corrected 2026-09-02, independent review of PR #227: `git ls-tree -r b82e555 --name-only
  | wc -l` reads 1020, not 1019, at the commit this figure was first measured against.** Re-measured
  again at this document's own current head, `git ls-tree -r f86fe87 --name-only | wc -l` → **1,023**
  (the branch added files between those two commits — evidence docs and this closure document
  itself). A full byte-level re-sweep at 1,023 files still finds exactly **one** holding a NUL byte —
  the already-documented exemption `qa/validator-upload-package/isaac-validator-qa-files.zip`
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

**The session's most important CI lesson, and it is not one of the per-PR review catches below —
it is that `main`'s own CI failed twice, on two different merge commits, and the release gate is
what stopped either from shipping.**

`main` CI **FAILED at `2b8a017`** (the #222 merge; run `33683247282`, conclusion `cancelled` —
superseded when the next merge landed before it finished) **and at `1ef0c0d`** (the #223 merge;
run `33685271261`): vitest ran clean — `194 passed (194)` files, `5154 passed (5154)` tests — and
then the separate `Build` step failed:

```
src/__tests__/proposal-arrival-announcement.test.tsx(183,3): error TS2741: Property 'runRev' is
missing in type '{ recordMoved: false; runIds: never[]; proposalIds: string[]; proposalStates:
never[]; otherKinds: never[]; highestRev: number; proposalRev: number; }' but required in type
'RecordChangeSummary'.
```

**Cause:** PR #222 added this test file building a `RecordChangeSummary` literal without `runRev`.
PR #224, merged separately, made `runRev` a *required* field of that same type. Each PR was
exact-head green against its own base — neither PR's own CI run ever saw the other PR's diff — and
GitHub reports **mergeability**, not **compilability**: a green checkmark and a "can be merged"
badge on each PR said nothing about whether `tsc -b` would pass on the tree the merge actually
produces. Nobody typechecked the combination before either merge, because nothing in the workflow
does that automatically for a fast-forward of two independently-green branches.

**The release gate is exactly what caught it, and quoting its own log removes any doubt that
something red could have shipped:**

```
release gate REFUSED for 2b8a0170c29889556e0a80668dd3c701c45ffbef: a required 'CI' run for this
commit concluded 'cancelled', not 'success'
release gate REFUSED for 1ef0c0d67713991ce5db26207750f47170e0b4bb: a required 'CI' run for this
commit concluded 'failure', not 'success'
```

Both refusals are quoted verbatim from `gh run view 33685276446 --log` and
`gh run view 33688344451 --log` respectively (also quoted in §8's release table). **Nothing red was
released.** The break was invisible in each PR's own diff and visible only once both landed on
`main` — and even then it was caught by the release gate refusing to tag an image, not by a human
reading a log.

**The fix landed twice, independently, because two branches hit the same break in parallel before
either had seen the other's fix:** PR #225's merge commit `7e29e81` ("Merge origin/main (2b8a017)
into feat/proposals-newest-first") added the missing `runRev: -1` to the same test file, with the
commit message naming `npx tsc -b` — not a test — as what caught it. PR #226's commit `da88c63`
independently hit and fixed the identical break merging the same two producer/consumer branches
together, before #226's own review pass. Both are one-line fixes; neither branch had to guess at
the value, because `-1` is `recordChanges.ts`'s own documented "no run entry survived" sentinel,
not a filler.

**Durable rule for this repository, because "exact-head-green" protects less than it sounds like it
does:** before merging a PR whose base has moved since it went green, re-run `tsc -b` (and the
relevant test suite) **on the merge result** — either `git merge-tree` into a throwaway worktree,
or merge `main` into the branch and let CI run against that merge commit — not just on the PR's own
HEAD against its own stale base. The exact-head-green rule protects the *head*; it says nothing
about the *merge*, and this session produced two counterexamples in the space of nine minutes
(`2b8a017` at 21:06, `1ef0c0d` at 21:27).

~~**`f58e8d2`'s own CI (run `33687944765`) had NOT concluded at the time of writing** — measured
`status: "in_progress"`, `conclusion: ""` via `gh run view 33687944765 --json headSha,conclusion,status`.
This document does not claim `main` is green again; that claim needs a later, successful
conclusion of that specific run, re-checked rather than assumed.~~ — **RESOLVED, this pass:**
re-checked via the same command, `33687944765` now reads `{"conclusion":"success","status":
"completed"}`. `main` at `f58e8d2` released cleanly as **v0.0.211** (§8). `fd179f2` (#226's merge,
now on top of `f58e8d2`) has its OWN separate CI run (`33692815125`) which had, at the time of THIS
paragraph's pass, **not** concluded — see §7/§8 for the run whose conclusion needed confirming.
**That run has since concluded `success` and released as v0.0.212** — see §7/§8 for the completed
figures; this paragraph is left as the historical record of what was known at the time it was
written, per this repository's convention of correcting in place rather than rewriting history.

---

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
| "Exact-head-green protects a merge" | assumed | **FALSE — `main` CI failed at `2b8a017` and `1ef0c0d`, both merges of independently-green PRs whose combination was never typechecked (see §4)** | measured this session, `gh run view 33683247282`/`33685271261` |

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

  **INVESTIGATED AND MEASURED 2026-09-03. The item is UNCHANGED as a residue — nothing was
  built — but it is no longer a design sketch, and one thing it did not say is now measured
  and is the load-bearing part.** Measured over HTTP at `6ce3f5c`, on a record with one run
  and one note:

  | act | record `rev` | served-detail fields that differ | bundle members changed |
  |---|---|---|---|
  | `POST .../proposals` | 2 → 3 | `/rev`, `/version`, `/workflow/record_rev` | **none** |
  | note `edit` review | 2 → 3 | `/rev`, `/version`, `/workflow/record_rev` | `notes` |

  Also measured: the authoritative signature *minus* `proposals` is **byte-identical** across
  the proposal act, and `GET /api/experiments/{id}` with the pre-proposal `If-None-Match`
  answers **200**, not 304 — so `useRecordSync` fires, `handleChanged` runs,
  `RecordWorkbench`'s `onChange` calls `bundle.reloadSilent()`, and the whole bundle is
  refetched.

  **THE ROW THAT MATTERS IS THE SECOND ONE, AND IT KILLS THE CHEAP FIX.** The obvious
  client-side shortcut — "if the fresh detail differs from the held one only in the version
  fields, skip the refetch" — is **unsound, by measurement rather than by caution**: a
  note-text edit produces the *identical* three-field delta while changing a bundle member.
  Every derived summary the detail carries (`status`, `draft_ok`, `pending_count`,
  `evidenced_field_count`, `workflow`) is unmoved by both. So no inference over what the
  server already publishes can separate them, which is precisely why the discriminator has to
  be **served**.

  **THE SERVER HALF IS SOUND AND IS SPECIFIED HERE so it is not re-derived.** A stored
  `content_rev` on the experiment, maintained exactly as `proposal_change_revs` already is:
  a `_content_signature` (the authoritative payload **minus** `proposals`), a
  `_bump_content_rev(next_rev)` called only on `save_versioned`'s write branch, the field
  rolled back with the others on a refused write, persisted in the state document (**no table,
  no migration** — it sits beside `proposal_change_revs`), hydrating to `rev` when absent so a
  legacy document over-reports at most once. It carries **no page-boundary unsoundness**,
  which is the objection #224 raised: it is an ABSOLUTE stored position on the entity, not an
  inference from which entities happened to share a page.

  **WHY IT IS NOT BUILT HERE, named rather than implied.** The client half is not a
  comparison — it is a *version-adoption* problem. `useRecordSession` does not own `version`;
  it reads it straight off the bundle's `detail` (`const version = detail?.version`). Skipping
  `reloadSilent()` therefore leaves `version` stale, so `useRecordSync` would answer 200 on
  **every** subsequent poll and every `If-Match` write would meet 412 — strictly worse than
  the refetch it saves. Consuming the discriminator needs either a data-adoption seam on
  `useFetch` (a generic hook used across the app) or a second owner of the authoritative
  token inside `useRecordSession` — which that module's own header exists to forbid
  ("behind one authoritative `version`/`recordRev`") — plus a change to `RecordWorkbench`'s
  `onChange`. Shipping the served field with no consumer would be the shape this repository
  has already deleted once (`api.getProposal`, *"dead code kept alive by a counter is worse
  than a smaller counter"*). **So: sound, specified, and deliberately not half-built.**
- ~~**`RUN_LIST_LIMIT_MAX` / `RUN_PAGE_MAX` literal duplication is untested.** #222's redesign
  (`5205496` I2) mirrors the server's `RUN_PAGE_MAX = 200` as a client-side `RUN_LIST_LIMIT_MAX`
  literal rather than reading it from the server; nothing pins the two values against drifting
  apart.~~ — **CLOSED 2026-09-03**, and struck rather than deleted because "nothing pins this"
  is a claim a future session acts on. `apps/api/tests/test_run_page_bound_parity.py` asserts
  all three expressions of the one bound agree: the Python constant, the `maximum` FastAPI
  derives from it onto the served `limit` parameter, and the TypeScript literal — failing with
  both numbers named so the message says which side moved. `runPaging.ts`'s own docstring,
  which named this gap, is corrected in place. **The DUPLICATION is not closed, only the
  DRIFT:** serving the bound and reading it needs `RunsSection`'s over-the-cap decision to
  change, which belongs to a slice that owns that component.
- **The change-feed burst budget is still not refilled at the row ceiling, by design.** #221 fixed
  the cliff at and past the budget; it did not add a refill mechanism, so a client that stays caught
  up for a long session still eventually pays the 8 s cadence rather than ever re-entering burst
  mode. Recorded as intended behaviour, not a defect, but worth naming so a future session does not
  "fix" it without re-deriving why.
- ~~**At-least-once delivery / poison-page semantics of the feed consumer are unexamined.** No test in
  this session's PRs establishes what happens if the same page is delivered twice, or if a
  malformed page can wedge the drain loop permanently rather than just slowly.~~ — **EXAMINED AND
  CLOSED 2026-09-03, and it was not only a documentation gap: the sweep found a real defect with
  two halves, both in the one unguarded line of `useChangeFeed`.**

  `cursorRef.current = page.next_cursor` and `page.changes.length > 0` both trusted the wire to
  match the type. **(i)** `changes` not an array — `"abc".length > 0` is `true`, so a string body
  was handed to the consumer AS the entries, and a consumer that iterates would invent one claim
  per character (the same defect `CLAUDE.md` §11 records server-side for `enumerate("abc")`).
  **(ii)** `next_cursor` missing — the cursor became `undefined`, so the next poll carried none and
  the server answered from the **floor of the feed**: one malformed reply silently redelivered the
  record's entire change history as though it were new, on every subsequent poll. That is the
  duplicate-effect hazard the hook's careful deliver-then-adopt ordering exists to prevent,
  arriving through the one line that was not guarded.

  The page is now refused whole when either half fails, which takes the same path a network
  failure takes: **the cursor is not advanced** (so nothing is skipped and the same page is asked
  for again), the failure counts toward `degraded` (so a surface stops claiming to be current),
  and the backoff decays the retry to the 60 s ceiling rather than wedging a fast drain loop.
  Seven tests in `change-feed.test.ts` §8 pin it (counted in the file: the `it(` blocks
  under `describe('useChangeFeed — at-least-once delivery and poison pages')`), and both halves of the guard were
  **mutation-checked**: deleting the `Array.isArray` clause turns two RED, deleting the
  `typeof next_cursor` clause turns one RED. The section also states out loud what the feed IS —
  **at-least-once, not exactly-once** — with a test asserting the duplicate page is delivered
  twice and moves the cursor only forward, so a future dedupe cannot land silently.
- **`isaac_runs` Stage 2b** and an apply route for `POST /ingestion/csv/preview` remain unchanged —
  the latter is a committed human decision (CLAUDE.md §15), not residual work.
- **PR #226 has MERGED, as `fd179f2`**, since the previous pass of this document. Its wiring
  (`RunsSection` now consuming both `runActivity` and `recordVersion`; the change feed paged at
  `limit: 200`; the two-actor proof) passed its own independent review (§4, verdict
  MERGE-after-fixes). ~~`fd179f2`'s own CI run had **not yet concluded** at the time of this
  pass (run `33692815125`, `status: in_progress`) — it has not released an image and has not been
  hosted-QA'd.~~ — **RESOLVED: `33692815125` concluded `success`** (re-verified via `gh run view
  33692815125 --json conclusion`), and the release gate then ran as `33695480008`, printing
  `commit under release: fd179f23e6b77ffd05a91722e1873bad64365c50` and setting `TAG="v0.0.212"`;
  `git rev-list -n1 v0.0.212` resolves to `fd179f2` — released as **v0.0.212**. See §8 for the
  completed table row. **Hosted QA is still unobserved from this environment** and remains
  `HOSTED QA PENDING (Krish)` regardless of the image having released — a release is not a hosted
  verification.

---

## 7. Measured state — SECOND PASS (complete)

This was a two-part second pass. Part 1 filled every marker answerable from git/gate-log state,
from THIS worktree, after merging `origin/main`. Part 2 — the main-checkout backend, frontend,
`tsc -b` and snapshot counts — was **measured in the main checkout at `fd179f2` by the
orchestrator**, `/Users/krishverma/Documents/ISAAC`, clean tree, because a worktree cannot produce
the main-checkout skip count (`graphify-out/graph.json` is gitignored and absent from every
worktree; CLAUDE.md §11 and the first session's closure note both record the +2 skew this causes).
All Part-2 figures below are quoted as measured by the orchestrator, not re-run in this worktree.

- **Backend, measured in the main checkout at `fd179f2` by the orchestrator:**
  `.venv/bin/pytest -q -rs` → **7,131 passed, 45 skipped, 0 failed**, exit 0, 475.78 s.
- **Backend skip classification** (from `SKIPPED [n]` line multipliers, 11 distinct lines summing
  to 45), measured in the main checkout at `fd179f2` by the orchestrator: **34** —
  `ISAAC_RUN_REAL_ENGINE_PARITY` not set (was 32 at the first session's baseline; **+2** are the two
  run-scoped durability scenarios #223 added, both of which CI runs with
  `ISAAC_REQUIRE_REAL_ENGINE_PARITY`, so an absent engine there fails rather than skips); **1** —
  `ISAAC_REQUIRE_REAL_ENGINE_PARITY` not set; **4** — opt-in benchmarks (`ISAAC_PERF_BENCH`: 2
  wall-clock + 1 scale envelope + 1 opt-in); **2** — psycopg2-installed (each names its
  unconditional sibling); **4** — strict-reader tolerances (`source`/`draft`/`created_utc`/
  `answer_log`, each covered by a route test). Total **45**, none an untested path wearing an
  environment gate. A worktree reads **+2** (47) — consistent with the +2 skew named above, and
  this worktree's own `pytest` run (§ notes elsewhere in this document) is not being re-quoted here
  for that reason.
- **Frontend, measured in the main checkout at `fd179f2` by the orchestrator:** `cd apps/web &&
  npx vitest run` → **195 files / 5,174 tests passed**, exit 0 (baseline at the first session's
  final SHA `504c2ee` was 191 files / 5,074 tests).
- **`tsc -b`, measured in the main checkout at `fd179f2` by the orchestrator:** exit **0**.
- **Snapshot `--check`, measured in the main checkout at `fd179f2` by the orchestrator:** no drift
  on both artifacts; served path set **201** / manifest **200**, unchanged from the first session's
  final state. This worktree's own `--check` (after merging `origin/main` and regenerating both
  artifacts here) also read exit 0 with no drift — the two independent checks agree.
- **PR #226 merge SHA: `fd179f2`** (`git log --oneline -1 origin/main`; `gh pr view 226 --json
  mergeCommit,mergedAt,state` → `mergeCommit.oid: fd179f23e6b77ffd05a91722e1873bad64365c50`,
  `mergedAt: 2026-09-02T22:57:09Z`, `state: MERGED`).
- **PR #226 review verdict: MERGE-after-fixes**, quoted verbatim from the review-fix commit
  `83ef774`'s own message (*"Independent review returned MERGE-after-fixes on this branch"*), after
  findings I-1, I-2 and four M items were fixed in that same commit — see §4.
- **`f58e8d2`'s CI: SUCCESS.** Run `33687944765`, re-verified via `gh run view 33687944765 --json
  headSha,conclusion,status` → `{"conclusion":"success","headSha":"f58e8d2…","status":"completed"}`.
  Release gate run `33691355159` printed `commit under release:
  f58e8d27afe9ab829da369e081f3b41409ece2bd` and its build job set `TAG="v0.0.211"`;
  `git rev-list -n1 v0.0.211` resolves to `f58e8d2`. §8's table row for `f58e8d2` is filled in below.
- ~~**`fd179f2`'s CI: still PENDING**, re-verified at the time of this pass via `gh run list
  --branch main --workflow CI --json headSha,status,conclusion` → `{"conclusion":"",
  "headSha":"fd179f2…","status":"in_progress"}`. §8's table row for `fd179f2` is left explicitly
  marked pending, not guessed, per the coordinator's instruction not to infer a conclusion.~~ —
  **RESOLVED: `fd179f2`'s CI (run `33692815125`) concluded `success`**, re-verified via
  `gh run view 33692815125 --json conclusion` → `{"conclusion":"success"}`. Release gate run
  `33695480008` printed `commit under release: fd179f23e6b77ffd05a91722e1873bad64365c50` and set
  `TAG="v0.0.212"`; `git rev-list -n1 v0.0.212` (after `git fetch --tags`) resolves to `fd179f2`.
  §8's table row for `fd179f2` is now filled in with the released outcome, not left pending.
- `docs/evidence/two-actor-workflow-proof-2026-09-02.md` — **confirmed present on `main`**
  (`git show origin/main:docs/evidence/two-actor-workflow-proof-2026-09-02.md | head` succeeds) —
  and **confirmed NOT in the manifest or the served path set** after regenerating both artifacts in
  this worktree: manifest stayed at exactly 200 entries and the served set at 201, and neither this
  document's own path nor the two-actor evidence doc's path appears in either. **This means the
  manifest bucket table in `CLAUDE.md` §17 ("37 | `docs/**` (excluding `docs/superpowers/`)") is not
  a live discovery rule** — the manifest builder does not automatically add every new `docs/**`
  file; whatever mechanism keeps that bucket at 37 either enumerates a fixed list or something else
  gates it. This is worth a future session's attention but is out of scope for this closure note to
  fix.
- **Open PRs / worktrees / stranded work at the true end of this session**, measured by the
  orchestrator from the main checkout: **open PRs — none, except this closure document's own PR**
  (to be opened from this branch after this pass); **worktrees — two**, the main checkout plus this
  one; **stranded work — none**, all eight of this session's branches measured **0 ahead of
  `origin/main`** and had their local refs deleted.

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
| `f58e8d2` | #225 | `33691355159` | `commit under release: f58e8d2…` → success | **v0.0.211** |
| `fd179f2` | #226 | `33695480008` | `commit under release: fd179f2…` → success | **v0.0.212** |

**See §4 for why both merges broke `tsc -b` on `main` despite each PR being green on its own head — the underlying cause, not just the refusal.** Read the two refusals precisely; they are not the same reason. `2b8a017`'s own CI run was
*cancelled* (superseded by the next merge landing before it finished). `1ef0c0d`'s own CI run
*concluded `failure`* — the gate log does not say cancellation for this one, and this document
does not assert it did. Both merge commits are superseded in the fast-forward history by later
commits whose own CI did complete successfully, so neither being unreleased blocks anything;
naming this precisely matters because a future reader should not assume every rapid-merge sequence
fails release for the identical reason.

`f58e8d2` released cleanly as **v0.0.211** — re-verified this pass via `gh run view 33687944765
--json headSha,conclusion,status` (CI: success) and `gh run view 33691355159 --log | grep -a
"commit under release\|TAG="` (`commit under release: f58e8d27afe9ab829da369e081f3b41409ece2bd`;
`TAG="v0.0.211"`), and cross-checked with `git rev-list -n1 v0.0.211` resolving to `f58e8d2`.

~~`fd179f2` (PR #226's merge) has **not yet completed its own CI run**, re-confirmed at the time of
this pass via `gh run list --branch main --workflow CI --json headSha,status,conclusion` →
`{"conclusion":"","headSha":"fd179f2…","status":"in_progress"}`. Do not read the row above as a
refusal; it is a status that has not arrived yet, and is deliberately left distinguishable from
`2b8a017`'s and `1ef0c0d`'s actual refusals. This document does not fill in `fd179f2`'s release-gate
row or image tag, because neither exists yet — a third session (or a later check of this same PR)
would need to observe and record that conclusion when it lands.~~ — **RESOLVED, one further pass
later.** `fd179f2`'s CI (run `33692815125`) concluded `success` — re-verified via `gh run view
33692815125 --json conclusion`. Release gate run `33695480008` then ran and printed `commit under
release: fd179f23e6b77ffd05a91722e1873bad64365c50` and its build job set `TAG="v0.0.212"`;
`git rev-list -n1 v0.0.212` (after `git fetch --tags`) resolves to `fd179f2`. `fd179f2` released
cleanly as **v0.0.212**, and the table row above is now filled in rather than left pending.
**This does not touch hosted QA**, which remains `HOSTED QA PENDING (Krish)` for every image from
this session regardless of release — a successful release-gate tag is not an observation of the
hosted deployment.
