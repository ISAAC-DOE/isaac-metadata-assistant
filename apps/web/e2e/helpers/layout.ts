/**
 * Layout probes that run *in the page*, against real rendered geometry.
 *
 * Deliberately NOT pixel snapshots. A whole-page screenshot diff on five
 * viewports would fail on every legitimate copy change and would tell a
 * reviewer nothing about *why*. These probes answer specific questions and
 * name the offending element when they fail.
 *
 * Tolerances are 1 CSS px throughout — sub-pixel rounding at
 * `deviceScaleFactor: 2` (the zoom project) otherwise produces false positives.
 *
 * ── THREE BLIND SPOTS THAT WERE CLOSED (2026-07-31) ─────────────────────────
 *
 * Each of these let a MEASURED defect in the `ceea656` build pass the whole
 * suite. The numbers below are real measurements, not illustrations.
 *
 *   1. NESTED horizontal overflow. `horizontalPageScroll` reads only
 *      `document.documentElement` and `document.body`. At `/experiments`,
 *      375x812, the document reported 375 == 375 (clean) while
 *      `main.screen-main.pad` measured scrollWidth 476 vs clientWidth 353. The
 *      page did not scroll; the MAIN CONTENT REGION did, and nothing looked.
 *      → `findOverflowingRegions` (below).
 *
 *   2. TOTAL text loss disguised as truncation. `findClippedText` skipped
 *      zero-width elements outright AND exempted anything with
 *      `text-overflow: ellipsis`, regardless of magnitude. The top-bar
 *      `span.record-title` measured clientWidth 0 / scrollWidth 250 —
 *      100% of the record's identity gone, with not even an ellipsis glyph
 *      painted — and was DOUBLE exempt.
 *      → the `total-loss` / `critical-loss` tier (below).
 *
 *   3. OCCLUSION the probe could not see. `findObscuredControls` scanned only
 *      interactive elements, so `span.record-surface` — which genuinely paints
 *      over the search button and the mode chip at 375px — was outside its
 *      universe entirely. And it hit-tested the centre of the VISIBLE
 *      INTERSECTION, so the New Record button, with 4.9px of its 128px visible,
 *      hit-tested to itself and passed.
 *      → a focused critical-label set, a usable-width test, and multi-point
 *        hit-testing over the INTENDED box (below).
 */

import type { Page } from '@playwright/test';
import { HIDDEN_TEXT_ALLOWANCES } from '../layout-allowlist';

const TOL = 1;

/**
 * Minimum visible inline width at which an element can still show a meaningful
 * fragment of its text.
 *
 * Derivation, so this is a measurement and not a taste: the app's UI text runs
 * 10.5–13px (`--font-ui`, no webfont), and average glyph advance for that
 * family is close to 0.5em, i.e. ~5.5–6.5 CSS px. 24px is therefore ~4 glyphs —
 * the least that can carry a word stem plus the ellipsis glyph. Below it, an
 * `text-overflow: ellipsis` box paints at most "…" and often nothing at all,
 * which is total content loss wearing truncation's clothes. 24 CSS px is also
 * the WCAG 2.5.8 (Target Size, Minimum) floor, so the number is anchored to a
 * published threshold rather than picked.
 */
const MIN_MEANINGFUL_TEXT_PX = 24;

/**
 * Minimum visible inline width for a CRITICAL label — a page `<h1>` or a record
 * title. Identity labels have to do more than prove text exists: they have to
 * let the user tell THIS record from the one they were looking at before.
 *
 * Derivation: an average English word is ~5 characters (~32px at 13px) and the
 * ellipsis glyph is ~5–8px, so ~40px is the least that can show one whole short
 * word followed by "…". Set deliberately at that floor and no higher: the goal
 * is to flag catastrophic loss (0px of 250px), not to police tight-but-legible
 * truncation, which is a design decision and not a defect.
 */
const CRITICAL_MIN_TEXT_PX = 40;

/**
 * The content-loss tier has TWO arms. An element fires if EITHER holds (and in
 * both cases only once more than `MIN_LOST_PX` is actually missing).
 *
 * ── Arm A, the absolute floor ───────────────────────────────────────────────
 *
 * `visible < MIN_MEANINGFUL_TEXT_PX` (or `CRITICAL_MIN_TEXT_PX`), NARROWED by
 * `visible / scrollWidth < MAX_VISIBLE_FRACTION_FOR_LOSS`. The narrowing exists
 * because the absolute test alone was measured to be wrong: it reported 300+
 * elements showing 100% of a short string — a count badge reading "2" is 7px
 * wide and is not truncated, it is just small. It also disposes of a
 * measurement artefact honestly: SVG `<text>` in the graph canvas reports
 * `scrollWidth` a few px above its client rect (20 vs 25), which at 80% visible
 * is plainly not content loss, and the ratio says so without a special case
 * for SVG.
 *
 * ── Arm B, severe fractional loss ───────────────────────────────────────────
 *
 * Arm A alone has a hole, and the previous version of this comment papered over
 * it by describing the ratio as what "restricts the tier to elements that
 * genuinely cannot show what they hold". It did not: ANDed with an absolute
 * floor, the ratio can only ever NARROW. A label painting 25px of 400px — 6%
 * visible, five sixths of it destroyed — escaped, because 25 >= 24. Worse, it
 * then also escaped the `clipped-x` tier, because `meaningfullyVisible` below
 * uses the same absolute floor to decide that ellipsis is excusable. Two tiers,
 * one blind spot.
 *
 * Arm B closes it: `visible / scrollWidth < SEVERE_LOSS_FRACTION` fires
 * regardless of absolute width.
 *
 * 0.2 is not a new standard, it is the same one expressed as a fraction. At 20%
 * visible a 400px string paints ~25px — about four glyphs plus an ellipsis,
 * which is exactly the amount Arm A's 24px floor already judges insufficient.
 * An element wide enough to clear the floor but no more readable should not get
 * a different answer.
 *
 * Arm B is deliberately restricted to elements that CLIP THEIR OWN CONTENT
 * (computed `overflow-x: hidden | clip`), and that restriction is load-bearing
 * rather than cautious:
 *
 *   * `overflow-x: auto | scroll` means the content is REACHABLE BY SCROLLING.
 *     Without this, an `.api-samples-code` block showing 227px of a 2000px curl
 *     line — 11% — would be reported as lost text, when scrolling reveals all
 *     of it. That would be a false positive on an intentionally allowlisted
 *     region, i.e. exactly the kind of noise that gets a probe weakened.
 *   * `overflow-x: visible` means the text SPILLS and is still painted; whether
 *     an ancestor then destroys it is the `clipped-x` walk's question, and that
 *     walk answers it with the ancestor named.
 *
 * So Arm B fires only where overflow is genuinely destroyed — which is also
 * precisely where `text-overflow: ellipsis` applies.
 */
