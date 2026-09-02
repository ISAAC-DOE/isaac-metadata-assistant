# Two scientists, one record: the end-to-end proof

**Date:** 2026-09-02 · **Branch:** `feat/live-refresh-integration-and-two-actor-proof`
**Spec:** [`apps/web/e2e/trusted/two-actor-workflow.spec.ts`](../../apps/web/e2e/trusted/two-actor-workflow.spec.ts)
**Suite:** `apps/web/playwright.trusted.config.ts` — one project, `workers: 1`, `retries: 0`,
its own backend on `127.0.0.1:8101`, its own Vite on `127.0.0.1:5275`, its own
`ISAAC_UI_WORKSPACE`, started with `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` and
`ISAAC_FIXTURE_ACTOR_SUBJECT=synthetic.browser.reviewer`.

This document records what a single Playwright test measured about the collaborative
workflow this programme has been building, and — with equal care — what it did **not**
measure.

---

## 0. The three tiers of claim, stated before any of them

A reader who takes only one thing from this document should take this table.

| Tier | What is established | By what |
|---|---|---|
| **Proven here** | All 20 steps below, against a real FastAPI process, a real Chromium, and a real filesystem-backed workspace. | The spec, run locally; raw output in §3. |
| **Proven only in CI** | Durability across a process restart, against a real PostgreSQL. | `apps/api/tests/test_proposal_durability.py`'s real-engine scenarios, gated on the engine-parity flags `ci.yml` sets. **Cited, never claimed here.** |
| **Proven nowhere** | Anything hosted. | `/krish` sits behind an Authentik edge this environment cannot authenticate to, **and no shipped deploy artifact sets either trusted-identity variable** (`apps/api/tests/test_deploy_config.py` pins that, scanning the `Dockerfile`, `build-push.yaml` and `pr-docker-smoke.yml`). A hosted acceptance answers `409 human_actor_required`. Status: **HOSTED QA PENDING (Krish)**. |

**Data boundary: none.** No production-derived content was read, written, or transited
any process. Every record, run, note, proposal and value in this proof is created by the
spec seconds earlier, in a workspace `global-setup` wipes at the start of every run. No
database connection was opened from this host.

---

## 1. The two actors, and why B is not a second browser

- **Scientist A** is a Playwright `page` with the Record Workbench open from step 1 to
  step 20. Every act attributed to A is a click or a keystroke.
- **Scientist B / an MCP producer** is a Playwright `request` context speaking HTTP to
  the **same backend process**.

B is HTTP and not a second browser for a measured reason, not for convenience: `lib/api.ts`
ships no `createProposal`, and `routes.py` records that *"NOTHING WAS REWIRED TO FEED
THEM. There is no automatic producer"*. **No surface in this build can create a
proposal**, so a second browser would have nothing to click.

The suite's inherited rule is not weakened: **the reviewed act happens through the visible
UI.** A's rejection (step 9) and A's acceptance (step 14) are clicks. B's HTTP calls
establish starting state and read server state back as an independent check; they never
perform the act under test. The two exceptions are deliberate and are labelled where they
occur — step 13's stale accept and withdraw are measured over HTTP because the *server's*
refusal is the guarantee and the panel deliberately still offers the button (see §5).

---

## 2. The 20 steps: what was asserted, and what was observed

Every row is asserted in the one test
`two scientists, one record, end to end › a colleague's proposals arrive, are judged, and
land on exactly what they named`. The step numbers are the comment banners in the spec, so
a failure message names its step.

