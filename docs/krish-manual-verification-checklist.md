# Krish · manual verification checklist

The shortest exact sequence that verifies what this environment could not. Nothing in
this file is a claim that the hosted app was tested — `/krish` sits behind an Authentik
edge that returns `302` here, and an agent must not enter credentials. Every hosted line
below is **HOSTED QA PENDING (Krish)**.

Times are rough and assume you are not debugging.

---

## 0. Before you start (2 min)

```bash
git -C ~/Documents/ISAAC fetch origin && git -C ~/Documents/ISAAC log --oneline origin/main -1
curl -s -o /dev/null -w '%{http_code}\n' https://isaac.slac.stanford.edu/krish/api/health
```

- A `302` means the edge is in front of you — expected, and the reason the rest of this
  is yours to do.
- Sign in, then open `/krish/api/health` in the browser and read `commit`. **If it does
  not match `origin/main`, stop** — Flux has not rolled yet, and everything below would
  be testing the previous image.

---

## 1. Product language (3 min) — visual, yours to accept

Open `/krish/experiments`, `/krish/load`, `/krish/governance`, `/krish/settings`.

**Should NOT appear anywhere in normal product copy:** Synthetic · Synthetic data ·
Synthetic workspace · Synthetic-only · Scenario · Fake · Mock · Fixture · Demo ·
Seeded test data.

**Two things that SHOULD still appear, and must not be "fixed":**

| Where | What | Why it stays |
|---|---|---|
| Governance & Safety → Policy | a paragraph naming the Validator and CSV preview as tools that **do read** what you paste or pick | it is TRUE, and the previous wording denied it |
| Settings → Data & Privacy | the `synthetic-only` data-regime value | it is the machine contract from `/api/health`, quoted verbatim, not product prose |

**The register check that matters most is NOT here — it is step 5 of §2b, and running it
here would report a known defect as fixed.** Search results and evidence previews render
**backend-sourced** strings, so the check needs records to search. This section runs
before §2b, i.e. in the ordinary workspace, which holds none: measured, `GET /api/search?q=synthetic`
there returns `workspace.total = 0` with `reason: "scope_has_no_records"`. Zero hits is
what an empty scope looks like, not what a fixed register looks like — and the same
⌘K search inside a worked example returns five, carrying exactly the strings the check is
hunting for. Do the language sweep on this page's four routes here; do the search check
once you are inside the walkthrough.

---

## 1b. Record workspaces — the 2026-09-03 redesign (10 min)

Open any record (`/krish/record/<id>`, from `/krish/experiments` or the worked example
per §2b). The single long record page is gone; the record sidebar now lists four
**Workspaces** beneath the (unchanged, server-derived) workflow spine: **Record Fields**
(the default — what `/record/<id>` still resolves to bare), **Runs**, **Capture &
Proposals**, **Graph**. Each is a real link (`?view=fields|runs|capture|graph`), so you
can middle-click, bookmark, and use Back/Forward normally — try Back after following one;
it should land you on the workspace you left, not at the top of the record.

**Runs (master-detail).** The list is compact rows (label, ordinal, condition summary,
"N of M run fields", override/exported/save-state chips). Click a row — its whole header
is the control, there is no separate "Focus" button — and exactly one run's full editor
opens, replacing the list. Previous/Next move between loaded runs without leaving the
editor. **Type something unparseable into a field, then click Back or another row**: a
real confirmation dialog should appear (focus moves into it, Escape = Stay) before any
navigation happens. This is the one interaction most likely to regress silently.

**Capture & Proposals.** The entry button now reads **"Capture Experiment Notes"** (not
"Start a capture"). Open it, and check the panel shows exactly one primary action for
whatever state it's in (idle / recording / held / processing / proposals ready / error) —
never two competing calls to action. A finalized capture should produce open proposals
below, listed **oldest-first by default** (the server's own default — a review queue
reads chronologically); use **Show Newest** or the order control to bring a just-arrived
proposal into the first window. Accepting one should feel like the same review flow §4
already exercises.

