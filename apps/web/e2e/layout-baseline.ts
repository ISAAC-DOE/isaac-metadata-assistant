/**
 * KNOWN, PRE-EXISTING RESPONSIVE-LAYOUT DEFECTS.
 *
 * Same contract as `a11y-baseline.ts`: an enumerated list of real bugs the
 * suite found in `apps/web/src/**`, not a way of switching a check off.
 * Anything the probes report that is NOT matched here fails the build.
 *
 * ── Matching is per INSTANCE, by exact selector ─────────────────────────────
 *
 * The first version matched with `selector.includes('statusbar')` scoped to a
 * cross-product of five surfaces and three projects. Two problems, both fixed:
 *
 *   * the substring swallowed anything whose selector merely MENTIONED
 *     `statusbar` — a genuinely new clipped descendant inside the footer would
 *     have been absorbed into the known finding and never reported;
 *   * the cross-product claimed 15 (surface, project) pairs. Measurement found
 *     the defect on 8. The other 7 were pre-authorised for free.
 *
 * `instances` below therefore lists, per `surfaceId@projectId`, the EXACT
 * offender selectors the probe produced. Anything else — a new selector, or the
 * same selector on a pair that is not listed — fails.
 *
 * A selector may be reported twice for one element (once for the horizontal
 * clip, once for the vertical); `helpers/layout.ts` de-duplicates on
 * selector + clip axis, so membership rather than a count is the right test.
 *
 * Fixing the CSS makes the matching entry stop firing;
 * `layout-responsive.spec.ts` annotates entries that no longer fire so they can
 * be deleted rather than left to rot.
 *
 * ── Some instance lists are PER PLATFORM ────────────────────────────────────
 *
 * Same cause as in `a11y-baseline.ts`, and it belongs here even more directly:
 * these probes measure rendered geometry. There is no webfont, so `--font-ui`
 * is SF Pro on macOS and a DejaVu/Liberation face on `ubuntu-latest`. Two
 * clips exist ONLY under the wider Linux face — they are real application
 * defects that macOS font metrics happened to hide, not test artifacts.
 *
 * An instance list may therefore be written as `{ darwin: [...], linux: [...] }`
 * and the CURRENT platform's list is the one enforced, exactly. A list is still
 * exhaustive for its platform: an offender not in it fails. `darwin: []` means
 * "measured on macOS, does not occur there" — it does not mean "unmeasured".
 *
 * **CI (Linux) is the authority.**
 */

import { currentPlatform, type BaselinePlatform } from './a11y-baseline';

/**
 * The exact offender selectors measured on a `surfaceId@projectId` pair —
 * identical on both platforms (a bare array) or measured separately because the
 * system font moves a wrap boundary.
 */
export type PlatformInstances =
  | readonly string[]
  | Readonly<Record<BaselinePlatform, readonly string[]>>;

/** Read one platform's offender list. */
export function platformInstances(
  instances: PlatformInstances | undefined,
  platform: BaselinePlatform
): readonly string[] {
  if (instances === undefined) return [];
  return Array.isArray(instances) ? instances : (instances as Record<BaselinePlatform, readonly string[]>)[platform];
}

export interface LayoutFinding {
  readonly id: string;
  /**
   * Which probe produced it.
   *
   * `'overflow'` was added when the probes were hardened (2026-08-01). It is
   * reported by `findOverflowingRegions`, which did not exist before: the old
   * `horizontalPageScroll` read ONLY `document.documentElement` and
   * `document.body`, so a region that scrolled sideways INSIDE the page was
   * invisible to the suite. That is not a hypothetical — at `/experiments`,
   * 375px, the document measured a clean 375 == 375 while `main.screen-main.pad`
   * measured scrollWidth 476 against clientWidth 353.
   */
  readonly kind: 'clipped' | 'obscured' | 'overflow';
  /**
   * Human-readable tag for this finding, used ONLY by the staleness annotation
   * in `layout-responsive.spec.ts` (which is outside this file's ownership and
   * reads `f.selector`). It is NOT what matching is based on — `instances` is.
   */
  readonly selector: string;
  /**
   * `surfaceId@projectId` → the exact offender selectors measured there, either
   * for both platforms (a bare array) or per platform.
   * Exhaustive: a pair that is absent tolerates nothing.
   */
  readonly instances: Readonly<Record<string, PlatformInstances>>;
  readonly note: string;
}