| # | Step | Asserted on the SCREEN | Asserted on the SERVER | Observed |
|---|---|---|---|---|
| 1 | A creates a record | URL is `/record/{26-char id}` | `GET /experiments/{id}` → `200`, `id` matches | ✅ |
| 2 | A adds two Runs **through the website** | `.run-card` count `2` | `GET .../runs` → 2 rows | ✅ |
| 3 | A enters **record-level** information | Record Description panel opened by its own disclosure; `Technique` `<select>` set; `Save record description` clicked | polled `GET .../draft` until `system.technique` holds the chosen enum member | ✅ |
| 4 | A enters **run-level** variables for run one | `Environment` `<select>` on the first run card | polled `GET .../runs/{one}` until the field autosaved | ✅ |
| 5 | A opens the proposal-review surface | `Ingestion Proposals` heading visible; `.proposals-empty` visible; `.proposal-card` count `0` | `GET .../proposals` → `[]` | ✅ |
| 6 | B creates a **RECORD-scoped** proposal with a `client_request_key` | — | `run_id` is `null`; key stored; **a replay of the same key returns `deduplicated: true` and the SAME `proposal_id`**; the record holds **one** proposal, not two | ✅ |
| 7 | A's page discovers it **with no reload and no navigation** | `.proposals-arrival-note-text` becomes visible on its own; text is exactly `At least 1 proposed change arrived and is ready to review.`; the sr-only `role="status"` region contains `proposed change`; the sentence contains **neither the proposed value nor the field path** | — | ✅ |
| 8 | The card renders, current vs proposed distinguishable | card visible; `.proposal-scope` is `On the record`; `Proposed value` label; `Show What the Record Holds Now` reveals the current value = A's choice, **not** the proposal's | — | ✅ |
| 9 | A **rejects** through the UI, with a reason | card name becomes `… — Rejected` | `state: "rejected"`; the typed reason stored **verbatim**; `accepted_value` `null`; **the canonical record value is byte-equal to before** | ✅ |
| 10 | B creates a **RUN-scoped** proposal for the **second** run | — | `run_id` == run two's id | ✅ |
| 11 | Both surfaces refresh **with no reload** | the new card appears on its own; `.proposal-scope` is `On run {runTwo.id}` | **exactly ONE** `GET .../runs?…` re-read attributable to the act, counted via `page.on('request')`, and its `limit` is **`2`** — the received count, not the page size | ✅ |
| 12 | Three distinct values, and the label says whose | current value = run two's; **not** run one's; **not** the proposal's; `.proposal-current-label` matches `/run/i` | — | ✅ |
| 13 | Stale-revision protection, on a **throwaway** proposal | the stale card (addressed by its scope line) says `…CHANGED since this proposal was made…`; after withdrawal the card reads `… — Withdrawn` | throwaway on **run one** goes `target_stale: true`; **step 10's proposal on run two stays `target_stale: false`**; accept → **`409 {"error": "proposal_stale"}`**; withdraw → `200` | ✅ |
| 14 | A **accepts** through the UI under the trusted identity | card name becomes `… — Accepted` | `state: "accepted"`, `accepted_value` = proposed, `accepted_from: "candidate"`, `applied_run_id` = run two | ✅ |
| 15 | **Only** run two changed | — | run two's target = the accepted value; **run one's WHOLE served document is `toEqual` its pre-accept snapshot** — `version`, `rev` and `updated_utc` included | ✅ |
| 16 | Attribution and audit history | — | the `accept` history entry carries `actor_subject: "synthetic.browser.reviewer"` and `actor_trust_basis: "test_fixture"`; the `propose` entry carries `actor_subject: null` / `unattributed`; the run's field holds a `user_confirmation` evidence entry whose `answer` **is** the accepted value | ✅ |
| 17 | Change feed, from a cursor taken before step 14 | — | `limit: 200` honoured; the proposal appears **once**, `state: "accepted"`; run two appears **once**; **run one is ABSENT**; every entry above the cursor; drains to `has_more: false`; **no entity served twice across pages**; a re-read of the drained cursor returns `[]` | ✅ |
| 18 | Durability across a **reload** | after `page.reload()`: both runs, the accepted card, **and the rejected card** (a rejection is kept, not deleted) | `/api/health` asserted to report `experiment_storage.backend: "filesystem"`, so this step's scope cannot silently widen; A's record-level value survives | ✅ |
| 19 | Validation reads the accepted value | — | `official_validator_ran: true`; `ok: false`; **no refusal message names the accepted value or A's record-level value**; the served run document at the target **is** the accepted value; per-run verdicts number `2` | ✅ |
| 20 | The tooling cannot Submit, export, or accept | — | `PERMITTED_TOOL_NAMES` parsed out of `mcp/policy.py` (comments stripped) → **no name contains `accept`, `approve`, `submit`, `export`, `publish` or `delete`**; and `POST /api/mcp` `tools/list` → **`404`**, because this deployment mounts no transport at all | ✅ |

### Step 19, precisely: the record is *not* exportable, and that is the measurement