const MAX_VISIBLE_FRACTION_FOR_LOSS = 0.6;

/** See Arm B above. Fires regardless of absolute width, on self-clipping elements only. */
const SEVERE_LOSS_FRACTION = 0.2;

/** Below this many px of lost content, the difference is layout rounding, not truncation. */
const MIN_LOST_PX = 2;

/**
 * Minimum visible width at which an interactive control is still usable.
 * WCAG 2.5.8 (Target Size, Minimum, AA in WCAG 2.2) is 24x24 CSS px. A control
 * narrower than that IN TOTAL is not automatically a defect (an 18px icon
 * button is a design choice), so the test is relative: at least
 * `min(intendedWidth, 24)` px of it must actually be visible. A 128px button
 * showing 4.9px fails; an 18px button showing all 18px passes.
 */
const MIN_USABLE_TARGET_PX = 24;

/**
 * Interactive controls — the original universe of `findObscuredControls`.
 */
const SEL_INTERACTIVE =
  'a[href], button, input, select, textarea, [role="tab"], [role="radio"], [tabindex]:not([tabindex="-1"])';

/**
 * CRITICAL NON-INTERACTIVE LABELS.
 *
 * A FOCUSED, ENUMERATED set — emphatically not "every text node". Scanning all
 * text would report every grid child that shares a cell with its own parent and
 * would drown the real findings; this list names the labels whose disappearance
 * changes what the user believes about the system:
 *
 *   `.record-title`, `.record-title-link`  which record am I editing
 *   `.record-surface`                      which sample surface it describes
 *   `.mode-chip`                           synthetic-only vs anything else — a
 *                                          governance claim, not decoration
 *   `.statusbar-*`                         phase, pending-blocker count,
 *                                          advisory state, export state
 *   `h1`                                   the page title
 *
 * `h1.sr-only` is in the set but never reported: it measures 1x1, and the
 * width guard in the probe drops boxes under 2px (their content-loss question
 * belongs to `findClippedText`, which knows the visually-hidden allowlist).
 * Headings below `<h1>` are deliberately NOT included — they are section labels,
 * and including them was measured to add noise without adding a finding.
 */
const SEL_CRITICAL_LABELS = [
  '.record-title',
  '.record-title-link',
  '.record-surface',
  '.mode-chip',
  '.statusbar-phase',
  '.statusbar-note',
  '.statusbar-pending',
  '.statusbar-advisory',
  '.statusbar-eyebrow',
  '.statusbar-right',
  'h1',
].join(', ');

export { SEL_CRITICAL_LABELS, SEL_INTERACTIVE, MIN_MEANINGFUL_TEXT_PX, CRITICAL_MIN_TEXT_PX, MIN_USABLE_TARGET_PX };

/*
 * NOTE on visibility, duplicated verbatim inside every `page.evaluate` body
 * below (they are serialised into the page, so they cannot close over a shared
 * helper defined here):
 *
 *   `getComputedStyle(...).display !== 'none'` is NOT sufficient. A CLOSED
 *   `<details>` keeps its children in layout with `content-visibility: hidden`
 *   in Chromium, so `getBoundingClientRect()` returns a real, non-zero box for
 *   content that is never painted. That produced three confident, wrong
 *   "occluded control" reports against the Endpoint Explorer's collapsed
 *   "Code Examples" disclosure, on every viewport.
 *   `Element.checkVisibility({ contentVisibilityAuto: true })` knows the
 *   difference; the explicit `details:not([open])` test is the fallback.
 */

export interface Offender {
  selector: string;
  detail: string;
  text: string;
  /**
   * Which rule produced the finding. Optional so that pre-existing
   * `toEqual([])` assertions and the `layout-baseline.ts` selector matching are
   * unaffected.
   */
  kind?: string;
}

/** A matcher pair passed into the page: an allowlist id and its CSS selector. */
export interface Matcher {
  id: string;
  match: string;
}

/**
 * Does the DOCUMENT scroll horizontally?
 *
 * This is the assertion the brief names explicitly:
 * `document.documentElement.scrollWidth <= clientWidth`. A wide table or code
 * block is allowed to scroll *inside its own container*; the page body is not.
 *
 * NOT SUFFICIENT ON ITS OWN, which is blind spot 1: a region nested inside the
 * page can overflow while the document stays exactly at its client width.
 * Always pair this with `findOverflowingRegions`.
 */