**Assistant (desktop ≥1025px).** A **Collapse Assistant** control should shrink the panel
to a labelled 44px strip and back; do this while mid-typing a question and confirm the
draft survives collapse and a workspace switch (it should — the panel is never
unmounted). The Assistant's own copy should name the workspace you're on (e.g. "You are
on Runs.").

**Narrow widths (≤1024px).** The four workspaces become a wrapping pill row. The
workflow spine becomes a single-row compact stepper (same five steps, no re-derivation —
if a step's blocking reason has changed from what you'd expect on wide, that is a
regression to report). The Assistant reverts to the existing slide-over drawer behaviour
— confirm Tab does not escape it while open (a keyboard trap here was found and fixed in
review; re-check it once, since it's exactly the kind of thing a later change could
reintroduce silently).

Nothing above changes what gets exported or what counts as valid — this section is
IA/interaction only. If a control's *location* surprises you but its *behaviour* is
correct, that's expected: this was a reorganisation, not a rewrite of the underlying
record/run/proposal model.

---

## 2. Standalone Validator — all 18 files (20 min)

Route: **`/krish/governance` → Validator tab**.

Files: `qa/validator-upload-package/` in the repo, or the ZIP.

```
ZIP     qa/validator-upload-package/isaac-validator-qa-files.zip
sha256  daee2ebc7bfa9dc0abbb167f575b02ab2477f384c38bcacbff63f1b124a66d04
bytes   66823
```

> Verify the checksum before you trust the archive:
> `shasum -a 256 qa/validator-upload-package/isaac-validator-qa-files.zip`
> `wc -c qa/validator-upload-package/isaac-validator-qa-files.zip`
>
> Both numbers are pinned by `tests/test_validator_qa_package.py::test_the_committed_archive_matches_the_digest_and_size_the_operator_is_told_to_verify`,
> which hashes the committed bytes and then asserts this document quotes the same
> values — so a rebuilt archive cannot leave this page stale and hand you a
> mismatch on a correct archive.

Upload in manifest order. For each: click **Upload JSON File**, pick the file, click
**Validate**, then check the verdict against `UPLOAD-GUIDE.md`.

**Three specific things to look for, because they are the point of this phase:**

1. **File 6 `empty-measurement-series.json`** → **PASS, 0 errors**, plus an advisory
   note **`NO_MEASUREMENT_SERIES`** on `measurement.series` saying the record contains no
   measured data. The PASS is correct (the schema sets no minimum) — the *finding* is
   that it passes, and the app now says so out loud. Before this phase it was a silent
   PASS with no signal at all.
2. **File 5 `invalid-date-time.json`** → **PASS**. Also correct-and-a-finding: declared
   `format` is not enforced. Do **not** "fix" the file. This is Dean question **Q20** — **answered
   2026-08-12: shadow mode is allowed; arming the official validator is NOT authorized.** So this
   file's behaviour is now correct **by decision**, not merely unresolved, and it stays as the
   reproducer.
3. **Every JSON file that parses** shows an advisory `NO_LINKS`. Expected — each declares
   `links: []`, which the schema permits. File 15 `malformed-json.json` is the exception and
   is not a failure of this check: it cannot be parsed, so it is refused as unreadable with
   no verdict card and therefore no advisories at all.

Also confirm, once each: no stack trace or server path in any message; switching files
clears the previous result; keyboard-only upload works (Tab to the control, Enter);
readable at a narrow window.

---

## 2b. Precondition for §3 and §4 — open the worked example first (1 min)

**This step is new, and §3 and §4 were UNPERFORMABLE without it.** Both used to start
from an example record on `/krish/experiments`. The five built-in examples are no longer
in that workspace at all — they exist only inside a **worked-example session**, and
`/krish/experiments` is empty until you open one.

1. Open `/krish/experiments`. Expect **"No experiments yet"** and zero rows. That is
   correct, not a broken deployment.
2. Start the walkthrough — either the **Take the Guided Walkthrough** card (first visit
   in this browser), or **`/krish/settings?tab=help` → Replay Tutorial** (always
   available). The empty state's **Go to Help & Tutorial** button takes you there.
3. A **Worked Example** bar now sits under the top bar on every screen, and
   `/krish/experiments` lists **five** rows. The mode chip reads **Worked Example**.
   Those five rows are the session's own copies — the scope changed, not the screen.
4. Do §3 and §4 **without leaving the walkthrough**. Skip, Close, Escape and Finish all
   discard the session and everything you did inside it. A **reload is safe** (the tab
   remembers which session it is in), and pressing Replay again is **not** — it discards
   the open session first.
5. **The register check, moved here from §1 because it is only performable here.** Type
   `synthetic` into ⌘K. Expect **five** hits. If they show *"Synthetic XANES campaign …
   committed demo fixtures"* or a filename `mock_campaign.csv`, that is **known and NOT
   yet fixed** — see §7, and it is not a regression. Run this **inside** the walkthrough:
   run in the ordinary workspace it returns zero **workspace** hits because there are no
   records there to search (project-memory leads still appear — ⌘K renders both groups, so
   you get "No workspace matches." above a list of memory leads), and zero workspace hits
   would read as the defect being fixed.

---

## 3. Reset safety (5 min) — the highest-priority fix

Route: the **Worked Example** bar → **Reset Worked Example**. (It was
`/krish/experiments` → "Reset Workspace". There is no such control: `POST /api/demo/reset`
now refuses without a session header, so its trigger moved into the bar, which only exists
while a walkthrough is open. Complete §2b first.)

1. Open the dialog. It must state a **derived** count of what would be lost
   (confirmed answers / examples carrying progress / exported records) — real numbers,
   not "some data".
2. The dialog arms on typing **`RESET`** — short, and shown in the field's own label
   ("Type RESET to confirm this destructive reset"). The longer
   `RESET EXAMPLE WORKSPACE` is the **backend's** phrase, sent internally on execute and
   deliberately never surfaced; you never type it. (This step used to tell you to type
   the long phrase, which leaves the confirm button disabled and stalls §3 at its most
   important step.) The dialog's own title is **Reset the Worked Example**.
3. Read the disclosure. It must say the ordinary workspace is **not** in this scope and
   that this control cannot reach it — and it must say that the rows on My Experiments
   **are** what gets reset. If it claims "Nothing in My Experiments is in this scope",
   that is the false sentence this phase removed; report it.
4. **The important one — and the two-tab trick now needs care.** The session pointer lives
   in `sessionStorage`, which is **per tab**. A freshly opened tab is *not* in the
   walkthrough and will show an empty workspace, so the old instruction ("open a second
   tab") no longer reaches the examples. Use Chrome's **Duplicate tab** on the tab that is
   already in the walkthrough — a duplicate inherits `sessionStorage`, so it is in the
   same worked example. Then: leave the reset dialog open in the first tab, answer a
   question on any example in the duplicate, come back and complete the reset. It must
   **refuse** and re-check rather than proceeding — the state it showed you no longer
   holds. Nothing should be destroyed. If Duplicate tab does not carry the session
   (browser-dependent), say so in your report rather than recording this step as passed.

   > **In the duplicate, do not press Escape, Close, Skip or Finish — the same warning as
   > §2b step 4, which applies here and is easy to miss because the duplicate opens with
   > the coach mark showing.** Because the duplicate inherits the pointer, it resumes the
   > walkthrough into its `running` phase, and each of those four controls discards **the
   > session both tabs share**. Do that and the first tab's reset returns
   > `404 tutorial_session_not_found` instead of the `412` this step is testing — which
   > looks like the precondition machinery failing when in fact the thing it was guarding
   > was deleted from under it. Answer the question and switch back; leave the duplicate
   > open.
5. Then reset normally and confirm you get exactly five examples back.

---

## 4. Answers · edit · export (10 min)

Inside the worked example from §2b — these records do not exist outside it.

1. Open an example with open questions → answer one → **reload the page** → the answer
   is still there, and you are still in the same worked example.
2. Press **"I don't know"** → nothing is sent, the question stays open, and the list says
   the decision is **not saved / this visit only**. Reload: the question is open again.
   That is correct — it was never persisted, and the copy now says so.
3. Open a ready example → **Export** → confirm it reports success and a record + sidecar.
   **Reload** → still exported. Press Export again → it must refuse, not silently produce
   a second artifact.
4. On the export screen press **Re-Validate** with the network throttled or offline → it
   must **say** the refresh failed. A silent no-op here is the defect that was fixed.
5. Finish or close the walkthrough. The bar goes, the chip returns to **Workspace**, and
   `/krish/experiments` is empty again — everything from §3 and §4 went with the session.
   The completion panel must **say** that; if it claims "Nothing you have looked at was
   changed", report it.

---

## 5. Things that must NOT be there (2 min)

- No `isaac validate --official · exit 0` line under the verdict — that was a fabricated
  command transcript; no CLI ever ran.
- No **"Answer 5 Fields →"** button on the worked-example screen — it was dead and its
  count was hard-coded. (Needs the §2b session; that screen is unreachable without one.)
- **Create API Key** is disabled with a visible reason. Correct and intentional: there is
  no key-issuing operation in this build.
- On the **ordinary** `/krish/experiments` (no walkthrough open) there must be **no**
  "Reset Worked Example" button, no "Open the Worked Example" button, and no second
  **"Replay Tutorial"** button — the empty state points at Help & Tutorial with **Go to
  Help & Tutorial** instead. The mode chip must read **Workspace**, and its tooltip /
  accessible name must say only that **nothing in this build adds a built-in example record
  to this workspace** — a statement about what the build does. It must **not** say the
  workspace is empty, and must **not** say the built-in examples *are not in* it: both are
  claims about the directory's contents, which nothing in this app reads. Both have shipped;
  the second was caught only by a second review. If you see either, report it.

---

## 6. Responsive / zoom sign-off (5 min) — only you can accept this

At **1280**, **768**, **390**, **375** and **320** px wide, and at **200 % browser zoom**:
`/experiments`, a record detail, Guided Completion, Export Readiness, Governance →
Validator, Settings.

Look for: clipped or overlapping text, a horizontally scrolling page body, touch targets
too small, focus outlines invisible when tabbing.

**What is and is not already automated at these widths — corrected.** An earlier version
of this file said *"390 and 320 are not covered by any automated project … unverified by
anything."* **That was wrong**, and the correction matters because it changes what you
actually need to look at.

- **Layout at 390 and 320 IS covered.** `apps/web/e2e/specs/layout-widths.spec.ts` sweeps
  `[1280, 1024, 768, 640, 390, 375, 320]`, checking nested overflow, lost text and
  obscured controls at each. Its header states that *320 "is included and is not
  optional: it is the WCAG 1.4.10 reflow width"*. It moves the viewport itself inside one
  project rather than adding five more, deliberately, for runtime — which is why 390/320
  do not appear in the project list and why I misread their absence as absent coverage.
- **Accessibility (axe) at 390 and 320 is NOT covered.** `a11y-axe.spec.ts` is
  per-project, so it only ever runs at 1280 / 1024 / 768 / 375 / zoom-200. Adding two
  narrow projects for it needs measured baseline counts for **both** platforms
  (`a11y-baseline.ts` keys by project and refuses an unlisted one), which needs a CI
  round-trip per platform. Attempted, then abandoned rather than ship a half-configured
  baseline. **This is the real remaining gap.**

So: contrast, accessible names and focus visibility at **390 and 320** are the part worth
your eyes. Gross layout breakage at those widths would already have failed CI.

---

## 7. Known and deliberately not fixed

| Item | Status |
|---|---|
| Search results / evidence previews show `Synthetic XANES campaign…`, `mock_campaign.csv`, `01SYNTHXANESSEED…` | **Not fixed.** Backend-sourced. `MANAGED_SOURCE_DESCRIPTION` feeds `classify_experiment`, which decides what reset may delete — renaming it is a behaviour change to the destructive path and needs its own reviewed slice. **Check it from §2b step 5, inside the worked example.** The ordinary workspace has nothing to search, so a search run there returns zero hits and would read as this being fixed. |
| `invalid-date-time.json` passes | Declared `format` is unenforced. **Dean — Q20, ANSWERED 2026-08-12: not authorized to be armed.** Expected, permanent, and not a defect to report. |
| Real-record display | **Closed by default** by the database owner. Not a gap to close here. |
| Upload that creates a record | `POST /api/uploads` is an unconditional 403 with no implementation behind it. Governance, not a bug. |
| Wrong-typed API answer returns no typed 422 | It no longer returns 500 (fixed). A precise 422 is a follow-up. |
| Tutorial | Built and tested; see whether PR #51 is merged at the commit you are testing. |
| Accessibility scans at 390 / 320 px | **Not automated.** See §6 — layout at those widths *is* covered; axe is not. |

---

## 8. If something fails

Capture: the route, the viewport, the exact visible text, and `/krish/api/health`'s
`commit`. The commit is what makes the report actionable — without it there is no way to
know which image you were looking at.

Do **not** capture or replay an auth token, and do not paste one into an issue.
