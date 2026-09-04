# Two actors, two real browsers — the workflow proof, 2026-09-03

**Spec:** `apps/web/e2e/trusted/two-actor-real-browser.spec.ts` (new)
**Suite:** `apps/web/playwright.trusted.config.ts` — its own backend, its own workspace,
`ISAAC_EDGE_TRUST_VERIFIER=test_fixture`, `workers: 1`, `retries: 0`.
**Branch:** `feat/two-actor-real-browser-proof`, based on `feat/capture-proposal-ux` @ `3aa6e95`.
**Status:** green, twice, on the whole config; every mutation control below reproduced red.

---

## 0. What is new here, and why it could not have been written before this branch

[`docs/evidence/two-actor-workflow-proof-2026-09-02.md`](./two-actor-workflow-proof-2026-09-02.md)
and the spec it documents both state their central limitation as a fact about the build:

> `lib/api.ts` deliberately ships no `createProposal`, and `routes.py` records that *"NOTHING WAS
> REWIRED TO FEED THEM. There is no automatic producer"* — so **no surface in this build can create
> a proposal**, and a second browser would have nothing to click.

**That stopped being true on this branch.** PR #228 made *Finalize and Read* mint durable ingestion
proposals server-side, and PR #231 added *Propose a value from this note*. There are now two
surfaces a person can click to produce one, so Scientist B is a **second browser context driving
the real UI** rather than an HTTP client.

The older spec is **kept and untouched**. It measures a producer-less arrival over HTTP, which is
still exactly what an MCP producer would do; deleting it would trade one proof for another rather
than adding one. The trusted suite went **6 tests → 8**.

---

## 1. Tiers of claim

Every statement in this document belongs to exactly one of these, and each is labelled where it
appears.

| Tier | What it means | How to check it |
|---|---|---|
| **BROWSER-OBSERVED** | A real Chromium page did it, or a real Chromium page showed it. | The spec line quoted beside the claim. |
| **HTTP-CHECKED** | Read back independently from the FastAPI process over HTTP, never from the DOM. | The `server.*` / `request.*` call quoted beside the claim. |
| **CITED** | Proven somewhere else. Named, never reproduced, never restated as if measured here. | The file and test named. |

Two things this document does **not** claim anywhere: anything about the hosted deployment, and
anything about PostgreSQL. See §7.

---

## 2. The two actors, and the one control that makes "no reload" a measurement

- **Scientist A** — the Playwright `page` fixture (context 1). Creates the record, fills it in,
  reviews. A's page is opened in step 1 and is **not reloaded until step 9**.
- **Scientist B** — `browser.newContext()`: a second browser context with its own cookie jar, its
  own `localStorage`, its own page and its own pollers. **B issues no HTTP call of its own.** Every
  act attributed to B is a DOM interaction.
- **`request`** — the Playwright API context. Establishes starting state no surface may create (one
  seeded proposal, for the step-4 negative control) and reads server state back. It is never the act
  under test.

**One qualification on "B issues no HTTP call of its own", added after independent review (m-4).**
B's *acts* are all DOM interactions, but **every id B's act is addressed by is a server read
performed by the harness, never by B** — the run id passed to B's run selector, the note id B's
note card is located by, and the run id in B's `?run=` URL all come from `server.runs()` /
`GET .../notes` issued by the test process. A scientist would read those off the screen. This is a
harness convenience, and it means the spec proves that B's *acts* go through the UI, not that every
identifier B needed was discoverable on B's screen.

**The "without a reload" claim is enforced, not narrated.** `plantSameDocumentMark` writes a value
onto `window`; `assertSameDocument` re-reads it at steps 2, 4, 7 and 8. A client-side navigation
keeps it and a full page load destroys it, so a stray `page.goto`/`page.reload` added by a later
edit fails an assertion instead of quietly weakening the proof. **Step 9 is that control's own
negative control**: after the deliberate reload the mark is asserted `null`, which is what proves
the earlier assertions were capable of failing.

**One thing this file deliberately does NOT prove.** `lib/selfMintedProposals.ts` is a module-level
map, so it is per page load; B's context is a different page load, so B's proposals are invisible to
A's copy and A's arrival note fires normally. **Same-tab own-act suppression is not exercised
across contexts** — this file is evidence that it does not reach across contexts, which is a
different and weaker claim than evidence that it works.

---

## 3. Step by step — what was asserted, and what was observed

Test 1: *"a colleague's browser mints proposals, and A judges them without ever reloading"*.

### Step 1 — A builds the record through the website

