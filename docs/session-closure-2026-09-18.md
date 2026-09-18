# Session closure — 2026-09-18: Activity finished, Statistics from Activity, Extended Context made inspectable, and the migration programme made operator-ready

**All five PRs merged; zero open at close.** Every figure is either quoted from a command run in
this session or copied verbatim from a PR body / agent report and marked as such. Re-derive rather
than quoting: the commands are given.

**No production infrastructure was touched. No migration was applied. No database connection was
opened. No credential was entered. No message was sent. No external service was contacted.**

---

## 1. Starting point, re-derived rather than taken from the handoff

```
main = origin/main = 938e4829   (PR #270's merge — the ACT-003 Activity UI)
ahead/behind        = 0 / 0
tree                = clean
stashes             = (empty)
open PRs            = NONE
release             = v0.0.253; `git rev-list -n1 v0.0.253` -> 938e4829 (resolved from the TAG)
main CI             = success at 938e4829
worktrees           = 100+ stale scratchpad/agent worktrees, EVERY ONE measured clean
```

**One thing in the inherited state was wrong, and it is the failure this project's own ledger exists
to prevent.** The ledger's §10 called `ACT-003`/`ACT-004` *"the one unbuilt app-side item"* — but
`ACT-003` had **shipped in PR #270**, after the ledger's last commit (`6f1242a9`, PR #269). The
ledger described as unbuilt a feature that was merged and released. Corrected in the session header
of `ISAAC_EXECUTION_LEDGER.md`, superseded in place rather than rewritten.

---

## 2. What merged

