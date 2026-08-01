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
      '`src/components/chrome.css` (.statusbar), not here.',
    instances: {
      'record-detail@mobile-375x812': [SB_PHASE, SB_PENDING, SB_ADVISORY, SB_EYEBROW, SB_RIGHT],
      // PLATFORM-DIFFERING. On Linux the wider system face makes the pending
      // segment ("— dry-run · 1 error") overflow the 768px footer as well, so
      // the same non-reflowing footer clips a second segment there. Evidenced
      // by GitHub Actions run 30668917975, whose log excerpt named
      // `span.statusbar-pending` / `span.statusbar-seg` / `footer.statusbar`
      // and that text. The excerpt was TRUNCATED: SB_ADVISORY is carried over
      // from the macOS measurement (the footer geometry that clips it there is
      // if anything tighter under a wider font) and it is possible CI reports
      // further segments at this pair. If it does, the failure names them
      // exactly — add them here rather than widening the match. Nothing beyond
      // SB_PENDING is claimed as Linux-measured.
      'record-detail@tablet-768x1024': { darwin: [SB_ADVISORY], linux: [SB_ADVISORY, SB_PENDING] },
      'record-detail@zoom-200': [SB_PHASE, SB_PENDING, SB_ADVISORY],
      'guided-completion@mobile-375x812': [SB_PHASE, SB_NOTE],
      'evidence@mobile-375x812': [SB_NOTE],
      'export-readiness@mobile-375x812': [SB_PENDING, SB_ADVISORY, SB_EYEBROW, SB_RIGHT],
      'export-readiness-done@mobile-375x812': [SB_ADVISORY, SB_EYEBROW, SB_RIGHT],
      'export-readiness-done@zoom-200': [SB_ADVISORY],
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
      'Fix belongs in `src/components/chrome.css` (.record-context / .topbar) and fixes both.',
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
      'It is recorded rather than fixed because it falls outside the authorized defect list for ' +
      'that slice (C1, I1-I5); recording it with exact selectors keeps the ratchet honest ' +
      'instead of letting an annotation quietly absorb it. ' +
      'Fix belongs in `src/components/chrome.css` (.statusbar / the trigger\'s offset), not here.',
    instances: {
      'record-detail@laptop-1024x768': [SB_RIGHT],
      'guided-completion@laptop-1024x768': [SB_RIGHT],
      'evidence@laptop-1024x768': [SB_RIGHT],
      'export-readiness@laptop-1024x768': [SB_RIGHT],
      'export-readiness-done@laptop-1024x768': [SB_RIGHT],
      'record-detail@tablet-768x1024': [SB_RIGHT],
      'guided-completion@tablet-768x1024': [SB_RIGHT],
      'evidence@tablet-768x1024': [SB_RIGHT],
      'export-readiness@tablet-768x1024': [SB_RIGHT],
      'export-readiness-done@tablet-768x1024': [SB_RIGHT],
      'guided-completion@mobile-375x812': [SB_RIGHT],
      // Not SB_RIGHT here: at this pair the record's own status text is shorter,
      // so a different segment lands under the trigger. Recorded as measured.
      'export-readiness-done@mobile-375x812': [SB_EYEBROW],
      'guided-completion@zoom-200': [SB_RIGHT],
      'evidence@zoom-200': [SB_RIGHT],
      'export-readiness@zoom-200': [SB_RIGHT],
      'export-readiness-done@zoom-200': [SB_RIGHT],
      // The width sweep (`layout-widths.spec.ts`) keys by WIDTH rather than by
      // Playwright project, so its pairs are namespaced `@width-<n>`. Measured
      // on darwin; Linux may differ and CI is the authority.
      'export-readiness@width-1024': [SB_RIGHT],
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
    instances: {
      'evidence@width-320': [
        'div.screen-card < div.app < div#root',
        'section.preview < main#main.screen-main < div.screen-body.evidence',
      ],
      'evidence@width-375': ['section.preview < main#main.screen-main < div.screen-body.evidence'],
      'evidence@width-390': ['section.preview < main#main.screen-main < div.screen-body.evidence'],
      'record-detail@width-320': [
        'div.screen-card < div.app < div#root',
        'section.field-group < main#main.screen-main.pad < div.screen-body.record',
      ],
      'record-detail@width-375': ['div.screen-card < div.app < div#root'],
      'record-detail@width-390': ['div.screen-card < div.app < div#root'],
      'export-readiness@width-320': ['div.screen-card < div.app < div#root'],
      'export-readiness@width-375': ['div.screen-card < div.app < div#root'],
      'export-readiness@width-390': ['div.screen-card < div.app < div#root'],
      'export-readiness-done@width-320': [
        'div.screen-card < div.app < div#root',
        'main#main.screen-main.pad < div.screen-body.record < div.screen-card',
      ],
      'export-readiness-done@width-375': [
        'div.screen-card < div.app < div#root',
        'main#main.screen-main.pad < div.screen-body.record < div.screen-card',
      ],
      'export-readiness-done@width-390': ['div.screen-card < div.app < div#root'],
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
      'load@width-320': ['main#main.screen-main.centered < div.screen-body.full < div.screen-card'],
      'load@width-375': ['main#main.screen-main.centered < div.screen-body.full < div.screen-card'],
      'load@width-390': ['main#main.screen-main.centered < div.screen-body.full < div.screen-card'],
    },
  },
];

export const layoutKey = (surfaceId: string, projectId: string): string => `${surfaceId}@${projectId}`;

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
