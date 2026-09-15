# "The text is still stopping midway through half the block" — measured at last

The project owner has reported this defect **twice**. A prior slice responded by moving a global
prose measure from `38em` to `68ch`; he reported it again afterwards, unchanged. This document is
the measurement that explains why that fix could not have worked, and it exists mainly so the
**method** is not re-derived a third time.

## The headline: THREE DETECTORS, TWO OF THEM WRONG, AND BOTH WRONG SILENTLY

This is the same failure class `CLAUDE.md` §11 records for `tr` on binary input and for the
`ugrep` complexity limit — a tool that answers confidently and wrongly, caught only because a
second method disagreed.

| attempt | what it compared | result | why it was wrong |
|---|---|---|---|
| 1 | text width vs paragraph box, any element | a noisy list topped by `.needsyou-item` at 587 px | counted **flex columns of short labels** as wrapped prose. A column of four 65 px chips is not a paragraph. |
| 2 | same, restricted to pure-text nodes that wrap | **zero findings on every page** | `max-width` caps the paragraph's own BOX, so `box − text` is ≈ 0 **by construction**. The detector was measuring the one quantity the defect cannot move. |
| 3 | paragraph box vs nearest **block container's content width**, 3+ rendered lines | the table below | this is the quantity a reader actually perceives: a tall narrow column of text inside a wide empty card. |

**Attempt 2 returning zero on all seven pages is the part worth remembering.** It looked like
proof that the defect was already fixed. It was proof that the question was wrong.

## The second reason it was invisible: viewport

Measured at **1280 px, attempt 3 finds nothing either.** At that width the container is
approximately the prose cap, so there is no slack to see. The owner's screenshots are far wider.
A `68ch` cap does not create dead space until the container outgrows it — so **the defect is
invisible at the width a developer happens to be testing at**, which is why two passes missed it.

`resize_window` reports success while the rendered viewport does not follow (a documented trap in
this repository), so the measurement was taken **inside a same-origin iframe sized to 1728 px**,
which is the established workaround here.

## What it measures, at 1728 px

Every figure is `container content width − paragraph box width`, for paragraphs rendering **three
or more lines**.

| surface | class | paragraph | container | dead | lines |
|---|---|---:|---:|---:|---:|
| Capture | `.notes-sub` | 514 | 1347 | **833** | 3 |
| Capture | `.proposals-sub` | 514 | 1347 | **833** | 4 |
| Runs | `.vr-sub` | 522 | 1343 | **821** | 4 |
| Capture | `.proposal-rule` | 590 | 1323 | **733** | 4 |
| Historical Import | `.hi-steps-disclosure` | 471 | 1168 | **697** | 8 |
| Historical Import | `.hi-note` | 471 | 1168 | **697** | 3 |
| Historical Import | `.hi-lead` | 557 | 1200 | **643** | 6 |
| Governance | `.gov-canonical` | 557 | 1200 | **643** | 6 |
| Runs | `.runs-sub` | 520 | 840 | 320 | 3 |

**`My Experiments`, `Settings` and the record's `Fields` workspace are CLEAN.** That is the useful
half of the result: this is not a global stylesheet fault, it is a specific family of
section-subtitle and note classes. A global CSS constant is therefore the wrong instrument —
which is exactly what the `38em → 68ch` change was.

## What the fix is, and what it is explicitly not

The owner pre-empted the wrong fix: *"Do not interpret this as: make every paragraph span the
entire viewport."* An 1347 px line is worse to read than a 514 px one.

The defect is not width alone — it is **multi-line prose in a narrow column inside a wide box**.
Two quantities produce it, and the cheaper one to change is the number of lines:

1. **Shorten the prose.** A one-line subtitle in a wide container has no dead-whitespace problem,
   because it never forms a tall narrow column. Nine of the nine rows above are section subtitles,
   notes or disclosures — precisely the content §10 budgets at one line with the remainder behind
   an accessible disclosure. This is the primary fix and it is a copy decision, not a CSS one.
2. **Only then, per composition**, widen the measure toward ~80ch, narrow the container, or
   restructure into rows — chosen per surface, never once globally.

## One consequence for whoever guards this next

No jsdom test can see any of this: jsdom computes no layout, so `getClientRects()` is empty and
every number above is unavailable. A guard for this defect has to run in a real browser, and it has
to compare **paragraph box against container content width** — not text against paragraph, which
is the measurement that returns zero on a broken page.

## Provenance

Measured by the orchestrator on 2026-09-15 against a local build of `feat/v2-nav-settings`
(`main` = `dbf9d121` plus navigation and docs commits), on a record created through
`POST /api/experiments` with one run and five run fields filled. Synthetic data only; nothing
hosted was contacted.