/**
 * An instance MEASURED AS FIXED on darwin, still tolerated on linux.
 *
 * `darwin: []` is a measurement, not an omission — see the platform note above.
 * The linux list is retained deliberately, following LAYOUT-02's precedent
 * verbatim: this environment cannot measure Linux, "expected" is not "measured",
 * and a stale entry only produces an annotation while deleting one that still
 * fires produces a red build. When CI annotates a linux instance as not-fired,
 * delete the whole entry then.
 *
 * The darwin side is not slack: `[]` tolerates nothing, so a regression on macOS
 * now FAILS where it used to be pre-authorised.
 *
 * THE FIRST ARGUMENT IS REQUIRED, and it was not always. This used to be
 * `(...linux: string[])`, which typechecked `fixedOnDarwin()` and yielded
 * `{darwin: [], linux: []}` — an entry tolerating nothing on either platform,
 * which is not "fixed on darwin" but a dead key that no reader would spot and
 * nothing rejected. A pair empty on BOTH platforms is also rejected at runtime by
 * `e2e/invariants/baseline-aggregate.invariant.test.ts`, which catches the
 * hand-written `{darwin: [], linux: []}` this signature cannot reach.
 */
const fixedOnDarwin = (first: string, ...rest: string[]): PlatformInstances => ({
  darwin: [],
  linux: [first, ...rest],
});

// The StatusBar offenders, named once so the table below stays readable.
const SB_PHASE = 'span.statusbar-phase < footer.statusbar < div.screen-card';
const SB_NOTE = 'span.statusbar-note < footer.statusbar < div.screen-card';
const SB_PENDING = 'span.statusbar-pending < span.statusbar-seg < footer.statusbar';
const SB_ADVISORY = 'span.statusbar-advisory < span.statusbar-seg < footer.statusbar';
const SB_EYEBROW = 'span.statusbar-eyebrow < span.statusbar-seg < footer.statusbar';
const SB_RIGHT = 'span.statusbar-right < span.statusbar-tail < footer.statusbar';

