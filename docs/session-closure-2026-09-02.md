# Session closure — 2026-09-01/02: the proposal workflow was broken in four places

**Read §7 first if you are resuming.** It is the only section that tells you what to do next.

Every number here was measured in this session and carries the command that produced it.
Where a figure could not be measured, this document says so rather than estimating.

---

## 1. The question this session was given, and the answer

*Does the full Claude / MCP proposal workflow actually work for a scientist?*

**It did not, and it was broken in four places rather than the one the previous session
identified.** The previous session's closure note said, honestly:

> **What was NOT built, and was not faked to satisfy a proof step:** there is **no proposal
> inbox in the frontend**. `lib/api.ts` carries zero proposal references.

That was accurate — `git show 7ff8194:apps/web/src/lib/api.ts | grep -ac proposal` returns **0**
— and it understated the problem. The four breaks:

| # | Break | Closed by |
|---|---|---|
| 1 | No website proposal review surface | #212 |
| 2 | **No MCP tool could create a proposal at all** — 10 tools, none proposal-related; `Scope` had two members | #214 |
| 3 | `artifact_link.py` was 235 lines of **dead code** — no route registered it, nothing imported it | #215 |
| 4 | The panel's change-feed refresh **lost a race it usually lost** | #216 |

Break 2 is the one nobody had named. The mission's workflow routes Claude through MCP, and
`docs/ingestion-proposal-contract.md` §4 had specified the surface on 2026-08-30 — but
`PERMITTED_TOOL_NAMES` held ten tools and not one of them touched a proposal. The HTTP routes
were complete and unreachable from any agent.

---

## 2. What is now proven, and by what

`apps/web/e2e/mutation/proposals.spec.ts` drives the workflow through the **visible UI**, in a
suite with its own backend, its own workspace, `workers: 1`, `retries: 0`. Ten of eleven steps
are proven in a browser: the proposal visible on the website; current versus proposed
distinguishable; source, rule, timestamp and derived excerpt shown; **reject with and without a
reason**; withdraw; supersede; **pending by inaction**; closed proposals readable with their
history; truthful over unreadable entries.

**The eleventh is not a gap.** `409 proposal_stale` is unreachable through that screen in a
default deployment, because the attributability gate runs *before* the target-digest comparison —
so an accept on a stale proposal answers `human_actor_required` first. DEC-1's derived
`target_stale` **is** proven both ways in the browser (an unrelated note moves `rev` and leaves it
`false`; editing the target flips it `true`), and the refusal itself is covered in
`apps/api/tests/test_ingestion_proposals.py`. Classification: *existing functionality needing
different evidence*.

**Durability is measured, not inferred.** `apps/api/tests/test_proposal_durability.py`, 14
scenarios, against a real `postgres:18` in CI:

```
proposal durability: 14 scenarios ran against the real engine, none skipped
```

The four engine-gated tests had never executed anywhere before that run. There is no PostgreSQL
and no container runtime on the development machine, and nothing was installed to manufacture one.

---

## 3. The acceptance question, answered rather than sidestepped

**`accept` answers `409 human_actor_required` in every default-configured deployment and writes
nothing.** That is a CONFIGURATION fact, not a defect: no verifier in this build reads a request,
and the trusted authentication boundary has not been built. The browser suite proves the refusal
through a real click, then confirms the record is untouched by **four independent reads** — draft
value, proposal state, `history.length === 1`, record `rev` — and then withdraws the proposal,
proving the banner's promise that refusing acts still work (DEC-9).

It does **not** assume acceptance is unreachable. `assertNoAttributableActor` reads
`/api/health`'s `submission.blockers` first, so the spec states its premise out loud; that guard
was verified load-bearing by running it against a fixture-verifier backend and watching it fail
with its own message.

**The canonical-mutation leg WAS measured.** With `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` and
`ISAAC_FIXTURE_ACTOR_SUBJECT`, accepting through the real button gave `reviewStatus 200`, draft
`system.technique` `HERFD-XAS` → `XRD`, `state accepted`, `applied_via record_enum_fields`, and
`subject null` / `trust_basis unattributed` — **I7 holding exactly as designed**, since a
perfectly verified actor in a tutorial session still stamps nothing.