| Asserted | Tier | Observed |
|---|---|---|
| The record holds no technique and no material name before A types one | HTTP-CHECKED | both `null` on the served draft |
| Two record-level values entered through the real capture controls (a `<select>` for the schema enum, a text box for the free-text path) and saved once | BROWSER-OBSERVED | `Save record description`, one click, both keys in one save |
| Both reached the server | HTTP-CHECKED | `system.technique` = the schema's first enum member; `sample.material.name` = the synthetic literal |
| Both survive a **reload** | BROWSER-OBSERVED | re-read into the controls after `page.reload()` |
| The Runs workspace is reachable **by keyboard**: Tab to the sidebar link, Enter | BROWSER-OBSERVED | `aria-current="page"` moved to `Runs`; the switch was same-document |
| Two runs added, each given a **different** `context.environment` through the run editor, the second reached via the toolbar's **Next run** | BROWSER-OBSERVED + HTTP-CHECKED | each value polled on the server, not read back off the control (`RunCard` autosaves; reading the box back would confirm only that typing works) |
| The open run names what it inherits and what it overrides | BROWSER-OBSERVED | `.run-section-summary` matches `/\d+ inherited · \d+ overridden on this run/` |
| Writing run two did not touch run one | HTTP-CHECKED | run one still holds its own value |
| The compact rows show the two runs' conditions, and neither claims an override | BROWSER-OBSERVED | row 0 contains run one's value and not run two's; **zero** `overridden` chips |

The "no override chip" assertion is deliberate rather than incidental: writing a **run field** is not
an override — an override is a run's declared divergence from a value the **record** holds, written
through `/overrides` — and a chip that appeared on every row would be that distinction collapsing
with nothing else on the screen to say so.

### Step 2 — A opens the review surface

| Asserted | Tier | Observed |
|---|---|---|
| Collapsed, the capture panel offers **exactly one** entry action | BROWSER-OBSERVED | `Capture Experiment Notes`; `button:visible` count = **1** |
| The collapsed panel makes **no recording claim** | BROWSER-OBSERVED | its intro sentence contains none of `record/Record/audio/Audio/microphone/voice/Voice` |
| Switching workspace did not reload the page | BROWSER-OBSERVED | same-document mark intact |

The recording assertion exists because finalize posts **text**, and turning a recording into text
needs a transcription provider this build never ships configured. A collapsed header mentioning
recording would present it as an equally finished path — the C1 correction
`transcriptCaptureContent.ts` records making, pinned here from the outside.

### Step 3 — B, a second browser, mints proposals through the UI

| Asserted | Tier | Observed |
|---|---|---|
| B opens the same record's Capture & Proposals workspace | BROWSER-OBSERVED | heading visible in context 2 |
| B selects run two, types a transcript, presses **Finalize and Read** | BROWSER-OBSERVED | the panel reports `Review 2 Proposals` |
| The server gained **exactly** the number the panel reported | HTTP-CHECKED | delta measured against a count captured before B acted |
| **Every** minted proposal names the run B *selected* | HTTP-CHECKED | both carry run two's id |
| The closed rule table read the two clauses the transcript wrote for it | HTTP-CHECKED | `context.temperature_K` = `300`, `context.thermodynamics.atmosphere` = `"dry nitrogen"` |
| **Review N Proposals moves focus**, not only the viewport | BROWSER-OBSERVED | `document.activeElement.id === "ingestion-proposals-heading"` |
| B proposes a value from a **stored note**, at a different target, for run two | BROWSER-OBSERVED | field path, run and value all chosen in the form; `Propose This Value` |
| That stored one further proposal | HTTP-CHECKED | count = seed + 2 + 1 |

The transcript is written against `apps/api/isaac_api/transcript_capture.py`'s closed rule table,
read rather than guessed, and **names no run in its words** — `_RUN_REFERENCE` would produce a run
clarification, and the run is chosen in the panel's own selector, which is the behaviour under test.

**FINDING F-1 (measured, and it forced a step into the spec).** `UnmappedNotesPanel` fetches the
record's notes **once per mount** and takes no live-refresh input at all — its props are
`{ experimentId }`, with no equivalent of the `activity` summary `IngestionProposalsPanel`
receives. Finalizing a transcript stores notes and proposals **in the same save**, and on that
screen the proposals appear on their own while the notes, one panel above them, do not. Measured:
without a reload the card for a note the server is already serving is not in the DOM at all
(`element(s) not found`). The spec therefore reloads **B's** page before B's second act, with the
finding written into the code beside it. A's document is untouched, so no "without a reload" claim
about A is affected.

### Step 4 — A is told once, and was not told about what was already there