A record created through the product's own path still owes the blocking questions this
test never answered. So step 19 asserts the two-parter rather than a pass: the accepted
value **is** in what the validator read, and the dry run names only **other** fields.
Measured over HTTP at this HEAD, on exactly this record shape, the three top-level
refusals are:

```
$        'descriptors' is a required property
context  'temperature_K' is a required property
system   'domain' is a required property
```

The spec asserts them as a **property of the set** — that no message contains the accepted
value or A's record-level value — rather than as a list of three, because the claim being
made is *"none of them is the field the proposal wrote"*, not *"there are exactly three"*.
Pinning the count would make an unrelated schema change look like a regression in this
proof.

### Step 20, precisely: two halves, one measurable here

- **(a) No permitted tool can accept, submit or export.** Measured. `PERMITTED_TOOL_NAMES`
  is parsed out of `apps/api/isaac_api/mcp/policy.py` rather than fetched, because this
  deployment mounts **no** MCP transport, so there is no `tools/list` to call. Reading the
  policy source is the established precedent —
  `apps/web/src/__tests__/connect-your-agent.test.tsx:726` does exactly this, and its own
  comment records the defect that hardened the parser (a quoted phrase in a comment
  *inside* the frozenset read as a fifteenth tool). Comment text is stripped here for the
  same reason.
- **(a′) And the transport is not even mounted.** `POST /api/mcp` → **`404`**, not `403`.
  `mcp_transport_or_none` registers no route for an unconfigured deployment, because
  *"a path that refuses is still a path that says ISAAC speaks MCP, find the credential"*.
  So the permitted tools here are not merely unable to accept — they are unreachable.
- **(b) An accept without a verified identity is refused. NOT MEASURABLE IN THIS PROCESS**,
  and said plainly rather than skipped. The verifier is chosen from the **backend
  process's** environment, and this suite exists precisely because it sets
  `ISAAC_EDGE_TRUST_VERIFIER=test_fixture`. One process has one configuration. That leg is
  `apps/web/e2e/mutation/proposals.spec.ts:1003`, *"accepting is refused truthfully, and
  nothing is written"*, which asserts `409 human_actor_required` against a backend with no
  verifier. **It is cited, not reproduced.**

---

## 3. Raw verification output

### The spec alone

```
$ E2E_UVICORN=…/.venv/bin/uvicorn PYTHONPATH=…/apps/api:…/src \
    npx playwright test --config=playwright.trusted.config.ts two-actor
[trusted-setup] hermetic: ordinary workspace empty; backend attributes through the test_fixture verifier, so acceptance is reachable.
Running 1 test using 1 worker
[1/1] [trusted-1280x800] › e2e/trusted/two-actor-workflow.spec.ts:240:3 › two scientists, one record, end to end › a colleague's proposals arrive, are judged, and land on exactly what they named
  1 passed (34.7s)
```

### The whole trusted suite (this spec plus the five it joins)

```
$ E2E_UVICORN=… PYTHONPATH=… npm run test:e2e:trusted
Running 6 tests using 1 worker
[1/6] … proposals-run-scoped.spec.ts:184:3 › the scientist sees it, and sees which RUN it is about
[2/6] … proposals-run-scoped.spec.ts:207:3 › the CURRENT value it shows is the targeted run's …
[3/6] … proposals-run-scoped.spec.ts:243:3 › accepting it through the screen writes ONE run …
[4/6] … proposals-run-scoped.spec.ts:293:3 › the acceptance is attributed to the subject …
[5/6] … proposals-run-scoped.spec.ts:327:3 › rejecting it through the screen leaves BOTH runs …
[6/6] … two-actor-workflow.spec.ts:240:3 › a colleague's proposals arrive, are judged, …
  6 passed (42.7s)
```

### Typechecks

```
$ npx tsc -b                                 # exit 0
$ npx tsc -p e2e/tsconfig.json --noEmit      # exit 0
```

---

## 4. Mutation controls

Seven controls were applied, run, and reverted. **Two of them are inert, and that is
recorded rather than dropped** — a control that cannot go red is a claim free to drift.
Controls A–D are against the jsdom integration test
(`apps/web/src/__tests__/runs-live-refresh-integration.test.tsx`); E–G are against this
spec.