export async function horizontalPageScroll(
  page: Page
): Promise<{ docScrollWidth: number; docClientWidth: number; bodyScrollWidth: number; bodyClientWidth: number }> {
  return page.evaluate(() => ({
    docScrollWidth: document.documentElement.scrollWidth,
    docClientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    bodyClientWidth: document.body.clientWidth,
  }));
}

export interface OverflowRegion extends Offender {
  kind: 'clip' | 'scroll';
  scrollWidth: number;
  clientWidth: number;
  overflowX: string;
  /** The widest descendant crossing the right content edge — the thing to fix. */
  culprit: string | null;
  /** Set when an allowlist entry matched. */
  allowedBy?: string;
}

export interface OverflowReport {
  /** Genuine findings: content clipped away, or an unintended inner scroller. */
  offenders: OverflowRegion[];
  /** Matched a narrow, documented entry in `layout-allowlist.ts`. */
  allowed: OverflowRegion[];
  /**
   * Overflow with NO VISIBLE, NOT-ALREADY-CONTAINED SOURCE — see the long note
   * on `findOverflowingRegions`. Reported, never silently dropped.
   */
  contained: OverflowRegion[];
  /**
   * Single-line `text-overflow: ellipsis` containers. Reported, NEVER silently
   * dropped, but handed to `findClippedText`, which judges MAGNITUDE. See the
   * long note below.
   */
  ellipsisDeferred: OverflowRegion[];
}

/**
 * NESTED horizontal overflow — blind spot 1.
 *
 * Reports every rendered element whose `scrollWidth` exceeds its `clientWidth`
 * AND whose computed `overflow-x` actually CLIPS or SCROLLS
 * (`hidden | clip | auto | scroll`). For each one it also names the widest
 * descendant crossing the content edge, because "screen-card overflows by
 * 222px" is not actionable and "…because footer.statusbar is 575px wide" is.
 *
 * ── Why elements with `overflow-x: visible` are not reported ────────────────
 *
 * This is the one exclusion that could be mistaken for a loophole, so here is
 * the completeness argument in full. A box with `overflow-x: visible` does not
 * hide anything: its content simply spills into the parent. The harm — text
 * gone, or an unexpected inner scrollbar — materialises at the FIRST ancestor
 * that clips or scrolls. Every overflow chain therefore terminates in exactly
 * one of two places:
 *
 *   * a clipping/scrolling box, which this probe reports, or
 *   * the document itself, which `horizontalPageScroll` reports.
 *
 * So nothing is lost, and the finding is attributed to the box where the user
 * is harmed instead of to every ancestor in the spill chain. Measured: on
 * `/experiments` at 375 the spill chain is `div.page-header` (visible, 448/297)
 * → `main.screen-main.pad` (**auto**, 476/353) → `div.screen-card` (**hidden**,
 * 476/353); the probe names the last two, which are the two that matter.
 *
 * KNOWN LIMIT, stated rather than implied: in a left-to-right writing mode,
 * `scrollWidth` accounts for content overflowing to the RIGHT only. Content
 * pushed off the LEFT edge of a clipping box does not raise `scrollWidth` and
 * is invisible to this probe. `findClippedText` covers that direction (it tests
 * `rect.left < ancestorRect.left`), which is why both probes are run together.
 *
 * ── Why "overflow with no visible source" is separated ──────────────────────
 *
 * `scrollWidth` is the browser's number and it counts things the user cannot
 * see. Two of them occur in this app and both were MEASURED producing wrong
 * findings before this rule existed:
 *
 *   * an OFF-CANVAS PANEL parked outside the box on purpose. In drawer mode the
 *     Assistant is `position: fixed; right: 0; transform: translateX(100%)` with
 *     `visibility: hidden` when closed (`src/components/assistant-drawer.css:55`).
 *     Its parked box inflated `div.screen-card`'s `scrollWidth` to 602 and was
 *     named as the culprit on five record surfaces. Nothing is hidden by it —
 *     it is hidden.
 *   * content that is ALREADY CONTAINED by a nested scroller. The widest
 *     descendant of `section.preview` is a source line 519px to the right, but
 *     it lives inside `div.preview-lines.scroll-x`, which scrolls it. Naming
 *     that line sent the reader to the wrong stylesheet; the real culprit was
 *     `h2.preview-prov-title` at 418.
 *
 * So the culprit search considers only descendants that are RENDERED and are
 * NOT already inside an intermediate clipping/scrolling box. If that search
 * finds nothing AND the element has no text of its own, the overflow has no
 * visible source and the region goes to `contained` rather than `offenders`.
 * The text-of-its-own condition matters: an element whose own text overflows
 * has no element descendant to blame, and dropping it would have hidden real
 * clipping.
 *
 * ── Why single-line ellipsis containers are separated, not exempted ─────────
 *
 * `scrollWidth > clientWidth` is the DEFINITION of an ellipsised element: if it
 * were not overflowing, no ellipsis would be drawn. Reporting them here would
 * mean reporting every truncated label in the app as an overflow defect, which
 * is noise, and allowlisting them one by one would grow without bound. They are
 * therefore returned in `ellipsisDeferred` — visible in the output, counted,
 * never dropped — and the QUESTION THAT MATTERS (is any text still readable?)
 * is answered by `findClippedText`'s magnitude tier. That hand-off is a real
 * one and is asserted by `specs/layout-widths.spec.ts`, which checks that a
 * zero-width ellipsis container deferred here is reported there.
 */
