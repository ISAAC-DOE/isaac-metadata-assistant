# Browser, accessibility and responsive testing

This document describes the real-browser test baseline for the ISAAC Metadata Assistant SPA:
what it runs, how to run it, exactly how 200% zoom is emulated and where that emulation stops
being faithful, what it found, and — importantly — what it does **not** and **cannot** cover.

It is a *test* baseline. It changes no application source. Every defect it found is recorded as
a finding with a tracking entry, not fixed here.

---

## 1. What this is

| | |
|---|---|
| Runner | [Playwright](https://playwright.dev) (`@playwright/test`), **Chromium only** |
| Accessibility engine | [`@axe-core/playwright`](https://github.com/dequelabs/axe-core-npm) + `axe-core` |
| Location | `apps/web/e2e/**`, config `apps/web/playwright.config.ts` |
| Scope | 18 catalogued surfaces × 5 viewport/zoom dimensions, plus interaction specs |
| Size | **568 tests** (567 run, 1 conditionally skipped), ~4 minutes locally with default workers |
| Licences | Playwright Apache-2.0, axe-core and `@axe-core/playwright` MPL-2.0 — **devDependencies only** |

The new packages are dev-only and are **not** in the shipped bundle. Proof:

```bash
cd apps/web && npm run build
grep -o -i -F playwright dist/assets/*.js | wc -l   # -> 0
grep -o -i -F axe-core   dist/assets/*.js | wc -l   # -> 0
```

Nothing here is collected by vitest: `apps/web/vite.config.ts` scopes vitest to
`include: ['src/**/*.{test,spec}.{ts,tsx}']`, and every file in this suite lives under
`apps/web/e2e/`. Do not move a `*.spec.ts` from `e2e/` into `src/` — vitest would try to run a
Playwright spec inside jsdom.

---

## 2. How to run it

### Prerequisites

Two servers. Playwright starts **one** of them.

1. **The backend — you start it.** Playwright cannot: it needs the repository's Python venv,
   which lives outside `apps/web`. It runs with **no database and no credentials**.

   ```bash
   # from the repository root
   .venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000
   ```

   Never set a `PG*` variable for this. The database is unreachable from a laptop by design
   (`docs/postgres-test-db-guide.md`) and this suite must never contact one.

2. **The Vite server — Playwright starts it** (`webServer` in `playwright.config.ts`), on
   port **5173**.

### Run

```bash
cd apps/web
npm run test:e2e:install     # once — downloads Chromium
npm run test:e2e             # the whole suite
npm run test:e2e -- --project=desktop-1280x800     # one dimension
npm run test:e2e -- --grep "@zoom"                 # one tag
npm run test:e2e:ui          # interactive
npm run test:e2e:report      # open the last HTML report
npm run typecheck:e2e        # tsc over e2e/ (NOT part of `npm run build`)
```

`global-setup.ts` asserts the backend is up, refuses to run unless it reports
`mode: "synthetic-only"`, and seeds the synthetic workspace **once** through
`POST /api/demo/run` — which is idempotent by construction (it upserts a fixed canonical id
rather than appending, so re-running never changes the record count). If the backend is
missing you get the exact command to run, not 500 browser timeouts.

### Port 5173 is not arbitrary

The backend's default CORS allow-list (`apps/api/isaac_api/app.py` → `DEFAULT_CORS_ORIGINS`)
contains only `http://localhost:5173` and `http://127.0.0.1:5173`. If you serve the SPA on any
other port, **every API call fails CORS** and the app renders its honest "Backend Not Running"
screen — which would silently turn this into a test suite for the error state. If 5173 is
already taken:

```bash
# terminal 1 — allow the alternate origin explicitly
ISAAC_UI_CORS_ORIGINS="http://127.0.0.1:5274" \
  .venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000

# terminal 2
cd apps/web && E2E_WEB_PORT=5274 npm run test:e2e
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `E2E_WEB_PORT` | `5173` | Port for the Vite server under test |
| `E2E_WEB_HOST` | `127.0.0.1` | Host it binds to |
| `E2E_BASE_URL` | `http://$HOST:$PORT` | Overrides both |
| `E2E_API_BASE` | `http://127.0.0.1:8000/api` | Backend the SPA and global setup talk to |
| `E2E_EXTERNAL_WEB_SERVER` | unset | `1` = you started the web server yourself; Playwright will not |

---

## 3. The five dimensions

| Project | Viewport | DPR | Runs |
|---|---|---|---|
| `desktop-1280x800` | 1280×800 | 1 | `@responsive` + `@interaction` |
| `laptop-1024x768` | 1024×768 | 1 | `@responsive` |
| `tablet-768x1024` | 768×1024 | 1 | `@responsive` |
| `mobile-375x812` | 375×812 | 1 | `@responsive` + `@interaction` |
| `zoom-200` | 640×400 | **2** | `@responsive` + `@zoom` |

`@interaction` runs at 1280 and 375 only — the `max-width: 640px` breakpoint changes the chrome,
so dialog and keyboard behaviour at phone width is not implied by the desktop run, but running
those specs five times would multiply runtime for no extra signal.

`mobile-375x812` is plain desktop Chromium at 375 CSS px. `isMobile` and `hasTouch` are
deliberately **false**: this suite is about layout and accessibility at a width, not about touch
emulation. Do not read "mobile" as "tested on a phone".

### Determinism

Fixed `locale: 'en-US'`, fixed `timezoneId: 'UTC'`, forced `colorScheme: 'light'` (the app
declares `<meta name="color-scheme" content="light">`), and `reducedMotion: 'reduce'` — which
engages the app's own `@media (prefers-reduced-motion: reduce)` rules in
`src/styles/base.css:258`. The `app` fixture additionally injects a stylesheet zeroing any
animation or transition that media query does not reach, so a measurement can never be taken
mid-transition.

> Note: in `@playwright/test` 1.62 `reducedMotion` is a **browser-context** option, not a
> top-level test option (only `colorScheme`, `deviceScaleFactor`, `hasTouch`, `isMobile`,
> `locale` and `timezoneId` are). It is therefore set via `contextOptions`. The effect is
> identical.

---

## 4. The 200% zoom mechanism — exactly what it is, and what it is not

### What is emulated

A user who presses <kbd>Cmd</kbd>/<kbd>Ctrl</kbd>-<kbd>+</kbd> twice in a 1280×800 window gets,
inside the page:

* a **CSS layout viewport of 640×400 CSS px** — every `@media (max-width: …)` query, every
  `vw`/`vh` unit and every flex/grid reflow now sees 640; and
* **`window.devicePixelRatio` doubled** (1 → 2), because one CSS px now covers two device px.

So the `zoom-200` project is exactly:

```ts
{ viewport: { width: 640, height: 400 }, deviceScaleFactor: 2 }
```

That is genuinely distinct from every other project in the matrix. It is **not** the 375px phone
case (different breakpoint, DPR 1) and it is **not** "a 640px-wide window", which would report
DPR 1. `e2e/specs/zoom-200.spec.ts` asserts all of it in the live page —
`innerWidth === 640`, `innerHeight === 400`, `devicePixelRatio === 2`,
`matchMedia('(min-resolution: 2dppx)').matches`, `matchMedia('(max-width: 640px)').matches` —
so if somebody later "simplifies" the config by dropping `deviceScaleFactor`, the suite fails
loudly instead of quietly degrading into a narrow-viewport test.

### What was rejected, and why

* **`document.body.style.zoom`** — not used. It is a non-standard rendering quirk that scales a
  subtree *without changing the layout viewport*, so media queries never fire. That is the
  opposite of what browser zoom does.
* **CDP `Emulation.setPageScaleFactor`** — evaluated and rejected. It is **pinch** zoom: a
  visual-viewport transform that magnifies without reflowing and without changing
  `devicePixelRatio`. It would test even less than the `zoom` property.

### Honest limits of the emulation

These belong in any report that cites this suite:

1. `window.outerWidth` reads 640 here. Under real browser zoom it would still read **1280**
   while `innerWidth` read 640. A page that measured `outerWidth` would behave differently.
2. Real zoom also scales the browser's own scrollbar and chrome. Headless Chromium has neither,
   so the usable content width is very slightly more generous here than on a real machine.
3. Real zoom applies a `visualViewport.scale`; here the scale stays `1` and the effect is
   reproduced through viewport size + DPR. The spec asserts `visualViewport.scale === 1` so the
   distinction is recorded in the suite itself, not just in this document.
4. Text metrics differ marginally: a real zoom rounds glyph metrics at the zoomed scale;
   DPR-2 rasterisation is close but not identical. Sub-pixel layout differences of <1px are
   therefore expected, and all layout tolerances are 1 CSS px.
5. It does **not** test OS-level text scaling, a browser minimum-font-size setting, or
   `text-size-adjust`. Those are separate user settings with separate failure modes.
6. Only the **200%** step is covered. WCAG 1.4.10 (Reflow) is specified at **400%** — i.e.
   320 CSS px — which this suite does not test.

**This is emulation. It is not a substitute for a human sitting in front of a real browser at
200% zoom.** That human sign-off gate (narrow viewport + 200% zoom) remains open and remains
Krish's to give.

---

## 5. What is covered

### Per surface, at every viewport (`@responsive`)

* **axe scan** — `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `best-practice`. Accessible names,
  ARIA attribute/role validity, landmark uniqueness, `page-has-heading-one`, form labels,
  keyboard access to scrollable regions, and **automated colour contrast**.
* **No horizontal page scroll** — `document.documentElement.scrollWidth <= clientWidth`, and the
  same for `body`. Wide content (tables, code blocks, the graph canvas) must scroll inside its
  own container; the page body never may.
* **No clipped text** — text cut off by an ancestor's `overflow: hidden` with no ellipsis and no
  scrollbar.
* **No occluded controls** — every interactive control is hit-testable at the centre of its
  visible area.
* **Landmarks** — exactly one `<main>`, at `#main`, targeted by a skip link; a banner region.
* **Heading hierarchy** — exactly one `<h1>` (or the recorded absence of one), no skipped levels.
* **Status is not colour-only** (best-effort) — status-like elements carry text or an accessible
  name; decorative dots are `aria-hidden`.
* **Long strings** — a 240-char unbreakable token typed into real controls, plus one clearly
  labelled synthetic DOM injection.

### Interaction (`@interaction`, at 1280 and 375)

* **Dialog semantics** — the ⌘K search modal (`aria-modal`, accessible name, focus into the
  dialog, Tab and Shift+Tab containment, Escape closes, focus restored to the trigger); the Help
  popover; the Reset Demo confirmation modal and its typed-confirmation gate; and the Assistant
  slide-over at narrow widths.
* **Tab widgets** — the three `role="tablist"` surfaces, against the WAI-ARIA APG pattern: one
  selected tab, roving tabindex, Arrow/Home/End, `aria-controls` → a rendered `tabpanel` that
  points back, and `?tab=` deep-link round-tripping.
* **Keyboard** — every keyboard-focused control paints a focus indicator (reached by pressing
  Tab, not `.focus()`, because only real keyboard focus engages `:focus-visible`); no focus
  trap; the skip link is the first tab stop and moves focus to `<main>`.
* **Disabled-control semantics** — disabled controls are named, out of the tab order, and the
  unavailable ones say *why* in prose rather than relying on a greyed-out button.
* **States** — loading (`role="status"`, `aria-live="polite"`), error (`role="alert"` with an
  actionable remedy and a Retry), not-found, refused (the upload boundary, asserted both in the
  UI and as a 403 at `POST /api/uploads`), and empty (the Assistant conversation on all five
  mounts; a no-match search).
* **Probe self-checks** — `e2e/specs/self-check.spec.ts` injects a known defect and asserts each
  probe reports it. A probe that returns `[]` because it is broken looks exactly like a probe
  that returns `[]` because the page is fine; these tests are what make a green run mean
  something. Covered: horizontal scroll, clipped text, occlusion, the focus-ring probe (including
  the realistic case of an element with a *resting* box-shadow that stops painting a ring, plus a
  positive control so the probe cannot pass by failing everything), and three checks on the axe
  baseline itself — a violation on a non-baselined surface, an extra node on a baselined one, and
  a changed failing colour at an unchanged count. **Not** self-checked, and listed in the spec
  header: heading-hierarchy and colour-only detection.

### Zoom-only (`@zoom`)

Emulation fidelity assertions (§4), a WCAG-1.4.10-style reflow sweep at 200% across all 18
surfaces, chrome operability, and a check that CSS text sizes are not clamped by the DPR change.

---

## 6. Findings

Every defect below is **pre-existing application behaviour**, found by this suite and *not*
fixed by it — fixing `apps/web/src/**` was out of scope for the baseline slice and would have
made the diff unreviewable.

Nothing is suppressed. No axe rule is disabled anywhere in the suite (`AxeBuilder.disableRules`
is never called). Instead each known defect is enumerated per rule, per surface, per viewport
**and per node count**, in:

* `apps/web/e2e/a11y-baseline.ts` — accessibility findings
* `apps/web/e2e/layout-baseline.ts` — responsive-layout findings

Anything the probes report that is **not** in those files fails the build — and so does a
recorded defect that **grows**. An earlier draft of this suite recorded `color-contrast` with a
wildcard scope, which silently made it equivalent to disabling the rule outright; that was caught
in review and is the reason the baseline is now count-based rather than rule-based. Each entry
carries an exact per-`surface@project` node count (total **1,974**), plus an identity guard —
`targetPattern` for structural rules, or the exact failing colour set for contrast — because an
unchanged count is not proof of an unchanged defect. Five verdicts can fail a run: `new`, `grew`,
`improved`, `new-target`, `new-foreground`. `improved` fails deliberately: when a defect is fixed
you must lower the number, so the baseline cannot quietly drift out of date.

Two known gaps, stated rather than hidden: `dialogs.spec.ts` still consults the baseline at
rule level (an open overlay legitimately changes counts, so page counts do not apply), and the
layout baseline enforces exact-selector membership rather than counts.

### Accessibility

| ID | Rule | Impact | Where | What is wrong |
|---|---|---|---|---|
| **A11Y-01** | `color-contrast` | serious | every surface, every viewport — **1,610 nodes** | **Not one palette decision — three distinct causes**, measured across 43 (foreground, background, size) combinations spanning **1.56:1 – 4.25:1** and **11** distinct rendered foregrounds. (1) `--text-disabled #c0c8d0`, which `tokens.css:34` intends for disabled chevrons, is rendered as *text* by `evidence.css:239` for preview line numbers at 11.5px → **1.56:1**, the worst in the app. (2) Genuinely low tokens: `#78838f`, `#9aa4af`, `#2f7d78` on the `#e6f1f0` chip tint. (3) **Five failures are `opacity` composites of tokens that pass at full strength** — e.g. `--text-muted #5b6570` is 5.93:1 but composites to `#777f89` under `queue.css:63 .exp-row.done { opacity: .82 }`; `--advisory-text #8a6420` was deliberately darkened for AA in P23C and still composites to `#9b793d`. **Darkening tokens will not fix group (3); the `opacity` has to go.** `#8e98a2`, named in an earlier draft of this table as a token, appears nowhere in `apps/web/src` — it is one of these composites. |
| **A11Y-02** | `button-name` | **critical** | every surface, at `mobile-375x812` and `zoom-200` | Below the 640px breakpoint `chrome.css:503` sets `.topbar-search-label, .topbar-search-kbd { display: none }`. The only remaining content of `<button class="topbar-search">` is an `aria-hidden` SVG and there is no `aria-label`, so **the global search trigger has no accessible name at all at phone widths and at 200% zoom**. |
| **A11Y-03** | `aria-allowed-attr` / `aria-allowed-role` | **critical** / minor | `evidence`, all viewports | The 31 Evidence Trail entries render as `<button role="listitem" aria-pressed="…">`. `role="listitem"` overrides the implicit button role, and `aria-pressed` is not allowed on `listitem` — so the selected/unselected state is not exposed at all. |
| **A11Y-04** | `scrollable-region-focusable` | serious | 3 pairs only: `evidence` at desktop and mobile, `settings-api` at mobile | `div.preview-lines.scroll-x` (source-file preview) and, at narrow widths, a code sample on API Access scroll horizontally but are not keyboard focusable. |
| **A11Y-05** | `page-has-heading-one` | moderate | `load` | `/load` renders no `<h1>`. Every other routed surface has one. |
| **A11Y-06** | `landmark-unique` | moderate | `settings-explorer` | Two `role="search"` landmarks with no distinguishing accessible name: the TopBar trigger (`SearchDialog.tsx:290`) and the endpoint filter (`settings/ApiDocs.tsx:333`). |

### Responsive layout

| ID | Where | What is wrong |
|---|---|---|
| **LAYOUT-01** | 8 measured `surface@project` pairs (not all 15 of the five record surfaces × three narrow projects — only 8 ever fire) | The record StatusBar footer does not reflow. At 375px its content measures **575px in a 353px box** with `overflow-x: visible`, so the phase / pending / advisory / coverage segments spill sideways and downwards and are then cut by `div.screen-card { overflow: hidden }`. Visually the segments overlap and read as garbled. Severity scales with width: severe at 375, ~11px of vertical clipping at 640 (200% zoom), ~1px at 768. Shared chrome, so it affects every record surface. |
| **LAYOUT-02** | `evidence` at `mobile-375x812` | The TopBar record-context status chip (`span.chip.chip-draft` in `div.record-context`) runs 9px past the right edge of `div.screen-card` and is cut by its `overflow: hidden` — the label reads "Draf". |

### Informational, not failing

`/record/:id/evidence` puts an `<h2>` ("Evidence Trail", inside the complementary landmark)
before the `<h1>` in DOM order. That is a defensible pattern for a landmark preceding `<main>`,
so it is recorded as a test annotation rather than asserted either way.

---

## 7. What this does NOT cover

Read this section before citing the suite as evidence of anything.

* **It never runs against the hosted `/krish` deployment, and it cannot.** That deployment sits
  behind an Authentik edge this environment cannot authenticate to. Everything here runs against
  the **Vite dev server** plus a local, database-free backend. A green run says nothing about a
  hosted rollout. Hosted QA remains a separate, Krish-gated step.
* **It tests the dev server, not the shipped bundle.** `playwright.config.ts` starts `npx vite`,
  not `vite preview`. Minification is therefore untested, and so is the configuration that
  actually ships — `VITE_BASE_PATH=/krish/` and `VITE_API_BASE=/krish/api` (`Dockerfile:22`).
  Everything here runs at base `/`.
* **The layout probes are load-sensitive.** Observed directly: running two Playwright suites
  concurrently produced one spurious `layout: Governance & Safety — Policy` failure at
  `tablet-768x1024` that passes in 1.5 s in isolation and does not recur on an idle machine
  (575 passed, 1 skipped, 0 failed, twice). Measuring rendered geometry under contention is
  inherently racy. Do not run the suite alongside another browser suite, and treat a single
  isolated layout failure as suspect until reproduced on a quiet machine. The same caveat already
  applies to the pre-existing `graph-real-artifact.test.tsx` vitest flake (finding **F1** in the
  Baseline Completion Matrix).
* **Font metrics are platform-dependent.** There is no webfont; `--font-ui` resolves to SF Pro on
  macOS and to a DejaVu/Liberation face on Linux CI. The clipping and horizontal-scroll probes
  measure text, so a baseline calibrated on one platform can legitimately differ on the other.
  CI is the authority.
* **It never touches a database.** No `PG*` variable is set anywhere; the backend runs with none.
* **It is read-only against the workspace during the run** — with one deliberate exception at
  setup: `global-setup.ts` POSTs `/demo/run` once to seed synthetic records (an idempotent
  upsert). After that no test creates, edits, exports, resets or deletes a record; the Reset Demo
  test opens the dialog and cancels without typing the confirmation phrase. That is what lets the
  five viewport projects run in parallel against one backend.
* **Set `ISAAC_UI_WORKSPACE` when running locally.** The default is the shared
  `/tmp/isaac-ui-workspace`, so records left by earlier manual use get swept into the scan and
  local results can diverge from CI for reasons that are hard to find. CI pins
  `/tmp/isaac-e2e-workspace`; do the same locally.
* **Chromium only.** No Firefox, no WebKit, no Safari, no real mobile browser.
* **No screen-reader testing.** axe checks the accessibility *tree*; it does not tell you what
  VoiceOver, NVDA or JAWS actually announce. Several of the findings above (A11Y-02, A11Y-03)
  are precisely the kind that a screen-reader pass would surface more vividly.
* **Automated contrast only.** axe measures computed foreground/background pairs. It cannot judge
  text over images or gradients, and it cannot tell you whether "red means bad" is comprehensible
  — the colour-only check here is explicitly best-effort (it verifies that status-like elements
  carry text or a name, nothing more).
* **No 400% zoom / 320px reflow**, no OS text scaling, no forced-colors / high-contrast mode, no
  `prefers-contrast`, no dark mode (the app declares light only).
* **No performance, no visual-regression pixel diffing.** Whole-page screenshot diffs were
  deliberately not used: on five viewports they fail on every legitimate copy change and tell a
  reviewer nothing about *why*. The probes name the offending element instead.
* **It does not replace the human visual sign-off gate.** An automated suite can prove the page
  does not scroll sideways and that no control is covered. It cannot tell you the layout is
  *good*.

---

## 8. CI

`.github/workflows/ci.yml` gains one **new, additive** job, `browser-a11y`. The existing `test`
(backend) and `frontend` jobs are untouched and this job neither gates nor depends on them.

It: installs the backend and the frontend, installs **Chromium only**
(`npx playwright install --with-deps chromium`), starts uvicorn with no database and no
credentials, waits for `/api/health` with the bounded loop pattern borrowed from
`pr-docker-smoke.yml`, asserts `mode == synthetic-only`, seeds via `POST /api/demo/run`,
typechecks `e2e/`, and runs the suite. The HTML report is uploaded as an artifact on every run.

CI uses port 5173 so that the backend's default CORS allow-list applies with no extra
configuration, `workers: 2`, and `retries: 1`.

---

## 9. Extending it

* **Add a surface** → one entry in `e2e/surfaces.ts`. Every `@responsive` spec picks it up
  automatically across all five dimensions. Give it a `ready` locator that proves its data has
  landed, or the sweep will race the loading panel and scan a skeleton.
* **Fix a finding** → delete its entry from `e2e/a11y-baseline.ts` or `e2e/layout-baseline.ts`
  in the same change. If you fix `/load`'s missing `<h1>`, also drop `expectH1: false` from its
  surfaces entry — that assertion exists so closing the finding is *forced*, not optional.
* **Add a probe** → add a matching case to `e2e/specs/self-check.spec.ts` proving it can fail.
  A probe with no self-check is not evidence.
* **Never** add `disableRules(...)`. Enumerate the defect instead.