| # | Mutation | Result | Reading |
|---|---|---|---|
| **A** | delete `activity={runActivity}` from `RecordWorkbench.tsx` | **7 passed** — inert | **An equivalent mutation on this screen.** `recordChanges.needsCanonicalRefetch` returns `true` whenever `summary.runIds.length > 0`, so *any* run signal also triggers a bundle refetch; the refetch moves `detail.version`; and `recordVersion` then fires the completeness path, which **subsumes** the fast path for every scenario the harness can build. Request **order** is identical too — measured by printing the recorded calls both ways. The prop is kept (it is the shipped contract and the only path that does not wait on a nine-request refetch), but no test here may be read as evidence it does anything. |
| **B** | delete `recordVersion={detail.version}` | **2 failed** | `expected 2 to be 1` (the removed run stays on screen) and `expected +0 to be 1`. Load-bearing, and it is the prop carrying the two cases the feed structurally cannot report. |
| **C** | delete the in-flight coalesce in `RunsSection.triggerBoundedSilentReload` | **7 passed** — inert | Under fake timers the two paths never actually overlap, so nothing lands while a request is outstanding. The `toBe(1)` assertions are still real (control D fails them) but are not measuring the coalesce. |
| **D** | delete **both** props — *exactly the tree before this branch* | **4 of 7 failed** | edit, removal, proposal-only and record-poller-first, each at a re-read count of 0 or a run still on screen. **This is the control that matters:** the wiring as a whole is load-bearing, and this file would have caught what two green branches shipped. |
| **E** | delete `activity={proposalActivity}` from `<IngestionProposalsPanel>` | **1 failed** | `Error: step 7: the arrival note appears on its own / expect(locator).toBeVisible() failed`. Live proposal discovery is genuinely live. |
| **F** | delete `recordVersion={detail.version}` (browser) | **1 failed** | `Error: step 11: exactly ONE bounded runs re-read is attributable to the proposal act / Expected: 1 / Received: 0`. **The browser test distinguishes what the jsdom test could not** in control A's direction: here the re-read is attributable, countable, and absent without the prop. |
| **G** | remove `ISAAC_EDGE_TRUST_VERIFIER` from the suite's backend env, fresh process | **run aborted in `globalSetup`** | `[trusted-setup · 1/2 premise] the backend reports verifier_id="unconfigured", expected "test_fixture". Acceptance would answer 409 human_actor_required and every spec here would fail on a button that did not move…`. The identity premise is verified **before any spec runs**, so it cannot be silently absent and the suite cannot pass vacuously. |

---

## 5. Four findings this proof produced, each measured

### 5.1 Staleness cannot be undone by restoring the value

The first version of step 13 made step 10's own proposal stale and then wrote the old
value back, expecting `target_stale` to return to `false`. It stayed `true`:

```
Error: step 13: step 10's proposal is not stale, so step 14 can proceed
expect(received).toBe(expected)   Expected: false   Received: true
- Timeout 15000ms exceeded while waiting on the predicate
```

`proposals.target_digest`'s own docstring says why: the digest is taken over *"the draft
field envelope (value **AND evidence**, which is why an added confirmation moves it)"*.
Restoring the value **adds a confirmation**, so the digest moves again and can never
return. This is correct behaviour and worth carrying forward: **a stale proposal is
recovered by withdrawing or superseding it, never by restoring the value.**

The step was reordered onto a throwaway proposal against **run one**, which is strictly
better than the alternatives, and the reason is also measured: `context.environment` is the
**only** run-scoped target the vendored schema closes with an enum — over all 17 run-scoped
paths, the other 16 are open strings or numbers — so a throwaway at a *different path* was
not available. A different *run* was, and it buys an extra assertion: **staleness is
scoped to the (run, path) pair, not to the record.** The record's revision moved,
`base_rev` moved with it, and step 10's proposal on run two stayed `target_stale: false` —
exactly what `target_digest`'s docstring says `base_rev` would get wrong "in both
directions".

### 5.2 The record-level write key is the bare dotted path

Measured over HTTP: `POST .../answers` with `{"answers": {"field:system.technique": …}}`
is refused **`422 unrecognized_field`**; with `{"answers": {"system.technique": …}}` it is
**`200`**. The `field:` prefix that the *run override* routes take is wrong at the record
level, and a fixture using it would report the record-level capture surface as broken. The
body also requires `confirmed_by_user: true` (otherwise `422 confirmation_required`) and
`answers` must be an **object**, not a list (`422 invalid_body`).