| Asserted | Tier | Observed |
|---|---|---|
| A's page has not been reloaded since step 1 | BROWSER-OBSERVED | same-document mark intact |
| An arrival note appears **on its own** | BROWSER-OBSERVED | `.proposals-arrival-note-text` visible without any interaction |
| It counts **B's three arrivals and not the seeded one** | BROWSER-OBSERVED | `"At least 3 proposed changes arrived and are ready to review."` |
| A screen-reader user was told too | BROWSER-OBSERVED | the `sr-only[role="status"]` region contains `proposed change` |
| Neither sentence leaks content | BROWSER-OBSERVED | neither contains the proposed value nor `context.` |
| **The running total did not grow across ≥2 change-feed polls** | BROWSER-OBSERVED | unchanged after **two further `GET .../changes` from A's own page**, counted at the wire — see the scoping paragraph below for what this does **not** discriminate against |
| The seeded proposal is **visible** — never hidden, only never announced | BROWSER-OBSERVED | its card is on screen |

The hydration negative control is the point of the seeded proposal: it was on the record **before**
A's panel mounted, and `lastOpenCountRef === null` on first load is the guard that suppresses it. If
hydration announced, the total would read `At least 4` — which is exactly what mutation **M1**
produced (§5).

The settle is **the client's own poller**, not a sleep: two further `GET .../changes` from A's page
are counted at the wire, so the window the total is held over is a real number of real polls rather
than an elapsed time.

**CORRECTION I-1, made after independent review, and the earlier claim is struck rather than
reworded because it claimed more than it established.** ~~That assertion discriminates against
"fires once per POLL rather than once per EVENT", the defect `CLAUDE.md` §11 records being found by
review in this area.~~ — **MEASURED FALSE.** Removing the count-rise guard, and separately removing
the signal-dedupe early return, **both leave the assertion green** (1 passed, twice). The reason is
structural rather than lucky: the announce effect's dependency array is
`[proposalSignal, reload, activity, experimentId]` (`apps/web/src/components/IngestionProposalsPanel.tsx:907`),
and `activity` is `null` once the record read has caught up — so an **empty poll re-runs the effect
at all**, and there is nothing for a per-poll bug to fire from.

So the two claims are now kept apart:

- **What the assertion establishes (BROWSER-OBSERVED):** across at least two further change-feed
  polls, the running total did not grow. It is kept because it is the assertion that fails if
  anything on this screen re-counts a standing arrival while the page sits still.
- **The events-not-polls property (verified by READING, not by this assertion):** it is enforced by
  that dependency array. `IngestionProposalsPanel.tsx:907` is the line; nothing in this spec can
  distinguish it.

### Step 5 — current versus proposed, and whose run

| Asserted | Tier | Observed |
|---|---|---|
| Each card names the run it is about | BROWSER-OBSERVED | `On run Run 2` |
| The live region is **mounted and empty** before anyone asks | BROWSER-OBSERVED | `.proposal-current-body` count 1, text empty |
| An **absence** is reported as an absence | HTTP-CHECKED + BROWSER-OBSERVED | server holds nothing at `context.temperature_K`; the card reads `No value is stored at this field path.` |
| On a target that **does** hold something, the read is the **run's own** value | BROWSER-OBSERVED | run two's environment, **not** run one's, **not** the proposal's |
| And the label says whose value it is | BROWSER-OBSERVED | `.proposal-current-label` matches `/run/i` |
| The atmosphere card carries the phrase exactly as B typed it | BROWSER-OBSERVED | `dry nitrogen`, matched against no vocabulary |

**Correction made while writing this step, recorded rather than silently fixed.** The first version
asserted `.proposal-current-body` had **count 0** before the control was pressed. It fails with
`Received: 1`, and the component is right: that div is the card's `aria-live` region and must stay
**mounted** to be announced at all — a region inserted together with its content is never read out.
"Nothing has been read yet" is therefore an **empty** region, not an absent one.

### Step 6 — a corrected acceptance, and a rejection

**BRIEF CORRECTION C-1, measured over HTTP against this backend.** The slice brief asked this step
to assert that *"Correct the Value, Then Accept"* **supersedes** the original, leaves a **new open**
proposal, and leaves canonical run two **unchanged**. **All three are false.** The control is an
`accept` with `accepted_from: "edited"`:

```
POST .../proposals/{id}/review  {"action":"accept","accepted_from":"edited","value":"…"}
→ 200  state: "accepted"   accepted_from: "edited"   applied_via: "run_field"
       accepted_value: "corrected dry argon"   applied_run_id: <run two>
```

