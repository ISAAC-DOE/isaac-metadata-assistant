# Screenshot inventory — Statistics

**Date:** 2026-08-06 · **Branch:** `feat/record-verification` at `59d65c7`

## This is a manifest of what does NOT exist

**No screenshot in this inventory has been captured. No browser QA was performed. Playwright was not run.**

The responsive and accessibility claims in the test suite are **CSS string assertions and jsdom-rendered
component tests** — not observed browser renderings. `statistics.css` is asserted by substring matching for
wrap and reflow rules; jsdom does not lay out, so no test in this repository has ever measured a rendered
width, an overflow, a clipped label, or a focus ring.

Anyone reading "accessibility and responsive verified" about this slice should read it as "unit-tested",
which is a weaker claim, and this file exists so that difference is not lost.

## Required shots — all NOT CAPTURED

### General ISAAC → Record Verification

| # | State | Status | Reason |
|---|---|---|---|
| 1 | Public reference preflight | **NOT CAPTURED** | No browser session run |
| 2 | Authorized private result | **NOT CAPTURED** | **The private run has never executed.** This state cannot be photographed truthfully today — only faked from a fixture, which would misrepresent it |
| 3 | Loading | **NOT CAPTURED** | No browser session run |
| 4 | Running | **NOT CAPTURED** | No browser session run |
| 5 | Stale | **NOT CAPTURED** | Requires a cached result aged past 3600 s |
| 6 | Refreshing | **NOT CAPTURED** | No browser session run |
| 7 | Database unavailable | **NOT CAPTURED** | Reachable only via the private mode, which has no route |
| 8 | Timeout | **NOT CAPTURED** | No browser session run |
| 9 | Safe error | **NOT CAPTURED** | No browser session run |
| 10 | Technical details collapsed | **NOT CAPTURED** | No browser session run |
| 11 | Technical details expanded | **NOT CAPTURED** | No browser session run |

### My Stats

| # | State | Status | Reason |
|---|---|---|---|
| 12 | Truthful unavailable state | **NOT CAPTURED** | No browser session run |

### Viewports — every state above, at each width

| Width | Status |
|---|---|
| 1280 (or 1440) | **NOT CAPTURED** |
| 1024 | **NOT CAPTURED** |
| 768 | **NOT CAPTURED** |
| 390 | **NOT CAPTURED** |
| 320 | **NOT CAPTURED** |

**Total: 0 of 60 required captures.**

## What WAS verified, and by what means

So the gap is precise rather than total:

| Property | Means | Strength |
|---|---|---|
| Both corpus labels never interchangeable | 16 hostile mode strings (prototype keys, case variants, prefixes, superstrings, whitespace, newlines, comma-joined) × pure function and rendered DOM | Strong — adversarially probed |
| Eleven runtime states render | Component tests driving each state | Moderate — jsdom, no layout |
| Mutation accounting reconciles on screen | Rendered assertions on measured values, plus a deliberately unbalanced fixture | Strong |
| Three distinct safeguard words; `not_applicable` toned neutral | Rendered assertions; no `content:` declaration exists in the CSS, so no `::before` tick is possible | Moderate |
| No tick glyph, no host, no credential, no record id in the DOM | Sweep over rendered output in both modes | Moderate |
| Axe structural scan | Proven on two **real** defects in this section (a `<dl>` demoted to `<div>` orphaning `dt`/`dd`; an unnamed control) | Moderate — axe in jsdom, not a browser |
| Wrap/reflow at narrow widths | **CSS substring assertions only** | **Weak — no layout was computed** |
| Nothing animates | Assertion over the new CSS | Moderate |

## Not covered by any means at all

- Rendered layout at **390 px and 320 px**
- **200 % zoom** (this remains an open human sign-off gate from Phase 33/34 and is unrelated to this slice)
- Focus-ring visibility as rendered
- Chart legibility, tooltip behaviour, table overflow behaviour
- Long schema paths as they actually wrap on a narrow viewport
- Live-region announcements as a screen reader actually receives them
- Console errors in a real browser
- Absence of network requests to any portal, observed on the wire

## To close this gap

The Statistics screens cannot be photographed in a hosted browser until an image publishes, and no image
can publish while GitHub Actions is billing-blocked org-wide. A local dev-server run could capture items
1, 3–6 and 8–12 without waiting on CI; item 2 cannot be captured honestly until the authorized private run
has actually occurred.

Hosted QA remains `HOSTED QA PENDING (Krish)`: `/krish` sits behind an Authentik edge this environment
cannot authenticate to, and an agent must not enter credentials.