export const LAYOUT_BASELINE: readonly LayoutFinding[] = [
  {
    id: 'LAYOUT-01',
    kind: 'clipped',
    selector: 'statusbar',
    note:
      'The record StatusBar footer does not reflow. At 375px its content measures ' +
      '575px in a 353px box with `overflow-x: visible`, so the phase / pending / ' +
      'advisory / coverage segments spill sideways and downwards and are then cut ' +
      'by `div.screen-card { overflow: hidden }`. Visually the segments overlap and ' +
      'read as garbled ("dry-run · 1" over "not exported yet"). Severity scales with ' +
      'width: severe at 375, a single vertically-clipped segment at 640 (200% zoom) ' +
      'and at 768 on macOS — TWO at 768 on Linux, where the wider system font pushes ' +
      'the pending segment over as well — nothing at 1024 or 1280. It affects every record surface because ' +
      'StatusBar is shared chrome, but WHICH segments clip depends on the record\'s ' +
      'own status text, so the lists below differ per surface. Fix belongs in ' +
      '`src/components/chrome.css` (.statusbar), not here. ' +
      'FIXED 2026-08-29 in `src/components/chrome.css` — exactly where this note said the fix ' +
      'belonged. Inside the existing `@media (max-width: 1024px)` block the footer becomes ' +
      '`min-height: 52px` + `flex-wrap: wrap` instead of a hard `height: 52px` single-line row, ' +
      'so the segments REFLOW onto further rows rather than spilling sideways out of the card. ' +
      'Nothing is hidden and nothing truncates: every segment of this footer is a trust signal ' +
      '(phase / Validation / Coverage / Advisory / the runtime honesty statement), so hiding or ' +
      'ellipsising one at a narrow width would make the readout say LESS on the screens where a ' +
      'reader can see least. All 20 recorded darwin offenders stopped firing in one run; see the ' +
      'per-instance note below for why the linux lists are kept.',
    /*
     * ── FIXED ON DARWIN, 2026-08-29 — ALL TWENTY OFFENDERS ──────────────────
     *
     * MEASURED, local macOS run at this branch's HEAD:
     * `npx playwright test e2e/specs/layout-responsive.spec.ts --reporter=json`,
     * reading the `layout-baseline-not-fired` annotations. Every one of the 20
     * darwin offenders across all eight keys was reported as not fired, and NO new
     * clipped or occluded finding appeared anywhere in that run. That is what a
     * shared-cause fix looks like: one declaration block, eight keys, twenty
     * offenders, one run.
     *
     * IT ALSO CLOSED FOUR LAYOUT-04 KEYS, which is the corroboration rather than a
     * coincidence: LAYOUT-04's cause (a) is stated as "`div.screen-card` inherits
     * the non-reflowing StatusBar's width", and `div.screen-card` stopped
     * overflowing at 320, 375 and 390 on every record surface in the same run.
     *
     * WHY THE LINUX LISTS SURVIVE, and this is a real reservation rather than the
     * usual conservatism. `flex-wrap: wrap` absorbs any amount of extra WIDTH by
     * adding rows, so the shared cause is closed structurally — but a wrap boundary
     * falls BETWEEN flex items, and a single `.statusbar-seg` is itself a nowrap
     * flex row. A segment whose own content exceeded the whole 353px line under a
     * wider system face would still overflow, and this environment cannot measure
     * the Linux face. `darwin: []` tolerates nothing, so a macOS regression now
     * FAILS where it used to be pre-authorised; when CI annotates a linux instance
     * as not-fired, delete the whole entry then.
     */
    instances: {
      'record-detail@mobile-375x812': fixedOnDarwin(SB_PHASE, SB_PENDING, SB_ADVISORY, SB_EYEBROW, SB_RIGHT),
      // ~~PLATFORM-DIFFERING.~~ Now `fixedOnDarwin`, like every other key here —
      // but the linux list is UNCHANGED and the reason it holds two selectors
      // rather than one is kept, because it is what CI will be judged against.
      // On Linux the wider system face makes the pending segment ("— dry-run · 1
      // error") overflow the 768px footer as well, so the same non-reflowing
      // footer clipped a second segment there. Evidenced by GitHub Actions run
      // 30668917975, whose log excerpt named `span.statusbar-pending` /
      // `span.statusbar-seg` / `footer.statusbar` and that text. The excerpt was
      // TRUNCATED: SB_ADVISORY is carried over from the macOS measurement (the
      // footer geometry that clipped it there was if anything tighter under a
      // wider font) and it is possible CI reports further segments at this pair.
      // If it does, the failure names them exactly — add them here rather than
      // widening the match. Nothing beyond SB_PENDING is claimed as
      // Linux-measured, and nothing here is claimed as still firing on Linux;
      // the list is what the fix has yet to be measured AGAINST.
      'record-detail@tablet-768x1024': fixedOnDarwin(SB_ADVISORY, SB_PENDING),
      'record-detail@zoom-200': fixedOnDarwin(SB_PHASE, SB_PENDING, SB_ADVISORY),
      'guided-completion@mobile-375x812': fixedOnDarwin(SB_PHASE, SB_NOTE),
      'evidence@mobile-375x812': fixedOnDarwin(SB_NOTE),
      'export-readiness@mobile-375x812': fixedOnDarwin(SB_PENDING, SB_ADVISORY, SB_EYEBROW, SB_RIGHT),
      'export-readiness-done@mobile-375x812': fixedOnDarwin(SB_ADVISORY, SB_EYEBROW, SB_RIGHT),
      'export-readiness-done@zoom-200': fixedOnDarwin(SB_ADVISORY),
    },
  },
  {
    id: 'LAYOUT-02',
    kind: 'clipped',
    selector: 'record-context',
    note:
      'At 375px the TopBar record-context status chip inside `div.record-context` runs past ' +
      'the right edge of `div.screen-card` and is cut by its `overflow: hidden`. On Evidence ' +
      'it is `span.chip.chip-draft`, 9px over, and the label reads "Draf". ' +
      'SECOND INSTANCE, Linux only: on Export Readiness (done) the `span.chip.chip-exported` ' +
      'chip runs from 315 to 372 in a container that ends at 365 — 7px over — and the label ' +
      '"Exported" is cut. That instance is the SAME APPLICATION DEFECT, not a test artifact: ' +
      'macOS font metrics merely happen to fit the chip inside the card by a couple of pixels, ' +
      'and the wider Linux system face does not. It would be visible to any user whose system ' +
      'font is a shade wider, and it is genuinely broken on CI. The underlying cause ' +
      '(record-context does not shrink at phone widths) is shared by both. ' +
      'Fix belongs in `src/components/chrome.css` (.record-context / .topbar) and fixes both. ' +
      'THE ONE REMAINING INSTANCE IS LINUX-ONLY AND THIS ENTRY HOLDS EXACTLY ONE KEY — ' +
      'do not read the "On Evidence it is `span.chip.chip-draft`" sentence above as a live ' +
      'instance; that macOS instance was DELETED on 2026-08-01 and the sentence survives only ' +
      'because it is what the Linux one is being compared to. ' +
      '2026-08-29: `src/components/chrome.css` now states the crumb\'s shrink contract instead ' +
      'of leaving it to the flexbox initial values — the state chip is `flex: none; ' +
      'max-width: 100%` (the word IS the state, so it must neither shrink nor ellipsise) and ' +
      '`.record-surface` is `flex: 0 1 auto` (it already truncates and keeps a readable ' +
      'fragment, so it is the item that yields). That makes the containment structural rather ' +
      'than a consequence of how wide the system face happens to be. IT IS NOT CLAIMED AS A ' +
      'MEASURED FIX: darwin already read `[]` here before the change, so no local run can ' +
      'distinguish it from the 2026-08-01 fix, and only CI can retire the linux instance.',
    instances: {
      // The macOS instance (`span < span.chip.chip-draft < div.record-context`
      // at `evidence@mobile-375x812`, label reading "Draf") is DELETED as of
      // 2026-08-01: the C1/I4 fix gave `.record-context` `overflow: hidden` at
      // every width and moved the compact top-bar treatment into the ≤1024
      // band, so the chip no longer runs past `div.screen-card`. Confirmed by
      // this suite's own staleness signal — `layout-baseline-not-fired` named
      // `evidence @ mobile-375x812: LAYOUT-02` — and by direct measurement.
      //
      // The Linux instance is KEPT, deliberately and conservatively. The fix
      // addresses its stated shared cause, so it is EXPECTED to stop firing on
      // CI too, but this environment cannot measure Linux font metrics and
      // "expected" is not "measured". A stale entry only produces an
      // annotation; deleting one that still fires produces a red build. If CI
      // annotates it as not-fired, delete it then.
      //
      // Evidenced by GitHub Actions run 30668917975: el 315..372 vs container
      // 10..365, clipped horizontally by `div.screen-card < div.app < div#root`,
      // text "Exported". `darwin: []` is a measurement: it does not clip on macOS.
      'export-readiness-done@mobile-375x812': {
        darwin: [],
        linux: ['span < span.chip.chip-exported < div.record-context'],
      },
    },
  },
  {
    id: 'LAYOUT-03',
    kind: 'obscured',
    selector: 'statusbar-right',
    note:
      'The floating Assistant trigger (`button.assistant-drawer-trigger`: `position: fixed`, ' +
      '`z-index: 45`, `bottom: 16px`, engaged by `@media (max-width: 1024px)`) is painted ' +
      'directly over the right-hand end of the record StatusBar. The covered text is the ' +
      'honesty statement "hosted preview · no telemetry" (rendered "local dev · no telemetry" ' +
      'against a dev server). CORRECTED 2026-08-01: an earlier revision of this note called the ' +
      'coverage "TOTAL, not partial", citing a visible-area ratio of 1.00. That inference was ' +
      'wrong. `ratio` is `visibleRect(el) / getBoundingClientRect()` and `visibleRect` intersects ' +
      'ONLY with clipping/scrolling ancestors and the viewport (helpers/layout.ts:821-843) — it ' +
      'has no knowledge of overlays, so 1.00 means "fully laid out and unclipped", NOT ' +
      '"fully occluded". The occlusion measure is the 5-point hit test, and its own figure is ' +
      '3 TO 5 of 5 — a 3-of-5 instance is partial. Coverage is partial-to-total by surface, and ' +
      'the reliably-lost part is the TRAILING half, which carries the telemetry claim. ' +
      'It survives `scrollIntoView`, so it is ' +
      'not "scrolled away" — it is unreachable at any scroll offset. ' +
      'PRE-EXISTING and NOT introduced by the 2026-08-01 remediation: it is a consequence of the ' +
      'fixed trigger and the non-reflowing footer (LAYOUT-01), both of which predate it. It was ' +
      'invisible until this slice, because the old `findObscuredControls` only ever examined ' +
      'INTERACTIVE elements — a `<span>` label was outside the probe\'s universe entirely. ' +
      'It WAS recorded rather than fixed because it fell outside the authorized defect list for ' +
      'that slice (C1, I1-I5); recording it with exact selectors kept the ratchet honest ' +
      'instead of letting an annotation quietly absorb it. ' +
      'FIXED 2026-08-25 in `src/components/chrome.css` — exactly where this note said the fix ' +
      'belonged — as `--assistant-trigger-reserve`: 64px of space AFTER `div.screen-card`, with the ' +
      'same amount taken back out of the card\'s `min-height` so a short page gains no scrollbar. ' +
      'The reserve, and not a change to the trigger, is the fix because the footer is `position: ' +
      'static` and the LAST child of the card while the DOCUMENT is the scroller at these widths: ' +
      'the coverage "survived scrollIntoView" only because there was nothing below the footer to ' +
      'scroll INTO. All 17 recorded instances stopped firing on darwin in one run; see the ' +
      'per-instance note below for why the linux lists are kept.',
    /*
     * ── FIXED ON DARWIN, 2026-08-25 — ALL SEVENTEEN INSTANCES ────────────────
     *
     * `components/chrome.css`'s `@media (max-width: 1024px)` block now reserves
     * `--assistant-trigger-reserve` (64px) after `div.screen-card` and gives the
     * same amount back out of the card's `min-height`, so the status bar can be
     * scrolled clear of the trigger. That closes the mechanism this entry
     * describes rather than moving it: the note above says the coverage
     * "survives `scrollIntoView`", and the reason it did was simply that there
     * was nothing below the footer to scroll INTO.
     *
     * MEASURED: `specs/layout-responsive.spec.ts` ran green across all five
     * projects and reported 16 of these instances as not-fired, and
     * `specs/layout-widths.spec.ts` reported the seventeenth
     * (`export-readiness@width-1024`). So every recorded instance stopped firing
     * on darwin in one run, which is what a shared-cause fix looks like.
     *
     * WHY THE LINUX LISTS SURVIVE. Same reasoning as LAYOUT-02, and it is a
     * deliberate conservatism rather than a doubt about the fix: this
     * environment cannot measure Linux font metrics, and while the reserve is
     * STRUCTURAL (64px of document space, which no glyph width can consume) the
     * status bar's own content is not — LAYOUT-01 records that the footer's
     * segments already clip differently under the wider Linux face. If CI
     * annotates these as not-fired, delete the entries then.
     *
     * The `@width-1024` key is the width sweep's namespace: that file keys by
     * WIDTH inside one project rather than by Playwright project.
     */
    instances: {
      'record-detail@laptop-1024x768': fixedOnDarwin(SB_RIGHT),
      'guided-completion@laptop-1024x768': fixedOnDarwin(SB_RIGHT),
      'evidence@laptop-1024x768': fixedOnDarwin(SB_RIGHT),
      'export-readiness@laptop-1024x768': fixedOnDarwin(SB_RIGHT),
      'export-readiness-done@laptop-1024x768': fixedOnDarwin(SB_RIGHT),
      'record-detail@tablet-768x1024': fixedOnDarwin(SB_RIGHT),
      'guided-completion@tablet-768x1024': fixedOnDarwin(SB_RIGHT),
      'evidence@tablet-768x1024': fixedOnDarwin(SB_RIGHT),
      'export-readiness@tablet-768x1024': fixedOnDarwin(SB_RIGHT),
      'export-readiness-done@tablet-768x1024': fixedOnDarwin(SB_RIGHT),
      'guided-completion@mobile-375x812': fixedOnDarwin(SB_RIGHT),
      // Not SB_RIGHT here: at this pair the record's own status text is shorter,
      // so a different segment lands under the trigger. Recorded as measured.
      'export-readiness-done@mobile-375x812': fixedOnDarwin(SB_EYEBROW),
      'guided-completion@zoom-200': fixedOnDarwin(SB_RIGHT),
      'evidence@zoom-200': fixedOnDarwin(SB_RIGHT),
      'export-readiness@zoom-200': fixedOnDarwin(SB_RIGHT),
      'export-readiness-done@zoom-200': fixedOnDarwin(SB_RIGHT),
      'export-readiness@width-1024': fixedOnDarwin(SB_RIGHT),
    },
  },
  {
    id: 'LAYOUT-04',
    kind: 'overflow',
    selector: 'nested-horizontal-overflow',
    note:
      'NESTED horizontal overflow: regions that scroll or clip sideways INSIDE the page while ' +
      'the document itself measures clean. Every instance below is PRE-EXISTING application ' +
      'debt that no test could previously report, because the old probe only asked whether ' +
      '`document.documentElement` / `document.body` overflowed. ' +
      'Two distinct causes, deliberately recorded under one id because they share that history: ' +
      '(a) `div.screen-card` inherits the non-reflowing StatusBar\'s width (LAYOUT-01: 575px of ' +
      'content in a 353px box), so the shell overflows on record surfaces; (b) several `main` ' +
      'regions and `section.preview` / `section.field-group` hold content whose min-content width ' +
      'exceeds a phone viewport. ' +
      'NOT the `/experiments` case that motivated the hardening — that one (`main.screen-main.pad`, ' +
      'scrollWidth 476 vs clientWidth 353) was FIXED in the same slice by the I1 change and is ' +
      'deliberately absent here; if it ever returns, it fails. ' +
      'These are recorded, not fixed, because they fall outside the slice\'s authorized defect ' +
      'list. Measured on darwin at the width sweep\'s own widths. **Linux is the authority and is ' +
      'NOT yet measured** — the system font is wider there, so CI may report further instances; ' +
      'when it does, add them exactly as named rather than widening the match.',
    /*
     * ── CAUSE (a) FIXED ON DARWIN, 2026-08-29 — TEN OFFENDERS ACROSS NINE KEYS ──
     *
     * This entry's own note names cause (a) as "`div.screen-card` inherits the
     * non-reflowing StatusBar's width (LAYOUT-01: 575px of content in a 353px
     * box)". LAYOUT-01 is now fixed at the source, and cause (a) went with it:
     * `div.screen-card < div.app < div#root` stopped overflowing at 320, 375 and
     * 390 on all four record surfaces in the same run, and
     * `section.field-group < main#main.screen-main.pad < …` at
     * `record-detail@width-320` went with them — the card is a column flex
     * container, so the footer's 575px min-content had been widening `main` and
     * everything inside it.
     *
     * MEASURED: `npx playwright test e2e/specs/layout-widths.spec.ts
     * --reporter=json`, local macOS, this branch's HEAD, reading the
     * `layout-baseline-not-fired` annotations at widths 320, 375 and 390. Known
     * overflow at those widths fell 320: 7 -> 3, 375: 5 -> 2, 390: 4 -> 1.
     *
     * CAUSE (b) IS UNTOUCHED AND STILL FIRES on darwin — `section.preview`
     * (evidence), `main#main.screen-main.pad` (export-readiness-done) and
     * `main#main.screen-main.centered` (guided-completion) are content whose
     * min-content width exceeds a phone viewport, which the footer never caused
     * and this change does not address.
     *
     * The linux lists are kept for the reason `fixedOnDarwin` documents and the
     * one LAYOUT-01 states in full: wrapping absorbs width between flex ITEMS,
     * and a single `.statusbar-seg` is itself a nowrap row that a wider face
     * could still overrun.
     */
    instances: {
      'evidence@width-320': {
        darwin: ['section.preview < main#main.screen-main < div.screen-body.evidence'],
        linux: [
          'div.screen-card < div.app < div#root',
          'section.preview < main#main.screen-main < div.screen-body.evidence',
        ],
      },
      'evidence@width-375': ['section.preview < main#main.screen-main < div.screen-body.evidence'],
      'evidence@width-390': ['section.preview < main#main.screen-main < div.screen-body.evidence'],
      'record-detail@width-320': fixedOnDarwin(
        'div.screen-card < div.app < div#root',
        'section.field-group < main#main.screen-main.pad < div.screen-body.record'
      ),
      'record-detail@width-375': fixedOnDarwin('div.screen-card < div.app < div#root'),
      'record-detail@width-390': fixedOnDarwin('div.screen-card < div.app < div#root'),
      'export-readiness@width-320': fixedOnDarwin('div.screen-card < div.app < div#root'),
      'export-readiness@width-375': fixedOnDarwin('div.screen-card < div.app < div#root'),
      'export-readiness@width-390': fixedOnDarwin('div.screen-card < div.app < div#root'),
      'export-readiness-done@width-320': {
        darwin: ['main#main.screen-main.pad < div.screen-body.record < div.screen-card'],
        linux: [
          'div.screen-card < div.app < div#root',
          'main#main.screen-main.pad < div.screen-body.record < div.screen-card',
        ],
      },
      'export-readiness-done@width-375': {
        darwin: ['main#main.screen-main.pad < div.screen-body.record < div.screen-card'],
        linux: [
          'div.screen-card < div.app < div#root',
          'main#main.screen-main.pad < div.screen-body.record < div.screen-card',
        ],
      },
      'export-readiness-done@width-390': fixedOnDarwin('div.screen-card < div.app < div#root'),
      'guided-completion@width-320': [
        'main#main.screen-main.centered < div.screen-body.record < div.screen-card',
      ],
      // PLATFORM-DIFFERING, and Linux is the one that is worse. MEASURED by CI
      // run 30691557697 on `7e9a387`: the same region overflows at 375 as well
      // under the wider Linux system face — scrollWidth 356 vs clientWidth 353,
      // with `span.upcoming-path < div.upcoming-row < div.centered-col.narrow`
      // as the widest overflowing child (right edge 367 vs 364). Three pixels,
      // and therefore exactly the kind of thing macOS font metrics hide: it is a
      // real application defect that any user with a slightly wider face sees.
      // `darwin: []` is a measurement, not an omission — it does not fire there.
      'guided-completion@width-375': {
        darwin: [],
        linux: ['main#main.screen-main.centered < div.screen-body.record < div.screen-card'],
      },
      /*
       * FIXED ON DARWIN, 2026-08-25. `components/runner.css` gave `.onramps`
       * `repeat(auto-fit, minmax(240px, 1fr))` in place of a hard `1fr 1fr` that
       * this file had no `@media` rule to soften, so Load Materials reflows to
       * one column below ~494px of container instead of holding 468px of cards
       * in a 242px box. That grid was the whole of this region's overflow: the
       * widest overflowing child measured `div.onramp` with a right edge of 507
       * against main's scrollWidth of 496. The same geometry was also the source
       * of an `[unusable-sliver]` occlusion finding on `button.drop-target`
       * (15px of 194px), which stopped firing in the same run.
       *
       * ~~"Unlike LAYOUT-02's font-metric instances, this one is STRUCTURAL — a
       * single `1fr` track cannot overflow its own container under any font — so the
       * linux lists are kept only for the reason the helper documents, not because the
       * mechanism is in doubt."~~ **WRONG ON BOTH HALVES, CORRECTED IN PLACE
       * 2026-08-25.** Keeping the linux lists is the right decision; the stated reason
       * was an invitation to delete them.
       *
       * FIRST: the track is not `1fr`, it is `minmax(240px, 1fr)`, and MINMAX HAS A
       * FLOOR THAT OVERFLOWS. Measured in headless Chromium on `/load`, as `.onramps`
       * scrollWidth/clientWidth:
       *
       *     viewport 320 -> 242/242   (clean)
       *     viewport 317 -> 240/239   (+1)
       *     viewport 310 -> 240/232   (+8)
       *
       * 320 is simply the narrowest width this sweep measures; it is not a width below
       * which the geometry is safe.
       *
       * SECOND, and this is why the linux lists are LOAD-BEARING EVIDENCE rather than
       * conservatism: at 320 the binding constraint is FONT-DEPENDENT. `.onramp-head`
       * is a no-wrap flex row, and its title/tagline stack had no `min-width: 0`, so
       * the row's width was floored by that stack's min-content. Scaling the on-ramp
       * fonts as a proxy for the wider Linux face reopened this very key: grid 245/242
       * (+3) at 1.3x, 265/242 (+23) at 1.5x, 318/242 (+76) at 2.0x. A wider system
       * face is exactly the input that can make `load@width-*` fire again, and the
       * linux lists are the only thing that would tolerate it while CI told us so.
       *
       * `components/runner.css` now declares `.onramp-head > div { min-width: 0 }`,
       * which returns every one of those scales to 242/242 — measured. That closes the
       * font-dependent half. The minmax FLOOR below ~318px is unclosed and lies outside
       * this sweep's widths.
       *
       * ONE FIGURE FROM THE REVIEW THAT DID NOT REPRODUCE, recorded rather than
       * repeated: it reported 21px of grid overflow at a 1.10x font scale. This
       * environment measures ZERO at 1.10x; the first overflow appears at 1.3x. The
       * mechanism is real; the threshold quoted is not what darwin measures.
       */
      'load@width-320': fixedOnDarwin('main#main.screen-main.centered < div.screen-body.full < div.screen-card'),
      'load@width-375': fixedOnDarwin('main#main.screen-main.centered < div.screen-body.full < div.screen-card'),
      'load@width-390': fixedOnDarwin('main#main.screen-main.centered < div.screen-body.full < div.screen-card'),
    },
  },
];