That is what the panel's own hint says it does — *"Accepting this way records that the proposed
value was WRONG and that this is the corrected one"* — and **`Supersede…`**, a different control
behind the same disclosure, is the one that does not write. The spec asserts the real semantics and
carries the brief's premise in a comment so a future reader can see it was checked.

| Asserted | Tier | Observed |
|---|---|---|
| The correction editor is **prefilled** with the proposed value | BROWSER-OBSERVED | `JSON.stringify("dry nitrogen")` |
| The **same** proposal is accepted, and no new one is created | HTTP-CHECKED | state `accepted`; proposal count unchanged |
| The record keeps "corrected" apart from "as proposed" | HTTP-CHECKED | `accepted_from: "edited"` |
| The **corrected** value is what reached run two, into an **empty** path | HTTP-CHECKED | run two now holds it; **CORRECTION I-2** — it held `undefined` before, not "something else": nothing in this file writes that path before step 6, so the old row (and the assertion behind it, `expect(before).not.toBe(CORRECTED)`) was unfalsifiable and its wording was false. The assertion is now `toBeUndefined()`, which is both checkable and the stronger claim |
| Run one's whole document is unmodified | HTTP-CHECKED | `toEqual` against a snapshot taken before |
| A **rejection** writes nothing | HTTP-CHECKED | both runs' whole documents identical before and after |
| The typed reason is stored verbatim | HTTP-CHECKED | the `reject` history entry's `reason` |

### Step 7 — B moves the target; A's accept is refused as stale

| Asserted | Tier | Observed |
|---|---|---|
| The temperature proposal is **fresh** before B acts | HTTP-CHECKED | `target_stale: false` |
| B, in its own browser, types a new temperature into run two | BROWSER-OBSERVED | run editor, autosaved |
| It reached the server | HTTP-CHECKED | run two's temperature = 77 |
| The proposal's target is now reported stale | HTTP-CHECKED | `target_stale: true` |
| A's card tells the reader the value moved | BROWSER-OBSERVED | `CHANGED since this proposal was made` |
| **A's accept is refused, on A's screen, in a scientist's words** | BROWSER-OBSERVED | `.proposals-error` contains *"has changed since this proposal was made"* and *"Nothing was written"* |
| The proposal is still **open** — a refusal is not a judgement | HTTP-CHECKED | `state: "open"` |
| Canonical run two reflects **B's edit alone** | HTTP-CHECKED | 77, never the proposed 300 |

Accept **is still offered** on a stale card, and that is deliberate rather than a defect:
`acceptUnavailableReason` fails **open** (the staleness was read a moment ago and a value can move
back) and the card's own copy says the **server** decides. So the guarantee under test is the
server's refusal surfacing on the screen — which is what the click measures.

### Step 8 — the acceptance lands on exactly the run it named

| Asserted | Tier | Observed |
|---|---|---|
| The note-proposal is still fresh, though B moved a **different path on the same run** | HTTP-CHECKED | `target_stale: false` — staleness is scoped to the `(run, path)` pair |
| A accepts it as proposed, through the card | BROWSER-OBSERVED | card moves to `Accepted` |
| The server recorded it | HTTP-CHECKED | `accepted_from: "candidate"`, `applied_run_id` = run two, `accepted_value` = B's value |
| **Only run two changed**, and it is a change | HTTP-CHECKED | run two holds the accepted value; what it held **immediately before the click** was read from the server (**m-1**: this used to compare two constants the spec had already asserted distinct, so it could not fail) and is A's step-1 value; run one's **whole document** is `toEqual` its pre-accept snapshot, rev and version included |
| Attribution | HTTP-CHECKED | the `accept` history entry carries `actor_subject: synthetic.browser.reviewer`, `actor_trust_basis: test_fixture` |
| **Proposing stays unattributed** | HTTP-CHECKED | the `propose` entry names nobody; the proposal's own `trust_basis` is `unattributed` |
| The change feed reports the proposal **once**, above the pre-accept cursor | HTTP-CHECKED | one `proposal` entry, state `accepted`; run one **absent**; every entry's `changed_at_rev` **> the record's rev at the cursor**, with a non-vacuity assertion before the loop |
| **The Runs workspace picked the value up with no navigation and no reload** | BROWSER-OBSERVED | the still-mounted, `hidden` `#record-workspace-runs` contains it *before* A goes there |
| And it is visible once A does go there; run one's row does not show it | BROWSER-OBSERVED | compact rows |
| The dry run **read** the accepted value | HTTP-CHECKED | `official_validator_ran: true`; `ok: false`; **no refusal names the accepted value**; the served run draft holds it; two per-run verdicts |