export async function findOverflowingRegions(page: Page, allowances: Matcher[] = []): Promise<OverflowReport> {
  return page.evaluate(
    ({ tol, allow }) => {
      const one = (e: Element) => {
        const id = e.id ? `#${e.id}` : '';
        const cls =
          typeof e.className === 'string' && e.className
            ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.')
            : '';
        return `${e.tagName.toLowerCase()}${id}${cls}`;
      };
      const describe = (el: Element): string => {
        const parts = [one(el)];
        let a = el.parentElement;
        while (a && parts.length < 3) {
          if (a.id || (typeof a.className === 'string' && a.className.trim())) parts.push(one(a));
          a = a.parentElement;
        }
        return parts.join(' < ');
      };
      const rendered = (el: Element): boolean => {
        if (el.closest('details:not([open])')) return false;
        const anyEl = el as Element & { checkVisibility?: (o: Record<string, boolean>) => boolean };
        if (typeof anyEl.checkVisibility === 'function') {
          return anyEl.checkVisibility({
            contentVisibilityAuto: true,
            opacityProperty: true,
            visibilityProperty: true,
          });
        }
        const st = getComputedStyle(el);
        return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity) !== 0;
      };

      // Type annotations are erased before serialisation, so referring to the
      // outer `OverflowRegion` type here is safe; only VALUES cannot cross.
      const offenders: OverflowRegion[] = [];
      const allowed: OverflowRegion[] = [];
      const contained: OverflowRegion[] = [];
      const ellipsisDeferred: OverflowRegion[] = [];

      const ownText = (el: Element): string => {
        let s = '';
        for (const n of Array.from(el.childNodes)) if (n.nodeType === Node.TEXT_NODE) s += n.textContent ?? '';
        return s.trim();
      };

      for (const el of Array.from(document.querySelectorAll<HTMLElement>('*'))) {
        if (el.scrollWidth <= el.clientWidth + tol) continue;
        const st = getComputedStyle(el);
        const ox = st.overflowX;
        // See the header note: `visible` SPILLS; the harm is reported at the
        // first clipping/scrolling ancestor, or by `horizontalPageScroll`.
        if (ox === 'visible') continue;
        if (!rendered(el)) continue;

        // The widest VISIBLE, NOT-ALREADY-CONTAINED descendant crossing the
        // content edge — the thing to fix. See the header for why both filters
        // are needed and what each one was measured to get wrong without them.
        const r = el.getBoundingClientRect();
        const contentRight = r.left + el.clientLeft + el.clientWidth;
        let culprit: Element | null = null;
        let worst = contentRight + tol;
        for (const d of Array.from(el.querySelectorAll('*'))) {
          const dr = d.getBoundingClientRect();
          if (dr.width === 0 && dr.height === 0) continue;
          if (dr.right <= worst) continue;
          if (!rendered(d)) continue;
          let alreadyContained = false;
          for (let a = d.parentElement; a && a !== el; a = a.parentElement) {
            if (getComputedStyle(a).overflowX !== 'visible') {
              alreadyContained = true;
              break;
            }
          }
          if (alreadyContained) continue;
          worst = dr.right;
          culprit = d;
        }

        const entry: OverflowRegion = {
          selector: describe(el),
          kind: ox === 'hidden' || ox === 'clip' ? ('clip' as const) : ('scroll' as const),
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
          overflowX: ox,
          culprit: culprit ? `${describe(culprit)} (right edge ${Math.round(worst)} vs ${Math.round(contentRight)})` : null,
          detail:
            `${ox === 'hidden' || ox === 'clip' ? 'clips' : 'scrolls'} horizontally: ` +
            `scrollWidth ${el.scrollWidth} vs clientWidth ${el.clientWidth} (overflow-x: ${ox})` +
            (culprit ? `; widest overflowing child: ${describe(culprit)}` : ''),
          text: (el.textContent ?? '').trim().slice(0, 60),
        };

        const hit = allow.find((a) => {
          try {
            return el.matches(a.match);
          } catch {
            return false;
          }
        });
        if (hit) {
          allowed.push({ ...entry, allowedBy: hit.id });
          continue;
        }
        // A single-line ellipsis container overflows BY DEFINITION. Deferred to
        // `findClippedText`, which judges how much text survives.
        const singleLine = st.whiteSpace === 'nowrap' || st.whiteSpace === 'pre';
        if (st.textOverflow === 'ellipsis' && singleLine) {
          ellipsisDeferred.push(entry);
          continue;
        }
        // No visible, not-already-contained source, and no text of its own:
        // `scrollWidth` is counting a parked off-canvas panel or content that a
        // nested scroller already handles. Nothing is hidden from the user.
        if (!culprit && !ownText(el)) {
          contained.push(entry);
          continue;
        }
        offenders.push(entry);
      }

      return { offenders, allowed, contained, ellipsisDeferred };
    },
    { tol: TOL, allow: allowances }
  );
}