export const layoutKey = (surfaceId: string, projectId: string): string => `${surfaceId}@${projectId}`;

/**
 * THE WIDTH SWEEP'S GRID, moved here from `specs/layout-widths.spec.ts`.
 *
 * Two grids write keys into `LAYOUT_BASELINE`, and they are not the same grid:
 * `specs/layout-responsive.spec.ts` keys by Playwright PROJECT
 * (`surfaceId@desktop-1280x800`), while `specs/layout-widths.spec.ts` moves the
 * viewport itself inside one project and keys by WIDTH
 * (`surfaceId@width-1024`). The namespacing is deliberate and is documented at
 * the sweep — both measure 1280, 1024, 768 and 640, and a shared key would let
 * a defect recorded for one measurement silently excuse the other.
 *
 * It lives HERE rather than in the spec because the spec cannot be imported by
 * anything that is not a Playwright run, and the fast invariant suite
 * (`invariants/baseline-aggregate.invariant.test.ts`) needs to know which
 * project halves are legal in order to reject a typo'd key in milliseconds
 * instead of after a ~30-minute browser job. A grid that only one runner can
 * see is a grid nothing cheap can check against.
 *
 * The spec imports these two declarations; it does not keep a second copy.
 */
export const LAYOUT_SWEEP_WIDTHS = [1280, 1024, 768, 640, 390, 375, 320] as const;