The attribution row is worth reading twice: **B made this proposal through a website, in a real
browser, and the record still names nobody for it.** Creating a proposal requires no attributable
actor in any deployment, and inventing one would be a fabrication. Only the **judgement** is
attributed.

The live-refresh assertion reads the **hidden but still-mounted** Runs panel. `RecordWorkbench`
keeps a workspace mounted once visited and hides it with the `hidden` attribute, so `RunsSection`
has been live since step 1 and its own pollers were running while A sat on Capture & Proposals.
Asserting the value in its DOM *before* switching is a claim about the live refresh; a
switch-then-look assertion would have measured a fresh mount instead.

**The record does not export, and that is the measurement rather than a disappointment.** A record
created through the product's own path still owes blocking questions nothing in this test answered,
so the honest claim is the two-part one above.

### Step 9 — durability across a reload

| Asserted | Tier | Observed |
|---|---|---|
| This backend is **filesystem**-backed | HTTP-CHECKED | `/api/health` → `experiment_storage.backend: "filesystem"` |
| Both runs, and run two's accepted value, survive | BROWSER-OBSERVED | after `page.reload()` |
| The accepted proposal survives; the rejected one is **kept**; the refused one is still open | BROWSER-OBSERVED | three cards, three states |
| **A reload destroys the same-document mark** | BROWSER-OBSERVED | the negative control for steps 2–8 |

PostgreSQL durability is **CITED, not claimed**:
`apps/api/tests/test_proposal_durability.py`'s real-engine scenarios, which run in CI against a real
`postgres:18`.

### Step 10 — nothing here can submit, export or accept on its own

**BRIEF CORRECTION C-2, measured.** The brief asked for a browser assertion that "the Submit control
exists ONLY on the scientist-facing export screen". **This build ships no control labelled *Submit*
anywhere** — there is no portal submission in the product, and Ready to Export says so in its own
words. The act that finalizes a record is **Export Official Record + Sidecar**.

**BRIEF CORRECTION C-3, measured.** The brief expected that control to be *disabled* on a
not-yet-ready record. `ExportReadiness` renders it inside `{pendingZero && dryRunOk && …}`, so on
this record the control **does not exist** — the gate is an **absence**, not a greyed button, and
the screen states the blocking count instead. That is a stronger property than the one asked for,
and it is asserted as what it is.

| Asserted | Tier | Observed |
|---|---|---|
| No control on the proposals surface offers submit / export / publish / finalize | BROWSER-OBSERVED | the region is asserted **visible first** (**m-3**: four `toHaveCount(0)` checks scoped to a locator that matched nothing would all pass), then four regex queries, count 0 each |
| No `Submit` control on the record screen at all | BROWSER-OBSERVED | count 0 |
| On Ready to Export the export control is **absent** while the record blocks export, and the screen says why | BROWSER-OBSERVED | count 0; `.preexport-title` matches `/still block export/` |
| No `Submit` on the export screen either | BROWSER-OBSERVED | count 0 |
| **No permitted MCP tool name** contains `accept`, `approve`, `submit`, `export`, `publish` or `delete` | source-parsed | `PERMITTED_TOOL_NAMES` read out of `apps/api/isaac_api/mcp/policy.py`, comments stripped, non-empty set asserted first |
| This deployment mounts **no MCP transport at all** | HTTP-CHECKED | `POST /api/mcp` → **404**, not 403 |

The Python-side proofs are **CITED, not reproduced**: `apps/api/tests/test_mcp_boundaries.py`
`::test_a_scope_named_submit_cannot_be_expressed_at_all`,
`::test_registering_a_submit_tool_raises_rather_than_being_ignored`, and
`::test_no_mcp_scope_can_reach_an_accepting_finalising_or_exporting_operation`. The policy source is
parsed here rather than fetched because there is no `tools/list` to call in this configuration —
the same precedent, and the same comment-stripping hardening, as
`apps/web/src/__tests__/connect-your-agent.test.tsx`.

### Step 11 — the record screen, by keyboard alone

For each of **Record Fields / Runs / Capture & Proposals / Graph**: focus is blurred to the top,
Tab is pressed until the sidebar link is focused (bounded at 150; **a miss throws**, so an
unreachable control cannot read as a pass), Enter activates it.