/**
 * Text that is CLIPPED — cut off with no way for the user to read it.
 *
 * FOUR tiers, in the order they are decided:
 *
 *   `critical-loss`  a page `<h1>` or a record title showing less than
 *                    CRITICAL_MIN_TEXT_PX of its content;
 *   `total-loss`     any text-bearing element showing less than
 *                    MIN_MEANINGFUL_TEXT_PX — including elements of width ZERO,
 *                    which the previous version skipped before it could look at
 *                    them, and including `text-overflow: ellipsis` boxes, which
 *                    the previous version exempted unconditionally;
 *   `clipped-x`      pushed sideways out of an `overflow: hidden` ancestor;
 *   `clipped-y`      pushed downwards out of one.
 *
 * WHAT IS STILL ALLOWED, and on what condition:
 *
 *   * Deliberate single-line truncation (`text-overflow: ellipsis`) — ONLY
 *     while the element still shows >= MIN_MEANINGFUL_TEXT_PX of text. That
 *     condition is the whole fix for blind spot 2: `span.trail-key` keeps 253
 *     of 291px and passes; `span.record-title` keeps 0 of 250px and does not.
 *   * Content inside a SCROLLABLE region (`overflow: auto | scroll`): the walk
 *     is per-axis and STOPS at the first scrollable ancestor, because whatever
 *     is inside it is reachable by scrolling. This app nests
 *     `main.screen-main` (`overflow: auto`) inside `div.screen-card`
 *     (`overflow: hidden`), so without it every below-the-fold paragraph would
 *     be reported as "clipped by .screen-card".
 *   * Visually-hidden accessible-name carriers, BY EXPLICIT CLASS, from
 *     `layout-allowlist.ts`. Never by geometry — a "clientWidth <= 1 is fine"
 *     rule would have swallowed the zero-width record title.
 *
 * @param hiddenTextMatchers visually-hidden allowlist entries; defaults to every
 *   entry in `layout-allowlist.ts` so existing callers keep working.
 */
