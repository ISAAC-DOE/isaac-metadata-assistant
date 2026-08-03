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

**The register check that matters most:** search results and evidence previews render
**backend-sourced** strings. Type `synthetic` into ⌘K. If you see
*"Synthetic XANES campaign … committed demo fixtures"* or a filename `mock_campaign.csv`,
that is **known and NOT yet fixed** — see §7. It is not a regression.

---

## 2. Standalone Validator — all 18 files (20 min)

Route: **`/krish/governance` → Validator tab**.

Files: `qa/validator-upload-package/` in the repo, or the ZIP.

```
ZIP     qa/validator-upload-package/isaac-validator-qa-files.zip
sha256  71c2303450487f0ae418e869844d336c2d7be53d01e87956901386f0292bc6f3
```

> Verify the checksum before you trust the archive:
> `shasum -a 256 qa/validator-upload-package/isaac-validator-qa-files.zip`

Upload in manifest order. For each: click **Upload JSON File**, pick the file, click
**Validate**, then check the verdict against `UPLOAD-GUIDE.md`.

**Three specific things to look for, because they are the point of this phase:**

1. **File 6 `empty-measurement-series.json`** → **PASS, 0 errors**, plus an advisory
   note **`NO_MEASUREMENT_SERIES`** on `measurement.series` saying the record contains no
   measured data. The PASS is correct (the schema sets no minimum) — the *finding* is
   that it passes, and the app now says so out loud. Before this phase it was a silent
   PASS with no signal at all.
2. **File 5 `invalid-date-time.json`** → **PASS**. Also correct-and-a-finding: declared
   `format` is not enforced. Do **not** "fix" the file. This is Dean question **Q20**.
3. **Every JSON file** shows an advisory `NO_LINKS`. Expected — each declares
   `links: []`, which the schema permits.

Also confirm, once each: no stack trace or server path in any message; switching files
clears the previous result; keyboard-only upload works (Tab to the control, Enter);
readable at a narrow window.

---

## 3. Reset safety (5 min) — the highest-priority fix

Route: **`/krish/experiments` → Reset Workspace**.

1. Open the dialog. It must state a **derived** count of what would be lost
   (confirmed answers / examples carrying progress / exported records) — real numbers,
   not "some data".
2. The typed phrase is now **`RESET EXAMPLE WORKSPACE`** (it used to be
   `RESET SYNTHETIC DEMO`).
3. **The important one.** With the dialog still open, open a second tab, answer a
   question on any example, then come back and complete the reset. It must **refuse**
   and re-check the workspace rather than proceeding — the state it showed you no longer
   holds. Nothing should be destroyed.
4. Then reset normally and confirm you get exactly five examples back.

---

## 4. Answers · edit · export (10 min)

1. Open an example with open questions → answer one → **reload the page** → the answer
   is still there.
2. Press **"I don't know"** → nothing is sent, the question stays open, and the list says
   the decision is **not saved / this visit only**. Reload: the question is open again.
   That is correct — it was never persisted, and the copy now says so.
3. Open a ready example → **Export** → confirm it reports success and a record + sidecar.
   **Reload** → still exported. Press Export again → it must refuse, not silently produce
   a second artifact.
4. On the export screen press **Re-Validate** with the network throttled or offline → it
   must **say** the refresh failed. A silent no-op here is the defect that was fixed.

---

## 5. Things that must NOT be there (2 min)

- No `isaac validate --official · exit 0` line under the verdict — that was a fabricated
  command transcript; no CLI ever ran.
- No **"Answer 5 Fields →"** button on the worked-example screen — it was dead and its
  count was hard-coded.
- **Create API Key** is disabled with a visible reason. Correct and intentional: there is
  no key-issuing operation in this build.

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
| Search results / evidence previews show `Synthetic XANES campaign…`, `mock_campaign.csv`, `01SYNTHXANESSEED…` | **Not fixed.** Backend-sourced. `MANAGED_SOURCE_DESCRIPTION` feeds `classify_experiment`, which decides what reset may delete — renaming it is a behaviour change to the destructive path and needs its own reviewed slice. |
| `invalid-date-time.json` passes | Declared `format` is unenforced. **Dean — Q20.** |
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