**It is not committed as a browser test, for a structural reason rather than a decision to skip.**
The verifier is chosen from the *backend process's* environment and that suite starts one backend,
so the refusal leg and the success leg cannot both be measured in one run — and the refusal is the
configuration every shipped deployment has. The success leg is already covered by
`test_I4_accept_succeeds_and_stamps_the_actor_under_the_fixture_verifier`.

---

## 4. The Critical this session found, and why CI could not

`isaac_propose_field_value` was first given `PROPOSALS_WRITE` **alone**, to satisfy contract §4's
*"can create a proposal and read nothing else"*. The safety case was that the handler returns a
**built** projection rather than the route body — true of the **success** branch. Independent
review measured the other one:

```
if_match='"0.0"'   -> 412 {"current_rev": 1, "current_version": "...1"}
if_match='"...1"'  -> 200, proposal STORED, envelope etag "...2"
bad span           -> 422 {"note_text_length": 55}
```

`_failed` forwards the route's body whole. **One extra request bootstrapped the documented wall**,
and each success envelope's `etag` sustained the session indefinitely. Bogus ids gave existence
oracles besides.

**Four published claims were false**, the worst on the Settings screen a scientist reads *before
granting the permission*: *"an agent holding it alone still cannot finish, because writing a
suggestion needs the record's current version and only a read can supply that."*

Fixed by requiring `{READ, PROPOSALS_WRITE}`. Projecting the refusal instead would have made the
docstring true and the deployment shape **inert** — such a principal could then never obtain an
ETag and never create anything, and a capability that cannot work is not least privilege.
`RESULT_CARRIES_NO_RECORD_CONTENT` and `_PROPOSAL_ACK_KEYS` were **removed rather than left
empty**, because with every proposer holding `READ` each withheld key is one `isaac_get_proposal`
away, and keeping them would leave a construction that *looks* like a confidentiality boundary
without being one.

Verified at merge time, independently of the implementer:

```
tools visible to a PROPOSALS_WRITE-only principal : []
isaac_propose_field_value costs                  : ['isaac:proposals.write', 'isaac:read']
operations touching /review                      : []
forbidden_tool_reason('isaac_accept_proposal')   : "...contains the forbidden capability token..."
```

---

## 5. Seven defects found by re-measurement, every one green in CI beforehand

This is the section worth carrying forward, because it is a catalogue of how a guard passes while
being wrong.

| Defect | Why CI passed |
|---|---|
| The scope leak above | Only the success branch was projected; nobody measured the refusal branch |
| Two "no accept tool" tests | Passed on a **substring of the tool name they quote** — `forbidden_tool_reason` falls through to a message containing `accept` because it quotes `isaac_accept_proposal`. Removing `accept` from the token set left that file 39/39 green |
| Worked-example isolation test | Asserted `total == 0` **over an empty set**, and a 404 about the *record*. Would have passed byte-identically had in-session creates written into ordinary scope |
| Test fixtures inventing `system.domain` as a proposal target | No behavioural assertion depended on the invented entry. The docstrings claimed they were *"shaped verbatim from `routes._proposals_payload`"*; measured, there are **18** target paths and `record_scoped_target_field_paths` holds **one** |
| A copy promise — *"what you typed is still here"* | Its mutation survived all 47 tests. **The obvious fix was vacuous by construction**: a probe asserting the promise directly *also* passed against the mutant, because the fixture resolves instantly and React coalesces the loading commit away. It only bit at a 25 ms delayed read |
| Governance sweeps blind to their own files | Both enumerate `git ls-files`; while the files were **untracked they were invisible**, so the guards read clean. The instant they were committed, they failed. **Third and fourth occurrence of a defect the same slice had self-reported twice** |
| Panel refresh dead in practice | The catching control asserts the **request count**, not the rendered card |

---

## 6. Measurements that corrected a prior claim

**The change-feed floor.** `summariseChanges(entries, recordRev)` drops entries at or below the
floor, and `recordRev` is advanced by the **record** poller. A proposal act moves the record's rev
(DEC-10), so a `proposal` entry always shares its coordinate with the `experiment` entry beside
it. Measured: the feed **did** deliver `{"kind":"proposal","changed_at_rev":2}` at **9,969 ms**,
but the record poller had already refetched at **7,541 ms** — and the panel issued **no further
`GET .../proposals` in 47 s**.