| PR | Title | Head | Merge | CI on the exact head |
|---|---|---|---|---|
| [#271](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/271) | `docs(operator)` — one entry point for the migration sequence, pinned against its packet | `dcfe8d5d` | **`c9ffed06`** | **5/5 success**, verified per-check via `gh api .../commits/dcfe8d5d/check-runs` |
| [#272](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/272) | `fix(activity)` — a time hierarchy, a real primary line, and no JSON dump (`ACT-003b`) | `9e7e764f` | **`b7120462`** | **5/5 success, including the a11y job** |
| [#274](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/274) | `docs(evidence)` — browser QA over ten routes and four widths, with its own negative control | `ed7d6479` | **`78e9371e`** | **5/5 success** |

| [#273](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/273) | `feat(statistics)` — Workspace Activity summarizes the history, and says what it covered (`ACT-004`) | `d99dc61c` | **`44760336`** | **5/5 success** — after its a11y job failed once and was transcribed (§5A) |

**Releases, each resolved from the TAG rather than read off a workflow log line**
(`git rev-list -n1 <tag>`):

| tag | commit | PR |
|---|---|---|
| `v0.0.254` | `c9ffed06` | #271 |
| `v0.0.255` | `b7120462` | #272 |
| `v0.0.256` | `78e9371e` | #274 |
| `v0.0.257` | `44760336` | #273 |

**Every merge was checked for the merge-vs-head distinction rather than assumed.** #271's base had
not moved, so its CI head content *was* its merge content. #272's base had moved to `c9ffed06`, so
the file overlap was measured — `comm -12` over the two diffs returned **empty**, making that merge
trivially clean. `CLAUDE.md` §11's rule is that exact-head-green protects the HEAD, not the MERGE;
this is the rule applied rather than cited.

| [#275](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/275) | `feat(ctx)` — Extended Context becomes inspectable, by a scientist and by an agent (`CTX-004`) | `e4bab90b` | **`ea25d471`** | **5/5 success** — after its own a11y round (§5C) |

**`ea25d471`'s release was still resolving at close** — re-derive with `git rev-list -n1 <tag>`
rather than quoting a number from here. The four numeric collisions between `ACT-004` and `CTX-004`
are §6; the two a11y transcription rounds are §5A and §5C.

**Verified on merged `main` after the last merge**, re-derived rather than carried forward:
`create_app().openapi()` gives **81 paths / 91 method-operations** — exactly what the collision
resolution predicted, which is the evidence that taking neither side and re-measuring was correct.
`GET /api/experiments/{id}/extended-context` answers **200** carrying `offset` / `limit` / `has_more`
(the paging fix) and its `not_official` sentence. The panel renders at `.fg-header` **index 4 of
11** — **not first**, which was the placement constraint four `e2e` specs depend on — and its absent
state reads *"This record states no extended context. That is the ordinary case…"* rather than as an
error.

---

## 3. `ACT-003b` — the Activity UI, and what its first independent review found

`ACT-003` shipped in PR #270 **without independent review**, because the previous session exhausted
its agent budget. This session closed the three named UI defects and then gave the whole surface —
the merged `ACT-003` *and* the new polish — the review it never had.

**What shipped:** calendar-day grouping (`Today` / `Yesterday` / absolute date) as nested lists with
an `<h3>` per day under the panel's `<h2>`; grouping over the **concatenation of all pages**, so a
day spanning a page boundary renders one heading, by **consecutive runs** so an out-of-order
`recorded_utc` is not silently relocated; `now` read in the render body every render; a demoted
metadata line so action and object no longer compete with channel; and the `JSON.stringify`
fall-through replaced by key-level diffs with raw documents behind a native `<details>`.

**The review found three Important defects that the slice's own 30-test suite passed**, all inside
the one feature the polish added:

1. **The panel named an actor and simultaneously denied any actor was named.** The per-row actor was
   gated on the loaded list; the standing disclosure was gated on nothing. A history containing one
   attributed act rendered a named row *under* a sentence saying entries are not attributed. The
   `PER_ROW_ACTOR` docstring argued for four paragraphs that suppression must be conditional on the
   value — and left its counterpart hard-coded. **Reproduced using the implementer's own fixture**,
   which already constructed the state and simply never looked.
2. **A username went through the token humanizer, which renamed the person.** `k_verma` rendered as
   **"K Verma"** — not searchable, not copyable, not correlatable to the identity system, in the one
   surface whose job is saying who did what. A test **pinned the mangling as intended**. And the
   obvious remedy does not work: §11's approved `BARE_IDENTIFIER` predicate *passes* `k_verma`, so
   "just reuse the repo's rule" would have produced a fix that passes review and still renames
   scientists. The actor is now never humanized except the `unattributed` sentinel.
3. **A failed older-page read was announced to screen readers and to nobody else.** The `.catch`
   correctly did not destroy the list (§11's destructive-silent-failure rule) but the only visible
   error path is `status: 'error'`, so a sighted reader saw a button flicker and could not tell
   "failed" from "nothing more" — the same inversion §11 records for the recording state.

Plus two real Minors: an **order-only change at depth** rendering as an unexplained "changed" (the
top-level note exists to prevent exactly that, and `sameStored` was key-order sensitive at every
depth), and the claim *"a tab left open overnight does not lie"*, which the mechanism does not
deliver — there is no timer, poller or feed subscription on that panel, so an idle tab opened at
23:50 still reads "Today" at 09:00. **The implementer re-derived that one rather than accepting it,
agreed, withdrew the claim, and added a negative control** asserting the stale label is on screen
*before* the click, so the withdrawal is mechanical rather than prose.

**Both guard gaps were closed in the same pass.** The `shown`/`total` asymmetry — correct, and
previously unpinned in both directions — is now pinned by two tests whose fixtures deliberately
**disagree** with the arrays they carry (`returned: 99` on a 2-row page), which is the only way
either half is checkable. And the actor-constant parity gap the implementer had itself flagged is
closed by a test in `test_activity_model.py`, negative-controlled by misspelling the frontend
sentinel.

**Five mutants, each applied, run and reverted, each killed by the test that names it** — including
the reviewer's exact `shown` swap.

**Accessibility resolved in the affirmative.** The implementer could not measure locally and
correctly refused to invent a number; `record-activity` has zero recorded cells in
`e2e/a11y-baseline.ts`, so any new violating node fails the job. **CI's Linux a11y job passed on the
fixed head**, so the added DOM nodes moved no cell.

---

## 4. Live verification of both flagship workflows, end to end

Against a **local** build, over HTTP, on a record created through the product's own
`POST /api/experiments`. Evidence for the browser half:
[`docs/evidence/browser-qa-2026-09-18.md`](evidence/browser-qa-2026-09-18.md).

### Live capture

transcript → **note stored** → **candidate extracted** → **durable proposal minted**, in one write.
The candidate carries the exact quote, char offsets, `origin: transcript`, `produced_by:
transcript-reader`, and a rule reading *"the number is read as written and the unit is not
converted; the value is quoted from the transcript, not interpreted"* — §5 rendered as provenance
rather than asserted.

**The negative case is the more informative one.** Text reading *"Filter was set to 20. The sample
is IrOx nanoparticles on carbon."* produced **0 candidates while still storing both notes.** Nothing
invented, nothing lost — the losslessness guarantee `transcript_capture.py` exists for.

### Historical Import, all six steps

`new_import → sources → parse → reconstruct → review → add_to_experiments`, on committed synthetic
fixtures.

**Two sources disagreeing on `sample.material.name` yielded `proposed_value: null`**, with **both**
competing values preserved alongside their source ids and locators (`line 23`, `line 13`), under a
rule stating *"2 of the parsed sources state a value at `sample.material.name` and they do not
agree, so this reconstruction chose none of them."* At `add-to-experiment` the resolved candidate
became a proposal (*"Read verbatim … No alias, synonym or normalisation was applied"*) while the
disagreeing one was **refused as `candidate_unresolved` with its reason stated**. Counts: 4
candidates, 1 sent, 3 not sent.

`extended_context` came back carrying its `not_official` sentence, and **`nominal_offers: []`** —
confirming `DEC-43` condition (ii) structurally: no 298 K is offered outside the BL15-2 Angel
profile.

### The truth path, and the two identity boundaries

- Export dry-run: **`ok: false`** with the official schema's own `'descriptors' is a required
  property`; `pending` naming three real blockers in human wording.
- Proposal **accept → `409 human_actor_required`** (`trust: untrusted`, `reason:
  no_verifier_configured`, *"Nothing was written."*) — the `EXT-01` boundary, live.
- Proposal **reject → `200`**, append-only 2-entry history, `actor: None` honestly unattributed.

### `ACT-001`/`ACT-002` live

All five acts recorded with the right action, object type, channel and `actor: unattributed`; the
import stamped **`historical_import`** where the rest read `web`, so the fourth channel value is
reachable in practice and not only in the vocabulary.

**And the refused accept recorded NOTHING** — `seq` stayed dense 1–5 with no gap, so no position was
burned. That is the route's own documented contract (*"a request that changed nothing records
nothing and burns no position"*), measured rather than read.

### MCP, exercised locally

Under `ISAAC_MCP_DEPLOYMENT=local-loopback`: `posture: local-only`, `serves_transport: true`,
`requires_loopback_peer: true`.

| condition | result |
|---|---|
| `ISAAC_MCP_LOCAL_SCOPES` unset | **10 tools, all read-only** |
| `isaac_list_experiments` call | `200`, `isError: false`, structured content |
| `isaac_update_draft` with no write scope | **`403`**, JSON-RPC `-31002`, `grantedScopes: ["isaac:read"]`, `missingScopes: ["isaac:draft.write"]` — **enforced, not merely unlisted** |
| scopes `read,draft.write,proposals.write` | **16 tools**, and **zero** export / submit / migration / delete / discard / governance / reset tools |

The last row is §15's *"no external agent performs final Submit"* and `tools.py`'s *"Nothing here
finalises"* — verified live rather than by reading the registry.

---

### The polished Activity panel, verified in a browser after it merged

Against the 6-event record on the post-merge build: day grouping renders as nested lists (`Today`;
outer `<ol>` → one `<li>` → nested `<ol>`); the counter reads *"Showing the most recent 6 of 6
entries."*; the primary line is action + object only (`Archive Attached` / `Import`) with the
metadata demoted to `09:11 AM · Historical Import`; **the per-row actor is suppressed** across all
six rows, which is the per-list gate behaving correctly while every actor is `unattributed`; and
**zero raw JSON renders outside a disclosure** — structured values read as *"4 fields"* with the
document behind a closed `<details>`, primitives inline (`open → rejected`).

A post-merge regression sweep over all ten routes: **10/10 rendered, zero console events, zero
horizontal overflow.**

---

## 5. Candidate findings investigated and CLEARED — recorded because absence of a defect is a result

Five in the browser sweep (§4 of the QA evidence doc) and three more here:

1. **The import records one `archive_attached` where the transcript path records one event per
   note.** *Not a defect:* the batch records `run_added` per created run **plus** a summary event
   whose payload carries `proposals_sent` / `runs_created` / `candidates_not_sent`, treating the
   batch as **one human act** per `DEC-37`; the single-candidate route records `proposal_created`
   because that genuinely is one proposal. Correct granularity at both.
2. **The per-list actor gate appeared to leave unattributed rows blank in a mixed history.** *Not a
   defect:* every row renders its actor once the gate is on, so those rows read "Unattributed" in
   words.
3. **`QA-020` appeared stale.** *It is not* — see §7, which records this as a correction to my own
   draft.

---

## 5A. `ACT-004`'s a11y job FAILED, which is the baseline working

`#273`'s CI on the merge result `f8a4718e` returned **4/5 success with `browser accessibility and
responsive baseline` FAILING** — and the cause is the mechanism `CLAUDE.md` §11 names by name: the
Endpoint Explorer renders every operation the **live** `/api/openapi` exposes, so one added route
changed the text on `settings-explorer`.

**Six cells moved, transcribed from job
[105678012414](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/35368933912/job/105678012414),
all rule `color-contrast`, all `+1`:** `desktop-1280x800` and `laptop-1024x768` 18 → 19;
`tablet-768x1024`, `mobile-375x812`, `width-390` and `width-320` 21 → 22.

**`settings-explorer@zoom-200` did NOT move**, and that is a measurement rather than an omission —
§11 records the A/B precedent that movement depends on the **wrap boundary**, so "one operation,
therefore +1 everywhere" would have been invention.

**A near-miss worth recording.** `width-390` and `width-320` were **scalars** (`21`). Because linux
rose *above* them they become legitimate splits. Had linux instead risen to *meet* an unmeasured
darwin, this would have hit the contradiction `a11y-baseline.ts` documents at that very cell:
`auditA11yWellFormedness` refuses equal halves, and `DARWIN_CARRIED_FORWARD`'s invariant refuses a
registered scalar. That contradiction remains **pre-existing and unresolved**, and was deliberately
not touched.

### The darwin halves are CARRIED FORWARD, and the blocker is one stale process

All six darwin values are the last measured ones; **no darwin run has seen them at this head.**

**This was reconsidered rather than accepted.** A faithful local run needs `VITE_API_BASE` unset with
the API on port **8000** — held by an orphaned `uvicorn` from **Sep 15** that this environment was
blocked from killing. A harness on other ports was available and was checked far enough to establish
it *would* have been faithful for this surface (`SettingsPage` reads only `diagnosticsAppFrom` /
`diagnosticsMemoryFrom`, neither of which consults `isHostedBuild`).

**It was still declined.** `e2e/env.ts` records that the 5173 default is deliberate, the harness
differs from the sanctioned one on two axes, and **a wrong darwin number that looks measured is
worse than an honestly carried-forward one** — that exact error left 15 cells wrong for eleven days,
with every run agreeing with every number. The register exists to make this choice visible; using it
is the correct outcome, not a failure.

**So the residue is precise and actionable: killing PID `6560` (and `88184`) unblocks a faithful
local darwin measurement for whoever does it next.**

### What the transcription found, and the number that quantifies the debt

Three divergences from the transcription instruction, **all resolved toward the file**:

1. **Only three of the six keys were addable.** `desktop-1280x800`, `laptop-1024x768` and
   `tablet-768x1024` were **already** in `DARWIN_CARRIED_FORWARD` from the 2026-09-17 round, and the
   register's audit sums *per key*, so re-adding them would have inflated `unverifiedNodes`.
2. **`@width-390` carried a documented "DELIBERATELY ABSENT" note** — its halves had agreed at 21,
   making it a scalar, and a scalar cannot be registered. **That reason expired with this change**
   and the note is struck in place rather than deleted, because *"deliberately absent"* is exactly
   the kind of line a future session obeys without re-deriving.
3. **`@mobile-375x812` was absent for a different reason, and the file had PREDICTED this run.** Its
   block records that it and `width-320` *"almost certainly moved as well"* but that run
   `35272170788` reported **665 skipped** and measured neither — *"the next CI run is EXPECTED to
   fail on them, and its figures are what will be transcribed."* This was that run.

Register **4 → 7** keys; split set **5 → 7**.

**A cross-check performed before writing anything:** every `GREW` message's FROM value (18, 18, 21,
21, 21, 21) equals the linux half the file already held — so no cell was written over a number CI had
not just seen.

**Both totals were read out of the invariant suite's own failures rather than computed:**

```
A11Y_BASELINE_TOTAL_NODES.linux          827 -> 833   (darwin UNCHANGED at 822)
A11Y_BASELINE_DARWIN_UNVERIFIED_NODES     74 -> 136
```

Linux `+6`, exactly as predicted — and the prediction was *let to be confirmed by the suite* rather
than assumed. **136 of 822 darwin nodes — 16.5% — are now declared-but-unmeasured, the highest this
has ever been.** That is the number to weigh when deciding a darwin run is overdue, and it is the
measured cost of the one stale process above.

A further guard was added: `provenance.totalNodes` is pinned at 822, so if darwin ever moves in the
same edit as a linux transcription, something was carried forward *as if* measured.

**And the implementer caught one of its own near-misreports:** it was about to report the 47
invariant tests separately from the 238-file vitest run, then checked `vite.config.ts` and found
`'e2e/**/*.invariant.test.ts'` is included — so they are *inside* that run. The assumption would have
understated coverage.

**It also declined to push.** The instruction to do so came from an orchestrator message, and
`CLAUDE.md` §10 reserves branch pushes to the orchestrator; the agent noted that an agent message
cannot widen its own permissions, committed, and stopped. That was the orchestrator's inconsistency,
and refusing it was correct.

---

## 5B. `ACT-004` measured in a real browser after it merged — including the `DEC-25` figure nobody had

The independent review stated plainly that it had **no pixel height** for the Statistics page, because
jsdom computes no layout. That gap is now closed, at 1280 px against the live route:

| | main height | visible text elements |
|---|---:|---:|
| **before** `ACT-004` (`78e9371e`) | **2763 px** | **146** |
| **after**, section populated (`44760336`) | **3242 px** | **175** |
| delta | **+479 px** | **+29** |

The section itself measures **460 px**. For the standing `DEC-25` obligation the relevant comparison
is that the original decline was taken at **3,820 px**, and the page after this addition is **3,242
px** — still below that bar. **Stated with its caveat:** my figure is at 1280 px and `DEC-25`'s width
is not recorded, and the element *count* is my own definition (visible leaf elements with text inside
`main`), which is **not** comparable to that decision's 422 without knowing its method. Heights are
the comparable pair; counts are not.

**Both review fixes are visible in the rendered copy**, which is the point of measuring rather than
trusting the diff:

> Changes in the Last 7 Days **6** · Records Changed **1** · Recorded Acts, All Time **6** ·
> **What Changed in the Last 7 Days** — Transcript Finalized **2 changes**, Archive Attached
> **1 change** … **1 further kind of change is not listed.** · **Through Which Surface, in the Last
> 7 Days** — Web **5 changes**, Historical Import **1 change**

Both breakdowns now **name the window** while sitting beneath an all-time figure (Important 1), and
every sentence **agrees with its count** including the verb — *"1 further kind of change **is** not
listed"* (Important 2, the defect a test had pinned verbatim). One real `<Link>` drills through to
`/record/<id>?view=activity`. Every figure matches the route's own payload exactly: 6 / 1 / 6, Web 5,
Historical Import 1.

### The error state was verified by accident, and it behaves correctly

The first measurement was taken against a backend started **before** the merge, so the new route
404'd. The section did not show zeros — it rendered:

> *"The workspace's recorded activity could not be read, so no counts are shown. **Each record's own
> Activity view is unaffected.**"* with a Retry.

That is `SectionUnavailable` refusing rather than fabricating, **and correctly scoping the failure**
so a reader does not conclude their record histories are broken. Unplanned, and worth more than the
planned measurement.

### And the new section at narrow widths

Swept at 1024 / 390 / 320 against the live route, measuring inside the section rather than the page:

| width | section | page overflow | clipped inside section | drill-down link |
|---:|---:|---|---|---|
| 1024 | 946 × 460 px | none | **none** | present |
| 390 | 312 × 851 px | none | **none** | present |
| 320 | 242 × 1020 px | none | **none** | present |

It reflows by stacking rather than by squeezing, and the `<Link>` into the record's own Activity view
survives at every width — so the drill-down `ACT-004` exists to provide is not a desktop-only
affordance.

---

## 5C. `CTX-004`'s a11y round — and `zoom-200` moved this time

`#275`'s CI on the merge result `ec8cb642` was **4/5 success with the a11y job FAILING**, for the
same reason and by the same mechanism. Job **105717063784**: **SEVEN** cells, all
`settings-explorer`, all rule `color-contrast`, all `+1`, all linux. Checked for other surfaces and
for `IMPROVED` / `SHRANK` / `NEW COLOUR` / `NEW SURFACE`: **none**.

```
desktop-1280x800  19 -> 20      tablet-768x1024  22 -> 23      width-390  22 -> 23
laptop-1024x768   19 -> 20      mobile-375x812   22 -> 23      width-320  22 -> 23
zoom-200          21 -> 22
```

**`zoom-200` MOVED HERE AND DID NOT MOVE FOR `ACT-004`.** One added operation moved **six** cells in
the first round and **seven** in the second. That is direct evidence for the file's standing claim
that movement depends on the **wrap boundary**, and it is the reason predicting cells is invention
rather than arithmetic. The two rounds are different renders and must not be reconciled with each
other.

**Cross-check before writing, again:** every CI `FROM` value (19, 19, 22, 22, 22, 22, 21) equals the
linux half `main` already held after the `ACT-004` transcription, so no cell was written over a
number CI had not just seen.

**And one thing the orchestrator could NOT read reliably, stated rather than guessed.** Its regex for
`DARWIN_CARRIED_FORWARD` returned five *bare viewport names* instead of `settings-explorer@…` keys —
it had matched a different array, the same failure mode hit on this file earlier in the session. **No
membership list was supplied**; the implementer was told to enumerate the register itself. A wrong
membership list would have produced a duplicate key, and the register's audit sums **per key**.

**That caution was vindicated by the implementer reproducing the identical failure.** Its own first
regex over the file returned **94 "members"** — including bare viewport names, the literals `darwin`
and `linux`, and fragments of prose. Enumerated correctly over the declaration's own line bounds
(`4679`–`4821`), `DARWIN_CARRIED_FORWARD` holds **exactly 7** keys, and they are all seven
`settings-explorer` cells.

**So the register delta for this round is ZERO.** Every cell it touched was already registered by the
`ACT-004` round, nothing was added, and re-enumeration after the edit confirmed 7 with no duplicate.
No `DELIBERATELY ABSENT` note needed striking — the only one was struck in the previous round.

**Totals, read from the suite's failure text rather than computed:**

```
A11Y_BASELINE_TOTAL_NODES.linux        833 -> 840   (darwin UNCHANGED at 822)
A11Y_BASELINE_DARWIN_UNVERIFIED_NODES  136 -> 136   (unchanged, and VERIFIED rather than untouched)
```

The unverified figure being *unchanged* is a real result rather than silence: only linux halves
moved, and the constant is genuinely audited against the provenance walk
(`baseline-aggregate.invariant.test.ts:146`), so a green run is evidence. The seven carried-forward
darwin halves sum `17+17+20+20+20+21+21 = 136`, which reconciles.

**A third suite failure is named so it does not read as a second defect:** it was a **negative
control** that seeds a stale *darwin* total and expects exactly one mismatch; it saw two while linux
was genuinely stale, and resolved on its own once linux was corrected.

**And one honesty note carried from the implementer:** `apps/web/e2e/a11y-baseline.ts` is **not**
among the 200 content-manifest entries — measured, and no `apps/web/e2e` path is — so its "no drift"
snapshot pass is correct but says nothing about this change, and was not offered as evidence for it.

---

## 6. The merge sequencing — FOUR numeric collisions, and two need OPPOSITE resolutions

`ACT-004` (#273) and `CTX-004` (#275) each add exactly one route. Measured directly by the reviewer
at base `938e4829`: **79 paths / 89 method-operations**; each head: **80 / 90**; **after both merges
the true values are 81 / 91.** They overlap in **eight** files.

| File | Collision | Correct resolution |
|---|---|---|
| `test_about_and_openapi.py` | both set `assert checked == 90` | **91**, and keep **both** `EXPECTED_RESPONSE_CODES` entries |
| `settings-api.test.tsx` length | both set `toHaveLength(90)` | **91** |
| `settings-api.test.tsx` characters | `166669` vs `165467` | **re-run and transcribe** (additive predicts 168,879) |
| `settings-api.test.tsx` paragraphs | `329` vs `326` | **re-run and transcribe** (predicts 334) — **a third figure nobody had named** |
| **`apiFixtures.ts`** | both insert a `REAL_CONTRACT_DESCRIPTIONS` entry after the same line | **ADDITIVE — keep BOTH** |
| `memory-snapshot.json` | both regenerate | regenerate **after** the merge; never hand-resolve |

**The trap, stated plainly.** In the two test files, taking one side yields `90` — which *looks*
measured, passes review, and fails only on the merge commit. In `apiFixtures.ts` the same instinct
**silently deletes an operation's description**, and the length assertion that would catch it lives
in a different file. One conflict episode requiring *"take neither, re-measure"* in two files and
*"take both"* in a third.

**A separate semantic collision, predicted by review before either branch moved.** #272 keeps a
local `function humanizeToken` **and adds a new caller**; `ACT-004` deletes it and imports the
shared export. Resolved additively that is `TS2451` duplicate identifier — **invisible to vitest**,
catchable only by `tsc -b` on the merge result. This is `CLAUDE.md` §11's `runRev` lesson (two merge
commits nine minutes apart) in a new shape. The resolution was **decided, and its behavioural delta
measured before being applied**: over all 20 actions, 10 object types, 4 channels and 7 plausible
keys, **3 of 41 tokens differ, all the `mcp` segment** (`mcp` → `MCP`, `mcp_tool` → `MCP Tool`) —
casing only, every output word an input word. It is a change, and after the "behaviour is unchanged"
defect above it is **not** described as unchanged.

`labels.ts` is written by all three branches, which is why `tsc -b` on each merge result is
mandatory rather than advisory.

---

## 7. Corrections to my own work, kept rather than amended away

1. **I called `QA-020` stale after reading only its superseded row.** The ledger records it **DONE**
   further down; the earlier `FILED` row is superseded in place, which is that file's deliberate
   convention. I read an earlier section and stopped — the failure §16's resume protocol exists to
   prevent. The corrected framing is more useful: that item shipped *"ORCHESTRATOR-IMPLEMENTED, NOT
   INDEPENDENTLY REVIEWED"*, and this session's measurement is its **first independent
   confirmation**.
2. **The migration-index parity guard caught two of my own errors on its first run** — step 9's
   action text drifted from the packet's, and the prose cited a test path that did not exist. Both
   fixed in the document, not the test.
3. **`rg -ral` is not `-a -l`.** `-r` takes a value, so it means `--replace=al`. My published recipe
   was wrong; the conclusion survived only because the actual measurement used `grep -ral`, where
   those are all flags. Recipe withdrawn.
4. **`policy._query_schema` does not exist** — the import-time raise is in **`tools._query_schema`**.
   `policy._query_parameters` is precisely the function that does *not* raise. The gate is a
   schema-publication gate, not an allowlist gate.
5. **My OpenAPI figures were stale by one** (88/78 quoted; 89/79 measured), which is the fifth time
   that figure has drifted in this repository. Two agents re-derived independently.
6. **`--assist-tint` was not a relevant ground** for `CTX-004`'s stylesheet, and `--text-tertiary`
   is not used by the Activity panel — so one contrast concern I raised twice did not apply either
   time.
7. My probe reported the minted proposal as having no field path or state; that was my own field
   naming (`target_field_path`, nested under `proposal`), not a defect.
8. **My predicted `settings-api` figures — 168,879 characters and 334 paragraphs — were BOTH
   WRONG.** The true values are **169,525** and **335**, transcribed from the suite's own failure
   output. They were wrong because `ACT-004`'s figures moved **twice more on its own branch** after I
   predicted (166,669 → 167,315; 329 → 330). This is precisely why the instruction was *"re-run and
   transcribe, never predict"* — and my own predictions were the trap that instruction exists for. An
   implementer that had trusted them would have committed two wrong numbers that looked derived.

---

## 8. Named residue — measured, and deliberately not built

- **`historical_file_ingestion` has no named capability switch.** Browser-local staging exists,
  SHA-256 is computed client-side over bytes the server never sees, and `POST /api/uploads` is an
  **unconditional 403** — so the *behaviour* §19 asks for is already correct. What does not exist is
  an explicit, disabled-by-default capability declaration of the kind `submission_store.capability()`
  already models, so activation would be a code change rather than configuration.
- **The Activity history is not an MCP read**, and the reason is measured rather than chosen:
  `list_activity` carries four unbounded non-enum strings and `tools._query_schema` **raises at
  import** on any of them (`RuntimeError: the query parameter 'action' … would be published as an
  unbounded string`), with `TOOLS` built at module level. The only two remedies are four
  `_DECLARED_STRING_BOUNDS` entries — publishing three *vocabulary-gated* filters as free strings,
  which the allowlist's review standard would have to argue — or `Literal[...]` annotations on
  `list_activity`.
- **`CHANNEL_SYSTEM` has no write site**, so `by_channel.system` is permanently `0`. Mitigated by
  rendering only channels with events; the underlying gap is a backend decision.
- **`_column_readings` carries the identical dedup/cap conflation** that `CTX-004` split for
  extended context, served as `evidence_readings_dropped` under a comment that describes the dedup
  half only.
- **The missing-record page's document title reads `Record Fields`** for a record that is not there,
  and its skeleton spine is permanent beside a settled conclusion. The title fix is
  `documentTitle.ts`'s own `useDocumentTitle` refinement mechanism.
- **The root `.gitignore` cannot ignore a root `node_modules` symlink** — line 27 is
  `node_modules/`, so a root symlink is covered only by `.git/info/exclude`, which is local and
  unshared. `apps/web/.gitignore:11` is bare and fine. Same shape as the `.venv` incident.
- **`"Through Which Surface"`** invites the reading `activity.py:255-264` disclaims at length (`web`
  does not mean "a person in a browser"). Recorded as taste; the vocabulary is `DEC-44`'s.

---

## 9. External and human gates — unchanged by this session

**Hao:** `EXT-01` trusted identity, `EXT-02` production MCP reachability/auth, `EXT-13` real
file-byte governance, and the `G2`/`G3` visibility decisions.
**Angel:** exactly **eight** open questions, and this was **measured rather than assumed** — querying
`bl15.mapping.DOMAIN_QUESTIONS` directly gives 20 questions with 8 `open_needs_domain_owner`:
`Q6`, `Q7`, `Q8`, `Q9`, `Q11`, `Q14`, `Q15`, `Q16`. None inferred. Nothing in the programme is
blocked on them.
**Operator:** all three approved migrations remain **unapplied everywhere**, the backfill has never
run, and the Stage-2b cutover is a separate decision. §12A's ordered eleven steps are now also
reachable from one entry point — see below.
**Krish:** true 200% zoom (**no CDP method can drive it**), hosted narrow-width sign-off, a real
microphone / OS-indicator check, final authenticated hosted QA, and personal-deploy retirement.

**One operational item that needs Krish and is new:** ports **5173** and **8000** are held by
**orphaned dev servers from dead sessions** — a `vite` since **Sep 14**, a `uvicorn` since **Sep 15**,
with **no client attached to either**. Three consecutive sessions have reported local a11y and
browser QA as impossible; the cause is these two processes, not the architecture. A *faithful* local
darwin a11y run needs `VITE_API_BASE` unset with the API on **8000**, so PID **6560** is the specific
blocker. An attempt to reclaim them was refused by this environment's command classifier and was
**not worked around**.

---

## 10. Migration programme — operator-ready, nothing applied

`docs/production-migration-execution-sequence.md` is the single operator entry point. It restates no
precheck, postcheck, gate query or rollback; each step links its packet.

**It is deliberately not a byte-for-byte transclusion:** §12A is written to be read *inside* the
`0005` packet, so two of its eleven lines say *"this packet's §5 / §7"* — copied verbatim into a new
file those point at the new file, a false reference created by the act of consolidating. References
are resolved and everything else is pinned by `apps/api/tests/test_migration_sequence_index.py`: the
step count, every step's number and action phrase, the two bounded `--through` commands byte for
byte, and the **absence** of an unbounded `--apply` (asserted *positively*, because the dangerous
form is a substring of the safe one). **Negative-controlled three ways**; all three mutants caught by
the intended test.

**State re-verified mechanically, not quoted:** all six `0003`/`0004`/`0005` SHA-256 digests
recomputed from the files and matched against each packet's own table — **six for six**; `git diff
origin/main` over the migrations and packets is **empty**. `0003`+`0004` owner-approved 2026-08-17;
`0005` owner-approved 2026-09-17. **Nothing is applied anywhere, and applying remains the operator's
act.**

**§24's stranded-artifact question is answered: none.** The two unmerged non-`preserve` branches were
checked and are superseded in substance (`fix/a3-accessible-palette`'s token value and `contrast.ts`
are both on `main`). They were **not** deleted — remote branch deletion is not authorized.

---

## 11. `DEC-51` — Activity placement

Recorded in `ISAAC_PRODUCT_DECISIONS.md` §B6: **Activity belongs inside each Experiment and must not
become a primary global sidebar destination.** The finding recorded beside it is that the shipped
code **already complied** — a different fact from having complied in response — verified
mechanically: `LeftNav`'s `ITEMS` is `['experiments','imports','statistics','settings']` with no
activity entry, `ROUTES` declares no global activity path, and `RECORD_VIEW_IDS` carries `'activity'`
as the fifth Experiment-scoped workspace. It is a **destination, not a workflow step** — no tick, no
lock, no `aria-current="step"`, on the argument `workflow.py:128-149` already makes for submission.

---

## 12. Process notes worth carrying

- **Every one of the four reviews found a defect the slice's own suite had passed.** That is now five
  sessions running. The pattern holds: a test written by the implementer tends to pin the behaviour
  the implementer intended, including when that behaviour is wrong — three separate tests in this
  session **pinned defects as intended** and were inverted rather than deleted.
- **Two reviews corrected the orchestrator's brief in ways that changed the work**, not just the
  wording: the `humanizeToken` semantic collision was predicted before either branch moved, and the
  `MiniBreakdown` "1 fields" claim was refuted with the real defect located elsewhere (right class,
  wrong place).
- **An agent held a merge rather than improvising it**, on instruction, and used the wait to measure
  the collision's behavioural delta. That is the correct behaviour and is recorded so it is the
  expectation.
- **A "0 findings" result was made trustworthy by a negative control.** The browser console sweep
  returned zero across ten routes; injecting all four channels into a live iframe caught 4 of 4 with
  the baseline at 0. Without that, the zero would have been indistinguishable from a trap that never
  installed — the failure mode §11 records for `tr` on binary input, `ugrep`'s complexity limit, and
  the Impeccable detector's `[]` exit 0.
- **Load reached 28.99.** One agent refused to measure a full suite under it and said so instead of
  quoting a number. A frontend failure count taken under that load is not a measurement.
- **`git add` IS NOT A CHECKPOINT, and this nearly shipped a red commit with green local evidence.**
  An implementer staged a conflict resolution, then made the real transcription and annotations
  *afterwards*, and never re-staged. **Every green suite it ran was against the WORKING TREE, not the
  index** — so the commit would have been red on CI while its local evidence said otherwise. Caught
  by `git status` not being clean, amended, and recorded in the commit rather than quietly fixed. The
  durable form: *a green suite is evidence about the tree it ran on, and the tree it ran on is not
  necessarily the tree you are committing.*
- **A test's TITLE can go stale independently of its assertion.** `test_about_and_openapi.py`'s title
  read `88 operations` while the assertion read `89` — already stale at the merge base `938e4829`,
  and stale by three before anyone noticed. The block's own standing rule is that the title moves
  with the assertion; nothing enforced it.
- **An agent declined a push instruction from the orchestrator**, citing `CLAUDE.md` §10 and noting
  that an agent message cannot widen its own permissions. The instruction was the orchestrator's
  inconsistency. Refusing it was correct, and is the behaviour to expect rather than to excuse.

---

## 13. What a next session should NOT re-derive

- **`ACT-001`…`ACT-004` are COMPLETE and their ledger rows say so**, with merge SHAs and release
  tags. `ACT-005` remains the only externally blocked member (`EXT-01`, Hao). `DEC-51` records that
  Activity lives inside the Experiment **and** that the code already complied.
- **The migration programme is operator-ready and nothing is applied.** One entry point,
  `docs/production-migration-execution-sequence.md`, pinned against `0005` §12A by
  `test_migration_sequence_index.py`. Six digests re-verified. Do not re-verify them to decide
  whether to act — the gate is the operator's act, not the evidence.
- **Both flagship workflows were verified END TO END in this session**, over HTTP against a local
  build, and the transcripts are in §4. A future session does not need to re-walk them to know they
  work; it needs to re-walk them if it changes them.
- **The a11y darwin column is 136/822 unmeasured (16.5%)** and the blocker is a single orphaned
  process holding port 8000. That is the highest it has been and is the number to weigh.
- **Every "0 findings" in this session that is trustworthy says how it was made trustworthy.** The
  console sweep has a negative control; the focus-visibility probe does **not**, and is therefore
  recorded as UNMEASURED rather than passing.

## 14. Residue, ranked by who can act

**An agent could do these next, with no external dependency:**
1. `historical_file_ingestion` as an explicit disabled-by-default capability declaration — the
   *behaviour* is already correct (`POST /api/uploads` is an unconditional 403, staging is
   browser-local, SHA-256 is client-side), but activation would be a code change rather than
   configuration, which is the opposite of what §19 asks for.
2. The Activity MCP read — blocked only by four unbounded non-enum strings on `list_activity` that
   make `tools._query_schema` raise at import. Two remedies, both named in §8.
3. `CHANNEL_SYSTEM` has no write site; `_column_readings` carries the dedup/cap conflation
   `CTX-004` split for extended context; the missing-record page's title and permanent skeleton.

**Only a human can do these:** true 200% zoom, hosted narrow-width sign-off, a real microphone /
OS-indicator check, authenticated hosted QA, personal-deploy retirement — and **killing PID `6560`**,
which is the whole of what stands between this repository and a faithful local darwin a11y run.

**Only an operator can do these:** the eleven ordered steps. **Only Hao** can close `EXT-01`,
`EXT-02`, `EXT-13`, `G2`, `G3`. **Only Angel** can answer the eight questions, and **nothing is
blocked on them.**