/** `320` → `'width-320'`. The "project" component of a width-sweep key. */
export const layoutWidthId = (width: number): string => `width-${width}`;

/** Every width-sweep pseudo-project id, in sweep order. */
export const LAYOUT_SWEEP_WIDTH_IDS: readonly string[] = LAYOUT_SWEEP_WIDTHS.map(layoutWidthId);

/**
 * True only for an EXACT recorded offender on an EXACT recorded
 * (surface, project) pair, ON THIS PLATFORM. No substrings, no wildcards, and
 * no cross-platform borrowing: a clip recorded only for Linux does not excuse
 * the same selector appearing on macOS.
 */
export function isKnownLayoutFinding(
  kind: LayoutFinding['kind'],
  selector: string,
  surfaceId: string,
  projectId: string,
  platform: BaselinePlatform = currentPlatform()
): boolean {
  const key = layoutKey(surfaceId, projectId);
  return LAYOUT_BASELINE.some(
    (f) => f.kind === kind && platformInstances(f.instances[key], platform).includes(selector)
  );
}

export function applicableLayoutFindings(
  surfaceId: string,
  projectId: string,
  platform: BaselinePlatform = currentPlatform()
): readonly LayoutFinding[] {
  const key = layoutKey(surfaceId, projectId);
  return LAYOUT_BASELINE.filter((f) => platformInstances(f.instances[key], platform).length > 0);
}

/**
 * Every offender this baseline tolerates, summed PER PLATFORM — the recorded
 * layout debt. Computed for both columns without resolving the current
 * platform, so an unmeasured platform fails at the first lookup with
 * `resolvePlatform`'s message rather than at module load with a stack trace.
 */
export const LAYOUT_BASELINE_TOTAL_INSTANCES: Readonly<Record<BaselinePlatform, number>> = {
  darwin: totalInstancesOn('darwin'),
  linux: totalInstancesOn('linux'),
};

function totalInstancesOn(platform: BaselinePlatform): number {
  return LAYOUT_BASELINE.reduce(
    (n, f) => n + Object.values(f.instances).reduce((m, list) => m + platformInstances(list, platform).length, 0),
    0
  );
}