**The fix is a split, not a removal.** The floor was never wrong to exist; *one floor was answering
two questions.* `recordRev` is sound for `experiment` and `run`, because a bundle refetch adopts
what those describe. It is false for `proposal`, whose list lives behind its own route.

**The e2e workaround could not be removed, and that is a measurement.** Removing it, the test
**still passed on unfixed code**: five runs gave PASS, FAIL, PASS, FAIL, PASS. Deleting the hold
would have left a flake that reads like evidence. It was **inverted** instead — moved onto
`GET .../changes` so the record poller wins, the ordering that dropped the proposal forever. Fixed
code passes; the single-floor mutant fails **3 of 3**.

**Does the same defect affect the `run` kind?** At the function level, identically. Observable
consequence: **none, because something worse is already true.** `RunsSection` takes one prop, its
list effect depends on nothing a feed signal moves, and `getRecordBundle`'s nine requests include
no `listRuns` — a colleague's run change never reaches that list at all. **Reported as a separate
defect and not fixed**; no third floor was added because no consumer would use it.

**The accessibility growth.** A first read of the CI log found **two** moved cells; the whole log
holds **six**, with different move sets per platform. The colour had to be **measured rather than
read off the label**, because `auditScan` `continue`s past the `foregrounds` guard on every
verdict except `ok` — so a `GREW` verdict never reaches the check that would name a new colour.
All 266 failing nodes carry one foreground: `#2f7d78` on `#e6f1f0`, recomputed at **4.21:1**, the
GET method chip at 10.5px/700. Pre-existing debt, and explicitly not a colour A3 was meant to fix.

**The durable finding there is prose versus row.** A3 darkened the neutral inks, so more *prose* on
that screen costs zero violating nodes — which is what the change-feed slice measured last
session. A new *operation row* still arrives carrying a teal chip A3 deliberately left. The next
slice that adds an operation pays one node per width; one that only adds words pays none.

---

## 7. What is NOT done — the only section that authorizes anything

### External gates (nobody in this repository may close these)

**Dean / operator / SLAC**
- `0005_run_projection` approval and hosted application; any later migration.
- Gate **G2** (per-record hosted display) and **G3** (the five withheld aggregates).
- Production remote MCP and OAuth routing.
- **The infrastructure half of trusted identity.** Until it exists, `accept` answers `409
  human_actor_required` in every deployment and `attribution.uploaded_by` stays unset. No
  application change can close this.
- Dean's **D1–D9** deferral is unchanged: no production provider, credential, endpoint or charge.

**Angel** — the six unclassified `system.configuration.*` fields. Nothing in this session touched
them and nothing is blocked on them.

**Krish / authenticated human**
- **`HOSTED QA PENDING` for every image from this session.** `/krish` sits behind an Authentik edge
  this environment cannot authenticate to. Checklist: `docs/krish-manual-verification-checklist.md`.
- The genuine browser **200%-zoom sign-off**. `CLAUDE.md` §11 records that **no CDP method, flag or
  API can drive it**, so it is not automatable at all. The layout-equivalent zoom proxy passes; that
  is a different claim.
- Team Owner review and private artifact sharing; real Team artifact authentication; a real Claude
  voice-plus-MCP smoke test. `docs/isaac-assistant-artifact-operator-checklist.md` opens **"Do not
  start."** and that is still correct — nothing here published, shared or contacted an artifact.
- Personal Vercel and Railway retirement, preserving the Railway volume.

### Application-side, named rather than implied

- **`RunsSection` has no refresh path from the change feed at all** (§6). Same class as the
  Evidence Graph fix `surface-freshness.test.tsx` §1 records; `RecordWorkbench`'s runs list was
  never swept.
- **A colleague's proposal now arrives with no announcement** on the ordinary ordering — the notice
  is correctly suppressed, because its sentence *"what is on screen was loaded before that"* would
  be false. Identical to what already happens to every field when the record poller wins. A product
  question about the notice, not about the panel.
- **One proposal event triggers a full-record bundle refetch including an unbounded `GET /pending`**
  — attributed to `useRecordSync` reacting to the `rev` bump, pre-existing for any write, **not**
  the feed. Not measured on a record with many runs; that combination is structurally unreachable
  today.