| Asserted | Tier | Observed |
|---|---|---|
| Every workspace link is reachable by Tab and activates on Enter | BROWSER-OBSERVED | 4 of 4. **The guarantee is `tabUntil`'s throw**, not a count assertion — `expect(presses).toBeGreaterThan(0)` on a 1-based counter could not fail, and was removed at both sites (**m-2**) |
| `aria-current="page"` moves to the activated one | BROWSER-OBSERVED | 4 of 4 |
| Continuing to Tab lands **inside `<main>`, inside the panel that link just opened** | BROWSER-OBSERVED | the focused element's nearest `.record-view-panel` ancestor is `record-workspace-<id>`, matched per workspace |
| At **768 px**, the Assistant drawer opens by keyboard as a modal dialog | BROWSER-OBSERVED | `aria-modal="true"` |
| And Tab from inside it reaches the composer | BROWSER-OBSERVED | `aria-label="Ask the assistant a question"` focused |
| Escape closes it | BROWSER-OBSERVED | `aria-modal` gone |

**FINDING F-2, stated precisely because the brief assumed otherwise.** The application does **not**
move focus into the newly opened workspace region — activating an in-app `<Link>` leaves focus on
the link. That is ordinary SPA behaviour and is not a defect on its own: the sidebar precedes
`<main>` in DOM order and a skip link exists, so the next Tab enters the region. The spec therefore
asserts the property a keyboard reader actually needs (the workspace's content is next in the
keyboard order) rather than a focus move the app does not perform, and this finding is recorded
rather than dressed up.

**The 768 px viewport is where the drawer exists at all.** `AssistantDrawer`'s trigger is CSS-hidden
at desktop, so asserting the dialog semantics at 1280 would have silently tested nothing.

---

## 4. Viewports (test 2)

Test 2 builds its own record, has B mint through the capture panel, and observes the arrival once at
**1280×800** — then holds the standing note and card up at **1024×768, 768×1024, 390×844 and
320×568**.

| Asserted at each of the four widths | Tier | Observed |
|---|---|---|
| The arrival note is still visible | BROWSER-OBSERVED | 4 of 4 |
| The card is visible, with its proposed value and its run named | BROWSER-OBSERVED | 4 of 4 |
| The card's **right edge is inside the viewport** | BROWSER-OBSERVED | `boundingBox().x + width ≤ width` — a box that sticks out passes `toBeVisible` and is unreadable, which is the failure a narrow pass exists to catch |
| **No horizontal page overflow** | BROWSER-OBSERVED | `documentElement.scrollWidth === clientWidth`, 4 of 4 |
| No reload happened across all five widths | BROWSER-OBSERVED | same-document mark intact |
| Looking at a record at five widths created nothing | HTTP-CHECKED | proposal count unchanged |

It is a **separate test** rather than a loop inside test 1 for a reason test 1 makes unavoidable: an
arrival is announced **once** and the visible note is a running total, so re-observing "an arrival
is legible" at five widths inside that test would mean either five colleagues' acts or four
observations of one already-standing note wearing the same words.