export async function findClippedText(
  page: Page,
  root = 'body',
  hiddenTextMatchers: Matcher[] = HIDDEN_TEXT_ALLOWANCES.map((a) => ({ id: a.id, match: a.match }))
): Promise<Offender[]> {
  return page.evaluate(
    ({
      rootSel,
      tol,
      minText,
      criticalMinText,
      maxVisibleFraction,
      severeFraction,
      minLostPx,
      criticalSel,
      hidden,
    }) => {
      const out: { selector: string; detail: string; text: string; kind: string }[] = [];
      const container = document.querySelector(rootSel);
      if (!container) return out;

      // Include the nearest classed ancestors: an unclassed `<span>` on its own
      // ("span: clipped horizontally") is unfindable in a 60-file codebase.
      const describe = (el: Element): string => {
        const one = (e: Element) => {
          const id = e.id ? `#${e.id}` : '';
          const cls =
            typeof e.className === 'string' && e.className
              ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.')
              : '';
          return `${e.tagName.toLowerCase()}${id}${cls}`;
        };
        const parts = [one(el)];
        let a = el.parentElement;
        while (a && parts.length < 3) {
          if (a.id || (typeof a.className === 'string' && a.className.trim())) parts.push(one(a));
          a = a.parentElement;
        }
        return parts.join(' < ');
      };

      const rendered = (el: Element): boolean => {
        if (el.closest('details:not([open])')) return false;
        const anyEl = el as Element & {
          checkVisibility?: (o: Record<string, boolean>) => boolean;
        };
        if (typeof anyEl.checkVisibility === 'function') {
          return anyEl.checkVisibility({
            contentVisibilityAuto: true,
            opacityProperty: true,
            visibilityProperty: true,
          });
        }
        const st = getComputedStyle(el);
        return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity) !== 0;
      };

      const ownText = (el: Element): string => {
        let s = '';
        for (const n of Array.from(el.childNodes)) if (n.nodeType === Node.TEXT_NODE) s += n.textContent ?? '';
        return s.trim();
      };

      const matchesAny = (el: Element, list: { id: string; match: string }[]) =>
        list.find((m) => {
          try {
            return el.matches(m.match);
          } catch {
            return false;
          }
        });

      for (const el of Array.from(container.querySelectorAll<HTMLElement>('*'))) {
        const text = ownText(el);
        if (!text) continue;
        if (!rendered(el)) continue;
        // Visually-hidden accessible-name carriers are SUPPOSED to paint
        // nothing. Matched by explicit class, never by size.
        if (matchesAny(el, hidden)) continue;

        const rect = el.getBoundingClientRect();
        const own = getComputedStyle(el);
        const critical = (() => {
          try {
            return el.matches(criticalSel);
          } catch {
            return false;
          }
        })();

        // ── Tier 1/2: is any meaningful text actually painted? ──────────────
        // `rect.width` is what the user can see; `scrollWidth` is what the
        // element wants to show. The previous version `continue`d here on
        // `rect.width === 0`, which is exactly how a 100%-lost record title
        // stayed invisible to the suite.
        //
        // KNOWN LIMIT, recorded rather than implied: Chromium reports
        // `scrollWidth === 0` for non-replaced INLINE elements, so this tier
        // cannot see them at all. Their clipping is still covered by the
        // per-axis ancestor walk further down.
        const visible = rect.width;
        const wanted = Math.max(el.scrollWidth, 0);
        const lost = wanted - visible;
        const fraction = wanted > 0 ? visible / wanted : 1;
        const floorPx = critical ? criticalMinText : minText;
        // Arm A: below the absolute readable floor, narrowed by the ratio.
        const belowFloor = fraction < maxVisibleFraction && visible < floorPx;
        // Arm B: severe FRACTIONAL loss, on elements that destroy their own
        // overflow. Fires regardless of absolute width — see the header block
        // on SEVERE_LOSS_FRACTION for why Arm A alone left a hole and why this
        // arm is restricted to `overflow-x: hidden | clip`.
        const clipsOwnContent = own.overflowX === 'hidden' || own.overflowX === 'clip';
        const severelyClipped = clipsOwnContent && fraction < severeFraction;
        if (wanted > 2 && lost > minLostPx && (belowFloor || severelyClipped)) {
          const pct = wanted > 0 ? Math.round((visible / wanted) * 100) : 0;
          out.push({
            selector: describe(el),
            kind: critical ? 'critical-loss' : 'total-loss',
            detail:
              `${critical ? 'CRITICAL label' : 'text'} is not readable: ${Math.round(visible)}px visible of ` +
              `${wanted}px of content (${pct}%) — ` +
              (belowFloor
                ? `below the ${floorPx}px readable floor`
                : `${Math.round((1 - fraction) * 100)}% of the content is destroyed by ` +
                  `"overflow-x: ${own.overflowX}" (severe-loss threshold ${Math.round(severeFraction * 100)}%)`) +
              (own.textOverflow === 'ellipsis'
                ? ` — "text-overflow: ellipsis" is set, but at ${Math.round(visible)}px of ${wanted}px it cannot ` +
                  'paint a meaningful fragment, so the truncation is content loss, not truncation'
                : ''),
            text: text.slice(0, 80),
          });
          continue;
        }
        if (rect.width === 0 || rect.height === 0) continue;

        // Per-axis walk. `liveX`/`liveY` go false as soon as that axis is
        // resolved — either by a scrollable ancestor (reachable, stop looking)
        // or by a reported clip.
        let liveX = true;
        let liveY = true;
        // Truncation only excuses a horizontal clip while enough text survives.
        // Reaching this point already means BOTH content-loss arms declined the
        // element, so the severe-fraction hole described in the header — an
        // element clearing the absolute floor at 6% visible and then being
        // excused here too — is closed at its source rather than patched twice.
        const meaningfullyVisible = visible >= (critical ? criticalMinText : minText);
        const ellipsised = own.textOverflow === 'ellipsis' && meaningfullyVisible;

        for (let a = el.parentElement; a && (liveX || liveY); a = a.parentElement) {
          const st = getComputedStyle(a);
          const ar = a.getBoundingClientRect();

          if (liveX) {
            if (st.overflowX === 'auto' || st.overflowX === 'scroll') {
              liveX = false;
            } else if (st.overflowX === 'hidden' || st.overflowX === 'clip') {
              const truncated = ellipsised || (st.textOverflow === 'ellipsis' && meaningfullyVisible);
              if (!truncated && (rect.right > ar.right + tol || rect.left < ar.left - tol)) {
                out.push({
                  selector: describe(el),
                  kind: 'clipped-x',
                  detail: `clipped horizontally by ${describe(a)} (el ${Math.round(rect.left)}..${Math.round(
                    rect.right
                  )} vs container ${Math.round(ar.left)}..${Math.round(ar.right)})`,
                  text: text.slice(0, 80),
                });
              }
              liveX = false;
            }
          }

          if (liveY) {
            if (st.overflowY === 'auto' || st.overflowY === 'scroll') {
              liveY = false;
            } else if (st.overflowY === 'hidden' || st.overflowY === 'clip') {
              if (rect.bottom > ar.bottom + tol || rect.top < ar.top - tol) {
                out.push({
                  selector: describe(el),
                  kind: 'clipped-y',
                  detail: `clipped vertically by ${describe(a)} (el ${Math.round(rect.top)}..${Math.round(
                    rect.bottom
                  )} vs container ${Math.round(ar.top)}..${Math.round(ar.bottom)})`,
                  text: text.slice(0, 80),
                });
              }
              liveY = false;
            }
          }

          if (a === document.documentElement) break;
        }
      }
      // De-duplicate — one broken container usually clips many children.
      const seen = new Set<string>();
      return out.filter((o) => {
        const k = o.selector + '|' + o.detail.split('(')[0];
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
    },
    {
      rootSel: root,
      tol: TOL,
      minText: MIN_MEANINGFUL_TEXT_PX,
      criticalMinText: CRITICAL_MIN_TEXT_PX,
      maxVisibleFraction: MAX_VISIBLE_FRACTION_FOR_LOSS,
      severeFraction: SEVERE_LOSS_FRACTION,
      minLostPx: MIN_LOST_PX,
      criticalSel: SEL_CRITICAL_LABELS,
      hidden: hiddenTextMatchers,
    }
  );
}

/**
 * OVERLAP, measured the way it actually harms a user: is anything the user must
 * be able to see or press covered by something else, or squeezed to a sliver?
 *
 * Pairwise box-intersection over every element is mathematically "overlap" but
 * is meaningless in a CSS-grid app (every ancestor overlaps its children). What
 * matters is occlusion: hit-test the element and check the topmost thing there
 * belongs to it.
 *
 * ── The universe: interactive controls PLUS a focused label set ─────────────
 *
 * Blind spot 3(a): the probe used to scan interactive elements only, so
 * `span.record-surface` — a non-interactive label that genuinely paints over
 * the search button and the mode chip at 375px — could not be reported, in
 * either direction. `SEL_CRITICAL_LABELS` adds the labels whose disappearance
 * misleads the user, and nothing else. Labels are exempt from the usable-width
 * test (a narrow label is a text question, answered by `findClippedText`); they
 * are subject to the hit tests.
 *
 * ── Partial visibility: three tests, because one is not enough ──────────────
 *
 * Blind spot 3(b): hit-testing the centre of the VISIBLE INTERSECTION means a
 * control with a 4.9px sliver showing hit-tests to itself and reports clean.
 * Measured: the New Record button at `/experiments`, 375x812, box 359..487 in a
 * 375px viewport — 4.9px of a 128px button — passed the old probe, while
 * `document.elementFromPoint(374, y)` returned `DIV.app`. So:
 *
 *   1. USABLE WIDTH. At least `min(intendedWidth, 24)` px must be visible
 *      (WCAG 2.5.8). Interactive controls only.
 *   2. MULTI-POINT HIT TEST over the INTENDED box, not the visible slice: five
 *      points at 10/30/50/70/90% of the full width. Two or more foreign hits is
 *      a finding — one is allowed for sub-pixel and border-radius rounding.
 *   3. THE VISIBLE CENTRE, kept from the original probe, which catches a
 *      control fully covered by an overlay.
 *
 * The visible-area RATIO is computed and reported in every finding's detail so
 * a reviewer can see the magnitude, and is what makes the difference between
 * "a 128px button with 4% showing" and "a 1000px-wide element cropped by a
 * 375px viewport", which is normal and is NOT reported.
 *
 * ── What is deliberately KEPT from the original ─────────────────────────────
 *
 *   * The closed-`<details>` / `content-visibility` handling — three confident,
 *     wrong reports came from ignoring it.
 *   * The `scrollIntoView` second chance: content sitting under a panel at one
 *     scroll offset and reachable by scrolling is normal. It is now
 *     VERTICAL-ONLY: every ancestor's `scrollLeft` is captured before the call
 *     and restored after it. Without that restore, `scrollIntoView` would
 *     silently scroll `main.screen-main` (which is itself an unintended
 *     horizontal scroller, finding E1) sideways to reveal the New Record button
 *     and then declare it fine — using one defect to excuse another. Vertical
 *     scrolling is how a page is read; horizontal scrolling of the main content
 *     region is the defect.
 *   * Elements with no visible area at all are still skipped, so callers should
 *     invoke this at more than one scroll position.
 */
export async function findObscuredControls(page: Page): Promise<Offender[]> {
  return page.evaluate(
    ({ selInteractive, selLabels, minUsable }) => {
      const out: { selector: string; detail: string; text: string; kind: string }[] = [];
      // Include the nearest classed ancestors: an unclassed `<span>` on its own
      // ("span: clipped horizontally") is unfindable in a 60-file codebase.
      const describe = (el: Element): string => {
        const one = (e: Element) => {
          const id = e.id ? `#${e.id}` : '';
          const cls =
            typeof e.className === 'string' && e.className
              ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.')
              : '';
          return `${e.tagName.toLowerCase()}${id}${cls}`;
        };
        const parts = [one(el)];
        let a = el.parentElement;
        while (a && parts.length < 3) {
          if (a.id || (typeof a.className === 'string' && a.className.trim())) parts.push(one(a));
          a = a.parentElement;
        }
        return parts.join(' < ');
      };

      const vw = document.documentElement.clientWidth;
      const vh = document.documentElement.clientHeight;

      const rendered = (el: Element): boolean => {
        if (el.closest('details:not([open])')) return false;
        const anyEl = el as Element & {
          checkVisibility?: (o: Record<string, boolean>) => boolean;
        };
        if (typeof anyEl.checkVisibility === 'function') {
          return anyEl.checkVisibility({
            contentVisibilityAuto: true,
            opacityProperty: true,
            visibilityProperty: true,
          });
        }
        const st = getComputedStyle(el);
        return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity) !== 0;
      };

      /** Intersect the element's box with every clipping/scrolling ancestor and the viewport. */
      const visibleRect = (el: HTMLElement) => {
        const r = el.getBoundingClientRect();
        let left = Math.max(r.left, 0);
        let top = Math.max(r.top, 0);
        let right = Math.min(r.right, vw);
        let bottom = Math.min(r.bottom, vh);
        for (let a = el.parentElement; a; a = a.parentElement) {
          const st = getComputedStyle(a);
          if (st.overflowX !== 'visible' || st.overflowY !== 'visible') {
            const ar = a.getBoundingClientRect();
            if (st.overflowX !== 'visible') {
              left = Math.max(left, ar.left);
              right = Math.min(right, ar.right);
            }
            if (st.overflowY !== 'visible') {
              top = Math.max(top, ar.top);
              bottom = Math.min(bottom, ar.bottom);
            }
          }
          if (a === document.documentElement) break;
        }
        return { left, top, right, bottom, width: right - left, height: bottom - top };
      };

      /** Is the topmost element at (x, y) part of `target`'s own story? */
      const hitBelongs = (target: HTMLElement, hit: Element | null): boolean => {
        if (!hit) return true; // nothing there to blame
        if (hit === target || target.contains(hit) || hit.contains(target)) return true;
        // A <label> that forwards its click to the control is not occlusion.
        if (hit instanceof HTMLLabelElement && hit.control === target) return true;
        return false;
      };

      /**
       * `scrollIntoView`, VERTICALLY ONLY. See the header: allowing the
       * horizontal scroll would let the unintended inner scroller excuse the
       * sliver it causes.
       */
      const scrollVerticallyIntoView = (el: HTMLElement) => {
        const saved: [Element, number][] = [];
        for (let a: Element | null = el.parentElement; a; a = a.parentElement) {
          saved.push([a, a.scrollLeft]);
          if (a === document.documentElement) break;
        }
        const pageX = window.scrollX;
        el.scrollIntoView({ block: 'center', inline: 'nearest' });
        for (const [a, left] of saved) a.scrollLeft = left;
        window.scrollTo(pageX, window.scrollY);
      };

      interface Assessment {
        verdict: string | null;
        detail: string;
      }

      const assess = (el: HTMLElement, interactive: boolean): Assessment => {
        const r = el.getBoundingClientRect();
        const v = visibleRect(el);
        const area = r.width * r.height;
        const ratio = area > 0 ? Math.max(0, (v.width * v.height) / area) : 0;
        const geom =
          `intended ${Math.round(r.left)}..${Math.round(r.right)} (${Math.round(r.width)}px), ` +
          `visible ${Math.round(v.left)}..${Math.round(v.right)} (${Math.round(v.width)}px), ` +
          `visible area ratio ${ratio.toFixed(2)}`;

        // Nothing visible at all: scrolled or clipped away entirely, which is
        // "not on screen right now", not "covered". Documented, deliberate.
        if (v.width < 2 || v.height < 2) return { verdict: null, detail: geom };

        // TEST 1 — usable width (interactive controls only).
        if (interactive && v.width + 0.5 < Math.min(r.width, minUsable)) {
          return {
            verdict: 'unusable-sliver',
            detail:
              `only ${v.width.toFixed(1)}px of a ${Math.round(r.width)}px control is visible ` +
              `(needs at least ${Math.round(Math.min(r.width, minUsable))}px; WCAG 2.5.8 target size is ` +
              `${minUsable}px) — ${geom}`,
          };
        }

        // TEST 2 — multi-point hit test over the INTENDED box.
        const foreign: string[] = [];
        let outside = 0;
        let sampled = 0;
        for (let i = 0; i < 5; i++) {
          const x = r.left + (r.width * (i + 0.5)) / 5;
          const y = r.top + r.height / 2;
          if (x < 0 || x >= vw || y < 0 || y >= vh) {
            outside++;
            continue;
          }
          sampled++;
          const hit = document.elementFromPoint(x, y);
          if (!hitBelongs(el, hit)) foreign.push(`${Math.round(x)}→${hit ? describe(hit) : 'null'}`);
        }
        if (foreign.length >= 2) {
          return {
            verdict: 'covered',
            detail:
              `${foreign.length} of ${sampled} sampled points across the intended box hit something else ` +
              `[${foreign.join(', ')}]${outside ? `; ${outside} point(s) lie outside the viewport` : ''} — ${geom}`,
          };
        }

        // TEST 3 — the visible centre (the original probe's test): catches a
        // control completely covered by an overlay.
        const cx = v.left + v.width / 2;
        const cy = v.top + v.height / 2;
        const centreHit = document.elementFromPoint(cx, cy);
        if (!hitBelongs(el, centreHit)) {
          return {
            verdict: 'covered',
            detail:
              `visible centre (${Math.round(cx)},${Math.round(cy)}) hits ${
                centreHit ? describe(centreHit) : 'null'
              } instead — ${geom}`,
          };
        }
        return { verdict: null, detail: geom };
      };

      const candidates = new Set<HTMLElement>();
      for (const el of Array.from(document.querySelectorAll<HTMLElement>(selInteractive))) candidates.add(el);
      for (const el of Array.from(document.querySelectorAll<HTMLElement>(selLabels))) candidates.add(el);

      for (const el of Array.from(candidates)) {
        if (!rendered(el)) continue;
        const interactive = el.matches(selInteractive);
        const st = getComputedStyle(el);
        if (interactive && st.pointerEvents === 'none') continue;
        const r = el.getBoundingClientRect();
        // Sub-2px boxes carry no occlusion question. A zero-width LABEL is a
        // content-loss question and belongs to `findClippedText`, which knows
        // the visually-hidden allowlist; deciding it here would double-report
        // `h1.sr-only` on every surface.
        if (r.width < 2 || r.height < 2) continue;

        const first = assess(el, interactive);
        if (first.verdict === null) continue;

        // Second chance: scroll it into view VERTICALLY, exactly as a user (or
        // Playwright's own auto-scroll before a click) would, and re-test.
        scrollVerticallyIntoView(el);
        const second = assess(el, interactive);
        if (second.verdict === null) continue;

        out.push({
          selector: describe(el),
          kind: second.verdict + (interactive ? '' : ':label'),
          detail: `${
            second.verdict === 'unusable-sliver' ? 'still an unusable sliver' : 'still occluded'
          } after vertical scrollIntoView: ${second.detail}`,
          text: (el.textContent ?? '').trim().slice(0, 60),
        });
      }
      return out;
    },
    { selInteractive: SEL_INTERACTIVE, selLabels: SEL_CRITICAL_LABELS, minUsable: MIN_USABLE_TARGET_PX }
  );
}

/** Scroll the window to the bottom and settle. Used to widen occlusion coverage. */
export async function scrollToBottom(page: Page): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(120);
}

export async function scrollToTop(page: Page): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(120);
}

/** The rendered font family, so macOS (SF Pro) vs Linux (DejaVu/Liberation) is visible in CI logs. */
export async function renderedFontFamily(page: Page): Promise<string> {
  return page.evaluate(() => {
    const st = getComputedStyle(document.body);
    return `${st.fontFamily} @ ${st.fontSize}`;
  });
}

export function render(offenders: Offender[]): string {
  return offenders
    .map((o) => `  - [${o.kind ?? 'offender'}] ${o.selector}: ${o.detail}\n      text: ${JSON.stringify(o.text)}`)
    .join('\n');
}

export function renderOverflow(regions: OverflowRegion[]): string {
  return regions
    .map(
      (r) =>
        `  - [${r.kind}] ${r.selector}: scrollWidth ${r.scrollWidth} vs clientWidth ${r.clientWidth} ` +
        `(overflow-x: ${r.overflowX})${r.culprit ? `\n      widest overflowing child: ${r.culprit}` : ''}`
    )
    .join('\n');
}