- **The drain budget is exactly exhausted at the row ceiling**: at 1,000 proposals, mount catch-up
  costs exactly 21 `/changes` requests — one cadence poll plus precisely
  `CHANGE_FEED_MAX_CONSECUTIVE_DRAINS = 20`.
- **No proposal producer exists in this build.** `routes.py` §7c: *"NOTHING WAS REWIRED TO FEED
  THEM."* Proposals arrive only via HTTP or MCP. The review surface deliberately has no create
  control — a surface that manufactured its own queue would be reviewing itself.
- Run-scoped proposals are untested end to end: the only record-scoped target path forces an
  exported record, which refuses `POST .../runs`.
- `isaac_runs` Stage 2b; an apply route for `POST /ingestion/csv/preview` remains **a committed
  human decision, not residual work**.

---

## 8. Measured state

All figures from the **main checkout** at the SHA named. A git worktree reads **+2** backend skips,
because `graphify-out/graph.json` is gitignored and absent from every worktree — a skip count
without its checkout is not a measurement.

| Measure | Value | Command |
|---|---:|---|
| Backend, at final `504c2ee` | **7,085 passed · 43 skipped · 0 failed** | `.venv/bin/pytest -q` |
| Frontend, at final `504c2ee` | **191 files · 5,074 tests**, 0 failed | `npx vitest run` |
| TypeScript | exit **0** | `npx tsc -b` |
| Both generated artifacts | **no drift** | `build_memory_snapshot.py … --detail-out … --check` |
| Served path set / manifest | **201 / 200**, unchanged all session | `json` over `memory-snapshot.json` |
| Backend skips, baseline → now | 39 → **43** | the +4 are exactly the engine-gated durability tests |
| Tracked files holding a NUL | **1** (the exempted zip, 918) | `python3 … count(b'\x00')`, never `tr` |
| Tracked symlinks | **0** | `git ls-files -s \| awk '$1=="120000"'` |
| Open PRs · worktrees · stranded | **0 · 1 · none** | `gh pr list`, `git worktree list`, `git rev-list --count` |

### The 43 skips, classified so they sum exactly

A first classification summed to **39** against a total of 43 and was **not published**. The cause
was the parse, not the suite: `pytest -rs` prints `SKIPPED [n] …`, so one line can represent
several skips and `uniq -c` counts lines. Parsed with the multiplier: **39 lines representing 43
skips.**

| Count | Category | An untested path? |
|---:|---|---|
| **32** | `ISAAC_RUN_REAL_ENGINE_PARITY` not set | **No** — `ci.yml` arms it at four sites |
| **1** | `ISAAC_REQUIRE_REAL_ENGINE_PARITY` not set | No — this is the guard that makes an absent engine a FAILURE in CI rather than a skip |
| **4** | opt-in benchmarks (`ISAAC_PERF_BENCH=1`) | No — deliberate |
| **2** | psycopg2 IS installed, so the test can only witness a genuinely absent driver | No — each names its unconditional sibling |
| **4** | strict-reader tolerances | No — each names the route tests that cover it |
| **43** | **TOTAL** | |

**Not one of the 43 is an untested path wearing an environment gate.** That distinction is the
reason the count is classified rather than quoted.

### Release state — read the gate log, not the run list

| Commit | GHCR | Released as |
|---|---|---|
| `6aa4e20` (#218) | success | **v0.0.205** |
| `fb1e1e3` (#217) | **failed the gate** — its CI was CANCELLED, superseded by the next push | never released |
| `504c2ee` (#215, final `main`) | CI still running at the time of writing | **not yet released** |

**A trap worth recording, because it nearly produced a false claim here.** `gh run list --json
headSha` reports the TRIGGER SHA, not the released one — the run whose `headSha` reads `504c2ee`
actually released `6aa4e20`, and only `scripts/ci_release_gate.py`'s own log says so. The
`fb1e1e3` failure is the pipeline working: the gate refuses to release a commit whose CI never
concluded success. No tag was created by hand.

Frontend counts moved per branch during the session and are recorded in each PR; the figure above
is the final tree, measured after the last merge rather than carried forward from before it.