### 5.3 `waitFor` hangs under fake timers; `__dirname` does not exist under ESM

Two tool-level traps, both of which produced a failure naming neither cause:

- The jsdom integration test's first version used testing-library's `waitFor` under
  `vi.useFakeTimers()`. All six mounting tests hung at `Test timed out in 5000ms`, naming
  neither the query nor the DOM — `waitFor` polls on an interval the fake clock leaves
  frozen. Every assertion now reads synchronously after a `settle()` that advances the
  clock inside `act`.
- This spec's first version resolved the policy file with `__dirname` and failed at run
  time with `ReferenceError: __dirname is not defined`. Playwright loads specs as ES
  modules. It now walks up from `process.cwd()`, which is also what
  `e2e/mutation/validator-package-upload.spec.ts` does and for the reason it states: it
  holds whether Playwright is invoked from `apps/web` or from the repository root.

### 5.4 A stale claim in `CLAUDE.md` §11, re-measured

§11 states that exactly one file under `apps/web/src` holds a NUL byte —
`components/RecordDescriptionPanel.tsx`, 2 of them — and that a `grep`/`rg` sweep of the
tree is only evidence of absence when run with `-a`. **The NUL is gone at this HEAD.**
Measured with the reader §11 itself prescribes (`tr` is the tool that fails silently):

```bash
$ python3 -c "import sys;print(open(sys.argv[1],'rb').read().count(b'\x00'))" \
    apps/web/src/components/RecordDescriptionPanel.tsx
0
```

and over every tracked file under that directory: **398 files, 0 with a NUL.** The
`-a` habit still costs nothing and the mechanical guard
(`apps/web/src/__tests__/source-is-greppable.test.ts`) is what keeps it that way — that
guard passing is presumably why the byte is gone. Recorded here so a future session
re-measures rather than quoting a status that has moved. **Not corrected in `CLAUDE.md` by
this branch**: that file's §11 corrections are the project owner's to sequence, and this
branch's charter does not extend to it.

---

## 6. Assumptions, and what remains unverified

**Assumptions this proof rests on, stated so a reader can attack them:**

1. **The fixture verifier is a faithful stand-in for a trusted edge** for the purpose of
   attribution. It mints `trust_basis: "test_fixture"`, which is deliberately *not*
   `verified_edge_assertion`, so nothing here stamps `attribution.uploaded_by` and nothing
   here claims a real identity boundary exists. ISAAC has no trusted authentication
   boundary (Dean reconfirmed the ClusterIP bypass, 2026-08-12).
2. **`DISCOVERY_DEADLINE` (45 s) is generous, not tuned.** It exists so a page that never
   noticed fails instead of hanging. No assertion passes because of a delay; shortening it
   could make the suite flaky on a loaded host, and lengthening it would change nothing
   about what is proven.
3. **The single-test structure is deliberate.** The steps are a sequence — step 15 is a
   statement about what step 14 did to state that steps 2–4 created — so splitting them
   would mean either twenty rebuilds of the same record or twenty tests sharing mutable
   state through a module variable, which is what `workers: 1` and `retries: 0` exist to
   avoid rather than to enable.
4. **The derivations follow the server.** The record-scoped target, the run-scoped target
   and all six enum values are read from `GET .../proposals` and `GET /api/schema` at run
   time. If the server widens or narrows a set, this spec follows it or throws with a
   message naming what it saw — it never contradicts it silently.

**Unverified, and named rather than implied:**

- **Every hosted claim.** `HOSTED QA PENDING (Krish)`. This proof says nothing about
  `/krish`, and the trusted identity it needs is set by no deploy artifact.
- **PostgreSQL durability.** Cited (§0), not measured here.
- **Bytes and latency.** jsdom has no wire; the browser suite counts requests and asserts
  their query strings, not their sizes or timings.
- **The mutation suite** (`npm run test:e2e:mutation`) was **not run** on this branch — see
  the session report for the reason and the load figures. Nothing in this branch touches a
  file it covers, but that is an argument, not a measurement.
- **Concurrency between the two actors.** Every step here is ordered. Two writers racing
  the same field in the same instant is `apps/api/tests/test_concurrent_write_pairs_lose_no_update.py`'s
  subject, not this file's.