320×568 is the narrowest width this repository's own accessibility baseline measures
(`apps/web/e2e/a11y-baseline.ts`'s `NARROW_WIDTHS`).

---

## 5. Mutation controls

Every mutation was applied to **production source**, run, observed red, then reverted with
`git checkout --`, and the tree re-verified. The suite was re-run green afterwards (§6). Backend
mutations were preceded by killing the reused uvicorn on port 8101 so the edited module was actually
loaded.

| # | Mutation | File | Step that went red | Failure |
|---|---|---|---|---|
| **M1** | Let the arrival announcement fire on **hydration**: `if (isArrivalReload && previousOpen !== null && openNow > previousOpen)` → `if ((isArrivalReload \|\| previousOpen === null) && openNow > (previousOpen ?? 0))` | `apps/web/src/components/IngestionProposalsPanel.tsx` | **4** | `Expected: "At least 3 proposed changes arrived…"` / `Received: "At least 4 …"` |
| **M2** | Remove the focus move from *Review N Proposals*, keeping the scroll: delete `heading.focus()` | `apps/web/src/components/TranscriptCapturePanel.tsx` | **3** | `Expected: "ingestion-proposals-heading"` / `Received: null` |
| **M3** | Remove the **staleness gate** on accept: `if current != proposal.target_digest:` → `if False:` | `apps/api/isaac_api/routes.py` | **7** | `.proposals-error` — `element(s) not found`; the refusal never reached A's screen |
| **M4** | Make an accepted run-field proposal write the **first** run rather than the one it names: `run = exp.runs[0]` at the `APPLIED_VIA_RUN_FIELD` branch | `apps/api/isaac_api/routes.py` | **6** | `step 6: the CORRECTED value is what reached run two` — `Expected: "SYNTHETIC corrected — dry argon…"` / `Received: undefined` |

**M4 is caught at step 6, not step 8, and that is reported as observed rather than as intended.**
Step 6's corrected acceptance is the first run-field write in the sequence, so the wrong-run mutation
fails there before step 8's `run one's whole document is unchanged` assertion is reached. The
guarantee is the same one; the earliest assertion that can catch it does.

**M3 was done by editing the backend, not by a route stub, and M4 likewise.** The brief suggested a
temporary test-only stub for the wrong-run case specifically. A stub at the route boundary cannot
express M4 at all — the run a proposal is applied to is chosen *inside* `_apply_accepted_proposal`,
below any seam a test could stand in front of — so the mutation was made where the decision is made,
run once, and reverted. `git status --short` after the revert (§6) is the evidence that nothing was
left behind.

A **fifth control is built into the spec itself** and needs no mutation: step 9 asserts that a
reload destroys the same-document mark, which is what proves the four `assertSameDocument` calls in
steps 2, 4, 7 and 8 were capable of failing.

---

## 6. Verification — commands and results

```
$ cd apps/web && npx tsc -p e2e/tsconfig.json --noEmit
(no output, exit 0)

$ E2E_UVICORN=/Users/krishverma/Documents/ISAAC/.venv/bin/uvicorn npm run test:e2e:trusted
[trusted-setup] hermetic: ordinary workspace empty; backend attributes through the
                test_fixture verifier, so acceptance is reachable.
Running 8 tests using 1 worker
  8 passed (1.9m)

$ E2E_UVICORN=… npm run test:e2e:trusted          # second run, flakiness check
  8 passed (1.8m)

$ E2E_UVICORN=… npm run test:e2e:trusted          # third run, after every mutation was reverted
  8 passed (1.8m)

$ E2E_UVICORN=… npx playwright test --config=playwright.trusted.config.ts \
      e2e/trusted/two-actor-real-browser.spec.ts --reporter=line
Running 2 tests using 1 worker
[1/2] … › a colleague’s browser mints proposals, and A judges them without ever reloading
[2/2] … › the arrival and the card stay legible from 1280 down to 320
  2 passed (54.5s)

$ .venv/bin/python scripts/build_memory_snapshot.py \
      --graph-dir /Users/krishverma/Documents/ISAAC/graphify-out \
      --out apps/api/isaac_api/data/memory-snapshot.json \
      --detail-out apps/api/isaac_api/data/memory-graph-detail.json --check
ok: apps/api/isaac_api/data/memory-snapshot.json matches regenerated snapshot (no drift)
ok: apps/api/isaac_api/data/memory-graph-detail.json matches regenerated graph detail (no drift)
(exit 0)

$ git status --short
 M apps/web/e2e/trusted/fixtures.ts
?? apps/web/e2e/trusted/two-actor-real-browser.spec.ts
?? docs/evidence/two-actor-real-browser-proof-2026-09-03.md
```

**The trusted suite went 6 → 8 tests.** The six existing ones are unchanged and all still pass.

**No production code was changed by this slice.** The only tracked edit is 14 added lines in
`apps/web/e2e/trusted/fixtures.ts`: `subject` and `trust_basis` declared on `ServerProposal`, with a
comment stating why they sit beside `history` (they are the **proposer's** identity, and the accept
entry's `actor_subject`/`actor_trust_basis` are the **reviewer's** — declaring them makes a server
that stopped sending one a compile error rather than an `undefined` that quietly satisfies a
`toBeNull()`).

**Snapshot:** no drift. `apps/web/e2e/**` and `docs/evidence/**` are not in the served-content
manifest — checked with the two-artifact command above rather than assumed.

**Data boundary:** none. Every record, run, transcript, note, proposal and value is created by these
specs seconds earlier in a workspace `global-setup` wipes; nothing production-derived was read, and
nothing left the process. The backend under test is filesystem-backed at
`$TMPDIR/isaac-e2e-trusted-workspace`.

**Authorization basis:** `CLAUDE.md` §15, the 2026-08-29 application-side scope extension —
*"website proposal review, edit, acceptance, rejection, deferral and conflict handling … and the
associated tests, documentation, migration artifacts, PRs and safe integration."* This slice adds
tests and one evidence document and changes no production behaviour.

---

## 7. What remains unverified

Named rather than implied, and none of it is closed by anything above.

- **Hosted.** Nothing here says anything about `/krish`. It sits behind an Authentik edge this
  environment cannot authenticate to, and `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` is set by **no**
  shipped deploy artifact (`apps/api/tests/test_deploy_config.py` pins that), so a hosted acceptance
  would answer **409 `human_actor_required`**. **HOSTED QA PENDING (Krish).**
- **PostgreSQL.** This backend is filesystem-backed, asserted from `/api/health` in step 9. Step 9's
  reload proves the values are re-read from the server and proves nothing about a database. The
  durable leg is `apps/api/tests/test_proposal_durability.py`'s real-engine scenarios in CI, cited.
- **A real Claude/MCP client.** Step 10 parses the permitted tool set out of `mcp/policy.py` and
  measures that **no transport is mounted** (404). No MCP client connected to anything here, and no
  provider was configured or called.
- **Same-tab own-act suppression.** Not exercised: B is a different browser context, so
  `selfMintedProposals`'s per-page-load map cannot apply. See §2.
- **A record that actually exports.** No test here reaches `pendingZero && dryRunOk`, so the enabled
  export control was never observed — only its truthful absence.
- **Accessibility beyond the keyboard walk and the overflow checks.** No axe scan is run by these
  specs; the a11y baseline suite is separate and untouched.
- **Every browser except Chromium.** The trusted config declares **one** project,
  `trusted-1280x800`, on `devices['Desktop Chrome']`. Nothing here was observed in Firefox or
  WebKit, and the narrow-viewport pass in §4 is Chromium at four emulated sizes — not four real
  devices and not four engines.
- **The 200 %-zoom human sign-off.** Unchanged, still open, and not automatable — no CDP method
  drives it.

---

## 8. Findings and brief corrections, collected

| Id | What | Where it is recorded |
|---|---|---|
| **F-1** | `UnmappedNotesPanel` has no live refresh: notes minted by a finalize on the same screen do not appear until the page is reloaded, while the proposals from the same save do. | §3 step 3; a comment in the spec beside the reload it forced |
| **F-2** | The app does not move focus into a workspace region on activating its sidebar link. Not a defect on its own (DOM order + skip link), but the brief assumed otherwise. | §3 step 11; a comment in the spec |
| **C-1** | *Correct the Value, Then Accept* **writes** the corrected value and accepts the same proposal — it does not supersede, does not mint a new proposal, and does not leave canonical unchanged. The brief said all three. | §3 step 6; a comment in the spec |
| **C-2** | This build has **no** `Submit` control anywhere. The finalizing act is *Export Official Record + Sidecar*. | §3 step 10 |
| **C-3** | On a not-yet-ready record the export control is **absent**, not disabled. | §3 step 10 |
| **C-4** | `.proposal-current-body` is a mounted, empty `aria-live` region before a read, not an absent one — a `toHaveCount(0)` assertion is wrong about the design. | §3 step 5 |
| **C-5** | The served draft reports a field the record does not hold as `null`, not by omitting it. | §3 step 1 |


---

## 9. Corrections made after independent review

The review returned **MERGE-after-fixes**. Every item below was applied to the spec and to this
document, and the earlier wording is struck in place rather than deleted wherever it was a claim a
reader could act on.

| Id | What the review found | What changed |
|---|---|---|
| **I-1** | The step-4 settle was claimed to discriminate against "fires once per poll rather than once per event". Measured: removing the count-rise guard **and** removing the signal-dedupe early return both leave it **green** — the announce effect never re-runs on an empty poll, because `activity` is `null` once the record read has caught up. | The assertion is **kept** and rescoped: it establishes that the running total did not grow across ≥2 change-feed polls. The events-not-polls property is now attributed to the effect's dependency array (`IngestionProposalsPanel.tsx:907`) and marked **verified by reading**. Spec comment and §3/§4 of this document both rewritten. |
| **I-2** | `expect(atmosphereBefore).not.toBe(CORRECTED_ATMOSPHERE)` compared `undefined` — nothing writes that path before step 6 — so it was unfalsifiable, and its message ("the run held something else a moment ago") was false and republished here. | Now `expect(atmosphereBefore).toBeUndefined()`, which is checkable and is the stronger claim: the acceptance wrote into an empty path. Step-6 row corrected. |
| **m-1** | Step 8's "it is a change" compared `envTwo` with `envProposed` — two constants already asserted distinct. | The value run two held is now **read from the server immediately before the accept click** and compared, plus a second assertion that it was A's step-1 value. |
| **m-2** | `expect(presses).toBeGreaterThan(0)` on a 1-based counter, at two sites. | Both removed, with a comment stating that **`tabUntil`'s throw** is the guarantee. |
| **m-3** | Four `toHaveCount(0)` checks scoped to the proposals region with no assertion that the region exists. | `await expect(proposals).toBeVisible()` added before them. |
| **m-4** | "B issues no HTTP call of its own" was true of B's acts but silent about how B's targets were addressed. | §2 now states that every id B's act is addressed by is a **server read performed by the harness, never by B**. |
| **m-5** | The unverified list did not mention browser coverage. | §7 now names it: **only Chromium**, one project, four emulated widths — not four devices and not four engines. |
